"""Sprint 31 candidate ``t13-keep-one-k2`` (``experiments/t13_keep_one_k2.py``) on synthetic states.

The classes from ``TriggerTest`` to ``IdentityTest`` are Sprint 30's K1 tests carried over mechanically to the K2 copy of
the rule (module alias, class names, identity strings and the level C label changed; the comparison with Sprint 28's
protocol now covers levels A, B and D, whose names K2 keeps). They show that K2 behaves as K1 wherever no stop
transition is involved. ``SettlingTest``, ``OnlyChangeTest`` and ``SettlingWorldTest`` cover the K2 change: the
documented post-arrival stop transition at its boundaries, every missing or inconsistent field, a deferred stop order,
state and transport transitions during settling, routes and speed; that level C is the only code difference from K1;
and the arrival case in a stand-in world that models the transition (``tests/fixtures/s31_engine.py``), where the
holder stays through its transition and after it.
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
from miaosuan_agent.experiments import t13_keep_one_k2 as k2
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
    return k2.decide(raw(units, cities, stage), BLUE, actions, travel)


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
        self.assertEqual(k2.skip_counts(result), (("decision not_play_stage", 1),))


class EligibilityTest(unittest.TestCase):
    def level(self, **fields):
        result = decide([unit(1, **fields)], [move(1)])
        return result.checks[0].occupants[0].level, result.checks[0].status, result.withheld

    def test_each_level_and_its_boundary(self) -> None:
        cases = [({"speed": 1}, "A_stationary"), ({"speed": 0.5}, "A_stationary"), ({"speed": 0}, "eligible"),
                 ({"speed": -1}, "eligible"),
                 ({"stop": 0}, "C_no_other_transition"), ({"move_to_stop_remain_time": 1}, "C_no_other_transition"),
                 ({"move_to_stop_remain_time": 0}, "eligible"), ({"change_state_remain_time": 1}, "C_no_other_transition"),
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
        for name in k2.TRANSITION_FIELDS + ("speed",):
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
        records = k2.change_records(result)
        self.assertEqual([(r["kind"], r["objective"], r["obj_id"], r["index"]) for r in records],
                         [("withheld_move", C, 1, 2), ("withheld_move", D, 2, 3)])
        self.assertEqual(k2.skip_counts(result), (("objective no_centre_occupant", 1), ("objective withheld", 2)))

    def test_artillery_counts_and_can_hold(self) -> None:
        result = decide([unit(1, sub=3, tau=50), unit(2)], [move(1), move(2)])
        self.assertEqual(result.checks[0].selected, 1)
        result = decide([unit(1, sub=3), unit(2)], [move(2)])
        self.assertEqual(statuses(result), [(C, "holder_remains")])

    def test_infantry_counts_and_can_hold(self) -> None:
        result = decide([unit(1, type_=INF, tau=144), unit(2)], [move(1), move(2)])
        self.assertEqual((result.checks[0].selected, result.withheld), (1, (0,)))
        result = decide([unit(1, type_=INF), unit(2)], [move(2)])
        self.assertEqual(statuses(result), [(C, "holder_remains")])

    def test_aircraft_enemies_and_passengers_are_not_occupants(self) -> None:
        observation = raw([unit(1), unit(5, type_=AIR), unit(6, color=RED)])
        observation["passengers"] = [unit(7)]
        result = k2.decide(observation, BLUE, [move(1)], travel)
        self.assertEqual([o.unit for o in result.checks[0].occupants], [1])
        self.assertEqual(result.withheld, (0,))

    def test_inputs_are_not_modified(self) -> None:
        observation = raw([unit(1), unit(2)])
        actions = [move(1), move(2)]
        before = copy.deepcopy((observation, actions))
        k2.decide(observation, BLUE, actions, travel)
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
                    k2.decide(observation, BLUE, [move(1)], travel)


COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")


class AddonTest(unittest.TestCase):
    def addon(self):
        return k2.K2Addon(COSTS, None)

    def test_the_registered_travel_relation(self) -> None:
        travel_ = k2.router_travel(Router(COSTS))
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
            k2.K2Addon(None, None).apply(observation, 11, BLUE, base, ())

    def test_wrapper_fails_closed_to_baseline_v2(self) -> None:
        """An error inside the rule (here a planted one) yields baseline-v2's decision and a recorded error."""
        env = se.HeldEnv()
        env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
        state, _ = env.step([{"actor": 1, "type": 333}, {"actor": 11, "type": 333}])
        blue = copy.deepcopy(state[se.BLUE])
        agent = k2.K2Agent()
        agent.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        v2 = ShootReservationAgent()
        v2.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        with mock.patch.object(k2, "held_centres", side_effect=ValueError("planted")):
            mine = [dict(a) for a in agent.step(copy.deepcopy(blue))]
        base = [dict(a) for a in v2.step(copy.deepcopy(blue))]
        self.assertEqual(mine, base)
        self.assertEqual(len([a for a in base if a["type"] == 1]), 3)
        self.assertIn("ValueError: planted", agent.last_trace.addon_error)


