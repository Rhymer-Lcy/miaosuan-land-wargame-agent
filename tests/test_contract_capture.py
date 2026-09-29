from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from miaosuan_agent.contract_capture import CaptureWriter, load_capture
from miaosuan_agent.engine_smoke import CAPTURE_POINTS
from tests.fixtures import synthetic as syn


class CaptureWriterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "capture"
        self.states = {"setup": syn.state(stage=1), "after-deployment": syn.state(stage=2),
                       "play-step": syn.state(stage=2, cur_step=1)}
        writer = CaptureWriter(self.root, {"engine_version": "synthetic"})
        for point in CAPTURE_POINTS:
            writer.capture(point, self.states[point])
        self.manifest_path = writer.finalize({"run_status": "PASS"})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_manifest_lists_every_point_and_slot(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["points"], list(CAPTURE_POINTS))
        self.assertEqual(len(manifest["entries"]), 9)
        self.assertEqual({e["slot"] for e in manifest["entries"]}, {"red", "blue", "global"})
        self.assertEqual(manifest["inexact_values"], [])
        self.assertEqual(manifest["containers"]["setup"]["keys"][0], {"repr": "0", "type": "int"})
        self.assertEqual(manifest["containers"]["setup"]["profile_deviations"], [])
        self.assertEqual([e["stage"] for e in manifest["entries"] if e["slot"] == "red"], [1, 2, 2])

    def test_load_restores_the_exact_engine_objects(self) -> None:
        loaded = load_capture(self.root)
        for point in CAPTURE_POINTS:
            self.assertEqual(loaded["states"][point], self.states[point])
            self.assertEqual(list(loaded["states"][point][0]["valid_actions"]), [syn.RED_UNIT])

    def test_tampered_file_is_detected(self) -> None:
        target = self.root / "setup" / "red.typed.json"
        target.write_text(target.read_text(encoding="utf-8").replace("synthetic-red", "synthetic-rex"), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_capture(self.root)

    def test_existing_directory_and_repeated_point_are_refused(self) -> None:
        with self.assertRaises(FileExistsError):
            CaptureWriter(self.root, {})
        writer = CaptureWriter(Path(self._tmp.name) / "second", {})
        writer.capture("setup", syn.state())
        with self.assertRaises(ValueError):
            writer.capture("setup", syn.state())


if __name__ == "__main__":
    unittest.main()
