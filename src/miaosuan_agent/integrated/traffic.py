"""Friendly-traffic capacity: prevent the stacking-limit blocks instead of trying to recover from them.

Facts it rests on (``docs/TACTICAL_FRONTIER.md``): a hex holds at most four own ground units; a unit whose next hex is
full waits with its path and zero speed for as long as the hex stays full, and the only action then listed, stop, is
deferred indefinitely (Sprint 4); an issued path cannot be changed. So the column deadlock of Sprints 1 and 2 (four
units on an objective, more waiting in the neighbour, the four then ordered out through that neighbour) can only be
prevented when moves are issued. The ledger therefore keeps, per hex:

* ``present``: own ground units physically in the hex now (any seat of the faction, passengers excluded);
* ``staying``: the ones without a move path that no order of this step takes away;
* ``inbound``: units whose path ends there (moving now, or ordered this step).

A planned stand (``staying + inbound``) at or above ``STACK_LIMIT`` closes the hex to every new path, a full
``present`` count closes it as a first hex, and a stand of ``STACK_LIMIT - 1`` makes it costly to cross. A
destination accepts a new unit only while its planned stand stays within the caller's cap. Every order this step is
registered before the next one is planned, in ascending unit order.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Set, Tuple

from . import facts as F
from .world import State, Unit, World

CROWDED_PENALTY = 3.0


class Traffic:
    def __init__(self, world: World) -> None:
        self.present: Dict[int, int] = world.ground_occupancy()
        self.staying: Dict[int, int] = {}
        self.inbound: Dict[int, int] = {}
        self.transit: Dict[int, int] = {}
        self.departing: Set[int] = set()
        self.waiting: Tuple[Unit, ...] = ()
        waiting = []
        for unit in world.units + world.allies:
            if not unit.ground or unit.aboard:
                continue
            if unit.path:
                self.inbound[unit.path[-1]] = self.inbound.get(unit.path[-1], 0) + 1
                for hex_ in unit.path[:-1]:
                    self.transit[hex_] = self.transit.get(hex_, 0) + 1
                if unit.state is State.WAITING:
                    waiting.append(unit)
            else:
                self.staying[unit.hex] = self.staying.get(unit.hex, 0) + 1
        self.waiting = tuple(waiting)

    def stand(self, hex_: int) -> int:
        """Own ground units that will stand on ``hex_`` once current movement and this step's orders complete."""
        return self.staying.get(hex_, 0) + self.inbound.get(hex_, 0)

    def blocked_for(self, start: int) -> FrozenSet[int]:
        """Hexes a new path from ``start`` must not enter."""
        closed = {h for h in set(self.staying) | set(self.inbound) if self.stand(h) >= F.STACK_LIMIT}
        closed.discard(start)
        return frozenset(closed)

    def penalty(self) -> Dict[int, float]:
        return {h: CROWDED_PENALTY for h in set(self.staying) | set(self.inbound)
                if self.stand(h) == F.STACK_LIMIT - 1}

    def first_hex_open(self, hex_: int) -> bool:
        return self.present.get(hex_, 0) < F.STACK_LIMIT

    def accepts(self, destination: int, cap: int) -> bool:
        return self.stand(destination) < min(cap, F.STACK_LIMIT)

    def order(self, unit: Unit, path: Tuple[int, ...]) -> None:
        """Register a move issued this step."""
        if not path:
            return
        if unit.obj_id not in self.departing:
            self.departing.add(unit.obj_id)
            self.staying[unit.hex] = max(0, self.staying.get(unit.hex, 0) - 1)
        self.inbound[path[-1]] = self.inbound.get(path[-1], 0) + 1
        for hex_ in path[:-1]:
            self.transit[hex_] = self.transit.get(hex_, 0) + 1

    def add_arrival(self, hex_: int) -> None:
        """A unit that will appear on ``hex_`` without a move (a disembarking passenger)."""
        self.inbound[hex_] = self.inbound.get(hex_, 0) + 1

    def blockers(self) -> Dict[int, Tuple[int, ...]]:
        """For every full hex some own unit waits to enter: the waiting units' ids."""
        found: Dict[int, list] = {}
        for unit in self.waiting:
            nxt = unit.path[0]
            if self.present.get(nxt, 0) >= F.STACK_LIMIT:
                found.setdefault(nxt, []).append(unit.obj_id)
        return {h: tuple(sorted(v)) for h, v in sorted(found.items())}
