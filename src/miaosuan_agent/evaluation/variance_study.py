"""The registered repeated-run variance study of the unchanged ``baseline-v1``.

The study replays the eight frozen scenarios of the ``baseline-v1`` evaluation in the three
conditions that contain the policy (C1 mirror, C2 against the inert control from red, C3 from
blue) until each of the 24 configurations holds ten repetitions: repetitions 1-2 are the frozen
evaluation's own games, reused and pinned by record digest; repetitions 3-10 are 192 new games.
C4 (inert mirror) is not replayed; its two historical repetitions are the deterministic control.

This module holds the registration (``build``), the deterministic run order (``schedule``), the
per-game metrics and every registered analysis. It reads no files; the scripts do the I/O. The
policy is identified by digest only: nothing here imports or alters decision code.
"""

from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import manifest as mf
from . import refusals, stats
from .metrics import LATER_SEAT_FIELDS, REFUSAL_FIELDS, compare, nearest_rank

SCHEMA = "miaosuan-variance-study-manifest/1"
STUDY_NAME = "baseline-v1-variance-study-1"
BASELINE_IDENTITY = "baseline-v1"
#: The frozen identity of baseline-v1 (docs/BASELINE_V1.md). The runner refuses any other digest.
BASELINE_V1_SOURCE_SHA256 = "1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9"
BASELINE_V1_GOLDEN_TRACE_CHAIN = "11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66"
BASELINE_V1_MANIFEST_SHA256 = "38526b9250d8bce7facdb0f5c6303b5f2040e3939bd2bcedfe1fc2fdb14f103f"
BASELINE_V1_RESULTS_SHA256 = "ea0ec674e8e51e546684fb75696673e5c81d32d6c9dd7a0d11796a91aeaeda07"
BASELINE_V1_EXECUTED_COMMIT = "1376ca6"
BASELINE_V1_PROMOTION_COMMIT = "d315664"
RUNTIME = {"python": "3.10.20", "environment": "miaosuan-runtime", "device": "CPU only"}

ACTIVE_CONDITIONS = ("C1", "C2", "C3")
CONTROL_CONDITION = "C4"
REPETITION_TARGET = 10
HISTORICAL_REPETITIONS = (1, 2)
NEW_REPETITIONS = tuple(range(3, REPETITION_TARGET + 1))
CONSECUTIVE_FAILURE_STOP = 3

LEVEL = 0.95
BOOTSTRAP = {"resamples": 10000, "seed": 20260930}
TEMPORAL_BOOTSTRAP = {"resamples": 2000, "seed": 20260931}
MONTE_CARLO = {"simulations": 1000, "seed": 20260932}
SIZING_REPETITIONS = (2, 5, 10, 15, 20)
ALPHA, POWER = 0.05, 0.80
CONSERVATIVE_LEVEL = 0.90
MATERIAL = {"standardized_difference": 0.5, "spearman": 0.3}
DEFAULT_RULE_METRIC, DEFAULT_RULE_EFFECT = "refusals_per_1000", -0.5

#: Per-game metrics, computed over the seats of the policy under test (both seats in C1).
METRICS = {
    "red_total": "engine final score red_total",
    "blue_total": "engine final score blue_total",
    "margin": "score margin from the policy's side: red_total - blue_total in C1 (red seat) and C2, "
              "blue_total - red_total in C3",
    "unit_actions": "emitted unit actions (every action type except deployment completion 333)",
    "refusals": "engine refusals (feedback entries with an error)",
    "refusals_per_1000": "engine refusals per 1,000 emitted unit actions",
    "code_1804": "refusals with code 1804 (regression metric; 0 in the frozen evaluation)",
    "code_516": "refusals with code 516",
    "code_203": "refusals with code 203",
    "code_1804_per_1000": "code-1804 refusals per 1,000 emitted unit actions",
    "code_516_per_1000": "code-516 refusals per 1,000 emitted unit actions",
    "code_203_per_1000": "code-203 refusals per 1,000 emitted unit actions",
    "gate_rejections": "project safety-gate rejections",
    "moves": "emitted moves (type 1)",
    "shots": "emitted shots (type 2): the engagement count",
    "occupations": "emitted occupations (type 5)",
    "active_step_rate": "steps with at least one emitted action / decisions, pooled over the seats",
    "no_op_rate": "no-op unit-steps / (no-op unit-steps + emitted unit actions), pooled over the seats",
    "suppressions": "occupations suppressed by the reservation",
    "units_acted": "units that emitted at least one action",
    "latency_p50_ms": "per-decision latency (time.perf_counter) p50 over the game's decisions, nearest rank",
    "latency_p95_ms": "per-decision latency p95",
    "latency_p99_ms": "per-decision latency p99",
    "latency_max_ms": "slowest decision",
    "decisions_over_100ms": "decisions slower than 100 ms",
    "decisions_over_400ms": "decisions slower than 400 ms",
    "decision_seconds": "total policy decision time",
    "engine_seconds": "total engine step time",
    "harness_seconds": "wall - decisions - engine",
    "wall_seconds": "game wall time",
    "steps": "engine steps played",
}
#: Metrics the n=2 versus n=10 comparison and the temporal diagnostics cover.
MAJOR = ("margin", "refusals_per_1000", "code_516_per_1000", "code_203_per_1000", "active_step_rate", "no_op_rate",
         "shots", "moves", "occupations", "latency_p99_ms", "decision_seconds", "wall_seconds")
