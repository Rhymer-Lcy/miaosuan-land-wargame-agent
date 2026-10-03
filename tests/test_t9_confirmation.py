"""Tests of the T9 confirmatory study's design, capture, estimands, checks, gates and disposition.

SYNTHETIC: every record, capture, ledger and game here is invented (or played on the PS-1 stand-in engine); nothing
reads private material. ``FullScheduleDryRun`` writes synthetic records for all 375 registered games and runs the
registered analysis of every phase over them, as the study will run it.
"""

from __future__ import annotations

import collections
import hashlib
import importlib.util
import itertools
import json
import math
import random
import statistics
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
from miaosuan_agent.experiments.t9_allocation import CANDIDATE_ID as T9_ID, AllocationAgent

from tests.fixtures import ps1_probe_engine as pe

REPO = Path(__file__).resolve().parents[1]
FAST = 400  # resamples in tests; the registered count is 20,000


def load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"t9test_{name}", REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------
# Synthetic records


def seat_facts(policy: str, never_departed: int = 0, held_at_end: int = 1, withheld: int = 0) -> Dict[str, Any]:
    return {"policy": policy,
            "moves": {"emitted": 10, "emitted_ground": 10, "kept": 8, "replaced": 2, "reverted": 0, "redirected": 2,
                      "withheld": withheld, "unreadable_destination": 0, "replaced_refused": {}, "addon_errors": 0},
            "withholding": {"units": 1 if withheld else 0, "unit_decisions": withheld, "longest_run_max": withheld,
                            "longest_run_median": withheld},
            "start_positions": {"ground_units": 6, "never_departed": never_departed, "departed": 6 - never_departed,
                                "embarked": 0, "removed_before_leaving": 0, "idle_unit_steps": 30,
                                "idle_steps_median": 5, "idle_steps_max": 9, "units_idle_half_play": 0},
            "waiting_in_front_of_full_hex": {"max": 0, "sum": 0, "steps_positive": 0},
            "max_objective_commitment": {"max": 4, "sum": 40, "steps_positive": 10},
            "objectives": {"count": 3, "held_steps": 20, "held_value_steps": 200, "mean_held": 1.0, "max_held": 2,
                           "held_at_end": held_at_end, "held_value_at_end": 50 * held_at_end, "ever_held": 2,
                           "first_hold_step_min": 3},
            "losses": {"start_units": 8, "lost": 1}}


def synthetic_game(entry: Dict[str, Any], manifest: Dict[str, Any], digest: str, session: str, red_margin: int,
                   *, status: str = "COMPLETED", candidate_classes=(), contract_errors: int = 0,
                   never_departed: int = 0, latency_us: Optional[List[int]] = None,
                   gate_rejections=()) -> Dict[str, Any]:
    """(record, t9 capture bytes, explore capture bytes) for one scheduled game."""
    seats, captured, steps = [], {}, 100
    for faction, policy in ((0, entry["red"]), (1, entry["blue"])):
        seat = {"seat": 1 if faction == 0 else 11, "faction": faction, "policy": policy, "actions_by_type": {"1": 10},
                "contract_errors": contract_errors if policy == tc.CANDIDATE_ID else 0,
                "gate_rejections": dict(gate_rejections) if policy == tc.CANDIDATE_ID else {},
                "replay_checks": 5, "replay_mismatches": 0,
                "refusal_facts": ([{"action_type": a, "code": c, "message_class": m, "count": 1}
                                   for a, c, m in candidate_classes] if policy == tc.CANDIDATE_ID else []),
                "latency_us": latency_us if latency_us is not None else [400, 500, 600, 1200]}
        seats.append(seat)
        if policy != INERT_ID:
            captured[str(faction)] = seat_facts(policy, never_departed if policy == tc.CANDIDATE_ID else 0)
    series = {"waiting": {"max": 1, "sum": 3, "steps_positive": 2}, "commitment_max": {"max": 4, "sum": 40,
                                                                                     "steps_positive": 10}}
    t9 = {"schema": tc.CAPTURE_SCHEMA, "steps": steps, "play_steps": steps - 1, "first_play_step": 0,
          "seats": captured, "series_checks": {"0": series, "1": series}, "addon_changes": {}, "addon_skips": {}}
    explore = {"waiting_ground_units": {"0": series["waiting"], "1": series["waiting"]},
               "max_objective_commitment": {"0": series["commitment_max"], "1": series["commitment_max"]},
               "addon_changes": {}, "addon_skips": {}}
    t9_bytes = json.dumps(t9, sort_keys=True).encode("utf-8") + b"\n"
    explore_bytes = json.dumps(explore, sort_keys=True).encode("utf-8") + b"\n"
    red_total = 500 + red_margin
    scores = {"red_total": red_total, "blue_total": 500, "red_win": red_margin, "blue_win": -red_margin}
    sources = {p: manifest["policies"][p]["policy_source"]["sha256"] for p in {entry["red"], entry["blue"]} - {INERT_ID}}
    record = {"status": status, "completion": "done" if status == "COMPLETED" else "step_cap", "steps": steps,
              "session": session, "timings_seconds": {"wall": 60.0}, "observer_errors": [], "final_scores": scores,
              "policies": {"red": entry["red"], "blue": entry["blue"]}, "seats": seats,
              "harness": {"manifest_sha256": digest, "dirty": False, "study": tc.STUDY_ID,
                          "policy_sources": dict(sorted(sources.items())), "runtime": tc.RUNTIME,
                          "thread_env": {"OPENBLAS_NUM_THREADS": "1"},
                          "execution": {"mode": "shared", "workers": tc.WORKERS, "worker": 1, "batch": 1,
                                        "scheduler": manifest["execution"]["scheduler"]}},
              "engine_version": "4.1.0", "python": "3.10.20", "session_close": {"integrity": {"ok": True}},
              "capture": {"t9_sha256": hashlib.sha256(t9_bytes).hexdigest(),
                          "explore_sha256": hashlib.sha256(explore_bytes).hexdigest()}}
    return record, t9_bytes, explore_bytes


