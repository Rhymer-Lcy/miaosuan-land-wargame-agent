"""Sprint 35 offline selection rule on SYNTHETIC summaries (evaluation.s35_offline)."""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.evaluation import s35_offline as so


def model_summary(value: int) -> dict:
    return {"games": 80, "objective_value": value, "rejections": 0, "model_refusals": 0, "fallbacks": 0,
            "replay_mismatches": 0, "replay_checks": 40, "max_wait": 20, "latency_ms_max": 250.0, "friendly_exposure": 0}


def genuine_summary() -> dict:
    return {"rejections": 0, "independent_illegal": 0, "fallbacks": 0, "contract_errors": 0, "latency_ms_p99": 30.0,
            "latency_ms_max": 300.0, "decisions_differing_from_control": 500, "play_decisions": 10000}


def precursors() -> dict:
    return {"episodes": 57, "alerted": 40, "departures": 18, "departures_kept": 12, "responded": 30}


def summaries(ca=(1000, 900), cm=(1000, 900)) -> dict:
    return {name: {"model": {"M-inert": model_summary(v[0]), "M-v2": model_summary(v[1])}, "genuine": genuine_summary(),
                   "precursors": precursors()} for name, v in (("CA", ca), ("CM", cm))}


CONTROL = {"model": {"M-inert": model_summary(1000), "M-v2": model_summary(900)},
           "fidelity": {"decisions": 46000, "differing": 0}}


class SelectionTests(unittest.TestCase):
    def test_both_pass_and_cm_within_two_percent(self):
        self.assertEqual(so.select(summaries(cm=(980, 882)), CONTROL)["selected"], "CM")

    def test_cm_below_two_percent_in_one_population_selects_ca(self):
        result = so.select(summaries(cm=(1000, 881)), CONTROL)    # 881 < 0.98 x 900 = 882
        self.assertEqual(result["selected"], "CA")

    def test_one_failing_gate_leaves_the_other(self):
        s = summaries()
        s["CM"]["genuine"]["independent_illegal"] = 1
        self.assertEqual(so.select(s, CONTROL)["selected"], "CA")
        s = summaries()
        s["CA"]["precursors"]["departures_kept"] = 8                # 8 < 0.5 x 18
        self.assertEqual(so.select(s, CONTROL)["selected"], "CM")

    def test_no_candidate_or_broken_fidelity_selects_nothing(self):
        s = summaries()
        for name in ("CA", "CM"):
            s[name]["model"]["M-v2"]["max_wait"] = 300
        self.assertIsNone(so.select(s, CONTROL)["selected"])
        broken = copy.deepcopy(CONTROL)
        broken["fidelity"]["differing"] = 1
        self.assertIsNone(so.select(summaries(), broken)["selected"])
        empty = copy.deepcopy(CONTROL)
        empty["fidelity"]["decisions"] = 0
        self.assertIsNone(so.select(summaries(), empty)["selected"])

    def test_each_gate_can_fail(self):
        breakers = {
            "G1 no rejected, refused or independently illegal action": lambda s: s["genuine"].update(rejections=1),
            "G2 no fallback or contract error": lambda s: s["genuine"].update(fallbacks=1),
            "G3 model replay identical": lambda s: s["model"]["M-inert"].update(replay_mismatches=1),
            "G4 no deadlock wait": lambda s: s["model"]["M-inert"].update(max_wait=300),
            "G5 latency": lambda s: s["genuine"].update(latency_ms_p99=100.5),
            "G6 differs from the Sprint 34 control": lambda s: s["genuine"].update(decisions_differing_from_control=99),
            "G7 no friendly exposure": lambda s: s["model"]["M-v2"].update(friendly_exposure=1),
            "G8 every population played": lambda s: s["precursors"].update(episodes=0, alerted=0),
            "G9 threat recognised before the loss": lambda s: s["precursors"].update(alerted=28),
            "G10 last defenders kept": lambda s: s["precursors"].update(departures_kept=8),
            "G11 no collapse of the movement race": lambda s: s["model"]["M-v2"].update(objective_value=809),
        }
        clean = summaries()["CA"]
        baseline = so.gates(clean["model"], clean["genuine"], clean["precursors"], CONTROL["model"])
        self.assertEqual(len(baseline), 11)
        self.assertTrue(all(baseline.values()))
        self.assertEqual(set(breakers), set(baseline))
        for name, breaker in breakers.items():
            s = copy.deepcopy(clean)
            breaker(s)
            result = so.gates(s["model"], s["genuine"], s["precursors"], CONTROL["model"])
            self.assertFalse(result[name], name)

    def test_precursor_summary(self):
        rows = [{"alerted": True, "departure": True, "kept": True, "responded": False, "stance_b150": "delay"},
                {"alerted": False, "departure": True, "kept": False, "responded": True, "stance_b150": "quiet"},
                {"alerted": True, "departure": False, "kept": True, "responded": True, "stance_b150": "delay"}]
        self.assertEqual(so.summarise_precursors(rows), {"episodes": 3, "alerted": 2, "departures": 2,
                                                         "departures_kept": 1, "responded": 2,
                                                         "stance_b150": {"delay": 2, "quiet": 1}})


if __name__ == "__main__":
    unittest.main()
