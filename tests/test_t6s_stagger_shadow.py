"""Sprint 26 T6-S stagger shadow (``experiments/t6s_stagger_shadow.py``) on synthetic states (no private data needed).

Hexes on one even row are ``1000 + column`` (distance = column difference); ``setUpModule`` asserts every distance and
published range the tests rely on with the project's own functions. Movers start on column 20 and their routes run
along the row (first route hex column 21). Hex times come from a test travel relation (``tau`` per unit) unless a test
uses the frozen relation over a fake cost graph.
"""

from __future__ import annotations

import types
import unittest

from miaosuan_agent.decision import policy
from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation.t7_candidates import weapon_range
from miaosuan_agent.evaluation.t7_visibility import hex_distance
from miaosuan_agent.experiments import t6s_stagger_shadow as ts

RED, BLUE = 0, 1
INF, VEH, AIR = 1, 2, 3
BIG_GUN = 36        # 10 against personnel, 18 against vehicles
RAPID_GROUND = 4    # 10 against personnel, not published against vehicles
INDIRECT = 72       # not in the direct-fire table
ORIGIN = 1020


def h(col: int) -> int:
    return 1000 + col


def setUpModule() -> None:
    for a, b in ((20, 38), (20, 39), (21, 39), (25, 43), (26, 44), (25, 44), (20, 2), (20, 1), (21, 1), (20, 30),
                 (20, 31), (21, 31)):
        assert hex_distance(h(a), h(b)) == abs(a - b), (a, b)
    assert (weapon_range([BIG_GUN], VEH), weapon_range([BIG_GUN], INF)) == (18, 10)
    assert (weapon_range([RAPID_GROUND], VEH), weapon_range([RAPID_GROUND], INF)) == (None, 10)
    assert weapon_range([INDIRECT], VEH) is None


def unit(obj, col=20, *, type_=VEH, sub=1, color=RED, weapons=(BIG_GUN,), path=(), tau=20, speed=0, stack=1):
    return {"obj_id": obj, "type": type_, "sub_type": sub, "color": color, "cur_hex": h(col), "move_path": list(path),
            "carry_weapon_ids": list(weapons), "tau": tau, "speed": speed, "stack": stack}


def enemy(col, obj=900, **kw):
    return unit(obj, col, color=BLUE, **kw)


def move(obj, start=21, length=10, cols=None):
    cols = cols if cols is not None else range(start, start + length)
    return {"actor": 1, "obj_id": obj, "type": 1, "move_path": [h(c) for c in cols]}


def shoot(obj):
    return {"actor": 1, "obj_id": obj, "type": 2, "target_obj_id": 900, "weapon_id": BIG_GUN}


def travel(u, route):
    if u.get("tau") is None:
        return None
    times = tuple(u.get("times") or (u["tau"],) * len(route))
    return times, float(u.get("cost", len(route)))


NEAR = enemy(38)            # covers the start hex at the vehicle range exactly


def decide(step, own, enemies, actions, memory=ts.StaggerMemory(), valid=None, stage=2):
    own_map = {u["obj_id"]: u for u in own}
    if valid is None:
        valid = {u["obj_id"]: {1: [], 2: []} for u in own}
    return ts.decide(step, stage, own_map, enemies, valid, actions, memory, travel)


def kinds(result):
    return [(e.kind, e.unit, e.reason) for e in result.events]


