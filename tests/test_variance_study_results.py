"""The committed results of the variance study agree with its registration and with themselves.

Public checks read only committed files. The private check regenerates the results from the game
records and requires them to be byte-identical to the committed file.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import variance_study as vs

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "evaluation" / vs.STUDY_NAME


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = json.loads((STUDY / "results.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((STUDY / "manifest.json").read_text(encoding="utf-8"))

    def test_validation_is_complete_and_names_the_registration(self) -> None:
        validation = self.results["validation"]
        self.assertTrue(validation["valid"] and validation["complete"], validation["problems"])
        self.assertEqual(validation["manifest_sha256"], mf.digest(self.manifest))
        self.assertEqual(validation["policy_source_at_analysis"], vs.BASELINE_V1_SOURCE_SHA256)
        self.assertEqual((validation["scheduled"], validation["recorded"], validation["missing"]), (192, 192, []))
        self.assertEqual((validation["historical_records"], validation["historical_records_verified"]), (64, 64))
        self.assertEqual(validation["status"], {"COMPLETED": 192})

    def test_games_cover_the_registered_plan(self) -> None:
        games = self.results["games"]
        new = {g["game_id"]: g for g in games if g["source"] == "new"}
        self.assertEqual(sorted(new), sorted(e["game_id"] for e in self.manifest["schedule"]))
        positions = {e["game_id"]: e["position"] for e in self.manifest["schedule"]}
        self.assertTrue(all(g["position"] == positions[k] for k, g in new.items()))
        sessions = sorted(int(g["session"]) for g in new.values())
        by_position = [new[e["game_id"]]["session"] for e in self.manifest["schedule"]]
        self.assertEqual([int(s) for s in by_position], sessions, "sessions follow the registered order")
        historical = [g["game_id"] for g in games if g["source"] == "historical"]
        self.assertEqual(sorted(historical), sorted(r["game_id"] for r in self.manifest["historical_records"]["records"]))

    def test_every_active_configuration_has_ten_values(self) -> None:
        configs = {vs.config_id(*c) for c in vs.configurations(self.manifest)}
        for metric in ("margin", "refusals_per_1000", "wall_seconds"):
            entries = self.results["configurations"][metric]["configurations"]
            with self.subTest(metric=metric):
                self.assertEqual(set(entries), configs)
                self.assertTrue(all(e["n"] == 10 and e["missing"] == 0 for e in entries.values()))

    def test_derived_fields_agree_with_their_inputs(self) -> None:
        self.assertEqual(self.results["default_repetitions"],
                         vs.default_repetitions(self.results["sizing"][vs.DEFAULT_RULE_METRIC]))
        games = [g for g in self.results["games"] if g["condition"] in vs.ACTIVE_CONDITIONS]
        facts = {}
        for game in games:
            for item in game["facts"]:
                key = f"{item['action_type']}|{item['code']}|{item['message_class']}"
                facts[key] = facts.get(key, 0) + item["count"]
        self.assertEqual(facts, {k: sum(v.values()) for k, v in self.results["refusal_facts_by_configuration"].items()})
        self.assertEqual(sum(facts.values()), sum(g["values"]["refusals"] for g in games))
        self.assertEqual(sum(g["values"]["code_1804"] for g in games), 0)
        margins = self.results["configurations"]["margin"]["configurations"]
        suite = self.results["configurations"]["margin"]["suite"]
        self.assertAlmostEqual(suite["mean"], sum(e["mean"] for e in margins.values()) / 24, places=5)
        self.assertTrue(self.results["margin_fields_consistent"])


@unittest.skipUnless((ROOT / "local" / "evaluation" / vs.STUDY_NAME / "games").is_dir(),
                     "private: needs the variance-study game records")
class PrivateRegenerationTest(unittest.TestCase):
    def test_results_regenerate_byte_identically(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze_variance_study.py"), "--check"],
                                capture_output=True, text=True, timeout=900, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
