"""The candidate manifest builder and the single owners of its pinned constants."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class GoldenConstantsTest(unittest.TestCase):
    def test_single_owners_agree(self) -> None:
        from miaosuan_agent.evaluation import candidate_manifest as cm
        from tests import test_decision_determinism, test_occupy_reservation

        self.assertEqual(cm.V0_GOLDEN_TRACE_CHAIN, test_decision_determinism.GOLDEN_TRACE_CHAIN)
        self.assertEqual(cm.GOLDEN_TRACE_CHAIN, test_occupy_reservation.GOLDEN_TRACE_CHAIN)



class BuilderTest(unittest.TestCase):
    """Built from the committed baseline-v0 files and a synthetic replay aggregate."""

    def build(self):
        import hashlib
        import json

        from miaosuan_agent.evaluation import candidate_manifest as cm

        v0 = ROOT / "evaluation" / "baseline-v0"
        self.v0_manifest = json.loads((v0 / "manifest.json").read_text(encoding="utf-8"))
        self.v0_diagnostics = json.loads((v0 / "diagnostics.json").read_text(encoding="utf-8"))
        replay = {"decision_states": 10, "identical": 8, "differing": 2, "unexplained": 0, "suppressed_occupations": 3}
        return cm.build(self.v0_manifest, hashlib.sha256((v0 / "results.json").read_bytes()).hexdigest(),
                        self.v0_diagnostics, "c" * 64, ["agent.py"], replay, "d" * 64)

    def test_protocol_is_copied_and_only_the_policy_substituted(self) -> None:
        from miaosuan_agent.decision import BASELINE_ID, INERT_ID
        from miaosuan_agent.evaluation import manifest as mf
        from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID

        built = self.build()
        for key in ("engine", "selection", "scenarios", "repetitions", "order", "players", "caps", "randomness",
                    "replay_check_every", "gate1", "gate_criteria"):
            self.assertEqual(built[key], self.v0_manifest[key], key)
        pairs = [(c["red"], c["blue"]) for c in built["conditions"]]
        self.assertEqual(pairs, [(CANDIDATE_ID, CANDIDATE_ID), (CANDIDATE_ID, INERT_ID), (INERT_ID, CANDIDATE_ID),
                                 (INERT_ID, INERT_ID)])
        self.assertEqual([c["id"] for c in built["conditions"]], [c["id"] for c in self.v0_manifest["conditions"]])
        self.assertEqual(built["policy_under_test"], CANDIDATE_ID)
        self.assertEqual(len(mf.games(built)), len(mf.games(self.v0_manifest)))
        self.assertEqual([g.game_id for g in mf.games(built)], [g.game_id for g in mf.games(self.v0_manifest)])
        self.assertEqual(built["reference"]["identity"], BASELINE_ID)
        self.assertEqual(built["reference"]["manifest_sha256"], mf.digest(self.v0_manifest))
        self.assertEqual(built["reference"]["policy_source_sha256"], self.v0_manifest["policy_source"]["sha256"])

    def test_taxonomy_evidence_comes_from_the_v0_diagnostics(self) -> None:
        built = self.build()
        classes = {c["code"]: c["count"] for c in self.v0_diagnostics["refusal_context"]["classes"]}
        for code, entry in built["refusal_taxonomy"]["codes"].items():
            self.assertIn(f"{classes[int(code)]} of {classes[int(code)]} diagnosed refusals", entry["evidence"])
        self.assertEqual(built["refusal_taxonomy"]["unknown_code"], "unclassified")
        self.assertIn("supplementary", built["refusal_taxonomy"]["relation_to_g4"])

    def test_deterministic_and_pinned(self) -> None:
        from miaosuan_agent.evaluation import manifest as mf
        from miaosuan_agent.evaluation.metrics import LATER_SEAT_FIELDS

        first, second = self.build(), self.build()
        self.assertEqual(mf.digest(first), mf.digest(second))
        self.assertEqual(first["counterfactual_replay"]["unexplained"], 0)
        self.assertEqual(first["registered_seat_metrics"], list(LATER_SEAT_FIELDS))
        self.assertTrue(any(line.startswith("A8 ") for line in first["acceptance"]))
        self.assertNotRegex(mf.canonical_bytes(first).decode("utf-8"), r"20\d\d-\d\d-\d\dT")


class AmendmentTest(unittest.TestCase):
    def test_gate1_rule_excludes_only_g4(self) -> None:
        import json

        from miaosuan_agent.evaluation import candidate_manifest as cm

        self.assertEqual(cm.GATE1_REQUIRED, ("G1", "G2", "G3", "G5", "G6"))
        self.assertEqual(cm.AMENDMENT["number"], 1)
        registered = json.loads((ROOT / "evaluation" / cm.EVALUATION_NAME / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(registered["gate1_required"], list(cm.GATE1_REQUIRED))
        self.assertNotIn("gate1_required", json.loads((ROOT / "evaluation" / "baseline-v0" / "manifest.json")
                                                        .read_text(encoding="utf-8")))
        self.assertTrue(registered["acceptance"][3].startswith("A4 Gate 1 passes its runtime criteria"))

if __name__ == "__main__":
    unittest.main()
