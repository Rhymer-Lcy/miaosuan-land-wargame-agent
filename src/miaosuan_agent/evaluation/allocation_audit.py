"""Read-only audit of baseline-v2's same-step shoot-target reservation: who owns a contested target, and what
happens to the units it displaces.

Everything is read from one start-of-step seat observation and baseline-v2's own decision on it (its emitted
actions and its trace). Nothing here is a policy: the O-B oracle below runs the frozen baseline-v2 on a modified copy
of the observation to measure a structural alternative, and no agent ever uses it.

Terms. A *candidate* is a shoot option baseline-v2 would consider (well-formed, attack level at least 1). Units are
processed in baseline-v2's order (ascending id). The *reserver* of a target is the unit whose emitted shot at it
came first; baseline-v2 emits at most one shot per target. A *collision group* is one target of one decision for
which at least one later unit had a candidate excluded by the reservation. Its *claimants* are the reserver and the
units whose preferred shoot candidate (their best before exclusion) was that target, i.e. the units the reservation
displaced from it; its *eligible* units are all units with any candidate on it. The attack level is the option's
documented result-table index; it is compared, never converted to damage.

O-B. For a group, the strongest claimant is the one whose best candidate on the target has the highest attack
level, ties broken by the existing deterministic fields (lower weapon id, then processing order). If it is not the
reserver, the oracle withdraws the target's candidates from every unit processed before the strongest claimant and
lets baseline-v2 decide. The group is unambiguous when the only units whose actions change are the reserver and the
strongest claimant, and the strongest claimant then shoots the target; otherwise the change reaches other units and
the group is coupled (ambiguous for a simple local rule).
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import Observation, Origin
from ..decision import Memory
from ..decision.candidates import move_candidates
from ..decision.context import build_context
from .shoot_counterfactual import is_candidate_option

SHOOT, OCCUPY, MOVE = 2, 5, 1
SUPPORTED_TYPES = (MOVE, SHOOT, OCCUPY)
FALLBACK = {"alternate-target": "F1 alternate shoot", "fallback-occupy": "F2 occupy", "fallback-move": "F3 move",
            "fallback-none": "F4 no-op"}
#: The fixed short horizons of the follow-up (steps after the decision), declared before the audit ran.
HORIZONS = (1, 2, 5)
#: Below this many reconstructable collision groups the audit is blocked by insufficient replay evidence.
MIN_GROUPS = 30


def candidates(raw: Mapping[str, Any], origin: Origin = Origin.ENGINE) -> Dict[int, List[Tuple[int, int, int]]]:
    """unit -> its shoot candidates (target, weapon, attack level), from the observation's valid_actions."""
    result: Dict[int, List[Tuple[int, int, int]]] = {}
    for unit, actions in Observation.from_raw(raw, origin).valid_actions().items():
        options = actions.get(SHOOT) or ()
        found = [(o["target_obj_id"], o["weapon_id"], o["attack_level"]) for o in options if is_candidate_option(o)]
        if found:
            result[unit] = found
    return result


def best_on(options: Sequence[Tuple[int, int, int]], target: int) -> Optional[Tuple[int, int, int]]:
    """A unit's best candidate on ``target`` by baseline-v2's ranking (highest level, then lower weapon)."""
    on = [o for o in options if o[0] == target]
    return min(on, key=lambda o: (-o[2], o[1])) if on else None


def preferred_target(options: Sequence[Tuple[int, int, int]]) -> int:
    """The target of a unit's best candidate before any exclusion (baseline-v2's rank: level, target, weapon).
    baseline-v2 records it in the unit's detail only when the unit still selects an action, so it is derived."""
    return min(options, key=lambda o: (-o[2], o[0], o[1]))[0]


@dataclass
class Group:
    target: int
    reserver: int
    reserver_level: int
    reserver_weapon: int
    claimants: List[Dict[str, Any]] = field(default_factory=list)  # reserver first, then displaced units in order
    eligible: List[Dict[str, Any]] = field(default_factory=list)
    displaced: List[int] = field(default_factory=list)
    excluded_other: List[int] = field(default_factory=list)  # options on this target excluded, preferred elsewhere

    def metrics(self) -> Dict[str, Any]:
        levels = [c["level"] for c in self.claimants]
        stronger = [c for c in self.claimants[1:] if c["level"] > self.reserver_level]
        top = max(levels)
        eligible_top = max(e["level"] for e in self.eligible)
        return {"claimants": len(self.claimants), "eligible": len(self.eligible), "displaced": len(self.displaced),
                "excluded_other": len(self.excluded_other), "reserver_level": self.reserver_level,
                "max_claimant_level": top, "max_eligible_level": eligible_top,
                "reserver_is_max_claimant": self.reserver_level == top,
                "reserver_rank": 1 + sum(1 for value in sorted(set(levels), reverse=True) if value > self.reserver_level),
                "stronger_displaced": len(stronger), "level_gap": top - self.reserver_level,
                "tie_at_max": sum(1 for value in levels if value == top) > 1,
                "stronger_eligible_non_claimant": sum(1 for e in self.eligible if not e["claimant"]
                                                      and e["level"] > self.reserver_level)}


