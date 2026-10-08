"""Sprint 25 T13-D1: held-objective loss anatomy and garrison shadow (``docs/SPRINT25_T13_D1.md``).

Pure functions over Sprint 18 census frames (``evaluation/s18_census.py``). Nothing here reaches a policy or an engine.

A side's frames are its decisions in order (``frame.k`` equals the position); ``recorded`` holds, per frame, the action
list the historical seat submitted (H0: ``baseline-v0``; HH: ``baseline-v2``), and ``frame.actions`` the ``baseline-v2``
list (H0: reconstructed on the recorded observation; HH: the recorded seat, equal to the reconstruction at every
decision by Sprint 18's check). Definitions are the registration's (sections 5 to 15); every docstring says which
section it implements.

Private rows (unit ids, hexes, routes) stay in the returned objects; :func:`public_loss` and the other ``public_*``
functions emit aggregates and labels only.
"""

from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..experiments import t13_garrison_shadow as tg
from . import s18_census as sc
from .t7_visibility import hex_distance

STUDY_ID = "s25-t13-d1"
V_ORDER, V_LOSS, V_OTHER = "V_ORDER", "V_LOSS", "V_OTHER"
V_CLASSES = (V_ORDER, V_LOSS, V_OTHER)
#: Fates of a last defender between the last occupied decision and the first empty one (section 6).
ALIVE_OUT, DESTROYED, MISSING, UNREADABLE = "left alive", "destroyed", "missing", "alive, hex unreadable"
#: Touched-loss categories (section 14).
TOUCHED, PREFIX_UNSUPPORTED, POST_DIVERGENCE, NON_ACTIONABLE, AMBIGUOUS = (
    "touched at a valid first divergence", "first divergence without prefix support (opportunity only)",
    "later historical-state opportunity only", "non-actionable", "classification ambiguity")
CATEGORIES = (TOUCHED, PREFIX_UNSUPPORTED, POST_DIVERGENCE, NON_ACTIONABLE, AMBIGUOUS)
#: Enemy information at the departure order (section 12), ground enemies only, first match.
ENEMY_INFO = ("visible, a qualifying threat", "visible, no qualifying threat", "seen within the previous 300 steps",
              "seen earlier only", "never seen")
LOOKBACK = 300
#: Stop thresholds and disposition precedence (section 16).
STOP_B_MIN_TOUCHED = 4
STOP_B_MIN_SCENARIO_SIDES = 2
DISPOSITIONS = ("T13_D1_INVALID", "T13_D1_NOT_READY", "T13_D1_READY_FOR_SMALL_EXPLORATORY_PROPOSAL")


# ------------------------------------------------------------------------------------------------
# side data

@dataclass
class Side:
    """One analysed side of one game: population, labels, frames, recorded and baseline-v2 action lists, events."""

    population: str
    label: str
    game: str
    scenario: str
    faction: int
    frames: List[sc.Frame]
    recorded: List[List[Mapping[str, Any]]]
    events: List[Tuple[int, Mapping[str, Any]]]
    values: Mapping[Any, Any] = field(default_factory=dict)

    @property
    def colour(self) -> str:
        return "red" if self.faction == 0 else "blue"

    @property
    def scenario_side(self) -> str:
        return f"{self.scenario} {self.colour}"


def objective_labels(values: Mapping[Any, Any]) -> Dict[Any, str]:
    from .s12_timeline import labels
    return labels(dict(values))


# ------------------------------------------------------------------------------------------------
# section 5: ownership-loss events and the denial zone

def loss_events(frames: Sequence[sc.Frame], faction: int) -> List[Dict[str, Any]]:
    """Sprint 18's N4 events (``s18_census.objective_defence``), restated with their positions: over the play-stage
    frames in order, an objective whose flag read the side's colour at the previous play decision and does not now."""
    play = [f for f in frames if f.stage == 2]
    out: List[Dict[str, Any]] = []
    held_prev: Dict[Any, bool] = {}
    for p, f in enumerate(play):
        for coord, flag in f.flags.items():
            held = flag == faction
            if held_prev.get(coord) and not held:
                out.append({"coord": coord, "k": f.k, "step": f.cur_step, "previous_k": play[p - 1].k})
            held_prev[coord] = held
    return out


def zone_occupants(frame: sc.Frame, coord: Any) -> Tuple[Any, ...]:
    """Own ground units (type 1 or 2, artillery included) with a readable hex within one hex of the objective."""
    return tg.zone_occupants(frame.own, coord)


def damage_decisions(events: Iterable[Tuple[int, Mapping[str, Any]]], faction: int) -> Dict[Any, Set[int]]:
    out: Dict[Any, Set[int]] = collections.defaultdict(set)
    for k, r in events:
        if r.get("target_color") == faction:
            out[r.get("target_obj_id")].add(k)
    return out


