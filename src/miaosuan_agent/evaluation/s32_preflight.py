"""Sprint 32 historical feasibility preflight of ``t7-b1-stop-engage-1`` (``docs/SPRINT32_T7_B1_PREFLIGHT.md``,
sections 4 and 5).

Offline, before any engine session. The candidate's rule (``experiments/t7_b1_stop_engage.py``, frozen with this
module) is applied to recorded seat observations and ``baseline-v2``'s decision on each of them, in four populations
of different evidence strength that are never pooled into one figure:

* **HH**: the ``baseline-v2`` seat of the four Sprint 12 head-to-head games in 2130511121 (opponent: the T9-v3
  candidate). Genuine ``baseline-v2`` trajectories.
* **HX**: the ``baseline-v2`` seat of the two later full-step head-to-head games in 2130511121: Sprint 27's session
  2797 (red; opponent the T6-S candidate) and Sprint 31's session 2800 (blue; opponent the K2 candidate). Genuine.
* **HI**: the three Sprint 10 games of ``baseline-v2`` against the inert control (2120531121 C3, 1930331196 C3,
  1930331196 C2). Genuine.
* **H0**: the eight replay-corpus games, both seats; ``baseline-v0``'s recorded actions with ``baseline-v2``
  reconstructed (off-policy).

Fixed before the preflight runs:

* **Rule replay.** At every decision the candidate's :func:`~..experiments.t7_b1_stop_engage.decide` runs twice on
  the seat observation and ``baseline-v2``'s actions: with the candidate's own memory chained through the side (its
  stops: one per unit and game), and with an empty memory (its **eligible** units, every level but
  ``H_not_stopped_before``).
* **Opportunity episode.** A maximal run of consecutive play decisions of one side at which one unit is eligible.
  Repeated observations of one unit inside a run are one opportunity; a unit's stop is the first decision of its first
  episode.
* **First divergence.** A side's first stop. A valid first-divergence fact in HH, HX and HI (genuine trajectories) and
  in H0 only when the recorded actions equal ``baseline-v2``'s at every earlier decision of that seat. Every later stop
  and episode lies on recorded states that an engine game with the candidate would not reach (off-policy) and is a
  descriptive diagnostic only.
* **Independent check** (:func:`independent_triggers`): at every decision a restatement of the trigger written apart
  from the candidate's code must give exactly the candidate's stops and eligible units. Any finding invalidates.
* **Recorded-trajectory descriptions** of each stop (off-policy, descriptive): the window is the expected completion
  ``hex_steps + 75`` plus the margin; whether the target stayed in the seat's view within range of the stop hex
  throughout the window (Sprint 5's B1 witness), whether the unit was lost or damaged, whether its path led to an
  objective its side did not hold and whether the side first owned that objective inside the window (an objective
  conflict), and whether the unit was ever listed a shot inside the window on the record.
* **Configurations** (:func:`configuration_status`): a configuration of the proposed mechanism check is
  ``VERIFIED`` when a genuine full-step ``baseline-v2`` record of it has a valid first divergence and no
  independent-check finding, ``NO_OPPORTUNITY`` when such records exist without one, and ``NO_FULL_STEP_RECORD`` when
  none exists.
* **Disposition** (:func:`disposition`, first match): ``S32_PREFLIGHT_INVALID`` (an anchor, an integrity check or the
  independent check fails); ``S32_PREFLIGHT_PASS`` (both proposed configurations ``VERIFIED``);
  ``S32_PREFLIGHT_PROPOSED_UNVERIFIED`` (a proposed configuration is not verified, but verified inert configurations
  exist for a ``baseline-v2`` red seat and a blue seat: an alternative pair is named and the owner chooses);
  ``S32_PREFLIGHT_INADEQUATE`` (otherwise: no live test is proposed).
"""

from __future__ import annotations

import collections
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..experiments import t7_b1_stop_engage as cand
from . import t7_candidates as t7c
from . import t7_visibility as t7v
from .s12_timeline import labels

