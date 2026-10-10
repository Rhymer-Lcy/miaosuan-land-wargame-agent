"""Sprint 36 offline comparison (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 15). Engine-free; no session.

    python scripts/s36_offline.py model    --data DIR --out DIR [--workers N]
    python scripts/s36_offline.py genuine  --data DIR --out DIR [--workers N]
    python scripts/s36_offline.py episodes --data DIR --out DIR [--workers N]
    python scripts/s36_offline.py select   --out DIR

Populations (each labelled by its evidence level in every output):

* ``model`` (engine-free, MODEL WORLD, no combat): every eligible scenario (Sprint 34's naming rule), both seats, each
  agent of ``AGENTS`` against the inert control (``M-inert``) and against ``baseline-v2`` (``M-v2``); the ablations
  against ``baseline-v2`` in the five Stage A scenarios (``M-v2-ablation``). ``OUT/model.jsonl``.
* ``genuine`` (decision-level on genuine engine observations): Sprint 34's offline corpus (the pinned replay corpus and
  sixteen full-step timelines) plus the 24 Sprint 34 and 19 Sprint 35 live games, every seat that is not the inert
  control, re-decided by each agent (and the two equivalence pairs) with its own memory chain: legality by the agent's validator and by
  an independent check, fallbacks, contract errors, latency, memory size, actions by type, differences from the frozen
  controls, and the two equivalence pairs (``ta-as-ca`` against Sprint 35's ``CA``, ``tc-no-guard`` against
  ``S34-MO``). The 19 Sprint 35 games informed this sprint's design: they are development data, not confirmation.
  ``OUT/genuine-private.json``.
* ``episodes`` (historical descriptive, decision-level): in the 43 recorded live games, every loss of a held objective
  and every own ground unit destroyed standing in a held objective's zone; each agent re-decides the policy-under-test
  seat's recorded observations (open loop: its decisions never change the recorded trajectory) and is read at those
  episodes: threat recognised 150 steps before the loss; zone abandoned (no unit kept or sent there in the 300 steps
  before the loss); a valuable unit (not cheap) later destroyed in the zone ordered out of it in the 300 steps before;
  Sprint 34's 18 last-defender departures kept. Also the controls' fidelity: each frozen control re-decides its own
  recorded games exactly. ``OUT/episodes-private.json``.

``select`` applies the registered gates and rule (``evaluation.s36_offline``) and writes the public summaries to
``evaluation/s36-tactical-recovery/{model,genuine,episodes,selection}.json`` (aggregates only).
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
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

from miaosuan_agent.evaluation import s36_offline as rules  # noqa: E402

PUBLIC = REPO_ROOT / "evaluation" / "s36-tactical-recovery"
AGENTS = rules.AGENTS
ABLATIONS = rules.ABLATIONS
EQUIVALENCE = rules.EQUIVALENCE
STAGE_A = ("2130511121", "2120531121", "1930331196", "1910631192", "2010431153")
LIVE_CARDS = ("s34-integrated-live-1", "s35-coalition-live-1")


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s36o_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S34 = load("s34_offline")
S35 = load("s35_offline")
REC = load("s36_reconstruct")


def make_agent(name: str, seat: int, faction: int, cost: Any):
    return REC.agent_for(name, seat, faction, cost)


def _key(action: Mapping[str, Any]) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True)


# ------------------------------------------------------------------------------------------------ model
def _model_job(job: Tuple[str, str, str, str, str, str]) -> Dict[str, Any]:
    from miaosuan_agent.evaluation.s36_modelplay import play_model
    data, population, sid, mid, red, blue = job
    tick = time.perf_counter()
    try:
        result = play_model(Path(data), sid, mid, red, blue, replay_every=97)
    except Exception as exc:  # noqa: BLE001 - a crash is a finding, recorded
        return {"population": population, "scenario_id": sid, "map_id": mid, "red": red, "blue": blue,
                "crash": f"{type(exc).__name__}: {exc}"[:500]}
    result["population"] = population
    result["wall_seconds"] = round(time.perf_counter() - tick, 1)
    return result


def model_jobs(data: Path) -> List[Tuple[str, str, str, str, str, str]]:
    scenarios = S34.eligible_scenarios(data)
    jobs = []
    for agent in AGENTS:
        for sid, mid in scenarios:
            jobs.append((str(data), "M-inert", sid, mid, agent, "inert"))
            jobs.append((str(data), "M-inert", sid, mid, "inert", agent))
            jobs.append((str(data), "M-v2", sid, mid, agent, "baseline-v2"))
            jobs.append((str(data), "M-v2", sid, mid, "baseline-v2", agent))
    stage_a = [(sid, mid) for sid, mid in scenarios if sid in STAGE_A]
    for agent in ABLATIONS:
        for sid, mid in stage_a:
            jobs.append((str(data), "M-v2-ablation", sid, mid, agent, "baseline-v2"))
            jobs.append((str(data), "M-v2-ablation", sid, mid, "baseline-v2", agent))
    return jobs


def cmd_model(args: argparse.Namespace) -> int:
    jobs = model_jobs(args.data)
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "model.jsonl"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    print(f"{len(jobs)} model games", file=sys.stderr, flush=True)
    with mp.Pool(args.workers) as pool, out.open("x", encoding="utf-8") as handle:
        for n, result in enumerate(pool.imap(_model_job, jobs), start=1):
            handle.write(json.dumps(result, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            if n % 25 == 0:
                print(f"{n}/{len(jobs)}", file=sys.stderr, flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ genuine
def live_jobs(data: Path) -> List[Tuple[str, str, str, str, str, str]]:
    jobs = []
    for card in LIVE_CARDS:
        base = REPO_ROOT / "local" / "evaluation" / card
        for record_path in sorted((base / "games").glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            game = record_path.stem
            kind = "LA" if (".H1." in game or ".H2." in game) else "LB"
            jobs.append((str(data), f"{kind}:{card}", str(base / "capture" / f"{game}.timeline.pkl"), str(record_path),
                         str(record["scenario_id"]), str(record["map_id"])))
    return jobs


def _genuine_job(job: Tuple[str, str, str, str, str, str]) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.boundary import MoveCosts
    from miaosuan_agent.decision.trace import canonical_json
    from miaosuan_agent.evaluation.s34_capture import plain
    from miaosuan_agent.experiments.routing_bounded import BoundedRouter
    data, kind, path, record_path, scenario_id, map_id = job
    record = json.loads(Path(record_path).read_text(encoding="utf-8")) if record_path else {}
    inputs = sdk_data.load_inputs(Path(data), scenario_id, map_id)
    router = BoundedRouter(MoveCosts.from_raw(inputs.cost))
    names = list(AGENTS) + sorted({n for pair in EQUIVALENCE for n in pair} - set(AGENTS))
    agents: Dict[Tuple[str, int], Any] = {}
    rows = collections.defaultdict(lambda: {"decisions": 0, "play_decisions": 0, "rejections": 0,
                                            "independent_illegal": 0, "illegal_examples": [], "fallbacks": 0,
                                            "contract_errors": 0, "differing_from_s34": 0, "differing_from_cm": 0,
                                            "actions_by_type": collections.Counter(), "latency_ms": [],
                                            "memory_bytes_max": 0, "stats": collections.Counter()})
    equivalence = {f"{a} vs {b}": 0 for a, b in EQUIVALENCE}
    kind_short = kind.split(":")[0]
    for seat, faction, raw in S34._sequence("HH" if kind_short in ("LA", "LB") else kind, Path(path), record):
        stage = (raw.get("time") or {}).get("stage")
        produced: Dict[str, List[str]] = {}
        for name in names:
            key = (name, seat)
            if key not in agents:
                agents[key] = make_agent(name, seat, faction, inputs.cost)
            agent = agents[key]
            tick = time.perf_counter()
            actions = agent.step(raw)
            elapsed = (time.perf_counter() - tick) * 1000.0
            trace = agent.last_trace
            r = rows[name]
            r["decisions"] += 1
            r["latency_ms"].append(elapsed)
            r["contract_errors"] += trace.error is not None
            r["fallbacks"] += bool(getattr(trace, "fallback", None))
            r["rejections"] += len(trace.rejected)
            size = len(canonical_json(plain(agent.memory.to_dict())).encode("utf-8"))
            r["memory_bytes_max"] = max(r["memory_bytes_max"], size)
            for k, v in getattr(trace, "stats", ()) or ():
                if k.startswith(("stance_", "guard_")) or k in ("withdrawing", "kept", "guided_shots",
                                                                 "artillery_orders"):
                    r["stats"][k] += v
            for a in actions:
                r["actions_by_type"][int(a["type"])] += 1
                problem = S35.independent_problem(a, raw, seat, faction, router)
                if problem:
                    r["independent_illegal"] += 1
                    if len(r["illegal_examples"]) < 5:
                        r["illegal_examples"].append(problem)
            produced[name] = sorted(_key(a) for a in actions)
            if stage == 2:
                r["play_decisions"] += 1
        if stage == 2:
            for name in names:
                rows[name]["differing_from_s34"] += produced[name] != produced["S34-MO"]
                rows[name]["differing_from_cm"] += produced[name] != produced["CM"]
            for a, b in EQUIVALENCE:
                equivalence[f"{a} vs {b}"] += produced[a] != produced[b]
    out: Dict[str, Any] = {"kind": kind, "game": Path(path).name, "agents": {}, "equivalence_differences": equivalence}
    for name, r in rows.items():
        lat = sorted(r.pop("latency_ms"))
        r["latency_ms_p50"] = lat[len(lat) // 2] if lat else 0.0
        r["latency_ms_p99"] = lat[int(len(lat) * 0.99)] if lat else 0.0
        r["latency_ms_max"] = lat[-1] if lat else 0.0
        r["actions_by_type"] = {f"type_{k}": v for k, v in sorted(r["actions_by_type"].items())}
        r["stats"] = dict(sorted(r["stats"].items()))
        out["agents"][name] = r
    return out


def cmd_genuine(args: argparse.Namespace) -> int:
    jobs = S34.genuine_jobs(args.data) + live_jobs(args.data)
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "genuine-private.json"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    inputs = {"files": [{"path": Path(j[2]).relative_to(REPO_ROOT).as_posix(), "sha256": S34.sha256(Path(j[2]))}
                        for j in jobs]}
    with mp.Pool(args.workers) as pool:
        results = pool.map(_genuine_job, jobs, chunksize=1)
    out.write_text(json.dumps({"inputs": inputs, "games": results}, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ episodes
def _episodes_job(job: Tuple[str, str, int]) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.integrated import facts as F
    data, card, position = job
    work = REPO_ROOT / "local" / "evaluation" / card
    record_path = next((work / "games").glob(f"*.p{position:02d}.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    game_id = record["game_id"]
    compact = json.loads((work / "capture" / f"{game_id}.timeline.json").read_text(encoding="utf-8"))
    windows = pickle.load(open(work / "capture" / f"{game_id}.timeline.pkl", "rb"))
    tested = [s for s in record["seats"] if s["policy"] not in (rules.V2, rules.INERT)]
    seat, colour, policy_id = tested[0]["seat"], tested[0]["faction"], tested[0]["policy"]
    recorded_policy = REC.policy_name(policy_id)
    inputs = sdk_data.load_inputs(Path(data), record["scenario_id"], record["map_id"])
    steps = [s for s in compact["steps"] if s["k"] >= 0]
    decisions: Dict[str, Dict[int, Dict[str, Any]]] = {}
    fidelity = {"decisions": 0, "differing": 0}
    cheap_limit = None
    for name in AGENTS:
        agent = make_agent(name, seat, colour, inputs.cost)
        per: Dict[int, Dict[str, Any]] = {}
        for sample in sorted(windows["samples"], key=lambda s: s["k"]):
            snap = sample["seats"].get(str(seat))
            if snap is None:
                continue
            raw = pickle.loads(snap["observation"])
            actions = [dict(a) for a in agent.step(raw)]
            if cheap_limit is None and (raw.get("time") or {}).get("stage") == 2:
                values = [u.get("value") or 0 for u in raw.get("operators") or ()
                          if u.get("color") == colour and u.get("type") in (1, 2) and u.get("sub_type") != F.ARTILLERY]
                cheap_limit = 0.5 * max(values + [0])
            per[sample["cur_step"]] = {"actions": actions, "stances": REC.stances_of(agent.last_trace)}
            if name == recorded_policy:
                fidelity["decisions"] += 1
                fidelity["differing"] += sorted(_key(a) for a in actions) != sorted(_key(a) for a in snap["submitted"])
        decisions[name] = per
    episodes = rules.episodes_from_timeline(steps, colour)
    rows = {name: rules.read_episodes(episodes, decisions[name], steps, colour, cheap_limit or 0.0)
            for name in AGENTS}
    return {"card": card, "position": position, "scenario_id": record["scenario_id"],
            "condition": record["condition"], "recorded_policy": recorded_policy, "fidelity": fidelity,
            "episodes": rules.episode_counts(episodes), "rows": rows}


def cmd_episodes(args: argparse.Namespace) -> int:
    jobs = []
    for card in LIVE_CARDS:
        base = REPO_ROOT / "local" / "evaluation" / card
        for record_path in sorted((base / "games").glob("*.json")):
            if ".H1." not in record_path.name and ".H2." not in record_path.name:
                continue
            position = int(record_path.stem.rsplit(".p", 1)[1])
            jobs.append((str(args.data), card, position))
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "episodes-private.json"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    with mp.Pool(args.workers) as pool:
        results = pool.map(_episodes_job, jobs, chunksize=1)
    out.write_text(json.dumps({"games": results}, sort_keys=True) + "\n", encoding="utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ select
def cmd_select(args: argparse.Namespace) -> int:
    model = [json.loads(line) for line in (args.out / "model.jsonl").read_text(encoding="utf-8").splitlines() if line]
    genuine = json.loads((args.out / "genuine-private.json").read_text(encoding="utf-8"))
    episodes = json.loads((args.out / "episodes-private.json").read_text(encoding="utf-8"))
    model_summary = rules.summarise_model(model)
    genuine_summary = rules.summarise_genuine(genuine["games"])
    episode_summary = rules.summarise_episodes(episodes["games"])
    selection = rules.select(model_summary, genuine_summary, episode_summary)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    for name, data in (("model", model_summary), ("genuine", genuine_summary), ("episodes", episode_summary),
                       ("selection", selection)):
        (PUBLIC / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                             newline="\n")
    print(json.dumps({k: selection[k] for k in ("selected", "rule", "gates_passed")}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("model", "genuine", "episodes", "select"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, required=True)
        if name != "select":
            p.add_argument("--data", type=Path, required=True)
            p.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    return {"model": cmd_model, "genuine": cmd_genuine, "episodes": cmd_episodes, "select": cmd_select}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
