"""The action catalog and the deterministic router."""

from __future__ import annotations

import unittest

from miaosuan_agent.boundary import END_DEPLOYMENT, MoveCosts, MoveMode, Stage
from miaosuan_agent.decision import CATALOG, MIN_ATTACK_LEVEL, ActionType, Legality, Parameters
from miaosuan_agent.decision.routing import Router, move_mode

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn


class CatalogTest(unittest.TestCase):
    def test_documented_type_ids(self) -> None:
        self.assertEqual((ActionType.MOVE, ActionType.SHOOT, ActionType.OCCUPY), (1, 2, 5))
        self.assertEqual(ActionType.END_DEPLOYMENT, END_DEPLOYMENT)
        self.assertEqual(ActionType.END_DEPLOYMENT, 333)
        self.assertEqual(MIN_ATTACK_LEVEL, 1)

    def test_every_type_catalogued_consistently(self) -> None:
        self.assertEqual(set(CATALOG), set(ActionType))
        for action_type, entry in CATALOG.items():
            with self.subTest(action_type=action_type):
                self.assertIs(entry.action_type, action_type)
                self.assertTrue(entry.evidence and all(entry.evidence))
                self.assertTrue(entry.meaning and entry.persistence and entry.uncertainty)
                self.assertTrue(entry.stages and entry.stages <= {Stage.DEPLOYMENT, Stage.PLAY})
                self.assertTrue({"actor", "type"} <= entry.keys)
                self.assertEqual("obj_id" in entry.keys, entry.unit_level)
                if entry.parameters is Parameters.OPTION:
                    self.assertTrue(set(entry.fields) <= set(entry.option_fields))
                if entry.parameters is Parameters.CONSTRUCTED_PATH:
                    self.assertEqual(entry.fields, ("move_path",))
                if entry.parameters is Parameters.NONE:
                    self.assertEqual(entry.fields, ())

    def test_only_deployment_completion_is_an_exception(self) -> None:
        exceptions = [t for t, e in CATALOG.items() if e.legality is Legality.DEPLOYMENT_EXCEPTION]
        self.assertEqual(exceptions, [ActionType.END_DEPLOYMENT])
        self.assertEqual(CATALOG[ActionType.END_DEPLOYMENT].stages, {Stage.DEPLOYMENT})
        self.assertFalse(CATALOG[ActionType.END_DEPLOYMENT].unit_level)
        for action_type in (ActionType.MOVE, ActionType.SHOOT, ActionType.OCCUPY):
            self.assertEqual(CATALOG[action_type].stages, {Stage.PLAY})


def formula_costs(rows: int = 8, cols: int = 8) -> MoveCosts:
    """Varied but fixed entry costs (1.0 to 3.0 in steps of 0.5), different for each mode."""
    data = []
    for mode in range(4):
        grid = [[{n: 1 + ((n * 7919 + mode * 31) % 5) * 0.5 for n in syn.grid_neighbours(r * 100 + c, rows, cols)}
                 for c in range(cols)] for r in range(rows)]
        data.append(grid)
    return MoveCosts.from_raw(data)


def bellman_ford(costs: MoveCosts, mode: MoveMode, start: int, blocked=frozenset()) -> dict:
    distance = {start: 0.0}
    hexes = [r * 100 + c for r in range(costs.rows) for c in range(costs.cols)]
    for _ in range(len(hexes)):
        changed = False
        for node in hexes:
            if node not in distance:
                continue
            for neighbour, cost in costs.neighbours(mode, node).items():
                if neighbour in blocked:
                    continue
                if distance[node] + cost < distance.get(neighbour, float("inf")) - 1e-12:
                    distance[neighbour] = distance[node] + cost
                    changed = True
        if not changed:
            break
    return distance


class MoveModeTest(unittest.TestCase):
    def test_documented_mapping(self) -> None:
        self.assertIs(move_mode(ds.VEHICLE, 0), MoveMode.VEHICLE)
        self.assertIs(move_mode(ds.VEHICLE, 1), MoveMode.VEHICLE_MARCH)
        for state in (None, 2, 3, 4, 5):
            self.assertIs(move_mode(ds.VEHICLE, state), MoveMode.VEHICLE)
        self.assertIs(move_mode(ds.INFANTRY, 0), MoveMode.INFANTRY)
        self.assertIs(move_mode(ds.INFANTRY, 1), MoveMode.INFANTRY)
        self.assertIs(move_mode(ds.AIRCRAFT, 0), MoveMode.AIR)
        for unknown in (0, 4, 99, -1):
            self.assertIsNone(move_mode(unknown, 0))


