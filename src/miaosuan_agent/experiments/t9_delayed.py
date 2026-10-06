"""OFFLINE design candidates of Sprint 15: v3's allocation plus DELAYED, memory-triggered cross-objective redistribution.

Sprint 15 (``docs/SPRINT15_DELAYED_REDISTRIBUTION.md``). Not in any run card and never packaged; every rule here was
frozen before any rule was replayed on the target corpus.

``baseline-v2`` decides first, unchanged (:mod:`.exploratory_addon`). One decision is then allocated exactly as Sprint
14's minimal rule (``t9_redistribution``, ``feasible-value-redirect``, which equals Sprint 13's oracle O2) with one
difference: an overflow claimant (a unit that could arrive at its own objective before the end but found it full) may be
redirected only when the rule's TRIGGER holds for it, and the trigger reads nothing but the seat's own memory of what it
observed and did at earlier decisions. Every claimant whose trigger does not hold is staged on its own route or withheld
exactly as by v3. With no claimant eligible the allocation equals ``t9_batch.allocate`` (v3); with every overflow
claimant eligible it equals ``feasible-value-redirect``. Stage 1, the admissibility of a redirect (objective not held,
fewer than four counted places, route cost at most twice the cost to the own objective, free-flow arrival before the
end), the ranking of alternatives (cost / value, cost, hex) and the order of claimants (v3's rank) are Sprint 14's,
unchanged.

Memory (one record per own ground unit, kept only while the unit is present):

* an *episode* is a run of observed overflow of one unit at one source objective; it starts at the first decision at
  which the unit is overflow at that source, and its counters reset when the unit claims another source;
* the record ends (is deleted) when the unit is no longer among the seat's own ground units, when it is observed
  moving to an objective (a counted mover) or standing on one, when stage 1 gives it a place, or when it claims while
  it cannot arrive before the end; the episode alone ends (its counters, alternative, saturation and redirect flag
  return to 0) when its source objective is held by the side;
* ``staged`` is the endpoint of the last staging move the add-on emitted for the unit; ``done`` becomes 1 when the unit
  is later observed with no path standing on that endpoint (the staging move completed). ``done`` survives a change of
  source, so that "a unit deferred once and available again" is remembered across a re-targeting by ``baseline-v2``;
* ``alternative`` is the best admissible alternative (stage-1 counts, before this decision's redirects) at the unit's
  last overflow observation; ``saturated`` is 1 when the source was then held by four own units standing on it with no
  counted mover;
* ``redirected`` is 1 once the add-on redirected the unit in the current episode: at most one redirect per episode
  (bounded recourse).

Triggers (``RULES``): ``repeat`` (the episode has at least ``count`` overflow observations, this one included),
``stable`` (the same best admissible alternative as at the previous overflow observation of the same episode),
``staged`` (the unit completed a staging move the add-on emitted, at the same source or any source), ``saturated``
(the source is saturated now and was at the previous overflow observation of the same episode). No trigger reads the
decision index, the scenario, a unit id or a coordinate as such.

The add-on's state is a sorted tuple of (key, value) integer pairs (``exploratory_addon.AddonMemory.addon``), key =
unit id times ``FIELDS`` plus the field index. A record that cannot be decoded is dropped (no redirect for that unit:
the conservative direction) and the error is recorded. Fail closed exactly as Sprint 14: if the allocation cannot be
computed, every own ground move to an objective is withheld for this decision; memory is then carried forward with the
observation-driven updates only.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from ..decision import gate
from ..decision.context import build_context
from ..decision.routing import Router
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int
from .t9_batch import CAPACITY, GROUND, MOVE, STAGE_CAP, Claimant, destination, free_flow_key, path_times
from .t9_redistribution import FULL, LATE, RULES as S14_RULES, UNREADABLE, Option, _options

BASE_RULE = S14_RULES["feasible-value-redirect"]  # Sprint 14's minimal rule = Sprint 13's oracle O2
FIELDS = 16
FIELD_NAMES = ("source", "count", "staged", "done", "alternative", "saturated", "redirected", "first", "stage_source")
SOURCE, COUNT, STAGED, DONE, ALTERNATIVE, SATURATED, REDIRECTED, FIRST, STAGE_SOURCE = range(len(FIELD_NAMES))
COUNT_CAP = 1000  # the episode counter saturates here; no rule reads beyond its own small threshold


@dataclass(frozen=True)
class DelayedRule:
    name: str
    trigger: str  # "repeat" | "stable" | "staged" | "saturated"
    count: int = 0  # repeat: overflow observations required in the episode
    same_source: bool = True  # staged: the completed staging move was toward the current source

    @property
    def identity(self) -> str:
        return f"t9-{self.name}-v5"


#: Declared order of simplicity, simplest first (selection rubric step 5).
RULES: Dict[str, DelayedRule] = {rule.name: rule for rule in (
    DelayedRule("delayed-repeat-2", "repeat", count=2),
    DelayedRule("delayed-repeat-3", "repeat", count=3),
    DelayedRule("delayed-stable-alternative", "stable"),
    DelayedRule("delayed-post-stage-same", "staged", same_source=True),
    DelayedRule("delayed-post-stage-any", "staged", same_source=False),
    DelayedRule("delayed-saturated-source", "saturated"),
)}


# ------------------------------------------------------------------------------------------------
# Memory codec


def decode(memory: Sequence[Sequence[int]]) -> Tuple[Dict[int, List[int]], List[str]]:
    """Records by unit from the add-on state; malformed entries are dropped and named."""
    records: Dict[int, List[int]] = {}
    errors: List[str] = []
    for entry in memory or ():
        try:
            key, value = entry
        except (TypeError, ValueError):
            errors.append("malformed entry")
            continue
        if not (is_int(key) and is_int(value)) or key < 0:
            errors.append("non-integer entry")
            continue
        unit, index = divmod(key, FIELDS)
        if index >= len(FIELD_NAMES):
            errors.append("unknown field")
            continue
        records.setdefault(unit, [0] * len(FIELD_NAMES))[index] = value
    return records, errors


def encode(records: Mapping[int, Sequence[int]]) -> Tuple[Tuple[int, int], ...]:
    pairs = []
    for unit in sorted(records):
        for index, value in enumerate(records[unit]):
            if value:
                pairs.append((unit * FIELDS + index, int(value)))
    return tuple(pairs)


# ------------------------------------------------------------------------------------------------
# Allocation


@dataclass
class Allocation:
    """One decision's allocation (the add-on emits ``actions`` and ``memory``; analyses read the rest)."""

    actions: Tuple[Mapping[str, Any], ...]
    memory: Tuple[Tuple[int, int], ...] = ()
    changes: List[Dict[str, Any]] = field(default_factory=list)
    skipped: collections.Counter = field(default_factory=collections.Counter)
    claimants: Dict[int, Claimant] = field(default_factory=dict)
    selected: Dict[int, int] = field(default_factory=dict)
    overflow: Tuple[int, ...] = ()
    eligible: Tuple[int, ...] = ()  # overflow claimants whose trigger held
    best: Dict[int, int] = field(default_factory=dict)  # overflow claimant -> best admissible alternative (0: none)
    redirected: Dict[int, Option] = field(default_factory=dict)
    staged: Dict[int, Tuple[int, ...]] = field(default_factory=dict)
    withheld: Dict[int, str] = field(default_factory=dict)
    ended: Dict[int, str] = field(default_factory=dict)  # records deleted at this decision, by reason
    error: Optional[str] = None


