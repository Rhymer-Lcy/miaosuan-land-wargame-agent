"""T7 design study: the audit, its independent cross-count and the candidate-pool predicates on synthetic data."""

from __future__ import annotations

import collections
import copy
import unittest

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.evaluation import t7_audit as ta
from miaosuan_agent.evaluation import t7_candidates as tc
from miaosuan_agent.evaluation.t7_crosscheck import CrossCount, agree

from tests.fixtures import synthetic as syn

OWN, ENEMY = 0, 1


def unit(obj_id, hex_, *, color=OWN, unit_type=2, sub_type=1, move_state=0, stop=1, path=(), speed=0.0, cs=0.0,
         mts=0.0, unfold=1, keep=0, tire=0, a1=0, weapons=(43,), basic_speed=36):
    return {"obj_id": obj_id, "color": color, "type": unit_type, "sub_type": sub_type, "cur_hex": hex_,
            "move_state": move_state, "stop": stop, "move_path": list(path), "speed": speed,
            "change_state_remain_time": cs, "move_to_stop_remain_time": mts, "weapon_unfold_state": unfold,
            "weapon_unfold_time": 0.0, "keep": keep, "tire": tire, "A1": a1, "carry_weapon_ids": list(weapons),
            "basic_speed": basic_speed, "passenger_ids": [], "target_state": 0, "can_to_move": 1, "flag_force_stop": 0,
            "tire_accumulate_time": 0, "get_on_remain_time": 0.0, "get_off_remain_time": 0.0}


def obs(units, valid, *, stage=2, cur_step=10, cities=(505,), judge=()):
    seats = {syn.RED_SEAT: syn.seat_record(syn.RED_SEAT, OWN, [u["obj_id"] for u in units if u["color"] == OWN], True)}
    raw = syn.build_observation(units=units, valid_actions=valid, seats=seats, stage=stage, cur_step=cur_step,
                                cities=[syn.city(c) for c in cities])
    raw["judge_info"] = [dict(r) for r in judge]
    raw["landmarks"]["roadblocks"] = []
    return raw


class AuditCounts(unittest.TestCase):
    def setUp(self):
        self.idle = unit(1, 303)
        self.moving = unit(2, 304, stop=0, path=[305], speed=0.05)
        self.locked = unit(3, 306, unfold=0)
        self.enemy = unit(9, 808, color=ENEMY)
        self.raw = obs([self.idle, self.moving, self.locked, self.enemy], {
            1: {6: [{"target_state": 4}, {"target_state": 0}], 10: None, 11: None},
            2: {10: None, 1: None},
            3: {11: None, 6: [{"target_state": 0}]},
            7: {6: [{"target_state": 2}]},  # a passenger: listed, not in operators
        })

    def test_counts_one_two_four_six_seven(self):
        audit = ta.Audit()
        audit.add("g", OWN, self.raw, [{"actor": 7, "obj_id": 2, "type": 1, "move_path": [305]},
                                        {"actor": 7, "obj_id": 3, "type": 11}])
        s = audit.summary()
        self.assertEqual(s["decisions_listing"], {"play:6": 1, "play:10": 1, "play:11": 1})
        self.assertEqual(s["unit_listings"], {"play:6": 3, "play:10": 2, "play:11": 2})
        self.assertEqual(s["issued"], {"play:11": 1})
        self.assertEqual(s["change_state_options"], {"play:2.1:0": 2, "play:2.1:4": 1, "play:None:2": 1})
        self.assertEqual(s["frozen_policy_instead"]["play:10:move"], 1)
        self.assertEqual(s["frozen_policy_instead"]["play:10:nothing"], 1)
        self.assertEqual(s["frozen_policy_instead"]["play:11:type 11"], 1)
        self.assertEqual(s["no_executable_opportunity"], {
            "play:10:empty move path": 1, "play:11:already locked": 1, "play:6:only the current state": 1,
            "play:6:unit not in operators": 1})

    def test_enemy_listings_are_ignored_and_missing_fields_counted(self):
        raw = copy.deepcopy(self.raw)
        raw["valid_actions"][9] = {10: None}
        del raw["operators"][0]["tire"]
        audit = ta.Audit()
        audit.add("g", OWN, raw, [])
        s = audit.summary()
        self.assertEqual(s["unit_listings"]["play:10"], 2)
        self.assertEqual(s["missing_fields"], {"play:tire": 1})

    def test_malformed_options_are_counted_not_repaired(self):
        raw = copy.deepcopy(self.raw)
        raw["valid_actions"][1][6] = [{"target_state": "4"}, {"other": 1}, {"target_state": 4}]
        audit = ta.Audit()
        audit.add("g", OWN, raw, [])
        s = audit.summary()
        self.assertEqual(s["malformed_options"], {"play:6": 2})
        self.assertEqual(s["change_state_options"]["play:2.1:4"], 1)

    def test_fingerprint_ignores_option_order_and_identifiers(self):
        a = ta.fingerprint("A", self.idle, {6: [{"target_state": 4}, {"target_state": 0}], 10: None}, False)
        b = ta.fingerprint("A", dict(self.idle, obj_id=77, cur_hex=909),
                           {10: None, 6: [{"target_state": 0}, {"target_state": 4}]}, False)
        self.assertEqual(a, b)
        self.assertNotEqual(a, ta.fingerprint("A", dict(self.idle, move_state=4), {6: [{"target_state": 0}]}, False))
        self.assertNotEqual(a, ta.fingerprint("A", self.idle, {6: [{"target_state": 4}, {"target_state": 0}],
                                                                10: None}, True))

    def test_no_opportunity_reasons(self):
        waiting = unit(5, 303, stop=0, path=[304], speed=0)
        self.assertEqual(ta.no_opportunity(10, waiting, None),
                         "speed 0 with a move path (ground unit; the Sprint 4 case when its next hex is full)")
        self.assertEqual(ta.no_opportunity(10, dict(waiting, type=3), None), "speed 0 with a move path (aircraft)")
        self.assertIsNone(ta.no_opportunity(10, self.moving, None))
        self.assertEqual(ta.no_opportunity(12, self.idle, None), "already unfolded")
        self.assertIsNone(ta.no_opportunity(12, self.locked, None))
        self.assertEqual(ta.no_opportunity(6, self.idle, [{"x": 1}]), "no well-formed option")
        self.assertEqual(ta.no_opportunity(10, dict(self.idle, move_path=None), None), "move path missing")


