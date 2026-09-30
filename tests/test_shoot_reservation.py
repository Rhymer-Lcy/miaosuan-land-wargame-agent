"""The shoot-target-reservation candidate against baseline-v1 on runtime r1. SYNTHETIC data only.

Mechanism: each registered situation (shared target, several shooters, alternate targets, weapons and
attack levels, fallback to occupation, movement or nothing, the gate, seats and steps). Invariants on a
deterministic generated corpus (seed below): no duplicate target in the candidate's shots; without a
duplicate in baseline-v1's shots the actions are equal; every difference is explained by the oracle of
``evaluation/shoot_counterfactual.py``; move paths are the router's. Determinism, identity, the golden
chain and the agent contract.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import random
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.boundary import ContractError, Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.decision import gate as gate_module
from miaosuan_agent.decision.routing import ROADBLOCKED_MODES, move_mode
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation import shoot_counterfactual as sc
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest
from miaosuan_agent.experiments.routing_bounded import BoundedRouter, BoundedRoutingAgent, BoundedRoutingPolicy
from miaosuan_agent.experiments.shoot_reservation import (CANDIDATE_ID, TRACE_SCHEMA, Effect, ShootCoordination,
                                                          ShootReservationAgent, ShootReservationPolicy)

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_occupy_reservation import GOLDEN_ACTIONS, golden_candidate_observations, setup_info

ROOT = Path(__file__).resolve().parents[1]
SEAT = syn.RED_SEAT
ENEMY_C = 900203
ENEMIES = (ds.ENEMY_A, ds.ENEMY_B, ENEMY_C)
RESERVED = ShootCoordination.TARGET_RESERVED.value
V1_DIGEST = "1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9"
RUNTIME_R1_DIGEST = "f9e50a538f1f530e9e485f75ce3d457435cfb9bcc2eb039ecdfa9374d54398ad"
GENERATED_SEED = 20261001
GENERATED_STATES = 1500
#: Chained digest of the candidate's traces over the golden sequence (``golden_sequence``).
GOLDEN_TRACE_CHAIN = "0d16c814c03909ed89303a776b276b4cc441cd047450a063329009458654910f"


def decide(policy_class, raw, origin=Origin.ENGINE, memory=Memory(deployment_sent=True), seat=SEAT, faction=ds.RED):
    return policy_class(ds.costs()).decide(Observation.from_raw(raw, origin), seat, faction, memory)


def compare(raw, origin=Origin.ENGINE, memory=Memory(deployment_sent=True)):
    costs = ds.costs()
    return sc.compare(raw, SEAT, ds.RED, BoundedRoutingPolicy(costs), ShootReservationPolicy(costs),
                      lambda: BoundedRoutingPolicy(costs), memory, memory, origin)


def summary(decision):
    return [(int(a["type"]), a.get("obj_id"), a.get("target_obj_id"), a.get("weapon_id")) for a in decision.actions]


def situation(valid, *, units=None, cities=None, hexes=None):
    """Red units A, B, C, D at 102, 103, 104, 105 (unless ``hexes`` says otherwise); three visible enemies."""
    hexes = hexes or {}
    ids = sorted(valid) if units is None else units
    red = [syn.unit(obj_id, ds.RED, hexes.get(obj_id, 102 + index), unit_type=ds.VEHICLE)
           for index, obj_id in enumerate(ids)]
    blue = [syn.unit(enemy, ds.BLUE, 304 + index) for index, enemy in enumerate(ENEMIES)]
    return ds.play_observation(red + blue, valid, cities=cities if cities is not None else [syn.city(909)])


def reserved_record(decision):
    return decision.trace.to_dict()["shoot_reserved"]


class MechanismTest(unittest.TestCase):
    def assertExplained(self, raw):
        comparison, first, second = compare(raw)
        self.assertTrue(comparison.explained, comparison.problem)
        self.assertEqual(comparison.candidate_duplicate_shots, 0)
        return comparison, first, second

    def test_two_shooters_one_target(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (2, ds.UNIT_B, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(reserved_record(second), [{"obj_id": ds.UNIT_B, "effect": "fallback-none", "reason": RESERVED,
                                                    "excluded": [{"target_obj_id": ds.ENEMY_A, "weapon_id": ds.GUN,
                                                                  "attack_level": 3, "reserved_by": ds.UNIT_A}]}])
        unit = second.trace.units[1]
        self.assertEqual((unit.rule, unit.action_type, unit.validation), ("none", None, "not applicable"))
        self.assertEqual(unit.no_op_reason, f"shoot targets reserved: {RESERVED}; move: movement not listed")
        self.assertEqual(unit.candidates, first.trace.units[1].candidates)
        self.assertEqual(comparison.classes["D"], 1)
        self.assertEqual((comparison.baseline_duplicate_shots, comparison.displaced_units), (1, 1))

    def test_three_shooters_keep_the_lowest_id(self) -> None:
        valid = {u: {2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 2)]} for u in (ds.UNIT_C, ds.UNIT_A, ds.UNIT_B)}
        raw = situation(valid, units=[ds.UNIT_C, ds.UNIT_A, ds.UNIT_B])
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(len(first.actions), 3)
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.MISSILE)])
        self.assertEqual([(e["obj_id"], e["excluded"][0]["reserved_by"]) for e in reserved_record(second)],
                         [(ds.UNIT_B, ds.UNIT_A), (ds.UNIT_C, ds.UNIT_A)])
        self.assertEqual(comparison.classes["D"], 2)

    def test_two_shooters_two_targets_is_baseline(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}})
        comparison, first, second = self.assertExplained(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(summary(first), summary(second))
        self.assertEqual(reserved_record(second), [])
        self.assertEqual(sc._normalized_candidate(second.trace.to_dict(), {}), sc._normalized_oracle(first.trace.to_dict()))

    def test_next_best_target_is_selected(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 2), ds.shoot(ds.ENEMY_A, ds.GUN, 3),
                                         ds.shoot(ENEMY_C, ds.GUN, 1)]}})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first)[1], (2, ds.UNIT_B, ds.ENEMY_A, ds.GUN))
        self.assertEqual(summary(second)[1], (2, ds.UNIT_B, ds.ENEMY_B, ds.GUN))
        detail = dict(second.trace.units[1].detail)
        self.assertEqual(detail, {"attack_level": 2, "shoot_target_reserved": ds.ENEMY_A,
                                  "shoot_reservation": Effect.ALTERNATE_TARGET.value})
        self.assertEqual(second.trace.units[1].rank, (-2, ds.ENEMY_B, ds.GUN))
        self.assertEqual(comparison.classes["A"], 1)

    def test_same_target_with_several_weapons(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 3), ds.shoot(ds.ENEMY_A, ds.GUN, 3),
                                         ds.shoot(ds.ENEMY_B, ds.GUN, 1)]}})
        comparison, _, second = self.assertExplained(raw)
        excluded = reserved_record(second)[0]["excluded"]
        self.assertEqual(sorted((e["target_obj_id"], e["weapon_id"]) for e in excluded),
                         [(ds.ENEMY_A, ds.GUN), (ds.ENEMY_A, ds.MISSILE)])
        self.assertEqual(summary(second)[1], (2, ds.UNIT_B, ds.ENEMY_B, ds.GUN))
        self.assertEqual(comparison.excluded_options, 2)

    def test_same_target_with_different_attack_levels(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 1)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 4), ds.shoot(ds.ENEMY_A, ds.GUN, 2),
                                         ds.shoot(ds.ENEMY_B, ds.GUN, 1)]}})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (2, ds.UNIT_B, ds.ENEMY_A, ds.MISSILE)])
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (2, ds.UNIT_B, ds.ENEMY_B, ds.GUN)])
        self.assertEqual(comparison.classes["A"], 1)

    def test_fallback_to_occupation(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None, 1: None}},
                        cities=[syn.city(505)], hexes={ds.UNIT_B: 505})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first)[1][:2], (2, ds.UNIT_B))
        self.assertEqual(summary(second)[1][:2], (5, ds.UNIT_B))
        self.assertEqual(reserved_record(second)[0]["effect"], Effect.OCCUPY.value)
        self.assertEqual(comparison.classes["B"], 1)

    def test_fallback_to_movement_keeps_the_route(self) -> None:
        valid = {ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 1: None}}
        raw = situation(valid, cities=[syn.city(505)])
        comparison, _, second = self.assertExplained(raw)
        self.assertEqual(summary(second)[1][:2], (1, ds.UNIT_B))
        without_shot = situation({ds.UNIT_A: valid[ds.UNIT_A], ds.UNIT_B: {1: None}}, cities=[syn.city(505)])
        reference = decide(BoundedRoutingPolicy, without_shot)
        self.assertEqual(second.actions[1], reference.actions[1])
        self.assertEqual(comparison.classes["C"], 1)

    def test_fallback_after_suppressed_occupation(self) -> None:
        raw = situation({ds.UNIT_A: {5: None}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None, 1: None}},
                        cities=[syn.city(505)], hexes={ds.UNIT_A: 505, ds.UNIT_C: 505})
        comparison, _, second = self.assertExplained(raw)
        unit = second.trace.units[2]
        self.assertEqual(unit.no_op_reason, f"shoot targets reserved: {RESERVED}; occupation suppressed: "
                                            "same-step-objective-reserved; move: standing on an objective outside own control")
        self.assertEqual(comparison.classes["D"], 1)

    def test_occupation_induced_by_a_fallback(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None},
                         ds.UNIT_C: {5: None}}, cities=[syn.city(505)], hexes={ds.UNIT_B: 505, ds.UNIT_C: 505})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (2, ds.UNIT_B, ds.ENEMY_A, ds.GUN),
                                          (5, ds.UNIT_C, None, None)])
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (5, ds.UNIT_B, None, None)])
        self.assertEqual((comparison.classes["B"], comparison.classes["I"]), (1, 1))

    def test_unchanged_selection_records_the_exclusion(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 4), ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first), summary(second))
        self.assertTrue(comparison.identical)
        self.assertEqual(reserved_record(second)[0]["effect"], Effect.UNCHANGED.value)
        self.assertNotIn("shoot_reservation", dict(second.trace.units[1].detail))

    def test_malformed_options_are_skipped_not_reserved(self) -> None:
        raw = situation({ds.UNIT_A: {2: [{"target_obj_id": "x", "weapon_id": ds.GUN, "attack_level": 3},
                                         ds.shoot(ds.ENEMY_A, ds.GUN, 0)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3), {"weapon_id": ds.GUN}]}})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(second), [(2, ds.UNIT_B, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(first.trace.diagnostics, second.trace.diagnostics)
        self.assertEqual(len(second.trace.diagnostics), 3)
        self.assertTrue(comparison.identical)


class GateTest(unittest.TestCase):
    def test_a_rejected_shot_reserves_nothing(self) -> None:
        real = gate_module.check

        def rejecting(actions, context, router):
            kept = [a for a in actions if not (a.get("obj_id") == ds.UNIT_A and a.get("type") == 2)]
            result = real(kept, context, router)
            extra = tuple(gate_module.Rejection(2, ds.UNIT_A, "synthetic rejection") for a in actions if a not in kept)
            return gate_module.GateResult(result.accepted, result.rejected + extra)

        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        with mock.patch.object(gate_module, "check", rejecting):
            second = decide(ShootReservationPolicy, raw)
        self.assertEqual(summary(second), [(2, ds.UNIT_B, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(reserved_record(second), [])
        self.assertEqual(second.trace.units[0].validation, "rejected: synthetic rejection")

    def test_the_verdict_is_the_units_own(self) -> None:
        real = gate_module.check

        def rejecting(actions, context, router):
            kept = [a for a in actions if not (a.get("obj_id") == ds.UNIT_B and a.get("type") == 2)]
            result = real(kept, context, router)
            extra = tuple(gate_module.Rejection(2, ds.UNIT_B, "synthetic rejection") for a in actions if a not in kept)
            return gate_module.GateResult(result.accepted, result.rejected + extra)

        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}})
        with mock.patch.object(gate_module, "check", rejecting):
            second = decide(ShootReservationPolicy, raw)
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (2, ds.UNIT_C, ds.ENEMY_B, ds.GUN)])
        self.assertEqual(reserved_record(second), [])


def rich_situation(rng: random.Random):
    """Red units co-located on objectives with occupation, movement and zero to four shoot options over three
    enemies (a few malformed or below the minimum attack level); some units are executing a move."""
    hexes = [505, 202, 707, 303, 808]
    cities = [syn.city(h, flag=rng.choice([-1, -1, 0, 1])) for h in rng.sample(hexes[:3], rng.randint(1, 3))]
    units, valid = [], {}
    for n in range(rng.randint(2, 7)):
        obj_id = 900101 + n
        moving = rng.random() < 0.15
        units.append(syn.unit(obj_id, ds.RED, rng.choice(hexes), unit_type=rng.choice([ds.VEHICLE, ds.VEHICLE, ds.INFANTRY]),
                              move_path=(606,) if moving else ()))
        actions = {}
        if not moving and rng.random() < 0.7:
            actions[1] = None
        if rng.random() < 0.5:
            actions[5] = None
        if rng.random() < 0.8:
            options = []
            for _ in range(rng.randint(1, 4)):
                if rng.random() < 0.05:
                    options.append({"target_obj_id": "bad", "weapon_id": ds.GUN, "attack_level": 3})
                else:
                    options.append(ds.shoot(rng.choice(ENEMIES), rng.choice([ds.GUN, ds.MISSILE]), rng.randint(0, 4)))
            actions[2] = options
        valid[obj_id] = actions
    for index, enemy in enumerate(ENEMIES):
        units.append(syn.unit(enemy, ds.BLUE, 900 + index))
    return ds.play_observation(units, valid, cities=cities)


class GeneratedCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rng = random.Random(GENERATED_SEED)
        cls.cases = []
        for _ in range(GENERATED_STATES):
            raw = rich_situation(rng)
            cls.cases.append((raw,) + compare(raw))

    def test_every_difference_is_explained(self) -> None:
        classes = {c: 0 for c in sc.CLASSES}
        for raw, comparison, _, _ in self.cases:
            self.assertTrue(comparison.explained, comparison.problem)
            self.assertEqual(comparison.candidate_duplicate_shots, 0)
            self.assertFalse(comparison.first_shot_changed)
            for label, n in comparison.classes.items():
                classes[label] += n
            self.assertEqual(sum(comparison.classes[c] for c in "ABCD"), comparison.displaced_units)
        self.assertEqual(classes["E"], 0)
        for label in "ABCDI":
            self.assertGreater(classes[label], 5, label)

    def test_without_a_baseline_duplicate_the_actions_are_equal(self) -> None:
        without = 0
        for raw, comparison, first, second in self.cases:
            if comparison.baseline_duplicate_shots == 0:
                without += 1
                self.assertEqual(first.actions, second.actions)
                self.assertEqual(sc._normalized_candidate(second.trace.to_dict(), {}),
                                 sc._normalized_oracle(first.trace.to_dict()))
        self.assertGreater(without, 300)

    def test_candidate_never_shoots_a_reserved_target_and_keeps_order(self) -> None:
        for raw, comparison, first, second in self.cases:
            targets = [a["target_obj_id"] for a in second.actions if a["type"] == 2]
            self.assertEqual(len(targets), len(set(targets)))
            order = [u.obj_id for u in second.trace.units]
            emitted = [a["obj_id"] for a in second.actions]
            self.assertEqual(emitted, sorted(emitted, key=order.index))

    def test_move_paths_are_the_routers(self) -> None:
        checked = 0
        for raw, comparison, first, second in self.cases:
            context = ds.context_of(raw)
            router = BoundedRouter(ds.costs())
            baseline_moves = {a["obj_id"]: a for a in first.actions if a["type"] == 1}
            for action in second.actions:
                if action["type"] != 1:
                    continue
                unit = context.unit(action["obj_id"])
                blocked = context.roadblocks if move_mode(unit.unit_type, unit.move_state) in ROADBLOCKED_MODES else frozenset()
                paths = router._dijkstra(unit.cur_hex, move_mode(unit.unit_type, unit.move_state), blocked)
                self.assertEqual(tuple(action["move_path"]), paths.path_to(action["move_path"][-1]))
                if action["obj_id"] in baseline_moves:
                    self.assertEqual(action, baseline_moves[action["obj_id"]])
                checked += 1
        self.assertGreater(checked, 200)


def golden_sequence():
    """Observations of every effect, decided in order by one agent (memory and memo threaded)."""
    base = golden_candidate_observations()
    shared = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
    alternate = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                           ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3), ds.shoot(ds.ENEMY_B, ds.MISSILE, 2)]}})
    occupy = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                        ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None},
                        ds.UNIT_C: {5: None}}, cities=[syn.city(505)], hexes={ds.UNIT_B: 505, ds.UNIT_C: 505})
    move = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                      ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 1: None}}, cities=[syn.city(505)])
    return base + [shared, alternate, occupy, move]


class DeterminismTest(unittest.TestCase):
    def conflict(self):
        return situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3), ds.shoot(ds.ENEMY_B, ds.GUN, 1)]},
                          ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 3), ds.shoot(ds.ENEMY_B, ds.GUN, 2)], 1: None},
                          ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 4), ds.shoot(ds.ENEMY_B, ds.GUN, 2)], 5: None}},
                         cities=[syn.city(505)], hexes={ds.UNIT_C: 505})

    def test_shuffled_inputs(self) -> None:
        reference = decide(ShootReservationPolicy, self.conflict())
        self.assertEqual(len(reserved_record(reference)), 2)
        for key in range(12):
            with self.subTest(permutation=key):
                shuffled = decide(ShootReservationPolicy, ds.reordered(self.conflict(), key))
                self.assertEqual(shuffled.actions, reference.actions)
                self.assertEqual(digest(shuffled.trace), digest(reference.trace))

    def test_json_round_trip(self) -> None:
        engine = decide(ShootReservationPolicy, self.conflict())
        via_json = decide(ShootReservationPolicy, syn.json_round_trip(self.conflict()), Origin.JSON)
        self.assertEqual(engine.actions, via_json.actions)
        self.assertEqual(digest(engine.trace), digest(via_json.trace))
        comparison, _, _ = compare(syn.json_round_trip(self.conflict()), Origin.JSON)
        self.assertTrue(comparison.explained, comparison.problem)

    def test_hash_seeds(self) -> None:
        program = (f"import sys; sys.path[:0] = [{str(ROOT / 'src')!r}, {str(ROOT)!r}]\n"
                   "from tests.test_shoot_reservation import DeterminismTest, decide\n"
                   "from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy\n"
                   "from miaosuan_agent.decision import digest\n"
                   "print(digest(decide(ShootReservationPolicy, DeterminismTest().conflict()).trace))\n")
        digests = set()
        for seed in ("0", "1", "4242", "random"):
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            env["PYTHONHASHSEED"] = seed
            result = subprocess.run([sys.executable, "-c", program], env=env, capture_output=True, text=True,
                                    timeout=120, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            digests.add(result.stdout.strip())
        self.assertEqual(digests, {digest(decide(ShootReservationPolicy, self.conflict()).trace)})

    def test_input_and_memory_are_not_modified(self) -> None:
        raw = self.conflict()
        before = copy.deepcopy(raw)
        memory = Memory(deployment_sent=True)
        decision = decide(ShootReservationPolicy, raw, memory=memory)
        self.assertEqual(raw, before)
        self.assertEqual(decision.memory, memory)

    def test_trace_is_deterministic_and_carries_the_schema(self) -> None:
        first, second = decide(ShootReservationPolicy, self.conflict()), decide(ShootReservationPolicy, self.conflict())
        self.assertEqual(digest(first.trace), digest(second.trace))
        self.assertEqual(first.trace.to_dict()["schema"], TRACE_SCHEMA)
        self.assertEqual(first.trace.policy, CANDIDATE_ID)

    def test_no_clock_or_random_source(self) -> None:
        forbidden = {"random", "time", "uuid", "secrets", "os", "datetime", "glob", "threading", "numpy"}
        tree = ast.parse((ROOT / "src" / "miaosuan_agent" / "experiments" / "shoot_reservation.py").read_text(encoding="utf-8"))
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
            decide(ShootReservationPolicy, self.conflict())
        finally:
            for patch in patches:
                patch.stop()

    def test_golden_chain(self) -> None:
        agent = ShootReservationAgent(strict=True)
        agent.setup(setup_info())
        chain = hashlib.sha256()
        for raw in golden_sequence():
            agent.step(raw)
            chain.update(digest(agent.last_trace).encode("ascii"))
        self.assertEqual(chain.hexdigest(), GOLDEN_TRACE_CHAIN)


class SeatAndStepTest(unittest.TestCase):
    def test_reservations_do_not_cross_seats(self) -> None:
        units = [syn.unit(ds.UNIT_A, ds.RED, 102), syn.unit(ds.UNIT_B, ds.RED, 103), syn.unit(ds.ENEMY_A, ds.BLUE, 304)]
        valid = {ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}}
        first_seat = ds.play_observation(units, valid, seat=SEAT, controlled=[ds.UNIT_A])
        second_seat = ds.play_observation(units, valid, seat=syn.BLUE_SEAT, controlled=[ds.UNIT_B])
        policy = ShootReservationPolicy(ds.costs())
        memory = Memory(deployment_sent=True)
        one = policy.decide(Observation.from_raw(first_seat, Origin.ENGINE), SEAT, ds.RED, memory)
        two = policy.decide(Observation.from_raw(second_seat, Origin.ENGINE), syn.BLUE_SEAT, ds.RED, memory)
        self.assertEqual(summary(one), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(summary(two), [(2, ds.UNIT_B, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(reserved_record(two), [])

    def test_reservations_end_with_the_step(self) -> None:
        agent = ShootReservationAgent(strict=True)
        agent.setup(setup_info())
        agent.memory = Memory(deployment_sent=True)
        step_one = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        step_two = situation({ds.UNIT_A: {1: None}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        self.assertEqual(len(agent.step(step_one)), 1)
        emitted = agent.step(step_two)
        self.assertIn({"actor": SEAT, "type": 2, "obj_id": ds.UNIT_B, "target_obj_id": ds.ENEMY_A, "weapon_id": ds.GUN},
                      [dict(a) for a in emitted])
        self.assertEqual(reserved_record_of(agent.last_trace), [])

    def test_agent_lifecycle_replay_and_contract_errors(self) -> None:
        agent = ShootReservationAgent(strict=True)
        self.assertEqual(agent.policy_id, CANDIDATE_ID)
        with self.assertRaises(RuntimeError):
            agent.step(situation({ds.UNIT_A: {1: None}}))
        agent.setup(setup_info())
        self.assertIsInstance(agent.policy, ShootReservationPolicy)
        self.assertIsInstance(agent.policy.router, BoundedRouter)
        agent.memory = Memory(deployment_sent=True)
        raw = DeterminismTest().conflict()
        memory = agent.memory
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        broken = copy.deepcopy(raw)
        del broken["time"]
        with self.assertRaises(ContractError):
            agent.step(broken)
        lenient = ShootReservationAgent()
        lenient.setup(setup_info())
        self.assertEqual(lenient.step(broken), [])
        self.assertIsNotNone(lenient.last_trace.error)


def reserved_record_of(trace):
    return trace.to_dict().get("shoot_reserved", [])


class IdentityTest(unittest.TestCase):
    def test_sources_are_runtime_r1_plus_one_file(self) -> None:
        self.assertEqual(policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0], V1_DIGEST)
        self.assertEqual(policy_source_digest(sources=rr.candidate_sources())[0], RUNTIME_R1_DIGEST)
        sources = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
        added = set(policy_source_digest(sources=sources)[1]) - set(policy_source_digest(sources=rr.candidate_sources())[1])
        self.assertEqual(added, {"experiments/shoot_reservation.py"})
        self.assertTrue(issubclass(ShootReservationPolicy, BoundedRoutingPolicy))
        self.assertTrue(issubclass(ShootReservationAgent, BoundedRoutingAgent))

    def test_no_scenario_specific_values(self) -> None:
        text = (ROOT / "src" / "miaosuan_agent" / "experiments" / "shoot_reservation.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
                self.assertLess(abs(node.value), 10, node.value)
        manifest = (ROOT / "evaluation" / "baseline-v1-candidate-occupy-reservation" / "manifest.json").read_text(encoding="utf-8")
        for scenario in json.loads(manifest)["scenarios"]:
            self.assertNotIn(str(scenario["scenario_id"]), text)
            self.assertNotIn(f"map {scenario['map_id']}", text)

    def test_golden_sequence_of_baseline_v1_is_unchanged(self) -> None:
        agent = ShootReservationAgent(strict=True)
        agent.setup(setup_info())
        reference = BoundedRoutingPolicy(ds.costs())
        memory = Memory()
        for raw, expected in zip(golden_candidate_observations(), GOLDEN_ACTIONS):
            observation = Observation.from_raw(raw, Origin.ENGINE)
            emitted = agent.step(raw)
            baseline = reference.decide(observation, SEAT, ds.RED, memory)
            memory = baseline.memory
            self.assertEqual([(a["type"], a.get("obj_id")) for a in emitted], expected)
            self.assertEqual([dict(a) for a in emitted], [dict(a) for a in baseline.actions])
            self.assertEqual(reserved_record_of(agent.last_trace), [])
            self.assertEqual(sc._normalized_candidate(agent.last_trace.to_dict(), {}),
                             sc._normalized_oracle(baseline.trace.to_dict()))


if __name__ == "__main__":
    unittest.main()
