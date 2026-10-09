"""The Sprint 27 probe rules (``evaluation/s27_probe.py``), observer (``evaluation/s27_capture.py``) and runner checks.

SYNTHETIC inputs throughout: ledgers, records, action lists and a stand-in head-to-head world
(``tests/fixtures/s27_engine.py``) in which the real ``baseline-v2`` plays both seats and the candidate one of them.
What is pinned: the card, its schedule, stages, pins, budget and the session mapping (2797 then 2798, nothing else);
every ledger defect and the stage prerequisites; the per-game structural checks; the registered-difference check; P1 at
its exact half-mean boundary and with the registered references; P2 with both references finite, one or both never
owned, a candidate that never owns, equality and the same-colour reference sets; the offline fidelity stop; the
mechanism rule, the stage gate and the disposition order with early termination; the observer's reconstruction, memory
chains and tampering detection; the real game loop with Sprint 26's frozen rule (through Sprint 26's own analysis)
replayed on the live trajectory, its independent check, the episode facts (an executed episode, a follower lost while
waiting, a blocked leader released by the wait bound, a refused leader MOVE); the runner's committed-gate check; and
the whitelist of the new identity.
"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import json
import pickle
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision import Memory
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation import s26_t6s as st
from miaosuan_agent.evaluation import s27_capture as cap
from miaosuan_agent.evaluation import s27_probe as sp
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.experiments import t6s_column_stagger_p1 as cand
from miaosuan_agent.experiments.exploratory_addon import AddonMemory
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from tests.fixtures import s27_engine as se
from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]


def script(name: str):
    spec = importlib.util.spec_from_file_location(f"s27_test_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------
# card


class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = script("build_s27_card")
        cls.card = cls.builder.build()

    def test_committed_card_rebuilds_byte_for_byte(self) -> None:
        self.assertEqual(self.builder.CARD.read_text(encoding="utf-8"), sp.dump(self.card))

    def test_schedule_stages_sessions_and_budget(self) -> None:
        games = [(g["game_id"], g["condition"], g["red"], g["blue"], g["screen_position"]) for g in self.card["games"]]
        self.assertEqual(games, [
            ("2130511121.H2.s27-t6s-probe-1.p01", "H2", sp.V2_ID, sp.CANDIDATE_ID, 1),
            ("2130511121.H1.s27-t6s-probe-1.p02", "H1", sp.CANDIDATE_ID, sp.V2_ID, 2)])
        self.assertEqual([sp.candidate_side(g) for g in self.card["games"]], ["blue", "red"])
        self.assertEqual(self.card["budget"], {"batch_sessions": 2, "ledger_base_session": 2796, "sprint_session_cap": 2})
        self.assertEqual(self.card["screen"]["stages"], {"A": 1, "B": 2})
        self.assertEqual(self.card["screen"]["expected_sessions"], [2797, 2798])
        self.assertEqual(self.card["execution"], {"runtime": "baseline-v1-runtime-r2", "workers": 1})
        self.assertIs(self.card["eligible_for_promotion"], False)
        self.assertEqual(self.card["candidate"], sp.CANDIDATE_ID)
        self.assertEqual(sorted(self.card["policies"]), sorted((sp.V2_ID, sp.CANDIDATE_ID)))
        self.assertEqual([s["scenario_id"] for s in self.card["scenarios"]], ["2130511121"])
        with self.assertRaises(ValueError):
            sp.candidate_side({"red": sp.CANDIDATE_ID, "blue": sp.CANDIDATE_ID})

    def test_card_problems_catch_every_pin(self) -> None:
        self.assertEqual(sp.card_problems(self.card, ROOT), [])
        cases = []
        c = copy.deepcopy(self.card); c["screen"]["rules"]["follow_up_window_steps"] = 299; cases.append(c)
        c = copy.deepcopy(self.card); c["screen"]["structural_stops"] = c["screen"]["structural_stops"][:-1]; cases.append(c)
        c = copy.deepcopy(self.card); c["screen"]["stages"] = {"A": 2, "B": 1}; cases.append(c)
        c = copy.deepcopy(self.card); c["screen"]["frozen_files"]["scripts/s27_analysis.py"] = "0" * 64; cases.append(c)
        c = copy.deepcopy(self.card); del c["screen"]["frozen_files"]["tests/test_s27_probe.py"]; cases.append(c)
        c = copy.deepcopy(self.card); c["policies"][sp.CANDIDATE_ID]["policy_source"]["sha256"] = "0" * 64; cases.append(c)
        c = copy.deepcopy(self.card); c["policies"][sp.V2_ID]["policy_source"]["sha256"] = "0" * 64; cases.append(c)
        c = copy.deepcopy(self.card); c["candidate"] = sp.V2_ID; cases.append(c)
        c = copy.deepcopy(self.card); c["budget"]["sprint_session_cap"] = 3; cases.append(c)
        c = copy.deepcopy(self.card); c["games"] = c["games"][::-1]; cases.append(c)
        c = copy.deepcopy(self.card); c["games"][0]["red"] = "inert-v0"; cases.append(c)
        for i, case in enumerate(cases):
            self.assertTrue(sp.card_problems(case, ROOT), i)
        self.assertEqual(sp.card_problems(dict(self.card, card_id="other"), ROOT), ["not the Sprint 27 probe card"])

    def test_frozen_pins_cover_the_candidate_the_rules_the_observer_the_scripts_and_the_tests(self) -> None:
        for rel in ("src/miaosuan_agent/experiments/t6s_column_stagger_p1.py", "src/miaosuan_agent/evaluation/s27_probe.py",
                    "src/miaosuan_agent/evaluation/s27_capture.py", "src/miaosuan_agent/evaluation/s26_t6s.py",
                    "src/miaosuan_agent/evaluation/s18_census.py", "scripts/run_s27_game.py", "scripts/run_s27_probe.py",
                    "scripts/s27_analysis.py", "scripts/build_s27_card.py", "tests/test_t6s_column_stagger_p1.py",
                    "tests/test_s27_probe.py", "tests/fixtures/s27_engine.py"):
            self.assertIn(rel, self.card["screen"]["frozen_files"])
        self.assertEqual(sorted(self.card["screen"]["frozen_files"]), sorted(sp.FROZEN_FILES))

    def test_rules_are_the_registered_values(self) -> None:
        r = sp.RULES
        self.assertEqual((r["max_step"], r["scenario"], r["follow_up_window_steps"]), (2880, "2130511121", 300))
        self.assertEqual(r["p1"]["references"], {"blue": {"HH p01 baseline-v2 blue": 9122, "HH p03 baseline-v2 blue": 29248},
                                                 "red": {"HH p02 baseline-v2 red": 6518, "HH p04 baseline-v2 red": 6489}})
        self.assertEqual(r["expected_opening_divergence_steps"], {"blue": 161, "red": 401})
        for colour, labels in sp.HH_LABELS.items():
            self.assertEqual(sorted(r["p1"]["references"][colour]), sorted(labels))
            self.assertEqual(sorted(r["p2"]["references"][colour]), sorted(sp.OBJECTIVES))
            for steps in r["p2"]["references"][colour].values():
                self.assertEqual(sorted(steps), sorted(labels))  # same-colour references only
        self.assertEqual(r["p2"]["references"]["red"]["80-point objective A"],
                         {"HH p02 baseline-v2 red": None, "HH p04 baseline-v2 red": None})
        self.assertEqual(r["p2"]["references"]["red"]["80-point objective C"],
                         {"HH p02 baseline-v2 red": None, "HH p04 baseline-v2 red": 604})
        self.assertEqual(r["p2"]["references"]["red"]["50-point objective C"],
                         {"HH p02 baseline-v2 red": 2737, "HH p04 baseline-v2 red": 561})
        refs = ROOT / "evaluation" / sp.STUDY_ID / "references.json"
        data = json.loads(refs.read_text(encoding="utf-8"))
        self.assertEqual(data["p1_references"], r["p1"]["references"])
        self.assertEqual(data["p2_references"], r["p2"]["references"])
        self.assertTrue(data["ok"])

    def test_references_follow_the_candidate_colour(self) -> None:
        for game in self.card["games"]:
            colour = sp.candidate_side(game)
            self.assertEqual(sorted(sp.RULES["p1"]["references"][colour]), sorted(sp.HH_LABELS[colour]))
            self.assertTrue(all(label.endswith(colour) for label in sp.RULES["p1"]["references"][colour]))
            for steps in sp.RULES["p2"]["references"][colour].values():
                self.assertTrue(all(label.endswith(colour) for label in steps))

    def test_build_refuses_inconsistent_input(self) -> None:
        shoot = json.loads((ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "manifest.json")
                           .read_text(encoding="utf-8"))
        policies = [{"id": p, "label": v["label"], "policy_source": dict(v["policy_source"])}
                    for p, v in self.card["policies"].items()]
        frozen = dict(self.card["screen"]["frozen_files"])
        self.assertEqual(sp.build_card(shoot, mf.digest(shoot), policies, frozen), self.card)
        with self.assertRaises(ValueError):
            sp.build_card(shoot, mf.digest(shoot), policies[:1], frozen)
        bad = copy.deepcopy(policies)
        bad[0]["policy_source"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            sp.build_card(shoot, mf.digest(shoot), bad, frozen)
        with self.assertRaises(ValueError):
            sp.build_card(shoot, mf.digest(shoot), policies, {k: v for k, v in list(frozen.items())[1:]})


# ------------------------------------------------------------------------------------------------
# ledger


def ledger(card: Dict[str, Any], sessions, base: bool = True) -> List[Dict[str, Any]]:
    """Base session 2796 opened and closed, then each (session, game index or game id, overrides) opened and closed;
    ``overrides`` may set ``open``/``close`` fields or ``no_close``/``recovered``."""
    records = [{"event": "session-open", "session": "2796", "state": "s0"},
               {"event": "session-close", "session": "2796", "state": "s0", "integrity": {"ok": True}}] if base else []
    for session, game, over in sessions:
        game_id = card["games"][game]["game_id"] if isinstance(game, int) else game
        harness = {"game_id": game_id, "card": sp.CARD_ID, "manifest_sha256": mf.digest(card),
                   "policy_source_sha256": sp.CANDIDATE_DIGEST, **over.get("harness", {})}
        records.append({"event": "session-open", "session": f"{session:04d}", "state": over.get("state", "s0"),
                        "harness": harness})
        if over.get("no_close"):
            continue
        event = "session-recovered" if over.get("recovered") else "session-close"
        records.append({"event": event, "session": f"{session:04d}", "state": "s0",
                        "integrity": {"ok": over.get("integrity", True)}})
    return records


class LedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.card = script("build_s27_card").build()

    def audit(self, sessions):
        return sp.ledger_audit(ledger(self.card, sessions), self.card)

    def test_the_registered_sessions_pass(self) -> None:
        for sessions, n in (([], 0), ([(2797, 0, {})], 1), ([(2797, 0, {}), (2798, 1, {})], 2)):
            audit = self.audit(sessions)
            self.assertTrue(audit["ok"], audit["problems"])
            self.assertEqual(audit["sessions"], n)

    def test_every_defect_is_found(self) -> None:
        cases = {
            "S2 wrong game at position one": [(2797, 1, {})],
            "S2 a game outside the card": [(2797, "other.game", {})],
            "S2 another card": [(2797, 0, {"harness": {"card": "other"}})],
            "S2 another card digest": [(2797, 0, {"harness": {"manifest_sha256": "0" * 64}})],
            "S2 another candidate digest": [(2797, 0, {"harness": {"policy_source_sha256": "0" * 64}})],
            "S2 opened twice": [(2797, 0, {}), (2798, 0, {})],
            "S2 the same game opened again in its own session": [(2797, 0, {}), (2797, 0, {"no_close": True})],
            "S2 unclosed": [(2797, 0, {"no_close": True})],
            "S2 recovered": [(2797, 0, {"recovered": True})],
            "S2 a third session": [(2797, 0, {}), (2798, 1, {}), (2799, 1, {})],
            "S2 out of order": [(2798, 1, {})],
            "S1 integrity": [(2797, 0, {"integrity": False})],
            "S1 state chain": [(2797, 0, {"state": "other"})],
        }
        for name, sessions in cases.items():
            audit = self.audit(sessions)
            self.assertFalse(audit["ok"], name)
            self.assertTrue(audit["problems"][name[:2]], (name, audit["problems"]))

    def test_stage_prerequisites(self) -> None:
        none, one, two = self.audit([]), self.audit([(2797, 0, {})]), self.audit([(2797, 0, {}), (2798, 1, {})])
        self.assertIsNone(sp.stage_ledger_problem(none, "A", self.card))
        self.assertIsNotNone(sp.stage_ledger_problem(one, "A", self.card))
        self.assertIsNone(sp.stage_ledger_problem(one, "B", self.card))
        self.assertIsNotNone(sp.stage_ledger_problem(none, "B", self.card))
        self.assertIsNotNone(sp.stage_ledger_problem(two, "B", self.card))
        self.assertIsNotNone(sp.stage_ledger_problem(self.audit([(2797, 0, {"integrity": False})]), "B", self.card))
        self.assertIsNotNone(sp.stage_ledger_problem(none, "C", self.card))

    def test_structural_stop_order(self) -> None:
        self.assertEqual(sp.structural_stops({"SF": ["x"], "S1": ["y"], "S5": ["z"]}), ["S1", "SF"])


# ------------------------------------------------------------------------------------------------
# per-game structural checks


def clean_game():
    entry = sp.games()[0]
    record = {"status": "COMPLETED", "steps": 3, "scenario_id": entry["scenario_id"], "condition": entry["condition"],
              "seats": [{"seat": 1, "faction": 0, "policy": sp.V2_ID, "actions_by_type": {"1": 4}},
                        {"seat": 11, "faction": 1, "policy": sp.CANDIDATE_ID, "actions_by_type": {"1": 2}}],
              "harness": {"game_id": entry["game_id"], "card": sp.CARD_ID, "policy_source_sha256": sp.CANDIDATE_DIGEST,
                          "policy_sources": {sp.V2_ID: sp.V2_DIGEST, sp.CANDIDATE_ID: sp.CANDIDATE_DIGEST}},
              "session_close": {"integrity": {"ok": True}},
              "final_scores": {"blue_win": 5, "blue_total": 10, "red_total": 5, "red_win": -5}}
    t9cap = {"steps": 3, "seats": {"1": {"moves": {"emitted": 2}}}}
    explore = {"steps": 3, "addon_errors": []}
    timeline = {"steps": [{}, {}, {}], "reconstructed_decisions": 6, "consistency_errors": [],
                "unregistered_differences": []}
    return entry, record, t9cap, explore, timeline, 2880, {"t9.json": ("a", "a")}


class GameStopsTest(unittest.TestCase):
    def stops(self, mutate=None):
        parts = list(clean_game())
        if mutate:
            mutate(parts)
        return sp.game_stops(*parts)

    def test_a_clean_game_has_no_stop(self) -> None:
        self.assertEqual(self.stops(), {})

    def test_each_defect_maps_to_its_code(self) -> None:
        def seat(i, **kw):
            return lambda p: p[1]["seats"][i].update(kw)
        cases = [
            ("S1", lambda p: p[1]["session_close"]["integrity"].update(ok=False)),
            ("S4", lambda p: p[1].update(status="FAILED")),
            ("S4", seat(1, contract_errors=1)),
            ("S6", seat(0, replay_mismatches=1)),
            ("S4", lambda p: p[1]["final_scores"].update(blue_win=6)),
            ("S7", seat(0, policy="inert-v0")),
            ("S7", lambda p: p[1].update(seats=[dict(p[1]["seats"][0], faction=1), dict(p[1]["seats"][1], faction=0)])),
            ("S7", lambda p: p[1].update(scenario_id="1930331196")),
            ("S7", lambda p: p[1]["harness"].update(game_id="other")),
            ("S7", lambda p: p[1]["harness"].update(policy_source_sha256="0" * 64)),
            ("S7", lambda p: p[1]["harness"]["policy_sources"].update({sp.V2_ID: "0" * 64})),
            ("S7", lambda p: p[1].update(observer_errors=["x"])),
            ("S7", lambda p: p.__setitem__(6, {"t9.json": ("a", "b")})),
            ("S7", lambda p: p[4].update(consistency_errors=[{"k": 1}])),
            ("S7", lambda p: p[4].update(unregistered_differences=[{"k": 1}])),
            ("S7", lambda p: p[4].update(steps=[{}, {}])),
            ("S7", lambda p: p[4].update(reconstructed_decisions=3)),
            ("S7", lambda p: p[2]["seats"]["1"]["moves"].update(emitted=3)),
            ("S7", lambda p: p[3].update(addon_errors=["x"])),
            ("S7", lambda p: p.__setitem__(5, 2881)),
        ]
        for i, (code, mutate) in enumerate(cases):
            stops = self.stops(mutate)
            self.assertIn(code, stops, (i, stops))


# ------------------------------------------------------------------------------------------------
# registered differences, P1, P2, fidelity, gate, disposition


def mv(obj, first=203):
    return {"actor": 11, "obj_id": obj, "type": 1, "move_path": [first, first + 1]}


class DifferenceTest(unittest.TestCase):
    def test_the_rule_withholding_passes(self) -> None:
        base = [mv(1), mv(2), {"actor": 11, "obj_id": 3, "type": 2, "target_obj_id": 9}, mv(4)]
        self.assertEqual(sp.unregistered_differences(base, base, []), [])
        self.assertEqual(sp.unregistered_differences(base, [base[0], base[2], base[3]], [1]), [])
        self.assertEqual(sp.unregistered_differences(base, [base[0], base[2]], [1, 3]), [])

    def test_unregistered_edits_fail(self) -> None:
        base = [mv(1), mv(2), {"actor": 11, "obj_id": 3, "type": 2, "target_obj_id": 9}]
        cases = [([base[0], base[2]], []),            # a MOVE removed that the rule did not withhold
                 ([base[0], base[1], base[2]], [1]),  # the rule withheld but the live list kept it
                 ([base[0], base[1]], [2]),           # a non-MOVE withheld
                 ([base[2], base[0]], [1]),           # reordered
                 ([base[0], base[2], mv(7)], [1]),    # an added action
                 ([base[0], base[2], base[2]], [1]),  # a duplicated action
                 ([base[0], dict(base[2], target_obj_id=8)], [1]),  # a changed action
                 ([base[0], base[2]], [5])]           # an index outside the list
        for i, (live, withheld) in enumerate(cases):
            self.assertTrue(sp.unregistered_differences(base, live, withheld), i)


class P1Test(unittest.TestCase):
    def test_the_half_mean_boundary_is_exact(self) -> None:
        self.assertFalse(sp.p1(10, {"a": 10, "b": 30})["triggered"])      # equal to half of the mean 20
        self.assertTrue(sp.p1(11, {"a": 10, "b": 30})["triggered"])
        self.assertFalse(sp.p1(0, {"a": 10, "b": 30})["triggered"])

    def test_the_registered_references(self) -> None:
        blue, red = sp.RULES["p1"]["references"]["blue"], sp.RULES["p1"]["references"]["red"]
        self.assertEqual((sp.p1(9592, blue)["triggered"], sp.p1(9593, blue)["triggered"]), (False, True))
        self.assertEqual((sp.p1(3251, red)["triggered"], sp.p1(3252, red)["triggered"]), (False, True))
        out = sp.p1(9593, blue)
        self.assertEqual((out["reference_sum"], out["reference_mean"], out["half_reference_mean"]),
                         (38370, 19185, "19185/2"))
        self.assertEqual(sp.p1(3252, red)["half_reference_mean"], "13007/4")
        self.assertEqual(sp.p1(5000, red)["absolute_change_from_reference_mean"], "-3007/2")

    def test_two_integer_references_only(self) -> None:
        for refs in ({"a": 1}, {"a": 1, "b": 2, "c": 3}, {"a": 1.0, "b": 2}, {"a": True, "b": 2}):
            with self.assertRaises(ValueError):
                sp.p1(1, refs)


class P2Test(unittest.TestCase):
    REFS = {"A": {"x": 100, "y": 120}, "B": {"x": None, "y": 50}, "C": {"x": None, "y": None}}

    def run_p2(self, a, b, c):
        return sp.p2({"A": a, "B": b, "C": c}, self.REFS)

    def test_latest_finite_reference_and_equality(self) -> None:
        out = self.run_p2(120, 50, 7)
        self.assertFalse(out["triggered"])
        rows = {r["objective"]: r for r in out["rows"]}
        self.assertEqual((rows["A"]["reference_step"], rows["B"]["reference_step"], rows["C"]["reference_step"]),
                         (120, 50, None))
        self.assertEqual(rows["A"]["differences_from_each_reference"], {"x": 20, "y": 0})
        self.assertEqual(rows["B"]["differences_from_each_reference"], {"x": None, "y": 0})
        self.assertEqual(out["objectives_without_reference"], ["C"])
        self.assertTrue(self.run_p2(121, 50, 7)["triggered"])
        self.assertTrue(self.run_p2(100, 51, 7)["triggered"])
        self.assertFalse(self.run_p2(100, 49, None)["triggered"])

    def test_never_first_owned(self) -> None:
        out = self.run_p2(None, 50, None)
        self.assertTrue(out["triggered"])
        self.assertEqual({r["objective"]: r["status"] for r in out["rows"]},
                         {"A": "never first-owned", "B": "at or before the reference",
                          "C": "no historical timing reference"})
        self.assertTrue(self.run_p2(100, None, None)["triggered"])

    def test_objectives_must_match(self) -> None:
        with self.assertRaises(ValueError):
            sp.p2({"A": 1, "B": 1}, self.REFS)

    def test_registered_same_colour_references(self) -> None:
        blue, red = sp.RULES["p2"]["references"]["blue"], sp.RULES["p2"]["references"]["red"]
        ok_blue = {obj: max(v for v in steps.values() if v is not None) for obj, steps in blue.items()}
        self.assertFalse(sp.p2(ok_blue, blue)["triggered"])
        self.assertTrue(sp.p2(dict(ok_blue, **{"80-point objective C": 162}), blue)["triggered"])
        red_first = {obj: (max((v for v in steps.values() if v is not None), default=None)) for obj, steps in red.items()}
        out = sp.p2(red_first, red)
        self.assertFalse(out["triggered"])
        self.assertEqual(out["objectives_without_reference"], ["80-point objective A"])
        rows = {r["objective"]: r for r in out["rows"]}
        self.assertEqual((rows["50-point objective C"]["reference_step"], rows["80-point objective C"]["reference_step"]),
                         (2737, 604))
        self.assertTrue(sp.p2(dict(red_first, **{"80-point objective C": None}), red)["triggered"])
        self.assertFalse(sp.p2(dict(red_first, **{"80-point objective A": None}), red)["triggered"])
        four = {obj: {**blue[obj], **red[obj]} for obj in sp.OBJECTIVES}
        sens = sp.p2_sensitivity(dict(ok_blue, **{"50-point objective A": 300}), four)
        self.assertFalse(sens["triggered"])  # 300 is before red's 421 although after blue's 161
        self.assertIn("not a stop", sens["note"])


def good_fidelity():
    return {"one_snapshot_per_decision": True, "decisions": 10, "frozen_rule_equal_decisions": 10,
            "frozen_rule_events_equal": True, "candidate_equals_baseline_v2_before_the_first_withholding": True,
            **{k: 0 for k in sp.FIDELITY_ZERO}}


class FidelityTest(unittest.TestCase):
    def test_every_clause(self) -> None:
        self.assertEqual(sp.fidelity_problems(good_fidelity()), [])
        changes = [{"one_snapshot_per_decision": False}, {"frozen_rule_equal_decisions": 9}, {"decisions": 0,
                   "frozen_rule_equal_decisions": 0}, {"frozen_rule_events_equal": False},
                   {"candidate_equals_baseline_v2_before_the_first_withholding": False}]
        changes += [{k: 1} for k in sp.FIDELITY_ZERO] + [{k: None} for k in sp.FIDELITY_ZERO]
        for change in changes:
            self.assertEqual(len(sp.fidelity_problems(dict(good_fidelity(), **change))), 1, change)


class GateAndDispositionTest(unittest.TestCase):
    OK = {"structural_stops": [], "completed": True, "mechanism_observed": True, "p1_triggered": False,
          "p2_triggered": False}

    def s(self, **kw):
        return dict(self.OK, **kw)

    def test_mechanism_rule(self) -> None:
        self.assertFalse(sp.mechanism_observed([]))
        self.assertFalse(sp.mechanism_observed([{"executed": False}, {"executed": False}]))
        self.assertTrue(sp.mechanism_observed([{"executed": False}, {"executed": True}]))

    def test_stage_gate(self) -> None:
        self.assertEqual(sp.stage_gate([], True, {"triggered": False}, {"triggered": False}, True),
                         {"stage_b_authorized": True, "reasons": []})
        for args in ((["S7"], True, {"triggered": False}, {"triggered": False}, True),
                     ([], False, {"triggered": False}, {"triggered": False}, True),
                     ([], True, {"triggered": True}, {"triggered": False}, True),
                     ([], True, {"triggered": False}, {"triggered": True}, True),
                     ([], True, {"triggered": False}, {"triggered": False}, False)):
            gate = sp.stage_gate(*args)
            self.assertFalse(gate["stage_b_authorized"], args)
            self.assertEqual(len(gate["reasons"]), 1, args)

    def test_disposition_order(self) -> None:
        d = sp.disposition
        self.assertEqual(d([self.OK, self.OK], True, True)["disposition"], sp.SUPPORTED)
        self.assertFalse(d([self.OK, self.OK], True, True)["paired_probe_terminated_early"])
        cases = [
            (([self.s(structural_stops=["S7"])], False, False), sp.INVALID, True),
            (([self.s(completed=False)], False, False), sp.INVALID, True),
            (([self.OK], True, False), sp.INVALID, True),
            (([self.OK], True, False), "stage B was authorized but not run", True),
            (([self.OK], True, True), sp.INVALID, True),
            (([self.OK], False, False), sp.INVALID, True),
            (([], False, False), sp.INVALID, False),
            (([self.OK, self.OK, self.OK], True, True), sp.INVALID, False),
            (([self.s(mechanism_observed=False)], False, False), sp.NOT_OBSERVED, True),
            (([self.s(p1_triggered=True)], False, False), sp.NOT_SUPPORTED, True),
            (([self.s(p2_triggered=True)], False, False), sp.NOT_SUPPORTED, True),
            (([self.s(mechanism_observed=False, p1_triggered=True)], False, False), sp.NOT_OBSERVED, True),
            (([self.s(structural_stops=["SF"], mechanism_observed=False)], False, False), sp.INVALID, True),
            (([self.OK, self.s(mechanism_observed=False)], True, True), sp.NOT_OBSERVED, False),
            (([self.OK, self.s(p2_triggered=True)], True, True), sp.NOT_SUPPORTED, False),
            (([self.OK, self.s(structural_stops=["S4"])], True, True), sp.INVALID, False),
        ]
        for i, ((sessions, authorized, opened), expected, early) in enumerate(cases):
            out = d(sessions, authorized, opened)
            if expected not in sp.DISPOSITIONS:
                self.assertIn(expected, out.get("problems", []), i)
                continue
            self.assertEqual(out["disposition"], expected, i)
            self.assertEqual(out["paired_probe_terminated_early"], early, i)
            self.assertEqual(out["order"], list(sp.DISPOSITIONS))


class PublicTest(unittest.TestCase):
    def test_the_sanitizer(self) -> None:
        clean = {"objective": "80-point objective A", "steps": [161, 2079], "scenario": "2130511121 blue", "e4": 2079}
        self.assertEqual(sp.public_problems(clean, {2079, 970001}), [])  # numeric leaves are masked
        self.assertTrue(sp.public_problems(dict(clean, note="unit 970001"), {970001}))   # a private value as a word
        self.assertTrue(sp.public_problems(dict(clean, **{"2079": 1}), {2079}))           # a private value as a key
        self.assertTrue(sp.public_problems(dict(clean, note="after 20 steps"), ()))        # a digit-only word
        self.assertTrue(sp.public_problems(dict(clean, obj_id=5), ()))                    # a forbidden key
        self.assertTrue(sp.public_problems(dict(clean, note="1930331196 red"), ()))        # another scenario
        self.assertEqual(sp.public_problems(dict(clean, note="1930331196 red"), (), ("2130511121", "1930331196")), [])
        self.assertEqual(sp.digit_words({"a b": ["12 x", "x12", "2130511121"]}, ("2130511121",)), ["12"])


# ------------------------------------------------------------------------------------------------
# observer and the real game loop in the stand-in world


COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")


def play_direct(steps: int, **options):
    """Drive the stand-in with the two agents directly; return the decision records of both seats per step."""
    env = se.StaggerEnv(play_steps=steps, **options)
    state = env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
    blue, red = cand.StaggerAgent(), ShootReservationAgent()
    blue.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
    red.setup({"seat": 1, "faction": se.RED, "cost_data": syn.cost_data()})
    out = []
    done = False
    while not done:
        row = []
        actions = []
        for agent, seat, faction, policy in ((red, 1, se.RED, sp.V2_ID), (blue, 11, se.BLUE, sp.CANDIDATE_ID)):
            raw = copy.deepcopy(state[faction])
            memory = agent.memory
            emitted = [dict(a) for a in agent.step(copy.deepcopy(raw))]
            row.append({"observation": raw, "memory": memory, "trace": agent.last_trace,
                        "submitted": copy.deepcopy(emitted), "seat": seat, "faction": faction, "policy": policy})
            actions.extend(emitted)
        out.append(row)
        state, done = env.step(actions)
    return out


class ObserverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = play_direct(160)

    def test_reconstruction_and_memory_chains_agree_with_the_live_agents(self) -> None:
        expected, expected_v2 = (Memory(), ()), Memory()
        withheld = 0
        for row in self.rows:
            red, blue = row
            rebuilt = cap.reconstruct(blue["observation"], 11, se.BLUE, blue["memory"], COSTS)
            self.assertTrue(all(cap.consistency(blue, rebuilt, expected).values()))
            self.assertEqual(sp.unregistered_differences(rebuilt["baseline_actions"], blue["submitted"],
                                                         rebuilt["withheld"]), [])
            expected = (rebuilt["baseline_memory_out"], rebuilt["memory_out"])
            withheld += len(rebuilt["withheld"])
            orebuilt = cap.reconstruct_v2(red["observation"], 1, se.RED, red["memory"], COSTS)
            self.assertTrue(all(cap.consistency_v2(red, orebuilt, expected_v2).values()))
            expected_v2 = orebuilt["memory_out"]
        self.assertGreater(withheld, 0)

    def test_tampering_is_detected(self) -> None:
        first, second = self.rows[1][1], self.rows[2][1]
        previous = cap.reconstruct(first["observation"], 11, se.BLUE, first["memory"], COSTS)
        rebuilt = cap.reconstruct(second["observation"], 11, se.BLUE, second["memory"], COSTS)
        expected = (previous["baseline_memory_out"], previous["memory_out"])
        self.assertTrue(all(cap.consistency(second, rebuilt, expected).values()))
        self.assertFalse(cap.consistency(dict(second, memory=AddonMemory(second["memory"].baseline, ())), rebuilt,
                                         expected)["addon_memory"])
        extra = [{"actor": 11, "obj_id": se.T2, "type": 1, "move_path": [203]}]
        self.assertFalse(cap.consistency(dict(second, submitted=list(second["submitted"]) + extra), rebuilt,
                                         expected)["actions"])
        self.assertFalse(cap.consistency(second, rebuilt, (Memory(), ()))["addon_memory"])
        red = self.rows[2][0]
        orebuilt = cap.reconstruct_v2(red["observation"], 1, se.RED, red["memory"], COSTS)
        self.assertTrue(all(cap.consistency_v2(red, orebuilt, red["memory"]).values()))
        self.assertFalse(cap.consistency_v2(dict(red, policy="inert-v0"), orebuilt, red["memory"])["policy"])
        self.assertFalse(cap.consistency_v2(dict(red, memory="tampered"), orebuilt, red["memory"])["memory"])


class Played:
    def __init__(self, **options) -> None:
        from miaosuan_agent.evaluation.game import play
        from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
        steps = options.pop("play_steps", 700)
        spec = GameSpec(game_id="synthetic.H2.s27", scenario_id="900000001", map_id="9000", condition="H2",
                        red=sp.V2_ID, blue=sp.CANDIDATE_ID, repetition=1, max_time=steps)
        timeline = cap.StaggerTimeline((sp.V2_ID, sp.CANDIDATE_ID), COSTS)
        ticks = itertools.count()
        factories = {sp.V2_ID: lambda: ShootReservationAgent(), sp.CANDIDATE_ID: lambda: cand.StaggerAgent()}
        self.record = play(lambda: se.StaggerEnv(play_steps=steps, **options), factories, spec, se.Inputs, PLAYERS,
                           clock=lambda: next(ticks) * 0.001, replay_policies={sp.V2_ID, sp.CANDIDATE_ID},
                           observer=tc.Tee(tc.T9Capture(), xp.ExploreCapture((sp.CANDIDATE_ID, sp.V2_ID)), timeline))
        compact, windows = timeline.files()
        self.compact, windows = json.loads(compact), pickle.loads(windows)
        samples = sorted(windows["samples"], key=lambda s: s["k"])
        steps_ = self.compact["steps"]
        raws = [pickle.loads(s["seats"][11]["observation"]) for s in samples]
        self.live = [[a["action"] for a in step["submitted"] if a["seat"] == 11] for step in steps_]
        self.baseline = [step["s27"]["11"]["baseline_actions"] for step in steps_]
        feedback = [[f for f in step["feedback"] if (f.get("message") or {}).get("actor") == 11] for step in steps_]
        self.frames = [sc.frame_from_raw(k, raw, se.BLUE, self.baseline[k]) for k, raw in enumerate(raws)]
        collector = sc.EventCollector()
        for k, sample in enumerate(samples):
            collector.add(k, pickle.loads(sample["global"]).get("judge_info") or [])
        values = {c["coord"]: c["value"] for c in raws[0]["cities"]}
        self.names = st.objective_labels(values)
        travel = cand.router_travel(Router(COSTS))
        self.side = st.Side("S27", "stand-in", "synthetic", "900000001", se.BLUE, self.frames, self.live,
                            collector.events, travel, values)
        self.run = st.run_shadow(self.side)
        checker = st.IndependentCheck(travel)
        self.unexplained = [p for k, f in enumerate(self.frames) if f.stage == 2 for p in checker.step(f, self.live[k])]
        self.episodes = [sp.episode_facts(self.frames, row, self.live, feedback, st.damage_steps(self.side),
                                          sc.lost_units(self.frames), self.names, se.BLUE) for row in self.run.episodes]
        rule_events = [step["s27"]["11"]["events"] for step in steps_]
        shadow_events = [[] for _ in self.frames]
        for k, e in self.run.events:
            shadow_events[k].append([e.kind, e.eid, e.unit, e.step, e.index, e.reason, e.moved])
        self.events_equal = shadow_events == rule_events


class StandInGameTest(unittest.TestCase):
    """The real game loop (``evaluation.game.play``) with the Sprint 27 observers in the stand-in world: the live
    reconstruction, the memory chains and the difference check hold at every decision of both seats; Sprint 26's frozen
    rule, replayed on the live trajectory through Sprint 26's own ``run_shadow``, emits exactly the live lists; Sprint
    26's independent check finds nothing unexplained; the episode facts reach the registered mechanism outcomes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.default = Played()

    def test_fidelity_through_the_real_game_loop(self) -> None:
        p = self.default
        self.assertEqual(p.record["status"], "COMPLETED")
        self.assertEqual(p.record.get("observer_errors"), [])
        self.assertEqual(p.compact["reconstructed_decisions"], 2 * len(p.compact["steps"]))
        self.assertEqual((p.compact["consistency_errors"], p.compact["unregistered_differences"]), ([], []))
        self.assertEqual([[dict(a) for a in c] for c in p.run.candidate], p.live)
        self.assertEqual(p.unexplained, [])
        self.assertTrue(p.events_equal)
        self.assertEqual(p.run.first_divergence, 1)
        self.assertTrue(all(p.live[k] == p.baseline[k] for k in range(p.run.first_divergence)))

    def test_an_executed_episode_observes_the_mechanism(self) -> None:
        first = self.default.episodes[0]
        self.assertTrue(first["completed"] and first["executed"])
        self.assertEqual((first["group_size"], first["followers_withheld_at_start"], first["leader_move_accepted"]),
                         (3, 2, True))
        self.assertEqual([f["release_reason"] for f in first["followers"]], ["reference_left", "reference_left"])
        self.assertEqual([f["wait_steps"] for f in first["followers"]], [20, 40])
        self.assertEqual([f["departure_steps"] for f in first["followers"]], [40, 60])
        self.assertEqual(first["leader_departure_steps"], 20)
        self.assertEqual([f["separation_from_leader_at_departure_hexes"] for f in first["followers"]], [1, 2])
        self.assertTrue(all(f["release_move_accepted"] for f in first["followers"]))
        # the leader pauses on the objective and moves on; the first follower catches it up on the next hex
        self.assertTrue(first["co_located_moving_beyond_start"])
        self.assertEqual(first["first_co_location_beyond_start_steps"], 140)
        self.assertEqual([f["destination"] for f in first["followers"]], ["80-point objective A"] * 2)
        self.assertTrue(first["followers"][0]["destination_first_owned_after_start"])
        self.assertTrue(first["followers"][0]["leader_among_first_owners"])
        self.assertFalse(first["followers"][0]["follower_among_first_owners"])
        self.assertEqual([f["arrival_lag_behind_leader_steps"] for f in first["followers"]], [20, 40])
        self.assertTrue(sp.mechanism_observed(self.default.episodes))

    def test_a_follower_lost_while_waiting(self) -> None:
        p = Played(remove={se.T2: 5})
        first = p.episodes[0]
        lost, other = first["followers"]
        self.assertEqual((lost["outcome"], lost["destroyed_before_departure"], lost["departed"]),
                         ("left the queue, follower_absent", True, False))
        self.assertTrue(other["departed_after_release"])
        self.assertTrue(first["executed"])
        self.assertTrue(p.events_equal)
        self.assertEqual(p.unexplained, [])

    def test_a_blocked_leader_is_released_by_the_wait_bound_and_not_executed(self) -> None:
        p = Played(block=4, play_steps=200)
        first = p.episodes[0]
        self.assertEqual([f["release_reason"] for f in first["followers"]], ["timeout", "timeout"])
        self.assertEqual([f["wait_steps"] for f in first["followers"]], [51, 51])
        self.assertFalse(first["executed"])
        self.assertFalse(sp.mechanism_observed(p.episodes))
        self.assertFalse(first["co_located_moving_beyond_start"])  # every member is stuck on the start hex
        self.assertEqual(p.unexplained, [])
        self.assertTrue(p.events_equal)

    def test_a_lost_leader_releases_by_reference_absent_and_is_not_executed(self) -> None:
        p = Played(n_blue=2, remove={se.T1: 5}, play_steps=200)
        first = p.episodes[0]
        (follower,) = first["followers"]
        self.assertEqual((follower["release_reason"], follower["departed_after_release"]), ("reference_absent", True))
        self.assertTrue(first["completed"])
        self.assertFalse(first["executed"])
        self.assertTrue(first["leader_absent_before_departure"])

    def test_an_episode_open_at_the_end_is_not_executed(self) -> None:
        p = Played(n_blue=4, play_steps=50)
        first = p.episodes[0]
        self.assertEqual(first["end"], "open_at_end")
        self.assertEqual(first["followers"][0]["release_reason"], "reference_left")
        self.assertTrue(first["followers"][0]["departed_after_release"])
        self.assertEqual(first["followers"][2]["outcome"], "pending at the end")
        self.assertFalse(first["executed"])

    def test_a_refused_leader_move(self) -> None:
        p = Played(refuse=(1,), play_steps=200)
        first = p.episodes[0]
        self.assertIs(first["leader_move_accepted"], False)
        self.assertFalse(first["executed"])
        self.assertEqual(p.compact["unregistered_differences"], [])


