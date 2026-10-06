"""Sprint 16 frozen rules (``evaluation/s16_mechanism.py``) and the analysis driver's pure parts
(``scripts/s16_analysis.py``). SYNTHETIC data: ledgers, decisions, unit ids in the 900000 range.

Every classification is tested at its boundary (the risk window's last decision, a firing decision equal to the
divergence), every bad-reservation clause alone and the fourth clause's conjunction member by member, the disposition
in its declared order, the restoration count without double counting at its thresholds, and the episode tracker on
every ending event, the corrected one included.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s14_design as sx
from miaosuan_agent.evaluation import s16_mechanism as ms
from miaosuan_agent.evaluation import s16_shadow as sh
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments import t9_delayed as td
from tests import test_t9_delayed as t15
from tests.test_t9_delayed import A, E, X, holders
from tests.test_t9_redistribution import RED, SEAT, observation, unit

ROOT = Path(__file__).resolve().parents[1]
C3, C2, R = "1930331196 C3", "1930331196 C2", "2120531121 C3"
U1, U2, U3 = 900501, 900502, 900503


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"t16_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CARDS = load("build_s16_card")


def fsd(k: int, ordinal: int = 5, changed=(U1,)) -> Dict[str, Any]:
    return {"k": k, "ordinal": ordinal, "changed": list(changed)}


def reservation_row(**flags: Any) -> Dict[str, Any]:
    row = {"v3_selection_not_kept": False, "dominated": False, "unreachable": False, "to_problem_objective": False,
           "consumes_last_place": False, "before_first_ownership": False, "capturer_without_place": False}
    row.update(flags)
    return row


class CardTest(unittest.TestCase):
    def test_committed_card_rebuilds_and_has_no_problem(self) -> None:
        text = CARDS.CARD.read_text(encoding="utf-8")
        self.assertEqual(ms.dump(CARDS.build()), text)
        card = json.loads(text)
        self.assertEqual(ms.card_problems(card, ROOT), [])
        self.assertEqual(card["card_id"], ms.CARD_ID)
        self.assertEqual(card["candidate"], ms.V3_ID)
        self.assertEqual(card["policies"][ms.V3_ID]["policy_source"]["sha256"],
                         "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8")
        self.assertIn("experiments/t9_batch.py", card["policies"][ms.V3_ID]["policy_source"]["files"])
        self.assertEqual(card["budget"], {"batch_sessions": 3, "ledger_base_session": 2790, "sprint_session_cap": 3})
        self.assertEqual(card["screen"]["expected_sessions"], [2791, 2792, 2793])
        self.assertFalse(card["screen"]["shadow"]["executable"])
        self.assertEqual(card["screen"]["shadow"]["id"], sh.SHADOW_ID)

    def test_schedule_is_the_owners_order_with_sprint10_seats(self) -> None:
        rows = [(g["screen_position"], g["scenario_id"], g["condition"], g["red"], g["blue"]) for g in ms.games()]
        self.assertEqual(rows, [(1, "1930331196", "C3", INERT_ID, ms.V3_ID), (2, "1930331196", "C2", ms.V3_ID, INERT_ID),
                                (3, "2120531121", "C3", INERT_ID, ms.V3_ID)])
        self.assertEqual([g["game_id"] for g in ms.games()],
                         [f"1930331196.C3.{ms.CARD_ID}.p01", f"1930331196.C2.{ms.CARD_ID}.p02",
                          f"2120531121.C3.{ms.CARD_ID}.p03"])

    def test_card_problems_catch_every_changed_pin(self) -> None:
        card = json.loads(CARDS.CARD.read_text(encoding="utf-8"))
        cases = []
        bad = copy.deepcopy(card)
        bad["policies"][ms.V3_ID]["policy_source"]["sha256"] = "0" * 64
        cases.append(bad)
        bad = copy.deepcopy(card)
        bad["screen"]["frozen_files"][ms.FROZEN_FILES[0]] = "0" * 64
        cases.append(bad)
        bad = copy.deepcopy(card)
        bad["games"][0]["red"], bad["games"][0]["blue"] = bad["games"][0]["blue"], bad["games"][0]["red"]
        cases.append(bad)
        bad = copy.deepcopy(card)
        bad["budget"]["sprint_session_cap"] = 4
        cases.append(bad)
        bad = copy.deepcopy(card)
        bad["screen"]["rules"]["restoration_required"]["H1"] = 7
        cases.append(bad)
        bad = copy.deepcopy(card)
        bad["screen"]["shadow"]["executable"] = True
        cases.append(bad)
        bad = copy.deepcopy(card)
        bad["card_id"] = "s12-v3-adverse-1"
        cases.append(bad)
        for case in cases:
            self.assertTrue(ms.card_problems(case, ROOT), case.get("card_id"))
        self.assertEqual(len(cases), 7)

    def test_build_card_refuses_a_changed_identity(self) -> None:
        shoot = json.loads((ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" /
                            "manifest.json").read_text(encoding="utf-8"))
        good = CARDS.build()
        policies = [{"id": pid, "label": p["label"], "policy_source": p["policy_source"]}
                    for pid, p in good["policies"].items()]
        wrong = copy.deepcopy(policies)
        next(p for p in wrong if p["id"] == ms.V3_ID)["policy_source"]["sha256"] = "1" * 64
        with self.assertRaises(ValueError):
            ms.build_card(shoot, mf.digest(shoot), wrong, ms.frozen_digests(ROOT), CARDS.shadow_identity())
        with self.assertRaises(ValueError):
            ms.build_card(shoot, mf.digest(shoot), policies, {}, CARDS.shadow_identity())

    def test_frozen_files_exist_and_rules_are_pinned(self) -> None:
        for rel in ms.FROZEN_FILES:
            self.assertTrue((ROOT / rel).is_file(), rel)
        self.assertEqual(ms.RULES["restoration_required"],
                         {s: math.ceil(0.5 * n) for s, n in ms.RULES["reference_units"].items()})
        self.assertEqual((ms.RULES["reference_units"], ms.RULES["restoration_required"]),
                         ({"H1": 15, "H2": 26}, {"H1": 8, "H2": 13}))
        self.assertEqual(ms.RULES["historical_fire_anchors"], {C3: [742, 804, 841, 876], C2: [611]})
        self.assertEqual((ms.RULES["recourse_per_episode_max"], ms.RULES["capacity"], ms.RULES["max_step"]),
                         (1, 4, 2880))
        self.assertEqual(ms.rules_digest(), "614da9f3684b1b65ef855ba5547acc71175c9048b39d09169aecb9b967e8f941")
        self.assertEqual((ms.LEDGER_BASE_SESSION, ms.SESSION_CEILING, ms.EXPECTED_SESSIONS), (2790, 3, (2791, 2792, 2793)))
        self.assertEqual((ms.V3_ID, ms.V3_DIGEST, ms.V2_DIGEST),
                         ("t9-batch-capacity-v3", "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8",
                          "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"))


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.card = json.loads(CARDS.CARD.read_text(encoding="utf-8"))
        self.digest = mf.digest(self.card)
        self.ids = [g["game_id"] for g in self.card["games"]]

    def ledger(self, plays: List[str], close_ok=True, unclosed=(), card=None, digest=None, state="s") -> List[Dict]:
        rows = [{"event": "session-close", "session": "2790", "state": {"x": "s"}, "integrity": {"ok": True}}]
        for n, game in enumerate(plays, start=2791):
            rows.append({"event": "session-open", "session": str(n), "state": {"x": state},
                         "harness": {"game_id": game, "card": card or ms.CARD_ID, "manifest_sha256": digest or self.digest}})
            if str(n) not in unclosed:
                rows.append({"event": "session-close", "session": str(n), "state": {"x": state},
                             "integrity": {"ok": close_ok}})
        return rows

    def test_three_games_in_order_pass(self) -> None:
        audit = ms.ledger_audit(self.ledger(self.ids), self.card)
        self.assertTrue(audit["ok"], audit)
        self.assertEqual((audit["sessions"], audit["unclosed"]), (3, []))
        self.assertTrue(ms.ledger_audit(self.ledger([]), self.card)["ok"])

    def test_every_ledger_defect_is_found(self) -> None:
        cases = {
            "order": (self.ledger([self.ids[1], self.ids[0]]), "S2"),
            "outside": (self.ledger(["2130511121.H1.other.p01"]), "S2"),
            "twice": (self.ledger([self.ids[0], self.ids[0]]), "S2"),
            "unclosed": (self.ledger(self.ids[:1], unclosed=("2791",)), "S2"),
            "integrity": (self.ledger(self.ids[:1], close_ok=False), "S1"),
            "card": (self.ledger(self.ids[:1], card="s12-v3-primary-1"), "S2"),
            "digest": (self.ledger(self.ids[:1], digest="0" * 64), "S2"),
            "state": (self.ledger(self.ids[:1], state="other"), "S1"),
            "fourth": (self.ledger(self.ids + [self.ids[0]]), "S2"),
        }
        recovered = self.ledger(self.ids[:1])
        recovered[-1]["event"] = "session-recovered"
        cases["recovered"] = (recovered, "S2")
        for name, (rows, code) in cases.items():
            audit = ms.ledger_audit(rows, self.card)
            self.assertFalse(audit["ok"], name)
            self.assertTrue(audit["problems"][code], name)
        fourth = ms.ledger_audit(cases["fourth"][0], self.card)["problems"]["S2"]
        self.assertIn("4 sessions exceed the ceiling of 3", fourth)  # its own finding, besides position and repeat

    def test_structural_stops(self) -> None:
        stops = {c: ["x"] for c in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13",
                                    "S14")}
        self.assertEqual(ms.structural_stops(stops), ["S1", "S2", "S3", "S4", "S6", "S7"])
        self.assertEqual(ms.structural_stops({"S5": ["x"], "S14": ["x"], "S8": ["x"]}), [])
        self.assertEqual(ms.structural_stops({"S7": [], "S4": ["x"]}), ["S4"])


class DivergenceTest(unittest.TestCase):
    MOVE_A = {"obj_id": U1, "type": 1, "move_path": [1, 2, 3]}
    MOVE_B = {"obj_id": U2, "type": 1, "move_path": [4, 5]}
    SHOT = {"obj_id": U3, "type": 2, "target_obj_id": 9}

    def test_divergence_and_changed_units(self) -> None:
        same = [self.MOVE_A, self.MOVE_B, self.SHOT]
        self.assertFalse(ms.diverges(same, [dict(a) for a in same]))
        self.assertEqual(ms.changed_units(same, same), [])
        redirected = [dict(self.MOVE_A, move_path=[1, 7]), self.MOVE_B, self.SHOT]
        self.assertTrue(ms.diverges(same, redirected))
        self.assertEqual(ms.changed_units(same, redirected), [U1])
        withheld = [self.MOVE_B, self.SHOT]
        self.assertEqual(ms.changed_units(same, withheld), [U1])
        reordered = [self.MOVE_B, self.MOVE_A, self.SHOT]
        self.assertTrue(ms.diverges(same, reordered))  # order alone is a divergence
        self.assertEqual(ms.changed_units(same, reordered), [])

    def test_fire_window_end(self) -> None:
        self.assertEqual(ms.fire_window_end(C3, {}), 876)
        self.assertEqual(ms.fire_window_end(C3, {U1: [100, 900]}), 900)
        self.assertEqual(ms.fire_window_end(C3, {U1: [100]}), 876)
        self.assertEqual(ms.fire_window_end(C2, {U1: [300]}), 611)
        self.assertEqual(ms.fire_window_end(C2, {U1: [300], U2: [650]}), 650)
        self.assertEqual(ms.reservation_window_end(None, 2880), 2880)
        self.assertEqual(ms.reservation_window_end(480, 2880), 480)


class FireClassTest(unittest.TestCase):
    def test_no_divergence_is_prefix_safe_with_no_trigger(self) -> None:
        out = ms.classify_fire(C3, None, 876, {U1: 742}, {})
        self.assertEqual((out["class"], out["sublabel"]), ("C3_PREFIX_SAFE", ms.NO_TRIGGER))
        self.assertEqual(ms.classify_fire(C2, None, 611, {}, {})["class"], "C2_PREFIX_SAFE")

    def test_the_risk_window_boundary(self) -> None:
        self.assertEqual(ms.classify_fire(C3, fsd(877, changed=(U1,)), 876, {U1: 742}, {U1: [876]})["class"],
                         "C3_PREFIX_SAFE")
        self.assertEqual(ms.classify_fire(C3, fsd(876, changed=(U2,)), 876, {U1: 742}, {})["class"],
                         "C3_PREFIX_AMBIGUOUS")  # at the window's last decision: inside
        self.assertEqual(ms.classify_fire(C2, fsd(612, changed=(U2,)), 611, {}, {})["class"], "C2_PREFIX_SAFE")
        self.assertEqual(ms.classify_fire(C2, fsd(611, changed=(U2,)), 611, {}, {})["class"], "C2_PREFIX_AMBIGUOUS")

    def test_shooters_and_fire_roles(self) -> None:
        # a historical shooter before (or at) its firing decision
        self.assertEqual(ms.classify_fire(C3, fsd(500, changed=(U1,)), 876, {U1: 742}, {})["class"],
                         "C3_FIRST_DIVERGENCE_UNSAFE")
        self.assertEqual(ms.classify_fire(C3, fsd(742, changed=(U1,)), 876, {U1: 742}, {})["class"],
                         "C3_FIRST_DIVERGENCE_UNSAFE")
        # after its historical firing decision, with no fire role left in the new game: not that mechanism
        self.assertEqual(ms.classify_fire(C3, fsd(800, changed=(U1,)), 876, {U1: 742}, {})["class"],
                         "C3_PREFIX_AMBIGUOUS")
        # a unit carrying a fire listing now, or later inside the window, in the new game
        self.assertEqual(ms.classify_fire(C2, fsd(300, changed=(U2,)), 611, {}, {U2: [300]})["class"],
                         "C2_FIRST_DIVERGENCE_UNSAFE")
        self.assertEqual(ms.classify_fire(C2, fsd(300, changed=(U2,)), 611, {}, {U2: [600]})["class"],
                         "C2_FIRST_DIVERGENCE_UNSAFE")
        # fire listed only before the divergence: no role left
        self.assertEqual(ms.classify_fire(C2, fsd(300, changed=(U2,)), 611, {}, {U2: [299]})["class"],
                         "C2_PREFIX_AMBIGUOUS")
        # another unit's role does not make this change unsafe
        self.assertEqual(ms.classify_fire(C3, fsd(500, changed=(U2,)), 876, {U1: 742}, {U1: [742]})["class"],
                         "C3_PREFIX_AMBIGUOUS")
        # one protected unit among several changed units is enough
        out = ms.classify_fire(C3, fsd(500, changed=(U2, U1)), 876, {U1: 742}, {})
        self.assertEqual(out["class"], "C3_FIRST_DIVERGENCE_UNSAFE")
        self.assertTrue(out["reasons"])

    def test_the_opening_topology(self) -> None:
        self.assertEqual(ms.classify_fire(C2, fsd(1, ordinal=1, changed=(U2,)), 611, {}, {})["class"],
                         "C2_FIRST_DIVERGENCE_UNSAFE")
        self.assertEqual(ms.classify_fire(C2, fsd(2, ordinal=2, changed=(U2,)), 611, {}, {})["class"],
                         "C2_PREFIX_AMBIGUOUS")

    def test_protected_reasons(self) -> None:
        self.assertEqual(ms.protected_reasons(U1, 10, 50, {U1: 9}, {}), [])
        self.assertEqual(len(ms.protected_reasons(U1, 10, 50, {U1: 10}, {U1: [10]})), 2)
        self.assertEqual(ms.protected_reasons(U1, 10, 50, {}, {U1: [51]}), [])  # beyond the window


class ReservationTest(unittest.TestCase):
    def test_safe_cases_and_boundary(self) -> None:
        self.assertEqual(ms.classify_reservation(None, 564, [])["class"], "C3_212_PREFIX_SAFE")
        self.assertEqual(ms.classify_reservation(None, 564, [])["sublabel"], ms.NO_TRIGGER)
        self.assertEqual(ms.classify_reservation(fsd(565), 564, [reservation_row(dominated=True)])["class"],
                         "C3_212_PREFIX_SAFE")
        self.assertEqual(ms.classify_reservation(fsd(564), 564, [reservation_row()])["class"],
                         "C3_212_PREFIX_AMBIGUOUS")

    def test_each_clause_alone_is_a_bad_reservation(self) -> None:
        for flag in ("v3_selection_not_kept", "dominated", "unreachable"):
            out = ms.classify_reservation(fsd(100), 564, [reservation_row(**{flag: True})])
            self.assertEqual(out["class"], "C3_212_FIRST_DIVERGENCE_BAD_RESERVATION", flag)
        full = dict(to_problem_objective=True, consumes_last_place=True, before_first_ownership=True,
                    capturer_without_place=True)
        self.assertEqual(ms.classify_reservation(fsd(100), 564, [reservation_row(**full)])["class"],
                         "C3_212_FIRST_DIVERGENCE_BAD_RESERVATION")
        for missing in full:  # the fourth clause needs all four conditions
            partial = dict(full, **{missing: False})
            self.assertEqual(ms.classify_reservation(fsd(100), 564, [reservation_row(**partial)])["class"],
                             "C3_212_PREFIX_AMBIGUOUS", missing)
        self.assertEqual(ms.classify_reservation(fsd(1, ordinal=1), 564, [reservation_row()])["class"],
                         "C3_212_FIRST_DIVERGENCE_BAD_RESERVATION")
        self.assertEqual(ms.reservation_flags(reservation_row(dominated=True, unreachable=True)),
                         [ms.RESERVATION_CLAUSES[1], ms.RESERVATION_CLAUSES[2]])

    def test_ownership_facts(self) -> None:
        self.assertEqual(ms.ownership_facts(100, None, [U1], []),
                         {"before_first_ownership": True, "capturer_without_place": False})
        self.assertEqual(ms.ownership_facts(100, 100, [U1], [U1])["before_first_ownership"], False)
        self.assertEqual(ms.ownership_facts(99, 100, [U1], [U1])["before_first_ownership"], True)
        self.assertEqual(ms.ownership_facts(99, 100, [U1], [U1, U2])["capturer_without_place"], True)
        self.assertEqual(ms.ownership_facts(99, 100, [U1, U2], [U2])["capturer_without_place"], False)

    def test_domination(self) -> None:
        def c(ff, feasible=True, placed=False):
            return {"free_flow": ff, "feasible": feasible, "placed": placed}
        self.assertTrue(ms.dominated(200, [c(100)]))
        self.assertFalse(ms.dominated(200, [c(300)]))
        self.assertFalse(ms.dominated(200, [c(200)]))
        self.assertFalse(ms.dominated(200, [c(100, placed=True)]))
        self.assertFalse(ms.dominated(200, [c(100, feasible=False)]))
        self.assertFalse(ms.dominated(200, [c(None)]))
        self.assertTrue(ms.dominated(None, []))
        self.assertFalse(ms.dominated(200, []))


class DispositionTest(unittest.TestCase):
    SAFE = {C3: {"class": "C3_PREFIX_SAFE", "sublabel": ms.NO_TRIGGER}, C2: {"class": "C2_PREFIX_SAFE", "sublabel": "x"},
            R: {"class": "C3_212_PREFIX_SAFE", "sublabel": ms.NO_TRIGGER}}

    def test_order(self) -> None:
        self.assertEqual(ms.disposition(["capture"], self.SAFE)["disposition"], "CAPTURE_INVALID")
        missing = {c: v for c, v in self.SAFE.items() if c != R}
        self.assertEqual(ms.disposition([], missing)["disposition"], "CAPTURE_INVALID")
        supported = ms.disposition([], self.SAFE)
        self.assertEqual(supported["disposition"], "MECHANISM_PREFIX_SUPPORTED")
        self.assertEqual(supported["no_trigger_observed"], [C3, R])
        ambiguous = dict(self.SAFE, **{C2: {"class": "C2_PREFIX_AMBIGUOUS"}})
        self.assertEqual(ms.disposition([], ambiguous), {"disposition": "MECHANISM_AMBIGUOUS", "configurations": [C2]})
        both = dict(ambiguous, **{R: {"class": "C3_212_FIRST_DIVERGENCE_BAD_RESERVATION"}})
        self.assertEqual(ms.disposition([], both), {"disposition": "MECHANISM_REFUTED", "configurations": [R]})
        unsafe = dict(self.SAFE, **{C3: {"class": "C3_FIRST_DIVERGENCE_UNSAFE"}})
        self.assertEqual(ms.disposition([], unsafe)["disposition"], "MECHANISM_REFUTED")
        with self.assertRaises(ValueError):
            ms.disposition([], dict(self.SAFE, **{C3: {"class": "C2_PREFIX_SAFE"}}))
        self.assertEqual(ms.DISPOSITIONS, ("CAPTURE_INVALID", "MECHANISM_REFUTED", "MECHANISM_AMBIGUOUS",
                                           "MECHANISM_PREFIX_SUPPORTED"))


class RestorationTest(unittest.TestCase):
    def reference(self, h1: int, h2: int):
        return {"H1": {("p01", 900000 + i) for i in range(h1)}, "H2": {("p02", 910000 + i) for i in range(h2)}}

    def test_thresholds_and_distinct_units(self) -> None:
        ref = self.reference(15, 26)
        got = {"H1": {("p01", 900000 + i) for i in range(8)}, "H2": {("p02", 910000 + i) for i in range(13)}}
        out = ms.restoration(ref, got)
        self.assertTrue(out["pass"])
        self.assertEqual(out["reference_reproduced"], {"H1": True, "H2": True})
        self.assertEqual((out["seats"]["H1"]["restored_units"], out["seats"]["H2"]["restored_units"]), (8, 13))
        short = {"H1": {("p01", 900000 + i) for i in range(7)}, "H2": got["H2"]}
        self.assertFalse(ms.restoration(ref, short)["pass"])
        short = {"H1": got["H1"], "H2": {("p02", 910000 + i) for i in range(12)}}
        self.assertFalse(ms.restoration(ref, short)["pass"])
        # units outside the reference and units of another game do not count; a set cannot double count a unit
        stray = {"H1": {("p03", 900000 + i) for i in range(8)} | {("p01", 950000 + i) for i in range(8)},
                 "H2": got["H2"]}
        self.assertEqual(ms.restoration(ref, stray)["seats"]["H1"]["restored_units"], 0)
        self.assertEqual(ms.restoration(self.reference(14, 26), got)["reference_reproduced"]["H1"], False)


class TrackerTest(unittest.TestCase):
    FLAGS = {A: -1, E: -1}

    def test_episode_ending_events(self) -> None:
        def opened() -> ms.EpisodeTracker:
            t = ms.EpisodeTracker()
            t.before({U1: (506, ())}, self.FLAGS, RED)
            t.after(1, {U1: (A, True, False)}, {})
            self.assertIn(U1, t.open)
            return t
        cases = {"absent": ({}, self.FLAGS), "moving to an objective": ({U1: (506, (507, E))}, self.FLAGS),
                 "standing on an unheld objective": ({U1: (E, ())}, self.FLAGS),
                 "source held": ({U1: (506, ())}, {A: RED, E: -1})}
        for name, (units, flags) in cases.items():
            t = opened()
            t.before(units, flags, RED)
            self.assertNotIn(U1, t.open, name)
            self.assertEqual(len(t.closed), 1, name)
        t = opened()  # the corrected semantics: standing on an objective the side holds keeps the episode
        t.before({U1: (E, ())}, {A: -1, E: RED}, RED)
        self.assertIn(U1, t.open)
        t = opened()
        self.assertNotIn(607, self.FLAGS)
        t.before({U1: (506, (507, 607))}, self.FLAGS, RED)  # a path ending off the objectives (a staging move)
        self.assertIn(U1, t.open)
        for claim in ((A, True, True), (A, False, False)):  # given a place; cannot arrive
            t = opened()
            t.after(2, {U1: claim}, {})
            self.assertNotIn(U1, t.open)

    def test_recourse_per_episode(self) -> None:
        t = ms.EpisodeTracker()
        for k in range(1, 5):
            t.before({U1: (506, ())}, self.FLAGS, RED)
            t.after(k, {U1: (A, True, False)}, {U1: E} if k == 2 else {})
        out = ms.recourse([t])
        self.assertEqual((out["episodes"], out["max_redirects_per_episode"], out["pass"]), (1, 1, True))
        t.after(5, {U1: (A, True, False)}, {U1: E})  # a second redirect in the same episode
        out = ms.recourse([t])
        self.assertEqual((out["max_redirects_per_episode"], out["episodes_over_limit"], out["pass"]), (2, 1, False))

    def test_a_new_source_is_a_new_episode_and_totals_are_descriptive(self) -> None:
        t = ms.EpisodeTracker()
        t.before({U1: (506, ())}, self.FLAGS, RED)
        t.after(1, {U1: (A, True, False)}, {U1: E})
        t.before({U1: (506, ())}, self.FLAGS, RED)
        t.after(2, {U1: (E, True, False)}, {U1: A})
        out = ms.recourse([t])
        self.assertEqual((out["episodes"], out["max_redirects_per_episode"], out["pass"]), (2, 1, True))
        self.assertEqual(out["redirects_per_unit"], {2: 1})
        self.assertEqual(out["oscillations_across_episodes"], 1)  # A to E, later E to A: reported, not gated
        self.assertEqual(ms.oscillations([(1, U1, A, E), (2, U2, E, A)]), 0)  # another unit is no oscillation

    def test_redirect_outside_an_episode_and_two_destinations_fail(self) -> None:
        t = ms.EpisodeTracker()
        t.after(1, {}, {U1: E})
        self.assertFalse(ms.recourse([t])["pass"])
        self.assertEqual(ms.recourse([t])["redirects_outside_episodes"], 1)
        t = ms.EpisodeTracker()
        t.after(1, {U1: (A, True, False)}, {U1: E})
        t.after(2, {U1: (A, True, False)}, {U1: 999})
        out = ms.recourse([t])
        self.assertEqual((out["multi_destination_episodes"], out["pass"]), (1, False))

    def test_a_shadow_that_ignores_its_redirect_flag_fails_recourse(self) -> None:
        """Mutation-style: the frozen trigger with its per-episode flag removed redirects again in the same episode;
        the tracker, which never reads the shadow's memory, must catch it."""
        helper = t15.DelayedTest("test_the_scenes_are_what_they_claim")
        helper.setUp()
        frozen = td.eligible

        def unbounded(rule, record, source, best, saturated):
            if record is not None:
                record = list(record)
                record[td.REDIRECTED] = 0
            return frozen(rule, record, source, best, saturated)

        def drive() -> Dict[str, Any]:
            t, memory = ms.EpisodeTracker(), ()
            for k in range(1, 6):
                obs = helper.withheld_scene()
                policy, base = helper.base(obs)
                v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
                t.before({u.obj_id: (u.cur_hex, tuple(u.move_path or ())) for u in obs.operators() if u.color == RED},
                         {c.coord: c.flag for c in obs.cities()}, RED)
                result = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES["delayed-repeat-2"], memory)
                memory = result.memory
                t.after(k, {u: (c.objective, c.status == "no place under capacity", u in v3.selected)
                            for u, c in v3.claimants.items()}, {u: o.objective for u, o in result.redirected.items()})
            return ms.recourse([t])
        self.assertTrue(drive()["pass"])
        with mock.patch.object(td, "eligible", unbounded):
            broken = drive()
        self.assertFalse(broken["pass"])
        self.assertGreater(broken["max_redirects_per_episode"], 1)


class AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = load("s16_analysis")

    def test_certificate_on_a_synthetic_first_divergence(self) -> None:
        helper = t15.DelayedTest("test_the_scenes_are_what_they_claim")
        helper.setUp()
        obs = helper.withheld_scene()
        policy, base = helper.base(obs)
        first = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES["delayed-repeat-2"], ())
        v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
        alloc = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES["delayed-repeat-2"], first.memory)
        self.assertTrue(ms.diverges(v3.actions, alloc.actions))
        checks = sx.candidate_checks(obs, SEAT, RED, base, alloc.actions, alloc, v3, helper.costs)
        cert = self.analysis.certificate("delayed-repeat-2", 7, 3, obs, SEAT, RED, base, v3, alloc, first.memory, checks,
                                         helper.costs, E)
        self.assertEqual((cert["k"], cert["ordinal"], cert["changed"]), (7, 3, [X]))
        (row,) = cert["redirects"]
        self.assertEqual((row["source"], row["alternative"], row["episode_count"]), (A, E, 2))
        self.assertEqual((row["v3_form"], row["shadow_form"]), ("WITHHOLD", "REDIRECT"))
        self.assertEqual((row["staging_completed"], row["previous_staging_source"]), (False, None))
        self.assertEqual((row["destination_counted_before"], row["consumes_last_place"]), (0, False))
        self.assertEqual((row["dominated"], row["unreachable"], row["v3_selection_not_kept"]), (False, False, False))
        self.assertEqual((row["to_problem_objective"], row["fire_listed_now"], row["source_counted"]), (True, False, 4))
        self.assertEqual(row["arrival_slack"], 2880 - (100 + row["free_flow"]))
        self.assertGreater(row["detour_ratio"], 1.0)

    def test_certificate_when_the_redirect_fills_the_last_place(self) -> None:
        helper = t15.DelayedTest("test_the_scenes_are_what_they_claim")
        helper.setUp()
        standing_at_e = [unit(905300 + k, E) for k in range(3)]
        obs = observation(holders() + standing_at_e + [unit(X, 506)], cities=(A, E), movable=[X])
        policy, base = helper.base(obs)
        first = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES["delayed-repeat-2"], ())
        v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
        alloc = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES["delayed-repeat-2"], first.memory)
        self.assertEqual(alloc.redirected[X].objective, E)
        checks = sx.candidate_checks(obs, SEAT, RED, base, alloc.actions, alloc, v3, helper.costs)
        cert = self.analysis.certificate("delayed-repeat-2", 9, 2, obs, SEAT, RED, base, v3, alloc, first.memory, checks,
                                         helper.costs, E)
        (row,) = cert["redirects"]
        self.assertEqual((row["destination_counted_before"], row["consumes_last_place"]), (3, True))
        self.assertEqual(sorted(row["problem_holders_at_divergence"]), [905300, 905301, 905302])
        self.assertEqual(row["v3_selected_at_destination"], [])

    def test_public_texts_refuse_private_values_and_the_v3_identity(self) -> None:
        a = self.analysis
        results = [({}, {"names": {"505": "x"}, "problem": None})]
        self.assertEqual(sorted(a.public_texts({"x": {"value": 1}}, results)), ["x"])
        for bad in ({"obj_id": 1}, {"value": 505}, {"note": ms.V3_ID}, {"note": ms.V3_DIGEST}, {"hex": 3}):
            with self.assertRaises(SystemExit, msg=str(bad)):
                a.public_texts({"x": bad}, results)

    def test_public_certificate_carries_no_identifier(self) -> None:
        a = self.analysis
        a.ANCHORS.update({"shooters": {C3: {}, C2: {}}})
        row = {"unit": X, "kind": 2, "trigger": "staged", "source": A, "alternative": E, "episode_count": 1,
               "episode_age_steps": 0, "staging_completed": True, "previous_staging_source": A,
               "previous_staging_source_is_current": False, "baseline_destination": A, "v3_form": "STAGE",
               "v3_staged_length": 3, "shadow_form": "REDIRECT", "route_cost": 4.0, "own_cost": 3.0,
               "detour_ratio": 1.3333, "free_flow": 80, "arrival_slack": 2000, "source_counted": 4,
               "destination_counted_before": 1, "fire_listed_now": False, "visible_enemies": 0,
               "nearest_visible_enemy": None}
        fsd_ = {"k": 300, "cur_step": 299, "ordinal": 40, "changed": [X],
                "changed_rows": [{"unit": X, "kind": 2, "v3_form": "STAGE", "shadow_form": "REDIRECT"}],
                "redirects": [row], "violations": {}}
        out = a.public_certificate(fsd_, {str(A): "50-point objective A", str(E): "80-point objective A"}, 876, C3, {})
        self.assertEqual(ms.public_check(out, {X, A, E}), [])
        self.assertEqual(out["redirects"][0]["source"], "50-point objective A")
        self.assertEqual(out["redirects"][0]["firing_role"], [])
        self.assertTrue(out["redirects"][0]["before_risk_window_end"])

    def test_first_ownership_and_fire_facts(self) -> None:
        class State:
            def __init__(self, flags, valid):
                self.flags, self.valid = flags, valid
        states = [State({A: -1}, {U1: {1}}), State({A: -1}, {U1: {2}}), State({A: RED}, {}), State({A: RED}, {})]
        self.assertEqual(self.analysis.first_ownership(states, A, RED, 3), 2)
        self.assertIsNone(self.analysis.first_ownership(states, A, 1, 3))
        rows = [{"submitted": []}, {"submitted": [{"obj_id": U2, "type": 2}]}, {"submitted": []}]
        steps = [{}, {"feedback": [{"message": {"actor": SEAT, "obj_id": U2, "type": 2}}]}, {}]
        observed, public = self.analysis.fire_facts(SEAT, rows, states, steps)
        self.assertEqual(observed, {U1: [1], U2: [1]})
        self.assertEqual((public["orders"], public["order_decisions"], public["responses"]), (1, [1], {"accepted": 1}))
        self.assertEqual((public["first_listing_decision"], public["last_listing_decision"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
