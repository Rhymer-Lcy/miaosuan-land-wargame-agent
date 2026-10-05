"""Sprint 14 offline design competition replay (``docs/SPRINT14_REDISTRIBUTION.md``), server only.

    python scripts/s14_design_replay.py freeze [--check]   # evaluation/s14-redistribution-design/inputs.json
    python scripts/s14_design_replay.py run [--check] [--workers N]

``freeze`` pins, by SHA-256, every private input the replay reads (the four Sprint 12 primary games' records and
timelines, the six Sprint 10 diagnostic captures, and the cost data of the three scenarios), recomputes the frozen
policy identities from the checkout and refuses to write if any differs, and records the identity of the Sprint 14
candidate module. ``run`` requires every pin to hold, replays every decision of the ten captures (one worker process
per capture), checks the replay's fidelity (``baseline-v2`` re-decided equals the capture; v3 equals what the v3 seat
played and its captured allocation; T9-v1 equals what the T9-v1 seats played and Sprint 10's captured audit; the
``feasible-value-redirect`` rule equals Sprint 13's oracle O2; the four games reproduce Sprint 13's published
figures) and then evaluates the frozen gate, the rubric and the disposition. Public output under
``evaluation/s14-redistribution-design/``; private rows under ``local/diagnostics/s14/``. ``--check`` regenerates the
public files in memory and compares them byte for byte; decision latency is measured once and kept in ``timing.json``,
which ``--check`` reads instead of re-measuring. No engine is opened and the ledger is not read.
"""

from __future__ import annotations

import argparse
import ast
import collections
import gzip
import hashlib
import inspect
import json
import multiprocessing
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s14_design as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t9_redistribution as tr  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402

SCHEMA_INPUTS = "miaosuan-s14-inputs/1"
SCHEMA = "miaosuan-s14-design/1"
OUT_DIR = REPO_ROOT / "evaluation" / "s14-redistribution-design"
INPUTS = OUT_DIR / "inputs.json"
PUBLIC = ("replay", "adverse", "gate")
TIMING = OUT_DIR / "timing.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s14"
EV = REPO_ROOT / "local" / "evaluation"
V3_POLICY_NAME = "t9-batch-capacity-v3"  # the Sprint 12 record's seat label; never written to a public file
NOTE = ("offline design competition on recorded states: every policy is an action-level decision on states another "
        "policy produced; nothing here is an engine outcome, a score estimate or evidence of an effect")

#: The frozen policy-source identities (docs/SPRINT14_REDISTRIBUTION.md, section 1).
FROZEN = {
    "baseline-v2": "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae",
    "t9-v1": "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa",
    "t9-v2": "66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece",
    "v3": "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8",
}
ADDON_MODULES = {"baseline-v2": (), "t9-v1": ("experiments/exploratory_addon.py", "experiments/t9_allocation.py"),
                 "t9-v2": ("experiments/exploratory_addon.py", "experiments/t9_staging.py"),
                 "v3": ("experiments/exploratory_addon.py", "experiments/t9_batch.py")}
CANDIDATE_MODULES = ("experiments/exploratory_addon.py", "experiments/t9_batch.py", "experiments/t9_redistribution.py")

PRIMARY_CARD = "s12-v3-primary-1"
PRIMARY_SCENARIO = "2130511121"
#: (configuration, card, game id, scenario, map id, diagnosed seat, policy that played the seat)
ADVERSE = (
    ("2120531121 C3", "s10-t9-v1-diagnosis", "2120531121.C3.s10-t9-v1-diagnosis.g01", "2120531121", "21", 11, "t9-v1"),
    ("2120531121 C3", "s10-t9-v1-diagnosis", "2120531121.C3.s10-t9-v1-diagnosis.g02", "2120531121", "21", 11,
     "baseline-v2"),
    ("1930331196 C3", "s10-t9-v1-diagnosis", "1930331196.C3.s10-t9-v1-diagnosis.g03", "1930331196", "96", 11, "t9-v1"),
    ("1930331196 C3", "s10-t9-v1-diagnosis", "1930331196.C3.s10-t9-v1-diagnosis.g04", "1930331196", "96", 11,
     "baseline-v2"),
    ("1930331196 C2", "s10-t9-v1-c2-diagnosis", "1930331196.C2.s10-t9-v1-c2-diagnosis.g01", "1930331196", "96", 1,
     "t9-v1"),
    ("1930331196 C2", "s10-t9-v1-c2-diagnosis", "1930331196.C2.s10-t9-v1-c2-diagnosis.g02", "1930331196", "96", 1,
     "baseline-v2"),
)
ALLOWED_LITERALS = {0, 1, 2, 2.0, 4, 300, 720, 1440, 0.25, 0.5, 0.75, 1_000_000}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def tree_digest(root: Path) -> Dict[str, Any]:
    rows = sorted((p.relative_to(root).as_posix(), sha256(p)) for p in root.rglob("*") if p.is_file())
    digest = hashlib.sha256("".join(f"{name}\0{value}\n" for name, value in rows).encode("utf-8")).hexdigest()
    return {"files": len(rows), "sha256": digest}


