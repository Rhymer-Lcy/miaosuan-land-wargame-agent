"""Deterministic shortest paths on the setup-supplied movement-cost graph.

This is the minimum needed to fill the ``move_path`` parameter, which ``valid_actions`` does not
enumerate: Dijkstra's algorithm over :class:`~miaosuan_agent.boundary.MoveCosts`. Results depend
only on the graph and the inputs. The frontier is a heap of ``(cost, hex)`` pairs, which are totally
ordered, so the pop sequence does not depend on the order in which neighbours are stored or
relaxed; and a node's predecessor changes only on a strictly lower cost, so among equal-cost paths
the one through the earliest-popped node wins.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from ..boundary import MoveCosts, MoveMode

#: Documented ``type`` values of units.
INFANTRY, VEHICLE, AIRCRAFT = 1, 2, 3
#: Documented ``move_state`` value of a vehicle in march state.
MARCH = 1
#: Modes whose units cannot enter roadblock hexes (rules: roadblocks stop vehicles, not infantry).
ROADBLOCKED_MODES = frozenset({MoveMode.VEHICLE, MoveMode.VEHICLE_MARCH})


def move_mode(unit_type: int, move_state: Optional[int]) -> Optional[MoveMode]:
    """The cost mode for a unit, or ``None`` for a type without documented movement."""
    if unit_type == VEHICLE:
        return MoveMode.VEHICLE_MARCH if move_state == MARCH else MoveMode.VEHICLE
    if unit_type == INFANTRY:
        return MoveMode.INFANTRY
    if unit_type == AIRCRAFT:
        return MoveMode.AIR
    return None


@dataclass(frozen=True)
class ShortestPaths:
    """Costs and predecessors from one start hex (read-only: results are shared through the memo)."""

    start: int
    cost: Mapping[int, float]
    previous: Mapping[int, int]

    def path_to(self, destination: int) -> Optional[Tuple[int, ...]]:
        """Hexes after ``start`` up to ``destination``; ``None`` if unreachable, ``()`` if already there."""
        if destination not in self.cost:
            return None
        hexes = []
        node = destination
        while node != self.start:
            hexes.append(node)
            node = self.previous[node]
        return tuple(reversed(hexes))


class Router:
    """Shortest paths with a small first-in-first-out memo (results never depend on the memo).

    Each entry holds costs and predecessors for the whole map, so the memo stays small.
    """

    def __init__(self, costs: MoveCosts, memo_size: int = 32) -> None:
        self.costs = costs
        self._memo: Dict[Tuple[int, int, FrozenSet[int]], ShortestPaths] = {}
        self._memo_size = memo_size

    def shortest_paths(self, start: int, mode: MoveMode, blocked: FrozenSet[int] = frozenset()) -> ShortestPaths:
        key = (start, int(mode), blocked)
        if key not in self._memo:
            if len(self._memo) >= self._memo_size:
                self._memo.pop(next(iter(self._memo)))
            self._memo[key] = self._dijkstra(start, mode, blocked)
        return self._memo[key]

    def _dijkstra(self, start: int, mode: MoveMode, blocked: FrozenSet[int]) -> ShortestPaths:
        cost: Dict[int, float] = {start: 0.0}
        previous: Dict[int, int] = {}
        done = set()
        frontier = [(0.0, start)]
        while frontier:
            distance, node = heapq.heappop(frontier)
            if node in done:
                continue
            done.add(node)
            edges = self.costs.neighbours(mode, node)
            for neighbour in edges:
                if neighbour in blocked or neighbour in done:
                    continue
                candidate = distance + edges[neighbour]
                if neighbour not in cost or candidate < cost[neighbour]:
                    cost[neighbour] = candidate
                    previous[neighbour] = node
                    heapq.heappush(frontier, (candidate, neighbour))
        return ShortestPaths(start=start, cost=MappingProxyType(cost), previous=MappingProxyType(previous))
