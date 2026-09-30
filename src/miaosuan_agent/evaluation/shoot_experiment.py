"""The registered two-group experiment of the shoot-target-reservation candidate.

Group B plays ``baseline-v1`` on ``baseline-v1-runtime-r1``; group C plays the candidate
``baseline-v2-candidate-shoot-target-reservation`` on the same runtime. Both groups are new games over the
eight frozen scenarios in the three conditions that contain the policy (24 configurations), 15 repetitions
per configuration and group, 720 games, interleaved in one deterministic schedule.

This module holds the registration (``build``), the run order (``schedule``), the per-game metrics, every
registered analysis and the mechanical evaluation of the promotion criteria. It reads no files; the scripts
do the I/O. Policies are identified by digest; nothing here is reachable from a policy.
"""

from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import manifest as mf
from . import refusals, stats
from . import variance_study as vs
from .game import SCHEMA as GAME_SCHEMA
from .metrics import nearest_rank

SCHEMA = "miaosuan-ab-experiment-manifest/1"
CANDIDATE_ID = "baseline-v2-candidate-shoot-target-reservation"
EXPERIMENT_NAME = CANDIDATE_ID
EXPERIMENT_ID = f"{CANDIDATE_ID}-ab-1"
RUNTIME_R1_ID = "baseline-v1-runtime-r1"
RUNTIME_R1_CODE_ID = "baseline-v1-routing-bounded-candidate"
RUNTIME_R1_SOURCE_SHA256 = "f9e50a538f1f530e9e485f75ce3d457435cfb9bcc2eb039ecdfa9374d54398ad"
CANDIDATE_FILE = "experiments/shoot_reservation.py"
TRACE_SCHEMA = "miaosuan-decision-trace/1+occupy-reservation+shoot-reservation"
#: Chained digest of the candidate's traces over its golden sequence (tests/test_shoot_reservation.py).
CANDIDATE_GOLDEN_TRACE_CHAIN = "0d16c814c03909ed89303a776b276b4cc441cd047450a063329009458654910f"
GROUPS = ("B", "C")
ACTIVE_CONDITIONS = vs.ACTIVE_CONDITIONS
REPETITIONS = 15
CONSECUTIVE_FAILURE_STOP = 3
LEVEL = 0.95
BOOTSTRAP = {"resamples": 10000, "seed": 20261001}
PRIMARY_METRIC = "code_516_per_1000"
MARGIN_METRIC = "margin"
NON_INFERIORITY_MARGIN = 10.0
MINIMUM_RELATIVE_REDUCTION = 0.25
EFFECT_GRID = (-0.25, -0.5, -1.0)
#: Factual refusal classes (action type, code, message class) of baseline-v1 over the 240 active games of the
#: variance study (results.json of baseline-v1-variance-study-1).
KNOWN_CLASSES = ((1, 404, "CantMoveKeptPeople"), (2, 203, "CantControlDiedOperator"), (2, 516, "CantShootToDiedBop"),
                 (5, 203, "CantControlDiedOperator"))
DISPLACED_EFFECTS = ("alternate-target", "fallback-occupy", "fallback-move", "fallback-none")
SEAT_FIELDS = ("duplicate_shoot_target_steps", "duplicate_shoot_target_commands", "shoot_targets_engaged",
               "steps_with_shot", "shoot_reservation_effects", "shoot_excluded_options", "steps_with_shoot_exclusion")

