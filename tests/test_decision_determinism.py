"""Determinism: decisions depend on the observation's content only, never on incidental order,
hash seeds, the clock or random sources. Golden decisions freeze the behaviour of ``baseline-v0``."""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.agent import BaselineAgent
from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import BASELINE_ID, BaselinePolicy, Memory, digest

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "miaosuan_agent"
SEAT = syn.RED_SEAT


def decide(raw, origin=Origin.ENGINE):
    return BaselinePolicy(ds.costs()).decide(Observation.from_raw(raw, origin), SEAT, ds.RED, Memory())


class ShuffleInvarianceTest(unittest.TestCase):
    def test_reordered_observations_decide_identically(self) -> None:
        reference = decide(ds.rich_observation())
        self.assertEqual(len(reference.actions), 3)
        for key in range(12):
            raw = ds.reordered(ds.rich_observation(), key)
            with self.subTest(permutation=key):
                decision = decide(raw)
                self.assertEqual(decision.actions, reference.actions)
                self.assertEqual(digest(decision.trace), digest(reference.trace))
                via_json = decide(syn.json_round_trip(raw), Origin.JSON)
                self.assertEqual(digest(via_json.trace), digest(reference.trace))

    def test_permutations_really_differ(self) -> None:
        original = ds.rich_observation()
        changed = {key: ds.reordered(original, key) for key in (1, 2)}
        for raw in changed.values():
            self.assertNotEqual(list(raw["valid_actions"]), list(original["valid_actions"]))
            self.assertNotEqual(raw["valid_actions"][ds.UNIT_A][2], original["valid_actions"][ds.UNIT_A][2])
            self.assertNotEqual(raw["cities"], original["cities"])


SUBPROCESS_PROGRAM = """
import sys
sys.path[:0] = [{src!r}, {root!r}]
from tests.test_decision_determinism import decide
from tests.fixtures import decision_scenarios as ds
from miaosuan_agent.decision import digest
print(digest(decide(ds.rich_observation()).trace))
"""


class HashSeedTest(unittest.TestCase):
    def test_trace_independent_of_hash_seed(self) -> None:
        program = SUBPROCESS_PROGRAM.format(src=str(ROOT / "src"), root=str(ROOT))
        digests = set()
        for seed in ("0", "1", "4242", "random"):
            env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
            env["PYTHONHASHSEED"] = seed
            result = subprocess.run([sys.executable, "-c", program], env=env, capture_output=True, text=True,
                                    timeout=120, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            digests.add(result.stdout.strip())
        self.assertEqual(digests, {digest(decide(ds.rich_observation()).trace)})


def _forbidden(*_args, **_kwargs):
    raise AssertionError("production decision code called a clock or a random source")


class NoClockNoRandomnessTest(unittest.TestCase):
    PATCHED = ("time.time", "time.time_ns", "time.perf_counter", "time.monotonic", "time.process_time",
               "random.random", "random.randint", "random.choice", "random.shuffle", "random.sample",
               "random.uniform", "random.getrandbits", "uuid.uuid1", "uuid.uuid4", "os.urandom",
               "secrets.token_bytes", "secrets.randbelow")

    def test_full_agent_lifecycle_without_clock_or_randomness(self) -> None:
        patchers = [mock.patch(target, _forbidden) for target in self.PATCHED]
        for patcher in patchers:
            patcher.start()
        try:
            agent = BaselineAgent(strict=True)
            agent.setup({"seat": SEAT, "faction": ds.RED, "cost_data": syn.cost_data()})
            deploy = ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102)], {ds.UNIT_A: {1: None}},
                                         stage=1, cur_step=0, ended=False)
            self.assertEqual(agent.step(deploy), [{"actor": SEAT, "type": 333}])
            self.assertEqual(len(agent.step(ds.rich_observation())), 3)
            agent.reset()
        finally:
            for patcher in patchers:
                patcher.stop()

    def test_decision_sources_import_no_clock_or_random_module(self) -> None:
        forbidden_modules = {"random", "time", "uuid", "secrets", "os", "datetime", "glob", "threading",
                             "multiprocessing", "numpy", "socket"}
        forbidden_calls = {"id", "hash", "globals", "locals", "vars", "input", "open"}
        files = sorted((PACKAGE / "decision").glob("*.py")) + [PACKAGE / "agent.py"]
        self.assertGreaterEqual(len(files), 8)
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                with self.subTest(file=path.name, line=getattr(node, "lineno", 0)):
                    if isinstance(node, ast.Import):
                        names = {alias.name.split(".")[0] for alias in node.names}
                        self.assertFalse(names & forbidden_modules, names)
                    elif isinstance(node, ast.ImportFrom) and node.level == 0:
                        self.assertNotIn(node.module.split(".")[0], forbidden_modules)
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, forbidden_calls)

    def test_source_scan_detects_a_planted_import(self) -> None:
        tree = ast.parse("import random\nfrom time import perf_counter\nx = id(object())\n")
        kinds = [type(node).__name__ for node in ast.walk(tree)
                 if isinstance(node, (ast.Import, ast.ImportFrom))
                 or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "id")]
        self.assertEqual(sorted(kinds), ["Call", "Import", "ImportFrom"])


