"""A deterministic stand-in head-to-head engine for the Sprint 31 tests. SYNTHETIC: invented map, units and numbers.

Sprint 27's stand-in (``tests/fixtures/s27_engine.py``), unchanged in its interface and movement model, with the
documented stop transition modelled on the fields the K2 rule reads: when a move ends the unit gets ``stop`` 0 and
``move_to_stop_remain_time`` 75, counting down one per step; ``stop`` returns to 1 when the timer reaches 0
(``docs/T7_DESIGN.md``, B-2). Every unit also carries ``flag_force_stop`` and ``change_state_remain_time`` at 0.

The blue tanks start together on ``START``; both objectives are unheld, so ``baseline-v2`` sends them to the nearer one
(``NEAR``), one of them occupies it, and at the next decision ``baseline-v2`` orders them all on toward ``FAR`` while
they are still settling: the departure the Sprint 31 candidate acts on. Options as in Sprint 27, plus ``speeds`` (the
blue tanks' ``basic_speed`` values, in unit order).
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from tests.fixtures import s27_engine as base

SEATS, RED, BLUE = base.SEATS, base.RED, base.BLUE
T1, T2, T3, T4 = base.T1, base.T2, base.T3, base.T4
RED_TANK = base.RED_TANK
START, NEAR, FAR, RED_HEX = base.START, base.NEAR, base.FAR, base.RED_HEX
STOP_TRANSITION = base.STOP_TRANSITION
Inputs = base.Inputs


class SettleEnv(base.StaggerEnv):
    def __init__(self, play_steps: int = 400, speeds: Sequence[int] = (36, 18, 36), **options: Any) -> None:
        super().__init__(play_steps=play_steps, n_blue=len(speeds), **options)
        self.speeds = tuple(speeds)

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        super().setup(setup_info)
        for u in self.units.values():
            u.update(flag_force_stop=0, change_state_remain_time=0)
        blue = sorted(u for u, rec in self.units.items() if rec["color"] == BLUE and u not in self.fixed)
        for obj_id, speed in zip(blue, self.speeds):
            self.units[obj_id]["basic_speed"] = speed
        return self.state()

    def _advance(self) -> None:
        super()._advance()
        for u in self.units.values():
            u["stop"] = 0 if u["move_to_stop_remain_time"] > 0 else 1
