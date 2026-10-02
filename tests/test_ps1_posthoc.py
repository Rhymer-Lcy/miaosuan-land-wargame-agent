"""The PS-1 post-hoc descriptions (``scripts/ps1_posthoc.py``) on SYNTHETIC observation sequences.

The entry rule under three processing orders (and its keep-flag classification), the restart trace with a refill
(traversal and wait runs), the split of outside-window episodes, and deadlock episodes released by a holder's order or
by a unit leaving the observation.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAT = 1
EDGES_1 = {}
for a, b in ((1, 2), (2, 3), (3, 4)):
    EDGES_1.setdefault(a, {})[b] = 1.0
    EDGES_1.setdefault(b, {})[a] = 1.0
EDGES = {0: EDGES_1, 1: EDGES_1, 2: EDGES_1, 3: {}}


def load_script():
    spec = importlib.util.spec_from_file_location("ps1_posthoc", ROOT / "scripts" / "ps1_posthoc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def op(uid, hex_, path=(), speed=0.0, keep=0):
    return {"obj_id": uid, "type": 2, "cur_hex": hex_, "move_path": list(path), "speed": speed, "basic_speed": 36,
            "on_board": 0, "move_state": 0, "keep": keep}


def obs(units, cities=()):
    return {"operators": units, "role_and_grouping_info": {SEAT: {"operators": [u["obj_id"] for u in units]}},
            "cities": [{"coord": c} for c in cities]}


class EntryRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ph = load_script()

    def test_lower_index_fills_the_next_hex_first(self) -> None:
        holders = [op(i, 3) for i in (20, 21, 22)]
        before = obs(holders + [op(1, 2, (3,), 0.05), op(5, 1, (2, 3), 0.05)])
        after = obs(holders + [op(1, 3), op(5, 2, (3,), 0.0)])  # 1 fills hex 3, then 5 enters 2 and waits at once
        t = self.ph.entry_rule([(10, before), (11, after)], SEAT)
        self.assertEqual((t["entries"], t["waited at once"]), (1, 1))
        self.assertEqual((t["ascending agrees"], t["descending disagrees"], t["end of step agrees"]), (1, 1, 1))

    def test_higher_index_fills_the_next_hex_afterwards(self) -> None:
        holders = [op(i, 3) for i in (20, 21, 22)]
        before = obs(holders + [op(2, 1, (2, 3), 0.05), op(9, 2, (3,), 0.05)])
        after = obs(holders + [op(2, 2, (3,), 0.05), op(9, 3)])  # 2 started while hex 3 still had room
        t = self.ph.entry_rule([(10, before), (11, after)], SEAT)
        self.assertEqual((t["ascending agrees"], t["descending disagrees"], t["end of step disagrees"]), (1, 1, 1))

    def test_keep_flag_disagreement_and_skipped_gap(self) -> None:
        before = obs([op(3, 1, (2, 3), 0.05)])
        after = obs([op(3, 2, (3,), 0.0, keep=1)])  # speed 0 with an empty next hex
        t = self.ph.entry_rule([(10, before), (11, after), (13, after)], SEAT)
        self.assertEqual(t["ascending disagreements with the keep flag set"], 1)
        self.assertEqual(t["ascending disagreements with the next hex not full"], 1)
        self.assertEqual(t["skipped transitions"], 1)


class RestartTraceTest(unittest.TestCase):
    def test_refill_produces_a_rewait_between_two_traversals(self) -> None:
        study = load_script().study
        seq = []
        for step in range(0, 70):
            in_two = [1, 2, 3] + ([4] if step < 10 else []) + ([6] if 15 <= step < 40 else [])
            units = [op(i, 2) for i in in_two]
            if step < 59:
                moving = 10 <= step <= 28 or 40 <= step <= 58
                units.append(op(5, 1, (2,), 0.05 if moving else 0.0))
            else:
                units.append(op(5, 2))
            seq.append((step, obs(units)))
        eps = study.restart_episodes(seq, SEAT, 0, EDGES, trace=True)
        self.assertEqual([(e["d"], e["tau"]) for e in eps], [(49, 20)])
        self.assertEqual(eps[0]["runs"], [(1, 19, 3), (0, 11, 4), (1, 19, 3)])
        self.assertNotIn("runs", study.restart_episodes(seq, SEAT, 0, EDGES)[0])

    def test_outside_windows_split(self) -> None:
        ph = load_script()
        eps = [{"d": 58, "tau": 20, "runs": [(1, 19, 2), (0, 20, 4), (1, 19, 3)]},
               {"d": 18, "tau": 20, "runs": [(1, 18, 2)]},  # in the M1b window (|18 - 19| <= 1): excluded
               {"d": 71, "tau": 20, "runs": [(0, 1, 4), (1, 25, 2), (0, 26, 3), (1, 19, 3)]}]  # opens waiting
        r = ph.outside_windows(eps)
        self.assertEqual((r["episodes"], r["traversals"], r["traversals_of_tau_minus_1"],
                          r["traversals_within_1_of_tau_minus_1"]), (2, 4, 3, 3))
        self.assertEqual((r["rewaits"], r["rewaits_beginning_with_the_target_full"]), (2, 1))


class DeadlockEpisodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ph = load_script()

    def chain(self, release):
        seq = []
        for step in range(0, 110):
            holders = [op(i, 2) for i in (1, 2, 3, 4)]
            if step >= 100 and release == "order":
                holders[0] = op(1, 2, (3,), 0.05)
            if step >= 100 and release == "removed":
                holders = holders[1:]
            waiting = ([op(5, 1, (2,), 0.0)] if step >= 5 else []) + ([op(6, 1, (2,), 0.0)] if step >= 30 else [])
            seq.append((step, obs(holders + waiting, cities=(2,))))
        return self.ph.deadlock_episodes(seq, SEAT, EDGES)

    def test_released_by_a_holder_order(self) -> None:
        (e,) = self.chain("order")
        self.assertEqual((e["start"], e["end"], e["steps"], e["kind"], e["max_units"]), (5, 99, 95, "chain", 2))
        # every deadlocked unit must be stalled: the later arrival (from 30) is stalled only after 2 * 20 + 10 steps
        self.assertEqual((e["trigger_steps"], e["trigger_latency"], e["holders_on_objective"]), (19, 76, True))
        self.assertEqual(e["released_by"], ["a holder received an order"])

    def test_released_by_removal_and_lasting(self) -> None:
        self.assertEqual(self.chain("removed")[0]["released_by"], ["removed from the observation"])
        (e,) = self.chain("none")
        self.assertEqual((e["end"], e["released_by"]), (109, ["lasted to the end of the game"]))


if __name__ == "__main__":
    unittest.main()