STUDY_ID = "s32-t7-b1"
SCHEMA = "miaosuan-s32-preflight/1"
POPULATIONS = ("HH", "HX", "HI", "H0")
GENUINE = ("HH", "HX", "HI")
#: The owner's tentative configurations of the mechanism check: (scenario, condition, baseline-v2 seat colour).
PROPOSED = (("2130511121", "C2", "red"), ("2130511121", "C3", "blue"))
DISPOSITIONS = ("S32_PREFLIGHT_INVALID", "S32_PREFLIGHT_PASS", "S32_PREFLIGHT_PROPOSED_UNVERIFIED",
                "S32_PREFLIGHT_INADEQUATE")
INVALID, PASS, UNVERIFIED, INADEQUATE = DISPOSITIONS
CONFIG_STATUS = ("VERIFIED", "NO_OPPORTUNITY", "NO_FULL_STEP_RECORD")
ANCHORS = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123,
           "HH decisions": 11524, "HI decisions": 8643, "HX decisions": 5762}
SIDE_GAMES = {"HH": 4, "HX": 2, "HI": 3, "H0": 16}
PLAY = 2
SHOOT = 2
WEAPON_NAMES = {54: "small direct-fire gun", 4: "rapid-fire gun (ground)", 56: "rapid-fire gun", 29: "infantry light "
                "weapons", 43: "vehicle light weapons", 83: "medium missile", 74: "portable medium missile",
                75: "small missile", 76: "loitering munition", 35: "rocket launcher", 71: "portable missile",
                69: "vehicle-mounted missile", 84: "gun-launched missile", 73: "heavy missile",
                36: "large direct-fire gun", 37: "medium direct-fire gun"}
TARGET_NAMES = {1: "infantry", 2: "vehicle"}


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def unit_class(u: Mapping[str, Any]) -> str:
    if u.get("type") == 1:
        return "infantry"
    if u.get("type") == 2:
        return "artillery" if u.get("sub_type") == 3 else f"vehicle_st{u.get('sub_type')}"
    return "other"


def reaching_weapon(weapons: Sequence[int], target_type: int) -> str:
    """The name of the weapon giving the longest published range against the target class (lowest id on ties)."""
    column = 0 if target_type == 1 else 1
    best = None
    for w in sorted(weapons):
        r = t7c.WEAPON_RANGES.get(w, (None, None))[column]
        if r is not None and (best is None or r > best[0]):
            best = (r, w)
    return "none" if best is None else WEAPON_NAMES.get(best[1], f"weapon_{best[1]}")


# ------------------------------------------------------------------------------------------------
# independent restatement of the trigger


