"""NON-EXECUTABLE analysis-side shadow of the T6-S stacked-column stagger rule (Sprint 26, ``docs/SPRINT26_T6S_SHADOW.md``).

OFFLINE ONLY. Not a policy: there is no agent class, it is not in ``decision.policy.POLICIES``, no run card may name
it, and nothing it returns reaches an engine. It filters an action list that ``baseline-v2`` has already produced for
one seat at one decision, so that the registered stagger rule is specified exactly, tested, and replayed on recorded
states.

Definitions (registration, sections 5 to 9):

* An **own ground unit** is a unit of the seat's own ``operators`` of type 1 or 2 (artillery included) with a readable
  hex; passengers are not operators.
* A **route** is the ``move_path`` of a ``baseline-v2`` MOVE (action type 1): the hexes after the unit's current hex,
  up to the destination; its **first hex** is ``route[0]``.
* **Threat exposure** of a MOVE is Sprint 18's threat-exposed order predicate (``evaluation.s18_census.
  threat_exposed``), restated here so that this module imports no analysis module: a currently visible enemy operator of
  any class with a readable hex and a published direct-fire range against the mover's type (``evaluation.
  t7_candidates.weapon_range`` over its ``carry_weapon_ids``) whose distance (``evaluation.t7_visibility.hex_distance``)
  to the mover's current hex, or to one of the first ``ROUTE_PREFIX`` (5) route hexes, is at most that range.
* **Hex time** and **free-flow arrival** are the project's free-flow relation (``experiments.t9_batch.path_times``,
  ``720 / basic_speed * cost`` steps per hex, rounded, per movement mode of the unit's type and ``move_state``, costs of
  the setup cost graph): a member's hex time is the first entry of its route's per-hex times (from its current hex to
  the route's first hex), its free-flow arrival the sum over the route.

**Mover eligibility** (each ``baseline-v2`` MOVE at a play decision, stage 2; the first failing check of
:data:`MOVER_REASONS` is reported): the unit is in the own operators, is a ground unit, has a readable hex; it has exactly
one MOVE in this decision's list; it is not already moving (empty observed ``move_path`` and no positive ``speed``:
withholding a new MOVE cannot stop an existing movement); ``baseline-v2`` gives it no embark or disembark at this
decision; action type 1 is listed for it in this decision's ``valid_actions``; the route is non-empty and every hex is
readable; its per-hex free-flow times are readable; it is not a member of an active episode; it is re-armed (below).

**Trigger** (registration, section 5): the eligible movers are grouped by (current hex, route first hex); a group of at
least ``MIN_GROUP`` (2) movers triggers when at least one member's MOVE is threat-exposed. Groups are examined in order
of (current hex, first hex).

**Leader and chain** (section 7): the members are ordered by (free-flow arrival, route cost, route length, unit id);
the first is the **leader**. The chain order is the release order.

**Action change** (section 5): at the triggering decision the leader's MOVE passes and every other member's MOVE is
withheld (dropped from the list). While a member is **pending**, every ``baseline-v2`` MOVE of it is withheld (a
repeat). Nothing else: no replacement action, no route or destination change, no stop command, no new action type, no
change to any other action; the remaining actions keep their order.

**Release rule** (section 6, the frozen reading of "one hex time later" and "until the released unit has left the shared
hex"): an episode keeps a **reference** unit, initially the leader, with the step at which its MOVE passed and its hex
time. At each later play decision, before any action is examined, the head of the pending queue is released when the
reference is absent from the own operators or is observed on a readable hex other than the shared start hex (under the
documented movement model a unit's ``cur_hex`` changes when it enters the next hex, one hex time after its order when
unimpeded). A released member's ``baseline-v2`` MOVE at that decision, if any, passes and the member becomes the
reference (its step is that decision's step, its hex time its own); a member released without a ``baseline-v2`` MOVE
is recorded as such and does not become the reference, and the next head is then examined against the unchanged
reference. A pending head that is absent from the own operators, or observed on another readable hex, leaves the queue
(``follower_absent``, ``follower_left``). **Wait bound**: when the reference has not left by ``cur_step - ref_step >
STALL_FACTOR * ref_hex_time + STALL_SLACK`` (the PS-1 stall definition, ``s > 2 * tau + 10``), every pending member is
released at once (``timeout``), so the rule then falls back to ``baseline-v2``. An episode **completes** when its
queue is empty.

**One episode per unit** (section 8): a unit belongs to at most one active episode; when an episode completes, each of
its members is **spent** at the shared start hex and cannot join a new episode until it has been observed on a readable
hex other than that one (re-armed). A repeated listing of the same unresolved co-departure therefore never starts a new
episode.

Non-play decisions pass unchanged and leave the memory unchanged. A new game starts from an empty :class:`StaggerMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..evaluation.t7_candidates import weapon_range
from ..evaluation.t7_visibility import hex_distance

SHADOW_ID = "t6s-column-stagger-shadow"
STATUS = "ANALYSIS SHADOW - NON-EXECUTABLE"
EXECUTABLE = False
MOVE = 1
TRANSPORT = (3, 4)
GROUND = (1, 2)
PLAY_STAGE = 2
ROUTE_PREFIX = 5
MIN_GROUP = 2
STALL_FACTOR = 2
STALL_SLACK = 10
#: Mover checks, in evaluation order; ``eligible`` when every check passes.
MOVER_REASONS = ("eligible", "unit_absent", "not_ground", "unreadable_unit_hex", "several_moves", "already_moving",
                 "transport_committed", "move_not_listed", "unreadable_route", "unreadable_travel",
                 "in_active_episode", "not_rearmed")
#: Group outcomes for eligible movers.
GROUP_REASONS = ("triggered", "single_mover", "no_qualifying_threat")
#: Release and queue events, and the reason an episode still open at the last decision is closed with by the analysis.
RELEASE_REASONS = ("reference_left", "reference_absent", "timeout")
QUEUE_REASONS = ("follower_absent", "follower_left")
OPEN_AT_END = "open_at_end"

Travel = Callable[[Mapping[str, Any], Sequence[Any]], Optional[Tuple[Tuple[int, ...], float]]]


def hex_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def as_int(value: Any) -> Optional[int]:
    """Sprint 18's reading of an integer field (``s18_census.as_int``)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def is_ground(u: Optional[Mapping[str, Any]]) -> bool:
    return bool(u) and u.get("type") in GROUND


