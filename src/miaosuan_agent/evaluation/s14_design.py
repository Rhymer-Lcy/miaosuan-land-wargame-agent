"""Sprint 14 offline design competition (``docs/SPRINT14_REDISTRIBUTION.md``): replay analysis, frozen gate, rubric.

Pure functions over captured decisions; nothing here opens an engine. :func:`decide_all` decides ``baseline-v2`` from
a captured seat observation and memory, then the reference policies (frozen T9-v1, frozen T9-v2, frozen v3 and Sprint
13's oracle O2) and every frozen Sprint 14 candidate rule on ``baseline-v2``'s actions. :func:`candidate_checks`
re-derives, independently of the candidate's own bookkeeping, the invariants the gate requires of one decision.
:func:`forms` classifies every ``baseline-v2`` ground move order by what a policy emitted for it. The gate
(:func:`gate`), the selection rubric (:func:`select`) and the Part A disposition (:func:`disposition`) are mechanical
functions of the published aggregates and of the thresholds in :data:`GATE`, all fixed before the replay.

Rows produced here carry unit ids and hexes; they stay private. Public structures pass :func:`public_check`.
"""

from __future__ import annotations

import collections
import math
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Stage
from ..decision import digest
from ..decision.candidates import move_candidates
from ..decision.context import build_context
from ..decision.routing import Router, move_mode
from ..experiments import t9_batch as tb
from ..experiments import t9_redistribution as tr
from ..experiments.exploratory_addon import is_int
from ..experiments.shoot_reservation import ShootReservationPolicy
from ..experiments.t9_allocation import AllocationAddon
from ..experiments.t9_staging import StagingAddon
from . import residual516 as rd
from . import s13_diagnosis as sd
from .ps1_model import hex_time
from .s12_screen import privacy_problems

GROUND = (1, 2)
MOVE = 1
CAPACITY = 4
KEEP, REDIRECT, STAGE, WITHHOLD = "KEEP", "REDIRECT", "STAGE", "WITHHOLD"
CANDIDATES: Tuple[str, ...] = tuple(tr.RULES)
REFERENCES = ("baseline-v2", "t9-v1", "t9-v2", "v3", "O2")
POLICIES = REFERENCES + CANDIDATES
#: The declared simplicity order of the candidates (rubric step 4), simplest first.
SIMPLICITY = CANDIDATES

#: Every threshold of the gate and of the rubric (protocol sections 7 and 8), fixed before the replay.
GATE = {
    "restore_share_ratio_min": 0.5,  # per seat: pooled redirect share at least half T9-v1's on the same states
    "restore_first_ratio_min": 0.5,  # every primary game: first-decision redirects at least half T9-v1's
    "restore_units_min": 4,  # every primary game: distinct redirected units
    "divergence_ratio_max": 0.70,  # pooled slot and order divergence from T9-v1 at most 70% of v3's
    "adverse_first_divisor": 3,  # 1930331196 C3 and C2: first-decision redirects at most floor(T9-v1's / 3)
    "adverse_early_divisor": 3,  # baseline-v2 trajectory, decisions before the first firing decision: same
    "latency_p99_ms_max": 20.0,
    "latency_max_ms_max": 200.0,
    "rubric_margin_band": 0.05,
    "rubric_prefix_band": 0.1,
    "rubric_change_tolerance": 0.10,
}
#: Values Sprint 13 published for the same four primary games (evaluation/s13-v3-diagnosis/): the replay must
#: reproduce them before any candidate figure is used (protocol section 5).
S13_EXPECTED = {
    "t9-v1": {"redirects": {"p01": 162, "p02": 212, "p03": 15, "p04": 256},
              "emitted": {"p01": 346, "p02": 268, "p03": 49, "p04": 394},
              "redirected_units": {"p01": 18, "p02": 22, "p03": 14, "p04": 22},
              "first_decision_redirects": {"p01": 14, "p02": 19, "p03": 14, "p04": 19}},
    "pooled": {"v3": {"slot_vs_t9-v1": 550, "orders_vs_t9-v1": 913},
               "O2": {"slot_vs_t9-v1": 222, "orders_vs_t9-v1": 337, "orders_vs_v3": 645, "redirects": 637}},
}
#: Facts of the Sprint 10 diagnostic games the adverse checks rest on (docs/SPRINT10_T9_DIAGNOSIS.md, Sprint 11).
ADVERSE_FACTS = {
    "2120531121 C3": {"baseline_capture_decision": 564, "certificate_from_decision": 442,
                      "v3_certificate_unit_decisions": 9194},
    "1930331196 C3": {"fire_decisions": (742, 804, 841, 876), "direct_fire_actions": 8,
                      "t9v1_first_decision_redirects": 12},
    "1930331196 C2": {"fire_decisions": (611,), "direct_fire_actions": 1, "t9v1_first_decision_redirects": 7},
}


