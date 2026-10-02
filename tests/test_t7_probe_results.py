"""The committed results of the T7 mechanism probe ``t7-mechanism-probe-1``.

The pooled result, the P-A continuation gate and the P-B1 stop branch recompute from the committed per-game outputs;
the registered disposition follows from them; the registration issue's record matches the committed canonical body;
the three games ran on the registration commit in sessions 2462 to 2464. Privately (skipped when the captures are
absent) the registered per-game analyses and the post-hoc description rebuild byte for byte.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import t7_probe as tp
from miaosuan_agent.evaluation import t7_probe_endpoints as ep

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / tp.PROBE_ID
WORK = ROOT / "local" / "evaluation" / tp.PROBE_ID
REGISTRATION = "015400d5bbeca32e01433b02e5746b7cb02712bc"
spec = importlib.util.spec_from_file_location("t7_probe_analysis", ROOT / "scripts" / "t7_probe_analysis.py")
ANA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ANA)


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


class CommittedResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.games = {"P-A": load("pa.json"), "P-B1": load("pb1.json"), "P-B2": load("pb2.json")}

    def test_pooled_result_recomputes(self) -> None:
        self.assertEqual(ANA.pool(self.games), load("gates.json"))

    def test_registered_disposition(self) -> None:
        pooled = load("gates.json")
        self.assertEqual(pooled["disposition"]["disposition"], "NEEDS_TARGETED_PROBE")
        self.assertEqual(pooled["disposition"]["reasons"], ["E3b NOT TESTED"])
        self.assertEqual((pooled["primary"]["orders"], pooled["primary"]["reached_within_76"]), (16, 16))
        self.assertEqual(pooled["E4"]["E4a"]["verdict"], "SUPPORTED")

    def test_gate_and_stop_branch_recompute(self) -> None:
        gate, stop = load("gate-pa.json"), load("stop-pb1.json")
        self.assertEqual(ep.gate_pa(self.games["P-A"], gate["installation"]["ok"])["checks"], gate["checks"])
        self.assertTrue(gate["continue_to_pb"])
        self.assertEqual(ep.stop_after_pb1(self.games["P-B1"], stop["installation"]["ok"])["checks"], stop["checks"])
        self.assertTrue(stop["run_pb2"])
        self.assertEqual((gate["installation"]["sessions_opened"], stop["installation"]["sessions_opened"]), (2462, 2463))

    def test_sessions_and_games(self) -> None:
        self.assertEqual([g["session"] for g in self.games.values()], ["2462", "2463", "2464"])
        for name, game in self.games.items():
            self.assertEqual(game["status"], "COMPLETED", name)
            self.assertTrue(game["integrity"]["ok"], name)
            self.assertEqual(game["integrity"]["relaxed_for_dry_run"], [], name)

    def test_registration_record(self) -> None:
        record = load("registration-verification.json")
        body = (OUT / "registration-issue.md").read_bytes()
        self.assertTrue(record["byte_identical"])
        self.assertTrue(record["fetched_without_authentication"])
        self.assertEqual(record["canonical_body_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(record["canonical_body_bytes"], len(body))
        self.assertIn(f"Registration commit `{REGISTRATION}`", body.decode("utf-8"))
        self.assertEqual(record["issue_number"], 3)


@unittest.skipUnless((WORK / "games" / f"{tp.PB2_GAME}.json").is_file(), "the probe captures are private (git-ignored)")
class RealRegeneration(unittest.TestCase):
    """The registered per-game analyses and the post-hoc description rebuild byte for byte (several minutes)."""

    def test_games(self) -> None:
        for probe, name in (("P-A", "pa.json"), ("P-B1", "pb1.json"), ("P-B2", "pb2.json")):
            with tempfile.TemporaryDirectory() as tmp:
                out, private = Path(tmp) / "out.json", Path(tmp) / "private.json"
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "t7_probe_analysis.py"), "game", "--probe",
                                       probe, "--work", str(WORK), "--out", str(out), "--private", str(private),
                                       "--commit", REGISTRATION], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(out.read_text(encoding="utf-8"), (OUT / name).read_text(encoding="utf-8"), probe)

    def test_posthoc(self) -> None:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "t7_probe_posthoc.py"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "posthoc identical", done.stderr)


if __name__ == "__main__":
    unittest.main()
