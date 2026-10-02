"""A deterministic stand-in engine for the PS-1 probe tests. SYNTHETIC: invented map, units and numbers.

Its movement core is the frozen post-hoc model (``evaluation/ps1_model.py`` with M1b and M1c): four own ground units
per hex, a hex time of ``720 / basic_speed`` steps on the uniform synthetic grid, waiting in front of full hexes. The
game forms a deadlock shaped like the Sprint 2 one within its first steps, by movement: four blue units enter a
blue-held objective on their way on through the neighbouring hex while four others enter that neighbour bound for the
objective, and two more follow behind them; every unit of the deadlock has thus moved before it (as in a real game,
where the stall bookkeeping has an observed progress event for each). The red side has one unit that never acts. The interface shape follows engine 4.1.0 (``setup`` / ``step`` / ``reset``, the state mapping with keys 0,
1 and -1, deployment ending when both seats send 333, every received action echoed in the all-seeing ``actions``
field, with an error when refused).

How the stand-in answers a stop (action 10) is an option, so each alternative a probe must recognise can be produced:
``stop`` is one of ``in place`` (the documented reading: the move is dropped at once and a transition of
``transition`` steps follows, during which nothing is listed; ``move_to_stop_remain_time`` counts down),
``refused`` (an error, no effect), ``ignored`` (no error, no effect), ``enter`` (the unit first enters its next hex,
over the stacking limit, then transitions); ``per_unit`` overrides it for single units. ``relist`` False never lists
the move action again after a stop; ``refuse_moves_after`` refuses every move order from that cur_step on;
``uncounted`` lets units enter a hex whose four occupants include transitioning units (they do not count);
``uncounted_after`` does so only from that many steps after the unit's stop (so waiting units are first seen
waiting, then restart);
``fill`` (cur_step, hex, count) puts that many idle blue units into a hex at that step; ``corridor`` restricts the
map to the dead-end row 205 to 209, so no deadlocked group can back off; ``rewrite_stop`` rewrites the type of every
received stop action in place to that value after applying it, as engine 4.1.0 does to a deployment split.
"""

from __future__ import annotations

import copy
import itertools
import json
import pickle
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import ps1_model as pm
from miaosuan_agent.evaluation import ps1_probe as pp
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
from miaosuan_agent.experiments.deployment_split import CANDIDATE_ID as SPLIT_ID, DeploymentSplitAgent
from miaosuan_agent.experiments.ps1_probe_hook import PROBE_ID, ProbeAgent

from . import synthetic as syn

SEATS = {0: 1, 1: 11}
RED, BLUE = 0, 1
SPEED = 240.0  # tau = 720 / 240 = 3 steps per hex on the uniform grid
OBJECTIVE, NEIGHBOUR, BEHIND, FAR = 205, 206, 207, 209
OCCUPANTS = (910001, 910002, 910003, 910004)
WAITERS = (910011, 910012, 910013, 910014)
BEHIND_UNITS = (910021, 910022)
RED_UNIT = 920001
CITIES = ({"coord": OBJECTIVE, "value": 50, "flag": BLUE, "name": "synthetic objective"},
          {"coord": FAR, "value": 80, "flag": -1, "name": "synthetic objective"})


CORRIDOR = (205, 206, 207, 208, 209)


def cost_data(corridor: bool = False) -> List[Any]:
    data = syn.cost_data()
    if corridor:
        for mode in data:
            for r, row in enumerate(mode):
                for c, cell in enumerate(row):
                    h = r * 100 + c
                    keep = {n: v for n, v in cell.items() if h in CORRIDOR and n in CORRIDOR}
                    cell.clear()
                    cell.update(keep)
    return data


def edges(corridor: bool = False) -> Dict[int, Dict[int, float]]:
    grid = cost_data(corridor)[0]
    return {r * 100 + c: dict(cell) for r, row in enumerate(grid) for c, cell in enumerate(row)}


