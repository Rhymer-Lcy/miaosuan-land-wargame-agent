"""EXPLORATORY mechanism-probe candidate ``t6s-column-stagger-p1`` (Sprint 27, ``docs/SPRINT27_T6S_PROBE.md``).

Exploratory track: not a baseline, not eligible for promotion and never packaged. Its only authorized use is the
owner-approved two-session T6-S mechanism probe of Sprint 27 (card ``s27-t6s-probe-1``, sessions 2797 and 2798 at
most); any other engine use needs new owner approval.

``baseline-v2`` decides first, on the seat's own current observation and memory, unchanged
(:mod:`.exploratory_addon`). The add-on then applies Sprint 26's frozen T6-S stacked-column stagger rule
(``docs/SPRINT26_T6S_SHADOW.md``, sections 5 to 9) to that decision, and nothing else:

* **the rule is Sprint 26's, restated verbatim.** Sprint 26's analysis shadow is non-executable and its own frozen test
  (pinned by Sprint 26's mutation record) forbids any further file from naming it, so this module cannot import it.
  Everything from the documented codes to the end of :func:`decide` below is a mechanical copy of the frozen shadow's
  text (the shadow's identity constants excepted), and the shadow's three helper imports are the same functions
  imported unchanged: the published weapon ranges (``evaluation.t7_candidates.weapon_range``), the hex distance
  (``evaluation.t7_visibility.hex_distance``) and the free-flow relation (``experiments.t9_batch.path_times``). Sprint
  27's rehearsal checks the copy against the frozen shadow, through Sprint 26's own analysis, at every recorded HH and
  H0 decision;
* **the only action edit** is the rule's: at an episode's start the leader's ``baseline-v2`` MOVE passes and the
  followers' MOVEs are withheld; while a follower is pending every ``baseline-v2`` MOVE of it is withheld; nothing is
  added, replaced, reordered or constructed. A released follower moves only if ``baseline-v2`` emits a MOVE for it on
  that decision's own observation;
* **the inputs** are the seat's own observation, read exactly as Sprint 18's census frames read it
  (:func:`seat_inputs`: the own operators of the seat's colour, every other operator as a visible enemy, the listed
  actions), the setup cost data (the free-flow relation over :class:`decision.routing.Router`) and the rule's memory;
* **the memory** is the rule's episode state (:class:`StaggerMemory`) encoded as integer pairs (position, value) in
  ``AddonMemory.addon`` (:func:`encode`, :func:`decode`); empty at the start of every game (``AddonAgent.setup`` and
  ``reset``). Memory that cannot be decoded raises, so the add-on wrapper plays ``baseline-v2``'s decision and records
  the error (a structural stop of the probe), never a re-interpretation.

Nothing reads another seat's view, the all-seeing state, the clock or randomness.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..decision.routing import Router
from ..evaluation.t7_candidates import weapon_range
from ..evaluation.t7_visibility import hex_distance
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult

CANDIDATE_ID = "t6s-column-stagger-p1"
ADDON_NAME = "t6s_column_stagger_p1"
STATUS = "EXPLORATORY MECHANISM-PROBE CANDIDATE - NOT ELIGIBLE FOR PROMOTION"
#: The marker lines that delimit the verbatim copy of the frozen rule (checked by the Sprint 27 rehearsal).
COPY_BEGIN = "# ---- BEGIN verbatim copy of Sprint 26's frozen T6-S rule ----"
COPY_END = "# ---- END verbatim copy of Sprint 26's frozen T6-S rule ----"

# ---- BEGIN verbatim copy of Sprint 26's frozen T6-S rule ----
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
# ---- END verbatim copy of Sprint 26's frozen T6-S rule ----


# ------------------------------------------------------------------------------------------------
# the seat's own observation, read as Sprint 18's census frames read it (``evaluation.s18_census``)

#: Unit fields kept for the rule (Sprint 18's ``UNIT_FIELDS``; everything else of the observation is dropped).
UNIT_FIELDS = ("obj_id", "type", "sub_type", "color", "cur_hex", "move_path", "speed", "stop", "keep",
               "keep_remain_time", "stack", "close_combat", "blood", "max_blood", "observe_distance",
               "carry_weapon_ids", "guide_ability", "on_board", "basic_speed", "move_state", "value")


def unit_view(u: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: u.get(k) for k in UNIT_FIELDS}
    out["move_path"] = tuple(u.get("move_path") or ())
    out["carry_weapon_ids"] = tuple(u.get("carry_weapon_ids") or ())
    return out


def listings(raw: Mapping[str, Any]) -> Dict[int, Dict[int, Any]]:
    out: Dict[int, Dict[int, Any]] = {}
    for obj, actions in (raw.get("valid_actions") or {}).items():
        oid = as_int(obj)
        if oid is None or not isinstance(actions, Mapping):
            continue
        out[oid] = {t: options for t, options in ((as_int(k), v) for k, v in actions.items()) if t is not None}
    return out


def seat_inputs(raw: Mapping[str, Any], faction: int) -> Tuple[Any, Any, Dict[Any, Dict[str, Any]],
                                                              Dict[Any, Dict[str, Any]], Dict[int, Dict[int, Any]]]:
    """``(cur_step, stage, own, enemies, valid)`` of one seat observation: every operator of the seat's colour is own,
    every other operator in the seat's view is a visible enemy (Sprint 18's ``frame_from_raw``)."""
    time_info = raw.get("time") or {}
    own: Dict[Any, Dict[str, Any]] = {}
    enemies: Dict[Any, Dict[str, Any]] = {}
    for u in raw.get("operators") or ():
        if not isinstance(u, Mapping) or as_int(u.get("obj_id")) is None:
            continue
        (own if u.get("color") == faction else enemies)[u["obj_id"]] = unit_view(u)
    return time_info.get("cur_step"), time_info.get("stage"), own, enemies, listings(raw)


# ------------------------------------------------------------------------------------------------
# memory: the rule's episode state as integer pairs (position, value)


def _int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"memory value {value!r} is not an integer")
    return value


def encode(memory: StaggerMemory) -> Tuple[Tuple[int, int], ...]:
    """The flat integer form: next identifier; spent count, then (unit, hex) pairs; episode count, then per episode its
    identifier, start hex, first hex, start step, chain length, chain, hex times, pending count, pending, reference,
    reference step, reference hex time. The empty memory is ``()``."""
    if memory == StaggerMemory():
        return ()
    values: List[int] = [_int(memory.next_eid), len(memory.spent)]
    for unit_id, origin in memory.spent:
        values += [_int(unit_id), _int(origin)]
    values.append(len(memory.episodes))
    for ep in memory.episodes:
        values += [_int(ep.eid), _int(ep.origin), _int(ep.first_hex), _int(ep.start_step), len(ep.chain)]
        values += [_int(u) for u in ep.chain] + [_int(t) for t in ep.hex_times]
        values += [len(ep.pending)] + [_int(u) for u in ep.pending]
        values += [_int(ep.ref), _int(ep.ref_step), _int(ep.ref_hex_time)]
    return tuple((i, v) for i, v in enumerate(values))


def decode(pairs: Sequence[Sequence[int]]) -> StaggerMemory:
    """The inverse of :func:`encode`; ``()`` is the empty memory. Raises ``ValueError`` on anything else."""
    if not pairs:
        return StaggerMemory()
    values: List[int] = []
    for position, pair in enumerate(pairs):
        if len(pair) != 2 or _int(pair[0]) != position:
            raise ValueError("memory positions are not consecutive")
        values.append(_int(pair[1]))
    cursor = 0

    def take(n: int = 1) -> List[int]:
        nonlocal cursor
        if n < 0 or cursor + n > len(values):
            raise ValueError("memory ends early")
        part = values[cursor:cursor + n]
        cursor += n
        return part

    next_eid, n_spent = take(2)
    spent = []
    for _ in range(n_spent):
        unit_id, origin = take(2)
        spent.append((unit_id, origin))
    (n_episodes,) = take()
    episodes = []
    for _ in range(n_episodes):
        eid, origin, first_hex, start_step, n_chain = take(5)
        chain = tuple(take(n_chain))
        hex_times = tuple(take(n_chain))
        (n_pending,) = take()
        pending = tuple(take(n_pending))
        ref, ref_step, ref_hex_time = take(3)
        if n_chain < 2 or not set(pending) <= set(chain):
            raise ValueError("an episode in memory is malformed")
        episodes.append(Episode(eid, origin, first_hex, start_step, chain, hex_times, pending, ref, ref_step,
                                ref_hex_time))
    if cursor != len(values):
        raise ValueError("memory carries trailing values")
    memory = StaggerMemory(tuple(episodes), tuple(spent), next_eid)
    if encode(memory) != tuple((i, v) for i, v in enumerate(values)):
        raise ValueError("memory does not round-trip")
    return memory


# ------------------------------------------------------------------------------------------------
# the add-on


def change_records(result: StaggerResult) -> Tuple[Dict[str, Any], ...]:
    """One change record per rule event, in event order (private: unit ids and hexes)."""
    out = []
    for e in result.events:
        record: Dict[str, Any] = {"kind": e.kind, "eid": e.eid, "obj_id": e.unit, "step": e.step}
        if e.index is not None:
            record["index"] = e.index
        if e.reason is not None:
            record["reason"] = e.reason
        if e.moved is not None:
            record["moved"] = e.moved
        if e.episode is not None:
            record.update(origin=e.episode.origin, first_hex=e.episode.first_hex, chain=list(e.episode.chain),
                          hex_times=list(e.episode.hex_times))
        out.append(record)
    return tuple(out)


def skip_counts(result: StaggerResult) -> Tuple[Tuple[str, int], ...]:
    """Counts of the mover checks and group outcomes of the decision."""
    counts: collections.Counter = collections.Counter()
    for _, _, check in result.checks:
        counts[f"mover {check.reason}"] += 1
    for _, _, _, outcome in result.groups:
        counts[f"group {outcome}"] += 1
    return tuple(sorted(counts.items()))


def apply_rule(raw: Mapping[str, Any], faction: int, base_actions: Sequence[Mapping[str, Any]],
               memory: Sequence[Sequence[int]], travel: Travel) -> Tuple[StaggerResult, Tuple[Tuple[int, int], ...]]:
    """One decision of the candidate's rule on the seat's own observation: the rule's result and the next memory."""
    cur_step, stage, own, enemies, valid = seat_inputs(raw, faction)
    result = decide(cur_step, stage, own, enemies.values(), valid, base_actions, decode(memory), travel)
    return result, encode(result.memory)


class StaggerAddon(Addon):
    name = ADDON_NAME

    def __init__(self, costs: Any, baseline: Any) -> None:
        super().__init__(costs, baseline)
        self.travel = router_travel(Router(costs)) if costs is not None else None

    def apply(self, observation: Any, seat: int, faction: int, base: Any,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        if self.travel is None:
            raise RuntimeError("no setup cost data: the free-flow relation is unreadable")
        result, memory_out = apply_rule(observation.fields, faction, tuple(base.actions), memory, self.travel)
        return AddonResult(result.actions, change_records(result), skip_counts(result), memory_out)


class StaggerPolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = StaggerAddon


class StaggerAgent(AddonAgent):
    policy_class = StaggerPolicy
