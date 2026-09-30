"""Characterization of the frozen baseline routing (decision/routing.py and move_candidates).

These tests pin behaviour the router has today, including behaviour that is only implicit in its
code, so that any replacement can be checked against it: equal-cost tie-breaking, predecessor
updates on strictly lower cost only, independence from neighbour order, unreachable and trivial
targets, roadblocks, movement modes, the memo, and the objective choice built on top of it.
SYNTHETIC data only.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from miaosuan_agent.boundary import ContractError, MoveCosts, MoveMode
from miaosuan_agent.decision.candidates import move_candidates
from miaosuan_agent.decision.routing import Router

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn


def graph(edges, rows=10, cols=10, modes=None):
    """MoveCosts from ``{hex: {neighbour: cost}}`` (the same adjacency in every mode unless ``modes`` given)."""
    per_mode = modes or [edges] * len(MoveMode)
    return MoveCosts(rows=rows, cols=cols, edges=tuple(
        MappingProxyType({h: MappingProxyType(dict(n)) for h, n in mode.items()}) for mode in per_mode))


DIAMOND = {1: {2: 1.0, 3: 1.0}, 2: {4: 1.0}, 3: {4: 1.0}, 4: {}}


class TieBreakingTest(unittest.TestCase):
    def test_equal_cost_paths_keep_the_earliest_popped_predecessor(self) -> None:
        paths = Router(graph(DIAMOND))._dijkstra(1, MoveMode.VEHICLE, frozenset())
        self.assertEqual(paths.cost[4], 2.0)
        self.assertEqual(paths.path_to(4), (2, 4))  # (1, 2) pops before (1, 3): hex order breaks the cost tie

    def test_neighbour_order_does_not_matter(self) -> None:
        reversed_edges = {h: dict(reversed(list(n.items()))) for h, n in DIAMOND.items()}
        a = Router(graph(DIAMOND))._dijkstra(1, MoveMode.VEHICLE, frozenset())
        b = Router(graph(reversed_edges))._dijkstra(1, MoveMode.VEHICLE, frozenset())
        self.assertEqual((dict(a.cost), dict(a.previous)), (dict(b.cost), dict(b.previous)))

    def test_predecessor_changes_only_on_a_strictly_lower_cost(self) -> None:
        edges = {1: {2: 1.0, 5: 3.0}, 2: {3: 1.0}, 3: {5: 1.0}, 5: {}}
        paths = Router(graph(edges))._dijkstra(1, MoveMode.VEHICLE, frozenset())
        self.assertEqual((paths.cost[5], paths.previous[5]), (3.0, 1))  # the cost-3 path via 3 ties and loses

    def test_uniform_grid_route_of_the_golden_decision(self) -> None:
        paths = Router(ds.costs())._dijkstra(102, MoveMode.VEHICLE, frozenset())
        self.assertEqual(paths.path_to(505), (103, 204, 304, 405, 505))


class ReachabilityTest(unittest.TestCase):
    def test_unreachable_trivial_and_blocked(self) -> None:
        edges = {1: {2: 1.0}, 2: {1: 1.0}, 7: {8: 1.0}, 8: {}}
        paths = Router(graph(edges))._dijkstra(1, MoveMode.VEHICLE, frozenset())
        self.assertIsNone(paths.path_to(8))
        self.assertNotIn(8, paths.cost)
        self.assertEqual(paths.path_to(1), ())
        blocked = Router(graph(DIAMOND))._dijkstra(1, MoveMode.VEHICLE, frozenset({2}))
        self.assertEqual(blocked.path_to(4), (3, 4))
        self.assertNotIn(2, blocked.cost)
        start_blocked = Router(graph(DIAMOND))._dijkstra(1, MoveMode.VEHICLE, frozenset({1}))
        self.assertEqual(start_blocked.path_to(4), (2, 4))  # the start hex itself is never checked

    def test_modes_use_their_own_adjacency(self) -> None:
        modes = [DIAMOND, {1: {3: 1.0}, 3: {4: 5.0}, 4: {}}, DIAMOND, DIAMOND]
        router = Router(graph(DIAMOND, modes=modes))
        self.assertEqual(router._dijkstra(1, MoveMode.VEHICLE_MARCH, frozenset()).path_to(4), (3, 4))
        self.assertEqual(router._dijkstra(1, MoveMode.VEHICLE_MARCH, frozenset()).cost[4], 6.0)
        self.assertEqual(router._dijkstra(1, MoveMode.VEHICLE, frozenset()).cost[4], 2.0)

    def test_zero_and_negative_costs_are_illegal_inputs(self) -> None:
        raw = syn.cost_data()
        raw[0][0][0][1] = 0
        with self.assertRaises(ContractError):
            MoveCosts.from_raw(raw)


class MemoTest(unittest.TestCase):
    def test_results_do_not_depend_on_the_memo(self) -> None:
        costs = ds.costs(entry_costs={304: 3, 405: 2})
        warm = Router(costs, memo_size=2)
        for start in (102, 207, 909, 102, 505, 102):
            fresh = Router(costs)._dijkstra(start, MoveMode.INFANTRY, frozenset({303}))
            shared = warm.shortest_paths(start, MoveMode.INFANTRY, frozenset({303}))
            self.assertEqual((dict(shared.cost), dict(shared.previous)), (dict(fresh.cost), dict(fresh.previous)))
        self.assertLessEqual(len(warm._memo), 2)

    def test_memo_key_is_start_mode_and_blocked(self) -> None:
        router = Router(ds.costs())
        a = router.shortest_paths(102, MoveMode.VEHICLE, frozenset())
        self.assertIs(router.shortest_paths(102, MoveMode.VEHICLE, frozenset()), a)
        self.assertIsNot(router.shortest_paths(102, MoveMode.INFANTRY, frozenset()), a)
        self.assertIsNot(router.shortest_paths(102, MoveMode.VEHICLE, frozenset({304})), a)


class ObjectiveChoiceTest(unittest.TestCase):
    def test_lowest_cost_objective_then_lowest_coord(self) -> None:
        unit = syn.unit(ds.UNIT_A, ds.RED, 505, unit_type=ds.INFANTRY)
        raw = ds.play_observation([unit], {ds.UNIT_A: {1: None}}, cities=[syn.city(303), syn.city(707)])
        context = ds.context_of(raw)
        candidates, reason = move_candidates(context.units[0], context, Router(ds.costs()))
        self.assertIsNone(reason)
        best = min(candidates, key=lambda c: c.rank)
        self.assertEqual([c.rank for c in candidates], sorted(c.rank for c in candidates))
        self.assertEqual(candidates[0].rank[0], candidates[1].rank[0])  # equal cost: the lower coord wins
        self.assertEqual(dict(best.detail)["destination"], 303)

    def test_roadblocks_bind_vehicles_only_and_unreachable_objectives_are_skipped(self) -> None:
        wall = [h for h in range(0, 1000) if h % 100 < 10 and h // 100 == 3]
        vehicle = syn.unit(ds.UNIT_A, ds.RED, 102, unit_type=ds.VEHICLE)
        infantry = syn.unit(ds.UNIT_B, ds.RED, 102, unit_type=ds.INFANTRY)
        raw = ds.play_observation([vehicle, infantry], {ds.UNIT_A: {1: None}, ds.UNIT_B: {1: None}},
                                  cities=[syn.city(505)], roadblocks=wall)
        context = ds.context_of(raw)
        router = Router(ds.costs())
        self.assertEqual(move_candidates(context.units[0], context, router), ([], "no objective reachable"))
        infantry_moves, _ = move_candidates(context.units[1], context, router)
        self.assertEqual(len(infantry_moves), 1)


if __name__ == "__main__":
    unittest.main()