def observe(observation: Observation, faction: int, records: Dict[int, List[int]]) -> Dict[int, str]:
    """Observation-driven memory updates before the allocation (in place); returns the deleted records' reasons."""
    ended: Dict[int, str] = {}
    own = {u.obj_id: u for u in observation.operators() if u.color == faction and u.unit_type in GROUND}
    cities = {c.coord: c for c in (observation.cities() or ())}
    for unit_id in sorted(records):
        record = records[unit_id]
        unit = own.get(unit_id)
        path = tuple(unit.move_path or ()) if unit is not None else ()
        if unit is None:
            reason = "absent"
        elif path and path[-1] in cities:
            reason = "moving to an objective"
        elif not path and unit.cur_hex in cities:
            reason = "standing on an objective"
        else:
            reason = None
        if reason is not None:
            ended[unit_id] = reason
            del records[unit_id]
            continue
        if record[SOURCE] in cities and cities[record[SOURCE]].flag == faction:
            # the episode ends with its source; what the unit itself did (a completed staging move) is kept
            ended[unit_id] = "source held by the side"
            for index in (SOURCE, COUNT, ALTERNATIVE, SATURATED, REDIRECTED, FIRST):
                record[index] = 0
        if record[STAGED] and not path and unit.cur_hex == record[STAGED]:
            record[DONE] = 1
        if not any(record):
            del records[unit_id]
    return ended


