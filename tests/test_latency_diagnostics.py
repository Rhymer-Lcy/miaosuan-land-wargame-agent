"""Latency diagnostics: record parsing, thresholds, grouping, outlier classes, the external probe and the plan.

Public: synthetic games from the stand-in engine only.
"""

from __future__ import annotations

import copy
import gc
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.decision import INERT_ID, digest
from miaosuan_agent.decision import policy as policy_module
from miaosuan_agent.decision import routing
from miaosuan_agent.diagnostics import instrument
from miaosuan_agent.diagnostics import latency as lat
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import variance_study as vs
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID, ReservationAgent

from tests.fixtures import fake_engine
from tests.test_evaluation_game import FACTORIES, Inputs, spec

ROOT = Path(__file__).resolve().parents[1]
ALL = dict(FACTORIES, **{CANDIDATE_ID: lambda: ReservationAgent(strict=True)})


def game(**options):
    record = play(lambda: fake_engine.FakeEnv(**options), ALL, spec(red=CANDIDATE_ID, blue=INERT_ID), Inputs, PLAYERS,
                  replay_policies={CANDIDATE_ID})
    record["condition"] = "C2"
    return record


def rows_of(latencies, scenario="s", condition="C1", decision_start=0):
    return [{"scenario_id": scenario, "condition": condition, "decision": decision_start + i, "first_play": i == 1,
             "latency_us": value} for i, value in enumerate(latencies)]


class RecordRowsTest(unittest.TestCase):
    def test_rows_follow_the_record(self) -> None:
        record = game()
        rows = lat.decision_rows(record, (CANDIDATE_ID,))
        seat = next(s for s in record["seats"] if s["policy"] == CANDIDATE_ID)
        self.assertEqual(len(rows), seat["decisions"])
        self.assertEqual([r["latency_us"] for r in rows], seat["latency_us"])
        self.assertEqual((rows[0]["stage"], rows[0]["first_play"], rows[0]["play_index"]), (1, False, None))
        self.assertEqual((rows[1]["stage"], rows[1]["first_play"], rows[1]["play_index"]), (2, True, 0))
        self.assertEqual(rows[5]["play_index"], 4)
        both = lat.decision_rows(record, (CANDIDATE_ID, INERT_ID))
        self.assertEqual(len(both), 2 * len(rows))

    def test_malformed_records_are_refused(self) -> None:
        record = game()
        broken = copy.deepcopy(record)
        del broken["stage_transitions"]
        with self.assertRaises(lat.RecordError):
            lat.decision_rows(broken, (CANDIDATE_ID,))
        broken = copy.deepcopy(record)
        broken["seats"][0]["latency_us"][2] = -1
        with self.assertRaises(lat.RecordError):
            lat.decision_rows(broken, (CANDIDATE_ID,))
        broken["seats"][0]["latency_us"] = "slow"
        with self.assertRaises(lat.RecordError):
            lat.decision_rows(broken, (CANDIDATE_ID,))

    def test_stage_at(self) -> None:
        transitions = [{"step": 0, "stage": 1}, {"step": 1, "stage": 2}]
        self.assertEqual([lat.stage_at(transitions, i) for i in (0, 1, 7)], [1, 2, 2])
        self.assertIsNone(lat.stage_at([{"step": 3, "stage": 2}], 0))


