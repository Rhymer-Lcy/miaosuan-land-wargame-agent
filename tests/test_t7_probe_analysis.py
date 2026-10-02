"""The registered analyses of the T7 mechanism probe, end to end on the stand-in engine. SYNTHETIC games.

Each stand-in game plays the registered candidate (blue) through the project's game loop with the T7 capture, under
one engine behaviour the protocol must recognise, and the analysis must give the registered verdicts. Planted errors
check that every integrity cross-check refuses, and the gate, the stop branch and the disposition are checked on
their own tables.
"""

from __future__ import annotations

import copy
import functools
import importlib.util
import json
import pickle
import unittest
from pathlib import Path
from unittest import mock

from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import t7_candidates as tc
from miaosuan_agent.evaluation import t7_probe as tp
from miaosuan_agent.evaluation import t7_probe_endpoints as ep
from miaosuan_agent.evaluation import t7_probe_metrics as tm
from miaosuan_agent.evaluation import t7_visibility as tv

from tests.fixtures import t7_probe_engine as fx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t7_probe_analysis", ROOT / "scripts" / "t7_probe_analysis.py")
ANA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ANA)

SEAT = 11
NEAR_SQUAD = 1118   # 7 hexes from the squad (between its concealed and normal distance), 9 from the vehicles
FAR = 2323          # 18 to 20 hexes from every blue unit: the matched band for a vehicle target


class Inputs:
    def __init__(self, **options) -> None:
        self.cost = fx.Inputs.cost
        self.basic = fx.basic_data(options.get("elevations"), options.get("forest", ()))
        self.see = fx.los_table()


def _key(options):
    return json.dumps(options, sort_keys=True)


@functools.lru_cache(maxsize=None)
def _played(key: str, blue: str, game_id: str):
    options = json.loads(key)
    for name in ("suppress", "red_moves", "flips"):
        if name in options:
            options[name] = [tuple(x) for x in options[name]]
    if "elevations" in options:
        options["elevations"] = {int(k): v for k, v in options["elevations"].items()}
    return fx.play_t7(blue=blue, game_id=game_id, **options)


def game_of(blue=tp.CANDIDATE_ID, game_id="synthetic.C3.pa", **options):
    record, compact, windows = _played(_key(options), blue, game_id)
    return tm.Game(game_id, copy.deepcopy(record), copy.deepcopy(compact), copy.deepcopy(windows))


def run(probe="P-A", game=None, reference=None, first_k=1, units=3, **options):
    game = game or game_of(game_id="synthetic.C3.pa" if probe == "P-A" else "synthetic.H1.pb1", **options)
    if probe == "P-A" and reference is None:
        reference = game_of(blue=tp.BASELINE_ID, game_id="synthetic.ref", **options)
    public, private = ANA.analyse(probe, game, fx.manifest(first_k, units), Inputs(**options), None,
                                  reference=reference)
    return public, private


def verdicts(public):
    return {k: public[k]["verdict"] for k in ("S1", "S2", "E1", "E2", "E3a", "E3b", "E5", "S3", "E6", "S4")
            if k in public}


