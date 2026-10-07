"""A deterministic stand-in transport engine for the Sprint 22 tests. SYNTHETIC: invented map, units and numbers.

The interface shape follows engine 4.1.0 (``setup`` / ``step`` / ``reset``, the state mapping with keys 0, 1 and -1,
deployment ending when both seats send 333, every received action echoed in the all-seeing ``actions`` field, with an
error when refused). Its transport semantics are the documented ones only: embark (3, listed under an infantry standing
stopped in the hex of a stopped infantry fighting vehicle with infantry room) and disembark (4, listed under a settled
carrier for each passenger) take 75 steps, during which neither unit lists anything; an aboard infantry is in
``passengers`` (``on_board`` 1, ``car`` its carrier, listed in the carrier's ``passenger_ids``) and moves with it; a
unit ending a move has a 75-step stop transition; occupation is listed for a unit standing on an objective its side does
not hold; four own ground units per hex. Blue: one infantry and one infantry fighting vehicle in ``START``, a slow tank
far away; red: one unit that never acts. Options: ``refuse`` (action types answered with an error and no effect),
``extra_at_destination`` (blue tanks standing still on the near objective), ``hex_steps`` (steps per hex).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence

from tests.fixtures import synthetic as syn

SEATS = {0: 1, 1: 11}
RED, BLUE = 0, 1
INF, CAR, TANK, RED_UNIT = 940001, 940002, 940003, 950001
START, NEAR, FAR, TANK_START = 202, 505, 909, 707
TRANSITION = 75
CITIES = ({"coord": NEAR, "value": 80, "flag": -1, "name": "synthetic objective"},
          {"coord": FAR, "value": 50, "flag": -1, "name": "synthetic objective"})


def unit(obj_id: int, color: int, hex_: int, kind: str) -> Dict[str, Any]:
    unit_type, sub_type = {"ifv": (2, 1), "infantry": (1, 2), "tank": (2, 0)}[kind]
    return {"obj_id": obj_id, "color": color, "type": unit_type, "sub_type": sub_type, "cur_hex": hex_,
            "move_state": 0, "move_path": [], "speed": 0, "move_to_stop_remain_time": 0, "keep": 0, "on_board": 0,
            "car": None, "passenger_ids": [], "get_on_remain_time": 0, "get_on_partner_id": [],
            "get_off_remain_time": 0, "get_off_partner_id": [], "basic_speed": 36 if unit_type == 2 else 5,
            "valid_passenger_types": [2, 4, 7] if kind == "ifv" else [], "stop": 1, "blood": 1, "max_blood": 1,
            "max_passenger_nums": {2: 1, 4: 1, 7: 2} if kind == "ifv" else {}}


class TransportEnv:
    def __init__(self, play_steps: int = 900, refuse: Sequence[int] = (), extra_at_destination: int = 0,
                 hex_steps: int = 5) -> None:
        self.play_steps, self.refuse, self.extra, self.hex_steps = play_steps, set(refuse), extra_at_destination, hex_steps
        self.stage, self.cur_step = 1, 0
        self.ended = {RED: False, BLUE: False}
        self.echo: List[Dict[str, Any]] = []
        self.units: Dict[int, Dict[str, Any]] = {}
        self.passengers: Dict[int, Dict[str, Any]] = {}
        self.timers: Dict[int, int] = {}
        self.fixed: set = set()
        self.cities: List[Dict[str, Any]] = []

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        seats = [player["seat"] for player in setup_info["player_info"]]
        assert seats == [SEATS[RED], SEATS[BLUE]], seats
        self.units = {INF: unit(INF, BLUE, START, "infantry"), CAR: unit(CAR, BLUE, START, "ifv"),
                      TANK: unit(TANK, BLUE, TANK_START, "tank"), RED_UNIT: unit(RED_UNIT, RED, 9, "tank")}
        for i in range(self.extra):
            self.units[960001 + i] = unit(960001 + i, BLUE, NEAR, "tank")
            self.fixed.add(960001 + i)
        self.cities = [dict(c) for c in CITIES]
        return self.state()

    # ---- observation
    def _valid(self, u: Dict[str, Any]) -> Dict[int, Any]:
        if u["color"] != BLUE or u["obj_id"] in self.fixed or u["get_on_remain_time"] or u["get_off_remain_time"]:
            return {}
        if u["move_path"]:
            return {10: None}
        settled = not u["move_to_stop_remain_time"]
        out: Dict[int, Any] = {1: None}
        city = next((c for c in self.cities if c["coord"] == u["cur_hex"]), None)
        if city is not None and city["flag"] != BLUE:
            out[5] = None
        if u["type"] == 1 and settled:
            cars = [c for c in self.units.values() if c["color"] == BLUE and (c["type"], c["sub_type"]) == (2, 1)
                    and c["cur_hex"] == u["cur_hex"] and not c["move_path"] and not c["move_to_stop_remain_time"]
                    and not c["get_on_remain_time"] and not c["get_off_remain_time"] and not c["passenger_ids"]]
            if cars:
                out[3] = [{"target_obj_id": c["obj_id"]} for c in cars]
        if (u["type"], u["sub_type"]) == (2, 1) and settled and u["passenger_ids"]:
            out[4] = [{"target_obj_id": p} for p in u["passenger_ids"]]
        return out

    def state(self) -> Dict[int, Any]:
        units = [copy.deepcopy(u) for _, u in sorted(self.units.items())]
        passengers = [copy.deepcopy(p) for _, p in sorted(self.passengers.items())]
        blue_ids = sorted(u for u, rec in list(self.units.items()) + list(self.passengers.items()) if rec["color"] == BLUE)
        seats = {SEATS[RED]: syn.seat_record(SEATS[RED], RED, [RED_UNIT], self.ended[RED]),
                 SEATS[BLUE]: syn.seat_record(SEATS[BLUE], BLUE, blue_ids, self.ended[BLUE])}
        valid_blue = {u["obj_id"]: self._valid(u) for u in self.units.values() if u["color"] == BLUE}
        common = dict(units=units, seats=seats, stage=self.stage, cur_step=self.cur_step,
                      cities=copy.deepcopy(self.cities))
        obs_red = syn.build_observation(valid_actions={RED_UNIT: {}}, **common)
        obs_blue = syn.build_observation(valid_actions=valid_blue, **common)
        everything = syn.build_observation(valid_actions={**valid_blue, RED_UNIT: {}}, all_seeing=True, **common)
        everything["actions"] = copy.deepcopy(self.echo)
        for obs in (obs_red, obs_blue, everything):
            obs["time"]["max_time"] = obs["time"]["max_step"] = self.play_steps
            obs["passengers"] = copy.deepcopy(passengers)
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
        if u is None:
            return 11
        busy = u["get_on_remain_time"] or u["get_off_remain_time"]
        if action["type"] == 1:
            if u["move_path"] or busy:
                return 21
            u["move_path"], u["move_to_stop_remain_time"] = list(action["move_path"]), 0
            self.timers[u["obj_id"]] = self.hex_steps if u["obj_id"] != TANK else 400
            return None
        if action["type"] == 5:
            city = next((c for c in self.cities if c["coord"] == u["cur_hex"]), None)
            if city is None or city["flag"] == BLUE:
                return 1804
            city["flag"] = BLUE
            return None
        if action["type"] == 3:
            if 3 not in self._valid(u) or {"target_obj_id": action.get("target_obj_id")} not in self._valid(u)[3]:
                return 31
            car = self.units[action["target_obj_id"]]
            for x, partner in ((u, car), (car, u)):
                x["get_on_remain_time"], x["get_on_partner_id"] = TRANSITION, [partner["obj_id"]]
            return None
        if action["type"] == 4:
            if 4 not in self._valid(u) or {"target_obj_id": action.get("target_obj_id")} not in self._valid(u)[4]:
                return 41
            if sum(1 for x in self.units.values() if x["color"] == BLUE and x["type"] in (1, 2)
                   and x["cur_hex"] == u["cur_hex"]) >= 4:
                return None  # the documented stacking limit voids it silently
            p = self.passengers[action["target_obj_id"]]
            for x, partner in ((u, p), (p, u)):
                x["get_off_remain_time"], x["get_off_partner_id"] = TRANSITION, [partner["obj_id"]]
            return None
        return 99

    def _advance(self) -> None:
        for u in list(self.units.values()):
            if u["get_on_remain_time"]:
                u["get_on_remain_time"] -= 1
                if not u["get_on_remain_time"]:
                    partner = u["get_on_partner_id"][0]
                    u["get_on_partner_id"] = []
                    if u["type"] == 1:
                        del self.units[u["obj_id"]]
                        u.update(on_board=1, car=partner)
                        self.passengers[u["obj_id"]] = u
                        self.units[partner]["passenger_ids"] = [u["obj_id"]]
            if u["move_to_stop_remain_time"]:
                u["move_to_stop_remain_time"] -= 1
            if u["move_path"]:
                self.timers[u["obj_id"]] -= 1
                u["speed"] = 1
                if not self.timers[u["obj_id"]]:
                    nxt = u["move_path"][0]
                    full = sum(1 for x in self.units.values() if x["color"] == BLUE and x["type"] in (1, 2)
                               and x["cur_hex"] == nxt) >= 4
                    if full:
                        self.timers[u["obj_id"]] = 1
                        continue
                    u["cur_hex"] = u["move_path"].pop(0)
                    self.timers[u["obj_id"]] = self.hex_steps if u["obj_id"] != TANK else 400
                    for p in u["passenger_ids"]:
                        self.passengers[p]["cur_hex"] = u["cur_hex"]
                    if not u["move_path"]:
                        u["speed"], u["move_to_stop_remain_time"] = 0, TRANSITION
        for p in list(self.passengers.values()):
            if p["get_off_remain_time"]:
                p["get_off_remain_time"] -= 1
                car = self.units[p["get_off_partner_id"][0]]
                car["get_off_remain_time"] = p["get_off_remain_time"]
                if not p["get_off_remain_time"]:
                    p["get_off_partner_id"], car["get_off_partner_id"] = [], []
                    car["passenger_ids"] = []
                    p.update(on_board=0, car=None, cur_hex=car["cur_hex"])
                    del self.passengers[p["obj_id"]]
                    self.units[p["obj_id"]] = p

    def reset(self) -> None:
        self.units, self.passengers = {}, {}


class Inputs:
    """Setup inputs of the stand-in (synthetic scenario, uniform costs)."""

    scenario, basic, see = {}, {}, {}
    cost = syn.cost_data()
