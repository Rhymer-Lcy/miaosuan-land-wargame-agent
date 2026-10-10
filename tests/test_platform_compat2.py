"""The ``compat2`` platform wrapper (``scripts/build_platform_package.py``). SYNTHETIC game data only.

The online platform passed ``setup_info.seat`` as ``"p3"``, keyed ``role_and_grouping_info`` by ``"p<N>"`` plus a
non-player ``"god"`` entry, and sent string user ids and a string scenario id; compat1's setup failed on the seat. These
tests rebuild that representation from the fake engine's game (``platform_form``: every value is the engine's, only
the seat representation and the evidenced extra fields change) and check the adapter: the incident reproduces against
compat1 and not against compat2, the seat mapping and the outbound actor, fail-closed seat handling, cost_data
diagnostics, unchanged engine-form behaviour, bounded and value-free diagnostics, reset, and that a planted defect in
each critical rule is caught.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pickle
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_builder():
    spec = importlib.util.spec_from_file_location("build_platform_package", ROOT / "scripts" / "build_platform_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CASES = r'''
import contextlib, io, json, pickle, sys
root, inputs_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
from ai import Agent
import ai.agent
data = pickle.load(open(inputs_path, "rb"))
platform, engine = data["platform"], data["engine"]
seat = sorted(platform["setups"])[0]
setup = platform["setups"][seat]
steps = [ob for s, ob, _ in platform["steps"] if s == seat]
deploy = next(ob for ob in steps if ob["time"]["stage"] == 1)
play = next(ob for ob in steps if ob["time"]["stage"] == 2)

def run(setup_info, observations):
    agent, err = Agent(), io.StringIO()
    with contextlib.redirect_stderr(err):
        agent.setup(setup_info)
        actions = [agent.step(ob) for ob in observations]
    return {"status": getattr(agent, "status", None), "actions": actions, "stderr": err.getvalue()}

def with_table(ob, edit):
    ob = dict(ob)
    ob["role_and_grouping_info"] = edit(dict(ob["role_and_grouping_info"]))
    return ob

out = {"wrapper": getattr(ai.agent, "WRAPPER", None), "seat": setup["seat"]}
out["incident"] = run(setup, [deploy, play])
bad = {"p0": "p0", "p03": "p03", "P1": "P1", "decimal": "1", "trailing": setup["seat"] + " ", "pp": "pp1", "empty": "",
       "god": "god", "none": None, "bool": True, "float": 1.5, "negative": "p-1", "fullwidth": "p１"}
out["bad_seats"] = {name: run(dict(setup, seat=value), [deploy, play]) for name, value in bad.items()}
out["bad_faction"] = run(dict(setup, faction="1"), [deploy])
out["god_with_units"] = run(setup, [with_table(deploy, lambda t: dict(t, god=dict(t["god"], operators=[1]))),
                                    with_table(play, lambda t: dict(t, god=dict(t["god"], operators=[1])))])
out["unknown_key"] = run(setup, [with_table(deploy, lambda t: dict(t, observer=dict(t["god"])))])
out["collision"] = run(setup, [with_table(deploy, lambda t: dict(t, **{seat_key[1:]: t[seat_key]}))
                               for seat_key in [setup["seat"]]])
no_cost = {k: v for k, v in setup.items() if k != "cost_data"}
out["cost_absent"] = run(no_cost, [deploy, play])
out["cost_malformed"] = run(dict(setup, cost_data=[]), [deploy, play])
out["cost_modes"] = run(dict(setup, cost_data=setup["cost_data"][:3]), [deploy])
agent, err = Agent(), io.StringIO()
with contextlib.redirect_stderr(err):
    agent.setup(dict(setup, seat="bad"))
    first = getattr(agent, "status", None)
    agent.setup(setup)
    second = getattr(agent, "status", None)
    again = agent.step(deploy)
    agent.reset()
    after_reset = getattr(agent, "status", None)
    stray = agent.step(deploy)
    agent.setup(setup)
    third = getattr(agent, "status", None)
    replay = agent.step(deploy)
out["repeat"] = {"first": first, "second": second, "again": again, "after_reset": after_reset, "stray": stray,
                 "third": third, "replay": replay, "stderr": err.getvalue()}
agents, err, game = {}, io.StringIO(), []
with contextlib.redirect_stderr(err):
    for s, info in platform["setups"].items():
        agents[s] = Agent()
        agents[s].setup(info)
    for s, ob, _ in platform["steps"]:
        game.append([s, agents[s].step(ob)])
out["game"] = {"actions": game, "stderr": err.getvalue(), "status": {str(s): getattr(a, "status", None) for s, a in agents.items()}}
print(json.dumps(out))
'''


def run_cases(builder, data: bytes, inputs: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "extract"
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(root)
        pickled = Path(tmp) / "inputs.pkl"
        pickled.write_bytes(pickle.dumps({"platform": builder.platform_form(inputs), "engine": inputs}, protocol=4))
        script = Path(tmp) / "cases.py"
        script.write_text(CASES, encoding="utf-8")
        result = subprocess.run([sys.executable, "-I", "-B", str(script), str(root), str(pickled)], capture_output=True,
                                text=True, cwd=tmp)
    if result.returncode != 0:
        raise AssertionError(f"cases failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout.strip().splitlines()[-1])


# -- the checks: each returns a list of problems (empty: the check passes) ------------------------------------------


def incident_fixed(cases: Dict[str, Any]) -> list:
    problems = []
    incident = cases["incident"]
    seat = cases["seat"]
    if incident["status"] != "ready":
        problems.append(f"status {incident['status']}")
    if incident["actions"][0] != [{"actor": seat, "type": 333}]:
        problems.append(f"deployment actions {incident['actions'][0]}")
    if "setup OK" not in incident["stderr"] or "SETUP FAILED" in incident["stderr"]:
        problems.append("setup diagnostics")
    return problems


def bad_seats_fail_closed(cases: Dict[str, Any]) -> list:
    problems = []
    for name, case in cases["bad_seats"].items():
        if case["status"] != "failed" or any(case["actions"]) or "SETUP FAILED" not in case["stderr"] \
                or "category seat" not in case["stderr"] or "setup OK" in case["stderr"]:
            problems.append(name)
    return problems


def non_player_rule(cases: Dict[str, Any]) -> list:
    problems = []
    for name in ("god_with_units", "unknown_key"):
        stderr = cases[name]["stderr"]
        if "input error" not in stderr or "category seat" not in stderr:
            problems.append(f"{name}: not refused")
    if cases["god_with_units"]["actions"][1]:
        problems.append("god_with_units: play-stage actions after a refused seat table")
    return problems


def collision_detected(cases: Dict[str, Any]) -> list:
    stderr = cases["collision"]["stderr"]
    return [] if "collide" in stderr and "input error" in stderr else ["collision not detected"]


def failure_is_not_success(cases: Dict[str, Any]) -> list:
    problems = []
    malformed = cases["cost_malformed"]
    if malformed["status"] != "failed" or "SETUP FAILED" not in malformed["stderr"] or "setup OK" in malformed["stderr"]:
        problems.append("malformed cost_data reported as success")
    if "category cost_data" not in malformed["stderr"]:
        problems.append("malformed cost_data category")
    if malformed["actions"][1]:
        problems.append("play-stage actions after a failed setup")
    return problems


class Compat2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.b = load_builder()
        cls.canary = cls.b.entries()
        cls.compat1 = cls.b.entries("compat1")
        cls.payload = cls.b.entries("compat2")
        cls.data = cls.b.write_zip(cls.payload)
        cls.inputs = cls.b.synthetic_inputs()
        cls.cases = run_cases(cls.b, cls.data, cls.inputs)
        cls.compat1_cases_stderr = run_cases(cls.b, cls.b.write_zip(cls.compat1), cls.inputs)["incident"]

    # 1, 2: the incident
    def test_compat1_reproduces_the_incident(self) -> None:
        incident = self.compat1_cases_stderr
        self.assertIn("setup error: ContractError: setup_info.seat: expected an int", incident["stderr"])
        self.assertEqual(incident["actions"], [[], []])

    def test_compat2_accepts_the_platform_seat(self) -> None:
        self.assertEqual(self.cases["wrapper"], "compat2")
        self.assertEqual(self.cases["seat"], "p1")
        self.assertEqual(incident_fixed(self.cases), [])
        self.assertIn("external seat 'p<N>' mapped to the internal seat", self.cases["incident"]["stderr"])

    # 3, 4, 6: seats
    def test_malformed_seats_fail_closed(self) -> None:
        self.assertEqual(len(self.cases["bad_seats"]), 13)
        self.assertEqual(bad_seats_fail_closed(self.cases), [])
        faction = self.cases["bad_faction"]
        self.assertEqual((faction["status"], faction["actions"]), ("failed", [[]]))
        self.assertIn("category faction", faction["stderr"])

    def test_non_player_entries(self) -> None:
        self.assertEqual(non_player_rule(self.cases), [])
        # the regular non-player entry is accepted: the incident case carries it
        self.assertIn("non-player x1", self.cases["incident"]["stderr"])

    def test_seat_key_collision(self) -> None:
        self.assertEqual(collision_detected(self.cases), [])

    # 5, 15, 16, 11, 12, 14: whole games in three forms
    def test_engine_json_and_platform_forms(self) -> None:
        for label, inputs in (("engine", self.inputs), ("json", self.b.json_form(self.inputs)),
                              ("platform", self.b.platform_form(self.inputs))):
            result = self.b.smoke(self.data, inputs, sys.executable)
            self.assertEqual((label, result["steps"], result["mismatches"]), (label, len(self.inputs["steps"]), 0))
        expected = [a for _, _, actions in self.b.platform_form(self.inputs)["steps"] for a in actions]
        self.assertIn(1, {a["type"] for a in expected}, "the synthetic game must contain MOVE")
        self.assertEqual({a["actor"] for a in expected}, {"p1", "p11"})

    def test_engine_form_entry_differs_from_canary_only_in_the_wrapper(self) -> None:
        differing = sorted(name for name in self.payload if self.payload[name] != self.canary[name])
        self.assertEqual(differing, ["ai/PACKAGE.json", "ai/agent.py"])
        self.assertEqual(json.loads(self.payload["ai/PACKAGE.json"])["wrapper"], "compat2")
        self.assertEqual(self.b.verify_zip(self.data), [])
        self.assertEqual(self.b.write_zip(self.b.entries("compat2")), self.data)

    # 13: every returned action is legal under the documented checks, re-derived here
    def test_returned_actions_are_legal(self) -> None:
        from miaosuan_agent.boundary import MoveCosts
        costs = MoveCosts.from_raw(self.inputs["setups"][1]["cost_data"])
        game = self.cases["game"]
        self.assertEqual(game["status"], {"1": "ready", "11": "ready"})
        moves = 0
        for seat, actions in game["actions"]:
            for action in actions:
                self.assertEqual(action["actor"], f"p{seat}")
                if action["type"] == 1:
                    moves += 1
                    path = action["move_path"]
                    self.assertTrue(path and all(isinstance(h, int) for h in path))
                    self.assertEqual(len(set(path)), len(path))
                    self.assertTrue(any(all(b in costs.neighbours(mode, a) for a, b in zip(path, path[1:]))
                                        for mode in range(len(costs.edges))))
        self.assertGreater(moves, 0)

    # 7, 8: cost_data
    def test_cost_data_diagnostics(self) -> None:
        self.assertIn("movement router ready", self.cases["incident"]["stderr"])
        self.assertIn("parsed (4 modes", self.cases["incident"]["stderr"])
        self.assertIn("JSON keys converted", self.cases["incident"]["stderr"])
        absent = self.cases["cost_absent"]
        self.assertEqual(absent["status"], "ready")
        self.assertIn("cost_data ABSENT", absent["stderr"])
        self.assertIn("movement router UNAVAILABLE", absent["stderr"])
        self.assertNotIn(1, {a["type"] for actions in absent["actions"] for a in actions})
        self.assertEqual(failure_is_not_success(self.cases), [])
        self.assertEqual(self.cases["cost_malformed"]["actions"][0], [{"actor": "p1", "type": 333}])
        self.assertIn("FALLBACK (setup failed)", self.cases["cost_malformed"]["stderr"])
        self.assertIn("category cost_data", self.cases["cost_modes"]["stderr"])

    # 9: the string scenario id and the extra field reach the policy without a contract error
    def test_platform_metadata_passes(self) -> None:
        stderr = self.cases["game"]["stderr"]
        self.assertNotIn("contract error", stderr)
        self.assertNotIn("input error", stderr)
        self.assertIn("first MOVE emitted", stderr)

    # 17, 19: failure is never success; reset and repeated setup
    def test_reset_and_repeated_setup(self) -> None:
        repeat = self.cases["repeat"]
        self.assertEqual((repeat["first"], repeat["second"], repeat["after_reset"], repeat["third"]),
                         ("failed", "ready", "uninitialized", "ready"))
        self.assertEqual(repeat["again"], [{"actor": "p1", "type": 333}])
        self.assertEqual(repeat["stray"], [])
        self.assertEqual(repeat["replay"], [{"actor": "p1", "type": 333}])
        self.assertIn("step while uninitialized", repeat["stderr"])

    # 18: diagnostics carry no unit id, hex or user name, and stay bounded
    def test_diagnostics_are_value_free_and_bounded(self) -> None:
        platform = self.b.platform_form(self.inputs)
        private_values = set()
        for _, ob, _ in platform["steps"]:
            for unit in ob["operators"]:
                private_values.update({str(unit["obj_id"]), str(unit["cur_hex"])})
            for city in ob.get("cities") or ():
                private_values.add(str(city["coord"]))
            for entry in ob["role_and_grouping_info"].values():
                if entry.get("user_name") not in (None, "god"):
                    private_values.add(str(entry["user_name"]))
        self.assertGreater(len(private_values), 3)
        texts = [self.cases["game"]["stderr"], self.cases["incident"]["stderr"], self.cases["cost_malformed"]["stderr"]]
        texts += [case["stderr"] for case in self.cases["bad_seats"].values()]
        import re
        words = {word for text in texts for word in re.findall(r"[A-Za-z0-9_]+", text)}
        self.assertEqual(private_values & words, set())
        for text in texts:
            lines = [line for line in text.splitlines() if line]
            self.assertLessEqual(len(lines), 51)
            self.assertTrue(all(line.startswith("[baseline-v2/compat2] ") for line in lines), lines)

    # 20: a planted defect in each critical rule is caught by its check
    def test_planted_defects_are_caught(self) -> None:
        source = self.payload["ai/agent.py"].decode("utf-8")
        plants = {
            "seat mapping off by one": ("            return int(match.group(1))\n    raise SeatError(\"setup_info.seat\"",
                                        "            return int(match.group(1)) + 1\n    raise SeatError(\"setup_info.seat\"",
                                        "platform"),
            "actor not converted back": ('converted["actor"] = self._external', 'converted["actor"] = self._internal',
                                         "platform"),
            "JSON keys not converted": ("(int(key) if rekey else key, new)", "(key, new)", "json"),
            "non-player entry with units accepted": ("and not entry.get(\"operators\"))", ")", non_player_rule),
            "collision ignored": ("        if internal in adapted:\n", "        if False:\n", collision_detected),
            "failed setup reported as ready": ("            self.status = \"failed\"\n            where, category",
                                               "            self.status = \"ready\"\n            where, category",
                                               failure_is_not_success),
            "bad seats accepted": ("    raise SeatError(\"setup_info.seat\", \"an int or 'p<N>' with N >= 1\")",
                                   "    return 1", bad_seats_fail_closed),
        }
        caught = {}
        for label, (old, new, check) in plants.items():
            self.assertEqual(source.count(old), 1, label)
            planted = dict(self.payload)
            planted["ai/agent.py"] = source.replace(old, new).encode("utf-8")
            data = self.b.write_zip(planted)
            if isinstance(check, str):
                inputs = self.b.platform_form(self.inputs) if check == "platform" else self.b.json_form(self.inputs)
                try:
                    caught[label] = self.b.smoke(data, inputs, sys.executable)["mismatches"] > 0
                except SystemExit:
                    caught[label] = True
            else:
                caught[label] = bool(check(run_cases(self.b, data, self.inputs)))
        self.assertEqual(caught, {label: True for label in plants})


if __name__ == "__main__":
    unittest.main()
