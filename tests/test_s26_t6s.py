"""Sprint 26 T6-S analysis (``evaluation/s26_t6s.py``) on synthetic sides (no private data needed).

Hexes on one even row are ``1000 + column``; the distances the tests rely on are asserted in ``setUpModule`` with the
project's own function. Movers start on column 20, their routes run along the row, and hex times come from a test
travel relation (``tau`` per unit). Each decision's ``cur_step`` equals its index unless a test sets the steps.
"""

from __future__ import annotations

import types
import unittest

from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation import s26_t6s as st
from miaosuan_agent.evaluation.t7_visibility import hex_distance
from miaosuan_agent.experiments import t6s_stagger_shadow as ts

RED, BLUE = 0, 1
INF, VEH = 1, 2
BIG_GUN = 36
SCENARIO = "2130511121"


def h(col: int) -> int:
    return 1000 + col


def setUpModule() -> None:
    for a, b in ((20, 38), (21, 38), (22, 38), (20, 44), (25, 44), (26, 44), (30, 38), (57, 38)):
        assert hex_distance(h(a), h(b)) == abs(a - b), (a, b)


def unit(obj, col=20, *, type_=VEH, path=(), tau=20, speed=0, stack=1, color=RED):
    return {"obj_id": obj, "type": type_, "sub_type": 1, "color": color, "cur_hex": h(col), "move_path": list(path),
            "carry_weapon_ids": [BIG_GUN], "tau": tau, "speed": speed, "stack": stack, "basic_speed": 36}


def enemy(col, obj=900):
    return unit(obj, col, color=BLUE)


def move(obj, cols=(21, 22)):
    return {"actor": 1, "obj_id": obj, "type": 1, "move_path": [h(c) for c in cols]}


def shoot(obj):
    return {"actor": 1, "obj_id": obj, "type": 2, "target_obj_id": 900, "weapon_id": BIG_GUN}


def travel(u, route):
    if u.get("tau") is None:
        return None
    return (u["tau"],) * len(route), float(len(route))


NEAR = enemy(38)
OBJ = h(22)


def frame(k, own, enemies=(NEAR,), actions=(), flags=None, stage=2, step=None, max_step=2880):
    return sc.Frame(k=k, cur_step=k if step is None else step, max_step=max_step, stage=stage, faction=RED,
                    own={u["obj_id"]: u for u in own}, aboard={}, enemies={e["obj_id"]: e for e in enemies},
                    valid={u["obj_id"]: {1: []} for u in own}, flags=dict({OBJ: -1} if flags is None else flags),
                    actions=[dict(a) for a in actions])


def side(frames, recorded=None, population="HH", label=None, scenario=SCENARIO, events=(), faction=RED):
    rec = recorded if recorded is not None else [[dict(a) for a in f.actions] for f in frames]
    colour = "red" if faction == 0 else "blue"
    return st.Side(population, label or f"{population} p01 baseline-v2 {colour}", "g1", scenario, faction, frames, rec,
                   list(events), travel, {OBJ: 80})


def column_frames(n=50, follower_moves_on_record=True, owner_at=None):
    """Two vehicles on column 20 ordered at decision 0 along (21, 22); on the record both move, entering 21 at step 20
    and 22 (the objective) at step 40, which the side first owns at ``owner_at`` (default never)."""
    frames = []
    for t in range(n):
        if t == 0:
            own = [unit(1), unit(2)]
            actions = [move(1), move(2)]
        else:
            col = 20 if t < 20 else 21 if t < 40 else 22
            path = [] if col == 22 else [h(c) for c in range(col + 1, 23)]
            own = [unit(1, col, path=path, speed=0 if col == 22 else 0.05)]
            own.append(unit(2, col, path=path, speed=0 if col == 22 else 0.05) if follower_moves_on_record else unit(2))
            actions = []
        flags = {OBJ: RED if owner_at is not None and t >= owner_at else -1}
        frames.append(frame(t, own, actions=actions, flags=flags))
    return frames


