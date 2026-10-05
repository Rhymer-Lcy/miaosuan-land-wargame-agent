"""Sprint 14: bind the committed design-competition results to each other, to the frozen protocol and to the frozen
candidate module (``docs/SPRINT14_REDISTRIBUTION.md``). Reads committed files only."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation import s14_design as sx
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files
from miaosuan_agent.experiments import t9_redistribution as tr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s14-redistribution-design"
ADVERSE = ("adverse-2120531121-c3", "adverse-1930331196-c3", "adverse-1930331196-c2")


def load(name: str):
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResultsTest(unittest.TestCase):
    def test_the_candidate_module_is_the_one_pinned_before_the_replay(self) -> None:
        pinned = load("inputs")["candidates"]
        sources = rr.candidate_sources() + ("experiments/shoot_reservation.py",) + tuple(pinned["module_files"])
        self.assertEqual(digest_of_files(policy_source_files(sources=sources)), pinned["policy_source_sha256"])
        self.assertEqual(sorted(pinned["rules"]), sorted(tr.RULES))
        self.assertEqual(load("inputs")["gate_thresholds"], sx.GATE)

    def test_files_bind_to_inputs_and_timing(self) -> None:
        self.assertEqual(load("replay")["inputs_sha256"], sha256(OUT / "inputs.json"))
        gate = load("gate")
        self.assertEqual(gate["timing_sha256"], sha256(OUT / "timing.json"))
        self.assertEqual(gate["thresholds"], sx.GATE)
        for name in ADVERSE + ("replay", "gate", "mutation", "timing", "inputs"):
            self.assertLess((OUT / f"{name}.json").stat().st_size, 100_000, name)

    def test_fidelity_held_and_sprint13_figures_reproduce(self) -> None:
        self.assertEqual(load("gate")["fidelity_problems"], [])
        primary = load("replay")["primary"]
        t9 = primary["t9-v1"]["games"]
        expected = sx.S13_EXPECTED["t9-v1"]
        self.assertEqual({g: t9[g]["redirects"] for g in t9}, expected["redirects"])
        self.assertEqual({g: t9[g]["emitted_ground_moves"] for g in t9}, expected["emitted"])
        self.assertEqual({g: t9[g]["first_decision_redirects"] for g in t9}, expected["first_decision_redirects"])
        for name, values in sx.S13_EXPECTED["pooled"].items():
            for key, value in values.items():
                self.assertEqual(primary[name]["pooled"][key], value, (name, key))
        a0, o2 = primary["feasible-value-redirect"], primary["O2"]  # the minimal candidate is O2
        self.assertEqual(a0["seats"], o2["seats"])
        for game in a0["games"]:
            for key in ("redirects", "emitted_ground_moves", "first_decision_redirects", "redirected_units", "stages",
                        "withholds", "destinations"):
                self.assertEqual(a0["games"][game][key], o2["games"][game][key], (game, key))
        for key in ("slot_vs_t9-v1", "orders_vs_t9-v1", "orders_vs_v3", "redirects"):
            self.assertEqual(a0["pooled"][key], o2["pooled"][key], key)

    def test_gate_rows_are_consistent_and_g9_is_recomputable(self) -> None:
        gate, primary = load("gate"), load("replay")["primary"]
        self.assertEqual(sorted(gate["gates"]), sorted(sx.CANDIDATES))
        t9 = primary["t9-v1"]["seats"]
        for name, row in gate["gates"].items():
            failed = [code for code, item in row["items"].items() if not item["pass"]]
            self.assertEqual(sorted(row["failed"]), sorted(failed), name)
            self.assertEqual(row["pass"], not failed, name)
            ratios = row["items"]["G9_redistribution_restored"]["seat_share_ratios"]
            for seat in ("H1", "H2"):
                self.assertAlmostEqual(ratios[seat], round(primary[name]["seats"][seat]["share"] / t9[seat]["share"], 4),
                                       places=4, msg=(name, seat))

    def test_every_candidate_fails_the_corridor_item_and_the_disposition_follows(self) -> None:
        gate = load("gate")
        self.assertTrue(all("G12_1930331196_corridors" in row["failed"] for row in gate["gates"].values()))
        self.assertEqual(gate["selection"], {"selected": None, "steps": []})
        self.assertEqual(gate["disposition"], sx.disposition([], gate["gates"], gate["selection"]))
        self.assertEqual(gate["disposition"]["disposition"], "NO_ENGINE_CANDIDATE")
        c3 = load("adverse-1930331196-c3")
        self.assertEqual(c3["anchors"]["direct_fire_actions"], 8)
        for name in sx.CANDIDATES:
            self.assertGreater(c3["policies"][name]["shooters_redirected"], 0, name)

    def test_the_mutation_record_is_complete(self) -> None:
        record = load("mutation")
        self.assertTrue(record["unmutated_tests_pass"])
        self.assertEqual((record["killed"], record["total"]), (len(record["mutations"]), len(record["mutations"])))
        self.assertGreaterEqual(record["total"], 30)

    def test_the_document_states_the_disposition(self) -> None:
        text = (ROOT / "docs" / "SPRINT14_REDISTRIBUTION.md").read_text(encoding="utf-8")
        self.assertIn("**NO_ENGINE_CANDIDATE.**", text)


if __name__ == "__main__":
    unittest.main()
