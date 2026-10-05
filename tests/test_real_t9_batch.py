"""Sprint 11: regenerate the offline replay and prevalence files from the private captures (server only).

Skipped unless the Sprint 10 diagnostic captures and the pinned replay corpus are present under ``local/``. Each script
is run as a program with ``--check``, which recomputes everything and compares the committed file byte for byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "local" / "evaluation" / "s10-t9-v1-diagnosis" / "capture" / \
    "2120531121.C3.s10-t9-v1-diagnosis.g01.windows.pkl"
CORPUS = ROOT / "local" / "replay-corpus" / "2130511121.C1.r1.jsonl.gz"


@unittest.skipUnless(CAPTURE.exists() and CORPUS.exists(), "private Sprint 10 captures or replay corpus not present")
class RealRegenerationTest(unittest.TestCase):
    def run_check(self, script: str) -> None:
        env = dict(os.environ, PYTHONNOUSERSITE="1")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--check"], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=3600)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("OK "), done.stdout)

    def test_replay_regenerates(self) -> None:
        self.run_check("t9_batch_replay.py")

    def test_prevalence_regenerates(self) -> None:
        self.run_check("t9_batch_prevalence.py")


if __name__ == "__main__":
    unittest.main()
