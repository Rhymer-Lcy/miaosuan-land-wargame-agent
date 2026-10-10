"""Direct and indirect fire.

Direct fire keeps ``baseline-v2``'s evidence-backed rules (``docs/BASELINE_V2.md``): only listed options at attack
level 1 or more; the highest attack level first, then (``baseline-v2``) the lower target id; at most one shot per
target in one step (the shoot-target reservation that removed 89% of the code-516 refusals). Variant B breaks ties
within the highest attack level by the target's lower observed remaining strength (``blood``) before the target id;
no hit or damage probability is modelled (``docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md``).

Indirect fire (variant B only) is ordered for an artillery unit whose action 8 is listed, at a visible enemy ground unit
without a move path (it can still be there 150 steps later), 15 to 65 hexes away (the accepted range observed in
Sprint 8). It is never ordered within ``artillery_clearance`` hexes of an own ground unit, of the remaining path of an
own moving unit, of a hex an own unit is planned to stand on this step, or of a live earlier impact. Targets in an
objective's zone come first, then higher value, lower remaining strength, lower hex.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import facts as F
from .config import Config
from .memory import FireOrder, live_fire_orders
from .world import Unit, World

Shot = Tuple[int, int, int]  # (target, weapon, attack level)


def shoot_options(unit: Unit) -> List[Shot]:
    out = []
    for option in unit.actions.get(F.SHOOT) or ():
        values = [option.get(k) for k in ("target_obj_id", "weapon_id", "attack_level")]
        if all(F.is_int(v) for v in values) and values[2] >= 1:
            out.append((values[0], values[1], values[2]))
    return out


def direct_fire(world: World, config: Config, units: Iterable[Unit]) -> Dict[int, Shot]:
    blood = {e.obj_id: e.blood for e in world.enemies}
    reserved: Set[int] = set()
    chosen: Dict[int, Shot] = {}
    for unit in sorted(units, key=lambda u: u.obj_id):
        options = [s for s in shoot_options(unit) if s[0] not in reserved]
        if not options:
            continue
        if config.fire_blood_tiebreak:
            best = min(options, key=lambda s: (-s[2], blood.get(s[0], 99.0), s[0], s[1]))
        else:
            best = min(options, key=lambda s: (-s[2], s[0], s[1]))
        chosen[unit.obj_id] = best
        reserved.add(best[0])
    return chosen


def hazard_hexes(world: World, fire_orders: Sequence[FireOrder], rows: int, cols: int) -> FrozenSet[int]:
    """Hexes a ground route must avoid: live own impacts and observed impact points, with their neighbours."""
    centres = {hex_ for hex_, _, _ in live_fire_orders(fire_orders, world.step)}
    centres.update(hex_ for hex_, status, _ in world.impact_points if status in (0, 1))
    out: Set[int] = set()
    for c in centres:
        out.update(F.zone(c, rows, cols))
    return frozenset(out)


def indirect_fire(world: World, config: Config, planned_stands: Iterable[int],
                  fire_orders: Sequence[FireOrder]) -> List[Tuple[int, int, int]]:
    """(artillery unit, impact hex, weapon id) orders for this step."""
    if not config.artillery:
        return []
    clearance = config.artillery_clearance
    protected: Set[int] = set(planned_stands)
    for unit in world.units + world.allies:
        if unit.ground and not unit.aboard:
            protected.add(unit.hex)
            protected.update(unit.path)
    live = [hex_ for hex_, _, _ in live_fire_orders(fire_orders, world.step)]
    live += [hex_ for hex_, status, _ in world.impact_points if status in (0, 1)]
    zones = set()
    for o in world.objectives:
        zones.update(o.zone)
    targets = sorted((e for e in world.enemies if e.ground and not e.path and e.speed <= 0),
                     key=lambda e: (0 if e.hex in zones else 1, -e.value, e.blood, e.hex, e.obj_id))
    orders: List[Tuple[int, int, int]] = []
    taken: Set[int] = set()
    for unit in sorted(world.units, key=lambda u: u.obj_id):
        options = [o.get("weapon_id") for o in (unit.actions.get(F.INDIRECT) or ()) if F.is_int(o.get("weapon_id"))]
        if not options:
            continue
        weapon = min(options)
        for e in targets:
            if e.hex in taken:
                continue
            distance = F.hex_distance(unit.hex, e.hex)
            if not (F.ARTILLERY_MIN_RANGE <= distance <= F.ARTILLERY_MAX_RANGE):
                continue
            if any(F.hex_distance(e.hex, p) <= clearance for p in protected):
                continue
            if any(F.hex_distance(e.hex, h) <= 1 for h in live + list(taken)):
                continue
            orders.append((unit.obj_id, e.hex, weapon))
            taken.add(e.hex)
            break
    return orders


def threat_penalty(world: World, config: Config, rows: int, cols: int) -> Dict[int, float]:
    """Extra route cost per hex inside the published direct-fire range of visible enemy ground units (variant B)."""
    if not config.threat_routing:
        return {}
    penalty: Dict[int, float] = {}
    for e in world.enemies:
        if not e.ground:
            continue
        reach = F.max_weapon_range(e.weapons)
        if reach <= 0:
            continue
        r0, c0 = divmod(e.hex, 100)
        for r in range(max(0, r0 - reach), min(rows, r0 + reach + 1)):
            for c in range(max(0, c0 - reach - 1), min(cols, c0 + reach + 2)):
                h = r * 100 + c
                if F.hex_distance(e.hex, h) <= reach:
                    penalty[h] = min(config.threat_cost_cap, penalty.get(h, 0.0) + config.threat_cost)
    return penalty
