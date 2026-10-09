"""The committed Sprint 27 result files (``evaluation/s27-t6s-probe/``) agree with the frozen rules: every published
game is the card's game in its registered session with its registered seats; P1, P2, the mechanism rule and the stage
gate are the frozen functions applied to the published facts; the disposition is ``s27_probe.disposition`` over the
published games; and the documentation states the same disposition. Skipped before the first game file exists."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s27_probe as sp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / sp.STUDY_ID


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def games():
    return [load(f"game-p{p:02d}.json") for p in (1, 2) if (OUT / f"game-p{p:02d}.json").exists()]


@unittest.skipUnless((OUT / "game-p01.json").exists() and (OUT / "disposition.json").exists(), "no results yet")
class ResultsTest(unittest.TestCase):
    def test_games_are_the_registered_sessions(self) -> None:
        card = json.loads((ROOT / "evaluation" / sp.CARD_ID / "manifest.json").read_text(encoding="utf-8"))
        for game in games():
            entry = card["games"][game["position"] - 1]
            self.assertEqual(game["game_id"], entry["game_id"])
            self.assertEqual(game["session"], sp.LEDGER_BASE_SESSION + game["position"])
            self.assertEqual(game["candidate_side"], sp.candidate_side(entry))
            self.assertEqual(game["stage"], {1: "A", 2: "B"}[game["position"]])
            self.assertEqual(game["ledger_sessions_after_base"], game["position"])
        self.assertEqual([g["position"] for g in games()], list(range(1, len(games()) + 1)))

    def test_endpoints_follow_from_the_published_facts(self) -> None:
        for game in games():
            side = game["candidate_side"]
            p1 = sp.p1(game["p1"]["candidate_e4"], sp.RULES["p1"]["references"][side])
            self.assertEqual(p1, game["p1"])
            self.assertEqual(game["descriptive"]["exposure"].get("moving_stacked_inside_envelope", 0),
                             game["p1"]["candidate_e4"])
            first = {r["objective"]: r["candidate_first_ownership_step"] for r in game["p2"]["rows"]}
            self.assertEqual(sp.p2(first, sp.RULES["p2"]["references"][side]), game["p2"])
            self.assertEqual(sp.mechanism_observed(game["episodes"]), game["mechanism_observed"])
            gate = sp.stage_gate(game["structural_stops"], game["status"] == "COMPLETED", game["p1"], game["p2"],
                                 game["mechanism_observed"])
            self.assertEqual(gate, game["stage_gate"])
            self.assertEqual(sp.fidelity_problems(game["fidelity"]) == [], "SF" not in game["structural_stops"])

    def test_disposition_follows_from_the_games(self) -> None:
        disp = load("disposition.json")
        sessions = [{"structural_stops": g["structural_stops"], "completed": g["status"] == "COMPLETED",
                     "mechanism_observed": g["mechanism_observed"], "p1_triggered": g["p1"]["triggered"],
                     "p2_triggered": g["p2"]["triggered"]} for g in games()]
        authorized = games()[0]["stage_gate"]["stage_b_authorized"]
        verdict = sp.disposition(sessions, authorized, len(games()) == 2)
        self.assertEqual(verdict["disposition"], disp["disposition"])
        self.assertEqual(verdict["paired_probe_terminated_early"], disp["paired_probe_terminated_early"])
        self.assertEqual(disp["stage_b_authorized"], authorized)
        self.assertEqual(disp["order"], list(sp.DISPOSITIONS))
        self.assertLessEqual(len(games()), sp.SESSION_CEILING)
        if not authorized:
            self.assertEqual(len(games()), 1)

    def test_documentation_states_the_disposition(self) -> None:
        text = (ROOT / "docs" / "SPRINT27_T6S_PROBE.md").read_text(encoding="utf-8")
        results = text.split("## Results", 1)[1]
        self.assertIn(f"**{load('disposition.json')['disposition']}.**", results)

    def test_public_files_carry_no_forbidden_key_or_digit_word(self) -> None:
        for path in sorted(OUT.glob("game-p*.json")) + [OUT / "disposition.json"]:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sp.public_problems(data, ()), [], path.name)


if __name__ == "__main__":
    unittest.main()
