"""The platform-facing coalition agent: Sprint 34's ``CommanderAgent`` contract around ``CoalitionPolicy``.

``setup`` / ``step`` / ``replay`` / ``reset`` behave as in ``integrated.agent``; the memory is a ``CoalitionMemory``.
Seat identity is the internal int seat; mapping an external platform seat is the platform adapter's job.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..boundary import ContractError, MoveCosts, Observation, Origin
from ..boundary.checks import require_int
from ..decision import StepTrace
from ..decision.trace import failed
from ..integrated.agent import CommanderAgent
from .config import CoalitionConfig
from .memory import CoalitionMemory
from .policy import CoalitionPolicy, candidate_id


class CoalitionAgent(CommanderAgent):
    def __init__(self, config: CoalitionConfig, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(config.base, origin, strict)
        self.coalition = config
        self.policy_id = candidate_id(config)
        self.memory = CoalitionMemory()

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        self.seat = require_int(setup_info["seat"], "setup_info.seat")
        self.faction = require_int(setup_info["faction"], "setup_info.faction")
        raw_costs = setup_info.get("cost_data")
        self.costs = None if raw_costs is None else MoveCosts.from_raw(raw_costs, self.origin, "setup_info.cost_data")
        self.policy = CoalitionPolicy(self.costs, self.coalition)
        self.memory = CoalitionMemory()
        self.last_trace = None

    def replay(self, observation: Any, memory: CoalitionMemory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = CoalitionPolicy(self.costs, self.coalition)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory)[1]
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)

    def reset(self) -> None:
        super().reset()
        self.memory = CoalitionMemory()
