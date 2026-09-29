"""Selection rule, manifest determinism, metrics, canonical digests, effect checks and the RNG probe."""

from __future__ import annotations

import math
import random
import unittest
from types import MappingProxyType

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.decision import BASELINE_ID, INERT_ID
from miaosuan_agent.evaluation import effects, manifest as mf, metrics, randomness
from miaosuan_agent.evaluation.canonical import canonical, value_digest
from miaosuan_agent.evaluation.selection import Pick, ScenarioFacts, facts_for, map_by_name, select

from tests.fixtures import synthetic as syn


def facts(scenario_id, map_id, operators, max_time=1800, reasons=()):
    return ScenarioFacts(scenario_id, map_id, operators, operators // 2, operators - operators // 2, 1, max_time,
                         tuple(reasons))


class SelectionTest(unittest.TestCase):
    def test_naming_rule(self) -> None:
        maps = {"21", "96", "9601"}
        self.assertEqual(map_by_name("201033019601", maps), "9601")
        self.assertEqual(map_by_name("1930331196", maps), "96")
        self.assertEqual(map_by_name("2120531121", maps), "21")
        self.assertIsNone(map_by_name("1231", maps))
        self.assertIsNone(map_by_name("209601", {"21"}))

    def test_rule(self) -> None:
        pool = [facts("110021", "21", 10), facts("120021", "21", 8, 2880), facts("130021", "21", 8, 1800),
                facts("140021", "21", 8, 1800), facts("150096", "96", 50), facts("160096", "96", 90),
                facts("170096", "96", 90), facts("1231", None, 2, reasons=["E1 no map"]),
                facts("180096", "96", 99, reasons=["E3 stuck"])]
        picks = select(pool)
        self.assertEqual([(p.scenario_id, p.rule) for p in picks], [
            ("130021", "S2 fewest operators on map 21"), ("150096", "S2 fewest operators on map 96"),
            ("160096", "S3 largest force")])
        self.assertEqual(picks[0].alternates, ("140021", "120021", "110021"))
        self.assertEqual(picks[1].alternates, ("160096", "170096"))
        self.assertEqual(picks[2].alternates, ("170096", "110021", "120021", "140021"))

    def test_largest_already_picked_takes_next(self) -> None:
        picks = select([facts("100021", "21", 5), facts("200021", "21", 9), facts("300096", "96", 3)])
        self.assertEqual([p.scenario_id for p in picks], ["100021", "300096", "200021"])

    def test_order_of_facts_does_not_matter(self) -> None:
        pool = [facts("110021", "21", 10), facts("130021", "21", 8), facts("150096", "96", 50), facts("160096", "96", 90)]
        self.assertEqual(select(pool), select(list(reversed(pool))))

    def test_eligibility_checks_can_fail(self) -> None:
        costs = MoveCosts.from_raw(syn.cost_data(rows=3, cols=3))
        basic = {"map_data": [[{"elev": 0} for _ in range(3)] for _ in range(3)]}
        flagged = {"map_data": [[{"roadblock": (r, c) == (1, 1)} for c in range(3)] for r in range(3)]}
        ok = {"operators": [{"cur_hex": 0, "type": 2, "color": 0}, {"cur_hex": 202, "type": 1, "color": 1}],
              "cities": [{"coord": 101}], "time": {"max_time": 1800}}
        self.assertTrue(facts_for(ok, "100021", "21", basic, costs).eligible)
        self.assertEqual(facts_for(ok, "1231", None, None, None).reasons[0][:2], "E1")
        outside = {**ok, "operators": [{"cur_hex": 305, "type": 2, "color": 0}]}
        self.assertEqual(facts_for(outside, "100021", "21", basic, costs).reasons[0][:2], "E2")
        isolated = MoveCosts.from_raw([[[{} for _ in range(3)] for _ in range(3)] for _ in range(4)])
        self.assertEqual(facts_for(ok, "100021", "21", basic, isolated).reasons[0][:2], "E3")
        on_board = {**ok, "operators": [{"cur_hex": 0, "type": 1, "color": 0, "on_board": 1}]}
        self.assertTrue(facts_for(on_board, "100021", "21", basic, isolated).eligible)
        self.assertEqual(facts_for(ok, "109601", "9601", flagged, costs).reasons[0][:2], "E4")
        matching = {**ok, "landmarks": {"roadblocks": [101]}}
        self.assertTrue(facts_for(matching, "109601", "9601", flagged, costs).eligible)
        counts = facts_for(ok, "100021", "21", basic, costs)
        self.assertEqual((counts.operators, counts.red, counts.blue, counts.cities, counts.max_time), (2, 1, 1, 1, 1800))


