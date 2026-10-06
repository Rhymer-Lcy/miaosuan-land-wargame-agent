"""Sprint 17 first-divergence probe: the frozen analysis (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``), server only.

    python scripts/s17_analysis.py freeze [--check]   # inputs.json and the private prefix reference, before session 2794
    python scripts/s17_analysis.py rehearse           # pre-engine replay of the executable candidate, private output
    python scripts/s17_analysis.py run [--check]      # after the two sessions: the public files

``freeze`` reads Sprint 16's frozen v3 games of 1930331196 C2 and 2120531121 C3 (pinned by SHA-256) and derives, with
the Sprint 16 target shadow, the prefix reference: the digests of v3's emitted actions and of the corrected-memory chain
up to the registered first divergence, the registered first-divergence actions, units and routes, the protected
direct-fire unit of 1930331196 C2, the problem objective and the two decision-361 units of 2120531121 C3, and v3's
first ownership of every objective. The reference is private (``local/diagnostics/s17/prefix-reference.json``, unit
ids and hexes); ``inputs.json`` publishes its digest, the input digests, the card digest, the candidate identity and the
anchors as decisions and counts.

``rehearse`` plays the executable candidate's agent (``PostStageAnyV6Agent``) over every recorded decision of the three
Sprint 16 games and requires: the candidate equals frozen v3 before the registered divergences (in 1930331196 C3 for the
whole game), produces exactly the registered first divergences, carries exactly the corrected-memory chain, equals the
Sprint 16 target shadow (actions and memory) at every recorded decision, and that the Sprint 17 observer's
reconstruction and consistency checks pass on every decision; it then runs this analysis's replay on the two Sprint 16
games as stand-ins (known answers: the fire endpoints of v3's own game hold, the problem objective is first owned at
564, the live-versus-candidate difference begins exactly at the divergence). Its output is private
(``local/diagnostics/s17/rehearsal.json``); exit status 1 if any requirement fails. It opens no engine.

``run`` requires the pins and the two recorded games, re-derives every candidate decision and its memory from the
seat's own observations, checks the prefix, evaluates the registered endpoints, classifies both configurations, decides
the disposition, and writes ``games.json``, ``mechanism.json`` and ``disposition.json`` under
``evaluation/s17-first-divergence-probe/``; ``--check`` regenerates them in memory and compares byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
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
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s13_diagnosis as sd  # noqa: E402
from miaosuan_agent.evaluation import s14_design as sx  # noqa: E402
from miaosuan_agent.evaluation import s15_delayed as s15  # noqa: E402
from miaosuan_agent.evaluation import s16_mechanism as ms  # noqa: E402
from miaosuan_agent.evaluation import s16_shadow as sh  # noqa: E402
from miaosuan_agent.evaluation import s17_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s17_probe as sp  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments import t9_delayed as td  # noqa: E402
from miaosuan_agent.experiments import t9_post_stage_v6 as c6  # noqa: E402
from miaosuan_agent.experiments import t9_redistribution as tr  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s17_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CARDS = load("build_s17_card")

SCHEMA_INPUTS = "miaosuan-s17-inputs/1"
OUT_DIR = REPO_ROOT / "evaluation" / sp.STUDY_ID
INPUTS = OUT_DIR / "inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s17"
REFERENCE = PRIVATE / "prefix-reference.json"
WORK = REPO_ROOT / "local" / "evaluation" / sp.CARD_ID
SOURCE_WORK = REPO_ROOT / "local" / "evaluation" / sp.SOURCE_CARD
SOURCE_CARD = REPO_ROOT / "evaluation" / sp.SOURCE_CARD / "manifest.json"
SOURCE_CAPTURES = ("t9.json", "v3.json", "v3series.json.gz", "timeline.json", "timeline.pkl")
CAPTURES = ("t9.json", "explore.json", "exploreseries.json.gz", "timeline.json", "timeline.pkl")
SOURCE_C3 = "1930331196.C3.s16-v3-mechanism-capture-1.p01"  # rehearsal only: the target never diverges there
PUBLIC_FILES = ("games", "mechanism", "disposition")
KIND = {1: "infantry", 2: "vehicle", 3: "aircraft"}  # decision.routing: INFANTRY, VEHICLE, AIRCRAFT
NOTE = ("mechanism probe: the executable candidate played its seat in two games against the inert control. Every figure "
        "is a fact of the observed trajectory; nothing here is a score estimate, a performance comparison or evidence of "
        "an effect, and one game per configuration shows one observed trajectory. Record scores are reported for audit "
        "and enter no rule")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(data: Any) -> str:
    return sp.dump(data)


def tree_digest(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(path.relative_to(folder).as_posix().encode("utf-8") + b"\0" + sha256(path).encode("ascii") + b"\0")
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------
# Streams


def source_card() -> Dict[str, Any]:
    return json.loads(SOURCE_CARD.read_text(encoding="utf-8"))


def card() -> Dict[str, Any]:
    return json.loads(CARDS.CARD.read_text(encoding="utf-8"))


def files_of(work: Path, game_id: str, names: Sequence[str]) -> Dict[str, Path]:
    return {name: work / "capture" / f"{game_id}.{name}" for name in names}


def inputs_of(the_card: Mapping[str, Any], work: Path, scenario: str):
    map_id = next(s["map_id"] for s in the_card["scenarios"] if s["scenario_id"] == scenario)
    return sdk_data.load_inputs(work / "data" / scenario / "Data", scenario, map_id)


def costs_of(the_card: Mapping[str, Any], work: Path, scenario: str) -> MoveCosts:
    return MoveCosts.from_raw(inputs_of(the_card, work, scenario).cost, Origin.ENGINE, "setup_info.cost_data")


def stream(record: Mapping[str, Any], timeline: Mapping[str, Any], windows: Mapping[str, Any], policy: str):
    """The seat playing ``policy``: its rows (raw observation, memory carried into the decision, emitted actions),
    its states (decisions 0..N-1 and the final one) and the timeline's step log."""
    seat = next(s["seat"] for s in record["seats"] if s["policy"] == policy)
    faction = next(s["faction"] for s in record["seats"] if s["policy"] == policy)
    states, raws = tl.load_states(windows, seat, faction)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    memories = [pickle.loads((s["seats"].get(seat) or s["seats"].get(str(seat)))["memory"]) for s in samples]
    steps = timeline["steps"]
    if not (len(steps) == len(raws) == len(memories)):
        raise ValueError("the timeline's step log, snapshots and memories differ in length")
    rows = [{"k": k, "raw": raws[k], "memory": memories[k],
             "submitted": [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == seat]}
            for k in range(len(steps))]
    return seat, faction, rows, states, steps


