"""The T9 confirmatory study's outputs regenerate from the private records (evaluation server only).

Skipped where the private records are absent. The planning figures and the pre-registration validation must
regenerate byte for byte, and so must every committed phase file (from the records, the captures and the engine
ledger, read only) and the disposition."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent import engine_install as ei
from miaosuan_agent.evaluation import t9_confirmation as tc

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "evaluation" / tc.STUDY_ID
CONTROL = REPO / "local" / "evaluation" / tc.V2_ID / "games"
INSTALL = REPO / "local" / "engines" / "sdk-4.1.0"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"t9real_{name}", REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(CONTROL.is_dir() and (REPO / "local" / "evaluation" / "t7-mechanism-probe-1" / "capture").is_dir(),
                     "private records absent")
class PreRegistrationRegenerationTest(unittest.TestCase):
    """Each script's own ``--check``: its worker functions must be importable by multiprocessing, so the scripts run
    as programs, not as modules loaded under another name."""

    def check(self, script: str) -> None:
        done = subprocess.run([sys.executable, str(REPO / "scripts" / script), "--check"], cwd=REPO,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout[-1000:] + done.stderr[-2000:])
        self.assertIn("OK evaluation/t9-confirmation-1/", done.stdout)

    def test_planning(self) -> None:
        self.check("t9_confirmation_planning.py")

    def test_validation(self) -> None:
        self.check("t9_confirmation_validation.py")


@unittest.skipUnless((REPO / "local" / "evaluation" / tc.STUDY_ID / "games").is_dir() and INSTALL.is_dir(),
                     "the study's private records are absent")
class PhaseRegenerationTest(unittest.TestCase):
    def test_every_committed_phase_file_and_the_disposition(self) -> None:
        analysis = load_script("t9_confirmation_analysis")
        manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
        ledger = ei.read_ledger(ei.EngineInstall(INSTALL.resolve()))
        work = REPO / "local" / "evaluation" / tc.STUDY_ID
        checked = 0
        for phase in tc.PHASE_ORDER:
            path = BASE / f"phase-{phase}.json"
            if not path.exists():
                break
            self.assertEqual(analysis.phase_text(manifest, phase, work, ledger), path.read_text(encoding="utf-8"), phase)
            checked += 1
        if (BASE / "disposition.json").exists():
            self.assertEqual(analysis.disposition_text(), (BASE / "disposition.json").read_text(encoding="utf-8"))
        if not checked:
            self.skipTest("no phase file committed yet")


if __name__ == "__main__":
    unittest.main()
