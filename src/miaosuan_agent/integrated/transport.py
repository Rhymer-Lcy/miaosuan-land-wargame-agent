"""Transport of infantry on carriers: lift candidates and the lift life cycle.

Mechanism (Sprint 22's registered probe, ``docs/SPRINT22_T2_TRANSPORT_PROBE.md``, and Sprint 34's listing measurement):
embark (action 3, by the passenger, target the carrier) is listed only for a settled passenger sharing a hex with a
settled carrier and completes 75 steps later; the loaded carrier moves at its own speed; disembark (action 4, by the
carrier, target the passenger) is listed only for a settled carrier, i.e. after its 75-step arrival transition, and
completes 75 steps later with the passenger on the carrier's hex.

A lift record (memory) is ``(passenger, carrier, objective, phase, since)``:

* ``boarding``: embark ordered at ``since``; the carrier is held settled. It becomes ``carrying`` once the passenger is
  aboard the carrier; it is dropped (``LIFT_TIMEOUT``) if the passenger is neither boarding nor aboard 10 steps after
  the order, or when either unit is gone.
* ``carrying``: the carrier is moved to the objective under the usual traffic rules; on the objective (or, past
  ``carry_deadline``, wherever it has settled) and settled with disembark listed for the passenger, disembark is
  ordered (``unloading``).
* ``unloading``: done when the passenger stands on the ground again; its record is replaced by a task on the
  objective. Dropped if neither unit is seen any more.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import facts as F
from .memory import BOARDING, CARRYING, UNLOADING, Lift
from .world import State, Unit, World

ORDER_GRACE = 10


@dataclass(frozen=True)
class LiftStep:
    """What the lift life cycle wants this decision."""

    lifts: Tuple[Lift, ...]                      # records kept for the next memory (phase updated)
    orders: Tuple[Tuple[int, dict], ...]         # (unit, action) for boarding / unloading
    carry_moves: Tuple[Tuple[int, int], ...]     # (carrier, objective) carriers to move
    hold_still: Tuple[int, ...]                  # units that must not be given another order
    delivered: Tuple[Tuple[int, int], ...]       # (passenger, objective) passengers back on the ground
    notes: Tuple[str, ...]
    loaded: Tuple[Tuple[int, int, int], ...] = ()  # (passenger, carrier, objective): settled loaded carriers that
    #                                                 the allocator may re-target (or unload where they stand)


def options(unit: Unit, action_type: int) -> Tuple[int, ...]:
    return tuple(sorted(o.get("target_obj_id") for o in (unit.actions.get(action_type) or ())
                        if F.is_int(o.get("target_obj_id"))))


def candidates(world: World, free_ids: Sequence[int], busy: Sequence[int]) -> List[Tuple[Unit, Unit]]:
    """(infantry, carrier) pairs that could start a lift now: both free and settled, sharing a hex, embark listed for
    the infantry with that carrier, the carrier carrying no infantry."""
    free = set(free_ids) - set(busy)
    pairs = []
    for infantry in world.units:
        if infantry.obj_id not in free or infantry.type != F.INFANTRY or infantry.state is not State.SETTLED:
            continue
        for carrier_id in options(infantry, F.GET_ON):
            carrier = world.unit(carrier_id)
            if carrier is None or carrier.obj_id not in free or carrier.state is not State.SETTLED:
                continue
            if carrier.hex != infantry.hex or not carrier.carrier:
                continue
            loaded = [world.passenger(pid) for pid in carrier.passengers]
            if any(p is not None and p.type == F.INFANTRY for p in loaded):
                continue
            pairs.append((infantry, carrier))
    return pairs


def step_lifts(world: World, lifts: Sequence[Lift], carry_deadline: int) -> LiftStep:
    kept: List[Lift] = []
    orders: List[Tuple[int, dict]] = []
    moves: List[Tuple[int, int]] = []
    still: List[int] = []
    delivered: List[Tuple[int, int]] = []
    notes: List[str] = []
    loaded: List[Tuple[int, int, int]] = []
    for passenger_id, carrier_id, objective, phase, since in sorted(lifts):
        carrier = world.unit(carrier_id)
        on_ground = world.unit(passenger_id)
        aboard = world.passenger(passenger_id)
        if carrier is None and aboard is None and on_ground is None:
            notes.append(f"lift {passenger_id}/{carrier_id} dropped: both units gone")
            continue
        if phase == BOARDING:
            if aboard is not None and carrier is not None and passenger_id in carrier.passengers:
                phase, since = CARRYING, world.step
            elif on_ground is not None and on_ground.state is State.BOARDING and carrier is not None:
                kept.append((passenger_id, carrier_id, objective, BOARDING, since))
                still.extend((passenger_id, carrier_id))
                continue
            elif world.step - since > ORDER_GRACE or carrier is None or on_ground is None:
                notes.append(f"lift {passenger_id}/{carrier_id} dropped: embark not executed")
                continue
            else:
                kept.append((passenger_id, carrier_id, objective, BOARDING, since))
                still.extend((passenger_id, carrier_id))
                continue
        if phase == CARRYING:
            if carrier is None:
                notes.append(f"lift {passenger_id}/{carrier_id} dropped: carrier gone")
                continue
            if aboard is None and on_ground is not None:
                delivered.append((passenger_id, objective))
                continue
            at_target = carrier.hex == objective
            overdue = world.step >= carry_deadline
            if carrier.path or carrier.state is not State.SETTLED:
                kept.append((passenger_id, carrier_id, objective, CARRYING, since))
                still.append(carrier_id)
                continue
            if (at_target or overdue) and passenger_id in options(carrier, F.GET_OFF):
                orders.append((carrier_id, {"type": F.GET_OFF, "obj_id": carrier_id, "target_obj_id": passenger_id}))
                kept.append((passenger_id, carrier_id, objective, UNLOADING, world.step))
                still.append(carrier_id)
                continue
            if not at_target and F.MOVE in carrier.actions:
                moves.append((carrier_id, objective))
                loaded.append((passenger_id, carrier_id, objective))
            kept.append((passenger_id, carrier_id, objective, CARRYING, since))
            still.append(carrier_id)
            continue
        if phase == UNLOADING:
            if on_ground is not None and aboard is None:
                delivered.append((passenger_id, objective))
                continue
            if world.step - since > F.TRANSITION + ORDER_GRACE and carrier is not None and aboard is not None:
                kept.append((passenger_id, carrier_id, objective, CARRYING, world.step))
                notes.append(f"lift {passenger_id}/{carrier_id}: disembark not executed, carrying again")
                still.append(carrier_id)
                continue
            kept.append((passenger_id, carrier_id, objective, UNLOADING, since))
            if carrier is not None:
                still.append(carrier_id)
    return LiftStep(tuple(sorted(kept)), tuple(orders), tuple(sorted(moves)), tuple(sorted(set(still))),
                    tuple(sorted(delivered)), tuple(notes), tuple(sorted(loaded)))
