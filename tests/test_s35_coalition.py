"""Sprint 35 coalition agent: unit, adversarial (docs/SPRINT35_COALITION_AGENT.md section 9) and interaction tests.

All states are SYNTHETIC (tests/fixtures/s34_states.py: a 12 x 12 uniform map). Each adversarial test names the
situation of the owner's list it covers; every expected value is computed by hand from the rules in
``coalition.coalition`` and stated beside the assertion.
"""

from __future__ import annotations

import random
import time
import unittest
from dataclasses import replace

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.coalition import capability as C
from miaosuan_agent.coalition import coalition as K
from miaosuan_agent.coalition.agent import CoalitionAgent
from miaosuan_agent.coalition.allocator import CoalitionAllocator
from miaosuan_agent.coalition.config import CA, CLASS_WEIGHT, CM, VARIANTS, CoalitionConfig
from miaosuan_agent.coalition.memory import CoalitionMemory, MAX_SIGHTINGS, canonical, updated_seen
from miaosuan_agent.coalition.policy import CoalitionPolicy, candidate_id
from miaosuan_agent.coalition.support import arrival_steps, guided_shots, support_fire
from miaosuan_agent.coalition.validate import validate
from miaosuan_agent.integrated import facts as F
from miaosuan_agent.integrated.allocation import known_enemies
from miaosuan_agent.integrated.config import MO
from miaosuan_agent.integrated.movement import Terrain
from miaosuan_agent.integrated.world import build_world
from tests.fixtures import s34_states as S

RED, BLUE = 0, 1
MOVE_ONLY = {F.MOVE: None}


def agent(config=CA) -> CoalitionAgent:
    a = CoalitionAgent(config, strict=True)
    a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
    a.memory = replace(a.memory, deployment_sent=True)
    return a


def world_of(observation, color=RED):
    seat = S.RED_SEAT if color == RED else S.BLUE_SEAT
    return build_world(Observation.from_raw(observation), seat, color, S.ROWS, S.COLS)


def by_unit(actions):
    return {a["obj_id"]: a for a in actions if "obj_id" in a}


def assess(observation, config=CA, memory=None):
    """The stance assessment of the red seat, built exactly as the policy builds it."""
    memory = memory or CoalitionMemory(deployment_sent=True)
    terrain = Terrain(MoveCosts.from_raw(S.costs()))
    allocator = CoalitionAllocator(config, terrain)
    view = Observation.from_raw(observation)
    world = build_world(view, S.RED_SEAT, RED, S.ROWS, S.COLS)
    max_blood = C.enemy_max_blood(view.operators(), RED)
    seen = updated_seen(memory.seen, C.observed_rows(world, max_blood), world.step, config.sighting_ttl)
    memory = replace(memory, seen=seen)
    from miaosuan_agent.integrated.world import State
    free = [u for u in world.units if u.mobile_ground and u.can_move and u.state in (State.SETTLED, State.TRANSITION)]
    pictures = allocator.pictures(world, known_enemies(world, memory), frozenset(u.obj_id for u in free))
    threats = C.threats(world, memory.seen, max_blood, config)
    return {a.hex: a for a in K.assess(world, memory, allocator, config, pictures, threats, free)}


def tank(i, color, hex_, **kw):
    return S.unit(i, color, hex_, sub_type=F.TANK, value=kw.pop("value", 10), **kw)


def ifv(i, color, hex_, **kw):
    return S.unit(i, color, hex_, sub_type=F.IFV, value=kw.pop("value", 8), **kw)


def squad(i, color, hex_, **kw):
    return S.unit(i, color, hex_, type_=F.INFANTRY, sub_type=F.SQUAD, basic_speed=kw.pop("basic_speed", 5),
                  value=kw.pop("value", 4), weapons=(29,), **kw)