class CrossCheck(unittest.TestCase):
    def raws(self):
        base = AuditCounts()
        base.setUp()
        out = [base.raw]
        second = copy.deepcopy(base.raw)
        second["time"]["stage"] = 1
        second["valid_actions"][2] = {12: None}
        out.append(second)
        third = copy.deepcopy(base.raw)
        third["operators"] = [u for u in third["operators"] if u["color"] == OWN]
        out.append(third)
        return out

    def counts(self, raws):
        audit, cross = ta.Audit(), CrossCount()
        for raw in raws:
            audit.add("g", OWN, raw, [])
            cross.add(Observation.from_raw(raw, Origin.ENGINE), OWN)
        return audit.summary(), cross.summary()

    def test_independent_count_agrees(self):
        a, c = self.counts(self.raws())
        self.assertTrue(agree(a, c)["agree"], (a, c))
        self.assertEqual(a["distinct_situations"]["play:A"], 6)  # three units, with and without an enemy seen

    def test_a_planted_disagreement_is_reported(self):
        raws = self.raws()
        audit = ta.Audit()
        for raw in raws:
            audit.add("g", OWN, raw, [])
        cross = CrossCount()
        for raw in raws[:2]:
            cross.add(Observation.from_raw(raw, Origin.ENGINE), OWN)
        self.assertFalse(agree(audit.summary(), cross.summary())["agree"])


class TransitionEpisodes(unittest.TestCase):
    def test_change_state_episode_arrival_gap_and_censoring(self):
        tr = ta.Transitions()
        seq = [
            (10, unit(1, 303, cs=75.0), unit(2, 304, stop=0, path=[305], speed=0.05), {}),
            (11, unit(1, 303, cs=74.0), unit(2, 305, stop=0, path=[], speed=0.0, mts=75.0), {}),
            (12, unit(1, 303, cs=0.0, move_state=4), unit(2, 305, stop=0, path=[], mts=74.0), {}),
            (13, unit(1, 303, move_state=4), unit(2, 305, stop=1, path=[]), {2: {1: None}}),
        ]
        for step, u1, u2, valid in seq:
            tr.add(step, OWN, obs([u1, u2], valid, cur_step=step))
        tr.add(20, OWN, obs([unit(1, 303, cs=5.0, move_state=4)], {}, cur_step=20))
        tr.finish()
        ends = collections.Counter((e["field"], e["end"], e["steps"]) for e in tr.episodes)
        self.assertEqual(ends[("change_state_remain_time", "completed", 2)], 1)
        self.assertEqual(ends[("move_to_stop_remain_time", "completed", 2)], 1)
        self.assertEqual(ends[("change_state_remain_time", "censored at the last observation", 1)], 1)
        self.assertEqual(tr.gaps, 1)
        self.assertEqual(tr.changes["move_state:2.1:0->4"], 1)
        settled = [a for a in tr.arrival_rows if a["end"] == "settled"]
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["stop_after"], 2)
        self.assertEqual(settled[0]["listed_after"], {"move": 2})

    def test_unit_gone_closes_its_episodes(self):
        tr = ta.Transitions()
        tr.add(1, OWN, obs([unit(1, 303, cs=10.0)], {}, cur_step=1))
        tr.add(2, OWN, obs([], {}, cur_step=2))
        self.assertEqual([(e["field"], e["end"]) for e in tr.episodes], [("change_state_remain_time", "unit gone")])


