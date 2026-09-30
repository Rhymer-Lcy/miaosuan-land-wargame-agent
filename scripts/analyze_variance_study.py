"""Validate and analyse the registered baseline-v1 variance study from its private records.

    python scripts/analyze_variance_study.py [--check] [--allow-incomplete]

Reads the registered manifest, the reused historical records (verified against their pinned
digests), the new records and the persistent engine's session ledger, all under the git-ignored
``local/`` tree, and never modifies them. Validates the executed games against the registration
(identity, digests, sessions, ledger, completeness, no unregistered or replaced game), then writes
the public results ``evaluation/<study>/results.json``: aggregates and sanitized per-game metrics,
no instance-level record content. ``--check`` rebuilds and compares with the committed file;
``--allow-incomplete`` writes results for a partial study (a dry run), which validation marks.

Exit status: 0 valid and written (or identical with --check); 1 validation failed or mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import metrics  # noqa: E402
from miaosuan_agent.evaluation import variance_study as vs  # noqa: E402

import run_evaluation as rev  # noqa: E402

STUDY = REPO_ROOT / "evaluation" / vs.STUDY_NAME
LOCAL = REPO_ROOT / "local"
LEDGER = LOCAL / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"
SCHEMA = "miaosuan-variance-study-results/1"


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v) for v in value]
    return value


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ledger_sessions() -> Dict[str, Dict[str, Any]]:
    sessions: Dict[str, Dict[str, Any]] = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        entry = sessions.setdefault(event["session"], {})
        entry[event["event"]] = event
    return sessions


def validate(manifest: Mapping[str, Any], history: List[Dict[str, Any]], new: Dict[str, Dict[str, Any]],
             allow_incomplete: bool) -> Dict[str, Any]:
    problems: List[str] = []
    digest = mf.digest(manifest)
    if manifest["design_sha256"] != vs.design_digest(manifest):
        problems.append("design digest does not match the manifest")
    if manifest["schedule"] != vs.schedule(manifest["design_sha256"], vs.configurations(manifest)):
        problems.append("schedule does not follow the registered rule")
    source = rev.registered_policy_source(manifest)
    if source != vs.BASELINE_V1_SOURCE_SHA256:
        problems.append(f"policy source at analysis is {source}, not baseline-v1")
    scheduled = [entry["game_id"] for entry in manifest["schedule"]]
    games_dir = LOCAL / "evaluation" / vs.STUDY_NAME / "games"
    present = sorted(p.stem for p in games_dir.glob("*.json")) if games_dir.is_dir() else []
    unregistered = sorted(set(present) - set(scheduled))
    if unregistered:
        problems.append(f"records not in the schedule: {unregistered}")
    started_dir = LOCAL / "evaluation" / vs.STUDY_NAME / "started"
    started = sorted(p.name for p in started_dir.iterdir()) if started_dir.is_dir() else []
    started_without_record = sorted(set(started) - set(present))
    missing = [g for g in scheduled if g not in new]
    statuses = Counter(record.get("status") for record in new.values())
    commits = sorted({record["harness"]["commit"] for record in new.values()})
    identity = Counter()
    for game, record in new.items():
        harness = record["harness"]
        checks = {"game id": record["game_id"] == game, "policy digest": harness["policy_source_sha256"] ==
                  vs.BASELINE_V1_SOURCE_SHA256, "manifest digest": harness["manifest_sha256"] == digest,
                  "clean harness": harness["dirty"] is False, "python": record.get("python") == vs.RUNTIME["python"],
                  "engine version": record.get("engine_version") == manifest["engine"]["version"],
                  "state unchanged": record.get("session_close", {}).get("state_changed") is False,
                  "integrity": (record.get("session_close", {}).get("integrity") or {}).get("ok") is True,
                  "fields": not metrics.missing_fields(record, manifest["registered_seat_metrics"])}
        for name, passed in checks.items():
            if not passed:
                identity[name] += 1
    if identity:
        problems.append(f"new records failing identity checks: {dict(identity)}")
    sessions = ledger_sessions()
    numbers = sorted(int(s) for s in sessions)
    continuous = numbers == list(range(1, len(numbers) + 1))
    unclosed = sorted(s for s, e in sessions.items() if "session-close" not in e)
    changed = sorted(s for s, e in sessions.items() if e.get("session-close", {}).get("state_changed"))
    study_sessions = sorted(record["session"] for record in new.values())
    opened = {s: e["session-open"]["harness"] for s, e in sessions.items()
              if e.get("session-open", {}).get("harness", {}).get("manifest_sha256") == digest}
    by_game = Counter(harness.get("game_id") for harness in opened.values())
    replaced = sorted(g for g, n in by_game.items() if n > 1)
    attempts_without_record = sorted(s for s in opened if s not in set(study_sessions))
    ledger_mismatch = sorted(record["game_id"] for record in new.values()
                             if sessions.get(record["session"], {}).get("session-close", {}).get("outcome", {}).get(
                                 "game_id") != record["game_id"])
    if not continuous or unclosed:
        problems.append("engine ledger is not continuous or has an unclosed session")
    if changed != ["0001"]:
        problems.append(f"engine state changed in sessions {changed}")
    if replaced or ledger_mismatch or attempts_without_record:
        problems.append(f"ledger shows replaced, mismatched or unrecorded games: "
                        f"{replaced + ledger_mismatch + attempts_without_record}")
    if len(set(study_sessions)) != len(study_sessions):
        problems.append("two records share an engine session")
    if (missing or started_without_record) and not allow_incomplete:
        problems.append(f"{len(missing)} scheduled games have no record")
    history_ok = all(h["verified"] for h in history)
    if not history_ok:
        problems.append("a historical record does not match its pinned digest")
    return {
        "manifest_sha256": digest, "policy_source_at_analysis": source,
        "historical_records": len(history), "historical_records_verified": sum(h["verified"] for h in history),
        "scheduled": len(scheduled), "recorded": len(new), "missing": missing, "unregistered": unregistered,
        "started_without_record": started_without_record, "status": dict(sorted(statuses.items(), key=str)),
        "harness_commits": commits, "identity_failures": dict(identity),
        "sessions": {"first": study_sessions[0] if study_sessions else None,
                     "last": study_sessions[-1] if study_sessions else None, "count": len(study_sessions),
                     "contiguous": [int(s) for s in study_sessions] == list(
                         range(int(study_sessions[0]), int(study_sessions[0]) + len(study_sessions)))
                     if study_sessions else None},
        "ledger": {"sessions": len(numbers), "continuous": continuous, "unclosed": unclosed,
                   "state_changed_in": changed, "study_sessions_opened": len(opened),
                   "study_sessions_without_record": attempts_without_record, "replaced_games": replaced,
                   "mismatched_games": ledger_mismatch},
        "complete": not missing and not started_without_record and statuses.get("COMPLETED", 0) == len(scheduled),
        "problems": problems, "valid": not problems,
    }


def analyse(manifest: Mapping[str, Any], history_records: Dict[str, Dict[str, Any]], new: Dict[str, Dict[str, Any]],
            history_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    policy = manifest["policy_under_test"]
    position = {e["game_id"]: e["position"] for e in manifest["schedule"]}
    configs = [vs.config_id(*c) for c in vs.configurations(manifest)]
    records: Dict[str, List[Dict[str, Any]]] = {c: [] for c in configs}
    games = []
    for source, pool in (("historical", history_records), ("new", new)):
        for game, record in sorted(pool.items()):
            cid = vs.config_id(record["scenario_id"], record["condition"])
            computed = vs.game_metrics(record, policy)
            if cid in records:
                records[cid].append(record)
            games.append({"game_id": game, "source": source, "scenario_id": record["scenario_id"],
                          "condition": record["condition"], "repetition": record["repetition"],
                          "position": position.get(game), "session": record.get("session"),
                          "status": record.get("status"), **computed})
    active = [g for g in games if vs.config_id(g["scenario_id"], g["condition"]) in records]
    values: Dict[str, Dict[str, List[Any]]] = {m: {c: [] for c in configs} for m in vs.METRICS}
    by_rep: Dict[str, Dict[str, List[Any]]] = {m: {c: [] for c in configs} for m in vs.METRICS}
    for game in sorted(active, key=lambda g: g["repetition"]):
        cid = vs.config_id(game["scenario_id"], game["condition"])
        for metric in vs.METRICS:
            values[metric][cid].append(game["values"][metric])
            by_rep[metric][cid].append((game["repetition"], game["values"][metric]))
    summary = vs.summarize(values, vs.ACTIVE_CONDITIONS)
    facts: Dict[str, Dict[str, int]] = {}
    attributions: Dict[str, Dict[str, int]] = {}
    for game in active:
        cid = vs.config_id(game["scenario_id"], game["condition"])
        for item in game["facts"]:
            key = f"{item['action_type']}|{item['code']}|{item['message_class']}"
            facts.setdefault(key, {}).setdefault(cid, 0)
            facts[key][cid] += item["count"]
        for label, count in (game["attributions"] or {}).items():
            attributions.setdefault(label, {}).setdefault(game["source"], 0)
            attributions[label][game["source"]] += count
    temporal = {}
    for metric in vs.TEMPORAL:
        new_rows = {c: [(g["position"], g["repetition"], g["values"][metric]) for g in active
                        if g["source"] == "new" and vs.config_id(g["scenario_id"], g["condition"]) == c] for c in configs}
        old_rows = {c: [g["values"][metric] for g in active if g["source"] == "historical"
                        and vs.config_id(g["scenario_id"], g["condition"]) == c] for c in configs}
        temporal[metric] = vs.temporal(new_rows, old_rows, metric)
    comparison = {metric: vs.n2_versus_n10(by_rep[metric]) for metric in vs.MAJOR}
    wall = {c: sum(v for v in values["wall_seconds"][c] if v is not None) / max(1, len(
        [v for v in values["wall_seconds"][c] if v is not None])) for c in configs}
    scenario_of = {c: c.split(".")[0] for c in configs}
    force = {c: manifest["force_value_by_scenario"][scenario_of[c]] for c in configs}
    sizing = {}
    for metric, grid in manifest["effect_grid"].items():
        subset = {c: values[metric][c] for c in configs if c.split(".")[1] in grid["configurations"]}
        sizing[metric] = vs.sizing(subset, grid, force, metric)
    determinism = {c: vs.determinism(sorted(records[c], key=lambda r: r["repetition"]), policy) for c in configs}
    control = {}
    for game, record in sorted(history_records.items()):
        if record["condition"] == vs.CONTROL_CONDITION:
            control.setdefault(record["scenario_id"], []).append(record)
    control_summary = {s: {"repetitions": len(r), "distinct_state_chains": len({x["state_chain"] for x in r}),
                           "final_scores_equal": all(x["final_scores"] == r[0]["final_scores"] for x in r)}
                       for s, r in sorted(control.items())}
    slow_indices = Counter(i for g in active for i in g["slow_decision_indices"])
    for game in games:
        game.pop("slow_decision_indices")
    new_games = [g for g in active if g["source"] == "new"]
    return {
        "games": games,
        "configurations": summary,
        "refusal_facts_by_configuration": facts,
        "refusal_attributions": attributions,
        "facts_complete": {"historical": all(g["facts_complete"] for g in active if g["source"] == "historical"),
                           "new": all(g["facts_complete"] for g in new_games)},
        "margin_fields_consistent": all(g["margin_fields_consistent"] is not False for g in games),
        "determinism": determinism,
        "control_c4": control_summary,
        "temporal": temporal,
        "n2_versus_n10": comparison,
        "sizing": sizing,
        "cost": vs.cost(wall),
        "default_repetitions": vs.default_repetitions(sizing[vs.DEFAULT_RULE_METRIC]),
        "latency_outliers": {"decisions_over_100ms_by_index": {str(k): v for k, v in sorted(slow_indices.items())},
                             "games_with_a_decision_over_400ms": sum(1 for g in active
                                                                     if g["values"]["decisions_over_400ms"])},
        "execution": execution(new, new_games),
    }


def execution(new: Mapping[str, Mapping[str, Any]], new_games: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Host-clock span of the new games (the host clock is not corrected) and their summed wall time."""
    started_dir = LOCAL / "evaluation" / vs.STUDY_NAME / "started"
    starts = sorted(p.read_text(encoding="utf-8").strip() for p in started_dir.iterdir()) if started_dir.is_dir() else []
    finishes = sorted(r.get("host_clock_finished", {}).get("host_clock_utc", "") for r in new.values())
    return {"host_clock_first_start": starts[0] if starts else None,
            "host_clock_last_finish": finishes[-1] if finishes else None,
            "new_games_wall_seconds": sum(g["values"]["wall_seconds"] or 0 for g in new_games)}


