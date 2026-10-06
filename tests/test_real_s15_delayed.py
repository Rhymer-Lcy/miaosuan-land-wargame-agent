"""Sprint 15: regenerate every public file of the delayed-redistribution study from the private captures (server only).

Skipped unless the Sprint 12 P1 timelines, the Sprint 10 diagnostic captures and the T9-v2 exploratory captures are
present under ``local/``. The driver is run as a program: ``diagnose --check`` re-decides the reference policies on the
ten captures and compares ``diagnostics.json`` byte for byte; once the inputs are pinned, ``freeze --check`` recomputes
every input digest and identity; once the replay has run, ``run --check`` replays every decision with every candidate's
memory and compares each public file byte for byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local" / "evaluation"
TIMELINE = LOCAL / "s12-v3-primary-1" / "capture" / "2130511121.H1.s12-v3-primary-1.p01.timeline.pkl"
WINDOWS = LOCAL / "s10-t9-v1-diagnosis" / "capture" / "2120531121.C3.s10-t9-v1-diagnosis.g01.windows.pkl"
EXPLORE = LOCAL / "s10-t9-v2-exploration" / "capture" / "1930331196.C3.s10-t9-v2-exploration.g03.explore.json"
OUT = ROOT / "evaluation" / "s15-delayed-redistribution"
DRIVER = ROOT / "scripts" / "s15_delayed_replay.py"


@unittest.skipUnless(TIMELINE.exists() and WINDOWS.exists() and EXPLORE.exists(), "private captures not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, str(DRIVER), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_diagnostics_regenerate(self) -> None:
        self.assertIn("OK: public files regenerate byte for byte", self.run_program("diagnose", "--check"))

    @unittest.skipUnless((OUT / "inputs.json").exists(), "inputs not pinned yet")
    def test_inputs_are_unchanged(self) -> None:
        self.assertEqual(self.run_program("freeze", "--check").strip(), "OK")

    @unittest.skipUnless((OUT / "gate.json").exists(), "replay not run yet")
    def test_every_public_file_regenerates(self) -> None:
        self.assertIn("OK: public files regenerate byte for byte", self.run_program("run", "--check"))

    @unittest.skipUnless((OUT / "posthoc.json").exists(), "post-hoc analysis not run yet")
    def test_the_posthoc_analysis_regenerates(self) -> None:
        out = self.run_program_at(ROOT / "scripts" / "s15_posthoc.py", "--check")
        self.assertTrue(out.startswith("OK "), out)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "mutation record not written yet")
    def test_the_mutation_record_regenerates(self) -> None:
        out = self.run_program_at(ROOT / "scripts" / "mutate_s15_delayed.py", "--check")
        self.assertTrue(out.startswith("OK "), out)

    def run_program_at(self, script: Path, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, str(script), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout


if __name__ == "__main__":
    unittest.main()
