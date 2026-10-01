"""Run the registered concurrency qualification. Diagnostic only: the production evaluator is not used.

    PYTHON scripts/qualify_concurrency.py stage --sdk-archive ZIP
    PYTHON scripts/qualify_concurrency.py tier --tier S|w01|w02|w04|w08|w16|w24|w32 [--attempt a2]
    PYTHON scripts/qualify_concurrency.py analyze [--check]

``game`` is internal: ``tier`` starts one process per game with it, inside the registered isolation. The
plan is ``evaluation/concurrency-qualification-1/plan.json``; everything a run writes is under the git-ignored
``local/diagnostics/concurrency-qualification-1/`` except the sanitized ``results.json`` written by ``analyze``.

``tier`` refuses unless every earlier tier of the plan passed its safety, independence, engine-state and
ledger checks (optional tiers also need the registered efficiency), and a tier directory is never reused:
a repetition needs a new ``--attempt`` name. Exit status of ``tier``: 0 every check passed, 2 refused before
any engine session, 3 paused because the host was busy, 5 a check failed (the qualification stops).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install as ei  # noqa: E402
from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.evaluation import concurrency as cq  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import procstat, randomness, scheduler  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402

PLAN = REPO_ROOT / "evaluation" / cq.PLAN_ID / "plan.json"
RESULTS = REPO_ROOT / "evaluation" / cq.PLAN_ID / "results.json"
MANIFEST = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
WORK = REPO_ROOT / "local" / "diagnostics" / cq.PLAN_ID
INSTALL = REPO_ROOT / "local" / "engines" / "sdk-4.1.0"
SEQUENCE = [t["tier"] for t in cq.TIERS] + [t["tier"] for t in cq.OPTIONAL_TIERS]


def evaluator() -> Any:
    spec = importlib.util.spec_from_file_location("run_evaluation", REPO_ROOT / "scripts" / "run_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plan() -> Dict[str, Any]:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def load_manifest(plan: Mapping[str, Any]) -> Dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if mf.digest(manifest) != plan["inputs"]["manifest_sha256"]:
        raise SystemExit("the shoot experiment manifest differs from the one the plan registered")
    return manifest


def tier_folder(tier: str, attempt: Optional[str]) -> Path:
    return WORK / "tiers" / (tier if attempt is None else f"{tier}.{attempt}")


def _terminate(signum: int, frame: Any) -> None:
    raise SystemExit(128 + signum)  # lets the session ledger record the interruption


# ----------------------------------------------------------------------------------------------
# stage and game


def cmd_stage(args: argparse.Namespace) -> int:
    plan = load_plan()
    manifest = load_manifest(plan)
    rev = evaluator()
    for scenario in manifest["scenarios"]:
        root = rev.data_root(WORK, scenario["scenario_id"])
        if not root.exists():
            sdk_data.stage_game_data(args.sdk_archive, root.parent, scenario["scenario_id"], scenario["map_id"])
        rev.verify_inputs(manifest, WORK, scenario["scenario_id"], scenario["map_id"])
        print(f"staged and verified {scenario['scenario_id']} (map {scenario['map_id']})")
    return 0


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, _terminate)
    plan = load_plan()
    manifest = load_manifest(plan)
    spec_tier = cq.tier_spec(plan, args.tier)
    entry = next((e for e in cq.tier_queue(plan, args.tier) if e["game_id"] == args.game_id), None)
    if entry is None:
        print(f"unknown game id {args.game_id} for tier {args.tier}", file=sys.stderr)
        return 2
    rev = evaluator()
    registered = plan["policy"]["policy_source"]
    source = rev.registered_source_digest(registered)
    if source != registered["sha256"]:
        print("REFUSED: the policy source differs from the registered baseline-v2 source", file=sys.stderr)
        return 2
    folder = Path(args.tier_dir)
    out = folder / "games" / f"{args.game_id}.json"
    if out.exists():
        print(f"REFUSED: {out} exists; records are never overwritten", file=sys.stderr)
        return 2
    scenario = next(s for s in manifest["scenarios"] if s["scenario_id"] == entry["scenario_id"])
    try:
        rev.verify_inputs(manifest, WORK, scenario["scenario_id"], scenario["map_id"])
        inputs = sdk_data.load_inputs(rev.data_root(WORK, scenario["scenario_id"]), scenario["scenario_id"],
                                      scenario["map_id"])
    except (sdk_data.SdkDataError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    spec = mf.GameSpec(game_id=args.game_id, scenario_id=scenario["scenario_id"], map_id=scenario["map_id"],
                       condition=entry["condition"], red=entry["red"], blue=entry["blue"], repetition=entry["seq"],
                       max_time=int(scenario["max_time"]))
    randomness.seed_globals(int(manifest["randomness"]["global_seed"]))
    harness = {"commit": args.harness_commit, "dirty": args.harness_dirty, "game_id": args.game_id,
               "plan_sha256": cq.digest(plan), "policy_source_sha256": source, "tier": args.tier,
               "tier_dir": folder.name, "worker": args.worker, "session_mode": spec_tier["session_mode"]}
    install = ei.EngineInstall(Path(args.engine_install).resolve())
    construct = rev.engine_factory(install)
    opener = (ei.session(install, cq.PURPOSE, harness) if spec_tier["session_mode"] == "exclusive"
              else ei.shared_session(install, cq.PURPOSE, harness, str(args.worker)))
    try:
        with opener as handle:
            record = play(construct, rev.FACTORIES, spec, inputs, manifest["players"], rng_probe=randomness.fingerprint,
                          replay_policies={cq.POLICY})
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": args.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except ei.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record["process"] = procstat.self_report()
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=ei.now())
    with open(out, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"GAME {args.game_id} {record['status']} steps={record.get('steps')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s session={record['session']}")
    return 0 if record["status"] == "COMPLETED" else 1


# ----------------------------------------------------------------------------------------------
# tier


def precheck(workers: int, plan: Mapping[str, Any]) -> Dict[str, Any]:
    etiquette = plan["etiquette"]
    logical = os.cpu_count() or 1
    checks = []
    for attempt in range(etiquette["rechecks"] + 1):
        a = procstat.read_host()
        time.sleep(etiquette["pre_tier_window_seconds"])
        b = procstat.read_host()
        busy = logical * (b["busy"] - a["busy"]) / max(1, b["total"] - a["total"])
        gpu = procstat.gpu_query()
        check = {"attempt": attempt, "others_cpus": round(busy, 3), "idle_after": round(logical - busy - workers, 3),
                 "load1": b["load1"], "gpu_utilization": [g["utilization"] for g in gpu["gpus"]] if gpu else None}
        check["ok"] = (busy <= etiquette["maximum_others_cpus_before"]
                       and logical - busy - workers >= etiquette["minimum_idle_logical_cpus"])
        checks.append(check)
        print(f"host check {attempt}: other activity {busy:.2f} logical CPUs, idle after the tier "
              f"{logical - busy - workers:.1f}, load1 {b['load1']} -> {'ok' if check['ok'] else 'busy'}", flush=True)
        if check["ok"]:
            return {"ok": True, "logical_cpus": logical, "checks": checks}
        if attempt < etiquette["rechecks"]:
            time.sleep(etiquette["recheck_seconds"])
    return {"ok": False, "logical_cpus": logical, "checks": checks}


def snapshot(install: ei.EngineInstall) -> Dict[str, Any]:
    manifest = ei.load_manifest(install)
    ledger = ei.read_ledger(install)
    state_file = install.site / manifest["state_files"][0]
    st = state_file.stat()
    return {"ledger_length": len(ledger), "opened": sum(1 for r in ledger if r.get("event") == "session-open"),
            "unclosed": ei.unclosed_sessions(ledger), "last_state": ledger[-1].get("state") if ledger else None,
            "state": ei.state_hashes(install, manifest),
            "state_stat": {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns},
            "integrity": ei.check_integrity(install, manifest).as_dict(), "home": ei.tree_files(install.home)}


def game_env(install: ei.EngineInstall, tmp: Path) -> Dict[str, str]:
    return {"HOME": str(install.home), "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
            "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": f"{install.site}:{REPO_ROOT / 'src'}", "TMPDIR": str(tmp)}


def summaries() -> Dict[str, Dict[str, Any]]:
    """Tier name -> the summary of its attempt that counts (the last uncontended one, else the last one)."""
    found: Dict[str, List[Dict[str, Any]]] = {}
    for path in sorted((WORK / "tiers").glob("*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        found.setdefault(summary["tier"], []).append(summary)
    chosen = {}
    for tier, items in found.items():
        items.sort(key=lambda s: s["attempt_order"])
        clean = [s for s in items if not s["public"]["contended"]]
        chosen[tier] = (clean or items)[-1]
    return chosen


def integrity_passed(summary: Mapping[str, Any]) -> bool:
    p = summary["public"]
    return p["safety_pass"] and p["independence_pass"] and p["engine_state_pass"] and p["ledger_pass"]


def prerequisites(tier: str) -> Optional[str]:
    """Why ``tier`` may not run yet, or None. Every earlier tier of the sequence must have passed."""
    done = summaries()
    for earlier in SEQUENCE[:SEQUENCE.index(tier)]:
        if earlier not in done:
            return f"tier {earlier} has not run"
        if not integrity_passed(done[earlier]):
            return f"tier {earlier} did not pass its safety, independence, engine-state and ledger checks"
    if tier in [t["tier"] for t in cq.OPTIONAL_TIERS]:
        previous = SEQUENCE[SEQUENCE.index(tier) - 1]
        analysis = analyse(done)
        row = next((t for t in analysis["tiers"] if t["tier"] == previous), None)
        if row is None or not all(c["pass"] for c in row["criteria"].values()) or (
                row["criteria"]["efficiency"]["efficiency"] < cq.OPTIONAL_EFFICIENCY):
            return f"optional tier {tier} needs {previous} to meet every criterion with efficiency >= {cq.OPTIONAL_EFFICIENCY}"
    return None


def cmd_tier(args: argparse.Namespace) -> int:
    plan = load_plan()
    load_manifest(plan)
    spec = cq.tier_spec(plan, args.tier)
    queue = cq.tier_queue(plan, args.tier)
    blocked = prerequisites(args.tier)
    if blocked:
        print(f"REFUSED: {blocked}", file=sys.stderr)
        return 2
    folder = tier_folder(args.tier, args.attempt)
    if folder.exists():
        print(f"REFUSED: {folder} exists; a tier is never rerun in place (use a new --attempt)", file=sys.stderr)
        return 2
    install = ei.EngineInstall(INSTALL.resolve())
    commit = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain"], capture_output=True, text=True,
                                check=True).stdout.strip())
    pre_host = precheck(spec["workers"], plan)
    checks = WORK / "prechecks"
    checks.mkdir(parents=True, exist_ok=True)
    with open(checks / f"{folder.name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json", "x",
              encoding="utf-8") as handle:
        handle.write(json.dumps(pre_host, indent=1) + "\n")
    if not pre_host["ok"]:
        print("PAUSED: the host stayed busy; the tier did not start", file=sys.stderr)
        return 3
    for sub in ("games", "logs", "started", "cwd", "tmp"):
        (folder / sub).mkdir(parents=True)
    with ei.exclusive_window(install):
        before = snapshot(install)
    problems = []
    if before["unclosed"]:
        problems.append(f"unclosed sessions before the tier: {before['unclosed']}")
    if not before["integrity"]["ok"] or before["integrity"]["added"]:
        problems.append(f"package integrity before the tier: {before['integrity']}")
    if before["state"] != before["last_state"]:
        problems.append("the engine state differs from the latest ledger record before the tier")
    if problems:
        (folder / "refused.json").write_text(json.dumps(problems, indent=1) + "\n", encoding="utf-8")
        print("STOP: " + "; ".join(problems), file=sys.stderr)
        return 5
    for entry in queue:
        (folder / "cwd" / entry["game_id"]).mkdir()
        (folder / "tmp" / entry["game_id"]).mkdir()

    running: Dict[str, int] = {}
    lock = threading.Lock()

    def current() -> Dict[str, int]:
        with lock:
            return dict(running)

    def start(job: scheduler.Job, worker: int, batch: int) -> scheduler.ProcessGame:
        entry = queue[job.index]
        gid = entry["game_id"]
        with open(folder / "started" / gid, "x", encoding="utf-8") as marker:
            marker.write(json.dumps({"worker": worker, "batch": batch, "at": ei.now()}) + "\n")
        argv = [args.python, str(REPO_ROOT / "scripts" / "qualify_concurrency.py"), "game", "--tier", args.tier,
                "--tier-dir", str(folder), "--game-id", gid, "--engine-install", str(install.root),
                "--worker", str(worker), "--harness-commit", commit] + (["--harness-dirty"] if dirty else [])
        game = scheduler.ProcessGame(argv, game_env(install, folder / "tmp" / gid), folder / "cwd" / gid,
                                     folder / "logs" / f"{gid}.log")
        with lock:
            running[gid] = game.pid
        return game

    def finished(result: scheduler.Result) -> None:
        with lock:
            running.pop(result.job.game_id, None)
        state = "ok" if result.completed else f"exit {result.exit_code}"
        print(f"{result.finished:8.1f}s worker {result.worker:2d} batch {result.batch:2d} {result.job.game_id} {state}",
              flush=True)

    jobs = [scheduler.Job(index=e["seq"] - 1, game_id=e["game_id"]) for e in queue]
    pool = scheduler.Pool(jobs, spec["workers"], start, timeout_seconds=plan["game_timeout_seconds"],
                          kill_after_seconds=plan["kill_after_seconds"], stop_rule=scheduler.stop_on_first_failure,
                          on_result=finished)
    signal.signal(signal.SIGINT, lambda *_: pool.cancel())
    signal.signal(signal.SIGTERM, lambda *_: pool.cancel())
    sampler = procstat.Sampler(folder / "samples.jsonl", current)
    sampler.start()
    print(f"tier {args.tier}: {len(queue)} games, {spec['workers']} workers, {spec['session_mode']} sessions, "
          f"harness {commit}{' (dirty)' if dirty else ''}", flush=True)
    report = pool.run()
    sampler.stop()
    try:
        with ei.exclusive_window(install):
            after = snapshot(install)
            events = ei.read_ledger(install)[before["ledger_length"]:]
    except ei.InstallRefused as exc:
        after, events = None, []
        problems.append(f"the exclusive window after the tier was refused: {exc}")
    collected = {"tier": args.tier, "attempt": args.attempt, "commit": commit, "dirty": dirty, "precheck": pre_host,
                 "before": before, "after": after, "events": events, "problems": problems,
                 "pool": {"workers": report.workers, "wall_seconds": report.wall_seconds,
                          "stopped_by_rule": report.stopped_by_rule, "cancelled": report.cancelled,
                          "not_started": [j.game_id for j in report.not_started],
                          "results": [{"game_id": r.job.game_id, "index": r.job.index, "worker": r.worker,
                                       "batch": r.batch, "exit_code": r.exit_code, "started": r.started,
                                       "finished": r.finished, "timed_out": r.timed_out, "cancelled": r.cancelled,
                                       "start_error": r.start_error, "leftover_processes": r.leftover_processes,
                                       "completed": r.completed, "usage": r.usage} for r in report.results]}}
    with open(folder / "collected.json", "x", encoding="utf-8") as handle:
        handle.write(json.dumps(collected, indent=1, sort_keys=True) + "\n")
    return write_summary(plan, folder)


def write_summary(plan: Mapping[str, Any], folder: Path) -> int:
    """Derive summary.json from what the tier collected; it can be rerun without touching the engine."""
    collected = json.loads((folder / "collected.json").read_text(encoding="utf-8"))
    summary = summarize(plan, collected, folder)
    (folder / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    p = summary["public"]
    print(f"tier {p['tier']}: safety {p['safety_pass']}, independence {p['independence_pass']}, engine state "
          f"{p['engine_state_pass']}, ledger {p['ledger_pass']}; {p['games_completed']}/{p['games_planned']} games in "
          f"{p['makespan_seconds']:.1f}s = {p['throughput_games_per_hour']:.1f} games/h")
    for problem in summary["problems"]:
        print(f"  PROBLEM: {problem}")
    return 0 if integrity_passed(summary) else 5


def summarize(plan: Mapping[str, Any], collected: Mapping[str, Any], folder: Path) -> Dict[str, Any]:
    tier = collected["tier"]
    spec = cq.tier_spec(plan, tier)
    queue = cq.tier_queue(plan, tier)
    before, after, events = collected["before"], collected["after"], collected["events"]
    pre_host, pool = collected["precheck"], collected["pool"]
    problems = list(collected["problems"])
    planned = [e["game_id"] for e in queue]
    records = {}
    for path in sorted((folder / "games").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        records[record["game_id"]] = record
    block = {e["config"]: e for e in plan["block"]}
    known = {tuple(c) for c in plan["known_refusal_classes"]}
    results = [argparse.Namespace(**r) for r in pool["results"]]
    by_game = {r.game_id: r for r in results}

    # safety
    if pool["not_started"] or pool["stopped_by_rule"] or pool["cancelled"]:
        problems.append(f"not every planned game ran (not started {len(pool['not_started'])}, stopped "
                        f"{pool['stopped_by_rule']}, cancelled {pool['cancelled']})")
    for r in results:
        if not r.completed:
            problems.append(f"{r.game_id}: exit {r.exit_code}, timed out {r.timed_out}, cancelled {r.cancelled}, "
                            f"leftover processes {r.leftover_processes}, start error {r.start_error}")
    for sub, suffix in (("games", ".json"), ("logs", ".log"), ("started", "")):
        names = sorted(p.name[:len(p.name) - len(suffix)] if suffix else p.name for p in (folder / sub).iterdir())
        if names != sorted(planned):
            problems.append(f"{sub}: {len(names)} files for {len(planned)} planned games")
    for gid in planned:
        for sub in ("cwd", "tmp"):
            if any((folder / sub / gid).iterdir()):
                problems.append(f"{gid}: its {sub} directory is not empty")
    game_rows = []
    for gid in planned:
        record = records.get(gid)
        result = by_game.get(gid)
        if record is None or result is None:
            continue
        facts = cq.game_facts(record)
        if facts["status"] != "COMPLETED" or facts["contract_errors"] or facts["gate_rejections"] or facts["replay_mismatches"]:
            problems.append(f"{gid}: {facts}")
        unknown = [c for c in facts["classes"] if tuple(c) not in known]
        if unknown:
            problems.append(f"{gid}: refusal classes outside the known set: {unknown}")
        usage = result.usage
        cpu = usage.get("cpu_user_seconds", 0.0) + usage.get("cpu_system_seconds", 0.0)
        wall = result.finished - result.started
        threads = record["process"]["threads"]
        total_thread_cpu = sum(t["cpu_seconds"] for t in threads) or 1.0
        game_rows.append({
            "game_id": gid, "config": f"{record['scenario_id']}.{record['condition']}", "worker": result.worker,
            "batch": result.batch, "session": record["session"], "process_wall_seconds": wall,
            "game_wall_seconds": record["timings_seconds"]["wall"], "cpu_seconds": cpu,
            "cpu_per_wall": cpu / wall if wall > 0 else None, "max_rss_kib": usage.get("max_rss_kib"),
            "voluntary_switches": usage.get("voluntary_switches"), "involuntary_switches": usage.get("involuntary_switches"),
            "block_input": usage.get("block_input"), "block_output": usage.get("block_output"),
            "threads": len(threads), "busy_threads": sum(1 for t in threads if t["cpu_seconds"] >= 0.01 * total_thread_cpu),
            "main_thread_cpu_share": max(t["cpu_seconds"] for t in threads) / total_thread_cpu,
            "write_bytes": (record["process"].get("io") or {}).get("write_bytes"),
            "gc_collections": [g.get("collections") for g in record["process"]["gc"]],
            "gpu_library": record["process"]["libraries"]["gpu"],
            "latency": cq.latency_summary([record]),
        })
    # descriptors and resources from the samples
    samples = [json.loads(line) for line in (folder / "samples.jsonl").read_text(encoding="utf-8").splitlines() if line]
    root = str(INSTALL.resolve())
    allowed = lambda path: (path.startswith(str(folder / "games")) or path.startswith(str(folder / "logs"))
                            or path in {f"{root}/{name}" for name in plan["expected_writable"]})
    resources = procstat.summarize_samples(samples, allowed)
    if resources["unexpected_writable_files"]:
        problems.append(f"unexpected writable files: {resources['unexpected_writable_files']}")
    if resources["inet_socket_observations"]:
        problems.append(f"internet sockets observed {resources['inet_socket_observations']} times")
    if resources["ours_on_gpu"] or resources["libraries"]["gpu"] or any(row["gpu_library"] for row in game_rows):
        problems.append("a game used or mapped a GPU library")
    # engine state and ledger
    engine_problems, ledger_problems = [], []
    if after is None:
        engine_problems.append("no snapshot after the tier")
    else:
        if after["state"] != before["state"] or after["state_stat"] != before["state_stat"]:
            engine_problems.append(f"engine state file changed: {before['state_stat']} -> {after['state_stat']}")
        if not after["integrity"]["ok"] or after["integrity"]["added"]:
            engine_problems.append(f"package integrity after the tier: {after['integrity']}")
        if after["home"] != before["home"]:
            engine_problems.append("home/ changed")
        if after["unclosed"]:
            ledger_problems.append(f"unclosed sessions after the tier: {after['unclosed']}")
    if any(r.exit_code == 4 for r in results):
        engine_problems.append("an engine session was refused")
    ledger = cq.ledger_check(events, before["opened"], records, spec["session_mode"], before["state"])
    ledger_problems.extend(ledger["problems"])
    # independence
    independence = {}
    for gid, record in records.items():
        config = f"{record['scenario_id']}.{record['condition']}"
        independence[gid] = cq.compare(record, block[config]["reference"])
    classes = {c: e["reference"]["class"] for c, e in block.items()}
    duplicates = cq.duplicate_chains(records.values(), classes)
    independence_problems = [f"{gid}: {v}" for gid, v in independence.items() if not v["pass"]]
    if duplicates:
        independence_problems.append(f"stochastic games share a state chain: {duplicates}")
    if len(independence) != len(planned):
        independence_problems.append("not every planned game has an independence comparison")
    # throughput and resources
    starts = [r.started for r in results]
    ends = [r.finished for r in results]
    makespan = (max(ends) - min(starts)) if results else 0.0
    completed = sum(1 for r in results if r.completed)
    walls = [row["process_wall_seconds"] for row in game_rows]
    cpu_total = sum(row["cpu_seconds"] for row in game_rows)
    mem_total = resources["mem_total_kib"] or 1
    configs: Dict[str, List[Dict[str, Any]]] = {}
    for row in game_rows:
        configs.setdefault(row["config"], []).append(row)
    per_config = {c: {"games": len(rows), "process_wall_median": cq.percentiles([r["process_wall_seconds"] for r in rows])["p50"],
                      "cpu_median": cq.percentiles([r["cpu_seconds"] for r in rows])["p50"],
                      "max_rss_kib_max": max(r["max_rss_kib"] for r in rows),
                      "gc_collections_median": [cq.percentiles([r["gc_collections"][i] for r in rows])["p50"] for i in range(3)],
                      "latency": cq.latency_summary([records[r["game_id"]] for r in rows])}
                  for c, rows in sorted(configs.items())}
    safety_pass = not problems
    public = {
        "tier": tier, "attempt": collected["attempt"], "workers": spec["workers"], "session_mode": spec["session_mode"],
        "games_planned": len(planned), "games_completed": completed, "makespan_seconds": makespan,
        "throughput_games_per_hour": completed / makespan * 3600 if makespan > 0 else 0.0,
        "process_wall_seconds": cq.percentiles(walls), "cpu_seconds_total": cpu_total,
        "cpu_seconds_per_game_median": cq.percentiles([row["cpu_seconds"] for row in game_rows])["p50"],
        "cpu_per_wall_median": cq.percentiles([row["cpu_per_wall"] for row in game_rows if row["cpu_per_wall"]])["p50"],
        "our_cpus_mean": cpu_total / makespan if makespan > 0 else 0.0,
        "host_busy_cpus_mean": resources["host_busy_cpus_mean"], "host_busy_fraction_mean": resources["host_busy_fraction_mean"],
        "others_cpus_mean": resources["others_cpus_mean"], "others_cpus_max": resources["others_cpus_max"],
        "contended": (resources["others_cpus_mean"] or 0.0) > plan["criteria"]["maximum_others_cpus_during"],
        "load1_max": resources["load1_max"], "procs_running_mean": resources["procs_running_mean"],
        "procs_running_max": resources["procs_running_max"],
        "context_switches_per_second": resources["context_switches_per_second"],
        "voluntary_switches_per_game_median": cq.percentiles([row["voluntary_switches"] for row in game_rows])["p50"],
        "involuntary_switches_per_game_median": cq.percentiles([row["involuntary_switches"] for row in game_rows])["p50"],
        "block_output_total": sum(row["block_output"] or 0 for row in game_rows),
        "block_input_total": sum(row["block_input"] or 0 for row in game_rows),
        "write_bytes_per_game_median": cq.percentiles([row["write_bytes"] or 0 for row in game_rows])["p50"],
        "max_rss_kib_per_game": cq.percentiles([row["max_rss_kib"] for row in game_rows]),
        "peak_total_rss_kib": resources["peak_total_rss_kib"], "peak_rss_fraction": resources["peak_total_rss_kib"] / mem_total,
        "threads_per_process_max": resources["threads_per_process_max"],
        "busy_threads_per_game_max": max((row["busy_threads"] for row in game_rows), default=None),
        "main_thread_cpu_share_min": min((row["main_thread_cpu_share"] for row in game_rows), default=None),
        "concurrent_processes_max": resources["concurrent_processes_max"],
        "latency": cq.latency_summary(records.values()), "per_config": per_config,
        "gpu": {"ours_on_gpu": resources["ours_on_gpu"], "gpu_library_mapped": resources["libraries"]["gpu"],
                "samples": resources["gpu_samples"]},
        "libraries": resources["libraries"], "unix_socket_observations": resources["unix_socket_observations"],
        "inet_socket_observations": resources["inet_socket_observations"],
        "descriptor_snapshots": resources["descriptor_snapshots"],
        "independence": {"deterministic_identical": sum(1 for v in independence.values()
                                                         if v["class"] == "deterministic" and v["pass"]),
                         "deterministic_games": sum(1 for v in independence.values() if v["class"] == "deterministic"),
                         "stochastic_prefix_equal": sum(1 for v in independence.values()
                                                        if v["class"] == "stochastic" and v["pass"]),
                         "stochastic_games": sum(1 for v in independence.values() if v["class"] == "stochastic"),
                         "duplicate_chain_groups": len(duplicates)},
        "ledger": {k: ledger[k] for k in ("sessions",)}, "batches": max((r.batch for r in results), default=-1) + 1,
        "safety_pass": safety_pass, "independence_pass": not independence_problems,
        "engine_state_pass": not engine_problems, "ledger_pass": not ledger_problems,
        "precheck_others_cpus": pre_host["checks"][-1]["others_cpus"],
    }
    return {"tier": tier, "attempt": collected["attempt"], "attempt_order": (folder / "collected.json").stat().st_mtime_ns,
            "commit": collected["commit"], "dirty": collected["dirty"],
            "plan_sha256": cq.digest(plan), "public": public, "games": game_rows, "resources": resources,
            "ledger": ledger, "before": before, "after": after, "independence": independence, "duplicates": duplicates,
            "problems": problems + engine_problems + ledger_problems + independence_problems,
            "precheck": pre_host}


# ----------------------------------------------------------------------------------------------
# analyze


def analyse(done: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    rows = []
    base = done.get("w01", {}).get("public")
    for tier in SEQUENCE:
        if tier not in done:
            continue
        public = dict(done[tier]["public"])
        if tier == "S" or base is None:
            public["criteria"] = {k: {"pass": public[f"{k}_pass"]} for k in ("safety", "independence", "engine_state", "ledger")}
        else:
            public["criteria"] = cq.criteria_for(public, base)
            public["speedup"] = public["criteria"]["throughput"]["speedup"]
            public["efficiency"] = public["criteria"]["efficiency"]["efficiency"]
        rows.append(public)
    shared = [r for r in rows if r["tier"] != "S"]
    recommendation = cq.recommend([r for r in rows if r["tier"] == "S"] + shared) if base else None
    return {"tiers": rows, "recommendation": recommendation}


def cmd_analyze(args: argparse.Namespace) -> int:
    plan = load_plan()
    done = summaries()
    analysis = analyse(done)
    results = {"schema": "miaosuan-concurrency-qualification-results/1", "plan_id": cq.PLAN_ID,
               "plan_sha256": cq.digest(plan), "commits": sorted({s["commit"] for s in done.values()}),
               "tiers": analysis["tiers"], "recommendation": analysis["recommendation"]}
    text = json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        if not RESULTS.is_file() or RESULTS.read_text(encoding="utf-8") != text:
            print("results differ", file=sys.stderr)
            return 1
        print("results identical")
        return 0
    RESULTS.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(analysis["recommendation"], indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--sdk-archive", type=Path, required=True)
    stage.set_defaults(func=cmd_stage)
    game = sub.add_parser("game")
    game.add_argument("--tier", required=True)
    game.add_argument("--tier-dir", required=True)
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", required=True)
    game.add_argument("--worker", type=int, required=True)
    game.add_argument("--harness-commit", default="unknown")
    game.add_argument("--harness-dirty", action="store_true")
    game.set_defaults(func=cmd_game)
    tier = sub.add_parser("tier")
    tier.add_argument("--tier", required=True, choices=SEQUENCE)
    tier.add_argument("--attempt")
    tier.add_argument("--python", default=sys.executable)
    tier.set_defaults(func=cmd_tier)
    resummarize = sub.add_parser("resummarize", help="rederive a tier's summary.json from what it collected")
    resummarize.add_argument("--tier", required=True, choices=SEQUENCE)
    resummarize.add_argument("--attempt")
    resummarize.set_defaults(func=lambda a: write_summary(load_plan(), tier_folder(a.tier, a.attempt)))
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--check", action="store_true")
    analyze.set_defaults(func=cmd_analyze)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
