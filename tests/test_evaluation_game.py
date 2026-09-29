"""The game runner against a synthetic stand-in engine."""

from __future__ import annotations

import re
import unittest

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import BASELINE_ID, INERT_ID
from miaosuan_agent.evaluation import metrics, randomness
from miaosuan_agent.evaluation.game import play, sanitize
from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec

from tests.fixtures import fake_engine
from tests.fixtures import synthetic as syn

FACTORIES = {BASELINE_ID: lambda: PolicyAgent(BASELINE_ID, strict=True),
             INERT_ID: lambda: PolicyAgent(INERT_ID, strict=True)}


def scalars(value):
    """Every int value (bools excluded) and every string (keys and values) in a nested structure."""
    ints, strings = set(), set()

    def walk(item):
        if isinstance(item, dict):
            for key, inner in item.items():
                walk(key)
                walk(inner)
        elif isinstance(item, (list, tuple)):
            for inner in item:
                walk(inner)
        elif isinstance(item, str):
            strings.add(item)
        elif isinstance(item, int) and not isinstance(item, bool):
            ints.add(item)

    walk(value)
    return ints, strings


class Inputs:
    scenario, basic, see = {"synthetic": True}, {"synthetic": True}, None
    cost = syn.cost_data()


def spec(red=BASELINE_ID, blue=BASELINE_ID, max_time=30, repetition=1):
    return GameSpec(game_id=f"synthetic.C.r{repetition}", scenario_id="900000001", map_id="9000", condition="C",
                    red=red, blue=blue, repetition=repetition, max_time=max_time)


def run(engine=None, **kwargs):
    engine = engine or (lambda: fake_engine.FakeEnv())
    return play(engine, FACTORIES, kwargs.pop("game", spec()), Inputs, PLAYERS, **kwargs)


