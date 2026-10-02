"""A deterministic stand-in engine for the T7 mechanism probe tests. SYNTHETIC: invented map, units and numbers.

The world: a 24 x 24 grid with uniform costs; two objectives held by blue from the start, so ``baseline-v2`` leaves
blue's units idle once they stand still; blue has a tank and an infantry fighting vehicle on one objective and an
infantry squad beside it; red has two vehicles in a screened corner that no unit outside it can see (line of sight is
a synthetic table) and never acts (the inert control). Engine-scripted events move red units, flip objectives, and
suppress units, so the registered policies meet the situations the probe's endpoints describe without being forced
to act. The interface shape follows engine 4.1.0 (``setup`` / ``step`` / ``reset``; the state mapping with keys 0, 1
and -1; deployment ending when both seats send 333; every received action echoed in the all-seeing ``actions``
field, with an error when refused; ``judge_info`` holding the step's shot records).

How the stand-in answers a concealment order (action 6, target_state 4) is an option:

* ``conceal``: ``documented`` (accepted; ``change_state_remain_time`` counts down from ``transition`` and the unit
  is concealed, move_state 4, when it reaches 0), ``refused`` (an error, no effect), ``ignored`` (no error, no
  effect), ``instant`` (move_state 4 at once with no timer), ``no timer`` (concealed after ``transition`` steps, the
  timer field never positive), ``lock`` (accepted; ``flag_force_stop`` 1 and nothing listed for the rest of the game);
* ``timer_delay``: steps before the timer becomes visible (0: in the next observation);
* ``exit``: what a move or shot of a concealed unit does: ``free`` (concealment ends at once, the action executes)
  or ``delayed`` (the unit stays concealed and inert for ``exit_delay`` steps first);
* ``during``: what a move ordered during the transition does: ``refused``, ``deferred`` (executed when the transition
  ends) or ``executed`` (the transition is abandoned);
* ``transition_listing``: ``empty`` (nothing listed during the transition) or ``kept`` (move still listed);
* ``concealed_listing``: the action types listed for a concealed unit besides 6 (default move and, for vehicles,
  weapon lock);
* ``visibility``: how red's view lists concealed blue units: ``documented`` (the published rules), ``ignored``
  (concealment has no effect) or ``hidden`` (a concealed unit is never listed);
* ``suppress``: (cur_step, unit, steps) puts the unit under suppression (keep 1); ``suppress_interrupts`` whether that
  ends a concealment transition; ``red_moves``: (cur_step, unit, hex) teleports a red unit; ``flips``: (cur_step,
  objective, flag); ``shoot``: blue vehicles list a shot at red units they see within 10 hexes; ``elevations`` and
  ``forest``: map overrides; ``play_steps``: the game's length; ``rewrite_conceal`` rewrites the type of every accepted
  concealment order in place after applying it, as engine 4.1.0 does to a deployment split; with ``shoot`` and the
  ``kept`` transition listing a tank also lists its shots during the transition (documented: it may fire, which ends
  the transition); ``blank``: (cur_step, unit, steps) lists nothing for the unit during those steps;
  ``no_echo`` leaves concealment orders out of the feedback; ``stop_transition``: the length of a move-to-stop
  transition after an arrival (``move_to_stop_remain_time`` counts down, nothing listed); ``conceal`` ``state first``
  sets move_state 4 at the order while the timer counts down; ``exit`` ``kept`` executes a concealed unit's move
  without ending concealment.
"""

from __future__ import annotations

import copy
import itertools
import json
import pickle
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import t7_probe as tp
from miaosuan_agent.evaluation import t7_visibility as tv
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from miaosuan_agent.experiments.t7_concealment import CANDIDATE_ID, ConcealmentAgent

from . import synthetic as syn

ROWS = COLS = 24
SEATS = {0: 1, 1: 11}
RED, BLUE = 0, 1
SPEED = 240.0  # 3 steps per hex
HEX_TIME = 3
OBJ_A, OBJ_B = 1010, 1414
TANK, IFV, SQUAD = 910001, 910002, 910003
RED_1, RED_2 = 920001, 920002
SCREEN = frozenset({0, 1, 2, 100, 101, 102})  # hexes that see nothing outside and are seen from nothing outside
WEAPON = 9001


