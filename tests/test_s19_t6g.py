"""Sprint 19 T6-G gate, hold state machine and shadow analysis on synthetic frames (no private data needed).

Hexes are on one even row (``1000 + column``), so the distance between two of them is the difference of their columns;
``setUpModule`` asserts that with the project's own distance function rather than trusting the arithmetic.
"""

from __future__ import annotations

import unittest

from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation import s19_t6g as st
from miaosuan_agent.evaluation.t7_visibility import hex_distance
from miaosuan_agent.experiments import t6_threat_entry_gate as tg

RED, BLUE = 0, 1
INF, VEH, AIR = 1, 2, 3
BIG_GUN = 36        # (10 against personnel, 18 against vehicles)
LIGHT = 29          # (3, 3)
RAPID_GROUND = 4    # (10, not published against vehicles)
ARTILLERY = 72      # indirect fire: not in the direct-fire table


def h(col: int) -> int:
    return 1000 + col


def setUpModule() -> None:
    for a, b in ((0, 30), (12, 30), (11, 30), (7, 30), (8, 30), (40, 30)):
        assert hex_distance(h(a), h(b)) == abs(a - b), (a, b)


def unit(obj, hex_, *, type_=VEH, color=RED, weapons=(BIG_GUN,), path=(), stack=0, close=0, sub=1):
    return {"obj_id": obj, "type": type_, "sub_type": sub, "color": color, "cur_hex": hex_, "move_path": list(path),
            "speed": 0, "stack": stack, "close_combat": close, "carry_weapon_ids": list(weapons), "blood": 4}


def move(obj, cols):
    return {"actor": 1, "obj_id": obj, "type": 1, "move_path": [h(c) for c in cols]}


ENEMY = unit(900, h(30), color=BLUE)                    # covers vehicles to 18 hexes: columns 12 to 48
MOVER = unit(1, h(0))                                   # 30 hexes away: outside
ROUTE_IN_AT_5 = (8, 9, 10, 11, 12)                      # from column 7: distances 22, 21, 20, 19, 18


