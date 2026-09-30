"""The variance study: registration, run order, per-game metrics, aggregation, diagnostics, sizing,
validation of executed games and the runner's baseline-v1 pin. Public: no SDK, data or records."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import variance_study as vs
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, POLICY_SOURCES, policy_source_digest
from miaosuan_agent.evaluation.manifest import PLAYERS
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID, ReservationAgent

from tests.fixtures import fake_engine
from tests.test_evaluation_game import FACTORIES, Inputs, spec

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "evaluation" / CANDIDATE_ID


def load_script(name):
    loader = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def real_build(history=None):
    v1_manifest = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
    results_bytes = (V1 / "results.json").read_bytes()
    digest, files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
    return vs.build(v1_manifest, json.loads(results_bytes), hashlib.sha256(results_bytes).hexdigest(),
                    history if history is not None else {"records": []}, files, digest, OCCUPY_RESERVATION_SOURCES)


SYNTHETIC_CONFIGS = [(f"9000000{i:02d}", c) for i in range(8) for c in vs.ACTIVE_CONDITIONS]


class ScheduleTest(unittest.TestCase):
    def raw_rounds(self, digest):
        """An independent reading of SCHEDULE_RULE, without the swap."""
        return [sorted(SYNTHETIC_CONFIGS, key=lambda c: hashlib.sha256(
            f"{digest}:{r}:{c[0]}.{c[1]}".encode("utf-8")).hexdigest()) for r in range(1, 9)]

    def test_plan_structure(self) -> None:
        plan = vs.schedule("d" * 64, SYNTHETIC_CONFIGS)
        self.assertEqual(len(plan), 192)
        self.assertEqual([e["position"] for e in plan], list(range(1, 193)))
        self.assertEqual(len({e["game_id"] for e in plan}), 192)
        for round_number in range(1, 9):
            rows = [e for e in plan if e["round"] == round_number]
            self.assertEqual(sorted((e["scenario_id"], e["condition"]) for e in rows), sorted(SYNTHETIC_CONFIGS))
            self.assertEqual({e["repetition"] for e in rows}, {round_number + 2})
        per_config = {}
        for e in plan:
            per_config.setdefault((e["scenario_id"], e["condition"]), []).append(e["repetition"])
        self.assertTrue(all(reps == list(range(3, 11)) for reps in per_config.values()))
        self.assertEqual({e["attempt"] for e in plan}, {1})

    def test_rule_is_reproducible_and_never_repeats_a_configuration_back_to_back(self) -> None:
        swaps = 0
        for n in range(40):
            digest = hashlib.sha256(str(n).encode()).hexdigest()
            plan = vs.schedule(digest, SYNTHETIC_CONFIGS)
            self.assertEqual(plan, vs.schedule(digest, SYNTHETIC_CONFIGS))
            played = [(e["scenario_id"], e["condition"]) for e in plan]
            self.assertTrue(all(a != b for a, b in zip(played, played[1:])))
            expected, previous = [], None
            for order in self.raw_rounds(digest):
                if previous is not None and order[0] == previous:
                    order[0], order[1] = order[1], order[0]
                    swaps += 1
                expected.extend(order)
                previous = order[-1]
            self.assertEqual(played, expected)
        self.assertGreater(swaps, 0, "the swap branch was never exercised")
        self.assertNotEqual(vs.schedule("a" * 64, SYNTHETIC_CONFIGS), vs.schedule("b" * 64, SYNTHETIC_CONFIGS))


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = real_build()

    def test_pins_and_structure(self) -> None:
        m = self.manifest
        self.assertEqual(m["policy_source"]["sha256"], vs.BASELINE_V1_SOURCE_SHA256)
        self.assertEqual(m["baseline"]["golden_trace_chain"], vs.BASELINE_V1_GOLDEN_TRACE_CHAIN)
        v1 = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["scenarios"], v1["scenarios"])
        self.assertEqual([c["id"] for c in m["conditions"]], ["C1", "C2", "C3"])
        self.assertEqual((m["repetition_target"], m["historical_repetitions"], m["new_repetitions"]),
                         (10, [1, 2], list(range(3, 11))))
        self.assertEqual((m["new_games"], len(m["schedule"])), (192, 192))
        self.assertEqual(m["design_sha256"], vs.design_digest(m))
        self.assertEqual(len(vs.scheduled_games(m)), 192)
        first = vs.scheduled_games(m)[0]
        self.assertEqual((first.game_id, first.repetition), (m["schedule"][0]["game_id"], 3))
        self.assertEqual(set(m["force_value_by_scenario"]), {s["scenario_id"] for s in m["scenarios"]})

    def test_deterministic_and_refuses_other_identities(self) -> None:
        self.assertEqual(mf.digest(self.manifest), mf.digest(real_build()))
        v1 = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
        results = json.loads((V1 / "results.json").read_text(encoding="utf-8"))
        digest, files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
        tampered = copy.deepcopy(v1)
        tampered["repetitions"] = 3
        with self.assertRaises(ValueError):
            vs.build(tampered, results, vs.BASELINE_V1_RESULTS_SHA256, {}, files, digest, OCCUPY_RESERVATION_SOURCES)
        with self.assertRaises(ValueError):
            vs.build(v1, results, "0" * 64, {}, files, digest, OCCUPY_RESERVATION_SOURCES)
        v0_digest, v0_files = policy_source_digest()
        with self.assertRaises(ValueError):
            vs.build(v1, results, vs.BASELINE_V1_RESULTS_SHA256, {}, v0_files, v0_digest, POLICY_SOURCES)

    def test_force_values_must_be_constant_per_scenario(self) -> None:
        results = json.loads((V1 / "results.json").read_text(encoding="utf-8"))
        broken = copy.deepcopy(results)
        broken["suite"]["games"][0]["final_scores"]["red_remain_max"] += 1
        with self.assertRaises(ValueError):
            vs.force_values(broken)

    def test_the_study_pins_the_current_baseline_v1_source(self) -> None:
        self.assertEqual(policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0], vs.BASELINE_V1_SOURCE_SHA256)


def candidate_game(condition="C2", **options):
    red, blue = {"C1": (CANDIDATE_ID, CANDIDATE_ID), "C2": (CANDIDATE_ID, INERT_ID), "C3": (INERT_ID, CANDIDATE_ID)}[condition]
    factories = dict(FACTORIES, **{CANDIDATE_ID: lambda: ReservationAgent(strict=True)})
    record = play(lambda: fake_engine.FakeEnv(**options), factories, spec(red=red, blue=blue), Inputs, PLAYERS,
                  replay_policies={CANDIDATE_ID})
    record["condition"] = condition
    return record


class GameMetricsTest(unittest.TestCase):
    def test_margin_follows_the_policy_side(self) -> None:
        record = candidate_game("C2")
        record["final_scores"] = {"red_total": 90, "blue_total": 30, "red_win": 60, "blue_win": -60}
        self.assertEqual(vs.game_metrics(record, CANDIDATE_ID)["values"]["margin"], 60)
        record["condition"] = "C3"
        metrics = vs.game_metrics(record, CANDIDATE_ID)
        self.assertEqual(metrics["values"]["margin"], -60)
        self.assertTrue(metrics["margin_fields_consistent"])
        record["final_scores"]["red_win"] = 1
        self.assertFalse(vs.game_metrics(record, CANDIDATE_ID)["margin_fields_consistent"])

    def test_counts_rates_and_facts_from_the_record(self) -> None:
        record = candidate_game("C2", red_wingmen=2, doomed=(7, fake_engine.RED_UNIT), engine_messages=True)
        metrics = vs.game_metrics(record, CANDIDATE_ID)
        values = metrics["values"]
        seats = [s for s in record["seats"] if s["policy"] == CANDIDATE_ID]
        self.assertEqual(len(seats), 1)
        actions = sum(v for s in seats for k, v in s["actions_by_type"].items() if k != "333")
        self.assertEqual(values["unit_actions"], actions)
        self.assertEqual(values["refusals"], sum(sum(s["feedback_errors_by_code"].values()) for s in seats))
        self.assertAlmostEqual(values["refusals_per_1000"], 1000 * values["refusals"] / actions)
        self.assertEqual(values["code_203"], 1)
        self.assertEqual(metrics["facts_source"], "record")
        self.assertEqual({(f["action_type"], f["code"]) for f in metrics["facts"]}, {(5, 203)})
        self.assertEqual(metrics["attributions"], {"actor no longer alive at resolution": 1})
        self.assertEqual(values["decision_seconds"], sum(v for s in seats for v in s["latency_us"]) / 1e6)
        self.assertGreater(values["suppressions"], 0)

    def test_historical_records_use_examples_and_mark_gaps(self) -> None:
        record = candidate_game("C2", red_wingmen=2, doomed=(7, fake_engine.RED_UNIT), engine_messages=True)
        for seat in record["seats"]:
            for name in ("refusals", "refusal_facts", "refusal_attributions"):
                del seat[name]
        metrics = vs.game_metrics(record, CANDIDATE_ID)
        self.assertEqual((metrics["facts_source"], metrics["facts_complete"], metrics["attributions"]),
                         ("examples", True, None))
        self.assertEqual({(f["action_type"], f["code"], f["message_class"]) for f in metrics["facts"]},
                         {(5, 203, "CantControlDiedOperator")})
        record["seats"][0]["feedback_error_examples"]["203"] = []
        self.assertFalse(vs.game_metrics(record, CANDIDATE_ID)["facts_complete"])

    def test_slow_decisions_are_counted_not_dropped(self) -> None:
        record = candidate_game("C2")
        seat = next(s for s in record["seats"] if s["policy"] == CANDIDATE_ID)
        seat["latency_us"][3] = 1_304_000
        metrics = vs.game_metrics(record, CANDIDATE_ID)
        self.assertEqual((metrics["values"]["latency_max_ms"], metrics["values"]["decisions_over_400ms"]), (1304.0, 1))
        self.assertIn(3, metrics["slow_decision_indices"])


class AggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = dict(vs.BOOTSTRAP)
        vs.BOOTSTRAP["resamples"] = 400

    def tearDown(self) -> None:
        vs.BOOTSTRAP.clear()
        vs.BOOTSTRAP.update(self.saved)

    def test_levels_keep_configurations_apart(self) -> None:
        values = {"x": {"1.C1": [1, 2, 3], "2.C1": [11, 12, 13], "1.C2": [5, 5, 5], "2.C2": [0, None, 2]}}
        result = vs.summarize(values, ["C1", "C2"])["x"]
        self.assertEqual(result["configurations"]["1.C2"]["constant"], True)
        self.assertEqual((result["configurations"]["1.C2"]["ci_low"], result["configurations"]["1.C2"]["ci_high"]),
                         (5.0, 5.0))
        self.assertEqual((result["configurations"]["2.C2"]["n"], result["configurations"]["2.C2"]["missing"]), (2, 1))
        c1 = result["conditions"]["C1"]
        self.assertAlmostEqual(c1["mean"], 7.0)
        self.assertAlmostEqual(c1["pooled_within_sd"], 1.0)
        self.assertAlmostEqual(c1["between_scenario_sd_of_means"], math.sqrt(50.0))
        self.assertAlmostEqual(c1["between_scenario_variance_component"], 50.0 - 1.0 / 3)
        self.assertTrue(c1["ci_low"] <= 7.0 <= c1["ci_high"])
        self.assertTrue(2.0 <= c1["ci_low"] and c1["ci_high"] <= 12.0)
        self.assertEqual(result["suite"]["configurations"], 4)
        self.assertEqual(result["suite"]["constant_configurations"], 1)
        self.assertEqual(result, vs.summarize(values, ["C1", "C2"])["x"], "the bootstrap must be deterministic")

    def test_pooled_sd_is_the_root_of_the_mean_variance(self) -> None:
        result = vs.summarize({"x": {"1.C1": [1, 3, 5], "2.C1": [10, 10, 16]}}, ["C1"])["x"]["conditions"]["C1"]
        self.assertAlmostEqual(result["within_variance"], (4 + 12) / 2)
        self.assertAlmostEqual(result["pooled_within_sd"], math.sqrt(8))

    def test_zero_variance_everywhere(self) -> None:
        result = vs.summarize({"x": {"1.C1": [4, 4], "2.C1": [4, 4]}}, ["C1"])["x"]["conditions"]["C1"]
        self.assertEqual((result["pooled_within_sd"], result["between_scenario_variance_component"], result["ci_low"],
                          result["ci_high"], result["between_share"]), (0.0, 0.0, 4.0, 4.0, None))


class TemporalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = dict(vs.TEMPORAL_BOOTSTRAP)
        vs.TEMPORAL_BOOTSTRAP["resamples"] = 300

    def tearDown(self) -> None:
        vs.TEMPORAL_BOOTSTRAP.clear()
        vs.TEMPORAL_BOOTSTRAP.update(self.saved)

    def rows(self, trend):
        new = {}
        for k in range(6):
            new[f"{k}.C1"] = [(10 * (r - 3) + k, r, 100 * k + trend * r + (r % 2)) for r in range(3, 11)]
        return new

    def test_a_trend_is_found_and_called_material(self) -> None:
        result = vs.temporal(self.rows(5.0), {}, "x")
        self.assertGreater(result["spearman_position"]["estimate"], 0.8)
        self.assertTrue(result["spearman_position"]["material"])
        self.assertTrue(result["second_minus_first_half_sd"]["material"])
        self.assertGreater(result["second_minus_first_half_sd"]["estimate"], 0)
        self.assertLess(vs.temporal({c: [(p, r, -v) for p, r, v in rows] for c, rows in self.rows(5.0).items()}, {},
                                    "x")["second_minus_first_half_sd"]["estimate"], 0)
        self.assertIsNone(result["historical_minus_new_sd"]["estimate"])

    def test_a_large_estimate_with_an_interval_across_zero_is_not_material(self) -> None:
        rows = {"a.C1": [(i + 1, r, float(v)) for i, (r, v) in enumerate(zip(range(3, 11), [1, 3, 2, 5, 4, 0, 7, 6]))]}
        result = vs.temporal(rows, {}, "x")
        for name in ("spearman_position", "second_minus_first_half_sd"):
            entry = result[name]
            with self.subTest(name=name):
                self.assertGreaterEqual(abs(entry["estimate"]), 0.5)
                self.assertLess(entry["ci_low"], 0)
                self.assertFalse(entry["material"])

    def test_no_trend_is_not_material_and_constant_configurations_are_excluded(self) -> None:
        rows = self.rows(0.0)
        rows["const.C2"] = [(200 + r, r, 7.0) for r in range(3, 11)]
        result = vs.temporal(rows, {c: [0.0, 1.0] for c in rows}, "x")
        self.assertFalse(result["spearman_position"]["material"])
        self.assertEqual(result["configurations_excluded_zero_sd"], 1)
        self.assertEqual(result["games"], 48)
        self.assertIsNotNone(result["historical_minus_new_sd"]["estimate"])

    def test_historical_offset_has_the_right_sign(self) -> None:
        rows = self.rows(0.0)
        result = vs.temporal(rows, {c: [v + 50 for _, _, v in rows[c][:2]] for c in rows}, "x")
        self.assertGreater(result["historical_minus_new_sd"]["estimate"], 0)


class ComparisonAndSizingTest(unittest.TestCase):
    def test_n2_versus_n10(self) -> None:
        per_config = {"a.C1": [(r, float(v)) for r, v in zip(range(1, 11), [0, 10, 5, 5, 5, 5, 5, 5, 5, 5])],
                      "b.C1": [(r, 3.0) for r in range(1, 11)]}
        result = vs.n2_versus_n10(per_config)
        a = result["configurations"]["a.C1"]
        self.assertEqual((a["n2_mean"], a["n10_mean"], a["change"]), (5.0, 5.0, 0.0))
        self.assertGreater(a["n2_ci_width"], a["n10_ci_width"])
        self.assertEqual(result["configurations"]["b.C1"]["n2_ci_width"], 0.0)
        self.assertFalse(a["n2_outside_n10_interval"])
        shifted = vs.n2_versus_n10({"c.C1": [(1, 50.0), (2, 52.0)] + [(r, float(r % 2)) for r in range(3, 11)]})
        self.assertTrue(shifted["configurations"]["c.C1"]["n2_outside_n10_interval"])
        self.assertEqual(shifted["equal_weighted"]["n2_estimates_outside_n10_interval"], 1)
        self.assertEqual(result["equal_weighted"]["configurations"], 2)
        self.assertGreater(result["equal_weighted"]["n2_ci_width"], result["equal_weighted"]["n10_ci_width"])

    def test_sizing_power_grows_with_repetitions(self) -> None:
        saved = dict(vs.MONTE_CARLO)
        vs.MONTE_CARLO["simulations"] = 300
        try:
            per_config = {f"{k}.C2": [float(v) for v in range(10 * k, 10 * k + 10)] for k in range(4)}
            per_config["z.C2"] = [5.0] * 10
            result = vs.sizing(per_config, {"absolute_points": [2]}, None, "x")
        finally:
            vs.MONTE_CARLO.clear()
            vs.MONTE_CARLO.update(saved)
        powers = [row["effects"][0]["power"] for row in result["table"]]
        self.assertEqual(powers, sorted(powers))
        sd = math.sqrt(sum((v - 4.5) ** 2 for v in range(10)) / 9)
        n2 = result["table"][0]
        self.assertAlmostEqual(n2["se"], math.sqrt(4 * 2 * sd ** 2 / 2) / 5)
        self.assertTrue(all(row["se_conservative"] > row["se"] for row in result["table"]))
        for row in result["table"]:
            effect = row["effects"][0]
            self.assertLess(abs(effect["power_monte_carlo"] - effect["power"]), 0.15)

    def test_relative_effects_and_the_default_rule(self) -> None:
        per_config = {"a.C1": [10.0, 12.0, 8.0, 10.0], "b.C1": [0.0, 0.0, 0.0, 0.0]}
        saved = dict(vs.MONTE_CARLO)
        vs.MONTE_CARLO["simulations"] = 50
        try:
            result = vs.sizing(per_config, {"relative_change": [-0.5]}, None, vs.DEFAULT_RULE_METRIC)
        finally:
            vs.MONTE_CARLO.clear()
            vs.MONTE_CARLO.update(saved)
        self.assertAlmostEqual(result["table"][0]["effects"][0]["macro_effect"], -2.5)
        self.assertEqual(vs.default_repetitions(result), next(
            row["repetitions"] for row in result["table"] if row["effects"][0]["power_conservative"] >= vs.POWER))
        never = {"table": [{"repetitions": n, "effects": [{"kind": "relative_change", "value": -0.5,
                                                              "power_conservative": 0.1}]} for n in (2, 5)]}
        self.assertIsNone(vs.default_repetitions(never))
        self.assertEqual(vs.cost({"a": 36.0, "b": 72.0})[0], {"repetitions": 2, "games_per_arm": 4, "hours_per_arm": 0.06,
                                                           "games_both_arms": 8, "hours_both_arms": 0.12})


class DeterminismTest(unittest.TestCase):
    def test_repetitions_of_a_deterministic_game_agree(self) -> None:
        records = [candidate_game("C2") for _ in range(3)]
        result = vs.determinism(records, CANDIDATE_ID)
        self.assertEqual((result["distinct_state_chains"], result["traces_equal_while_states_equal"]), (1, True))
        self.assertEqual(result["state_first_divergence_vs_repetition_1"], [None, None])
        noisy = candidate_game("C2", noise_at=10)
        result = vs.determinism(records[:1] + [noisy], CANDIDATE_ID)
        self.assertEqual(result["distinct_state_chains"], 2)
        self.assertIsNotNone(result["state_first_divergence_vs_repetition_1"][0])


class ValidationTest(unittest.TestCase):
    """The analysis script's checks of executed games, against a synthetic private tree."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = load_script("analyze_variance_study")
        cls.manifest = real_build()
        cls.digest = mf.digest(cls.manifest)
        cls.template = candidate_game("C2")

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (self.analysis.LOCAL, self.analysis.LEDGER)
        self.analysis.LOCAL = self.tmp
        self.analysis.LEDGER = self.tmp / "ledger.jsonl"
        (self.tmp / "evaluation" / vs.STUDY_NAME / "games").mkdir(parents=True)
        (self.tmp / "evaluation" / vs.STUDY_NAME / "started").mkdir(parents=True)

    def tearDown(self) -> None:
        self.analysis.LOCAL, self.analysis.LEDGER = self.saved
        shutil.rmtree(self.tmp)

    def record(self, entry, session):
        record = copy.deepcopy(self.template)
        record.update(game_id=entry["game_id"], scenario_id=entry["scenario_id"], condition=entry["condition"],
                      repetition=entry["repetition"], session=session, python=vs.RUNTIME["python"],
                      engine_version=self.manifest["engine"]["version"],
                      session_close={"state_changed": False, "home_changed": False, "integrity": {"ok": True}},
                      harness={"commit": "c" * 40, "dirty": False, "game_id": entry["game_id"],
                               "manifest_sha256": self.digest, "policy_source_sha256": vs.BASELINE_V1_SOURCE_SHA256})
        return record

    def write(self, records, ledger_games=None, started=()):
        games = self.tmp / "evaluation" / vs.STUDY_NAME / "games"
        for record in records:
            (games / f"{record['game_id']}.json").write_text(json.dumps(record), encoding="utf-8")
            (games.parent / "started" / record["game_id"]).write_text("2026-09-30T00:00:00Z", encoding="utf-8")
        for name in started:
            (games.parent / "started" / name).write_text("2026-09-30T00:00:00Z", encoding="utf-8")
        lines = [{"session": "0001", "event": "session-open", "harness": {}},
                 {"session": "0001", "event": "session-close", "state_changed": True, "outcome": {}}]
        for index, game in enumerate(ledger_games if ledger_games is not None else [r["game_id"] for r in records]):
            session = f"{index + 2:04d}"
            lines.append({"session": session, "event": "session-open",
                          "harness": {"manifest_sha256": self.digest, "game_id": game}})
            lines.append({"session": session, "event": "session-close", "state_changed": False,
                          "outcome": {"game_id": game}})
        self.analysis.LEDGER.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    def validate(self, records, allow_incomplete=True):
        history = [{"game_id": "h", "verified": True}]
        return self.analysis.validate(self.manifest, history, {r["game_id"]: r for r in records}, allow_incomplete)

    def three(self):
        return [self.record(entry, f"{i + 2:04d}") for i, entry in enumerate(self.manifest["schedule"][:3])]

    def test_a_valid_partial_run(self) -> None:
        records = self.three()
        self.write(records)
        result = self.validate(records)
        self.assertEqual(result["problems"], [])
        self.assertEqual((result["recorded"], len(result["missing"]), result["complete"]), (3, 189, False))
        self.assertEqual(result["sessions"], {"first": "0002", "last": "0004", "count": 3, "contiguous": True})
        self.assertIn("189 scheduled games have no record", " ".join(self.validate(records, False)["problems"]))

    def test_unregistered_duplicate_replaced_and_foreign_games_are_found(self) -> None:
        records = self.three()
        extra = copy.deepcopy(records[0])
        extra["game_id"] = "900.C1.r3"
        self.write(records + [extra])
        self.assertIn("records not in the schedule", " ".join(self.validate(records)["problems"]))
        self.tearDown()
        self.setUp()
        records = self.three()
        records[2]["session"] = records[1]["session"]
        self.write(records)
        self.assertIn("share an engine session", " ".join(self.validate(records)["problems"]))
        self.tearDown()
        self.setUp()
        records = self.three()
        ids = [r["game_id"] for r in records]
        self.write(records, ledger_games=ids[:1] + ids)
        result = self.validate(records)
        self.assertEqual(result["ledger"]["replaced_games"], ids[:1])
        self.tearDown()
        self.setUp()
        records = self.three()
        records[1]["harness"]["policy_source_sha256"] = "0" * 64
        self.write(records)
        self.assertEqual(self.validate(records)["identity_failures"], {"policy digest": 1})

    def test_failed_attempts_are_kept_and_reported(self) -> None:
        records = self.three()
        records[1]["status"] = "FAIL"
        self.write(records, started=[self.manifest["schedule"][3]["game_id"]])
        result = self.validate(records)
        self.assertEqual(result["status"], {"COMPLETED": 2, "FAIL": 1})
        self.assertEqual(result["started_without_record"], [self.manifest["schedule"][3]["game_id"]])
        self.assertFalse(result["complete"])
        self.assertIn("scheduled games have no record", " ".join(self.validate(records, False)["problems"]))