HYPOTHESIS = {
    "primary": "Adding per-seat, per-step shoot-target reservation reduces the registered code-516 refusal rate "
               "(code-516 refusals per 1,000 emitted unit actions) relative to baseline-v1 on baseline-v1-runtime-r1.",
    "direction": "reduction (candidate minus baseline < 0)",
    "not_claimed": "No claim that unique-target fire is tactically superior: removing follow-up fire can lose damage "
                   "when the first shot does not destroy the target. Outcomes are guarded by the non-inferiority "
                   "criterion and otherwise reported descriptively.",
}
SINGLE_VARIABLE = (
    "Within one seat's decision step at most one emitted shoot action targets the same enemy object. Units are "
    "processed in baseline-v1 order; when a unit's selected shoot action passes the final safety gate its "
    "target_obj_id is reserved for the rest of that seat's step; a later unit's shoot options on a reserved target "
    "are excluded before selection, and the unit selects exactly as baseline-v1 among what remains (the next shoot "
    "option in baseline order, else occupation, movement or nothing). A gate-rejected shot reserves nothing. "
    "Reservations never cross seats or steps. Everything else is baseline-v1 on baseline-v1-runtime-r1: context, "
    "candidates, priorities, rankings and tie-breaks, the occupation reservation, the target-bounded router, "
    "deployment and the safety gate, reused unchanged by import."
)
PRIMARY_DEFINITION = {
    "metric": PRIMARY_METRIC,
    "numerator": "engine refusals with code 516 of the seats of the group's policy in the game (both seats in C1)",
    "denominator": "emitted unit actions of the same seats: every action type except deployment completion (333)",
    "scaling": "per 1,000 emitted unit actions",
    "undefined": "a game with no emitted unit action has no rate and is left out of its configuration's mean",
    "games": "every recorded game of the group in the 24 active configurations",
    "weighting": "configuration mean over games, then the equal-weighted mean over the 24 configurations",
    "source": "the metric code_516_per_1000 of variance_study.game_metrics, the definition the variance study "
              "planned with; identical code computes it here",
}
PRIMARY_ANALYSIS = {
    "estimand": "delta = (1/24) * sum over configurations of (mean_C - mean_B); relative change = delta / "
                "((1/24) * sum of mean_B)",
    "interval": "95% percentile interval of a stratified bootstrap: games resampled with replacement within each "
                "configuration and group independently; the groups are independent samples, repetitions are not "
                "paired",
    "bootstrap": f"{BOOTSTRAP['resamples']} resamples; one random.Random with seed int(first 12 hex digits of "
                 f"SHA-256('{BOOTSTRAP['seed']}:<metric>'), 16); configurations in sorted order, within each the "
                 "baseline group's games are drawn before the candidate's; indices int(random() * n); limits are "
                 "the exact nearest-rank 2.5th and 97.5th percentiles",
    "sensitivity": "the analytic interval of the planning method: SE = sqrt(sum_k (s_Ck^2 / n_Ck + s_Bk^2 / n_Bk)) / K "
                   "with Student t at df = sum_k (n_Ck + n_Bk - 2); reported, not decisive",
    "criterion": f"P6 passes when the upper limit of the bootstrap interval of delta is below 0 and the point estimate "
                 f"of the relative reduction is at least {MINIMUM_RELATIVE_REDUCTION:.0%} (the smallest effect of the "
                 "registered planning grid)",
}
NON_INFERIORITY = {
    "metric": MARGIN_METRIC,
    "definition": "score margin from the active side: red_total - blue_total in C2 (policy red), blue_total - "
                  "red_total in C3 (policy blue); the C1 mirror margin measures side asymmetry and is not used",
    "configurations": "the 16 configurations of C2 and C3",
    "contrast": "delta_margin = (1/16) * sum over configurations of (mean_C - mean_B)",
    "interval": "the same stratified bootstrap (seed metric name 'margin'), 95% percentile interval",
    "margin": f"-{NON_INFERIORITY_MARGIN:g} engine score points: the smallest absolute margin effect of the variance "
              "study's planning grid, fixed from game semantics before any baseline-v1 game of that study",
    "rule": f"P7 passes when the lower limit of the interval of delta_margin is above -{NON_INFERIORITY_MARGIN:g}",
}
PROMOTION = {
    "P1": "implementation integrity: the candidate's sources are baseline-v1-runtime-r1's byte-identical plus exactly "
          "experiments/shoot_reservation.py, and the pinned counterfactual replay has zero unexplained states and zero "
          "class-E units",
    "P2": "deterministic mechanism: group C emitted no shoot action at a target another shoot action of the same seat "
          "had in the same step (harness count from emitted actions), and every in-game replay check of group C "
          "matched",
    "P3": "execution reliability: every registered game has a record, group C has no more games that did not "
          "complete (FAIL or CAPPED) than group B, and group C has no contract error",
    "P4": "project legality: project safety-gate rejections of group C = 0",
    "P5": "solved-feature regression: code-1804 refusals of group C = 0 and duplicate same-objective occupation "
          "commands of group C = 0",
    "P6": "primary effect: " + PRIMARY_ANALYSIS["criterion"],
    "P7": "tactical non-inferiority: " + NON_INFERIORITY["rule"],
    "P8": "no unexplained new refusal mechanism: every factual refusal class of group C is a known baseline-v1 class "
          "(KNOWN_CLASSES) or also occurs in group B of this experiment",
    "P9": "runtime comparability: every group-B record carries the runtime-r1 policy digest and every group-C record "
          "the registered candidate digest, both under this manifest and a clean harness at one commit",
    "P10": "privacy and reproducibility: the results regenerate byte-identically from the records, the public "
           "artifacts hold aggregates only, and the registration was on the public remote before the first game",
}
PROMOTION_RULES = (
    "The candidate is promoted to baseline-v2 only if P1-P10 all pass; otherwise it is retained as a partial or "
    "negative candidate under its own identity, and baseline-v1 on baseline-v1-runtime-r1 stays the baseline.",
    "Neither a higher score nor zero code-516 refusals is required or sufficient.",
    "A promoted baseline-v2 keeps running on baseline-v1-runtime-r1; the runtime is not renamed.",
)
SCHEDULE_RULE = (
    "design_sha256 is the SHA-256 of the canonical manifest without the schedule and without design_sha256",
    "round r (r = 1..15) plays repetition r of every configuration in both groups exactly once (48 games)",
    "within round r the games alternate between the groups: B first in odd rounds, C first in even rounds",
    "each group's 24 configurations are ordered by the ascending hex SHA-256 of the UTF-8 string "
    "'<design_sha256>:<r>:<group>:<scenario_id>.<condition>'",
    "if the first game of a round repeats the configuration and group of the previous round's last game, the round's "
    "first two games of that group exchange places",
    "positions 1..720 number the games in play order; the two groups' games of one configuration may follow each other, "
    "one configuration and group never plays twice in a row, and no game is added, removed or reordered after registration",
)
FAILURE_RULES = (
    "every registered game recomputes its group's policy source digest before touching the engine and refuses on a "
    "mismatch; the runner then stops",
    "a record is never overwritten; a game that was started and left no record stops the runner",
    "a game that writes a record with status FAIL or CAPPED is kept and reported; the runner continues, and stops "
    f"after {CONSECUTIVE_FAILURE_STOP} consecutive games that did not complete (the only safety stop)",
    "any other exit (input error, installation guardrail, timeout, crash) stops the runner",
    "no stop, addition or repetition is ever decided from scores, refusal counts or any other outcome",
    "no replacement is scheduled by this registration; a replacement needs a registered amendment first, runs under a "
    "distinct attempt identity (game id suffix .a2) and is reported beside the attempt it replaces, both kept",
    "a missing or failed game reduces its cell's n and is reported; nothing is imputed or replaced silently",
    "no valid observation is excluded, however extreme its score, refusal count or latency",
    "if execution-affecting code must change after registration, the experiment stops; collected attempts are kept, "
    "and a new experiment version with its own registration is created; results are never merged across versions",
)
ARTIFACTS = {
    "public": "this manifest, the counterfactual replay and mutation aggregates, results.json with aggregates and "
              "sanitized per-game metrics, documentation",
    "private (git-ignored local/)": "game records, per-step digests, factual refusal instances, traces, logs, the "
                                    "engine installation and its ledger, scenario and map data",
}
NOT_CRITERIA = (
    "engine scores other than the registered C2/C3 non-inferiority contrast are descriptive",
    "code 203 is not a target of the candidate: a change in its count arises from different engine trajectories and "
    "is reported, not credited",
    "latency is reported, not judged; the late collection pauses of the shared engine process are a known runtime risk",
)