# ------------------------------------------------------------------------------------------------
# Small helpers


def own_ground(observation: Observation, faction: int) -> Dict[int, Any]:
    return {u.obj_id: u for u in observation.operators() if u.color == faction and u.unit_type in GROUND}


def ground_moves(actions: Iterable[Mapping[str, Any]], ground: Mapping[int, Any]) -> Dict[int, Mapping[str, Any]]:
    return {a["obj_id"]: a for a in actions if a.get("type") == MOVE and a.get("obj_id") in ground}


def other_actions(actions: Iterable[Mapping[str, Any]], ground: Mapping[int, Any]) -> List[Any]:
    return [rd.plain(a) for a in actions if not (a.get("type") == MOVE and a.get("obj_id") in ground)]


def form(base: Mapping[str, Any], emitted: Optional[Mapping[str, Any]], cities: Iterable[int]) -> str:
    """What a policy did with one ``baseline-v2`` ground move order (Sprint 13's definition)."""
    if emitted is None:
        return WITHHOLD
    if dict(emitted) == dict(base):
        return KEEP
    path = list(emitted["move_path"])
    if path and path[-1] in set(cities) and path[-1] != list(base["move_path"])[-1]:
        return REDIRECT
    return STAGE


def forms(base_actions: Sequence[Mapping[str, Any]], emitted_actions: Sequence[Mapping[str, Any]],
          ground: Mapping[int, Any], cities: Iterable[int]) -> Dict[int, str]:
    cities = set(cities)
    emitted = ground_moves(emitted_actions, ground)
    return {u: form(a, emitted.get(u), cities) for u, a in ground_moves(base_actions, ground).items()}


def slots(actions: Sequence[Mapping[str, Any]], ground: Mapping[int, Any], cities: Iterable[int]) -> Dict[int, frozenset]:
    """Objective -> the units a policy's emitted ground moves send there."""
    cities = set(cities)
    out: Dict[int, set] = collections.defaultdict(set)
    for u, action in ground_moves(actions, ground).items():
        end = list(action["move_path"])[-1]
        if end in cities:
            out[end].add(u)
    return {c: frozenset(v) for c, v in out.items()}


def slot_divergence(a: Mapping[int, frozenset], b: Mapping[int, frozenset]) -> int:
    return sum(1 for c in set(a) | set(b) if a.get(c, frozenset()) != b.get(c, frozenset()))


def order_divergence(a_actions: Sequence[Mapping[str, Any]], b_actions: Sequence[Mapping[str, Any]],
                     ground: Mapping[int, Any]) -> set:
    a, b = ground_moves(a_actions, ground), ground_moves(b_actions, ground)
    return {u for u in set(a) | set(b) if dict(a.get(u) or {}) != dict(b.get(u) or {})}


def independent_free_flow(costs: MoveCosts, unit: Any, path: Sequence[int]) -> Optional[int]:
    """Free-flow time along ``path`` from the unit's hex, from the cost data and ``ps1_model.hex_time`` only (not the
    candidate's ``path_times``); None if any part is unreadable."""
    mode = move_mode(unit.unit_type, unit.move_state) if is_int(unit.unit_type) else None
    speed = unit.fields.get("basic_speed")
    if mode is None or not isinstance(speed, (int, float)) or speed <= 0 or not path:
        return None
    total, previous = 0, unit.cur_hex
    for hex_ in path:
        edges = costs.neighbours(mode, previous)
        if hex_ not in edges or not edges[hex_] > 0:
            return None
        total += hex_time(speed, edges[hex_])
        previous = hex_
    return total


