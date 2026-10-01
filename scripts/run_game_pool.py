"""Play registered games several at a time: the parallel path of ``scripts/run_evaluation.sh --workers N``.

    PYTHON scripts/run_game_pool.py --evaluation NAME --work DIR --engine-install DIR --workers N
        --games-file FILE --harness-commit SHA [--harness-dirty] [--purpose evaluation|diagnostic]
        [--timeout SECONDS] [--stop-after-failures K]

``run_evaluation.sh`` calls this after its registered pre-run checks, with the plan's games in registered
order. Each game is the serial loop's command in the serial loop's isolation, with two differences: its own
working directory (``WORK/cwd/<game>/a/b``) and a shared engine session whose record names the worker count,
the worker, the batch (dispatch wave) and the scheduler identity. Games are dispatched in queue order, at
most N at a time, by ``src/miaosuan_agent/evaluation/scheduler.py``. ``--runtime`` names the runtime identity;
its numerical-thread variables (``src/miaosuan_agent/evaluation/execution.py``) are added to every game's
environment, and the game checks them. ``--expected-scheduler`` refuses the run unless this scheduler's identity
is the registered one.

A game with a record is skipped. A game that was started earlier and left no record stops the run before
any game starts, as in the serial loop, because rerunning it would select among outcomes. Nothing is retried
and no record, marker or log is overwritten. Dispatch stops after K consecutive games that did not complete
(in completion order; 0 disables), on any exit status other than 0 and 1, and on SIGINT or SIGTERM, whose
running games are terminated and recorded as interrupted by their own sessions. No session may be unclosed
before the run, and none after it.

Exit status: 0 every started game exited 0 or 1; 1 the consecutive-failure stop or a stale start; 4 an
unclosed session; otherwise the first other exit status of a game, or 128 + signal after cancellation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import signal
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install as ei  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import scheduler  # noqa: E402

SCHEDULER_SOURCES = ("src/miaosuan_agent/evaluation/scheduler.py", "scripts/run_game_pool.py")
GAME_SCRIPT = REPO_ROOT / "scripts" / "run_evaluation.py"


def scheduler_identity(root: Path = REPO_ROOT) -> str:
    """``<scheduler id>@<sha256 over the scheduler's source files>``, recorded with every parallel game."""
    digest = hashlib.sha256()
    for rel in SCHEDULER_SOURCES:
        data = (root / rel).read_bytes()
        digest.update(f"{rel}\0{len(data)}\0".encode("utf-8"))
        digest.update(data)
    return f"{scheduler.SCHEDULER_ID}@{digest.hexdigest()}"


def isolation_env(install: ei.EngineInstall, runtime: str = ex.DEFAULT_RUNTIME) -> Dict[str, str]:
    """The serial loop's ``env -i`` environment plus the runtime's numerical-thread variables (none for r1)."""
    return {"HOME": str(install.home), "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
            "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": f"{install.site}:{REPO_ROOT / 'src'}", **ex.runtime_env(runtime)}


def plan_queue(games: Sequence[str], work: Path) -> Tuple[List[str], List[str], List[str]]:
    """(games to play, games already recorded, games started earlier without a record)."""
    queue, recorded, stale = [], [], []
    for game in games:
        if (work / "games" / f"{game}.json").exists():
            recorded.append(game)
        elif (work / "started" / game).exists():
            stale.append(game)
        else:
            queue.append(game)
    return queue, recorded, stale


def stop_rule(consecutive: int) -> scheduler.StopRule:
    """Stop dispatch on an exit status other than 0 and 1, or after ``consecutive`` non-completions (0: never)."""
    tail_rule = scheduler.stop_after_consecutive_failures(consecutive) if consecutive > 0 else None

    def rule(results: Sequence[scheduler.Result]) -> bool:
        last = results[-1]
        if last.start_error is not None or (last.exit_code not in (0, 1) and not last.cancelled):
            return True
        return bool(tail_rule and tail_rule(results))
    return rule


def game_argv(python: str, game_script: Path, evaluation: str, work: Path, game: str, install: ei.EngineInstall,
              commit: str, dirty: bool, purpose: str, workers: int, worker: int, batch: int, identity: str,
              runtime: str = ex.DEFAULT_RUNTIME) -> List[str]:
    return ([python, str(game_script), "--evaluation", evaluation, "--work", str(work), "game", "--game-id", game,
             "--engine-install", str(install.root), "--harness-commit", commit] + (["--harness-dirty"] if dirty else [])
            + ["--purpose", purpose, "--session-mode", "shared", "--workers", str(workers), "--worker", str(worker),
               "--batch", str(batch), "--scheduler", identity, "--runtime", runtime])


def exit_status(report: scheduler.PoolReport, signum: Optional[int]) -> int:
    if report.cancelled:
        return 128 + (signum or signal.SIGTERM)
    for result in report.results:
        if result.start_error is not None:
            return 2
        if result.timed_out:
            return 124  # what timeout(1) returns in the serial loop
        if result.exit_code not in (0, 1):
            return result.exit_code if result.exit_code > 0 else 128 - result.exit_code
    return 1 if report.stopped_by_rule else 0


