"""Sprint 31 preflight rules (``evaluation/s31_preflight.py``) on synthetic inputs.

Covered: K2's restated holder test agrees with the candidate's eligibility on settled, settling and ambiguous units;
the K2 independent check agrees with the candidate, catches a wrong holder and a missed settling trigger, and differs
from Sprint 30's K1 check exactly where K1 would not withhold; the scoped swap restores Sprint 30's module names exactly,
also after an error, and refuses unknown names; Sprint 30's frozen analysis run with the K2 rule finds a valid first
divergence on a synthetic stream where the K1 rule finds none; the stop rule in its order, with the pilot's two fixed
inert configurations; and the registered constants.
"""

from __future__ import annotations

import copy
import itertools
import unittest

from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.evaluation import s27_probe as sp
from miaosuan_agent.evaluation import s30_preflight as pf
from miaosuan_agent.evaluation import s31_preflight as kp
from miaosuan_agent.experiments import t13_keep_one_k2 as k2
from tests.fixtures import s31_engine as se
from tests.test_t13_keep_one_k1 import BLUE, RED, city, raw, shoot, unit

COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")
TRAVEL = k2.router_travel(Router(COSTS))
A, B = 202, 505
ROUTE = [203, 204, 304, 405, 505]


def ground(obj, hex_=A, speed=36, settle=None, path=(), **fields):
    """A tank on ``hex_``; ``settle`` puts it in the documented stop transition; ``fields`` are applied last."""
    u = dict(unit(obj, hex_, tau=None, path=path), basic_speed=speed, move_state=0, flag_force_stop=0)
    if settle is not None:
        u.update(stop=0, move_to_stop_remain_time=settle)
    u.update(fields)
    return u


def mv(obj, route=ROUTE):
    return {"actor": 11, "obj_id": obj, "type": 1, "move_path": list(route)}


class HolderTest(unittest.TestCase):
    def test_restatement_agrees_with_the_candidate(self) -> None:
        variants = [{}, {"settle": 74}, {"settle": 75}, {"settle": 76}, {"settle": 1}, {"settle": 0},
                    {"settle": 40, "flag_force_stop": 1}, {"settle": 40, "speed_field": 1},
                    {"settle": 40, "stop": False}, {"settle": "40", "stop": 0}, {"settle": 40, "get_on_remain_time": -1},
                    {"settle": 40, "change_state_remain_time": 1}, {"settle": 40, "get_on_remain_time": 1},
                    {"stop": 0}, {"move_to_stop_remain_time": 30}, {"change_state_remain_time": 2},
                    {"get_off_remain_time": 2}, {"path": [203]}, {"settle": 40, "drop": "flag_force_stop"},
                    {"settle": 40, "drop": "speed"}, {"drop": "stop"}]
        for v in variants:
            with self.subTest(v=v):
                v = dict(v)
                drop = v.pop("drop", None)
                speed_field = v.pop("speed_field", None)
                u = ground(1, **v)
                if speed_field is not None:
                    u["speed"] = speed_field
                if drop:
                    del u[drop]
                acts = [mv(1)]
                mine = k2.eligibility(u, [(0, acts[0])], A) == k2.ELIGIBLE
                self.assertEqual(kp.holder_ok(u, acts, A), mine)
        self.assertTrue(kp.holder_ok(ground(1, settle=74), [mv(1)], A))
        self.assertFalse(pf.holder_ok(ground(1, settle=74), [mv(1)], A))


class IndependentTest(unittest.TestCase):
    def state(self, units):
        return raw(units, [city(A)], 2, 10)

    def test_agrees_and_catches_planted_defects(self) -> None:
        observation = self.state([ground(1, settle=74), ground(2, speed=18, settle=74)])
        base = [mv(1), mv(2), shoot(9)]
        result = k2.decide(observation, BLUE, base, TRAVEL)
        live = [dict(a) for a in result.actions]
        self.assertEqual((result.checks[0].selected, live), (2, [base[0], base[2]]))
        self.assertEqual(kp.independent_problems(observation, BLUE, base, live, COSTS), [])
        self.assertTrue(any("registered holder" in p for p in
                            kp.independent_problems(observation, BLUE, base, [base[1], base[2]], COSTS)))
        self.assertTrue(any("kept every MOVE" in p for p in kp.independent_problems(observation, BLUE, base, base, COSTS)))
        # Sprint 30's K1 check does not explain the K2 withholding of a settling holder
        self.assertTrue(pf.independent_problems(observation, BLUE, base, live, COSTS))
        ambiguous = self.state([ground(1, settle=74, flag_force_stop=1), ground(2, speed=18, settle=74,
                                                                               flag_force_stop=1)])
        self.assertEqual(kp.independent_problems(ambiguous, BLUE, base, base, COSTS), [])

    def test_the_k1_holder_test_is_restored(self) -> None:
        before = (pf.holder_ok, pf.independent_problems, pf.k1)
        kp.independent_problems(self.state([ground(1, settle=74)]), BLUE, [mv(1)], [], COSTS)
        self.assertEqual((pf.holder_ok, pf.independent_problems, pf.k1), before)


