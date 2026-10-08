"""Sprint 25 T13 garrison shadow (``experiments/t13_garrison_shadow.py``) on synthetic states (no private data needed).

Hexes on one even row are ``1000 + column`` (distance = column difference); ``setUpModule`` asserts every distance the
tests rely on with the project's own function, including the six neighbours of the objective in the rows above and
below.
"""

from __future__ import annotations

import unittest

from miaosuan_agent.decision import policy
from miaosuan_agent.evaluation.t7_visibility import hex_distance
from miaosuan_agent.experiments import t13_garrison_shadow as tg

RED, BLUE = 0, 1
INF, VEH, AIR = 1, 2, 3
BIG_GUN = 36        # 10 against personnel, 18 against vehicles
RAPID_GROUND = 4    # 10 against personnel, not published against vehicles
INDIRECT = 72       # not in the direct-fire table
OBJ = 1030
OTHER_OBJ = 1032
NEIGHBOURS = (1029, 1031, 929, 930, 1129, 1130)


def h(col: int) -> int:
    return 1000 + col


def setUpModule() -> None:
    for a, b in ((30, 49), (30, 50), (30, 41), (30, 42), (30, 31), (30, 32), (31, 32)):
        assert hex_distance(h(a), h(b)) == abs(a - b), (a, b)
    assert sorted(x for x in range(800, 1300) if hex_distance(x, OBJ) == 1) == sorted(NEIGHBOURS), "neighbours"


def unit(obj, hex_, *, type_=VEH, sub=1, color=RED, weapons=(BIG_GUN,), path=()):
    return {"obj_id": obj, "type": type_, "sub_type": sub, "color": color, "cur_hex": hex_, "move_path": list(path),
            "carry_weapon_ids": list(weapons)}


def move(obj, cols):
    return {"actor": 1, "obj_id": obj, "type": 1, "move_path": [h(c) for c in cols]}


def shoot(obj):
    return {"actor": 1, "obj_id": obj, "type": 2, "target_obj_id": 900, "weapon_id": BIG_GUN}


def enemy(col, **kw):
    return unit(900, h(col), color=BLUE, **kw)


DEFENDER = unit(1, OBJ)
NEAR = enemy(49)            # vehicles: reach 18 + 1 = 19 -> qualifies
FAR = enemy(50)             # 20 -> does not
FLAGS = {OBJ: RED}
LEAVE = move(1, (31, 32, 33))
STAY = move(1, (31,))


def decide(step, own, enemies, actions, memory=tg.GarrisonMemory(), flags=None, stage=2):
    return tg.decide(RED, step, stage, {u["obj_id"]: u for u in own}, enemies, FLAGS if flags is None else flags,
                     actions, memory)


