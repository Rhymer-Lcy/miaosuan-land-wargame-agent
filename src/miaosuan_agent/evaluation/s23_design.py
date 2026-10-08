"""Sprint 23 offline T2 policy design and opportunity study (``docs/SPRINT23_T2_POLICY_DESIGN.md``): every frozen
rule of the study.

Pure functions over plain data, fixed before the study is run: the independent check of a proposed batch, the
projections of one episode against the recorded history (transported and foot arrival, destination occupancy, the role
of the delivered infantry, the carrier's foregone moves), the readiness rule with its thresholds, and the rule that
builds the one proposed screen. Nothing here reads an engine, a capture or the ledger; nothing here imports the proposed
candidate, so that the batch check is independent of it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import s12_screen as sc

STUDY_ID = "s23-t2-policy-design"
SCHEMA = "miaosuan-s23-design/1"
MOVE, EMBARK, DISEMBARK = 1, 3, 4
INFANTRY, VEHICLE = 1, 2
INFANTRY_SUB, IFV_SUB = 2, 1
#: Sprint 22's documented transition, bound and stacking limit (restated here so that the check does not import the
#: candidate; a test pins them equal to the candidate's).
TRANSITION, BOUND, STACK_LIMIT, PLACES, CHAIN_TRANSITIONS = 75, 150, 4, 2, 3

#: Evidence populations (section 11). H0: baseline-v2 reconstructed on the 8 baseline-v0 mirror replay games, both
#: seats; HH: the baseline-v2 seat of the 4 Sprint 12 head-to-head games; HI: the 3 actual baseline-v2 games against
#: the inert control of Sprint 22's tier 1. Acting-opponent populations: H0 and HH.
POPULATIONS = ("H0", "HH", "HI")
ACTING = ("H0", "HH")

#: The readiness rule's thresholds (section 14), frozen before the study.
READINESS = {
    "min_first_divergence_episodes": 4,
    "min_first_divergence_episodes_acting": 2,
    "min_scenarios": 2,
    "max_saturated_share": "1/4",
    "max_claimant_share": "1/2",
}
DISPOSITIONS = ("T2_DESIGN_INVALID", "T2_NO_GENERALIZABLE_OPPORTUNITY", "T2_UNRESOLVED_INTERACTION_RISK",
                "T2_READY_FOR_SMALL_EXPLORATORY_PROPOSAL")
INVALID, NO_OPPORTUNITY, RISK, READY = DISPOSITIONS
ROLES = {"A": "potential first-capture contributor", "B": "reinforcement of an objective already held",
         "C": "arrival too late to matter under the projected schedule",
         "D": "unclassifiable from the available evidence"}
#: The screen's session ceiling (section 15).
SCREEN_SESSION_CEILING = 3


def rules_digest() -> str:
    frozen = {"readiness": READINESS, "dispositions": DISPOSITIONS, "roles": ROLES, "transition": TRANSITION,
              "bound": BOUND, "stack_limit": STACK_LIMIT, "places": PLACES, "chain": CHAIN_TRANSITIONS,
              "screen_ceiling": SCREEN_SESSION_CEILING, "populations": POPULATIONS, "acting": ACTING}
    return hashlib.sha256(json.dumps(frozen, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------
# the independent batch check (sections 6, 8 and 13)


def _units(raw: Mapping[str, Any], faction: int) -> Tuple[Dict[int, Mapping[str, Any]], Dict[int, Mapping[str, Any]]]:
    own = {u["obj_id"]: u for u in raw.get("operators") or () if u.get("color") == faction}
    aboard = {u["obj_id"]: u for u in raw.get("passengers") or () if u.get("color") == faction}
    return own, aboard


def _listing(raw: Mapping[str, Any], unit: int, action_type: int) -> List[Mapping[str, Any]]:
    valid = raw.get("valid_actions") or {}
    per = valid.get(unit) if unit in valid else valid.get(str(unit))
    per = per or {}
    options = per.get(action_type) if action_type in per else per.get(str(action_type))
    return list(options or ())


def _still(u: Mapping[str, Any]) -> bool:
    return (not (u.get("move_path") or ()) and not (u.get("speed") or 0) and not (u.get("move_to_stop_remain_time") or 0)
            and not (u.get("keep") or 0) and not (u.get("get_on_remain_time") or 0)
            and not (u.get("get_off_remain_time") or 0) and not (u.get("on_board") or 0)
            and not u.get("get_on_partner_id") and not u.get("get_off_partner_id"))


def _infantry_room(car: Mapping[str, Any], aboard: Mapping[int, Mapping[str, Any]]) -> bool:
    types = car.get("valid_passenger_types") or ()
    if INFANTRY_SUB not in types:
        return False
    if any((aboard.get(p) or {}).get("type") == INFANTRY for p in car.get("passenger_ids") or ()):
        return False
    caps = car.get("max_passenger_nums") or {}
    cap = caps.get(INFANTRY_SUB, caps.get(str(INFANTRY_SUB)))
    return isinstance(cap, int) and cap >= 1


def _ground(own: Mapping[int, Mapping[str, Any]], hex_: Any) -> int:
    return sum(1 for u in own.values() if u.get("type") in (INFANTRY, VEHICLE) and u.get("cur_hex") == hex_)


def eligible(raw: Mapping[str, Any], seat: int, faction: int, base: Sequence[Mapping[str, Any]], inf: int, car: int,
             free_flow: Callable[[Mapping[str, Any], Sequence[Any]], Optional[int]]) -> Tuple[List[str], Dict[str, Any]]:
    """Conditions 1 to 8 for one pair, recomputed from the raw seat observation and baseline-v2's actions; the failed
    conditions and the projected times."""
    own, aboard = _units(raw, faction)
    controlled = set(((raw.get("role_and_grouping_info") or {}).get(seat)
                      or (raw.get("role_and_grouping_info") or {}).get(str(seat)) or {}).get("operators") or ())
    problems: List[str] = []
    i, c = own.get(inf), own.get(car)
    if i is None or c is None or (i.get("type"), i.get("sub_type")) != (INFANTRY, INFANTRY_SUB) \
            or (c.get("type"), c.get("sub_type")) != (VEHICLE, IFV_SUB):
        return ["not an own infantry and an own infantry fighting vehicle on the ground"], {}
    if i.get("cur_hex") != c.get("cur_hex"):
        problems.append("not co-located")
    if not (_still(i) and _still(c)) or inf not in controlled or car not in controlled:
        problems.append("not both stationary, unsuppressed, out of transition and controlled")
    if not any(set(o) == {"target_obj_id"} and o.get("target_obj_id") == car for o in _listing(raw, inf, EMBARK)):
        problems.append("embark naming the carrier not listed")
    mine = [a for a in base if a.get("obj_id") == inf]
    theirs = [a for a in base if a.get("obj_id") == car]
    if not (len(mine) == 1 == len(theirs) and mine[0].get("type") == MOVE == theirs[0].get("type")
            and mine[0].get("move_path") and theirs[0].get("move_path")):
        problems.append("baseline-v2 does not move both")
        return problems, {}
    dest = list(theirs[0]["move_path"])[-1]
    cities = {x.get("coord") for x in raw.get("cities") or ()}
    if list(mine[0]["move_path"])[-1] != dest or dest not in cities:
        problems.append("not the same objective")
    t_inf, t_car = free_flow(i, mine[0]["move_path"]), free_flow(c, theirs[0]["move_path"])
    now, max_step = (raw.get("time") or {}).get("cur_step"), (raw.get("time") or {}).get("max_step")
    facts: Dict[str, Any] = {"destination": dest}
    if t_inf is None or t_car is None:
        problems.append("free-flow time unreadable")
    else:
        transported = now + CHAIN_TRANSITIONS * TRANSITION + t_car
        foot = now + t_inf
        facts.update(transported=transported, foot=foot, saving=foot - transported, unable=foot >= max_step,
                     infantry_free_flow=t_inf, carrier_free_flow=t_car)
        if not (transported < max_step and foot - transported > 0):
            problems.append("no positive feasible saving")
    if not _infantry_room(c, aboard):
        problems.append("no infantry room")
    return problems, facts


def batch_problems(raw: Mapping[str, Any], seat: int, faction: int, base: Sequence[Mapping[str, Any]],
                   live: Sequence[Mapping[str, Any]], batch: Sequence[Tuple[int, int]],
                   free_flow: Callable[[Mapping[str, Any], Sequence[Any]], Optional[int]],
                   reserved: Optional[Mapping[Any, int]] = None) -> List[str]:
    """Whether a batch of new pairs proposed at one decision (``batch``: (infantry, carrier)), with the emitted actions
    ``live`` against baseline-v2's ``base``, is internally consistent: every pair meets conditions 1 to 8; no unit is
    in two pairs; every destination admits its pairs (current own ground units + ``reserved`` + 2 per pair <= 4); only
    the registered edits differ from baseline-v2 (the infantry's MOVE replaced in place by the listed embark, the
    carrier's MOVE withheld), in baseline-v2's order, with no duplicate action; and no further pair that meets
    conditions 1 to 8, has both units free and fits its destination was left unselected."""
    problems: List[str] = []
    own, _ = _units(raw, faction)
    units = [u for pair in batch for u in pair]
    if len(set(units)) != len(units):
        problems.append("a unit is in two pairs")
    per_dest: Dict[Any, int] = {}
    for inf, car in batch:
        failed, facts = eligible(raw, seat, faction, base, inf, car, free_flow)
        problems.extend(f"pair fails: {f}" for f in failed)
        if "destination" in facts:
            per_dest[facts["destination"]] = per_dest.get(facts["destination"], 0) + 1
    reserved = reserved or {}
    for dest, n in per_dest.items():
        if _ground(own, dest) + reserved.get(dest, 0) + PLACES * n > STACK_LIMIT:
            problems.append("a destination is over-committed")
    infantry = {inf: car for inf, car in batch}
    carriers = {car for _, car in batch}
    expected: List[str] = []
    for a in base:
        unit = a.get("obj_id")
        if unit in infantry and a.get("type") == MOVE:
            expected.append(sc_canonical({"actor": seat, "obj_id": unit, "type": EMBARK,
                                          "target_obj_id": infantry[unit]}))
        elif unit in carriers and a.get("type") == MOVE:
            continue
        else:
            expected.append(sc_canonical(a))
    got = [sc_canonical(a) for a in live]
    if got != expected:
        problems.append("the emitted actions are not baseline-v2's with exactly the registered edits")
    if len(set(got)) != len(got):
        problems.append("a duplicate action")
    taken = set(units)
    for inf in sorted(u for u, x in own.items() if (x.get("type"), x.get("sub_type")) == (INFANTRY, INFANTRY_SUB)):
        for car in sorted(u for u, x in own.items() if (x.get("type"), x.get("sub_type")) == (VEHICLE, IFV_SUB)):
            if inf in taken or car in taken or own[inf].get("cur_hex") != own[car].get("cur_hex"):
                continue
            failed, facts = eligible(raw, seat, faction, base, inf, car, free_flow)
            if failed:
                continue
            dest = facts["destination"]
            if _ground(own, dest) + reserved.get(dest, 0) + PLACES * (per_dest.get(dest, 0) + 1) <= STACK_LIMIT:
                problems.append("an admissible pair with both units free was left unselected")
    return problems


def sc_canonical(action: Mapping[str, Any]) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True, separators=(",", ":"), default=repr)


# ------------------------------------------------------------------------------------------------
# recorded history and the projections of one episode (sections 7 to 10)


@dataclass
class Moment:
    """What the study keeps of one recorded decision of one side: the step, the objective flags, own ground units per
    hex, every own ground unit's hex and whether it has a move path, and baseline-v2's MOVE ends per unit."""

    k: int
    cur_step: int
    flags: Dict[Any, Any]
    ground: Dict[Any, int]
    where: Dict[int, Tuple[Any, bool]]
    orders: Dict[int, Any] = field(default_factory=dict)


def group_runs(selections: Sequence[Tuple[int, Sequence[Tuple[int, int]]]]) -> List[Tuple[int, Tuple[int, int]]]:
    """Recorded-state episodes: each maximal run of consecutive decisions selecting the same pair is one episode,
    reported at its first decision. ``selections``: (decision, selected pairs) for the decisions with a selection, in
    order."""
    starts: List[Tuple[int, Tuple[int, int]]] = []
    previous: Tuple[Optional[int], set] = (None, set())
    for k, selected in selections:
        for pair in selected:
            if not (previous[0] == k - 1 and tuple(pair) in previous[1]):
                starts.append((k, tuple(pair)))
        previous = (k, {tuple(p) for p in selected})
    return starts


def first_at(history: Sequence[Moment], start: int, step: int) -> Optional[int]:
    """The index of the first moment at or after ``start`` whose step is at least ``step``."""
    for j in range(start, len(history)):
        if history[j].cur_step >= step:
            return j
    return None


def others_on(moment: Moment, dest: Any, pair: Sequence[int]) -> int:
    """Own ground units on ``dest`` other than the pair's two units."""
    return moment.ground.get(dest, 0) - sum(1 for u in pair if (moment.where.get(u) or (None,))[0] == dest)


def project(history: Sequence[Moment], k: int, faction: int, max_step: int, pair: Tuple[int, int], dest: Any,
            carrier_ff: int, infantry_ff: int) -> Dict[str, Any]:
    """The projections of one episode triggered at ``history[k]`` (descriptive; after the trigger every recorded state
    is off-policy for the candidate)."""
    s = history[k].cur_step
    inf, car = pair
    arrival = s + TRANSITION + carrier_ff
    delivery = s + CHAIN_TRANSITIONS * TRANSITION + carrier_ff
    foot = s + infantry_ff
    out: Dict[str, Any] = {"trigger_step": s, "carrier_free_flow": carrier_ff, "infantry_free_flow": infantry_ff,
                           "projected_carrier_arrival": arrival, "projected_delivery": delivery, "foot_arrival": foot,
                           "projected_saving": foot - delivery, "unable_on_foot": foot >= max_step,
                           "on_objective_gain": min(foot, max_step) - delivery,
                           "occupancy_at_trigger": history[k].ground.get(dest, 0)}
    j = first_at(history, k, arrival)
    out["others_at_projected_arrival"] = None if j is None else others_on(history[j], dest, pair)
    out["saturated_at_arrival"] = j is not None and others_on(history[j], dest, pair) >= STACK_LIMIT - 1
    window = [m for m in history[k:] if arrival <= m.cur_step <= arrival + BOUND]
    out["saturated_through_settle_bound"] = bool(window) and all(others_on(m, dest, pair) >= STACK_LIMIT - 1
                                                                 for m in window)
    out["role"] = role(history, k, faction, max_step, dest, delivery)
    out.update(carrier_hold(history, k, faction, car, dest))
    return out


def role(history: Sequence[Moment], k: int, faction: int, max_step: int, dest: Any, delivery: int) -> str:
    """A: the side never owned the destination up to the projected delivery; B: the side owns it at that step; C: the
    projected delivery is at or after the end; D: otherwise (owned earlier and not at that step, or no recorded state
    at that step)."""
    if delivery >= max_step:
        return "C"
    j = first_at(history, k, delivery)
    if j is None:
        return "D"
    if history[j].flags.get(dest) == faction:
        return "B"
    if all(m.flags.get(dest) != faction for m in history[: j + 1]):
        return "A"
    return "D"


def carrier_hold(history: Sequence[Moment], k: int, faction: int, car: int, dest: Any) -> Dict[str, Any]:
    """The carrier's recorded behaviour after its own recorded arrival on the destination: baseline-v2's MOVE orders
    for it in the next ``2 * TRANSITION`` steps (the expected destination hold: settling and disembark), the delay of
    the first, whether the first goes to another objective the side does not hold at that decision (a potential
    claimant elsewhere), and whether the destination was held at the carrier's arrival."""
    arrived = next((j for j in range(k + 1, len(history))
                    if history[j].where.get(car) == (dest, False)), None)
    out: Dict[str, Any] = {"carrier_arrived_in_history": arrived is not None, "first_move_delay": None,
                           "moves_in_expected_hold": 0, "claimant_elsewhere": False, "destination_held_at_arrival": None,
                           "projected_suppressed_decisions": 0}
    if arrived is None:
        return out
    t0 = history[arrived].cur_step
    out["destination_held_at_arrival"] = history[arrived].flags.get(dest) == faction
    orders = [(m, m.orders[car]) for m in history[arrived:] if car in m.orders and m.cur_step <= t0 + 2 * TRANSITION]
    out["moves_in_expected_hold"] = len(orders)
    if orders:
        moment, end = orders[0]
        out["first_move_delay"] = moment.cur_step - t0
        out["claimant_elsewhere"] = end != dest and end in moment.flags and moment.flags.get(end) != faction
        out["projected_suppressed_decisions"] = 2 * TRANSITION - (moment.cur_step - t0)
    return out


# ------------------------------------------------------------------------------------------------
# readiness (section 14) and the screen (section 15)


def share(part: int, whole: int) -> Fraction:
    return Fraction(part, whole) if whole else Fraction(0)


def disposition(invalid: Sequence[str], episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """First match: DESIGN_INVALID (any fidelity, consistency or batch problem); NO_GENERALIZABLE_OPPORTUNITY (fewer
    first-divergence episodes than the minimum, fewer in acting-opponent populations, or fewer scenarios);
    UNRESOLVED_INTERACTION_RISK (saturated-at-arrival share or claimant share above its maximum); else READY.
    ``episodes``: the first-divergence episodes with ``population``, ``scenario``, ``saturated_at_arrival`` and
    ``claimant_elsewhere``."""
    if invalid:
        return {"disposition": INVALID, "problems": list(invalid)[:20], "problem_count": len(invalid)}
    n = len(episodes)
    acting = sum(1 for e in episodes if e["population"] in ACTING)
    scenarios = len({e["scenario"] for e in episodes})
    counts = {"first_divergence_episodes": n, "acting_opponent_episodes": acting, "scenarios": scenarios}
    short = [name for name, value, floor in (
        ("first_divergence_episodes", n, READINESS["min_first_divergence_episodes"]),
        ("acting_opponent_episodes", acting, READINESS["min_first_divergence_episodes_acting"]),
        ("scenarios", scenarios, READINESS["min_scenarios"])) if value < floor]
    if short:
        return {"disposition": NO_OPPORTUNITY, "below_minimum": short, **counts}
    saturated = share(sum(1 for e in episodes if e["saturated_at_arrival"]), n)
    claimant = share(sum(1 for e in episodes if e["claimant_elsewhere"]), n)
    shares = {"saturated_share": str(saturated), "claimant_share": str(claimant)}
    over = [name for name, value, ceiling in (("saturated_share", saturated, READINESS["max_saturated_share"]),
                                              ("claimant_share", claimant, READINESS["max_claimant_share"]))
            if value > Fraction(ceiling)]
    if over:
        return {"disposition": RISK, "above_maximum": over, **counts, **shares}
    return {"disposition": READY, **counts, **shares}


def screen(episodes: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The one proposed screen, built by the frozen rule from the first-divergence evidence (only if READY).

    Phase M (concurrency mechanism, deterministic): if an inert-control (HI) side-game's first-divergence batch holds
    two or more pairs, the HI configuration with the largest batch (then the game label) is played once with the
    candidate in that seat against the inert control; otherwise no phase M. Phase H (acting opponent): the scenario
    with the most first-divergence episodes in H0 or HH (ties: HH before H0, then the scenario id), played head to head
    against baseline-v2 once in each seat order. ``batches``: one row per side-game with ``population``, ``game``,
    ``scenario``, ``condition``, ``side`` and ``batch_size``."""
    m = [b for b in batches if b["population"] == "HI" and b["batch_size"] >= 2]
    phase_m = None
    if m:
        best = sorted(m, key=lambda b: (-b["batch_size"], b["game"]))[0]
        phase_m = {"scenario": best["scenario"], "condition": best["condition"], "candidate_side": best["side"],
                   "opponent": "inert control", "games": 1, "source": best["game"]}
    acting: Dict[Tuple[str, str], int] = {}
    for e in episodes:
        if e["population"] in ACTING:
            acting[(e["population"], e["scenario"])] = acting.get((e["population"], e["scenario"]), 0) + 1
    by_scenario: Dict[str, Tuple[int, int]] = {}
    for (population, scenario), n in acting.items():
        total, hh = by_scenario.get(scenario, (0, 0))
        by_scenario[scenario] = (total + n, hh + (n if population == "HH" else 0))
    if not by_scenario:
        return None
    scenario = sorted(by_scenario, key=lambda s: (-by_scenario[s][0], -by_scenario[s][1], s))[0]
    phase_h = {"scenario": scenario, "conditions": ["H1", "H2"], "opponent": "baseline-v2", "games": 2,
               "first_divergence_episodes": by_scenario[scenario][0]}
    sessions = (phase_m["games"] if phase_m else 0) + phase_h["games"]
    if sessions > SCREEN_SESSION_CEILING:
        raise ValueError("the screen exceeds its session ceiling")
    return {"phase_m": phase_m, "phase_h": phase_h, "sessions": sessions}


# ------------------------------------------------------------------------------------------------
# public sanitization


def mask_numbers(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {k: mask_numbers(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [mask_numbers(v) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return None
    return node


def public_problems(data: Any, private_values: Iterable[Any]) -> List[str]:
    """The project's sanitizer: forbidden keys anywhere, and the private unit ids and hexes as keys or words of strings.
    Numeric leaves are aggregates by construction and are not compared (Sprint 18's reading: ids and hexes overlap the
    range of ordinary counts)."""
    return sc.privacy_problems(data) + sc.privacy_problems(mask_numbers(data), sorted(private_values))


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
