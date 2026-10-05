"""Sprint 13 offline diagnosis of the T9-v3 primary-scenario failure (``docs/SPRINT13_V3_DIAGNOSIS.md``).

Pure functions over captured decisions; nothing here opens an engine or simulates a game. On one captured decision of
the v3 seat (its own observation and its ``baseline-v2`` memory) :func:`decide_policies` decides ``baseline-v2``,
frozen T9-v1 (and Sprint 10's independent audit of it), frozen T9-v2 and frozen v3, each with a fresh policy instance,
and the three diagnostic oracles of section 7. :func:`classify_orders` partitions every ``baseline-v2`` ground move order
by its T9-v1 and v3 forms (section 4). The rest derives reservation episodes (section 6), prospective features and
their rank statistics (section 7), the 50-step snapshot comparison with Sprint 9 (section 8) and the mechanical
disposition (section 9).

The oracles O1 to O3 are analysis devices, not policies: they exist only in :func:`oracle_allocate`, carry no policy
identity, and are never packaged or placed in a run card. O1 uses future information on purpose.

Rows produced here carry unit ids and hexes; they stay in private files. :func:`public_check` refuses any public
structure with a forbidden key or a planted private value.
"""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import digest, gate
from ..decision.candidates import move_candidates
from ..decision.context import build_context
from ..decision.routing import Router
from ..decision.trace import canonical_json
from ..experiments import t9_batch as tb
from ..experiments.exploratory_addon import AddonMemory, hex_distance, is_int
from ..experiments.shoot_reservation import ShootReservationPolicy
from ..experiments.t9_allocation import DETOUR, AllocationAddon
from ..experiments.t9_staging import StagingAddon
from . import residual516 as rd
from . import t9_diagnostic as td
from .s12_screen import FORBIDDEN_KEYS, privacy_problems

GROUND = (1, 2)
MOVE = 1
SHOOT = 2
CAPACITY = 4
KIND = {1: "infantry", 2: "vehicle"}

KEEP, REDIRECT, STAGE, WITHHOLD = "KEEP", "REDIRECT", "STAGE", "WITHHOLD"
CLASSES = ("CROSS_OBJECTIVE_REDIRECTION_V1_ONLY", "STAGING_VERSUS_REDIRECTION", "WITHHOLDING_VERSUS_REDIRECTION",
           "END_OF_GAME_FEASIBILITY_EXCLUSION", "INCUMBENT_MOVER_DIFFERENCE", "SAME_OBJECTIVE_CAPACITY_SELECTION",
           "STAGING_VERSUS_WITHHOLDING", "OTHER")
LATE = "cannot arrive before the end"
FULL = "no place under capacity"
INTERVALS = ((0, 99), (100, 499), (500, 1499), (1500, None))
ORACLES = ("O1", "O2", "O3")
LABELS = ("REDISTRIBUTION_DOMINANT", "RESERVATION_LIFETIME_DOMINANT", "BOTH_MECHANISMS_MATERIAL",
          "INSUFFICIENT_FOR_REVISION")

#: Registered thresholds (section 9 and section 7 of the protocol).
RULE = {"a_min_units": 4, "a_min_share": 0.25, "b_min_units": 4, "b_min_share": 0.10, "games_needed": 3,
        "overlap_max": 0.5, "ratio": 0.25, "auc_high": 0.70, "auc_low": 0.30, "auc_min_per_class": 3,
        "char_own": 12, "char_not_own": 3, "t9v1_games_per_seat": 15}


def interval(k: int) -> str:
    for low, high in INTERVALS:
        if k >= low and (high is None or k <= high):
            return f"{low}-{'end' if high is None else high}"
    raise ValueError(k)


def own_ground(observation: Observation, faction: int) -> Dict[int, Any]:
    return {u.obj_id: u for u in observation.operators() if u.color == faction and u.unit_type in GROUND}


def ground_moves(actions: Iterable[Mapping[str, Any]], ground: Mapping[int, Any]) -> Dict[int, Mapping[str, Any]]:
    return {a["obj_id"]: a for a in actions if a.get("type") == MOVE and a.get("obj_id") in ground}


def free_flow(router: Router, unit: Any, path: Sequence[int], skip_first: bool = False) -> Optional[int]:
    times, _ = tb.path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"), unit.cur_hex,
                             path)
    if times is None:
        return None
    return sum(times[1:] if skip_first else times)


# ------------------------------------------------------------------------------------------------
# Oracle allocator (section 7): t9_batch.allocate, optionally with O1's exclusion and O2's redirection.


@dataclass
class OracleAllocation:
    actions: Tuple[Mapping[str, Any], ...]
    selected: Dict[int, int] = field(default_factory=dict)
    staged: Dict[int, Tuple[int, ...]] = field(default_factory=dict)
    withheld: Dict[int, str] = field(default_factory=dict)
    redirected: Dict[int, Tuple[int, int]] = field(default_factory=dict)  # unit -> (from, to)
    claimants: Dict[int, tb.Claimant] = field(default_factory=dict)
    objectives: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    redirect_infeasible: int = 0  # T9-v1 alternatives dropped by the end-of-game test


