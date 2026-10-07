"""Sprint 20 T11-O1 kill-first rule, its comparison with baseline-v2 and the decision logic. SYNTHETIC data only.

The rule (``experiments/t11_kill_first.py``) on hand-built situations of every registered boundary; the comparison and
classification (``evaluation/s20_t11.py``) on those situations and on a generated corpus; the opportunity, coupling,
kill-edge and disposition rules at their edges; the documentary kill-model rule; the privacy sanitizer.
"""

from __future__ import annotations

import copy
import random
import unittest
from unittest import mock

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import Memory
from miaosuan_agent.decision import gate as gate_module
from miaosuan_agent.evaluation import s20_t11 as st
from miaosuan_agent.experiments import t11_kill_first as tk
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn

SEAT = syn.RED_SEAT
A, B, C, D = ds.UNIT_A, ds.UNIT_B, ds.UNIT_C, ds.UNIT_D
E1, E2, E3 = 900201, 900202, 900203
GUN, MISSILE = ds.GUN, ds.MISSILE
PLAY = Memory(deployment_sent=True)


def situation(valid, blood, *, cities=None, hexes=None, enemy_fields=None, shuffle=None):
    """Red units at 102, 103, ... (unless ``hexes`` says otherwise); blue enemies E1, E2, E3 with the given blood
    (``blood`` maps enemy -> value; a missing key means no blood field); ``enemy_fields`` overrides fields."""
    hexes = hexes or {}
    red = [dict(syn.unit(obj, ds.RED, hexes.get(obj, 102 + i), unit_type=ds.VEHICLE), blood=3)
           for i, obj in enumerate(sorted(valid))]
    blue = []
    for i, enemy in enumerate((E1, E2, E3)):
        u = syn.unit(enemy, ds.BLUE, 304 + i)
        if enemy in blood:
            u["blood"] = blood[enemy]
        u.update((enemy_fields or {}).get(enemy, {}))
        blue.append(u)
    units = red + blue
    if shuffle is not None:
        shuffle.shuffle(units)
    return ds.play_observation(units, valid, cities=cities if cities is not None else [syn.city(909)])


def decide(raw, ranking=tk.KILL_FIRST, memory=PLAY):
    policy = tk.RankedReservationPolicy(ds.costs(), ranking)
    decision = policy.decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED, memory)
    return decision, policy


def baseline(raw, memory=PLAY):
    return ShootReservationPolicy(ds.costs()).decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED, memory)


def shots(decision):
    return [(a["obj_id"], a.get("target_obj_id"), a.get("weapon_id")) for a in decision.actions if a["type"] == 2]


def kinds(decision):
    return [(int(a["type"]), a["obj_id"]) for a in decision.actions]


def compare(raw, memory=PLAY):
    bd, b = decide(raw, tk.BASELINE, memory)
    cd, c = decide(raw, tk.KILL_FIRST, memory)
    return st.compare_decision(2, bd.actions, b.records, cd.actions, c.records, bd.memory, cd.memory), bd, cd


BLOOD = {E1: 4, E2: 1, E3: 3}