def eligible(rule: DelayedRule, record: Optional[Sequence[int]], source: int, best: int, saturated: bool) -> bool:
    """The rule's trigger for one overflow claimant at its source, from its record as updated by :func:`observe`."""
    if record is None or record[REDIRECTED]:
        return False
    same = record[SOURCE] == source
    if rule.trigger == "repeat":
        return same and record[COUNT] + 1 >= rule.count
    if rule.trigger == "stable":
        return same and best != 0 and record[ALTERNATIVE] == best
    if rule.trigger == "staged":
        return bool(record[DONE]) and (not rule.same_source or record[STAGE_SOURCE] == source)
    if rule.trigger == "saturated":
        return same and saturated and bool(record[SATURATED])
    raise ValueError(f"unknown trigger {rule.trigger}")


def allocate(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
             router: Optional[Router], rule: Optional[DelayedRule], memory: Sequence[Sequence[int]] = (),
             everyone: bool = False) -> Allocation:
    """One decision. ``rule`` None: no claimant is eligible (v3). ``everyone``: every overflow claimant is eligible
    (Sprint 14's ``feasible-value-redirect``); both exist only for the identity checks."""
    actions = tuple(actions)
    records, errors = decode(memory)
    if observation.time().stage != Stage.PLAY:
        return Allocation(actions, encode(records))
    try:
        ended = observe(observation, faction, records)
    except ContractError:
        raise
    except Exception:  # noqa: BLE001 - memory that cannot be updated is forgotten: no redirect can follow from it
        errors.append("memory update failed")
        ended = {unit_id: "memory update failed" for unit_id in records}
        records = {}
    return _allocate_or_fail(observation, seat, faction, actions, router, rule, records, ended, errors, everyone)


def _allocate_or_fail(observation: Observation, seat: int, faction: int, actions: Tuple[Mapping[str, Any], ...],
                      router: Optional[Router], rule: Optional[DelayedRule], records: Dict[int, List[int]],
                      ended: Dict[int, str], errors: List[str], everyone: bool) -> Allocation:
    if not any(a.get("type") == MOVE for a in actions):
        out = Allocation(actions, encode(records), ended=ended)
        if errors:
            out.changes.append({"kind": "memory-dropped", "count": len(errors)})
        return out
    try:
        out = _allocate(observation, seat, faction, actions, router, rule, records, everyone)
    except ContractError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed: no ground move to an objective leaves unchecked
        cities = set()
        try:
            cities = {city.coord for city in (observation.cities() or ())}
        except Exception:  # noqa: BLE001
            pass
        ground = set()
        for unit in observation.operators():
            try:
                if unit.color == faction and unit.unit_type in GROUND:
                    ground.add(unit.obj_id)
            except ContractError:
                continue
        kept, changes = [], []
        for action in actions:
            if action.get("type") == MOVE and action.get("obj_id") in ground and (
                    not cities or destination(action) in cities or destination(action) is None):
                changes.append({"kind": "fail-closed", "obj_id": action.get("obj_id")})
                continue
            kept.append(action)
        out = Allocation(tuple(kept), encode(records), changes, error=f"{type(exc).__name__}: {exc}"[:300])
    out.ended.update(ended)
    if errors:
        out.changes.append({"kind": "memory-dropped", "count": len(errors)})
    return out


