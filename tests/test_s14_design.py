"""Sprint 14 design-competition analysis (``evaluation/s14_design.py``): gate, rubric, disposition and the
independent per-decision checks. SYNTHETIC facts and observations only; every threshold is crossed at its boundary."""

from __future__ import annotations

import copy
import unittest
from typing import Any, Dict

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import Memory
from miaosuan_agent.evaluation import s14_design as sx
from miaosuan_agent.experiments import t9_redistribution as tr
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn
from tests.test_t9_redistribution import A, B, RED, SEAT, SHOT, observation, unit

GAMES = ("p01", "p02", "p03", "p04")
CELL = {"p01": "H1", "p02": "H2", "p03": "H1", "p04": "H2"}


def primary(share: Dict[str, float], first: Dict[str, int], units: int, slot: Dict[str, int], orders: int) -> Dict:
    return {"games": {g: {"first_decision_redirects": first[g], "redirected_units": units, "cell": CELL[g]} for g in GAMES},
            "seats": {s: {"share": share[s], "slot_vs_t9-v1": slot[s]} for s in ("H1", "H2")},
            "pooled": {"slot_vs_t9-v1": slot["H1"] + slot["H2"], "orders_vs_t9-v1": orders}}


def passing_facts() -> Dict[str, Any]:
    """A candidate that clears every item with room; the references are the Sprint 13 shapes."""
    t9 = primary({"H1": 0.4, "H2": 0.7}, {"p01": 14, "p02": 19, "p03": 14, "p04": 19}, 20, {"H1": 0, "H2": 0}, 0)
    v3 = primary({"H1": 0.0, "H2": 0.0}, {g: 0 for g in GAMES}, 0, {"H1": 300, "H2": 250}, 913)
    cand = primary({"H1": 0.3, "H2": 0.5}, {"p01": 10, "p02": 12, "p03": 10, "p04": 12}, 10, {"H1": 100, "H2": 100},
                   400)
    t9_adverse = {"1930331196 C3": {"first_decision_redirects_by_trajectory": {"t9-v1": 12, "baseline-v2": 12},
                                    "first_decision_redirects": 12, "early_redirects_baseline": 12},
                  "1930331196 C2": {"first_decision_redirects_by_trajectory": {"t9-v1": 7, "baseline-v2": 7},
                                    "first_decision_redirects": 7, "early_redirects_baseline": 9}}
    adverse = {"2120531121 C3": {"unreachable_places": 0, "v3_selection_not_kept": 0, "far_reservations_missed": 0,
                                 "certificate_unit_decisions": 9194, "v3_certificate_unit_decisions": 9194},
               "1930331196 C3": {"shooters_redirected": 0, "first_decision_redirects": 2, "early_redirects_baseline": 2},
               "1930331196 C2": {"shooters_redirected": 0, "first_decision_redirects": 1, "early_redirects_baseline": 1}}
    return {"candidates": {"x": {"repeat_differences": 0, "repeat_comparisons": 100, "order_differences": 0,
                                 "order_comparisons": 300, "violations": {}, "primary": cand, "adverse": adverse,
                                 "latency_ms": {"p99": 5.0, "max": 50.0}}},
            "references": {"t9-v1": {"primary": t9, "adverse": t9_adverse}, "v3": {"primary": v3, "adverse": {}}},
            "static": {"seat_local": True, "no_special_case_literal": True}}


