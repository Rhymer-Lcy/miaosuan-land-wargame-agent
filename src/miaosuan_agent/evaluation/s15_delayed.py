"""Sprint 15 offline study of delayed redistribution (``docs/SPRINT15_DELAYED_REDISTRIBUTION.md``): analysis, frozen gate.

Pure functions over captured decisions and published aggregates; nothing here opens an engine. The replay driver
(``scripts/s15_delayed_replay.py``) decides every policy on every captured decision, simulating each stateful
candidate's own memory sequentially over the captured observation stream, and calls:

* :func:`decide_step`: ``baseline-v2`` from the captured memory, then frozen T9-v1, frozen v3, Sprint 13's oracle O2
  (= Sprint 14's ``feasible-value-redirect``) and every Sprint 15 candidate with its memory;
* :func:`repeat_checks`: determinism (a fresh router, same memory in) and order invariance (three reorderings of
  ``baseline-v2``'s actions) of the actions, the allocation and the memory out;
* :func:`memory_problems`: the memory's bounds against the observation;
* :func:`gate`, :func:`adequacy`, :func:`select`, :func:`disposition`: the frozen protocol (sections 7 to 10), from
  the published aggregates and the thresholds in :data:`GATE`, all fixed before the final replay;
* :func:`rule_search`: the diagnostic one- and two-predicate search of section 4 (never a policy).

Rows produced here can carry unit ids and hexes; they stay private. Public structures pass :func:`public_check`.
"""

from __future__ import annotations

import collections
import itertools
import math
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Stage
from ..decision import digest
from ..experiments import t9_batch as tb
from ..experiments import t9_delayed as td
from ..experiments import t9_redistribution as tr
from ..experiments.shoot_reservation import ShootReservationPolicy
from ..experiments.t9_allocation import AllocationAddon
from . import residual516 as rd
from . import s14_design as sx

KEEP, REDIRECT, STAGE, WITHHOLD = sx.KEEP, sx.REDIRECT, sx.STAGE, sx.WITHHOLD
CANDIDATES: Tuple[str, ...] = tuple(td.RULES)
REFERENCES = ("baseline-v2", "t9-v1", "v3", "O2", "batch-value-redirect")
POLICIES = REFERENCES + CANDIDATES
SIMPLICITY = CANDIDATES  # declared order, simplest first
V3_TRACK = "v3-track"  # the memory a delayed rule keeps when nobody is eligible: v3's actions, the rules' bookkeeping
BUCKETS = ("first", "next5", "next20", "later")

#: Every threshold of the gate, the adequacy rule and the rubric (protocol sections 7 to 9), fixed before the replay.
GATE = {
    "restore_units_ratio_min": 0.5,  # per seat: post-opening distinct redirected units >= ratio x T9-v1's
    "restore_units_min": 4,  # per seat: and at least this many
    "divergence_ratio_max": 0.70,  # pooled post-opening slot divergence from T9-v1 <= ratio x v3's
    "adverse_first_divisor": 3,  # 1930331196: first-decision redirects <= floor(T9-v1's at its own first decision / 3)
    "adverse_early_divisor": 3,  # baseline-v2 trajectory, before the first firing decision: <= floor(T9-v1's / 3)
    "recourse_max": 3,  # redirects of any one unit in one game (any episodes), primary states and H0
    "latency_p99_ms_max": 20.0,
    "latency_max_ms_max": 200.0,
    "rubric_band": 0.05,
    "rubric_tolerance": 0.10,
}
#: Risk windows of the adequacy rule (section 8): decisions before which the trigger must have been exercised.
RISK_WINDOW = {"1930331196 C3": 876, "1930331196 C2": 611, "2120531121 C3": 564}
DISPOSITIONS = ("REPLAY_INVALID", "NO_DELAYED_REDISTRIBUTION_OPPORTUNITY", "OFFLINE_CANDIDATE_SELECTED",
                "MECHANISM_AMBIGUOUS", "NO_STATE_DISCRIMINATOR", "NO_RESTORING_TRIGGER")


def bucket(ordinal: int) -> str:
    """Decision bucket by the ordinal of the active decision (1 = the first decision with an own ground move)."""
    if ordinal <= 1:
        return "first"
    if ordinal <= 6:
        return "next5"
    if ordinal <= 26:
        return "next20"
    return "later"


# ------------------------------------------------------------------------------------------------
# One decision


