"""The concurrency qualification's plan functions, serial references, checks and recommendation rule.

Synthetic records and references only; the registered plan itself is tested in
tests/test_concurrency_registration.py.
"""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.evaluation import concurrency as cq
from miaosuan_agent.evaluation import shoot_experiment as sx


def record(game_id, config, states, traces, chain=None, wall=10.0):
    scenario, condition = config.split(".")
    return {"game_id": game_id, "scenario_id": scenario, "condition": condition, "state_steps": list(states),
            "state_chain": chain or "chain-" + "".join(states), "timings_seconds": {"wall": wall},
            "seats": [{"seat": seat, "trace_steps": list(t), "trace_chain": "t-" + "".join(t)}
                      for seat, t in traces.items()]}


def fake_manifest():
    conditions = {"C1": {"red": sx.CANDIDATE_ID, "blue": sx.CANDIDATE_ID},
                  "C2": {"red": sx.CANDIDATE_ID, "blue": "inert-v0"}, "C3": {"red": "inert-v0", "blue": sx.CANDIDATE_ID}}
    schedule = []
    for k, config in enumerate(reversed(cq.BLOCK_CONFIGS)):
        for group in sx.GROUPS:
            for repetition in (1, 2):
                schedule.append({"game_id": f"{config}.{group}.r{repetition}"})
    return {"groups": {"B": {"conditions": conditions}, "C": {"conditions": conditions}}, "schedule": schedule,
            "scenarios": [], "players": [], "randomness": {"global_seed": 1}, "engine": {"version": "0"}}


def fake_references():
    refs = {}
    for group in sx.GROUPS:
        refs[group] = {}
        for k, config in enumerate(cq.BLOCK_CONFIGS):
            deterministic = config in cq.DETERMINISTIC_EXPECTED
            reps = [record(f"{config}.{r}", config, ["s0", "s1", "s2" if deterministic else f"x{r}"],
                           {1: ["a", "b", "c"]}, wall=10.0 + k * 10 + r) for r in range(3)]
            refs[group][config] = cq.reference(reps)
    return refs


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = cq.build(fake_manifest(), "m" * 64, fake_references(), {"sha256": "p"}, "g" * 64)

    def test_queue_is_longest_first_with_unique_ids(self) -> None:
        queue = cq.tier_queue(self.plan, "w08")
        self.assertEqual(len(queue), 32)
        self.assertEqual(len({e["game_id"] for e in queue}), 32)
        expected = {e["config"]: e["expected_wall_seconds"] for e in self.plan["block"]}
        walls = [expected[e["config"]] for e in queue]
        self.assertEqual(walls, sorted(walls, reverse=True))
        self.assertEqual(queue[0]["game_id"], "cq1.w08.001.2130511121.C3")
        self.assertEqual([e["block"] for e in queue[:4]], [0, 1, 2, 3])
        self.assertEqual([e["seq"] for e in queue], list(range(1, 33)))

    def test_tier_sizes_follow_the_blocks(self) -> None:
        sizes = {t["tier"]: len(cq.tier_queue(self.plan, t["tier"])) for t in self.plan["tiers"] + self.plan["optional_tiers"]}
        self.assertEqual(sizes, {"S": 8, "w01": 16, "w02": 16, "w04": 16, "w08": 32, "w16": 64, "w24": 96, "w32": 128})

    def test_equivalence_corpus_mixes_both_groups_in_schedule_order(self) -> None:
        corpus = self.plan["equivalence"]["corpus"]
        self.assertEqual(len(corpus), 16)
        self.assertEqual(corpus[:2], ["2130511121.C3.B.r1", "2130511121.C3.C.r1"])
        self.assertEqual(set(self.plan["equivalence"]["references"]), set(corpus))

    def test_a_changed_determinism_class_refuses_the_plan(self) -> None:
        refs = fake_references()
        refs["C"]["201033019601.C2"] = refs["C"]["2130511121.C3"]
        with self.assertRaises(ValueError):
            cq.build(fake_manifest(), "m" * 64, refs, {"sha256": "p"}, "g" * 64)

    def test_digest_is_canonical(self) -> None:
        self.assertEqual(cq.digest(self.plan), cq.digest(copy.deepcopy(self.plan)))
        changed = copy.deepcopy(self.plan)
        changed["criteria"]["minimum_efficiency"] = 0.5
        self.assertNotEqual(cq.digest(self.plan), cq.digest(changed))


