"""The shoot-reservation experiment: registration, schedule, per-game metrics, the registered analyses, the
promotion criteria, validation of executed games, the runner's pins and the harness counters. Public: no SDK,
data or records."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import unittest.mock
from argparse import Namespace
from collections import Counter
from pathlib import Path

from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.identity import policy_source_digest
from miaosuan_agent.evaluation.manifest import PLAYERS
from miaosuan_agent.experiments import routing_bounded, shoot_reservation
from miaosuan_agent.experiments.routing_bounded import BoundedRoutingAgent
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent

from tests import test_shoot_reservation
from tests.fixtures import fake_engine
from tests.test_evaluation_game import FACTORIES, Inputs, spec

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_CONFIGS = [(f"9000000{i:02d}", c) for i in range(8) for c in sx.ACTIVE_CONDITIONS]
ALL = dict(FACTORIES, **{sx.RUNTIME_R1_CODE_ID: lambda: BoundedRoutingAgent(strict=True),
                         sx.CANDIDATE_ID: lambda: ShootReservationAgent(strict=True)})


def load_script(name):
    loader = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def real_build(**overrides):
    inputs = load_script("build_shoot_experiment_manifest").inputs()
    inputs.update(overrides)
    return sx.build(**inputs)


class CloseEnemy(fake_engine.FakeEnv):
    """The stand-in engine with the blue unit two hexes from the red units, so every red unit can shoot it."""

    def setup(self, setup_info):
        super().setup(setup_info)
        self.units[fake_engine.BLUE_UNIT]["cur_hex"] = 104
        return self.state()


def group_game(policy, condition="C2", wingmen=2):
    red, blue = {"C1": (policy, policy), "C2": (policy, INERT_ID), "C3": (INERT_ID, policy)}[condition]
    record = play(lambda: CloseEnemy(red_wingmen=wingmen), ALL, spec(red=red, blue=blue), Inputs, PLAYERS,
                  replay_policies={policy})
    record["condition"] = condition
    return record


class ScheduleTest(unittest.TestCase):
    def test_structure(self) -> None:
        plan = sx.schedule("d" * 64, SYNTHETIC_CONFIGS)
        self.assertEqual(len(plan), 720)
        self.assertEqual([e["position"] for e in plan], list(range(1, 721)))
        cells = Counter((e["scenario_id"], e["condition"], e["group"], e["repetition"]) for e in plan)
        self.assertEqual(len(cells), 720)
        self.assertEqual(set(cells.values()), {1})
        for index, entry in enumerate(plan):
            self.assertEqual(entry["round"], index // 48 + 1)
            self.assertEqual(entry["repetition"], entry["round"])
            first = "B" if entry["round"] % 2 else "C"
            self.assertEqual(entry["group"], first if index % 2 == 0 else ("C" if first == "B" else "B"))
            self.assertEqual(entry["game_id"], f"{entry['scenario_id']}.{entry['condition']}.{entry['group']}.r{entry['repetition']}")
            self.assertEqual(entry["attempt"], 1)

    def test_rounds_follow_the_hash_rule(self) -> None:
        digest = "e" * 64
        plan = sx.schedule(digest, SYNTHETIC_CONFIGS)
        for round_number in range(1, 16):
            games = [e for e in plan if e["round"] == round_number]
            for group in sx.GROUPS:
                order = [(e["scenario_id"], e["condition"]) for e in games if e["group"] == group]
                expected = sorted(SYNTHETIC_CONFIGS, key=lambda c: hashlib.sha256(
                    f"{digest}:{round_number}:{group}:{c[0]}.{c[1]}".encode("utf-8")).hexdigest())
                if order != expected:
                    self.assertEqual((order[0], order[1]), (expected[1], expected[0]))
                    self.assertEqual(order[2:], expected[2:])

    def test_no_configuration_and_group_twice_in_a_row(self) -> None:
        for digest in ("0" * 64, "1" * 64, "a" * 64, "f" * 64):
            plan = sx.schedule(digest, SYNTHETIC_CONFIGS)
            for a, b in zip(plan, plan[1:]):
                self.assertNotEqual((a["scenario_id"], a["condition"], a["group"]),
                                    (b["scenario_id"], b["condition"], b["group"]))

    def test_groups_are_interleaved_over_time(self) -> None:
        plan = sx.schedule("b" * 64, SYNTHETIC_CONFIGS)
        for start in range(0, 720, 48):
            window = Counter(e["group"] for e in plan[start:start + 48])
            self.assertEqual(window, {"B": 24, "C": 24})
        for a, b in zip(plan, plan[1:]):
            if a["round"] == b["round"]:
                self.assertNotEqual(a["group"], b["group"])

    def test_the_boundary_swap_is_exercised(self) -> None:
        swaps = 0
        for index in range(60):
            digest = hashlib.sha256(str(index).encode("utf-8")).hexdigest()
            plan = sx.schedule(digest, SYNTHETIC_CONFIGS)
            for a, b in zip(plan, plan[1:]):
                self.assertNotEqual((a["scenario_id"], a["condition"], a["group"]),
                                    (b["scenario_id"], b["condition"], b["group"]))
            for round_number in range(2, 16):
                first = "B" if round_number % 2 else "C"
                raw = sorted(SYNTHETIC_CONFIGS, key=lambda c: hashlib.sha256(
                    f"{digest}:{round_number}:{first}:{c[0]}.{c[1]}".encode("utf-8")).hexdigest())
                start = next(e for e in plan if e["round"] == round_number)
                swaps += (start["scenario_id"], start["condition"]) != raw[0]
        self.assertGreater(swaps, 0)

    def test_deterministic_and_seeded_by_the_design(self) -> None:
        self.assertEqual(sx.schedule("c" * 64, SYNTHETIC_CONFIGS), sx.schedule("c" * 64, SYNTHETIC_CONFIGS))
        self.assertNotEqual(sx.schedule("c" * 64, SYNTHETIC_CONFIGS), sx.schedule("d" * 64, SYNTHETIC_CONFIGS))


class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = real_build()

    def test_rebuilds_identically(self) -> None:
        self.assertEqual(mf.digest(real_build()), mf.digest(self.manifest))
        self.assertEqual(self.manifest["design_sha256"], sx.design_digest(self.manifest))
        self.assertEqual(self.manifest["schedule"], sx.schedule(self.manifest["design_sha256"], sx.configurations(self.manifest)))

    def test_fifteen_repetitions_per_group_and_configuration(self) -> None:
        self.assertEqual(self.manifest["repetitions"], 15)
        self.assertEqual(self.manifest["games"], 720)
        cells = Counter((e["scenario_id"], e["condition"], e["group"]) for e in self.manifest["schedule"])
        self.assertEqual(len(cells), 48)
        self.assertEqual(set(cells.values()), {15})
        study = json.loads((ROOT / "evaluation" / "baseline-v1-variance-study-1" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(self.manifest["scenarios"], study["scenarios"])
        self.assertEqual([s["scenario_id"] for s in self.manifest["scenarios"]], [s["scenario_id"] for s in study["scenarios"]])
        self.assertEqual(self.manifest["planning"]["default_repetitions"], 15)

    def test_both_groups_run_runtime_r1(self) -> None:
        groups = self.manifest["groups"]
        runtime_digest, runtime_files = policy_source_digest(sources=rr.candidate_sources())
        self.assertEqual(runtime_digest, sx.RUNTIME_R1_SOURCE_SHA256)
        self.assertEqual(groups["B"]["policy_source"]["sha256"], runtime_digest)
        self.assertEqual(groups["B"]["policy"], routing_bounded.CANDIDATE_ID)
        self.assertEqual(groups["C"]["policy"], shoot_reservation.CANDIDATE_ID)
        self.assertEqual(sorted(set(groups["C"]["policy_source"]["files"]) - set(runtime_files)), [sx.CANDIDATE_FILE])
        self.assertTrue(set(runtime_files) <= set(groups["C"]["policy_source"]["files"]))
        self.assertEqual(groups["C"]["policy_source"]["sha256"],
                         policy_source_digest(sources=rr.candidate_sources() + (sx.CANDIDATE_FILE,))[0])
        self.assertEqual(groups["C"]["golden_trace_chain"], test_shoot_reservation.GOLDEN_TRACE_CHAIN)
        rev = load_script("run_evaluation")
        self.assertIsInstance(rev.FACTORIES[groups["B"]["policy"]](), BoundedRoutingAgent)
        self.assertIsInstance(rev.FACTORIES[groups["C"]["policy"]](), ShootReservationAgent)
        for group in sx.GROUPS:
            conditions = groups[group]["conditions"]
            policy = groups[group]["policy"]
            self.assertEqual(conditions, {"C1": {"red": policy, "blue": policy}, "C2": {"red": policy, "blue": INERT_ID},
                                          "C3": {"red": INERT_ID, "blue": policy}})

    def test_pins_the_counterfactual_and_the_mutation_results(self) -> None:
        directory = ROOT / "evaluation" / sx.EXPERIMENT_NAME
        for key, name in (("counterfactual_replay", "counterfactual-replay.json"), ("mutation", "mutation.json")):
            self.assertEqual(self.manifest[key]["sha256"], hashlib.sha256((directory / name).read_bytes()).hexdigest())
        self.assertEqual((self.manifest["counterfactual_replay"]["unexplained_states"],
                          self.manifest["counterfactual_replay"]["class_E"]), (0, 0))

    def test_refuses_unexplained_deltas_failed_mutation_or_another_runtime(self) -> None:
        inputs = load_script("build_shoot_experiment_manifest").inputs()
        bad = copy.deepcopy(inputs["counterfactual"])
        bad["totals"]["class_E"] = 1
        with self.assertRaises(ValueError):
            real_build(counterfactual=bad)
        failed = dict(inputs["mutation"], **{"pass": False})
        with self.assertRaises(ValueError):
            real_build(mutation=failed)
        runtime = dict(inputs["runtime"], policy_source_sha256="0" * 64)
        with self.assertRaises(ValueError):
            real_build(runtime=runtime)

    def test_the_primary_metric_is_the_planned_one(self) -> None:
        primary = self.manifest["primary_metric"]
        self.assertEqual(primary["metric"], "code_516_per_1000")
        self.assertIn("333", primary["denominator"])
        planning = self.manifest["planning"]["code_516_per_1000"]
        study = json.loads((ROOT / "evaluation" / "baseline-v1-variance-study-1" / "results.json").read_text(encoding="utf-8"))
        row = next(r for r in study["sizing"]["code_516_per_1000"]["table"] if r["repetitions"] == 15)
        self.assertEqual((planning["se"], planning["effects"]), (row["se"], row["effects"]))
        self.assertEqual(self.manifest["non_inferiority_margin"], 10.0)
        self.assertEqual(set(self.manifest["promotion"]), {f"P{i}" for i in range(1, 11)})


def seat(policy, seat_id=1, actions=None, codes=None, **fields):
    base = {"seat": seat_id, "policy": policy, "decisions": 4, "latency_us": [500, 800, 1_200_000, 900],
            "actions_by_type": actions or {"333": 1, "1": 10, "2": 8, "5": 2}, "steps_with_action": 3,
            "first_step_by_type": {"2": 2}, "units_acted": 3, "no_op_reasons": {"x": 30},
            "gate_rejections": {}, "feedback_errors_by_code": codes or {"516": 2}, "suppressions": 1,
            "contract_errors": 0, "replay_checks": 2, "replay_mismatches": 0, "duplicate_occupation_commands": 0,
            "refusals": [{"code": 516, "evidence": {"own_shots_at_target": 2}},
                         {"code": 516, "evidence": {"own_shots_at_target": 1}}],
            "refusal_facts": [{"action_type": 2, "code": 516, "message_class": "CantShootToDiedBop", "count": 2}],
            "refusal_attributions": {"target no longer alive at resolution": 2},
            "duplicate_shoot_target_steps": 1, "duplicate_shoot_target_commands": 2, "shoot_targets_engaged": 6,
            "steps_with_shot": 3, "shoot_reservation_effects": {"alternate-target": 2, "fallback-none": 1, "unchanged": 4},
            "shoot_excluded_options": 9, "steps_with_shoot_exclusion": 2}
    base.update(fields)
    return base


def record(condition, seats, red=100, blue=40):
    return {"game_id": "g", "condition": condition, "seats": seats, "steps": 10,
            "final_scores": {"red_total": red, "blue_total": blue, "red_win": red - blue, "blue_win": blue - red},
            "timings_seconds": {"wall": 5.0, "engine_step": 3.0, "decisions": 1.0, "harness": 1.0}}


class GameMetricsTest(unittest.TestCase):
    def test_denominator_is_unit_actions_of_the_policy_seats(self) -> None:
        policy = sx.CANDIDATE_ID
        values = sx.game_metrics(record("C2", [seat(policy), seat(INERT_ID, 11, codes={"516": 50})]), policy)["values"]
        self.assertEqual(values["unit_actions"], 20)
        self.assertEqual(values["code_516"], 2)
        self.assertAlmostEqual(values["code_516_per_1000"], 100.0)
        self.assertAlmostEqual(values["code_516_per_1000_shots"], 250.0)
        self.assertEqual(values["margin"], 60)
        c3 = sx.game_metrics(record("C3", [seat(INERT_ID), seat(policy, 11)]), policy)["values"]
        self.assertEqual(c3["margin"], -60)
        c1 = sx.game_metrics(record("C1", [seat(policy), seat(policy, 11)]), policy)["values"]
        self.assertEqual((c1["unit_actions"], c1["code_516"], c1["duplicate_shoot_target_commands"]), (40, 4, 4))

    def test_mechanism_and_evidence_fields(self) -> None:
        values = sx.game_metrics(record("C2", [seat(sx.CANDIDATE_ID)]), sx.CANDIDATE_ID)["values"]
        self.assertEqual((values["reserved_target_exclusions"], values["alternate_target_redirections"],
                          values["fallback_none"], values["unchanged_with_exclusion"]), (3, 2, 1, 4))
        self.assertEqual((values["unique_targets_engaged"], values["steps_with_shot"]), (6, 3))
        self.assertAlmostEqual(values["unique_targets_per_shot_step"], 2.0)
        self.assertEqual((values["code_516_repeat_fire"], values["code_516_single_fire"]), (1, 1))
        self.assertEqual(values["decisions_over_1000ms"], 1)

    def test_no_unit_action_leaves_the_rate_undefined(self) -> None:
        values = sx.game_metrics(record("C2", [seat(sx.CANDIDATE_ID, actions={"333": 1})]), sx.CANDIDATE_ID)["values"]
        self.assertIsNone(values["code_516_per_1000"])

    def test_missing_seat_fields_are_an_error(self) -> None:
        broken = seat(sx.CANDIDATE_ID)
        del broken["steps_with_shot"]
        with self.assertRaises(ValueError):
            sx.game_metrics(record("C2", [broken]), sx.CANDIDATE_ID)


class AnalysisTest(unittest.TestCase):
    def test_contrast_is_the_equal_weighted_difference(self) -> None:
        baseline = {"a": [2.0, 4.0], "b": [10.0, 10.0, 10.0]}
        candidate = {"a": [1.0, 1.0], "b": [4.0, 6.0]}
        result = sx.contrast(baseline, candidate, "x", resamples=400)
        self.assertAlmostEqual(result["delta"], ((1 - 3) + (5 - 10)) / 2)
        self.assertAlmostEqual(result["baseline_mean"], 6.5)
        self.assertAlmostEqual(result["relative_change"], -3.5 / 6.5)
        self.assertLessEqual(result["ci_low"], result["delta"])
        self.assertGreaterEqual(result["ci_high"], result["delta"])
        self.assertEqual(result, sx.contrast(baseline, candidate, "x", resamples=400))
        varied_b = {"a": [1.3, 2.9, 4.4, 0.7, 3.8, 2.2, 5.1], "b": [9.1, 12.4, 8.8, 10.6, 11.9]}
        varied_c = {"a": [1.1, 0.4, 2.6, 1.9, 0.8], "b": [4.2, 6.7, 3.3, 5.9, 7.4, 2.8]}
        self.assertNotEqual(sx.contrast(varied_b, varied_c, "x", resamples=400)["ci_low"],
                            sx.contrast(varied_b, varied_c, "y", resamples=400)["ci_low"])
        self.assertNotEqual(sx.metric_seed("x"), sx.metric_seed("y"))

    def test_the_registered_bootstrap_procedure_is_pinned(self) -> None:
        baseline = {"a": [1.3, 2.9, 4.4, 0.7, 3.8, 2.2, 5.1], "b": [9.1, 12.4, 8.8, 10.6, 11.9]}
        candidate = {"a": [1.1, 0.4, 2.6, 1.9, 0.8], "b": [4.2, 6.7, 3.3, 5.9, 7.4, 2.8]}
        result = sx.contrast(baseline, candidate, "pinned", resamples=1000)
        self.assertAlmostEqual(result["delta"], ((6.8 / 5 - 20.4 / 7) + (30.3 / 6 - 52.8 / 5)) / 2, places=12)
        self.assertAlmostEqual(result["ci_low"], -4.576904761904762, places=12)
        self.assertAlmostEqual(result["ci_high"], -2.3649999999999998, places=12)

    def test_constant_cells_and_undefined_games(self) -> None:
        result = sx.contrast({"a": [3.0, 3.0, None]}, {"a": [1.0, 1.0]}, "x", resamples=200)
        self.assertEqual((result["delta"], result["ci_low"], result["ci_high"]), (-2.0, -2.0, -2.0))
        self.assertEqual(result["per_configuration"]["a"]["baseline_n"], 2)

    def test_analytic_interval_is_reported(self) -> None:
        result = sx.contrast({"a": [1.0, 2.0, 3.0]}, {"a": [1.0, 2.0, 3.0]}, "x", resamples=200)
        self.assertAlmostEqual(result["delta"], 0.0)
        self.assertLess(result["analytic_ci_low"], 0.0)
        self.assertGreater(result["analytic_ci_high"], 0.0)
        self.assertEqual(result["analytic_df"], 4)

    def test_primary_verdict_boundaries(self) -> None:
        passing = {"configurations": 24, "ci_high": -0.01, "relative_change": -0.25}
        self.assertTrue(sx.primary_verdict(passing)["pass"])
        self.assertFalse(sx.primary_verdict(dict(passing, ci_high=0.0))["pass"])
        self.assertFalse(sx.primary_verdict(dict(passing, relative_change=-0.249))["pass"])
        self.assertFalse(sx.primary_verdict(dict(passing, configurations=23))["pass"])
        self.assertFalse(sx.primary_verdict(dict(passing, relative_change=None))["pass"])

    def test_non_inferiority_boundaries(self) -> None:
        self.assertTrue(sx.non_inferiority_verdict({"configurations": 16, "ci_low": -9.99})["pass"])
        self.assertFalse(sx.non_inferiority_verdict({"configurations": 16, "ci_low": -10.0})["pass"])
        self.assertFalse(sx.non_inferiority_verdict({"configurations": 15, "ci_low": 5.0})["pass"])

    def test_promotion_needs_every_criterion(self) -> None:
        checks = {f"P{i}": {"pass": True, "detail": None} for i in range(1, 11)}
        self.assertEqual(sx.promotion(checks)["disposition"], "PROMOTED AS baseline-v2")
        for name in list(checks):
            one_fails = dict(checks, **{name: {"pass": False}})
            result = sx.promotion(one_fails)
            self.assertEqual(result["disposition"], "RETAINED AS PARTIAL/NEGATIVE CANDIDATE", name)
            self.assertFalse(result["criteria"][name]["pass"])
        self.assertEqual(list(sx.promotion(checks)["criteria"]), [f"P{i}" for i in range(1, 11)])

    def test_latency_summary(self) -> None:
        summary = sx.latency_summary([1000, 2000, 150_000, 1_500_000])
        self.assertEqual((summary["decisions"], summary["over_100ms"], summary["over_1000ms"]), (4, 2, 1))
        self.assertEqual(summary["max_ms"], 1500.0)


class SyntheticTree(unittest.TestCase):
    """Fixtures: a synthetic private tree (records, started markers, ledger, push record); no tests here."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = load_script("analyze_shoot_experiment")
        cls.manifest = real_build()
        cls.digest = mf.digest(cls.manifest)
        cls.templates = {g: group_game(cls.manifest["groups"][g]["policy"]) for g in sx.GROUPS}

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (self.analysis.LOCAL, self.analysis.LEDGER, self.analysis.PUSH)
        self.analysis.LOCAL = self.tmp
        self.analysis.LEDGER = self.tmp / "ledger.jsonl"
        self.analysis.PUSH = self.tmp / "push.json"
        (self.tmp / "evaluation" / sx.EXPERIMENT_NAME / "games").mkdir(parents=True)
        (self.tmp / "evaluation" / sx.EXPERIMENT_NAME / "started").mkdir(parents=True)
        self.push("2026-10-01T00:00:00+00:00", 388)

    def tearDown(self) -> None:
        self.analysis.LOCAL, self.analysis.LEDGER, self.analysis.PUSH = self.saved
        shutil.rmtree(self.tmp)

    def push(self, when, ahead, commit="c" * 40):
        self.analysis.PUSH.write_text(json.dumps({"registration_commit": commit, "verified_on_remote_utc": when,
                                                  "host_clock_ahead_seconds": ahead}), encoding="utf-8")

    def record(self, entry, session):
        group = entry["group"]
        record = copy.deepcopy(self.templates[group])
        policy = self.manifest["groups"][group]["policy"]
        record.update(game_id=entry["game_id"], scenario_id=entry["scenario_id"], condition="C2",
                      repetition=entry["repetition"], session=session, python="3.10.20",
                      engine_version=self.manifest["engine"]["version"],
                      session_close={"state_changed": False, "home_changed": False, "integrity": {"ok": True}},
                      harness={"commit": "c" * 40, "dirty": False, "game_id": entry["game_id"], "group": group,
                               "manifest_sha256": self.digest,
                               "policy_source_sha256": self.manifest["groups"][group]["policy_source"]["sha256"]})
        for seat_record in record["seats"]:
            if seat_record["policy"] == policy:
                self.assertTrue(all(name in seat_record for name in sx.SEAT_FIELDS))
        return record

    def four(self):
        entries = [e for e in self.manifest["schedule"] if e["condition"] == "C2"][:4]
        return [self.record(e, f"{i + 2:04d}") for i, e in enumerate(entries)]

    def write(self, records, started=(), start_time="2026-10-01T00:30:00Z", ledger_games=None):
        games = self.tmp / "evaluation" / sx.EXPERIMENT_NAME / "games"
        for item in records:
            (games / f"{item['game_id']}.json").write_text(json.dumps(item), encoding="utf-8")
            (games.parent / "started" / item["game_id"]).write_text(start_time, encoding="utf-8")
        for name in started:
            (games.parent / "started" / name).write_text(start_time, encoding="utf-8")
        lines = [{"session": "0001", "event": "session-open", "harness": {}},
                 {"session": "0001", "event": "session-close", "state_changed": True, "outcome": {}}]
        for index, game in enumerate(ledger_games if ledger_games is not None else [r["game_id"] for r in records]):
            session = f"{index + 2:04d}"
            lines.append({"session": session, "event": "session-open",
                          "harness": {"manifest_sha256": self.digest, "game_id": game}})
            lines.append({"session": session, "event": "session-close", "state_changed": False,
                          "outcome": {"game_id": game}})
        self.analysis.LEDGER.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")

    def validate(self, records, allow_incomplete=True):
        return self.analysis.validate(self.manifest, {r["game_id"]: r for r in records}, allow_incomplete)

