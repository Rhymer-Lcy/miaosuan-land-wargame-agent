"""Sprint 32 preflight rules (``evaluation/s32_preflight.py``) on synthetic streams: the independent restatement
against the candidate (agreement on random states, and disagreement on planted defects), opportunity episodes, the
first-divergence validity rule, the recorded-trajectory descriptions, the configuration status and the disposition."""

from __future__ import annotations

import random
import unittest
from unittest import mock

from miaosuan_agent.evaluation import s32_preflight as pf
from miaosuan_agent.experiments import t7_b1_stop_engage as b1
from tests.test_t7_b1_stop_engage import BLUE, RED, SEAT, ZERO_FIELDS, enemy, move, own, raw


def random_state(rng: random.Random, step: int = 100):
    units = []
    for i in range(rng.randint(1, 6)):
        hex_ = rng.choice([1010, 1110, 1210, 1012, 1013])
        length = rng.choice([0, 1, 2, 3])
        path = tuple(hex_ + 1 + j for j in range(length))
        if rng.random() < 0.3:
            path = (1011,) + path[1:] if path else path
        u = own(i + 1, hex_, path=path, speed=rng.choice([0.05] * 6 + [0, 1 / 144, -0.05, None]),
                pos=rng.choice([0.5] * 6 + [0.0, 0.95, 1.0, None]), type_=rng.choice([2] * 6 + [1, 1, 3]),
                weapons=rng.choice([(54, 43)] * 6 + [(29,), (37, 43), (99,), (83,)]),
                A1=rng.choice([0] * 8 + [1, None]))
        if rng.random() < 0.1:
            u[rng.choice(ZERO_FIELDS)] = rng.choice([1, None])
        if rng.random() < 0.05:
            u["weapon_unfold_state"] = 0
        u["see_enemy_bop_ids"] = rng.choice([[900]] * 4 + [[900, 901], [], None])
        units.append(u)
    units.append(enemy(900, rng.choice([1016, 1024, 1025, 1030, 1112]), rng.choice([1, 2, 2, 3])))
    units.append(enemy(901, rng.choice([1014, 1040]), 1))
    listing = {}
    for u in units:
        if u["color"] == BLUE and u.get("move_path"):
            listing[u["obj_id"]] = rng.choice([{10: None}] * 6 + [{1: None}, {10: [{"x": 1}]}])
    controlled = [u["obj_id"] for u in units if u["color"] == BLUE and rng.random() < 0.95]
    observation = raw(units, listing, step=step, end=rng.choice([2880] * 4 + [step + 88, step + 87, step + 60]),
                      controlled=controlled)
    base = []
    if rng.random() < 0.4:
        base.append(move(rng.randint(1, 6), (rng.choice([1011, 2000]), 2001)))
    return observation, base


class IndependentCheckTest(unittest.TestCase):
    def test_agrees_with_the_candidate_on_random_states(self) -> None:
        rng = random.Random(32)
        triggers = 0
        for _ in range(3000):
            observation, base = random_state(rng)
            memory = tuple(sorted({(u, 1) for u in rng.sample(range(1, 7), rng.randint(0, 2))}))
            result = b1.decide(observation, SEAT, BLUE, base, memory)
            self.assertEqual(pf.independent_triggers(observation, SEAT, BLUE, base, {u for u, _ in memory}),
                             set(result.stops))
            triggers += len(result.stops)
        self.assertGreater(triggers, 100)

    def test_catches_planted_defects(self) -> None:
        rng = random.Random(5)
        states = [random_state(rng) for _ in range(3000)]
        plants = [("ROOM_OTHERS", 3), ("END_MARGIN", 0), ("TRANSITION", 74), ("TANK_GUNS", frozenset({36})),
                  ("ZERO_FIELDS", ZERO_FIELDS[:-1]), ("ZERO_FIELDS", ZERO_FIELDS[1:])]
        for name, value in plants:
            with self.subTest(plant=name), mock.patch.object(b1, name, value):
                disagreements = sum(set(b1.decide(o, SEAT, BLUE, base, ()).stops)
                                    != pf.independent_triggers(o, SEAT, BLUE, base, set()) for o, base in states)
                self.assertGreater(disagreements, 0)

    def test_not_play_stage(self) -> None:
        observation = raw([own(1), enemy()], stage=1)
        self.assertEqual(pf.independent_triggers(observation, SEAT, BLUE, [], set()), set())