class ProbeEnv:
    def __init__(self, play_steps: int = 200, stop: str = "in place", transition: int = 75, relist: bool = True,
                 per_unit: Optional[Dict[int, str]] = None, refuse_moves_after: Optional[int] = None,
                 uncounted: bool = False, fill: Optional[Tuple[int, int, int]] = None, corridor: bool = False,
                 rewrite_stop: Optional[int] = None, uncounted_after: Optional[int] = None) -> None:
        self.corridor, self.rewrite_stop, self.uncounted_after = corridor, rewrite_stop, uncounted_after
        self.stopped_at: Dict[int, int] = {}
        self.play_steps, self.stop, self.transition, self.relist = play_steps, stop, transition, relist
        self.per_unit, self.refuse_moves_after, self.uncounted, self.fill = per_unit or {}, refuse_moves_after, uncounted, fill
        self.stage, self.cur_step = 1, 0
        self.ended = {RED: False, BLUE: False}
        self.echo: List[Dict[str, Any]] = []
        self.stopped: Dict[int, int] = {}  # unit -> cur_step its transition ends
        self.never_relist: set = set()
        self.sim: Optional[pm.Simulation] = None
        self.cities: List[Dict[str, Any]] = []

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        seats = [player["seat"] for player in setup_info["player_info"]]
        assert seats == [SEATS[RED], SEATS[BLUE]], seats
        units = ([pm.Unit(u, 204, SPEED, 0, (OBJECTIVE, NEIGHBOUR, BEHIND, 208, FAR), ready_at=3) for u in OCCUPANTS]
                 + [pm.Unit(u, BEHIND, SPEED, 0, (NEIGHBOUR, OBJECTIVE), ready_at=3) for u in WAITERS]
                 + [pm.Unit(u, 208, SPEED, 0, (BEHIND, NEIGHBOUR, OBJECTIVE), waiting=True) for u in BEHIND_UNITS])
        self.sim = pm.Simulation(units=units, edges_by_mode={m: edges(self.corridor) for m in range(4)}, step=0,
                                 restart_after_wait=True, wait_at_entry=True)
        self.cities = [dict(c) for c in CITIES]
        return self.state()

    # ---- observation
    def _record(self, u: pm.Unit) -> Dict[str, Any]:
        transition = max(0, self.stopped.get(u.uid, 0) - self.cur_step)
        speed = 0 if (not u.path or u.waiting or u.ready_at is None) else round(1 / pm.hex_time(SPEED, 1), 6)
        record = syn.unit(u.uid, BLUE, u.hex, move_path=u.path)
        record.update(basic_speed=SPEED, speed=speed, blood=1, on_board=0, keep=0, stop=1 if transition else 0,
                      move_to_stop_remain_time=transition, can_to_move=0 if transition else 1)
        return record

    def _valid(self, u: pm.Unit) -> Dict[int, Any]:
        if u.path:
            return {10: None}
        if self.cur_step < self.stopped.get(u.uid, 0) or u.uid in self.never_relist:
            return {}
        actions: Dict[int, Any] = {1: None}
        city = next((c for c in self.cities if c["coord"] == u.hex), None)
        if city is not None and city["flag"] != BLUE:
            actions[5] = None
        return actions

    def state(self) -> Dict[int, Any]:
        blue = [self._record(u) for u in sorted(self.sim.units, key=lambda x: x.uid)]
        red = syn.unit(RED_UNIT, RED, 909)
        red.update(basic_speed=SPEED, speed=0, blood=1, on_board=0, keep=0)
        units = blue + [red]
        seats = {SEATS[RED]: syn.seat_record(SEATS[RED], RED, [RED_UNIT], self.ended[RED]),
                 SEATS[BLUE]: syn.seat_record(SEATS[BLUE], BLUE, sorted(u.uid for u in self.sim.units), self.ended[BLUE])}
        valid_blue = {u.uid: self._valid(u) for u in self.sim.units}
        common = dict(units=units, seats=seats, stage=self.stage, cur_step=self.cur_step, cities=copy.deepcopy(self.cities))
        obs_red = syn.build_observation(valid_actions={RED_UNIT: {}}, **common)
        obs_blue = syn.build_observation(valid_actions=valid_blue, **common)
        everything = syn.build_observation(valid_actions={**valid_blue, RED_UNIT: {}}, all_seeing=True, **common)
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
            if self.fill is not None and self.cur_step == self.fill[0]:
                for n in range(self.fill[2]):
                    self.sim.units.append(pm.Unit(930001 + n, self.fill[1], SPEED, 0))
            self._advance()
            self.cur_step += 1
        done = self.stage == 2 and self.cur_step >= self.play_steps
        return self.state(), done

    def _advance(self) -> None:
        sim = self.sim
        if self.uncounted or self.uncounted_after is not None:  # transitioning units invisible to the stacking check
            delay = 0 if self.uncounted else self.uncounted_after
            hidden = [u for u in sim.units if self.cur_step < self.stopped.get(u.uid, 0)
                      and self.cur_step >= self.stopped_at.get(u.uid, 0) + delay]
            sim.units = [u for u in sim.units if u not in hidden]
            sim.advance()
            sim.units = sim.units + hidden
        else:
            sim.advance()

    def _apply(self, action: Dict[str, Any]) -> Optional[int]:
        faction = next(f for f, seat in SEATS.items() if seat == action.get("actor"))
        if action["type"] == 333:
            self.ended[faction] = True
            return None
        try:
            u = self.sim.unit(action.get("obj_id"))
        except KeyError:
            return 11
        if action["type"] == 10:
            mode = self.per_unit.get(u.uid, self.stop)
            if mode == "refused" or not u.path:
                return 101
            if mode == "ignored":
                return None
            if mode == "enter":
                self.sim._put(replace(u, hex=u.path[0], path=(), waiting=False, ready_at=None))
            else:
                self.sim.step = self.cur_step
                self.sim.order_stop(u.uid)
            self.stopped[u.uid] = self.cur_step + self.transition
            self.stopped_at[u.uid] = self.cur_step
            self.sim._put(replace(self.sim.unit(u.uid), stopped_until=self.stopped[u.uid]))
            if not self.relist:
                self.never_relist.add(u.uid)
            if self.rewrite_stop is not None:
                action["type"] = self.rewrite_stop
            return None
        if action["type"] == 1:
            if (u.path or self.cur_step < self.stopped.get(u.uid, 0)
                    or (self.refuse_moves_after is not None and self.cur_step >= self.refuse_moves_after)):
                return 21
            self.sim.step = self.cur_step
            try:
                self.sim.order_move(u.uid, tuple(action["move_path"]))
            except pm.ModelError:
                return 22
            return None
        if action["type"] == 5:
            city = next((c for c in self.cities if c["coord"] == u.hex), None)
            if city is None or city["flag"] == BLUE:
                return 1804
            city["flag"] = BLUE
            return None
        return 99

    def reset(self) -> None:
        self.sim = None


