"""E3b configuration search (``t7-e3b-search-1``): the episode rules on synthetic decision sequences."""

from __future__ import annotations

import unittest
from dataclasses import replace

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.evaluation import t7_e3b as te
from miaosuan_agent.experiments import t7_concealment as cand
from miaosuan_agent.experiments import t7_idle_concealment as sh

from tests.fixtures import synthetic as syn

SEAT, OWN, ENEMY = syn.RED_SEAT, 0, 1
COSTS = MoveCosts.from_raw(syn.cost_data(), Origin.ENGINE)
U, HEX, S0 = 7, 1203, 500


def state(**changes):
    base = te.UnitState(U, 2, 1, HEX, 10, 0, (), 1, 0, 0, (0, 0, 0, 0, 0), 0.0, frozenset({1, 6, 11}))
    return replace(base, **changes)


def run(n, *, events=None, unit_changes=None, missing=(), gaps=(), enemy_at=None, attackers=None, targets=None,
        others=None):
    """``n`` decisions from the order decision (index 0, cur_step S0); ``events``: index -> action of unit U;
    ``unit_changes``: index -> UnitState changes (or None: unit absent) applied from that index on."""
    events, unit_changes = events or {}, unit_changes or {}
    rows, current, step = [], state(), S0
    for i in range(n):
        if i in unit_changes:
            current = None if unit_changes[i] is None else replace(state(), **unit_changes[i])
        if i in gaps:
            step += 1
        units = {} if current is None or i in missing else {U: current}
        units.update((others or {}).get(i, {}))
        actions = {U: events[i]} if i in events else {}
        rows.append(te.Decision(i, step, units, actions,
                                frozenset({HEX}) if enemy_at is not None and i >= enemy_at else frozenset(),
                                frozenset({U}) if attackers == i else frozenset(),
                                frozenset({U}) if targets == i else frozenset()))
        step += 1
    return rows


MOVE = {"type": 1, "obj_id": U, "move_path": [1204]}
SHOT = {"type": 2, "obj_id": U, "target_obj_id": 99, "weapon_id": 36}


class Intervals(unittest.TestCase):
    def test_74_75_76(self):
        for d, expected in ((74, te.TI), (75, te.W), (76, te.W)):
            e = te.classify(run(d + 3, events={d: MOVE}), 0, U)
            self.assertEqual((e.cls, e.d, e.k1, e.s1), (expected, d, d, S0 + d), d)
            self.assertEqual(e.completed, d >= 75)

    def test_a_shot_counts_like_a_move(self):
        self.assertEqual(te.classify(run(90, events={80: SHOT}), 0, U).cls, te.W)
        self.assertEqual(te.classify(run(90, events={10: SHOT}), 0, U).cls, te.TI)

    def test_other_action_types_are_never_witnesses(self):
        for t in (8, 5, 3, 9):
            e = te.classify(run(120, events={100: {"type": t, "obj_id": U}}), 0, U)
            self.assertEqual((e.cls, e.later_type, e.label()), (te.OA, t, f"OA type {t}"))

    def test_censoring_on_either_side_of_75(self):
        e = te.classify(run(75), 0, U)  # last decision at d 74
        self.assertEqual((e.cls, e.d, e.label()), (te.CE, 74, "CE during the transition"))
        e = te.classify(run(76), 0, U)
        self.assertEqual((e.cls, e.d, e.label()), (te.CE, 75, "CE after the transition"))

    def test_a_command_to_another_unit_does_not_end_the_episode(self):
        rows = run(100)
        rows[80].actions[8] = {"type": 1, "obj_id": 8}
        self.assertEqual(te.classify(rows, 0, U).cls, te.CE)


