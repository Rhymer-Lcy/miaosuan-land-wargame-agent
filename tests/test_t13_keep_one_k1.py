"""Sprint 30 candidate ``t13-keep-one-k1`` (``experiments/t13_keep_one_k1.py``) on synthetic states.

SYNTHETIC inputs: raw seat observations built here (blue is the acting side; the held objective's centre is ``C``),
``baseline-v2`` action lists written by hand, and a test travel relation (``tau`` steps per route hex, ``None`` when a
unit carries no ``tau``) unless a test uses the registered relation over the synthetic cost graph. Covered: the trigger
and each objective outcome; every eligibility level and its boundary; missing transition fields; unheld objectives;
the non-play stage; the selection by travel time, its tie rule and unreadable times; two objectives at one decision;
artillery, aircraft, enemies and passengers; action order and unchanged inputs; malformed observations, non-empty
memory and missing costs through the add-on wrapper (fail closed to ``baseline-v2``); the registered travel relation;
the executable policy with the real ``baseline-v2`` in the held-objective stand-in world; identity and imports.
"""

from __future__ import annotations

import ast
import copy
import random
import types
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision import policy
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.experiments import t13_keep_one_k1 as k1
from miaosuan_agent.experiments.exploratory_addon import AddonMemory
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from tests.fixtures import s30_engine as se
from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
RED, BLUE = 0, 1
INF, VEH, AIR = 1, 2, 3
C, D, E = 1010, 1020, 1030          # objective centres
OFF = 1050                          # a hex that is not an objective


def unit(obj, hex_=C, *, type_=VEH, sub=0, color=BLUE, path=(), speed=0, tau=20, **fields):
    u = {"obj_id": obj, "type": type_, "sub_type": sub, "color": color, "cur_hex": hex_, "move_path": list(path),
         "speed": speed, "stop": 1, "move_to_stop_remain_time": 0, "change_state_remain_time": 0,
         "get_on_remain_time": 0, "get_off_remain_time": 0}
    if tau is not None:
        u["tau"] = tau
    u.update(fields)
    return u


def city(coord, flag=BLUE, value=80):
    return {"coord": coord, "flag": flag, "value": value, "name": "synthetic objective"}


def raw(units, cities=None, stage=2, step=100):
    return {"operators": [dict(u) for u in units], "passengers": [], "cities": cities if cities is not None else [city(C)],
            "time": {"cur_step": step, "stage": stage}}


def move(obj, length=3, start=None, end=None):
    route = [(start or 2000) + i for i in range(length)]
    if end is not None:
        route[-1] = end
    return {"actor": 11, "obj_id": obj, "type": 1, "move_path": route}


def shoot(obj):
    return {"actor": 11, "obj_id": obj, "type": 2, "target_obj_id": 900, "weapon_id": 36}


def occupy(obj):
    return {"actor": 11, "obj_id": obj, "type": 5}


def travel(u, route):
    return None if u.get("tau") is None else u["tau"] * len(route)


def decide(units, actions, cities=None, stage=2):
    return k1.decide(raw(units, cities, stage), BLUE, actions, travel)


def statuses(result):
    return [(c.centre, c.status) for c in result.checks]


