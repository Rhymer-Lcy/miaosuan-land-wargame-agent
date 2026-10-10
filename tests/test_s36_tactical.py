"""Sprint 36 tactical agent: rule, adversarial and equivalence tests (SYNTHETIC 12 x 12 uniform map).

States come from ``tests/fixtures/s34_states.py``: vehicles at basic speed 36 enter a hex in 720 / 36 = 20 steps,
squads at 5 in 144; an enemy without a path arrives at a zone in (hex distance - 1) x its hex time. Each expectation is
derived beside its assertion from the rules in ``tactical.assess`` and Sprint 35's ``coalition.coalition``.
"""

from __future__ import annotations

import time
import unittest
from dataclasses import replace

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.coalition import capability as C
from miaosuan_agent.coalition import coalition as K
from miaosuan_agent.coalition.agent import CoalitionAgent
from miaosuan_agent.coalition.config import CA
from miaosuan_agent.integrated import facts as F
from miaosuan_agent.integrated.agent import CommanderAgent
from miaosuan_agent.integrated.allocation import known_enemies
from miaosuan_agent.integrated.config import MO
from miaosuan_agent.integrated.movement import Terrain
from miaosuan_agent.integrated.traffic import Traffic
from miaosuan_agent.integrated.world import State, build_world
from miaosuan_agent.tactical import assess as A
from miaosuan_agent.tactical.agent import TacticalAgent
from miaosuan_agent.tactical.allocator import DELAY_PLACE, TacticalAllocator
from miaosuan_agent.tactical.config import TA, TB, TC, VARIANTS
from miaosuan_agent.tactical.memory import (MAX_POSTS, TacticalMemory, canonical, updated_losses,
                                            updated_posts)
from miaosuan_agent.tactical.policy import ENABLED, candidate_id
from tests.fixtures import s34_states as S

RED, BLUE = 0, 1
MOVE_ONLY = {F.MOVE: None}


def tank(i, color, hex_, **kw):
    return S.unit(i, color, hex_, sub_type=F.TANK, value=kw.pop("value", 10), **kw)


def ifv(i, color, hex_, **kw):
    return S.unit(i, color, hex_, sub_type=F.IFV, value=kw.pop("value", 8), **kw)


def squad(i, color, hex_, **kw):
    return S.unit(i, color, hex_, type_=F.INFANTRY, sub_type=F.SQUAD, basic_speed=kw.pop("basic_speed", 5),
                  value=kw.pop("value", 4), weapons=(29,), **kw)


def by_unit(actions):
    return {a["obj_id"]: a for a in actions if "obj_id" in a}


def tactical(config=TA):
    a = TacticalAgent(config, strict=True)
    a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
    a.memory = replace(a.memory, deployment_sent=True)
    return a


def coalition(config=CA):
    a = CoalitionAgent(config, strict=True)
    a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
    a.memory = replace(a.memory, deployment_sent=True)
    return a


def orchestrator():
    a = CommanderAgent(MO, strict=True)
    a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
    a.memory = replace(a.memory, deployment_sent=True)
    return a


def assess(observation, config=TA, memory=None):
    """The red seat's Sprint 36 assessment, built as ``TacticalPolicy`` builds it (memory upkeep of posts excluded:
    pass them in ``memory``)."""
    memory = memory or TacticalMemory(deployment_sent=True)
    terrain = Terrain(MoveCosts.from_raw(S.costs()))
    allocator = TacticalAllocator(config, terrain)
    view = Observation.from_raw(observation)
    world = build_world(view, S.RED_SEAT, RED, S.ROWS, S.COLS)
    max_blood = C.enemy_max_blood(view.operators(), RED)
    from miaosuan_agent.coalition.memory import updated_seen
    memory = replace(memory, seen=updated_seen(memory.seen, C.observed_rows(world, max_blood), world.step,
                                                 config.coalition.sighting_ttl))
    free = [u for u in world.units if u.mobile_ground and u.can_move and u.state in (State.SETTLED, State.TRANSITION)]
    pictures = allocator.pictures(world, known_enemies(world, memory), frozenset(u.obj_id for u in free))
    threats = C.threats(world, memory.seen, max_blood, config.coalition)
    out = A.assess(world, memory, allocator, config, pictures, threats, free, Traffic(world), terrain)
    return {a.hex: a for a in out}


