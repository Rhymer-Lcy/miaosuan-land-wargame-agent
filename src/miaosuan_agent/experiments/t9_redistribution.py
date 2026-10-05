"""OFFLINE design candidates of Sprint 14: v3's batch allocation plus bounded cross-objective redistribution.

Sprint 14 design competition (``docs/SPRINT14_REDISTRIBUTION.md``). Not in any run card unless a later registration
selects exactly one rule; never packaged. Every rule here was frozen before any rule was replayed on the target
corpus.

``baseline-v2`` decides first, unchanged (:mod:`.exploratory_addon`). One decision is then allocated in two stages.

Stage 1 is ``t9-batch-capacity-v3`` (:mod:`.t9_batch`) restated without change: incumbents of an objective are the
own ground units standing on it with no path and the movers whose path ends on it, a mover counting unless its
remaining free-flow time already reaches the end of the game; claimants are the own ground units ``baseline-v2``
moves to an objective, ranked together by free-flow time, route cost, path length and unit id (never by emission
order); the best selectable claimants take the free places and keep ``baseline-v2``'s move.

Stage 2 redistributes overflow only. A claimant that could arrive before the end but found its objective full may be
redirected to another objective, by the same move ``baseline-v2``'s own candidate builder makes for that unit and
objective (the router's path from the unit's hex), when all of these hold:

* the objective is not held by the side and differs from the claimant's own;
* its places counted the stage-1 way, including this decision's selections and redirects, stay below ``CAPACITY``;
* the route cost is at most ``DETOUR`` times the cost to the claimant's own objective (T9-v1's bound);
* the free-flow time along the new path ends before the game does (the lower-bound discipline of stage 1);
* the rule's own bounds: a free-flow horizon and/or a share of ``baseline-v2``'s path the new path must keep as its
  prefix.

Among the admissible objectives a rule ranks by T9-v1's preference (route cost divided by objective value, then cost,
then hex) or by ``baseline-v2``'s own (route cost, then hex). Overflow claimants choose in stage-1 rank order, or, for a
batch rule, are assigned all at once: as many redirects as the places allow, then the smallest total of the rule's
first rank component (a min-cost maximum flow, solved in a canonical order).

Every other claimant is staged on its own route or withheld exactly as by stage 1. Replaced moves pass the project gate
together with the step's other actions; a rejected redirect or staged move is withheld. Shots, occupations, air units,
units ``baseline-v2`` leaves idle and every other action are unchanged and keep their order. Fail closed: if the
allocation cannot be computed, every own ground move to an objective is withheld for this decision and the error is
recorded. Inputs are the seat's own observation and the setup cost data. Stateless: no memory.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from ..decision import gate
from ..decision.candidates import move_candidates
from ..decision.context import build_context
from ..decision.routing import Router
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int
from .t9_batch import CAPACITY, GROUND, MOVE, STAGE_CAP, Claimant, destination, free_flow_key, path_times

DETOUR = 2.0
LATE = "cannot arrive before the end"
FULL = "no place under capacity"
UNREADABLE = "free-flow time unreadable"
WEIGHT_SCALE = 1_000_000  # integer arc costs of the batch assignment


@dataclass(frozen=True)
class Rule:
    """One candidate: how overflow claimants are redirected."""

    name: str
    rank: str  # "value": cost / value, cost, hex (T9-v1); "cost": cost, hex (baseline-v2's own order)
    horizon: Optional[int] = None  # largest admissible free-flow time of a redirect, in steps
    min_prefix: Optional[float] = None  # smallest share of baseline-v2's path kept as the redirect's prefix
    batch: bool = False  # assign every overflow claimant at once instead of in rank order

    @property
    def identity(self) -> str:
        return f"t9-{self.name}-v4"


RULES: Dict[str, Rule] = {rule.name: rule for rule in (
    Rule("feasible-cost-redirect", "cost"),
    Rule("feasible-value-redirect", "value"),
    Rule("feasible-value-redirect-h1440", "value", horizon=1440),
    Rule("feasible-value-redirect-h720", "value", horizon=720),
    Rule("corridor-value-redirect-p25", "value", min_prefix=0.25),
    Rule("corridor-value-redirect-p50", "value", min_prefix=0.5),
    Rule("corridor-value-redirect-p75", "value", min_prefix=0.75),
    Rule("batch-value-redirect", "value", batch=True),
)}


@dataclass(frozen=True)
class Option:
    """One admissible redirect of one claimant."""

    objective: int
    action: Mapping[str, Any]
    path: Tuple[int, ...]
    cost: float
    base_cost: float
    free_flow: int
    prefix: int  # leading hexes shared with baseline-v2's path
    key: Tuple[Any, ...]


@dataclass
class Allocation:
    """Everything one decision's allocation computed (the add-on emits ``actions``; analyses read the rest)."""

    actions: Tuple[Mapping[str, Any], ...]
    changes: List[Dict[str, Any]] = field(default_factory=list)
    skipped: collections.Counter = field(default_factory=collections.Counter)
    objectives: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    claimants: Dict[int, Claimant] = field(default_factory=dict)
    selected: Dict[int, int] = field(default_factory=dict)  # obj_id -> objective
    redirected: Dict[int, Option] = field(default_factory=dict)  # obj_id -> chosen redirect
    staged: Dict[int, Tuple[int, ...]] = field(default_factory=dict)  # obj_id -> staged path
    withheld: Dict[int, str] = field(default_factory=dict)  # obj_id -> reason
    dropped: collections.Counter = field(default_factory=collections.Counter)  # excluded alternatives by reason
    error: Optional[str] = None


