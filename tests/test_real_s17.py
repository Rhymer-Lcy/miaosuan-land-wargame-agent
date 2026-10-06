"""Sprint 17 regeneration on the evaluation server (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``). Skipped wherever the
private captures are absent (the workstation, a clean clone).

* ``scripts/s17_analysis.py freeze --check``: the private prefix reference and the committed ``inputs.json`` still equal
  a fresh derivation from Sprint 16's pinned v3 games, the committed card and the frozen rules;
* ``scripts/s17_analysis.py run --check``: once the two games exist, every public file regenerates byte for byte;
* ``scripts/mutate_s17.py --check``: the committed mutation record regenerates.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local" / "evaluation" / "s16-v3-mechanism-capture-1" / "capture"
REFERENCE = ROOT / "local" / "diagnostics" / "s17" / "prefix-reference.json"
GAMES = ROOT / "local" / "evaluation" / "s17-post-stage-v6-probe-1" / "games"
OUT = ROOT / "evaluation" / "s17-first-divergence-probe"


def run(*args: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


@unittest.skipUnless(SOURCE.is_dir() and REFERENCE.exists(), "private captures are not on this host")
class RealS17Test(unittest.TestCase):
    def test_inputs_and_prefix_reference_regenerate(self) -> None:
        done = run("scripts/s17_analysis.py", "freeze", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)

    @unittest.skipUnless(GAMES.is_dir() and len(list(GAMES.glob("*.json"))) == 2
                         and (OUT / "disposition.json").exists(), "the two games and their analysis do not exist")
    def test_public_files_regenerate(self) -> None:
        done = run("scripts/s17_analysis.py", "run", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK: public files regenerate byte for byte", done.stdout)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "no mutation record")
    def test_mutation_record_regenerates(self) -> None:
        done = run("scripts/mutate_s17.py", "--check", timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
