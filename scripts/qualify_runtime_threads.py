"""Run the registered runtime thread-pool qualification. Diagnostic only.

    PYTHON scripts/qualify_runtime_threads.py stage --sdk-archive ZIP
    PYTHON scripts/qualify_runtime_threads.py build-probe
    PYTHON scripts/qualify_runtime_threads.py tier --tier P-A|E-B|B-w01|A-w16|B-w16|A-w24|B-w24|B-w32 [--attempt a2]
    PYTHON scripts/qualify_runtime_threads.py resummarize --tier T [--attempt a2]
    PYTHON scripts/qualify_runtime_threads.py analyze [--check]

``game`` is internal. The plan is ``evaluation/runtime-thread-qualification-1/plan.json``; everything a run writes
is under the git-ignored ``local/diagnostics/runtime-thread-qualification-1/`` except the sanitized
``results.json``. A tier runs only after every earlier tier passed its equivalence, safety, engine-state and
ledger checks, and a tier directory is never reused. Each game gets exactly its group's numerical-thread
variables (the probe tier also the call-counting shim's) on top of the concurrency qualification's isolation,
and refuses to play if its effective environment differs. Exit status of ``tier``: 0 every check passed,
2 refused before any engine session, 3 paused for host load, 5 a check failed.
"""

from __future__ import annotations

import argparse
import hashlib
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
from miaosuan_agent.evaluation import runtime_threads as rt  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.gc_pauses import GcPauses  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402

PLAN = REPO_ROOT / "evaluation" / rt.PLAN_ID / "plan.json"
RESULTS = REPO_ROOT / "evaluation" / rt.PLAN_ID / "results.json"
CQ_RESULTS = REPO_ROOT / "evaluation" / cq.PLAN_ID / "results.json"
MANIFEST = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
SERIAL = REPO_ROOT / "local" / "evaluation" / sx.EXPERIMENT_NAME / "games"
WORK = REPO_ROOT / "local" / "diagnostics" / rt.PLAN_ID
INSTALL = REPO_ROOT / "local" / "engines" / "sdk-4.1.0"
SHIM = WORK / "blas_count.so"
THREAD_VARIABLES = ("OPENBLAS_NUM_THREADS", "GOTO_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS")


def load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
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


def numpy_libraries() -> Dict[str, str]:
    import numpy
    libs = Path(numpy.__file__).resolve().parents[1] / "numpy.libs"
    found = {name: str(next(libs.glob(f"{name}*.so*"))) for name in ("libopenblas", "libquadmath", "libgfortran")}
    return found


def probe_environment(folder: Path, game: str) -> Dict[str, str]:
    libs = numpy_libraries()
    return {"LD_PRELOAD": str(SHIM), "BLAS_COUNT_LIBRARY": libs["libopenblas"],
            "BLAS_COUNT_DEPS": f"{libs['libquadmath']}:{libs['libgfortran']}",
            "BLAS_COUNT_OUTPUT": str(folder / "blas" / f"{game}.json")}


def _terminate(signum: int, frame: Any) -> None:
    raise SystemExit(128 + signum)


# ----------------------------------------------------------------------------------------------
# stage, probe build, game


def cmd_stage(args: argparse.Namespace) -> int:
    plan = load_plan()
    manifest = load_manifest(plan)
    rev = load_script("run_evaluation")
    for scenario in manifest["scenarios"]:
        root = rev.data_root(WORK, scenario["scenario_id"])
        if not root.exists():
            sdk_data.stage_game_data(args.sdk_archive, root.parent, scenario["scenario_id"], scenario["map_id"])
        rev.verify_inputs(manifest, WORK, scenario["scenario_id"], scenario["map_id"])
        print(f"staged and verified {scenario['scenario_id']} (map {scenario['map_id']})")
    return 0