def facts_of(entry, manifest, red_margin, **kw) -> Dict[str, Any]:
    record, t9_bytes, explore_bytes = synthetic_game(entry, manifest, "d" * 64, "3000", red_margin, **kw)
    return tc.game_facts(entry, record, json.loads(t9_bytes), json.loads(explore_bytes))


def ledger_for(games: List[str], digest: str, start: int = tc.LEDGER_BASE_SESSION + 1) -> List[Dict[str, Any]]:
    ledger = [{"event": "session-close", "session": f"{tc.LEDGER_BASE_SESSION:04d}", "state": {"s": "x"},
               "integrity": {"ok": True}}]
    for n, game in enumerate(games, start=start):
        ledger.append({"event": "session-open", "session": f"{n:04d}", "state": {"s": "x"},
                       "harness": {"manifest_sha256": digest, "game_id": game}})
        ledger.append({"event": "session-close", "session": f"{n:04d}", "state": {"s": "x"},
                       "integrity": {"ok": True}})
    return ledger


def mini_manifest() -> Dict[str, Any]:
    """The design parts of a manifest (no committed files needed)."""
    games = tc.schedule("0" * 64)
    return {"games": games, "execution": {"scheduler": "miaosuan-game-pool/1@synthetic"},
            "policies": {tc.V2_ID: {"policy_source": {"sha256": tc.V2_DIGEST}},
                         tc.CANDIDATE_ID: {"policy_source": {"sha256": tc.CANDIDATE_DIGEST}}}}


def phase_facts(manifest, phase: str, margin_of, **kw) -> List[Dict[str, Any]]:
    return [facts_of(e, manifest, margin_of(e), **kw) for e in tc.phase_games(manifest, phase)]


def h2h_margin(effect: float, rng: random.Random, sd: float = 100.0):
    """Red margin of a head-to-head game: the scenario's red bias -800, the candidate's effect on its seat."""
    def margin(entry):
        noise = rng.gauss(0, sd)
        if entry["cell"] == "H1":
            return round(-800 + effect + noise)
        if entry["cell"] == "H2":
            return round(-800 - effect + noise)
        return round(-800 + noise)
    return margin


# ------------------------------------------------------------------------------------------------


class DesignTest(unittest.TestCase):
    def setUp(self) -> None:
        self.games = tc.schedule("a" * 64)

    def test_phase_sizes_and_the_cap(self) -> None:
        counts = collections.Counter(g["phase"] for g in self.games)
        self.assertEqual(counts, {"A": 45, "D": 60, "B": 180, "C": 90})
        self.assertEqual(len(self.games), tc.SESSION_CAP)
        self.assertEqual([g["position"] for g in self.games], list(range(1, 376)))
        self.assertEqual(len({g["game_id"] for g in self.games}), 375)
        self.assertEqual([g["phase"] for g in self.games], sorted((g["phase"] for g in self.games),
                                                                  key=tc.PHASE_ORDER.index))

    def test_every_round_plays_every_cell_once(self) -> None:
        for phase in tc.PHASE_ORDER:
            rounds = collections.defaultdict(list)
            for g in self.games:
                if g["phase"] == phase:
                    rounds[g["repetition"]].append((g["scenario_id"], g["cell"]))
            self.assertEqual(len(rounds), tc.PHASES[phase]["repetitions"])
            for cells in rounds.values():
                self.assertEqual(sorted(cells), sorted(tc.cells(phase)))

    def test_phase_a_positions_are_exactly_balanced(self) -> None:
        a = [g for g in self.games if g["phase"] == "A"]
        positions = collections.Counter((g["cell"], (g["phase_position"] - 1) % 3) for g in a)
        self.assertEqual(set(positions.values()), {5})
        self.assertEqual(len(positions), 9)

    def test_the_schedule_depends_only_on_the_design(self) -> None:
        self.assertEqual(tc.schedule("a" * 64), self.games)
        self.assertNotEqual([g["game_id"] for g in tc.schedule("b" * 64)], [g["game_id"] for g in self.games])

    def test_players(self) -> None:
        self.assertEqual(tc.cell_players("H1"), (tc.CANDIDATE_ID, tc.V2_ID))
        self.assertEqual(tc.cell_players("H2"), (tc.V2_ID, tc.CANDIDATE_ID))
        self.assertEqual(tc.cell_players("C1"), (tc.V2_ID, tc.V2_ID))
        self.assertEqual(tc.cell_players("C2-T9"), (tc.CANDIDATE_ID, INERT_ID))
        self.assertEqual(tc.cell_players("C3-T9"), (INERT_ID, tc.CANDIDATE_ID))
        self.assertEqual(tc.cell_players("C2-V2"), (tc.V2_ID, INERT_ID))
        self.assertEqual(tc.cell_players("C3-V2"), (INERT_ID, tc.V2_ID))
        for g in self.games:
            self.assertEqual((g["red"], g["blue"]), tc.cell_players(g["cell"]))

    def test_phase_scenarios(self) -> None:
        by_phase = collections.defaultdict(set)
        for g in self.games:
            by_phase[g["phase"]].add(g["scenario_id"])
        self.assertEqual(by_phase["A"], {"2130511121"})
        self.assertEqual(by_phase["D"], set(tc.SMALL))
        self.assertEqual(by_phase["B"], set(tc.LARGE))
        self.assertEqual(by_phase["C"], {"2120531121", "1930331196"})


class MarginTest(unittest.TestCase):
    def test_margin_convention(self) -> None:
        scores = {"red_total": 491, "blue_total": 1112, "red_win": -621, "blue_win": 621}
        self.assertEqual(tc.seat_margin(scores, 0), -621)
        self.assertEqual(tc.seat_margin(scores, 1), 621)
        self.assertTrue(tc.margin_identity(scores))
        self.assertFalse(tc.margin_identity({**scores, "blue_win": 620}))
        self.assertFalse(tc.margin_identity({"red_total": 1, "blue_total": 0}))


