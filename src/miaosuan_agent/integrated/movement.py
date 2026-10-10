"""Terrain-aware travel times and constrained path planning on the setup cost graph.

``Terrain`` holds, per movement mode, the reverse adjacency of the cost graph and a cache of reverse distance fields:
for a target hex, the cheapest entry-cost sum from every hex to it (Dijkstra on the reversed graph, roadblocks
removed for vehicle modes). Fields depend only on static setup data and the observed roadblocks, so they are computed
once per (mode, target, roadblocks) and reused all game; travel time is ``720 / basic_speed`` times the cost (each
hex rounded, as the engine does, when an exact path is timed).

Paths are planned with A* from the unit to its target. The heuristic is the target's exact distance field, which is
admissible because the planner only removes edges (blocked hexes) and adds non-negative penalties. Results depend
only on the inputs: the frontier holds (estimate, cost, hex) triples, which are totally ordered, and a predecessor
changes only on a strictly lower cost.
"""

from __future__ import annotations

import heapq
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

from ..boundary import MoveCosts, MoveMode
from ..decision.routing import ROADBLOCKED_MODES, move_mode
from . import facts as F

INF = float("inf")
#: Expansion bound of one A* search (a full map has fewer than 10,000 hexes).
MAX_EXPANSIONS = 40_000


def unit_mode(unit_type: int, move_state: int) -> Optional[MoveMode]:
    return move_mode(unit_type, move_state)


class Terrain:
    def __init__(self, costs: MoveCosts) -> None:
        self.costs = costs
        self.rows, self.cols = costs.rows, costs.cols
        self._reverse: Dict[int, Dict[int, Dict[int, float]]] = {}
        self._fields: Dict[Tuple[int, int, FrozenSet[int]], Mapping[int, float]] = {}

    # -- reverse distance fields ------------------------------------------------------------------
    def _reverse_graph(self, mode: MoveMode) -> Dict[int, Dict[int, float]]:
        key = int(mode)
        if key not in self._reverse:
            reverse: Dict[int, Dict[int, float]] = {}
            for hex_, edges in self.costs.edges[key].items():
                for neighbour, cost in edges.items():
                    reverse.setdefault(neighbour, {})[hex_] = cost
            self._reverse[key] = reverse
        return self._reverse[key]

    def field(self, mode: MoveMode, target: int, roadblocks: FrozenSet[int] = frozenset()) -> Mapping[int, float]:
        """Cheapest entry-cost sum from every hex to ``target`` (absent: unreachable)."""
        blocked = roadblocks if mode in ROADBLOCKED_MODES else frozenset()
        key = (int(mode), target, blocked)
        if key not in self._fields:
            reverse = self._reverse_graph(mode)
            dist: Dict[int, float] = {target: 0.0}
            done = set()
            frontier = [(0.0, target)]
            while frontier:
                d, node = heapq.heappop(frontier)
                if node in done:
                    continue
                done.add(node)
                # Entering ``node`` from ``prev`` costs reverse[node][prev]; a blocked hex can be neither entered
                # nor left on the way (the target itself is never in ``blocked`` for a valid order).
                for prev, cost in reverse.get(node, {}).items():
                    if prev in done or prev in blocked:
                        continue
                    candidate = d + cost
                    if prev not in dist or candidate < dist[prev]:
                        dist[prev] = candidate
                        heapq.heappush(frontier, (candidate, prev))
            self._fields[key] = dist
        return self._fields[key]

    def cost_to(self, mode: Optional[MoveMode], start: int, target: int, roadblocks: FrozenSet[int]) -> Optional[float]:
        if mode is None:
            return None
        if start == target:
            return 0.0
        value = self.field(mode, target, roadblocks).get(start)
        return value

    @staticmethod
    def seconds(basic_speed: float, cost: Optional[float]) -> Optional[float]:
        if cost is None or basic_speed <= 0:
            return None
        return F.SECONDS_PER_HEX_AT_1KMH / basic_speed * cost

    def path_seconds(self, mode: MoveMode, basic_speed: float, start: int, path: Tuple[int, ...]) -> Optional[int]:
        """Exact free-flow time of a path, each hex rounded as the engine's hex time."""
        total, here = 0, start
        for hex_ in path:
            cost = self.costs.neighbours(mode, here).get(hex_)
            step = F.hex_time(basic_speed, cost)
            if step is None:
                return None
            total += step
            here = hex_
        return total

    # -- constrained planning ---------------------------------------------------------------------
    def plan(self, mode: MoveMode, start: int, target: int, roadblocks: FrozenSet[int],
             blocked: FrozenSet[int] = frozenset(), penalty: Optional[Mapping[int, float]] = None
             ) -> Optional[Tuple[int, ...]]:
        """The cheapest path (hexes after ``start``, ending on ``target``) avoiding ``blocked`` hexes and paying
        ``penalty`` (extra cost units) on entry; ``None`` when none exists within the expansion bound."""
        if start == target:
            return ()
        road = roadblocks if mode in ROADBLOCKED_MODES else frozenset()
        heuristic = self.field(mode, target, roadblocks)
        if start not in heuristic or target in road or target in blocked:
            return None
        penalty = penalty or {}
        cost: Dict[int, float] = {start: 0.0}
        previous: Dict[int, int] = {}
        done = set()
        frontier = [(heuristic[start], 0.0, start)]
        expansions = 0
        while frontier:
            _, g, node = heapq.heappop(frontier)
            if node in done:
                continue
            if node == target:
                break
            done.add(node)
            expansions += 1
            if expansions > MAX_EXPANSIONS:
                return None
            for neighbour, step_cost in self.costs.neighbours(mode, node).items():
                if neighbour in done or neighbour in road or (neighbour in blocked and neighbour != target):
                    continue
                h = heuristic.get(neighbour)
                if h is None:
                    continue
                candidate = g + step_cost + penalty.get(neighbour, 0.0)
                if neighbour not in cost or candidate < cost[neighbour]:
                    cost[neighbour] = candidate
                    previous[neighbour] = node
                    heapq.heappush(frontier, (candidate + h, candidate, neighbour))
        if target not in previous:
            return None
        hexes: List[int] = []
        node = target
        while node != start:
            hexes.append(node)
            node = previous[node]
        return tuple(reversed(hexes))

    def path_is_valid(self, mode: MoveMode, start: int, path: Tuple[int, ...], roadblocks: FrozenSet[int]) -> bool:
        road = roadblocks if mode in ROADBLOCKED_MODES else frozenset()
        if not path or len(set(path)) != len(path) or start in path:
            return False
        here = start
        for hex_ in path:
            if hex_ not in self.costs.neighbours(mode, here) or hex_ in road:
                return False
            here = hex_
        return True
