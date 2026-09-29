"""Exercise the smoke-test loop against a stand-in engine; the real SDK is never imported."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent import engine_smoke
from miaosuan_agent.sdk_data import ScenarioInputs
from miaosuan_agent.smoke_agent import END_DEPLOYMENT, SmokeAgent

INPUTS = ScenarioInputs(scenario_id="1", map_id="2", scenario={}, basic={"map_data": [[{}]]}, cost=[], see=None)
LIMITS = engine_smoke.SmokeLimits(max_steps=50, max_seconds=30.0)


class FakeEnv:
    """Minimal stand-in: deployment ends once both seats send END_DEPLOYMENT; the game lasts 5 steps."""

    output: List[str] = []
    include_stage = True
    raise_in_setup = False
    print_on_setup = ""

    def __init__(self) -> None:
        self.ended = set()
        self.step_count = 0

    def _obs(self, stage: int) -> Dict[str, Any]:
        time_info: Dict[str, Any] = {"cur_step": self.step_count}
        if self.include_stage:
            time_info["stage"] = stage
        return {"time": time_info, "valid_actions": {101: {1: None, 6: [{"target_state": 4}]}},
                "operators": [{"obj_id": 101}], "passengers": [], "actions": [],
                "role_and_grouping_info": {1: {"role": 1, "operators": [101]}}, "communication": []}

    def _state(self) -> list:
        stage = 2 if len(self.ended) == 2 else 1
        return [self._obs(stage), self._obs(stage), self._obs(stage)]

    def setup(self, setup_info: Dict[str, Any]) -> list:
        if self.print_on_setup:
            FakeEnv.output.append(self.print_on_setup)
        if self.raise_in_setup:
            raise ValueError("bad scenario")
        return self._state()

    def step(self, actions: List[Dict[str, Any]]) -> tuple:
        self.step_count += 1
        self.ended.update(a["actor"] for a in actions if a["type"] == END_DEPLOYMENT)
        return self._state(), self.step_count >= 5

    def reset(self) -> None:
        pass


def _run(env_cls: type, limits: engine_smoke.SmokeLimits = LIMITS) -> dict:
    FakeEnv.output = []
    with tempfile.TemporaryDirectory() as tmp:
        report = engine_smoke.run_smoke(env_cls, SmokeAgent, INPUTS, limits, Path(tmp),
                                        captured_output=lambda: "".join(FakeEnv.output))
        files = sorted(p.name for p in Path(tmp).iterdir())
    report["_files"] = files
    return report


class RunSmokeTest(unittest.TestCase):
    def test_pass_records_contract_and_stage_transition(self) -> None:
        report = _run(FakeEnv)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertEqual(report["completion"], "done")
        self.assertEqual(report["steps"], 5)
        self.assertEqual(report["stage_transitions"], [{"step": 0, "stage": 1}, {"step": 1, "stage": 2}])
        valid = report["contract_initial_red"]["valid_actions"]
        self.assertEqual(valid["operator_key_types"], ["int"])
        self.assertEqual(valid["action_key_types"], ["int"])
        self.assertEqual(len(report["issued_actions"]), 2)
        self.assertIn("observation-red-first-play.json", report["_files"])

    def test_authentication_failure_blocks_before_stepping(self) -> None:
        class AuthFailEnv(FakeEnv):
            print_on_setup = "did not pass authentication\n"

        report = _run(AuthFailEnv)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn("steps", report)

    def test_setup_exception_is_reported(self) -> None:
        class BrokenEnv(FakeEnv):
            raise_in_setup = True

        report = _run(BrokenEnv)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["phase"], "setup")
        self.assertIn("ValueError", report["reasons"][0])

    def test_missing_stage_field_is_not_a_pass(self) -> None:
        class NoStageEnv(FakeEnv):
            include_stage = False

        report = _run(NoStageEnv)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("cannot be verified", report["reasons"][0])

    def test_deployment_that_never_ends_is_not_a_pass(self) -> None:
        class StuckEnv(FakeEnv):
            def step(self, actions: List[Dict[str, Any]]) -> tuple:
                self.step_count += 1
                return self._state_stuck(), False

            def _state_stuck(self) -> list:
                return [self._obs(1)] * 3

        report = _run(StuckEnv, engine_smoke.SmokeLimits(max_steps=3, max_seconds=30.0))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["completion"], "step_limit")


class DescribeTest(unittest.TestCase):
    def test_reports_key_types(self) -> None:
        summary = engine_smoke.describe({1: {"a": [1, 2]}, "2": None})
        self.assertEqual(summary["key_types"], ["int", "str"])
        self.assertEqual(summary["values"]["1"]["values"]["'a'"]["element_types"], ["int"])


if __name__ == "__main__":
    unittest.main()
