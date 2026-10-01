"""Exploratory tactical screens: a candidate against ``baseline-v2`` in a small, fast, registered engine A/B.

A screen is EXPLORATORY: it decides whether a tactic deserves a fresh confirmatory experiment, and it can never
promote a baseline. One manifest registers both policies by source digest, the frozen scenarios, the arm conditions
(C1 mirror of the arm's policy, C2 the arm as red against the inert control, C3 the arm as blue against it) for a
baseline arm and a candidate arm, the head-to-head conditions (H1 candidate red against baseline blue, H2 baseline
red against candidate blue), ``n`` games per configuration, a small diagnostic mechanism smoke (the candidate as red
against the inert control, one game per scenario, played with the read-only step capture), the execution identity
and the exploratory disposition rule. Games are ordered in rounds: round r plays game r of every configuration once,
ordered by SHA-256 of ``<design_sha256>:<r>:<config>``.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Sequence

from ..decision import INERT_ID
from . import manifest as mf
from .execution import RUNTIMES

SCHEMA = "miaosuan-tactical-screen-manifest/1"
ARM_CONDITIONS = ("C1", "C2", "C3")
HEAD_TO_HEAD = ("H1", "H2")
ARMS = ("b", "c")  # baseline, candidate


def arm_players(condition: str, policy: str) -> Dict[str, str]:
    return {"C1": {"red": policy, "blue": policy}, "C2": {"red": policy, "blue": INERT_ID},
            "C3": {"red": INERT_ID, "blue": policy}}[condition]


def configurations(scenarios: Sequence[str], baseline: str, candidate: str) -> List[Dict[str, Any]]:
    configs = []
    for sid in scenarios:
        for condition in ARM_CONDITIONS:
            for arm in ARMS:
                configs.append({"config": f"{sid}.{condition}.{arm}", "scenario_id": sid, "condition": condition,
                                "arm": arm, **arm_players(condition, baseline if arm == "b" else candidate)})
        configs.append({"config": f"{sid}.H1", "scenario_id": sid, "condition": "H1", "arm": None,
                        "red": candidate, "blue": baseline})
        configs.append({"config": f"{sid}.H2", "scenario_id": sid, "condition": "H2", "arm": None,
                        "red": baseline, "blue": candidate})
    return configs


def schedule(configs: Sequence[Mapping[str, Any]], n: int, design_sha256: str) -> List[Dict[str, Any]]:
    by_name = {c["config"]: c for c in configs}
    entries: List[Dict[str, Any]] = []
    for r in range(1, n + 1):
        order = sorted(by_name, key=lambda c: hashlib.sha256(f"{design_sha256}:{r}:{c}".encode("utf-8")).hexdigest())
        if entries and order[0] == entries[-1]["config"]:
            order[0], order[1] = order[1], order[0]
        for name in order:
            entries.append({**by_name[name], "game_id": f"{name}.x{r:02d}", "repetition": r, "round": r,
                            "position": len(entries) + 1})
    return entries


def smoke_games(scenarios: Sequence[str], candidate: str) -> List[Dict[str, Any]]:
    return [{"config": f"{sid}.C2.c", "scenario_id": sid, "condition": "C2", "arm": "c", **arm_players("C2", candidate),
             "game_id": f"{sid}.C2.c.s01", "repetition": 1, "round": 0, "position": k}
            for k, sid in enumerate(scenarios, start=1)]


def build(screen_id: str, texts: Mapping[str, Any], shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str,
          rt_results: Mapping[str, Any], rt_results_sha256: str, baseline: Mapping[str, Any],
          candidate: Mapping[str, Any], n: int) -> Dict[str, Any]:
    """The registered manifest. ``baseline`` and ``candidate``: {id, label, policy_source {sha256, files, sources}}."""
    (scheduler,) = rt_results["production_path"]["scheduler"]
    runtime = rt_results["disposition"]["runtime"]
    scenarios = [s["scenario_id"] for s in shoot_manifest["scenarios"]]
    configs = configurations(scenarios, baseline["id"], candidate["id"])
    design = {
        "schema": SCHEMA, "screen_id": screen_id, "evaluation_id": screen_id, "purpose": "exploratory",
        "eligible_for_promotion": False, **dict(texts),
        "baseline": baseline["id"], "candidate": candidate["id"],
        "policies": {p["id"]: {"label": p["label"], "policy_source": dict(p["policy_source"])} for p in (baseline, candidate)},
        "execution": {"workers": 32, "runtime": runtime, "scheduler": scheduler},
        "runtime_environment": dict(RUNTIMES[runtime]),
        "scenarios": [dict(s) for s in shoot_manifest["scenarios"]],
        "players": [dict(p) for p in shoot_manifest["players"]],
        "randomness": dict(shoot_manifest["randomness"]), "caps": dict(shoot_manifest["caps"]),
        "n_per_configuration": n, "configurations": configs,
        "inputs": {"shoot_manifest_sha256": shoot_manifest_sha256, "runtime_results_sha256": rt_results_sha256},
        "smoke_games": smoke_games(scenarios, candidate["id"]),
    }
    design_sha = mf.digest(design)
    return {**design, "design_sha256": design_sha, "games": schedule(configs, n, design_sha)}


def digest(manifest: Mapping[str, Any]) -> str:
    return mf.digest(manifest)


def is_screen(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(manifest: Mapping[str, Any], smoke: bool = False) -> List[mf.GameSpec]:
    scenarios = {s["scenario_id"]: s for s in manifest["scenarios"]}
    return [mf.GameSpec(game_id=g["game_id"], scenario_id=g["scenario_id"], map_id=scenarios[g["scenario_id"]]["map_id"],
                        condition=g["condition"], red=g["red"], blue=g["blue"], repetition=g["repetition"],
                        max_time=int(scenarios[g["scenario_id"]]["max_time"]))
            for g in (manifest["smoke_games"] if smoke else manifest["games"])]


def game_policies(spec: mf.GameSpec) -> List[str]:
    return sorted({spec.red, spec.blue} - {INERT_ID})


DISPOSITIONS = ("ADVANCE TO CONFIRMATION", "REVISE BEFORE CONFIRMATION", "REJECT TACTIC", "BLOCKED BY ENGINE SEMANTICS")


def smoke_verdict(games: Sequence[Mapping[str, Any]]) -> str:
    """The registered smoke pass rule over per-game smoke facts."""
    took_effect = any(g["splits_emitted"] and g["operators_appearing_in_deployment"] for g in games)
    commanded = any(g["appearing_operators_commanded"] for g in games)
    healthy = bool(games) and all(g["status"] == "COMPLETED" and not g["contract_errors"] and g["deployment_ended"]
                                  for g in games)
    if not took_effect or not commanded:
        return "BLOCKED BY ENGINE SEMANTICS"
    return "PASS" if healthy else "FAIL: a game was not healthy"


def exploratory_disposition(catastrophic: bool, pooled_mean: float, positive: int, negative: int, activated: int,
                            cells: int, inert_not_worse: int, scenarios: int = 8, configurations: int = 16) -> str:
    """The registered exploratory disposition (the smoke having passed)."""
    majority = scenarios // 2 + 1
    if catastrophic or (pooled_mean < 0 and negative >= majority):
        return DISPOSITIONS[2]
    if activated >= 0.75 * cells and pooled_mean > 0 and positive >= majority and inert_not_worse >= configurations // 2:
        return DISPOSITIONS[0]
    return DISPOSITIONS[1]