class ReferenceTest(unittest.TestCase):
    def test_common_prefix_and_divergence(self) -> None:
        self.assertIsNone(cq.first_divergence(["a", "b"], ["a", "b"]))
        self.assertEqual(cq.first_divergence(["a", "b"], ["a", "c"]), 1)
        self.assertEqual(cq.first_divergence(["a"], ["a", "b"]), 1)
        self.assertEqual(cq.common_prefix([["a", "b", "c"], ["a", "b", "x"], ["a", "y", "z"]]), 1)

    def test_stochastic_reference_and_comparison(self) -> None:
        reps = [record(f"r{k}", "2130511121.C3", ["s0", "s1", f"x{k}"], {11: ["a", "b", f"c{k}"]}) for k in range(3)]
        ref = cq.reference(reps)
        self.assertEqual((ref["class"], ref["state_prefix_steps"]), ("stochastic", 2))
        self.assertEqual(ref["seats"]["11"]["trace_prefix_steps"], 2)
        fresh = record("q", "2130511121.C3", ["s0", "s1", "new"], {11: ["a", "b", "new"]})
        self.assertTrue(cq.compare(fresh, ref)["pass"])
        early = record("q", "2130511121.C3", ["s0", "zz", "new"], {11: ["a", "b", "new"]})
        self.assertFalse(cq.compare(early, ref)["pass"])
        copied = record("q", "2130511121.C3", ["s0", "s1", "x1"], {11: ["a", "b", "c1"]})
        self.assertTrue(cq.compare(copied, ref)["matches_a_serial_chain"])
        self.assertFalse(cq.compare(copied, ref)["pass"])
        traced = record("q", "2130511121.C3", ["s0", "s1", "new"], {11: ["a", "q", "new"]})
        self.assertFalse(cq.compare(traced, ref)["pass"])

    def test_deterministic_reference_requires_identity(self) -> None:
        reps = [record(f"r{k}", "201033019601.C2", ["s0", "s1"], {1: ["a", "b"]}) for k in range(3)]
        ref = cq.reference(reps)
        self.assertEqual(ref["class"], "deterministic")
        self.assertTrue(cq.compare(record("q", "201033019601.C2", ["s0", "s1"], {1: ["a", "b"]}), ref)["identical"])
        late = record("q", "201033019601.C2", ["s0", "s1"], {1: ["a", "b"]}, chain="other")
        self.assertFalse(cq.compare(late, ref)["pass"])

    def test_duplicate_stochastic_chains_are_found(self) -> None:
        classes = {"2130511121.C3": "stochastic", "201033019601.C2": "deterministic"}
        records = [record("a", "2130511121.C3", ["s"], {}, chain="same"), record("b", "2130511121.C3", ["s"], {}, chain="same"),
                   record("c", "2130511121.C3", ["s"], {}, chain="other"),
                   record("d", "201033019601.C2", ["s"], {}, chain="det"), record("e", "201033019601.C2", ["s"], {}, chain="det")]
        self.assertEqual(cq.duplicate_chains(records, classes), [["a", "b"]])