class TriggerTest(unittest.TestCase):
    def test_all_departing_by_move_withholds_one(self) -> None:
        actions = [move(1), move(2, length=5), shoot(9)]
        result = decide([unit(1), unit(2), unit(9, OFF)], actions)
        self.assertEqual(result.withheld, (1,))
        self.assertEqual([dict(a) for a in result.actions], [move(1), shoot(9)])
        self.assertEqual(statuses(result), [(C, "withheld")])
        check = result.checks[0]
        self.assertEqual((check.selected, check.index, check.travel), (2, 1, 100))

    def test_a_remaining_occupant_means_no_change(self) -> None:
        for staying in ([], [shoot(3)], [occupy(3)]):
            with self.subTest(staying=staying):
                actions = [move(1), move(2)] + staying
                result = decide([unit(1), unit(2), unit(3)], actions)
                self.assertEqual((result.withheld, statuses(result)), ((), [(C, "holder_remains")]))
                self.assertEqual([dict(a) for a in result.actions], actions)

    def test_a_remaining_occupant_in_a_stop_transition_still_holds(self) -> None:
        result = decide([unit(1), unit(3, move_to_stop_remain_time=40, stop=0)], [move(1)])
        self.assertEqual((result.withheld, statuses(result)), ((), [(C, "holder_remains")]))

    def test_all_occupants_already_moving_is_uncovered(self) -> None:
        result = decide([unit(1, path=[2001], speed=1), unit(2, path=[2001, 2002])], [])
        self.assertEqual((result.withheld, statuses(result)), ((), [(C, "all_moving")]))

    def test_moving_occupant_and_ordered_stationary_occupant(self) -> None:
        result = decide([unit(1, path=[2001], speed=1), unit(2)], [move(2)])
        self.assertEqual((result.withheld, statuses(result)), ((0,), [(C, "withheld")]))
        self.assertEqual(result.actions, ())

    def test_no_occupant(self) -> None:
        result = decide([unit(1, OFF)], [move(1)])
        self.assertEqual((result.withheld, statuses(result)), ((), [(C, "no_centre_occupant")]))

    def test_unheld_objectives_are_ignored(self) -> None:
        for flag in (RED, -1):
            with self.subTest(flag=flag):
                result = decide([unit(1), unit(2)], [move(1), move(2)], cities=[city(C, flag)])
                self.assertEqual((result.withheld, result.checks), ((), ()))

    def test_non_play_stage_changes_nothing(self) -> None:
        actions = [move(1), move(2)]
        result = decide([unit(1), unit(2)], actions, stage=1)
        self.assertEqual((result.play, result.withheld, result.checks), (False, (), ()))
        self.assertEqual([dict(a) for a in result.actions], actions)
        self.assertEqual(k1.skip_counts(result), (("decision not_play_stage", 1),))


class EligibilityTest(unittest.TestCase):
    def level(self, **fields):
        result = decide([unit(1, **fields)], [move(1)])
        return result.checks[0].occupants[0].level, result.checks[0].status, result.withheld

    def test_each_level_and_its_boundary(self) -> None:
        cases = [({"speed": 1}, "A_stationary"), ({"speed": 0.5}, "A_stationary"), ({"speed": 0}, "eligible"),
                 ({"speed": -1}, "eligible"),
                 ({"stop": 0}, "C_no_transition"), ({"move_to_stop_remain_time": 1}, "C_no_transition"),
                 ({"move_to_stop_remain_time": 0}, "eligible"), ({"change_state_remain_time": 1}, "C_no_transition"),
                 ({"get_on_remain_time": 1}, "D_no_transport_transition"),
                 ({"get_off_remain_time": 1}, "D_no_transport_transition"), ({"get_off_remain_time": 0}, "eligible")]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                level, status, withheld = self.level(**fields)
                self.assertEqual(level, expected)
                self.assertEqual(status, "withheld" if expected == "eligible" else "no_eligible_holder")
                self.assertEqual(withheld, (0,) if expected == "eligible" else ())

    def test_missing_fields_count_as_no_transition(self) -> None:
        u = unit(1)
        for name in k1.TRANSITION_FIELDS + ("speed",):
            del u[name]
        result = decide([u], [move(1)])
        self.assertEqual((result.checks[0].occupants[0].level, result.withheld), ("eligible", (0,)))

    def test_route_with_a_move_is_level_b(self) -> None:
        result = decide([unit(1, path=[2001])], [move(1)])
        self.assertEqual(result.checks[0].occupants[0].level, "B_no_route")
        self.assertEqual(result.withheld, ())

    def test_the_move_itself(self) -> None:
        bad = [[move(1), shoot(1)], [{"actor": 11, "obj_id": 1, "type": 1, "move_path": []}],
               [{"actor": 11, "obj_id": 1, "type": 1}], [move(1, end=C)],
               [{"actor": 11, "obj_id": 1, "type": 1, "move_path": [2001, "2002"]}],
               [{"actor": 11, "obj_id": 1, "type": 1, "move_path": [2001, True]}]]
        for actions in bad:
            with self.subTest(actions=actions):
                result = decide([unit(1)], actions)
                self.assertEqual((result.checks[0].occupants[0].level, result.withheld),
                                 ("E_single_departing_move", ()))
                self.assertEqual(result.checks[0].status, "no_eligible_holder")


