"""Sprint 25 T13-D1 analysis (``evaluation/s25_t13.py``) on synthetic sides (no private data needed).

Hexes on one even row are ``1000 + column``; the distances the tests rely on are asserted in ``setUpModule`` with the
project's own function. Each decision's ``cur_step`` equals its index unless a test sets the steps.
"""

from __future__ import annotations

import types
import unittest

from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation import s25_t13 as st
from miaosuan_agent.evaluation.t7_visibility import hex_distance
from miaosuan_agent.experiments import t13_garrison_shadow as tg

RED, BLUE = 0, 1
INF, VEH = 1, 2
BIG_GUN = 36
OBJ, X_OBJ = 1030, 1040


def h(col: int) -> int:
    return 1000 + col


def setUpModule() -> None:
    for a, b in ((30, 49), (30, 50), (30, 32), (30, 28), (40, 49), (40, 30)):
        assert hex_distance(h(a), h(b)) == abs(a - b), (a, b)


def unit(obj, hex_, *, type_=VEH, sub=1, color=RED, path=()):
    return {"obj_id": obj, "type": type_, "sub_type": sub, "color": color, "cur_hex": hex_, "move_path": list(path),
            "carry_weapon_ids": [BIG_GUN], "stack": 0, "blood": 4}


def enemy(col, obj=900):
    return unit(obj, h(col), color=BLUE)


def move(obj, cols):
    return {"actor": 1, "obj_id": obj, "type": 1, "move_path": [h(c) for c in cols]}


NEAR = enemy(49)
FAR = enemy(50)


def frame(k, own, enemies=(NEAR,), flags=None, actions=(), stage=2, step=None):
    return sc.Frame(k=k, cur_step=k if step is None else step, max_step=2880, stage=stage, faction=RED,
                    own={u["obj_id"]: u for u in own}, aboard={}, enemies={e["obj_id"]: e for e in enemies},
                    valid={}, flags=dict({OBJ: RED} if flags is None else flags), actions=[dict(a) for a in actions])


def side(frames, recorded=None, events=(), population="HH", scenario="S1", values=None):
    rec = recorded if recorded is not None else [[dict(a) for a in f.actions] for f in frames]
    return st.Side(population, f"{population} {scenario} red", "g1", scenario, RED, frames, rec, list(events),
                   values if values is not None else {OBJ: 80, X_OBJ: 50})


LOST = {OBJ: BLUE}


def leaving_side(first_action=True, enemies=(NEAR,), population="HH", recorded=None):
    """A single defender on the objective is ordered out at decision 0, leaves the zone at 2, the objective is lost at 3."""
    acts = [move(1, (31, 32, 33))] if first_action else []
    frames = [frame(0, [unit(1, OBJ)], enemies, actions=acts),
              frame(1, [unit(1, h(31), path=(h(32), h(33)))], enemies),
              frame(2, [unit(1, h(32), path=(h(33),))], enemies),
              frame(3, [unit(1, h(33))], enemies, flags=LOST)]
    return side(frames, recorded, population=population)


def analyse(s):
    a = st.analyse_side(s)
    return a, a.losses


class LossEventTest(unittest.TestCase):
    def test_held_to_lost_transition_and_n4_agreement(self) -> None:
        s = leaving_side()
        events = st.loss_events(s.frames, RED)
        self.assertEqual([(e["coord"], e["k"]) for e in events], [(OBJ, 3)])
        census = sc.objective_defence(sc.Game("HH", "g", "S1", {RED: s.frames}, [], (RED,)), RED)
        self.assertEqual(census["objective_losses"], 1)

    def test_objective_that_stays_held_has_no_loss(self) -> None:
        frames = [frame(k, [unit(1, h(32))]) for k in range(4)]
        self.assertEqual(st.loss_events(frames, RED), [])

    def test_neutral_flag_after_holding_is_a_loss_and_never_held_is_not(self) -> None:
        frames = [frame(0, [], flags={OBJ: RED}), frame(1, [], flags={OBJ: -1}), frame(2, [], flags={OBJ: BLUE})]
        self.assertEqual(len(st.loss_events(frames, RED)), 1)
        frames = [frame(0, [], flags={OBJ: -1}), frame(1, [], flags={OBJ: BLUE})]
        self.assertEqual(st.loss_events(frames, RED), [])

    def test_deployment_decisions_are_not_play_decisions(self) -> None:
        frames = [frame(0, [], flags={OBJ: RED}, stage=1), frame(1, [], flags={OBJ: BLUE})]
        self.assertEqual(st.loss_events(frames, RED), [])