def stream(frames):
    """(raw, recorded, baseline) rows; ``frames`` is a list of (units, recorded differs) pairs."""
    for k, (units, differs) in enumerate(frames):
        observation = raw(units, step=100 + k)
        observation["cities"] = [{"coord": 1013, "flag": -1, "value": 50}]
        recorded = [move(99, (3000,))] if differs else []
        yield observation, recorded, []


META = {"population": "HI", "label": "HI test", "scenario": "2120531121", "condition": "C3", "faction": BLUE,
        "seat": SEAT}


class SideTest(unittest.TestCase):
    def test_episodes_stops_and_first_divergence(self) -> None:
        moving, idle = own(1, pos=0.5), own(1, path=(), speed=0)
        other = own(2, 1110, path=(1111, 1112))
        frames = [([moving, enemy()], False), ([moving, enemy()], False), ([idle, enemy()], False),
                  ([moving, other, enemy()], False), ([moving, other, enemy()], False)]
        summary, private = pf.analyse_side(META, stream(frames))
        self.assertEqual(summary["eligible_unit_decisions"], 6)
        self.assertEqual(summary["opportunity_episodes"], 3)   # unit 1 twice (a gap), unit 2 once
        self.assertEqual(summary["distinct_units"], 2)
        self.assertEqual(summary["stops"], 2)                  # one per unit and game
        self.assertEqual([s["k"] for s in summary["private"]["stops"]], [0, 3])
        self.assertEqual(summary["first_divergence"]["step"], 100)
        self.assertTrue(summary["first_divergence"]["valid"])
        self.assertTrue(summary["verified_opportunity"])
        self.assertEqual(summary["independent_check_findings"], 0)
        self.assertIn(1011, private)

    def test_h0_validity_needs_a_supported_prefix(self) -> None:
        moving = own(1)
        frames = [([own(1, path=(), speed=0), enemy()], True), ([moving, enemy()], False)]
        summary, _ = pf.analyse_side(dict(META, population="H0"), stream(frames))
        self.assertFalse(summary["first_divergence"]["valid"])
        self.assertFalse(summary["verified_opportunity"])
        summary, _ = pf.analyse_side(dict(META, population="HH"), stream(frames))
        self.assertTrue(summary["first_divergence"]["valid"])
        frames = [([moving, enemy()], False), ([own(1, path=(), speed=0), enemy()], True)]
        summary, _ = pf.analyse_side(dict(META, population="H0"), stream(frames))
        self.assertTrue(summary["first_divergence"]["valid"])

    def test_a_planted_candidate_defect_is_a_finding(self) -> None:
        frames = [([own(1), own(2, 1011, path=(), speed=0), own(3, 1110, path=(1111, 1011), A1=1),
                    own(4, 1210, path=(1211, 1011), A1=1), enemy()], False)]
        summary, _ = pf.analyse_side(META, stream(frames))
        self.assertEqual((summary["stops"], summary["independent_check_findings"]), (0, 0))
        with mock.patch.object(b1, "ROOM_OTHERS", 3):
            summary, _ = pf.analyse_side(META, stream(frames))
        self.assertGreater(summary["independent_check_findings"], 0)
        self.assertFalse(summary["verified_opportunity"])

    def test_descriptions(self) -> None:
        unit = own(1, pos=0.5)              # hex_steps 10: window 10 + 75 + 3 = 88 steps
        names = {1013: "50-point objective A"}
        frames = [{"step": 100 + k, "own": {1: (1010, 10, False)}, "enemy": {900: 1016},
                   "flags": {1013: -1}} for k in range(100)]
        stop = {"k": 0, "step": 100, "unit": 1, "target": 900, "next_hex": 1011, "range": 13, "hex_steps": 10,
                "destination": 1013}
        out = pf.describe(dict(stop), frames, BLUE, names)
        self.assertEqual(out["window_steps"], 88)
        self.assertTrue(out["witness_target_in_view_and_range_through_window"])
        self.assertFalse(out["unit_lost_in_window"] or out["unit_damaged_in_window"])
        self.assertTrue(out["path_ends_at_unheld_objective"])
        self.assertFalse(out["side_first_owned_it_in_window"])
        far = list(frames)
        far[50] = dict(far[50], enemy={900: 1025})       # still in view, 14 hexes from the stop hex: out of range
        self.assertFalse(pf.describe(dict(stop), far, BLUE, names)["witness_target_in_view_and_range_through_window"])
        far[50] = dict(far[50], enemy={900: 1024})       # 13 hexes: in range
        self.assertTrue(pf.describe(dict(stop), far, BLUE, names)["witness_target_in_view_and_range_through_window"])
        frames[88] = dict(frames[88], enemy={}, flags={1013: BLUE}, own={1: (1013, 8, True)})
        out = pf.describe(dict(stop), frames, BLUE, names)
        self.assertFalse(out["witness_target_in_view_and_range_through_window"])
        self.assertTrue(out["side_first_owned_it_in_window"] and out["unit_damaged_in_window"])
        self.assertTrue(out["shoot_listed_in_window_on_record"])
        frames[89] = dict(frames[89], enemy={}, flags={1013: BLUE}, own={})   # outside the window: ignored
        frames[88] = dict(frames[88], own={})
        out = pf.describe(dict(stop), frames, BLUE, names)
        self.assertTrue(out["unit_lost_in_window"])
        self.assertFalse(out["shoot_listed_in_window_on_record"])
        del unit


