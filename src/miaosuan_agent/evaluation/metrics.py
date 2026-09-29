"""Metrics derived from private game records: percentiles, repetition comparison, gate checks and
the sanitized public summary.

Percentiles use the nearest-rank method: the p-th percentile of n values is the value at rank
ceil(p / 100 * n) in ascending order, so every reported percentile is an observed value.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..decision import BASELINE_ID, ActionType
from .effects import NOT_OBSERVED
from .game import sanitize

PLAY_TYPES = {str(int(t)) for t in (ActionType.MOVE, ActionType.SHOOT, ActionType.OCCUPY)}
RECORD_FIELDS = ("schema", "game_id", "status", "completion", "steps", "done", "stage_transitions", "final_scores",
                 "timings_seconds", "seats", "state_chain", "state_steps", "rng_probe", "deployment_ended")
SEAT_FIELDS = ("decisions", "latency_us", "trace_chain", "trace_steps", "actions_by_type", "steps_with_action",
               "first_step_by_type", "units_seen", "units_acted", "no_op_reasons", "gate_rejections",
               "contract_errors", "replay_checks", "replay_mismatches", "effects_by_type", "feedback_entries",
               "feedback_errors_by_code")


def nearest_rank(values: Sequence[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(percentile / 100 * len(ordered))) - 1]


def latency(values_us: Sequence[int]) -> Dict[str, Any]:
    def ms(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value / 1000, 3)

    return {"count": len(values_us), "p50_ms": ms(nearest_rank(values_us, 50)),
            "p95_ms": ms(nearest_rank(values_us, 95)), "p99_ms": ms(nearest_rank(values_us, 99)),
            "max_ms": ms(max(values_us) if values_us else None), "total_ms": ms(sum(values_us))}


def first_divergence(a: Sequence[str], b: Sequence[str]) -> Optional[int]:
    """The first index where two digest sequences differ (a length difference counts), else ``None``."""
    for index, (left, right) in enumerate(zip(a, b)):
        if left != right:
            return index
    return None if len(a) == len(b) else min(len(a), len(b))


def missing_fields(record: Mapping[str, Any]) -> List[str]:
    missing = [name for name in RECORD_FIELDS if name not in record]
    for index, seat in enumerate(record.get("seats") or []):
        missing += [f"seats[{index}].{name}" for name in SEAT_FIELDS if name not in seat]
    if not record.get("seats"):
        missing.append("seats (empty)")
    return missing


def compare(a: Mapping[str, Any], b: Mapping[str, Any]) -> Dict[str, Any]:
    """Repetition agreement. Traces are compared on the steps whose observed state agreed."""
    state = first_divergence(a.get("state_steps", []), b.get("state_steps", []))
    seats = []
    for left, right in zip(a.get("seats", []), b.get("seats", [])):
        trace = first_divergence(left["trace_steps"], right["trace_steps"])
        agreed = len(left["trace_steps"]) if state is None else min(state, len(left["trace_steps"]))
        seats.append({"seat": left["seat"], "policy": left["policy"], "trace_chain_equal":
                      left["trace_chain"] == right["trace_chain"], "trace_first_divergence": trace,
                      "traces_equal_while_states_equal": trace is None or trace >= agreed})
    return {"state_chain_equal": a.get("state_chain") == b.get("state_chain"), "state_first_divergence": state,
            "final_scores_equal": a.get("final_scores") == b.get("final_scores"), "seats": seats}


def _baseline_seats(record: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [seat for seat in record.get("seats", []) if seat["policy"] == BASELINE_ID]


def gate_check(records: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The registered criteria G1-G6 for a set of repetitions of one configuration.

    ``pass`` is ``None`` for a criterion about baseline seats in a configuration without one.
    """
    baseline = [seat for record in records for seat in _baseline_seats(record)]

    def criterion(passed: bool, detail: Any, about_baseline: bool = False) -> Dict[str, Any]:
        return {"pass": None if about_baseline and not baseline else bool(passed), "detail": detail}

    g1 = [(r["game_id"], r.get("status"), (r.get("failure") or {}).get("origin"),
           sum(s["contract_errors"] for s in r.get("seats", []))) for r in records]
    effects_bad = {}
    for seat in baseline:
        for kind in (str(int(ActionType.MOVE)), str(int(ActionType.END_DEPLOYMENT))):
            count = seat["effects_by_type"].get(kind, {}).get(NOT_OBSERVED, 0)
            if count:
                effects_bad[f"seat {seat['seat']} type {kind}"] = effects_bad.get(f"seat {seat['seat']} type {kind}", 0) + count
    legality = {"gate_rejections": sum(sum(s["gate_rejections"].values()) for s in baseline),
                "feedback_errors": sum(sum(s["feedback_errors_by_code"].values()) for s in baseline),
                "unconfirmed_moves_or_deployment": effects_bad}
    comparisons = [compare(records[0], other) for other in records[1:]]
    replay = sum(s["replay_mismatches"] for s in baseline)
    determinism = all(seat["traces_equal_while_states_equal"] for c in comparisons for seat in c["seats"]
                      if seat["policy"] == BASELINE_ID)
    return {
        "G1": criterion(all(status == "COMPLETED" and origin is None and errors == 0 for _, status, origin, errors in g1),
                        g1),
        "G2": criterion(all(r.get("deployment_ended") for r in records), [r.get("deployment_ended") for r in records]),
        "G3": criterion(all(any(s["actions_by_type"].get(t, 0) for t in PLAY_TYPES) for s in baseline),
                        [s["actions_by_type"] for s in baseline], about_baseline=True),
        "G4": criterion(legality["gate_rejections"] == 0 and legality["feedback_errors"] == 0 and not effects_bad,
                        legality, about_baseline=True),
        "G5": criterion(determinism and replay == 0 and len(records) >= 2,
                        {"replay_mismatches": replay, "comparisons": comparisons}, about_baseline=True),
        "G6": criterion(all(not missing_fields(r) for r in records), {r["game_id"]: missing_fields(r) for r in records}),
    }