def los_table(screen: frozenset = SCREEN) -> List[np.ndarray]:
    """Line of sight for modes 0 to 2: every pair sees each other unless exactly one end is in the screen."""
    inside = np.zeros((ROWS, COLS), dtype=bool)
    for h in screen:
        inside[divmod(h, 100)] = True
    a = inside[:, :, None, None]
    b = inside[None, None, :, :]
    table = ~(a ^ b)
    return [table.copy() for _ in range(3)]


def basic_data(elevations: Optional[Dict[int, int]] = None, forest: Sequence[int] = ()) -> Dict[str, Any]:
    elev = elevations or {}
    return {"map_data": [[{"elev": elev.get(r * 100 + c, 0), "cond": 1 if r * 100 + c in forest else 0,
                           "roads": [0] * 6, "rivers": [0] * 6, "neighbors": []} for c in range(COLS)]
                         for r in range(ROWS)]}


@dataclass
class Unit:
    uid: int
    color: int
    kind: int  # 1 infantry, 2 vehicle
    sub_type: int
    hex: int
    a1: int = 0
    path: List[int] = field(default_factory=list)
    progress: int = 0
    move_state: int = 0
    timer: int = 0          # the documented change_state_remain_time
    hidden_timer: int = 0   # the stand-in's own countdown (option "no timer" and the timer delay)
    total: int = 0          # the length of the current transition
    mts: int = 0            # move_to_stop_remain_time after an arrival
    keep: int = 0
    lock: bool = False
    stop: int = 1
    deferred: Optional[List[int]] = None
    exit_wait: int = 0
    exit_path: Optional[List[int]] = None