class CapabilityTests(unittest.TestCase):
    def test_class_weights_follow_the_recorded_rates(self):
        # capability.json: tank 2.2945, ifv 0.5593, ugv 0.4242, squad 0.0886 damage per 1,000 unit-steps
        for sub, rate in ((F.IFV, 0.5593), (F.UGV, 0.4242), (F.SQUAD, 0.0886)):
            self.assertAlmostEqual(CLASS_WEIGHT[sub], round(rate / 2.2945 * 20) / 20, places=6)
        self.assertEqual(CLASS_WEIGHT[F.TANK], 1.0)

    def test_power_scales_with_strength_and_has_a_floor(self):
        self.assertAlmostEqual(C.class_weight(99), 0.15)
        self.assertAlmostEqual(C.class_weight(F.SQUAD), 0.05)
        self.assertAlmostEqual(C.strength_fraction(1, 4), 0.25)
        self.assertEqual(C.strength_fraction(5, 0), 1.0)
        self.assertEqual(C.strength_fraction(0, 0), 0.0)

    def test_each_enemy_counts_against_one_objective(self):
        # a tank one hex from 505 and seven from 909, and a tank nearer 505 whose visible path ends at 909
        own = [ifv(1, RED, 505), ifv(2, RED, 909)]
        enemies = [tank(901, BLUE, 405), tank(902, BLUE, 101, path=(202, 909), speed=0.05)]
        stances = assess(S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY},
                               cities=[S.city(505, RED, 80), S.city(909, RED, 50)]))
        self.assertAlmostEqual(stances[505].threat, 1.0)    # only the nearer tank
        self.assertAlmostEqual(stances[909].threat, 1.0)    # only the tank whose path ends there
        self.assertEqual((F.hex_distance(405, 505), F.hex_distance(405, 909)), (1, 7))
        self.assertLess(F.hex_distance(101, 505), F.hex_distance(101, 909))

    def test_revision_2_counts_an_enemy_at_its_own_objective_against_the_next_one(self):
        # an enemy tank standing on 909, an objective its side holds; our held objective 505 is 6 hexes away (arrival 100 steps)
        own = [ifv(1, RED, 505)]
        enemy = [tank(901, BLUE, 909)]
        cities = [S.city(505, RED, 80), S.city(909, BLUE, 50)]
        obs = S.obs(RED, own + enemy, {1: MOVE_ONLY}, cities=cities)
        self.assertEqual(F.hex_distance(909, 505), 6)
        now = assess(obs)[505]
        self.assertAlmostEqual(now.threat, 1.0)            # counted against 505
        self.assertEqual(now.stance, K.DELAY)
        before = assess(obs, config=VARIANTS["ca-r1-attribution"])[505]
        self.assertEqual(before.stance, K.QUIET)           # revision 1: counted against 909 (arrival 0) only

    def test_remembered_threat_decays_and_expires(self):
        # situation 6: a hidden enemy known only from a stale sighting
        own = [tank(1, RED, 505)]
        memory = CoalitionMemory(deployment_sent=True, seen=((901, 507, 100, F.TANK, 1000),))
        cities = [S.city(505, RED, 80)]
        fresh = assess(S.obs(RED, own, {1: MOVE_ONLY}, cities=cities, step=400), memory=memory)[505]
        self.assertEqual(fresh.stance, K.SECURE)            # threat 1.0 x (1 - 300/600) = 0.5 <= defence 1.0
        self.assertAlmostEqual(fresh.threat, 0.5)
        self.assertAlmostEqual(fresh.visible_threat, 0.0)
        gone = assess(S.obs(RED, own, {1: MOVE_ONLY}, cities=cities, step=700), memory=memory)[505]
        self.assertEqual(gone.stance, K.QUIET)              # age 600 -> confidence 0