def public_game(record: Mapping[str, Any]) -> Dict[str, Any]:
    """The sanitized summary of one game: counts, rates, percentiles and engine scores only."""
    failure = record.get("failure")
    probe = record.get("rng_probe") or {}
    base = probe.get("before-construct")
    return {
        "game_id": record["game_id"], "scenario_id": record["scenario_id"], "map_id": record["map_id"],
        "condition": record["condition"], "repetition": record["repetition"], "policies": record["policies"],
        "status": record.get("status"), "completion": record.get("completion"), "steps": record.get("steps"),
        "failure": None if not failure else {"origin": failure["origin"], "phase": failure["phase"],
                                             "type": failure["type"], "message": sanitize(failure["message"])[:200]},
        "final_scores": record.get("final_scores"),
        "timings_seconds": {k: round(v, 3) for k, v in (record.get("timings_seconds") or {}).items()},
        "global_rng_changed_by_engine": None if not base else {
            generator: any(point_values.get(generator) != base.get(generator) for point, point_values in probe.items())
            for generator in sorted(base)},
        "seats": [{
            "seat": s["seat"], "faction": s["faction"], "policy": s["policy"], "decisions": s["decisions"],
            "latency": latency(s["latency_us"]), "actions_by_type": s["actions_by_type"],
            "steps_with_action": s["steps_with_action"], "first_step_by_type": s["first_step_by_type"],
            "units_seen": s["units_seen"], "units_acted": s["units_acted"], "no_op_reasons": s["no_op_reasons"],
            "gate_rejections": s["gate_rejections"], "contract_errors": s["contract_errors"],
            "diagnostics": s["diagnostics"], "replay_checks": s["replay_checks"],
            "replay_mismatches": s["replay_mismatches"], "effects_by_type": s["effects_by_type"],
            "feedback_entries": s["feedback_entries"], "feedback_errors_by_code": s["feedback_errors_by_code"],
        } for s in record.get("seats", [])],
    }


def condition_summary(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregates over the games of one condition; latency percentiles over all baseline decisions."""
    baseline = [seat for record in records for seat in _baseline_seats(record)]
    actions: Dict[str, int] = {}
    for seat in baseline:
        for kind, count in seat["actions_by_type"].items():
            actions[kind] = actions.get(kind, 0) + count
    return {
        "games": len(records), "completed": sum(1 for r in records if r.get("status") == "COMPLETED"),
        "failed": sum(1 for r in records if r.get("status") == "FAIL"),
        "capped": sum(1 for r in records if r.get("status") == "CAPPED"),
        "baseline_decisions": sum(s["decisions"] for s in baseline),
        "baseline_latency": latency([value for s in baseline for value in s["latency_us"]]),
        "baseline_actions_by_type": dict(sorted(actions.items())),
        "baseline_gate_rejections": sum(sum(s["gate_rejections"].values()) for s in baseline),
        "baseline_feedback_errors": sum(sum(s["feedback_errors_by_code"].values()) for s in baseline),
        "baseline_contract_errors": sum(s["contract_errors"] for s in baseline),
        "replay_mismatches": sum(s["replay_mismatches"] for s in baseline),
        "engine_seconds": round(sum((r.get("timings_seconds") or {}).get("engine_step", 0.0) for r in records), 3),
        "wall_seconds": round(sum((r.get("timings_seconds") or {}).get("wall", 0.0) for r in records), 3),
    }