class LedgerCheckTest(unittest.TestCase):
    STATE = {"state": "h"}

    def events(self):
        opens = [{"event": "session-open", "session": "0011", "state": self.STATE, "harness": {"game_id": "g1"},
                  "concurrency": {"mode": "shared", "worker": "0"}},
                 {"event": "session-open", "session": "0012", "state": self.STATE, "harness": {"game_id": "g2"},
                  "concurrency": {"mode": "shared", "worker": "1"}}]
        closes = [{"event": "session-close", "session": s, "state": self.STATE, "state_changed": False,
                   "home_changed": False, "integrity": {"ok": True}} for s in ("0012", "0011")]
        return opens + closes

    def records(self):
        return {"g1": {"session": "0011"}, "g2": {"session": "0012"}}

    def test_a_clean_tier_passes(self) -> None:
        check = cq.ledger_check(self.events(), 10, self.records(), "shared", self.STATE)
        self.assertTrue(check["pass"], check["problems"])
        self.assertEqual((check["first"], check["last"]), (11, 12))

    def test_defects_are_reported(self) -> None:
        events = self.events()
        self.assertFalse(cq.ledger_check(events[:-1], 10, self.records(), "shared", self.STATE)["pass"])
        self.assertFalse(cq.ledger_check(events, 9, self.records(), "shared", self.STATE)["pass"])
        self.assertFalse(cq.ledger_check(events, 10, self.records(), "exclusive", self.STATE)["pass"])
        self.assertFalse(cq.ledger_check(events, 10, self.records(), "shared", {"state": "other"})["pass"])
        recovered = events + [{"event": "session-recovered", "session": "0012", "state": self.STATE}]
        self.assertFalse(cq.ledger_check(recovered, 10, self.records(), "shared", self.STATE)["pass"])
        swapped = self.records()
        swapped["g1"]["session"] = "0012"
        self.assertFalse(cq.ledger_check(events, 10, swapped, "shared", self.STATE)["pass"])
        changed = copy.deepcopy(events)
        changed[2]["state_changed"] = True
        self.assertFalse(cq.ledger_check(changed, 10, self.records(), "shared", self.STATE)["pass"])


def tier(workers, throughput, p99=1.0, maximum=100.0, ok=True, our=4.0, rss=0.01):
    return {"tier": f"w{workers:02d}", "workers": workers, "throughput_games_per_hour": throughput,
            "latency": {"p99_ms": p99, "max_ms": maximum}, "safety_pass": ok, "independence_pass": True,
            "engine_state_pass": True, "ledger_pass": True, "our_cpus_mean": our, "peak_rss_fraction": rss}


def evaluated(rows):
    base = rows[0]
    for row in rows:
        row["criteria"] = cq.criteria_for(row, base)
    return rows


class RecommendationTest(unittest.TestCase):
    def test_knee_prefers_the_smaller_count(self) -> None:
        rows = evaluated([tier(1, 10), tier(2, 19), tier(4, 37), tier(8, 70), tier(16, 80)])
        self.assertEqual(cq.recommend(rows)["disposition"], "RECOMMEND 8 WORKERS")

    def test_near_linear_scaling_takes_the_top(self) -> None:
        rows = evaluated([tier(1, 10), tier(2, 20), tier(4, 39), tier(8, 78), tier(16, 150)])
        self.assertEqual(cq.recommend(rows)["disposition"], "RECOMMEND 16 WORKERS")

    def test_worse_tails_or_low_efficiency_exclude_a_tier(self) -> None:
        rows = evaluated([tier(1, 10), tier(2, 19), tier(4, 37), tier(8, 70, p99=1.6), tier(16, 100)])
        self.assertFalse(rows[3]["criteria"]["latency"]["pass"])
        self.assertFalse(rows[4]["criteria"]["efficiency"]["pass"])
        self.assertEqual(cq.recommend(rows)["disposition"], "RECOMMEND 4 WORKERS")

    def test_no_gain_retains_serial_and_a_failed_check_blocks(self) -> None:
        self.assertEqual(cq.recommend(evaluated([tier(1, 10), tier(2, 12)]))["disposition"], "RETAIN SERIAL EXECUTION")
        rows = evaluated([tier(1, 10), tier(2, 19, ok=False), tier(4, 37)])
        self.assertEqual(cq.recommend(rows)["disposition"], "CONCURRENCY BLOCKED PENDING MORE EVIDENCE")

    def test_headroom(self) -> None:
        rows = evaluated([tier(1, 10), tier(2, 19), tier(32, 300, our=33.0)])
        self.assertFalse(rows[2]["criteria"]["headroom"]["pass"])
        self.assertEqual(cq.recommend(rows)["disposition"], "RECOMMEND 2 WORKERS")

    def test_latency_summary(self) -> None:
        records = [{"seats": [{"policy": cq.POLICY, "latency_us": [1000, 2000, 150000, 1200000]},
                              {"policy": "inert-v0", "latency_us": [9_000_000]}]}]
        summary = cq.latency_summary(records)
        self.assertEqual((summary["decisions"], summary["max_ms"], summary["over_100ms"], summary["over_1000ms"]),
                         (4, 1200.0, 2, 1))


if __name__ == "__main__":
    unittest.main()
