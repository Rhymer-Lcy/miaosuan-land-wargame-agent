"""A deterministic stand-in head-to-head engine for the Sprint 27 tests. SYNTHETIC: invented map, units and numbers.

The interface shape follows engine 4.1.0 (``setup`` / ``step`` / ``reset``, the state mapping with keys 0, 1 and -1,
deployment ending when both seats send 333, every received action echoed in the all-seeing ``actions`` field, with an
error when refused). Movement follows the documented model only: a unit given a MOVE enters the next hex of its path
``hex_steps`` steps later (its ``cur_hex`` changes on entry), waits while that hex holds four own ground units, and
ends its move with a 75-step stop transition; ``speed`` is positive while it traverses; ``stack`` is set while another
own ground unit shares its hex; occupation (5) is listed for a unit standing on an objective its side does not hold.

Blue: ``n_blue`` tanks co-located in ``START``; red: one tank that lists nothing (``baseline-v2`` gives it no action),
visible to blue, whose published gun range covers the whole map. Options: ``refuse`` (action types answered with an
error and no effect), ``block`` (blue tanks fixed on the first hex of the route, so the leader cannot advance),
``remove`` ({unit: step}: a unit removed from the game at that step), ``hex_steps`` (steps per hex).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence

from tests.fixtures import synthetic as syn

SEATS = {0: 1, 1: 11}
RED, BLUE = 0, 1
T1, T2, T3, T4 = 970001, 970002, 970003, 970004
RED_TANK = 980001
START, NEAR, FAR, RED_HEX, FIRST = 202, 505, 808, 909, 203
STOP_TRANSITION = 75
STACK_LIMIT = 4
CITIES = ({"coord": NEAR, "value": 80, "flag": -1, "name": "synthetic objective"},
          {"coord": FAR, "value": 50, "flag": -1, "name": "synthetic objective"})


def unit(obj_id: int, color: int, hex_: int) -> Dict[str, Any]:
    return {"obj_id": obj_id, "color": color, "type": 2, "sub_type": 0, "cur_hex": hex_, "move_state": 0,
            "move_path": [], "speed": 0, "move_to_stop_remain_time": 0, "keep": 0, "keep_remain_time": 0,
            "on_board": 0, "car": None, "passenger_ids": [], "get_on_remain_time": 0, "get_on_partner_id": [],
            "get_off_remain_time": 0, "get_off_partner_id": [], "basic_speed": 36, "stop": 1, "stack": 0,
            "blood": 3, "max_blood": 3, "carry_weapon_ids": [36], "valid_passenger_types": [],
            "max_passenger_nums": {}}


class StaggerEnv:
    def __init__(self, play_steps: int = 700, n_blue: int = 3, refuse: Sequence[int] = (), block: int = 0,
                 remove: Optional[Mapping[int, int]] = None, hex_steps: int = 20) -> None:
        self.play_steps, self.n_blue, self.refuse, self.block = play_steps, n_blue, set(refuse), block
        self.remove, self.hex_steps = dict(remove or {}), hex_steps
        self.stage, self.cur_step = 1, 0
        self.ended = {RED: False, BLUE: False}
        self.echo: List[Dict[str, Any]] = []
        self.units: Dict[int, Dict[str, Any]] = {}
        self.timers: Dict[int, int] = {}
        self.fixed: set = set()
        self.cities: List[Dict[str, Any]] = []

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        seats = [player["seat"] for player in setup_info["player_info"]]
        assert seats == [SEATS[RED], SEATS[BLUE]], seats
        blue = (T1, T2, T3, T4)[:self.n_blue]
        self.units = {u: unit(u, BLUE, START) for u in blue}
        self.units[RED_TANK] = unit(RED_TANK, RED, RED_HEX)
        self.fixed = {RED_TANK}
        for i in range(self.block):
            self.units[990001 + i] = unit(990001 + i, BLUE, FIRST)
            self.fixed.add(990001 + i)
        self.cities = [dict(c) for c in CITIES]
        self._stack()
        return self.state()

    # ---- observation
    def _valid(self, u: Dict[str, Any]) -> Dict[int, Any]:
        if u["obj_id"] in self.fixed:
            return {}
        if u["move_path"]:
            return {10: None}
        out: Dict[int, Any] = {1: None}
        city = next((c for c in self.cities if c["coord"] == u["cur_hex"]), None)
        if city is not None and city["flag"] != u["color"]:
            out[5] = None
        return out

    def _stack(self) -> None:
        for u in self.units.values():
            u["stack"] = int(any(x is not u and x["color"] == u["color"] and x["cur_hex"] == u["cur_hex"]
                                 for x in self.units.values()))

    def state(self) -> Dict[int, Any]:
        units = [copy.deepcopy(u) for _, u in sorted(self.units.items())]
        blue_ids = sorted(u for u, rec in self.units.items() if rec["color"] == BLUE)
        red_ids = sorted(u for u, rec in self.units.items() if rec["color"] == RED)
        seats = {SEATS[RED]: syn.seat_record(SEATS[RED], RED, red_ids, self.ended[RED]),
                 SEATS[BLUE]: syn.seat_record(SEATS[BLUE], BLUE, blue_ids, self.ended[BLUE])}
        valid_blue = {u["obj_id"]: self._valid(u) for u in self.units.values() if u["color"] == BLUE}
        valid_red = {u["obj_id"]: self._valid(u) for u in self.units.values() if u["color"] == RED}
        common = dict(units=units, seats=seats, stage=self.stage, cur_step=self.cur_step,
                      cities=copy.deepcopy(self.cities))
        obs_red = syn.build_observation(valid_actions=valid_red, **common)
        obs_blue = syn.build_observation(valid_actions=valid_blue, **common)
        everything = syn.build_observation(valid_actions={**valid_blue, **valid_red}, all_seeing=True, **common)
        everything["actions"] = copy.deepcopy(self.echo)
        for obs in (obs_red, obs_blue, everything):
            obs["time"]["max_time"] = obs["time"]["max_step"] = self.play_steps
        return {0: obs_red, 1: obs_blue, -1: everything}

    # ---- dynamics
    def step(self, actions: List[Dict[str, Any]]):
        self.echo = []
        for action in actions:
            error = self._apply(action)
            entry = {"cur_step": self.cur_step, "message": dict(action)}
            if error:
                entry["error"] = {"code": error, "message": "synthetic refusal"}
            self.echo.append(entry)
        if self.stage == 1 and all(self.ended.values()):
            self.stage = 2
        elif self.stage == 2:
            self._advance()
            self.cur_step += 1
        done = self.stage == 2 and self.cur_step >= self.play_steps
        return self.state(), done

    def _apply(self, action: Dict[str, Any]) -> Optional[int]:
        faction = next(f for f, seat in SEATS.items() if seat == action.get("actor"))
        if action["type"] == 333:
            self.ended[faction] = True
            return None
        if action["type"] in self.refuse:
            return 77
        u = self.units.get(action.get("obj_id"))
        if u is None or u["obj_id"] in self.fixed:
            return 11
        if action["type"] == 1:
            if u["move_path"]:
                return 21
            u["move_path"], u["move_to_stop_remain_time"] = list(action["move_path"]), 0
            self.timers[u["obj_id"]] = self.hex_steps
            return None
        if action["type"] == 5:
            city = next((c for c in self.cities if c["coord"] == u["cur_hex"]), None)
            if city is None or city["flag"] == u["color"]:
                return 1804
            city["flag"] = u["color"]
            return None
        return 99

    def _advance(self) -> None:
        for obj_id, step in list(self.remove.items()):
            if step == self.cur_step and obj_id in self.units:
                del self.units[obj_id]
        for u in list(self.units.values()):
            if u["move_to_stop_remain_time"]:
                u["move_to_stop_remain_time"] -= 1
            if u["move_path"]:
                self.timers[u["obj_id"]] -= 1
                u["speed"] = 1
                if self.timers[u["obj_id"]] <= 0:
                    nxt = u["move_path"][0]
                    full = sum(1 for x in self.units.values() if x["color"] == u["color"]
                               and x["cur_hex"] == nxt) >= STACK_LIMIT
                    if full:
                        u["speed"] = 0
                        self.timers[u["obj_id"]] = 1
                        continue
                    u["cur_hex"] = u["move_path"].pop(0)
                    self.timers[u["obj_id"]] = self.hex_steps
                    if not u["move_path"]:
                        u["speed"], u["move_to_stop_remain_time"] = 0, STOP_TRANSITION
        self._stack()

    def reset(self) -> None:
        self.units = {}


class Inputs:
    """Setup inputs of the stand-in (synthetic scenario, uniform costs)."""

    scenario, basic, see = {}, {}, {}
    cost = syn.cost_data()
