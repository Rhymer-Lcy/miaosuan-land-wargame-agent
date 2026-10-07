"""Sprint 21: regenerate the direct-fire adjudication-semantics audit from the private inputs (server only).

Skipped unless the frozen corpus and the committed result files are present. The driver runs as a program:
``freeze --check`` rebuilds the protocol and the inventory with its pins, and ``run --check`` verifies every pinned input
and frozen source, rebuilds every row and compares every public file and the private rows byte for byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture" / "2130511121.H1.s12-v3-primary-1.p01.timeline.pkl"
RESULT = ROOT / "evaluation" / "s21-direct-fire-semantics" / "disposition.json"
PRIVATE = ROOT / "local" / "diagnostics" / "s21" / "rows-private.json.gz"


@unittest.skipUnless(TIMELINE.exists() and RESULT.exists() and PRIVATE.exists(),
                     "private Sprint 21 inputs or results not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_protocol_inputs_and_audit_regenerate(self) -> None:
        script = str(ROOT / "scripts" / "s21_semantics.py")
        self.assertEqual(self.run_program(script, "freeze", "--check").strip(), "identical: protocol.json, inputs.json")
        self.assertEqual(self.run_program(script, "run", "--check").strip(), "audit identical")


if __name__ == "__main__":
    unittest.main()