class ShadowRunTest(unittest.TestCase):
    def test_first_divergence_release_and_no_unexplained_difference(self) -> None:
        a = st.analyse_side(side(column_frames()))
        s = a.shadow
        self.assertEqual(s.first_divergence, 0)
        self.assertEqual(s.withheld, {0: (1,)})
        self.assertEqual(s.unexplained, [])
        self.assertTrue(all(a.integrity.values()), a.integrity)
        (row,) = s.episodes
        self.assertEqual((row["chain"], row["end"], row["end_k"]), ([1, 2], "complete", 20))
        self.assertEqual(row["releases"][2], {"k": 20, "step": 20, "reason": "reference_left", "moved": False})
        self.assertEqual(row["projected_waits"], [20])
        self.assertTrue(row["first_divergence"])
        self.assertFalse(row["post_divergence"])

    def test_follow_up_on_the_record(self) -> None:
        a = st.analyse_side(side(column_frames()))
        fu = a.shadow.episodes[0]["follow_up"]
        self.assertEqual((fu["members_followed_on_record"], fu["all_followed"]), (2, True))
        self.assertTrue(fu["co_located_moving_beyond_start"])
        self.assertEqual(fu["co_located_hexes_beyond_start"], 1)              # column 21 (22 is reached stationary)
        self.assertEqual(fu["co_located_moving_decisions"], 20)
        self.assertEqual(fu["stacked_moving_inside_envelope_unit_decisions"], 78)      # 39 moving decisions x 2
        self.assertEqual(fu["leader_recorded_departure_steps"], 20)

    def test_not_followed_on_the_record(self) -> None:
        frames = column_frames()
        rec = [[dict(x) for x in f.actions] for f in frames]
        rec[0] = [move(1)]
        a = st.analyse_side(side(frames, recorded=rec))
        fu = a.shadow.episodes[0]["follow_up"]
        self.assertEqual((fu["members_followed_on_record"], fu["all_followed"]), (1, False))

    def test_onward_first_owner_risk(self) -> None:
        a = st.analyse_side(side(column_frames(owner_at=40)))
        row = a.shadow.episodes[0]
        o = row["onward"][2]
        self.assertEqual((o["destination_kind"], o["first_owned_after_start"], o["first_owner"]),
                         (st.DEST_UNHELD, True, True))
        self.assertTrue(o["other_own_first_owners"])
        self.assertEqual(o["steps_start_to_first_ownership"], 40)
        self.assertTrue(row["first_owner_risk"])

    def test_onward_first_owned_before_or_by_others(self) -> None:
        a = st.analyse_side(side(column_frames(owner_at=0)))
        o = a.shadow.episodes[0]["onward"][2]
        self.assertEqual((o["destination_kind"], o["first_owned_before_start"], o["first_owner"]),
                         (st.DEST_HELD, True, False))
        frames = column_frames(owner_at=40)
        for f in frames[40:]:
            f.own[2] = unit(2, 21)                                         # the follower is not on the objective
        row = st.analyse_side(side(frames)).shadow.episodes[0]
        o = row["onward"][2]
        self.assertEqual((o["first_owner"], o["other_own_first_owners"]), (False, True))
        self.assertEqual((sorted(row["onward"]), row["first_owner_risk"]), ([2], False))   # the leader is not delayed

    def test_destination_not_an_objective(self) -> None:
        frames = column_frames(owner_at=40)
        for f in frames:
            f.flags = {h(30): -1}
        o = st.analyse_side(side(frames)).shadow.episodes[0]["onward"][2]
        self.assertEqual((o["destination_kind"], o["first_owner"], o["never_owned"]), (st.DEST_NOT_OBJECTIVE, False, False))

    def test_pushed_past_the_end(self) -> None:
        frames = column_frames()
        frames[0].max_step = 50                                            # arrival 40, wait 20: 40 <= 50 < 60
        o = st.analyse_side(side(frames)).shadow.episodes[0]["onward"][2]
        self.assertTrue(o["pushed_past_the_end"])
        frames[0].max_step = 60
        self.assertFalse(st.analyse_side(side(frames)).shadow.episodes[0]["onward"][2]["pushed_past_the_end"])
        frames[0].max_step = 39
        o = st.analyse_side(side(frames)).shadow.episodes[0]["onward"][2]
        self.assertEqual((o["pushed_past_the_end"], o["unreachable_free_flow"]), (False, True))

    def test_damage_windows(self) -> None:
        events = [(30, {"target_color": RED, "target_obj_id": 2, "damage": 1, "cur_step": 30}),
                  (100, {"target_color": RED, "target_obj_id": 1, "damage": 1, "cur_step": 100}),
                  (5, {"target_color": BLUE, "target_obj_id": 2, "damage": 1, "cur_step": 5})]
        frames = column_frames(n=120)
        d = st.analyse_side(side(frames, events=events)).shadow.episodes[0]["damage"]
        self.assertEqual((d["members_damaged_within_75"], d["members_damaged_within_150"], d["followers_damaged_within_75"]),
                         (1, 2, 1))


