"""EXPLORATORY pilot candidate ``t13-keep-one-k1`` (Sprint 30, ``docs/SPRINT30_T13_K1_PILOT.md``).

Exploratory track: not a baseline, not eligible for promotion and never packaged. Its only authorized engine use is
the owner-approved Sprint 30 pilot (card ``s30-t13-k1-pilot-1``, sessions 2798 to 2801 at most); any other engine use
needs new owner approval.

``baseline-v2`` decides first, on the seat's own current observation and memory, unchanged
(:mod:`.exploratory_addon`). The add-on then applies one rule to that decision and nothing else (Sprint 29 portfolio
item H1, restated with the Sprint 30 owner brief):

* **Objective and centre.** An objective is a ``cities`` entry of the seat's observation with an integer ``coord``; the
  side **holds** it when its ``flag`` equals the side's colour. Its **centre** is that hex.
* **Occupants.** The own ground units on the centre: operators of the seat's colour, of type 1 or 2 (artillery
  included), whose ``cur_hex`` is the centre. Passengers are not operators.
* **Departing and remaining.** An occupant **departs** when it has a non-empty ``move_path`` (an accepted movement
  already under way) or ``baseline-v2`` emits a MOVE for it at this decision; otherwise it **remains**.
* **Trigger**, per held objective at a play decision (stage 2), in increasing centre order: the centre has at least
  one occupant, every occupant departs, and at least one of them departs by a ``baseline-v2`` MOVE. A held objective
  with a remaining occupant is left alone; one whose occupants all depart under earlier movement only is uncovered (an
  accepted path cannot be cancelled by withholding a new order) and is left alone.
* **Eligible holder**, an occupant that, in this order (the first failing level is recorded): ``A_stationary``
  (``speed`` not positive); ``B_no_route`` (empty ``move_path``); ``C_no_transition`` (the ``stop`` flag not 0, and
  ``move_to_stop_remain_time`` and ``change_state_remain_time`` not positive); ``D_no_transport_transition``
  (``get_on_remain_time`` and ``get_off_remain_time`` not positive); ``E_single_departing_move`` (``baseline-v2`` emits
  exactly one action for it, a MOVE with a non-empty route of integer hexes that does not end on the centre). Levels A
  to D are Sprint 28's idle levels of the same names (``experiments/t12_dispersion_shadow.py``), restated here so that
  the candidate's source set holds no analysis module; a missing field counts as not positive and not 0, the observed
  absence of a transition.
* **Selection.** Among the eligible holders, the one with the longest free-flow travel time of its ``baseline-v2`` MOVE
  (the sum along the MOVE's route of the per-hex times of ``experiments.t9_batch.path_times``: ``720 / basic_speed *
  entry cost``, rounded per hex, in the unit's movement mode from its current hex); ties go to the lower unit id. An
  eligible holder whose time is unreadable (unknown mode or speed, or a route edge outside the cost graph) is not
  ranked; when no eligible holder can be ranked the objective is skipped with ``no_travel_time``.
* **Action edit.** The selected holder's ``baseline-v2`` MOVE is withheld (removed). Nothing is added, replaced,
  reordered or constructed: no stop, no route change, no reassignment, no change to shots, occupations, embarkation or
  any other unit. At most one MOVE is withheld per objective; distinct centres hold distinct units, so the edits of
  different objectives never conflict.
* **Stateless.** No memory: every decision is recomputed from the current observation, so a holder is released as soon
  as the objective is no longer held, another occupant remains, the holder is gone, or it no longer qualifies.

Nothing reads another seat's view, the all-seeing state, the clock, randomness or any outcome. A malformed
observation raises, so the add-on wrapper plays ``baseline-v2``'s decision and records the error, never a guess.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..decision.routing import Router
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult

CANDIDATE_ID = "t13-keep-one-k1"
ADDON_NAME = "t13_keep_one_k1"
STATUS = "EXPLORATORY PILOT CANDIDATE - NOT ELIGIBLE FOR PROMOTION"
MOVE = 1
GROUND = (1, 2)
PLAY_STAGE = 2
#: Eligibility levels of a departing occupant, in evaluation order; the first failing level is recorded.
ELIGIBILITY = ("A_stationary", "B_no_route", "C_no_transition", "D_no_transport_transition",
               "E_single_departing_move")
ELIGIBLE = "eligible"
#: Outcome of one held objective at one play decision, first match.
OBJECTIVE_STATUS = ("no_centre_occupant", "holder_remains", "all_moving", "no_eligible_holder", "no_travel_time",
                    "withheld")
#: Raw operator fields the eligibility levels read.
TRANSITION_FIELDS = ("stop", "move_to_stop_remain_time", "change_state_remain_time", "get_on_remain_time",
                     "get_off_remain_time")

Travel = Callable[[Mapping[str, Any], Sequence[Any]], Optional[int]]


def as_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def router_travel(router: Router) -> Travel:
    """The free-flow travel time of a route from a unit's current hex: the sum of
    ``experiments.t9_batch.path_times``'s per-hex times, or ``None`` when any part is unreadable."""
    from .t9_batch import path_times

    def travel(unit: Mapping[str, Any], route: Sequence[Any]) -> Optional[int]:
        times, _ = path_times(router, unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                              unit.get("cur_hex"), list(route))
        return None if not times else int(sum(times))

    return travel


