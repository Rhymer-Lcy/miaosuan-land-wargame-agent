"""Sprint 27 regeneration on the evaluation server (``docs/SPRINT27_T6S_PROBE.md``). Skipped wherever the private
captures are absent (the workstation, a clean clone).

* ``scripts/s27_analysis.py references --check``: the frozen HH references regenerate through Sprint 26's loader;
* ``scripts/s27_analysis.py rehearse --check``: the candidate equals Sprint 26's frozen rule on every recorded decision;
* ``scripts/s27_analysis.py inputs --check``: the committed ``inputs.json`` equals a fresh derivation;
* ``scripts/s27_analysis.py game --position N --check`` and ``disposition --check``: once a game and its analysis exist,
  its public file (and the disposition) regenerate byte for byte;
* ``scripts/mutate_s27.py --check``: the committed mutation record regenerates.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture"
GAMES = ROOT / "local" / "evaluation" / "s27-t6s-probe-1" / "games"
OUT = ROOT / "evaluation" / "s27-t6s-probe"


def run(*args: str, timeout: int = 7200) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


@unittest.skipUnless(SOURCE.is_dir(), "private captures are not on this host")
class RealS27Test(unittest.TestCase):
    def test_references_rehearsal_and_inputs_regenerate(self) -> None:
        for name in ("references", "rehearse", "inputs"):
            done = run("scripts/s27_analysis.py", name, "--check")
            self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
            self.assertNotIn("MISMATCH", done.stdout)
            self.assertIn("OK evaluation/s27-t6s-probe/", done.stdout)

    def test_game_files_regenerate(self) -> None:
        checked = 0
        for position in (1, 2):
            if not (OUT / f"game-p{position:02d}.json").exists():
                continue
            done = run("scripts/s27_analysis.py", "game", "--position", str(position), "--check")
            self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
            self.assertIn(f"OK evaluation/s27-t6s-probe/game-p{position:02d}.json", done.stdout)
            checked += 1
        if not checked:
            self.skipTest("no game file yet")

    @unittest.skipUnless((OUT / "disposition.json").exists(), "no disposition yet")
    def test_disposition_regenerates(self) -> None:
        done = run("scripts/s27_analysis.py", "disposition", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK evaluation/s27-t6s-probe/disposition.json", done.stdout)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "no mutation record")
    def test_mutation_record_regenerates(self) -> None:
        done = run("scripts/mutate_s27.py", "--check", timeout=14400)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