class Disturbances(unittest.TestCase):
    def check(self, rows, reason, d):
        e = te.classify(rows, 0, U)
        self.assertEqual((e.cls, e.reason, e.d), (te.DT, reason, d))
        return e

    def test_each_violation_ends_the_episode(self):
        cases = [({"blood": 9}, "damaged"), ({"hex": 1204}, "moved"), ({"path": (1204,)}, "move path"),
                 ({"stop": 0}, "not stopped"), ({"keep": 1}, "suppressed"), ({"on_board": 1}, "boarded"),
                 ({"flag_force_stop": 1}, "forced stop"), ({"timers": (3, 0, 0, 0, 0)}, "transition"),
                 ({"timers": (0, 0, 0, 1, 0)}, "transition")]
        for changes, reason in cases:
            self.check(run(120, events={100: MOVE}, unit_changes={30: changes}), reason, 30)

    def test_the_unit_disappearing(self):
        self.check(run(120, events={100: MOVE}, unit_changes={40: None}), "unit gone", 40)

    def test_an_enemy_in_its_hex_and_judge_records(self):
        self.check(run(120, events={100: MOVE}, enemy_at=20), "enemy in hex", 20)
        self.check(run(120, events={100: MOVE}, attackers=21), "fired", 21)
        self.check(run(120, events={100: MOVE}, targets=22), "attacked", 22)

    def test_disturbance_at_the_command_decision_wins(self):
        self.check(run(120, events={90: MOVE}, unit_changes={90: {"keep": 1}}), "suppressed", 90)

    def test_disturbance_after_the_transition_is_labelled_so(self):
        e = self.check(run(120, events={110: MOVE}, unit_changes={80: {"keep": 1}}), "suppressed", 80)
        self.assertEqual(e.label(), "DT after the transition")
        e = self.check(run(120, events={110: MOVE}, unit_changes={74: {"keep": 1}}), "suppressed", 74)
        self.assertEqual(e.label(), "DT during the transition")

    def test_the_order_decision_must_be_idle(self):
        with self.assertRaises(ValueError):
            te.classify(run(10, events={0: MOVE}), 0, U)
        with self.assertRaises(ValueError):
            te.classify(run(10, unit_changes={0: None}), 0, U)


class MissingEvidence(unittest.TestCase):
    def test_a_snapshot_gap_is_recorded_and_keeps_the_witness(self):
        e = te.classify(run(100, events={90: MOVE}, gaps=(40,)), 0, U)
        self.assertEqual((e.cls, e.gaps, e.d), (te.W, [(40, te.GAP)], 91))

    def test_a_missing_field_is_recorded_not_a_disturbance(self):
        e = te.classify(run(100, events={90: MOVE}, unit_changes={30: {"blood": None}, 31: {}}), 0, U)
        self.assertEqual((e.cls, e.gaps), (te.W, [(30, te.MISSING)]))
        e = te.classify(run(100, events={90: MOVE}, unit_changes={30: {"timers": (0, None, 0, 0, 0)}, 31: {}}), 0, U)
        self.assertEqual(e.gaps, [(30, te.MISSING)])

    def test_a_missing_field_at_the_order_is_recorded(self):
        e = te.classify(run(100, events={90: MOVE}, unit_changes={0: {"keep": None}, 1: {}}), 0, U)
        self.assertEqual(e.gaps[0], (0, te.MISSING))


class EpisodeOpening(unittest.TestCase):
    def test_two_first_orders_in_one_decision(self):
        rows = run(120, events={100: MOVE}, others={i: {8: replace(state(), obj_id=8, hex=1205)} for i in range(120)})
        eps = te.episodes(rows, {U: [0], 8: [0]})
        self.assertEqual([(e.unit, e.cls) for e in eps], [(U, te.W), (8, te.CE)])

    def test_repeats_inside_an_episode_are_ignored_and_ce_has_no_successor(self):
        self.assertEqual(len(te.episodes(run(300), {U: [0, 75, 150, 225]})), 1)

    def test_an_order_after_the_end_opens_a_conditional_episode(self):
        rows = run(300, events={20: MOVE, 250: MOVE}, unit_changes={21: {}})
        eps = te.episodes(rows, {U: [0, 75, 150]})
        self.assertEqual([(e.cls, e.k0, e.previous) for e in eps], [(te.TI, 0, None), (te.W, 75, "TI")])
        self.assertTrue(eps[1].conditional and not eps[0].conditional)

    def test_an_order_at_the_end_decision_does_not_open_one(self):
        self.assertEqual(len(te.episodes(run(200, events={20: MOVE}), {U: [0, 20]})), 1)