# ----------------------------------------------------------------------------------------------
# Registration


def configurations(manifest: Mapping[str, Any]) -> List[Tuple[str, str]]:
    return [(s["scenario_id"], c) for s in manifest["scenarios"] for c in ACTIVE_CONDITIONS]


def config_id(scenario_id: str, condition: str) -> str:
    return f"{scenario_id}.{condition}"


def game_id(scenario_id: str, condition: str, group: str, repetition: int) -> str:
    return f"{scenario_id}.{condition}.{group}.r{repetition}"


def design_digest(manifest: Mapping[str, Any]) -> str:
    return mf.digest({k: v for k, v in manifest.items() if k not in ("schedule", "design_sha256")})


def _order(design_sha256: str, round_number: int, group: str, configs: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return sorted(configs, key=lambda c: hashlib.sha256(
        f"{design_sha256}:{round_number}:{group}:{config_id(*c)}".encode("utf-8")).hexdigest())


def schedule(design_sha256: str, configs: Sequence[Tuple[str, str]], repetitions: int = REPETITIONS) -> List[Dict[str, Any]]:
    """The registered run order (``SCHEDULE_RULE``)."""
    plan: List[Dict[str, Any]] = []
    previous: Optional[Tuple[str, str, str]] = None
    for round_number in range(1, repetitions + 1):
        first, second = ("B", "C") if round_number % 2 else ("C", "B")
        orders = {g: _order(design_sha256, round_number, g, configs) for g in GROUPS}
        if previous is not None and (orders[first][0] + (first,)) == previous:
            orders[first][0], orders[first][1] = orders[first][1], orders[first][0]
        games = [(group, orders[group][i]) for i in range(len(configs)) for group in (first, second)]
        for group, (scenario_id, condition) in games:
            plan.append({"position": len(plan) + 1, "round": round_number, "group": group, "scenario_id": scenario_id,
                         "condition": condition, "repetition": round_number, "attempt": 1,
                         "game_id": game_id(scenario_id, condition, group, round_number)})
        last = plan[-1]
        previous = (last["scenario_id"], last["condition"], last["group"])
    return plan


def group_conditions(policy: str, control: str) -> Dict[str, Dict[str, str]]:
    return {"C1": {"red": policy, "blue": policy}, "C2": {"red": policy, "blue": control},
            "C3": {"red": control, "blue": policy}}


def build(study_manifest: Mapping[str, Any], study_results: Mapping[str, Any], study_results_sha256: str,
          runtime: Mapping[str, Any], candidate: Mapping[str, Any], counterfactual: Mapping[str, Any],
          counterfactual_sha256: str, mutation: Mapping[str, Any], mutation_sha256: str) -> Dict[str, Any]:
    """The registered manifest. Every input is a committed file; generation is deterministic.

    ``runtime`` pins baseline-v1-runtime-r1 (source digest and files, remediation record digests); ``candidate``
    the candidate (source digest, files, golden trace chain)."""
    if mf.digest(study_manifest) != "78109fca78dc8b044b63dcf475c163ca91a6f7f60fe1454a4b126d7ada10f48e":
        raise ValueError("the variance-study manifest is not the frozen one")
    if runtime["policy_source_sha256"] != RUNTIME_R1_SOURCE_SHA256:
        raise ValueError("the runtime is not baseline-v1-runtime-r1")
    if counterfactual["unexplained_states"] != 0 or counterfactual["totals"]["class_E"] != 0:
        raise ValueError("the counterfactual replay has unexplained deltas; the experiment may not be registered")
    if not mutation["pass"]:
        raise ValueError("the mutation test did not pass")
    if counterfactual["candidate"]["policy_source_sha256"] != candidate["policy_source_sha256"]:
        raise ValueError("the counterfactual replay is not of this candidate")
    sizing = study_results["sizing"]
    row516 = next(r for r in sizing[PRIMARY_METRIC]["table"] if r["repetitions"] == REPETITIONS)
    row_margin = next(r for r in sizing[MARGIN_METRIC]["table"] if r["repetitions"] == REPETITIONS)
    control = study_manifest["control_policy"]
    manifest: Dict[str, Any] = {key: copy.deepcopy(study_manifest[key]) for key in (
        "engine", "scenarios", "players", "caps", "randomness", "replay_check_every")}
    manifest.update({
        "schema": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "evaluation_id": EXPERIMENT_ID,
        "purpose": "preregistered single-variable tactical experiment: same-step shoot-target reservation against "
                   "baseline-v1, both on baseline-v1-runtime-r1",
        "parent": {"identity": vs.BASELINE_IDENTITY, "policy_source_sha256": vs.BASELINE_V1_SOURCE_SHA256,
                   "golden_trace_chain": vs.BASELINE_V1_GOLDEN_TRACE_CHAIN,
                   "evaluation_manifest_sha256": vs.BASELINE_V1_MANIFEST_SHA256,
                   "evaluation_results_sha256": vs.BASELINE_V1_RESULTS_SHA256},
        "runtime": dict(runtime),
        "scenario_source": {"manifest": "evaluation/baseline-v1-variance-study-1/manifest.json",
                            "manifest_sha256": mf.digest(study_manifest),
                            "note": "the eight scenarios, players, caps and randomness procedure are copied unchanged"},
        "control_policy": control,
        "groups": {
            "B": {"label": "baseline-v1 on baseline-v1-runtime-r1", "policy": RUNTIME_R1_CODE_ID,
                  "policy_source": {"sha256": runtime["policy_source_sha256"], "files": list(runtime["files"]),
                                    "sources": list(runtime["sources"])},
                  "conditions": group_conditions(RUNTIME_R1_CODE_ID, control)},
            "C": {"label": "candidate on baseline-v1-runtime-r1", "policy": CANDIDATE_ID,
                  "policy_source": {"sha256": candidate["policy_source_sha256"], "files": list(candidate["files"]),
                                    "sources": list(candidate["sources"])},
                  "golden_trace_chain": candidate["golden_trace_chain"], "trace_schema": TRACE_SCHEMA,
                  "conditions": group_conditions(CANDIDATE_ID, control)},
        },
        "policy_source_rule": "sorted relative paths, CRLF normalized to LF; see evaluation/identity.py",
        "active_conditions": list(ACTIVE_CONDITIONS),
        "control_condition": "C4 (inert mirror) contains no decision of either policy and is not played",
        "repetitions": REPETITIONS,
        "games": REPETITIONS * len(GROUPS) * len(ACTIVE_CONDITIONS) * len(study_manifest["scenarios"]),
        "single_variable": SINGLE_VARIABLE,
        "hypothesis": dict(HYPOTHESIS),
        "primary_metric": dict(PRIMARY_DEFINITION),
        "primary_analysis": dict(PRIMARY_ANALYSIS),
        "effect_grid": {"metric": PRIMARY_METRIC, "relative_change": list(EFFECT_GRID),
                        "practically_important": "a 50% relative reduction, the effect of the variance study's default "
                                                 "repetition rule"},
        "planning": {
            "source": {"file": "evaluation/baseline-v1-variance-study-1/results.json", "sha256": study_results_sha256},
            "default_repetitions": study_results["default_repetitions"],
            "default_rule": "the smallest n at which the conservative power for a 50% reduction of all engine refusals "
                            "per 1,000 unit actions reaches 0.8 (the variance study's registered rule)",
            PRIMARY_METRIC: {"repetitions": REPETITIONS, "se": row516["se"], "se_conservative": row516["se_conservative"],
                             "mde": row516["mde"], "mde_conservative": row516["mde_conservative"],
                             "effects": copy.deepcopy(row516["effects"])},
            MARGIN_METRIC: {"repetitions": REPETITIONS, "se": row_margin["se"],
                            "se_conservative": row_margin["se_conservative"], "mde": row_margin["mde"],
                            "mde_conservative": row_margin["mde_conservative"],
                            "effects": [e for e in row_margin["effects"] if e["kind"] == "absolute_points"]},
            "note": "n = 15 is the variance study's default. For the code-516 rate it gives analytic power 0.90 and "
                    "conservative power 0.60 for a 50% reduction, and 1.00 / 0.99 for a 100% reduction; the power "
                    "figures assume the candidate keeps baseline-v1's within-configuration SDs",
            "cost": copy.deepcopy(study_results["cost"][[c["repetitions"] for c in study_results["cost"]].index(REPETITIONS)]),
        },
        "non_inferiority": dict(NON_INFERIORITY),
        "secondary_metrics": {
            "mechanism (deterministic within a state)": "duplicate same-target shoot commands per seat and step (harness "
                "count from emitted actions); reserved-target exclusions (units whose best shoot option was excluded); "
                "alternate-target redirections; fallbacks to occupation, movement and no action; excluded options; "
                "shots; unique targets engaged (sum over steps of distinct shoot targets); unique targets per step with "
                "a shot; code-516 refusals per 1,000 shoot actions",
            "refusals (stochastic engine outcome)": "code 516 with its step evidence (own shots at the target in the "
                "step: 1 or at least 2), code 203, code 404, total engine refusals, factual classes",
            "safety and regression": "project-gate rejections, contract errors, replay mismatches, code 1804, duplicate "
                "occupation commands, games that did not complete, deployment completion, new factual classes, "
                "policy and runtime digests",
            "descriptive": "scores and margins in every condition, active-step rate, no-op rate, moves, occupations, "
                "shots, decision latency p50/p95/p99/max, decisions slower than 100 ms, 400 ms and 1 s",
        },
        "known_refusal_classes": [list(c) for c in KNOWN_CLASSES],
        "refusal_taxonomy": {"fact": refusals.FACT_SCHEMA, "attribution": refusals.ATTRIBUTION_VERSION,
                             "document": "docs/REFUSAL_TAXONOMY.md"},
        "promotion": dict(PROMOTION),
        "promotion_rules": list(PROMOTION_RULES),
        "not_criteria": list(NOT_CRITERIA),
        "schedule_rule": list(SCHEDULE_RULE),
        "failure_rules": list(FAILURE_RULES),
        "artifacts": dict(ARTIFACTS),
        "artifact_schema": {"game_record": f"{GAME_SCHEMA} with seat fields {', '.join(SEAT_FIELDS)}",
                            "decision_trace": TRACE_SCHEMA},
        "counterfactual_replay": {"file": f"evaluation/{EXPERIMENT_NAME}/counterfactual-replay.json",
                                  "sha256": counterfactual_sha256,
                                  "corpus_sha256": counterfactual["corpus"]["sha256"],
                                  **{k: counterfactual["totals"][k] for k in (
                                      "states", "identical", "changed", "baseline_duplicate_shots", "displaced_units",
                                      "class_A", "class_B", "class_C", "class_D", "class_I", "class_E",
                                      "candidate_duplicate_shots")},
                                  "unexplained_states": counterfactual["unexplained_states"]},
        "mutation": {"file": f"evaluation/{EXPERIMENT_NAME}/mutation.json", "sha256": mutation_sha256,
                     "non_equivalent": copy.deepcopy(mutation["non_equivalent"]),
                     "equivalent": copy.deepcopy(mutation["equivalent"])},
        "level": LEVEL, "bootstrap": dict(BOOTSTRAP), "non_inferiority_margin": NON_INFERIORITY_MARGIN,
        "minimum_relative_reduction": MINIMUM_RELATIVE_REDUCTION,
    })
    manifest["design_sha256"] = design_digest(manifest)
    manifest["schedule"] = schedule(manifest["design_sha256"], configurations(manifest))
    return manifest


def is_experiment(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(manifest: Mapping[str, Any]) -> List[mf.GameSpec]:
    """The registered games in play order."""
    scenarios = {s["scenario_id"]: s for s in manifest["scenarios"]}
    specs = []
    for entry in manifest["schedule"]:
        policies = manifest["groups"][entry["group"]]["conditions"][entry["condition"]]
        scenario = scenarios[entry["scenario_id"]]
        specs.append(mf.GameSpec(game_id=entry["game_id"], scenario_id=entry["scenario_id"], map_id=scenario["map_id"],
                                 condition=entry["condition"], red=policies["red"], blue=policies["blue"],
                                 repetition=entry["repetition"], max_time=int(scenario["max_time"])))
    return specs


def group_of(manifest: Mapping[str, Any], game: str) -> str:
    return next(e["group"] for e in manifest["schedule"] if e["game_id"] == game)


# ----------------------------------------------------------------------------------------------
# Per-game metrics


def _per_1000(count: int, actions: int) -> Optional[float]:
    return 1000.0 * count / actions if actions else None


def game_metrics(record: Mapping[str, Any], policy: str) -> Dict[str, Any]:
    """The variance study's metrics of one game plus this experiment's mechanism and safety fields."""
    base = vs.game_metrics(record, policy)
    values = dict(base["values"])
    seats = [s for s in record.get("seats", []) if s["policy"] == policy]
    missing = [name for name in SEAT_FIELDS for s in seats if name not in s]
    if missing:
        raise ValueError(f"{record.get('game_id')}: seat fields missing: {sorted(set(missing))}")
    effects: Dict[str, int] = {}
    for seat in seats:
        for effect, count in seat["shoot_reservation_effects"].items():
            effects[effect] = effects.get(effect, 0) + count
    evidence = {"repeat_fire": 0, "single_fire": 0, "no_evidence": 0}
    for seat in seats:
        for refusal in seat.get("refusals", []):
            if refusal.get("code") in (516, "516"):
                shots = (refusal.get("evidence") or {}).get("own_shots_at_target")
                key = "no_evidence" if shots is None else "repeat_fire" if shots >= 2 else "single_fire"
                evidence[key] += 1
    shots = values["shots"]
    steps_with_shot = sum(s["steps_with_shot"] for s in seats)
    engaged = sum(s["shoot_targets_engaged"] for s in seats)
    latencies = [v for s in seats for v in s["latency_us"]]
    values.update({
        "duplicate_shoot_target_commands": sum(s["duplicate_shoot_target_commands"] for s in seats),
        "duplicate_shoot_target_steps": sum(s["duplicate_shoot_target_steps"] for s in seats),
        "unique_targets_engaged": engaged,
        "steps_with_shot": steps_with_shot,
        "unique_targets_per_shot_step": engaged / steps_with_shot if steps_with_shot else None,
        "reserved_target_exclusions": sum(effects.get(e, 0) for e in DISPLACED_EFFECTS),
        "alternate_target_redirections": effects.get("alternate-target", 0),
        "fallback_occupy": effects.get("fallback-occupy", 0),
        "fallback_move": effects.get("fallback-move", 0),
        "fallback_none": effects.get("fallback-none", 0),
        "unchanged_with_exclusion": effects.get("unchanged", 0),
        "excluded_options": sum(s["shoot_excluded_options"] for s in seats),
        "code_516_per_1000_shots": _per_1000(values["code_516"], shots),
        "code_516_repeat_fire": evidence["repeat_fire"],
        "code_516_single_fire": evidence["single_fire"],
        "code_516_no_evidence": evidence["no_evidence"],
        "code_404": sum(int(s["feedback_errors_by_code"].get("404", 0)) for s in seats),
        "contract_errors": sum(s["contract_errors"] for s in seats),
        "replay_checks": sum(s["replay_checks"] for s in seats),
        "replay_mismatches": sum(s["replay_mismatches"] for s in seats),
        "duplicate_occupation_commands": sum(s["duplicate_occupation_commands"] for s in seats),
        "decisions_over_1000ms": sum(1 for v in latencies if v > 1_000_000),
    })
    return {"values": values, "facts": base["facts"], "facts_complete": base["facts_complete"],
            "attributions": base["attributions"], "margin_fields_consistent": base["margin_fields_consistent"],
            "first_shot_decision": base["first_shot_decision"]}


# ----------------------------------------------------------------------------------------------
# Analysis


def metric_seed(name: str) -> int:
    return int(hashlib.sha256(f"{BOOTSTRAP['seed']}:{name}".encode("utf-8")).hexdigest()[:12], 16)


def contrast(baseline: Mapping[str, Sequence[float]], candidate: Mapping[str, Sequence[float]], name: str,
             resamples: int = BOOTSTRAP["resamples"]) -> Dict[str, Any]:
    """The equal-weighted difference of configuration means (candidate minus baseline) with its registered
    stratified bootstrap interval and the analytic sensitivity interval."""
    configs = sorted(set(baseline) & set(candidate))
    pairs = [([v for v in baseline[c] if v is not None], [v for v in candidate[c] if v is not None]) for c in configs]
    usable = [(c, b, x) for c, (b, x) in zip(configs, pairs) if b and x]
    if not usable:
        return {"configurations": 0}
    k = len(usable)
    base_means = [sum(b) / len(b) for _, b, _ in usable]
    cand_means = [sum(x) / len(x) for _, _, x in usable]
    delta = sum(c - b for b, c in zip(base_means, cand_means)) / k
    base_level = sum(base_means) / k
    rng = random.Random(metric_seed(name))
    samples: List[float] = []
    relative: List[float] = []
    for _ in range(resamples):
        d_sum = b_sum = 0.0
        for _, b, x in usable:
            mb = sum(b[stats.draw(rng, len(b))] for _ in b) / len(b)
            mx = sum(x[stats.draw(rng, len(x))] for _ in x) / len(x)
            d_sum += mx - mb
            b_sum += mb
        samples.append(d_sum / k)
        if b_sum:
            relative.append((d_sum / k) / (b_sum / k))
    low, high = stats.percentile_interval(samples, LEVEL)
    var_terms = []
    df = 0
    for _, b, x in usable:
        vb, vx = stats.variance(b) or 0.0, stats.variance(x) or 0.0
        var_terms.append(vb / len(b) + vx / len(x))
        df += len(b) + len(x) - 2
    se = math.sqrt(sum(var_terms)) / k
    t = stats.t_quantile(0.5 + LEVEL / 2, df) if df > 0 else None
    rel_interval = stats.percentile_interval(relative, LEVEL) if relative else (None, None)
    return {"configurations": k, "baseline_mean": base_level, "candidate_mean": sum(cand_means) / k,
            "delta": delta, "relative_change": delta / base_level if base_level else None,
            "ci_low": low, "ci_high": high, "relative_ci_low": rel_interval[0], "relative_ci_high": rel_interval[1],
            "analytic_se": se, "analytic_df": df,
            "analytic_ci_low": None if t is None else delta - t * se,
            "analytic_ci_high": None if t is None else delta + t * se,
            "per_configuration": {c: {"baseline_mean": sum(b) / len(b), "candidate_mean": sum(x) / len(x),
                                      "baseline_n": len(b), "candidate_n": len(x)} for c, b, x in usable}}


def primary_verdict(result: Mapping[str, Any]) -> Dict[str, Any]:
    relative = result.get("relative_change")
    reduction = None if relative is None else -relative
    passed = (result.get("configurations") == 24 and result["ci_high"] < 0 and reduction is not None
              and reduction >= MINIMUM_RELATIVE_REDUCTION)
    return {"relative_reduction": reduction, "interval_below_zero": bool(result.get("ci_high", 0) < 0),
            "reaches_minimum_reduction": bool(reduction is not None and reduction >= MINIMUM_RELATIVE_REDUCTION),
            "pass": bool(passed)}


def non_inferiority_verdict(result: Mapping[str, Any]) -> Dict[str, Any]:
    passed = result.get("configurations") == 16 and result["ci_low"] > -NON_INFERIORITY_MARGIN
    return {"margin": -NON_INFERIORITY_MARGIN, "lower_limit": result.get("ci_low"), "pass": bool(passed)}


def latency_summary(latencies_us: Sequence[int]) -> Dict[str, Any]:
    ms = [v / 1000.0 for v in latencies_us]
    if not ms:
        return {"decisions": 0}
    return {"decisions": len(ms), "p50_ms": nearest_rank(ms, 50), "p95_ms": nearest_rank(ms, 95),
            "p99_ms": nearest_rank(ms, 99), "max_ms": max(ms), "over_100ms": sum(1 for v in ms if v > 100),
            "over_400ms": sum(1 for v in ms if v > 400), "over_1000ms": sum(1 for v in ms if v > 1000)}


def promotion(checks: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """P1-P10 from their individual checks; the candidate is promoted only when every one passes."""
    verdict = {name: {"pass": bool(checks[name]["pass"]), "detail": checks[name].get("detail")}
               for name in sorted(PROMOTION, key=lambda p: int(p[1:]))}
    all_pass = all(v["pass"] for v in verdict.values()) and set(verdict) == set(PROMOTION)
    disposition = ("PROMOTED AS baseline-v2" if all_pass else "RETAINED AS PARTIAL/NEGATIVE CANDIDATE")
    return {"criteria": verdict, "all_pass": all_pass, "disposition": disposition}