class GateTest(unittest.TestCase):
    def failed(self, facts) -> list:
        return sx.gate("x", facts)["failed"]

    def test_the_passing_shape_passes_every_item(self) -> None:
        result = sx.gate("x", passing_facts())
        self.assertTrue(result["pass"], result["failed"])
        self.assertEqual(len(result["items"]), 15)

    def test_each_planted_defect_fails_exactly_its_item(self) -> None:
        plants = {
            "G1_deterministic": lambda f: f["candidates"]["x"].update(repeat_differences=1),
            "G3_order_invariant": lambda f: f["candidates"]["x"].update(order_differences=1),
            "G4_capacity": lambda f: f["candidates"]["x"]["violations"].update({"objective above capacity": 1}),
            "G5_unrelated_actions": lambda f: f["candidates"]["x"]["violations"].update({"ground move order changed": 1}),
            "G6_no_invented_move": lambda f: f["candidates"]["x"]["violations"].update({"invented move": 1}),
            "G7_engine_supported_moves": lambda f: f["candidates"]["x"]["violations"].update(
                {"redirect route differs from baseline-v2's candidate route": 1}),
            "G8_reachable": lambda f: f["candidates"]["x"]["violations"].update(
                {"place for a unit that cannot arrive before the end": 1}),
            "G11_2120531121_C3": lambda f: f["candidates"]["x"]["adverse"]["2120531121 C3"].update(
                far_reservations_missed=1),
            "G15_latency": lambda f: f["candidates"]["x"]["latency_ms"].update(p99=20.001),
        }
        for item, plant in plants.items():
            facts = passing_facts()
            plant(facts)
            self.assertEqual(self.failed(facts), [item], item)

    def test_static_items(self) -> None:
        facts = passing_facts()
        facts["static"]["seat_local"] = False
        self.assertEqual(self.failed(facts), ["G2_seat_local", "G13_no_future_information"])
        facts = passing_facts()
        facts["static"]["no_special_case_literal"] = False
        self.assertEqual(self.failed(facts), ["G14_no_special_case"])

    def test_restoration_boundaries(self) -> None:
        facts = passing_facts()
        facts["candidates"]["x"]["primary"]["seats"]["H1"]["share"] = 0.2  # exactly half of 0.4
        self.assertEqual(self.failed(facts), [])
        facts["candidates"]["x"]["primary"]["seats"]["H1"]["share"] = 0.1999
        self.assertEqual(self.failed(facts), ["G9_redistribution_restored"])
        facts = passing_facts()
        facts["candidates"]["x"]["primary"]["games"]["p02"]["first_decision_redirects"] = 9  # 9 / 19 < 0.5
        self.assertEqual(self.failed(facts), ["G9_redistribution_restored"])
        facts["candidates"]["x"]["primary"]["games"]["p02"]["first_decision_redirects"] = 10
        self.assertEqual(self.failed(facts), [])
        facts["candidates"]["x"]["primary"]["games"]["p03"]["redirected_units"] = 4
        self.assertEqual(self.failed(facts), [])
        facts["candidates"]["x"]["primary"]["games"]["p03"]["redirected_units"] = 3
        self.assertEqual(self.failed(facts), ["G9_redistribution_restored"])

    def test_divergence_boundaries(self) -> None:
        facts = passing_facts()
        c = facts["candidates"]["x"]["primary"]
        c["pooled"]["slot_vs_t9-v1"] = 385  # 0.70 of 550
        self.assertEqual(self.failed(facts), [])
        c["pooled"]["slot_vs_t9-v1"] = 386
        self.assertEqual(self.failed(facts), ["G10_divergence_reduced"])
        facts = passing_facts()
        facts["candidates"]["x"]["primary"]["pooled"]["orders_vs_t9-v1"] = 640  # > 0.70 of 913 = 639.1
        self.assertEqual(self.failed(facts), ["G10_divergence_reduced"])
        facts = passing_facts()
        facts["candidates"]["x"]["primary"]["seats"]["H2"]["slot_vs_t9-v1"] = 250  # not below v3's seat value
        self.assertEqual(self.failed(facts), ["G10_divergence_reduced"])

    def test_corridor_limits_use_floor_of_a_third_and_t9v1s_own_game(self) -> None:
        facts = passing_facts()
        adverse = facts["candidates"]["x"]["adverse"]
        adverse["1930331196 C3"]["first_decision_redirects"] = 4  # floor(12 / 3)
        adverse["1930331196 C2"]["first_decision_redirects"] = 2  # floor(7 / 3)
        adverse["1930331196 C2"]["early_redirects_baseline"] = 3  # floor(9 / 3)
        self.assertEqual(self.failed(facts), [])
        adverse["1930331196 C2"]["first_decision_redirects"] = 3
        self.assertEqual(self.failed(facts), ["G12_1930331196_corridors"])
        facts = passing_facts()
        facts["references"]["t9-v1"]["adverse"]["1930331196 C3"]["first_decision_redirects_by_trajectory"]["t9-v1"] = 5
        self.assertEqual(self.failed(facts), ["G12_1930331196_corridors"])  # limit 1 < 2
        facts = passing_facts()
        facts["candidates"]["x"]["adverse"]["1930331196 C3"]["shooters_redirected"] = 1
        self.assertEqual(self.failed(facts), ["G12_1930331196_corridors"])

    def test_certificate_must_not_fall_below_v3(self) -> None:
        facts = passing_facts()
        facts["candidates"]["x"]["adverse"]["2120531121 C3"]["certificate_unit_decisions"] = 9193
        self.assertEqual(self.failed(facts), ["G11_2120531121_C3"])