def golden_observations():
    """A scripted sequence of situations (independent observations, not an engine simulation)."""
    city = [syn.city(505, flag=-1)]
    tank = lambda hex_, **kw: syn.unit(ds.UNIT_A, ds.RED, hex_, unit_type=ds.VEHICLE, **kw)  # noqa: E731
    enemy = syn.unit(ds.ENEMY_A, ds.BLUE, 405)
    return [
        ds.play_observation([tank(102)], {ds.UNIT_A: {1: None}}, stage=1, cur_step=0, ended=False, cities=city),
        ds.play_observation([tank(102)], {ds.UNIT_A: {1: None}}, cur_step=1, cities=city),
        ds.play_observation([tank(103, move_path=(204, 304, 405, 505))], {ds.UNIT_A: {1: None}}, cur_step=2,
                            cities=city),
        ds.play_observation([tank(304), enemy], {ds.UNIT_A: {1: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 2),
                                                                          ds.shoot(ds.ENEMY_A, ds.MISSILE, 4)]}},
                            cur_step=3, cities=city),
        ds.play_observation([tank(505)], {ds.UNIT_A: {1: None, 5: None}}, cur_step=4, cities=city),
        ds.play_observation([tank(505)], {ds.UNIT_A: {1: None}}, cur_step=5, cities=[syn.city(505, flag=ds.RED)]),
    ]


GOLDEN_ACTIONS = [
    [{"actor": SEAT, "type": 333}],
    [{"actor": SEAT, "type": 1, "obj_id": ds.UNIT_A, "move_path": [103, 204, 304, 405, 505]}],
    [],
    [{"actor": SEAT, "type": 2, "obj_id": ds.UNIT_A, "target_obj_id": ds.ENEMY_A, "weapon_id": ds.MISSILE}],
    [{"actor": SEAT, "type": 5, "obj_id": ds.UNIT_A}],
    [],
]
#: Chained digest of the six golden traces. If this changes, the behaviour of the policy changed:
#: that requires a new baseline identity and a rerun of the registered evaluation.
GOLDEN_TRACE_CHAIN = "0743df89c0855d7673352ce16727c1c613264839659b157183f6a97fbaa7cff2"


class GoldenDecisionsTest(unittest.TestCase):
    def test_baseline_identity(self) -> None:
        self.assertEqual(BASELINE_ID, "baseline-v0")

    def test_golden_sequence(self) -> None:
        agent = BaselineAgent(strict=True)
        agent.setup({"seat": SEAT, "faction": ds.RED, "cost_data": syn.cost_data()})
        chain = hashlib.sha256()
        for index, (raw, expected) in enumerate(zip(golden_observations(), GOLDEN_ACTIONS)):
            with self.subTest(step=index):
                self.assertEqual(agent.step(raw), expected)
            chain.update(digest(agent.last_trace).encode("ascii"))
        self.assertEqual(agent.last_trace.units[0].no_op_reason, "no candidate; move: no objective outside own control")
        self.assertEqual(chain.hexdigest(), GOLDEN_TRACE_CHAIN)


if __name__ == "__main__":
    unittest.main()
