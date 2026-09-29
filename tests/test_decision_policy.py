"""Baseline and inert policy behaviour on synthetic situations."""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.boundary import ContractError, Observation, Origin
from miaosuan_agent.decision import BaselinePolicy, InertPolicy, Memory, digest

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn

SEAT = syn.RED_SEAT


def decide(raw, policy=None, memory=Memory(), faction=ds.RED, seat=SEAT, origin=Origin.ENGINE):
    policy = policy or BaselinePolicy(ds.costs())
    return policy.decide(Observation.from_raw(raw, origin), seat, faction, memory)


def one_unit(unit, actions, **kwargs):
    return ds.play_observation([unit], {unit["obj_id"]: actions}, **kwargs)


class DeploymentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102)],
                                       {ds.UNIT_A: {1: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)], 5: None}},
                                       stage=1, cur_step=0, ended=False)

    def test_ends_deployment_once_and_nothing_else(self) -> None:
        first = decide(self.raw)
        self.assertEqual(list(first.actions), [{"actor": SEAT, "type": 333}])
        self.assertTrue(first.memory.deployment_sent)
        self.assertEqual(first.trace.deployment, "emitted")
        self.assertEqual(first.trace.units, ())
        second = decide(self.raw, memory=first.memory)
        self.assertEqual(second.actions, ())
        self.assertEqual(second.trace.deployment, "already sent")

    def test_not_available_after_the_seat_ended(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["role_and_grouping_info"][SEAT]["end_deployment"] = True
        decision = decide(raw)
        self.assertEqual((decision.actions, decision.trace.deployment), ((), "not available"))
        self.assertFalse(decision.memory.deployment_sent)

    def test_inert_policy_deploys_the_same_way(self) -> None:
        self.assertEqual(list(decide(self.raw, InertPolicy(None)).actions), [{"actor": SEAT, "type": 333}])

    def test_unknown_stage_does_nothing(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["time"]["stage"] = 3
        decision = decide(raw)
        self.assertEqual(decision.actions, ())
        self.assertIn("stage 3 is not interpreted", decision.trace.diagnostics[0])


class PriorityTest(unittest.TestCase):
    def unit_action(self, actions, unit=None, **kwargs):
        unit = unit or syn.unit(ds.UNIT_A, ds.RED, 102)
        decision = decide(one_unit(unit, actions, **kwargs))
        return list(decision.actions), decision.trace.units[0]

    def test_engage_before_occupy_before_move(self) -> None:
        both = {1: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 2)], 5: None}
        self.assertEqual(self.unit_action(both)[0][0]["type"], 2)
        self.assertEqual(self.unit_action({1: None, 5: None})[0][0]["type"], 5)
        self.assertEqual(self.unit_action({1: None})[0][0]["type"], 1)
        actions, record = self.unit_action({})
        self.assertEqual((actions, record.rule, record.no_op_reason), ([], "none", "no action listed"))

    def test_candidate_counts_are_traced(self) -> None:
        _, record = self.unit_action({1: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 2), ds.shoot(ds.ENEMY_B, ds.GUN, 1)]})
        self.assertEqual(dict(record.candidates), {"engage": 2, "occupy": 0, "move": 1})
        self.assertEqual((record.rule, record.validation), ("engage", "accepted"))

    def test_engage_ranking_and_tie_breaks(self) -> None:
        options = [ds.shoot(ds.ENEMY_B, ds.GUN, 2), ds.shoot(ds.ENEMY_B, ds.MISSILE, 3),
                   ds.shoot(ds.ENEMY_A, ds.MISSILE, 3), ds.shoot(ds.ENEMY_A, ds.GUN, 3)]
        actions, record = self.unit_action({2: options})
        self.assertEqual(actions, [{"actor": SEAT, "type": 2, "obj_id": ds.UNIT_A,
                                    "target_obj_id": ds.ENEMY_A, "weapon_id": ds.GUN}])
        self.assertEqual(record.rank, (-3, ds.ENEMY_A, ds.GUN))
        self.assertEqual(dict(record.detail), {"attack_level": 3})

    def test_low_or_malformed_options_are_skipped_with_diagnostics(self) -> None:
        options = [ds.shoot(ds.ENEMY_A, ds.GUN, 0), ds.shoot(ds.ENEMY_A, ds.GUN, -1),
                   {"target_obj_id": ds.ENEMY_A, "weapon_id": ds.GUN}, ds.shoot(ds.ENEMY_A, True, 3),
                   ds.shoot(str(ds.ENEMY_A), ds.GUN, 3)]
        decision = decide(one_unit(syn.unit(ds.UNIT_A, ds.RED, 102), {1: None, 2: options}))
        self.assertEqual(decision.actions[0]["type"], 1)
        self.assertEqual(len(decision.trace.diagnostics), 5)
        self.assertEqual(list(decision.trace.diagnostics), sorted(decision.trace.diagnostics))

    def test_occupy_even_when_standing_on_objective(self) -> None:
        actions, _ = self.unit_action({1: None, 5: None}, syn.unit(ds.UNIT_A, ds.RED, syn.CITY_HEX))
        self.assertEqual(actions, [{"actor": SEAT, "type": 5, "obj_id": ds.UNIT_A}])