TEMPORAL = ("margin", "refusals_per_1000", "unit_actions", "shots", "moves", "occupations", "latency_p99_ms",
            "latency_max_ms", "decision_seconds", "engine_seconds", "wall_seconds")
EFFECT_GRID = {
    "margin": {"configurations": ["C2", "C3"], "absolute_points": [10, 25, 50, 100],
               "relative_to_force_value": [0.025, 0.05, 0.10]},
    "refusals_per_1000": {"configurations": list(ACTIVE_CONDITIONS), "relative_change": [-0.25, -0.5, -1.0]},
    "code_516_per_1000": {"configurations": list(ACTIVE_CONDITIONS), "relative_change": [-0.25, -0.5, -1.0]},
    "active_step_rate": {"configurations": list(ACTIVE_CONDITIONS), "relative_change": [0.05, 0.10, 0.20]},
}
EFFECT_RATIONALE = (
    "Score effects are in engine value points. The smallest absolute effect is below the smallest scenario's "
    "combined start force value and the largest is below half the median scenario's combined value "
    "(force_value_by_scenario, read from the frozen results before any new game); the relative grid scales "
    "with each scenario's own force value, so large scenarios are not favoured.",
    "The margin is sized over C2 and C3 only: in the C1 mirror both sides change with the policy, so its margin "
    "measures side asymmetry, not a policy effect.",
    "Rate effects are relative to each configuration's own mean under baseline-v1: a quarter, a half and all of a "
    "refusal rate removed; a 5, 10 and 20 percent change of the active-step rate.",
    "No value of the grid depends on an effect observed for baseline-v1.",
)


# ----------------------------------------------------------------------------------------------
# Registration


