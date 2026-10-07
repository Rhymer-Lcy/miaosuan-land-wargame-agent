"""The Sprint 22 probe rules (``evaluation/s22_probe.py``): witness selection, the registered-difference and prefix
checks, the mechanism endpoints, the disposition order and the public guards. SYNTHETIC rows and actions only."""

from __future__ import annotations

import unittest
from typing import Any, Dict

from miaosuan_agent.evaluation import s22_probe as sp
from miaosuan_agent.experiments import t2_transport_p1 as t2

INF, CAR, OTHER = 900301, 900302, 900304


def row(game: str, **overrides: Any) -> Dict[str, Any]:
    out = {"game": game, "tier": 1, "full_step_capture": True, "inert_opponent": True, "reconstruction_exact": True,
           "trigger": True, "before_first_fire": True, "carrier_route_to_objective": True, "time_feasible": True,
           "destination_saturated_in_history": False, "destination_taken_by_another_unit_before_release": False,
           "free_flow_saving": 100, "infantry_cannot_arrive_on_foot": True, "trigger_step": 1}
    out.update(overrides)
    return out


class SelectionTest(unittest.TestCase):
    def test_every_minimum_excludes(self) -> None:
        for name in sp.MINIMUMS:
            with self.subTest(name):
                chosen = sp.select_witness([row("a", **{name: False})])
                self.assertIsNone(chosen["chosen"])
                self.assertEqual(chosen["failures"]["a"], [name])

    def test_ranking_order(self) -> None:
        pairs = [("destination_saturated_in_history", True, False),
                 ("destination_taken_by_another_unit_before_release", True, False),
                 ("free_flow_saving", 0, 1), ("infantry_cannot_arrive_on_foot", False, True),
                 ("trigger_step", 5, 4)]
        for name, worse, better in pairs:
            with self.subTest(name):
                rows = [row("a", **{name: worse}), row("b", **{name: better})]
                self.assertEqual(sp.select_witness(rows)["chosen"]["game"], "b")
        self.assertEqual(sp.select_witness([row("b"), row("a")])["chosen"]["game"], "a")
        # each criterion dominates every later one
        self.assertEqual(sp.select_witness([row("a", destination_saturated_in_history=True, trigger_step=0,
                                                free_flow_saving=999),
                                            row("b", trigger_step=9, free_flow_saving=1)])["chosen"]["game"], "b")
        self.assertEqual(sp.select_witness([row("a", free_flow_saving=0, trigger_step=0),
                                            row("b", infantry_cannot_arrive_on_foot=False,
                                                trigger_step=9)])["chosen"]["game"], "b")

    def test_tier_two_only_without_an_eligible_tier_one_game(self) -> None:
        rows = [row("a", tier=2, trigger_step=0), row("b", tier=1, trigger_step=9, free_flow_saving=0)]
        self.assertEqual(sp.select_witness(rows)["chosen"]["game"], "b")
        rows[1]["trigger"] = False
        self.assertEqual(sp.select_witness(rows)["chosen"]["game"], "a")

    def test_feasibility_boundary(self) -> None:
        self.assertTrue(sp.feasible(1, 100, 1 + 3 * 75 + 100 + 1))
        self.assertFalse(sp.feasible(1, 100, 1 + 3 * 75 + 100))


if __name__ == "__main__":
    unittest.main()