def outcome_of(allocation: tr.Allocation) -> tuple:
    return (tuple(sorted(allocation.selected.items())),
            tuple(sorted((u, o.objective, tuple(o.path)) for u, o in allocation.redirected.items())),
            tuple(sorted((u, tuple(p)) for u, p in allocation.staged.items())),
            tuple(sorted(allocation.withheld.items())))


def per_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, Any]:
    return {a.get("obj_id"): rd.plain(a) for a in actions if a.get("type") == MOVE}


def reorders(n: int, seed: str) -> List[List[int]]:
    """Three deterministic reorderings of ``n`` actions: reversed, rotated by one, and a seeded shuffle."""
    import random
    shuffled = list(range(n))
    random.Random(seed).shuffle(shuffled)
    return [list(reversed(range(n))), list(range(1, n)) + [0], shuffled]


# ------------------------------------------------------------------------------------------------
# One decision


def decide_all(observation: Observation, seat: int, faction: int, memory: Any, costs: MoveCosts,
               timer=time.perf_counter) -> Dict[str, Any]:
    """``baseline-v2`` (fresh, from the captured memory) and every reference and candidate on its actions."""
    policy = ShootReservationPolicy(costs)
    base = policy.decide(observation, seat, faction, memory)
    actions = tuple(base.actions)
    out: Dict[str, Any] = {"baseline-v2": actions, "baseline_trace_sha256": digest(base.trace),
                           "play": observation.time().stage == Stage.PLAY}
    ground = own_ground(observation, faction)
    out["active"] = bool(out["play"] and ground_moves(actions, ground))
    if not out["active"]:
        for name in POLICIES[1:]:
            out[name] = actions
        if out["play"] and any(a.get("type") == MOVE for a in actions):
            for name in CANDIDATES:  # moves of air units only: the candidates must leave them alone
                out[name] = tr.allocate(observation, seat, faction, actions, policy.router, tr.RULES[name]).actions
        return out
    router = policy.router
    started = timer()
    out["t9-v1"] = tuple(AllocationAddon(costs, policy).apply(observation, seat, faction, base, ()).actions)
    out["t9-v1_ms"] = (timer() - started) * 1000.0
    out["t9-v2"] = tuple(StagingAddon(costs, policy).apply(observation, seat, faction, base, ()).actions)
    v3 = tb.allocate(observation, seat, faction, actions, router)
    out["v3"], out["v3_allocation"] = tuple(v3.actions), v3
    o2 = sd.oracle_allocate(observation, seat, faction, actions, router, redirect=True)
    out["O2"], out["O2_allocation"] = tuple(o2.actions), o2
    for name in CANDIDATES:
        started = timer()
        allocation = tr.allocate(observation, seat, faction, actions, router, tr.RULES[name])
        out[f"{name}_ms"] = (timer() - started) * 1000.0
        out[name], out[f"{name}_allocation"] = tuple(allocation.actions), allocation
    return out


def repeat_checks(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
                  costs: MoveCosts, decided: Mapping[str, Any], seed: str) -> Dict[str, collections.Counter]:
    """Determinism (a second allocation with a fresh router) and order invariance (three reorderings when there are
    at least two claimants) of every candidate. Returns per candidate the counts of comparisons and differences."""
    out: Dict[str, collections.Counter] = {}
    actions = list(actions)
    for name in CANDIDATES:
        counts = collections.Counter()
        reference = decided[f"{name}_allocation"]
        fresh = tr.allocate(observation, seat, faction, actions, ShootReservationPolicy(costs).router, tr.RULES[name])
        counts["repeat_comparisons"] += 1
        if outcome_of(fresh) != outcome_of(reference) or [rd.plain(a) for a in fresh.actions] != [
                rd.plain(a) for a in reference.actions]:
            counts["repeat_differences"] += 1
        if len(reference.claimants) >= 2:
            router = ShootReservationPolicy(costs).router
            ground = own_ground(observation, faction)
            for order in reorders(len(actions), f"{seed}-{name}"):
                permuted = [actions[i] for i in order]
                other = tr.allocate(observation, seat, faction, permuted, router, tr.RULES[name])
                counts["order_comparisons"] += 1
                if (outcome_of(other) != outcome_of(reference) or per_unit(other.actions) != per_unit(reference.actions)
                        or other_actions(other.actions, ground) != other_actions(permuted, ground)):
                    counts["order_differences"] += 1
        out[name] = counts
    return out