class SwapTest(unittest.TestCase):
    def test_names_are_restored_after_an_error(self) -> None:
        before = (pf.k1, pf.independent_problems)
        with self.assertRaises(RuntimeError):
            with kp.k2_rules():
                self.assertIs(pf.k1, k2)
                self.assertIs(pf.independent_problems, kp.independent_problems)
                raise RuntimeError("planted")
        self.assertEqual((pf.k1, pf.independent_problems), before)
        with self.assertRaises(AttributeError):
            with kp.swapped(pf, not_a_name=1):
                pass
        self.assertFalse(hasattr(pf, "not_a_name"))


def stream(n=10, capture=3):
    """Two settling tanks on A; A turns blue at ``capture`` and baseline-v2 orders both on to B from then on."""
    rows = []
    for k in range(n):
        held = k >= capture
        units = [ground(1, settle=max(1, 74 - k)), ground(2, speed=18, settle=max(1, 74 - k))]
        observation = raw(units, [city(A, flag=BLUE if held else -1), city(B, flag=-1, value=50)], step=k)
        base = [mv(1), mv(2)] if held else []
        rows.append((observation, copy.deepcopy(base), base))
    return rows


class AnalysisTest(unittest.TestCase):
    meta = {"population": "HH", "label": "synthetic", "scenario": "900000001", "condition": "H2", "faction": BLUE}

    def test_k2_diverges_where_k1_does_not(self) -> None:
        before = (pf.k1, pf.independent_problems)
        summary, _ = kp.analyse_side(self.meta, stream(), COSTS, TRAVEL)
        self.assertEqual((pf.k1, pf.independent_problems), before)
        first = summary["first_divergence"]
        self.assertEqual((first["decision"], first["valid"], summary["verified_opportunity"]), (3, True, True))
        self.assertEqual((first["holder_class"], first["eligible"], summary["independent_check_findings"]),
                         ("vehicle", 2, 0))
        k1_summary, _ = pf.analyse_side(self.meta, stream(), COSTS, TRAVEL)
        self.assertIsNone(k1_summary["first_divergence"])
        self.assertEqual(k1_summary["outcomes"].get("no_eligible_holder"), 7)


def side(population, scenario, condition, colour, verified, findings=0):
    return {"population": population, "scenario": scenario, "condition": condition, "colour": colour,
            "verified_opportunity": verified, "independent_check_findings": findings}


class DispositionTest(unittest.TestCase):
    def sides(self, red=(True, False), blue=(False, True), hi=(True, True, True)):
        out = [side("HH", "2130511121", "H2", "red", v) for v in red]
        out += [side("HH", "2130511121", "H1", "blue", v) for v in blue]
        configs = (("2120531121", "C3", "blue"), ("1930331196", "C2", "red"), ("1930331196", "C3", "blue"))
        out += [side("HI", s, c, colour, v) for (s, c, colour), v in zip(configs, hi)]
        return out

    def test_pass(self) -> None:
        self.assertEqual(kp.disposition(True, self.sides()), {"disposition": "K2_PREFLIGHT_PASS", "reasons": []})
        self.assertEqual(kp.disposition(True, self.sides(hi=(True, True, False)))["disposition"], "K2_PREFLIGHT_PASS")

    def test_inadequate(self) -> None:
        for options in ({"red": (False, False)}, {"blue": (False, False)}, {"hi": (False, True, True)},
                        {"hi": (True, False, True)}, {"red": (True,)}):
            with self.subTest(options=options):
                verdict = kp.disposition(True, self.sides(**options))
                self.assertEqual(verdict["disposition"], "K2_PREFLIGHT_INADEQUATE")
                self.assertTrue(verdict["reasons"])
                self.assertEqual(sp.digit_words(verdict["reasons"], ("2120531121", "1930331196")), [])

    def test_invalid_first(self) -> None:
        self.assertEqual(kp.disposition(False, self.sides())["disposition"], "K2_PREFLIGHT_INVALID")
        broken = self.sides(red=(False, False))
        broken[2]["independent_check_findings"] = 1
        self.assertEqual(kp.disposition(True, broken)["disposition"], "K2_PREFLIGHT_INVALID")

    def test_registered_constants(self) -> None:
        self.assertEqual(kp.PILOT_INERT, (("2120531121", "C3"), ("1930331196", "C2")))
        self.assertEqual(kp.ANCHORS, pf.ANCHORS)
        self.assertEqual((kp.SETTLE_LIMIT, kp.SETTLE_NAMES), (k2.SETTLE_STEPS, k2.SETTLE_FIELDS))
        self.assertEqual(kp.DISPOSITIONS, ("K2_PREFLIGHT_INVALID", "K2_PREFLIGHT_INADEQUATE", "K2_PREFLIGHT_PASS"))


if __name__ == "__main__":
    unittest.main()
