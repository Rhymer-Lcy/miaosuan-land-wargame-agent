"""The bounded game pool: dispatch order, worker slots, batches, stop rules, timeouts and cancellation.

Fake handles stand in for game processes, so the dispatch logic is tested on every platform; the POSIX
process handle is exercised with tiny Python child processes where it is available.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import scheduler as sc


class FakeGame:
    def __init__(self, duration: float, code: int = 0, leftover: bool = False) -> None:
        self.duration, self.code, self.leftover = duration, code, leftover
        self.done = threading.Event()
        self.signals = []

    def wait(self):
        if not self.done.wait(self.duration):
            pass
        return (self.code if not self.signals else -15), {"cpu_user_seconds": self.duration}

    def terminate(self) -> None:
        self.signals.append("TERM")
        self.done.set()

    def kill(self) -> None:
        self.signals.append("KILL")
        self.done.set()

    def leftovers(self) -> bool:
        return self.leftover


def jobs(n: int):
    return [sc.Job(index=i, game_id=f"g{i:02d}", group="BC"[i % 2]) for i in range(n)]


class PoolTest(unittest.TestCase):
    def run_pool(self, durations, workers, codes=None, **kwargs):
        codes = codes or {}
        order, lock, games = [], threading.Lock(), {}

        def start(job, worker, batch):
            with lock:
                order.append((job.game_id, worker, batch))
            games[job.game_id] = FakeGame(durations[job.index], codes.get(job.index, 0))
            return games[job.game_id]

        kwargs.setdefault("timeout_seconds", 30)
        report = sc.Pool(jobs(len(durations)), workers, start, **kwargs).run()
        return report, order, games

    def test_dispatch_follows_the_queue_and_never_exceeds_the_workers(self) -> None:
        active, peak, lock = [0], [0], threading.Lock()

        class Counting(FakeGame):
            def wait(self):
                with lock:
                    active[0] += 1
                    peak[0] = max(peak[0], active[0])
                result = super().wait()
                with lock:
                    active[0] -= 1
                return result

        order = []

        def start(job, worker, batch):
            order.append(job.game_id)
            return Counting(0.02 + 0.01 * (job.index % 3))

        report = sc.Pool(jobs(12), 3, start, timeout_seconds=30).run()
        self.assertEqual(order, [f"g{i:02d}" for i in range(12)])
        self.assertLessEqual(peak[0], 3)
        self.assertEqual(len(report.results), 12)
        self.assertTrue(all(r.completed for r in report.results))
        self.assertEqual(report.not_started, [])

    def test_first_wave_takes_slots_in_order_and_batches_are_dispatch_waves(self) -> None:
        report, order, _ = self.run_pool([0.05] * 8, 4)
        self.assertEqual([(g, w) for g, w, _ in order[:4]], [("g00", 0), ("g01", 1), ("g02", 2), ("g03", 3)])
        self.assertEqual([b for _, _, b in order], [0, 0, 0, 0, 1, 1, 1, 1])
        self.assertEqual({r.batch for r in report.results}, {0, 1})

    def test_a_free_slot_is_the_lowest_numbered(self) -> None:
        report, order, _ = self.run_pool([0.30, 0.05, 0.30, 0.30], 3)
        self.assertEqual(order[3][1], 1)

    def test_stop_on_first_failure_stops_dispatch_without_retrying(self) -> None:
        report, order, _ = self.run_pool([0.01, 0.01, 0.01, 0.01, 0.01], 1, codes={1: 1},
                                         stop_rule=sc.stop_on_first_failure)
        self.assertEqual([g for g, _, _ in order], ["g00", "g01"])
        self.assertTrue(report.stopped_by_rule)
        self.assertEqual([j.game_id for j in report.not_started], ["g02", "g03", "g04"])

    def test_consecutive_failure_rule(self) -> None:
        rule = sc.stop_after_consecutive_failures(3)
        ok = sc.Result(job=jobs(1)[0], worker=0, batch=0, exit_code=0, started=0, finished=1)
        bad = sc.Result(job=jobs(1)[0], worker=0, batch=0, exit_code=1, started=0, finished=1)
        self.assertFalse(rule([bad, bad]))
        self.assertFalse(rule([bad, ok, bad, bad]))
        self.assertTrue(rule([ok, bad, bad, bad]))

    def test_timeout_terminates_and_is_reported(self) -> None:
        report, _, games = self.run_pool([5.0], 1, timeout_seconds=0.05, kill_after_seconds=0.05)
        result = report.results[0]
        self.assertTrue(result.timed_out)
        self.assertFalse(result.completed)
        self.assertIn("TERM", games["g00"].signals)

    def test_cancel_terminates_running_games_and_starts_no_more(self) -> None:
        games = {}

        def start(job, worker, batch):
            games[job.game_id] = FakeGame(5.0)
            return games[job.game_id]

        pool = sc.Pool(jobs(6), 2, start, timeout_seconds=30)
        threading.Timer(0.1, pool.cancel).start()
        report = pool.run()
        self.assertTrue(report.cancelled)
        self.assertEqual(sorted(games), ["g00", "g01"])
        self.assertTrue(all(r.cancelled and not r.completed for r in report.results))
        self.assertEqual(len(report.not_started), 4)

    def test_launch_failure_is_a_result_and_stops(self) -> None:
        def start(job, worker, batch):
            if job.index == 1:
                raise OSError("log exists")
            return FakeGame(0.01)

        report = sc.Pool(jobs(4), 1, start, timeout_seconds=30).run()
        self.assertEqual(report.results[1].start_error, "OSError: log exists")
        self.assertTrue(report.stopped_by_rule)
        self.assertEqual(len(report.not_started), 2)

    def test_leftover_processes_fail_the_game(self) -> None:
        def start(job, worker, batch):
            return FakeGame(0.01, leftover=True)

        report = sc.Pool(jobs(1), 1, start, timeout_seconds=30).run()
        self.assertTrue(report.results[0].leftover_processes)
        self.assertFalse(report.results[0].completed)

    def test_invalid_queues_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            sc.Pool([sc.Job(1, "a")], 1, lambda *a: None, timeout_seconds=1)
        with self.assertRaises(ValueError):
            sc.Pool([sc.Job(0, "a"), sc.Job(1, "a")], 1, lambda *a: None, timeout_seconds=1)
        with self.assertRaises(ValueError):
            sc.Pool(jobs(1), 0, lambda *a: None, timeout_seconds=1)


@unittest.skipUnless(hasattr(os, "wait4") and importlib.util.find_spec("fcntl"), "POSIX process handles")
class ProcessGameTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_exit_code_usage_and_log(self) -> None:
        game = sc.ProcessGame([sys.executable, "-c", "print('hello'); raise SystemExit(3)"], dict(os.environ),
                              self.tmp, self.tmp / "g.log")
        code, usage = game.wait()
        self.assertEqual(code, 3)
        self.assertIn("max_rss_kib", usage)
        self.assertEqual((self.tmp / "g.log").read_text(encoding="utf-8").strip(), "hello")
        self.assertFalse(game.leftovers())

    def test_existing_log_refuses_the_launch(self) -> None:
        (self.tmp / "g.log").write_text("earlier", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            sc.ProcessGame([sys.executable, "-c", "pass"], dict(os.environ), self.tmp, self.tmp / "g.log")

    def test_terminate_signals_the_process_group(self) -> None:
        game = sc.ProcessGame([sys.executable, "-c", "import time; time.sleep(30)"], dict(os.environ), self.tmp,
                              self.tmp / "g.log")
        time.sleep(0.2)
        game.terminate()
        code, _ = game.wait()
        self.assertEqual(code, -15)

    def test_leftover_child_is_detected(self) -> None:
        script = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])"
        game = sc.ProcessGame([sys.executable, "-c", script], dict(os.environ), self.tmp, self.tmp / "g.log")
        game.wait()
        self.assertTrue(game.leftovers())
        game.kill()
        deadline = time.monotonic() + 5
        while game.leftovers() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(game.leftovers())


if __name__ == "__main__":
    unittest.main()