def side(population, scenario, condition, colour, verified=True, findings=0):
    return {"population": population, "scenario": scenario, "condition": condition, "colour": colour,
            "verified_opportunity": verified, "independent_check_findings": findings}


class DispositionTest(unittest.TestCase):
    hi = [side("HI", "2120531121", "C3", "blue"), side("HI", "1930331196", "C2", "red"),
          side("HI", "1930331196", "C3", "blue", verified=False)]

    def test_configuration_status(self) -> None:
        sides = self.hi + [side("HI", "2130511121", "C2", "red", verified=False)]
        self.assertEqual(pf.configuration_status(sides, "2130511121", "C2", "red"), "NO_OPPORTUNITY")
        self.assertEqual(pf.configuration_status(sides, "2130511121", "C3", "blue"), "NO_FULL_STEP_RECORD")
        self.assertEqual(pf.configuration_status(sides, "2120531121", "C3", "blue"), "VERIFIED")
        self.assertEqual(pf.configuration_status([side("HH", "2120531121", "C3", "blue")], "2120531121", "C3",
                                                 "blue"), "NO_FULL_STEP_RECORD")

    def test_disposition_order(self) -> None:
        self.assertEqual(pf.disposition(False, self.hi)["disposition"], pf.INVALID)
        self.assertEqual(pf.disposition(True, self.hi + [side("HH", "2130511121", "H1", "red", findings=1)])
                         ["disposition"], pf.INVALID)
        verdict = pf.disposition(True, self.hi)
        self.assertEqual(verdict["disposition"], pf.UNVERIFIED)
        self.assertEqual(verdict["verified_inert_configurations"],
                         {"red": ["1930331196 C2"], "blue": ["2120531121 C3"]})
        self.assertEqual(set(verdict["proposed_configurations"].values()), {"NO_FULL_STEP_RECORD"})
        verdict = pf.disposition(True, self.hi[:1])
        self.assertEqual(verdict["disposition"], pf.INADEQUATE)
        self.assertIn("no verified inert configuration for a baseline-v2 red", verdict["reasons"])
        both = self.hi + [side("HI", "2130511121", "C2", "red"), side("HI", "2130511121", "C3", "blue")]
        self.assertEqual(pf.disposition(True, both)["disposition"], pf.PASS)
        half = self.hi + [side("HI", "2130511121", "C2", "red")]
        self.assertEqual(pf.disposition(True, half)["disposition"], pf.UNVERIFIED)


class PublicTest(unittest.TestCase):
    def test_public_side_drops_private_rows(self) -> None:
        frames = [([own(1), enemy()], False), ([own(1), enemy()], False)]
        summary, private = pf.analyse_side(META, stream(frames))
        public = pf.public_side(summary)
        self.assertNotIn("private", public)
        self.assertEqual(public["first_divergence_stop_and_later_stops"]["first"]["stops"], 1)
        from miaosuan_agent.evaluation import s27_probe as sp
        self.assertEqual(sp.public_problems(public, private, {"2120531121"}), [])
        pooled = pf.pooled([summary])
        self.assertEqual((pooled["opportunity_episodes"], pooled["verified_opportunities"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