class AggregationTest(unittest.TestCase):
    def test_thresholds_are_strict_and_cumulative(self) -> None:
        rows = rows_of([10_000, 10_001, 50_001, 100_000, 400_001, 1_000_001])
        self.assertEqual(lat.threshold_counts(rows), {">10ms": 5, ">50ms": 4, ">100ms": 2, ">250ms": 2, ">400ms": 2,
                                                      ">1000ms": 1})
        self.assertEqual(lat.threshold_counts([]), {f">{t}ms": 0 for t in lat.THRESHOLDS_MS})

    def test_grouping_and_concentration(self) -> None:
        rows = rows_of([200_000, 500, 700_000], "a", "C3") + rows_of([150_000, 400], "b", "C1")
        grouped = lat.grouped(rows, ("scenario_id", "condition"))
        self.assertEqual(set(grouped), {"a|C3", "b|C1"})
        self.assertEqual((grouped["a|C3"]["decisions"], grouped["a|C3"][">100ms"], grouped["a|C3"]["max_ms"]), (3, 2, 700.0))
        concentration = lat.concentration(rows, 100, ("scenario_id",))
        self.assertEqual(concentration["above"], 3)
        self.assertEqual(list(concentration["groups"]), ["a", "b"])
        self.assertAlmostEqual(sum(g["share"] for g in concentration["groups"].values()), 1.0)
        self.assertEqual(lat.concentration(rows, 5000, ("scenario_id",)), {"above": 0, "groups": {}})

    def test_summary_uses_exact_nearest_ranks(self) -> None:
        values = list(range(1, 1001))
        summary = lat.summary([v * 1000 for v in values])
        self.assertEqual((summary["p50_ms"], summary["p95_ms"], summary["p99_ms"], summary["max_ms"]),
                         (500.0, 950.0, 990.0, 1000.0))
        self.assertEqual(lat.summary([])["count"], 0)

    def test_outlier_classes(self) -> None:
        self.assertEqual(lat.classify(1.2, 0.004, 0.0), "scheduling or waiting")
        self.assertEqual(lat.classify(1.2, 1.19, 1.1), "garbage collection")
        self.assertEqual(lat.classify(0.5, 0.49, 0.001), "computation")
        self.assertEqual(lat.classify(0.5, 0.35, 0.1), "mixed")
        self.assertEqual(lat.classify(0.0, 0.0, 0.0), "unmeasurable")
        self.assertEqual(lat.classify(0.5, None, None), "unclassified: no CPU time")


class ProbeTest(unittest.TestCase):
    def test_install_and_restore(self) -> None:
        originals = (policy_module.build_context, routing.Router._dijkstra, routing.Router.__dict__["shortest_paths"])
        probe = instrument.Probe()
        with probe.installed():
            self.assertIsNot(policy_module.build_context, originals[0])
            self.assertIs(policy_module.build_context.__wrapped__, originals[0])
        self.assertEqual((policy_module.build_context, routing.Router._dijkstra,
                          routing.Router.__dict__["shortest_paths"]), originals)

    def test_decisions_do_not_change_under_the_probe(self) -> None:
        plain = game(red_wingmen=2)
        probe = instrument.Probe()
        with probe.installed():
            probed = game(red_wingmen=2)
        for a, b in zip(plain["seats"], probed["seats"]):
            self.assertEqual(a["trace_chain"], b["trace_chain"])
            self.assertEqual(a["actions_by_type"], b["actions_by_type"])
        self.assertEqual(plain["state_chain"], probed["state_chain"])

    def test_component_times_add_up_and_routing_is_counted(self) -> None:
        agent = ReservationAgent(strict=True)
        agent.setup({"seat": 1, "faction": 0, "cost_data": Inputs.cost})
        env = fake_engine.FakeEnv()
        from miaosuan_agent.boundary import Origin, normalize_state
        state = env.setup({"player_info": [dict(p) for p in PLAYERS]})
        probe = instrument.Probe()
        with probe.installed():
            for _ in range(3):
                view = normalize_state(state, Origin.ENGINE)
                with probe.decision({"i": _}) as record:
                    actions = agent.step(view.for_faction(0).fields)
                state, _done = env.step(actions + [{"actor": 11, "type": 333}])
        moved = [d for d in probe.decisions if d["routing"]["requests"]]
        self.assertTrue(moved)
        self.assertGreaterEqual(moved[0]["routing"]["dijkstra_runs"], 1)
        self.assertGreater(moved[0]["routing"]["nodes_settled"], 0)
        self.assertEqual(len(moved[0]["routing"]["per_unit"]), moved[0]["routing"]["move_candidate_calls"])
        for record in probe.decisions:
            account = instrument.accounting(record)
            self.assertLess(account["sum_error"], 1e-6)
            self.assertGreaterEqual(record["thread_cpu"], 0.0)  # coarse on some platforms
        self.assertGreater(moved[0]["components"]["dijkstra"], 0)

    def test_exclusive_time_with_a_fake_clock(self) -> None:
        ticks = iter(range(100))
        probe = instrument.Probe(clock=lambda: float(next(ticks)))
        with probe.decision() as record:
            probe._enter("move_candidates")
            probe._enter("dijkstra")
            probe._exit()
            probe._exit()
        self.assertEqual(record["components"]["dijkstra"], 1.0)
        self.assertEqual(record["components"]["move_candidates"], 2.0)
        self.assertEqual(record["components"]["other"], 2.0)
        self.assertEqual(record["wall"], 5.0)

    def test_collections_inside_a_decision_are_recorded(self) -> None:
        probe = instrument.Probe(keep=False)
        with probe.installed():
            with probe.decision({"which": "forced"}) as record:
                gc.collect()
            gc.collect()
        self.assertGreaterEqual(record["gc"]["collections"], 1)
        self.assertEqual(record["gc"]["by_generation"].get("2"), 1)
        self.assertGreater(record["gc"]["full_seconds"], 0)
        self.assertEqual(probe.decisions, [])
        inside = [c for c in probe.full_collections if c["in_decision"]]
        self.assertEqual([c["in_decision"] for c in inside], [{"which": "forced"}])
        self.assertGreaterEqual(probe.collections_outside_decisions.get("2", 0), 1)


