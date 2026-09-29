"""The occupation-reservation candidate differs from baseline-v0 in exactly one registered way.

Equivalence domain: where v0 would not select two occupations of one objective in a step, the
candidate's actions, memory and trace (apart from name, schema and an empty suppression list) equal
v0's. Difference domain: at most one occupation per objective, the first unit in v0 order keeps it,
the others are suppressed with a stable reason and continue down the unchanged hierarchy.
SYNTHETIC data only.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import os
import random
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import BaselinePolicy, Memory, digest
from miaosuan_agent.evaluation import counterfactual as cf
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, POLICY_SOURCES, policy_source_digest
from miaosuan_agent.experiments.occupy_reservation import (CANDIDATE_ID, TRACE_SCHEMA, Coordination,
                                                           OccupyReservationPolicy, ReservationAgent)

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_decision_determinism import golden_observations

ROOT = Path(__file__).resolve().parents[1]
SEAT = syn.RED_SEAT
RESERVED = Coordination.OBJECTIVE_RESERVED.value


def decide(policy_class, raw, origin=Origin.ENGINE, memory=Memory()):
    return policy_class(ds.costs()).decide(Observation.from_raw(raw, origin), SEAT, ds.RED, memory)


def pair(raw, origin=Origin.ENGINE):
    return cf.compare(raw, SEAT, ds.RED, BaselinePolicy(ds.costs()), OccupyReservationPolicy(ds.costs()),
                      Memory(), Memory(), origin)


def occupiers_on(hex_, ids, extra_units=(), extra_valid=None, cities=None):
    units = [syn.unit(obj_id, ds.RED, hex_) for obj_id in ids] + list(extra_units)
    valid = {obj_id: {1: None, 5: None} for obj_id in ids}
    valid.update(extra_valid or {})
    return ds.play_observation(units, valid, cities=cities if cities is not None else [syn.city(hex_)])


def action_list(decision):
    return [(a["type"], a.get("obj_id")) for a in decision.actions]


class IdentityTest(unittest.TestCase):
    def test_candidate_lives_outside_the_frozen_sources(self) -> None:
        v0_digest, v0_files = policy_source_digest()
        self.assertEqual(v0_digest, "8e209640534e0af597fdcf4c7911bdcce417c6f2b883671e5bbfc0d243e43a13")
        self.assertFalse([f for f in v0_files if f.startswith("experiments/")])
        candidate_digest, candidate_files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
        self.assertEqual(set(candidate_files) - set(v0_files),
                         {"experiments/__init__.py", "experiments/occupy_reservation.py"})
        self.assertNotEqual(candidate_digest, v0_digest)
        self.assertEqual(OCCUPY_RESERVATION_SOURCES[:len(POLICY_SOURCES)], POLICY_SOURCES)

    def test_names(self) -> None:
        self.assertEqual(CANDIDATE_ID, "baseline-v1-candidate-occupy-reservation")
        self.assertEqual(OccupyReservationPolicy.identity, CANDIDATE_ID)
        self.assertEqual(RESERVED, "same-step-objective-reserved")


class EquivalenceTest(unittest.TestCase):
    def test_rich_situation_is_identical(self) -> None:
        comparison, first, second = pair(ds.rich_observation())
        self.assertTrue(comparison.identical, comparison)
        self.assertEqual(second.trace.policy, CANDIDATE_ID)
        self.assertEqual(second.trace.to_dict()["schema"], TRACE_SCHEMA)

    def test_golden_v0_sequence_is_identical(self) -> None:
        v0, candidate = BaselinePolicy(ds.costs()), OccupyReservationPolicy(ds.costs())
        m0 = m1 = Memory()
        for raw in golden_observations():
            comparison, first, second = cf.compare(raw, SEAT, ds.RED, v0, candidate, m0, m1)
            self.assertTrue(comparison.identical, comparison)
            m0, m1 = first.memory, second.memory
        self.assertTrue(m0.deployment_sent and m1.deployment_sent)

    def test_randomised_situations_match_the_oracle(self) -> None:
        rng = random.Random(20260930)
        identical = differing = suppressions = 0
        for index in range(400):
            raw = random_situation(rng)
            with self.subTest(case=index):
                comparison, _, _ = pair(raw)
                self.assertTrue(comparison.explained, comparison)
                identical += comparison.identical
                differing += not comparison.identical
                suppressions += len(comparison.suppressed)
                self.assertTrue(set(comparison.changed_types) <= {5}, comparison)
        self.assertGreater(identical, 100)
        self.assertGreater(differing, 50)
        self.assertGreaterEqual(suppressions, differing)


def random_situation(rng: random.Random):
    """A synthetic play-stage observation with co-located units, objectives of mixed ownership,
    shoot options and moving units: both domains occur."""
    hexes = [505, 202, 707, 303, 808]
    cities = [syn.city(h, flag=rng.choice([-1, -1, 0, 1])) for h in rng.sample(hexes[:3], rng.randint(1, 3))]
    units, valid = [], {}
    for n in range(rng.randint(1, 5)):
        obj_id = 900101 + n
        moving = rng.random() < 0.15
        unit_type = rng.choice([ds.VEHICLE, ds.VEHICLE, ds.INFANTRY])
        units.append(syn.unit(obj_id, ds.RED, rng.choice(hexes), unit_type=unit_type,
                              move_path=(606,) if moving else ()))
        actions = {}
        if not moving and rng.random() < 0.8:
            actions[1] = None
        if rng.random() < 0.6:
            actions[5] = None
        if rng.random() < 0.3:
            actions[2] = [ds.shoot(ds.ENEMY_A, ds.GUN, rng.randint(0, 4))]
        valid[obj_id] = actions
    units.append(syn.unit(ds.ENEMY_A, ds.BLUE, 909))
    return ds.play_observation(units, valid, cities=cities)


class DifferenceTest(unittest.TestCase):
    def test_two_units_one_objective(self) -> None:
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B])
        comparison, first, second = pair(raw)
        self.assertTrue(comparison.explained and not comparison.identical)
        self.assertEqual(action_list(first), [(5, ds.UNIT_A), (5, ds.UNIT_B)])
        self.assertEqual(action_list(second), [(5, ds.UNIT_A)])
        self.assertEqual(second.trace.suppressed, ((ds.UNIT_B, 505, ds.UNIT_A, RESERVED),))
        record = second.trace.units[1]
        self.assertEqual((record.rule, record.action_type, record.validation), ("none", None, "not applicable"))
        self.assertEqual(record.no_op_reason,
                         f"occupation suppressed: {RESERVED}; move: standing on an objective outside own control")
        self.assertEqual(record.candidates, first.trace.units[1].candidates)

    def test_three_units_keep_the_lowest_id(self) -> None:
        raw = occupiers_on(505, [ds.UNIT_C, ds.UNIT_A, ds.UNIT_B])
        comparison, first, second = pair(raw)
        self.assertTrue(comparison.explained)
        self.assertEqual(len(first.actions), 3)
        self.assertEqual(action_list(second), [(5, ds.UNIT_A)])
        self.assertEqual([s[0] for s in second.trace.suppressed], [ds.UNIT_B, ds.UNIT_C])
        self.assertEqual({s[2] for s in second.trace.suppressed}, {ds.UNIT_A})

    def test_several_objectives(self) -> None:
        units = [syn.unit(ds.UNIT_A, ds.RED, 505), syn.unit(ds.UNIT_B, ds.RED, 202), syn.unit(ds.UNIT_C, ds.RED, 505),
                 syn.unit(ds.UNIT_D, ds.RED, 202), syn.unit(900105, ds.RED, 707)]
        valid = {u["obj_id"]: {1: None, 5: None} for u in units}
        raw = ds.play_observation(units, valid, cities=[syn.city(505), syn.city(202), syn.city(707)])
        comparison, first, second = pair(raw)
        self.assertTrue(comparison.explained)
        self.assertEqual(action_list(first), [(5, ds.UNIT_A), (5, ds.UNIT_B), (5, ds.UNIT_C), (5, ds.UNIT_D),
                                              (5, 900105)])
        self.assertEqual(action_list(second), [(5, ds.UNIT_A), (5, ds.UNIT_B), (5, 900105)])
        self.assertEqual(second.trace.suppressed, ((ds.UNIT_C, 505, ds.UNIT_A, RESERVED),
                                                   (ds.UNIT_D, 202, ds.UNIT_B, RESERVED)))

    def test_engagement_keeps_priority_and_does_not_reserve(self) -> None:
        shooter_valid = {ds.UNIT_A: {1: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None}}
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B, ds.UNIT_C], extra_units=[syn.unit(ds.ENEMY_A, ds.BLUE, 506)],
                           extra_valid=shooter_valid)
        comparison, first, second = pair(raw)
        self.assertTrue(comparison.explained)
        self.assertEqual(action_list(first), [(2, ds.UNIT_A), (5, ds.UNIT_B), (5, ds.UNIT_C)])
        self.assertEqual(action_list(second), [(2, ds.UNIT_A), (5, ds.UNIT_B)])
        self.assertEqual(second.trace.suppressed, ((ds.UNIT_C, 505, ds.UNIT_B, RESERVED),))
        self.assertEqual(first.actions[0], second.actions[0])

    def test_shooting_is_never_coordinated(self) -> None:
        units = [syn.unit(ds.UNIT_A, ds.RED, 505), syn.unit(ds.UNIT_B, ds.RED, 505), syn.unit(ds.ENEMY_A, ds.BLUE, 506)]
        option = [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]
        raw = ds.play_observation(units, {ds.UNIT_A: {2: option, 5: None}, ds.UNIT_B: {2: option, 5: None}})
        comparison, first, second = pair(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(action_list(second), [(2, ds.UNIT_A), (2, ds.UNIT_B)])

    def test_suppressed_unit_continues_down_the_unchanged_hierarchy(self) -> None:
        # occupation offered on an objective the side already holds, so the baseline allows moving on
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B], cities=[syn.city(505, flag=ds.RED), syn.city(909)])
        comparison, first, second = pair(raw)
        self.assertTrue(comparison.explained, comparison)
        self.assertEqual(action_list(first), [(5, ds.UNIT_A), (5, ds.UNIT_B)])
        self.assertEqual(action_list(second), [(5, ds.UNIT_A), (1, ds.UNIT_B)])
        self.assertEqual(second.trace.units[1].rule, "move")
        self.assertEqual(dict(second.trace.units[1].detail)["suppressed"], RESERVED)

    def test_reservation_does_not_outlive_the_step(self) -> None:
        policy = OccupyReservationPolicy(ds.costs())
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B])
        before = set(vars(policy))
        first = policy.decide(Observation.from_raw(raw), SEAT, ds.RED, Memory())
        again = policy.decide(Observation.from_raw(raw), SEAT, ds.RED, first.memory)
        self.assertEqual(set(vars(policy)), before)
        self.assertEqual(first.actions, again.actions)
        self.assertEqual(digest(first.trace), digest(again.trace))
        single = policy.decide(Observation.from_raw(occupiers_on(505, [ds.UNIT_B])), SEAT, ds.RED, first.memory)
        self.assertEqual(action_list(single), [(5, ds.UNIT_B)])

    def test_engine_code_1804_condition(self) -> None:
        """The recorded refusal condition: two own units, one start-of-step observation, one unheld
        objective, occupation listed for both. v0 orders both (the second was refused by the engine
        with 1804); the candidate orders exactly one."""
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B], cities=[syn.city(505, flag=-1)])
        self.assertEqual(len([a for a in decide(BaselinePolicy, raw).actions if a["type"] == 5]), 2)
        self.assertEqual(len([a for a in decide(OccupyReservationPolicy, raw).actions if a["type"] == 5]), 1)


class DeterminismTest(unittest.TestCase):
    def duplicate_situation(self):
        units = [syn.unit(obj_id, ds.RED, 505) for obj_id in (ds.UNIT_A, ds.UNIT_B, ds.UNIT_C)]
        units += [syn.unit(ds.UNIT_D, ds.RED, 202), syn.unit(ds.ENEMY_A, ds.BLUE, 506)]
        valid = {ds.UNIT_A: {1: None, 5: None}, ds.UNIT_B: {1: None, 5: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 2)]},
                 ds.UNIT_C: {1: None, 5: None}, ds.UNIT_D: {1: None, 5: None}}
        return ds.play_observation(units, valid, cities=[syn.city(505), syn.city(202), syn.city(909)], roadblocks=(606,))

    def test_shuffled_inputs(self) -> None:
        reference = decide(OccupyReservationPolicy, self.duplicate_situation())
        self.assertEqual(len(reference.trace.suppressed), 1)
        for key in range(12):
            with self.subTest(permutation=key):
                shuffled = decide(OccupyReservationPolicy, ds.reordered(self.duplicate_situation(), key))
                self.assertEqual(shuffled.actions, reference.actions)
                self.assertEqual(digest(shuffled.trace), digest(reference.trace))

    def test_json_round_trip(self) -> None:
        engine = decide(OccupyReservationPolicy, self.duplicate_situation())
        via_json = OccupyReservationPolicy(ds.costs()).decide(
            Observation.from_raw(syn.json_round_trip(self.duplicate_situation()), Origin.JSON), SEAT, ds.RED, Memory())
        self.assertEqual(engine.actions, via_json.actions)
        self.assertEqual(digest(engine.trace), digest(via_json.trace))
        comparison, _, _ = pair(syn.json_round_trip(self.duplicate_situation()), Origin.JSON)
        self.assertTrue(comparison.explained)

    def test_hash_seeds(self) -> None:
        program = (f"import sys; sys.path[:0] = [{str(ROOT / 'src')!r}, {str(ROOT)!r}]\n"
                   "from tests.test_occupy_reservation import DeterminismTest, decide\n"
                   "from miaosuan_agent.experiments.occupy_reservation import OccupyReservationPolicy\n"
                   "from miaosuan_agent.decision import digest\n"
                   "print(digest(decide(OccupyReservationPolicy, DeterminismTest().duplicate_situation()).trace))\n")
        digests = set()
        for seed in ("0", "1", "4242", "random"):
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            env["PYTHONHASHSEED"] = seed
            result = subprocess.run([sys.executable, "-c", program], env=env, capture_output=True, text=True,
                                    timeout=120, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            digests.add(result.stdout.strip())
        self.assertEqual(digests, {digest(decide(OccupyReservationPolicy, self.duplicate_situation()).trace)})

    def test_input_is_not_modified(self) -> None:
        raw = self.duplicate_situation()
        before = copy.deepcopy(raw)
        pair(raw)
        self.assertEqual(raw, before)

    def test_no_clock_or_random_source(self) -> None:
        forbidden = {"random", "time", "uuid", "secrets", "os", "datetime", "glob", "threading", "numpy"}
        for name in ("__init__.py", "occupy_reservation.py"):
            tree = ast.parse((ROOT / "src" / "miaosuan_agent" / "experiments" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split(".")[0] for a in node.names} & forbidden)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertNotIn(node.module.split(".")[0], forbidden)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"id", "hash", "globals", "locals", "vars", "open"})
        patches = [mock.patch(t, side_effect=AssertionError("clock or random source used"))
                   for t in ("time.time", "time.perf_counter", "time.monotonic", "random.random", "random.choice",
                             "random.shuffle", "os.urandom")]
        for patch in patches:
            patch.start()
        try:
            decide(OccupyReservationPolicy, self.duplicate_situation())
        finally:
            for patch in patches:
                patch.stop()


def setup_info():
    return {"seat": SEAT, "faction": ds.RED, "cost_data": syn.cost_data()}


class AgentTest(unittest.TestCase):
    def test_lifecycle_and_replay(self) -> None:
        agent = ReservationAgent(strict=True)
        self.assertEqual(agent.policy_id, CANDIDATE_ID)
        with self.assertRaises(RuntimeError):
            agent.step(occupiers_on(505, [ds.UNIT_A]))
        agent.setup(setup_info())
        deploy = ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102)], {ds.UNIT_A: {1: None}}, stage=1,
                                     cur_step=0, ended=False)
        self.assertEqual(agent.step(deploy), [{"actor": SEAT, "type": 333}])
        memory = agent.memory
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B])
        actions = agent.step(raw)
        self.assertEqual([(a["type"], a["obj_id"]) for a in actions], [(5, ds.UNIT_A)])
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        self.assertEqual(agent.last_trace.suppressed, ((ds.UNIT_B, 505, ds.UNIT_A, RESERVED),))
        agent.reset()
        self.assertIsNone(agent.policy)

    def test_malformed_observation_fails_closed(self) -> None:
        agent = ReservationAgent()
        agent.setup(setup_info())
        self.assertEqual(agent.step({"operators": []}), [])
        self.assertTrue(agent.last_trace.error.startswith("ContractError"))
        self.assertIsNotNone(agent.replay({"operators": []}, agent.memory).error)


class CounterfactualCheckTest(unittest.TestCase):
    """The comparison must be able to fail."""

    def test_v0_posing_as_candidate_is_caught(self) -> None:
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B])
        comparison, _, _ = cf.compare(raw, SEAT, ds.RED, BaselinePolicy(ds.costs()), BaselinePolicy(ds.costs()),
                                      Memory(), Memory())
        self.assertFalse(comparison.explained)

    def test_over_suppression_is_caught(self) -> None:
        class OverSuppressing(OccupyReservationPolicy):
            def _play(self, context, memory):
                decision = super()._play(context, memory)
                return type(decision)(decision.actions[:0], decision.trace, decision.memory)

        comparison, _, _ = cf.compare(occupiers_on(505, [ds.UNIT_A, ds.UNIT_B]), SEAT, ds.RED,
                                      BaselinePolicy(ds.costs()), OverSuppressing(ds.costs()), Memory(), Memory())
        self.assertFalse(comparison.explained)
        comparison, _, _ = cf.compare(ds.rich_observation(), SEAT, ds.RED, BaselinePolicy(ds.costs()),
                                      OverSuppressing(ds.costs()), Memory(), Memory())
        self.assertFalse(comparison.explained)

    def test_trace_only_change_is_caught(self) -> None:
        class NoisyTrace(OccupyReservationPolicy):
            def decide(self, observation, seat, faction, memory):
                decision = super().decide(observation, seat, faction, memory)
                return type(decision)(decision.actions, replace(decision.trace, diagnostics=("extra",)), decision.memory)

        comparison, first, second = cf.compare(ds.rich_observation(), SEAT, ds.RED, BaselinePolicy(ds.costs()),
                                               NoisyTrace(ds.costs()), Memory(), Memory())
        self.assertEqual(first.actions, second.actions)
        self.assertEqual((comparison.explained, comparison.problem),
                         (False, "trace differs without a duplicate occupier"))

    def test_missing_fall_through_is_caught_by_the_oracle(self) -> None:
        class NoFallThrough(OccupyReservationPolicy):
            def decide(self, observation, seat, faction, memory):
                decision = super().decide(observation, seat, faction, memory)
                suppressed = {entry[0] for entry in decision.trace.suppressed}
                kept = tuple(a for a in decision.actions if a.get("obj_id") not in suppressed)
                return type(decision)(kept, decision.trace, decision.memory)

        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B], cities=[syn.city(505, flag=ds.RED), syn.city(909)])
        comparison, _, _ = cf.compare(raw, SEAT, ds.RED, BaselinePolicy(ds.costs()), NoFallThrough(ds.costs()),
                                      Memory(), Memory())
        self.assertEqual((comparison.explained, comparison.problem), (False, "actions differ from the oracle"))

    def test_without_occupation_handles_both_key_forms(self) -> None:
        raw = occupiers_on(505, [ds.UNIT_A, ds.UNIT_B])
        self.assertNotIn(5, cf.without_occupation(raw, [ds.UNIT_B])["valid_actions"][ds.UNIT_B])
        self.assertIn(5, cf.without_occupation(raw, [ds.UNIT_B])["valid_actions"][ds.UNIT_A])
        as_json = cf.without_occupation(syn.json_round_trip(raw), [ds.UNIT_B])
        self.assertNotIn("5", as_json["valid_actions"][str(ds.UNIT_B)])


def golden_candidate_observations():
    city = [syn.city(505), syn.city(202)]
    return golden_observations()[:2] + [
        occupiers_on(505, [ds.UNIT_A, ds.UNIT_B, ds.UNIT_C], cities=city),
        occupiers_on(505, [ds.UNIT_A, ds.UNIT_B], extra_units=[syn.unit(ds.ENEMY_A, ds.BLUE, 506)],
                     extra_valid={ds.UNIT_A: {1: None, 2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 2)], 5: None}}, cities=city),
        occupiers_on(505, [ds.UNIT_A, ds.UNIT_B], cities=[syn.city(505, flag=ds.RED), syn.city(909)]),
    ]


GOLDEN_ACTIONS = [
    [(333, None)],
    [(1, ds.UNIT_A)],
    [(5, ds.UNIT_A)],
    [(2, ds.UNIT_A), (5, ds.UNIT_B)],
    [(5, ds.UNIT_A), (1, ds.UNIT_B)],
]
#: Chained digest of the golden candidate traces; a change means the candidate's behaviour changed.
GOLDEN_TRACE_CHAIN = "11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66"


class GoldenCandidateTest(unittest.TestCase):
    def test_golden_sequence(self) -> None:
        agent = ReservationAgent(strict=True)
        agent.setup(setup_info())
        chain = hashlib.sha256()
        for index, (raw, expected) in enumerate(zip(golden_candidate_observations(), GOLDEN_ACTIONS)):
            with self.subTest(step=index):
                self.assertEqual([(a["type"], a.get("obj_id")) for a in agent.step(raw)], expected)
            chain.update(digest(agent.last_trace).encode("ascii"))
        self.assertEqual(chain.hexdigest(), GOLDEN_TRACE_CHAIN)


if __name__ == "__main__":
    unittest.main()