def configurations(manifest: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """(scenario id, condition id) of every active configuration, in manifest order."""
    return [(s["scenario_id"], c["id"]) for s in manifest["scenarios"] for c in manifest["conditions"]
            if c["id"] in ACTIVE_CONDITIONS]


def config_id(scenario_id: str, condition: str) -> str:
    return f"{scenario_id}.{condition}"


def game_id(scenario_id: str, condition: str, repetition: int) -> str:
    return f"{scenario_id}.{condition}.r{repetition}"


def design_digest(manifest: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical manifest without its schedule: the seed of the run order."""
    return mf.digest({k: v for k, v in manifest.items() if k not in ("schedule", "design_sha256")})


def schedule(design_sha256: str, configs: Sequence[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """The registered run order (algorithm in ``SCHEDULE_RULE``)."""
    plan: List[Dict[str, Any]] = []
    previous: Optional[Tuple[str, str]] = None
    for round_number, repetition in enumerate(NEW_REPETITIONS, start=1):
        order = sorted(configs, key=lambda c: hashlib.sha256(
            f"{design_sha256}:{round_number}:{config_id(*c)}".encode("utf-8")).hexdigest())
        if previous is not None and order[0] == previous and len(order) > 1:
            order[0], order[1] = order[1], order[0]
        for scenario_id, condition in order:
            plan.append({"position": len(plan) + 1, "round": round_number, "game_id": game_id(scenario_id, condition, repetition),
                         "scenario_id": scenario_id, "condition": condition, "repetition": repetition, "attempt": 1})
        previous = order[-1]
    return plan


SCHEDULE_RULE = (
    "design_sha256 is the SHA-256 of the canonical manifest without the schedule and without design_sha256",
    "round r (r = 1..8) plays repetition r + 2 of every active configuration exactly once",
    "within round r the configurations are ordered by the ascending hex SHA-256 of the UTF-8 string "
    "'<design_sha256>:<r>:<scenario_id>.<condition>'",
    "if the first configuration of a round is the last of the previous round, it is swapped with the second",
    "positions 1..192 number the games in play order; no game is added, removed or reordered after registration",
)
FAILURE_RULES = (
    "every registered game checks the pinned baseline-v1 policy source digest before touching the engine and "
    "refuses on a mismatch; the runner then stops the study",
    "a record is never overwritten; a game that was started and left no record stops the runner",
    "a game that writes a record with status FAIL or CAPPED is kept and reported; the runner continues, and stops "
    f"after {CONSECUTIVE_FAILURE_STOP} consecutive games that did not complete",
    "any other exit (input error, installation guardrail, timeout, crash) stops the runner",
    "no replacement attempt is scheduled by this registration; a replacement needs a registered amendment first, "
    "runs under a distinct attempt identity (game id suffix .a2) and is reported beside the attempt it replaces",
    "a missing or failed game reduces its configuration's n and is reported; nothing is imputed or replaced silently",
    "no valid observation is excluded, however extreme its score, refusal count or latency",
    "if execution-affecting code must change after registration, the study stops; collected attempts are kept, and "
    "a new study version with its own registration is created; incompatible results are never merged",
)
MISSING_DATA = (
    "a metric a historical record cannot provide is reported as missing for that record, never substituted",
    "historical factual refusal classes come from the retained examples; a seat whose examples do not cover all its "
    "refusals marks that game's classes incomplete",
    "attribution-2 labels need step evidence that only new records carry; historical refusals have none",
)
ARTIFACTS = {
    "public": "this manifest, the historical record digests, aggregate statistics and sanitized per-game metrics, "
              "sizing tables, documentation",
    "private (git-ignored local/)": "game records, per-step digests, factual refusal instances, logs, the engine "
                                    "installation and its ledger, scenario and map data",
}
STATISTICS = {
    "configuration": "n, mean, SD (n - 1), nearest-rank median and quartiles, min, max, and a 95% Student-t interval "
                     "for the mean (df n - 1; descriptive: n = 10 and outcomes need not be normal); zero variance "
                     "gives a zero-width interval",
    "condition and suite": "equal-weighted mean of configuration means (8 per condition, 24 for the suite); pooled "
                           "within-configuration SD = sqrt(mean of configuration variances); between-scenario SD "
                           "of configuration means; method-of-moments between-scenario variance component "
                           "max(0, var(means) - mean(variances) / n); 95% percentile interval of a stratified "
                           "bootstrap that resamples games with replacement within each configuration",
    "bootstrap": f"{BOOTSTRAP['resamples']} resamples; indices int(random() * n) from random.Random(seed), seed = "
                 f"int(first 12 hex digits of SHA-256('{BOOTSTRAP['seed']}:<metric>'), 16); never resamples steps; "
                 "interval limits are the nearest-rank 2.5th and 97.5th percentiles, ranks computed exactly",
    "temporal": "new games only, in play order. Standardized residual z = (x - configuration mean) / configuration "
                "SD over repetitions 3-10 (configurations with zero SD excluded and counted). Spearman correlation "
                "of play position with z; first half (repetitions 3-6) versus second half (7-10) as the "
                "equal-weighted mean over configurations of (mean second - mean first) / SD; historical repetitions "
                "1-2 versus new 3-10 likewise. 95% percentile intervals from "
                f"{TEMPORAL_BOOTSTRAP['resamples']} stratified bootstrap resamples (within configuration and, for "
                "halves, within half). A trend is called material when its interval excludes 0 and |standardized "
                f"difference| >= {MATERIAL['standardized_difference']} or |Spearman| >= {MATERIAL['spearman']}; "
                "otherwise the magnitude and interval are reported and no absence of drift is claimed",
    "n2 versus n10": "per configuration and equal-weighted: the estimate from repetitions 1-2 and from 1-10, their "
                     "difference, and 95% interval widths (Student-t per configuration; for the equal-weighted mean "
                     "t with df = sum(n - 1) on SE = sqrt(sum(s^2 / n)) / K)",
    "sizing": "independent candidate and baseline samples (no pairing by repetition: the engine has no seed "
              "control), n games per arm and configuration, analysed as the equal-weighted difference of "
              "configuration means over the metric's declared configurations, with the configurations as fixed "
              f"blocks. SE = sqrt(sum_k 2 s_k^2 / n) / K; two-sided alpha {ALPHA}; normal-approximation power; "
              f"minimum detectable effect at power {POWER}. Assumes the candidate's within-configuration SD equals "
              f"baseline-v1's. Conservative variant: each s_k replaced by its one-sided {CONSERVATIVE_LEVEL:.0%} "
              "upper confidence bound s_k * sqrt((n_k - 1) / chi2_{0.10, n_k - 1}). Check: deterministic Monte Carlo "
              f"({MONTE_CARLO['simulations']} simulations per cell) resampling each configuration's observed values, "
              "the effect added (absolute) or applied as a factor (relative), rejecting when |difference / "
              "estimated SE| exceeds t_{0.975, 2K(n - 1)}. Cost from the observed mean wall time per configuration",
    "default repetition count": f"the smallest n in {list(SIZING_REPETITIONS)} at which the conservative analytic "
                                f"power for a {abs(DEFAULT_RULE_EFFECT):.0%} relative reduction of "
                                f"{DEFAULT_RULE_METRIC} over the 24 active configurations reaches {POWER}; reported "
                                "with the n each other metric and effect of the grid needs",
}
ANALYSIS = (
    "No composite score is computed and no claim of tactical strength is made; baseline-v1 stays the frozen baseline.",
    "Scenario heterogeneity is kept: nothing is pooled across configurations into one SD, and aggregates weight "
    "configurations equally.",
    "Thousands of decision steps are not independent outcome samples; the game is the unit of every interval.",
    "Deterministic properties (a configuration whose ten values are all equal) are reported as such and not given "
    "an interval of uncertainty.",
)


def force_values(v1_results: Mapping[str, Any]) -> Dict[str, int]:
    """Each scenario's combined start force value (red_remain_max + blue_remain_max) from the frozen results.

    The value must be the same in every game of the scenario; otherwise the input is rejected.
    """
    values: Dict[str, set] = {}
    for game in v1_results["suite"]["games"]:
        scores = game["final_scores"]
        values.setdefault(game["scenario_id"], set()).add(scores["red_remain_max"] + scores["blue_remain_max"])
    if any(len(v) != 1 for v in values.values()):
        raise ValueError("a scenario's start force value differs between its games")
    return {scenario: next(iter(v)) for scenario, v in sorted(values.items())}


def build(v1_manifest: Mapping[str, Any], v1_results: Mapping[str, Any], v1_results_sha256: str,
          historical_records: Mapping[str, Any], policy_files: Sequence[str], policy_sha256: str,
          policy_sources: Sequence[str]) -> Dict[str, Any]:
    """The registered manifest. Every input is a committed file; generation is deterministic."""
    if mf.digest(v1_manifest) != BASELINE_V1_MANIFEST_SHA256:
        raise ValueError("the baseline-v1 manifest is not the frozen one")
    if v1_results_sha256 != BASELINE_V1_RESULTS_SHA256:
        raise ValueError("the baseline-v1 results are not the frozen ones")
    if policy_sha256 != BASELINE_V1_SOURCE_SHA256:
        raise ValueError("the policy source is not baseline-v1")
    if v1_manifest["golden_trace_chain"] != BASELINE_V1_GOLDEN_TRACE_CHAIN:
        raise ValueError("the golden decision chain is not baseline-v1's")
    manifest: Dict[str, Any] = {key: copy.deepcopy(v1_manifest[key]) for key in (
        "engine", "scenarios", "players", "caps", "randomness", "replay_check_every", "policy_under_test",
        "control_policy")}
    manifest.update({
        "schema": SCHEMA,
        "study_id": STUDY_NAME,
        "evaluation_id": STUDY_NAME,
        "purpose": "repeated-run variance of the unchanged baseline-v1: within-configuration variability, "
                   "scenario heterogeneity, run-order effects and repetition counts for future experiments",
        "baseline": {"identity": BASELINE_IDENTITY, "code_identity": v1_manifest["policy_under_test"],
                     "policy_source_sha256": BASELINE_V1_SOURCE_SHA256,
                     "golden_trace_chain": BASELINE_V1_GOLDEN_TRACE_CHAIN,
                     "evaluation_manifest_sha256": BASELINE_V1_MANIFEST_SHA256,
                     "evaluation_results_sha256": BASELINE_V1_RESULTS_SHA256,
                     "executed_commit": BASELINE_V1_EXECUTED_COMMIT, "promotion_commit": BASELINE_V1_PROMOTION_COMMIT},
        "policy_source": {"sha256": policy_sha256, "files": list(policy_files), "sources": list(policy_sources),
                          "rule": "sorted relative paths, CRLF normalized to LF; see evaluation/identity.py"},
        "runtime": dict(RUNTIME),
        "scenario_manifest_sha256": BASELINE_V1_MANIFEST_SHA256,
        "conditions": [copy.deepcopy(c) for c in v1_manifest["conditions"] if c["id"] in ACTIVE_CONDITIONS],
        "control_condition": {"id": CONTROL_CONDITION, "treatment": "not replayed; its historical repetitions 1-2 are "
                                                                     "kept as the deterministic control"},
        "repetition_target": REPETITION_TARGET,
        "historical_repetitions": list(HISTORICAL_REPETITIONS),
        "new_repetitions": list(NEW_REPETITIONS),
        "new_games": len(NEW_REPETITIONS) * len(configurations({"scenarios": v1_manifest["scenarios"],
                                                                 "conditions": v1_manifest["conditions"]})),
        "historical_records": copy.deepcopy(dict(historical_records)),
        "schedule_rule": list(SCHEDULE_RULE),
        "failure_rules": list(FAILURE_RULES),
        "missing_data": list(MISSING_DATA),
        "artifacts": dict(ARTIFACTS),
        "metrics": dict(METRICS),
        "major_metrics": list(MAJOR),
        "temporal_metrics": list(TEMPORAL),
        "registered_seat_metrics": list(LATER_SEAT_FIELDS) + list(REFUSAL_FIELDS),
        "refusal_taxonomy": {"fact": refusals.FACT_SCHEMA, "attribution": refusals.ATTRIBUTION_VERSION,
                             "document": "docs/REFUSAL_TAXONOMY.md"},
        "statistics": dict(STATISTICS),
        "level": LEVEL,
        "bootstrap": dict(BOOTSTRAP), "temporal_bootstrap": dict(TEMPORAL_BOOTSTRAP), "monte_carlo": dict(MONTE_CARLO),
        "sizing_repetitions": list(SIZING_REPETITIONS), "alpha": ALPHA, "power": POWER,
        "conservative_level": CONSERVATIVE_LEVEL, "material_trend": dict(MATERIAL),
        "effect_grid": copy.deepcopy(EFFECT_GRID), "effect_rationale": list(EFFECT_RATIONALE),
        "force_value_by_scenario": force_values(v1_results),
        "analysis": list(ANALYSIS),
    })
    manifest["design_sha256"] = design_digest(manifest)
    manifest["schedule"] = schedule(manifest["design_sha256"], configurations(manifest))
    return manifest


def scheduled_games(manifest: Mapping[str, Any]) -> List[mf.GameSpec]:
    """The registered new games in play order."""
    scenarios = {s["scenario_id"]: s for s in manifest["scenarios"]}
    conditions = {c["id"]: c for c in manifest["conditions"]}
    specs = []
    for entry in manifest["schedule"]:
        condition, scenario = conditions[entry["condition"]], scenarios[entry["scenario_id"]]
        specs.append(mf.GameSpec(game_id=entry["game_id"], scenario_id=entry["scenario_id"], map_id=scenario["map_id"],
                                 condition=entry["condition"], red=condition["red"], blue=condition["blue"],
                                 repetition=entry["repetition"], max_time=int(scenario["max_time"])))
    return specs


def is_study(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


# ----------------------------------------------------------------------------------------------
# Per-game metrics


def _per_1000(count: int, actions: int) -> Optional[float]:
    return 1000.0 * count / actions if actions else None


def historical_facts(seats: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """Factual classes from retained examples; complete only if every refusal has an example."""
    items, complete = [], True
    for seat in seats:
        examples = seat.get("feedback_error_examples")
        for code, count in seat["feedback_errors_by_code"].items():
            kept = (examples or {}).get(code, [])
            complete = complete and examples is not None and len(kept) == count
            items.extend({"action_type": e["action"].get("type"), "code": int(code),
                          "message_class": refusals.normalize_message(e.get("error_message"))} for e in kept)
    return refusals.fact_counts(items), complete


def game_metrics(record: Mapping[str, Any], policy: str) -> Dict[str, Any]:
    """The registered metrics of one game, plus its factual refusal classes."""
    seats = [s for s in record.get("seats", []) if s["policy"] == policy]
    scores = record.get("final_scores") or {}
    red, blue = scores.get("red_total"), scores.get("blue_total")
    margin = None if red is None or blue is None else (blue - red if record["condition"] == "C3" else red - blue)
    actions: Dict[str, int] = {}
    codes: Dict[str, int] = {}
    for seat in seats:
        for kind, count in seat["actions_by_type"].items():
            actions[kind] = actions.get(kind, 0) + count
        for code, count in seat["feedback_errors_by_code"].items():
            codes[str(code)] = codes.get(str(code), 0) + count
    unit_actions = sum(v for k, v in actions.items() if k != "333")
    decisions = sum(s["decisions"] for s in seats)
    no_ops = sum(sum(s["no_op_reasons"].values()) for s in seats)
    latencies = [v for s in seats for v in s["latency_us"]]
    timings = record.get("timings_seconds") or {}
    refused = sum(codes.values())
    if all("refusal_facts" in s for s in seats):
        facts, source = refusals.merge_fact_counts([s["refusal_facts"] for s in seats]), "record"
        complete = True
    else:
        facts, complete = historical_facts(seats)
        source = "examples"
    attributions: Optional[Dict[str, int]] = None
    if all("refusal_attributions" in s for s in seats):
        attributions = {}
        for seat in seats:
            for label, count in seat["refusal_attributions"].items():
                attributions[label] = attributions.get(label, 0) + count
    ms = lambda us: None if us is None else us / 1000.0  # noqa: E731
    values = {
        "red_total": red, "blue_total": blue, "margin": margin,
        "unit_actions": unit_actions, "refusals": refused, "refusals_per_1000": _per_1000(refused, unit_actions),
        "code_1804": codes.get("1804", 0), "code_516": codes.get("516", 0), "code_203": codes.get("203", 0),
        "code_1804_per_1000": _per_1000(codes.get("1804", 0), unit_actions),
        "code_516_per_1000": _per_1000(codes.get("516", 0), unit_actions),
        "code_203_per_1000": _per_1000(codes.get("203", 0), unit_actions),
        "gate_rejections": sum(sum(s["gate_rejections"].values()) for s in seats),
        "moves": actions.get("1", 0), "shots": actions.get("2", 0), "occupations": actions.get("5", 0),
        "active_step_rate": sum(s["steps_with_action"] for s in seats) / decisions if decisions else None,
        "no_op_rate": no_ops / (no_ops + unit_actions) if no_ops + unit_actions else None,
        "suppressions": sum(s.get("suppressions", 0) for s in seats),
        "units_acted": sum(s["units_acted"] for s in seats),
        "latency_p50_ms": ms(nearest_rank(latencies, 50)), "latency_p95_ms": ms(nearest_rank(latencies, 95)),
        "latency_p99_ms": ms(nearest_rank(latencies, 99)), "latency_max_ms": ms(max(latencies) if latencies else None),
        "decisions_over_100ms": sum(1 for v in latencies if v > 100_000),
        "decisions_over_400ms": sum(1 for v in latencies if v > 400_000),
        "decision_seconds": sum(latencies) / 1e6,
        "engine_seconds": timings.get("engine_step"), "harness_seconds": timings.get("harness"),
        "wall_seconds": timings.get("wall"), "steps": record.get("steps"),
    }
    first_shots = [int(s["first_step_by_type"]["2"]) for s in record.get("seats", []) if "2" in s["first_step_by_type"]]
    return {"values": values, "facts": facts, "facts_source": source, "facts_complete": complete,
            "attributions": attributions,
            "margin_fields_consistent": None if margin is None else (
                scores.get("red_win") == red - blue and scores.get("blue_win") == blue - red),
            "first_shot_decision": min(first_shots) if first_shots else None,
            "slow_decision_indices": sorted({i for s in seats for i, v in enumerate(s["latency_us"]) if v > 100_000})}


# ----------------------------------------------------------------------------------------------
# Aggregation


def metric_seed(base: int, name: str) -> int:
    return int(hashlib.sha256(f"{base}:{name}".encode("utf-8")).hexdigest()[:12], 16)


def level_summary(groups: Sequence[Sequence[float]], boot: Sequence[Sequence[float]]) -> Dict[str, Any]:
    """Equal-weighted aggregate of configuration means with its variance structure and bootstrap interval."""
    groups = [list(g) for g in groups]
    usable = [(g, b) for g, b in zip(groups, boot) if g]
    means = [sum(g) / len(g) for g, _ in usable]
    variances = [stats.variance(g) for g, _ in usable]
    variances = [v for v in variances if v is not None]
    within = sum(variances) / len(variances) if variances else None
    between_raw = stats.variance(means)
    n_harmonic = len(usable) / sum(1.0 / len(g) for g, _ in usable) if usable else None
    component = None if between_raw is None or within is None else max(0.0, between_raw - within / n_harmonic)
    interval = None
    if usable and all(b for _, b in usable):
        combined = [sum(b[i] for _, b in usable) / len(usable) for i in range(len(usable[0][1]))]
        interval = stats.percentile_interval(combined, LEVEL)
    return {
        "configurations": len(usable), "mean": sum(means) / len(means) if means else None,
        "pooled_within_sd": None if within is None else math.sqrt(within),
        "between_scenario_sd_of_means": None if between_raw is None else math.sqrt(between_raw),
        "between_scenario_variance_component": component,
        "within_variance": within,
        "between_share": None if component is None or within is None or component + within == 0
        else component / (component + within),
        "constant_configurations": sum(1 for v in variances if v == 0),
        "ci_low": None if interval is None else interval[0], "ci_high": None if interval is None else interval[1],
    }


def summarize(values: Mapping[str, Mapping[str, Sequence[float]]], conditions: Sequence[str]) -> Dict[str, Any]:
    """``values[metric][config_id]`` -> per-configuration, per-condition and suite summaries."""
    result: Dict[str, Any] = {}
    for metric in sorted(values):
        per_config = values[metric]
        ids = sorted(per_config)
        groups = [[v for v in per_config[c] if v is not None] for c in ids]
        boot = stats.bootstrap_means(groups, BOOTSTRAP["resamples"], metric_seed(BOOTSTRAP["seed"], metric))
        entry = {"configurations": {c: dict(stats.describe(g), missing=len(per_config[c]) - len(g),
                                            constant=len(g) >= 2 and max(g) == min(g))
                                    for c, g in zip(ids, groups)}}
        entry["conditions"] = {cond: level_summary([g for c, g in zip(ids, groups) if c.endswith("." + cond)],
                                                   [b for c, b in zip(ids, boot) if c.endswith("." + cond)])
                               for cond in conditions}
        entry["suite"] = level_summary(groups, boot)
        result[metric] = entry
    return result


def _bootstrap_statistic(groups: Sequence[Sequence[Tuple[float, float]]], statistic, resamples: int,
                         seed: int) -> List[float]:
    rng = random.Random(seed)
    samples = []
    for _ in range(resamples):
        drawn = [[g[stats.draw(rng, len(g))] for _ in g] for g in groups]
        value = statistic(drawn)
        if value is not None:
            samples.append(value)
    return samples


def temporal(new: Mapping[str, Sequence[Tuple[int, int, Optional[float]]]],
             historical: Mapping[str, Sequence[Optional[float]]], metric: str) -> Dict[str, Any]:
    """Run-order diagnostics of one metric.

    ``new[config] = [(position, repetition, value)]`` for repetitions 3-10; ``historical[config]`` holds the
    values of repetitions 1-2.
    """
    standardized: List[Tuple[float, float]] = []
    halves: List[Tuple[List[float], List[float], float]] = []
    versus: List[Tuple[List[float], List[float]]] = []
    by_config: List[List[Tuple[float, float]]] = []
    excluded = 0
    first = set(NEW_REPETITIONS[:len(NEW_REPETITIONS) // 2])
    for config in sorted(new):
        rows = [(p, r, v) for p, r, v in new[config] if v is not None]
        values = [v for _, _, v in rows]
        s = stats.sd(values)
        if s is None or s == 0:
            excluded += 1
            continue
        m = sum(values) / len(values)
        pairs = [(float(p), (v - m) / s) for p, _, v in rows]
        standardized.extend(pairs)
        by_config.append(pairs)
        halves.append(([v for _, r, v in rows if r in first], [v for _, r, v in rows if r not in first], s))
        old = [v for v in historical.get(config, ()) if v is not None]
        if old:
            versus.append((old, values))

    def rho(groups):
        pairs = [pair for g in groups for pair in g]
        return stats.spearman([p for p, _ in pairs], [z for _, z in pairs]) if len(pairs) > 2 else None

    def half_difference(parts):
        diffs = [(sum(b) / len(b) - sum(a) / len(a)) / s for a, b, s in parts if a and b]
        return sum(diffs) / len(diffs) if diffs else None

    def old_new_difference(parts):
        diffs = []
        for old, current in parts:
            s = stats.sd(current)
            if s:
                diffs.append((sum(old) / len(old) - sum(current) / len(current)) / s)
        return sum(diffs) / len(diffs) if diffs else None

    seed = metric_seed(TEMPORAL_BOOTSTRAP["seed"], metric)
    resamples = TEMPORAL_BOOTSTRAP["resamples"]
    rho_samples = _bootstrap_statistic(by_config, rho, resamples, seed)
    half_groups = [[(v, 0.0) for v in a] for a, _, _ in halves] + [[(v, 1.0) for v in b] for _, b, _ in halves]

    def half_from_draw(drawn):
        k = len(halves)
        return half_difference([([v for v, _ in drawn[i]], [v for v, _ in drawn[k + i]], halves[i][2])
                                for i in range(k)])

    half_samples = _bootstrap_statistic(half_groups, half_from_draw, resamples, seed + 1) if halves else []
    versus_groups = [[(v, 0.0) for v in old] for old, _ in versus] + [[(v, 1.0) for v in cur] for _, cur in versus]

    def versus_from_draw(drawn):
        k = len(versus)
        return old_new_difference([([v for v, _ in drawn[i]], [v for v, _ in drawn[k + i]]) for i in range(k)])

    versus_samples = _bootstrap_statistic(versus_groups, versus_from_draw, resamples, seed + 2) if versus else []

    def packed(point, samples, threshold):
        if point is None:
            return {"estimate": None, "ci_low": None, "ci_high": None, "material": False}
        low, high = stats.percentile_interval(samples, LEVEL) if samples else (None, None)
        excludes_zero = low is not None and (low > 0 or high < 0)
        return {"estimate": point, "ci_low": low, "ci_high": high,
                "material": bool(excludes_zero and abs(point) >= threshold)}

    return {"games": len(standardized), "configurations_excluded_zero_sd": excluded,
            "spearman_position": packed(rho(by_config), rho_samples, MATERIAL["spearman"]),
            "second_minus_first_half_sd": packed(half_difference(halves), half_samples,
                                                 MATERIAL["standardized_difference"]),
            "historical_minus_new_sd": packed(old_new_difference(versus), versus_samples,
                                              MATERIAL["standardized_difference"])}


def n2_versus_n10(per_config: Mapping[str, Sequence[Tuple[int, Optional[float]]]]) -> Dict[str, Any]:
    """``per_config[config] = [(repetition, value)]``: estimates from repetitions 1-2 against 1-10."""
    rows = {}
    two_means, all_means, two_var, all_var, outside = [], [], [], [], 0
    df_two = df_all = 0
    for config in sorted(per_config):
        two = [v for r, v in per_config[config] if r in HISTORICAL_REPETITIONS and v is not None]
        every = [v for _, v in per_config[config] if v is not None]
        i2, i10 = stats.t_interval(two, LEVEL), stats.t_interval(every, LEVEL)
        m2, m10 = stats.mean(two), stats.mean(every)
        rows[config] = {"n2_mean": m2, "n10_mean": m10, "change": None if m2 is None or m10 is None else m2 - m10,
                        "n2_ci_width": None if i2 is None else i2[1] - i2[0],
                        "n10_ci_width": None if i10 is None else i10[1] - i10[0],
                        "n2_outside_n10_interval": None if i10 is None or m2 is None else not i10[0] <= m2 <= i10[1]}
        if rows[config]["n2_outside_n10_interval"]:
            outside += 1
        if len(two) >= 2 and len(every) >= 2:
            two_means.append(m2)
            all_means.append(m10)
            two_var.append(stats.variance(two) / len(two))
            all_var.append(stats.variance(every) / len(every))
            df_two += len(two) - 1
            df_all += len(every) - 1
    k = len(two_means)

    def width(var_terms, df):
        if not k or df == 0:
            return None
        return 2 * stats.t_quantile(0.5 + LEVEL / 2, df) * math.sqrt(sum(var_terms)) / k

    equal = {"configurations": k, "n2_mean": sum(two_means) / k if k else None,
             "n10_mean": sum(all_means) / k if k else None,
             "n2_ci_width": width(two_var, df_two), "n10_ci_width": width(all_var, df_all),
             "n2_estimates_outside_n10_interval": outside}
    if equal["n2_mean"] is not None:
        equal["change"] = equal["n2_mean"] - equal["n10_mean"]
    return {"configurations": rows, "equal_weighted": equal}


def sizing(per_config: Mapping[str, Sequence[float]], effects: Mapping[str, Any],
           force_by_config: Optional[Mapping[str, float]], metric: str) -> Dict[str, Any]:
    """Planning sensitivity of a future two-arm experiment for one metric over its configurations."""
    configs = sorted(c for c in per_config if [v for v in per_config[c] if v is not None])
    groups = {c: [v for v in per_config[c] if v is not None] for c in configs}
    k = len(configs)
    sds = {c: stats.sd(g) or 0.0 for c, g in groups.items()}
    upper = {}
    for c, g in groups.items():
        n0 = len(g)
        upper[c] = sds[c] * math.sqrt((n0 - 1) / stats.chi2_quantile(1 - CONSERVATIVE_LEVEL, n0 - 1)) if n0 >= 2 else 0.0
    means = {c: sum(g) / len(g) for c, g in groups.items()}
    cells = []
    for kind, grid in (("absolute_points", effects.get("absolute_points", [])),
                       ("relative_to_force_value", effects.get("relative_to_force_value", [])),
                       ("relative_change", effects.get("relative_change", []))):
        for value in grid:
            if kind == "absolute_points":
                shift = {c: float(value) for c in configs}
            elif kind == "relative_to_force_value":
                shift = {c: value * force_by_config[c] for c in configs}
            else:
                shift = {c: value * means[c] for c in configs}
            cells.append((kind, value, shift))
    table = []
    for n in SIZING_REPETITIONS:
        se = math.sqrt(sum(2 * sds[c] ** 2 / n for c in configs)) / k
        se_up = math.sqrt(sum(2 * upper[c] ** 2 / n for c in configs)) / k
        row = {"repetitions": n, "se": se, "se_conservative": se_up,
               "mde": stats.minimum_detectable(se, ALPHA, POWER),
               "mde_conservative": stats.minimum_detectable(se_up, ALPHA, POWER), "effects": []}
        for kind, value, shift in cells:
            delta = sum(shift.values()) / k
            row["effects"].append({"kind": kind, "value": value, "macro_effect": delta,
                                   "power": stats.power_two_sided(delta, se, ALPHA),
                                   "power_conservative": stats.power_two_sided(delta, se_up, ALPHA),
                                   "power_monte_carlo": monte_carlo_power(groups, kind, shift, value, n, metric)})
        table.append(row)
    return {"configurations": k, "configuration_ids": configs, "table": table}


def cost(wall_by_config: Mapping[str, float]) -> List[Dict[str, Any]]:
    """Games and serial engine hours of a future experiment over every active configuration, per arm."""
    hours = sum(wall_by_config.values()) / 3600.0
    return [{"repetitions": n, "games_per_arm": n * len(wall_by_config), "hours_per_arm": n * hours,
             "games_both_arms": 2 * n * len(wall_by_config), "hours_both_arms": 2 * n * hours}
            for n in SIZING_REPETITIONS]


def monte_carlo_power(groups: Mapping[str, Sequence[float]], kind: str, shift: Mapping[str, float], value: float,
                      n: int, metric: str) -> float:
    """Rejection rate over simulated experiments drawn from each configuration's observed values."""
    configs = sorted(groups)
    k = len(configs)
    seed = metric_seed(MONTE_CARLO["seed"], f"{metric}:{kind}:{value}:{n}")
    rng = random.Random(seed)
    critical = stats.t_quantile(1 - ALPHA / 2, 2 * k * (n - 1))
    rejected = 0
    for _ in range(MONTE_CARLO["simulations"]):
        difference, variance_sum = 0.0, 0.0
        for c in configs:
            g = groups[c]
            a = [g[stats.draw(rng, len(g))] for _ in range(n)]
            b = [g[stats.draw(rng, len(g))] for _ in range(n)]
            b = [x + shift[c] for x in b] if kind != "relative_change" else [x * (1 + value) for x in b]
            difference += sum(b) / n - sum(a) / n
            variance_sum += (stats.variance(a) + stats.variance(b)) / n
        difference /= k
        se = math.sqrt(variance_sum) / k
        if (se == 0 and difference != 0) or (se > 0 and abs(difference / se) > critical):
            rejected += 1
    return rejected / MONTE_CARLO["simulations"]


def default_repetitions(sizing_result: Mapping[str, Any]) -> Optional[int]:
    """The registered default rule applied to the sizing table of ``DEFAULT_RULE_METRIC``."""
    for row in sizing_result["table"]:
        for effect in row["effects"]:
            if effect["kind"] == "relative_change" and effect["value"] == DEFAULT_RULE_EFFECT \
                    and effect["power_conservative"] >= POWER:
                return row["repetitions"]
    return None


def determinism(records: Sequence[Mapping[str, Any]], policy: str) -> Dict[str, Any]:
    """Repetition agreement within one configuration: distinct engine trajectories, divergence after the
    first shot, and whether the policy's traces agree wherever the engine states agree."""
    first = records[0]
    comparisons = [compare(first, other) for other in records[1:]]
    shots = [game_metrics(r, policy)["first_shot_decision"] for r in records]
    divergences = [c["state_first_divergence"] for c in comparisons]
    return {"repetitions": len(records), "distinct_state_chains": len({r.get("state_chain") for r in records}),
            "traces_equal_while_states_equal": all(seat["traces_equal_while_states_equal"]
                                                   for c in comparisons for seat in c["seats"]
                                                   if seat["policy"] == policy),
            "first_shot_decision": sorted({s for s in shots if s is not None}),
            "state_first_divergence_vs_repetition_1": divergences}
