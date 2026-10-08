"""NON-EXECUTABLE analysis-side shadow of the T13 garrison rule (Sprint 25, ``docs/SPRINT25_T13_D1.md``).

OFFLINE ONLY. Not a policy: there is no agent class, it is not in ``decision.policy.POLICIES``, no run card may name
it, and nothing it returns reaches an engine. It filters an action list that ``baseline-v2`` has already produced for
one seat at one decision, so that the registered garrison rule is specified exactly, tested, and replayed on recorded
states.

Definitions (registration, sections 5 to 9):

* An **objective** is a ``cities`` entry of the seat's observation with a readable hex; the side **holds** it when its
  flag equals the side's colour.
* Its **denial zone** is the objective hex and its six neighbours: every hex ``h`` with
  ``evaluation.t7_visibility.hex_distance(h, objective) <= 1``.
* An **own ground unit** is a unit of the seat's own ``operators`` of type 1 or 2 with a readable hex (passengers are
  not operators). An **eligible defender** is an own ground unit that is not artillery (type 2, sub_type 3).
* A **qualifying threat** for an objective and a defender is a currently visible enemy operator of type 1 or 2 with a
  readable hex whose published direct-fire range against the defender's class is known
  (``evaluation.t7_candidates.weapon_range`` over its ``carry_weapon_ids``: the longest range of its weapons against
  personnel for a type 1 defender, against vehicles for a type 2 defender) and whose distance to the objective hex is at
  most that range plus ``THREAT_MARGIN`` (1) hex. An enemy without a published range for the class is not a threat to
  this rule (fail closed: no capability is invented).

**Trigger** (a ``baseline-v2`` MOVE at a play decision, stage 2), for the objectives in whose zone the mover stands,
checked in the order of :data:`TRIGGER_REASONS`: the mover is in the seat's own operators, is an eligible defender, has
a readable hex and stands in the zone of an objective the side holds; that zone holds exactly one own ground unit,
the mover (artillery counts as an occupant, so an artillery unit in the zone means the move does not empty it); the
MOVE's ``move_path`` is readable and has a hex outside the zone; the mover's observed ``move_path`` (its remaining
route under an earlier order) lies inside the zone, because withholding a new MOVE cannot stop an existing movement
(otherwise ``existing_path_exits``: outside this rule's actionable scope); ``baseline-v2`` gives the mover no embark or
disembark at this decision (transport commitment; ``baseline-v2`` issues neither in the recorded populations, so this
is a structural guard); a qualifying threat exists; the objective has no active hold and is not in its cooldown.

**Action change**: the triggering MOVE is withheld (dropped from the list). Nothing else: no replacement action, no
route change, no stop command, no reassignment, no change to any other action; the remaining actions keep their order.

**Hold episode** (per objective, at most one at a time, owned by one unit). It starts at the triggering decision with
``hold_start_step = cur_step``. At each later play decision, before any action is examined, an active episode is
released by the first of :data:`RELEASE_REASONS` that applies: the objective is no longer held; the defender is absent
from the own operators (destroyed, missing or no longer controllable); the defender is outside the zone; another own
ground unit is in the zone; no qualifying threat remains (threats measured for the defender's class); ``cur_step -
hold_start_step >= HOLD_LIMIT`` (300). While the episode is active every ``baseline-v2`` MOVE of the defender whose
route has a hex outside the zone is withheld (a repeat); a MOVE inside the zone, or with an unreadable route, passes. A
release puts the objective in a cooldown: no new episode starts on it while ``cur_step - release_step < COOLDOWN``
(300), so an expired hold cannot be restarted at once. Episodes do not depend on whether ``baseline-v2`` emits a MOVE.

**Overlapping zones**: a unit owns at most one episode. A MOVE of a unit that already owns an episode is judged by that
episode only. Otherwise the held objectives in whose zone the unit stands are taken in order of distance from the unit,
then objective hex; the first that passes every condition owns the new episode, and the others that also pass are
recorded as overlaps (no second withholding, no second episode).

Non-play decisions pass unchanged and leave the memory unchanged. A new game starts from an empty :class:`GarrisonMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..evaluation.t7_candidates import weapon_range
from ..evaluation.t7_visibility import hex_distance

SHADOW_ID = "t13-d1-garrison-shadow"
STATUS = "ANALYSIS SHADOW - NON-EXECUTABLE"
EXECUTABLE = False
MOVE = 1
TRANSPORT = (3, 4)
GROUND = (1, 2)
VEHICLE = 2
ARTILLERY_SUB = 3
PLAY_STAGE = 2
ZONE_RADIUS = 1
THREAT_MARGIN = 1
HOLD_LIMIT = 300
COOLDOWN = 300
HOLD, COOL = "hold", "cooldown"
#: Trigger checks, in evaluation order; ``eligible`` when every check passes.
TRIGGER_REASONS = ("eligible", "unit_absent", "not_ground", "artillery", "unreadable_unit_hex",
                   "not_in_a_held_zone", "zone_not_single", "unreadable_route", "route_stays_in_zone",
                   "existing_path_exits", "transport_committed", "no_qualifying_threat",
                   "objective_in_episode", "objective_in_cooldown")
#: Release reasons, first match.
RELEASE_REASONS = ("objective_not_held", "defender_absent", "defender_outside_zone", "backup_entered",
                   "threat_cleared", "hold_limit")


def hex_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def in_zone(h: Any, objective: Any) -> bool:
    a, b = hex_int(h), hex_int(objective)
    return a is not None and b is not None and hex_distance(a, b) <= ZONE_RADIUS


def is_ground(u: Optional[Mapping[str, Any]]) -> bool:
    return bool(u) and u.get("type") in GROUND


def is_eligible_defender(u: Optional[Mapping[str, Any]]) -> bool:
    return is_ground(u) and not (u.get("type") == VEHICLE and u.get("sub_type") == ARTILLERY_SUB)


def zone_occupants(own: Mapping[Any, Mapping[str, Any]], objective: Any) -> Tuple[Any, ...]:
    """Own ground units (artillery included) with a readable hex in the objective's zone, sorted by id."""
    return tuple(sorted((obj for obj, u in own.items() if is_ground(u) and in_zone(u.get("cur_hex"), objective)),
                        key=str))