class PrefixTest(unittest.TestCase):
    def test_h0_prefix_fidelity_failure(self) -> None:
        frames = column_frames()
        quiet = [frame(0, [unit(1), unit(2)], actions=[shoot(1)])]
        frames = quiet + [sc.Frame(**{**f.__dict__, "k": f.k + 1, "cur_step": f.cur_step + 1}) for f in frames]
        rec = [[dict(x) for x in f.actions] for f in frames]
        rec[0] = []                                                         # baseline-v0 differs before the trigger
        a = st.analyse_side(side(frames, recorded=rec, population="H0", label=f"H0 {SCENARIO} red"))
        self.assertEqual(a.shadow.first_divergence, 1)
        self.assertFalse(st.prefix_supported(a.side, 1))
        cert = st.certificate(a)
        self.assertEqual((cert["prefix_supported"], cert["on_policy_baseline_v2_witness"]), (False, False))
        self.assertIs(a.shadow.episodes[0]["prefix_supported"], False)

    def test_hh_exact_reconstruction_is_supported(self) -> None:
        a = st.analyse_side(side(column_frames()))
        cert = st.certificate(a)
        self.assertEqual((cert["prefix_supported"], cert["on_policy_baseline_v2_witness"]), (True, True))
        self.assertTrue(cert["only_follower_moves_withheld"])
        self.assertTrue(cert["leader_moves_kept"])
        self.assertTrue(cert["unrelated_actions_unchanged"])
        self.assertEqual((cert["baseline_action_types"], cert["candidate_action_types"]), ([1, 1], [1]))

    def test_later_episodes_are_post_divergence(self) -> None:
        frames = column_frames(n=60)
        frames[50] = frame(50, [unit(1, 22), unit(2, 22), unit(3, 30), unit(4, 30)],
                           actions=[move(3, (31, 32)), move(4, (31, 32))])
        a = st.analyse_side(side(frames))
        self.assertEqual([(r["start_k"], r["first_divergence"], r["post_divergence"]) for r in a.shadow.episodes],
                         [(0, True, False), (50, False, True)])
        self.assertIsNone(a.shadow.episodes[1]["prefix_supported"])