class PoolPredicates(unittest.TestCase):
    def setUp(self):
        self.memory = tc.SeatMemory()

    def a2(self, u, valid=None, v2=None, seen=False, step=10):
        valid = {6: [{"target_state": 4}]} if valid is None else valid
        return tc.a2(u, valid, v2, seen, step, self.memory)

    def test_a2_fires_only_on_idle_eligible_units(self):
        self.assertIsNotNone(self.a2(unit(1, 303)))
        for name, u in (("moving", unit(1, 303, stop=0, path=[304], speed=0.05)), ("suppressed", unit(1, 303, keep=1)),
                        ("concealed", unit(1, 303, move_state=4)), ("in transition", unit(1, 303, cs=3.0)),
                        ("stopping", unit(1, 303, mts=3.0)), ("aircraft", unit(1, 303, unit_type=3))):
            with self.subTest(name):
                self.memory = tc.SeatMemory()
                self.assertIsNone(self.a2(u))
        self.memory = tc.SeatMemory()
        missing = unit(1, 303)
        missing["change_state_remain_time"] = None
        self.assertIsNone(self.a2(missing))
        self.assertIsNone(self.a2(unit(1, 303), valid={6: [{"target_state": 0}]}))
        self.assertIsNone(self.a2(unit(1, 303), v2={"obj_id": 1, "type": 1}))
        self.assertIsNone(self.a2(unit(1, 303), seen=True))

    def test_a2_memory_blocks_repeats_for_one_transition(self):
        self.assertEqual(self.a2(unit(1, 303), step=10), {"repeat": False})
        self.assertIsNone(self.a2(unit(1, 303), step=84))
        self.assertEqual(self.a2(unit(1, 303), step=85), {"repeat": True})

    def test_b1_stop_to_engage(self):
        moving = unit(1, 303, stop=0, path=[304], speed=0.05, weapons=(43,))
        near, far = unit(9, 308, color=ENEMY, unit_type=1), unit(9, 316, color=ENEMY, unit_type=1)
        raw_near = obs([moving, near], {1: {10: None}})
        self.assertEqual(tc.b1(moving, {10: None}, raw_near, OWN)["distance"], 5)
        self.assertIsNone(tc.b1(moving, {10: None}, obs([moving, far], {1: {10: None}}), OWN))
        waiting = dict(moving, speed=0)
        self.assertIsNone(tc.b1(waiting, {10: None}, obs([waiting, near], {1: {10: None}}), OWN))
        self.assertIsNone(tc.b1(dict(moving, A1=1), {10: None}, raw_near, OWN))
        self.assertIsNone(tc.b1(moving, {1: None}, raw_near, OWN))
        unknown = dict(moving, carry_weapon_ids=[5])
        self.assertIsNone(tc.b1(unknown, {10: None}, obs([unknown, near], {1: {10: None}}), OWN))

    def test_b2_entering_observation_range(self):
        mover = unit(1, 312, stop=0, path=[313], speed=0.05)
        watcher = unit(9, 303, color=ENEMY, unit_type=1)  # infantry observes vehicles at 25
        self.assertIsNone(tc.b2(mover, {10: None}, obs([mover, watcher], {}), OWN))
        far = dict(watcher, cur_hex=303 - 0)
        mover_far = unit(1, 329, stop=0, path=[328], speed=0.05)
        record = tc.b2(mover_far, {10: None}, obs([mover_far, far], {}), OWN)
        self.assertEqual(tc.hex_distance(303, 328), 25)
        self.assertEqual(tc.hex_distance(303, 329), 26)
        self.assertEqual(record, {"next": 328, "enemy": 9})

    def test_a1_documented_saving(self):
        rows = cols = 10
        costs_raw = syn.cost_data(rows, cols, cost=1)
        for r in range(rows):
            for c in range(cols):
                costs_raw[1][r][c] = {n: 1 for n in syn.grid_neighbours(r * 100 + c, rows, cols) if n // 100 == r}
        costs = MoveCosts.from_raw(costs_raw, Origin.ENGINE)
        router = Router(costs)
        start = 0
        u = unit(1, start)
        u["sub_type"] = 0
        path = list(range(1, 10))
        raw = obs([u], {})
        record = tc.a1(u, {11: None}, {"obj_id": 1, "type": 1, "move_path": path}, raw, OWN, costs, router)
        self.assertIsNone(record)  # 9 hexes: 180 s normal against 72 + 300 s
        long_costs = syn.cost_data(rows, cols, cost=5)
        for r in range(rows):
            for c in range(cols):
                long_costs[1][r][c] = {n: 1 for n in syn.grid_neighbours(r * 100 + c, rows, cols) if n // 100 == r}
        costs = MoveCosts.from_raw(long_costs, Origin.ENGINE)
        record = tc.a1(u, {11: None}, {"obj_id": 1, "type": 1, "move_path": path}, raw, OWN, costs, Router(costs))
        self.assertEqual((record["t0"], record["t1"], record["saving"]), (900.0, 72.0, 528.0))
        self.assertFalse(record["march_option_listed"])
        artillery = dict(u, sub_type=3)
        self.assertIsNone(tc.a1(artillery, {}, {"obj_id": 1, "type": 1, "move_path": path}, raw, OWN, costs,
                                Router(costs)))

    def test_a3_final_approach(self):
        inf = unit(1, 503, unit_type=1, sub_type=2)
        raw = obs([inf], {}, cities=(505,))
        valid = {6: [{"target_state": 2}]}
        self.assertEqual(tc.a3(inf, valid, {"type": 1, "move_path": [504, 505]}, raw, OWN), {"hexes": 2})
        self.assertIsNone(tc.a3(inf, valid, {"type": 1, "move_path": [504, 505, 506]}, raw, OWN))
        self.assertIsNone(tc.a3(inf, valid, {"type": 1, "move_path": [504]}, raw, OWN))
        self.assertIsNone(tc.a3(dict(inf, tire=1), valid, {"type": 1, "move_path": [504, 505]}, raw, OWN))

    def test_evaluate_runs_only_in_play_and_never_fires_c0(self):
        raw = obs([unit(1, 303)], {1: {6: [{"target_state": 4}], 11: None}})
        costs = MoveCosts.from_raw(syn.cost_data(), Origin.ENGINE)
        acts = tc.evaluate(raw, OWN, [], costs, Router(costs), tc.SeatMemory())
        self.assertEqual([a[0] for a in acts], ["A2"])
        raw["time"]["stage"] = 1
        self.assertEqual(tc.evaluate(raw, OWN, [], costs, Router(costs), tc.SeatMemory()), [])


class Constants(unittest.TestCase):
    def test_hex_distance_equals_breadth_first_search(self):
        rows = cols = 10
        hexes = [r * 100 + c for r in range(rows) for c in range(cols)]
        for start in (0, 105, 404, 909, 509):
            dist = {start: 0}
            queue = collections.deque([start])
            while queue:
                h = queue.popleft()
                for n in syn.grid_neighbours(h, rows, cols):
                    if n not in dist:
                        dist[n] = dist[h] + 1
                        queue.append(n)
            for h in hexes:
                self.assertEqual(tc.hex_distance(start, h), dist[h], (start, h))

    def test_published_ranges_and_observation_distances(self):
        self.assertEqual(tc.weapon_range([36, 43], 2), 18)
        self.assertEqual(tc.weapon_range([36, 43], 1), 10)
        self.assertEqual(tc.weapon_range([29], 1), 3)
        self.assertIsNone(tc.weapon_range([89, 5], 2))
        self.assertIsNone(tc.weapon_range([36], 3))
        self.assertEqual(tc.observation_distance({"type": 3, "sub_type": 5}, 2), 2)
        self.assertEqual(tc.observation_distance({"type": 1, "sub_type": 2}, 2), 25)
        self.assertEqual(tc.observation_distance({"type": 2, "sub_type": 0}, 1), 10)


if __name__ == "__main__":
    unittest.main()