def held_objectives(flags: Mapping[Any, Any], faction: int) -> Tuple[int, ...]:
    return tuple(sorted(c for c, flag in flags.items() if hex_int(c) is not None and flag == faction))


@dataclass(frozen=True)
class Threat:
    """A qualifying threat (private fields): the enemy, its hex, its published reach and its distance to the objective."""

    enemy: Any
    hex: int
    reach: int
    distance: int


def qualifying_threats(enemies: Iterable[Mapping[str, Any]], objective: int, defender_type: Any) -> Tuple[Threat, ...]:
    out = []
    for e in enemies:
        if not is_ground(e):
            continue
        h = hex_int(e.get("cur_hex"))
        reach = weapon_range(e.get("carry_weapon_ids") or (), defender_type)
        if h is None or reach is None:
            continue
        d = hex_distance(h, objective)
        if d <= reach + THREAT_MARGIN:
            out.append(Threat(e.get("obj_id"), h, reach, d))
    return tuple(sorted(out, key=lambda t: (t.distance, str(t.enemy))))


def route_exits(route: Any, objective: int) -> Optional[bool]:
    """Whether a route has a hex outside the zone; ``None`` when a hex is unreadable or the route is empty."""
    hexes = list(route or ())
    if not hexes or any(hex_int(h) is None for h in hexes):
        return None
    return any(not in_zone(h, objective) for h in hexes)


@dataclass(frozen=True)
class TriggerCheck:
    """The trigger for one MOVE: whether it holds, the reason (``eligible`` when it holds; otherwise the first failing
    check, and with several examined objectives the one whose checks went furthest in :data:`TRIGGER_REASONS`), the
    owning objective, the other passing objectives (overlaps), the reason per examined objective and the owner's
    threats."""

    eligible: bool
    reason: str
    objective: Optional[int] = None
    overlaps: Tuple[int, ...] = ()
    per_objective: Tuple[Tuple[int, str], ...] = ()
    threats: Tuple[Threat, ...] = ()