class ContrastTest(unittest.TestCase):
    def test_point_estimate_and_standard_error(self) -> None:
        strata = [tc.Stratum("a", 0.5, (1.0, 3.0)), tc.Stratum("b", 0.5, (10.0, 14.0)), tc.Stratum("c", -1.0, (2.0, 2.0))]
        self.assertAlmostEqual(tc.estimate(strata), 0.5 * 2 + 0.5 * 12 - 2)
        self.assertAlmostEqual(tc.standard_error(strata), math.sqrt(0.25 * 2 / 2 + 0.25 * 8 / 2))

    def test_constant_strata_give_a_point_interval(self) -> None:
        result = tc.contrast([tc.Stratum("x", 1.0, (5.0, 5.0, 5.0)), tc.Stratum("y", -1.0, (2.0, 2.0, 2.0))], "k", FAST)
        self.assertEqual((result["estimate"], result["ci_low"], result["ci_high"]), (3.0, 3.0, 3.0))
        self.assertEqual(result["welch_ci"], [3.0, 3.0])

    def test_an_empty_stratum_is_not_estimable(self) -> None:
        self.assertFalse(tc.contrast([tc.Stratum("x", 1.0, ()), tc.Stratum("y", -1.0, (1.0,))], "k", FAST)["estimable"])

    def test_deterministic_and_seeded_by_name(self) -> None:
        rng = random.Random(1)
        strata = [tc.Stratum("x", 1.0, tuple(rng.gauss(0, 1) for _ in range(15))),
                  tc.Stratum("y", -1.0, tuple(rng.gauss(0, 1) for _ in range(15)))]
        self.assertEqual(tc.contrast(strata, "one", FAST), tc.contrast(strata, "one", FAST))
        self.assertNotEqual(tc.contrast(strata, "one", FAST)["ci_low"], tc.contrast(strata, "two", FAST)["ci_low"])
        self.assertNotEqual(tc.seed_for("one"), tc.seed_for("two"))

    def test_large_samples_agree_with_welch(self) -> None:
        rng = random.Random(7)
        strata = [tc.Stratum("x", 1.0, tuple(rng.gauss(50, 10) for _ in range(400))),
                  tc.Stratum("y", -1.0, tuple(rng.gauss(0, 20) for _ in range(400)))]
        result = tc.contrast(strata, "large", 2000)
        self.assertLess(abs(result["ci_low"] - result["welch_ci"][0]), 0.3 * result["se"])
        self.assertLess(abs(result["ci_high"] - result["welch_ci"][1]), 0.3 * result["se"])
        self.assertLess(result["ci_low"], result["estimate"])
        self.assertGreater(result["ci_high"], result["estimate"])

    def test_skewed_samples_give_an_asymmetric_studentized_interval(self) -> None:
        rng = random.Random(3)
        values = tuple(rng.expovariate(1 / 50.0) for _ in range(15))
        result = tc.contrast([tc.Stratum("x", 1.0, values)], "skew", 4000)
        self.assertGreater(result["ci_high"] - result["estimate"], result["estimate"] - result["ci_low"])

    def test_welch_df(self) -> None:
        strata = [tc.Stratum("x", 1.0, (1.0, 2.0, 3.0)), tc.Stratum("y", -1.0, (0.0, 0.0, 0.0))]
        self.assertAlmostEqual(tc.welch_df(strata), 2.0)
        self.assertIsNone(tc.welch_df([tc.Stratum("y", 1.0, (0.0, 0.0))]))


class StrataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = mini_manifest()

    def a_facts(self, margins: Dict[str, List[int]]) -> List[Dict[str, Any]]:
        out = []
        counters = collections.Counter()
        for entry in tc.phase_games(self.manifest, "A"):
            value = margins[entry["cell"]][counters[entry["cell"]] % len(margins[entry["cell"]])]
            counters[entry["cell"]] += 1
            out.append(facts_of(entry, self.manifest, value))
        return out

    def test_c1_games_cancel_from_the_seat_average(self) -> None:
        facts = self.a_facts({"H1": [-600, -700], "H2": [-1100, -1200], "C1": [-900, -800, -1000]})
        strata = tc.h2h_strata(facts, "2130511121")
        c1 = strata["seat_average"][2]
        self.assertEqual(set(c1.values), {0.0})
        self.assertEqual(len(c1.values), 15)
        h1, h2 = strata["seat_average"][0].values, strata["seat_average"][1].values
        self.assertEqual(set(h2), {1100.0, 1200.0})  # the blue margin of an H2 game
        self.assertAlmostEqual(tc.estimate(strata["seat_average"]), (statistics.mean(h1) + statistics.mean(h2)) / 2)
        self.assertAlmostEqual(tc.estimate(strata["seat_average"]),
                               (tc.estimate(strata["red"]) + tc.estimate(strata["blue"])) / 2)

    def test_a_non_zero_sum_c1_game_enters_the_seat_average(self) -> None:
        facts = self.a_facts({"H1": [-600], "H2": [-1100], "C1": [-900]})
        before = tc.estimate(tc.h2h_strata(facts, "2130511121")["seat_average"])
        c1 = next(f for f in facts if f["cell"] == "C1")
        c1["margins"] = {"red": -900, "blue": 930}
        after = tc.estimate(tc.h2h_strata(facts, "2130511121")["seat_average"])
        self.assertAlmostEqual(before - after, 15.0 / 15)

    def test_incomplete_games_are_left_out(self) -> None:
        facts = self.a_facts({"H1": [-600], "H2": [-1100], "C1": [-900]})
        facts[0]["completed"] = False
        strata = tc.h2h_strata(facts, "2130511121")
        self.assertEqual(sum(len(s.values) for s in strata["seat_average"]), 44)

    def test_inert_strata_use_the_candidate_seat(self) -> None:
        manifest = self.manifest
        d = tc.phase_games(manifest, "D")
        facts = [facts_of(e, manifest, 100 if e["cell"].endswith("T9") else 90) for e in d]
        c2 = tc.inert_strata(facts, "1910631192", "C2")
        self.assertEqual((c2[0].values, c2[1].values), ((100.0,) * 3, (90.0,) * 3))
        c3 = tc.inert_strata(facts, "1910631192", "C3")
        self.assertEqual((c3[0].values, c3[1].values), ((-100.0,) * 3, (-90.0,) * 3))
        analysis = tc.inert_analysis(facts, "1910631192", "C3", "D", FAST)
        self.assertEqual(analysis["estimate"], -10.0)
        self.assertEqual(analysis["pairwise_range"], [-10.0, -10.0])


class LedgerAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ids = [g["game_id"] for g in tc.schedule("0" * 64) if g["phase"] == "A"]

    def test_a_clean_ledger(self) -> None:
        audit = tc.ledger_audit(ledger_for(self.ids, "m"), "m", self.ids)
        self.assertTrue(audit["ok"], audit["problems"])
        self.assertEqual(audit["sessions"], 45)
        self.assertEqual(audit["games"][self.ids[0]], "2488")

    def check(self, ledger, needle: str) -> None:
        audit = tc.ledger_audit(ledger, "m", self.ids)
        self.assertFalse(audit["ok"])
        self.assertTrue(any(needle in p for p in audit["problems"]), audit["problems"])

    def test_a_foreign_session(self) -> None:
        ledger = ledger_for(self.ids, "m")
        ledger[1]["harness"]["manifest_sha256"] = "other"
        self.check(ledger, "not under the registered manifest")

    def test_an_unscheduled_game(self) -> None:
        ledger = ledger_for(self.ids, "m")
        ledger[1]["harness"]["game_id"] = "x"
        self.check(ledger, "unscheduled game")

    def test_a_game_opened_twice(self) -> None:
        self.check(ledger_for(self.ids + self.ids[:1], "m"), "opened twice")

    def test_unclosed_recovered_and_integrity(self) -> None:
        self.check(ledger_for(self.ids, "m")[:-1], "unclosed")
        ledger = ledger_for(self.ids, "m")
        ledger[2]["event"] = "session-recovered"
        self.check(ledger, "recovered")
        ledger = ledger_for(self.ids, "m")
        ledger[2]["integrity"] = {"ok": False}
        self.check(ledger, "integrity failure")

    def test_state_discontinuity(self) -> None:
        ledger = ledger_for(self.ids, "m")
        ledger[3]["state"] = {"s": "y"}
        self.check(ledger, "state other than")

    def test_the_cap(self) -> None:
        audit = tc.ledger_audit(ledger_for(self.ids, "m"), "m", self.ids, cap=44)
        self.assertFalse(audit["ok"])
        self.assertTrue(any("exceed the cap" in p for p in audit["problems"]))

    def test_sessions_before_the_base_are_ignored(self) -> None:
        ledger = [{"event": "session-open", "session": "0005", "state": {"s": "x"}, "harness": {}}] + ledger_for(self.ids, "m")
        self.assertTrue(tc.ledger_audit(ledger, "m", self.ids)["ok"])


class IdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = mini_manifest()
        self.entry = tc.phase_games(self.manifest, "A")[0]
        self.record = synthetic_game(self.entry, self.manifest, "m", "2488", 0)[0]

    def test_a_good_record(self) -> None:
        self.assertEqual(tc.record_identity_problems(self.record, self.manifest, "m"), [])

    def test_each_identity_is_checked(self) -> None:
        cases = {
            "manifest digest": lambda r: r["harness"].__setitem__("manifest_sha256", "x"),
            "dirty or unknown harness tree": lambda r: r["harness"].__setitem__("dirty", True),
            "study id": lambda r: r["harness"].__setitem__("study", "x"),
            "policy sources": lambda r: r["harness"]["policy_sources"].__setitem__(tc.V2_ID, "x" * 64),
            "runtime": lambda r: r["harness"].__setitem__("thread_env", {}),
            "execution (mode, workers or scheduler)": lambda r: r["harness"]["execution"].__setitem__("workers", 16),
            "engine version": lambda r: r.__setitem__("engine_version", "4.2.0"),
            "python version": lambda r: r.__setitem__("python", "3.12.1"),
            "session close integrity": lambda r: r.__setitem__("session_close", {"integrity": {"ok": False}}),
        }
        for problem, mutate in cases.items():
            record = json.loads(json.dumps(self.record))
            mutate(record)
            self.assertEqual(tc.record_identity_problems(record, self.manifest, "m"), [problem], problem)


class SystemicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = mini_manifest()
        self.entries = tc.phase_games(self.manifest, "A")

    def test_clean(self) -> None:
        facts = [facts_of(e, self.manifest, 0) for e in self.entries]
        self.assertTrue(tc.systemic_checks(facts)["ok"])

    def test_contract_errors_fail(self) -> None:
        h1 = next(k for k, e in enumerate(self.entries) if e["cell"] == "H1")
        facts = [facts_of(e, self.manifest, 0, contract_errors=1 if k == h1 else 0) for k, e in enumerate(self.entries)]
        check = tc.systemic_checks(facts)
        self.assertEqual(check["totals"]["contract_errors"], 1)
        self.assertEqual(check["failures"], ["contract_errors"])

    def test_a_new_candidate_refusal_class_fails_unless_baseline_v2_shows_it(self) -> None:
        h = next(e for e in self.entries if e["cell"] == "H1")
        facts = [facts_of(h, self.manifest, 0, candidate_classes=[(1, 777, "Synthetic")])]
        self.assertEqual(tc.systemic_checks(facts)["new_refusal_classes"], {"1/777/Synthetic": 1})
        self.assertIn("new refusal class in a candidate seat", tc.systemic_checks(facts)["failures"])
        self.assertTrue(tc.systemic_checks(facts, [(1, 777, "Synthetic")])["ok"])
        shown = facts_of(h, self.manifest, 0)
        shown["seats"]["blue"]["refusal_classes"] = [[1, 777, "Synthetic", 2]]
        self.assertTrue(tc.systemic_checks(facts + [shown])["ok"])
        known = [facts_of(h, self.manifest, 0, candidate_classes=[(2, 516, "CantShootToDiedBop")])]
        self.assertTrue(tc.systemic_checks(known)["ok"])

    def test_gate_rejections_are_counted_from_the_reason_mapping(self) -> None:
        h = next(e for e in self.entries if e["cell"] == "H1")
        facts = [facts_of(h, self.manifest, 0, gate_rejections={"reason N": 2, "other": 1})]
        self.assertEqual(facts[0]["seats"]["red"]["gate_rejections"], 3)
        self.assertEqual(tc.systemic_checks(facts)["failures"], ["gate_rejections"])

    def test_an_addon_error_fails(self) -> None:
        facts = [facts_of(e, self.manifest, 0) for e in self.entries]
        seat = tc.candidate_seats(facts[0] if facts[0]["cell"] != "C1" else facts[1])[0]
        seat["mechanism"]["moves"]["addon_errors"] = 1
        self.assertIn("addon_errors", tc.systemic_checks(facts)["failures"])


