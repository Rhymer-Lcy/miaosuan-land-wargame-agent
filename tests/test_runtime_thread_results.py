"""The committed results of the runtime thread-pool qualification, recomputed from their own public values.

Throughput, speedups, every worker criterion, the A/B comparison and the disposition must follow from the per-tier
figures in results.json and the registered rules; the byte-identical regeneration from the private tier summaries
runs only where they exist.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import runtime_threads as rt

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / rt.PLAN_ID
TIERS = ROOT / "local" / "diagnostics" / rt.PLAN_ID / "tiers"


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads((DIRECTORY / "plan.json").read_text(encoding="utf-8"))
        cls.results = json.loads((DIRECTORY / "results.json").read_text(encoding="utf-8"))
        cls.tiers = cls.results["tiers"]

    def test_results_cite_the_plan_and_one_commit(self) -> None:
        self.assertEqual(self.results["plan_sha256"], rt.digest(self.plan))
        self.assertEqual(len(self.results["commits"]), 1)

    def test_every_tier_ran_and_passed(self) -> None:
        self.assertEqual(sorted(self.tiers), sorted(rt.sequence(self.plan)))
        for name, tier in self.tiers.items():
            spec = rt.tier_spec(self.plan, name)
            self.assertEqual((tier["environment"], tier["workers"]), (spec["environment"], spec["workers"]))
            self.assertEqual(tier["thread_env"], self.plan["environments"][spec["environment"]])
            self.assertEqual(tier["games_completed"], len(rt.tier_queue(self.plan, name)))
            self.assertEqual(tier["games_planned"], tier["games_completed"])
            self.assertEqual(tier["ledger"]["sessions"], tier["games_planned"])
            self.assertTrue(tier["safety_pass"] and tier["independence_pass"] and tier["engine_state_pass"]
                            and tier["ledger_pass"], name)
            self.assertFalse(tier["contended"])
            self.assertEqual(tier["inet_socket_observations"], 0)
            self.assertFalse(tier["gpu"]["ours_on_gpu"] or tier["gpu"]["gpu_library_mapped"])
            self.assertEqual(tier["threads_per_process_max"], 64 if spec["environment"] == "A" else 1, name)
            eq = tier["equivalence"]
            self.assertEqual(eq["deterministic_identical"], eq["deterministic_games"])
            self.assertEqual(eq["stochastic_prefix_equal"], eq["stochastic_games"])
            self.assertEqual(eq["deterministic_games"] + eq["stochastic_games"], tier["games_planned"])
            self.assertEqual(eq["duplicate_chain_groups"], 0)
            self.assertGreaterEqual(eq["agreement_min_over_first_shot"], 1)
            self.assertAlmostEqual(tier["throughput_games_per_hour"],
                                   tier["games_completed"] / tier["makespan_seconds"] * 3600, places=6)

    def test_the_probe_found_no_blas_work(self) -> None:
        probe = self.tiers["P-A"]["probe"]
        self.assertEqual((probe["games"], probe["games_with_blas_calls"], probe["calls"]), (16, 0, {}))

    def test_criteria_comparison_and_disposition_follow(self) -> None:
        base = self.tiers["B-w01"]
        for name, tier in self.tiers.items():
            if name.startswith("B-w"):
                self.assertEqual(tier["criteria"], json.loads(json.dumps(rt.worker_criteria(tier, base))), name)
                self.assertAlmostEqual(tier["speedup"], tier["throughput_games_per_hour"] / base["throughput_games_per_hour"])
                self.assertAlmostEqual(tier["efficiency"], tier["speedup"] / tier["workers"])
        for n in (16, 24):
            a, b, c = self.tiers[f"A-w{n}"], self.tiers[f"B-w{n}"], self.results["comparison"][f"w{n}"]
            self.assertAlmostEqual(c["throughput_ratio_b_over_a"], b["throughput_games_per_hour"] / a["throughput_games_per_hour"])
            self.assertAlmostEqual(c["cpu_per_game_ratio_b_over_a"], b["cpu_seconds_per_game_median"] / a["cpu_seconds_per_game_median"])
        expected = json.loads(json.dumps(rt.disposition(self.tiers)))
        self.assertEqual(self.results["disposition"], expected)
        self.assertEqual((expected["disposition"], expected["workers"]), ("PROMOTED AS baseline-v1-runtime-r2", 32))
        self.assertEqual(expected["benefits"], {"cpu_reduction": True, "higher_worker_count": True, "throughput_gain": False})

    def test_process_level_and_production_path(self) -> None:
        process = self.results["process_level"]
        self.assertEqual((process["A"]["threads_after"], process["B"]["threads_after"]), ([64], [1]))
        self.assertLess(process["B"]["import_cpu_median"], process["A"]["import_cpu_median"])
        self.assertTrue(process["A"]["sanity_consistent"] and process["B"]["sanity_consistent"])
        equal = process["sanity_equal_between_environments"]
        self.assertEqual(equal, {k: process["A"]["sanity"][k] == process["B"]["sanity"][k] for k in process["A"]["sanity"]})
        production = self.results["production_path"]
        self.assertTrue(production["pass"])
        self.assertEqual((production["records"], production["independence"], production["games"]), (16, 16, 16))
        self.assertEqual((production["runtime"], production["thread_env"]), ("baseline-v1-runtime-r2", {"OPENBLAS_NUM_THREADS": "1"}))
        self.assertEqual(production["sessions"], list(range(production["sessions"][0], production["sessions"][0] + 16)))

    @unittest.skipUnless(TIERS.is_dir(), "the tier summaries are private (git-ignored)")
    def test_results_regenerate_from_the_private_summaries(self) -> None:
        spec = importlib.util.spec_from_file_location("qualify", ROOT / "scripts" / "qualify_runtime_threads.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.cmd_analyze(type("A", (), {"check": True})()), 0)


if __name__ == "__main__":
    unittest.main()