class RuleTest(unittest.TestCase):
    def test_one_target_is_baseline(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 5), ds.shoot(E1, MISSILE, 7)]}}, BLOOD)
        decision, policy = decide(raw)
        self.assertEqual(decision.actions, baseline(raw).actions)
        self.assertEqual(shots(decision), [(A, E1, MISSILE)])
        self.assertIsNone(policy.records[0].fallback)

    def test_two_targets_lowest_blood_selected(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]}}, BLOOD)
        self.assertEqual(shots(baseline(raw)), [(A, E1, GUN)])
        decision, policy = decide(raw)
        self.assertEqual(shots(decision), [(A, E2, GUN)])
        self.assertEqual((policy.records[0].baseline_choice, policy.records[0].ranked_choice),
                         ((E1, GUN, 8), (E2, GUN, 3)))

    def test_blood_direction_is_lowest_not_highest(self) -> None:
        raw = situation({A: {2: [ds.shoot(E3, GUN, 5), ds.shoot(E2, GUN, 5), ds.shoot(E1, GUN, 5)]}}, BLOOD)
        self.assertEqual(shots(decide(raw)[0]), [(A, E2, GUN)])

    def test_blood_zero_is_comparable_and_lowest(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 5), ds.shoot(E2, GUN, 5)]}}, {E1: 0, E2: 1})
        decision, policy = decide(raw)
        self.assertEqual(shots(decision), [(A, E1, GUN)])
        self.assertIsNone(policy.records[0].fallback)

    def test_equal_blood_keeps_baseline_target_order(self) -> None:
        tie = {E1: 2, E2: 2, E3: 4}
        # baseline order among the tied targets: higher attack level first ...
        raw = situation({A: {2: [ds.shoot(E1, GUN, 3), ds.shoot(E2, GUN, 6), ds.shoot(E3, GUN, 9)]}}, tie)
        self.assertEqual(shots(decide(raw)[0]), [(A, E2, GUN)])
        # ... then the lower target id
        raw = situation({A: {2: [ds.shoot(E2, GUN, 6), ds.shoot(E1, GUN, 6), ds.shoot(E3, GUN, 9)]}}, tie)
        self.assertEqual(shots(decide(raw)[0]), [(A, E1, GUN)])

    def test_same_target_highest_level_then_lower_weapon(self) -> None:
        raw = situation({A: {2: [ds.shoot(E2, MISSILE, 4), ds.shoot(E2, GUN, 6), ds.shoot(E1, GUN, 9)]}}, BLOOD)
        self.assertEqual(shots(decide(raw)[0]), [(A, E2, GUN)])
        raw = situation({A: {2: [ds.shoot(E2, MISSILE, 6), ds.shoot(E2, GUN, 6), ds.shoot(E1, GUN, 9)]}}, BLOOD)
        self.assertEqual(shots(decide(raw)[0]), [(A, E2, GUN)])  # GUN 43 < MISSILE 71

    def test_unreadable_blood_fails_closed_to_baseline(self) -> None:
        options = {A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]}}
        cases = {"missing": ({E1: 4}, tk.BLOOD_MISSING), "bool": ({E1: 4, E2: True}, tk.BLOOD_MALFORMED),
                 "negative": ({E1: 4, E2: -1}, tk.BLOOD_MALFORMED), "float": ({E1: 4, E2: 1.0}, tk.BLOOD_MALFORMED),
                 "text": ({E1: 4, E2: "1"}, tk.BLOOD_MALFORMED), "none": ({E1: 4, E2: None}, tk.BLOOD_MALFORMED)}
        for name, (blood, reason) in cases.items():
            with self.subTest(name):
                raw = situation(options, blood)
                decision, policy = decide(raw)
                self.assertEqual(shots(decision), [(A, E1, GUN)])
                self.assertEqual(policy.records[0].fallback, reason)

    def test_target_not_visible_fails_closed(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(900299, GUN, 3)]}}, BLOOD)
        decision, policy = decide(raw)
        self.assertEqual(shots(decision), [(A, E1, GUN)])
        self.assertEqual(policy.records[0].fallback, tk.NOT_VISIBLE)

    def test_an_own_unit_is_not_an_enemy_view(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(B, GUN, 3)]}, B: {}}, BLOOD)
        decision, policy = decide(raw)
        self.assertEqual(policy.records[0].fallback, tk.NOT_VISIBLE)

    def test_reserved_low_blood_target_is_excluded_before_ranking(self) -> None:
        raw = situation({A: {2: [ds.shoot(E2, GUN, 2)]},
                         B: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3), ds.shoot(E3, GUN, 5)]}}, BLOOD)
        decision, policy = decide(raw)
        self.assertEqual(shots(decision), [(A, E2, GUN), (B, E3, GUN)])  # E3 (3) is the lowest unreserved
        record = policy.records[1]
        self.assertEqual(record.excluded, ((E2, GUN, 3),))
        self.assertEqual(record.reserved_before, frozenset({E2}))

    def test_early_root_switch_changes_a_later_exclusion(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]},
                         B: {2: [ds.shoot(E2, GUN, 6), ds.shoot(E3, GUN, 2)]}}, BLOOD)
        self.assertEqual(shots(baseline(raw)), [(A, E1, GUN), (B, E2, GUN)])
        comparison, bd, cd = compare(raw)
        self.assertEqual(shots(cd), [(A, E2, GUN), (B, E3, GUN)])
        self.assertEqual([(d.obj_id, d.cls, d.kind) for d in comparison.diffs],
                         [(A, st.ROOT, st.CHANGED_SHOT), (B, st.INDUCED_SHOOT, st.CHANGED_SHOT)])
        self.assertEqual(comparison.max_chain, 2)
        self.assertEqual((comparison.newly_reserved, comparison.no_longer_reserved), (1, 1))
        self.assertEqual((comparison.excluded_only_candidate, comparison.excluded_only_baseline), (1, 0))
        self.assertEqual(comparison.problems, [])

    def test_a_three_unit_reservation_chain(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]},
                         B: {2: [ds.shoot(E2, GUN, 6), ds.shoot(E3, GUN, 5)]},
                         C: {2: [ds.shoot(E3, GUN, 6), ds.shoot(E1, GUN, 2)]}}, BLOOD)
        self.assertEqual(shots(baseline(raw)), [(A, E1, GUN), (B, E2, GUN), (C, E3, GUN)])
        comparison, _, cd = compare(raw)
        self.assertEqual(shots(cd), [(A, E2, GUN), (B, E3, GUN), (C, E1, GUN)])
        self.assertEqual([(d.cls, d.chain) for d in comparison.diffs],
                         [(st.ROOT, 1), (st.INDUCED_SHOOT, 2), (st.INDUCED_SHOOT, 3)])
        self.assertEqual(comparison.max_chain, 3)

    def test_reservation_can_remove_a_later_shot(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]}, B: {2: [ds.shoot(E2, GUN, 6)], 5: None}},
                        BLOOD, hexes={B: 909})
        comparison, bd, cd = compare(raw)
        self.assertEqual(kinds(cd), [(2, A), (5, B)])
        self.assertEqual([(d.cls, d.kind) for d in comparison.diffs],
                         [(st.ROOT, st.CHANGED_SHOT), (st.INDUCED_NONSHOOT, st.LOST_SHOT)])

    def test_reservation_can_add_a_later_shot(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]}, B: {2: [ds.shoot(E1, GUN, 6)], 5: None}},
                        BLOOD, hexes={B: 909})
        self.assertEqual(kinds(baseline(raw)), [(2, A), (5, B)])
        comparison, bd, cd = compare(raw)
        self.assertEqual(shots(cd), [(A, E2, GUN), (B, E1, GUN)])
        self.assertEqual([(d.cls, d.kind) for d in comparison.diffs],
                         [(st.ROOT, st.CHANGED_SHOT), (st.INDUCED_NONSHOOT, st.GAINED_SHOT)])

    def test_occupation_reservation_carries_an_induced_change(self) -> None:
        # B loses its shot, falls back to occupying hex 909 and so blocks C's occupation of the same objective
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]}, B: {2: [ds.shoot(E2, GUN, 6)], 5: None},
                         C: {5: None, 1: None}}, BLOOD, hexes={B: 909, C: 909})
        comparison, bd, cd = compare(raw)
        self.assertEqual(kinds(bd), [(2, A), (2, B), (5, C)])
        self.assertEqual(kinds(cd), [(2, A), (5, B)])
        self.assertEqual([(d.obj_id, d.cls, d.kind) for d in comparison.diffs],
                         [(A, st.ROOT, st.CHANGED_SHOT), (B, st.INDUCED_NONSHOOT, st.LOST_SHOT),
                          (C, st.INDUCED_NONSHOOT, st.OTHER)])
        self.assertEqual(comparison.problems, [])

    def test_non_shoot_machinery_is_unchanged_without_shots(self) -> None:
        raw = ds.rich_observation()
        for u in raw["operators"]:
            u["blood"] = 2
        raw["valid_actions"][A] = {1: None}
        decision, _ = decide(raw)
        self.assertEqual(decision.actions, baseline(raw).actions)
        self.assertEqual(sorted(t for t, _ in kinds(decision)), [1, 1, 5])

    def test_deployment_and_memory_are_unchanged(self) -> None:
        units = [dict(syn.unit(A, ds.RED, 102), blood=2), dict(syn.unit(E1, ds.BLUE, 304), blood=1)]
        raw = ds.play_observation(units, {A: {1: None}}, stage=1, cur_step=0, ended=False)
        for memory in (Memory(), Memory(deployment_sent=True)):
            decision, _ = decide(raw, memory=memory)
            base = baseline(raw, memory)
            self.assertEqual((decision.actions, decision.memory), (base.actions, base.memory))

    def test_an_emitted_shot_is_exactly_a_listed_option(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, MISSILE, 3)]}}, BLOOD)
        decision, _ = decide(raw)
        (action,) = decision.actions
        self.assertEqual(set(action), {"actor", "type", "obj_id", "target_obj_id", "weapon_id"})
        self.assertIn({"target_obj_id": action["target_obj_id"], "weapon_id": action["weapon_id"], "attack_level": 3},
                      raw["valid_actions"][A][2])

    def test_a_gate_rejected_shot_reserves_nothing(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]}, B: {2: [ds.shoot(E2, GUN, 6)]}}, BLOOD)
        real = gate_module.check

        def rejecting(actions, context, router):
            result = real(actions, context, router)
            keep = tuple(a for a in result.accepted if a.get("obj_id") != A)
            gone = tuple(gate_module.Rejection(2, A, "synthetic") for a in result.accepted if a.get("obj_id") == A)
            return gate_module.GateResult(keep, result.rejected + gone)

        with mock.patch.object(gate_module, "check", rejecting):
            decision, policy = decide(raw)
        self.assertEqual(shots(decision), [(B, E2, GUN)])
        self.assertIsNone(policy.records[0].reserved_by_unit)

    def test_unknown_ranking_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            tk.RankedReservationPolicy(ds.costs(), "highest-blood")


