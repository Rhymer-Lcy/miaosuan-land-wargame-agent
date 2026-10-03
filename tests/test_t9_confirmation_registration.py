"""The registration of the T9 confirmatory study: manifest, frozen identities, budget, schedule, pins and the
pre-registration outputs (``docs/T9_CONFIRMATION.md``). Public: reads committed files only."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.experiments import t9_allocation as t9

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "evaluation" / tc.STUDY_ID


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"t9reg_{name}", REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
        cls.digest = mf.digest(cls.manifest)

    def test_the_manifest_rebuilds_byte_identically(self) -> None:
        self.assertTrue(load_script("build_t9_confirmation_manifest").matches())

    def test_frozen_identities(self) -> None:
        m = self.manifest
        self.assertEqual(m["schema"], tc.SCHEMA)
        self.assertEqual(m["track"], "CONFIRMATORY")
        self.assertFalse(m["eligible_for_promotion"])
        self.assertEqual(m["policies"][tc.CANDIDATE_ID]["policy_source"]["sha256"],
                         "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa")
        self.assertEqual(m["policies"][tc.V2_ID]["policy_source"]["sha256"],
                         "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae")
        self.assertEqual((m["candidate"]["capacity"], m["candidate"]["detour_factor"]), (4, 2.0))
        self.assertEqual((t9.CAPACITY, t9.DETOUR), (4, 2.0))
        self.assertEqual(json.loads((REPO / "evaluation" / "s8-t9-v1-rep" / "manifest.json").read_text(encoding="utf-8"))
                         ["policies"][tc.CANDIDATE_ID]["policy_source"], m["policies"][tc.CANDIDATE_ID]["policy_source"])

    def test_execution_and_budget(self) -> None:
        m = self.manifest
        rt = json.loads((REPO / "evaluation" / "runtime-thread-qualification-1" / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(m["execution"], {"workers": 32, "runtime": "baseline-v1-runtime-r2",
                                          "scheduler": rt["production_path"]["scheduler"][0],
                                          "stop_after_consecutive_failures": 3})
        self.assertEqual(m["runtime_environment"], {"OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual(m["budget"], {"ledger_base_session": 2487, "session_cap": 375,
                                       "phases": {"A": 45, "D": 60, "B": 180, "C": 90}})
        self.assertEqual(sum(m["budget"]["phases"].values()), m["budget"]["session_cap"])

    def test_the_schedule_is_the_design_s(self) -> None:
        m = self.manifest
        design = {k: v for k, v in m.items() if k not in ("design_sha256", "games")}
        self.assertEqual(m["design_sha256"], tc.design_digest(design))
        self.assertEqual(m["games"], tc.schedule(m["design_sha256"]))
        self.assertEqual(len(m["games"]), 375)
        self.assertEqual([g["game_id"] for g in m["games"][:45]], [g["game_id"] for g in m["games"] if g["phase"] == "A"])

    def test_every_pin_holds(self) -> None:
        for rel, digest in sorted({**self.manifest["files"], **self.manifest["tests"]}.items()):
            self.assertEqual(tc.normalized_sha256(REPO / rel), digest, rel)
        for key, digest in self.manifest["inputs"].items():
            if key.endswith("(normalised sha256)"):
                self.assertEqual(tc.normalized_sha256(REPO / key.split(" ")[0]), digest, key)

    def test_the_pre_registration_outputs(self) -> None:
        planning = json.loads((BASE / "planning.json").read_text(encoding="utf-8"))
        validation = json.loads((BASE / "validation.json").read_text(encoding="utf-8"))
        self.assertTrue(validation["ok"])
        self.assertEqual(validation["inventory"]["planning_sha256"], hashlib.sha256(
            (BASE / "planning.json").read_bytes()).hexdigest())
        self.assertEqual(validation["rehearsal"]["identity_check_rejected"], validation["rehearsal"]["records"])
        self.assertEqual(validation["rehearsal"]["seat_average"]["estimate"], planning["primary"]["exploratory_estimate"])
        nulls = {k: v["lower_limit_above_0"]["studentized (registered)"] for k, v in validation["calibration"]["table"].items()
                 if k.endswith("| null")}
        self.assertEqual(len(nulls), 6)
        self.assertTrue(all(rate <= 0.03 for rate in nulls.values()), nulls)
        self.assertTrue(all(c["ok"] and c["held_value_equals_occupy_score"] for c in validation["capture"]))
        alarms = planning["gate_false_alarms_on_baseline_v2"]
        self.assertEqual(len(alarms), 16)
        self.assertLessEqual(max(a["rate"] for a in alarms.values()), 0.01)

    def test_the_document_names_this_manifest(self) -> None:
        doc = (REPO / "docs" / "T9_CONFIRMATION.md").read_text(encoding="utf-8")
        self.assertIn(self.digest, doc)
        self.assertIn(self.manifest["design_sha256"], doc)


if __name__ == "__main__":
    unittest.main()
