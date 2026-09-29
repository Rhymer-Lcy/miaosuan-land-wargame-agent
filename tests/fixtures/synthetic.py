"""Synthetic engine states and observations for tests. SYNTHETIC: nothing here is SDK data.

Field *names* and value *types* follow the interface verified on SDK engine 4.1.0
(``docs/CONTRACT.md``). Every identifier, coordinate, name and number is invented and chosen to be
recognisably artificial: unit ids in the 900000 range, seats 7 and 17, scenario 900000001,
terrain 9000, user names prefixed ``synthetic-``. Records are built by functions so that each
test states the variation it needs instead of copying a large blob.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from miaosuan_agent.boundary.profile import SCORE_FIELDS

RED_SEAT = 7
BLUE_SEAT = 17
RED_UNIT = 900101
BLUE_UNIT = 900201
SCENARIO_ID = 900000001
TERRAIN_ID = 9000


def unit(obj_id: int, color: int, hex_: int) -> Dict[str, Any]:
    """A unit record with a handful of fields, including one the boundary does not know."""
    return {"obj_id": obj_id, "color": color, "type": 2, "sub_type": 0, "cur_hex": hex_,
            "synthetic_field": "preserved"}


def seat_record(seat: int, faction: int, operators: Sequence[int], end_deployment: bool) -> Dict[str, Any]:
    return {"faction": faction, "role": 1, "operators": list(operators), "user_id": 900000 + seat,
            "user_name": f"synthetic-{'red' if faction == 0 else 'blue'}", "end_deployment": end_deployment}


def observation(slot: int, stage: int = 1, cur_step: int = 0, *, end_deployment: Optional[bool] = None,
                communication: Optional[List[Dict[str, Any]]] = None, red_seat: int = RED_SEAT,
                blue_seat: int = BLUE_SEAT) -> Dict[str, Any]:
    """One observation for slot 0 (red), 1 (blue) or -1 (all-seeing)."""
    ended = stage >= 2 if end_deployment is None else end_deployment
    red = (unit(RED_UNIT, 0, 1203), {RED_UNIT: {1: None, 6: [{"target_state": 2}]}},
           {red_seat: seat_record(red_seat, 0, [RED_UNIT], ended)})
    blue = (unit(BLUE_UNIT, 1, 1407), {BLUE_UNIT: {1: None}},
            {blue_seat: seat_record(blue_seat, 1, [BLUE_UNIT], ended)})
    if slot == 0:
        parts = [red]
    elif slot == 1:
        parts = [blue]
    elif slot == -1:
        parts = [red, blue]
    else:
        raise ValueError(f"no such slot {slot}")
    obs: Dict[str, Any] = {
        "operators": [part[0] for part in parts],
        "passengers": [],
        "time": {"cur_step": cur_step, "tick": 1.0, "max_time": 50, "max_step": 50, "stage": stage},
        "jm_points": [],
        "cities": [{"coord": 1305, "value": 7, "flag": -1, "name": "synthetic objective"}],
        "scores": {name: 0 for name in sorted(SCORE_FIELDS)},
        "judge_info": [],
        "valid_actions": {k: v for part in parts for k, v in part[1].items()},
        "role_and_grouping_info": {k: v for part in parts for k, v in part[2].items()},
        "communication": list(communication or []),
        "landmarks": {"roadblocks": [], "minefields": [], "fortifications": []},
        "scenario_id": SCENARIO_ID,
        "terrain_id": TERRAIN_ID,
    }
    if slot == -1:
        obs["actions"] = []
    return obs


def state(stage: int = 1, cur_step: int = 0, **kwargs: Any) -> Dict[int, Dict[str, Any]]:
    """The mapping form observed from engine 4.1.0: keys 0 (red), 1 (blue), -1 (all-seeing)."""
    return {slot: observation(slot, stage, cur_step, **kwargs) for slot in (0, 1, -1)}


def sequence_state(stage: int = 1, cur_step: int = 0, **kwargs: Any) -> List[Dict[str, Any]]:
    """The documented list form ``[red, blue, all-seeing]``."""
    return [observation(slot, stage, cur_step, **kwargs) for slot in (0, 1, -1)]


def json_round_trip(value: Any) -> Any:
    """What a JSON transport or file delivers: every mapping key becomes a string."""
    return json.loads(json.dumps(value))
