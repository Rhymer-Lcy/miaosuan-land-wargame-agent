"""Sprint 36 live results: the committed public files agree with the registered functions (reads the committed files)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s36_live as sl
from miaosuan_agent.evaluation import s36_study as st
from miaosuan_agent.tactical.config import LIVE
from miaosuan_agent.tactical.policy import candidate_id

REPO = Path(__file__).resolve().parents[1]
FOLDER = REPO / "evaluation" / sl.CARD_ID


class ResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = json.loads((FOLDER / "results.json").read_text(encoding="utf-8"))
        cls.summary = json.loads((FOLDER / "summary.json").read_text(encoding="utf-8"))
        cls.games = cls.results["games"]

    def test_the_study_stopped_at_the_a2_gate_with_severe_harm(self):
        state = self.results["state"]
        self.assertEqual(state["disposition"]["disposition"], "S36_SEVERE_HARM")
        self.assertEqual(state["stop"]["kind"], "harm")
        self.assertEqual((state["stop"]["position"], state["stop"]["at"], state["stop"]["batch"]), (43, "batch", "A2"))
        self.assertEqual(state["stop"]["findings"], ["1930331196 H1: both candidate margins below the reference minimum"])
        self.assertFalse(state["complete"])
        self.assertIsNone(state["next_position"])
        self.assertEqual(state["protocol_problems"], [])
        self.assertEqual(self.summary["disposition"], state["disposition"])

    def test_exactly_the_schedule_prefix_was_played_in_its_sessions(self):
        schedule = sl.schedule(candidate_id(LIVE))
        self.assertEqual(len(self.games), 43)
        self.assertEqual([g["position"] for g in self.games], list(range(1, 44)))
        self.assertEqual([int(g["session"]) for g in self.games], list(range(2846, 2889)))
        for game, row in zip(self.games, schedule):
            self.assertEqual((game["scenario_id"], game["condition"], game["tag"], game["batch"]),
                             (row["scenario_id"], row["condition"], row["tag"], row["batch"]))
            self.assertEqual(game["status"], "COMPLETED")
            self.assertEqual(game["reconstruction_mismatches"], 0)
            self.assertEqual(game["fallbacks"], 0)
        statuses = self.results["state"]["positions"]
        self.assertEqual([p for p in range(1, 52) if statuses[str(p)] == st.AFTER_STOP],
                         list(range(44, 52)))
        self.assertEqual(statuses["43"], st.STOPPED_HERE)
        self.assertEqual([p for p in range(1, 43) if statuses[str(p)] != st.PLAYED], [])
        self.assertEqual(self.summary["positions_not_played"], list(range(44, 52)))

    def test_the_comparison_and_the_gates_recompute_from_the_public_games(self):
        def plain(value):
            return json.loads(json.dumps(value))

        self.assertEqual(plain(sl.comparison(self.games, ("A1",))), self.summary["comparison_after_A1"])
        self.assertEqual(plain(sl.comparison(self.games)), self.summary["comparison_after_A1_A2_descriptive"])
        refs = self.summary["references"]
        facts = [dict(g, reference=refs[f"{g['scenario_id']} {g['candidate_side']}"]) for g in self.games]
        a1 = [f for f in facts if f["batch"] == "A1"]
        self.assertIsNone(sl.batch_gate("A1", a1))
        self.assertIsNone(self.summary["batch_gate_A1"])
        gate = sl.batch_gate("A2", facts)
        self.assertEqual(list(gate), ["harm", self.results["state"]["stop"]["findings"]])
        self.assertEqual(self.summary["batch_gate_A2"], [gate[0], gate[1]])
        below = [(f["position"], f["candidate"]["win"]) for f in facts if f["tag"] == "s36"
                 and (f["scenario_id"], f["condition"]) == ("1930331196", "H1")]
        self.assertEqual(below, [(10, -762), (33, -520)])
        self.assertEqual(refs["1930331196 red"]["win"]["min"], -508.0)
        for f in facts:
            if f["tag"] == "s36":
                ref = f["reference"]["win"]
                self.assertGreaterEqual(f["candidate"]["win"], ref["min"] - sl.SEVERE_SD * ref["sd"])
        self.assertGreater(self.summary["comparison_after_A1"]["dbar"], sl.EARLY_FUTILITY)

    def test_the_publication_keeps_every_registered_key(self):
        load = __import__("importlib.util").util
        spec = load.spec_from_file_location("t36r_analysis", REPO / "scripts" / "s36_analysis.py")
        analysis = load.module_from_spec(spec)
        spec.loader.exec_module(analysis)
        for game in self.games:
            self.assertEqual(sorted(game), sorted(analysis.PUBLIC_KEYS))


if __name__ == "__main__":
    unittest.main()