def cmd_build_probe(args: argparse.Namespace) -> int:
    plan = load_plan()
    source = REPO_ROOT / plan["probe"]["source"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != plan["probe"]["source_sha256"]:
        print("REFUSED: the shim source differs from the registered one", file=sys.stderr)
        return 2
    WORK.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-o", str(SHIM), str(source), "-ldl"], check=True)
    print(f"built {SHIM} sha256={hashlib.sha256(SHIM.read_bytes()).hexdigest()}")
    return 0


def cmd_game(args: argparse.Namespace) -> int:
    import resource

    before = procstat.startup_report()
    clock = time.perf_counter()
    import numpy  # the game imports it moments later (map data, seeding); imported here to time it
    import_wall = time.perf_counter() - clock
    after = procstat.startup_report()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    startup = {"numpy": numpy.__version__, "before_numpy": before, "after_numpy": after,
               "numpy_import_wall_seconds": import_wall,
               "numpy_import_cpu_seconds": (after["cpu_user_seconds"] + after["cpu_system_seconds"]
                                            - before["cpu_user_seconds"] - before["cpu_system_seconds"]),
               "voluntary_switches": usage.ru_nvcsw, "involuntary_switches": usage.ru_nivcsw}
    signal.signal(signal.SIGTERM, _terminate)
    plan = load_plan()
    manifest = load_manifest(plan)
    spec_tier = rt.tier_spec(plan, args.tier)
    entry = next((e for e in rt.tier_queue(plan, args.tier) if e["game_id"] == args.game_id), None)
    if entry is None:
        print(f"unknown game id {args.game_id} for tier {args.tier}", file=sys.stderr)
        return 2
    expected = plan["environments"][spec_tier["environment"]]
    effective = {name: os.environ[name] for name in THREAD_VARIABLES if name in os.environ}
    if effective != expected:
        print(f"REFUSED: numerical-thread environment {effective} differs from the registered {expected}", file=sys.stderr)
        return 2
    rev = load_script("run_evaluation")
    registered = manifest["groups"][entry["group"]]["policy_source"]
    source = rev.registered_source_digest(registered)
    if source != registered["sha256"]:
        print("REFUSED: the policy source differs from the registered one", file=sys.stderr)
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
               "plan_sha256": rt.digest(plan), "policy_source_sha256": source, "group": entry["group"],
               "tier": args.tier, "tier_dir": folder.name, "worker": args.worker, "environment": spec_tier["environment"],
               "thread_env": effective, "probe": bool(spec_tier.get("probe"))}
    install = ei.EngineInstall(Path(args.engine_install).resolve())
    construct = rev.engine_factory(install)
    pauses = GcPauses()
    try:
        with ei.shared_session(install, rt.PURPOSE, harness, str(args.worker)) as handle:
            pauses.install()
            try:
                record = play(construct, rev.FACTORIES, spec, inputs, manifest["players"],
                              rng_probe=randomness.fingerprint, replay_policies={entry["policy"]})
            finally:
                pauses.remove()
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": args.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except ei.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record["process"] = procstat.self_report()
    record["startup"] = startup
    record["gc_pauses"] = pauses.summary()
    final = resource.getrusage(resource.RUSAGE_SELF)
    record["rusage_self"] = {"voluntary_switches": final.ru_nvcsw, "involuntary_switches": final.ru_nivcsw,
                             "cpu_user_seconds": final.ru_utime, "cpu_system_seconds": final.ru_stime}
    record["environment"] = {key: value for key, value in sorted(os.environ.items())}
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=ei.now())
    with open(out, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"GAME {args.game_id} {record['status']} steps={record.get('steps')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s session={record['session']}")
    return 0 if record["status"] == "COMPLETED" else 1


# ----------------------------------------------------------------------------------------------
# tier


