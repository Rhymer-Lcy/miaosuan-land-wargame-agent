"""Entry points of the registered target-ownership prevalence diagnostic (``baseline-v2-target-ownership-prevalence-1``).

    PYTHON scripts/ownership_prevalence.py check-observer [--check]   before registration: the observer on preserved states
    PYTHON scripts/ownership_prevalence.py preflight                  the shared-server courtesy check
    PYTHON scripts/ownership_prevalence.py snapshot --label before|after
    PYTHON scripts/ownership_prevalence.py analyze [--check]

``check-observer`` runs the study's classifier on every verified decision of the target-allocation audit's private
corpora (the residual-516 snapshots and the replay corpus) and proves, without an engine, that it leaves the
observation unchanged, that a fresh baseline-v2 decision after it is identical, that it is deterministic, that the
pre-filter never skips a decision with two shooters, and that its S1/S2 and E2/E3 counts equal the design study's
oracle on the same population; it writes ``observer-check.json`` (counts only). ``analyze`` checks integrity and
instrumentation first and reports no prevalence as valid unless both pass; it writes the sanitized
``results.json`` and, privately, the per-game details.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import importlib.util
import json
import pickle
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install as ei  # noqa: E402
from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import digest as trace_digest  # noqa: E402
from miaosuan_agent.evaluation import concurrency as cq  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import ownership_design as od  # noqa: E402
from miaosuan_agent.evaluation import ownership_prevalence as op  # noqa: E402
from miaosuan_agent.evaluation.canonical import value_digest  # noqa: E402
from miaosuan_agent.evaluation.execution import RUNTIMES  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

PUBLIC = REPO_ROOT / "evaluation" / op.STUDY_ID
MANIFEST = PUBLIC / "manifest.json"
RESULTS = PUBLIC / "results.json"
OBSERVER_CHECK = PUBLIC / "observer-check.json"
WORK = REPO_ROOT / "local" / "evaluation" / op.STUDY_ID
INSTALL = REPO_ROOT / "local" / "engines" / "sdk-4.1.0"
DESIGN = REPO_ROOT / "evaluation" / "target-ownership-design-1" / "analysis.json"
LAST_SESSION_BEFORE = 1897


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
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def hist(values: Any) -> Dict[str, int]:
    return {str(k): v for k, v in sorted(collections.Counter(values).items(), key=lambda kv: (isinstance(kv[0], str), kv[0]))}


# ----------------------------------------------------------------------------------------------
# before registration: the observer on preserved states


class ObserverCheck:
    """Receives every verified baseline-v2 decision from the target-allocation audit's loaders."""

    def __init__(self) -> None:
        self.fidelity: collections.Counter = collections.Counter()
        self.counts: collections.Counter = collections.Counter()
        self.problems: List[Dict[str, Any]] = []

    def decision(self, where: Dict[str, Any], raw: Mapping[str, Any], seat: int, faction: int, v2: Any, costs: MoveCosts,
                 memory: Any, outcome: Any = None) -> None:
        self.counts["decisions"] += 1
        before = value_digest(dict(raw))
        actions = [dict(a) for a in v2.actions]
        if op.shoot_listed_units(raw) < 2:
            self.counts["decisions skipped by the pre-filter"] += 1
            if len(od.shoot_graph(raw, seat, faction)[1]) >= 2:
                self.problems.append({**where, "problem": "the pre-filter skipped a decision with two shooters"})
            return
        self.counts["decisions classified"] += 1
        rows = op.classify(raw, seat, faction, where["config"], actions)
        again = op.classify(raw, seat, faction, where["config"], actions)
        if again != rows:
            self.problems.append({**where, "problem": "classification is not deterministic"})
        if value_digest(dict(raw)) != before:
            self.problems.append({**where, "problem": "classification changed the observation"})
        fresh = ShootReservationPolicy(costs).decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
        if [dict(a) for a in fresh.actions] != actions or trace_digest(fresh.trace) != trace_digest(v2.trace):
            self.problems.append({**where, "problem": "a decision after classification differs"})
        for problem in op.check_consistency(rows):
            self.problems.append({**where, "problem": problem})
        for row in rows:
            self.counts[f"components {row['kind']}"] += 1
            for event in ("E0", "E1", "E2", "E3"):
                self.counts[event] += row[event]
            if row["kind"] == "S2" and (row["E2"] or row["E3"]):
                self.problems.append({**where, "problem": "an S2 component was reported as E2 or E3"})
            if row["E2"] and not row["E3"]:
                self.counts["E2 with a failed gate precheck"] += 1


