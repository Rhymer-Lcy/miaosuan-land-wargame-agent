"""The target-bounded routing candidate against the frozen full search and against baseline-v1.

Router level: hand-made edge cases and a deterministic generated corpus (seed recorded below) compare,
for every requested target, cost, predecessor path and unreachability with the frozen full search,
including the memo over changing targets, roadblocks and modes. Policy level: whole decisions of the
candidate and of baseline-v1 on the same observations have equal actions and equal semantic traces,
and the candidate's semantic golden chain equals baseline-v1's. SYNTHETIC data only.
"""

from __future__ import annotations

import copy
import hashlib
import random
import unittest
from pathlib import Path
from types import MappingProxyType

from miaosuan_agent.boundary import MoveCosts, MoveMode, Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.decision.candidates import move_candidates
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest
from miaosuan_agent.experiments.occupy_reservation import OccupyReservationPolicy, ReservationAgent
from miaosuan_agent.experiments.routing_bounded import (CANDIDATE_ID, BoundedRouter, BoundedRoutingAgent,
                                                        BoundedRoutingPolicy)

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_occupy_reservation import GOLDEN_ACTIONS, golden_candidate_observations, random_situation, setup_info
from tests.test_routing_contract import DIAMOND, graph

ROOT = Path(__file__).resolve().parents[1]
GENERATED_SEED = 20260930
GENERATED_GRAPHS = 400
V1_DIGEST = "1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9"


def compare_routes(test, costs, start, mode, blocked, targets):
    """Bounded and full search agree on every target: cost, path, unreachability."""
    full = Router(costs)._dijkstra(start, mode, blocked)
    router = BoundedRouter(costs)
    router.targets = frozenset(targets)
    bounded = router.shortest_paths(start, mode, blocked)
    for target in targets:
        test.assertEqual(bounded.cost.get(target), full.cost.get(target), (start, target))
        test.assertEqual(bounded.path_to(target), full.path_to(target), (start, target))
    test.assertTrue(set(bounded.cost) <= set(full.cost))
    for node, value in bounded.cost.items():  # only settled hexes, with final values
        test.assertEqual(value, full.cost[node])
        test.assertEqual(bounded.path_to(node), full.path_to(node))
    return full, bounded


class IdentityTest(unittest.TestCase):
    def test_candidate_adds_one_file_and_leaves_baseline_v1_untouched(self) -> None:
        self.assertEqual(policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0], V1_DIGEST)
        self.assertEqual(rr.candidate_sources(), OCCUPY_RESERVATION_SOURCES + ("experiments/routing_bounded.py",))
        files = policy_source_digest(sources=rr.candidate_sources())[1]
        self.assertEqual(set(files) - set(policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[1]),
                         {"experiments/routing_bounded.py"})
        self.assertEqual((CANDIDATE_ID, rr.CANDIDATE_ID), ("baseline-v1-routing-bounded-candidate",) * 2)


