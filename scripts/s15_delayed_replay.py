"""Sprint 15 offline study of delayed redistribution (``docs/SPRINT15_DELAYED_REDISTRIBUTION.md``), server only.

    python scripts/s15_delayed_replay.py diagnose [--check]   # reference policies only -> diagnostics.json
    python scripts/s15_delayed_replay.py freeze [--check]     # inputs.json, after diagnostics.json is committed
    python scripts/s15_delayed_replay.py run [--check] [--workers N]

``diagnose`` reads the ten captures Sprint 14 pinned (its ``inputs.json`` must still hold), the eight Sprint 10 T9-v2
exploratory captures, and decides the reference policies only (``baseline-v2``, frozen T9-v1, frozen v3, Sprint 13's O2,
Sprint 14's batch rule, and v3's own memory track): the opening-versus-later decomposition, the state features of every
redirect opportunity with the diagnostic rule search, the geometry from v3's first staging hexes, the staging-hex proxy
with its known-answer calibration, and the T9-v2 withhold episodes against the shooters. No candidate is decided.

``freeze`` pins every private input of the final replay by SHA-256 (the ten captures, the cost data, the H0 replay
corpus, the T9-v2 captures), the committed ``diagnostics.json``, the candidate module's identity, the gate thresholds
and the reference figures; it refuses if a frozen policy identity differs.

``run`` requires every pin, replays every decision of the ten captures and both seats of the eight H0 games with every
Sprint 15 candidate's memory simulated sequentially from empty, checks the replay's fidelity, evaluates the frozen gate,
the adequacy rule, the rubric and the disposition, and writes the public files. ``--check`` regenerates them in memory
and compares byte for byte; ``timing.json`` is measured once and reused. No engine is opened and the ledger is not read.
"""

from __future__ import annotations

import argparse
import ast
import collections
import gzip
import hashlib
import importlib.util
import inspect
import json
import math
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.context import build_context  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.decision.routing import ROADBLOCKED_MODES, move_mode  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s13_diagnosis as sd  # noqa: E402
from miaosuan_agent.evaluation import s14_design as sx  # noqa: E402
from miaosuan_agent.evaluation import s15_delayed as s15  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments import t9_delayed as td  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory, hex_distance  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

_spec = importlib.util.spec_from_file_location("s14_design_replay", REPO_ROOT / "scripts" / "s14_design_replay.py")
S14 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S14)  # Sprint 14's frozen loaders, read only

SCHEMA = "miaosuan-s15-delayed/1"
SCHEMA_INPUTS = "miaosuan-s15-inputs/1"
OUT_DIR = REPO_ROOT / "evaluation" / "s15-delayed-redistribution"
INPUTS = OUT_DIR / "inputs.json"
DIAGNOSTICS = OUT_DIR / "diagnostics.json"
TIMING = OUT_DIR / "timing.json"
ADVERSE_FILES = {"2120531121 C3": "adverse-2120531121-c3", "1930331196 C3": "adverse-1930331196-c3",
                 "1930331196 C2": "adverse-1930331196-c2"}
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s15"
EV = REPO_ROOT / "local" / "evaluation"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
H0_DATA = EV / "baseline-v1-variance-study-1" / "data"
T9V2 = EV / "s10-t9-v2-exploration" / "capture"
CANDIDATE_MODULES = ("experiments/exploratory_addon.py", "experiments/t9_batch.py", "experiments/t9_redistribution.py",
                     "experiments/t9_delayed.py")
ALLOWED_LITERALS = {0, 1, 2, 3, 16, 300, 1000}
TRANSITION_FREE = 0  # a staged unit can be ordered again on the step it arrives (Sprint 5 and Sprint 11 audits)
NOTE = ("offline study on recorded states: every policy is an action-level decision on states another policy "
        "produced, with each candidate's own memory simulated over the recorded observations; nothing here is an "
        "engine outcome, a score estimate or evidence of an effect")
FEATURES = ("prior_overflow_same_source", "completed_stage", "steps_in_episode", "unheld_share", "source_saturated",
            "detour_ratio", "value_ratio", "free_flow", "vehicle", "nearest_seen_enemy", "enemies_within_10",
            "strength")


def sha256(path: Path) -> str:
    return S14.sha256(path)


def dump(data: Any) -> str:
    return S14.dump(data)


# ------------------------------------------------------------------------------------------------
# Identities and inputs


def candidate_identity() -> Dict[str, Any]:
    base = S14.rr.candidate_sources() + ("experiments/shoot_reservation.py",)
    files = policy_source_files(sources=base + CANDIDATE_MODULES)
    return {"policy_source_sha256": digest_of_files(files), "module_files": list(CANDIDATE_MODULES),
            "rules": {name: {"identity": r.identity, "trigger": r.trigger, "count": r.count,
                             "same_source": r.same_source} for name, r in td.RULES.items()}}


def static_checks() -> Dict[str, bool]:
    source = Path(td.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    parameters = tuple(inspect.signature(td.allocate).parameters)
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}
    return {"seat_local": (not any("evaluation" in m or "engine" in m for m in imported)
                           and parameters == ("observation", "seat", "faction", "actions", "router", "rule",
                                              "memory", "everyone")),
            "no_special_case_literal": literals <= ALLOWED_LITERALS}


def h0_files() -> List[Tuple[Path, str]]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    return [(REPO_ROOT / e["path"], e["sha256"]) for e in corpus["files"] if e["role"] == "replay corpus game"]


def t9v2_files() -> List[Path]:
    return sorted(T9V2.glob("*.explore.json"))


def build_inputs() -> Dict[str, Any]:
    s14_inputs = S14.require_inputs()  # the ten captures and their cost data, as Sprint 14 pinned them
    h0 = []
    for path, pinned in h0_files():
        if sha256(path) != pinned:
            raise SystemExit(f"refused: {path.name} differs from its corpus pin")
        h0.append({"file": path.name, "sha256": pinned})
    if len(h0) != 8:
        raise SystemExit("refused: expected 8 H0 games")
    return {"schema": SCHEMA_INPUTS, "frozen_policies_checked": s14_inputs["frozen_policies_checked"],
            "sprint14_inputs_sha256": sha256(S14.INPUTS), "candidates": candidate_identity(),
            "primary": s14_inputs["primary"], "adverse": s14_inputs["adverse"], "cost_data": s14_inputs["cost_data"],
            "h0": {"corpus_sha256": sha256(CORPUS), "games": h0, "data": S14.tree_digest(H0_DATA)},
            "t9_v2_captures": [{"file": p.name, "sha256": sha256(p)} for p in t9v2_files()],
            "diagnostics_sha256": sha256(DIAGNOSTICS), "gate_thresholds": s15.GATE, "risk_windows": s15.RISK_WINDOW,
            "s13_expected": sx.S13_EXPECTED,
            "adverse_facts": {k: {kk: list(vv) if isinstance(vv, tuple) else vv for kk, vv in v.items()}
                              for k, v in sx.ADVERSE_FACTS.items()},
            "note": "private inputs pinned before the Sprint 15 final replay; files stay under the ignored local/ tree"}


def require_inputs() -> Mapping[str, Any]:
    committed = INPUTS.read_text(encoding="utf-8")
    if dump(build_inputs()) != committed:
        raise SystemExit("refused: an input, an identity or a threshold differs from inputs.json")
    return json.loads(committed)


# ------------------------------------------------------------------------------------------------
# One capture


def new_facts() -> Dict[str, Any]:
    return {"active_decisions": 0, "emitted_ground": 0, "redirects": 0, "keeps": 0, "stages": 0, "withholds": 0,
            "buckets": collections.Counter(), "units": set(), "post_units": set(), "first_decision_redirects": None,
            "violations": collections.Counter(), "slot_vs_t9": 0, "post_slot_vs_t9": 0, "orders_vs":
            collections.Counter(), "repeat": collections.Counter(), "certificate": collections.Counter(),
            "latency": [], "memory_checks": 0, "memory_problems": 0, "ended": collections.Counter(),
            "persistence_steps": [], "persistence_count": [], "exposure": [], "max_records": 0,
            "eligible_observations": 0, "overflow_observations": 0}


