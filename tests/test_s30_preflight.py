"""Sprint 30 preflight rules (``evaluation/s30_preflight.py``) on synthetic inputs.

Covered: the independent restatement agrees with the candidate on its synthetic states and in the stand-in world, and
catches a planted wrong holder, a removed non-MOVE, two removals at one objective, a reorder, a missed trigger and a
removal outside the play stage; its free-flow sum equals the registered relation on the synthetic cost graph; one side's
analysis on a synthetic stream (first divergence, its validity in H0 and in the genuine populations, departure episodes,
onward labels, prefix before any enemy was seen); the stop rule in its order and the inert priority; the public side
summary and the sanitizer on its texts.
"""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.evaluation import s27_probe as sp
from miaosuan_agent.evaluation import s30_preflight as pf
from miaosuan_agent.experiments import t13_keep_one_k1 as k1
from tests.fixtures import s30_engine as se
from tests.test_t13_keep_one_k1 import BLUE, C, RED, city, move, raw, shoot, unit

COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")
TRAVEL = k1.router_travel(Router(COSTS))
A, B = 202, 505                       # hexes of the synthetic cost graph
ROUTE = [203, 204, 304, 405, 505]      # the router's vehicle path from A to B (asserted below)


def ground(obj, hex_=A, speed=36, **fields):
    return dict(unit(obj, hex_, tau=None, **fields), basic_speed=speed, move_state=0)


def mv(obj, route):
    return {"actor": 11, "obj_id": obj, "type": 1, "move_path": list(route)}


def state(units, cities=None, stage=2, step=10):
    return raw(units, cities if cities is not None else [city(A)], stage, step)


class IndependentCheckTest(unittest.TestCase):
    def run_both(self, observation, base):
        result = k1.decide(observation, BLUE, base, TRAVEL)
        live = [dict(a) for a in result.actions]
        return result, live, pf.independent_problems(observation, BLUE, base, live, COSTS)

    def test_agrees_with_the_candidate(self) -> None:
        cases = [([ground(1), ground(2, speed=18)], [mv(1, [203, 204]), mv(2, [203, 204])]),
                 ([ground(1), ground(2)], [mv(1, [203])]),
                 ([ground(1, path=[203], speed=1), ground(2)], [mv(2, [203])]),
                 ([ground(1, stop=0)], [mv(1, [203])]),
                 ([ground(1)], [mv(1, [203]), shoot(1)]),
                 ([ground(1, speed=None), ground(2, speed=None)], [mv(1, [203]), mv(2, [203])])]
        for units, base in cases:
            with self.subTest(units=units):
                result, live, problems = self.run_both(state(units), base)
                self.assertEqual(problems, [])
        result, _, _ = self.run_both(state(cases[0][0]), cases[0][1])
        self.assertEqual(result.checks[0].selected, 2)

    def test_free_flow_equals_the_registered_relation(self) -> None:
        for speed, route in ((36, [203, 204, 205]), (18, [203]), (7, [203, 204]), (36, [205]), (None, [203])):
            u = ground(1, speed=speed)
            self.assertEqual(pf.free_flow(COSTS, u, route), TRAVEL(u, route))

    def test_planted_defects_are_found(self) -> None:
        observation = state([ground(1), ground(2, speed=18), ground(3, B)])
        base = [mv(1, [203]), mv(2, [203]), mv(3, [506]), shoot(9)]
        wrong_holder = [base[1], base[2], base[3]]
        non_move = base[:3]
        two = [base[2], base[3]]
        reorder = [base[0], base[2], base[3]][::-1]
        missed = list(base)
        for live, needle in ((wrong_holder, "not the registered holder"), (non_move, "not a MOVE"),
                             (two, "two MOVEs removed"), (reorder, "removed in order"), (missed, "kept every MOVE")):
            with self.subTest(needle=needle):
                problems = pf.independent_problems(observation, BLUE, base, live, COSTS)
                self.assertTrue(any(needle in p for p in problems), problems)
        right = [base[0], base[2], base[3]]
        self.assertEqual(pf.independent_problems(observation, BLUE, base, right, COSTS), [])
        outside = state([ground(1), ground(2, speed=18)], stage=1)
        self.assertEqual(pf.independent_problems(outside, BLUE, base, right, COSTS),
                         ["an action was removed outside the play stage"])

    def test_the_route_is_the_routers(self) -> None:
        from miaosuan_agent.boundary import MoveMode
        self.assertEqual(list(Router(COSTS).shortest_paths(A, MoveMode.VEHICLE, frozenset()).path_to(B)), ROUTE)

    def test_removed_indices(self) -> None:
        base = [mv(1, [203]), shoot(2), mv(3, [203])]
        self.assertEqual(pf.removed_indices(base, [base[1]]), [0, 2])
        self.assertIsNone(pf.removed_indices(base, [base[2], base[1]]))
        self.assertIsNone(pf.removed_indices(base, base + [shoot(4)]))


def stream(n, *, holder_leaves_at=None, divergence_at=3, enemy_at=None, differs_at=None, lose_at=None):
    """A synthetic side: two tanks stand on the held objective A; from ``divergence_at`` baseline-v2 orders both to
    B. On the record they leave at ``holder_leaves_at``; the flag of B turns blue when tank 2 stands on it."""
    rows = []
    for k in range(n):
        units = [ground(1), ground(2, speed=18)]
        cities = [city(A), city(B, flag=-1, value=50)]
        if holder_leaves_at is not None and k >= holder_leaves_at:
            units = [ground(1, B), ground(2, B, speed=18)]
            cities[1]["flag"] = BLUE
        if lose_at is not None and k >= lose_at:
            cities[0]["flag"] = RED
        if enemy_at is not None and k >= enemy_at:
            units.append(ground(99, 909, color=RED))
        observation = raw(units, cities, step=k)
        base = [mv(1, ROUTE), mv(2, ROUTE)] if k >= divergence_at and \
            (holder_leaves_at is None or k < holder_leaves_at) else []
        recorded = copy.deepcopy(base)
        if differs_at is not None and k == differs_at:
            recorded = [shoot(5)]
        rows.append((observation, recorded, base))
    return rows