class StanceTests(unittest.TestCase):
    def test_situation_1_strongly_held_enemy_objective_is_skipped_by_a_weak_force(self):
        enemies = [tank(901, BLUE, 505), tank(902, BLUE, 506), tank(903, BLUE, 504)]
        own = [ifv(1, RED, 101)]
        a = assess(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)]))[505]
        self.assertEqual(a.stance, K.SKIP)                  # want 1.2 x 3.0 = 3.6; reachable 0.25
        actions = agent().step(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)]))
        self.assertEqual(actions, [])                        # no unit is sent alone

    def test_situation_1_a_strong_enough_coalition_is_formed(self):
        enemies = [tank(901, BLUE, 505)]
        own = [tank(i, RED, 101 + i) for i in range(1, 3)]
        a = assess(S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)]))[505]
        self.assertEqual(a.stance, K.COALITION)             # want 1.2; two tanks reach 2.0
        self.assertEqual(a.places, 2)
        moved = by_unit(agent().step(S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY},
                                           cities=[S.city(505, BLUE, 80)])))
        self.assertEqual(set(moved), {1, 2})

    def test_situation_2_mass_heading_for_one_objective_diverts_the_force_to_the_other(self):
        # slow enemies (basic speed 4: 180 steps per hex): path end in 808's zone in 360 steps; 303 is 9-10 hexes away
        mass = [tank(901 + i, BLUE, 1009 + i, path=(909, 808), speed=0.005, basic_speed=4) for i in range(2)]
        own = [ifv(1, RED, 202)]
        cities = [S.city(303, -1, 50), S.city(808, -1, 80)]
        stances = assess(S.obs(RED, own + mass, {1: MOVE_ONLY}, cities=cities))
        self.assertEqual(stances[303].stance, K.CAPTURE)
        self.assertEqual(stances[808].stance, K.SKIP)
        move = by_unit(agent().step(S.obs(RED, own + mass, {1: MOVE_ONLY}, cities=cities)))[1]
        self.assertEqual(move["move_path"][-1], 303)

    def test_situation_3_and_4_outmatched_holder_delays_and_stays(self):
        enemies = [tank(901 + i, BLUE, 508 + i * 100 - 100) for i in range(3)]
        own = [ifv(1, RED, 505)]
        a = assess(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=[S.city(505, RED, 80)]))[505]
        self.assertEqual(a.stance, K.DELAY)                 # defence 0.25 < 0.6 x 3.0, nothing reachable
        self.assertEqual(a.keep, (1,))
        self.assertEqual(a.withdraw, ())
        self.assertEqual(agent().step(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=[S.city(505, RED, 80)])), [])

    def test_delay_withdraws_the_valuable_unit_and_keeps_the_infantry_holder(self):
        # slow enemies 3-4 hexes from 505 (arrival 360-540 steps), 9-10 hexes from 909 (beyond the horizon)
        enemies = [tank(901, BLUE, 502, basic_speed=4), tank(902, BLUE, 402, basic_speed=4),
                   tank(903, BLUE, 602, basic_speed=4)]
        own = [squad(1, RED, 505), tank(2, RED, 505), squad(3, RED, 909)]
        cities = [S.city(505, RED, 80), S.city(909, RED, 50)]
        listings = {1: MOVE_ONLY, 2: MOVE_ONLY, 3: MOVE_ONLY}
        a = assess(S.obs(RED, own + enemies, listings, cities=cities))[505]
        self.assertEqual(a.stance, K.DELAY)                 # defence 1.05 < 0.6 x 3.0 = 1.8
        self.assertEqual(a.keep, (1,))                      # the squad holds (infantry first)
        self.assertEqual(a.withdraw, ((2, 909),))           # the tank leaves for the other held objective
        moved = by_unit(agent().step(S.obs(RED, own + enemies, listings, cities=cities)))
        self.assertIn(2, moved)
        self.assertIn(moved[2]["move_path"][-1], F.zone(909, S.ROWS, S.COLS))
        self.assertNotIn(1, moved)

    def test_withdrawal_needs_visible_threat(self):
        # situation 4 with stale knowledge only: no withdrawal, both defenders kept
        own = [squad(1, RED, 505), tank(2, RED, 505)]
        seen = tuple((901 + i, 508, 50, F.TANK, 1000) for i in range(3))
        memory = CoalitionMemory(deployment_sent=True, seen=seen)
        a = assess(S.obs(RED, own, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80), S.city(909, RED, 50)],
                         step=60), memory=memory)[505]
        self.assertEqual(a.stance, K.DELAY)                 # threat 3 x (1 - 10/600) = 2.95; defence 1.05
        self.assertEqual(a.withdraw, ())
        self.assertEqual(a.keep, (1, 2))

    def test_situation_5_capability_not_headcount(self):
        squads = [squad(901 + i, BLUE, 707 + i) for i in range(3)]
        a = assess(S.obs(RED, [tank(1, RED, 505)] + squads, {1: MOVE_ONLY}, cities=[S.city(505, RED, 80)]))[505]
        self.assertEqual(a.stance, K.SECURE)                # three squads 0.15 <= one tank 1.0
        b = assess(S.obs(RED, [squad(i, RED, 505) for i in (1, 2, 3)] + [tank(901, BLUE, 707)],
                         {1: MOVE_ONLY, 2: MOVE_ONLY, 3: MOVE_ONLY}, cities=[S.city(505, RED, 80)]))[505]
        self.assertEqual(b.stance, K.DELAY)                 # three squads 0.15 < 0.6 x 1.0

    def test_situation_7_reserve_supports_one_objective_without_stripping_another(self):
        # slow enemy 4 hexes from 505 (arrival 540), 11 from 1101 (no threat); the tank at 707 is 3 hexes away
        enemies = [tank(901, BLUE, 509, basic_speed=4)]
        own = [ifv(1, RED, 505), ifv(2, RED, 1101), tank(3, RED, 707)]
        cities = [S.city(505, RED, 80), S.city(1101, RED, 50)]
        listings = {u: MOVE_ONLY for u in (1, 2, 3)}
        stances = assess(S.obs(RED, own + enemies, listings, cities=cities))
        self.assertEqual(stances[505].stance, K.DEFEND)     # defence 0.25 < 1.0; tank reaches it before the enemy
        moved = by_unit(agent().step(S.obs(RED, own + enemies, listings, cities=cities)))
        self.assertIn(3, moved)
        self.assertIn(moved[3]["move_path"][-1], F.zone(505, S.ROWS, S.COLS))
        self.assertNotIn(1, moved)
        self.assertNotIn(2, moved)                          # the other objective's holder stays

    def test_situation_8_two_competing_requests_one_unit_goes_to_one(self):
        enemies = [tank(901, BLUE, 211), tank(902, BLUE, 1111)]
        own = [ifv(1, RED, 202), ifv(2, RED, 1002), tank(3, RED, 606)]
        cities = [S.city(202, RED, 80), S.city(1002, RED, 50)]
        listings = {u: MOVE_ONLY for u in (1, 2, 3)}
        moved = by_unit(agent().step(S.obs(RED, own + enemies, listings, cities=cities)))
        self.assertEqual(set(moved), {3})
        zones = F.zone(202, S.ROWS, S.COLS) | F.zone(1002, S.ROWS, S.COLS)
        self.assertIn(moved[3]["move_path"][-1], zones)
        again = by_unit(agent().step(S.obs(RED, own + enemies, listings, cities=cities)))
        self.assertEqual(moved, again)                      # deterministic

    def test_dwell_delays_a_downgrade(self):
        enemies = [tank(901 + i, BLUE, 508) for i in range(3)]
        own = [ifv(1, RED, 505)]
        cities = [S.city(505, RED, 80)]
        recent = CoalitionMemory(deployment_sent=True, stances=((505, K.DEFEND, 5),))
        self.assertEqual(assess(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=cities, step=10),
                                memory=recent)[505].stance, K.DEFEND)
        self.assertEqual(assess(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=cities, step=80),
                                memory=recent)[505].stance, K.DELAY)

    def test_retention_keeps_the_last_defender_against_a_better_slot(self):
        # the Sprint 34 departure pattern: a held, threatened objective's only defender and an open objective nearby
        own = [ifv(1, RED, 505)]
        enemies = [ifv(901, BLUE, 509, basic_speed=4)]   # threatens 505 (540 steps), not 303 (1,080)
        cities = [S.city(505, RED, 50), S.city(303, -1, 80)]
        a = agent(CA).step(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=cities))
        self.assertEqual(a, [])
        ablated = agent(VARIANTS["ca-no-retention"]).step(S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=cities))
        self.assertEqual(by_unit(ablated)[1]["move_path"][-1], 303)


