"""The launcher-dependent shoot-reservation candidate against baseline-v2. SYNTHETIC data only.

The relation is set on synthetic enemy records as if the seat observed it; engine 4.1.0 does not show it for enemy
units (docs/LAUNCHER_DEPENDENCY_COUNTERFACTUAL.md). Mechanism cases, the gate, seats and steps, the existing
reservations, malformed relations, invariants on a generated corpus (every difference explained by the oracle of
``evaluation/launcher_counterfactual.py``), determinism, identity and the agent contract.
"""

from __future__ import annotations

import ast
import copy
import random
import unittest
from unittest import mock
from pathlib import Path

from miaosuan_agent.boundary import ContractError, Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.decision import gate as gate_module
from miaosuan_agent.evaluation import launcher_counterfactual as lc
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation.identity import policy_source_digest
from miaosuan_agent.experiments.launcher_reservation import (CANDIDATE_ID, TRACE_SCHEMA, LauncherCoordination,
                                                             LauncherReservationAgent, LauncherReservationPolicy)
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent, ShootReservationPolicy

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_occupy_reservation import setup_info
from tests.test_shoot_reservation import golden_sequence

ROOT = Path(__file__).resolve().parents[1]
SEAT = syn.RED_SEAT
ENEMY_C, ENEMY_D = 900203, 900204
ENEMIES = (ds.ENEMY_A, ds.ENEMY_B, ENEMY_C, ENEMY_D)
REASON = LauncherCoordination.LAUNCHER_TARGET_RESERVED.value
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
MEMORY = Memory(deployment_sent=True)


def situation(valid, *, launchers=None, units=None, cities=None, hexes=None, absent=()):
    """Red units at 102, 103, ... (unless ``hexes`` says otherwise); four visible enemies, each with a launcher field
    (``None`` unless ``launchers`` names one; no field at all for the enemies in ``absent``)."""
    hexes, launchers = hexes or {}, launchers or {}
    ids = sorted(valid) if units is None else units
    red = [syn.unit(obj_id, ds.RED, hexes.get(obj_id, 102 + index), unit_type=ds.VEHICLE)
           for index, obj_id in enumerate(ids)]
    blue = []
    for index, enemy in enumerate(ENEMIES):
        record = syn.unit(enemy, ds.BLUE, 304 + index)
        if enemy not in absent:
            record["launcher"] = launchers.get(enemy)
        blue.append(record)
    return ds.play_observation(red + blue, valid, cities=cities if cities is not None else [syn.city(909)])


def decide(policy_class, raw, origin=Origin.ENGINE, memory=MEMORY, seat=SEAT, faction=ds.RED):
    return policy_class(ds.costs()).decide(Observation.from_raw(raw, origin), seat, faction, memory)


def compare(raw, origin=Origin.ENGINE):
    costs = ds.costs()
    return lc.compare(raw, SEAT, ds.RED, ShootReservationPolicy(costs), LauncherReservationPolicy(costs),
                      lambda: ShootReservationPolicy(costs), MEMORY, origin)


def summary(decision):
    return [(int(a["type"]), a.get("obj_id"), a.get("target_obj_id"), a.get("weapon_id")) for a in decision.actions]


def record(decision):
    return decision.trace.to_dict()["launcher_reserved"]