class SideTest(unittest.TestCase):
    def analyse(self, population="HH", **options):
        meta = {"population": population, "label": "synthetic", "scenario": "900000001", "condition": "H2",
                "faction": BLUE}
        return pf.analyse_side(meta, stream(12, **options), COSTS, TRAVEL)

    def test_first_divergence_and_onward_labels(self) -> None:
        summary, private = self.analyse(holder_leaves_at=6, enemy_at=8, lose_at=10)
        first = summary["first_divergence"]
        self.assertEqual((first["decision"], first["step"], first["valid"]), (3, 3, True))
        self.assertEqual((first["holder_class"], first["occupants"], first["eligible"]), ("vehicle", 2, 2))
        self.assertEqual(first["destination"], "50-point objective A")
        self.assertTrue(first["holder_first_owner_of_its_destination_on_the_record"])
        self.assertEqual(first["recorded_objective_lost_steps_after"], 7)
        self.assertEqual((first["first_enemy_seen_step"], first["prefix_before_any_enemy_was_seen"]), (8, True))
        self.assertTrue(summary["verified_opportunity"])
        self.assertEqual(summary["withholding_decisions"], 3)
        self.assertEqual(summary["post_divergence_withholding_decisions"], 2)
        self.assertIn(A, private)
        episodes = summary["departure_episodes"]
        self.assertEqual([(e["first_status"], e["length"], e["actionable"]) for e in episodes], [("withheld", 3, True)])

    def test_h0_validity_needs_a_supported_prefix(self) -> None:
        self.assertTrue(self.analyse("H0")[0]["first_divergence"]["valid"])
        self.assertTrue(self.analyse("H0", differs_at=3)[0]["first_divergence"]["valid"])
        early = self.analyse("H0", differs_at=2)[0]
        self.assertEqual((early["first_divergence"]["valid"], early["verified_opportunity"]), (False, False))
        self.assertTrue(self.analyse("HI", differs_at=2)[0]["first_divergence"]["valid"])

    def test_no_divergence(self) -> None:
        summary, _ = self.analyse(divergence_at=99)
        self.assertEqual((summary["first_divergence"], summary["verified_opportunity"]), (None, False))
        self.assertEqual(summary["outcomes"], {"holder_remains": 12})

    def test_public_summary_is_sanitised_and_aggregated(self) -> None:
        summary, private = self.analyse(holder_leaves_at=6)
        public = pf.public_side(summary)
        self.assertNotIn("private", public)
        self.assertEqual(public["departure_episodes"]["count"], 1)
        self.assertEqual(sp.public_problems(public, private, {"900000001"}), [])
        self.assertTrue(sp.public_problems({"note": "kept 3 units"}, private, {"900000001"}))


def side(population, scenario, condition, colour, verified):
    return {"population": population, "scenario": scenario, "condition": condition, "colour": colour,
            "verified_opportunity": verified, "independent_check_findings": 0}


class DispositionTest(unittest.TestCase):
    def sides(self, hi=(True, True, True), red=(True, False), blue=(False, True)):
        out = [side("HH", "2130511121", "H2", "red", v) for v in red]
        out += [side("HH", "2130511121", "H1", "blue", v) for v in blue]
        out += [side("HI", s, c, "blue", v) for (s, c), v in zip(pf.INERT_PRIORITY, hi)]
        return out

    def test_pass_and_the_inert_priority(self) -> None:
        verdict = pf.disposition(True, self.sides())
        self.assertEqual((verdict["disposition"], verdict["inert_configurations"]),
                         ("K1_PREFLIGHT_PASS", [["2120531121", "C3"], ["1930331196", "C2"]]))
        verdict = pf.disposition(True, self.sides(hi=(False, True, True)))
        self.assertEqual(verdict["inert_configurations"], [["1930331196", "C2"], ["1930331196", "C3"]])

    def test_inadequate(self) -> None:
        for options in ({"red": (False, False)}, {"blue": (False, False)}, {"hi": (True, False, False)},
                        {"red": (True,)}):
            with self.subTest(options=options):
                verdict = pf.disposition(True, self.sides(**options))
                self.assertEqual(verdict["disposition"], "K1_PREFLIGHT_INADEQUATE")
                self.assertTrue(verdict["reasons"])
                self.assertEqual(sp.digit_words(verdict["reasons"]), [])

    def test_invalid_first(self) -> None:
        self.assertEqual(pf.disposition(False, self.sides())["disposition"], "K1_PREFLIGHT_INVALID")
        broken = self.sides()
        broken[0]["independent_check_findings"] = 1
        self.assertEqual(pf.disposition(True, broken)["disposition"], "K1_PREFLIGHT_INVALID")

    def test_registered_constants(self) -> None:
        self.assertEqual(pf.INERT_PRIORITY, (("2120531121", "C3"), ("1930331196", "C2"), ("1930331196", "C3")))
        self.assertEqual(pf.ANCHORS, {"H0 decisions": 33696, "H0 play decisions": 33680,
                                      "H0 v2 differs from recorded v0": 123, "HH decisions": 11524,
                                      "HI decisions": 8643})
        self.assertEqual(pf.GENUINE, ("HH", "HI"))


if __name__ == "__main__":
    unittest.main()
