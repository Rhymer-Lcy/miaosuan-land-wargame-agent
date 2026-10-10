"""Whole-force allocation over the places the objective stances offer (``coalition.coalition``).

Sprint 34's allocator (``integrated.allocation.Allocator``) is reused for travel times, feasibility and its utility;
what changes is which places exist and how a reinforcement or coalition place is valued:

* ``quiet`` and ``capture`` objectives offer Sprint 34's own hold and capture places (same weights, same caps);
* ``defend`` offers its reinforcement places (kind ``hold``) with a deadline: only a unit whose free-flow arrival
  precedes the enemy's earliest optimistic arrival may take one; ``coalition`` offers its places (kind ``capture``)
  with the coalition weights; ``secure`` and ``defend`` add the reserve places; ``delay`` and ``skip`` offer none;
* a reinforcement or coalition place is worth ``weight x value x (0.5 + power)`` for a unit of the given power, so the
  strongest units that arrive in time are preferred; quiet holds keep Sprint 34's economic preference for cheap holders.

The solver is the configured one (variant B of Sprint 34, greedy, including lift pairs); with ``safe_transport`` a lift or
a loaded carrier may only take a place at an objective whose threat is zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..integrated import assignment as solve
from ..integrated import facts as F
from ..integrated.allocation import OWN, Allocator, Assignment, Picture
from ..integrated.memory import CAPTURE, CARRY, HOLD, RIDE, CommanderMemory
from ..integrated.world import Unit, World
from . import capability as C
from .coalition import CAPTURE as S_CAPTURE
from .coalition import COALITION, DEFEND, QUIET, SECURE, Assessment
from .config import CoalitionConfig

REINFORCE, RESERVE_PLACE, BASE = "reinforce", "reserve", "base"


@dataclass(frozen=True)
class Place:
    hex: int
    index: int
    kind: str          # task kind recorded in memory: hold or capture
    role: str          # base | reinforce | reserve
    weight: float
    deadline: Optional[int]


class CoalitionAllocator(Allocator):
    def __init__(self, coalition: CoalitionConfig, terrain) -> None:
        super().__init__(coalition.base, terrain)
        self.coalition = coalition

    def places(self, world: World, pictures: Sequence[Picture], assessments: Sequence[Assessment]) -> List[Place]:
        cfg = self.config
        by_hex = {a.hex: a for a in assessments}
        out: List[Place] = []
        for p in pictures:
            a = by_hex[p.hex]
            room = max(0, cfg.destination_cap - p.committed)
            if a.stance == QUIET:
                for k in range(p.committed, 1):
                    if room <= 0:
                        break
                    out.append(Place(p.hex, k, HOLD, BASE, cfg.hold_quiet, None))
                    room -= 1
            elif a.stance == S_CAPTURE:
                weights = cfg.capture_contested if p.contested else cfg.capture_clear
                for k in range(p.committed, len(weights)):
                    if room <= 0:
                        break
                    out.append(Place(p.hex, k, CAPTURE, BASE, weights[k], None))
                    room -= 1
            elif a.stance == DEFEND:
                for k in range(a.places):
                    out.append(Place(p.hex, k, HOLD, REINFORCE, self.coalition.reinforce_weight, a.deadline))
            elif a.stance == COALITION:
                weights = self.coalition.coalition_weights
                for k in range(min(a.places, len(weights))):
                    out.append(Place(p.hex, k, CAPTURE, REINFORCE, weights[k], None))
            if a.stance in (SECURE, DEFEND):
                for k in range(a.reserve):
                    out.append(Place(p.hex, 100 + k, HOLD, RESERVE_PLACE, self.coalition.reserve_weight, None))
        return out

    def place_utility(self, world: World, memory: CommanderMemory, unit: Unit, picture: Picture, place: Place,
                      eta: float, top: float) -> float:
        if place.role == BASE:
            return self.utility(world, memory, unit, picture, place.kind, place.weight, eta, top)
        cfg = self.config
        value = place.weight * picture.value * (0.5 + C.unit_power(unit)) - cfg.time_cost * eta
        task = memory.task_of(unit.obj_id)
        if (task is not None and task[2] == picture.hex) or unit.hex == picture.hex:
            value += cfg.stickiness
        return value

    def place_feasible(self, world: World, place: Place, eta: Optional[float]) -> bool:
        if not self.feasible(world, eta):
            return False
        return place.deadline is None or world.step + eta <= place.deadline

    def allocate_places(self, world: World, memory: CommanderMemory, free: Sequence[Unit], pictures: Sequence[Picture],
                        assessments: Sequence[Assessment], lift_candidates: Sequence[Tuple[Unit, Unit]] = (),
                        loaded: Sequence[Tuple[int, Unit, int]] = ()) -> List[Assignment]:
        cfg = self.config
        places = self.places(world, pictures, assessments)
        by_hex = {p.hex: p for p in pictures}
        threat = {a.hex: a.threat for a in assessments}
        top = max([u.value for u in world.units if u.mobile_ground] + [0.0])
        etas: Dict[Tuple[int, int], Optional[float]] = {}
        for unit in free:
            for hex_ in {pl.hex for pl in places}:
                etas[(unit.obj_id, hex_)] = self.eta(unit, hex_, world.roadblocks)
        keyed = {(pl.hex, pl.index): pl for pl in places}
        if cfg.solver == "hungarian" and not lift_candidates and not loaded:
            matrix = []
            for unit in free:
                row = []
                for pl in places:
                    eta = etas[(unit.obj_id, pl.hex)]
                    row.append(self.place_utility(world, memory, unit, by_hex[pl.hex], pl, eta, top)
                               if self.place_feasible(world, pl, eta) else 0.0)
                matrix.append(row)
            result = solve.hungarian(matrix)
            chosen = []
            for i, (unit, col) in enumerate(zip(free, result)):
                if col is None:
                    continue
                pl = places[col]
                chosen.append(Assignment(unit.obj_id, pl.kind, pl.hex, pl.index, int(etas[(unit.obj_id, pl.hex)]),
                                         round(matrix[i][col], 6), reason=f"{pl.role} {pl.kind} place {pl.index}"))
            return chosen
        pairs = []
        for unit in free:
            for pl in places:
                eta = etas[(unit.obj_id, pl.hex)]
                if not self.place_feasible(world, pl, eta):
                    continue
                u = self.place_utility(world, memory, unit, by_hex[pl.hex], pl, eta, top)
                pairs.append((u, ("solo", unit.obj_id, pl.hex, pl.index), (unit.obj_id,), (pl.hex, pl.index)))
        safe = self.coalition.safe_transport
        for infantry, carrier in lift_candidates:
            for pl in places:
                if safe and threat.get(pl.hex, 0.0) > 0:
                    continue
                carried = self.eta(carrier, pl.hex, world.roadblocks)
                if carried is None:
                    continue
                eta = 3 * F.TRANSITION + carried + 5
                walk = self.eta(infantry, pl.hex, world.roadblocks)
                if not self.place_feasible(world, pl, eta):
                    continue
                if walk is not None and self.feasible(world, walk) and walk < eta + cfg.lift_gain:
                    continue
                u = (self.place_utility(world, memory, carrier, by_hex[pl.hex], pl, eta, top)
                     + cfg.hold_quiet * by_hex[pl.hex].value - cfg.time_cost * max(0.0, eta - carried))
                pairs.append((u, ("lift", infantry.obj_id, carrier.obj_id, pl.hex, pl.index),
                              (infantry.obj_id, carrier.obj_id), (pl.hex, pl.index)))
        for passenger_id, carrier, current in loaded:
            for pl in places:
                if safe and threat.get(pl.hex, 0.0) > 0:
                    continue
                carried = self.eta(carrier, pl.hex, world.roadblocks)
                if carried is None:
                    continue
                eta = 2 * F.TRANSITION + carried + 5
                if not self.place_feasible(world, pl, eta):
                    continue
                u = (self.place_utility(world, memory, carrier, by_hex[pl.hex], pl, eta, top)
                     + cfg.hold_quiet * by_hex[pl.hex].value + cfg.stickiness * (2.0 if pl.hex == current else 1.0))
                pairs.append((u, ("loaded", passenger_id, carrier.obj_id, pl.hex, pl.index),
                              (passenger_id, carrier.obj_id), (pl.hex, pl.index)))
        chosen = []
        utilities = {p[1]: p[0] for p in pairs}
        for key, members, (hex_, k) in solve.greedy(pairs):
            pl = keyed[(hex_, k)]
            if key[0] == "solo":
                chosen.append(Assignment(key[1], pl.kind, hex_, k, int(etas[(key[1], hex_)]), round(utilities[key], 6),
                                         reason=f"{pl.role} {pl.kind} place {k}"))
            elif key[0] == "loaded":
                chosen.append(Assignment(key[2], CARRY, hex_, k, 0, round(utilities[key], 6), members=(key[1], key[2]),
                                         reason=f"carry for {pl.role} {pl.kind} place {k}"))
            else:
                infantry_id, carrier_id = key[1], key[2]
                carried = self.eta(next(u for u in free if u.obj_id == carrier_id), hex_, world.roadblocks) or 0.0
                chosen.append(Assignment(infantry_id, RIDE, hex_, k, int(3 * F.TRANSITION + carried + 5),
                                         round(utilities[key], 6), members=(infantry_id, carrier_id),
                                         reason=f"lift for {pl.role} {pl.kind} place {k}"))
        return chosen


def objective_status(pictures: Sequence[Picture]) -> Mapping[int, str]:
    return {p.hex: p.status for p in pictures}


__all__ = ["CoalitionAllocator", "Place", "objective_status", "OWN"]
