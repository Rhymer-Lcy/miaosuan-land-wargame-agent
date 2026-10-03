"""Offline search for an E3b configuration (``t7-e3b-search-1``, ``docs/T7_E3B_SEARCH.md``): the episode rules.

Read-only and engine-free. A searched seat is a sequence of :class:`Decision` rows (one per decision of the seat, in
order), each holding the seat's own units as :class:`UnitState`, the first action ``baseline-v2`` gave each unit, the
enemy hexes and the judge records of the engine step that led to the decision. :func:`episodes` opens an episode at
every episode-opening concealment order of the candidate replay and :func:`classify` follows the unit from that order
(``k0``) to the first later ``baseline-v2`` command, the first disturbance or the end of the game (protocol section 4).
:func:`idle_runs` finds the D2 structural opportunities; :class:`Configuration`, :func:`rank_key` and
:func:`disposition` apply the feasibility rubric (section 8) and the decision rule (section 9). Nothing here decides an
action, reads an engine or imports a policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

TRANSITION = 75
MOVE, SHOOT = 1, 2
GROUND = (1, 2)
LONG_WAIT = 20
TIMERS = ("change_state_remain_time", "move_to_stop_remain_time", "weapon_unfold_time", "get_on_remain_time",
          "get_off_remain_time")

W, TI, OA, DT, CE = "W", "TI", "OA", "DT", "CE"
CLASSES = (W, TI, OA, DT, CE)
GAP, MISSING = "snapshot gap", "missing or malformed field"

IDENTIFIED = "E3B_CONFIGURATION_IDENTIFIED"
UNCERTAIN = "E3B_CONFIGURATION_UNCERTAIN"
NONE_FOUND = "NO_NATURAL_E3B_WITNESS_FOUND"
BLOCKED = "BLOCKED"


def _num(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


@dataclass(frozen=True)
class UnitState:
    """One own unit at one decision, as one channel shows it (``None`` where the field is absent)."""

    obj_id: int
    type: Any
    sub_type: Any
    hex: Any
    blood: Any
    on_board: Any
    path: Optional[Tuple[Any, ...]]
    stop: Any
    keep: Any
    flag_force_stop: Any
    timers: Tuple[Any, ...]
    speed: Any = None
    listed: Optional[FrozenSet[int]] = None  # listed action types (None: no valid_actions entry)

    @staticmethod
    def from_raw(unit: Mapping[str, Any], listed_types: Optional[Sequence[int]] = None) -> "UnitState":
        path = unit.get("move_path")
        return UnitState(unit.get("obj_id"), unit.get("type"), unit.get("sub_type"), unit.get("cur_hex"),
                         unit.get("blood"), unit.get("on_board"),
                         tuple(path) if isinstance(path, (list, tuple)) else None, unit.get("stop"), unit.get("keep"),
                         unit.get("flag_force_stop"), tuple(unit.get(t) for t in TIMERS), unit.get("speed"),
                         None if listed_types is None else frozenset(listed_types))

    def state_key(self) -> Tuple[Any, ...]:
        """The fields the two channels must agree on (listings excluded: the all-seeing view lists for every seat)."""
        return (self.type, self.sub_type, self.hex, self.blood, self.on_board, self.path, self.stop, self.keep,
                self.flag_force_stop, self.timers, self.speed)


@dataclass
class Decision:
    """One decision of the searched seat.

    ``attackers`` and ``targets``: unit ids named by the judge records of the engine step that LED to this decision
    (between the previous decision and this one). ``actions``: the first ``baseline-v2`` action per unit at this
    decision. ``enemy_hexes``: hexes holding an enemy unit (all-seeing state where captured, else the seat view).
    """

    k: int
    cur_step: int
    units: Dict[int, UnitState]
    actions: Dict[int, Mapping[str, Any]] = field(default_factory=dict)
    enemy_hexes: FrozenSet[Any] = frozenset()
    attackers: FrozenSet[Any] = frozenset()
    targets: FrozenSet[Any] = frozenset()


@dataclass
class Episode:
    unit: int
    k0: int
    s0: int
    cls: str = CE
    d: Optional[int] = None  # cur_step distance from s0 to the end event (k1, the disturbance or the last decision)
    k1: Optional[int] = None  # decision of the end event
    s1: Optional[int] = None  # cur_step of the later command (W, TI, OA only)
    later_type: Any = None
    later_action: Optional[Mapping[str, Any]] = None
    reason: Optional[str] = None  # the disturbance, for DT
    gaps: List[Tuple[int, str]] = field(default_factory=list)
    previous: Optional[str] = None  # label of the unit's previous episode (None: the unit's first order)

    @property
    def conditional(self) -> bool:
        return self.previous is not None

    @property
    def completed(self) -> bool:
        """The 75-step transition would have completed before the end event."""
        return self.d is not None and self.d >= TRANSITION

    def label(self) -> str:
        if self.cls in (DT, CE):
            return f"{self.cls} {'after' if self.completed else 'during'} the transition"
        if self.cls == OA:
            return f"OA type {self.later_type}"
        return self.cls


def state_violation(start: UnitState, now: Optional[UnitState], decision: Decision) -> Optional[str]:
    """Why the unit's state at ``decision`` breaks its continuity since ``start`` (``None`` when it does not)."""
    if now is None:
        return "unit gone"
    if any(v is None for v in (now.blood, now.hex, now.stop, now.keep)) or now.path is None:
        return MISSING
    if any(_num(t) is None for t in now.timers):
        return MISSING
    if now.on_board not in (0, None, False):
        return "boarded"
    if now.blood != start.blood:
        return "damaged"
    if now.hex != start.hex:
        return "moved"
    if now.path:
        return "move path"
    if now.stop != 1:
        return "not stopped"
    if now.keep != 0:
        return "suppressed"
    if now.flag_force_stop == 1:
        return "forced stop"
    if any(_num(t) != 0 for t in now.timers):
        return "transition"
    if now.hex in decision.enemy_hexes:
        return "enemy in hex"
    if now.obj_id in decision.attackers:
        return "fired"
    if now.obj_id in decision.targets:
        return "attacked"
    return None