def load_game(work: Path, game_id: str, names: Sequence[str]):
    record = json.loads((work / "games" / f"{game_id}.json").read_text(encoding="utf-8"))
    paths = files_of(work, game_id, names)
    timeline = json.loads(paths["timeline.json"].read_text(encoding="utf-8"))
    with paths["timeline.pkl"].open("rb") as handle:
        windows = pickle.load(handle)
    return record, timeline, windows, paths


def listed_types(raw: Mapping[str, Any], unit: Any) -> Set[int]:
    listed = raw.get("valid_actions") or {}
    entry = listed.get(unit)
    if entry is None:
        entry = listed.get(str(unit)) or {}
    return {int(t) for t in entry}


def names_of(raw: Mapping[str, Any]) -> Dict[Any, str]:
    return tl.labels({c["coord"]: c.get("value") for c in (raw.get("cities") or ())})


def ownership(states: Sequence[Any], faction: int, decisions: int, names: Mapping[Any, str]) -> Dict[str, Any]:
    """First ownership of every objective by decision (the first decision whose observed state shows it own) and by
    step, and the number of flag transitions."""
    out = {}
    for coord, label in sorted(names.items(), key=lambda i: i[1]):
        k = sp.first_ownership([states[j].flags for j in range(decisions)], coord, faction)
        flags = [states[j].flags.get(coord) for j in range(len(states))]
        out[label] = {"first_ownership_decision": k, "first_ownership_step": None if k is None else states[k].cur_step,
                      "own_at_end": states[-1].flags.get(coord) == faction,
                      "transitions": sum(1 for a, b in zip(flags, flags[1:]) if a != b)}
    return out


# ------------------------------------------------------------------------------------------------
# Freeze: the prefix reference from Sprint 16's v3 games


def reference_for(config: str) -> Dict[str, Any]:
    game_id = sp.SOURCE_GAMES[config]
    the_card = source_card()
    entry = next(g for g in the_card["games"] if g["game_id"] == game_id)
    record, timeline, windows, _ = load_game(SOURCE_WORK, game_id, SOURCE_CAPTURES)
    seat, faction, rows, states, steps = stream(record, timeline, windows, tb.CANDIDATE_ID)
    costs = costs_of(the_card, SOURCE_WORK, entry["scenario_id"])
    names = names_of(rows[0]["raw"])
    memory: Tuple[Tuple[int, int], ...] = ()
    v3_actions, memory_in, observations = [], [], []
    out: Dict[str, Any] = {"source_game": game_id, "seat_faction": faction}
    for row in rows:
        k = row["k"]
        observation = Observation.from_raw(row["raw"], Origin.ENGINE)
        policy = ShootReservationPolicy(costs)
        base = policy.decide(observation, seat, faction, row["memory"].baseline)
        v3 = tb.allocate(observation, seat, faction, base.actions, policy.router)
        if rd.plain(v3.actions) != row["submitted"]:
            raise SystemExit(f"refused: {config} k{k}: v3 re-decided differs from the Sprint 16 capture")
        target = sh.allocate(observation, seat, faction, base.actions, policy.router, sh.RULES[sh.TARGET], memory)
        memory_in.append(sp.memory_digest(memory))
        v3_actions.append(sp.actions_digest(row["submitted"]))
        observations.append(sp.canonical_sha256(row["raw"]))
        if ms.diverges(row["submitted"], target.actions):
            redirected = dict(target.redirected)
            out.update(divergence=k, expected_actions=sp.actions_digest(rd.plain(target.actions)),
                       changed=cap.changed_units(row["submitted"], rd.plain(target.actions)),
                       redirects={str(u): [o.objective, list(o.path)] for u, o in sorted(redirected.items())},
                       redirect_kinds=sorted(sx.own_ground(observation, faction)[u].unit_type for u in redirected),
                       destination_labels=sorted({names[o.objective] for o in redirected.values()}))
            memory_in.append(sp.memory_digest(target.memory))
            break
        memory = target.memory
    else:
        raise SystemExit(f"refused: {config}: the target shadow never diverges on the Sprint 16 game")
    out.update(v3_actions=v3_actions, memory_in=memory_in, observations=observations)
    k = out["divergence"]
    if k != sp.RULES["first_divergence"][config] or len(out["changed"]) != sp.RULES[
            "first_divergence_redirected_vehicles"][config] or set(out["redirect_kinds"]) != {2} \
            or sorted(map(str, out["changed"])) != sorted(out["redirects"]):
        raise SystemExit(f"refused: {config}: the Sprint 16 first divergence is not the registered one: {k}")
    out["first_ownership"] = ownership(states, faction, len(rows), names)
    if config == sp.C2:
        units = {}
        endpoints = {}
        for d in sp.RULES["protected_fire_decisions"]:
            orders = [a for a in rows[d]["submitted"] if a.get("type") == sp.SHOOT]
            if len(orders) != 1:
                raise SystemExit(f"refused: decision {d} of the Sprint 16 C2 game has {len(orders)} direct-fire orders")
            units[d] = orders[0]["obj_id"]
            endpoints[d] = sp.fire_endpoint(d, units[d], listed_types(rows[d]["raw"], units[d]),
                                            [(a, tl.response(steps[d], seat, a)) for a in rows[d]["submitted"]])
        if len(set(units.values())) != 1 or not all(e["preserved"] for e in endpoints.values()):
            raise SystemExit(f"refused: the protected fire mechanism of the Sprint 16 C2 game is not one unit's, "
                             f"listed, emitted and accepted: {endpoints}")
        out["protected_unit"] = units[sp.RULES["protected_fire_decisions"][0]]
        out["protected_unit_kind"] = next(u.get("type") for u in rows[0]["raw"].get("operators") or ()
                                          if u.get("obj_id") == out["protected_unit"])
        out["reference_fire_endpoints"] = {str(d): e for d, e in endpoints.items()}
    else:
        problem = next(c for c, label in names.items() if label == sp.RULES["problem_objective"])
        first = out["first_ownership"][sp.RULES["problem_objective"]]["first_ownership_decision"]
        if first != sp.RULES["first_ownership_deadline"]:
            raise SystemExit(f"refused: v3 first owned the problem objective at {first} in the Sprint 16 game")
        if {r[0] for r in out["redirects"].values()} != {problem}:
            raise SystemExit("refused: the registered 2120531121 C3 redirects do not go to the problem objective")
        out["problem_objective"] = problem
        out["early_units"] = sorted(out["changed"])
        out["v3_capturers"] = sorted(u for u, position in states[first].units.items() if position[0] == problem)
        if not out["v3_capturers"]:
            raise SystemExit("refused: no unit stood on the problem objective at v3's first ownership")
    return out