def analyse(manifest, phase, facts, ledger_ok=True, identity=None, prior=()):
    audit = {"ok": ledger_ok, "problems": [] if ledger_ok else ["x"], "games": {}}
    return tc.analyse_phase(manifest, phase, facts, audit, identity or {}, prior, FAST)


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = mini_manifest()

    def test_phase_a_positive_effect_continues(self) -> None:
        facts = phase_facts(self.manifest, "A", h2h_margin(200, random.Random(1)))
        result = analyse(self.manifest, "A", facts)
        self.assertTrue(result["primary"]["supported"], result["primary"])
        self.assertEqual(result["gate"], {"decision": "CONTINUE", "reasons": [], "permits": "D"})

    def test_phase_a_null_effect_stops(self) -> None:
        facts = phase_facts(self.manifest, "A", h2h_margin(-30, random.Random(2)))
        result = analyse(self.manifest, "A", facts)
        self.assertTrue(result["primary"]["tested"])
        self.assertFalse(result["primary"]["supported"])
        self.assertEqual(result["gate"]["decision"], "STOP")
        self.assertIn("the primary interval's lower limit is not above 0", result["gate"]["reasons"])

    def test_a_positive_estimate_with_a_low_interval_stops(self) -> None:
        facts = phase_facts(self.manifest, "A", h2h_margin(25, random.Random(9), sd=300))
        result = analyse(self.manifest, "A", facts)
        self.assertGreater(result["primary"]["estimate"], 0)
        self.assertLessEqual(result["primary"]["ci_low"], 0)
        self.assertFalse(result["primary"]["supported"])
        self.assertEqual(result["gate"]["decision"], "STOP")

    def test_an_incomplete_phase_a_is_not_tested(self) -> None:
        margin = h2h_margin(300, random.Random(1))
        facts = [facts_of(e, self.manifest, margin(e), status="CAPPED" if k == 3 else "COMPLETED")
                 for k, e in enumerate(tc.phase_games(self.manifest, "A"))]
        result = analyse(self.manifest, "A", facts)
        self.assertFalse(result["primary"]["tested"])
        self.assertFalse(result["primary"]["supported"])
        self.assertIn("primary not tested", result["gate"]["reasons"])
        self.assertEqual(result["completion"]["not_completed"], [facts[3]["game_id"]])

    def test_integrity_failures_stop(self) -> None:
        facts = phase_facts(self.manifest, "A", h2h_margin(300, random.Random(1)))
        failed = analyse(self.manifest, "A", facts, ledger_ok=False)
        self.assertEqual(failed["gate"]["decision"], "STOP")
        self.assertFalse(failed["primary"]["tested"])
        self.assertFalse(failed["primary"]["supported"])
        self.assertEqual(analyse(self.manifest, "A", facts, identity={facts[0]["game_id"]: ["x"]})["gate"]["decision"],
                         "STOP")
        facts[2]["capture_checks"] = {"ok": False, "problems": ["x"]}
        self.assertEqual(analyse(self.manifest, "A", facts)["integrity"]["captures"], [facts[2]["game_id"]])

    def test_a_margin_identity_failure_stops(self) -> None:
        facts = phase_facts(self.manifest, "A", h2h_margin(300, random.Random(1)))
        facts[5]["margin_identity"] = False
        self.assertEqual(analyse(self.manifest, "A", facts)["gate"]["decision"], "STOP")

    def test_facts_must_cover_the_phase_in_order(self) -> None:
        facts = phase_facts(self.manifest, "A", h2h_margin(300, random.Random(1)))
        with self.assertRaises(ValueError):
            analyse(self.manifest, "A", facts[1:])
        with self.assertRaises(ValueError):
            analyse(self.manifest, "A", list(reversed(facts)))

    def d_facts(self, gap: float, config=("1910631192", "C2")) -> List[Dict[str, Any]]:
        def margin(entry):
            red = entry["cell"].startswith("C2")
            base = 100 if red else -100
            if (entry["scenario_id"], entry["cell"].split("-")[0]) == config and entry["cell"].endswith("T9"):
                return base + gap if red else base - gap
            return base
        return phase_facts(self.manifest, "D", margin)

    def test_phase_d_threshold(self) -> None:
        self.assertEqual(analyse(self.manifest, "D", self.d_facts(-9))["gate"]["decision"], "CONTINUE")
        self.assertEqual(analyse(self.manifest, "D", self.d_facts(-10))["gate"]["decision"], "CONTINUE")
        stopped = analyse(self.manifest, "D", self.d_facts(-10.5))
        self.assertEqual(stopped["gate"]["decision"], "STOP")
        self.assertEqual(len(stopped["adverse_signals"]), 1)
        blue = analyse(self.manifest, "D", self.d_facts(-11, ("2010131194", "C3")))
        self.assertEqual(blue["adverse_signals"][0].split(":")[0], "2010131194 C3")

    def test_phase_b_threshold_uses_the_interval(self) -> None:
        rng = random.Random(5)

        def margin(entry, shift):
            red = entry["cell"].startswith("C2")
            noise = rng.gauss(0, 5)
            value = (300 if red else -300) + noise
            if entry["cell"] == "C3-T9" and entry["scenario_id"] == "1930331196":
                value -= shift
            return round(value)

        clear = phase_facts(self.manifest, "B", lambda e: margin(e, -40))
        self.assertEqual(analyse(self.manifest, "B", clear)["gate"]["decision"], "STOP")
        mild = phase_facts(self.manifest, "B", lambda e: margin(e, -8))
        self.assertEqual(analyse(self.manifest, "B", mild)["gate"]["decision"], "CONTINUE")

    def test_phase_c_completes(self) -> None:
        facts = phase_facts(self.manifest, "C", h2h_margin(0, random.Random(4), sd=400))
        result = analyse(self.manifest, "C", facts)
        self.assertEqual(result["gate"]["decision"], "COMPLETE")
        self.assertEqual(sorted(result["head_to_head"]), ["1930331196", "2120531121"])
        self.assertNotIn("primary", result)

    def test_flags_are_descriptive(self) -> None:
        facts = [facts_of(e, self.manifest, 100 if e["cell"].startswith("C2") else -100,
                          never_departed=2) for e in tc.phase_games(self.manifest, "D")]
        result = analyse(self.manifest, "D", facts)
        self.assertEqual(len(result["flags"]["idle"]), 10)
        self.assertEqual(result["gate"]["decision"], "CONTINUE")
        slow = [facts_of(e, self.manifest, 100 if e["cell"].startswith("C2") else -100,
                         latency_us=[500] * 200 + [6_000_000]) for e in tc.phase_games(self.manifest, "D")]
        self.assertEqual(len(analyse(self.manifest, "D", slow)["flags"]["latency"]), 10)  # by the maximum alone
        self.assertEqual(slow[0]["seats"]["red" if slow[0]["red"] == tc.CANDIDATE_ID else "blue"]["latency"]["p99_ms"],
                         0.5)


