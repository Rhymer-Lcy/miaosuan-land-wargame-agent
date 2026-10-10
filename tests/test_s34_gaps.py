"""Sprint 34 tests written for the gaps the first mutation run found (``evaluation/s34-integrated-agent``)."""

from __future__ import annotations

import unittest
from dataclasses import replace

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.evaluation import s34_live as sl
from miaosuan_agent.evaluation import s34_offline as so
from miaosuan_agent.evaluation.s34_capture import S34Timeline
from miaosuan_agent.integrated import facts as F
from miaosuan_agent.integrated import memory as M
from miaosuan_agent.integrated import transport as T
from miaosuan_agent.integrated.agent import CommanderAgent
from miaosuan_agent.integrated.allocation import Allocator
from miaosuan_agent.integrated.config import CT, MO
from miaosuan_agent.integrated.movement import Terrain
from miaosuan_agent.integrated.policy import CommanderPolicy, Intent, candidate_id
from miaosuan_agent.integrated.traffic import Traffic
from miaosuan_agent.integrated.world import build_world
from tests.fixtures import s34_states as S
from tests.test_s34_integrated import MOVE_ONLY, RED, agent, by_unit, world_of
from tests.test_s34_live import facts as live_facts
from tests.test_s34_offline import summaries


class TrafficGapTests(unittest.TestCase):
    def test_a_destination_at_cap_three_refuses(self):
        units = [S.unit(900100 + i, RED, 505) for i in range(3)]
        t = Traffic(world_of(S.obs(RED, units, {})))
        self.assertFalse(t.accepts(505, 3))
        self.assertTrue(t.accepts(505, 4))
        self.assertTrue(t.accepts(506, 3))

    def test_an_order_moves_the_planned_stand(self):
        mover = S.unit(900101, RED, 101)
        w = world_of(S.obs(RED, [mover] + [S.unit(900110 + i, RED, 505) for i in range(2)], {}))
        t = Traffic(w)
        t.order(w.unit(900101), (102, 505))
        self.assertEqual((t.stand(101), t.stand(505)), (0, 3))
        self.assertFalse(t.accepts(505, 3))


class AllocationGapTests(unittest.TestCase):
    def setUp(self):
        self.allocator = Allocator(MO, Terrain(MoveCosts.from_raw(S.costs())))

    def test_room_counts_commitments(self):
        from miaosuan_agent.integrated.allocation import known_enemies
        mover = S.unit(900101, RED, 806, path=[807, 808], speed=0.05)
        enemy = S.unit(900201, 1, 809)
        w = world_of(S.obs(RED, [mover, enemy], {}, cities=[S.city(808)], controlled=[900101]))
        known = known_enemies(w, M.CommanderMemory())
        pictures = self.allocator.pictures(w, known, frozenset())
        self.assertEqual((pictures[0].committed, pictures[0].contested), (1, True))
        self.assertEqual([s[1] for s in self.allocator.slots(w, pictures)], [1, 2])
        tight = Allocator(replace(MO, destination_cap=2), self.allocator.terrain)
        self.assertEqual([s[1] for s in tight.slots(w, tight.pictures(w, known, frozenset()))], [1])

    def test_movers_that_cannot_arrive_are_not_commitments(self):
        far = S.unit(900101, RED, 101, path=[102, 103, 104, 105], speed=1 / 144, basic_speed=5, type_=1, sub_type=2)
        w = world_of(S.obs(RED, [far], {}, cities=[S.city(105)], step=1990, max_step=2000))
        self.assertEqual(self.allocator.pictures(w, [], frozenset())[0].inbound, ())

    def test_no_lift_when_walking_is_nearly_as_fast(self):
        a = agent(MO)
        inf = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2], value=8)
        listings = {900101: {**MOVE_ONLY, F.GET_ON: [{"target_obj_id": 900102}]}, 900102: MOVE_ONLY}
        actions = a.step(S.obs(RED, [inf, car], listings, cities=[S.city(102)]))
        self.assertFalse(any(x["type"] == F.GET_ON for x in actions))