class GameTest(unittest.TestCase):
    def test_complete_game_record(self) -> None:
        record = run()
        self.assertEqual((record["status"], record["completion"], record["done"]), ("COMPLETED", "done", True))
        self.assertEqual(record["steps"], 31)
        self.assertEqual(record["stage_transitions"], [{"step": 0, "stage": 1}, {"step": 1, "stage": 2}])
        self.assertTrue(record["deployment_ended"])
        self.assertEqual(len(record["state_steps"]), record["steps"] + 1)
        self.assertEqual(metrics.missing_fields(record), [])
        for seat in record["seats"]:
            with self.subTest(seat=seat["seat"]):
                self.assertEqual(len(seat["trace_steps"]), record["steps"])
                self.assertEqual(seat["decisions"], record["steps"])
                self.assertEqual(seat["actions_by_type"]["333"], 1)
                self.assertGreater(seat["actions_by_type"]["1"], 0)
                self.assertEqual(seat["effects_by_type"]["333"], {"confirmed": 1})
                self.assertEqual(set(seat["effects_by_type"]["1"]), {"confirmed"})
                self.assertEqual(seat["feedback_entries"], sum(seat["actions_by_type"].values()))
                self.assertEqual(seat["feedback_errors_by_code"], {})
                self.assertEqual((seat["replay_checks"], seat["replay_mismatches"]), (1, 0))
                self.assertEqual(seat["gate_rejections"], {})
                self.assertEqual(seat["contract_errors"], 0)
        self.assertEqual(set(record["timings_seconds"]), {"wall", "engine_step", "decisions", "harness"})

    def test_repetitions_agree_and_gate_passes(self) -> None:
        first, second = run(), run(game=spec(repetition=2))
        comparison = metrics.compare(first, second)
        self.assertTrue(comparison["state_chain_equal"])
        self.assertIsNone(comparison["state_first_divergence"])
        self.assertTrue(all(seat["trace_chain_equal"] for seat in comparison["seats"]))
        gate = metrics.gate_check([first, second])
        self.assertEqual({k: v["pass"] for k, v in gate.items()}, {f"G{i}": True for i in range(1, 7)})

    def test_engine_divergence_is_located(self) -> None:
        first = run()
        second = run(lambda: fake_engine.FakeEnv(noise_at=7), game=spec(repetition=2))
        comparison = metrics.compare(first, second)
        self.assertFalse(comparison["state_chain_equal"])
        self.assertEqual(comparison["state_first_divergence"], 7)
        self.assertTrue(all(seat["traces_equal_while_states_equal"] for seat in comparison["seats"]))
        self.assertTrue(metrics.gate_check([first, second])["G5"]["pass"])

    def test_refused_moves_fail_legality(self) -> None:
        records = [run(lambda: fake_engine.FakeEnv(refuse_moves=True), game=spec(repetition=r)) for r in (1, 2)]
        seat = records[0]["seats"][0]
        self.assertGreater(seat["feedback_errors_by_code"]["21"], 0)
        self.assertGreater(seat["effects_by_type"]["1"]["not observed"], 0)
        gate = metrics.gate_check(records)
        self.assertFalse(gate["G4"]["pass"])
        self.assertTrue(gate["G1"]["pass"])

    def test_engine_error_details(self) -> None:
        record = run(lambda: fake_engine.FakeEnv(refuse_moves=True))
        seat = record["seats"][0]
        refused = seat["feedback_errors_by_code"]["21"]
        self.assertEqual(seat["feedback_errors_by_code_and_type"], {"21/1": refused})
        examples = seat["feedback_error_examples"]["21"]
        self.assertEqual(len(examples), min(refused, 5))
        self.assertEqual({e["error_message"] for e in examples}, {"synthetic refusal"})
        self.assertEqual({e["action"]["type"] for e in examples}, {1})
        public = metrics.public_game(record)["seats"][0]
        self.assertEqual(public["feedback_errors_by_code_and_type"], {"21/1": refused})
        self.assertNotIn("feedback_error_examples", public)
        clean = run()["seats"][0]
        self.assertEqual((clean["feedback_errors_by_code_and_type"], clean["feedback_error_examples"]), ({}, {}))

    def test_inert_control(self) -> None:
        record = run(game=spec(red=BASELINE_ID, blue=INERT_ID))
        red, blue = record["seats"]
        self.assertEqual(blue["actions_by_type"], {"333": 1})
        self.assertEqual(blue["replay_checks"], 0)
        self.assertEqual(blue["no_op_reasons"], {"inert control policy": record["steps"] - 1})
        self.assertGreater(red["actions_by_type"].get("1", 0), 0)
        gate = metrics.gate_check([record, run(game=spec(red=INERT_ID, blue=INERT_ID))])
        self.assertIsNone(metrics.gate_check([run(game=spec(red=INERT_ID, blue=INERT_ID))])["G3"]["pass"])
        self.assertIn("G1", gate)

    def test_engine_failure_is_recorded(self) -> None:
        record = run(lambda: fake_engine.FakeEnv(fail_at=4))
        self.assertEqual(record["status"], "FAIL")
        self.assertEqual((record["failure"]["origin"], record["steps"]), ("engine-step", 3))
        self.assertIn("synthetic engine failure", record["failure"]["message"])
        self.assertFalse(metrics.gate_check([record, record])["G1"]["pass"])

    def test_construct_and_setup_failures(self) -> None:
        def broken():
            raise ImportError("no engine here")

        self.assertEqual(run(broken)["failure"]["origin"], "engine")

        class NoSetup(fake_engine.FakeEnv):
            def setup(self, info):
                raise ValueError("bad scenario")

        record = run(NoSetup)
        self.assertEqual((record["status"], record["failure"]["origin"]), ("FAIL", "engine-setup"))
        self.assertEqual(metrics.public_game(record)["failure"]["type"], "ValueError")

    def test_agent_failure_is_recorded(self) -> None:
        class Broken(PolicyAgent):
            def step(self, observation):
                raise KeyError("agent bug")

        record = play(lambda: fake_engine.FakeEnv(), {BASELINE_ID: lambda: Broken(BASELINE_ID)}, spec(), Inputs, PLAYERS)
        self.assertEqual((record["status"], record["failure"]["origin"]), ("FAIL", "agent-0"))

    def test_step_cap(self) -> None:
        record = run(lambda: fake_engine.FakeEnv(never_done=True), game=spec(max_time=5))
        self.assertEqual((record["status"], record["completion"], record["steps"]), ("CAPPED", "step_cap", 106))

    def test_wall_cap_uses_the_injected_clock(self) -> None:
        ticks = iter(range(0, 10_000_000, 7))
        record = run(lambda: fake_engine.FakeEnv(never_done=True), wall_cap=500, clock=lambda: next(ticks))
        self.assertEqual(record["completion"], "wall_cap")

    def test_rng_probe_points(self) -> None:
        randomness.seed_globals(5)
        record = run(rng_probe=randomness.fingerprint)
        self.assertEqual(set(record["rng_probe"]),
                         {"before-construct", "after-construct", "after-setup", "after-first-step", "end"})
        self.assertEqual(metrics.public_game(record)["global_rng_changed_by_engine"],
                         {"numpy": False, "python": False} if "numpy" in record["rng_probe"]["end"]
                         else {"python": False})

    def test_public_summary_carries_no_private_detail(self) -> None:
        public = metrics.public_game(run())
        ints, strings = scalars(public)
        for private in ("trace_steps", "state_steps", "latency_us", "trace_chain", "state_chain"):
            self.assertNotIn(private, strings)
        # compared as whole values, never as substrings: a latency such as 0.102 ms is not hex 102
        scenario_values = {syn.RED_HEX, syn.BLUE_HEX, syn.CITY_HEX, syn.RED_UNIT, syn.BLUE_UNIT}
        self.assertFalse(scenario_values & ints)
        self.assertFalse([s for s in strings if any(re.search(rf"(?<!\d){v}(?!\d)", s) for v in scenario_values)])
        self.assertEqual(sanitize("hex 1234 is not a traversable neighbour of 1235"),
                         "hex N is not a traversable neighbour of N")

    def test_privacy_check_detects_a_planted_value(self) -> None:
        public = metrics.public_game(run())
        public["seats"][0]["no_op_reasons"][f"unit {syn.RED_UNIT} idle"] = 1
        public["seats"][1]["units_seen"] = syn.CITY_HEX
        ints, strings = scalars(public)
        self.assertIn(syn.CITY_HEX, ints)
        self.assertTrue(any(str(syn.RED_UNIT) in s for s in strings))


class CostsFixtureTest(unittest.TestCase):
    def test_fake_engine_map_matches_costs(self) -> None:
        self.assertEqual(MoveCosts.from_raw(Inputs.cost).rows, syn.GRID_ROWS)


if __name__ == "__main__":
    unittest.main()
