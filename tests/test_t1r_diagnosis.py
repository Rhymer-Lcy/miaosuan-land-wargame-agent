"""The T1-r diagnosis analysis (``scripts/t1r_diagnosis.py``) on SYNTHETIC captures.

Per-state quantities, idle reasons from observed fields, fresh feedback, move completion, the first divergence aligned
by engine time, the capture-against-record cross-checks and the mechanical verdicts.
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAT, FACTION = 11, 1
RED_SEAT = 1


def load_script():
    spec = importlib.util.spec_from_file_location("t1r_diagnosis", ROOT / "scripts" / "t1r_diagnosis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unit(obj_id, hex_, blood=3, color=FACTION, **extra):
    return {"obj_id": obj_id, "color": color, "cur_hex": hex_, "blood": blood, "type": 2, "sub_type": 0, "value": 10,
            "on_board": 0, "car": None, "move_path": [], "keep": 0, **extra}


def state(cur_step, stage, units, flags=(-1, -1)):
    return {"time": {"cur_step": cur_step, "stage": stage}, "operators": units,
            "cities": [{"coord": 4754, "value": 80, "flag": flags[0]}, {"coord": 5052, "value": 50, "flag": flags[1]}]}


def build(work: Path, game_id: str, plan, final_scores, actions_by_type):
    """plan: list of (cur_step, stage, units, flags, own_actions, valid_actions)."""
    steps, samples = [], []
    for k, (cur_step, stage, units, flags, actions, valid) in enumerate(plan):
        batch = [{"i": i, "j": i, "seat": SEAT, "faction": FACTION, "action": dict(a, actor=SEAT)} for i, a in enumerate(actions)]
        steps.append({"k": k, "cur_step": cur_step, "stage": stage, "batch": batch, "feedback": [], "appeared": [],
                      "gone": [], "boarded": [], "landed": [], "changed": {}, "traces": {}})
        if k > 0:
            samples.append({"k": k, "cur_step": cur_step, "global": pickle.dumps(state(cur_step, stage, units, flags)),
                            "seats": {SEAT: {"faction": FACTION, "policy": "p", "observation": pickle.dumps({"valid_actions": valid}),
                                             "memory": pickle.dumps(None), "actions": actions, "trace": "t"}}})
    (work / "games").mkdir(parents=True, exist_ok=True)
    (work / "capture").mkdir(parents=True, exist_ok=True)
    record = {"game_id": game_id, "status": "COMPLETED", "final_scores": final_scores,
              "seats": [{"seat": RED_SEAT, "faction": 0, "policy": "inert-v0", "actions_by_type": {}},
                        {"seat": SEAT, "faction": FACTION, "policy": "p", "actions_by_type": actions_by_type}]}
    (work / "games" / f"{game_id}.json").write_text(json.dumps(record), encoding="utf-8")
    (work / "capture" / f"{game_id}.capture.json").write_text(json.dumps({"steps": steps, "setup": {}}), encoding="utf-8")
    (work / "capture" / f"{game_id}.windows.pkl").write_bytes(pickle.dumps({"samples": samples, "events": []}))


def scores(occupy, remain=60, attack=0):
    return {"blue_occupy": occupy, "blue_attack": attack, "blue_remain": remain, "blue_total": occupy + remain + attack,
            "red_occupy": 0, "red_attack": 0, "red_remain": 40, "red_total": 40}


MOVE_A = {"type": 1, "obj_id": 1, "move_path": [5052]}
MOVE_B = {"type": 1, "obj_id": 2, "move_path": [4754]}
OCC_A = {"type": 5, "obj_id": 1}
VALID = {1: {1: None}, 2: {1: None}}


def baseline_plan():
    far = [unit(1, 7000), unit(2, 7001)]
    on_a = [unit(1, 5052), unit(2, 7001)]
    held = [unit(1, 5052), unit(2, 4754)]
    return [(0, 1, far, (-1, -1), [{"type": 333}], {}),
            (0, 2, far, (-1, -1), [MOVE_A, MOVE_B], VALID),
            (1, 2, on_a, (-1, -1), [OCC_A], {1: {5: None}, 2: {}}),
            (2, 2, held, (-1, 1), [], {}),
            (3, 2, held, (1, 1), [], {})]


def candidate_plan():
    """Same engine time, but unit 2 never leaves and stands idle with movement not listed; unit 1 splits."""
    far = [unit(1, 7000, blood=2), unit(3, 7000, blood=1), unit(2, 7001)]
    on_a = [unit(1, 5052, blood=2), unit(3, 7000, blood=1), unit(2, 7001)]
    return [(0, 1, far, (-1, -1), [{"type": 314, "obj_id": 1}], {}),
            (0, 1, far, (-1, -1), [{"type": 333}], {}),
            (0, 2, far, (-1, -1), [MOVE_A], VALID),
            (1, 2, on_a, (-1, -1), [OCC_A], {1: {5: None}, 2: {}, 3: {}}),
            (2, 2, on_a, (-1, 1), [], {2: {}, 3: {}}),
            (3, 2, on_a, (-1, 1), [], {2: {}, 3: {}})]


class QuantitiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.d = load_script()

    def test_occupancy_and_stacks(self) -> None:
        units = [unit(1, 100, 2), unit(2, 100, 1), unit(3, 200, 4), unit(4, 100, 1, on_board=1), unit(9, 100, 3, color=0)]
        self.assertEqual(self.d.occupancy(units[:4]), {100: 3, 200: 4})
        self.assertEqual(self.d.stack_counts(units[:4]), {100: 2, 200: 1})
        self.assertEqual([c["label"] for c in self.d.objectives(state(0, 2, []))], ["objective_value_80", "objective_value_50"])

    def test_idle_reasons(self) -> None:
        r = self.d.idle_reason
        self.assertEqual(r(unit(1, 5, on_board=1), {}, [5]), "passenger")
        self.assertEqual(r(unit(1, 5, move_path=[6]), {}, [5]), "already moving")
        self.assertEqual(r(unit(1, 5), {1: {2: None}}, []), "shoot listed, not emitted")
        self.assertEqual(r(unit(1, 5), {1: {5: None}}, [5]), "occupy listed, not emitted")
        self.assertEqual(r(unit(1, 5), {1: {1: None}}, [5]), "standing on an unheld objective, occupy not listed")
        self.assertEqual(r(unit(1, 7), {1: {}}, [5]), "move not listed")
        self.assertEqual(r(unit(1, 7), {1: {1: None}}, []), "no objective outside own control")
        self.assertEqual(r(unit(1, 7), {"1": {1: None}}, [5]), "move listed, none emitted")

    def test_fresh_feedback(self) -> None:
        steps = [{"cur_step": 0, "feedback": [{"m": 1}]}, {"cur_step": 0, "feedback": [{"m": 1}, {"m": 2}]},
                 {"cur_step": 1, "feedback": [{"m": 1}, {"m": 2}]}]
        self.assertEqual(self.d.fresh_feedback(steps), [[{"m": 1}], [{"m": 2}], [{"m": 1}, {"m": 2}]])


class AnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.d = load_script()

    def analyse(self, baseline=None, candidate=None, b_scores=None, c_scores=None, b_counts=None, c_counts=None, expect=None):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            build(work, "b", baseline or baseline_plan(), b_scores or scores(130), b_counts or {"1": 2, "5": 1, "333": 1})
            build(work, "c", candidate or candidate_plan(), c_scores or scores(50), c_counts or {"1": 1, "5": 1, "314": 1, "333": 1})
            return self.d.analyse(work, "b", "c", expect)

    def test_planted_games(self) -> None:
        out = self.analyse(expect=(190, 110))
        self.assertTrue(out["premise"]["reproduced"])
        b, c = out["baseline"], out["candidate"]
        self.assertEqual((b["moves_issued"], b["occupations_issued"], c["moves_issued"], c["deployment_splits_issued"]), (2, 1, 1, 1))
        self.assertEqual((b["deployment_steps"], c["deployment_steps"]), (1, 2))
        self.assertEqual(b["flag_flip_k"], {"objective_value_80": 4, "objective_value_50": 3})
        self.assertEqual(c["flag_flip_k"], {"objective_value_80": None, "objective_value_50": 4})
        self.assertEqual((b["held_value_at_end"], c["held_value_at_end"]), (130, 50))
        self.assertTrue(b["flags_at_last_snapshot_reproduce_occupy_score"] and c["flags_at_last_snapshot_reproduce_occupy_score"])
        self.assertEqual(c["idle_reasons_while_an_objective_unheld"], {"move listed, none emitted": 1, "move not listed": 9})
        self.assertEqual(b["moves"], {"issued": 2, "completed": 2, "not_completed": 0, "undetermined": 0})
        self.assertEqual(c["moves"]["completed"], 1)
        self.assertEqual(out["difference"]["components"], {"occupy": -80, "attack": 0, "remain": 0})
        self.assertTrue(out["difference"]["components_sum_equals_total"])
        self.assertEqual(out["difference"]["occupy_points_held_by_window_candidate_minus_baseline"], {"0": -80})
        div = out["first_divergence"]
        self.assertEqual((div["cur_step"], div["k_baseline"], div["k_candidate"]), (1, 2, 3))
        self.assertIn("blood-weighted occupancy differs in 2 hexes", div["reasons"])
        self.assertEqual(out["mechanical_verdicts"], {"H1": "REFUTED", "H4": "REFUTED", "H6": "REFUTED"})
        self.assertNotIn("4754", json.dumps(out))

    def test_cross_checks_refuse(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.analyse(b_counts={"1": 3, "5": 1, "333": 1})
        self.assertIn("2 moves in the capture but the record counts 3", str(raised.exception))
        with self.assertRaises(SystemExit):
            self.analyse(c_scores=scores(0))

    def test_premise_failure_stops(self) -> None:
        out = self.analyse(expect=(190, 111))
        self.assertFalse(out["premise"]["reproduced"])
        self.assertIn("stopped", out)

    def test_verdicts_follow_planted_changes(self) -> None:
        plan = candidate_plan()
        hurt = [(s, st, [dict(u, blood=1) for u in us], f, a, v) if s == 3 else (s, st, us, f, a, v) for s, st, us, f, a, v in plan]
        self.assertEqual(self.analyse(candidate=hurt)["mechanical_verdicts"]["H1"], "SUPPORTED")
        rider = [(s, st, [dict(us[0], on_board=1)] + us[1:], f, a, v) for s, st, us, f, a, v in plan]
        self.assertEqual(self.analyse(candidate=rider)["mechanical_verdicts"]["H4"], "SUPPORTED")
        self.assertEqual(self.analyse(c_scores=scores(50, remain=61))["mechanical_verdicts"]["H6"], "SUPPORTED")


@unittest.skipUnless((ROOT / "evaluation" / "t1r-diagnosis-1" / "analysis.json").exists(), "the public analysis is committed separately")
class PublishedAnalysisTest(unittest.TestCase):
    def test_identities_and_privacy(self) -> None:
        text = (ROOT / "evaluation" / "t1r-diagnosis-1" / "analysis.json").read_text(encoding="utf-8")
        out = json.loads(text)
        self.assertEqual((out["status"], out["premise"]["reproduced"]), ("DIAGNOSTIC", True))
        diff = out["difference"]
        self.assertTrue(diff["components_sum_equals_total"])
        self.assertEqual(diff["total"], out["candidate"]["scores"]["blue_total"] - out["baseline"]["scores"]["blue_total"])
        for side in ("baseline", "candidate"):
            s = out[side]
            self.assertEqual(s["remain_score"], s["value_times_blood_at_end"])
            self.assertEqual(s["held_value_at_end"], s["occupy_score"])
            self.assertEqual(s["moves"]["issued"], s["moves_issued"])
        for forbidden in ("obj_id", "cur_hex", "4754", "5052"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
