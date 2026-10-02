"""T7 design study (``t7-design-1``): the candidate pool of ``docs/T7_DESIGN.md`` section 8, as trigger predicates.

Each predicate reads one seat observation (engine form), the frozen ``baseline-v2`` decision on it, the setup cost
graph and documented constants; none reads another seat's view or the all-seeing state. They return an activation
record or ``None``. They are offline research predicates, not a policy: nothing here emits an action to an engine.

Documented constants (published rules and references, read 2026-09-29):

* weapon id to name mapping and direct-fire ranges (hexes) against personnel and against vehicles; a weapon whose
  range for a target class is not published contributes nothing;
* observation distances (hexes): infantry, vehicles and helicopters observe infantry at 10 and vehicles at 25;
  unmanned aerial vehicles and loitering munitions observe ground units at 2;
* march at 90 km/h on the fastest road class, i.e. 8 s per 200 m hex at march cost 1 (the cost graph's march mode is
  defined relative to the mode's maximum speed); vehicle hex time ``(720 / basic_speed) * cost``;
* every state transition used here takes 75 s; A1's four transitions take 300 s.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, MoveMode
from ..decision.routing import Router
from .t7_audit import enemy_seen, has_path, integer, listings, number, operators, target_states

TRANSITION = 75
A1_OVERHEAD = 4 * TRANSITION
MARCH_SECONDS_PER_COST = 8.0
SECONDS_PER_KMH_HEX = 720.0
A3_MAX_HEXES = 2
CONCEAL, MARCH, CHARGE1 = 4, 1, 2
INFANTRY, VEHICLE, AIRCRAFT = 1, 2, 3
ARTILLERY = 3
POOL = ("A1", "A2", "A3", "B1", "B2", "C0")

#: Published direct-fire ranges in hexes by weapon id: (against personnel, against vehicles); None = not published.
WEAPON_RANGES: Mapping[int, Tuple[Optional[int], Optional[int]]] = {
    36: (10, 18),   # large direct-fire gun
    37: (10, 15),   # medium direct-fire gun
    54: (10, 13),   # small direct-fire gun
    4: (10, None),  # rapid-fire gun (ground)
    56: (None, 10),  # rapid-fire gun
    29: (3, 3),     # infantry light weapons
    43: (10, None),  # vehicle light weapons
    83: (10, 20),   # medium missile (standard)
    74: (10, 10),   # medium missile (portable)
    75: (5, 5),     # small missile
    76: (2, 2),     # loitering munition
    35: (None, 4),  # rocket launcher
    71: (None, 10),  # portable missile
    69: (None, 20),  # vehicle-mounted missile
    84: (None, 20),  # gun-launched missile
    73: (None, 20),  # heavy missile
}
#: Unmanned aerial vehicle and loitering munition archetypes (type 3, sub_type 5 and 7).
SHORT_SIGHTED = frozenset({(AIRCRAFT, 5), (AIRCRAFT, 7)})


def hex_distance(a: int, b: int) -> int:
    """Hex distance between two four-digit hexes (row * 100 + col, odd rows shifted), via cube coordinates."""
    (r1, c1), (r2, c2) = divmod(a, 100), divmod(b, 100)
    q1, q2 = c1 - (r1 - (r1 & 1)) // 2, c2 - (r2 - (r2 & 1)) // 2
    return (abs(q1 - q2) + abs(r1 - r2) + abs((-q1 - r1) - (-q2 - r2))) // 2


def weapon_range(weapon_ids: Sequence[Any], target_type: Any) -> Optional[int]:
    """The longest published range of the weapons against the target class, or ``None``."""
    column = 0 if target_type == INFANTRY else 1 if target_type == VEHICLE else None
    if column is None:
        return None
    ranges = [WEAPON_RANGES[w][column] for w in weapon_ids or () if integer(w) is not None and w in WEAPON_RANGES]
    ranges = [r for r in ranges if r is not None]
    return max(ranges) if ranges else None


def observation_distance(observer: Mapping[str, Any], target_type: Any) -> Optional[int]:
    """The published observation distance of an observer against a ground target class (no terrain, no concealment)."""
    if (observer.get("type"), observer.get("sub_type")) in SHORT_SIGHTED:
        return 2
    if observer.get("type") not in (INFANTRY, VEHICLE, AIRCRAFT):
        return None
    return {INFANTRY: 10, VEHICLE: 25}.get(target_type)


def cities(raw: Mapping[str, Any]) -> FrozenSet[int]:
    return frozenset(c.get("coord") for c in raw.get("cities") or () if isinstance(c, Mapping)
                     and integer(c.get("coord")) is not None)


def roadblocks(raw: Mapping[str, Any]) -> FrozenSet[int]:
    marks = (raw.get("landmarks") or {}).get("roadblocks") or ()
    return frozenset(h for h in marks if integer(h) is not None)


def path_seconds(costs: MoveCosts, mode: MoveMode, start: int, path: Sequence[int], per_cost: float) -> Optional[float]:
    """Documented time along a path: ``per_cost`` seconds per unit of entry cost; ``None`` if an edge is missing."""
    total, here = 0.0, start
    for hex_ in path:
        edges = costs.neighbours(mode, here)
        if hex_ not in edges:
            return None
        total += per_cost * edges[hex_]
        here = hex_
    return total


def in_transition(unit: Mapping[str, Any]) -> bool:
    names = ("change_state_remain_time", "move_to_stop_remain_time", "weapon_unfold_time", "get_on_remain_time",
             "get_off_remain_time")
    return any((number(unit.get(n)) or 0) > 0 for n in names)


@dataclass
class SeatMemory:
    """A2's only memory: the step at which the candidate last ordered each unit to change state."""

    last_order: Dict[int, int] = field(default_factory=dict)


