"""Build the privacy-safe public result for Sprint 10's T9-v2 exploratory screen.

    python scripts/t9_v2_exploration_analysis.py [--check] [--output PATH]

The private game records and captures remain under ``local/``.  This report extends the established exploratory
report with aggregate same-route staging, withholding-duration, objective, queue and integrity facts.  It never
publishes unit identifiers, map coordinates, raw observations or SDK data.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402

CARD_ID = "s10-t9-v2-exploration"
OUT = REPO_ROOT / "evaluation" / CARD_ID / "results.json"
SCHEMA = "miaosuan-exploratory-results/1"


def load_explore_report() -> Any:
    spec = importlib.util.spec_from_file_location("explore_report", REPO_ROOT / "scripts" / "explore_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duration_summary(details: Mapping[str, Any]) -> Dict[str, int | float]:
    values = sorted(int(row["decisions"]) for row in details.get("withhold_episodes", ()))
    if not values:
        return {"episodes": 0, "longest": 0, "median": 0, "sum": 0, "unique_units": 0}
    return {"episodes": len(values), "longest": max(values), "median": statistics.median(values),
            "sum": sum(values), "unique_units": int(details["withhold_unique_units"])}


def public_extension(record: Mapping[str, Any], capture: Mapping[str, Any], side: int) -> Dict[str, Any]:
    """Aggregate private fields without returning unit ids or objective coordinates."""
    seat = next(row for row in record["seats"] if int(row["faction"]) == side)
    details = capture["t9_v2"]
    flags = collections.Counter(int(flag) for _, flag in capture["snapshots"][-1]["flags"])
    scores = record["final_scores"]
    color = "red" if side == 0 else "blue"
    compact_errors = capture.get("addon_errors") or []
    return {
        "mechanism": {
            "stage_actions": int(capture["addon_changes"].get(f"{side}:stage", 0)),
            "stage_unique_units": int(details["stage_unique_units"]),
            "stage_path_hexes_removed": dict(details["stage_path_hexes_removed"]),
            "withhold_actions": int(capture["addon_changes"].get(f"{side}:withhold", 0)),
            "withholding": duration_summary(details),
        },
        "objectives_final": {"candidate": flags[side], "opponent": flags[1 - side],
                             "neutral_or_other": sum(flags.values()) - flags[side] - flags[1 - side]},
        "firing_and_damage": {"direct_fire_actions": int(seat["actions_by_type"].get("2", 0)),
                              "attack_score": int(scores.get(f"{color}_attack", 0)),
                              "remain_score": int(scores.get(f"{color}_remain", 0)),
                              "feedback_refusal_attributions": dict(seat.get("refusal_attributions") or {})},
        "candidate_queue": capture["waiting_ground_units"][str(side)],
        "candidate_max_objective_commitment": capture["max_objective_commitment"][str(side)],
        "integrity": {
            "addon_errors": len(compact_errors),
            "contract_errors": int(seat["contract_errors"]),
            "gate_rejections": sum(int(value) for value in seat["gate_rejections"].values()),
            "replay_mismatches": int(seat["replay_mismatches"]),
            "observer_errors": len(record.get("observer_errors") or ()),
            "state_changed": bool(record["session_close"]["state_changed"]),
            "home_changed": bool(record["session_close"]["home_changed"]),
            "engine_integrity_ok": bool(record["session_close"]["integrity"]["ok"]),
        },
    }


def historical_sprint9(game: Mapping[str, Any], side: int, phase_a: Mapping[str, Any],
                       phase_b: Mapping[str, Any]) -> Dict[str, float | int | str]:
    """The already-registered Sprint 9 means relevant to one exploratory game."""
    if game["condition"] in ("C2", "C3"):
        result = phase_b["against_inert"][f"{game['scenario_id']} {game['condition']}"]
        return {"population": f"Sprint 9 phase B {game['scenario_id']} {game['condition']}",
                "n_per_arm": int(result["strata"]["T9"]["n"]),
                "t9_v1_margin_mean": round(float(result["strata"]["T9"]["mean"]), 2),
                "baseline_v2_margin_mean": round(float(result["strata"]["V2"]["mean"]), 2),
                "registered_mean_difference": round(float(result["estimate"]), 2)}
    seat = "red" if side == 0 else "blue"
    result = phase_a["head_to_head"][game["scenario_id"]][seat]
    return {"population": f"Sprint 9 phase A {game['scenario_id']} {game['condition']}",
            "n_per_arm": int(result["strata"][f"H{side + 1} {seat}"]["n"]),
            "t9_v1_margin_mean": round(float(result["strata"][f"H{side + 1} {seat}"]["mean"]), 2),
            "baseline_v2_margin_mean": round(float(result["strata"][f"C1 {seat}"]["mean"]), 2),
            "registered_mean_difference": round(float(result["estimate"]), 2)}


def build(work: Path, control_work: Path) -> Dict[str, Any]:
    report = load_explore_report()
    card = json.loads((REPO_ROOT / "evaluation" / CARD_ID / "manifest.json").read_text(encoding="utf-8"))
    phase_a = json.loads((REPO_ROOT / "evaluation" / "t9-confirmation-1" / "phase-A.json").read_text(
        encoding="utf-8"))
    phase_b = json.loads((REPO_ROOT / "evaluation" / "t9-confirmation-1" / "phase-B.json").read_text(
        encoding="utf-8"))
    games = []
    problems = []
    for position, game in enumerate(card["games"], start=1):
        row = report.game_report(card, game, work, control_work)
        record_path = work / "games" / f"{game['game_id']}.json"
        capture_path = work / "capture" / f"{game['game_id']}.explore.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        side = report.candidate_side(game, card["candidate"])
        row.update(public_extension(record, capture, side))
        row["historical_sprint9"] = historical_sprint9(game, side, phase_a, phase_b)
        row["record_sha256"] = sha256(record_path)
        row["capture_sha256"] = sha256(capture_path)
        if row["capture_sha256"] != record["capture"]["compact_sha256"]:
            problems.append(f"{game['game_id']}: compact capture digest")
        if int(record["session"]) != 2778 + position:
            problems.append(f"{game['game_id']}: session sequence")
        if record["harness"]["manifest_sha256"] != xp.digest(card):
            problems.append(f"{game['game_id']}: manifest identity")
        integ = row["integrity"]
        if (row["status"] != "COMPLETED" or integ["addon_errors"] or integ["contract_errors"] or
                integ["gate_rejections"] or integ["replay_mismatches"] or integ["observer_errors"] or
                integ["state_changed"] or integ["home_changed"] or not integ["engine_integrity_ok"]):
            problems.append(f"{game['game_id']}: completion or integrity")
        if row["candidate_max_objective_commitment"]["max"] > 4:
            problems.append(f"{game['game_id']}: candidate objective capacity")
        games.append(row)
    grouped = collections.defaultdict(list)
    for row in games:
        grouped[f"{row['scenario_id']} {row['condition']}"].append(row["candidate_margin"])
    directional = {key: {"games": len(values), "candidate_margin_mean": round(statistics.mean(values), 2)}
                   for key, values in sorted(grouped.items())}
    primary = directional["2130511121 H1"]["candidate_margin_mean"] / 2
    primary += directional["2130511121 H2"]["candidate_margin_mean"] / 2
    directional["2130511121 seat average"] = {
        "games": 2, "candidate_margin_mean": round(primary, 2),
        "historical_t9_v1_registered_mean_improvement": 305.47,
        "historical_baseline_mirror_mean": 0,
    }
    return {
        "schema": SCHEMA,
        "card_id": CARD_ID,
        "card_sha256": xp.digest(card),
        "track": xp.TRACK,
        "candidate": card["candidate"],
        "candidate_policy_source_sha256": card["policies"][card["candidate"]]["policy_source"]["sha256"],
        "games": games,
        "directional_summary": directional,
        "integrity": {"ok": not problems, "problems": problems, "sessions": [row["session"] for row in games],
                      "session_cap_used": 14, "session_cap": 14},
        "note": "exploratory, directional and game-level; historical controls are descriptive, not a test of superiority",
        "privacy": "aggregates only; no unit identifiers, objective coordinates, raw observations or SDK data",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / CARD_ID)
    parser.add_argument("--control-work", type=Path,
                        default=REPO_ROOT / "local" / "evaluation" /
                        "baseline-v2-candidate-shoot-target-reservation")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build(args.work, args.control_work)
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False) + "\n"
    if args.check:
        same = args.output.exists() and args.output.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {args.output}")
        return 0 if same and result["integrity"]["ok"] else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    for row in result["games"]:
        print(f"{row['session']} {row['game_id']} margin={row['candidate_margin']} "
              f"objectives={row['objectives_final']['candidate']} attack={row['firing_and_damage']['attack_score']} "
              f"stage={row['mechanism']['stage_actions']} withhold={row['mechanism']['withhold_actions']} "
              f"longest={row['mechanism']['withholding']['longest']} p99ms={row['seat']['latency']['p99_ms']}")
    print(f"integrity={result['integrity']['ok']} problems={result['integrity']['problems']}")
    return 0 if result["integrity"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
