"""Sprint 36 objective assessment: Sprint 35's stances, then four survival and opportunity rules on top of them.

Sprint 35's assessment (``coalition.coalition.assess``) is called unchanged on a filtered threat list; its stances are
then revised by the rules below, each behind its own switch in ``tactical.config.TacticalConfig``. With every switch off
the result is exactly Sprint 35's (``ta-as-ca``), so every difference from Sprint 35 is attributable to a named rule.

1. **Static filter** (``static_filter``). An enemy ground unit seen standing on one hex without a move path for at least
   ``static_steps`` steps, and not standing in any objective's zone, is removed from the threat list: it neither blocks
   occupation (only an enemy in the zone does) nor approaches. A unit that moves loses that status at once
   (``tactical.memory.updated_posts``). Calibration (report section 7.2): in the 40 recorded live games no
   ``baseline-v2`` ground unit stood still outside an objective zone for more than one step, so the filter removes no
   moving attacker of that kind; it removes the motionless units that made Sprint 35 skip 20 of 80 model scenario-sides.
2. **Opportunity capture** (``opportunity_capture``). An objective the side does not hold, in ``skip`` or ``coalition``,
   with no known enemy in its zone, becomes ``capture`` (Sprint 34's capture places) when some free unit's free-flow
   arrival is at least ``race_margin`` steps earlier than every remaining threat's optimistic arrival at the zone:
   the unit takes it first, and holding it afterwards is the defence rules' task.
3. **Survival delay** (``defence == "survival"``). For a held objective in ``delay`` (defenders plus reachable
   reinforcements below the commit ratio), instead of keeping every defender: one *cheap* defender (value at most
   ``cheap_share`` of the side's highest mobile ground value; infantry first, then lowest value) stays to deny
   occupation (``delay_holder``); every other standing defender withdraws (``withdrawal``) when at least
   ``withdraw_visible_share`` of the threat is visible now, the earliest enemy arrival is at least ``withdraw_lead``
   steps away (it is not already under fire) and a destination exists: the nearest held objective not in delay, else
   the nearest reachable hex outside every objective zone that is at least ``safe_margin`` hexes farther from every
   visible threat member than the unit is now (``safe_hex``). A defender that cannot withdraw stays. In the last ``end_window`` steps every defender stays
   (only the final ownership is scored). With nobody standing in the zone, one *cheap* free unit arriving before the
   enemy may take a delaying place (``empty_holder``).
4. **Counterattack priority** (``counterattack_bonus``; variant B). Coalition places at an objective lost within
   ``counterattack_window`` steps are worth that much more (``tactical.allocator``).
"""

from __future__ import annotations

import heapq
from dataclasses import replace
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from ..coalition import capability as C
from ..coalition import coalition as K
from ..coalition.coalition import Assessment
from ..decision.routing import ROADBLOCKED_MODES
from ..integrated import facts as F
from ..integrated.allocation import ENEMY, OWN, Allocator, Picture, enemy_eta
from ..integrated.movement import unit_mode
from ..integrated.traffic import Traffic
from ..integrated.world import Unit, World
from .config import TacticalConfig
from .memory import TacticalMemory

DELAY_ROLE_NOTE = "delaying place for a cheap unit"
SAFE_RADIUS = 8


# ------------------------------------------------------------------------------------------------ threats
def is_static(threat: C.Threat, memory: TacticalMemory, step: int, minimum: int) -> bool:
    post = memory.post_of(threat.obj_id)
    return post is not None and post[1] == threat.hex and step - post[2] >= minimum


def filtered_threats(world: World, memory: TacticalMemory, threat_list: Sequence[C.Threat],
                     tcfg: TacticalConfig) -> Tuple[C.Threat, ...]:
    """The threat list without static enemies standing outside every objective zone (rule 1)."""
    if not tcfg.static_filter:
        return tuple(threat_list)
    zones: Set[int] = set()
    for o in world.objectives:
        zones.update(o.zone)
    return tuple(t for t in threat_list
                 if t.hex in zones or not is_static(t, memory, world.step, tcfg.static_steps))


def cheap_limit(world: World, share: float) -> float:
    top = max([u.value for u in world.units if u.mobile_ground] + [0.0])
    return share * top


def is_cheap(unit: Unit, limit: float) -> bool:
    return unit.value <= limit