class IdleRuns(unittest.TestCase):
    def test_a_run_without_an_order_is_d2(self):
        runs = te.idle_runs(run(120, events={100: MOVE}), {})
        self.assertEqual([(r.unit, r.k1, r.length, r.later_type) for r in runs], [(U, 100, 100, 1)])

    def test_an_order_in_the_run_excludes_it(self):
        self.assertEqual(te.idle_runs(run(120, events={100: MOVE}), {U: [50]}), [])

    def test_the_75_step_minimum(self):
        self.assertEqual(len(te.idle_runs(run(80, events={75: MOVE}), {})), 1)
        self.assertEqual(te.idle_runs(run(80, events={74: MOVE}), {}), [])

    def test_the_run_starts_after_a_disturbance(self):
        runs = te.idle_runs(run(200, events={150: MOVE}, unit_changes={50: {"keep": 1}, 60: {}}), {})
        self.assertEqual([(r.start_k, r.length) for r in runs], [(60, 90)])
        self.assertEqual(te.idle_runs(run(200, events={100: MOVE}, unit_changes={50: {"keep": 1}, 60: {}}), {}), [])

    def test_only_moves_and_shots_of_ground_units(self):
        self.assertEqual(te.idle_runs(run(120, events={100: {"type": 8, "obj_id": U}}), {}), [])
        rows = run(120, events={100: MOVE}, unit_changes={0: {"type": 3}})
        self.assertEqual(te.idle_runs(rows, {}), [])

    def test_a_gap_ends_the_run(self):
        runs = te.idle_runs(run(120, events={100: MOVE}, gaps=(40,)), {})
        self.assertEqual([(r.start_k, r.length) for r in runs], [])
        runs = te.idle_runs(run(200, events={150: MOVE}, gaps=(40,)), {})
        self.assertEqual([(r.start_k, r.length) for r in runs], [(40, 110)])


class Evidence(unittest.TestCase):
    def feedback(self, action, code=None):
        entry = {"message": dict(action, actor=SEAT)}
        if code is not None:
            entry["error"] = {"code": code}
        return entry

    def test_an_accepted_executed_move(self):
        action = dict(MOVE, actor=SEAT)
        ev = te.command_evidence(action, [action], [self.feedback(MOVE)], [], state(hex=1204), {1: None, 6: []})
        self.assertEqual((ev["echoes"], ev["accepted"], ev["executed"], ev["listed"]), (1, True, True, True))
        ev = te.command_evidence(action, [], [self.feedback(MOVE)], [], state(path=(1204,)), {1: None})
        self.assertTrue(ev["executed"])

    def test_rejected_unechoed_and_doubly_echoed(self):
        action = dict(MOVE, actor=SEAT)
        self.assertFalse(te.command_evidence(action, [], [self.feedback(MOVE, 404)], [], state(), {1: None})["accepted"])
        none = te.command_evidence(action, [], [], [], state(), {1: None})
        self.assertEqual((none["echoes"], none["accepted"], none["executed"]), (0, False, False))
        two = te.command_evidence(action, [], [self.feedback(MOVE), self.feedback(MOVE)], [], state(), {1: None})
        self.assertFalse(two["accepted"])
        other = te.command_evidence(action, [], [self.feedback(dict(MOVE, move_path=[1205]))], [], state(), {})
        self.assertEqual((other["echoes"], other["listed"]), (0, False))

    def test_a_shot_needs_a_judge_record_and_a_listed_option(self):
        action = dict(SHOT, actor=SEAT)
        listed = {2: [{"target_obj_id": 99, "weapon_id": 36}]}
        ev = te.command_evidence(action, [], [self.feedback(SHOT)], [{"att_obj_id": U, "target_obj_id": 99}], None, listed)
        self.assertEqual((ev["accepted"], ev["executed"], ev["listed"]), (True, True, True))
        ev = te.command_evidence(action, [], [self.feedback(SHOT)], [{"att_obj_id": 5}], None,
                                 {2: [{"target_obj_id": 99, "weapon_id": 54}]})
        self.assertEqual((ev["executed"], ev["listed"]), (False, False))

    def test_an_echo_of_the_rewritten_serialisation_counts(self):
        action = dict(MOVE, actor=SEAT)
        rewritten = dict(action, type=14)
        ev = te.command_evidence(action, [rewritten], [self.feedback(dict(MOVE, type=14))], [], state(hex=1204), {1: None})
        self.assertEqual(ev["echoes"], 1)


def unit(obj_id, hex_, *, color=OWN, unit_type=2):
    return {"obj_id": obj_id, "color": color, "type": unit_type, "sub_type": 1, "cur_hex": hex_, "move_state": 0,
            "stop": 1, "move_path": [], "speed": 0.0, "change_state_remain_time": 0.0, "move_to_stop_remain_time": 0.0,
            "weapon_unfold_time": 0.0, "get_on_remain_time": 0.0, "get_off_remain_time": 0.0, "weapon_unfold_state": 1,
            "keep": 0, "tire": 0, "A1": 0, "basic_speed": 36, "blood": 1, "passenger_ids": []}


def observation(units, valid):
    own = [u["obj_id"] for u in units if u["color"] == OWN]
    return syn.build_observation(units=units, valid_actions=valid, seats={SEAT: syn.seat_record(SEAT, OWN, own, True)},
                                 stage=2, cur_step=100, cities=[syn.city(505, flag=-1)])