def unit_features(raw: Mapping[str, Any], faction: int, unit_id: int) -> Dict[str, Any]:
    units = {u["obj_id"]: u for u in raw.get("operators") or ()}
    unit = units[unit_id]
    seen = [u["cur_hex"] for u in units.values() if u.get("color") == 1 - faction and isinstance(u.get("cur_hex"), int)]
    dists = sorted(hex_distance(unit["cur_hex"], h) for h in seen)
    max_blood = unit.get("max_blood") or 0
    return {"nearest_seen_enemy": dists[0] if dists else None, "enemies_within_10": sum(1 for d in dists if d <= 10),
            "strength": round((unit.get("blood") or 0) / max_blood, 4) if max_blood else None,
            "vehicle": int(unit.get("type") == 2)}


def stream(kind: str, spec: Any):
    if kind == "primary":
        gid, label, cell = spec["game_id"], spec["label"], spec["cell"]
        costs = S14.costs_for(S14.PRIMARY_CARD, S14.PRIMARY_SCENARIO, "21")
        seat, faction, rows = S14.primary_stream(gid)
        return gid, label, cell, f"{S14.PRIMARY_SCENARIO} {cell}", "v3", costs, seat, faction, rows
    config, card, gid, scenario, map_id, _, played = spec
    costs = S14.costs_for(card, scenario, map_id)
    seat, faction, rows = S14.adverse_stream(spec)
    return gid, gid.rsplit(".", 1)[-1], config.split()[1], config, played, costs, seat, faction, rows


def shooters_of(entry: Sequence[Any]) -> Tuple[str, Dict[int, int]]:
    """The direct-fire units of a baseline-v2 adverse capture at its registered firing decisions: unit -> first one."""
    config = entry[0]
    _, _, rows = S14.adverse_stream(entry)
    fire = sx.ADVERSE_FACTS[config]["fire_decisions"]
    out: Dict[int, int] = {}
    for row in rows:
        if row["k"] in fire:
            for action in row["submitted"]:
                if action.get("type") == 2:
                    out[action["obj_id"]] = min(out.get(action["obj_id"], row["k"]), row["k"])
    return config, out