def policy_digests() -> Dict[str, str]:
    base = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
    return {name: digest_of_files(policy_source_files(sources=base + extra)) for name, extra in ADDON_MODULES.items()}


def candidate_identity() -> Dict[str, Any]:
    base = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
    files = policy_source_files(sources=base + CANDIDATE_MODULES)
    return {"policy_source_sha256": digest_of_files(files), "module_files": list(CANDIDATE_MODULES),
            "rules": {name: {"identity": r.identity, "rank": r.rank, "horizon": r.horizon, "min_prefix": r.min_prefix,
                             "batch": r.batch} for name, r in tr.RULES.items()}}


def static_checks() -> Dict[str, bool]:
    """G2/G13 (inputs) and G14 (literals), read from the candidate module's source."""
    source = Path(tr.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    parameters = tuple(inspect.signature(tr.allocate).parameters)
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}
    return {"seat_local": (not any("evaluation" in m or "engine" in m for m in imported)
                           and parameters == ("observation", "seat", "faction", "actions", "router", "rule")),
            "no_special_case_literal": literals <= ALLOWED_LITERALS}


def primary_games() -> List[Dict[str, Any]]:
    manifest = json.loads((REPO_ROOT / "evaluation" / PRIMARY_CARD / "manifest.json").read_text(encoding="utf-8"))
    return [{"game_id": g["game_id"], "cell": g["condition"], "label": g["game_id"].rsplit(".", 1)[-1]}
            for g in manifest["games"]]


def primary_files(gid: str) -> Dict[str, Path]:
    base = EV / PRIMARY_CARD
    return {"record": base / "games" / f"{gid}.json", "timeline.json": base / "capture" / f"{gid}.timeline.json",
            "timeline.pkl": base / "capture" / f"{gid}.timeline.pkl"}


def adverse_file(entry: Sequence[Any]) -> Path:
    return EV / entry[1] / "capture" / f"{entry[2]}.windows.pkl"


def build_inputs() -> Dict[str, Any]:
    digests = policy_digests()
    wrong = sorted(k for k, v in digests.items() if v != FROZEN[k])
    if wrong:
        raise SystemExit(f"refused: policy identities differ from the frozen values: {wrong}")
    primary = []
    for game in primary_games():
        primary.append({**game, "files": {k: sha256(p) for k, p in primary_files(game["game_id"]).items()}})
    adverse = [{"configuration": e[0], "game_id": e[2], "played": e[6], "seat": e[5],
                "windows_sha256": sha256(adverse_file(e))} for e in ADVERSE]
    data = {"primary_cost": tree_digest(EV / PRIMARY_CARD / "data" / PRIMARY_SCENARIO),
            "s10_cost": tree_digest(EV / "s10-t9-v1-diagnosis" / "data"),
            "s10_c2_cost": tree_digest(EV / "s10-t9-v1-c2-diagnosis" / "data")}
    if len(primary) != 4 or len(adverse) != 6:
        raise SystemExit("refused: expected 4 primary and 6 adverse captures")
    return {"schema": SCHEMA_INPUTS, "frozen_policies_checked": sorted(digests), "candidates": candidate_identity(),
            "primary": {"card": PRIMARY_CARD, "games": primary}, "adverse": adverse, "cost_data": data,
            "gate_thresholds": sx.GATE, "s13_expected": sx.S13_EXPECTED,
            "adverse_facts": {k: {kk: list(vv) if isinstance(vv, tuple) else vv for kk, vv in v.items()}
                              for k, v in sx.ADVERSE_FACTS.items()},
            "note": "private inputs pinned before the Sprint 14 replay; files stay under the ignored local/ tree"}


def require_inputs() -> Mapping[str, Any]:
    committed = INPUTS.read_text(encoding="utf-8")
    if dump(build_inputs()) != committed:
        raise SystemExit("refused: an input, an identity or a threshold differs from inputs.json")
    return json.loads(committed)


def costs_for(card: str, scenario: str, map_id: str) -> MoveCosts:
    inputs = sdk_data.load_inputs(EV / card / "data" / scenario / "Data", scenario, map_id)
    return MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")


# ------------------------------------------------------------------------------------------------
# Decisions of one capture