def run(args: argparse.Namespace, game_script: Path = GAME_SCRIPT,
        launcher: Callable[..., scheduler.Handle] = scheduler.ProcessGame) -> int:
    work = Path(args.work).resolve()
    games = [line.strip() for line in Path(args.games_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(set(games)) != len(games):
        print("REFUSED: the games file lists a game twice", file=sys.stderr)
        return 2
    queue, recorded, stale = plan_queue(games, work)
    for game in recorded:
        print(f"recorded already: {game}")
    if stale:
        print(f"STOP: {stale} were started earlier and left no record; investigate and document before rerunning",
              file=sys.stderr)
        return 1
    install = ei.EngineInstall(Path(args.engine_install).resolve())
    try:
        with ei.exclusive_window(install):
            unclosed = ei.unclosed_sessions(ei.read_ledger(install))
    except ei.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    if unclosed:
        print(f"REFUSED: the ledger shows unclosed sessions {unclosed}; investigate before a parallel run",
              file=sys.stderr)
        return 4
    identity = scheduler_identity()
    expected = getattr(args, "expected_scheduler", None)
    if expected and expected != identity:
        print(f"REFUSED: the manifest registers scheduler {expected}; this scheduler is {identity}", file=sys.stderr)
        return 2
    runtime = getattr(args, "runtime", None) or ex.DEFAULT_RUNTIME
    try:
        env = isolation_env(install, runtime)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    for sub in ("games", "started", "logs", "cwd", "pool"):
        (work / sub).mkdir(parents=True, exist_ok=True)

    def start(job: scheduler.Job, worker: int, batch: int) -> scheduler.Handle:
        with open(work / "started" / job.game_id, "x", encoding="utf-8") as marker:
            marker.write(dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
        cwd = work / "cwd" / job.game_id / "a" / "b"
        cwd.mkdir(parents=True)
        argv = game_argv(args.python, game_script, args.evaluation, work, job.game_id, install, args.harness_commit,
                         args.harness_dirty, args.purpose, args.workers, worker, batch, identity, runtime)
        return launcher(argv, env, cwd, work / "logs" / f"{job.game_id}.log")

    def finished(result: scheduler.Result) -> None:
        log = work / "logs" / f"{result.job.game_id}.log"
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
        print(lines[-1] if lines else f"{result.job.game_id}: no output", flush=True)
        if not result.completed:
            print(f"game {result.job.game_id} exited with status {result.exit_code} (worker {result.worker}, batch "
                  f"{result.batch}, timed out {result.timed_out}, cancelled {result.cancelled})", file=sys.stderr)

    jobs = [scheduler.Job(index=k, game_id=game) for k, game in enumerate(queue)]
    pool = scheduler.Pool(jobs, args.workers, start, timeout_seconds=args.timeout, kill_after_seconds=30,
                          stop_rule=stop_rule(args.stop_after_failures), on_result=finished)
    received: List[int] = []

    def cancel(signum: int, frame: object) -> None:
        received.append(signum)
        pool.cancel()

    signal.signal(signal.SIGINT, cancel)
    signal.signal(signal.SIGTERM, cancel)
    print(f"pool: {len(queue)} games, {args.workers} workers, runtime {runtime} {ex.runtime_env(runtime)}, "
          f"scheduler {identity}", flush=True)
    report = pool.run()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with open(work / "pool" / f"run-{stamp}.json", "x", encoding="utf-8") as handle:
        handle.write(json.dumps({"scheduler": identity, "workers": args.workers, "runtime": runtime,
                                 "thread_env": ex.runtime_env(runtime), "queue": queue,
                                 "not_started": [j.game_id for j in report.not_started],
                                 "stopped_by_rule": report.stopped_by_rule, "cancelled": report.cancelled,
                                 "wall_seconds": report.wall_seconds,
                                 "results": [{"game_id": r.job.game_id, "worker": r.worker, "batch": r.batch,
                                              "exit_code": r.exit_code, "started": r.started, "finished": r.finished,
                                              "timed_out": r.timed_out, "cancelled": r.cancelled,
                                              "start_error": r.start_error, "leftover_processes": r.leftover_processes,
                                              "usage": r.usage} for r in report.results]},
                                indent=1, sort_keys=True) + "\n")
    try:
        with ei.exclusive_window(install):
            unclosed = ei.unclosed_sessions(ei.read_ledger(install))
    except ei.InstallRefused as exc:
        print(f"PROBLEM: a session still holds the installation after the run: {exc}", file=sys.stderr)
        return 4
    if unclosed:
        print(f"PROBLEM: unclosed sessions after the run: {unclosed}", file=sys.stderr)
        return 4
    failures = sum(1 for r in report.results if not r.completed)
    print(f"pool finished: {len(report.results)} started, {failures} not completed, {len(report.not_started)} not "
          f"started, {len(recorded)} recorded already, {report.wall_seconds:.1f}s")
    return exit_status(report, received[0] if received else None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--engine-install", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--games-file", required=True)
    parser.add_argument("--harness-commit", required=True)
    parser.add_argument("--harness-dirty", action="store_true")
    parser.add_argument("--purpose", default="evaluation", choices=("evaluation", "diagnostic"))
    parser.add_argument("--timeout", type=float, default=2100.0)
    parser.add_argument("--stop-after-failures", type=int, default=0)
    parser.add_argument("--runtime", default=ex.DEFAULT_RUNTIME,
                        help="runtime identity; its numerical-thread variables are added to every game's environment")
    parser.add_argument("--expected-scheduler", help="refuse unless this scheduler's identity equals the registered one")
    args = parser.parse_args()
    if args.workers < 2:
        print("the pool is for two or more workers; one worker is the serial loop of run_evaluation.sh",
              file=sys.stderr)
        return 2
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