class HandMadeRouteTest(unittest.TestCase):
    def test_edge_cases(self) -> None:
        disconnected = {1: {2: 1.0}, 2: {1: 1.0}, 7: {8: 1.0}, 8: {}}
        cycle = {1: {2: 1.0}, 2: {3: 1.0}, 3: {1: 1.0, 4: 2.0}, 4: {2: 0.5}}
        cases = [
            ("one target", graph(DIAMOND), 1, frozenset(), {4}),
            ("several targets", graph(DIAMOND), 1, frozenset(), {2, 3, 4}),
            ("equal-cost targets", graph(DIAMOND), 1, frozenset(), {2, 3}),
            ("equal-cost alternate paths", graph(DIAMOND), 1, frozenset(), {4}),
            ("unreachable", graph(disconnected), 1, frozenset(), {8}),
            ("reachable and unreachable", graph(disconnected), 1, frozenset(), {2, 7, 8}),
            ("target is the start", graph(DIAMOND), 1, frozenset(), {1}),
            ("start among targets", graph(DIAMOND), 1, frozenset(), {1, 4}),
            ("cycle", graph(cycle), 1, frozenset(), {4, 2}),
            ("blocked detour", graph(DIAMOND), 1, frozenset({2}), {4}),
            ("blocked target", graph(DIAMOND), 1, frozenset({4}), {4, 3}),
            ("start blocked", graph(DIAMOND), 1, frozenset({1}), {4}),
            ("absent target hex", graph(DIAMOND), 1, frozenset(), {99}),
        ]
        for name, costs, start, blocked, targets in cases:
            with self.subTest(case=name):
                compare_routes(self, costs, start, MoveMode.VEHICLE, blocked, targets)

    def test_modes_roadblocks_and_orders(self) -> None:
        modes = [DIAMOND, {1: {3: 1.0}, 3: {4: 5.0}, 4: {}}, DIAMOND, {1: {4: 9.0}, 4: {}}]
        costs = graph(DIAMOND, modes=modes)
        for mode in MoveMode:
            with self.subTest(mode=mode):
                compare_routes(self, costs, 1, mode, frozenset(), {4, 3})
        reversed_costs = graph({h: dict(reversed(list(n.items()))) for h, n in DIAMOND.items()})
        a = compare_routes(self, graph(DIAMOND), 1, MoveMode.VEHICLE, frozenset(), [4, 2, 3])[1]
        b = compare_routes(self, reversed_costs, 1, MoveMode.VEHICLE, frozenset(), [3, 2, 4])[1]
        self.assertEqual((dict(a.cost), dict(a.previous)), (dict(b.cost), dict(b.previous)))
        grid = ds.costs(entry_costs={304: 3, 405: 2, 506: 1.5})
        wall = frozenset(300 + c for c in range(10) if c != 9)
        for mode in (MoveMode.VEHICLE, MoveMode.INFANTRY):
            compare_routes(self, grid, 102, mode, wall, {505, 909, 707})

    def test_large_grid(self) -> None:
        rng = random.Random(GENERATED_SEED)
        raw = syn.cost_data(rows=60, cols=80, entry_costs={h: rng.choice([1, 1, 2, 3, 0.5])
                                                           for h in range(6000) if h % 100 < 80})
        costs = MoveCosts.from_raw(raw)
        full, bounded = compare_routes(self, costs, 1010, MoveMode.VEHICLE, frozenset({2020, 2021, 2022}),
                                       {1015, 3040, 5579, 4460, 2000})
        self.assertLess(len(bounded.cost), len(full.cost))


def generated_graph(rng: random.Random):
    """A random directed graph on hexes of a small grid, with tie-prone positive weights."""
    rows, cols = rng.randint(2, 20), rng.randint(2, 20)
    nodes = [r * 100 + c for r in range(rows) for c in range(cols)]
    density = rng.choice([0.05, 0.15, 0.3])
    weights = [1.0, 1.0, 1.0, 2.0, 3.0, 0.5, 1.5, 0.25]
    modes = []
    for _ in MoveMode:
        edges = {}
        for node in nodes:
            neighbours = [n for n in nodes if n != node and rng.random() < density / 4 + (abs(n - node) in (1, 100)) * density]
            rng.shuffle(neighbours)
            edges[node] = {n: rng.choice(weights) for n in neighbours}
        modes.append(edges)
    return graph(modes[0], rows=rows, cols=cols, modes=modes), nodes