def decide_step(observation: Observation, seat: int, faction: int, memory: Any, costs: MoveCosts,
                memories: Mapping[str, Any], timer=time.perf_counter, candidates: Sequence[str] = CANDIDATES
                ) -> Dict[str, Any]:
    """``baseline-v2`` (fresh, from the captured memory), the references and every candidate with its memory in.
    ``out[name]`` the actions, ``out[name + "_allocation"]`` the allocation, ``out[name + "_memory"]`` the memory out,
    ``out[name + "_ms"]`` the candidate's milliseconds."""
    policy = ShootReservationPolicy(costs)
    base = policy.decide(observation, seat, faction, memory)
    actions = tuple(base.actions)
    out: Dict[str, Any] = {"baseline-v2": actions, "baseline_trace_sha256": digest(base.trace),
                           "play": observation.time().stage == Stage.PLAY}
    ground = sx.own_ground(observation, faction)
    out["active"] = bool(out["play"] and sx.ground_moves(actions, ground))
    router = policy.router
    nobody = td.allocate(observation, seat, faction, actions, router, None, memories.get(V3_TRACK, ()))
    out[f"{V3_TRACK}_allocation"], out[f"{V3_TRACK}_memory"] = nobody, nobody.memory
    for name in candidates:
        started = timer()
        allocation = td.allocate(observation, seat, faction, actions, router, td.RULES[name], memories.get(name, ()))
        out[f"{name}_ms"] = (timer() - started) * 1000.0
        out[name], out[f"{name}_allocation"], out[f"{name}_memory"] = tuple(allocation.actions), allocation, \
            allocation.memory
    if not out["active"]:
        for name in REFERENCES[1:]:
            out[name] = actions
        return out
    started = timer()
    out["t9-v1"] = tuple(AllocationAddon(costs, policy).apply(observation, seat, faction, base, ()).actions)
    out["t9-v1_ms"] = (timer() - started) * 1000.0
    v3 = tb.allocate(observation, seat, faction, actions, router)
    out["v3"], out["v3_allocation"] = tuple(v3.actions), v3
    o2 = tr.allocate(observation, seat, faction, actions, router, tr.RULES["feasible-value-redirect"])
    out["O2"], out["O2_allocation"] = tuple(o2.actions), o2
    batch = tr.allocate(observation, seat, faction, actions, router, tr.RULES["batch-value-redirect"])
    out["batch-value-redirect"], out["batch-value-redirect_allocation"] = tuple(batch.actions), batch
    everyone = td.allocate(observation, seat, faction, actions, router, None, everyone=True)
    out["identity_v3"] = ([rd.plain(a) for a in nobody.actions] == [rd.plain(a) for a in v3.actions]
                          and (nobody.selected, nobody.staged, nobody.withheld) == (v3.selected, v3.staged, v3.withheld))
    out["identity_o2"] = ([rd.plain(a) for a in everyone.actions] == [rd.plain(a) for a in o2.actions]
                          and {u: (o.objective, o.path) for u, o in everyone.redirected.items()}
                          == {u: (o.objective, o.path) for u, o in o2.redirected.items()}
                          and (everyone.staged, everyone.withheld) == (o2.staged, o2.withheld))
    return out


def outcome(allocation: td.Allocation) -> tuple:
    return (tuple(sorted(allocation.selected.items())),
            tuple(sorted((u, o.objective, tuple(o.path)) for u, o in allocation.redirected.items())),
            tuple(sorted((u, tuple(p)) for u, p in allocation.staged.items())),
            tuple(sorted(allocation.withheld.items())), tuple(allocation.memory))


def repeat_checks(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
                  costs: MoveCosts, decided: Mapping[str, Any], memories: Mapping[str, Any], seed: str,
                  candidates: Sequence[str] = CANDIDATES) -> Dict[str, collections.Counter]:
    """Determinism and order invariance of every candidate on one decision, the memory out included."""
    out: Dict[str, collections.Counter] = {}
    actions = list(actions)
    ground = sx.own_ground(observation, faction)
    for name in candidates:
        counts = collections.Counter()
        reference = decided[f"{name}_allocation"]
        memory = memories.get(name, ())
        fresh = td.allocate(observation, seat, faction, actions, ShootReservationPolicy(costs).router, td.RULES[name],
                            memory)
        counts["repeat_comparisons"] += 1
        if outcome(fresh) != outcome(reference) or [rd.plain(a) for a in fresh.actions] != [
                rd.plain(a) for a in reference.actions]:
            counts["repeat_differences"] += 1
        if len(reference.claimants) >= 2:
            router = ShootReservationPolicy(costs).router
            for order in sx.reorders(len(actions), f"{seed}-{name}"):
                permuted = [actions[i] for i in order]
                other = td.allocate(observation, seat, faction, permuted, router, td.RULES[name], memory)
                counts["order_comparisons"] += 1
                if (outcome(other) != outcome(reference) or sx.per_unit(other.actions) != sx.per_unit(reference.actions)
                        or sx.other_actions(other.actions, ground) != sx.other_actions(permuted, ground)):
                    counts["order_differences"] += 1
        out[name] = counts
    return out