class ValidationTest(SyntheticTree):
    """The analysis script's checks of executed games."""

    def test_valid_partial_run(self) -> None:
        records = self.four()
        self.write(records)
        result = self.validate(records)
        self.assertEqual(result["problems"], [])
        self.assertTrue(result["registration_order"]["verified"])
        self.assertEqual(result["registration_order"]["minutes_between"], round((30 * 60 - 388) / 60.0, 1))
        self.assertFalse(result["complete"])
        self.assertIn("scheduled games have no record", " ".join(self.validate(records, False)["problems"]))

    def test_identity_failures_are_counted(self) -> None:
        records = self.four()
        records[0]["harness"]["policy_source_sha256"] = "0" * 64
        records[1]["harness"]["group"] = "X"
        records[2]["harness"]["dirty"] = True
        self.write(records)
        self.assertEqual(self.validate(records)["identity_failures"], {"policy digest": 1, "group": 1, "clean harness": 1})

    def test_failed_attempts_are_kept_and_reported(self) -> None:
        records = self.four()
        records[1]["status"] = "FAIL"
        extra = self.manifest["schedule"][60]["game_id"]
        self.write(records, started=[extra])
        result = self.validate(records)
        group = self.manifest["schedule"][[e["game_id"] for e in self.manifest["schedule"]].index(records[1]["game_id"])]["group"]
        self.assertEqual(result["status_by_group"][group].get("FAIL"), 1)
        self.assertEqual(result["started_without_record"], [extra])

    def test_registration_order_needs_the_push_first(self) -> None:
        records = self.four()
        self.write(records, start_time="2026-10-01T00:05:00Z")
        self.assertFalse(self.validate(records)["registration_order"]["verified"])
        self.push("2026-10-01T00:00:00+00:00", 0)
        self.assertTrue(self.validate(records)["registration_order"]["verified"])
        self.push("2026-10-01T00:00:00+00:00", 0, commit="d" * 40)
        self.assertFalse(self.validate(records)["registration_order"]["verified"])

    def test_a_replaced_attempt_is_found_in_the_ledger(self) -> None:
        records = self.four()
        for item, session in zip(records, ("0002", "0004", "0005", "0006")):
            item["session"] = session
        games = [r["game_id"] for r in records]
        self.write(records, ledger_games=[games[0], games[1], games[1], games[2], games[3]])
        result = self.validate(records)
        self.assertEqual(result["ledger"]["replaced_games"], [games[1]])
        self.assertEqual(result["ledger"]["experiment_sessions_without_record"], ["0003"])
        self.assertTrue(any("replaced" in p for p in result["problems"]))

    def test_engine_state_change_is_a_problem(self) -> None:
        records = self.four()
        self.write(records)
        lines = self.analysis.LEDGER.read_text(encoding="utf-8").splitlines()
        changed = json.loads(lines[-1])
        changed["state_changed"] = True
        self.analysis.LEDGER.write_text("\n".join(lines[:-1] + [json.dumps(changed)]) + "\n", encoding="utf-8")
        self.assertTrue(any("engine state changed" in p for p in self.validate(records)["problems"]))


