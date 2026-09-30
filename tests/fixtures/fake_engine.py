"""A tiny deterministic stand-in for the SDK engine. SYNTHETIC: it models no real rules.

It reproduces the interface shape verified on engine 4.1.0 (``setup`` returns the state mapping
with keys 0, 1 and -1; ``step(actions)`` returns ``(state, done)``; deployment ends when both
seats send 333) and a few documented effects: a move sets ``move_path`` and advances one hex per
step, occupation sets the objective's flag, direct fire adds a ``judge_info`` record, and every
received action is echoed in the all-seeing ``actions`` field, with an error when refused.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from . import synthetic as syn

SEATS = {0: 1, 1: 11}
RED_UNIT, BLUE_UNIT = syn.RED_UNIT, syn.BLUE_UNIT
#: Messages borrowed from engine 4.1.0 for the codes this stand-in can return with ``engine_messages``.
ENGINE_MESSAGES = {1804: "CantOccupyCauseAlreadyMy", 516: "CantShootToDiedBop", 203: "CantControlDiedOperator"}


class FakeEnv:
    """Options: ``play_steps`` before done, ``never_done``, ``fail_at`` (raise in that step),
    ``noise_at`` (perturb the state from that step on), ``refuse_moves`` (echo an error, no effect),
    ``red_wingmen`` (extra red units starting on the red tank's hex, so several red units reach the
    objective together; an occupation of an objective the side already holds is refused with 1804),
    ``doomed`` ((call, obj_id): that unit is removed before the actions of that ``step`` call are
    applied, so its own action is refused with 203 and a shot at it with 516, whatever the action type)
    and ``engine_messages`` (refusals carry the engine's message for the code instead of a synthetic one)."""

    def __init__(self, play_steps: int = 30, never_done: bool = False, fail_at: Optional[int] = None,
                 noise_at: Optional[int] = None, refuse_moves: bool = False, red_wingmen: int = 0,
                 doomed: Optional[Tuple[int, int]] = None, engine_messages: bool = False) -> None:
        self.play_steps, self.never_done, self.fail_at = play_steps, never_done, fail_at
        self.noise_at, self.refuse_moves, self.red_wingmen = noise_at, refuse_moves, red_wingmen
        self.doomed, self.engine_messages = doomed, engine_messages
        self.destroyed: set = set()
        self.units: Dict[int, Dict[str, Any]] = {}
        self.cities: List[Dict[str, Any]] = []
        self.ended = {0: False, 1: False}
        self.stage, self.cur_step, self.calls = 1, 0, 0
        self.judge: List[Dict[str, Any]] = []
        self.echo: List[Dict[str, Any]] = []

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        seats = [player["seat"] for player in setup_info["player_info"]]
        assert seats == [SEATS[0], SEATS[1]], seats
        self.units = {RED_UNIT: syn.unit(RED_UNIT, 0, 102), BLUE_UNIT: syn.unit(BLUE_UNIT, 1, 807)}
        for n in range(self.red_wingmen):
            self.units[RED_UNIT + 1 + n] = syn.unit(RED_UNIT + 1 + n, 0, 102)
        self.cities = [syn.city(505)]
        return self.state()

    def _valid(self, faction: int) -> Dict[int, Any]:
        valid = {}
        for obj_id, unit in self.units.items():
            if unit["color"] != faction:
                continue
            actions: Dict[int, Any] = {}
            if not unit["move_path"]:
                actions[1] = None
            city = next((c for c in self.cities if c["coord"] == unit["cur_hex"]), None)
            if city is not None and city["flag"] != faction:
                actions[5] = None
            enemy = next((u for u in self.units.values() if u["color"] != faction), None)
            if enemy is not None and abs(enemy["cur_hex"] // 100 - unit["cur_hex"] // 100) + abs(
                    enemy["cur_hex"] % 100 - unit["cur_hex"] % 100) <= 2:
                actions[2] = [{"target_obj_id": enemy["obj_id"], "weapon_id": 43, "attack_level": 2}]
            valid[obj_id] = actions
        return valid

    def state(self) -> Dict[int, Any]:
        units = [copy.deepcopy(u) for _, u in sorted(self.units.items())]
        seats = {SEATS[f]: syn.seat_record(SEATS[f], f, sorted(i for i, u in self.units.items() if u["color"] == f),
                                           self.ended[f]) for f in (0, 1)}
        common = dict(units=units, seats=seats, stage=self.stage, cur_step=self.cur_step,
                      cities=copy.deepcopy(self.cities))
        red = syn.build_observation(valid_actions=self._valid(0), **common)
        blue = syn.build_observation(valid_actions=self._valid(1), **common)
        everything = syn.build_observation(valid_actions={**self._valid(0), **self._valid(1)}, all_seeing=True,
                                           **common)
        everything["actions"] = copy.deepcopy(self.echo)
        everything["judge_info"] = copy.deepcopy(self.judge)
        if self.noise_at is not None and self.calls >= self.noise_at:
            everything["scores"]["red_total"] = self.calls
        for obs in (red, blue, everything):
            obs["time"]["max_time"] = obs["time"]["max_step"] = self.play_steps
        return {0: red, 1: blue, -1: everything}

    def step(self, actions: List[Dict[str, Any]]):
        self.calls += 1
        if self.fail_at is not None and self.calls == self.fail_at:
            raise RuntimeError("synthetic engine failure")
        self.echo, self.judge = [], []
        if self.doomed is not None and self.calls == self.doomed[0] and self.doomed[1] in self.units:
            del self.units[self.doomed[1]]
            self.destroyed.add(self.doomed[1])
        for action in actions:
            error = self._apply(action)
            entry = {"cur_step": self.cur_step, "message": dict(action)}
            if error:
                message = ENGINE_MESSAGES.get(error, "synthetic refusal") if self.engine_messages else "synthetic refusal"
                entry["error"] = {"code": error, "message": message}
            self.echo.append(entry)
        if self.stage == 1 and all(self.ended.values()):
            self.stage = 2
        elif self.stage == 2:
            self.cur_step += 1
            for unit in self.units.values():
                if unit["move_path"]:
                    unit["cur_hex"] = unit["move_path"].pop(0)
        done = not self.never_done and self.stage == 2 and self.cur_step >= self.play_steps
        return self.state(), done

    def _apply(self, action: Dict[str, Any]) -> Optional[int]:
        faction = next(f for f, seat in SEATS.items() if seat == action.get("actor"))
        if action["type"] == 333:
            self.ended[faction] = True
            return None
        unit = self.units.get(action.get("obj_id"))
        if unit is None and action.get("obj_id") in self.destroyed:
            return 203
        if unit is None or unit["color"] != faction:
            return 11
        if action["type"] == 1:
            if self.refuse_moves or unit["move_path"]:
                return 21
            unit["move_path"] = list(action["move_path"])
            return None
        if action["type"] == 5:
            city = next((c for c in self.cities if c["coord"] == unit["cur_hex"]), None)
            if city is None:
                return 51
            if city["flag"] == faction:
                return 1804
            city["flag"] = faction
            return None
        if action["type"] == 2:
            if action.get("target_obj_id") in self.destroyed:
                return 516
            self.judge.append({"att_obj_id": unit["obj_id"], "target_obj_id": action["target_obj_id"],
                               "cur_step": self.cur_step, "wp_id": action["weapon_id"], "damage": 0})
            return None
        return 99

    def reset(self) -> None:
        self.units, self.cities = {}, []
