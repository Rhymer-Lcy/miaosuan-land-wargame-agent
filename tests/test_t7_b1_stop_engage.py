"""Sprint 32 candidate ``t7-b1-stop-engage-1`` (``experiments/t7_b1_stop_engage.py``) on synthetic states.

Synthetic observations only: these tests check the rule's reading of a seat observation, the action it emits, its
memory and its isolation from ``baseline-v2``. They say nothing about what the engine does with a stop order.
"""

from __future__ import annotations

import ast
import copy
import random
import types
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.evaluation import t7_candidates
from miaosuan_agent.experiments import t7_b1_stop_engage as b1
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
RED, BLUE = 0, 1
SEAT = 11
STEP, END = 100, 2880
#: Written out here rather than read from the module, so that a field dropped from the rule fails a test.
ZERO_FIELDS = ("stop", "move_to_stop_remain_time", "flag_force_stop", "change_state_remain_time",
               "get_on_remain_time", "get_off_remain_time", "weapon_unfold_time", "keep", "move_state", "on_board")


def own(obj, hex_=1010, *, path=(1011, 1012, 1013), speed=0.05, pos=0.5, type_=2, sub=1, weapons=(54, 43), **fields):
    u = {"obj_id": obj, "type": type_, "sub_type": sub, "color": BLUE, "cur_hex": hex_, "move_path": list(path),
         "speed": speed, "cur_pos": pos, "A1": 0, "carry_weapon_ids": list(weapons), "see_enemy_bop_ids": [900],
         "stop": 0, "move_to_stop_remain_time": 0, "flag_force_stop": 0, "change_state_remain_time": 0,
         "get_on_remain_time": 0, "get_off_remain_time": 0, "weapon_unfold_time": 0, "keep": 0, "move_state": 0,
         "on_board": 0, "weapon_unfold_state": 1}
    u.update(fields)
    return u


def enemy(obj=900, hex_=1016, type_=2, color=RED):
    return {"obj_id": obj, "type": type_, "sub_type": 0, "color": color, "cur_hex": hex_, "move_path": []}


def raw(units, listing=None, *, step=STEP, end=END, stage=2, controlled=None):
    ids = [u["obj_id"] for u in units if u.get("color") == BLUE]
    listing = {u["obj_id"]: {10: None} for u in units if u.get("color") == BLUE and u.get("move_path")} \
        if listing is None else listing
    return {"operators": [dict(u) for u in units], "passengers": [], "cities": [],
            "time": {"cur_step": step, "stage": stage, "max_step": end},
            "valid_actions": listing,
            "role_and_grouping_info": {SEAT: {"faction": BLUE, "operators": ids if controlled is None else controlled}}}


def move(obj, route):
    return {"actor": SEAT, "obj_id": obj, "type": 1, "move_path": list(route)}


def stop(obj):
    return {"actor": SEAT, "obj_id": obj, "type": 10}


def decide(units, base=(), memory=(), **kw):
    return b1.decide(raw(units, **kw), SEAT, BLUE, list(base), memory)


def level(units, unit=1, base=(), memory=(), **kw):
    return next(c for c in decide(units, base, memory, **kw).checks if c.unit == unit).level