def collision_groups(raw: Mapping[str, Any], decision: Any, origin: Origin = Origin.ENGINE) -> List[Group]:
    """Every collision group of one baseline-v2 decision, from its own trace and the observation."""
    payload = decision.trace.to_dict()
    records = {e["obj_id"]: e for e in payload.get("shoot_reserved", [])}
    if not records:
        return []
    order = [u.obj_id for u in decision.trace.units]
    position = {unit: i for i, unit in enumerate(order)}
    options = candidates(raw, origin)
    reserver = {e["target_obj_id"]: e["reserved_by"] for record in records.values() for e in record["excluded"]}
    preferred = {u: preferred_target(options[u]) for u in records if records[u]["effect"] != "unchanged"}
    groups = []
    for target in sorted(reserver, key=lambda t: position[reserver[t]]):
        owner = reserver[target]
        _, weapon, level = best_on(options[owner], target)
        group = Group(target, owner, level, weapon)
        group.claimants.append({"unit": owner, "level": level, "weapon": weapon, "order": position[owner]})
        for unit in order:
            best = best_on(options.get(unit, ()), target)
            if best is None:
                continue
            claimant = unit == owner or preferred.get(unit) == target
            group.eligible.append({"unit": unit, "level": best[2], "weapon": best[1], "order": position[unit],
                                   "claimant": claimant})
            if unit != owner and preferred.get(unit) == target:
                group.claimants.append({"unit": unit, "level": best[2], "weapon": best[1], "order": position[unit]})
                group.displaced.append(unit)
            elif unit in records and any(e["target_obj_id"] == target for e in records[unit]["excluded"]):
                group.excluded_other.append(unit)
        groups.append(group)
    return groups


def inconsistencies(raw: Mapping[str, Any], decision: Any, origin: Origin = Origin.ENGINE) -> List[str]:
    """Disagreements between the reconstruction above and baseline-v2's own records (expected: none)."""
    payload = decision.trace.to_dict()
    records = {e["obj_id"]: e for e in payload.get("shoot_reserved", [])}
    options = candidates(raw, origin)
    units = {u.obj_id: u for u in decision.trace.units}
    shots = {a["obj_id"]: (a["target_obj_id"], a["weapon_id"]) for a in decision.actions if int(a["type"]) == SHOOT}
    problems = []
    for unit, record in records.items():
        excluded = {(e["target_obj_id"], e["weapon_id"], e["attack_level"]) for e in record["excluded"]}
        if not excluded <= set(options.get(unit, ())):
            problems.append("an excluded option is not a candidate in the observation")
        displaced = record["effect"] != "unchanged"
        if displaced != (preferred_target(options[unit]) in {e[0] for e in excluded}):
            problems.append("the derived preferred target disagrees with the recorded effect")
        recorded = dict(units[unit].detail).get("shoot_target_reserved")
        if recorded is not None and recorded != preferred_target(options[unit]):
            problems.append("the derived preferred target disagrees with the recorded one")
        if displaced and (record["effect"] == "fallback-none") != (units[unit].action_type is None):
            problems.append("the recorded effect disagrees with the unit's selection")
        for e in record["excluded"]:
            owner = e["reserved_by"]
            if owner in shots and shots[owner][0] == e["target_obj_id"]:
                if shots[owner][1] != best_on(options[owner], e["target_obj_id"])[1]:
                    problems.append("the reserving shot is not the reserver's best option on the target")
            else:
                problems.append("the reserver's shot at the target was not emitted")
    return problems


def strongest(group: Group) -> Dict[str, Any]:
    return min(group.claimants, key=lambda c: (-c["level"], c["weapon"], c["order"]))


def withdraw_target(raw: Mapping[str, Any], target: int, units: Set[int]) -> Dict[str, Any]:
    """A copy without ``target``'s candidates for ``units`` (the shoot type stays listed)."""
    result = copy.deepcopy(dict(raw))
    for key, per_unit in result["valid_actions"].items():
        if int(key) not in units:
            continue
        for action_key in [k for k in per_unit if int(k) == SHOOT]:
            options = per_unit[action_key]
            if isinstance(options, list):
                per_unit[action_key] = [o for o in options if not (is_candidate_option(o) and o["target_obj_id"] == target)]
    return result