def independent_triggers(raw: Mapping[str, Any], seat: int, faction: int, base: Sequence[Mapping[str, Any]],
                         stopped: Set[int]) -> Set[int]:
    """The units the registered trigger selects, restated apart from the candidate's code (the T7 study's range table
    and distance, its own field reading); ``stopped`` holds the units the candidate already stopped."""
    t = raw.get("time") or {}
    if t.get("stage") != PLAY:
        return set()
    step, end = t.get("cur_step"), t.get("max_step")
    info = raw.get("role_and_grouping_info") or {}
    mine = info.get(seat) if seat in info else info.get(str(seat))
    controlled = set((mine or {}).get("operators") or ())
    listing = raw.get("valid_actions") or {}
    ops = [u for u in raw.get("operators") or () if isinstance(u, Mapping)]
    acted = {a.get("obj_id") for a in base}
    planned: List[Tuple[Any, Sequence[Any]]] = [(a.get("obj_id"), a.get("move_path") or ()) for a in base
                                                if a.get("type") == 1]
    out = set()
    for u in ops:
        uid = u.get("obj_id")
        if u.get("color") != faction or u.get("type") not in (1, 2) or uid not in controlled:
            continue
        guns = u.get("carry_weapon_ids")
        if type(u.get("A1")) is not int or u["A1"] != 0 or not isinstance(guns, list) \
                or not all(type(w) is int for w in guns) or 36 in guns or 37 in guns:
            continue
        route = u.get("move_path")
        if not isinstance(route, list) or len(route) < 2 or not all(type(h) is int for h in route) \
                or type(u.get("cur_hex")) is not int:
            continue
        speed, pos = u.get("speed"), u.get("cur_pos")
        if not (is_num(speed) and speed > 0 and is_num(pos) and 0 <= pos < 1):
            continue
        per = listing.get(uid) if uid in listing else listing.get(str(uid))
        if not isinstance(per, Mapping):
            continue
        stop_keys = [k for k in per if str(k) == "10"]
        if len(stop_keys) != 1 or per[stop_keys[0]] is not None:
            continue
        zero = ("stop", "move_to_stop_remain_time", "flag_force_stop", "change_state_remain_time",
                "get_on_remain_time", "get_off_remain_time", "weapon_unfold_time", "keep", "move_state", "on_board")
        if any(not is_num(u.get(f)) or u.get(f) != 0 for f in zero) or u.get("weapon_unfold_state") != 1 \
                or not is_num(u.get("weapon_unfold_state")):
            continue
        if uid in acted or uid in stopped:
            continue
        here = route[0]
        seen = u.get("see_enemy_bop_ids")
        if not isinstance(seen, (list, tuple)):
            continue
        hit = False
        for e in ops:
            if e.get("color") == faction or e.get("type") not in (1, 2) or e.get("obj_id") not in seen \
                    or type(e.get("cur_hex")) is not int:
                continue
            column = 0 if e["type"] == 1 else 1
            ranges = [t7c.WEAPON_RANGES[w][column] for w in guns if w in t7c.WEAPON_RANGES
                      and t7c.WEAPON_RANGES[w][column] is not None]
            if ranges and t7v.hex_distance(here, e["cur_hex"]) <= max(ranges):
                hit = True
                break
        if not hit:
            continue
        crowd = {o.get("obj_id") for o in ops if o.get("color") == faction and o.get("type") in (1, 2)
                 and o.get("obj_id") != uid and (o.get("cur_hex") == here or here in (o.get("move_path") or ()))}
        crowd |= {unit for unit, path in planned if unit != uid and here in path}
        if len(crowd) > 2:
            continue
        need = (1.0 - pos) / speed
        whole = int(round(need, 6))
        steps = whole if abs(need - whole) < 1e-6 else int(need) + 1
        if step + steps + 75 + 3 > end:
            continue
        out.add(uid)
    return out


# ------------------------------------------------------------------------------------------------
# one side


def light(raw: Mapping[str, Any], faction: int) -> Dict[str, Any]:
    """What the recorded-trajectory descriptions keep of one decision."""
    own, enemy = {}, {}
    listing = raw.get("valid_actions") or {}
    for u in raw.get("operators") or ():
        if not isinstance(u, Mapping):
            continue
        if u.get("color") == faction and u.get("type") in (1, 2):
            per = listing.get(u.get("obj_id")) or listing.get(str(u.get("obj_id"))) or {}
            own[u["obj_id"]] = (u.get("cur_hex"), u.get("blood"), any(str(k) == str(SHOOT) for k in per))
        elif u.get("color") != faction and u.get("type") in (1, 2):
            enemy[u["obj_id"]] = u.get("cur_hex")
    t = raw.get("time") or {}
    return {"step": t.get("cur_step"), "stage": t.get("stage"), "own": own, "enemy": enemy,
            "flags": {c.get("coord"): c.get("flag") for c in raw.get("cities") or () if isinstance(c, Mapping)}}


