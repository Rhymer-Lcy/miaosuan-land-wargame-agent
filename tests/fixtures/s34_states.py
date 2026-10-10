"""Synthetic states for the Sprint 34 integrated agent tests. SYNTHETIC: invented map, units and numbers.

A 12 x 12 map with uniform costs (``tests/fixtures/synthetic.py`` conventions: odd rows shifted right, ids in the
900000 range, seats 7 and 17). ``unit`` builds an own or enemy unit record with the fields the agent reads; ``obs``
assembles a complete observation for one seat from units, listings, cities and passengers.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from tests.fixtures import synthetic as syn

ROWS = COLS = 12
RED_SEAT, BLUE_SEAT = syn.RED_SEAT, syn.BLUE_SEAT
MAX_STEP = 2000


def costs(entry_costs: Optional[Mapping[int, float]] = None) -> List[Any]:
    return syn.cost_data(ROWS, COLS, 1, entry_costs)


def unit(obj_id: int, color: int, hex_: int, *, type_: int = 2, sub_type: int = 0, path: Sequence[int] = (),
         speed: float = 0.0, basic_speed: float = 36, value: int = 10, blood: int = 3, move_to_stop: float = 0,
         weapons: Sequence[int] = (37,), passengers: Sequence[int] = (), passenger_types: Sequence[int] = (),
         on_board: int = 0, get_on: float = 0, get_off: float = 0) -> Dict[str, Any]:
    return {"obj_id": obj_id, "color": color, "type": type_, "sub_type": sub_type, "cur_hex": hex_, "move_state": 0,
            "move_path": list(path), "speed": speed, "cur_pos": 0.0, "basic_speed": basic_speed, "blood": blood,
            "max_blood": blood, "value": value, "move_to_stop_remain_time": move_to_stop, "stop": 0 if path else 1,
            "get_on_remain_time": get_on, "get_off_remain_time": get_off, "change_state_remain_time": 0,
            "on_board": on_board, "car": None, "passenger_ids": list(passengers),
            "valid_passenger_types": list(passenger_types), "max_passenger_nums": {"2": 1},
            "carry_weapon_ids": list(weapons), "see_enemy_bop_ids": [], "armor": 1, "weapon_cool_time": 0}


def obs(color: int, units: Sequence[Dict[str, Any]], listings: Mapping[int, Any], *,
        cities: Sequence[Dict[str, Any]] = (), passengers: Sequence[Dict[str, Any]] = (), step: int = 10,
        stage: int = 2, controlled: Optional[Iterable[int]] = None, jm_points: Sequence[Dict[str, Any]] = (),
        max_step: int = MAX_STEP) -> Dict[str, Any]:
    seat = RED_SEAT if color == 0 else BLUE_SEAT
    own = [u["obj_id"] for u in units if u["color"] == color] + [p["obj_id"] for p in passengers]
    ids = sorted(own if controlled is None else controlled)
    record = syn.build_observation(units=list(units), valid_actions=dict(listings),
                                   seats={seat: syn.seat_record(seat, color, ids, stage >= 2)},
                                   stage=stage, cur_step=step, cities=list(cities))
    record["passengers"] = [dict(p) for p in passengers]
    record["time"]["max_time"] = record["time"]["max_step"] = max_step
    record["jm_points"] = [dict(p) for p in jm_points]
    return record


def city(hex_: int, flag: int = -1, value: int = 80) -> Dict[str, Any]:
    return syn.city(hex_, flag, value)