class StaticFilterTests(unittest.TestCase):
    def setUp(self):
        # an enemy tank two hexes from objective 505 (outside its zone): arrival (2 - 1) x 20 = 20 steps
        self.enemy = tank(901, BLUE, 507)
        self.own = [tank(1, RED, 202)]
        self.cities = [S.city(505, -1, 80)]
        self.assertEqual(F.hex_distance(507, 505), 2)

    def obs(self, step=100):
        return S.obs(RED, self.own + [self.enemy], {1: MOVE_ONLY}, cities=self.cities, step=step)

    def test_a_mobile_enemy_near_the_zone_still_blocks_a_lone_capture(self):
        # threat 1.0, capture ratio 1.2: one tank (1.0) is not a coalition; our arrival (> 20) loses the race
        self.assertEqual(assess(self.obs())[505].stance, K.SKIP)

    def test_a_static_enemy_outside_the_zone_is_not_a_threat(self):
        posted = TacticalMemory(deployment_sent=True, posts=((901, 507, 25, 99),))   # standing since 25: 75 steps
        a = assess(self.obs(step=100), memory=posted)[505]
        self.assertEqual(a.stance, K.CAPTURE)
        self.assertEqual(a.threat, 0.0)
        young = TacticalMemory(deployment_sent=True, posts=((901, 507, 26, 99),))     # 74 steps: not yet static
        self.assertEqual(assess(self.obs(step=100), memory=young)[505].stance, K.SKIP)
        self.assertEqual(assess(self.obs(step=100), config=VARIANTS["ta-no-static-filter"],
                                memory=posted)[505].stance, K.SKIP)

    def test_a_static_enemy_inside_the_zone_still_blocks(self):
        self.enemy = tank(901, BLUE, 506)                                             # in the zone of 505
        posted = TacticalMemory(deployment_sent=True, posts=((901, 506, 0, 99),))
        self.assertEqual(assess(self.obs(step=100), memory=posted)[505].stance, K.SKIP)

    def test_a_moving_enemy_loses_its_post(self):
        posts = updated_posts(((901, 507, 0, 50),), [], [901], 60, 600)
        self.assertEqual(posts, ())
        posts = updated_posts(((901, 507, 0, 50),), [(901, 507)], [], 60, 600)
        self.assertEqual(posts, ((901, 507, 0, 60),))                                  # still there: since kept
        posts = updated_posts(((901, 507, 0, 50),), [(901, 508)], [], 60, 600)
        self.assertEqual(posts, ((901, 508, 60, 60),))                                 # moved: since reset


class OpportunityCaptureTests(unittest.TestCase):
    def test_a_free_unit_that_arrives_first_takes_the_objective(self):
        # enemy tank at 1105: 6 hexes from 505, arrival 5 x 20 = 100 steps (within the 600-step horizon);
        # our tank at 404 is 2 hexes away: 40 steps; 40 + 10 <= 100 -> capture
        own = [tank(1, RED, 404)]
        enemy = tank(901, BLUE, 1105)
        self.assertEqual((F.hex_distance(1105, 505), F.hex_distance(404, 505)), (6, 2))
        obs = S.obs(RED, own + [enemy], {1: MOVE_ONLY}, cities=[S.city(505, -1, 80)])
        self.assertEqual(assess(obs, config=VARIANTS["ta-no-opportunity-capture"])[505].stance, K.SKIP)
        a = assess(obs)[505]
        self.assertEqual(a.stance, K.CAPTURE)
        self.assertTrue(a.note.startswith("opportunity"))
        moved = by_unit(tactical().step(obs))
        self.assertIn(moved[1]["move_path"][-1], F.zone(505, S.ROWS, S.COLS))
        self.assertEqual(coalition().step(obs), [])                                    # Sprint 35 sends nobody

    def test_an_enemy_arriving_first_keeps_the_coalition_rule(self):
        own = [tank(1, RED, 1101)]
        enemy = tank(901, BLUE, 507)                                                   # arrives in 20 steps
        obs = S.obs(RED, own + [enemy], {1: MOVE_ONLY}, cities=[S.city(505, -1, 80)])
        self.assertEqual(assess(obs)[505].stance, K.SKIP)

    def test_an_enemy_in_the_zone_is_never_raced(self):
        own = [tank(1, RED, 404)]
        enemy = tank(901, BLUE, 506)
        obs = S.obs(RED, own + [enemy], {1: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)])
        self.assertEqual(assess(obs)[505].stance, K.SKIP)