def threat_exposed(unit: Optional[Mapping[str, Any]], route: Sequence[Any],
                   enemies: Iterable[Mapping[str, Any]]) -> Optional[bool]:
    """Sprint 18's threat-exposed order predicate, restated: ``True`` when a visible enemy's published range against the
    mover's type covers its hex or one of the first ``ROUTE_PREFIX`` route hexes; ``None`` when the mover is unreadable
    or every visible enemy is unreadable."""
    enemies = list(enemies)
    if unit is None or as_int(unit.get("cur_hex")) is None:
        return None
    hexes = [unit["cur_hex"]] + [h for h in list(route or ())[:ROUTE_PREFIX] if as_int(h) is not None]
    readable = False
    for enemy in enemies:
        reach = weapon_range(enemy.get("carry_weapon_ids") or (), unit.get("type"))
        if reach is None or as_int(enemy.get("cur_hex")) is None:
            continue
        readable = True
        if any(hex_distance(enemy["cur_hex"], h) <= reach for h in hexes):
            return True
    return False if readable or not enemies else None


def router_travel(router: Any) -> Travel:
    """The free-flow relation over a router's cost graph (``experiments.t9_batch.path_times``): per-hex times and route
    cost of a unit's route from its current hex, or ``None`` when any part is unreadable."""
    from .t9_batch import path_times

    def travel(unit: Mapping[str, Any], route: Sequence[Any]) -> Optional[Tuple[Tuple[int, ...], float]]:
        times, cost = path_times(router, unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                                 unit.get("cur_hex"), list(route))
        if times is None or not times:
            return None
        return tuple(times), cost

    return travel


def leader_key(member: "Member") -> Tuple[Any, ...]:
    """Chain order: free-flow arrival, route cost, route length, unit id."""
    return (member.arrival, member.cost, len(member.route), member.unit)


@dataclass(frozen=True)
class Member:
    """An eligible mover (private fields): unit, action index, route, hex time, free-flow arrival, cost, exposure."""

    unit: Any
    index: int
    route: Tuple[int, ...]
    hex_time: int
    arrival: int
    cost: float
    exposed: bool


@dataclass(frozen=True)
class MoverCheck:
    eligible: bool
    reason: str
    member: Optional[Member] = None


@dataclass(frozen=True)
class Episode:
    """An active episode: identifier, shared start hex, shared first hex, start step, chain (unit ids, release order),
    each member's hex time, pending followers, the reference unit, its release step and hex time."""

    eid: int
    origin: int
    first_hex: int
    start_step: int
    chain: Tuple[Any, ...]
    hex_times: Tuple[int, ...]
    pending: Tuple[Any, ...]
    ref: Any
    ref_step: int
    ref_hex_time: int

    def hex_time_of(self, unit: Any) -> int:
        return self.hex_times[self.chain.index(unit)]


