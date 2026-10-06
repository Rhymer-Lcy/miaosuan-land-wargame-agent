"""Sprint 15 analysis (``evaluation/s15_delayed.py``): the frozen gate, the adequacy rule, the rubric, the disposition,
the diagnostic rule search and the small helpers, on synthetic facts with planted threshold crossings."""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.evaluation import s15_delayed as s15
from miaosuan_agent.experiments import t9_delayed as td
from tests.fixtures import synthetic as syn

NAME = "delayed-repeat-2"


def primary(post_units=(10, 20), post_slot=(50, 100), first=(0, 0, 0, 0), recourse=1, oscillations=0):
    games = {g: {"first_decision_redirects": n} for g, n in zip(("p01", "p02", "p03", "p04"), first)}
    seats = {"H1": {"post_opening_units": post_units[0], "post_slot_vs_t9-v1": post_slot[0]},
             "H2": {"post_opening_units": post_units[1], "post_slot_vs_t9-v1": post_slot[1]}}
    return {"games": games, "seats": seats,
            "pooled": {"post_slot_vs_t9-v1": sum(post_slot), "max_redirects_per_unit_game": recourse,
                       "oscillations": oscillations}}


def adverse(shooters=(0, 0), first=(0, 0), early=(0, 0), exposure=(5, 5, 5), unreachable=0, not_kept=0, cert=9194):
    return {"1930331196 C3": {"shooters_redirected": shooters[0], "first_decision_redirects": first[0],
                              "early_redirects_baseline": early[0], "trigger_exposure_in_window": exposure[0],
                              "first_decision_redirects_own_game": 0},
            "1930331196 C2": {"shooters_redirected": shooters[1], "first_decision_redirects": first[1],
                              "early_redirects_baseline": early[1], "trigger_exposure_in_window": exposure[1],
                              "first_decision_redirects_own_game": 0},
            "2120531121 C3": {"unreachable_places": unreachable, "v3_selection_not_kept": not_kept,
                              "certificate_unit_decisions": cert, "trigger_exposure_in_window": exposure[2],
                              "first_decision_redirects": 0}}


def facts(**kw):
    candidate = {"invariants": {"repeat_comparisons": 10, "repeat_differences": 0, "order_comparisons": 30,
                                "order_differences": 0, "violations": {}, "memory_checks": 100, "memory_problems": 0},
                 "primary": primary(**kw.get("primary", {})), "adverse": adverse(**kw.get("adverse", {})),
                 "latency_ms": {"p99": 1.0, "max": 10.0}}
    references = {
        "t9-v1": {"primary": primary(post_units=(15, 26)),
                  "adverse": {"1930331196 C3": {"first_decision_redirects_own_game": 12, "early_redirects_baseline": 12},
                              "1930331196 C2": {"first_decision_redirects_own_game": 7, "early_redirects_baseline": 15}}},
        "v3": {"primary": primary(post_units=(0, 0), post_slot=(200, 300)),
               "adverse": {"2120531121 C3": {"certificate_unit_decisions": 9194}}},
        "O2": {"primary": primary(post_units=(14, 26))}}
    return {"candidates": {NAME: candidate}, "references": references,
            "static": {"seat_local": True, "no_special_case_literal": True}}


