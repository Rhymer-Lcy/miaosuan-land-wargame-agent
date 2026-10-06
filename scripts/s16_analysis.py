"""Sprint 16 mechanism capture: the frozen analysis (``docs/SPRINT16_MECHANISM_CAPTURE.md``), server only.

    python scripts/s16_analysis.py freeze [--check]            # inputs.json, before session 2791
    python scripts/s16_analysis.py rehearse [--workers N]      # pre-registration known-answer run, private output only
    python scripts/s16_analysis.py run [--check] [--workers N] # after the three sessions: the public files

``freeze`` pins every historical input by SHA-256 (the four Sprint 12 primary captures, the four Sprint 10 captures
that anchor the historical shooters and the problem objective, the cost data), the committed card, the shadow
identity and the rules, and derives the historical anchors (published as counts and decisions only).

``rehearse`` runs the complete per-capture replay on the four real Sprint 12 v3 captures, which are in exactly the
format the new captures will have, as stand-ins: every reconstruction check, the shadows, the first divergences, the
certificates, the episode tracker and the restoration measure. Its output is private
(``local/diagnostics/s16/rehearsal.json``); it opens no engine.

``run`` requires the pins and the three recorded games, replays every decision of the three new v3 captures (the
on-policy prefix and, labelled, the off-policy remainder) and every decision of the four primary captures (R3, R4),
classifies each configuration, decides the disposition, and writes ``games.json``, ``shadows.json``,
``restoration.json`` and ``disposition.json`` under ``evaluation/s16-mechanism-capture/``; ``--check`` regenerates them
in memory and compares byte for byte. No engine is opened; the ledger is read only.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin, Stage  # noqa: E402
from miaosuan_agent.decision import digest  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s13_diagnosis as sd  # noqa: E402
from miaosuan_agent.evaluation import s14_design as sx  # noqa: E402
from miaosuan_agent.evaluation import s15_delayed as s15  # noqa: E402
from miaosuan_agent.evaluation import s16_mechanism as ms  # noqa: E402
from miaosuan_agent.evaluation import s16_shadow as sh  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments import t9_delayed as td  # noqa: E402
from miaosuan_agent.experiments import t9_redistribution as tr  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory, hex_distance  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402
from miaosuan_agent.experiments.t9_allocation import AllocationAddon  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s16_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S14 = load("s14_design_replay")  # Sprint 14's frozen loaders, read only
CARDS = load("build_s16_card")

SCHEMA_INPUTS = "miaosuan-s16-inputs/1"
OUT_DIR = REPO_ROOT / "evaluation" / ms.STUDY_ID
INPUTS = OUT_DIR / "inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s16"
WORK = REPO_ROOT / "local" / "evaluation" / ms.CARD_ID
CAPTURES = ("t9.json", "v3.json", "v3series.json.gz", "timeline.json", "timeline.pkl")
SHADOWS: Tuple[str, ...] = tuple(sh.RULES)
V3_TRACK = "v3-track"  # the corrected memory with nobody eligible: frozen v3's actions, the shadows' bookkeeping
PUBLIC_FILES = ("games", "shadows", "restoration", "disposition")
REPORTED_S12_FIELDS_EXCLUDED = ("t9v2_like", "collapse", "adverse_class", "replication_triggers",
                                "fifth_objective_attributed_to_v3_selection")
KIND = {1: "infantry", 2: "vehicle"}
NOTE = ("mechanism capture: frozen v3 played every decision of its seat; every shadow figure is a decision computed "
        "afterwards on the recorded v3 observations. Before a shadow's first divergence the recorded states are its own "
        "trajectory (on-policy); every later figure is OFF-POLICY shadow replay on v3 states and is descriptive only. "
        "Nothing here is a score estimate or evidence of an effect; one game per configuration shows one observed "
        "trajectory, not what a configuration can or cannot do")


def sha256(path: Path) -> str:
    return S14.sha256(path)


def dump(data: Any) -> str:
    return ms.dump(data)


# ------------------------------------------------------------------------------------------------
# Historical anchors (Sprint 10 captures)


def baseline_entry(config: str) -> Sequence[Any]:
    return next(e for e in S14.ADVERSE if e[0] == config and e[6] == "baseline-v2")


def historical_shooters(config: str) -> Dict[int, int]:
    """Units of the direct-fire orders of Sprint 10's baseline-v2 capture at its firing decisions: unit -> first."""
    anchors = set(ms.RULES["historical_fire_anchors"][config])
    _, _, rows = S14.adverse_stream(baseline_entry(config))
    out: Dict[int, int] = {}
    for row in rows:
        if row["k"] in anchors:
            for action in row["submitted"]:
                if action.get("type") == ms.SHOOT:
                    out[action["obj_id"]] = min(out.get(action["obj_id"], row["k"]), row["k"])
    return out


def historical_start(config: str) -> Dict[int, Tuple[Any, Any]]:
    """(type, hex) of every own ground unit at decision 0 of Sprint 10's baseline-v2 capture (identity mapping)."""
    seat, faction, rows = S14.adverse_stream(baseline_entry(config))
    return {u["obj_id"]: (u.get("type"), u.get("cur_hex")) for u in rows[0]["raw"].get("operators") or ()
            if u.get("color") == faction}


def problem_objective() -> Dict[str, Any]:
    """The 80-point objective T9-v1 never owned in Sprint 10's 2120531121 C3 capture, and baseline-v2's first
    ownership of it in the other capture (Sprint 15's derivation)."""
    entries = {e[6]: e for e in S14.ADVERSE if e[0] == ms.RESERVATION_CONFIG}
    flags: Dict[str, Dict[Any, List[Tuple[int, Any]]]] = {}
    values: Dict[Any, Any] = {}
    faction = None
    for played, entry in entries.items():
        _, faction, rows = S14.adverse_stream(entry)
        history: Dict[Any, List[Tuple[int, Any]]] = {}
        for row in rows:
            for city in row["raw"].get("cities") or ():
                values[city["coord"]] = city.get("value")
                h = history.setdefault(city["coord"], [])
                if not h or h[-1][1] != city.get("flag"):
                    h.append((row["k"], city.get("flag")))
        flags[played] = history
    never = [c for c, h in flags["t9-v1"].items() if values[c] == 80 and all(f != faction for _, f in h)]
    if len(never) != 1:
        raise SystemExit(f"refused: expected one 80-point objective T9-v1 never owned, found {len(never)}")
    coord = never[0]
    captured = next((k for k, f in flags["baseline-v2"][coord] if f == faction), None)
    return {"coord": coord, "label": tl.labels(values)[coord], "baseline_capture_decision": captured,
            "faction": faction}