@dataclass(frozen=True)
class Occupant:
    """One own ground unit on a held objective's centre (private: unit id)."""

    unit: int
    departs: bool
    by_move: bool
    level: str  # ELIGIBLE, a failing level of ELIGIBILITY, or "remains"
    index: Optional[int]  # position of its baseline-v2 MOVE, if any
    travel: Optional[int]


@dataclass(frozen=True)
class ObjectiveCheck:
    """One held objective at one play decision (private: centre hex and unit ids)."""

    centre: int
    status: str
    occupants: Tuple[Occupant, ...]
    selected: Optional[int] = None
    index: Optional[int] = None
    travel: Optional[int] = None


@dataclass(frozen=True)
class K1Result:
    actions: Tuple[Mapping[str, Any], ...]
    withheld: Tuple[int, ...]
    checks: Tuple[ObjectiveCheck, ...]
    play: bool
    cur_step: Any


def eligibility(unit: Mapping[str, Any], own_actions: Sequence[Tuple[int, Mapping[str, Any]]], centre: int) -> str:
    """The first failing level of :data:`ELIGIBILITY` for a departing occupant, or :data:`ELIGIBLE`."""
    if positive(unit.get("speed")):
        return ELIGIBILITY[0]
    if unit.get("move_path"):
        return ELIGIBILITY[1]
    if unit.get("stop") == 0 or positive(unit.get("move_to_stop_remain_time")) \
            or positive(unit.get("change_state_remain_time")):
        return ELIGIBILITY[2]
    if positive(unit.get("get_on_remain_time")) or positive(unit.get("get_off_remain_time")):
        return ELIGIBILITY[3]
    if len(own_actions) != 1:
        return ELIGIBILITY[4]
    action = own_actions[0][1]
    route = action.get("move_path")
    if action.get("type") != MOVE or not isinstance(route, (list, tuple)) or not route \
            or any(as_int(h) is None for h in route) or route[-1] == centre:
        return ELIGIBILITY[4]
    return ELIGIBLE


def held_centres(raw: Mapping[str, Any], faction: int) -> List[int]:
    cities = raw.get("cities")
    if not isinstance(cities, (list, tuple)):
        raise ValueError("the observation carries no readable cities list")
    out = set()
    for city in cities:
        if not isinstance(city, Mapping) or as_int(city.get("coord")) is None:
            raise ValueError("a cities entry has no integer coord")
        if city.get("flag") == faction:
            out.add(city["coord"])
    return sorted(out)


