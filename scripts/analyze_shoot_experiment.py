"""Validate and analyse the registered shoot-target-reservation experiment from its private records.

    python scripts/analyze_shoot_experiment.py [--check] [--allow-incomplete]

Reads the registered manifest, the game records of both groups and the persistent engine's session ledger
(all under the git-ignored ``local/`` tree, never modified) and the registration push record
(``registration-push.json``: the registration commit, the UTC time it was verified on the public remote, and
the offset of the host clock). Validates the executed games against the registration (identity, digests per
group, sessions, ledger, completeness, no unregistered or replaced game), computes every registered analysis
and applies P1-P10 mechanically. Writes ``evaluation/<experiment>/results.json`` with aggregates and sanitized
per-game metrics only. ``--check`` rebuilds and compares with the committed file; ``--allow-incomplete``
analyses a partial run (a dry run), which validation marks.

Exit status: 0 valid and written (or identical with --check); 1 validation failed or mismatch.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import refusals  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation import stats  # noqa: E402

import run_evaluation as rev  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME
LOCAL = REPO_ROOT / "local"
LEDGER = LOCAL / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"
PUSH = DIRECTORY / "registration-push.json"
SCHEMA = "miaosuan-ab-experiment-results/1"
PYTHON = "3.10.20"
DESCRIPTIVE_CONTRASTS = {"refusals_per_1000": "C1 C2 C3", "code_203_per_1000": "C1 C2 C3",
                         "code_516_per_1000_shots": "C1 C2 C3", "shots": "C1 C2 C3", "active_step_rate": "C1 C2 C3",
                         "no_op_rate": "C1 C2 C3", "margin_c1": "C1"}
TOTALS = ("unit_actions", "shots", "moves", "occupations", "code_516", "code_203", "code_404", "code_1804", "refusals",
          "gate_rejections", "contract_errors", "replay_checks", "replay_mismatches", "duplicate_shoot_target_commands",
          "duplicate_shoot_target_steps", "unique_targets_engaged", "steps_with_shot", "reserved_target_exclusions",
          "alternate_target_redirections", "fallback_occupy", "fallback_move", "fallback_none",
          "unchanged_with_exclusion", "excluded_options", "code_516_repeat_fire", "code_516_single_fire",
          "code_516_no_evidence", "duplicate_occupation_commands", "suppressions", "decisions_over_100ms",
          "decisions_over_400ms", "decisions_over_1000ms")


def work() -> Path:
    """The private work directory of the experiment (derived from LOCAL at call time)."""
    return LOCAL / "evaluation" / sx.EXPERIMENT_NAME


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
        if line.strip():
            event = json.loads(line)
            sessions.setdefault(event["session"], {})[event["event"]] = event
    return sessions


def parse_utc(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def validate(manifest: Mapping[str, Any], records: Dict[str, Dict[str, Any]], allow_incomplete: bool) -> Dict[str, Any]:
    problems: List[str] = []
    digest = mf.digest(manifest)
    if manifest["design_sha256"] != sx.design_digest(manifest):
        problems.append("design digest does not match the manifest")
    if manifest["schedule"] != sx.schedule(manifest["design_sha256"], sx.configurations(manifest)):
        problems.append("schedule does not follow the registered rule")
    sources = {g: rev.registered_source_digest(manifest["groups"][g]["policy_source"]) for g in sx.GROUPS}
    for group, source in sources.items():
        if source != manifest["groups"][group]["policy_source"]["sha256"]:
            problems.append(f"group {group}'s policy source at analysis is {source}, not the registered one")
    if sources["B"] != sx.RUNTIME_R1_SOURCE_SHA256:
        problems.append("group B is not baseline-v1-runtime-r1 at analysis")
    groups = {e["game_id"]: e["group"] for e in manifest["schedule"]}
    scheduled = list(groups)
    present = sorted(p.stem for p in (work() / "games").glob("*.json")) if (work() / "games").is_dir() else []
    unregistered = sorted(set(present) - set(scheduled))
    if unregistered:
        problems.append(f"records not in the schedule: {unregistered}")
    started_dir = work() / "started"
    started = sorted(p.name for p in started_dir.iterdir()) if started_dir.is_dir() else []
    started_without_record = sorted(set(started) - set(present))
    missing = [g for g in scheduled if g not in records]
    statuses = {g: dict(Counter(r.get("status") for game, r in records.items() if groups[game] == g)) for g in sx.GROUPS}
    commits = sorted({r["harness"]["commit"] for r in records.values()})
    identity = Counter()
    for game, record in records.items():
        harness, group = record["harness"], groups[game]
        policy = manifest["groups"][group]["policy"]
        seats = [s for s in record.get("seats", []) if s["policy"] == policy]
        checks = {"game id": record["game_id"] == game, "group": harness.get("group") == group,
                  "policy digest": harness["policy_source_sha256"] == manifest["groups"][group]["policy_source"]["sha256"],
                  "manifest digest": harness["manifest_sha256"] == digest, "clean harness": harness["dirty"] is False,
                  "python": record.get("python") == PYTHON,
                  "engine version": record.get("engine_version") == manifest["engine"]["version"],
                  "state unchanged": record.get("session_close", {}).get("state_changed") is False,
                  "home unchanged": record.get("session_close", {}).get("home_changed") is False,
                  "integrity": (record.get("session_close", {}).get("integrity") or {}).get("ok") is True,
                  "policy seats": bool(seats), "fields": all(name in s for s in seats for name in sx.SEAT_FIELDS)}
        for name, passed in checks.items():
            if not passed:
                identity[name] += 1
    if identity:
        problems.append(f"records failing identity checks: {dict(identity)}")
    if len(commits) > 1:
        problems.append(f"records come from several harness commits: {commits}")
    sessions_used = sorted(r["session"] for r in records.values())
    last = max((int(s) for s in sessions_used), default=None)
    sessions = {s: e for s, e in ledger_sessions().items() if last is None or int(s) <= last}
    numbers = sorted(int(s) for s in sessions)
    continuous = numbers == list(range(1, len(numbers) + 1))
    unclosed = sorted(s for s, e in sessions.items() if "session-close" not in e)
    changed = sorted(s for s, e in sessions.items() if e.get("session-close", {}).get("state_changed"))
    opened = {s: e["session-open"]["harness"] for s, e in sessions.items()
              if e.get("session-open", {}).get("harness", {}).get("manifest_sha256") == digest}
    by_game = Counter(h.get("game_id") for h in opened.values())
    replaced = sorted(g for g, n in by_game.items() if n > 1)
    attempts_without_record = sorted(s for s in opened if s not in set(sessions_used))
    ledger_mismatch = sorted(r["game_id"] for r in records.values()
                             if sessions.get(r["session"], {}).get("session-close", {}).get("outcome", {}).get("game_id")
                             != r["game_id"])
    if not continuous or unclosed:
        problems.append("engine ledger is not continuous or has an unclosed session")
    if changed != ["0001"]:
        problems.append(f"engine state changed in sessions {changed}")
    if replaced or ledger_mismatch or attempts_without_record:
        problems.append(f"ledger shows replaced, mismatched or unrecorded games: "
                        f"{replaced + ledger_mismatch + attempts_without_record}")
    if len(set(sessions_used)) != len(sessions_used):
        problems.append("two records share an engine session")
    if (missing or started_without_record) and not allow_incomplete:
        problems.append(f"{len(missing)} scheduled games have no record")
    ordering = registration_order(started_dir, commits)
    if not ordering["verified"]:
        problems.append(f"registration order not verified: {ordering['reason']}")
    return {
        "manifest_sha256": digest, "policy_sources_at_analysis": sources, "scheduled": len(scheduled),
        "recorded": len(records), "missing": missing, "unregistered": unregistered,
        "started_without_record": started_without_record, "status_by_group": statuses, "harness_commits": commits,
        "identity_failures": dict(identity),
        "sessions": {"first": sessions_used[0] if sessions_used else None,
                     "last": sessions_used[-1] if sessions_used else None, "count": len(sessions_used),
                     "contiguous": [int(s) for s in sessions_used] == list(range(int(sessions_used[0]),
                                                                                int(sessions_used[0]) + len(sessions_used)))
                     if sessions_used else None},
        "ledger": {"sessions": len(numbers), "continuous": continuous, "unclosed": unclosed, "state_changed_in": changed,
                   "experiment_sessions_opened": len(opened), "experiment_sessions_without_record": attempts_without_record,
                   "replaced_games": replaced, "mismatched_games": ledger_mismatch},
        "registration_order": ordering,
        "complete": not missing and not started_without_record,
        "problems": problems, "valid": not problems,
    }


def registration_order(started_dir: Path, commits: List[str]) -> Dict[str, Any]:
    """The registration commit was verified on the public remote before the first game started."""
    if not PUSH.exists():
        return {"verified": False, "reason": "no registration push record"}
    push = load_json(PUSH)
    starts = sorted(p.read_text(encoding="utf-8").strip() for p in started_dir.iterdir()) if started_dir.is_dir() else []
    if not starts:
        return {"verified": False, "reason": "no game started"}
    first_host = parse_utc(starts[0])
    first_true = first_host - dt.timedelta(seconds=push["host_clock_ahead_seconds"])
    pushed = parse_utc(push["verified_on_remote_utc"])
    harness_is_registration = bool(commits) and all(c.startswith(push["registration_commit"]) or
                                                    push["registration_commit"].startswith(c) for c in commits)
    verified = pushed < first_true and harness_is_registration
    return {"verified": verified, "registration_commit": push["registration_commit"],
            "verified_on_remote_utc": push["verified_on_remote_utc"], "first_game_host_clock_utc": starts[0],
            "host_clock_ahead_seconds": push["host_clock_ahead_seconds"],
            "first_game_utc_corrected": first_true.isoformat(timespec="seconds"),
            "minutes_between": round((first_true - pushed).total_seconds() / 60.0, 1),
            "harness_commit_is_registration": harness_is_registration,
            "reason": None if verified else "push not before the first game, or the harness commit differs"}


def describe_group(values: Mapping[str, Mapping[str, List[Any]]], configs: List[str]) -> Dict[str, Any]:
    result = {}
    for metric in sorted(values):
        per_config = {c: [v for v in values[metric][c] if v is not None] for c in configs}
        entry = {"configurations": {c: dict(stats.describe(g), missing=len(values[metric][c]) - len(g),
                                            constant=len(g) >= 2 and max(g) == min(g)) for c, g in per_config.items()}}
        for condition in sx.ACTIVE_CONDITIONS:
            means = [sum(g) / len(g) for c, g in per_config.items() if c.endswith("." + condition) and g]
            entry[condition] = sum(means) / len(means) if means else None
        means = [sum(g) / len(g) for g in per_config.values() if g]
        entry["suite"] = sum(means) / len(means) if means else None
        result[metric] = entry
    return result


def analyse(manifest: Mapping[str, Any], records: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    entries = {e["game_id"]: e for e in manifest["schedule"]}
    configs = [sx.config_id(*c) for c in sx.configurations(manifest)]
    games, latencies = [], {g: [] for g in sx.GROUPS}
    values: Dict[str, Dict[str, Dict[str, List[Any]]]] = {g: {} for g in sx.GROUPS}
    facts: Dict[str, Counter] = {g: Counter() for g in sx.GROUPS}
    attributions: Dict[str, Counter] = {g: Counter() for g in sx.GROUPS}
    slow: List[Dict[str, Any]] = []
    status: Dict[str, Counter] = {g: Counter() for g in sx.GROUPS}
    deployment = {g: 0 for g in sx.GROUPS}
    for game in sorted(records, key=lambda g: entries[g]["position"]):
        record, entry = records[game], entries[game]
        group, cid = entry["group"], sx.config_id(entry["scenario_id"], entry["condition"])
        policy = manifest["groups"][group]["policy"]
        computed = sx.game_metrics(record, policy)
        status[group][record.get("status")] += 1
        deployment[group] += bool(record.get("deployment_ended"))
        for metric, value in computed["values"].items():
            values[group].setdefault(metric, {c: [] for c in configs})[cid].append(value)
        values[group].setdefault("margin_c1", {c: [] for c in configs})[cid].append(
            computed["values"]["margin"] if entry["condition"] == "C1" else None)
        for item in computed["facts"]:
            facts[group][(item["action_type"], item["code"], item["message_class"])] += item["count"]
        for label, count in (computed["attributions"] or {}).items():
            attributions[group][label] += count
        first_play = next((t["step"] for t in record.get("stage_transitions", []) if t["stage"] == 2), None)
        for seat in record.get("seats", []):
            if seat["policy"] != policy:
                continue
            latencies[group].extend(seat["latency_us"])
            for index, value in enumerate(seat["latency_us"]):
                if value > 1_000_000:
                    slow.append({"game_id": game, "group": group, "seat": seat["seat"], "decision": index,
                                 "ms": value / 1000.0, "first_play_decision": index == first_play})
        games.append({"game_id": game, "group": group, "scenario_id": entry["scenario_id"], "condition": entry["condition"],
                      "repetition": entry["repetition"], "position": entry["position"], "session": record.get("session"),
                      "status": record.get("status"), "values": computed["values"],
                      "facts": computed["facts"], "margin_fields_consistent": computed["margin_fields_consistent"]})
    primary = sx.contrast(values["B"][sx.PRIMARY_METRIC], values["C"][sx.PRIMARY_METRIC], sx.PRIMARY_METRIC)
    c2c3 = [c for c in configs if c.split(".")[1] in ("C2", "C3")]
    margin = sx.contrast({c: values["B"][sx.MARGIN_METRIC][c] for c in c2c3},
                         {c: values["C"][sx.MARGIN_METRIC][c] for c in c2c3}, sx.MARGIN_METRIC)
    descriptive = {}
    for metric, conditions in DESCRIPTIVE_CONTRASTS.items():
        subset = [c for c in configs if c.split(".")[1] in conditions.split()]
        descriptive[metric] = sx.contrast({c: values["B"][metric][c] for c in subset},
                                          {c: values["C"][metric][c] for c in subset}, metric)
    totals = {g: {name: sum(v for c in configs for v in values[g][name][c] if v is not None) for name in TOTALS}
              for g in sx.GROUPS}
    known = {tuple(c) for c in manifest["known_refusal_classes"]}
    new_classes = sorted([list(k) for k in facts["C"] if k not in known and k not in facts["B"]], key=str)
    classes = {g: [{"action_type": k[0], "code": k[1], "message_class": k[2], "count": n}
                   for k, n in sorted(facts[g].items(), key=lambda kv: str(kv[0]))] for g in sx.GROUPS}
    return {
        "games": games,
        "descriptive": {g: describe_group(values[g], configs) for g in sx.GROUPS},
        "primary": dict(primary, verdict=sx.primary_verdict(primary)),
        "non_inferiority": dict(margin, verdict=sx.non_inferiority_verdict(margin)),
        "descriptive_contrasts": descriptive,
        "totals": totals,
        "status": {g: dict(status[g]) for g in sx.GROUPS},
        "deployment_completed": deployment,
        "refusal_classes": classes,
        "refusal_classes_new_in_candidate": new_classes,
        "refusal_attributions": {g: dict(sorted(attributions[g].items())) for g in sx.GROUPS},
        "latency": {g: sx.latency_summary(latencies[g]) for g in sx.GROUPS},
        "decisions_over_1s": slow,
        "margin_fields_consistent": all(g["margin_fields_consistent"] is not False for g in games),
    }


def checks(manifest: Mapping[str, Any], validation: Mapping[str, Any], analysis: Mapping[str, Any]) -> Dict[str, Any]:
    b_files, c_files = (manifest["groups"][g]["policy_source"]["files"] for g in ("B", "C"))
    added = sorted(set(c_files) - set(b_files))
    counterfactual = manifest["counterfactual_replay"]
    cf_path = REPO_ROOT / counterfactual["file"]
    cf_ok = cf_path.exists() and hashlib.sha256(cf_path.read_bytes()).hexdigest() == counterfactual["sha256"]
    totals, status = analysis["totals"], analysis["status"]
    not_completed = {g: sum(n for s, n in status[g].items() if s != "COMPLETED") for g in sx.GROUPS}
    return {
        "P1": {"pass": set(b_files) <= set(c_files) and added == [sx.CANDIDATE_FILE] and cf_ok
               and counterfactual["unexplained_states"] == 0 and counterfactual["class_E"] == 0
               and validation["policy_sources_at_analysis"]["C"] == manifest["groups"]["C"]["policy_source"]["sha256"],
               "detail": {"added_files": added, "counterfactual_pinned_and_unchanged": cf_ok,
                          "unexplained_states": counterfactual["unexplained_states"], "class_E": counterfactual["class_E"]}},
        "P2": {"pass": totals["C"]["duplicate_shoot_target_commands"] == 0 and totals["C"]["replay_mismatches"] == 0,
               "detail": {"duplicate_shoot_target_commands": totals["C"]["duplicate_shoot_target_commands"],
                          "replay_mismatches": totals["C"]["replay_mismatches"], "replay_checks": totals["C"]["replay_checks"]}},
        "P3": {"pass": not validation["missing"] and not validation["started_without_record"]
               and not_completed["C"] <= not_completed["B"] and totals["C"]["contract_errors"] == 0,
               "detail": {"missing": len(validation["missing"]), "not_completed": not_completed,
                          "contract_errors_C": totals["C"]["contract_errors"]}},
        "P4": {"pass": totals["C"]["gate_rejections"] == 0, "detail": {"gate_rejections_C": totals["C"]["gate_rejections"]}},
        "P5": {"pass": totals["C"]["code_1804"] == 0 and totals["C"]["duplicate_occupation_commands"] == 0,
               "detail": {"code_1804_C": totals["C"]["code_1804"],
                          "duplicate_occupation_commands_C": totals["C"]["duplicate_occupation_commands"]}},
        "P6": {"pass": analysis["primary"]["verdict"]["pass"], "detail": analysis["primary"]["verdict"]},
        "P7": {"pass": analysis["non_inferiority"]["verdict"]["pass"], "detail": analysis["non_inferiority"]["verdict"]},
        "P8": {"pass": not analysis["refusal_classes_new_in_candidate"],
               "detail": {"new_classes": analysis["refusal_classes_new_in_candidate"]}},
        "P9": {"pass": not validation["identity_failures"] and len(validation["harness_commits"]) == 1,
               "detail": {"identity_failures": validation["identity_failures"],
                          "harness_commits": validation["harness_commits"]}},
        "P10": {"pass": validation["valid"] and validation["registration_order"]["verified"],
                "detail": {"validation_valid": validation["valid"],
                           "registration_order_verified": validation["registration_order"]["verified"]}},
    }


def build(allow_incomplete: bool, manifest: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    manifest = manifest if manifest is not None else load_json(DIRECTORY / "manifest.json")
    records = {}
    for entry in manifest["schedule"]:
        path = work() / "games" / f"{entry['game_id']}.json"
        if path.is_file():
            records[entry["game_id"]] = load_json(path)
    validation = validate(manifest, records, allow_incomplete)
    analysis = analyse(manifest, records)
    result = {"schema": SCHEMA, "experiment_id": manifest["experiment_id"], "validation": validation}
    result.update(analysis)
    result["promotion"] = sx.promotion(checks(manifest, validation, analysis))
    return rounded(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed results instead of writing")
    parser.add_argument("--allow-incomplete", action="store_true", help="dry run on a partial experiment")
    parser.add_argument("--out", type=Path, default=DIRECTORY / "results.json")
    args = parser.parse_args()
    result = build(args.allow_incomplete)
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    validation = result["validation"]
    print(f"records {validation['recorded']}/{validation['scheduled']}; complete {validation['complete']}; "
          f"valid {validation['valid']}; disposition {result['promotion']['disposition']}")
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
