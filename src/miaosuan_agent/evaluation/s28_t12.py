"""Sprint 28 T12-O1 objective-zone dispersion offline qualification (``docs/SPRINT28_T12_O1.md``).

Pure functions over Sprint 18 census frames (``evaluation/s18_census.py``). Nothing here reaches a policy or an engine.

A side's frames are its decisions in order (``frame.k`` equals the position); ``recorded`` holds, per frame, the action
list the historical seat submitted (H0: ``baseline-v0``; HH: ``baseline-v2``), and ``frame.actions`` the ``baseline-v2``
list (H0: reconstructed on the recorded observation; HH: the recorded seat, equal to the reconstruction at every
decision by Sprint 18's check). ``extras`` holds, per frame, the raw transition fields of the own ground operators, and
``roadblocks`` the roadblock hexes of the game's observation. Definitions are the registration's (sections 5 to 20);
every docstring says which section it implements.

Private rows (unit ids, hexes, routes) stay in the returned objects; the ``public_*`` functions emit aggregates and
labels only.
"""

from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..decision.routing import ROADBLOCKED_MODES, move_mode
from ..experiments import t12_dispersion_shadow as ts
from . import s18_census as sc
from .t7_visibility import hex_distance

STUDY_ID = "s28-t12-o1"
HH_SIDE_GAMES = 4
H0_SIDE_GAMES = 16
#: Registered opportunity stop (section 18): every HH side-game needs at least this many distinct trigger episodes.
STOP_MIN_EPISODES_PER_HH_SIDE_GAME = 1
#: Damage windows (steps) before and after an episode start (Sprint 18's lookback window).
WINDOW = 300
DISPOSITIONS = ("T12_O1_OFFLINE_INVALID", "T12_O1_INADEQUATE_OPPORTUNITY", "T12_O1_LEGALITY_UNRESOLVED",
                "T12_O1_INTERACTION_NOT_READY", "T12_O1_READY_FOR_MECHANISM_PROPOSAL")
#: Interaction criteria (section 19), each met on a strict majority of its denominator in HH, H0 or pooled.
INTERACTION_CRITERIA = ("I1_tactical_isolation", "I2_holder_ordered_off", "I3_partial_dispersion")
DEST_HELD, DEST_UNHELD, DEST_NOT_OBJECTIVE = "objective held", "objective not held", "not an objective"
TIERS = ("trigger", "legal")


# ------------------------------------------------------------------------------------------------
# side data

@dataclass
class Side:
    """One analysed side of one game (section 4)."""

    population: str
    label: str
    game: str
    scenario: str
    faction: int
    frames: List[sc.Frame]
    recorded: List[List[Mapping[str, Any]]]
    costs: Any
    roadblocks: frozenset
    extras: List[Mapping[Any, Mapping[str, Any]]]
    damage_rows: List[Mapping[str, Any]] = field(default_factory=list)
    values: Mapping[Any, Any] = field(default_factory=dict)
    actor: Any = None

    @property
    def colour(self) -> str:
        return "red" if self.faction == 0 else "blue"

    @property
    def scenario_side(self) -> str:
        return f"{self.scenario} {self.colour}"


def context(side: Side, f: sc.Frame) -> ts.Context:
    return ts.Context(side.faction, f.cur_step, f.stage, f.own, tuple(f.enemies.values()), f.flags, f.valid,
                      tuple(dict(a) for a in f.actions), side.costs, side.roadblocks, side.extras[f.k], side.actor)


def objective_labels(values: Mapping[Any, Any]) -> Dict[Any, str]:
    from .s12_timeline import labels
    return labels(dict(values))


def first_ownership(frames: Sequence[sc.Frame], faction: int, coord: Any) -> Optional[int]:
    """The decision of the side's first-ever play-stage ownership of ``coord``."""
    for f in frames:
        if f.stage == 2 and f.flags.get(coord) == faction:
            return f.k
    return None


def prefix_supported(side: Side, upto: int) -> bool:
    """H0: the recorded ``baseline-v0`` actions equal ``baseline-v2``'s at every decision before ``upto`` (Sprint 23's
    evidence boundary); HH: the recorded seat equals ``baseline-v2`` there."""
    return all([dict(a) for a in side.recorded[j]] == [dict(a) for a in side.frames[j].actions] for j in range(upto))


# ------------------------------------------------------------------------------------------------
# section 17: the stateful shadow, the independent check and the first divergence