class ExposureTest(unittest.TestCase):
    def frame(self, mover, enemies):
        return sc.Frame(k=0, cur_step=0, max_step=100, stage=2, faction=RED, own={mover["obj_id"]: mover}, aboard={},
                        enemies={e["obj_id"]: e for e in enemies}, valid={}, flags={})

    def test_restatement_equals_sprint18_predicate(self) -> None:
        cases = [[], [NEAR], [enemy(39)], [enemy(43)], [enemy(44)], [enemy(2)], [enemy(1)],
                 [enemy(30, weapons=(RAPID_GROUND,))], [enemy(30, weapons=(INDIRECT,))],
                 [enemy(30, type_=AIR)], [enemy(44), enemy(43, obj=901)]]
        for mover in (unit(1), unit(1, type_=INF), unit(1, type_=AIR)):
            for enemies in cases:
                a = move(1)
                self.assertEqual(ts.threat_exposed(mover, a["move_path"], enemies),
                                 sc.threat_exposed(self.frame(mover, enemies), a), (mover["type"], enemies))
        self.assertIsNone(ts.threat_exposed(None, [h(21)], [NEAR]))

    def test_boundaries(self) -> None:
        route = move(1)["move_path"]
        self.assertTrue(ts.threat_exposed(unit(1), route, [enemy(38)]))      # start hex at distance 18
        self.assertTrue(ts.threat_exposed(unit(1), route, [enemy(43)]))      # fifth route hex at 18
        self.assertFalse(ts.threat_exposed(unit(1), route, [enemy(44)]))     # only the sixth route hex at 18
        self.assertTrue(ts.threat_exposed(unit(1), route, [enemy(2)]))       # start hex at 18 on the other side
        self.assertFalse(ts.threat_exposed(unit(1), route, [enemy(1)]))      # 19
        self.assertTrue(ts.threat_exposed(unit(1, type_=INF), route, [enemy(30, weapons=(RAPID_GROUND,))]))
        self.assertFalse(ts.threat_exposed(unit(1), route, [enemy(30, weapons=(RAPID_GROUND,))]))
        self.assertFalse(ts.threat_exposed(unit(1), route, [enemy(30, weapons=(INDIRECT,))]))
        self.assertTrue(ts.threat_exposed(unit(1), route, [enemy(30, type_=AIR)]))  # any class with a published range


