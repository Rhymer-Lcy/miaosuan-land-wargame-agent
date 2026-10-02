"""T7 design study: exposure and witness scoring, the rubric's computed anchors and the shadow's contract check."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STUDY = script("t7_study")
RUBRIC = script("t7_rubric")
SHADOW = script("t7_shadow")
UNIT, ENEMY = 5, 90


def row(k, *, stop=1, path=False, hex_=303, acted=(), enemies=None, ids=(), judged=()):
    return {"cur_step": k, "own": {UNIT: (hex_, stop, path)}, "enemies": dict(enemies or {}), "judged": set(judged),
            "acted": set(acted), "listed_ids": set(ids)}


def table(n=200, **changes):
    rows = {k: row(k) for k in range(1, n + 1)}
    for k, values in changes.items():
        rows[int(k)] = row(int(k), **values)
    return rows


class A2Scoring(unittest.TestCase):
    act = {"unit": UNIT, "k": 10}

    def test_exposure_window_is_75_steps(self):
        mine = table(**{"85": {"acted": (UNIT,)}})
        self.assertTrue(STUDY.score("A2", self.act, mine, None, 200)[0])
        mine = table(**{"86": {"acted": (UNIT,)}})
        self.assertFalse(STUDY.score("A2", self.act, mine, None, 200)[0])

    def test_witness_while_idle_through_the_opposing_view_or_judge_info(self):
        theirs = table(**{"40": {"ids": (UNIT,)}})
        self.assertTrue(STUDY.score("A2", self.act, table(), theirs, 200)[1])
        self.assertTrue(STUDY.score("A2", self.act, table(**{"50": {"judged": (UNIT,)}}), None, 200)[1])
        self.assertFalse(STUDY.score("A2", self.act, table(), table(), 200)[1])

    def test_no_witness_after_the_unit_moves_or_acts(self):
        theirs = table(**{"40": {"ids": (UNIT,)}})
        self.assertFalse(STUDY.score("A2", self.act, table(**{"30": {"stop": 0}}), theirs, 200)[1])
        self.assertFalse(STUDY.score("A2", self.act, table(**{"30": {"path": True}}), theirs, 200)[1])
        self.assertFalse(STUDY.score("A2", self.act, table(**{"30": {"acted": (UNIT,)}}), theirs, 200)[1])


class StopScoring(unittest.TestCase):
    def test_b1_witness_needs_the_enemy_in_range_for_hex_time_plus_75(self):
        act = {"unit": UNIT, "k": 10, "record": {"enemy": ENEMY, "range": 10}, "hex_time": 20.0,
               "path_ends_at_objective": True}
        near = {k: row(k, enemies={ENEMY: (308, 2)}) for k in range(1, 200)}
        exposure, witness = STUDY.score("B1", act, near, None, 199)
        self.assertTrue(exposure)
        self.assertTrue(witness)
        far = dict(near)
        far[60] = row(60, enemies={ENEMY: (320, 2)})
        self.assertFalse(STUDY.score("B1", act, far, None, 199)[1])
        gone = dict(near)
        gone[104] = row(104)
        self.assertFalse(STUDY.score("B1", act, gone, None, 199)[1])
        self.assertIsNone(STUDY.score("B1", dict(act, hex_time=None), near, None, 199)[1])

    def test_b2_witness_on_entering_the_next_hex(self):
        act = {"unit": UNIT, "k": 10, "record": {"next": 304}, "path_ends_at_objective": False}
        mine = {k: row(k, hex_=303 if k < 30 else 304) for k in range(1, 100)}
        theirs = {k: row(k, ids=(UNIT,) if k == 30 else ()) for k in range(1, 100)}
        self.assertEqual(STUDY.score("B2", act, mine, theirs, 99), (False, True))
        theirs[30] = row(30)
        self.assertEqual(STUDY.score("B2", act, mine, theirs, 99), (False, False))
        self.assertEqual(STUDY.score("B2", act, mine, None, 99), (False, None))


class RubricAnchors(unittest.TestCase):
    def entry(self, scenarios, archetypes, activations=10, exposure=0):
        return {"scenarios": [str(i) for i in range(scenarios)], "archetypes": {str(i): 1 for i in range(archetypes)},
                "activations": activations, "exposure": exposure}

    def test_generality(self):
        cases = [((8, 3), 5), ((8, 2), 4), ((6, 9), 4), ((5, 9), 3), ((4, 1), 3), ((3, 9), 2), ((2, 9), 2), ((1, 9), 1),
                 ((0, 0), 0)]
        for (n, a), expected in cases:
            with self.subTest(n=n, archetypes=a):
                self.assertEqual(RUBRIC.generality(self.entry(n, a))[0], expected)

    def test_opportunity_cost(self):
        cases = [(0, 5), (1, 5), (2, 4), (5, 4), (6, 3), (15, 3), (16, 2), (30, 2), (31, 1), (100, 1)]
        for exposed, expected in cases:
            with self.subTest(exposed=exposed):
                self.assertEqual(RUBRIC.opportunity(self.entry(1, 1, 100, exposed))[:2], (expected, False))
        self.assertEqual(RUBRIC.opportunity(self.entry(0, 0, 0, 0))[:2], (RUBRIC.CAP, True))


class SensitivityUnknownCells(unittest.TestCase):
    def test_unknown_cells_take_the_variant_value(self):
        weights = {"G": 0.5, "L": 0.5}
        row = {"G": {"score": 2, "unknown": True}, "L": {"score": 4, "unknown": False}}
        self.assertEqual(RUBRIC.weighted(row, weights), 3.0)
        self.assertEqual(RUBRIC.weighted(row, weights, 0), 2.0)
        self.assertEqual(RUBRIC.weighted(row, weights, 5), 4.5)


class ShadowContract(unittest.TestCase):
    def test_contract_check_reads_the_raw_listing(self):
        raw = {"valid_actions": {7: {6: [{"target_state": 5}, {"target_state": 4}]}, 8: {6: [{"target_state": 5}]}}}
        good = {"actor": 1, "obj_id": 7, "type": 6, "target_state": 4}
        self.assertTrue(SHADOW.contract_ok(good, raw))
        self.assertFalse(SHADOW.contract_ok(dict(good, obj_id=8), raw))
        self.assertFalse(SHADOW.contract_ok(dict(good, obj_id=9), raw))
        self.assertFalse(SHADOW.contract_ok(dict(good, extra=1), raw))
        self.assertFalse(SHADOW.contract_ok(dict(good, type=1), raw))


if __name__ == "__main__":
    unittest.main()
