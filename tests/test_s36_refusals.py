"""Sprint 36 refusal taxonomy and gate (SYNTHETIC records; every expectation is computed by hand beside it)."""

from __future__ import annotations

import unittest

from miaosuan_agent.evaluation import s36_refusals as R

GONE = "target no longer alive at resolution"
ACTOR = "actor no longer alive at resolution"
UNCLASSIFIED = "unclassified: no attribution rule for this factual class"


def fact(kind=2, code=516, message="CantShootToDiedBop", label=GONE, listed=True, gate=True, shots=1, unit=7):
    evidence = {"actor_on_map_at_start": True, "actor_present_after": True}
    if kind == 2:
        evidence["own_shots_at_target"] = shots
    return {"schema": "miaosuan-refusal-fact/1", "action_type": kind, "code": code, "message_class": message,
            "attribution": label, "legal_at_start": listed, "passed_project_gate": gate, "evidence": evidence,
            "obj_id": unit}


def seat(refusals, shots=10, moves=10, echo=None, retained=True):
    by_type = {"1": moves, "2": shots, "333": 1}
    unit_actions = moves + shots
    out = {"policy": "candidate", "actions_by_type": by_type,
           "feedback_entries": unit_actions if echo is None else echo,
           "feedback_errors_by_code": {str(r["code"]): 1 for r in refusals},
           "feedback_errors_by_code_and_type": {}, "units_seen": 6}
    if retained:
        out["refusals"] = list(refusals)
        out["refusal_facts"] = []
    for r in refusals:
        key = f"{r['code']}/{r['action_type']}"
        out["feedback_errors_by_code_and_type"][key] = out["feedback_errors_by_code_and_type"].get(key, 0) + 1
    out["feedback_errors_by_code"] = {}
    for r in refusals:
        out["feedback_errors_by_code"][str(r["code"])] = out["feedback_errors_by_code"].get(str(r["code"]), 0) + 1
    return out