def classify(decisions: Sequence[Decision], index0: int, unit: int, previous: Optional[str] = None) -> Episode:
    """The episode of ``unit`` opened by an order at ``decisions[index0]`` (section 4).

    Missing evidence (a snapshot gap, a missing or malformed field) never ends the episode: it is recorded in ``gaps``
    and the scan continues, so that an episode that would otherwise be a witness is downgraded to category B."""
    d0 = decisions[index0]
    start = d0.units.get(unit)
    if start is None:
        raise ValueError(f"unit {unit} is not an own unit at decision {d0.k}")
    if unit in d0.actions:
        raise ValueError(f"baseline-v2 acted on unit {unit} at its order decision {d0.k}")
    episode = Episode(unit, d0.k, d0.cur_step, previous=previous)
    if state_violation(start, start, d0) == MISSING:
        episode.gaps.append((d0.k, MISSING))
    prior = d0
    for decision in decisions[index0 + 1:]:
        if decision.cur_step != prior.cur_step + 1:
            episode.gaps.append((decision.k, GAP))
        prior = decision
        reason = state_violation(start, decision.units.get(unit), decision)
        if reason == MISSING:
            episode.gaps.append((decision.k, MISSING))
        elif reason is not None:
            episode.cls, episode.reason = DT, reason
            episode.k1, episode.d = decision.k, decision.cur_step - d0.cur_step
            return episode
        action = decision.actions.get(unit)
        if action is not None:
            episode.k1, episode.s1 = decision.k, decision.cur_step
            episode.d = decision.cur_step - d0.cur_step
            episode.later_type, episode.later_action = action.get("type"), action
            if action.get("type") in (MOVE, SHOOT):
                episode.cls = W if episode.d >= TRANSITION else TI
            else:
                episode.cls = OA
            return episode
    episode.k1 = decisions[-1].k
    episode.d = decisions[-1].cur_step - d0.cur_step
    return episode


def episodes(decisions: Sequence[Decision], orders: Mapping[int, Sequence[int]]) -> List[Episode]:
    """Every episode of every ordered unit: the first order opens one; a later order opens another only when it is
    issued after the unit's previous episode ended (at its later command or disturbance) and is then conditional on
    that episode. Orders inside an episode (the replay's 75-step repeats on a trajectory without concealment) are
    ignored; an episode that runs to the end of the game (CE) admits no successor."""
    index = {d.k: i for i, d in enumerate(decisions)}
    out: List[Episode] = []
    for unit in sorted(orders):
        boundary: Optional[int] = None  # decision at which the previous episode ended
        previous: Optional[Episode] = None
        for k in sorted(orders[unit]):
            if previous is not None and (previous.cls == CE or k <= boundary):
                continue
            episode = classify(decisions, index[k], unit, None if previous is None else previous.label())
            out.append(episode)
            previous, boundary = episode, episode.k1
    return out