def generated_situation(rng: random.Random):
    """Red units with zero to four shoot options over three enemies (some malformed or below level 1), occupation and
    movement; some units on objectives, some executing a move; enemy blood from 0 to 4, sometimes missing."""
    hexes = [505, 202, 707, 303, 808]
    cities = [syn.city(h, flag=rng.choice([-1, -1, 0, 1])) for h in rng.sample(hexes[:3], rng.randint(1, 3))]
    units, valid = [], {}
    for n in range(rng.randint(2, 7)):
        obj = 900101 + n
        moving = rng.random() < 0.15
        units.append(dict(syn.unit(obj, ds.RED, rng.choice(hexes), unit_type=rng.choice([ds.VEHICLE, ds.INFANTRY]),
                                   move_path=(606,) if moving else ()), blood=rng.randint(1, 4)))
        actions = {}
        if not moving and rng.random() < 0.7:
            actions[1] = None
        if rng.random() < 0.5:
            actions[5] = None
        if rng.random() < 0.8:
            options = []
            for _ in range(rng.randint(1, 4)):
                if rng.random() < 0.05:
                    options.append({"target_obj_id": "bad", "weapon_id": GUN, "attack_level": 3})
                else:
                    options.append(ds.shoot(rng.choice((E1, E2, E3)), rng.choice([GUN, MISSILE]), rng.randint(0, 9)))
            actions[2] = options
        valid[obj] = actions
    for i, enemy in enumerate((E1, E2, E3)):
        u = syn.unit(enemy, ds.BLUE, 900 + i)
        if rng.random() < 0.95:
            u["blood"] = rng.randint(0, 4)
        units.append(u)
    return ds.play_observation(units, valid, cities=cities)


class GeneratedCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rng = random.Random(20261007)
        cls.cases = []
        for _ in range(1200):
            raw = generated_situation(rng)
            comparison, bd, cd = compare(raw)
            cls.cases.append((raw, comparison, bd, cd))

    def test_baseline_ranking_reproduces_baseline_v2(self) -> None:
        for raw, _, bd, _ in self.cases:
            self.assertEqual(bd.actions, baseline(raw).actions)

    def test_every_difference_is_explained_and_every_class_occurs(self) -> None:
        seen = {(c, k): 0 for c in st.CLASSES for k in st.KINDS}
        for _, comparison, _, _ in self.cases:
            self.assertEqual(comparison.problems, [])
            for d in comparison.diffs:
                seen[(d.cls, d.kind)] += 1
        for key in ((st.ROOT, st.CHANGED_SHOT), (st.INDUCED_SHOOT, st.CHANGED_SHOT),
                    (st.INDUCED_NONSHOOT, st.LOST_SHOT), (st.INDUCED_NONSHOOT, st.GAINED_SHOT)):
            self.assertGreater(seen[key], 5, key)
        self.assertEqual(sum(seen[(st.UNEXPLAINED, k)] for k in st.KINDS), 0)
        self.assertEqual(sum(seen[(st.INDUCED_SHOOT, k)] for k in st.KINDS if k != st.CHANGED_SHOT), 0)

    def test_no_duplicate_target_and_no_reserved_target(self) -> None:
        for _, comparison, bd, cd in self.cases:
            self.assertEqual((comparison.duplicates_baseline, comparison.duplicates_candidate), (0, 0))
            targets = [a["target_obj_id"] for a in cd.actions if a["type"] == 2]
            self.assertEqual(len(targets), len(set(targets)))

    def test_every_shot_is_listed_and_the_order_is_ascending(self) -> None:
        for raw, _, _, cd in self.cases:
            ids = [a["obj_id"] for a in cd.actions]
            self.assertEqual(ids, sorted(ids))
            for a in cd.actions:
                if a["type"] == 2:
                    listed = [(o.get("target_obj_id"), o.get("weapon_id")) for o in raw["valid_actions"][a["obj_id"]][2]]
                    self.assertIn((a["target_obj_id"], a["weapon_id"]), listed)

    def test_a_root_switch_never_raises_the_chosen_blood(self) -> None:
        roots = 0
        for raw, comparison, _, cd in self.cases:
            blood = {u["obj_id"]: u.get("blood") for u in raw["operators"]}
            for d in comparison.diffs:
                if d.cls == st.ROOT:
                    roots += 1
                    self.assertLess(blood[d.root_choice[0]], blood[d.root_baseline[0]])
                    self.assertNotEqual(d.root_choice[0], d.root_baseline[0])
        self.assertGreater(roots, 50)

    def test_observation_permutation_does_not_change_the_decision(self) -> None:
        rng = random.Random(7)
        for raw, _, _, cd in self.cases[:300]:
            shuffled = copy.deepcopy(raw)
            rng.shuffle(shuffled["operators"])
            for actions in shuffled["valid_actions"].values():
                if actions.get(2):
                    rng.shuffle(actions[2])
            self.assertEqual(decide(shuffled)[0].actions, cd.actions)


