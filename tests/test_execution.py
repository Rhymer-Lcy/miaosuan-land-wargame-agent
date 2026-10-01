"""Runtime identities and the registered execution settings, and how the evaluation entry points enforce them."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.evaluation import execution as ex
from miaosuan_agent.evaluation import runtime_threads as rt
from miaosuan_agent.evaluation import shoot_experiment as sx

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RegisteredTest(unittest.TestCase):
    def test_defaults_are_what_every_earlier_registration_ran(self) -> None:
        self.assertEqual(ex.registered({}), {"workers": 1, "runtime": "baseline-v1-runtime-r1", "thread_env": {},
                                             "scheduler": None})
        manifest = json.loads((ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(ex.registered(manifest)["runtime"], "baseline-v1-runtime-r1")

    def test_runtime_r2_is_the_qualified_environment(self) -> None:
        self.assertEqual(ex.runtime_env("baseline-v1-runtime-r2"), rt.ENVIRONMENTS["B"])
        self.assertEqual(ex.runtime_env("baseline-v1-runtime-r1"), rt.ENVIRONMENTS["A"])
        registered = ex.registered({"execution": {"workers": 32, "runtime": "baseline-v1-runtime-r2", "scheduler": "s"}})
        self.assertEqual(registered, {"workers": 32, "runtime": "baseline-v1-runtime-r2",
                                      "thread_env": {"OPENBLAS_NUM_THREADS": "1"}, "scheduler": "s"})

    def test_unknown_runtimes_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            ex.registered({"execution": {"runtime": "baseline-v1-runtime-r9"}})

    def test_thread_environment_check(self) -> None:
        self.assertIsNone(ex.check_thread_env({"PATH": "/bin"}, "baseline-v1-runtime-r1"))
        self.assertIsNotNone(ex.check_thread_env({"OMP_NUM_THREADS": "4"}, "baseline-v1-runtime-r1"))
        self.assertIsNone(ex.check_thread_env({"OPENBLAS_NUM_THREADS": "1"}, "baseline-v1-runtime-r2"))
        self.assertIsNotNone(ex.check_thread_env({"OPENBLAS_NUM_THREADS": "2"}, "baseline-v1-runtime-r2"))
        self.assertIsNotNone(ex.check_thread_env({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
                                                 "baseline-v1-runtime-r2"))


class GameRefusalTest(unittest.TestCase):
    def run_game(self, runtime, purpose, environ):
        rev = load_script("run_evaluation")
        manifest = json.loads((ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            args = argparse.Namespace(manifest=path, game_id=manifest["schedule"][0]["game_id"], work=Path(tmp) / "work",
                                      engine_install=Path(tmp), harness_commit="x", harness_dirty=False, purpose=purpose,
                                      runtime=runtime)
            with mock.patch.dict(os.environ, environ, clear=False), contextlib.redirect_stderr(io.StringIO()) as err:
                for name in ex.THREAD_VARIABLES:
                    if name not in environ:
                        os.environ.pop(name, None)
                status = rev.cmd_game(args)
        return status, err.getvalue()

    def test_a_registered_run_cannot_change_its_runtime(self) -> None:
        status, message = self.run_game("baseline-v1-runtime-r2", "evaluation", {"OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual(status, 2)
        self.assertIn("uses the runtime its manifest registers", message)

    def test_the_effective_thread_environment_must_match(self) -> None:
        status, message = self.run_game(None, "evaluation", {"OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual(status, 2)
        self.assertIn("numerical-thread environment", message)
        status, message = self.run_game("baseline-v1-runtime-r2", "diagnostic", {})
        self.assertEqual(status, 2)
        self.assertIn("numerical-thread environment", message)

    def test_a_matching_runtime_reaches_the_input_check(self) -> None:
        status, message = self.run_game("baseline-v1-runtime-r2", "diagnostic", {"OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual(status, 2)
        self.assertIn("input error", message)


class WiringTest(unittest.TestCase):
    def test_the_shell_runner_takes_the_variables_from_the_runtime_table(self) -> None:
        text = (ROOT / "scripts" / "run_evaluation.sh").read_text(encoding="utf-8")
        block = text[text.index("env -i \\"):text.index("timeout --signal=TERM")]
        self.assertIn('"${THREAD_ENV[@]}"', block)
        self.assertIn("ex.runtime_env(runtime)", text)
        self.assertIn('--runtime "$RUNTIME" "${SCHEDULER_ARGS[@]}"', text)
        self.assertIn('--purpose "$PURPOSE" --runtime "$RUNTIME"', text)
        self.assertIn("a registered run cannot use $RUNTIME", text)

    def test_the_pool_adds_the_runtime_variables(self) -> None:
        pool = load_script("run_game_pool")
        from miaosuan_agent import engine_install as ei
        install = ei.EngineInstall(Path("/x"))
        base = pool.isolation_env(install)
        r2 = pool.isolation_env(install, "baseline-v1-runtime-r2")
        self.assertEqual(r2, dict(base, OPENBLAS_NUM_THREADS="1"))
        argv = pool.game_argv("py", Path("g.py"), "E", Path("/w"), "id", install, "c", False, "diagnostic", 2, 0, 0, "s",
                              "baseline-v1-runtime-r2")
        self.assertEqual(argv[-2:], ["--runtime", "baseline-v1-runtime-r2"])


if __name__ == "__main__":
    unittest.main()