class SurvivalDelayTests(unittest.TestCase):
    def setUp(self):
        # three slow enemy tanks (basic speed 4: 180 steps per hex) 3-4 hexes from 505: arrival 360-540 steps,
        # all visible; defence < 0.6 x 3.0 -> delay. A second held objective 909 is quiet.
        self.enemies = [tank(901, BLUE, 502, basic_speed=4), tank(902, BLUE, 402, basic_speed=4),
                        tank(903, BLUE, 602, basic_speed=4)]
        self.cities = [S.city(505, RED, 80), S.city(909, RED, 50)]

    def obs(self, own, step=10):
        return S.obs(RED, own + self.enemies, {u["obj_id"]: MOVE_ONLY for u in own}, cities=self.cities, step=step)

    def test_no_cheap_holder_every_valuable_defender_withdraws(self):
        own = [ifv(1, RED, 505), tank(2, RED, 505)]
        ca = coalition().step(self.obs(own))
        s35 = assess(self.obs(own), config=VARIANTS["ta-as-ca"])[505]
        self.assertEqual((s35.stance, s35.keep, s35.withdraw), (K.DELAY, (1,), ((2, 909),)))   # IFV held, tank leaves
        self.assertEqual(set(by_unit(ca)), {2})
        a = assess(self.obs(own))[505]
        self.assertEqual((a.stance, a.keep), (K.DELAY, ()))                       # no unit is cheap (8 > 0.5 x 10)
        self.assertEqual(a.withdraw, ((1, 909), (2, 909)))
        moved = by_unit(tactical().step(self.obs(own)))
        self.assertEqual(set(moved), {1, 2})
        for m in moved.values():
            self.assertIn(m["move_path"][-1], F.zone(909, S.ROWS, S.COLS))

    def test_a_cheap_holder_stays_and_the_others_withdraw(self):
        own = [squad(1, RED, 505), ifv(2, RED, 505), tank(3, RED, 505)]
        a = assess(self.obs(own))[505]
        self.assertEqual(a.keep, (1,))
        self.assertEqual(a.withdraw, ((2, 909), (3, 909)))

    def test_no_withdrawal_when_contact_is_too_close(self):
        # fast enemy tanks 2 hexes away: arrival 20 steps < withdraw_lead 40 -> everybody stays and fights
        self.enemies = [tank(901 + i, BLUE, 507) for i in range(3)]
        own = [ifv(1, RED, 505), tank(2, RED, 505)]
        a = assess(self.obs(own))[505]
        self.assertEqual((a.stance, a.keep, a.withdraw), (K.DELAY, (1, 2), ()))

    def test_end_window_every_defender_stays(self):
        own = [ifv(1, RED, 505), tank(2, RED, 505)]
        a = assess(self.obs(own, step=S.MAX_STEP - 300))[505]
        self.assertEqual((a.keep, a.withdraw), ((1, 2), ()))
        b = assess(self.obs(own, step=S.MAX_STEP - 301))[505]
        self.assertEqual(b.keep, ())
        c = assess(self.obs(own, step=S.MAX_STEP - 300), config=VARIANTS["ta-no-end-window"])[505]
        self.assertEqual(c.keep, ())

    def test_withdrawal_to_a_contact_breaking_hex_without_a_held_objective(self):
        self.cities = [S.city(505, RED, 80)]
        own = [tank(2, RED, 505)]
        a = assess(self.obs(own))[505]
        self.assertEqual(len(a.withdraw), 1)
        dest = a.withdraw[0][1]
        now = min(F.hex_distance(505, e["cur_hex"]) for e in self.enemies)
        self.assertGreaterEqual(min(F.hex_distance(dest, e["cur_hex"]) for e in self.enemies), now + TA.safe_margin)
        self.assertNotIn(dest, F.zone(505, S.ROWS, S.COLS))
        self.assertLessEqual(F.hex_distance(505, dest), A.SAFE_RADIUS)

    def test_ablation_without_withdrawal_keeps_them(self):
        own = [ifv(1, RED, 505), tank(2, RED, 505)]
        a = assess(self.obs(own), config=VARIANTS["ta-no-withdrawal"])[505]
        self.assertEqual((a.keep, a.withdraw), ((1, 2), ()))


