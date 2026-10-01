"""A bounded, deterministic pool of engine games: one process per game, at most ``workers`` at a time.

Dispatch follows the queue order exactly. A game goes to the lowest-numbered free worker slot, and its
batch is its dispatch index divided by the worker count (the dispatch wave), so a registered queue that
alternates its groups puts both groups into every batch. Nothing is ever retried: a game that fails,
times out or is cancelled is reported as such, and a stop rule only prevents further dispatch. The pool
does not know what a game is; ``start`` launches one and returns a handle that can wait for it, signal
its process group and report processes the game left behind.

:class:`ProcessGame` is the POSIX handle: the game runs in a new session (its own process group), its
output goes to a log file that must not exist yet, and it is reaped with ``wait4`` so that its exact CPU
time, peak resident set and context switches are known.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

SCHEDULER_ID = "miaosuan-game-pool/1"


@dataclass(frozen=True)
class Job:
    index: int
    game_id: str
    group: Optional[str] = None


@dataclass
class Result:
    job: Job
    worker: int
    batch: int
    exit_code: Optional[int]
    started: float
    finished: float
    timed_out: bool = False
    cancelled: bool = False
    start_error: Optional[str] = None
    leftover_processes: bool = False
    usage: Dict[str, float] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return self.exit_code == 0 and not (self.timed_out or self.cancelled or self.leftover_processes)


@dataclass
class PoolReport:
    workers: int
    results: List[Result]
    not_started: List[Job]
    stopped_by_rule: bool
    cancelled: bool
    wall_seconds: float


class Handle(Protocol):
    def wait(self) -> Tuple[int, Dict[str, float]]: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def leftovers(self) -> bool: ...


StartFn = Callable[[Job, int, int], Handle]
StopRule = Callable[[Sequence[Result]], bool]


def stop_on_first_failure(results: Sequence[Result]) -> bool:
    return bool(results) and not results[-1].completed


def stop_after_consecutive_failures(count: int) -> StopRule:
    """Stop dispatching after ``count`` consecutive results, in completion order, that did not complete."""
    def rule(results: Sequence[Result]) -> bool:
        tail = results[-count:]
        return len(tail) == count and not any(r.completed for r in tail)
    return rule


class Pool:
    """Run ``jobs`` with at most ``workers`` games at a time. Use :meth:`run`; :meth:`cancel` is thread-safe."""

    def __init__(self, jobs: Sequence[Job], workers: int, start: StartFn, *, timeout_seconds: float,
                 kill_after_seconds: float = 30.0, stop_rule: Optional[StopRule] = None,
                 on_result: Optional[Callable[[Result], None]] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        if [job.index for job in jobs] != list(range(len(jobs))):
            raise ValueError("job indexes must be the queue positions 0..n-1 in order")
        if len({job.game_id for job in jobs}) != len(jobs):
            raise ValueError("game ids in the queue must be unique")
        self.jobs, self.workers, self.start = list(jobs), workers, start
        self.timeout, self.kill_after = timeout_seconds, kill_after_seconds
        self.stop_rule, self.on_result, self.clock = stop_rule, on_result, clock
        self._cond = threading.Condition()
        self._free = set(range(workers))
        self._running: Dict[int, Handle] = {}
        self._results: List[Result] = []
        self._stop = False
        self._stopped_by_rule = False
        self._cancelled = False
        self._t0 = 0.0

    def cancel(self) -> None:
        """Stop dispatching and send SIGTERM to every running game; they are reported as cancelled."""
        with self._cond:
            self._cancelled = self._stop = True
            running = list(self._running.values())
            self._cond.notify_all()
        for handle in running:
            handle.terminate()

    def _now(self) -> float:
        return self.clock() - self._t0

    def _watch(self, job: Job, worker: int, batch: int, handle: Handle, started: float) -> None:
        timed_out = threading.Event()

        def expire() -> None:
            timed_out.set()
            handle.terminate()
            killer = threading.Timer(self.kill_after, handle.kill)
            killer.daemon = True
            killer.start()

        timer = threading.Timer(self.timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            code, usage = handle.wait()
        finally:
            timer.cancel()
        leftover = handle.leftovers()
        if leftover:
            handle.kill()
        with self._cond:
            result = Result(job=job, worker=worker, batch=batch, exit_code=code, started=started, finished=self._now(),
                            timed_out=timed_out.is_set(), cancelled=self._cancelled and code != 0,
                            leftover_processes=leftover,
                            usage=dict(usage))
            self._results.append(result)
            if self.stop_rule is not None and self.stop_rule(self._results):
                self._stop = self._stopped_by_rule = True
            del self._running[worker]
            self._free.add(worker)
            self._cond.notify_all()
        if self.on_result is not None:
            self.on_result(result)

    def run(self) -> PoolReport:
        self._t0 = self.clock()
        watchers: List[threading.Thread] = []
        pending = list(self.jobs)
        dispatched = 0
        while pending:
            with self._cond:
                while not self._free and not self._stop:
                    self._cond.wait()
                if self._stop:
                    break
                worker = min(self._free)
                self._free.discard(worker)
            job = pending.pop(0)
            batch = dispatched // self.workers
            dispatched += 1
            started = self._now()
            try:
                handle = self.start(job, worker, batch)
            except Exception as exc:  # noqa: BLE001 - a launch failure is a result, never a silent skip
                with self._cond:
                    self._results.append(Result(job=job, worker=worker, batch=batch, exit_code=None, started=started,
                                                finished=self._now(), start_error=f"{type(exc).__name__}: {exc}"))
                    self._stop = self._stopped_by_rule = True
                    self._free.add(worker)
                break
            with self._cond:
                self._running[worker] = handle
            thread = threading.Thread(target=self._watch, args=(job, worker, batch, handle, started), daemon=True)
            thread.start()
            watchers.append(thread)
        for thread in watchers:
            thread.join()
        started_ids = {r.job.game_id for r in self._results}
        return PoolReport(workers=self.workers, results=list(self._results),
                          not_started=[job for job in self.jobs if job.game_id not in started_ids],
                          stopped_by_rule=self._stopped_by_rule, cancelled=self._cancelled,
                          wall_seconds=self._now())


class ProcessGame:
    """A game process in its own session; output to a new log file; reaped with ``wait4``. POSIX only."""

    def __init__(self, argv: Sequence[str], env: Mapping[str, str], cwd: Path, log: Path) -> None:
        with open(log, "x", encoding="utf-8") as handle:
            self.proc = subprocess.Popen(list(argv), env=dict(env), cwd=str(cwd), stdout=handle,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.pid = self.proc.pid

    def wait(self) -> Tuple[int, Dict[str, float]]:
        _, status, usage = os.wait4(self.pid, 0)
        code = os.waitstatus_to_exitcode(status)
        self.proc.returncode = code
        return code, {"cpu_user_seconds": usage.ru_utime, "cpu_system_seconds": usage.ru_stime,
                      "max_rss_kib": float(usage.ru_maxrss), "voluntary_switches": float(usage.ru_nvcsw),
                      "involuntary_switches": float(usage.ru_nivcsw), "block_input": float(usage.ru_inblock),
                      "block_output": float(usage.ru_oublock)}

    def _signal(self, number: int) -> None:
        try:
            os.killpg(self.pid, number)
        except (ProcessLookupError, PermissionError):
            pass

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)

    def leftovers(self) -> bool:
        """Whether any process is still in the game's process group after the game itself was reaped."""
        try:
            os.killpg(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
