"""The single boundary between raw SDK data and project code.

Three notions are kept apart (see ``docs/CONTRACT.md``):

* the *observed contract* of one engine build, recorded in :mod:`.profile`;
* the *accepted boundary*: the input forms :func:`normalize_state` and
  :meth:`Observation.from_raw` deliberately accept, each validated explicitly;
* the *canonical representation*: :class:`StateView`, :class:`Observation` and the value objects
  they return. Code above this package consumes only these, never raw SDK containers.
"""

from .actions import (END_DEPLOYMENT, deployment_completion_available, end_deployment_action,
                      validate_end_deployment_action)
from .errors import ContractError
from .keys import Origin, normalize_int_key, normalize_int_keyed
from .observation import KNOWN_FIELDS, REQUIRED_FIELDS, Observation, Operator, SeatInfo, Stage, TimeInfo
from .state import Slot, StateForm, StateView, normalize_state

__all__ = [
    "END_DEPLOYMENT", "KNOWN_FIELDS", "REQUIRED_FIELDS", "ContractError", "Observation", "Operator",
    "Origin", "SeatInfo", "Slot", "Stage", "StateForm", "StateView", "TimeInfo",
    "deployment_completion_available", "end_deployment_action", "normalize_int_key", "normalize_int_keyed",
    "normalize_state", "validate_end_deployment_action",
]