def process(job: Tuple[str, str, Any, Mapping[int, int]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    mode, kind, spec, shooters = job
    candidates = s15.CANDIDATES if mode == "run" else ()
    policies = s15.REFERENCES + tuple(candidates)
    gid, label, cell, config, played, costs, seat, faction, rows = stream(kind, spec)
    values = {c["coord"]: c.get("value") for c in (rows[0]["raw"].get("cities") or ())}
    names = tl.labels(values)
    facts: Dict[str, Any] = {"game": gid, "label": label, "cell": cell, "configuration": config, "played": played,
                             "decisions": len(rows), "policies": {n: new_facts() for n in policies}, "problems": [],
                             "first_active_k": None, "first_state_sha256": None, "steps_at": {}, "flags": {},
                             "seat_faction": faction, "unheld": {}, "shooter_states": {}, "identity_checks": 0}
    private: Dict[str, Any] = {"game": gid, "redirects": {n: [] for n in policies}, "features": [],
                               "exposure": {n: [] for n in candidates}, "names": {str(c): n for c, n in names.items()},
                               "claims": [], "geometry": [], "proxy": None}
    problems = facts["problems"]
    memories: Dict[str, Any] = {s15.V3_TRACK: (), **{n: () for n in candidates}}
    ordinal = 0
    first_v3: Optional[Any] = None
    for row in rows:
        k, raw = row["k"], row["raw"]
        now = (raw.get("time") or {}).get("cur_step")
        facts["steps_at"][str(k)] = now
        for city in raw.get("cities") or ():
            history = facts["flags"].setdefault(str(city["coord"]), [])
            if not history or history[-1][1] != city.get("flag"):
                history.append((k, city.get("flag")))
        observation = Observation.from_raw(raw, Origin.ENGINE)
        memory = row["memory"]
        base_memory = memory.baseline if isinstance(memory, AddonMemory) else memory
        decided = s15.decide_step(observation, seat, faction, base_memory, costs, memories, candidates=candidates)
        base = decided["baseline-v2"]
        if row["baseline"] is not None and rd.plain(base) != rd.plain(row["baseline"]):
            problems.append(f"k{k}: baseline-v2 re-decided differs from the capture")
        if row["trace"] is not None and decided["baseline_trace_sha256"] != row["trace"]:
            problems.append(f"k{k}: baseline-v2 trace digest differs from the capture")
        if rd.plain(decided[played]) != rd.plain(row["submitted"]):
            problems.append(f"k{k}: {played} differs from what the seat submitted")
        if row.get("t9_audit") is not None and rd.plain(decided["t9-v1"]) != rd.plain(row["t9_audit"]):
            problems.append(f"k{k}: T9-v1 differs from Sprint 10's captured audit")
        ground = sx.own_ground(observation, faction)
        before = dict(memories)
        for name in candidates:
            out_memory = decided[f"{name}_memory"]
            p = facts["policies"][name]
            p["memory_checks"] += 1
            found = s15.memory_problems(observation, faction, out_memory)
            p["memory_problems"] += len(found)
            if found and len(problems) < 50:
                problems.append(f"k{k}: {name} memory: {found[:2]}")
            p["max_records"] = max(p["max_records"], len(td.decode(out_memory)[0]))
            allocation = decided[f"{name}_allocation"]
            p["ended"].update(allocation.ended.values())
            if shooters:
                records = td.decode(out_memory)[0]
                states = facts["shooter_states"].setdefault(name, {})
                for unit_id, fire_k in shooters.items():
                    if k >= fire_k:
                        continue
                    state = states.setdefault(str(fire_k), collections.Counter())
                    record = records.get(unit_id)
                    if record is None:
                        state["no record"] += 1
                    else:
                        state[f"record: episode count {min(record[td.COUNT], 3)}{'+' if record[td.COUNT] > 3 else ''}"
                              f", completed staging {record[td.DONE]}, redirected {record[td.REDIRECTED]}"] += 1
                    state["overflow observations"] += int(unit_id in allocation.overflow)
                    state["trigger held"] += int(unit_id in allocation.eligible)
                    state["absent"] += int(unit_id not in ground)
            memories[name] = out_memory
        memories[s15.V3_TRACK] = decided[f"{s15.V3_TRACK}_memory"]
        if not decided["active"]:
            for name in candidates:
                if rd.plain(decided[name]) != rd.plain(base):
                    problems.append(f"k{k}: {name} changed a decision without own ground moves")
            continue
        ordinal += 1
        if facts["first_active_k"] is None:
            facts["first_active_k"] = k
            facts["first_state_sha256"] = hashlib.sha256(json.dumps(raw, sort_keys=True, default=repr).encode()
                                                         ).hexdigest()
            first_v3 = (row, decided["v3_allocation"])
        facts["identity_checks"] += 1
        if not decided["identity_v3"]:
            problems.append(f"k{k}: the delayed module with nobody eligible differs from v3")
        if not decided["identity_o2"]:
            problems.append(f"k{k}: the delayed module with everyone eligible differs from O2")
        v3 = decided["v3_allocation"]
        if row["allocation"] is not None:
            cap = row["allocation"]
            if ({str(u): c for u, c in v3.selected.items()} != cap["selected"]
                    or {str(u): list(p) for u, p in v3.staged.items()} != cap["staged"]
                    or {str(u): r for u, r in v3.withheld.items()} != cap["withheld"]):
                problems.append(f"k{k}: v3's allocation differs from the captured allocation")
        cities = {c.coord for c in (observation.cities() or ())}
        context = build_context(observation, seat, faction)
        facts["unheld"][str(k)] = len(context.objectives)
        slot_sets = {n: sx.slots(decided[n], ground, cities) for n in policies}
        repeats = s15.repeat_checks(observation, seat, faction, base, costs, decided, before, f"{gid}-{k}",
                                    candidates) if candidates else {}
        for name in policies:
            p = facts["policies"][name]
            p["active_decisions"] += 1
            allocation = decided.get(f"{name}_allocation")
            checks = sx.candidate_checks(observation, seat, faction, base, decided[name],
                                         allocation if name in candidates else None,
                                         v3 if name in candidates else None, costs)
            p["violations"].update(checks["violations"])
            forms = checks["forms"]
            counts = collections.Counter(forms.values())
            p["emitted_ground"] += len(sx.ground_moves(decided[name], ground))
            p["redirects"] += counts[s15.REDIRECT]
            p["keeps"] += counts[s15.KEEP]
            p["stages"] += counts[s15.STAGE]
            p["withholds"] += counts[s15.WITHHOLD]
            redirected = {u for u, f in forms.items() if f == s15.REDIRECT}
            p["units"] |= redirected
            p["buckets"][s15.bucket(ordinal)] += len(redirected)
            if ordinal > 1:
                p["post_units"] |= redirected
            if ordinal == 1:
                p["first_decision_redirects"] = len(redirected)
            p["slot_vs_t9"] += sx.slot_divergence(slot_sets[name], slot_sets["t9-v1"])
            if ordinal > 1:
                p["post_slot_vs_t9"] += sx.slot_divergence(slot_sets[name], slot_sets["t9-v1"])
            for ref in ("baseline-v2", "t9-v1", "v3", "O2"):
                p["orders_vs"][ref] += len(sx.order_divergence(decided[name], decided[ref], ground))
            for r in checks["redirects"]:
                private["redirects"][name].append({**r, "k": k, "ordinal": ordinal, "cur_step": now,
                                                   "to_label": names.get(r["to"]), "from_label": names.get(r["from"])})
            if name in candidates:
                p["repeat"].update(repeats[name])
                p["latency"].append(decided[f"{name}_ms"])
                p["overflow_observations"] += len(allocation.overflow)
                p["eligible_observations"] += len(allocation.eligible)
                for unit_id in allocation.eligible:
                    private["exposure"][name].append({"k": k, "unit": unit_id,
                                                      "redirected": unit_id in allocation.redirected})
                records_in = td.decode(before.get(name, ()))[0]
                for unit_id in allocation.redirected:
                    record = records_in.get(unit_id)
                    if record is not None:
                        p["persistence_count"].append(record[td.COUNT] + 1)
                        p["persistence_steps"].append(now - record[td.FIRST] if record[td.FIRST] else 0)
            elif name == "t9-v1":
                p["latency"].append(decided["t9-v1_ms"])
            if config == "2120531121 C3" and k >= sx.ADVERSE_FACTS[config]["certificate_from_decision"]:
                v1_forms = sx.forms(base, decided["t9-v1"], ground, cities)
                for u, action in sx.ground_moves(base, ground).items():
                    dest = list(action["move_path"])[-1]
                    if dest in cities and v1_forms.get(u) != s15.KEEP and forms.get(u) == s15.KEEP:
                        p["certificate"][str(dest)] += 1
        if mode == "diagnose":
            diagnose_decision(private, facts, observation, raw, seat, faction, decided, before, ordinal, k, now,
                              values, shooters)
    if problems:
        raise SystemExit(f"refused: {gid}: {len(problems)} reconstruction problems, e.g. {problems[:3]}")
    if mode == "diagnose" and first_v3 is not None:
        private["geometry"] = staging_geometry(first_v3, costs, seat, faction, names)
        if played in ("v3", "baseline-v2"):
            private["proxy"] = staging_proxy(rows, first_v3, costs, seat, faction, names, private["claims"])
    for p in facts["policies"].values():
        p["redirected_units"] = len(p.pop("units"))
        p["post_opening_units"] = len(p.pop("post_units"))
    return facts, private


def diagnose_decision(private, facts, observation, raw, seat, faction, decided, before, ordinal, k, now, values,
                      shooters) -> None:
    """Feature rows of every O2 redirect opportunity, and every claim (for the decomposition and the shooters)."""
    o2 = decided["O2_allocation"]
    v3 = decided["v3_allocation"]
    track = td.decode(before.get(s15.V3_TRACK, ()))[0]
    td.observe(observation, faction, track)  # the view a candidate decides on: this decision's updates applied
    context = build_context(observation, seat, faction)
    share = len(context.objectives) / max(len(values), 1)
    for unit_id, claimant in sorted(o2.claimants.items()):
        overflow = claimant.status == "no place under capacity" and unit_id not in o2.selected
        listed = context.unit(unit_id)
        private["claims"].append({"k": k, "ordinal": ordinal, "cur_step": now, "unit": unit_id,
                                  "source": claimant.objective, "overflow": overflow,
                                  "o2": unit_id in o2.redirected, "selected": unit_id in o2.selected,
                                  "v3_form": "KEEP" if unit_id in v3.selected else (
                                      "STAGE" if unit_id in v3.staged else "WITHHOLD"),
                                  "fire_listed": int(listed is not None and 2 in listed.actions)})
        if unit_id not in o2.redirected:
            continue
        option = o2.redirected[unit_id]
        record = track.get(unit_id)
        same = record is not None and record[td.SOURCE] == claimant.objective
        source_row = o2.objectives.get(claimant.objective, {})
        row = {"k": k, "ordinal": ordinal, "unit": unit_id, "opening": ordinal == 1,
               "prior_overflow_same_source": record[td.COUNT] if same else 0,
               "completed_stage": int(bool(record and record[td.DONE])),
               "steps_in_episode": (now - record[td.FIRST]) if same and record[td.FIRST] else 0,
               "unheld_share": round(share, 4),
               "source_saturated": int(source_row.get("physical", 0) >= td.CAPACITY and source_row.get("movers", 1) == 0),
               "detour_ratio": round(option.cost / option.base_cost, 4) if option.base_cost else None,
               "value_ratio": round((values.get(option.objective) or 1) / (values.get(claimant.objective) or 1), 4),
               "free_flow": option.free_flow, **unit_features(raw, faction, unit_id)}
        private["features"].append(row)


def staging_geometry(first, costs, seat, faction, names) -> List[Dict[str, Any]]:
    """From v3's decision-1 staging endpoints: which overflow units have any objective within twice the cost to
    their own (holding state and capacity ignored: a necessary condition of a later redirect from there)."""
    row, v3 = first
    raw = row["raw"]
    observation = Observation.from_raw(raw, Origin.ENGINE)
    context = build_context(observation, seat, faction)
    router = ShootReservationPolicy(costs).router
    units = {u["obj_id"]: u for u in raw.get("operators") or ()}
    out = []
    for unit_id, claimant in sorted(v3.claimants.items()):
        if claimant.status != "no place under capacity" or unit_id in v3.selected:
            continue
        unit = units[unit_id]
        mode = move_mode(unit["type"], unit.get("move_state"))
        blocked = context.roadblocks if mode in ROADBLOCKED_MODES else frozenset()
        start = v3.staged[unit_id][-1] if unit_id in v3.staged else unit["cur_hex"]
        paths = router.shortest_paths(start, mode, blocked)
        own = paths.cost.get(claimant.objective)
        within = [c for c in names if c != claimant.objective and c in paths.cost and own is not None
                  and paths.cost[c] <= 2.0 * own]
        out.append({"unit": unit_id, "kind": unit["type"], "form": "STAGE" if unit_id in v3.staged else "WITHHOLD",
                    "own_cost_from_end": own, "objectives_within_twice": len(within)})
    return out


def staging_proxy(rows, first, costs, seat, faction, names, claims) -> Dict[str, Any]:
    """The staging-hex proxy (section 4.4): v3's decision-1 staged overflow units pinned at their staging endpoints
    from their free-flow arrival on, claiming from there on the recorded objective states with every pinned unit
    removed from the counts. Returns, per unit, the proxy's first ready step and first proxy redirect opportunity,
    and the recorded trajectory's first post-opening claim and whether it was an O2 opportunity."""
    row1, v3 = first
    router = ShootReservationPolicy(costs).router
    observation = Observation.from_raw(row1["raw"], Origin.ENGINE)
    ground0 = sd.own_ground(observation, faction)
    start_step = row1["raw"]["time"]["cur_step"]
    pinned = {}
    for unit_id, claimant in v3.claimants.items():
        if claimant.status == "no place under capacity" and unit_id not in v3.selected and unit_id in v3.staged:
            unit = ground0[unit_id]
            times, _ = tb.path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"),
                                     unit.cur_hex, v3.staged[unit_id])
            pinned[unit_id] = {"hex": v3.staged[unit_id][-1], "ready": start_step + sum(times) + TRANSITION_FREE,
                               "kind": unit.unit_type, "speed": unit.fields.get("basic_speed"),
                               "state": unit.move_state}
    tracked = frozenset(pinned)
    proxy_first: Dict[int, Tuple[int, int]] = {}
    left: Dict[int, str] = {}
    for row in rows:
        if row["k"] <= row1["k"]:
            continue
        raw = row["raw"]
        now, end = raw["time"]["cur_step"], raw["time"]["max_step"]
        ready = [u for u, p in pinned.items() if p["ready"] <= now and u not in left and u not in proxy_first]
        if not ready:
            continue
        obs = Observation.from_raw(raw, Origin.ENGINE)
        context = build_context(obs, seat, faction)
        unheld = {c.coord for c in context.objectives}
        if not unheld:
            continue
        ground = sd.own_ground(obs, faction)
        counted, _ = sd.counted_incumbents(obs, faction, router, tracked)
        for coord, info in counted.items():
            info["physical"] -= sum(1 for u in tracked if u in ground and not ground[u].move_path
                                    and ground[u].cur_hex == coord)
        claimed = {}
        for u in ready:
            if u not in ground:
                left[u] = "gone"
                continue
            listed = context.unit(u)
            if listed is not None and 2 in listed.actions:
                continue
            p = pinned[u]
            if p["hex"] in unheld:
                continue
            mode = move_mode(p["kind"], p["state"])
            blocked = context.roadblocks if mode in ROADBLOCKED_MODES else frozenset()
            paths = router.shortest_paths(p["hex"], mode, blocked)
            options = sorted((paths.cost[c], c) for c in unheld if c in paths.cost)
            if options:
                claimed[u] = (options, paths, mode)
        by_target: Dict[int, List[int]] = collections.defaultdict(list)
        for u, (options, _, _) in claimed.items():
            by_target[options[0][1]].append(u)
        for target, group in sorted(by_target.items()):
            free = td.CAPACITY - counted[target]["physical"] - counted[target]["movers"]
            group.sort(key=lambda u: (claimed[u][0][0][0], u))
            for index, u in enumerate(group):
                if index < max(free, 0):
                    left[u] = "a place"
                    continue
                options, paths, mode = claimed[u]
                own_cost = options[0][0]
                for c_cost, coord in options[1:]:
                    if c_cost > 2.0 * own_cost or counted[coord]["physical"] + counted[coord]["movers"] >= td.CAPACITY:
                        continue
                    total, previous = 0, pinned[u]["hex"]
                    for hex_ in paths.path_to(coord):
                        total += tb.hex_time(pinned[u]["speed"], router.costs.neighbours(mode, previous)[hex_])
                        previous = hex_
                    if now + total < end:
                        proxy_first[u] = (row["k"], now)
                        break
    actual: Dict[int, Tuple[int, int, bool]] = {}
    for claim in claims:
        u = claim["unit"]
        if u in pinned and u not in actual and claim["ordinal"] > 1:
            actual[u] = (claim["k"], claim["cur_step"], claim["o2"])
    return {"pinned": {str(u): {"ready": p["ready"], "proxy_first": proxy_first.get(u), "left": left.get(u),
                                "actual_first_claim": actual.get(u)} for u, p in sorted(pinned.items())}}


# ------------------------------------------------------------------------------------------------
# H0 generalisation corpus (run only)


def h0_lines(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def process_h0(path_text: str) -> Dict[str, Any]:
    path = Path(path_text)
    stream_ = h0_lines(path)
    header = next(stream_)
    scenario = header["scenario_id"]
    costs = MoveCosts.from_raw(sdk_data.load_inputs(H0_DATA / scenario / "Data", scenario, header["map_id"]).cost)
    seats: Dict[int, Dict[str, Any]] = {}
    out = {"scenario": scenario, "checks": collections.Counter(), "policies": {n: new_facts() for n in
                                                                               s15.CANDIDATES + ("O2",)},
           "problems": [], "history": {n: [] for n in s15.CANDIDATES}}
    keys: Dict[Tuple[int, int], int] = {}  # (seat, unit) -> a dense index, for the oscillation count
    for row in stream_:
        seat, faction = row["seat"], row["faction"]
        if seat not in seats:
            seats[seat] = {"v0": BaselinePolicy(costs), "v2": ShootReservationPolicy(costs), "m0": Memory(),
                           "m2": Memory(), "memories": {n: () for n in s15.CANDIDATES}}
        s = seats[seat]
        raw = typed_json.decode(row["observation"])
        out["checks"]["decisions"] += 1
        try:
            v0 = s["v0"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, s["m0"])
        except ContractError:
            out["checks"]["excluded: contract error"] += 1
            continue
        s["m0"] = v0.memory
        if not ([dict(a) for a in v0.actions] == [dict(a) for a in row["actions"]]
                and digest(v0.trace) == row["trace_digest"]):
            out["checks"]["excluded: baseline-v0 not reproduced"] += 1
            continue
        observation = Observation.from_raw(raw, Origin.ENGINE)
        m2_before = s["m2"]
        v2 = s["v2"].decide(observation, seat, faction, s["m2"])
        s["m2"] = v2.memory
        out["checks"]["baseline-v0 reproduced, baseline-v2 reconstructed"] += 1
        decided = s15.decide_step(observation, seat, faction, m2_before, costs, s["memories"],
                                  candidates=s15.CANDIDATES)
        base = decided["baseline-v2"]
        if rd.plain(base) != rd.plain(v2.actions):
            out["problems"].append("baseline-v2 decided twice differs")
        before = dict(s["memories"])
        for name in s15.CANDIDATES:
            p = out["policies"][name]
            found = s15.memory_problems(observation, faction, decided[f"{name}_memory"])
            p["memory_checks"] += 1
            p["memory_problems"] += len(found)
            p["max_records"] = max(p["max_records"], len(td.decode(decided[f"{name}_memory"])[0]))
            p["ended"].update(decided[f"{name}_allocation"].ended.values())
            s["memories"][name] = decided[f"{name}_memory"]
        if not decided["active"]:
            if any(rd.plain(decided[name]) != rd.plain(base) for name in s15.CANDIDATES):
                out["problems"].append("a candidate changed a decision without own ground moves")
            continue
        out["checks"]["decisions with an own ground move"] += 1
        if not (decided["identity_v3"] and decided["identity_o2"]):
            out["problems"].append("an identity with v3 or O2 failed")
        v3 = decided["v3_allocation"]
        repeats = s15.repeat_checks(observation, seat, faction, base, costs, decided, before,
                                    f"h0-{scenario}-{seat}-{out['checks']['decisions']}", s15.CANDIDATES)
        for name in s15.CANDIDATES + ("O2",):
            p = out["policies"][name]
            allocation = decided.get(f"{name}_allocation")
            checks = sx.candidate_checks(observation, seat, faction, base, decided[name],
                                         allocation if name != "O2" else None, v3 if name != "O2" else None, costs)
            p["violations"].update(checks["violations"])
            p["active_decisions"] += 1
            redirected = [r for r in checks["redirects"]]
            p["redirects"] += len(redirected)
            p["units"] |= {(seat, r["unit"]) for r in redirected}
            if name != "O2":
                p["repeat"].update(repeats[name])
                p["latency"].append(decided[f"{name}_ms"])
                p["overflow_observations"] += len(allocation.overflow)
                p["eligible_observations"] += len(allocation.eligible)
                for r in redirected:
                    index = keys.setdefault((seat, r["unit"]), len(keys))
                    out["history"][name].append((out["checks"]["decisions"], index, r["from"], r["to"]))
    for name in s15.CANDIDATES + ("O2",):
        p = out["policies"][name]
        p["redirected_units"] = len(p.pop("units"))
        p.pop("post_units")
        p["oscillations"] = s15.oscillations(out["history"][name]) if name != "O2" else None
        p["max_redirects_per_unit_game"] = max(collections.Counter(u for _, u, _, _ in out["history"][name]).values(),
                                               default=0) if name != "O2" else None
    out.pop("history")
    if out["problems"]:
        raise SystemExit(f"refused: H0 {scenario}: {out['problems'][:3]}")
    return out


# ------------------------------------------------------------------------------------------------
# Combination


def summarize(p: Mapping[str, Any]) -> Dict[str, Any]:
    share = p["redirects"] / p["emitted_ground"] if p["emitted_ground"] else 0.0
    return {"active_decisions": p["active_decisions"], "emitted_ground_moves": p["emitted_ground"],
            "redirects": p["redirects"], "redirected_units": p["redirected_units"],
            "post_opening_units": p["post_opening_units"], "redirect_share": round(share, 4),
            "keeps": p["keeps"], "stages": p["stages"], "withholds": p["withholds"],
            "buckets": {b: p["buckets"].get(b, 0) for b in s15.BUCKETS},
            "first_decision_redirects": p["first_decision_redirects"],
            "violations": dict(sorted((k, v) for k, v in p["violations"].items() if v)),
            "slot_vs_t9-v1": p["slot_vs_t9"], "post_slot_vs_t9-v1": p["post_slot_vs_t9"],
            "order_divergence": dict(sorted(p["orders_vs"].items())), "repeat": dict(sorted(p["repeat"].items()))}


def memory_summary(p: Mapping[str, Any]) -> Dict[str, Any]:
    return {"memory_checks": p["memory_checks"], "memory_problems": p["memory_problems"],
            "max_records": p["max_records"], "records_ended": dict(sorted(p["ended"].items())),
            "overflow_observations": p["overflow_observations"], "trigger_held": p["eligible_observations"],
            "episode_count_at_redirect": s15.distribution(p["persistence_count"]),
            "steps_in_episode_at_redirect": s15.distribution(p["persistence_steps"])}


def check_fidelity(facts: Mapping[str, Mapping[str, Any]], games: Mapping[str, Any]) -> List[str]:
    out = []
    for f in facts.values():
        if f["first_active_k"] != 1:
            out.append(f"{f['label']}: first decision with an own ground move is {f['first_active_k']}, not 1")
    t9 = games["t9-v1"]
    expected = sx.S13_EXPECTED["t9-v1"]
    for key, field in (("redirects", "redirects"), ("emitted", "emitted_ground_moves"),
                       ("redirected_units", "redirected_units"),
                       ("first_decision_redirects", "first_decision_redirects")):
        got = {g: t9[g][field] for g in t9}
        if got != expected[key]:
            out.append(f"T9-v1 {key} {got} differ from Sprint 13's {expected[key]}")
    return out


def primary_rows(results, policies) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    primary = sorted((f for f, _ in results if f["configuration"].startswith(S14.PRIMARY_SCENARIO)),
                     key=lambda f: f["label"])
    blocks, games_by_policy = {}, {}
    for name in policies:
        games, seats, pooled = {}, {}, collections.Counter()
        for f in primary:
            p = f["policies"][name]
            games[f["label"]] = {**summarize(p), "cell": f["cell"]}
            seat = seats.setdefault(f["cell"], collections.Counter())
            seat["post_opening_units"] += p["post_opening_units"]
            seat["redirects"] += p["redirects"]
            seat["emitted"] += p["emitted_ground"]
            seat["post_slot_vs_t9-v1"] += p["post_slot_vs_t9"]
            seat["slot_vs_t9-v1"] += p["slot_vs_t9"]
            pooled["post_slot_vs_t9-v1"] += p["post_slot_vs_t9"]
            pooled["slot_vs_t9-v1"] += p["slot_vs_t9"]
            pooled["orders_vs_baseline-v2"] += p["orders_vs"]["baseline-v2"]
            pooled["orders_vs_t9-v1"] += p["orders_vs"]["t9-v1"]
            pooled["orders_vs_v3"] += p["orders_vs"]["v3"]
            pooled["redirects"] += p["redirects"]
        blocks[name] = {"games": games, "seats": {c: dict(sorted(s.items())) for c, s in sorted(seats.items())},
                        "pooled": dict(sorted(pooled.items()))}
        games_by_policy[name] = games
    return blocks, games_by_policy


def opportunity_of(blocks: Mapping[str, Any]) -> Dict[str, Any]:
    out = {}
    for seat in ("H1", "H2"):
        t9 = blocks["t9-v1"]["seats"][seat]["post_opening_units"]
        out[seat] = {"t9-v1_post_opening_units": t9,
                     "o2_post_opening_units": blocks["O2"]["seats"][seat]["post_opening_units"],
                     "batch_post_opening_units": blocks["batch-value-redirect"]["seats"][seat]["post_opening_units"],
                     "required": max(s15.GATE["restore_units_min"],
                                     math.ceil(s15.GATE["restore_units_ratio_min"] * t9))}
    return out


def trajectory_key(f: Mapping[str, Any]) -> str:
    return f"{f['label']} ({f['played']} trajectory)"


def diagnose_combine(results, shooters) -> Dict[str, Any]:
    facts = {f["game"]: f for f, _ in results}
    private = {p["game"]: p for _, p in results}
    policies = s15.REFERENCES
    blocks, games = primary_rows(results, policies)
    fidelity = check_fidelity(facts, games)
    decomposition: Dict[str, Any] = {}
    for gid, f in sorted(facts.items()):
        claims = private[gid]["claims"]
        opening_overflow = {c["unit"] for c in claims if c["ordinal"] == 1 and c["overflow"]}
        row = {"active_decisions": f["policies"]["v3"]["active_decisions"],
               "opening_overflow_units": len(opening_overflow), "policies": {}}
        for name in ("t9-v1", "O2", "batch-value-redirect"):
            rows = private[gid]["redirects"][name]
            post = [r for r in rows if r["ordinal"] > 1]
            pairs = collections.Counter((r["unit"], r["from"]) for r in rows)
            row["policies"][name] = {
                "redirects": len(rows), "redirected_units": len({r["unit"] for r in rows}),
                "buckets": {b: sum(1 for r in rows if s15.bucket(r["ordinal"]) == b) for b in s15.BUCKETS},
                "post_opening_redirects": len(post), "post_opening_units": len({r["unit"] for r in post}),
                "redirects_by_opening_overflow_units": sum(1 for r in rows if r["unit"] in opening_overflow),
                "post_opening_units_never_opening_overflow": len({r["unit"] for r in post} - opening_overflow),
                "unit_source_pairs_redirected_more_than_once": sum(1 for v in pairs.values() if v > 1),
                "largest_repeat": max(pairs.values(), default=0)}
        decomposition.setdefault(f["configuration"], {})[trajectory_key(f)] = row
    first_post = {}
    for gid, f in sorted(facts.items()):
        if not f["configuration"].startswith(S14.PRIMARY_SCENARIO):
            continue
        rows = [r for r in private[gid]["redirects"]["O2"] if r["ordinal"] > 1]
        first = min(rows, key=lambda r: r["k"]) if rows else None
        first_post[f["label"]] = {"decision": first["k"] if first else None,
                                  "step": first["cur_step"] if first else None,
                                  "post_opening_opportunity_observations": len(rows)}
    shooter_rows: Dict[str, Any] = {}
    for config, units in sorted(shooters.items()):
        for gid, f in sorted(facts.items()):
            if f["configuration"] != config:
                continue
            claims = private[gid]["claims"]
            opening_overflow = {c["unit"] for c in claims if c["ordinal"] == 1 and c["overflow"]}
            rows = []
            for unit_id, fire_k in sorted(units.items(), key=lambda x: (x[1], x[0])):
                mine = [c for c in claims if c["unit"] == unit_id and c["k"] < fire_k]
                rows.append({"firing_decision": fire_k, "opening_overflow": unit_id in opening_overflow,
                             "claims_before_firing": len(mine),
                             "overflow_claims_before_firing": sum(1 for c in mine if c["overflow"]),
                             "o2_opportunities_before_firing": sum(1 for c in mine if c["o2"]),
                             "post_opening_o2_opportunities_before_firing": sum(
                                 1 for c in mine if c["o2"] and c["ordinal"] > 1),
                             "fire_listed_at_claims": sum(c["fire_listed"] for c in mine)})
            shooter_rows.setdefault(config, {})[trajectory_key(f)] = rows
    feature_rows = []
    for gid, p in sorted(private.items()):
        config = facts[gid]["configuration"]
        label = "PRIMARY" if config.startswith(S14.PRIMARY_SCENARIO) else (
            "ADVERSE" if config.startswith("1930331196") else "UNLABELLED")
        seen = set()
        for r in p["features"]:
            key = (r["unit"], r["opening"])
            if key in seen:
                continue  # first opportunity per unit and phase: repeats on recorded states are not new situations
            seen.add(key)
            feature_rows.append({**{k: r[k] for k in FEATURES}, "opening": r["opening"], "label": label,
                                 "group": config})
    feature_tables = {}
    for phase, keep in (("all", lambda r: True), ("opening", lambda r: r["opening"]),
                        ("post_opening", lambda r: not r["opening"])):
        rows = [r for r in feature_rows if keep(r)]
        by_group = {}
        for group in sorted({r["group"] for r in rows}):
            members = [r for r in rows if r["group"] == group]
            by_group[group] = {"rows": len(members), "label": members[0]["label"],
                               "features": {k: s15.distribution([m[k] for m in members]) for k in FEATURES}}
        feature_tables[phase] = {"groups": by_group, "rule_search": s15.rule_search(rows, FEATURES)}
    geometry, proxy = {}, {}
    for gid, p in sorted(private.items()):
        f = facts[gid]
        key = f"{f['configuration']} {trajectory_key(f)}"
        g = p["geometry"]
        geometry[key] = {"overflow_units": len(g), "staged": sum(1 for r in g if r["form"] == "STAGE"),
                         "with_an_objective_within_twice_from_the_staging_end": sum(
                             1 for r in g if r["objectives_within_twice"] > 0),
                         "own_cost_from_staging_end": s15.distribution([r["own_cost_from_end"] for r in g])}
        if p["proxy"] is not None:
            rows = list(p["proxy"]["pinned"].values())
            class_rows = [r for r in rows if r["actual_first_claim"]]
            agree = sum(1 for r in class_rows if (r["proxy_first"] is not None and r["proxy_first"][0] ==
                                                  r["actual_first_claim"][0]) == bool(r["actual_first_claim"][2]))
            proxy[key] = {"pinned_units": len(rows),
                          "proxy_redirect_opportunity_units": sum(1 for r in rows if r["proxy_first"]),
                          "proxy_given_a_place_units": sum(1 for r in rows if r["left"] == "a place"),
                          "known_answer": f["played"] == "v3",
                          "units_with_a_recorded_post_opening_claim": len(class_rows),
                          "ready_step_equals_first_claim_step": sum(
                              1 for r in class_rows if r["ready"] == r["actual_first_claim"][1]),
                          "recorded_first_claim_was_an_o2_opportunity": sum(
                              1 for r in class_rows if r["actual_first_claim"][2]),
                          "proxy_agrees_on_that_claim": agree,
                          "proxy_first_opportunity_steps": s15.distribution(
                              [r["proxy_first"][1] for r in rows if r["proxy_first"]])}
    episodes = {}
    unheld_baseline = {f["configuration"]: f["unheld"] for f in facts.values() if f["played"] == "baseline-v2"}
    for path in t9v2_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        parts = path.name.split(".")
        config = f"{parts[0]} {parts[1]}"
        eps = (data.get("t9_v2") or {}).get("withhold_episodes") or []
        units = shooters.get(config, {})
        timeline = unheld_baseline.get(config, {})
        rows = []
        for e in eps:
            if e["obj_id"] in units and e["start"] < units[e["obj_id"]]:
                prior = [int(k) for k in timeline if int(k) <= e["start"]]
                rows.append({"firing_decision": units[e["obj_id"]], "episode_start": e["start"],
                             "decisions": e["decisions"], "gap_to_firing": units[e["obj_id"]] - e["start"],
                             "unheld_objectives_on_the_baseline_trajectory_then":
                                 timeline[str(max(prior))] if prior else None})
        episodes[f"{config} {parts[3]}"] = {
            "withhold_episodes": len(eps), "withheld_units": len({e["obj_id"] for e in eps}),
            "longest": max((e["decisions"] for e in eps), default=0),
            "shooter_episodes_starting_before_firing": sorted(
                rows, key=lambda r: (r["firing_decision"], r["episode_start"]))}
    return {"schema": SCHEMA, "note": NOTE, "sprint14_inputs_sha256": sha256(S14.INPUTS),
            "t9_v2_captures": [{"file": p.name, "sha256": sha256(p)} for p in t9v2_files()],
            "fidelity_problems": fidelity, "decomposition": decomposition,
            "reference_opportunity": opportunity_of(blocks), "primary_first_post_opening_opportunity": first_post,
            "shooters": shooter_rows, "features": feature_tables, "staging_geometry": geometry,
            "staging_proxy": proxy, "t9_v2_withhold_episodes": episodes,
            "reference_primary": {n: {"seats": blocks[n]["seats"], "pooled": blocks[n]["pooled"]} for n in policies}}


def adverse_rows(facts, private, shooters, policies, fidelity) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    by_config: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for f in facts.values():
        if not f["configuration"].startswith(S14.PRIMARY_SCENARIO):
            by_config[f["configuration"]].append(f)
    anchors, out = {}, {name: {} for name in policies}
    v3_cert = None
    for config, members in sorted(by_config.items()):
        played = {g["played"]: g for g in members}
        anchors[config] = {"first_decision_state_identical":
                           played["t9-v1"]["first_state_sha256"] == played["baseline-v2"]["first_state_sha256"]}
        missed = None
        if config == "2120531121 C3":
            names = private[played["t9-v1"]["game"]]["names"]
            values = {c: int(n.split("-")[0]) for c, n in names.items()}
            faction = played["t9-v1"]["seat_faction"]
            never = [c for c, hist in played["t9-v1"]["flags"].items()
                     if values[c] == 80 and all(fl != faction for _, fl in hist)]
            if len(never) != 1:
                fidelity.append(f"{config}: expected one 80-point objective T9-v1 never owned, found {len(never)}")
            else:
                missed = never[0]
                captured = next((k for k, fl in played["baseline-v2"]["flags"][missed] if fl == faction), None)
                if captured != sx.ADVERSE_FACTS[config]["baseline_capture_decision"]:
                    fidelity.append(f"{config}: baseline-v2 first owned the missed objective at decision {captured}")
                anchors[config].update(missed_label=names[missed], baseline_capture_decision=captured,
                                       baseline_capture_step=played["baseline-v2"]["steps_at"][str(captured)])
        else:
            units = shooters.get(config, {})
            anchors[config].update(shooters=len(units),
                                   firing_decisions=sorted(set(units.values())))
            if sorted(set(units.values())) != sorted(sx.ADVERSE_FACTS[config]["fire_decisions"]):
                fidelity.append(f"{config}: shooters' firing decisions differ from the registered ones")
            own = played["t9-v1"]["policies"]["t9-v1"]["first_decision_redirects"]
            if own != sx.ADVERSE_FACTS[config]["t9v1_first_decision_redirects"]:
                fidelity.append(f"{config}: T9-v1 redirects {own} at the first decision of its own game")
        for name in policies:
            rows_all = {g["played"]: private[g["game"]]["redirects"][name] for g in members}
            row: Dict[str, Any] = {g["played"]: summarize(g["policies"][name]) for g in members}
            row["first_decision_redirects"] = max(g["policies"][name]["first_decision_redirects"] for g in members)
            row["first_decision_redirects_own_game"] = played["t9-v1"]["policies"][name]["first_decision_redirects"]
            if name in s15.CANDIDATES:
                window = s15.RISK_WINDOW[config]
                row["trigger_exposure_in_window"] = sum(
                    1 for g in members for e in private[g["game"]]["exposure"][name] if e["k"] < window)
                row["trigger_exposure_total"] = sum(len(private[g["game"]]["exposure"][name]) for g in members)
                row["memory_metrics"] = {g["played"]: memory_summary(g["policies"][name]) for g in members}
            if config == "2120531121 C3":
                cap_step = anchors[config].get("baseline_capture_step")
                missed_label = anchors[config].get("missed_label")
                far = [r for rows in rows_all.values() for r in rows if r["to_label"] == missed_label
                       and cap_step is not None and r["cur_step"] < cap_step and r["free_flow"] is not None
                       and r["cur_step"] + r["free_flow"] > cap_step]
                row.update(unreachable_places=sum(g["policies"][name]["violations"].get(
                    "place for a unit that cannot arrive before the end", 0) for g in members),
                    v3_selection_not_kept=sum(g["policies"][name]["violations"].get("a v3 selection not kept", 0)
                                              for g in members),
                    certificate_unit_decisions=played["t9-v1"]["policies"][name]["certificate"].get(str(missed), 0),
                    redirects_into_missed=sum(1 for rows in rows_all.values() for r in rows
                                              if r["to_label"] == missed_label),
                    sprint14_registered_far_reservations=len(far))
                if name == "v3":
                    v3_cert = row["certificate_unit_decisions"]
            else:
                units = shooters.get(config, {})
                hit = [r for rows in rows_all.values() for r in rows if r["unit"] in units and r["k"] < units[r["unit"]]]
                first_fire = min(sx.ADVERSE_FACTS[config]["fire_decisions"])
                row.update(shooters_redirected=len(hit),
                           early_redirects_baseline=sum(1 for r in rows_all["baseline-v2"] if r["k"] < first_fire),
                           redirects_in_risk_window=sum(1 for rows in rows_all.values() for r in rows
                                                        if r["k"] < s15.RISK_WINDOW[config]))
                if name in s15.CANDIDATES:
                    row["shooter_memory_before_firing"] = {
                        g["played"]: {fk: dict(sorted(c.items())) for fk, c in
                                      sorted(g["shooter_states"].get(name, {}).items())} for g in members}
            out[name][config] = row
    if v3_cert != sx.ADVERSE_FACTS["2120531121 C3"]["v3_certificate_unit_decisions"]:
        fidelity.append(f"2120531121 C3: v3 admits {v3_cert} certificate unit-decisions")
    return anchors, out, v3_cert


def run_combine(results, h0, shooters, timing) -> Dict[str, Any]:
    facts = {f["game"]: f for f, _ in results}
    private = {p["game"]: p for _, p in results}
    policies = s15.POLICIES
    blocks, games = primary_rows(results, policies)
    fidelity = check_fidelity(facts, games)
    for name, expected in sx.S13_EXPECTED["pooled"].items():
        pooled = blocks[name]["pooled"]
        for key, value in expected.items():
            if pooled.get(key) != value:
                fidelity.append(f"{name} pooled {key} {pooled.get(key)} differs from Sprint 13's {value}")
    primary_ids = sorted(g for g, f in facts.items() if f["configuration"].startswith(S14.PRIMARY_SCENARIO))
    for name in s15.CANDIDATES:
        blocks[name]["pooled"]["oscillations"] = sum(s15.oscillations(
            [(r["k"], r["unit"], r["from"], r["to"]) for r in private[g]["redirects"][name]]) for g in primary_ids)
        blocks[name]["pooled"]["max_redirects_per_unit_game"] = max(
            [n for g in primary_ids for n in collections.Counter(r["unit"] for r in private[g]["redirects"][name])
             .values()], default=0)
        for g in primary_ids:
            blocks[name]["games"][facts[g]["label"]]["memory_metrics"] = memory_summary(facts[g]["policies"][name])
        rows = [r for g in primary_ids for r in private[g]["redirects"][name]]
        blocks[name]["redirect_descriptives"] = {
            "free_flow_steps": s15.distribution([r["free_flow"] for r in rows]),
            "detour_ratio": s15.distribution([r["detour"] for r in rows]),
            "kinds": dict(sorted(collections.Counter({1: "infantry", 2: "vehicle"}.get(r["kind"], "other")
                                                     for r in rows).items())),
            "destinations": dict(sorted(collections.Counter(f"{r['from_label']} -> {r['to_label']}"
                                                            for r in rows).items()))}
    anchors, adverse_blocks, _ = adverse_rows(facts, private, shooters, policies, fidelity)
    h0_public, h0_tot = {}, {n: collections.Counter() for n in s15.CANDIDATES}
    for game in h0:
        h0_public[game["scenario"]] = {"checks": dict(sorted(game["checks"].items())), "policies": {
            n: {"active_decisions": p["active_decisions"], "redirects": p["redirects"],
                "redirected_units": p["redirected_units"], "oscillations": p.get("oscillations"),
                "max_redirects_per_unit_game": p.get("max_redirects_per_unit_game"),
                "overflow_observations": p["overflow_observations"], "trigger_held": p["eligible_observations"],
                "violations": dict(sorted((k, v) for k, v in p["violations"].items() if v)),
                "repeat": dict(sorted(p["repeat"].items())), "memory_checks": p["memory_checks"],
                "memory_problems": p["memory_problems"], "max_records": p["max_records"],
                "records_ended": dict(sorted(p["ended"].items()))} for n, p in game["policies"].items()}}
        for name in s15.CANDIDATES:
            p = game["policies"][name]
            for key, value in p["violations"].items():
                h0_tot[name][f"v:{key}"] += value
            for key, value in p["repeat"].items():
                h0_tot[name][f"r:{key}"] += value
            h0_tot[name]["memory_checks"] += p["memory_checks"]
            h0_tot[name]["memory_problems"] += p["memory_problems"]
            h0_tot[name]["oscillations"] += p["oscillations"] or 0
            h0_tot[name]["max_redirects_per_unit_game"] = max(h0_tot[name]["max_redirects_per_unit_game"],
                                                              p["max_redirects_per_unit_game"])
    static = static_checks()
    gates, adequacies, passing = {}, {}, {}
    for name in s15.CANDIDATES:
        violations, repeat = collections.Counter(), collections.Counter()
        memory = collections.Counter()
        for f in facts.values():
            violations.update(f["policies"][name]["violations"])
            repeat.update(f["policies"][name]["repeat"])
            memory["memory_checks"] += f["policies"][name]["memory_checks"]
            memory["memory_problems"] += f["policies"][name]["memory_problems"]
        h = h0_tot[name]
        for key, value in h.items():
            if key.startswith("v:"):
                violations[key[2:]] += value
            elif key.startswith("r:"):
                repeat[key[2:]] += value
        invariants = {"repeat_comparisons": repeat["repeat_comparisons"], "repeat_differences": repeat["repeat_differences"],
                      "order_comparisons": repeat["order_comparisons"], "order_differences": repeat["order_differences"],
                      "violations": dict(violations), "memory_checks": memory["memory_checks"] + h["memory_checks"],
                      "memory_problems": memory["memory_problems"] + h["memory_problems"]}
        blocks[name]["pooled"]["oscillations"] += h["oscillations"]  # H0 oscillations count against recourse too
        blocks[name]["pooled"]["max_redirects_per_unit_game"] = max(blocks[name]["pooled"]["max_redirects_per_unit_game"],
                                                                    h["max_redirects_per_unit_game"])
        gate_facts = {"candidates": {name: {"invariants": invariants, "primary": blocks[name],
                                            "adverse": adverse_blocks[name], "latency_ms": timing["candidates"][name]}},
                      "references": {ref: {"primary": blocks[ref], "adverse": adverse_blocks[ref]}
                                     for ref in ("t9-v1", "v3", "O2")},
                      "static": static}
        gates[name] = s15.gate(name, gate_facts)
        adequacies[name] = s15.adequacy(name, gate_facts)
        if gates[name]["pass"] and adequacies[name]["all_tested"]:
            passing[name] = {"gate": gates[name], "post_slot": blocks[name]["pooled"]["post_slot_vs_t9-v1"],
                             "redirects": blocks[name]["pooled"]["redirects"],
                             "latency_p99": timing["candidates"][name]["p99"]}
    opportunity = opportunity_of(blocks)
    selection = s15.select(passing)
    verdict = s15.disposition(fidelity, gates, adequacies, opportunity, selection)
    return {
        "replay": {"schema": SCHEMA, "note": NOTE, "inputs_sha256": sha256(INPUTS),
                   "primary": {name: blocks[name] for name in policies}},
        **{stem: {"schema": SCHEMA, "note": NOTE, "configuration": config, "anchors": anchors.get(config),
                  "policies": {name: adverse_blocks[name].get(config) for name in policies}}
           for config, stem in ADVERSE_FILES.items()},
        "generalisation": {"schema": SCHEMA, "note": "H0: baseline-v0 mirror games, both seats, baseline-v2 "
                           "reconstructed; states no T9 policy reached; invariants and trigger prevalence only",
                           "games": h0_public},
        "gate": {"schema": SCHEMA, "note": NOTE, "thresholds": s15.GATE, "risk_windows": s15.RISK_WINDOW,
                 "static": static, "fidelity_problems": fidelity, "opportunity": opportunity, "gates": gates,
                 "adequacy": adequacies, "selection": selection, "disposition": verdict,
                 "timing_sha256": sha256(TIMING) if TIMING.exists() else None},
    }


def timing_of(results, h0) -> Dict[str, Any]:
    out = {"candidates": {}, "t9-v1": None, "note": "milliseconds per decision with an own ground move (ten captures "
           "and H0), measured once in the replay's worker processes; not regenerated by --check"}
    for name in s15.CANDIDATES + ("t9-v1",):
        values = [v for f, _ in results for v in f["policies"][name]["latency"]]
        if name != "t9-v1":
            values += [v for g in h0 for v in g["policies"][name]["latency"]]
        row = {"decisions": len(values), "p50": round(s15.percentile(values, 0.5), 3),
               "p99": round(s15.percentile(values, 0.99), 3), "max": round(max(values) if values else 0.0, 3)}
        if name == "t9-v1":
            out["t9-v1"] = row
        else:
            out["candidates"][name] = row
    return out


def private_values(results) -> set:
    values = set()
    for _, p in results:
        for rows in p["redirects"].values():
            for r in rows:
                values.update({r["from"], r["to"]})
        values.update(int(c) for c in p["names"])
    return values


def jobs(mode: str, shooters: Mapping[str, Mapping[int, int]]):
    return ([(mode, "primary", g, {}) for g in S14.primary_games()]
            + [(mode, "adverse", e, shooters.get(e[0], {})) for e in S14.ADVERSE])


def shooter_table(pool) -> Dict[str, Dict[int, int]]:
    baseline = [e for e in S14.ADVERSE if e[6] == "baseline-v2" and e[0] != "2120531121 C3"]
    return dict(pool.map(shooters_of, baseline))


def write_or_check(texts: Mapping[str, str], check: bool) -> int:
    if check:
        bad = [n for n, t in texts.items() if (OUT_DIR / f"{n}.json").read_text(encoding="utf-8") != t]
        if bad:
            print(f"MISMATCH: {bad}")
            return 1
        print("OK: public files regenerate byte for byte")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (OUT_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
    return 0


def public_texts(public: Mapping[str, Any], results) -> Dict[str, str]:
    hidden = private_values(results)
    for name, data in public.items():
        found = s15.public_check(data, hidden)
        if found:
            raise SystemExit(f"refused: {name}.json would publish private values: {found[:5]}")
    return {name: dump(data) for name, data in public.items()}


def save_private(name: str, shooters, results) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with gzip.open(PRIVATE / name, "wt", encoding="utf-8") as handle:
        json.dump({"shooters": {c: {str(u): k for u, k in v.items()} for c, v in shooters.items()},
                   "private": [p for _, p in results]}, handle, sort_keys=True, default=str)


def diagnose(args: argparse.Namespace) -> int:
    S14.require_inputs()
    with multiprocessing.get_context("fork").Pool(args.workers) as pool:
        shooters = shooter_table(pool)
        results = pool.map(process, jobs("diagnose", shooters), chunksize=1)
    data = diagnose_combine(results, shooters)
    if data["fidelity_problems"]:
        print(json.dumps(data["fidelity_problems"], indent=1))
    code = write_or_check(public_texts({"diagnostics": data}, results), args.check)
    if not args.check:
        save_private("diagnostics-private.json.gz", shooters, results)
    return code


def run(args: argparse.Namespace) -> int:
    require_inputs()
    with multiprocessing.get_context("fork").Pool(args.workers) as pool:
        shooters = shooter_table(pool)
        results = pool.map(process, jobs("run", shooters), chunksize=1)
        h0 = pool.map(process_h0, [str(p) for p, _ in h0_files()], chunksize=1)
    if args.check or TIMING.exists():
        timing = json.loads(TIMING.read_text(encoding="utf-8"))
    else:
        timing = timing_of(results, h0)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        TIMING.write_text(dump(timing), encoding="utf-8", newline="\n")
    public = run_combine(results, h0, shooters, timing)
    code = write_or_check(public_texts(public, results), args.check)
    if not args.check:
        save_private("replay-private.json.gz", shooters, results)
        print(json.dumps(public["gate"]["disposition"], indent=1))
    return code


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("diagnose", "freeze", "run"):
        p = sub.add_parser(command)
        p.add_argument("--check", action="store_true")
        p.add_argument("--workers", type=int, default=12)
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
    return diagnose(args) if args.command == "diagnose" else run(args)


if __name__ == "__main__":
    sys.exit(main())
