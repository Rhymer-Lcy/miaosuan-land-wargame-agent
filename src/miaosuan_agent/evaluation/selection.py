"""The pre-registered scenario selection rule: eligibility, strata and picks, fixed before any result.

Facts are computed from the SDK's scenario and map files (private) by :func:`survey`; the rule
itself (:func:`select`) is a pure function of those facts, so it is testable on synthetic facts.

Eligibility (each failure is recorded as a reason; the pairing or inputs are then invalid):

* E1 the scenario id names a supplied map by the naming rule (``NAMING_RULE``);
* E2 every operator and objective hex lies inside that map;
* E3 every operator that starts on the map (not on board) and has a documented movement mode
  (types 1 to 3) has at least one traversable neighbour for that mode at its start hex;
* E4 on a map whose cells carry roadblock flags, the scenario's roadblocks are exactly those cells.

Selection:

* S1 strata are the maps of the eligible scenarios;
* S2 from each stratum, the scenario with the fewest operators; ties by smaller ``max_time``, then
  smaller numeric scenario id;
* S3 in addition, the eligible scenario with the most operators overall (ties by smaller numeric
  id); if S2 already picked it, the next one in that order that S2 did not pick.

Replacement, applied only for a documented objective failure (the engine raises during setup,
before any decision): the next scenario in the same order within the same pick (S2 stratum or S3).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from typing import Collection, Dict, List, Optional, Sequence, Tuple

from ..boundary import MoveCosts, MoveMode
from ..sdk_data import load_cost_bytes

RULE_ID = "miaosuan-scenario-selection/1"
NAMING_RULE = "map id = the last four digits of the scenario id when they are 9601, otherwise the last two digits"
#: Documented movement modes of unit types 1 (infantry), 2 (vehicle), 3 (aircraft).
START_MODES = {1: MoveMode.INFANTRY, 2: MoveMode.VEHICLE, 3: MoveMode.AIR}


@dataclass(frozen=True)
class ScenarioFacts:
    scenario_id: str
    map_id: Optional[str]
    operators: int
    red: int
    blue: int
    cities: int
    max_time: int
    reasons: Tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Pick:
    scenario_id: str
    map_id: str
    rule: str
    alternates: Tuple[str, ...] = field(default=())


def map_by_name(scenario_id: str, maps: Collection[str]) -> Optional[str]:
    """The supplied map the scenario id names, or ``None``."""
    candidate = scenario_id[-4:] if scenario_id.endswith("9601") else scenario_id[-2:]
    return candidate if candidate in maps else None


def _fewest_key(facts: ScenarioFacts) -> Tuple[int, int, int]:
    return (facts.operators, facts.max_time, int(facts.scenario_id))


def _largest_key(facts: ScenarioFacts) -> Tuple[int, int]:
    return (-facts.operators, int(facts.scenario_id))


def select(facts: Sequence[ScenarioFacts]) -> List[Pick]:
    """Apply S1 to S3. The result is ordered: S2 picks by map id (numeric), then the S3 pick."""
    eligible = [f for f in facts if f.eligible]
    by_map: Dict[str, List[ScenarioFacts]] = {}
    for item in eligible:
        by_map.setdefault(item.map_id, []).append(item)
    picks: List[Pick] = []
    for map_id in sorted(by_map, key=int):
        ordered = sorted(by_map[map_id], key=_fewest_key)
        picks.append(Pick(ordered[0].scenario_id, map_id, f"S2 fewest operators on map {map_id}",
                          tuple(item.scenario_id for item in ordered[1:])))
    taken = {pick.scenario_id for pick in picks}
    largest = [item for item in sorted(eligible, key=_largest_key) if item.scenario_id not in taken]
    if largest:
        picks.append(Pick(largest[0].scenario_id, largest[0].map_id, "S3 largest force",
                          tuple(item.scenario_id for item in largest[1:])))
    return picks


def _roadblock_cells(basic: dict) -> Optional[frozenset]:
    """Cells flagged as roadblocks in ``basic.json``, or ``None`` when the map has no such flags."""
    cells, flagged = set(), False
    for row_index, row in enumerate(basic["map_data"]):
        for col_index, cell in enumerate(row):
            if isinstance(cell, dict) and "roadblock" in cell:
                flagged = True
                if cell["roadblock"]:
                    cells.add(row_index * 100 + col_index)
    return frozenset(cells) if flagged else None


def facts_for(scenario: dict, scenario_id: str, map_id: Optional[str], basic: Optional[dict],
              costs: Optional[MoveCosts]) -> ScenarioFacts:
    operators = scenario.get("operators", [])
    reasons: List[str] = []
    if map_id is None or basic is None or costs is None:
        reasons.append("E1 no supplied map named by the scenario id")
    else:
        rows, cols = len(basic["map_data"]), len(basic["map_data"][0])
        hexes = [op.get("cur_hex") for op in operators] + [c.get("coord") for c in scenario.get("cities", [])]
        if any(not (isinstance(h, int) and 0 <= h // 100 < rows and 0 <= h % 100 < cols) for h in hexes):
            reasons.append("E2 a position lies outside the map")
        else:
            for op in operators:
                mode = START_MODES.get(op.get("type"))
                if mode is not None and not op.get("on_board") and not costs.neighbours(mode, op["cur_hex"]):
                    reasons.append("E3 a unit starts on a hex with no traversable neighbour for its mode")
                    break
        flagged = _roadblock_cells(basic)
        if flagged is not None:
            # scenario files list roadblocks as bare hex indices (observations wrap them in records)
            blocks = frozenset((scenario.get("landmarks") or {}).get("roadblocks", []))
            if blocks != flagged:
                reasons.append("E4 roadblocks differ from the map's roadblock cells")
    colors = [op.get("color") for op in operators]
    return ScenarioFacts(scenario_id=scenario_id, map_id=map_id, operators=len(operators),
                         red=colors.count(0), blue=colors.count(1), cities=len(scenario.get("cities", [])),
                         max_time=int(scenario["time"]["max_time"]), reasons=tuple(reasons))


def survey(data: zipfile.ZipFile) -> List[ScenarioFacts]:
    """Facts for every scenario in an opened SDK ``Data.zip``, ordered by numeric scenario id."""
    names = data.namelist()
    maps = {name.split("/")[2][len("map_"):] for name in names
            if name.startswith("Data/maps/map_") and name.endswith("/basic.json")}
    scenario_files = [name for name in names if name.startswith("Data/scenarios/") and name.endswith(".json")]
    cache: Dict[str, Tuple[dict, MoveCosts]] = {}
    facts = []
    for name in scenario_files:
        scenario_id = name.rsplit("/", 1)[1][:-len(".json")]
        scenario = json.loads(data.read(name).decode("utf-8"))
        map_id = map_by_name(scenario_id, maps)
        basic = costs = None
        if map_id is not None:
            if map_id not in cache:
                basic_data = json.loads(data.read(f"Data/maps/map_{map_id}/basic.json").decode("utf-8"))
                cost_data = MoveCosts.from_raw(load_cost_bytes(data.read(f"Data/maps/map_{map_id}/cost.pickle")))
                cache[map_id] = (basic_data, cost_data)
            basic, costs = cache[map_id]
        facts.append(facts_for(scenario, scenario_id, map_id, basic, costs))
    return sorted(facts, key=lambda item: int(item.scenario_id))
