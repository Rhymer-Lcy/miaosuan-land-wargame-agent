"""The shoot-reservation experiment's committed pre-registration artifacts.

The manifest rebuilds byte-identically; the pinned counterfactual replay and both mutation results name the
code and tests that are in the checkout now; the registration document states the manifest's identities and
the pinned counts. Public: committed files only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / sx.EXPERIMENT_NAME
DOCUMENT = ROOT / "docs" / "EVALUATION_SHOOT_RESERVATION.md"


def load(name: str):
    return json.loads((DIRECTORY / name).read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load("manifest.json")
        cls.counterfactual = load("counterfactual-replay.json")
        cls.mutation = load("mutation.json")
        cls.analysis_mutation = load("mutation-analysis.json")

    def test_manifest_rebuilds(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_shoot_experiment_manifest.py"), "--check"],
                                capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_candidate_mutation_result_is_current(self) -> None:
        target = ROOT / self.mutation["target"]
        self.assertEqual(self.mutation["target_sha256"], sha(target))
        self.assertEqual(self.mutation["non_equivalent"]["killed"], self.mutation["non_equivalent"]["total"])
        self.assertEqual(self.mutation["equivalent"]["survived"], self.mutation["equivalent"]["total"])
        self.assertGreaterEqual(self.mutation["non_equivalent"]["total"], 9)
        for row in self.mutation["mutants"]:
            self.assertEqual(row["outcome"], row["expected"], row["mutant"])
        self.assertTrue(self.mutation["pass"])

    def test_analysis_mutation_result_is_current(self) -> None:
        result = self.analysis_mutation
        for name, digest in result["targets"].items():
            self.assertEqual(digest, sha(ROOT / name), name)
        self.assertEqual(result["tests_sha256"], sha(ROOT / "tests" / "test_shoot_experiment.py"))
        self.assertEqual((result["killed"], result["survivors"], result["pass"]), (result["total"], [], True))
        self.assertGreaterEqual(result["total"], 20)

    def test_counterfactual_is_pinned_complete_and_clean(self) -> None:
        pinned = self.manifest["counterfactual_replay"]
        self.assertEqual(pinned["sha256"], sha(DIRECTORY / "counterfactual-replay.json"))
        totals = self.counterfactual["totals"]
        corpus = ROOT / "evaluation" / rr.REMEDIATION_ID / "corpus.json"
        self.assertEqual(self.counterfactual["corpus"]["sha256"], sha(corpus))
        self.assertEqual(totals["states"], json.loads(corpus.read_text(encoding="utf-8"))["decisions_total"])
        self.assertEqual(totals["identical"] + totals["changed"], totals["states"])
        self.assertEqual(totals["displaced_units"], sum(totals[f"class_{c}"] for c in "ABCD"))
        self.assertEqual((totals["class_E"], totals["candidate_duplicate_shots"], totals["first_shot_changed"],
                          self.counterfactual["unexplained_states"]), (0, 0, 0, 0))
        self.assertEqual(self.counterfactual["candidate"]["policy_source_sha256"],
                         self.manifest["groups"]["C"]["policy_source"]["sha256"])
        self.assertEqual(self.counterfactual["baseline"]["policy_source_sha256"], sx.RUNTIME_R1_SOURCE_SHA256)
        for key in ("states", "identical", "changed", "baseline_duplicate_shots", "displaced_units", "class_A",
                    "class_B", "class_C", "class_D", "class_I", "class_E", "candidate_duplicate_shots"):
            self.assertEqual(pinned[key], totals[key], key)

    def test_document_states_the_registered_identities_and_counts(self) -> None:
        flat = " ".join(DOCUMENT.read_text(encoding="utf-8").split())
        groups = self.manifest["groups"]
        prefixes = [policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0], self.manifest["parent"]["golden_trace_chain"],
                    groups["B"]["policy_source"]["sha256"], self.manifest["runtime"]["remediation"]["registration_sha256"],
                    groups["C"]["policy_source"]["sha256"], groups["C"]["golden_trace_chain"]]
        for digest in prefixes:
            self.assertIn(f"`{digest[:8]}…`", flat)
        totals = self.counterfactual["totals"]
        clauses = [f"decisions of the private canonical corpus", f"{totals['states']:,} decisions",
                   f"{totals['identical']:,} decisions were identical and {totals['changed']} changed",
                   f"emitted {totals['baseline_duplicate_shots']} duplicate-target shoot commands, and the candidate "
                   f"displaced exactly {totals['displaced_units']} units",
                   f"{totals['class_A']} shot another target (class A) and {totals['class_D']} did nothing (class D)",
                   f"{self.mutation['non_equivalent']['killed']} of {self.mutation['non_equivalent']['total']} "
                   f"non-equivalent mutants", f"{self.mutation['equivalent']['total']} equivalent mutants survived",
                   f"{self.manifest['repetitions']} per configuration and group",
                   f"That is {self.manifest['games']} new games", "−10 engine score points"]
        for clause in clauses:
            self.assertIn(" ".join(clause.split()), flat, clause)
        for class_label in ("B", "C", "I"):
            self.assertEqual(totals[f"class_{class_label}"], 0)
        for scenario in self.manifest["scenarios"]:
            self.assertIn(scenario["scenario_id"], flat)
        effects = {e["value"]: e for e in self.manifest["planning"]["code_516_per_1000"]["effects"]}
        half, full = effects[-0.5], effects[-1.0]
        self.assertIn(f"50% reduction: {half['power']:.2f}, {half['power_conservative']:.2f} and "
                      f"{half['power_monte_carlo']:.3f}", flat)
        self.assertIn(f"100% reduction: {full['power']:.2f}, {full['power_conservative']:.2f} and "
                      f"{full['power_monte_carlo']:.2f}", flat)

    def test_registration_is_canonical(self) -> None:
        self.assertEqual(self.manifest["design_sha256"], sx.design_digest(self.manifest))
        self.assertEqual(len(mf.digest(self.manifest)), 64)
        self.assertEqual(self.manifest["experiment_id"], sx.EXPERIMENT_ID)


if __name__ == "__main__":
    unittest.main()
