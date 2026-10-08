"""Sprint 26 T6-S stacked-column stagger offline shadow (``docs/SPRINT26_T6S_SHADOW.md``).

Pure functions over Sprint 18 census frames (``evaluation/s18_census.py``). Nothing here reaches a policy or an engine.

A side's frames are its decisions in order (``frame.k`` equals the position); ``recorded`` holds, per frame, the action
list the historical seat submitted (H0: ``baseline-v0``; HH: ``baseline-v2``), and ``frame.actions`` the ``baseline-v2``
list (H0: reconstructed on the recorded observation; HH: the recorded seat, equal to the reconstruction at every
decision by Sprint 18's check). ``travel`` is the frozen free-flow relation over the side's cost graph
(``experiments.t6s_stagger_shadow.router_travel``). Definitions are the registration's (sections 5 to 18); every
docstring says which section it implements.

Private rows (unit ids, hexes, routes) stay in the returned objects; the ``public_*`` functions emit aggregates and
labels only.
"""

from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..experiments import t6s_stagger_shadow as ts
from . import s18_census as sc
from .t7_candidates import weapon_range
from .t7_visibility import hex_distance

STUDY_ID = "s26-t6s-shadow"
#: Follow-up window (steps) for the historical descriptives after an episode start (Sprint 18's window).
FOLLOW_UP = 300
#: Damage windows (steps) after an episode start (Sprint 19's windows).
WINDOWS = (75, 150, 300)
#: Registered stop thresholds (section 17).
STOP_A_MIN_EPISODES = 10
STOP_B_MIN_SCENARIO_SIDES = 4
HH_SIDE_GAMES = 4
H0_SIDE_GAMES = 16
DISPOSITIONS = ("T6_S_INVALID", "T6_S_INADEQUATE_OPPORTUNITY", "T6_S_ONWARD_CAPTURE_RISK", "T6_S_OFFLINE_PASS")
#: Destination kinds of a member's MOVE at the episode start (section 15).
DEST_HELD, DEST_UNHELD, DEST_NOT_OBJECTIVE = "objective held", "objective not held", "not an objective"
#: Sprint 25 collective-departure categories (section 16), first match.
S25_CATEGORIES = ("ordered at several decisions", "ordered at one decision from different hexes",
                  "same hex, different first route hexes", "no qualifying visible threat",
                  "baseline-v2 did not emit the same MOVEs", "frozen trigger fails",
                  "trigger holds at a valid first divergence", "trigger holds after a divergence or without prefix support")


# ------------------------------------------------------------------------------------------------
# side data

@dataclass
class Side:
    """One analysed side of one game: population, labels, frames, recorded and baseline-v2 lists, events, the
    objective values and the frozen free-flow relation."""

    population: str
    label: str
    game: str
    scenario: str
    faction: int
    frames: List[sc.Frame]
    recorded: List[List[Mapping[str, Any]]]
    events: List[Tuple[int, Mapping[str, Any]]]
    travel: ts.Travel
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


def ground_hex(u: Optional[Mapping[str, Any]]) -> Optional[int]:
    return ts.hex_int(u.get("cur_hex")) if ts.is_ground(u) else None


def first_ownership(frames: Sequence[sc.Frame], faction: int, coord: Any) -> Optional[int]:
    """The decision of the side's first-ever play-stage ownership of ``coord`` (its flag reads the side's colour)."""
    for f in frames:
        if f.stage == 2 and f.flags.get(coord) == faction:
            return f.k
    return None


def in_envelope(unit: Mapping[str, Any], enemies: Iterable[Mapping[str, Any]]) -> bool:
    """Whether a visible enemy's published direct-fire range against the unit's type covers the unit's hex."""
    h = sc.as_int(unit.get("cur_hex"))
    if h is None:
        return False
    for e in enemies:
        reach = weapon_range(e.get("carry_weapon_ids") or (), unit.get("type"))
        if reach is not None and sc.as_int(e.get("cur_hex")) is not None and hex_distance(e["cur_hex"], h) <= reach:
            return True
    return False


# ------------------------------------------------------------------------------------------------
# section 13 (registration): the shadow over a side and the independent action-level check

@dataclass
class ShadowRun:
    candidate: List[Tuple[Mapping[str, Any], ...]]
    withheld: Dict[int, Tuple[int, ...]]
    events: List[Tuple[int, ts.StaggerEvent]]
    checks: List[Tuple[int, int, Any, ts.MoverCheck]]
    groups: List[Tuple[int, int, int, Tuple[Any, ...], str]]
    first_divergence: Optional[int]
    unexplained: List[Dict[str, Any]]
    episodes: List[Dict[str, Any]]


