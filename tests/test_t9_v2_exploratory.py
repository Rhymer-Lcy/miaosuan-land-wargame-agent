"""Synthetic tests for Sprint 10's private T9-v2 exploratory capture."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from miaosuan_agent.boundary import Origin, normalize_state
from miaosuan_agent.evaluation.t9_v2_exploratory import CAPTURE_SCHEMA, T9V2Capture
from tests.fixtures import synthetic as syn


class CaptureTest(unittest.TestCase):
    @staticmethod
    def view(step):
        return normalize_state(syn.state(stage=2, cur_step=step), Origin.ENGINE)

    @staticmethod
    def decision(*changes):
        trace = SimpleNamespace(addon_name="t9_staging", changes=tuple(json.dumps(c) for c in changes),
                                skipped=(), addon_error=None)
        return {"faction": 1, "submitted": [], "trace": trace}

    def test_staging_aggregates_and_continuous_withholding_episodes(self) -> None:
        capture = T9V2Capture(("t9-capacity-staging-v2",))
        stage = {"kind": "stage", "obj_id": 10, "path_length": 8, "staged_path_length": 6}
        hold10 = {"kind": "withhold", "obj_id": 10}
        hold11 = {"kind": "withhold", "obj_id": 11}
        views = [self.view(k) for k in range(5)]
        capture.step(0, views[0], views[1], [self.decision(stage, hold10)])
        capture.step(1, views[1], views[2], [self.decision(hold10, hold11)])
        capture.step(2, views[2], views[3], [self.decision(hold11)])
        capture.step(3, views[3], views[4], [self.decision(hold11)])
        compact = capture.compact()
        self.assertEqual(compact["schema"], CAPTURE_SCHEMA)
        self.assertEqual(compact["t9_v2"]["stage_path_hexes_removed"], {"2": 1})
        self.assertEqual(compact["t9_v2"]["stage_unique_units"], 1)
        self.assertEqual(compact["t9_v2"]["withhold_unique_units"], 2)
        self.assertEqual([row["decisions"] for row in compact["t9_v2"]["withhold_episodes"]], [2, 3])
        compact_bytes, series = capture.files()
        summary = capture.summary(compact_bytes, series)
        self.assertEqual(summary["schema"], CAPTURE_SCHEMA)
        self.assertEqual(summary["withhold_longest_decisions"], 3)


if __name__ == "__main__":
    unittest.main()