def objective_reason(own: Mapping[Any, Mapping[str, Any]], enemies: Sequence[Mapping[str, Any]], unit_id: Any,
                     unit: Mapping[str, Any], action: Mapping[str, Any], objective: int,
                     transport: bool, active: Mapping[int, Any], cooldown: Mapping[int, int]
                     ) -> Tuple[str, Tuple[Threat, ...]]:
    if zone_occupants(own, objective) != (unit_id,):
        return "zone_not_single", ()
    exits = route_exits(action.get("move_path"), objective)
    if exits is None:
        return "unreadable_route", ()
    if not exits:
        return "route_stays_in_zone", ()
    existing = list(unit.get("move_path") or ())
    if existing and route_exits(existing, objective) is not False:
        return "existing_path_exits", ()
    if transport:
        return "transport_committed", ()
    threats = qualifying_threats(enemies, objective, unit.get("type"))
    if not threats:
        return "no_qualifying_threat", ()
    if objective in active:
        return "objective_in_episode", threats
    if objective in cooldown:
        return "objective_in_cooldown", threats
    return "eligible", threats


def trigger(faction: int, own: Mapping[Any, Mapping[str, Any]], enemies: Sequence[Mapping[str, Any]],
            flags: Mapping[Any, Any], actions: Sequence[Mapping[str, Any]], action: Mapping[str, Any],
            active: Mapping[int, Any] = None, cooldown: Mapping[int, int] = None) -> TriggerCheck:
    """The registered trigger for one ``baseline-v2`` MOVE (stateless when ``active`` and ``cooldown`` are empty)."""
    active = active or {}
    cooldown = cooldown or {}
    unit_id = action.get("obj_id")
    unit = own.get(unit_id)
    if unit is None:
        return TriggerCheck(False, "unit_absent")
    if not is_ground(unit):
        return TriggerCheck(False, "not_ground")
    if not is_eligible_defender(unit):
        return TriggerCheck(False, "artillery")
    h = hex_int(unit.get("cur_hex"))
    if h is None:
        return TriggerCheck(False, "unreadable_unit_hex")
    zones = sorted((c for c in held_objectives(flags, faction) if in_zone(h, c)), key=lambda c: (hex_distance(h, c), c))
    if not zones:
        return TriggerCheck(False, "not_in_a_held_zone")
    transport = any(a.get("obj_id") == unit_id and a.get("type") in TRANSPORT for a in actions)
    per: List[Tuple[int, str]] = []
    threats_by: Dict[int, Tuple[Threat, ...]] = {}
    for c in zones:
        reason, threats = objective_reason(own, enemies, unit_id, unit, action, c, transport, active, cooldown)
        per.append((c, reason))
        threats_by[c] = threats
    passing = [c for c, r in per if r == "eligible"]
    if passing:
        return TriggerCheck(True, "eligible", passing[0], tuple(passing[1:]), tuple(per), threats_by[passing[0]])
    order = {r: i for i, r in enumerate(TRIGGER_REASONS)}
    reason = max((r for _, r in per), key=lambda r: order[r])
    return TriggerCheck(False, reason, None, (), tuple(per))


def release_reason(faction: int, own: Mapping[Any, Mapping[str, Any]], enemies: Sequence[Mapping[str, Any]],
                   flags: Mapping[Any, Any], objective: int, unit_id: Any, start: int, cur_step: int) -> Optional[str]:
    if flags.get(objective) != faction:
        return "objective_not_held"
    unit = own.get(unit_id)
    if unit is None:
        return "defender_absent"
    if not in_zone(unit.get("cur_hex"), objective):
        return "defender_outside_zone"
    if zone_occupants(own, objective) != (unit_id,):
        return "backup_entered"
    if not qualifying_threats(enemies, objective, unit.get("type")):
        return "threat_cleared"
    if cur_step - start >= HOLD_LIMIT:
        return "hold_limit"
    return None


