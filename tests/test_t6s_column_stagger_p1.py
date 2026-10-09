"""Sprint 27 candidate ``t6s-column-stagger-p1`` (``experiments/t6s_column_stagger_p1.py``) on synthetic states.

The test classes from ``ExposureTest`` to ``EpisodeLimitTest`` are Sprint 26's synthetic rule tests, ported
mechanically onto the copy (only this docstring and the import line differ from Sprint 26's frozen test file; Sprint 26's
identity tests are replaced by the Sprint 27 ones below). Hexes on one even row are ``1000 + column`` (distance = column
difference); ``setUpModule`` asserts every distance and published range the tests rely on with the project's own
functions. Movers start on column 20 and their routes run along the row (first route hex column 21). Hex times come from
a test travel relation (``tau`` per unit) unless a test uses the frozen relation over a fake cost graph.

The Sprint 27 tests below cover: the copy against Sprint 26's frozen text (located through Sprint 26's protocol pins),
the memory encoding, the reading of the seat observation against Sprint 18's frames, the add-on (actions, change
records, skip counts, memory, failure on malformed memory or missing costs, non-play decisions), the executable policy
with the real ``baseline-v2`` in the head-to-head stand-in world, the identity, the source digest and the imports.
"""

from __future__ import annotations

import types
import unittest

from miaosuan_agent.decision import policy
from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation.t7_candidates import weapon_range
from miaosuan_agent.evaluation.t7_visibility import hex_distance
from miaosuan_agent.experiments import t6s_column_stagger_p1 as ts

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


# ------------------------------------------------------------------------------------------------
# Sprint 27: the executable candidate

import ast  # noqa: E402
import copy  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent  # noqa: E402
from tests.fixtures import s27_engine as se  # noqa: E402
from tests.fixtures import synthetic as syn  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def frozen_rule_text() -> str:
    """Sprint 26's frozen rule, located through Sprint 26's protocol pins and checked against its pinned digest."""
    import hashlib
    proto = json.loads((ROOT / "evaluation" / "s26-t6s-shadow" / "protocol.json").read_text(encoding="utf-8"))
    paths = [p for p in proto["sources"] if p.startswith("src/miaosuan_agent/experiments/") and p.endswith("_shadow.py")]
    assert len(paths) == 1, paths
    data = (ROOT / paths[0]).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == proto["sources"][paths[0]]
    return data.decode("utf-8")


def candidate_text() -> str:
    return (ROOT / "src" / "miaosuan_agent" / "experiments" / "t6s_column_stagger_p1.py").read_text(encoding="utf-8")


