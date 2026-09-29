"""Exercise the smoke-test loop against a stand-in engine; the real SDK is never imported."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent import engine_smoke
from miaosuan_agent.boundary import END_DEPLOYMENT
from miaosuan_agent.sdk_data import ScenarioInputs
from miaosuan_agent.smoke_agent import SmokeAgent
from tests.fixtures import synthetic as syn

INPUTS = ScenarioInputs(scenario_id="1", map_id="2", scenario={}, basic={"map_data": [[{}]]}, cost=[], see=None)
LIMITS = engine_smoke.SmokeLimits(max_steps=50, max_seconds=30.0)


class FakeEnv:
    """Stand-in engine built from synthetic observations.

    Deployment ends once both seats send END_DEPLOYMENT; the game ends after five steps.
    """

    output: List[str] = []
    print_on_setup = ""
    raise_in_setup = False

    def __init__(self) -> None:
        self.ended = set()
        self.step_count = 0
        self.seats = (0, 0)

    def _state(self) -> Any:
        stage = 2 if len(self.ended) == 2 else 1
        return syn.state(stage=stage, cur_step=max(0, self.step_count - 1),
                         red_seat=self.seats[0], blue_seat=self.seats[1])

    def setup(self, setup_info: Dict[str, Any]) -> Any:
        if self.print_on_setup:
            FakeEnv.output.append(self.print_on_setup)
        if self.raise_in_setup:
            raise ValueError("bad scenario")
        self.seats = tuple(player["seat"] for player in setup_info["player_info"])
        return self._state()

    def step(self, actions: List[Dict[str, Any]]) -> tuple:
        self.step_count += 1
        self.ended.update(a["actor"] for a in actions if a["type"] == END_DEPLOYMENT)
        return self._state(), self.step_count >= 5

    def reset(self) -> None:
        pass


def _run(env_cls: type, limits: engine_smoke.SmokeLimits = LIMITS, capture=None) -> dict:
    FakeEnv.output = []
    with tempfile.TemporaryDirectory() as tmp:
        report = engine_smoke.run_smoke(env_cls, SmokeAgent, INPUTS, limits, Path(tmp),
                                        captured_output=lambda: "".join(FakeEnv.output), capture=capture)
        report["_files"] = sorted(p.name for p in Path(tmp).iterdir())
    return report


class RunSmokeTest(unittest.TestCase):
    def test_pass_with_profile_and_stage_transition(self) -> None:
        report = _run(FakeEnv)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertEqual((report["completion"], report["steps"]), ("done", 5))
        self.assertEqual(report["stage_transitions"], [{"step": 0, "stage": 1}, {"step": 1, "stage": 2}])
        self.assertEqual(report["state_form"], "mapping")
        self.assertEqual(report["profile_deviation_count"], 0, report["profile_deviations"])
        self.assertTrue(report["deployment_transition_matches_profile"])
        self.assertEqual(set(report["fingerprints"]), {"setup", "after-deployment", "play-step"})
        self.assertEqual(len(report["issued_actions"]), 2)
        self.assertIn("observation-red-first-play.json", report["_files"])
        self.assertIs(report["state_object_reused_by_step"], False)

    def test_capture_receives_three_points(self) -> None:
        seen: List[str] = []
        report = _run(FakeEnv, capture=lambda point, state: seen.append(point))
        self.assertEqual(seen, list(engine_smoke.CAPTURE_POINTS))
        self.assertEqual(report["captured_points"], list(engine_smoke.CAPTURE_POINTS))

    def test_sequence_form_passes_the_boundary_but_deviates_from_the_profile(self) -> None:
        class ListEnv(FakeEnv):
            def _state(self) -> Any:
                state = FakeEnv._state(self)
                return [state[0], state[1], state[-1]]

        report = _run(ListEnv)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertEqual(report["state_form"], "sequence")
        self.assertGreater(report["profile_deviation_count"], 0)

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
        self.assertEqual((report["status"], report["phase"]), ("FAIL", "setup"))
        self.assertIn("ValueError", report["reasons"][0])

    def test_contract_violation_fails_with_its_path(self) -> None:
        class NoStageEnv(FakeEnv):
            def _state(self) -> Any:
                state = FakeEnv._state(self)
                del state[0]["time"]["stage"]
                return state

        report = _run(NoStageEnv)
        self.assertEqual((report["status"], report["phase"]), ("FAIL", "setup-contract"))
        self.assertIn("state[0].time.stage", report["reasons"][0])

    def test_deployment_that_never_ends_is_not_a_pass(self) -> None:
        class StuckEnv(FakeEnv):
            def step(self, actions: List[Dict[str, Any]]) -> tuple:
                self.step_count += 1
                return syn.state(stage=1, red_seat=self.seats[0], blue_seat=self.seats[1]), False

        report = _run(StuckEnv, engine_smoke.SmokeLimits(max_steps=3, max_seconds=30.0))
        self.assertEqual((report["status"], report["completion"]), ("FAIL", "step_limit"))


if __name__ == "__main__":
    unittest.main()