@dataclass(frozen=True)
class GarrisonMemory:
    """Active holds ``(objective, unit, hold_start_step)`` and cooldowns ``(objective, release_step)``, sorted."""

    holds: Tuple[Tuple[int, Any, int], ...] = ()
    cooldowns: Tuple[Tuple[int, int], ...] = ()


@dataclass(frozen=True)
class GarrisonEvent:
    """``start``, ``repeat``, ``release`` (with ``reason``), ``overlap`` or ``pass_in_hold`` (a MOVE of a held unit
    that stays in the zone or has an unreadable route)."""

    kind: str
    objective: int
    unit: Any
    step: int
    index: Optional[int] = None
    reason: Optional[str] = None
    hold_start: Optional[int] = None


@dataclass(frozen=True)
class GarrisonResult:
    actions: Tuple[Mapping[str, Any], ...]
    withheld: Tuple[int, ...]
    events: Tuple[GarrisonEvent, ...]
    checks: Tuple[Tuple[int, Any, TriggerCheck], ...]
    memory: GarrisonMemory


def decide(faction: int, cur_step: int, stage: Any, own: Mapping[Any, Mapping[str, Any]],
           enemies: Iterable[Mapping[str, Any]], flags: Mapping[Any, Any], actions: Sequence[Mapping[str, Any]],
           memory: GarrisonMemory) -> GarrisonResult:
    """One decision of the shadow: the candidate action list, the withheld indices, the events, the trigger check of
    every MOVE not under an active hold, and the new memory. Deterministic; inputs are not modified."""
    actions = [dict(a) for a in actions]
    if stage != PLAY_STAGE:
        return GarrisonResult(tuple(actions), (), (), (), memory)
    enemies = list(enemies)
    holds: Dict[int, Tuple[Any, int]] = {c: (u, s) for c, u, s in memory.holds}
    cooldown: Dict[int, int] = {c: s for c, s in memory.cooldowns if cur_step - s < COOLDOWN}
    events: List[GarrisonEvent] = []
    for c in sorted(holds):
        unit_id, start = holds[c]
        reason = release_reason(faction, own, enemies, flags, c, unit_id, start, cur_step)
        if reason is not None:
            events.append(GarrisonEvent("release", c, unit_id, cur_step, reason=reason, hold_start=start))
            del holds[c]
            cooldown[c] = cur_step
    withheld: List[int] = []
    checks: List[Tuple[int, Any, TriggerCheck]] = []
    for i, action in enumerate(actions):
        if action.get("type") != MOVE:
            continue
        unit_id = action.get("obj_id")
        owned = [c for c, (u, _) in holds.items() if u == unit_id]
        if owned:
            c = owned[0]
            exits = route_exits(action.get("move_path"), c)
            if exits:
                withheld.append(i)
                events.append(GarrisonEvent("repeat", c, unit_id, cur_step, index=i, hold_start=holds[c][1]))
            else:
                events.append(GarrisonEvent("pass_in_hold", c, unit_id, cur_step, index=i, hold_start=holds[c][1]))
            continue
        check = trigger(faction, own, enemies, flags, actions, action, holds, cooldown)
        checks.append((i, unit_id, check))
        if check.eligible:
            holds[check.objective] = (unit_id, cur_step)
            withheld.append(i)
            events.append(GarrisonEvent("start", check.objective, unit_id, cur_step, index=i, hold_start=cur_step))
            for c in check.overlaps:
                events.append(GarrisonEvent("overlap", c, unit_id, cur_step, index=i))
    kept = set(withheld)
    out = tuple(a for i, a in enumerate(actions) if i not in kept)
    new = GarrisonMemory(tuple(sorted((c, u, s) for c, (u, s) in holds.items())),
                         tuple(sorted(cooldown.items())))
    return GarrisonResult(out, tuple(withheld), tuple(events), tuple(checks), new)
