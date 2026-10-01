"""Analysis-only model of the target-ownership design study (``target-ownership-design-1``). Not a policy.

One seat's legal shoot opportunities at one decision are a bipartite graph: shooters (controllable units, in
baseline-v2's processing order) and targets, with an edge where the shooter has at least one shoot candidate on the
target. The edge carries the shooter's best existing candidate on that target by baseline-v2's own within-unit rank
(highest attack level, then lower weapon id; the target id is fixed on an edge). Candidates are extracted exactly as
baseline-v2 extracts them (``engage_candidates`` on the tactical context), so the graph is baseline-v2's view.

Connected components of the graph are classified:

* **S1**: exactly one target and at least two shooters (an isolated single-target collision component);
* **S2**: two or more targets and at least two shooters (coupled);
* **S3**: one shooter (no competing claimant).

For an S1 component on target T, baseline-v2's owner is its first shooter in processing order (every shooter's only
shoot candidates are on T and shooting has priority, so the first one shoots T whenever its shot passes the gate).
The designed rule names the claimant with the highest attack level on T, ties broken by lower weapon id, then by
processing order. The designated owner counts only if its shot passes the same single-proposal gate check
baseline-v2 uses to reserve a target; otherwise the component keeps baseline-v2's behaviour. S2 and S3 components
always keep baseline-v2's behaviour.

The S1 oracle measures the designed rule without implementing it: it removes T's candidates from every shooter of
the component processed before the designated owner and lets the frozen baseline-v2 decide on that copy of the
observation. Later shooters are then excluded by baseline-v2's own same-step reservation, as the design intends.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import Observation, Origin
from ..decision import Memory
from ..decision import gate
from ..decision.candidates import engage_candidates
from ..decision.context import build_context
from . import allocation_audit as aa

KINDS = ("S1", "S2", "S3")
Graph = Dict[int, Dict[int, Tuple[int, int]]]  # shooter -> target -> (attack level, weapon) of its best candidate


def _target_weapon_level(candidate: Any) -> Tuple[int, int, int]:
    params = dict(candidate.params)
    return params["target_obj_id"], params["weapon_id"], dict(candidate.detail)["attack_level"]


def shoot_graph(raw: Mapping[str, Any], seat: int, faction: int,
                origin: Origin = Origin.ENGINE) -> Tuple[List[int], Graph]:
    """baseline-v2's processing order and its shoot graph for one seat observation."""
    context = build_context(Observation.from_raw(raw, origin), seat, faction)
    order = [unit.obj_id for unit in context.units]
    graph: Graph = {}
    for unit in context.units:
        options = [_target_weapon_level(c) for c in engage_candidates(unit)[0]]
        edges = {}
        for target in sorted({o[0] for o in options}):
            _, weapon, level = aa.best_on(options, target)
            edges[target] = (level, weapon)
        if edges:
            graph[unit.obj_id] = edges
    return order, graph


@dataclass(frozen=True)
class Component:
    shooters: Tuple[int, ...]  # processing order
    targets: Tuple[int, ...]  # ascending id
    edges: int

    @property
    def kind(self) -> str:
        return "S3" if len(self.shooters) == 1 else "S1" if len(self.targets) == 1 else "S2"


def components(order: Sequence[int], graph: Graph) -> List[Component]:
    """Connected components of the shoot graph, ordered by their first shooter's position."""
    parent: Dict[Tuple[str, int], Tuple[str, int]] = {}

    def find(node: Tuple[str, int]) -> Tuple[str, int]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for shooter, edges in graph.items():
        for target in edges:
            a, b = find(("u", shooter)), find(("t", target))
            if a != b:
                parent[b] = a
    position = {unit: i for i, unit in enumerate(order)}
    groups: Dict[Tuple[str, int], List[int]] = {}
    for shooter in graph:
        groups.setdefault(find(("u", shooter)), []).append(shooter)
    result = []
    for members in groups.values():
        shooters = tuple(sorted(members, key=lambda u: position[u]))
        targets = tuple(sorted({t for u in shooters for t in graph[u]}))
        result.append(Component(shooters, targets, sum(len(graph[u]) for u in shooters)))
    return sorted(result, key=lambda c: position[c.shooters[0]])


def owners(component: Component, graph: Graph) -> Dict[str, Any]:
    """For an S1 component: baseline-v2's owner, the designated owner and the key that decided the difference."""
    if component.kind != "S1":
        raise ValueError("ownership is designed for S1 components only")
    target = component.targets[0]
    ranked = sorted(range(len(component.shooters)),
                    key=lambda i: (-graph[component.shooters[i]][target][0], graph[component.shooters[i]][target][1], i))
    baseline, designated = component.shooters[0], component.shooters[ranked[0]]
    levels = [graph[u][target][0] for u in component.shooters]
    if designated == baseline:
        key = "unchanged"
    elif graph[designated][target][0] > graph[baseline][target][0]:
        key = "higher attack level"
    else:
        key = "weapon tie-break"
    return {"target": target, "baseline_owner": baseline, "designated_owner": designated, "key": key,
            "levels": levels, "lower_attack_level_owner": max(levels) > levels[0]}