class SelectionTest(unittest.TestCase):
    def test_longest_time_then_lower_id(self) -> None:
        result = decide([unit(3, tau=30), unit(1, tau=10), unit(2, tau=30)], [move(1), move(2), move(3)])
        self.assertEqual((result.checks[0].selected, result.withheld), (2, (1,)))
        result = decide([unit(3, tau=31), unit(1, tau=10), unit(2, tau=30)], [move(1), move(2), move(3)])
        self.assertEqual(result.checks[0].selected, 3)

    def test_unreadable_times_are_not_ranked(self) -> None:
        result = decide([unit(1, tau=None), unit(2, tau=5)], [move(1, length=9), move(2)])
        self.assertEqual(result.checks[0].selected, 2)
        result = decide([unit(1, tau=None), unit(2, tau=None)], [move(1), move(2)])
        self.assertEqual((statuses(result), result.withheld), ([(C, "no_travel_time")], ()))

    def test_an_ineligible_slower_unit_is_not_selected(self) -> None:
        result = decide([unit(1, tau=99, stop=0), unit(2, tau=5)], [move(1), move(2)])
        self.assertEqual(result.checks[0].selected, 2)

    def test_input_order_does_not_matter(self) -> None:
        units = [unit(i, tau=t) for i, t in ((5, 20), (2, 40), (7, 40), (3, 10))]
        actions = [move(i) for i in (5, 2, 7, 3)]
        rng = random.Random(30)
        for _ in range(12):
            u, a = units[:], actions[:]
            rng.shuffle(u)
            rng.shuffle(a)
            result = decide(u, a)
            self.assertEqual(result.checks[0].selected, 2)
            self.assertEqual([x["obj_id"] for x in result.actions], [x["obj_id"] for x in a if x["obj_id"] != 2])


class ObjectivesAndUnitsTest(unittest.TestCase):
    def test_two_objectives_one_holder_each(self) -> None:
        units = [unit(1), unit(2, D, tau=40), unit(3, D)]
        actions = [move(3), shoot(8), move(1), move(2)]
        result = decide(units, actions, cities=[city(D), city(C), city(E)])
        self.assertEqual(statuses(result), [(C, "withheld"), (D, "withheld"), (E, "no_centre_occupant")])
        self.assertEqual(result.withheld, (2, 3))
        self.assertEqual([dict(a) for a in result.actions], [move(3), shoot(8)])
        records = k1.change_records(result)
        self.assertEqual([(r["kind"], r["objective"], r["obj_id"], r["index"]) for r in records],
                         [("withheld_move", C, 1, 2), ("withheld_move", D, 2, 3)])
        self.assertEqual(k1.skip_counts(result), (("objective no_centre_occupant", 1), ("objective withheld", 2)))

    def test_artillery_counts_and_can_hold(self) -> None:
        result = decide([unit(1, sub=3, tau=50), unit(2)], [move(1), move(2)])
        self.assertEqual(result.checks[0].selected, 1)
        result = decide([unit(1, sub=3), unit(2)], [move(2)])
        self.assertEqual(statuses(result), [(C, "holder_remains")])

    def test_aircraft_enemies_and_passengers_are_not_occupants(self) -> None:
        observation = raw([unit(1), unit(5, type_=AIR), unit(6, color=RED)])
        observation["passengers"] = [unit(7)]
        result = k1.decide(observation, BLUE, [move(1)], travel)
        self.assertEqual([o.unit for o in result.checks[0].occupants], [1])
        self.assertEqual(result.withheld, (0,))

    def test_inputs_are_not_modified(self) -> None:
        observation = raw([unit(1), unit(2)])
        actions = [move(1), move(2)]
        before = copy.deepcopy((observation, actions))
        k1.decide(observation, BLUE, actions, travel)
        self.assertEqual((observation, actions), before)

    def test_malformed_cities_raise(self) -> None:
        for cities in (None, "x", [{"coord": "1010", "flag": BLUE}], [7]):
            with self.subTest(cities=cities):
                observation = raw([unit(1)])
                if cities is None:
                    del observation["cities"]
                else:
                    observation["cities"] = cities
                with self.assertRaises(ValueError):
                    k1.decide(observation, BLUE, [move(1)], travel)


COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")


class AddonTest(unittest.TestCase):
    def addon(self):
        return k1.K1Addon(COSTS, None)

    def test_the_registered_travel_relation(self) -> None:
        travel_ = k1.router_travel(Router(COSTS))
        u = {"type": VEH, "move_state": 0, "basic_speed": 36, "cur_hex": 202}
        self.assertEqual(travel_(u, [203, 204, 205]), 3 * 20)
        self.assertEqual(travel_(dict(u, basic_speed=18), [203, 204]), 2 * 40)
        self.assertIsNone(travel_(dict(u, basic_speed=None), [203]))
        self.assertIsNone(travel_(u, [205]))          # not a neighbour of the current hex
        self.assertIsNone(travel_(dict(u, type=4), [203]))
        self.assertIsNone(travel_(u, []))

    def test_result_changes_skips_and_memory(self) -> None:
        observation = raw([dict(unit(1), basic_speed=36, move_state=0, cur_hex=202),
                           dict(unit(2), basic_speed=18, move_state=0, cur_hex=202)], cities=[city(202)])
        base = types.SimpleNamespace(actions=({"actor": 11, "obj_id": 1, "type": 1, "move_path": [203]},
                                              {"actor": 11, "obj_id": 2, "type": 1, "move_path": [203]}))
        out = self.addon().apply(types.SimpleNamespace(fields=observation), 11, BLUE, base, ())
        self.assertEqual([a["obj_id"] for a in out.actions], [1])
        self.assertEqual([(c["obj_id"], c["travel"], c["objective"]) for c in out.changes], [(2, 40, 202)])
        self.assertEqual((out.skipped, out.addon_memory), ((("objective withheld", 1),), ()))

    def test_failures_raise(self) -> None:
        observation = types.SimpleNamespace(fields=raw([unit(1)]))
        base = types.SimpleNamespace(actions=(move(1),))
        with self.assertRaises(ValueError):
            self.addon().apply(observation, 11, BLUE, base, ((0, 1),))
        with self.assertRaises(RuntimeError):
            k1.K1Addon(None, None).apply(observation, 11, BLUE, base, ())

    def test_wrapper_fails_closed_to_baseline_v2(self) -> None:
        """An error inside the rule (here a planted one) yields baseline-v2's decision and a recorded error."""
        env = se.HeldEnv()
        env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
        state, _ = env.step([{"actor": 1, "type": 333}, {"actor": 11, "type": 333}])
        blue = copy.deepcopy(state[se.BLUE])
        agent = k1.K1Agent()
        agent.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        v2 = ShootReservationAgent()
        v2.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        with mock.patch.object(k1, "held_centres", side_effect=ValueError("planted")):
            mine = [dict(a) for a in agent.step(copy.deepcopy(blue))]
        base = [dict(a) for a in v2.step(copy.deepcopy(blue))]
        self.assertEqual(mine, base)
        self.assertEqual(len([a for a in base if a["type"] == 1]), 3)
        self.assertIn("ValueError: planted", agent.last_trace.addon_error)


def play_first_decisions(n: int, **options):
    env = se.HeldEnv(**options)
    state = env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
    blue, v2 = k1.K1Agent(), ShootReservationAgent()
    for agent in (blue, v2):
        agent.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
    red = ShootReservationAgent()
    red.setup({"seat": 1, "faction": se.RED, "cost_data": syn.cost_data()})
    rows = []
    for _ in range(n):
        observation = copy.deepcopy(state[se.BLUE])
        base = [dict(a) for a in v2.step(copy.deepcopy(observation))]
        mine = [dict(a) for a in blue.step(copy.deepcopy(observation))]
        rows.append((observation, base, mine, blue.last_trace))
        state, done = env.step(mine + [dict(a) for a in red.step(copy.deepcopy(state[se.RED]))])
        if done:
            break
    return rows