class TriggerTest(unittest.TestCase):
    def test_trigger_appends_one_exact_stop(self) -> None:
        base = [move(5, (2000, 2001))]
        result = decide([own(1), own(5, 3000, path=()), enemy()], base)
        self.assertEqual(result.stops, (1,))
        self.assertEqual([dict(a) for a in result.actions], base + [stop(1)])
        self.assertEqual(set(result.actions[-1]), {"actor", "obj_id", "type"})
        self.assertEqual(result.memory, ((1, STEP),))
        check = next(c for c in result.checks if c.unit == 1)
        self.assertEqual((check.target, check.distance, check.reach, check.next_hex, check.others, check.steps),
                         (900, 5, 13, 1011, 0, 10))

    def test_several_units_in_ascending_order_after_baseline(self) -> None:
        base = [move(7, (2000,))]
        units = [own(3, 1110, path=(1111, 1112)), own(2, 1210, path=(1211, 1212)), own(7, 3000, path=()), enemy()]
        result = decide(units, base)
        self.assertEqual([dict(a) for a in result.actions], base + [stop(2), stop(3)])
        self.assertEqual(result.memory, ((2, STEP), (3, STEP)))

    def test_not_play_stage_returns_baseline_untouched(self) -> None:
        base = [move(5, (2000,))]
        result = decide([own(1), enemy()], base, stage=1)
        self.assertEqual((list(result.actions), result.stops, result.checks, result.play), (base, (), (), False))

    def test_infantry_light_weapons_reach_three(self) -> None:
        inf = own(1, type_=1, sub=0, weapons=(29,), speed=1 / 144, pos=0.0)
        self.assertEqual(level([inf, enemy(hex_=1014, type_=1)]), b1.TRIGGER)
        self.assertEqual(level([inf, enemy(hex_=1015, type_=1)]), "I_target_in_range")


