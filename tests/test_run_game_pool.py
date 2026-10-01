"""The production parallel path: scripts/run_game_pool.py and its hooks in run_evaluation.sh and .py.

The end-to-end tests run the pool against a synthetic engine installation with a fake game script that
writes a record, so the queue, markers, logs, working directories, isolation, skips, stops and the
ledger guard are exercised without the engine. POSIX only where processes and file locks are involved.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from miaosuan_agent import engine_install as ei
from miaosuan_agent.evaluation import scheduler as sc

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pool = load_script("run_game_pool")

FAKE_GAME = r'''
import json, os, sys, time
argv = sys.argv
def arg(name):
    return argv[argv.index(name) + 1]
work, game = arg("--work"), arg("--game-id")
time.sleep(0.05)
record = {"game_id": game, "argv": argv[2:], "cwd": os.getcwd(), "env": sorted(os.environ)}
with open(os.path.join(work, "codes.json")) as handle:
    code = json.load(handle).get(game, 0)
if code == 0:
    with open(os.path.join(work, "games", game + ".json"), "x") as handle:
        json.dump(record, handle)
print("GAME", game, "exit", code)
sys.exit(code)
'''


def fake_installer(wheel: Path, target: Path) -> dict:
    (target / "pkg" / "state").mkdir(parents=True)
    (target / "pkg" / "state" / ".synthetic_state").write_bytes(b"")
    return {"command": ["fake"], "pip_version": "none"}


class PureTest(unittest.TestCase):
    def test_plan_queue_skips_records_and_flags_stale_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "games").mkdir()
            (work / "started").mkdir()
            (work / "games" / "a.json").write_text("{}", encoding="utf-8")
            (work / "started" / "a").write_text("t", encoding="utf-8")
            (work / "started" / "b").write_text("t", encoding="utf-8")
            self.assertEqual(pool.plan_queue(["a", "b", "c"], work), (["c"], ["a"], ["b"]))

    def test_stop_rule(self) -> None:
        job = sc.Job(0, "g")
        result = lambda code, **kw: sc.Result(job=job, worker=0, batch=0, exit_code=code, started=0, finished=1, **kw)
        self.assertTrue(pool.stop_rule(0)([result(4)]))
        self.assertTrue(pool.stop_rule(0)([result(-15)]))
        self.assertFalse(pool.stop_rule(0)([result(1), result(1), result(1)]))
        self.assertTrue(pool.stop_rule(3)([result(0), result(1), result(1), result(1)]))
        self.assertFalse(pool.stop_rule(3)([result(1), result(0), result(1), result(1)]))
        self.assertFalse(pool.stop_rule(0)([result(-15, cancelled=True)]))

    def test_exit_status(self) -> None:
        job = sc.Job(0, "g")
        report = lambda results, **kw: sc.PoolReport(workers=2, results=results, not_started=[], wall_seconds=1,
                                                      stopped_by_rule=kw.get("stopped", False),
                                                      cancelled=kw.get("cancelled", False))
        result = lambda code, **kw: sc.Result(job=job, worker=0, batch=0, exit_code=code, started=0, finished=1, **kw)
        self.assertEqual(pool.exit_status(report([result(0), result(1)]), None), 0)
        self.assertEqual(pool.exit_status(report([result(0), result(4)]), None), 4)
        self.assertEqual(pool.exit_status(report([result(-15, timed_out=True)]), None), 124)
        self.assertEqual(pool.exit_status(report([result(-9)]), None), 137)
        self.assertEqual(pool.exit_status(report([result(1)] * 3, stopped=True), None), 1)
        self.assertEqual(pool.exit_status(report([], cancelled=True), 2), 130)

    def test_scheduler_identity_covers_its_sources(self) -> None:
        identity = pool.scheduler_identity()
        self.assertTrue(identity.startswith(sc.SCHEDULER_ID + "@"))
        with tempfile.TemporaryDirectory() as tmp:
            for rel in pool.SCHEDULER_SOURCES:
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, Path(tmp) / rel)
            self.assertEqual(pool.scheduler_identity(Path(tmp)), identity)
            with open(Path(tmp) / pool.SCHEDULER_SOURCES[0], "a", encoding="utf-8") as handle:
                handle.write("\n# changed\n")
            self.assertNotEqual(pool.scheduler_identity(Path(tmp)), identity)

    def test_isolation_matches_the_serial_loop(self) -> None:
        text = (ROOT / "scripts" / "run_evaluation.sh").read_text(encoding="utf-8")
        block = text[text.index("env -i \\"):text.index("timeout --signal=TERM")]
        serial = sorted(re.findall(r"^\s+([A-Z_]+)=", block, flags=re.M))
        env = pool.isolation_env(ei.EngineInstall(Path("/x")))
        self.assertEqual(sorted(env), serial)
        self.assertEqual((env["PYTHONHASHSEED"], env["CUDA_VISIBLE_DEVICES"]), ("0", ""))

    def test_game_argv_requests_a_shared_session(self) -> None:
        argv = pool.game_argv("py", Path("g.py"), "E", Path("/w"), "id", ei.EngineInstall(Path("/i")), "c", True,
                              "diagnostic", 4, 2, 7, "pool@abc")
        self.assertEqual(argv[:4], ["py", "g.py", "--evaluation", "E"])
        joined = " ".join(argv)
        for part in (f"--work {Path('/w')} game --game-id id", "--harness-dirty", "--purpose diagnostic", "--session-mode shared",
                     "--workers 4", "--worker 2", "--batch 7", "--scheduler pool@abc"):
            self.assertIn(part, joined)

    def test_the_shell_runner_wires_the_pool_and_the_registered_count(self) -> None:
        text = (ROOT / "scripts" / "run_evaluation.sh").read_text(encoding="utf-8")
        self.assertIn('--workers) WORKERS=$2', text)
        self.assertIn("a registered run cannot use --workers", text)
        self.assertIn('scripts/run_game_pool.py" --evaluation "$NAME" --work "$WORK"', text)
        self.assertIn('--engine-install "$INSTALL" --purpose "$PURPOSE"', text)
        self.assertEqual(text.count("timeout --signal=TERM --kill-after=30"), 1)

    def test_a_shared_game_needs_its_execution_fields(self) -> None:
        rev = load_script("run_evaluation")
        args = argparse.Namespace(session_mode="shared", workers=4, worker=None, batch=0, scheduler="s",
                                  manifest=Path("unused"), game_id="x")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(rev.cmd_game(args), 2)
        self.assertIn("--workers, --worker, --batch and --scheduler", err.getvalue())


@unittest.skipUnless(hasattr(os, "wait4") and importlib.util.find_spec("fcntl"), "POSIX processes and file locks")
class EndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        wheel = self.tmp / "engine.whl"
        wheel.write_bytes(b"wheel")
        self.install = ei.EngineInstall(self.tmp / "install")
        ei.create_install(self.install.root, wheel, wheel_sha256=hashlib.sha256(b"wheel").hexdigest(),
                          engine_version="0", state_files=("pkg/state/.synthetic_state",), installer=fake_installer)
        with ei.session(self.install, "smoke", {}) as handle:
            handle.outcome = {"status": "PASS"}
        self.work = self.tmp / "work"
        (self.work / "games").mkdir(parents=True)
        self.script = self.tmp / "fake_game.py"
        self.script.write_text(FAKE_GAME, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_pool(self, games, codes=None, workers=3, stop_after=0, **extra):
        (self.work / "codes.json").write_text(json.dumps(codes or {}), encoding="utf-8")
        games_file = self.tmp / f"games-{len(list(self.tmp.glob('games-*')))}.txt"
        games_file.write_text("\n".join(games) + "\n", encoding="utf-8")
        args = argparse.Namespace(work=str(self.work), games_file=str(games_file), engine_install=str(self.install.root),
                                  python=sys.executable, evaluation="E", harness_commit="c", harness_dirty=False,
                                  purpose="diagnostic", workers=workers, timeout=60.0, stop_after_failures=stop_after,
                                  **extra)
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            status = pool.run(args, game_script=self.script)
        return status, out.getvalue()

    def test_games_run_once_each_in_isolation(self) -> None:
        games = [f"g{k}" for k in range(7)]
        status, out = self.run_pool(games)
        self.assertEqual(status, 0, out)
        self.assertEqual(sorted(p.stem for p in (self.work / "games").glob("*.json") if p.stem != "codes"), games)
        self.assertEqual(sorted(p.name for p in (self.work / "started").iterdir()), games)
        self.assertEqual(sorted(p.stem for p in (self.work / "logs").iterdir()), games)
        record = json.loads((self.work / "games" / "g3.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(record["cwd"]).resolve(), (self.work / "cwd" / "g3" / "a" / "b").resolve())
        self.assertEqual(sorted(record["env"]), sorted(pool.isolation_env(self.install)))
        argv = record["argv"]
        self.assertEqual(argv[argv.index("--workers") + 1], "3")
        self.assertIn(int(argv[argv.index("--worker") + 1]), (0, 1, 2))
        runs = list((self.work / "pool").glob("run-*.json"))
        self.assertEqual(len(runs), 1)
        self.assertEqual(json.loads(runs[0].read_text(encoding="utf-8"))["queue"], games)
        again, out = self.run_pool(games)
        self.assertEqual(again, 0)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("recorded already: ")), 7)
        self.assertIn("pool finished: 0 started", out)

    def test_runtime_r2_reaches_every_game_environment(self) -> None:
        status, out = self.run_pool(["g0", "g1"], runtime="baseline-v1-runtime-r2")
        self.assertEqual(status, 0, out)
        record = json.loads((self.work / "games" / "g1.json").read_text(encoding="utf-8"))
        self.assertIn("OPENBLAS_NUM_THREADS", record["env"])
        self.assertEqual(sorted(record["env"]), sorted(pool.isolation_env(self.install, "baseline-v1-runtime-r2")))
        self.assertEqual(record["argv"][-2:], ["--runtime", "baseline-v1-runtime-r2"])
        run = json.loads(next((self.work / "pool").glob("run-*.json")).read_text(encoding="utf-8"))
        self.assertEqual((run["runtime"], run["thread_env"]), ("baseline-v1-runtime-r2", {"OPENBLAS_NUM_THREADS": "1"}))

    def test_a_registered_scheduler_must_match(self) -> None:
        status, _ = self.run_pool(["g0"], expected_scheduler="miaosuan-game-pool/1@" + "0" * 64)
        self.assertEqual(status, 2)
        self.assertFalse((self.work / "started").exists() and any((self.work / "started").iterdir()))
        status, _ = self.run_pool(["g0"], expected_scheduler=pool.scheduler_identity())
        self.assertEqual(status, 0)

    def test_an_unknown_runtime_is_refused(self) -> None:
        status, _ = self.run_pool(["g0"], runtime="baseline-v1-runtime-r9")
        self.assertEqual(status, 2)

    def test_a_stale_start_stops_before_any_game(self) -> None:
        (self.work / "started").mkdir()
        (self.work / "started" / "g1").write_text("earlier", encoding="utf-8")
        status, _ = self.run_pool(["g0", "g1"])
        self.assertEqual(status, 1)
        self.assertFalse((self.work / "games" / "g0.json").exists())

    def test_consecutive_failures_stop_dispatch_and_nothing_is_retried(self) -> None:
        games = [f"g{k}" for k in range(6)]
        status, _ = self.run_pool(games, codes={g: 1 for g in games}, workers=1, stop_after=2)
        self.assertEqual(status, 1)
        self.assertEqual(sorted(p.name for p in (self.work / "started").iterdir()), ["g0", "g1"])

    def test_another_exit_status_stops_and_is_returned(self) -> None:
        status, _ = self.run_pool(["g0", "g1", "g2"], codes={"g0": 4}, workers=1)
        self.assertEqual(status, 4)
        self.assertEqual(sorted(p.name for p in (self.work / "started").iterdir()), ["g0"])

    def test_an_unclosed_session_refuses_the_run(self) -> None:
        ei.open_shared_session(self.install, "diagnostic", {}, "0")
        status, _ = self.run_pool(["g0"])
        self.assertEqual(status, 4)
        self.assertFalse((self.work / "started").exists() and any((self.work / "started").iterdir()))

    def test_one_worker_is_refused_by_the_command_line(self) -> None:
        games_file = self.tmp / "one.txt"
        games_file.write_text("g0\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_game_pool.py"), "--evaluation", "E",
                               "--work", str(self.work), "--engine-install", str(self.install.root), "--workers", "1",
                               "--games-file", str(games_file), "--harness-commit", "c"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)


@unittest.skipUnless(shutil.which("bash") and os.name == "posix", "bash syntax check")
class ShellSyntaxTest(unittest.TestCase):
    def test_run_evaluation_sh_parses(self) -> None:
        done = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "run_evaluation.sh")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