def anchors() -> Dict[str, Any]:
    shooters = {c: historical_shooters(c) for c in ms.FIRE_CONFIGS}
    starts = {c: historical_start(c) for c in ms.FIRE_CONFIGS}
    objective = problem_objective()
    return {"shooters": shooters, "starts": starts, "objective": objective}


def public_anchors(a: Mapping[str, Any]) -> Dict[str, Any]:
    out = {}
    for config in ms.FIRE_CONFIGS:
        units = a["shooters"][config]
        out[config] = {"historical_shooters": len(units), "firing_decisions": sorted(set(units.values())),
                       "registered_anchors": ms.RULES["historical_fire_anchors"][config]}
    o = a["objective"]
    out[ms.RESERVATION_CONFIG] = {"problem_objective": o["label"], "baseline_capture_decision":
                                  o["baseline_capture_decision"],
                                  "registered_anchor": ms.RULES["historical_capture_anchor"][ms.RESERVATION_CONFIG]}
    return out


def anchor_problems(a: Mapping[str, Any]) -> List[str]:
    problems = []
    for config in ms.FIRE_CONFIGS:
        found = sorted(set(a["shooters"][config].values()))
        if found != sorted(ms.RULES["historical_fire_anchors"][config]):
            problems.append(f"{config}: historical firing decisions {found} differ from the registered anchors")
    captured = a["objective"]["baseline_capture_decision"]
    if captured != ms.RULES["historical_capture_anchor"][ms.RESERVATION_CONFIG]:
        problems.append(f"{ms.RESERVATION_CONFIG}: baseline-v2 first owned the problem objective at {captured}")
    return problems


# ------------------------------------------------------------------------------------------------
# Inputs


def historical_files() -> List[Dict[str, Any]]:
    entries = [baseline_entry(c) for c in ms.FIRE_CONFIGS] + [e for e in S14.ADVERSE if e[0] == ms.RESERVATION_CONFIG]
    return [{"configuration": e[0], "game_id": e[2], "played": e[6], "windows_sha256": sha256(S14.adverse_file(e))}
            for e in entries]


def build_inputs() -> Dict[str, Any]:
    card_text = CARDS.CARD.read_text(encoding="utf-8")
    if card_text != ms.dump(CARDS.build()):
        raise SystemExit("refused: the committed card does not rebuild byte-identically")
    card = json.loads(card_text)
    primary = [{**g, "files": {k: sha256(p) for k, p in S14.primary_files(g["game_id"]).items()}}
               for g in S14.primary_games()]
    if len(primary) != 4:
        raise SystemExit("refused: expected the four Sprint 12 primary captures")
    a = anchors()
    problems = anchor_problems(a)
    if problems:
        raise SystemExit(f"refused: {problems}")
    shadow = CARDS.shadow_identity()
    return {"schema": SCHEMA_INPUTS, "card": {"id": ms.CARD_ID, "canonical_sha256": mf.digest(card)},
            "shadow": {"id": shadow["id"], "source_sha256": shadow["source_sha256"], "rules": shadow["rules"],
                       "target": shadow["target"], "executable": False},
            "rules": ms.RULES, "rules_sha256": ms.rules_digest(),
            "primary": {"card": S14.PRIMARY_CARD, "games": primary},
            "historical_adverse": historical_files(),
            "cost_data": {"primary_cost": S14.tree_digest(S14.EV / S14.PRIMARY_CARD / "data" / S14.PRIMARY_SCENARIO),
                          "s10_cost": S14.tree_digest(S14.EV / "s10-t9-v1-diagnosis" / "data"),
                          "s10_c2_cost": S14.tree_digest(S14.EV / "s10-t9-v1-c2-diagnosis" / "data")},
            "anchors": public_anchors(a),
            "note": "historical inputs pinned before session 2791; files stay under the ignored local/ tree"}


def require_inputs() -> Mapping[str, Any]:
    committed = INPUTS.read_text(encoding="utf-8")
    if dump(build_inputs()) != committed:
        raise SystemExit("refused: an input, an identity or a threshold differs from inputs.json")
    return json.loads(committed)


# ------------------------------------------------------------------------------------------------
# Streams


def card() -> Dict[str, Any]:
    return json.loads(CARDS.CARD.read_text(encoding="utf-8"))


def capture_files(work: Path, game_id: str) -> Dict[str, Path]:
    return {name: work / "capture" / f"{game_id}.{name}" for name in CAPTURES}


def sprint12_stream(record: Mapping[str, Any], timeline: Mapping[str, Any], windows: Mapping[str, Any]):
    """A Sprint 12-format capture (the new games and the primary games alike): the v3 seat's rows, and its states
    (decisions 0..N-1 and the final one)."""
    seat = next(s["seat"] for s in record["seats"] if s["policy"] == ms.V3_ID)
    faction = next(s["faction"] for s in record["seats"] if s["policy"] == ms.V3_ID)
    states, raws = tl.load_states(windows, seat, faction)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    memories = [pickle.loads((s["seats"].get(seat) or s["seats"].get(str(seat)))["memory"]) for s in samples]
    steps = timeline["steps"]
    rows = []
    for k in range(len(steps)):
        row = (steps[k].get("s12") or {}).get(str(seat)) or {}
        rows.append({"k": k, "raw": raws[k], "memory": memories[k], "baseline": row.get("baseline_actions"),
                     "trace": row.get("baseline_trace_sha256"), "allocation": row.get("allocation"),
                     "submitted": [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == seat]})
    return seat, faction, rows, states, steps


def costs_of(the_card: Mapping[str, Any], work: Path, scenario: str) -> MoveCosts:
    map_id = next(s["map_id"] for s in the_card["scenarios"] if s["scenario_id"] == scenario)
    inputs = sdk_data.load_inputs(work / "data" / scenario / "Data", scenario, map_id)
    return MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")


# ------------------------------------------------------------------------------------------------
# Per-game facts from the observed v3 trajectory (computed before the replay: they fix the risk windows)