def counted_incumbents(observation: Observation, faction: int, router: Router,
                       exclude: FrozenSet[int] = frozenset()) -> Tuple[Dict[int, Dict[str, Any]], collections.Counter]:
    """Per objective: physical incumbents, counted movers (with their remaining bound), phantom movers (cannot arrive
    before the end) and movers excluded by O1; and the endpoint count of every own ground unit. The same counting as
    ``t9_batch._allocate``."""
    time_info = observation.time()
    end = time_info.max_step if is_int(time_info.max_step) else None
    now = time_info.cur_step
    cities = {c.coord for c in (observation.cities() or ())}
    rows = {coord: {"physical": 0, "movers": 0, "phantom": 0, "excluded": 0, "mover_bounds": {}, "phantoms": [],
                    "excluded_units": []} for coord in cities}
    endpoints: collections.Counter = collections.Counter()
    for unit in own_ground(observation, faction).values():
        path = tuple(unit.move_path or ())
        stop = path[-1] if path else unit.cur_hex
        endpoints[stop] += 1
        if stop not in cities:
            continue
        row = rows[stop]
        if not path:
            row["physical"] += 1
            continue
        bound = free_flow(router, unit, path, skip_first=True)
        if bound is not None and end is not None and now + bound >= end:
            row["phantom"] += 1
            row["phantoms"].append(unit.obj_id)
        elif unit.obj_id in exclude:
            row["excluded"] += 1
            row["excluded_units"].append(unit.obj_id)
        else:
            row["movers"] += 1
            row["mover_bounds"][unit.obj_id] = bound
    return rows, endpoints


def _v1_alternative(unit_id: int, own_dest: int, context: Any, router: Router, unheld: Mapping[int, Any],
                    counted: Mapping[int, int], seat: int, ground: Mapping[int, Any], now: int,
                    end: Optional[int]) -> Tuple[Optional[Tuple[Mapping[str, Any], int]], int]:
    """T9-v1's alternative objective for one unit (cost at most DETOUR times the cost to its own objective, smallest
    cost / value, then cost, then hex) among objectives not own with fewer than CAPACITY places counted, and whose
    free-flow arrival comes before the end; returns (action, objective) or None, and the number of alternatives
    dropped only by the end-of-game test."""
    unit_ctx = context.unit(unit_id)
    if unit_ctx is None:
        return None, 0
    candidates, _ = move_candidates(unit_ctx, context, router)
    costs = {dict(c.detail)["destination"]: dict(c.detail)["cost"] for c in candidates}
    base_cost = costs.get(own_dest)
    options, infeasible = [], 0
    for candidate in candidates:
        detail = dict(candidate.detail)
        coord, cost = detail["destination"], detail["cost"]
        if coord == own_dest or coord not in unheld or counted.get(coord, 0) >= CAPACITY:
            continue
        if base_cost is None or cost > DETOUR * base_cost:
            continue
        action = candidate.action(seat)
        ff = free_flow(router, ground[unit_id], list(action["move_path"]))
        if ff is None or (end is not None and now + ff >= end):
            infeasible += 1
            continue
        value = unheld[coord].value
        weight = value if is_int(value) and value > 0 else 1
        options.append(((cost / weight, cost, coord), action, coord))
    if not options:
        return None, infeasible
    _, action, coord = min(options, key=lambda option: option[0])
    return (action, coord), infeasible