def primary_stream(gid: str):
    files = primary_files(gid)
    record = json.loads(files["record"].read_text(encoding="utf-8"))
    seat = next(s["seat"] for s in record["seats"] if s["policy"] == V3_POLICY_NAME)
    faction = next(s["faction"] for s in record["seats"] if s["policy"] == V3_POLICY_NAME)
    timeline = json.loads(files["timeline.json"].read_text(encoding="utf-8"))
    with files["timeline.pkl"].open("rb") as handle:
        windows = pickle.load(handle)
    _, raws = tl.load_states(windows, seat, faction)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    memories = [pickle.loads((s["seats"].get(seat) or s["seats"].get(str(seat)))["memory"]) for s in samples]
    del windows, samples
    steps = timeline["steps"]
    rows = []
    for k in range(len(steps)):
        row = (steps[k].get("s12") or {}).get(str(seat)) or {}
        rows.append({"k": k, "raw": raws[k], "memory": memories[k], "baseline": row.get("baseline_actions"),
                     "trace": row.get("baseline_trace_sha256"), "allocation": row.get("allocation"),
                     "submitted": [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == seat]})
    return seat, faction, rows


def adverse_stream(entry: Sequence[Any]):
    seat = entry[5]
    with adverse_file(entry).open("rb") as handle:
        samples = pickle.load(handle)["samples"]
    rows, faction = [], None
    for sample in sorted(samples, key=lambda s: s["k"]):
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        if snap is None:
            raise SystemExit(f"{entry[2]}: no seat snapshot at k{sample['k']}")
        faction = snap["faction"]
        audit = snap.get("t9_audit") or {}
        rows.append({"k": sample["k"], "raw": pickle.loads(snap["observation"]), "memory": pickle.loads(snap["memory"]),
                     "baseline": snap["baseline_actions"], "trace": None, "allocation": None,
                     "t9_audit": audit.get("hypothetical_t9_actions"),
                     "submitted": [dict(a) for a in snap.get("submitted") or []]})
    if [r["k"] for r in rows] != list(range(len(rows))):
        raise SystemExit(f"{entry[2]}: samples are not one per decision")
    return seat, faction, rows


def new_policy_facts() -> Dict[str, Any]:
    return {"active_decisions": 0, "emitted_ground": 0, "redirects": 0, "redirected_units": set(), "keeps": 0,
            "stages": 0, "withholds": 0, "late_claimants": 0, "first_decision_redirects": None,
            "first_difference_k": None, "destinations": collections.Counter(), "violations": collections.Counter(),
            "slot_vs": collections.Counter(), "orders_vs": collections.Counter(), "order_units_vs": {},
            "max_commitment": 0, "repeat": collections.Counter(), "certificate": collections.Counter(),
            "latency": []}


