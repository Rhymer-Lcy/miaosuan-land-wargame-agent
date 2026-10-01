"""The registered target-ownership prevalence diagnostic. SYNTHETIC data only.

Registration (byte-identical rebuild, frozen identities, the 360-game schedule), the runner's pins (baseline-v2 only,
captures never overwritten), the observer (changes nothing in a game; counts and snapshots), the E0 to E3
classification (ties and weapon keys are not E2, a failed gate precheck is E2 but not E3, S2 is never E2 or E3, the
observation is never modified, determinism, the pre-filter), and the registered next-step decision rule.
"""

from __future__ import annotations

import collections
import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import BASELINE_ID, Memory
from miaosuan_agent.evaluation import ownership_design as od
from miaosuan_agent.evaluation import ownership_prevalence as op
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation.canonical import value_digest
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import fake_engine
from tests.fixtures import synthetic as syn
from tests.test_evaluation_game import FACTORIES, Inputs, spec
from tests.test_shoot_reservation import ENEMY_C, SEAT, situation

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / op.STUDY_ID / "manifest.json"
MEMORY = Memory(deployment_sent=True)
CONFIG = "999 C9"


def load_script(name):
    loader = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def counting_clock():
    ticks = iter(range(10 ** 7))
    return lambda: float(next(ticks))


def game(observer=None, **options):
    return play(lambda: fake_engine.FakeEnv(**options), FACTORIES, spec(), Inputs, PLAYERS, clock=counting_clock(),
                observer=observer)


def decide(raw):
    return ShootReservationPolicy(ds.costs()).decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED, MEMORY)


def classify(raw):
    return op.classify(raw, SEAT, ds.RED, CONFIG, decide(raw).actions)


def shoot(target, level, weapon=ds.GUN):
    return ds.shoot(target, weapon, level)


