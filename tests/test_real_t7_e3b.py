"""E3b configuration search (``t7-e3b-search-1``): private regeneration of the public outputs.

Skipped without the private captures and the replay corpus (a public checkout). On the evaluation server it rebuilds
the known-answer validation, the search, the certificates and the decision, and the independent cross-check, and
requires each to be byte-identical to the committed file.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEEDED = (REPO / "local" / "evaluation" / "t1r-diagnosis-1" / "capture",
          REPO / "local" / "evaluation" / "t7-mechanism-probe-1" / "capture",
          REPO / "local" / "replay-corpus",
          REPO / "local" / "diagnostics" / "t7" / "posthoc-private.json")


@unittest.skipUnless(all(p.exists() for p in NEEDED), "private captures, replay corpus or Sprint 5 rows absent")
class RealRegeneration(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *args], cwd=REPO, capture_output=True, text=True, timeout=7200)

    def test_validation_search_certificates_and_decision_rebuild_identically(self) -> None:
        done = self.run_script("scripts/t7_e3b_search.py", "check")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.count("identical"), 4, done.stdout)

    def test_crosscheck_rebuilds_identically(self) -> None:
        done = self.run_script("scripts/t7_e3b_crosscheck.py", "--check")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("crosscheck identical", done.stdout)

    def test_posthoc_rebuilds_identically(self) -> None:
        done = self.run_script("scripts/t7_e3b_posthoc.py", "--check")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("posthoc identical", done.stdout)


if __name__ == "__main__":
    unittest.main()