def summaries(plan: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
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


def passed(summary: Mapping[str, Any]) -> bool:
    p = summary["public"]
    return p["safety_pass"] and p["independence_pass"] and p["engine_state_pass"] and p["ledger_pass"]


def prerequisites(plan: Mapping[str, Any], tier: str) -> Optional[str]:
    done = summaries(plan)
    order = rt.sequence(plan)
    for earlier in order[:order.index(tier)]:
        if earlier not in done:
            return f"tier {earlier} has not run"
        if not passed(done[earlier]):
            return f"tier {earlier} did not pass its equivalence, safety, engine-state and ledger checks"
    if tier in [t["tier"] for t in plan["optional_tiers"]]:
        base, previous = done["B-w01"]["public"], done["B-w24"]["public"]
        criteria = rt.worker_criteria(previous, base)
        if not all(c["pass"] for c in criteria.values()) or criteria["efficiency"]["efficiency"] < plan["optional_efficiency"]:
            return f"{tier} needs B-w24 to meet every worker criterion with efficiency >= {plan['optional_efficiency']}"
    return None


def cmd_tier(args: argparse.Namespace) -> int:
    qc = load_script("qualify_concurrency")
    pool_script = load_script("run_game_pool")
    plan = load_plan()
    load_manifest(plan)
    spec = rt.tier_spec(plan, args.tier)
    queue = rt.tier_queue(plan, args.tier)
    blocked = prerequisites(plan, args.tier)
    if blocked:
        print(f"REFUSED: {blocked}", file=sys.stderr)
        return 2
    if pool_script.scheduler_identity() != plan["identities"]["scheduler"]:
        print("REFUSED: the scheduler identity differs from the registered one", file=sys.stderr)
        return 2
    if spec.get("probe") and not SHIM.exists():
        print("REFUSED: build the probe first (build-probe)", file=sys.stderr)
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
    pre_host = qc.precheck(spec["workers"], plan)
    checks = WORK / "prechecks"
    checks.mkdir(parents=True, exist_ok=True)
    with open(checks / f"{folder.name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json", "x", encoding="utf-8") as h:
        h.write(json.dumps(pre_host, indent=1) + "\n")
    if not pre_host["ok"]:
        print("PAUSED: the host stayed busy; the tier did not start", file=sys.stderr)
        return 3
    for sub in ("games", "logs", "started", "cwd", "tmp", "blas"):
        (folder / sub).mkdir(parents=True)
    with ei.exclusive_window(install):
        before = qc.snapshot(install)
    problems = []
    if before["unclosed"] or not before["integrity"]["ok"] or before["integrity"]["added"] or before["state"] != before["last_state"]:
        problems.append(f"installation not clean before the tier: unclosed {before['unclosed']}, integrity {before['integrity']}")
        (folder / "refused.json").write_text(json.dumps(problems, indent=1) + "\n", encoding="utf-8")
        print("STOP: " + "; ".join(problems), file=sys.stderr)
        return 5
    for entry in queue:
        (folder / "cwd" / entry["game_id"]).mkdir()
        (folder / "tmp" / entry["game_id"]).mkdir()
    running: Dict[str, int] = {}
    lock = threading.Lock()

    def start(job: scheduler.Job, worker: int, batch: int) -> scheduler.ProcessGame:
        gid = queue[job.index]["game_id"]
        with open(folder / "started" / gid, "x", encoding="utf-8") as marker:
            marker.write(json.dumps({"worker": worker, "batch": batch, "at": ei.now()}) + "\n")
        env = qc.game_env(install, folder / "tmp" / gid)
        env.update(plan["environments"][spec["environment"]])
        if spec.get("probe"):
            env.update(probe_environment(folder, gid))
        argv = [args.python, str(REPO_ROOT / "scripts" / "qualify_runtime_threads.py"), "game", "--tier", args.tier,
                "--tier-dir", str(folder), "--game-id", gid, "--engine-install", str(install.root), "--worker",
                str(worker), "--harness-commit", commit] + (["--harness-dirty"] if dirty else [])
        game = scheduler.ProcessGame(argv, env, folder / "cwd" / gid, folder / "logs" / f"{gid}.log")
        with lock:
            running[gid] = game.pid
        return game

    def finished(result: scheduler.Result) -> None:
        with lock:
            running.pop(result.job.game_id, None)
        print(f"{result.finished:8.1f}s worker {result.worker:2d} batch {result.batch:2d} {result.job.game_id} "
              f"{'ok' if result.completed else f'exit {result.exit_code}'}", flush=True)

    jobs = [scheduler.Job(index=e["seq"] - 1, game_id=e["game_id"], group=e["group"]) for e in queue]
    pool = scheduler.Pool(jobs, spec["workers"], start, timeout_seconds=plan["game_timeout_seconds"],
                          kill_after_seconds=plan["kill_after_seconds"], stop_rule=scheduler.stop_on_first_failure,
                          on_result=finished)
    signal.signal(signal.SIGINT, lambda *_: pool.cancel())
    signal.signal(signal.SIGTERM, lambda *_: pool.cancel())
    sampler = procstat.Sampler(folder / "samples.jsonl", lambda: dict(running))
    sampler.start()
    print(f"tier {args.tier}: {len(queue)} games, {spec['workers']} workers, environment {spec['environment']} "
          f"{plan['environments'][spec['environment']]}, harness {commit}{' (dirty)' if dirty else ''}", flush=True)
    report = pool.run()
    sampler.stop()
    try:
        with ei.exclusive_window(install):
            after = qc.snapshot(install)
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
    collected = json.loads((folder / "collected.json").read_text(encoding="utf-8"))
    summary = summarize(plan, collected, folder)
    (folder / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    p = summary["public"]
    print(f"tier {p['tier']}: safety {p['safety_pass']}, independence {p['independence_pass']}, engine state "
          f"{p['engine_state_pass']}, ledger {p['ledger_pass']}; {p['games_completed']}/{p['games_planned']} games in "
          f"{p['makespan_seconds']:.1f}s = {p['throughput_games_per_hour']:.1f} games/h")
    for problem in summary["problems"]:
        print(f"  PROBLEM: {problem}")
    return 0 if passed(summary) else 5


def serial_records(config: str, group: str) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SERIAL.glob(f"{config}.{group}.r*.json"))]