def last_order(recorded: Sequence[Sequence[Mapping[str, Any]]], unit: Any, upto: int) -> Optional[Tuple[int, Mapping[str, Any]]]:
    """The latest recorded MOVE (type 1) for ``unit`` at a decision ``<= upto``: (decision, action)."""
    for j in range(min(upto, len(recorded) - 1), -1, -1):
        for a in reversed(list(recorded[j])):
            if a.get("obj_id") == unit and a.get("type") == tg.MOVE:
                return j, a
    return None


# ------------------------------------------------------------------------------------------------
# section 6: last-defender reconstruction and the V classes

def anatomy(side: Side, loss: Mapping[str, Any]) -> Dict[str, Any]:
    """The last-defender reconstruction and V class of one loss (private row).

    The zone's occupancy is read at every decision from the first play decision to the loss decision. If the zone is
    occupied at the loss decision itself, the class is V_OTHER (``zone occupied at the loss decision``). Otherwise ``e``
    is the first decision of the empty run that ends at the loss; the last defenders are the occupants at ``e - 1``; if
    the zone was empty from the first play decision there is no last defender (V_OTHER). Each last defender's fate
    between ``e - 1`` and ``e``: left alive (in the own operators at ``e``, outside the zone), destroyed (absent from
    the own operators and passengers from ``e`` to the end of the game, with a positive damage record on it placed at
    ``e``), missing (absent otherwise) or alive with an unreadable hex. V_ORDER: every last defender left alive and the
    departure of each is attributable to a recorded MOVE (its latest recorded MOVE at or before ``e - 1`` lists its hex
    at ``e`` on the route); V_LOSS: every last defender was destroyed; anything else (mixed fates, a missing unit, an
    unattributable departure, an unreadable hex) is V_OTHER with its reason."""
    frames = side.frames
    by_k = {f.k: f for f in frames}
    first_play = next(f.k for f in frames if f.stage == 2)
    coord, k = loss["coord"], loss["k"]
    row: Dict[str, Any] = {"coord": coord, "loss_k": k, "loss_step": loss["step"], "previous_k": loss["previous_k"]}
    occupied = [(j, zone_occupants(by_k[j], coord)) for j in range(first_play, k + 1)]
    occ = dict(occupied)
    row["reentries"] = sum(1 for (j, a), (_, b) in zip(occupied, occupied[1:]) if not a and b)
    if occ[k]:
        row.update(v_class=V_OTHER, v_reason="zone occupied at the loss decision", defenders=list(occ[k]), fates={})
        return row
    e = k
    while e - 1 >= first_play and not occ[e - 1]:
        e -= 1
    row["empty_k"], row["empty_step"] = e, by_k[e].cur_step
    if e == first_play:
        row.update(v_class=V_OTHER, v_reason="no last defender observed", defenders=[], fates={})
        return row
    defenders = list(occ[e - 1])
    row["defenders"] = defenders
    row["last_occupied_k"] = e - 1
    lost = sc.lost_units(frames)
    damaged = damage_decisions(side.events, side.faction)
    fates: Dict[Any, str] = {}
    orders: Dict[Any, Dict[str, Any]] = {}
    for d in defenders:
        after = by_k[e].own.get(d)
        if after is not None:
            if tg.hex_int(after.get("cur_hex")) is None:
                fates[d] = UNREADABLE
                continue
            fates[d] = ALIVE_OUT
            found = last_order(side.recorded, d, e - 1)
            route = list(found[1].get("move_path") or ()) if found else []
            orders[d] = {"order_k": found[0] if found else None, "action": dict(found[1]) if found else None,
                         "attributable": bool(found) and after.get("cur_hex") in route}
        elif lost.get(d) == e and d not in by_k[e].aboard and e in damaged.get(d, ()):
            fates[d] = DESTROYED
        else:
            fates[d] = MISSING
    row["fates"] = fates
    row["orders"] = orders
    kinds = set(fates.values())
    if kinds == {ALIVE_OUT} and all(o["attributable"] for o in orders.values()):
        row.update(v_class=V_ORDER, v_reason="left alive under a recorded MOVE" if len(defenders) == 1
                   else "several last defenders, all left alive under recorded MOVEs")
    elif kinds == {DESTROYED}:
        row.update(v_class=V_LOSS, v_reason="destroyed in the zone" if len(defenders) == 1
                   else "several last defenders, all destroyed in the zone")
    elif kinds == {ALIVE_OUT}:
        row.update(v_class=V_OTHER, v_reason="left alive, departure not attributable to a recorded MOVE")
    elif MISSING in kinds:
        row.update(v_class=V_OTHER, v_reason="a last defender missing without a damage record at its disappearance")
    elif UNREADABLE in kinds:
        row.update(v_class=V_OTHER, v_reason="a last defender's hex unreadable")
    else:
        row.update(v_class=V_OTHER, v_reason="several last defenders with different fates in the same step")
    return row


