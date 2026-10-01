"""The read-only target-allocation audit of baseline-v2 (``evaluation/allocation_audit.py``). SYNTHETIC data only.

Collision groups and ownership metrics, the derived preferred target, the O-B oracle (owner unchanged, unambiguous,
coupled), coupled components, the factual no-op reasons and the defect check, and the reconstruction's own
consistency check. Every decision comes from the frozen baseline-v2 on synthetic observations.
"""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import Memory
from miaosuan_agent.evaluation import allocation_audit as aa
from miaosuan_agent.experiments.shoot_reservation import Effect, ShootReservationPolicy

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_shoot_reservation import ENEMY_C, SEAT, situation

MEMORY = Memory(deployment_sent=True)


def decide(raw):
    return ShootReservationPolicy(ds.costs()).decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED, MEMORY)


def oracle(raw, decision, group):
    return aa.oracle_b(raw, SEAT, ds.RED, decision, group, lambda: ShootReservationPolicy(ds.costs()), MEMORY)


def no_op(raw, decision, unit):
    return aa.no_op_reasons(raw, SEAT, ds.RED, decision, unit, ShootReservationPolicy(ds.costs()).router)


def shots(decision):
    return [(a["obj_id"], a["target_obj_id"]) for a in decision.actions if int(a["type"]) == aa.SHOOT]


class GroupTest(unittest.TestCase):
    def test_equal_claimants_keep_the_first(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        decision = decide(raw)
        [group] = aa.collision_groups(raw, decision)
        self.assertEqual((group.target, group.reserver, group.displaced), (ds.ENEMY_A, ds.UNIT_A, [ds.UNIT_B]))
        m = group.metrics()
        self.assertEqual((m["claimants"], m["eligible"], m["stronger_displaced"], m["level_gap"]), (2, 2, 0, 0))
        self.assertTrue(m["reserver_is_max_claimant"] and m["tie_at_max"])
        self.assertEqual(m["reserver_rank"], 1)
        self.assertEqual(oracle(raw, decision, group), {"owner_changed": False})
        self.assertEqual(aa.inconsistencies(raw, decision), [])

    def test_no_collision_no_group(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}})
        self.assertEqual(aa.collision_groups(raw, decide(raw)), [])

    def test_weaker_reserver_and_an_unambiguous_owner_change(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 1)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 4), ds.shoot(ds.ENEMY_B, ds.GUN, 1)]}})
        decision = decide(raw)
        self.assertEqual(shots(decision), [(ds.UNIT_A, ds.ENEMY_A), (ds.UNIT_B, ds.ENEMY_B)])
        [group] = aa.collision_groups(raw, decision)
        m = group.metrics()
        self.assertEqual((m["reserver_level"], m["max_claimant_level"], m["level_gap"], m["reserver_rank"]), (1, 4, 3, 2))
        self.assertEqual(m["stronger_displaced"], 1)
        self.assertFalse(m["reserver_is_max_claimant"] or m["tie_at_max"])
        result = oracle(raw, decision, group)
        self.assertEqual(result, {"owner_changed": True, "unambiguous": True, "changed_units": 2, "promoted_level_gain": 3,
                                  "promoted_by": "higher attack level", "former_owner": "none", "shot_delta": -1,
                                  "non_shoot_changes": 0, "promoted_previous": "alternate shoot"})
        self.assertEqual(oracle(raw, decision, group), result)

    def test_weapon_tie_break_changes_the_owner(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.MISSILE, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        decision = decide(raw)
        [group] = aa.collision_groups(raw, decision)
        self.assertEqual(group.metrics()["stronger_displaced"], 0)
        self.assertEqual(aa.strongest(group)["unit"], ds.UNIT_B)
        self.assertEqual(oracle(raw, decision, group)["promoted_by"], "weapon tie-break")

    def test_coupled_owner_change(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 2), ds.shoot(ds.ENEMY_B, ds.GUN, 1)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 1)]}})
        decision = decide(raw)
        self.assertEqual(shots(decision), [(ds.UNIT_A, ds.ENEMY_A), (ds.UNIT_C, ds.ENEMY_B)])
        [group] = aa.collision_groups(raw, decision)
        result = oracle(raw, decision, group)
        self.assertTrue(result["owner_changed"])
        self.assertFalse(result["unambiguous"])
        self.assertEqual(result["changed_units"], 3)

    def test_groups_sharing_a_shooter_form_one_component(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3), ds.shoot(ds.ENEMY_B, ds.GUN, 1)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]},
                         ds.UNIT_D: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 2)]}})
        decision = decide(raw)
        groups = aa.collision_groups(raw, decision)
        self.assertEqual([(g.target, g.reserver, g.displaced) for g in groups],
                         [(ds.ENEMY_A, ds.UNIT_A, [ds.UNIT_B]), (ds.ENEMY_B, ds.UNIT_C, [ds.UNIT_D])])
        self.assertEqual([e["unit"] for e in groups[1].eligible], [ds.UNIT_A, ds.UNIT_C, ds.UNIT_D])
        self.assertFalse(groups[1].eligible[0]["claimant"])
        self.assertEqual(aa.components(groups), [{"targets": 2, "shooters": 4}])
        separate = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                              ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]}, ds.UNIT_D: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 2)]}})
        self.assertEqual(aa.components(aa.collision_groups(separate, decide(separate))),
                         [{"targets": 1, "shooters": 2}, {"targets": 1, "shooters": 2}])

    def test_a_unit_excluded_on_a_target_it_did_not_prefer(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 4), ds.shoot(ds.ENEMY_A, ds.GUN, 2),
                                         ds.shoot(ENEMY_C, ds.GUN, 1)]}})
        decision = decide(raw)
        groups = {g.target: g for g in aa.collision_groups(raw, decision)}
        self.assertEqual(groups[ds.ENEMY_B].displaced, [ds.UNIT_C])
        self.assertEqual((groups[ds.ENEMY_A].displaced, groups[ds.ENEMY_A].excluded_other), ([], [ds.UNIT_C]))
        self.assertEqual(groups[ds.ENEMY_B].metrics()["stronger_displaced"], 1)

    def test_preferred_target_follows_the_baseline_rank(self) -> None:
        self.assertEqual(aa.preferred_target([(5, 1, 2), (4, 9, 2), (3, 1, 1)]), 4)
        self.assertEqual(aa.preferred_target([(5, 1, 2), (6, 1, 3)]), 6)
        self.assertEqual(aa.best_on([(5, 9, 2), (5, 1, 2), (5, 3, 3), (6, 1, 4)], 5), (5, 3, 3))
        self.assertIsNone(aa.best_on([(5, 1, 2)], 6))

    def test_fallback_classes_cover_every_displacing_effect(self) -> None:
        self.assertEqual(set(aa.FALLBACK), {e.value for e in Effect} - {Effect.UNCHANGED.value})

    def test_withdraw_target_is_a_copy_and_targets_only_the_listed_units(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3), ds.shoot(ds.ENEMY_B, ds.GUN, 1)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        before = copy.deepcopy(raw)
        changed = aa.withdraw_target(raw, ds.ENEMY_A, {ds.UNIT_A})
        self.assertEqual(raw, before)
        self.assertEqual(aa.candidates(changed), {ds.UNIT_A: [(ds.ENEMY_B, ds.GUN, 1)], ds.UNIT_B: [(ds.ENEMY_A, ds.GUN, 3)]})


