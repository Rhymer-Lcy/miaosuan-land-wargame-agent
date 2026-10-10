"""Sprint 35 live card: identities, pins and refusals (reads the committed card; no engine)."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.coalition.config import LIVE, VARIANTS
from miaosuan_agent.coalition.policy import candidate_id
from miaosuan_agent.evaluation import s35_live as sl

REPO = Path(__file__).resolve().parents[1]


def cards():
    spec = importlib.util.spec_from_file_location("t35_cards", REPO / "scripts" / "build_s35_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = cards()
        cls.card = json.loads(cls.cards.CARD.read_text(encoding="utf-8"))

    def test_the_committed_card_rebuilds_and_has_no_problem(self):
        self.assertEqual(self.cards.dump(self.cards.build()), self.cards.CARD.read_text(encoding="utf-8"))
        self.assertEqual(self.cards.card_problems(self.card), [])

    def test_identities_and_sources(self):
        self.assertIn(LIVE, VARIANTS.values())
        self.assertEqual(self.card["candidate"], candidate_id(LIVE))
        policies = self.card["policies"]
        self.assertEqual(set(policies), {sl.V2, sl.S34_CONTROL, candidate_id(LIVE)})
        self.assertEqual(policies[sl.V2]["policy_source"]["sha256"], self.cards.V2_DIGEST)
        self.assertEqual(policies[sl.S34_CONTROL]["policy_source"]["sha256"], self.cards.S34_DIGEST)
        self.assertEqual(self.cards.S34_DIGEST, "b107d23ecdb57d9efb42610818eae60b64311480529d26dfdb6e2976ebcdad3b")
        candidate_files = policies[candidate_id(LIVE)]["policy_source"]["files"]
        self.assertTrue(any("/coalition/" in f or f.startswith("coalition/") for f in candidate_files))
        self.assertFalse(any("coalition" in f for f in policies[sl.S34_CONTROL]["policy_source"]["files"]))

    def test_schedule_budget_and_frozen_files(self):
        self.assertEqual([g["game_id"] for g in self.card["games"]], [g["game_id"] for g in sl.schedule(candidate_id(LIVE))])
        self.assertEqual(self.card["budget"], {"batch_sessions": 48, "ledger_base_session": 2826, "sprint_session_cap": 48})
        self.assertEqual(self.card["screen"]["expected_sessions"], list(range(2827, 2875)))
        self.assertEqual(sorted(self.card["screen"]["frozen_files"]), sorted(self.cards.FROZEN_FILES))
        self.assertFalse(self.card["eligible_for_promotion"])

    def test_problems_are_found(self):
        for change, needle in (
                (lambda c: c.update(candidate="other"), "candidate"),
                (lambda c: c["screen"].update(control="other"), "control"),
                (lambda c: c["games"].pop(), "schedule"),
                (lambda c: c["budget"].update(sprint_session_cap=49), "budget"),
                (lambda c: c["screen"].update(rules_sha256="0" * 64), "rules"),
                (lambda c: c["screen"]["frozen_files"].update({self.cards.FROZEN_FILES[0]: "0" * 64}), "frozen"),
                (lambda c: c["screen"].update(id="other"), "Sprint 35 card")):
            card = copy.deepcopy(self.card)
            change(card)
            problems = self.cards.card_problems(card)
            self.assertTrue(problems and any(needle in p for p in problems), (needle, problems))


if __name__ == "__main__":
    unittest.main()
