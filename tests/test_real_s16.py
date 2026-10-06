"""Sprint 16 regeneration on the evaluation server (``docs/SPRINT16_MECHANISM_CAPTURE.md``). Skipped wherever the
private captures are absent (the workstation, a clean clone).

* ``scripts/s16_analysis.py freeze --check``: the committed ``inputs.json`` still equals a fresh derivation from the
  pinned historical captures, the committed card and the frozen rules;
* ``scripts/s16_analysis.py run --check``: once the three games exist, every public file regenerates byte for byte;
* ``scripts/mutate_s16.py --check``: the committed mutation record regenerates.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture"
HISTORICAL = ROOT / "local" / "evaluation" / "s10-t9-v1-diagnosis" / "capture"
GAMES = ROOT / "local" / "evaluation" / "s16-v3-mechanism-capture-1" / "games"
OUT = ROOT / "evaluation" / "s16-mechanism-capture"


def run(*args: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


@unittest.skipUnless(PRIMARY.is_dir() and HISTORICAL.is_dir(), "private captures are not on this host")
class RealS16Test(unittest.TestCase):
    def test_inputs_regenerate(self) -> None:
        done = run("scripts/s16_analysis.py", "freeze", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)

    @unittest.skipUnless(GAMES.is_dir() and len(list(GAMES.glob("*.json"))) == 3
                         and (OUT / "disposition.json").exists(), "the three games and their analysis do not exist")
    def test_public_files_regenerate(self) -> None:
        done = run("scripts/s16_analysis.py", "run", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK: public files regenerate byte for byte", done.stdout)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "no mutation record")
    def test_mutation_record_regenerates(self) -> None:
        done = run("scripts/mutate_s16.py", "--check", timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
