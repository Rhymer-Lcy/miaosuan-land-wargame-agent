"""Sprint 19: regenerate the T6-G shadow study from the private inputs (server only).

Skipped unless the replay corpus, the Sprint 12 timelines and the committed result files are present. The driver runs as
a program: ``run --check`` verifies every pinned input and frozen source, reproduces Sprint 18's figures (it refuses on
any difference), replays the frozen gate and compares every public file and the private rows byte for byte.
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
RESULT = ROOT / "evaluation" / "s19-t6g-shadow" / "disposition.json"
PRIVATE = ROOT / "local" / "diagnostics" / "s19" / "shadow-private.json.gz"


@unittest.skipUnless(CORPUS.exists() and TIMELINE.exists() and RESULT.exists() and PRIVATE.exists(),
                     "private Sprint 19 inputs or results not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_protocol_inputs_and_shadow_regenerate(self) -> None:
        script = str(ROOT / "scripts" / "s19_t6g_shadow.py")
        self.assertEqual(self.run_program(script, "freeze", "--check").strip(), "protocol and inputs identical")
        self.assertEqual(self.run_program(script, "run", "--check").strip(), "shadow identical")


if __name__ == "__main__":
    unittest.main()
