"""A deterministic stand-in engine for the Sprint 12 screen tests. SYNTHETIC: invented map, units and numbers.

It reuses the PS-1 stand-in (``ps1_probe_engine.ProbeEnv``: four own ground units per hex, a hex time of three steps,
waiting in front of full hexes, occupation listed for a unit standing on an objective its side does not hold) with
another start: six stationary blue vehicles west of two neutral objectives, so that ``baseline-v2`` sends all six to
the nearer objective in its first play decision, the candidate selects four places and stages the other two on their
routes, the selected units arrive and occupy, and the staged units are later sent on. The red side has one unit that
never acts. ``play_steps`` is the game's ``max_step``.
"""

from __future__ import annotations

import itertools
import json
import pickle
from typing import Any, Dict, Optional, Tuple

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import ps1_model as pm
from miaosuan_agent.evaluation import s12_capture as cap
from miaosuan_agent.evaluation import s12_screen as sc
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from miaosuan_agent.experiments.t9_batch import BatchAgent

from . import ps1_probe_engine as pe

NEAR, FAR = 205, 209
START = {200: (930001, 930002, 930003, 930004), 300: (930011, 930012)}
CITIES = ({"coord": NEAR, "value": 50, "flag": -1, "name": "synthetic objective"},
          {"coord": FAR, "value": 80, "flag": -1, "name": "synthetic objective"})
FACTORIES = {INERT_ID: lambda: PolicyAgent(INERT_ID), sc.V3_ID: lambda: BatchAgent(),
             sc.V2_ID: lambda: ShootReservationAgent()}


class ScreenEnv(pe.ProbeEnv):
    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        units = [pm.Unit(u, hex_, pe.SPEED, 0) for hex_, ids in START.items() for u in ids]
        self.sim = pm.Simulation(units=units, edges_by_mode={m: pe.edges() for m in range(4)}, step=0,
                                 restart_after_wait=True, wait_at_entry=True)
        self.cities = [dict(c) for c in CITIES]
        return self.state()


def costs() -> MoveCosts:
    return MoveCosts.from_raw(pe.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")


def play_screen_game(blue: str = sc.V3_ID, play_steps: int = 90,
                     env: Optional[Any] = None) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """One stand-in game (red inert, blue ``blue``) under the screen's three observers; returns the record and the
    four capture contents as the files hold them (T9 capture, compact v3 capture, timeline compact, timeline windows)."""
    spec = GameSpec(game_id="synthetic.C3.s12", scenario_id="900000001", map_id="9000", condition="C3", red=INERT_ID,
                    blue=blue, repetition=1, max_time=play_steps)
    t9 = tc.T9Capture()
    compact = cap.V3CompactCapture((blue,))
    timeline = cap.V3Timeline((INERT_ID, blue), costs())
    ticks = itertools.count()
    record = play(env or (lambda: ScreenEnv(play_steps=play_steps)), FACTORIES, spec, pe.Inputs, PLAYERS,
                  clock=lambda: next(ticks) * 0.001, replay_policies={blue}, observer=tc.Tee(t9, compact, timeline))
    timeline_compact, windows = timeline.files()
    return (record, json.loads(t9.file()), json.loads(compact.files()[0]), json.loads(timeline_compact),
            pickle.loads(windows))