def candidate_checks(observation: Observation, seat: int, faction: int, base_actions: Sequence[Mapping[str, Any]],
                     emitted: Sequence[Mapping[str, Any]], allocation: Optional[tr.Allocation],
                     v3_allocation: Optional[tb.Allocation], costs: MoveCosts) -> Dict[str, Any]:
    """The invariants of one candidate decision, re-derived from the observation and the cost data with a fresh
    router: unrelated actions, invented moves, capacity, redirect routes and reachability, staging prefixes, and
    that every v3 selection is kept. Returns violation counts and the decision's redirect rows."""
    violations: collections.Counter = collections.Counter()
    ground = own_ground(observation, faction)
    cities = {c.coord for c in (observation.cities() or ())}
    if other_actions(emitted, ground) != other_actions(base_actions, ground):
        violations["unrelated action changed"] += 1
    base_moves, out_moves = ground_moves(base_actions, ground), ground_moves(emitted, ground)
    violations["invented move"] += len(set(out_moves) - set(base_moves))
    emitted_order = [a.get("obj_id") for a in emitted if a.get("type") == MOVE and a.get("obj_id") in ground]
    base_order = [u for u in (a.get("obj_id") for a in base_actions if a.get("type") == MOVE) if u in out_moves]
    if emitted_order != base_order:
        violations["ground move order changed"] += 1
    rows: List[Dict[str, Any]] = []
    if not out_moves and not base_moves:
        return {"violations": violations, "redirects": rows, "forms": {}}
    router = ShootReservationPolicy(costs).router
    context = build_context(observation, seat, faction)
    if hasattr(router, "targets"):
        router.targets = frozenset(c.coord for c in context.objectives)
    unheld = {c.coord for c in context.objectives}
    time_info = observation.time()
    end = time_info.max_step if is_int(time_info.max_step) else None
    now = time_info.cur_step
    incumbents, _ = sd.counted_incumbents(observation, faction, router)
    additions: collections.Counter = collections.Counter()
    unit_forms = forms(base_actions, emitted, ground, cities)
    for u, kind in unit_forms.items():
        action = out_moves.get(u)
        base_path = list(base_moves[u]["move_path"])
        if kind in (KEEP, REDIRECT):
            end_hex = list(action["move_path"])[-1]
            if end_hex in cities:
                additions[end_hex] += 1
                ff = independent_free_flow(costs, ground[u], list(action["move_path"]))
                if ff is None or (end is not None and now + ff >= end):
                    violations["place for a unit that cannot arrive before the end"] += 1
        if kind == STAGE:
            path = list(action["move_path"])
            if not (0 < len(path) < len(base_path) and path == base_path[:len(path)] and path[-1] not in cities):
                violations["changed move neither a redirect nor a strict same-route prefix off objectives"] += 1
        if kind == REDIRECT:
            path = list(action["move_path"])
            unit_ctx = context.unit(u)
            candidates, _ = move_candidates(unit_ctx, context, router) if unit_ctx is not None else ([], None)
            routes = {dict(c.detail)["destination"]: (list(c.action(seat)["move_path"]), dict(c.detail)["cost"])
                      for c in candidates}
            own_cost = routes.get(base_path[-1], (None, None))[1]
            target = routes.get(path[-1])
            if target is None or target[0] != path:
                violations["redirect route differs from baseline-v2's candidate route"] += 1
            if path[-1] not in unheld:
                violations["redirect to an objective the side holds"] += 1
            if own_cost is None or target is None or target[1] > tr.DETOUR * own_cost:
                violations["redirect beyond the detour bound"] += 1
            ff = independent_free_flow(costs, ground[u], path)
            prefix = tr.shared_prefix(base_path, path)
            rows.append({"unit": u, "from": base_path[-1], "to": path[-1], "free_flow": ff,
                         "slack": None if (ff is None or end is None) else end - (now + ff),
                         "detour": None if (own_cost is None or target is None or not own_cost) else target[1] / own_cost,
                         "prefix": prefix, "base_length": len(base_path), "length": len(path),
                         "kind": ground[u].unit_type})
    for coord, added in additions.items():
        row = incumbents.get(coord, {})
        if added and row.get("physical", 0) + row.get("movers", 0) + added > CAPACITY:
            violations["objective above capacity"] += 1
    if allocation is not None:
        if allocation.error is not None:
            violations["candidate error"] += 1
        if v3_allocation is not None and any(allocation.selected.get(u) != c for u, c in v3_allocation.selected.items()):
            violations["a v3 selection not kept"] += 1
        violations["gate rejections"] += sum(1 for r in allocation.withheld.values() if "rejected by the gate" in r)
    return {"violations": violations, "redirects": rows, "forms": unit_forms,
            "max_commitment": max((incumbents.get(c, {}).get("physical", 0) + incumbents.get(c, {}).get("movers", 0)
                                   + a for c, a in additions.items()), default=0)}


