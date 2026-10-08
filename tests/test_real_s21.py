"""Sprint 21: regenerate the direct-fire adjudication-semantics audit from the private inputs (server only).

Skipped unless the frozen corpus and the committed result files are present. ``freeze --check`` rebuilds the protocol
and the inventory with its pins, and ``run --check`` verifies every pinned input and frozen source, rebuilds every row
and compares every public file and the private rows byte for byte.

Maintenance (Sprint 22, 2026-10-08): Sprint 21's inventory lists every capture folder under ``local/evaluation/``, so a
later sprint's capture folder (Sprint 22's ``s22-t2-transport-probe-1``) would enter a fresh inventory and make the
check fail although nothing of Sprint 21 changed. The freeze check therefore runs Sprint 21's frozen driver unchanged,
in process, with its folder listing bounded to the folders its committed ``inputs.json`` names; the driver, its pins and
its public files are untouched (this test file is not among Sprint 21's pins). ``run --check`` runs as a program, as
before.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "local" / "evaluation" / "s12-v3-primary-1" / "capture" / "2130511121.H1.s12-v3-primary-1.p01.timeline.pkl"
RESULT = ROOT / "evaluation" / "s21-direct-fire-semantics" / "disposition.json"
PRIVATE = ROOT / "local" / "diagnostics" / "s21" / "rows-private.json.gz"
INPUTS = ROOT / "evaluation" / "s21-direct-fire-semantics" / "inputs.json"


def frozen_folders() -> set:
    """Every folder Sprint 21's committed inventory names (captures, explore or confirmation only, records only, not
    opened)."""
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    names = {e["folder"] for e in committed["inventory"]}
    names |= set(committed["explore_or_confirmation_only_folders"]) | set(committed["records_only_folders"])
    return names | set(committed["not_opened"])


def load_driver():
    spec = importlib.util.spec_from_file_location("s21_semantics_frozen", ROOT / "scripts" / "s21_semantics.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bounded(root: Path, allowed: set) -> Path:
    """``root`` whose own directory listing yields only the ``allowed`` folders (children are ordinary paths)."""
    base = type(root)

    class Bounded(base):
        def iterdir(self):
            for child in base(self).iterdir():
                if base(self) != base(root) or child.name in allowed:
                    yield child

    return Bounded(root)


@unittest.skipUnless(TIMELINE.exists() and RESULT.exists() and PRIVATE.exists(),
                     "private Sprint 21 inputs or results not present")
class RealRegenerationTest(unittest.TestCase):
    def run_program(self, *args: str) -> str:
        env = dict(os.environ, PYTHONNOUSERSITE="1", OPENBLAS_NUM_THREADS="1")
        done = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=7200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_protocol_inputs_and_audit_regenerate(self) -> None:
        driver = load_driver()
        allowed = frozen_folders()
        present = {p.name for p in driver.LOCAL_EVAL.iterdir() if p.is_dir()}
        self.assertTrue(allowed <= present, sorted(allowed - present))
        driver.LOCAL_EVAL = bounded(driver.LOCAL_EVAL, allowed)
        self.assertEqual(sorted(p.name for p in driver.LOCAL_EVAL.iterdir() if p.is_dir()), sorted(allowed))
        self.assertEqual(driver.dump(driver.protocol()), driver.PROTOCOL.read_text(encoding="utf-8"))
        self.assertEqual(driver.dump(driver.inputs()), INPUTS.read_text(encoding="utf-8"))
        script = str(ROOT / "scripts" / "s21_semantics.py")
        self.assertEqual(self.run_program(script, "run", "--check").strip(), "audit identical")


if __name__ == "__main__":
    unittest.main()