class MechanismTest(unittest.TestCase):
    def assertExplained(self, raw):
        comparison, first, second = compare(raw)
        self.assertTrue(comparison.explained, comparison.problem)
        return comparison, first, second

    def test_dependent_after_its_launcher_is_excluded(self) -> None:  # case 1 and 10
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(first), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN), (2, ds.UNIT_B, ds.ENEMY_B, ds.GUN)])
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(record(second), [{"obj_id": ds.UNIT_B, "effect": "fallback-none", "reason": REASON, "excluded": [
            {"target_obj_id": ds.ENEMY_B, "launcher": ds.ENEMY_A, "weapon_id": ds.GUN, "attack_level": 3,
             "reserved_by": ds.UNIT_A, "reserved_by_position": 0}]}])
        self.assertEqual(second.trace.to_dict()["shoot_reserved"], [])
        unit = second.trace.units[1]
        self.assertEqual(unit.no_op_reason, f"launcher targets reserved: {REASON}; move: movement not listed")
        self.assertEqual((comparison.category, comparison.units["fallback-none"]), ("C4", 1))

    def test_launcher_not_shot(self) -> None:  # case 2
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ENEMY_C, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(record(second), [])

    def test_launcher_option_that_loses_selection_reserves_nothing(self) -> None:  # case 3
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ENEMY_C, ds.GUN, 4), ds.shoot(ds.ENEMY_A, ds.GUN, 2)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}}, launchers={ds.ENEMY_B: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(summary(second)[0], (2, ds.UNIT_A, ENEMY_C, ds.GUN))
        self.assertEqual(record(second), [])

    def test_dependent_processed_before_the_launcher_shooter(self) -> None:  # case 5
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(record(second), [])

    def test_two_dependents_of_one_launcher(self) -> None:  # case 6
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ENEMY_C, ds.MISSILE, 2)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A, ENEMY_C: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(second), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN)])
        self.assertEqual([(e["obj_id"], e["excluded"][0]["target_obj_id"]) for e in record(second)],
                         [(ds.UNIT_B, ds.ENEMY_B), (ds.UNIT_C, ENEMY_C)])
        self.assertEqual((comparison.category, len(comparison.direct)), ("C5", 2))

    def test_alternate_target_keeps_baseline_ranking(self) -> None:  # case 7
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3), ds.shoot(ENEMY_D, ds.GUN, 1),
                                         ds.shoot(ENEMY_C, ds.MISSILE, 2), ds.shoot(ENEMY_C, ds.GUN, 2)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(second)[1], (2, ds.UNIT_B, ENEMY_C, ds.GUN))
        self.assertEqual(second.trace.units[1].rank, (-2, ENEMY_C, ds.GUN))
        self.assertEqual(dict(second.trace.units[1].detail),
                         {"attack_level": 2, "launcher_target_reserved": ds.ENEMY_B, "launcher_reservation": "alternate-target"})
        self.assertEqual(comparison.category, "C1")

    def test_fallback_to_occupation(self) -> None:  # case 8
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)], 5: None, 1: None}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A}, cities=[syn.city(505)], hexes={ds.UNIT_B: 505})
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(second)[1][:2], (5, ds.UNIT_B))
        self.assertEqual((record(second)[0]["effect"], comparison.category), ("fallback-occupy", "C2"))

    def test_fallback_to_movement_keeps_the_route(self) -> None:  # case 9
        valid = {ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)], 1: None}}
        raw = situation(valid, launchers={ds.ENEMY_B: ds.ENEMY_A}, cities=[syn.city(505)])
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(second)[1][:2], (1, ds.UNIT_B))
        reference = decide(ShootReservationPolicy, situation({ds.UNIT_A: valid[ds.UNIT_A], ds.UNIT_B: {1: None}},
                                                             cities=[syn.city(505)]))
        self.assertEqual(second.actions[1], reference.actions[1])
        self.assertEqual(comparison.category, "C3")

    def test_absent_or_none_relation_is_baseline(self) -> None:  # case 11
        valid = {ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}}
        for raw in (situation(valid), situation(valid, absent=ENEMIES)):
            comparison, first, second = self.assertExplained(raw)
            self.assertTrue(comparison.identical)
            self.assertEqual(record(second), [])
            self.assertEqual(second.trace.diagnostics, first.trace.diagnostics)

    def test_malformed_relation_is_skipped_with_a_diagnostic(self) -> None:  # case 12
        valid = {ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}}
        for bad in (str(ds.ENEMY_A), True, [ds.ENEMY_A], float(ds.ENEMY_A)):
            with self.subTest(value=bad):
                comparison, first, second = self.assertExplained(situation(valid, launchers={ds.ENEMY_B: bad}))
                self.assertTrue(comparison.identical)
                self.assertEqual(record(second), [])
                self.assertEqual(second.trace.diagnostics,
                                 (f"unit {ds.ENEMY_B}: malformed launcher relation skipped: {bad!r}",))

    def test_baseline_diagnostics_keep_their_order(self) -> None:
        short, long_ = 99001, 100001  # ids of different lengths: text order differs from processing order
        units = [syn.unit(short, ds.RED, 102), syn.unit(long_, ds.RED, 103),
                 dict(syn.unit(ds.ENEMY_A, ds.BLUE, 304), launcher="bad")]
        valid = {short: {2: [{"weapon_id": ds.GUN}]}, long_: {2: [{"weapon_id": ds.GUN}]}}
        raw = ds.play_observation(units, valid)
        first, second = decide(ShootReservationPolicy, raw), decide(LauncherReservationPolicy, raw)
        self.assertEqual(second.trace.diagnostics,
                         first.trace.diagnostics + (f"unit {ds.ENEMY_A}: malformed launcher relation skipped: 'bad'",))
        self.assertEqual([d.split(":")[0] for d in first.trace.diagnostics], [f"unit {short}", f"unit {long_}"])

    def test_same_target_reservation_is_unchanged(self) -> None:  # case 15
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        comparison, first, second = self.assertExplained(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(second.trace.to_dict()["shoot_reserved"], first.trace.to_dict()["shoot_reserved"])
        self.assertEqual(record(second), [])

    def test_non_shoot_actions_are_unchanged(self) -> None:  # case 16
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {5: None},
                         ds.UNIT_C: {1: None}}, launchers={ds.ENEMY_B: ds.ENEMY_A},
                        cities=[syn.city(505), syn.city(909)], hexes={ds.UNIT_B: 505})
        comparison, first, second = self.assertExplained(raw)
        self.assertTrue(comparison.identical)
        self.assertEqual(summary(first), summary(second))

    def test_secondary_interaction_is_classified_c6(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3), ds.shoot(ENEMY_C, ds.GUN, 2)]},
                         ds.UNIT_C: {2: [ds.shoot(ENEMY_C, ds.GUN, 2)], 1: None}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A}, cities=[syn.city(505)])
        comparison, first, second = self.assertExplained(raw)
        self.assertEqual(summary(second)[1], (2, ds.UNIT_B, ENEMY_C, ds.GUN))
        self.assertEqual(summary(second)[2][:2], (1, ds.UNIT_C))
        self.assertEqual((comparison.category, comparison.units["secondary"]), ("C6", 1))