def fire_facts(seat: int, rows: Sequence[Mapping[str, Any]], states: Sequence[Any], steps: Sequence[Any]
               ) -> Tuple[Dict[Any, List[int]], Dict[str, Any]]:
    """Direct-fire listings, orders and responses of the v3 seat: unit -> decisions with a listing or an order (own
    ground units listed; ordered units of any kind), and the public aggregate."""
    observed: Dict[Any, Set[int]] = collections.defaultdict(set)
    listed_decisions, order_decisions, responses = [], [], collections.Counter()
    for k in range(len(rows)):
        listed = [u for u, valid in states[k].valid.items() if ms.SHOOT in valid]
        for u in listed:
            observed[u].add(k)
        if listed:
            listed_decisions.append(k)
        orders = [a for a in rows[k]["submitted"] if a.get("type") == ms.SHOOT]
        for action in orders:
            observed[action.get("obj_id")].add(k)
            responses[tl.response(steps[k], seat, action)] += 1
        if orders:
            order_decisions.append(k)
    public = {"decisions_with_a_listing": len(listed_decisions),
              "first_listing_decision": listed_decisions[0] if listed_decisions else None,
              "last_listing_decision": listed_decisions[-1] if listed_decisions else None,
              "orders": sum(responses.values()), "order_decisions": order_decisions,
              "responses": dict(sorted(responses.items())), "units_with_a_fire_role": len(observed)}
    return {u: sorted(v) for u, v in observed.items()}, public


def first_ownership(states: Sequence[Any], coord: Any, faction: int, decisions: int) -> Optional[int]:
    return next((k for k in range(decisions) if states[k].flags.get(coord) == faction), None)


# ------------------------------------------------------------------------------------------------
# The replay of one stream


def record_view(memory: Sequence[Sequence[int]], observation: Observation, faction: int) -> Dict[int, List[int]]:
    """The records as a shadow's trigger saw them at this decision (the corrected update applied to a copy)."""
    records, _ = td.decode(memory)
    sh.observe(observation, faction, records)
    return records


def certificate(name: str, k: int, ordinal: int, observation: Observation, seat: int, faction: int,
                actions: Sequence[Mapping[str, Any]], v3: tb.Allocation, alloc: td.Allocation,
                before: Sequence[Sequence[int]], checks: Mapping[str, Any], costs: MoveCosts,
                problem: Optional[Any]) -> Dict[str, Any]:
    """Every fact of a shadow's first divergence that can be read at that decision (private: unit ids, hexes)."""
    ground = sx.own_ground(observation, faction)
    cities = {c.coord for c in (observation.cities() or ())}
    time_info = observation.time()
    now, end = time_info.cur_step, time_info.max_step
    router = ShootReservationPolicy(costs).router
    counted, _ = sd.counted_incumbents(observation, faction, router)
    selected_at = collections.Counter(v3.selected.values())
    base_moves, v3_moves, out_moves = (sx.ground_moves(actions, ground), sx.ground_moves(v3.actions, ground),
                                       sx.ground_moves(alloc.actions, ground))
    changed = ms.changed_units(v3.actions, alloc.actions)
    raw = observation.fields
    listed = raw.get("valid_actions") or {}
    enemies = [u.get("cur_hex") for u in raw.get("operators") or () if u.get("color") not in (None, faction)
               and isinstance(u.get("cur_hex"), int)]
    records = record_view(before, observation, faction)
    rule = sh.RULES[name]
    rows_by_unit = {r["unit"]: r for r in checks["redirects"]}
    order = [u for u in alloc.overflow if u in alloc.redirected]
    redirects = []
    for unit in order:
        option = alloc.redirected[unit]
        claimant = alloc.claimants[unit]
        record = records.get(unit)
        same = record is not None and record[td.SOURCE] == claimant.objective
        earlier = sum(1 for u in order[:order.index(unit)] if alloc.redirected[u].objective == option.objective)
        dest_row = counted.get(option.objective, {})
        dest_before = dest_row.get("physical", 0) + dest_row.get("movers", 0) + selected_at[option.objective] + earlier
        src_row = counted.get(claimant.objective, {})
        check = rows_by_unit.get(unit, {})
        ff = check.get("free_flow")
        claimants_there = [{"free_flow": c.free_flow, "feasible": c.status == tr.FULL,
                            "placed": alloc.selected.get(c.obj_id) == option.objective, "unit": c.obj_id}
                           for c in v3.claimants.values() if c.objective == option.objective and c.obj_id != unit]
        holders = set()
        if problem is not None:
            holders = ({u for u, g in ground.items() if not g.move_path and g.cur_hex == problem}
                       | set(counted.get(problem, {}).get("mover_bounds", {}))
                       | {u for u, c in v3.selected.items() if c == problem})
        dists = sorted(hex_distance(ground[unit].cur_hex, h) for h in enemies) if unit in ground else []
        redirects.append({
            "unit": unit, "kind": ground[unit].unit_type if unit in ground else None, "trigger": rule.trigger,
            "same_source_rule": rule.same_source,
            "source": claimant.objective, "alternative": option.objective,
            "episode_count": (record[td.COUNT] + 1) if same else 1,
            "episode_age_steps": (now - record[td.FIRST]) if same and record[td.FIRST] else 0,
            "staging_completed": bool(record and record[td.DONE]),
            "previous_staging_source": record[td.STAGE_SOURCE] if record and record[td.STAGE_SOURCE] else None,
            "previous_staging_source_is_current": bool(record and record[td.STAGE_SOURCE] == claimant.objective),
            "baseline_destination": claimant.objective,
            "v3_form": sx.form(base_moves[unit], v3_moves.get(unit), cities) if unit in base_moves else None,
            "v3_staged_length": len(v3.staged[unit]) if unit in v3.staged else None,
            "shadow_form": sx.form(base_moves[unit], out_moves.get(unit), cities) if unit in base_moves else None,
            "route_cost": option.cost, "own_cost": option.base_cost,
            "detour_ratio": round(option.cost / option.base_cost, 4) if option.base_cost else None,
            "free_flow": ff, "free_flow_candidate": option.free_flow,
            "arrival_slack": None if (ff is None or end is None) else end - (now + ff),
            "source_counted": src_row.get("physical", 0) + src_row.get("movers", 0) + selected_at[claimant.objective],
            "destination_counted_before": dest_before,
            "fire_listed_now": ms.SHOOT in {int(x) for x in (listed.get(unit) or listed.get(str(unit)) or {})},
            "visible_enemies": len(enemies), "nearest_visible_enemy": dists[0] if dists else None,
            "v3_selection_not_kept": bool(checks["violations"].get("a v3 selection not kept", 0)) or any(
                out_moves.get(u) != v3_moves.get(u) for u in v3.selected),
            "dominated": ms.dominated(ff, claimants_there),
            "unreachable": ff is None or (end is not None and now + ff >= end),
            "to_problem_objective": problem is not None and option.objective == problem,
            "consumes_last_place": dest_before == ms.RULES["capacity"] - 1,
            "destination_claimants": [{k_: v for k_, v in c.items() if k_ != "unit"} for c in claimants_there],
            "v3_selected_at_destination": sorted(v3.claimants[u].free_flow for u, c in v3.selected.items()
                                                 if c == option.objective and v3.claimants[u].free_flow is not None),
            "problem_holders_at_divergence": sorted(holders)})
    return {"k": k, "cur_step": now, "ordinal": ordinal, "changed": changed,
            "changed_rows": [{"unit": u, "kind": ground[u].unit_type if u in ground else None,
                              "v3_form": sx.form(base_moves[u], v3_moves.get(u), cities) if u in base_moves else None,
                              "shadow_form": sx.form(base_moves[u], out_moves.get(u), cities) if u in base_moves else None}
                             for u in changed],
            "redirects": redirects, "violations": dict(sorted((a, b) for a, b in checks["violations"].items() if b))}


