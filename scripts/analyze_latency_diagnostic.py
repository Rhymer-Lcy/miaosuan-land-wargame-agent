"""Summarize the latency diagnostic into public, privacy-safe findings.

    python scripts/analyze_latency_diagnostic.py [--check]

Inputs (private, under the git-ignored ``local/diagnostics/latency/``): the offline sequence replay
rows, the offline state benchmark, and the instrumented diagnostic games of the registered plan.
Output: ``evaluation/latency-diagnostic-1/findings.json`` with counts, durations, shares and rank
correlations only (no observation, unit id, hex or trace content). ``--check`` rebuilds it and
compares with the committed file.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, MoveMode  # noqa: E402
from miaosuan_agent.diagnostics import latency as lat  # noqa: E402
from miaosuan_agent.evaluation import stats  # noqa: E402
from miaosuan_agent.evaluation.metrics import compare  # noqa: E402

LOCAL = REPO_ROOT / "local" / "diagnostics" / "latency"
PLAN = REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json"
OUT = REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "findings.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
SCHEMA = "miaosuan-latency-findings/1"
POLICY = "baseline-v1-candidate-occupy-reservation"
WORK_FIELDS = ("units", "emitted", "candidates_total", "move_candidates", "requests", "dijkstra_runs", "nodes_settled")


def rows(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def ms(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value * 1000, 3)


def dominant(record: Mapping[str, Any]) -> str:
    components = dict(record["components"])
    if record["gc"]["seconds"] >= 0.5 * record["wall"]:
        return "garbage collection"
    return max(components, key=components.get)


def distribution(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "p50": stats.exact_rank_value(values, 50), "p95": stats.exact_rank_value(values, 95),
            "p99": stats.exact_rank_value(values, 99), "max": max(values), "min": min(values)}


def graph_size(scenario_id: str, map_id: str) -> Dict[str, Any]:
    costs = MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario_id / "Data", scenario_id, map_id).cost)
    return {
            "nodes_by_mode": {m.name.lower(): len(costs.edges[m]) for m in MoveMode},
            "edges_by_mode": {m.name.lower(): sum(len(v) for v in costs.edges[m].values()) for m in MoveMode}}


def offline_sequence() -> Dict[str, Any]:
    data = list(rows(LOCAL / "offline-sequence.jsonl.gz"))
    for row in data:
        work = row["workload"]
        row["_work"] = {"units": work["units"], "emitted": work["emitted"],
                        "candidates_total": sum(work["candidates"].values()), "move_candidates": work["candidates"]["move"],
                        "requests": row["routing"]["requests"], "dijkstra_runs": row["routing"]["dijkstra_runs"],
                        "nodes_settled": row["routing"]["nodes_settled"]}
    walls = [r["wall"] for r in data]
    no_gc = [r for r in data if r["gc"]["collections"] == 0]
    big = [r for r in data if r["meta"]["scenario_id"] == "2130511121" and r["meta"]["decision"] >= 1]

    def correlations(subset: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
        return {f: stats.spearman([r["wall"] for r in subset], [r["_work"][f] for r in subset]) for f in WORK_FIELDS}

    total_wall = sum(walls)
    components: Dict[str, float] = {}
    slow_components: Dict[str, float] = {}
    slow = [r for r in data if r["wall"] > 0.1]
    for row in data:
        for k, v in row["components"].items():
            components[k] = components.get(k, 0.0) + v
    for row in slow:
        for k, v in row["components"].items():
            slow_components[k] = slow_components.get(k, 0.0) + v
    top = sorted(data, key=lambda r: -r["wall"])[:15]
    requests = sum(r["routing"]["requests"] for r in data)
    runs = sum(r["routing"]["dijkstra_runs"] for r in data)
    routed_units = sum(r["routing_units"] for r in data)
    wasted = sum(r["routing_for_units_not_moving"] for r in data)
    first = [r for r in data if r["meta"]["decision"] == 1]
    full = [r["gc"]["full_seconds"] for r in data if r["gc"]["by_generation"].get("2")]
    heap = [{"scenario_id": r["meta"]["scenario_id"], "seat": r["meta"]["seat"], "decision": r["meta"]["decision"],
             "objects": r["tracked_objects_after"]} for r in data if "tracked_objects_after" in r]
    return {
        "decisions": len(data), "games": len({r["meta"]["game"] for r in data}),
        "full_collections_inside_decisions": {"count": len(full), "seconds": distribution(full)},
        "tracked_objects": heap,
        "wall_ms": {k: ms(v) for k, v in distribution(walls).items() if k != "n"},
        "threshold_counts": {f">{t}ms": sum(1 for w in walls if w > t / 1000) for t in lat.THRESHOLDS_MS},
        "classes_over_10ms": _count(lat.classify(r["wall"], r["thread_cpu"], r["gc"]["seconds"]) for r in data if r["wall"] > 0.01),
        "top_decisions": [{"scenario_id": r["meta"]["scenario_id"], "seat": r["meta"]["seat"], "decision": r["meta"]["decision"],
                           "wall_ms": ms(r["wall"]), "thread_cpu_ms": ms(r["thread_cpu"]), "gc_ms": ms(r["gc"]["seconds"]),
                           "gc_generations": r["gc"]["by_generation"], "dominant": dominant(r),
                           "dijkstra_runs": r["routing"]["dijkstra_runs"], "routing_requests": r["routing"]["requests"],
                           "units": r["workload"]["units"]} for r in top],
        "component_share_all": {k: round(v / total_wall, 6) for k, v in sorted(components.items())},
        "component_share_over_100ms": {k: round(v / sum(r["wall"] for r in slow), 6) for k, v in sorted(slow_components.items())},
        "spearman_wall_vs_workload": {"all": correlations(data), "without_gc": correlations(no_gc),
                                      "largest_scenario_play": correlations(big)},
        "routing": {"requests": requests, "dijkstra_runs": runs, "memo_hits": requests - runs,
                    "units_routed": routed_units, "units_routed_but_not_moving": wasted,
                    "share_routed_not_moving": wasted / routed_units if routed_units else None,
                    "routing_time_share": round((components.get("dijkstra", 0.0) + components.get("routing_lookup", 0.0))
                                                / total_wall, 6),
                    "first_play_decisions": [{"scenario_id": r["meta"]["scenario_id"], "seat": r["meta"]["seat"],
                                              "wall_ms": ms(r["wall"]), "dijkstra_ms": ms(r["components"]["dijkstra"]),
                                              "dijkstra_runs": r["routing"]["dijkstra_runs"],
                                              "distinct_keys": r["routing"]["distinct_keys"],
                                              "requests": r["routing"]["requests"], "units": r["workload"]["units"],
                                              "nodes_settled_per_run": r["routing"]["nodes_settled"] // max(1, r["routing"]["dijkstra_runs"])}
                                             for r in sorted(first, key=lambda r: -r["wall"])]},
    }


def _count(values: Iterator[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def offline_states() -> Dict[str, Any]:
    result: Dict[str, Any] = {"states": {}}
    for file in ("offline-states.json", "offline-states-engine.json"):
        path = LOCAL / file
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result.update(repetitions=data["repetitions"], cold_runs=data["cold_runs"])
        for name, entry in sorted(data["states"].items()):
            clean = {k: v for k, v in entry.items() if k not in ("trace_digests", "source")}
            clean["source"] = ("replay corpus (recorded game)" if entry["source"].startswith("replay corpus")
                               else entry["source"])
            result["states"][re.sub(r"-seat[0-9]+", "", name)] = clean
    return result


def engine_game(entry: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    path = LOCAL / "engine" / f"{entry['id']}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    record = payload["record"]
    decisions = list(rows(LOCAL / "engine" / payload["decisions_file"]))
    outer = {s["seat"]: s["latency_us"] for s in record["seats"]}
    seats: Dict[str, Any] = {}
    for seat_no in sorted({d["meta"]["seat"] for d in decisions}):
        mine = [d for d in decisions if d["meta"]["seat"] == seat_no]
        policy = mine[0]["meta"]["policy"]
        slow = [d for d in mine if d["wall"] > 0.1]
        overhead = [outer[seat_no][d["meta"]["decision"]] / 1e6 - d["wall"] for d in mine
                    if "tracked_objects_after" not in d["meta"]]
        seats[str(seat_no)] = {
            "policy": policy, "decisions": len(mine),
            "threshold_counts": {f">{t}ms": sum(1 for d in mine if d["wall"] > t / 1000) for t in lat.THRESHOLDS_MS},
            "wall_ms": {k: ms(v) for k, v in distribution([d["wall"] for d in mine]).items() if k != "n"},
            "over_100ms": [{"decision": d["meta"]["decision"], "wall_ms": ms(d["wall"]), "thread_cpu_ms": ms(d["thread_cpu"]),
                            "gc_ms": ms(d["gc"]["seconds"]), "full_gc_ms": ms(d["gc"]["full_seconds"]),
                            "gc_generations": d["gc"]["by_generation"],
                            "class": lat.classify(d["wall"], d["thread_cpu"], d["gc"]["seconds"]),
                            "dominant": dominant(d), "dijkstra_ms": ms(d["components"]["dijkstra"]),
                            "dijkstra_runs": d["routing"]["dijkstra_runs"],
                            "involuntary_switches": (d["rusage"] or {}).get("involuntary_switches"),
                            "voluntary_switches": (d["rusage"] or {}).get("voluntary_switches"),
                            "major_faults": (d["rusage"] or {}).get("major_faults"),
                            "minor_faults": (d["rusage"] or {}).get("minor_faults")} for d in slow],
            "classes_over_100ms": _count(lat.classify(d["wall"], d["thread_cpu"], d["gc"]["seconds"]) for d in slow),
            "cpu_share_over_100ms": distribution([d["thread_cpu"] / d["wall"] for d in slow]),
            "probe_overhead_ms": {k: ms(v) for k, v in distribution(overhead).items() if k != "n"},
        }
    full = payload["full_collections"]
    heap = sorted({(d["meta"]["decision"], d["meta"]["tracked_objects_after"]) for d in decisions
                   if "tracked_objects_after" in d["meta"]})
    return {"condition": entry["condition"], "scenario_id": entry["scenario_id"], "gc_in_decision": entry["gc_in_decision"],
            "session": payload["session"], "status": record["status"], "steps": record["steps"],
            "session_state_changed": payload["session_close"]["state_changed"],
            "loadavg_start": payload["loadavg_start"], "loadavg_end": payload["loadavg_end"],
            "gc_thresholds": payload["gc_thresholds"], "python": payload["python"], "seats": seats,
            "full_collections": {"count": len(full), "seconds": distribution([c["seconds"] for c in full]),
                                 "inside_decisions": sum(1 for c in full if c["in_decision"]),
                                 "inside_by_seat": _count(str(c["in_decision"]["seat"]) for c in full if c["in_decision"]),
                                 "durations_in_order_ms": [ms(c["seconds"]) for c in full]},
            "collections_outside_decisions": payload["collections_outside_decisions"],
            "tracked_objects": [{"decision": d, "objects": n} for d, n in heap],
            "trace_digests": {str(d["meta"]["seat"]) + ":" + str(d["meta"]["decision"]): d["meta"]["trace_digest"]
                              for d in decisions}, "_record": record}


def build() -> Dict[str, Any]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    games = {e["id"]: engine_game(e) for e in plan["games"]}
    comparisons = {}
    for left, right in (("latdiag-1", "latdiag-2"), ("latdiag-1", "latdiag-5")):
        if games.get(left) and games.get(right):
            a, b = games[left]["trace_digests"], games[right]["trace_digests"]
            shared = sorted(set(a) & set(b), key=lambda k: (int(k.split(":")[0]), int(k.split(":")[1])))
            result = compare(games[left]["_record"], games[right]["_record"])
            shots = [int(s["first_step_by_type"]["2"]) for s in games[left]["_record"]["seats"] if "2" in s["first_step_by_type"]]
            comparisons[f"{left} vs {right}"] = {
                "decisions_compared": len(shared),
                "first_differing_trace": next((k for k in shared if a[k] != b[k]), None),
                "state_first_divergence": result["state_first_divergence"],
                "first_shot_decision": min(shots) if shots else None,
                "traces_equal_while_states_equal": all(seat["traces_equal_while_states_equal"] for seat in result["seats"])}
    for game in games.values():
        if game:
            game.pop("trace_digests")
            game.pop("_record")
    size = {s: graph_size(s, m) for s, m in (("2130511121", "21"), ("2010131194", "94"))}
    bound_path = LOCAL / "offline-bound.json"
    bound = json.loads(bound_path.read_text(encoding="utf-8")) if bound_path.exists() else None
    if bound is not None:
        bound = {name.split("-seat")[0] + f"-decision{entry['decision']}": entry for name, entry in sorted(bound.items())}
    return {"schema": SCHEMA, "plan": plan["plan_id"], "offline_sequence": offline_sequence(),
            "target_bounded_search_estimate": bound,
            "offline_states": offline_states(), "graph_size": size, "engine_games": games,
            "trace_comparisons": comparisons}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