class AnatomyTest(unittest.TestCase):
    def test_v_order_single_defender_on_the_objective(self) -> None:
        _, (row,) = analyse(leaving_side())
        self.assertEqual((row["v_class"], row["defenders"], row["empty_k"], row["last_occupied_k"]),
                         (st.V_ORDER, [1], 2, 1))
        self.assertTrue(row["orders"][1]["attributable"])

    def test_defender_on_an_adjacent_hex(self) -> None:
        frames = [frame(0, [unit(1, h(29))], actions=[move(1, (28, 27))]),
                  frame(1, [unit(1, h(28), path=(h(27),))]), frame(2, [unit(1, h(27))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["empty_k"]), (st.V_ORDER, 1))

    def test_destroyed_in_the_zone_is_v_loss(self) -> None:
        frames = [frame(0, [unit(1, OBJ)]), frame(1, [unit(1, OBJ)]), frame(2, []), frame(3, [], flags=LOST)]
        events = [(2, {"target_color": RED, "target_obj_id": 1, "damage": 2})]
        _, (row,) = analyse(side(frames, events=events))
        self.assertEqual((row["v_class"], row["fates"], row["category"]), (st.V_LOSS, {1: st.DESTROYED},
                                                                           st.NON_ACTIONABLE))

    def test_disappearance_without_a_damage_record_is_v_other(self) -> None:
        frames = [frame(0, [unit(1, OBJ)]), frame(1, [unit(1, OBJ)]), frame(2, []), frame(3, [], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["category"]), (st.V_OTHER, st.AMBIGUOUS))
        self.assertIn("missing", row["v_reason"])

    def test_damage_record_at_another_decision_does_not_make_v_loss(self) -> None:
        frames = [frame(0, [unit(1, OBJ)]), frame(1, [unit(1, OBJ)]), frame(2, []), frame(3, [], flags=LOST)]
        events = [(1, {"target_color": RED, "target_obj_id": 1, "damage": 1})]
        _, (row,) = analyse(side(frames, events=events))
        self.assertEqual(row["v_class"], st.V_OTHER)

    def test_simultaneous_exit_and_destruction_is_v_other(self) -> None:
        frames = [frame(0, [unit(1, OBJ), unit(2, h(31))], actions=[move(1, (31, 32))]),
                  frame(1, [unit(1, h(32))]), frame(2, [unit(1, h(32))], flags=LOST)]
        events = [(1, {"target_color": RED, "target_obj_id": 2, "damage": 4})]
        _, (row,) = analyse(side(frames, events=events))
        self.assertEqual((row["v_class"], sorted(row["fates"].values())), (st.V_OTHER, [st.DESTROYED, st.ALIVE_OUT]))
        self.assertIn("different fates", row["v_reason"])

    def test_two_defenders_leaving_by_order_is_v_order_but_not_actionable(self) -> None:
        frames = [frame(0, [unit(1, OBJ), unit(2, h(31))], actions=[move(1, (31, 32)), move(2, (32, 33))]),
                  frame(1, [unit(1, h(32)), unit(2, h(33))]), frame(2, [unit(1, h(32)), unit(2, h(33))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["category"], row["category_reason"]),
                         (st.V_ORDER, st.NON_ACTIONABLE, "several last defenders"))

    def test_no_identified_defender(self) -> None:
        frames = [frame(0, [unit(1, h(35))]), frame(1, [unit(1, h(35))]), frame(2, [unit(1, h(35))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["v_reason"], row["category"]),
                         (st.V_OTHER, "no last defender observed", st.AMBIGUOUS))

    def test_departure_without_a_recorded_move_is_not_v_order(self) -> None:
        frames = [frame(0, [unit(1, OBJ)]), frame(1, [unit(1, h(32))]), frame(2, [unit(1, h(32))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["v_reason"]),
                         (st.V_OTHER, "left alive, departure not attributable to a recorded MOVE"))

    def test_position_off_the_recorded_route_is_not_attributable(self) -> None:
        frames = [frame(0, [unit(1, OBJ)], actions=[move(1, (31, 32))]), frame(1, [unit(1, h(28))]),
                  frame(2, [unit(1, h(27))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual(row["v_class"], st.V_OTHER)

    def test_zone_occupied_at_the_loss_decision(self) -> None:
        frames = [frame(0, [unit(1, OBJ)]), frame(1, [unit(1, h(31))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["v_reason"]), (st.V_OTHER, "zone occupied at the loss decision"))

    def test_reentry_uses_the_last_empty_run(self) -> None:
        frames = [frame(0, [unit(1, OBJ)], actions=[move(1, (31, 32))]), frame(1, [unit(1, h(32))]),
                  frame(2, [unit(1, h(31))], actions=[move(1, (32, 33))]), frame(3, [unit(1, h(32))]),
                  frame(4, [unit(1, h(33))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["empty_k"], row["last_occupied_k"], row["reentries"], row["orders"][1]["order_k"]),
                         (3, 2, 1, 2))

    def test_artillery_occupies_but_its_departure_is_not_actionable(self) -> None:
        frames = [frame(0, [unit(1, OBJ, sub=3)], actions=[move(1, (31, 32))]), frame(1, [unit(1, h(31), sub=3)]),
                  frame(2, [unit(1, h(32), sub=3)]), frame(3, [unit(1, h(32), sub=3)], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["category"], row["category_reason"]),
                         (st.V_ORDER, st.NON_ACTIONABLE, "trigger: artillery"))


class TouchTest(unittest.TestCase):
    def test_hh_departure_withheld_at_the_first_divergence_is_touched(self) -> None:
        a, (row,) = analyse(leaving_side())
        self.assertEqual((row["category"], a.shadow.first_divergence), (st.TOUCHED, 0))
        d = row["departure"]
        self.assertEqual((d["order_k"], d["ordered_from_inside_zone"], d["withheld_by_shadow"], d["trigger_reason"]),
                         (0, True, True, "eligible"))
        self.assertEqual((d["steps_departure_to_loss"], d["steps_order_to_loss"], d["same_decision"]), (1, 3, False))

    def test_no_threat_is_not_actionable(self) -> None:
        _, (row,) = analyse(leaving_side(enemies=(FAR,)))
        self.assertEqual((row["v_class"], row["category"], row["category_reason"]),
                         (st.V_ORDER, st.NON_ACTIONABLE, "trigger: no_qualifying_threat"))

    def test_h0_departure_by_a_baseline_v0_move_baseline_v2_did_not_emit(self) -> None:
        s = leaving_side(first_action=False, population="H0",
                         recorded=[[move(1, (31, 32, 33))], [], [], []])
        _, (row,) = analyse(s)
        self.assertEqual((row["v_class"], row["departure"]["baseline_v2_same_move"], row["category"]),
                         (st.V_ORDER, "no MOVE for the unit", st.NON_ACTIONABLE))

    def test_h0_baseline_v2_with_a_different_route(self) -> None:
        frames = leaving_side().frames
        frames[0].actions = [move(1, (31, 32, 34))]
        s = side(frames, recorded=[[move(1, (31, 32, 33))], [], [], []], population="H0")
        _, (row,) = analyse(s)
        self.assertEqual((row["departure"]["baseline_v2_same_move"], row["category_reason"]),
                         ("a different MOVE for the unit", "baseline-v2 did not emit this MOVE"))

    def test_h0_identical_move_with_a_supported_prefix_is_touched(self) -> None:
        s = leaving_side(population="H0", recorded=[[move(1, (31, 32, 33))], [], [], []])
        _, (row,) = analyse(s)
        self.assertEqual((row["departure"]["baseline_v2_same_move"], row["category"]), ("identical", st.TOUCHED))

    def test_h0_prefix_not_supported(self) -> None:
        own0 = [unit(1, OBJ)]
        frames = [frame(0, own0, actions=[]), frame(1, own0, actions=[move(1, (31, 32, 33))]),
                  frame(2, [unit(1, h(31), path=(h(32), h(33)))]), frame(3, [unit(1, h(32))]),
                  frame(4, [unit(1, h(33))], flags=LOST)]
        recorded = [[{"actor": 1, "obj_id": 1, "type": 2, "target_obj_id": 900, "weapon_id": BIG_GUN}],
                    [move(1, (31, 32, 33))], [], [], []]
        a, (row,) = analyse(side(frames, recorded=recorded, population="H0"))
        self.assertEqual((a.shadow.first_divergence, row["category"]), (1, st.PREFIX_UNSUPPORTED))
        self.assertFalse(st.prefix_supported(a.side, 1))
        self.assertTrue(st.prefix_supported(a.side, 0))

    def test_later_opportunity_after_the_first_divergence(self) -> None:
        flags = {OBJ: RED, X_OBJ: RED}
        lost = {OBJ: BLUE, X_OBJ: RED}
        e = unit(2, X_OBJ)
        frames = [frame(0, [unit(1, OBJ), e], flags=flags, actions=[move(2, (41, 42, 43))]),
                  frame(1, [unit(1, OBJ), unit(2, h(41))], flags=flags),
                  frame(2, [unit(1, OBJ), unit(2, h(42))], flags=flags, actions=[move(1, (31, 32))]),
                  frame(3, [unit(1, h(31)), unit(2, h(43))], flags=flags),
                  frame(4, [unit(1, h(32)), unit(2, h(43))], flags=flags),
                  frame(5, [unit(1, h(32)), unit(2, h(43))], flags=lost)]
        a, rows = analyse(side(frames))
        row = next(r for r in rows if r["coord"] == OBJ)
        self.assertEqual((a.shadow.first_divergence, row["category"]), (0, st.POST_DIVERGENCE))
        self.assertTrue(row["departure"]["withheld_by_shadow"])

    def test_ordered_before_entering_the_zone(self) -> None:
        route = (32, 31, 30, 29, 28)
        frames = [frame(0, [unit(1, h(33))], actions=[move(1, route)])] + \
                 [frame(k, [unit(1, h(c))]) for k, c in enumerate(route, start=1)] + \
                 [frame(6, [unit(1, h(28))], flags=LOST)]
        _, (row,) = analyse(side(frames))
        self.assertEqual((row["v_class"], row["category_reason"]), (st.V_ORDER, "ordered before entering the zone"))

    def test_existing_path_is_not_cancelled_by_withholding(self) -> None:
        frames = [frame(0, [unit(1, OBJ, path=(h(31), h(32)))], actions=[move(1, (31, 32, 33))]),
                  frame(1, [unit(1, h(31))]), frame(2, [unit(1, h(32))]), frame(3, [unit(1, h(33))], flags=LOST)]
        a, (row,) = analyse(side(frames))
        self.assertEqual((row["category_reason"], a.shadow.first_divergence), ("trigger: existing_path_exits", None))


class EnemyInformationTest(unittest.TestCase):
    def frames(self, seen_step, now_enemies):
        own = [unit(1, OBJ)]
        out = [frame(0, own, enemies=(), step=0)]
        if seen_step is not None:
            out.append(frame(1, own, enemies=(enemy(60),), step=seen_step))
        out.append(frame(len(out), own, enemies=now_enemies, step=1000))
        return out

    def test_categories(self) -> None:
        cases = [((None, (NEAR,)), st.ENEMY_INFO[0]), ((None, (FAR,)), st.ENEMY_INFO[1]),
                 ((700, ()), st.ENEMY_INFO[2]), ((699, ()), st.ENEMY_INFO[3]), ((None, ()), st.ENEMY_INFO[4])]
        for (seen, now), expected in cases:
            frames = self.frames(seen, now)
            info = st.enemy_information(frames, len(frames) - 1, OBJ, VEH)
            self.assertEqual(info["enemy_info"], expected, (seen, now))

    def test_threat_margin_and_published_range_counts(self) -> None:
        frames = self.frames(None, (NEAR, dict(enemy(35, 901), carry_weapon_ids=[72])))
        info = st.enemy_information(frames, len(frames) - 1, OBJ, VEH)
        self.assertEqual((info["qualifying_threats"], info["threat_margin"], info["visible_without_published_range"],
                          info["nearest_visible_distance"]), (1, 0, 1, 5))


class OnwardTest(unittest.TestCase):
    def row_for(self, frames):
        _, rows = analyse(side(frames))
        return next(r for r in rows if r["coord"] == OBJ)

    def base(self, x_flag_later, on_x, other_on_x=False, x_flag_at_order=-1, route=(31, 32, 33, 34, 35, 36, 37, 38, 39, 40)):
        flags0 = {OBJ: RED, X_OBJ: x_flag_at_order}
        frames = [frame(0, [unit(1, OBJ)], flags=flags0, actions=[move(1, route)]),
                  frame(1, [unit(1, h(31))], flags=flags0), frame(2, [unit(1, h(32))], flags=flags0),
                  frame(3, [unit(1, h(33))], flags={OBJ: BLUE, X_OBJ: x_flag_at_order})]
        own4 = [unit(1, X_OBJ if on_x else h(36))] + ([unit(5, X_OBJ)] if other_on_x else [])
        frames.append(frame(4, own4, flags={OBJ: BLUE, X_OBJ: x_flag_later}))
        return frames

    def test_first_owner_of_the_destination(self) -> None:
        on = self.row_for(self.base(RED, True))["departure"]["onward"]
        self.assertEqual((on["destination_kind"], on["next_objective"], on["first_owner"],
                          on["steps_order_to_first_ownership"], on["travel_steps_to_destination"]),
                         ("objective not held", X_OBJ, True, 4, 4))

    def test_destination_first_owned_by_another_unit(self) -> None:
        on = self.row_for(self.base(RED, False, other_on_x=True))["departure"]["onward"]
        self.assertEqual((on["first_owner"], on["first_owned_by_other_own_units_only"]), (False, True))

    def test_destination_already_held(self) -> None:
        on = self.row_for(self.base(RED, True, x_flag_at_order=RED))["departure"]["onward"]
        self.assertEqual((on["destination_kind"], on["first_owner"], on["next_objective_first_owned_before_order"]),
                         ("objective held", False, True))

    def test_first_owner_before_the_order_is_not_a_risk(self) -> None:
        flags = {OBJ: RED, X_OBJ: RED}
        frames = [frame(0, [unit(1, X_OBJ)], flags=flags),
                  frame(1, [unit(1, OBJ)], flags=flags, actions=[move(1, range(31, 41))]),
                  frame(2, [unit(1, h(31))], flags=flags), frame(3, [unit(1, h(32))], flags=flags),
                  frame(4, [unit(1, h(33))], flags={OBJ: BLUE, X_OBJ: RED})]
        on = self.row_for(frames)["departure"]["onward"]
        self.assertEqual((on["destination_kind"], on["first_owner"], on["next_objective_first_owned_before_order"]),
                         ("objective held", False, True))

    def test_non_objective_destination_uses_the_first_objective_stood_on(self) -> None:
        on = self.row_for(self.base(RED, True, route=(31, 32, 33, 34, 35)))["departure"]["onward"]
        self.assertEqual((on["destination_kind"], on["next_objective_from"], on["next_objective"], on["first_owner"]),
                         ("not an objective", "the first objective stood on after the order", X_OBJ, True))

    def test_non_objective_destination_and_no_objective_later(self) -> None:
        on = self.row_for(self.base(-1, False, route=(31, 32, 33, 34, 35)))["departure"]["onward"]
        self.assertEqual((on["next_objective"], on["first_owner"], on["next_objective_from"]),
                         (None, False, "no objective stood on after the order"))


def fake(population, scenario, rows):
    s = types.SimpleNamespace(population=population, scenario_side=f"{scenario} red")
    return types.SimpleNamespace(side=s, losses=rows)


def row(v=st.V_ORDER, cat=st.TOUCHED, unit_id=1, step=10, coord=OBJ, first_owner=False):
    out = {"v_class": v, "category": cat, "coord": coord}
    if cat == st.TOUCHED:
        out["departure"] = {"order_step": step, "unit": unit_id, "route": (h(32),), "onward": {"first_owner": first_owner}}
    return out


class StopTest(unittest.TestCase):
    def test_stop_a_exactly_half_passes_and_below_half_fails(self) -> None:
        half = [fake("H0", "A", [row(), row(st.V_LOSS, st.NON_ACTIONABLE)]),
                fake("HH", "A", [row(step=11)])]
        self.assertFalse(st.stops(half)["A_departure_not_dominant"]["met"])
        below = [fake("H0", "A", [row(), row(st.V_LOSS, st.NON_ACTIONABLE), row(st.V_OTHER, st.AMBIGUOUS)]),
                 fake("HH", "A", [row(step=11)])]
        out = st.stops(below)["A_departure_not_dominant"]
        self.assertTrue(out["met"])
        self.assertEqual((out["by_population"]["H0"]["share"], out["by_population"]["H0"]["met"],
                          out["by_population"]["HH"]["met"], out["by_population"]["pooled"]["met"]),
                         ("1/3", True, False, False))

    def test_stop_a_one_population_failing_is_not_hidden_by_pooling(self) -> None:
        sides = [fake("H0", "A", [row(step=s) for s in range(9)]),
                 fake("HH", "A", [row(st.V_LOSS, st.NON_ACTIONABLE), row(st.V_LOSS, st.NON_ACTIONABLE), row(step=99)])]
        out = st.stops(sides)["A_departure_not_dominant"]
        self.assertEqual((out["by_population"]["pooled"]["met"], out["by_population"]["HH"]["met"], out["met"]),
                         (False, True, True))

    def test_stop_a_no_loss_is_met(self) -> None:
        self.assertTrue(st.stops([fake("H0", "A", []), fake("HH", "A", [])])["A_departure_not_dominant"]["met"])

    def test_stop_b_four_losses_and_two_scenario_sides(self) -> None:
        three = [fake("H0", "A", [row(step=1), row(step=2)]), fake("H0", "B", [row(step=3)])]
        self.assertTrue(st.stops(three)["B_insufficient_actionable_coverage"]["met"])
        four = [fake("H0", "A", [row(step=1), row(step=2)]), fake("H0", "B", [row(step=3), row(step=4)])]
        self.assertFalse(st.stops(four)["B_insufficient_actionable_coverage"]["met"])
        one_side = [fake("H0", "A", [row(step=s) for s in range(1, 5)])]
        b = st.stops(one_side)["B_insufficient_actionable_coverage"]
        self.assertEqual((b["touched_distinct"], b["distinct_scenario_sides"], b["met"]), (4, 1, True))

    def test_stop_b_replicas_counted_once(self) -> None:
        sides = [fake("H0", "A", [row(step=1), row(step=2)]), fake("HH", "A", [row(step=1), row(step=2)]),
                 fake("HH", "B", [row(step=3)])]
        b = st.stops(sides)["B_insufficient_actionable_coverage"]
        self.assertEqual((b["touched_raw"], b["touched_distinct"], b["distinct_scenario_sides"], b["met"]),
                         (5, 3, 2, True))

    def test_stop_b_counts_only_valid_first_divergence(self) -> None:
        others = [row(cat=c) for c in (st.POST_DIVERGENCE, st.PREFIX_UNSUPPORTED, st.NON_ACTIONABLE)]
        sides = [fake("H0", "A", [row(step=1)] + others), fake("H0", "B", [row(step=2)] + others)]
        self.assertEqual(st.stops(sides)["B_insufficient_actionable_coverage"]["touched_distinct"], 2)

    def test_stop_c_one_half_passes_and_more_fails(self) -> None:
        def sides(owners):
            rows = [row(step=s, first_owner=s <= owners) for s in range(1, 5)]
            return [fake("H0", "A", rows[:2]), fake("H0", "B", rows[2:])]
        self.assertFalse(st.stops(sides(2))["C_onward_capture_interference"]["met"])
        c = st.stops(sides(3))["C_onward_capture_interference"]
        self.assertEqual((c["share"], c["met"]), ("3/4", True))

    def test_stop_c_without_touched_losses_is_met(self) -> None:
        c = st.stops([fake("H0", "A", [row(st.V_LOSS, st.NON_ACTIONABLE)])])["C_onward_capture_interference"]
        self.assertEqual((c["evaluable"], c["met"]), (False, True))


class DispositionTest(unittest.TestCase):
    PASS = {k: {"met": False} for k in ("A_departure_not_dominant", "B_insufficient_actionable_coverage",
                                        "C_onward_capture_interference")}

    def test_precedence(self) -> None:
        fail = dict(self.PASS, B_insufficient_actionable_coverage={"met": True})
        self.assertEqual(st.disposition(False, True, 0, fail)["disposition"], "T13_D1_INVALID")
        self.assertEqual(st.disposition(True, False, 0, self.PASS)["disposition"], "T13_D1_INVALID")
        self.assertEqual(st.disposition(True, True, 1, self.PASS)["disposition"], "T13_D1_INVALID")
        out = st.disposition(True, True, 0, fail)
        self.assertEqual((out["disposition"], out["stops_met"]), ("T13_D1_NOT_READY", ["B_insufficient_actionable_coverage"]))
        self.assertEqual(st.disposition(True, True, 0, self.PASS)["disposition"],
                         "T13_D1_READY_FOR_SMALL_EXPLORATORY_PROPOSAL")

    def test_every_stop_reported_even_when_invalid(self) -> None:
        every = {k: {"met": True} for k in self.PASS}
        out = st.disposition(False, True, 0, every)
        self.assertEqual((out["disposition"], len(out["stops_met"])), ("T13_D1_INVALID", 3))


class CompareTest(unittest.TestCase):
    def test_registered_withholding_is_explained(self) -> None:
        f = frame(0, [unit(1, OBJ)], actions=[move(1, (31, 32))])
        self.assertEqual(st.compare(f, [], RED), [])

    def test_dropping_another_action_or_reordering_is_unexplained(self) -> None:
        shot = {"actor": 1, "obj_id": 1, "type": 2, "target_obj_id": 900, "weapon_id": BIG_GUN}
        f = frame(0, [unit(1, OBJ)], actions=[shot, move(1, (31, 32))])
        self.assertEqual(len(st.compare(f, [move(1, (31, 32))], RED)), 1)
        f2 = frame(0, [unit(1, OBJ), unit(2, h(35))], actions=[move(2, (36,)), shot])
        problems = st.compare(f2, [shot, move(2, (36,))], RED)
        self.assertEqual([p["problem"] for p in problems][0], "the candidate adds or reorders actions")
        self.assertEqual(len(problems), 2)

    def test_withholding_without_a_threat_is_unexplained(self) -> None:
        f = frame(0, [unit(1, OBJ)], enemies=(FAR,), actions=[move(1, (31, 32))])
        self.assertEqual(len(st.compare(f, [], RED)), 1)

    def test_the_shadow_run_has_no_unexplained_difference(self) -> None:
        a, _ = analyse(leaving_side())
        self.assertEqual((a.shadow.unexplained, a.shadow.withheld), ([], {0: (0,)}))
        self.assertTrue(all(a.integrity.values()), a.integrity)


class PublicTest(unittest.TestCase):
    def test_public_rows_carry_no_private_value(self) -> None:
        a, rows = analyse(leaving_side())
        private = {1, 900, OBJ, X_OBJ} | set(range(1025, 1060))
        data = {"loss": st.public_loss(a, rows[0], 1), "side": st.side_summary(a), "cert": st.certificate(a),
                "pooled": st.pooled_table([a])}
        self.assertEqual(st.public_problems(data, private), [])
        self.assertEqual(data["loss"]["objective"], "80-point objective A")
        self.assertEqual(data["loss"]["departure"]["onward"]["next_objective"], None)

    def test_no_public_label_carries_a_number_word(self) -> None:
        """Amendment A1: a label word made only of digits can equal a private hex or unit id and refuse the run."""
        labels = [*st.V_CLASSES, *st.CATEGORIES, *st.ENEMY_INFO, st.ALIVE_OUT, st.DESTROYED, st.MISSING,
                  st.UNREADABLE, *tg.TRIGGER_REASONS, *tg.RELEASE_REASONS, *st.DISPOSITIONS]
        a, rows = analyse(leaving_side())
        strings = []

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, (list, tuple)):
                for v in node:
                    walk(v)
            elif isinstance(node, str):
                strings.append(node)
        walk({"loss": st.public_loss(a, rows[0], 1), "side": st.side_summary(a), "pooled": st.pooled_table([a])})
        for text in labels + strings:
            self.assertFalse(any(w.strip(",.;:()").isdigit() for w in text.split()), text)
        self.assertEqual(st.public_problems({"labels": labels}, range(10000)), [])

    def test_planted_private_values_are_caught(self) -> None:
        self.assertTrue(st.public_problems({"cur_hex": 5}, ()))
        self.assertTrue(st.public_problems({"note": "unit 17 left"}, {17}))
        self.assertTrue(st.public_problems({"17": 1}, {17}))


if __name__ == "__main__":
    unittest.main()
