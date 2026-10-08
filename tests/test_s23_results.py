"""The committed Sprint 23 result files (``evaluation/s23-t2-policy-design/``) agree with the frozen rules: the
disposition is the readiness rule applied to the committed first-divergence episodes; the pooled rows are the sums of
the side rows; every consistency check and known answer holds; no public file carries a forbidden key; and no screen is
proposed unless the disposition is ready.
"""

from __future__ import annotations

import collections
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s23_design as sd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / sd.STUDY_ID


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


@unittest.skipUnless((OUT / "disposition.json").exists(), "the study has not run")
class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prevalence, cls.episodes, cls.disposition = load("prevalence.json"), load("episodes.json"), \
            load("disposition.json")

    def test_disposition_is_the_rule_applied_to_the_committed_episodes(self) -> None:
        first = self.episodes["first_divergence"]
        verdict = sd.disposition([], first)
        self.assertEqual(self.disposition["disposition"], verdict["disposition"])
        self.assertEqual({k: self.disposition[k] for k in verdict}, verdict)
        self.assertEqual(self.disposition["readiness"], sd.READINESS)
        self.assertEqual(self.disposition["invalid_problem_count"], 0)
        expected_screen = sd.screen(first, []) if verdict["disposition"] == sd.READY else None
        if expected_screen is None:
            self.assertIsNone(self.disposition["screen"])
        self.assertTrue(all(e["first_divergence"] and e["evidence"] == "first divergence" for e in first))
        self.assertEqual(len(first), sum(s["first_batch_size"] for s in self.prevalence["sides"]
                                         if s["first_trigger_valid"]))

    def test_consistency_and_known_answers(self) -> None:
        self.assertTrue(all(c["equal"] for c in self.prevalence["consistency"].values()))
        self.assertEqual(len(self.prevalence["consistency"]), 6)
        self.assertTrue(all(a["agrees"] for a in self.prevalence["known_answers"].values()))
        self.assertEqual(len(self.prevalence["known_answers"]), 3)

    def test_pooled_rows_are_the_sums_of_the_side_rows(self) -> None:
        sides = self.prevalence["sides"]
        self.assertEqual(len(sides), 23)
        for population, pooled in self.prevalence["pooled"].items():
            part = [s for s in sides if population == "all" or s["population"] == population]
            funnel: collections.Counter = collections.Counter()
            for s in part:
                funnel.update(s["funnel"])
            self.assertEqual(pooled["funnel"], dict(funnel), population)
            self.assertEqual(pooled["decisions"], sum(s["decisions"] for s in part))
            self.assertEqual(pooled["first_divergence_pairs"],
                             sum(s["first_batch_size"] for s in part if s["first_trigger_valid"]))

    def test_summary_counts_match_the_rows(self) -> None:
        first = self.episodes["first_divergence"]
        summary = self.episodes["first_divergence_summary"]
        self.assertEqual(summary["episodes"], len(first))
        self.assertEqual(summary["claimant_elsewhere"], sum(1 for e in first if e["claimant_elsewhere"]))
        self.assertEqual(summary["saturated_at_arrival"], sum(1 for e in first if e["saturated_at_arrival"]))
        self.assertEqual(summary["roles"], dict(sorted(collections.Counter(e["role"] for e in first).items())))
        self.assertNotIn("C", summary["roles"])  # excluded by condition 7

    def test_no_forbidden_key_and_shares_unreduced(self) -> None:
        for name in ("prevalence.json", "episodes.json", "disposition.json"):
            self.assertEqual(sd.public_problems(load(name), range(50)), [], name)
        for key in ("saturated_share", "claimant_share"):
            if key in self.disposition:
                part, whole = self.disposition[key].split("/")
                self.assertEqual(int(whole), self.disposition["first_divergence_episodes"])


if __name__ == "__main__":
    unittest.main()