class LevelTest(unittest.TestCase):
    def test_a_ground_controllable(self) -> None:
        self.assertEqual(level([own(1, type_=3), enemy()]), "A_ground_controllable")
        self.assertEqual(level([own(1), enemy()], controlled=[2]), "A_ground_controllable")
        units = [own(1), enemy()]
        observation = raw(units)
        del observation["role_and_grouping_info"]
        self.assertEqual(next(c for c in b1.decide(observation, SEAT, BLUE, [], ()).checks if c.unit == 1).level,
                         "A_ground_controllable")

    def test_b_no_move_and_fire(self) -> None:
        for fields in ({"A1": 1}, {"A1": None}, {"A1": False}, {"A1": "0"}, {"carry_weapon_ids": [54, 37]},
                       {"carry_weapon_ids": [36]}, {"carry_weapon_ids": "54"}, {"carry_weapon_ids": [54, "43"]}):
            with self.subTest(fields=fields):
                self.assertEqual(level([own(1, **fields), enemy()]), "B_no_move_and_fire")

    def test_c_traversing(self) -> None:
        cases = {"no path": dict(path=()), "waiting": dict(speed=0), "unreadable speed": dict(speed=None),
                 "unreadable progress": dict(pos=1.0)}
        for detail, kw in cases.items():
            with self.subTest(detail=detail):
                check = next(c for c in decide([own(1, **kw), enemy()]).checks if c.unit == 1)
                self.assertEqual((check.level, check.detail), ("C_traversing", detail))
        for kw in (dict(speed=-0.05), dict(speed=True), dict(pos=-0.1), dict(pos=None), dict(path=(1011, "x")),
                   dict(cur_hex=None)):
            with self.subTest(kw=kw):
                self.assertEqual(level([own(1, **kw), enemy()]), "C_traversing")

    def test_d_stop_listed(self) -> None:
        units = [own(1), enemy()]
        self.assertEqual(level(units, listing={1: {1: None}}), "D_stop_listed")
        self.assertEqual(level(units, listing={}), "D_stop_listed")
        self.assertEqual(level(units, listing={1: {10: [{"x": 1}]}}), "D_stop_listed")
        self.assertEqual(level(units, listing={1: {10: None, "10": None}}), "D_stop_listed")
        self.assertEqual(level(units, listing={"1": {"10": None}}), b1.TRIGGER)

    def test_e_no_other_state(self) -> None:
        self.assertEqual(b1.ZERO_FIELDS, ZERO_FIELDS)
        for name in ZERO_FIELDS:
            for value in (1, None, True, "0"):
                with self.subTest(name=name, value=value):
                    self.assertEqual(level([own(1, **{name: value}), enemy()]), "E_no_other_state")
            units = [own(1), enemy()]
            del units[0][name]
            self.assertEqual(level(units), "E_no_other_state")
        for value in (0, None, True):
            self.assertEqual(level([own(1, weapon_unfold_state=value), enemy()]), "E_no_other_state")

    def test_f_route_continues(self) -> None:
        self.assertEqual(level([own(1, path=(1011,)), enemy()]), "F_route_continues")

    def test_g_and_h(self) -> None:
        units = [own(1), enemy()]
        self.assertEqual(level(units, base=[{"actor": SEAT, "obj_id": 1, "type": 2}]), "G_no_baseline_action")
        self.assertEqual(level(units, memory=((1, 50),)), "H_not_stopped_before")
        self.assertEqual(level(units, memory=((2, 50),)), b1.TRIGGER)

    def test_i_target(self) -> None:
        self.assertEqual(level([own(1, see_enemy_bop_ids=[]), enemy()]), "I_target_in_range")
        self.assertEqual(level([own(1, see_enemy_bop_ids=None), enemy()]), "I_target_in_range")
        self.assertEqual(level([own(1), enemy(type_=3)]), "I_target_in_range")
        self.assertEqual(level([own(1), enemy(color=BLUE)]), "I_target_in_range")
        # range against vehicles 13 (weapon 54), against infantry 10 (weapons 54 and 43); measured from the first hex
        # of the path (1011): 1024 is 13 from 1011 and 14 from the current hex 1010.
        self.assertEqual(level([own(1), enemy(hex_=1024)]), b1.TRIGGER)
        self.assertEqual(level([own(1), enemy(hex_=1025)]), "I_target_in_range")
        self.assertEqual(level([own(1), enemy(hex_=1021, type_=1)]), b1.TRIGGER)
        self.assertEqual(level([own(1), enemy(hex_=1022, type_=1)]), "I_target_in_range")
        self.assertEqual(level([own(1, path=(1009, 1008)), enemy(hex_=1022, type_=1)]), "I_target_in_range")
        self.assertEqual(level([own(1, weapons=(99,)), enemy()]), "I_target_in_range")

    def test_j_next_hex_room(self) -> None:
        on_next = own(2, 1011, path=(), speed=0)
        through = own(3, 1110, path=(1111, 1011, 1012))
        waiting = own(4, 1112, path=(1011,), speed=0)
        e = enemy()
        self.assertEqual(level([own(1), on_next, through, e]), b1.TRIGGER)
        self.assertEqual(level([own(1), on_next, through, waiting, e]), "J_next_hex_room")
        self.assertEqual(level([own(1), on_next, through, own(6, 3000, path=()), e],
                               base=[move(6, (3001, 1011))]), "J_next_hex_room")
        self.assertEqual(level([own(1), on_next, through, own(6, 3000, path=()), e],
                               base=[move(6, (3001, 3002))]), b1.TRIGGER)
        # aircraft and enemy units do not count
        self.assertEqual(level([own(1), on_next, through, own(7, 1011, type_=3, path=()), enemy(901, 1011), e]),
                         b1.TRIGGER)

    def test_k_time_left(self) -> None:
        # hex_steps 10 at pos 0.5 and speed 0.05: allowed while STEP + 10 + 75 + 3 <= max_step
        self.assertEqual(level([own(1), enemy()], end=STEP + 88), b1.TRIGGER)
        self.assertEqual(level([own(1), enemy()], end=STEP + 87), "K_time_left")

    def test_hex_steps(self) -> None:
        cases = [(0.05, 0.05, 19), (0.0, 1 / 144, 144), (0.5, 0.05, 10), (0.51, 0.05, 10), (0.49, 0.05, 11),
                 (1 / 60 * 7, 1 / 60, 53), (0.95, 0.05, 1)]
        for pos, speed, steps in cases:
            with self.subTest(pos=pos, speed=speed):
                self.assertEqual(b1.hex_steps({"cur_pos": pos, "speed": speed}), steps)


