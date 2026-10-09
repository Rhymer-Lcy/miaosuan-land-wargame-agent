"""A deterministic stand-in head-to-head engine for the Sprint 30 tests. SYNTHETIC: invented map, units and numbers.

Sprint 27's stand-in (``tests/fixtures/s27_engine.py``), unchanged in its interface and movement model, with one
change of the starting state: the blue tanks start stationary, fully stopped, on the 80-point objective ``NEAR``,
which blue already holds. ``baseline-v2`` therefore orders every one of them toward the unheld objective ``FAR`` at
its first play decision, which is the departure the Sprint 30 candidate acts on. Options as in Sprint 27, plus
``speeds`` (the blue tanks' ``basic_speed`` values, in unit order) and ``held`` (whether blue holds ``NEAR`` at the
start).
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from tests.fixtures import s27_engine as base

SEATS, RED, BLUE = base.SEATS, base.RED, base.BLUE
T1, T2, T3, T4 = base.T1, base.T2, base.T3, base.T4
RED_TANK = base.RED_TANK
START, NEAR, FAR, RED_HEX = base.START, base.NEAR, base.FAR, base.RED_HEX
Inputs = base.Inputs


class HeldEnv(base.StaggerEnv):
    def __init__(self, play_steps: int = 300, speeds: Sequence[int] = (36, 18, 36), held: bool = True,
                 **options: Any) -> None:
        super().__init__(play_steps=play_steps, n_blue=len(speeds), **options)
        self.speeds, self.held = tuple(speeds), held

    def setup(self, setup_info: Dict[str, Any]) -> Dict[int, Any]:
        super().setup(setup_info)
        blue = sorted(u for u, rec in self.units.items() if rec["color"] == BLUE and u not in self.fixed)
        for obj_id, speed in zip(blue, self.speeds):
            self.units[obj_id].update(cur_hex=NEAR, basic_speed=speed)
        if self.held:
            next(c for c in self.cities if c["coord"] == NEAR)["flag"] = BLUE
        self._stack()
        return self.state()
