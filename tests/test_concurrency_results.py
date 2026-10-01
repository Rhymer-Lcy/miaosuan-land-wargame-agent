"""The committed results of the concurrency qualification, recomputed from their own public values.

Speedups, efficiencies, every criterion and the recommendation must follow from the per-tier figures in
results.json and the registered thresholds; the byte-identical regeneration from the private tier summaries
runs only where they exist.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import concurrency as cq

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / cq.PLAN_ID
TIERS = ROOT / "local" / "diagnostics" / cq.PLAN_ID / "tiers"


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads((DIRECTORY / "plan.json").read_text(encoding="utf-8"))
        cls.results = json.loads((DIRECTORY / "results.json").read_text(encoding="utf-8"))
        cls.tiers = {t["tier"]: t for t in cls.results["tiers"]}

    def test_results_cite_the_registered_plan(self) -> None:
        self.assertEqual(self.results["plan_sha256"], cq.digest(self.plan))
        self.assertEqual(self.results["plan_id"], cq.PLAN_ID)

    def test_tiers_ran_in_order_and_completed(self) -> None:
        self.assertEqual(list(self.tiers), ["S", "w01", "w02", "w04", "w08", "w16", "w24"])
        for name, tier in self.tiers.items():
            spec = cq.tier_spec(self.plan, name)
            self.assertEqual((tier["workers"], tier["session_mode"]), (spec["workers"], spec["session_mode"]))
            self.assertEqual(tier["games_planned"], len(cq.tier_queue(self.plan, name)))
            self.assertEqual(tier["games_completed"], tier["games_planned"])
            self.assertEqual(tier["ledger"]["sessions"], tier["games_planned"])
            self.assertFalse(tier["contended"])
            self.assertTrue(tier["safety_pass"] and tier["independence_pass"] and tier["engine_state_pass"]
                            and tier["ledger_pass"], name)
            ind = tier["independence"]
            self.assertEqual(ind["deterministic_identical"], ind["deterministic_games"])
            self.assertEqual(ind["stochastic_prefix_equal"], ind["stochastic_games"])
            self.assertEqual(ind["deterministic_games"] + ind["stochastic_games"], tier["games_planned"])
            self.assertEqual(ind["duplicate_chain_groups"], 0)
            self.assertFalse(tier["gpu"]["ours_on_gpu"] or tier["gpu"]["gpu_library_mapped"])
            self.assertEqual(tier["inet_socket_observations"], 0)

    def test_throughput_and_criteria_follow_from_the_figures(self) -> None:
        base = self.tiers["w01"]
        for name, tier in self.tiers.items():
            self.assertAlmostEqual(tier["throughput_games_per_hour"],
                                   tier["games_completed"] / tier["makespan_seconds"] * 3600, places=6)
            if name == "S":
                continue
            recomputed = cq.criteria_for(tier, base)
            self.assertEqual(tier["criteria"], json.loads(json.dumps(recomputed)), name)
            self.assertAlmostEqual(tier["speedup"], tier["throughput_games_per_hour"] / base["throughput_games_per_hour"])
            self.assertAlmostEqual(tier["efficiency"], tier["speedup"] / tier["workers"])
            self.assertEqual(tier["criteria"]["throughput"]["pass"], tier["speedup"] >= 1.5)
            self.assertEqual(tier["criteria"]["efficiency"]["pass"], tier["efficiency"] >= 0.70)

    def test_the_recommendation_is_mechanical(self) -> None:
        rows = [self.tiers["S"]] + [t for n, t in self.tiers.items() if n != "S"]
        self.assertEqual(self.results["recommendation"], cq.recommend(rows))
        self.assertEqual(self.results["recommendation"]["disposition"], "RECOMMEND 16 WORKERS")
        self.assertFalse(self.tiers["w24"]["criteria"]["latency"]["pass"])
        self.assertLess(self.tiers["w24"]["efficiency"], cq.OPTIONAL_EFFICIENCY)
        self.assertNotIn("w32", self.tiers)

    def test_scheduler_equivalence(self) -> None:
        eq = self.results["equivalence"]
        self.assertTrue(eq["pass"])
        self.assertEqual(eq["problems"], [])
        self.assertEqual(eq["workers"], self.results["recommendation"]["workers"])
        self.assertEqual((eq["serial"]["records"], eq["parallel"]["records"]), (16, 16))
        self.assertEqual(eq["independence"], {"games": 16, "parallel": 16, "serial": 16})
        self.assertEqual(eq["deterministic_identical_between_runs"], eq["deterministic_games"])
        for run in ("serial", "parallel"):
            sessions = eq[run]["sessions"]
            self.assertEqual(sessions, list(range(sessions[0], sessions[0] + 16)))
            self.assertEqual(eq[run]["states"], 1)
        groups = [g for batch in eq["parallel"]["batches"].values() for g in batch]
        self.assertEqual(sorted(groups), ["B"] * 8 + ["C"] * 8)
        self.assertEqual(len(eq["scheduler"]), 1)

    @unittest.skipUnless(TIERS.is_dir(), "the tier summaries are private (git-ignored)")
    def test_results_regenerate_from_the_private_summaries(self) -> None:
        spec = importlib.util.spec_from_file_location("qualify", ROOT / "scripts" / "qualify_concurrency.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.cmd_analyze(type("A", (), {"check": True})()), 0)


if __name__ == "__main__":
    unittest.main()