def sample_manifest():
    pool = [facts("201033019601", "9601", 2, 1000), facts("2010131194", "94", 4), facts("2130511121", "21", 89, 2880)]
    picks = select(pool)
    digests = {p.scenario_id: {"scenario": "a" * 64, "basic": "b" * 64, "cost": "c" * 64, "see": "d" * 64} for p in picks}
    return mf.build(pool, picks, digests, "e" * 64, "4.1.0")


class ManifestTest(unittest.TestCase):
    def test_deterministic(self) -> None:
        self.assertEqual(mf.canonical_bytes(sample_manifest()), mf.canonical_bytes(sample_manifest()))
        self.assertEqual(mf.digest(sample_manifest()), mf.digest(sample_manifest()))
        changed = sample_manifest()
        changed["repetitions"] = 3
        self.assertNotEqual(mf.digest(changed), mf.digest(sample_manifest()))

    def test_plan(self) -> None:
        manifest = sample_manifest()
        plan = mf.games(manifest)
        self.assertEqual(len(plan), len(manifest["scenarios"]) * len(manifest["conditions"]) * mf.REPETITIONS)
        self.assertEqual(len({g.game_id for g in plan}), len(plan))
        self.assertEqual([s["scenario_id"] for s in manifest["scenarios"]], ["2130511121", "2010131194", "201033019601"])
        self.assertEqual([s["rule"][:2] for s in manifest["scenarios"]], ["S2", "S2", "S2"])
        self.assertEqual([g.game_id for g in plan[:5]], ["2130511121.C1.r1", "2130511121.C2.r1", "2130511121.C3.r1",
                                                        "2130511121.C4.r1", "2010131194.C1.r1"])
        self.assertEqual(plan[-1].repetition, 2)
        self.assertEqual({(g.red, g.blue) for g in plan}, {(BASELINE_ID, BASELINE_ID), (BASELINE_ID, INERT_ID),
                                                           (INERT_ID, BASELINE_ID), (INERT_ID, INERT_ID)})
        gate = mf.gate1_games(manifest)
        self.assertEqual([g.game_id for g in gate], ["gate1.201033019601.C1.r1", "gate1.201033019601.C1.r2"])
        self.assertEqual(gate[0].step_cap, 1000 + 1 + mf.STEP_MARGIN)

    def test_gate1_must_be_registered(self) -> None:
        manifest = sample_manifest()
        manifest["scenarios"] = [s for s in manifest["scenarios"] if s["scenario_id"] != "201033019601"]
        with self.assertRaises(ValueError):
            mf.gate1_games(manifest)

    def test_manifest_has_no_clock_value(self) -> None:
        text = mf.canonical_bytes(sample_manifest()).decode("utf-8")
        self.assertNotRegex(text, r"20\d\d-\d\d-\d\dT")


