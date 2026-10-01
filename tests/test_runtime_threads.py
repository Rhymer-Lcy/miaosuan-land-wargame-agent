"""The runtime thread-pool qualification: plan, queues, disposition rule, probe reading and GC-pause observer.

The plan is built from committed files only (the concurrency plan and the shoot experiment's manifest), so its
rebuild is a public test.
"""

from __future__ import annotations

import gc
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import runtime_threads as rt
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation.gc_pauses import GcPauses

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "evaluation" / rt.PLAN_ID / "plan.json"
DOCUMENT = ROOT / "docs" / "RUNTIME_THREAD_QUALIFICATION.md"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN.read_text(encoding="utf-8"))

    def test_the_committed_plan_rebuilds_from_public_files(self) -> None:
        self.assertEqual(load_script("build_runtime_thread_plan").build(), PLAN.read_text(encoding="utf-8"))

    def test_the_only_variable_is_the_thread_environment(self) -> None:
        self.assertEqual(self.plan["environments"], {"A": {}, "B": {"OPENBLAS_NUM_THREADS": "1"}})
        self.assertEqual(self.plan["identities"]["policy_source"]["sha256"],
                         "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae")
        self.assertEqual(self.plan["identities"]["runtime_policy_source_sha256"], sx.RUNTIME_R1_SOURCE_SHA256)
        self.assertEqual(self.plan["runtime_candidate"], "baseline-v1-runtime-r2")
        self.assertEqual([t["environment"] for t in self.plan["tiers"]], ["A", "B", "B", "A", "B", "A", "B"])

    def test_queues(self) -> None:
        sizes = {t["tier"]: len(rt.tier_queue(self.plan, t["tier"])) for t in self.plan["tiers"] + self.plan["optional_tiers"]}
        self.assertEqual(sizes, {"P-A": 16, "E-B": 16, "B-w01": 16, "A-w16": 64, "B-w16": 64, "A-w24": 96, "B-w24": 96,
                                 "B-w32": 128})
        ids = [e["game_id"] for t in rt.sequence(self.plan) for e in rt.tier_queue(self.plan, t)]
        self.assertEqual(len(ids), len(set(ids)))
        corpus = rt.tier_queue(self.plan, "E-B")
        self.assertEqual(sorted({e["group"] for e in corpus}), ["B", "C"])
        self.assertEqual({e["policy"] for e in corpus}, {sx.RUNTIME_R1_CODE_ID, sx.CANDIDATE_ID})
        self.assertTrue(all(e["game_id"].endswith("." + e["group"]) for e in corpus))
        block = rt.tier_queue(self.plan, "B-w16")
        self.assertEqual({e["group"] for e in block}, {"C"})
        self.assertEqual(block[0]["game_id"], "rt1.B-w16.001.2130511121.C3")
        walls = [next(b for b in self.plan["block"] if b["config"] == e["config"])["expected_wall_seconds"] for e in block]
        self.assertEqual(walls, sorted(walls, reverse=True))

    def test_probe_and_process_check_are_pinned(self) -> None:
        import hashlib
        self.assertEqual(self.plan["probe"]["source_sha256"],
                         hashlib.sha256((ROOT / "scripts" / "blas_count_shim.c").read_bytes()).hexdigest())
        self.assertEqual(self.plan["probe"]["import_baseline"], {"cblas_sdot64_": 1})
        self.assertEqual(self.plan["process_check"]["concurrent"], [16, 24])

    def test_document_cites_the_plan(self) -> None:
        flat = " ".join(DOCUMENT.read_text(encoding="utf-8").split())
        self.assertIn(f"`{rt.digest(self.plan)[:8]}…`", flat)
        self.assertIn("OPENBLAS_NUM_THREADS=1", flat)


def tier(name, workers, throughput, cpu=20.0, p99=1.0, maximum=800.0, ok=True, our=None, rss=0.02):
    return {"tier": name, "workers": workers, "throughput_games_per_hour": throughput, "cpu_seconds_per_game_median": cpu,
            "latency": {"p99_ms": p99, "max_ms": maximum}, "safety_pass": ok, "independence_pass": True,
            "engine_state_pass": True, "ledger_pass": True, "our_cpus_mean": workers if our is None else our,
            "peak_rss_fraction": rss}


