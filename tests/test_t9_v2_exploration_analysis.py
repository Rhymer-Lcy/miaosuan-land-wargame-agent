"""Privacy and aggregation tests for the Sprint 10 T9-v2 public analyzer."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location("t9_v2_exploration_analysis",
                                                  ROOT / "scripts" / "t9_v2_exploration_analysis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnalysisTest(unittest.TestCase):
    def test_public_extension_aggregates_without_private_identifiers_or_coordinates(self) -> None:
        module = load_script()
        record = {
            "seats": [{"faction": 1, "actions_by_type": {"2": 3}, "contract_errors": 0,
                       "gate_rejections": {}, "replay_mismatches": 0}],
            "final_scores": {"blue_attack": 24, "blue_remain": 407},
            "observer_errors": [],
            "session_close": {"state_changed": False, "home_changed": False, "integrity": {"ok": True}},
        }
        capture = {
            "t9_v2": {"stage_unique_units": 2, "withhold_unique_units": 1,
                      "stage_path_hexes_removed": {"1": 2},
                      "withhold_episodes": [{"obj_id": 987654, "faction": 1, "start": 4, "end": 8,
                                             "decisions": 5}]},
            "addon_changes": {"1:stage": 2, "1:withhold": 5},
            "snapshots": [{"flags": [[1234, 1], [5678, 0], [9012, -1]]}],
            "addon_errors": [],
            "waiting_ground_units": {"1": {"max": 1, "sum": 2, "steps_positive": 2}},
            "max_objective_commitment": {"1": {"max": 4, "sum": 10, "steps_positive": 3}},
        }
        result = module.public_extension(record, capture, 1)
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("987654", encoded)
        self.assertNotIn("1234", encoded)
        self.assertEqual(result["mechanism"]["withholding"],
                         {"episodes": 1, "longest": 5, "median": 5, "sum": 5, "unique_units": 1})
        self.assertEqual(result["objectives_final"], {"candidate": 1, "opponent": 1, "neutral_or_other": 1})
        self.assertTrue(result["integrity"]["engine_integrity_ok"])

    def test_historical_summary_omits_non_finite_interval(self) -> None:
        module = load_script()
        phase_b = {"against_inert": {"x C2": {"estimate": -2.0, "ci_high": float("inf"), "strata": {
            "T9": {"n": 15, "mean": 10.0}, "V2": {"n": 15, "mean": 12.0}}}}}
        result = module.historical_sprint9({"scenario_id": "x", "condition": "C2"}, 0, {}, phase_b)
        self.assertNotIn("ci_high", result)
        json.dumps(result, allow_nan=False)

    def test_empty_duration_summary_is_finite_strict_json(self) -> None:
        module = load_script()
        result = module.duration_summary({"withhold_episodes": [], "withhold_unique_units": 0})
        self.assertEqual(result["longest"], 0)
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
