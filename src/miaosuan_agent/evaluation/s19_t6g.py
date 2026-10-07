"""Sprint 19 T6-G offline shadow study (``docs/SPRINT19_T6G_SHADOW.md``): analysis over Sprint 18 census frames.

The frozen gate (``experiments/t6_threat_entry_gate.py``) is applied, decision by decision, to the ``baseline-v2``
action lists of one side of one historical game (H0: reconstructed on ``baseline-v0`` trajectories; HH: the genuine
``baseline-v2`` seat). Nothing here reaches a policy or an engine.

Evidence boundary (registration, section 6). The recorded states were produced by historical policies, not by T6-G.
Before a side-game's first gate the candidate's action lists equal ``baseline-v2``'s; the first gate itself is a valid
action-level fact; every later state is off-policy for T6-G, so later gates, holds and releases are opportunity
diagnostics on recorded states, never states T6-G would reach. On HH the historical unit moved where T6-G would have
held it, so the shadow's hold usually ends at the next decision with reason ``no_baseline_move``: a synthetic hold
length describes the replay, not a hold the candidate would make.

Private rows (unit ids, hexes, routes) stay in the returned objects and the private output; :func:`public_side` and
the other ``public_*`` functions emit aggregates only.
"""

from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..experiments import t6_threat_entry_gate as tg
from . import s18_census as sc

WINDOWS = (75, 150, 300)
#: Episode-level historical reference for the future probe: damage from hold start through this many steps after release.
AFTER_RELEASE = 300
#: Opportunity adequacy: first gates of an episode per registered HH side-game (section 10).
OPPORTUNITY_MIN = 10
HH_SIDE_GAMES = 4
DISPOSITIONS = ("REPLAY_INVALID", "T6_G_OFFLINE_INADEQUATE_OPPORTUNITY", "T6_G_OFFLINE_CAPTURE_RISK",
                "T6_G_OFFLINE_PASS")
OPEN_AT_END = "open_at_end"


# ------------------------------------------------------------------------------------------------
# the shadow on one side

@dataclass
class Episode:
    obj: Any
    start_k: int
    start_step: int
    index: int
    check: tg.EntryCheck
    mover: Mapping[str, Any]
    route: Tuple[Any, ...]
    baseline_types: Tuple[Any, ...]
    gate_types: Tuple[Any, ...]
    repeats: int = 0
    release_k: Optional[int] = None
    release_step: Optional[int] = None
    reason: Optional[str] = None
    release_check_reason: Optional[str] = None


@dataclass
class SideShadow:
    decisions: int = 0
    move_orders: int = 0
    gated_decisions: int = 0
    opportunities: List[Tuple[int, int, Any]] = field(default_factory=list)
    episodes: List[Episode] = field(default_factory=list)
    cooldown_suppressed: List[Tuple[int, int, Any]] = field(default_factory=list)
    dropped: Dict[int, Tuple[int, ...]] = field(default_factory=dict)
    check_reasons: collections.Counter = field(default_factory=collections.Counter)
    route_starts_at_current_hex: int = 0
    integrity: Dict[str, bool] = field(default_factory=dict)