def memory_problems(observation: Observation, faction: int, memory: Sequence[Sequence[int]]) -> List[str]:
    """The memory after a decision must decode cleanly, hold only present own ground units, carry exactly the
    declared fields and keep its counters inside their bounds."""
    records, errors = td.decode(memory)
    problems = [f"decode: {e}" for e in errors]
    own = {u.obj_id for u in observation.operators() if u.color == faction and u.unit_type in td.GROUND}
    stray = set(records) - own
    if stray:
        problems.append(f"{len(stray)} records for units not present")
    for record in records.values():
        if not any(record):
            problems.append("an empty record was kept")
        if not 0 <= record[td.COUNT] <= td.COUNT_CAP or record[td.REDIRECTED] not in (0, 1) or \
                record[td.DONE] not in (0, 1) or record[td.SATURATED] not in (0, 1):
            problems.append("a field outside its bounds")
    if len(memory) > len(own) * len(td.FIELD_NAMES):
        problems.append("more entries than fields of present units")
    return problems


def oscillations(history: Sequence[Tuple[int, int, int, int]]) -> int:
    """Redirects (decision, unit, from, to) that send a unit back to an objective it was earlier redirected away
    from, from the objective it was then redirected to (A to B, later B to A)."""
    seen: Dict[int, List[Tuple[int, int]]] = collections.defaultdict(list)
    count = 0
    for _, unit, source, target in sorted(history):
        if any(previous_source == target and previous_target == source for previous_source, previous_target in
               seen[unit]):
            count += 1
        seen[unit].append((source, target))
    return count


# ------------------------------------------------------------------------------------------------
# Gate (section 7), adequacy (section 8), rubric (section 9), disposition (section 10)


def ratio(a: float, b: float) -> Optional[float]:
    return None if not b else a / b


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, Mapping):
        return {k: rounded(v) for k, v in value.items()}
    return value


