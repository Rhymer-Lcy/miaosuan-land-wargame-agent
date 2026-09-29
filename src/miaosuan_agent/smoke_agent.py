"""A deliberately inert agent for smoke-testing the engine contract.

It follows the platform's agent interface (``setup``, ``step``, ``reset``) without depending on the
SDK's ``BaseAgent``. It ends the deployment stage once and otherwise issues no actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

#: Action type that ends a player's deployment (结束部署).
END_DEPLOYMENT = 333
#: Value of ``observation["time"]["stage"]`` during deployment.
DEPLOYMENT_STAGE = 1


class SmokeAgent:
    """Ends deployment exactly once; never acts otherwise."""

    def __init__(self) -> None:
        self.seat: Optional[int] = None
        self.deployment_ended = False

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        self.seat = int(setup_info["seat"])
        self.deployment_ended = False

    def step(self, observation: Mapping[str, Any]) -> List[Dict[str, Any]]:
        if self.seat is None:
            raise RuntimeError("SmokeAgent.step() called before setup()")
        time_info = observation.get("time")
        stage = time_info.get("stage") if isinstance(time_info, Mapping) else None
        if stage == DEPLOYMENT_STAGE and not self.deployment_ended:
            self.deployment_ended = True
            return [{"actor": self.seat, "type": END_DEPLOYMENT}]
        return []

    def reset(self) -> None:
        self.seat = None
        self.deployment_ended = False