class ConditionTest(unittest.TestCase):
    def check(self, mover, cols, enemies=(ENEMY,)):
        return tg.threat_entry(mover, [h(c) for c in cols], [dict(e) for e in enemies])

    def test_current_position_outside_and_fifth_route_hex_inside(self) -> None:
        c = self.check(unit(1, h(7)), ROUTE_IN_AT_5)
        self.assertTrue(c.eligible)
        self.assertEqual((c.first_entry_index, len(c.inspected), len(c.causing)), (5, 5, 1))

    def test_current_position_exactly_at_range_is_inside(self) -> None:
        self.assertEqual(hex_distance(h(12), h(30)), 18)
        c = self.check(unit(1, h(12)), (13, 14))
        self.assertEqual((c.eligible, c.reason), (False, "current_hex_inside"))

    def test_one_hex_beyond_range_is_outside(self) -> None:
        c = self.check(unit(1, h(11)), (12,))
        self.assertEqual((c.eligible, c.first_entry_index), (True, 1))

    def test_first_route_hex_inside(self) -> None:
        c = self.check(unit(1, h(11)), (12, 13, 14, 15, 16, 17))
        self.assertEqual((c.eligible, c.first_entry_index, len(c.inspected)), (True, 1, 5))

    def test_sixth_route_hex_only_inside_does_not_gate(self) -> None:
        c = self.check(unit(1, h(6)), (7, 8, 9, 10, 11, 12))
        self.assertEqual((c.eligible, c.reason, len(c.inspected)), (False, "no_route_entry", 5))

    def test_short_route_uses_every_hex(self) -> None:
        c = self.check(unit(1, h(10)), (11, 12))
        self.assertEqual((c.eligible, len(c.inspected), c.first_entry_index), (True, 2, 2))

    def test_empty_route_cannot_trigger(self) -> None:
        self.assertEqual(self.check(unit(1, h(7)), ()).reason, "empty_route")

    def test_unreadable_route_fails_closed(self) -> None:
        c = tg.threat_entry(unit(1, h(7)), [h(8), "x", h(12)], [ENEMY])
        self.assertEqual((c.eligible, c.reason), (False, "unreadable_route"))

    def test_multiple_enemies_any_covers(self) -> None:
        far = unit(901, h(60), color=BLUE)
        c = self.check(unit(1, h(7)), ROUTE_IN_AT_5, (far, ENEMY))
        self.assertEqual((c.eligible, len(c.threats), len(c.causing)), (True, 2, 1))
        near = unit(902, h(20), color=BLUE)                     # covers column 7 (13 hexes)
        self.assertEqual(self.check(unit(1, h(7)), ROUTE_IN_AT_5, (far, ENEMY, near)).reason, "current_hex_inside")

    def test_multiple_weapons_longest_applicable_range(self) -> None:
        enemy = unit(900, h(30), color=BLUE, weapons=(LIGHT, BIG_GUN))
        self.assertTrue(self.check(unit(1, h(7)), ROUTE_IN_AT_5, (enemy,)).eligible)
        light_only = unit(900, h(30), color=BLUE, weapons=(LIGHT,))
        self.assertEqual(self.check(unit(1, h(7)), ROUTE_IN_AT_5, (light_only,)).reason, "no_route_entry")

    def test_range_follows_the_mover_class(self) -> None:
        # against personnel the big gun reaches 10: column 12 is 18 away, so infantry is not gated there
        self.assertEqual(self.check(unit(1, h(7), type_=INF), ROUTE_IN_AT_5).reason, "no_route_entry")
        self.assertTrue(self.check(unit(1, h(19), type_=INF), (20,)).eligible)

    def test_non_direct_fire_weapon_ignored(self) -> None:
        artillery = unit(900, h(30), color=BLUE, weapons=(ARTILLERY,))
        self.assertEqual(self.check(unit(1, h(7)), ROUTE_IN_AT_5, (artillery,)).reason, "no_qualifying_threat")
        rapid = unit(900, h(30), color=BLUE, weapons=(RAPID_GROUND,))
        self.assertEqual(self.check(unit(1, h(7)), ROUTE_IN_AT_5, (rapid,)).reason, "no_qualifying_threat")

    def test_no_qualifying_visible_enemy(self) -> None:
        self.assertEqual(self.check(unit(1, h(7)), ROUTE_IN_AT_5, ()).reason, "no_qualifying_threat")
        unreadable = dict(ENEMY, cur_hex=None)
        self.assertEqual(self.check(unit(1, h(7)), ROUTE_IN_AT_5, (unreadable,)).reason, "no_qualifying_threat")

    def test_non_ground_mover_and_missing_mover(self) -> None:
        self.assertEqual(self.check(unit(1, h(7), type_=AIR), ROUTE_IN_AT_5).reason, "not_ground")
        self.assertEqual(tg.threat_entry(None, [h(8)], [ENEMY]).reason, "not_ground")
        self.assertEqual(self.check(dict(unit(1, h(7)), cur_hex=None), ROUTE_IN_AT_5).reason, "unreadable_mover")


