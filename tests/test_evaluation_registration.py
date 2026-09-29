"""The registered evaluation manifest agrees with the code that will be evaluated.

The first class needs only the committed manifest: it fails when the policy source changes without
a new registration. The second rebuilds the manifest from the private SDK archive and is skipped
without it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent import sdk_provenance as prov
from miaosuan_agent.decision import BASELINE_ID, INERT_ID
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation.identity import policy_source_digest, policy_source_files

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "evaluation" / "baseline-v0" / "manifest.json"
ARCHIVE = prov.default_archive_dir(REPO) / prov.SDK_ARCHIVE_NAME


class RegisteredManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_policy_source_is_the_registered_one(self) -> None:
        digest, files = policy_source_digest()
        self.assertEqual(files, self.manifest["policy_source"]["files"])
        self.assertEqual(digest, self.manifest["policy_source"]["sha256"],
                         "the policy changed after registration: assign a new identity, register again and rerun")

    def test_policy_source_covers_the_decision_path(self) -> None:
        files = policy_source_files()
        self.assertIn("agent.py", files)
        self.assertIn("decision/gate.py", files)
        self.assertIn("boundary/observation.py", files)
        self.assertFalse([f for f in files if f.startswith("evaluation/")])

    def test_structure(self) -> None:
        m = self.manifest
        self.assertEqual((m["schema"], m["policy_under_test"], m["control_policy"]), (mf.SCHEMA, BASELINE_ID, INERT_ID))
        self.assertEqual(m["engine"]["sdk_archive_sha256"], prov.SDK_ARCHIVE_SHA256)
        self.assertEqual(m["engine"]["version"], prov.ENGINE_VERSION)
        self.assertTrue(5 <= len(m["scenarios"]) <= 10)
        self.assertEqual(len({s["scenario_id"] for s in m["scenarios"]}), len(m["scenarios"]))
        self.assertEqual(len(mf.games(m)), len(m["scenarios"]) * len(m["conditions"]) * m["repetitions"])
        self.assertEqual(len(mf.gate1_games(m)), 2)
        self.assertEqual([s["rule"][:2] for s in m["scenarios"]].count("S3"), 1)
        for scenario in m["scenarios"]:
            self.assertEqual(set(scenario["inputs_sha256"]), {"scenario", "basic", "cost", "see"})
        self.assertEqual(m["selection"]["pool"], m["selection"]["eligible"] + sum(m["selection"]["ineligible_by_reason"].values()))

    def test_file_is_the_canonical_rendering(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(self.manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


@unittest.skipUnless(ARCHIVE.is_file(), "private SDK archive absent (git-ignored)")
class RebuildTest(unittest.TestCase):
    def test_manifest_rebuilds_identically(self) -> None:
        result = subprocess.run([sys.executable, str(REPO / "scripts" / "build_evaluation_manifest.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(REPO))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