class RouterTest(unittest.TestCase):
    def test_costs_are_optimal(self) -> None:
        costs = formula_costs()
        router = Router(costs)
        for mode in MoveMode:
            for start in (0, 305, 707):
                with self.subTest(mode=mode, start=start):
                    paths = router.shortest_paths(start, mode)
                    expected = bellman_ford(costs, mode, start)
                    self.assertEqual(set(paths.cost), set(expected))
                    for node, value in expected.items():
                        self.assertAlmostEqual(paths.cost[node], value, places=9)

    def test_paths_are_adjacent_and_sum_to_their_cost(self) -> None:
        costs = formula_costs()
        paths = Router(costs).shortest_paths(101, MoveMode.INFANTRY)
        for destination in (101, 102, 407, 706, 0):
            path = paths.path_to(destination)
            if destination == 101:
                self.assertEqual(path, ())
                continue
            self.assertNotIn(101, path)
            self.assertEqual(path[-1], destination)
            total, previous = 0.0, 101
            for hex_ in path:
                self.assertIn(hex_, costs.neighbours(MoveMode.INFANTRY, previous))
                total += costs.neighbours(MoveMode.INFANTRY, previous)[hex_]
                previous = hex_
            self.assertAlmostEqual(total, paths.cost[destination], places=9)

    def test_blocked_hexes_are_avoided_and_unreachable(self) -> None:
        costs = ds.costs()
        paths = Router(costs).shortest_paths(500, MoveMode.VEHICLE, frozenset({501, 502}))
        self.assertIsNone(paths.path_to(501))
        path = paths.path_to(503)
        self.assertFalse({501, 502} & set(path))
        self.assertEqual(paths.cost[503], 4.0)
        self.assertEqual(Router(costs).shortest_paths(500, MoveMode.VEHICLE).path_to(503), (501, 502, 503))

    def test_unreachable_destination(self) -> None:
        costs = ds.costs()
        walls = frozenset({400, 401, 501, 600, 601})
        self.assertIsNone(Router(costs).shortest_paths(500, MoveMode.VEHICLE, walls).path_to(909))

    def test_tie_break_is_pinned(self) -> None:
        # Uniform costs: many shortest paths exist; the frontier order (cost, hex) selects this one.
        paths = Router(ds.costs()).shortest_paths(102, MoveMode.VEHICLE)
        self.assertEqual(paths.path_to(505), (103, 204, 304, 405, 505))
        self.assertEqual(paths.cost[505], 5.0)

    def test_independent_of_neighbour_order(self) -> None:
        forward = syn.cost_data(entry_costs={304: 2.5, 204: 1.5})
        backward = [[[dict(reversed(list(cell.items()))) for cell in row] for row in mode] for mode in forward]
        a = Router(MoveCosts.from_raw(forward)).shortest_paths(102, MoveMode.VEHICLE)
        b = Router(MoveCosts.from_raw(backward)).shortest_paths(102, MoveMode.VEHICLE)
        self.assertEqual((a.cost, a.previous), (b.cost, b.previous))

    def test_memo_never_changes_results(self) -> None:
        costs = formula_costs()
        tiny = Router(costs, memo_size=1)
        queries = [(0, MoveMode.VEHICLE, frozenset()), (305, MoveMode.AIR, frozenset({306})),
                   (0, MoveMode.VEHICLE, frozenset()), (707, MoveMode.INFANTRY, frozenset())]
        for start, mode, blocked in queries:
            fresh = Router(costs).shortest_paths(start, mode, blocked)
            cached = tiny.shortest_paths(start, mode, blocked)
            self.assertEqual((fresh.cost, fresh.previous), (cached.cost, cached.previous))
        self.assertEqual(len(tiny._memo), 1)


if __name__ == "__main__":
    unittest.main()