def observer_check() -> Dict[str, Any]:
    audit = load_script("audit_target_allocation")
    check = ObserverCheck()
    audit.d1(check)
    audit.d2(check)
    audit.d3(check)
    design = load(DESIGN)
    expected = {"E0": design["situations"]["collision_components"], "E1": design["s1"]["components"],
                "E2": design["s1"]["lower_attack_level_owner"],
                "E3": design["s1"]["lower_attack_level_owner"] - design["s1"]["gate_precheck_failures"]}
    observed = {e: check.counts[e] for e in expected}
    return {"schema": "miaosuan-ownership-prevalence-observer-check/1", "study_id": op.STUDY_ID,
            "observer_source_sha256": op.observer_source_sha256(),
            "population": {k: v for k, v in sorted(check.fidelity.items())},
            "counts": dict(sorted(check.counts.items())), "problems": len(check.problems),
            "design_study_expected": expected, "agrees_with_design_study": observed == expected,
            "pass": not check.problems and observed == expected}


def cmd_check_observer(args: argparse.Namespace) -> int:
    result = observer_check()
    content = text(result)
    if args.check:
        same = OBSERVER_CHECK.exists() and OBSERVER_CHECK.read_text(encoding="utf-8") == content
        print("observer check identical" if same else "MISMATCH")
        return 0 if same else 1
    OBSERVER_CHECK.parent.mkdir(parents=True, exist_ok=True)
    OBSERVER_CHECK.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OBSERVER_CHECK.relative_to(REPO_ROOT).as_posix()}: pass {result['pass']}")
    return 0 if result["pass"] else 1


# ----------------------------------------------------------------------------------------------
# run support


def cmd_preflight(args: argparse.Namespace) -> int:
    qc = load_script("qualify_concurrency")
    plan = load(REPO_ROOT / "evaluation" / cq.PLAN_ID / "plan.json")
    result = qc.precheck(op.WORKERS, plan)
    out = WORK / "prechecks" / f"precheck-{stamp()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as handle:
        handle.write(text({"workers": op.WORKERS, **result}))
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
# integrity and instrumentation