class MisleadingListings(unittest.TestCase):
    def orders(self, raw):
        d = cand.ConcealmentPolicy(COSTS).decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, OWN, sh.ShadowMemory())
        return [a["obj_id"] for a in d.actions if a.get("type") == 6]

    def test_only_malformed_concealment_options_never_trigger(self):
        raw = observation([unit(1, 303)], {1: {6: [{"target_state": "4"}, {"state": 4}]}})
        self.assertEqual(self.orders(raw), [])
        self.assertEqual(self.orders(observation([unit(1, 303)], {1: {6: [{"target_state": 4}]}})), [1])

    def test_a_unit_listed_but_not_an_operator_is_no_row_and_no_order(self):
        raw = observation([unit(1, 303)], {1: {6: [{"target_state": 4}]}, 2: {6: [{"target_state": 4}], 1: None}})
        self.assertEqual(sorted(te.rows_from_raw(raw, OWN)), [1])
        self.assertEqual(self.orders(raw), [1])
        self.assertEqual(te.rows_from_raw(raw, OWN)[1].listed, frozenset({6}))

    def test_enemy_units_are_not_rows(self):
        raw = observation([unit(1, 303), unit(9, 808, color=ENEMY)], {1: {6: [{"target_state": 4}]}})
        self.assertEqual(sorted(te.rows_from_raw(raw, OWN)), [1])
        self.assertEqual(self.orders(raw), [])  # an enemy is seen


def config(category="A", *, cls=te.W, d=80, s0=600, conditional=False, accepted=True, executed=True, first_judge=None,
           inert=True, earlier=0, seen=0, before_k1=0, deterministic=True, wait=False):
    e = te.Episode(U, 10, s0, cls, d, 10 + d, s0 + d, 1, previous="TI" if conditional else None)
    return te.Configuration("X", category, e, accepted, executed, first_judge, inert, earlier, seen, before_k1,
                            deterministic, wait)


class Feasibility(unittest.TestCase):
    def test_the_mandatory_conditions(self):
        self.assertTrue(config().feasible())
        self.assertFalse(config("B").feasible())
        self.assertFalse(config(conditional=True).feasible())
        self.assertFalse(config(first_judge=599).feasible())
        self.assertTrue(config(first_judge=600).feasible())
        self.assertFalse(config(inert=False, earlier=1, seen=1).feasible())
        self.assertTrue(config(inert=False, earlier=1, seen=0).feasible())
        self.assertTrue(config(inert=True, earlier=1, seen=1).feasible())
        self.assertFalse(config(accepted=False).feasible())
        self.assertFalse(config(executed=None).feasible())
        self.assertFalse(config(cls=te.TI, d=74).feasible())

    def test_the_ranking(self):
        order = [config(deterministic=True, earlier=0, before_k1=0, d=80),
                 config(deterministic=True, earlier=0, before_k1=0, d=90),
                 config(deterministic=True, earlier=0, before_k1=2, d=75),
                 config(deterministic=True, earlier=1, before_k1=0, d=75),
                 config(deterministic=False, earlier=0, before_k1=0, d=75)]
        self.assertEqual(sorted(order, key=te.rank_key), order)
        waiting = config(wait=True)
        self.assertLess(te.rank_key(config(before_k1=0, d=95)), te.rank_key(waiting))

    def test_long_wait(self):
        waiting = state(path=(1204,), speed=0.0)
        rows = run(30, unit_changes={0: {"path": (1204,), "speed": 0.0}})
        self.assertTrue(te.long_wait(rows, S0 + 30))
        self.assertFalse(te.long_wait(rows, S0 + 20))
        self.assertFalse(te.long_wait(run(30, unit_changes={0: {"path": (1204,), "speed": 0.05}}), S0 + 30))
        self.assertIsNotNone(waiting)


class Decision(unittest.TestCase):
    def test_the_rule(self):
        self.assertEqual(te.disposition([config()], True, False), te.IDENTIFIED)
        self.assertEqual(te.disposition([config("B")], True, False), te.UNCERTAIN)
        self.assertEqual(te.disposition([config("C")], True, False), te.UNCERTAIN)
        self.assertEqual(te.disposition([config(first_judge=1)], True, False), te.UNCERTAIN)
        self.assertEqual(te.disposition([config(cls=te.TI, d=50)], True, False), te.NONE_FOUND)
        self.assertEqual(te.disposition([], True, False), te.NONE_FOUND)
        self.assertEqual(te.disposition([config()], False, False), te.BLOCKED)
        self.assertEqual(te.disposition([config()], True, True), te.BLOCKED)


if __name__ == "__main__":
    unittest.main()