def play_first_decisions(n: int, **options):
    env = se.HeldEnv(**options)
    state = env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
    blue, v2 = k2.K2Agent(), ShootReservationAgent()
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
        agent = k2.K2Agent()
        agent.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        agent.reset()
        self.assertEqual(agent.memory, AddonMemory())


class IdentityTest(unittest.TestCase):
    def test_identity_and_status(self) -> None:
        self.assertEqual((k2.CANDIDATE_ID, k2.ADDON_NAME), ("t13-keep-one-k2", "t13_keep_one_k2"))
        self.assertEqual(k2.K2Policy.identity, k2.CANDIDATE_ID)
        self.assertNotIn(k2.CANDIDATE_ID, policy.POLICIES)
        self.assertIn("NOT ELIGIBLE FOR PROMOTION", k2.STATUS)
        self.assertEqual(k2.ELIGIBILITY, ("A_stationary", "B_no_route", "C_no_other_transition",
                                          "D_no_transport_transition", "E_single_departing_move"))
        self.assertEqual(k2.OBJECTIVE_STATUS, ("no_centre_occupant", "holder_remains", "all_moving",
                                               "no_eligible_holder", "no_travel_time", "withheld"))

    def test_levels_a_to_d_restate_sprint28s_idle_levels(self) -> None:
        """Against Sprint 28's registered protocol (its frozen identity test forbids other files from naming its shadow
        module): the same first four level names in the same order, the same transition fields, and each level's
        boundary as Sprint 28's registration defines it."""
        import json
        protocol = json.loads((ROOT / "evaluation" / "s28-t12-o1" / "protocol.json").read_text(encoding="utf-8"))
        levels = protocol["shadow"]["idle_levels_in_order"]
        self.assertEqual([k2.ELIGIBILITY[i] for i in (0, 1, 3)], [levels[i] for i in (0, 1, 3)])
        self.assertEqual((levels[2], k2.ELIGIBILITY[2]), ("C_no_transition", "C_no_other_transition"))
        self.assertEqual(list(k2.TRANSITION_FIELDS), protocol["shadow"]["transition_fields"])
        cases = [({}, "eligible"), ({"speed": 1}, "A_stationary"), ({"move_path": [1]}, "B_no_route"),
                 ({"stop": 0}, "C_no_other_transition"), ({"move_to_stop_remain_time": 3}, "C_no_other_transition"),
                 ({"change_state_remain_time": 2}, "C_no_other_transition"),
                 ({"get_on_remain_time": 1}, "D_no_transport_transition"),
                 ({"get_off_remain_time": 4}, "D_no_transport_transition")]
        for fields, expected in cases:
            self.assertEqual(k2.eligibility(dict(unit(1), **fields), [(0, move(1))], C), expected, fields)

    def test_imports_are_the_router_the_free_flow_relation_and_the_wrapper_only(self) -> None:
        text = (ROOT / "src" / "miaosuan_agent" / "experiments" / "t13_keep_one_k2.py").read_text(encoding="utf-8")
        found = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                found.add(("." * node.level) + (node.module or ""))
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
        self.assertEqual(found, {"__future__", "collections", "dataclasses", "typing", "..decision.routing",
                                 ".exploratory_addon", ".t9_batch"})


# ------------------------------------------------------------------------------------------------
# the K2 change


def settling_unit(obj, hex_=C, **fields):
    """A unit in the documented post-arrival stop transition (stop 0, timer positive, no other transition)."""
    return unit(obj, hex_, **{**dict(stop=0, move_to_stop_remain_time=74, flag_force_stop=0), **fields})