class MemoryAndCheckTest(unittest.TestCase):
    def test_malformed_memory_raises(self) -> None:
        for memory in (((1,),), ((1, 2), (1, 3)), (("1", 2),), ((1, True),), (5,)):
            with self.subTest(memory=memory):
                with self.assertRaises(ValueError):
                    decide([own(1), enemy()], memory=memory)

    def test_unreadable_time_or_operators_raise(self) -> None:
        observation = raw([own(1), enemy()])
        observation["time"]["max_step"] = None
        with self.assertRaises(ValueError):
            b1.decide(observation, SEAT, BLUE, [], ())
        observation = raw([own(1), enemy()])
        observation["operators"].append({"obj_id": "x"})
        with self.assertRaises(ValueError):
            b1.decide(observation, SEAT, BLUE, [], ())

    def test_own_check(self) -> None:
        observation = raw([own(1), enemy()])
        base = (move(5, (2000,)),)
        good = b1.decide(observation, SEAT, BLUE, base, ())
        b1.own_check(good, observation, SEAT, base)
        bad_results = [
            b1.StopResult((move(5, (2001,)), stop(1)), good.stops, good.checks, True, STEP, good.memory),
            b1.StopResult(base + (dict(stop(1), weapon_id=1),), good.stops, good.checks, True, STEP, good.memory),
            b1.StopResult(base + (stop(2),), good.stops, good.checks, True, STEP, good.memory),
            b1.StopResult(base + (stop(1), stop(1)), good.stops, good.checks, True, STEP, good.memory),
            b1.StopResult(base + (dict(stop(1), actor=1),), good.stops, good.checks, True, STEP, good.memory),
        ]
        for result in bad_results:
            with self.subTest(actions=result.actions):
                with self.assertRaises(ValueError):
                    b1.own_check(result, observation, SEAT, base)

    def test_addon_records(self) -> None:
        observation = raw([own(1), enemy()])
        base = types.SimpleNamespace(actions=(move(5, (2000,)),))
        out = b1.StopEngageAddon(None, None).apply(types.SimpleNamespace(fields=observation), SEAT, BLUE, base, ())
        self.assertEqual([dict(a) for a in out.actions], [move(5, (2000,)), stop(1)])
        self.assertEqual([(c["kind"], c["obj_id"], c["target"], c["hex_steps"]) for c in out.changes],
                         [("added_stop", 1, 900, 10)])
        self.assertIn(("unit stop", 1), out.skipped)
        self.assertEqual(out.addon_memory, ((1, STEP),))

    def test_determinism_under_permutation(self) -> None:
        units = [own(3, 1110, path=(1111, 1112)), own(2, 1210, path=(1211, 1212)), own(4, 1310, speed=0),
                 enemy(), enemy(901, 1113, 1)]
        reference = decide(units)
        rng = random.Random(7)
        for _ in range(20):
            shuffled = copy.deepcopy(units)
            rng.shuffle(shuffled)
            observation = raw(shuffled)
            observation["valid_actions"] = dict(reversed(list(observation["valid_actions"].items())))
            again = b1.decide(observation, SEAT, BLUE, [], ())
            self.assertEqual((again.actions, again.memory), (reference.actions, reference.memory))
            self.assertEqual(sorted(again.checks, key=lambda c: c.unit), sorted(reference.checks, key=lambda c: c.unit))


def policy_observation(step=STEP, extra_unit=None):
    """A full synthetic observation for the real ``baseline-v2``: one moving IFV with a visible enemy in range, one
    idle tank with an objective to go to."""
    mover = dict(own(syn.BLUE_UNIT, 505, path=(506, 507, 508)), sub_type=1, see_enemy_bop_ids=[syn.RED_UNIT])
    idle = dict(own(syn.BLUE_UNIT + 1, 202, path=(), speed=0, weapons=(37,), A1=1), stop=1, sub_type=0)
    foe = enemy(syn.RED_UNIT, 509, 2)
    units = [mover, idle, foe] + ([extra_unit] if extra_unit else [])
    seats = {syn.BLUE_SEAT: syn.seat_record(syn.BLUE_SEAT, BLUE, [mover["obj_id"], idle["obj_id"]], True)}
    listing = {mover["obj_id"]: {10: None}, idle["obj_id"]: {1: None}}
    observation = syn.build_observation(units=units, valid_actions=listing, seats=seats, stage=2, cur_step=step,
                                        cities=[syn.city(808)])
    observation["time"]["max_step"] = END
    return observation