class TriggerTest(unittest.TestCase):
    def test_two_co_located_movers_sharing_the_first_hex(self) -> None:
        actions = [move(1), move(2)]
        r = decide(0, [unit(1), unit(2)], [NEAR], actions)
        self.assertEqual([dict(a) for a in r.actions], [actions[0]])
        self.assertEqual(r.withheld, (1,))
        self.assertEqual([g[3] for g in r.groups], ["triggered"])
        ep = r.memory.episodes[0]
        self.assertEqual((ep.origin, ep.first_hex, ep.chain, ep.pending, ep.ref, ep.ref_step), (ORIGIN, h(21), (1, 2), (2,), 1, 0))
        self.assertEqual(kinds(r), [("start", 1, None), ("withhold", 2, None)])

    def test_same_hex_different_first_hex(self) -> None:
        r = decide(0, [unit(1), unit(2)], [NEAR], [move(1), move(2, cols=range(19, 10, -1))])
        self.assertEqual(r.withheld, ())
        self.assertEqual(sorted(g[3] for g in r.groups), ["single_mover", "single_mover"])

    def test_different_hex_same_next_hex(self) -> None:
        r = decide(0, [unit(1), unit(2, 22)], [NEAR], [move(1), move(2, cols=(21, 20, 19))])
        self.assertEqual(r.withheld, ())

    def test_no_baseline_move(self) -> None:
        r = decide(0, [unit(1), unit(2)], [NEAR], [shoot(1), shoot(2)])
        self.assertEqual((r.withheld, r.groups, r.checks), ((), (), ()))

    def test_one_move_only(self) -> None:
        r = decide(0, [unit(1), unit(2)], [NEAR], [move(1), shoot(2)])
        self.assertEqual([g[3] for g in r.groups], ["single_mover"])

    def test_no_visible_threat(self) -> None:
        for enemies in ([], [enemy(44)], [enemy(30, weapons=(INDIRECT,))]):
            r = decide(0, [unit(1), unit(2)], enemies, [move(1), move(2)])
            self.assertEqual([g[3] for g in r.groups], ["no_qualifying_threat"], enemies)
            self.assertEqual(r.withheld, ())

    def test_threat_at_the_envelope_boundary_and_the_sixth_hex(self) -> None:
        self.assertEqual(decide(0, [unit(1), unit(2)], [enemy(43)], [move(1), move(2)]).withheld, (1,))
        self.assertEqual(decide(0, [unit(1), unit(2)], [enemy(44)], [move(1), move(2)]).withheld, ())

    def test_one_exposed_member_is_enough(self) -> None:
        # the infantry is exposed to a personnel-only weapon, the vehicle is not
        r = decide(0, [unit(1), unit(2, type_=INF, tau=144)], [enemy(30, weapons=(RAPID_GROUND,))], [move(1), move(2)])
        self.assertEqual(r.withheld, (1,))
        self.assertEqual(r.memory.episodes[0].chain, (1, 2))

    def test_multiple_threats(self) -> None:
        r = decide(0, [unit(1), unit(2)], [enemy(44), enemy(38, obj=901), enemy(1, obj=902)], [move(1), move(2)])
        self.assertEqual(r.withheld, (1,))

    def test_mover_checks(self) -> None:
        cases = {
            "unit_absent": ([unit(2)], [move(1), move(2)], None),
            "not_ground": ([unit(1, type_=AIR), unit(2)], [move(1), move(2)], None),
            "unreadable_unit_hex": ([dict(unit(1), cur_hex=None), unit(2)], [move(1), move(2)], None),
            "several_moves": ([unit(1), unit(2)], [move(1), move(1, length=3), move(2)], None),
            "already_moving": ([unit(1, path=(h(21),)), unit(2)], [move(1), move(2)], None),
            "transport_committed": ([unit(1), unit(2)], [move(1), {"obj_id": 1, "type": 3}, move(2)], None),
            "move_not_listed": ([unit(1), unit(2)], [move(1), move(2)], {1: {2: []}, 2: {1: []}}),
            "unreadable_route": ([unit(1), unit(2)], [dict(move(1), move_path=[h(21), "x"]), move(2)], None),
            "unreadable_travel": ([unit(1, tau=None), unit(2)], [move(1), move(2)], None),
        }
        for reason, (own, actions, valid) in cases.items():
            r = decide(0, own, [NEAR], actions, valid=valid)
            got = {u: c.reason for _, u, c in r.checks}
            self.assertEqual(got.get(1), reason, reason)
            self.assertEqual(r.withheld, (), reason)
        r = decide(0, [unit(1, speed=0.05), unit(2)], [NEAR], [move(1), move(2)])
        self.assertEqual({u: c.reason for _, u, c in r.checks}[1], "already_moving")

    def test_non_play_decision_unchanged(self) -> None:
        actions = [move(1), move(2)]
        r = decide(0, [unit(1), unit(2)], [NEAR], actions, stage=1)
        self.assertEqual(([dict(a) for a in r.actions], r.withheld, r.memory), (actions, (), ts.StaggerMemory()))

    def test_independent_groups(self) -> None:
        own = [unit(1), unit(2), unit(3, 30), unit(4, 30)]
        actions = [move(3, 31), move(1), move(4, 31), move(2)]
        r = decide(0, own, [NEAR], actions)
        self.assertEqual(r.withheld, (2, 3))
        self.assertEqual([(e.origin, e.chain) for e in r.memory.episodes], [(h(20), (1, 2)), (h(30), (3, 4))])
        self.assertEqual([e.eid for e in r.memory.episodes], [0, 1])

    def test_no_action_other_than_follower_moves_changes(self) -> None:
        actions = [shoot(2), move(1), {"obj_id": 7, "type": 5}, move(2), shoot(1)]
        r = decide(0, [unit(1), unit(2)], [NEAR], actions)
        self.assertEqual([dict(a) for a in r.actions], [actions[0], actions[1], actions[2], actions[4]])
        for a in r.actions:
            self.assertIn(dict(a), actions)


