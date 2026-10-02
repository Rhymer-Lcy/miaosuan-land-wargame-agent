"""T7 design study: the public outputs regenerate byte for byte, and the rubric is the one frozen with the protocol."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evaluation" / "t7-design-1"
#: SHA-256 of rubric.json as pushed with the protocol in e753456 (fetched back from the public remote).
RUBRIC_SHA256 = "66d77fb7a15fba4e7587e66418de45a00c613da8044bd503c835bbdbe858c1c4"


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenRubric(unittest.TestCase):
    def test_rubric_is_the_frozen_one(self):
        self.assertEqual(hashlib.sha256((EV / "rubric.json").read_bytes()).hexdigest(), RUBRIC_SHA256)


class Regeneration(unittest.TestCase):
    def test_semantics_matrix(self):
        module = script("t7_semantics")
        self.assertEqual((EV / "semantics.json").read_text(encoding="utf-8"),
                         json.dumps(module.build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")

    def test_scores_and_selection(self):
        module = script("t7_rubric")
        scored, selection = module.build()
        self.assertEqual((EV / "scores.json").read_text(encoding="utf-8"), module.dump(scored))
        self.assertEqual((EV / "selection.json").read_text(encoding="utf-8"), module.dump(selection))


class Gates(unittest.TestCase):
    def test_gates_regenerate_and_read_ready(self):
        module = script("t7_gates")
        data = module.build()
        self.assertEqual((EV / "gates.json").read_text(encoding="utf-8"),
                         json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        self.assertEqual({k: v["verdict"] for k, v in data["gates"].items()},
                         {"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS"})
        self.assertEqual(data["disposition"], "READY_FOR_MECHANISM_PROBE")

    def test_disposition_order(self):
        module = script("t7_gates")
        ready = {"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS"}
        self.assertEqual(module.disposition(ready, True, True), "READY_FOR_MECHANISM_PROBE")
        self.assertEqual(module.disposition(ready, False, True), "SHELVE_T7_FOR_NOW")
        self.assertEqual(module.disposition(ready, True, False), "SHELVE_T7_FOR_NOW")
        self.assertEqual(module.disposition(dict(ready, G1="FAIL", G2="UNRESOLVED"), True, True), "REVISE")
        self.assertEqual(module.disposition(dict(ready, G2="UNRESOLVED"), True, True), "NEEDS_ENGINE_PROBE")
        self.assertEqual(module.disposition(dict(ready, G4="UNRESOLVED"), True, True), "NEEDS_ENGINE_PROBE")
        self.assertEqual(module.disposition(dict(ready, G5="FAIL"), True, True), "REVISE")
        self.assertEqual(module.disposition(dict(ready, G3="FAIL"), True, True), "REVISE")

    def test_proposal_elements_are_required(self):
        module = script("t7_gates")
        verdict, evidence = module.g5("")
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(len(evidence["missing"]), len(module.PROPOSAL_ELEMENTS))


class Selection(unittest.TestCase):
    def test_selected_candidate_and_robustness(self):
        selection = json.loads((EV / "selection.json").read_text(encoding="utf-8"))
        rubric = json.loads((EV / "rubric.json").read_text(encoding="utf-8"))
        self.assertEqual(selection["selected"], "A2")
        self.assertEqual(selection["sensitivity"]["variants"], rubric["sensitivity"]["variants"])
        self.assertEqual(selection["sensitivity"]["selected_first_in"], rubric["sensitivity"]["variants"])
        failed = {c: b["failed_mandatory"] for c, b in selection["base"].items() if not b["eligible"]}
        self.assertEqual(failed, {"A1": ["S"], "A3": ["S"], "B1": ["S"], "B2": ["S"]})

    def test_unknown_cells_are_capped(self):
        scores = json.loads((EV / "scores.json").read_text(encoding="utf-8"))
        for cand, row in scores["scores"].items():
            for crit, cell in row.items():
                if cell["unknown"]:
                    self.assertLessEqual(cell["score"], scores["cap_for_unknown"], (cand, crit))
                self.assertTrue(cell["reason"])

    def test_a_scoring_change_changes_the_output(self):
        module = script("t7_rubric")
        saved = module.JUDGED["A2"]["L"]
        try:
            module.JUDGED["A2"]["L"] = (2, False, "planted")
            scored, _ = module.build()
        finally:
            module.JUDGED["A2"]["L"] = saved
        self.assertNotEqual((EV / "scores.json").read_text(encoding="utf-8"), module.dump(scored))


if __name__ == "__main__":
    unittest.main()
