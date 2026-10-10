"""Sprint 34 offline selection rule on synthetic summaries (no SDK data)."""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.evaluation import s34_offline as so


def model(value=300, **changes):
    base = {"games": 80, "objective_value": value, "rejections": 0, "fallbacks": 0, "replay_mismatches": 0,
            "replay_checks": 500, "model_refusals": 0, "max_wait": 0, "latency_ms_max": 120.0,
            "friendly_exposure": 0}
    base.update(changes)
    return base


def genuine(**changes):
    base = {"rejections": 0, "independent_illegal": 0, "fallbacks": 0, "contract_errors": 0, "latency_ms_p99": 20.0,
            "latency_ms_max": 300.0, "decisions_differing": 900, "play_decisions": 40000}
    base.update(changes)
    return base


def summaries(ct=(1000, 800), mo=(1000, 800)):
    return {"CT": {"model": {"M-inert": model(ct[0]), "M-v2": model(ct[1])}, "genuine": genuine()},
            "MO": {"model": {"M-inert": model(mo[0]), "M-v2": model(mo[1])}, "genuine": genuine()}}


class SelectionRuleTests(unittest.TestCase):
    def test_mo_within_two_percent_is_selected(self):
        self.assertEqual(so.select(summaries(mo=(981, 785)))["selected"], "MO")

    def test_mo_beyond_two_percent_loses_to_a_better_ct(self):
        self.assertEqual(so.select(summaries(mo=(970, 800)))["selected"], "CT")
        self.assertEqual(so.select(summaries(mo=(1000, 780)))["selected"], "CT")

    def test_mo_better_in_total_but_worse_in_one_population(self):
        self.assertEqual(so.select(summaries(mo=(1150, 700)))["selected"], "MO")

    def test_a_tie_in_total_goes_to_ct(self):
        self.assertEqual(so.select(summaries(mo=(1100, 700)))["selected"], "CT")

    def test_every_gate_can_disqualify(self):
        planted = [("model", "M-inert", "rejections", 1), ("model", "M-v2", "model_refusals", 1),
                   ("model", "M-inert", "fallbacks", 2), ("model", "M-v2", "replay_mismatches", 1),
                   ("model", "M-v2", "replay_checks", 0), ("model", "M-inert", "max_wait", so.DEADLOCK_WAIT),
                   ("model", "M-v2", "latency_ms_max", so.LATENCY_MAX_MS + 1),
                   ("model", "M-inert", "friendly_exposure", 1), ("model", "M-v2", "games", 0),
                   ("genuine", None, "independent_illegal", 1), ("genuine", None, "rejections", 1),
                   ("genuine", None, "contract_errors", 1), ("genuine", None, "fallbacks", 1),
                   ("genuine", None, "latency_ms_p99", so.LATENCY_P99_MS + 0.1),
                   ("genuine", None, "decisions_differing", 399), ("genuine", None, "play_decisions", 0)]
        for part, population, key, value in planted:
            s = summaries(mo=(2000, 2000))
            target = s["MO"][part][population] if population else s["MO"][part]
            target[key] = value
            result = so.select(s)
            self.assertEqual(result["selected"], "CT", (part, population, key))
            failed = [g for g, ok in result["gates"]["MO"].items() if not ok]
            self.assertEqual(len(failed), 1, (key, failed))

    def test_no_candidate_passes(self):
        s = summaries()
        for c in ("CT", "MO"):
            s[c]["genuine"]["fallbacks"] = 1
        self.assertIsNone(so.select(s)["selected"])

    def test_model_summary_reads_only_the_candidate_seat(self):
        game = {"seats": {"0": {"agent": "MO", "rejected": {}, "fallbacks": 0, "replay_mismatches": 0,
                                "replay_checks": 3, "latency_ms_max": 5.0, "embarked": 1, "indirect_orders": 2,
                                "friendly_exposure_unit_steps": 0},
                          "1": {"agent": "inert", "rejected": {"x": 4}, "fallbacks": 9, "replay_mismatches": 0,
                                "replay_checks": 0, "latency_ms_max": 1.0, "embarked": 0, "indirect_orders": 0}},
                "occupy": {"red_occupy": 130, "blue_occupy": 50}, "model_refusals": 0,
                "max_wait": {"0": 12, "1": 900}, "wait_unit_steps": {"0": 12, "1": 900},
                "first_owner": {"5": [0, 300], "6": [1, 200]}, "objective_value_total": 180}
        s = so.summarise_model([game, copy.deepcopy(game)], "MO")
        self.assertEqual((s["games"], s["objective_value"], s["fallbacks"], s["max_wait"], s["first_owned"]),
                         (2, 260, 0, 12, 2))
        self.assertEqual(s["first_owned_median_step"], 300)


if __name__ == "__main__":
    unittest.main()