# ------------------------------------------------------------------------------------------------
# section 12: enemy information and threat proximity at the departure order

def ground_seen_steps(frames: Sequence[sc.Frame], upto: int) -> List[int]:
    return [f.cur_step for f in frames[:upto] for u in f.enemies.values() if tg.is_ground(u)]


def enemy_information(frames: Sequence[sc.Frame], j: int, coord: Any, defender_type: Any) -> Dict[str, Any]:
    f = frames[j]
    visible = [u for u in f.enemies.values() if tg.is_ground(u)]
    threats = tg.qualifying_threats(visible, coord, defender_type)
    readable = [u for u in visible if tg.hex_int(u.get("cur_hex")) is not None]
    no_range = [u for u in readable if sc_range(u, defender_type) is None]
    seen = ground_seen_steps(frames, j)
    if threats:
        info = ENEMY_INFO[0]
    elif visible:
        info = ENEMY_INFO[1]
    elif any(f.cur_step - LOOKBACK <= s < f.cur_step for s in seen):
        info = ENEMY_INFO[2]
    elif seen:
        info = ENEMY_INFO[3]
    else:
        info = ENEMY_INFO[4]
    return {"enemy_info": info, "visible_ground_enemies": len(visible), "qualifying_threats": len(threats),
            "visible_without_published_range": len(no_range),
            "nearest_visible_distance": min((hex_distance(u["cur_hex"], coord) for u in readable), default=None),
            "threat_margin": (min(t.distance - (t.reach + tg.THREAT_MARGIN) for t in threats) if threats else None),
            "threat_reaches": sorted(t.reach for t in threats)}


def sc_range(enemy: Mapping[str, Any], defender_type: Any) -> Optional[int]:
    from .t7_candidates import weapon_range
    return weapon_range(enemy.get("carry_weapon_ids") or (), defender_type)


# ------------------------------------------------------------------------------------------------
# section 13: the shadow over a side, the first divergence and the independent check

@dataclass
class ShadowRun:
    candidate: List[Tuple[Mapping[str, Any], ...]]
    withheld: Dict[int, Tuple[int, ...]]
    events: List[Tuple[int, tg.GarrisonEvent]]
    checks: List[Tuple[int, int, Any, tg.TriggerCheck]]
    first_divergence: Optional[int]
    unexplained: List[Dict[str, Any]]


def run_shadow(side: Side) -> ShadowRun:
    """The frozen shadow on every decision of the side from an empty memory (the candidate's lists), the withheld
    indices, events and checks, the first divergence and the action-level comparison of section 13."""
    memory = tg.GarrisonMemory()
    candidate, withheld, events, checks, unexplained = [], {}, [], [], []
    for f in side.frames:
        result = tg.decide(side.faction, f.cur_step, f.stage, f.own, f.enemies.values(), f.flags, f.actions, memory)
        memory = result.memory
        candidate.append(result.actions)
        if result.withheld:
            withheld[f.k] = result.withheld
        events.extend((f.k, e) for e in result.events)
        checks.extend((f.k, i, u, c) for i, u, c in result.checks)
        unexplained.extend(compare(f, result.actions, side.faction))
    first = min(withheld) if withheld else None
    return ShadowRun(candidate, withheld, events, checks, first, unexplained)


def withheld_reasons(frame: sc.Frame, faction: int, action: Mapping[str, Any]) -> List[str]:
    """Independent restatement of what a withheld action must satisfy (section 13), from the frame's raw fields: a
    MOVE of an own non-artillery ground unit standing alone (among own ground units) in the zone of an objective the
    side holds, with a readable route that leaves that zone, and a visible enemy ground unit within its published
    range against the unit's class plus one hex of that objective. Returns the failed conditions (empty if none)."""
    failed = []
    if action.get("type") != 1:
        return ["not a MOVE"]
    unit = frame.own.get(action.get("obj_id"))
    if unit is None or unit.get("type") not in (1, 2) or (unit.get("type") == 2 and unit.get("sub_type") == 3):
        return ["not an own non-artillery ground unit"]
    here = unit.get("cur_hex")
    route = list(action.get("move_path") or ())
    ok_objectives = []
    for coord, flag in frame.flags.items():
        if flag != faction or not isinstance(coord, int) or not isinstance(here, int) or hex_distance(here, coord) > 1:
            continue
        others = [o for o, u in frame.own.items() if u.get("type") in (1, 2) and isinstance(u.get("cur_hex"), int)
                  and hex_distance(u["cur_hex"], coord) <= 1 and o != action.get("obj_id")]
        leaves = bool(route) and all(isinstance(h, int) for h in route) and any(hex_distance(h, coord) > 1 for h in route)
        near = any(e.get("type") in (1, 2) and isinstance(e.get("cur_hex"), int)
                   and sc_range(e, unit.get("type")) is not None
                   and hex_distance(e["cur_hex"], coord) <= sc_range(e, unit.get("type")) + 1
                   for e in frame.enemies.values())
        if not others and leaves and near:
            ok_objectives.append(coord)
    if not ok_objectives:
        failed.append("no held objective whose zone it alone occupies, that its route leaves and a threat is near")
    return failed