class DocumentedEngineTest(unittest.TestCase):
    def test_documented_concealment_passes_every_pa_check(self) -> None:
        public, private = run()
        self.assertEqual(verdicts(public), {"S1": "PASS", "S2": "PASS", "E1": "SUPPORTED", "E2": "SUPPORTED",
                                            "E3a": "SUPPORTED", "E3b": "NOT TESTED", "E5": "NOT TESTED",
                                            "S3": "PASS", "E6": "SUPPORTED"})
        self.assertEqual(public["E2"]["durations"], {"75": 3})
        self.assertEqual(public["E2"]["timer_start_offsets"], {"1": 3})
        self.assertEqual(public["primary"]["share"], 1.0)
        self.assertEqual(public["integrity"]["I3"]["trace_blocks"], 3)
        self.assertEqual(len(private["orders"]), 3)
        gate = ep.gate_pa(public, True)
        self.assertTrue(gate["continue_to_pb"])
        self.assertFalse(ep.gate_pa(public, False)["continue_to_pb"])
        self.assertNotIn(str(fx.TANK), json.dumps(public))  # no unit id in the public output

    def test_timer_one_step_late_is_still_documented(self) -> None:
        public, _ = run(timer_delay=1)
        self.assertEqual(public["E2"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E2"]["timer_start_offsets"], {"2": 3})

    def test_state_set_first_with_the_timer_counting_down(self) -> None:
        public, _ = run(conceal="state first")
        self.assertEqual(public["E2"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E2"]["durations"], {"75": 3})
        self.assertEqual(public["E2"]["first_move_state_4_offsets"], {"1": 3})

    def test_window_boundary(self) -> None:
        public, _ = run(transition=76)
        self.assertEqual(public["E2"]["outcomes"], {"COMPLETED": 3})
        self.assertEqual(public["E2"]["durations"], {"76": 3})
        public, _ = run(transition=77)
        self.assertEqual(public["E2"]["outcomes"], {"LATE": 3})

    def test_missing_echo_is_inconclusive_for_e1_only(self) -> None:
        public, _ = run(no_echo=True)
        self.assertEqual(public["E1"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(public["E1"]["no_or_several_echoes"], 3)
        self.assertEqual(public["S1"]["verdict"], "PASS")
        self.assertEqual(public["E2"]["verdict"], "SUPPORTED")

    def test_in_place_rewrite_is_counted_not_refused(self) -> None:
        public, _ = run(rewrite_conceal=16)
        self.assertEqual(public["integrity"]["I3"]["rewritten_in_place"], 3)
        self.assertEqual(public["E1"]["verdict"], "SUPPORTED")  # matched on the pre-execution copy's type


class RefutationsTest(unittest.TestCase):
    def test_refused_orders(self) -> None:
        public, _ = run(conceal="refused")
        v = verdicts(public)
        self.assertEqual((v["S1"], v["E1"], v["E2"]), ("FAIL", "REFUTED", "REFUTED"))
        self.assertIn("NOT_COMPLETED", public["E2"]["outcomes"])
        self.assertFalse(ep.gate_pa(public, True)["continue_to_pb"])

    def test_echo_without_error_is_not_a_transition(self) -> None:
        public, _ = run(conceal="ignored")
        self.assertEqual(public["E1"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E2"]["verdict"], "REFUTED")
        self.assertIn("NOT_COMPLETED", public["E2"]["outcomes"])
        self.assertIn("CENSORED", public["E2"]["outcomes"])  # the repeat at cur_step 225 cannot finish by 300

    def test_timer_anomalies(self) -> None:
        for option in ({"conceal": "instant"}, {"conceal": "no timer"}, {"timer_delay": 2}):
            public, _ = run(**option)
            self.assertEqual(public["E2"]["verdict"], "REFUTED", option)
            self.assertEqual(public["E2"]["outcomes"], {"COMPLETED_TIMER_ANOMALY": 3}, option)
            self.assertEqual(public["primary"]["reached_within_76"], 3, option)  # primary counts arrival only

    def test_late_completion(self) -> None:
        public, _ = run(transition=80)
        self.assertEqual(public["E2"]["outcomes"], {"LATE": 3})
        self.assertEqual(public["primary"]["share"], 0.0)

    def test_lock_fails_s2(self) -> None:
        public, _ = run(conceal="lock")
        self.assertEqual(public["S2"]["verdict"], "FAIL")
        self.assertIn("flag_force_stop", {x["what"] for x in public["S2"]["violations"]})
        self.assertEqual(public["E1"]["verdict"], "SUPPORTED")

    def test_listing_losses(self) -> None:
        public, _ = run(concealed_listing=())
        self.assertEqual(public["S2"]["verdict"], "FAIL")
        self.assertIn("move not listed", {x["what"] for x in public["S2"]["violations"]})
        self.assertEqual(public["E3a"]["verdict"], "REFUTED")
        public, _ = run(concealed_listing=(1,))
        self.assertEqual(public["S2"]["verdict"], "PASS")
        self.assertEqual(public["E3a"]["lost_types"], [11])


class TransientListingTest(unittest.TestCase):
    def test_one_empty_snapshot_is_transient_two_are_a_loss(self) -> None:
        public, _ = run(blank=[(150, fx.TANK, 1)])
        self.assertEqual(public["S2"]["verdict"], "PASS")
        self.assertEqual([x["snapshots"] for x in public["S2"]["transients"]], [1, 1])
        self.assertEqual(public["E3a"]["verdict"], "SUPPORTED")
        self.assertEqual(sorted(x["type"] for x in public["E3a"]["transients"]), [1, 11])
        public, _ = run(blank=[(150, fx.TANK, 2)])
        self.assertEqual(public["S2"]["verdict"], "FAIL")
        self.assertEqual({x["what"] for x in public["S2"]["violations"]},
                         {"empty listing outside a transition", "move not listed"})
        self.assertEqual(public["E3a"]["verdict"], "REFUTED")


class CensoringAndInterruptionTest(unittest.TestCase):
    def test_game_end_censors(self) -> None:
        public, _ = run(play_steps=50)
        self.assertEqual(public["E2"]["outcomes"], {"CENSORED": 3})
        self.assertEqual(public["E2"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(public["primary"], {"orders": 3, "reached_within_76": 0, "share": 0.0, "censored": 3,
                                             "interrupted": 0, "failed": 0, "criterion_100_percent": False})

    def test_suppression_interrupts(self) -> None:
        public, private = run(suppress=[(30, fx.TANK, 10)])
        self.assertEqual(public["E2"]["verdict"], "INCONCLUSIVE")
        interrupted = [r for r in private["orders"] if r["outcome"] == "INTERRUPTED"]
        self.assertEqual([r["interrupter"]["what"] for r in interrupted], ["suppressed"])
        self.assertEqual(public["E5"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E5"]["by_event"], {"suppressed": 1})

    def test_suppression_that_does_not_interrupt_refutes_e5(self) -> None:
        public, _ = run(suppress=[(30, fx.TANK, 10)], suppress_interrupts=False)
        self.assertEqual(public["E2"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E5"]["verdict"], "REFUTED")


class ExitAndTransitionOrdersTest(unittest.TestCase):
    def test_free_exit_by_move(self) -> None:
        public, _ = run(flips=[(100, fx.OBJ_B, fx.RED)], stop_transition=10)
        self.assertEqual(public["E3b"]["verdict"], "SUPPORTED")
        self.assertEqual(public["S2"]["verdict"], "PASS")  # empty listings inside the move-to-stop transition
        self.assertGreaterEqual(public["E3b"]["consistent"], 1)
        self.assertEqual(public["S3"]["verdict"], "PASS")
        self.assertEqual(public["E6"]["verdict"], "SUPPORTED")

    def test_delayed_exit_refutes_e3b_and_breaks_non_interference(self) -> None:
        public, _ = run(flips=[(100, fx.OBJ_B, fx.RED)], exit="delayed")
        self.assertEqual(public["E3b"]["verdict"], "REFUTED")
        self.assertEqual(public["E6"]["verdict"], "REFUTED")
        self.assertEqual(public["S3"]["verdict"], "FAIL")  # the delayed units occupy late, so baseline-v2 differs

    def test_a_move_that_keeps_concealment_refutes_e3b(self) -> None:
        public, _ = run(flips=[(100, fx.OBJ_B, fx.RED)], exit="kept")
        self.assertEqual(public["E3b"]["verdict"], "REFUTED")

    def test_new_refusal_class_of_the_candidate_fails_s4(self) -> None:
        public, _ = run("P-B1", flips=[(20, fx.OBJ_B, fx.RED)], transition_listing="kept", during="refused")
        self.assertEqual(public["S4"]["verdict"], "FAIL")
        self.assertFalse(ep.stop_after_pb1(public, True)["run_pb2"])
        public, _ = run("P-B1")
        self.assertEqual(public["S4"]["verdict"], "PASS")

    def test_orders_during_the_transition(self) -> None:
        base = dict(flips=[(20, fx.OBJ_B, fx.RED)], transition_listing="kept")
        public, _ = run(during="refused", **base)
        self.assertEqual(public["E5"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E2"]["verdict"], "SUPPORTED")
        public, _ = run(during="executed", **base)
        self.assertEqual(public["E5"]["verdict"], "REFUTED")
        self.assertEqual(public["E2"]["verdict"], "INCONCLUSIVE")
        public, _ = run(during="deferred", **base)
        self.assertEqual(public["E5"]["verdict"], "SUPPORTED")

    def test_tank_shot_during_the_transition_interrupts_it(self) -> None:
        public, private = run(shoot=True, transition_listing="kept", red_moves=[(20, fx.RED_1, NEAR_SQUAD)])
        self.assertEqual(public["E5"]["verdict"], "SUPPORTED")
        tank = [r for r in private["orders"] if r["unit"] == fx.TANK]
        self.assertEqual(tank[0]["outcome"], "INTERRUPTED")
        self.assertEqual(tank[0]["interrupter"]["what"], "fired")

    def test_shot_from_concealment(self) -> None:
        public, _ = run(shoot=True, red_moves=[(100, fx.RED_1, NEAR_SQUAD)])
        self.assertEqual(public["E3b"]["verdict"], "SUPPORTED")
        self.assertIn("2", public["E3b"]["by_type"])


class VisibilityTest(unittest.TestCase):
    MOVES = [(100, fx.RED_1, NEAR_SQUAD), (100, fx.RED_2, FAR)]

    def test_geometry_of_the_scenario(self) -> None:
        self.assertEqual(tv.hex_distance(1111, NEAR_SQUAD), 7)
        self.assertEqual(tv.hex_distance(fx.OBJ_A, NEAR_SQUAD), 9)
        self.assertGreater(min(tv.hex_distance(h, FAR) for h in (fx.OBJ_A, 1111)), 13)

    def test_documented_visibility_supports_e4a(self) -> None:
        public, private = run("P-B1", red_moves=self.MOVES)
        e4 = public["E4"]
        self.assertTrue(e4["control_valid"])
        self.assertEqual(e4["E4a"]["verdict"], "SUPPORTED")
        self.assertEqual(e4["E4b"]["verdict"], "SUPPORTED")
        # red arrives at cur_step 100: snapshots 100 to 299 and the final state (cur_step 300)
        self.assertEqual(e4["classes"][tv.DISCRIMINATING], {"unlisted": 201})
        self.assertEqual(e4["matched"]["target_steps"], 201)
        self.assertEqual(public["S4"]["verdict"], "PASS")
        self.assertTrue(all("target" in row for row in private["E4_rows"]))

    def test_concealment_without_effect_refutes_e4a(self) -> None:
        public, _ = run("P-B1", red_moves=self.MOVES, visibility="ignored")
        self.assertEqual(public["E4"]["E4a"]["verdict"], "REFUTED")

    def test_invisible_concealment_refutes_only_e4b(self) -> None:
        public, _ = run("P-B1", red_moves=self.MOVES, visibility="hidden")
        self.assertEqual(public["E4"]["E4a"]["verdict"], "SUPPORTED")
        self.assertEqual(public["E4"]["E4b"]["verdict"], "REFUTED")

    def test_lower_vehicle_exception(self) -> None:
        public, _ = run("P-B1", red_moves=self.MOVES, elevations={NEAR_SQUAD: 5})
        self.assertIn(tv.EXCEPTION_VISIBLE, public["E4"]["classes"])
        self.assertEqual(public["E4"]["classes"][tv.EXCEPTION_VISIBLE].get("unlisted", 0), 0)

    def test_no_opponent_nearby_leaves_e4_untested(self) -> None:
        public, _ = run("P-B1")
        self.assertEqual(public["E4"]["E4a"]["verdict"], "NOT TESTED")
        self.assertFalse(public["E4"]["control_valid"])  # no matched-band control either

    def test_control_validity(self) -> None:
        self.assertTrue(ep.control_valid(10000, 9995, 30, 30))
        self.assertFalse(ep.control_valid(10000, 9995, 30, 29))   # matched band below 0.99
        self.assertFalse(ep.control_valid(10000, 9989, 30, 30))   # control below 0.999
        self.assertFalse(ep.control_valid(10000, 10000, 19, 19))  # fewer than 20 matched target-steps
        self.assertFalse(ep.control_valid(0, 0, 30, 30))

    def test_e4_verdict_thresholds(self) -> None:
        good = {"control_valid": True, "classes": {tv.DISCRIMINATING: {"unlisted": 10}}}
        self.assertEqual(ep.e4_verdicts([good])["E4a"]["verdict"], "SUPPORTED")
        self.assertEqual(ep.e4_verdicts([dict(good, control_valid=False)])["E4a"]["verdict"], "INCONCLUSIVE")
        mixed = dict(good, classes={tv.DISCRIMINATING: {"unlisted": 6, "listed": 4}})
        self.assertEqual(ep.e4_verdicts([mixed])["E4a"]["verdict"], "INCONCLUSIVE")
        half = dict(good, classes={tv.DISCRIMINATING: {"unlisted": 5, "listed": 5}})
        self.assertEqual(ep.e4_verdicts([half])["E4a"]["verdict"], "REFUTED")
        self.assertEqual(ep.e4_verdicts([dict(good, classes={})])["E4a"]["verdict"], "NOT TESTED")
        self.assertEqual(ep.e4_verdicts([good, mixed])["E4a"]["listed"], 4)


class IntegrityPlantsTest(unittest.TestCase):
    def refuses(self, game, pattern, probe="P-A"):
        with self.assertRaises(tm.AnalysisRefused) as caught:
            run(probe, game=game, reference=game_of(blue=tp.BASELINE_ID, game_id="synthetic.ref"))
        self.assertRegex(str(caught.exception), pattern)

    def test_missing_trace_block(self) -> None:
        game = game_of()
        del game.steps[5]["t7"][str(SEAT)]
        self.refuses(game, "I3: no t7 trace block")

    def test_record_count_differs(self) -> None:
        game = game_of()
        seat = next(s for s in game.record["seats"] if s["seat"] == SEAT)
        seat["actions_by_type"]["6"] += 1
        self.refuses(game, "I3")

    def test_a_copy_altered(self) -> None:
        game = game_of()
        game.steps[1]["submitted"][1]["action"]["target_state"] = 5
        self.refuses(game, "I3")

    def test_missing_snapshot_and_final(self) -> None:
        game = game_of()
        del game.samples[40]
        self.refuses(game, "I2: no snapshot")
        game = game_of()
        game.windows["final"] = None
        self.refuses(game, "I2: no final state")

    def test_record_problems(self) -> None:
        game = game_of()
        game.record["harness"]["dirty"] = True
        self.refuses(game, "I1: harness dirty")
        game = game_of()
        game.record["status"] = "CAPPED"
        self.refuses(game, "I1: record status")

    def test_channels_disagree(self) -> None:
        game = game_of()
        sample = game.samples[120]
        raw = pickle.loads(sample["seats"][SEAT]["observation"])
        for unit in raw["operators"]:
            if unit["obj_id"] == fx.TANK:
                unit["move_state"] = 0
        sample["seats"][SEAT]["observation"] = pickle.dumps(raw, protocol=4)
        self.refuses(game, "I4: unit 910001 field move_state differs")

    def test_channels_disagree_on_a_listing(self) -> None:
        game = game_of()
        sample = game.samples[120]
        raw = pickle.loads(sample["seats"][SEAT]["observation"])
        raw["valid_actions"][fx.TANK].pop(11)
        sample["seats"][SEAT]["observation"] = pickle.dumps(raw, protocol=4)
        self.refuses(game, "I4: unit 910001 field types differs")

    def test_actions_altered(self) -> None:
        game = game_of()
        game.steps[0]["submitted"][1]["action"]["planted"] = 1
        self.refuses(game, "I5: re-decided actions differ")

    def test_trace_digest_altered(self) -> None:
        game = game_of()
        game.steps[30]["traces"][str(SEAT)] = "0" * 64
        self.refuses(game, "I5: re-decided trace differs")

    def test_pool_predicate_disagrees(self) -> None:
        with mock.patch.object(tc, "a2", return_value=None):
            self.refuses(game_of(), "I5: the pool predicate")

    def test_reconstruction_disagrees(self) -> None:
        record = {"k": 1, "unit": 1, "cur_step": 0, "timer_start": 1, "completion": 75}
        with self.assertRaises(tm.AnalysisRefused):
            ep.check_reconstruction([record], [(1, 76)])
        self.assertEqual(ep.check_reconstruction([record], [(1, 75)]), {"orders_compared": 1})

    def test_e4_channels_disagree(self) -> None:
        game = game_of(game_id="synthetic.H1.pb1", red_moves=VisibilityTest.MOVES)
        sample = game.samples[150]
        raw = pickle.loads(sample["seats"][1]["observation"])
        for unit in raw["operators"]:
            if unit["obj_id"] == fx.RED_1:
                unit["cur_hex"] = 1117
        sample["seats"][1]["observation"] = pickle.dumps(raw, protocol=4)
        with self.assertRaises(tm.AnalysisRefused) as caught:
            run("P-B1", game=game, red_moves=VisibilityTest.MOVES)
        self.assertIn("E4 channels disagree", str(caught.exception))


class ReferenceComparisonTest(unittest.TestCase):
    def test_reference_differs_before_the_first_order(self) -> None:
        ref = game_of(blue=tp.BASELINE_ID, game_id="synthetic.ref")
        ref.record["state_steps"][1] = "f" * 16
        public, _ = run(reference=ref)
        self.assertEqual(public["S3"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(public["E6"]["verdict"], "INCONCLUSIVE")
        self.assertFalse(ep.gate_pa(public, True)["continue_to_pb"])

    def test_reference_differs_after_the_first_order(self) -> None:
        ref = game_of(blue=tp.BASELINE_ID, game_id="synthetic.ref")
        ref.steps[200]["batch"].append({"i": 9, "seat": SEAT, "faction": 1, "j": 0,
                                        "action": {"actor": SEAT, "obj_id": fx.IFV, "type": 1, "move_path": [1011]}})
        public, _ = run(reference=ref)
        self.assertEqual(public["S3"]["verdict"], "FAIL")
        self.assertEqual(public["S3"]["after_first_order"][0]["k"], 200)

    def test_reference_positions_differ(self) -> None:
        ref = game_of(blue=tp.BASELINE_ID, game_id="synthetic.ref")
        raw = pickle.loads(ref.samples[150]["global"])
        raw["operators"][0]["cur_hex"] = 1212
        ref.samples[150]["global"] = pickle.dumps(raw, protocol=4)
        public, _ = run(reference=ref)
        self.assertEqual(public["E6"]["verdict"], "REFUTED")

    def test_unpredicted_first_order(self) -> None:
        public, _ = run(first_k=2)
        self.assertEqual(public["S3"]["verdict"], "INCONCLUSIVE")


class FreshFeedbackTest(unittest.TestCase):
    def test_repeats_while_the_clock_stands_still_are_dropped(self) -> None:
        a = {"message": {"actor": 1, "type": 333}}
        b = {"message": {"actor": 11, "type": 333}}
        steps = {0: {"cur_step": 0, "feedback": [a]}, 1: {"cur_step": 0, "feedback": [a, b]},
                 2: {"cur_step": 1, "feedback": [a]}}
        self.assertEqual(tm.fresh_feedback(steps), {0: [a], 1: [b], 2: [a]})

    def test_matching_needs_the_target_state(self) -> None:
        entry = {"message": {"actor": 11, "type": 6, "obj_id": 5, "target_state": 4}}
        self.assertTrue(tm.matches(entry, {"actor": 11, "type": 6, "obj_id": 5, "target_state": 4}))
        self.assertFalse(tm.matches(entry, {"actor": 11, "type": 6, "obj_id": 5, "target_state": 5}))
        self.assertFalse(tm.matches(entry, {"actor": 11, "type": 6, "obj_id": 6, "target_state": 4}))


def _result(**overrides):
    base = {"integrity": {"ok": True}, "S1": {"verdict": "PASS"}, "S2": {"verdict": "PASS"},
            "E1": {"verdict": "SUPPORTED"}, "E2": {"verdict": "SUPPORTED"}, "E3a": {"verdict": "SUPPORTED"},
            "E3b": {"verdict": "SUPPORTED"}, "E5": {"verdict": "NOT TESTED"}, "orders": [{"outcome": "COMPLETED"}]}
    base.update({k: {"verdict": v} if isinstance(v, str) else v for k, v in overrides.items()})
    return base


class DispositionTest(unittest.TestCase):
    def results(self, pa=None, pb1=None, pb2=None, e4a="SUPPORTED"):
        r = {"P-A": _result(**{"S3": "PASS", "E6": "SUPPORTED", **(pa or {})}),
             "P-B1": _result(**{"S4": "PASS", **(pb1 or {})}), "P-B2": _result(**{"S4": "PASS", **(pb2 or {})}),
             "pooled_e4": {"E4a": {"verdict": e4a}, "E4b": {"verdict": "SUPPORTED"}}}
        return r

    def label(self, results, played=("P-A", "P-B1", "P-B2")):
        return ep.disposition(results, list(played))["disposition"]

    def test_ready(self) -> None:
        self.assertEqual(self.label(self.results()), "READY_FOR_TACTICAL_SCREEN")

    def test_shelve(self) -> None:
        self.assertEqual(self.label(self.results(pb1={"S2": "FAIL"})), "SHELVE")
        self.assertEqual(self.label(self.results(e4a="REFUTED")), "SHELVE")
        self.assertEqual(self.label(self.results(pb2={"E3b": "REFUTED"})), "SHELVE")
        self.assertEqual(self.label(self.results(pa={"E2": "REFUTED", "orders": [{"outcome": "NOT_COMPLETED"}]})),
                         "SHELVE")

    def test_revise(self) -> None:
        self.assertEqual(self.label(self.results(pa={"E2": "REFUTED", "orders": [{"outcome": "LATE"}]})), "REVISE")
        self.assertEqual(self.label(self.results(pa={"S3": "FAIL"})), "REVISE")
        self.assertEqual(self.label(self.results(pb1={"S4": "FAIL"})), "REVISE")
        self.assertEqual(self.label(self.results(pb1={"E3a": "REFUTED"})), "REVISE")
        self.assertEqual(self.label(self.results(pb1={"integrity": {"ok": False}})), "REVISE")

    def test_needs_targeted_probe(self) -> None:
        self.assertEqual(self.label(self.results(e4a="NOT TESTED")), "NEEDS_TARGETED_PROBE")
        self.assertEqual(self.label(self.results(pa={"E3b": "NOT TESTED"}, pb1={"E3b": "NOT TESTED"},
                                                 pb2={"E3b": "NOT TESTED"})), "NEEDS_TARGETED_PROBE")
        r = self.results()
        self.assertEqual(self.label(r, ("P-A",)), "NEEDS_TARGETED_PROBE")
        self.assertEqual(self.label(self.results(pa={"E2": "INCONCLUSIVE"})), "NEEDS_TARGETED_PROBE")

    def test_gate_and_stop_branch(self) -> None:
        pa = _result(S3="PASS", E6="SUPPORTED")
        self.assertTrue(ep.gate_pa(pa, True)["continue_to_pb"])
        for name, value in (("S1", "FAIL"), ("S2", "FAIL"), ("S3", "FAIL"), ("S3", "INCONCLUSIVE"),
                            ("E2", "INCONCLUSIVE"), ("E2", "REFUTED"), ("S2", "NOT TESTED")):
            self.assertFalse(ep.gate_pa(_result(**{"S3": "PASS", name: value}), True)["continue_to_pb"], (name, value))
        pb1 = _result(S4="PASS")
        self.assertTrue(ep.stop_after_pb1(pb1, True)["run_pb2"])
        self.assertTrue(ep.stop_after_pb1(_result(S4="PASS", S2="NOT TESTED", E2="REFUTED"), True)["run_pb2"])
        for name, value in (("S1", "FAIL"), ("S2", "FAIL"), ("S4", "FAIL")):
            self.assertFalse(ep.stop_after_pb1(_result(**{"S4": "PASS", name: value}), True)["run_pb2"])
        self.assertFalse(ep.stop_after_pb1(pb1, False)["run_pb2"])

    def test_pooling(self) -> None:
        self.assertEqual(ep.pooled(["SUPPORTED", "NOT TESTED"]), "SUPPORTED")
        self.assertEqual(ep.pooled(["SUPPORTED", "INCONCLUSIVE"]), "INCONCLUSIVE")
        self.assertEqual(ep.pooled(["INCONCLUSIVE", "REFUTED"]), "REFUTED")
        self.assertEqual(ep.pooled([None, "NOT TESTED"]), "NOT TESTED")


if __name__ == "__main__":
    unittest.main()
