"""Sprint 16 analysis-side shadows (``evaluation/s16_shadow.py``, identity ``s16-delayed-shadow-v6``). SYNTHETIC
observations on the scenes of ``tests/test_t9_delayed.py`` (geometry computed with the project's router and asserted
as a precondition, never typed by hand).

What is pinned here: the one corrected memory transition (a unit standing on an objective its side holds keeps its
record; one standing on an objective its side does not hold still loses it), its equality with the post-hoc correction
of Sprint 15 (``scripts/s15_posthoc.py``), every other transition and trigger unchanged from the frozen v5, the identity
with v3 when nobody is eligible, at most one redirect per episode, and that nothing here can act in an engine.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent.boundary import Observation
from miaosuan_agent.evaluation import s16_mechanism as ms
from miaosuan_agent.evaluation import s16_shadow as sh
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments import t9_delayed as td
from miaosuan_agent.experiments import t9_redistribution as tr
from tests import test_t9_delayed as t15
from tests.test_t9_delayed import A, E, F, HOLDERS, X, holders
from tests.test_t9_redistribution import RED, SEAT, cost, observation, route, unit

ROOT = Path(__file__).resolve().parents[1]


def posthoc_module():
    spec = importlib.util.spec_from_file_location("s15_posthoc_for_s16", ROOT / "scripts" / "s15_posthoc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShadowTest(unittest.TestCase):
    # the Sprint 15 scene builders, borrowed without their tests
    setUp = t15.DelayedTest.setUp
    base = t15.DelayedTest.base
    withheld_scene = t15.DelayedTest.withheld_scene
    staged_scene_start = t15.DelayedTest.staged_scene_start
    staged_scene_arrived = t15.DelayedTest.staged_scene_arrived
    seven_objectives = t15.DelayedTest.seven_objectives

    def shadow(self, obs: Observation, rule, memory=(), actions=None, router=None) -> td.Allocation:
        policy, base = self.base(obs)
        rule_ = None if rule is None else sh.RULES[rule]
        return sh.allocate(obs, SEAT, RED, base if actions is None else actions, router or policy.router, rule_, memory)

    def shadow_sequence(self, rule: str, observations) -> List[td.Allocation]:
        memory, out = (), []
        for obs in observations:
            result = self.shadow(obs, rule, memory)
            out.append(result)
            memory = result.memory
        return out

    def g_alternative(self, start: int) -> int:
        """An objective farther than A from ``start`` but within the detour bound, off the holders' hex."""
        for hex_ in sorted(r * 100 + c for r in range(10) for c in range(10)):
            if hex_ in (A, E, F, start):
                continue
            if cost(start, A) < cost(start, hex_) <= tr.DETOUR * cost(start, A):
                return hex_
        self.fail("no alternative objective in the synthetic grid")

    # -- identity with v3 ----------------------------------------------------------------------------------------
    def test_nobody_eligible_and_fresh_memory_equal_v3(self) -> None:
        shapes = [self.withheld_scene(), self.staged_scene_start(), self.staged_scene_arrived(),
                  self.seven_objectives()]
        for obs in shapes:
            policy, base = self.base(obs)
            v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
            nobody = sh.allocate(obs, SEAT, RED, base, policy.router, None)
            self.assertEqual([dict(a) for a in nobody.actions], [dict(a) for a in v3.actions])
            self.assertEqual((nobody.selected, nobody.staged, nobody.withheld, nobody.redirected),
                             (v3.selected, v3.staged, v3.withheld, {}))
            for name in sh.RULES:  # an empty memory (the first decision of every game) never makes anyone eligible
                fresh = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES[name], ())
                self.assertEqual([dict(a) for a in fresh.actions], [dict(a) for a in v3.actions], name)
                self.assertEqual(fresh.eligible, (), name)

    # -- the corrected memory transition ----------------------------------------------------------------------------
    def test_a_held_objective_does_not_erase_the_deferred_history(self) -> None:
        self.assertLess(cost(E, A), tr.DETOUR * cost(E, A))
        on_held = observation(holders() + [unit(X, E)], cities=(A, E), movable=[X], held=(E,))
        first = self.shadow(self.withheld_scene(), "delayed-repeat-3")
        second = self.shadow(on_held, "delayed-repeat-3", first.memory)
        self.assertEqual(second.claimants[X].objective, A)
        self.assertEqual(second.ended, {})  # v5 ended the record here ("standing on an objective")
        self.assertEqual(td.decode(second.memory)[0][X][td.COUNT], 2)
        third = self.shadow(on_held, "delayed-repeat-3", second.memory)
        self.assertEqual(td.decode(third.memory)[0][X][td.COUNT], 3)
        self.assertTrue(third.eligible)  # the third observation of the episode: the trigger holds (no open alternative)
        frozen = td.allocate(on_held, SEAT, RED, self.base(on_held)[1], self.base(on_held)[0].router,
                             td.RULES["delayed-repeat-3"], first.memory)
        self.assertEqual(frozen.ended, {X: "standing on an objective"})  # the frozen v5 behaviour, unchanged

    def test_an_unheld_objective_still_ends_the_record(self) -> None:
        first = self.shadow(self.withheld_scene(), "delayed-repeat-2")
        standing = observation(holders() + [unit(X, E)], cities=(A, E), movable=[])
        after = self.shadow(standing, "delayed-repeat-2", first.memory)
        self.assertEqual(after.ended, {X: sh.STANDING_UNHELD})
        self.assertEqual(td.decode(after.memory)[0], {})

    def test_completed_staging_survives_standing_on_a_held_objective_and_post_stage_any_then_fires(self) -> None:
        g = self.g_alternative(F)
        record = [0] * len(td.FIELD_NAMES)
        record[td.SOURCE], record[td.COUNT], record[td.STAGED], record[td.DONE], record[td.STAGE_SOURCE] = A, 1, 405, 1, A
        record[td.FIRST] = 90
        memory = td.encode({X: record})
        scene = observation(holders() + [unit(X, F)], cities=(A, F, g), movable=[X], held=(F,))
        _, base = self.base(scene)
        self.assertEqual([tb.destination(a) for a in base if a.get("obj_id") == X], [A])  # precondition
        v6 = self.shadow(scene, "delayed-post-stage-any", memory)
        self.assertEqual(v6.redirected[X].objective, g)
        policy, _ = self.base(scene)
        v5 = td.allocate(scene, SEAT, RED, base, policy.router, td.RULES["delayed-post-stage-any"], memory)
        self.assertEqual(v5.redirected, {})  # v5 erased the completed-staging fact on the held objective
        self.assertEqual(v5.ended, {X: "standing on an objective"})

    def test_the_correction_equals_sprint15_posthoc(self) -> None:
        """The source of truth is the post-hoc correction of Sprint 15: identical records and ended keys on every
        scene; the reasons differ only in the corrected label."""
        posthoc = posthoc_module()
        g = self.g_alternative(F)
        records = {X: [A, 2, 405, 1, E, 0, 0, 90, A], HOLDERS[0]: [A, 1, 0, 0, 0, 0, 1, 80, 0],
                   905777: [F, 3, 0, 0, 0, 1, 0, 70, 0]}
        scenes = [observation(holders() + [unit(X, F), unit(905777, 304)], cities=(A, F, g), movable=[X], held=(F,)),
                  observation(holders() + [unit(X, F), unit(905777, 304)], cities=(A, F, g), movable=[X]),
                  observation(holders() + [unit(X, 405)], cities=(A, F, g), movable=[X], held=(A,)),
                  observation(holders() + [unit(X, 304, move_path=[405])], cities=(A, F, g), movable=[]),
                  observation(holders() + [unit(X, 304, move_path=route(304, F))], cities=(A, F, g), movable=[]),
                  observation(holders(), cities=(A, F, g), movable=[]),
                  observation(holders() + [unit(X, A)], cities=(A, F, g), movable=[], held=(A,))]
        compared = 0
        for obs in scenes:
            mine = {u: list(r) for u, r in records.items()}
            theirs = {u: list(r) for u, r in records.items()}
            ended_mine = sh.observe(obs, RED, mine)
            ended_theirs = posthoc.observe_corrected(obs, RED, theirs)
            self.assertEqual(mine, theirs)
            self.assertEqual(sorted(ended_mine), sorted(ended_theirs))
            relabel = {sh.STANDING_UNHELD: "standing on an objective"}
            self.assertEqual({u: relabel.get(r, r) for u, r in ended_mine.items()}, ended_theirs)
            compared += 1
        self.assertEqual(compared, len(scenes))

    def test_every_other_transition_is_the_frozen_one(self) -> None:
        # absent, moving to an objective, source held (staging facts kept), a place given, cannot arrive
        first = self.shadow(self.withheld_scene(), "delayed-repeat-2")
        gone = observation(holders(), cities=(A, E), movable=[])
        self.assertEqual(self.shadow(gone, "delayed-repeat-2", first.memory).ended, {X: sh.ABSENT})
        mover = observation(holders() + [unit(X, 506, move_path=[507, E])], cities=(A, E), movable=[])
        self.assertEqual(self.shadow(mover, "delayed-repeat-2", first.memory).ended, {X: sh.MOVING})
        start = self.shadow(self.staged_scene_start(), "delayed-post-stage-any")
        held = observation(holders() + [unit(X, 405)], cities=(A, F), movable=[], held=(A,))
        after = self.shadow(held, "delayed-post-stage-any", start.memory)
        record = td.decode(after.memory)[0][X]
        self.assertEqual((record[td.SOURCE], record[td.COUNT], record[td.REDIRECTED]), (0, 0, 0))
        self.assertEqual((record[td.STAGED], record[td.DONE], record[td.STAGE_SOURCE]), (405, 1, A))
        self.assertEqual(after.ended, {X: sh.SOURCE_HELD})
        room = observation([unit(h, A) for h in HOLDERS[:3]] + [unit(X, 506)], cities=(A, E), movable=[X])
        given = self.shadow(room, "delayed-repeat-2", first.memory)
        self.assertEqual((given.selected, given.ended, given.memory), ({X: A}, {X: "given a place"}, ()))
        late = observation(holders() + [unit(X, 506)], cities=(A, E), movable=[X], cur_step=2870)
        self.assertEqual(self.shadow(late, "delayed-repeat-2", first.memory).ended,
                         {X: "cannot arrive before the end"})

    # -- triggers, stage completion, recourse ------------------------------------------------------------------------
    def test_post_stage_any_needs_a_completed_staging_move(self) -> None:
        start, arrived = self.shadow_sequence(sh.TARGET, [self.staged_scene_start(), self.staged_scene_arrived()])
        self.assertEqual((start.redirected, start.staged[X][-1]), ({}, 405))
        self.assertEqual(arrived.redirected[X].objective, F)
        self.assertEqual(arrived.eligible, (X,))
        moving = observation(holders() + [unit(X, 304, move_path=[405])], cities=(A, F), movable=[])
        self.assertEqual(self.shadow_sequence(sh.TARGET, [self.staged_scene_start(), moving])[1].claimants, {})
        short = observation(holders() + [unit(X, 304)], cities=(A, F), movable=[X])
        stopped = self.shadow_sequence(sh.TARGET, [self.staged_scene_start(), short])[1]
        self.assertEqual((stopped.redirected, stopped.eligible), ({}, ()))
        never = self.shadow_sequence(sh.TARGET, [self.withheld_scene()] * 4)  # withheld, never staged: no trigger
        self.assertEqual([r.eligible for r in never], [(), (), (), ()])

    def test_at_most_one_redirect_per_episode_and_a_new_source_resets(self) -> None:
        results = self.shadow_sequence("delayed-repeat-2", [self.withheld_scene()] * 5)
        self.assertEqual([bool(r.redirected) for r in results], [False, True, False, False, False])
        stale = [0] * len(td.FIELD_NAMES)
        stale[td.SOURCE], stale[td.COUNT], stale[td.REDIRECTED], stale[td.FIRST] = E, 5, 1, 7
        renewed = self.shadow(self.withheld_scene(), "delayed-repeat-2", td.encode({X: stale}))
        record = td.decode(renewed.memory)[0][X]
        self.assertEqual((record[td.SOURCE], record[td.COUNT], record[td.REDIRECTED]), (A, 1, 0))
        again = self.shadow(self.withheld_scene(), "delayed-repeat-2", renewed.memory)
        self.assertEqual(again.redirected[X].objective, E)  # a new episode allows one redirect again

    def test_episode_tracker_agrees_with_the_state_machine(self) -> None:
        tracker = ms.EpisodeTracker()
        memory = ()
        for k, obs in enumerate([self.withheld_scene()] * 5, start=1):
            policy, base = self.base(obs)
            v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
            ground = {u.obj_id: (u.cur_hex, tuple(u.move_path or ())) for u in obs.operators() if u.color == RED}
            tracker.before(ground, {c.coord: c.flag for c in obs.cities()}, RED)
            result = sh.allocate(obs, SEAT, RED, base, policy.router, sh.RULES["delayed-repeat-2"], memory)
            memory = result.memory
            tracker.after(k, {u: (c.objective, c.status == tr.FULL, u in v3.selected) for u, c in v3.claimants.items()},
                          {u: o.objective for u, o in result.redirected.items()})
        summary = ms.recourse([tracker])
        self.assertEqual((summary["episodes"], summary["max_redirects_per_episode"], summary["pass"]), (1, 1, True))

    # -- scope ------------------------------------------------------------------------------------------------------
    def test_identity_rules_and_target(self) -> None:
        self.assertEqual(sh.SHADOW_ID, "s16-delayed-shadow-v6")
        self.assertEqual(list(sh.RULES), list(td.RULES))
        self.assertTrue(all(sh.RULES[n] is td.RULES[n] for n in td.RULES))
        self.assertEqual(sh.TARGET, "delayed-post-stage-any")
        self.assertEqual(sh.identity(sh.TARGET), "s16-delayed-post-stage-any-shadow-v6")
        self.assertEqual({r.identity for r in td.RULES.values()}, {f"t9-{n}-v5" for n in td.RULES})  # v5 untouched
        self.assertEqual([row[0] for row in sh.shadow_rules()], list(td.RULES))

    def test_nothing_here_can_act_in_an_engine(self) -> None:
        source = Path(sh.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        self.assertEqual(classes, [])
        imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(sorted(imported), ["__future__", "boundary", "decision.routing", "experiments", "typing"])
        self.assertEqual(tuple(inspect.signature(sh.allocate).parameters),
                         ("observation", "seat", "faction", "actions", "router", "rule", "memory"))
        for name in ("POLICIES", "AGENTS", "Policy", "Agent", "Addon"):
            self.assertFalse(hasattr(sh, name), name)
        runner = (ROOT / "scripts" / "run_s16_game.py").read_text(encoding="utf-8")
        self.assertNotIn("s16_shadow", runner)  # the game entry point never imports a shadow
        self.assertNotIn("t9_delayed", runner)

    def test_every_replay_stream_starts_with_empty_shadow_memory(self) -> None:
        """reset() between games: the analysis starts every shadow's memory empty for every stream."""
        tree = ast.parse((ROOT / "scripts" / "s16_analysis.py").read_text(encoding="utf-8"))
        replay = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "replay")
        text = ast.unparse(replay)
        self.assertIn("memories = {n: () for n in SHADOWS}", text)
        self.assertIn("memories[V3_TRACK] = ()", text)
        self.assertEqual(sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "replay"), 1)


if __name__ == "__main__":
    unittest.main()
