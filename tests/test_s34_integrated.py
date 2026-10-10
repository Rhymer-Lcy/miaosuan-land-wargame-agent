"""Sprint 34 integrated agent: unit, adversarial and module-interaction tests on synthetic states."""

from __future__ import annotations

import copy
import itertools
import random
import unittest
from dataclasses import replace

from miaosuan_agent.boundary import ContractError, MoveCosts, Observation
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.decision.trace import digest
from miaosuan_agent.integrated import assignment as solve
from miaosuan_agent.integrated import facts as F
from miaosuan_agent.integrated import memory as M
from miaosuan_agent.integrated.agent import CommanderAgent
from miaosuan_agent.integrated.allocation import Allocator
from miaosuan_agent.integrated.config import CT, MO, VARIANTS
from miaosuan_agent.integrated.movement import Terrain
from miaosuan_agent.integrated.policy import CommanderPolicy, candidate_id
from miaosuan_agent.integrated.traffic import Traffic
from miaosuan_agent.integrated.validate import validate
from miaosuan_agent.integrated.world import State, build_world
from tests.fixtures import s34_states as S
from tests.fixtures import synthetic as syn

RED, BLUE = 0, 1
MOVE_ONLY = {F.MOVE: None}


def agent(config=MO, entry_costs=None) -> CommanderAgent:
    a = CommanderAgent(config, strict=True)
    a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs(entry_costs)})
    a.memory = replace(a.memory, deployment_sent=True)
    return a


def world_of(observation, color=RED):
    seat = S.RED_SEAT if color == RED else S.BLUE_SEAT
    return build_world(Observation.from_raw(observation), seat, color, S.ROWS, S.COLS)


def by_unit(actions):
    return {a["obj_id"]: a for a in actions if "obj_id" in a}


def path_ok(costs, start, path):
    here = start
    for h in path:
        if h not in costs.neighbours(0, here):
            return False
        here = h
    return True


class GeometryTests(unittest.TestCase):
    def test_neighbours_match_the_synthetic_grid_offsets(self):
        for h in (0, 101, 505, 1111, 606, 1100):
            self.assertEqual(sorted(F.neighbours(h, S.ROWS, S.COLS)), sorted(syn.grid_neighbours(h, S.ROWS, S.COLS)))

    def test_distance_is_symmetric_and_one_for_neighbours(self):
        for h in (101, 505, 606):
            for n in F.neighbours(h, S.ROWS, S.COLS):
                self.assertEqual(F.hex_distance(h, n), 1)
                self.assertEqual(F.hex_distance(n, h), 1)
        self.assertEqual(F.hex_distance(505, 505), 0)
        self.assertEqual(len(F.zone(505, S.ROWS, S.COLS)), 7)

    def test_hex_time_and_ranges(self):
        self.assertEqual(F.hex_time(36, 1), 20)
        self.assertEqual(F.hex_time(5, 1), 144)
        self.assertIsNone(F.hex_time(0, 1))
        self.assertEqual(F.weapon_range([37], 2), 15)
        self.assertEqual(F.weapon_range([37], 1), 10)
        self.assertIsNone(F.weapon_range([999], 2))
        self.assertEqual(F.max_weapon_range([69, 29]), 20)


