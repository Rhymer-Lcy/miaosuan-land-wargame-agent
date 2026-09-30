"""The routing remediation's comparison and measurement tools, and the committed results they produced.

The tools are exercised on SYNTHETIC observations: the full-agent comparator and the engine wrapper
must report no difference between baseline-v1 and the candidate, and must report a planted one; the
benchmark's work counter must count real work. The committed aggregates (equivalence, benchmark,
mutation) must be internally consistent, name the current candidate and baseline-v1, and satisfy the
registered criteria when recomputed here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import unittest
from pathlib import Path

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.decision import BASELINE_ID
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest

from tests.test_occupy_reservation import golden_candidate_observations, setup_info

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / rr.REMEDIATION_ID


def script(name: str):
    loader = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class Reversed:
    """A planted difference: the wrapped agent's actions in reverse order."""

    def __init__(self, agent) -> None:
        self.agent = agent

    def step(self, observation):
        return list(self.agent.step(observation))[::-1]

    def __getattr__(self, name: str):
        return getattr(self.agent, name)


class ComparatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compare = script("compare_routing_candidate")

    def run_sequence(self, planted: bool):
        info = setup_info()
        tally = self.compare.Tally()
        old, new = self.compare.agents_for(info["seat"], info["faction"], info["cost_data"])
        for index, observation in enumerate(golden_candidate_observations()):
            self.compare.compare(tally, "synthetic", f"golden {index}", (old, Reversed(new) if planted else new),
                                 observation)
        return tally

    def test_equal_agents_show_no_difference(self) -> None:
        tally = self.run_sequence(planted=False)
        counts = tally.by_role["synthetic"]
        self.assertEqual((counts["decisions"], counts["identical"], tally.differences), (5, 5, []))
        self.assertGreater(counts["moves"], 0)
        self.assertEqual(counts["moves"], counts["move_paths_equal"])

    def test_a_planted_difference_is_reported(self) -> None:
        tally = self.run_sequence(planted=True)
        self.assertEqual([d["where"] for d in tally.differences], ["golden 3", "golden 4"])
        for difference in tally.differences:
            self.assertIn("actions_equal", difference["failed"])
            self.assertNotIn("semantic_traces_equal", difference["failed"])


class EngineWrapperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = script("diagnose_routing_engine")

    def play(self, shadow=None):
        sink = {"decisions": io.StringIO(), "tally": self.engine.new_tally()}
        agent = self.engine.Shadowed(sink)
        if shadow is not None:
            agent.shadow = shadow
        agent.setup(setup_info())
        emitted = [agent.step(observation) for observation in golden_candidate_observations()]
        rows = [json.loads(line) for line in sink["decisions"].getvalue().splitlines()]
        return agent, emitted, rows, sink["tally"]

    def test_the_candidate_drives_and_the_shadow_agrees(self) -> None:
        agent, emitted, rows, tally = self.play()
        self.assertEqual((tally["decisions"], tally["different"], len(rows)), (5, 0, 5))
        self.assertTrue(all(row["equal"] for row in rows))
        self.assertEqual(agent.inner.policy_id, rr.CANDIDATE_ID)
        self.assertEqual([len(e) for e in emitted], [row["emitted"] for row in rows])
        self.assertEqual(agent.first_play["decision"], 1)
        self.assertEqual(agent.memory, agent.inner.memory)
        for row in rows:
            self.assertGreater(row["candidate"]["wall"], 0)
            self.assertGreater(row["shadow"]["wall"], 0)

    def test_a_different_shadow_is_reported(self) -> None:
        _, _, rows, tally = self.play(shadow=PolicyAgent(BASELINE_ID))
        self.assertGreater(tally["different"], 0)
        self.assertTrue(all("failed" in row for row in rows if not row["equal"]))