class StateMachineTest(unittest.TestCase):
    OWN = {1: unit(1, h(7)), 2: unit(2, h(0))}

    def step(self, t, memory, actions=None, enemies=(ENEMY,), own=None):
        actions = [move(1, ROUTE_IN_AT_5)] if actions is None else actions
        return tg.apply_gate(t, self.OWN if own is None else own, [dict(e) for e in enemies], actions, memory)

    def kinds(self, result):
        return [(e.kind, e.reason) for e in result.events]

    def test_hold_start_and_repeat(self) -> None:
        r = self.step(100, tg.GateMemory())
        self.assertEqual((r.dropped, r.actions, self.kinds(r)), ((0,), (), [("gate_start", None)]))
        self.assertEqual(r.memory.entries, ((1, tg.HOLD, 100),))
        r2 = self.step(101, r.memory)
        self.assertEqual((r2.dropped, self.kinds(r2)), ((0,), [("gate_repeat", None)]))
        self.assertEqual(r2.memory, r.memory)

    def test_early_threat_disappearance_releases(self) -> None:
        r = self.step(100, tg.GateMemory())
        r2 = self.step(120, r.memory, enemies=())
        self.assertEqual((r2.dropped, self.kinds(r2)), ((), [("release", "condition_cleared")]))
        self.assertEqual(r2.memory.entries, ((1, tg.COOL, 120),))

    def test_exact_hold_limit_boundary(self) -> None:
        m = self.step(100, tg.GateMemory()).memory
        r = self.step(249, m)
        self.assertEqual(r.dropped, (0,))                 # 149 steps into the hold: still held
        r = self.step(250, r.memory)                      # 150: released, the move passes
        self.assertEqual((r.dropped, self.kinds(r)), ((), [("release", "hold_limit")]))
        self.assertEqual(r.memory.entries, ((1, tg.COOL, 250),))

    def test_exact_cooldown_boundary(self) -> None:
        m = self.step(250, tg.GateMemory(((1, tg.HOLD, 100),))).memory
        r = self.step(549, m)
        self.assertEqual((r.dropped, self.kinds(r)), ((), [("cooldown_suppressed", None)]))
        r = self.step(550, r.memory)
        self.assertEqual((r.dropped, self.kinds(r)), ((0,), [("gate_start", None)]))

    def test_no_baseline_move_releases_and_starts_cooldown(self) -> None:
        m = self.step(100, tg.GateMemory()).memory
        r = self.step(101, m, actions=[{"actor": 1, "obj_id": 1, "type": 2, "target_obj_id": 900, "weapon_id": 36}])
        self.assertEqual(self.kinds(r), [("release", "no_baseline_move")])
        self.assertEqual(r.memory.entries, ((1, tg.COOL, 101),))
        self.assertEqual(self.step(102, r.memory).dropped, ())

    def test_unit_disappearance_deletes_state(self) -> None:
        m = self.step(100, tg.GateMemory()).memory
        r = self.step(101, m, actions=[], own={2: self.OWN[2]})
        self.assertEqual((self.kinds(r), r.memory.entries), ([("release", "unit_absent")], ()))
        cooled = tg.GateMemory(((1, tg.COOL, 90),))
        self.assertEqual(self.step(101, cooled, actions=[], own={2: self.OWN[2]}).memory.entries, ())

    def test_reset_between_games(self) -> None:
        held = self.step(100, tg.GateMemory()).memory
        self.assertEqual(self.step(5, tg.GateMemory()).dropped, (0,))       # a new game starts from an empty memory
        self.assertEqual(self.step(5, held).dropped, (0,))                  # the old memory would read as a repeat
        frames = [frame(100, {1: unit(1, h(7))}, [move(1, ROUTE_IN_AT_5)], (ENEMY,))]
        first, second = st.shadow_side(frames), st.shadow_side(frames)
        self.assertEqual((len(first.episodes), len(second.episodes)), (1, 1))

    def test_deterministic_memory(self) -> None:
        own = {3: unit(3, h(7)), 1: unit(1, h(7))}
        acts = [move(3, ROUTE_IN_AT_5), move(1, ROUTE_IN_AT_5)]
        a = tg.apply_gate(100, own, [ENEMY], acts, tg.GateMemory())
        b = tg.apply_gate(100, own, [ENEMY], acts, tg.GateMemory())
        self.assertEqual(a, b)
        self.assertEqual([e[0] for e in a.memory.entries], [1, 3])

    def test_order_preserved_and_only_the_move_removed(self) -> None:
        own = {1: unit(1, h(7)), 2: unit(2, h(0)), 4: unit(4, h(40))}
        shoot = {"actor": 1, "obj_id": 4, "type": 2, "target_obj_id": 900, "weapon_id": 36}
        occupy = {"actor": 1, "obj_id": 2, "type": 5}
        free = move(2, (1, 2))                          # 28 and 29 hexes away: not gated
        acts = [shoot, move(1, ROUTE_IN_AT_5), occupy, free]
        before = [dict(a) for a in acts]
        r = tg.apply_gate(100, own, [ENEMY], acts, tg.GateMemory())
        self.assertEqual(r.dropped, (1,))
        self.assertEqual(list(r.actions), [shoot, occupy, free])
        self.assertEqual(acts, before)                  # the input list is not modified

    def test_custom_rules_never_fire_with_empty_prefix(self) -> None:
        r = tg.apply_gate(100, self.OWN, [ENEMY], [move(1, ROUTE_IN_AT_5)], tg.GateMemory(), tg.GateRules(route_prefix=0))
        self.assertEqual((r.dropped, r.checks[0][2].reason), ((), "empty_route"))


def frame(step, own, actions, enemies=(), *, k=None, cities=None, faction=RED):
    units = list(own.values()) + [dict(e) for e in enemies]
    raw = {"time": {"cur_step": step, "max_step": 2880, "stage": 2}, "operators": units, "passengers": [],
           "valid_actions": {}, "cities": cities or [], "judge_info": []}
    return sc.frame_from_raw(step if k is None else k, raw, faction, actions)


