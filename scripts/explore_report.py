"""Report one EXPLORATORY run card's games (``docs/EXPLORATORY_TRACK.md``): directional, game-level, not confirmatory.

    python scripts/explore_report.py --card s8-t4-v1-mechanism [--work DIR] [--control-work DIR] [--public]

Reads the card, its game records and captures (``local/evaluation/<card>/``) and the historical ``baseline-v2``
control: the registered shoot-reservation experiment's group C records for the same scenario and the same seat
against the same kind of opponent (C1 mirror for a head-to-head game, C2 or C3 for a game against the inert
control). Prints a per-game table and, with ``--public``, writes ``evaluation/<card>/results.json``: aggregates only
(scores, margins, counts, durations, distances), no unit ids, hexes or positions.

Control placement is descriptive: the candidate's margin, the control's mean, standard deviation, range and the
number of control games below and above it. Nothing here is a test of superiority.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402

SIDES = {0: "red", 1: "blue"}
SCHEMA = "miaosuan-exploratory-results/1"


def candidate_side(game: Mapping[str, Any], candidate: str) -> int:
    return 0 if game["red"] == candidate else 1


def control_condition(game: Mapping[str, Any], side: int) -> str:
    opponent = game["blue"] if side == 0 else game["red"]
    if opponent == INERT_ID:
        return "C2" if side == 0 else "C3"
    return "C1"


def margin(scores: Mapping[str, Any], side: int) -> int:
    own, other = SIDES[side], SIDES[1 - side]
    return int(scores[f"{own}_total"]) - int(scores[f"{other}_total"])


def control(control_work: Path, scenario: str, condition: str, side: int) -> Dict[str, Any]:
    values = []
    for path in sorted((control_work / "games").glob(f"{scenario}.{condition}.C.r*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] == "COMPLETED":
            values.append(margin(record["final_scores"], side))
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.mean(values), 2), "sd": round(statistics.pstdev(values), 2),
            "min": min(values), "max": max(values), "values": sorted(values)}


def latency(values: List[int]) -> Dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {}
    return {"median_ms": round(statistics.median(ordered) / 1e3, 3),
            "p99_ms": round(ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))] / 1e3, 3),
            "max_ms": round(ordered[-1] / 1e3, 3)}


def indirect_facts(capture: Mapping[str, Any], side: int) -> Dict[str, Any]:
    orders = [o for o in capture["indirect_orders"] if o["faction"] == side]
    errors = collections.Counter()
    accepted = 0
    for entry in capture["indirect_feedback"]:
        message = entry["entry"].get("message") or {}
        if message.get("obj_id") is None:
            continue
        error = entry["entry"].get("error")
        code = error.get("code") if isinstance(error, Mapping) else None
        if code is None:
            accepted += 1
        else:
            errors[f"{code}/{str(error.get('message'))[:60]}"] += 1
    flight, boom, statuses = [], [], collections.Counter()
    for point in capture["indirect_points"]:
        if point["first"].get("color") != side:
            continue
        seen = point["statuses"]
        statuses["+".join(sorted(seen))] += 1
        if "0" in seen and "1" in seen:
            flight.append(seen["1"] - seen["0"])
        if "1" in seen:
            boom.append(point["last_step"] - seen["1"] + 1)
    damage = collections.Counter()
    align = collections.Counter()
    results = collections.Counter()
    for item in capture["indirect_judgements"]:
        entry = item["entry"]
        if entry.get("attack_color") != side:
            continue
        target = "own" if entry.get("target_color") == side else "enemy"
        align[str(entry.get("align_status"))] += 1
        value = entry.get("damage")
        results[f"{target}:{value}"] += 1
        if isinstance(value, int) and value > 0:
            damage[target] += value
    return {"orders": len(orders), "feedback_without_error": accepted, "feedback_errors": dict(sorted(errors.items())),
            "points_by_statuses": dict(sorted(statuses.items())),
            "flight_steps": sorted(collections.Counter(flight).items()),
            "explosion_steps": sorted(collections.Counter(boom).items()),
            "judgements_by_align_status": dict(sorted(align.items())),
            "judgement_results": dict(sorted(results.items())), "damage": dict(sorted(damage.items())),
            "order_distances": capture.get("addon_distances", {}).get(str(side), {})}


def game_report(card: Mapping[str, Any], game: Mapping[str, Any], work: Path, control_work: Path) -> Dict[str, Any]:
    candidate = card["candidate"]
    side = candidate_side(game, candidate)
    record_path = work / "games" / f"{game['game_id']}.json"
    if not record_path.exists():
        return {"game_id": game["game_id"], "status": "NOT PLAYED"}
    record = json.loads(record_path.read_text(encoding="utf-8"))
    seat = next(s for s in record["seats"] if s["faction"] == side)
    scores = record.get("final_scores") or {}
    report: Dict[str, Any] = {
        "game_id": game["game_id"], "scenario_id": game["scenario_id"], "condition": game["condition"],
        "candidate_side": SIDES[side], "status": record["status"], "steps": record.get("steps"),
        "session": record.get("session"), "wall_seconds": round(record["timings_seconds"]["wall"], 1),
        "scores": {k: scores.get(k) for k in sorted(scores) if k.startswith(SIDES[side]) or k.endswith("total")},
        "candidate_margin": margin(scores, side) if scores else None,
        "control_condition": control_condition(game, side),
        "seat": {"actions_by_type": seat["actions_by_type"], "feedback_errors_by_code_and_type":
                 seat["feedback_errors_by_code_and_type"], "contract_errors": seat["contract_errors"],
                 "gate_rejections": seat["gate_rejections"], "replay_mismatches": seat["replay_mismatches"],
                 "replay_checks": seat["replay_checks"], "latency": latency(seat["latency_us"])},
    }
    other = next((s for s in record["seats"] if s["faction"] != side), None)
    if other is not None:
        report["opponent"] = {"policy": other["policy"], "actions_by_type": other["actions_by_type"],
                              "feedback_errors_by_code_and_type": other["feedback_errors_by_code_and_type"]}
    ctl = control(control_work, game["scenario_id"], report["control_condition"], side)
    if ctl["n"] and report["candidate_margin"] is not None:
        x = report["candidate_margin"]
        ctl["below"] = sum(1 for v in ctl["values"] if v < x)
        ctl["above"] = sum(1 for v in ctl["values"] if v > x)
    report["control"] = ctl
    capture_path = work / "capture" / f"{game['game_id']}.explore.json"
    if capture_path.exists():
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        report["addon_changes"] = capture["addon_changes"]
        report["addon_skips"] = capture["addon_skips"]
        report["addon_errors"] = len(capture["addon_errors"])
        report["indirect"] = {SIDES[c]: indirect_facts(capture, c) for c in (0, 1)}
        report["waiting_ground_units"] = capture["waiting_ground_units"]
        report["max_objective_commitment"] = capture["max_objective_commitment"]
        report["blood_last"] = capture["snapshots"][-1]["blood"] if capture["snapshots"] else None
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", required=True)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--control-work", type=Path,
                        default=REPO_ROOT / "local" / "evaluation" / sx.EXPERIMENT_NAME)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    card = json.loads((REPO_ROOT / "evaluation" / args.card / "manifest.json").read_text(encoding="utf-8"))
    if not xp.is_card(card):
        print("not an exploratory run card", file=sys.stderr)
        return 2
    work = args.work or REPO_ROOT / "local" / "evaluation" / args.card
    games = [game_report(card, g, work, args.control_work) for g in card["games"]]
    for g in games:
        ctl = g.get("control", {})
        print(f"{g['game_id']}: {g['status']} side={g.get('candidate_side')} margin={g.get('candidate_margin')} "
              f"control n={ctl.get('n')} mean={ctl.get('mean')} sd={ctl.get('sd')} below={ctl.get('below')} "
              f"above={ctl.get('above')} actions={g.get('seat', {}).get('actions_by_type')} "
              f"errors={g.get('seat', {}).get('feedback_errors_by_code_and_type')}")
    result = {"schema": SCHEMA, "card_id": args.card, "card_sha256": xp.digest(card), "track": xp.TRACK,
              "candidate": card["candidate"], "games": games,
              "note": "exploratory, directional and game-level; not a test of superiority"}
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    (work / "report.json").write_text(text, encoding="utf-8")
    if args.public:
        (REPO_ROOT / "evaluation" / args.card / "results.json").write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