@dataclass
class IdleRun:
    unit: int
    k1: int
    s1: int
    start_k: int
    length: int  # cur_step steps from the run's first decision to k1
    later_type: Any


def idle_runs(decisions: Sequence[Decision], orders: Mapping[int, Sequence[int]]) -> List[IdleRun]:
    """D2: every ``baseline-v2`` move or shot to an own ground unit preceded by at least 75 consecutive steps in which
    the unit was stationary, unsuppressed, without an action and undisturbed, while the candidate replay never ordered
    it in that run (``orders``: unit to the decisions ``k`` at which the replay ordered it, repeats included)."""
    runs: List[IdleRun] = []
    for i1, decision in enumerate(decisions):
        for unit, action in decision.actions.items():
            if action.get("type") not in (MOVE, SHOOT):
                continue
            here = decision.units.get(unit)
            if here is None or here.type not in GROUND or state_violation(here, here, decision) is not None:
                continue
            j = i1
            while j > 0:
                before = decisions[j - 1]
                if decisions[j].cur_step != before.cur_step + 1 or unit in before.actions:
                    break
                if state_violation(here, before.units.get(unit), before) is not None:
                    break
                j -= 1
            length = decision.cur_step - decisions[j].cur_step
            if length < TRANSITION:
                continue
            start_k = decisions[j].k
            if any(start_k <= k < decision.k for k in orders.get(unit, ())):
                continue
            runs.append(IdleRun(unit, decision.k, decision.cur_step, start_k, length, action.get("type")))
    return runs


def _key_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def listing_of(raw: Mapping[str, Any]) -> Dict[int, Dict[int, Any]]:
    """``valid_actions`` as unit id to action type to options (keys normalised to integers)."""
    out: Dict[int, Dict[int, Any]] = {}
    for unit_id, actions in (raw.get("valid_actions") or {}).items():
        uid = _key_int(unit_id)
        if uid is None or not isinstance(actions, Mapping):
            continue
        out[uid] = {t: options for key, options in actions.items() if (t := _key_int(key)) is not None}
    return out


def rows_from_raw(raw: Mapping[str, Any], faction: Any, with_listings: bool = True) -> Dict[int, UnitState]:
    """The faction's units in ``operators`` (a unit listed only in ``valid_actions`` is not a unit of the view)."""
    listed = listing_of(raw) if with_listings else {}
    out: Dict[int, UnitState] = {}
    for unit in raw.get("operators") or ():
        if not isinstance(unit, Mapping) or _key_int(unit.get("obj_id")) is None or isinstance(unit.get("obj_id"), str):
            continue
        if unit.get("color") != faction:
            continue
        uid = unit["obj_id"]
        types = sorted(listed[uid]) if with_listings and uid in listed else None
        out[uid] = UnitState.from_raw(unit, types)
    return out


def error_code(entry: Mapping[str, Any]) -> Any:
    error = entry.get("error")
    if not error:
        return None
    return error.get("code") if isinstance(error, Mapping) else error


def echoes(entry: Mapping[str, Any], action: Mapping[str, Any]) -> bool:
    """A feedback entry's message is this action: same actor, type, obj_id and identifying parameters."""
    message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
    for key in ("actor", "type", "obj_id"):
        if message.get(key) != action.get(key):
            return False
    for key in ("target_obj_id", "weapon_id", "target_state"):
        if key in action and message.get(key) != action.get(key):
            return False
    if "move_path" in action and list(message.get("move_path") or []) != list(action.get("move_path") or []):
        return False
    return True