def gate(name: str, facts: Mapping[str, Any], rules: Mapping[str, Any] = GATE) -> Dict[str, Any]:
    """Every hard item of one candidate. ``facts['candidates'][name]`` holds the candidate's aggregates,
    ``facts['references']`` T9-v1's, v3's and O2's on the same states (keys documented in the protocol)."""
    c = facts["candidates"][name]
    ref = facts["references"]
    items: Dict[str, Dict[str, Any]] = {}

    def item(code: str, ok: bool, **values: Any) -> None:
        items[code] = {"pass": bool(ok), **values}

    inv = c["invariants"]
    item("G1_deterministic", inv["repeat_differences"] == 0 and inv["repeat_comparisons"] > 0,
         comparisons=inv["repeat_comparisons"], differences=inv["repeat_differences"])
    item("G2_seat_local", facts["static"]["seat_local"], basis="module imports and inputs (static check)")
    item("G3_order_invariant", inv["order_differences"] == 0 and inv["order_comparisons"] > 0,
         comparisons=inv["order_comparisons"], differences=inv["order_differences"])
    v = inv["violations"]
    item("G4_capacity", v.get("objective above capacity", 0) == 0, violations=v.get("objective above capacity", 0))
    unrelated = v.get("unrelated action changed", 0) + v.get("ground move order changed", 0)
    item("G5_unrelated_actions", unrelated == 0, violations=unrelated)
    item("G6_no_invented_move", v.get("invented move", 0) == 0, violations=v.get("invented move", 0))
    semantics = (v.get("redirect route differs from baseline-v2's candidate route", 0)
                 + v.get("changed move neither a redirect nor a strict same-route prefix off objectives", 0)
                 + v.get("redirect to an objective the side holds", 0) + v.get("redirect beyond the detour bound", 0)
                 + v.get("candidate error", 0) + v.get("gate rejections", 0))
    item("G7_engine_supported_moves", semantics == 0, violations=semantics)
    item("G8_reachable", v.get("place for a unit that cannot arrive before the end", 0) == 0,
         violations=v.get("place for a unit that cannot arrive before the end", 0))
    item("G9_memory", inv["memory_problems"] == 0 and inv["memory_checks"] > 0, checks=inv["memory_checks"],
         problems=inv["memory_problems"])
    item("G10_no_future_information", facts["static"]["seat_local"], basis="the allocator's inputs (static check)")
    item("G11_no_special_case", facts["static"]["no_special_case_literal"], basis="numeric literals (static check)")
    lat = c["latency_ms"]
    item("G12_latency", lat["p99"] <= rules["latency_p99_ms_max"] and lat["max"] <= rules["latency_max_ms_max"],
         p99_ms=round(lat["p99"], 3), max_ms=round(lat["max"], 3))

    # primary restoration
    prim, t9, v3 = c["primary"], ref["t9-v1"]["primary"], ref["v3"]["primary"]
    first = {g: prim["games"][g]["first_decision_redirects"] for g in sorted(prim["games"])}
    adverse_first = {cfg: c["adverse"][cfg]["first_decision_redirects"] for cfg in sorted(c["adverse"])}
    item("R1_no_opening_redistribution", all(n == 0 for n in first.values()) and all(
        n == 0 for n in adverse_first.values()) and len(first) == 4 and len(adverse_first) == 3,
         primary=first, adverse=adverse_first)
    units, needed = {}, {}
    for seat in ("H1", "H2"):
        units[seat] = prim["seats"][seat]["post_opening_units"]
        needed[seat] = max(rules["restore_units_min"],
                           math.ceil(rules["restore_units_ratio_min"] * t9["seats"][seat]["post_opening_units"]))
    item("R2_post_opening_restored", all(units[s] >= needed[s] for s in ("H1", "H2")),
         post_opening_units=units, required=needed)
    slot = ratio(prim["pooled"]["post_slot_vs_t9-v1"], v3["pooled"]["post_slot_vs_t9-v1"])
    lower = {s: prim["seats"][s]["post_slot_vs_t9-v1"] < v3["seats"][s]["post_slot_vs_t9-v1"] for s in ("H1", "H2")}
    item("R3_divergence_reduced", slot is not None and slot <= rules["divergence_ratio_max"] and all(lower.values()),
         post_slot_ratio=rounded(slot), seat_below_v3=lower)
    # Orders changed from baseline-v2 are the same for every rule built on v3's stage 1 (selections are kept, only
    # overflow orders change), so churn is measured as recourse: oscillations and redirects of one unit in one game.
    recourse = prim["pooled"]["max_redirects_per_unit_game"]
    item("R4_bounded_recourse", prim["pooled"]["oscillations"] == 0 and recourse <= rules["recourse_max"],
         oscillations=prim["pooled"]["oscillations"], max_redirects_per_unit_game=recourse,
         limit=rules["recourse_max"])

    # adverse safety
    rows, ok = {}, True
    for config in ("1930331196 C3", "1930331196 C2"):
        x, r = c["adverse"][config], ref["t9-v1"]["adverse"][config]
        first_limit = r["first_decision_redirects_own_game"] // rules["adverse_first_divisor"]
        early_limit = r["early_redirects_baseline"] // rules["adverse_early_divisor"]
        good = (x["shooters_redirected"] == 0 and x["first_decision_redirects"] <= first_limit
                and x["early_redirects_baseline"] <= early_limit)
        ok = ok and good
        rows[config] = {"shooters_redirected": x["shooters_redirected"],
                        "first_decision_redirects": x["first_decision_redirects"], "first_limit": first_limit,
                        "early_redirects_baseline": x["early_redirects_baseline"], "early_limit": early_limit,
                        "pass": good}
    item("A1_1930331196", ok, configurations=rows)
    a = c["adverse"]["2120531121 C3"]
    v3_cert = ref["v3"]["adverse"]["2120531121 C3"]["certificate_unit_decisions"]
    item("A2_2120531121_C3", a["unreachable_places"] == 0 and a["v3_selection_not_kept"] == 0
         and a["certificate_unit_decisions"] >= v3_cert, unreachable_places=a["unreachable_places"],
         v3_selection_not_kept=a["v3_selection_not_kept"], certificate_unit_decisions=a["certificate_unit_decisions"],
         v3_certificate_unit_decisions=v3_cert)
    groups = {"invariants": [k for k in items if k.startswith("G")], "restoration": [k for k in items if
                                                                                  k.startswith("R")],
              "adverse": [k for k in items if k.startswith("A")]}
    passed = {g: all(items[k]["pass"] for k in keys) for g, keys in groups.items()}
    return {"items": items, "groups": passed, "pass": all(passed.values()),
            "failed": [code for code, i in items.items() if not i["pass"]]}