class ClassificationTest(unittest.TestCase):
    def record(self, obj, *, engage=(), excluded=(), base=None, ranked=None, blocked=False, before=(), by=None):
        remaining = tuple(c for c in engage if c not in excluded)
        return tk.UnitRecord(obj, 2, tuple(engage), tuple(excluded), remaining, base, ranked, None, blocked,
                             "engage" if ranked else "none", None, frozenset(before), frozenset(), by)

    def test_same_state_and_ranking_with_different_actions_is_unexplained(self) -> None:
        r = self.record(A, engage=((E1, GUN, 3),), base=(E1, GUN, 3), ranked=(E1, GUN, 3))
        shot = {"actor": SEAT, "type": 2, "obj_id": A, "target_obj_id": E1, "weapon_id": GUN}
        out = st.compare_decision(2, [shot], [r], [], [r], PLAY, PLAY)
        self.assertEqual([d.cls for d in out.diffs], [st.UNEXPLAINED])
        self.assertTrue(out.problems)

    def test_root_switch_with_an_identical_emitted_action_is_silent(self) -> None:
        b = self.record(A, engage=((E1, GUN, 8), (E2, GUN, 3)), excluded=((E1, GUN, 8),), base=(E2, GUN, 3),
                        ranked=(E2, GUN, 3), before=(E1,))
        c = self.record(A, engage=((E1, GUN, 8), (E2, GUN, 3)), base=(E1, GUN, 8), ranked=(E2, GUN, 3))
        shot = {"actor": SEAT, "type": 2, "obj_id": A, "target_obj_id": E2, "weapon_id": GUN}
        out = st.compare_decision(2, [shot], [b], [shot], [c], PLAY, PLAY)
        self.assertEqual((out.diffs, out.silent_roots), ([], 1))

    def test_memory_and_non_play_differences_are_problems(self) -> None:
        self.assertTrue(st.compare_decision(2, [], [], [], [], PLAY, Memory()).problems)
        end = {"actor": SEAT, "type": 333}
        self.assertTrue(st.compare_decision(1, [end], [], [], [], PLAY, PLAY).problems)
        self.assertFalse(st.compare_decision(1, [end], [], [end], [], PLAY, PLAY).problems)

    def test_a_shot_at_a_reserved_target_or_an_unlisted_option_is_a_problem(self) -> None:
        c = self.record(A, engage=((E1, GUN, 3),), base=(E1, GUN, 3), ranked=(E1, GUN, 3), before=(E1,))
        b = self.record(A, engage=((E1, GUN, 3),), base=(E1, GUN, 3), ranked=(E1, GUN, 3), before=(E1,))
        shot = {"actor": SEAT, "type": 2, "obj_id": A, "target_obj_id": E1, "weapon_id": GUN}
        self.assertIn("a T11 shot targets a target reserved earlier in the step",
                      st.compare_decision(2, [shot], [b], [shot], [c], PLAY, PLAY).problems)
        other = dict(shot, weapon_id=MISSILE)
        listed_gun_only = self.record(A, engage=((E1, GUN, 3),))
        self.assertIn("a T11 shot is not a listed option",
                      st.compare_decision(2, [other], [listed_gun_only], [other], [listed_gun_only], PLAY, PLAY).problems)

    def test_duplicate_targets_are_counted(self) -> None:
        s1 = {"actor": SEAT, "type": 2, "obj_id": A, "target_obj_id": E1, "weapon_id": GUN}
        s2 = {"actor": SEAT, "type": 2, "obj_id": B, "target_obj_id": E1, "weapon_id": GUN}
        rec = [self.record(A, engage=((E1, GUN, 3),)), self.record(B, engage=((E1, GUN, 3),))]
        out = st.compare_decision(2, [s1, s2], rec, [s1, s2], rec, PLAY, PLAY)
        self.assertEqual((out.duplicates_baseline, out.duplicates_candidate), (1, 1))
        self.assertIn("a duplicate shoot target", out.problems)