class GateTest(unittest.TestCase):
    def test_clean_facts_pass_every_item(self) -> None:
        row = s15.gate(NAME, facts())
        self.assertTrue(row["pass"], row["failed"])
        self.assertEqual(row["groups"], {"invariants": True, "restoration": True, "adverse": True})
        self.assertEqual(row["items"]["R2_post_opening_restored"]["required"], {"H1": 8, "H2": 13})

    def test_each_planted_crossing_fails_its_own_item(self) -> None:
        plants = {
            "G1_deterministic": lambda f: f["candidates"][NAME]["invariants"].update(repeat_differences=1),
            "G3_order_invariant": lambda f: f["candidates"][NAME]["invariants"].update(order_comparisons=0),
            "G4_capacity": lambda f: f["candidates"][NAME]["invariants"]["violations"].update(
                {"objective above capacity": 1}),
            "G7_engine_supported_moves": lambda f: f["candidates"][NAME]["invariants"]["violations"].update(
                {"gate rejections": 1}),
            "G8_reachable": lambda f: f["candidates"][NAME]["invariants"]["violations"].update(
                {"place for a unit that cannot arrive before the end": 1}),
            "G9_memory": lambda f: f["candidates"][NAME]["invariants"].update(memory_problems=1),
            "G12_latency": lambda f: f["candidates"][NAME]["latency_ms"].update(max=200.5),
            "R1_no_opening_redistribution": lambda f: f["candidates"][NAME]["primary"]["games"]["p03"].update(
                first_decision_redirects=1),
            "R2_post_opening_restored": lambda f: f["candidates"][NAME]["primary"]["seats"]["H1"].update(
                post_opening_units=7),
            "R3_divergence_reduced": lambda f: f["candidates"][NAME]["primary"]["seats"]["H2"].update(
                **{"post_slot_vs_t9-v1": 300}),
            "R4_bounded_recourse": lambda f: f["candidates"][NAME]["primary"]["pooled"].update(oscillations=1),
            "A1_1930331196": lambda f: f["candidates"][NAME]["adverse"]["1930331196 C3"].update(shooters_redirected=1),
            "A2_2120531121_C3": lambda f: f["candidates"][NAME]["adverse"]["2120531121 C3"].update(
                certificate_unit_decisions=9193),
        }
        for code, plant in plants.items():
            f = copy.deepcopy(facts())
            plant(f)
            row = s15.gate(NAME, f)
            self.assertFalse(row["items"][code]["pass"], code)
            self.assertFalse(row["pass"], code)

    def test_thresholds_are_inclusive_where_the_protocol_says_at_least_or_at_most(self) -> None:
        f = facts(primary={"post_units": (8, 13)})
        self.assertTrue(s15.gate(NAME, f)["items"]["R2_post_opening_restored"]["pass"])
        f = facts(primary={"post_units": (8, 12)})
        self.assertFalse(s15.gate(NAME, f)["items"]["R2_post_opening_restored"]["pass"])
        # pooled post-opening divergence at exactly 0.70 of v3's (500) passes; seats strictly below v3's
        f = facts(primary={"post_slot": (150, 200)})
        self.assertTrue(s15.gate(NAME, f)["items"]["R3_divergence_reduced"]["pass"])
        f = facts(primary={"post_slot": (151, 200)})
        self.assertFalse(s15.gate(NAME, f)["items"]["R3_divergence_reduced"]["pass"])
        f = facts(primary={"post_slot": (200, 100)})
        self.assertFalse(s15.gate(NAME, f)["items"]["R3_divergence_reduced"]["pass"])  # H1 not below v3's 200
        # adverse limits: floor(12 / 3) = 4 in C3, floor(15 / 3) = 5 early in C2
        f = facts(adverse={"early": (4, 5)})
        self.assertTrue(s15.gate(NAME, f)["items"]["A1_1930331196"]["pass"])
        f = facts(adverse={"early": (4, 6)})
        self.assertFalse(s15.gate(NAME, f)["items"]["A1_1930331196"]["pass"])
        # recourse: at most three redirects of one unit in one game
        self.assertTrue(s15.gate(NAME, facts(primary={"recourse": 3}))["items"]["R4_bounded_recourse"]["pass"])
        self.assertFalse(s15.gate(NAME, facts(primary={"recourse": 4}))["items"]["R4_bounded_recourse"]["pass"])

    def test_adequacy_marks_untested_configurations(self) -> None:
        self.assertTrue(s15.adequacy(NAME, facts())["all_tested"])
        row = s15.adequacy(NAME, facts(adverse={"exposure": (0, 5, 5)}))
        self.assertFalse(row["all_tested"])
        self.assertEqual(row["configurations"]["1930331196 C3"]["status"], "UNTESTED")
        self.assertEqual(row["configurations"]["1930331196 C2"]["status"], "TESTED")

    def test_disposition_order(self) -> None:
        good = s15.gate(NAME, facts())
        tested = s15.adequacy(NAME, facts())
        untested = s15.adequacy(NAME, facts(adverse={"exposure": (5, 0, 5)}))
        opportunity = {"H1": {"o2_post_opening_units": 14, "required": 8},
                       "H2": {"o2_post_opening_units": 26, "required": 13}}
        selection = s15.select({NAME: {"gate": good, "post_slot": 150, "redirects": 20, "latency_p99": 1.0}})
        self.assertEqual(s15.disposition(["x"], {NAME: good}, {NAME: tested}, opportunity, selection)["disposition"],
                         "REPLAY_INVALID")
        short = {"H1": {"o2_post_opening_units": 7, "required": 8}, "H2": opportunity["H2"]}
        self.assertEqual(s15.disposition([], {NAME: good}, {NAME: tested}, short, selection)["disposition"],
                         "NO_DELAYED_REDISTRIBUTION_OPPORTUNITY")
        self.assertEqual(s15.disposition([], {NAME: good}, {NAME: tested}, opportunity, selection)["disposition"],
                         "OFFLINE_CANDIDATE_SELECTED")
        verdict = s15.disposition([], {NAME: good}, {NAME: untested}, opportunity, {"selected": None})
        self.assertEqual(verdict["disposition"], "MECHANISM_AMBIGUOUS")
        self.assertEqual(verdict["untested"], {NAME: ["1930331196 C2"]})
        unsafe = s15.gate(NAME, facts(adverse={"shooters": (1, 0)}))
        self.assertEqual(s15.disposition([], {NAME: unsafe}, {NAME: tested}, opportunity, {"selected": None})
                         ["disposition"], "NO_STATE_DISCRIMINATOR")
        weak = s15.gate(NAME, facts(primary={"post_units": (3, 3)}))
        self.assertEqual(s15.disposition([], {NAME: weak}, {NAME: tested}, opportunity, {"selected": None})
                         ["disposition"], "NO_RESTORING_TRIGGER")
        self.assertEqual(set(s15.DISPOSITIONS), {"REPLAY_INVALID", "NO_DELAYED_REDISTRIBUTION_OPPORTUNITY",
                                                 "OFFLINE_CANDIDATE_SELECTED", "MECHANISM_AMBIGUOUS",
                                                 "NO_STATE_DISCRIMINATOR", "NO_RESTORING_TRIGGER"})

    def test_rubric_prefers_margin_then_divergence_then_recourse_then_simplicity(self) -> None:
        names = list(td.RULES)
        gates = {n: s15.gate(NAME, facts()) for n in names[:3]}
        rows = {n: {"gate": gates[n], "post_slot": 150, "redirects": 20, "latency_p99": 1.0} for n in names[:3]}
        self.assertEqual(s15.select(rows)["selected"], names[0])  # full tie: the simplest
        rows[names[0]]["redirects"] = 40
        self.assertEqual(s15.select(rows)["selected"], names[1])  # more recourse loses
        better = s15.gate(NAME, facts(primary={"post_units": (16, 26)}))
        rows[names[2]]["gate"] = better
        self.assertEqual(s15.select(rows)["selected"], names[2])  # a wider restoration margin wins first
        self.assertEqual(s15.select({})["selected"], None)
        margins = s15.margins(better)
        self.assertAlmostEqual(margins["restore"], min(16 / 8, 26 / 13) - 1.0)
        self.assertEqual(margins["adverse"], 1.0)

    def test_frozen_thresholds_and_windows(self) -> None:
        self.assertEqual(s15.GATE, {"restore_units_ratio_min": 0.5, "restore_units_min": 4, "divergence_ratio_max": 0.70,
                                    "adverse_first_divisor": 3, "adverse_early_divisor": 3, "recourse_max": 3,
                                    "latency_p99_ms_max": 20.0, "latency_max_ms_max": 200.0, "rubric_band": 0.05,
                                    "rubric_tolerance": 0.10})
        self.assertEqual(s15.RISK_WINDOW, {"1930331196 C3": 876, "1930331196 C2": 611, "2120531121 C3": 564})
        self.assertEqual(s15.CANDIDATES, tuple(td.RULES))


