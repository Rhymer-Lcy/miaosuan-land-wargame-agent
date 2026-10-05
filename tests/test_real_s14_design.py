"""Sprint 14: regenerate every public design-competition file from the private captures (server only).

Skipped unless the Sprint 12 P1 timelines and the Sprint 10 diagnostic captures are present under ``local/``. The driver
is run as a program: ``freeze --check`` recomputes every input digest and policy identity, ``run --check`` replays every
decision of the ten captures (it refuses on any reconstruction disagreement) and compares each public file byte for
byte, and the mutation record is regenerated and compared.
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
WINDOWS = ROOT / "local" / "evaluation" / "s10-t9-v1-diagnosis" / "capture" / \
    "2120531121.C3.s10-t9-v1-diagnosis.g01.windows.pkl"


@unittest.skipUnless(TIMELINE.exists() and WINDOWS.exists(), "private Sprint 12 or Sprint 10 captures not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_inputs_are_unchanged(self) -> None:
        self.assertEqual(self.run_program(str(ROOT / "scripts" / "s14_design_replay.py"), "freeze", "--check").strip(),
                         "OK")

    def test_every_public_file_regenerates(self) -> None:
        out = self.run_program(str(ROOT / "scripts" / "s14_design_replay.py"), "run", "--check")
        self.assertIn("OK: public files regenerate byte for byte", out)

    def test_the_mutation_record_regenerates(self) -> None:
        out = self.run_program(str(ROOT / "scripts" / "mutate_s14_design.py"), "--check")
        self.assertTrue(out.startswith("OK "), out)


if __name__ == "__main__":
    unittest.main()
