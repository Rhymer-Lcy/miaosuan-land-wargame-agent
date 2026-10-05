"""Sprint 13: regenerate every public diagnosis file from the private inputs (server only).

Skipped unless the Sprint 12 P1 captures and the Sprint 9 phase-A captures are present under ``local/``. The driver is
run as a program: ``freeze --check`` recomputes every input digest and policy identity, ``run --check`` recomputes the
whole diagnosis (it refuses on any reconstruction disagreement) and compares each public file byte for byte, and the
mutation record is regenerated and compared.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture" / \
    "2130511121.H1.s12-v3-primary-1.p01.timeline.pkl"
SPRINT9 = ROOT / "local" / "evaluation" / "t9-confirmation-1" / "capture" / "2130511121.H1.A.r01.explore.json"


@unittest.skipUnless(TIMELINE.exists() and SPRINT9.exists(), "private Sprint 12 or Sprint 9 captures not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_inputs_are_unchanged(self) -> None:
        self.assertIn("inputs: identical", self.run_program(str(ROOT / "scripts" / "s13_v3_diagnosis.py"), "freeze",
                                                            "--check"))

    def test_every_public_file_regenerates(self) -> None:
        out = self.run_program(str(ROOT / "scripts" / "s13_v3_diagnosis.py"), "run", "--check")
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 7, out)
        self.assertTrue(all(line.startswith("OK ") for line in lines), out)

    def test_the_mutation_record_regenerates(self) -> None:
        out = self.run_program(str(ROOT / "scripts" / "mutate_s13_diagnosis.py"), "--check")
        self.assertTrue(out.startswith("OK "), out)


if __name__ == "__main__":
    unittest.main()