# ------------------------------------------------------------------------------------------------
# runner: the committed stage-A gate


class CommittedGateTest(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       check=True, capture_output=True)

    def test_the_gate_must_be_committed_unchanged_and_authorize(self) -> None:
        game = script("run_s27_game")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self.git(repo, "init", "-q")
            path = game.gate_file(1, repo)
            self.assertIn("missing", game.committed_gate(repo))
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"stage_gate": {"stage_b_authorized": True}}), encoding="utf-8")
            self.assertIn("not committed", game.committed_gate(repo))
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-q", "-m", "gate")
            self.assertEqual(game.committed_gate(repo), "")
            path.write_text(json.dumps({"stage_gate": {"stage_b_authorized": True}, "x": 1}), encoding="utf-8")
            self.assertIn("differs", game.committed_gate(repo))
            path.write_text(json.dumps({"stage_gate": {"stage_b_authorized": False, "reasons": ["P1"]}}),
                            encoding="utf-8")
            self.git(repo, "commit", "-q", "-am", "refused")
            self.assertIn("does not authorize", game.committed_gate(repo))


# ------------------------------------------------------------------------------------------------
# whitelist


class WhitelistTest(unittest.TestCase):
    def test_candidate_occurs_only_in_the_approved_sprint27_card(self) -> None:
        """Owner-approved narrow authorization (Sprint 27, 2026-10-09): the identity ``t6s-column-stagger-p1`` may
        appear in exactly one run card, ``s27-t6s-probe-1``, bound to the registered digest; any other JSON naming it
        lies in ``evaluation/s27-t6s-probe/`` and is never executable; only the Sprint 27 scripts and modules import the
        module. A changed source is a new identity that needs new approval."""
        cards = 0
        for path in sorted((ROOT / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if sp.CANDIDATE_ID not in text and sp.CANDIDATE_DIGEST not in text:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = json.loads(text)
            if isinstance(data, dict) and (xp.is_card(data) or path.name == "manifest.json"):
                cards += 1
                self.assertEqual(rel, f"evaluation/{sp.CARD_ID}/manifest.json")
                self.assertEqual(data["policies"][sp.CANDIDATE_ID]["policy_source"]["sha256"], sp.CANDIDATE_DIGEST)
                self.assertIn("experiments/t6s_column_stagger_p1.py",
                              data["policies"][sp.CANDIDATE_ID]["policy_source"]["files"])
                continue
            self.assertTrue(rel.startswith(f"evaluation/{sp.STUDY_ID}/"), rel)
            self.assertFalse(isinstance(data, dict) and data.get("executable"), rel)
        self.assertEqual(cards, 1)
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "run_evaluation.py",
                     "run_s22_game.py", "build_s22_card.py", "run_s17_game.py", "build_s17_card.py"):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn("t6s_column_stagger_p1", text, name)
            self.assertNotIn(sp.CANDIDATE_ID, text, name)
        users = sorted(p.relative_to(ROOT).as_posix() for folder in ("src", "scripts")
                       for p in (ROOT / folder).rglob("*.py")
                       if "t6s_column_stagger_p1" in p.read_text(encoding="utf-8")
                       and p.name != "t6s_column_stagger_p1.py")
        self.assertEqual(users, ["scripts/build_s27_card.py", "scripts/mutate_s27.py", "scripts/run_s27_game.py",
                                 "scripts/s27_analysis.py", "src/miaosuan_agent/evaluation/s27_capture.py",
                                 "src/miaosuan_agent/evaluation/s27_probe.py"])

    def test_no_sprint27_file_names_sprint26s_shadow(self) -> None:
        needle = "t6s_stagger" + "_shadow"
        for rel in ("src/miaosuan_agent/experiments/t6s_column_stagger_p1.py", "src/miaosuan_agent/evaluation/s27_probe.py",
                    "src/miaosuan_agent/evaluation/s27_capture.py", "scripts/build_s27_card.py",
                    "scripts/run_s27_game.py", "scripts/run_s27_probe.py", "scripts/s27_analysis.py",
                    "scripts/mutate_s27.py", "tests/test_t6s_column_stagger_p1.py", "tests/test_s27_probe.py",
                    "tests/fixtures/s27_engine.py"):
            self.assertNotIn(needle, (ROOT / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    unittest.main()
