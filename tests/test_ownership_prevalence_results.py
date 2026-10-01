"""The committed result of the target-ownership prevalence diagnostic, checked against its registration.

The registered prefix check failed, so the registered rule withholds every prevalence figure and the next-step
decision; ``problems`` checks that the result says exactly that and that its counts close, and the supplementary
prefix diagnosis is checked against the result. Planted errors must each be caught. Regeneration from the private
records runs only where they exist.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import ownership_prevalence as op

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / op.STUDY_ID
PRIVATE = ROOT / "local" / "evaluation" / op.STUDY_ID / "games"
CHECKS = ("consistency", "in_game_replay", "observation_unchanged", "observer_errors", "offline_replay", "prefix")


def problems(r, d, manifest):
    found = []

    def expect(condition, message):
        if not condition:
            found.append(message)

    integ, instr = r["integrity"], r["instrumentation"]
    games = len(manifest["games"])
    expect(r["manifest_sha256"] == mf.digest(manifest), "manifest digest")
    expect(integ["pass"] == (not integ["problems"]), "integrity pass")
    expect(integ["records"] == games and integ["sessions"] == [1898, 1897 + games], "records and sessions")
    expect(integ["states"] == 1 and integ["leftover_processes"] == 0 and integ["pool_runs"] == 1, "engine state and pool")
    expect(sorted(instr["checks"]) == sorted(CHECKS), "registered checks")
    expect(instr["pass"] == all(instr["checks"].values()), "instrumentation pass")
    expect(instr["checks"]["prefix"] == (instr["prefix_equal"] == instr["games"] == games), "prefix check")
    expect(sum(instr["prefix_games_by_reference_class"].values()) == games, "reference classes")
    expect(instr["checks"]["in_game_replay"] == (instr["in_game_replay_mismatches"] == 0 < instr["in_game_replay_checks"]),
           "in-game replay")
    expect(instr["checks"]["offline_replay"] == (instr["offline_mismatches"] == 0 < instr["offline_decisions"]), "offline replay")
    expect(instr["checks"]["observation_unchanged"] == (instr["observation_mutations"] == 0), "mutations")
    expect(instr["checks"]["consistency"] == (instr["consistency_problems"] == 0), "consistency")
    expect(r["valid"] == (integ["pass"] and instr["pass"]), "validity follows the checks")
    if not r["valid"]:
        expect(r["decision"] is None, "no decision without validity")
        expect(not {"prevalence", "diversity", "structure", "historical", "decision_inputs"} & set(r), "no prevalence")
    else:
        expect(r["decision"] in op.DECISION_RULE["outcomes"], "decision")
    expect(d["registered"] is False, "the diagnosis is supplementary")
    expect(d["games"] == games and d["serial_comparisons"] == games * 15, "diagnosis coverage")
    expect(len(d["failing_games"]) == games - instr["prefix_equal"], "failing games")
    expect(len({f["game"] for f in d["failing_games"]}) == len(d["failing_games"]), "failing games unique")
    for f in d["failing_games"]:
        expect(f["class"] == manifest["references"][".".join(f["game"].split(".")[:2])]["class"], f"{f['game']} class")
        expect(f["best_serial_state_prefix"] >= f["reference_state_prefix"] or not f["state_prefix_equal"], f"{f['game']} states")
        explained = f["reproduces_a_serial_chain"] or any(
            f["best_serial_trace_prefixes"][seat] < length for seat, length in f["reference_trace_prefixes"].items())
        expect(explained, f"{f['game']} failure explained by a short trace prefix or a reproduced chain")
    return found


class PrevalenceResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = json.loads((DIRECTORY / "results.json").read_text(encoding="utf-8"))
        cls.d = json.loads((DIRECTORY / "prefix-diagnosis.json").read_text(encoding="utf-8"))
        cls.m = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))

    def test_figures_close(self) -> None:
        self.assertEqual(problems(self.r, self.d, self.m), [])

    def test_the_registered_rule_stops_before_interpretation(self) -> None:
        self.assertTrue(self.r["integrity"]["pass"])
        self.assertFalse(self.r["instrumentation"]["checks"]["prefix"])
        self.assertFalse(self.r["valid"])
        self.assertIsNone(self.r["decision"])

    def test_no_decision_differed_on_identical_observed_states(self) -> None:
        self.assertEqual(self.d["decisions_differing_on_identical_observed_states"], 0)

    def test_planted_errors_are_caught(self) -> None:
        plants = [(("instrumentation", "prefix_equal"), 1), (("integrity", "records"), -1),
                  (("instrumentation", "observation_mutations"), 1), (("instrumentation", "offline_mismatches"), 1)]
        for path, delta in plants:
            with self.subTest(plant=".".join(path)):
                planted = copy.deepcopy(self.r)
                planted[path[0]][path[1]] += delta
                self.assertTrue(problems(planted, self.d, self.m))
        planted = copy.deepcopy(self.r)
        planted["decision"] = op.DECISION_RULE["outcomes"][0]
        self.assertTrue(problems(planted, self.d, self.m))
        planted = copy.deepcopy(self.r)
        planted["valid"] = True
        self.assertTrue(problems(planted, self.d, self.m))
        planted = copy.deepcopy(self.r)
        planted["prevalence"] = {}
        self.assertTrue(problems(planted, self.d, self.m))
        diagnosis = copy.deepcopy(self.d)
        diagnosis["failing_games"] = diagnosis["failing_games"][1:]
        self.assertTrue(problems(self.r, diagnosis, self.m))
        diagnosis = copy.deepcopy(self.d)
        first = diagnosis["failing_games"][-1]
        first["best_serial_trace_prefixes"] = dict(first["reference_trace_prefixes"])
        first["reproduces_a_serial_chain"] = False
        self.assertTrue(problems(self.r, diagnosis, self.m))

    @unittest.skipUnless(PRIVATE.exists(), "private records not present")
    def test_regenerates_from_the_private_records(self) -> None:
        for command, expected in ((["analyze", "--check"], "results identical"),
                                  (["prefix-diagnosis", "--check"], "prefix diagnosis identical")):
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "ownership_prevalence.py"), *command],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(expected, result.stdout)


if __name__ == "__main__":
    unittest.main()
