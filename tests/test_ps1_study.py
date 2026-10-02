"""The PS-1 design-study driver (``scripts/ps1_study.py``) on a SYNTHETIC capture shaped like the real ones.

Two-channel reconstruction (all-seeing state against the seat observation, flags against the observation's score
counters), the capture-against-record refusal, the path-shrink and hex-time audits, fidelity F1/F2, entry comparison,
the amendment-1 restart check and its thresholds, and the trigger census.
"""

from __future__ import annotations

import copy
import importlib.util
import pickle
import unittest
from pathlib import Path

from miaosuan_agent.boundary import MoveCosts

ROOT = Path(__file__).resolve().parents[1]
SEAT, FACTION = 1, 0


def load_script():
    spec = importlib.util.spec_from_file_location("ps1_study", ROOT / "scripts" / "ps1_study.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def costs(pairs):
    edges = {}
    for a, b in pairs:
        edges.setdefault(a, {})[b] = 1.0
        edges.setdefault(b, {})[a] = 1.0
    return MoveCosts(rows=2, cols=10, edges=(edges, edges, edges, {}))


COSTS = costs([(101, 102), (102, 103)])


def operator(hex_, path, speed):
    return {"obj_id": 1, "color": FACTION, "type": 2, "sub_type": 0, "cur_hex": hex_, "move_path": list(path),
            "basic_speed": 36, "on_board": 0, "move_state": 0, "speed": speed, "can_to_move": 1, "flag_force_stop": 0,
            "stop": 0, "car": None}


def game(order_path_end=103, record_moves=1, corrupt_at=None, late=0, stale_path_at=None):
    """One vehicle ordered at decision 1 from 101 to 103 (20 steps per hex), occupying 103 at 41."""
    samples, steps = [], []
    for k in range(0, 61):
        if k <= 1:
            hex_, path = 101, ()
        elif k < 21:
            hex_, path = 101, (102, 103)
        elif k < 41 + late:
            hex_, path = 102, (103,)
        else:
            hex_, path = 103, ()
        speed = 0.05 if path else 0
        flag = FACTION if k >= 42 + late else -1
        state = {"time": {"cur_step": max(0, k - 1), "stage": 1 if k == 0 else 2},
                 "operators": [operator(hex_, path, speed)],
                 "cities": [{"coord": 103, "value": 80, "flag": flag}], "landmarks": {"roadblocks": []}}
        obs = copy.deepcopy(state)
        obs["role_and_grouping_info"] = {SEAT: {"faction": FACTION, "operators": [1]}}
        obs["scores"] = {"red_occupy": 80 if flag == FACTION else 0}
        obs["valid_actions"] = {1: {10: None}} if path else {1: {1: None}}
        if corrupt_at == k:
            obs["operators"][0]["cur_hex"] = 999
        if stale_path_at == k:  # the path did not shrink on entry (both channels)
            for view in (state, obs):
                view["operators"][0]["move_path"] = [102, 103]
        samples.append({"k": k, "global": pickle.dumps(state), "seats": {SEAT: {"observation": pickle.dumps(obs)}}})
        batch = []
        if k == 0:
            batch = [{"seat": SEAT, "action": {"type": 333}}]
        elif k == 1:
            batch = [{"seat": SEAT, "action": {"actor": SEAT, "obj_id": 1, "type": 1, "move_path": [102, order_path_end]}}]
        elif k == 41 + late:
            batch = [{"seat": SEAT, "action": {"actor": SEAT, "obj_id": 1, "type": 5}}]
        steps.append({"k": k, "stage": state["time"]["stage"], "cur_step": state["time"]["cur_step"], "batch": batch,
                      "feedback": []})
    record = {"game_id": "s.C3.c.x01", "status": "COMPLETED",
              "final_scores": {"red_total": 210, "red_win": 106, "red_occupy": 80, "red_remain": 130, "red_attack": 0,
                               "blue_total": 104},
              "seats": [{"seat": SEAT, "faction": FACTION, "policy": "p", "actions_by_type": {"1": record_moves, "5": 1}},
                        {"seat": 11, "faction": 1, "policy": "inert-v0", "actions_by_type": {}}]}
    return record, {"steps": steps}, {"samples": samples, "events": []}


class ReconstructionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = load_script()

    def test_two_channels_and_audits(self) -> None:
        cap = self.s.Capture(*game())
        r = self.s.reconstruct(cap, COSTS)
        self.assertEqual((r["channel_disagreements"], r["flags_vs_observation_scores"]), (0, {"equal": 61}))
        self.assertEqual((r["orders"], r["occupations"], r["entries"]), (1, 1, 2))
        self.assertEqual((r["O2"], r["O5"], r["order_echo"]), ({"path advanced by one": 2}, {"exact": 2},
                                                              {"next state carries the path": 1}))
        self.assertEqual(r["O4_speed"], {"moving": {"speed equals 1/tau": 39}})
        self.assertIsNone(r["persistent_deadlock"])
        self.assertEqual(r["scores"]["win"], r["scores"]["total"] - r["scores"]["other_total"])

    def test_path_that_does_not_shrink_is_reported(self) -> None:
        r = self.s.reconstruct(self.s.Capture(*game(stale_path_at=21)), COSTS)
        self.assertEqual(r["O2"]["path not advanced by one"], 1)
        self.assertEqual(r["O2"]["path inconsistent with the cost graph"], 1)  # counted, not a crash

    def test_channel_disagreement_is_counted(self) -> None:
        r = self.s.reconstruct(self.s.Capture(*game(corrupt_at=30)), COSTS)
        self.assertEqual(r["channel_disagreements"], 1)

    def test_capture_against_record_refusal(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.s.reconstruct(self.s.Capture(*game(record_moves=2)), COSTS)
        self.assertIn("1 moves in the capture, 2 in the record", str(raised.exception))


class FidelityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = load_script()

    def test_both_levels_pass_on_a_reproducible_game(self) -> None:
        cap = self.s.Capture(*game())
        recon = self.s.reconstruct(cap, COSTS)
        for restart in (False, True):
            f = self.s.fidelity(cap, COSTS, recon, restart)
            self.assertTrue(f["F1_pass"] and f["F2_pass"], (restart, f))
            self.assertEqual(f["F2"]["orders"], {"recorded": 1, "simulated": 1, "recorded_matched": 1})
            self.assertEqual(f["F2"]["occupation_steps"], {"recorded": [41], "simulated": [41]})

    def test_an_offset_of_two_steps_fails_fidelity(self) -> None:
        cap = self.s.Capture(*game(late=2))  # the second hex is entered two steps later than the model predicts
        recon = self.s.reconstruct(cap, COSTS)
        f = self.s.fidelity(cap, COSTS, recon)
        self.assertEqual((f["F1"]["worst_step_offset"], f["F1_pass"]), (2, False))

    def test_entry_comparison(self) -> None:
        cmp = self.s.compare_entries([(21, 1, 102), (42, 1, 103)], [(21, 1, 102), (41, 1, 103)], 1)
        self.assertEqual((cmp["hex_sequences_differ"], cmp["worst_step_offset"]), (0, 1))
        cmp = self.s.compare_entries([(21, 1, 102)], [(21, 1, 102), (41, 1, 103)], 1)
        self.assertEqual(cmp["hex_sequences_differ"], 1)


class RestartCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = load_script()

    def sequence(self, enter_after_room):
        """A unit at 101 bound for 102, which holds four units until step 30; it enters at 30 + enter_after_room."""
        out = []
        for step in range(0, 80):
            blockers = 4 if step < 30 else 3
            entered = step >= 30 + enter_after_room
            me = {"obj_id": 1, "type": 2, "cur_hex": 102 if entered else 101, "move_path": [] if entered else [102],
                  "basic_speed": 36, "on_board": 0, "move_state": 0, "speed": 0 if step < 30 else 0.05}
            others = [{"obj_id": 10 + i, "type": 2, "cur_hex": 102, "move_path": [], "basic_speed": 36, "on_board": 0,
                       "move_state": 0, "speed": 0} for i in range(blockers)]
            out.append((step, {"role_and_grouping_info": {SEAT: {"operators": [1, 10, 11, 12, 13]}},
                               "operators": [me] + others}))
        return out

    def test_episode_distance_and_windows(self) -> None:
        edges = {0: COSTS.edges[0]}
        m1b = self.s.restart_episodes(self.sequence(19), SEAT, FACTION, edges)
        m1 = self.s.restart_episodes(self.sequence(0), SEAT, FACTION, edges)
        self.assertEqual((m1b, m1), ([{"d": 19, "tau": 20}], [{"d": 0, "tau": 20}]))

    def test_classification_thresholds(self) -> None:
        c = self.s.classify_restarts
        good = [{"d": 19, "tau": 20}] * 10
        self.assertEqual(c(good)["verdict"], "supports M1b")
        self.assertEqual(c(good[:9])["verdict"], "insufficient")
        self.assertEqual(c(good[:9] + [{"d": 0, "tau": 20}] * 2)["verdict"], "does not support M1b")  # 2 of 11 in M1
        self.assertEqual(c(good[:9] + [{"d": 7, "tau": 20}])["verdict"], "supports M1b")  # 9 of 10 = 90%
        self.assertEqual(c(good[:8] + [{"d": 7, "tau": 20}] * 2)["verdict"], "does not support M1b")
        self.assertEqual(c(good[:9] + [{"d": 7, "tau": 20}])["other"], 1)
        fast = [{"d": 0, "tau": 1}] * 10  # both windows contain d = 0: the evidence cannot discriminate
        self.assertEqual(c(fast)["verdict"], "does not support M1b")


class CensusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = load_script()

    def test_deadlock_and_admission_counts(self) -> None:
        edges = {0: COSTS.edges[0]}
        a = [{"obj_id": i, "type": 2, "cur_hex": 101, "move_path": [102], "basic_speed": 36, "on_board": 0,
              "move_state": 0} for i in range(1, 5)]
        b = [{"obj_id": i, "type": 2, "cur_hex": 102, "move_path": [101], "basic_speed": 36, "on_board": 0,
              "move_state": 0} for i in range(5, 9)]
        obs = {"role_and_grouping_info": {SEAT: {"operators": list(range(1, 9))}}, "operators": a + b,
               "cities": [{"coord": 103, "flag": -1}]}
        seq = [(step, obs, []) for step in range(0, 100)]
        res = self.s.census_sequence(seq, SEAT, FACTION, edges)["counts"]
        self.assertEqual((res["unit_steps"], res["unit_steps_blocked"], res["unit_steps_deadlocked"]), (800, 800, 800))
        self.assertEqual(res["ps1b_trigger_steps"], 100 - 51)  # stalled once more than 2 * 20 + 10 steps passed
        mover = dict(a[0], obj_id=20, cur_hex=103, move_path=[102])  # 102 is full: blocked; then a free mover
        freely = dict(a[0], obj_id=21, cur_hex=101, move_path=[])
        obs2 = dict(obs, operators=[freely, mover],
                    role_and_grouping_info={SEAT: {"operators": [20, 21]}})
        res2 = self.s.census_sequence([(0, obs2, [])], SEAT, FACTION, edges)["counts"]
        self.assertEqual((res2["unit_steps_moving"], res2["unit_steps_blocked"]), (1, 0))
        free = {"role_and_grouping_info": {SEAT: {"operators": [1]}}, "operators": [dict(a[0], move_path=[])],
                "cities": [{"coord": 103, "flag": -1}]}
        res = self.s.census_sequence([(0, free, [{"type": 1, "obj_id": 1, "move_path": [102, 103]}])], SEAT, FACTION,
                                     edges)["counts"]
        self.assertEqual((res["orders"], res.get("ps1a_would_change_order", 0)), (1, 0))


if __name__ == "__main__":
    unittest.main()