def describe(stop: Dict[str, Any], frames: Sequence[Mapping[str, Any]], faction: int,
             names: Mapping[Any, str]) -> Dict[str, Any]:
    """Recorded-trajectory description of one stop (off-policy for every stop but a valid first divergence)."""
    k0, unit, target, nxt, reach = stop["k"], stop["unit"], stop["target"], stop["next_hex"], stop["range"]
    end_step = stop["step"] + stop["hex_steps"] + cand.TRANSITION + cand.END_MARGIN
    window = [f for f in frames[k0:] if is_int(f["step"]) and f["step"] <= end_step]
    witness = all(target in f["enemy"] and is_int(f["enemy"][target])
                  and t7v.hex_distance(nxt, f["enemy"][target]) <= reach for f in window)
    present = [f for f in window if unit in f["own"]]
    lost = len(present) < len(window)
    bloods = [f["own"][unit][1] for f in present if is_num(f["own"][unit][1])]
    damaged = bool(bloods) and min(bloods) < bloods[0]
    shot_listed = any(f["own"][unit][2] for f in present[1:])
    dest = stop["destination"]
    objective_bound = dest in names and frames[k0]["flags"].get(dest) != faction
    capture = objective_bound and any(f["flags"].get(dest) == faction for f in window[1:])
    return {"witness_target_in_view_and_range_through_window": witness, "unit_lost_in_window": lost,
            "unit_damaged_in_window": damaged, "shoot_listed_in_window_on_record": shot_listed,
            "path_ends_at_unheld_objective": objective_bound, "side_first_owned_it_in_window": capture,
            "window_steps": end_step - stop["step"]}


def analyse_side(meta: Mapping[str, Any], stream: Iterable[Tuple[Mapping[str, Any], Sequence[Mapping[str, Any]],
                                                                Sequence[Mapping[str, Any]]]]
                 ) -> Tuple[Dict[str, Any], set]:
    """One side: ``stream`` yields (raw seat observation, recorded actions, ``baseline-v2``'s actions) per decision."""
    faction, seat, population = meta["faction"], meta["seat"], meta["population"]
    private: set = set()
    decisions = play = differs = 0
    first_difference = None
    levels: collections.Counter = collections.Counter()
    waiting_with_path = 0
    problems: List[Tuple[int, str]] = []
    memory: Tuple[Tuple[int, int], ...] = ()
    stops: List[Dict[str, Any]] = []
    eligible_by_k: List[Set[int]] = []
    frames: List[Dict[str, Any]] = []
    values: Dict[Any, Any] = {}
    unreadable: collections.Counter = collections.Counter()
    for k, (raw, recorded, base) in enumerate(stream):
        decisions += 1
        base = [dict(a) for a in base]
        if [dict(a) for a in recorded] != base:
            differs += 1
            first_difference = k if first_difference is None else first_difference
        frames.append(light(raw, faction))
        for c in raw.get("cities") or ():
            if isinstance(c, Mapping):
                values.setdefault(c.get("coord"), c.get("value"))
                private.add(c.get("coord"))
        for u in raw.get("operators") or ():
            if isinstance(u, Mapping):
                private.update(x for x in (u.get("obj_id"), u.get("cur_hex")) if x is not None)
                private.update(u.get("move_path") or ())
        if (raw.get("time") or {}).get("stage") != PLAY:
            eligible_by_k.append(set())
            continue
        play += 1
        live = cand.decide(raw, seat, faction, base, memory)
        free = cand.decide(raw, seat, faction, base, ())
        eligible = {c.unit for c in free.checks if c.level == cand.TRIGGER}
        eligible_by_k.append(eligible)
        stopped = {u for u, _ in memory}
        if independent_triggers(raw, seat, faction, base, stopped) != set(live.stops):
            problems.append((k, "the restated trigger disagrees with the candidate's stops"))
        if independent_triggers(raw, seat, faction, base, set()) != eligible:
            problems.append((k, "the restated trigger disagrees with the candidate's eligible units"))
        if list(live.actions[:len(base)]) != base or any(a["type"] != cand.STOP for a in live.actions[len(base):]):
            problems.append((k, "the candidate's list is not baseline-v2's followed by stops"))
        ops = {u.get("obj_id"): u for u in raw.get("operators") or () if isinstance(u, Mapping)}
        for c in free.checks:
            levels[c.level] += 1
            if c.level == cand.LEVELS[2] and c.detail.startswith("unreadable"):
                unreadable[c.detail] += 1
            if c.level == cand.LEVELS[2] and c.detail == "waiting":
                waiting_with_path += 1
            if c.level == cand.LEVELS[3] and c.detail == "ambiguous listing":
                unreadable["ambiguous stop listing"] += 1
        for c in live.checks:
            if c.level != cand.TRIGGER:
                continue
            u = ops[c.unit]
            target = ops[c.target]
            stops.append({"k": k, "step": (raw.get("time") or {}).get("cur_step"), "unit": c.unit,
                          "class": unit_class(u), "target": c.target,
                          "target_class": TARGET_NAMES.get(target.get("type"), "other"),
                          "weapon": reaching_weapon(u.get("carry_weapon_ids") or (), target.get("type")),
                          "distance": c.distance, "range": c.reach, "next_hex": c.next_hex, "others": c.others,
                          "hex_steps": c.steps, "path_hexes": len(u.get("move_path") or ()),
                          "destination": (u.get("move_path") or [None])[-1],
                          "steps_left": (raw.get("time") or {}).get("max_step") - (raw.get("time") or {}).get("cur_step")})
        memory = live.memory
    names = labels({c: v for c, v in values.items() if is_int(c)})
    for s in stops:
        s.update(describe(s, frames, faction, names))
    episodes: List[Dict[str, Any]] = []
    open_runs: Dict[int, Dict[str, Any]] = {}
    for k, eligible in enumerate(eligible_by_k):
        for unit in list(open_runs):
            if unit not in eligible:
                episodes.append(open_runs.pop(unit))
        for unit in eligible:
            if unit in open_runs:
                open_runs[unit]["length"] += 1
            else:
                open_runs[unit] = {"unit": unit, "k": k, "step": frames[k]["step"], "length": 1}
    episodes.extend(open_runs.values())
    episodes.sort(key=lambda e: (e["k"], e["unit"]))
    first = stops[0] if stops else None
    valid = first is not None and (population in GENUINE or first_difference is None or first_difference >= first["k"])
    summary = {"population": population, "label": meta["label"], "scenario": meta["scenario"],
               "condition": meta["condition"], "colour": "red" if faction == 0 else "blue",
               "decisions": decisions, "play_decisions": play, "baseline_v2_differs_from_recorded": differs,
               "independent_check_findings": len(problems),
               "unit_decision_levels": dict(sorted(levels.items())),
               "waiting_with_path_unit_decisions": waiting_with_path,
               "unreadable_or_ambiguous": dict(sorted(unreadable.items())),
               "eligible_unit_decisions": sum(len(e) for e in eligible_by_k),
               "opportunity_episodes": len(episodes),
               "distinct_units": len({e["unit"] for e in episodes}),
               "stops": len(stops),
               "first_divergence": None if first is None else {
                   "decision": first["k"], "step": first["step"], "valid": valid,
                   **{key: first[key] for key in ("class", "target_class", "weapon", "distance", "range", "others",
                                                  "hex_steps", "path_hexes", "steps_left",
                                                  "witness_target_in_view_and_range_through_window",
                                                  "unit_lost_in_window", "unit_damaged_in_window",
                                                  "shoot_listed_in_window_on_record",
                                                  "path_ends_at_unheld_objective", "side_first_owned_it_in_window",
                                                  "window_steps")},
                   "objective": names.get(first["destination"], "not an objective")},
               "verified_opportunity": bool(valid and not problems),
               "private": {"problems": problems[:50], "stops": stops, "episodes": episodes,
                           "first_difference": first_difference}}
    return summary, private


