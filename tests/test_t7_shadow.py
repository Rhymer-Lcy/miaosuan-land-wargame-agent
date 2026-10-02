"""T7 design study: the offline shadow of ``t7-idle-concealment`` on synthetic observations."""

from __future__ import annotations

import ast
import copy
import random
import unittest
from pathlib import Path

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import Memory
from miaosuan_agent.experiments import t7_idle_concealment as sh
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import synthetic as syn

SEAT, OWN, ENEMY = syn.RED_SEAT, 0, 1
COSTS = MoveCosts.from_raw(syn.cost_data(), Origin.ENGINE)


def unit(obj_id, hex_, *, color=OWN, unit_type=2, move_state=0, stop=1, path=(), cs=0.0, mts=0.0, wut=0.0, keep=0):
    return {"obj_id": obj_id, "color": color, "type": unit_type, "sub_type": 1, "cur_hex": hex_,
            "move_state": move_state, "stop": stop, "move_path": list(path), "speed": 0.0,
            "change_state_remain_time": cs, "move_to_stop_remain_time": mts, "weapon_unfold_time": wut,
            "get_on_remain_time": 0.0, "get_off_remain_time": 0.0, "weapon_unfold_state": 1, "keep": keep, "tire": 0,
            "A1": 0, "basic_speed": 36, "blood": 1, "passenger_ids": []}


CONCEAL_OPTIONS = [{"target_state": 4}, {"target_state": 5}]


def raw(units, valid, *, stage=2, cur_step=100):
    own = [u["obj_id"] for u in units if u["color"] == OWN]
    seats = {SEAT: syn.seat_record(SEAT, OWN, own, True)}
    obs = syn.build_observation(units=units, valid_actions=valid, seats=seats, stage=stage, cur_step=cur_step,
                                cities=[syn.city(505, flag=-1)])
    return obs


def decide(obs, memory=None, shadow=None):
    shadow = shadow or sh.IdleConcealmentShadow(COSTS)
    return shadow.decide(Observation.from_raw(obs, Origin.ENGINE), SEAT, OWN, memory or sh.ShadowMemory())


def v2(obs, memory=None):
    return ShootReservationPolicy(COSTS).decide(Observation.from_raw(obs, Origin.ENGINE), SEAT, OWN, memory or Memory())


class Trigger(unittest.TestCase):
    def test_idle_units_are_concealed_and_baseline_actions_are_kept(self):
        obs = raw([unit(1, 303), unit(2, 304), unit(3, 102)],
                  {1: {6: CONCEAL_OPTIONS}, 2: {6: CONCEAL_OPTIONS}, 3: {1: None, 6: CONCEAL_OPTIONS}})
        decision = decide(obs)
        base = v2(obs)
        self.assertEqual(list(decision.baseline.actions), list(base.actions))
        self.assertEqual(len(base.actions), 1)
        self.assertEqual(base.actions[0]["obj_id"], 3)
        self.assertEqual(list(decision.actions[:1]), list(base.actions))
        self.assertEqual(list(decision.added), [{"actor": SEAT, "obj_id": 1, "type": 6, "target_state": 4},
                                                {"actor": SEAT, "obj_id": 2, "type": 6, "target_state": 4}])
        self.assertEqual(dict(decision.memory.last_order), {1: 100, 2: 100})

    def test_without_a_trigger_the_shadow_equals_baseline_v2(self):
        obs = raw([unit(1, 303), unit(9, 808, color=ENEMY), unit(3, 102)], {1: {6: CONCEAL_OPTIONS}, 3: {1: None}})
        decision = decide(obs)
        self.assertEqual(list(decision.actions), list(v2(obs).actions))
        self.assertEqual(decision.added, ())
        self.assertEqual(dict(decision.skipped), {"an enemy is seen": 1})

    def test_refusals_by_reason(self):
        cases = {
            "in a transition": unit(1, 303, cs=12.0),
            "not stopped": unit(1, 303, stop=0, mts=0.0),
            "has a move path": unit(1, 303, path=[304]),
            "suppressed": unit(1, 303, keep=1),
            "contradictory: concealment listed for a concealed unit": unit(1, 303, move_state=4),
            "not a ground unit": dict(unit(1, 303), type=3),
        }
        for reason, u in cases.items():
            with self.subTest(reason):
                decision = decide(raw([u], {1: {6: CONCEAL_OPTIONS}}))
                self.assertEqual(decision.added, ())
                self.assertEqual(dict(decision.skipped), {reason: 1})
        stopping = decide(raw([unit(1, 303, stop=0, mts=40.0)], {1: {6: CONCEAL_OPTIONS}}))
        self.assertEqual(dict(stopping.skipped), {"in a transition": 1})
        unfolding = decide(raw([unit(1, 303, wut=10.0)], {1: {6: CONCEAL_OPTIONS}}))
        self.assertEqual(dict(unfolding.skipped), {"in a transition": 1})

    def test_unavailable_or_malformed_options(self):
        for valid, reason in (({}, "change state not listed"), ({6: [{"target_state": 5}]}, "concealment not listed"),
                              ({6: [{"target_state": "4"}, {"x": 1}]}, "malformed change-state option"),
                              ({6: None}, "concealment not listed")):
            with self.subTest(reason=reason, valid=valid):
                decision = decide(raw([unit(1, 303)], {1: valid}))
                self.assertEqual(dict(decision.skipped), {reason: 1})
        mixed = decide(raw([unit(1, 303)], {1: {6: [{"target_state": "4"}, {"target_state": 4}]}}))
        self.assertEqual(len(mixed.added), 1)

    def test_missing_fields_fail_closed(self):
        for name in sh.TRANSITION_FIELDS + ("move_state", "stop", "move_path", "keep"):
            with self.subTest(name):
                u = unit(1, 303)
                del u[name]
                decision = decide(raw([u], {1: {6: CONCEAL_OPTIONS}}))
                self.assertEqual(decision.added, ())
                (reason, n), = decision.skipped
                self.assertIn(name, reason)
                self.assertEqual(n, 1)
        u = unit(1, 303)
        u["keep"] = True
        self.assertEqual(dict(decide(raw([u], {1: {6: CONCEAL_OPTIONS}})).skipped), {"missing or malformed keep": 1})

    def test_deployment_stage_adds_nothing(self):
        decision = decide(raw([unit(1, 303)], {1: {6: CONCEAL_OPTIONS}}, stage=1, cur_step=0))
        self.assertEqual(decision.added, ())