def compare(frame: sc.Frame, candidate: Sequence[Mapping[str, Any]], faction: int) -> List[Dict[str, Any]]:
    """Section 13: every action-level difference between the candidate and ``baseline-v2`` at one decision must be a
    registered MOVE withheld; returns the unexplained differences (private rows)."""
    base = [dict(a) for a in frame.actions]
    cand = [dict(a) for a in candidate]
    out = []
    i = 0
    removed = []
    for a in base:
        if i < len(cand) and cand[i] == a:
            i += 1
        else:
            removed.append(a)
    if i != len(cand):
        out.append({"k": frame.k, "problem": "the candidate adds or reorders actions"})
    for a in removed:
        problems = withheld_reasons(frame, faction, a)
        if problems:
            out.append({"k": frame.k, "problem": "; ".join(problems), "action": a})
    return out


def prefix_supported(side: Side, upto: int) -> bool:
    """H0: the recorded ``baseline-v0`` actions equal ``baseline-v2``'s at every decision before ``upto`` (Sprint 23's
    evidence boundary); HH: the recorded seat equals ``baseline-v2`` there."""
    return all([dict(a) for a in side.recorded[j]] == [dict(a) for a in side.frames[j].actions] for j in range(upto))


# ------------------------------------------------------------------------------------------------
# sections 14 and 15: touched losses and onward capture

def first_ownership(frames: Sequence[sc.Frame], faction: int, coord: Any) -> Optional[int]:
    """The decision of the side's first-ever play-stage ownership of ``coord`` (its flag reads the side's colour)."""
    for f in frames:
        if f.stage == 2 and f.flags.get(coord) == faction:
            return f.k
    return None


def onward(side: Side, row: Mapping[str, Any], unit: Any, j: int, action: Mapping[str, Any]) -> Dict[str, Any]:
    """Section 15 for one departure: the departure MOVE's destination, the next objective, first ownership and the
    registered first-owner risk flag (analysis only, from the historical trajectory)."""
    frames, faction, lost_coord = side.frames, side.faction, row["coord"]
    f = frames[j]
    route = list(action.get("move_path") or ())
    dest = route[-1] if route and tg.hex_int(route[-1]) is not None else None
    if dest is None:
        kind = "unreadable"
    elif dest == lost_coord:
        kind = "the lost objective"
    elif dest in f.flags:
        kind = "objective held" if f.flags[dest] == faction else "objective not held"
    else:
        kind = "not an objective"
    if kind in ("objective held", "objective not held"):
        nxt, how = dest, "the MOVE's destination"
    else:
        nxt, how = None, "no objective stood on after the order"
        for g in frames[j + 1:]:
            u = g.own.get(unit)
            if u is not None and u.get("cur_hex") in g.flags and u.get("cur_hex") != lost_coord:
                nxt, how = u["cur_hex"], "the first objective stood on after the order"
                break
    arrival = next((g.cur_step for g in frames[j + 1:] if (g.own.get(unit) or {}).get("cur_hex") == dest), None) \
        if dest is not None else None
    first_k = first_ownership(frames, faction, nxt) if nxt is not None else None
    first_step = frames[first_k].cur_step if first_k is not None else None
    after = first_k is not None and first_k > j
    participants = sorted((o for o, u in frames[first_k].own.items() if tg.is_ground(u) and u.get("cur_hex") == nxt),
                          key=str) if first_k is not None else []
    risk = after and unit in participants
    lost = sc.lost_units(frames)
    any_first = []
    for coord in {c for g in frames for c in g.flags}:
        fk = first_ownership(frames, faction, coord)
        if fk is not None and fk > j and coord != lost_coord and (frames[fk].own.get(unit) or {}).get("cur_hex") == coord:
            any_first.append(fk)
    recapture = None
    if nxt is not None:
        for g in frames[j + 1:]:
            if g.stage == 2 and g.flags.get(nxt) == faction and frames[g.k - 1].flags.get(nxt) != faction:
                recapture = (g.own.get(unit) or {}).get("cur_hex") == nxt
                break
    return {
        "destination_kind": kind, "next_objective": nxt, "next_objective_from": how,
        "travel_steps_to_destination": (arrival - f.cur_step) if arrival is not None else None,
        "next_first_owned_after_order": after,
        "steps_order_to_first_ownership": (first_step - f.cur_step) if after else None,
        "first_owner": risk,
        "first_owned_by_other_own_units_only": after and not risk and bool(participants),
        "next_objective_first_owned_before_order": first_k is not None and not after,
        "next_objective_never_owned": nxt is not None and first_k is None,
        "owner_at_next_ownership_transition": recapture,
        "first_owner_of_any_objective_after_order": bool(any_first),
        "unit_later_lost": unit in lost and lost[unit] > j,
        "steps_order_to_unit_loss": (frames[lost[unit]].cur_step - f.cur_step) if unit in lost and lost[unit] > j
        and lost[unit] < len(frames) else None,
    }