def shadow_side(frames: Sequence[sc.Frame], rules: tg.GateRules = tg.FROZEN) -> SideShadow:
    """Applies the gate to every decision of one side, from an empty memory, and collects episodes and counts."""
    out = SideShadow()
    memory = tg.GateMemory()
    open_eps: Dict[Any, Episode] = {}
    order_ok = only_moves_dropped = True
    for f in frames:
        out.decisions += 1
        result = tg.apply_gate(f.cur_step, f.own, f.enemies.values(), f.actions, memory, rules)
        memory = result.memory
        expected = [dict(a) for i, a in enumerate(f.actions) if i not in set(result.dropped)]
        order_ok &= list(result.actions) == expected and len(result.actions) + len(result.dropped) == len(f.actions)
        only_moves_dropped &= all(f.actions[i].get("type") == tg.MOVE for i in result.dropped)
        if result.dropped:
            out.dropped[f.k] = result.dropped
            out.gated_decisions += len(result.dropped)
        for i, obj, check in result.checks:
            out.move_orders += 1
            out.check_reasons[check.reason] += 1
            unit = f.own.get(obj)
            route = tuple(f.actions[i].get("move_path") or ())
            if unit is not None and route and route[0] == unit.get("cur_hex"):
                out.route_starts_at_current_hex += 1
            if check.eligible:
                out.opportunities.append((f.k, f.cur_step, obj))
        for e in result.events:
            if e.kind == "gate_start":
                action = f.actions[e.index]
                ep = Episode(e.obj_id, f.k, f.cur_step, e.index, e.check, dict(f.own[e.obj_id]),
                             tuple(action.get("move_path") or ()), tuple(a.get("type") for a in f.actions),
                             tuple(a.get("type") for a in result.actions))
                open_eps[e.obj_id] = ep
                out.episodes.append(ep)
            elif e.kind == "gate_repeat":
                open_eps[e.obj_id].repeats += 1
            elif e.kind == "release":
                ep = open_eps.pop(e.obj_id)
                ep.release_k, ep.release_step, ep.reason = f.k, f.cur_step, e.reason
                ep.release_check_reason = e.check.reason if e.check is not None else None
            elif e.kind == "cooldown_suppressed":
                out.cooldown_suppressed.append((f.k, f.cur_step, e.obj_id))
    if frames:
        last = frames[-1]
        for ep in open_eps.values():
            ep.release_k, ep.release_step, ep.reason = last.k, last.cur_step, OPEN_AT_END
    out.integrity = {"action order preserved and only dropped moves removed": bool(order_ok and only_moves_dropped),
                     "every episode starts with a dropped move": all(ep.index in out.dropped.get(ep.start_k, ())
                                                                     for ep in out.episodes),
                     "gated decisions = episodes + repeats": out.gated_decisions == len(out.episodes)
                     + sum(ep.repeats for ep in out.episodes)}
    return out


# ------------------------------------------------------------------------------------------------
# historical facts the analysis joins to the shadow

def first_ownerships(frames: Sequence[sc.Frame], faction: int) -> List[Dict[str, Any]]:
    """Each objective's first decision whose flag reads ``faction``, with the side's own ground units standing on it
    at that decision (the historical first-ownership participants). ``initial`` marks an objective already owned at the
    side's first decision (no transition, no participants counted)."""
    out: List[Dict[str, Any]] = []
    seen: Set[Any] = set()
    for idx, f in enumerate(frames):
        for coord, flag in f.flags.items():
            if coord in seen or flag != faction:
                continue
            seen.add(coord)
            initial = idx == 0
            parts = frozenset() if initial else frozenset(
                obj for obj, u in f.own.items() if u.get("type") in tg.GROUND and u.get("cur_hex") == coord)
            out.append({"coord": coord, "k": f.k, "step": f.cur_step, "participants": parts, "initial": initial})
    return out