def oracle_allocate(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
                    router: Router, *, exclude: FrozenSet[int] = frozenset(), redirect: bool = False) -> OracleAllocation:
    """``t9_batch.allocate`` re-stated for analysis. With ``exclude`` empty and ``redirect`` False it must return the
    same actions, selected, staged and withheld sets (checked at every decision). ``exclude`` (O1): counted movers that
    hold no place. ``redirect`` (O2): claimants that find their objective full go, in rank order, to T9-v1's
    alternative counted the v3 way; with none they are staged or withheld as by v3. Exceptions propagate."""
    actions = tuple(actions)
    out = OracleAllocation(actions)
    if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
        return out
    context = build_context(observation, seat, faction)
    time_info = observation.time()
    end = time_info.max_step if is_int(time_info.max_step) else None
    now = time_info.cur_step
    cities = {c.coord for c in (observation.cities() or ())}
    ground = own_ground(observation, faction)
    rows, endpoints = counted_incumbents(observation, faction, router, exclude)
    claimants: Dict[int, tb.Claimant] = {}
    for index, action in enumerate(actions):
        obj_id = action.get("obj_id")
        if action.get("type") != MOVE or obj_id not in ground:
            continue
        dest = tb.destination(action)
        if dest is None or dest not in cities:
            continue
        unit = ground[obj_id]
        path = tuple(action["move_path"])
        times, cost = tb.path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"),
                                    unit.cur_hex, path)
        ff = None if times is None else sum(times)
        if ff is None:
            status = "free-flow time unreadable"
        elif end is not None and now + ff >= end:
            status = LATE
        else:
            status = FULL
        claimants[obj_id] = tb.Claimant(obj_id, dest, path, ff, cost, status == FULL, index, status)
    out.claimants = claimants
    by_objective: Dict[int, List[tb.Claimant]] = collections.defaultdict(list)
    for claimant in claimants.values():
        by_objective[claimant.objective].append(claimant)
    counted = {coord: row["physical"] + row["movers"] for coord, row in rows.items()}
    for coord, group in sorted(by_objective.items()):
        row = rows[coord]
        free = CAPACITY - row["physical"] - row["movers"]
        ranked = sorted(group, key=tb.free_flow_key)
        chosen = [c for c in ranked if c.feasible][:max(free, 0)]
        for claimant in chosen:
            out.selected[claimant.obj_id] = coord
            counted[coord] += 1
        out.objectives[coord] = {"physical": row["physical"], "movers": row["movers"], "phantom": row["phantom"],
                                 "excluded": row["excluded"], "free": free, "claimants": len(group),
                                 "selected": [c.obj_id for c in chosen]}
    unheld = {city.coord: city for city in context.objectives}
    replacements: Dict[int, Dict[str, Any]] = {}
    for claimant in sorted((c for c in claimants.values() if c.obj_id not in out.selected), key=tb.free_flow_key):
        if redirect and claimant.feasible:
            choice, dropped = _v1_alternative(claimant.obj_id, claimant.objective, context, router, unheld, counted,
                                              seat, ground, now, end)
            out.redirect_infeasible += dropped
            if choice is not None:
                action, coord = choice
                counted[coord] = counted.get(coord, 0) + 1
                out.redirected[claimant.obj_id] = (claimant.objective, coord)
                replacements[claimant.obj_id] = dict(action)
                continue
        target = None
        for position in range(len(claimant.path) - 2, -1, -1):
            hex_ = claimant.path[position]
            if hex_ not in cities and endpoints[hex_] < tb.STAGE_CAP:
                target = position
                break
        if target is None:
            out.withheld[claimant.obj_id] = claimant.status
            continue
        staged_path = claimant.path[:target + 1]
        endpoints[staged_path[-1]] += 1
        out.staged[claimant.obj_id] = staged_path
        replacement = dict(actions[claimant.index])
        replacement["move_path"] = list(staged_path)
        replacements[claimant.obj_id] = replacement
    final: List[Optional[Mapping[str, Any]]] = []
    for action in actions:
        obj_id = action.get("obj_id")
        if action.get("type") == MOVE and obj_id in claimants and obj_id not in out.selected:
            final.append(replacements.get(obj_id))
        else:
            final.append(action)
    checked = gate.check([a for a in final if a is not None], context, router)
    rejected = {r.obj_id for r in checked.rejected}
    for position, action in enumerate(final):
        if action is None:
            continue
        obj_id = action.get("obj_id")
        if obj_id in replacements and obj_id in rejected:
            final[position] = None
            redirected = out.redirected.pop(obj_id, None)
            out.staged.pop(obj_id, None)
            out.withheld[obj_id] = ("redirect rejected by the gate" if redirected is not None
                                    else "staged move rejected by the gate")
    out.actions = tuple(a for a in final if a is not None)
    return out


# ------------------------------------------------------------------------------------------------
# T9-v1 with chosen incumbents left out (the INCUMBENT_MOVER_DIFFERENCE test of section 4)


def v1_outcomes(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
                router: Router, exclude: FrozenSet[int] = frozenset()) -> Dict[int, str]:
    """T9-v1's per-unit outcome (keep / replace / withhold) with the units in ``exclude`` left out of the initial
    commitments; with ``exclude`` empty it equals the frozen add-on's outcomes before the gate (checked)."""
    if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
        return {}
    context = build_context(observation, seat, faction)
    cities = {city.coord: city for city in (observation.cities() or ())}
    unheld = {city.coord: city for city in context.objectives}
    kinds = {u.obj_id: u.fields.get("type") for u in observation.operators() if u.color == faction}
    commitments: collections.Counter = collections.Counter()
    for unit in observation.operators():
        if unit.color != faction or unit.fields.get("type") not in GROUND or unit.obj_id in exclude:
            continue
        path = unit.move_path or ()
        stop = path[-1] if path else unit.cur_hex
        if stop in cities:
            commitments[stop] += 1
    out: Dict[int, str] = {}
    for action in actions:
        if action.get("type") != MOVE or kinds.get(action.get("obj_id")) not in GROUND:
            continue
        dest = tb.destination(action)
        if dest is None or commitments[dest] < CAPACITY:
            if dest is not None:
                commitments[dest] += 1
            out[action["obj_id"]] = "keep"
            continue
        unit = context.unit(action["obj_id"])
        candidates, _ = move_candidates(unit, context, router) if unit is not None else ([], "not a unit")
        costs = {dict(c.detail)["destination"]: dict(c.detail)["cost"] for c in candidates}
        base_cost = costs.get(dest)
        options = []
        for candidate in candidates:
            detail = dict(candidate.detail)
            coord, cost = detail["destination"], detail["cost"]
            if coord == dest or coord not in unheld or commitments[coord] >= CAPACITY:
                continue
            if base_cost is None or cost > DETOUR * base_cost:
                continue
            value = unheld[coord].value
            weight = value if is_int(value) and value > 0 else 1
            options.append(((cost / weight, cost, coord), coord))
        if not options:
            out[action["obj_id"]] = "withhold"
            continue
        coord = min(options)[1]
        commitments[coord] += 1
        out[action["obj_id"]] = "replace"
    return out


