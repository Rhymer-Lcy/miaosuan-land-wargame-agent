"""A stand-in engine for the Sprint 34 rehearsals: the MODEL WORLD (``evaluation.s34_world``) behind the engine's
``setup`` / ``step`` / ``reset`` interface, so that ``evaluation.game.play`` and the live observers run unchanged.

The state is the mapping form of engine 4.1.0 (keys 0 red, 1 blue, -1 all-seeing); the all-seeing view adds the
``actions`` echo (each received action, with ``error`` when the model refused it) and the director options. Scores
carry every field of the observed schema; with no combat, attack is 0 and the remaining force is never reduced.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.evaluation.s34_world import ModelWorld

DIRECTOR = {401: None, 402: None, 403: None, 404: None}


class ModelEnv:
    version = "s34-model-world"

    def __init__(self) -> None:
        self.world: Any = None
        self.seat_colour: Dict[int, int] = {}

    def _scores(self) -> Dict[str, int]:
        occupy = self.world.scores()
        out: Dict[str, int] = {}
        remain = {}
        for colour, side in ((0, "red"), (1, "blue")):
            units = [u for u in list(self.world.units.values()) + list(self.world.aboard.values()) if u["color"] == colour]
            remain[side] = sum(int(u.get("value") or 0) for u in units)
            out[f"{side}_occupy"] = occupy[f"{side}_occupy"]
            out[f"{side}_attack"] = 0
            out[f"{side}_remain"] = remain[side]
            out[f"{side}_remain_max"] = remain[side]
            out[f"{side}_total"] = out[f"{side}_occupy"] + remain[side]
        out["red_win"] = out["red_total"] - out["blue_total"]
        out["blue_win"] = -out["red_win"]
        return out

    def _state(self) -> Dict[int, Any]:
        red, blue = self.world.observation(0), self.world.observation(1)
        scores = self._scores()
        for view in (red, blue):
            view["scores"] = dict(scores)
        everything = dict(red)
        ids = set()
        operators: List[Mapping[str, Any]] = []
        for view in (red, blue):
            for u in view["operators"]:
                if u["obj_id"] not in ids and u["color"] in (0, 1):
                    own = u["color"] == (0 if view is red else 1)
                    if own:
                        operators.append(u)
                        ids.add(u["obj_id"])
        everything["operators"] = sorted(operators, key=lambda u: u["obj_id"])
        everything["passengers"] = red["passengers"] + blue["passengers"]
        everything["valid_actions"] = {**red["valid_actions"], **blue["valid_actions"], -1: dict(DIRECTOR)}
        everything["role_and_grouping_info"] = {**red["role_and_grouping_info"], **blue["role_and_grouping_info"]}
        echo = []
        for e in self.world.echo:
            echo.append(dict(e))
        for r in self.world.refused:
            if r["step"] == self.world.cur_step - 1 or (self.world.stage == 1 and r["step"] == self.world.cur_step):
                echo.append({"cur_step": r["step"], "message": dict(r["action"]),
                             "error": {"code": 999, "message": r["reason"]}})
        everything["actions"] = echo
        return {0: red, 1: blue, -1: everything}

    def setup(self, info: Mapping[str, Any]) -> Dict[int, Any]:
        costs = MoveCosts.from_raw(info["cost_data"])
        scenario = info["scenario_data"]
        self.world = ModelWorld(scenario, costs)
        self.seat_colour = {p["seat"]: p["faction"] for p in info["player_info"]}
        return self._state()

    def step(self, actions: List[Mapping[str, Any]]):
        by_colour: Dict[int, List[Mapping[str, Any]]] = {0: [], 1: []}
        for a in actions:
            by_colour[self.seat_colour[a["actor"]]].append(a)
        done = self.world.step(by_colour)
        return self._state(), done

    def reset(self) -> None:
        self.world = None