def _allocate(observation: Observation, seat: int, faction: int, actions: Tuple[Mapping[str, Any], ...],
              router: Optional[Router], rule: Optional[DelayedRule], records: Dict[int, List[int]],
              everyone: bool) -> Allocation:
    if router is None:
        raise ValueError("no movement-cost data")
    context = build_context(observation, seat, faction)
    time_info = observation.time()
    end = time_info.max_step if is_int(time_info.max_step) else None
    now = time_info.cur_step
    cities = {city.coord for city in (observation.cities() or ())}
    if not cities:
        raise ValueError("no objectives in the observation")

    own: Dict[int, Any] = {}
    for unit in observation.operators():
        if unit.color == faction and unit.unit_type in GROUND:
            own[unit.obj_id] = unit
    out = Allocation(actions)
    endpoints: collections.Counter = collections.Counter()
    incumbents = {coord: {"physical": 0, "movers": 0} for coord in cities}
    for unit in own.values():
        path = tuple(unit.move_path or ())
        stop = path[-1] if path else unit.cur_hex
        endpoints[stop] += 1
        if stop not in cities:
            continue
        row = incumbents[stop]
        if not path:
            row["physical"] += 1
            continue
        times, _ = path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"),
                              unit.cur_hex, path)
        bound = None if times is None else sum(times[1:])
        if bound is not None and end is not None and now + bound >= end:
            out.skipped["mover cannot arrive before the end: no place held"] += 1
        else:
            row["movers"] += 1

    claimants: Dict[int, Claimant] = {}
    for index, action in enumerate(actions):
        obj_id = action.get("obj_id")
        if action.get("type") != MOVE or obj_id not in own:
            continue
        dest = destination(action)
        if dest is None:
            out.skipped["move without a readable destination: kept"] += 1
            continue
        if dest not in cities:
            out.skipped["move to a non-objective hex: kept"] += 1
            continue
        unit = own[obj_id]
        path = tuple(action["move_path"])
        times, cost = path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"),
                                 unit.cur_hex, path)
        free_flow = None if times is None else sum(times)
        if free_flow is None:
            status = UNREADABLE
        elif end is not None and now + free_flow >= end:
            status = LATE
        else:
            status = FULL
        claimants[obj_id] = Claimant(obj_id, dest, path, free_flow, cost, status == FULL, index, status)
    out.claimants = claimants

    by_objective: Dict[int, List[Claimant]] = collections.defaultdict(list)
    for claimant in claimants.values():
        by_objective[claimant.objective].append(claimant)
    counted = {coord: row["physical"] + row["movers"] for coord, row in incumbents.items()}
    for coord, group in sorted(by_objective.items()):
        row = incumbents[coord]
        free = CAPACITY - row["physical"] - row["movers"]
        for claimant in [c for c in sorted(group, key=free_flow_key) if c.feasible][:max(free, 0)]:
            out.selected[claimant.obj_id] = coord
            counted[coord] += 1

    overflow = sorted((c for c in claimants.values() if c.obj_id not in out.selected and c.status == FULL),
                      key=free_flow_key)
    out.overflow = tuple(c.obj_id for c in overflow)
    if overflow:
        if hasattr(router, "targets"):
            router.targets = frozenset(city.coord for city in context.objectives)  # as baseline-v2 sets it
        unheld = {city.coord: city for city in context.objectives}
        dropped: collections.Counter = collections.Counter()
        options = {c.obj_id: _options(c, own[c.obj_id], context, router, BASE_RULE, unheld, seat, now, end, dropped)
                   for c in overflow}
        for claimant in overflow:
            open_now = [o for o in options[claimant.obj_id] if counted[o.objective] < CAPACITY]
            out.best[claimant.obj_id] = open_now[0].objective if open_now else 0
        ok = []
        for claimant in overflow:
            row = incumbents[claimant.objective]
            saturated = row["physical"] >= CAPACITY and row["movers"] == 0
            if everyone or (rule is not None and eligible(rule, records.get(claimant.obj_id), claimant.objective,
                                                          out.best[claimant.obj_id], saturated)):
                ok.append(claimant.obj_id)
        out.eligible = tuple(ok)
        for claimant in overflow:
            if claimant.obj_id not in ok:
                continue
            open_ = [o for o in options[claimant.obj_id] if counted[o.objective] < CAPACITY]
            if not open_:
                continue
            choice = min(open_, key=lambda o: o.key)
            counted[choice.objective] += 1
            out.redirected[claimant.obj_id] = choice
        for reason, count in dropped.items():
            out.skipped[f"alternative excluded: {reason}"] += count

    rest = sorted((c for c in claimants.values() if c.obj_id not in out.selected and c.obj_id not in out.redirected),
                  key=free_flow_key)
    replacements: Dict[int, Dict[str, Any]] = {}
    for obj_id, option in sorted(out.redirected.items()):
        claimant = claimants[obj_id]
        replacements[obj_id] = dict(option.action)
        out.changes.append({"kind": "redirect", "obj_id": obj_id, "from": claimant.objective, "to": option.objective,
                            "free_flow": option.free_flow, "cost": option.cost, "base_cost": option.base_cost,
                            "prefix": option.prefix, "path_length": len(option.path),
                            "base_path_length": len(claimant.path)})
    for claimant in rest:
        reason = claimant.status
        target = None
        for position in range(len(claimant.path) - 2, -1, -1):
            hex_ = claimant.path[position]
            if hex_ not in cities and endpoints[hex_] < STAGE_CAP:
                target = position
                break
        if target is None:
            out.withheld[claimant.obj_id] = reason
            out.changes.append({"kind": "withhold", "obj_id": claimant.obj_id, "destination": claimant.objective,
                                "free_flow": claimant.free_flow, "reason": reason})
            continue
        staged_path = claimant.path[:target + 1]
        endpoints[staged_path[-1]] += 1
        out.staged[claimant.obj_id] = staged_path
        replacement = dict(actions[claimant.index])
        replacement["move_path"] = list(staged_path)
        replacements[claimant.obj_id] = replacement
        out.changes.append({"kind": "stage", "obj_id": claimant.obj_id, "destination": claimant.objective,
                            "staging": staged_path[-1], "free_flow": claimant.free_flow, "reason": reason,
                            "path_length": len(claimant.path), "staged_path_length": len(staged_path)})

    out.skipped["kept: selected"] += len(out.selected)
    if out.redirected:
        out.skipped["redirected to another objective"] += len(out.redirected)
    if out.overflow:
        out.skipped["overflow claimants whose trigger held"] += len(out.eligible)
        out.skipped["overflow claimants deferred by the trigger"] += len(out.overflow) - len(out.eligible)

    final: List[Optional[Mapping[str, Any]]] = []
    for action in actions:
        obj_id = action.get("obj_id")
        if action.get("type") == MOVE and obj_id in claimants and obj_id not in out.selected:
            final.append(replacements.get(obj_id))
        else:
            final.append(action)
    checked = gate.check([a for a in final if a is not None], context, router)
    rejected = {rejection.obj_id: rejection.reason for rejection in checked.rejected}
    for position, action in enumerate(final):
        if action is None:
            continue
        obj_id = action.get("obj_id")
        if obj_id in replacements and obj_id in rejected:
            final[position] = None
            if out.redirected.pop(obj_id, None) is not None:
                out.withheld[obj_id] = "redirect rejected by the gate"
                out.changes.append({"kind": "redirect-rejected", "obj_id": obj_id, "reason": rejected[obj_id]})
            else:
                out.staged.pop(obj_id, None)
                out.withheld[obj_id] = "staged move rejected by the gate"
                out.changes.append({"kind": "stage-rejected", "obj_id": obj_id, "reason": rejected[obj_id]})
    out.actions = tuple(a for a in final if a is not None)

    # memory after the decision
    for obj_id, claimant in sorted(claimants.items()):
        record = records.get(obj_id)
        if obj_id in out.selected or claimant.status != FULL:
            if record is not None:
                out.ended[obj_id] = "given a place" if obj_id in out.selected else "cannot arrive before the end"
                del records[obj_id]
            continue
        if record is None:
            record = records[obj_id] = [0] * len(FIELD_NAMES)
        if record[SOURCE] != claimant.objective:
            record[SOURCE], record[COUNT], record[FIRST] = claimant.objective, 0, now
            record[REDIRECTED] = 0
        row = incumbents[claimant.objective]
        record[COUNT] = min(record[COUNT] + 1, COUNT_CAP)
        record[ALTERNATIVE] = out.best.get(obj_id, 0)
        record[SATURATED] = int(row["physical"] >= CAPACITY and row["movers"] == 0)
        if obj_id in out.redirected:
            record[REDIRECTED] = 1
        elif obj_id in out.staged:
            record[STAGED], record[STAGE_SOURCE], record[DONE] = out.staged[obj_id][-1], claimant.objective, 0
    out.memory = encode(records)
    return out