class ClassifyTests(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(R.classify(fact()), "D")                                     # target killed by another cause
        self.assertEqual(R.classify(fact(shots=2)), "R")                              # second own shot at it
        self.assertEqual(R.classify(fact(code=203, message="CantControlDiedOperator", label=ACTOR)), "D")
        self.assertEqual(R.classify(fact(kind=5, code=203, message="CantControlDiedOperator", label=ACTOR)), "D")
        self.assertEqual(R.classify(fact(kind=14, code=103, message="ErrorActionType", label=UNCLASSIFIED,
                                         listed=False, gate=False)), "A")
        self.assertEqual(R.classify(fact(kind=14, code=103, message="ErrorActionType", label=UNCLASSIFIED)), "A")
        self.assertEqual(R.classify(fact(listed=False)), "A")                         # a shot not listed at start
        self.assertEqual(R.classify(fact(kind=1, code=404, message="CantMoveKeptPeople", label=UNCLASSIFIED,
                                         listed=False)), "B")                          # an unlisted move
        self.assertEqual(R.classify(fact(kind=1, code=404, message="CantMoveKeptPeople", label=UNCLASSIFIED)), "E")
        self.assertEqual(R.classify(fact(gate=False)), "A")
        self.assertEqual(R.classify(fact(code=999, message="Unheard", label=UNCLASSIFIED)), "E")
        self.assertEqual(R.classify(fact(kind=5, code=1804, message="CantOccupyCauseAlreadyMy",
                                         label="same-step duplicate objective occupation")), "R")
        missing = fact()
        missing["evidence"] = {}
        self.assertEqual(R.classify(missing), "E")                                    # 516 without the shot count

    def test_code_alone_never_decides(self):
        # a 516 whose attribution was contradicted is unexplained, not a race
        self.assertEqual(R.classify(fact(label="unclassified: evidence contradicts the rule")), "E")


class SummaryTests(unittest.TestCase):
    def test_denominators_and_echo(self):
        s = R.seat_summary(seat([fact()], shots=4, moves=2))
        self.assertEqual((s["unit_actions"], s["fire_actions"], s["other_actions"]), (6, 4, 2))
        self.assertTrue(s["echo_matches"])
        self.assertEqual(s["classes"]["D_fire"], 1)
        s = R.seat_summary(seat([fact()], shots=4, moves=2, echo=5))
        self.assertFalse(s["echo_matches"])

    def test_code_only_record_is_not_classified(self):
        s = R.seat_summary(seat([fact()], retained=False))
        self.assertFalse(s["retained"])
        self.assertEqual(R.structural_findings(s), ["refusal facts not retained: the game cannot be classified"])


class GateBoundaryTests(unittest.TestCase):
    """The owner's four boundary cases (section 3) and the calibrated constants."""

    def test_one_ordinary_refused_shot_in_a_six_action_game_is_not_a_stop(self):
        s = R.seat_summary(seat([fact()], shots=4, moves=2))
        self.assertTrue(R.s6_sprint35(s))                         # 1 > 2% of 6: Sprint 35's S6 fired
        self.assertEqual(R.proposed(s), {"structural": [], "systemic": []})

    def test_sprint35_position_19_two_races_in_fourteen_shots(self):
        s = R.seat_summary(seat([fact(), fact(code=203, message="CantControlDiedOperator", label=ACTOR, unit=8)],
                                shots=14, moves=17))
        self.assertTrue(R.s6_sprint35(s))                         # 2 of 31 = 6.5%
        self.assertEqual(R.proposed(s), {"structural": [], "systemic": []})

    def test_a_malformed_action_in_a_small_game_stops(self):
        s = R.seat_summary(seat([fact(listed=False)], shots=4, moves=2))
        self.assertEqual(R.structural_findings(s), ["1 contract refusal(s)"])
        s = R.seat_summary(seat([fact(kind=1, code=404, message="CantMoveKeptPeople", label=UNCLASSIFIED,
                                      listed=False)], shots=4, moves=2))
        self.assertEqual(R.structural_findings(s), ["1 movement or transition refusal of an unlisted action(s)"])

    def test_many_refused_shots_in_a_large_game_are_systemic(self):
        # 300 fire actions at the reference race rate 0.00776733: expected 2.33; the tail at 13 is below 1e-6, at 12
        # it is not (s36_refusals: the smallest k with P(X >= k) < 1e-6 for n = 300 is 13)
        n = 300
        p = R.REFERENCE_RATES["race_fire"]
        self.assertLess(R.upper_tail(13, n, p), 1e-6)
        self.assertGreaterEqual(R.upper_tail(12, n, p), 1e-6)
        big = R.seat_summary(seat([fact(unit=i) for i in range(13)], shots=n, moves=100))
        self.assertEqual(len(R.systemic_findings(big)), 1)
        ok = R.seat_summary(seat([fact(unit=i) for i in range(12)], shots=n, moves=100))
        self.assertEqual(R.systemic_findings(ok), [])
        self.assertTrue(R.absolute(ok, 3))                         # an absolute count would have fired at 3

    def test_unknown_semantics_are_counted_not_whitelisted(self):
        unknown = fact(code=999, message="Unheard", label=UNCLASSIFIED)
        one = R.seat_summary(seat([unknown]))
        self.assertEqual(R.structural_findings(one), [])
        self.assertEqual(R.structural_findings(one, e_before=2), ["3 unexplained refusals in the study"])
        two = R.seat_summary(seat([unknown, dict(unknown, obj_id=9)]))
        self.assertEqual(R.structural_findings(two), ["2 unexplained refusals in one game"])

    def test_redundant_refusals_and_repeated_actor(self):
        s = R.seat_summary(seat([fact(shots=2, unit=1), fact(shots=2, unit=2)], shots=40, moves=10))
        self.assertEqual(len(R.systemic_findings(s)), 1)          # two redundant: the reference made none
        s = R.seat_summary(seat([fact(unit=5), fact(unit=5), fact(unit=5)], shots=400, moves=10))
        self.assertIn("one unit refused 3 times", R.systemic_findings(s))

    def test_small_denominator_three_races(self):
        s = R.seat_summary(seat([fact(unit=i) for i in range(3)], shots=8, moves=2))
        self.assertEqual(R.systemic_findings(s), ["3 race refusals of 8 fire actions (fewer than 10 actions)"])
        s = R.seat_summary(seat([fact(unit=i) for i in range(2)], shots=8, moves=2))
        self.assertEqual(R.systemic_findings(s), [])

    def test_echo_mismatch_is_structural(self):
        s = R.seat_summary(seat([], shots=10, moves=10, echo=19))
        self.assertEqual(R.structural_findings(s), ["the engine echoed 19 actions of the seat, 20 emitted"])

    def test_dangerous_action_is_structural(self):
        s = R.seat_summary(seat([]))
        self.assertEqual(R.structural_findings(s, dangerous=1), ["1 dangerous accepted action(s)"])

    def test_upper_tail_exact(self):
        self.assertAlmostEqual(R.upper_tail(1, 1, 0.3), 0.3)
        self.assertAlmostEqual(R.upper_tail(2, 3, 0.5), 0.5)       # (3 + 1) / 8
        self.assertEqual(R.upper_tail(0, 5, 0.1), 1.0)
        self.assertEqual(R.upper_tail(6, 5, 0.1), 0.0)
        self.assertEqual(R.upper_tail(1, 5, 0.0), 0.0)

    def test_pooled_rates(self):
        a = R.seat_summary(seat([fact()], shots=10, moves=30))
        b = R.seat_summary(seat([], shots=10, moves=30))
        self.assertEqual(R.pooled_rates([a, b]), {"race_fire": 0.05, "race_other": 0.0, "redundant_fire": 0.0,
                                                  "redundant_other": 0.0})


class ConstantsTests(unittest.TestCase):
    def test_constants_spelled_out(self):
        self.assertEqual(dict(R.REFERENCE_RATES), {"race_fire": 0.00776733, "race_other": 6.873e-05,
                                                   "redundant_fire": 0.0, "redundant_other": 0.0})
        self.assertEqual((R.SYSTEMIC_MIN, R.REDUNDANT_MIN, R.SYSTEMIC_ALPHA, R.MIN_DENOMINATOR, R.REPEAT_ACTOR,
                          R.E_PER_GAME, R.E_PER_STUDY), (3, 2, 1e-6, 10, 3, 2, 3))
        self.assertAlmostEqual(219 / 28195, R.REFERENCE_RATES["race_fire"], places=8)
        self.assertAlmostEqual(4 / 58199, R.REFERENCE_RATES["race_other"], places=8)


if __name__ == "__main__":
    unittest.main()