class DispositionTest(unittest.TestCase):
    def base(self):
        return {"P-A": tier("P-A", 1, 60), "E-B": tier("E-B", 1, 60), "B-w01": tier("B-w01", 1, 70, cpu=17.0)}

    def test_a_failed_check_blocks(self) -> None:
        tiers = dict(self.base(), **{"B-w16": tier("B-w16", 16, 1000, ok=False)})
        self.assertEqual(rt.disposition(tiers)["disposition"], "BLOCKED")
        self.assertEqual(rt.disposition({"P-A": tier("P-A", 1, 60)})["disposition"], "BLOCKED")

    def test_no_benefit_retains_runtime_r1(self) -> None:
        tiers = dict(self.base(), **{"A-w16": tier("A-w16", 16, 960, cpu=20.0), "B-w16": tier("B-w16", 16, 970, cpu=19.0),
                                     "A-w24": tier("A-w24", 24, 1380, cpu=21.0),
                                     "B-w24": tier("B-w24", 24, 1390, cpu=20.0, maximum=1700.0)})
        result = rt.disposition(tiers)
        self.assertEqual((result["disposition"], result["workers"]), ("RETAIN runtime-r1", 16))

    def test_cpu_benefit_promotes_and_the_knee_picks_the_count(self) -> None:
        tiers = dict(self.base(), **{"A-w16": tier("A-w16", 16, 960, cpu=23.0), "B-w16": tier("B-w16", 16, 1000, cpu=18.0),
                                     "A-w24": tier("A-w24", 24, 1380, cpu=24.0), "B-w24": tier("B-w24", 24, 1500, cpu=18.0),
                                     "B-w32": tier("B-w32", 32, 1950, cpu=18.0, our=31.0)})
        result = rt.disposition(tiers)
        self.assertEqual(result["disposition"], "PROMOTED AS baseline-v1-runtime-r2")
        self.assertEqual(result["workers"], 32)
        self.assertTrue(result["benefits"]["cpu_reduction"] and result["benefits"]["higher_worker_count"])

    def test_a_latency_failure_excludes_a_tier(self) -> None:
        tiers = dict(self.base(), **{"A-w16": tier("A-w16", 16, 960, cpu=23.0), "B-w16": tier("B-w16", 16, 1000, cpu=18.0),
                                     "A-w24": tier("A-w24", 24, 1380, cpu=24.0),
                                     "B-w24": tier("B-w24", 24, 1500, cpu=18.0, maximum=1700.0)})
        result = rt.disposition(tiers)
        self.assertFalse(result["criteria"]["B-w24"]["latency"]["pass"])
        self.assertEqual((result["disposition"], result["workers"]), ("PROMOTED AS baseline-v1-runtime-r2", 16))

    def test_throughput_benefit_alone(self) -> None:
        tiers = dict(self.base(), **{"A-w16": tier("A-w16", 16, 900, cpu=20.0), "B-w16": tier("B-w16", 16, 960, cpu=19.5),
                                     "A-w24": tier("A-w24", 24, 1380, cpu=21.0),
                                     "B-w24": tier("B-w24", 24, 1390, cpu=20.0, maximum=1700.0)})
        result = rt.disposition(tiers)
        self.assertTrue(result["benefits"]["throughput_gain"])
        self.assertFalse(result["benefits"]["cpu_reduction"])
        self.assertEqual(result["disposition"], "PROMOTED AS baseline-v1-runtime-r2")


class ReadingTest(unittest.TestCase):
    def test_blas_calls_subtract_the_import_baseline(self) -> None:
        counts = {"cblas_sdot64_": 1, "cblas_ddot64_": 0, "dgesv_64_": 0}
        self.assertEqual(rt.blas_calls(counts, {"cblas_sdot64_": 1}), {})
        self.assertEqual(rt.blas_calls(dict(counts, cblas_ddot64_=3), {"cblas_sdot64_": 1}), {"cblas_ddot64_": 3})

    def test_thread_split(self) -> None:
        rows = [{"tid": 1, "cpu_seconds": 10.0, "voluntary": 5, "involuntary": 7, "migrations": 2},
                {"tid": 2, "cpu_seconds": 0.1, "voluntary": 1, "involuntary": 1000, "migrations": 30},
                {"tid": 3, "cpu_seconds": 0.1, "voluntary": 1, "involuntary": 500, "migrations": 20}]
        split = rt.thread_split(rows)
        self.assertEqual((split["threads"], split["main_involuntary"], split["other_involuntary"], split["other_migrations"]),
                         (3, 7, 1500.0, 50.0))
        self.assertIsNone(rt.thread_split(rows[:1] + [{"tid": 2, "cpu_seconds": 0.1}])["other_involuntary"])
        self.assertEqual(rt.thread_split([]), {})


class GcPausesTest(unittest.TestCase):
    def test_pauses_are_timed_per_generation(self) -> None:
        ticks = iter([0.0, 0.010, 1.0, 1.120, 2.0, 2.001])
        probe = GcPauses(keep_over_seconds=0.05, clock=lambda: next(ticks))
        probe("start", {"generation": 0})
        probe("stop", {"generation": 0})
        probe("start", {"generation": 2})
        probe("stop", {"generation": 2})
        probe("start", {"generation": 1})
        probe("stop", {"generation": 1})
        summary = probe.summary()
        self.assertEqual(summary["count"], [1, 1, 1])
        self.assertEqual(summary["max_ms"], [10.0, 1.0, 120.0])
        self.assertEqual(summary["kept"], [[2, 120.0]])

    def test_install_observes_real_collections_without_changing_thresholds(self) -> None:
        thresholds = gc.get_threshold()
        probe = GcPauses().install()
        try:
            gc.collect()
        finally:
            probe.remove()
        self.assertGreaterEqual(probe.summary()["count"][2], 1)
        self.assertNotIn(probe, gc.callbacks)
        self.assertEqual(gc.get_threshold(), thresholds)


if __name__ == "__main__":
    unittest.main()