# ------------------------------------------------------------------------------------------------
# One decision, every policy (section 3)


def _fresh(costs: MoveCosts, observation: Observation, seat: int, faction: int, memory: Any):
    policy = ShootReservationPolicy(costs)
    return policy, policy.decide(observation, seat, faction, memory)


def decide_policies(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts,
                    doomed: Callable[[Mapping[int, Dict[str, Any]]], FrozenSet[int]] = lambda rows: frozenset()
                    ) -> Dict[str, Any]:
    """Every policy and oracle on one captured decision. ``doomed(rows)`` names, from the counted incumbents, the
    movers O1 treats as holding no place (the caller labels them from the timeline)."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory = memory.baseline if isinstance(memory, AddonMemory) else memory
    p0, b0 = _fresh(costs, observation, seat, faction, base_memory)
    out: Dict[str, Any] = {"observation": observation, "baseline": tuple(b0.actions),
                           "baseline_trace_sha256": digest(b0.trace),
                           "play": observation.time().stage == Stage.PLAY}
    ground = own_ground(observation, faction)
    if not out["play"] or not ground_moves(b0.actions, ground):
        for name in ("t9-v1", "t9-v2", "t9-v3", "O1", "O2", "O3", "identity"):
            out[name] = tuple(b0.actions)
        out["active"] = False
        return out
    out["active"] = True
    p1, b1 = _fresh(costs, observation, seat, faction, base_memory)
    v1 = AllocationAddon(costs, p1).apply(observation, seat, faction, b1, ())
    out["t9-v1"], out["t9-v1_changes"] = tuple(v1.actions), tuple(canonical_json(dict(c)) for c in v1.changes)
    pa, ba = _fresh(costs, observation, seat, faction, base_memory)
    audit = td.audit_allocation(observation, seat, faction, ba.actions, pa)
    out["audit"] = audit
    p2, b2 = _fresh(costs, observation, seat, faction, base_memory)
    out["t9-v2"] = tuple(StagingAddon(costs, p2).apply(observation, seat, faction, b2, ()).actions)
    p3, b3 = _fresh(costs, observation, seat, faction, base_memory)
    v3 = tb.allocate(observation, seat, faction, b3.actions, p3.router)
    out["t9-v3"], out["allocation"] = tuple(v3.actions), v3
    po, bo = _fresh(costs, observation, seat, faction, base_memory)
    rows, _ = counted_incumbents(observation, faction, po.router)
    out["incumbents"] = rows
    identity = oracle_allocate(observation, seat, faction, bo.actions, po.router)
    out["identity"], out["identity_allocation"] = identity.actions, identity
    excluded = frozenset(doomed(rows))
    out["doomed"] = excluded
    for name, options in (("O1", {"exclude": excluded}), ("O2", {"redirect": True}),
                          ("O3", {"exclude": excluded, "redirect": True})):
        pn, bn = _fresh(costs, observation, seat, faction, base_memory)
        allocation = oracle_allocate(observation, seat, faction, bn.actions, pn.router, **options)
        out[name], out[f"{name}_allocation"] = allocation.actions, allocation
    pv, bv = _fresh(costs, observation, seat, faction, base_memory)
    out["v1_outcomes"] = v1_outcomes(observation, seat, faction, bv.actions, pv.router)
    phantoms = frozenset(u for row in rows.values() for u in row["phantoms"])
    pw, bw = _fresh(costs, observation, seat, faction, base_memory)
    out["v1_outcomes_v3_count"] = v1_outcomes(observation, seat, faction, bw.actions, pw.router, phantoms)
    return out


def verify(decided: Mapping[str, Any], captured_row: Mapping[str, Any], submitted: Sequence[Mapping[str, Any]]
           ) -> List[str]:
    """Section 3 checks of one decision; an empty list means every check passed."""
    problems = []
    if rd.plain(decided["baseline"]) != captured_row["baseline_actions"]:
        problems.append("baseline-v2 actions differ from the capture")
    if decided["baseline_trace_sha256"] != captured_row["baseline_trace_sha256"]:
        problems.append("baseline-v2 trace digest differs from the capture")
    if rd.plain(decided["t9-v3"]) != rd.plain(list(submitted)):
        problems.append("v3 actions differ from the submitted actions")
    if rd.plain(decided["identity"]) != rd.plain(decided["t9-v3"]):
        problems.append("the oracle allocator without modifications differs from v3")
    if decided["active"]:
        captured = captured_row["allocation"]
        allocation = decided["allocation"]
        if {str(u): c for u, c in allocation.selected.items()} != captured["selected"]:
            problems.append("v3 selection differs from the capture")
        if {str(u): list(p) for u, p in allocation.staged.items()} != captured["staged"]:
            problems.append("v3 staging differs from the capture")
        if {str(u): r for u, r in allocation.withheld.items()} != captured["withheld"]:
            problems.append("v3 withholding differs from the capture")
        identity = decided["identity_allocation"]
        if (identity.selected != allocation.selected or identity.staged != allocation.staged
                or identity.withheld != allocation.withheld):
            problems.append("the oracle allocator's sets differ from v3's")
        audit = decided["audit"]
        if rd.plain(audit.actions) != rd.plain(decided["t9-v1"]):
            problems.append("the Sprint 10 audit's T9-v1 actions differ from the frozen add-on")
        if tuple(canonical_json(dict(c)) for c in audit.changes) != decided["t9-v1_changes"]:
            problems.append("the Sprint 10 audit's T9-v1 changes differ from the frozen add-on")
        pre_gate = {m["obj_id"]: ("keep" if m["outcome"] in ("keep", "revert") else m["outcome"])
                    for m in audit.moves}
        reverted = {m["obj_id"] for m in audit.moves if m["outcome"] == "revert"}
        restated = {u: ("keep" if u in reverted else o) for u, o in decided["v1_outcomes"].items()}
        if restated != pre_gate:
            problems.append("the restated T9-v1 rule differs from the frozen add-on")
    return problems


# ------------------------------------------------------------------------------------------------
# Order classification (section 4)


def unit_forms(decided: Mapping[str, Any], faction: int) -> List[Dict[str, Any]]:
    """One row per baseline-v2 ground move order of an active decision: each policy's form, and the class."""
    observation = decided["observation"]
    ground = own_ground(observation, faction)
    cities = {c.coord: c for c in (observation.cities() or ())}
    base = ground_moves(decided["baseline"], ground)
    audit_rows = {m["obj_id"]: m for m in decided["audit"].moves}
    allocation = decided["allocation"]
    rows_inc = decided["incumbents"]
    emitted = {name: ground_moves(decided[name], ground) for name in ("t9-v1", "t9-v2", "t9-v3", "O1", "O2", "O3")}
    rows = []
    for unit_id, action in base.items():
        dest = tb.destination(action)
        audit = audit_rows.get(unit_id, {})
        v1_outcome = audit.get("outcome", "keep")
        v1_form = {"keep": KEEP, "revert": KEEP, "replace": REDIRECT, "withhold": WITHHOLD}[v1_outcome]
        if unit_id in allocation.selected or unit_id not in allocation.claimants:
            v3_form = KEEP
        elif unit_id in allocation.staged:
            v3_form = STAGE
        else:
            v3_form = WITHHOLD
        claimant = allocation.claimants.get(unit_id)
        v3_reason = None if v3_form == KEEP else (claimant.status if claimant else None)
        if v3_form == WITHHOLD and allocation.withheld.get(unit_id) == "staged move rejected by the gate":
            v3_reason = "staged move rejected by the gate"
        same = dict(emitted["t9-v1"].get(unit_id) or {}) == dict(emitted["t9-v3"].get(unit_id) or {}) and (
            (unit_id in emitted["t9-v1"]) == (unit_id in emitted["t9-v3"]))
        klass = None if same else classify(v1_form, v3_form, v3_reason,
                                            decided["v1_outcomes_v3_count"].get(unit_id))
        phantom_at_dest = rows_inc.get(dest, {}).get("phantom", 0) if dest in cities else 0
        before = audit.get("destination_commitments_before")
        cause = None
        if v1_form == REDIRECT:
            cause = "PHANTOM_INCUMBENTS" if (before is not None and before - phantom_at_dest < CAPACITY) else "CAPACITY"
        forms = {}
        for name in ("t9-v2", "O1", "O2", "O3"):
            forms[name] = _form(name, unit_id, action, emitted[name].get(unit_id), decided, cities)
        rows.append({"unit": unit_id, "destination": dest, "objective": dest in cities, "v1": v1_form, "v3": v3_form,
                     "v3_reason": v3_reason, "class": klass, "cause": cause,
                     "v1_to": audit.get("chosen_destination") if v1_outcome == "replace" else None,
                     "v1_count_before": before, "phantom_at_destination": phantom_at_dest,
                     "free_flow": claimant.free_flow if claimant else None, **{f"form_{k}": v for k, v in forms.items()}})
    return rows


