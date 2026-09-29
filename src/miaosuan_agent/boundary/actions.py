"""Protocol actions the project itself issues. Only deployment completion exists so far."""

from __future__ import annotations

from typing import Any, Dict

from .checks import require_int, require_mapping
from .errors import ContractError
from .observation import Observation

#: Action type that ends a player's deployment (结束部署). It is a player-level action: it does
#: not appear under any operator in ``valid_actions``.
END_DEPLOYMENT = 333


def end_deployment_action(seat: int) -> Dict[str, int]:
    return {"actor": require_int(seat, "seat"), "type": END_DEPLOYMENT}


def validate_end_deployment_action(action: Any) -> None:
    """Check the documented shape ``{"actor": <seat>, "type": 333}`` and nothing else."""
    mapping = require_mapping(action, "action")
    if set(mapping) != {"actor", "type"}:
        raise ContractError("action", "exactly the keys 'actor' and 'type'", action,
                            detail=f"keys present: {sorted(map(str, mapping))}")
    require_int(mapping["actor"], "action.actor")
    if require_int(mapping["type"], "action.type") != END_DEPLOYMENT:
        raise ContractError("action.type", f"{END_DEPLOYMENT}", mapping["type"])


def deployment_completion_available(observation: Observation, seat: int) -> bool:
    """True while the stage is deployment and the seat has not already ended its deployment.

    The seat must be listed in ``role_and_grouping_info``. When ``end_deployment`` is absent
    (a form some documentation shows), availability follows the stage alone.
    """
    if not observation.time().is_deployment:
        return False
    return observation.seat(seat).end_deployment is not True
