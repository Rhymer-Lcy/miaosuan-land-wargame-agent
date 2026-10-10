"""Fire support of variant B: indirect fire tied to the objective stances, arrival fire, and guided fire.

Indirect fire keeps every guard of Sprint 34's (``integrated.fire.indirect_fire``): only listed weapons, 15 to 65 hexes,
never within ``artillery_clearance`` hexes of an own ground unit, of an own unit's remaining path or of a hex an own
unit is planned to stand on this step, never next to a live impact, and the route planner keeps own ground units out of
live impact zones (``integrated.fire.hazard_hexes``). What changes:

* order of targets: first the enemies counted in the threat of a held objective (``secure``, ``defend`` or ``delay``),
  then those near a ``coalition`` target, then any other target in an objective's zone, then the rest; within a group,
  higher value, lower remaining strength, lower hex;
* ``arrival_fire``: besides stationary enemies, an enemy whose visible path ends at a hex it will reach, at free-flow
  speed, no sooner than the round's flight time and before the explosion is over (``arrival_window`` steps later) is a
  target at that end hex (it stops there for the 75-step arrival transition). The end hex obeys the same clearances.
  This aims at a predicted position; the order is recorded as such, and a judge record, not the order, is evidence of
  an effect.

Guided fire (action 9) is listed for an own unit able to guide (in the recorded games: squads, unmanned ground vehicles
and unmanned aerial vehicles) with options naming the target, the weapon and the guided carrier (``guided_obj_id``).
``guided_shots`` takes, for each such unit not acting otherwise, the option with the highest attack level (at least 1)
whose target no other shot of this step has taken and whose guided carrier is not acting this step, then lower target
strength, then ids. The carrier is reserved: it gets no other action in the step.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..integrated import facts as F
from ..integrated.memory import FireOrder, live_fire_orders
from ..integrated.world import Enemy, Unit, World
from .coalition import COALITION, DEFEND, DELAY, SECURE, Assessment
from .config import CoalitionConfig

GuidedShot = Tuple[int, int, int, int]   # (target, weapon, guided carrier, attack level)


def arrival_steps(enemy: Enemy) -> Optional[int]:
    """Free-flow steps until a moving enemy enters the last hex of its visible path (``None`` if not moving)."""
    if not enemy.path or enemy.speed <= 0:
        return None
    per_hex = 1.0 / enemy.speed
    return int(round(per_hex * len(enemy.path)))


def _priority_groups(world: World, assessments: Sequence[Assessment], threat_members: Mapping[int, Tuple[int, ...]]
                     ) -> Dict[int, int]:
    """enemy id -> group (0 best)."""
    group: Dict[int, int] = {}
    for a in assessments:
        members = threat_members.get(a.hex, ())
        if a.stance in (SECURE, DEFEND, DELAY):
            for m in members:
                group[m] = min(group.get(m, 9), 0)
        elif a.stance == COALITION:
            for m in members:
                group[m] = min(group.get(m, 9), 1)
    return group


def support_fire(world: World, config: CoalitionConfig, planned_stands: Iterable[int],
                 fire_orders: Sequence[FireOrder], assessments: Sequence[Assessment],
                 threat_members: Mapping[int, Tuple[int, ...]]) -> List[Tuple[int, int, int, str]]:
    """(artillery unit, impact hex, weapon id, reason) orders for this step."""
    base = config.base
    if not base.artillery:
        return []
    clearance = base.artillery_clearance
    protected: Set[int] = set(planned_stands)
    for unit in world.units + world.allies:
        if unit.ground and not unit.aboard:
            protected.add(unit.hex)
            protected.update(unit.path)
    live = [hex_ for hex_, _, _ in live_fire_orders(fire_orders, world.step)]
    live += [hex_ for hex_, status, _ in world.impact_points if status in (0, 1)]
    zones: Set[int] = set()
    for o in world.objectives:
        zones.update(o.zone)
    group = _priority_groups(world, assessments, threat_members) if config.fire_support else {}
    candidates: List[Tuple[Tuple, int, Enemy, str]] = []
    for e in world.enemies:
        if not e.ground:
            continue
        aim: Optional[int] = None
        why = ""
        if not e.path and e.speed <= 0:
            aim, why = e.hex, "stationary enemy"
        elif config.arrival_fire and e.path:
            steps = arrival_steps(e)
            if steps is not None and F.ARTILLERY_FLIGHT <= steps < F.ARTILLERY_FLIGHT + config.arrival_window:
                aim, why = e.path[-1], f"enemy arriving in {steps} steps"
        if aim is None:
            continue
        g = group.get(e.obj_id, 2 if aim in zones else 3)
        candidates.append(((g, -e.value, e.blood, aim, e.obj_id), aim, e, why))
    candidates.sort(key=lambda c: c[0])
    orders: List[Tuple[int, int, int, str]] = []
    taken: Set[int] = set()
    for unit in sorted(world.units, key=lambda u: u.obj_id):
        options = [o.get("weapon_id") for o in (unit.actions.get(F.INDIRECT) or ()) if F.is_int(o.get("weapon_id"))]
        if not options:
            continue
        weapon = min(options)
        for key, aim, e, why in candidates:
            if aim in taken:
                continue
            distance = F.hex_distance(unit.hex, aim)
            if not (F.ARTILLERY_MIN_RANGE <= distance <= F.ARTILLERY_MAX_RANGE):
                continue
            if any(F.hex_distance(aim, p) <= clearance for p in protected):
                continue
            if any(F.hex_distance(aim, h) <= 1 for h in live + list(taken)):
                continue
            orders.append((unit.obj_id, aim, weapon, f"{why}; priority group {key[0]}"))
            taken.add(aim)
            break
    return orders


def guided_options(unit: Unit) -> List[GuidedShot]:
    out = []
    for option in unit.actions.get(F.GUIDED) or ():
        values = [option.get(k) for k in ("target_obj_id", "weapon_id", "guided_obj_id", "attack_level")]
        if all(F.is_int(v) for v in values) and values[3] >= 1:
            out.append((values[0], values[1], values[2], values[3]))
    return out


def guided_shots(world: World, acting: FrozenSet[int], reserved_targets: Set[int]) -> Dict[int, GuidedShot]:
    """unit -> guided shot, for units not in ``acting``; updates ``reserved_targets``."""
    blood = {e.obj_id: e.blood for e in world.enemies}
    carriers: Set[int] = set()
    chosen: Dict[int, GuidedShot] = {}
    for unit in sorted(world.units, key=lambda u: u.obj_id):
        if unit.obj_id in acting:
            continue
        options = [s for s in guided_options(unit)
                   if s[0] not in reserved_targets and s[2] not in carriers and s[2] not in acting and s[2] != unit.obj_id]
        if not options:
            continue
        best = min(options, key=lambda s: (-s[3], blood.get(s[0], 99.0), s[0], s[1], s[2]))
        chosen[unit.obj_id] = best
        reserved_targets.add(best[0])
        carriers.add(best[2])
    return chosen