class WorkCounterTest(unittest.TestCase):
    def test_counts_real_search_work(self) -> None:
        bench = script("benchmark_routing_candidate")
        info = setup_info()
        observation = golden_candidate_observations()[1]
        state = {"seat": info["seat"], "faction": info["faction"], "memory": {"deployment_sent": True}}
        old, old_output = bench.work("baseline-v1", state, info["cost_data"], observation)
        new, new_output = bench.work("candidate", state, info["cost_data"], observation)
        self.assertEqual(old_output, new_output)
        self.assertEqual((old["requests"], old["searches"]), (new["requests"], new["searches"]))
        self.assertGreaterEqual(old["searches"], 1)
        self.assertGreater(old["edges"], 0)
        self.assertLess(new["settled"], old["settled"])
        self.assertLess(new["edges"], old["edges"])


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registration = json.loads((DIRECTORY / "registration.json").read_text(encoding="utf-8"))
        cls.equivalence = json.loads((DIRECTORY / "equivalence.json").read_text(encoding="utf-8"))
        cls.benchmark = json.loads((DIRECTORY / "benchmark.json").read_text(encoding="utf-8"))
        cls.candidate = policy_source_digest(sources=rr.candidate_sources())[0]

    def test_equivalence_covers_the_pinned_corpus_without_difference(self) -> None:
        result = self.equivalence
        totals = result["totals"]
        self.assertEqual(result["candidate_source_sha256"], self.candidate)
        self.assertEqual(result["baseline_v1_source_sha256"],
                         policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0])
        self.assertEqual(result["corpus_sha256"], self.registration["corpus_sha256"])
        self.assertEqual(totals["decisions"], self.registration["corpus"]["decisions_total"])
        pinned = {}
        for entry in self.registration["corpus"]["files"]:
            pinned[entry["role"]] = pinned.get(entry["role"], 0) + entry["decisions"]
        self.assertEqual({role: counts["decisions"] for role, counts in result["by_role"].items()}, pinned)
        self.assertEqual(result["unexplained_differences"], 0)
        for name in ("identical", "actions_equal", "semantic_traces_equal", "memory_equal"):
            self.assertEqual(totals[name], totals["decisions"], name)
        self.assertEqual(totals["move_paths_equal"], totals["moves"])
        self.assertEqual(totals["objective_choices_equal"], totals["objective_choices"])
        self.assertEqual(totals["no_op_units_equal"], totals["no_op_units"])
        self.assertEqual((totals["different"], totals["contract_errors"], totals["mutated_inputs"]), (0, 0, 0))
        self.assertGreater(totals["moves"], 1000)

    def test_benchmark_names_this_candidate_and_this_equivalence(self) -> None:
        result = self.benchmark
        self.assertEqual(result["candidate_source_sha256"], self.candidate)
        self.assertEqual(result["equivalence_sha256"],
                         hashlib.sha256((DIRECTORY / "equivalence.json").read_bytes()).hexdigest())
        self.assertEqual(result["performance_registered"], self.registration["performance"])
        self.assertEqual(result["repetitions"], self.registration["performance"]["repetitions"])

    def test_benchmark_meets_the_registered_criterion_recomputed(self) -> None:
        result = self.benchmark
        states = result["states"]
        registered = {entry["path"].split("/")[-1][:-len(".json")] for entry in self.registration["corpus"]["files"]
                      if entry["path"].endswith(".json")}
        self.assertEqual({n for n, s in states.items() if s["kind"] == "registered"}, registered)
        self.assertEqual(len(registered), 9)
        worst = ("2130511121-seat11-decision1", "2130511121-seat11-decision1-latdiag-1")
        repetitions = result["repetitions"]
        per_state = 2 * (repetitions["fresh_agent"] + repetitions["memo_warm"] + repetitions["cold_process"])
        for name, state in states.items():
            old = state["fresh_agent"]["baseline-v1"]["p50_ms"]
            new = state["fresh_agent"]["candidate"]["p50_ms"]
            if name in worst:
                self.assertLessEqual(new, 0.50 * old, name)
            else:
                self.assertLessEqual(new, old * 1.10 + 0.20, name)
            self.assertEqual(state["output_mismatches"], 0, name)
            self.assertEqual(state["calls_checked"], per_state, name)
            for mode in ("fresh_agent", "memo_warm", "cold_process"):
                self.assertEqual(state[mode]["candidate"]["n"], repetitions[mode], (name, mode))
        self.assertTrue(result["verdict"]["pass"])
        self.assertEqual(result["verdict"]["calls_checked"], per_state * len(states))

    def test_mutation_result_is_complete_and_names_the_current_candidate(self) -> None:
        result = json.loads((DIRECTORY / "mutation.json").read_text(encoding="utf-8"))
        target = ROOT / result["target"]
        self.assertEqual(result["target_sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
        names = [row["mutant"] for row in result["mutants"]]
        self.assertEqual(len(names), len(set(names)))
        classes = [row["class"] for row in result["mutants"]]
        self.assertEqual((classes.count("non-equivalent"), classes.count("equivalent")),
                         (result["non_equivalent"]["total"], result["equivalent"]["total"]))
        self.assertGreaterEqual(result["non_equivalent"]["total"], 15)
        for row in result["mutants"]:
            self.assertEqual(row["outcome"], "killed" if row["class"] == "non-equivalent" else "survived", row["mutant"])
            self.assertEqual("argument" in row, row["class"] == "equivalent", row["mutant"])
        self.assertEqual((result["unexpected"], result["pass"]), ([], True))

    def test_measured_work_equals_the_earlier_estimate(self) -> None:
        estimated = [s for s in self.benchmark["states"].values() if "estimate" in s]
        self.assertEqual(len(estimated), 4)
        for state in estimated:
            self.assertTrue(state["estimate"]["measured_equals_estimate"])
        worst = self.benchmark["states"]["2130511121-seat11-decision1"]
        self.assertEqual((worst["work"]["baseline-v1"]["settled"], worst["work"]["candidate"]["settled"]),
                         (226688, 35920))


if __name__ == "__main__":
    unittest.main()