# ------------------------------------------------------------------------------------------------ assessment
def assess(world: World, memory: TacticalMemory, allocator: Allocator, tcfg: TacticalConfig,
           pictures: Sequence[Picture], threat_list: Sequence[C.Threat], free: Sequence[Unit],
           traffic: Optional[Traffic] = None, terrain=None) -> Tuple[Assessment, ...]:
    """One assessment per objective, in ``pictures`` order. Pure function of its inputs."""
    cfg = tcfg.coalition
    threats = filtered_threats(world, memory, threat_list, tcfg)
    base = K.assess(world, memory, allocator, cfg, pictures, threats, free)
    out: List[Assessment] = list(base)
    zones = {o.hex: o.zone for o in world.objectives}
    by_hex = {p.hex: p for p in pictures}
    held = [p.hex for p in pictures if p.status == OWN]
    stance = {a.hex: a.stance for a in base}
    free_ids = frozenset(u.obj_id for u in free)
    limit = cheap_limit(world, tcfg.cheap_share)
    for i, a in enumerate(out):
        p = by_hex[a.hex]
        zone = zones[a.hex]
        if (tcfg.opportunity_capture and p.status != OWN and a.stance in (K.SKIP, K.COALITION)):
            out[i] = _opportunity(a, world, allocator, zone, threats, free, tcfg.race_margin)
        elif a.stance == K.DELAY and tcfg.defence == "survival":
            out[i] = _survival_delay(a, world, allocator, tcfg, zone, threats, free, free_ids, held, stance, limit,
                                     traffic, terrain)
    return tuple(out)


def _opportunity(a: Assessment, world: World, allocator: Allocator, zone: FrozenSet[int],
                 threats: Sequence[C.Threat], free: Sequence[Unit], margin: int) -> Assessment:
    if any(t.hex in zone and t.confidence > 0 for t in threats):
        return a
    contest = min((enemy_eta(t.known, zone, a.hex) for t in threats if t.confidence > 0), default=float("inf"))
    ours = None
    for unit in free:
        if not unit.mobile_ground:
            continue
        eta = allocator.eta(unit, a.hex, world.roadblocks)
        if eta is None or not allocator.feasible(world, eta):
            continue
        ours = eta if ours is None else min(ours, eta)
    if ours is None or ours + margin > contest:
        return a
    return replace(a, stance=K.CAPTURE, places=0, requirement=0.0,
                   note=f"opportunity: a free unit arrives in {int(ours)} steps, the first contest in "
                        f"{'none' if contest == float('inf') else int(contest)}")


def _survival_delay(a: Assessment, world: World, allocator: Allocator, tcfg: TacticalConfig, zone: FrozenSet[int],
                    threats: Sequence[C.Threat], free: Sequence[Unit], free_ids: FrozenSet[int],
                    held: Sequence[int], stance: Mapping[int, str], limit: float,
                    traffic: Optional[Traffic], terrain) -> Assessment:
    standing = [u for u in C.defenders(world, zone) if u.controllable]
    mine = sorted(standing, key=C.holder_rank)
    if not mine:
        if not tcfg.empty_holder:
            return a
        deadline = (world.step + int(a.enemy_eta)) if a.enemy_eta != float("inf") else None
        cheap_free = [u for u in free if u.mobile_ground and is_cheap(u, limit)]
        if not cheap_free:
            return replace(a, keep=(), withdraw=(), note="untenable and empty; no cheap unit is free")
        return replace(a, places=1, deadline=deadline, keep=(), withdraw=(), note=DELAY_ROLE_NOTE)
    if world.remaining <= tcfg.end_window:
        return replace(a, keep=tuple(sorted(u.obj_id for u in mine)), withdraw=(),
                       note="end window: every defender stays to the end")
    holder = next((u for u in mine if is_cheap(u, limit)), None) if tcfg.delay_holder else None
    members = [t for t in threats if t.obj_id in _members(a, threats, zone, tcfg.coalition.threat_horizon)]
    share = a.visible_threat / a.threat if a.threat > 0 else 0.0
    leaving: List[Tuple[int, int]] = []
    if tcfg.withdrawal and share >= tcfg.withdraw_visible_share and a.enemy_eta >= tcfg.withdraw_lead:
        for u in mine:
            if holder is not None and u.obj_id == holder.obj_id:
                continue
            if u.obj_id not in free_ids:
                continue
            dest = _destination(allocator, world, u, a.hex, held, stance, members, tcfg, traffic, terrain)
            if dest is not None:
                leaving.append((u.obj_id, dest))
    gone = {w[0] for w in leaving}
    keep = tuple(sorted(u.obj_id for u in mine if u.obj_id not in gone))
    if holder is None:
        note = "untenable: no cheap holder; " + (f"{len(leaving)} withdraw" if leaving else "nobody can withdraw")
    else:
        note = f"untenable: cheap holder kept; {len(leaving)} withdraw"
    return replace(a, keep=keep, withdraw=tuple(sorted(leaving)), note=note)