def classify_touch(side: Side, row: Dict[str, Any], shadow: ShadowRun) -> None:
    """Section 14 for one loss, in place: the category, its reason and the departure facts the tables need."""
    if row["v_class"] == V_LOSS:
        row.update(category=NON_ACTIONABLE, category_reason="destroyed in the zone")
        return
    if row["v_class"] == V_OTHER:
        row.update(category=AMBIGUOUS, category_reason=row["v_reason"])
        return
    if len(row["defenders"]) != 1:
        row.update(category=NON_ACTIONABLE, category_reason="several last defenders")
        return
    unit = row["defenders"][0]
    order = row["orders"][unit]
    j, action = order["order_k"], order["action"]
    f = side.frames[j]
    coord = row["coord"]
    me = f.own.get(unit) or {}
    row["departure"] = {
        "unit": unit, "route": tuple(action.get("move_path") or ()),
        "order_k": j, "order_step": f.cur_step, "unit_class": sc.unit_class(me),
        "ordered_from_inside_zone": tg.in_zone(me.get("cur_hex"), coord),
        "sole_occupant_at_order": zone_occupants(f, coord) == (unit,),
        "existing_path_at_order": bool(me.get("move_path")),
        "order_at_last_occupied_decision": j == row["last_occupied_k"],
        "steps_departure_to_loss": row["loss_step"] - side.frames[row["empty_k"]].cur_step,
        "steps_order_to_loss": row["loss_step"] - f.cur_step,
        "same_decision": row["empty_k"] == row["loss_k"],
        "baseline_v2_same_move": baseline_agreement(f, action),
        **enemy_information(side.frames, j, coord, me.get("type")),
        "onward": onward(side, row, unit, j, action),
    }
    check = tg.trigger(side.faction, f.own, list(f.enemies.values()), f.flags, f.actions, action) \
        if f.stage == 2 else tg.TriggerCheck(False, "not a play decision")
    passes_for_lost = check.eligible and (check.objective == coord or coord in check.overlaps)
    row["departure"]["trigger_reason"] = check.reason
    row["departure"]["trigger_passes_for_the_lost_objective"] = passes_for_lost
    idx = [i for i, a in enumerate(f.actions) if dict(a) == dict(action)]
    stateful = bool(idx) and any(i in shadow.withheld.get(j, ()) for i in idx)
    row["departure"]["withheld_by_shadow"] = stateful
    row["departure"]["side_first_divergence_k"] = shadow.first_divergence
    if not row["departure"]["ordered_from_inside_zone"]:
        row.update(category=NON_ACTIONABLE, category_reason="ordered before entering the zone")
    elif row["departure"]["baseline_v2_same_move"] != "identical":
        row.update(category=NON_ACTIONABLE, category_reason="baseline-v2 did not emit this MOVE")
    elif not check.eligible:
        row.update(category=NON_ACTIONABLE, category_reason=f"trigger: {check.reason}")
    elif not passes_for_lost:
        row.update(category=NON_ACTIONABLE, category_reason="withheld for another objective only")
    elif shadow.first_divergence is not None and j == shadow.first_divergence and stateful:
        if prefix_supported(side, j):
            row.update(category=TOUCHED, category_reason="withheld at the side's first divergence")
        else:
            row.update(category=PREFIX_UNSUPPORTED, category_reason="recorded actions differ from baseline-v2 earlier")
    elif shadow.first_divergence is not None and j > shadow.first_divergence:
        row.update(category=POST_DIVERGENCE, category_reason="after the side's first divergence")
    else:
        row.update(category="INCONSISTENT", category_reason="stateless trigger holds before or at the first divergence "
                                                            "without a withholding")


def baseline_agreement(frame: sc.Frame, action: Mapping[str, Any]) -> str:
    mine = [dict(a) for a in frame.actions if a.get("obj_id") == action.get("obj_id") and a.get("type") == tg.MOVE]
    if dict(action) in mine:
        return "identical"
    return "a different MOVE for the unit" if mine else "no MOVE for the unit"


# ------------------------------------------------------------------------------------------------
# per side

@dataclass
class SideAnalysis:
    side: Side
    losses: List[Dict[str, Any]]
    shadow: ShadowRun
    integrity: Dict[str, bool]