def decide(raw: Mapping[str, Any], faction: int, base_actions: Sequence[Mapping[str, Any]],
           travel: Travel) -> K1Result:
    """One decision of the rule on the seat's own observation and ``baseline-v2``'s actions."""
    base = tuple(base_actions)
    time_info = raw.get("time") if isinstance(raw.get("time"), Mapping) else {}
    cur_step, stage = time_info.get("cur_step"), time_info.get("stage")
    if stage != PLAY_STAGE:
        return K1Result(base, (), (), False, cur_step)
    by_unit: Dict[int, List[Tuple[int, Mapping[str, Any]]]] = collections.defaultdict(list)
    for i, action in enumerate(base):
        unit = as_int(action.get("obj_id"))
        if unit is not None:
            by_unit[unit].append((i, action))
    on_hex: Dict[int, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for u in raw.get("operators") or ():
        if isinstance(u, Mapping) and u.get("color") == faction and u.get("type") in GROUND \
                and as_int(u.get("obj_id")) is not None and as_int(u.get("cur_hex")) is not None:
            on_hex[u["cur_hex"]].append(u)
    checks: List[ObjectiveCheck] = []
    withheld: List[int] = []
    for centre in held_centres(raw, faction):
        units = sorted(on_hex.get(centre, ()), key=lambda u: u["obj_id"])
        if not units:
            checks.append(ObjectiveCheck(centre, OBJECTIVE_STATUS[0], ()))
            continue
        occupants: List[Occupant] = []
        for u in units:
            own = by_unit.get(u["obj_id"], [])
            moves = [(i, a) for i, a in own if a.get("type") == MOVE]
            by_move = bool(moves)
            departs = bool(u.get("move_path")) or by_move
            if not departs:
                occupants.append(Occupant(u["obj_id"], False, False, "remains", None, None))
                continue
            level = eligibility(u, own, centre) if by_move else ELIGIBILITY[1]
            index = moves[0][0] if by_move else None
            time_ = travel(u, list(moves[0][1].get("move_path") or ())) if level == ELIGIBLE else None
            occupants.append(Occupant(u["obj_id"], True, by_move, level, index, time_))
        if any(not o.departs for o in occupants):
            checks.append(ObjectiveCheck(centre, OBJECTIVE_STATUS[1], tuple(occupants)))
            continue
        if not any(o.by_move for o in occupants):
            checks.append(ObjectiveCheck(centre, OBJECTIVE_STATUS[2], tuple(occupants)))
            continue
        eligible = [o for o in occupants if o.level == ELIGIBLE]
        if not eligible:
            checks.append(ObjectiveCheck(centre, OBJECTIVE_STATUS[3], tuple(occupants)))
            continue
        ranked = [o for o in eligible if o.travel is not None]
        if not ranked:
            checks.append(ObjectiveCheck(centre, OBJECTIVE_STATUS[4], tuple(occupants)))
            continue
        best = min(ranked, key=lambda o: (-o.travel, o.unit))
        withheld.append(best.index)
        checks.append(ObjectiveCheck(centre, OBJECTIVE_STATUS[5], tuple(occupants), best.unit, best.index,
                                     best.travel))
    if len(set(withheld)) != len(withheld):
        raise ValueError("two objectives selected the same action")
    drop = set(withheld)
    actions = tuple(a for i, a in enumerate(base) if i not in drop)
    return K1Result(actions, tuple(sorted(withheld)), tuple(checks), True, cur_step)


def change_records(result: K1Result) -> Tuple[Dict[str, Any], ...]:
    """One change record per withheld MOVE (private: unit ids and hexes)."""
    out = []
    for c in result.checks:
        if c.status == OBJECTIVE_STATUS[5]:
            out.append({"kind": "withheld_move", "objective": c.centre, "obj_id": c.selected, "index": c.index,
                        "travel": c.travel, "occupants": len(c.occupants),
                        "eligible": sum(1 for o in c.occupants if o.level == ELIGIBLE), "step": result.cur_step})
    return tuple(out)


def skip_counts(result: K1Result) -> Tuple[Tuple[str, int], ...]:
    """Counts of the objective outcomes of the decision (and of a non-play decision)."""
    counts: collections.Counter = collections.Counter()
    if not result.play:
        counts["decision not_play_stage"] += 1
    for c in result.checks:
        counts[f"objective {c.status}"] += 1
    return tuple(sorted(counts.items()))


def apply_rule(raw: Mapping[str, Any], faction: int, base_actions: Sequence[Mapping[str, Any]],
               travel: Travel) -> K1Result:
    return decide(raw, faction, base_actions, travel)


class K1Addon(Addon):
    name = ADDON_NAME

    def __init__(self, costs: Any, baseline: Any) -> None:
        super().__init__(costs, baseline)
        self.travel = router_travel(Router(costs)) if costs is not None else None

    def apply(self, observation: Any, seat: int, faction: int, base: Any,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        if self.travel is None:
            raise RuntimeError("no setup cost data: the free-flow relation is unreadable")
        if memory:
            raise ValueError("the rule is stateless; a non-empty add-on memory is a defect")
        result = apply_rule(observation.fields, faction, tuple(base.actions), self.travel)
        return AddonResult(result.actions, change_records(result), skip_counts(result), ())


class K1Policy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = K1Addon


class K1Agent(AddonAgent):
    policy_class = K1Policy
