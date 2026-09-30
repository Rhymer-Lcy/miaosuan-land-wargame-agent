"""Diagnostic estimate of how much of a shortest-path search the policy actually needs.

The policy's router (:mod:`..decision.routing`) runs Dijkstra from a unit's hex over the whole map,
but a move candidate only reads the costs and paths of objective hexes. This module re-runs the
same search loop on the same inputs and counts the nodes settled until every target hex is settled,
which bounds the work a target-aware search would do. It is a measurement for remediation design
only: nothing here is imported by a policy, and no result feeds a decision.
"""

from __future__ import annotations

import heapq
from typing import Any, Dict, FrozenSet, Iterable

from ..boundary import MoveCosts, MoveMode


def settled_until_targets(costs: MoveCosts, start: int, mode: MoveMode, blocked: FrozenSet[int],
                          targets: Iterable[int]) -> Dict[str, Any]:
    """Nodes settled in total and until the last reachable target was settled (the router's own loop)."""
    remaining = set(targets)
    cost: Dict[int, float] = {start: 0.0}
    done = set()
    frontier = [(0.0, start)]
    settled, needed = 0, None
    while frontier:
        distance, node = heapq.heappop(frontier)
        if node in done:
            continue
        done.add(node)
        settled += 1
        if node in remaining:
            remaining.discard(node)
            if not remaining:
                needed = settled
        edges = costs.neighbours(mode, node)
        for neighbour in edges:
            if neighbour in blocked or neighbour in done:
                continue
            candidate = distance + edges[neighbour]
            if neighbour not in cost or candidate < cost[neighbour]:
                cost[neighbour] = candidate
                heapq.heappush(frontier, (candidate, neighbour))
    return {"settled": settled, "settled_until_targets": settled if needed is None else needed,
            "unreachable_targets": len(remaining)}