def _form(name: str, unit_id: int, base: Mapping[str, Any], emitted: Optional[Mapping[str, Any]],
          decided: Mapping[str, Any], cities: Mapping[int, Any]) -> str:
    if emitted is None:
        return WITHHOLD
    if dict(emitted) == dict(base):
        return KEEP
    path = list(emitted["move_path"])
    if path and path[-1] in cities and path[-1] != base["move_path"][-1]:
        return REDIRECT
    return STAGE


def classify(v1_form: str, v3_form: str, v3_reason: Optional[str], v1_with_v3_count: Optional[str]) -> str:
    """Section 4's class of one differing order (taken in order)."""
    if v1_form == REDIRECT:
        return {KEEP: CLASSES[0], STAGE: CLASSES[1], WITHHOLD: CLASSES[2]}[v3_form]
    if v1_form == KEEP and v3_form in (STAGE, WITHHOLD) and v3_reason == LATE:
        return CLASSES[3]
    if v1_form == WITHHOLD and v3_form == KEEP and v1_with_v3_count == "keep":
        return CLASSES[4]
    if (v1_form == KEEP and v3_form in (STAGE, WITHHOLD)) or (v1_form == WITHHOLD and v3_form == KEEP):
        return CLASSES[5]
    if v1_form == WITHHOLD and v3_form == STAGE:
        return CLASSES[6]
    return CLASSES[7]


