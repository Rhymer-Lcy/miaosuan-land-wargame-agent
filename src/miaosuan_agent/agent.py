"""The platform-facing agent: ``setup`` / ``step`` / ``reset`` around one deterministic policy.

Like :class:`~miaosuan_agent.smoke_agent.SmokeAgent` it follows the platform's agent interface
without importing the SDK. Observations enter only through
:meth:`~miaosuan_agent.boundary.Observation.from_raw`; the policy sees canonical objects only.

Failure handling is fail-closed: an observation that violates the contract yields no actions and a
trace carrying the error (or raises, with ``strict=True``). Setup data that violates the contract
always raises, because every later decision would depend on it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .boundary import ContractError, MoveCosts, Observation, Origin
from .boundary.checks import require_int
from .decision import BASELINE_ID, INERT_ID, POLICIES, Memory, StepTrace
from .decision.policy import BaselinePolicy
from .decision.trace import failed


class PolicyAgent:
    """Runs the policy named ``policy`` for one seat."""

    def __init__(self, policy: str = BASELINE_ID, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}; known: {sorted(POLICIES)}")
        self.policy_id = policy
        self.origin = origin
        self.strict = strict
        self.seat: Optional[int] = None
        self.faction: Optional[int] = None
        self.policy: Optional[BaselinePolicy] = None
        self.memory = Memory()
        self.last_trace: Optional[StepTrace] = None

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        self.seat = require_int(setup_info["seat"], "setup_info.seat")
        self.faction = require_int(setup_info["faction"], "setup_info.faction")
        raw_costs = setup_info.get("cost_data")
        costs = None if raw_costs is None else MoveCosts.from_raw(raw_costs, self.origin, "setup_info.cost_data")
        self.policy = POLICIES[self.policy_id](costs)
        self.memory = Memory()
        self.last_trace = None

    def step(self, observation: Any) -> List[Dict[str, Any]]:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("step() called before setup()")
        try:
            view = Observation.from_raw(observation, self.origin)
            decision = self.policy.decide(view, self.seat, self.faction, self.memory)
        except ContractError as exc:
            if self.strict:
                raise
            self.last_trace = failed(self.policy.identity, self.seat, self.faction, exc)
            return []
        self.memory = decision.memory
        self.last_trace = decision.trace
        return [dict(action) for action in decision.actions]

    def reset(self) -> None:
        self.seat = self.faction = self.policy = self.last_trace = None
        self.memory = Memory()


class BaselineAgent(PolicyAgent):
    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(BASELINE_ID, origin, strict)


class InertAgent(PolicyAgent):
    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(INERT_ID, origin, strict)