class TriggerTest(unittest.TestCase):
    def check(self, own, enemies, action, flags=None):
        own_map = {u["obj_id"]: u for u in own}
        return tg.trigger(RED, own_map, enemies, FLAGS if flags is None else flags, [action], action)

    def test_single_defender_on_the_objective_leaving_with_a_threat_near(self) -> None:
        c = self.check([DEFENDER], [NEAR], LEAVE)
        self.assertEqual((c.eligible, c.reason, c.objective), (True, "eligible", OBJ))
        self.assertEqual([(t.reach, t.distance) for t in c.threats], [(18, 19)])

    def test_defender_on_each_adjacent_hex(self) -> None:
        for n in NEIGHBOURS:
            c = self.check([unit(1, n)], [NEAR], {"actor": 1, "obj_id": 1, "type": 1, "move_path": [h(33)]})
            self.assertTrue(c.eligible, n)

    def test_two_hexes_away_is_outside_the_zone(self) -> None:
        self.assertEqual(self.check([unit(1, h(32))], [NEAR], move(1, (33,))).reason, "not_in_a_held_zone")

    def test_objective_not_held(self) -> None:
        for flag in (BLUE, -1):
            self.assertEqual(self.check([DEFENDER], [NEAR], LEAVE, {OBJ: flag}).reason, "not_in_a_held_zone")

    def test_two_own_units_in_the_zone(self) -> None:
        self.assertEqual(self.check([DEFENDER, unit(2, h(31))], [NEAR], LEAVE).reason, "zone_not_single")

    def test_artillery_is_not_a_defender_but_occupies(self) -> None:
        self.assertEqual(self.check([unit(1, OBJ, sub=3)], [NEAR], LEAVE).reason, "artillery")
        self.assertEqual(self.check([DEFENDER, unit(2, h(31), sub=3)], [NEAR], LEAVE).reason, "zone_not_single")

    def test_aircraft_neither_defends_nor_occupies(self) -> None:
        self.assertEqual(self.check([unit(1, OBJ, type_=AIR)], [NEAR], LEAVE).reason, "not_ground")
        self.assertTrue(self.check([DEFENDER, unit(2, h(31), type_=AIR)], [NEAR], LEAVE).eligible)

    def test_unit_absent_or_hex_unreadable(self) -> None:
        self.assertEqual(self.check([], [NEAR], LEAVE).reason, "unit_absent")
        self.assertEqual(self.check([unit(1, None)], [NEAR], LEAVE).reason, "unreadable_unit_hex")

    def test_route_inside_the_zone_does_not_trigger(self) -> None:
        self.assertEqual(self.check([DEFENDER], [NEAR], STAY).reason, "route_stays_in_zone")

    def test_route_unreadable_or_empty_fails_closed(self) -> None:
        bad = {"actor": 1, "obj_id": 1, "type": 1, "move_path": [h(31), "x"]}
        self.assertEqual(self.check([DEFENDER], [NEAR], bad).reason, "unreadable_route")
        self.assertEqual(self.check([DEFENDER], [NEAR], move(1, ())).reason, "unreadable_route")

    def test_threat_distance_boundary_vehicle(self) -> None:
        self.assertTrue(self.check([DEFENDER], [NEAR], LEAVE).eligible)
        self.assertEqual(self.check([DEFENDER], [FAR], LEAVE).reason, "no_qualifying_threat")

    def test_threat_distance_boundary_infantry(self) -> None:
        inf = unit(1, OBJ, type_=INF, sub=2)
        self.assertTrue(self.check([inf], [enemy(41)], LEAVE).eligible)           # 10 + 1 = 11
        self.assertEqual(self.check([inf], [enemy(42)], LEAVE).reason, "no_qualifying_threat")

    def test_no_published_range_fails_closed(self) -> None:
        self.assertEqual(self.check([DEFENDER], [enemy(35, weapons=(INDIRECT,))], LEAVE).reason, "no_qualifying_threat")
        self.assertEqual(self.check([DEFENDER], [enemy(35, weapons=(RAPID_GROUND,))], LEAVE).reason,
                         "no_qualifying_threat")
        inf = unit(1, OBJ, type_=INF, sub=2)
        self.assertTrue(self.check([inf], [enemy(35, weapons=(RAPID_GROUND,))], LEAVE).eligible)

    def test_enemy_aircraft_is_not_a_ground_threat(self) -> None:
        self.assertEqual(self.check([DEFENDER], [enemy(35, type_=AIR)], LEAVE).reason, "no_qualifying_threat")

    def test_existing_path_leaving_the_zone_is_outside_scope(self) -> None:
        moving = unit(1, OBJ, path=(h(31), h(32)))
        self.assertEqual(self.check([moving], [NEAR], LEAVE).reason, "existing_path_exits")
        inside = unit(1, OBJ, path=(h(31),))
        self.assertTrue(self.check([inside], [NEAR], LEAVE).eligible)

    def test_transport_commitment(self) -> None:
        own = {1: DEFENDER}
        c = tg.trigger(RED, own, [NEAR], FLAGS, [LEAVE, {"actor": 1, "obj_id": 1, "type": 4, "target_obj_id": 5}], LEAVE)
        self.assertEqual(c.reason, "transport_committed")


