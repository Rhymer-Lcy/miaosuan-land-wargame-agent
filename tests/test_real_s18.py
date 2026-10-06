"""Sprint 18: regenerate the census and the admission tables from the private inputs (server only).

Skipped unless the replay corpus, the Sprint 12 timelines and the private record inventory are present under ``local/``.
The drivers run as programs: ``run --check`` verifies every pinned input and the record inventory, recomputes the census
(it refuses on any consistency check against the published figures) and compares ``census.json`` byte for byte;
``s18_admission.py --check`` does the same for ``admission.json`` from the private rows.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "local" / "replay-corpus" / "2130511121.C1.r1.jsonl.gz"
TIMELINE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture" / "2130511121.H1.s12-v3-primary-1.p01.timeline.pkl"
INVENTORY = ROOT / "local" / "diagnostics" / "s18" / "record-inventory.txt"


@unittest.skipUnless(CORPUS.exists() and TIMELINE.exists() and INVENTORY.exists(), "private Sprint 18 inputs not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_census_and_admission_regenerate(self) -> None:
        self.assertEqual(self.run_program(str(ROOT / "scripts" / "s18_census.py"), "run", "--check").strip(),
                         "census identical")
        self.assertEqual(self.run_program(str(ROOT / "scripts" / "s18_admission.py"), "--check").strip(),
                         "admission identical")


if __name__ == "__main__":
    unittest.main()