# ------------------------------------------------------------------------------------------------
# Reservation episodes (section 6)


def holder_fate(unit: int, objective: Any, start: int, stood: Callable[[int, Any, int], Optional[int]],
                lost_at: Mapping[int, Optional[int]]) -> Tuple[str, Optional[int]]:
    """HONOURED (stood on the objective from state ``start`` on), DESTROYED (left the seat's units first; with the
    state index) or ALIVE_NOT_ARRIVED."""
    arrived = stood(unit, objective, start)
    lost = lost_at.get(unit)
    if lost is not None and lost >= start and (arrived is None or lost <= arrived):
        return "DESTROYED", lost
    if arrived is not None:
        return "HONOURED", None
    return "ALIVE_NOT_ARRIVED", None


def episodes(counted: Sequence[Mapping[int, Mapping[int, Optional[int]]]],
             selections: Mapping[Tuple[int, Any], Iterable[int]]) -> List[Dict[str, Any]]:
    """Reservation episodes from the per-decision counted movers (``counted[k][objective][unit] = remaining bound``)
    and v3's selections (``(unit, objective) -> decisions``): one episode per maximal run of consecutive decisions in
    which a unit is a counted mover of one objective, starting at its selection when it was selected at the decision
    before the run."""
    out: List[Dict[str, Any]] = []
    open_: Dict[Tuple[int, Any], Dict[str, Any]] = {}
    chosen = {key: set(ks) for key, ks in selections.items()}
    for k, per_objective in enumerate(counted):
        present = {(unit, coord): bound for coord, units in per_objective.items() for unit, bound in units.items()}
        for key in list(open_):
            if key not in present:
                out.append(open_.pop(key))
        for key, bound in present.items():
            row = open_.get(key)
            if row is None:
                selected = k - 1 if (k - 1) in chosen.get(key, ()) else None
                row = {"unit": key[0], "objective": key[1], "selection": selected,
                       "start": k if selected is None else selected, "first_counted": k, "last_counted": k,
                       "bounds": {}}
                open_[key] = row
            row["last_counted"] = k
            row["bounds"][k] = bound
    out.extend(open_.values())
    return sorted(out, key=lambda r: (r["start"], r["objective"], r["unit"]))


# ------------------------------------------------------------------------------------------------
# Prospective features (section 7)


def features(raw: Mapping[str, Any], faction: int, unit_id: int, objective: int, path: Sequence[int],
             free_flow_time: Optional[int], incumbents: int) -> Dict[str, Any]:
    """The registered seat-local features of one selection, from the seat's own observation only."""
    units = {u["obj_id"]: u for u in raw.get("operators") or ()}
    unit = units[unit_id]
    enemy = 1 - faction
    seen = [u for u in units.values() if u.get("color") == enemy]
    seen_hexes = [u["cur_hex"] for u in seen if is_int(u.get("cur_hex"))]
    route = [unit["cur_hex"]] + [h for h in path if is_int(h)]
    nearest = min((hex_distance(unit["cur_hex"], h) for h in seen_hexes), default=None)
    route_min = min((hex_distance(r, h) for r in route for h in seen_hexes), default=None)
    near_route = sum(1 for h in seen_hexes if any(hex_distance(r, h) <= 3 for r in route))
    city = next(c for c in raw.get("cities") or () if c["coord"] == objective)
    contested = city.get("flag") != faction and (city.get("flag") == enemy or any(
        hex_distance(objective, h) <= 2 for h in seen_hexes))
    max_blood = unit.get("max_blood") or 0
    return {"free_flow": free_flow_time, "route_length": len(path), "vehicle": int(unit.get("type") == 2),
            "strength_fraction": (unit.get("blood") or 0) / max_blood if max_blood else None,
            "suppressed": int(bool(unit.get("keep"))), "seen_enemies": len(seen),
            "nearest_seen_enemy": nearest, "route_nearest_seen_enemy": route_min,
            "seen_enemies_near_route": near_route, "contested": int(bool(contested)),
            "objective_value": city.get("value"), "counted_incumbents": incumbents}