def side_with(changed=0, lost=0, gained=0, other=0, label="s"):
    side = st.SideAnalysis("HH", label)
    side.counts["changed_emitted_shots"] = changed
    side.kinds[st.ROOT][st.CHANGED_SHOT] = changed
    side.kinds[st.INDUCED_NONSHOOT][st.LOST_SHOT] = lost
    side.kinds[st.INDUCED_NONSHOOT][st.GAINED_SHOT] = gained
    side.kinds[st.INDUCED_NONSHOOT][st.OTHER] = other
    return side


class DecisionRuleTest(unittest.TestCase):
    def test_opportunity_boundary(self) -> None:
        self.assertTrue(st.opportunity_ok([10, 10, 10, 10]))
        self.assertFalse(st.opportunity_ok([10, 9, 50, 50]))
        self.assertFalse(st.opportunity_ok([40, 40, 40]))          # three side-games
        self.assertFalse(st.opportunity_ok([100, 100, 100, 9]))     # a pooled total never rescues a side-game
        self.assertFalse(st.opportunity_ok([10, 10, 10, 10, 10]))

    def test_changed_shot_counts_are_per_side_game(self) -> None:
        sides = [side_with(changed=n, label=str(i)) for i, n in enumerate((12, 9, 30, 10))]
        self.assertEqual(st.changed_shot_counts(sides), [12, 9, 30, 10])
        self.assertFalse(st.opportunity_ok(st.changed_shot_counts(sides)))

    def test_lost_gained_and_other_differences_are_not_changed_shots(self) -> None:
        side = side_with(changed=10, lost=3, gained=2, other=1)
        self.assertEqual(st.changed_shot_counts([side]), [10])
        self.assertEqual(st.nonshoot(side), 6)

    def test_coupling(self) -> None:
        self.assertFalse(st.coupled([side_with(changed=20), side_with(changed=3)]))
        for kw in ({"lost": 1}, {"gained": 1}, {"other": 1}):
            self.assertTrue(st.coupled([side_with(changed=20), side_with(changed=20, **kw)]), kw)
        root_lost = side_with(changed=20)
        root_lost.kinds[st.ROOT][st.LOST_SHOT] = 1
        self.assertTrue(st.coupled([root_lost]))

    def test_kill_edge(self) -> None:
        self.assertTrue(st.kill_edge(1e-9))
        self.assertFalse(st.kill_edge(0.0))
        self.assertFalse(st.kill_edge(-0.1))
        self.assertFalse(st.kill_edge(None))

    def test_disposition_precedence(self) -> None:
        good = [10, 11, 12, 13]
        cases = [((False, True, False, good, 0.1), "REPLAY_INVALID"),
                 ((True, False, False, good, 0.1), "T11_OFFLINE_MODEL_UNAVAILABLE"),
                 ((True, False, True, [0, 0, 0, 0], None), "T11_OFFLINE_MODEL_UNAVAILABLE"),
                 ((True, True, True, good, 0.1), "T11_OFFLINE_COUPLED_BEHAVIOR"),
                 ((True, True, True, [0, 0, 0, 0], 0.1), "T11_OFFLINE_COUPLED_BEHAVIOR"),
                 ((True, True, False, [9, 11, 12, 13], 0.1), "T11_OFFLINE_INADEQUATE_OPPORTUNITY"),
                 ((True, True, False, good, 0.0), "T11_OFFLINE_NO_KILL_EDGE"),
                 ((True, True, False, good, -0.2), "T11_OFFLINE_NO_KILL_EDGE"),
                 ((True, True, False, good, 0.01), "T11_OFFLINE_PASS")]
        for args, expected in cases:
            self.assertEqual(st.disposition(*args)["disposition"], expected, args)
        self.assertEqual(st.DISPOSITIONS, ("REPLAY_INVALID", "T11_OFFLINE_MODEL_UNAVAILABLE",
                                           "T11_OFFLINE_COUPLED_BEHAVIOR", "T11_OFFLINE_INADEQUATE_OPPORTUNITY",
                                           "T11_OFFLINE_NO_KILL_EDGE", "T11_OFFLINE_PASS"))

    def test_side_analysis_counts_changed_shots_from_comparisons(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]},
                         B: {2: [ds.shoot(E2, GUN, 6), ds.shoot(E3, GUN, 2)]}}, BLOOD)
        comparison, _, cd = compare(raw)
        _, policy = decide(raw)
        side = st.SideAnalysis("HH", "x")
        side.add(0, 5, 2, True, comparison, policy.views)
        side.add(1, 6, 2, True, st.DecisionComparison(), {})
        self.assertEqual((side.counts["changed_emitted_shots"], side.counts["root_changed_shots"],
                          side.counts["induced_changed_shots"]), (2, 1, 1))
        self.assertEqual((side.changed_decisions, side.first_change_k, len(side.changed_shooters)), (1, 0, 2))
        self.assertTrue(side.integrity_ok)
        public = st.public_side(side)
        root = public["root_switches"]
        self.assertEqual((root["n"], root["baseline_target_blood"], root["t11_target_blood"]),
                         (1, {"blood_4": 1}, {"blood_1": 1}))
        self.assertEqual((root["blood_reduction"], root["attack_level_change"], root["targets_available"]),
                         ({"reduction_3": 1}, {"change_-5": 1}, {"targets_2": 1}))
        self.assertEqual((root["attack_level_pairs"], root["t11_level_lower"]), ({"L8_L3": 1}, 1))
        self.assertEqual(public["reservation"]["max_chain"], 2)
        side.add(2, 7, 2, False, st.DecisionComparison(), {})
        self.assertFalse(side.integrity_ok)
        self.assertEqual(side.problems, ["k2: the baseline ranking does not reproduce baseline-v2"])


