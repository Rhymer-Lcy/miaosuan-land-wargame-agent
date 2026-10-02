"""The documented observation model of engine 4.1.0, for the T7 mechanism probe's E4 analysis (analysis only).

Nothing here is a policy input: it reads the all-seeing state or both seats' own views and the setup map data, and
predicts which enemy ground units a seat's view lists. Published rules (observation rules of the platform's
published rulebook, snapshot of 2026-09-29):

* distances in hexes, with line of sight and no terrain cover: infantry, vehicle and helicopter observers see
  infantry at 10 and vehicles at 25; unmanned aerial vehicles and loitering munitions see ground units at 2;
* a unit in concealment is observed at half the distance; concealment does not help a vehicle whose elevation is
  lower than its observer's;
* a unit in a forest or town hex with line of sight is observed at half the distance;
* line of sight comes from the setup table (``see``): mode 0 (ground to ground) for ground observers and mode 2 (low
  air to ground) for aerial observers.

The model without concealment was calibrated before the probe's registration on the replay corpus H0 (no unit ever
concealed): see ``scripts/t7_probe_analysis.py calibrate``. What is not documented stays explicit: whether the
terrain and concealment halvings stack, whether an aerial observer counts as higher than a concealed vehicle, and how a
half distance of 12.5 hexes is rounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

INFANTRY, VEHICLE, AIRCRAFT = 1, 2, 3
GROUND = (INFANTRY, VEHICLE)
SHORT_SIGHTED = frozenset({5, 7})  # aircraft sub_types: unmanned aerial vehicle, loitering munition
COVER = frozenset({1, 2})  # forest, town
CONCEAL = 4
GROUND_MODE, AIR_MODE = 0, 2
FULL = {INFANTRY: 10.0, VEHICLE: 25.0}
SHORT = 2.0

#: Pair bands of a concealed target (see :func:`band`).
INSIDE = "within the concealed distance"
BETWEEN = "between the concealed and the normal distance"
BOUNDARY = "on the rounding boundary of a half distance"
OUTSIDE = "beyond the normal distance"
NO_LOS = "no line of sight"


def hex_distance(a: int, b: int) -> int:
    """Hex distance between two four-digit hexes (row * 100 + col, odd rows shifted), via cube coordinates."""
    (r1, c1), (r2, c2) = divmod(a, 100), divmod(b, 100)
    q1, q2 = c1 - (r1 - (r1 & 1)) // 2, c2 - (r2 - (r2 & 1)) // 2
    return (abs(q1 - q2) + abs(r1 - r2) + abs((-q1 - r1) - (-q2 - r2))) // 2


class MapData:
    """Elevation, terrain condition and line of sight of one map (setup data only)."""

    def __init__(self, basic: Mapping[str, Any], see: Any) -> None:
        rows = basic["map_data"]
        self.elev: Dict[int, int] = {}
        self.cond: Dict[int, int] = {}
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                self.elev[r * 100 + c] = cell["elev"]
                self.cond[r * 100 + c] = cell["cond"]
        self.see = see

    def los(self, mode: int, a: int, b: int) -> bool:
        r1, c1 = divmod(a, 100)
        r2, c2 = divmod(b, 100)
        return bool(self.see[mode][r1, c1, r2, c2])

    def covered(self, hex_: int) -> bool:
        return self.cond.get(hex_) in COVER


def is_aerial(unit: Mapping[str, Any]) -> bool:
    return unit.get("type") == AIRCRAFT


def normal_distance(observer: Mapping[str, Any], target: Mapping[str, Any]) -> Optional[float]:
    """The published distance of an observer against a ground target, without terrain or concealment."""
    if target.get("type") not in GROUND:
        return None
    if is_aerial(observer) and observer.get("sub_type") in SHORT_SIGHTED:
        return SHORT
    if observer.get("type") not in (INFANTRY, VEHICLE, AIRCRAFT):
        return None
    return FULL[target["type"]]


def sees_unconcealed(m: MapData, observer: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    """Whether the documented model lets ``observer`` see an unconcealed ground ``target`` (terrain halving applied)."""
    full = normal_distance(observer, target)
    if full is None:
        return False
    o, x = observer["cur_hex"], target["cur_hex"]
    if not m.los(AIR_MODE if is_aerial(observer) else GROUND_MODE, o, x):
        return False
    reach = full / 2 if m.covered(x) else full
    return hex_distance(o, x) <= reach


@dataclass(frozen=True)
class Pair:
    """One observer against one concealed target at one step: the facts and the band."""

    observer: int
    aerial: bool
    distance: int
    los: bool
    normal: Optional[float]
    band: str
    cover: bool
    lower_vehicle: Optional[bool]  # target vehicle lower than the observer (None: aerial observer or infantry)


def band(m: MapData, observer: Mapping[str, Any], target: Mapping[str, Any]) -> Pair:
    """Classify one observer against one concealed ground target (no terrain, no exception applied here)."""
    full = normal_distance(observer, target)
    o, x = observer["cur_hex"], target["cur_hex"]
    aerial = is_aerial(observer)
    d = hex_distance(o, x)
    sight = m.los(AIR_MODE if aerial else GROUND_MODE, o, x)
    lower = None
    if target.get("type") == VEHICLE and not aerial:
        lower = m.elev.get(x, 0) < m.elev.get(o, 0)
    if full is None:
        label = OUTSIDE
    elif not sight:
        label = NO_LOS
    elif d > full:
        label = OUTSIDE
    elif d <= full / 2 - 0.5 or (full / 2).is_integer() and d <= full / 2:
        label = INSIDE
    elif not (full / 2).is_integer() and d == int(full / 2) + 1:
        label = BOUNDARY
    else:
        label = BETWEEN
    return Pair(observer["obj_id"], aerial, d, sight, full, label, m.covered(x), lower)


#: Target-step classes for a concealed target.
DISCRIMINATING = "discriminating: an observer between the concealed and the normal distance, none closer"
EXPECTED_VISIBLE = "expected listed: an observer within the concealed distance"
EXCEPTION_VISIBLE = "expected listed: documented exception (a vehicle lower than a ground observer within range)"
EXPECTED_HIDDEN = "expected unlisted: no observer within the normal distance"
TERRAIN = "terrain: the target in a forest or town hex (stacking of the two halvings undocumented)"
AMBIGUOUS_AIR = "ambiguous: an aerial observer within its normal distance of a concealed vehicle (exception undocumented)"
AMBIGUOUS_BOUNDARY = "ambiguous: the nearest relevant observer on the rounding boundary of 12.5 hexes"


def classify(m: MapData, observers: Iterable[Mapping[str, Any]], target: Mapping[str, Any]) -> Tuple[str, List[Pair]]:
    """The class of one concealed ground target at one step, and its pairs with every opposing observer on the map."""
    pairs = [band(m, o, target) for o in observers]
    relevant = [p for p in pairs if p.band in (INSIDE, BETWEEN, BOUNDARY)]
    if m.covered(target["cur_hex"]) and relevant:
        return TERRAIN, pairs
    if any(p.band in (INSIDE, BETWEEN, BOUNDARY) and p.lower_vehicle for p in pairs):
        return EXCEPTION_VISIBLE, pairs
    if target.get("type") == VEHICLE and any(p.aerial and p.band in (INSIDE, BETWEEN, BOUNDARY) for p in pairs):
        return AMBIGUOUS_AIR, pairs
    if any(p.band == INSIDE for p in pairs):
        return EXPECTED_VISIBLE, pairs
    if any(p.band == BOUNDARY for p in pairs):
        return AMBIGUOUS_BOUNDARY, pairs
    if any(p.band == BETWEEN for p in pairs):
        return DISCRIMINATING, pairs
    return EXPECTED_HIDDEN, pairs