def shared_prefix(a: Sequence[Any], b: Sequence[Any]) -> int:
    count = 0
    for x, y in zip(a, b):
        if x != y:
            break
        count += 1
    return count


def allocate(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
             router: Optional[Router], rule: Optional[Rule]) -> Allocation:
    """One decision's allocation under ``rule`` (``None``: stage 1 alone, which must equal ``t9_batch.allocate``)."""
    actions = tuple(actions)
    if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
        return Allocation(actions)
    try:
        return _allocate(observation, seat, faction, actions, router, rule)
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
        return Allocation(tuple(kept), changes, error=f"{type(exc).__name__}: {exc}"[:300])


def _allocate(observation: Observation, seat: int, faction: int, actions: Tuple[Mapping[str, Any], ...],
              router: Optional[Router], rule: Optional[Rule]) -> Allocation:
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
    incumbents = {coord: {"physical": 0, "movers": 0, "phantom": 0, "mover_bounds": {}} for coord in cities}
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
        bound = None if times is None else sum(times[1:])  # the hex being entered may be partly done
        if bound is not None and end is not None and now + bound >= end:
            row["phantom"] += 1
            out.skipped["mover cannot arrive before the end: no place held"] += 1
        else:
            row["movers"] += 1
            row["mover_bounds"][unit.obj_id] = bound

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
        ranked = sorted(group, key=free_flow_key)
        chosen = [c for c in ranked if c.feasible][:max(free, 0)]
        for claimant in chosen:
            out.selected[claimant.obj_id] = coord
            counted[coord] += 1
        out.objectives[coord] = {"physical": row["physical"], "movers": row["movers"], "phantom": row["phantom"],
                                 "mover_bounds": dict(row["mover_bounds"]),
                                 "free": free, "claimants": len(group),
                                 "ranked": [c.obj_id for c in ranked], "selected": [c.obj_id for c in chosen]}

    overflow = sorted((c for c in claimants.values() if c.obj_id not in out.selected and c.status == FULL),
                      key=free_flow_key)
    if rule is not None and overflow:
        if hasattr(router, "targets"):
            router.targets = frozenset(city.coord for city in context.objectives)  # as baseline-v2 sets it
        unheld = {city.coord: city for city in context.objectives}
        options = {c.obj_id: _options(c, own[c.obj_id], context, router, rule, unheld, seat, now, end, out.dropped)
                   for c in overflow}
        if rule.batch:
            assigned = batch_assign([c.obj_id for c in overflow], options, counted)
        else:
            assigned = {}
            for claimant in overflow:
                open_ = [o for o in options[claimant.obj_id] if counted[o.objective] < CAPACITY]
                if not open_:
                    continue
                choice = min(open_, key=lambda o: o.key)
                counted[choice.objective] += 1
                assigned[claimant.obj_id] = choice
        out.redirected = dict(assigned)

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

    for coord in sorted(out.objectives):
        info = out.objectives[coord]
        out.skipped["kept: selected"] += len(info["selected"])
        out.skipped["incumbent movers retained (cannot be re-ordered)"] += info["movers"]
    if out.redirected:
        out.skipped["redirected to another objective"] += len(out.redirected)
    for reason, count in out.dropped.items():
        out.skipped[f"alternative excluded: {reason}"] += count

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
    return out


def _options(claimant: Claimant, unit: Any, context: Any, router: Router, rule: Rule, unheld: Mapping[int, Any],
             seat: int, now: int, end: Optional[int], dropped: collections.Counter) -> List[Option]:
    """Every admissible redirect of one overflow claimant, best first (capacity is checked by the caller)."""
    unit_ctx = context.unit(claimant.obj_id)
    if unit_ctx is None:
        dropped["claimant not controllable"] += 1
        return []
    candidates, _ = move_candidates(unit_ctx, context, router)
    costs = {dict(c.detail)["destination"]: dict(c.detail)["cost"] for c in candidates}
    base_cost = costs.get(claimant.objective)
    if base_cost is None:
        dropped["no route cost to the own objective"] += 1
        return []
    options = []
    for candidate in candidates:
        detail = dict(candidate.detail)
        coord, cost = detail["destination"], detail["cost"]
        if coord == claimant.objective:
            continue
        if coord not in unheld:
            dropped["objective held by the side"] += 1
            continue
        if cost > DETOUR * base_cost:
            dropped["detour bound"] += 1
            continue
        action = candidate.action(seat)
        path = tuple(action["move_path"])
        times, _ = path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"), unit.cur_hex,
                              path)
        if times is None:
            dropped[UNREADABLE] += 1
            continue
        free_flow = sum(times)
        if end is not None and now + free_flow >= end:
            dropped[LATE] += 1
            continue
        if rule.horizon is not None and free_flow > rule.horizon:
            dropped["beyond the redirect horizon"] += 1
            continue
        prefix = shared_prefix(claimant.path, path)
        if rule.min_prefix is not None and prefix < rule.min_prefix * len(claimant.path):
            dropped["leaves baseline-v2's corridor"] += 1
            continue
        value = unheld[coord].value
        weight = value if is_int(value) and value > 0 else 1
        key = (cost / weight, cost, coord) if rule.rank == "value" else (cost, coord)
        options.append(Option(coord, action, path, cost, base_cost, free_flow, prefix, key))
    return sorted(options, key=lambda o: o.key)