class SettlingTest(unittest.TestCase):
    def level(self, u):
        result = decide([u], [move(u["obj_id"])])
        return result.checks[0].occupants[0].level, result.withheld

    def test_the_settling_holder_is_eligible_and_withheld(self) -> None:
        result = decide([settling_unit(1), settling_unit(2, tau=40)], [move(1), move(2)])
        self.assertEqual([o.level for o in result.checks[0].occupants], ["eligible", "eligible"])
        self.assertEqual((result.checks[0].selected, result.withheld, statuses(result)), (2, (1,), [(C, "withheld")]))
        self.assertEqual([dict(a) for a in result.actions], [move(1)])

    def test_timer_boundaries(self) -> None:
        for timer, expected in ((1, "eligible"), (74, "eligible"), (75, "eligible"), (74.0, "eligible"),
                                (76, "C_no_other_transition"), (0, "C_no_other_transition"),
                                (-1, "C_no_other_transition"), ("40", "C_no_other_transition"),
                                (None, "C_no_other_transition"), (True, "C_no_other_transition")):
            with self.subTest(timer=timer):
                level, withheld = self.level(settling_unit(1, move_to_stop_remain_time=timer))
                self.assertEqual(level, expected)
                self.assertEqual(withheld, (0,) if expected == "eligible" else ())

    def test_each_settle_field_missing_fails_closed(self) -> None:
        self.assertEqual(k2.SETTLE_FIELDS, ("speed", "stop", "move_to_stop_remain_time", "flag_force_stop",
                                            "change_state_remain_time", "get_on_remain_time", "get_off_remain_time"))
        for name in k2.SETTLE_FIELDS:
            with self.subTest(missing=name):
                u = settling_unit(1)
                del u[name]
                self.assertEqual(self.level(u), ("C_no_other_transition", ()))

    def test_inconsistent_or_other_transitions_fail_closed(self) -> None:
        for fields in ({"stop": 1, "move_to_stop_remain_time": 40}, {"flag_force_stop": 1},
                       {"move_to_stop_remain_time": 0}, {"speed": -1}, {"stop": False}, {"stop": 0.5},
                       {"change_state_remain_time": 3}, {"get_on_remain_time": 2}, {"get_off_remain_time": 2},
                       {"change_state_remain_time": -1}, {"get_on_remain_time": -1}, {"get_off_remain_time": -1}):
            with self.subTest(fields=fields):
                self.assertEqual(self.level(settling_unit(1, **fields)), ("C_no_other_transition", ()))

    def test_route_and_speed_still_exclude(self) -> None:
        self.assertEqual(self.level(settling_unit(1, path=[2001])), ("B_no_route", ()))
        self.assertEqual(self.level(settling_unit(1, speed=1)), ("A_stationary", ()))

    def test_a_settled_unit_keeps_k1s_reading(self) -> None:
        self.assertEqual(self.level(unit(1)), ("eligible", (0,)))
        self.assertEqual(self.level(unit(1, change_state_remain_time=2)), ("C_no_other_transition", ()))
        u = unit(1)
        del u["stop"], u["move_to_stop_remain_time"]
        self.assertEqual(self.level(u), ("eligible", (0,)))

    def test_collective_departure_ties_and_one_holder(self) -> None:
        units = [settling_unit(i) for i in (4, 2, 3)] + [unit(9, path=[2001], speed=1)]
        result = decide(units, [move(4), move(2), move(3)])
        self.assertEqual((result.checks[0].selected, len(result.withheld)), (2, 1))
        self.assertEqual([a["obj_id"] for a in result.actions], [4, 3])

    def test_a_settling_occupant_without_a_move_remains(self) -> None:
        result = decide([settling_unit(1), settling_unit(2)], [move(1)])
        self.assertEqual((statuses(result), result.withheld), ([(C, "holder_remains")], ()))


class OnlyChangeTest(unittest.TestCase):
    """Level C is the only code difference from Sprint 30's frozen K1 module, and K1 is unchanged."""

    def nodes(self, name):
        tree = ast.parse((ROOT / "src" / "miaosuan_agent" / "experiments" / name).read_text(encoding="utf-8"))
        out = {}
        for node in tree.body[1:]:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                out[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                out[getattr(target, "id", ast.dump(target))] = node
            else:
                out[ast.dump(node)] = node
        return out

    def test_level_c_is_the_only_code_difference(self) -> None:
        old, new = self.nodes("t13_keep_one_k1.py"), self.nodes("t13_keep_one_k2.py")
        renamed = {"K1Result": "K2Result", "K1Addon": "K2Addon", "K1Policy": "K2Policy", "K1Agent": "K2Agent"}

        def dump(node):
            text = ast.dump(node)
            for a, b in renamed.items():
                text = text.replace(a, b)
            return text

        old = {renamed.get(k, k): v for k, v in old.items()}
        changed = sorted(k for k in old if k in new and dump(old[k]) != dump(new[k]))
        self.assertEqual(changed, ["ADDON_NAME", "CANDIDATE_ID", "ELIGIBILITY", "eligibility"])
        self.assertEqual(sorted(set(new) - set(old)), ["SETTLE_FIELDS", "SETTLE_STEPS", "is_number", "settling"])
        self.assertEqual(sorted(set(old) - set(new)), [])
        a, b = old["eligibility"].body, new["eligibility"].body
        self.assertEqual(len(a), len(b))
        differ = [i for i, (x, y) in enumerate(zip(a, b)) if ast.dump(x) != ast.dump(y)]
        self.assertEqual(len(differ), 1)
        self.assertEqual([ast.dump(s) for s in a[differ[0]].body],                     # the same return of level C
                         [ast.dump(s) for s in b[differ[0]].body])
        self.assertIn("ELIGIBILITY", ast.dump(b[differ[0]].body[0]))
        self.assertEqual(k2.SETTLE_STEPS, 75)

    def test_k1_is_the_frozen_sprint30_module(self) -> None:
        import hashlib
        import json
        pins = json.loads((ROOT / "evaluation" / "s30-t13-k1" / "preflight-inputs.json").read_text(encoding="utf-8"))
        rel = "src/miaosuan_agent/experiments/t13_keep_one_k1.py"
        text = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(text).hexdigest(), pins["sources"][rel])


