"""The routing-remediation registration pins the frozen parent and rebuilds from committed files."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import candidate_manifest as cm
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation import variance_study as vs
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / rr.REMEDIATION_ID


class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registration = json.loads((DIRECTORY / "registration.json").read_text(encoding="utf-8"))

    def test_rebuilds_and_is_canonical(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_remediation_registration.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_parent_pins_are_the_frozen_baseline(self) -> None:
        parent = self.registration["parent"]
        self.assertEqual(parent["policy_source_sha256"], policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0])
        self.assertEqual(parent["golden_trace_chain"], cm.GOLDEN_TRACE_CHAIN)
        v1 = ROOT / "evaluation" / cm.EVALUATION_NAME
        self.assertEqual(parent["evaluation_manifest_sha256"],
                         mf.digest(json.loads((v1 / "manifest.json").read_text(encoding="utf-8"))))
        self.assertEqual(parent["evaluation_results_sha256"], hashlib.sha256((v1 / "results.json").read_bytes()).hexdigest())
        study = json.loads((ROOT / "evaluation" / vs.STUDY_NAME / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(parent["variance_study_manifest_sha256"], mf.digest(study))

    def test_candidate_scope_and_corpus(self) -> None:
        candidate = self.registration["candidate"]
        self.assertEqual(candidate["sources"], list(OCCUPY_RESERVATION_SOURCES) + [rr.CANDIDATE_FILE])
        self.assertNotIn("decision", rr.CANDIDATE_FILE)
        corpus = self.registration["corpus"]
        self.assertEqual(self.registration["corpus_sha256"], mf.digest(corpus))
        self.assertEqual(len(corpus["files"]), 22)
        self.assertEqual(corpus["decisions_total"], sum(f["decisions"] for f in corpus["files"]))
        self.assertTrue(all(f["path"].startswith("local/") and len(f["sha256"]) == 64 for f in corpus["files"]))
        self.assertEqual(corpus, json.loads((DIRECTORY / "corpus.json").read_text(encoding="utf-8")))
        self.assertIn("0.50 x baseline-v1 median", self.registration["performance"]["criterion"])


if __name__ == "__main__":
    unittest.main()
