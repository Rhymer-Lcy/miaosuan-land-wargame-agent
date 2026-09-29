"""Normalization of the engine state container into one canonical view.

``TrainEnv.setup`` and ``TrainEnv.step`` return the state for all players at once. Engine 4.1.0
returns a mapping keyed ``0`` (red), ``1`` (blue) and ``-1`` (the all-seeing view). The platform
documentation describes a list in which ``state[0]`` is red, ``state[1]`` blue and ``state[-1]``
the all-seeing view. Both forms are accepted when they are unambiguous:

* a mapping must contain the three slot keys; further integer keys are preserved in
  ``extra_slots``; key form follows the declared origin (see :mod:`.keys`);
* a list or tuple must have exactly three items, read as ``[red, blue, all-seeing]``; with any
  other length ``state[-1]`` would not identify a distinct slot, so it is rejected.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .errors import ContractError
from .keys import Origin, normalize_int_keyed
from .observation import Observation


class Slot(enum.IntEnum):
    """State slots, valued as the engine keys them. The SDK calls the all-seeing view GREEN."""

    RED = 0
    BLUE = 1
    GLOBAL = -1


class StateForm(enum.Enum):
    MAPPING = "mapping"
    SEQUENCE = "sequence"


#: Order of the documented list form.
SEQUENCE_ORDER = (Slot.RED, Slot.BLUE, Slot.GLOBAL)
_FACTION_SLOTS = {0: Slot.RED, 1: Slot.BLUE}


@dataclass(frozen=True)
class StateView:
    """One observation per slot, independent of the container form it came from."""

    form: StateForm
    red: Observation
    blue: Observation
    global_observation: Observation
    extra_slots: Mapping[int, Any]

    def observation(self, slot: Slot) -> Observation:
        return {Slot.RED: self.red, Slot.BLUE: self.blue, Slot.GLOBAL: self.global_observation}[Slot(slot)]

    def for_faction(self, faction: int) -> Observation:
        """The observation of faction 0 (red) or 1 (blue)."""
        if not isinstance(faction, int) or isinstance(faction, bool) or faction not in _FACTION_SLOTS:
            raise ContractError("faction", "0 (red) or 1 (blue)", faction)
        return self.observation(_FACTION_SLOTS[faction])


def normalize_state(raw: Any, origin: Origin = Origin.ENGINE, path: str = "state",
                    validate: bool = True) -> StateView:
    """Return the canonical view of a raw state; with ``validate``, check every observation fully."""
    if isinstance(raw, Mapping):
        slots = normalize_int_keyed(raw, origin, path)
        missing = [slot.name for slot in Slot if slot.value not in slots]
        if missing:
            raise ContractError(path, "slots 0 (red), 1 (blue) and -1 (all-seeing)", raw,
                                detail=f"missing {', '.join(missing)}")
        form = StateForm.MAPPING
        values = {slot: slots[slot.value] for slot in Slot}
        extra = {key: value for key, value in slots.items() if key not in {slot.value for slot in Slot}}
    elif isinstance(raw, (list, tuple)):
        if len(raw) != len(SEQUENCE_ORDER):
            raise ContractError(path, "a sequence of exactly 3 observations [red, blue, all-seeing]", raw)
        form = StateForm.SEQUENCE
        values = dict(zip(SEQUENCE_ORDER, raw))
        extra = {}
    else:
        raise ContractError(path, "a mapping keyed by slot or a 3-item sequence", raw)

    observations = {slot: Observation.from_raw(values[slot], origin, f"{path}[{slot.value}]") for slot in Slot}
    if validate:
        for observation in observations.values():
            observation.validate()
    return StateView(form=form, red=observations[Slot.RED], blue=observations[Slot.BLUE],
                     global_observation=observations[Slot.GLOBAL], extra_slots=MappingProxyType(extra))
