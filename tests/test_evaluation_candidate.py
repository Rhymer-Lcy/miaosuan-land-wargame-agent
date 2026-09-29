"""Harness support for evaluating a candidate policy: counters, refusal contexts, summaries, source checks."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.decision import BASELINE_ID, INERT_ID
from miaosuan_agent.evaluation import effects, metrics
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID, ReservationAgent

from tests.fixtures import fake_engine
from tests.test_evaluation_game import FACTORIES, Inputs, spec

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_evaluation", ROOT / "scripts" / "run_evaluation.py")
run_evaluation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_evaluation)  # type: ignore[union-attr]

ALL = dict(FACTORIES, **{CANDIDATE_ID: lambda: ReservationAgent(strict=True)})
DUPLICATE = f"1804/5/{effects.DUPLICATE_OCCUPATION}"


def wingmen_game(policy, repetition=1):
    return play(lambda: fake_engine.FakeEnv(red_wingmen=2), ALL, spec(red=policy, blue=INERT_ID, repetition=repetition),
                Inputs, PLAYERS, replay_policies={policy})


class DuplicateOccupationTest(unittest.TestCase):
    def test_v0_duplicates_are_refused_and_classified(self) -> None:
        red = wingmen_game(BASELINE_ID)["seats"][0]
        self.assertEqual(red["actions_by_type"]["5"], 3)
        self.assertEqual(red["feedback_errors_by_code"], {"1804": 2})
        self.assertEqual(red["refusal_contexts"], {DUPLICATE: 2})
        self.assertEqual((red["duplicate_occupation_steps"], red["duplicate_occupation_commands"]), (1, 2))
        self.assertEqual((red["suppressions"], red["steps_with_suppression"]), (0, 0))

    def test_candidate_issues_one_occupation(self) -> None:
        record = wingmen_game(CANDIDATE_ID)
        red = record["seats"][0]
        self.assertEqual(record["status"], "COMPLETED")
        self.assertEqual(red["actions_by_type"]["5"], 1)
        self.assertEqual((red["feedback_errors_by_code"], red["refusal_contexts"]), ({}, {}))
        self.assertEqual((red["duplicate_occupation_steps"], red["duplicate_occupation_commands"]), (0, 0))
        self.assertEqual((red["suppressions"], red["steps_with_suppression"]), (2, 1))
        self.assertEqual((red["replay_checks"], red["replay_mismatches"]), (1, 0))
        self.assertEqual(red["gate_rejections"], {})

    def test_candidate_criteria_and_summaries(self) -> None:
        records = [wingmen_game(CANDIDATE_ID, r) for r in (1, 2)]
        extra = metrics.LATER_SEAT_FIELDS
        gate = metrics.gate_check(records, CANDIDATE_ID, extra)
        self.assertEqual({k: v["pass"] for k, v in gate.items()}, {f"G{i}": True for i in range(1, 7)})
        self.assertIsNone(metrics.gate_check(records, "absent-policy")["G3"]["pass"])
        summary = metrics.condition_summary(records, CANDIDATE_ID, extended=True)
        self.assertEqual(summary["policy_under_test"], CANDIDATE_ID)
        self.assertEqual((summary["tested_suppressions"], summary["tested_steps_with_suppression"]), (4, 2))
        self.assertEqual(summary["tested_duplicate_occupation_commands"], 0)
        self.assertFalse([k for k in summary if k.startswith("baseline_")])
        self.assertTrue(0 < summary["tested_active_step_rate"] <= 1 and 0 <= summary["tested_no_op_rate"] <= 1)
        v0_summary = metrics.condition_summary([wingmen_game(BASELINE_ID)])
        self.assertIn("baseline_decisions", v0_summary)
        self.assertNotIn("policy_under_test", v0_summary)

    def test_g6_counts_registered_later_fields(self) -> None:
        record = wingmen_game(CANDIDATE_ID)
        stripped = copy.deepcopy(record)
        del stripped["seats"][0]["suppressions"]
        self.assertEqual(metrics.missing_fields(stripped), [])
        self.assertEqual(metrics.missing_fields(stripped, metrics.LATER_SEAT_FIELDS), ["seats[0].suppressions"])


class RefusalContextTest(unittest.TestCase):
    hexes = {1: 505, 2: 505, 3: 707, 9: 506}
    flags = {505: -1, 707: 0}

    def label(self, code, action, own):
        return effects.refusal_context({"message": action, "error": {"code": code}}, code, 0, self.hexes, self.flags, own)

    def test_occupation_classes(self) -> None:
        occupy = lambda i: {"type": 5, "obj_id": i, "actor": 7}  # noqa: E731
        self.assertEqual(self.label(1804, occupy(2), [occupy(1), occupy(2)]), DUPLICATE)
        self.assertEqual(self.label(1804, occupy(3), [occupy(3)]), f"1804/5/{effects.OBJECTIVE_ALREADY_OWN}")
        self.assertEqual(self.label(1804, occupy(2), [occupy(2)]), f"1804/5/{effects.UNEXPLAINED}")
        self.assertEqual(self.label(1804, occupy(42), [occupy(42)]), f"1804/5/{effects.UNEXPLAINED}")

    def test_shot_classes(self) -> None:
        shot = lambda i, t: {"type": 2, "obj_id": i, "target_obj_id": t, "weapon_id": 1}  # noqa: E731
        self.assertEqual(self.label(516, shot(1, 9), [shot(1, 9), shot(2, 9)]), f"516/2/{effects.TARGET_SHOT_TWICE}")
        self.assertEqual(self.label(516, shot(1, 9), [shot(1, 9)]), f"516/2/{effects.UNEXPLAINED}")
        self.assertEqual(self.label(516, shot(1, 77), [shot(1, 77)]), f"516/2/{effects.TARGET_ABSENT}")
        self.assertEqual(self.label(203, shot(1, 9), [shot(1, 9)]), f"203/2/{effects.SHOOTER_DESTROYED}")
        self.assertEqual(self.label(203, shot(55, 9), []), f"203/2/{effects.SHOOTER_ABSENT}")

    def test_anything_else_is_unclassified(self) -> None:
        self.assertEqual(self.label(999, {"type": 5, "obj_id": 1}, []), f"999/5/{effects.UNCLASSIFIED}")
        self.assertEqual(self.label(516, {"type": 1, "obj_id": 1}, []), f"516/1/{effects.UNCLASSIFIED}")


class DecompositionTest(unittest.TestCase):
    taxonomy = {"1804": {"category": "same-step conflict: duplicate own occupation"}}

    def test_categories_contexts_and_unknown_codes(self) -> None:
        record = wingmen_game(BASELINE_ID)
        extra = copy.deepcopy(record)
        extra["seats"][0]["feedback_errors_by_code"]["777"] = 3
        result = metrics.refusal_decomposition([record, extra], BASELINE_ID, self.taxonomy)
        self.assertEqual(result["engine_refusals"], 7)
        self.assertEqual(result["by_code"], {"1804": 4, "777": 3})
        self.assertEqual(result["by_code_category"], {"same-step conflict: duplicate own occupation": 4,
                                                      "unclassified": 3})
        self.assertEqual(result["by_start_of_step_context"], {DUPLICATE: 4})
        self.assertEqual(result["project_gate_rejections"], 0)

    def test_records_without_contexts_report_none(self) -> None:
        record = wingmen_game(BASELINE_ID)
        del record["seats"][0]["refusal_contexts"]
        self.assertIsNone(metrics.refusal_decomposition([record], BASELINE_ID, self.taxonomy)["by_start_of_step_context"])

    def test_public_summary_carries_later_fields_only_when_recorded(self) -> None:
        record = wingmen_game(CANDIDATE_ID)
        public = metrics.public_game(record)["seats"][0]
        self.assertEqual(public["suppressions"], 2)
        for name in metrics.LATER_SEAT_FIELDS:
            del record["seats"][0][name]
        self.assertFalse(set(metrics.LATER_SEAT_FIELDS) & set(metrics.public_game(record)["seats"][0]))


class RegisteredSourceTest(unittest.TestCase):
    def test_v0_manifest_source_recomputes(self) -> None:
        manifest = json.loads((ROOT / "evaluation" / "baseline-v0" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(run_evaluation.registered_policy_source(manifest), manifest["policy_source"]["sha256"])
        tampered = copy.deepcopy(manifest)
        tampered["policy_source"]["files"] = tampered["policy_source"]["files"][:-1]
        self.assertNotEqual(run_evaluation.registered_policy_source(tampered), manifest["policy_source"]["sha256"])


if __name__ == "__main__":
    unittest.main()