class TrafficAndTransportTests(unittest.TestCase):
    def test_situation_9_kept_infantry_is_not_lifted(self):
        own = [squad(1, RED, 505), ifv(2, RED, 505, passenger_types=(2,))]
        enemies = [tank(901, BLUE, 509)]
        listings = {1: {F.MOVE: None, F.GET_ON: [{"target_obj_id": 2}]}, 2: MOVE_ONLY}
        actions = agent(CA).step(S.obs(RED, own + enemies, listings, cities=[S.city(505, RED, 80)]))
        self.assertNotIn(F.GET_ON, [a["type"] for a in actions])

    def test_situation_10_reinforcements_spread_over_the_zone(self):
        own = [ifv(i, RED, 505) for i in (1, 2, 3)] + [tank(4, RED, 101), tank(5, RED, 102)]
        # three slow enemy tanks 4 hexes away (arrival 540); the own tanks arrive in about 100-120 steps
        enemies = [tank(901, BLUE, 509, basic_speed=4), tank(902, BLUE, 509, basic_speed=4),
                   tank(903, BLUE, 509, basic_speed=4)]
        listings = {u: MOVE_ONLY for u in (1, 2, 3, 4, 5)}
        moved = by_unit(agent().step(S.obs(RED, own + enemies, listings, cities=[S.city(505, RED, 80)])))
        ends = [m["move_path"][-1] for m in moved.values()]
        self.assertTrue(ends)
        self.assertNotIn(505, ends)                         # the objective hex already holds three
        for end in ends:
            self.assertIn(end, F.zone(505, S.ROWS, S.COLS))
        self.assertLessEqual(max(ends.count(e) for e in ends), 2)

    def test_situation_13_a_unit_on_an_issued_path_is_never_reordered(self):
        own = [tank(1, RED, 303, path=(304, 305), speed=0.05)]
        actions = agent().step(S.obs(RED, own, {1: {F.STOP: None}}, cities=[S.city(808, -1, 80)]))
        self.assertEqual(actions, [])

    def test_situation_19_no_artillery_and_no_carrier(self):
        own = [tank(1, RED, 202)]
        for config in (CA, CM):
            actions = agent(config).step(S.obs(RED, own, {1: MOVE_ONLY}, cities=[S.city(808, -1, 80)]))
            self.assertEqual([a["type"] for a in actions], [F.MOVE])

    def test_safe_transport_refuses_lifts_to_threatened_objectives(self):
        own = [squad(1, RED, 101), ifv(2, RED, 101, passenger_types=(2,)), tank(3, RED, 1001)]
        enemies = [squad(901, BLUE, 1111)]
        listings = {1: {F.MOVE: None, F.GET_ON: [{"target_obj_id": 2}]}, 2: MOVE_ONLY, 3: MOVE_ONLY}
        cities = [S.city(1110, RED, 80)]
        cm = agent(CM).step(S.obs(RED, own + enemies, listings, cities=cities))
        self.assertNotIn(F.GET_ON, [a["type"] for a in cm])