@dataclass(frozen=True)
class StaggerMemory:
    """Active episodes (by identifier), spent units ``(unit, start hex)`` sorted by unit, and the next identifier."""

    episodes: Tuple[Episode, ...] = ()
    spent: Tuple[Tuple[Any, int], ...] = ()
    next_eid: int = 0


@dataclass(frozen=True)
class StaggerEvent:
    """``start`` (with the episode), ``withhold`` (a follower withheld at the start), ``repeat``, ``release`` (with
    ``reason`` and whether ``baseline-v2`` gave the member a MOVE that passed), ``queue`` (a pending member leaving the
    queue, with ``reason``), ``complete``, ``rearm``."""

    kind: str
    eid: Optional[int]
    unit: Any
    step: int
    index: Optional[int] = None
    reason: Optional[str] = None
    moved: Optional[bool] = None
    episode: Optional[Episode] = None


@dataclass(frozen=True)
class StaggerResult:
    actions: Tuple[Mapping[str, Any], ...]
    withheld: Tuple[int, ...]
    events: Tuple[StaggerEvent, ...]
    checks: Tuple[Tuple[int, Any, MoverCheck], ...]
    groups: Tuple[Tuple[int, int, Tuple[Any, ...], str], ...]
    memory: StaggerMemory


def mover_check(unit_id: Any, index: int, action: Mapping[str, Any], own: Mapping[Any, Mapping[str, Any]],
                enemies: Sequence[Mapping[str, Any]], valid: Mapping[Any, Mapping[Any, Any]],
                actions: Sequence[Mapping[str, Any]], travel: Travel, busy: Iterable[Any],
                spent: Mapping[Any, int]) -> MoverCheck:
    """Eligibility of one ``baseline-v2`` MOVE (the checks of :data:`MOVER_REASONS`, first failure reported)."""
    unit = own.get(unit_id)
    if unit is None:
        return MoverCheck(False, "unit_absent")
    if not is_ground(unit):
        return MoverCheck(False, "not_ground")
    here = hex_int(unit.get("cur_hex"))
    if here is None:
        return MoverCheck(False, "unreadable_unit_hex")
    if sum(1 for a in actions if a.get("type") == MOVE and a.get("obj_id") == unit_id) != 1:
        return MoverCheck(False, "several_moves")
    speed = unit.get("speed")
    if unit.get("move_path") or (isinstance(speed, (int, float)) and not isinstance(speed, bool) and speed > 0):
        return MoverCheck(False, "already_moving")
    if any(a.get("obj_id") == unit_id and a.get("type") in TRANSPORT for a in actions):
        return MoverCheck(False, "transport_committed")
    if MOVE not in (valid.get(unit_id) or {}):
        return MoverCheck(False, "move_not_listed")
    route = tuple(action.get("move_path") or ())
    if not route or any(hex_int(h) is None for h in route):
        return MoverCheck(False, "unreadable_route")
    timing = travel(unit, route)
    if timing is None:
        return MoverCheck(False, "unreadable_travel")
    times, cost = timing
    if unit_id in set(busy):
        return MoverCheck(False, "in_active_episode")
    if unit_id in spent:
        return MoverCheck(False, "not_rearmed")
    exposed = bool(threat_exposed(unit, route, enemies))
    return MoverCheck(True, "eligible", Member(unit_id, index, route, int(times[0]), int(sum(times)), float(cost),
                                               exposed))


def stalled(episode: Episode, cur_step: int) -> bool:
    return cur_step - episode.ref_step > STALL_FACTOR * episode.ref_hex_time + STALL_SLACK