def damage_index(rows: Iterable[Mapping[str, Any]]) -> Dict[Any, List[Mapping[str, Any]]]:
    out: Dict[Any, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        out[r["victim"]].append(r)
    for v in out.values():
        v.sort(key=lambda r: (r["step"], r["k"]))
    return out


def damage_between(index: Mapping[Any, List[Mapping[str, Any]]], obj: Any, lo: int, hi: int) -> List[Mapping[str, Any]]:
    """Damage events on ``obj`` with ``lo <= step <= hi`` (Sprint 18's inclusive window)."""
    return [r for r in index.get(obj, ()) if lo <= r["step"] <= hi]


# ------------------------------------------------------------------------------------------------
# per-episode facts (private) and per-side analysis

def episode_facts(ep: Episode, frame: sc.Frame, damage: Mapping[Any, List[Mapping[str, Any]]],
                  participants: Mapping[Any, List[int]], values: Mapping[Any, Any]) -> Dict[str, Any]:
    """Everything the public tables need about one episode, private fields included."""
    check = ep.check
    cur = ep.mover.get("cur_hex")
    current = [sc_dist(cur, t.hex) for t in check.threats]
    margins = [sc_dist(cur, t.hex) - t.reach for t in check.threats]
    depth = max(t.reach - sc_dist(h, t.hex) for t in check.causing for h in check.inspected)
    enemy_hexes = {u.get("cur_hex") for u in frame.enemies.values()}
    end = ep.route[-1] if ep.route else None
    windows = {w: damage_between(damage, ep.obj, ep.start_step, ep.start_step + w) for w in WINDOWS}
    first = windows[300][0] if windows[300] else None
    causing_ids = {t.enemy for t in check.causing}
    reference_hi = (ep.release_step if ep.release_step is not None else ep.start_step) + AFTER_RELEASE
    own_steps = participants.get(ep.obj, [])
    return {
        "obj": ep.obj, "k": ep.start_k, "step": ep.start_step, "index": ep.index, "unit_class": sc.unit_class(ep.mover),
        "stacked": bool(ep.mover.get("stack")), "on_objective": cur in frame.flags,
        "close_combat_flag": bool(ep.mover.get("close_combat")),
        "route_length": len(ep.route), "inspected_length": len(check.inspected),
        "first_entry_index": check.first_entry_index,
        "visible_qualifying_threats": len(check.threats), "causing_threats": len(check.causing),
        "causing_ranges": sorted(t.reach for t in check.causing),
        "current_distance_to_causing": sorted(sc_dist(cur, t.hex) for t in check.causing),
        "current_distances": sorted(current), "current_margin": min(margins), "entry_depth": depth,
        "causing_classes": sorted(sc.unit_class(frame.enemies.get(t.enemy) or {}) for t in check.causing),
        "close_combat_entry": any(h in enemy_hexes for h in check.inspected),
        "objective_bound": end in frame.flags, "objective_label": values.get(end) if end in frame.flags else None,
        "baseline_types": list(ep.baseline_types), "gate_types": list(ep.gate_types),
        "repeats": ep.repeats, "release_step": ep.release_step, "reason": ep.reason,
        "release_check_reason": ep.release_check_reason,
        "hold_steps": (ep.release_step - ep.start_step) if ep.release_step is not None else None,
        "damaged_within": {str(w): bool(windows[w]) for w in WINDOWS},
        "first_damage": None if first is None else {
            "step": first["step"], "attacker": first["attacker"], "attacker_class": first["attacker_class"],
            "attacker_visible_at_gate": first["attacker"] in frame.enemies,
            "attacker_caused_gate": first["attacker"] in causing_ids, "victim_moving": bool(first["moving"])},
        "any_damage_by_causing_threat_300": any(r["attacker"] in causing_ids for r in windows[300]),
        "reference_damaged": bool(damage_between(damage, ep.obj, ep.start_step, reference_hi)),
        "participant_first_own_steps": sorted(own_steps),
        # private
        "cur_hex": cur, "route": list(ep.route), "inspected": list(check.inspected),
        "threats": [{"enemy": t.enemy, "hex": t.hex, "reach": t.reach,
                     "weapons": list((frame.enemies.get(t.enemy) or {}).get("carry_weapon_ids") or ())}
                    for t in check.threats],
        "causing": [t.enemy for t in check.causing],
    }


def sc_dist(a: Any, b: Any) -> int:
    from .t7_visibility import hex_distance
    return hex_distance(a, b)


@dataclass
class SideAnalysis:
    population: str
    label: str
    shadow: SideShadow
    episodes: List[Dict[str, Any]]
    exposed_not_gated: List[Dict[str, Any]]
    ownerships: List[Dict[str, Any]]
    gated: Set[Any]
    participants: Set[Any]
    integrity: Dict[str, bool]


def analyse_side(population: str, label: str, game: sc.Game, faction: int, values: Mapping[Any, Any],
                 rules: tg.GateRules = tg.FROZEN) -> SideAnalysis:
    frames = game.sides[faction]
    shadow = shadow_side(frames, rules)
    rows = sc.event_rows(game, faction)
    damage = damage_index(rows)
    owns = first_ownerships(frames, faction)
    participant_steps: Dict[Any, List[int]] = collections.defaultdict(list)
    for o in owns:
        for obj in o["participants"]:
            participant_steps[obj].append(o["step"])
    by_k = {f.k: f for f in frames}
    episodes = [episode_facts(ep, by_k[ep.start_k], damage, participant_steps, values) for ep in shadow.episodes]
    exposed_not_gated: List[Dict[str, Any]] = []
    gated_exposed = True
    for f in frames:
        dropped = set(shadow.dropped.get(f.k, ()))
        for i, a in enumerate(f.actions):
            if a.get("type") != tg.MOVE:
                continue
            verdict = sc.threat_exposed(f, a)
            if i in dropped:
                gated_exposed &= verdict is True
                continue
            if verdict:
                unit = f.own.get(a.get("obj_id")) or {}
                exposed_not_gated.append({
                    "k": f.k, "step": f.cur_step, "obj": a.get("obj_id"), "unit_class": sc.unit_class(unit),
                    "damaged_within": {str(w): bool(damage_between(damage, a.get("obj_id"), f.cur_step, f.cur_step + w))
                                       for w in WINDOWS}})
    census_steps = sc.first_ownership_steps(game, faction)
    integrity = dict(shadow.integrity)
    integrity["every dropped move is a Sprint 18 threat-exposed order"] = gated_exposed
    integrity["first ownerships equal the Sprint 18 census steps"] = sorted(o["step"] for o in owns) == census_steps
    integrity["every move route starts after the current hex"] = shadow.route_starts_at_current_hex == 0
    return SideAnalysis(population, label, shadow, episodes, exposed_not_gated, owns,
                        {ep.obj for ep in shadow.episodes},
                        {obj for o in owns for obj in o["participants"]}, integrity)


# ------------------------------------------------------------------------------------------------
# public aggregates

def dist(values: Sequence[float]) -> Dict[str, Any]:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def tally(values: Iterable[Any]) -> List[List[Any]]:
    """Value counts as ``[value, count]`` pairs (no numeric keys: numbers are never used as keys in public files)."""
    counts = collections.Counter(values)
    return [[v, counts[v]] for v in sorted(counts, key=lambda v: (str(type(v)), v))]


def damage_table(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"n": len(items)}
    for w in WINDOWS:
        out[f"damaged_within_{w}"] = sum(1 for i in items if i["damaged_within"][str(w)])
    return out


def by_class(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    groups: Dict[str, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for i in items:
        groups[i["unit_class"]].append(i)
    return {c: damage_table(v) for c, v in sorted(groups.items())}


def attacker_table(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    hit = [e["first_damage"] for e in episodes if e["first_damage"] is not None]
    return {"episodes_damaged_within_300": len(hit),
            "first_attacker_visible_at_gate": sum(h["attacker_visible_at_gate"] for h in hit),
            "first_attacker_caused_the_gate": sum(h["attacker_caused_gate"] for h in hit),
            "any_damage_by_a_causing_threat": sum(e["any_damage_by_causing_threat_300"] for e in episodes),
            "first_attacker_class": tally(h["attacker_class"] for h in hit),
            "victim_moving_at_first_damage": sum(h["victim_moving"] for h in hit),
            "steps_from_gate_to_first_damage": dist([h["step"] - e["step"] for e, h in
                                                     ((e, e["first_damage"]) for e in episodes) if h is not None])}


def diagnostics(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {"unit_class": tally(e["unit_class"] for e in episodes),
            "on_objective": sum(e["on_objective"] for e in episodes),
            "stacked": sum(e["stacked"] for e in episodes),
            "in_close_combat": sum(e["close_combat_flag"] for e in episodes),
            "close_combat_entry": sum(e["close_combat_entry"] for e in episodes),
            "objective_bound": sum(e["objective_bound"] for e in episodes),
            "route_length": dist([e["route_length"] for e in episodes]),
            "inspected_length": tally(e["inspected_length"] for e in episodes),
            "first_entry_index": tally(e["first_entry_index"] for e in episodes),
            "current_margin_outside_range": dist([e["current_margin"] for e in episodes]),
            "route_entry_depth_inside_range": dist([e["entry_depth"] for e in episodes]),
            "visible_qualifying_threats": dist([e["visible_qualifying_threats"] for e in episodes]),
            "causing_threats": dist([e["causing_threats"] for e in episodes]),
            "causing_ranges": tally(r for e in episodes for r in e["causing_ranges"]),
            "current_distance_to_causing": dist([d for e in episodes for d in e["current_distance_to_causing"]]),
            "causing_threat_class": tally(c for e in episodes for c in e["causing_classes"])}


def public_side(a: SideAnalysis) -> Dict[str, Any]:
    s = a.shadow
    eps = a.episodes
    first = eps[0] if eps else None
    out: Dict[str, Any] = {
        "side_game": a.label, "population": a.population,
        "decisions": s.decisions, "move_orders": s.move_orders,
        "threat_entry_opportunities": len(s.opportunities),
        "distinct_with_an_opportunity": len({o[2] for o in s.opportunities}),
        "gate_episodes": len(eps), "distinct_gated": len(a.gated),
        "gated_decisions": s.gated_decisions, "repeats_within_episodes": sum(e["repeats"] for e in eps),
        "cooldown_suppressions": len(s.cooldown_suppressed),
        "condition_reasons_over_all_moves": dict(sorted(s.check_reasons.items())),
        "release_reasons": dict(sorted(collections.Counter(e["reason"] for e in eps).items())),
        "condition_cleared_by": dict(sorted(collections.Counter(e["release_check_reason"] for e in eps
                                                                if e["reason"] == "condition_cleared").items())),
        "synthetic_hold_steps": dist([e["hold_steps"] for e in eps]),
        "first_gate": None if first is None else {
            "decision": first["k"], "step": first["step"], "decisions_before": first["k"],
            "unit_class": first["unit_class"]},
        "post_divergence_episodes": max(0, len(eps) - 1),
        "capturers": {"distinct_gated": len(a.gated), "first_ownership_participants": len(a.gated & a.participants)},
        "first_ownerships": len([o for o in a.ownerships if not o["initial"]]),
        "objectives_owned_at_first_decision": len([o for o in a.ownerships if o["initial"]]),
        "damage_after_gate": damage_table(eps),
        "damage_after_exposed_not_gated": damage_table(a.exposed_not_gated),
        "integrity": dict(sorted(a.integrity.items())),
    }
    return out


def pooled(sides: Sequence[SideAnalysis]) -> Dict[str, Any]:
    eps = [e for a in sides for e in a.episodes]
    first_gates = [a.episodes[0] for a in sides if a.episodes]
    later = [e for a in sides for e in a.episodes[1:]]
    exposed = [x for a in sides for x in a.exposed_not_gated]
    gated = sum(len(a.gated) for a in sides)
    capt = sum(len(a.gated & a.participants) for a in sides)
    distinct_damaged = 0
    for a in sides:
        for obj in a.gated:
            first_ep = next(e for e in a.episodes if e["obj"] == obj)
            distinct_damaged += first_ep["damaged_within"]["300"]
    return {
        "side_games": len(sides), "move_orders": sum(a.shadow.move_orders for a in sides),
        "threat_entry_opportunities": sum(len(a.shadow.opportunities) for a in sides),
        "gate_episodes": len(eps), "gated_decisions": sum(a.shadow.gated_decisions for a in sides),
        "cooldown_suppressions": sum(len(a.shadow.cooldown_suppressed) for a in sides),
        "capturers": capturer_fraction(sides),
        "gated_distinct_side_game_instances": gated, "of_which_first_ownership_participants": capt,
        "release_reasons": dict(sorted(collections.Counter(e["reason"] for e in eps).items())),
        "synthetic_hold_steps": dist([e["hold_steps"] for e in eps]),
        "damage_after_gate": damage_table(eps),
        "damage_after_gate_by_class": by_class(eps),
        "damage_after_first_gate_only": damage_table(first_gates),
        "damage_after_post_divergence_gates": damage_table(later),
        "damage_after_exposed_not_gated": damage_table(exposed),
        "damage_after_exposed_not_gated_by_class": by_class(exposed),
        "attackers_after_gate": attacker_table(eps),
        "distinct_gated_damaged_within_300_of_first_gate": distinct_damaged,
        "episode_reference": {"episodes": len(eps), "damaged_from_start_to_release_plus_300":
                              sum(e["reference_damaged"] for e in eps)},
        "diagnostics": diagnostics(eps),
    }


def capturer_fraction(sides: Sequence[SideAnalysis]) -> Dict[str, Any]:
    """Pooled over side-games, distinct units de-duplicated only within a side-game (section 11)."""
    num = sum(len(a.gated & a.participants) for a in sides)
    den = sum(len(a.gated) for a in sides)
    return {"participants": num, "gated": den, "fraction": round(num / den, 4) if den else None,
            "per_side_game": [[a.label, len(a.gated & a.participants), len(a.gated)] for a in sides]}


def objective_timing(sides: Sequence[SideAnalysis], values_by_side: Mapping[str, Mapping[Any, Any]]) -> List[Dict[str, Any]]:
    """Per historical first ownership (HH): whether gated units took part and how long before it they were gated."""
    from .s12_timeline import labels
    out = []
    for a in sides:
        names = labels(dict(values_by_side.get(a.label) or {}))
        starts: Dict[Any, List[int]] = collections.defaultdict(list)
        for e in a.episodes:
            starts[e["obj"]].append(e["step"])
        for o in a.ownerships:
            if o["initial"]:
                continue
            parts = o["participants"]
            gated_any = parts & a.gated
            before = {obj: min(s for s in starts[obj] if s < o["step"]) for obj in gated_any
                      if any(s < o["step"] for s in starts[obj])}
            out.append({"side_game": a.label, "objective": names.get(o["coord"], "unlabelled objective"),
                        "first_own_step": o["step"], "participants": len(parts),
                        "gated_participants": len(gated_any), "gated_before_first_ownership": len(before),
                        "steps_from_earliest_gate_to_first_ownership":
                            (o["step"] - min(before.values())) if before else None})
    return out


def certificate(a: SideAnalysis, values: Mapping[Any, Any]) -> Optional[Dict[str, Any]]:
    """The public, sanitised certificate of a side-game's first gate."""
    if not a.episodes:
        return None
    from .s12_timeline import labels
    e = a.episodes[0]
    names = labels(dict(values))
    end = e["route"][-1] if e["route"] else None
    return {"side_game": a.label, "decision": e["k"], "step": e["step"], "decisions_before_identical": e["k"],
            "unit_class": e["unit_class"], "stacked": e["stacked"], "on_objective": e["on_objective"],
            "route_length": e["route_length"], "inspected_length": e["inspected_length"],
            "first_entry_index": e["first_entry_index"],
            "visible_qualifying_threats": e["visible_qualifying_threats"], "causing_threats": e["causing_threats"],
            "causing_threat_classes": e["causing_classes"], "causing_ranges": e["causing_ranges"],
            "range_source": "evaluation/t7_candidates.weapon_range (published direct-fire ranges)",
            "current_distance_to_causing": e["current_distance_to_causing"],
            "current_margin_outside_range": e["current_margin"], "route_entry_depth_inside_range": e["entry_depth"],
            "baseline_action_types": e["baseline_types"], "gate_action_types": e["gate_types"],
            "dropped_position": e["index"],
            "objective_bound": e["objective_bound"],
            "route_end_objective": names.get(end) if e["objective_bound"] else None,
            "later_first_ownership_participant": bool(e["participant_first_own_steps"]),
            "first_ownership_after_gate": any(s >= e["step"] for s in e["participant_first_own_steps"]),
            "damaged_within": e["damaged_within"]}


# ------------------------------------------------------------------------------------------------
# disposition (section 13), first match

def gate_episode_counts(sides: Sequence[SideAnalysis]) -> List[int]:
    """Opportunity per side-game: gate episodes (first gates), not gated decisions (section 10)."""
    return [len(a.episodes) for a in sides]


def disposition(fidelity_ok: bool, hh_episodes: Sequence[int], capturer_participants: int,
                capturer_gated: int) -> Dict[str, Any]:
    """REPLAY_INVALID, then opportunity (every registered HH side-game at least ``OPPORTUNITY_MIN`` gate episodes),
    then capturer risk (pooled fraction strictly above one half fails; exactly one half passes), else PASS."""
    items = {"fidelity": bool(fidelity_ok),
             "opportunity": len(hh_episodes) == HH_SIDE_GAMES and all(n >= OPPORTUNITY_MIN for n in hh_episodes),
             "capturer_risk": capturer_gated > 0 and 2 * capturer_participants <= capturer_gated}
    if not items["fidelity"]:
        outcome = DISPOSITIONS[0]
    elif not items["opportunity"]:
        outcome = DISPOSITIONS[1]
    elif not items["capturer_risk"]:
        outcome = DISPOSITIONS[2]
    else:
        outcome = DISPOSITIONS[3]
    return {"disposition": outcome, "items_pass": items, "hh_gate_episodes": list(hh_episodes),
            "capturer": [capturer_participants, capturer_gated]}


# ------------------------------------------------------------------------------------------------
# sanitiser

def mask_numbers(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {k: mask_numbers(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [mask_numbers(v) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return None
    return node


def public_problems(data: Any, private_values: Iterable[Any]) -> List[str]:
    """Sprint 18's reading of the project sanitizer: forbidden keys anywhere; private hexes and unit ids as keys or as
    words of strings, with numeric leaves (aggregates by construction) masked."""
    from .s12_screen import privacy_problems
    return privacy_problems(data) + privacy_problems(mask_numbers(data), sorted({str(v) for v in private_values}))