class DecideTest(unittest.TestCase):
    def test_only_the_triggering_move_is_withheld_in_order(self) -> None:
        other = move(7, (40, 41))
        r = decide(10, [DEFENDER, unit(7, h(40))], [NEAR], [shoot(7), LEAVE, other])
        self.assertEqual(r.withheld, (1,))
        self.assertEqual(list(r.actions), [shoot(7), other])
        self.assertEqual([e.kind for e in r.events], ["start"])
        self.assertEqual(r.memory.holds, ((OBJ, 1, 10),))

    def test_inputs_are_not_modified_and_replay_is_deterministic(self) -> None:
        actions = [LEAVE]
        own = [DEFENDER]
        first = decide(10, own, [NEAR], actions)
        second = decide(10, own, [NEAR], actions)
        self.assertEqual(first, second)
        self.assertEqual(actions, [LEAVE])

    def test_non_play_decision_passes_unchanged(self) -> None:
        r = decide(0, [DEFENDER], [NEAR], [LEAVE], stage=1)
        self.assertEqual((r.withheld, list(r.actions), r.memory), ((), [LEAVE], tg.GarrisonMemory()))

    def test_hold_boundary_at_exactly_300_steps(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        r = decide(309, [DEFENDER], [NEAR], [LEAVE], m)
        self.assertEqual((r.withheld, [e.kind for e in r.events]), ((0,), ["repeat"]))
        r = decide(310, [DEFENDER], [NEAR], [LEAVE], r.memory)
        self.assertEqual(r.withheld, ())
        self.assertEqual([(e.kind, e.reason) for e in r.events], [("release", "hold_limit")])
        self.assertEqual(r.memory.cooldowns, ((OBJ, 310),))

    def test_expired_hold_cannot_restart_at_once(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        m = decide(310, [DEFENDER], [NEAR], [LEAVE], m).memory
        r = decide(609, [DEFENDER], [NEAR], [LEAVE], m)
        self.assertEqual((r.withheld, r.checks[0][2].reason), ((), "objective_in_cooldown"))
        r = decide(610, [DEFENDER], [NEAR], [LEAVE], r.memory)
        self.assertEqual((r.withheld, r.memory.holds), ((0,), ((OBJ, 1, 610),)))

    def test_release_when_a_backup_enters(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        r = decide(11, [DEFENDER, unit(2, h(31))], [NEAR], [LEAVE], m)
        self.assertEqual([(e.kind, e.reason) for e in r.events if e.kind == "release"], [("release", "backup_entered")])
        self.assertEqual(r.withheld, ())

    def test_release_when_the_threat_leaves(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        for enemies in ([], [FAR]):
            r = decide(11, [DEFENDER], enemies, [LEAVE], m)
            self.assertEqual([e.reason for e in r.events if e.kind == "release"], ["threat_cleared"])
            self.assertEqual(r.withheld, ())

    def test_release_when_defender_absent_outside_or_objective_lost(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        self.assertEqual([e.reason for e in decide(11, [], [NEAR], [], m).events], ["defender_absent"])
        self.assertEqual([e.reason for e in decide(11, [unit(1, h(32))], [NEAR], [], m).events],
                         ["defender_outside_zone"])
        self.assertEqual([e.reason for e in decide(11, [DEFENDER], [NEAR], [], m, flags={OBJ: BLUE}).events],
                         ["objective_not_held"])

    def test_release_precedence_is_first_match(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        r = decide(400, [DEFENDER, unit(2, h(31))], [], [], m)
        self.assertEqual([e.reason for e in r.events], ["backup_entered"])

    def test_hold_survives_decisions_without_a_move(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        r = decide(11, [DEFENDER], [NEAR], [shoot(1)], m)
        self.assertEqual((r.events, r.memory.holds), ((), ((OBJ, 1, 10),)))

    def test_move_inside_the_zone_passes_during_a_hold(self) -> None:
        m = decide(10, [DEFENDER], [NEAR], [LEAVE]).memory
        r = decide(11, [DEFENDER], [NEAR], [STAY], m)
        self.assertEqual((r.withheld, [e.kind for e in r.events]), ((), ["pass_in_hold"]))

    def test_withholding_does_not_cancel_an_existing_path(self) -> None:
        moving = unit(1, OBJ, path=(h(31), h(32)))
        r = decide(10, [moving], [NEAR], [LEAVE])
        self.assertEqual((r.withheld, r.checks[0][2].reason), ((), "existing_path_exits"))

    def test_overlapping_zones_one_episode_one_withholding(self) -> None:
        flags = {OBJ: RED, OTHER_OBJ: RED}
        r = decide(10, [unit(1, h(31))], [NEAR], [move(1, (34, 35))], flags=flags)
        self.assertEqual(r.withheld, (0,))
        self.assertEqual([(e.kind, e.objective) for e in r.events], [("start", OBJ), ("overlap", OTHER_OBJ)])
        self.assertEqual(r.memory.holds, ((OBJ, 1, 10),))
        r = decide(11, [unit(1, h(31))], [NEAR], [move(1, (34, 35))], r.memory, flags=flags)
        self.assertEqual((r.withheld, [e.kind for e in r.events]), ((0,), ["repeat"]))

    def test_overlap_owner_is_the_nearer_objective_before_the_lower_hex(self) -> None:
        flags = {OBJ: RED, h(31): RED}
        r = decide(10, [unit(1, h(31))], [NEAR], [move(1, (34, 35))], flags=flags)
        self.assertEqual(r.memory.holds, ((h(31), 1, 10),))
        self.assertEqual(r.checks[0][2].overlaps, (OBJ,))

    def test_new_game_starts_from_empty_memory(self) -> None:
        self.assertEqual(tg.GarrisonMemory(), tg.GarrisonMemory((), ()))


class IdentityTest(unittest.TestCase):
    def test_not_executable_and_not_a_policy(self) -> None:
        self.assertFalse(tg.EXECUTABLE)
        self.assertEqual(tg.STATUS, "ANALYSIS SHADOW - NON-EXECUTABLE")
        self.assertNotIn(tg.SHADOW_ID, policy.POLICIES)
        self.assertFalse(any(isinstance(v, type) and hasattr(v, "setup") for v in vars(tg).values()))

    def test_only_this_sprints_files_name_the_shadow(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        users = sorted(p.relative_to(root).as_posix() for folder in ("src", "scripts", "tests")
                       for p in (root / folder).rglob("*.py") if "t13_garrison_shadow" in p.read_text(encoding="utf-8")
                       and p.name != "t13_garrison_shadow.py")
        self.assertEqual(users, ["scripts/mutate_s25.py", "scripts/s25_t13_d1.py",
                                 "src/miaosuan_agent/evaluation/s25_t13.py", "tests/test_s25_t13.py",
                                 "tests/test_t13_garrison_shadow.py"])

    def test_frozen_parameters(self) -> None:
        self.assertEqual((tg.ZONE_RADIUS, tg.THREAT_MARGIN, tg.HOLD_LIMIT, tg.COOLDOWN), (1, 1, 300, 300))
        self.assertEqual(tg.RELEASE_REASONS, ("objective_not_held", "defender_absent", "defender_outside_zone",
                                              "backup_entered", "threat_cleared", "hold_limit"))


if __name__ == "__main__":
    unittest.main()
