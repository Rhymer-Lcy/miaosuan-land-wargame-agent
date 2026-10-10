"""Allocation over the Sprint 36 stance places: Sprint 35's coalition allocator plus two place rules.

* A held objective in ``delay`` with nobody standing in it, whose assessment offers one place
  (``tactical.assess.DELAY_ROLE_NOTE``), gets one ``delay`` place: only a cheap unit (``tactical.assess.is_cheap``)
  arriving by the enemy's optimistic arrival may take it, at the reinforcement weight.
* Variant B: a coalition place at an objective lost within ``counterattack_window`` steps is worth
  ``1 + counterattack_bonus`` times its weight.

Everything else - Sprint 34's hold and capture places for ``quiet`` and ``capture``, Sprint 35's reinforcement,
coalition and reserve places, the utilities, the greedy solver with lift pairs, safe transport - is Sprint 35's
``coalition.allocator.CoalitionAllocator`` unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from ..coalition.allocator import BASE, CoalitionAllocator, Place
from ..coalition.coalition import COALITION, DELAY, Assessment
from ..integrated import assignment as solve
from ..integrated import facts as F
from ..integrated.allocation import Assignment, Picture
from ..integrated.memory import CARRY, HOLD, RIDE, CommanderMemory
from ..integrated.world import Unit, World
from .assess import DELAY_ROLE_NOTE, cheap_limit, is_cheap
from .config import TacticalConfig

DELAY_PLACE = "delay"


class TacticalAllocator(CoalitionAllocator):
    def __init__(self, tactical: TacticalConfig, terrain) -> None:
        super().__init__(tactical.coalition, terrain)
        self.tactical = tactical
        self.lost: Dict[int, int] = {}

    def places(self, world: World, pictures: Sequence[Picture], assessments: Sequence[Assessment]) -> List[Place]:
        out = super().places(world, pictures, assessments)
        t = self.tactical
        if t.counterattack_bonus > 0:
            recent = {h for h, step in self.lost.items() if world.step - step <= t.counterattack_window}
            out = [replace(pl, weight=pl.weight * (1.0 + t.counterattack_bonus))
                   if (pl.hex in recent and pl.role != BASE and pl.kind == "capture") else pl for pl in out]
        for a in assessments:
            if a.stance == DELAY and a.places == 1 and a.note == DELAY_ROLE_NOTE:
                out.append(Place(a.hex, 200, HOLD, DELAY_PLACE, self.coalition.reinforce_weight, a.deadline))
        return out

    def allocate_places(self, world: World, memory: CommanderMemory, free: Sequence[Unit], pictures: Sequence[Picture],
                        assessments: Sequence[Assessment], lift_candidates: Sequence[Tuple[Unit, Unit]] = (),
                        loaded: Sequence[Tuple[int, Unit, int]] = ()) -> List[Assignment]:
        """Sprint 35's greedy allocation (``CoalitionAllocator.allocate_places``) with one restriction: a ``delay``
        place is offered only to a cheap unit walking (never to a lift or a loaded carrier)."""
        cfg = self.config
        if cfg.solver != "greedy":
            return super().allocate_places(world, memory, free, pictures, assessments, lift_candidates, loaded)
        places = self.places(world, pictures, assessments)
        by_hex = {p.hex: p for p in pictures}
        threat = {a.hex: a.threat for a in assessments}
        top = max([u.value for u in world.units if u.mobile_ground] + [0.0])
        limit = cheap_limit(world, self.tactical.cheap_share)
        etas: Dict[Tuple[int, int], Optional[float]] = {}
        for unit in free:
            for hex_ in {pl.hex for pl in places}:
                etas[(unit.obj_id, hex_)] = self.eta(unit, hex_, world.roadblocks)
        keyed = {(pl.hex, pl.index): pl for pl in places}
        pairs = []
        for unit in free:
            for pl in places:
                if pl.role == DELAY_PLACE and not is_cheap(unit, limit):
                    continue
                eta = etas[(unit.obj_id, pl.hex)]
                if not self.place_feasible(world, pl, eta):
                    continue
                u = self.place_utility(world, memory, unit, by_hex[pl.hex], pl, eta, top)
                pairs.append((u, ("solo", unit.obj_id, pl.hex, pl.index), (unit.obj_id,), (pl.hex, pl.index)))
        safe = self.coalition.safe_transport
        lift_places = [pl for pl in places if pl.role != DELAY_PLACE]
        for infantry, carrier in lift_candidates:
            for pl in lift_places:
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
            for pl in lift_places:
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


__all__ = ["TacticalAllocator", "DELAY_PLACE"]