# ------------------------------------------------------------------------------------------------
# Gate (protocol section 7)


def ratio(a: float, b: float) -> Optional[float]:
    return None if not b else a / b


def gate(name: str, facts: Mapping[str, Any], rules: Mapping[str, Any] = GATE) -> Dict[str, Any]:
    """Every gate item of one candidate from the published facts. ``facts`` holds, for the candidate and for the
    references, the aggregates the driver publishes (see the protocol for each key)."""
    c = facts["candidates"][name]
    ref = facts["references"]
    items: Dict[str, Dict[str, Any]] = {}

    def item(code: str, ok: bool, **values: Any) -> None:
        items[code] = {"pass": bool(ok), **values}

    item("G1_deterministic", c["repeat_differences"] == 0 and c["repeat_comparisons"] > 0,
         comparisons=c["repeat_comparisons"], differences=c["repeat_differences"])
    item("G2_seat_local", facts["static"]["seat_local"], basis="module imports and inputs (static check)")
    item("G3_order_invariant", c["order_differences"] == 0 and c["order_comparisons"] > 0,
         comparisons=c["order_comparisons"], differences=c["order_differences"])
    v = c["violations"]
    item("G4_capacity", v.get("objective above capacity", 0) == 0, violations=v.get("objective above capacity", 0))
    item("G5_unrelated_actions", v.get("unrelated action changed", 0) + v.get("ground move order changed", 0) == 0,
         violations=v.get("unrelated action changed", 0) + v.get("ground move order changed", 0))
    item("G6_no_invented_move", v.get("invented move", 0) == 0, violations=v.get("invented move", 0))
    semantics = (v.get("redirect route differs from baseline-v2's candidate route", 0)
                 + v.get("changed move neither a redirect nor a strict same-route prefix off objectives", 0)
                 + v.get("redirect to an objective the side holds", 0) + v.get("redirect beyond the detour bound", 0)
                 + v.get("candidate error", 0))
    item("G7_engine_supported_moves", semantics == 0, violations=semantics)
    item("G8_reachable", v.get("place for a unit that cannot arrive before the end", 0) == 0,
         violations=v.get("place for a unit that cannot arrive before the end", 0))

    # G9: restoration of redistribution on the primary states
    prim, t9p = c["primary"], ref["t9-v1"]["primary"]
    seat_ratios = {seat: ratio(prim["seats"][seat]["share"], t9p["seats"][seat]["share"]) for seat in ("H1", "H2")}
    first_ratios = {g: ratio(prim["games"][g]["first_decision_redirects"], t9p["games"][g]["first_decision_redirects"])
                    for g in sorted(prim["games"])}
    units = {g: prim["games"][g]["redirected_units"] for g in sorted(prim["games"])}
    ok9 = (all(r is not None and r >= rules["restore_share_ratio_min"] for r in seat_ratios.values())
           and all(r is not None and r >= rules["restore_first_ratio_min"] for r in first_ratios.values())
           and all(n >= rules["restore_units_min"] for n in units.values()) and len(units) == 4)
    item("G9_redistribution_restored", ok9, seat_share_ratios=rounded(seat_ratios),
         first_decision_ratios=rounded(first_ratios), redirected_units=units)

    # G10: divergence from T9-v1 reduced relative to v3
    v3p = ref["v3"]["primary"]
    slot_ratio = ratio(prim["pooled"]["slot_vs_t9-v1"], v3p["pooled"]["slot_vs_t9-v1"])
    order_ratio = ratio(prim["pooled"]["orders_vs_t9-v1"], v3p["pooled"]["orders_vs_t9-v1"])
    seats_lower = {seat: prim["seats"][seat]["slot_vs_t9-v1"] < v3p["seats"][seat]["slot_vs_t9-v1"]
                   for seat in ("H1", "H2")}
    ok10 = (slot_ratio is not None and slot_ratio <= rules["divergence_ratio_max"] and order_ratio is not None
            and order_ratio <= rules["divergence_ratio_max"] and all(seats_lower.values()))
    item("G10_divergence_reduced", ok10, slot_ratio=rounded(slot_ratio), order_ratio=rounded(order_ratio),
         seat_slot_below_v3=seats_lower)

    # G11: 2120531121 C3
    a = c["adverse"]["2120531121 C3"]
    ok11 = (a["unreachable_places"] == 0 and a["v3_selection_not_kept"] == 0 and a["far_reservations_missed"] == 0
            and a["certificate_unit_decisions"] >= a["v3_certificate_unit_decisions"])
    item("G11_2120531121_C3", ok11, unreachable_places=a["unreachable_places"],
         v3_selection_not_kept=a["v3_selection_not_kept"], far_reservations_missed=a["far_reservations_missed"],
         certificate_unit_decisions=a["certificate_unit_decisions"],
         v3_certificate_unit_decisions=a["v3_certificate_unit_decisions"])

    # G12: 1930331196 corridors
    rows12, ok12 = {}, True
    for config in ("1930331196 C3", "1930331196 C2"):
        x = c["adverse"][config]
        t9 = ref["t9-v1"]["adverse"][config]
        first_limit = t9["first_decision_redirects_by_trajectory"]["t9-v1"] // rules["adverse_first_divisor"]
        early_limit = t9["early_redirects_baseline"] // rules["adverse_early_divisor"]
        ok = (x["shooters_redirected"] == 0 and x["first_decision_redirects"] <= first_limit
              and x["early_redirects_baseline"] <= early_limit)
        ok12 = ok12 and ok
        rows12[config] = {"shooters_redirected": x["shooters_redirected"],
                          "first_decision_redirects": x["first_decision_redirects"], "first_limit": first_limit,
                          "early_redirects_baseline": x["early_redirects_baseline"], "early_limit": early_limit,
                          "pass": ok}
    item("G12_1930331196_corridors", ok12, configurations=rows12)
    item("G13_no_future_information", facts["static"]["seat_local"], basis="the allocator's inputs (static check)")
    item("G14_no_special_case", facts["static"]["no_special_case_literal"], basis="numeric literals (static check)")
    lat = c["latency_ms"]
    item("G15_latency", lat["p99"] <= rules["latency_p99_ms_max"] and lat["max"] <= rules["latency_max_ms_max"],
         p99_ms=round(lat["p99"], 3), max_ms=round(lat["max"], 3))
    return {"items": items, "pass": all(i["pass"] for i in items.values()),
            "failed": [code for code, i in items.items() if not i["pass"]]}


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, Mapping):
        return {k: rounded(v) for k, v in value.items()}
    return value