FEATURES = ("free_flow", "route_length", "vehicle", "strength_fraction", "suppressed", "seen_enemies",
            "nearest_seen_enemy", "route_nearest_seen_enemy", "seen_enemies_near_route", "contested",
            "objective_value", "counted_incumbents")


def auc(positives: Sequence[float], negatives: Sequence[float]) -> Optional[float]:
    """P(a positive value > a negative value) + 0.5 P(equal); None if either side is empty."""
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(positives) * len(negatives))


def separation(rows: Sequence[Mapping[str, Any]], feature: str, label: str = "lost",
               game_key: str = "game") -> Dict[str, Any]:
    """Pooled and per-game AUC of ``feature`` for ``label``; rows with a missing value are counted, not used. A
    missing value is reported for every game; the separating test uses games with enough of both classes."""
    usable = [r for r in rows if r.get(feature) is not None]
    def split(sub):
        return ([float(r[feature]) for r in sub if r[label]], [float(r[feature]) for r in sub if not r[label]])
    pos, neg = split(usable)
    pooled = auc(pos, neg)
    per_game = {}
    for game in sorted({r[game_key] for r in rows}):
        p, n = split([r for r in usable if r[game_key] == game])
        per_game[game] = {"lost": len(p), "other": len(n), "auc": None if auc(p, n) is None else round(auc(p, n), 4)}
    eligible = [g for g in per_game.values() if g["lost"] >= RULE["auc_min_per_class"]
                and g["other"] >= RULE["auc_min_per_class"]]
    separating = False
    if pooled is not None and (pooled >= RULE["auc_high"] or pooled <= RULE["auc_low"]):
        high = pooled > 0.5
        separating = all(g["auc"] is not None and ((g["auc"] > 0.5) if high else (g["auc"] < 0.5)) for g in eligible)
    return {"pooled_auc": None if pooled is None else round(pooled, 4), "missing": len(rows) - len(usable),
            "per_game": per_game, "eligible_games": len(eligible), "separating": separating}


