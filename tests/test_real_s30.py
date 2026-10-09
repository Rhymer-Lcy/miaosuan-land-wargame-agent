"""Sprint 30 preflight regeneration on the private inputs (evaluation server only; skipped elsewhere).

``scripts/s30_preflight.py freeze --check`` must reproduce the committed inputs, and ``run --check`` the committed
public files and the private rows byte for byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ROOT / "local" / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "games"
PRIVATE = ROOT / "local" / "diagnostics" / "s30" / "preflight-private.json.gz"


@unittest.skipUnless(CONTROLS.is_dir() and PRIVATE.exists() and (ROOT / "local" / "replay-corpus").is_dir(),
                     "the private preflight inputs are only on the evaluation server")
class RealPreflightTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONNOUSERSITE="1")
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "s30_preflight.py"), *args], cwd=ROOT,
                              env=env, capture_output=True, text=True)

    def test_freeze_and_run_regenerate(self) -> None:
        freeze = self.run_script("freeze", "--check")
        self.assertEqual(freeze.returncode, 0, freeze.stdout + freeze.stderr)
        self.assertIn("preflight inputs identical", freeze.stdout)
        run = self.run_script("run", "--check", "--workers", "8")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("preflight identical", run.stdout)


if __name__ == "__main__":
    unittest.main()