class MovementTest(unittest.TestCase):
    def move_of(self, unit, cities=None, roadblocks=(), policy=None):
        decision = decide(one_unit(unit, {1: None}, cities=cities, roadblocks=roadblocks), policy)
        return (decision.actions[0]["move_path"] if decision.actions else None), decision.trace.units[0]

    def test_nearest_unheld_objective(self) -> None:
        cities = [syn.city(909, flag=-1), syn.city(104, flag=ds.RED), syn.city(505, flag=ds.BLUE)]
        path, record = self.move_of(syn.unit(ds.UNIT_A, ds.RED, 102), cities)
        self.assertEqual(path, [103, 204, 304, 405, 505])
        self.assertEqual(dict(record.detail), {"destination": 505, "cost": 5.0, "hexes": 5})

    def test_equal_cost_objectives_break_ties_by_hex(self) -> None:
        cities = [syn.city(107, flag=-1), syn.city(103, flag=-1)]
        path, record = self.move_of(syn.unit(ds.UNIT_A, ds.RED, 105), cities)
        self.assertEqual((path, record.rank), ([104, 103], (2.0, 103)))

    def test_path_cost_not_hex_distance(self) -> None:
        cities = [syn.city(103, flag=-1), syn.city(108, flag=-1)]
        unit = syn.unit(ds.UNIT_A, ds.RED, 105)
        near, _ = self.move_of(unit, cities)
        self.assertEqual(near, [104, 103])
        costly = BaselinePolicy(ds.costs(entry_costs={103: 10}))
        far, record = self.move_of(unit, cities, policy=costly)
        self.assertEqual((far, dict(record.detail)["cost"]), ([106, 107, 108], 3.0))

    def test_roadblocks_for_vehicles_not_infantry(self) -> None:
        cities = [syn.city(503, flag=-1)]
        vehicle, _ = self.move_of(syn.unit(ds.UNIT_A, ds.RED, 500, unit_type=ds.VEHICLE), cities, (501, 502))
        infantry, _ = self.move_of(syn.unit(ds.UNIT_A, ds.RED, 500, unit_type=ds.INFANTRY), cities, (501, 502))
        self.assertEqual(len(vehicle), 4)
        self.assertFalse({501, 502} & set(vehicle))
        self.assertEqual(infantry, [501, 502, 503])

    def test_no_move_reasons(self) -> None:
        cities = [syn.city(505, flag=-1)]
        cases = {
            "already moving (an issued move cannot be changed)":
                (syn.unit(ds.UNIT_A, ds.RED, 102, move_path=(103,)), cities, None),
            "no movement-cost data": (syn.unit(ds.UNIT_A, ds.RED, 102), cities, BaselinePolicy(None)),
            "no documented movement mode for unit type 7": (syn.unit(ds.UNIT_A, ds.RED, 102, unit_type=7), cities, None),
            "no objective outside own control": (syn.unit(ds.UNIT_A, ds.RED, 102), [syn.city(505, flag=ds.RED)], None),
            "standing on an objective outside own control": (syn.unit(ds.UNIT_A, ds.RED, 505), cities, None),
        }
        for reason, (unit, city_list, policy) in cases.items():
            with self.subTest(reason=reason):
                path, record = self.move_of(unit, city_list, policy=policy)
                self.assertIsNone(path)
                self.assertEqual(record.no_op_reason, f"no candidate; move: {reason}")

    def test_unreachable_objective(self) -> None:
        cities = [syn.city(909, flag=-1)]
        path, record = self.move_of(syn.unit(ds.UNIT_A, ds.RED, 500), cities, (400, 401, 501, 600, 601))
        self.assertIsNone(path)
        self.assertEqual(record.no_op_reason, "no candidate; move: no objective reachable")

    def test_no_cities_field(self) -> None:
        raw = one_unit(syn.unit(ds.UNIT_A, ds.RED, 102), {1: None})
        del raw["cities"]
        self.assertEqual(decide(raw).trace.units[0].no_op_reason, "no candidate; move: no objective outside own control")