class SolverTests(unittest.TestCase):
    def test_hungarian_is_exact_on_random_matrices(self):
        rng = random.Random(34)
        for _ in range(200):
            rows, cols = rng.randint(1, 5), rng.randint(1, 5)
            u = [[round(rng.uniform(-4, 9), 2) for _ in range(cols)] for _ in range(rows)]
            result = solve.hungarian(u)
            taken = [c for c in result if c is not None]
            self.assertEqual(len(taken), len(set(taken)))
            self.assertTrue(all(u[r][c] > 0 for r, c in enumerate(result) if c is not None))
            best = 0.0
            for perm in itertools.permutations(list(range(cols)) + [None] * rows, rows):
                if len([p for p in perm if p is not None]) != len({p for p in perm if p is not None}):
                    continue
                best = max(best, sum(max(0.0, u[r][c]) for r, c in enumerate(perm) if c is not None))
            self.assertAlmostEqual(solve.total(u, result), best, places=6)

    def test_greedy_respects_shared_members_and_slots(self):
        pairs = [(10.0, ("lift", 1, 2), (1, 2), "A"), (9.0, ("solo", 2), (2,), "B"), (8.0, ("solo", 3), (3,), "A"),
                 (7.0, ("solo", 3), (3,), "B"), (-1.0, ("solo", 4), (4,), "C")]
        chosen = solve.greedy(pairs)
        self.assertEqual([c[2] for c in chosen], ["A", "B"])
        self.assertEqual(chosen[1][1], (3,))


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.costs = MoveCosts.from_raw(S.costs({505: 3, 506: 3}))
        self.terrain = Terrain(self.costs)

    def test_field_equals_forward_dijkstra_costs(self):
        router = Router(self.costs)
        for start in (101, 1010, 707):
            forward = router.shortest_paths(start, 0)
            for target in (505, 909, 1111, 0):
                self.assertAlmostEqual(self.terrain.cost_to(0, start, target, frozenset()), forward.cost[target])

    def test_plan_avoids_blocked_hexes_and_is_valid(self):
        direct = self.terrain.plan(0, 503, 508, frozenset())
        self.assertTrue(self.terrain.path_is_valid(0, 503, direct, frozenset()))
        blocked = frozenset({504, 604, 404})
        detour = self.terrain.plan(0, 503, 508, frozenset(), blocked)
        self.assertTrue(detour and not set(detour) & blocked)
        self.assertTrue(self.terrain.path_is_valid(0, 503, detour, frozenset()))
        sealed = frozenset(F.neighbours(503, S.ROWS, S.COLS))
        self.assertIsNone(self.terrain.plan(0, 503, 508, frozenset(), sealed))

    def test_roadblocks_close_vehicle_modes_only(self):
        road = frozenset({504})
        self.assertNotIn(504, self.terrain.plan(0, 503, 505, road) or ())
        self.assertIsNone(self.terrain.plan(0, 503, 504, road))
        self.assertEqual(self.terrain.plan(2, 503, 504, road), (504,))


class WorldAndTrafficTests(unittest.TestCase):
    def test_states_carrier_and_allies(self):
        units = [S.unit(900101, RED, 101, path=[102], speed=0.05), S.unit(900102, RED, 101, path=[102], speed=0),
                 S.unit(900103, RED, 202, move_to_stop=30), S.unit(900104, RED, 202, type_=1, sub_type=2, get_on=40),
                 S.unit(900105, RED, 303, sub_type=1, passenger_types=[2, 4, 7]), S.unit(900106, RED, 303),
                 S.unit(900201, BLUE, 909)]
        w = world_of(S.obs(RED, units, {}, controlled=[900101, 900102, 900103, 900104, 900105]))
        states = {u.obj_id: u.state for u in w.units}
        self.assertEqual(states, {900101: State.MOVING, 900102: State.WAITING, 900103: State.TRANSITION,
                                  900104: State.BOARDING, 900105: State.SETTLED})
        self.assertTrue(w.unit(900105).carrier)
        self.assertFalse(w.unit(900103).carrier)
        self.assertEqual([a.obj_id for a in w.allies], [900106])
        self.assertEqual(w.ground_occupancy()[303], 2)
        self.assertEqual([e.obj_id for e in w.enemies], [900201])

    def test_ledger_closes_full_planned_stands(self):
        units = [S.unit(900100 + i, RED, 505) for i in range(3)] + [S.unit(900110, RED, 101, path=[102, 505],
                                                                            speed=0.05)]
        units.append(S.unit(900120, RED, 707, path=[708], speed=0))
        units += [S.unit(900130 + i, RED, 708) for i in range(4)]
        t = Traffic(world_of(S.obs(RED, units, {})))
        self.assertEqual(t.stand(505), 4)
        self.assertIn(505, t.blocked_for(101))
        self.assertFalse(t.accepts(505, 3))
        self.assertFalse(t.first_hex_open(708))
        self.assertEqual(t.blockers(), {708: (900120,)})


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.costs = MoveCosts.from_raw(S.costs())
        self.terrain = Terrain(self.costs)
        units = [S.unit(900101, RED, 505), S.unit(900102, RED, 506, path=[507], speed=0.05),
                 S.unit(900201, BLUE, 909)]
        listings = {900101: {F.MOVE: None, F.SHOOT: [{"target_obj_id": 900201, "weapon_id": 37, "attack_level": 3}]},
                    900102: {F.STOP: None}}
        self.world = world_of(S.obs(RED, units, listings, controlled=[900101, 900102]))

    def check(self, action):
        return validate([action], self.world, self.terrain, frozenset(VALIDATE_ALL), False)

    def test_accepts_listed_actions_and_rejects_the_rest(self):
        seat = S.RED_SEAT
        good_move = {"actor": seat, "type": F.MOVE, "obj_id": 900101, "move_path": [506, 507]}
        self.assertEqual(len(self.check(good_move).accepted), 1)
        shot = {"actor": seat, "type": F.SHOOT, "obj_id": 900101, "target_obj_id": 900201, "weapon_id": 37}
        self.assertEqual(len(self.check(shot).accepted), 1)
        bad = [
            dict(good_move, actor=seat + 1),
            dict(good_move, move_path=[507]),
            dict(good_move, move_path=[506, 506]),
            dict(good_move, move_path=[505, 506]),
            dict(good_move, move_path=[]),
            {"actor": seat, "type": F.MOVE, "obj_id": 900102, "move_path": [508]},
            dict(shot, weapon_id=36),
            dict(shot, target_obj_id=900999),
            {"actor": seat, "type": F.OCCUPY, "obj_id": 900101},
            {"actor": seat, "type": F.MOVE, "obj_id": 900201, "move_path": [908]},
            {"actor": seat, "type": 99, "obj_id": 900101},
            dict(good_move, extra=1),
            {"actor": seat, "type": F.END_DEPLOYMENT},
            "not a mapping",
        ]
        for action in bad:
            verdict = self.check(action)
            self.assertEqual(verdict.accepted, (), action)
            self.assertEqual(len(verdict.rejected), 1)

    def test_one_action_per_unit(self):
        a = {"actor": S.RED_SEAT, "type": F.MOVE, "obj_id": 900101, "move_path": [506]}
        verdict = validate([a, dict(a)], self.world, self.terrain, frozenset(VALIDATE_ALL), False)
        self.assertEqual(len(verdict.accepted), 1)
        self.assertIn("second action", verdict.rejected[0][2])


