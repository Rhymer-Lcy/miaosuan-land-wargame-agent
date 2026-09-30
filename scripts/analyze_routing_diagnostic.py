"""Summarize the routing remediation's engine diagnostic into public findings.

    python scripts/analyze_routing_diagnostic.py [--check]

Inputs (private, git-ignored): the diagnostic games under ``local/diagnostics/routing/engine/`` and,
for the trajectory comparison, the baseline-v1 records of the same scenario and condition from the
variance study and the latency diagnostic. Output: ``evaluation/routing-remediation-1/engine.json``
with counts, durations and step indices only (no observation, unit, hex or trace content).
``--check`` rebuilds it and compares with the committed file.

For each game: the live comparison with the shadow baseline-v1 agent (every decision of every
candidate seat), the candidate's and the shadow's decision times, the first play decision, every
decision above 100 ms in either arm with the collection time inside it, the engine's refusal codes,
the harness's replay checks, the session record (engine state and home unchanged, package integrity) and
the first step at which the game's observed state differs from each same-configuration baseline-v1
game, beside the same quantity between those baseline-v1 games themselves.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import stats  # noqa: E402
from miaosuan_agent.evaluation.metrics import first_divergence  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID
OUT = DIRECTORY / "engine.json"
ENGINE = REPO_ROOT / "local" / "diagnostics" / "routing" / "engine"
STUDY_GAMES = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "games"
LATENCY = REPO_ROOT / "local" / "diagnostics" / "latency" / "engine"
LATENCY_PLAN = REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json"
SCHEMA = "miaosuan-routing-engine-diagnostic/1"
RATIO = 0.50
SHOOT = "2"


def rows(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def ms(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value * 1000, 3)


def distribution_ms(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "p50": ms(stats.exact_rank_value(values, 50)), "p95": ms(stats.exact_rank_value(values, 95)),
            "p99": ms(stats.exact_rank_value(values, 99)), "max": ms(max(values))}


def first_shot(record: Mapping[str, Any]) -> Optional[int]:
    shots = [int(s["first_step_by_type"][SHOOT]) for s in record["seats"] if SHOOT in s["first_step_by_type"]]
    return min(shots) if shots else None


def references(scenario_id: str, condition: str) -> Dict[str, Mapping[str, Any]]:
    """Completed baseline-v1 records of the configuration: the study's repetitions and latency games."""
    found: Dict[str, Mapping[str, Any]] = {}
    for path in sorted(STUDY_GAMES.glob(f"{scenario_id}.{condition}.r*.json")):
        found[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    plan = json.loads(LATENCY_PLAN.read_text(encoding="utf-8"))
    for entry in plan["games"]:
        path = LATENCY / f"{entry['id']}.json.gz"
        if (entry["scenario_id"], entry["condition"]) == (scenario_id, condition) and path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                found[entry["id"]] = json.load(handle)["record"]
    return {name: record for name, record in found.items() if record.get("status") == "COMPLETED"}


def game(entry: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    path = ENGINE / f"{entry['id']}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    record = payload["record"]
    decisions = list(rows(ENGINE / payload["decisions_file"]))
    seats: Dict[str, Any] = {}
    for seat in record["seats"]:
        mine = [d for d in decisions if d["seat"] == seat["seat"]]
        if not mine:
            continue
        first = payload["first_play"][str(seat["seat"])]
        seats[str(seat["seat"])] = {
            "decisions_played": seat["decisions"], "decisions_compared": len(mine),
            "different": sum(1 for d in mine if not d["equal"]),
            "candidate_ms": distribution_ms([d["candidate"]["wall"] for d in mine]),
            "shadow_ms": distribution_ms([d["shadow"]["wall"] for d in mine]),
            "over_100ms": {"candidate": sum(1 for d in mine if d["candidate"]["wall"] > 0.1),
                           "shadow": sum(1 for d in mine if d["shadow"]["wall"] > 0.1)},
            "candidate_gc_max_ms": ms(max(d["candidate"]["gc"] for d in mine)),
            "first_play": None if first is None else {
                "decision": first["decision"], "candidate_ms": ms(first["candidate"]["wall"]),
                "shadow_ms": ms(first["shadow"]["wall"]), "candidate_cpu_ms": ms(first["candidate"]["cpu"]),
                "shadow_cpu_ms": ms(first["shadow"]["cpu"]),
                "ratio": round(first["candidate"]["wall"] / first["shadow"]["wall"], 4)},
            "rejected_decisions": {"candidate": sum(1 for d in mine if d["rejected"]),
                                   "shadow": sum(1 for d in mine if d["shadow_rejected"])},
            "contract_errors": {"candidate": sum(1 for d in mine if d["error"]),
                                "shadow": sum(1 for d in mine if d["shadow_error"])},
            "replay_checks": seat["replay_checks"], "replay_mismatches": seat["replay_mismatches"],
            "gate_rejections": sum(seat["gate_rejections"].values()),
            "engine_feedback_errors": sum(seat["feedback_errors_by_code"].values()),
            "engine_feedback_errors_by_code": seat["feedback_errors_by_code"],
            "over_100ms_decisions": [
                {"decision": d["decision"], "stage": d["stage"], "candidate_ms": ms(d["candidate"]["wall"]),
                 "candidate_gc_ms": ms(d["candidate"]["gc"]), "shadow_ms": ms(d["shadow"]["wall"]),
                 "shadow_gc_ms": ms(d["shadow"]["gc"])}
                for d in mine if d["candidate"]["wall"] > 0.1 or d["shadow"]["wall"] > 0.1],
        }
    others = references(entry["scenario_id"], entry["condition"])
    against = {name: first_divergence(record["state_steps"], other["state_steps"]) for name, other in others.items()}
    among = sorted({first_divergence(a["state_steps"], b["state_steps"])
                    for a, b in itertools.combinations(others.values(), 2)}, key=lambda v: (v is None, v or 0))
    close = payload["session_close"]
    result = {"scenario_id": entry["scenario_id"], "condition": entry["condition"], "purpose": entry["purpose"],
              "session": payload["session"], "status": record["status"], "steps": record.get("steps"),
              "python": payload["python"], "gc_thresholds": payload["gc_thresholds"],
              "comparison": payload["comparison"], "seats": seats,
              "session_close": {"state_changed": close["state_changed"], "home_changed": close["home_changed"],
                                "integrity_ok": close["integrity"]["ok"],
                                "integrity_changed": len(close["integrity"]["changed"]),
                                "integrity_missing": len(close["integrity"]["missing"])},
              "trajectory": {"first_shot_step": first_shot(record), "baseline_v1_games": len(others),
                             "first_state_divergence_from_baseline_v1": dict(sorted(against.items())),
                             "first_state_divergence_among_baseline_v1": among,
                             "first_shot_steps_of_baseline_v1": sorted({first_shot(o) for o in others.values()},
                                                                       key=lambda v: (v is None, v or 0))}}
    every = all(s["decisions_compared"] == s["decisions_played"] for s in seats.values())
    result["every_decision_compared"] = bool(seats) and every
    if entry["scenario_id"] == "2130511121":
        ratios = [s["first_play"]["ratio"] for s in seats.values() if s["first_play"]]
        result["engine_criterion"] = {"rule": f"first play decision <= {RATIO} x the shadow's time",
                                      "ratios": ratios, "pass": bool(ratios) and all(r <= RATIO for r in ratios)}
    return result


def build() -> Dict[str, Any]:
    registration = json.loads((DIRECTORY / "registration.json").read_text(encoding="utf-8"))
    games = {entry["id"]: game(entry) for entry in registration["engine_diagnostic"]["games"]}
    played = [g for g in games.values() if g]
    verdict = {
        "games_played": len(played), "games_registered": len(games),
        "all_completed": all(g["status"] == "COMPLETED" for g in played),
        "every_decision_compared": all(g["every_decision_compared"] for g in played),
        "different": sum(g["comparison"]["different"] for g in played),
        "decisions_compared": sum(g["comparison"]["decisions"] for g in played),
        "candidate_only_rejections_or_errors": sum(
            max(0, s["rejected_decisions"]["candidate"] - s["rejected_decisions"]["shadow"])
            + max(0, s["contract_errors"]["candidate"] - s["contract_errors"]["shadow"])
            for g in played for s in g["seats"].values()),
        "replay_mismatches": sum(s["replay_mismatches"] for g in played for s in g["seats"].values()),
        "sessions_left_state_unchanged": all(not g["session_close"]["state_changed"]
                                             and not g["session_close"]["home_changed"]
                                             and g["session_close"]["integrity_ok"] for g in played),
        "engine_criterion_pass": all(g["engine_criterion"]["pass"] for g in played if "engine_criterion" in g),
    }
    verdict["pass"] = (verdict["games_played"] == verdict["games_registered"] and verdict["all_completed"]
                       and verdict["every_decision_compared"] and verdict["different"] == 0
                       and verdict["candidate_only_rejections_or_errors"] == 0 and verdict["replay_mismatches"] == 0
                       and verdict["sessions_left_state_unchanged"] and verdict["engine_criterion_pass"])
    return {"schema": SCHEMA, "remediation_id": rr.REMEDIATION_ID, "games": games, "verdict": verdict}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    print(json.dumps(result["verdict"]))
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