def judge(step, attacker, target, damage=1):
    return {"cur_step": step, "att_obj_id": attacker, "target_obj_id": target, "damage": damage, "distance": 5,
            "attack_color": BLUE, "target_color": RED, "type": "direct", "ele_diff": 0}


class ShadowTest(unittest.TestCase):
    """A small red side: unit 1 is gated twice (episodes at 0 and after its cooldown), unit 2 never."""

    def build(self):
        red, blue = [], []
        city = [{"coord": h(12), "flag": -1, "value": 80}]
        for k in range(0, 8):
            step = [0, 1, 2, 3, 301, 302, 303, 304][k]
            own = {1: unit(1, h(7)), 2: unit(2, h(0))}
            acts = [move(1, ROUTE_IN_AT_5)] if step in (0, 1, 302, 303) else []
            if step == 304:                              # unit 1 stands on the objective, now owned
                own[1] = unit(1, h(12))
                city = [{"coord": h(12), "flag": RED, "value": 80}]
            red.append(frame(step, own, acts, (ENEMY,), k=k, cities=city))
            blue.append(frame(step, {900: dict(ENEMY)}, [], k=k, cities=city, faction=BLUE))
        events = [(2, judge(76, 900, 1)), (4, judge(301, 900, 1))]
        for k, f in enumerate(red):
            f.k = k
        return sc.Game("HH", "g.p01", "s", {RED: red, BLUE: blue}, events, (RED,))

    def test_episodes_releases_and_damage(self) -> None:
        a = st.analyse_side("HH", "HH p01 baseline-v2 red", self.build(), RED, {h(12): 80})
        self.assertEqual([(e["step"], e["repeats"], e["reason"]) for e in a.episodes],
                         [(0, 1, "no_baseline_move"), (302, 1, "no_baseline_move")])
        self.assertEqual(a.shadow.gated_decisions, 4)
        self.assertEqual(len(a.shadow.opportunities), 4)
        first = a.episodes[0]
        # from the gate at 0: the hit at 76 is outside 75 and inside 150; the hit at 301 is outside 300
        self.assertEqual(first["damaged_within"], {"75": False, "150": True, "300": True})
        self.assertEqual(first["first_damage"]["step"], 76)
        self.assertEqual(a.episodes[1]["damaged_within"], {"75": False, "150": False, "300": False})
        self.assertTrue(first["first_damage"]["attacker_caused_gate"])
        self.assertTrue(all(a.integrity.values()), a.integrity)

    def test_ownership_participants_and_capturers(self) -> None:
        a = st.analyse_side("HH", "HH p01 baseline-v2 red", self.build(), RED, {h(12): 80})
        self.assertEqual([(o["step"], sorted(o["participants"])) for o in a.ownerships], [(304, [1])])
        self.assertEqual((a.gated, a.participants), ({1}, {1}))
        timing = st.objective_timing([a], {a.label: {h(12): 80}})
        self.assertEqual(timing[0]["gated_before_first_ownership"], 1)
        self.assertEqual(timing[0]["steps_from_earliest_gate_to_first_ownership"], 304)
        self.assertEqual(timing[0]["objective"], "80-point objective A")

    def test_initial_ownership_has_no_participants(self) -> None:
        f0 = frame(0, {1: unit(1, h(12))}, [], cities=[{"coord": h(12), "flag": RED}])
        (o,) = st.first_ownerships([f0], RED)
        self.assertEqual((o["initial"], o["participants"]), (True, frozenset()))

    def test_open_episode_closed_at_the_end(self) -> None:
        frames = [frame(s, {1: unit(1, h(7))}, [move(1, ROUTE_IN_AT_5)], (ENEMY,), k=i) for i, s in enumerate((0, 1, 2))]
        s = st.shadow_side(frames)
        self.assertEqual([(e.reason, e.repeats, e.release_step) for e in s.episodes], [(st.OPEN_AT_END, 2, 2)])

    def test_damage_windows_are_inclusive(self) -> None:
        index = st.damage_index([{"victim": 1, "step": s, "k": 0} for s in (75, 150, 300, 301)])
        self.assertEqual([len(st.damage_between(index, 1, 0, w)) for w in st.WINDOWS], [1, 2, 3])


