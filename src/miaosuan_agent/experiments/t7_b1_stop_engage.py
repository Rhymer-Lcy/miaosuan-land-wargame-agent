"""EXPLORATORY mechanism candidate ``t7-b1-stop-engage-1`` (Sprint 32, ``docs/SPRINT32_T7_B1_PREFLIGHT.md``).

Exploratory track: not a baseline, not eligible for promotion and never packaged. No engine use is authorized for it;
any engine session needs the owner's explicit approval of a registered mechanism check first.

``baseline-v2`` decides first, on the seat's own current observation and memory, unchanged
(:mod:`.exploratory_addon`). The add-on then appends at most one stop order (action 10) per own unit, for units that
``baseline-v2`` leaves without an action, and changes nothing else: no ``baseline-v2`` action is removed, replaced or
reordered, and no other action type is constructed.

**Trigger.** Own units are checked in ascending ``obj_id``; the first failing level is recorded and the unit is left
alone. A unit gets a stop only when every level passes:

* ``A_ground_controllable``: an operator of the seat's colour, of type 1 (infantry) or 2 (vehicle), listed among the
  seat's own operators in ``role_and_grouping_info``.
* ``B_no_move_and_fire``: the move-and-fire field ``A1`` is the integer 0 and ``carry_weapon_ids`` is a list of integers
  holding neither tank main gun (weapon ids 36 and 37, the large and medium direct-fire guns that the published rules
  allow to fire on the move). A unit that may fire without stopping is never stopped.
* ``C_traversing``: a non-empty ``move_path`` of integer hexes, ``speed`` a number above 0 (``speed`` 0 with a path is
  a unit waiting in front of a full hex, the case in which a stop is deferred indefinitely), ``cur_pos`` a number in
  ``[0, 1)`` and an integer ``cur_hex``.
* ``D_stop_listed``: ``valid_actions`` lists action 10 for the unit with the value ``None`` (the parameterless form in
  which engine 4.1.0 lists it); any other listing is ambiguous and fails closed. The emitted order is exactly the
  documented key set ``actor``, ``obj_id``, ``type``.
* ``E_no_other_state``: every field of :data:`ZERO_FIELDS` present as a number equal to 0 (no stop transition, no
  deferred stop, no state change, no embarking or disembarking, no weapon lock or unfold under way, not suppressed,
  normal movement state, not aboard) and ``weapon_unfold_state`` equal to 1 (weapons unfolded).
* ``F_route_continues``: the path has at least two hexes, so that the stop drops movement that would otherwise happen.
* ``G_no_baseline_action``: ``baseline-v2`` emits no action for the unit at this decision.
* ``H_not_stopped_before``: the candidate has not ordered this unit to stop earlier in the game (its memory). At most
  one stop per unit per game: no repeated stop to a pending transition, no stop-move oscillation.
* ``I_target_in_range``: an enemy ground unit (type 1 or 2, another colour, an operator of the seat's view) whose id is
  in the unit's own ``see_enemy_bop_ids`` lies within the published direct-fire range of one of the unit's weapons
  against its class, measured from the first hex of the path (where the documented stop takes effect).
* ``J_next_hex_room``: the first hex of the path holds no more than :data:`ROOM_OTHERS` own ground units other than
  this one when counting every own ground unit standing on it, every own ground unit whose ``move_path`` contains it
  and every unit that ``baseline-v2`` orders at this decision onto a route containing it. With the unit itself the hex
  can then hold at most three, below the stacking limit of four: the unit cannot be left waiting in front of a full
  hex by any movement already planned, and a stopped unit leaves room for one unit passing through.
* ``K_time_left``: ``cur_step + hex_steps + 75 + END_MARGIN <= max_step``, where ``hex_steps`` is the number of steps
  needed to complete the current hex, ``ceil((1 - cur_pos) / speed)`` (``speed`` is in hexes per step), so that the
  documented 75-step transition ends with time left to fire.

**Memory.** ``baseline-v2``'s memory plus, per unit stopped by the candidate, the ``cur_step`` of the decision (sorted
integer pairs); empty at the start of a game. A malformed memory or observation raises, so the add-on wrapper plays
``baseline-v2``'s decision and records the error, never a guess.

Nothing reads another seat's view, the all-seeing state, the clock, randomness or any outcome.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, hex_distance

CANDIDATE_ID = "t7-b1-stop-engage-1"
ADDON_NAME = "t7_b1_stop_engage"
STATUS = "EXPLORATORY MECHANISM CANDIDATE - NOT ELIGIBLE FOR PROMOTION - NO ENGINE USE AUTHORIZED"
STOP = 10
MOVE = 1
GROUND = (1, 2)
INFANTRY, VEHICLE = 1, 2
PLAY_STAGE = 2
#: The documented duration of the move-to-stop transition, in steps.
TRANSITION = 75
#: Steps kept free after the transition: two steps of timing tolerance and one decision in which to fire.
END_MARGIN = 3
#: The stacking limit of own ground units per hex.
STACK_LIMIT = 4
#: At most this many other own ground units may stand on, or be routed through, the hex where the stop takes effect.
ROOM_OTHERS = 2
#: Tank main guns: the large and medium direct-fire guns, which fire on the move under the published rules.
TANK_GUNS = frozenset({36, 37})
#: Fields that must be present as numbers equal to 0.
ZERO_FIELDS = ("stop", "move_to_stop_remain_time", "flag_force_stop", "change_state_remain_time",
               "get_on_remain_time", "get_off_remain_time", "weapon_unfold_time", "keep", "move_state", "on_board")
#: Trigger levels, in evaluation order; the first failing level is recorded.
LEVELS = ("A_ground_controllable", "B_no_move_and_fire", "C_traversing", "D_stop_listed", "E_no_other_state",
          "F_route_continues", "G_no_baseline_action", "H_not_stopped_before", "I_target_in_range",
          "J_next_hex_room", "K_time_left")
TRIGGER = "stop"

#: Published direct-fire ranges in hexes by weapon id: (against personnel, against vehicles); ``None`` = not published.
#: The same table as the T7 design study's (``evaluation/t7_candidates.py``), repeated here so that the candidate's
#: source set does not include an analysis module.
WEAPON_RANGES: Mapping[int, Tuple[Optional[int], Optional[int]]] = {
    36: (10, 18), 37: (10, 15), 54: (10, 13), 4: (10, None), 56: (None, 10), 29: (3, 3), 43: (10, None),
    83: (10, 20), 74: (10, 10), 75: (5, 5), 76: (2, 2), 35: (None, 4), 71: (None, 10), 69: (None, 20),
    84: (None, 20), 73: (None, 20),
}


def as_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def weapon_range(weapon_ids: Sequence[int], target_type: Any) -> Optional[int]:
    """The longest published range of the weapons against the target class (1 infantry, 2 vehicle), or ``None``."""
    column = 0 if target_type == INFANTRY else 1 if target_type == VEHICLE else None
    if column is None:
        return None
    ranges = [WEAPON_RANGES[w][column] for w in weapon_ids if w in WEAPON_RANGES]
    ranges = [r for r in ranges if r is not None]
    return max(ranges) if ranges else None


def hex_steps(unit: Mapping[str, Any]) -> int:
    """Steps to complete the current hex at the current speed: ``ceil((1 - cur_pos) / speed)``, rounded to six
    decimals first so that a quotient such as 0.95 / 0.05 is not pushed above an integer by binary arithmetic."""
    return int(math.ceil(round((1.0 - unit["cur_pos"]) / unit["speed"], 6)))


@dataclass(frozen=True)
class UnitCheck:
    """One own unit at one play decision (private: ids and hexes)."""

    unit: int
    level: str  # TRIGGER or the first failing level of LEVELS
    detail: str = ""
    target: Optional[int] = None
    distance: Optional[int] = None
    reach: Optional[int] = None
    next_hex: Optional[int] = None
    others: Optional[int] = None
    steps: Optional[int] = None


@dataclass(frozen=True)
class StopResult:
    actions: Tuple[Mapping[str, Any], ...]
    stops: Tuple[int, ...]
    checks: Tuple[UnitCheck, ...]
    play: bool
    cur_step: Any
    memory: Tuple[Tuple[int, int], ...]


def read_memory(memory: Iterable[Any]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for pair in memory:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or as_int(pair[0]) is None or as_int(pair[1]) is None:
            raise ValueError("a memory entry is not a pair of integers")
        if pair[0] in out:
            raise ValueError("a unit appears twice in the memory")
        out[pair[0]] = pair[1]
    return out


def seat_units(raw: Mapping[str, Any], seat: int) -> Optional[frozenset]:
    """The ids the seat's ``role_and_grouping_info`` entry lists (keys may be ints or digit strings), or ``None``."""
    info = raw.get("role_and_grouping_info")
    if not isinstance(info, Mapping):
        return None
    entry = info.get(seat, info.get(str(seat)))
    if not isinstance(entry, Mapping) or not isinstance(entry.get("operators"), (list, tuple)):
        return None
    ids = [as_int(v) for v in entry["operators"]]
    return None if any(v is None for v in ids) else frozenset(ids)


