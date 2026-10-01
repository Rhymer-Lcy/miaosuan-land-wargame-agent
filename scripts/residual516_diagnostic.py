"""Read-only checks and analysis of the registered residual-516 diagnostic.

    PYTHON scripts/residual516_diagnostic.py preflight          # shared-server courtesy check before the run
    PYTHON scripts/residual516_diagnostic.py snapshot --label before|after
    PYTHON scripts/residual516_diagnostic.py analyze [--check]

The games themselves run through ``scripts/run_evaluation.sh --plan residual516 --workers 32``. ``analyze`` reads
the private records, capture logs and snapshot windows under ``local/evaluation/<diagnostic>/``, checks integrity
and instrumentation, builds a factual record of every code-516 refusal of the policy seat, classifies it with the
registered rules, counts same-target fire across seats, and writes the private analysis (``analysis/facts.json``)
and the sanitized public ``evaluation/<diagnostic>/results.json``; ``--check`` regenerates both and compares them
byte for byte. Nothing here starts the engine or opens an engine session.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import pickle
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install as ei  # noqa: E402
from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import digest as trace_digest  # noqa: E402
from miaosuan_agent.evaluation import concurrency as cq  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import runtime_threads as rt  # noqa: E402
from miaosuan_agent.evaluation.execution import RUNTIMES  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / rd.DIAGNOSTIC_ID
MANIFEST = DIRECTORY / "manifest.json"
PUBLIC = DIRECTORY / "results.json"
WORK = REPO_ROOT / "local" / "evaluation" / rd.DIAGNOSTIC_ID
PRIVATE = WORK / "analysis" / "facts.json"
INSTALL = REPO_ROOT / "local" / "engines" / "sdk-4.1.0"
#: Unit sub-type labels as documented in the SDK observation notes (type 1 infantry, 2 vehicle, 3 aircraft).
SUB_TYPES = {0: "tank", 1: "infantry fighting vehicle", 2: "infantry", 3: "artillery", 4: "unmanned ground vehicle",
             5: "unmanned aerial vehicle", 6: "helicopter", 7: "loitering munition"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def label(unit_class: Optional[List[Any]]) -> str:
    if not unit_class or unit_class[2] is None:
        return "unknown"
    side = {0: "red", 1: "blue"}.get(unit_class[0], "?")
    return f"{side} {SUB_TYPES.get(unit_class[2], f'sub-type {unit_class[2]}')}"


# ----------------------------------------------------------------------------------------------
# preflight and snapshots


def cmd_preflight(args: argparse.Namespace) -> int:
    qc = load_script("qualify_concurrency")
    plan = load(REPO_ROOT / "evaluation" / cq.PLAN_ID / "plan.json")
    result = qc.precheck(rd.WORKERS, plan)
    out = WORK / "prechecks" / f"precheck-{stamp()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as handle:
        handle.write(text({"workers": rd.WORKERS, **result}))
    print(f"{'OK' if result['ok'] else 'BUSY'}: {out.relative_to(REPO_ROOT)}")
    return 0 if result["ok"] else 3


def cmd_snapshot(args: argparse.Namespace) -> int:
    qc = load_script("qualify_concurrency")
    install = ei.EngineInstall(INSTALL.resolve())
    with ei.exclusive_window(install):
        snap = qc.snapshot(install)
    out = WORK / "snapshots" / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as handle:
        handle.write(text(snap))
    print(f"wrote {out.relative_to(REPO_ROOT)}: sessions opened {snap['opened']}, unclosed {snap['unclosed']}")
    return 0


# ----------------------------------------------------------------------------------------------
# integrity


def chain(digests: List[str]) -> str:
    h = hashlib.sha256()
    for item in digests:
        h.update(item.encode("ascii"))
    return h.hexdigest()


def integrity(manifest: Mapping[str, Any], records: Mapping[str, Dict[str, Any]], ledger: List[Dict[str, Any]],
              captures: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    games = [g["game_id"] for g in manifest["games"]]
    problems: List[str] = []
    if sorted(records) != sorted(games):
        problems.append(f"records for {len(records)} of {len(games)} registered games")
    started = sorted(p.name for p in (WORK / "started").iterdir()) if (WORK / "started").exists() else []
    if started != sorted(games):
        problems.append(f"start markers for {len(started)} games")
    events: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for event in ledger:
        events.setdefault(event["session"], {}).setdefault(event["event"], []).append(event)
    digest = mf.digest(manifest)
    execution = manifest["execution"]
    env = dict(RUNTIMES[execution["runtime"]])
    states, harness_commits = set(), set()
    for game, record in sorted(records.items()):
        harness = record["harness"]
        harness_commits.add(harness["commit"])
        if record["status"] != "COMPLETED":
            problems.append(f"{game}: {record['status']}")
        if (harness["manifest_sha256"], harness["policy_source_sha256"]) != (digest, rd.BASELINE_V2_SOURCE_SHA256):
            problems.append(f"{game}: harness digests differ from the registration")
        if harness.get("dirty"):
            problems.append(f"{game}: dirty harness")
        if (harness.get("runtime"), harness.get("thread_env")) != (execution["runtime"], env):
            problems.append(f"{game}: runtime {harness.get('runtime')} {harness.get('thread_env')}")
        run = harness.get("execution") or {}
        if (run.get("mode"), run.get("workers"), run.get("scheduler")) != ("shared", execution["workers"], execution["scheduler"]):
            problems.append(f"{game}: execution {run}")
        if record.get("observer_errors"):
            problems.append(f"{game}: observer errors {record['observer_errors'][:2]}")
        if not (WORK / "logs" / f"{game}.log").exists():
            problems.append(f"{game}: no log")
        session = events.get(record["session"], {})
        opens, closes = session.get("session-open", []), session.get("session-close", [])
        if len(opens) != 1 or len(closes) != 1 or session.get("session-recovered"):
            problems.append(f"{game}: session {record['session']} is not opened and closed exactly once")
        else:
            if opens[0]["harness"].get("game_id") != game or opens[0].get("concurrency", {}).get("mode") != "shared":
                problems.append(f"{game}: session {record['session']} does not name this shared game")
            if closes[0].get("state_changed") or closes[0].get("home_changed") or not closes[0]["integrity"]["ok"]:
                problems.append(f"{game}: state, home or integrity changed in its session")
            states.add(json.dumps(opens[0]["state"], sort_keys=True))
            states.add(json.dumps(closes[0]["state"], sort_keys=True))
        capture = captures.get(game)
        summary = record.get("capture") or {}
        if capture is None:
            problems.append(f"{game}: no capture")
            continue
        if (capture["compact_sha256"], capture["windows_sha256"]) != (summary.get("compact_sha256"), summary.get("windows_sha256")):
            problems.append(f"{game}: capture files differ from the digests in its record")
        steps = capture["compact"]["steps"]
        if [e["k"] for e in steps] != list(range(record["steps"])):
            problems.append(f"{game}: capture covers {len(steps)} of {record['steps']} steps")
        for seat in record["seats"]:
            if chain([e["traces"][str(seat["seat"])] for e in steps]) != seat["trace_chain"]:
                problems.append(f"{game}: capture trace chain of seat {seat['seat']} differs from the record's")
    sessions = sorted(int(r["session"]) for r in records.values())
    if sessions and sessions != list(range(sessions[0], sessions[0] + len(sessions))):
        problems.append("sessions are not consecutive")
    if len(states) > 1:
        problems.append("the engine state differs between sessions")
    pools = [load(p) for p in sorted((WORK / "pool").glob("run-*.json"))] if (WORK / "pool").exists() else []
    leftovers = 0
    for pool in pools:
        if (pool["workers"], pool["runtime"], pool["thread_env"], pool["scheduler"]) != (
                execution["workers"], execution["runtime"], env, execution["scheduler"]):
            problems.append("a pool run differs from the registered execution")
        for result in pool["results"]:
            leftovers += len(result.get("leftover_processes") or [])
            if result["exit_code"] != 0 or result["timed_out"] or result["cancelled"]:
                problems.append(f"{result['game_id']}: pool exit {result['exit_code']}")
    if not pools:
        problems.append("no pool run file")
    if leftovers:
        problems.append(f"{leftovers} leftover processes")
    return {"pass": not problems, "problems": problems, "records": len(records), "sessions": sessions,
            "states": len(states), "pool_runs": len(pools), "leftover_processes": leftovers,
            "harness_commits": sorted(harness_commits)}


# ----------------------------------------------------------------------------------------------
# instrumentation


def offline_replay(manifest: Mapping[str, Any], windows: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    """A fresh baseline-v2 policy recomputes every captured snapshot's decision from its observation and memory."""
    scenario = manifest["scenarios"][0]
    inputs = sdk_data.load_inputs(WORK / "data" / scenario["scenario_id"] / "Data", scenario["scenario_id"],
                                  scenario["map_id"])
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    checked, mismatches = 0, []
    for game, data in sorted(windows.items()):
        snapshots: Dict[int, Dict[str, Any]] = {}
        for event in data["events"]:
            for snap in event["window"]:
                snapshots[snap["k"]] = snap
        for snap in data["samples"]:
            snapshots[snap["k"]] = snap
        for k, snap in sorted(snapshots.items()):
            for seat, entry in sorted(snap["seats"].items()):
                decision = ShootReservationPolicy(costs).decide(
                    Observation.from_raw(pickle.loads(entry["observation"]), Origin.ENGINE), seat, entry["faction"],
                    pickle.loads(entry["memory"]))
                checked += 1
                actions = rd.plain([dict(a) for a in decision.actions])
                if actions != entry["actions"] or trace_digest(decision.trace) != entry["trace"]:
                    mismatches.append({"game": game, "k": k, "seat": seat})
    return {"decisions": checked, "mismatches": mismatches}