def divergence(record: Mapping[str, Any], serial: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """How long a game tracks the serial repetitions, against its first shot."""
    points = [cq.first_divergence(record["state_steps"], rep["state_steps"]) for rep in serial]
    points = [len(record["state_steps"]) if p is None else p for p in points]
    shots = [int(s["first_step_by_type"]["2"]) for s in record.get("seats", []) if "2" in s.get("first_step_by_type", {})]
    first_shot = min(shots) if shots else None
    return {"agreement_max": max(points) if points else None, "agreement_min": min(points) if points else None,
            "first_shot": first_shot, "serial_repetitions": len(serial)}


def median(values: List[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return cq.percentiles(values)["p50"] if values else None


def summarize(plan: Mapping[str, Any], collected: Mapping[str, Any], folder: Path) -> Dict[str, Any]:
    tier = collected["tier"]
    spec = rt.tier_spec(plan, tier)
    queue = rt.tier_queue(plan, tier)
    entries = {e["game_id"]: e for e in queue}
    before, after, events = collected["before"], collected["after"], collected["events"]
    pool = collected["pool"]
    problems = list(collected["problems"])
    planned = [e["game_id"] for e in queue]
    records = {}
    for path in sorted((folder / "games").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        records[record["game_id"]] = record
    known = {tuple(c) for c in plan["known_refusal_classes"]}
    results = [argparse.Namespace(**r) for r in pool["results"]]
    by_game = {r.game_id: r for r in results}
    # safety
    if pool["not_started"] or pool["stopped_by_rule"] or pool["cancelled"]:
        problems.append(f"not every planned game ran ({len(pool['not_started'])} not started)")
    for r in results:
        if not r.completed:
            problems.append(f"{r.game_id}: exit {r.exit_code}, timed out {r.timed_out}, leftover {r.leftover_processes}")
    for sub, suffix in (("games", ".json"), ("logs", ".log"), ("started", "")):
        names = sorted(p.name[:len(p.name) - len(suffix)] if suffix else p.name for p in (folder / sub).iterdir())
        if names != sorted(planned):
            problems.append(f"{sub}: {len(names)} files for {len(planned)} planned games")
    for gid in planned:
        for sub in ("cwd", "tmp"):
            if any((folder / sub / gid).iterdir()):
                problems.append(f"{gid}: its {sub} directory is not empty")
    rows = []
    for gid in planned:
        record, result, entry = records.get(gid), by_game.get(gid), entries[gid]
        if record is None or result is None:
            continue
        facts = cq.game_facts(record, entry["policy"])
        if facts["status"] != "COMPLETED" or facts["contract_errors"] or facts["gate_rejections"] or facts["replay_mismatches"]:
            problems.append(f"{gid}: {facts}")
        unknown = [c for c in facts["classes"] if tuple(c) not in known]
        if unknown:
            problems.append(f"{gid}: refusal classes outside the known set: {unknown}")
        expected_env = plan["environments"][spec["environment"]]
        if record["harness"]["thread_env"] != expected_env:
            problems.append(f"{gid}: environment {record['harness']['thread_env']}")
        usage = result.usage
        cpu = usage.get("cpu_user_seconds", 0.0) + usage.get("cpu_system_seconds", 0.0)
        split = rt.thread_split(record["process"]["scheduling"])
        gc_summary = record["gc_pauses"]
        startup = record["startup"]
        rows.append({
            "game_id": gid, "config": entry["config"], "group": entry["group"], "worker": result.worker,
            "batch": result.batch, "session": record["session"], "process_wall_seconds": result.finished - result.started,
            "game_wall_seconds": record["timings_seconds"]["wall"], "cpu_seconds": cpu,
            "max_rss_kib": usage.get("max_rss_kib"), "voluntary_switches": usage.get("voluntary_switches"),
            "involuntary_switches": usage.get("involuntary_switches"), "block_output": usage.get("block_output"),
            "threads": len(record["process"]["threads"]), "threads_before_numpy": startup["before_numpy"]["threads"],
            "startup_threads": startup["after_numpy"]["threads"],
            "startup_wall_seconds": startup["after_numpy"]["wall_since_start_seconds"],
            "startup_cpu_seconds": startup["after_numpy"]["cpu_user_seconds"] + startup["after_numpy"]["cpu_system_seconds"],
            "import_wall_seconds": startup["numpy_import_wall_seconds"],
            "import_cpu_seconds": startup["numpy_import_cpu_seconds"],
            "startup_involuntary": startup.get("involuntary_switches"), "split": split,
            "self_involuntary": record["rusage_self"]["involuntary_switches"],
            "gc_gen2_max_ms": gc_summary["max_ms"][2], "gc_max_ms": max(gc_summary["max_ms"]),
            "gc_counts": gc_summary["count"], "gc_kept": len(gc_summary["kept"]),
            "latency": cq.latency_summary([record], entry["policy"]),
        })
    samples = [json.loads(line) for line in (folder / "samples.jsonl").read_text(encoding="utf-8").splitlines() if line]
    root = str(INSTALL.resolve())
    allowed = lambda path: (path.startswith(str(folder / "games")) or path.startswith(str(folder / "logs"))
                            or path.startswith(str(folder / "blas")) or path == "/dev/null"
                            or path in {f"{root}/{name}" for name in plan["expected_writable"]})
    resources = procstat.summarize_samples(samples, allowed)
    if resources["unexpected_writable_files"]:
        problems.append(f"unexpected writable files: {resources['unexpected_writable_files']}")
    if resources["inet_socket_observations"]:
        problems.append(f"internet sockets observed {resources['inet_socket_observations']} times")
    if resources["ours_on_gpu"] or any(records[g]["process"]["libraries"]["gpu"] for g in records):
        problems.append("a game used or mapped a GPU library")
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
    ledger = cq.ledger_check(events, before["opened"], records, "shared", before["state"])
    ledger_problems.extend(ledger["problems"])
    # equivalence
    comparisons, divergences = {}, {}
    for gid, record in records.items():
        entry = entries[gid]
        comparisons[gid] = cq.compare(record, entry["reference"])
        if entry["reference"]["class"] == "stochastic":
            divergences[gid] = divergence(record, serial_records(entry["config"], entry["group"]))
    chains: Dict[tuple, List[str]] = {}
    for gid, record in records.items():
        entry = entries[gid]
        if entry["reference"]["class"] == "stochastic":
            chains.setdefault((entry["config"], entry["group"], record["state_chain"]), []).append(gid)
    duplicates = sorted(sorted(v) for v in chains.values() if len(v) > 1)
    equivalence_problems = [f"{gid}: {v}" for gid, v in comparisons.items() if not v["pass"]]
    if duplicates:
        equivalence_problems.append(f"stochastic games share a state chain: {duplicates}")
    if len(comparisons) != len(planned):
        equivalence_problems.append("not every planned game has an equivalence comparison")
    for gid, d in divergences.items():
        if d["agreement_max"] is None or d["agreement_max"] < entries[gid]["reference"]["state_prefix_steps"]:
            equivalence_problems.append(f"{gid}: diverges from every serial repetition before the serial prefix: {d}")
    # probe
    probe = {}
    if spec.get("probe"):
        baseline = plan["probe"]["import_baseline"]
        for gid in planned:
            path = folder / "blas" / f"{gid}.json"
            if not path.exists():
                problems.append(f"{gid}: no BLAS counts")
                continue
            counts = json.loads(path.read_text(encoding="utf-8"))
            probe[gid] = rt.blas_calls(counts, baseline)
            if any(counts.get(k, 0) < v for k, v in baseline.items()):
                problems.append(f"{gid}: the import-time BLAS call is missing: the shim may not have counted")
    starts = [r.started for r in results]
    ends = [r.finished for r in results]
    makespan = (max(ends) - min(starts)) if results else 0.0
    completed = sum(1 for r in results if r.completed)
    cpu_total = sum(row["cpu_seconds"] for row in rows)
    mem_total = resources["mem_total_kib"] or 1
    per_config: Dict[str, Any] = {}
    for config in sorted({row["config"] for row in rows}):
        subset = [row for row in rows if row["config"] == config]
        per_config[config] = {
            "games": len(subset), "process_wall_median": median([r["process_wall_seconds"] for r in subset]),
            "cpu_median": median([r["cpu_seconds"] for r in subset]),
            "latency_max_ms": max(r["latency"]["max_ms"] or 0 for r in subset),
            "over_1000ms": sum(r["latency"]["over_1000ms"] for r in subset),
            "over_100ms": sum(r["latency"]["over_100ms"] for r in subset),
            "gc_gen2_max_ms": max(r["gc_gen2_max_ms"] for r in subset),
            "gc_counts_median": [median([r["gc_counts"][i] for r in subset]) for i in range(3)],
        }
    walls = [row["process_wall_seconds"] for row in rows]
    all_records = [records[g] for g in planned if g in records]
    latency = cq.latency_summary(all_records, rt.GROUP_POLICIES["C"]) if spec["corpus"] == "block" else {
        group: cq.latency_summary([records[g] for g in planned if g in records and entries[g]["group"] == group], policy)
        for group, policy in rt.GROUP_POLICIES.items()}
    public = {
        "tier": tier, "attempt": collected["attempt"], "environment": spec["environment"],
        "thread_env": plan["environments"][spec["environment"]], "workers": spec["workers"], "corpus": spec["corpus"],
        "probe_tier": bool(spec.get("probe")), "games_planned": len(planned), "games_completed": completed,
        "makespan_seconds": makespan, "throughput_games_per_hour": completed / makespan * 3600 if makespan > 0 else 0.0,
        "process_wall_seconds": cq.percentiles(walls),
        "game_wall_seconds_median": median([r["game_wall_seconds"] for r in rows]),
        "cpu_seconds_total": cpu_total, "cpu_seconds_per_game_median": median([r["cpu_seconds"] for r in rows]),
        "our_cpus_mean": cpu_total / makespan if makespan > 0 else 0.0,
        "host_busy_cpus_mean": resources["host_busy_cpus_mean"], "host_busy_fraction_mean": resources["host_busy_fraction_mean"],
        "others_cpus_mean": resources["others_cpus_mean"],
        "contended": (resources["others_cpus_mean"] or 0.0) > plan["criteria"]["maximum_others_cpus_during"],
        "load1_max": resources["load1_max"], "procs_running_mean": resources["procs_running_mean"],
        "procs_running_max": resources["procs_running_max"], "context_switches_per_second": resources["context_switches_per_second"],
        "threads_per_process_max": resources["threads_per_process_max"],
        "threads_per_process_at_start_max": max((r["startup_threads"] or 0) for r in rows) if rows else None,
        "threads_before_numpy_max": max((r["threads_before_numpy"] or 0) for r in rows) if rows else None,
        "total_threads_max": resources["total_threads_max"],
        "concurrent_processes_max": resources["concurrent_processes_max"],
        "startup_wall_seconds_median": median([r["startup_wall_seconds"] for r in rows]),
        "startup_cpu_seconds_median": median([r["startup_cpu_seconds"] for r in rows]),
        "import_wall_seconds_median": median([r["import_wall_seconds"] for r in rows]),
        "import_cpu_seconds_median": median([r["import_cpu_seconds"] for r in rows]),
        "voluntary_switches_per_game_median": median([r["voluntary_switches"] for r in rows]),
        "involuntary_switches_per_game_median": median([r["involuntary_switches"] for r in rows]),
        "involuntary_switches_at_start_median": median([r["startup_involuntary"] for r in rows]),
        "main_thread_involuntary_median": median([r["split"].get("main_involuntary") for r in rows]),
        "other_threads_involuntary_median": median([r["split"].get("other_involuntary") for r in rows]),
        "main_thread_migrations_median": median([r["split"].get("main_migrations") for r in rows]),
        "other_threads_migrations_median": median([r["split"].get("other_migrations") for r in rows]),
        "main_thread_cpu_median": median([r["split"].get("main_cpu_seconds") for r in rows]),
        "other_threads_cpu_median": median([r["split"].get("other_cpu_seconds") for r in rows]),
        "involuntary_self_over_wait4_median": median([(r["self_involuntary"] / r["involuntary_switches"])
                                                      if r["involuntary_switches"] else None for r in rows]),
        "max_rss_kib_per_game": cq.percentiles([r["max_rss_kib"] for r in rows]),
        "peak_total_rss_kib": resources["peak_total_rss_kib"], "peak_rss_fraction": resources["peak_total_rss_kib"] / mem_total,
        "block_output_total": sum(r["block_output"] or 0 for r in rows),
        "latency": latency, "per_config": per_config,
        "gc_gen2_max_ms": max((r["gc_gen2_max_ms"] for r in rows), default=None),
        "gc_pauses_over_50ms": sum(r["gc_kept"] for r in rows),
        "equivalence": {
            "deterministic_identical": sum(1 for v in comparisons.values() if v["class"] == "deterministic" and v["pass"]),
            "deterministic_games": sum(1 for v in comparisons.values() if v["class"] == "deterministic"),
            "stochastic_prefix_equal": sum(1 for v in comparisons.values() if v["class"] == "stochastic" and v["pass"]),
            "stochastic_games": sum(1 for v in comparisons.values() if v["class"] == "stochastic"),
            "duplicate_chain_groups": len(duplicates),
            "agreement_min_over_first_shot": min(((d["agreement_max"] - d["first_shot"]) for d in divergences.values()
                                                  if d["first_shot"] is not None), default=None),
            "agreement_max_median": median([d["agreement_max"] for d in divergences.values()]),
        },
        "probe": {"games": len(probe), "games_with_blas_calls": sum(1 for v in probe.values() if v),
                  "calls": {name: sum(v.get(name, 0) for v in probe.values()) for name in sorted({n for v in probe.values() for n in v})}}
        if spec.get("probe") else None,
        "gpu": {"ours_on_gpu": resources["ours_on_gpu"], "gpu_library_mapped": resources["libraries"]["gpu"]},
        "libraries": resources["libraries"], "inet_socket_observations": resources["inet_socket_observations"],
        "unix_socket_observations": resources["unix_socket_observations"],
        "descriptor_snapshots": resources["descriptor_snapshots"], "ledger": {"sessions": ledger["sessions"]},
        "batches": max((r.batch for r in results), default=-1) + 1,
        "safety_pass": not problems, "independence_pass": not equivalence_problems,
        "engine_state_pass": not engine_problems, "ledger_pass": not ledger_problems,
        "precheck_others_cpus": collected["precheck"]["checks"][-1]["others_cpus"],
    }
    return {"tier": tier, "attempt": collected["attempt"],
            "attempt_order": (folder / "collected.json").stat().st_mtime_ns, "commit": collected["commit"],
            "dirty": collected["dirty"], "plan_sha256": rt.digest(plan), "public": public, "games": rows,
            "resources": resources, "ledger": ledger, "comparisons": comparisons, "divergences": divergences,
            "probe": probe, "problems": problems + engine_problems + ledger_problems + equivalence_problems}


# ----------------------------------------------------------------------------------------------
# process-level check (no engine)

CHILD = '''
import hashlib, json, os, sys, time
def threads():
    return len(os.listdir("/proc/self/task"))
def cpu():
    t = os.times()
    return t.user + t.system
before, c0, w0 = threads(), cpu(), time.perf_counter()
import numpy as np
w1, c1, after = time.perf_counter(), cpu(), threads()
time.sleep(float(sys.argv[1]))
c2 = cpu()
libs = sorted({line.split()[-1].rsplit("/", 1)[-1] for line in open("/proc/self/maps")
               if "/" in line and any(k in line for k in ("blas", "gomp", "lapack", "mkl"))})
out = {"threads_before": before, "threads_after": after, "import_wall": w1 - w0, "import_cpu": c1 - c0,
       "settled_cpu": c2 - c0, "libraries": libs}
if sys.argv[2] == "sanity":
    a = np.arange(1000, dtype=np.float64) / 7.0
    b = np.arange(200000, dtype=np.float64) / 7.0
    m = (np.arange(1600, dtype=np.float64).reshape(40, 40) % 13) / 3.0
    g = (np.arange(250000, dtype=np.float64).reshape(500, 500) % 17) / 3.0
    s = np.eye(50) * 3.0 + (np.arange(2500, dtype=np.float64).reshape(50, 50) % 5) / 10.0
    out["sanity"] = {"dot_1000": float(np.dot(a, a)).hex(), "dot_200000": float(np.dot(b, b)).hex(),
                     "matmul_40": hashlib.sha256((m @ m).tobytes()).hexdigest(),
                     "matmul_500": hashlib.sha256((g @ g).tobytes()).hexdigest(),
                     "solve_50": hashlib.sha256(np.linalg.solve(s, np.ones(50)).tobytes()).hexdigest()}
print(json.dumps(out))
'''


def run_children(python: str, env: Dict[str, str], count: int, settle: float, mode: str) -> List[Dict[str, Any]]:
    """Start ``count`` fresh interpreters at once; collect their reports and their exact usage from wait4."""
    procs = [subprocess.Popen([python, "-c", CHILD, str(settle), mode], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for _ in range(count)]
    rows = []
    for proc in procs:
        out, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"child failed: {err[-500:]}")
        rows.append(json.loads(out))
    return rows


def cmd_process(args: argparse.Namespace) -> int:
    import resource

    plan = load_plan()
    check = plan["process_check"]
    out = WORK / "process"
    out.mkdir(parents=True, exist_ok=True)
    base = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "CUDA_VISIBLE_DEVICES": ""}
    report: Dict[str, Any] = {}
    for name, variables in plan["environments"].items():
        env = dict(base, **variables)
        entry: Dict[str, Any] = {"serial": [], "concurrent": {}, "sanity": []}
        for _ in range(check["serial_repetitions"]):
            mark = resource.getrusage(resource.RUSAGE_CHILDREN)
            row = run_children(args.python, env, 1, check["settle_seconds"], "import")[0]
            now = resource.getrusage(resource.RUSAGE_CHILDREN)
            row["involuntary_switches"] = now.ru_nivcsw - mark.ru_nivcsw
            row["voluntary_switches"] = now.ru_nvcsw - mark.ru_nvcsw
            entry["serial"].append(row)
        for count in check["concurrent"]:
            rounds = []
            for _ in range(check["rounds"]):
                mark = resource.getrusage(resource.RUSAGE_CHILDREN)
                rows = run_children(args.python, env, count, check["settle_seconds"], "import")
                now = resource.getrusage(resource.RUSAGE_CHILDREN)
                rounds.append({"children": count, "rows": rows,
                               "involuntary_per_child": (now.ru_nivcsw - mark.ru_nivcsw) / count,
                               "voluntary_per_child": (now.ru_nvcsw - mark.ru_nvcsw) / count,
                               "cpu_per_child": ((now.ru_utime + now.ru_stime) - (mark.ru_utime + mark.ru_stime)) / count})
            entry["concurrent"][str(count)] = rounds
        for _ in range(check["sanity_repetitions"]):
            entry["sanity"].append(run_children(args.python, env, 1, 0.0, "sanity")[0])
        report[name] = entry
        print(f"environment {name}: done", flush=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    with open(out / f"process-{stamp}.json", "x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(process_summary(report), indent=1, sort_keys=True))
    return 0


def process_summary(report: Mapping[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for name, entry in report.items():
        serial = entry["serial"]
        concurrent = {}
        for count, rounds in entry["concurrent"].items():
            concurrent[count] = {"involuntary_per_child": median([r["involuntary_per_child"] for r in rounds]),
                                 "voluntary_per_child": median([r["voluntary_per_child"] for r in rounds]),
                                 "cpu_per_child": median([r["cpu_per_child"] for r in rounds]),
                                 "import_wall_median": median([row["import_wall"] for r in rounds for row in r["rows"]])}
        sanity = entry["sanity"]
        summary[name] = {
            "threads_before": sorted({r["threads_before"] for r in serial}),
            "threads_after": sorted({r["threads_after"] for r in serial}),
            "import_wall_median": median([r["import_wall"] for r in serial]),
            "import_cpu_median": median([r["import_cpu"] for r in serial]),
            "settled_cpu_median": median([r["settled_cpu"] for r in serial]),
            "involuntary_median": median([r["involuntary_switches"] for r in serial]),
            "libraries": sorted({lib for r in serial for lib in r["libraries"]}),
            "concurrent": concurrent,
            "sanity_consistent": all(s["sanity"] == sanity[0]["sanity"] for s in sanity),
            "sanity": sanity[0]["sanity"] if sanity else None,
        }
    if "A" in summary and "B" in summary and summary["A"]["sanity"] and summary["B"]["sanity"]:
        summary["sanity_equal_between_environments"] = {
            key: summary["A"]["sanity"][key] == summary["B"]["sanity"][key] for key in summary["A"]["sanity"]}
    return summary


# ----------------------------------------------------------------------------------------------
# analyze


def analyse(plan: Mapping[str, Any]) -> Dict[str, Any]:
    done = summaries(plan)
    tiers = {name: dict(done[name]["public"]) for name in rt.sequence(plan) if name in done}
    committed = json.loads(CQ_RESULTS.read_text(encoding="utf-8"))
    cq_tiers = {t["tier"]: t for t in committed["tiers"]}
    base_b = tiers.get("B-w01")
    for name, tier in tiers.items():
        if name.startswith("B-w") and base_b:
            criteria = rt.worker_criteria(tier, base_b)
            tier["criteria"] = criteria
            tier["speedup"] = criteria["throughput"]["speedup"]
            tier["efficiency"] = criteria["efficiency"]["efficiency"]
        if name.startswith("A-w"):
            tier["speedup_vs_committed_w01"] = tier["throughput_games_per_hour"] / cq_tiers["w01"]["throughput_games_per_hour"]
            tier["efficiency_vs_committed_w01"] = tier["speedup_vs_committed_w01"] / tier["workers"]
    comparison = {}
    for n in (16, 24):
        a, b, old = tiers.get(f"A-w{n}"), tiers.get(f"B-w{n}"), cq_tiers.get(f"w{n:02d}")
        if a and b:
            comparison[f"w{n}"] = {
                "throughput_ratio_b_over_a": b["throughput_games_per_hour"] / a["throughput_games_per_hour"],
                "cpu_per_game_ratio_b_over_a": b["cpu_seconds_per_game_median"] / a["cpu_seconds_per_game_median"],
                "max_latency_ratio_b_over_a": b["latency"]["max_ms"] / a["latency"]["max_ms"],
                "committed_involuntary_per_game_median": old["involuntary_switches_per_game_median"] if old else None,
                "committed_throughput": old["throughput_games_per_hour"] if old else None,
                "committed_max_latency_ms": old["latency"]["max_ms"] if old else None,
            }
    process_files = sorted((WORK / "process").glob("process-*.json"))
    process = process_summary(json.loads(process_files[-1].read_text(encoding="utf-8"))) if process_files else None
    return {"tiers": tiers, "comparison": comparison, "disposition": rt.disposition(tiers), "process_level": process,
            "commits": sorted({s["commit"] for s in done.values()})}


def cmd_analyze(args: argparse.Namespace) -> int:
    plan = load_plan()
    analysis = analyse(plan)
    results = {"schema": "miaosuan-runtime-thread-results/1", "plan_id": rt.PLAN_ID, "plan_sha256": rt.digest(plan),
               **analysis}
    text = json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        if not RESULTS.is_file() or RESULTS.read_text(encoding="utf-8") != text:
            print("results differ", file=sys.stderr)
            return 1
        print("results identical")
        return 0
    RESULTS.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(analysis["disposition"], indent=1, default=str)[:2000])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--sdk-archive", type=Path, required=True)
    stage.set_defaults(func=cmd_stage)
    probe = sub.add_parser("build-probe")
    probe.set_defaults(func=cmd_build_probe)
    process = sub.add_parser("process", help="the registered process-level check, without the engine")
    process.add_argument("--python", default=sys.executable)
    process.set_defaults(func=cmd_process)
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
    tier.add_argument("--tier", required=True)
    tier.add_argument("--attempt")
    tier.add_argument("--python", default=sys.executable)
    tier.set_defaults(func=cmd_tier)
    resummarize = sub.add_parser("resummarize")
    resummarize.add_argument("--tier", required=True)
    resummarize.add_argument("--attempt")
    resummarize.set_defaults(func=lambda a: write_summary(load_plan(), tier_folder(a.tier, a.attempt)))
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--check", action="store_true")
    analyze.set_defaults(func=cmd_analyze)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
