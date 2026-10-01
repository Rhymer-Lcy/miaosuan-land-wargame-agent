"""The committed results of the residual-516 diagnostic, checked against their own figures and the registered rules.

The byte-identical regeneration from the private records and captures runs only where they exist.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import residual516 as rd

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / rd.DIAGNOSTIC_ID
CAPTURES = ROOT / "local" / "evaluation" / rd.DIAGNOSTIC_ID / "capture"


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        cls.results = json.loads((DIRECTORY / "results.json").read_text(encoding="utf-8"))

    def test_results_cite_the_registration(self) -> None:
        r = self.results
        self.assertEqual(r["manifest_sha256"], mf.digest(self.manifest))
        self.assertEqual(len(r["harness_commits"]), 1)
        self.assertEqual(r["games"], {"registered": 32, "recorded": 32, "completed": 32, "not_completed": [],
                                      "missing": []})

    def test_integrity_and_instrumentation(self) -> None:
        integrity, instr = self.results["integrity"], self.results["instrumentation"]
        self.assertTrue(integrity["pass"])
        self.assertEqual((integrity["records"], integrity["sessions"], integrity["states"], integrity["problems"],
                          integrity["leftover_processes"]), (32, 32, 1, 0, 0))
        self.assertEqual((integrity["runtime"], integrity["thread_env"], integrity["workers"], integrity["scheduler"]),
                         (self.manifest["execution"]["runtime"], {"OPENBLAS_NUM_THREADS": "1"}, 32,
                          self.manifest["execution"]["scheduler"]))
        self.assertTrue(instr["pass"] and all(instr["checks"].values()))
        self.assertEqual((instr["prefix_equal"], instr["games"]), (32, 32))
        self.assertEqual((instr["in_game_replay_mismatches"], instr["offline_mismatches"], instr["observer_errors"]),
                         (0, 0, 0))
        self.assertGreater(instr["offline_decisions"], 0)
        self.assertEqual(instr["prefix_steps"], self.manifest["reference"]["state_prefix_steps"])
        self.assertEqual(self.results["validity"], {"instrumentation": True, "integrity": True, "complete": True})

    def test_classification_and_conclusion_follow_the_rules(self) -> None:
        r = self.results
        n = r["refusals"]["residual_516"]
        categories = r["classification"]
        self.assertEqual(sorted(categories), list(rd.CATEGORIES))
        self.assertEqual(sum(c["count"] for c in categories.values()), n)
        for name, c in categories.items():
            self.assertEqual(c["strong"] + c["moderate"], c["count"] if name != "H7" else 0)
        listing = [{"category": name, "strength": strength} for name, c in categories.items()
                   for strength, count in (("strong", c["strong"]), ("moderate", c["moderate"]),
                                           ("none", c["count"] - c["strong"] - c["moderate"])) for _ in range(count)]
        self.assertEqual(len(listing), n)
        self.assertEqual(r["conclusion"], rd.conclusion(listing, all(r["validity"].values())))
        self.assertEqual(sum(r["h7_matches"].values()), categories["H7"]["count"])

    def test_counts_are_consistent(self) -> None:
        r = self.results
        n = r["refusals"]["residual_516"]
        refusals, cross, evidence = r["refusals"], r["cross_seat"], r["evidence"]
        self.assertEqual(refusals["by_class"], [{"action_type": 2, "code": 516, "message_class": "CantShootToDiedBop",
                                                 "count": n}])
        self.assertTrue(refusals["complete_against_records"])
        for key in ("single_own_shot", "passed_project_gate", "legal_at_start", "target_on_map_at_start",
                    "target_absent_after"):
            self.assertEqual(refusals[key], n, key)
        self.assertEqual(sum(refusals["target_classes"].values()), n)
        self.assertEqual(cross["events_with_friendly_other_seat_fire"] + cross["events_without_friendly_other_seat_fire"], n)
        self.assertEqual(cross["collisions"], cross["collisions_with_516"] + cross["collisions_without_516"])
        self.assertLessEqual(cross["collision_steps"], cross["collisions"])
        self.assertEqual((cross["same_seat_repeats"], cross["opposing_unit_actions"]), (0, 0))
        self.assertEqual(sum(evidence["linked_relations_removed"].values()), sum(evidence["linked_classes_removed"].values()))
        self.assertLessEqual(evidence["events_with_a_linked_object_removed"], evidence["events_with_a_linked_object"])
        self.assertLessEqual(r["classification"]["H4"]["count"], evidence["events_with_a_linked_object_removed"])
        self.assertEqual(r["architecture"]["playing_seats_by_faction"], {"0": 1, "1": 1})
        judge = r["supplementary"]["judge_info_against_shots"]
        self.assertEqual(judge["accepted shots"], judge["records"])
        self.assertEqual(judge["steps whose records equal their accepted shots"], judge["steps with an accepted shot or a record"])
        self.assertEqual(judge["accepted shots"] + n, cross["shots"])

    @unittest.skipUnless(CAPTURES.is_dir(), "the records and captures are private (git-ignored)")
    def test_results_regenerate_from_the_private_captures(self) -> None:
        spec = importlib.util.spec_from_file_location("diag", ROOT / "scripts" / "residual516_diagnostic.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.cmd_analyze(type("A", (), {"check": True})()), 0)


if __name__ == "__main__":
    unittest.main()
