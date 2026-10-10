"""Bounded local force estimates from legal observations only.

The power of a ground unit is its class weight (``config.CLASS_WEIGHT``) times its remaining strength fraction. Own
units are read from the seat's observation. Enemy units are the ones the seat sees now (full confidence) and the ones it
saw within the sighting lifetime (confidence falling linearly to zero with age); a remembered enemy keeps the class and
strength it had when last seen and is assumed to be where it was last seen. Nothing is inferred about unseen units, and
no kill probability is modelled: the estimate only ranks force against force.

An enemy's arrival at a zone is Sprint 34's optimistic estimate (``integrated.allocation.enemy_eta``): one cost unit per
hex at its basic speed, or the length of its visible path when that path ends in the zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..integrated import facts as F
from ..integrated.allocation import DEFAULT_SPEED, Known, enemy_eta
from ..integrated.world import Unit, World
from .config import CLASS_WEIGHT, FLOOR_WEIGHT, OTHER_WEIGHT, CoalitionConfig

PER_MILLE = 1000


def class_weight(sub_type: int) -> float:
    return max(FLOOR_WEIGHT, CLASS_WEIGHT.get(sub_type, OTHER_WEIGHT))


def strength_fraction(blood: float, max_blood: float) -> float:
    if max_blood <= 0:
        return 1.0 if blood > 0 else 0.0
    return max(0.0, min(1.0, blood / max_blood))


def unit_power(unit: Unit) -> float:
    return class_weight(unit.sub_type) * strength_fraction(unit.blood, unit.max_blood)


@dataclass(frozen=True)
class Threat:
    """A known enemy ground unit with its power and the confidence of the knowledge."""

    obj_id: int
    hex: int
    sub_type: int
    power: float
    confidence: float
    visible: bool
    known: Known


def enemy_max_blood(observation_operators: Iterable[object], faction: int) -> Dict[int, float]:
    """Maximum strength of every enemy operator the observation lists (the field is published with the operator)."""
    out: Dict[int, float] = {}
    for op in observation_operators:
        if getattr(op, "color", None) == faction:
            continue
        value = op.fields.get("max_blood")
        out[op.obj_id] = F.number(value)
    return out


def threats(world: World, seen: Sequence[Tuple[int, int, int, int, int]], max_blood: Mapping[int, float],
            config: CoalitionConfig) -> Tuple[Threat, ...]:
    """Every known enemy ground unit: visible now, or remembered within the sighting lifetime."""
    out: Dict[int, Threat] = {}
    for e in world.enemies:
        if not e.ground:
            continue
        strength = strength_fraction(e.blood, max_blood.get(e.obj_id, 0.0))
        known = Known(e.obj_id, e.hex, e.type, e.basic_speed or DEFAULT_SPEED.get(e.type, 36.0), e.value, True, e.path,
                      e.weapons)
        out[e.obj_id] = Threat(e.obj_id, e.hex, e.sub_type, class_weight(e.sub_type) * strength, 1.0, True, known)
    for enemy, hex_, step, sub_type, strength in seen:
        if enemy in out:
            continue
        age = world.step - step
        confidence = max(0.0, 1.0 - age / float(config.sighting_ttl))
        if confidence <= 0:
            continue
        type_ = F.INFANTRY if sub_type == F.SQUAD else F.VEHICLE
        known = Known(enemy, hex_, type_, DEFAULT_SPEED.get(type_, 36.0), 0.0, False, (), ())
        out[enemy] = Threat(enemy, hex_, sub_type, class_weight(sub_type) * strength / PER_MILLE, confidence, False,
                            known)
    return tuple(out[k] for k in sorted(out))


def observed_rows(world: World, max_blood: Mapping[int, float]) -> List[Tuple[int, int, int, int]]:
    """(enemy, hex, sub_type, strength per mille) of the enemy ground units visible now, for the sighting memory."""
    rows = []
    for e in world.enemies:
        if e.ground:
            rows.append((e.obj_id, e.hex, e.sub_type,
                         int(round(PER_MILLE * strength_fraction(e.blood, max_blood.get(e.obj_id, 0.0))))))
    return sorted(rows)


@dataclass(frozen=True)
class ZoneThreat:
    power: float           # sum of power x confidence of the enemies arriving within the horizon
    visible_power: float   # the part from enemies visible now
    eta: float             # earliest optimistic arrival (steps from now); inf when none
    members: Tuple[int, ...]


def attribute(threat_list: Sequence[Threat], objectives: Sequence[Tuple[int, FrozenSet[int]]],
              config: CoalitionConfig, enemy_held: FrozenSet[int] = frozenset()) -> Dict[int, List[Tuple[Threat, float]]]:
    """Each known enemy counts against one objective, never against all of them, and only when its optimistic arrival
    there is within ``threat_horizon``. ``objectives`` = (hex, zone) pairs; returns hex -> [(threat, arrival)].

    Revision 2 (``config.attribution == "unheld"``, the default): an enemy is a threat to an objective its own side does
    not hold (``enemy_held`` lists the ones it holds): the objective its visible path ends at if its side does not hold
    it, else the one of those it can reach first (ties count against each). An enemy standing at an objective its side
    holds is therefore counted against the next objective it can take, which is how ``baseline-v2`` moves (it sends
    idle units from held objectives to the nearest one it does not hold). If its side holds every objective, all count.
    Revision 1 (``"first"``, registered first and corrected after its registered comparison): the objective its path
    ends at, else the one it reaches first, whoever holds it."""
    out: Dict[int, List[Tuple[Threat, float]]] = {hex_: [] for hex_, _ in objectives}
    pool = [(hex_, zone) for hex_, zone in objectives if hex_ not in enemy_held] if config.attribution == "unheld" \
        else list(objectives)
    pool = pool or list(objectives)
    for t in threat_list:
        etas = [(enemy_eta(t.known, zone, hex_), hex_) for hex_, zone in pool]
        if not etas:
            continue
        heading = [hex_ for hex_, zone in pool if t.known.path and t.known.path[-1] in zone]
        if heading:
            chosen = [(e, h) for e, h in etas if h in heading]
        else:
            first = min(e for e, _ in etas)
            chosen = [(e, h) for e, h in etas if e == first]
        for arrival, hex_ in chosen:
            if arrival <= config.threat_horizon:
                out[hex_].append((t, arrival))
    return out


def zone_threat(assigned: Sequence[Tuple[Threat, float]]) -> ZoneThreat:
    """The threat of one objective from the enemies attributed to it (``attribute``)."""
    power = visible = 0.0
    eta = float("inf")
    members = []
    for t, arrival in assigned:
        power += t.power * t.confidence
        if t.visible:
            visible += t.power
        eta = min(eta, arrival)
        members.append(t.obj_id)
    return ZoneThreat(round(power, 6), round(visible, 6), eta, tuple(sorted(members)))


def defenders(world: World, zone: FrozenSet[int]) -> List[Unit]:
    """Own ground units (any seat of the faction) standing in the zone: no move path, not aboard, not artillery."""
    return [u for u in world.units + world.allies
            if u.ground and not u.aboard and not u.artillery and not u.path and u.hex in zone]


def inbound(world: World, zone: FrozenSet[int]) -> List[Unit]:
    """Own ground units whose current path ends in the zone."""
    return [u for u in world.units + world.allies
            if u.ground and not u.aboard and not u.artillery and u.path and u.path[-1] in zone]


def total_power(units: Iterable[Unit]) -> float:
    return round(sum(unit_power(u) for u in units), 6)


def holder_rank(unit: Unit) -> Tuple[int, float, int]:
    """Order in which a unit is preferred as the last holder of a zone: infantry first (Sprint 34 live games: squads took
    about a tenth of the damage per unit-step that vehicles took), then the lowest value, then the id."""
    return (0 if unit.type == F.INFANTRY else 1, unit.value, unit.obj_id)


def eta_or_none(value: Optional[float]) -> float:
    return float("inf") if value is None else value
