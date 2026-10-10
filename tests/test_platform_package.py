"""The platform upload package builder (``scripts/build_platform_package.py``). SYNTHETIC game data only.

Layout (exactly one top-level ``ai`` package with ``agent.py``), vendored modules byte-identical to the source, an
import closure of relative and standard-library imports only, refusal of forbidden content and layouts, the size
limit, a deterministic archive, and the isolated-interpreter smoke in which the packaged agent's actions equal the
repository agent's.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_platform_package", ROOT / "scripts" / "build_platform_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.b = load_builder()
        cls.payload = cls.b.entries()
        cls.data = cls.b.write_zip(cls.payload)

    def test_layout(self) -> None:
        names = set(self.payload)
        self.assertTrue(all(name.startswith("ai/") for name in names))
        for required in ("ai/__init__.py", "ai/agent.py", "ai/base_agent.py", "ai/PACKAGE.json",
                         "ai/miaosuan_agent/experiments/shoot_reservation.py"):
            self.assertIn(required, names)
        with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
            self.assertEqual({n.split("/")[0] for n in archive.namelist()}, {"ai"})
        self.assertEqual(self.b.verify_zip(self.data), [])

    def test_vendored_modules_are_the_source(self) -> None:
        vendored = [name for name in self.payload if name.startswith("ai/miaosuan_agent/")]
        self.assertGreater(len(vendored), 10)
        for name in vendored:
            self.assertEqual(self.payload[name], (ROOT / "src" / name[len("ai/"):]).read_bytes(), name)
        self.assertNotIn("ai/miaosuan_agent/evaluation/game.py", self.payload)

    def test_closure_is_relative_and_standard_library(self) -> None:
        files, external = self.b.closure()
        self.assertIn("miaosuan_agent/agent.py", files)
        self.b.check_external(external)
        with self.assertRaises(SystemExit):
            self.b.check_external(external | {"numpy"})

    def test_forbidden_content_is_refused(self) -> None:
        for name, content in (("ai/tests/test_x.py", b""), ("ai/x.pyc", b""), ("ai/data.json", b"{}"),
                              ("ai/__pycache__/x.py", b""), ("ai/local/x.py", b""), ("other/agent.py", b""),
                              ("ai/x.py", ("path = '/" + "home/user/x'").encode()), ("ai/y.py", b"import train_env"),
                              ("ai/z.py", ("path = 'C" + ":/data/x'").encode()), ("ai/w.py", ("host = '192." + "168.0.1'").encode()),
                              ("ai/.engine_config", b"")):
            self.assertTrue(self.b.forbidden(name, content), name)
        self.assertEqual(self.b.forbidden("ai/agent.py", self.payload["ai/agent.py"]), [])
        extra = dict(self.payload, **{"other/readme.txt": b"x"})
        self.assertTrue(self.b.verify_zip(self.b.write_zip(extra)))

    def test_size_limit(self) -> None:
        with mock.patch.object(self.b, "LIMIT_BYTES", 1000):
            self.assertTrue(any("200 MB" in p for p in self.b.verify_zip(self.data)))

    def test_archive_is_deterministic(self) -> None:
        self.assertEqual(self.b.write_zip(self.b.entries()), self.data)
        with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
            for info in archive.infolist():
                self.assertEqual((info.create_system, info.date_time, info.compress_type),
                                 (3, (1980, 1, 1, 0, 0, 0), zipfile.ZIP_STORED))

    def test_isolated_smoke(self) -> None:
        result = self.b.smoke(self.data, self.b.synthetic_inputs(), sys.executable)
        self.assertGreater(result["steps"], 0)
        self.assertEqual(result["mismatches"], 0)
        self.assertEqual((result["ai"], result["source"]), ("baseline-v2", self.b.POLICY_SOURCE_SHA256))

    def test_a_broken_package_fails_the_smoke(self) -> None:
        broken = dict(self.payload)
        broken["ai/agent.py"] = self.payload["ai/agent.py"].replace(b"return actions", b"return actions[:0]")
        result = self.b.smoke(self.b.write_zip(broken), self.b.synthetic_inputs(), sys.executable)
        self.assertGreater(result["mismatches"], 0)


CASES = r'''
import contextlib, io, json, sys
root = sys.argv[1]
sys.path.insert(0, root)
from ai import Agent
import ai.agent

def deployment(seats, stage=1):
    return {"time": {"cur_step": 0, "stage": stage}, "operators": [], "passengers": [], "valid_actions": {},
            "role_and_grouping_info": seats}

def run(setup, observation):
    agent, err = Agent(), io.StringIO()
    with contextlib.redirect_stderr(err):
        agent.setup(setup)
        actions = agent.step(observation)
    return {"actions": actions, "stderr": err.getvalue()}

ok = {"seat": 1, "faction": 0, "role": 0}
seat_entry = {"role": 0, "faction": 0, "operators": [], "user_id": 0, "user_name": "x"}
print(json.dumps({
    "wrapper": getattr(ai.agent, "WRAPPER", None),
    "bad_setup_deployment": run({"seat": 1, "faction": 0, "cost_data": "x"}, deployment({1: seat_entry})),
    "bad_setup_play": run({"seat": 1, "faction": 0, "cost_data": "x"}, deployment({1: seat_entry}, stage=2)),
    "bad_setup_already_ended": run({"seat": 1, "faction": 0, "cost_data": "x"},
                                   deployment({1: dict(seat_entry, end_deployment=True)})),
    "missing_seat_info": run(ok, {"time": {"cur_step": 0, "stage": 1}, "operators": [], "passengers": [],
                                  "valid_actions": {}}),
    "string_seat": run({"seat": "1", "faction": "0"}, deployment({"1": seat_entry})),
    "no_seat": run({"faction": 0}, deployment({1: seat_entry})),
}))
'''


class Compat1Test(unittest.TestCase):
    """The ``compat1`` wrapper: the canary's policy files, JSON-form inputs, start-up safety and diagnostics."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.b = load_builder()
        cls.canary = cls.b.entries()
        cls.payload = cls.b.entries("compat1")
        cls.data = cls.b.write_zip(cls.payload)
        cls.inputs = cls.b.synthetic_inputs()

    def test_canary_entry_point_is_unchanged(self) -> None:
        self.assertNotIn(b"compat1", self.canary["ai/agent.py"])
        self.assertNotIn(b"wrapper", self.canary["ai/PACKAGE.json"])
        self.assertEqual(self.b.VARIANT_NAMES["canary"], "miaosuan-baseline-v2-canary")

    def test_only_the_entry_point_and_manifest_differ(self) -> None:
        self.assertEqual(set(self.payload), set(self.canary))
        differing = sorted(name for name in self.payload if self.payload[name] != self.canary[name])
        self.assertEqual(differing, ["ai/PACKAGE.json", "ai/agent.py"])
        self.assertEqual(json.loads(self.payload["ai/PACKAGE.json"])["wrapper"], "compat1")
        self.assertEqual(self.b.verify_zip(self.data), [])

    def test_engine_form_actions_equal_the_repository_agent(self) -> None:
        result = self.b.smoke(self.data, self.inputs, sys.executable)
        self.assertGreater(result["steps"], 0)
        self.assertEqual(result["mismatches"], 0)

    def test_json_form_actions_equal_the_engine_form(self) -> None:
        json_form = self.b.json_form(self.inputs)
        first_seat, first_observation, _ = json_form["steps"][0]
        self.assertTrue(all(isinstance(k, str) for k in first_observation["role_and_grouping_info"]))
        result = self.b.smoke(self.data, json_form, sys.executable)
        self.assertEqual((result["steps"], result["mismatches"]), (len(self.inputs["steps"]), 0))

    def test_the_canary_fails_on_json_form(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.b.smoke(self.b.write_zip(self.canary), self.b.json_form(self.inputs), sys.executable)
        self.assertIn("expected an int key", str(raised.exception))

    def test_a_broken_wrapper_fails_the_json_smoke(self) -> None:
        broken = dict(self.payload)
        broken["ai/agent.py"] = self.payload["ai/agent.py"].replace(b"int(key) if rekey else key", b"key")
        self.assertNotEqual(broken["ai/agent.py"], self.payload["ai/agent.py"])
        result = self.b.smoke(self.b.write_zip(broken), self.b.json_form(self.inputs), sys.executable)
        self.assertGreater(result["mismatches"], 0)
        self.assertEqual(self.b.smoke(self.b.write_zip(broken), self.inputs, sys.executable)["mismatches"], 0)

    def test_start_up_safety_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
                archive.extractall(root)
            script = Path(tmp) / "cases.py"
            script.write_text(CASES, encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", "-B", str(script), str(root)], capture_output=True,
                                    text=True, cwd=tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        cases = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(cases["wrapper"], "compat1")
        end = [{"actor": 1, "type": 333}]
        self.assertEqual(cases["bad_setup_deployment"]["actions"], end)
        self.assertIn("setup error", cases["bad_setup_deployment"]["stderr"])
        self.assertIn("fallback", cases["bad_setup_deployment"]["stderr"])
        self.assertEqual(cases["bad_setup_play"]["actions"], [])
        self.assertEqual(cases["bad_setup_already_ended"]["actions"], [])
        self.assertEqual(cases["missing_seat_info"]["actions"], end)
        self.assertIn("contract error", cases["missing_seat_info"]["stderr"])
        self.assertIn("ABSENT", cases["missing_seat_info"]["stderr"])
        self.assertEqual(cases["string_seat"]["actions"], end)
        self.assertNotIn("fallback", cases["string_seat"]["stderr"])
        self.assertIn("converted to integer form", cases["string_seat"]["stderr"])
        self.assertEqual(cases["no_seat"]["actions"], [])
        self.assertIn("setup error", cases["no_seat"]["stderr"])
        for case in cases.values():
            if isinstance(case, dict):
                self.assertTrue(all(line.startswith("[baseline-v2/compat1] ")
                                    for line in case["stderr"].splitlines()), case["stderr"])


if __name__ == "__main__":
    unittest.main()