class KillModelTest(unittest.TestCase):
    def test_the_registered_model_is_unavailable_and_names_its_gaps(self) -> None:
        self.assertFalse(st.kill_model_available())
        self.assertEqual(st.kill_model_gaps(), ["K2", "K4", "K5", "K6"])
        self.assertEqual(len(st.KILL_MODEL_ITEMS), 10)

    def test_the_rule_needs_every_item_documented(self) -> None:
        documented = [dict(i, status=st.DOCUMENTED) for i in st.KILL_MODEL_ITEMS]
        self.assertTrue(st.kill_model_available(documented))
        for status in (st.INFERRED, st.UNDOCUMENTED):
            one = documented[:3] + [dict(documented[3], status=status)] + documented[4:]
            self.assertFalse(st.kill_model_available(one), status)
        self.assertFalse(st.kill_model_available([]))

    def test_quotations_are_checked_verbatim_with_whitespace_normalised(self) -> None:
        texts = {"a.txt": "line one\n  the quoted   words here\nend"}
        item = {"id": "X", "status": st.DOCUMENTED, "quotes": (("a.txt", "the quoted words here"),)}
        self.assertEqual(st.quote_problems([item], texts.__getitem__), [])
        planted = dict(item, quotes=(("a.txt", "the quoted word here"),))
        self.assertEqual(len(st.quote_problems([planted], texts.__getitem__)), 1)
        self.assertEqual(len(st.quote_problems([dict(item, status="maybe")], texts.__getitem__)), 1)