class T7Env:
    def __init__(self, play_steps: int = 300, conceal: str = "documented", transition: int = 75,
                 timer_delay: int = 0, exit: str = "free", exit_delay: int = 75, during: str = "refused",
                 transition_listing: str = "empty", concealed_listing: Optional[Tuple[int, ...]] = None,
                 visibility: str = "documented", suppress: Sequence[Tuple[int, int, int]] = (),
                 suppress_interrupts: bool = True, red_moves: Sequence[Tuple[int, int, int]] = (),
                 flips: Sequence[Tuple[int, int, int]] = (), shoot: bool = False,
                 elevations: Optional[Dict[int, int]] = None, forest: Sequence[int] = (),
                 blue_start: Optional[Dict[int, int]] = None, rewrite_conceal: Optional[int] = None,
                 blank: Sequence[Tuple[int, int, int]] = (), no_echo: bool = False,
                 stop_transition: int = 0) -> None:
        self.rewrite_conceal, self.blank = rewrite_conceal, list(blank)
        self.no_echo, self.stop_transition = no_echo, stop_transition
        self.play_steps, self.conceal, self.transition, self.timer_delay = play_steps, conceal, transition, timer_delay
        self.exit, self.exit_delay, self.during = exit, exit_delay, during
        self.transition_listing, self.concealed_listing, self.visibility = transition_listing, concealed_listing, visibility
        self.suppress, self.suppress_interrupts = list(suppress), suppress_interrupts
        self.red_moves, self.flips, self.shoot = list(red_moves), list(flips), shoot
        self.map = tv.MapData(basic_data(elevations, forest), los_table())
        self.blue_start = blue_start or {}
        self.stage, self.cur_step = 1, 0
        self.ended = {RED: False, BLUE: False}
        self.echo: List[Dict[str, Any]] = []
        self.judge: List[Dict[str, Any]] = []
        self.units: Dict[int, Unit] = {}
        self.cities: List[Dict[str, Any]] = []

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        seats = [player["seat"] for player in setup_info["player_info"]]
        assert seats == [SEATS[RED], SEATS[BLUE]], seats
        start = {TANK: OBJ_A, IFV: OBJ_A, SQUAD: 1111, **self.blue_start}
        self.units = {TANK: Unit(TANK, BLUE, 2, 0, start[TANK], a1=1), IFV: Unit(IFV, BLUE, 2, 1, start[IFV]),
                      SQUAD: Unit(SQUAD, BLUE, 1, 0, start[SQUAD]),
                      RED_1: Unit(RED_1, RED, 2, 0, 1), RED_2: Unit(RED_2, RED, 2, 1, 101)}
        self.cities = [syn.city(OBJ_A, BLUE, 50), syn.city(OBJ_B, BLUE, 80)]
        return self.state()

    # ---- observation
    def _transitioning(self, u: Unit) -> bool:
        return u.timer > 0 or u.hidden_timer > 0

    def _record(self, u: Unit) -> Dict[str, Any]:
        record = syn.unit(u.uid, u.color, u.hex, unit_type=u.kind, move_state=u.move_state, move_path=u.path)
        moving = bool(u.path) and u.exit_wait == 0
        record.update(sub_type=u.sub_type, basic_speed=SPEED, speed=round(1 / HEX_TIME, 6) if moving else 0, blood=1,
                      on_board=0, keep=u.keep, stop=0 if u.path else 1, change_state_remain_time=u.timer,
                      move_to_stop_remain_time=u.mts, weapon_unfold_time=0, get_on_remain_time=0, get_off_remain_time=0,
                      flag_force_stop=1 if u.lock else 0, A1=u.a1, launcher=None, can_to_move=1, tire=0,
                      weapon_unfold_state=1, carry_weapon_ids=[WEAPON])
        return record

    def _valid(self, u: Unit) -> Dict[int, Any]:
        if u.color == RED:
            return {}
        if u.lock or any(start <= self.cur_step < start + steps and uid == u.uid for start, uid, steps in self.blank):
            return {}
        if u.path:
            return {10: None}
        if u.mts:
            return {}
        if self._transitioning(u):
            if self.transition_listing == "empty":
                return {}
            actions = {1: None}
            if self.shoot and u.a1:
                targets = [r for r in self._listed_by(BLUE) if tv.hex_distance(u.hex, self.units[r].hex) <= 10]
                if targets:
                    actions[2] = [{"target_obj_id": r, "weapon_id": WEAPON, "attack_level": 5} for r in sorted(targets)]
            return actions
        if u.exit_wait:
            return {}
        if u.keep:
            return {1: None, 6: [{"target_state": 5}]} if u.kind == 2 else {1: None, 6: [{"target_state": 2}]}
        actions: Dict[int, Any] = {}
        if u.move_state == 4:
            listed = self.concealed_listing if self.concealed_listing is not None else (
                (1, 11) if u.kind == 2 else (1,))
            for t in listed:
                actions[t] = None
            actions[6] = [{"target_state": 5}] if u.kind == 2 else [{"target_state": 2}, {"target_state": 3}]
        else:
            actions[1] = None
            actions[6] = ([{"target_state": 4}, {"target_state": 5}] if u.kind == 2
                          else [{"target_state": 2}, {"target_state": 3}, {"target_state": 4}])
            if u.kind == 2:
                actions[11] = None
        city = next((c for c in self.cities if c["coord"] == u.hex), None)
        if city is not None and city["flag"] != BLUE:
            actions[5] = None
        if self.shoot and u.kind == 2:
            targets = [r for r in self._listed_by(BLUE) if tv.hex_distance(u.hex, self.units[r].hex) <= 10]
            if targets:
                actions[2] = [{"target_obj_id": r, "weapon_id": WEAPON, "attack_level": 5} for r in sorted(targets)]
        return actions

    def _dict(self, u: Unit) -> Dict[str, Any]:
        return {"obj_id": u.uid, "type": u.kind, "sub_type": u.sub_type, "cur_hex": u.hex}

    def _listed_by(self, faction: int) -> List[int]:
        """Enemy units listed in ``faction``'s view."""
        observers = [self._dict(u) for u in self.units.values() if u.color == faction]
        out = []
        for u in self.units.values():
            if u.color == faction:
                continue
            target = self._dict(u)
            concealed = u.move_state == 4 and u.timer == 0
            if not concealed or self.visibility == "ignored":
                seen = any(tv.sees_unconcealed(self.map, o, target) for o in observers)
            elif self.visibility == "hidden":
                seen = False
            else:
                label, _ = tv.classify(self.map, observers, target)
                seen = label in (tv.EXPECTED_VISIBLE, tv.EXCEPTION_VISIBLE)
            if seen:
                out.append(u.uid)
        return sorted(out)

    def state(self) -> Dict[int, Any]:
        records = {uid: self._record(u) for uid, u in sorted(self.units.items())}
        valid = {uid: self._valid(u) for uid, u in sorted(self.units.items())}
        own = {f: [uid for uid, u in sorted(self.units.items()) if u.color == f] for f in (RED, BLUE)}
        seats = {SEATS[f]: syn.seat_record(SEATS[f], f, own[f], self.ended[f]) for f in (RED, BLUE)}
        common = dict(seats=seats, stage=self.stage, cur_step=self.cur_step, cities=copy.deepcopy(self.cities))
        views = {}
        for f in (RED, BLUE):
            visible = own[f] + self._listed_by(f)
            views[f] = syn.build_observation(units=[records[u] for u in sorted(visible)],
                                             valid_actions={u: valid[u] for u in own[f]}, **common)
        everything = syn.build_observation(units=list(records.values()), valid_actions=dict(valid), all_seeing=True,
                                           **common)
        everything["actions"] = copy.deepcopy(self.echo)
        for obs in (views[RED], views[BLUE], everything):
            obs["time"]["max_time"] = obs["time"]["max_step"] = self.play_steps
            obs["judge_info"] = copy.deepcopy(self.judge)
        return {0: views[RED], 1: views[BLUE], -1: everything}

    # ---- dynamics
    def step(self, actions: List[Dict[str, Any]]):
        self.echo, self.judge = [], []
        for action in actions:
            error = self._apply(action)
            entry = {"cur_step": self.cur_step, "message": dict(action)}
            if error:
                entry["error"] = {"code": error, "message": "synthetic refusal"}
            if not (self.no_echo and action.get("target_state") == 4):
                self.echo.append(entry)
        if self.stage == 1 and all(self.ended.values()):
            self.stage = 2
        elif self.stage == 2:
            self._advance()
            self.cur_step += 1
            self._scripts()
        done = self.stage == 2 and self.cur_step >= self.play_steps
        return self.state(), done

    def _start_move(self, u: Unit, path: List[int]) -> None:
        u.path, u.progress, u.stop = list(path), 0, 0

    def _apply(self, action: Dict[str, Any]) -> Optional[int]:
        faction = next(f for f, seat in SEATS.items() if seat == action.get("actor"))
        if action["type"] == 333:
            self.ended[faction] = True
            return None
        u = self.units.get(action.get("obj_id"))
        if u is None or u.color != faction:
            return 11
        if action["type"] == 6:
            if action.get("target_state") != 4 or u.path or self._transitioning(u) or u.keep:
                return 31
            if self.conceal == "refused":
                return 32
            if self.conceal == "ignored":
                return None
            if self.conceal == "instant":
                u.move_state = 4
                return None
            if self.conceal == "lock":
                u.lock = True
                return None
            if self.conceal == "state first":
                u.move_state = 4
            u.hidden_timer = u.total = self.transition
            if self.rewrite_conceal is not None:
                action["type"] = self.rewrite_conceal
            return None
        if action["type"] == 1:
            if self._transitioning(u):
                if self.during == "refused":
                    return 41
                if self.during == "deferred":
                    u.deferred = list(action["move_path"])
                    return None
                u.timer = u.hidden_timer = 0
                self._start_move(u, action["move_path"])
                return None
            if u.move_state == 4:
                u.move_state = 4 if self.exit == "kept" else 0
                if self.exit == "delayed":
                    u.move_state, u.exit_wait, u.exit_path = 4, self.exit_delay, list(action["move_path"])
                    return None
            if u.path:
                return 42
            self._start_move(u, action["move_path"])
            return None
        if action["type"] == 2:
            target = action.get("target_obj_id")
            if target not in self.units or target not in self._listed_by(BLUE):
                return 516
            if self._transitioning(u) and not u.a1:
                return 43
            if self._transitioning(u) and u.a1:
                u.timer = u.hidden_timer = 0
            if u.move_state == 4:
                u.move_state = 0
            self.judge.append({"att_obj_id": u.uid, "target_obj_id": target, "damage": 0, "cur_step": self.cur_step,
                               "type": "direct"})
            return None
        if action["type"] == 5:
            city = next((c for c in self.cities if c["coord"] == u.hex), None)
            if city is None or city["flag"] == BLUE:
                return 1804
            city["flag"] = BLUE
            return None
        return 99

    def _advance(self) -> None:
        for u in self.units.values():
            if u.exit_wait:
                u.exit_wait -= 1
                if u.exit_wait == 0:
                    u.move_state = 0
                    self._start_move(u, u.exit_path or [])
            elif u.path:
                u.progress += 1
                if u.progress >= HEX_TIME:
                    u.hex, u.progress = u.path.pop(0), 0
                    if not u.path:
                        u.stop = 1
                        u.mts = self.stop_transition
            elif u.mts:
                u.mts -= 1
            if u.hidden_timer > 0:
                u.hidden_timer -= 1
                elapsed = u.total - u.hidden_timer
                visible = self.conceal in ("documented", "state first") and elapsed >= self.timer_delay + 1
                u.timer = u.hidden_timer if visible else 0
                if u.hidden_timer == 0:
                    u.timer = 0
                    u.move_state = 4
                    if u.deferred:
                        u.move_state = 0
                        self._start_move(u, u.deferred)
                        u.deferred = None

    def _scripts(self) -> None:
        for step, uid, steps in self.suppress:
            u = self.units[uid]
            if step == self.cur_step:
                u.keep = steps
                if self.suppress_interrupts and self._transitioning(u):
                    u.timer = u.hidden_timer = 0
            elif u.keep and step < self.cur_step:
                u.keep = max(0, steps - (self.cur_step - step))
        for step, uid, hex_ in self.red_moves:
            if step == self.cur_step:
                self.units[uid].hex = hex_
        for step, coord, flag in self.flips:
            if step == self.cur_step:
                next(c for c in self.cities if c["coord"] == coord)["flag"] = flag

    def reset(self) -> None:
        self.units = {}