def analyse_side(side: Side) -> SideAnalysis:
    frames = side.frames
    integrity = {"frame positions equal decision indices": all(f.k == i for i, f in enumerate(frames)),
                 "one recorded list per decision": len(side.recorded) == len(frames)}
    shadow = run_shadow(side)
    rows = [anatomy(side, loss) for loss in loss_events(frames, side.faction)]
    for row in rows:
        classify_touch(side, row, shadow)
    census = sc.objective_defence(sc.Game(side.population, side.game, side.scenario, {side.faction: frames}, [],
                                          (side.faction,)), side.faction)
    integrity["losses equal the Sprint 18 N4 count"] = census["objective_losses"] == len(rows)
    integrity["no loss with an own unit on the objective at the previous decision"] = \
        census["losses_with_own_unit_on_it_before"] == 0
    integrity["no inconsistent touch category"] = all(r["category"] != "INCONSISTENT" for r in rows)
    first = shadow.first_divergence
    pre = True
    if first is not None:
        for j in range(first):
            pre &= list(shadow.candidate[j]) == [dict(a) for a in frames[j].actions]
            pre &= not any(c.eligible for (k, _, _, c) in shadow.checks if k == j)
    integrity["candidate equals baseline-v2 before the first divergence"] = pre
    integrity["withheld actions are MOVEs"] = all(frames[k].actions[i].get("type") == tg.MOVE
                                                  for k, idx in shadow.withheld.items() for i in idx)
    return SideAnalysis(side, rows, shadow, integrity)


# ------------------------------------------------------------------------------------------------
# public aggregates (section 12 to 16)

def dist(values: Iterable[Optional[float]]) -> Dict[str, Any]:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def tally(values: Iterable[Any]) -> List[List[Any]]:
    counts = collections.Counter(values)
    return [[v, counts[v]] for v in sorted(counts, key=lambda v: (str(type(v)), str(v)))]


def dedup_key(a: SideAnalysis, row: Mapping[str, Any]) -> Tuple[Any, ...]:
    """Replica de-duplication of a touched loss (section 16): the same scenario-side, objective, order step, departing
    unit and route count once however many recorded games repeat them."""
    d = row["departure"]
    return (a.side.scenario_side, row["coord"], d["order_step"], d["unit"], d["route"])


def distinct_touched(analyses: Sequence[SideAnalysis]) -> Tuple[int, List[Tuple[SideAnalysis, Dict[str, Any]]]]:
    """The touched losses (section 14): their raw count and the first occurrence of each replica key, in order."""
    seen: Dict[Tuple[Any, ...], Tuple[SideAnalysis, Dict[str, Any]]] = {}
    raw = 0
    for a in analyses:
        for r in a.losses:
            if r["category"] == TOUCHED:
                raw += 1
                seen.setdefault(dedup_key(a, r), (a, r))
    return raw, list(seen.values())