class IndependentCheckTest(unittest.TestCase):
    def check(self, frames, candidates):
        c = st.IndependentCheck(travel)
        out = []
        for f, cand in zip(frames, candidates):
            out.extend(c.step(f, cand))
        return [p["problem"] for p in out]

    def start(self, step=0, own=None, actions=None, enemies=(NEAR,)):
        own = own or [unit(1), unit(2)]
        actions = actions or [move(1), move(2)]
        return frame(step, own, enemies=enemies, actions=actions, step=step)

    def test_valid_start_and_repeats_within_the_bound(self) -> None:
        frames = [self.start(0), frame(1, [unit(1), unit(2)], actions=[move(2)], step=1),
                  frame(30, [unit(1), unit(2)], actions=[move(2)], step=30)]
        self.assertEqual(self.check(frames, [[move(1)], [], []]), [])

    def test_added_or_reordered(self) -> None:
        self.assertEqual(self.check([self.start()], [[move(2), move(1)]]), ["the candidate adds or reorders actions"])
        self.assertEqual(self.check([self.start()], [[move(1), move(2), shoot(1)]]),
                         ["the candidate adds or reorders actions"])

    def test_removed_non_move(self) -> None:
        f = self.start(actions=[move(1), shoot(2), move(2)])
        self.assertEqual(self.check([f], [[move(1), move(2)]]), ["a removed action is not a MOVE"])

    def test_removed_move_of_a_moving_unit(self) -> None:
        f = self.start(own=[unit(1), unit(2, path=(h(21),))])
        self.assertEqual(self.check([f], [[move(1)]]), ["a removed MOVE belongs to a unit already moving"])

    def test_removed_without_a_kept_partner_or_threat(self) -> None:
        f = self.start(actions=[move(1, (19, 18)), move(2)])
        self.assertEqual(self.check([f], [[move(1, (19, 18))]]), ["no co-located MOVE with the same first hex is kept"])
        f = self.start(enemies=(enemy(44),))
        self.assertEqual(self.check([f], [[move(1)]]), ["no MOVE of the group is threat-exposed"])

    def test_repeat_beyond_the_bound_or_after_leaving(self) -> None:
        # n = 2, t = 20: bound (2 - 1) * (2 * 20 + 11) = 51 steps
        frames = [self.start(0), frame(51, [unit(1), unit(2)], actions=[move(2)], step=51),
                  frame(52, [unit(1), unit(2)], actions=[move(2)], step=52)]
        self.assertEqual(self.check(frames, [[move(1)], [], []]), ["a second run on a hex the unit has not left"])
        frames = [self.start(0), frame(5, [unit(1), unit(2, 21)], actions=[move(2, (22,))], step=5)]
        self.assertEqual(self.check(frames, [[move(1)], []]), ["no co-located MOVE with the same first hex is kept"])

    def test_second_run_needs_a_departure(self) -> None:
        frames = [self.start(0), frame(60, [unit(1), unit(2)], actions=[move(1), move(2)], step=60)]
        self.assertEqual(self.check(frames, [[move(1)], [move(1)]]), ["a second run on a hex the unit has not left"])
        frames = [self.start(0), frame(10, [unit(1), unit(2, 25)], step=10),
                  frame(60, [unit(1), unit(2)], actions=[move(1), move(2)], step=60)]
        self.assertEqual(self.check(frames, [[move(1)], [], [move(1)]]), [])

    def test_an_excluded_unreadable_co_mover_is_not_unexplained(self) -> None:
        f = self.start(own=[unit(1), unit(2), unit(3, tau=None)], actions=[move(1), move(2), move(3)])
        result = ts.decide(0, 2, f.own, f.enemies.values(), f.valid, f.actions, ts.StaggerMemory(), travel)
        self.assertEqual([dict(a) for a in result.actions], [move(1), move(3)])
        self.assertEqual(self.check([f], [result.actions]), [])
        self.assertEqual(self.check([f], [[move(1), move(2)]]), ["the removed MOVE's free-flow time is unreadable"])

    def test_real_shadow_has_no_unexplained_difference_over_a_long_wait(self) -> None:
        frames = [frame(t, [unit(1, path=(h(21),) if t else ()), unit(2), unit(3)],
                        actions=[move(1), move(2), move(3)] if t == 0 else [move(2), move(3)], step=t) for t in range(120)]
        a = st.analyse_side(side(frames))
        self.assertEqual(a.shadow.unexplained, [])
        self.assertEqual(max(k for k in a.shadow.withheld), 50)              # the leader never leaves: timeout