class RubricTest(unittest.TestCase):
    def row(self, first_c3: int, share_h1: float, prefix: float, orders: int) -> Dict[str, Any]:
        facts = passing_facts()
        facts["candidates"]["x"]["adverse"]["1930331196 C3"]["first_decision_redirects"] = first_c3
        facts["candidates"]["x"]["primary"]["seats"]["H1"]["share"] = share_h1
        gate = sx.gate("x", facts)
        self.assertTrue(gate["pass"], gate["failed"])
        return {"gate": gate, "prefix_median": prefix, "orders_vs_baseline": orders, "latency_p99": 1.0}

    def test_margin_decides_first(self) -> None:
        names = list(sx.SIMPLICITY)
        rows = {names[0]: self.row(4, 0.4, 0.9, 100), names[5]: self.row(1, 0.4, 0.1, 900)}
        self.assertEqual(sx.select(rows)["selected"], names[5])

    def test_corridor_then_change_then_simplicity(self) -> None:
        names = list(sx.SIMPLICITY)
        rows = {names[1]: self.row(1, 0.4, 0.31, 100), names[4]: self.row(1, 0.4, 0.45, 100)}
        self.assertEqual(sx.select(rows)["selected"], names[4])  # corridor band 4 beats band 3
        rows = {names[1]: self.row(1, 0.4, 0.45, 110), names[4]: self.row(1, 0.4, 0.45, 100)}
        self.assertEqual(sx.select(rows)["selected"], names[1])  # within 10%: simplicity
        rows = {names[1]: self.row(1, 0.4, 0.45, 111), names[4]: self.row(1, 0.4, 0.45, 100)}
        self.assertEqual(sx.select(rows)["selected"], names[4])

    def test_disposition(self) -> None:
        self.assertEqual(sx.disposition(["x"], {}, {})["disposition"], "REPLAY_INVALID")
        self.assertEqual(sx.disposition([], {"a": {"pass": False}}, {"selected": None})["disposition"],
                         "NO_ENGINE_CANDIDATE")
        name = sx.CANDIDATES[0]
        verdict = sx.disposition([], {name: {"pass": True}}, {"selected": name})
        self.assertEqual((verdict["disposition"], verdict["identity"]),
                         ("ENGINE_CANDIDATE_SELECTED", tr.RULES[name].identity))


class ChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        near = [unit(905000 + k, h) for k, h in enumerate((504, 506, 404, 604))]
        idle = unit(905020, 100)  # an own ground unit with no listed move: baseline-v2 leaves it alone
        self.obs = observation(near + [unit(905010, 408), unit(905011, 806), idle],
                               movable=[905000, 905001, 905002, 905003, 905010, 905011])
        self.base = list(ShootReservationPolicy(self.costs).decide(self.obs, SEAT, RED, Memory()).actions)

    def decided(self):
        return sx.decide_all(self.obs, SEAT, RED, Memory(), self.costs)

    def test_clean_decision_has_no_violation_and_reports_redirects(self) -> None:
        d = self.decided()
        self.assertTrue(d["active"])
        for name in sx.CANDIDATES:
            checks = sx.candidate_checks(self.obs, SEAT, RED, self.base, d[name], d[f"{name}_allocation"],
                                         d["v3_allocation"], self.costs)
            self.assertEqual(+checks["violations"], sx.collections.Counter(), name)
        checks = sx.candidate_checks(self.obs, SEAT, RED, self.base, d["feasible-value-redirect"],
                                     d["feasible-value-redirect_allocation"], d["v3_allocation"], self.costs)
        self.assertEqual({r["to"] for r in checks["redirects"]}, {B})
        self.assertEqual(sorted(checks["forms"].values()).count(sx.REDIRECT), 2)
        self.assertEqual(d["feasible-value-redirect"], d["O2"])

    def test_planted_defects_are_seen(self) -> None:
        d = self.decided()
        good = list(d["feasible-value-redirect"])
        allocation = d["feasible-value-redirect_allocation"]

        def check(actions):
            return +sx.candidate_checks(self.obs, SEAT, RED, self.base, actions, allocation, d["v3_allocation"],
                                        self.costs)["violations"]
        self.assertEqual(check(good), sx.collections.Counter())
        self.assertIn("unrelated action changed", check(good + [SHOT]))
        invented = dict(good[0], obj_id=905020)
        self.assertIn("invented move", check(good + [invented]))
        self.assertIn("ground move order changed", check(list(reversed(good))))
        redirected = [a for a in good if a["obj_id"] == 905010][0]
        bent = dict(redirected, move_path=list(redirected["move_path"])[:-1] + [A])
        self.assertTrue(check([bent if a is redirected else a for a in good]))
        detour = list(redirected["move_path"])
        bent_route = dict(redirected, move_path=detour[:1] + [detour[0] + 1] + detour[1:])
        self.assertIn("redirect route differs from baseline-v2's candidate route",
                      check([bent_route if a is redirected else a for a in good]))
        off_route = dict(redirected, move_path=[list(redirected["move_path"])[0]])
        self.assertIn("changed move neither a redirect nor a strict same-route prefix off objectives",
                      check([off_route if a is redirected else a for a in good]))
        crowd = [dict(a, move_path=list(self.base[i]["move_path"])) for i, a in enumerate(good)]
        self.assertIn("objective above capacity", check(crowd))

    def test_unreachable_and_late_places_are_seen(self) -> None:
        d = self.decided()
        late = observation([unit(905000 + k, h) for k, h in enumerate((504, 506, 404, 604))]
                           + [unit(905010, 408), unit(905011, 806)], cur_step=2880 - 30)
        checks = sx.candidate_checks(late, SEAT, RED, self.base, self.base, None, None, self.costs)
        self.assertGreater(checks["violations"]["place for a unit that cannot arrive before the end"], 0)
        self.assertEqual(checks["violations"]["objective above capacity"], 1)
        self.assertIsNotNone(d)

    def test_repeat_and_order_checks_compare_and_can_fail(self) -> None:
        d = self.decided()
        counts = sx.repeat_checks(self.obs, SEAT, RED, self.base, self.costs, d, "seed")
        for name in sx.CANDIDATES:
            self.assertEqual(counts[name]["repeat_differences"], 0, name)
            self.assertEqual(counts[name]["order_differences"], 0, name)
            self.assertEqual(counts[name]["order_comparisons"], 3, name)
        broken = copy.copy(d)
        alloc = copy.deepcopy(d["batch-value-redirect_allocation"])
        alloc.selected = {}
        broken["batch-value-redirect_allocation"] = alloc
        counts = sx.repeat_checks(self.obs, SEAT, RED, self.base, self.costs, broken, "seed")
        self.assertEqual(counts["batch-value-redirect"]["repeat_differences"], 1)
        self.assertEqual(counts["batch-value-redirect"]["order_differences"], 3)

    def test_forms_and_divergences(self) -> None:
        d = self.decided()
        ground = sx.own_ground(self.obs, RED)
        cities = {A, B}
        forms = sx.forms(self.base, d["v3"], ground, cities)
        self.assertEqual(sorted(forms.values()).count(sx.KEEP), 4)
        self.assertEqual(sx.slot_divergence(sx.slots(d["v3"], ground, cities), sx.slots(d["O2"], ground, cities)), 1)
        self.assertEqual(sx.order_divergence(d["v3"], d["O2"], ground), {905010, 905011})
        self.assertEqual(sx.distribution([3, 1, 2])["median"], 2)
        self.assertEqual(sx.percentile([1.0, 2.0, 3.0, 4.0], 0.99), 4.0)


if __name__ == "__main__":
    unittest.main()