def batch_assign(order: Sequence[int], options: Mapping[int, Sequence[Option]],
                 counted: Mapping[int, int]) -> Dict[int, Option]:
    """Min-cost maximum flow from overflow claimants (in ``order``) to objectives with ``CAPACITY - counted`` places
    left; arc cost = the option's first rank component, scaled to an integer. Successive shortest paths with
    Bellman-Ford over a canonically ordered arc list, so the result depends only on the inputs, never on emission
    order. Updates nothing in ``counted``; returns claimant -> option."""
    objectives = sorted({o.objective for ops in options.values() for o in ops if CAPACITY - counted[o.objective] > 0})
    if not objectives:
        return {}
    claimant_ids = [u for u in order if any(o.objective in objectives for o in options.get(u, ()))]
    source, sink = 0, 1 + len(claimant_ids) + len(objectives)
    node_of_claimant = {u: 1 + i for i, u in enumerate(claimant_ids)}
    node_of_objective = {coord: 1 + len(claimant_ids) + j for j, coord in enumerate(objectives)}
    # arcs: [tail, head, capacity, cost, reverse index]
    arcs: List[List[int]] = []
    adjacency: Dict[int, List[int]] = collections.defaultdict(list)

    def add(tail: int, head: int, capacity: int, cost: int) -> int:
        adjacency[tail].append(len(arcs))
        arcs.append([tail, head, capacity, cost, len(arcs) + 1])
        adjacency[head].append(len(arcs))
        arcs.append([head, tail, 0, -cost, len(arcs) - 1])
        return len(arcs) - 2

    choice_arcs: Dict[int, Tuple[int, Option]] = {}
    for u in claimant_ids:
        add(source, node_of_claimant[u], 1, 0)
        for option in options[u]:
            if option.objective in node_of_objective:
                index = add(node_of_claimant[u], node_of_objective[option.objective], 1,
                            int(round(option.key[0] * WEIGHT_SCALE)))
                choice_arcs[index] = (u, option)
    for coord in objectives:
        add(node_of_objective[coord], sink, CAPACITY - counted[coord], 0)
    nodes = sink + 1
    while True:
        distance: List[Optional[int]] = [None] * nodes
        via: List[Optional[int]] = [None] * nodes
        distance[source] = 0
        for _ in range(nodes - 1):
            changed = False
            for index, (tail, head, capacity, cost, _) in enumerate(arcs):
                if capacity > 0 and distance[tail] is not None and (
                        distance[head] is None or distance[tail] + cost < distance[head]):
                    distance[head] = distance[tail] + cost
                    via[head] = index
                    changed = True
            if not changed:
                break
        if distance[sink] is None:
            break
        node = sink
        while node != source:
            index = via[node]
            arcs[index][2] -= 1
            arcs[arcs[index][4]][2] += 1
            node = arcs[index][0]
    return {u: option for index, (u, option) in choice_arcs.items() if arcs[index][2] == 0}


class RedistributionAddon(Addon):
    name = "t9_redistribution"
    rule: Optional[Rule] = None

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        if self.rule is None:
            raise ValueError("no redistribution rule bound")
        result = allocate(observation, seat, faction, tuple(base.actions), self.baseline.router, self.rule)
        changes = list(result.changes)
        if result.error is not None:
            changes.append({"kind": "error", "reason": result.error})
        return AddonResult(result.actions, tuple(changes), tuple(sorted(result.skipped.items())))


def _bind(rule: Rule) -> Tuple[type, type]:
    suffix = "".join(part.capitalize() for part in rule.name.split("-"))
    addon = type(f"{suffix}Addon", (RedistributionAddon,), {"rule": rule})
    policy = type(f"{suffix}Policy", (AddonPolicy,), {"identity": rule.identity, "addon_class": addon})
    agent = type(f"{suffix}Agent", (AddonAgent,), {"policy_class": policy})
    return policy, agent


POLICIES: Dict[str, type] = {}
AGENTS: Dict[str, type] = {}
for _name, _rule in RULES.items():
    POLICIES[_name], AGENTS[_name] = _bind(_rule)
del _name, _rule