def decide(cur_step: int, stage: Any, own: Mapping[Any, Mapping[str, Any]], enemies: Iterable[Mapping[str, Any]],
           valid: Mapping[Any, Mapping[Any, Any]], actions: Sequence[Mapping[str, Any]], memory: StaggerMemory,
           travel: Travel) -> StaggerResult:
    """One decision of the shadow: the candidate action list, the withheld indices, the events, the eligibility check of
    every MOVE, the group outcomes ``(start hex, first hex, members, outcome)`` and the new memory. Deterministic;
    inputs are not modified."""
    actions = [dict(a) for a in actions]
    if stage != PLAY_STAGE:
        return StaggerResult(tuple(actions), (), (), (), (), memory)
    enemies = list(enemies)
    events: List[StaggerEvent] = []
    spent: Dict[Any, int] = dict(memory.spent)
    for unit_id in sorted(spent, key=str):
        h = hex_int((own.get(unit_id) or {}).get("cur_hex"))
        if h is not None and h != spent[unit_id]:
            events.append(StaggerEvent("rearm", None, unit_id, cur_step))
            del spent[unit_id]
    moves_of: Dict[Any, List[int]] = {}
    for i, a in enumerate(actions):
        if a.get("type") == MOVE:
            moves_of.setdefault(a.get("obj_id"), []).append(i)
    active: List[Episode] = []
    for ep in sorted(memory.episodes, key=lambda e: e.eid):
        pending = list(ep.pending)
        while pending:
            head = pending[0]
            ref_unit = own.get(ep.ref)
            ref_hex = hex_int((ref_unit or {}).get("cur_hex"))
            if ref_unit is None or (ref_hex is not None and ref_hex != ep.origin):
                pending.pop(0)
                moved = bool(moves_of.get(head))
                events.append(StaggerEvent("release", ep.eid, head, cur_step,
                                           reason="reference_absent" if ref_unit is None else "reference_left",
                                           moved=moved))
                if moved:
                    ep = replace(ep, ref=head, ref_step=cur_step, ref_hex_time=ep.hex_time_of(head))
                continue
            head_unit = own.get(head)
            head_hex = hex_int((head_unit or {}).get("cur_hex"))
            if head_unit is None or (head_hex is not None and head_hex != ep.origin):
                pending.pop(0)
                events.append(StaggerEvent("queue", ep.eid, head, cur_step,
                                           reason="follower_absent" if head_unit is None else "follower_left"))
                continue
            if stalled(ep, cur_step):
                for unit_id in pending:
                    events.append(StaggerEvent("release", ep.eid, unit_id, cur_step, reason="timeout",
                                               moved=bool(moves_of.get(unit_id))))
                pending = []
            break
        ep = replace(ep, pending=tuple(pending))
        if pending:
            active.append(ep)
        else:
            events.append(StaggerEvent("complete", ep.eid, ep.chain[0], cur_step))
            for unit_id in ep.chain:
                spent[unit_id] = ep.origin
    withheld: List[int] = []
    pending_of = {u: ep.eid for ep in active for u in ep.pending}
    for unit_id, idx in sorted(moves_of.items(), key=lambda kv: kv[1][0]):
        if unit_id in pending_of:
            for i in idx:
                withheld.append(i)
                events.append(StaggerEvent("repeat", pending_of[unit_id], unit_id, cur_step, index=i))
    busy = {u for ep in active for u in ep.chain}
    checks: List[Tuple[int, Any, MoverCheck]] = []
    eligible: Dict[Tuple[int, int], List[Member]] = {}
    for i, a in enumerate(actions):
        if a.get("type") != MOVE or a.get("obj_id") in pending_of:
            continue
        check = mover_check(a.get("obj_id"), i, a, own, enemies, valid, actions, travel, busy, spent)
        checks.append((i, a.get("obj_id"), check))
        if check.eligible:
            m = check.member
            eligible.setdefault((own[m.unit]["cur_hex"], m.route[0]), []).append(m)
    groups: List[Tuple[int, int, Tuple[Any, ...], str]] = []
    next_eid = memory.next_eid
    for (origin, first), members in sorted(eligible.items()):
        units = tuple(sorted((m.unit for m in members), key=str))
        if len(members) < MIN_GROUP:
            groups.append((origin, first, units, "single_mover"))
            continue
        if not any(m.exposed for m in members):
            groups.append((origin, first, units, "no_qualifying_threat"))
            continue
        groups.append((origin, first, units, "triggered"))
        chain = sorted(members, key=leader_key)
        ep = Episode(next_eid, origin, first, cur_step, tuple(m.unit for m in chain),
                     tuple(m.hex_time for m in chain), tuple(m.unit for m in chain[1:]), chain[0].unit, cur_step,
                     chain[0].hex_time)
        next_eid += 1
        active.append(ep)
        events.append(StaggerEvent("start", ep.eid, chain[0].unit, cur_step, index=chain[0].index, episode=ep))
        for m in chain[1:]:
            withheld.append(m.index)
            events.append(StaggerEvent("withhold", ep.eid, m.unit, cur_step, index=m.index))
    kept = set(withheld)
    out = tuple(a for i, a in enumerate(actions) if i not in kept)
    new = StaggerMemory(tuple(sorted(active, key=lambda e: e.eid)),
                        tuple(sorted(spent.items(), key=lambda kv: str(kv[0]))), next_eid)
    return StaggerResult(out, tuple(sorted(withheld)), tuple(events), tuple(checks), tuple(groups), new)
