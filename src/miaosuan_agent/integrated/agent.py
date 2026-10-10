"""The platform-facing agent around :class:`~.policy.CommanderPolicy` (same contract as ``PolicyAgent``).

``setup`` / ``step`` / ``replay`` / ``reset``; observations enter only through the canonical boundary; a contract
violation yields no actions and a failed trace (or raises with ``strict``); setup data that violates the contract
raises. ``memory`` is the explicit :class:`~.memory.CommanderMemory` before the next decision, and ``replay``
re-decides an observation with a fresh policy instance and a given memory without touching the agent's state.

Seat identity is the internal int seat; mapping an external platform seat is the platform adapter's job, not this
module's.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from ..boundary import ContractError, MoveCosts, Observation, Origin
from ..boundary.checks import require_int
from ..decision import StepTrace
from ..decision.trace import failed
from .config import Config
from .memory import CommanderMemory
from .policy import CommanderPolicy, candidate_id


class CommanderAgent:
    def __init__(self, config: Config, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        self.config = config
        self.policy_id = candidate_id(config)
        self.origin = origin
        self.strict = strict
        self.seat: Optional[int] = None
        self.faction: Optional[int] = None
        self.costs: Optional[MoveCosts] = None
        self.policy: Optional[CommanderPolicy] = None
        self.memory = CommanderMemory()
        self.last_trace: Optional[StepTrace] = None

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        self.seat = require_int(setup_info["seat"], "setup_info.seat")
        self.faction = require_int(setup_info["faction"], "setup_info.faction")
        raw_costs = setup_info.get("cost_data")
        self.costs = None if raw_costs is None else MoveCosts.from_raw(raw_costs, self.origin, "setup_info.cost_data")
        self.policy = CommanderPolicy(self.costs, self.config)
        self.memory = CommanderMemory()
        self.last_trace = None

    def step(self, observation: Any) -> List[Dict[str, Any]]:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("step() called before setup()")
        try:
            view = Observation.from_raw(observation, self.origin)
            actions, trace, memory = self.policy.decide(view, self.seat, self.faction, self.memory)
        except ContractError as exc:
            if self.strict:
                raise
            self.last_trace = failed(self.policy.identity, self.seat, self.faction, exc)
            return []
        self.memory = memory
        self.last_trace = trace
        return [dict(action) for action in actions]

    def replay(self, observation: Any, memory: CommanderMemory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = CommanderPolicy(self.costs, self.config)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory)[1]
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)

    def reset(self) -> None:
        self.seat = self.faction = self.policy = self.last_trace = self.costs = None
        self.memory = CommanderMemory()