# ------------------------------------------------------------------------------------------------
# Add-on, policies, agents


class DelayedAddon(Addon):
    name = "t9_delayed"
    rule: Optional[DelayedRule] = None

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        if self.rule is None:
            raise ValueError("no delayed rule bound")
        result = allocate(observation, seat, faction, tuple(base.actions), self.baseline.router, self.rule, memory)
        changes = list(result.changes)
        if result.error is not None:
            changes.append({"kind": "error", "reason": result.error})
        for unit_id, reason in sorted(result.ended.items()):
            changes.append({"kind": "memory-ended", "obj_id": unit_id, "reason": reason})
        return AddonResult(result.actions, tuple(changes), tuple(sorted(result.skipped.items())), result.memory)


def _bind(rule: DelayedRule) -> Tuple[type, type]:
    suffix = "".join(part.capitalize() for part in rule.name.split("-"))
    addon = type(f"{suffix}Addon", (DelayedAddon,), {"rule": rule})
    policy = type(f"{suffix}Policy", (AddonPolicy,), {"identity": rule.identity, "addon_class": addon})
    agent = type(f"{suffix}Agent", (AddonAgent,), {"policy_class": policy})
    return policy, agent


POLICIES: Dict[str, type] = {}
AGENTS: Dict[str, type] = {}
for _name, _rule in RULES.items():
    POLICIES[_name], AGENTS[_name] = _bind(_rule)
del _name, _rule
