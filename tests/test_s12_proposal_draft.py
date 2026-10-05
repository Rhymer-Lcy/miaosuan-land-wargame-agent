"""The Sprint 12 screen proposal is a draft that authorizes nothing (``docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md``).

These tests read the committed draft companion (``evaluation/s12-batch-allocator-draft/draft.json``), the checkout and
the proposal document. They check that the companion regenerates byte for byte, that it cannot be mistaken for a run
card, that the candidate is still in no run card, that the proposed schedule keeps its ceiling and its order, and that
the rule values printed in the document are the companion's.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402

DRAFT = ROOT / "evaluation" / "s12-batch-allocator-draft" / "draft.json"
DOC = ROOT / "docs" / "SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md"
SCRIPT = ROOT / "scripts" / "t9_batch_screen_draft.py"
LABEL = "DRAFT — UNAPPROVED — NO ENGINE AUTHORIZATION"
V3 = "t9-batch-capacity-v3"
V3_DIGEST = "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8"
V2 = "baseline-v2-candidate-shoot-target-reservation"


def load_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalised(text: str) -> str:
    """Whitespace-normalised text, so that a phrase wrapped across lines still matches."""
    return " ".join(text.split())


class DraftCompanionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.draft = json.loads(DRAFT.read_text(encoding="utf-8"))

    def test_the_companion_regenerates_byte_for_byte(self) -> None:
        run = subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("OK evaluation/s12-batch-allocator-draft/draft.json", run.stdout)

    def test_the_companion_is_not_a_run_card(self) -> None:
        self.assertEqual(self.draft["status"], LABEL)
        self.assertEqual(self.draft["schema"], "miaosuan-proposal-draft/1")
        self.assertIs(self.draft["executable"], False)
        self.assertIs(self.draft["approved"], False)
        self.assertIs(self.draft["registered"], False)
        self.assertFalse(xp.is_card(self.draft))
        self.assertEqual(sorted(p.name for p in DRAFT.parent.iterdir()), ["draft.json"])

    def test_identities_are_the_frozen_ones(self) -> None:
        self.assertEqual(self.draft["candidate"], {"id": V3, "policy_source_sha256": V3_DIGEST})
        self.assertEqual(self.draft["baseline"]["policy_source_sha256"], self.draft["frozen_identities"]["baseline-v2"])
        module = load_script(SCRIPT)
        self.assertEqual(module.FROZEN[V3], V3_DIGEST)

    def test_the_schedule_keeps_its_ceiling_and_order(self) -> None:
        schedule = self.draft["schedule"]
        self.assertEqual((schedule["ledger_base_session"], schedule["session_ceiling"]), (2786, 12))
        stages = schedule["stages"]
        self.assertEqual([s["stage"] for s in stages], ["P1", "P2", "A1", "A2"])
        self.assertEqual(sum(s["max_sessions"] for s in stages), 12)
        self.assertEqual(schedule["sessions_if_no_stop_and_no_replication"], 9)
        games = [g for s in stages for g in s["games"]]
        self.assertEqual([g["position"] for g in games], list(range(1, 13)))
        for stage in stages:
            self.assertEqual(len(stage["games"]), stage["max_sessions"])
            for game in stage["games"]:
                self.assertEqual(sorted(p == V3 for p in (game["red"], game["blue"])), [False, True], game)
                other = game["blue"] if game["red"] == V3 else game["red"]
                if stage["stage"].startswith("P"):
                    self.assertEqual((game["scenario_id"], other), ("2130511121", V2))
                    self.assertEqual(game["red"] == V3, game["condition"] == "H1")
                else:
                    self.assertEqual(other, "inert-v0")
            if stage["stage"].startswith("P"):
                seats = [g["condition"] for g in stage["games"]]
                self.assertEqual(seats.count("H1"), seats.count("H2"))
        adverse = [(g["scenario_id"], g["condition"]) for s in stages[2:] for g in s["games"]]
        self.assertEqual(sorted(set(adverse)), [("1930331196", "C2"), ("1930331196", "C3"), ("2120531121", "C3")])

    def test_the_rule_checks_are_recorded_for_both_reference_populations(self) -> None:
        checks = self.draft["primary"]["rule_checks"]
        self.assertEqual(len(checks), 2)
        for check in checks.values():
            rates = check["rates"]
            self.assertEqual(check["draws"], 20000)
            self.assertAlmostEqual(rates["interim stop"] + rates["NOT_PRESERVED"] + rates["AMBIGUOUS"]
                                   + rates["PRESERVED_DIRECTIONALLY"], 1.0, places=3)


class CandidateOnlyInApprovedCardsTest(unittest.TestCase):
    """Before the owner's approval this test required that v3 be in no run card. The registration approved on
    2026-10-05 replaced that with an exact whitelist (tests/test_t9_batch.py holds the full check): v3 may appear only
    in the four Sprint 12 stage cards; the draft companion stays proposal evidence, never a card."""

    def test_only_approved_cards_name_the_candidate_and_old_runners_never_do(self) -> None:
        sys.path.insert(0, str(ROOT / "src"))
        from miaosuan_agent.evaluation import s12_screen as sc
        approved = set(sc.CARD_IDS.values())
        cards = sorted((ROOT / "evaluation").glob("*/manifest.json"))
        self.assertGreater(len(cards), 10)
        for path in cards:
            text = path.read_text(encoding="utf-8")
            if V3 in text or V3_DIGEST in text or "s12" in path.parent.name:
                self.assertIn(path.parent.name, approved, path)
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py"):
            self.assertNotIn("t9_batch", (ROOT / "scripts" / name).read_text(encoding="utf-8"), name)
        self.assertFalse((DRAFT.parent / "manifest.json").exists())


class DocumentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = DOC.read_text(encoding="utf-8")
        cls.text = normalised(cls.raw)
        cls.draft = json.loads(DRAFT.read_text(encoding="utf-8"))

    def test_the_document_is_labelled_a_draft_without_authorization(self) -> None:
        head = self.raw.splitlines()[:4]
        self.assertIn(f"**{LABEL}**", head)
        self.assertIn("evaluation/s12-batch-allocator-draft/draft.json", self.text)
        self.assertIn(V3_DIGEST, self.text)

    def test_the_printed_rule_values_are_the_companions(self) -> None:
        values = self.draft["primary"]["rule_values"]
        self.assertIn(f"below {values['h1_coverage_floor']:.3f} (exactly {str(values['h1_coverage_floor'])[:6]}...",
                      self.text)
        self.assertIn(f"blue margin is below {values['h2_margin_floor']}", self.text)
        self.assertIn(f"red margin below {values['h1_collapse_below']:,}", self.text)
        self.assertIn(f"blue margin below {values['h2_collapse_below']}", self.text)
        self.assertIn(f"at least +{values['preserved_seat_average_at_least']}", self.text)

    def test_the_printed_rule_checks_are_the_companions(self) -> None:
        checks = list(self.draft["primary"]["rule_checks"].values())
        for check, label in zip(checks, ("T9-v1 (3 + 3 draws", "`baseline-v2` (3 + 3 draws")):
            rates = check["rates"]
            row = next(line for line in self.raw.splitlines() if line.startswith(f"| {label}"))
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            expected = [f"{100 * rates[key]:.2f}%" for key in
                        ("stopped before the adverse stage", "AMBIGUOUS", "PRESERVED_DIRECTIONALLY")]
            self.assertEqual(cells[1:], expected, label)

    def test_the_printed_adverse_limits_are_the_companions(self) -> None:
        adverse = self.draft["adverse"]
        self.assertIn(f"margin at least {adverse['2120531121 C3']['thresholds']['margin_at_least']}", self.text)
        limits = adverse["1930331196 C3"]["thresholds"]
        self.assertIn(f"attack at least {limits['attack_at_least']} | REGRESSED: occupy below 310, or attack at most "
                      f"{limits['attack_at_most_regressed']} |", self.text)
        limits = adverse["1930331196 C2"]["thresholds"]
        self.assertIn(f"attack at least {limits['attack_at_least']} | REGRESSED: occupy below 310, or attack "
                      f"{limits['attack_at_most_regressed']} |", self.text)


if __name__ == "__main__":
    unittest.main()