class ScriptHelpersTest(unittest.TestCase):
    def test_distribution_reports_the_first_call_and_exact_ranks(self) -> None:
        loader = importlib.util.spec_from_file_location("bench", ROOT / "scripts" / "replay_latency_benchmark.py")
        bench = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(bench)  # type: ignore[union-attr]
        values = [0.5] + [0.001] * 199
        result = bench.distribution(values)
        self.assertEqual((result["n"], result["first_ms"], result["max_ms"]), (200, 500.0, 500.0))
        self.assertEqual(result["p50_ms"], 1.0)
        agent = ReservationAgent(strict=True)
        agent.setup({"seat": 1, "faction": 0, "cost_data": Inputs.cost})
        from miaosuan_agent.boundary import Origin, normalize_state
        env = fake_engine.FakeEnv()
        state = env.setup({"player_info": [dict(p) for p in PLAYERS]})
        state, _ = env.step([{"actor": 1, "type": 333}, {"actor": 11, "type": 333}])
        agent.memory = type(agent.memory)(deployment_sent=True)
        actions = agent.step(normalize_state(state, Origin.ENGINE).for_faction(0).fields)
        work = bench.workload(agent, actions)
        self.assertEqual((work["units"], work["emitted"]), (1, len(actions)))
        self.assertEqual(work["move_units"], {u.obj_id for u in agent.last_trace.units if u.rule == "move"})
        self.assertEqual(digest(agent.last_trace), digest(agent.last_trace))


class PlanTest(unittest.TestCase):
    def test_plan_pins_the_frozen_policy_and_the_study(self) -> None:
        plan = json.loads((ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json").read_text(encoding="utf-8"))
        study = json.loads((ROOT / "evaluation" / vs.STUDY_NAME / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["policy_source_sha256"], vs.BASELINE_V1_SOURCE_SHA256)
        self.assertEqual(plan["study_manifest_sha256"], mf.digest(study))
        games = plan["games"]
        self.assertEqual(len(games), 5)
        self.assertEqual(len({g["id"] for g in games}), 5)
        scenarios = {s["scenario_id"] for s in study["scenarios"]}
        self.assertTrue(all(g["scenario_id"] in scenarios and g["condition"] in ("C1", "C2", "C3") for g in games))
        self.assertEqual(sorted(g["gc_in_decision"] for g in games).count("paused"), 1)
        self.assertTrue(all(g["gc_in_decision"] in ("enabled", "paused") for g in games))


if __name__ == "__main__":
    unittest.main()
