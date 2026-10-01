"""The residual-516 diagnostic: registration, the read-only observer, facts, classification and counting."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import itertools
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from miaosuan_agent.decision import BASELINE_ID, INERT_ID
from miaosuan_agent.evaluation import residual516 as rd
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation.identity import digest_of_files

from tests.fixtures import fake_engine
from tests.test_evaluation_game import FACTORIES, Inputs, spec
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / rd.DIAGNOSTIC_ID / "manifest.json"


def load_script(name):
    loader = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def counting_clock():
    ticks = itertools.count()
    return lambda: next(ticks) * 0.001


def game(observer=None, **options):
    options.setdefault("engine_messages", True)
    return play(lambda: fake_engine.FakeEnv(**options), FACTORIES, spec(), Inputs, PLAYERS, clock=counting_clock(),
                replay_policies={BASELINE_ID}, observer=observer)


class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_rebuilds_byte_identically(self) -> None:
        build = load_script("build_residual516_manifest")
        text = json.dumps(build.build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        self.assertEqual(MANIFEST.read_text(encoding="utf-8"), text)

    def test_frozen_identities(self) -> None:
        m = self.manifest
        self.assertEqual(m["policy_source"]["sha256"], rd.BASELINE_V2_SOURCE_SHA256)
        self.assertEqual(digest_of_files(m["policy_source"]["files"]), rd.BASELINE_V2_SOURCE_SHA256)
        self.assertEqual(m["golden_trace_chain"], sx.CANDIDATE_GOLDEN_TRACE_CHAIN)
        self.assertEqual(m["policy_under_test"], sx.CANDIDATE_ID)
        self.assertEqual(m["configuration"], {"scenario_id": "1930331196", "condition": "C3", "red": INERT_ID,
                                              "blue": sx.CANDIDATE_ID})
        self.assertEqual(m["execution"]["workers"], 32)
        self.assertEqual(m["execution"]["runtime"], "baseline-v1-runtime-r2")
        self.assertEqual(m["identities"]["runtime_environment"], {"OPENBLAS_NUM_THREADS": "1"})
        pool = load_script("run_game_pool")
        self.assertEqual(m["execution"]["scheduler"], pool.scheduler_identity())

    def test_exactly_32_games_of_one_configuration(self) -> None:
        specs = rd.scheduled_games(self.manifest)
        self.assertEqual(len(specs), 32)
        self.assertEqual(len({s.game_id for s in specs}), 32)
        self.assertEqual({(s.scenario_id, s.condition, s.red, s.blue) for s in specs},
                         {("1930331196", "C3", INERT_ID, sx.CANDIDATE_ID)})
        self.assertEqual([s.repetition for s in specs], list(range(1, 33)))
        rev = load_script("run_evaluation")
        self.assertEqual(list(rev.all_games(self.manifest)), [s.game_id for s in specs])

    def test_taxonomy_and_rules_are_registered(self) -> None:
        self.assertEqual(sorted(self.manifest["taxonomy"]), list(rd.CATEGORIES))
        self.assertEqual(self.manifest["conclusion_rule"], rd.CONCLUSION_RULE)
        self.assertEqual(self.manifest["reference"]["class"], "stochastic")

    def test_document_cites_the_manifest(self) -> None:
        doc = (ROOT / "docs" / "RESIDUAL_516_DIAGNOSTIC.md").read_text(encoding="utf-8")
        self.assertIn(rd.digest(self.manifest)[:8], doc)


class RunnerPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def run_game(self, manifest, capture=False):
        rev = load_script("run_evaluation")
        game_id = manifest["games"][0]["game_id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            if capture:
                (Path(tmp) / "work" / "capture").mkdir(parents=True)
                (Path(tmp) / "work" / "capture" / f"{game_id}.windows.pkl").write_bytes(b"")
            args = Namespace(manifest=path, game_id=game_id, work=Path(tmp) / "work", engine_install=Path(tmp),
                             harness_commit="x", harness_dirty=False, purpose="evaluation")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = rev.cmd_game(args)
        return status, err.getvalue()

    def test_another_policy_is_refused(self) -> None:
        shoot = json.loads((ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
        other = copy.deepcopy(self.manifest)
        other["policy_source"] = copy.deepcopy(shoot["groups"]["B"]["policy_source"])
        status, message = self.run_game(other)
        self.assertEqual(status, 2)
        self.assertIn("runs baseline-v2 only", message)

    def test_a_tampered_digest_is_refused(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["policy_source"]["sha256"] = "0" * 64
        status, message = self.run_game(tampered)
        self.assertEqual(status, 2)
        self.assertIn("differs from the registered one", message)

    def test_captures_are_never_overwritten(self) -> None:
        status, message = self.run_game(self.manifest, capture=True)
        self.assertEqual(status, 2)
        self.assertIn("captures are never overwritten", message)


class ObserverTest(unittest.TestCase):
    def test_the_observer_changes_nothing_in_the_game(self) -> None:
        for options in ({}, {"doomed": (7, fake_engine.BLUE_UNIT)}):
            plain = game(**options)
            observed = game(rd.Capture((BASELINE_ID,)), **options)
            self.assertEqual(observed.pop("observer_errors"), [])
            self.assertEqual(plain, observed)

    def test_a_failing_observer_is_recorded_not_raised(self) -> None:
        class Broken:
            def setup(self, *args):
                raise RuntimeError("setup broke")

            def step(self, *args):
                raise RuntimeError("step broke")

        plain = game()
        observed = game(Broken())
        errors = observed.pop("observer_errors")
        self.assertEqual(errors[0], "setup: RuntimeError: setup broke")
        self.assertEqual(len(errors), observed["steps"] + 1)
        self.assertEqual(plain, observed)

    def test_capture_of_a_refused_shot(self) -> None:
        capture = rd.Capture((BASELINE_ID,))
        record = game(capture, doomed=(7, fake_engine.BLUE_UNIT))
        compact = capture.compact()
        self.assertEqual([e["k"] for e in compact["steps"]], list(range(record["steps"])))
        self.assertEqual(len(capture.events), 1)
        self.assertEqual([s["k"] for s in capture.events[0]["window"]], [2, 3, 4, 5, 6])
        self.assertEqual(compact["setup"]["coverage"]["1"]["playing_seats"], [11])
        load = load_script("residual516_diagnostic")
        for seat in record["seats"]:
            self.assertEqual(load.chain([e["traces"][str(seat["seat"])] for e in compact["steps"]]), seat["trace_chain"])
        event = capture.events[0]
        snap = event["window"][-1]
        import pickle
        factions = {s["seat"]: s["faction"] for s in compact["setup"]["seats"]}
        facts = rd.event_facts("g", compact["steps"][event["k"]], compact["steps"], pickle.loads(snap["global"]),
                               pickle.loads(event["after"]), pickle.loads(snap["seats"][1]["observation"]), {1, 11},
                               factions)
        (fact,) = facts
        self.assertEqual((fact["seat"], fact["target"], fact["own_shots"], fact["friendly_other_seat_shots"]),
                         (1, fake_engine.BLUE_UNIT, 1, 0))
        self.assertEqual((fact["target_on_map_at_start"], fact["target_present_after"], fact["legal_at_start"],
                          fact["passed_project_gate"]), (True, False, True, True))
        self.assertEqual(rd.classify(fact), {"category": "H7", "matches": [], "strength": "none",
                                             "reason": "no rule matched"})
        compact_bytes, windows_bytes = capture.files()
        summary = capture.summary(compact_bytes, windows_bytes)
        self.assertEqual((summary["steps"], summary["events"]), (record["steps"], 1))


class JudgeDeltaTest(unittest.TestCase):
    def test_relations(self) -> None:
        a, b, c = {"x": 1}, {"x": 2}, {"x": 3}
        self.assertEqual(rd.judge_delta([a], [])[:2], ([], "empty"))
        self.assertEqual(rd.judge_delta([], [a])[:2], ([a], "first"))
        self.assertEqual(rd.judge_delta([a], [a, b])[:2], ([b], "prefix"))
        self.assertEqual(rd.judge_delta([a, b], [c])[:2], ([c], "replaced"))
        self.assertEqual(rd.judge_delta([a, b], [b, c])[:2], ([c], "replaced"))
        long = [{"x": n} for n in range(rd.FULL_PREFIX_CHECK + 5)]
        new, relation, keys = rd.judge_delta(long, long + [c])
        self.assertEqual((new, relation, len(keys)), ([c], "prefix-sampled", len(long) + 1))
        self.assertEqual(rd.judge_delta(long + [c], long + [c, a], keys)[:2], ([a], "prefix-sampled"))


def facts(**overrides):
    base = {"seat": 11, "faction": 1, "target": 7, "actor": 3, "judge_on_target": [], "target_blood_at_start": 2,
            "opposing_actions_on_target": [], "jm_at_target_hex": [], "linked": [], "target_changes": {},
            "target_passenger_after": False, "target_present_after": False, "target_on_map_after": False,
            "judge_by_actor_on_target": 0}
    base.update(overrides)
    return base


def record(damage, seats=(), earlier=None, faction=1):
    return {"attacker": 5, "attacker_class": [faction, 2, 0], "damage": damage, "same_step_seats": list(seats),
            "earlier_k": earlier}


def linked(present_after=False, positive=1):
    return {"id": 9, "relation": "launcher", "present_before": True, "present_after": present_after,
            "positive_damage": positive}


class ClassificationTest(unittest.TestCase):
    def category(self, **overrides):
        result = rd.classify(facts(**overrides))
        return result["category"], result["strength"]

    def test_each_category(self) -> None:
        self.assertEqual(self.category(judge_on_target=[record(2, seats=[12])]), ("H1", "strong"))
        self.assertEqual(self.category(judge_on_target=[record(1, seats=[12])]), ("H1", "moderate"))
        self.assertEqual(self.category(judge_on_target=[record(2, faction=0)]), ("H2", "strong"))
        self.assertEqual(self.category(opposing_actions_on_target=[{"seat": 1}]), ("H2", "moderate"))
        self.assertEqual(self.category(judge_on_target=[record(2, earlier=40)]), ("H3", "strong"))
        self.assertEqual(self.category(jm_at_target_hex=[{"status": 1}]), ("H3", "moderate"))
        self.assertEqual(self.category(linked=[linked()]), ("H4", "strong"))
        self.assertEqual(self.category(linked=[linked(positive=0)]), ("H4", "moderate"))
        self.assertEqual(self.category(linked=[linked()], judge_on_target=[record(0)]), ("H4", "moderate"))
        self.assertEqual(self.category(target_passenger_after=True, target_present_after=True), ("H5", "strong"))
        self.assertEqual(self.category(target_changes={"lose_control": [0, 1]}), ("H5", "moderate"))
        self.assertEqual(self.category(target_present_after=True, target_on_map_after=True), ("H6", "strong"))
        self.assertEqual(self.category(judge_by_actor_on_target=1), ("H6", "moderate"))
        self.assertEqual(self.category(), ("H7", "none"))

    def test_more_than_one_rule_is_unresolved(self) -> None:
        result = rd.classify(facts(judge_on_target=[record(2, earlier=40)], opposing_actions_on_target=[{"seat": 1}]))
        self.assertEqual((result["category"], result["matches"]), ("H7", ["H2", "H3"]))

    def test_unattributed_damage_lowers_strength(self) -> None:
        result = rd.classify(facts(judge_on_target=[record(2, earlier=40), record(1)]))
        self.assertEqual((result["category"], result["strength"]), ("H3", "moderate"))

    def test_conclusion_rule(self) -> None:
        strong, moderate, h7 = ({"category": "H4", "strength": "strong"}, {"category": "H3", "strength": "moderate"},
                                {"category": "H7", "strength": "none"})
        self.assertEqual(rd.conclusion([strong, strong], True), rd.CONCLUSIONS[0])
        self.assertEqual(rd.conclusion([strong, moderate], True), rd.CONCLUSIONS[1])
        self.assertEqual(rd.conclusion([strong, h7], True), rd.CONCLUSIONS[1])
        self.assertEqual(rd.conclusion([h7], True), rd.CONCLUSIONS[2])
        self.assertEqual(rd.conclusion([], True), rd.CONCLUSIONS[2])
        self.assertEqual(rd.conclusion([strong], False), rd.CONCLUSIONS[2])


class CollisionTest(unittest.TestCase):
    def test_cross_seat_and_same_seat_fire(self) -> None:
        shot = lambda seat, faction, target, i: {"i": i, "seat": seat, "faction": faction, "j": 0,
                                                 "action": {"actor": seat, "type": 2, "obj_id": 100 + i,
                                                            "target_obj_id": target, "weapon_id": 1}}
        steps = [
            {"k": 0, "batch": [shot(11, 1, 7, 0), shot(12, 1, 7, 1)], "feedback": [
                {"message": {"actor": 12, "type": 2, "obj_id": 101, "target_obj_id": 7, "weapon_id": 1},
                 "error": {"code": 516, "message": "CantShootToDiedBop"}}]},
            {"k": 1, "batch": [shot(11, 1, 8, 0), shot(12, 1, 8, 1), shot(11, 1, 9, 2), shot(11, 1, 9, 3)], "feedback": []},
            {"k": 2, "batch": [shot(1, 0, 8, 0), shot(11, 1, 8, 1)], "feedback": []},
        ]
        result = rd.collisions("g", steps, {1: 0, 11: 1, 12: 1})
        self.assertEqual([(c["k"], c["target"], c["produced_516"]) for c in result["cross_seat_collisions"]],
                         [(0, 7, True), (1, 8, False)])
        self.assertEqual((result["cross_seat_steps"], result["same_seat_repeats"], result["shots"]), (2, 1, 8))
        self.assertEqual(rd.opposing_unit_actions(steps, {1}), 1)


if __name__ == "__main__":
    unittest.main()