class MemoryAndRepeats(unittest.TestCase):
    def test_repeat_window_and_duplicate_observations(self):
        obs = raw([unit(1, 303)], {1: {6: CONCEAL_OPTIONS}}, cur_step=100)
        first = decide(obs)
        again = decide(obs, first.memory)
        self.assertEqual(again.added, ())
        self.assertEqual(dict(again.skipped), {"ordered within the repeat window": 1})
        later = raw([unit(1, 303)], {1: {6: CONCEAL_OPTIONS}}, cur_step=174)
        self.assertEqual(decide(later, first.memory).added, ())
        last = raw([unit(1, 303)], {1: {6: CONCEAL_OPTIONS}}, cur_step=175)
        self.assertEqual(len(decide(last, first.memory).added), 1)

    def test_fresh_memory_orders_at_once_and_vanished_units_are_harmless(self):
        memory = sh.ShadowMemory(last_order=((77, 90),))
        decision = decide(raw([unit(1, 303)], {1: {6: CONCEAL_OPTIONS}}, cur_step=100), memory)
        self.assertEqual(len(decision.added), 1)
        self.assertEqual(dict(decision.memory.last_order), {1: 100, 77: 90})


class OwnCheckAndDeterminism(unittest.TestCase):
    def test_own_check(self):
        listed = {1: {6: CONCEAL_OPTIONS}}
        good = {"actor": SEAT, "obj_id": 1, "type": 6, "target_state": 4}
        self.assertIsNone(sh.own_check(good, listed, []))
        self.assertEqual(sh.own_check(dict(good, extra=1), listed, []), "key set differs")
        self.assertEqual(sh.own_check(dict(good, target_state=5), listed, []), "not a concealment order")
        self.assertEqual(sh.own_check(good, {1: {6: [{"target_state": 5}]}}, []), "option not listed for the unit")
        self.assertEqual(sh.own_check(good, listed, [{"obj_id": 1, "type": 1}]), "unit already has an action")

    def test_own_check_backs_up_the_trigger(self):
        saved = sh.refusal
        try:
            sh.refusal = lambda *args: None  # a defective trigger that accepts every unit
            decision = decide(raw([unit(1, 303), unit(2, 304), unit(3, 102)],
                                  {1: {6: [{"target_state": 5}]}, 2: {}, 3: {1: None, 6: CONCEAL_OPTIONS}}))
        finally:
            sh.refusal = saved
        self.assertEqual(decision.added, ())
        self.assertEqual(dict(decision.skipped), {"own check: option not listed for the unit": 2})
        self.assertEqual([a["obj_id"] for a in decision.actions], [3])

    def test_permutations_do_not_change_decisions(self):
        units = [unit(i, 300 + i) for i in range(1, 7)] + [unit(9, 909, color=ENEMY)]
        valid = {i: {6: list(CONCEAL_OPTIONS)} for i in range(1, 7)}
        valid[3][1] = None
        base_obs = raw([u for u in units if u["color"] == OWN], valid)
        reference = decide(base_obs)
        rng = random.Random(7)
        for _ in range(10):
            obs = copy.deepcopy(base_obs)
            rng.shuffle(obs["operators"])
            for actions in obs["valid_actions"].values():
                if actions.get(6):
                    rng.shuffle(actions[6])
            items = list(obs["valid_actions"].items())
            rng.shuffle(items)
            obs["valid_actions"] = dict(items)
            other = decide(obs)
            self.assertEqual(list(other.actions), list(reference.actions))
            self.assertEqual(other.skipped, reference.skipped)

    def test_the_shadow_reads_no_evaluation_or_all_seeing_code(self):
        source = Path(sh.__file__).read_text(encoding="utf-8")
        imports = [node for node in ast.walk(ast.parse(source)) if isinstance(node, (ast.Import, ast.ImportFrom))]
        modules = {(node.module or "") for node in imports if isinstance(node, ast.ImportFrom)}
        self.assertEqual({m for m in modules if m and not m.startswith("__")},
                         {"boundary", "decision", "decision.policy", "shoot_reservation", "dataclasses", "typing"})
        self.assertFalse(any("evaluation" in m for m in modules))
        self.assertNotIn("global_observation", source)

    def test_not_registered_as_a_policy(self):
        from miaosuan_agent.decision.policy import POLICIES
        self.assertNotIn(sh.SHADOW_ID, POLICIES)


if __name__ == "__main__":
    unittest.main()