VALIDATE_ALL = {F.MOVE, F.SHOOT, F.GET_ON, F.GET_OFF, F.OCCUPY, F.INDIRECT, F.END_DEPLOYMENT}


class PolicyTests(unittest.TestCase):
    def test_deployment_once(self):
        a = CommanderAgent(MO, strict=True)
        a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
        first = a.step(S.obs(RED, [S.unit(900101, RED, 101)], {}, stage=1, step=0))
        self.assertEqual(first, [{"actor": S.RED_SEAT, "type": F.END_DEPLOYMENT}])
        self.assertEqual(a.step(S.obs(RED, [S.unit(900101, RED, 101)], {}, stage=1, step=0)), [])

    def test_moves_to_an_unheld_objective_on_a_valid_path(self):
        a = agent()
        actions = a.step(S.obs(RED, [S.unit(900101, RED, 101)], {900101: MOVE_ONLY}, cities=[S.city(808)]))
        move = by_unit(actions)[900101]
        self.assertEqual(move["type"], F.MOVE)
        self.assertEqual(move["move_path"][-1], 808)
        self.assertTrue(path_ok(MoveCosts.from_raw(S.costs()), 101, move["move_path"]))

    def test_occupies_before_shooting(self):
        a = agent()
        listing = {F.OCCUPY: None, F.SHOOT: [{"target_obj_id": 900201, "weapon_id": 37, "attack_level": 4}], **MOVE_ONLY}
        actions = a.step(S.obs(RED, [S.unit(900101, RED, 808), S.unit(900201, BLUE, 1111)], {900101: listing},
                               cities=[S.city(808)], controlled=[900101]))
        self.assertEqual(by_unit(actions)[900101]["type"], F.OCCUPY)

    def test_no_herd_capacity_capped_and_spread(self):
        a = agent()
        units = [S.unit(900101 + i, RED, 101) for i in range(6)]
        listings = {u["obj_id"]: MOVE_ONLY for u in units}
        actions = a.step(S.obs(RED, units, listings, cities=[S.city(808), S.city(1003, value=50)]))
        dests = [m["move_path"][-1] for m in actions if m["type"] == F.MOVE]
        self.assertEqual(sorted(set(dests)), [808, 1003])
        for d in set(dests):
            self.assertLessEqual(dests.count(d), MO.destination_cap)
        self.assertLessEqual(len(dests), 4)  # clear objectives offer two slots each

    def test_path_avoids_a_full_hex_and_waits_on_a_full_first_hex(self):
        a = agent()
        blockers = [S.unit(900110 + i, RED, 104) for i in range(4)]
        mover = S.unit(900101, RED, 103)
        actions = a.step(S.obs(RED, blockers + [mover], {900101: MOVE_ONLY}, cities=[S.city(106)],
                               controlled=[900101]))
        self.assertNotIn(104, by_unit(actions)[900101]["move_path"])
        # Every neighbour full except none: the unit is held, with a recorded reason.
        sealed = [S.unit(900200 + 10 * k + i, RED, n)
                  for k, n in enumerate(F.neighbours(103, S.ROWS, S.COLS)) for i in range(4)]
        b = agent()
        actions = b.step(S.obs(RED, sealed + [mover], {900101: MOVE_ONLY}, cities=[S.city(106)],
                               controlled=[900101]))
        self.assertNotIn(900101, by_unit(actions))
        plan = next(p for p in b.last_trace.plans if p[0] == 900101)
        self.assertIn("held", plan[5])

    def test_unreachable_and_late_objectives_get_no_move(self):
        walls = {h: 10 ** 6 for h in F.neighbours(808, S.ROWS, S.COLS)}
        a = agent(entry_costs=walls)
        actions = a.step(S.obs(RED, [S.unit(900101, RED, 101)], {900101: MOVE_ONLY}, cities=[S.city(808)],
                               max_step=200))
        self.assertEqual(actions, [])
        late = agent()
        actions = late.step(S.obs(RED, [S.unit(900101, RED, 101)], {900101: MOVE_ONLY}, cities=[S.city(1111)],
                                  step=1990, max_step=2000))
        self.assertEqual(actions, [])

    def test_holder_stays_and_the_other_unit_captures(self):
        for config in (CT, MO):
            a = agent(config)
            units = [S.unit(900101, RED, 505, type_=1, sub_type=2, basic_speed=5, value=4),
                     S.unit(900102, RED, 505, value=10)]
            listings = {900101: MOVE_ONLY, 900102: MOVE_ONLY}
            actions = a.step(S.obs(RED, units, listings, cities=[S.city(505, flag=RED, value=50), S.city(808)]))
            moved = {k for k, v in by_unit(actions).items() if v["type"] == F.MOVE}
            self.assertEqual(moved, {900102}, config.name)

    def test_recovery_steps_aside_for_a_waiting_unit(self):
        a = agent()
        standing = [S.unit(900110 + i, RED, 505) for i in range(4)]
        waiter = S.unit(900101, RED, 504, path=[505, 506], speed=0)
        listings = {u["obj_id"]: MOVE_ONLY for u in standing}
        listings[900101] = {F.STOP: None}
        actions = a.step(S.obs(RED, standing + [waiter], listings, cities=[]))
        moves = [m for m in actions if m["type"] == F.MOVE]
        self.assertEqual(len(moves), 1)
        self.assertNotIn(moves[0]["move_path"][-1], (504, 505, 506))
        self.assertTrue(all(m["obj_id"] != 900101 for m in actions))  # never a stop on the waiting unit

    def test_fire_reserves_targets_and_beats_moving(self):
        a = agent()
        option = [{"target_obj_id": 900201, "weapon_id": 37, "attack_level": 3}]
        units = [S.unit(900101, RED, 505), S.unit(900102, RED, 506), S.unit(900201, BLUE, 509)]
        listings = {900101: {**MOVE_ONLY, F.SHOOT: option}, 900102: {**MOVE_ONLY, F.SHOOT: option}}
        actions = a.step(S.obs(RED, units, listings, cities=[S.city(1111)], controlled=[900101, 900102]))
        shots = [x for x in actions if x["type"] == F.SHOOT]
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["obj_id"], 900101)

    def test_transport_life_cycle(self):
        a = agent(MO)
        inf = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2, 4, 7], value=8)
        listings = {900101: {**MOVE_ONLY, F.GET_ON: [{"target_obj_id": 900102}]}, 900102: MOVE_ONLY}
        cities = [S.city(1110)]
        actions = by_unit(a.step(S.obs(RED, [inf, car], listings, cities=cities)))
        self.assertEqual(actions[900101], {"actor": S.RED_SEAT, "type": F.GET_ON, "obj_id": 900101,
                                           "target_obj_id": 900102})
        self.assertNotIn(900102, actions)
        self.assertEqual(a.memory.lifts[0][3], M.BOARDING)
        # Boarding in progress: both held.
        inf2 = dict(inf, get_on_remain_time=40)
        actions = by_unit(a.step(S.obs(RED, [inf2, car], {900102: MOVE_ONLY}, cities=cities, step=11)))
        self.assertEqual(actions, {})
        # Aboard: the carrier moves to the objective.
        aboard = dict(inf, on_board=1)
        loaded = dict(car, passenger_ids=[900101])
        actions = by_unit(a.step(S.obs(RED, [loaded], {900102: MOVE_ONLY}, cities=cities, passengers=[aboard],
                                       step=90)))
        self.assertEqual(actions[900102]["move_path"][-1], 1110)
        self.assertEqual(a.memory.lifts[0][3], M.CARRYING)
        # Arrived and settled: disembark.
        arrived = dict(loaded, cur_hex=1110)
        listing = {900102: {**MOVE_ONLY, F.GET_OFF: [{"target_obj_id": 900101}]}}
        actions = by_unit(a.step(S.obs(RED, [arrived], listing, cities=cities, passengers=[aboard], step=400)))
        self.assertEqual(actions[900102]["type"], F.GET_OFF)
        # On the ground again: the lift is done and the passenger holds the objective.
        down = dict(inf, cur_hex=1110)
        a.step(S.obs(RED, [down, arrived], {900101: MOVE_ONLY, 900102: MOVE_ONLY}, cities=cities, step=480))
        self.assertEqual(a.memory.lifts, ())
        self.assertEqual(a.memory.task_of(900101)[1:3], (M.HOLD, 1110))

    def test_ct_never_lifts(self):
        a = agent(CT)
        inf = S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, RED, 101, sub_type=1, passenger_types=[2], value=8)
        listings = {900101: {**MOVE_ONLY, F.GET_ON: [{"target_obj_id": 900102}]}, 900102: MOVE_ONLY}
        actions = a.step(S.obs(RED, [inf, car], listings, cities=[S.city(1110)]))
        self.assertFalse(any(x["type"] == F.GET_ON for x in actions))

    def test_indirect_fire_keeps_clear_of_own_units(self):
        art = S.unit(900101, RED, 0, sub_type=3, basic_speed=36, value=0)
        listing = {900101: {F.INDIRECT: [{"weapon_id": 72}]}}
        far = S.unit(900201, BLUE, 1111)
        a = agent(MO)
        units = [art, far]
        w = world_of(S.obs(RED, units, listing))
        self.assertGreaterEqual(F.hex_distance(0, 1111), F.ARTILLERY_MIN_RANGE)
        actions = by_unit(a.step(S.obs(RED, units, listing, controlled=[900101])))
        self.assertEqual(actions[900101]["jm_pos"], 1111)
        self.assertEqual(actions[900101]["type"], F.INDIRECT)
        self.assertEqual(a.memory.fire_orders[0][:1], (1111,))
        near_own = S.unit(900102, RED, 1110)
        b = agent(MO)
        actions = by_unit(b.step(S.obs(RED, [art, far, near_own], {**listing, 900102: {}}, controlled=[900101, 900102])))
        self.assertNotIn(900101, actions)
        c = agent(CT)
        self.assertEqual(c.step(S.obs(RED, units, listing, controlled=[900101])), [])
        self.assertIsNotNone(w)

    def test_routes_avoid_live_impacts(self):
        a = agent(MO)
        point = {"obj_id": 900999, "weapon_id": 72, "pos": 104, "status": 1, "fly_time": 0, "boom_time": 200}
        actions = by_unit(a.step(S.obs(RED, [S.unit(900101, RED, 102)], {900101: MOVE_ONLY}, cities=[S.city(106)],
                                       jm_points=[point])))
        self.assertTrue(set(actions[900101]["move_path"]).isdisjoint(F.zone(104, S.ROWS, S.COLS)))

    def test_fallback_to_baseline_v2_is_recorded(self):
        a = agent(MO)

        def broken(*args, **kwargs):
            raise RuntimeError("planted")
        a.policy.allocator.allocate = broken
        actions = a.step(S.obs(RED, [S.unit(900101, RED, 101)], {900101: MOVE_ONLY}, cities=[S.city(808)]))
        self.assertEqual(by_unit(actions)[900101]["type"], F.MOVE)
        self.assertIn("planted", a.last_trace.fallback)
        self.assertEqual(a.memory.fallbacks, 1)

    def test_contract_violation_yields_nothing(self):
        a = CommanderAgent(MO)
        a.setup({"seat": S.RED_SEAT, "faction": RED, "cost_data": S.costs()})
        bad = S.obs(RED, [S.unit(900101, RED, 101)], {900101: MOVE_ONLY})
        del bad["time"]
        self.assertEqual(a.step(bad), [])
        self.assertIsNotNone(a.last_trace.error)
        strict = agent()
        with self.assertRaises(ContractError):
            strict.step(bad)

    def test_determinism_replay_and_order_independence(self):
        units = [S.unit(900101 + i, RED, 101 + i) for i in range(5)] + [S.unit(900201, BLUE, 909)]
        listings = {900101 + i: MOVE_ONLY for i in range(5)}
        observation = S.obs(RED, units, listings, cities=[S.city(808), S.city(1003, value=50)],
                            controlled=[900101 + i for i in range(5)])
        a, b = agent(), agent()
        memory = a.memory
        first = a.step(copy.deepcopy(observation))
        shuffled = copy.deepcopy(observation)
        shuffled["operators"].reverse()
        second = b.step(shuffled)
        self.assertEqual(first, second)
        self.assertEqual(digest(a.replay(observation, memory)), digest(a.last_trace))

    def test_uncontrolled_units_never_act(self):
        units = [S.unit(900101, RED, 101), S.unit(900102, RED, 102)]
        listings = {900101: MOVE_ONLY, 900102: MOVE_ONLY}
        a = agent()
        actions = a.step(S.obs(RED, units, listings, cities=[S.city(808)], controlled=[900101]))
        self.assertEqual(set(by_unit(actions)), {900101})

    def test_every_unit_has_a_recorded_reason(self):
        units = [S.unit(900101, RED, 101), S.unit(900102, RED, 102, path=[103], speed=0.05),
                 S.unit(900103, RED, 104, sub_type=3, value=0)]
        a = agent()
        a.step(S.obs(RED, units, {900101: MOVE_ONLY, 900102: {F.STOP: None}, 900103: {}}, cities=[S.city(808)]))
        plans = {p[0]: p for p in a.last_trace.plans}
        self.assertEqual(set(plans), {900101, 900102, 900103})
        self.assertTrue(all(p[5] for p in plans.values()))

    def test_memory_is_bounded(self):
        seen = [(900000 + i, 101, 2, 5) for i in range(500)]
        kept = M.updated_sightings((), seen, 10)
        self.assertEqual(len(kept), M.MAX_SIGHTINGS)
        self.assertEqual(M.updated_sightings(kept, (), 10 + M.SIGHTING_TTL + 1), ())

    def test_identities_are_distinct(self):
        ids = {candidate_id(c) for c in VARIANTS.values()}
        self.assertEqual(len(ids), len(VARIANTS))
        self.assertTrue(all(i.startswith("s34-integrated-") for i in ids))


