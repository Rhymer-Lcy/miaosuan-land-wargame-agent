"""Sprint 36 offline comparison rules: episode reading, gates and the selection rule (SYNTHETIC inputs)."""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.evaluation import s36_offline as O


def row(uid, colour, hex_, path=0, value=10, aboard=0, sub=0):
    return [uid, colour, 2, sub, hex_, path, 0.0, 3, value, aboard]


def steps_with_loss():
    """Decisions every 40 steps. Own (colour 0) tank 1 and squad 2 stand in the zone of 505; the squad is at 909 from
    step 240, the tank is gone at step 320; the objective flips at step 360."""
    out = []
    for s in range(0, 11):
        units = []
        if s <= 7:
            units.append(row(1, 0, 505))
        if s <= 5:
            units.append(row(2, 0, 506, value=4, sub=2))
        elif s <= 10:
            units.append(row(2, 0, 909, value=4, sub=2))
        flag = 0 if s < 9 else 1
        out.append({"k": s, "cur_step": 40 * s, "units": units, "cities": [[505, flag, 80]]})
    return out


class EpisodeTests(unittest.TestCase):
    def test_episodes_from_timeline(self):
        e = O.episodes_from_timeline(steps_with_loss(), 0)
        self.assertEqual(len(e["losses"]), 1)
        self.assertEqual(e["losses"][0]["step"], 360)
        self.assertEqual(e["destroyed"], [{"unit": 1, "sub_type": 0, "value": 10, "objective": 505, "step": 320}])
        self.assertEqual(O.episode_counts(e), {"losses": 1, "destroyed_in_held_zone": 1, "departures": 0})

    def test_read_episodes(self):
        steps = steps_with_loss()
        e = O.episodes_from_timeline(steps, 0)
        # agent A orders the tank out at step 160 and keeps a unit at 505 in its stance; agent B never acts
        per_a = {40 * s: {"actions": [], "stances": {505: {"stance": "delay", "keep": [2]}}} for s in range(0, 11)}
        per_a[160]["actions"] = [{"type": 1, "obj_id": 1, "move_path": [606, 707]}]
        per_b = {40 * s: {"actions": [], "stances": {}} for s in range(0, 11)}
        a = O.read_episodes(e, per_a, steps, 0, cheap_limit=5.0)
        b = O.read_episodes(e, per_b, steps, 0, cheap_limit=5.0)
        self.assertEqual(a["destroyed_valuable"], 1)
        self.assertEqual(a["destroyed_valuable_ordered_out_before"], 1)
        self.assertEqual(b["destroyed_valuable_ordered_out_before"], 0)
        self.assertEqual(a["recognised_150_before"], 1)         # the decision at 200 = nearest to 360 - 150
        self.assertEqual(b["recognised_150_before"], 0)
        self.assertEqual(a["presence_in_last_300"], 1)
        self.assertEqual(b["presence_in_last_300"], 1)          # the tank stood there and B did not move it
        early = O.read_episodes({"losses": [dict(e["losses"][0], step=100)], "destroyed": []}, per_a, steps, 0, 5.0)
        self.assertEqual(early["recognised_150_before"], 0)     # no decision 150 steps before step 100


def model_summary(values):
    pops = {}
    for name, (inert, v2) in values.items():
        base = {"games": 80, "rejections": 0, "model_refusals": 0, "fallbacks": 0, "replay_checks": 10,
                "replay_mismatches": 0, "max_wait": 20, "latency_ms_max": 300.0}
        pops[f"M-inert|{name}"] = dict(base, objective_value=inert)
        pops[f"M-v2|{name}"] = dict(base, objective_value=v2)
    sides = {"1910631192 blue": {n: 130 for n in values}, "2010131194 red": {n: 50 for n in values}}
    return {"crashes": 0, "populations": pops, "m_inert_sides": sides}