class HelperTest(unittest.TestCase):
    def test_buckets(self) -> None:
        self.assertEqual([s15.bucket(n) for n in (1, 2, 6, 7, 26, 27, 999)],
                         ["first", "next5", "next5", "next20", "next20", "later", "later"])

    def test_oscillations_count_only_back_and_forth(self) -> None:
        self.assertEqual(s15.oscillations([(1, 7, 10, 20), (5, 7, 20, 10)]), 1)
        self.assertEqual(s15.oscillations([(1, 7, 10, 20), (5, 7, 20, 30)]), 0)
        self.assertEqual(s15.oscillations([(1, 7, 10, 20), (5, 8, 20, 10)]), 0)  # another unit
        self.assertEqual(s15.oscillations([(5, 7, 20, 10), (1, 7, 10, 20)]), 1)  # decision order, not list order

    def test_memory_problems(self) -> None:
        raw = syn.build_observation(units=[syn.unit(41, 0, 505)], valid_actions={}, stage=2, cur_step=10,
                                    seats={1: syn.seat_record(1, 0, [41], True)}, cities=[syn.city(505)])
        obs = Observation.from_raw(raw, Origin.ENGINE)
        good = td.encode({41: [505, 1, 0, 0, 0, 0, 0, 3, 0]})
        self.assertEqual(s15.memory_problems(obs, 0, good), [])
        self.assertTrue(s15.memory_problems(obs, 0, td.encode({42: [505, 1, 0, 0, 0, 0, 0, 3, 0]})))
        self.assertTrue(s15.memory_problems(obs, 0, td.encode({41: [505, 1, 0, 2, 0, 0, 0, 3, 0]})))
        self.assertTrue(s15.memory_problems(obs, 0, ((41 * td.FIELDS + 15, 1),)))
        self.assertTrue(s15.memory_problems(obs, 0, td.encode({41: [505, td.COUNT_CAP + 1, 0, 0, 0, 0, 0, 3, 0]})))

    def test_rule_search_finds_a_separating_conjunction_and_reports_leave_one_out(self) -> None:
        rows = ([{"a": 1, "b": 5, "label": "PRIMARY", "group": "P1"} for _ in range(4)]
                + [{"a": 1, "b": 1, "label": "ADVERSE", "group": "A1"} for _ in range(3)]
                + [{"a": 0, "b": 5, "label": "ADVERSE", "group": "A2"} for _ in range(2)]
                + [{"a": 1, "b": 5, "label": "PRIMARY", "group": "P2"} for _ in range(2)]
                + [{"a": 9, "b": 9, "label": "UNLABELLED", "group": "U"}])
        out = s15.rule_search(rows, ("a", "b"))
        best = out["all"]
        self.assertEqual(best["rule"], [["a", ">=", 1], ["b", ">=", 5]])  # no single predicate separates both
        self.assertEqual((best["adverse_allowed"], best["primary_allowed"]), (0, 6))
        self.assertEqual(best["primary_rows"], 6)
        self.assertEqual(best["adverse_rows"], 5)  # the unlabelled row is not scored
        self.assertEqual(set(out["leave_one_group_out"]), {"A1", "A2", "P1", "P2"})
        held = out["leave_one_group_out"]["A2"]
        self.assertEqual(held["held_out_rows"], 2)
        # fitted without A2, the single predicate on b separates A1 and lets both A2 rows through
        self.assertEqual(held["rule"], [["b", ">=", 5]])
        self.assertEqual((held["held_out_adverse_allowed"], held["held_out_primary_allowed"]), (2, 0))
        self.assertEqual(out["leave_one_group_out"]["P2"]["held_out_primary_allowed"], 2)
        scored = s15.score([("b", ">=", 5)], rows)
        self.assertEqual(scored, (2, 6, 1))


if __name__ == "__main__":
    unittest.main()
