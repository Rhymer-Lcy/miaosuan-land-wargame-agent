"""The platform-facing agent wrapper: lifecycle, fail-closed handling and origins."""

from __future__ import annotations

import unittest

from miaosuan_agent.agent import BaselineAgent, InertAgent, PolicyAgent
from miaosuan_agent.boundary import ContractError, Origin
from miaosuan_agent.decision import BASELINE_ID, INERT_ID, Memory, digest

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn

SEAT = syn.RED_SEAT


def setup_info(**overrides):
    info = {"seat": SEAT, "faction": ds.RED, "cost_data": syn.cost_data(), "role": 1, "user_name": "synthetic-red",
            "user_id": 900007}
    info.update(overrides)
    return info


def deploy_observation():
    return ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102)], {ds.UNIT_A: {1: None}}, stage=1, cur_step=0,
                               ended=False)


class LifecycleTest(unittest.TestCase):
    def test_identities(self) -> None:
        self.assertEqual(BaselineAgent().policy_id, BASELINE_ID)
        self.assertEqual(InertAgent().policy_id, INERT_ID)
        with self.assertRaises(ValueError):
            PolicyAgent("tuned-v1")

    def test_step_before_setup(self) -> None:
        with self.assertRaises(RuntimeError):
            BaselineAgent().step(deploy_observation())

    def test_setup_step_reset_setup(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        self.assertEqual(agent.step(deploy_observation()), [{"actor": SEAT, "type": 333}])
        self.assertEqual(agent.step(deploy_observation()), [])
        agent.reset()
        self.assertIsNone(agent.last_trace)
        with self.assertRaises(RuntimeError):
            agent.step(deploy_observation())
        agent.setup(setup_info())
        self.assertEqual(agent.step(deploy_observation()), [{"actor": SEAT, "type": 333}])

    def test_setup_starts_a_new_game_without_reset(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        agent.step(deploy_observation())
        agent.setup(setup_info())
        self.assertEqual(agent.step(deploy_observation()), [{"actor": SEAT, "type": 333}])

    def test_returned_actions_are_independent_copies(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        first = agent.step(ds.rich_observation())
        first[0]["obj_id"] = 1
        self.assertEqual(agent.step(ds.rich_observation())[0]["obj_id"], ds.UNIT_A)

    def test_last_trace_matches_actions(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        actions = agent.step(ds.rich_observation())
        self.assertEqual([(a["type"], a.get("obj_id")) for a in actions], list(agent.last_trace.emitted))
        self.assertEqual(agent.last_trace.policy, BASELINE_ID)


class ReplayTest(unittest.TestCase):
    def test_replay_reproduces_the_step_without_side_effects(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        memory = agent.memory
        agent.step(deploy_observation())
        after_deploy = (agent.memory, agent.last_trace)
        replayed = agent.replay(deploy_observation(), memory)
        self.assertEqual(digest(replayed), digest(after_deploy[1]))
        self.assertEqual((agent.memory, agent.last_trace), after_deploy)
        self.assertEqual(agent.replay(deploy_observation(), agent.memory).deployment, "already sent")
        agent.step(ds.rich_observation())
        self.assertEqual(digest(agent.replay(ds.rich_observation(), agent.memory)), digest(agent.last_trace))

    def test_replay_of_a_malformed_observation(self) -> None:
        agent = BaselineAgent()
        agent.setup(setup_info())
        self.assertIsNotNone(agent.replay({"operators": []}, agent.memory).error)
        strict = BaselineAgent(strict=True)
        strict.setup(setup_info())
        with self.assertRaises(ContractError):
            strict.replay({"operators": []}, strict.memory)

    def test_replay_before_setup(self) -> None:
        with self.assertRaises(RuntimeError):
            BaselineAgent().replay(deploy_observation(), Memory())


class FailClosedTest(unittest.TestCase):
    MALFORMED = {"not a mapping": [1, 2, 3], "no time": {"operators": []}, "int keys": {1: "x"}}

    def test_non_strict_emits_nothing_and_traces_the_error(self) -> None:
        agent = BaselineAgent()
        agent.setup(setup_info())
        for name, raw in self.MALFORMED.items():
            with self.subTest(case=name):
                self.assertEqual(agent.step(raw), [])
                self.assertIsNotNone(agent.last_trace.error)
                self.assertTrue(agent.last_trace.error.startswith("ContractError"))
                self.assertIsNone(agent.last_trace.step)
                digest(agent.last_trace)
        self.assertEqual(agent.step(deploy_observation()), [{"actor": SEAT, "type": 333}])

    def test_strict_raises(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        for name, raw in self.MALFORMED.items():
            with self.subTest(case=name), self.assertRaises(ContractError):
                agent.step(raw)

    def test_contract_failure_keeps_memory(self) -> None:
        agent = BaselineAgent()
        agent.setup(setup_info())
        agent.step(deploy_observation())
        agent.step({"operators": []})
        self.assertEqual(agent.step(deploy_observation()), [])

    def test_malformed_setup_always_raises(self) -> None:
        for strict in (False, True):
            agent = BaselineAgent(strict=strict)
            for info in (setup_info(seat="7"), setup_info(faction=None), setup_info(cost_data=[[[{}]]])):
                with self.subTest(strict=strict), self.assertRaises(ContractError):
                    agent.setup(info)

    def test_missing_cost_data_disables_movement_only(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info(cost_data=None))
        actions = agent.step(ds.rich_observation())
        self.assertEqual([a["type"] for a in actions], [2, 5])
        self.assertIn("no movement-cost data", agent.last_trace.units[2].no_op_reason)


class OriginTest(unittest.TestCase):
    def test_json_transport_agent(self) -> None:
        engine, json_agent = BaselineAgent(strict=True), BaselineAgent(Origin.JSON, strict=True)
        engine.setup(setup_info())
        json_agent.setup(setup_info(cost_data=syn.json_round_trip(syn.cost_data())))
        self.assertEqual(engine.step(ds.rich_observation()),
                         json_agent.step(syn.json_round_trip(ds.rich_observation())))
        self.assertEqual(digest(engine.last_trace), digest(json_agent.last_trace))

    def test_engine_agent_rejects_json_keys(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup(setup_info())
        with self.assertRaises(ContractError):
            agent.step(syn.json_round_trip(ds.rich_observation()))


if __name__ == "__main__":
    unittest.main()
