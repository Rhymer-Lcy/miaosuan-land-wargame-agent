"""Sprint 34 offline architecture comparison (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 8). Engine-free.

    python scripts/s34_offline.py model   --data DIR --out DIR [--workers N]
    python scripts/s34_offline.py genuine --data DIR --out DIR [--workers N]
    python scripts/s34_offline.py select  --out DIR

``model`` plays, in the Sprint 34 model world, every eligible SDK scenario with each candidate (``CT``, ``MO``) and
``baseline-v2`` in both seats against the inert control (``M-inert``) and against ``baseline-v2`` (``M-v2``), plus the
ablations in the eight frozen scenarios; one JSON line per game in ``OUT/model.jsonl`` (private: hex keys).

``genuine`` re-decides every recorded decision of the genuine engine observations (the replay corpus pinned by
``evaluation/routing-remediation-1/corpus.json``, both seats; and the full-step timelines listed in ``TIMELINES``,
every seat that is not the inert control) with each candidate and with a fresh ``baseline-v2``: legality by the
candidate's validator and by an independent check (the frozen project gate for move, shoot and occupation; the listing
and option for embark, disembark and indirect fire), differences from ``baseline-v2``'s decision by module, the first
divergence, latency, fallbacks and contract errors. ``OUT/genuine.json`` (aggregates) and ``OUT/genuine-private.json``.

``select`` applies the registered rule (``evaluation.s34_offline.select``) and writes the public summaries to
``evaluation/s34-integrated-agent/{model,genuine,selection}.json``.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import multiprocessing as mp
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

PUBLIC = REPO_ROOT / "evaluation" / "s34-integrated-agent"
FROZEN = ("2120531121", "2010211129", "2010431153", "1910631192", "2010131194", "1930331196", "201033019601",
          "2130511121")
ABLATIONS = ("mo-no-transport", "mo-no-artillery", "mo-no-threat-routing", "mo-no-economy", "mo-no-recovery",
             "ct-greedy", "mo-hungarian-no-transport")
TIMELINES = (
    "s12-v3-primary-1/2130511121.H1.s12-v3-primary-1.p01", "s12-v3-primary-1/2130511121.H2.s12-v3-primary-1.p02",
    "s12-v3-primary-1/2130511121.H1.s12-v3-primary-1.p03", "s12-v3-primary-1/2130511121.H2.s12-v3-primary-1.p04",
    "s16-v3-mechanism-capture-1/1930331196.C3.s16-v3-mechanism-capture-1.p01",
    "s16-v3-mechanism-capture-1/1930331196.C2.s16-v3-mechanism-capture-1.p02",
    "s16-v3-mechanism-capture-1/2120531121.C3.s16-v3-mechanism-capture-1.p03",
    "s17-post-stage-v6-probe-1/1930331196.C2.s17-post-stage-v6-probe-1.p01",
    "s17-post-stage-v6-probe-1/2120531121.C3.s17-post-stage-v6-probe-1.p02",
    "s22-t2-transport-probe-1/1930331196.C3.s22-t2-transport-probe-1.p01",
    "s27-t6s-probe-1/2130511121.H2.s27-t6s-probe-1.p01",
    "s31-t13-k2-pilot-1/2120531121.C3.s31-t13-k2-pilot-1.p01",
    "s31-t13-k2-pilot-1/1930331196.C2.s31-t13-k2-pilot-1.p02",
    "s31-t13-k2-pilot-1/2130511121.H1.s31-t13-k2-pilot-1.p03",
    "s33-t7-b1-live-1/2120531121.C3.s33-t7-b1-live-1.p01",
    "s33-t7-b1-live-1/1930331196.C3.s33-t7-b1-live-1.p02",
)
INERT_POLICY = "inert-v0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ model
def eligible_scenarios(data: Path) -> List[Tuple[str, str]]:
    from miaosuan_agent.evaluation import selection
    maps = {p.name[len("map_"):] for p in (data / "maps").iterdir() if p.is_dir()}
    out = []
    for path in sorted((data / "scenarios").glob("*.json")):
        sid = path.stem
        mid = selection.map_by_name(sid, maps)
        if mid is not None:
            out.append((sid, mid))
    return out


def _model_job(job: Tuple[str, str, str, str, str, str]) -> Dict[str, Any]:
    from miaosuan_agent.evaluation.s34_modelplay import play_model
    data, population, sid, mid, red, blue = job
    tick = time.perf_counter()
    try:
        result = play_model(Path(data), sid, mid, red, blue, replay_every=97)
    except Exception as exc:  # noqa: BLE001 - a crash is a finding, recorded
        return {"population": population, "scenario_id": sid, "red": red, "blue": blue,
                "crash": f"{type(exc).__name__}: {exc}"[:500]}
    result["population"] = population
    result["wall_seconds"] = round(time.perf_counter() - tick, 1)
    return result


def cmd_model(args: argparse.Namespace) -> int:
    scenarios = eligible_scenarios(args.data)
    jobs = []
    for agent in ("CT", "MO", "baseline-v2"):
        for sid, mid in scenarios:
            jobs.append((str(args.data), "M-inert", sid, mid, agent, "inert"))
            jobs.append((str(args.data), "M-inert", sid, mid, "inert", agent))
            if agent != "baseline-v2":
                jobs.append((str(args.data), "M-v2", sid, mid, agent, "baseline-v2"))
                jobs.append((str(args.data), "M-v2", sid, mid, "baseline-v2", agent))
            else:
                jobs.append((str(args.data), "M-v2", sid, mid, "baseline-v2", "baseline-v2"))
    for agent in ABLATIONS:
        for sid, mid in scenarios:
            if sid not in FROZEN:
                continue
            for population, opponent in (("M-inert", "inert"), ("M-v2", "baseline-v2")):
                jobs.append((str(args.data), population, sid, mid, agent, opponent))
                jobs.append((str(args.data), population, sid, mid, opponent, agent))
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "model.jsonl"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    print(f"{len(jobs)} model games over {len(scenarios)} scenarios", file=sys.stderr, flush=True)
    with mp.Pool(args.workers) as pool, out.open("x", encoding="utf-8") as handle:
        for n, result in enumerate(pool.imap(_model_job, jobs), start=1):
            handle.write(json.dumps(result, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            if n % 25 == 0:
                print(f"{n}/{len(jobs)}", file=sys.stderr, flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ genuine
def _independent_problem(action: Mapping[str, Any], raw: Mapping[str, Any], seat: int, faction: int, router) -> str:
    """Legality of one candidate action by a check that shares no code with the candidate's validator."""
    from miaosuan_agent.boundary import Observation, Origin
    from miaosuan_agent.decision import gate
    from miaosuan_agent.decision.context import build_context
    kind = action.get("type")
    observation = Observation.from_raw(raw, Origin.ENGINE)
    if kind in (1, 2, 5, 333):
        context = build_context(observation, seat, faction)
        result = gate.check([action], context, router)
        return "" if result.accepted else result.rejected[0].reason
    listed = observation.valid_actions().get(action.get("obj_id"), {})
    if kind not in listed:
        return "type not listed"
    if kind in (3, 4):
        return "" if {"target_obj_id": action.get("target_obj_id")} in [dict(o) for o in listed[kind] or ()] \
            else "option not listed"
    if kind == 8:
        weapons = [o.get("weapon_id") for o in listed[kind] or ()]
        return "" if action.get("weapon_id") in weapons and isinstance(action.get("jm_pos"), int) else "bad option"
    return "type outside the candidate catalog"