class LeaderTest(unittest.TestCase):
    def test_earliest_free_flow_arrival_leads_not_the_fastest_first_hex(self) -> None:
        slow_first = dict(unit(1), times=(30, 10, 10))
        fast_first = dict(unit(2), times=(10, 40, 40))
        r = decide(0, [slow_first, fast_first], [NEAR], [move(1, length=3), move(2, length=3)])
        self.assertEqual(r.memory.episodes[0].chain, (1, 2))
        self.assertEqual(r.memory.episodes[0].hex_times, (30, 10))

    def test_different_speeds(self) -> None:
        r = decide(0, [unit(1, type_=INF, tau=144), unit(2, tau=20)], [NEAR], [move(1), move(2)])
        self.assertEqual(r.memory.episodes[0].chain, (2, 1))
        self.assertEqual(r.withheld, (0,))

    def test_ties(self) -> None:
        r = decide(0, [unit(5), unit(2)], [NEAR], [move(5), move(2)])
        self.assertEqual(r.memory.episodes[0].chain, (2, 5))            # equal arrival, cost and length: unit id
        cheaper = dict(unit(5), cost=1.0)
        r = decide(0, [cheaper, unit(2)], [NEAR], [move(5), move(2)])
        self.assertEqual(r.memory.episodes[0].chain, (5, 2))            # equal arrival: lower route cost
        r = decide(0, [dict(unit(5), times=(20, 20)), dict(unit(2), times=(10, 10, 10, 10))], [NEAR],
                   [move(5, length=2), move(2, length=4)])
        self.assertEqual(r.memory.episodes[0].chain, (5, 2))            # equal arrival 40: cost by length
        r = decide(0, [dict(unit(5), times=(20, 20), cost=4.0), dict(unit(2), times=(10, 10, 10, 10), cost=4.0)], [NEAR],
                   [move(5, length=2), move(2, length=4)])
        self.assertEqual(r.memory.episodes[0].chain, (5, 2))            # equal arrival and cost: shorter route

    def test_router_travel_uses_the_frozen_free_flow_relation(self) -> None:
        class Costs:
            @staticmethod
            def neighbours(mode, hex_):
                return {hex_ + 1: 1.0, hex_ - 1: 2.0}

        fn = ts.router_travel(types.SimpleNamespace(costs=Costs))
        car = {"type": VEH, "move_state": 0, "basic_speed": 36, "cur_hex": h(20)}
        self.assertEqual(fn(car, [h(21), h(22)]), ((20, 20), 2.0))
        self.assertEqual(fn(car, [h(19)]), ((40,), 2.0))
        foot = {"type": INF, "move_state": 0, "basic_speed": 5, "cur_hex": h(20)}
        self.assertEqual(fn(foot, [h(21)]), ((144,), 1.0))
        self.assertIsNone(fn(car, [h(23)]))
        self.assertIsNone(fn(dict(car, basic_speed=None), [h(21)]))