class DispositionTest(unittest.TestCase):
    def result(self, phase, supported=True, tested=True, adverse=(), systemic_ok=True, gate="CONTINUE"):
        r = {"completion": {"ok": tested}, "integrity": {"ok": True}, "systemic": {"ok": systemic_ok},
             "adverse_signals": list(adverse), "flags": {"idle": [], "objectives": [], "latency": []},
             "gate": {"decision": gate}}
        if phase == "A":
            r["primary"] = {"supported": supported, "tested": tested}
        return r

    def test_labels(self) -> None:
        self.assertEqual(tc.disposition({"A": self.result("A")})["label"], "PRIMARY_SUPPORTED")
        self.assertEqual(tc.disposition({"A": self.result("A", supported=False)})["label"], "PRIMARY_NOT_SUPPORTED")
        self.assertEqual(tc.disposition({"A": self.result("A", supported=False, tested=False)})["label"],
                         "INCONCLUSIVE_PROTOCOL_INCOMPLETE")
        self.assertEqual(tc.disposition({"A": self.result("A"), "D": self.result("D", adverse=["x"])})["label"],
                         "PRIMARY_SUPPORTED_NEEDS_REVISION")
        self.assertEqual(tc.disposition({"A": self.result("A"), "D": self.result("D", systemic_ok=False)})["label"],
                         "PRIMARY_SUPPORTED_NEEDS_REVISION")
        d = tc.disposition({"A": self.result("A"), "D": self.result("D")})
        self.assertEqual(d["safety"], {"A": "CLEAN", "D": "CLEAN", "B": "NOT_REACHED", "C": "NOT_REACHED"})
        self.assertEqual(d["generality"], "NOT_REACHED")
        self.assertFalse(d["eligible_for_promotion"])
        with self.assertRaises(ValueError):
            tc.disposition({})

    def test_generality_counts(self) -> None:
        b = self.result("B")
        b["against_inert"] = {"s C2": {"estimable": True, "estimate": 5.0, "ci_low": 1.0, "ci_high": 9.0},
                              "s C3": {"estimable": True, "estimate": -5.0, "ci_low": -9.0, "ci_high": -1.0}}
        c = self.result("C", gate="COMPLETE")
        c["head_to_head"] = {"x": {"seat_average": {"estimable": True, "estimate": 3.0, "ci_low": -1.0, "ci_high": 7.0}}}
        g = tc.disposition({"A": self.result("A"), "D": self.result("D"), "B": b, "C": c})["generality"]
        self.assertEqual((g["configurations"], g["estimate_above_0"], g["interval_above_0"], g["interval_below_0"]),
                         (3, 2, 1, 1))


# ------------------------------------------------------------------------------------------------
# The capture, on the stand-in engine through the real game loop


def stand_in_game(fill=(4, 201, 6), steps=60):
    spec = GameSpec(game_id="synthetic.C3.t9", scenario_id="900000001", map_id="9000", condition="C3", red=INERT_ID,
                    blue=T9_ID, repetition=1, max_time=steps)
    capture, explore = tc.T9Capture(), xp.ExploreCapture((T9_ID,))
    ticks = itertools.count()
    factories = {INERT_ID: lambda: PolicyAgent(INERT_ID), T9_ID: lambda: AllocationAgent()}
    record = play(lambda: pe.ProbeEnv(play_steps=steps, fill=fill), factories, spec, pe.Inputs, PLAYERS,
                  clock=lambda: next(ticks) * 0.001, replay_policies={T9_ID}, observer=tc.Tee(capture, explore))
    return record, json.loads(capture.file()), json.loads(explore.files()[0])


class CaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record, cls.capture, cls.explore = stand_in_game()

    def test_the_game_completes_without_observer_errors(self) -> None:
        self.assertEqual(self.record["status"], "COMPLETED")
        self.assertEqual(self.record["observer_errors"], [])
        self.assertEqual(self.capture["steps"], self.record["steps"])

    def test_the_cross_checks_agree(self) -> None:
        self.assertEqual(tc.capture_checks(self.record, self.capture, self.explore), {"ok": True, "problems": []})

    def test_the_candidate_withholds_the_idle_units(self) -> None:
        moves = self.capture["seats"]["1"]["moves"]
        withholding = self.capture["seats"]["1"]["withholding"]
        self.assertGreater(moves["withheld"], 0)
        self.assertEqual(withholding["units"], 6)  # the six idle units put into hex 201
        self.assertEqual(withholding["unit_decisions"], moves["withheld"])
        self.assertLessEqual(withholding["longest_run_max"], withholding["unit_decisions"])
        self.assertEqual(moves["redirected"], moves["replaced"] - moves["reverted"])
        self.assertEqual(self.capture["addon_changes"].get("1:withhold"), moves["withheld"])

    def test_start_positions_and_objectives(self) -> None:
        start = self.capture["seats"]["1"]["start_positions"]
        self.assertEqual(start["ground_units"], 10)
        self.assertEqual(start["ground_units"], start["never_departed"] + start["departed"] + start["embarked"]
                         + start["removed_before_leaving"])
        objectives = self.capture["seats"]["1"]["objectives"]
        self.assertEqual(objectives["count"], 2)
        self.assertGreaterEqual(objectives["held_at_end"], 1)  # objective 205 is blue's from the start
        self.assertEqual(self.capture["seats"]["1"]["losses"], {"start_units": 10, "lost": 0})

    def test_a_disagreement_is_detected(self) -> None:
        explore = json.loads(json.dumps(self.explore))
        explore["waiting_ground_units"]["1"]["sum"] += 1
        self.assertFalse(tc.capture_checks(self.record, self.capture, explore)["ok"])
        capture = json.loads(json.dumps(self.capture))
        capture["steps"] += 1
        self.assertEqual(tc.capture_checks(self.record, capture, self.explore)["problems"], ["step count"])
        capture = json.loads(json.dumps(self.capture))
        capture["seats"]["1"]["moves"]["emitted"] += 1
        self.assertIn("move orders of side 1", tc.capture_checks(self.record, capture, self.explore)["problems"])
        self.assertFalse(tc.capture_checks(self.record, None, self.explore)["ok"])

    def test_the_tee_runs_every_observer_and_reports_errors(self) -> None:
        calls = []

        class Good:
            def setup(self, *a):
                calls.append("good")

            step = setup

        class Bad:
            def setup(self, *a):
                raise KeyError("boom")

            step = setup

        with self.assertRaises(RuntimeError) as raised:
            tc.Tee(Bad(), Good()).setup()
        self.assertEqual(calls, ["good"])
        self.assertIn("Bad.setup: KeyError", str(raised.exception))


class CaptureUnitTest(unittest.TestCase):
    """Hand-built states: departure, embarkation, removal, waiting, holding, withheld runs and refusals."""

    @staticmethod
    def view(cur_step, units, cities, passengers=(), feedback=(), stage=2):
        from miaosuan_agent.boundary import normalize_state
        observation = {"operators": units, "passengers": list(passengers),
                       "time": {"cur_step": cur_step, "stage": stage}, "cities": cities, "actions": list(feedback),
                       "valid_actions": {}}
        return normalize_state({0: observation, 1: observation, -1: observation}, validate=False)

    def test_counts(self) -> None:
        def u(i, hex_, path=(), speed=1, kind=2):
            return {"obj_id": i, "color": 1, "type": kind, "cur_hex": hex_, "move_path": list(path), "speed": speed}

        cities = [{"coord": 500, "value": 30, "flag": -1}, {"coord": 600, "value": 70, "flag": 1}]

        class Trace:
            addon_name = "t9"
            skipped = (("kept: destination under capacity", 1),)
            addon_error = None

            def __init__(self, changes):
                self.changes = tuple(json.dumps(c) for c in changes)

        capture = tc.T9Capture()
        capture.setup(None, (), {0: INERT_ID, 1: T9_ID})
        s0 = self.view(10, [u(1, 100), u(2, 101), u(3, 102), u(4, 103)], cities)
        s1 = self.view(11, [u(1, 100), u(2, 105, (500,)), u(4, 103, (500, 600), speed=0)], cities, passengers=[u(3, 0)],
                       feedback=[{"message": {"actor": 11, "obj_id": 4, "type": 1}, "error": {"code": 21}},
                                 {"message": {"actor": 11, "obj_id": 2, "type": 1}, "error": {"code": 22}}])
        s2 = self.view(12, [u(1, 100), u(4, 103, (500, 600), speed=0)], [dict(cities[0], flag=1), cities[1]],
                       passengers=[u(3, 0)])
        s3 = self.view(13, [u(1, 100), u(4, 104)], [dict(cities[0], flag=1), cities[1]], passengers=[u(3, 0)])
        withhold = {"kind": "withhold", "obj_id": 1}
        decisions = lambda changes: [{"seat": 11, "faction": 1, "submitted": [{"type": 1, "obj_id": 4}],
                                      "trace": Trace(changes)}]
        capture.step(0, s0, s1, decisions([withhold, {"kind": "replace", "obj_id": 4}, {"kind": "replace", "obj_id": 2},
                                           {"kind": "revert", "obj_id": 2}]))
        capture.step(1, s1, s2, decisions([withhold]))
        capture.step(2, s2, s3, decisions([]))
        capture.step(3, s3, s3, decisions([withhold]))
        facts = capture.seat_facts(1)
        self.assertEqual(facts["moves"]["withheld"], 3)
        self.assertEqual((facts["moves"]["replaced"], facts["moves"]["reverted"], facts["moves"]["redirected"]), (2, 1, 1))
        self.assertEqual(facts["moves"]["replaced_refused"], {"21": 1})
        self.assertEqual(facts["withholding"], {"units": 1, "unit_decisions": 3, "longest_run_max": 2,
                                                "longest_run_median": 2})
        start = facts["start_positions"]
        self.assertEqual((start["never_departed"], start["departed"], start["embarked"], start["removed_before_leaving"]),
                         (1, 2, 1, 0))
        self.assertEqual(start["idle_unit_steps"], 4 + 2)  # unit 1 idle in 4 states; unit 4 in 2 before it left
        self.assertEqual(facts["waiting_in_front_of_full_hex"], {"max": 1, "sum": 2, "steps_positive": 2})
        self.assertEqual(facts["objectives"]["held_steps"], 1 + 2 + 2 + 2)
        self.assertEqual(facts["objectives"]["held_at_end"], 2)
        self.assertEqual(facts["objectives"]["held_value_at_end"], 100)
        self.assertEqual(facts["objectives"]["first_hold_step_min"], 11)
        self.assertEqual(facts["losses"], {"start_units": 4, "lost": 1})
        self.assertEqual(facts["max_objective_commitment"]["max"], 1)