class FireTests(unittest.TestCase):
    def setUp(self):
        self.art = S.unit(50, RED, 0, sub_type=F.ARTILLERY, weapons=(72,))   # 15 to 17 hexes from rows 10-11
        self.listing = {50: {F.INDIRECT: [{"weapon_id": 72}]}}

    def test_situation_11_no_impact_near_a_planned_stand(self):
        enemy = tank(901, BLUE, 1110)
        w = world_of(S.obs(RED, [self.art, enemy], self.listing))
        self.assertEqual([o[1] for o in support_fire(w, CM, [], (), (), {})], [1110])
        self.assertEqual(support_fire(w, CM, [1109], (), (), {}), [])    # a planned stand next to it

    def test_situation_12_no_visible_target_no_order(self):
        w = world_of(S.obs(RED, [self.art], self.listing))
        self.assertEqual(support_fire(w, CM, [], (), (), {}), [])

    def test_arrival_fire_aims_at_the_path_end_inside_the_window(self):
        # 10 hexes at speed 1/20 -> 200 steps: inside [150, 375)
        e = tank(901, BLUE, 1100, path=tuple(1101 + i for i in range(10)), speed=0.05)
        w = world_of(S.obs(RED, [self.art, e], self.listing))
        self.assertEqual(arrival_steps(w.enemies[0]), 200)
        self.assertEqual([o[1] for o in support_fire(w, CM, [], (), (), {})], [1110])
        self.assertEqual(support_fire(w, VARIANTS["cm-no-arrival-fire"], [], (), (), {}), [])
        near = tank(902, BLUE, 1100, path=(1101, 1102), speed=0.05)    # 40 steps: too soon
        self.assertEqual(support_fire(world_of(S.obs(RED, [self.art, near], self.listing)), CM, [], (), (), {}), [])

    def test_threat_priority_orders_targets(self):
        far = tank(901, BLUE, 1111, value=20)
        near = ifv(902, BLUE, 1011, value=5)
        w = world_of(S.obs(RED, [self.art, far, near], self.listing, cities=[S.city(1001, RED, 80)]))
        a = K.Assessment(1001, 80, K.DEFEND, 0.25, 0.25, 10, 0, 0.25, 0, None)
        self.assertEqual(support_fire(w, CM, [], (), (a,), {1001: (902,)})[0][1], 1011)
        # without fire support the order is Sprint 34's: the higher value first
        self.assertEqual(support_fire(w, VARIANTS["cm-no-fire-support"], [], (), (a,), {1001: (902,)})[0][1], 1111)

    def test_guided_fire_reserves_target_and_carrier(self):
        own = [squad(1, RED, 505), ifv(2, RED, 506), squad(3, RED, 507)]
        enemy = tank(901, BLUE, 909)
        g = [{"target_obj_id": 901, "weapon_id": 73, "guided_obj_id": 2, "attack_level": 8}]
        listings = {1: {F.GUIDED: g}, 3: {F.GUIDED: g}, 2: MOVE_ONLY}
        w = world_of(S.obs(RED, own + [enemy], listings))
        shots = guided_shots(w, frozenset(), set())
        self.assertEqual(shots, {1: (901, 73, 2, 8)})       # unit 3 finds the target and the carrier taken
        self.assertEqual(guided_shots(w, frozenset({2}), set()), {})   # carrier acting: no guided shot
        actions = agent(CM).step(S.obs(RED, own + [enemy], listings))
        self.assertEqual([a for a in actions if a["type"] == F.GUIDED],
                         [{"actor": S.RED_SEAT, "type": F.GUIDED, "obj_id": 1, "target_obj_id": 901, "weapon_id": 73,
                           "guided_obj_id": 2}])
        self.assertNotIn(2, by_unit(actions))
        self.assertNotIn(F.GUIDED, [a["type"] for a in agent(CA).step(S.obs(RED, own + [enemy], listings))])

    def test_situation_14_invalid_or_missing_options(self):
        own = [squad(1, RED, 505), ifv(2, RED, 506)]
        bad = [{"target_obj_id": 901, "weapon_id": 73, "guided_obj_id": 2, "attack_level": 0},
               {"target_obj_id": 901, "weapon_id": None, "guided_obj_id": 2, "attack_level": 8}]
        w = world_of(S.obs(RED, own + [tank(901, BLUE, 909)], {1: {F.GUIDED: bad}, 2: MOVE_ONLY}))
        self.assertEqual(guided_shots(w, frozenset(), set()), {})
        good = [{"target_obj_id": 901, "weapon_id": 73, "guided_obj_id": 2, "attack_level": 8}]
        w = world_of(S.obs(RED, own + [tank(901, BLUE, 909)], {1: {F.GUIDED: good}, 2: MOVE_ONLY}))
        ok = {"actor": S.RED_SEAT, "type": F.GUIDED, "obj_id": 1, "target_obj_id": 901, "weapon_id": 73,
              "guided_obj_id": 2}
        terrain = Terrain(MoveCosts.from_raw(S.costs()))
        enabled = frozenset({F.MOVE})
        self.assertEqual(len(validate([ok], w, terrain, enabled, False, True).accepted), 1)
        self.assertEqual(len(validate([ok], w, terrain, enabled, False, False).accepted), 0)
        for change in ({"weapon_id": 74}, {"guided_obj_id": 3}, {"target_obj_id": 902}, {"actor": S.BLUE_SEAT}):
            self.assertEqual(validate([{**ok, **change}], w, terrain, enabled, False, True).accepted, ())
        extra = dict(ok, attack_level=8)
        self.assertEqual(validate([extra], w, terrain, enabled, False, True).accepted, ())
        carrier_moves = {"actor": S.RED_SEAT, "type": F.MOVE, "obj_id": 2, "move_path": [507]}
        verdict = validate([carrier_moves, ok], w, terrain, enabled, False, True)
        self.assertEqual([a["type"] for a in verdict.accepted], [F.MOVE])


