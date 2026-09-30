"""The historical refusal facts agree with the committed results, which stay byte-identical.

The correction of the code-203 interpretation (docs/REFUSAL_TAXONOMY.md) derives new analysis from
the historical records; it must never alter a registered artifact. The digests below are those of
the committed files at the time of the correction.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "evaluation" / "refusal-taxonomy-correction" / "historical-refusal-facts.json"
CANDIDATE = "evaluation/baseline-v1-candidate-occupy-reservation"
PINNED_FILES = {
    "evaluation/baseline-v0/results.json": "13dad290a452e953d50e9043321258038fce19ae0257592509e14bb5ccb77fbe",
    "evaluation/baseline-v0/diagnostics.json": "5d08e21e583dd42585f4d9edda79f7f47344a4a71a8db671ea9560d7154c8408",
    f"{CANDIDATE}/results.json": "ea0ec674e8e51e546684fb75696673e5c81d32d6c9dd7a0d11796a91aeaeda07",
    f"{CANDIDATE}/results-gate1-attempt-1.json": "b8578841b813492e64e702c4f73ca7b7ed61ede9088f19063fe91f6c251bedc1",
}
PINNED_MANIFESTS = {
    "evaluation/baseline-v0/manifest.json": "01c1f88b064ace501e56018576426cea6291bbabdce0e35387f72bec2d0068e6",
    f"{CANDIDATE}/manifest.json": "38526b9250d8bce7facdb0f5c6303b5f2040e3939bd2bcedfe1fc2fdb14f103f",
}


def public_games(data, part):
    return data["engine_messages"]["games"] if part == "engine_messages" else data[part]["games"]


def add(counts, key, value):
    counts[key] = counts.get(key, 0) + value


class HistoricalArtifactsTest(unittest.TestCase):
    def test_registered_results_are_unchanged(self) -> None:
        for relative, expected in PINNED_FILES.items():
            with self.subTest(file=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)
        for relative, expected in PINNED_MANIFESTS.items():
            with self.subTest(file=relative):
                self.assertEqual(mf.digest(json.loads((ROOT / relative).read_text(encoding="utf-8"))), expected)


class HistoricalFactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = json.loads(FACTS.read_text(encoding="utf-8"))

    def test_every_set_pins_a_committed_file(self) -> None:
        self.assertEqual(len(self.facts["sets"]), 6)
        for item in self.facts["sets"]:
            with self.subTest(set=(item["evaluation"], item["part"])):
                self.assertEqual(item["public_sha256"], PINNED_FILES[item["public_file"]])

    def test_counts_agree_with_the_committed_results(self) -> None:
        for item in self.facts["sets"]:
            with self.subTest(set=(item["evaluation"], item["part"])):
                data = json.loads((ROOT / item["public_file"]).read_text(encoding="utf-8"))
                games = public_games(data, item["public_part"])
                seats = [s for g in games for s in g["seats"] if s["policy"] == item["policy"]]
                self.assertEqual((len(games), len(seats)), (item["games"], item["seats_of_policy"]))
                by_code, typed = {}, {}
                for seat in seats:
                    for key, count in (seat.get("feedback_errors_by_code_and_type") or {}).items():
                        add(typed, key, count)
                    codes = seat.get("feedback_errors_by_code")
                    for code, count in (codes.items() if codes is not None
                                        else ((k.split("/")[0], v) for k, v in seat["feedback_errors_by_code_and_type"].items())):
                        add(by_code, code, count)
                self.assertEqual(by_code, item["by_code"])
                if item["by_code_and_type"] is not None:
                    self.assertEqual(typed, item["by_code_and_type"])
                else:
                    self.assertEqual(typed, {}, "the type was recorded after all")
                per_code = {}
                for fact in item["facts"]:
                    add(per_code, str(fact["code"]), fact["count"])
                    self.assertEqual(sum(fact["messages"].values()) + fact["message_not_retained"], fact["count"])
                self.assertEqual(per_code, item["by_code"])
                self.assertEqual(item["complete"], all(f["message_not_retained"] == 0 and f["action_type"] is not None
                                                       for f in item["facts"]))

    def test_code_203_is_not_one_factual_class(self) -> None:
        sets = {(s["evaluation"], s["part"]): s for s in self.facts["sets"]}
        suite = sets[("baseline-v1-candidate-occupy-reservation", "suite")]
        self.assertTrue(suite["complete"])
        classes = {(f["action_type"], message) for f in suite["facts"] if f["code"] == 203 for message in f["messages"]}
        self.assertEqual(classes, {(2, "CantControlDiedOperator"), (5, "CantControlDiedOperator")})
        unknown = [f for f in sets[("baseline-v0", "suite")]["facts"] if f["code"] == 203]
        self.assertEqual([(f["action_type"], f["messages"]) for f in unknown], [(None, {})])

    def test_superseded_statements_point_at_existing_files(self) -> None:
        self.assertEqual(len(self.facts["superseded"]), 3)
        for entry in self.facts["superseded"]:
            paths = [word.strip(",;") for word in entry["where"].replace("(", " ").replace(")", " ").split()
                     if "/" in word]
            self.assertTrue(paths)
            for path in paths:
                self.assertTrue((ROOT / path).is_file(), path)


@unittest.skipUnless((ROOT / "local" / "evaluation" / "baseline-v1-candidate-occupy-reservation" / "games").is_dir(),
                     "private: needs the historical game records")
class PrivateRebuildTest(unittest.TestCase):
    def test_file_rebuilds_from_the_records(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "derive_historical_refusal_facts.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