def read_captures(manifest: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    captures = {}
    for entry in manifest["games"]:
        game = entry["game_id"]
        compact_path, snapshot_path = WORK / "capture" / f"{game}.ownership.json", WORK / "capture" / f"{game}.snapshots.pkl"
        if compact_path.exists() and snapshot_path.exists():
            compact, snapshots = compact_path.read_bytes(), snapshot_path.read_bytes()
            captures[game] = {"compact": json.loads(compact), "snapshots": pickle.loads(snapshots),
                              "compact_sha256": hashlib.sha256(compact).hexdigest(),
                              "snapshots_sha256": hashlib.sha256(snapshots).hexdigest()}
    return captures


def integrity(manifest: Mapping[str, Any], records: Mapping[str, Dict[str, Any]], ledger: List[Dict[str, Any]],
              captures: Mapping[str, Dict[str, Any]], snapshots: Mapping[str, Any]) -> Dict[str, Any]:
    games = [g["game_id"] for g in manifest["games"]]
    problems: List[str] = []
    if sorted(records) != sorted(games):
        problems.append(f"records for {len(records)} of {len(games)} registered games")
    started = sorted(p.name for p in (WORK / "started").iterdir()) if (WORK / "started").exists() else []
    if started != sorted(games):
        problems.append(f"start markers for {len(started)} games")
    queues = sorted((WORK / "logs").glob("queue-*.txt")) if (WORK / "logs").exists() else []
    if len(queues) != 1 or queues[0].read_text(encoding="utf-8").split() != games:
        problems.append("the dispatch queue is not exactly the registered order")
    events: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for event in ledger:
        events.setdefault(event["session"], {}).setdefault(event["event"], []).append(event)
    digest = mf.digest(manifest)
    execution = manifest["execution"]
    env = dict(RUNTIMES[execution["runtime"]])
    observer = manifest["identities"]["observer_source_sha256"]
    active = manifest["active_seats"]
    states, commits = set(), set()
    for game, record in sorted(records.items()):
        harness = record["harness"]
        commits.add(harness["commit"])
        if record["status"] != "COMPLETED":
            problems.append(f"{game}: {record['status']}")
        if (harness["manifest_sha256"], harness["policy_source_sha256"]) != (digest, op.BASELINE_V2_SOURCE_SHA256):
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
        if (capture["compact_sha256"], capture["snapshots_sha256"]) != (summary.get("compact_sha256"), summary.get("snapshots_sha256")):
            problems.append(f"{game}: capture files differ from the digests in its record")
        compact = capture["compact"]
        if compact.get("observer_source_sha256") != observer:
            problems.append(f"{game}: observer source {compact.get('observer_source_sha256')}")
        condition = game.split(".")[1]
        if sorted(int(s) for s in compact["decisions"]) != active[condition]:
            problems.append(f"{game}: observed seats {sorted(compact['decisions'])}")
        for seat in record["seats"]:
            if seat["seat"] in active[condition] and compact["decisions"].get(str(seat["seat"])) != seat["decisions"]:
                problems.append(f"{game}: seat {seat['seat']} decisions differ between capture and record")
    sessions = sorted(int(r["session"]) for r in records.values())
    if sessions and sessions != list(range(LAST_SESSION_BEFORE + 1, LAST_SESSION_BEFORE + 1 + len(sessions))):
        problems.append("sessions are not consecutive after the registered last session")
    if len(states) > 1:
        problems.append("the engine state differs between sessions")
    before, after = snapshots.get("before"), snapshots.get("after")
    if not before or not after:
        problems.append("a ledger snapshot is missing")
    else:
        if before["opened"] != LAST_SESSION_BEFORE or after["opened"] != LAST_SESSION_BEFORE + len(games):
            problems.append(f"sessions opened {before['opened']} before and {after['opened']} after")
        if before["unclosed"] or after["unclosed"]:
            problems.append("unclosed sessions in a snapshot")
        if (before["state"], before["state_stat"]["size"], before["state_stat"]["mtime_ns"]) != (
                after["state"], after["state_stat"]["size"], after["state_stat"]["mtime_ns"]):
            problems.append("the engine state files changed")
        if before["home"] != after["home"] or not after["integrity"]["ok"]:
            problems.append("home or package integrity changed")
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
    return {"pass": not problems, "problems": problems, "records": len(records), "sessions": [sessions[0], sessions[-1]]
            if sessions else None, "states": len(states), "pool_runs": len(pools), "leftover_processes": leftovers,
            "harness_commits": sorted(commits)}


def offline_replay(manifest: Mapping[str, Any], captures: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    costs = {}
    for scenario in manifest["scenarios"]:
        inputs = sdk_data.load_inputs(WORK / "data" / scenario["scenario_id"] / "Data", scenario["scenario_id"],
                                      scenario["map_id"])
        costs[scenario["scenario_id"]] = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    checked, mismatches = 0, []
    for game, capture in sorted(captures.items()):
        for snap in capture["snapshots"]["snapshots"]:
            decision = ShootReservationPolicy(costs[game.split(".")[0]]).decide(
                Observation.from_raw(pickle.loads(snap["observation"]), Origin.ENGINE), snap["seat"], snap["faction"],
                pickle.loads(snap["memory"]))
            checked += 1
            if op.plain([dict(a) for a in decision.actions]) != snap["actions"] or trace_digest(decision.trace) != snap["trace"]:
                mismatches.append({"game": game, "k": snap["k"], "seat": snap["seat"]})
    return {"decisions": checked, "mismatches": mismatches}


def instrumentation(manifest: Mapping[str, Any], records: Mapping[str, Dict[str, Any]],
                    captures: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    policy = manifest["policy_under_test"]
    comparisons = {game: cq.compare(record, manifest["references"][".".join(game.split(".")[:2])])
                   for game, record in sorted(records.items())}
    seats = [s for r in records.values() for s in r["seats"] if s["policy"] == policy]
    replay = offline_replay(manifest, captures)
    observer = [c["compact"]["observer_seconds"] for c in captures.values()]
    shares = [captures[g]["compact"]["observer_seconds"] / r["timings_seconds"]["wall"] for g, r in records.items() if g in captures]
    walls = [r["timings_seconds"]["wall"] for r in records.values()]
    mutations = sum(c["compact"]["observation_mutations"] for c in captures.values())
    problems = sum(len(c["compact"]["problems"]) for c in captures.values())
    errors = sum(len(r.get("observer_errors") or []) for r in records.values())
    checks = {"prefix": all(c["pass"] for c in comparisons.values()) and len(comparisons) == len(manifest["games"]),
              "in_game_replay": sum(s["replay_mismatches"] for s in seats) == 0 and sum(s["replay_checks"] for s in seats) > 0,
              "offline_replay": replay["decisions"] > 0 and not replay["mismatches"],
              "observation_unchanged": mutations == 0, "consistency": problems == 0,
              "observer_errors": errors == 0 and len(captures) == len(records)}
    by_class = collections.Counter(c["class"] for c in comparisons.values())
    return {"pass": all(checks.values()) and bool(records), "checks": checks,
            "prefix_equal": sum(1 for c in comparisons.values() if c["pass"]), "games": len(comparisons),
            "prefix_games_by_reference_class": dict(sorted(by_class.items())),
            "in_game_replay_checks": sum(s["replay_checks"] for s in seats),
            "in_game_replay_mismatches": sum(s["replay_mismatches"] for s in seats),
            "offline_decisions": replay["decisions"], "offline_mismatches": len(replay["mismatches"]),
            "observation_mutations": mutations, "consistency_problems": problems, "observer_errors": errors,
            "observer_seconds": {"median": statistics.median(observer), "max": max(observer), "total": sum(observer)}
            if observer else None,
            "observer_share_of_wall": {"median": statistics.median(shares), "max": max(shares)} if shares else None,
            "game_wall_seconds": {"median": statistics.median(walls), "max": max(walls)} if walls else None,
            "private": {"comparisons": comparisons, "offline_mismatches": replay["mismatches"]}}


# ----------------------------------------------------------------------------------------------
# prevalence


def game_rows(manifest: Mapping[str, Any], records: Mapping[str, Dict[str, Any]],
              captures: Mapping[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for entry in manifest["games"]:
        game = entry["game_id"]
        if game not in captures or records.get(game, {}).get("status") != "COMPLETED":
            continue
        comps = captures[game]["compact"]["components"]
        seats = sorted(int(s) for s in captures[game]["compact"]["decisions"])
        row = {"game": game, "config": entry["config"], "scenario_id": entry["scenario_id"], "condition": entry["condition"],
               "seats": seats, "decisions": captures[game]["compact"]["decisions"],
               "e3": [c for c in comps if c["E3"]]}
        for event in ("E0", "E1", "E2", "E3"):
            row[event] = any(c[event] for c in comps)
            row[f"{event}_seats"] = sorted({c["seat"] for c in comps if c[event]})
            row[f"{event}_decisions"] = len({(c["seat"], c["k"]) for c in comps if c[event]})
            row[f"{event}_components"] = sum(1 for c in comps if c[event])
        row["e2_gate_failed"] = sum(1 for c in comps if c["E2"] and not c["E3"])
        row["weapon_key_only"] = sum(1 for c in comps if c.get("key") == "weapon tie-break")
        rows.append(row)
    return rows


def share(x: int, n: int) -> Dict[str, Any]:
    return {"positive": x, "games": n, "share": round(x / n, 4) if n else None,
            "exact_95": op.clopper_pearson(x, n) if n else None}


def prevalence(manifest: Mapping[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    configs = sorted({e["config"] for e in manifest["games"]})
    by_condition = {c: [r for r in rows if r["condition"] == c] for c in op.CONDITIONS}
    out: Dict[str, Any] = {"games": {}, "by_configuration": {}, "active_seat_games": {}, "exposure": {}}
    for event in ("E3", "E2", "E1", "E0"):
        out["games"][event] = {c: share(sum(r[event] for r in rs), len(rs)) for c, rs in by_condition.items()}
        out["games"][event]["suite"] = share(sum(r[event] for r in rows), len(rows))
    per_config = {c: [r for r in rows if r["config"] == c] for c in configs}
    out["by_configuration"] = {c: {**share(sum(r["E3"] for r in rs), len(rs)), "E2": sum(r["E2"] for r in rs),
                                   "E1": sum(r["E1"] for r in rs), "E0": sum(r["E0"] for r in rs)}
                               for c, rs in per_config.items()}
    out["suite_equal_configuration_weight"] = {
        "share": round(statistics.mean(sum(r["E3"] for r in rs) / len(rs) for rs in per_config.values() if rs), 4)
        if all(per_config.values()) else None,
        "note": "with 15 games in every configuration the equal-weight share equals the pooled share"}
    for c, rs in by_condition.items():
        seat_games = sum(len(r["seats"]) for r in rs)
        positive = sum(len(r["E3_seats"]) for r in rs)
        out["active_seat_games"][c] = {"positive": positive, "seat_games": seat_games,
                                       "share": round(positive / seat_games, 4) if seat_games else None,
                                       "exact_95": op.clopper_pearson(positive, seat_games) if seat_games and c != "C1" else None}
        decisions = [int(v) for r in rs for v in r["decisions"].values()]
        out["exposure"][c] = {"games": len(rs), "active_seats_per_game": sorted({len(r["seats"]) for r in rs}),
                              "active_seat_games": seat_games, "baseline_v2_decisions": sum(decisions),
                              "decisions_per_seat_game": {"min": min(decisions), "median": statistics.median(decisions),
                                                          "max": max(decisions)} if decisions else None}
    return out


def diversity(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    occurrences = collections.Counter()
    games_of: Dict[str, set] = collections.defaultdict(set)
    per_game_distinct = []
    per_game_raw = []
    within = []
    for r in rows:
        if not r["e3"]:
            continue
        counts = collections.Counter(c["fingerprint"] for c in r["e3"])
        per_game_raw.append(len(r["e3"]))
        per_game_distinct.append(len(counts))
        within.extend(counts.values())
        for fp, n in counts.items():
            occurrences[fp] += n
            games_of[fp].add(r["game"])
    return {"e3_components": sum(per_game_raw), "e3_decisions": sum(r["E3_decisions"] for r in rows),
            "distinct_fingerprints": len(occurrences), "affected_games": len(per_game_raw),
            "repeated_fingerprints": sum(1 for n in occurrences.values() if n > 1),
            "fingerprints_in_several_games": sum(1 for g in games_of.values() if len(g) > 1),
            "max_within_game_repetition": max(within) if within else 0,
            "max_cross_game_recurrence": max((len(g) for g in games_of.values()), default=0),
            "components_per_affected_game": hist(per_game_raw),
            "distinct_fingerprints_per_affected_game": hist(per_game_distinct),
            "multiplicity": hist(occurrences.values()),
            "games_per_fingerprint": hist(len(g) for g in games_of.values()),
            "scenarios_with_e3": len({r["scenario_id"] for r in rows if r["e3"]}),
            "configurations_with_e3": len({r["config"] for r in rows if r["e3"]}),
            "table": [{"fingerprint": fp, "occurrences": occurrences[fp], "games": len(games_of[fp]),
                       "configuration": sorted({r["config"] for r in rows for c in r["e3"] if c["fingerprint"] == fp})}
                      for fp in sorted(occurrences)]}


def structure(rows: List[Dict[str, Any]], captures: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    comps = [c for cap in captures.values() for c in cap["compact"]["components"]]
    s1 = [c for c in comps if c["kind"] == "S1"]
    e2 = [c for c in s1 if c["E2"]]
    e3 = [c for c in e2 if c["E3"]]
    positive = [r for r in rows if r["e3"]]
    return {
        "components": {"E0": len(comps), "S1": len(s1), "S2": sum(1 for c in comps if c["kind"] == "S2"),
                       "E2": len(e2), "E3": len(e3), "E2_gate_failed": len(e2) - len(e3)},
        "decisions": {"E0": len({(c["seat"], c["k"], g) for g, cap in captures.items() for c in cap["compact"]["components"]}),
                      "E1": len({(c["seat"], c["k"], g) for g, cap in captures.items() for c in cap["compact"]["components"] if c["E1"]}),
                      "E2": len({(c["seat"], c["k"], g) for g, cap in captures.items() for c in cap["compact"]["components"] if c["E2"]}),
                      "E3": len({(c["seat"], c["k"], g) for g, cap in captures.items() for c in cap["compact"]["components"] if c["E3"]})},
        "e3_gap": hist(c["gap"] for c in e3), "e2_gap": hist(c["gap"] for c in e2),
        "e3_claimants": hist(c["shooters"] for c in e3), "s1_claimants": hist(c["shooters"] for c in s1),
        "e3_class_pairs": hist(f"{c['owner_class']} -> {c['designated_class']}" for c in e3),
        "e3_same_class": sum(1 for c in e3 if c["same_class"]), "e3_cross_class": sum(1 for c in e3 if not c["same_class"]),
        "e3_same_weapon": sum(1 for c in e3 if c["same_weapon"]),
        "e3_games_cross_class_only": sum(1 for r in positive if all(not c["same_class"] for c in r["e3"])),
        "e3_games_same_class_only": sum(1 for r in positive if all(c["same_class"] for c in r["e3"])),
        "e3_top_claimants": hist(c["top_claimants"] for c in e3),
        "e3_top_weapons_differ": sum(1 for c in e3 if c["top_weapons_differ"]),
        "s1_weapon_key_only": sum(1 for c in s1 if c["key"] == "weapon tie-break"),
        "e3_owner_then": hist(c["claimant_actions"][0] for c in e3),
        "e3_designated_then": hist(c["claimant_actions"][c["levels"].index(max(c["levels"]))] for c in e3),
        "e3_by_condition": hist(g.split(".")[1] for g, cap in captures.items() for c in cap["compact"]["components"] if c["E3"]),
    }


def historical(rows: List[Dict[str, Any]], captures: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    design = load(DESIGN)
    past = {r["fingerprint"] for r in design["situations"]["table"] if r["lower_attack_reserver"] and r["kind"] == "S1"}
    now_e2 = {c["fingerprint"] for cap in captures.values() for c in cap["compact"]["components"] if c["E2"]}
    now_e3 = {c["fingerprint"] for cap in captures.values() for c in cap["compact"]["components"] if c["E3"]}
    return {"historical_s1_mismatch_fingerprints": len(past),
            "historical_s1_owner_changes": design["s1"]["owner_changed"],
            "historical_games_with_s1_change": design["s1"]["games_changed"],
            "prospective_e2_fingerprints_seen_historically": len(now_e2 & past),
            "prospective_e3_fingerprints_seen_historically": len(now_e3 & past),
            "historical_fingerprints_seen_prospectively": len(past & now_e2)}


def analyse() -> Dict[str, Any]:
    manifest = load(MANIFEST)
    records = {}
    for entry in manifest["games"]:
        path = WORK / "games" / f"{entry['game_id']}.json"
        if path.exists():
            records[entry["game_id"]] = load(path)
    captures = read_captures(manifest)
    ledger = ei.read_ledger(ei.EngineInstall(INSTALL.resolve()))
    snapshots = {label: load(WORK / "snapshots" / f"{label}.json") for label in ("before", "after")
                 if (WORK / "snapshots" / f"{label}.json").exists()}
    integ = integrity(manifest, records, ledger, captures, snapshots)
    instr = instrumentation(manifest, records, captures)
    rows = game_rows(manifest, records, captures)
    valid = integ["pass"] and instr["pass"]
    result = {"schema": op.RESULTS_SCHEMA, "study_id": op.STUDY_ID, "manifest_sha256": mf.digest(manifest),
              "integrity": {k: v for k, v in integ.items()}, "instrumentation": {k: v for k, v in instr.items() if k != "private"},
              "valid": valid}
    if valid:
        result.update(prevalence=prevalence(manifest, rows), diversity=diversity(rows), structure=structure(rows, captures),
                      historical=historical(rows, captures),
                      decision=op.next_step(rows, valid),
                      decision_inputs={"e3_games": sum(1 for r in rows if r["e3"]),
                                       "scenarios": len({r["scenario_id"] for r in rows if r["e3"]})})
    else:
        result["decision"] = None
    private = {"games": [{k: v for k, v in r.items() if k != "e3"} | {"e3_fingerprints": [c["fingerprint"] for c in r["e3"]]}
                         for r in rows], "comparisons": instr["private"]}
    return {"public": result, "private": private}


def cmd_analyze(args: argparse.Namespace) -> int:
    out = analyse()
    content = text(out["public"])
    if args.check:
        same = RESULTS.exists() and RESULTS.read_text(encoding="utf-8") == content
        print("results identical" if same else "MISMATCH")
        return 0 if same else 1
    RESULTS.write_text(content, encoding="utf-8", newline="\n")
    (WORK / "analysis").mkdir(parents=True, exist_ok=True)
    (WORK / "analysis" / "private.json").write_text(text(out["private"]), encoding="utf-8")
    public = out["public"]
    print(f"wrote {RESULTS.relative_to(REPO_ROOT).as_posix()}: valid {public['valid']}, decision {public['decision']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-observer")
    check.add_argument("--check", action="store_true")
    check.set_defaults(func=cmd_check_observer)
    sub.add_parser("preflight").set_defaults(func=cmd_preflight)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--label", required=True, choices=("before", "after"))
    snap.set_defaults(func=cmd_snapshot)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--check", action="store_true")
    analyze.set_defaults(func=cmd_analyze)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