def fake_analysis(population, label, scenario_side, rows):
    sd = types.SimpleNamespace(population=population, label=label, scenario_side=scenario_side, game=label, faction=0)
    return types.SimpleNamespace(side=sd, shadow=types.SimpleNamespace(episodes=rows))


def ep(step, units=(1, 2), risk=False):
    m = {u: types.SimpleNamespace(route=(h(21), h(22))) for u in units}
    return {"start_step": step, "origin": h(20), "first_hex": h(21), "chain": list(units), "members": m,
            "first_owner_risk": risk}


def hh_sides(counts, risks=None):
    risks = risks or [0] * len(counts)
    return [fake_analysis("HH", f"HH p0{i + 1} baseline-v2 red", f"{SCENARIO} red",
                          [ep(1000 * i + j, risk=j < r) for j in range(n)])
            for i, (n, r) in enumerate(zip(counts, risks))]


def h0_sides(n_sides):
    return [fake_analysis("H0", f"H0 S{i} red", f"S{i} red", [ep(5)]) for i in range(n_sides)]


class StopTest(unittest.TestCase):
    def test_stop_a_exact_ten(self) -> None:
        self.assertFalse(st.stops(hh_sides([10, 10, 10, 10]) + h0_sides(4))["A_hh_opportunity"]["met"])
        self.assertTrue(st.stops(hh_sides([10, 9, 30, 30]) + h0_sides(4))["A_hh_opportunity"]["met"])
        self.assertTrue(st.stops(hh_sides([40, 40, 40]) + h0_sides(4))["A_hh_opportunity"]["met"])  # a side-game missing

    def test_stop_b_exact_four(self) -> None:
        self.assertFalse(st.stops(hh_sides([10] * 4) + h0_sides(4))["B_h0_generality"]["met"])
        self.assertTrue(st.stops(hh_sides([10] * 4) + h0_sides(3))["B_h0_generality"]["met"])
        empty = [fake_analysis("H0", f"H0 E{i} red", f"E{i} red", []) for i in range(10)]
        out = st.stops(hh_sides([10] * 4) + h0_sides(3) + empty)["B_h0_generality"]
        self.assertEqual((out["h0_scenario_sides_with_an_episode"], out["met"]), (3, True))
        twin = fake_analysis("H0", "H0 S0 red again", "S0 red", [ep(9)])
        out = st.stops(hh_sides([10] * 4) + h0_sides(3) + [twin])["B_h0_generality"]
        self.assertEqual((out["h0_scenario_sides_with_an_episode"], out["met"]), (3, True))

    def test_stop_c_one_half_passes_more_fails(self) -> None:
        sides = [fake_analysis("HH", "HH p01 baseline-v2 red", "x", [ep(i, risk=i < 2) for i in range(4)])]
        c = st.stops(sides)["C_onward_capture_conflict"]
        self.assertEqual((c["episodes_distinct"], c["first_owner_risk_episodes"], c["met"]), (4, 2, False))
        sides = [fake_analysis("HH", "HH p01 baseline-v2 red", "x", [ep(i, risk=i < 3) for i in range(5)])]
        c = st.stops(sides)["C_onward_capture_conflict"]
        self.assertEqual((c["first_owner_risk_episodes"], c["met"], c["share"]), (3, True, "3/5"))
        self.assertTrue(st.stops([fake_analysis("HH", "HH p01 baseline-v2 red", "x", [])])["C_onward_capture_conflict"]["met"])

    def test_stop_c_replicas_count_once_and_at_risk_in_any(self) -> None:
        a = fake_analysis("HH", "HH p01 baseline-v2 red", "x", [ep(7), ep(8)])
        b = fake_analysis("HH", "HH p03 baseline-v2 red", "x", [ep(7, risk=True), ep(9)])
        c = st.stops([a, b])["C_onward_capture_conflict"]
        self.assertEqual((c["episodes_raw"], c["episodes_distinct"], c["first_owner_risk_episodes"]), (4, 3, 1))
        other = fake_analysis("HH", "HH p02 baseline-v2 blue", "y", [ep(7)])
        self.assertEqual(st.stops([a, other])["C_onward_capture_conflict"]["episodes_distinct"], 3)


