"""Sprint 34 MODEL WORLD mechanics on a synthetic scenario (SYNTHETIC: invented map, units and numbers)."""

from __future__ import annotations

import unittest

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.evaluation.s34_world import SEATS, ModelWorld
from miaosuan_agent.integrated import facts as F
from tests.fixtures import s34_states as S


def scenario(units, cities=(), max_time=400):
    return {"scenario_id": 900000034, "time": {"cur_step": 0, "tick": 1.0, "max_time": max_time},
            "cities": [dict(c) for c in cities], "operators": [dict(u) for u in units]}


def play(world, red=(), blue=(), steps=1):
    for _ in range(steps):
        world.step({0: list(red), 1: list(blue)})
        red, blue = (), ()


class ModelWorldTests(unittest.TestCase):
    def setUp(self):
        self.costs = MoveCosts.from_raw(S.costs())

    def started(self, units, cities=()):
        w = ModelWorld(scenario(units, cities), self.costs)
        w.step({0: [{"actor": SEATS[0], "type": F.END_DEPLOYMENT}], 1: [{"actor": SEATS[1], "type": F.END_DEPLOYMENT}]})
        self.assertEqual(w.stage, 2)
        return w

    def test_observations_pass_the_boundary(self):
        w = self.started([S.unit(900101, 0, 101), S.unit(900201, 1, 1111)])
        for color in (0, 1):
            Observation.from_raw(w.observation(color)).validate()

    def test_hex_time_entry_and_arrival_transition(self):
        w = self.started([S.unit(900101, 0, 101)])
        move = {"actor": SEATS[0], "type": F.MOVE, "obj_id": 900101, "move_path": [102, 103]}
        play(w, red=[move])
        unit = w.units[900101]
        self.assertEqual(unit["cur_hex"], 101)
        play(w, steps=19)
        self.assertEqual(unit["cur_hex"], 102)  # entered after exactly 20 steps
        play(w, steps=20)
        self.assertEqual(unit["cur_hex"], 103)
        self.assertEqual(unit["move_path"], [])
        self.assertEqual(unit["move_to_stop_remain_time"], F.TRANSITION)
        self.assertIn(F.MOVE, w.listing(unit, []))

    def test_stacking_limit_waits_and_restarts(self):
        units = [S.unit(900110 + i, 0, 102) for i in range(4)] + [S.unit(900101, 0, 101)]
        w = self.started(units)
        play(w, red=[{"actor": SEATS[0], "type": F.MOVE, "obj_id": 900101, "move_path": [102]}], steps=40)
        self.assertEqual(w.units[900101]["cur_hex"], 101)
        self.assertEqual(w.units[900101]["speed"], 0)
        self.assertEqual(w.max_wait[900101], 40)
        play(w, red=[{"actor": SEATS[0], "type": F.MOVE, "obj_id": 900110, "move_path": [103]}], steps=20)
        self.assertEqual(w.units[900110]["cur_hex"], 103)
        self.assertEqual(w.units[900101]["cur_hex"], 101)  # restart needs a full hex time
        play(w, steps=20)
        self.assertEqual(w.units[900101]["cur_hex"], 102)

    def test_occupation_needs_a_clear_zone(self):
        city = S.city(505)
        w = self.started([S.unit(900101, 0, 505), S.unit(900201, 1, 506)], [city])
        self.assertNotIn(F.OCCUPY, w.listing(w.units[900101], []))
        w2 = self.started([S.unit(900101, 0, 505), S.unit(900201, 1, 808)], [city])
        self.assertIn(F.OCCUPY, w2.listing(w2.units[900101], []))
        play(w2, red=[{"actor": SEATS[0], "type": F.OCCUPY, "obj_id": 900101}])
        self.assertEqual(w2.cities[0]["flag"], 0)

    def test_embark_and_disembark_take_75_steps(self):
        inf = S.unit(900101, 0, 101, type_=1, sub_type=2, basic_speed=5, value=4)
        car = S.unit(900102, 0, 101, sub_type=1, passenger_types=[2, 4, 7], value=8)
        w = self.started([inf, car])
        self.assertEqual(w.listing(w.units[900101], [])[F.GET_ON], [{"target_obj_id": 900102}])
        play(w, red=[{"actor": SEATS[0], "type": F.GET_ON, "obj_id": 900101, "target_obj_id": 900102}], steps=74)
        self.assertIn(900101, w.units)
        play(w, steps=1)
        self.assertNotIn(900101, w.units)
        self.assertEqual(w.units[900102]["passenger_ids"], [900101])
        self.assertEqual(w.listing(w.units[900102], [])[F.GET_OFF], [{"target_obj_id": 900101}])
        play(w, red=[{"actor": SEATS[0], "type": F.GET_OFF, "obj_id": 900102, "target_obj_id": 900101}], steps=75)
        self.assertEqual(w.units[900101]["cur_hex"], 101)

    def test_refuses_unlisted_actions(self):
        w = self.started([S.unit(900101, 0, 101, sub_type=3, value=0)])
        play(w, red=[{"actor": SEATS[0], "type": F.MOVE, "obj_id": 900101, "move_path": [102]}])
        self.assertEqual(len(w.refused), 1)


if __name__ == "__main__":
    unittest.main()