class PrivacyTest(unittest.TestCase):
    def test_sanitizer(self) -> None:
        self.assertTrue(st.public_problems({"obj_id": 1}, ()))
        self.assertTrue(st.public_problems({"note": "unit 900201 shot"}, (900201,)))
        self.assertFalse(st.public_problems({"count": 900201}, (900201,)))  # numeric leaves are masked
        self.assertTrue(st.public_problems({"900201": 1}, (900201,)))

    def test_public_side_carries_no_identities(self) -> None:
        raw = situation({A: {2: [ds.shoot(E1, GUN, 8), ds.shoot(E2, GUN, 3)]},
                         B: {2: [ds.shoot(E2, GUN, 6), ds.shoot(E3, GUN, 2)]}}, BLOOD)
        comparison, _, _ = compare(raw)
        _, policy = decide(raw)
        side = st.SideAnalysis("HH", "x")
        side.add(0, 5, 2, True, comparison, policy.views)
        ids = {A, B, E1, E2, E3, 102, 103, 304, 305, 306, 909}
        self.assertEqual(st.public_problems(st.public_side(side), ids), [])
        self.assertEqual(st.public_problems(st.pooled([side]), ids), [])
        # real unit identifiers include small integers: no public key may be a bare count, blood or level value
        small = set(range(0, 50)) | {-5, -4, -3, -2, -1}
        self.assertEqual(st.public_problems(st.public_side(side), small), [])
        self.assertEqual(st.public_problems(st.pooled([side]), small), [])


if __name__ == "__main__":
    unittest.main()