# ------------------------------------------------------------------------------------------------
# Rubric (protocol section 8) and Part A disposition


def margins(gate_row: Mapping[str, Any], rules: Mapping[str, Any] = GATE) -> Dict[str, float]:
    """How comfortably a passing candidate clears the restoration and the adverse thresholds."""
    g9 = gate_row["items"]["G9_redistribution_restored"]
    restore = min(min(g9["seat_share_ratios"].values()), min(g9["first_decision_ratios"].values()), 1.0)
    rows = gate_row["items"]["G12_1930331196_corridors"]["configurations"]
    used = []
    for row in rows.values():
        used.append(row["first_decision_redirects"] / max(row["first_limit"], 1) if row["first_limit"] else
                    (0.0 if row["first_decision_redirects"] == 0 else math.inf))
        used.append(row["early_redirects_baseline"] / max(row["early_limit"], 1) if row["early_limit"] else
                    (0.0 if row["early_redirects_baseline"] == 0 else math.inf))
    floor = rules["restore_share_ratio_min"]
    restore_margin = (restore - floor) / (1.0 - floor)
    adverse_margin = 1.0 - max(used)
    return {"restore": restore_margin, "adverse": adverse_margin, "margin": min(restore_margin, adverse_margin)}


def select(passing: Mapping[str, Mapping[str, Any]], rules: Mapping[str, Any] = GATE) -> Dict[str, Any]:
    """Exactly one candidate from those that passed the gate, by the frozen lexicographic rubric.

    ``passing`` maps a candidate to ``{"gate": gate row, "prefix_median": share, "orders_vs_baseline": n,
    "latency_p99": ms}``. Each step keeps the best band and passes the survivors on."""
    if not passing:
        return {"selected": None, "steps": []}
    steps = []
    alive = sorted(passing, key=SIMPLICITY.index)
    band = {n: math.floor(margins(passing[n]["gate"], rules)["margin"] / rules["rubric_margin_band"] + 1e-9)
            for n in alive}
    best = max(band.values())
    alive = [n for n in alive if band[n] == best]
    steps.append({"step": "margin band", "values": band, "kept": list(alive)})
    prefix = {n: math.floor((passing[n]["prefix_median"] or 0.0) / rules["rubric_prefix_band"] + 1e-9) for n in alive}
    best = max(prefix.values())
    alive = [n for n in alive if prefix[n] == best]
    steps.append({"step": "corridor band", "values": prefix, "kept": list(alive)})
    change = {n: passing[n]["orders_vs_baseline"] for n in alive}
    least = min(change.values())
    alive = [n for n in alive if change[n] <= least * (1 + rules["rubric_change_tolerance"])]
    steps.append({"step": "behaviour changed from baseline-v2", "values": change, "kept": list(alive)})
    alive = [min(alive, key=SIMPLICITY.index)] if len(alive) > 1 else alive
    steps.append({"step": "simplicity", "kept": list(alive)})
    return {"selected": alive[0], "steps": steps}