class EmptyHolderTests(unittest.TestCase):
    def test_a_cheap_free_unit_takes_the_delaying_place(self):
        # held 505 with nobody in its zone; three slow tanks 4 hexes away arrive in 3 x 180 = 540 steps; the tank at
        # 101 (6 hexes, 120 steps) and the squad at 404 (2 hexes, 288 steps) reach it in time but
        # 1.0 + 0.05 < 0.6 x 3.0 -> delay; the squad is the only cheap unit
        enemies = [tank(901, BLUE, 808, basic_speed=4), tank(902, BLUE, 808, basic_speed=4),
                   tank(903, BLUE, 808, basic_speed=4)]
        self.assertEqual((F.hex_distance(808, 505), F.hex_distance(404, 505), F.hex_distance(101, 505)), (4, 2, 6))
        own = [tank(1, RED, 101), squad(2, RED, 404)]
        obs = S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80)])
        a = assess(obs)[505]
        self.assertEqual((a.stance, a.places, a.note), (K.DELAY, 1, A.DELAY_ROLE_NOTE))
        moved = by_unit(tactical().step(obs))
        self.assertIn(2, moved)
        self.assertIn(moved[2]["move_path"][-1], F.zone(505, S.ROWS, S.COLS))
        self.assertNotIn(1, moved)                                                  # the tank is not cheap
        self.assertEqual(by_unit(coalition().step(obs)), {})                         # Sprint 35: nobody
        none = assess(obs, config=VARIANTS["ta-no-delay-holder"])[505]
        self.assertEqual(none.places, 0)


class GuardTests(unittest.TestCase):
    def test_a_valuable_unit_is_not_sent_into_an_untenable_zone(self):
        enemies = [tank(901, BLUE, 506), tank(902, BLUE, 504), tank(903, BLUE, 405)]   # in the zone of 505
        own = [tank(1, RED, 202)]
        obs = S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)])
        mo = by_unit(orchestrator().step(obs))
        self.assertIn(1, mo)                                                         # Sprint 34 attacks alone
        guarded = tactical(TC)
        self.assertEqual(guarded.step(obs), [])
        self.assertEqual(dict(guarded.last_trace.stats)["guard_dropped"], 1)
        self.assertEqual(by_unit(tactical(VARIANTS["tc-no-guard"]).step(obs)), mo)

    def test_a_cheap_unit_may_still_go(self):
        enemies = [tank(901, BLUE, 506), tank(902, BLUE, 504), tank(903, BLUE, 405)]
        own = [squad(1, RED, 202), tank(2, RED, 1111)]
        obs = S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)])
        mo = by_unit(orchestrator().step(obs))
        self.assertEqual(set(mo), {1, 2})                                            # Sprint 34 sends both
        guarded = by_unit(tactical(TC).step(obs))
        self.assertEqual(guarded, {1: mo[1]})                                        # the squad (4 <= 5) still goes

    def test_the_guard_adds_withdrawals_through_the_traffic_ledger(self):
        enemies = [tank(901, BLUE, 502, basic_speed=4), tank(902, BLUE, 402, basic_speed=4),
                   tank(903, BLUE, 602, basic_speed=4)]
        own = [ifv(1, RED, 505), tank(2, RED, 505), squad(3, RED, 909)]
        cities = [S.city(505, RED, 80), S.city(909, RED, 50)]
        obs = S.obs(RED, own + enemies, {1: MOVE_ONLY, 2: MOVE_ONLY, 3: MOVE_ONLY}, cities=cities)
        agent = tactical(TC)
        moved = by_unit(agent.step(obs))
        self.assertEqual({u for u in moved if u in (1, 2)}, {1, 2})
        for u in (1, 2):
            self.assertIn(moved[u]["move_path"][-1], F.zone(909, S.ROWS, S.COLS))
        self.assertEqual(dict(agent.last_trace.stats)["guard_withdrawals"], 2)
        no = by_unit(tactical(VARIANTS["tc-no-withdrawal"]).step(obs))
        self.assertNotIn(2, {u for u, m in no.items() if m["move_path"][-1] in F.zone(909, S.ROWS, S.COLS)})


