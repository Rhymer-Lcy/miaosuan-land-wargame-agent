"""Decision-latency records: per-decision rows, threshold counts, concentration, outlier classes.

Rows are derived from private game records (the per-decision ``latency_us`` lists and the stage
transitions) and carry no scenario content beyond identifiers the public results already hold.
Percentiles use the nearest rank with the rank computed exactly (:func:`..evaluation.stats.
exact_rank_value`). Outlier classes compare wall time with CPU time and garbage-collection time
measured for the same decision; their thresholds are fixed here, not tuned on data.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..evaluation.stats import exact_rank_value

THRESHOLDS_MS = (10, 50, 100, 250, 400, 1000)
#: Outlier classes. CPU share = thread CPU time / wall time; GC share = collection time inside the decision / wall.
SCHEDULER_CPU_SHARE = 0.5   # below: the thread mostly waited, so the wall time is not computation
GC_SHARE = 0.5              # at or above: a collection took most of the decision
COMPUTE_CPU_SHARE = 0.8     # at or above, with little collection time: the policy computed


class RecordError(ValueError):
    """A game record lacks what latency rows need."""


def stage_at(transitions: Sequence[Mapping[str, Any]], decision: int) -> Optional[int]:
    """The engine stage at decision ``decision``: that of the last transition at or before it."""
    stage = None
    for item in sorted(transitions, key=lambda t: t["step"]):
        if item["step"] <= decision:
            stage = item["stage"]
    return stage


def decision_rows(record: Mapping[str, Any], policies: Iterable[str]) -> List[Dict[str, Any]]:
    """One row per decision of every seat playing one of ``policies``."""
    wanted = set(policies)
    try:
        transitions = record["stage_transitions"]
        seats = record["seats"]
        base = {k: record[k] for k in ("game_id", "scenario_id", "condition", "repetition")}
    except (KeyError, TypeError) as exc:
        raise RecordError(f"record lacks {exc}") from exc
    play_start = next((t["step"] for t in sorted(transitions, key=lambda t: t["step"]) if t["stage"] == 2), None)
    rows = []
    for seat in seats:
        if seat.get("policy") not in wanted:
            continue
        latencies = seat.get("latency_us")
        if not isinstance(latencies, list) or not all(isinstance(v, int) and v >= 0 for v in latencies):
            raise RecordError(f"{base['game_id']} seat {seat.get('seat')}: latency_us is not a list of non-negative ints")
        for index, value in enumerate(latencies):
            rows.append(dict(base, session=record.get("session"), seat=seat["seat"], policy=seat["policy"],
                             decision=index, stage=stage_at(transitions, index),
                             first_play=index == play_start, play_index=None if play_start is None or
                             index < play_start else index - play_start, latency_us=value))
    return rows


def threshold_counts(rows: Sequence[Mapping[str, Any]], thresholds: Sequence[int] = THRESHOLDS_MS) -> Dict[str, int]:
    return {f">{t}ms": sum(1 for r in rows if r["latency_us"] > t * 1000) for t in thresholds}


def grouped(rows: Sequence[Mapping[str, Any]], key: Tuple[str, ...],
            thresholds: Sequence[int] = THRESHOLDS_MS) -> Dict[str, Dict[str, Any]]:
    """Decisions and threshold counts per group (only groups with at least one decision)."""
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault("|".join(str(row[k]) for k in key), []).append(row)
    return {name: dict(decisions=len(items), **threshold_counts(items, thresholds),
                       max_ms=max(r["latency_us"] for r in items) / 1000)
            for name, items in sorted(groups.items())}


def concentration(rows: Sequence[Mapping[str, Any]], threshold_ms: int, key: Tuple[str, ...]) -> Dict[str, Any]:
    """How the decisions above ``threshold_ms`` distribute over ``key``; shares of the total above it."""
    above = [r for r in rows if r["latency_us"] > threshold_ms * 1000]
    counts: Dict[str, int] = {}
    for row in above:
        name = "|".join(str(row[k]) for k in key)
        counts[name] = counts.get(name, 0) + 1
    total = len(above)
    return {"above": total, "groups": {k: {"count": v, "share": v / total} for k, v in
                                       sorted(counts.items(), key=lambda item: (-item[1], item[0]))}}


def summary(values_us: Sequence[int]) -> Dict[str, Optional[float]]:
    if not values_us:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
    return {"count": len(values_us), "p50_ms": exact_rank_value(values_us, 50) / 1000,
            "p95_ms": exact_rank_value(values_us, 95) / 1000, "p99_ms": exact_rank_value(values_us, 99) / 1000,
            "max_ms": max(values_us) / 1000}


def classify(wall: float, thread_cpu: Optional[float], gc_seconds: Optional[float]) -> str:
    """Class of one measured decision from its wall, thread-CPU and in-decision GC seconds."""
    if wall <= 0:
        return "unmeasurable"
    if thread_cpu is None:
        return "unclassified: no CPU time"
    gc_share = (gc_seconds or 0.0) / wall
    cpu_share = thread_cpu / wall
    if cpu_share < SCHEDULER_CPU_SHARE:
        return "scheduling or waiting"
    if gc_share >= GC_SHARE:
        return "garbage collection"
    if cpu_share >= COMPUTE_CPU_SHARE:
        return "computation"
    return "mixed"
