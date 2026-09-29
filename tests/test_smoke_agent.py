from __future__ import annotations

import unittest

from miaosuan_agent.smoke_agent import END_DEPLOYMENT, SmokeAgent


class SmokeAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = SmokeAgent()
        self.agent.setup({"seat": 11})

    def test_ends_deployment_exactly_once(self) -> None:
        deploying = {"time": {"stage": 1}}
        self.assertEqual(self.agent.step(deploying), [{"actor": 11, "type": END_DEPLOYMENT}])
        self.assertEqual(self.agent.step(deploying), [])

    def test_never_acts_outside_deployment(self) -> None:
        self.assertEqual(self.agent.step({"time": {"stage": 2}}), [])
        self.assertEqual(self.agent.step({"time": {}}), [])
        self.assertEqual(self.agent.step({}), [])

    def test_reset_requires_new_setup(self) -> None:
        self.agent.reset()
        with self.assertRaises(RuntimeError):
            self.agent.step({"time": {"stage": 1}})


if __name__ == "__main__":
    unittest.main()