def unit_listing(raw: Mapping[str, Any], unit: int) -> Optional[Mapping[Any, Any]]:
    listed = raw.get("valid_actions")
    if not isinstance(listed, Mapping):
        return None
    per = listed.get(unit, listed.get(str(unit)))
    return per if isinstance(per, Mapping) else None


def stop_listed(per: Optional[Mapping[Any, Any]]) -> Optional[bool]:
    """``True`` when action 10 is listed in its parameterless form, ``False`` when it is not listed, ``None`` when it
    is listed in any other form (ambiguous)."""
    if per is None:
        return False
    keys = [k for k in per if k == STOP or k == str(STOP)]
    if not keys:
        return False
    if len(keys) != 1 or per[keys[0]] is not None:
        return None
    return True


def check_unit(u: Mapping[str, Any], raw: Mapping[str, Any], faction: int, controlled: Optional[frozenset],
               base_units: frozenset, stopped: Mapping[int, int], enemies: Sequence[Mapping[str, Any]],
               own_ground: Sequence[Mapping[str, Any]], v2_routes: Sequence[Tuple[int, Sequence[Any]]],
               cur_step: int, max_step: int) -> UnitCheck:
    uid = u["obj_id"]
    if u.get("type") not in GROUND or controlled is None or uid not in controlled:
        return UnitCheck(uid, LEVELS[0])
    weapons = u.get("carry_weapon_ids")
    if as_int(u.get("A1")) != 0 or not isinstance(weapons, (list, tuple)) or any(as_int(w) is None for w in weapons) \
            or TANK_GUNS & set(weapons):
        return UnitCheck(uid, LEVELS[1])
    path = u.get("move_path")
    if not isinstance(path, (list, tuple)) or not path:
        return UnitCheck(uid, LEVELS[2], "no path")
    if any(as_int(h) is None for h in path) or as_int(u.get("cur_hex")) is None:
        return UnitCheck(uid, LEVELS[2], "unreadable hex")
    if not is_number(u.get("speed")):
        return UnitCheck(uid, LEVELS[2], "unreadable speed")
    if u["speed"] <= 0:
        return UnitCheck(uid, LEVELS[2], "waiting")
    if not is_number(u.get("cur_pos")) or not 0 <= u["cur_pos"] < 1:
        return UnitCheck(uid, LEVELS[2], "unreadable progress")
    listed = stop_listed(unit_listing(raw, uid))
    if listed is not True:
        return UnitCheck(uid, LEVELS[3], "ambiguous listing" if listed is None else "not listed")
    if not all(is_number(u.get(name)) and u.get(name) == 0 for name in ZERO_FIELDS) \
            or not (is_number(u.get("weapon_unfold_state")) and u.get("weapon_unfold_state") == 1):
        return UnitCheck(uid, LEVELS[4])
    if len(path) < 2:
        return UnitCheck(uid, LEVELS[5])
    if uid in base_units:
        return UnitCheck(uid, LEVELS[6])
    if uid in stopped:
        return UnitCheck(uid, LEVELS[7])
    nxt = path[0]
    seen = u.get("see_enemy_bop_ids")
    if not isinstance(seen, (list, tuple)):
        return UnitCheck(uid, LEVELS[8], "unreadable visibility")
    seen_ids = {as_int(v) for v in seen}
    best: Optional[Tuple[int, int, int]] = None
    for e in enemies:
        if e["obj_id"] not in seen_ids:
            continue
        reach = weapon_range(weapons, e.get("type"))
        there = as_int(e.get("cur_hex"))
        if reach is None or there is None:
            continue
        d = hex_distance(nxt, there)
        if d <= reach and (best is None or (d, e["obj_id"]) < (best[0], best[1])):
            best = (d, e["obj_id"], reach)
    if best is None:
        return UnitCheck(uid, LEVELS[8], next_hex=nxt)
    others = set()
    for o in own_ground:
        if o["obj_id"] == uid:
            continue
        route = o.get("move_path")
        if o.get("cur_hex") == nxt or (isinstance(route, (list, tuple)) and nxt in route):
            others.add(o["obj_id"])
    for unit, route in v2_routes:
        if unit != uid and nxt in route:
            others.add(unit)
    if len(others) > ROOM_OTHERS:
        return UnitCheck(uid, LEVELS[9], target=best[1], distance=best[0], reach=best[2], next_hex=nxt,
                         others=len(others))
    steps = hex_steps(u)
    if cur_step + steps + TRANSITION + END_MARGIN > max_step:
        return UnitCheck(uid, LEVELS[10], target=best[1], distance=best[0], reach=best[2], next_hex=nxt,
                         others=len(others), steps=steps)
    return UnitCheck(uid, TRIGGER, target=best[1], distance=best[0], reach=best[2], next_hex=nxt, others=len(others),
                     steps=steps)