def oracle_b(raw: Mapping[str, Any], seat: int, faction: int, decision: Any, group: Group, policy_factory: Any,
             memory: Memory, origin: Origin = Origin.ENGINE) -> Dict[str, Any]:
    """The O-B measurement of one group (see the module docstring)."""
    top = strongest(group)
    if top["unit"] == group.reserver:
        return {"owner_changed": False}
    before = {u.obj_id for u in decision.trace.units[:top["order"]]}
    other = policy_factory().decide(Observation.from_raw(withdraw_target(raw, group.target, before), origin), seat,
                                    faction, memory)
    old = {a.get("obj_id", "seat"): dict(a) for a in decision.actions}
    new = {a.get("obj_id", "seat"): dict(a) for a in other.actions}
    changed = sorted((k for k in set(old) | set(new) if old.get(k) != new.get(k)), key=str)
    promoted = new.get(top["unit"])
    unambiguous = (set(changed) <= {group.reserver, top["unit"]} and promoted is not None
                   and int(promoted["type"]) == SHOOT and promoted["target_obj_id"] == group.target)
    former = new.get(group.reserver)
    former_kind = ("none" if former is None else {SHOOT: "alternate shoot", OCCUPY: "occupy", MOVE: "move"}.get(
        int(former["type"]), "other"))
    shots_old = sum(1 for a in decision.actions if int(a["type"]) == SHOOT)
    shots_new = sum(1 for a in other.actions if int(a["type"]) == SHOOT)
    return {"owner_changed": True, "unambiguous": unambiguous, "changed_units": len(changed),
            "promoted_level_gain": top["level"] - group.reserver_level,
            "promoted_by": "higher attack level" if top["level"] > group.reserver_level else "weapon tie-break",
            "former_owner": former_kind, "shot_delta": shots_new - shots_old,
            "non_shoot_changes": sum(1 for k in changed if (old.get(k) and int(old[k]["type"]) != SHOOT)
                                     or (new.get(k) and int(new[k]["type"]) != SHOOT)),
            "promoted_previous": "none" if old.get(top["unit"]) is None else
            {SHOOT: "alternate shoot", OCCUPY: "occupy", MOVE: "move"}.get(int(old[top["unit"]]["type"]), "other")}


def components(groups: Sequence[Group]) -> List[Dict[str, int]]:
    """Coupled components of one decision's groups: groups sharing an eligible unit are connected."""
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: Dict[int, int] = {}
    for i, group in enumerate(groups):
        for e in group.eligible:
            if e["unit"] in owner:
                parent[find(i)] = find(owner[e["unit"]])
            else:
                owner[e["unit"]] = i
    members: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(groups)):
        members[find(i)].append(i)
    return [{"targets": len(idx), "shooters": len({e["unit"] for i in idx for e in groups[i].eligible})}
            for idx in members.values()]


MOVE_REASON = re.compile(r"move: (.*)$")


def no_op_reasons(raw: Mapping[str, Any], seat: int, faction: int, decision: Any, unit: int, router: Any,
                  origin: Origin = Origin.ENGINE) -> Dict[str, Any]:
    """Factual reasons a displaced unit did nothing, and whether a supported action was available after all."""
    payload = decision.trace.to_dict()
    record = next(e for e in payload["shoot_reserved"] if e["obj_id"] == unit)
    trace_unit = next(u for u in decision.trace.units if u.obj_id == unit)
    observation = Observation.from_raw(raw, origin)
    listed = dict(observation.valid_actions().get(unit, {}))
    options = candidates(raw, origin).get(unit, [])
    order = [u.obj_id for u in decision.trace.units]
    reserved_before: Set[int] = set()
    for a in decision.actions:
        if int(a["type"]) == SHOOT and order.index(a["obj_id"]) < order.index(unit):
            reserved_before.add(a["target_obj_id"])
    reserved_before |= {e["target_obj_id"] for e in record["excluded"]}
    free = [o for o in options if o[0] not in reserved_before]
    shootable = {o[0] for o in options}
    suppressed = any(s["obj_id"] == unit for s in payload.get("suppressed", []))
    context = build_context(observation, seat, faction)
    if router is not None and hasattr(router, "targets"):
        router.targets = frozenset(city.coord for city in context.objectives)  # as baseline-v2 sets it
    unit_context = next(u for u in context.units if u.obj_id == unit)
    moves, move_reason = move_candidates(unit_context, context, router)
    reasons = {
        "shoot": "its only shootable target was reserved" if len(shootable) == 1 else "every shootable target was reserved",
        "occupy": ("not listed" if OCCUPY not in listed else "suppressed by the same-step objective reservation"
                   if suppressed else "listed and not suppressed"),
        "move": move_reason or "a move candidate existed",
        "trace_move_reason": (MOVE_REASON.search(trace_unit.no_op_reason or "") or [None, None])[1],
        "unsupported_types": sorted(t for t in listed if t not in SUPPORTED_TYPES),
    }
    defect = bool(free) or (OCCUPY in listed and not suppressed) or bool(moves)
    return {"reasons": reasons, "defect": defect, "free_shoot_candidates": len(free)}