class GateTest(unittest.TestCase):
    def test_a_rejected_launcher_shot_reserves_nothing(self) -> None:  # case 4
        real = gate_module.check

        def rejecting(actions, context, router):
            kept = [a for a in actions if not (a.get("obj_id") == ds.UNIT_A and a.get("type") == 2)]
            result = real(kept, context, router)
            extra = tuple(gate_module.Rejection(2, ds.UNIT_A, "synthetic rejection") for a in actions if a not in kept)
            return gate_module.GateResult(result.accepted, result.rejected + extra)

        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        with mock.patch.object(gate_module, "check", rejecting):
            second = decide(LauncherReservationPolicy, raw)
        self.assertEqual(summary(second), [(2, ds.UNIT_B, ds.ENEMY_B, ds.GUN)])
        self.assertEqual(record(second), [])


class SeatAndStepTest(unittest.TestCase):
    def test_no_leak_across_steps(self) -> None:  # case 13
        agent = LauncherReservationAgent(strict=True)
        agent.setup(setup_info())
        agent.memory = MEMORY
        one = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A})
        two = situation({ds.UNIT_A: {1: None}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A}, cities=[syn.city(505)])
        self.assertEqual(len(agent.step(one)), 1)
        emitted = [dict(a) for a in agent.step(two)]
        self.assertIn({"actor": SEAT, "type": 2, "obj_id": ds.UNIT_B, "target_obj_id": ds.ENEMY_B, "weapon_id": ds.GUN},
                      emitted)
        self.assertEqual(agent.last_trace.to_dict()["launcher_reserved"], [])
        self.assertEqual(agent.policy._relations, {})

    def test_no_leak_across_seats(self) -> None:  # case 14
        units = [syn.unit(ds.UNIT_A, ds.RED, 102), syn.unit(ds.UNIT_B, ds.RED, 103),
                 dict(syn.unit(ds.ENEMY_A, ds.BLUE, 304), launcher=None),
                 dict(syn.unit(ds.ENEMY_B, ds.BLUE, 305), launcher=ds.ENEMY_A)]
        valid = {ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}}
        first_seat = ds.play_observation(units, valid, seat=SEAT, controlled=[ds.UNIT_A])
        second_seat = ds.play_observation(units, valid, seat=syn.BLUE_SEAT, controlled=[ds.UNIT_B])
        policy = LauncherReservationPolicy(ds.costs())
        one = policy.decide(Observation.from_raw(first_seat, Origin.ENGINE), SEAT, ds.RED, MEMORY)
        two = policy.decide(Observation.from_raw(second_seat, Origin.ENGINE), syn.BLUE_SEAT, ds.RED, MEMORY)
        self.assertEqual(summary(one), [(2, ds.UNIT_A, ds.ENEMY_A, ds.GUN)])
        self.assertEqual(summary(two), [(2, ds.UNIT_B, ds.ENEMY_B, ds.GUN)])
        self.assertEqual(record(two), [])


def generated(seed):
    rng = random.Random(seed)
    units = [ds.UNIT_A, ds.UNIT_B, ds.UNIT_C, ds.UNIT_D]
    valid = {}
    for unit in units:
        actions = {}
        if rng.random() < 0.8:
            actions[2] = [ds.shoot(rng.choice(ENEMIES), rng.choice((ds.GUN, ds.MISSILE)), rng.randint(0, 4))
                          for _ in range(rng.randint(0, 3))]
        if rng.random() < 0.3:
            actions[5] = None
        if rng.random() < 0.4:
            actions[1] = None
        valid[unit] = actions
    launchers = {enemy: rng.choice(ENEMIES) for enemy in ENEMIES if rng.random() < 0.5}
    hexes = {unit: rng.choice((505, 102 + i)) for i, unit in enumerate(units)}
    return situation(valid, launchers=launchers, cities=[syn.city(505), syn.city(909)], hexes=hexes)


