"""The registered variance-study manifest: pinned identities, reuse of the frozen games, run order.

Fails if the registration changes after it was committed, if baseline-v1's policy source, golden
chain or evaluation artifacts change, or if the reused historical games stop matching the frozen
results. The private part re-derives the historical record digests from the records themselves.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import candidate_manifest as cm
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import variance_study as vs
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "evaluation" / vs.STUDY_NAME
V1 = ROOT / "evaluation" / cm.EVALUATION_NAME
#: Canonical digest of the registered manifest (the registration commit is its record).
REGISTERED_MANIFEST_SHA256 = "78109fca78dc8b044b63dcf475c163ca91a6f7f60fe1454a4b126d7ada10f48e"


class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((STUDY / "manifest.json").read_text(encoding="utf-8"))
        cls.v1 = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
        cls.v1_results = json.loads((V1 / "results.json").read_text(encoding="utf-8"))

    def test_registration_is_unchanged_and_rebuilds(self) -> None:
        self.assertEqual(mf.digest(self.manifest), REGISTERED_MANIFEST_SHA256)
        text = (STUDY / "manifest.json").read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(self.manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_variance_study_manifest.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_baseline_v1_is_pinned_and_unchanged(self) -> None:
        digest, files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
        self.assertEqual((digest, files), (self.manifest["policy_source"]["sha256"], self.manifest["policy_source"]["files"]))
        self.assertEqual(digest, vs.BASELINE_V1_SOURCE_SHA256)
        self.assertEqual(self.manifest["baseline"]["golden_trace_chain"], cm.GOLDEN_TRACE_CHAIN)
        self.assertEqual(self.manifest["scenario_manifest_sha256"], mf.digest(self.v1))
        self.assertEqual(self.manifest["baseline"]["evaluation_results_sha256"],
                         hashlib.sha256((V1 / "results.json").read_bytes()).hexdigest())
        self.assertEqual(self.manifest["scenarios"], self.v1["scenarios"])
        self.assertEqual(self.manifest["engine"], self.v1["engine"])
        self.assertEqual(self.manifest["conditions"], [c for c in self.v1["conditions"] if c["id"] in ("C1", "C2", "C3")])
        self.assertEqual(self.manifest["policy_under_test"], self.v1["policy_under_test"])

    def test_repetition_plan(self) -> None:
        m = self.manifest
        self.assertEqual((m["repetition_target"], m["historical_repetitions"], m["new_repetitions"]),
                         (10, [1, 2], list(range(3, 11))))
        configs = vs.configurations(m)
        self.assertEqual(len(configs), 24)
        self.assertEqual(m["design_sha256"], vs.design_digest(m))
        self.assertEqual(m["schedule"], vs.schedule(m["design_sha256"], configs))
        self.assertEqual(m["new_games"], len(m["schedule"]))
        counts = {}
        for entry in m["schedule"]:
            counts[(entry["scenario_id"], entry["condition"])] = counts.get((entry["scenario_id"], entry["condition"]), 0) + 1
        self.assertEqual(set(counts.values()), {8})
        self.assertEqual(sorted(counts), sorted(configs))

    def test_reused_games_are_the_frozen_suite(self) -> None:
        history = self.manifest["historical_records"]
        self.assertEqual(history["source_evaluation"], cm.EVALUATION_NAME)
        self.assertEqual(history["source_results_sha256"], vs.BASELINE_V1_RESULTS_SHA256)
        rows = history["records"]
        frozen = {g["game_id"]: g for g in self.v1_results["suite"]["games"]}
        self.assertEqual(sorted(r["game_id"] for r in rows), sorted(frozen))
        for row in rows:
            game = frozen[row["game_id"]]
            self.assertEqual((row["scenario_id"], row["condition"], row["repetition"], row["status"]),
                             (game["scenario_id"], game["condition"], game["repetition"], game["status"]))
            self.assertRegex(row["record_sha256"], r"^[0-9a-f]{64}$")
        active = [r for r in rows if r["condition"] in ("C1", "C2", "C3")]
        self.assertEqual(len(active), 48)
        self.assertEqual({(r["scenario_id"], r["condition"]) for r in active}, set(vs.configurations(self.manifest)))
        self.assertEqual({r["repetition"] for r in active}, {1, 2})
        sessions = sorted(int(r["session"]) for r in rows)
        self.assertEqual(sessions, list(range(sessions[0], sessions[0] + 64)))
        self.assertEqual({r["harness_commit"][:7] for r in rows}, {vs.BASELINE_V1_EXECUTED_COMMIT})
        self.assertEqual(history, json.loads((STUDY / "historical-records.json").read_text(encoding="utf-8")))

    def test_effect_grid_and_its_stated_anchors(self) -> None:
        m = self.manifest
        self.assertEqual(m["effect_grid"], vs.EFFECT_GRID)
        self.assertEqual(m["force_value_by_scenario"], vs.force_values(self.v1_results))
        forces = sorted(m["force_value_by_scenario"].values())
        median = (forces[3] + forces[4]) / 2
        points = m["effect_grid"]["margin"]["absolute_points"]
        self.assertLess(min(points), forces[0])
        self.assertLess(max(points), median / 2)


@unittest.skipUnless((ROOT / "local" / "evaluation" / cm.EVALUATION_NAME / "games").is_dir(),
                     "private: needs the historical game records")
class PrivateHistoryTest(unittest.TestCase):
    def test_pinned_record_digests_match_the_records(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pin_study_history.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
