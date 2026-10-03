"""The frozen record inventory of the T7 design study (``scripts/t7_study.py``; maintenance revision of 2026-10-03).

Sprint 5's issued-action census read every game record under ``local/evaluation/`` at run time, so records written
later (Sprint 6's probe games) changed it and broke the byte-identical rebuild of the published outputs. The census
now reads exactly the records named by ``evaluation/t7-design-1/record-inventory.json``. SYNTHETIC records check that
later records, in new or in original folders, are ignored and that a missing, changed, duplicated or malformed entry
stops the study; the committed inventory is checked against the published audit; privately (skipped when the records
are absent) the real inventory reproduces the published census with Sprint 6's records present.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "t7-design-1"
spec = importlib.util.spec_from_file_location("t7_study", ROOT / "scripts" / "t7_study.py")
STUDY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STUDY)
#: SHA-256 of the published outputs as committed in Sprint 5 (e3108dd); the maintenance revision must not change them.
PUBLISHED = {"audit.json": "46b3bd7eedb396df778bd35376bfcce5561a7647e400be74d1083ff5e66803e3",
             "candidates.json": "0b52d8c5df9a9b71b635d20762495c968c5c41918fede28daea4f26d6ee289c3"}
SPRINT6_RECORDS = ("t7-mechanism-probe-1/games/1910631192.C3.pa.json",
                   "t7-mechanism-probe-1/games/2120531121.H1.pb1.json",
                   "t7-mechanism-probe-1/games/2120531121.H2.pb2.json")


def entry(rel: str, data: bytes) -> str:
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16] + ":" + hashlib.sha256(data).hexdigest()[:32]


def record(policy: str, conceal: int = 0) -> bytes:
    return json.dumps({"seats": [{"policy": policy, "actions_by_type": {"1": 3, "6": conceal}},
                                 {"policy": "inert-v0", "actions_by_type": {"333": 1}}]}).encode("utf-8")


class SyntheticInventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "evaluation"
        self.files = {"study-a/games/g1.json": record("policy-a"), "study-a/games/g2.json": record("policy-a", 2),
                      "study-b/games/g1.json": record("policy-b")}
        for rel, data in self.files.items():
            self.write(rel, data)
        self.spec = self.inventory(sorted(entry(rel, data) for rel, data in self.files.items()))
        self.path = Path(self.tmp.name) / "inventory.json"
        self.save(self.spec)
        self.original = STUDY.records(self.root, self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    @staticmethod
    def inventory(entries):
        return {"schema": STUDY.INVENTORY_SCHEMA, "count": len(entries), "entries": list(entries),
                "inventory_sha256": hashlib.sha256("\n".join(entries).encode("ascii")).hexdigest()}

    def save(self, spec) -> None:
        self.path.write_text(json.dumps(spec), encoding="utf-8")

    def test_reads_exactly_the_inventory(self) -> None:
        self.assertEqual(self.original["files"], 3)
        self.assertEqual(self.original["folders"], ["study-a", "study-b"])
        self.assertEqual(self.original["t7_actions_by_policy"]["policy-a"]["6"], 2)
        self.assertEqual(self.original["t7_actions_by_policy"]["inert-v0"]["seat-games"], 3)

    def test_a_later_record_in_a_new_folder_is_ignored(self) -> None:
        self.write("study-c/games/g9.json", record("policy-c", 16))
        self.assertEqual(STUDY.records(self.root, self.path), self.original)

    def test_a_later_record_in_an_original_folder_is_ignored(self) -> None:
        self.write("study-a/games/g9.json", record("policy-a", 7))
        self.assertEqual(STUDY.records(self.root, self.path), self.original)

    def test_a_missing_record_fails(self) -> None:
        (self.root / "study-b" / "games" / "g1.json").unlink()
        with self.assertRaisesRegex(STUDY.InventoryError, "1 inventory records are missing"):
            STUDY.records(self.root, self.path)

    def test_a_changed_record_fails(self) -> None:
        self.write("study-a/games/g1.json", record("policy-a", 1))
        with self.assertRaisesRegex(STUDY.InventoryError, "1 inventory records have changed"):
            STUDY.records(self.root, self.path)

    def test_duplicate_entries_fail(self) -> None:
        entries = self.spec["entries"] + [self.spec["entries"][0]]
        self.save(self.inventory(entries))
        with self.assertRaisesRegex(STUDY.InventoryError, "duplicate"):
            STUDY.records(self.root, self.path)
        clash = self.spec["entries"][0][:17] + "0" * 32  # same path digest, another content digest
        self.save(self.inventory(self.spec["entries"] + [clash]))
        with self.assertRaisesRegex(STUDY.InventoryError, "duplicate"):
            STUDY.records(self.root, self.path)

    def test_malformed_inventories_fail(self) -> None:
        for bad in ("XYZ", self.spec["entries"][0].upper(), self.spec["entries"][0][:-1], 7,
                    self.spec["entries"][0].replace(":", "-")):
            self.save(self.inventory(self.spec["entries"][1:] + [bad]) if isinstance(bad, str) else
                      dict(self.spec, entries=self.spec["entries"][1:] + [bad]))
            with self.assertRaisesRegex(STUDY.InventoryError, "malformed", msg=repr(bad)):
                STUDY.records(self.root, self.path)
        for broken in (dict(self.spec, count=4), dict(self.spec, inventory_sha256="0" * 64),
                       dict(self.spec, schema="other"), {k: v for k, v in self.spec.items() if k != "entries"}):
            self.save(broken)
            with self.assertRaises(STUDY.InventoryError):
                STUDY.records(self.root, self.path)

    def test_an_excluded_study_cannot_be_inventoried(self) -> None:
        rel = "baseline-v2-target-ownership-prevalence-1/games/g.json"
        self.write(rel, record("x"))
        spec = self.inventory(sorted(self.spec["entries"] + [entry(rel, record("x"))]))
        self.save(spec)
        with self.assertRaisesRegex(STUDY.InventoryError, "excluded study"):
            STUDY.records(self.root, self.path)


class CommittedInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads((OUT / "record-inventory.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))

    def test_inventory_matches_the_published_census(self) -> None:
        self.assertEqual(self.spec["count"], 1284)
        self.assertEqual(self.spec["count"], self.audit["issued_records"]["files"])
        self.assertEqual(len(set(e[:16] for e in self.spec["entries"])), 1284)
        self.assertEqual(self.spec["entries"], sorted(self.spec["entries"]))
        self.assertIn("RETROSPECTIVE MAINTENANCE RECONSTRUCTION", self.spec["status"])

    def test_sprint6_records_are_not_inventoried(self) -> None:
        keys = {e[:16] for e in self.spec["entries"]}
        for rel in SPRINT6_RECORDS:
            self.assertNotIn(hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16], keys, rel)
        self.assertNotIn("t7-mechanism-probe-1", self.audit["issued_records"]["folders"])

    def test_published_outputs_are_unchanged(self) -> None:
        for name, digest in PUBLISHED.items():
            self.assertEqual(hashlib.sha256((OUT / name).read_bytes()).hexdigest(), digest, name)


@unittest.skipUnless((STUDY.LOCAL_EVAL / SPRINT6_RECORDS[0]).is_file(), "the game records are private (git-ignored)")
class RealInventoryTest(unittest.TestCase):
    def test_real_records_reproduce_the_published_census_with_sprint6_present(self) -> None:
        for rel in SPRINT6_RECORDS:
            self.assertTrue((STUDY.LOCAL_EVAL / rel).is_file(), rel)
        published = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))["issued_records"]
        selected = STUDY.inventory_records()
        self.assertEqual(len(selected), 1284)
        self.assertFalse(any(p.parts[-3] == "t7-mechanism-probe-1" for p in selected))
        self.assertEqual(STUDY.records(), published)


if __name__ == "__main__":
    unittest.main()