@unittest.skipUnless(MANIFEST.exists(), "the manifest is registered by its own commit")
class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_rebuilds_byte_identically(self) -> None:
        builder = load_script("build_prevalence_manifest")
        self.assertEqual(json.dumps(builder.build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                         MANIFEST.read_text(encoding="utf-8"))

    def test_frozen_identities(self) -> None:
        m = self.manifest
        self.assertEqual(m["policy_source"]["sha256"], op.BASELINE_V2_SOURCE_SHA256)
        self.assertEqual(m["golden_trace_chain"], sx.CANDIDATE_GOLDEN_TRACE_CHAIN)
        self.assertEqual(m["execution"], {"workers": 32, "runtime": "baseline-v1-runtime-r2",
                                          "scheduler": "miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90"})
        self.assertEqual(m["identities"]["runtime_environment"], {"OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual(m["identities"]["observer_source_sha256"], op.observer_source_sha256())
        self.assertEqual(m["policy_under_test"], sx.CANDIDATE_ID)

    def test_schedule(self) -> None:
        games = self.manifest["games"]
        self.assertEqual(len(games), 360)
        self.assertEqual([g["position"] for g in games], list(range(1, 361)))
        self.assertEqual(len({g["game_id"] for g in games}), 360)
        configs = collections.Counter(g["config"] for g in games)
        self.assertEqual(len(configs), 24)
        self.assertEqual(set(configs.values()), {15})
        for r in range(1, 16):
            self.assertEqual(sorted(g["config"] for g in games if g["round"] == r), sorted(configs))
        self.assertTrue(all(a["config"] != b["config"] for a, b in zip(games, games[1:])))
        self.assertEqual(sorted({g["condition"] for g in games}), ["C1", "C2", "C3"])
        self.assertEqual(len(op.scheduled_games(self.manifest)), 360)

    def test_exposure_and_rules_are_registered(self) -> None:
        m = self.manifest
        self.assertEqual(m["active_seats"], {"C1": [1, 11], "C2": [1], "C3": [11]})
        self.assertEqual(set(m["events"]), {"E0", "E1", "E2", "E3"})
        self.assertEqual(m["decision_rule"]["thresholds"], op.DECISION_RULE["thresholds"])
        self.assertEqual(sorted(m["references"]), sorted(f"{s['scenario_id']}.{c}" for s in m["scenarios"]
                                                         for c in ("C1", "C2", "C3")))

    def test_document_cites_the_manifest(self) -> None:
        doc = (ROOT / "docs" / "OWNERSHIP_PREVALENCE_DIAGNOSTIC.md").read_text(encoding="utf-8")
        self.assertIn(op.digest(self.manifest)[:8], doc)


@unittest.skipUnless(MANIFEST.exists(), "the manifest is registered by its own commit")
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
                (Path(tmp) / "work" / "capture" / f"{game_id}.ownership.json").write_bytes(b"")
            args = Namespace(manifest=path, game_id=game_id, work=Path(tmp) / "work", engine_install=Path(tmp),
                             harness_commit="x", harness_dirty=False, purpose="evaluation")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = rev.cmd_game(args)
        return status, err.getvalue()

    def test_another_policy_is_refused(self) -> None:
        shoot_manifest = json.loads((ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
        other = copy.deepcopy(self.manifest)
        other["policy_source"] = copy.deepcopy(shoot_manifest["groups"]["B"]["policy_source"])
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
            observer = op.Observer(CONFIG, (BASELINE_ID,))
            observed = game(observer, **options)
            self.assertEqual(observed.pop("observer_errors"), [])
            self.assertEqual(plain, observed)
            compact = observer.compact()
            self.assertEqual(sorted(compact["decisions"]), ["1", "11"])
            self.assertEqual(set(compact["decisions"].values()), {plain["steps"]})
            self.assertEqual((compact["observation_mutations"], compact["problems"]), (0, []))
            compact_bytes, snapshot_bytes = observer.files()
            summary = observer.summary(compact_bytes, snapshot_bytes)
            self.assertEqual(summary["observer_source_sha256"], op.observer_source_sha256())

    def test_only_the_registered_policy_is_observed(self) -> None:
        observer = op.Observer(CONFIG, ("some-other-policy",))
        game(observer)
        self.assertEqual(observer.compact()["decisions"], {})

    def test_step_records_components_and_snapshots(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        decision = decide(raw)
        observer = op.Observer(CONFIG, ("p",), sample_every=3)
        observer.setup(None, [{"seat": SEAT, "faction": ds.RED}], {ds.RED: "p"})
        lone = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}})
        for k, observation in enumerate((raw, lone, lone)):
            d = decide(observation)
            observer.step(k, None, None, [{"seat": SEAT, "faction": ds.RED, "policy": "p", "observation": observation,
                                           "memory": MEMORY, "actions": d.actions, "trace": d.trace}])
        compact = observer.compact()
        self.assertEqual(observer.active, [{"seat": SEAT, "faction": ds.RED}])
        self.assertEqual((compact["decisions"], compact["classified"]), ({str(SEAT): 3}, {str(SEAT): 1}))
        self.assertEqual([(c["k"], c["kind"], c["E3"]) for c in compact["components"]], [(0, "S1", True)])
        self.assertEqual([(s["k"], s["reason"]) for s in observer.snapshots], [(0, "S1"), (2, "sample")])
        self.assertEqual(observer.snapshots[0]["actions"], json.loads(json.dumps(list(decision.actions))))


class ClassificationTest(unittest.TestCase):
    def test_s2_is_e0_only(self) -> None:
        [row] = classify(situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3), shoot(ds.ENEMY_B, 1)]},
                                    ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 5)]}}))
        self.assertEqual((row["kind"], row["E0"], row["E1"], row["E2"], row["E3"]), ("S2", True, False, False, False))

    def test_single_shooters_are_not_reported(self) -> None:
        self.assertEqual(classify(situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3), shoot(ds.ENEMY_B, 1)]},
                                             ds.UNIT_B: {2: [shoot(ENEMY_C, 5)]}})), [])

    def test_equal_attack_levels_are_not_e2(self) -> None:
        [row] = classify(situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3)]}}))
        self.assertEqual((row["E1"], row["E2"], row["E3"], row["gate_precheck"]), (True, False, False, None))

    def test_a_weapon_key_alone_is_not_e2(self) -> None:
        [row] = classify(situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3, ds.MISSILE)]},
                                    ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3, ds.GUN)]}}))
        self.assertEqual((row["key"], row["E2"], row["E3"]), ("weapon tie-break", False, False))

    def test_e3(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]},
                         ds.UNIT_C: {2: [shoot(ds.ENEMY_A, 4, ds.MISSILE)]}})
        [row] = classify(raw)
        self.assertEqual((row["E1"], row["E2"], row["E3"], row["gate_precheck"]), (True, True, True, True))
        self.assertEqual((row["levels"], row["gap"], row["top_claimants"], row["top_weapons_differ"]), ([1, 4, 4], 3, 2, True))
        self.assertEqual((row["claimant_actions"], row["owner_shot_emitted"]), (["shoot", "none", "none"], True))
        self.assertEqual(row["private"]["designated"], ds.UNIT_B)
        self.assertEqual((row["owner_class"], row["same_class"], row["same_weapon"]), (f"{ds.VEHICLE}.0", True, True))
        self.assertRegex(row["fingerprint"], r"^[0-9a-f]{16}$")
        self.assertEqual(op.check_consistency([row]), [])

    def test_a_failed_gate_precheck_is_e2_but_not_e3(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        with mock.patch.object(od, "gate_precheck", return_value=False):
            [row] = classify(raw)
        self.assertEqual((row["E2"], row["E3"], row["gate_precheck"]), (True, False, False))

    def test_the_precheck_is_the_designated_claimants(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 2)]},
                         ds.UNIT_C: {2: [shoot(ds.ENEMY_A, 4)]}})
        with mock.patch.object(od, "gate_precheck", return_value=True) as precheck:
            classify(raw)
        self.assertEqual([c.args[3:5] for c in precheck.call_args_list], [(ds.UNIT_C, ds.ENEMY_A)])

    def test_an_observation_mutation_is_counted(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        d = decide(raw)
        observer = op.Observer(CONFIG, ("p",))

        def mutating(observation, *args, **kwargs):
            observation["operators"].append({"obj_id": 1})
            return []
        with mock.patch.object(op, "classify", side_effect=mutating):
            observer.step(0, None, None, [{"seat": SEAT, "faction": ds.RED, "policy": "p", "observation": raw,
                                           "memory": MEMORY, "actions": d.actions, "trace": d.trace}])
        self.assertEqual(observer.mutations, 1)

    def test_classes_differ(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        raw["operators"] = [dict(u, type=ds.INFANTRY) if u["obj_id"] == ds.UNIT_B else u for u in raw["operators"]]
        [row] = classify(raw)
        self.assertEqual((row["owner_class"], row["designated_class"], row["same_class"]),
                         (f"{ds.VEHICLE}.0", f"{ds.INFANTRY}.0", False))
        self.assertEqual((row["top_claimants"], row["top_weapons_differ"]), (1, False))

    def test_the_observation_is_not_modified_and_the_result_is_deterministic(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)], 5: None}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}},
                        cities=[syn.city(505)], hexes={ds.UNIT_A: 505})
        before, frozen = value_digest(raw), copy.deepcopy(raw)
        first = classify(raw)
        self.assertEqual(value_digest(raw), before)
        self.assertEqual(raw, frozen)
        self.assertEqual(classify(raw), first)
        self.assertEqual([dict(a) for a in decide(raw).actions], [dict(a) for a in decide(frozen).actions])

    def test_consistency_problems_are_reported(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        rows = op.classify(raw, SEAT, ds.RED, CONFIG, [])
        self.assertEqual(op.check_consistency(rows), ["the S1 owner's shot at the target was not emitted"])
        later = [{"type": 2, "obj_id": ds.UNIT_A, "target_obj_id": ds.ENEMY_A}, {"type": 2, "obj_id": ds.UNIT_B,
                                                                                 "target_obj_id": ds.ENEMY_A}]
        self.assertEqual(op.check_consistency(op.classify(raw, SEAT, ds.RED, CONFIG, later)), ["a later S1 claimant shot"])

    def test_pre_filter(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {1: None}, ds.UNIT_C: {2: []}})
        self.assertEqual(op.shoot_listed_units(raw), 1)
        raw["valid_actions"] = {str(k): {str(t): v for t, v in actions.items()} for k, actions in raw["valid_actions"].items()}
        raw["valid_actions"][str(ds.UNIT_B)]["2"] = [shoot(ds.ENEMY_A, 0)]
        self.assertEqual(op.shoot_listed_units(raw), 2)