class PolicyGapTests(unittest.TestCase):
    def policy(self):
        return CommanderPolicy(MoveCosts.from_raw(S.costs()), MO)

    def test_route_refuses_a_destination_at_capacity(self):
        p = self.policy()
        units = [S.unit(900101, RED, 101)] + [S.unit(900110 + i, RED, 808) for i in range(3)]
        w = world_of(S.obs(RED, units, {900101: MOVE_ONLY}, cities=[S.city(808)]))
        path, why = p._route(w, w.unit(900101), Intent("allocation", "capture", 808, ""), Traffic(w), frozenset(), {})
        self.assertIsNone(path)
        self.assertEqual(why, "destination stand at capacity")

    def test_route_refuses_a_full_first_hex(self):
        p = self.policy()
        through = [S.unit(900110 + i, RED, 102, path=[103 + i], speed=0.05) for i in range(4)]
        w = world_of(S.obs(RED, [S.unit(900101, RED, 101)] + through, {900101: MOVE_ONLY}, cities=[S.city(102)]))
        traffic = Traffic(w)
        self.assertNotIn(102, traffic.blocked_for(101))
        path, why = p._route(w, w.unit(900101), Intent("allocation", "capture", 102, ""), traffic, frozenset(), {})
        self.assertIsNone(path)
        self.assertEqual(why, "first hex full")

    def test_no_new_lift_within_the_cooldown(self):
        a = agent(MO)
        a.memory = replace(a.memory, orders=((900101, F.GET_ON, 5),))
        inf = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2], value=8)
        listings = {900101: {**MOVE_ONLY, F.GET_ON: [{"target_obj_id": 900102}]}, 900102: MOVE_ONLY}
        actions = a.step(S.obs(RED, [inf, car], listings, cities=[S.city(1110)], step=100))
        self.assertFalse(any(x["type"] == F.GET_ON for x in actions))
        later = agent(MO)
        later.memory = replace(later.memory, orders=((900101, F.GET_ON, 5),))
        actions = later.step(S.obs(RED, [inf, car], listings, cities=[S.city(1110)], step=5 + MO.lift_cooldown))
        self.assertTrue(any(x["type"] == F.GET_ON for x in actions))

    def test_the_boarding_carrier_is_held(self):
        a = agent(MO)
        inf = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2], value=8)
        listings = {900101: {**MOVE_ONLY, F.GET_ON: [{"target_obj_id": 900102}]}, 900102: MOVE_ONLY}
        actions = by_unit(a.step(S.obs(RED, [inf, car], listings, cities=[S.city(1110)])))
        self.assertEqual(actions[900101]["type"], F.GET_ON)
        self.assertNotIn(900102, actions)
        plan = next(p for p in a.last_trace.plans if p[0] == 900102)
        self.assertEqual(plan[2], "boarding-hold")


class FireAndTransportGapTests(unittest.TestCase):
    def test_level_zero_options_are_never_fired(self):
        a = agent()
        option = [{"target_obj_id": 900201, "weapon_id": 37, "attack_level": 0}]
        actions = a.step(S.obs(RED, [S.unit(900101, RED, 505), S.unit(900201, 1, 509)],
                               {900101: {F.SHOOT: option}}, controlled=[900101]))
        self.assertEqual(actions, [])

    def test_an_unexecuted_embark_is_dropped(self):
        inf = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2], value=8)
        w = world_of(S.obs(RED, [inf, car], {}, step=40))
        lifts = ((900101, 900102, 1110, M.BOARDING, 20),)
        step = T.step_lifts(w, lifts, 1900)
        self.assertEqual(step.lifts, ())
        self.assertIn("embark not executed", step.notes[0])
        recent = T.step_lifts(world_of(S.obs(RED, [inf, car], {}, step=25)), lifts, 1900)
        self.assertEqual(len(recent.lifts), 1)

    def test_a_loaded_carrier_does_not_unload_short_of_its_objective(self):
        aboard = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4, on_board=1)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2], value=8, passengers=[900101])
        listing = {900102: {**MOVE_ONLY, F.GET_OFF: [{"target_obj_id": 900101}]}}
        w = world_of(S.obs(RED, [car], listing, passengers=[aboard], step=200))
        step = T.step_lifts(w, ((900101, 900102, 1110, M.CARRYING, 150),), 1900)
        self.assertEqual(step.orders, ())
        self.assertEqual(step.carry_moves, ((900102, 1110),))
        overdue = T.step_lifts(w, ((900101, 900102, 1110, M.CARRYING, 150),), 150)
        self.assertEqual(overdue.orders[0][1]["type"], F.GET_OFF)


class RuleGapTests(unittest.TestCase):
    def test_promising_needs_a_zbar_of_one_half(self):
        open_gate = [{"batch": "A1", "open": True, "reason": "x"}]
        near = [live_facts(p, 122.5 if p <= 16 else 300) for p in range(1, 25)]  # z = 0.45
        self.assertEqual(sl.disposition(near, open_gate)["disposition"], "S34_INTEGRATED_INCONCLUSIVE")
        at = [live_facts(p, 125.0 if p <= 16 else 300) for p in range(1, 25)]   # z = 0.5
        self.assertEqual(sl.disposition(at, open_gate)["disposition"], "S34_INTEGRATED_PROMISING")

    def test_the_deadlock_gate_is_three_hundred_steps(self):
        for wait, selected in ((299, "MO"), (300, "CT")):
            s = summaries(mo=(2000, 2000))
            s["MO"]["model"]["M-v2"]["max_wait"] = wait
            self.assertEqual(so.select(s)["selected"], selected, wait)


class ObserverGapTests(unittest.TestCase):
    def test_a_tampered_live_decision_is_a_mismatch(self):
        costs = MoveCosts.from_raw(S.costs())
        timeline = S34Timeline(candidate_id(MO), MO, costs)
        a = agent(MO)
        observation = S.obs(RED, [S.unit(900101, RED, 101)], {900101: MOVE_ONLY}, cities=[S.city(808)])
        memory = a.memory
        live = a.step(observation)
        decision = {"seat": S.RED_SEAT, "faction": RED, "policy": candidate_id(MO), "observation": observation,
                    "memory": memory, "actions": live, "submitted": live, "trace": a.last_trace}
        timeline._check(0, S.RED_SEAT, decision, live, a.last_trace)
        self.assertEqual(timeline.checks.get("reconstruction_mismatch", 0), 0)
        tampered = [dict(live[0], move_path=live[0]["move_path"][:-1])]
        timeline._check(1, S.RED_SEAT, dict(decision, submitted=tampered), tampered, a.last_trace)
        self.assertEqual(timeline.checks["reconstruction_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