def new_policy() -> Dict[str, Any]:
    return {"fsd": None, "redirects": [], "exposure": [], "memory_checks": 0, "memory_problems": 0,
            "violations_on_policy": collections.Counter(), "violations_off_policy": collections.Counter(),
            "restored_candidates": set(), "differing_decisions": 0}


def replay(job: Tuple[str, str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One stream: ``("new", game_id, None)`` for a Sprint 16 game, ``("primary", game_id, cell)`` for a Sprint 12
    primary game, ``("rehearsal", game_id, cell)`` for a primary game run through the new-game path."""
    kind, gid, cell = job
    started = time.perf_counter()
    if kind == "new":
        the_card = card()
        entry = next(g for g in the_card["games"] if g["game_id"] == gid)
        files = capture_files(WORK, gid)
        record = json.loads((WORK / "games" / f"{gid}.json").read_text(encoding="utf-8"))
        costs = costs_of(the_card, WORK, entry["scenario_id"])
        config = ms.config_key(entry["scenario_id"], entry["condition"])
    else:
        paths = S14.primary_files(gid)
        files = {"timeline.json": paths["timeline.json"], "timeline.pkl": paths["timeline.pkl"]}
        record = json.loads(paths["record"].read_text(encoding="utf-8"))
        costs = S14.costs_for(S14.PRIMARY_CARD, S14.PRIMARY_SCENARIO, "21")
        config = f"{S14.PRIMARY_SCENARIO} {cell}"
    timeline = json.loads(files["timeline.json"].read_text(encoding="utf-8"))
    with files["timeline.pkl"].open("rb") as handle:
        windows = pickle.load(handle)
    seat, faction, rows, states, steps = sprint12_stream(record, timeline, windows)
    del windows
    observed, fire_public = fire_facts(seat, rows, states, steps)
    values = {c["coord"]: c.get("value") for c in (rows[0]["raw"].get("cities") or ())}
    names = tl.labels(values)
    a = ANCHORS if kind == "new" else None
    problem = a["objective"]["coord"] if kind == "new" and config == ms.RESERVATION_CONFIG else None
    first_own = first_ownership(states, problem, faction, len(rows)) if problem is not None else None
    if config in ms.FIRE_CONFIGS:
        window_end = ms.fire_window_end(config, observed)
    elif config == ms.RESERVATION_CONFIG:
        window_end = ms.reservation_window_end(first_own, len(rows) - 1)
    else:
        window_end = None
    problems: List[str] = []
    identity_problems: List[str] = []
    if kind == "new" and config in ms.FIRE_CONFIGS:
        start = {u["obj_id"]: (u.get("type"), u.get("cur_hex")) for u in rows[0]["raw"].get("operators") or ()
                 if u.get("color") == faction}
        for unit in a["shooters"][config]:
            if a["starts"][config].get(unit) != start.get(unit):
                identity_problems.append(f"{gid}: a historical shooter is not the same unit at decision 0")
    counts = collections.Counter()
    policies = {n: new_policy() for n in SHADOWS}
    trackers = {n: ms.EpisodeTracker() for n in SHADOWS}
    memories = {n: () for n in SHADOWS}
    memories[V3_TRACK] = ()
    reference: Set[Any] = set()
    retarget = collections.Counter()
    retarget_first: Dict[str, Optional[int]] = {"other_source_with_alternative": None, "other_source": None}
    ordinal = 0
    for row in rows:
        k, raw = row["k"], row["raw"]
        observation = Observation.from_raw(raw, Origin.ENGINE)
        memory = row["memory"]
        base_memory = memory.baseline if isinstance(memory, AddonMemory) else memory
        policy = ShootReservationPolicy(costs)
        base = policy.decide(observation, seat, faction, base_memory)
        actions = tuple(base.actions)
        counts["decisions"] += 1
        if row["baseline"] is not None:
            counts["baseline_compared"] += 1
            if rd.plain(actions) != rd.plain(row["baseline"]):
                problems.append(f"k{k}: baseline-v2 re-decided differs from the capture")
        if row["trace"] is not None and digest(base.trace) != row["trace"]:
            problems.append(f"k{k}: baseline-v2 trace digest differs from the capture")
        v3 = tb.allocate(observation, seat, faction, actions, policy.router)
        counts["v3_compared"] += 1
        if rd.plain(v3.actions) != rd.plain(row["submitted"]):
            problems.append(f"k{k}: reconstructed v3 differs from the live decision")
        cap = row["allocation"]
        if cap is not None:
            counts["allocation_compared"] += 1
            if ({str(u): c for u, c in v3.selected.items()} != cap["selected"]
                    or {str(u): list(p) for u, p in v3.staged.items()} != cap["staged"]
                    or {str(u): r for u, r in v3.withheld.items()} != cap["withheld"]):
                problems.append(f"k{k}: v3's allocation differs from the captured allocation")
        play = observation.time().stage == Stage.PLAY
        ground = sx.own_ground(observation, faction)
        active = play and bool(sx.ground_moves(actions, ground))
        if active:
            ordinal += 1
        cities = {c.coord: c for c in (observation.cities() or ())}
        flags = {c: city.flag for c, city in cities.items()}
        units = {u: (g.cur_hex, tuple(g.move_path or ())) for u, g in ground.items()}
        track = sh.allocate(observation, seat, faction, actions, policy.router, None, memories[V3_TRACK])
        if rd.plain(track.actions) != rd.plain(v3.actions):
            problems.append(f"k{k}: the shadow with nobody eligible differs from v3")
        if active:
            seen = record_view(memories[V3_TRACK], observation, faction)
            for unit in track.overflow:
                record = seen.get(unit)
                if record is None or not record[td.DONE]:
                    continue
                other = record[td.STAGE_SOURCE] != track.claimants[unit].objective
                retarget["overflow_after_completed_staging"] += 1
                if other:
                    retarget["at_another_source"] += 1
                    if retarget_first["other_source"] is None:
                        retarget_first["other_source"] = k
                    if track.best.get(unit):
                        retarget["at_another_source_with_an_admissible_alternative"] += 1
                        if retarget_first["other_source_with_alternative"] is None:
                            retarget_first["other_source_with_alternative"] = k
        memories[V3_TRACK] = track.memory
        if kind == "primary" and active and ordinal > 1:
            t9 = AllocationAddon(costs, policy).apply(observation, seat, faction, base, ()).actions
            forms = sx.forms(actions, t9, ground, cities)
            reference |= {u for u, f in forms.items() if f == sx.REDIRECT}
        for name in SHADOWS:
            p = policies[name]
            before = memories[name]
            alloc = sh.allocate(observation, seat, faction, actions, policy.router, sh.RULES[name], before)
            memories[name] = alloc.memory
            p["memory_checks"] += 1
            found = s15.memory_problems(observation, faction, alloc.memory)
            if found:
                p["memory_problems"] += len(found)
                problems.append(f"k{k}: {name} memory: {found[:2]}")
            if play:
                trackers[name].before(units, flags, faction)
            on_policy = p["fsd"] is None
            if alloc.eligible:
                p["exposure"].append((k, len(alloc.eligible), on_policy))
            if not active:
                if ms.diverges(v3.actions, alloc.actions):
                    problems.append(f"k{k}: {name} changed a decision without own ground moves")
                continue
            claimants = {u: (c.objective, c.status == tr.FULL, u in v3.selected) for u, c in v3.claimants.items()}
            trackers[name].after(k, claimants, {u: o.objective for u, o in alloc.redirected.items()})
            if not ms.diverges(v3.actions, alloc.actions):
                continue
            p["differing_decisions"] += 1
            checks = sx.candidate_checks(observation, seat, faction, actions, alloc.actions, alloc, v3, costs)
            bucket = "violations_on_policy" if on_policy else "violations_off_policy"
            p[bucket].update({a: b for a, b in checks["violations"].items() if b})
            clean = not any(checks["violations"].values())
            for r in checks["redirects"]:
                p["redirects"].append({"k": k, "ordinal": ordinal, "cur_step": observation.time().cur_step,
                                       "unit": r["unit"], "from": r["from"], "to": r["to"],
                                       "free_flow": r["free_flow"], "detour": r["detour"], "kind": r["kind"],
                                       "on_policy": on_policy, "clean": clean})
                if ordinal > 1 and clean:
                    p["restored_candidates"].add(r["unit"])
            if on_policy:
                p["fsd"] = certificate(name, k, ordinal, observation, seat, faction, actions, v3, alloc, before,
                                       checks, costs, problem)
    if problems or identity_problems:
        problems = (identity_problems + problems)[:50]
    capturers: Set[Any] = set()
    if problem is not None and first_own is not None:
        capturers = {u for u, position in states[first_own].units.items() if position[0] == problem}
    facts = {"kind": kind, "game": gid, "cell": cell, "configuration": config, "seat_faction": faction,
             "decisions": len(rows), "active_decisions": ordinal, "counts": dict(counts), "problems": problems,
             "fire": fire_public, "window_end": window_end, "first_own_problem_decision": first_own,
             "retargeting": {"events": dict(sorted(retarget.items())), "first": retarget_first},
             "seconds": round(time.perf_counter() - started, 1)}
    private = {"game": gid, "observed_fire": observed,
               "names": {str(c): n for c, n in names.items()}, "policies": {}, "reference": sorted(reference),
               "capturers": sorted(capturers), "trackers": {}, "problem": problem}
    for name in SHADOWS:
        p = policies[name]
        fsd = p["fsd"]
        if fsd is not None and problem is not None:
            for r in fsd["redirects"]:
                r.update(ms.ownership_facts(fsd["k"], first_own, r["problem_holders_at_divergence"], capturers))
        private["policies"][name] = {**{k_: v for k_, v in p.items() if k_ not in ("restored_candidates",)},
                                     "restored_candidates": sorted(p["restored_candidates"]),
                                     "violations_on_policy": dict(p["violations_on_policy"]),
                                     "violations_off_policy": dict(p["violations_off_policy"])}
        private["trackers"][name] = trackers[name]
    return facts, private


# ------------------------------------------------------------------------------------------------
# Classification, combination and public files


def fsd_input(fsd: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    return None if fsd is None else {"k": fsd["k"], "ordinal": fsd["ordinal"], "changed": fsd["changed"]}


def classify(config: str, facts: Mapping[str, Any], private: Mapping[str, Any], name: str) -> Dict[str, Any]:
    fsd = private["policies"][name]["fsd"]
    if config in ms.FIRE_CONFIGS:
        return ms.classify_fire(config, fsd_input(fsd), facts["window_end"], ANCHORS["shooters"][config],
                                private["observed_fire"])
    return ms.classify_reservation(fsd_input(fsd), facts["window_end"], fsd["redirects"] if fsd else [])


def public_certificate(fsd: Optional[Mapping[str, Any]], names: Mapping[str, str], window_end: Optional[int],
                       config: str, observed: Mapping[Any, Sequence[int]]) -> Optional[Dict[str, Any]]:
    """The first divergence without unit ids or hexes: objectives by label, units by kind."""
    if fsd is None:
        return None
    label = lambda coord: None if coord is None else names.get(str(coord), "an objective")  # noqa: E731
    rows = []
    for r in fsd["redirects"]:
        row = {"kind": KIND.get(r["kind"], "other"), "trigger": r["trigger"], "source": label(r["source"]),
               "alternative": label(r["alternative"]), "episode_count": r["episode_count"],
               "episode_age_steps": r["episode_age_steps"], "staging_completed": r["staging_completed"],
               "previous_staging_source": label(r["previous_staging_source"]),
               "previous_staging_source_is_current": r["previous_staging_source_is_current"],
               "baseline_destination": label(r["baseline_destination"]), "v3_action": r["v3_form"],
               "v3_staged_length": r["v3_staged_length"], "shadow_action": r["shadow_form"],
               "route_cost": r["route_cost"], "own_cost": r["own_cost"], "detour_ratio": r["detour_ratio"],
               "free_flow_steps": r["free_flow"], "arrival_slack_steps": r["arrival_slack"],
               "source_counted_places": r["source_counted"],
               "destination_counted_places_before": r["destination_counted_before"],
               "fire_listed_now": r["fire_listed_now"], "visible_enemies": r["visible_enemies"],
               "nearest_visible_enemy_hexes": r["nearest_visible_enemy"],
               "before_risk_window_end": None if window_end is None else fsd["k"] <= window_end}
        if config in ms.FIRE_CONFIGS:
            row["firing_role"] = ms.protected_reasons(r["unit"], fsd["k"], window_end, ANCHORS["shooters"][config],
                                                      observed)
        if config == ms.RESERVATION_CONFIG:
            row.update({key: r.get(key) for key in ("v3_selection_not_kept", "dominated", "unreachable",
                                                    "to_problem_objective", "consumes_last_place",
                                                    "before_first_ownership", "capturer_without_place")})
            row["destination_claimant_free_flows"] = sorted(c["free_flow"] for c in r["destination_claimants"]
                                                            if c["free_flow"] is not None)
            row["v3_selected_free_flows_at_destination"] = r["v3_selected_at_destination"]
            row["bad_reservation_clauses"] = ms.reservation_flags(r)
        rows.append(row)
    changed = [{"kind": KIND.get(c["kind"], "other"), "v3_action": c["v3_form"], "shadow_action": c["shadow_form"]}
               for c in fsd["changed_rows"]]
    return {"decision": fsd["k"], "cur_step": fsd["cur_step"], "ordinal": fsd["ordinal"], "changed_units": changed,
            "redirects": rows, "violations": fsd["violations"]}


def exposure_summary(p: Mapping[str, Any], window_end: Optional[int]) -> Dict[str, Any]:
    rows = p["exposure"]
    inside = [r for r in rows if window_end is not None and r[0] <= window_end]
    return {"trigger_held_observations": sum(r[1] for r in rows),
            "trigger_held_observations_in_risk_window": sum(r[1] for r in inside),
            "trigger_held_observations_in_risk_window_on_policy": sum(r[1] for r in inside if r[2]),
            "decisions_with_the_trigger_held": len(rows),
            "first_decision_with_the_trigger_held": rows[0][0] if rows else None}


def off_policy_summary(p: Mapping[str, Any]) -> Dict[str, Any]:
    later = [r for r in p["redirects"] if not r["on_policy"]]
    return {"label": "OFF-POLICY shadow replay on v3 states after the first divergence: descriptive only",
            "redirects": len(later), "redirected_units": len({r["unit"] for r in later}),
            "decisions": len({r["k"] for r in later}),
            "violations": dict(sorted(p["violations_off_policy"].items()))}


def combine(results: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]], game_facts: Mapping[str, Any],
            ledger: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    facts = {f["game"]: f for f, _ in results}
    private = {p["game"]: p for _, p in results}
    the_card = card()
    problems: List[str] = list(anchor_problems(ANCHORS))
    if not ledger["ok"]:
        problems.append(f"ledger audit: {ledger['problems']}")
    new = {f["configuration"]: f for f in facts.values() if f["kind"] == "new"}
    for f in facts.values():
        problems.extend(f"{f['game']}: {p}" for p in f["problems"])
    games_public = []
    for entry in the_card["games"]:
        config = ms.config_key(entry["scenario_id"], entry["condition"])
        g = game_facts.get(entry["game_id"])
        if g is None:
            problems.append(f"{entry['game_id']}: no record")
            continue
        structural = ms.structural_stops(g["stops"])
        if structural:
            problems.append(f"{entry['game_id']}: structural stops {structural}")
        f = new.get(config)
        public_v3 = {k: v for k, v in tl.public(g).items() if k not in REPORTED_S12_FIELDS_EXCLUDED}
        public_v3["stops"] = {c: n for c, n in public_v3.get("stops", {}).items() if n}
        row = {"position": entry["screen_position"], "configuration": config, "game_id": entry["game_id"],
               "session": g.get("session"), "status": g.get("status"), "steps": g.get("steps"),
               "structural_stops": structural,
               "reported_v3_findings": sorted(c for c, d in g["stops"].items() if d and c not in ms.STRUCTURAL_STOPS),
               "v3": public_v3}
        if f is not None:
            row["offline_reconstruction"] = {"decisions": f["decisions"], **{k: v for k, v in f["counts"].items()},
                                             "problems": len(f["problems"])}
            row["fire_in_the_new_game"] = f["fire"]
            row["staging_then_overflow_on_the_v3_trajectory"] = f["retargeting"]
            row["risk_window_end_decision"] = f["window_end"]
            if config == ms.RESERVATION_CONFIG:
                row["problem_objective"] = {"label": ANCHORS["objective"]["label"],
                                            "v3_first_ownership_decision": f["first_own_problem_decision"]}
        games_public.append(row)
    missing = sorted(set(ms.CONFIGS) - set(new))
    if missing:
        problems.append(f"configurations without a replayed game: {missing}")
    shadows_public: Dict[str, Any] = {}
    classes: Dict[str, Dict[str, Any]] = {name: {} for name in SHADOWS}
    for config in ms.CONFIGS:
        f = new.get(config)
        if f is None:
            continue
        p = private[f["game"]]
        observed = p["observed_fire"]
        block = {"game_id": f["game"], "risk_window_end_decision": f["window_end"],
                 "risk_window_basis": ("the latest of the historical firing anchors and the new game's direct-fire "
                                       "listings and orders") if config in ms.FIRE_CONFIGS else
                 "v3's first ownership of the problem objective in the new game (the last decision if never)",
                 "shadows": {}}
        for name in SHADOWS:
            c = classify(config, f, p, name)
            classes[name][config] = c
            policy = p["policies"][name]
            block["shadows"][name] = {
                "identity": sh.identity(name), "classification": c,
                "first_divergence": public_certificate(policy["fsd"], p["names"], f["window_end"], config, observed),
                "trigger_exposure": exposure_summary(policy, f["window_end"]),
                "off_policy": off_policy_summary(policy),
                "memory_bounds": {"checks": policy["memory_checks"], "problems": policy["memory_problems"]},
                "recourse": ms.recourse([p["trackers"][name]])}
        shadows_public[config] = block
    primary = sorted((f for f in facts.values() if f["kind"] == "primary"), key=lambda f: f["game"])
    reference = {seat: {(f["game"], u) for f in primary if f["cell"] == seat for u in private[f["game"]]["reference"]}
                 for seat in ("H1", "H2")}
    restoration_public: Dict[str, Any] = {}
    for name in SHADOWS:
        redirected = {seat: {(f["game"], u) for f in primary if f["cell"] == seat
                             for u in private[f["game"]]["policies"][name]["restored_candidates"]}
                      for seat in ("H1", "H2")}
        r3 = ms.restoration(reference, redirected)
        r4_primary = ms.recourse([private[f["game"]]["trackers"][name] for f in primary])
        r4_new = ms.recourse([private[f["game"]]["trackers"][name] for f in new.values()])
        restoration_public[name] = {"identity": sh.identity(name), "R3_distinct_unit_restoration": r3,
                                    "R4_recourse_primary": r4_primary, "R4_recourse_new_captures_off_policy": r4_new,
                                    "R4_pass": r4_primary["pass"] and r4_new["pass"]}
    if primary and not all(restoration_public[SHADOWS[0]]["R3_distinct_unit_restoration"]["reference_reproduced"]
                           .values()):
        problems.append("the primary reference units (T9-v1's post-opening redirected units) were not reproduced")
    if len(primary) != 4:
        problems.append(f"expected 4 primary games, replayed {len(primary)}")
    target = classes[sh.TARGET]
    verdict = ms.disposition(problems, target if not problems else {})
    disposition_public = {
        "schema": ms.SCHEMA, "note": NOTE, "target": sh.TARGET, "target_identity": sh.identity(sh.TARGET),
        "classes": {c: target[c]["class"] for c in sorted(target)},
        "sublabels": {c: target[c]["sublabel"] for c in sorted(target)},
        "disposition": verdict,
        "target_restoration_and_recourse": {
            "R3_pass": restoration_public[sh.TARGET]["R3_distinct_unit_restoration"]["pass"],
            "R4_pass": restoration_public[sh.TARGET]["R4_pass"],
            "note": "reported with their frozen values; they do not enter the Sprint 16 disposition"},
        "other_shadows": {n: {c: classes[n][c]["class"] for c in sorted(classes[n])} for n in SHADOWS
                          if n != sh.TARGET},
        "problems": problems[:50],
        "statement": "the disposition concerns the target shadow's first divergence on three observed v3 "
                     "trajectories; it authorizes no engine use and returns to the owner"}
    base = {"schema": ms.SCHEMA, "note": NOTE, "inputs_sha256": sha256(INPUTS)}
    return {
        "games": {**base, "card": {"id": ms.CARD_ID, "canonical_sha256": mf.digest(the_card)},
                  "ledger": {"sessions_after_base": ledger["sessions"], "unclosed": ledger["unclosed"],
                             "ok": ledger["ok"], "sessions": sorted(int(s) for s in ledger["games"].values())},
                  "games": games_public},
        "shadows": {**base, "evidence_boundary": ms.__doc__.split("Evidence boundary. ")[1].strip(),
                    "target": sh.TARGET, "configurations": shadows_public},
        "restoration": {**base, "reference": {seat: len(units) for seat, units in reference.items()},
                        "thresholds": {"restoration_required": ms.RULES["restoration_required"],
                                       "recourse_per_episode_max": ms.RULES["recourse_per_episode_max"]},
                        "shadows": restoration_public},
        "disposition": {**base, **disposition_public},
    }


def private_values(results) -> Set[Any]:
    values: Set[Any] = set()
    for _, p in results:
        values.update(int(c) for c in p["names"])
        if p["problem"] is not None:
            values.add(p["problem"])
    return values


def public_texts(public: Mapping[str, Any], results) -> Dict[str, str]:
    hidden = private_values(results)
    texts = {}
    for name, data in public.items():
        found = ms.public_check(data, hidden)
        if found:
            raise SystemExit(f"refused: {name}.json would publish private values: {found[:5]}")
        text = dump(data)
        if ms.V3_ID in text or ms.V3_DIGEST in text:
            raise SystemExit(f"refused: {name}.json names the v3 identity outside the card (whitelist)")
        texts[name] = text
    return texts


# ------------------------------------------------------------------------------------------------
# Game facts and the ledger (read only)


def game_facts_of(entry: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    record_path = WORK / "games" / f"{entry['game_id']}.json"
    if not record_path.exists():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    paths = capture_files(WORK, entry["game_id"])
    if any(not p.exists() for p in paths.values()):
        return {"stops": {"S7": ["capture files missing"]}, "session": record.get("session"),
                "status": record.get("status"), "steps": record.get("steps")}
    recorded = record.get("capture") or {}
    digests = {name: (recorded.get(name), sha256(path)) for name, path in paths.items()}
    with paths["timeline.pkl"].open("rb") as handle:
        windows = pickle.load(handle)
    the_card = card()
    facts = tl.analyze(entry, ms.CARD_ID, record, json.loads(paths["t9.json"].read_text(encoding="utf-8")),
                       json.loads(paths["v3.json"].read_text(encoding="utf-8")),
                       json.loads(paths["timeline.json"].read_text(encoding="utf-8")), windows,
                       costs_of(the_card, WORK, entry["scenario_id"]), capture_digests=digests)
    facts["session"] = record.get("session")
    return facts


def ledger_audit() -> Dict[str, Any]:
    path = REPO_ROOT / "local" / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return ms.ledger_audit(records, card())


def replay_safe(job: Tuple[str, str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """A new game whose captures cannot be replayed is a capture failure, recorded as a problem, never a crash that
    hides the other games; the historical streams are pinned and must replay."""
    if job[0] != "new":
        return replay(job)
    try:
        return replay(job)
    except Exception as exc:  # noqa: BLE001
        message = f"{type(exc).__name__}: {exc}"[:300]
        facts = {"kind": "invalid", "game": job[1], "cell": None, "configuration": None,
                 "problems": [f"the captures could not be replayed: {message}"]}
        return facts, {"game": job[1], "names": {}, "problem": None, "policies": {}, "trackers": {}}


def game_facts_job(entry: Mapping[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    return entry["game_id"], game_facts_of(entry)


# ------------------------------------------------------------------------------------------------
# Commands


ANCHORS: Dict[str, Any] = {}


def primary_jobs(kind: str) -> List[Tuple[str, str, Any]]:
    return [(kind, g["game_id"], g["cell"]) for g in S14.primary_games()]


def run(args: argparse.Namespace) -> int:
    require_inputs()
    ANCHORS.update(anchors())
    the_card = card()
    jobs = [("new", g["game_id"], None) for g in the_card["games"]
            if (WORK / "games" / f"{g['game_id']}.json").exists()] + primary_jobs("primary")
    with multiprocessing.get_context("fork").Pool(args.workers) as pool:
        results = pool.map(replay_safe, jobs, chunksize=1)
        game_facts = dict(pool.map(game_facts_job, the_card["games"], chunksize=1))
    public = combine(results, game_facts, ledger_audit())
    texts = public_texts(public, results)
    if args.check:
        bad = [n for n, t in texts.items() if (OUT_DIR / f"{n}.json").read_text(encoding="utf-8") != t]
        print("OK: public files regenerate byte for byte" if not bad else f"MISMATCH: {bad}")
        return 1 if bad else 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (OUT_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with gzip.open(PRIVATE / "analysis-private.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"anchors": ANCHORS, "results": [{"facts": f, "private": {k: v for k, v in p.items()
                                                                           if k != "trackers"},
                                                   "episodes": {n: t.episodes() for n, t in p["trackers"].items()}}
                                                  for f, p in results]}, handle, sort_keys=True, default=str)
    print(json.dumps(public["disposition"]["disposition"], indent=1))
    print(json.dumps(public["disposition"]["classes"], indent=1))
    return 0


def rehearse(args: argparse.Namespace) -> int:
    """The new-game path on the four real Sprint 12 v3 captures (format-identical stand-ins), plus the primary path."""
    ANCHORS.update(anchors())
    problems = anchor_problems(ANCHORS)
    started = time.perf_counter()
    with multiprocessing.get_context("fork").Pool(args.workers) as pool:
        results = pool.map(replay, primary_jobs("rehearsal") + primary_jobs("primary"), chunksize=1)
    seconds = round(time.perf_counter() - started, 1)
    out = {"anchors": public_anchors(ANCHORS), "anchor_problems": problems, "wall_seconds": seconds, "games": []}
    primary = [(f, p) for f, p in results if f["kind"] == "primary"]
    for f, p in results:
        row = {"kind": f["kind"], "game": f["game"], "cell": f["cell"], "decisions": f["decisions"],
               "active_decisions": f["active_decisions"], "counts": f["counts"], "problems": f["problems"][:5],
               "seconds": f["seconds"], "fire": f["fire"], "retargeting": f["retargeting"], "shadows": {}}
        for name in SHADOWS:
            policy = p["policies"][name]
            fsd = policy["fsd"]
            row["shadows"][name] = {"first_divergence_decision": fsd["k"] if fsd else None,
                                    "first_divergence_ordinal": fsd["ordinal"] if fsd else None,
                                    "first_divergence_redirects": len(fsd["redirects"]) if fsd else 0,
                                    "first_divergence_changed_units": len(fsd["changed"]) if fsd else 0,
                                    "exposure": exposure_summary(policy, f["decisions"] - 1),
                                    "off_policy": off_policy_summary(policy),
                                    "recourse": ms.recourse([p["trackers"][name]])}
            if f["kind"] == "rehearsal" and fsd is not None:
                # the classifier exercised on real first divergences with the game's own fire as the window (plumbing)
                observed = p["observed_fire"]
                row["shadows"][name]["plumbing_fire_class"] = ms.classify_fire(
                    "1930331196 C3", fsd_input(fsd), max([0] + [d for v in observed.values() for d in v]), {},
                    observed)["class"]
                row["shadows"][name]["plumbing_reservation_flags"] = sorted(
                    {flag for r in fsd["redirects"] for flag in ms.reservation_flags(
                        {**r, "before_first_ownership": True, "capturer_without_place": False})})
        out["games"].append(row)
    reference = {seat: {(f["game"], u) for f, p in primary if f["cell"] == seat for u in p["reference"]}
                 for seat in ("H1", "H2")}
    out["restoration"] = {}
    for name in SHADOWS:
        redirected = {seat: {(f["game"], u) for f, p in primary if f["cell"] == seat
                             for u in p["policies"][name]["restored_candidates"]} for seat in ("H1", "H2")}
        out["restoration"][name] = {"R3": ms.restoration(reference, redirected),
                                    "R4": ms.recourse([p["trackers"][name] for _, p in primary])}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "rehearsal.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n",
                                            encoding="utf-8", newline="\n")
    print(json.dumps({"wall_seconds": seconds, "anchor_problems": problems,
                      "problems": {g["game"] + ":" + g["kind"]: len(g["problems"]) for g in out["games"]}}, indent=1))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("freeze", "rehearse", "run"):
        p = sub.add_parser(command)
        p.add_argument("--check", action="store_true")
        p.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    if args.command == "freeze":
        text = dump(build_inputs())
        if args.check:
            same = INPUTS.read_text(encoding="utf-8") == text
            print("OK" if same else "MISMATCH")
            return 0 if same else 1
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {INPUTS.relative_to(REPO_ROOT).as_posix()}")
        return 0
    return rehearse(args) if args.command == "rehearse" else run(args)


if __name__ == "__main__":
    sys.exit(main())
