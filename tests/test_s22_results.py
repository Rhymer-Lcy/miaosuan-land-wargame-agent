"""The committed Sprint 22 result files (``evaluation/s22-t2-transport-probe/``) agree with the frozen rules: the
disposition is the one ``s22_probe.disposition`` gives on the published endpoints, the endpoints are the frozen endpoint
functions applied to the published facts, the game is the card's one game in session 2796 with no structural stop,
reconstruction difference or prefix problem, and the documentation states the same disposition."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s22_probe as sp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / sp.STUDY_ID


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


class ResultsTest(unittest.TestCase):
    def test_game_is_the_registered_session_without_any_problem(self) -> None:
        games = load("games.json")
        card = json.loads((ROOT / "evaluation" / sp.CARD_ID / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(games["game_id"], card["games"][0]["game_id"])
        self.assertEqual((games["session"], games["status"], games["steps"]), ("2796", "COMPLETED", 2881))
        self.assertEqual(games["structural_stops"], [])
        self.assertEqual(games["ledger_sessions_after_base"], 1)
        self.assertEqual((games["offline_differences"], games["live_consistency_errors"],
                          games["live_unregistered_differences"], games["prefix_problems"]), (0, 0, 0, 0))
        self.assertEqual(games["decisions_reconstructed_offline"], games["steps"])
        self.assertEqual(games["memory_compared"], games["steps"])

    def test_endpoints_and_disposition_follow_from_the_published_facts(self) -> None:
        mech, disp = load("mechanism.json"), load("disposition.json")
        facts = mech["facts"]
        endpoints = {"embark": sp.embark_endpoint(facts["embark"]), "carry": sp.carry_endpoint(facts["carry"]),
                     "stacking": sp.stacking_endpoint(facts["stacking"]),
                     "disembark": sp.disembark_endpoint(facts["disembark"])}
        self.assertEqual(endpoints, mech["endpoints"])
        verdict = sp.disposition(None, [], endpoints["embark"], endpoints["carry"], endpoints["stacking"],
                                 endpoints["disembark"])
        self.assertEqual(verdict["disposition"], disp["disposition"])
        self.assertEqual(disp["order"], list(sp.DISPOSITIONS))
        self.assertEqual(disp["disposition"], sp.SUPPORTED)

    def test_the_state_sequence_and_timing_agree_with_the_facts(self) -> None:
        mech = load("mechanism.json")
        states = {s["state"]: s["cur_step"] for s in mech["descriptive"]["candidate_states"]}
        facts = mech["facts"]
        self.assertEqual(list(states), ["EMBARK_REQUESTED", "CARRIER_RELEASED", "AT_DESTINATION", "DISEMBARK_REQUESTED",
                                        "DONE"])
        self.assertEqual(states["CARRIER_RELEASED"] - states["EMBARK_REQUESTED"], facts["embark"]["aboard_after"])
        self.assertEqual(states["AT_DESTINATION"] - states["CARRIER_RELEASED"], facts["carry"]["release_to_arrival_steps"])
        self.assertEqual(states["DISEMBARK_REQUESTED"] - states["AT_DESTINATION"], facts["disembark"]["listed_after"])
        self.assertEqual(states["DONE"] - states["DISEMBARK_REQUESTED"], facts["disembark"]["ground_after"])
        self.assertEqual(mech["descriptive"]["destination"], sp.RULES["witness"]["destination"])

    def test_documentation_states_the_disposition(self) -> None:
        text = (ROOT / "docs" / "SPRINT22_T2_TRANSPORT_PROBE.md").read_text(encoding="utf-8")
        results = text.split("## Results", 1)[1]
        self.assertIn(f"**{load('disposition.json')['disposition']}.**", results)
        self.assertIn("T2_P1_MECHANISM_SUPPORTED", (ROOT / "docs" / "TACTICAL_FRONTIER.md").read_text(encoding="utf-8"))

    def test_public_files_carry_no_forbidden_key(self) -> None:
        for name in ("games.json", "mechanism.json", "disposition.json"):
            self.assertEqual(sp.public_check(load(name)), [], name)


if __name__ == "__main__":
    unittest.main()