class IndependentCheck:
    """Section 17: an independent restatement, from the frames' fields, of what every difference between the
    candidate list and ``baseline-v2``'s must satisfy. The candidate must be ``baseline-v2``'s list with some MOVEs
    removed, in order, followed by appended actions. A removed action must be a MOVE of a unit this check has accepted
    as dispersed earlier, while that dispersal's objective is still held and the unit is present. An appended action
    must be exactly ``{"actor", "obj_id", "type": 1, "move_path": [n]}`` for an own ground unit not dispersed before,
    standing on the hex ``c`` of an objective the side holds, idle (speed not positive, no observed route, stop flag
    not 0, no stop, state or transport transition, not suppressed, no ``baseline-v2`` action), with type 1 listed; at
    least two such idle units not dispersed before stand on ``c``; ``n`` is at distance 1 from ``c`` inside the map,
    a neighbour of ``c`` in the unit's movement mode, not a roadblock for vehicle modes, not an objective, holds no
    visible enemy, is on no own observed route and no ``baseline-v2`` MOVE route, and its own ground units plus the
    units appended to it earlier at this decision are fewer than four; and after the appended actions at least one
    idle unit on ``c`` is neither appended nor dispersed before."""

    KEYS = {"actor", "obj_id", "type", "move_path"}

    def __init__(self, side: Side) -> None:
        self.side = side
        self.dispersed: Dict[Any, Any] = {}

    def idle(self, f: sc.Frame, unit_id: Any, acted: Set[Any]) -> bool:
        u = f.own.get(unit_id)
        x = self.side.extras[f.k].get(unit_id) or {}
        if u is None or u.get("type") not in (1, 2) or sc.as_int(u.get("cur_hex")) is None:
            return False

        def pos(v: Any) -> bool:
            return sc.is_number(v) and v > 0

        return (not pos(u.get("speed")) and not u.get("move_path") and x.get("stop") != 0
                and not pos(x.get("move_to_stop_remain_time")) and not pos(x.get("change_state_remain_time"))
                and not pos(x.get("get_on_remain_time")) and not pos(x.get("get_off_remain_time"))
                and not u.get("keep") and unit_id not in acted)

    def step(self, f: sc.Frame, candidate: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        faction = self.side.faction
        for u in list(self.dispersed):
            if f.flags.get(self.dispersed[u]) != faction or u not in f.own:
                del self.dispersed[u]
        base = [dict(a) for a in f.actions]
        cand = [dict(a) for a in candidate]
        i, removed = 0, []
        for a in base:
            if i < len(cand) and cand[i] == a:
                i += 1
            else:
                removed.append(a)
        appended = cand[i:]
        for a in removed:
            if a.get("type") != 1 or a.get("obj_id") not in self.dispersed:
                out.append({"k": f.k, "problem": "a removed action is not a MOVE of a dispersed unit", "action": a})
        acted = {a.get("obj_id") for a in base}
        counts = collections.Counter(u["cur_hex"] for u in f.own.values()
                                     if u.get("type") in (1, 2) and sc.as_int(u.get("cur_hex")) is not None)
        routes = {h for u in f.own.values() for h in (u.get("move_path") or ())}
        routes |= {h for a in base if a.get("type") == 1 for h in (a.get("move_path") or ())}
        enemy = {e.get("cur_hex") for e in f.enemies.values()}
        added_to: collections.Counter = collections.Counter()
        appended_units: Dict[Any, Any] = {}
        for a in appended:
            problem = self.explain(f, a, acted, counts, routes, enemy, added_to, appended_units)
            if problem:
                out.append({"k": f.k, "problem": problem, "action": a})
                continue
            appended_units[a["obj_id"]] = f.own[a["obj_id"]]["cur_hex"]
            added_to[a["move_path"][0]] += 1
        for c in set(appended_units.values()):
            stay = [o for o, u in f.own.items() if u.get("cur_hex") == c and o not in appended_units
                    and o not in self.dispersed and self.idle(f, o, acted)]
            if not stay:
                out.append({"k": f.k, "problem": "no idle holder stays on the objective"})
        for o, c in appended_units.items():
            self.dispersed[o] = c
        return out

    def explain(self, f: sc.Frame, a: Mapping[str, Any], acted: Set[Any], counts: Mapping[int, int],
                routes: Set[Any], enemy: Set[Any], added_to: Mapping[int, int],
                appended_units: Mapping[Any, Any]) -> Optional[str]:
        if set(a) != self.KEYS or a.get("type") != 1 or a.get("actor") != self.side.actor:
            return "an appended action is not a registered MOVE"
        o = a.get("obj_id")
        if o in self.dispersed or o in appended_units:
            return "a unit is dispersed twice"
        u = f.own.get(o)
        if u is None or not self.idle(f, o, acted):
            return "an appended MOVE is not of an idle own ground unit"
        c = u["cur_hex"]
        if f.flags.get(c) != self.side.faction:
            return "the unit is not on an objective the side holds"
        if sum(1 for x in f.own if f.own[x].get("cur_hex") == c and x not in self.dispersed
               and self.idle(f, x, acted)) < 2:
            return "fewer than two idle units on the objective"
        if 1 not in (f.valid.get(o) or {}):
            return "movement is not listed for the unit"
        route = a.get("move_path")
        if not isinstance(route, list) or len(route) != 1 or sc.as_int(route[0]) is None:
            return "the route is not one hex"
        n = route[0]
        rows, cols = self.side.costs.rows, self.side.costs.cols
        if hex_distance(c, n) != 1 or not (0 <= n // 100 < rows and 0 <= n % 100 < cols):
            return "the destination is not a neighbour inside the map"
        mode = move_mode(u.get("type"), u.get("move_state"))
        if mode is None or n not in self.side.costs.neighbours(mode, c):
            return "the destination is not traversable in the unit's mode"
        if mode in ROADBLOCKED_MODES and n in self.side.roadblocks:
            return "the destination is a roadblock for a vehicle"
        if n in f.flags:
            return "the destination is an objective"
        if n in enemy:
            return "the destination holds a visible enemy"
        if n in routes:
            return "the destination is on an own route"
        if counts.get(n, 0) + added_to.get(n, 0) >= ts.STACK_LIMIT:
            return "the destination would exceed the stacking limit"
        return None


@dataclass
class ShadowRun:
    candidate: List[Tuple[Mapping[str, Any], ...]]
    added: Dict[int, Tuple[Mapping[str, Any], ...]]
    withheld: Dict[int, Tuple[int, ...]]
    events: List[Tuple[int, ts.DispersionEvent]]
    checks: Dict[int, Tuple[ts.ObjectiveCheck, ...]]
    first_divergence: Optional[int]
    unexplained: List[Dict[str, Any]]


def run_shadow(side: Side) -> ShadowRun:
    """The frozen shadow on every decision of the side from an empty memory (the candidate's lists)."""
    memory = ts.DispersionMemory()
    checker = IndependentCheck(side)
    candidate, added, withheld, events, checks, unexplained = [], {}, {}, [], {}, []
    for f in side.frames:
        result = ts.decide(context(side, f), memory)
        memory = result.memory
        candidate.append(result.actions)
        if result.added:
            added[f.k] = result.added
        if result.withheld:
            withheld[f.k] = result.withheld
        events.extend((f.k, e) for e in result.events)
        if result.checks:
            checks[f.k] = result.checks
        if f.stage == 2:
            unexplained.extend(checker.step(f, result.actions))
    changed = sorted(set(added) | set(withheld))
    return ShadowRun(candidate, added, withheld, events, checks, changed[0] if changed else None, unexplained)


# ------------------------------------------------------------------------------------------------
# sections 8 to 11 and 15: the stateless census

def passes_through(level: str, upto: str) -> bool:
    """Whether a unit whose first failing idle level is ``level`` (or ``"idle"``) passes every level up to ``upto``."""
    order = ts.IDLE_LEVELS
    return level == "idle" or order.index(level) > order.index(upto)


def stateless_checks(side: Side) -> Dict[int, Tuple[ts.ObjectiveCheck, ...]]:
    """Section 15: every play decision's objective checks with no hold in force."""
    return {f.k: ts.evaluate(context(side, f)) for f in side.frames if f.stage == 2}


def census(side: Side, checks: Mapping[int, Tuple[ts.ObjectiveCheck, ...]]) -> Dict[str, Any]:
    """Section 15: nested objective-decision counts, unit-decision counts, reasons and occupancy (a group listed again
    at a later decision is counted again; these are not episodes)."""
    out: collections.Counter = collections.Counter()
    held: Set[Any] = set()
    legal_reasons: collections.Counter = collections.Counter()
    admissible: collections.Counter = collections.Counter()
    outcomes: collections.Counter = collections.Counter()
    centre_counts: collections.Counter = collections.Counter()
    zone_counts: collections.Counter = collections.Counter()
    first_failing: collections.Counter = collections.Counter()
    for k, objectives in checks.items():
        f = side.frames[k]
        routes = ts.route_hexes(context(side, f))
        enemy = frozenset(e["cur_hex"] for e in f.enemies.values() if ts.hex_int(e.get("cur_hex")) is not None)
        triggered = [c for c in objectives if c.trigger]
        zones = [set(n for n, _, _ in c.neighbour_counts) for c in triggered]
        out["decisions_with_two_triggered_objectives_sharing_a_neighbour"] += any(
            zones[i] & zones[j] for i in range(len(zones)) for j in range(i + 1, len(zones)))
        for c in objectives:
            held.add(c.objective)
            out["held_objective_decisions"] += 1
            levels = [lv for _, lv in c.centre_units]
            for lv in levels:
                first_failing[lv] += 1
            if len(levels) >= 2:
                out["centre_two_or_more_ground"] += 1
            for lv in ts.IDLE_LEVELS:
                if sum(1 for x in levels if passes_through(x, lv)) >= 2:
                    out[f"centre_two_or_more_through_{lv}"] += 1
            if len(c.idle) >= ts.MIN_IDLE:
                out["two_or_more_idle"] += 1
            out["idle_centre_unit_decisions"] += len(c.idle)
            if not c.trigger:
                if len(c.idle) >= ts.MIN_IDLE:
                    out["two_or_more_idle_no_passable_neighbour"] += 1
                continue
            out["trigger"] += 1
            out["trigger_with_a_visible_enemy_on_a_neighbour"] += any(n in enemy for n, _, _ in c.neighbour_counts)
            centre_counts[len(c.centre_units)] += 1
            zone_counts[sum(n for _, n, _ in c.neighbour_counts)] += 1
            legal_any = any(r == ts.LEGAL_REASONS[0] for x in c.units for _, r in x.legal)
            out["trigger_with_a_legal_one_hex_move"] += legal_any
            out["trigger_with_an_admissible_destination"] += any(x.admissible for x in c.units)
            out["legal_tier"] += c.legal_tier
            out["legal_tier_complete"] += c.legal_tier and all(x.outcome in ("holder", "dispersed") for x in c.units)
            out["legal_unit_decisions"] += sum(1 for x in c.units if any(r == ts.LEGAL_REASONS[0] for _, r in x.legal))
            for x in c.units:
                outcomes[x.outcome] += 1
                for n, r in x.legal:
                    legal_reasons[r] += 1
                    if r == ts.LEGAL_REASONS[0]:
                        admissible[ts.admissible_reason(context(side, f), n, routes, enemy)] += 1
    out["held_objectives"] = len(held)
    return {"objective_decisions": dict(sorted(out.items())),
            "first_failing_idle_level_unit_decisions": dict(sorted(first_failing.items())),
            "legal_reasons_unit_neighbour_pairs": dict(sorted(legal_reasons.items())),
            "admissibility_of_legal_pairs": dict(sorted(admissible.items())),
            "batch_outcomes_unit_decisions": dict(sorted(outcomes.items())),
            "trigger_centre_own_ground": tally(centre_counts.elements()),
            "trigger_neighbour_own_ground_total": tally(zone_counts.elements())}


# ------------------------------------------------------------------------------------------------
# section 15: episodes (maximal runs)

def episodes(side: Side, checks: Mapping[int, Tuple[ts.ObjectiveCheck, ...]], tier: str) -> List[Dict[str, Any]]:
    """Maximal runs of consecutive play decisions at which one objective meets the tier (``trigger``: the theoretical
    trigger; ``legal``: the frozen batch disperses at least one unit). One episode per run; the decisions after the
    first are repeated listings, not new episodes."""
    flag: Dict[int, Dict[int, ts.ObjectiveCheck]] = {}
    for k, objectives in checks.items():
        for c in objectives:
            if (c.trigger if tier == "trigger" else c.legal_tier):
                flag.setdefault(c.objective, {})[k] = c
    rows = []
    for objective in sorted(flag):
        ks = sorted(flag[objective])
        start = prev = ks[0]
        for k in ks[1:] + [None]:
            if k is not None and k == prev + 1:
                prev = k
                continue
            c = flag[objective][start]
            rows.append({"tier": tier, "objective": objective, "start_k": start, "end_k": prev,
                         "decisions": prev - start + 1, "start_step": side.frames[start].cur_step,
                         "idle": tuple(c.idle), "check": c})
            if k is not None:
                start = prev = k
    rows.sort(key=lambda r: (r["start_k"], r["objective"]))
    return rows


def episode_key(side: Side, row: Mapping[str, Any]) -> Tuple[Any, ...]:
    """Replica de-duplication: the same scenario-side, objective, start step and idle units count once."""
    return (side.scenario_side, row["objective"], row["start_step"], tuple(sorted(row["idle"])))


# ------------------------------------------------------------------------------------------------
# section 12: onward movement and the cost of the hold (historical indicators)

def destination_kind(frame: sc.Frame, faction: int, dest: Any) -> str:
    if dest in frame.flags:
        return DEST_HELD if frame.flags[dest] == faction else DEST_UNHELD
    return DEST_NOT_OBJECTIVE


def onward(side: Side, row: Mapping[str, Any], lost: Mapping[Any, int]) -> Dict[str, Any]:
    """Section 12 for one legal episode, on the recorded trajectory after its start (labels for analysis only; future
    ownership is never an online input)."""
    frames, faction = side.frames, side.faction
    k, obj = row["start_k"], row["objective"]
    c: ts.ObjectiveCheck = row["check"]
    release = next((g.k for g in frames[k + 1:] if g.stage == 2 and g.flags.get(obj) != faction), None)
    end = release if release is not None else len(frames)
    units = []
    for u, dest_hex in c.dispersed:
        first = None
        suppressed = 0
        for g in frames[k + 1:end]:
            if u not in g.own:
                break
            moves = [a for a in g.actions if a.get("type") == 1 and a.get("obj_id") == u]
            if moves:
                suppressed += 1
                if first is None:
                    first = (g, moves[0])
        rec: Dict[str, Any] = {"unit": u, "dispersal_destination": dest_hex, "suppressed_move_decisions": suppressed,
                               "onward_move": first is not None, "later_lost": u in lost and lost[u] > k}
        if first is not None:
            g, a = first
            dest = list(a.get("move_path") or ())[-1] if a.get("move_path") else None
            kind = destination_kind(g, faction, dest)
            fo = first_ownership(frames, faction, dest) if kind != DEST_NOT_OBJECTIVE else None
            after = fo is not None and fo > g.k
            owners = sorted(o for o, x in frames[fo].own.items() if ts.is_ground(x) and x["cur_hex"] == dest) if after else []
            rec.update({"steps_to_onward_move": g.cur_step - frames[k].cur_step, "onward_destination_kind": kind,
                        "onward_destination": dest,
                        "claimant": kind == DEST_UNHELD,
                        "first_owner": after and u in owners,
                        "other_own_first_owners": after and any(o != u for o in owners),
                        "destination_first_owned_before_order": fo is not None and not after,
                        "destination_never_owned": kind != DEST_NOT_OBJECTIVE and fo is None})
        units.append(rec)
    holder = c.holder
    holder_off = None
    for g in frames[k + 1:end]:
        if holder not in g.own:
            break
        if any(a.get("type") == 1 and a.get("obj_id") == holder for a in g.actions):
            holder_off = g.cur_step - frames[k].cur_step
            break
    return {"units": units, "hold_release_steps": None if release is None else frames[release].cur_step - frames[k].cur_step,
            "hold_to_end": release is None, "holder_ordered_off_while_held": holder_off is not None,
            "holder_ordered_off_steps": holder_off}


# ------------------------------------------------------------------------------------------------
# section 16: historical damage diagnostics

def holding_run_start(frames: Sequence[sc.Frame], faction: int, coord: Any, k: int) -> Optional[int]:
    """The first decision of the continuous holding run of ``coord`` that contains ``k`` (``None`` if not held at k)."""
    if frames[k].flags.get(coord) != faction:
        return None
    j = k
    while j > 0 and frames[j - 1].stage == 2 and frames[j - 1].flags.get(coord) == faction:
        j -= 1
    return j


def damage_rows(side: Side, checks: Mapping[int, Tuple[ts.ObjectiveCheck, ...]], first: Optional[int]) -> List[Dict[str, Any]]:
    """Section 16: one row per damage event on a stationary own ground unit standing on an objective hex (Sprint 18's
    event rows), with whether the objective was held, and whether the trigger or the legal tier held at that objective
    at an earlier decision of the same holding run."""
    out = []
    by_obj: Dict[Any, Dict[int, ts.ObjectiveCheck]] = collections.defaultdict(dict)
    for k, objectives in checks.items():
        for c in objectives:
            by_obj[c.objective][k] = c
    for r in side.damage_rows:
        if r["victim_class"] not in ("infantry", "vehicle", "artillery") or r["aboard"] or r["moving"] or not r["on_objective"]:
            continue
        k = min(r["k"], len(side.frames) - 1)
        victim, _ = sc.last_seen_unit(side.frames, r["k"], r["victim"])
        coord = victim.get("cur_hex") if victim else None
        run = holding_run_start(side.frames, side.faction, coord, k) if coord is not None else None
        earlier = [j for j in range(run, k) if j in by_obj.get(coord, {})] if run is not None else []
        trig = [j for j in earlier if by_obj[coord][j].trigger]
        legal = [j for j in earlier if by_obj[coord][j].legal_tier]
        out.append({"k": r["k"], "step": r["step"], "victim": r["victim"], "objective": coord,
                    "victim_class": r["victim_class"], "stacked": r["stacked"], "held": run is not None,
                    "attacker_seen_at_event": r["seen_at_event"], "attacker_seen_before": r["seen_before"],
                    "victim_lost": r["lost"], "earlier_trigger": bool(trig), "earlier_legal": bool(legal),
                    "steps_since_latest_legal": (side.frames[k].cur_step - side.frames[legal[-1]].cur_step) if legal else None,
                    "earlier_legal_at_first_divergence": bool(legal) and first is not None and first in legal})
    return out


def episode_damage(side: Side, row: Mapping[str, Any]) -> Dict[str, Any]:
    """Damage events on the episode's idle centre units within ``WINDOW`` steps before and after its start."""
    start = row["start_step"]
    members = set(row["idle"])
    before = [r for r in side.damage_rows if r["victim"] in members and start - WINDOW <= r["step"] < start]
    after = [r for r in side.damage_rows if r["victim"] in members and start <= r["step"] <= start + WINDOW]
    return {"centre_units_damaged_before": len({r["victim"] for r in before}), "damage_events_before": len(before),
            "centre_units_damaged_after": len({r["victim"] for r in after}), "damage_events_after": len(after),
            "damage_events_after_victim_stacked": sum(1 for r in after if r["stacked"])}


# ------------------------------------------------------------------------------------------------
# per side

@dataclass
class SideAnalysis:
    side: Side
    shadow: ShadowRun
    checks: Dict[int, Tuple[ts.ObjectiveCheck, ...]]
    census: Dict[str, Any]
    trigger_episodes: List[Dict[str, Any]]
    legal_episodes: List[Dict[str, Any]]
    damage: List[Dict[str, Any]]
    integrity: Dict[str, bool]


def analyse_side(side: Side) -> SideAnalysis:
    frames = side.frames
    integrity = {"frame positions equal decision indices": all(f.k == i for i, f in enumerate(frames)),
                 "one recorded list per decision": len(side.recorded) == len(frames),
                 "one extras map per decision": len(side.extras) == len(frames)}
    shadow = run_shadow(side)
    checks = stateless_checks(side)
    trig = episodes(side, checks, "trigger")
    legal = episodes(side, checks, "legal")
    lost = sc.lost_units(frames)
    first = shadow.first_divergence
    for row in legal:
        row["onward"] = onward(side, row, lost)
        row["damage"] = episode_damage(side, row)
        row["first_divergence"] = first is not None and row["start_k"] == first
        row["post_divergence"] = first is not None and row["start_k"] > first
        row["prefix_supported"] = prefix_supported(side, row["start_k"]) if row["first_divergence"] else None
    first_legal = min((k for k, objs in checks.items() if any(c.legal_tier for c in objs)), default=None)
    integrity["first divergence is the first legal-tier decision"] = first == first_legal
    pre = True
    if first is not None:
        pre = all(list(shadow.candidate[j]) == [dict(a) for a in frames[j].actions] for j in range(first))
        pre &= not shadow.withheld.get(first)
        pre &= [ (c.objective, c.dispersed) for c in shadow.checks.get(first, ()) ] == \
            [(c.objective, c.dispersed) for c in checks.get(first, ())]
    integrity["candidate equals baseline-v2 before the first divergence, stateful equals stateless there"] = pre
    integrity["withheld actions are MOVEs"] = all(frames[k].actions[i].get("type") == ts.MOVE
                                                  for k, idx in shadow.withheld.items() for i in idx)
    integrity["every legal episode lies inside a trigger episode"] = all(
        any(t["objective"] == r["objective"] and t["start_k"] <= r["start_k"] <= t["end_k"] for t in trig) for r in legal)
    integrity["no unit is on two centres"] = all(len({u for c in objs for u, _ in c.centre_units})
                                                 == sum(len(c.centre_units) for c in objs) for objs in checks.values())
    integrity["every legal batch keeps a holder"] = all(c.holder is not None for objs in checks.values() for c in objs
                                                        if c.legal_tier)
    return SideAnalysis(side, shadow, checks, census(side, checks), trig, legal, damage_rows(side, checks, first), integrity)


# ------------------------------------------------------------------------------------------------
# sections 18 to 20: stops, readiness criteria and disposition

def majority(part: int, whole: int) -> bool:
    """Strictly more than one half (the convention of Sprints 23, 25 and 26)."""
    return 2 * part > whole


def distinct(analyses: Sequence[SideAnalysis], tier: str) -> Dict[Tuple[Any, ...], List[Tuple[SideAnalysis, Dict[str, Any]]]]:
    out: Dict[Tuple[Any, ...], List[Tuple[SideAnalysis, Dict[str, Any]]]] = {}
    for a in analyses:
        for r in (a.trigger_episodes if tier == "trigger" else a.legal_episodes):
            out.setdefault(episode_key(a.side, r), []).append((a, r))
    return out


def interaction(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    """Section 19's interaction criteria over the distinct legal episodes (first replica of each key), per
    population and pooled; a criterion is met when it is met in any of the three with a non-empty denominator."""
    out: Dict[str, Any] = {}
    groups = {"HH": [a for a in analyses if a.side.population == "HH"],
              "H0": [a for a in analyses if a.side.population == "H0"], "pooled": list(analyses)}
    for name, part in groups.items():
        eps = [occ[0][1] for occ in distinct(part, "legal").values()]
        units = [u for r in eps for u in r["onward"]["units"]]
        claim = sum(1 for u in units if u.get("claimant"))
        owner = sum(1 for u in units if u.get("first_owner"))
        holder = sum(1 for r in eps if r["onward"]["holder_ordered_off_while_held"])
        partial = sum(1 for r in eps if any(x.outcome in ("no_destination_left", "no_admissible_destination")
                                            for x in r["check"].units))
        out[name] = {"distinct_legal_episodes": len(eps), "dispersed_units": len(units),
                     "claimant_units": claim, "first_owner_units": owner,
                     "episodes_holder_ordered_off_while_held": holder, "episodes_partial_dispersion": partial,
                     "I1_tactical_isolation": bool(units) and majority(claim, len(units)),
                     "I2_holder_ordered_off": bool(eps) and majority(holder, len(eps)),
                     "I3_partial_dispersion": bool(eps) and majority(partial, len(eps))}
    out["met"] = {c: any(out[g][c] for g in groups) for c in INTERACTION_CRITERIA}
    return out


def stops(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    """Section 18's registered opportunity stop (HH, primary), its H0 readings (reported only), and section 20's
    legality gate."""
    hh = [a for a in analyses if a.side.population == "HH"]
    h0 = [a for a in analyses if a.side.population == "H0"]
    per_hh = {a.side.label: len(a.trigger_episodes) for a in hh}
    per_h0 = {a.side.label: len(a.trigger_episodes) for a in h0}
    legal_hh = {a.side.label: len(a.legal_episodes) for a in hh}
    out = {
        "opportunity_stop": {
            "rule": "met when any of the four HH side-games has fewer than one distinct trigger episode, or the HH "
                    "side-games are not all present",
            "trigger_episodes_by_hh_side_game": per_hh, "hh_side_games": len(hh),
            "met": len(hh) != HH_SIDE_GAMES or any(n < STOP_MIN_EPISODES_PER_HH_SIDE_GAME for n in per_hh.values())},
        "h0_readings": {
            "trigger_episodes_by_h0_side_game": per_h0, "h0_side_games": len(h0),
            "each_side_game_reading_met": len(h0) != H0_SIDE_GAMES or any(n < 1 for n in per_h0.values()),
            "average_reading_met": sum(per_h0.values()) < len(h0),
            "use": "reported only; not part of the disposition"},
        "legality_gate": {
            "rule": "met when any of the four HH side-games has no distinct legal-tier episode",
            "legal_episodes_by_hh_side_game": legal_hh,
            "met": len(hh) != HH_SIDE_GAMES or any(n < 1 for n in legal_hh.values())},
    }
    return out


def disposition(fidelity_ok: bool, integrity_ok: bool, unexplained: int, stop: Mapping[str, Any],
                inter: Mapping[str, Any]) -> Dict[str, Any]:
    """Section 20, first match: INVALID; INADEQUATE_OPPORTUNITY (the opportunity stop); LEGALITY_UNRESOLVED (the
    legality gate); INTERACTION_NOT_READY (any interaction criterion); READY_FOR_MECHANISM_PROPOSAL."""
    if not fidelity_ok or not integrity_ok or unexplained != 0:
        outcome = DISPOSITIONS[0]
    elif stop["opportunity_stop"]["met"]:
        outcome = DISPOSITIONS[1]
    elif stop["legality_gate"]["met"]:
        outcome = DISPOSITIONS[2]
    elif any(inter["met"].values()):
        outcome = DISPOSITIONS[3]
    else:
        outcome = DISPOSITIONS[4]
    return {"disposition": outcome, "fidelity_ok": bool(fidelity_ok), "integrity_ok": bool(integrity_ok),
            "unexplained_action_differences": unexplained,
            "opportunity_stop_met": bool(stop["opportunity_stop"]["met"]),
            "legality_gate_met": bool(stop["legality_gate"]["met"]),
            "interaction_criteria_met": [c for c in INTERACTION_CRITERIA if inter["met"][c]]}


def readiness_risks(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    """Section 19's risk classes, reported whatever the disposition (independent of the opportunity stop)."""
    out: Dict[str, Any] = {}
    for name, part in (("HH", [a for a in analyses if a.side.population == "HH"]),
                       ("H0", [a for a in analyses if a.side.population == "H0"])):
        stationary = trig = legal = 0
        reasons: collections.Counter = collections.Counter()
        for a in part:
            for objs in a.checks.values():
                for c in objs:
                    lv = [x for _, x in c.centre_units]
                    if sum(1 for x in lv if passes_through(x, ts.IDLE_LEVELS[0])) < 2:
                        continue
                    stationary += 1
                    if c.legal_tier:
                        legal += 1
                        continue
                    if not c.trigger:
                        reasons["fewer than two idle units" if len(c.idle) < 2 else "no passable neighbour"] += 1
                        if len(c.idle) < 2:
                            for x in lv:
                                if x != "idle" and passes_through(x, ts.IDLE_LEVELS[0]):
                                    reasons[f"stationary unit failing {x}"] += 1
                    else:
                        trig += 1
                        reasons["trigger without a dispersed unit"] += 1
        firsts = [a for a in part if a.shadow.first_divergence is not None]
        out[name] = {
            "R1_stationary_stacks_without_a_dispersal": {"objective_decisions_two_or_more_stationary": stationary,
                                                        "with_a_dispersal": legal, "without": stationary - legal,
                                                        "reasons": dict(sorted(reasons.items()))},
            "R2_holder_selection": "deterministic by construction; holder departures under baseline-v2 are criterion I2",
            "R3_same_step_conflicts_unit_decisions": sum(a.census["batch_outcomes_unit_decisions"].get("no_destination_left", 0)
                                                         for a in part),
            "R4_onward_moves": "criterion I1 (claimants) and the first-owner counts",
            "R5_adjacency_denial": "unresolved offline by construction: the published capture rule has not been tested "
                                   "with a held objective whose centre is empty while own units stand next to it",
            "R6_first_divergences": {"side_games_with_one": len(firsts),
                                     "prefix_supported": sum(1 for a in firsts if prefix_supported(a.side, a.shadow.first_divergence))},
        }
    return out


# ------------------------------------------------------------------------------------------------
# public aggregates

def dist(values: Iterable[Optional[float]]) -> Dict[str, Any]:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def tally(values: Iterable[Any]) -> List[List[Any]]:
    counts = collections.Counter(values)
    return [[v, counts[v]] for v in sorted(counts, key=lambda v: (str(type(v)), str(v)))]


def unit_class(side: Side, k: int, unit: Any) -> str:
    u = side.frames[k].own.get(unit)
    return sc.unit_class(u) if u else "unknown"


def public_episode(a: SideAnalysis, row: Mapping[str, Any], ordinal: int, counted: bool) -> Dict[str, Any]:
    """One sanitised legal-episode row (no unit id, hex or route)."""
    names = objective_labels(a.side.values)
    c: ts.ObjectiveCheck = row["check"]
    k = row["start_k"]
    f = a.side.frames[k]
    counts = ts.ground_counts(f.own)
    disp = dict(c.dispersed)
    after = collections.Counter(counts)
    for u, n in disp.items():
        after[n] += 1
        after[c.objective] -= 1
    units = []
    for rec in row["onward"]["units"]:
        out = {key: value for key, value in rec.items() if key not in ("unit", "dispersal_destination", "onward_destination")}
        out["unit_class"] = unit_class(a.side, k, rec["unit"])
        out["destination_own_ground_before"] = counts.get(rec["dispersal_destination"], 0)
        out["destination_own_ground_after"] = after[rec["dispersal_destination"]]
        if rec.get("onward_destination_kind") in (DEST_HELD, DEST_UNHELD):
            out["onward_destination_label"] = names.get(rec["onward_destination"], "unlabelled objective")
        units.append(out)
    return {"population": a.side.population, "side_game": a.side.label, "scenario_side": a.side.scenario_side,
            "episode_ordinal": ordinal, "objective_label": names.get(c.objective, "unlabelled objective"),
            "start_step": row["start_step"], "listed_decisions": row["decisions"],
            "idle_centre_units": len(c.idle), "centre_own_ground": len(c.centre_units),
            "centre_own_ground_after": after[c.objective],
            "holder_class": unit_class(a.side, k, c.holder),
            "outcomes": tally(x.outcome for x in c.units),
            "neighbour_own_ground": sorted(n for _, n, _ in c.neighbour_counts),
            "first_divergence": row["first_divergence"], "post_divergence": row["post_divergence"],
            "prefix_supported": row["prefix_supported"], "counted_as_distinct": counted,
            "hold_to_end": row["onward"]["hold_to_end"], "hold_release_steps": row["onward"]["hold_release_steps"],
            "holder_ordered_off_while_held": row["onward"]["holder_ordered_off_while_held"],
            "holder_ordered_off_steps": row["onward"]["holder_ordered_off_steps"],
            "dispersed": units, "damage": row["damage"]}


def certificate(a: SideAnalysis) -> Optional[Dict[str, Any]]:
    """The public first-divergence certificate of one side-game (section 17)."""
    s = a.shadow
    first = s.first_divergence
    if first is None:
        return None
    f = a.side.frames[first]
    base, cand = [dict(x) for x in f.actions], [dict(x) for x in s.candidate[first]]
    added = [dict(x) for x in s.added.get(first, ())]
    objs = [c for c in s.checks.get(first, ()) if c.legal_tier]
    names = objective_labels(a.side.values)
    counts = ts.ground_counts(f.own)
    disp = {u: n for c in objs for u, n in c.dispersed}
    return {"side_game": a.side.label, "population": a.side.population, "decision": first, "step": f.cur_step,
            "decisions_before_identical": first, "prefix_supported": prefix_supported(a.side, first),
            "on_policy_baseline_v2_witness": a.side.population == "HH" or prefix_supported(a.side, first),
            "objectives": [names.get(c.objective, "unlabelled objective") for c in objs],
            "objective_held": all(f.flags.get(c.objective) == a.side.faction for c in objs),
            "idle_centre_units": [len(c.idle) for c in objs],
            "holder_retained": all(c.holder is not None and c.holder not in disp and f.own[c.holder]["cur_hex"] == c.objective
                                   for c in objs),
            "dispersed_units": len(disp),
            "destinations_empty_before": sum(1 for n in disp.values() if counts.get(n, 0) == 0),
            "destinations_distinct": len(set(disp.values())),
            "only_registered_moves_added": cand == base + added and all(
                x.get("type") == 1 and len(x.get("move_path") or ()) == 1 for x in added),
            "baseline_actions_preserved": cand[:len(base)] == base,
            "no_baseline_action_for_dispersed_units": not any(x.get("obj_id") in disp for x in base)}


def side_summary(a: SideAnalysis) -> Dict[str, Any]:
    s = a.shadow
    first = s.first_divergence
    trig, legal = a.trigger_episodes, a.legal_episodes
    return {
        "side_game": a.side.label, "population": a.side.population, "scenario_side": a.side.scenario_side,
        "decisions": len(a.side.frames), "play_decisions": sum(1 for f in a.side.frames if f.stage == 2),
        "census": a.census,
        "trigger_episodes": len(trig), "legal_episodes": len(legal),
        "trigger_repeated_listings": sum(r["decisions"] - 1 for r in trig),
        "legal_repeated_listings": sum(r["decisions"] - 1 for r in legal),
        "trigger_objectives": len({r["objective"] for r in trig}),
        "legal_objectives": len({r["objective"] for r in legal}),
        "legal_distinct_groups": len({(r["objective"], r["idle"]) for r in legal}),
        "legal_dispersed_units_distinct": len({u for r in legal for u, _ in r["check"].dispersed}),
        "first_divergence": None if first is None else {
            "decision": first, "step": a.side.frames[first].cur_step, "prefix_supported": prefix_supported(a.side, first)},
        "replay_withheld_actions": sum(len(v) for v in s.withheld.values()),
        "replay_added_actions": sum(len(v) for v in s.added.values()),
        "replay_release_reasons": tally(e.reason for _, e in s.events if e.kind == "release"),
        "unexplained_action_differences": len(s.unexplained),
        "integrity": dict(sorted(a.integrity.items())),
    }


def pooled(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    legal = [(a, r) for a in analyses for r in a.legal_episodes]
    trig = [(a, r) for a in analyses for r in a.trigger_episodes]
    units = [(a, r, u) for a, r in legal for u in r["onward"]["units"]]
    census_sum: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for a in analyses:
        for key, block in a.census.items():
            if isinstance(block, dict):
                census_sum[key].update(block)
    dl = distinct(analyses, "legal")
    dt = distinct(analyses, "trigger")
    return {
        "side_games": len(analyses),
        "census": {k: dict(sorted(v.items())) for k, v in sorted(census_sum.items())},
        "trigger_episodes": len(trig), "trigger_episodes_distinct": len(dt),
        "legal_episodes": len(legal), "legal_episodes_distinct": len(dl),
        "side_games_with_a_trigger_episode": len({a.side.label for a, _ in trig}),
        "side_games_with_a_legal_episode": len({a.side.label for a, _ in legal}),
        "scenario_sides_with_a_trigger_episode": len({a.side.scenario_side for a, _ in trig}),
        "scenario_sides_with_a_legal_episode": len({a.side.scenario_side for a, _ in legal}),
        "objectives_with_a_legal_episode": len({(a.side.game, a.side.faction, r["objective"]) for a, r in legal}),
        "dispersed_units_distinct": len({(a.side.game, a.side.faction, u["unit"]) for a, r, u in units}),
        "repeated_listings_excluded": {"trigger": sum(r["decisions"] - 1 for _, r in trig),
                                       "legal": sum(r["decisions"] - 1 for _, r in legal)},
        "legal_episode_lengths": dist(r["decisions"] for _, r in legal),
        "onward": {
            "dispersed_units": len(units),
            "with_an_onward_move": sum(1 for *_, u in units if u["onward_move"]),
            "claimants": sum(1 for *_, u in units if u.get("claimant")),
            "first_owners": sum(1 for *_, u in units if u.get("first_owner")),
            "with_other_own_first_owners": sum(1 for *_, u in units if u.get("other_own_first_owners")),
            "onward_destination_kinds": tally(u["onward_destination_kind"] for *_, u in units if u["onward_move"]),
            "steps_to_onward_move": dist(u.get("steps_to_onward_move") for *_, u in units),
            "suppressed_move_decisions": dist(u["suppressed_move_decisions"] for *_, u in units),
            "later_lost": sum(1 for *_, u in units if u["later_lost"]),
            "episodes_hold_to_end": sum(1 for _, r in legal if r["onward"]["hold_to_end"]),
            "episodes_holder_ordered_off_while_held": sum(1 for _, r in legal if r["onward"]["holder_ordered_off_while_held"]),
        },
        "damage": {k: sum(r["damage"][k] for _, r in legal) for k in sorted(legal[0][1]["damage"])} if legal else {},
    }


def damage_summary(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in ("H0", "HH"):
        rows = [r for a in analyses if a.side.population == name for r in a.damage]
        stacked = [r for r in rows if r["stacked"]]
        out[name] = {"stationary_on_objective_ground_events": len(rows), "stacked": len(stacked),
                     "alone": len(rows) - len(stacked),
                     "objective_held": sum(1 for r in rows if r["held"]),
                     "stacked_and_held": sum(1 for r in stacked if r["held"]),
                     "attacker_seen_at_event": sum(1 for r in rows if r["attacker_seen_at_event"]),
                     "attacker_seen_before": sum(1 for r in rows if r["attacker_seen_before"]),
                     "victim_lost": sum(1 for r in rows if r["victim_lost"]),
                     "stacked_held_with_an_earlier_trigger": sum(1 for r in stacked if r["held"] and r["earlier_trigger"]),
                     "stacked_held_with_an_earlier_legal_dispersal": sum(1 for r in stacked if r["held"] and r["earlier_legal"]),
                     "stacked_held_earlier_legal_at_the_first_divergence": sum(
                         1 for r in stacked if r["held"] and r["earlier_legal_at_first_divergence"]),
                     "steps_since_latest_legal": dist(r["steps_since_latest_legal"] for r in stacked if r["held"])}
    return out


def public_damage_row(a: SideAnalysis, r: Mapping[str, Any]) -> Dict[str, Any]:
    names = objective_labels(a.side.values)
    return {"population": a.side.population, "side_game": a.side.label, "step": r["step"],
            "objective_label": names.get(r["objective"], "unlabelled objective") if r["objective"] is not None else None,
            "victim_class": r["victim_class"], "stacked": r["stacked"], "held": r["held"],
            "attacker_seen_at_event": r["attacker_seen_at_event"], "attacker_seen_before": r["attacker_seen_before"],
            "victim_lost": r["victim_lost"], "earlier_trigger": r["earlier_trigger"], "earlier_legal": r["earlier_legal"],
            "steps_since_latest_legal": r["steps_since_latest_legal"],
            "earlier_legal_at_first_divergence": r["earlier_legal_at_first_divergence"]}


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
    words of strings, numeric leaves (aggregates, steps and counts by construction) masked."""
    from .s12_screen import privacy_problems
    return privacy_problems(data) + privacy_problems(mask_numbers(data), sorted({str(v) for v in private_values}))


def digit_words(data: Any, allowed: Iterable[str] = ()) -> List[str]:
    """Every word made only of digits in a key or string of ``data`` except the ``allowed`` ones (section 21: public
    labels carry none but the registered scenario identifiers)."""
    keep = set(allowed)
    out: List[str] = []

    def words(text: str) -> None:
        out.extend(w for w in text.split() if w.isdigit() and w not in keep)

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for k, v in node.items():
                words(str(k))
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            words(node)

    walk(data)
    return out