class MetricsTest(unittest.TestCase):
    def test_nearest_rank(self) -> None:
        values = list(range(100, 0, -1))
        self.assertEqual([metrics.nearest_rank(values, p) for p in (1, 50, 95, 99, 100)], [1, 50, 95, 99, 100])
        self.assertEqual(metrics.nearest_rank([7], 99), 7)
        self.assertEqual(metrics.nearest_rank([3, 1, 2], 50), 2)
        self.assertIsNone(metrics.nearest_rank([], 50))
        for bad in (0, 101, -5):
            with self.assertRaises(ValueError):
                metrics.nearest_rank([1], bad)

    def test_latency_in_milliseconds(self) -> None:
        summary = metrics.latency([1000, 2000, 3000, 250000])
        self.assertEqual(summary, {"count": 4, "p50_ms": 2.0, "p95_ms": 250.0, "p99_ms": 250.0, "max_ms": 250.0,
                                   "total_ms": 256.0})
        self.assertEqual(metrics.latency([])["p50_ms"], None)

    @staticmethod
    def record(states, traces, status="COMPLETED"):
        seat = {"seat": 1, "faction": 0, "policy": BASELINE_ID, "trace_steps": traces, "trace_chain": "".join(traces),
                "decisions": len(traces), "latency_us": [1] * len(traces), "actions_by_type": {"333": 1, "1": 1},
                "steps_with_action": 1, "first_step_by_type": {}, "units_seen": 1, "units_acted": 1,
                "no_op_reasons": {}, "gate_rejections": {}, "contract_errors": 0, "diagnostics": 0,
                "replay_checks": 1, "replay_mismatches": 0, "effects_by_type": {}, "feedback_entries": 0,
                "feedback_errors_by_code": {}}
        return {"schema": "s", "game_id": f"g{len(states)}{traces[-1]}", "status": status, "failure": None,
                "completion": "done", "steps": len(traces), "done": status == "COMPLETED", "stage_transitions": [],
                "final_scores": {}, "timings_seconds": {}, "seats": [seat], "state_chain": "".join(states),
                "state_steps": states, "rng_probe": {}, "deployment_ended": True}

    def test_traces_are_compared_only_while_states_agree(self) -> None:
        base = self.record(["s0", "s1", "s2", "s3"], ["t0", "t1", "t2"])
        later = self.record(["s0", "s1", "X2", "X3"], ["t0", "t1", "T2"])
        earlier = self.record(["s0", "s1", "X2", "X3"], ["t0", "T1", "T2"])
        same_states = self.record(["s0", "s1", "s2", "s3"], ["t0", "t1", "T2"])
        self.assertTrue(metrics.compare(base, later)["seats"][0]["traces_equal_while_states_equal"])
        self.assertFalse(metrics.compare(base, earlier)["seats"][0]["traces_equal_while_states_equal"])
        self.assertFalse(metrics.compare(base, same_states)["seats"][0]["traces_equal_while_states_equal"])
        self.assertTrue(metrics.gate_check([base, later])["G5"]["pass"])
        self.assertFalse(metrics.gate_check([base, earlier])["G5"]["pass"])

    def test_capped_or_failed_games_fail_g1(self) -> None:
        good = self.record(["s0", "s1"], ["t0"])
        self.assertTrue(metrics.gate_check([good, good])["G1"]["pass"])
        capped = self.record(["s0", "s1"], ["t0"], status="CAPPED")
        self.assertFalse(metrics.gate_check([good, capped])["G1"]["pass"])
        failed = dict(self.record(["s0", "s1"], ["t0"], status="FAIL"), failure={"origin": "engine"})
        self.assertFalse(metrics.gate_check([failed, good])["G1"]["pass"])

    def test_first_divergence(self) -> None:
        self.assertIsNone(metrics.first_divergence(["a", "b"], ["a", "b"]))
        self.assertEqual(metrics.first_divergence(["a", "b"], ["a", "c"]), 1)
        self.assertEqual(metrics.first_divergence(["a"], ["a", "b"]), 1)
        self.assertEqual(metrics.first_divergence([], ["a"]), 0)


class CanonicalTest(unittest.TestCase):
    def test_order_independent_type_faithful(self) -> None:
        self.assertEqual(value_digest({1: "a", 2: [1, 2]}), value_digest({2: [1, 2], 1: "a"}))
        self.assertNotEqual(value_digest({1: "a"}), value_digest({"1": "a"}))
        self.assertNotEqual(value_digest((1, 2)), value_digest([1, 2]))
        self.assertNotEqual(value_digest([1, 2]), value_digest([2, 1]))
        self.assertNotEqual(value_digest(1), value_digest(1.0))
        self.assertNotEqual(value_digest(True), value_digest(1))
        self.assertEqual(value_digest(MappingProxyType({"a": 1})), value_digest({"a": 1}))
        self.assertEqual(canonical(math.nan), {"$float": "nan"})
        self.assertEqual(canonical(object.__new__(object))["$other"][0], "builtins.object")


def everything(units, cities=None, stage=2, cur_step=5, ended=True, judge=None):
    raw = syn.build_observation(units=units, valid_actions={}, cities=cities, stage=stage, cur_step=cur_step,
                                seats={syn.RED_SEAT: syn.seat_record(syn.RED_SEAT, 0, [syn.RED_UNIT], ended)},
                                all_seeing=True)
    if judge is not None:
        raw["judge_info"] = judge
    return Observation.from_raw(raw)


