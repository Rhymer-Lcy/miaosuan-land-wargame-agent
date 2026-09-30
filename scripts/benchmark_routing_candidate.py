"""Registered offline benchmark of the routing candidate against baseline-v1 (routing-remediation-1).

    python scripts/benchmark_routing_candidate.py run [--repetitions N] [--cold-runs N]
    python scripts/benchmark_routing_candidate.py cold --state FILE --arm ARM   (one first call; used by run)

No engine is involved, and the benchmark runs only after the equivalence replay is clean. Inputs:

* the registered diagnostic states of ``evaluation/routing-remediation-1/corpus.json`` (each file is
  verified against its pinned digest); the performance criterion is evaluated on these;
* supplementary first-play states: decision 1 of the highest seat of every other pinned replay game,
  derived by replaying that seat with baseline-v1 (they cover the remaining large scenarios; the
  no-regression rule is applied to them as well and reported separately).

For every input the two arms, baseline-v1 (``ReservationAgent``) and the candidate
(``BoundedRoutingAgent``), are called through ``agent.step`` exactly as the harness calls them, with
repetitions interleaved (the order alternates on every repetition): ``fresh_agent`` builds a new agent
per call (empty routing memo); ``memo_warm`` reuses one agent per arm; ``cold_process`` makes one call
in a new interpreter. Each call records wall time, thread CPU time and the time spent in garbage
collection during the call. Outside the timed window, every call's actions and semantic trace digest
must equal baseline-v1's reference for that input, and baseline-v1's full digest must equal the state's
recorded digest. A separate uncounted pass per arm counts the routing work: shortest-path requests,
searches, settled hexes and examined edges.

Per-call values are written privately under ``local/diagnostics/routing/``; the public summary with
the criterion verdicts is ``evaluation/routing-remediation-1/benchmark.json``.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.decision import digest  # noqa: E402
from miaosuan_agent.decision.policy import Memory  # noqa: E402
from miaosuan_agent.decision.trace import canonical_json  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest  # noqa: E402
from miaosuan_agent.evaluation.stats import exact_rank_value  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import ReservationAgent  # noqa: E402
from miaosuan_agent.experiments.routing_bounded import BoundedRoutingAgent  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID
OUT = DIRECTORY / "benchmark.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "routing"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
FINDINGS = REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "findings.json"
SCHEMA = "miaosuan-routing-benchmark/1"
ARMS: Dict[str, Callable[[], Any]] = {"baseline-v1": ReservationAgent, "candidate": BoundedRoutingAgent}
WORST = ("2130511121-seat11-decision1", "2130511121-seat11-decision1-latdiag-1")
RATIO, SLACK, FLOOR_MS = 0.50, 1.10, 0.20

_gc = {"start": 0.0, "seconds": 0.0}


def _gc_callback(phase: str, info: Mapping[str, Any]) -> None:
    if phase == "start":
        _gc["start"] = time.perf_counter()
    else:
        _gc["seconds"] += time.perf_counter() - _gc["start"]


def costs_for(scenario_id: str, map_id: str) -> Any:
    return sdk_data.load_inputs(DATA / scenario_id / "Data", scenario_id, map_id).cost


def prepared(arm: str, state: Mapping[str, Any], cost: Any) -> Any:
    agent = ARMS[arm]()
    agent.setup({"seat": state["seat"], "faction": state["faction"], "cost_data": cost})
    agent.memory = Memory(deployment_sent=bool(state["memory"]["deployment_sent"]))
    return agent


def signature(agent: Any, actions: Any) -> Tuple[str, str]:
    """What must not change: the emitted actions (content and order) and the semantic trace."""
    return (hashlib.sha256(canonical_json([dict(a) for a in actions]).encode("utf-8")).hexdigest(),
            rr.semantic_digest(agent.last_trace))


def timed(agent: Any, observation: Any) -> Tuple[Any, float, float, float]:
    _gc["seconds"] = 0.0
    thread0, start = time.thread_time(), time.perf_counter()
    actions = agent.step(observation)
    wall, cpu = time.perf_counter() - start, time.thread_time() - thread0
    return actions, wall, cpu, _gc["seconds"]


def work(arm: str, state: Mapping[str, Any], cost: Any, observation: Any) -> Tuple[Dict[str, int], Tuple[str, str]]:
    """Routing work of one fresh-agent call, counted by wrapping this agent's router instance only."""
    agent = prepared(arm, state, cost)
    router = agent.policy.router
    counts = {"requests": 0, "searches": 0, "settled": 0, "edges": 0}

    class Counting:
        def __init__(self, costs: Any) -> None:
            self.costs = costs

        def neighbours(self, mode: Any, node: int) -> Any:
            edges = self.costs.neighbours(mode, node)
            counts["edges"] += len(edges)
            return edges

    def searching(method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any) -> Any:
            real = router.costs
            router.costs = Counting(real)
            try:
                result = method(*args)
            finally:
                router.costs = real
            counts["searches"] += 1
            counts["settled"] += len(result.cost)  # the full search exposes every settled hex, the bounded one only those
            return result
        return wrapper

    def requesting(method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            counts["requests"] += 1
            return method(*args, **kwargs)
        return wrapper

    if router is not None:
        router._dijkstra = searching(router._dijkstra)
        if hasattr(router, "_bounded"):
            router._bounded = searching(router._bounded)
        router.shortest_paths = requesting(router.shortest_paths)
    actions = agent.step(observation)
    return counts, signature(agent, actions)


def lines(path: Path) -> List[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def inputs(registration: Mapping[str, Any]) -> List[Tuple[str, Path]]:
    """(kind, path) of every benchmark input; supplementary states are derived into the private tree."""
    chosen, registered_names = [], set()
    games = []
    for entry in registration["corpus"]["files"]:
        path = REPO_ROOT / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        if entry["path"].endswith(".json"):
            chosen.append(("registered", path))
            registered_names.add(json.loads(path.read_text(encoding="utf-8"))["name"])
        elif entry["role"] == "replay corpus game":
            games.append(path)
    derived = PRIVATE / "states-supplementary"
    derived.mkdir(parents=True, exist_ok=True)
    for path in games:
        records = lines(path)
        header = records[0]
        seat = max(p["seat"] for p in header["players"])
        name = f"{header['scenario_id']}-seat{seat}-decision1"
        if name in registered_names:
            continue
        cost = costs_for(header["scenario_id"], header["map_id"])
        agent = None
        for record in records[1:]:
            if record["seat"] != seat:
                continue
            if agent is None:
                agent = ReservationAgent()
                agent.setup({"seat": seat, "faction": record["faction"], "cost_data": cost})
            memory = agent.memory
            observation = typed_json.decode(record["observation"])
            agent.step(observation)
            if record["step"] == 1:
                state = {"name": name, "source": f"replay corpus {header['game_id']}",
                         "scenario_id": header["scenario_id"], "map_id": header["map_id"], "seat": seat,
                         "faction": record["faction"], "decision": 1,
                         "memory": {"deployment_sent": memory.deployment_sent}, "observation": record["observation"],
                         "expected_trace_digest": digest(agent.last_trace)}
                target = derived / f"{name}.json"
                target.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
                chosen.append(("supplementary", target))
                break
    return chosen


def distribution(values: List[float]) -> Dict[str, float]:
    return {"n": len(values), "p50_ms": exact_rank_value(values, 50) * 1000,
            "p95_ms": exact_rank_value(values, 95) * 1000, "p99_ms": exact_rank_value(values, 99) * 1000,
            "max_ms": max(values) * 1000, "min_ms": min(values) * 1000, "mean_ms": statistics.fmean(values) * 1000}


def cold(args: argparse.Namespace) -> int:
    state = json.loads(args.state.read_text(encoding="utf-8"))
    observation = typed_json.decode(state["observation"])
    agent = prepared(args.arm, state, costs_for(state["scenario_id"], state["map_id"]))
    gc.callbacks.append(_gc_callback)
    actions, wall, cpu, gc_seconds = timed(agent, observation)
    print(json.dumps({"wall": wall, "cpu": cpu, "gc": gc_seconds, "signature": list(signature(agent, actions)),
                      "digest": digest(agent.last_trace)}))
    return 0


def run(args: argparse.Namespace) -> int:
    if policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0] != rr.PARENT["policy_source_sha256"]:
        raise SystemExit("baseline-v1's policy source is not the frozen one")
    candidate_sha = policy_source_digest(sources=rr.candidate_sources())[0]
    registration = json.loads((DIRECTORY / "registration.json").read_text(encoding="utf-8"))
    equivalence = json.loads((DIRECTORY / "equivalence.json").read_text(encoding="utf-8"))
    if equivalence["unexplained_differences"] != 0 or equivalence["candidate_source_sha256"] != candidate_sha:
        raise SystemExit("REFUSED: the equivalence replay of this candidate is not clean")
    estimate = json.loads(FINDINGS.read_text(encoding="utf-8"))["target_bounded_search_estimate"]
    gc.callbacks.append(_gc_callback)
    results, private = {}, {}
    for kind, path in inputs(registration):
        state = json.loads(path.read_text(encoding="utf-8"))
        name = state["name"]
        observation = typed_json.decode(state["observation"])
        cost = costs_for(state["scenario_id"], state["map_id"])
        counts = {}
        reference = None
        for arm in ARMS:
            counts[arm], produced = work(arm, state, cost, observation)
            reference = reference or produced
            if produced != reference:
                raise SystemExit(f"{name}: {arm} differs from baseline-v1 in the counting pass")
        mismatches = 0
        calls: Dict[str, Dict[str, Dict[str, List[float]]]] = {
            mode: {arm: {"wall": [], "cpu": [], "gc": []} for arm in ARMS} for mode in ("fresh_agent", "memo_warm",
                                                                                       "cold_process")}

        def record(mode: str, arm: str, agent: Any, actions: Any, wall: float, cpu: float, gc_seconds: float) -> None:
            nonlocal mismatches
            calls[mode][arm]["wall"].append(wall)
            calls[mode][arm]["cpu"].append(cpu)
            calls[mode][arm]["gc"].append(gc_seconds)
            mismatches += signature(agent, actions) != reference
            if arm == "baseline-v1":
                mismatches += digest(agent.last_trace) != state["expected_trace_digest"]

        for index in range(args.cold_runs):
            for arm in (ARMS if index % 2 == 0 else reversed(list(ARMS))):
                output = subprocess.run([sys.executable, str(Path(__file__).resolve()), "cold", "--state", str(path),
                                         "--arm", arm], capture_output=True, text=True, check=True).stdout
                measured = json.loads(output)
                calls["cold_process"][arm]["wall"].append(measured["wall"])
                calls["cold_process"][arm]["cpu"].append(measured["cpu"])
                calls["cold_process"][arm]["gc"].append(measured["gc"])
                mismatches += tuple(measured["signature"]) != reference
                if arm == "baseline-v1":
                    mismatches += measured["digest"] != state["expected_trace_digest"]
        for index in range(args.repetitions):
            for arm in (ARMS if index % 2 == 0 else reversed(list(ARMS))):
                agent = prepared(arm, state, cost)
                actions, wall, cpu, gc_seconds = timed(agent, observation)
                record("fresh_agent", arm, agent, actions, wall, cpu, gc_seconds)
        warm = {arm: prepared(arm, state, cost) for arm in ARMS}
        for index in range(args.repetitions):
            for arm in (ARMS if index % 2 == 0 else reversed(list(ARMS))):
                agent = warm[arm]
                agent.memory = Memory(deployment_sent=bool(state["memory"]["deployment_sent"]))
                actions, wall, cpu, gc_seconds = timed(agent, observation)
                record("memo_warm", arm, agent, actions, wall, cpu, gc_seconds)
        summary: Dict[str, Any] = {"kind": kind, "scenario_id": state["scenario_id"], "decision": state["decision"],
                                   "source": state["source"], "work": counts, "output_mismatches": mismatches,
                                   "calls_checked": sum(len(calls[m][a]["wall"]) for m in calls for a in ARMS)}
        if "in_engine_wall" in state:
            summary["in_engine_wall_ms"] = state["in_engine_wall"] * 1000
        old, new = counts["baseline-v1"], counts["candidate"]
        summary["retained_work"] = {k: (new[k] / old[k] if old[k] else None) for k in ("settled", "edges")}
        key = f"{state['scenario_id']}-decision{state['decision']}"
        if key in estimate and kind == "registered" and not name.endswith("latdiag-1"):
            summary["estimate"] = {"settled": estimate[key]["settled"],
                                   "settled_until_targets": estimate[key]["settled_until_targets"],
                                   "searches": estimate[key]["searches"],
                                   "measured_equals_estimate": (old["settled"], new["settled"], new["searches"]) ==
                                   (estimate[key]["settled"], estimate[key]["settled_until_targets"],
                                    estimate[key]["searches"])}
        for mode in calls:
            summary[mode] = {}
            for arm in ARMS:
                values = calls[mode][arm]
                summary[mode][arm] = dict(distribution(values["wall"]), gc_max_ms=max(values["gc"]) * 1000,
                                          cpu_p50_ms=exact_rank_value(values["cpu"], 50) * 1000,
                                          cpu_share_median=statistics.median(c / w for c, w in
                                                                             zip(values["cpu"], values["wall"]) if w))
            summary[mode]["speedup_median"] = (summary[mode]["baseline-v1"]["p50_ms"] /
                                               summary[mode]["candidate"]["p50_ms"])
        old_p50, new_p50 = summary["fresh_agent"]["baseline-v1"]["p50_ms"], summary["fresh_agent"]["candidate"]["p50_ms"]
        if name in WORST:
            summary["criterion"] = {"rule": f"candidate median <= {RATIO} x baseline-v1 median",
                                    "ratio": new_p50 / old_p50, "pass": new_p50 <= RATIO * old_p50}
        else:
            summary["criterion"] = {"rule": f"candidate median <= baseline-v1 median x {SLACK} + {FLOOR_MS} ms",
                                    "limit_ms": old_p50 * SLACK + FLOOR_MS, "pass": new_p50 <= old_p50 * SLACK + FLOOR_MS}
        results[name] = summary
        private[name] = calls
        print(name, kind, "fresh p50 ms", round(old_p50, 3), "->", round(new_p50, 3), "mismatches", mismatches,
              "pass" if summary["criterion"]["pass"] else "FAIL", flush=True)
    registered = {n: r for n, r in results.items() if r["kind"] == "registered"}
    supplementary = {n: r for n, r in results.items() if r["kind"] == "supplementary"}
    verdict = {"worst_inputs_present": all(n in registered for n in WORST),
               "registered_criterion_pass": all(r["criterion"]["pass"] for r in registered.values()),
               "supplementary_no_regression_pass": all(r["criterion"]["pass"] for r in supplementary.values()),
               "output_mismatches": sum(r["output_mismatches"] for r in results.values()),
               "calls_checked": sum(r["calls_checked"] for r in results.values())}
    verdict["pass"] = (verdict["worst_inputs_present"] and verdict["registered_criterion_pass"]
                       and verdict["supplementary_no_regression_pass"] and verdict["output_mismatches"] == 0)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "benchmark-calls.json").write_text(json.dumps(private, sort_keys=True) + "\n", encoding="utf-8")
    public = {"schema": SCHEMA, "remediation_id": rr.REMEDIATION_ID, "corpus_sha256": registration["corpus_sha256"],
              "baseline_v1_source_sha256": rr.PARENT["policy_source_sha256"], "candidate_source_sha256": candidate_sha,
              "equivalence_sha256": hashlib.sha256((DIRECTORY / "equivalence.json").read_bytes()).hexdigest(),
              "repetitions": {"fresh_agent": args.repetitions, "memo_warm": args.repetitions,
                              "cold_process": args.cold_runs},
              "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation()},
              "performance_registered": registration["performance"], "states": results, "verdict": verdict}
    OUT.write_text(json.dumps(public, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                   newline="\n")
    print(json.dumps(verdict))
    return 0 if verdict["pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--repetitions", type=int, default=rr.PERFORMANCE["repetitions"]["fresh_agent"])
    p.add_argument("--cold-runs", type=int, default=rr.PERFORMANCE["repetitions"]["cold_process"])
    p.set_defaults(func=run)
    p = sub.add_parser("cold")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--arm", choices=sorted(ARMS), required=True)
    p.set_defaults(func=cold)
    args = parser.parse_args()
    gc.collect()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
