"""Synthetic engine states, observations and maps for tests. SYNTHETIC: nothing here is SDK data.

Field *names* and value *types* follow the interface verified on SDK engine 4.1.0
(``docs/CONTRACT.md``). Every identifier, coordinate, name and number is invented and chosen to be
recognisably artificial: unit ids in the 900000 range, seats 7 and 17, scenario 900000001,
terrain 9000, user names prefixed ``synthetic-``, a 10 x 10 map with uniform costs. Records are
built by functions so that each test states the variation it needs instead of copying a blob.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from miaosuan_agent.boundary.profile import SCORE_FIELDS

RED_SEAT = 7
BLUE_SEAT = 17
RED_UNIT = 900101
BLUE_UNIT = 900201
SCENARIO_ID = 900000001
TERRAIN_ID = 9000
GRID_ROWS = 10
GRID_COLS = 10
RED_HEX = 102
BLUE_HEX = 807
CITY_HEX = 505
DIRECTOR_OPTIONS = {401: None, 402: None, 403: None, 404: None}


def unit(obj_id: int, color: int, hex_: int, *, unit_type: int = 2, move_state: int = 0,
         move_path: Sequence[int] = ()) -> Dict[str, Any]:
    """A unit record with a handful of fields, including one the boundary does not know."""
    return {"obj_id": obj_id, "color": color, "type": unit_type, "sub_type": 0, "cur_hex": hex_,
            "move_state": move_state, "move_path": list(move_path), "synthetic_field": "preserved"}


def seat_record(seat: int, faction: int, operators: Sequence[int], end_deployment: bool) -> Dict[str, Any]:
    return {"faction": faction, "role": 1, "operators": list(operators), "user_id": 900000 + seat,
            "user_name": f"synthetic-{'red' if faction == 0 else 'blue'}", "end_deployment": end_deployment}


def city(coord: int, flag: int = -1, value: int = 7) -> Dict[str, Any]:
    return {"coord": coord, "value": value, "flag": flag, "name": "synthetic objective"}


def build_observation(*, units: Sequence[Dict[str, Any]], valid_actions: Mapping[int, Any],
                      seats: Mapping[int, Dict[str, Any]], stage: int = 2, cur_step: int = 0,
                      cities: Optional[Sequence[Dict[str, Any]]] = None, roadblocks: Iterable[int] = (),
                      communication: Optional[List[Dict[str, Any]]] = None,
                      all_seeing: bool = False) -> Dict[str, Any]:
    """A complete observation with the 13 observed fields (14 for the all-seeing view)."""
    obs: Dict[str, Any] = {
        "operators": [dict(u) for u in units],
        "passengers": [],
        "time": {"cur_step": cur_step, "tick": 1.0, "max_time": 50, "max_step": 50, "stage": stage},
        "jm_points": [],
        "cities": [dict(c) for c in (cities if cities is not None else [city(CITY_HEX)])],
        "scores": {name: 0 for name in sorted(SCORE_FIELDS)},
        "judge_info": [],
        "valid_actions": {k: v for k, v in valid_actions.items()},
        "role_and_grouping_info": {k: dict(v) for k, v in seats.items()},
        "communication": list(communication or []),
        "landmarks": {"roadblocks": [{"id": index, "name": "synthetic roadblock", "hex": hex_, "color": -1,
                                      "creator": None, "type": 0} for index, hex_ in enumerate(roadblocks)],
                      "minefields": [], "fortifications": []},
        "scenario_id": SCENARIO_ID,
        "terrain_id": TERRAIN_ID,
    }
    if all_seeing:
        obs["valid_actions"][-1] = dict(DIRECTOR_OPTIONS)
        obs["actions"] = []
    return obs


def observation(slot: int, stage: int = 1, cur_step: int = 0, *, end_deployment: Optional[bool] = None,
                communication: Optional[List[Dict[str, Any]]] = None, red_seat: int = RED_SEAT,
                blue_seat: int = BLUE_SEAT) -> Dict[str, Any]:
    """One observation for slot 0 (red), 1 (blue) or -1 (all-seeing)."""
    ended = stage >= 2 if end_deployment is None else end_deployment
    red = (unit(RED_UNIT, 0, RED_HEX), {RED_UNIT: {1: None, 6: [{"target_state": 2}]}},
           {red_seat: seat_record(red_seat, 0, [RED_UNIT], ended)})
    blue = (unit(BLUE_UNIT, 1, BLUE_HEX), {BLUE_UNIT: {1: None}},
            {blue_seat: seat_record(blue_seat, 1, [BLUE_UNIT], ended)})
    parts = {0: [red], 1: [blue], -1: [red, blue]}.get(slot)
    if parts is None:
        raise ValueError(f"no such slot {slot}")
    return build_observation(units=[part[0] for part in parts],
                             valid_actions={k: v for part in parts for k, v in part[1].items()},
                             seats={k: v for part in parts for k, v in part[2].items()},
                             stage=stage, cur_step=cur_step, communication=communication, all_seeing=slot == -1)


def state(stage: int = 1, cur_step: int = 0, **kwargs: Any) -> Dict[int, Dict[str, Any]]:
    """The mapping form observed from engine 4.1.0: keys 0 (red), 1 (blue), -1 (all-seeing)."""
    return {slot: observation(slot, stage, cur_step, **kwargs) for slot in (0, 1, -1)}


def sequence_state(stage: int = 1, cur_step: int = 0, **kwargs: Any) -> List[Dict[str, Any]]:
    """The documented list form ``[red, blue, all-seeing]``."""
    return [observation(slot, stage, cur_step, **kwargs) for slot in (0, 1, -1)]


def grid_neighbours(hex_: int, rows: int = GRID_ROWS, cols: int = GRID_COLS) -> List[int]:
    """Six neighbours in the documented order (east first, then anticlockwise), odd rows shifted right."""
    row, col = divmod(hex_, 100)
    if row % 2:
        offsets = [(0, 1), (-1, 1), (-1, 0), (0, -1), (1, 0), (1, 1)]
    else:
        offsets = [(0, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0)]
    return [(row + dr) * 100 + (col + dc) for dr, dc in offsets
            if 0 <= row + dr < rows and 0 <= col + dc < cols]


def cost_data(rows: int = GRID_ROWS, cols: int = GRID_COLS, cost: float = 1,
              entry_costs: Optional[Mapping[int, float]] = None) -> List[List[List[Dict[int, float]]]]:
    """Four identical movement modes; entering hex ``h`` costs ``entry_costs.get(h, cost)``."""
    entry = dict(entry_costs or {})
    grid = [[{n: entry.get(n, cost) for n in grid_neighbours(r * 100 + c, rows, cols)} for c in range(cols)]
            for r in range(rows)]
    return [[[dict(cell) for cell in row] for row in grid] for _ in range(4)]


def json_round_trip(value: Any) -> Any:
    """What a JSON transport or file delivers: every mapping key becomes a string."""
    return json.loads(json.dumps(value))