def build_reference() -> Dict[str, Any]:
    return {"schema": "miaosuan-s17-prefix-reference/1", "configs": {c: reference_for(c) for c in sp.CONFIGS}}


def public_anchor(config: str, ref: Mapping[str, Any]) -> Dict[str, Any]:
    out = {"source_game": ref["source_game"], "first_divergence_decision": ref["divergence"],
           "redirected_vehicles": len(ref["changed"]), "redirect_destination": ref["destination_labels"],
           "v3_first_ownership": {label: row["first_ownership_decision"] for label, row in
                                  ref["first_ownership"].items()}}
    if config == sp.C2:
        out["protected_fire_decisions"] = sp.RULES["protected_fire_decisions"]
        out["protected_unit_kind"] = KIND.get(ref["protected_unit_kind"], "other")
        out["reference_fire_endpoints"] = {d: {k: v for k, v in e.items() if k != "decision"}
                                           for d, e in ref["reference_fire_endpoints"].items()}
    else:
        out["problem_objective"] = sp.RULES["problem_objective"]
        out["first_ownership_deadline"] = sp.RULES["first_ownership_deadline"]
    return out


def build_inputs(reference_text: str) -> Dict[str, Any]:
    card_text = CARDS.CARD.read_text(encoding="utf-8")
    if card_text != sp.dump(CARDS.build()):
        raise SystemExit("refused: the committed card does not rebuild byte-identically")
    the_card = json.loads(card_text)
    reference = json.loads(reference_text)
    source = source_card()
    games = {}
    for config in sp.CONFIGS:
        gid = sp.SOURCE_GAMES[config]
        files = {name: sha256(p) for name, p in files_of(SOURCE_WORK, gid, SOURCE_CAPTURES).items()}
        files["record"] = sha256(SOURCE_WORK / "games" / f"{gid}.json")
        games[config] = {"game_id": gid, "files": files}
    scenarios = sorted({g["scenario_id"] for g in source["games"]})
    candidate = the_card["policies"][sp.CANDIDATE_ID]["policy_source"]
    return {"schema": SCHEMA_INPUTS, "card": {"id": sp.CARD_ID, "canonical_sha256": mf.digest(the_card)},
            "candidate": {"id": sp.CANDIDATE_ID, "policy_source_sha256": candidate["sha256"],
                          "files": candidate["files"]},
            "rules": sp.RULES, "rules_sha256": sp.rules_digest(),
            "source": {"card": sp.SOURCE_CARD, "canonical_sha256": mf.digest(source), "games": games,
                       "cost_data": {s: tree_digest(SOURCE_WORK / "data" / s) for s in scenarios}},
            "prefix_reference_sha256": hashlib.sha256(reference_text.encode("utf-8")).hexdigest(),
            "anchors": {c: public_anchor(c, reference["configs"][c]) for c in sp.CONFIGS},
            "note": "inputs pinned before session 2794; the prefix reference and every capture stay under the ignored "
                    "local/ tree"}


def require_inputs() -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    reference_text = REFERENCE.read_text(encoding="utf-8")
    if dump(build_reference()) != reference_text:
        raise SystemExit("refused: the prefix reference does not regenerate from the Sprint 16 games")
    committed = INPUTS.read_text(encoding="utf-8")
    if dump(build_inputs(reference_text)) != committed:
        raise SystemExit("refused: an input, an identity or a threshold differs from inputs.json")
    return json.loads(committed), json.loads(reference_text)


# ------------------------------------------------------------------------------------------------
# The replay of one game


def certificate_of(k: int, ordinal: int, observation: Observation, seat: int, faction: int,
                   base_actions: Sequence[Mapping[str, Any]], v3: tb.Allocation, alloc: td.Allocation,
                   before: Sequence[Sequence[int]], costs: MoveCosts, names: Mapping[Any, str],
                   problem: Optional[Any]) -> Dict[str, Any]:
    """The first divergence of the candidate from the stage-1 allocator on its own trajectory (private), with Sprint
    14's independent checks of every redirect."""
    checks = sx.candidate_checks(observation, seat, faction, base_actions, alloc.actions, alloc, v3, costs)
    ground = sx.own_ground(observation, faction)
    cities = {c.coord for c in (observation.cities() or ())}
    base_moves, v3_moves, out_moves = (sx.ground_moves(base_actions, ground), sx.ground_moves(v3.actions, ground),
                                       sx.ground_moves(alloc.actions, ground))
    rows_by_unit = {r["unit"]: r for r in checks["redirects"]}
    redirects = []
    for unit, option in sorted(alloc.redirected.items()):
        claimant = alloc.claimants[unit]
        row = rows_by_unit.get(unit, {})
        redirects.append({"unit": unit, "kind": ground[unit].unit_type if unit in ground else None,
                          "source": claimant.objective, "alternative": option.objective,
                          "route": list(option.path), "route_cost": option.cost, "own_cost": option.base_cost,
                          "free_flow": row.get("free_flow"), "v3_form": sx.form(base_moves[unit], v3_moves.get(unit),
                                                                                cities),
                          "candidate_form": sx.form(base_moves[unit], out_moves.get(unit), cities),
                          "to_problem_objective": problem is not None and option.objective == problem})
    changed = cap.changed_units(rd.plain(v3.actions), rd.plain(alloc.actions))
    return {"k": k, "cur_step": observation.time().cur_step, "ordinal": ordinal, "changed": changed,
            "changed_kinds": sorted(ground[u].unit_type for u in changed if u in ground),
            "redirects": redirects, "violations": dict(sorted((a, b) for a, b in checks["violations"].items() if b)),
            "memory_records_before": len(td.decode(before)[0])}