class CapturerAndDispositionTest(unittest.TestCase):
    def side(self, label, gated, participants):
        return st.SideAnalysis("HH", label, st.SideShadow(), [], [], [], set(gated), set(participants), {})

    def test_pooled_fraction_deduplicates_only_within_a_side_game(self) -> None:
        sides = [self.side("a", {1, 2}, {1}), self.side("b", {1, 2}, {1, 2})]
        c = st.capturer_fraction(sides)
        self.assertEqual((c["participants"], c["gated"], c["fraction"]), (3, 4, 0.75))

    def test_disposition_order_and_boundaries(self) -> None:
        d = st.disposition
        self.assertEqual(d(True, [10, 10, 10, 10], 5, 10)["disposition"], "T6_G_OFFLINE_PASS")          # exactly 0.50
        self.assertEqual(d(True, [10, 10, 10, 10], 6, 11)["disposition"], "T6_G_OFFLINE_CAPTURE_RISK")  # 0.545
        self.assertEqual(d(True, [10, 10, 10, 10], 6, 10)["disposition"], "T6_G_OFFLINE_CAPTURE_RISK")
        self.assertEqual(d(True, [10, 9, 10, 10], 0, 10)["disposition"], "T6_G_OFFLINE_INADEQUATE_OPPORTUNITY")
        self.assertEqual(d(True, [10, 10, 10], 0, 10)["disposition"], "T6_G_OFFLINE_INADEQUATE_OPPORTUNITY")
        self.assertEqual(d(True, [40, 40, 40, 40, 40], 0, 10)["disposition"], "T6_G_OFFLINE_INADEQUATE_OPPORTUNITY")
        self.assertEqual(d(False, [10, 10, 10, 10], 0, 10)["disposition"], "REPLAY_INVALID")
        self.assertEqual(d(True, [9, 9, 9, 9], 10, 10)["disposition"], "T6_G_OFFLINE_INADEQUATE_OPPORTUNITY")
        # a pooled count never replaces a failing side-game
        self.assertEqual(d(True, [40, 9, 10, 10], 0, 10)["disposition"], "T6_G_OFFLINE_INADEQUATE_OPPORTUNITY")
        self.assertEqual(d(True, [10, 10, 10, 10], 0, 1)["disposition"], "T6_G_OFFLINE_PASS")

    def test_opportunity_counts_first_gates_not_gated_decisions(self) -> None:
        frames = [frame(s, {1: unit(1, h(7))}, [move(1, ROUTE_IN_AT_5)], (ENEMY,), k=i) for i, s in enumerate(range(12))]
        s = st.shadow_side(frames)
        self.assertEqual((len(s.episodes), s.gated_decisions), (1, 12))
        side = st.SideAnalysis("HH", "a", s, [{}], [], [], {1}, set(), {})
        self.assertEqual(st.gate_episode_counts([side, side]), [1, 1])


class PublicOutputTest(unittest.TestCase):
    def test_sanitizer_masks_numbers_and_checks_keys_and_words(self) -> None:
        p = st.public_problems
        self.assertEqual(p({"count": 930001}, {930001}), [])
        self.assertTrue(p({"note": "unit 930001 held"}, {930001}))
        self.assertTrue(p({"930001": 1}, {930001}))
        self.assertTrue(p({"units": 1}, set()))
        self.assertTrue(p({"move_path": []}, set()))

    def test_public_side_and_certificate_carry_no_private_value(self) -> None:
        a = st.analyse_side("HH", "HH p01 baseline-v2 red", ShadowTest().build(), RED, {h(12): 80})
        private = {1, 2, 900, h(0), h(7), h(12), h(30)} | {h(c) for c in ROUTE_IN_AT_5}
        for data in (st.public_side(a), st.certificate(a, {h(12): 80}), st.pooled([a]),
                     st.objective_timing([a], {a.label: {h(12): 80}})):
            self.assertEqual(st.public_problems(data, private), [])
            text = repr(st.mask_numbers(data))
            for value in private - {1, 2}:              # one-digit ids occur inside labels such as "p01"
                self.assertNotIn(str(value), text)
        cert = st.certificate(a, {h(12): 80})
        self.assertEqual((cert["baseline_action_types"], cert["gate_action_types"], cert["dropped_position"]),
                         ([1], [], 0))
        self.assertEqual((cert["first_entry_index"], cert["causing_ranges"], cert["current_margin_outside_range"]),
                         (5, [18], 5))


if __name__ == "__main__":
    unittest.main()