def adequacy(name: str, facts: Mapping[str, Any]) -> Dict[str, Any]:
    """Section 8: an adverse configuration's result is TESTED only if the candidate's trigger held for at least one
    overflow observation in that configuration's risk window (either trajectory); otherwise UNTESTED, whatever the
    gate items say. A trigger that never held cannot show that the configuration is safe."""
    rows = {}
    for config in sorted(RISK_WINDOW):
        exposure = facts["candidates"][name]["adverse"][config]["trigger_exposure_in_window"]
        rows[config] = {"trigger_exposure_in_window": exposure, "status": "TESTED" if exposure > 0 else "UNTESTED"}
    return {"configurations": rows, "all_tested": all(r["status"] == "TESTED" for r in rows.values())}


def margins(gate_row: Mapping[str, Any]) -> Dict[str, float]:
    """How comfortably a passing candidate clears the restoration and adverse thresholds (rubric steps 1 and 2)."""
    r2 = gate_row["items"]["R2_post_opening_restored"]
    restore = min(r2["post_opening_units"][s] / r2["required"][s] for s in r2["required"]) - 1.0
    used = []
    for row in gate_row["items"]["A1_1930331196"]["configurations"].values():
        for count, limit in ((row["first_decision_redirects"], row["first_limit"]),
                             (row["early_redirects_baseline"], row["early_limit"])):
            used.append(count / limit if limit else (0.0 if count == 0 else math.inf))
    return {"restore": restore, "adverse": 1.0 - max(used)}


def select(passing: Mapping[str, Mapping[str, Any]], rules: Mapping[str, Any] = GATE) -> Dict[str, Any]:
    """Exactly one candidate among those that passed every item with every adverse configuration TESTED.

    ``passing``: name -> {"gate": gate row, "post_slot": pooled post-opening slot divergence from T9-v1,
    "redirects": redirect order-decisions on the primary states, "latency_p99": ms}. Lexicographic: adverse margin
    band, restoration margin band, post-opening divergence within tolerance, recourse within tolerance, simplicity,
    latency."""
    if not passing:
        return {"selected": None, "steps": []}
    steps = []
    alive = sorted(passing, key=SIMPLICITY.index)
    for label, key in (("adverse margin band", "adverse"), ("restoration margin band", "restore")):
        band = {n: math.floor(margins(passing[n]["gate"])[key] / rules["rubric_band"] + 1e-9) for n in alive}
        best = max(band.values())
        alive = [n for n in alive if band[n] == best]
        steps.append({"step": label, "values": band, "kept": list(alive)})
    for label, key in (("post-opening divergence from T9-v1", "post_slot"), ("recourse", "redirects")):
        values = {n: passing[n][key] for n in alive}
        least = min(values.values())
        alive = [n for n in alive if values[n] <= least * (1 + rules["rubric_tolerance"])]
        steps.append({"step": label, "values": values, "kept": list(alive)})
    alive = [min(alive, key=SIMPLICITY.index)] if len(alive) > 1 else alive
    steps.append({"step": "simplicity", "kept": list(alive)})
    return {"selected": alive[0], "steps": steps}


def disposition(fidelity_problems: Sequence[str], gates: Mapping[str, Mapping[str, Any]],
                adequacies: Mapping[str, Mapping[str, Any]], opportunity: Mapping[str, Any],
                selection: Mapping[str, Any]) -> Dict[str, Any]:
    """Section 10, first match. ``opportunity``: per seat the upper bound of any delayed rule (O2's post-opening
    distinct redirected units) and the units R2 requires."""
    if fidelity_problems:
        return {"disposition": "REPLAY_INVALID", "problems": list(fidelity_problems)[:20]}
    short = sorted(s for s, row in opportunity.items() if row["o2_post_opening_units"] < row["required"])
    if short:
        return {"disposition": "NO_DELAYED_REDISTRIBUTION_OPPORTUNITY", "seats": short}
    full = sorted((n for n, g in gates.items() if g["pass"] and adequacies[n]["all_tested"]), key=SIMPLICITY.index)
    if full:
        return {"disposition": "OFFLINE_CANDIDATE_SELECTED", "passed": full, "selected": selection["selected"],
                "identity": td.RULES[selection["selected"]].identity}
    untested = sorted((n for n, g in gates.items() if g["pass"]), key=SIMPLICITY.index)
    if untested:
        return {"disposition": "MECHANISM_AMBIGUOUS", "passed_untested": untested,
                "untested": {n: sorted(c for c, r in adequacies[n]["configurations"].items() if r["status"] ==
                                       "UNTESTED") for n in untested}}
    restoring = sorted((n for n, g in gates.items() if g["groups"]["invariants"] and g["groups"]["restoration"]),
                       key=SIMPLICITY.index)
    if restoring:
        return {"disposition": "NO_STATE_DISCRIMINATOR", "restoring_but_unsafe": restoring}
    return {"disposition": "NO_RESTORING_TRIGGER", "passed": []}


