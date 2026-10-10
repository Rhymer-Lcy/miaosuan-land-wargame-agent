"""Documented and measured constants the integrated agent reads, and hex geometry.

Sources, each restated here so that the candidate's source set holds no analysis module:

* action types and fields: the SDK's ``docs/action_note.json`` and the public action documentation;
* hex time ``720 / basic_speed * cost`` per entered hex, a stacking limit of four own ground units per hex, the
  75-step stop, embark, disembark and state transitions (``docs/TACTICAL_FRONTIER.md`` engine facts; Sprint 22);
* indirect fire: a round lands 150 steps after the order and the hex then explodes for about 300 steps, judging
  every unit in it, own units included; orders were accepted at 15 to 65 hexes (Sprint 8 exploratory games);
* published direct-fire ranges by weapon id (the live rules snapshot read 2026-09-29, as tabulated in Sprint 5);
* listing facts measured in Sprint 34 on genuine full-step captures: occupation is listed during the post-arrival
  transition when no enemy ground unit is in the zone; embark is listed only for a settled infantry or unmanned
  ground vehicle sharing a hex with a settled carrier; disembark only for a settled carrier with passengers; only
  tanks list a shot while moving; artillery never lists movement.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Sequence, Tuple

MOVE, SHOOT, GET_ON, GET_OFF, OCCUPY, CHANGE_STATE = 1, 2, 3, 4, 5, 6
REMOVE_KEEP, INDIRECT, GUIDED, STOP, LOCK, UNFOLD, CANCEL_INDIRECT = 7, 8, 9, 10, 11, 12, 13
END_DEPLOYMENT = 333

INFANTRY, VEHICLE, AIRCRAFT = 1, 2, 3
GROUND = frozenset({INFANTRY, VEHICLE})
#: sub_type codes named in the SDK observation note.
TANK, IFV, SQUAD, ARTILLERY, UGV, UAV, HELICOPTER, LOITERING = 0, 1, 2, 3, 4, 5, 6, 7

STACK_LIMIT = 4
TRANSITION = 75
SECONDS_PER_HEX_AT_1KMH = 720.0
ARTILLERY_FLIGHT = 150
ARTILLERY_EXPLOSION = 300
ARTILLERY_MIN_RANGE, ARTILLERY_MAX_RANGE = 15, 65

#: Published direct-fire ranges in hexes by weapon id: (against personnel, against vehicles); None = not published.
WEAPON_RANGES: Mapping[int, Tuple[Optional[int], Optional[int]]] = {
    36: (10, 18), 37: (10, 15), 54: (10, 13), 4: (10, None), 56: (None, 10), 29: (3, 3), 43: (10, None),
    83: (10, 20), 74: (10, 10), 75: (5, 5), 76: (2, 2), 35: (None, 4), 71: (None, 10), 69: (None, 20),
    84: (None, 20), 73: (None, 20),
}


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number(value: Any, default: float = 0.0) -> float:
    return float(value) if is_number(value) else default


def hex_distance(a: int, b: int) -> int:
    """Hex distance between two four-digit hexes (``row * 100 + col``, odd rows shifted), via cube coordinates."""
    (r1, c1), (r2, c2) = divmod(a, 100), divmod(b, 100)
    q1, q2 = c1 - (r1 - (r1 & 1)) // 2, c2 - (r2 - (r2 & 1)) // 2
    return (abs(q1 - q2) + abs(r1 - r2) + abs((-q1 - r1) - (-q2 - r2))) // 2


def neighbours(hex_: int, rows: int = 100, cols: int = 100) -> Tuple[int, ...]:
    """The six geometric neighbours of a hex inside a ``rows`` x ``cols`` map, ascending."""
    r, c = divmod(hex_, 100)
    found = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == dc == 0:
                continue
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols and hex_distance(hex_, rr * 100 + cc) == 1:
                found.append(rr * 100 + cc)
    return tuple(sorted(found))


def zone(hex_: int, rows: int = 100, cols: int = 100) -> FrozenSet[int]:
    """An objective's occupation zone: its hex and the six neighbours."""
    return frozenset((hex_,) + neighbours(hex_, rows, cols))


def hex_time(basic_speed: Any, cost: Any) -> Optional[int]:
    """Steps to enter one hex, ``720 / basic_speed * cost`` rounded; ``None`` if unreadable."""
    if not (is_number(basic_speed) and is_number(cost) and basic_speed > 0 and cost > 0):
        return None
    return int(SECONDS_PER_HEX_AT_1KMH / basic_speed * cost + 0.5)


def weapon_range(weapon_ids: Iterable[Any], target_type: Any) -> Optional[int]:
    """The longest published range of the weapons against a target class, or ``None``."""
    column = 0 if target_type == INFANTRY else 1 if target_type in (VEHICLE, AIRCRAFT) else None
    if column is None:
        return None
    ranges = [WEAPON_RANGES[w][column] for w in weapon_ids or () if is_int(w) and w in WEAPON_RANGES]
    ranges = [r for r in ranges if r is not None]
    return max(ranges) if ranges else None


def max_weapon_range(weapon_ids: Iterable[Any]) -> int:
    """The longest published range of any weapon against any ground class (0 if none)."""
    best = 0
    for w in weapon_ids or ():
        if is_int(w) and w in WEAPON_RANGES:
            best = max([best] + [r for r in WEAPON_RANGES[w] if r is not None])
    return best


def canonical_sorted(items: Iterable[Tuple[Any, ...]]) -> Tuple[Tuple[Any, ...], ...]:
    """A tuple of tuples sorted by their ``repr``-stable natural order (ints and strings only)."""
    return tuple(sorted(items))


def as_dict(pairs: Sequence[Tuple[Any, Any]]) -> Dict[Any, Any]:
    return {k: v for k, v in pairs}