def build(allow_incomplete: bool) -> Dict[str, Any]:
    manifest = load_json(STUDY / "manifest.json")
    history_rows = manifest["historical_records"]["records"]
    source = manifest["historical_records"]["source_evaluation"]
    history_records, history = {}, []
    for row in history_rows:
        path = LOCAL / "evaluation" / source / "games" / f"{row['game_id']}.json"
        data = path.read_bytes() if path.is_file() else b""
        verified = hashlib.sha256(data).hexdigest() == row["record_sha256"]
        history.append({"game_id": row["game_id"], "verified": verified})
        if verified:
            history_records[row["game_id"]] = json.loads(data.decode("utf-8"))
    new = {}
    for entry in manifest["schedule"]:
        path = LOCAL / "evaluation" / vs.STUDY_NAME / "games" / f"{entry['game_id']}.json"
        if path.is_file():
            new[entry["game_id"]] = load_json(path)
    validation = validate(manifest, history, new, allow_incomplete)
    result = {"schema": SCHEMA, "study_id": manifest["study_id"], "validation": validation}
    result.update(analyse(manifest, history_records, new, history_rows))
    return rounded(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed results instead of writing")
    parser.add_argument("--allow-incomplete", action="store_true", help="dry run on a partial study")
    parser.add_argument("--out", type=Path, default=STUDY / "results.json")
    args = parser.parse_args()
    result = build(args.allow_incomplete)
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    validation = result["validation"]
    print(f"records {validation['recorded']}/{validation['scheduled']}; historical verified "
          f"{validation['historical_records_verified']}/{validation['historical_records']}; complete "
          f"{validation['complete']}; valid {validation['valid']}")
    for problem in validation["problems"]:
        print("PROBLEM", problem)
    if args.check:
        same = args.out.exists() and args.out.read_text(encoding="utf-8") == text
        print("results identical" if same else "MISMATCH with the committed results")
        return 0 if same and validation["valid"] else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0 if validation["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