class InvariantTest(unittest.TestCase):
    def test_every_difference_is_explained(self) -> None:
        categories = {c: 0 for c in lc.CATEGORIES}
        for seed in range(600):
            raw = generated(seed)
            comparison, first, second = compare(raw)
            self.assertTrue(comparison.explained, (seed, comparison.problem))
            if comparison.category:
                categories[comparison.category] += 1
            shots = [a for a in second.actions if int(a["type"]) == 2]
            relations = lc.relations(raw)
            for index, action in enumerate(shots):
                earlier = {a["target_obj_id"] for a in shots[:index]}
                self.assertFalse(relations.get(action["target_obj_id"]) in earlier
                                 and action["target_obj_id"] not in earlier, seed)
        self.assertEqual(categories["C7"], 0)
        self.assertGreater(sum(categories[c] for c in ("C1", "C2", "C3", "C4")), 0)

    def test_baseline_v2_golden_sequence_is_unchanged(self) -> None:
        agent, reference = LauncherReservationAgent(strict=True), ShootReservationAgent(strict=True)
        agent.setup(setup_info())
        reference.setup(setup_info())
        for raw in golden_sequence():
            self.assertEqual([dict(a) for a in agent.step(raw)], [dict(a) for a in reference.step(raw)])
            ours, theirs = agent.last_trace.to_dict(), reference.last_trace.to_dict()
            self.assertEqual(ours.pop("launcher_reserved"), [])
            for payload in (ours, theirs):
                payload.pop("schema")
                payload.pop("policy")
            self.assertEqual(ours, theirs)

    def test_shuffled_inputs(self) -> None:  # case 17
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3), ds.shoot(ENEMY_C, ds.GUN, 1)]},
                         ds.UNIT_C: {2: [ds.shoot(ENEMY_C, ds.MISSILE, 2)], 1: None}},
                        launchers={ds.ENEMY_B: ds.ENEMY_A, ENEMY_C: ds.ENEMY_A}, cities=[syn.city(505)])
        reference = decide(LauncherReservationPolicy, raw)
        self.assertEqual(len(record(reference)), 2)
        for key in range(12):
            with self.subTest(permutation=key):
                shuffled = decide(LauncherReservationPolicy, ds.reordered(raw, key))
                self.assertEqual(shuffled.actions, reference.actions)
                self.assertEqual(digest(shuffled.trace), digest(reference.trace))

    def test_input_memory_and_determinism(self) -> None:
        raw = generated(7)
        before = copy.deepcopy(raw)
        first, second = decide(LauncherReservationPolicy, raw), decide(LauncherReservationPolicy, raw)
        self.assertEqual(raw, before)
        self.assertEqual(first.memory, MEMORY)
        self.assertEqual(digest(first.trace), digest(second.trace))
        self.assertEqual((first.trace.to_dict()["schema"], first.trace.policy), (TRACE_SCHEMA, CANDIDATE_ID))


class IdentityTest(unittest.TestCase):
    def test_sources_are_baseline_v2_plus_one_file(self) -> None:
        v2 = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
        self.assertEqual(policy_source_digest(sources=v2)[0], V2_DIGEST)
        added = (set(policy_source_digest(sources=v2 + ("experiments/launcher_reservation.py",))[1])
                 - set(policy_source_digest(sources=v2)[1]))
        self.assertEqual(added, {"experiments/launcher_reservation.py"})
        self.assertTrue(issubclass(LauncherReservationPolicy, ShootReservationPolicy))

    def test_no_clock_random_global_view_or_scenario_values(self) -> None:
        text = (ROOT / "src" / "miaosuan_agent" / "experiments" / "launcher_reservation.py").read_text(encoding="utf-8")
        forbidden = {"random", "time", "uuid", "secrets", "os", "datetime", "glob", "threading", "numpy"}
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                self.assertFalse({a.name.split(".")[0] for a in node.names} & forbidden)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                self.assertNotIn(node.module.split(".")[0], forbidden)
            elif isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
                self.assertLess(abs(node.value), 10, node.value)
        for word in ("global_observation", "GLOBAL", "judge_info", "516", "scenario_id", "terrain"):
            self.assertNotIn(word, text)

    def test_agent_lifecycle_and_contract(self) -> None:
        agent = LauncherReservationAgent(strict=True)
        self.assertEqual(agent.policy_id, CANDIDATE_ID)
        agent.setup(setup_info())
        agent.memory = MEMORY
        raw = generated(11)
        memory = agent.memory
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        broken = copy.deepcopy(raw)
        del broken["time"]
        with self.assertRaises(ContractError):
            agent.step(broken)
        lenient = LauncherReservationAgent()
        lenient.setup(setup_info())
        self.assertEqual(lenient.step(broken), [])


if __name__ == "__main__":
    unittest.main()