class GuardRetentionTests(unittest.TestCase):
    def test_the_last_defender_of_a_threatened_held_objective_is_not_ordered_away(self):
        # Sprint 34's departure pattern: the only defender of held 505 (threatened by a slow enemy IFV 4 hexes away,
        # arrival 540 steps) and an open objective 303 worth more
        own = [ifv(1, RED, 505)]
        enemies = [ifv(901, BLUE, 509, basic_speed=4)]
        cities = [S.city(505, RED, 50), S.city(303, -1, 80)]
        obs = S.obs(RED, own + enemies, {1: MOVE_ONLY}, cities=cities)
        mo = by_unit(orchestrator().step(obs))
        self.assertEqual(mo[1]["move_path"][-1], 303)                                # Sprint 34 leaves
        agent = tactical(TC)
        self.assertEqual(agent.step(obs), [])                                        # secure: 0.25 >= 0.25 x 1.0
        self.assertEqual(dict(agent.last_trace.stats)["guard_dropped"], 1)
        self.assertEqual(by_unit(tactical(VARIANTS["tc-no-retention"]).step(obs)), mo)


class EquivalenceTests(unittest.TestCase):
    """With every Sprint 36 rule off the agents decide as the frozen controls (actions compared)."""

    STATES = []

    @classmethod
    def setUpClass(cls):
        e3 = [tank(901, BLUE, 502, basic_speed=4), tank(902, BLUE, 402, basic_speed=4),
              tank(903, BLUE, 602, basic_speed=4)]
        cls.STATES = [
            S.obs(RED, [tank(1, RED, 404), tank(901, BLUE, 1105)], {1: MOVE_ONLY}, cities=[S.city(505, -1, 80)]),
            S.obs(RED, [ifv(1, RED, 505), tank(2, RED, 505)] + e3, {1: MOVE_ONLY, 2: MOVE_ONLY},
                  cities=[S.city(505, RED, 80), S.city(909, RED, 50)]),
            S.obs(RED, [tank(1, RED, 101), squad(2, RED, 404), tank(901, BLUE, 802, basic_speed=4)],
                  {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80), S.city(303, -1, 50)]),
            S.obs(RED, [tank(1, RED, 202), tank(901, BLUE, 506)], {1: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)]),
        ]

    def test_ta_as_ca_is_sprint35_ca(self):
        for obs in self.STATES:
            self.assertEqual(tactical(VARIANTS["ta-as-ca"]).step(obs), coalition(CA).step(obs))

    def test_tc_without_guard_is_sprint34_mo(self):
        for obs in self.STATES:
            self.assertEqual(tactical(VARIANTS["tc-no-guard"]).step(obs), orchestrator().step(obs))