def decide(raw: Mapping[str, Any], seat: int, faction: int, base_actions: Sequence[Mapping[str, Any]],
           memory: Iterable[Any]) -> StopResult:
    """One decision of the rule on the seat's own observation, ``baseline-v2``'s actions and the candidate's memory."""
    base = tuple(base_actions)
    stopped = read_memory(memory)
    kept = tuple(sorted(stopped.items()))
    time_info = raw.get("time") if isinstance(raw.get("time"), Mapping) else {}
    cur_step, stage, max_step = time_info.get("cur_step"), time_info.get("stage"), time_info.get("max_step")
    if stage != PLAY_STAGE:
        return StopResult(base, (), (), False, cur_step, kept)
    if as_int(cur_step) is None or as_int(max_step) is None:
        raise ValueError("the observation's time carries no integer cur_step and max_step")
    operators = raw.get("operators")
    if not isinstance(operators, (list, tuple)) or any(not isinstance(u, Mapping) or as_int(u.get("obj_id")) is None
                                                       for u in operators):
        raise ValueError("the observation carries no readable operators list")
    base_units = frozenset(as_int(a.get("obj_id")) for a in base if as_int(a.get("obj_id")) is not None)
    v2_routes = [(a["obj_id"], tuple(a.get("move_path") or ())) for a in base
                 if a.get("type") == MOVE and as_int(a.get("obj_id")) is not None]
    own = [u for u in operators if u.get("color") == faction]
    own_ground = [u for u in own if u.get("type") in GROUND]
    enemies = [u for u in operators if u.get("color") != faction and u.get("type") in GROUND]
    controlled = seat_units(raw, seat)
    checks = tuple(check_unit(u, raw, faction, controlled, base_units, stopped, enemies, own_ground, v2_routes,
                              cur_step, max_step) for u in sorted(own, key=lambda u: u["obj_id"]))
    stops = tuple(c.unit for c in checks if c.level == TRIGGER)
    added = tuple({"actor": seat, "obj_id": unit, "type": STOP} for unit in stops)
    new_memory = dict(stopped)
    new_memory.update({unit: cur_step for unit in stops})
    return StopResult(base + added, stops, checks, True, cur_step, tuple(sorted(new_memory.items())))


