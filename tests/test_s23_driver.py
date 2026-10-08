"""Stand-in rehearsal of the Sprint 23 study driver (``scripts/s23_t2_design.py``) on a SYNTHETIC side-game.

A scripted baseline-v2 stands in for the real one, so that the per-side pipeline runs end to end without any capture:
the fidelity counts, the recorded history, the funnel, the candidate's first divergence and its validity rule (an H0
side is valid only if baseline-v2 equalled the recorded actions before the trigger), the recorded-state episodes, every
projection, the public rows and the sanitizer, the consistency checks and the known answers. Nothing here reads the
evaluation server's private data.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent.evaluation import s23_design as sd
from miaosuan_agent.experiments import t2_transport_x1 as x1
from tests import test_t2_transport_p1 as tt
from tests import test_t2_transport_x1 as tx

ROOT = Path(__file__).resolve().parents[1]
SEAT, RED = tx.SEAT, tx.RED
INF, CAR, OTHER = tx.INF, tx.CAR, tx.OTHER
START, DEST, FAR = tx.START, tx.DEST, tx.FAR


def driver():
    spec = importlib.util.spec_from_file_location("s23_driver_test", ROOT / "scripts" / "s23_t2_design.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DRIVER = driver()
CAR_FF = tx.ff("ifv", START, DEST)
ARRIVE, ORDER, HELD = CAR_FF, CAR_FF + 10, 200


def world(k: int) -> Dict[str, Any]:
    """Decision k: deployment at 0, the trigger state at 1 (step 0), then both units moving; the carrier stands on
    the destination from step ARRIVE; the destination is the side's from step HELD."""
    step = max(0, k - 1)
    inf = tt.unit(INF, START, kind="infantry", **({} if k <= 1 else {"move_path": tt.route(START, DEST, 1)}))
    if k <= 1:
        car = tt.unit(CAR, START)
    elif step < ARRIVE:
        car = tt.unit(CAR, 303, move_path=tt.route(303, DEST))
    else:
        car = tt.unit(CAR, DEST)
    valid = {INF: {1: None, 3: [{"target_obj_id": CAR}]}, CAR: {1: None}} if k <= 1 else {}
    return tt.raw_observation([inf, car, tt.unit(OTHER, START, kind="tank")], (), valid, cur_step=step,
                              stage=1 if k == 0 else 2, held=(DEST,) if step >= HELD else ())


def scripted(k: int) -> List[Dict[str, Any]]:
    if k == 1:
        return [tx.move(OTHER, START, FAR), tx.move(INF, START, DEST, 1), tx.move(CAR, START, DEST)]
    if k - 1 == ORDER:
        return [tx.move(CAR, DEST, FAR)]
    return []


def side(population: str = "HI", recorded_differs_at: int = -1) -> Dict[str, Any]:
    stream = ((world(k), scripted(k) if k != recorded_differs_at else [{"x": 1}], None) for k in range(400))
    calls = iter(range(400))

    def decide(observation, seat, faction, memory):
        return scripted(next(calls))
    job = {"population": population, "game": "1930331196.C3.synthetic"}
    return DRIVER.run_side(job, "1930331196", SEAT, RED, stream, decide, x1.router_free_flow(tt.ROUTER), tx._raw_ff,
                           False)


class StandInTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.side = side()

    def test_fidelity_counts_and_first_divergence(self) -> None:
        s = self.side
        self.assertEqual((s["decisions"], s["play_decisions"], s["baseline_v2_differs_from_recorded"], s["problems"]),
                         (400, 399, 0, []))
        self.assertEqual((s["first_trigger_decision"], s["first_trigger_valid"], len(s["first_batch"])), (1, True, 1))
        self.assertEqual(s["first_batch"][0]["pair"], (INF, CAR))
        self.assertEqual(s["pre_trigger_certificates"], 0)
        self.assertEqual(s["funnel"]["selected_pair_decisions"], 1)
        self.assertEqual(s["distinct"]["outcome_selected"], 1)
        self.assertEqual(s["funnel"]["co_located_pair_decisions"], 1)

    def test_projections(self) -> None:
        e = self.side["first_batch"][0]
        self.assertEqual((e["projected_carrier_arrival"], e["projected_delivery"]), (75 + CAR_FF, 225 + CAR_FF))
        self.assertEqual(e["role"], "B" if 225 + CAR_FF >= HELD else "A")
        self.assertEqual((e["carrier_arrived_in_history"], e["first_move_delay"], e["claimant_elsewhere"]),
                         (True, 10, True))
        self.assertFalse(e["saturated_at_arrival"])
        self.assertEqual(e["projected_suppressed_decisions"], 2 * 75 - 10)

    def test_public_rows_pass_the_sanitizer(self) -> None:
        s = self.side
        row = DRIVER.public_episode(s, s["episodes"][0], s["labels"])
        self.assertEqual(row["destination"], "7-point objective A" if DEST < FAR else "7-point objective B")
        summary = DRIVER.summary([dict(row, first_divergence=True)])
        self.assertEqual((summary["episodes"], summary["claimant_elsewhere"]), (1, 1))
        self.assertEqual(sd.public_problems({"row": row, "summary": summary}, s["private_values"]), [])
        self.assertTrue(sd.public_problems({"row": dict(row, note=f"unit {INF}")}, s["private_values"]))

    def test_h0_validity_requires_baseline_equal_before_the_trigger(self) -> None:
        early = side("H0", recorded_differs_at=0)
        self.assertEqual((early["first_difference_from_recorded"], early["first_trigger_valid"]), (0, False))
        late = side("H0", recorded_differs_at=5)
        self.assertEqual((late["first_difference_from_recorded"], late["first_trigger_valid"]), (5, True))
        same = side("H0", recorded_differs_at=1)  # a difference AT the trigger decision leaves the state on-policy
        self.assertEqual((same["first_difference_from_recorded"], same["first_trigger_valid"]), (1, True))

    def test_consistency_and_known_answers(self) -> None:
        sides = [dict(self.side, population="HI", decisions=1, baseline_v2_differs_from_recorded=0)] * 3
        checks = DRIVER.consistency(sides)
        self.assertTrue(checks["HI baseline-v2 reconstruction equals the recorded seat"]["equal"])
        self.assertFalse(DRIVER.consistency(sides[:2])["HI baseline-v2 reconstruction equals the recorded seat"]["equal"])
        witness = {"rows": [{"game": self.side["game"], "tier": 1, "trigger": True, "trigger_decision": 1,
                             "destination": "x", "infantry_own_objective": "x"}]}
        reference = {"triggers": {self.side["game"]: {"pair": [INF, CAR]}}}
        self.assertTrue(DRIVER.known_answers([self.side], witness, reference)[self.side["game"]]["agrees"])
        witness["rows"][0]["infantry_own_objective"] = "y"
        self.assertFalse(DRIVER.known_answers([self.side], witness, reference)[self.side["game"]]["agrees"])


if __name__ == "__main__":
    unittest.main()