class RunnerPinTest(unittest.TestCase):
    def run_game(self, manifest):
        rev = load_script("run_evaluation")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            args = Namespace(manifest=path, game_id=manifest["schedule"][0]["game_id"], work=Path(tmp) / "work",
                             engine_install=Path(tmp), harness_commit="x", harness_dirty=False, purpose="evaluation")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = rev.cmd_game(args)
        return status, err.getvalue()

    def test_study_games_refuse_anything_but_baseline_v1(self) -> None:
        manifest = real_build()
        rev = load_script("run_evaluation")
        self.assertEqual(list(rev.all_games(manifest)), [e["game_id"] for e in manifest["schedule"]])
        tampered = copy.deepcopy(manifest)
        tampered["policy_source"]["sha256"] = "0" * 64
        status, message = self.run_game(tampered)
        self.assertEqual(status, 2)
        self.assertIn("differs from the registered one", message)
        v0_digest, v0_files = policy_source_digest()
        other = copy.deepcopy(manifest)
        other["policy_source"] = {"sha256": v0_digest, "files": v0_files, "sources": list(POLICY_SOURCES)}
        status, message = self.run_game(other)
        self.assertEqual(status, 2)
        self.assertIn("runs baseline-v1 only", message)


if __name__ == "__main__":
    unittest.main()