class PolicyTest(unittest.TestCase):
    """The executable policy with the real ``baseline-v2`` on a synthetic observation."""

    def agents(self):
        cand, v2 = b1.StopEngageAgent(), ShootReservationAgent()
        for agent in (cand, v2):
            agent.setup({"seat": syn.BLUE_SEAT, "faction": BLUE, "cost_data": syn.cost_data()})
        return cand, v2

    def test_candidate_is_baseline_plus_one_stop_then_no_repeat(self) -> None:
        cand, v2 = self.agents()
        observation = policy_observation()
        base = [dict(a) for a in v2.step(copy.deepcopy(observation))]
        mine = [dict(a) for a in cand.step(copy.deepcopy(observation))]
        self.assertTrue(any(a["type"] == 1 for a in base))
        self.assertEqual(mine, base + [{"actor": syn.BLUE_SEAT, "obj_id": syn.BLUE_UNIT, "type": 10}])
        trace = cand.last_trace.to_dict()
        self.assertEqual(trace["policy"], b1.CANDIDATE_ID)
        self.assertIsNone(trace[b1.ADDON_NAME]["error"])
        later = policy_observation(step=STEP + 1)
        base = [dict(a) for a in v2.step(copy.deepcopy(later))]
        mine = [dict(a) for a in cand.step(copy.deepcopy(later))]
        self.assertEqual(mine, base)

    def test_wrapper_fails_closed_to_baseline_v2(self) -> None:
        cand, v2 = self.agents()
        observation = policy_observation()
        with mock.patch.object(b1, "check_unit", side_effect=ValueError("planted")):
            mine = [dict(a) for a in cand.step(copy.deepcopy(observation))]
        base = [dict(a) for a in v2.step(copy.deepcopy(observation))]
        self.assertEqual(mine, base)
        self.assertIn("ValueError: planted", cand.last_trace.addon_error)

    def test_reset_clears_memory(self) -> None:
        cand, _ = self.agents()
        cand.step(copy.deepcopy(policy_observation()))
        self.assertEqual(cand.memory.addon, ((syn.BLUE_UNIT, STEP),))
        cand.reset()
        self.assertEqual(cand.memory.addon, ())


class IdentityTest(unittest.TestCase):
    def test_identity_constants(self) -> None:
        self.assertEqual(b1.CANDIDATE_ID, "t7-b1-stop-engage-1")
        self.assertIn("NOT ELIGIBLE FOR PROMOTION", b1.STATUS)
        self.assertEqual((b1.TRANSITION, b1.END_MARGIN, b1.STACK_LIMIT, b1.ROOM_OTHERS), (75, 3, 4, 2))
        self.assertEqual(b1.TANK_GUNS, frozenset({36, 37}))

    def test_weapon_table_equals_the_t7_study(self) -> None:
        self.assertEqual(dict(b1.WEAPON_RANGES), dict(t7_candidates.WEAPON_RANGES))

    def test_no_analysis_import_and_no_randomness(self) -> None:
        tree = ast.parse((ROOT / "src/miaosuan_agent/experiments/t7_b1_stop_engage.py").read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(("." * node.level) + (node.module or ""))
            elif isinstance(node, ast.Import):
                modules.update(a.name for a in node.names)
        self.assertEqual(modules, {"__future__", "collections", "math", "dataclasses", "typing",
                                   ".exploratory_addon"})


if __name__ == "__main__":
    unittest.main()
