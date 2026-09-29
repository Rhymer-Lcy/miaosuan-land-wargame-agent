from __future__ import annotations

import unittest

from miaosuan_agent.boundary import (END_DEPLOYMENT, ContractError, Observation, deployment_completion_available,
                                     end_deployment_action, validate_end_deployment_action)
from tests.fixtures import synthetic as syn


class EndDeploymentActionTest(unittest.TestCase):
    def test_builder_produces_the_documented_shape(self) -> None:
        action = end_deployment_action(syn.RED_SEAT)
        self.assertEqual(action, {"actor": syn.RED_SEAT, "type": END_DEPLOYMENT})
        validate_end_deployment_action(action)

    def test_builder_rejects_non_int_seats(self) -> None:
        for seat in (True, "7", 7.0):
            with self.subTest(seat=seat), self.assertRaises(ContractError):
                end_deployment_action(seat)

    def test_shape_validation(self) -> None:
        bad = [
            {"actor": 7, "type": 333, "obj_id": 1},
            {"actor": 7},
            {"actor": 7, "type": 334},
            {"actor": "7", "type": 333},
            [7, 333],
        ]
        for action in bad:
            with self.subTest(action=action), self.assertRaises(ContractError):
                validate_end_deployment_action(action)


class AvailabilityTest(unittest.TestCase):
    def available(self, raw: dict, seat: int = syn.RED_SEAT) -> bool:
        return deployment_completion_available(Observation.from_raw(raw), seat)

    def test_follows_stage_and_seat_flag(self) -> None:
        self.assertTrue(self.available(syn.observation(0, stage=1)))
        self.assertFalse(self.available(syn.observation(0, stage=1, end_deployment=True)))
        self.assertFalse(self.available(syn.observation(0, stage=2)))

    def test_not_discovered_through_valid_actions(self) -> None:
        raw = syn.observation(0, stage=1)
        for per_unit in raw["valid_actions"].values():
            self.assertNotIn(END_DEPLOYMENT, per_unit)
        self.assertTrue(self.available(raw))

    def test_flag_absent_falls_back_to_stage(self) -> None:
        raw = syn.observation(0, stage=1)
        del raw["role_and_grouping_info"][syn.RED_SEAT]["end_deployment"]
        self.assertTrue(self.available(raw))

    def test_seat_must_be_listed(self) -> None:
        with self.assertRaises(ContractError):
            self.available(syn.observation(0, stage=1), seat=syn.BLUE_SEAT)


if __name__ == "__main__":
    unittest.main()
