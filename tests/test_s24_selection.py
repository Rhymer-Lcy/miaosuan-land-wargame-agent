"""Sprint 24 frozen selection rule: the registered numbers, computed criteria and caps, eligibility, the tie band and its
cost-aware order, the 27 variants, the judgement perturbations, the evidence checker and the committed files."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s24_selection as sel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s24-tactical-frontier-reselection"
RUBRIC = json.loads((OUT / "rubric.json").read_text(encoding="utf-8"))
S18 = json.loads((ROOT / "evaluation" / "s18-frontier-reset" / "rubric.json").read_text(encoding="utf-8"))


def load_script():
    spec = importlib.util.spec_from_file_location("s24_select_script", ROOT / "scripts" / "s24_select.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cand(family="A", next_sessions=0, follow_sessions=2, engineering=1, interaction=1, **scores):
    """W of the default scores is 4.10: G5 L3 O5 I3 M4 R5 P4 (E3, C3)."""
    base = {"G": 5, "L": 3, "O": 5, "I": 3, "M": 4, "R": 5, "P": 4, "E": 3, "C": 3}
    base.update(scores)
    return {"family": family, "scores": base, "next_sessions": next_sessions, "follow_sessions": follow_sessions,
            "engineering": engineering, "interaction": interaction, "next_offline": True, "conflict_measured": True,
            "repairs": [], "depends_on_unidentified": False, "uses_stopped_data": False, "admitted": True}


def table(*cands):
    return {c["family"]: c for c in cands}


class RubricTest(unittest.TestCase):
    def test_registered_numbers(self) -> None:
        self.assertEqual(RUBRIC["weights"], {"G": 0.20, "L": 0.25, "O": 0.15, "I": 0.10, "M": 0.10, "R": 0.10, "P": 0.10})
        self.assertEqual(RUBRIC["weights"], S18["weights"])
        self.assertEqual((RUBRIC["tie_band"], RUBRIC["robust_min_first"], RUBRIC["variant_count"]), (0.15, 19, 27))
        self.assertEqual(RUBRIC["perturbation"]["max_flip_share"], "1/3")
        el = RUBRIC["eligibility"]
        self.assertEqual(el["min"], {"O": 3, "M": 3, "R": 2, "E": 2})
        self.assertEqual(el["excluded_families"], ["T1", "T1-r", "PS-1", "T4", "T9"])
        self.assertEqual((el["max_next_sessions"], el["max_follow_sessions"], el["max_engineering"],
                          el["interaction_offline_from"]), (4, 4, 3, 2))
        self.assertIn("T2-X1 multi-pair transport", el["closed_increments"])
        self.assertIn("T6-G threat-entry gate", el["closed_increments"])
        self.assertIn("T11-O1 kill-first rule", el["closed_increments"])
        self.assertEqual(RUBRIC["criteria"]["P"]["basis_penalty"], {"TRIGGER": 0, "STAKE": 1, "CAPABILITY": 1})
        self.assertEqual(RUBRIC["leverage_cap"]["max_without_registered_stake"], 3)
        self.assertEqual(RUBRIC["outcomes"], list(sel.OUTCOMES))
        self.assertIsNone(RUBRIC["scores"])

    def test_anchors_are_sprint_18s(self) -> None:
        for c in sel.CRITERIA:
            self.assertEqual(RUBRIC["criteria"][c]["anchors"], S18["criteria"][c]["anchors"], c)
        self.assertEqual(RUBRIC["secondary"]["E"]["anchors"], S18["secondary"]["E"]["anchors"])
        self.assertEqual(RUBRIC["criteria"]["G"]["thresholds"], S18["criteria"]["G"]["thresholds"])
        self.assertEqual(RUBRIC["criteria"]["P"]["thresholds"], S18["criteria"]["P"]["thresholds"])

    def test_variants(self) -> None:
        v = sel.variants(RUBRIC["weights"])
        self.assertEqual(len(v), RUBRIC["variant_count"])
        for name, w in v.items():
            self.assertAlmostEqual(sum(w.values()), 1.0, msg=name)
        self.assertAlmostEqual(v["leverage 0.40"]["L"], 0.40)
        self.assertAlmostEqual(v["without P"]["P"], 0.0)
        self.assertAlmostEqual(v["C as a criterion at 0.20"]["C"], 0.20)
        self.assertAlmostEqual(v["C as a criterion at 0.10"]["G"], 0.18)
        self.assertAlmostEqual(v["E as a criterion at 0.10"]["E"], 0.10)
        self.assertNotIn("C", v["E as a criterion at 0.20"])
        self.assertAlmostEqual(v["O +0.05"]["O"], 0.20)


class ComputedTest(unittest.TestCase):
    def test_levels_and_basis_penalty(self) -> None:
        p = RUBRIC["criteria"]["P"]
        shares = [x / 16 for x in (16, 15, 12, 11, 8, 7, 4, 3, 1, 0)]
        self.assertEqual([sel.level(s, p["thresholds"]) for s in shares], [5, 4, 4, 3, 3, 2, 2, 1, 1, 0])
        pen = p["basis_penalty"]
        self.assertEqual([sel.basis_level(s, p["thresholds"], "TRIGGER", pen) for s in shares],
                         [5, 4, 4, 3, 3, 2, 2, 1, 1, 0])
        self.assertEqual([sel.basis_level(s, p["thresholds"], "STAKE", pen) for s in shares],
                         [4, 3, 3, 2, 2, 1, 1, 0, 0, 0])
        self.assertEqual(sel.basis_level(7 / 16, p["thresholds"], "CAPABILITY", pen), 1)
        with self.assertRaises(ValueError):
            sel.basis_level(0.5, p["thresholds"], "GUESS", pen)
        g = RUBRIC["criteria"]["G"]["thresholds"]
        self.assertEqual([sel.level(x / 50, g) for x in (50, 45, 44, 38, 37, 25, 24, 13, 12, 1, 0)],
                         [5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 0])

    def test_leverage_cap(self) -> None:
        rule = RUBRIC["leverage_cap"]
        strong = {"level": "REGISTERED RESULT", "scenario_sides": 7}
        self.assertEqual(sel.leverage_cap([strong], rule), 5)
        self.assertEqual(sel.leverage_cap([{"level": "REGISTERED RESULT", "scenario_sides": 2}], rule), 5)
        self.assertEqual(sel.leverage_cap([{"level": "REGISTERED RESULT", "scenario_sides": 1}], rule), 3)
        self.assertEqual(sel.leverage_cap([{"level": "REGISTERED RESULT", "scenario_sides": None}], rule), 3)
        self.assertEqual(sel.leverage_cap([{"level": "POST-HOC DIAGNOSTIC", "scenario_sides": 10}], rule), 3)
        self.assertEqual(sel.leverage_cap([{"level": "HYPOTHESIS", "scenario_sides": 16}], rule), 3)
        self.assertEqual(sel.leverage_cap([{"level": "HYPOTHESIS", "scenario_sides": 16}, strong], rule), 5)
        self.assertEqual(sel.leverage_cap([{"level": "OFFLINE ACTION COUNTERFACTUAL", "scenario_sides": 2}], rule), 5)

    def test_cost_economy(self) -> None:
        self.assertEqual(sel.cost_economy(0, 0, 0), 5)
        self.assertEqual(sel.cost_economy(0, 2, 1), 3)
        self.assertEqual(sel.cost_economy(0, 2, 2), 2)
        self.assertEqual(sel.cost_economy(2, 0, 3), 1)
        self.assertEqual(sel.cost_economy(3, 4, 3), 0)


class EligibilityTest(unittest.TestCase):
    def reasons(self, **changes):
        c = cand()
        scores = changes.pop("scores", {})
        c.update(changes)
        c["scores"].update(scores)
        return sel.ineligibility(c, RUBRIC)

    def test_each_rule(self) -> None:
        self.assertEqual(self.reasons(), [])
        self.assertEqual(self.reasons(family="T9"), ["excluded family"])
        self.assertEqual(self.reasons(family="PS-1"), ["excluded family"])
        self.assertEqual(self.reasons(admitted=False), ["not admitted"])
        self.assertEqual(self.reasons(repairs=["T2-X1 multi-pair transport"]), ["repairs or restates a closed increment"])
        self.assertEqual(self.reasons(depends_on_unidentified=True), ["endpoint depends on unidentified semantics"])
        self.assertEqual(self.reasons(uses_stopped_data=True), ["uses stopped or withheld data"])
        self.assertEqual(self.reasons(scores={"O": 2}), ["O below 3"])
        self.assertEqual(self.reasons(scores={"M": 2}), ["M below 3"])
        self.assertEqual(self.reasons(scores={"R": 1}), ["R below 2"])
        self.assertEqual(self.reasons(scores={"E": 1}), ["E below 2"])
        self.assertEqual(self.reasons(scores={"O": 3, "M": 3, "R": 2, "E": 2}), [])
        self.assertEqual(self.reasons(next_sessions=5), ["next experiment needs too many engine sessions"])
        self.assertEqual(self.reasons(next_sessions=4), [])
        self.assertEqual(self.reasons(follow_sessions=5), ["the engine step it leads to needs too many sessions"])
        self.assertEqual(self.reasons(follow_sessions=4), [])
        self.assertEqual(self.reasons(engineering=4), ["engineering class too high"])
        self.assertEqual(self.reasons(engineering=3), [])

    def test_interaction_rule(self) -> None:
        self.assertEqual(self.reasons(interaction=2), [])
        why = ["withholding interaction without an offline conflict measure first"]
        self.assertEqual(self.reasons(interaction=2, next_offline=False), why)
        self.assertEqual(self.reasons(interaction=2, conflict_measured=False), why)
        self.assertEqual(self.reasons(interaction=1, next_offline=False, conflict_measured=False), [])


class SelectTest(unittest.TestCase):
    def test_clear_winner_and_full_robustness(self) -> None:
        r = sel.select(table(cand("A", L=5), cand("B")), RUBRIC)          # W 4.60 against 4.10
        self.assertEqual((r["outcome"], r["selected"], r["runner_up"], r["margin_over_runner_up"], r["stage"]),
                         ("NEXT_INCREMENT_SELECTED", "A", "B", 0.5, "robust"))
        self.assertEqual((r["selected_first_in"], r["variants_total"]), (27, 27))
        # A: L-1, O-1, I+-1, M+-1, R-1, E+-1 (9); B: every criterion except O+1 and R+1 (10); none flips
        self.assertEqual((r["perturbations_total"], r["perturbation_flips"]), (19, 0))

    def test_band_and_e_with_the_perturbation_tie(self) -> None:
        # M differs by one point (0.10), inside the band: the lower-W candidate B wins on E in every variant, but
        # 7 of its 19 single-point perturbations (B L-1, O-1, I-1, M-1, R-1; A L+1, I+1) move the winner: > 1/3
        r = sel.select(table(cand("A", M=5, E=2), cand("B", E=4)), RUBRIC)
        self.assertEqual((r["band"], r["selected_first_in"]), (["A", "B"], 27))
        self.assertEqual((r["perturbations_total"], r["perturbation_flips"], r["perturbation_flip_share"]), (19, 7, "7/19"))
        self.assertEqual((r["outcome"], r["tied"], r["stage"]), ("FRONTIER_TIE", ["A", "B"], "perturbation"))

    def test_band_edges(self) -> None:
        # G differs by one point: 0.20, outside the band, so W decides although B has the higher E; but 9 of the 19
        # perturbations move the winner (A L-1, O-1, I-1, M-1, R-1, E-1; B L+1, I+1, M+1), more than 1/3: a tie
        r = sel.select(table(cand("A", E=2), cand("B", G=4, E=5)), RUBRIC)
        self.assertEqual((r["band"], r["selected_first_in"] >= 19), (["A"], True))
        self.assertEqual((r["perturbation_flip_share"], r["outcome"], r["tied"]), ("9/19", "FRONTIER_TIE", ["A", "B"]))
        # O differs by one point: exactly 0.15, inside the main band; B wins on E but is first in fewer than 19
        # of the 27 variants, so the robustness rule makes it a tie with A
        r = sel.select(table(cand("A", E=2), cand("B", O=4, E=4)), RUBRIC)
        self.assertEqual(r["band"], ["A", "B"])
        self.assertLess(r["selected_first_in"], 19)
        self.assertEqual((r["outcome"], r["tied"], r["stage"], r["most_frequent_other_first"]),
                         ("FRONTIER_TIE", ["A", "B"], "variants", "A"))

    def test_sessions_then_engineering_break_the_band(self) -> None:
        # equal scores and E: fewer sessions to the mechanism answer wins; 4 of 20 perturbations flip (A L-1, A E-1,
        # B L+1, B E+1), within 1/3
        r = sel.select(table(cand("A"), cand("B", next_sessions=2)), RUBRIC)
        self.assertEqual((r["outcome"], r["selected"], r["perturbation_flips"], r["perturbations_total"]),
                         ("NEXT_INCREMENT_SELECTED", "A", 4, 20))
        self.assertEqual(r["margin_over_runner_up"], 0.0)
        # equal scores, E and sessions: the lower engineering class wins
        r = sel.select(table(cand("A", engineering=3), cand("B", engineering=2)), RUBRIC)
        self.assertEqual((r["outcome"], r["selected"]), ("NEXT_INCREMENT_SELECTED", "B"))
        # equal on E, sessions and K: a tie at the main stage
        r = sel.select(table(cand("A"), cand("B"), cand("C", L=1)), RUBRIC)
        self.assertEqual((r["outcome"], r["tied"], r["stage"], r["selected"]), ("FRONTIER_TIE", ["A", "B"], "main", None))

    def test_eligibility_enters_before_the_ranking(self) -> None:
        r = sel.select(table(cand("A", L=5, E=1), cand("B")), RUBRIC)
        self.assertEqual((r["selected"], r["ineligible"]), ("B", {"A": ["E below 2"]}))
        self.assertIsNone(r["runner_up"])
        self.assertEqual(r["perturbations_total"], 10)
        r = sel.select(table(cand("A", O=2), cand("T4")), RUBRIC)
        self.assertEqual((r["outcome"], r["selected"], r["eligible"]), ("NO_READY_INCREMENT", None, []))

    def test_band_edge_is_inclusive(self) -> None:
        # weights 0.5 and 0.5 make the difference exactly representable: one G point is exactly the band
        rubric = copy.deepcopy(RUBRIC)
        rubric["weights"] = {"G": 0.5, "L": 0.5}
        rubric["tie_band"] = 0.5
        r = sel.main_rule(table(cand("A"), cand("B", G=4, E=4)), rubric)
        self.assertEqual((r["band"], r["winner"]), (["A", "B"], "B"))

    def test_robustness_threshold_edges(self) -> None:
        # found by local/diagnostics/s24/find_boundaries.py: 18 of 27 variant firsts is a tie, 19 passes to the
        # perturbation stage (which this table then fails, 9 of 21)
        r = sel.select(table(cand("A"), cand("B", G=4, I=2, M=5, E=4, C=5)), RUBRIC)
        self.assertEqual((r["selected_first_in"], r["outcome"], r["stage"]), (18, "FRONTIER_TIE", "variants"))
        r = sel.select(table(cand("A"), cand("B", G=4, L=4, O=4, I=2, E=3, C=5)), RUBRIC)
        self.assertEqual((r["selected_first_in"], r["stage"], r["perturbation_flip_share"]), (19, "perturbation", "9/21"))

    def test_challenger_is_the_most_frequent_other_first(self) -> None:
        r = sel.select(table(cand("A"), cand("B", G=4, L=2, O=4, E=5, C=1),
                             cand("C", L=4, O=4, I=4, M=5, P=3, E=2, C=5)), RUBRIC)
        firsts = sorted(r["variants"].values())
        self.assertEqual((firsts.count("A"), firsts.count("B"), firsts.count("C")), (8, 1, 18))
        self.assertEqual((r["most_frequent_other_first"], r["tied"], r["stage"]), ("A", ["A", "C"], "variants"))

    def test_flip_share_of_exactly_one_third_passes(self) -> None:
        r = sel.select(table(cand("A", L=2, I=2, M=5, E=4, P=3), cand("B", I=2, M=3, E=5, P=2)), RUBRIC)
        self.assertEqual((r["perturbation_flip_share"], r["outcome"], r["selected"]), ("6/18", "NEXT_INCREMENT_SELECTED", "B"))

    def test_capped_leverage_is_not_perturbed_above_its_cap(self) -> None:
        free = sel.select(table(cand("A", L=5), cand("B")), RUBRIC)
        capped = sel.select(table(cand("A", L=5), cand("B")), RUBRIC, caps={"B": 3})
        self.assertEqual(capped["perturbations_total"], free["perturbations_total"] - 1)
        self.assertNotIn(("B", "L", 1), {(p["candidate"], p["criterion"], p["step"]) for p in capped["perturbations"]})

    def test_scores_must_be_integers(self) -> None:
        bad = cand("A")
        bad["scores"]["L"] = 3.5
        with self.assertRaises(ValueError):
            sel.select(table(bad, cand("B")), RUBRIC)
        missing = cand("A")
        del missing["scores"]["C"]
        with self.assertRaises(ValueError):
            sel.select(table(missing, cand("B")), RUBRIC)


class EvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = load_script()
        self.ok = {
            "k": {"claim": "held objectives lost in H0", "value": 40, "count_unit": "events", "population": "H0",
                  "level": "REGISTERED RESULT", "scenario_sides": 7,
                  "source": {"file": "s18_census", "key": ["scan", "N4", "H0", "objective_losses"]}},
            "q": {"claim": "the claimant share", "value": "25/30", "count_unit": "opportunities", "population": "H0+HH+HI",
                  "level": "OFFLINE ACTION COUNTERFACTUAL", "scenario_sides": 10,
                  "source": {"doc": "doc_s23", "quote": "The saturated share is 0/30, within its maximum of 1/4; the "
                                                         "claimant share is 25/30, above its maximum of 1/2"}},
            "w": {"claim": "a thousands separator in the source", "value": 33696, "count_unit": "decisions",
                  "population": "H0", "level": "REGISTERED RESULT", "scenario_sides": 16,
                  "source": {"doc": "doc_s23", "quote": "| H0 decisions | 33,696 | 33,696 |"}},
        }

    def problems(self, **plant):
        evidence = copy.deepcopy(self.ok)
        for ident, fields in plant.items():
            evidence[ident].update(fields)
        return self.s.evidence_problems(evidence, RUBRIC, {})

    def test_known_good_items_pass(self) -> None:
        self.assertEqual(self.problems(), [])

    def test_planted_defects(self) -> None:
        self.assertTrue(self.problems(k={"value": 41}))
        self.assertTrue(self.problems(k={"value": 40.0}))
        self.assertTrue(self.problems(k={"source": {"file": "s18_census", "key": ["scan", "N4", "H0", "nothing"]}}))
        self.assertTrue(self.problems(k={"source": {"file": "census_elsewhere", "key": ["x"]}}))
        self.assertTrue(self.problems(q={"value": "24/30"}))
        self.assertTrue(self.problems(q={"source": {"doc": "doc_s23", "quote": "the claimant share is 25/31"}}))
        self.assertTrue(self.problems(w={"value": 3369}))
        self.assertTrue(self.problems(k={"level": "SUGGESTIVE"}))
        self.assertTrue(self.problems(k={"count_unit": "items"}))
        self.assertTrue(self.problems(k={"scenario_sides": -1}))
        broken = copy.deepcopy(self.ok)
        del broken["k"]["population"]
        self.assertTrue(self.s.evidence_problems(broken, RUBRIC, {}))

    def test_quotes_across_hard_line_breaks(self) -> None:
        # the document wraps "Every selection happens at decision 1 (step 0), the first play decision" over a line end
        q = {"source": {"doc": "doc_s23", "quote": "Every selection happens at decision 1 (step 0), the first play "
                                                   "decision, and nowhere else"}, "value": 1}
        self.assertEqual(self.problems(q=q), [])

    def test_whole_numbers(self) -> None:
        self.assertTrue(self.s.number_in(1709, "listed 1,709 times"))
        self.assertTrue(self.s.number_in(1709, "listed 1709 times"))
        self.assertFalse(self.s.number_in(25, "125 events"))
        self.assertFalse(self.s.number_in(25, "2,500 events"))
        self.assertFalse(self.s.number_in(25, "25/30 of them"))
        self.assertFalse(self.s.number_in(2, "2,500 events"))
        self.assertFalse(self.s.number_in(40, "40.5 steps"))
        self.assertTrue(self.s.number_in("25/30", "share 25/30, above"))
        self.assertFalse(self.s.number_in(0.81, "a median of 0.815"))
        self.assertTrue(self.s.number_in(0.81, "a median of 0.81 (mirrors"))


class ExperimentAndPublicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = load_script()

    def entry(self, **changes):
        e = {f: None for f in self.s.EXPERIMENT_FIELDS}
        e.update({"id": "X-1", "family": "X", "new_family": False, "evidence": [], "next_sessions": 0,
                  "follow_sessions": 2, "engineering": 1, "interaction": 1, "related_closed": {}, "repairs": []})
        e.update(changes)
        return e

    def test_experiment_checks(self) -> None:
        self.assertEqual(self.s.experiment_problems({"X": self.entry()}, {}, RUBRIC), [])
        self.assertTrue(self.s.experiment_problems({"X": self.entry(evidence=["nope"])}, {}, RUBRIC))
        self.assertTrue(self.s.experiment_problems({"X": self.entry(related_closed={"T6-G": "differs"})}, {}, RUBRIC))
        self.assertTrue(self.s.experiment_problems(
            {"X": self.entry(related_closed={"T6-G threat-entry gate": " "})}, {}, RUBRIC))
        self.assertEqual(self.s.experiment_problems(
            {"X": self.entry(related_closed={"T6-G threat-entry gate": "different trigger"})}, {}, RUBRIC), [])
        self.assertTrue(self.s.experiment_problems({"X": self.entry(engineering=5)}, {}, RUBRIC))
        self.assertTrue(self.s.experiment_problems({"X": self.entry(interaction=3)}, {}, RUBRIC))
        self.assertTrue(self.s.experiment_problems({"X": self.entry(next_sessions=-1)}, {}, RUBRIC))
        self.assertTrue(self.s.experiment_problems({"X": self.entry(family="Y")}, {}, RUBRIC))
        incomplete = self.entry()
        del incomplete["stop"]
        self.assertTrue(self.s.experiment_problems({"X": incomplete}, {}, RUBRIC))

    def test_public_content(self) -> None:
        self.assertEqual(self.s.public_problems({"note": "T2-X1 was shelved"}), [])
        self.assertTrue(self.s.public_problems({"note": "the t2-transport-x1 candidate"}))
        self.assertTrue(self.s.public_problems({"units": 3}))
        self.assertTrue(self.s.public_problems({"a": {"path": "x"}}))


class CandidateTableTest(unittest.TestCase):
    """The computed and capped values that enter the rule, on a two-candidate fixture over real pinned sources."""

    def setUp(self) -> None:
        self.s = load_script()
        self.evidence = {
            "strong": {"claim": "held objectives lost in H0", "value": 40, "count_unit": "events", "population": "H0",
                       "level": "REGISTERED RESULT", "scenario_sides": 7,
                       "source": {"file": "s18_census", "key": ["scan", "N4", "H0", "objective_losses"]}},
            "weak": {"claim": "a post-hoc count", "value": 40, "count_unit": "events", "population": "H0",
                     "level": "POST-HOC DIAGNOSTIC", "scenario_sides": 10,
                     "source": {"file": "s18_census", "key": ["scan", "N4", "H0", "objective_losses"]}},
        }
        base = {"next_sessions": 0, "follow_sessions": 2, "engineering": 1, "interaction": 2, "next_offline": True,
                "conflict_measured": True, "repairs": [], "depends_on_unidentified": False,
                "uses_stopped_data": False}
        self.experiments = {"A": {**base, "id": "A-1", "family": "A", "new_family": False, "evidence": ["strong"]},
                            "B": {**base, "id": "B-1", "family": "B", "new_family": True, "evidence": ["weak"],
                                  "interaction": 1, "engineering": 3, "next_sessions": 1}}
        g = {"file": "s18_census", "key": ["S", "presence_all", "T6 any unit"], "of": 50}
        p_stake = {"file": "s18_census", "key": ["opportunity_sides", "sides_with_opportunity",
                                                 "scan objective lost after being held"], "of": 16, "basis": "STAKE"}
        p_zero = {"file": "s18_census", "key": None, "of": 16, "basis": "TRIGGER", "zero_reason": "no frozen scenario"}
        judged = {c: [5, "reason"] for c in sel.JUDGED}
        self.scores = {"A": {**judged, "increment": "A-1", "G": g, "P": p_stake, "stakes": ["strong"]},
                       "B": {**judged, "increment": "B-1", "G": g, "P": p_zero, "stakes": ["weak"]}}

    def build(self, admission=None):
        return self.s.candidate_table(self.experiments, self.scores, self.evidence,
                                      admission if admission is not None else {"B": {"admitted": True}}, RUBRIC, {})

    def test_computed_and_capped_values(self) -> None:
        rows, cands, caps = self.build()
        self.assertEqual(rows["A"]["G_source"], {"count": 50, "of": 50, "share": 1.0, "score": 5})
        # 7 of 16 sides is level 2, lowered to 1 on a stake basis
        self.assertEqual(rows["A"]["P_source"], {"count": 7, "of": 16, "share": 0.4375, "score": 1, "basis": "STAKE"})
        self.assertEqual(rows["B"]["P_source"]["score"], 0)
        self.assertEqual((cands["A"]["scores"]["L"], caps["A"]), (5, 5))
        self.assertEqual((cands["B"]["scores"]["L"], caps["B"], rows["B"]["caps_applied"]), (3, 3, ["L capped at 3"]))
        self.assertEqual((cands["A"]["scores"]["I"], rows["A"]["caps_applied"]), (3, ["I capped at 3 (X2)"]))
        self.assertEqual(cands["B"]["scores"]["I"], 5)
        self.assertEqual((cands["A"]["scores"]["C"], cands["B"]["scores"]["C"]), (3, 0))
        self.assertTrue(cands["B"]["admitted"])
        _, cands, _ = self.build(admission={})
        self.assertEqual((cands["A"]["admitted"], cands["B"]["admitted"]), (True, False))

    def test_refusals(self) -> None:
        self.scores["B"]["P"] = {**self.scores["B"]["P"], "zero_reason": ""}
        with self.assertRaises(SystemExit):
            self.build()
        self.setUp()
        self.scores["A"]["P"] = {**self.scores["A"]["P"], "of": 15}
        with self.assertRaises(SystemExit):
            self.build()
        self.setUp()
        self.scores["A"]["stakes"] = ["weak"]
        with self.assertRaises(SystemExit):
            self.build()
        self.setUp()
        self.scores["A"]["L"] = [4, " "]
        with self.assertRaises(SystemExit):
            self.build()
        self.setUp()
        del self.scores["B"]
        with self.assertRaises(SystemExit):
            self.build()


class CommittedFilesTest(unittest.TestCase):
    def test_inputs_are_pinned_and_regenerate(self) -> None:
        s = load_script()
        record = json.loads((OUT / "inputs.json").read_text(encoding="utf-8"))
        self.assertEqual(s.pin_problems(record), [])
        self.assertEqual((OUT / "inputs.json").read_text(encoding="utf-8"), s.dump(s.freeze_record()))
        self.assertEqual(set(record["sources"]), set(s.SOURCES))
        for name, rel in s.SOURCES.items():
            self.assertFalse(rel.endswith(("TACTICAL_FRONTIER.md", "README.md")), name)
        for key in ("rules_sha256", "rubric_sha256"):
            planted = copy.deepcopy(record)
            planted[key] = "0" * 64
            self.assertEqual(s.pin_problems(planted), [f"{key} differs"])
        planted = copy.deepcopy(record)
        planted["sources"]["doc_s23"]["sha256"] = "0" * 64
        self.assertEqual(s.pin_problems(planted), ["doc_s23: digest differs"])
        del planted["sources"]["doc_s23"]
        self.assertEqual(s.pin_problems(planted), ["doc_s23: not pinned"])

    @unittest.skipUnless((OUT / "selection.json").exists(), "written after the scores")
    def test_selection_regenerates(self) -> None:
        s = load_script()
        self.assertEqual((OUT / "selection.json").read_text(encoding="utf-8"), s.dump(s.build()))


if __name__ == "__main__":
    unittest.main()