def play_settling(agent_class, steps=260):
    """Drive the settling stand-in with ``agent_class`` as blue and a shadow ``baseline-v2`` on the same observations."""
    from tests.fixtures import s31_engine as world
    env = world.SettleEnv(play_steps=steps)
    state = env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
    blue, v2, red = agent_class(), ShootReservationAgent(), ShootReservationAgent()
    for agent, seat, faction in ((blue, 11, world.BLUE), (v2, 11, world.BLUE), (red, 1, world.RED)):
        agent.setup({"seat": seat, "faction": faction, "cost_data": syn.cost_data()})
    rows = []
    done = False
    while not done:
        observation = copy.deepcopy(state[world.BLUE])
        base = [dict(a) for a in v2.step(copy.deepcopy(observation))]
        mine = [dict(a) for a in blue.step(copy.deepcopy(observation))]
        rows.append((observation, base, mine))
        state, done = env.step(mine + [dict(a) for a in red.step(copy.deepcopy(state[world.RED]))])
    return world, rows


class SettlingWorldTest(unittest.TestCase):
    """Three tanks arrive together on an unheld objective, one occupies it, and at the next decision baseline-v2 orders
    all three on while they are settling: K2 keeps the slowest, which stays through its transition and after it; K1
    keeps nobody at that decision."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world, cls.rows = play_settling(k2.K2Agent)

    def flag(self, observation):
        return next(c["flag"] for c in observation["cities"] if c["coord"] == self.world.NEAR)

    def test_the_holder_is_kept_through_and_after_its_transition(self) -> None:
        w = self.world
        first = next(i for i, (_, base, mine) in enumerate(self.rows) if base != mine)
        observation, base, mine = self.rows[first]
        units = {u["obj_id"]: u for u in observation["operators"]}
        self.assertEqual(self.flag(observation), w.BLUE)
        self.assertTrue(all(units[u]["stop"] == 0 and units[u]["move_to_stop_remain_time"] > 0
                            for u in (w.T1, w.T2, w.T3)))
        self.assertEqual(mine, [a for a in base if a["obj_id"] != w.T2])
        timers, withheld_while_settled = [], 0
        for observation, base, mine in self.rows[first + 1:]:
            units = {u["obj_id"]: u for u in observation["operators"]}
            self.assertEqual(units[w.T2]["cur_hex"], w.NEAR)
            self.assertEqual(units[w.T2]["move_path"], [])
            timers.append(units[w.T2]["move_to_stop_remain_time"])
            removed = [a for a in base if a not in mine]
            self.assertTrue(all(a["obj_id"] == w.T2 and a["type"] == 1 for a in removed))
            if removed and units[w.T2]["stop"] == 1:
                withheld_while_settled += 1
        self.assertEqual(timers[-1], 0)
        self.assertEqual(sorted(set(timers)), list(range(0, max(timers) + 1)))
        self.assertGreater(withheld_while_settled, 0)

    def test_k1_keeps_nobody_at_the_capture(self) -> None:
        from miaosuan_agent.experiments import t13_keep_one_k1 as k1
        _, rows = play_settling(k1.K1Agent, steps=120)
        capture = next(i for i, (o, _, _) in enumerate(rows) if self.flag(o) == self.world.BLUE)
        observation, base, mine = rows[capture]
        self.assertEqual(len([a for a in base if a["type"] == 1]), 3)
        self.assertEqual(mine, base)


if __name__ == "__main__":
    unittest.main()