def disposition(fidelity_problems: Sequence[str], gates: Mapping[str, Mapping[str, Any]],
                selection: Mapping[str, Any]) -> Dict[str, Any]:
    if fidelity_problems:
        return {"disposition": "REPLAY_INVALID", "problems": list(fidelity_problems)[:20]}
    passed = sorted((n for n, g in gates.items() if g["pass"]), key=SIMPLICITY.index)
    if not passed:
        return {"disposition": "NO_ENGINE_CANDIDATE", "passed": []}
    return {"disposition": "ENGINE_CANDIDATE_SELECTED", "passed": passed, "selected": selection["selected"],
            "identity": tr.RULES[selection["selected"]].identity}


# ------------------------------------------------------------------------------------------------
# Distributions and privacy


def distribution(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0}
    def q(p: float) -> float:
        return vals[min(len(vals) - 1, int(p * (len(vals) - 1) + 0.5))]
    return {"n": len(vals), "min": rounded(float(vals[0])), "p25": rounded(float(q(0.25))),
            "median": rounded(float(q(0.5))), "p75": rounded(float(q(0.75))), "max": rounded(float(vals[-1]))}


def percentile(values: Sequence[float], p: float) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    rank = max(1, math.ceil(p * len(vals)))
    return vals[rank - 1]


def public_check(value: Any, private_values: Iterable[Any] = ()) -> List[str]:
    return privacy_problems(value, private_values)
