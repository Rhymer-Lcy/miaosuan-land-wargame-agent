"""A runtime candidate derived from baseline-v1: target-bounded shortest paths, identical decisions.

Registered as ``routing-remediation-1`` (docs/ROUTING_REMEDIATION.md). The frozen router
(``decision.routing.Router``) runs Dijkstra over the whole map, although a move candidate reads only
the objectives not held by the side. :class:`BoundedRouter` runs the same search, pop for pop and
relaxation for relaxation, and stops as soon as every target hex is settled, or when the reachable
frontier is exhausted. The bounded run is therefore a prefix of the full run: every settled hex has
the full run's cost and predecessor, and an unreachable target keeps the search going to the end,
exactly as before. The result exposes settled hexes only, so no tentative value can be read. The memo
key is the frozen key (start, mode, roadblocks) plus the target set.

The policy is baseline-v1's (:class:`OccupyReservationPolicy`) with this router; before each
play-stage decision it hands the router the hexes of the objectives that the unchanged tactical
context lists. Nothing else differs; the decision trace differs only in its ``policy`` field.
"""

from __future__ import annotations

import heapq
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, Mapping, Optional

from ..boundary import ContractError, MoveCosts, MoveMode, Observation, Origin
from ..decision import Memory, StepTrace
from ..decision.context import TacticalContext
from ..decision.policy import Decision
from ..decision.routing import Router, ShortestPaths
from ..decision.trace import failed
from .occupy_reservation import OccupyReservationPolicy, ReservationAgent

CANDIDATE_ID = "baseline-v1-routing-bounded-candidate"


class BoundedRouter(Router):
    """The frozen router's search, stopped once every target hex is settled."""

    def __init__(self, costs: MoveCosts, memo_size: int = 32) -> None:
        super().__init__(costs, memo_size)
        #: Hexes the current decision reads; ``None`` means the frozen full search.
        self.targets: Optional[FrozenSet[int]] = None

    def shortest_paths(self, start: int, mode: MoveMode, blocked: FrozenSet[int] = frozenset()) -> ShortestPaths:
        targets = self.targets
        key = (start, int(mode), blocked, targets)
        if key not in self._memo:
            if len(self._memo) >= self._memo_size:
                self._memo.pop(next(iter(self._memo)))
            self._memo[key] = (self._dijkstra(start, mode, blocked) if targets is None
                               else self._bounded(start, mode, blocked, targets))
        return self._memo[key]

    def _bounded(self, start: int, mode: MoveMode, blocked: FrozenSet[int], targets: FrozenSet[int]) -> ShortestPaths:
        remaining = set(targets)
        cost: Dict[int, float] = {start: 0.0}
        previous: Dict[int, int] = {}
        done = set()
        frontier = [(0.0, start)]
        while frontier:
            distance, node = heapq.heappop(frontier)
            if node in done:
                continue
            done.add(node)
            remaining.discard(node)
            if not remaining:
                break
            edges = self.costs.neighbours(mode, node)
            for neighbour in edges:
                if neighbour in blocked or neighbour in done:
                    continue
                candidate = distance + edges[neighbour]
                if neighbour not in cost or candidate < cost[neighbour]:
                    cost[neighbour] = candidate
                    previous[neighbour] = node
                    heapq.heappush(frontier, (candidate, neighbour))
        return ShortestPaths(start=start, cost=MappingProxyType({node: cost[node] for node in done}),
                             previous=MappingProxyType({node: previous[node] for node in done if node in previous}))


class BoundedRoutingPolicy(OccupyReservationPolicy):
    """baseline-v1 with the bounded router."""

    identity = CANDIDATE_ID

    def __init__(self, costs: Optional[MoveCosts]) -> None:
        super().__init__(costs)
        self.router = BoundedRouter(costs) if costs is not None else None

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        if self.router is not None:
            self.router.targets = frozenset(city.coord for city in context.objectives)
        return super()._play(context, memory)


class BoundedRoutingAgent(ReservationAgent):
    """The platform agent interface around the candidate (same contract as baseline-v1's agent)."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = CANDIDATE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = BoundedRoutingPolicy(self.costs)

    def replay(self, observation: Any, memory: Memory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = BoundedRoutingPolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)