def change_records(result: StopResult) -> Tuple[Dict[str, Any], ...]:
    """One change record per added stop (private: unit ids and hexes)."""
    return tuple({"kind": "added_stop", "obj_id": c.unit, "target": c.target, "distance": c.distance,
                  "range": c.reach, "next_hex": c.next_hex, "others": c.others, "hex_steps": c.steps,
                  "step": result.cur_step} for c in result.checks if c.level == TRIGGER)


def skip_counts(result: StopResult) -> Tuple[Tuple[str, int], ...]:
    counts: collections.Counter = collections.Counter()
    if not result.play:
        counts["decision not_play_stage"] += 1
    for c in result.checks:
        counts[f"unit {c.level}"] += 1
    return tuple(sorted(counts.items()))


def own_check(result: StopResult, raw: Mapping[str, Any], seat: int, base: Sequence[Mapping[str, Any]]) -> None:
    """The candidate's own check of its edit (action 10 is not in the project gate's catalogue): ``baseline-v2``'s
    actions come first, unchanged and in order; every added action is a parameterless stop listed for its unit, with
    exactly the documented key set; no unit receives two actions."""
    actions = list(result.actions)
    if [dict(a) for a in actions[:len(base)]] != [dict(a) for a in base]:
        raise ValueError("a baseline-v2 action was changed")
    for action in actions[len(base):]:
        if set(action) != {"actor", "obj_id", "type"} or action["type"] != STOP or action["actor"] != seat:
            raise ValueError("an added action is not a parameterless stop of this seat")
        if stop_listed(unit_listing(raw, action["obj_id"])) is not True:
            raise ValueError("an added stop is not listed for its unit")
    ids = [as_int(a.get("obj_id")) for a in actions if as_int(a.get("obj_id")) is not None]
    if len(ids) != len(set(ids)):
        raise ValueError("a unit receives two actions")


class StopEngageAddon(Addon):
    name = ADDON_NAME

    def apply(self, observation: Any, seat: int, faction: int, base: Any,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        raw = observation.fields
        result = decide(raw, seat, faction, tuple(base.actions), memory)
        own_check(result, raw, seat, tuple(base.actions))
        return AddonResult(result.actions, change_records(result), skip_counts(result), result.memory)


class StopEngagePolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = StopEngageAddon


class StopEngageAgent(AddonAgent):
    policy_class = StopEngagePolicy
