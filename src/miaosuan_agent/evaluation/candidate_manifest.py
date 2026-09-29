"""The registered manifest of the occupation-reservation candidate experiment.

It is derived from the registered ``baseline-v0`` manifest: scenario selection, scenarios and their
input digests, repetitions, order, players, caps, the randomness procedure, the Gate 1 scenario and
the definitions of G1-G6 are copied unchanged, and the candidate replaces ``baseline-v0`` wherever
the policy under test plays. Added: the single-variable hypothesis, the acceptance criteria, the
refusal taxonomy (supplementary to G4, which keeps its registered definition), the metrics registered
for this experiment, the pinned ``baseline-v0`` reference and the pinned counterfactual replay result.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Sequence

from ..decision import BASELINE_ID, INERT_ID
from ..experiments.occupy_reservation import CANDIDATE_ID, TRACE_SCHEMA
from . import manifest as mf
from .game import SCHEMA as GAME_SCHEMA
from .identity import OCCUPY_RESERVATION_SOURCES
from .metrics import LATER_SEAT_FIELDS

SCHEMA = "miaosuan-evaluation-manifest/2"
EVALUATION_NAME = CANDIDATE_ID
EVALUATION_ID = f"{CANDIDATE_ID}-suite-1"
#: Chained digest of the candidate's golden decisions (tests/test_occupy_reservation.py).
GOLDEN_TRACE_CHAIN = "11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66"
#: Frozen reference values of baseline-v0 that are not stored in its manifest.
V0_GOLDEN_TRACE_CHAIN = "0743df89c0855d7673352ce16727c1c613264839659b157183f6a97fbaa7cff2"
V0_REGISTRATION_COMMIT = "0a806f1"

SINGLE_VARIABLE = (
    "Within one decision step at most one occupation command is issued per objective (keyed by the hex the "
    "occupying unit stands on, the objective's coord). Units are processed in baseline-v0 order; the first unit "
    "that selects occupation of an objective keeps it; a later unit that would select occupation of the same "
    "objective is suppressed, recorded in the trace with reason 'same-step-objective-reserved', and continues down "
    "the unchanged baseline-v0 hierarchy. The reservation lives for one decision step. Nothing else differs from "
    "baseline-v0: context, candidate generation, priorities, rankings, tie-breaks, shooting, movement, routing, "
    "deployment and the safety gate are reused unchanged by import."
)
HYPOTHESIS = (
    "Per-objective, per-step occupation reservation eliminates engine refusal code 1804 attributable to duplicate "
    "friendly occupation commands, without introducing a project-gate rejection or changing unrelated baseline "
    "decision behaviour. No score or win-rate hypothesis is registered; outcomes are descriptive."
)
ACCEPTANCE = (
    "A1 baseline-v0 still verifies: its policy source digest, golden decision chain, manifest re-derivation, and "
    "byte-identical regeneration of its committed results from its game records",
    "A2 counterfactual replay of recorded real start-of-step inputs shows zero unexplained deltas (pinned below; "
    "run before registration)",
    "A3 the public and private tests pass on both machines",
    "A4 Gate 1 passes G1-G6",
    "A5 the suite completes: every registered game reaches the engine's done flag",
    "A6 project-gate rejections of the policy under test: 0 over Gate 1 and the suite",
    "A7 duplicate same-objective occupation commands emitted by the policy under test, counted by the harness from "
    "the emitted actions: 0",
    "A8 engine refusals 1804 whose start-of-step context is several own occupations of the objective: 0",
    "A9 no scenario, map or terrain identifier in the candidate's policy sources",
    "A10 determinism: G5 passes in every applicable configuration and every in-game replay check matches",
    "A11 repository and privacy checks pass",
)
NOT_CRITERIA = (
    "G4 is reported exactly as registered for baseline-v0 and is not a promotion criterion; it is expected to keep "
    "failing because codes 516 and 203 are untouched by this experiment",
    "engine scores and results are descriptive only",
    "latency is reported, not judged",
    "a code-1804 refusal with another start-of-step context is reported and analysed, and no second heuristic is added",
)
ANALYSIS = (
    "No composite quality score is computed and no claim of tactical strength is made.",
    "Deterministic policy effects are separated from effects of divergent stochastic engine trajectories: the "
    "counterfactual replay measures the former; live counts of 516 and 203 may change only through the latter.",
    "The candidate is promoted to baseline-v1 only if A1-A11 all hold; otherwise it is kept as a negative or "
    "partial candidate under its own identity.",
    "Scenarios are never dropped, added or reordered after results are seen, except by rule R of the selection.",
    "Any change to the candidate's policy source invalidates its results: a new digest, registration and full rerun.",
)
METRICS_ADDED = {
    "primary": "code-1804 refusals (by start-of-step context); steps with a suppressed duplicate occupation; "
               "occupations suppressed by the reservation; project-gate rejections; engine refusals; G4 as registered",
    "secondary": "actions by type; active-step rate (steps with an action / decisions); no-op rate (no-op unit-steps / "
                 "(no-op unit-steps + unit actions)); games completed; failures and caps; contract errors; latency "
                 "p50/p95/p99/max; total decision time; wall time; replay checks",
    "descriptive": "the engine's final scores",
}


def taxonomy(v0_diagnostics: Mapping[str, Any]) -> Dict[str, Any]:
    """The refusal taxonomy, with evidence counts read from the committed baseline-v0 diagnostics."""
    classes = {c["code"]: c for c in v0_diagnostics["refusal_context"]["classes"]}
    messages = {code: entries[0] for code, entries in v0_diagnostics["engine_messages"]["codes"].items()}
    games = len(v0_diagnostics["refusal_context"]["games"])
    evidence = "evaluation/baseline-v0/diagnostics.json: {n} of {n} diagnosed refusals in {g} games: {context}"
    categories = {"1804": "same-step conflict: duplicate own occupation",
                  "516": "same-step conflict: target destroyed earlier in the step",
                  "203": "same-step conflict: shooter destroyed earlier in the step"}
    codes = {}
    for code, category in categories.items():
        observed = classes[int(code)]
        codes[code] = {"action_type": messages[code]["action_type"], "engine_message": messages[code]["engine_message"],
                       "category": category,
                       "evidence": evidence.format(n=observed["count"], g=games, context=", ".join(observed["context"]))}
    return {
        "codes": codes,
        "unknown_code": "unclassified",
        "instance_contexts": [
            "occupy 1804: objective held by own side at step start | several own occupations of the objective in the "
            "step | otherwise unexplained",
            "shoot 516: target absent at step start | target fired at more than once by own side in the step | "
            "otherwise unexplained",
            "shoot 203: shooter absent at step start | shooter present at step start (destroyed during the step)",
            "any other code or action type: unclassified",
        ],
        "decomposition": ["project-gate rejections", "engine refusals", "engine refusals by code",
                          "engine refusals of actions the gate accepted at decision time",
                          "engine refusals by evidence-backed code category (unknown codes unclassified)",
                          "engine refusals by start-of-step context class"],
        "relation_to_g4": "supplementary; G4 keeps its registered definition and baseline-v0's G4 result stands",
    }


def build(v0_manifest: Mapping[str, Any], v0_results_sha256: str, v0_diagnostics: Mapping[str, Any],
          candidate_source_sha256: str, candidate_files: Sequence[str], replay: Mapping[str, Any],
          replay_sha256: str) -> Dict[str, Any]:
    manifest = {key: copy.deepcopy(v0_manifest[key]) for key in (
        "engine", "selection", "scenarios", "repetitions", "order", "players", "caps", "randomness",
        "replay_check_every", "gate1", "gate_criteria")}
    substitute = {BASELINE_ID: CANDIDATE_ID}
    conditions = []
    for condition in v0_manifest["conditions"]:
        red, blue = substitute.get(condition["red"], condition["red"]), substitute.get(condition["blue"], condition["blue"])
        description = condition["description"].replace("baseline", "candidate")
        conditions.append({"id": condition["id"], "red": red, "blue": blue, "description": description})
    manifest.update({
        "schema": SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "policy_under_test": CANDIDATE_ID,
        "control_policy": INERT_ID,
        "conditions": conditions,
        "reference": {"identity": BASELINE_ID, "policy_source_sha256": v0_manifest["policy_source"]["sha256"],
                      "manifest_sha256": mf.digest(v0_manifest), "results_sha256": v0_results_sha256,
                      "golden_trace_chain": V0_GOLDEN_TRACE_CHAIN, "registration_commit": V0_REGISTRATION_COMMIT,
                      "scenarios": "copied unchanged from the baseline-v0 manifest"},
        "single_variable": SINGLE_VARIABLE,
        "hypothesis": HYPOTHESIS,
        "acceptance": list(ACCEPTANCE),
        "not_criteria": list(NOT_CRITERIA),
        "gate_rules": [
            "Gate 1 passes when G1-G6 all pass for its two games; the suite may not start before that",
            "in the suite, G1-G6 are evaluated for every configuration over its repetitions and reported; criteria "
            "about the seats of the policy under test are not applicable to C4",
            "G1-G6 keep their baseline-v0 definitions, with 'baseline seats' read as the seats of the policy under test",
        ],
        "metrics": dict(v0_manifest["metrics"], **{f"added_{k}": v for k, v in METRICS_ADDED.items()}),
        "registered_seat_metrics": list(LATER_SEAT_FIELDS),
        "refusal_taxonomy": taxonomy(v0_diagnostics),
        "analysis": list(ANALYSIS),
        "policy_source": {"sha256": candidate_source_sha256, "files": list(candidate_files),
                          "sources": list(OCCUPY_RESERVATION_SOURCES),
                          "rule": "sorted relative paths, CRLF normalized to LF; see evaluation/identity.py"},
        "golden_trace_chain": GOLDEN_TRACE_CHAIN,
        "counterfactual_replay": {"file": f"evaluation/{EVALUATION_NAME}/counterfactual-replay.json",
                                  "sha256": replay_sha256,
                                  **{k: replay[k] for k in ("decision_states", "identical", "differing",
                                                            "unexplained", "suppressed_occupations")}},
        "artifact_schema": {"game_record": f"{GAME_SCHEMA} with seat fields {', '.join(LATER_SEAT_FIELDS)}",
                            "decision_trace": TRACE_SCHEMA,
                            "results": "sanitized summary written by scripts/run_evaluation.py summarize"},
    })
    return manifest
