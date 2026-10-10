"""Objective assessment and whole-force task allocation.

One allocation per decision, over the own mobile ground units that can take a new order now (``free``: settled or in
the post-arrival transition, movement listed, not part of a lift). Units already moving keep their path (no operation
can change it) and are counted as commitments of their destination when they can arrive before the game ends.

Objectives offer **slots**. An objective the side does not hold offers capture slots: weights
``capture_contested`` when a known enemy ground unit is within ``contest_radius`` (or it is enemy-held), else
``capture_clear``. A held objective offers a hold slot (``hold_threatened`` when a known enemy could reach its zone
before the end, else ``hold_quiet``) unless a committed unit is already on its way, plus a reinforcement slot while
contested. Slots already filled by commitments are not offered, and no objective is offered more slots than
``destination_cap`` minus its commitments. A unit's utility for a slot is ``weight * value - time_cost * eta`` plus
persistence (``stickiness``) for its current target and, in variant B, an economy bonus on hold slots for the units
whose value is lowest. A slot a unit cannot reach ``arrival_margin`` steps before the end is never offered to it.

Variant A solves the unit-to-slot matching exactly (``assignment.hungarian``); variant B allocates greedily by utility
and may give a slot to a lift pair (an infantry unit and a co-located settled carrier, both free) whose delivery time
(embark, carrier travel, arrival transition, disembark) beats walking by ``lift_gain`` steps.
Free units left without a slot stay where they are (``reserve``); nothing is sent without a slot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import assignment as solve
from . import facts as F
from .config import Config
from .memory import CAPTURE, CARRY, HOLD, RESERVE, RIDE, SUPPORT, CommanderMemory
from .movement import Terrain, unit_mode
from .traffic import Traffic
from .world import State, Unit, World

OWN, ENEMY, NEUTRAL = "own", "enemy", "neutral"
DEFAULT_SPEED = {F.INFANTRY: 5.0, F.VEHICLE: 36.0}


@dataclass(frozen=True)
class Known:
    """A known enemy ground unit: visible now, or remembered from an earlier sighting."""

    obj_id: int
    hex: int
    type: int
    basic_speed: float
    value: float
    visible: bool
    path: Tuple[int, ...]
    weapons: Tuple[int, ...]


@dataclass(frozen=True)
class Picture:
    hex: int
    value: float
    status: str
    inbound: Tuple[Tuple[int, int], ...]   # (unit, eta) of committed movers
    fixed: Tuple[int, ...]                 # own ground units on the hex that cannot take an order now
    standing: Tuple[int, ...]              # own ground units without a path in the zone
    enemy_zone: Tuple[int, ...]
    threat_eta: float
    contested: bool

    @property
    def committed(self) -> int:
        return len(self.inbound) + len(self.fixed)


@dataclass(frozen=True)
class Assignment:
    unit: int
    kind: str
    target: int
    slot: int
    eta: int
    utility: float
    members: Tuple[int, ...] = ()
    reason: str = ""


def known_enemies(world: World, memory: CommanderMemory) -> Tuple[Known, ...]:
    visible = {}
    for e in world.enemies:
        if e.ground:
            visible[e.obj_id] = Known(e.obj_id, e.hex, e.type, e.basic_speed or DEFAULT_SPEED.get(e.type, 36.0),
                                      e.value, True, e.path, e.weapons)
    remembered = []
    for enemy, hex_, step, type_, value in memory.sightings:
        if enemy in visible or type_ not in F.GROUND:
            continue
        remembered.append(Known(enemy, hex_, type_, DEFAULT_SPEED.get(type_, 36.0), float(value), False, (), ()))
    return tuple(sorted(list(visible.values()) + remembered, key=lambda k: k.obj_id))


def enemy_eta(known: Known, target_zone: FrozenSet[int], target: int) -> float:
    """An optimistic (early) arrival estimate of an enemy ground unit at a zone: one cost unit per hex."""
    if known.hex in target_zone:
        return 0.0
    if known.path and known.path[-1] in target_zone:
        per_hex = F.SECONDS_PER_HEX_AT_1KMH / max(known.basic_speed, 1.0)
        return per_hex * len(known.path)
    distance = max(0, F.hex_distance(known.hex, target) - 1)
    return distance * F.SECONDS_PER_HEX_AT_1KMH / max(known.basic_speed, 1.0)


class Allocator:
    def __init__(self, config: Config, terrain: Terrain) -> None:
        self.config = config
        self.terrain = terrain

    # -- times ----------------------------------------------------------------------------------
    def eta(self, unit: Unit, target: int, roadblocks: FrozenSet[int]) -> Optional[float]:
        if unit.hex == target:
            return 0.0
        mode = unit_mode(unit.type, unit.move_state)
        cost = self.terrain.cost_to(mode, unit.hex, target, roadblocks)
        return self.terrain.seconds(unit.basic_speed, cost)

    def mover_eta(self, unit: Unit, roadblocks: FrozenSet[int]) -> Optional[float]:
        """Remaining free-flow time of a moving unit to its destination (a lower bound on its arrival)."""
        if not unit.path:
            return None
        mode = unit_mode(unit.type, unit.move_state)
        rest = self.terrain.cost_to(mode, unit.path[0], unit.path[-1], roadblocks)
        seconds = self.terrain.seconds(unit.basic_speed, rest)
        if seconds is None:
            return None
        return unit.seconds_into_next_hex() + seconds

    def feasible(self, world: World, eta: Optional[float]) -> bool:
        return eta is not None and world.step + eta + self.config.arrival_margin <= world.max_step

    # -- objective pictures ----------------------------------------------------------------------
    def pictures(self, world: World, known: Sequence[Known], free_ids: FrozenSet[int]) -> Tuple[Picture, ...]:
        cfg = self.config
        enemy_faction = 1 - world.faction
        out = []
        for o in world.objectives:
            status = OWN if o.flag == world.faction else ENEMY if o.flag == enemy_faction else NEUTRAL
            inbound, fixed, standing = [], [], []
            for unit in world.units + world.allies:
                if not unit.ground or unit.aboard or unit.artillery:
                    continue
                if unit.path:
                    if unit.path[-1] == o.hex:
                        eta = self.mover_eta(unit, world.roadblocks)
                        if self.feasible(world, eta):
                            inbound.append((unit.obj_id, int(eta)))
                    continue
                if unit.hex in o.zone:
                    standing.append(unit.obj_id)
                if unit.hex == o.hex and unit.obj_id not in free_ids:
                    fixed.append(unit.obj_id)
            enemy_zone = tuple(sorted(k.obj_id for k in known if k.visible and k.hex in o.zone))
            near = [k for k in known if F.hex_distance(k.hex, o.hex) <= cfg.threat_radius
                    or (k.path and k.path[-1] in o.zone)]
            threat = min((enemy_eta(k, o.zone, o.hex) for k in near), default=float("inf"))
            contested = (status == ENEMY or bool(enemy_zone)
                         or any(F.hex_distance(k.hex, o.hex) <= cfg.contest_radius for k in known)
                         or any(k.path and k.path[-1] in o.zone for k in known))
            out.append(Picture(o.hex, o.value, status, tuple(sorted(inbound)), tuple(sorted(fixed)),
                               tuple(sorted(standing)), enemy_zone, threat, contested))
        return tuple(out)

    # -- slots -----------------------------------------------------------------------------------
    def slots(self, world: World, pictures: Sequence[Picture]) -> List[Tuple[int, int, str, float]]:
        """(objective hex, slot index, kind, weight) for every slot still open."""
        cfg = self.config
        out = []
        for p in pictures:
            room = max(0, cfg.destination_cap - p.committed)
            if p.status != OWN:
                weights = cfg.capture_contested if p.contested else cfg.capture_clear
                kind = CAPTURE
            else:
                hold = cfg.hold_threatened if p.threat_eta <= world.remaining else cfg.hold_quiet
                weights = (hold, cfg.reinforce) if p.contested else (hold,)
                kind = HOLD
            for k in range(p.committed, len(weights)):
                if room <= 0:
                    break
                out.append((p.hex, k, kind, weights[k]))
                room -= 1
        return out

    # -- utilities -------------------------------------------------------------------------------
    def utility(self, world: World, memory: CommanderMemory, unit: Unit, objective: Picture, kind: str,
                weight: float, eta: float, force_top_value: float) -> float:
        cfg = self.config
        value = weight * objective.value - cfg.time_cost * eta
        task = memory.task_of(unit.obj_id)
        if (task is not None and task[2] == objective.hex) or unit.hex == objective.hex:
            value += cfg.stickiness
        if kind == HOLD and cfg.economic_holders:
            value += cfg.economy_per_value * max(0.0, force_top_value - unit.value)
            if unit.type == F.INFANTRY:
                value += cfg.infantry_holder_bonus
        return value

    def allocate(self, world: World, memory: CommanderMemory, free: Sequence[Unit], pictures: Sequence[Picture],
                 lift_candidates: Sequence[Tuple[Unit, Unit]] = (),
                 loaded: Sequence[Tuple[int, Unit, int]] = ()) -> List[Assignment]:
        """``loaded``: (passenger id, carrier, current objective) for settled loaded carriers of live lifts."""
        cfg = self.config
        slots = self.slots(world, pictures)
        by_hex = {p.hex: p for p in pictures}
        top = max([u.value for u in world.units if u.mobile_ground] + [0.0])
        etas: Dict[Tuple[int, int], Optional[float]] = {}
        for unit in free:
            for hex_ in {s[0] for s in slots}:
                etas[(unit.obj_id, hex_)] = self.eta(unit, hex_, world.roadblocks)
        if cfg.solver == "hungarian" and not lift_candidates and not loaded:
            matrix = []
            for unit in free:
                row = []
                for hex_, k, kind, weight in slots:
                    eta = etas[(unit.obj_id, hex_)]
                    row.append(self.utility(world, memory, unit, by_hex[hex_], kind, weight, eta, top)
                               if self.feasible(world, eta) else 0.0)
                matrix.append(row)
            result = solve.hungarian(matrix)
            chosen = []
            for unit, col in zip(free, result):
                if col is None:
                    continue
                hex_, k, kind, weight = slots[col]
                chosen.append(Assignment(unit.obj_id, kind, hex_, k, int(etas[(unit.obj_id, hex_)]),
                                         round(matrix[free.index(unit)][col], 6), reason=f"{kind} slot {k}"))
            return chosen
        pairs = []
        for unit in free:
            for hex_, k, kind, weight in slots:
                eta = etas[(unit.obj_id, hex_)]
                if not self.feasible(world, eta):
                    continue
                u = self.utility(world, memory, unit, by_hex[hex_], kind, weight, eta, top)
                pairs.append((u, ("solo", unit.obj_id, hex_, k), (unit.obj_id,), (hex_, k)))
        for infantry, carrier in lift_candidates:
            for hex_, k, kind, weight in slots:
                carried = self.eta(carrier, hex_, world.roadblocks)
                if carried is None:
                    continue
                eta = 3 * F.TRANSITION + carried + 5
                walk = self.eta(infantry, hex_, world.roadblocks)
                if not self.feasible(world, eta):
                    continue
                if walk is not None and self.feasible(world, walk) and walk < eta + cfg.lift_gain:
                    continue
                # The carrier arrives too (it takes the slot), and the passenger stays as the objective's holder so
                # the carrier can be re-tasked: credit that holder, charge the carrier's delay against going alone.
                u = (self.utility(world, memory, carrier, by_hex[hex_], kind, weight, eta, top)
                     + cfg.hold_quiet * by_hex[hex_].value - cfg.time_cost * max(0.0, eta - carried))
                pairs.append((u, ("lift", infantry.obj_id, carrier.obj_id, hex_, k),
                              (infantry.obj_id, carrier.obj_id), (hex_, k)))
        for passenger_id, carrier, current in loaded:
            for hex_, k, kind, weight in slots:
                carried = self.eta(carrier, hex_, world.roadblocks)
                if carried is None:
                    continue
                eta = 2 * F.TRANSITION + carried + 5
                if not self.feasible(world, eta):
                    continue
                # Sunk boarding cost: a loaded pair keeps priority over fresh claimants on every slot (stickiness),
                # and twice that on its current objective.
                u = (self.utility(world, memory, carrier, by_hex[hex_], kind, weight, eta, top)
                     + cfg.hold_quiet * by_hex[hex_].value + cfg.stickiness * (2.0 if hex_ == current else 1.0))
                pairs.append((u, ("loaded", passenger_id, carrier.obj_id, hex_, k),
                              (passenger_id, carrier.obj_id), (hex_, k)))
        chosen = []
        utilities = {p[1]: p[0] for p in pairs}
        for key, members, (hex_, k) in solve.greedy(pairs):
            kind = next(s[2] for s in slots if s[0] == hex_ and s[1] == k)
            if key[0] == "solo":
                eta = etas[(key[1], hex_)]
                chosen.append(Assignment(key[1], kind, hex_, k, int(eta), round(utilities[key], 6),
                                         reason=f"{kind} slot {k}"))
            elif key[0] == "loaded":
                passenger_id, carrier_id = key[1], key[2]
                chosen.append(Assignment(carrier_id, CARRY, hex_, k, 0, round(utilities[key], 6),
                                         members=(passenger_id, carrier_id), reason=f"carry for {kind} slot {k}"))
            else:
                infantry_id, carrier_id = key[1], key[2]
                carried = self.eta(next(u for u in free if u.obj_id == carrier_id), hex_, world.roadblocks) or 0.0
                chosen.append(Assignment(infantry_id, RIDE, hex_, k, int(3 * F.TRANSITION + carried + 5),
                                         round(utilities[key], 6), members=(infantry_id, carrier_id),
                                         reason=f"lift for {kind} slot {k}"))
        return chosen


def support_targets(world: World, pictures: Sequence[Picture], assignments: Sequence[Assignment]) -> Dict[int, int]:
    """Aircraft support: each free aircraft goes to the objective not held with the most own commitments
    (ties: higher value, nearer, lower hex); with every objective held, to the contested held one nearest to it;
    otherwise it stays. Returns unit -> target hex for aircraft that should move."""
    commitments: Dict[int, int] = {}
    for p in pictures:
        commitments[p.hex] = p.committed
    for a in assignments:
        commitments[a.target] = commitments.get(a.target, 0) + 1
    targets: Dict[int, int] = {}
    for unit in world.units:
        if not unit.air or unit.aboard or unit.path or F.MOVE not in unit.actions:
            continue
        open_ = [p for p in pictures if p.status != OWN]
        pool = open_ or [p for p in pictures if p.contested]
        if not pool:
            continue
        best = min(pool, key=lambda p: (-commitments.get(p.hex, 0), -p.value, F.hex_distance(unit.hex, p.hex), p.hex))
        if best.hex != unit.hex:
            targets[unit.obj_id] = best.hex
    return targets