class AllocationTests(unittest.TestCase):
    def test_a_unit_that_cannot_arrive_takes_no_slot(self):
        terrain = Terrain(MoveCosts.from_raw(S.costs()))
        allocator = Allocator(MO, terrain)
        units = [S.unit(900101, RED, 101, type_=1, sub_type=2, basic_speed=5, value=4)]
        w = world_of(S.obs(RED, units, {900101: MOVE_ONLY}, cities=[S.city(1111)], step=1500))
        pictures = allocator.pictures(w, (), frozenset({900101}))
        self.assertEqual(allocator.allocate(w, M.CommanderMemory(), list(w.units), pictures), [])

    def test_committed_movers_fill_slots(self):
        terrain = Terrain(MoveCosts.from_raw(S.costs()))
        allocator = Allocator(CT, terrain)
        units = [S.unit(900101, RED, 806, path=[807, 808], speed=0.05), S.unit(900102, RED, 101)]
        w = world_of(S.obs(RED, units, {900102: MOVE_ONLY}, cities=[S.city(808)]))
        pictures = allocator.pictures(w, (), frozenset({900102}))
        self.assertEqual(pictures[0].inbound[0][0], 900101)
        chosen = allocator.allocate(w, M.CommanderMemory(), [w.unit(900102)], pictures)
        self.assertEqual([a.slot for a in chosen], [1])


if __name__ == "__main__":
    unittest.main()