class MultiUnitTest(unittest.TestCase):
    def test_rich_situation(self) -> None:
        decision = decide(ds.rich_observation())
        self.assertEqual(list(decision.actions), [
            {"actor": SEAT, "type": 2, "obj_id": ds.UNIT_A, "target_obj_id": ds.ENEMY_A, "weapon_id": ds.GUN},
            {"actor": SEAT, "type": 5, "obj_id": ds.UNIT_B},
            {"actor": SEAT, "type": 1, "obj_id": ds.UNIT_C, "move_path": [607, 506, 505]},
        ])
        trace = decision.trace
        self.assertEqual([u.obj_id for u in trace.units], [ds.UNIT_A, ds.UNIT_B, ds.UNIT_C, ds.UNIT_D])
        self.assertEqual([u.rule for u in trace.units], ["engage", "occupy", "move", "none"])
        self.assertEqual(trace.emitted, ((2, ds.UNIT_A), (5, ds.UNIT_B), (1, ds.UNIT_C)))
        self.assertEqual(trace.excluded, (
            (ds.UNCONTROLLED, "not controlled by this seat"),
            (ds.NOT_ON_MAP, "listed for the seat but not on the map"),
            (ds.ONLY_LISTED, "listed in valid_actions but not a controllable unit"),
        ))
        self.assertEqual(len(trace.diagnostics), 1)
        self.assertEqual(trace.rejected, ())

    def test_blue_seat_sees_only_its_units(self) -> None:
        raw = ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102), syn.unit(ds.ENEMY_A, ds.BLUE, 707)],
                                  {ds.ENEMY_A: {1: None}}, seat=syn.BLUE_SEAT, faction=ds.BLUE,
                                  cities=[syn.city(505, flag=ds.RED)])
        decision = decide(raw, faction=ds.BLUE, seat=syn.BLUE_SEAT)
        self.assertEqual([a["obj_id"] for a in decision.actions], [ds.ENEMY_A])
        self.assertEqual(decision.actions[0]["actor"], syn.BLUE_SEAT)

    def test_inert_policy_never_acts_in_play(self) -> None:
        decision = decide(ds.rich_observation(), InertPolicy(ds.costs()))
        self.assertEqual(decision.actions, ())
        self.assertTrue(all(u.no_op_reason == "inert control policy" for u in decision.trace.units))


class FailClosedTest(unittest.TestCase):
    def test_faction_mismatch_is_a_contract_violation(self) -> None:
        with self.assertRaises(ContractError):
            decide(ds.rich_observation(), faction=ds.BLUE)

    def test_missing_seat_is_a_contract_violation(self) -> None:
        with self.assertRaises(ContractError):
            decide(ds.rich_observation(), seat=syn.BLUE_SEAT)

    def test_malformed_parts_raise(self) -> None:
        mutations = {
            "valid_actions not a mapping": lambda o: o.__setitem__("valid_actions", [1]),
            "operator without hex": lambda o: o["operators"][0].pop("cur_hex"),
            "city without coord": lambda o: o["cities"][0].pop("coord"),
            "roadblock without hex": lambda o: o["landmarks"]["roadblocks"][0].pop("hex"),
            "option list not a list": lambda o: o["valid_actions"][ds.UNIT_A].__setitem__(2, 5),
            "time without stage": lambda o: o["time"].pop("stage"),
        }
        for name, mutate in mutations.items():
            raw = ds.rich_observation()
            mutate(raw)
            with self.subTest(case=name), self.assertRaises(ContractError):
                decide(raw)


class PurityTest(unittest.TestCase):
    def test_input_is_not_modified(self) -> None:
        raw = ds.rich_observation()
        before = copy.deepcopy(raw)
        decide(raw)
        self.assertEqual(raw, before)

    def test_same_input_same_decision(self) -> None:
        policy = BaselinePolicy(ds.costs())
        first, second = decide(ds.rich_observation(), policy), decide(ds.rich_observation(), policy)
        fresh = decide(ds.rich_observation(), BaselinePolicy(ds.costs()))
        self.assertEqual(first, second)
        self.assertEqual(first, fresh)
        self.assertEqual(digest(first.trace), digest(fresh.trace))

    def test_json_origin_decides_identically(self) -> None:
        engine = decide(ds.rich_observation())
        json_policy = BaselinePolicy(ds.costs())
        via_json = decide(syn.json_round_trip(ds.rich_observation()), json_policy, origin=Origin.JSON)
        self.assertEqual(engine.actions, via_json.actions)
        self.assertEqual(digest(engine.trace), digest(via_json.trace))


if __name__ == "__main__":
    unittest.main()
