"""A deterministic stand-in engine for the Sprint 33 tests. SYNTHETIC: invented map, units and numbers.

Sprint 27's stand-in interface (``tests/fixtures/s27_engine.py``: ``setup`` / ``step`` / ``reset``, the state mapping
with keys 0, 1 and -1, deployment ending when both seats send 333, every received action echoed in the all-seeing
``actions`` field, with an error when refused) with the fields the stop candidate reads. Blue: one infantry fighting
vehicle (``IFV``: type 2, sub_type 1, ``A1`` 0, a vehicle-mounted missile, weapon 69, published range 20 against
vehicles) on ``START``; red: one vehicle that lists nothing (the inert control plays red) on ``RED_HEX``, in the IFV's
own ``see_enemy_bop_ids`` and within range everywhere on the map. The objective ``FAR`` is unheld, so ``baseline-v2``
orders the IFV toward it; while it traverses, the candidate's trigger holds.

Movement: a unit entering a hex needs ``hex_steps`` steps; ``speed`` is ``1 / hex_steps`` hexes per step and
``cur_pos`` the fraction of the current hex done, so the documented ``ceil((1 - cur_pos) / speed)`` is the number of
steps to the next entry. The path empties on entering its last hex, with ``stop`` 0 and ``move_to_stop_remain_time``
75 counting down, ``stop`` returning to 1 when it reaches 0 (``docs/T7_DESIGN.md``, B-2). While traversing a unit lists
only the stop (action 10, value ``None``); during a transition nothing; when stopped, movement (1) and, for a unit with
``A1`` 0 and a target in range and no shot in the last 75 steps, a shot (2). A shot is echoed and appends a judge record
naming the attacker.

The stop order (action 10) follows ``mode``:

* ``documented``: the unit finishes its current hex; on entering the next hex the rest of the path is dropped and the
  75-step transition starts. With ``flag`` true, ``flag_force_stop`` is 1 from the order until the path clears.
* ``refuse``: the order is answered with an error and has no effect.
* ``defer``: ``flag_force_stop`` 1, ``speed`` 0, the path kept, every listing withdrawn, for the rest of the game
  (``docs/PS1_ENGINE_PROBE.md``, B-4).
* ``in_place``: the path is dropped at once and the transition starts on the current hex.
* ``late``: as documented, but the transition lasts ``late_transition`` steps.
* ``no_resume``: as documented, but movement is never listed again after the transition.
* ``no_fire``: as documented, but a shot is never listed.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from tests.fixtures import synthetic as syn

SEATS = {0: 1, 1: 11}
RED, BLUE = 0, 1
IFV = 970101
RED_VEHICLE = 980101
START, FAR, RED_HEX = 202, 808, 909
TRANSITION = 75
COOLDOWN = 75
STACK_LIMIT = 4
MODES = ("documented", "refuse", "defer", "in_place", "late", "no_resume", "no_fire")
CITIES = ({"coord": FAR, "value": 80, "flag": -1, "name": "synthetic objective"},)


def unit(obj_id: int, color: int, hex_: int) -> Dict[str, Any]:
    return {"obj_id": obj_id, "color": color, "type": 2, "sub_type": 1, "cur_hex": hex_, "move_state": 0,
            "move_path": [], "speed": 0, "cur_pos": 0, "move_to_stop_remain_time": 0, "flag_force_stop": 0,
            "keep": 0, "keep_remain_time": 0, "on_board": 0, "car": None, "passenger_ids": [],
            "get_on_remain_time": 0, "get_on_partner_id": [], "get_off_remain_time": 0, "get_off_partner_id": [],
            "change_state_remain_time": 0, "weapon_unfold_time": 0, "weapon_unfold_state": 1, "A1": 0,
            "basic_speed": 36, "stop": 1, "stack": 0, "blood": 3, "max_blood": 3, "carry_weapon_ids": [69],
            "see_enemy_bop_ids": [], "valid_passenger_types": [], "max_passenger_nums": {}}


class StopEnv:
    def __init__(self, play_steps: int = 400, mode: str = "documented", flag: bool = True, hex_steps: int = 20,
                 late_transition: int = 80) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode}")
        self.play_steps, self.mode, self.flag, self.hex_steps = play_steps, mode, flag, hex_steps
        self.late_transition = late_transition
        self.stage, self.cur_step = 1, 0
        self.ended = {RED: False, BLUE: False}
        self.echo: List[Dict[str, Any]] = []
        self.judge: List[Dict[str, Any]] = []
        self.units: Dict[int, Dict[str, Any]] = {}
        self.remaining: Dict[int, int] = {}
        self.pending: set = set()
        self.applied: set = set()
        self.deferred: set = set()
        self.last_shot: Dict[int, int] = {}
        self.cities: List[Dict[str, Any]] = []

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        seats = [player["seat"] for player in setup_info["player_info"]]
        assert seats == [SEATS[RED], SEATS[BLUE]], seats
        self.units = {IFV: unit(IFV, BLUE, START), RED_VEHICLE: unit(RED_VEHICLE, RED, RED_HEX)}
        self.units[RED_VEHICLE].update(A1=1, carry_weapon_ids=[37])
        self.cities = [dict(c) for c in CITIES]
        return self.state()

    # ---- observation
    def _in_range(self, u: Dict[str, Any]) -> bool:
        from miaosuan_agent.experiments.exploratory_addon import hex_distance
        foe = self.units.get(RED_VEHICLE)
        return foe is not None and hex_distance(u["cur_hex"], foe["cur_hex"]) <= 20

    def _valid(self, u: Dict[str, Any]) -> Dict[int, Any]:
        if u["color"] != BLUE or u["obj_id"] in self.deferred:
            return {}
        if u["move_path"]:
            return {10: None}
        if u["move_to_stop_remain_time"] > 0:
            return {}
        out: Dict[int, Any] = {} if (self.mode == "no_resume" and u["obj_id"] in self.applied) else {1: None}
        cooled = self.cur_step - self.last_shot.get(u["obj_id"], -COOLDOWN) >= COOLDOWN
        if self.mode != "no_fire" and u["A1"] == 0 and cooled and self._in_range(u):
            out[2] = [{"target_obj_id": RED_VEHICLE, "weapon_id": 69, "attack_level": 5}]
        return out

    def state(self) -> Dict[int, Any]:
        for u in self.units.values():
            u["see_enemy_bop_ids"] = [RED_VEHICLE] if u["color"] == BLUE and RED_VEHICLE in self.units else []
        units = [copy.deepcopy(u) for _, u in sorted(self.units.items())]
        blue_ids = sorted(u for u, rec in self.units.items() if rec["color"] == BLUE)
        red_ids = sorted(u for u, rec in self.units.items() if rec["color"] == RED)
        seats = {SEATS[RED]: syn.seat_record(SEATS[RED], RED, red_ids, self.ended[RED]),
                 SEATS[BLUE]: syn.seat_record(SEATS[BLUE], BLUE, blue_ids, self.ended[BLUE])}
        valid_blue = {u["obj_id"]: self._valid(u) for u in self.units.values() if u["color"] == BLUE}
        valid_red = {u["obj_id"]: {} for u in self.units.values() if u["color"] == RED}
        common = dict(units=units, seats=seats, stage=self.stage, cur_step=self.cur_step,
                      cities=copy.deepcopy(self.cities))
        obs_red = syn.build_observation(valid_actions=valid_red, **common)
        obs_blue = syn.build_observation(valid_actions=valid_blue, **common)
        everything = syn.build_observation(valid_actions={**valid_blue, **valid_red}, all_seeing=True, **common)
        everything["actions"] = copy.deepcopy(self.echo)
        for obs in (obs_red, obs_blue, everything):
            obs["time"]["max_time"] = obs["time"]["max_step"] = self.play_steps
            obs["judge_info"] = copy.deepcopy(self.judge)
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
        u = self.units.get(action.get("obj_id"))
        if u is None or u["color"] != BLUE:
            return 11
        kind = action["type"]
        if kind not in self._valid(u):
            return 1001
        if kind == 1:
            u["move_path"], u["speed"], u["cur_pos"] = list(action["move_path"]), 1 / self.hex_steps, 0
            u["stop"] = 0
            self.remaining[u["obj_id"]] = self.hex_steps
            return None
        if kind == 2:
            self.last_shot[u["obj_id"]] = self.cur_step
            self.judge.append({"att_obj_id": u["obj_id"], "target_obj_id": action.get("target_obj_id"),
                               "weapon_id": action.get("weapon_id"), "damage": 1, "cur_step": self.cur_step})
            return None
        if kind == 10:
            if self.mode == "refuse":
                return 2001
            if self.mode == "defer":
                self.deferred.add(u["obj_id"])
                u.update(flag_force_stop=1, speed=0)
                return None
            if self.mode == "in_place":
                self.applied.add(u["obj_id"])
                u.update(move_path=[], speed=0, cur_pos=0, move_to_stop_remain_time=TRANSITION, stop=0)
                return None
            self.pending.add(u["obj_id"])
            if self.flag:
                u["flag_force_stop"] = 1
            return None
        return 99

    def _advance(self) -> None:
        for u in self.units.values():
            uid = u["obj_id"]
            if u["move_to_stop_remain_time"] > 0:
                u["move_to_stop_remain_time"] -= 1
                if u["move_to_stop_remain_time"] == 0:
                    u["stop"] = 1
            if not u["move_path"] or uid in self.deferred:
                continue
            self.remaining[uid] -= 1
            u["cur_pos"] = (self.hex_steps - self.remaining[uid]) / self.hex_steps
            if self.remaining[uid] > 0:
                continue
            u["cur_hex"] = u["move_path"].pop(0)
            u["cur_pos"] = 0
            self.remaining[uid] = self.hex_steps
            stopping = uid in self.pending
            if stopping:
                u["move_path"] = []
                self.pending.discard(uid)
                self.applied.add(uid)
            if not u["move_path"]:
                length = self.late_transition if self.mode == "late" and stopping else TRANSITION
                u.update(speed=0, move_to_stop_remain_time=length, stop=0, flag_force_stop=0)

    def reset(self) -> None:
        self.units = {}


class Inputs:
    """Setup inputs of the stand-in (synthetic scenario, uniform costs)."""

    scenario, basic, see = {}, {}, {}
    cost = syn.cost_data()