class NoOpTest(unittest.TestCase):
    def test_nothing_else_listed(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        decision = decide(raw)
        result = no_op(raw, decision, ds.UNIT_B)
        self.assertEqual(result, {"reasons": {"shoot": "its only shootable target was reserved", "occupy": "not listed",
                                              "move": "movement not listed", "trace_move_reason": "movement not listed",
                                              "unsupported_types": []},
                                  "defect": False, "free_shoot_candidates": 0})

    def test_suppressed_occupation_and_standing_on_the_objective(self) -> None:
        raw = situation({ds.UNIT_A: {5: None}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None, 1: None, 9: None}},
                        cities=[syn.city(505)], hexes={ds.UNIT_A: 505, ds.UNIT_C: 505})
        decision = decide(raw)
        result = no_op(raw, decision, ds.UNIT_C)
        self.assertEqual(result["reasons"]["occupy"], "suppressed by the same-step objective reservation")
        self.assertEqual(result["reasons"]["move"], "standing on an objective outside own control")
        self.assertEqual(result["reasons"]["move"], result["reasons"]["trace_move_reason"])
        self.assertEqual(result["reasons"]["unsupported_types"], [9])
        self.assertFalse(result["defect"])

    def test_every_target_reserved(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 3)]},
                         ds.UNIT_C: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3), ds.shoot(ds.ENEMY_B, ds.GUN, 2)]}})
        decision = decide(raw)
        self.assertEqual(no_op(raw, decision, ds.UNIT_C)["reasons"]["shoot"], "every shootable target was reserved")

    def test_a_supported_action_left_over_is_a_defect(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        decision = decide(raw)
        other = copy.deepcopy(raw)
        other["valid_actions"][ds.UNIT_B][2].append(ds.shoot(ds.ENEMY_B, ds.GUN, 1))
        result = no_op(other, decision, ds.UNIT_B)
        self.assertTrue(result["defect"])
        self.assertEqual(result["free_shoot_candidates"], 1)
        occupy = copy.deepcopy(raw)
        occupy["valid_actions"][ds.UNIT_B][5] = None
        self.assertTrue(no_op(occupy, decision, ds.UNIT_B)["defect"])


class ConsistencyTest(unittest.TestCase):
    def test_a_different_observation_is_reported(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        decision = decide(raw)
        self.assertEqual(aa.inconsistencies(raw, decision), [])
        other = copy.deepcopy(raw)
        other["valid_actions"][ds.UNIT_B][2] = [ds.shoot(ds.ENEMY_A, ds.GUN, 2), ds.shoot(ds.ENEMY_B, ds.GUN, 4)]
        problems = aa.inconsistencies(other, decision)
        self.assertIn("an excluded option is not a candidate in the observation", problems)
        self.assertIn("the derived preferred target disagrees with the recorded effect", problems)

    def test_the_recorded_preferred_target_is_derived(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]},
                         ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_B, ds.GUN, 2), ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        decision = decide(raw)
        self.assertEqual(dict(decision.trace.units[1].detail)["shoot_target_reserved"], ds.ENEMY_A)
        self.assertEqual(aa.preferred_target(aa.candidates(raw)[ds.UNIT_B]), ds.ENEMY_A)
        self.assertEqual(aa.inconsistencies(raw, decision), [])


if __name__ == "__main__":
    unittest.main()
