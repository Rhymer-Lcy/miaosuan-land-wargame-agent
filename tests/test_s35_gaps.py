"""Sprint 35: tests that close the gaps found by the first mutation run (scripts/mutate_s35.py; SYNTHETIC states).

Each test names the mutant it kills. Expected values are computed by hand beside the assertions (12 x 12 uniform map,
vehicles at basic speed 36 enter a hex in 20 steps, at basic speed 4 in 180 steps).
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.coalition import coalition as K
from miaosuan_agent.coalition.allocator import REINFORCE, CoalitionAllocator, Place
from miaosuan_agent.coalition.config import CA, CM
from miaosuan_agent.coalition.support import guided_shots, support_fire
from miaosuan_agent.evaluation import s35_live as sl
from miaosuan_agent.integrated import facts as F
from miaosuan_agent.integrated import transport as T
from miaosuan_agent.integrated.allocation import known_enemies
from miaosuan_agent.integrated.memory import HOLD, RIDE
from miaosuan_agent.integrated.movement import Terrain
from miaosuan_agent.integrated.world import build_world
from miaosuan_agent.coalition.memory import CoalitionMemory
from tests.fixtures import s34_states as S
from tests.test_s35_coalition import MOVE_ONLY, RED, BLUE, agent, assess, by_unit, ifv, squad, tank, world_of
from tests.test_s35_live import CAND, facts, played


class StanceGapTests(unittest.TestCase):
    def test_threat_beyond_the_horizon_is_ignored(self):           # kills "threat horizon ignored"
        obs = S.obs(RED, [ifv(1, RED, 505), tank(901, BLUE, 1111, basic_speed=4)], {1: MOVE_ONLY},
                    cities=[S.city(505, RED, 80)])
        self.assertEqual(F.hex_distance(505, 1111), 9)              # arrival (9 - 1) x 180 = 1,440 > 600
        self.assertEqual(assess(obs)[505].stance, K.QUIET)

    def three_tanks_at_509(self):
        return [tank(901 + i, BLUE, 509, basic_speed=4) for i in range(3)]   # arrival (4 - 1) x 180 = 540

    def test_infantry_holds_before_a_cheaper_vehicle(self):        # kills "holder rank not infantry first"
        own = [squad(1, RED, 505, value=12), S.unit(2, RED, 505, sub_type=F.UGV, value=6)]
        obs = S.obs(RED, own + self.three_tanks_at_509(), {1: MOVE_ONLY, 2: MOVE_ONLY},
                    cities=[S.city(505, RED, 80), S.city(1101, RED, 50)])
        a = assess(obs)[505]
        self.assertEqual(a.stance, K.DELAY)                         # defence 0.05 + 0.2 < 0.6 x 3
        self.assertEqual((a.keep, a.withdraw), ((1, 2), ()))        # the squad holds; the vehicle is cheaper: stays

    def test_a_unit_cheaper_than_the_holder_is_not_withdrawn(self):  # kills "cheaper units withdrawn"
        own = [squad(1, RED, 505, value=4), ifv(2, RED, 505, value=3)]
        obs = S.obs(RED, own + self.three_tanks_at_509(), {1: MOVE_ONLY, 2: MOVE_ONLY},
                    cities=[S.city(505, RED, 80), S.city(1101, RED, 50)])
        a = assess(obs)[505]
        self.assertEqual((a.stance, a.withdraw, a.keep), (K.DELAY, (), (1, 2)))

    def test_secure_keeps_only_what_the_requirement_needs(self):   # kills "secure keeps every defender"
        own = [tank(i, RED, 505) for i in (1, 2, 3)]
        obs = S.obs(RED, own + [ifv(901, BLUE, 509, basic_speed=4)], {i: MOVE_ONLY for i in (1, 2, 3)},
                    cities=[S.city(505, RED, 80)])
        a = assess(obs)[505]
        self.assertEqual((a.stance, a.keep), (K.SECURE, (1,)))      # one tank (1.0) covers the 0.25 threat

    def test_inbound_units_count_before_the_enemy(self):            # kills "inbound arrivals not counted"
        own = [ifv(1, RED, 505), tank(2, RED, 707, path=(606, 505), speed=0.05)]
        obs = S.obs(RED, own + [tank(901, BLUE, 509, basic_speed=4)], {1: MOVE_ONLY},
                    cities=[S.city(505, RED, 80)])
        a = assess(obs)[505]
        self.assertEqual(a.stance, K.SECURE)                        # 0.25 + 1.0 >= 1.0 before the 540-step arrival
        self.assertAlmostEqual(a.defence, 1.25)

    def test_a_reinforcement_just_after_the_enemy_still_counts(self):  # kills "reinforcement grace dropped"
        own = [ifv(1, RED, 505), tank(2, RED, 105)]
        obs = S.obs(RED, own + [tank(901, BLUE, 509)], {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80)])
        self.assertEqual((F.hex_distance(509, 505), F.hex_distance(105, 505)), (4, 4))
        a = assess(obs)[505]                                        # enemy 3 x 20 = 60; the tank 4 x 20 = 80 <= 100
        self.assertEqual((a.stance, a.places), (K.DEFEND, 1))

    def test_a_weak_force_skips_instead_of_capturing(self):         # kills "skip becomes capture"
        enemies = [tank(901, BLUE, 505), tank(902, BLUE, 506)]
        a = assess(S.obs(RED, [ifv(1, RED, 101)] + enemies, {1: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)]))[505]
        self.assertEqual((a.stance, a.places), (K.SKIP, 0))


class AllocatorGapTests(unittest.TestCase):
    def setUp(self):
        self.terrain = Terrain(MoveCosts.from_raw(S.costs()))

    def test_a_reinforcement_place_has_a_deadline(self):            # kills "reinforcement deadline ignored"
        w = world_of(S.obs(RED, [tank(1, RED, 101)], {1: MOVE_ONLY}, step=10))
        allocator = CoalitionAllocator(CA, self.terrain)
        place = Place(505, 0, HOLD, REINFORCE, 1.0, 10 + 50)
        self.assertTrue(allocator.place_feasible(w, place, 50.0))
        self.assertFalse(allocator.place_feasible(w, place, 60.0))

    def test_reinforcement_value_grows_with_power(self):            # kills "power not valued"
        own = [tank(1, RED, 101), squad(2, RED, 101)]
        w = world_of(S.obs(RED, own, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80)]))
        allocator = CoalitionAllocator(CA, self.terrain)
        picture = allocator.pictures(w, (), frozenset({1, 2}))[0]
        place = Place(505, 0, HOLD, REINFORCE, 1.0, None)
        memory = CoalitionMemory()
        u_tank = allocator.place_utility(w, memory, w.unit(1), picture, place, 100.0, 10.0)
        u_squad = allocator.place_utility(w, memory, w.unit(2), picture, place, 100.0, 10.0)
        self.assertAlmostEqual(u_tank - u_squad, 0.95 * 80)       # 80 x (0.5 + 1.0) - 80 x (0.5 + 0.05)

    def test_safe_transport_refuses_a_lift_to_a_threatened_objective(self):  # kills "safe transport ignored"
        own = [squad(1, RED, 101), ifv(2, RED, 101, passenger_types=(2,))]
        listings = {1: {F.MOVE: None, F.GET_ON: [{"target_obj_id": 2}]}, 2: MOVE_ONLY}
        w = world_of(S.obs(RED, own, listings, cities=[S.city(1110, -1, 80)]))
        pairs = T.candidates(w, [1, 2], [])
        self.assertEqual([(i.obj_id, c.obj_id) for i, c in pairs], [(1, 2)])
        threatened = [K.Assessment(1110, 80, K.CAPTURE, 0.5, 0.5, 300, 0.0, 0.0, 0, None)]
        kinds = {}
        for config in (CA, CM):
            allocator = CoalitionAllocator(config, self.terrain)
            pictures = allocator.pictures(w, (), frozenset({1, 2}))
            result = allocator.allocate_places(w, CoalitionMemory(), [w.unit(1), w.unit(2)], pictures, threatened,
                                               pairs, ())
            kinds[config.name] = sorted(a.kind for a in result)
        self.assertIn(RIDE, kinds[CA.name])                         # walking 14 hexes takes 2,016 steps; a lift ~510
        self.assertNotIn(RIDE, kinds[CM.name])


class FireGapTests(unittest.TestCase):
    def test_the_guided_carrier_takes_no_other_action(self):        # kills "guided carrier acts"
        own = [squad(1, RED, 505), ifv(2, RED, 506)]
        g = [{"target_obj_id": 901, "weapon_id": 73, "guided_obj_id": 2, "attack_level": 8}]
        # a slow enemy far from the open objective 101 (no threat there), so unit 2 has a capture place
        obs = S.obs(RED, own + [tank(901, BLUE, 1111, basic_speed=4)], {1: {F.GUIDED: g}, 2: MOVE_ONLY},
                    cities=[S.city(101, -1, 80)])
        actions = by_unit(agent(CM).step(obs))
        self.assertEqual(actions[1]["type"], F.GUIDED)
        self.assertNotIn(2, actions)                                # without the shot, unit 2 would move to 101
        self.assertEqual(by_unit(agent(CA).step(obs))[2]["type"], F.MOVE)

    def test_two_guiding_units_do_not_share_a_target(self):        # kills "guided target not reserved"
        own = [squad(1, RED, 505), ifv(2, RED, 506), S.unit(3, RED, 507, sub_type=F.UGV), ifv(4, RED, 508)]
        g1 = [{"target_obj_id": 901, "weapon_id": 73, "guided_obj_id": 2, "attack_level": 8}]
        g3 = [{"target_obj_id": 901, "weapon_id": 73, "guided_obj_id": 4, "attack_level": 8}]
        w = world_of(S.obs(RED, own + [tank(901, BLUE, 909)], {1: {F.GUIDED: g1}, 3: {F.GUIDED: g3}}))
        self.assertEqual(guided_shots(w, frozenset(), set()), {1: (901, 73, 2, 8)})

    def test_an_arrival_after_the_window_is_not_a_target(self):     # kills "arrival window ignored"
        art = S.unit(50, RED, 0, sub_type=F.ARTILLERY, weapons=(72,))
        late = tank(901, BLUE, 1100, path=tuple(1101 + i for i in range(10)), speed=0.01)   # 1,000 steps
        w = world_of(S.obs(RED, [art, late], {50: {F.INDIRECT: [{"weapon_id": 72}]}}))
        self.assertEqual(F.hex_distance(0, 1110), 16)
        self.assertEqual(support_fire(w, CM, [], (), (), {}), [])


class LiveGapTests(unittest.TestCase):
    def test_the_control_is_subtracted(self):                       # kills "control not subtracted"
        c = sl.comparison(played(lambda g: 150, lambda g: 150, n=40))
        self.assertEqual((c["dbar"], c["zbar_candidate"], c["zbar_control"]), (0.0, 1.0, 1.0))

    def test_promising_needs_dbar_of_half(self):                    # kills "promising threshold loosened"
        gate = [{"batch": "A1", "open": True, "reason": "x"}]
        near = played(lambda g: 127.5, lambda g: 105)               # d = 0.55 - 0.1 = 0.45; own z 0.55
        self.assertAlmostEqual(sl.comparison(near)["dbar"], 0.45)
        self.assertEqual(sl.disposition(near, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")

    def test_margins_at_the_minimum_are_not_severe_harm(self):     # kills "severe harm at the minimum"
        stage_a = [facts(p, 100) for p in range(1, 41)]
        first = next(g for g in sl.schedule(CAND) if g["tag"] == "s35")
        twin = next(g for g in sl.schedule(CAND) if g["tag"] == "s35" and g["repetition"] == 2
                    and g["scenario_id"] == first["scenario_id"] and g["condition"] == first["condition"])
        for game in (first, twin):
            stage_a[game["position"] - 1] = facts(game["position"], 0)     # equal to the reference minimum 0
        self.assertTrue(sl.batch_gate("A2", stage_a)["open"])


if __name__ == "__main__":
    unittest.main()