# ------------------------------------------------------------------------------------------------
# Diagnostic rule search (section 4): one or two generic predicates, frozen scoring, leave-one-group-out


def predicates(rows: Sequence[Mapping[str, Any]], features: Sequence[str]) -> List[Tuple[str, str, float]]:
    """Threshold predicates (feature, ">=" or "<=", value) at every distinct observed value of each feature."""
    out = []
    for feature in features:
        values = sorted({r[feature] for r in rows if r.get(feature) is not None})
        for value in values:
            out.append((feature, ">=", value))
            out.append((feature, "<=", value))
    return out


def holds(row: Mapping[str, Any], predicate: Tuple[str, str, float]) -> bool:
    feature, op, value = predicate
    x = row.get(feature)
    if x is None:
        return False
    return x >= value if op == ">=" else x <= value


def score(rule: Sequence[Tuple[str, str, float]], rows: Sequence[Mapping[str, Any]]) -> Tuple[int, int, int]:
    """(adverse rows the rule allows, primary rows it allows, -len(rule)); a rule is better when it allows no
    adverse row, then more primary rows, then fewer predicates (compared as (-adverse, primary, -size))."""
    allowed = [r for r in rows if all(holds(r, p) for p in rule)]
    return (sum(1 for r in allowed if r["label"] == "ADVERSE"), sum(1 for r in allowed if r["label"] == "PRIMARY"),
            len(rule))


def best_rule(rows: Sequence[Mapping[str, Any]], features: Sequence[str]) -> Dict[str, Any]:
    """The best rule of at most two predicates by :func:`score`; ties by the rule's text (deterministic)."""
    singles = predicates(rows, features)
    best, best_key = None, None
    for size in (1, 2):
        for rule in itertools.combinations(singles, size):
            if size == 2 and rule[0][0] == rule[1][0]:
                continue
            adverse, primary, n = score(rule, rows)
            key = (-adverse, primary, -n, str(rule))
            if best_key is None or key > best_key:
                best, best_key = rule, key
    adverse, primary, _ = score(best, rows) if best else (0, 0, 0)
    return {"rule": [list(p) for p in best] if best else [], "adverse_allowed": adverse, "primary_allowed": primary,
            "primary_rows": sum(1 for r in rows if r["label"] == "PRIMARY"),
            "adverse_rows": sum(1 for r in rows if r["label"] == "ADVERSE")}


def rule_search(rows: Sequence[Mapping[str, Any]], features: Sequence[str]) -> Dict[str, Any]:
    """The best rule on all labelled rows, and for every group left out, the rule fitted on the rest and its counts
    on the group left out (instability is the finding to report, not a rule to ship)."""
    labelled = [r for r in rows if r["label"] in ("PRIMARY", "ADVERSE")]
    out = {"all": best_rule(labelled, features), "leave_one_group_out": {}}
    for group in sorted({r["group"] for r in labelled}):
        fit = best_rule([r for r in labelled if r["group"] != group], features)
        rule = [tuple(p) for p in fit["rule"]]
        held = [r for r in labelled if r["group"] == group]
        adverse, primary, _ = score(rule, held) if rule else (0, 0, 0)
        out["leave_one_group_out"][group] = {"rule": fit["rule"], "held_out_rows": len(held),
                                             "held_out_adverse_allowed": adverse, "held_out_primary_allowed": primary}
    return out


# ------------------------------------------------------------------------------------------------
# Distributions and privacy


def distribution(values: Iterable[Optional[float]]) -> Dict[str, Any]:
    return sx.distribution(list(values))


def percentile(values: Sequence[float], p: float) -> float:
    return sx.percentile(values, p)


def public_check(value: Any, private_values: Iterable[Any] = ()) -> List[str]:
    return sx.public_check(value, private_values)
