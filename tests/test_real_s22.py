"""Sprint 22 regeneration on the evaluation server (``docs/SPRINT22_T2_TRANSPORT_PROBE.md``). Skipped wherever the
private captures are absent (the workstation, a clean clone).

* ``scripts/s22_analysis.py semantics --check`` and ``witness --check``: the semantics audit, the public witness file and
  the private witness reference regenerate from Sprint 21's pinned corpus;
* ``scripts/s22_analysis.py inputs --check``: the committed ``inputs.json`` equals a fresh derivation;
* ``scripts/s22_analysis.py rehearse``: the candidate reproduces the registered trigger on the witness game's prefix;
* ``scripts/s22_analysis.py run --check``: once the game exists, every public result file regenerates byte for byte;
* ``scripts/mutate_s22.py --check``: the committed mutation record regenerates.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local" / "evaluation" / "s10-t9-v1-diagnosis" / "capture"
REFERENCE = ROOT / "local" / "diagnostics" / "s22" / "witness-reference.json"
GAMES = ROOT / "local" / "evaluation" / "s22-t2-transport-probe-1" / "games"
OUT = ROOT / "evaluation" / "s22-t2-transport-probe"


def run(*args: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


@unittest.skipUnless(SOURCE.is_dir() and REFERENCE.exists(), "private captures are not on this host")
class RealS22Test(unittest.TestCase):
    def test_semantics_witness_and_inputs_regenerate(self) -> None:
        for name in ("semantics", "witness", "inputs"):
            done = run("scripts/s22_analysis.py", name, "--check")
            self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
            self.assertNotIn("MISMATCH", done.stdout)
            self.assertIn("OK", done.stdout)

    def test_rehearsal_reproduces_the_registered_trigger(self) -> None:
        done = run("scripts/s22_analysis.py", "rehearse")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("rehearsal over decisions 0..1: PASS", done.stdout)

    @unittest.skipUnless(GAMES.is_dir() and len(list(GAMES.glob("*.json"))) == 1
                         and (OUT / "disposition.json").exists(), "the game and its analysis do not exist")
    def test_public_files_regenerate(self) -> None:
        done = run("scripts/s22_analysis.py", "run", "--check")
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertEqual(done.stdout.count("OK evaluation/s22-t2-transport-probe/"), 3, done.stdout)

    @unittest.skipUnless((OUT / "mutation.json").exists(), "no mutation record")
    def test_mutation_record_regenerates(self) -> None:
        done = run("scripts/mutate_s22.py", "--check", timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