class AgentTests(unittest.TestCase):
    def test_situation_15_deployment_stage_emits_only_the_completion(self):
        a = CoalitionAgent(CM, strict=True)
        a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
        own = [squad(1, RED, 505), ifv(2, RED, 505, passenger_types=(2,))]
        observation = S.obs(RED, own, {1: {F.GET_ON: [{"target_obj_id": 2}], 14: None}}, stage=1, step=0)
        self.assertEqual(a.step(observation), [{"actor": S.RED_SEAT, "type": F.END_DEPLOYMENT}])

    def test_situation_16_delivered_infantry_without_follow_on_task_stays(self):
        own = [squad(1, RED, 505)]
        actions = agent().step(S.obs(RED, own, {1: MOVE_ONLY}, cities=[S.city(505, RED, 80)]))
        self.assertEqual(actions, [])

    def test_situation_17_and_18_few_and_many_heterogeneous_units(self):
        self.assertEqual(agent().step(S.obs(RED, [tank(1, RED, 101)], {1: MOVE_ONLY}, cities=[S.city(808, -1, 80)]))[0]
                         ["type"], F.MOVE)
        rng = random.Random(35)
        units, listings = [], {}
        hexes = [r * 100 + c for r in range(S.ROWS) for c in range(S.COLS)]
        for i in range(1, 41):
            kind = rng.choice((tank, ifv, squad))
            units.append(kind(i, RED, rng.choice(hexes)))
            listings[i] = MOVE_ONLY
        for i in range(901, 931):
            units.append(rng.choice((tank, ifv, squad))(i, BLUE, rng.choice(hexes)))
        cities = [S.city(h, rng.choice((-1, RED, BLUE)), v) for h, v in ((202, 80), (909, 80), (505, 50), (1010, 50))]
        for config in (CA, CM):
            a = agent(config)
            tick = time.perf_counter()
            actions = a.step(S.obs(RED, units, listings, cities=cities))
            elapsed = time.perf_counter() - tick
            self.assertIsNone(a.last_trace.fallback)
            self.assertEqual(a.last_trace.rejected, ())
            self.assertLess(elapsed, 1.0)                   # situation 20: inside the online budget
            ends = {}
            for x in actions:
                ends[x["move_path"][-1]] = ends.get(x["move_path"][-1], 0) + 1
            self.assertTrue(all(v <= F.STACK_LIMIT for v in ends.values()))

    def test_decide_is_pure_and_replay_matches(self):
        own = [ifv(1, RED, 505), tank(2, RED, 101)]
        enemies = [tank(901, BLUE, 509)]
        obs = S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80)])
        a = agent(CM)
        memory = a.memory
        first = a.step(obs)
        from miaosuan_agent.decision.trace import digest
        self.assertEqual(digest(a.replay(obs, memory)), digest(a.last_trace))
        b = agent(CM)
        self.assertEqual(b.step(obs), first)

    def test_memory_is_canonical_and_bounded(self):
        seen = updated_seen((), [(i, 101, F.TANK, 1000) for i in range(200)], 10, 600)
        self.assertEqual(len(seen), MAX_SIGHTINGS)
        older = updated_seen(((5, 101, 0, F.TANK, 1000),), [], 700, 600)
        self.assertEqual(older, ())
        m = CoalitionMemory(stances=((2, "quiet", 0), (1, "defend", 3), (1, "defend", 3)))
        self.assertEqual(canonical(m).stances, ((1, "defend", 3), (2, "quiet", 0)))
        self.assertIn("stances", m.to_dict())

    def test_identities(self):
        self.assertEqual(candidate_id(CA), "s35-coalition-coalition-allocator-2")
        self.assertEqual(candidate_id(CM), "s35-coalition-coalition-mission-planner-2")
        self.assertEqual(candidate_id(VARIANTS["ca-r1-attribution"]), "s35-coalition-ca-r1-attribution-1")
        self.assertEqual((CA.revision, CA.attribution, CM.revision, CM.attribution), (2, "unheld", 2, "unheld"))
        self.assertIs(CA.base, MO)
        self.assertFalse(CA.guided_fire or CA.arrival_fire or CA.fire_support or CA.safe_transport)
        self.assertTrue(CM.guided_fire and CM.arrival_fire and CM.fire_support and CM.safe_transport)
        names = {c.name for c in VARIANTS.values()}
        self.assertEqual(len(names), len(VARIANTS))

    def test_variant_a_indirect_fire_is_sprint_34s(self):
        from miaosuan_agent.integrated.fire import indirect_fire
        art = S.unit(50, RED, 101, sub_type=F.ARTILLERY, weapons=(72,))
        listing = {50: {F.INDIRECT: [{"weapon_id": 72}]}}
        enemies = [tank(901, BLUE, 1010), ifv(902, BLUE, 1111, path=(1110,), speed=0.05)]
        obs = S.obs(RED, [art] + enemies, listing, cities=[S.city(1010, BLUE, 50)])
        mine = [a for a in agent(CA).step(obs) if a["type"] == F.INDIRECT]
        w = world_of(obs)
        expected = indirect_fire(w, MO, [], ())
        self.assertEqual([(a["obj_id"], a["jm_pos"], a["weapon_id"]) for a in mine], expected)


if __name__ == "__main__":
    unittest.main()