class ContractAndMemoryTests(unittest.TestCase):
    def test_only_enabled_action_types_and_no_stop(self):
        e3 = [tank(901 + i, BLUE, 507) for i in range(3)]
        obs = S.obs(RED, [ifv(1, RED, 505), tank(2, RED, 505), squad(3, RED, 909)] + e3,
                    {1: {F.MOVE: None, F.STOP: None}, 2: MOVE_ONLY, 3: MOVE_ONLY},
                    cities=[S.city(505, RED, 80), S.city(909, RED, 50)])
        for name in ("TA", "TB", "TC"):
            for a in tactical(VARIANTS[name]).step(obs):
                self.assertIn(a["type"], ENABLED)
                self.assertNotEqual(a["type"], F.STOP)

    def test_decision_is_pure(self):
        obs = S.obs(RED, [tank(1, RED, 404), tank(901, BLUE, 1105)], {1: MOVE_ONLY}, cities=[S.city(505, -1, 80)])
        for config in (TA, TB, TC):
            a, b = tactical(config), tactical(config)
            self.assertEqual(a.step(obs), b.step(obs))
            self.assertEqual(canonical(a.memory), canonical(b.memory))
            replayed = a.replay(obs, replace(TacticalMemory(), deployment_sent=True))
            self.assertEqual(replayed.emitted, a.last_trace.emitted)

    def test_posts_and_losses_are_bounded(self):
        posts = updated_posts((), [(i, 100 + i) for i in range(200)], [], 10, 600)
        self.assertEqual(len(posts), MAX_POSTS)
        self.assertEqual(updated_posts(posts, [], [], 700, 600), ())                  # all expired
        self.assertEqual(updated_losses(((303, 5),), (505, 909), (909,), 40), ((303, 5), (505, 40)))

    def test_identity(self):
        self.assertEqual(candidate_id(TA), "s36-tactical-survival-capture-1")
        self.assertEqual(candidate_id(TB), "s36-tactical-mission-coordinator-1")
        self.assertEqual(candidate_id(TC), "s36-tactical-guarded-orchestrator-1")

    def test_counterattack_bonus_on_recent_losses(self):
        terrain = Terrain(MoveCosts.from_raw(S.costs()))
        allocator = TacticalAllocator(TB, terrain)
        obs = S.obs(RED, [tank(1, RED, 101), tank(2, RED, 102), tank(901, BLUE, 505)],
                    {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, BLUE, 80)], step=500)
        world = build_world(Observation.from_raw(obs), S.RED_SEAT, RED, S.ROWS, S.COLS)
        a = K.Assessment(505, 80, K.COALITION, 1.0, 1.0, 0.0, 0.0, 1.2, 2, None)
        pictures = allocator.pictures(world, known_enemies(world, TacticalMemory()), frozenset({1, 2}))
        base = [p.weight for p in allocator.places(world, pictures, [a])]
        allocator.lost = {505: 300}
        boosted = [p.weight for p in allocator.places(world, pictures, [a])]
        self.assertEqual(boosted, [w * 1.25 for w in base])
        allocator.lost = {505: -200}                                                 # 700 steps ago: outside 600
        self.assertEqual([p.weight for p in allocator.places(world, pictures, [a])], base)

    def test_delay_place_is_offered_only_to_cheap_units(self):
        terrain = Terrain(MoveCosts.from_raw(S.costs()))
        allocator = TacticalAllocator(TA, terrain)
        obs = S.obs(RED, [tank(1, RED, 404), squad(2, RED, 404)], {1: MOVE_ONLY, 2: MOVE_ONLY},
                    cities=[S.city(505, RED, 80)])
        world = build_world(Observation.from_raw(obs), S.RED_SEAT, RED, S.ROWS, S.COLS)
        units = list(world.units)
        pictures = allocator.pictures(world, (), frozenset({1, 2}))
        a = K.Assessment(505, 80, K.DELAY, 3.0, 3.0, 360.0, 0.0, 3.0, 1, 370, note=A.DELAY_ROLE_NOTE)
        self.assertIn(DELAY_PLACE, [p.role for p in allocator.places(world, pictures, [a])])
        chosen = allocator.allocate_places(world, TacticalMemory(), units, pictures, [a])
        self.assertEqual([c.unit for c in chosen], [2])


class ScaleTests(unittest.TestCase):
    def test_forty_against_thirty_units_decide_quickly_and_legally(self):
        own = [tank(i, RED, (i % 10) * 100 + i // 10) for i in range(1, 41)]
        enemies = [tank(900 + i, BLUE, (i % 10) * 100 + 11 - i // 10) for i in range(30)]
        listings = {u["obj_id"]: MOVE_ONLY for u in own}
        cities = [S.city(505, -1, 80), S.city(909, RED, 50), S.city(202, BLUE, 50)]
        obs = S.obs(RED, own + enemies, listings, cities=cities)
        for config in (TA, TB, TC):
            agent = tactical(config)
            tick = time.perf_counter()
            actions = agent.step(obs)
            self.assertLess(time.perf_counter() - tick, 2.0)
            self.assertIsNone(getattr(agent.last_trace, "fallback", None))
            self.assertEqual(agent.last_trace.rejected, ())
            ends = [a["move_path"][-1] for a in actions if a["type"] == F.MOVE]
            self.assertLessEqual(max([ends.count(e) for e in ends] or [0]), F.STACK_LIMIT)


if __name__ == "__main__":
    unittest.main()