class Inputs:
    """Setup inputs of the stand-in (synthetic scenario, uniform costs)."""

    scenario, basic, see = {}, {}, {}
    cost = cost_data()


FACTORIES = {INERT_ID: lambda: PolicyAgent(INERT_ID), PROBE_ID: lambda: ProbeAgent(),
             SPLIT_ID: lambda: DeploymentSplitAgent()}


def play_probe(blue: str = PROBE_ID, **options: Any) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """One stand-in game (red inert, ``blue`` the hooked or the plain candidate) with the probe capture; returns the
    record (with the harness block the runner would add), the compact log and the snapshots, as the files hold them."""
    steps = options.get("play_steps", 200)
    spec = GameSpec(game_id="synthetic.C3.p1", scenario_id="900000001", map_id="9000", condition="C3", red=INERT_ID,
                    blue=blue, repetition=1, max_time=steps)
    inputs = type("CorridorInputs", (Inputs,), {"cost": cost_data(True)}) if options.get("corridor") else Inputs
    capture = pp.ProbeCapture((blue,))
    ticks = itertools.count()
    record = play(lambda: ProbeEnv(**options), FACTORIES, spec, inputs, PLAYERS, clock=lambda: next(ticks) * 0.001,
                  replay_policies={blue}, observer=capture)
    record["harness"] = {"runtime": pp.RUNTIME, "capture": {"sample_every": pp.SAMPLE_EVERY}, "policy_sources": {}}
    compact, windows = capture.files()
    return record, json.loads(compact), pickle.loads(windows)


def manifest(predicted_k: int = 23, group: int = 4) -> Dict[str, Any]:
    """The parts of the registered manifest the analyses read, with the stand-in's own prediction."""
    return {"policies": {}, "execution": {"runtime": pp.RUNTIME},
            "parameters": {"predicted_trigger_k": predicted_k, "predicted_group_size": group}}