class EndToEndAnalysisTest(SyntheticTree):
    """Every registered game recorded (synthetic): the whole analysis, P1-P10 and the disposition."""

    def full(self, baseline_516, candidate_change=None):
        records = []
        for index, entry in enumerate(self.manifest["schedule"]):
            item = self.record(entry, f"{index + 2:04d}")
            item["condition"] = entry["condition"]
            if entry["group"] == "B":
                for seat_record in item["seats"]:
                    if seat_record["policy"] == self.manifest["groups"]["B"]["policy"]:
                        seat_record["feedback_errors_by_code"] = {"516": baseline_516(index)}
            elif candidate_change is not None:
                candidate_change(item, index)
            records.append(item)
        self.write(records)
        return records

    def test_each_candidate_regression_fails_its_own_criterion(self) -> None:
        policy = self.manifest["groups"]["C"]["policy"]
        occupy_1804 = {"action_type": 5, "code": 1804, "message_class": "CantOccupyCauseAlreadyMy", "count": 1}
        regressions = {
            "P2": {"duplicate_shoot_target_commands": 1},
            "P3": {"contract_errors": 1},
            "P4": {"gate_rejections": {"synthetic": 1}},
            "P5 code 1804": {"feedback_errors_by_code": {"1804": 1}, "refusal_facts": [occupy_1804]},
            "P5 duplicate occupation": {"duplicate_occupation_commands": 1},
            "P8": {"feedback_errors_by_code": {"999": 1},
                   "refusal_facts": [{"action_type": 1, "code": 999, "message_class": "Synthetic", "count": 1}]},
        }
        self.assertEqual(self.manifest["schedule"][1]["group"], "C")
        for label, change in regressions.items():
            with self.subTest(regression=label):
                self.tearDown()
                self.setUp()

                def regress(item, index, change=change):
                    if index == 1:
                        next(s for s in item["seats"] if s["policy"] == policy).update(copy.deepcopy(change))

                self.full(lambda index: 3, regress)
                criteria = self.build()["promotion"]["criteria"]
                criterion = label.split()[0]
                self.assertFalse(criteria[criterion]["pass"], label)
                for name in ("P1", "P6", "P7", "P9", "P10"):
                    self.assertTrue(criteria[name]["pass"], (label, name))
                if label == "P8":
                    self.assertEqual(criteria["P8"]["detail"]["new_classes"], [[1, 999, "Synthetic"]])

    def test_a_game_that_never_started_fails_p3(self) -> None:
        records = self.full(lambda index: 3)
        missing = records[100]["game_id"]
        base = self.tmp / "evaluation" / sx.EXPERIMENT_NAME
        (base / "games" / f"{missing}.json").unlink()
        (base / "started" / missing).unlink()
        result = self.build()
        self.assertEqual(result["validation"]["started_without_record"], [])
        self.assertEqual(result["validation"]["missing"], [missing])
        self.assertFalse(result["promotion"]["criteria"]["P3"]["pass"])

    def build(self):
        original = sx.contrast
        with unittest.mock.patch.object(sx, "contrast", lambda *a, **k: original(*a, **dict(k, resamples=200))):
            return self.analysis.build(False, self.manifest)

    def test_the_primary_contrast_reads_code_516_only(self) -> None:
        records = self.full(lambda index: 2)
        policy = self.manifest["groups"]["B"]["policy"]
        for item in records:
            for seat_record in item["seats"]:
                if seat_record["policy"] == policy:
                    seat_record["feedback_errors_by_code"]["203"] = 5
        self.write(records)
        result = self.build()
        suite_516 = result["descriptive"]["B"]["code_516_per_1000"]["suite"]
        self.assertAlmostEqual(result["primary"]["baseline_mean"], suite_516, places=5)
        self.assertGreater(result["descriptive"]["B"]["refusals_per_1000"]["suite"], suite_516 + 1)

    def test_a_clear_reduction_with_equal_outcomes_is_promoted(self) -> None:
        self.full(lambda index: 2 + index % 3)
        result = self.build()
        self.assertTrue(result["validation"]["valid"], result["validation"]["problems"])
        self.assertTrue(result["validation"]["complete"])
        self.assertEqual((result["primary"]["configurations"], result["non_inferiority"]["configurations"]), (24, 16))
        self.assertLess(result["primary"]["ci_high"], 0)
        self.assertAlmostEqual(result["primary"]["relative_change"], -1.0)
        self.assertEqual(result["non_inferiority"]["delta"], 0.0)
        self.assertEqual(result["promotion"]["disposition"], "PROMOTED AS baseline-v2", result["promotion"])
        self.assertEqual(len(result["games"]), 720)
        self.assertEqual(result["totals"]["B"]["code_516"], sum(2 + i % 3 for i, e in enumerate(self.manifest["schedule"])
                                                                if e["group"] == "B"))

    def test_no_reduction_is_retained(self) -> None:
        self.full(lambda index: 0)
        result = self.build()
        self.assertFalse(result["promotion"]["criteria"]["P6"]["pass"])
        self.assertEqual(result["promotion"]["disposition"], "RETAINED AS PARTIAL/NEGATIVE CANDIDATE")

    def test_a_missing_game_fails_p3(self) -> None:
        records = self.full(lambda index: 3)
        missing = records[100]
        (self.tmp / "evaluation" / sx.EXPERIMENT_NAME / "games" / f"{missing['game_id']}.json").unlink()
        result = self.build()
        self.assertFalse(result["promotion"]["criteria"]["P3"]["pass"])
        self.assertFalse(result["validation"]["valid"])


