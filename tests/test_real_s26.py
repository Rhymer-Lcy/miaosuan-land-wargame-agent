"""Sprint 26 regeneration on the evaluation server (``docs/SPRINT26_T6S_SHADOW.md``). Skipped wherever the private
captures are absent (the workstation, a clean clone).

* ``scripts/s26_t6s.py freeze --check``: the committed ``protocol.json`` and ``inputs.json`` equal a fresh derivation;
* ``scripts/s26_t6s.py run --check``: once the study has run, every public file and the private rows regenerate byte
  for byte;
* ``scripts/mutate_s26.py --check``: the committed mutation record regenerates.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture"
OUT = ROOT / "evaluation" / "s26-t6s-shadow"


def run(*args: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


@unittest.skipUnless(SOURCE.is_dir(), "private captures are not on this host")
class RealS26Test(unittest.TestCase):
    def test_protocol_and_inputs_regenerate(self) -> None:
        done = run("scripts/s26_t6s.py", "freeze", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("protocol and inputs identical", done.stdout)

    @unittest.skipUnless((OUT / "disposition.json").exists(), "the study has not run")
    def test_study_regenerates(self) -> None:
        done = run("scripts/s26_t6s.py", "run", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("study identical", done.stdout)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "no mutation record")
    def test_mutation_record_regenerates(self) -> None:
        done = run("scripts/mutate_s26.py", "--check", timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
