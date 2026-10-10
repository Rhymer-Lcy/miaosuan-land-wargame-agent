"""The integrated agent's explicit memory: the only state carried from one decision to the next.

Every member is a sorted tuple of int/str tuples (or a scalar), so equal memories are equal values, a memory has one
canonical serialisation, and a decision is a pure function of (observation, memory). Sizes are bounded: tasks and
transport records exist only for live own units, sightings expire after ``SIGHTING_TTL`` steps and are capped at
``MAX_SIGHTINGS``, fire orders expire when their impact hex can no longer explode.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from . import facts as F

SIGHTING_TTL = 600
MAX_SIGHTINGS = 96
FIRE_MEMORY = F.ARTILLERY_FLIGHT + F.ARTILLERY_EXPLOSION + 30

#: Task kinds (an own unit has at most one).
CAPTURE, HOLD, SUPPORT, RIDE, CARRY, RESERVE = "capture", "hold", "support", "ride", "carry", "reserve"
KINDS = (CAPTURE, HOLD, SUPPORT, RIDE, CARRY, RESERVE)
#: Transport phases.
BOARDING, CARRYING, UNLOADING = "boarding", "carrying", "unloading"

Task = Tuple[int, str, int, int]            # (unit, kind, target hex, since step)
Lift = Tuple[int, int, int, str, int]       # (passenger, carrier, objective hex, phase, since step)
Sighting = Tuple[int, int, int, int, int]   # (enemy, hex, step, type, value)
FireOrder = Tuple[int, int, int]            # (impact hex, order step, artillery unit)
Order = Tuple[int, int, int]                # (unit, action type, step)


@dataclass(frozen=True)
class CommanderMemory:
    deployment_sent: bool = False
    tasks: Tuple[Task, ...] = ()
    lifts: Tuple[Lift, ...] = ()
    sightings: Tuple[Sighting, ...] = ()
    fire_orders: Tuple[FireOrder, ...] = ()
    orders: Tuple[Order, ...] = ()
    first_owned: Tuple[Tuple[int, int], ...] = ()
    fallbacks: int = 0

    def task_of(self, unit: int) -> Optional[Task]:
        for task in self.tasks:
            if task[0] == unit:
                return task
        return None

    def lift_of(self, unit: int) -> Optional[Lift]:
        for lift in self.lifts:
            if lift[0] == unit or lift[1] == unit:
                return lift
        return None

    def last_order(self, unit: int) -> Optional[Order]:
        for order in self.orders:
            if order[0] == unit:
                return order
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"deployment_sent": self.deployment_sent, "tasks": [list(t) for t in self.tasks],
                "lifts": [list(x) for x in self.lifts], "sightings": [list(s) for s in self.sightings],
                "fire_orders": [list(f) for f in self.fire_orders], "orders": [list(o) for o in self.orders],
                "first_owned": [list(x) for x in self.first_owned], "fallbacks": self.fallbacks}


def canonical(memory: CommanderMemory) -> CommanderMemory:
    return replace(memory, tasks=tuple(sorted(set(memory.tasks))), lifts=tuple(sorted(set(memory.lifts))),
                   sightings=tuple(sorted(set(memory.sightings))), fire_orders=tuple(sorted(set(memory.fire_orders))),
                   orders=tuple(sorted(set(memory.orders))), first_owned=tuple(sorted(set(memory.first_owned))))


def updated_sightings(previous: Iterable[Sighting], seen: Iterable[Tuple[int, int, int, int]], step: int) -> Tuple[Sighting, ...]:
    """Latest sighting per enemy: ``seen`` = (enemy, hex, type, value) observed now; old ones expire."""
    latest: Dict[int, Sighting] = {}
    for s in previous:
        if step - s[2] <= SIGHTING_TTL:
            latest[s[0]] = s
    for enemy, hex_, type_, value in seen:
        latest[enemy] = (enemy, hex_, step, type_, value)
    kept = sorted(latest.values(), key=lambda s: (-s[2], s[0]))[:MAX_SIGHTINGS]
    return tuple(sorted(kept))


def live_fire_orders(orders: Iterable[FireOrder], step: int) -> Tuple[FireOrder, ...]:
    return tuple(sorted(o for o in orders if step - o[1] <= FIRE_MEMORY))


def first_owned_update(previous: Iterable[Tuple[int, int]], owned_now: Iterable[int], step: int) -> Tuple[Tuple[int, int], ...]:
    known = {hex_: s for hex_, s in previous}
    for hex_ in owned_now:
        known.setdefault(hex_, step)
    return tuple(sorted(known.items()))


def as_pairs(mapping: Mapping[int, Any]) -> Tuple[Tuple[int, Any], ...]:
    return tuple(sorted(mapping.items()))