def _sequence(kind: str, path: Path, record: Mapping[str, Any]):
    """Yield (seat, faction, raw observation) in decision order for every analysed seat of one genuine game."""
    from miaosuan_agent import typed_json
    if kind == "H0":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            next(handle)
            for line in handle:
                row = json.loads(line)
                yield row["seat"], row["faction"], typed_json.decode(row["observation"])
        return
    windows = pickle.load(path.open("rb"))
    seats = {s["seat"]: s for s in record["seats"]}
    for sample in sorted(windows["samples"], key=lambda s: s["k"]):
        for seat_key, snap in sorted(sample["seats"].items(), key=lambda kv: int(kv[0])):
            seat = int(seat_key)
            if seats[seat]["policy"] == INERT_POLICY:
                continue
            yield seat, seats[seat]["faction"], pickle.loads(snap["observation"])


def _genuine_job(job: Tuple[str, str, str, str, str, str]) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.boundary import MoveCosts, Observation, Origin
    from miaosuan_agent.decision import Memory
    from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
    from miaosuan_agent.experiments.routing_bounded import BoundedRouter
    from miaosuan_agent.integrated.agent import CommanderAgent
    from miaosuan_agent.integrated.config import VARIANTS
    data, kind, path, record_path, scenario_id, map_id = job
    record = json.loads(Path(record_path).read_text(encoding="utf-8")) if record_path else {}
    inputs = sdk_data.load_inputs(Path(data), scenario_id, map_id)
    costs = MoveCosts.from_raw(inputs.cost)
    router = BoundedRouter(costs)
    agents: Dict[Tuple[str, int], Any] = {}
    v2: Dict[int, Any] = {}
    out: Dict[str, Any] = {"kind": kind, "game": Path(path).name, "candidates": {}}
    rows = collections.defaultdict(lambda: {"decisions": 0, "play_decisions": 0, "rejections": 0,
                                            "independent_illegal": 0, "illegal_examples": [], "fallbacks": 0,
                                            "contract_errors": 0, "decisions_differing": 0,
                                            "differing_by_module": collections.Counter(),
                                            "actions_by_type": collections.Counter(), "first_divergence": {},
                                            "latency_ms": []})
    for seat, faction, raw in _sequence(kind, Path(path), record):
        observation = Observation.from_raw(raw, Origin.ENGINE)
        stage = (raw.get("time") or {}).get("stage")
        if seat not in v2:
            v2[seat] = [ShootReservationPolicy(costs), Memory()]
        base = v2[seat][0].decide(observation, seat, faction, v2[seat][1])
        v2[seat][1] = base.memory
        base_actions = sorted(json.dumps(dict(a), sort_keys=True) for a in base.actions)
        for name in ("CT", "MO"):
            key = (name, seat)
            if key not in agents:
                agent = CommanderAgent(VARIANTS[name])
                agent.setup({"seat": seat, "faction": faction, "cost_data": inputs.cost})
                agents[key] = agent
            agent = agents[key]
            tick = time.perf_counter()
            actions = agent.step(raw)
            elapsed = (time.perf_counter() - tick) * 1000.0
            trace = agent.last_trace
            r = rows[name]
            r["decisions"] += 1
            r["latency_ms"].append(elapsed)
            if trace.error is not None:
                r["contract_errors"] += 1
            if getattr(trace, "fallback", None):
                r["fallbacks"] += 1
            r["rejections"] += len(trace.rejected)
            for a in actions:
                r["actions_by_type"][int(a["type"])] += 1
                problem = _independent_problem(a, raw, seat, faction, router)
                if problem:
                    r["independent_illegal"] += 1
                    if len(r["illegal_examples"]) < 5:
                        r["illegal_examples"].append(problem)
            if stage == 2:
                r["play_decisions"] += 1
                mine = sorted(json.dumps(dict(a), sort_keys=True) for a in actions)
                if mine != base_actions:
                    r["decisions_differing"] += 1
                    r["first_divergence"].setdefault(str(seat), observation.time().cur_step)
                    plans = {p[0]: p for p in getattr(trace, "plans", ())}
                    base_units = {a.get("obj_id"): json.dumps(dict(a), sort_keys=True) for a in base.actions}
                    mine_units = {a.get("obj_id"): json.dumps(dict(a), sort_keys=True) for a in actions}
                    for unit in set(base_units) | set(mine_units):
                        if base_units.get(unit) != mine_units.get(unit):
                            module = plans[unit][1] if unit in plans else "baseline-only"
                            r["differing_by_module"][module] += 1
    for name, r in rows.items():
        lat = sorted(r.pop("latency_ms"))
        r["latency_ms_p50"] = lat[len(lat) // 2] if lat else 0.0
        r["latency_ms_p99"] = lat[int(len(lat) * 0.99)] if lat else 0.0
        r["latency_ms_max"] = lat[-1] if lat else 0.0
        r["differing_by_module"] = dict(r["differing_by_module"])
        r["actions_by_type"] = {f"type_{k}": v for k, v in sorted(r["actions_by_type"].items())}
        out["candidates"][name] = r
    return out


def genuine_jobs(data: Path) -> List[Tuple[str, str, str, str, str, str]]:
    corpus = json.loads((REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json").read_text(encoding="utf-8"))
    jobs = []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
        jobs.append((str(data), "H0", str(path), "", str(header["scenario_id"]), str(header["map_id"])))
    for item in TIMELINES:
        folder, game = item.split("/")
        base = REPO_ROOT / "local" / "evaluation" / folder
        record = json.loads((base / "games" / f"{game}.json").read_text(encoding="utf-8"))
        kind = "HH" if ".H1." in game or ".H2." in game else "HI"
        jobs.append((str(data), kind, str(base / "capture" / f"{game}.timeline.pkl"), str(base / "games" / f"{game}.json"),
                     str(record["scenario_id"]), str(record["map_id"])))
    return jobs


def cmd_genuine(args: argparse.Namespace) -> int:
    jobs = genuine_jobs(args.data)
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "genuine-private.json"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    inputs = {"files": [{"path": Path(j[2]).relative_to(REPO_ROOT).as_posix(), "sha256": sha256(Path(j[2]))}
                        for j in jobs]}
    with mp.Pool(args.workers) as pool:
        results = pool.map(_genuine_job, jobs)
    out.write_text(json.dumps({"inputs": inputs, "games": results}, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ select
def genuine_summary(games: List[Mapping[str, Any]], candidate: str) -> Dict[str, Any]:
    total = collections.Counter()
    modules = collections.Counter()
    actions = collections.Counter()
    p99 = []
    worst = 0.0
    by_kind = collections.defaultdict(collections.Counter)
    for g in games:
        r = g["candidates"][candidate]
        for k in ("decisions", "play_decisions", "rejections", "independent_illegal", "fallbacks", "contract_errors",
                  "decisions_differing"):
            total[k] += r[k]
            by_kind[g["kind"]][k] += r[k]
        modules.update(r["differing_by_module"])
        actions.update(r["actions_by_type"])
        p99.append(r["latency_ms_p99"])
        worst = max(worst, r["latency_ms_max"])
    out = dict(total)
    out.update(latency_ms_p99=round(max(p99) if p99 else 0.0, 3), latency_ms_max=round(worst, 3),
               differing_by_module=dict(sorted(modules.items())), actions_by_type=dict(sorted(actions.items())),
               by_population={k: dict(v) for k, v in sorted(by_kind.items())}, games=len(games))
    return out


def cmd_select(args: argparse.Namespace) -> int:
    from miaosuan_agent.evaluation import s34_offline as so
    games = [json.loads(line) for line in (args.out / "model.jsonl").read_text(encoding="utf-8").splitlines() if line]
    crashes = [g for g in games if "crash" in g]
    genuine = json.loads((args.out / "genuine-private.json").read_text(encoding="utf-8"))
    summaries: Dict[str, Any] = {}
    model_public: Dict[str, Any] = {"crashes": len(crashes), "populations": {}}
    agents = ("CT", "MO", "baseline-v2") + ABLATIONS
    for population in ("M-inert", "M-v2"):
        pop_games = [g for g in games if g.get("population") == population and "crash" not in g]
        model_public["populations"][population] = {}
        for agent in agents:
            if agent == "baseline-v2" and population == "M-v2":
                mirror = [g for g in pop_games if g["red"] == g["blue"] == "baseline-v2"]
                model_public["populations"][population][agent] = so.summarise_model(mirror, agent)
                continue
            mine = [g for g in pop_games if agent in (g["red"], g["blue"])
                    and not (g["red"] == g["blue"] == "baseline-v2")]
            model_public["populations"][population][agent] = so.summarise_model(mine, agent)
    for candidate in so.CANDIDATES:
        summaries[candidate] = {"model": {p: model_public["populations"][p][candidate] for p in ("M-inert", "M-v2")},
                                "genuine": genuine_summary(genuine["games"], candidate)}
    decision = so.select(summaries)
    if crashes:
        decision = {"selected": None, "rule": "a model game crashed", "crashes": len(crashes)}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    dump = lambda data: json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"  # noqa: E731
    (PUBLIC / "model.json").write_text(dump(model_public), encoding="utf-8", newline="\n")
    (PUBLIC / "genuine.json").write_text(dump({c: summaries[c]["genuine"] for c in so.CANDIDATES}
                                              | {"inputs": genuine["inputs"]}), encoding="utf-8", newline="\n")
    (PUBLIC / "selection.json").write_text(dump(decision), encoding="utf-8", newline="\n")
    print(json.dumps({"selected": decision["selected"], "rule": decision["rule"]}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("model", cmd_model), ("genuine", cmd_genuine), ("select", cmd_select)):
        p = sub.add_parser(name)
        if name != "select":
            p.add_argument("--data", type=Path, required=True)
            p.add_argument("--workers", type=int, default=8)
        p.add_argument("--out", type=Path, required=True)
        p.set_defaults(func=func)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