class IndependentCheck:
    """Section 13: an independent restatement, from the frames' raw fields and Sprint 18's own threat predicate, of
    what every action-level difference between the candidate and ``baseline-v2`` must satisfy.

    The candidate list must be ``baseline-v2``'s with some actions removed and the rest in order. Each removed action
    must be a MOVE of an own ground unit (type 1 or 2) with a readable hex that is not moving (empty observed route, no
    positive speed). A unit's first removal opens a **run** at its hex: another own ground unit on the same hex must
    keep a MOVE with the same route first hex at that decision, one of those same-hex, same-first-hex MOVEs must be
    threat-exposed by ``s18_census.threat_exposed``, and the removed MOVE's free-flow times must be readable. Later
    removals of the unit belong to the run while the unit stays on that hex and within ``(n - 1) * (2 * t + 11)`` steps
    of the run's start (``n`` the same-hex, same-first-hex MOVEs at the start, ``t`` the largest readable first-hex
    free-flow time among them). A run ends when the unit is observed elsewhere or absent,
    or the bound passes; a unit cannot open a second run on a hex before it has been observed elsewhere."""

    def __init__(self, travel: ts.Travel) -> None:
        self.travel = travel
        self.runs: Dict[Any, Dict[str, int]] = {}
        self.closed: Dict[Any, int] = {}

    def step(self, frame: sc.Frame, candidate: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        base = [dict(a) for a in frame.actions]
        cand = [dict(a) for a in candidate]
        i, removed, kept = 0, [], []
        for a in base:
            if i < len(cand) and cand[i] == a:
                kept.append(a)
                i += 1
            else:
                removed.append(a)
        if i != len(cand):
            out.append({"k": frame.k, "problem": "the candidate adds or reorders actions"})
        for unit_id in list(self.runs):
            h = sc.as_int((frame.own.get(unit_id) or {}).get("cur_hex"))
            run = self.runs[unit_id]
            if h is None and unit_id in frame.own:
                continue
            if h != run["origin"] or frame.cur_step - run["start"] > run["bound"]:
                self.closed[unit_id] = run["origin"]
                del self.runs[unit_id]
        for unit_id in list(self.closed):
            h = sc.as_int((frame.own.get(unit_id) or {}).get("cur_hex"))
            if h is not None and h != self.closed[unit_id]:
                del self.closed[unit_id]
        for a in removed:
            problem = self.explain(frame, a, kept, base)
            if problem:
                out.append({"k": frame.k, "problem": problem, "action": a})
        return out

    def explain(self, frame: sc.Frame, action: Mapping[str, Any], kept: Sequence[Mapping[str, Any]],
                base: Sequence[Mapping[str, Any]]) -> Optional[str]:
        if action.get("type") != 1:
            return "a removed action is not a MOVE"
        unit_id = action.get("obj_id")
        unit = frame.own.get(unit_id)
        if unit is None or unit.get("type") not in (1, 2) or sc.as_int(unit.get("cur_hex")) is None:
            return "a removed MOVE is not of an own ground unit with a readable hex"
        if unit.get("move_path") or (sc.is_number(unit.get("speed")) and unit["speed"] > 0):
            return "a removed MOVE belongs to a unit already moving"
        here = unit["cur_hex"]
        route = list(action.get("move_path") or ())
        run = self.runs.get(unit_id)
        if run is not None:
            return None if here == run["origin"] and frame.cur_step - run["start"] <= run["bound"] else \
                "a repeated removal outside its run"
        if self.closed.get(unit_id) == here:
            return "a second run on a hex the unit has not left"
        if not route:
            return "a removed MOVE has no route"

        def same(a: Mapping[str, Any]) -> bool:
            u = frame.own.get(a.get("obj_id"))
            r = list(a.get("move_path") or ())
            return (a.get("type") == 1 and u is not None and u.get("type") in (1, 2) and u.get("cur_hex") == here
                    and bool(r) and r[0] == route[0])

        if not any(same(a) and a.get("obj_id") != unit_id for a in kept):
            return "no co-located MOVE with the same first hex is kept"
        group = [a for a in base if same(a)]
        if not any(sc.threat_exposed(frame, a) for a in group):
            return "no MOVE of the group is threat-exposed"
        if self.travel(unit, route) is None:
            return "the removed MOVE's free-flow time is unreadable"
        times = [timing[0][0] for timing in (self.travel(frame.own[a["obj_id"]], list(a["move_path"])) for a in group)
                 if timing is not None]
        self.runs[unit_id] = {"origin": here, "start": frame.cur_step,
                              "bound": (len(group) - 1) * (2 * max(times) + 11)}
        return None


def run_shadow(side: Side) -> ShadowRun:
    """The frozen shadow on every decision of the side from an empty memory (the candidate's lists), the withheld
    indices, events, checks and group outcomes, the first divergence, the independent comparison and the assembled
    episode rows (private)."""
    memory = ts.StaggerMemory()
    checker = IndependentCheck(side.travel)
    candidate, withheld, events, checks, groups, unexplained = [], {}, [], [], [], []
    rows: Dict[int, Dict[str, Any]] = {}
    for f in side.frames:
        result = ts.decide(f.cur_step, f.stage, f.own, f.enemies.values(), f.valid, f.actions, memory, side.travel)
        memory = result.memory
        candidate.append(result.actions)
        if result.withheld:
            withheld[f.k] = result.withheld
        events.extend((f.k, e) for e in result.events)
        checks.extend((f.k, i, u, c) for i, u, c in result.checks)
        groups.extend((f.k, o, h, units, outcome) for o, h, units, outcome in result.groups)
        if f.stage == 2:
            unexplained.extend(checker.step(f, result.actions))
        members = {c.member.unit: c.member for _, _, c in result.checks if c.eligible}
        for e in result.events:
            if e.kind == "start":
                ep = e.episode
                rows[ep.eid] = {"eid": ep.eid, "start_k": f.k, "start_step": f.cur_step, "origin": ep.origin,
                                "first_hex": ep.first_hex, "chain": list(ep.chain), "hex_times": list(ep.hex_times),
                                "members": {u: members[u] for u in ep.chain}, "releases": {}, "queue": {},
                                "repeats": 0, "end_k": None, "end_step": None, "end": None}
            elif e.kind == "repeat":
                rows[e.eid]["repeats"] += 1
            elif e.kind == "release":
                rows[e.eid]["releases"][e.unit] = {"k": f.k, "step": f.cur_step, "reason": e.reason, "moved": e.moved}
            elif e.kind == "queue":
                rows[e.eid]["queue"][e.unit] = {"k": f.k, "step": f.cur_step, "reason": e.reason}
            elif e.kind == "complete":
                rows[e.eid].update(end_k=f.k, end_step=f.cur_step, end="complete")
    if side.frames:
        last = side.frames[-1]
        for row in rows.values():
            if row["end"] is None:
                row.update(end_k=last.k, end_step=last.cur_step, end=ts.OPEN_AT_END)
    first = min(withheld) if withheld else None
    return ShadowRun(candidate, withheld, events, checks, groups, first, unexplained,
                     [rows[k] for k in sorted(rows)])


def prefix_supported(side: Side, upto: int) -> bool:
    """H0: the recorded ``baseline-v0`` actions equal ``baseline-v2``'s at every decision before ``upto`` (Sprint 23's
    evidence boundary); HH: the recorded seat equals ``baseline-v2`` there."""
    return all([dict(a) for a in side.recorded[j]] == [dict(a) for a in side.frames[j].actions] for j in range(upto))


# ------------------------------------------------------------------------------------------------
# sections 12, 13 and 15: per-episode facts

def destination_kind(frame: sc.Frame, faction: int, dest: Any) -> str:
    if dest in frame.flags:
        return DEST_HELD if frame.flags[dest] == faction else DEST_UNHELD
    return DEST_NOT_OBJECTIVE


def shared_prefix(routes: Sequence[Sequence[Any]]) -> int:
    n = 0
    for column in zip(*routes):
        if len(set(column)) != 1:
            break
        n += 1
    return n


def follower_onward(side: Side, row: Mapping[str, Any], unit: Any, position: int,
                    lost: Mapping[Any, int]) -> Dict[str, Any]:
    """Section 15 for one withheld follower, from the historical trajectory (labels for analysis only). ``lost`` is
    ``s18_census.lost_units`` of the side."""
    frames, faction = side.frames, side.faction
    k = row["start_k"]
    f = frames[k]
    m = row["members"][unit]
    dest = m.route[-1]
    kind = destination_kind(f, faction, dest)
    first_k = first_ownership(frames, faction, dest) if kind != DEST_NOT_OBJECTIVE else None
    after = first_k is not None and first_k > k
    participants = sorted((o for o, u in frames[first_k].own.items() if ts.is_ground(u) and u.get("cur_hex") == dest),
                          key=str) if after else []
    wait = sum(row["hex_times"][:position])
    left = (f.max_step - f.cur_step) if sc.is_number(f.max_step) and sc.is_number(f.cur_step) else None
    return {
        "destination_kind": kind, "destination": dest,
        "first_owned_after_start": after,
        "first_owner": after and unit in participants,
        "other_own_first_owners": after and any(p != unit for p in participants),
        "steps_start_to_first_ownership": (frames[first_k].cur_step - f.cur_step) if after else None,
        "first_owned_before_start": first_k is not None and not after,
        "never_owned": kind != DEST_NOT_OBJECTIVE and first_k is None,
        "projected_wait": wait, "free_flow_arrival": m.arrival,
        "pushed_past_the_end": left is not None and m.arrival <= left < m.arrival + wait,
        "unreachable_free_flow": left is not None and m.arrival > left,
        "later_lost": unit in lost and lost[unit] > k,
        "steps_start_to_loss": (frames[lost[unit]].cur_step - f.cur_step)
        if unit in lost and lost[unit] > k and lost[unit] < len(frames) else None,
    }


def damage_steps(side: Side) -> Dict[Any, List[Tuple[int, int]]]:
    """Per own unit, the (decision, step) of each damage event on it (Sprint 18's events: positive damage)."""
    out: Dict[Any, List[Tuple[int, int]]] = collections.defaultdict(list)
    for k, r in side.events:
        if r.get("target_color") != side.faction:
            continue
        frame = side.frames[min(k, len(side.frames) - 1)]
        step = r.get("cur_step") if sc.is_number(r.get("cur_step")) else frame.cur_step
        out[r.get("target_obj_id")].append((k, step))
    return out


def follow_up(side: Side, row: Mapping[str, Any]) -> Dict[str, Any]:
    """Section 13 for one episode on the recorded trajectory: whether each member's recorded actions at the start
    contain its ``baseline-v2`` MOVE (followed on the record), and, for the followed members, within ``FOLLOW_UP``
    steps: co-location while moving at hexes other than the start hex, moving stacked member unit-decisions inside
    applicable envelopes, the leader's recorded departure from the start hex."""
    frames = side.frames
    k = row["start_k"]
    f = frames[k]
    recorded = [dict(a) for a in side.recorded[k]]
    followed = [u for u in row["chain"] if any(a.get("type") == 1 and a.get("obj_id") == u
                                               and tuple(a.get("move_path") or ()) == row["members"][u].route
                                               for a in recorded)]
    out: Dict[str, Any] = {"members_followed_on_record": len(followed), "all_followed": len(followed) == len(row["chain"])}
    shared_hexes: Set[Any] = set()
    together = stacked_inside = 0
    leader = row["chain"][0]
    leader_left = None
    for g in frames[k + 1:]:
        if g.cur_step - f.cur_step > FOLLOW_UP:
            break
        if leader_left is None and leader in followed:
            h = sc.as_int((g.own.get(leader) or {}).get("cur_hex"))
            if leader not in g.own or (h is not None and h != row["origin"]):
                leader_left = g.cur_step - f.cur_step
        states = [(u, g.own[u]) for u in followed if u in g.own and sc.moving(g.own[u])]
        here = collections.Counter(s.get("cur_hex") for _, s in states)
        shared = {h for h, n in here.items() if n >= 2 and h != row["origin"] and h is not None}
        if shared:
            together += 1
            shared_hexes |= shared
        stacked_inside += sum(1 for _, s in states if s.get("stack") and in_envelope(s, g.enemies.values()))
    out.update({"co_located_moving_beyond_start": bool(shared_hexes), "co_located_hexes_beyond_start": len(shared_hexes),
                "co_located_moving_decisions": together, "stacked_moving_inside_envelope_unit_decisions": stacked_inside,
                "leader_recorded_departure_steps": leader_left})
    return out


def episode_damage(side: Side, row: Mapping[str, Any], hits: Mapping[Any, List[Tuple[int, int]]]) -> Dict[str, Any]:
    start = row["start_step"]
    out: Dict[str, Any] = {}
    for w in WINDOWS:
        out[f"members_damaged_within_{w}"] = sum(1 for u in row["chain"] if any(start <= s <= start + w for _, s in hits.get(u, ())))
        out[f"followers_damaged_within_{w}"] = sum(1 for u in row["chain"][1:]
                                                   if any(start <= s <= start + w for _, s in hits.get(u, ())))
    return out


def episode_facts(side: Side, row: Dict[str, Any], first_divergence: Optional[int],
                  hits: Mapping[Any, List[Tuple[int, int]]], lost: Mapping[Any, int]) -> None:
    """Sections 12 to 15 for one episode, in place."""
    f = side.frames[row["start_k"]]
    chain = row["chain"]
    units = [f.own[u] for u in chain]
    routes = [row["members"][u].route for u in chain]
    row["group_size"] = len(chain)
    row["classes"] = [sc.unit_class(u) for u in units]
    row["basic_speeds"] = [u.get("basic_speed") for u in units]
    row["different_hex_times"] = len(set(row["hex_times"])) > 1
    row["members_exposed"] = sum(1 for u in chain if row["members"][u].exposed)
    row["members_stacked_at_start"] = sum(1 for u in units if u.get("stack"))
    row["own_ground_on_start_hex"] = sum(1 for u in f.own.values() if ground_hex(u) == row["origin"])
    row["carriers_with_passengers"] = sum(1 for u in chain if (getattr(f, "carrying", {}) or {}).get(u))
    row["shared_route_prefix"] = shared_prefix(routes)
    row["route_lengths"] = [len(r) for r in routes]
    row["destination_kinds"] = [destination_kind(f, side.faction, r[-1]) for r in routes]
    row["same_destination"] = len({r[-1] for r in routes}) == 1
    row["first_divergence"] = first_divergence is not None and row["start_k"] == first_divergence
    row["post_divergence"] = first_divergence is not None and row["start_k"] > first_divergence
    row["prefix_supported"] = prefix_supported(side, row["start_k"]) if row["first_divergence"] else None
    row["projected_waits"] = [sum(row["hex_times"][:i]) for i in range(1, len(chain))]
    row["onward"] = {u: follower_onward(side, row, u, i, lost) for i, u in enumerate(chain) if i > 0}
    row["first_owner_risk"] = any(o["first_owner"] for o in row["onward"].values())
    row["follow_up"] = follow_up(side, row)
    row["damage"] = episode_damage(side, row, hits)
    row["timeout"] = any(r["reason"] == "timeout" for r in row["releases"].values())


# ------------------------------------------------------------------------------------------------
# section 12: the decision-level census (stateless; independent of the shadow's eligibility)

def census(side: Side) -> Dict[str, Any]:
    """Decision-level counts over play decisions: ``baseline-v2`` MOVEs, ground MOVEs, same-hex co-departure groups,
    groups sharing a first route hex and those with a threat-exposed member (Sprint 18's predicate). A group listed
    again at a later decision is counted again (these are not episodes)."""
    out = collections.Counter()
    for f in side.frames:
        if f.stage != 2:
            continue
        by_hex: Dict[Any, List[Mapping[str, Any]]] = collections.defaultdict(list)
        for a in f.actions:
            if a.get("type") != 1:
                continue
            out["move_orders"] += 1
            u = f.own.get(a.get("obj_id"))
            if not ts.is_ground(u) or sc.as_int(u.get("cur_hex")) is None:
                continue
            out["ground_move_orders"] += 1
            by_hex[u["cur_hex"]].append(a)
        for here, moves in by_hex.items():
            if len(moves) < 2:
                continue
            out["same_hex_groups"] += 1
            out["same_hex_group_moves"] += len(moves)
            firsts = collections.Counter((list(a.get("move_path") or ()) or [None])[0] for a in moves)
            if len(firsts) == 1 and None not in firsts:
                out["same_hex_groups_all_one_first_hex"] += 1
            for first, n in firsts.items():
                if first is None or n < 2:
                    continue
                out["shared_first_hex_groups"] += 1
                sub = [a for a in moves if (list(a.get("move_path") or ()) or [None])[0] == first]
                if any(sc.threat_exposed(f, a) for a in sub):
                    out["shared_first_hex_groups_threat_exposed"] += 1
    return dict(sorted(out.items()))


def exposure(side: Side) -> Dict[str, Any]:
    """Section 13: moving own ground unit-decisions (``s18_census.moving``), stacked (``stack`` truthy) and not, and
    inside a visible enemy's applicable envelope (published range against the unit's type covers its hex)."""
    out = collections.Counter()
    for f in side.frames:
        if f.stage != 2:
            continue
        for u in f.own.values():
            if not ts.is_ground(u) or sc.as_int(u.get("cur_hex")) is None or not sc.moving(u):
                continue
            stacked = bool(u.get("stack"))
            inside = in_envelope(u, f.enemies.values())
            out["moving_unit_decisions"] += 1
            out["moving_stacked_unit_decisions" if stacked else "moving_alone_unit_decisions"] += 1
            if inside:
                out["moving_stacked_inside_envelope" if stacked else "moving_alone_inside_envelope"] += 1
    return dict(sorted(out.items()))


# ------------------------------------------------------------------------------------------------
# per side

@dataclass
class SideAnalysis:
    side: Side
    shadow: ShadowRun
    census: Dict[str, Any]
    exposure: Dict[str, Any]
    integrity: Dict[str, bool]


def analyse_side(side: Side) -> SideAnalysis:
    frames = side.frames
    integrity = {"frame positions equal decision indices": all(f.k == i for i, f in enumerate(frames)),
                 "one recorded list per decision": len(side.recorded) == len(frames)}
    shadow = run_shadow(side)
    hits = damage_steps(side)
    lost = sc.lost_units(frames)
    for row in shadow.episodes:
        episode_facts(side, row, shadow.first_divergence, hits, lost)
    first = shadow.first_divergence
    pre = True
    if first is not None:
        for j in range(first):
            pre &= list(shadow.candidate[j]) == [dict(a) for a in frames[j].actions]
        pre &= not any(o == "triggered" for (k, *_, o) in shadow.groups if k < first)
        pre &= any(r["start_k"] == first for r in shadow.episodes)
    integrity["candidate equals baseline-v2 before the first divergence"] = pre
    integrity["withheld actions are MOVEs"] = all(frames[k].actions[i].get("type") == ts.MOVE
                                                  for k, idx in shadow.withheld.items() for i in idx)
    same = True
    for f in frames:
        if f.stage != 2:
            continue
        for a in f.actions:
            if a.get("type") == 1:
                same &= ts.threat_exposed(f.own.get(a.get("obj_id")), a.get("move_path") or (),
                                          f.enemies.values()) == sc.threat_exposed(f, a)
    integrity["shadow exposure equals Sprint 18's predicate on every MOVE"] = same
    integrity["every episode keeps its leader's MOVE and withholds its followers"] = all(
        any(x.get("obj_id") == r["chain"][0] and x.get("type") == 1 for x in shadow.candidate[r["start_k"]])
        and all(not any(x.get("obj_id") == u and x.get("type") == 1 for x in shadow.candidate[r["start_k"]])
                for u in r["chain"][1:]) for r in shadow.episodes)
    n_withheld = sum(len(v) for v in shadow.withheld.values())
    n_events = sum(1 for _, e in shadow.events if e.kind in ("withhold", "repeat"))
    integrity["withheld actions = start withholdings + repeats"] = n_withheld == n_events
    integrity["at most one active episode per unit"] = all(
        len(set(r["chain"])) == len(r["chain"]) for r in shadow.episodes) and not overlapping(shadow.episodes)
    return SideAnalysis(side, shadow, census(side), exposure(side), integrity)


def overlapping(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a unit is a member of two episodes whose active spans (start to end decision) overlap."""
    spans: Dict[Any, List[Tuple[int, int]]] = collections.defaultdict(list)
    for r in rows:
        for u in r["chain"]:
            spans[u].append((r["start_k"], r["end_k"]))
    for items in spans.values():
        items.sort()
        if any(b[0] < a[1] for a, b in zip(items, items[1:])):
            return True
    return False


# ------------------------------------------------------------------------------------------------
# section 17: stops and disposition

def episode_key(a: SideAnalysis, row: Mapping[str, Any]) -> Tuple[Any, ...]:
    """Replica de-duplication (section 17, stop C): the same scenario-side, start step, start hex, first hex, members
    and routes count once however many recorded games repeat them."""
    return (a.side.scenario_side, row["start_step"], row["origin"], row["first_hex"],
            tuple(sorted(row["chain"], key=str)), tuple(sorted(row["members"][u].route for u in row["chain"])))


def distinct_episodes(analyses: Sequence[SideAnalysis]) -> Dict[Tuple[Any, ...], List[Tuple[SideAnalysis, Dict[str, Any]]]]:
    out: Dict[Tuple[Any, ...], List[Tuple[SideAnalysis, Dict[str, Any]]]] = {}
    for a in analyses:
        for r in a.shadow.episodes:
            out.setdefault(episode_key(a, r), []).append((a, r))
    return out


def stops(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    """The three frozen stop conditions (section 17), each reported whatever the others decide."""
    out: Dict[str, Any] = {}
    hh = [a for a in analyses if a.side.population == "HH"]
    per = {a.side.label: len(a.shadow.episodes) for a in hh}
    out["A_hh_opportunity"] = {"episodes_by_hh_side_game": per, "minimum_per_side_game": STOP_A_MIN_EPISODES,
                               "hh_side_games": len(hh),
                               "met": len(hh) != HH_SIDE_GAMES or any(n < STOP_A_MIN_EPISODES for n in per.values())}
    h0 = [a for a in analyses if a.side.population == "H0"]
    sides = sorted({a.side.scenario_side for a in h0 if a.shadow.episodes})
    out["B_h0_generality"] = {"h0_scenario_sides_with_an_episode": len(sides), "h0_scenario_sides": len({a.side.scenario_side for a in h0}),
                              "minimum_scenario_sides": STOP_B_MIN_SCENARIO_SIDES,
                              "met": len(sides) < STOP_B_MIN_SCENARIO_SIDES}
    distinct = distinct_episodes(analyses)
    n = len(distinct)
    risk = sum(1 for occurrences in distinct.values() if any(r["first_owner_risk"] for _, r in occurrences))
    raw = sum(len(v) for v in distinct.values())
    out["C_onward_capture_conflict"] = {"episodes_raw": raw, "episodes_distinct": n, "first_owner_risk_episodes": risk,
                                        "share": f"{risk}/{n}", "evaluable": n > 0, "met": n == 0 or 2 * risk > n}
    return out


def disposition(fidelity_ok: bool, integrity_ok: bool, unexplained: int, stop: Mapping[str, Any]) -> Dict[str, Any]:
    """First match: INVALID (fidelity, integrity or any unexplained action difference); INADEQUATE_OPPORTUNITY (stop A
    or B); ONWARD_CAPTURE_RISK (stop C); OFFLINE_PASS."""
    invalid = not fidelity_ok or not integrity_ok or unexplained != 0
    met = [k for k in ("A_hh_opportunity", "B_h0_generality", "C_onward_capture_conflict") if stop[k]["met"]]
    if invalid:
        outcome = DISPOSITIONS[0]
    elif stop["A_hh_opportunity"]["met"] or stop["B_h0_generality"]["met"]:
        outcome = DISPOSITIONS[1]
    elif stop["C_onward_capture_conflict"]["met"]:
        outcome = DISPOSITIONS[2]
    else:
        outcome = DISPOSITIONS[3]
    return {"disposition": outcome, "fidelity_ok": bool(fidelity_ok), "integrity_ok": bool(integrity_ok),
            "unexplained_action_differences": unexplained, "stops_met": met}


# ------------------------------------------------------------------------------------------------
# section 16: Sprint 25's collective departures

def s25_category(side: SideAnalysis, defenders: Sequence[Any], orders: Mapping[Any, Mapping[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """The first-match category of one Sprint 25 multi-defender order-vacating loss (descriptive)."""
    frames = side.side.frames
    ks = {orders[d]["order_k"] for d in defenders}
    facts: Dict[str, Any] = {"order_decisions": len(ks)}
    if len(ks) != 1:
        return S25_CATEGORIES[0], facts
    (k,) = ks
    f = frames[k]
    hexes = {(f.own.get(d) or {}).get("cur_hex") for d in defenders}
    if len(hexes) != 1:
        return S25_CATEGORIES[1], facts
    actions = [orders[d]["action"] for d in defenders]
    firsts = {(list(a.get("move_path") or ()) or [None])[0] for a in actions}
    if len(firsts) != 1 or None in firsts:
        return S25_CATEGORIES[2], facts
    if not any(sc.threat_exposed(f, a) for a in actions):
        return S25_CATEGORIES[3], facts
    base = [dict(a) for a in f.actions]
    if not all(dict(a) in base for a in actions):
        return S25_CATEGORIES[4], facts
    started = [r for r in side.shadow.episodes if r["start_k"] == k and len(set(r["chain"]) & set(defenders)) >= 2]
    stateless = ts.decide(f.cur_step, f.stage, f.own, f.enemies.values(), f.valid, f.actions, ts.StaggerMemory(),
                          side.side.travel)
    stateless_hit = any(o == "triggered" and len(set(units) & set(defenders)) >= 2 for _, _, units, o in stateless.groups)
    facts["stateless_trigger"] = stateless_hit
    facts["stateful_episode"] = bool(started)
    if not stateless_hit:
        return S25_CATEGORIES[5], facts
    first = side.shadow.first_divergence
    if started and first == k and prefix_supported(side.side, k):
        return S25_CATEGORIES[6], facts
    return S25_CATEGORIES[7], facts


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


def class_label(classes: Sequence[str]) -> str:
    counts = collections.Counter(classes)
    return ", ".join(f"{c} x{counts[c]}" if counts[c] > 1 else c for c in sorted(counts))


def public_episode(a: SideAnalysis, row: Mapping[str, Any], ordinal: int, counted: bool, risk_any: bool) -> Dict[str, Any]:
    """One sanitised episode row (no unit id, hex or route)."""
    names = objective_labels(a.side.values)
    onward = []
    for i, u in enumerate(row["chain"][1:], start=1):
        o = dict(row["onward"][u])
        dest = o.pop("destination")
        o["destination"] = names.get(dest, "unlabelled objective") if o["destination_kind"] != DEST_NOT_OBJECTIVE else None
        o["chain_position"] = i
        o["unit_class"] = row["classes"][i]
        rel = row["releases"].get(u)
        q = row["queue"].get(u)
        o["replay_outcome"] = (f"released, {rel['reason']}" + ("" if rel["moved"] else ", no baseline-v2 MOVE")) if rel \
            else (f"left the queue, {q['reason']}" if q else "pending at the end")
        o["replay_wait_steps"] = (rel["step"] - row["start_step"]) if rel else (q["step"] - row["start_step"]) if q else None
        onward.append(o)
    return {
        "population": a.side.population, "side_game": a.side.label, "scenario_side": a.side.scenario_side,
        "episode_ordinal": ordinal, "start_step": row["start_step"], "group_size": row["group_size"],
        "classes": class_label(row["classes"]), "leader_class": row["classes"][0],
        "hex_times": sorted(row["hex_times"]), "different_hex_times": row["different_hex_times"],
        "members_exposed": row["members_exposed"], "members_stacked_at_start": row["members_stacked_at_start"],
        "own_ground_on_start_hex": row["own_ground_on_start_hex"],
        "carriers_with_passengers": row["carriers_with_passengers"],
        "shared_route_prefix": row["shared_route_prefix"], "route_lengths": sorted(row["route_lengths"]),
        "destination_kinds": tally(row["destination_kinds"]), "same_destination": row["same_destination"],
        "first_divergence": row["first_divergence"], "post_divergence": row["post_divergence"],
        "prefix_supported": row["prefix_supported"], "projected_waits": row["projected_waits"],
        "replay_end": row["end"], "replay_repeats": row["repeats"], "replay_timeout": row["timeout"],
        "first_owner_risk": row["first_owner_risk"], "counted_in_stop_c": counted,
        "first_owner_risk_in_any_replica": risk_any,
        "follow_up": row["follow_up"], "damage": row["damage"], "followers": onward,
    }


def converging_decisions(groups: Sequence[Tuple[int, int, int, Tuple[Any, ...], str]]) -> int:
    """Decisions at which two or more triggered groups from different start hexes share one first hex (section 8)."""
    firsts = collections.Counter((k, first) for k, _, first, _, outcome in groups if outcome == "triggered")
    return len({k for (k, _), n in firsts.items() if n >= 2})


def side_summary(a: SideAnalysis) -> Dict[str, Any]:
    s = a.shadow
    rows = s.episodes
    first = s.first_divergence
    followers = [(r, u) for r in rows for u in r["chain"][1:]]
    return {
        "side_game": a.side.label, "population": a.side.population, "scenario_side": a.side.scenario_side,
        "decisions": len(a.side.frames), "play_decisions": sum(1 for f in a.side.frames if f.stage == 2),
        "census": a.census, "mover_reasons": dict(sorted(collections.Counter(c.reason for *_, c in s.checks).items())),
        "group_outcomes": dict(sorted(collections.Counter(o for *_, o in s.groups).items())),
        "episodes": len(rows), "episodes_at_first_divergence": sum(1 for r in rows if r["first_divergence"]),
        "episodes_after_first_divergence": sum(1 for r in rows if r["post_divergence"]),
        "distinct_units_in_episodes": len({u for r in rows for u in r["chain"]}),
        "distinct_leaders": len({r["chain"][0] for r in rows}),
        "distinct_followers": len({u for r, u in followers}),
        "followers": len(followers),
        "group_sizes": tally(r["group_size"] for r in rows),
        "decisions_with_two_groups_into_one_first_hex": converging_decisions(s.groups),
        "withheld_actions": sum(len(v) for v in s.withheld.values()), "withheld_decisions": len(s.withheld),
        "replay_release_reasons": tally(rel["reason"] for r in rows for rel in r["releases"].values()),
        "replay_queue_exits": tally(q["reason"] for r in rows for q in r["queue"].values()),
        "replay_ends": tally(r["end"] for r in rows),
        "projected_wait": dist(w for r in rows for w in r["projected_waits"]),
        "first_divergence": None if first is None else {
            "decision": first, "step": a.side.frames[first].cur_step, "prefix_supported": prefix_supported(a.side, first)},
        "exposure": a.exposure,
        "unexplained_action_differences": len(s.unexplained),
        "integrity": dict(sorted(a.integrity.items())),
    }


def certificate(a: SideAnalysis) -> Optional[Dict[str, Any]]:
    """The public first-divergence certificate of one side-game (section 14)."""
    s = a.shadow
    first = s.first_divergence
    if first is None:
        return None
    f = a.side.frames[first]
    base, cand = [dict(x) for x in f.actions], [dict(x) for x in s.candidate[first]]
    removed = [x for x in base if x not in cand]
    rows = [r for r in s.episodes if r["start_k"] == first]
    members = {u for r in rows for u in r["chain"]}
    followers = {u for r in rows for u in r["chain"][1:]}
    return {"side_game": a.side.label, "population": a.side.population, "decision": first, "step": f.cur_step,
            "decisions_before_identical": first, "prefix_supported": prefix_supported(a.side, first),
            "on_policy_baseline_v2_witness": a.side.population == "HH" or prefix_supported(a.side, first),
            "episodes": len(rows), "group_sizes": [r["group_size"] for r in rows],
            "classes": [class_label(r["classes"]) for r in rows],
            "baseline_action_types": [x.get("type") for x in base],
            "candidate_action_types": [x.get("type") for x in cand],
            "only_follower_moves_withheld": all(x.get("type") == 1 and x.get("obj_id") in followers for x in removed)
            and len(removed) == len(followers),
            "leader_moves_kept": all(any(x.get("obj_id") == r["chain"][0] and x.get("type") == 1 for x in cand) for r in rows),
            "unrelated_actions_unchanged": [x for x in base if x.get("obj_id") not in members]
            == [x for x in cand if x.get("obj_id") not in members],
            "first_owner_risk": [r["first_owner_risk"] for r in rows]}


def pooled(analyses: Sequence[SideAnalysis]) -> Dict[str, Any]:
    rows = [(a, r) for a in analyses for r in a.shadow.episodes]
    followers = [(a, r, u) for a, r in rows for u in r["chain"][1:]]
    census_sum: collections.Counter = collections.Counter()
    exposure_sum: collections.Counter = collections.Counter()
    for a in analyses:
        census_sum.update(a.census)
        exposure_sum.update(a.exposure)
    return {
        "side_games": len(analyses), "episodes": len(rows),
        "side_games_with_an_episode": len({(a.side.game, a.side.faction) for a, _ in rows}),
        "scenario_sides_with_an_episode": len({a.side.scenario_side for a, _ in rows}),
        "games_with_an_episode": len({a.side.game for a, _ in rows}),
        "distinct_units": len({(a.side.game, a.side.faction, u) for a, r in rows for u in r["chain"]}),
        "followers": len(followers),
        "census": dict(sorted(census_sum.items())), "exposure": dict(sorted(exposure_sum.items())),
        "group_sizes": tally(r["group_size"] for _, r in rows),
        "leader_classes": tally(r["classes"][0] for _, r in rows),
        "member_classes": tally(c for _, r in rows for c in r["classes"]),
        "different_hex_times": sum(1 for _, r in rows if r["different_hex_times"]),
        "all_members_exposed": sum(1 for _, r in rows if r["members_exposed"] == r["group_size"]),
        "members_stacked_at_start": sum(r["members_stacked_at_start"] for _, r in rows),
        "members": sum(r["group_size"] for _, r in rows),
        "carriers_with_passengers": sum(r["carriers_with_passengers"] for _, r in rows),
        "shared_route_prefix": dist(r["shared_route_prefix"] for _, r in rows),
        "same_destination": sum(1 for _, r in rows if r["same_destination"]),
        "destination_kinds_of_followers": tally(r["onward"][u]["destination_kind"] for _, r, u in followers),
        "projected_wait": dist(r["onward"][u]["projected_wait"] for _, r, u in followers),
        "follow_up_all_members_followed": sum(1 for _, r in rows if r["follow_up"]["all_followed"]),
        "follow_up_co_located_moving_beyond_start": sum(1 for _, r in rows if r["follow_up"]["all_followed"]
                                                        and r["follow_up"]["co_located_moving_beyond_start"]),
        "follow_up_separated_after_the_start_hex": sum(1 for _, r in rows if r["follow_up"]["all_followed"]
                                                       and not r["follow_up"]["co_located_moving_beyond_start"]),
        "follow_up_stacked_moving_inside_envelope_unit_decisions": sum(
            r["follow_up"]["stacked_moving_inside_envelope_unit_decisions"] for _, r in rows if r["follow_up"]["all_followed"]),
        "follow_up_leader_departure_steps": dist(r["follow_up"]["leader_recorded_departure_steps"] for _, r in rows),
        "damage": {k: sum(r["damage"][k] for _, r in rows) for k in sorted(rows[0][1]["damage"])} if rows else {},
        "onward": {
            "followers_first_owner": sum(1 for _, r, u in followers if r["onward"][u]["first_owner"]),
            "followers_with_other_own_first_owners": sum(1 for _, r, u in followers if r["onward"][u]["other_own_first_owners"]),
            "followers_destination_first_owned_before": sum(1 for _, r, u in followers if r["onward"][u]["first_owned_before_start"]),
            "followers_destination_never_owned": sum(1 for _, r, u in followers if r["onward"][u]["never_owned"]),
            "followers_later_lost": sum(1 for _, r, u in followers if r["onward"][u]["later_lost"]),
            "followers_pushed_past_the_end": sum(1 for _, r, u in followers if r["onward"][u]["pushed_past_the_end"]),
            "followers_unreachable_at_free_flow": sum(1 for _, r, u in followers if r["onward"][u]["unreachable_free_flow"]),
            "steps_start_to_first_ownership_of_first_owners": dist(r["onward"][u]["steps_start_to_first_ownership"]
                                                                  for _, r, u in followers if r["onward"][u]["first_owner"]),
            "projected_wait_of_first_owners": dist(r["onward"][u]["projected_wait"] for _, r, u in followers
                                                   if r["onward"][u]["first_owner"]),
            "episodes_with_first_owner_risk": sum(1 for _, r in rows if r["first_owner_risk"]),
        },
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


def digit_words(data: Any, allowed: Iterable[str] = ()) -> List[str]:
    """Every word made only of digits in a key or string of ``data`` except the ``allowed`` ones (section 18: public
    labels carry none but the registered scenario identifiers, which name scenario-sides and cannot equal a four-digit
    hex or a unit identifier)."""
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