class ReleaseTest(unittest.TestCase):
    def start(self, own, actions=None):
        actions = actions or [move(u["obj_id"]) for u in own]
        return decide(0, own, [NEAR], actions)

    def test_exact_release_boundary(self) -> None:
        m = self.start([unit(1), unit(2)]).memory
        r = decide(19, [unit(1, path=(h(21),), speed=0.05), unit(2)], [NEAR], [move(2)], m)
        self.assertEqual(r.withheld, (0,))                               # leader still on the start hex
        r = decide(20, [unit(1, 21, path=(h(22),), speed=0.05), unit(2)], [NEAR], [move(2)], r.memory)
        self.assertEqual(r.withheld, ())                                 # leader observed on the first hex
        self.assertIn(("release", 2, "reference_left"), kinds(r))
        self.assertIn(("complete", 1, None), kinds(r))
        self.assertEqual(r.memory.episodes, ())

    def test_three_followers_released_one_hex_time_apart(self) -> None:
        own = [unit(1, tau=20), unit(2, tau=20), unit(3, tau=20), unit(4, tau=20)]
        m = self.start(own).memory
        self.assertEqual(m.episodes[0].pending, (2, 3, 4))
        moving = lambda u, col: dict(u, cur_hex=h(col), move_path=[h(col + 1)], speed=0.05)
        r = decide(20, [moving(own[0], 21)] + own[1:], [NEAR], [move(2), move(3), move(4)], m)
        self.assertEqual(r.withheld, (1, 2))                             # 2 released, 3 and 4 still wait
        self.assertEqual(r.memory.episodes[0].ref, 2)
        r = decide(21, [moving(own[0], 21), dict(own[1], move_path=[h(21)], speed=0.05), own[2], own[3]], [NEAR],
                   [move(3), move(4)], r.memory)
        self.assertEqual(r.withheld, (0, 1))                             # 2 has not left yet
        r = decide(40, [moving(own[0], 22), moving(own[1], 21), own[2], own[3]], [NEAR], [move(3), move(4)], r.memory)
        self.assertEqual(r.withheld, (1,))                               # 3 released, 4 waits
        r = decide(60, [moving(own[0], 23), moving(own[1], 22), moving(own[2], 21), own[3]], [NEAR], [move(4)], r.memory)
        self.assertEqual(r.withheld, ())
        self.assertEqual(r.memory.episodes, ())

    def test_follower_without_a_baseline_move_at_release_is_not_manufactured(self) -> None:
        own = [unit(1), unit(2), unit(3)]
        m = self.start(own).memory
        r = decide(20, [dict(own[0], cur_hex=h(21)), own[1], own[2]], [NEAR], [move(3), shoot(2)], m)
        self.assertEqual([dict(a) for a in r.actions], [move(3), shoot(2)])  # nothing added; 3 released at once
        rel = [(e.unit, e.reason, e.moved) for e in r.events if e.kind == "release"]
        self.assertEqual(rel, [(2, "reference_left", False), (3, "reference_left", True)])
        self.assertEqual(r.memory.episodes, ())

    def test_disappearing_leader_releases_the_next_follower(self) -> None:
        own = [unit(1), unit(2), unit(3)]
        m = self.start(own).memory
        r = decide(5, [own[1], own[2]], [NEAR], [move(2), move(3)], m)
        self.assertEqual(r.withheld, (1,))
        self.assertEqual([(e.unit, e.reason) for e in r.events if e.kind == "release"], [(2, "reference_absent")])
        self.assertEqual(r.memory.episodes[0].ref, 2)

    def test_blocked_leader_exact_timeout(self) -> None:
        own = [unit(1, tau=20), unit(2), unit(3)]
        m = self.start(own).memory
        waiting = [dict(own[0], move_path=[h(21)], speed=0)] + own[1:]
        r = decide(50, waiting, [NEAR], [move(2), move(3)], m)           # age 50 = 2 * 20 + 10: still waiting
        self.assertEqual(r.withheld, (0, 1))
        r = decide(51, waiting, [NEAR], [move(2), move(3)], r.memory)    # age 51 > 50: every pending member released
        self.assertEqual(r.withheld, ())
        self.assertEqual([(e.unit, e.reason, e.moved) for e in r.events if e.kind == "release"],
                         [(2, "timeout", True), (3, "timeout", True)])
        self.assertEqual(r.memory.episodes, ())

    def test_timeout_measured_from_the_reference_release(self) -> None:
        own = [unit(1, tau=20), unit(2, tau=100), unit(3, tau=300)]
        m = self.start(own).memory
        r = decide(20, [dict(own[0], cur_hex=h(21))] + own[1:], [NEAR], [move(2), move(3)], m)
        self.assertEqual(r.memory.episodes[0].ref, 2)
        stuck = [dict(own[0], cur_hex=h(22)), dict(own[1], move_path=[h(21)])] + own[2:]
        r2 = decide(230, stuck, [NEAR], [move(3)], r.memory)             # 210 = 2 * 100 + 10
        self.assertEqual(r2.withheld, (0,))
        r3 = decide(231, stuck, [NEAR], [move(3)], r2.memory)
        self.assertEqual(r3.withheld, ())

    def test_follower_absent_or_left_leaves_the_queue(self) -> None:
        own = [unit(1), unit(2), unit(3)]
        m = self.start(own).memory
        r = decide(3, [own[0], own[2]], [NEAR], [move(3)], m)
        self.assertEqual([(e.unit, e.reason) for e in r.events if e.kind == "queue"], [(2, "follower_absent")])
        self.assertEqual(r.withheld, (0,))
        r = decide(4, [own[0], dict(own[2], cur_hex=h(19))], [NEAR], [], r.memory)
        self.assertEqual([(e.unit, e.reason) for e in r.events if e.kind == "queue"], [(3, "follower_left")])
        self.assertEqual(r.memory.episodes, ())

    def test_follower_moves_withheld_while_pending_and_other_actions_pass(self) -> None:
        own = [unit(1), unit(2)]
        m = self.start(own).memory
        r = decide(3, own, [NEAR], [shoot(2), move(2, length=4)], m)
        self.assertEqual([dict(a) for a in r.actions], [shoot(2)])
        self.assertEqual([(e.kind, e.unit) for e in r.events], [("repeat", 2)])

    def test_unreadable_reference_hex_waits(self) -> None:
        own = [unit(1), unit(2)]
        m = self.start(own).memory
        r = decide(10, [dict(own[0], cur_hex=None), own[1]], [NEAR], [move(2)], m)
        self.assertEqual(r.withheld, (0,))