def _members(a: Assessment, threats: Sequence[C.Threat], zone: FrozenSet[int], horizon: int) -> Set[int]:
    """Visible enemies whose optimistic arrival at the zone is within the threat horizon (the enemies a withdrawing
    unit must keep its distance from)."""
    out = set()
    for t in threats:
        if t.visible and enemy_eta(t.known, zone, a.hex) <= horizon:
            out.add(t.obj_id)
    return out


def _destination(allocator: Allocator, world: World, unit: Unit, origin: int, held: Sequence[int],
                 stance: Mapping[int, str], members: Sequence[C.Threat], tcfg: TacticalConfig,
                 traffic: Optional[Traffic], terrain) -> Optional[int]:
    """Nearest held objective other than ``origin`` not in delay; else the nearest safe hex (encoded as a hex, not an
    objective). ``None`` when neither exists."""
    best = None
    for hex_ in held:
        if hex_ == origin or stance.get(hex_) == K.DELAY:
            continue
        eta = allocator.eta(unit, hex_, world.roadblocks)
        if eta is None or not allocator.feasible(world, eta):
            continue
        key = (eta, hex_)
        if best is None or key < best[0]:
            best = (key, hex_)
    if best is not None:
        return best[1]
    return safe_hex(world, unit, members, tcfg, traffic, terrain, allocator)


def local_costs(terrain, mode, start: int, radius: int, roadblocks: FrozenSet[int]) -> Dict[int, float]:
    """Cheapest entry-cost sums from ``start`` to every hex within ``radius`` hexes of it (a bounded forward search;
    the Sprint 34 terrain caches whole-map fields per target, which would grow with every candidate hex here)."""
    blocked = roadblocks if mode in ROADBLOCKED_MODES else frozenset()
    dist: Dict[int, float] = {start: 0.0}
    done: Set[int] = set()
    frontier = [(0.0, start)]
    while frontier:
        d, node = heapq.heappop(frontier)
        if node in done:
            continue
        done.add(node)
        for nxt, cost in terrain.costs.neighbours(mode, node).items():
            if nxt in done or nxt in blocked or F.hex_distance(start, nxt) > radius:
                continue
            candidate = d + cost
            if nxt not in dist or candidate < dist[nxt]:
                dist[nxt] = candidate
                heapq.heappush(frontier, (candidate, nxt))
    return dist


def safe_hex(world: World, unit: Unit, members: Sequence[C.Threat], tcfg: TacticalConfig,
             traffic: Optional[Traffic], terrain, allocator: Allocator) -> Optional[int]:
    """A fallback hex that breaks contact: within ``SAFE_RADIUS`` hexes of ``unit``, at least ``safe_margin`` hexes
    farther from every visible threat member than the unit is now, outside the zone of every objective, not a
    roadblock, with fewer than two own units planned to stand on it, reachable (bounded forward search) before the end;
    the nearest by free-flow time, then hex. (Getting beyond the threat's published range is rarely possible: tank
    weapons reach 18 to 20 hexes.)"""
    visible = [t for t in members if t.visible]
    mode = unit_mode(unit.type, unit.move_state)
    if not visible or terrain is None or mode is None:
        return None
    now = min(F.hex_distance(unit.hex, t.hex) for t in visible)
    zones: Set[int] = set()
    for o in world.objectives:
        zones.update(o.zone)
    costs = local_costs(terrain, mode, unit.hex, SAFE_RADIUS, world.roadblocks)
    options = []
    for h, cost in costs.items():
        if h == unit.hex or h in zones or h in world.roadblocks:
            continue
        if min(F.hex_distance(h, t.hex) for t in visible) < now + tcfg.safe_margin:
            continue
        if traffic is not None and traffic.stand(h) >= 2:
            continue
        eta = terrain.seconds(unit.basic_speed, cost)
        if eta is None or not allocator.feasible(world, eta):
            continue
        options.append((eta, h))
    return min(options)[1] if options else None


__all__ = ["assess", "filtered_threats", "is_static", "cheap_limit", "is_cheap", "safe_hex", "local_costs",
           "DELAY_ROLE_NOTE"]
