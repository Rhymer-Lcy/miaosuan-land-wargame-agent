"""The evaluation manifest: everything fixed before the first baseline game is played.

The manifest is built deterministically from the scenario facts and the selection rule, serialized
as canonical JSON, and identified by the SHA-256 of that serialization. It carries no timestamp:
the commit that adds it is the registration record. Any change to the policy under test, the
selection, the conditions, the caps or the metric definitions produces a different digest and
requires a new registration and a complete rerun.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from ..decision import BASELINE_ID, INERT_ID
from .selection import NAMING_RULE, RULE_ID, Pick, ScenarioFacts

SCHEMA = "miaosuan-evaluation-manifest/1"
EVALUATION_ID = "baseline-v0-suite-1"
REPETITIONS = 2
STEP_MARGIN = 100
WALL_CAP_SECONDS = 1800
GLOBAL_SEED = 20260929
REPLAY_CHECK_EVERY = 100
PLAYERS = (
    {"seat": 1, "faction": 0, "role": 1, "user_name": "demo", "user_id": 0},
    {"seat": 11, "faction": 1, "role": 1, "user_name": "demo", "user_id": 0},
)
CONDITIONS = (
    ("C1", BASELINE_ID, BASELINE_ID, "baseline mirror"),
    ("C2", BASELINE_ID, INERT_ID, "baseline (red) against the inert control (blue)"),
    ("C3", INERT_ID, BASELINE_ID, "inert control (red) against the baseline (blue)"),
    ("C4", INERT_ID, INERT_ID, "inert mirror: the engine's outcome when nobody acts"),
)
GATE1 = {"scenario_id": "201033019601", "map_id": "9601", "condition": "C1", "repetitions": 2}

ELIGIBILITY = (
    "E1 the scenario id names a supplied map by the naming rule",
    "E2 every operator and objective hex lies inside that map",
    "E3 every operator that starts on the map (not on board) with a documented movement mode (types 1-3) "
    "has at least one traversable neighbour for that mode at its start hex",
    "E4 on a map whose cells carry roadblock flags, the scenario's roadblocks are exactly those cells",
)
SELECTION = (
    "S1 strata are the maps of the eligible scenarios",
    "S2 from each stratum, the scenario with the fewest operators; ties by smaller max_time, then smaller numeric id",
    "S3 in addition, the eligible scenario with the most operators overall (ties by smaller numeric id), "
    "or the next in that order if S2 already picked it",
    "R  replacement only after a documented objective failure (the engine raises during setup, before any "
    "decision): the next alternate of the same pick, in the listed order",
)
GATE_RULES = (
    "Gate 1 passes when G1-G6 all pass for its two games; the suite may not start before that",
    "in the suite, G1-G6 are evaluated for every configuration (scenario and condition) over its repetitions and "
    "reported; criteria about baseline seats are not applicable to C4",
)
GATE_CRITERIA = (
    "G1 every game reaches the engine's done flag within the step cap, without an exception in the engine, the "
    "harness or an agent, and without a contract error",
    "G2 both seats end deployment and the play stage begins",
    "G3 every baseline seat emits at least one play-stage unit action (activity)",
    "G4 no gate rejection, no engine-reported error for a baseline action, and every emitted move and deployment "
    "completion confirmed by the next observation; occupy and shoot confirmation is reported but not gating, because "
    "another action in the same step (such as a second shot at a target already destroyed) can legitimately remove "
    "its precondition (legality)",
    "G5 for every step before the first divergence of the engine state between the two repetitions, the "
    "decision traces are identical, and every in-game replay check matches (determinism)",
    "G6 every game record contains every registered metric (measurability)",
)
METRICS = {
    "reliability": "games completed / started; exceptions by origin; contract errors; step-cap and wall-cap hits",
    "legality": "gate rejections by sanitized reason; engine-reported errors for the seat's actions by code; "
                "effect check per emitted action (confirmed / not observed / indeterminate) by action type",
    "activity": "actions by type; steps with at least one action; units that acted / controllable units seen; "
                "first step of each action type; unit-step counts per no-op reason",
    "determinism": "per-step canonical digest of the all-seeing state; per-seat chained trace digest; first "
                   "divergence between repetitions; in-game replay mismatches; global RNG consumption probe",
    "outcome": "the engine's final scores fields exactly as reported (no composite score)",
    "performance": "per-decision latency (time.perf_counter) p50/p95/p99/max by nearest rank; total decision time; "
                   "total engine step time; game wall time; harness time = wall - decisions - engine",
}
ANALYSIS = (
    "No composite quality score is computed.",
    "Outcomes are reported per game and summarized descriptively per condition; with eight scenarios and two "
    "repetitions no claim that one policy is stronger than another is made.",
    "Scenarios are never dropped, added or reordered after results are seen, except by rule R.",
    "Any change to the policy under test invalidates every result: a new identity, registration and full rerun.",
)


@dataclass(frozen=True)
class GameSpec:
    game_id: str
    scenario_id: str
    map_id: str
    condition: str
    red: str
    blue: str
    repetition: int
    max_time: int

    @property
    def step_cap(self) -> int:
        return self.max_time + 1 + STEP_MARGIN


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            + "\n").encode("utf-8")


def digest(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def build(facts: Sequence[ScenarioFacts], picks: Sequence[Pick], input_digests: Mapping[str, Mapping[str, str]],
          sdk_archive_sha256: str, engine_version: str) -> Dict[str, Any]:
    """The manifest as a plain dict. ``input_digests`` maps scenario id -> file role -> SHA-256."""
    by_id = {item.scenario_id: item for item in facts}
    reasons: Dict[str, int] = {}
    for item in facts:
        for reason in item.reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
    scenarios = []
    for pick in picks:
        item = by_id[pick.scenario_id]
        scenarios.append({
            "scenario_id": pick.scenario_id, "map_id": pick.map_id, "rule": pick.rule,
            "operators": item.operators, "red": item.red, "blue": item.blue, "cities": item.cities,
            "max_time": item.max_time, "alternates": list(pick.alternates),
            "inputs_sha256": dict(sorted(input_digests[pick.scenario_id].items())),
        })
    return {
        "schema": SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "policy_under_test": BASELINE_ID,
        "control_policy": INERT_ID,
        "engine": {"version": engine_version, "sdk_archive_sha256": sdk_archive_sha256},
        "selection": {"rule_id": RULE_ID, "naming_rule": NAMING_RULE, "eligibility": list(ELIGIBILITY),
                      "selection": list(SELECTION), "pool": len(facts),
                      "eligible": sum(1 for item in facts if item.eligible),
                      "ineligible_by_reason": dict(sorted(reasons.items()))},
        "scenarios": scenarios,
        "conditions": [{"id": cid, "red": red, "blue": blue, "description": text}
                       for cid, red, blue, text in CONDITIONS],
        "repetitions": REPETITIONS,
        "order": "for each repetition, for each scenario in the listed order, for each condition in the listed order",
        "players": [dict(player) for player in PLAYERS],
        "caps": {"steps": f"max_time + 1 + {STEP_MARGIN}", "wall_seconds": WALL_CAP_SECONDS},
        "randomness": {
            "python_hash_seed": 0, "global_seed": GLOBAL_SEED,
            "procedure": "each game runs in a fresh process; the harness seeds Python's and NumPy's global "
                         "generators with global_seed before the engine is constructed and records whether "
                         "the engine consumes them; no undocumented engine interface is used",
        },
        "replay_check_every": REPLAY_CHECK_EVERY,
        "gate1": dict(GATE1),
        "gate_criteria": list(GATE_CRITERIA),
        "gate_rules": list(GATE_RULES),
        "metrics": dict(METRICS),
        "analysis": list(ANALYSIS),
    }


def games(manifest: Mapping[str, Any]) -> List[GameSpec]:
    """The registered games in execution order."""
    plan = []
    for repetition in range(1, int(manifest["repetitions"]) + 1):
        for scenario in manifest["scenarios"]:
            for condition in manifest["conditions"]:
                plan.append(GameSpec(
                    game_id=f"{scenario['scenario_id']}.{condition['id']}.r{repetition}",
                    scenario_id=scenario["scenario_id"], map_id=scenario["map_id"], condition=condition["id"],
                    red=condition["red"], blue=condition["blue"], repetition=repetition,
                    max_time=int(scenario["max_time"]),
                ))
    return plan


def gate1_games(manifest: Mapping[str, Any]) -> List[GameSpec]:
    gate = manifest["gate1"]
    condition = next(c for c in manifest["conditions"] if c["id"] == gate["condition"])
    scenario = next((s for s in manifest["scenarios"] if s["scenario_id"] == gate["scenario_id"]), None)
    if scenario is None:
        raise ValueError("the Gate 1 scenario must be one of the registered scenarios")
    return [GameSpec(game_id=f"gate1.{gate['scenario_id']}.{condition['id']}.r{repetition}",
                     scenario_id=gate["scenario_id"], map_id=gate["map_id"], condition=condition["id"],
                     red=condition["red"], blue=condition["blue"], repetition=repetition,
                     max_time=int(scenario["max_time"]))
            for repetition in range(1, int(gate["repetitions"]) + 1)]