class EpisodeLimitTest(unittest.TestCase):
    def test_members_of_an_active_episode_cannot_join_another(self) -> None:
        own = [unit(1), unit(2), unit(3), unit(4)]
        m = decide(0, own[:3], [NEAR], [move(1), move(2), move(3)]).memory
        r = decide(1, own, [NEAR], [move(4), move(2)], m)
        self.assertEqual({u: c.reason for _, u, c in r.checks}, {4: "eligible"})
        self.assertEqual(r.withheld, (1,))                               # the pending follower's MOVE only
        r = decide(1, own[:3] + [unit(9)], [NEAR], [move(1), move(9)], m)
        self.assertEqual({u: c.reason for _, u, c in r.checks}, {1: "in_active_episode", 9: "eligible"})
        self.assertEqual(r.withheld, ())

    def test_one_episode_per_stay_on_a_hex(self) -> None:
        own = [unit(1), unit(2)]
        m = decide(0, own, [NEAR], [move(1), move(2)]).memory
        r = decide(51, own, [NEAR], [move(2)], m)                        # timeout: 2 released
        self.assertEqual(r.memory.spent, ((1, ORIGIN), (2, ORIGIN)))
        r = decide(52, own, [NEAR], [move(1), move(2)], r.memory)        # same unresolved co-departure listed again
        self.assertEqual({u: c.reason for _, u, c in r.checks}, {1: "not_rearmed", 2: "not_rearmed"})
        self.assertEqual(r.withheld, ())
        r = decide(60, [unit(1, 21), unit(2)], [NEAR], [], r.memory)    # unit 1 observed elsewhere: re-armed
        self.assertEqual(r.memory.spent, ((2, ORIGIN),))
        self.assertIn(("rearm", 1, None), kinds(r))

    def test_no_unbounded_hold(self) -> None:
        own = [unit(1, tau=20), unit(2)]
        m = decide(0, own, [NEAR], [move(1), move(2)]).memory
        withheld_steps = []
        for step in range(1, 400):
            r = decide(step, own, [NEAR], [move(1), move(2)], m)
            m = r.memory
            if r.withheld:
                withheld_steps.append(step)
        self.assertEqual(withheld_steps, list(range(1, 51)))


class IdentityTest(unittest.TestCase):
    def test_not_executable_and_not_a_policy(self) -> None:
        self.assertFalse(ts.EXECUTABLE)
        self.assertEqual(ts.STATUS, "ANALYSIS SHADOW - NON-EXECUTABLE")
        self.assertNotIn(ts.SHADOW_ID, policy.POLICIES)
        self.assertFalse(any(isinstance(v, type) and hasattr(v, "setup") for v in vars(ts).values()))

    def test_only_this_sprints_files_name_the_shadow(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        users = sorted(p.relative_to(root).as_posix() for folder in ("src", "scripts", "tests")
                       for p in (root / folder).rglob("*.py") if "t6s_stagger_shadow" in p.read_text(encoding="utf-8")
                       and p.name != "t6s_stagger_shadow.py")
        self.assertEqual(users, ["scripts/mutate_s26.py", "scripts/s26_t6s.py",
                                 "src/miaosuan_agent/evaluation/s26_t6s.py", "tests/test_s26_t6s.py",
                                 "tests/test_t6s_stagger_shadow.py"])

    def test_frozen_parameters(self) -> None:
        self.assertEqual((ts.ROUTE_PREFIX, ts.MIN_GROUP, ts.STALL_FACTOR, ts.STALL_SLACK), (5, 2, 2, 10))
        self.assertEqual(ts.RELEASE_REASONS, ("reference_left", "reference_absent", "timeout"))
        self.assertEqual(ts.QUEUE_REASONS, ("follower_absent", "follower_left"))

    def test_labels_carry_no_digit_word(self) -> None:
        for label in ts.MOVER_REASONS + ts.GROUP_REASONS + ts.RELEASE_REASONS + ts.QUEUE_REASONS + (ts.OPEN_AT_END,):
            self.assertFalse(any(w.isdigit() for w in label.split()), label)


if __name__ == "__main__":
    unittest.main()
