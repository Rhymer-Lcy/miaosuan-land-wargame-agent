"""Sprint 35 offline architecture comparison (``docs/SPRINT35_COALITION_AGENT.md`` section 8). Engine-free.

    python scripts/s35_offline.py model      --data DIR --out DIR [--workers N]
    python scripts/s35_offline.py genuine    --data DIR --out DIR [--workers N]
    python scripts/s35_offline.py precursors --data DIR --out DIR [--workers N]
    python scripts/s35_offline.py select     --out DIR

``model`` plays every eligible SDK scenario (Sprint 34's registered naming rule) with ``S34-MO``, ``CA`` and ``CM`` in
both seats against the inert control (``M-inert``) and against ``baseline-v2`` (``M-v2``), and the ablations against
``baseline-v2`` in the five Stage A scenarios; one JSON line per game in ``OUT/model.jsonl`` (private).

``genuine`` re-decides every recorded decision of the genuine engine observations (Sprint 34's population: the pinned
replay corpus and sixteen full-step timelines; plus the 24 Sprint 34 live games, every seat that is not the inert
control) with each agent (own memory chain): legality by its validator and by an independent check (the frozen project
gate for move, shoot and occupation; the listing and the exact option for embark, disembark, indirect and guided
fire), fallbacks, contract errors, latency, and decisions differing from ``S34-MO``'s on the same observation.

``precursors`` re-decides, with each agent, the Sprint 34 candidate seat of the sixteen Stage A live games and reads the
57 held-objective loss episodes: was the threat recognised 150 steps before the loss (stance secure, defend or delay),
were last defenders that Sprint 34 ordered away kept (no move taking them out of the zone at that decision), and did
the agent respond in the 300 steps before the loss (a move into the zone from outside, or a withdrawal). ``S34-MO``'s
re-decisions on its own trajectory must reproduce its recorded actions at every decision (fidelity).

``select`` applies the registered rule (``evaluation.s35_offline.select``) and writes the public summaries to
``evaluation/s35-coalition-agent/{model,genuine,precursors,selection}.json``.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import multiprocessing as mp
import pickle
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

PUBLIC = REPO_ROOT / "evaluation" / "s35-coalition-agent"
AGENTS = ("S34-MO", "CA", "CM")
STAGE_A = ("2130511121", "2120531121", "1930331196", "1910631192", "2010431153")
ABLATIONS = ("ca-no-retention", "ca-no-withdrawal", "ca-no-reinforcement", "ca-no-coalition-capture", "ca-no-reserve",
             "cm-no-fire-support", "cm-no-arrival-fire", "cm-no-guided-fire", "cm-no-safe-transport", "cm-no-transport")
LIVE_CARD = "s34-integrated-live-1"
STANCE_ROW = re.compile(r"^objective (\d+): (\w+) .* withdraw (\[.*\]): ")
THREATENED = ("secure", "defend", "delay")


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s35o_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S34 = load("s34_offline")


# ------------------------------------------------------------------------------------------------ model
def _model_job(job: Tuple[str, str, str, str, str, str]) -> Dict[str, Any]:
    from miaosuan_agent.evaluation.s35_modelplay import play_model
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
def independent_problem(action: Mapping[str, Any], raw: Mapping[str, Any], seat: int, faction: int, router) -> str:
    """Sprint 34's independent legality check, plus guided fire: action 9 listed for the unit and its (target,
    weapon, guided carrier) exactly one listed option."""
    if action.get("type") == 9:
        from miaosuan_agent.boundary import Observation, Origin
        listed = Observation.from_raw(raw, Origin.ENGINE).valid_actions().get(action.get("obj_id"), {})
        if 9 not in listed:
            return "type not listed"
        wanted = [action.get("target_obj_id"), action.get("weapon_id"), action.get("guided_obj_id")]
        offered = [[o.get("target_obj_id"), o.get("weapon_id"), o.get("guided_obj_id")] for o in listed[9] or ()]
        return "" if wanted in offered else "option not listed"
    return S34._independent_problem(action, raw, seat, faction, router)


def make_agent(name: str, seat: int, faction: int, cost: Any):
    from miaosuan_agent.coalition.agent import CoalitionAgent
    from miaosuan_agent.coalition.config import VARIANTS
    from miaosuan_agent.integrated.agent import CommanderAgent
    from miaosuan_agent.integrated.config import LIVE
    agent = CommanderAgent(LIVE) if name == "S34-MO" else CoalitionAgent(VARIANTS[name])
    agent.setup({"seat": seat, "faction": faction, "cost_data": cost})
    return agent


def _key(action: Mapping[str, Any]) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True)


def _genuine_job(job: Tuple[str, str, str, str, str, str]) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.boundary import MoveCosts, Observation, Origin
    from miaosuan_agent.experiments.routing_bounded import BoundedRouter
    data, kind, path, record_path, scenario_id, map_id = job
    record = json.loads(Path(record_path).read_text(encoding="utf-8")) if record_path else {}
    inputs = sdk_data.load_inputs(Path(data), scenario_id, map_id)
    router = BoundedRouter(MoveCosts.from_raw(inputs.cost))
    agents: Dict[Tuple[str, int], Any] = {}
    rows = collections.defaultdict(lambda: {"decisions": 0, "play_decisions": 0, "rejections": 0,
                                            "independent_illegal": 0, "illegal_examples": [], "fallbacks": 0,
                                            "contract_errors": 0, "decisions_differing_from_control": 0,
                                            "actions_by_type": collections.Counter(), "latency_ms": []})
    for seat, faction, raw in S34._sequence(kind, Path(path), record):
        stage = (raw.get("time") or {}).get("stage")
        produced: Dict[str, List[str]] = {}
        for name in AGENTS:
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
            for a in actions:
                r["actions_by_type"][int(a["type"])] += 1
                problem = independent_problem(a, raw, seat, faction, router)
                if problem:
                    r["independent_illegal"] += 1
                    if len(r["illegal_examples"]) < 5:
                        r["illegal_examples"].append(problem)
            produced[name] = sorted(_key(a) for a in actions)
            if stage == 2:
                r["play_decisions"] += 1
        if stage == 2:
            for name in AGENTS:
                if produced[name] != produced["S34-MO"]:
                    rows[name]["decisions_differing_from_control"] += 1
    out: Dict[str, Any] = {"kind": kind, "game": Path(path).name, "agents": {}}
    for name, r in rows.items():
        lat = sorted(r.pop("latency_ms"))
        r["latency_ms_p50"] = lat[len(lat) // 2] if lat else 0.0
        r["latency_ms_p99"] = lat[int(len(lat) * 0.99)] if lat else 0.0
        r["latency_ms_max"] = lat[-1] if lat else 0.0
        r["actions_by_type"] = {f"type_{k}": v for k, v in sorted(r["actions_by_type"].items())}
        out["agents"][name] = r
    return out


def live_jobs(data: Path) -> List[Tuple[str, str, str, str, str, str]]:
    base = REPO_ROOT / "local" / "evaluation" / LIVE_CARD
    jobs = []
    for record_path in sorted((base / "games").glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        game = record_path.stem
        kind = "LA" if (".H1." in game or ".H2." in game) else "LB"
        jobs.append((str(data), kind, str(base / "capture" / f"{game}.timeline.pkl"), str(record_path),
                     str(record["scenario_id"]), str(record["map_id"])))
    return jobs


def cmd_genuine(args: argparse.Namespace) -> int:
    jobs = S34.genuine_jobs(args.data) + live_jobs(args.data)
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "genuine-private.json"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    inputs = {"files": [{"path": Path(j[2]).relative_to(REPO_ROOT).as_posix(), "sha256": S34.sha256(Path(j[2]))}
                        for j in jobs]}
    with mp.Pool(args.workers) as pool:
        results = pool.map(_genuine_job, jobs)
    out.write_text(json.dumps({"inputs": inputs, "games": results}, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ precursors
def loss_episodes(steps: List[Mapping[str, Any]], samples: Mapping[int, Any], colour: int, seat: int,
                  zone_of) -> List[Dict[str, Any]]:
    """Held-objective losses of the candidate side (as ``scripts/s35_loss_episodes.py`` reads them), with the last
    standing defenders that the recorded candidate ordered away and the decision step of that order."""
    episodes = []
    prev: Dict[int, Any] = {}
    for i, s in enumerate(steps):
        for coord, flag, _ in s["cities"]:
            if prev.get(coord) == colour and flag != colour:
                zone = zone_of(coord)
                departures = []
                for j in range(i - 1, max(-1, i - 1800), -1):
                    standers = [r for r in steps[j]["units"] if r[1] == colour and r[2] in (1, 2) and not r[9]
                                and r[4] in zone and r[5] == 0]
                    if not standers:
                        continue
                    for r in standers:
                        for back in range(0, 3):
                            sample = samples.get(steps[j]["cur_step"] - back)
                            snap = sample["seats"].get(str(seat)) if sample else None
                            for p in (snap.get("plans") or ()) if snap else ():
                                if p[0] == r[0] and p[4] == 1:
                                    departures.append((r[0], steps[j]["cur_step"] - back))
                    break
                episodes.append({"objective": coord, "step": s["cur_step"], "departures": sorted(set(departures))})
            prev[coord] = flag
    return episodes


def _precursor_job(job: Tuple[str, str, Mapping[str, Any], str]) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.integrated import facts as F
    data, work, game, map_id = job
    colour = 0 if game["condition"] == "H1" else 1
    seat = 1 if colour == 0 else 11
    compact = json.loads((Path(work) / "capture" / f"{game['game_id']}.timeline.json").read_text(encoding="utf-8"))
    steps = [s for s in compact["steps"] if s["k"] >= 0]
    windows = pickle.load(open(Path(work) / "capture" / f"{game['game_id']}.timeline.pkl", "rb"))
    samples = {s["cur_step"]: s for s in windows["samples"]}
    inputs = sdk_data.load_inputs(Path(data), game["scenario_id"], map_id)
    zone_of = lambda h: F.zone(h)  # noqa: E731 - the engine maps are 100 x 100 or smaller
    episodes = loss_episodes(steps, samples, colour, seat, zone_of)
    decisions: Dict[str, Dict[int, Tuple[List[Mapping[str, Any]], Dict[int, Tuple[str, bool]]]]] = {}
    fidelity = {"decisions": 0, "differing": 0}
    for name in AGENTS:
        agent = make_agent(name, seat, colour, inputs.cost)
        per: Dict[int, Tuple[List[Mapping[str, Any]], Dict[int, Tuple[str, bool]]]] = {}
        for sample in sorted(windows["samples"], key=lambda s: s["k"]):
            snap = sample["seats"].get(str(seat))
            if snap is None:
                continue
            raw = pickle.loads(snap["observation"])
            actions = agent.step(raw)
            stances: Dict[int, Tuple[str, bool]] = {}
            for row in agent.last_trace.diagnostics or ():
                m = STANCE_ROW.match(str(row))
                if m:
                    stances[int(m.group(1))] = (m.group(2), m.group(3) != "[]")
            per[sample["cur_step"]] = ([dict(a) for a in actions], stances)
            if name == "S34-MO":
                fidelity["decisions"] += 1
                fidelity["differing"] += sorted(_key(a) for a in actions) != sorted(_key(a) for a in snap["submitted"])
        decisions[name] = per
    rows: Dict[str, List[Dict[str, Any]]] = {name: [] for name in AGENTS}
    for ep in episodes:
        zone = zone_of(ep["objective"])
        t = ep["step"]
        for name in AGENTS:
            per = decisions[name]
            at = max((s for s in per if s <= t - 150), default=None)
            stance = per[at][1].get(ep["objective"], ("none", False))[0] if at is not None else "none"
            kept = True
            for unit, step in ep["departures"]:
                actions = per.get(step, ([], {}))[0]
                if any(a.get("obj_id") == unit and a.get("type") == 1 and a["move_path"][-1] not in zone
                       for a in actions):
                    kept = False
            responded = False
            here = {r[0]: r[4] for s in steps if s["cur_step"] == t - 300 for r in s["units"]}
            for step in range(max(0, t - 300), t):
                actions, stances = per.get(step, ([], {}))
                if stances.get(ep["objective"], ("", False))[1]:
                    responded = True
                for a in actions:
                    if a.get("type") == 1 and a["move_path"][-1] in zone and here.get(a.get("obj_id")) not in zone:
                        responded = True
            rows[name].append({"alerted": stance in THREATENED, "departure": bool(ep["departures"]), "kept": kept,
                               "responded": responded, "stance_b150": stance})
    return {"position": game["position"], "scenario_id": game["scenario_id"], "condition": game["condition"],
            "episodes": len(episodes), "rows": rows, "fidelity": fidelity}


def cmd_precursors(args: argparse.Namespace) -> int:
    from miaosuan_agent.evaluation import s34_live as sl
    cards = load("build_s34_card")
    card = json.loads(cards.CARD.read_text(encoding="utf-8"))
    maps = {s["scenario_id"]: s["map_id"] for s in card["scenarios"]}
    work = REPO_ROOT / "local" / "evaluation" / LIVE_CARD
    games = [g for g in sl.schedule(cards.CANDIDATE_ID) if g["stage"] == "A"]
    jobs = [(str(args.data), str(work), g, maps[g["scenario_id"]]) for g in games]
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "precursors-private.json"
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    with mp.Pool(args.workers) as pool:
        results = sorted(pool.map(_precursor_job, jobs), key=lambda r: r["position"])
    out.write_text(json.dumps(results, sort_keys=True) + "\n", encoding="utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ select
def genuine_summary(games: List[Mapping[str, Any]], name: str) -> Dict[str, Any]:
    total = collections.Counter()
    actions = collections.Counter()
    p99, worst = [], 0.0
    by_kind = collections.defaultdict(collections.Counter)
    for g in games:
        r = g["agents"][name]
        for k in ("decisions", "play_decisions", "rejections", "independent_illegal", "fallbacks", "contract_errors",
                  "decisions_differing_from_control"):
            total[k] += r[k]
            by_kind[g["kind"]][k] += r[k]
        actions.update(r["actions_by_type"])
        p99.append(r["latency_ms_p99"])
        worst = max(worst, r["latency_ms_max"])
    out = dict(total)
    out.update(latency_ms_p99=round(max(p99) if p99 else 0.0, 3), latency_ms_max=round(worst, 3),
               actions_by_type=dict(sorted(actions.items())),
               by_population={k: dict(v) for k, v in sorted(by_kind.items())}, games=len(games))
    return out


def cmd_select(args: argparse.Namespace) -> int:
    from miaosuan_agent.evaluation import s34_offline as so34
    from miaosuan_agent.evaluation import s35_offline as so
    games = [json.loads(line) for line in (args.out / "model.jsonl").read_text(encoding="utf-8").splitlines() if line]
    crashes = [g for g in games if "crash" in g]
    genuine = json.loads((args.out / "genuine-private.json").read_text(encoding="utf-8"))
    precursors = json.loads((args.out / "precursors-private.json").read_text(encoding="utf-8"))
    model_public: Dict[str, Any] = {"crashes": len(crashes), "populations": {}}
    for population in ("M-inert", "M-v2", "M-v2-ablation"):
        pop_games = [g for g in games if g.get("population") == population and "crash" not in g]
        names = AGENTS if population != "M-v2-ablation" else ABLATIONS
        model_public["populations"][population] = {n: so34.summarise_model(pop_games, n) for n in names}
    precursor_public: Dict[str, Any] = {"episodes_by_game": {f"p{r['position']:02d}": r["episodes"] for r in precursors},
                                        "control_fidelity": {
                                            "decisions": sum(r["fidelity"]["decisions"] for r in precursors),
                                            "differing": sum(r["fidelity"]["differing"] for r in precursors)},
                                        "agents": {}}
    for name in AGENTS:
        precursor_public["agents"][name] = so.summarise_precursors([row for r in precursors for row in r["rows"][name]])
    summaries = {}
    for name in so.CANDIDATES:
        summaries[name] = {"model": {p: model_public["populations"][p][name] for p in ("M-inert", "M-v2")},
                           "genuine": genuine_summary(genuine["games"], name),
                           "precursors": precursor_public["agents"][name]}
    control = {"model": {p: model_public["populations"][p]["S34-MO"] for p in ("M-inert", "M-v2")},
               "fidelity": precursor_public["control_fidelity"]}
    decision = so.select(summaries, control)
    if crashes:
        decision = {"selected": None, "rule": "a model game crashed", "crashes": len(crashes)}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    dump = lambda data: json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"  # noqa: E731
    (PUBLIC / "model.json").write_text(dump(model_public), encoding="utf-8", newline="\n")
    (PUBLIC / "genuine.json").write_text(dump({n: genuine_summary(genuine["games"], n) for n in AGENTS}
                                              | {"inputs": genuine["inputs"]}), encoding="utf-8", newline="\n")
    (PUBLIC / "precursors.json").write_text(dump(precursor_public), encoding="utf-8", newline="\n")
    (PUBLIC / "selection.json").write_text(dump(decision), encoding="utf-8", newline="\n")
    print(json.dumps({"selected": decision["selected"], "rule": decision["rule"]}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("model", cmd_model), ("genuine", cmd_genuine), ("precursors", cmd_precursors),
                       ("select", cmd_select)):
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
