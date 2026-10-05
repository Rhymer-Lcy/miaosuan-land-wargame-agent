"""The committed Sprint 13 diagnosis files (``evaluation/s13-v3-diagnosis/``) against each other, Sprint 12's committed
report and the registered rule. Reads only public files and the checkout; regeneration from the private inputs is
``tests/test_real_s13_diagnosis.py`` (server only).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s13_diagnosis as sd

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "evaluation" / "s13-v3-diagnosis"
NAMES = ("reconstruction", "redistribution", "reservations", "features", "oracles", "sequence", "disposition")


def load(name: str):
    return json.loads((FOLDER / f"{name}.json").read_text(encoding="utf-8"))


def driver():
    spec = importlib.util.spec_from_file_location("s13_driver_for_results", ROOT / "scripts" / "s13_v3_diagnosis.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = {name: load(name) for name in NAMES}
        cls.inputs = json.loads((FOLDER / "inputs.json").read_text(encoding="utf-8"))
        cls.report = json.loads((ROOT / "evaluation" / "s12-v3-primary-1" / "report.json").read_text(encoding="utf-8"))
        cls.driver = driver()

    def games(self, name: str):
        return {g["game_id"]: g for g in self.files[name]["games"]}

    def test_files_are_small_private_free_and_bound_to_the_inputs(self) -> None:
        digest = hashlib.sha256((FOLDER / "inputs.json").read_bytes()).hexdigest()
        for name in NAMES:
            self.assertLess((FOLDER / f"{name}.json").stat().st_size, 100_000)
            self.assertEqual(sd.public_check(self.files[name]), [], name)
            self.assertEqual(self.files[name]["inputs_sha256"], digest, name)
        self.assertEqual(self.inputs["policies"], self.driver.FROZEN)
        self.assertEqual(self.driver.policy_digests(), self.driver.FROZEN)
        self.assertEqual(len(self.inputs["s12"]["games"]), 4)
        self.assertEqual(len(self.inputs["s9"]["games"]), 30)

    def test_the_label_follows_from_the_published_facts(self) -> None:
        red, res, seq = self.games("redistribution"), self.games("reservations"), self.files["sequence"]["comparison"]
        divergence = {g["game_id"]: g["divergence_snapshot"] for cell in ("H1", "H2") for g in seq[cell]["games"]}
        per_game = {gid: sd.game_materiality(red[gid]["a"], res[gid]["b"], divergence[gid]) for gid in red}
        disposition = self.files["disposition"]
        self.assertEqual(per_game, disposition["per_game"])
        overlap = self.files["oracles"]["overlap"]
        jaccard = overlap["both"] / (overlap["a_unit_decisions"] + overlap["b_unit_decisions"] - overlap["both"])
        self.assertEqual(round(jaccard, 4), overlap["jaccard"])
        sa = sum(g["a"]["distinct_redirected"] for g in red.values())
        sb = sum(g["b"]["distinct_admitted"] for g in res.values())
        prospective = self.files["features"]["prospectively_separating"]
        self.assertEqual(prospective, any(s["separating"] for s in self.files["features"]["separation"].values()))
        result = sd.disposition(per_game, disposition["seats"], jaccard, sa, sb, prospective)
        for key, value in result.items():
            self.assertEqual(disposition[key], value, key)
        self.assertIn(disposition["label"], sd.LABELS)
        self.assertEqual(disposition["thresholds"], dict(sd.RULE))

    def test_classes_partition_every_differing_order(self) -> None:
        recon = self.files["reconstruction"]
        pooled = {c: 0 for c in sd.CLASSES}
        for g in recon["games"]:
            self.assertEqual(sum(g["classes"].values()) + g["unchanged_orders"], g["orders"], g["game_id"])
            for c in sd.CLASSES:
                pooled[c] += g["classes"][c]
                self.assertEqual(sum(row[c] for row in g["classes_by_interval"].values()), g["classes"][c])
                objective_total = sum(row[c] for row in g["classes_by_objective"].values())
                self.assertLessEqual(objective_total, g["classes"][c])
            self.assertEqual(sum(r["count"] for r in g["classes_by_v3_reason"]), sum(g["classes"].values()))
            self.assertEqual(g["decisions"], 2881)
            self.assertEqual(g["unrelated_actions"]["differences"], 0)
            self.assertGreater(g["unrelated_actions"]["actions_compared"], 0)
        self.assertEqual(pooled, recon["pooled_classes"])
        self.assertEqual(pooled["OTHER"], 0)

    def test_redirects_agree_across_files(self) -> None:
        red, oracles, recon = self.games("redistribution"), self.games("oracles"), self.games("reconstruction")
        for gid, g in red.items():
            redirects = g["a"]["redirects"]
            self.assertEqual(sum(r["count"] for r in g["redirects"]), redirects)
            self.assertEqual(sum(r["count"] for r in g["redirect_timing"]), redirects)
            self.assertEqual(oracles[gid]["policies"]["t9-v1"]["cross_objective"], redirects)
            self.assertEqual(sum(recon[gid]["classes"][c] for c in sd.CLASSES[:3]), redirects)
            self.assertEqual(sum(recon[gid]["redirect_causes"].values()), redirects)
            self.assertEqual(oracles[gid]["policies"]["t9-v3"]["cross_objective"], 0)
            self.assertEqual(oracles[gid]["policies"]["t9-v2"]["cross_objective"], 0)
            self.assertEqual(oracles[gid]["policies"]["O1"]["cross_objective"], 0)
            self.assertEqual(oracles[gid]["policies"]["O1"]["admitted_vs_v3"],
                             self.games("reservations")[gid]["b"]["admitted_decisions"])

    def test_sprint12_facts_are_reproduced(self) -> None:
        report = {g["game_id"]: g for g in self.report["games"]}
        holders = 0
        for gid, g in self.games("reservations").items():
            check = g["sprint12_cross_check"]
            self.assertEqual(check["unproductive"], report[gid]["unproductive"])
            self.assertEqual(check["places_outcomes"], report[gid]["places"]["outcomes"])
            self.assertEqual(check["unproductive_pairs"], report[gid]["unproductive"]["unproductive_holders"])
            self.assertEqual(check["unproductive_pair_fates"], {"DESTROYED": check["unproductive_pairs"]})
            self.assertEqual(g["b"]["held_selectable"], report[gid]["unproductive"]["holds"])
            rec = g["reconciliation"]
            self.assertEqual(rec["lost_places"], report[gid]["places"]["outcomes"]["LOST"])
            self.assertEqual(rec["destroyed_episodes"] + rec["lost_places_without_episode"], rec["lost_places"])
            self.assertEqual(g["episodes"]["destroyed_blocking"]["holders"] + rec["destroyed_pairs_without_episode"],
                             check["unproductive_pairs"])
            holders += check["unproductive_pairs"]
        self.assertEqual(holders, 27)

    def test_the_mutation_record_belongs_to_the_current_sources(self) -> None:
        record = load("mutation")
        self.assertEqual(record["killed"], record["total"])
        self.assertGreaterEqual(record["total"], 30)
        for path, value in record["sources"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest(), value, path)


if __name__ == "__main__":
    unittest.main()
