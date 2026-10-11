"""Sprint 36 live card: identities, pins, the owner's authorization and refusals (reads the committed card)."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from miaosuan_agent.evaluation import s36_live as sl
from miaosuan_agent.tactical.config import LIVE, VARIANTS
from miaosuan_agent.tactical.policy import candidate_id

REPO = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(f"t36_{name}", REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = load("build_s36_card")
        cls.card = json.loads(cls.cards.CARD.read_text(encoding="utf-8"))

    def test_the_committed_card_rebuilds_and_has_no_problem(self):
        self.assertEqual(self.cards.dump(self.cards.build()), self.cards.CARD.read_text(encoding="utf-8"))
        self.assertEqual(self.cards.card_problems(self.card), [])

    def test_identities_and_sources(self):
        self.assertIn(LIVE, VARIANTS.values())
        selection = json.loads((REPO / "evaluation" / "s36-tactical-recovery" / "selection.json").read_text(encoding="utf-8"))
        self.assertIs(VARIANTS[selection["selected"]], LIVE)
        self.assertEqual(self.card["candidate"], candidate_id(LIVE))
        policies = self.card["policies"]
        self.assertEqual(set(policies), {sl.V2, sl.S34_CONTROL, sl.S35_CONTROL, candidate_id(LIVE)})
        self.assertEqual(policies[sl.V2]["policy_source"]["sha256"],
                         "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae")
        self.assertEqual(policies[sl.S34_CONTROL]["policy_source"]["sha256"],
                         "b107d23ecdb57d9efb42610818eae60b64311480529d26dfdb6e2976ebcdad3b")
        self.assertEqual(policies[sl.S35_CONTROL]["policy_source"]["sha256"],
                         "ea38c04216385a8aa119d624c9e437c118268a3a8caec682cf98f1834df8400c")
        candidate_files = policies[candidate_id(LIVE)]["policy_source"]["files"]
        self.assertTrue(any("tactical" in f for f in candidate_files))
        self.assertFalse(any("tactical" in f for f in policies[sl.S35_CONTROL]["policy_source"]["files"]))

    def test_schedule_budget_authorized_and_frozen_files(self):
        self.assertEqual([g["game_id"] for g in self.card["games"]],
                         [g["game_id"] for g in sl.schedule(candidate_id(LIVE))])
        self.assertEqual(self.card["budget"], {"batch_sessions": 51, "ledger_base_session": 2845,
                                               "sprint_session_cap": 51})
        self.assertEqual(self.card["screen"]["expected_sessions"], list(range(2846, 2897)))
        self.assertIs(self.card["screen"]["authorized"], True)
        self.assertEqual(sorted(self.card["screen"]["frozen_files"]), sorted(self.cards.FROZEN_FILES))
        self.assertFalse(self.card["eligible_for_promotion"])

    def test_problems_are_found(self):
        for change, needle in (
                (lambda c: c.update(candidate="other"), "candidate"),
                (lambda c: c["screen"].update(control="other"), "controls"),
                (lambda c: c["screen"].update(replication="other"), "controls"),
                (lambda c: c["games"].pop(), "schedule"),
                (lambda c: c["budget"].update(sprint_session_cap=52), "budget"),
                (lambda c: c["screen"].update(rules_sha256="0" * 64), "rules"),
                (lambda c: c["screen"].update(rules_digest="0" * 64), "rules"),
                (lambda c: c["screen"]["frozen_files"].update({self.cards.FROZEN_FILES[0]: "0" * 64}), "frozen"),
                (lambda c: c["screen"].update(id="other"), "Sprint 36 card")):
            card = copy.deepcopy(self.card)
            change(card)
            problems = self.cards.card_problems(card)
            self.assertTrue(problems and any(needle in p for p in problems), (needle, problems))

    def runner_with_card(self, card):
        """The runner, reading ``card`` from a temporary file as if it were the committed card."""
        runner = load("run_s36")
        cards = load("build_s36_card")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "manifest.json"
        path.write_text(cards.dump(card), encoding="utf-8")
        cards.CARD = path
        cards.build = lambda repo=None: copy.deepcopy(card)
        real = runner.load
        runner.load = lambda name: cards if name == "build_s36_card" else real(name)
        refused = []
        runner.refuse = lambda message: refused.append(message) or 2
        runner.git_dirty = lambda repo: False
        runner.outside_ignored = lambda repo: []
        return runner, refused, Path(tmp.name)

    def test_the_runner_refuses_an_unauthorized_card(self):
        card = copy.deepcopy(self.card)
        card["screen"]["authorized"] = False
        runner, refused, tmp = self.runner_with_card(card)
        args = SimpleNamespace(position=1, python="python", sdk_archive=Path("none"), engine_install=tmp,
                               work=tmp / "work")
        launched = []
        self.assertEqual(runner.run_position(args, launch=lambda *a: launched.append(a) or 0, stage_inputs=False), 2)
        self.assertEqual(refused, ["no session of the Sprint 36 card is authorized"])
        self.assertEqual(launched, [])

    def test_the_runner_accepts_the_authorized_card_and_still_checks_the_ledger(self):
        runner, refused, tmp = self.runner_with_card(self.card)
        (tmp / "usage-ledger.jsonl").write_text("", encoding="utf-8")
        launched = []
        args = SimpleNamespace(position=2, python="python", sdk_archive=Path("none"), engine_install=tmp,
                               work=tmp / "work")
        self.assertEqual(runner.run_position(args, launch=lambda *a: launched.append(a) or 0, stage_inputs=False), 2)
        self.assertTrue(refused and "ledger audit 0 sessions" in refused[0], refused)
        args.position = 1
        refused.clear()
        # no engine: the stand-in launch opens no session, so the runner's post-game ledger check must fail
        self.assertEqual(runner.run_position(args, launch=lambda *a: launched.append(a) or 0, stage_inputs=False), 3)
        self.assertEqual(refused, [])
        self.assertEqual([a[2] for a in launched], [sl.schedule(candidate_id(LIVE))[0]["game_id"]])

    def test_the_authorization_changes_only_the_allowlisted_paths(self):
        auth = load("s36_authorization")
        try:
            original = json.loads(auth.git_show(auth.ORIGINAL_COMMIT, auth.CARD_PATH).decode("utf-8"))
            original_builder = auth.git_show(auth.ORIGINAL_COMMIT, auth.BUILDER_PATH)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("the registration commit is not in this checkout's history")
        builder = (REPO / auth.BUILDER_PATH).read_bytes()
        problems, changes = auth.compare(original, self.card, original_builder, builder)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(tuple(c["path"]) for c in changes), sorted(auth.ALLOWED))
        stored = json.loads((REPO / "evaluation" / sl.CARD_ID / "authorization.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, auth.result(self.cards.CARD.read_text(encoding="utf-8")))
        for change, needle in (
                (lambda c: c["games"][0].update(scenario_id="2010211129"), "outside the authorization"),
                (lambda c: c["games"].pop(), "outside the authorization"),
                (lambda c: c["screen"].update(rules_sha256="0" * 64), "outside the authorization"),
                (lambda c: c["budget"].update(sprint_session_cap=52), "outside the authorization"),
                (lambda c: c.update(status=c["status"] + " "), "status text"),
                (lambda c: c["screen"].update(authorized=False), "not exactly the allowlist")):
            card = copy.deepcopy(self.card)
            change(card)
            found, _ = auth.compare(original, card, original_builder, builder)
            self.assertTrue(any(needle in p for p in found), (needle, found))
        found, _ = auth.compare(original, self.card, original_builder, builder.replace(b"WORKERS = 1", b"WORKERS = 2"))
        self.assertTrue(any("beyond the declared edits" in p for p in found), found)

if __name__ == "__main__":
    unittest.main()