def analyze_game(config: str, record: Mapping[str, Any], timeline: Mapping[str, Any], windows: Mapping[str, Any],
                 costs: MoveCosts, reference: Mapping[str, Any], policy: str, rehearsal: bool = False
                 ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Re-derive every decision of the seat playing ``policy`` from its own observations: baseline-v2 (with the
    recorded baseline memory, whose chain is checked), the stage-1 allocator and the candidate with its own memory
    chain from an empty memory. In a probe game the candidate must equal the live decision and the live memory at
    every decision. ``rehearsal``: a Sprint 16 v3 game as a stand-in (the live seat is v3, so the live memory is not
    the candidate's and differences after the divergence are expected)."""
    started = time.perf_counter()
    seat, faction, rows, states, steps = stream(record, timeline, windows, policy)
    ref = reference["configs"][config]
    names = names_of(rows[0]["raw"])
    problem = ref.get("problem_objective")
    early = set(ref.get("early_units") or ())
    first_own = None if problem is None else sp.first_ownership([states[j].flags for j in range(len(rows))],
                                                                problem, faction)
    counts = collections.Counter()
    problems: List[str] = []
    differences: List[int] = []
    memory: Tuple[Tuple[int, int], ...] = ()
    tracker = ms.EpisodeTracker()
    redirects: List[Dict[str, Any]] = []
    fsd: Optional[Dict[str, Any]] = None
    ordinal = 0
    max_records, ended = 0, collections.Counter()
    exposure = 0
    fire = {"listing_decisions": 0, "orders": 0, "responses": collections.Counter(), "order_decisions": []}
    audit: List[Dict[str, Any]] = []
    survival: Dict[Any, Dict[str, Any]] = {u: {"counted_decisions": 0, "lost_before_ownership": False,
                                               "present_at_ownership": None, "on_objective_at_ownership": None}
                                           for u in early}
    live_memory = [cap.split_memory(row["memory"]) for row in rows]
    for row in rows:
        k, raw = row["k"], row["raw"]
        observation = Observation.from_raw(raw, Origin.ENGINE)
        base_memory, live_addon = live_memory[k]
        policy_v2 = ShootReservationPolicy(costs)
        base = policy_v2.decide(observation, seat, faction, base_memory)
        if k + 1 < len(rows) and base.memory != live_memory[k + 1][0]:
            problems.append(f"k{k}: baseline-v2's next memory differs from the recorded one")
        v3 = tb.allocate(observation, seat, faction, base.actions, policy_v2.router)
        before = memory
        alloc = c6.allocate(observation, seat, faction, base.actions, policy_v2.router, before)
        counts["decisions"] += 1
        if not rehearsal:
            counts["memory_compared"] += 1
            if tuple(live_addon) != tuple(before):
                problems.append(f"k{k}: the live memory differs from the re-derived candidate memory")
        if rd.plain(alloc.actions) != row["submitted"]:
            differences.append(k)
        found = s15.memory_problems(observation, faction, alloc.memory)
        if found:
            problems.append(f"k{k}: memory: {found[:2]}")
        records = td.decode(alloc.memory)[0]
        max_records = max(max_records, len(records))
        ended.update(alloc.ended.values())
        play = observation.time().stage == Stage.PLAY
        ground = sx.own_ground(observation, faction)
        cities = {c.coord: c for c in (observation.cities() or ())}
        active = play and bool(sx.ground_moves(base.actions, ground))
        if active:
            ordinal += 1
        if play:
            tracker.before({u: (g.cur_hex, tuple(g.move_path or ())) for u, g in ground.items()},
                           {c: city.flag for c, city in cities.items()}, faction)
        if alloc.eligible:
            exposure += len(alloc.eligible)
        if active:
            claimants = {u: (c.objective, c.status == tr.FULL, u in alloc.selected) for u, c in alloc.claimants.items()}
            tracker.after(k, claimants, {u: o.objective for u, o in alloc.redirected.items()})
        elif ms.diverges(v3.actions, alloc.actions):
            problems.append(f"k{k}: the candidate changed a decision without own ground moves")
        if alloc.redirected:
            checks = sx.candidate_checks(observation, seat, faction, base.actions, alloc.actions, alloc, v3, costs)
            clean = not any(checks["violations"].values())
            for unit, option in sorted(alloc.redirected.items()):
                redirects.append({"k": k, "unit": unit, "from": alloc.claimants[unit].objective,
                                  "to": option.objective, "kind": ground[unit].unit_type if unit in ground else None,
                                  "clean": clean, "free_flow": option.free_flow,
                                  "detour": round(option.cost / option.base_cost, 4) if option.base_cost else None})
        if fsd is None and ms.diverges(v3.actions, alloc.actions):
            fsd = certificate_of(k, ordinal, observation, seat, faction, base.actions, v3, alloc, before, costs,
                                 names, problem)
        # direct fire of the seat (any unit kind)
        if any(sp.SHOOT in {int(t) for t in (v or {})} for v in (raw.get("valid_actions") or {}).values()):
            fire["listing_decisions"] += 1
        shots = [a for a in row["submitted"] if a.get("type") == sp.SHOOT]
        if shots:
            fire["order_decisions"].append(k)
        for action in shots:
            fire["orders"] += 1
            fire["responses"][tl.response(steps[k], seat, action)] += 1
        # 2120531121 C3: the pre-capture audit, from the registered divergence to first ownership
        if problem is not None and k >= ref["divergence"] and (first_own is None or k < first_own):
            counted, _ = sd.counted_incumbents(observation, faction, policy_v2.router)
            row_p = counted.get(problem, {})
            physical_units = {u for u, g in ground.items() if not g.move_path and g.cur_hex == problem}
            movers = set(row_p.get("mover_bounds", {}))
            places = physical_units | movers
            if len(physical_units) != row_p.get("physical", 0):
                problems.append(f"k{k}: physical incumbents of the problem objective miscounted")
            info = v3.objectives.get(problem)
            if info is not None and (info["physical"] + info["movers"] != len(places)
                                     or set(info["mover_bounds"]) != movers):
                problems.append(f"k{k}: the audit's counted places differ from the stage-1 allocator's")
            early_here = places & early
            later_here = {u for u in places - early if any(r["unit"] == u and r["to"] == problem
                                                          for r in redirects if r["k"] < k)}
            for u in early:
                survival[u]["counted_decisions"] += int(u in early_here)
                if u not in ground and not survival[u]["lost_before_ownership"]:
                    survival[u]["lost_before_ownership"] = True
            claims = [c for c in alloc.claimants.values() if c.objective == problem]
            if claims:
                base_paths = {a.get("obj_id"): tuple(a.get("move_path") or ())
                              for a in base.actions if a.get("type") == sp.MOVE}
                out_paths = {a.get("obj_id"): tuple(a.get("move_path") or ())
                             for a in alloc.actions if a.get("type") == sp.MOVE}
                rows_in = [{"unit": c.obj_id, "feasible": c.status == tr.FULL, "key": list(tb.free_flow_key(c)),
                            "form": sp.form(base_paths.get(c.obj_id), out_paths.get(c.obj_id),
                                            c.obj_id in alloc.redirected)} for c in claims]
                selected = [u for u, coord in alloc.selected.items() if coord == problem]
                try:
                    found_rows = sp.early_place_rows(rows_in, len(places), len(early_here), selected)
                    later_rows = sp.early_place_rows(rows_in, len(places), len(early_here) + len(later_here), selected)
                except ValueError as exc:
                    problems.append(f"k{k}: early-place audit: {exc}")
                    found_rows, later_rows = [], []
                by_unit = {c.obj_id: c for c in claims}
                for r, later in zip(found_rows, later_rows):
                    c = by_unit[r["unit"]]
                    audit.append({**r, "k": k, "cur_step": observation.time().cur_step,
                                  "can_arrive": c.status == tr.FULL, "status": c.status, "free_flow": c.free_flow,
                                  "kind": ground[c.obj_id].unit_type if c.obj_id in ground else None,
                                  "counted_places": len(places), "early_places": len(early_here),
                                  "other_redirect_places": len(later_here),
                                  "placed_without_any_redirect_places": later["placed_without_early_places"],
                                  "redirect_place_block": later["early_place_block"]})
        memory = alloc.memory
    capturers: Dict[str, Dict[str, Any]] = {}
    if problem is not None:
        for u in ref.get("v3_capturers") or ():
            mine = [r for r in audit if r["unit"] == u]
            position = None if first_own is None else states[first_own].units.get(u)
            capturers[str(u)] = {"kind": next((x.get("type") for x in rows[0]["raw"].get("operators") or ()
                                              if x.get("obj_id") == u), None),
                                 "claim_decisions": len(mine),
                                 "forms": dict(sorted(collections.Counter(r["form"] for r in mine).items())),
                                 "early_place_blocks": sum(1 for r in mine if r["early_place_block"]),
                                 "on_objective_at_ownership": position is not None and position[0] == problem}
    if problem is not None and first_own is not None:
        for u in early:
            position = states[first_own].units.get(u)
            survival[u]["present_at_ownership"] = position is not None
            survival[u]["on_objective_at_ownership"] = position is not None and position[0] == problem
    if not rehearsal and differences:
        problems.append(f"{len(differences)} decisions differ from the live decision (first at {differences[0]})")
    fire_endpoints = {}
    if config == sp.C2:
        unit = ref["protected_unit"]
        for d in sp.RULES["protected_fire_decisions"]:
            if d >= len(rows):
                problems.append(f"the game ended before decision {d}")
                continue
            fire_endpoints[d] = sp.fire_endpoint(d, unit, listed_types(rows[d]["raw"], unit),
                                                 [(a, tl.response(steps[d], seat, a)) for a in rows[d]["submitted"]])
    live = cap.prefix_inputs(timeline, windows, seat, ref["divergence"])
    prefix = sp.prefix_problems(ref, live["actions"], live["memory"], live["changed"], live["redirects"])
    world = sum(1 for j in range(min(ref["divergence"] + 1, len(rows)))
                if sp.canonical_sha256(rows[j]["raw"]) == ref["observations"][j])
    facts = {"configuration": config, "game": record.get("game_id"), "session": record.get("session"),
             "status": record.get("status"), "steps": record.get("steps"), "seat_faction": faction,
             "decisions": len(rows), "active_decisions": ordinal, "counts": dict(counts),
             "differences": len(differences), "first_difference": differences[0] if differences else None,
             "problems": problems[:50], "prefix_problems": prefix,
             "world_identical_through_divergence": {"decisions": min(ref["divergence"] + 1, len(rows)),
                                                    "identical": world},
             "first_ownership": ownership(states, faction, len(rows), names),
             "first_own_problem_decision": first_own,
             "fire": {"decisions_with_a_direct_fire_listing": fire["listing_decisions"], "orders": fire["orders"],
                      "order_decisions": fire["order_decisions"], "responses": dict(sorted(fire["responses"].items()))},
             "memory": {"max_records": max_records, "ended": dict(sorted(ended.items())),
                        "eligible_claimant_decisions": exposure},
             "scores": {k_: v for k_, v in sorted((record.get("final_scores") or {}).items())},
             "seconds": round(time.perf_counter() - started, 1)}
    private = {"game": record.get("game_id"), "names": {str(c): n for c, n in names.items()}, "fsd": fsd,
               "redirects": redirects, "tracker": tracker, "fire_endpoints": fire_endpoints, "audit": audit,
               "survival": {str(u): s for u, s in survival.items()}, "problem": problem, "capturers": capturers,
               "differences": differences[:50]}
    return facts, private


# ------------------------------------------------------------------------------------------------
# Classification and public files


def label(names: Mapping[str, str], coord: Any) -> Optional[str]:
    return None if coord is None else names.get(str(coord), "an objective")


def public_fsd(fsd: Optional[Mapping[str, Any]], names: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    if fsd is None:
        return None
    return {"decision": fsd["k"], "cur_step": fsd["cur_step"], "ordinal": fsd["ordinal"],
            "changed_unit_kinds": [KIND.get(k, "other") for k in fsd["changed_kinds"]],
            "redirects": [{"kind": KIND.get(r["kind"], "other"), "source": label(names, r["source"]),
                           "alternative": label(names, r["alternative"]), "route_cost": r["route_cost"],
                           "own_cost": r["own_cost"], "free_flow_steps": r["free_flow"], "v3_action": r["v3_form"],
                           "candidate_action": r["candidate_form"],
                           "to_problem_objective": r["to_problem_objective"]} for r in fsd["redirects"]],
            "independent_check_violations": fsd["violations"]}


def redirect_summary(rows: Sequence[Mapping[str, Any]], names: Mapping[str, str]) -> Dict[str, Any]:
    by_decision = collections.defaultdict(list)
    for r in rows:
        by_decision[r["k"]].append(r)
    return {"redirects": len(rows), "redirected_units": len({r["unit"] for r in rows}),
            "decisions": [{"decision": k, "count": len(v), "kinds": sorted(KIND.get(r["kind"], "other") for r in v),
                           "from": sorted({label(names, r["from"]) for r in v}),
                           "to": sorted({label(names, r["to"]) for r in v}),
                           "independent_checks_clean": all(r["clean"] for r in v)}
                          for k, v in sorted(by_decision.items())]}


def audit_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    feasible = [r for r in rows if r["feasible"]]
    return {"claim_decisions": len({r["k"] for r in rows}), "claimant_decisions": len(rows),
            "claimants": len({r["unit"] for r in rows}),
            "able_to_arrive": len(feasible),
            "forms": dict(sorted(collections.Counter(r["form"] for r in rows).items())),
            "placed": sum(1 for r in rows if r["placed"]),
            "selectable_not_placed": sum(1 for r in feasible if not r["placed"]),
            "early_place_blocks": sum(1 for r in rows if r["early_place_block"]),
            "early_place_block_decisions": sorted({r["k"] for r in rows if r["early_place_block"]}),
            "early_place_block_forms": dict(sorted(collections.Counter(r["form"] for r in rows
                                                                       if r["early_place_block"]).items())),
            "max_early_places": max((r["early_places"] for r in rows), default=0),
            "descriptive_all_redirect_place_blocks": sum(1 for r in rows if r["redirect_place_block"]),
            "first_claim_decision": min((r["k"] for r in rows), default=None)}


def classify(config: str, facts: Mapping[str, Any], private: Mapping[str, Any]) -> Dict[str, Any]:
    if config == sp.C2:
        return sp.classify_c2(private["fire_endpoints"])
    return sp.classify_212(facts["first_own_problem_decision"], audit_summary(private["audit"])["early_place_blocks"])


def combine(results: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]], stops: Mapping[str, Mapping[str, Any]],
            ledger: Mapping[str, Any], inputs: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    the_card = card()
    by_config = {f["configuration"]: (f, p) for f, p in results}
    problems: List[str] = []
    if not ledger["ok"]:
        problems.append(f"ledger audit: {ledger['problems']}")
    games_public, mechanism_public, classes = [], {}, {}
    for entry in the_card["games"]:
        config = sp.config_key(entry["scenario_id"], entry["condition"])
        found = stops.get(entry["game_id"])
        if found is None or config not in by_config:
            problems.append(f"{entry['game_id']}: no record or no replay")
            continue
        structural = sp.structural_stops(found)
        if structural:
            problems.append(f"{entry['game_id']}: structural stops {structural}")
        f, p = by_config[config]
        problems.extend(f"{entry['game_id']}: {x}" for x in f["problems"] + [f"prefix: {x}" for x in
                                                                              f["prefix_problems"]])
        names = p["names"]
        reference = inputs["anchors"][config]["v3_first_ownership"]
        games_public.append({
            "position": entry["screen_position"], "configuration": config, "game_id": entry["game_id"],
            "session": f["session"], "status": f["status"], "steps": f["steps"], "structural_stops": structural,
            "offline_reconstruction": {"decisions": f["decisions"], "differences": f["differences"],
                                       "memory_compared": f["counts"].get("memory_compared", 0),
                                       "problems": len(f["problems"])},
            "prefix": {"registered_first_divergence": inputs["anchors"][config]["first_divergence_decision"],
                       "pass": not f["prefix_problems"], "problems": f["prefix_problems"],
                       "world_identical_through_divergence": f["world_identical_through_divergence"]},
            "record_facts_not_used_in_any_rule": f["scores"]})
        block = {"game_id": entry["game_id"], "first_divergence": public_fsd(p["fsd"], names),
                 "candidate_redirects": redirect_summary(p["redirects"], names),
                 "recourse": ms.recourse([p["tracker"]]),
                 "memory_bounds": f["memory"],
                 "objective_ownership": {lab: {**row, "v3_first_ownership_decision": reference.get(lab)}
                                         for lab, row in f["first_ownership"].items()},
                 "capture_order": [lab for _, lab in sorted((row["first_ownership_decision"], lab)
                                                            for lab, row in f["first_ownership"].items()
                                                            if row["first_ownership_decision"] is not None)],
                 "v3_capture_order": [lab for _, lab in sorted((k, lab) for lab, k in reference.items()
                                                               if k is not None)],
                 "direct_fire": f["fire"]}
        if config == sp.C2:
            block["protected_fire_endpoints"] = {str(d): dict(e) for d, e in sorted(p["fire_endpoints"].items())}
        else:
            block["problem_objective"] = {"label": sp.RULES["problem_objective"],
                                          "first_ownership_decision": f["first_own_problem_decision"],
                                          "deadline": sp.RULES["first_ownership_deadline"]}
            block["pre_capture_audit"] = audit_summary(p["audit"])
            block["v3_capturers_in_this_game"] = [{**{k_: v for k_, v in c.items() if k_ != "kind"},
                                                   "kind": KIND.get(c["kind"], "other")}
                                                  for _, c in sorted(p["capturers"].items())]
            block["decision_361_units"] = [{"counted_decisions": s["counted_decisions"],
                                            "lost_before_ownership": s["lost_before_ownership"],
                                            "present_at_ownership": s["present_at_ownership"],
                                            "on_objective_at_ownership": s["on_objective_at_ownership"]}
                                           for _, s in sorted(p["survival"].items())]
        c = classify(config, f, p)
        classes[config] = c
        block["classification"] = c
        mechanism_public[config] = block
    verdict = sp.disposition(problems, classes.get(sp.C2), classes.get(sp.C212))
    base = {"schema": sp.SCHEMA, "note": NOTE, "inputs_sha256": sha256(INPUTS)}
    return {
        "games": {**base, "card": {"id": sp.CARD_ID, "canonical_sha256": mf.digest(the_card)},
                  "ledger": {"sessions_after_base": ledger["sessions"], "unclosed": ledger["unclosed"],
                             "ok": ledger["ok"], "sessions": sorted(int(s) for s in ledger["games"].values())},
                  "games": games_public},
        "mechanism": {**base, "configurations": mechanism_public},
        "disposition": {**base, "classes": {c: row["class"] for c, row in sorted(classes.items())},
                        "reasons": {c: row["reasons"] for c, row in sorted(classes.items())},
                        "disposition": verdict, "problems": problems[:50],
                        "statement": "the disposition concerns two observed games of the executable candidate; it "
                                     "promotes nothing, authorizes no further engine use and returns to the owner"}}


def private_values(results) -> Set[Any]:
    values: Set[Any] = set()
    for _, p in results:
        values.update(int(c) for c in p["names"])
        for r in p["redirects"]:
            values.update((r["from"], r["to"]))
    return values


def public_texts(public: Mapping[str, Any], results) -> Dict[str, str]:
    hidden = private_values(results)
    texts = {}
    for name, data in public.items():
        found = sp.public_check(data, hidden)
        if found:
            raise SystemExit(f"refused: {name}.json would publish private values: {found[:5]}")
        text = dump(data)
        if sp.forbidden_identity(text):
            raise SystemExit(f"refused: {name}.json names the stage-1 allocator's identity (its whitelist)")
        texts[name] = text
    return texts


# ------------------------------------------------------------------------------------------------
# Commands


def ledger_audit() -> Dict[str, Any]:
    """The audit over the ledger read up to this sprint's last possible session (2793 + 2): a later sprint's sessions
    can never change the published files. The runner and the game entry point audit the whole live ledger, and the
    close-out verifies separately that no session after 2795 was opened by this sprint."""
    path = REPO_ROOT / "local" / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"
    last = sp.LEDGER_BASE_SESSION + sp.SESSION_CEILING
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sp.ledger_audit([r for r in records if r.get("session") is None or int(r["session"]) <= last], card())


def run_job(job: Tuple[str, str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    config, game_id = job
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    the_card = card()
    entry = next(g for g in the_card["games"] if g["game_id"] == game_id)
    record, timeline, windows, _ = load_game(WORK, game_id, CAPTURES)
    return analyze_game(config, record, timeline, windows, costs_of(the_card, WORK, entry["scenario_id"]), reference,
                        sp.CANDIDATE_ID)


def stops_job(entry: Mapping[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    if not (WORK / "games" / f"{entry['game_id']}.json").exists():
        return entry["game_id"], None
    game = load("run_s17_game")
    return entry["game_id"], game.recorded_stops(card(), dict(entry), WORK)


def run(args: argparse.Namespace) -> int:
    inputs, _ = require_inputs()
    the_card = card()
    jobs = [(sp.config_key(g["scenario_id"], g["condition"]), g["game_id"]) for g in the_card["games"]
            if (WORK / "games" / f"{g['game_id']}.json").exists()]
    with multiprocessing.get_context("fork").Pool(max(1, len(jobs))) as pool:
        results = pool.map(run_job, jobs, chunksize=1)
        stops = dict(pool.map(stops_job, the_card["games"], chunksize=1))
    public = combine(results, {g: s for g, s in stops.items() if s is not None}, ledger_audit(), inputs)
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
        json.dump({"results": [{"facts": f, "private": {k: v for k, v in p.items() if k != "tracker"},
                                "episodes": p["tracker"].episodes()} for f, p in results]},
                  handle, sort_keys=True, default=str)
    print(json.dumps(public["disposition"]["disposition"], indent=1))
    print(json.dumps(public["disposition"]["classes"], indent=1))
    return 0


def rehearse_agent(config: str, game_id: str, reference: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The executable agent over every recorded decision of one Sprint 16 v3 game: equality with frozen v3 on the
    on-policy prefix, the registered divergence, the corrected-memory chain, equality with the Sprint 16 target shadow
    at every decision, and the Sprint 17 observer's reconstruction and consistency checks."""
    the_card = source_card()
    entry = next(g for g in the_card["games"] if g["game_id"] == game_id)
    record, timeline, windows, _ = load_game(SOURCE_WORK, game_id, SOURCE_CAPTURES)
    seat, faction, rows, _, _ = stream(record, timeline, windows, tb.CANDIDATE_ID)
    inputs = inputs_of(the_card, SOURCE_WORK, entry["scenario_id"])
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    agent = c6.PostStageAnyV6Agent()
    agent.setup({"seat": seat, "faction": faction, "cost_data": inputs.cost})
    divergence = None if reference is None else reference["divergence"]
    shadow: Tuple[Tuple[int, int], ...] = ()
    expected = (agent.memory.baseline, ())
    out = collections.Counter()
    first: Dict[str, Optional[int]] = {"v3_difference": None, "shadow_difference": None, "memory_difference": None,
                                       "observer_failure": None, "chain_difference": None}
    for row in rows:
        k, raw = row["k"], row["raw"]
        on_policy = divergence is None or k <= divergence
        memory_before = agent.memory
        if on_policy and memory_before.baseline != row["memory"].baseline:
            first["chain_difference"] = first["chain_difference"] if first["chain_difference"] is not None else k
        if reference is not None and k <= divergence + 1 and \
                sp.memory_digest(memory_before.addon) != reference["memory_in"][k]:
            first["memory_difference"] = first["memory_difference"] if first["memory_difference"] is not None else k
        actions = rd.plain(agent.step(dict(raw)))
        observation = Observation.from_raw(raw, Origin.ENGINE)
        policy = ShootReservationPolicy(costs)
        base = policy.decide(observation, seat, faction, memory_before.baseline)
        target = sh.allocate(observation, seat, faction, base.actions, policy.router, sh.RULES[sh.TARGET], shadow)
        out["decisions"] += 1
        if actions != rd.plain(target.actions) or tuple(agent.memory.addon) != tuple(target.memory):
            first["shadow_difference"] = first["shadow_difference"] if first["shadow_difference"] is not None else k
        shadow = target.memory
        if on_policy:
            out["on_policy_decisions"] += 1
            if divergence is None or k < divergence:
                if actions != row["submitted"]:
                    first["v3_difference"] = first["v3_difference"] if first["v3_difference"] is not None else k
            elif sp.actions_digest(actions) != reference["expected_actions"]:
                out["divergence_mismatch"] += 1
            decision = {"trace": agent.last_trace, "submitted": actions, "memory": memory_before, "observation": raw}
            rebuilt = cap.reconstruct(raw, seat, faction, memory_before, costs)
            checks = cap.consistency(decision, rebuilt, expected)
            expected = (rebuilt["baseline_memory_out"], rebuilt["memory_out"])
            out["observer_checks"] += 1
            if not all(checks.values()):
                first["observer_failure"] = first["observer_failure"] if first["observer_failure"] is not None else k
    ok = all(v is None for v in first.values()) and not out["divergence_mismatch"]
    return {"configuration": config, "game": game_id, "counts": dict(out), "first_failures": first, "pass": ok}


def rehearse(args: argparse.Namespace) -> int:
    inputs, reference = require_inputs()
    started = time.perf_counter()
    jobs = [(sp.C2, sp.SOURCE_GAMES[sp.C2]), (sp.C212, sp.SOURCE_GAMES[sp.C212]), ("1930331196 C3", SOURCE_C3)]
    agents = [rehearse_agent(c, g, reference["configs"].get(c)) for c, g in jobs]
    stand_ins = []
    the_card = source_card()
    for config in sp.CONFIGS:
        gid = sp.SOURCE_GAMES[config]
        entry = next(g for g in the_card["games"] if g["game_id"] == gid)
        record, timeline, windows, _ = load_game(SOURCE_WORK, gid, SOURCE_CAPTURES)
        facts, private = analyze_game(config, record, timeline, windows,
                                      costs_of(the_card, SOURCE_WORK, entry["scenario_id"]), reference,
                                      tb.CANDIDATE_ID, rehearsal=True)
        row = {"configuration": config, "first_difference": facts["first_difference"], "problems": facts["problems"],
               "prefix_problems": facts["prefix_problems"], "fsd": None if private["fsd"] is None else
               private["fsd"]["k"], "world": facts["world_identical_through_divergence"]}
        if config == sp.C2:
            row["fire_class"] = sp.classify_c2(private["fire_endpoints"])["class"]
        else:
            row["first_own"] = facts["first_own_problem_decision"]
            row["audit"] = audit_summary(private["audit"])
            row["capturers"] = private["capturers"]
        stand_ins.append(row)
    requirements = {
        "agent_replays_pass": all(a["pass"] for a in agents),
        "c2_divergence": stand_ins[0]["first_difference"] == sp.RULES["first_divergence"][sp.C2]
        and stand_ins[0]["fsd"] == sp.RULES["first_divergence"][sp.C2],
        "212_divergence": stand_ins[1]["first_difference"] == sp.RULES["first_divergence"][sp.C212]
        and stand_ins[1]["fsd"] == sp.RULES["first_divergence"][sp.C212],
        "c2_v3_fire_preserved": stand_ins[0]["fire_class"] == sp.C2_CLASSES[0],
        "212_v3_first_ownership": stand_ins[1]["first_own"] == sp.RULES["first_ownership_deadline"],
        "212_v3_capturers_found_on_the_objective": bool(stand_ins[1]["capturers"]) and all(
            c["on_objective_at_ownership"] for c in stand_ins[1]["capturers"].values()),
        "stand_in_prefix_passes_before_and_fails_at_the_divergence": all(
            not any(x.startswith("the candidate's actions differ") for x in s["prefix_problems"])
            and any(x.startswith("no divergence at decision") for x in s["prefix_problems"]) for s in stand_ins),
        "stand_in_problems_none": all(not s["problems"] for s in stand_ins),
        "world_identical": all(s["world"]["identical"] == s["world"]["decisions"] for s in stand_ins),
    }
    out = {"wall_seconds": round(time.perf_counter() - started, 1), "agents": agents, "stand_ins": stand_ins,
           "requirements": requirements, "pass": all(requirements.values())}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "rehearsal.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n",
                                            encoding="utf-8", newline="\n")
    print(json.dumps({"requirements": requirements, "pass": out["pass"], "wall_seconds": out["wall_seconds"]},
                     indent=1))
    return 0 if out["pass"] else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("freeze", "rehearse", "run"):
        p = sub.add_parser(command)
        p.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "freeze":
        reference_text = dump(build_reference())
        inputs_text = dump(build_inputs(reference_text))
        if args.check:
            same = (REFERENCE.read_text(encoding="utf-8") == reference_text
                    and INPUTS.read_text(encoding="utf-8") == inputs_text)
            print("OK" if same else "MISMATCH")
            return 0 if same else 1
        PRIVATE.mkdir(parents=True, exist_ok=True)
        REFERENCE.write_text(reference_text, encoding="utf-8", newline="\n")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(inputs_text, encoding="utf-8", newline="\n")
        print(f"wrote {INPUTS.relative_to(REPO_ROOT).as_posix()} and the private prefix reference")
        return 0
    return rehearse(args) if args.command == "rehearse" else run(args)


if __name__ == "__main__":
    sys.exit(main())