def v2_by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[int, Mapping[str, Any]]:
    return {a["obj_id"]: a for a in actions if integer(a.get("obj_id")) is not None}


def a1(unit: Mapping[str, Any], unit_actions: Mapping[int, Any], v2: Optional[Mapping[str, Any]],
       raw: Mapping[str, Any], faction: int, costs: MoveCosts, router: Router) -> Optional[Dict[str, Any]]:
    if unit.get("type") != VEHICLE or unit.get("sub_type") == ARTILLERY:
        return None
    if v2 is None or v2.get("type") != 1 or not v2.get("move_path"):
        return None
    if enemy_seen(raw, faction) or unit.get("passenger_ids"):
        return None
    speed = number(unit.get("basic_speed"))
    start = integer(unit.get("cur_hex"))
    if not speed or start is None:
        return None
    path = [int(h) for h in v2["move_path"]]
    t0 = path_seconds(costs, MoveMode.VEHICLE, start, path, SECONDS_PER_KMH_HEX / speed)
    march = router.shortest_paths(start, MoveMode.VEHICLE_MARCH, roadblocks(raw))
    destination = path[-1]
    if t0 is None or destination not in march.cost or destination == start:
        return None
    t1 = MARCH_SECONDS_PER_COST * march.cost[destination]
    saving = t0 - (t1 + A1_OVERHEAD)
    if saving <= 0:
        return None
    states, _ = target_states(unit_actions.get(6))
    return {"t0": t0, "t1": t1, "saving": saving, "hexes": len(path), "lock_listed": 11 in unit_actions,
            "march_option_listed": MARCH in states}


def a2(unit: Mapping[str, Any], unit_actions: Mapping[int, Any], v2: Optional[Mapping[str, Any]], seen: bool,
       cur_step: int, memory: SeatMemory) -> Optional[Dict[str, Any]]:
    if unit.get("type") not in (INFANTRY, VEHICLE):
        return None
    states, _ = target_states(unit_actions.get(6))
    if CONCEAL not in states or v2 is not None or seen:
        return None
    if unit.get("move_state") == CONCEAL or number(unit.get("change_state_remain_time")) != 0 or in_transition(unit):
        return None
    if unit.get("stop") != 1 or has_path(unit) is not False or number(unit.get("keep")) != 0:
        return None
    last = memory.last_order.get(unit["obj_id"])
    if last is not None and cur_step - last < TRANSITION:
        return None
    memory.last_order[unit["obj_id"]] = cur_step
    return {"repeat": last is not None}


