from __future__ import annotations

import unittest

from miaosuan_agent.boundary import END_DEPLOYMENT, ContractError, Origin
from miaosuan_agent.smoke_agent import SmokeAgent
from tests.fixtures import synthetic as syn


class SmokeAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = SmokeAgent()
        self.agent.setup({"seat": syn.RED_SEAT})

    def test_ends_deployment_exactly_once(self) -> None:
        deploying = syn.observation(0, stage=1)
        self.assertEqual(self.agent.step(deploying), [{"actor": syn.RED_SEAT, "type": END_DEPLOYMENT}])
        self.assertEqual(self.agent.step(deploying), [])

    def test_never_acts_outside_deployment_or_after_its_seat_ended(self) -> None:
        self.assertEqual(self.agent.step(syn.observation(0, stage=2)), [])
        self.assertEqual(self.agent.step(syn.observation(0, stage=1, end_deployment=True)), [])

    def test_malformed_observations_raise_instead_of_passing_silently(self) -> None:
        for raw in ({"time": {}}, {}, syn.observation(1, stage=1)):
            with self.subTest(keys=sorted(raw)[:3]), self.assertRaises(ContractError):
                SmokeAgent_ = SmokeAgent()
                SmokeAgent_.setup({"seat": syn.RED_SEAT})
                SmokeAgent_.step(raw)

    def test_json_origin(self) -> None:
        agent = SmokeAgent(Origin.JSON)
        agent.setup({"seat": syn.RED_SEAT})
        self.assertEqual(agent.step(syn.json_round_trip(syn.observation(0, stage=1))),
                         [{"actor": syn.RED_SEAT, "type": END_DEPLOYMENT}])

    def test_seat_must_be_an_int_and_reset_requires_setup(self) -> None:
        with self.assertRaises(ContractError):
            SmokeAgent().setup({"seat": "7"})
        self.agent.reset()
        with self.assertRaises(RuntimeError):
            self.agent.step(syn.observation(0, stage=1))


if __name__ == "__main__":
    unittest.main()