class DispositionTest(unittest.TestCase):
    def stop(self, a=False, b=False, c=False):
        return {"A_hh_opportunity": {"met": a}, "B_h0_generality": {"met": b}, "C_onward_capture_conflict": {"met": c}}

    def test_precedence(self) -> None:
        d = st.disposition
        self.assertEqual(d(False, True, 0, self.stop())["disposition"], "T6_S_INVALID")
        self.assertEqual(d(True, False, 0, self.stop())["disposition"], "T6_S_INVALID")
        self.assertEqual(d(True, True, 1, self.stop())["disposition"], "T6_S_INVALID")
        self.assertEqual(d(False, True, 0, self.stop(a=True, c=True))["disposition"], "T6_S_INVALID")
        self.assertEqual(d(True, True, 0, self.stop(a=True))["disposition"], "T6_S_INADEQUATE_OPPORTUNITY")
        self.assertEqual(d(True, True, 0, self.stop(b=True, c=True))["disposition"], "T6_S_INADEQUATE_OPPORTUNITY")
        self.assertEqual(d(True, True, 0, self.stop(c=True))["disposition"], "T6_S_ONWARD_CAPTURE_RISK")
        out = d(True, True, 0, self.stop())
        self.assertEqual((out["disposition"], out["stops_met"]), ("T6_S_OFFLINE_PASS", []))
        self.assertEqual(d(True, True, 0, self.stop(a=True, b=True, c=True))["stops_met"],
                         ["A_hh_opportunity", "B_h0_generality", "C_onward_capture_conflict"])


class CensusTest(unittest.TestCase):
    def test_decision_level_counts(self) -> None:
        frames = [frame(0, [unit(1), unit(2), unit(3), unit(4, 30), unit(5, 30), unit(9, type_=3)],
                        actions=[move(1), move(2), move(3, (19,)), move(4, (31,)), move(5, (29,)), move(9)]),
                  frame(1, [unit(1), unit(2)], enemies=(enemy(44),), actions=[move(1), move(2)])]
        c = st.census(side(frames))
        self.assertEqual(c, {"ground_move_orders": 7, "move_orders": 8, "same_hex_group_moves": 7, "same_hex_groups": 3,
                             "same_hex_groups_all_one_first_hex": 1, "shared_first_hex_groups": 2,
                             "shared_first_hex_groups_threat_exposed": 1})

    def test_exposure_counts(self) -> None:
        frames = [frame(0, [unit(1, path=(h(21),)), unit(2, 57, path=(h(58),), stack=0), unit(3), unit(4, 25, type_=3,
                                                                                                       path=(h(26),))])]
        e = st.exposure(side(frames))
        self.assertEqual(e, {"moving_alone_unit_decisions": 1, "moving_stacked_inside_envelope": 1,
                             "moving_stacked_unit_decisions": 1, "moving_unit_decisions": 2})


