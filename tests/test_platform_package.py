"""The platform upload package builder (``scripts/build_platform_package.py``). SYNTHETIC game data only.

Layout (exactly one top-level ``ai`` package with ``agent.py``), vendored modules byte-identical to the source, an
import closure of relative and standard-library imports only, refusal of forbidden content and layouts, the size
limit, a deterministic archive, and the isolated-interpreter smoke in which the packaged agent's actions equal the
repository agent's.
"""

from __future__ import annotations

import importlib.util
import io
import sys
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
                              ("ai/x.py", b"path = '/home/ubuntu/x'"), ("ai/y.py", b"import train_env"),
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


if __name__ == "__main__":
    unittest.main()