class EffectsTest(unittest.TestCase):
    def test_move(self) -> None:
        before = everything([syn.unit(syn.RED_UNIT, 0, 102)])
        action = {"actor": syn.RED_SEAT, "type": 1, "obj_id": syn.RED_UNIT, "move_path": [103]}
        classify = lambda after: effects.classify(action, 0, before, after, 5)  # noqa: E731
        self.assertEqual(classify(everything([syn.unit(syn.RED_UNIT, 0, 102, move_path=(103,))])), effects.CONFIRMED)
        self.assertEqual(classify(everything([syn.unit(syn.RED_UNIT, 0, 103)])), effects.CONFIRMED)
        self.assertEqual(classify(everything([syn.unit(syn.RED_UNIT, 0, 102)])), effects.NOT_OBSERVED)
        self.assertEqual(classify(everything([])), effects.INDETERMINATE)

    def test_occupy(self) -> None:
        before = everything([syn.unit(syn.RED_UNIT, 0, 505)])
        action = {"actor": syn.RED_SEAT, "type": 5, "obj_id": syn.RED_UNIT}
        held = everything([syn.unit(syn.RED_UNIT, 0, 505)], cities=[syn.city(505, flag=0)])
        self.assertEqual(effects.classify(action, 0, before, held, 5), effects.CONFIRMED)
        self.assertEqual(effects.classify(action, 0, before, everything([syn.unit(syn.RED_UNIT, 0, 505)]), 5),
                         effects.NOT_OBSERVED)

    def test_shoot(self) -> None:
        units = [syn.unit(syn.RED_UNIT, 0, 505), syn.unit(syn.BLUE_UNIT, 1, 506)]
        action = {"actor": syn.RED_SEAT, "type": 2, "obj_id": syn.RED_UNIT, "target_obj_id": syn.BLUE_UNIT,
                  "weapon_id": 43}
        record = {"att_obj_id": syn.RED_UNIT, "target_obj_id": syn.BLUE_UNIT, "cur_step": 5}
        before = everything(units)
        self.assertEqual(effects.classify(action, 0, before, everything(units, judge=[record]), 5), effects.CONFIRMED)
        stale = dict(record, cur_step=4)
        self.assertEqual(effects.classify(action, 0, before, everything(units, judge=[stale]), 5), effects.NOT_OBSERVED)
        self.assertEqual(effects.classify(action, 0, before, everything(units, judge=[]), 5), effects.NOT_OBSERVED)

    def test_deployment(self) -> None:
        action = {"actor": syn.RED_SEAT, "type": 333}
        before = everything([], stage=1, ended=False)
        self.assertEqual(effects.classify(action, 0, before, everything([], stage=1, ended=True), 0), effects.CONFIRMED)
        self.assertEqual(effects.classify(action, 0, before, everything([], stage=2, ended=False), 0), effects.CONFIRMED)
        self.assertEqual(effects.classify(action, 0, before, everything([], stage=1, ended=False), 0),
                         effects.NOT_OBSERVED)

    def test_feedback_fields(self) -> None:
        self.assertEqual(effects.feedback_actor({"message": {"actor": 11}}), 11)
        self.assertIsNone(effects.feedback_actor({"message": {"actor": True}}))
        self.assertIsNone(effects.feedback_actor({}))
        self.assertEqual(effects.feedback_error_code({"error": {"code": 7}}), 7)
        self.assertEqual(effects.feedback_error_code({"error": {"message": "x"}}), "unspecified")
        self.assertIsNone(effects.feedback_error_code({"error": None}))


class RandomnessTest(unittest.TestCase):
    def test_seed_and_fingerprint(self) -> None:
        randomness.seed_globals(20260929)
        first = randomness.fingerprint()
        randomness.seed_globals(20260929)
        self.assertEqual(randomness.fingerprint(), first)
        random.random()
        self.assertNotEqual(randomness.fingerprint()["python"], first["python"])
        if "numpy" in first:
            import numpy
            randomness.seed_globals(20260929)
            numpy.random.random()
            changed = randomness.fingerprint()
            self.assertEqual(changed["python"], first["python"])
            self.assertNotEqual(changed["numpy"], first["numpy"])


if __name__ == "__main__":
    unittest.main()