class S25IntersectionTest(unittest.TestCase):
    def analysis(self, frames, population="HH"):
        return st.analyse_side(side(frames, population=population,
                                    label=None if population == "HH" else f"H0 {SCENARIO} red"))

    def test_categories(self) -> None:
        a = self.analysis(column_frames())
        orders = {1: {"order_k": 0, "action": move(1)}, 2: {"order_k": 0, "action": move(2)}}
        self.assertEqual(st.s25_category(a, [1, 2], orders)[0], st.S25_CATEGORIES[6])
        self.assertEqual(st.s25_category(a, [1, 2], {1: orders[1], 2: {"order_k": 3, "action": move(2)}})[0],
                         st.S25_CATEGORIES[0])
        frames = column_frames()
        frames[0] = frame(0, [unit(1), unit(2, 30)], actions=[move(1), move(2, (31,))])
        b = self.analysis(frames)
        self.assertEqual(st.s25_category(b, [1, 2], {1: orders[1], 2: {"order_k": 0, "action": move(2, (31,))}})[0],
                         st.S25_CATEGORIES[1])
        frames[0] = frame(0, [unit(1), unit(2)], actions=[move(1), move(2, (19,))])
        c = self.analysis(frames)
        self.assertEqual(st.s25_category(c, [1, 2], {1: orders[1], 2: {"order_k": 0, "action": move(2, (19,))}})[0],
                         st.S25_CATEGORIES[2])
        frames[0] = frame(0, [unit(1), unit(2)], enemies=(enemy(44),), actions=[move(1), move(2)])
        d = self.analysis(frames)
        self.assertEqual(st.s25_category(d, [1, 2], orders)[0], st.S25_CATEGORIES[3])
        frames[0] = frame(0, [unit(1), unit(2)], actions=[move(1)])
        e = self.analysis(frames, population="H0")
        self.assertEqual(st.s25_category(e, [1, 2], orders)[0], st.S25_CATEGORIES[4])
        frames[0] = frame(0, [unit(1), unit(2, tau=None)], actions=[move(1), move(2)])
        f = self.analysis(frames)
        self.assertEqual(st.s25_category(f, [1, 2], orders)[0], st.S25_CATEGORIES[5])

    def test_later_trigger_is_not_valid(self) -> None:
        frames = column_frames(n=60)
        frames[50] = frame(50, [unit(1, 22), unit(2, 22), unit(3, 30), unit(4, 30)],
                           actions=[move(3, (31, 32)), move(4, (31, 32))])
        a = self.analysis(frames)
        orders = {3: {"order_k": 50, "action": move(3, (31, 32))}, 4: {"order_k": 50, "action": move(4, (31, 32))}}
        self.assertEqual(st.s25_category(a, [3, 4], orders)[0], st.S25_CATEGORIES[7])


class PublicTest(unittest.TestCase):
    def outputs(self):
        frames = column_frames(n=60, owner_at=40)
        frames[50] = frame(50, [unit(1, 22), unit(2, 22), unit(3, 30), unit(4, 30)],
                           actions=[move(3, (31, 32)), move(4, (31, 32))])
        a = st.analyse_side(side(frames))
        data = {"summary": st.side_summary(a), "certificate": st.certificate(a), "pooled": st.pooled([a]),
                "rows": [st.public_episode(a, r, i, True, r["first_owner_risk"]) for i, r in enumerate(a.shadow.episodes, 1)],
                "stops": st.stops([a])}
        private = set(range(50)) | {h(c) for c in range(60)}
        return data, private

    def test_sanitizer_passes_with_small_private_ids(self) -> None:
        data, private = self.outputs()
        self.assertEqual(st.public_problems(data, private), [])
        self.assertEqual(st.digit_words(data, {SCENARIO}), [])
        self.assertEqual(data["rows"][0]["followers"][0]["destination"], "80-point objective A")

    def test_sanitizer_catches_a_number_word_in_a_label(self) -> None:
        data, private = self.outputs()
        data["rows"][0]["note"] = "seen within the previous 2 steps"
        self.assertTrue(st.public_problems(data, private))
        self.assertEqual(st.digit_words(data, {SCENARIO}), ["2"])

    def test_no_private_field_names(self) -> None:
        data, _ = self.outputs()
        text = repr(data)
        for key in ("obj_id", "cur_hex", "move_path", "'route'", "'chain'", "'origin'", "'first_hex'"):
            self.assertNotIn(key, text)

    def test_registered_labels_carry_no_digit_word(self) -> None:
        labels = (list(st.DISPOSITIONS) + list(st.S25_CATEGORIES) + [st.DEST_HELD, st.DEST_UNHELD, st.DEST_NOT_OBJECTIVE])
        self.assertEqual(st.digit_words(labels), [])


if __name__ == "__main__":
    unittest.main()
