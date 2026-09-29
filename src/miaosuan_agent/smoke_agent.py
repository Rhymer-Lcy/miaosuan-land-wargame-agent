"""A deliberately inert agent for smoke-testing the engine contract.

It follows the platform's agent interface (``setup``, ``step``, ``reset``) without depending on the
SDK's ``BaseAgent`` and reads observations only through :mod:`miaosuan_agent.boundary`. It ends
the deployment stage once, when that is available to its seat, and otherwise issues no actions.
Malformed observations raise :class:`~miaosuan_agent.boundary.ContractError` instead of being
treated as "nothing to do".
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .boundary import Observation, Origin, deployment_completion_available, end_deployment_action
from .boundary.checks import require_int


class SmokeAgent:
    """Ends deployment exactly once; never acts otherwise."""

    def __init__(self, origin: Origin = Origin.ENGINE) -> None:
        self.origin = origin
        self.seat: Optional[int] = None
        self.deployment_ended = False

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        self.seat = require_int(setup_info["seat"], "setup_info.seat")
        self.deployment_ended = False

    def step(self, observation: Any) -> List[Dict[str, int]]:
        if self.seat is None:
            raise RuntimeError("SmokeAgent.step() called before setup()")
        view = Observation.from_raw(observation, self.origin)
        if not self.deployment_ended and deployment_completion_available(view, self.seat):
            self.deployment_ended = True
            return [end_deployment_action(self.seat)]
        return []

    def reset(self) -> None:
        self.seat = None
        self.deployment_ended = False