def instrumentation(manifest: Mapping[str, Any], records: Mapping[str, Dict[str, Any]],
                    windows: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    policy = manifest["policy_under_test"]
    comparisons = {game: cq.compare(record, manifest["reference"]) for game, record in sorted(records.items())}
    seats = [s for r in records.values() for s in r["seats"] if s["policy"] == policy]
    replay = offline_replay(manifest, windows)
    observer = [r["capture"]["observer_seconds"] for r in records.values() if r.get("capture")]
    walls = [r["timings_seconds"]["wall"] for r in records.values()]
    shares = [r["capture"]["observer_seconds"] / r["timings_seconds"]["wall"] for r in records.values() if r.get("capture")]
    errors = sum(len(r.get("observer_errors") or []) for r in records.values())
    checks = {"prefix": all(c["pass"] for c in comparisons.values()) and len(comparisons) == len(manifest["games"]),
              "in_game_replay": sum(s["replay_mismatches"] for s in seats) == 0 and sum(s["replay_checks"] for s in seats) > 0,
              "offline_replay": replay["decisions"] > 0 and not replay["mismatches"],
              "observer_errors": errors == 0 and len(observer) == len(records)}
    return {"pass": all(checks.values()) and bool(records), "checks": checks,
            "prefix_equal": sum(1 for c in comparisons.values() if c["pass"]), "games": len(comparisons),
            "prefix_steps": manifest["reference"]["state_prefix_steps"],
            "in_game_replay_checks": sum(s["replay_checks"] for s in seats),
            "in_game_replay_mismatches": sum(s["replay_mismatches"] for s in seats),
            "offline_decisions": replay["decisions"], "offline_mismatches": len(replay["mismatches"]),
            "observer_errors": errors,
            "observer_seconds": {"median": statistics.median(observer), "max": max(observer), "total": sum(observer)}
            if observer else None,
            "observer_share_of_wall": {"median": statistics.median(shares), "max": max(shares)} if shares else None,
            "game_wall_seconds": {"median": statistics.median(walls), "max": max(walls)} if walls else None,
            "private": {"comparisons": comparisons, "offline_mismatches": replay["mismatches"]}}


# ----------------------------------------------------------------------------------------------
# events, classification, cross-seat fire


def feedback_order(steps: List[Dict[str, Any]]) -> Dict[str, int]:
    """How the engine's feedback relates to the submitted batch, over steps with at least two actions."""
    counts = collections.Counter()
    for entry in steps:
        batch = entry["batch"]
        if len(batch) < 2:
            continue
        positions = []
        for f in entry["feedback"]:
            message = f.get("message") or {}
            match = next((item["i"] for item in batch if item["i"] not in positions
                          and rd.refusals.same_action(message, item["action"]) and message.get("actor") == item["seat"]), None)
            if match is not None:
                positions.append(match)
        counts["steps"] += 1
        counts["every_action_echoed" if len(positions) == len(batch) else "not_every_action_echoed"] += 1
        counts["echo_in_batch_order" if positions == sorted(positions) else "echo_out_of_batch_order"] += 1
    return dict(sorted(counts.items()))


def judge_steps(steps: List[Dict[str, Any]]) -> Dict[str, int]:
    """The cur_step of each new judge_info record against the engine step of the observation before the step."""
    counts = collections.Counter()
    for entry in steps:
        for record in entry["judge_new"]:
            step = record.get("cur_step")
            if not isinstance(step, int):
                counts["record cur_step absent"] += 1
            else:
                delta = step - entry["cur_step"]
                counts[f"record cur_step = step {'+' if delta >= 0 else '-'} {abs(delta)}" if delta else "record cur_step = step"] += 1
    return dict(sorted(counts.items()))


def timeline(facts: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """A sanitized timeline of one refusal: steps relative to it, roles instead of identifiers."""
    k, actor = facts["k"], facts["actor"]
    linked = {l["id"]: l for l in facts["linked"]}

    def role(unit: Any, seat: Any = None) -> str:
        if unit == actor:
            return "the refused shooter"
        if unit == facts["target"]:
            return "the target"
        if unit in linked:
            return f"the target's {linked[unit]['relation']}"
        return "another own unit" if seat == facts["seat"] else "another unit"

    rows = []
    for shot in facts["prior_shots_at_target"]:
        rows.append({"dt": shot["k"] - k, "event": f"{role(shot['actor'], shot['seat'])} shot at the target",
                     "engine": "accepted" if shot["feedback"] is None else f"refused ({shot['feedback']})"})
    for record in facts["prior_judge_on_target"]:
        rows.append({"dt": record["k"] - k, "event": "judge_info record on the target",
                     "engine": "positive damage" if isinstance(record["damage"], (int, float)) and record["damage"] > 0
                     else "no damage"})
    for l in facts["linked"]:
        for shot in l["same_step_shots"]:
            rows.append({"dt": 0, "event": f"{'the refused shooter' if shot['by_refused_actor'] else 'another own unit' if shot['seat'] == facts['seat'] else 'another unit'} "
                                           f"shot at the target's {l['relation']} (batch position {shot['i'] + 1} of {facts['batch_size']})",
                         "engine": "accepted" if shot["feedback"] is None else f"refused ({shot['feedback']})"})
        rows.append({"dt": 0, "event": f"judge_info records on the target's {l['relation']}",
                     "engine": f"{l['damage_records']} new, {l['positive_damage']} with positive damage"})
        rows.append({"dt": 0, "event": f"the target's {l['relation']} after the step",
                     "engine": "present" if l["present_after"] else "absent"})
    rows.append({"dt": 0, "event": f"the refused shot at the target (batch position "
                                   f"{(facts['batch_position'] or 0) + 1} of {facts['batch_size']})",
                 "engine": f"refused ({facts['code']} {facts['message_class']})"})
    for record in facts["judge_on_target"]:
        rows.append({"dt": 0, "event": f"judge_info record on the target from {role(record['attacker'])}",
                     "engine": "positive damage" if isinstance(record["damage"], (int, float)) and record["damage"] > 0
                     else "no damage"})
    rows.append({"dt": 0, "event": "the target after the step",
                 "engine": "passenger" if facts["target_passenger_after"] else "present" if facts["target_present_after"]
                 else "absent"})
    return sorted(rows, key=lambda r: r["dt"])


def analyse() -> Dict[str, Any]:
    manifest = load(MANIFEST)
    games = [g["game_id"] for g in manifest["games"]]
    records = {g: load(WORK / "games" / f"{g}.json") for g in games if (WORK / "games" / f"{g}.json").exists()}
    captures, windows = {}, {}
    for game in records:
        compact_path = WORK / "capture" / f"{game}.capture.json"
        windows_path = WORK / "capture" / f"{game}.windows.pkl"
        if compact_path.exists() and windows_path.exists():
            raw_compact, raw_windows = compact_path.read_bytes(), windows_path.read_bytes()
            captures[game] = {"compact": json.loads(raw_compact), "compact_sha256": hashlib.sha256(raw_compact).hexdigest(),
                              "windows_sha256": hashlib.sha256(raw_windows).hexdigest()}
            windows[game] = pickle.loads(raw_windows)
    install = ei.EngineInstall(INSTALL.resolve())
    with ei.exclusive_window(install):
        ledger = ei.read_ledger(install)
    checks = integrity(manifest, records, ledger, captures)
    instr = instrumentation(manifest, records, windows)
    policy = manifest["policy_under_test"]
    facts: List[Dict[str, Any]] = []
    collisions, completeness = [], []
    feedback_counts, judge_counts, relations = collections.Counter(), collections.Counter(), collections.Counter()
    setups = []
    shots = same_seat = opposing = 0
    for game in sorted(captures):
        compact = captures[game]["compact"]
        setup = compact["setup"]
        setups.append(setup)
        factions = {s["seat"]: s["faction"] for s in setup["seats"]}
        seats = {p["seat"] for p in setup["players"] if p["policy"] == policy}
        steps = compact["steps"]
        by_k = {e["k"]: e for e in steps}
        found = []
        for event in windows[game]["events"]:
            snap = next(s for s in event["window"] if s["k"] == event["k"])
            seat_obs = None
            for seat in seats:
                if seat in snap["seats"]:
                    seat_obs = pickle.loads(snap["seats"][seat]["observation"])
            found.extend(rd.event_facts(game, by_k[event["k"]], steps, pickle.loads(snap["global"]),
                                        pickle.loads(event["after"]), seat_obs, seats, factions))
        recorded = sum(1 for s in records[game]["seats"] if s["seat"] in seats for r in s["refusals"] if r["code"] == rd.TRIGGER_CODE)
        completeness.append(recorded == len(found))
        facts.extend(found)
        result = rd.collisions(game, steps, factions)
        collisions.extend(result["cross_seat_collisions"])
        shots += result["shots"]
        same_seat += result["same_seat_repeats"]
        opposing += rd.opposing_unit_actions(steps, {factions[s] for s in seats})
        feedback_counts.update(feedback_order(steps))
        judge_counts.update(judge_steps(steps))
        relations.update(compact["judge_relations"])
    classes = [rd.classify(f) for f in facts]
    for f, c in zip(facts, classes):
        f["classification"] = c
    valid = instr["pass"] and checks["pass"] and all(completeness)
    verdict = rd.conclusion(classes, valid)
    categories = {}
    for category in rd.CATEGORIES:
        chosen = [c for c in classes if c["category"] == category]
        categories[category] = {"count": len(chosen), "strong": sum(1 for c in chosen if c["strength"] == "strong"),
                                "moderate": sum(1 for c in chosen if c["strength"] == "moderate")}
    h7_matches = collections.Counter("+".join(c["matches"]) or "none" for c in classes if c["category"] == "H7")
    linked_gone = [l for f in facts for l in f["linked"] if l["present_before"] and not l["present_after"]]
    representative = {}
    for f, c in zip(facts, classes):
        representative.setdefault(c["category"], timeline(f))
    coverage = setups[0]["coverage"] if setups else {}
    public = {
        "schema": rd.RESULTS_SCHEMA, "diagnostic_id": rd.DIAGNOSTIC_ID, "manifest_sha256": mf.digest(manifest),
        "harness_commits": checks["harness_commits"],
        "games": {"registered": len(games), "recorded": len(records),
                  "completed": sum(1 for r in records.values() if r["status"] == "COMPLETED"),
                  "not_completed": sorted(g for g, r in records.items() if r["status"] != "COMPLETED"),
                  "missing": sorted(set(games) - set(records))},
        "integrity": {k: checks[k] for k in ("pass", "records", "states", "pool_runs", "leftover_processes")}
        | {"sessions": len(checks["sessions"]), "problems": len(checks["problems"]),
           "consecutive_sessions": bool(checks["sessions"]) and checks["sessions"] == list(
               range(checks["sessions"][0], checks["sessions"][0] + len(checks["sessions"]))),
           "runtime": manifest["execution"]["runtime"], "thread_env": RUNTIMES[manifest["execution"]["runtime"]],
           "workers": manifest["execution"]["workers"], "scheduler": manifest["execution"]["scheduler"]},
        "instrumentation": {k: v for k, v in instr.items() if k != "private"},
        "architecture": {
            "seats_by_faction": {str(f): len(v["seats"]) for f, v in coverage.items()},
            "playing_seats_by_faction": {str(f): len(v["playing_seats"]) for f, v in coverage.items()},
            "units_by_faction": {str(f): v["units"] for f, v in coverage.items()},
            "units_listed_for_a_playing_seat": {str(f): v["listed_for_a_playing_seat"] for f, v in coverage.items()},
            "setups_identical": all(s == setups[0] for s in setups) if setups else None,
            "feedback_order": dict(sorted(feedback_counts.items())), "judge_relations": dict(sorted(relations.items())),
            "judge_record_steps": dict(sorted(judge_counts.items())),
        },
        "refusals": {
            "residual_516": len(facts), "complete_against_records": all(completeness),
            "by_class": [{"action_type": k[0], "code": k[1], "message_class": k[2], "count": n} for k, n in sorted(
                collections.Counter((f["action_type"], f["code"], f["message_class"]) for f in facts).items(), key=str)],
            "single_own_shot": sum(1 for f in facts if f["own_shots"] == 1),
            "passed_project_gate": sum(1 for f in facts if f["passed_project_gate"]),
            "legal_at_start": sum(1 for f in facts if f["legal_at_start"]),
            "target_on_map_at_start": sum(1 for f in facts if f["target_on_map_at_start"]),
            "target_absent_after": sum(1 for f in facts if not f["target_present_after"]),
            "actor_present_after": sum(1 for f in facts if f["actor_present_after"]),
            "target_classes": dict(sorted(collections.Counter(label(f["target_class"]) for f in facts).items())),
            "games_with_a_residual_516": len({f["game"] for f in facts}),
        },
        "cross_seat": {
            "events_with_friendly_other_seat_fire": sum(1 for f in facts if f["friendly_other_seat_shots"]),
            "events_without_friendly_other_seat_fire": sum(1 for f in facts if not f["friendly_other_seat_shots"]),
            "events_with_opposing_action_on_target": sum(1 for f in facts if f["opposing_actions_on_target"]),
            "collisions": len(collisions), "collision_steps": len({(c["game"], c["k"]) for c in collisions}),
            "collisions_with_516": sum(1 for c in collisions if c["produced_516"]),
            "collisions_without_516": sum(1 for c in collisions if not c["produced_516"]),
            "same_seat_repeats": same_seat, "shots": shots, "opposing_unit_actions": opposing,
        },
        "evidence": {
            "events_with_positive_damage_on_target": sum(1 for f in facts if any(
                isinstance(r["damage"], (int, float)) and r["damage"] > 0 for r in f["judge_on_target"])),
            "events_with_any_judge_record_on_target": sum(1 for f in facts if f["judge_on_target"]),
            "events_with_a_linked_object": sum(1 for f in facts if f["linked"]),
            "events_with_a_linked_object_removed": sum(1 for f in facts if any(
                l["present_before"] and not l["present_after"] for l in f["linked"])),
            "linked_relations_removed": dict(sorted(collections.Counter(l["relation"] for l in linked_gone).items())),
            "linked_classes_removed": dict(sorted(collections.Counter(label(l["class"]) for l in linked_gone).items())),
            "linked_removed_with_positive_damage": sum(1 for l in linked_gone if l["positive_damage"]),
            "linked_removed_with_accepted_same_step_shot_of_the_seat": sum(1 for f in facts for l in f["linked"]
                if l["present_before"] and not l["present_after"]
                and any(s["seat"] == f["seat"] and s["feedback"] is None for s in l["same_step_shots"])),
            "refused_shot_after_the_linked_shot_in_batch": sum(1 for f in facts for l in f["linked"]
                if l["present_before"] and not l["present_after"] and f["batch_position"] is not None
                and any(s["i"] < f["batch_position"] for s in l["same_step_shots"])),
            "refused_shot_before_the_linked_shot_in_batch": sum(1 for f in facts for l in f["linked"]
                if l["present_before"] and not l["present_after"] and f["batch_position"] is not None
                and any(s["i"] > f["batch_position"] for s in l["same_step_shots"])),
            "events_with_prior_accepted_shot_at_target": sum(1 for f in facts if any(
                s["feedback"] is None for s in f["prior_shots_at_target"])),
            "events_with_prior_judge_record_on_target": sum(1 for f in facts if f["prior_judge_on_target"]),
            "events_with_target_state_change": sum(1 for f in facts if f["target_changes"]),
            "events_with_indirect_fire_at_target_hex": sum(1 for f in facts if f["jm_at_target_hex"]),
        },
        "classification": categories, "h7_matches": dict(sorted(h7_matches.items())),
        "timelines": representative, "conclusion": verdict,
        "validity": {"instrumentation": instr["pass"], "integrity": checks["pass"], "complete": all(completeness)},
        "uninstrumented_reference": {
            "source": f"evaluation/{rt.PLAN_ID}/results.json, tier B-w32, configuration {rd.SCENARIO_ID}.{rd.CONDITION}",
            "process_wall_median_seconds": load(REPO_ROOT / "evaluation" / rt.PLAN_ID / "results.json")["tiers"]["B-w32"][
                "per_config"][f"{rd.SCENARIO_ID}.{rd.CONDITION}"]["process_wall_median"]},
    }
    private = {"schema": rd.FACT_SCHEMA, "facts": facts, "integrity": checks,
               "instrumentation": instr["private"], "collisions": collisions, "setups": setups}
    return {"public": public, "private": private}


def cmd_analyze(args: argparse.Namespace) -> int:
    result = analyse()
    public, private = text(result["public"]), text(result["private"])
    if args.check:
        same = PUBLIC.exists() and PUBLIC.read_text(encoding="utf-8") == public and PRIVATE.exists() and \
            PRIVATE.read_text(encoding="utf-8") == private
        print("results identical" if same else "MISMATCH")
        return 0 if same else 1
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(private, encoding="utf-8", newline="\n")
    PUBLIC.write_text(public, encoding="utf-8", newline="\n")
    print(f"wrote {PUBLIC.relative_to(REPO_ROOT)}: {result['public']['conclusion']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight").set_defaults(func=cmd_preflight)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--label", required=True, choices=("before", "after"))
    snapshot.set_defaults(func=cmd_snapshot)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--check", action="store_true")
    analyze.set_defaults(func=cmd_analyze)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