class DecisionRuleTest(unittest.TestCase):
    @staticmethod
    def games(spec_list):
        """spec_list: (scenario, configuration, [(fingerprint, same_class), ...]) per game."""
        return [{"scenario_id": s, "config": c, "e3": [{"fingerprint": f, "same_class": same} for f, same in comps]}
                for s, c, comps in spec_list]

    def test_rule(self) -> None:
        implement, stop, semantic = op.DECISION_RULE["outcomes"]
        diverse = self.games([("s1", "s1.C1", [("a", True)]), ("s1", "s1.C1", [("b", True)]), ("s2", "s2.C2", [("c", True)]),
                              ("s2", "s2.C2", [("c", True)]), ("s3", "s3.C3", [("d", False)]), ("s3", "s3.C3", [])])
        self.assertEqual(op.next_step(diverse, True), implement)
        self.assertIsNone(op.next_step(diverse, False))
        self.assertEqual(op.next_step(diverse[:4], True), stop)
        one_scenario = self.games([("s1", "s1.C1", [(f, True)]) for f in "abcde"])
        self.assertEqual(op.next_step(one_scenario, True), stop)
        two_fingerprints = self.games([("s1", "s1.C1", [("a", True)])] * 3 + [("s2", "s2.C1", [("b", True)])] * 2)
        self.assertEqual(op.next_step(two_fingerprints, True), stop)
        dominated = self.games([("s1", "s1.C1", [("a", True), (f, True)]) for f in "bcd"] +
                               [("s2", "s2.C1", [("a", True)])] * 2)
        self.assertEqual(op.next_step(dominated, True), stop)
        crossed = self.games([("s1", "s1.C1", [(f, False)]) for f in "abc"] + [("s2", "s2.C2", [(f, True)]) for f in "de"])
        self.assertEqual(op.next_step(crossed, True), semantic)
        half = self.games([("s1", "s1.C1", [(f, False)]) for f in "ab"] + [("s2", "s2.C2", [(f, True)]) for f in "cd"]
                          + [("s3", "s3.C3", [("e", True), ("f", False)])])
        self.assertEqual(op.next_step(half, True), implement)
        exactly_half = self.games([("s1", "s1.C1", [(f, False)]) for f in "abc"] + [("s2", "s2.C2", [(f, True)]) for f in "def"])
        self.assertEqual(op.next_step(exactly_half, True), implement)
        at_the_line = self.games([("s1", "s1.C1", [("a", True), (f, True)]) for f in "bcde"] + [("s2", "s2.C2", [("f", True)])])
        self.assertEqual(op.next_step(at_the_line, True), stop)
        below_the_line = at_the_line + self.games([("s2", "s2.C2", [("g", True)])])
        self.assertEqual(op.next_step(below_the_line, True), implement)
        self.assertEqual(op.next_step([], True), stop)

    def test_clopper_pearson(self) -> None:
        self.assertEqual(op.clopper_pearson(4, 8), [0.157, 0.843])
        self.assertEqual(op.clopper_pearson(0, 120), [0.0, 0.0303])
        self.assertEqual(op.clopper_pearson(120, 120), [0.9697, 1.0])


if __name__ == "__main__":
    unittest.main()