def a3(unit: Mapping[str, Any], unit_actions: Mapping[int, Any], v2: Optional[Mapping[str, Any]],
       raw: Mapping[str, Any], faction: int) -> Optional[Dict[str, Any]]:
    if unit.get("type") != INFANTRY:
        return None
    states, _ = target_states(unit_actions.get(6))
    if CHARGE1 not in states or v2 is None or v2.get("type") != 1:
        return None
    path = list(v2.get("move_path") or ())
    if not path or len(path) > A3_MAX_HEXES or path[-1] not in cities(raw):
        return None
    if unit.get("tire") != 0 or enemy_seen(raw, faction):
        return None
    return {"hexes": len(path)}


def moving(unit: Mapping[str, Any], unit_actions: Mapping[int, Any]) -> bool:
    """A traversing unit with a stop listed (never one waiting in front of a full hex: speed 0 with a path)."""
    return (unit.get("type") in (INFANTRY, VEHICLE) and has_path(unit) is True and (number(unit.get("speed")) or 0) > 0
            and 10 in unit_actions)


def b1(unit: Mapping[str, Any], unit_actions: Mapping[int, Any], raw: Mapping[str, Any],
       faction: int) -> Optional[Dict[str, Any]]:
    if unit.get("A1") != 0 or not moving(unit, unit_actions):
        return None
    here = integer(unit.get("cur_hex"))
    if here is None:
        return None
    best = None
    for enemy in operators(raw).values():
        if enemy.get("color") == faction or enemy.get("type") not in (INFANTRY, VEHICLE):
            continue
        reach = weapon_range(unit.get("carry_weapon_ids"), enemy.get("type"))
        there = integer(enemy.get("cur_hex"))
        if reach is None or there is None:
            continue
        d = hex_distance(here, there)
        if d <= reach and (best is None or d < best[0]):
            best = (d, enemy["obj_id"], reach)
    if best is None:
        return None
    return {"distance": best[0], "enemy": best[1], "range": best[2]}


def b2(unit: Mapping[str, Any], unit_actions: Mapping[int, Any], raw: Mapping[str, Any],
       faction: int) -> Optional[Dict[str, Any]]:
    if not moving(unit, unit_actions):
        return None
    here, nxt = integer(unit.get("cur_hex")), integer((unit.get("move_path") or [None])[0])
    if here is None or nxt is None:
        return None
    for enemy in operators(raw).values():
        if enemy.get("color") == faction:
            continue
        reach = observation_distance(enemy, unit.get("type"))
        there = integer(enemy.get("cur_hex"))
        if reach is None or there is None:
            continue
        if hex_distance(there, nxt) <= reach < hex_distance(there, here):
            return {"next": nxt, "enemy": enemy["obj_id"]}
    return None


def evaluate(raw: Mapping[str, Any], faction: int, v2_actions: Sequence[Mapping[str, Any]], costs: MoveCosts,
             router: Router, memory: SeatMemory) -> List[Tuple[str, int, Dict[str, Any]]]:
    """Every activation of the pool on one play-stage decision: (candidate, unit id, record). C0 never fires."""
    if (raw.get("time") or {}).get("stage") != 2:
        return []
    cur_step = (raw.get("time") or {}).get("cur_step")
    listed = listings(raw)
    seen = enemy_seen(raw, faction)
    v2 = v2_by_unit(v2_actions)
    out: List[Tuple[str, int, Dict[str, Any]]] = []
    for unit_id, unit in sorted(operators(raw).items()):
        if unit.get("color") != faction:
            continue
        unit_actions = listed.get(unit_id, {})
        record = a1(unit, unit_actions, v2.get(unit_id), raw, faction, costs, router)
        if record:
            out.append(("A1", unit_id, record))
        record = a2(unit, unit_actions, v2.get(unit_id), seen, cur_step, memory)
        if record:
            out.append(("A2", unit_id, record))
        record = a3(unit, unit_actions, v2.get(unit_id), raw, faction)
        if record:
            out.append(("A3", unit_id, record))
        if v2.get(unit_id) is None:
            record = b1(unit, unit_actions, raw, faction)
            if record:
                out.append(("B1", unit_id, record))
            record = b2(unit, unit_actions, raw, faction)
            if record:
                out.append(("B2", unit_id, record))
    return out
