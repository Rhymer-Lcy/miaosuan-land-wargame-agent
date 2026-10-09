"""Sprint 30 historical feasibility preflight of ``t13-keep-one-k1`` (``docs/SPRINT30_T13_K1_PILOT.md``, section 4).

Offline, before any engine session. The candidate's rule (``experiments/t13_keep_one_k1.py``, frozen with this module)
is applied to recorded seat observations and ``baseline-v2``'s decision on each of them, in three populations of
different evidence strength that are never pooled into one figure:

* **HH**: the ``baseline-v2`` seat of the four Sprint 12 head-to-head games in 2130511121 (two per seat colour; the
  opponent was the T9-v3 candidate, not ``baseline-v2``). Genuine ``baseline-v2`` trajectories.
* **HI**: the three Sprint 10 games of ``baseline-v2`` against the inert control (2120531121 C3, 1930331196 C3,
  1930331196 C2). Genuine ``baseline-v2`` trajectories.
* **H0**: the eight replay-corpus games, both seats; the recorded actions are ``baseline-v0``'s and ``baseline-v2``'s
  decisions are reconstructed on those states (off-policy).

The inputs are Sprint 23's committed and pinned job list, read through Sprint 23's own loader and its ``baseline-v2``
reconstruction, unchanged. Everything this module decides is fixed before the preflight runs:

* **Fidelity anchors** (published by Sprints 18, 21 and 23): H0 33,696 decisions, 33,680 play decisions and 123
  decisions where reconstructed ``baseline-v2`` differs from the recorded actions; HH 11,524 and HI 8,643 decisions,
  every one equal to the recorded seat. Any miss makes the preflight ``K1_PREFLIGHT_INVALID``.
* **Independent check** (:func:`independent_problems`): at every decision, a restatement of the rule written apart from
  the candidate's code (its own reading of the observation, its own free-flow sum over the cost graph) must explain
  every withheld action and find no missed trigger. Any finding makes the preflight invalid.
* **First divergence**: a side's first decision at which the candidate's list differs from ``baseline-v2``'s. It is a
  valid first-divergence fact in HH and HI (genuine trajectories), and in H0 only when the recorded actions equal
  ``baseline-v2``'s at every earlier decision of that seat. Later withholdings lie on off-policy recorded states and
  are post-divergence diagnostics only.
* **Verified opportunity**: a side-game with a valid first divergence and no independent-check finding.
* **Stop** (:func:`disposition`, first match): ``K1_PREFLIGHT_INVALID`` (an anchor, an integrity check or the
  independent check fails); ``K1_PREFLIGHT_INADEQUATE`` (no verified opportunity among the HH red side-games, or none
  among the HH blue side-games, or fewer than two HI configurations with one): no engine session is opened;
  ``K1_PREFLIGHT_PASS``.
* **Inert configurations of the pilot** (:func:`select_inert`): the first two of :data:`INERT_PRIORITY` that have a
  verified opportunity. The order is fixed now: 2120531121 C3 first (the configuration in which withholding moves
  already cost an objective, T9-v1 as blue against the inert control), then 1930331196 C2 (another scenario and the
  other seat colour), then 1930331196 C3.

Departure facts (descriptive): for each held objective at each play decision the rule's outcome; a **departure
episode** is a maximal run of consecutive play decisions of one side at which one held objective's occupants all
depart (outcomes ``all_moving``, ``no_eligible_holder``, ``no_travel_time``, ``withheld``), described by its first
decision. Onward labels are historical, read on the recorded trajectory after the decision, never online inputs.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts
from ..decision.routing import move_mode
from ..experiments import t13_keep_one_k1 as k1
from .s12_timeline import labels

STUDY_ID = "s30-t13-k1"
SCHEMA = "miaosuan-s30-preflight/1"
POPULATIONS = ("H0", "HH", "HI")
GENUINE = ("HH", "HI")
H2H_SCENARIO = "2130511121"
#: Inert-control configurations of the pilot, in priority order (scenario, condition; C3 = baseline-v2 blue, C2 =
#: baseline-v2 red).
INERT_PRIORITY = (("2120531121", "C3"), ("1930331196", "C2"), ("1930331196", "C3"))
INERT_GAMES_NEEDED = 2
DISPOSITIONS = ("K1_PREFLIGHT_INVALID", "K1_PREFLIGHT_INADEQUATE", "K1_PREFLIGHT_PASS")
INVALID, INADEQUATE, PASS = DISPOSITIONS
ANCHORS = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123,
           "HH decisions": 11524, "HI decisions": 8643}
DEPARTING = ("all_moving", "no_eligible_holder", "no_travel_time", "withheld")
STACK_LIMIT = 4
PLAY = 2
MOVE, SHOOT = 1, 2
CLASS = {1: "infantry", 2: "vehicle"}


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def unit_class(u: Mapping[str, Any]) -> str:
    if u.get("type") == 2 and u.get("sub_type") == 3:
        return "artillery"
    return CLASS.get(u.get("type"), "other")


# ------------------------------------------------------------------------------------------------
# independent restatement of the rule


def free_flow(costs: MoveCosts, u: Mapping[str, Any], route: Sequence[Any]) -> Optional[int]:
    """The free-flow time of ``route`` from the unit's hex, summed here from the cost graph: per hex
    ``int(720 / basic_speed * entry cost + 0.5)``; ``None`` when the mode, speed, a hex or an edge is unreadable."""
    mode = move_mode(u.get("type"), u.get("move_state")) if is_int(u.get("type")) else None
    speed = u.get("basic_speed")
    if mode is None or not is_int(u.get("cur_hex")) or not route \
            or not (isinstance(speed, (int, float)) and not isinstance(speed, bool) and speed > 0):
        return None
    total, here = 0, u["cur_hex"]
    for nxt in route:
        cost = costs.neighbours(mode, here).get(nxt) if is_int(nxt) else None
        if not (isinstance(cost, (int, float)) and cost > 0):
            return None
        total += int(720.0 / speed * cost + 0.5)
        here = nxt
    return total


def removed_indices(baseline: Sequence[Mapping[str, Any]], live: Sequence[Mapping[str, Any]]) -> Optional[List[int]]:
    """The positions of ``baseline`` absent from ``live`` when ``live`` is ``baseline`` with some entries removed and
    the rest in order; ``None`` otherwise."""
    out, j = [], 0
    for i, action in enumerate(baseline):
        if j < len(live) and dict(live[j]) == dict(action):
            j += 1
        else:
            out.append(i)
    return out if j == len(live) else None


def holder_ok(u: Mapping[str, Any], acts: Sequence[Mapping[str, Any]], centre: int) -> bool:
    """A stationary occupant without route or transition whose only ``baseline-v2`` action is a MOVE leaving the
    centre."""
    if positive(u.get("speed")) or u.get("move_path"):
        return False
    if u.get("stop") == 0 or any(positive(u.get(f)) for f in ("move_to_stop_remain_time", "change_state_remain_time",
                                                             "get_on_remain_time", "get_off_remain_time")):
        return False
    if len(acts) != 1 or acts[0].get("type") != MOVE:
        return False
    route = acts[0].get("move_path")
    return isinstance(route, (list, tuple)) and len(route) > 0 and all(is_int(h) for h in route) \
        and route[-1] != centre


def independent_problems(raw: Mapping[str, Any], faction: int, baseline: Sequence[Mapping[str, Any]],
                         live: Sequence[Mapping[str, Any]], costs: MoveCosts) -> List[str]:
    """Every difference between ``baseline-v2``'s list and the candidate's that the registered rule does not explain,
    and every objective at which the rule should have withheld and did not."""
    removed = removed_indices(baseline, live)
    if removed is None:
        return ["the candidate's list is not baseline-v2's with entries removed in order"]
    stage = (raw.get("time") or {}).get("stage")
    if stage != PLAY:
        return ["an action was removed outside the play stage"] if removed else []
    held = {c.get("coord") for c in raw.get("cities") or () if isinstance(c, Mapping) and c.get("flag") == faction}
    ground = [u for u in raw.get("operators") or () if isinstance(u, Mapping) and u.get("color") == faction
              and u.get("type") in (1, 2) and is_int(u.get("obj_id"))]
    acts: Dict[Any, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for a in baseline:
        acts[a.get("obj_id")].append(a)
    expected: Dict[int, Tuple[Any, int]] = {}
    for centre in held:
        here = [u for u in ground if u.get("cur_hex") == centre]
        if not here:
            continue
        leaving = [u for u in here if u.get("move_path") or any(a.get("type") == MOVE for a in acts[u["obj_id"]])]
        if len(leaving) != len(here) or not any(any(a.get("type") == MOVE for a in acts[u["obj_id"]]) for u in here):
            continue
        rated = [(free_flow(costs, u, acts[u["obj_id"]][0].get("move_path")), u["obj_id"]) for u in here
                 if holder_ok(u, acts[u["obj_id"]], centre)]
        rated = [(t, uid) for t, uid in rated if t is not None]
        if rated:
            best = sorted(rated, key=lambda r: (-r[0], r[1]))[0]
            expected[centre] = (best[1], best[0])
    problems = []
    got: Dict[int, Any] = {}
    for i in removed:
        a = baseline[i]
        where = next((u.get("cur_hex") for u in ground if u["obj_id"] == a.get("obj_id")), None)
        if a.get("type") != MOVE:
            problems.append("a removed action is not a MOVE")
        elif where not in expected or expected[where][0] != a.get("obj_id"):
            problems.append("a removed MOVE is not the registered holder's")
        elif where in got:
            problems.append("two MOVEs removed at one objective")
        got[where] = a.get("obj_id")
    for centre in sorted(set(expected) - set(got)):
        problems.append("a triggered objective with an eligible holder kept every MOVE")
    return problems


# ------------------------------------------------------------------------------------------------
# one side


def first_enemy_step(raws: Sequence[Mapping[str, Any]], faction: int) -> Optional[int]:
    for raw in raws:
        if any(isinstance(u, Mapping) and u.get("color") not in (faction, None) for u in raw.get("operators") or ()):
            return (raw.get("time") or {}).get("cur_step")
    return None


def analyse_side(meta: Mapping[str, Any], stream: Iterable[Tuple[Mapping[str, Any], Sequence[Mapping[str, Any]],
                                                                Sequence[Mapping[str, Any]]]],
                 costs: MoveCosts, travel: k1.Travel) -> Tuple[Dict[str, Any], set]:
    """One side: ``stream`` yields (raw seat observation, recorded actions, ``baseline-v2``'s actions) per decision.
    Returns the side's private summary (unit ids and hexes inside ``private``) and the private values seen."""
    faction = meta["faction"]
    population = meta["population"]
    private: set = set()
    decisions = play = differs = 0
    first_difference = None
    status_counts: collections.Counter = collections.Counter()
    level_counts: collections.Counter = collections.Counter()
    problems: List[Tuple[int, str]] = []
    withholdings: List[Dict[str, Any]] = []
    runs: Dict[int, Dict[str, Any]] = {}
    episodes: List[Dict[str, Any]] = []
    flags_by_k: List[Dict[Any, Any]] = []
    where_by_k: List[Dict[Any, Any]] = []
    raws_light: List[Dict[str, Any]] = []
    values: Dict[Any, Any] = {}
    first_shot = None
    for k, (raw, recorded, base) in enumerate(stream):
        decisions += 1
        base = [dict(a) for a in base]
        if [dict(a) for a in recorded] != base:
            differs += 1
            first_difference = k if first_difference is None else first_difference
        time_info = raw.get("time") or {}
        step, stage = time_info.get("cur_step"), time_info.get("stage")
        for c in raw.get("cities") or ():
            if isinstance(c, Mapping):
                values.setdefault(c.get("coord"), c.get("value"))
                private.add(c.get("coord"))
        own = {}
        for u in raw.get("operators") or ():
            if isinstance(u, Mapping):
                private.update(x for x in (u.get("obj_id"), u.get("cur_hex")) if x is not None)
                private.update(u.get("move_path") or ())
                if u.get("color") == faction:
                    own[u.get("obj_id")] = u.get("cur_hex")
        for a in base:
            private.update(a.get("move_path") or ())
        flags_by_k.append({c.get("coord"): c.get("flag") for c in raw.get("cities") or () if isinstance(c, Mapping)})
        where_by_k.append(own)
        raws_light.append({"time": {"cur_step": step},
                           "operators": [{"color": u.get("color")} for u in raw.get("operators") or ()
                                         if isinstance(u, Mapping)]})
        if first_shot is None and any(a.get("type") == SHOOT for a in base):
            first_shot = step
        if stage == PLAY:
            play += 1
        result = k1.decide(raw, faction, base, travel)
        live = [dict(a) for a in result.actions]
        for p in independent_problems(raw, faction, base, live, costs):
            problems.append((k, p))
        seen = set()
        for c in result.checks:
            status_counts[c.status] += 1
            seen.add(c.centre)
            run = runs.get(c.centre)
            if c.status in DEPARTING:
                if run is None:
                    first = c.occupants
                    run = {"start_k": k, "start_step": step, "centre": c.centre, "length": 0, "statuses": set(),
                           "first_status": c.status, "occupants": len(first),
                           "moving": sum(1 for o in first if o.departs and not o.by_move),
                           "ordered_eligible": sum(1 for o in first if o.level == k1.ELIGIBLE),
                           "ordered_ineligible": dict(collections.Counter(o.level for o in first
                                                                          if o.by_move and o.level != k1.ELIGIBLE))}
                    runs[c.centre] = run
                run["length"] += 1
                run["statuses"].add(c.status)
                for o in c.occupants:
                    if o.by_move:
                        level_counts[o.level] += 1
            elif run is not None:
                episodes.append(runs.pop(c.centre))
            if c.status == "withheld":
                holder = next(u for u in raw["operators"] if isinstance(u, Mapping) and u.get("obj_id") == c.selected
                              and u.get("color") == faction)
                route = list(base[c.index].get("move_path") or ())
                transit = sum(1 for i, a in enumerate(base) if i != c.index and a.get("type") == MOVE
                              and c.centre in (a.get("move_path") or ()))
                transit += sum(1 for u in raw.get("operators") or () if isinstance(u, Mapping)
                               and u.get("color") == faction and u.get("type") in (1, 2)
                               and u.get("cur_hex") != c.centre and c.centre in (u.get("move_path") or ()))
                withholdings.append({"k": k, "step": step, "centre": c.centre, "unit": c.selected,
                                     "class": unit_class(holder), "travel": c.travel,
                                     "occupants": len(c.occupants),
                                     "eligible": sum(1 for o in c.occupants if o.level == k1.ELIGIBLE),
                                     "destination": route[-1] if route else None, "routes_through_centre": transit})
        for centre in list(runs):
            if centre not in seen:
                episodes.append(runs.pop(centre))
    episodes.extend(runs.values())
    names = labels({c: v for c, v in values.items() if is_int(c)})
    first = withholdings[0] if withholdings else None
    valid = first is not None and (population in GENUINE or first_difference is None
                                   or first_difference >= first["k"])
    onward = None
    if first is not None:
        dest, unit, k0 = first["destination"], first["unit"], first["k"]
        owned_before = any(flags_by_k[j].get(dest) == faction for j in range(k0 + 1))
        first_owner = None
        lost_after = None
        if dest in names and not owned_before:
            j = next((j for j in range(k0 + 1, len(flags_by_k)) if flags_by_k[j].get(dest) == faction), None)
            first_owner = None if j is None else where_by_k[j].get(unit) == dest
        j = next((j for j in range(k0 + 1, len(flags_by_k)) if flags_by_k[j].get(first["centre"]) != faction), None)
        if j is not None:
            lost_after = raws_light[j]["time"]["cur_step"] - first["step"]
        enemy = first_enemy_step(raws_light, faction)
        onward = {"destination": names.get(dest, "not an objective"),
                  "destination_owned_at_or_before_the_decision": owned_before,
                  "holder_first_owner_of_its_destination_on_the_record": first_owner,
                  "recorded_objective_lost_steps_after": lost_after,
                  "first_enemy_seen_step": enemy,
                  "prefix_before_any_enemy_was_seen": enemy is None or enemy > first["step"],
                  "first_own_shot_step": first_shot,
                  "potential_congestion": 1 + first["routes_through_centre"] > STACK_LIMIT}
    distinct_runs = [{"first_status": e["first_status"], "length": e["length"],
                      "statuses": sorted(e["statuses"]), "occupants": e["occupants"], "moving": e["moving"],
                      "ordered_eligible": e["ordered_eligible"], "ordered_ineligible": e["ordered_ineligible"],
                      "actionable": "withheld" in e["statuses"], "start_step": e["start_step"],
                      "objective": names.get(e["centre"])} for e in sorted(episodes, key=lambda e: (e["start_k"],
                                                                                                 e["centre"]))]
    summary = {"population": population, "label": meta["label"], "scenario": meta["scenario"],
               "condition": meta.get("condition"), "colour": "red" if faction == 0 else "blue",
               "decisions": decisions, "play_decisions": play, "baseline_v2_differs_from_recorded": differs,
               "independent_check_findings": len(problems), "outcomes": dict(sorted(status_counts.items())),
               "ordered_occupant_levels": dict(sorted(level_counts.items())),
               "withholding_decisions": len({w["k"] for w in withholdings}), "withholdings": len(withholdings),
               "departure_episodes": distinct_runs,
               "first_divergence": None if first is None else {
                   "decision": first["k"], "step": first["step"], "valid": valid,
                   "objective": names.get(first["centre"]), "holder_class": first["class"],
                   "holder_travel_steps": first["travel"], "occupants": first["occupants"],
                   "eligible": first["eligible"], "routes_through_centre": first["routes_through_centre"],
                   **(onward or {})},
               "verified_opportunity": bool(valid and not problems),
               "post_divergence_withholding_decisions": len({w["k"] for w in withholdings if first and w["k"] > first["k"]}),
               "private": {"problems": problems[:50], "withholdings": withholdings, "first_difference": first_difference}}
    return summary, private


# ------------------------------------------------------------------------------------------------
# the study's decision


def select_inert(sides: Sequence[Mapping[str, Any]]) -> List[Tuple[str, str]]:
    """The first :data:`INERT_GAMES_NEEDED` configurations of :data:`INERT_PRIORITY` with a verified opportunity."""
    ok = {(s["scenario"], s["condition"]) for s in sides if s["population"] == "HI" and s["verified_opportunity"]}
    return [c for c in INERT_PRIORITY if c in ok][:INERT_GAMES_NEEDED]


def disposition(anchors_ok: bool, sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    reasons = []
    if not anchors_ok:
        reasons.append("a fidelity anchor is not reproduced")
    if any(s["independent_check_findings"] for s in sides):
        reasons.append("the independent check found an unexplained or missed withholding")
    if reasons:
        return {"disposition": INVALID, "reasons": reasons, "inert_configurations": []}
    hh = {colour: [s for s in sides if s["population"] == "HH" and s["colour"] == colour] for colour in ("red", "blue")}
    inert = select_inert(sides)
    for colour, group in hh.items():
        if len(group) != 2:
            reasons.append(f"the HH {colour} side-games are not the two registered ones")
        elif not any(s["verified_opportunity"] for s in group):
            reasons.append(f"no verified first-divergence opportunity in the HH {colour} side-games")
    if len(inert) < INERT_GAMES_NEEDED:
        reasons.append("fewer HI configurations with a verified opportunity than the pilot's inert games")
    if reasons:
        return {"disposition": INADEQUATE, "reasons": reasons, "inert_configurations": [list(c) for c in inert]}
    return {"disposition": PASS, "reasons": [], "inert_configurations": [list(c) for c in inert]}


def public_side(s: Mapping[str, Any]) -> Dict[str, Any]:
    """A side's public summary: its departure episodes aggregated (the rows stay private)."""
    out = {k: v for k, v in s.items() if k not in ("private", "departure_episodes")}
    episodes = s["departure_episodes"]
    out["departure_episodes"] = {
        "count": len(episodes),
        "by_first_outcome": dict(sorted(collections.Counter(e["first_status"] for e in episodes).items())),
        "with_a_withholding": sum(1 for e in episodes if e["actionable"]),
        "units_already_moving_at_start": sum(e["moving"] for e in episodes),
        "stationary_eligible_units_ordered_at_start": sum(e["ordered_eligible"] for e in episodes)}
    return out


def pooled(sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    outcomes: collections.Counter = collections.Counter()
    levels: collections.Counter = collections.Counter()
    first_status: collections.Counter = collections.Counter()
    actionable = moving_units = eligible_units = 0
    for s in sides:
        outcomes.update(s["outcomes"])
        levels.update(s["ordered_occupant_levels"])
        for e in s["departure_episodes"]:
            first_status[e["first_status"]] += 1
            actionable += e["actionable"]
            moving_units += e["moving"]
            eligible_units += e["ordered_eligible"]
    return {"side_games": len(sides), "objective_decision_outcomes": dict(sorted(outcomes.items())),
            "departure_episodes": sum(len(s["departure_episodes"]) for s in sides),
            "departure_episodes_by_first_outcome": dict(sorted(first_status.items())),
            "departure_episodes_with_a_withholding": actionable,
            "units_already_moving_at_episode_start": moving_units,
            "stationary_eligible_units_ordered_at_episode_start": eligible_units,
            "ordered_occupant_levels": dict(sorted(levels.items())),
            "side_games_with_a_first_divergence": sum(1 for s in sides if s["first_divergence"]),
            "valid_first_divergences": sum(1 for s in sides if s["first_divergence"] and s["first_divergence"]["valid"]),
            "verified_opportunities": sum(1 for s in sides if s["verified_opportunity"]),
            "scenario_sides_with_a_verified_opportunity": sorted({f"{s['scenario']} {s['colour']}" for s in sides
                                                                  if s["verified_opportunity"]})}