# ------------------------------------------------------------------------------------------------
# aggregation and the study's decision


def spread(values: Sequence[Any]) -> Optional[Dict[str, Any]]:
    values = sorted(v for v in values if is_num(v))
    if not values:
        return None
    return {"min": values[0], "median": statistics.median(values), "max": values[-1]}


def stop_profile(stops: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    flags = ("witness_target_in_view_and_range_through_window", "unit_lost_in_window", "unit_damaged_in_window",
             "shoot_listed_in_window_on_record", "path_ends_at_unheld_objective", "side_first_owned_it_in_window")
    return {"stops": len(stops),
            "unit_classes": dict(sorted(collections.Counter(s["class"] for s in stops).items())),
            "target_classes": dict(sorted(collections.Counter(s["target_class"] for s in stops).items())),
            "weapons": dict(sorted(collections.Counter(s["weapon"] for s in stops).items())),
            "hex_steps": spread([s["hex_steps"] for s in stops]),
            "distance_from_stop_hex": spread([s["distance"] for s in stops]),
            "path_hexes": spread([s["path_hexes"] for s in stops]),
            "steps_left_before_end": spread([s["steps_left"] for s in stops]),
            "others_on_or_routed_through_stop_hex": dict(sorted(collections.Counter(
                f"others_{s['others']}" for s in stops).items())),
            **{flag: sum(1 for s in stops if s[flag]) for flag in flags}}


def public_side(s: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in s.items() if k != "private"}
    stops = s["private"]["stops"]
    out["first_divergence_stop_and_later_stops"] = {
        "first": stop_profile(stops[:1]), "later_off_policy": stop_profile(stops[1:])}
    out["episode_lengths"] = spread([e["length"] for e in s["private"]["episodes"]])
    return out


def pooled(sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    levels: collections.Counter = collections.Counter()
    for s in sides:
        levels.update(s["unit_decision_levels"])
    stops = [x for s in sides for x in s["private"]["stops"]]
    return {"side_games": len(sides), "unit_decision_levels": dict(sorted(levels.items())),
            "waiting_with_path_unit_decisions": sum(s["waiting_with_path_unit_decisions"] for s in sides),
            "eligible_unit_decisions": sum(s["eligible_unit_decisions"] for s in sides),
            "opportunity_episodes": sum(s["opportunity_episodes"] for s in sides),
            "distinct_units": sum(s["distinct_units"] for s in sides),
            "side_games_with_a_stop": sum(1 for s in sides if s["stops"]),
            "valid_first_divergences": sum(1 for s in sides if s["first_divergence"] and s["first_divergence"]["valid"]),
            "verified_opportunities": sum(1 for s in sides if s["verified_opportunity"]),
            "scenario_sides_with_a_verified_opportunity": sorted({f"{s['scenario']} {s['colour']}" for s in sides
                                                                  if s["verified_opportunity"]}),
            "stops": stop_profile(stops)}


def configuration_status(sides: Sequence[Mapping[str, Any]], scenario: str, condition: str, colour: str) -> str:
    """``VERIFIED``, ``NO_OPPORTUNITY`` or ``NO_FULL_STEP_RECORD`` for one inert configuration (genuine HI sides)."""
    group = [s for s in sides if s["population"] == "HI" and s["scenario"] == scenario
             and s["condition"] == condition and s["colour"] == colour]
    if not group:
        return CONFIG_STATUS[2]
    return CONFIG_STATUS[0] if any(s["verified_opportunity"] for s in group) else CONFIG_STATUS[1]


def disposition(anchors_ok: bool, sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    reasons = []
    if not anchors_ok:
        reasons.append("a fidelity anchor is not reproduced")
    if any(s["independent_check_findings"] for s in sides):
        reasons.append("the independent check found a disagreement")
    proposed = {f"{sid} {cond} baseline-v2 {colour}": configuration_status(sides, sid, cond, colour)
                for sid, cond, colour in PROPOSED}
    verified = sorted({(s["scenario"], s["condition"], s["colour"]) for s in sides
                       if s["population"] == "HI" and s["verified_opportunity"]})
    alternatives = {colour: [f"{sid} {cond}" for sid, cond, c in verified if c == colour] for colour in ("red", "blue")}
    out = {"proposed_configurations": proposed, "verified_inert_configurations": alternatives}
    if reasons:
        return {"disposition": INVALID, "reasons": reasons, **out}
    if all(v == CONFIG_STATUS[0] for v in proposed.values()):
        return {"disposition": PASS, "reasons": [], **out}
    if alternatives["red"] and alternatives["blue"]:
        return {"disposition": UNVERIFIED,
                "reasons": [f"{k}: {v}" for k, v in proposed.items() if v != CONFIG_STATUS[0]], **out}
    return {"disposition": INADEQUATE,
            "reasons": [f"{k}: {v}" for k, v in proposed.items() if v != CONFIG_STATUS[0]]
            + ["no verified inert configuration for a baseline-v2 " + c for c in ("red", "blue") if not alternatives[c]],
            **out}
