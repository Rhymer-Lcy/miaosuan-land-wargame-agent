"""T7 mechanism probe: the pre-registration analyses on real records (private; skipped when the inputs are absent).

The calibration of the visibility model on the replay corpus, the premise (the registered candidate replayed over the
reference game), the equivalence of the candidate with the Sprint 5 shadow, and the dry run of the registered
analyses on real records rebuild byte for byte; the dry run's content is checked as registered: on the reference game
the P-A analysis finds no concealment order and reports every mechanism endpoint NOT TESTED.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "local" / "evaluation" / "t1r-diagnosis-1" / "capture" / "1910631192.C3.b.x01.windows.pkl"
CORPUS_GAME = ROOT / "local" / "replay-corpus" / "2120531121.C1.r1.jsonl.gz"
DATA = ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
OUT = ROOT / "evaluation" / "t7-mechanism-probe-1"
PRIVATE = REFERENCE.is_file() and CORPUS_GAME.is_file() and DATA.is_dir()


@unittest.skipUnless(PRIVATE, "the reference game, the replay corpus and the scenario data are private (git-ignored)")
class RealRegeneration(unittest.TestCase):
    """The public pre-registration outputs rebuild byte for byte (several minutes)."""

    def check(self, *args: str) -> str:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / args[0]), *args[1:], "--check"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_calibration(self) -> None:
        self.assertIn("calibration.json identical", self.check("t7_probe_analysis.py", "calibrate"))

    def test_premise(self) -> None:
        self.assertIn("premise.json identical", self.check("t7_probe_analysis.py", "premise"))

    def test_equivalence(self) -> None:
        self.assertIn("equivalence.json identical", self.check("t7_probe_analysis.py", "equivalence"))

    def test_dry_run(self) -> None:
        self.assertIn("dryrun.json identical", self.check("t7_probe_analysis.py", "dryrun"))

    def test_mutation_results(self) -> None:
        self.assertIn("mutation results identical", self.check("mutate_t7_probe.py"))


@unittest.skipUnless((OUT / "dryrun.json").is_file(), "the dry run output is committed with the registration")
class DryRunContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.d = json.loads((OUT / "dryrun.json").read_text(encoding="utf-8"))
        cls.c = json.loads((OUT / "calibration.json").read_text(encoding="utf-8"))
        cls.p = json.loads((OUT / "premise.json").read_text(encoding="utf-8"))
        cls.e = json.loads((OUT / "equivalence.json").read_text(encoding="utf-8"))

    def test_reference_game_has_no_order_and_no_manufactured_event(self) -> None:
        pa = self.d["P-A analysis on the reference game"]
        self.assertEqual(pa["integrity"]["I3"]["trace_blocks"], 0)
        self.assertEqual(pa["integrity"]["I3"]["pre_execution"], 0)
        self.assertEqual(pa["integrity"]["relaxed_for_dry_run"], ["I1", "I2", "I5"])
        for name in ("E1", "E2", "E3a", "E3b", "E5", "E6"):
            self.assertEqual(pa[name]["verdict"], "NOT TESTED", name)
        self.assertEqual(pa["S2"]["verdict"], "NOT TESTED")
        self.assertEqual(pa["primary"]["orders"], 0)
        self.assertEqual(pa["S3"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(pa["S3"]["premise_problems"], ["no concealment order was issued"])
        self.assertEqual(pa["S3"]["compared"]["state digests"], 1801)

    def test_reference_is_deterministic_across_its_repetitions(self) -> None:
        reps = self.d["reference determinism against the Sprint 1 repetitions"]
        self.assertEqual(sorted(reps), ["x01", "x02", "x03"])
        for rep in reps.values():
            self.assertEqual(rep, {"state_digests_equal": True, "trace_digests_equal": True,
                                   "final_scores_equal": True, "steps": 1801})

    def test_e4_machinery_on_the_corpus_game(self) -> None:
        e4 = self.d["E4 machinery on the H0 game of 2120531121"]
        self.assertTrue(e4["control_valid"])
        self.assertEqual(e4["E4a"]["verdict"], "NOT TESTED")
        self.assertEqual(e4["control"]["agree"], e4["control"]["target_steps"])

    def test_calibration_and_premise(self) -> None:
        self.assertEqual(self.c["agree"], self.c["target_steps"])
        self.assertEqual(self.p["first_order_decisions"], [{"k": 717, "units": 2}, {"k": 736, "units": 2}])
        self.assertEqual(self.p["baseline_v2_actions_equal_to_recorded"], self.p["decisions"])

    def test_equivalence_on_every_population(self) -> None:
        for population, counts in self.e["populations"].items():
            for key, value in counts.items():
                if key != "orders":
                    self.assertEqual(value, counts["decisions"], (population, key))
        self.assertEqual({p: c["orders"] for p, c in self.e["populations"].items()},
                         {"H0": 234, "H1": 60, "H2": 429})


if __name__ == "__main__":
    unittest.main()