def stops(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    """The three frozen stop conditions (section 16), each reported whatever the others decide."""
    out: Dict[str, Any] = {}
    a_items = {}
    for name, part in (("H0", [a for a in analyses if a.side.population == "H0"]),
                       ("HH", [a for a in analyses if a.side.population == "HH"]), ("pooled", list(analyses))):
        rows = [r for a in part for r in a.losses]
        v = sum(1 for r in rows if r["v_class"] == V_ORDER)
        a_items[name] = {"v_order": v, "losses": len(rows), "share": f"{v}/{len(rows)}",
                         "met": len(rows) == 0 or 2 * v < len(rows)}
    out["A_departure_not_dominant"] = {"by_population": a_items, "met": any(i["met"] for i in a_items.values())}
    raw, touched = distinct_touched(analyses)
    sides = {a.side.scenario_side for a, _ in touched}
    out["B_insufficient_actionable_coverage"] = {
        "touched_raw": raw, "touched_distinct": len(touched), "distinct_scenario_sides": len(sides),
        "minimum_touched": STOP_B_MIN_TOUCHED, "minimum_scenario_sides": STOP_B_MIN_SCENARIO_SIDES,
        "met": len(touched) < STOP_B_MIN_TOUCHED or len(sides) < STOP_B_MIN_SCENARIO_SIDES}
    risk = sum(1 for a, r in touched if r["departure"]["onward"]["first_owner"])
    n = len(touched)
    out["C_onward_capture_interference"] = {
        "first_owner": risk, "touched_distinct": n, "share": f"{risk}/{n}", "evaluable": n > 0,
        "met": n == 0 or 2 * risk > n}
    return out


def disposition(fidelity_ok: bool, integrity_ok: bool, unexplained: int, stop: Mapping[str, Any]) -> Dict[str, Any]:
    """First match: INVALID (fidelity, integrity or any unexplained action difference), NOT_READY (any stop met),
    READY."""
    invalid = not fidelity_ok or not integrity_ok or unexplained != 0
    met = [k for k in ("A_departure_not_dominant", "B_insufficient_actionable_coverage",
                       "C_onward_capture_interference") if stop[k]["met"]]
    outcome = DISPOSITIONS[0] if invalid else DISPOSITIONS[1] if met else DISPOSITIONS[2]
    return {"disposition": outcome, "fidelity_ok": bool(fidelity_ok), "integrity_ok": bool(integrity_ok),
            "unexplained_action_differences": unexplained, "stops_met": met}


def public_loss(a: SideAnalysis, row: Mapping[str, Any], ordinal: int, counted: bool = False) -> Dict[str, Any]:
    """One sanitised loss row; ``counted`` marks the first occurrence of a touched loss's replica key (the rows stops
    B and C count)."""
    names = objective_labels(a.side.values)
    out: Dict[str, Any] = {
        "population": a.side.population, "side_game": a.side.label, "scenario_side": a.side.scenario_side,
        "loss_ordinal": ordinal, "objective": names.get(row["coord"], "unlabelled objective"),
        "loss_step": row["loss_step"], "v_class": row["v_class"], "v_reason": row["v_reason"],
        "last_defenders": len(row.get("defenders") or []),
        "defender_classes": sorted(sc.unit_class(a.side.frames[row["last_occupied_k"]].own[d])
                                   for d in row.get("defenders") or [] if "last_occupied_k" in row),
        "fates": sorted(row.get("fates", {}).values()),
        "zone_reentries_before_loss": row["reentries"],
        "steps_zone_empty_to_loss": (row["loss_step"] - row["empty_step"]) if "empty_step" in row else None,
        "category": row["category"], "category_reason": row["category_reason"],
        "counted_in_stops_b_and_c": bool(counted),
    }
    d = row.get("departure")
    if d:
        out["departure"] = {k: v for k, v in d.items() if k not in ("unit", "route", "onward")}
        out["departure"]["route_length"] = len(d["route"])
        on = dict(d["onward"])
        on["next_objective"] = names.get(on["next_objective"], "unlabelled objective") \
            if on["next_objective"] is not None else None
        out["departure"]["onward"] = on
    return out


def side_summary(a: SideAnalysis) -> Dict[str, Any]:
    s = a.shadow
    starts = [(k, e) for k, e in s.events if e.kind == "start"]
    releases = [(k, e) for k, e in s.events if e.kind == "release"]
    rows = a.losses
    first = s.first_divergence
    out = {
        "side_game": a.side.label, "population": a.side.population, "scenario_side": a.side.scenario_side,
        "decisions": len(a.side.frames), "play_decisions": sum(1 for f in a.side.frames if f.stage == 2),
        "losses": len(rows), "v_classes": {c: sum(1 for r in rows if r["v_class"] == c) for c in V_CLASSES},
        "categories": {c: sum(1 for r in rows if r["category"] == c) for c in CATEGORIES},
        "move_checks": len(s.checks), "trigger_reasons": dict(sorted(collections.Counter(c.reason for *_, c in s.checks).items())),
        "episodes": len(starts), "withheld_decisions": len(s.withheld),
        "withheld_actions": sum(len(v) for v in s.withheld.values()),
        "repeats": sum(1 for _, e in s.events if e.kind == "repeat"),
        "overlaps": sum(1 for _, e in s.events if e.kind == "overlap"),
        "passes_in_hold": sum(1 for _, e in s.events if e.kind == "pass_in_hold"),
        "release_reasons": dict(sorted(collections.Counter(e.reason for _, e in releases).items())),
        "synthetic_hold_steps": dist([e.step - e.hold_start for _, e in releases]),
        "episodes_open_at_end": len(starts) - len(releases),
        "first_divergence": None if first is None else {
            "decision": first, "step": a.side.frames[first].cur_step, "decisions_before_identical": first,
            "prefix_supported": prefix_supported(a.side, first),
            "withheld_actions": len(s.withheld[first]),
            "is_a_loss_departure": any(r["category"] in (TOUCHED, PREFIX_UNSUPPORTED) for r in rows)},
        "post_divergence_episodes": max(0, len(starts) - (1 if first is not None else 0)),
        "unexplained_action_differences": len(s.unexplained),
        "integrity": dict(sorted(a.integrity.items())),
    }
    return out


def certificate(a: SideAnalysis) -> Optional[Dict[str, Any]]:
    """The public first-divergence certificate of one side-game (section 13)."""
    s = a.shadow
    first = s.first_divergence
    if first is None:
        return None
    f = a.side.frames[first]
    names = objective_labels(a.side.values)
    items = []
    for k, e in s.events:
        if k != first or e.kind != "start":
            continue
        unit = f.own[e.unit]
        action = f.actions[e.index]
        check = next(c for k, i, u, c in s.checks if k == first and i == e.index)
        items.append({"objective": names.get(e.objective, "unlabelled objective"), "unit_class": sc.unit_class(unit),
                      "route_length": len(action.get("move_path") or ()),
                      "existing_path": bool(unit.get("move_path")),
                      "qualifying_threats": len(check.threats),
                      "threat_reaches": sorted(t.reach for t in check.threats),
                      "nearest_threat_distance": min(t.distance for t in check.threats),
                      "nearest_threat_margin": min(t.distance - (t.reach + tg.THREAT_MARGIN) for t in check.threats),
                      "overlaps": len(check.overlaps), "dropped_position": e.index,
                      "precedes_a_loss_of_this_objective": any(
                          r["coord"] == e.objective and r.get("departure") and r["departure"]["order_k"] == first
                          for r in a.losses)})
    return {"side_game": a.side.label, "population": a.side.population, "decision": first, "step": f.cur_step,
            "decisions_before_identical": first, "prefix_supported": prefix_supported(a.side, first),
            "baseline_action_types": [x.get("type") for x in f.actions],
            "candidate_action_types": [x.get("type") for x in s.candidate[first]],
            "withheld": items}


def pooled_table(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    rows = [(a, r) for a in analyses for r in a.losses]

    def count(pred) -> Dict[str, int]:
        sel = [(a, r) for a, r in rows if pred(a, r)]
        return {"events": len(sel), "games": len({a.side.game for a, _ in sel}),
                "side_games": len({(a.side.game, a.side.faction) for a, _ in sel}),
                "scenario_sides": len({a.side.scenario_side for a, _ in sel}),
                "distinct_setups": len({(a.side.scenario_side, r["coord"]) for a, r in sel}),
                "defender_units": len({(a.side.game, a.side.faction, d) for a, r in sel for d in r.get("defenders") or []})}

    deps = [(a, r, r["departure"]) for a, r in rows if r.get("departure")]
    return {
        "losses": count(lambda a, r: True),
        "by_v_class": {c: count(lambda a, r, c=c: r["v_class"] == c) for c in V_CLASSES},
        "v_reasons": tally(r["v_reason"] for _, r in rows),
        "by_category": {c: count(lambda a, r, c=c: r["category"] == c) for c in CATEGORIES},
        "category_reasons": tally(r["category_reason"] for _, r in rows),
        "last_defender_identified": sum(1 for _, r in rows if r.get("defenders") and "empty_k" in r),
        "zone_became_empty": sum(1 for _, r in rows if "empty_k" in r),
        "last_defenders": tally(len(r.get("defenders") or []) for _, r in rows),
        "single_defender_departures": len(deps),
        "departure_enemy_info": tally(d["enemy_info"] for _, _, d in deps),
        "departures_with_visible_enemy_without_published_range": sum(1 for *_, d in deps if d["visible_without_published_range"]),
        "steps_departure_to_loss": dist([d["steps_departure_to_loss"] for *_, d in deps]),
        "steps_order_to_loss": dist([d["steps_order_to_loss"] for *_, d in deps]),
        "order_to_loss_within_hold_limit": sum(1 for *_, d in deps if d["steps_order_to_loss"] < tg.HOLD_LIMIT),
        "same_decision_empty_and_lost": sum(1 for *_, d in deps if d["same_decision"]),
        "departing_unit_class": tally(d["unit_class"] for *_, d in deps),
        "ordered_from_inside_zone": sum(1 for *_, d in deps if d["ordered_from_inside_zone"]),
        "order_at_last_occupied_decision": sum(1 for *_, d in deps if d["order_at_last_occupied_decision"]),
        "existing_path_at_order": sum(1 for *_, d in deps if d["existing_path_at_order"]),
        "baseline_v2_same_move": tally(d["baseline_v2_same_move"] for *_, d in deps),
        "trigger_reason_at_departure": tally(d["trigger_reason"] for *_, d in deps),
        "withheld_by_stateful_shadow": sum(1 for *_, d in deps if d["withheld_by_shadow"]),
        "nearest_visible_enemy_distance": dist([d["nearest_visible_distance"] for *_, d in deps]),
        "threat_margin_at_departure": dist([d["threat_margin"] for *_, d in deps]),
        "onward_destination": tally(d["onward"]["destination_kind"] for *_, d in deps),
        "onward_first_owner": sum(1 for *_, d in deps if d["onward"]["first_owner"]),
        "onward_first_owner_of_any_objective": sum(1 for *_, d in deps if d["onward"]["first_owner_of_any_objective_after_order"]),
        "onward_unit_later_lost": sum(1 for *_, d in deps if d["onward"]["unit_later_lost"]),
    }


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
    words of strings, numeric leaves (aggregates, steps and distances by construction) masked."""
    from .s12_screen import privacy_problems
    return privacy_problems(data) + privacy_problems(mask_numbers(data), sorted({str(v) for v in private_values}))
