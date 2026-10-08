"""Sprint 23 regeneration on the evaluation server (``docs/SPRINT23_T2_POLICY_DESIGN.md``). Skipped wherever the
private captures are absent (the workstation, a clean clone).

* ``scripts/s23_t2_design.py freeze --check``: the committed ``inputs.json`` equals a fresh derivation (every corpus
  file, cost table and source pin);
* ``scripts/s23_t2_design.py run --check``: once the study has run, every public file regenerates byte for byte;
* ``scripts/mutate_s23.py --check``: the committed mutation record regenerates.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture"
REFERENCE = ROOT / "local" / "diagnostics" / "s22" / "witness-reference.json"
OUT = ROOT / "evaluation" / "s23-t2-policy-design"


def run(*args: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


@unittest.skipUnless(SOURCE.is_dir() and REFERENCE.exists(), "private captures are not on this host")
class RealS23Test(unittest.TestCase):
    def test_inputs_regenerate(self) -> None:
        done = run("scripts/s23_t2_design.py", "freeze", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK evaluation/s23-t2-policy-design/inputs.json", done.stdout)

    @unittest.skipUnless((OUT / "disposition.json").exists(), "the study has not run")
    def test_public_files_regenerate(self) -> None:
        done = run("scripts/s23_t2_design.py", "run", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertEqual(done.stdout.count("OK evaluation/s23-t2-policy-design/"), 3, done.stdout)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "no mutation record")
    def test_mutation_record_regenerates(self) -> None:
        done = run("scripts/mutate_s23.py", "--check", timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