def analysis_script():
    spec = importlib.util.spec_from_file_location("s27_analysis_test", ROOT / "scripts" / "s27_analysis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CopyTest(unittest.TestCase):
    def test_the_marked_block_is_sprint26s_frozen_rule_verbatim(self) -> None:
        frozen = frozen_rule_text().split("\n")
        mine = candidate_text().replace("\r\n", "\n").split("\n")
        self.assertEqual((mine.count(ts.COPY_BEGIN), mine.count(ts.COPY_END)), (1, 1))
        block = mine[mine.index(ts.COPY_BEGIN) + 1:mine.index(ts.COPY_END)]
        original = frozen[frozen.index("MOVE = 1"):]
        while original and original[-1] == "":
            original.pop()
        self.assertEqual(block, original)
        self.assertGreater(len(block), 250)
        self.assertEqual(analysis_script().copied_block_problems(candidate_text(), frozen_rule_text()), [])

    def test_the_text_check_catches_a_changed_copy(self) -> None:
        planted = candidate_text().replace("STALL_SLACK = 10", "STALL_SLACK = 11", 1)
        self.assertNotEqual(planted, candidate_text())
        self.assertEqual(analysis_script().copied_block_problems(planted, frozen_rule_text()),
                         ["the candidate's copy differs from Sprint 26's frozen rule"])
        twice = candidate_text().replace(ts.COPY_END, ts.COPY_END + "\n" + ts.COPY_BEGIN + "\n" + ts.COPY_END, 1)
        self.assertEqual(analysis_script().copied_block_problems(twice, frozen_rule_text()),
                         ["the candidate does not carry exactly one marked copy"])

    def test_frozen_parameters_and_labels(self) -> None:
        self.assertEqual((ts.ROUTE_PREFIX, ts.MIN_GROUP, ts.STALL_FACTOR, ts.STALL_SLACK), (5, 2, 2, 10))
        self.assertEqual(ts.MOVER_REASONS, ("eligible", "unit_absent", "not_ground", "unreadable_unit_hex",
                                            "several_moves", "already_moving", "transport_committed",
                                            "move_not_listed", "unreadable_route", "unreadable_travel",
                                            "in_active_episode", "not_rearmed"))
        self.assertEqual(ts.RELEASE_REASONS, ("reference_left", "reference_absent", "timeout"))
        self.assertEqual(ts.QUEUE_REASONS, ("follower_absent", "follower_left"))
        self.assertIs(ts.weapon_range, weapon_range)
        self.assertIs(ts.hex_distance, hex_distance)


class MemoryTest(unittest.TestCase):
    def memories(self):
        ep = ts.Episode(3, h(20), h(21), 10, (5, 6, 7), (20, 20, 30), (6, 7), 5, 10, 20)
        ep2 = ts.Episode(4, h(30), h(31), 12, (8, 9), (144, 144), (9,), 8, 12, 144)
        return [ts.StaggerMemory(), ts.StaggerMemory((), ((1, h(20)),), 1),
                ts.StaggerMemory((ep,), ((1, h(20)), (2, h(25))), 4), ts.StaggerMemory((ep, ep2), (), 5)]

    def test_round_trip(self) -> None:
        for m in self.memories():
            pairs = ts.encode(m)
            self.assertEqual([p[0] for p in pairs], list(range(len(pairs))))
            self.assertEqual(ts.decode(pairs), m)
        self.assertEqual(ts.decode(()), ts.StaggerMemory())

    def test_round_trip_over_a_rule_run(self) -> None:
        own = [unit(1), unit(2), unit(3)]
        m = ts.StaggerMemory()
        for step, own_now in ((0, own), (20, [dict(own[0], cur_hex=h(21))] + own[1:]), (40, own[1:])):
            r = decide(step, own_now, [NEAR], [move(u["obj_id"]) for u in own_now], m)
            self.assertEqual(ts.decode(ts.encode(r.memory)), r.memory)
            m = r.memory

    def test_malformed_memory_is_refused(self) -> None:
        good = list(ts.encode(self.memories()[2]))
        cases = {
            "positions": [(i + 1, v) for i, v in good],
            "a boolean": [good[0], (1, True)] + good[2:],
            "a string": [good[0], (1, "1")] + good[2:],
            "trailing": good + [(len(good), 0)],
            "early end": good[:-1],
            "a pair of three": [good[0] + (0,)] + good[1:],
        }
        for name, pairs in cases.items():
            with self.assertRaises((ValueError, TypeError), msg=name):
                ts.decode(pairs)
        short = ts.encode(ts.StaggerMemory((ts.Episode(0, 1, 2, 3, (5, 6), (1, 1), (6,), 5, 3, 1),), (), 1))
        self.assertEqual(ts.decode(short).episodes[0].chain, (5, 6))
        with self.assertRaises(ValueError):
            ts.decode(((0, 0), (1, 0), (2, 0)))  # the empty memory in a non-canonical form
        one = ts.encode(ts.StaggerMemory((ts.Episode(0, 1, 2, 3, (5,), (1,), (), 5, 3, 1),), (), 1))
        with self.assertRaises(ValueError):
            ts.decode(one)
        stray = ts.encode(ts.StaggerMemory((ts.Episode(0, 1, 2, 3, (5, 6), (1, 1), (7,), 5, 3, 1),), (), 1))
        with self.assertRaises(ValueError):
            ts.decode(stray)
        with self.assertRaises(ValueError):
            ts.encode(ts.StaggerMemory((), (("a", 1),), 0))


class InputsTest(unittest.TestCase):
    def raw(self):
        units = [dict(unit(1), color=RED, basic_speed=36, move_state=0, extra="dropped"),
                 dict(unit(2), color=RED, move_path=[h(21), h(22)], speed=0.05),
                 enemy(38), dict(enemy(30, obj=901), obj_id="901"), "not a unit", dict(unit(3), obj_id=None)]
        return {"time": {"cur_step": 7, "stage": 2}, "operators": units,
                "valid_actions": {"1": {"1": None, "2": [{"target_obj_id": 900}]}, 2: {1: None}, "x": {1: None},
                                  "3": "not a mapping"}}

    def test_the_seat_view_matches_sprint18_frames(self) -> None:
        raw = self.raw()
        cur, stage, own, enemies, valid = ts.seat_inputs(raw, RED)
        frame = sc.frame_from_raw(0, raw, RED)
        self.assertEqual((cur, stage), (7, 2))
        self.assertEqual((own, enemies, valid), (frame.own, frame.enemies, frame.valid))
        self.assertEqual(sorted(own, key=str), [1, 2])
        self.assertEqual(sorted(enemies, key=str), [900, "901"])
        self.assertNotIn("extra", own[1])
        self.assertEqual(own[2]["move_path"], (h(21), h(22)))
        self.assertEqual(valid, {1: {1: None, 2: [{"target_obj_id": 900}]}, 2: {1: None}})
        self.assertEqual(ts.UNIT_FIELDS, sc.UNIT_FIELDS)


def observation(raw):
    return Observation.from_raw(raw, Origin.ENGINE)


class AddonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addon = ts.StaggerAddon(MoveCosts.from_raw(syn.cost_data(), Origin.ENGINE, "setup_info.cost_data"), None)
        # the seat view keeps observation fields only (no test ``tau``): every hex takes 20 steps, as ``unit``'s default
        self.addon.travel = lambda u, route: ((20,) * len(route), float(len(route)))

    def raw(self, step, own, enemies, stage=2):
        units = [dict(u, color=RED) for u in own] + list(enemies)
        return {"time": {"cur_step": step, "stage": stage}, "operators": units,
                "valid_actions": {u["obj_id"]: {1: [], 2: []} for u in own}}

    def apply(self, raw, actions, memory=()):
        base = types.SimpleNamespace(actions=tuple(actions))
        return self.addon.apply(types.SimpleNamespace(fields=raw), 1, RED, base, memory)

    def test_actions_changes_skips_and_memory_follow_the_rule(self) -> None:
        own = [unit(1), unit(2), unit(3, 30)]
        actions = [move(1), move(2), shoot(3), move(3, 31)]
        result = self.apply(self.raw(0, own, [NEAR]), actions)
        expected = decide(0, own, [NEAR], actions)
        self.assertEqual([dict(a) for a in result.actions], [dict(a) for a in expected.actions])
        self.assertEqual(result.addon_memory, ts.encode(expected.memory))
        self.assertEqual([c["kind"] for c in result.changes], ["start", "withhold"])
        self.assertEqual(result.changes[0]["chain"], [1, 2])
        self.assertEqual(result.changes[1], {"kind": "withhold", "eid": 0, "obj_id": 2, "step": 0, "index": 1})
        self.assertEqual(dict(result.skipped), {"group single_mover": 1, "group triggered": 1, "mover eligible": 3})
        later = self.apply(self.raw(20, [dict(own[0], cur_hex=h(21))] + own[1:], [NEAR]), [move(2)],
                           result.addon_memory)
        self.assertEqual([dict(a) for a in later.actions], [move(2)])
        self.assertEqual([c["kind"] for c in later.changes], ["release", "complete"])
        self.assertEqual(later.changes[0]["reason"], "reference_left")
        self.assertIs(later.changes[0]["moved"], True)

    def test_non_play_decision_and_failures(self) -> None:
        own = [unit(1), unit(2)]
        result = self.apply(self.raw(0, own, [NEAR], stage=1), [move(1), move(2)])
        self.assertEqual(([dict(a) for a in result.actions], result.changes, result.addon_memory),
                         ([move(1), move(2)], (), ()))
        with self.assertRaises(ValueError):
            self.apply(self.raw(0, own, [NEAR]), [move(1), move(2)], ((1, 0),))
        bare = ts.StaggerAddon(None, None)
        with self.assertRaises(RuntimeError):
            bare.apply(types.SimpleNamespace(fields=self.raw(0, own, [NEAR])), 1, RED,
                       types.SimpleNamespace(actions=(move(1),)), ())

    def test_inputs_are_not_modified(self) -> None:
        own = [unit(1), unit(2)]
        raw = self.raw(0, own, [NEAR])
        actions = [move(1), move(2)]
        before = (copy.deepcopy(raw), copy.deepcopy(actions))
        self.apply(raw, actions)
        self.assertEqual((raw, actions), before)


def standin_play_view():
    env = se.StaggerEnv()
    env.setup({"player_info": [{"seat": 1}, {"seat": 11}]})
    state, _ = env.step([{"actor": 1, "type": 333}, {"actor": 11, "type": 333}])
    return state[se.BLUE]


class PolicyTest(unittest.TestCase):
    """The executable policy with the real baseline-v2 in the stand-in world: baseline-v2 sends the three co-located
    tanks along one route under a visible enemy gun; the candidate lets the leader go and withholds the others."""

    def test_the_first_play_decision_withholds_the_followers(self) -> None:
        raw = standin_play_view()
        v2 = ShootReservationAgent()
        v2.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        agent = ts.StaggerAgent()
        agent.setup({"seat": 11, "faction": se.BLUE, "cost_data": syn.cost_data()})
        base = [dict(a) for a in v2.step(copy.deepcopy(raw))]
        mine = [dict(a) for a in agent.step(copy.deepcopy(raw))]
        moves = [a for a in base if a["type"] == 1]
        self.assertEqual(sorted(a["obj_id"] for a in moves), [se.T1, se.T2, se.T3])
        self.assertEqual(len({tuple(a["move_path"]) for a in moves}), 1)
        self.assertEqual(mine, [a for a in base if not (a["type"] == 1 and a["obj_id"] in (se.T2, se.T3))])
        self.assertEqual(agent.last_trace.addon_error, None)
        self.assertIsInstance(agent.memory, AddonMemory)
        self.assertEqual(ts.decode(agent.memory.addon).episodes[0].chain, (se.T1, se.T2, se.T3))
        agent.reset()
        self.assertEqual(agent.memory, AddonMemory())


class IdentityTest(unittest.TestCase):
    def test_identity_and_status(self) -> None:
        self.assertEqual((ts.CANDIDATE_ID, ts.ADDON_NAME), ("t6s-column-stagger-p1", "t6s_column_stagger_p1"))
        self.assertEqual(ts.StaggerPolicy.identity, ts.CANDIDATE_ID)
        self.assertNotIn(ts.CANDIDATE_ID, policy.POLICIES)
        self.assertIn("NOT ELIGIBLE FOR PROMOTION", ts.STATUS)

    def test_policy_source_digest_is_the_registered_one(self) -> None:
        from miaosuan_agent.evaluation import s27_probe as sp
        spec = importlib.util.spec_from_file_location("bs27_identity", ROOT / "scripts" / "build_s27_card.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = module.policy_source(module.CANDIDATE_SOURCES)
        self.assertEqual(source["sha256"], sp.CANDIDATE_DIGEST)
        for name in ("experiments/t6s_column_stagger_p1.py", "experiments/exploratory_addon.py",
                     "experiments/t9_batch.py", "evaluation/t7_candidates.py", "evaluation/t7_audit.py",
                     "evaluation/t7_visibility.py", "experiments/shoot_reservation.py"):
            self.assertIn(name, source["files"])

    def test_imports_are_the_rule_helpers_and_the_wrapper_only(self) -> None:
        tree = ast.parse(candidate_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                found.add(("." * node.level) + (node.module or ""))
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
        self.assertEqual(found, {"__future__", "collections", "dataclasses", "typing", "..decision.routing",
                                 "..evaluation.t7_candidates", "..evaluation.t7_visibility", ".exploratory_addon",
                                 ".t9_batch"})
