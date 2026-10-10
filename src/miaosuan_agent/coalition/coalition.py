"""Objective stances: how each objective is served this decision (``docs/SPRINT35_COALITION_AGENT.md`` section 7).

Sprint 34's allocator offered every objective a fixed set of slots and filled them unit by unit, so a contested
objective got one or two units at a time, held objectives kept one holder each, and the last holder of a threatened
objective could be sent elsewhere by a better-scoring slot. Sprint 35's post hoc reading of the 57 held-objective losses
(``evaluation/s35-coalition-agent/loss-episodes.json``): in 18 the last standing defenders were ordered away alive by
the allocation, in 38 they were destroyed, mostly one or two vehicles facing two to four arriving enemies, which the seat
had seen within eight hexes hundreds of steps earlier. An objective is lost only when no own ground unit is left in its
zone (occupation is not listed while an enemy ground unit is in the zone), so a defence needs survivors, not numbers
alone.

Each known enemy counts against one objective only (``capability.attribute``: the one its visible path ends at, else
the one it can reach first). Each decision every objective gets one stance, from that capability-weighted threat, the
power of the own units standing in its zone, and the free units that could arrive in time:

* held, no known threat: ``quiet`` - one holder place (Sprint 34's quiet hold); its standing units stay free;
* held, defenders at least ``defend_ratio`` x threat: ``secure`` - the strongest defenders reaching the requirement and
  the best holder are kept, the rest stay free;
* held, defenders plus reachable reinforcements at least ``commit_ratio`` x threat: ``defend`` - every standing
  defender kept, and just enough reinforcement places (strongest first) to reach ``defend_ratio`` x threat, each only
  for a free unit whose free-flow arrival is at most ``deadline_grace`` steps after the enemy's earliest optimistic
  arrival (Sprint 34's 57 losses came a median 41 steps after the first enemy ground unit entered the zone);
* held, not even that: ``delay`` - the best holder (infantry first, then lowest value) is kept to deny the zone; each
  other defender withdraws to the nearest held objective that is not in ``delay`` when at least
  ``withdraw_visible_share`` of the threat comes from enemies seen now and the unit is worth more than the holder;
  otherwise it is kept too;
* not held, no known threat: ``capture`` - Sprint 34's capture places;
* not held, threatened: ``coalition`` - places for the smallest group of free units (strongest first) reaching
  ``capture_ratio`` x threat, if one exists; otherwise ``skip``: no place, no unit is sent alone.

A threatened held objective (``secure`` or ``defend``) also offers ``reserve_places`` low-weight places (the mobile
reserve). A downgrade from ``defend`` or ``secure`` to ``delay`` waits ``stance_dwell`` steps after the stance was set;
every other change is immediate. Units kept or withdrawn are taken out of the free pool before the allocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from ..integrated.allocation import OWN, Allocator, Picture
from ..integrated.world import Unit, World
from . import capability as C
from .config import CoalitionConfig
from .memory import CoalitionMemory, Stance

QUIET, SECURE, DEFEND, DELAY, CAPTURE, COALITION, SKIP = "quiet", "secure", "defend", "delay", "capture", "coalition", "skip"
STANCES = (QUIET, SECURE, DEFEND, DELAY, CAPTURE, COALITION, SKIP)
HELD_STANCES = (QUIET, SECURE, DEFEND, DELAY)
DWELL_FROM = (SECURE, DEFEND)
INF = float("inf")


@dataclass(frozen=True)
class Assessment:
    hex: int
    value: float
    stance: str
    threat: float
    visible_threat: float
    enemy_eta: float                 # steps from now; inf when no threat
    defence: float                   # power of own units standing in (and, for coalitions, bound for) the zone
    requirement: float               # power wanted at the objective (0 when none)
    places: int                      # reinforcement or coalition places offered
    deadline: Optional[int]          # latest arrival step for a reinforcement place (None: the game's end)
    keep: Tuple[int, ...] = ()       # own units held in the zone (removed from the free pool)
    withdraw: Tuple[Tuple[int, int], ...] = ()   # (unit, destination objective hex)
    reserve: int = 0
    note: str = ""


def _reachable(allocator: Allocator, world: World, free: Sequence[Unit], target: int, within: float,
               exclude: FrozenSet[int]) -> List[Tuple[float, Unit, float]]:
    """(power, unit, eta) of free units able to arrive at ``target`` within ``within`` steps and before the end,
    strongest first."""
    out = []
    for unit in free:
        if unit.obj_id in exclude or not unit.mobile_ground:
            continue
        eta = allocator.eta(unit, target, world.roadblocks)
        if eta is None or eta > within or not allocator.feasible(world, eta):
            continue
        out.append((C.unit_power(unit), unit, eta))
    out.sort(key=lambda r: (-r[0], r[2], r[1].obj_id))
    return out


def _needed(available: Sequence[Tuple[float, Unit, float]], have: float, want: float) -> Tuple[int, float]:
    """The fewest units (in the given order) taking ``have`` to ``want``: (count, power reached, possibly short)."""
    total = have
    count = 0
    for power, _, _ in available:
        if total >= want:
            break
        total += power
        count += 1
    return count, total


def assess(world: World, memory: CoalitionMemory, allocator: Allocator, config: CoalitionConfig,
           pictures: Sequence[Picture], threat_list: Sequence[C.Threat], free: Sequence[Unit]) -> Tuple[Assessment, ...]:
    """One assessment per objective, in ``pictures`` order. Pure function of its inputs."""
    cfg = config
    zones = {o.hex: o.zone for o in world.objectives}
    free_ids = frozenset(u.obj_id for u in free)
    assigned = C.attribute(threat_list, [(p.hex, zones[p.hex]) for p in pictures], cfg)
    threat = {p.hex: C.zone_threat(assigned[p.hex]) for p in pictures}
    standing = {p.hex: C.defenders(world, zones[p.hex]) for p in pictures}
    # pass 0: every controllable unit standing in a threatened held zone is spoken for there
    spoken: Set[int] = set()
    for p in pictures:
        if p.status == OWN and threat[p.hex].power > 0:
            spoken.update(u.obj_id for u in standing[p.hex] if u.controllable)
    # pass 1: stances
    stance: Dict[int, str] = {}
    keep: Dict[int, Tuple[int, ...]] = {}
    places: Dict[int, int] = {}
    want: Dict[int, float] = {}
    defence: Dict[int, float] = {}
    notes: Dict[int, str] = {}
    committed: Set[int] = set(spoken)
    for p in pictures:
        zt = threat[p.hex]
        mine = sorted((u for u in standing[p.hex] if u.controllable), key=C.holder_rank)
        defence[p.hex] = C.total_power(standing[p.hex])
        if p.status == OWN:
            if zt.power <= 0:
                stance[p.hex], want[p.hex], notes[p.hex] = QUIET, 0.0, "held, no known threat"
                continue
            want[p.hex] = cfg.defend_ratio * zt.power
            arriving = [u for u in C.inbound(world, zones[p.hex])
                        if C.eta_or_none(allocator.mover_eta(u, world.roadblocks)) <= zt.eta]
            if arriving:
                defence[p.hex] = round(defence[p.hex] + C.total_power(arriving), 6)
            if defence[p.hex] >= want[p.hex]:
                stance[p.hex], notes[p.hex] = SECURE, "defenders reach the requirement"
                if cfg.retention and mine:
                    kept = [mine[0]]
                    reached = C.unit_power(mine[0]) + C.total_power(u for u in standing[p.hex] if not u.controllable)
                    for u in sorted(mine[1:], key=lambda u: (-C.unit_power(u), u.obj_id)):
                        if reached >= want[p.hex]:
                            break
                        kept.append(u)
                        reached += C.unit_power(u)
                    keep[p.hex] = tuple(sorted(u.obj_id for u in kept))
                continue
            reach = (_reachable(allocator, world, free, p.hex, zt.eta + cfg.deadline_grace, frozenset(committed))
                     if cfg.reinforcement else [])
            count, reached = _needed(reach, defence[p.hex], want[p.hex])
            commit = reached >= cfg.commit_ratio * zt.power
            chosen = DEFEND if commit else DELAY
            prior = memory.stance_of(p.hex)
            if chosen == DELAY and prior is not None and prior[1] in DWELL_FROM and world.step - prior[2] < cfg.stance_dwell:
                chosen = DEFEND
                notes[p.hex] = "delay pending: dwell after a defend or secure stance"
            else:
                notes[p.hex] = ("reinforcements reach the commit ratio" if commit
                                else "reinforcements cannot reach the commit ratio")
            stance[p.hex] = chosen
            if chosen == DEFEND:
                places[p.hex] = count
                committed.update(r[1].obj_id for r in reach[:count])
                if cfg.retention:
                    keep[p.hex] = tuple(sorted(u.obj_id for u in mine))
            continue
        if zt.power <= 0 or not cfg.coalition_capture:
            stance[p.hex], want[p.hex] = CAPTURE, 0.0
            notes[p.hex] = "no known threat" if zt.power <= 0 else "coalition capture disabled"
            continue
        want[p.hex] = cfg.capture_ratio * zt.power
        bound = C.total_power(C.inbound(world, zones[p.hex]))
        defence[p.hex] = round(defence[p.hex] + bound, 6)
        reach = _reachable(allocator, world, free, p.hex, float(world.remaining), frozenset(committed))
        count, reached = _needed(reach, defence[p.hex], want[p.hex])
        if reached >= want[p.hex]:
            stance[p.hex], places[p.hex] = COALITION, count
            committed.update(r[1].obj_id for r in reach[:count])
            notes[p.hex] = f"a coalition of {count} reaches the capture ratio"
        else:
            stance[p.hex], notes[p.hex] = SKIP, "no coalition reaches the capture ratio"
    # pass 2: delay holders and withdrawals, against the final stances
    held = [p.hex for p in pictures if p.status == OWN]
    withdraw: Dict[int, Tuple[Tuple[int, int], ...]] = {}
    for p in pictures:
        if stance[p.hex] != DELAY:
            continue
        zt = threat[p.hex]
        mine = sorted((u for u in standing[p.hex] if u.controllable), key=C.holder_rank)
        if not mine:
            keep[p.hex] = ()
            continue
        holder = mine[0]
        leaving: List[Tuple[int, int]] = []
        share = zt.visible_power / zt.power if zt.power > 0 else 0.0
        if cfg.withdrawal and share >= cfg.withdraw_visible_share:
            for u in mine[1:]:
                if u.value <= holder.value or u.obj_id not in free_ids:
                    continue
                dest = _withdrawal_destination(allocator, world, u, p.hex, held, stance)
                if dest is not None:
                    leaving.append((u.obj_id, dest))
        withdraw[p.hex] = tuple(sorted(leaving))
        gone = {w[0] for w in leaving}
        keep[p.hex] = tuple(sorted(u.obj_id for u in mine if u.obj_id not in gone)) if cfg.retention else ()
    out = []
    for p in pictures:
        zt = threat[p.hex]
        s = stance[p.hex]
        deadline = (world.step + int(zt.eta) + cfg.deadline_grace) if (s == DEFEND and zt.eta != INF) else None
        reserve = cfg.reserve_places if (cfg.reserve and s in (SECURE, DEFEND)) else 0
        out.append(Assessment(p.hex, p.value, s, zt.power, zt.visible_power, zt.eta, defence[p.hex], want.get(p.hex, 0.0),
                              places.get(p.hex, 0), deadline, keep=keep.get(p.hex, ()), withdraw=withdraw.get(p.hex, ()),
                              reserve=reserve, note=notes.get(p.hex, "")))
    return tuple(out)


def _withdrawal_destination(allocator: Allocator, world: World, unit: Unit, origin: int, held: Sequence[int],
                            stance: Mapping[int, str]) -> Optional[int]:
    """The nearest (free-flow) held objective other than ``origin`` whose stance is not ``delay``."""
    best = None
    for hex_ in held:
        if hex_ == origin or stance.get(hex_) == DELAY:
            continue
        eta = allocator.eta(unit, hex_, world.roadblocks)
        if eta is None or not allocator.feasible(world, eta):
            continue
        key = (eta, hex_)
        if best is None or key < best[0]:
            best = (key, hex_)
    return best[1] if best else None


def stances_for_memory(assessments: Sequence[Assessment], memory: CoalitionMemory, step: int) -> Tuple[Stance, ...]:
    """The stance records to keep: an unchanged stance keeps its ``since`` step."""
    out = []
    for a in assessments:
        prior = memory.stance_of(a.hex)
        since = prior[2] if prior is not None and prior[1] == a.stance else step
        out.append((a.hex, a.stance, since))
    return tuple(sorted(out))