class HarnessCounterTest(unittest.TestCase):
    def test_duplicates_and_reservations_are_counted(self) -> None:
        baseline = group_game(sx.RUNTIME_R1_CODE_ID)
        candidate = group_game(sx.CANDIDATE_ID)
        red_b, red_c = baseline["seats"][0], candidate["seats"][0]
        self.assertEqual(baseline["status"], "COMPLETED")
        self.assertGreater(red_b["duplicate_shoot_target_commands"], 0)
        self.assertEqual(red_b["shoot_reservation_effects"], {})
        self.assertEqual(red_c["duplicate_shoot_target_commands"], 0)
        self.assertGreater(sum(red_c["shoot_reservation_effects"].values()), 0)
        self.assertEqual(red_b["shoot_targets_engaged"], red_b["actions_by_type"]["2"] - red_b["duplicate_shoot_target_commands"])
        self.assertEqual(red_c["shoot_targets_engaged"], red_c["actions_by_type"]["2"])
        self.assertLessEqual(red_c["steps_with_shot"], red_c["shoot_targets_engaged"])
        self.assertEqual((red_c["replay_checks"] > 0, red_c["replay_mismatches"]), (True, 0))
        values = sx.game_metrics(candidate, sx.CANDIDATE_ID)["values"]
        self.assertEqual(values["reserved_target_exclusions"],
                         sum(red_c["shoot_reservation_effects"].get(e, 0) for e in sx.DISPLACED_EFFECTS))


class RunnerPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = real_build()

    def run_game(self, manifest, game_id=None, existing=False):
        rev = load_script("run_evaluation")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            game_id = game_id or manifest["schedule"][0]["game_id"]
            if existing:
                (Path(tmp) / "work" / "games").mkdir(parents=True)
                (Path(tmp) / "work" / "games" / f"{game_id}.json").write_text("{}", encoding="utf-8")
            args = Namespace(manifest=path, game_id=game_id, work=Path(tmp) / "work", engine_install=Path(tmp),
                             harness_commit="x", harness_dirty=False, purpose="evaluation")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = rev.cmd_game(args)
        return status, err.getvalue()

    def test_games_are_the_schedule(self) -> None:
        rev = load_script("run_evaluation")
        self.assertEqual(list(rev.all_games(self.manifest)), [e["game_id"] for e in self.manifest["schedule"]])

    def test_a_tampered_group_digest_is_refused(self) -> None:
        for group in sx.GROUPS:
            tampered = copy.deepcopy(self.manifest)
            tampered["groups"][group]["policy_source"]["sha256"] = "0" * 64
            game = next(e["game_id"] for e in tampered["schedule"] if e["group"] == group)
            status, message = self.run_game(tampered, game)
            self.assertEqual(status, 2)
            self.assertIn("differs from the registered one", message)

    def test_group_b_must_be_runtime_r1(self) -> None:
        other = copy.deepcopy(self.manifest)
        other["groups"]["B"]["policy_source"] = copy.deepcopy(other["groups"]["C"]["policy_source"])
        game = next(e["game_id"] for e in other["schedule"] if e["group"] == "B")
        status, message = self.run_game(other, game)
        self.assertEqual(status, 2)
        self.assertIn("baseline-v1-runtime-r1 only", message)

    def test_records_are_never_overwritten(self) -> None:
        status, message = self.run_game(self.manifest, existing=True)
        self.assertEqual(status, 2)
        self.assertIn("never overwritten", message)


if __name__ == "__main__":
    unittest.main()
