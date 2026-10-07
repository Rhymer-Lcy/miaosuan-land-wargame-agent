"""Sprint 21: the committed public files of the direct-fire adjudication-semantics audit (no private data needed).

The protocol is rebuilt and compared byte for byte; the inputs, the mutation record and, once present, the result files
are bound to the registration and to each other; the disposition is recomputed from the public per-class statuses by
the frozen rule; and no public file carries a bare numeric key or a candidate identity.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s21_semantics as sm

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s21-direct-fire-semantics"
RESULTS = ("coverage.json", "k2.json", "k4.json", "k5.json", "k6.json", "semantics.json", "disposition.json")


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def driver():
    spec = importlib.util.spec_from_file_location("s21_driver", ROOT / "scripts" / "s21_semantics.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def keys(node, path="$"):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k
            yield from keys(v, f"{path}.{k}")
    elif isinstance(node, list):
        for v in node:
            yield from keys(v, path)


class RegistrationTest(unittest.TestCase):
    def test_protocol_regenerates(self) -> None:
        self.assertEqual((OUT / "protocol.json").read_text(encoding="utf-8"), driver().dump(driver().protocol()))

    def test_protocol_content(self) -> None:
        p = load("protocol.json")
        self.assertEqual(p["engine_sessions"], 0)
        self.assertEqual(p["dispositions_first_match"], list(sm.DISPOSITIONS))
        self.assertEqual(p["required_classes"], [sm.INFANTRY, sm.VEHICLE, sm.AIRCRAFT, sm.FORTIFICATION])
        self.assertEqual(p["k4"]["probability_status_at_registration"], sm.K4P_UNRESOLVED)
        self.assertEqual(len(p["k5"]["relations"]), 12)
        self.assertEqual(len(p["k5"]["short_relations"]), 4)
        self.assertEqual(p["hh_changed_shots"], 94)
        self.assertEqual(p["s20_replay_sha256"], sha256(ROOT / "evaluation" / "s20-t11-replay" / "replay.json"))

    def test_inputs(self) -> None:
        i = load("inputs.json")
        usable = [e for e in i["inventory"] if e["usable"]]
        self.assertEqual(len(i["corpus"]), 18)
        self.assertEqual(sorted((e["folder"], e["game"]) for e in usable),
                         sorted((e["folder"], e["game"]) for e in i["corpus"]))
        self.assertEqual((sum(e["shoot_actions"] for e in usable), sum(e["judge_records"] for e in usable)), (982, 1210))
        self.assertEqual({e["engine_version"] for e in usable}, {"4.1.0"})
        self.assertTrue(all(not e["usable"] and e["reasons_not_usable"] for e in i["inventory"] if e not in usable))
        self.assertIn("baseline-v2-target-ownership-prevalence-1", i["not_opened"])
        self.assertNotIn("baseline-v2-target-ownership-prevalence-1", json.dumps(i["inventory"]))
        self.assertEqual(i["s20_replay"]["sha256"], sha256(ROOT / "evaluation" / "s20-t11-replay" / "replay.json"))
        for e in i["corpus"]:
            self.assertEqual(sorted(e["files"]), ["compact", "record", "windows"])

    def test_mutation_record(self) -> None:
        m = load("mutation.json")
        self.assertEqual(m["declared"], m["killed"])
        self.assertEqual(m["declared"], len(m["mutants"]))
        self.assertGreaterEqual(m["declared"], 36)
        source = Path(sm.__file__).read_bytes()
        self.assertEqual(m["source_sha256"], hashlib.sha256(source.replace(b"\r\n", b"\n")).hexdigest())

    def test_no_bare_numeric_keys_or_candidate_identities(self) -> None:
        for path in sorted(OUT.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for where, k in keys(data):
                self.assertFalse(str(k).lstrip("-").isdigit(), f"{path.name} {where}.{k}")
            text = path.read_text(encoding="utf-8")
            for word in ("t9-batch-capacity-v3", "t9-delayed-post-stage", "t9-capacity-allocation", "t7-idle-concealment"):
                self.assertNotIn(word, text, path.name)
            if path.name in RESULTS:  # the sanitizer forbids keys such as "path", which the frozen inputs need
                self.assertEqual(sm.public_problems(data, []), [], path.name)


class SyntheticPublicOutputTest(unittest.TestCase):
    """The driver's public aggregates of a synthetic corpus whose unit identifiers are small integers pass the
    sanitizer: no forbidden key, no identifier as a key or a word, no bare numeric key."""

    def test_public_aggregates_pass_the_sanitizer(self) -> None:
        d = driver()
        corpus = d.Corpus()

        def unit(obj, type_, blood, hex_):
            return {"obj_id": obj, "color": 0 if obj % 2 else 1, "type": type_, "sub_type": 0, "blood": blood,
                    "max_blood": 4, "keep": 0, "stack": 0, "armor": 2, "cur_hex": hex_, "where": "operators"}

        shooter, target = unit(3, 2, 2, 1234), unit(4, 1, 2, 1235)
        rec = {"att_obj_id": 3, "target_obj_id": 4, "wp_id": 36, "att_level": 5, "random1": 2, "random2": 3,
               "random2_rect": 5, "ori_damage": 1, "rect_damage": 0, "damage": 1, "ele_diff": -1, "distance": 7,
               "att_obj_blood": 2, "cur_step": 9, "attack_color": 1, "target_color": 0, "type": sm.DIRECT_FIRE_TYPE}
        corpus.shots = [{"source": "s12-v3-primary-1", "game": "g", "k": 9, "cur_step": 9, "seat": 11, "faction": 1,
                         "status": sm.PAIRED, "shooter_class": sm.VEHICLE, "target_class": sm.INFANTRY, "shooter": shooter,
                         "target": target, "weapon": 36, "listed_status": "listed", "listed": 5, "judged": 5,
                         "ele_diff": -1, "att_obj_blood": 2, "record_index": 0}]
        corpus.records = [{"source": "s12-v3-primary-1", "game": "g", "k": 9, "status": sm.RECORD_PAIRED, "record": rec,
                           "attacker": shooter, "target": target, "target_class": sm.INFANTRY, "present_after": True,
                           "blood_after": 1, "records_on_target_in_step": 1, "linked_removal": False}]
        corpus.removals = [{"source": "s12-v3-primary-1", "game": "g", "k": 9, "class": sm.VEHICLE, "on_board": False,
                            "linked_to_removed_unit_with_record": True, "unit": unit(5, 2, 1, 1236)}]
        corpus.fort_occupants = [{"class": sm.INFANTRY, "own_record": False, "removed": False, "blood_lost": True,
                                  "fort_removed": False}]
        corpus.games = [{"source": "s12-v3-primary-1", "game": "g", "steps": 10, "policy_classes": ["baseline-v2"],
                         "shot_status": {sm.PAIRED: 1}}]
        public = d.analyse(corpus)
        self.assertEqual(sorted(public), sorted(RESULTS))
        hidden = list(range(0, 50)) + [1234, 1235, 1236]
        for name, data in public.items():
            self.assertEqual(sm.public_problems(data, hidden), [], name)
            for where, k in keys(data):
                self.assertFalse(str(k).lstrip("-").isdigit(), f"{name} {where}.{k}")
        self.assertEqual(public["disposition.json"]["disposition"], sm.DISPOSITIONS[0])  # one game is not the corpus


@unittest.skipUnless((OUT / "disposition.json").exists(), "results not yet written")
class ResultsTest(unittest.TestCase):
    def test_results_are_bound_to_the_registration(self) -> None:
        for name in RESULTS:
            data = load(name)
            self.assertEqual(data["protocol_sha256"], sha256(OUT / "protocol.json"), name)
            self.assertEqual(data["inputs_sha256"], sha256(OUT / "inputs.json"), name)
            self.assertEqual(data["study_id"], sm.STUDY_ID)

    def test_sufficiency_and_disposition_follow_the_frozen_rule(self) -> None:
        sem, disp, cov = load("semantics.json"), load("disposition.json"), load("coverage.json")
        for cls, row in sem["by_class"].items():
            expected = sm.class_sufficiency(row["k2"], row["k4_probability"], row["k5"], row["k6"])
            self.assertEqual((row["items"], row["sufficient"]), (expected["items"], expected["sufficient"]), cls)
        k2, k5, k6 = load("k2.json"), load("k5.json"), load("k6.json")
        for cls in sm.TARGET_CLASSES:
            self.assertEqual(sem["by_class"][cls]["k2"], k2["by_target_class"][cls])
            self.assertEqual(sem["by_class"][cls]["k5"], k5["by_class"][cls]["status"])
            self.assertEqual(sem["by_class"][cls]["k6"], k6["by_class"][cls]["status"])
        self.assertEqual(cov["integrity_ok"], cov["integrity_problems"] == 0 and cov["games"] == 18)
        recomputed = sm.disposition(cov["integrity_ok"], sem["by_class"], sem["required_classes"])
        self.assertEqual(disp["disposition"], recomputed["disposition"])
        self.assertEqual(disp["insufficient_required_classes"], recomputed["insufficient_required_classes"])
        self.assertEqual(disp["engine_sessions"], 0)
        self.assertEqual(load("k4.json")["probability_law"]["status"], sm.K4P_UNRESOLVED)
        if disp["disposition"] != sm.DISPOSITIONS[2]:
            self.assertIsNone(disp["t11_completion"])
            self.assertFalse((OUT / "kill_model.json").exists())
            self.assertFalse((OUT / "t11_completion.json").exists())


if __name__ == "__main__":
    unittest.main()
