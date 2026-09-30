"""Offline latency benchmark of the frozen baseline-v1 policy on recorded canonical observations.

    python scripts/replay_latency_benchmark.py sequence --out PRIVATE.jsonl.gz [--corpus DIR]
    python scripts/replay_latency_benchmark.py extract --out-dir DIR [--corpus DIR]
    python scripts/replay_latency_benchmark.py states --states DIR --out PRIVATE.json [--repetitions N]
    python scripts/replay_latency_benchmark.py cold --state FILE      (one first call; used by ``states``)

No engine is involved. The observations are those an agent received in recorded games (the
replay corpus, or states captured by scripts/diagnose_latency_engine.py); every file read and
written lives under the git-ignored ``local/`` tree. The policy is the frozen baseline-v1
(``ReservationAgent``, exactly as the harness constructs it) and is called through ``agent.step``,
the call the harness times.

``sequence`` replays each recorded game seat by seat in order with one persistent agent (the routing
memo evolves as in a game) under the instrumentation probe and writes one private row per decision:
wall, CPU and GC time, components, routing workload and decision workload. ``extract`` writes the
representative states. ``states`` benchmarks each state: a fixed number of cold first calls, each in
a fresh interpreter; warm calls with a fresh agent per call (empty routing memo); warm calls on one
agent (memo warm); every call's decision-trace digest must equal the expected one.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.decision import digest  # noqa: E402
from miaosuan_agent.decision.policy import Memory  # noqa: E402
from miaosuan_agent.diagnostics import instrument  # noqa: E402
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest  # noqa: E402
from miaosuan_agent.evaluation.stats import exact_rank_value  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import ReservationAgent  # noqa: E402

FROZEN = "1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9"
CORPUS = REPO_ROOT / "local" / "replay-corpus"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
REPETITIONS = 200
COLD_RUNS = 10


def frozen_or_exit() -> None:
    if policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0] != FROZEN:
        raise SystemExit("REFUSED: the policy source is not the frozen baseline-v1")


def costs_for(scenario_id: str, map_id: str) -> Any:
    root = DATA / scenario_id / "Data"
    return sdk_data.load_inputs(root, scenario_id, map_id).cost


def read_corpus(path: Path) -> Tuple[Dict[str, Any], Iterator[Dict[str, Any]]]:
    handle = gzip.open(path, "rt", encoding="utf-8")
    header = json.loads(handle.readline())

    def lines() -> Iterator[Dict[str, Any]]:
        with handle:
            for line in handle:
                yield json.loads(line)
    return header, lines()


def new_agent(seat: int, faction: int, cost: Any) -> ReservationAgent:
    agent = ReservationAgent()
    agent.setup({"seat": seat, "faction": faction, "cost_data": cost})
    return agent


def workload(agent: ReservationAgent, actions: List[Any]) -> Dict[str, Any]:
    trace = agent.last_trace
    categories: Dict[str, int] = {}
    candidates = {"engage": 0, "occupy": 0, "move": 0}
    for unit in trace.units:
        categories[unit.rule] = categories.get(unit.rule, 0) + 1
        for name, count in unit.candidates:
            candidates[name] = candidates.get(name, 0) + count
    return {"units": len(trace.units), "emitted": len(actions), "selected": categories, "candidates": candidates,
            "move_units": {u.obj_id for u in trace.units if u.rule == "move"}}


def sequence(args: argparse.Namespace) -> int:
    frozen_or_exit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    probe = instrument.Probe()
    written = 0
    with probe.installed(), gzip.open(args.out, "wt", encoding="utf-8") as out:
        for path in sorted(args.corpus.glob("*.jsonl.gz")):
            header, records = read_corpus(path)
            cost = costs_for(header["scenario_id"], header["map_id"])
            agents: Dict[int, ReservationAgent] = {}
            for record in records:
                seat, faction = record["seat"], record["faction"]
                if seat not in agents:
                    agents[seat] = new_agent(seat, faction, cost)
                agent = agents[seat]
                observation = typed_json.decode(record["observation"])
                with probe.decision({"game": header["game_id"], "scenario_id": header["scenario_id"], "seat": seat,
                                     "decision": record["step"]}) as measured:
                    actions = agent.step(observation)
                work = workload(agent, actions)
                per_unit = measured["routing"].pop("per_unit")
                wasted = sum(1 for u in per_unit if u["requests"] and u["obj_id"] not in work["move_units"])
                work["move_units"] = len(work["move_units"])
                row = dict(measured, workload=work, trace_digest=digest(agent.last_trace),
                           routing_for_units_not_moving=wasted,
                           routing_units=sum(1 for u in per_unit if u["requests"]))
                out.write(json.dumps(row, sort_keys=True) + "\n")
                written += 1
    print(f"wrote {written} decisions to {args.out}")
    return 0


def extract(args: argparse.Namespace) -> int:
    """Representative states: first play decision and a later one of the largest and the smallest scenario."""
    frozen_or_exit()
    picks = {"2130511121": [1, 1000], "2010131194": [1, 900]}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.corpus.glob("*.jsonl.gz")):
        header, records = read_corpus(path)
        if header["scenario_id"] not in picks:
            continue
        cost = costs_for(header["scenario_id"], header["map_id"])
        seat_wanted = max(p["seat"] for p in header["players"])  # blue: the seat of the C3 tail
        agent = None
        for record in records:
            if record["seat"] != seat_wanted:
                continue
            if agent is None:
                agent = new_agent(record["seat"], record["faction"], cost)
            memory = agent.memory
            observation = typed_json.decode(record["observation"])
            agent.step(observation)
            if record["step"] in picks[header["scenario_id"]]:
                name = f"{header['scenario_id']}-seat{record['seat']}-decision{record['step']}"
                state = {"name": name, "source": f"replay corpus {header['game_id']}", "scenario_id": header["scenario_id"],
                         "map_id": header["map_id"], "seat": record["seat"], "faction": record["faction"],
                         "decision": record["step"], "memory": {"deployment_sent": memory.deployment_sent},
                         "observation": record["observation"], "expected_trace_digest": digest(agent.last_trace)}
                (args.out_dir / f"{name}.json").write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
                print("extracted", name)
    return 0


def load_state(path: Path) -> Tuple[Dict[str, Any], Any, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    return state, typed_json.decode(state["observation"]), costs_for(state["scenario_id"], state["map_id"])


def prepared(state: Mapping[str, Any], cost: Any) -> ReservationAgent:
    agent = new_agent(state["seat"], state["faction"], cost)
    agent.memory = Memory(deployment_sent=bool(state["memory"]["deployment_sent"]))
    return agent


def cold(args: argparse.Namespace) -> int:
    state, observation, cost = load_state(args.state)
    agent = prepared(state, cost)
    thread0, start = time.thread_time(), time.perf_counter()
    agent.step(observation)
    wall, cpu = time.perf_counter() - start, time.thread_time() - thread0
    print(json.dumps({"wall": wall, "thread_cpu": cpu, "trace_digest": digest(agent.last_trace)}))
    return 0


def distribution(values: List[float]) -> Dict[str, float]:
    return {"n": len(values), "first_ms": values[0] * 1000, "p50_ms": exact_rank_value(values, 50) * 1000,
            "p95_ms": exact_rank_value(values, 95) * 1000, "p99_ms": exact_rank_value(values, 99) * 1000,
            "max_ms": max(values) * 1000, "mean_ms": statistics.fmean(values) * 1000}


def states(args: argparse.Namespace) -> int:
    frozen_or_exit()
    results = {}
    for path in sorted(args.states.glob("*.json")):
        state, observation, cost = load_state(path)
        expected = state["expected_trace_digest"]
        digests = set()
        cold_runs = []
        for _ in range(COLD_RUNS):
            output = subprocess.run([sys.executable, str(Path(__file__).resolve()), "cold", "--state", str(path)],
                                    capture_output=True, text=True, check=True).stdout
            measured = json.loads(output)
            cold_runs.append(measured["wall"])
            digests.add(measured["trace_digest"])
        fresh, fresh_cpu, gc_seconds = [], [], []
        probe = instrument.Probe()
        with probe.installed():
            for _ in range(args.repetitions):
                agent = prepared(state, cost)
                with probe.decision() as measured:
                    agent.step(observation)
                fresh.append(measured["wall"])
                fresh_cpu.append(measured["thread_cpu"])
                gc_seconds.append(measured["gc"]["seconds"])
                digests.add(digest(agent.last_trace))
            components = {k: statistics.fmean(d["components"][k] for d in probe.decisions) * 1000
                          for k in probe.decisions[0]["components"]}
            routing = {k: statistics.fmean(d["routing"][k] for d in probe.decisions)
                       for k in ("requests", "dijkstra_runs", "nodes_settled", "distinct_keys", "move_candidate_calls")}
        warm = []
        agent = prepared(state, cost)
        for _ in range(args.repetitions):
            agent.memory = Memory(deployment_sent=bool(state["memory"]["deployment_sent"]))
            start = time.perf_counter()
            agent.step(observation)
            warm.append(time.perf_counter() - start)
            digests.add(digest(agent.last_trace))
        unprobed = []
        for _ in range(args.repetitions):
            agent = prepared(state, cost)
            start = time.perf_counter()
            agent.step(observation)
            unprobed.append(time.perf_counter() - start)
            digests.add(digest(agent.last_trace))
        results[state["name"]] = {
            "decision": state["decision"], "scenario_id": state["scenario_id"], "source": state["source"],
            "cold_process_first_call": distribution(cold_runs),
            "warm_fresh_agent_probed": distribution(fresh),
            "warm_fresh_agent_unprobed": distribution(unprobed),
            "warm_same_agent_memo_warm": distribution(warm),
            "fresh_agent_cpu_share_median": statistics.median(c / w for c, w in zip(fresh_cpu, fresh) if w),
            "fresh_agent_gc_seconds_max": max(gc_seconds),
            "components_mean_ms": components, "routing_mean": routing,
            "probe_overhead_ms_median": (exact_rank_value(fresh, 50) - exact_rank_value(unprobed, 50)) * 1000,
            "trace_digests": sorted(digests), "trace_equal": digests == {expected},
        }
        print(state["name"], "trace equal:", digests == {expected})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"repetitions": args.repetitions, "cold_runs": COLD_RUNS, "states": results},
                                   indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if all(r["trace_equal"] for r in results.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sequence")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--corpus", type=Path, default=CORPUS)
    p.set_defaults(func=sequence)
    p = sub.add_parser("extract")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--corpus", type=Path, default=CORPUS)
    p.set_defaults(func=extract)
    p = sub.add_parser("states")
    p.add_argument("--states", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repetitions", type=int, default=REPETITIONS)
    p.set_defaults(func=states)
    p = sub.add_parser("cold")
    p.add_argument("--state", type=Path, required=True)
    p.set_defaults(func=cold)
    args = parser.parse_args()
    gc.collect()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
