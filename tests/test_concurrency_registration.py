"""The registered plan of the concurrency qualification, committed before any qualification session.

Public: committed files only. The rebuild of the plan from the shoot experiment's private records runs only
where those records exist.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import concurrency as cq
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import shoot_experiment as sx

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "evaluation" / cq.PLAN_ID / "plan.json"
MANIFEST = ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
DOCUMENT = ROOT / "docs" / "CONCURRENCY_QUALIFICATION.md"
RECORDS = ROOT / "local" / "evaluation" / sx.EXPERIMENT_NAME / "games"


class PlanRegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_identity_and_inputs(self) -> None:
        plan, manifest = self.plan, self.manifest
        self.assertEqual((plan["schema"], plan["plan_id"], plan["purpose"]), (cq.SCHEMA, cq.PLAN_ID, "diagnostic"))
        self.assertEqual(plan["policy"]["code_identity"], sx.CANDIDATE_ID)
        self.assertEqual(plan["policy"]["policy_source"], manifest["groups"]["C"]["policy_source"])
        self.assertEqual(plan["policy"]["golden_trace_chain"], manifest["groups"]["C"]["golden_trace_chain"])
        self.assertEqual(plan["inputs"]["manifest_sha256"], mf.digest(manifest))
        self.assertEqual(plan["inputs"]["players"], manifest["players"])
        self.assertEqual(plan["inputs"]["randomness"], manifest["randomness"])
        self.assertEqual(PLAN.read_text(encoding="utf-8"), cq.text(plan))

    def test_tiers_rules_and_criteria_are_the_module_constants(self) -> None:
        plan = self.plan
        self.assertEqual(plan["tiers"], [dict(t) for t in cq.TIERS])
        self.assertEqual(plan["optional_tiers"], [dict(t) for t in cq.OPTIONAL_TIERS])
        self.assertEqual(plan["criteria"], cq.CRITERIA)
        self.assertEqual(plan["etiquette"], cq.ETIQUETTE)
        for key, value in (("safety_checks", cq.SAFETY_CHECKS), ("independence", cq.INDEPENDENCE),
                           ("stop_conditions", cq.STOP_CONDITIONS), ("measurements", cq.MEASUREMENTS)):
            self.assertEqual(plan[key], list(value), key)
        self.assertEqual(plan["recommendation_rule"], cq.RECOMMENDATION_RULE)
        self.assertEqual(plan["known_refusal_classes"], [list(c) for c in sx.KNOWN_CLASSES])
        self.assertEqual((plan["game_timeout_seconds"], plan["kill_after_seconds"]), (2100, 30))
        self.assertEqual([t["workers"] for t in plan["tiers"]], [1, 1, 2, 4, 8, 16])
        self.assertEqual(plan["tiers"][0]["session_mode"], "exclusive")
        self.assertTrue(all(t["session_mode"] == "shared" for t in plan["tiers"][1:] + plan["optional_tiers"]))

    def test_block_references_and_queues(self) -> None:
        plan = self.plan
        self.assertEqual([b["config"] for b in plan["block"]], list(cq.BLOCK_CONFIGS))
        for entry in plan["block"]:
            ref = entry["reference"]
            self.assertEqual(ref["repetitions"], 15)
            if entry["config"] in cq.DETERMINISTIC_EXPECTED:
                self.assertEqual((ref["class"], len(ref["state_chains"])), ("deterministic", 1))
                self.assertEqual(ref["state_prefix_steps"], ref["state_steps"])
            else:
                self.assertEqual((ref["class"], len(ref["state_chains"])), ("stochastic", 15))
                self.assertLess(ref["state_prefix_steps"], ref["state_steps"])
            self.assertEqual(entry["expected_wall_seconds"], ref["expected_wall_seconds"])
        ids = [e["game_id"] for t in plan["tiers"] + plan["optional_tiers"] for e in cq.tier_queue(plan, t["tier"])]
        self.assertEqual(len(ids), 8 + 16 + 16 + 16 + 32 + 64 + 96 + 128)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(all(i.startswith("cq1.") for i in ids))

    def test_equivalence_corpus(self) -> None:
        corpus = self.plan["equivalence"]["corpus"]
        self.assertEqual(corpus, cq.equivalence_corpus(self.manifest))
        self.assertEqual(len(corpus), 16)
        self.assertEqual(sorted({g.split(".")[2] for g in corpus}), ["B", "C"])
        self.assertEqual(set(self.plan["equivalence"]["references"]), set(corpus))

    def test_document_cites_the_plan(self) -> None:
        flat = " ".join(DOCUMENT.read_text(encoding="utf-8").split())
        self.assertIn(f"`{cq.digest(self.plan)[:8]}…`", flat)
        self.assertIn("evaluation/concurrency-qualification-1/plan.json", flat)

    @unittest.skipUnless(RECORDS.is_dir(), "the shoot experiment's records are private (git-ignored)")
    def test_plan_rebuilds_from_the_private_records(self) -> None:
        spec = importlib.util.spec_from_file_location("build_plan", ROOT / "scripts" / "build_concurrency_plan.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.build(), PLAN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
