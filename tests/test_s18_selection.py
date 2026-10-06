"""Sprint 18 frozen selection rule: thresholds, eligibility, the tie band and E, robustness, and the committed files."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.evaluation import s18_selection as sel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s18-frontier-reset"
RUBRIC = json.loads((OUT / "rubric.json").read_text(encoding="utf-8"))


def cand(**kw):
    base = {"G": 5, "L": 3, "O": 5, "I": 3, "M": 4, "R": 5, "P": 4, "E": 3}
    base.update(kw)
    return base


def load_script():
    spec = importlib.util.spec_from_file_location("s18_select_script", ROOT / "scripts" / "s18_select.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RubricTest(unittest.TestCase):
    def test_registered_numbers(self) -> None:
        self.assertEqual(RUBRIC["weights"], {"G": 0.20, "L": 0.25, "O": 0.15, "I": 0.10, "M": 0.10, "R": 0.10, "P": 0.10})
        self.assertAlmostEqual(sum(RUBRIC["weights"].values()), 1.0)
        self.assertEqual((RUBRIC["tie_band"], RUBRIC["robust_min_first"], RUBRIC["variant_count"]), (0.15, 17, 25))
        self.assertEqual(RUBRIC["eligibility"]["min"], {"O": 3, "M": 3, "R": 2, "E": 2})
        self.assertEqual(RUBRIC["eligibility"]["excluded_families"], ["T1", "T1-r", "PS-1", "T4", "T9"])

    def test_variants(self) -> None:
        v = sel.variants(RUBRIC["weights"])
        self.assertEqual(len(v), RUBRIC["variant_count"])
        for name, w in v.items():
            self.assertAlmostEqual(sum(w.values()), 1.0, msg=name)
        self.assertAlmostEqual(v["leverage 0.40"]["L"], 0.40)
        self.assertAlmostEqual(v["without G"]["G"], 0.0)
        self.assertAlmostEqual(v["E as a criterion at 0.20"]["E"], 0.20)
        self.assertNotIn("E", v["equal weights"])
        self.assertAlmostEqual(v["L -0.05"]["L"], 0.20)

    def test_levels_at_planted_boundaries(self) -> None:
        g, p = RUBRIC["criteria"]["G"]["thresholds"], RUBRIC["criteria"]["P"]["thresholds"]
        self.assertEqual([sel.level(x, g) for x in (0.90, 0.8999, 0.75, 0.7499, 0.50, 0.25, 0.2499, 0.02, 0.0)],
                         [5, 4, 4, 3, 3, 2, 1, 1, 0])
        self.assertEqual([sel.level(x / 16, p) for x in (16, 15, 12, 11, 8, 7, 4, 3, 1, 0)],
                         [5, 4, 4, 3, 3, 2, 2, 1, 1, 0])
        self.assertEqual(sel.level(47 / 50, g), 5)
        self.assertEqual(sel.level(26 / 50, g), 3)


class SelectTest(unittest.TestCase):
    def test_clear_winner(self) -> None:
        r = sel.select({"A": cand(L=5), "B": cand(L=3)}, RUBRIC)          # W differs by 0.50
        self.assertEqual((r["outcome"], r["selected"], r["runner_up"], r["margin_over_runner_up"]),
                         ("NEXT_FAMILY_SELECTED", "A", "B", 0.5))

    def test_band_edge_and_e_tie_break(self) -> None:
        # M differs by one point (0.10), inside the band: the lower-W candidate wins on E
        r = sel.select({"A": cand(M=5, E=2), "B": cand(M=4, E=4)}, RUBRIC)
        self.assertEqual((r["outcome"], r["selected"], r["band"]), ("NEXT_FAMILY_SELECTED", "B", ["A", "B"]))
        # O differs by one point: exactly 0.15, inside the main band; at that edge the rescaled variants split, the
        # selected candidate is first in fewer than 17 of them, and the robustness rule makes it a tie
        r = sel.select({"A": cand(O=5, E=2), "B": cand(O=4, E=4)}, RUBRIC)
        self.assertEqual(r["band"], ["A", "B"])
        self.assertLess(r["selected_first_in"], 17)
        self.assertEqual((r["outcome"], r["tied"]), ("FRONTIER_TIE", ["A", "B"]))
        # G differs by one point: 0.20, outside the band, so W decides
        r = sel.select({"A": cand(G=5, E=2), "B": cand(G=4, E=5)}, RUBRIC)
        self.assertEqual((r["selected"], r["band"]), ("A", ["A"]))

    def test_equal_e_in_band_is_a_frontier_tie(self) -> None:
        r = sel.select({"A": cand(I=4, E=3), "B": cand(I=3, E=3), "C": cand(G=1, E=5)}, RUBRIC)
        self.assertEqual((r["outcome"], r["selected"], r["tied"]), ("FRONTIER_TIE", None, ["A", "B"]))

    def test_eligibility_minima_and_exclusions(self) -> None:
        for key, low in (("O", 2), ("M", 2), ("R", 1), ("E", 1)):
            r = sel.select({"A": cand(L=5, **{key: low}), "B": cand()}, RUBRIC)
            self.assertEqual(r["selected"], "B", key)
            self.assertFalse(r["eligible"]["A"])
        r = sel.select({"A": cand(O=3, M=3, R=2, E=2, L=5)}, RUBRIC)
        self.assertEqual(r["selected"], "A")
        r = sel.select({"T9": cand(L=5), "B": cand()}, RUBRIC)
        self.assertEqual(r["selected"], "B")

    def test_no_ready_family(self) -> None:
        r = sel.select({"A": cand(E=1), "B": cand(O=2)}, RUBRIC)
        self.assertEqual((r["outcome"], r["selected"], r["ranking"]), ("NO_READY_FAMILY", None, []))

    def test_robustness_threshold_is_applied(self) -> None:
        scores = {"A": cand(L=5), "B": cand(L=3, E=5)}
        r = sel.select(scores, RUBRIC)
        self.assertEqual(r["outcome"], "NEXT_FAMILY_SELECTED")
        planted = dict(RUBRIC, robust_min_first=r["selected_first_in"] + 1)
        r2 = sel.select(scores, planted)
        self.assertEqual((r2["outcome"], r2["tied"]), ("FRONTIER_TIE", ["A", "B"]))

    def test_variant_tie_order(self) -> None:
        w = {"G": 0.5, "L": 0.5}
        self.assertEqual(sel.first_in_variant({"A": {"G": 5, "L": 4, "E": 2, "R": 1},
                                               "B": {"G": 4, "L": 5, "E": 3, "R": 1}}, w, 0.15), "B")
        self.assertEqual(sel.first_in_variant({"A": {"G": 5, "L": 4, "E": 3, "R": 1},
                                               "B": {"G": 4, "L": 5, "E": 3, "R": 1}}, w, 0.15), "B")
        self.assertEqual(sel.first_in_variant({"A": {"G": 5, "L": 4, "E": 3, "R": 2},
                                               "B": {"G": 5, "L": 4, "E": 3, "R": 1}}, w, 0.15), "A")

    def test_variant_band_is_inclusive_and_r_breaks_ties(self) -> None:
        w = {"G": 0.15, "L": 0.85}
        # W 0.75 against 0.60: exactly the band, so the higher E wins inside it
        self.assertEqual(sel.first_in_variant({"A": {"G": 5, "L": 0, "E": 2, "R": 1},
                                               "B": {"G": 4, "L": 0, "E": 3, "R": 1}}, w, 0.15), "B")
        # equal W, E and L: the higher R wins even against the earlier identifier
        self.assertEqual(sel.first_in_variant({"A": {"G": 5, "L": 4, "E": 3, "R": 1},
                                               "B": {"G": 5, "L": 4, "E": 3, "R": 2}}, {"G": 0.5, "L": 0.5}, 0.15), "B")

    def test_robustness_threshold_is_inclusive(self) -> None:
        scores = {"A": cand(L=5), "B": cand(L=3, E=5)}
        r = sel.select(scores, RUBRIC)
        exact = dict(RUBRIC, robust_min_first=r["selected_first_in"])
        self.assertEqual(sel.select(scores, exact)["outcome"], "NEXT_FAMILY_SELECTED")

    def test_challenger_is_the_most_frequent_other_first(self) -> None:
        scores = {"A": {"G": 5, "L": 5, "O": 5, "I": 4, "M": 5, "R": 4, "P": 2, "E": 2},
                  "B": {"G": 5, "L": 5, "O": 3, "I": 5, "M": 3, "R": 3, "P": 4, "E": 5},
                  "C": {"G": 5, "L": 4, "O": 4, "I": 5, "M": 5, "R": 5, "P": 4, "E": 3}}
        r = sel.select(scores, RUBRIC)
        others = [f for f in r["variants"].values() if f != r["selected"]]
        self.assertEqual((r["selected"], others.count("B"), others.count("A")), ("C", 3, 2))
        self.assertEqual(r["most_frequent_other_first"], "B")
        planted = dict(RUBRIC, robust_min_first=26)
        self.assertEqual(sel.select(scores, planted)["tied"], ["B", "C"])

    def test_scores_must_be_integers_in_range(self) -> None:
        with self.assertRaises(ValueError):
            sel.select({"A": cand(L=6)}, RUBRIC)
        with self.assertRaises(ValueError):
            sel.select({"A": cand(L=4.0)}, RUBRIC)


class CommittedSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = load_script()
        cls.selection = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))

    def test_regenerates_byte_for_byte(self) -> None:
        text = json.dumps(self.script.build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        self.assertEqual(text, (OUT / "selection.json").read_text(encoding="utf-8"))

    def test_committed_outcome(self) -> None:
        s = self.selection
        self.assertEqual((s["outcome"], s["selected"], s["runner_up"], s["margin_over_runner_up"]),
                         ("NEXT_FAMILY_SELECTED", "T6", "T11", 0.25))
        self.assertEqual((s["selected_first_in"], s["variants_total"]), (24, 25))
        self.assertEqual(sorted(f for f, ok in s["eligible"].items() if not ok), ["T5", "TO-1"])
        self.assertEqual(len(s["candidates"]), 10)

    def test_every_experiment_has_the_registered_fields(self) -> None:
        experiments = json.loads((OUT / "experiments.json").read_text(encoding="utf-8"))["experiments"]
        fields = {"id", "hypothesis", "trigger", "action", "mechanism", "offline", "engine_probe", "sessions", "risk",
                  "stop", "negative_teaches", "to_ab"}
        scores = json.loads((OUT / "scores.json").read_text(encoding="utf-8"))["candidates"]
        self.assertEqual(sorted(experiments), sorted(scores))
        for family, e in experiments.items():
            self.assertEqual(set(e), fields, family)
            self.assertEqual(scores[family]["increment"], e["id"], family)

    def test_planted_score_changes_reach_the_outcome(self) -> None:
        raw = json.loads((OUT / "scores.json").read_text(encoding="utf-8"))
        planted = copy.deepcopy(raw)
        planted["candidates"]["T6"]["L"][0] = 3
        original = self.script.json.loads

        def fake_loads(text, *a, **k):
            data = original(text, *a, **k)
            return planted if isinstance(data, dict) and data.get("schema") == "miaosuan-s18-scores/1" else data
        with mock.patch.object(self.script.json, "loads", side_effect=fake_loads):
            out = self.script.build()
        self.assertEqual(out["weighted"]["T6"], 4.1)
        # T6, T11 and T2 are then within the band and T2 has the highest E
        self.assertEqual((out["band"], out["selected"]), (["T11", "T6", "T2"], "T2"))

        planted = copy.deepcopy(raw)
        planted["candidates"]["T2"]["L"][1] = ""
        with mock.patch.object(self.script.json, "loads", side_effect=fake_loads):
            with self.assertRaises(SystemExit):
                self.script.build()

    def test_computed_scores_follow_their_sources(self) -> None:
        c = self.selection["candidates"]
        self.assertEqual((c["T6"]["P_source"]["count"], c["T6"]["P_source"]["of"], c["T6"]["scores"]["P"]), (12, 16, 4))
        self.assertEqual((c["T8"]["G_source"]["count"], c["T8"]["scores"]["G"]), (26, 3))
        self.assertEqual((c["TO-1"]["P_source"]["count"], c["TO-1"]["P_source"]["of"]), (2, 8))


if __name__ == "__main__":
    unittest.main()