def quartile_table(rows: Sequence[Mapping[str, Any]], feature: str, label: str = "lost") -> List[Dict[str, Any]]:
    """Conditional counts by pooled quartile (by category for a feature with at most four distinct values)."""
    usable = [r for r in rows if r.get(feature) is not None]
    values = sorted(float(r[feature]) for r in usable)
    if not values:
        return []
    distinct = sorted(set(values))
    if len(distinct) <= 4:
        def bin_of(v: float) -> int:
            return distinct.index(v)
    else:
        cuts = [values[(len(values) * q) // 4] for q in (1, 2, 3)]

        def bin_of(v: float) -> int:
            return sum(1 for c in cuts if v > c)
    groups: Dict[int, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for r in usable:
        groups[bin_of(float(r[feature]))].append(r)
    out = []
    for index in sorted(groups):
        inside = groups[index]
        inside_values = [float(r[feature]) for r in inside]
        out.append({"from": round(min(inside_values), 4), "to": round(max(inside_values), 4),
                    "lost": sum(1 for r in inside if r[label]), "other": sum(1 for r in inside if not r[label])})
    return out


# ------------------------------------------------------------------------------------------------
# Snapshot series and the Sprint 9 comparison (section 8)


def snapshot_series(snapshots: Sequence[Mapping[str, Any]], faction: int, names: Mapping[Any, str]
                    ) -> List[Dict[str, Any]]:
    side = ("red", "blue")[faction]
    out = []
    for snap in sorted(snapshots, key=lambda s: s["k"]):
        own = sorted(names[c] for c, flag in snap["flags"] if flag == faction)
        scores = snap["scores"]
        out.append({"k": snap["k"], "own": own, "margin": scores.get(f"{side}_win"),
                    "attack": scores.get(f"{side}_attack"), "strength": (snap.get("blood") or {}).get(str(faction))})
    return out


def coverage_series(series: Sequence[Mapping[str, Any]]) -> List[Optional[float]]:
    """Cumulative coverage: mean objectives own over the snapshots with k > 0 so far (None at k = 0)."""
    out, total, n = [], 0, 0
    for row in series:
        if row["k"] == 0:
            out.append(None)
            continue
        total += len(row["own"])
        n += 1
        out.append(total / n)
    return out


def stays_below(values: Sequence[Optional[float]], floors: Sequence[Optional[float]]) -> Optional[int]:
    """The first index from which ``values`` is below ``floors`` at every later index; None if there is none."""
    first = None
    for i in range(len(values) - 1, -1, -1):
        v, f = values[i], floors[i]
        if v is None or f is None or not v < f:
            break
        first = i
    return first


def characteristic(population: Sequence[Sequence[Mapping[str, Any]]], labels: Sequence[str]
                   ) -> List[Dict[str, str]]:
    """Per snapshot index: objective label -> "own" (owned in at least 12 of the games) or "not own" (at most 3)."""
    out = []
    for i in range(len(population[0])):
        row = {}
        for label in labels:
            count = sum(1 for game in population if label in game[i]["own"])
            if count >= RULE["char_own"]:
                row[label] = "own"
            elif count <= RULE["char_not_own"]:
                row[label] = "not own"
        out.append(row)
    return out


def first_contradiction(series: Sequence[Mapping[str, Any]], pattern: Sequence[Mapping[str, str]]
                        ) -> Optional[Dict[str, Any]]:
    for i, row in enumerate(series):
        for label, expected in sorted(pattern[i].items()):
            own = label in row["own"]
            if (expected == "own") != own:
                return {"k": row["k"], "objective": label, "expected": expected}
    return None


def placement(value: Optional[float], population: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(v for v in population if v is not None)
    if value is None or not vals:
        return {"value": value, "n": len(vals)}
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return {"value": value, "n": len(vals), "min": vals[0], "median": median, "max": vals[-1],
            "below": sum(1 for v in vals if v < value), "equal": sum(1 for v in vals if v == value)}


def capture_order(series: Sequence[Mapping[str, Any]]) -> List[Tuple[int, str]]:
    first: Dict[str, int] = {}
    for row in series:
        for label in row["own"]:
            first.setdefault(label, row["k"])
    return sorted((k, label) for label, k in first.items())


# ------------------------------------------------------------------------------------------------
# Disposition (section 9)


def game_materiality(a: Mapping[str, Any], b: Mapping[str, Any], divergence_step: Optional[int]) -> Dict[str, Any]:
    """Per game: whether A and B are material. ``a``: distinct redirected units (``distinct_redirected``), redirects,
    T9-v1 emitted ground moves, first redirect step. ``b``: distinct admitted claimants (``distinct_admitted``),
    admitted claimant-decisions, v3 held-back selectable claimant-decisions, first admission step."""
    def before(step):
        return step is not None and (divergence_step is None or step < divergence_step)
    a_share = a["redirects"] / a["v1_emitted_ground"] if a["v1_emitted_ground"] else 0.0
    b_share = b["admitted_decisions"] / b["held_selectable"] if b["held_selectable"] else 0.0
    return {"a_material": a["distinct_redirected"] >= RULE["a_min_units"] and a_share >= RULE["a_min_share"]
            and before(a["first_step"]),
            "a_share": round(a_share, 4),
            "b_material": b["distinct_admitted"] >= RULE["b_min_units"] and b_share >= RULE["b_min_share"]
            and before(b["first_step"]),
            "b_share": round(b_share, 4)}


def disposition(games: Mapping[str, Mapping[str, Any]], seats: Mapping[str, str], overlap: float, sa: int, sb: int,
                prospective: bool) -> Dict[str, Any]:
    """The registered rule. ``games``: per game the output of :func:`game_materiality`; ``seats``: game -> H1 / H2."""
    def material(key):
        hit = [g for g, row in games.items() if row[key]]
        return len(hit) >= RULE["games_needed"] and {seats[g] for g in hit} >= {"H1", "H2"}, len(hit)

    a, na = material("a_material")
    b, nb = material("b_material")
    reservation = "RESERVATION_LIFETIME_DOMINANT" if prospective else "INSUFFICIENT_FOR_REVISION"
    if not a and not b:
        label, rule = "INSUFFICIENT_FOR_REVISION", 1
    elif a and not b:
        label, rule = "REDISTRIBUTION_DOMINANT", 2
    elif b and not a:
        label, rule = reservation, 3
    elif overlap > RULE["overlap_max"]:
        label, rule = ("REDISTRIBUTION_DOMINANT" if sa >= sb else reservation), 4
    elif sb < RULE["ratio"] * sa:
        label, rule = "REDISTRIBUTION_DOMINANT", 5
    elif sa < RULE["ratio"] * sb:
        label, rule = reservation, 5
    else:
        label, rule = "BOTH_MECHANISMS_MATERIAL", 5
    return {"label": label, "rule": rule, "a_material": a, "a_games": na, "b_material": b, "b_games": nb,
            "overlap": round(overlap, 4), "sa": sa, "sb": sb, "prospective": prospective}


# ------------------------------------------------------------------------------------------------
# Public output


def public_check(value: Any, private_values: Iterable[Any] = (), allowed: Iterable[str] = ()) -> List[str]:
    """Forbidden keys and planted private values anywhere in ``value`` (``s12_screen.privacy_problems``), minus the
    declared ``allowed`` locations (counts that coincide with a private value, each adjudicated by path)."""
    allowed = set(allowed)
    return [p for p in privacy_problems(value, private_values) if p.split(":")[0] not in allowed]


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


__all__ = [name for name in dir() if not name.startswith("_")] + ["FORBIDDEN_KEYS"]