def process(job: Tuple[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One capture: ``(facts, private)``; refuses (raises SystemExit) on any reconstruction disagreement."""
    kind, spec = job
    if kind == "primary":
        gid, label, cell = spec["game_id"], spec["label"], spec["cell"]
        costs = costs_for(PRIMARY_CARD, PRIMARY_SCENARIO, "21")
        seat, faction, rows = primary_stream(gid)
        played, config = "v3", f"{PRIMARY_SCENARIO} {cell}"
    else:
        config, card, gid, scenario, map_id, seat_, played = spec
        costs = costs_for(card, scenario, map_id)
        seat, faction, rows = adverse_stream(spec)
        label, cell = gid.rsplit(".", 1)[-1], config.split()[1]
    values = {c["coord"]: c.get("value") for c in (rows[0]["raw"].get("cities") or ())}
    names = tl.labels(values)
    facts: Dict[str, Any] = {"game": gid, "label": label, "cell": cell, "configuration": config, "played": played,
                             "decisions": len(rows), "policies": {n: new_policy_facts() for n in sx.POLICIES},
                             "problems": [], "flags": {}, "first_active_k": None, "first_state_sha256": None,
                             "seat_faction": faction, "steps_at": {}}
    private: Dict[str, Any] = {"game": gid, "redirects": {n: [] for n in sx.POLICIES}, "shooters": [],
                               "names": {str(c): n for c, n in names.items()}}
    problems = facts["problems"]
    fire_k: Dict[int, int] = {}
    if kind == "adverse":
        for row in rows:
            for action in row["submitted"]:
                if action.get("type") == 2 and row["k"] in sx.ADVERSE_FACTS.get(config, {}).get("fire_decisions", ()):
                    private["shooters"].append({"k": row["k"], "unit": action.get("obj_id")})
                    fire_k[action.get("obj_id")] = min(fire_k.get(action.get("obj_id"), row["k"]), row["k"])
    for row in rows:
        k, raw = row["k"], row["raw"]
        facts["steps_at"][str(k)] = (raw.get("time") or {}).get("cur_step")
        for city in raw.get("cities") or ():
            history = facts["flags"].setdefault(str(city["coord"]), [])
            if not history or history[-1][1] != city.get("flag"):
                history.append((k, city.get("flag")))
        observation = Observation.from_raw(raw, Origin.ENGINE)
        memory = row["memory"]
        base_memory = memory.baseline if isinstance(memory, AddonMemory) else memory
        decided = sx.decide_all(observation, seat, faction, base_memory, costs)
        if row["baseline"] is not None and rd.plain(decided["baseline-v2"]) != rd.plain(row["baseline"]):
            problems.append(f"k{k}: baseline-v2 re-decided differs from the capture")
        if row["trace"] is not None and decided["baseline_trace_sha256"] != row["trace"]:
            problems.append(f"k{k}: baseline-v2 trace digest differs from the capture")
        reference = {"v3": "v3", "t9-v1": "t9-v1", "baseline-v2": "baseline-v2"}[played]
        if rd.plain(decided[reference]) != rd.plain(row["submitted"]):
            problems.append(f"k{k}: {reference} differs from what the seat submitted")
        if row.get("t9_audit") is not None and rd.plain(decided["t9-v1"]) != rd.plain(row["t9_audit"]):
            problems.append(f"k{k}: T9-v1 differs from Sprint 10's captured audit")
        if rd.plain(decided["feasible-value-redirect"]) != rd.plain(decided["O2"]):
            problems.append(f"k{k}: feasible-value-redirect differs from Sprint 13's oracle O2")
        if not decided["active"]:
            for name in sx.CANDIDATES:
                if rd.plain(decided[name]) != rd.plain(decided["baseline-v2"]):
                    problems.append(f"k{k}: {name} changed a decision without own ground moves")
            continue
        if facts["first_active_k"] is None:
            facts["first_active_k"] = k
            facts["first_state_sha256"] = hashlib.sha256(json.dumps(raw, sort_keys=True, default=repr).encode()).hexdigest()
        v3 = decided["v3_allocation"]
        o2 = decided["O2_allocation"]
        a0 = decided["feasible-value-redirect_allocation"]
        if (a0.selected, {u: o.objective for u, o in a0.redirected.items()}, a0.staged, a0.withheld) != (
                o2.selected, {u: c for u, (_, c) in o2.redirected.items()}, o2.staged, o2.withheld):
            problems.append(f"k{k}: feasible-value-redirect's sets differ from O2's")
        if row["allocation"] is not None:
            cap = row["allocation"]
            if ({str(u): c for u, c in v3.selected.items()} != cap["selected"]
                    or {str(u): list(p) for u, p in v3.staged.items()} != cap["staged"]
                    or {str(u): r for u, r in v3.withheld.items()} != cap["withheld"]):
                problems.append(f"k{k}: v3's allocation differs from the captured allocation")
        ground = sx.own_ground(observation, faction)
        cities = {c.coord for c in (observation.cities() or ())}
        now = observation.time().cur_step
        base = decided["baseline-v2"]
        slot_sets = {n: sx.slots(decided[n], ground, cities) for n in sx.POLICIES}
        repeats = sx.repeat_checks(observation, seat, faction, base, costs, decided, f"{gid}-{k}")
        for name in sx.POLICIES:
            p = facts["policies"][name]
            p["active_decisions"] += 1
            allocation = decided.get(f"{name}_allocation")
            checks = sx.candidate_checks(observation, seat, faction, base, decided[name],
                                         allocation if name in sx.CANDIDATES else None,
                                         v3 if name in sx.CANDIDATES else None, costs)
            p["violations"].update(checks["violations"])
            p["max_commitment"] = max(p["max_commitment"], checks.get("max_commitment", 0))
            unit_forms = checks["forms"]
            p["emitted_ground"] += len(sx.ground_moves(decided[name], ground))
            counts = collections.Counter(unit_forms.values())
            p["redirects"] += counts[sx.REDIRECT]
            p["keeps"] += counts[sx.KEEP]
            p["stages"] += counts[sx.STAGE]
            p["withholds"] += counts[sx.WITHHOLD]
            p["redirected_units"] |= {u for u, f in unit_forms.items() if f == sx.REDIRECT}
            if k == facts["first_active_k"]:
                p["first_decision_redirects"] = counts[sx.REDIRECT]
            if p["first_difference_k"] is None and sx.order_divergence(decided[name], base, ground):
                p["first_difference_k"] = k
            for u, f in unit_forms.items():
                if u in fire_k and k < fire_k[u]:
                    p.setdefault("shooter_forms", collections.Counter())[f] += 1
            if allocation is not None and hasattr(allocation, "claimants"):
                p["late_claimants"] += sum(1 for c in allocation.claimants.values() if c.status == tr.LATE)
            for redirect in checks["redirects"]:
                p["destinations"][f"{names.get(redirect['from'])} -> {names.get(redirect['to'])}"] += 1
                private["redirects"][name].append({**redirect, "k": k, "cur_step": now,
                                                   "to_label": names.get(redirect["to"])})
            for ref in ("baseline-v2", "t9-v1", "v3", "O2"):
                p["slot_vs"][ref] += sx.slot_divergence(slot_sets[name], slot_sets[ref])
                changed = sx.order_divergence(decided[name], decided[ref], ground)
                p["orders_vs"][ref] += len(changed)
                p["order_units_vs"].setdefault(ref, set()).update(changed)
            if name in sx.CANDIDATES:
                p["repeat"].update(repeats[name])
                p["latency"].append(decided[f"{name}_ms"])
            elif name == "t9-v1":
                p["latency"].append(decided["t9-v1_ms"])
            # certificate (2120531121 C3): admitted claimants that T9-v1 held back, by objective, from decision 442
            if config == "2120531121 C3" and k >= sx.ADVERSE_FACTS[config]["certificate_from_decision"]:
                v1_forms = sx.forms(base, decided["t9-v1"], ground, cities)
                for u, action in sx.ground_moves(base, ground).items():
                    dest = list(action["move_path"])[-1]
                    if dest in cities and v1_forms.get(u) != sx.KEEP and unit_forms.get(u) == sx.KEEP:
                        p["certificate"][str(dest)] += 1
    if problems:
        raise SystemExit(f"refused: {gid}: {len(problems)} reconstruction problems, e.g. {problems[:3]}")
    for p in facts["policies"].values():
        p["redirected_units"] = len(p["redirected_units"])
        p["order_units_vs"] = {ref: len(units) for ref, units in p["order_units_vs"].items()}
    return facts, private


# ------------------------------------------------------------------------------------------------
# Combination, fidelity, gate


def seat_of(cell: str) -> str:
    return cell


def summarize(policy: Mapping[str, Any]) -> Dict[str, Any]:
    share = policy["redirects"] / policy["emitted_ground"] if policy["emitted_ground"] else 0.0
    return {"active_decisions": policy["active_decisions"], "emitted_ground_moves": policy["emitted_ground"],
            "redirects": policy["redirects"], "redirected_units": policy["redirected_units"],
            "redirect_share": round(share, 4), "keeps": policy["keeps"], "stages": policy["stages"],
            "withholds": policy["withholds"], "end_of_game_exclusions": policy["late_claimants"],
            "first_decision_redirects": policy["first_decision_redirects"],
            "first_difference_decision": policy["first_difference_k"],
            "destinations": dict(sorted(policy["destinations"].items())),
            "max_objective_commitment": policy["max_commitment"],
            "violations": dict(sorted((k, v) for k, v in policy["violations"].items() if v)),
            "slot_divergence": dict(sorted(policy["slot_vs"].items())),
            "order_divergence": dict(sorted(policy["orders_vs"].items())),
            "order_divergence_distinct": dict(sorted(policy["order_units_vs"].items())),
            "repeat": dict(sorted(policy["repeat"].items()))}


def redirect_descriptives(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {"slack_steps": sx.distribution([r["slack"] for r in rows]),
            "free_flow_steps": sx.distribution([r["free_flow"] for r in rows]),
            "detour_ratio": sx.distribution([r["detour"] for r in rows]),
            "prefix_share": sx.distribution([r["prefix"] / r["base_length"] for r in rows if r["base_length"]]),
            "prefix_hexes": sx.distribution([r["prefix"] for r in rows]),
            "kinds": dict(sorted(collections.Counter({1: "infantry", 2: "vehicle"}.get(r["kind"], "other")
                                                     for r in rows).items()))}


def combine(results: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]], timing: Mapping[str, Any]
            ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    facts = {f["game"]: f for f, _ in results}
    private = {p["game"]: p for _, p in results}
    primary = [f for f in facts.values() if f["configuration"].startswith(PRIMARY_SCENARIO)]
    adverse = [f for f in facts.values() if not f["configuration"].startswith(PRIMARY_SCENARIO)]
    fidelity: List[str] = []
    for f in facts.values():
        if f["first_active_k"] != 1:
            fidelity.append(f"{f['label']}: first decision with an own ground move is {f['first_active_k']}, not 1")

    def primary_block(name: str) -> Dict[str, Any]:
        games, seats = {}, {}
        pooled = collections.Counter()
        for f in sorted(primary, key=lambda x: x["label"]):
            p = f["policies"][name]
            games[f["label"]] = {**summarize(p), "cell": f["cell"]}
            seat = seats.setdefault(f["cell"], collections.Counter())
            seat["redirects"] += p["redirects"]
            seat["emitted"] += p["emitted_ground"]
            seat["slot_vs_t9-v1"] += p["slot_vs"]["t9-v1"]
            pooled["slot_vs_t9-v1"] += p["slot_vs"]["t9-v1"]
            pooled["orders_vs_t9-v1"] += p["orders_vs"]["t9-v1"]
            pooled["orders_vs_v3"] += p["orders_vs"]["v3"]
            pooled["orders_vs_baseline-v2"] += p["orders_vs"]["baseline-v2"]
            pooled["redirects"] += p["redirects"]
        seat_rows = {cell: {"redirects": s["redirects"], "emitted": s["emitted"],
                            "share": round(s["redirects"] / s["emitted"], 4) if s["emitted"] else 0.0,
                            "slot_vs_t9-v1": s["slot_vs_t9-v1"]} for cell, s in sorted(seats.items())}
        rows = [r for f in primary for r in private[f["game"]]["redirects"][name]]
        return {"games": games, "seats": seat_rows, "pooled": dict(sorted(pooled.items())),
                "redirect_descriptives": redirect_descriptives(rows)}

    blocks = {name: {"primary": primary_block(name)} for name in sx.POLICIES}
    # fidelity against Sprint 13's published figures
    t9 = blocks["t9-v1"]["primary"]["games"]
    for key, field in (("redirects", "redirects"), ("emitted", "emitted_ground_moves"),
                       ("redirected_units", "redirected_units"), ("first_decision_redirects", "first_decision_redirects")):
        got = {g: t9[g][field] for g in t9}
        if got != sx.S13_EXPECTED["t9-v1"][key]:
            fidelity.append(f"T9-v1 {key} {got} differ from Sprint 13's {sx.S13_EXPECTED['t9-v1'][key]}")
    for name, expected in sx.S13_EXPECTED["pooled"].items():
        pooled = blocks[name]["primary"]["pooled"]
        for key, value in expected.items():
            if pooled.get(key) != value:
                fidelity.append(f"{name} pooled {key} {pooled.get(key)} differs from Sprint 13's {value}")

    # adverse configurations
    adverse_public: Dict[str, Any] = {}
    by_config: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for f in adverse:
        by_config[f["configuration"]].append(f)
    anchors: Dict[str, Any] = {}
    for config, games in sorted(by_config.items()):
        played = {g["played"]: g for g in games}
        if set(played) != {"t9-v1", "baseline-v2"}:
            fidelity.append(f"{config}: expected one T9-v1 and one baseline-v2 trajectory")
            continue
        same_first = played["t9-v1"]["first_state_sha256"] == played["baseline-v2"]["first_state_sha256"]
        anchors[config] = {"first_decision_state_identical": same_first}
        if config == "2120531121 C3":
            names = private[played["t9-v1"]["game"]]["names"]
            values = {c: int(n.split("-")[0]) for c, n in names.items()}
            t9_flags, base_flags = played["t9-v1"]["flags"], played["baseline-v2"]["flags"]
            seat_faction = _faction(played["t9-v1"])
            never = [c for c, hist in t9_flags.items() if values[c] == 80 and all(f != seat_faction for _, f in hist)]
            if len(never) != 1:
                fidelity.append(f"{config}: expected one 80-point objective T9-v1 never owned, found {len(never)}")
                continue
            missed = never[0]
            captured = next((k for k, f in base_flags[missed] if f == seat_faction), None)
            if captured != sx.ADVERSE_FACTS[config]["baseline_capture_decision"]:
                fidelity.append(f"{config}: baseline-v2 first owned the missed objective at decision {captured}")
            anchors[config].update(missed_label=names[missed], baseline_capture_decision=captured,
                                   baseline_capture_step=_capture_step(played["baseline-v2"], captured))
        else:
            shooters = private[played["baseline-v2"]["game"]]["shooters"]
            expected = sx.ADVERSE_FACTS[config]["direct_fire_actions"]
            if len(shooters) != expected:
                fidelity.append(f"{config}: {len(shooters)} direct-fire actions at the firing decisions, not {expected}")
            anchors[config].update(direct_fire_actions=len(shooters),
                                   shooters=len({s["unit"] for s in shooters}))
            own = played["t9-v1"]["policies"]["t9-v1"]["first_decision_redirects"]
            if own != sx.ADVERSE_FACTS[config]["t9v1_first_decision_redirects"]:
                fidelity.append(f"{config}: T9-v1 redirects {own} at the first decision of its own game, Sprint 10 "
                                f"published {sx.ADVERSE_FACTS[config]['t9v1_first_decision_redirects']}")
    v3_cert = None
    for name in sx.POLICIES:
        out = {}
        for config, games in sorted(by_config.items()):
            played = {g["played"]: g for g in games}
            if set(played) != {"t9-v1", "baseline-v2"}:
                continue
            row: Dict[str, Any] = {g["played"]: summarize(g["policies"][name]) for g in games}
            rows_all = {g["played"]: private[g["game"]]["redirects"][name] for g in games}
            by_trajectory = {g["played"]: g["policies"][name]["first_decision_redirects"] for g in games}
            row["first_decision_redirects_by_trajectory"] = by_trajectory
            row["first_decision_redirects"] = max(by_trajectory.values())
            if config == "2120531121 C3" and "missed_label" in anchors[config]:
                missed_label = anchors[config]["missed_label"]
                capture_k = anchors[config]["baseline_capture_decision"]
                base_rows = private[played["baseline-v2"]["game"]]
                capture_step = _capture_step(played["baseline-v2"], capture_k)
                far = [r for g in games for r in private[g["game"]]["redirects"][name]
                       if r["to_label"] == missed_label and r["cur_step"] < capture_step
                       and r["free_flow"] is not None and r["cur_step"] + r["free_flow"] > capture_step]
                missed_coord = next(c for c, n in base_rows["names"].items() if n == missed_label)
                cert = played["t9-v1"]["policies"][name]["certificate"].get(missed_coord, 0)
                unreachable = sum(g["policies"][name]["violations"].get(
                    "place for a unit that cannot arrive before the end", 0) for g in games)
                not_kept = sum(g["policies"][name]["violations"].get("a v3 selection not kept", 0) for g in games)
                row.update(far_reservations_missed=len(far), certificate_unit_decisions=cert,
                           unreachable_places=unreachable, v3_selection_not_kept=not_kept,
                           redirects_into_missed=sum(1 for r in rows_all["t9-v1"] + rows_all["baseline-v2"]
                                                     if r["to_label"] == missed_label))
                if name == "v3":
                    v3_cert = cert
            elif config != "2120531121 C3":
                shooters = private[played["baseline-v2"]["game"]]["shooters"]
                fire_k = {}
                for s in shooters:
                    fire_k[s["unit"]] = min(fire_k.get(s["unit"], s["k"]), s["k"])
                hit = [r for rows in rows_all.values() for r in rows if r["unit"] in fire_k and r["k"] < fire_k[r["unit"]]]
                first_fire = min(sx.ADVERSE_FACTS[config]["fire_decisions"])
                early = [r for r in rows_all["baseline-v2"] if r["k"] < first_fire]
                t9_first = {(r["unit"], r["to"]) for r in private[played["baseline-v2"]["game"]]["redirects"]["t9-v1"]
                            if r["k"] == played["baseline-v2"]["first_active_k"]}
                mine_first = {(r["unit"], r["to"]) for r in rows_all["baseline-v2"]
                              if r["k"] == played["baseline-v2"]["first_active_k"]}
                causal_units = {u for u, _ in t9_first}
                row.update(shooters_redirected=len(hit), early_redirects_baseline=len(early),
                           first_decision_same_as_t9v1=len(t9_first & mine_first),
                           causal_units_objective_changed=len({u for u, _ in mine_first} & causal_units),
                           first_decision_prefix=redirect_descriptives(
                               [r for r in rows_all["baseline-v2"] if r["k"] == played["baseline-v2"]["first_active_k"]]),
                           shooter_forms=_shooter_forms(played["baseline-v2"], name))
            row["redirect_descriptives"] = redirect_descriptives([r for rows in rows_all.values() for r in rows])
            out[config] = row
        blocks[name]["adverse"] = out
    expected_cert = sx.ADVERSE_FACTS["2120531121 C3"]["v3_certificate_unit_decisions"]
    if v3_cert != expected_cert:
        fidelity.append(f"2120531121 C3: v3 admits {v3_cert} certificate unit-decisions, Sprint 11 published {expected_cert}")

    static = static_checks()
    gates, passing = {}, {}
    for name in sx.CANDIDATES:
        c = blocks[name]
        tot = collections.Counter()
        rep = collections.Counter()
        for f in facts.values():
            tot.update(f["policies"][name]["violations"])
            rep.update(f["policies"][name]["repeat"])
        gate_facts = {
            "candidates": {name: {
                "repeat_differences": rep["repeat_differences"], "repeat_comparisons": rep["repeat_comparisons"],
                "order_differences": rep["order_differences"], "order_comparisons": rep["order_comparisons"],
                "violations": dict(tot),
                "primary": {"games": c["primary"]["games"], "seats": c["primary"]["seats"],
                            "pooled": c["primary"]["pooled"]},
                "adverse": {cfg: dict(c["adverse"][cfg], **({"v3_certificate_unit_decisions": v3_cert}
                                                                if cfg == "2120531121 C3" else {}))
                            for cfg in c["adverse"]},
                "latency_ms": timing["candidates"][name]}},
            "references": {ref: {"primary": blocks[ref]["primary"], "adverse": blocks[ref]["adverse"]}
                           for ref in ("t9-v1", "v3")},
            "static": static}
        gates[name] = sx.gate(name, gate_facts)
        if gates[name]["pass"]:
            passing[name] = {"gate": gates[name],
                             "prefix_median": c["primary"]["redirect_descriptives"]["prefix_share"].get("median"),
                             "orders_vs_baseline": c["primary"]["pooled"]["orders_vs_baseline-v2"],
                             "latency_p99": timing["candidates"][name]["p99"]}
    selection = sx.select(passing)
    verdict = sx.disposition(fidelity, gates, selection)
    public = {
        "replay": {"schema": SCHEMA, "note": NOTE, "inputs_sha256": sha256(INPUTS),
                   "primary": {name: blocks[name]["primary"] for name in sx.POLICIES}},
        "adverse": {"schema": SCHEMA, "note": NOTE, "anchors": anchors,
                    "configurations": {name: blocks[name]["adverse"] for name in sx.POLICIES}},
        "gate": {"schema": SCHEMA, "note": NOTE, "thresholds": sx.GATE, "static": static, "fidelity_problems": fidelity,
                 "gates": gates, "selection": selection, "disposition": verdict,
                 "timing_sha256": sha256(TIMING) if TIMING.exists() else None},
    }
    return public, {"facts_digest": None, "private": private}


def _faction(game_facts: Mapping[str, Any]) -> int:
    return game_facts["seat_faction"]


def _capture_step(game_facts: Mapping[str, Any], k: int) -> int:
    return game_facts["steps_at"][str(k)]


def _shooter_forms(game_facts: Mapping[str, Any], name: str) -> Dict[str, int]:
    return dict(sorted(game_facts["policies"][name].get("shooter_forms", {}).items()))


def timing_of(results: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]]) -> Dict[str, Any]:
    out = {"candidates": {}, "t9-v1": None, "note": "milliseconds per decision with an own ground move, measured "
           "once in the worker processes of the replay; not regenerated by --check"}
    for name in sx.CANDIDATES + ("t9-v1",):
        values = [v for f, _ in results for v in f["policies"][name]["latency"]]
        row = {"decisions": len(values), "p50": round(sx.percentile(values, 0.5), 3),
               "p99": round(sx.percentile(values, 0.99), 3), "max": round(max(values) if values else 0.0, 3)}
        if name == "t9-v1":
            out["t9-v1"] = row
        else:
            out["candidates"][name] = row
    return out


def private_values(results) -> set:
    values = set()
    for _, private in results:
        for rows in private["redirects"].values():
            for r in rows:
                values.update({r["from"], r["to"]})
        values.update(int(c) for c in private["names"])
    return values


def run(args: argparse.Namespace) -> int:
    require_inputs()
    jobs = [("primary", g) for g in primary_games()] + [("adverse", e) for e in ADVERSE]
    with multiprocessing.get_context("fork").Pool(min(args.workers, len(jobs))) as pool:
        results = pool.map(process, jobs, chunksize=1)
    if args.check:
        timing = json.loads(TIMING.read_text(encoding="utf-8"))
    else:
        timing = timing_of(results)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        TIMING.write_text(dump(timing), encoding="utf-8", newline="\n")
    public, private = combine(results, timing)
    hidden = private_values(results)
    for name, data in public.items():
        found = sx.public_check(data, hidden)
        if found:
            raise SystemExit(f"refused: {name}.json would publish private values: {found[:5]}")
    texts = {name: dump(data) for name, data in public.items()}
    if args.check:
        bad = [n for n, t in texts.items() if (OUT_DIR / f"{n}.json").read_text(encoding="utf-8") != t]
        if bad:
            print(f"MISMATCH: {bad}")
            return 1
        print("OK: public files regenerate byte for byte")
        return 0
    for name, text in texts.items():
        (OUT_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with gzip.open(PRIVATE / "replay-private.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"private": private["private"]}, handle, sort_keys=True, default=str)
    print(json.dumps(public["gate"]["disposition"], indent=1))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--check", action="store_true")
    go = sub.add_parser("run")
    go.add_argument("--check", action="store_true")
    go.add_argument("--workers", type=int, default=10)
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
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