def command_evidence(action: Mapping[str, Any], serialised: Sequence[Mapping[str, Any]],
                     feedback: Sequence[Mapping[str, Any]], judge_of_step: Sequence[Mapping[str, Any]],
                     next_state: Optional[UnitState], listed: Mapping[int, Any]) -> Dict[str, Any]:
    """Echo, execution and listing of a later command in the original game (section 4).

    ``serialised``: the same action as serialised after the step (the engine may rewrite it in place);
    ``feedback``: the fresh feedback entries of the step; ``judge_of_step``: its judge records; ``next_state``: the
    unit at the next decision; ``listed``: the unit's listing at the command's decision."""
    matching = [e for e in feedback if echoes(e, action) or any(echoes(e, s) for s in serialised)]
    codes = [error_code(e) for e in matching]
    executed: Optional[bool] = None
    unit = action.get("obj_id")
    if action.get("type") == SHOOT:
        executed = any(isinstance(r, Mapping) and r.get("att_obj_id") == unit for r in judge_of_step)
    elif next_state is not None:
        path = tuple(action.get("move_path") or ())
        later_path = next_state.path or ()
        executed = bool(path) and (next_state.hex == path[0]
                                   or (bool(later_path) and tuple(later_path) == path[len(path) - len(later_path):]))
    if action.get("type") == SHOOT:
        in_listing = any(isinstance(o, Mapping) and o.get("target_obj_id") == action.get("target_obj_id")
                         and o.get("weapon_id") == action.get("weapon_id") for o in listed.get(SHOOT) or ())
    else:
        in_listing = action.get("type") in listed
    return {"echoes": len(matching), "codes": codes, "accepted": len(matching) == 1 and codes == [None],
            "executed": executed, "listed": in_listing, "listed_types": sorted(listed)}


def long_wait(decisions: Sequence[Decision], until_step: int, limit: int = LONG_WAIT) -> bool:
    """A seat unit waiting more than ``limit`` consecutive decisions in front of a full hex (speed 0 with a move path)
    before ``until_step``."""
    runs: Dict[int, int] = {}
    for decision in decisions:
        if decision.cur_step >= until_step:
            break
        for unit, state in decision.units.items():
            waiting = bool(state.path) and _num(state.speed) == 0
            runs[unit] = runs.get(unit, 0) + 1 if waiting else 0
            if runs[unit] > limit:
                return True
    return False


# ----------------------------------------------------------------------------------------------
# Feasibility (section 8) and the decision rule (section 9)


@dataclass
class Configuration:
    """A W episode with the evidence the rubric reads."""

    dataset: str
    category: str  # "A", "B" or "C"
    episode: Episode
    accepted: Optional[bool]  # later command echoed exactly once without an error code
    executed: Optional[bool]
    first_judge_step: Optional[int]  # cur_step of the game's first judge record (None: no shot in the game)
    opponent_inert: bool
    earlier_first_orders: int  # other units first ordered before k0 in the seat
    earlier_seen_by_opponent: int  # of those, units the opposing seat lists between their order and s0
    first_ordered_before_k1: int  # other units first ordered before k1
    deterministic_configuration: bool  # earlier records show identical repetitions of this configuration
    long_wait_before_s1: bool
    notes: Dict[str, Any] = field(default_factory=dict)

    def f1(self) -> bool:
        return self.category == "A"

    def f2(self) -> bool:
        if self.episode.conditional:
            return False
        if self.first_judge_step is not None and self.first_judge_step < self.episode.s0:
            return False
        return self.opponent_inert or self.earlier_seen_by_opponent == 0

    def f3(self) -> bool:
        return bool(self.accepted) and bool(self.executed) and (self.episode.d or 0) >= TRANSITION

    def feasible(self) -> bool:
        return self.episode.cls == W and self.f1() and self.f2() and self.f3()


def rank_key(c: Configuration) -> Tuple[Any, ...]:
    """Lexicographic rank of section 8 (smaller is better)."""
    e = c.episode
    return (0 if c.deterministic_configuration else 1, 0 if c.earlier_first_orders == 0 else 1,
            c.first_ordered_before_k1, 1 if c.long_wait_before_s1 else 0, (e.d or 0) - TRANSITION, e.s1 or 0)


def disposition(configurations: Sequence[Configuration], crosscheck_agrees: bool, stopped: bool) -> str:
    """Section 9; ``configurations`` holds every W episode of categories A, B and C."""
    if stopped or not crosscheck_agrees:
        return BLOCKED
    if any(c.feasible() for c in configurations):
        return IDENTIFIED
    if any(c.episode.cls == W and c.category in ("A", "B", "C") for c in configurations):
        return UNCERTAIN
    return NONE_FOUND