def gate_precheck(raw: Mapping[str, Any], seat: int, faction: int, unit: int, target: int,
                  origin: Origin = Origin.ENGINE) -> bool:
    """Whether the unit's best candidate on the target passes the single-proposal gate check baseline-v2 applies
    before reserving a target (a pure function of the action and the decision's context)."""
    context = build_context(Observation.from_raw(raw, origin), seat, faction)
    unit_context = context.unit(unit)
    on_target = [c for c in engage_candidates(unit_context)[0] if _target_weapon_level(c)[0] == target]
    best = min(on_target, key=lambda c: c.rank)
    return bool(gate.check([best.action(context.seat)], context, None).accepted)


def _kind(action: Optional[Mapping[str, Any]]) -> str:
    if action is None:
        return "none"
    return {aa.SHOOT: "shoot", aa.OCCUPY: "occupy", aa.MOVE: "move"}.get(int(action["type"]), "other")


def s1_oracle(raw: Mapping[str, Any], seat: int, faction: int, decision: Any, component: Component, graph: Graph,
              policy_factory: Any, memory: Memory, origin: Origin = Origin.ENGINE) -> Dict[str, Any]:
    """The designed rule on one S1 component of one baseline-v2 decision (see the module docstring)."""
    own = owners(component, graph)
    target, baseline, designated = own["target"], own["baseline_owner"], own["designated_owner"]
    old = {a.get("obj_id", "seat"): dict(a) for a in decision.actions}
    first = old.get(baseline)
    consistent = first is not None and _kind(first) == "shoot" and first["target_obj_id"] == target
    result = {"key": own["key"], "levels": own["levels"], "baseline_owner_shot_emitted": consistent}
    if designated == baseline:
        return {**result, "owner_changed": False}
    if not gate_precheck(raw, seat, faction, designated, target, origin):
        return {**result, "owner_changed": False, "fallback": "designated owner failed the gate precheck"}
    index = component.shooters.index(designated)
    before = set(component.shooters[:index])
    other = policy_factory().decide(Observation.from_raw(aa.withdraw_target(raw, target, before), origin), seat,
                                    faction, memory)
    new = {a.get("obj_id", "seat"): dict(a) for a in other.actions}
    changed = sorted((k for k in set(old) | set(new) if old.get(k) != new.get(k)), key=str)
    promoted = new.get(designated)
    shots = [sum(1 for a in actions.values() if _kind(a) == "shoot") for actions in (old, new)]
    return {**result, "owner_changed": True,
            "designated_owner_shoots_target": _kind(promoted) == "shoot" and promoted["target_obj_id"] == target,
            "simple": set(changed) <= {baseline, designated},
            "changed_units": len(changed), "level_gain": own["levels"][index] - own["levels"][0],
            "former_owner_then": _kind(new.get(baseline)), "designated_owner_before": _kind(old.get(designated)),
            "shot_delta": shots[1] - shots[0],
            "non_shoot_changes": sum(1 for k in changed if _kind(old.get(k)) not in ("shoot", "none")
                                     or _kind(new.get(k)) not in ("shoot", "none")),
            "earlier_non_owners": index, "later_non_owners": len(component.shooters) - index - 1}


def fingerprint(config: str, raw: Mapping[str, Any], seat: int, faction: int, component: Component, graph: Graph,
                origin: Origin = Origin.ENGINE) -> str:
    """A deterministic structural fingerprint of one component, with no unit, target or weapon id in it.

    Ingredients: configuration, seat faction, component kind, and per shooter in processing order: its edges as
    (target index, attack level, weapon rank), whether occupation and movement are listed, and whether it stands on
    an objective outside own control; plus whether any objective is outside own control. Targets are indexed by
    first appearance over the shooters in processing order (each shooter's edges by level, weapon, id); weapons by
    dense rank of their id within the component."""
    context = build_context(Observation.from_raw(raw, origin), seat, faction)
    units = {u.obj_id: u for u in context.units}
    objectives = {city.coord for city in context.objectives}
    index: Dict[int, int] = {}
    for shooter in component.shooters:
        for target in sorted(graph[shooter], key=lambda t: (-graph[shooter][t][0], graph[shooter][t][1], t)):
            index.setdefault(target, len(index))
    weapons = sorted({graph[u][t][1] for u in component.shooters for t in graph[u]})
    rank = {w: i for i, w in enumerate(weapons)}
    shooters = []
    for shooter in component.shooters:
        unit = units[shooter]
        shooters.append({"edges": sorted([index[t], graph[shooter][t][0], rank[graph[shooter][t][1]]]
                                         for t in graph[shooter]),
                         "occupy": aa.OCCUPY in unit.actions, "move": aa.MOVE in unit.actions,
                         "on_objective": unit.cur_hex in objectives})
    canonical = {"config": config, "faction": faction, "kind": component.kind, "shooters": shooters,
                 "objective_outside_control": bool(objectives)}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("ascii")).hexdigest()[:16]