class PolicyTest(unittest.TestCase):
    """The executable policy with the real ``baseline-v2`` in the held-objective stand-in world: ``baseline-v2`` orders
    the three tanks off the held objective; the candidate keeps the slowest (T2) and nothing else changes."""

    def test_the_first_play_decision_keeps_the_slowest_tank(self) -> None:
        rows = play_first_decisions(4)
        play = [(o, b, m, t) for o, b, m, t in rows if o["time"]["stage"] == 2]
        observation, base, mine, trace = play[0]
        self.assertEqual(sorted(a["obj_id"] for a in base if a["type"] == 1), [se.T1, se.T2, se.T3])
        self.assertEqual(mine, [a for a in base if a["obj_id"] != se.T2])
        self.assertIsNone(trace.addon_error)
        self.assertEqual(len(trace.changes), 1)

    def test_the_holder_stays_and_nothing_is_withheld_when_not_held(self) -> None:
        rows = play_first_decisions(60)
        play = [r for r in rows if r[0]["time"]["stage"] == 2]
        for observation, base, mine, _ in play[1:]:
            hexes = {u["obj_id"]: u["cur_hex"] for u in observation["operators"]}
            self.assertEqual(hexes[se.T2], se.NEAR)
            self.assertNotIn(se.T2, [a["obj_id"] for a in mine if a["type"] == 1])
        rows = play_first_decisions(6, held=False)
        flags = [next(c["flag"] for c in r[0]["cities"] if c["coord"] == se.NEAR) for r in rows]
        unheld = [r for r, flag in zip(rows, flags) if flag != se.BLUE]
        self.assertEqual(len(unheld), 2)                                     # deployment, then the occupation
        for observation, base, mine, trace in unheld:
            self.assertEqual(mine, base)
        self.assertIn(5, [a["type"] for r in unheld for a in r[1]])          # blue occupies NEAR first
        first_held = rows[flags.index(se.BLUE)]
        self.assertEqual(first_held[2], [a for a in first_held[1] if a["obj_id"] != se.T2])

    def test_reset(self) -> None:
        agent = k1.K1Agent()
        agent.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        agent.reset()
        self.assertEqual(agent.memory, AddonMemory())


class IdentityTest(unittest.TestCase):
    def test_identity_and_status(self) -> None:
        self.assertEqual((k1.CANDIDATE_ID, k1.ADDON_NAME), ("t13-keep-one-k1", "t13_keep_one_k1"))
        self.assertEqual(k1.K1Policy.identity, k1.CANDIDATE_ID)
        self.assertNotIn(k1.CANDIDATE_ID, policy.POLICIES)
        self.assertIn("NOT ELIGIBLE FOR PROMOTION", k1.STATUS)
        self.assertEqual(k1.ELIGIBILITY, ("A_stationary", "B_no_route", "C_no_transition",
                                          "D_no_transport_transition", "E_single_departing_move"))
        self.assertEqual(k1.OBJECTIVE_STATUS, ("no_centre_occupant", "holder_remains", "all_moving",
                                               "no_eligible_holder", "no_travel_time", "withheld"))

    def test_levels_a_to_d_restate_sprint28s_idle_levels(self) -> None:
        from miaosuan_agent.experiments import t12_dispersion_shadow as t12
        self.assertEqual(k1.ELIGIBILITY[:4], t12.IDLE_LEVELS[:4])
        self.assertEqual(k1.TRANSITION_FIELDS, t12.TRANSITION_FIELDS)
        cases = [{}, {"speed": 1}, {"move_path": [1]}, {"stop": 0}, {"move_to_stop_remain_time": 3},
                 {"change_state_remain_time": 2}, {"get_on_remain_time": 1}, {"get_off_remain_time": 4}]
        for fields in cases:
            u = dict(unit(1), **fields)
            theirs = t12.idle_level(u, {k: u.get(k) for k in t12.TRANSITION_FIELDS}, {1: (1,)}, 1)
            mine = k1.eligibility(u, [(0, move(1))], C)
            self.assertEqual(mine, "eligible" if theirs == "F_no_baseline_move" else theirs, fields)

    def test_imports_are_the_router_the_free_flow_relation_and_the_wrapper_only(self) -> None:
        text = (ROOT / "src" / "miaosuan_agent" / "experiments" / "t13_keep_one_k1.py").read_text(encoding="utf-8")
        found = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                found.add(("." * node.level) + (node.module or ""))
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
        self.assertEqual(found, {"__future__", "collections", "dataclasses", "typing", "..decision.routing",
                                 ".exploratory_addon", ".t9_batch"})


if __name__ == "__main__":
    unittest.main()