class GeneratedCorpusTest(unittest.TestCase):
    """Differential comparison over a deterministic generated corpus (seed ``GENERATED_SEED``)."""

    def test_generated_graphs_agree_with_the_full_search(self) -> None:
        rng = random.Random(GENERATED_SEED)
        compared = unreachable = 0
        for index in range(GENERATED_GRAPHS):
            costs, nodes = generated_graph(rng)
            start = rng.choice(nodes)
            mode = rng.choice(list(MoveMode))
            blocked = frozenset(rng.sample(nodes, rng.randint(0, max(0, len(nodes) // 5))))
            targets = set(rng.sample(nodes, rng.randint(1, min(8, len(nodes)))))
            if rng.random() < 0.2:
                targets.add(9999)
            with self.subTest(graph=index):
                full, _ = compare_routes(self, costs, start, mode, blocked, targets)
            compared += len(targets)
            unreachable += sum(1 for t in targets if t not in full.cost)
        self.assertGreater(compared, 1500)
        self.assertGreater(unreachable, 200)

    def test_memo_over_changing_targets_roadblocks_and_modes(self) -> None:
        rng = random.Random(GENERATED_SEED + 1)
        for _ in range(40):
            costs, nodes = generated_graph(rng)
            router = BoundedRouter(costs, memo_size=rng.choice([1, 3, 32]))
            for _ in range(12):
                start = rng.choice(nodes[:4])
                mode = rng.choice([MoveMode.VEHICLE, MoveMode.INFANTRY])
                blocked = frozenset(rng.sample(nodes, rng.randint(0, 3)))
                targets = frozenset(rng.sample(nodes, rng.randint(1, 5)))
                router.targets = targets
                shared = router.shortest_paths(start, mode, blocked)
                full = Router(costs)._dijkstra(start, mode, blocked)
                for target in targets:
                    self.assertEqual((shared.cost.get(target), shared.path_to(target)),
                                     (full.cost.get(target), full.path_to(target)))

    def test_a_truncated_result_never_serves_a_larger_target_set(self) -> None:
        router = BoundedRouter(ds.costs())
        router.targets = frozenset({103})
        near = router.shortest_paths(102, MoveMode.VEHICLE, frozenset())
        router.targets = frozenset({103, 909})
        both = router.shortest_paths(102, MoveMode.VEHICLE, frozenset())
        self.assertIsNot(near, both)
        self.assertIsNotNone(both.path_to(909))
        self.assertIsNone(near.path_to(909))
        router.targets = frozenset({909, 103})
        self.assertIs(router.shortest_paths(102, MoveMode.VEHICLE, frozenset()), both)
        blocked = router.shortest_paths(102, MoveMode.VEHICLE, frozenset({103, 202, 203}))
        self.assertIsNot(blocked, both)
        self.assertNotEqual(blocked.path_to(909), both.path_to(909))

    def test_the_memo_distinguishes_movement_modes(self) -> None:
        modes = [DIAMOND, {1: {3: 1.0}, 3: {4: 5.0}, 4: {}}, DIAMOND, {1: {4: 9.0}, 4: {}}]
        costs = graph(DIAMOND, modes=modes)
        router = BoundedRouter(costs)
        router.targets = frozenset({4})
        for mode in (MoveMode.VEHICLE, MoveMode.VEHICLE_MARCH, MoveMode.AIR, MoveMode.VEHICLE):
            shared = router.shortest_paths(1, mode, frozenset())
            full = Router(costs)._dijkstra(1, mode, frozenset())
            self.assertEqual((shared.cost.get(4), shared.path_to(4)), (full.cost.get(4), full.path_to(4)), mode)

    def test_no_targets_means_the_frozen_full_search(self) -> None:
        router = BoundedRouter(ds.costs())
        full = router.shortest_paths(102, MoveMode.VEHICLE, frozenset())
        reference = Router(ds.costs())._dijkstra(102, MoveMode.VEHICLE, frozenset())
        self.assertEqual((dict(full.cost), dict(full.previous)), (dict(reference.cost), dict(reference.previous)))
        router.targets = frozenset()
        self.assertEqual(dict(router.shortest_paths(102, MoveMode.VEHICLE, frozenset()).cost), {102: 0.0})


def decide(policy_class, raw, memory=Memory()):
    return policy_class(ds.costs()).decide(Observation.from_raw(raw, Origin.ENGINE), ds.syn.RED_SEAT, ds.RED, memory)


class PolicyEquivalenceTest(unittest.TestCase):
    def assert_same_decision(self, raw, memory=Memory()) -> None:
        before = copy.deepcopy(raw)
        old, new = decide(OccupyReservationPolicy, raw, memory), decide(BoundedRoutingPolicy, raw, memory)
        self.assertEqual([dict(a) for a in new.actions], [dict(a) for a in old.actions])
        self.assertEqual(rr.semantic_trace(new.trace), rr.semantic_trace(old.trace))
        self.assertEqual((new.memory, new.trace.policy, old.trace.policy),
                         (old.memory, CANDIDATE_ID, "baseline-v1-candidate-occupy-reservation"))
        self.assertEqual(raw, before)

    def test_rich_and_random_situations(self) -> None:
        self.assert_same_decision(ds.rich_observation())
        rng = random.Random(GENERATED_SEED)
        moves = 0
        for index in range(400):
            raw = random_situation(rng)
            with self.subTest(case=index):
                self.assert_same_decision(raw)
            moves += sum(1 for a in decide(BoundedRoutingPolicy, raw).actions if a["type"] == 1)
        self.assertGreater(moves, 100)

    def test_move_candidates_are_identical(self) -> None:
        unit_a = syn.unit(ds.UNIT_A, ds.RED, 102, unit_type=ds.VEHICLE)
        unit_b = syn.unit(ds.UNIT_B, ds.RED, 909, unit_type=ds.INFANTRY)
        raw = ds.play_observation([unit_a, unit_b], {ds.UNIT_A: {1: None}, ds.UNIT_B: {1: None}},
                                  cities=[syn.city(303), syn.city(707), syn.city(505, flag=ds.RED)],
                                  roadblocks=[203, 204])
        context = ds.context_of(raw)
        router = BoundedRouter(ds.costs())
        router.targets = frozenset(c.coord for c in context.objectives)
        for unit in context.units:
            self.assertEqual(move_candidates(unit, context, router), move_candidates(unit, context, Router(ds.costs())))

    def test_semantic_golden_chain_equals_baseline_v1(self) -> None:
        agents = {"v1": ReservationAgent(strict=True), "candidate": BoundedRoutingAgent(strict=True)}
        chains = {name: hashlib.sha256() for name in agents}
        for agent in agents.values():
            agent.setup(setup_info())
        for index, (raw, expected) in enumerate(zip(golden_candidate_observations(), GOLDEN_ACTIONS)):
            for name, agent in agents.items():
                with self.subTest(step=index, agent=name):
                    self.assertEqual([(a["type"], a.get("obj_id")) for a in agent.step(raw)], expected)
                chains[name].update(rr.semantic_digest(agent.last_trace).encode("ascii"))
            self.assertNotEqual(digest(agents["v1"].last_trace), digest(agents["candidate"].last_trace))
        self.assertEqual(chains["candidate"].hexdigest(), chains["v1"].hexdigest())

    def test_agent_lifecycle_replay_and_failure(self) -> None:
        agent = BoundedRoutingAgent(strict=False)
        agent.setup(setup_info())
        raw = golden_candidate_observations()[1]
        memory = agent.memory
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        self.assertIsInstance(agent.policy.router, BoundedRouter)
        self.assertEqual(agent.step({"broken": True}), [])
        self.assertEqual(agent.last_trace.policy, CANDIDATE_ID)
        self.assertIsNotNone(agent.last_trace.error)

    def test_the_bounded_search_is_what_runs(self) -> None:
        policy = BoundedRoutingPolicy(ds.costs())
        unit = syn.unit(ds.UNIT_A, ds.RED, 102, unit_type=ds.VEHICLE)
        raw = ds.play_observation([unit], {ds.UNIT_A: {1: None}}, cities=[syn.city(203)])
        policy.decide(Observation.from_raw(raw, Origin.ENGINE), ds.syn.RED_SEAT, ds.RED, Memory())
        self.assertEqual(policy.router.targets, frozenset({203}))
        (result,) = policy.router._memo.values()
        self.assertLess(len(result.cost), 100)


if __name__ == "__main__":
    unittest.main()
