"""OFFLINE design candidates of Sprint 14 (``experiments/t9_redistribution.py``). SYNTHETIC observations.

Geometry is never typed by hand: every route cost, free-flow time and shared prefix a test relies on is computed with
the project's router on the 10 x 10 synthetic grid (uniform cost 1 per hex) and asserted as a precondition. Vehicles
have ``basic_speed`` 36 (20 steps per hex), infantry 5 (144 steps per hex). The clock is ``cur_step`` 100 of
``max_step`` 2880 unless a test needs the end of the game.
"""

from __future__ import annotations

import ast
import itertools
import json
import random
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import Memory, digest, gate
from miaosuan_agent.decision.routing import Router, move_mode
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments import t9_redistribution as tr
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn

SEAT, RED = syn.RED_SEAT, 0
A, B, C = 505, 909, 5
VEHICLE, INFANTRY = (2, 36), (1, 5)
ROUTER = Router(MoveCosts.from_raw(syn.cost_data()))
SHOT = {"actor": SEAT, "type": 2, "obj_id": 999999, "target_obj_id": 1, "weapon_id": 1}


def cost(start: int, goal: int, kind=VEHICLE) -> float:
    return ROUTER.shortest_paths(start, move_mode(kind[0], 0)).cost[goal]


def route(start: int, goal: int, kind=VEHICLE) -> List[int]:
    return list(ROUTER.shortest_paths(start, move_mode(kind[0], 0)).path_to(goal))


def unit(obj_id: int, hex_: int, kind=VEHICLE, move_path: Sequence[int] = (), color: int = RED,
         **extra: Any) -> Dict[str, Any]:
    record = syn.unit(obj_id, color, hex_, unit_type=kind[0], move_path=move_path)
    record.update({"basic_speed": kind[1], "speed": 0 if not move_path else 1, "stop": 0 if move_path else 1})
    record.update(extra)
    return record


def observation(units: Sequence[Dict[str, Any]], cities: Sequence[int] = (A, B), *, values: Optional[Dict[int, int]] = None,
                movable: Optional[Sequence[int]] = None, cur_step: int = 100, max_step: Optional[int] = 2880,
                stage: int = 2, held: Sequence[int] = ()) -> Observation:
    own = [u["obj_id"] for u in units if u["color"] == RED]
    ids = movable if movable is not None else [u["obj_id"] for u in units if not u["move_path"]]
    values = values or {}
    raw = syn.build_observation(units=units, valid_actions={i: {1: None} for i in ids}, stage=stage, cur_step=cur_step,
                                seats={SEAT: syn.seat_record(SEAT, RED, own, True)},
                                cities=[syn.city(c, flag=RED if c in held else -1, value=values.get(c, 7))
                                        for c in cities])
    if max_step is None:
        del raw["time"]["max_step"]
    else:
        raw["time"]["max_step"] = max_step
    return Observation.from_raw(raw, Origin.ENGINE)


def outcome(result: tr.Allocation) -> tuple:
    return (dict(result.selected), {u: (o.objective, o.path) for u, o in result.redirected.items()},
            {u: tuple(p) for u, p in result.staged.items()}, dict(result.withheld))


class RedistributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())

    # -- helpers -------------------------------------------------------------------------------------------------
    def baseline(self, obs: Observation):
        return ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())

    def allocate(self, obs: Observation, rule: Optional[str], actions=None) -> tr.Allocation:
        policy = ShootReservationPolicy(self.costs)
        base = policy.decide(obs, SEAT, RED, Memory()).actions if actions is None else actions
        return tr.allocate(obs, SEAT, RED, base, policy.router, None if rule is None else tr.RULES[rule])

    @staticmethod
    def moves(actions) -> Dict[int, List[int]]:
        return {a["obj_id"]: list(a["move_path"]) for a in actions if a["type"] == 1}

    def overflow_scene(self) -> Observation:
        """Four near vehicles take A's places; two more claim A and have B within twice their route cost."""
        near = [unit(903000 + k, h) for k, h in enumerate((504, 506, 404, 604))]
        far = [unit(903010, 408), unit(903011, 806)]
        for record in far:
            h = record["cur_hex"]
            self.assertLess(cost(h, A), cost(h, B))
            self.assertLessEqual(cost(h, B), tr.DETOUR * cost(h, A))
        self.assertTrue(all(cost(u["cur_hex"], A) < cost(f["cur_hex"], A) for u in near for f in far))
        return observation(near + far)

    # -- stage 1 is v3 ---------------------------------------------------------------------------------------------
    def test_stage_one_alone_equals_v3_on_every_shape(self) -> None:
        shapes = [self.overflow_scene(), self.seven_objectives(),
                  observation([unit(903020 + k, h) for k, h in enumerate((503, 507, 303, 703, 100))], cities=(A,)),
                  observation([unit(903030, 503, INFANTRY)], cur_step=2880 - 100)]
        for obs in shapes:
            policy = ShootReservationPolicy(self.costs)
            base = policy.decide(obs, SEAT, RED, Memory()).actions
            mine = tr.allocate(obs, SEAT, RED, base, policy.router, None)
            v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
            self.assertEqual([dict(a) for a in mine.actions], [dict(a) for a in v3.actions])
            self.assertEqual((mine.selected, mine.staged, mine.withheld), (v3.selected, v3.staged, v3.withheld))
            self.assertEqual(mine.redirected, {})
            for name in tr.RULES:
                ruled = self.allocate(obs, name, base)
                self.assertEqual(ruled.selected, v3.selected, name)  # same-objective admissions never reduced

    # -- what may be redirected ------------------------------------------------------------------------------------
    def test_only_overflow_is_redirected_to_an_unheld_objective_under_capacity(self) -> None:
        obs = self.overflow_scene()
        for name in tr.RULES:
            if tr.RULES[name].horizon or tr.RULES[name].min_prefix:
                continue
            result = self.allocate(obs, name)
            self.assertEqual(set(result.selected), {903000, 903001, 903002, 903003}, name)
            self.assertEqual({u: o.objective for u, o in result.redirected.items()}, {903010: B, 903011: B}, name)
            moves = self.moves(result.actions)
            self.assertEqual(moves[903010], route(408, B))
            self.assertEqual(moves[903011], route(806, B))
            self.assertEqual(result.staged, {})
            self.assertEqual(result.withheld, {})

    def test_no_redirect_to_an_objective_the_side_holds(self) -> None:
        obs = observation(self.overflow_scene_units(), held=(B,))
        result = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(result.redirected, {})
        self.assertEqual(len(result.staged) + len(result.withheld), 2)

    def overflow_scene_units(self) -> List[Dict[str, Any]]:
        return [unit(903000 + k, h) for k, h in enumerate((504, 506, 404, 604))] + [unit(903010, 408),
                                                                                    unit(903011, 806)]

    def test_capacity_at_the_alternative_counts_incumbents_selections_and_redirects(self) -> None:
        standing = [unit(903040 + k, B) for k in range(3)]
        obs = observation(self.overflow_scene_units() + standing, movable=[903000, 903001, 903002, 903003,
                                                                           903010, 903011])
        result = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(len(result.redirected), 1)
        winner, = result.redirected
        loser = ({903010, 903011} - {winner}).pop()
        claim = result.claimants
        self.assertLess(tb.free_flow_key(claim[winner]), tb.free_flow_key(claim[loser]))  # rank order decides
        self.assertIn(loser, set(result.staged) | set(result.withheld))
        base = list(self.baseline(obs).actions)
        reversed_ = self.allocate(obs, "feasible-value-redirect", list(reversed(base)))
        self.assertEqual(set(reversed_.redirected), {winner})  # the rank, not the emission order, decides
        batch = self.allocate(obs, "batch-value-redirect")
        self.assertEqual(len(batch.redirected), 1)

    def test_late_claimants_are_never_redirected(self) -> None:
        obs = observation([unit(903050, 503, INFANTRY)] + [unit(903051 + k, h) for k, h in
                                                          enumerate((504, 506, 404, 604))], cur_step=2880 - 200)
        result = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(result.claimants[903050].status, tr.LATE)
        self.assertNotIn(903050, result.redirected)
        self.assertEqual(sum(result.dropped.values()), 0)  # no alternative is even considered for it

    def test_late_claimant_boundary_is_exact_as_in_v3(self) -> None:
        probe = observation([unit(903055, 503, INFANTRY)])
        free_flow = 144 * len(route(503, A, INFANTRY))
        for cur_step, status in ((2880 - free_flow, tr.LATE), (2880 - free_flow - 1, tr.FULL)):
            obs = observation([unit(903055, 503, INFANTRY)], cur_step=cur_step)
            result = self.allocate(obs, "feasible-value-redirect")
            self.assertEqual(result.claimants[903055].status, status)
            policy = ShootReservationPolicy(self.costs)
            base = policy.decide(obs, SEAT, RED, Memory()).actions
            v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
            self.assertEqual((result.selected, result.staged, result.withheld), (v3.selected, v3.staged, v3.withheld))
        self.assertIsNotNone(probe)

    def test_movers_that_cannot_arrive_hold_no_place_so_nothing_overflows(self) -> None:
        path = route(100, A, INFANTRY)
        far = [unit(903120 + k, 100, INFANTRY, move_path=path) for k in range(tr.CAPACITY)]
        near = [unit(903130 + k, h) for k, h in enumerate((504, 506, 404, 604))]
        bound = 144 * (len(path) - 1)
        obs = observation(far + near, cur_step=2880 - bound)
        result = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(result.objectives[A]["phantom"], tr.CAPACITY)
        self.assertEqual(set(result.selected), {903130, 903131, 903132, 903133})
        self.assertEqual(result.redirected, {})

    def test_detour_bound_is_inclusive_at_exactly_twice_the_cost(self) -> None:
        near = [unit(903060 + k, h) for k, h in enumerate((405, 406, 504, 506))]
        self.assertEqual(cost(607, B), tr.DETOUR * cost(607, A))
        self.assertGreater(cost(503, B), tr.DETOUR * cost(503, A))
        self.assertTrue(all(cost(u["cur_hex"], A) < min(cost(607, A), cost(503, A)) for u in near))
        result = self.allocate(observation(near + [unit(903065, 607)]), "feasible-value-redirect")
        self.assertIn(903065, result.redirected)
        result = self.allocate(observation(near + [unit(903066, 503)]), "feasible-value-redirect")
        self.assertNotIn(903066, result.redirected)
        self.assertGreaterEqual(result.dropped["detour bound"], 1)

    def test_redirect_must_arrive_before_the_end_with_an_exact_boundary(self) -> None:
        near = [unit(903070 + k, h) for k, h in enumerate((504, 506, 404, 604))]
        probe = observation(near + [unit(903075, 408)])
        free_flow = 20 * len(route(408, B))
        own = 20 * len(route(408, A))
        self.assertLess(own, free_flow)
        at_end = self.allocate(observation(near + [unit(903075, 408)], cur_step=2880 - free_flow), "feasible-value-redirect")
        self.assertEqual(at_end.claimants[903075].status, tr.FULL)
        self.assertNotIn(903075, at_end.redirected)
        self.assertGreaterEqual(at_end.dropped[tr.LATE], 1)
        before = self.allocate(observation(near + [unit(903075, 408)], cur_step=2880 - free_flow - 1),
                               "feasible-value-redirect")
        self.assertIn(903075, before.redirected)
        self.assertLess(before.redirected[903075].free_flow + 2880 - free_flow - 1, 2880)
        self.assertIsNotNone(probe)

    def test_horizon_is_inclusive(self) -> None:
        near = [unit(903080 + k, h) for k, h in enumerate((504, 506, 404, 604))]
        far = unit(903085, 307, INFANTRY)
        obs = observation(near + [far])
        free_flow = 144 * len(route(307, B, INFANTRY))
        result = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(result.redirected[903085].free_flow, free_flow)
        self.assertGreater(free_flow, 720)
        self.assertLessEqual(free_flow, 1440)
        self.assertIn(903085, self.allocate(obs, "feasible-value-redirect-h1440").redirected)
        short = self.allocate(obs, "feasible-value-redirect-h720")
        self.assertNotIn(903085, short.redirected)
        self.assertGreaterEqual(short.dropped["beyond the redirect horizon"], 1)
        rule = tr.Rule("probe", "value", horizon=free_flow)
        policy = ShootReservationPolicy(self.costs)
        base = policy.decide(obs, SEAT, RED, Memory()).actions
        self.assertIn(903085, tr.allocate(obs, SEAT, RED, base, policy.router, rule).redirected)
        rule = tr.Rule("probe", "value", horizon=free_flow - 1)
        self.assertNotIn(903085, tr.allocate(obs, SEAT, RED, base, policy.router, rule).redirected)

    def test_corridor_rules_keep_a_share_of_baseline_paths_as_prefix(self) -> None:
        sharing, diverging = 400, 9
        self.assertEqual(tr.shared_prefix(route(sharing, A), route(sharing, B)), 5)
        self.assertEqual(len(route(sharing, A)), 6)
        self.assertEqual(tr.shared_prefix(route(diverging, A), route(diverging, B)), 0)
        near = [unit(903090 + k, h) for k, h in enumerate((504, 506, 404, 604))]
        obs = observation(near + [unit(903095, sharing), unit(903096, diverging)])
        everyone = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(set(everyone.redirected), {903095, 903096})
        for name in ("corridor-value-redirect-p25", "corridor-value-redirect-p50", "corridor-value-redirect-p75"):
            result = self.allocate(obs, name)
            self.assertEqual(set(result.redirected), {903095}, name)
            self.assertEqual(result.redirected[903095].prefix, 5)
        boundary = tr.Rule("probe", "value", min_prefix=5 / 6)
        policy = ShootReservationPolicy(self.costs)
        base = policy.decide(obs, SEAT, RED, Memory()).actions
        self.assertIn(903095, tr.allocate(obs, SEAT, RED, base, policy.router, boundary).redirected)
        above = tr.Rule("probe", "value", min_prefix=5 / 6 + 1e-9)
        self.assertNotIn(903095, tr.allocate(obs, SEAT, RED, base, policy.router, above).redirected)

    # -- ranking ---------------------------------------------------------------------------------------------------
    def test_value_rank_prefers_cost_per_value_and_cost_rank_prefers_cost(self) -> None:
        h = 307
        self.assertLess(cost(h, A), cost(h, C))
        self.assertLess(cost(h, C), cost(h, B))
        self.assertLessEqual(cost(h, B), tr.DETOUR * cost(h, A))
        values = {A: 50, B: 80, C: 10}
        self.assertLess(cost(h, B) / 80, cost(h, C) / 10)
        near = [unit(903100 + k, x) for k, x in enumerate((504, 506, 404, 604))]
        obs = observation(near + [unit(903105, h)], cities=(A, B, C), values=values)
        self.assertEqual(self.moves(self.baseline(obs).actions)[903105][-1], A)
        self.assertEqual(self.allocate(obs, "feasible-value-redirect").redirected[903105].objective, B)
        self.assertEqual(self.allocate(obs, "feasible-cost-redirect").redirected[903105].objective, C)

    def test_greedy_and_batch_are_free_of_emission_order(self) -> None:
        obs = self.seven_objectives()
        base = list(self.baseline(obs).actions)
        rng = random.Random(14)
        orders = [list(reversed(range(len(base))))] + [rng.sample(range(len(base)), len(base)) for _ in range(6)]
        for name in tr.RULES:
            reference = outcome(self.allocate(obs, name, base))
            for order in orders:
                self.assertEqual(outcome(self.allocate(obs, name, [base[i] for i in order])), reference, name)

    def test_batch_redirects_more_when_greedy_order_strands_a_claimant(self) -> None:
        # X (faster) prefers B but could also use C; Y's only alternative is B; B and C have one place each.
        options = {1: [self.option(B, 1.0), self.option(C, 2.0)], 2: [self.option(B, 1.5)]}
        counted = {B: tr.CAPACITY - 1, C: tr.CAPACITY - 1}
        batch = tr.batch_assign([1, 2], options, counted)
        self.assertEqual({u: o.objective for u, o in batch.items()}, {1: C, 2: B})
        self.assertEqual(counted, {B: tr.CAPACITY - 1, C: tr.CAPACITY - 1})

    @staticmethod
    def option(objective: int, weight: float) -> tr.Option:
        return tr.Option(objective, {"objective": objective}, (objective,), weight, 1.0, 1, 0, (weight, weight, objective))

    def test_batch_assignment_is_a_minimum_cost_maximum_matching_against_brute_force(self) -> None:
        rng = random.Random(1414)
        objectives = [101, 202, 303]
        for trial in range(300):
            units = list(range(rng.randint(1, 5)))
            options = {}
            for u in units:
                chosen = rng.sample(objectives, rng.randint(0, 3))
                options[u] = sorted((self.option(o, rng.choice([0.25, 0.5, 1.0, 1.5, 2.0])) for o in chosen),
                                    key=lambda x: x.key)
            counted = {o: tr.CAPACITY - rng.randint(0, 2) for o in objectives}
            got = tr.batch_assign(units, options, counted)
            best = (0, 0.0)
            for assignment in itertools.product(*[[None] + list(options[u]) for u in units]):
                load: Dict[int, int] = {}
                for o in assignment:
                    if o is not None:
                        load[o.objective] = load.get(o.objective, 0) + 1
                if any(counted[o] + n > tr.CAPACITY for o, n in load.items()):
                    continue
                size = sum(1 for o in assignment if o is not None)
                total = sum(o.key[0] for o in assignment if o is not None)
                if size > best[0] or (size == best[0] and total < best[1] - 1e-12):
                    best = (size, total)
            load = {}
            for u, o in got.items():
                self.assertIn(o, options[u])
                load[o.objective] = load.get(o.objective, 0) + 1
            self.assertTrue(all(counted[o] + n <= tr.CAPACITY for o, n in load.items()), trial)
            self.assertEqual(len(got), best[0], trial)
            self.assertAlmostEqual(sum(o.key[0] for o in got.values()), best[1], places=9, msg=str(trial))
            again = tr.batch_assign(list(reversed(units)), {u: options[u] for u in reversed(units)}, dict(counted))
            self.assertEqual(len(again), len(got))

    # -- invariants on a larger shape ---------------------------------------------------------------------------------
    def seven_objectives(self) -> Observation:
        cities = (101, 105, 108, 404, 707, 902, 908)
        starts = [100 + i for i in range(10)] + [900 + i for i in range(10)] + [500 + i for i in range(10)]
        units = [unit(904000 + i, h) for i, h in enumerate(starts) if h not in cities]
        return observation(units, cities=cities, values={101: 50, 105: 80, 108: 50, 404: 80, 707: 50, 902: 80,
                                                          908: 50})

    def test_seven_objective_shape_respects_capacity_routes_and_unrelated_actions(self) -> None:
        obs = self.seven_objectives()
        base = list(self.baseline(obs).actions)
        mixed = base[:5] + [SHOT] + base[5:]
        cities = (101, 105, 108, 404, 707, 902, 908)
        redirected_any = False
        for name, rule in tr.RULES.items():
            result = self.allocate(obs, name, mixed)
            self.assertIsNone(result.error, name)
            self.assertEqual([dict(a) for a in result.actions if a.get("type") != 1], [SHOT], name)
            emitted = [a["obj_id"] for a in result.actions if a.get("type") == 1]
            self.assertEqual(emitted, [a["obj_id"] for a in base if a["obj_id"] in emitted], name)
            moves = self.moves(result.actions)
            counts = {c: sum(p[-1] == c for p in moves.values()) for c in cities}
            self.assertTrue(all(v <= tr.CAPACITY for v in counts.values()), (name, counts))
            base_moves = self.moves(base)
            for obj_id, path in moves.items():
                self.assertIn(obj_id, base_moves, name)  # nothing invented
                if obj_id in result.redirected:
                    option = result.redirected[obj_id]
                    self.assertEqual(path, route(self.hex_of(obs, obj_id), path[-1]), name)
                    self.assertNotEqual(path[-1], base_moves[obj_id][-1])
                    self.assertLessEqual(option.cost, tr.DETOUR * option.base_cost)
                    self.assertLess(100 + option.free_flow, 2880)
                    if rule.horizon is not None:
                        self.assertLessEqual(option.free_flow, rule.horizon)
                    if rule.min_prefix is not None:
                        self.assertGreaterEqual(option.prefix, rule.min_prefix * len(base_moves[obj_id]))
                    redirected_any = True
                elif path != base_moves[obj_id]:
                    self.assertEqual(path, base_moves[obj_id][:len(path)], name)
                    self.assertNotIn(path[-1], cities, name)
        self.assertTrue(redirected_any)

    @staticmethod
    def hex_of(obs: Observation, obj_id: int) -> int:
        return next(u.cur_hex for u in obs.operators() if u.obj_id == obj_id)

    def test_repeated_and_fresh_router_results_are_identical(self) -> None:
        obs = self.seven_objectives()
        base = list(self.baseline(obs).actions)
        for name in tr.RULES:
            first = self.allocate(obs, name, base)
            fresh_router = Router(self.costs)
            second = tr.allocate(obs, SEAT, RED, base, fresh_router, tr.RULES[name])
            self.assertEqual(outcome(first), outcome(second), name)
            self.assertEqual([dict(a) for a in first.actions], [dict(a) for a in second.actions], name)

    # -- gate and failure ----------------------------------------------------------------------------------------------
    def test_redirect_rejected_by_the_gate_is_withheld(self) -> None:
        obs = self.overflow_scene()
        real = gate.check

        def reject_redirects(proposals, context, router):
            result = real(proposals, context, router)
            moved = [p for p in proposals if p.get("type") == 1 and p["move_path"][-1] == B]
            return gate.GateResult(tuple(p for p in result.accepted if p not in moved),
                                   tuple(result.rejected) + tuple(gate.Rejection(1, p["obj_id"], "planted")
                                                                  for p in moved))

        with mock.patch.object(tr.gate, "check", side_effect=reject_redirects):
            result = self.allocate(obs, "feasible-value-redirect")
        self.assertEqual(result.redirected, {})
        self.assertEqual(result.withheld, {903010: "redirect rejected by the gate", 903011: "redirect rejected by the gate"})
        self.assertEqual(len(self.moves(result.actions)), tr.CAPACITY)

    def test_internal_failure_withholds_every_ground_objective_move_and_keeps_the_rest(self) -> None:
        obs = self.overflow_scene()
        with mock.patch.object(tr, "path_times", side_effect=RuntimeError("planted")):
            result = self.allocate(obs, "feasible-value-redirect", list(self.baseline(obs).actions) + [SHOT])
        self.assertEqual([dict(a) for a in result.actions], [SHOT])
        self.assertIn("planted", result.error)
        policy = tr.POLICIES["feasible-value-redirect"](self.costs)
        with mock.patch.object(tr, "path_times", side_effect=RuntimeError("planted")):
            decision = policy.decide(obs, SEAT, RED, ea.AddonMemory())
        self.assertEqual(decision.actions, ())
        self.assertIn("error", [json.loads(c)["kind"] for c in decision.trace.changes])

    def test_non_play_stage_and_no_move_are_unchanged(self) -> None:
        obs = observation([unit(903110, 503)], stage=1)
        for name in tr.RULES:
            result = self.allocate(obs, name)
            self.assertEqual([dict(a) for a in result.actions], [dict(a) for a in self.baseline(obs).actions])
        self.assertEqual(tr.allocate(self.overflow_scene(), SEAT, RED, [SHOT], ROUTER, tr.RULES["batch-value-redirect"]
                                     ).actions, (SHOT,))

    # -- identities, policies, scope ---------------------------------------------------------------------------------
    def test_frozen_rule_table(self) -> None:
        table = {name: (r.rank, r.horizon, r.min_prefix, r.batch, r.identity) for name, r in tr.RULES.items()}
        self.assertEqual(table, {
            "feasible-cost-redirect": ("cost", None, None, False, "t9-feasible-cost-redirect-v4"),
            "feasible-value-redirect": ("value", None, None, False, "t9-feasible-value-redirect-v4"),
            "feasible-value-redirect-h1440": ("value", 1440, None, False, "t9-feasible-value-redirect-h1440-v4"),
            "feasible-value-redirect-h720": ("value", 720, None, False, "t9-feasible-value-redirect-h720-v4"),
            "corridor-value-redirect-p25": ("value", None, 0.25, False, "t9-corridor-value-redirect-p25-v4"),
            "corridor-value-redirect-p50": ("value", None, 0.5, False, "t9-corridor-value-redirect-p50-v4"),
            "corridor-value-redirect-p75": ("value", None, 0.75, False, "t9-corridor-value-redirect-p75-v4"),
            "batch-value-redirect": ("value", None, None, True, "t9-batch-value-redirect-v4")})
        self.assertEqual((tr.DETOUR, tr.CAPACITY, tr.STAGE_CAP), (2.0, 4, 3))
        self.assertEqual({p.identity for p in tr.POLICIES.values()}, {r.identity for r in tr.RULES.values()})

    def test_policy_trace_records_redirects_and_agent_replay_reproduces_it(self) -> None:
        obs = self.overflow_scene()
        policy = tr.POLICIES["feasible-value-redirect"](self.costs)
        decision = policy.decide(obs, SEAT, RED, ea.AddonMemory())
        kinds = [json.loads(c)["kind"] for c in decision.trace.changes]
        self.assertEqual(kinds.count("redirect"), 2)
        self.assertEqual(decision.trace.policy, "t9-feasible-value-redirect-v4")
        agent = tr.AGENTS["feasible-value-redirect"]()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(obs.fields)
        memory = agent.memory
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))

    def test_module_reads_no_analysis_code_and_holds_no_special_case_literal(self) -> None:
        source = Path(tr.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse([m for m in imported if m and "evaluation" in m], imported)
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                    and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}
        self.assertEqual(literals - {0, 1, 2, 2.0, 4, 300, 720, 1440, 0.25, 0.5, 0.75, 1_000_000}, set(), literals)


if __name__ == "__main__":
    unittest.main()