# ------------------------------------------------------------------------------------------------
# The full schedule through the registered analysis


class FullScheduleDryRun(unittest.TestCase):
    """Synthetic records for every one of the 375 scheduled games of the registered manifest (before registration:
    the same design with placeholder pins), analysed phase by phase with the analysis script's own functions; then
    the disposition."""

    @classmethod
    def setUpClass(cls) -> None:
        build = load_script("build_t9_confirmation_manifest")
        cls.analysis = load_script("t9_confirmation_analysis")
        committed = REPO / "evaluation" / tc.STUDY_ID / "manifest.json"
        if committed.exists():  # the exact registered schedule
            cls.manifest = json.loads(committed.read_text(encoding="utf-8"))
        else:  # before registration: the same design with placeholder pins
            shoot = json.loads((REPO / "evaluation" / tc.V2_ID / "manifest.json").read_text(encoding="utf-8"))
            policies = {tc.V2_ID: {"label": "v2", "policy_source": build.policy_source(build.V2_SOURCES)},
                        tc.CANDIDATE_ID: {"label": "t9", "policy_source": build.policy_source(build.T9_SOURCES)}}
            cls.manifest = tc.build(build.TEXTS, shoot, "s" * 64, policies, build.current_scheduler(), {}, {}, {})
        from miaosuan_agent.evaluation import manifest as mf
        cls.digest = mf.digest(cls.manifest)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp.name)
        (cls.work / "games").mkdir()
        (cls.work / "capture").mkdir()
        rng = random.Random(11)
        margin_a = h2h_margin(250, rng)
        ids = []
        for n, entry in enumerate(cls.manifest["games"], start=tc.LEDGER_BASE_SESSION + 1):
            if entry["phase"] in ("A", "C"):
                red = margin_a(entry)
            else:
                red = 100 if entry["cell"].startswith("C2") else -100
            record, t9_bytes, explore_bytes = synthetic_game(entry, cls.manifest, cls.digest, f"{n:04d}", red)
            (cls.work / "games" / f"{entry['game_id']}.json").write_text(json.dumps(record), encoding="utf-8")
            (cls.work / "capture" / f"{entry['game_id']}.t9.json").write_bytes(t9_bytes)
            (cls.work / "capture" / f"{entry['game_id']}.explore.json").write_bytes(explore_bytes)
            ids.append(entry["game_id"])
        cls.ledger = ledger_for(ids, cls.digest)
        cls.results = {phase: cls.analysis.analyse(cls.manifest, phase, cls.work, cls.ledger, resamples=FAST)
                       for phase in tc.PHASE_ORDER}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_every_phase_passes_its_gate(self) -> None:
        decisions = {p: r["gate"]["decision"] for p, r in self.results.items()}
        self.assertEqual(decisions, {"A": "CONTINUE", "D": "CONTINUE", "B": "CONTINUE", "C": "COMPLETE"},
                         {p: r["gate"]["reasons"] for p, r in self.results.items()})
        for phase, result in self.results.items():
            self.assertEqual(len(result["games"]), tc.phase_sessions(phase))
            self.assertTrue(result["integrity"]["ok"], result["integrity"])

    def test_the_primary_is_tested_once_in_phase_a(self) -> None:
        primary = self.results["A"]["primary"]
        self.assertTrue(primary["tested"] and primary["supported"])
        self.assertEqual([p for p, r in self.results.items() if "primary" in r], ["A"])

    def test_the_ledger_prefix_keeps_a_phase_file_stable(self) -> None:
        a_only = self.ledger[:1 + 2 * 45]
        again = self.analysis.analyse(self.manifest, "A", self.work, a_only, resamples=FAST)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.results["A"], sort_keys=True))

    def test_a_changed_capture_fails_integrity(self) -> None:
        game = tc.phase_games(self.manifest, "D")[0]["game_id"]
        path = self.work / "capture" / f"{game}.t9.json"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")  # same content, other bytes: only the digest check sees it
            result = self.analysis.analyse(self.manifest, "D", self.work, self.ledger, resamples=FAST)
            self.assertEqual(result["integrity"]["captures"], [game])
            self.assertEqual(result["gate"]["decision"], "STOP")
        finally:
            path.write_bytes(original)

    def test_a_session_other_than_the_ledger_s_fails_integrity(self) -> None:
        game = tc.phase_games(self.manifest, "C")[3]["game_id"]
        path = self.work / "games" / f"{game}.json"
        original = path.read_bytes()
        try:
            record = json.loads(original)
            record["session"] = "9999"
            path.write_text(json.dumps(record), encoding="utf-8")
            result = self.analysis.analyse(self.manifest, "C", self.work, self.ledger, resamples=FAST)
            self.assertEqual(result["integrity"]["records_identity"], {game: ["session differs from the ledger's"]})
            self.assertEqual(result["gate"]["decision"], "STOP")
        finally:
            path.write_bytes(original)

    def test_a_missing_record_stops(self) -> None:
        game = tc.phase_games(self.manifest, "B")[7]["game_id"]
        path = self.work / "games" / f"{game}.json"
        original = path.read_bytes()
        try:
            path.unlink()
            result = self.analysis.analyse(self.manifest, "B", self.work, self.ledger, resamples=FAST)
            self.assertEqual(result["completion"]["not_completed"], [game])
            self.assertEqual(result["gate"]["decision"], "STOP")
        finally:
            path.write_bytes(original)

    def test_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as out:
            for phase, result in self.results.items():
                Path(out, f"phase-{phase}.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
            payload = json.loads(self.analysis.disposition_text(Path(out)))
        self.assertEqual(payload["label"], "PRIMARY_SUPPORTED")
        self.assertEqual(payload["phases_reached"], list(tc.PHASE_ORDER))
        self.assertEqual(payload["generality"]["configurations"], 8)


if __name__ == "__main__":
    unittest.main()