class Inputs:
    """Setup inputs of the stand-in (synthetic scenario, uniform costs, synthetic map and line of sight)."""

    scenario: Dict[str, Any] = {}
    basic = basic_data()
    see = los_table()
    cost = syn.cost_data(ROWS, COLS)


FACTORIES = {INERT_ID: lambda: PolicyAgent(INERT_ID), CANDIDATE_ID: lambda: ConcealmentAgent(),
             tp.BASELINE_ID: lambda: ShootReservationAgent()}


def play_t7(red: str = INERT_ID, blue: str = CANDIDATE_ID, game_id: str = "synthetic.C3.pa",
            **options: Any) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """One stand-in game with the T7 capture; returns the record (with the harness block the runner would add), the
    compact log and the snapshots, as the files hold them."""
    steps = options.get("play_steps", 300)
    spec = GameSpec(game_id=game_id, scenario_id="900000001", map_id="9000", condition="C3", red=red, blue=blue,
                    repetition=1, max_time=steps)
    inputs = type("Inputs", (Inputs,), {"basic": basic_data(options.get("elevations"), options.get("forest", ()))})
    capture = tp.T7Capture(tuple(sorted({red, blue})))
    ticks = itertools.count()
    pinned = sorted({red, blue} - {INERT_ID})
    record = play(lambda: T7Env(**options), FACTORIES, spec, inputs, PLAYERS, clock=lambda: next(ticks) * 0.001,
                  replay_policies=set(pinned), observer=capture)
    record["harness"] = {"runtime": tp.RUNTIME, "capture": {"sample_every": tp.SAMPLE_EVERY,
                                                            "schema": tp.CAPTURE_SCHEMA},
                         "policy_sources": {p: "synthetic" for p in pinned}, "commit": "synthetic", "dirty": False}
    compact, windows = capture.files()
    return record, json.loads(compact), pickle.loads(windows)


def manifest(first_k: int = 1, units: int = 3) -> Dict[str, Any]:
    """The parts of the registered manifest the analyses read, for the stand-in."""
    return {"policies": {CANDIDATE_ID: {"policy_source": {"sha256": "synthetic"}},
                         tp.BASELINE_ID: {"policy_source": {"sha256": "synthetic"}}},
            "execution": {"runtime": tp.RUNTIME},
            "reference": {"predicted_orders": [{"k": first_k, "units": units}]}}