def genuine_summary(names):
    agents = {n: {"rejections": 0, "independent_illegal": 0, "fallbacks": 0, "contract_errors": 0,
                  "latency_ms_p99_max_over_games": 30.0, "latency_ms_max": 400.0, "memory_bytes_max": 3000,
                  "differing_from_s34": 5000, "play_decisions": 100000} for n in names}
    return {"games": O.EXPECTED_GENUINE, "agents": agents, "equivalence_differences": {"CA vs ta-as-ca": 0,
                                                                                      "S34-MO vs tc-no-guard": 0}}


EPISODES = {"games": O.EXPECTED_EPISODE_GAMES, "control_fidelity": {"S34-MO decisions": 10, "S34-MO differing": 0,
                                                                    "CM decisions": 10, "CM differing": 0}}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        names = ("S34-MO", "CM", "TA", "TB", "TC")
        self.model = model_summary({n: (22480, 18300) for n in names})
        self.genuine = genuine_summary(names)

    def test_least_change_first(self):
        s = O.select(self.model, self.genuine, EPISODES)
        self.assertEqual(s["gates_passed"], ["TC", "TA", "TB"])
        self.assertEqual(s["selected"], "TC")

    def test_a_failed_gate_moves_to_the_next(self):
        genuine = copy.deepcopy(self.genuine)
        genuine["agents"]["TC"]["fallbacks"] = 1
        s = O.select(self.model, genuine, EPISODES)
        self.assertFalse(s["gates"]["TC"]["G2"]["pass"])
        self.assertEqual(s["selected"], "TA")

    def test_each_gate_can_fail(self):
        cases = {
            "G1": lambda m, g, e: g["agents"]["TC"].__setitem__("independent_illegal", 1),
            "G3": lambda m, g, e: m.__setitem__("crashes", 1),
            "G4": lambda m, g, e: m["populations"]["M-v2|TC"].__setitem__("max_wait", 300),
            "G5": lambda m, g, e: g["agents"]["TC"].__setitem__("latency_ms_max", 1000.5),
            "G6": lambda m, g, e: g["agents"]["TC"].__setitem__("memory_bytes_max", 200001),
            "G7": lambda m, g, e: m["m_inert_sides"]["2010131194 red"].__setitem__("TC", 0),
            "G8": lambda m, g, e: m["populations"]["M-v2|TC"].__setitem__("objective_value", 17384),
            "G9": lambda m, g, e: g.__setitem__("games", O.EXPECTED_GENUINE - 1),
            "G10": lambda m, g, e: g["equivalence_differences"].__setitem__("S34-MO vs tc-no-guard", 1),
            "G11": lambda m, g, e: e["control_fidelity"].__setitem__("CM differing", 1),
            "G12": lambda m, g, e: g["agents"]["TC"].__setitem__("differing_from_s34", 999),
        }
        for code, plant in cases.items():
            m, g, e = copy.deepcopy(self.model), copy.deepcopy(self.genuine), copy.deepcopy(EPISODES)
            plant(m, g, e)
            gates = O.select(m, g, e)["gates"]["TC"]
            self.assertFalse(gates[code]["pass"], code)
            self.assertTrue(all(v["pass"] for k, v in gates.items() if k != code), code)

    def test_movement_floor_boundary(self):
        m = copy.deepcopy(self.model)
        m["populations"]["M-v2|TC"]["objective_value"] = 17385          # 0.95 x 18300 = 17385
        self.assertTrue(O.select(m, self.genuine, EPISODES)["gates"]["TC"]["G8"]["pass"])

    def test_nothing_passes(self):
        g = copy.deepcopy(self.genuine)
        g["equivalence_differences"]["CA vs ta-as-ca"] = 2
        s = O.select(self.model, g, EPISODES)
        self.assertIsNone(s["selected"])
        self.assertEqual(s["disposition"], "S36_ENGINEERING_BLOCKED")


if __name__ == "__main__":
    unittest.main()
