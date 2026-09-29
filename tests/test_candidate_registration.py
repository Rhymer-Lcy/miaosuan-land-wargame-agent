"""The registered candidate manifest agrees with the candidate code and with the frozen baseline-v0.

Fails when the candidate's policy source changes without a new registration, when the golden
decisions change, or when a pinned baseline-v0 reference no longer matches its committed artifact.
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
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / cm.EVALUATION_NAME
V0 = ROOT / "evaluation" / "baseline-v0"


class CandidateRegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        cls.v0 = json.loads((V0 / "manifest.json").read_text(encoding="utf-8"))

    def test_policy_source_is_the_registered_one(self) -> None:
        digest, files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
        self.assertEqual(files, self.manifest["policy_source"]["files"])
        self.assertEqual(digest, self.manifest["policy_source"]["sha256"],
                         "the candidate changed after registration: register again and rerun")
        self.assertEqual(self.manifest["policy_source"]["sources"], list(OCCUPY_RESERVATION_SOURCES))

    def test_frozen_reference_still_matches(self) -> None:
        reference = self.manifest["reference"]
        self.assertEqual(reference["manifest_sha256"], mf.digest(self.v0))
        self.assertEqual(reference["policy_source_sha256"], policy_source_digest()[0])
        self.assertEqual(reference["results_sha256"], hashlib.sha256((V0 / "results.json").read_bytes()).hexdigest())
        self.assertEqual(reference["golden_trace_chain"], cm.V0_GOLDEN_TRACE_CHAIN)
        self.assertEqual(self.manifest["scenarios"], self.v0["scenarios"])

    def test_pins(self) -> None:
        self.assertEqual(self.manifest["golden_trace_chain"], cm.GOLDEN_TRACE_CHAIN)
        replay_bytes = (DIRECTORY / "counterfactual-replay.json").read_bytes()
        self.assertEqual(self.manifest["counterfactual_replay"]["sha256"], hashlib.sha256(replay_bytes).hexdigest())
        replay = json.loads(replay_bytes)
        self.assertEqual((replay["unexplained"], replay["fidelity_mismatches"]), (0, 0))
        self.assertEqual(replay["candidate_policy_source_sha256"], self.manifest["policy_source"]["sha256"])
        self.assertEqual(replay["v0_policy_source_sha256"], self.v0["policy_source"]["sha256"])

    def test_file_is_canonical_and_rebuilds(self) -> None:
        text = (DIRECTORY / "manifest.json").read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(self.manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_candidate_manifest.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
