"""The Sprint 17 executable candidate ``t9-delayed-post-stage-any-v6`` (``experiments/t9_post_stage_v6.py``).
SYNTHETIC observations on the scenes of ``tests/test_t9_delayed.py`` (geometry computed with the project's router and
asserted as a precondition, never typed by hand).

What is pinned here: the candidate equals Sprint 16's analysis-side target shadow (``s16-delayed-post-stage-any-
shadow-v6``) on every synthetic decision sequence, actions and memory alike, and its memory update is the shadow's,
function body for function body; it equals frozen v3 while nobody is eligible; memory starts empty in every game and is
seat-local and bounded; at most one redirect per episode; decisions are free of emission and operator order; every
failure path fails closed; the source identity is pinned and the frozen modules are byte-identical to the ones Sprint 16
pinned; and the identity may appear in exactly one committed run card, the owner-authorized Sprint 17 probe card.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
import random
import unittest
from pathlib import Path
from typing import List, Sequence
from unittest import mock

from miaosuan_agent.boundary import Observation
from miaosuan_agent.decision import digest
from miaosuan_agent.evaluation import s16_shadow as sh
from miaosuan_agent.evaluation import s17_probe as sp
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments import t9_delayed as td
from miaosuan_agent.experiments import t9_post_stage_v6 as c6
from miaosuan_agent.experiments import t9_redistribution as tr
from tests import test_t9_delayed as t15
from tests.fixtures import synthetic as syn
from tests.test_t9_delayed import A, E, F, X, holders, outcome
from tests.test_t9_redistribution import RED, SEAT, SHOT, cost, observation, unit

ROOT = Path(__file__).resolve().parents[1]


def full(result: td.Allocation) -> tuple:
    return ([dict(a) for a in result.actions], result.memory, outcome(result), result.overflow, result.eligible,
            dict(result.best), dict(result.ended), [dict(c) for c in result.changes], dict(result.skipped),
            result.error)


def body_dump(function, rename: dict = None) -> str:
    node = ast.parse(inspect.getsource(function)).body[0]
    body = [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]

    class Rename(ast.NodeTransformer):
        def visit_Name(self, name: ast.Name) -> ast.Name:
            return ast.copy_location(ast.Name(id=(rename or {}).get(name.id, name.id), ctx=name.ctx), name)

    return "\n".join(ast.dump(Rename().visit(copy.deepcopy(n))) for n in body)


class CandidateTest(unittest.TestCase):
    setUp = t15.DelayedTest.setUp
    base = t15.DelayedTest.base
    withheld_scene = t15.DelayedTest.withheld_scene
    staged_scene_start = t15.DelayedTest.staged_scene_start
    staged_scene_arrived = t15.DelayedTest.staged_scene_arrived
    seven_objectives = t15.DelayedTest.seven_objectives

    def candidate(self, obs: Observation, memory=(), actions=None, router=None) -> td.Allocation:
        policy, base = self.base(obs)
        return c6.allocate(obs, SEAT, RED, base if actions is None else actions, router or policy.router, memory)

    def shadow(self, obs: Observation, memory=(), actions=None) -> td.Allocation:
        policy, base = self.base(obs)
        return sh.allocate(obs, SEAT, RED, base if actions is None else actions, policy.router,
                           sh.RULES[sh.TARGET], memory)

    def sequence(self, observations: Sequence[Observation]) -> List[td.Allocation]:
        memory, out = (), []
        for obs in observations:
            result = self.candidate(obs, memory)
            out.append(result)
            memory = result.memory
        return out

    def g_alternative(self, start: int) -> int:
        for hex_ in sorted(r * 100 + c for r in range(10) for c in range(10)):
            if hex_ in (A, E, F, start):
                continue
            if cost(start, A) < cost(start, hex_) <= tr.DETOUR * cost(start, A):
                return hex_
        self.fail("no alternative objective in the synthetic grid")

    def pool(self) -> List[Observation]:
        g = self.g_alternative(F)
        return [self.withheld_scene(), self.staged_scene_start(), self.staged_scene_arrived(),
                self.staged_scene_arrived(held=(A,)),
                observation(holders() + [unit(X, 304, move_path=[405])], cities=(A, F), movable=[]),
                observation(holders() + [unit(X, 304)], cities=(A, F), movable=[X]),
                observation(holders() + [unit(X, F)], cities=(A, F, g), movable=[X], held=(F,)),
                observation(holders() + [unit(X, F)], cities=(A, F, g), movable=[X]),
                observation(holders(), cities=(A, F), movable=[]),
                self.seven_objectives()]

    # -- equality with the Sprint 16 target shadow -------------------------------------------------------------------
    def test_candidate_equals_the_sprint16_target_shadow_on_synthetic_sequences(self) -> None:
        pool = self.pool()
        sequences = [[pool[1], pool[2], pool[2], pool[2]], [pool[1], pool[4], pool[2]], [pool[1], pool[5], pool[2]],
                     [pool[0]] * 4, [pool[1], pool[3], pool[2]], [pool[1], pool[2], pool[6], pool[7]],
                     [pool[9]] * 3, [pool[1], pool[8], pool[2]]]
        rng = random.Random(17)
        sequences += [[rng.choice(pool) for _ in range(6)] for _ in range(24)]
        compared, redirects = 0, 0
        for sequence in sequences:
            mine, theirs = (), ()
            for obs in sequence:
                a = self.candidate(obs, mine)
                b = self.shadow(obs, theirs)
                self.assertEqual(full(a), full(b))
                mine, theirs = a.memory, b.memory
                compared += 1
                redirects += len(a.redirected)
        self.assertEqual(compared, sum(len(s) for s in sequences))  # every decision of every sequence was compared
        self.assertEqual(compared, 171)
        self.assertGreater(redirects, 0)  # the comparison covers redirects, not only v3's decisions

    def test_memory_update_and_allocation_are_the_shadows_function_bodies(self) -> None:
        self.assertEqual(body_dump(c6.observe), body_dump(sh.observe))
        self.assertEqual(body_dump(c6.allocate), body_dump(sh.allocate, {"rule": "RULE"}))
        self.assertEqual((c6.ABSENT, c6.MOVING, c6.STANDING_UNHELD, c6.SOURCE_HELD),
                         (sh.ABSENT, sh.MOVING, sh.STANDING_UNHELD, sh.SOURCE_HELD))
        self.assertIs(c6.RULE, td.RULES["delayed-post-stage-any"])
        self.assertIs(c6.RULE, sh.RULES[sh.TARGET])
        self.assertEqual((c6.RULE.trigger, c6.RULE.same_source), ("staged", False))

    # -- equality with v3 before eligibility ---------------------------------------------------------------------------
    def test_nobody_eligible_equals_v3(self) -> None:
        for obs in self.pool():
            policy, base = self.base(obs)
            v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
            fresh = self.candidate(obs)
            self.assertEqual([dict(a) for a in fresh.actions], [dict(a) for a in v3.actions])
            self.assertEqual((fresh.selected, fresh.staged, fresh.withheld, fresh.redirected, fresh.eligible),
                             (v3.selected, v3.staged, v3.withheld, {}, ()))
        # a staging move emitted but not completed: still v3
        start = self.candidate(self.staged_scene_start())
        short = observation(holders() + [unit(X, 304)], cities=(A, F), movable=[X])
        policy, base = self.base(short)
        self.assertEqual([dict(a) for a in self.candidate(short, start.memory).actions],
                         [dict(a) for a in tb.allocate(short, SEAT, RED, base, policy.router).actions])

    def test_post_stage_any_redirects_after_a_completed_staging_move_only(self) -> None:
        start, arrived = self.sequence([self.staged_scene_start(), self.staged_scene_arrived()])
        self.assertEqual((start.redirected, start.staged[X][-1]), ({}, 405))
        self.assertEqual((arrived.redirected[X].objective, arrived.eligible), (F, (X,)))
        self.assertEqual([r.eligible for r in self.sequence([self.withheld_scene()] * 4)], [(), (), (), ()])

    def test_a_held_objective_keeps_the_completed_staging_fact(self) -> None:
        g = self.g_alternative(F)
        record = [0] * len(td.FIELD_NAMES)
        record[td.SOURCE], record[td.COUNT], record[td.STAGED], record[td.DONE], record[td.STAGE_SOURCE] = A, 1, 405, 1, A
        scene = observation(holders() + [unit(X, F)], cities=(A, F, g), movable=[X], held=(F,))
        self.assertEqual(self.candidate(scene, td.encode({X: record})).redirected[X].objective, g)
        unheld = observation(holders() + [unit(X, F)], cities=(A, F, g), movable=[])
        after = self.candidate(unheld, td.encode({X: record}))
        self.assertEqual((after.ended, after.memory), ({X: c6.STANDING_UNHELD}, ()))

    def test_the_trace_records_every_ended_record(self) -> None:
        policy = c6.PostStageAnyV6Policy(self.costs)
        first = policy.decide(self.staged_scene_start(), SEAT, RED, ea.AddonMemory())
        gone = observation(holders(), cities=(A, F), movable=[])
        after = policy.decide(gone, SEAT, RED, first.memory)
        ended = [json.loads(c) for c in after.trace.changes if json.loads(c)["kind"] == "memory-ended"]
        self.assertEqual(ended, [{"kind": "memory-ended", "obj_id": X, "reason": c6.ABSENT}])
        self.assertEqual(after.memory.addon, ())

    # -- recourse, ordering, determinism ------------------------------------------------------------------------------
    def test_at_most_one_redirect_per_episode_and_no_oscillation_within_it(self) -> None:
        results = self.sequence([self.staged_scene_start()] + [self.staged_scene_arrived()] * 4)
        self.assertEqual([bool(r.redirected) for r in results], [False, True, False, False, False])
        self.assertEqual(td.decode(results[-1].memory)[0][X][td.REDIRECTED], 1)
        self.assertEqual([tuple(r.withheld) for r in results[2:]], [(X,)] * 3)  # deferred, never sent back to A

    def test_competing_eligible_claimants_take_places_in_rank_order_whatever_the_emission_order(self) -> None:
        y = 904999
        standing_at_e = [unit(905300 + k, E) for k in range(3)]
        obs = observation(holders() + standing_at_e + [unit(y, 105), unit(X, 506)], cities=(A, E), movable=[X, y])
        self.assertLess(cost(506, A), cost(105, A))
        self.assertLessEqual(cost(105, E), tr.DETOUR * cost(105, A))
        self.assertLessEqual(cost(506, E), tr.DETOUR * cost(506, A))
        done = [A, 1, 105, 1, 0, 0, 0, 1, A]
        records = td.encode({X: [A, 1, 506, 1, 0, 0, 0, 1, A], y: done})
        _, base = self.base(obs)
        for order in (list(base), list(reversed(base))):
            result = self.candidate(obs, records, order)
            self.assertEqual(set(result.redirected), {X})  # one place at E: the faster claimant takes it

    def test_decisions_and_memory_are_free_of_emission_and_operator_order(self) -> None:
        obs = self.seven_objectives()
        _, base = self.base(obs)
        records = {a["obj_id"]: [tb.destination(a), 1, 100, 1, 0, 0, 0, 1, 77] for a in base if a.get("type") == 1}
        memory = td.encode(records)
        reference = self.candidate(obs, memory, base)
        self.assertTrue(reference.redirected)
        rng = random.Random(171)
        for order in [list(reversed(range(len(base))))] + [rng.sample(range(len(base)), len(base)) for _ in range(6)]:
            other = self.candidate(obs, memory, [base[i] for i in order])
            self.assertEqual((outcome(other), other.memory), (outcome(reference), reference.memory))
            self.assertEqual({a["obj_id"]: dict(a) for a in other.actions},
                             {a["obj_id"]: dict(a) for a in reference.actions})
        raw = dict(obs.fields)
        flipped = Observation.from_raw(dict(raw, operators=list(reversed(raw["operators"]))), obs.origin)
        other = self.candidate(flipped, memory, base)
        self.assertEqual((outcome(other), other.memory), (outcome(reference), reference.memory))

    def test_fresh_router_gives_identical_decisions_and_memory(self) -> None:
        from miaosuan_agent.decision.routing import Router
        memory = ()
        for obs in [self.staged_scene_start(), self.staged_scene_arrived(), self.seven_objectives()]:
            first = self.candidate(obs, memory)
            second = self.candidate(obs, memory, router=Router(self.costs))
            self.assertEqual((outcome(first), first.memory), (outcome(second), second.memory))
            memory = first.memory

    def test_memory_is_seat_local_and_bounded(self) -> None:
        memory = ()
        for obs in [self.seven_objectives()] * 4 + self.pool():
            result = self.candidate(obs, memory)
            records = td.decode(result.memory)[0]
            own = {u.obj_id for u in obs.operators() if u.color == RED and u.unit_type in td.GROUND}
            self.assertLessEqual(set(records), own)
            cities = {c.coord for c in obs.cities()}
            hexes = {u.cur_hex for u in obs.operators() if u.color == RED} | {
                h for u in obs.operators() if u.color == RED for h in (u.move_path or ())}
            hexes |= {h for a in self.base(obs)[1] if a.get("type") == 1 for h in a["move_path"]}
            for record in records.values():
                for index in (td.SOURCE, td.ALTERNATIVE, td.STAGE_SOURCE):
                    self.assertIn(record[index], cities | {0})
                self.assertIn(record[td.STAGED], hexes | {0})
            memory = result.memory

    # -- game reset ---------------------------------------------------------------------------------------------------
    def test_memory_starts_empty_in_every_game(self) -> None:
        agent = c6.PostStageAnyV6Agent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        self.assertEqual(agent.memory, ea.AddonMemory())
        agent.step(dict(self.staged_scene_start().fields))
        self.assertTrue(agent.memory.addon)
        arrived = dict(self.staged_scene_arrived().fields)
        memory = agent.memory
        agent.step(arrived)
        self.assertIn("redirect", [json.loads(c)["kind"] for c in agent.last_trace.changes])
        self.assertEqual(agent.last_trace.policy, sp.CANDIDATE_ID)
        self.assertEqual(digest(agent.replay(arrived, memory)), digest(agent.last_trace))
        agent.reset()
        self.assertEqual(agent.memory, ea.AddonMemory())
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        self.assertEqual(agent.memory, ea.AddonMemory())
        agent.step(arrived)  # a new game: no staging move remembered, so nothing is eligible
        self.assertNotIn("redirect", [json.loads(c)["kind"] for c in agent.last_trace.changes])

    # -- failure ----------------------------------------------------------------------------------------------------
    def test_internal_failure_withholds_objective_moves_and_keeps_memory(self) -> None:
        start = self.candidate(self.staged_scene_start())
        obs = self.staged_scene_arrived()
        _, base = self.base(obs)
        with mock.patch.object(td, "path_times", side_effect=RuntimeError("planted")):
            result = self.candidate(obs, start.memory, list(base) + [SHOT])
        self.assertEqual([dict(a) for a in result.actions], [SHOT])
        self.assertIn("planted", result.error)
        self.assertEqual(td.decode(result.memory)[0][X][td.STAGED], 405)

    def test_failed_memory_update_forgets_and_redirects_nothing(self) -> None:
        start = self.candidate(self.staged_scene_start())
        with mock.patch.object(c6, "observe", side_effect=RuntimeError("planted")):
            result = self.candidate(self.staged_scene_arrived(), start.memory)
        self.assertEqual(result.redirected, {})
        self.assertIn("memory-dropped", [c["kind"] for c in result.changes])

    def test_malformed_memory_is_dropped_and_gives_v3(self) -> None:
        obs = self.staged_scene_arrived()
        policy, base = self.base(obs)
        result = self.candidate(obs, ((X * td.FIELDS + td.DONE, "bad"), (-1, 2)))
        self.assertEqual([dict(a) for a in result.actions],
                         [dict(a) for a in tb.allocate(obs, SEAT, RED, base, policy.router).actions])
        self.assertIn("memory-dropped", [c["kind"] for c in result.changes])

    def test_an_add_on_exception_falls_back_to_baseline_v2_and_records_the_error(self) -> None:
        policy = c6.PostStageAnyV6Policy(self.costs)
        obs = self.staged_scene_start()
        first = policy.decide(obs, SEAT, RED, ea.AddonMemory())
        with mock.patch.object(c6, "allocate", side_effect=RuntimeError("planted")):
            failed = policy.decide(self.staged_scene_arrived(), SEAT, RED, first.memory)
        _, base = self.base(self.staged_scene_arrived())
        self.assertEqual([dict(a) for a in failed.actions], [dict(a) for a in base])
        self.assertIn("planted", failed.trace.addon_error)
        self.assertEqual(failed.memory.addon, first.memory.addon)

    def test_non_play_stage_keeps_memory_and_actions(self) -> None:
        start = self.candidate(self.staged_scene_start())
        obs = self.withheld_scene(stage=1)
        result = self.candidate(obs, start.memory)
        self.assertEqual(result.memory, start.memory)
        self.assertEqual([dict(a) for a in result.actions], [dict(a) for a in self.base(obs)[1]])

    # -- identity, scope and the whitelist ----------------------------------------------------------------------------
    def test_module_reads_no_analysis_code_and_adds_no_tactical_literal(self) -> None:
        source = Path(c6.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(sorted(imported), ["", "__future__", "boundary", "decision.routing", "exploratory_addon",
                                            "typing"])
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                    and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}
        # only the flag values of the copied memory update: no threshold, timing, corridor or special case of its own
        self.assertEqual(literals, {0, 1}, literals)
        code = source.split('"""', 2)[2]
        for word in ("scenario", "decision_index", "1930331196", "2120531121", "threat", "corridor"):
            self.assertNotIn(word, code)

    def test_identity_and_policy_classes(self) -> None:
        self.assertEqual((c6.CANDIDATE_ID, c6.ADDON_NAME), ("t9-delayed-post-stage-any-v6", "t9_delayed_v6"))
        self.assertEqual(c6.PostStageAnyV6Policy.identity, c6.CANDIDATE_ID)
        self.assertIs(c6.PostStageAnyV6Agent.policy_class, c6.PostStageAnyV6Policy)
        for frozen in ("t9-batch-capacity-v3", "s16-delayed-post-stage-any-shadow-v6", "t9-delayed-post-stage-any-v5",
                       "s16-delayed-shadow-v6"):
            self.assertNotEqual(c6.CANDIDATE_ID, frozen)
        self.assertNotIn(c6.CANDIDATE_ID, {p.identity for p in td.POLICIES.values()})

    def test_source_identity_is_pinned_and_the_frozen_modules_are_unchanged(self) -> None:
        from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files
        spec = importlib.util.spec_from_file_location("bs17", ROOT / "scripts" / "build_s17_card.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        files = policy_source_files(sources=module.CANDIDATE_SOURCES)
        self.assertEqual(digest_of_files(files), sp.CANDIDATE_DIGEST)
        self.assertIn("experiments/t9_post_stage_v6.py", files)
        v3_sources = module.V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_batch.py")
        self.assertEqual(digest_of_files(policy_source_files(sources=v3_sources)),
                         "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8")
        s16 = json.loads((ROOT / "evaluation" / "s16-v3-mechanism-capture-1" / "manifest.json").read_text("utf-8"))
        pinned = s16["screen"]["frozen_files"]
        for rel in ("src/miaosuan_agent/experiments/t9_batch.py", "src/miaosuan_agent/experiments/t9_delayed.py",
                    "src/miaosuan_agent/experiments/t9_redistribution.py",
                    "src/miaosuan_agent/experiments/exploratory_addon.py",
                    "src/miaosuan_agent/evaluation/s16_shadow.py"):
            self.assertEqual(sp.normalized_sha256(ROOT / rel), pinned[rel], rel)

    def test_candidate_occurs_only_in_the_approved_sprint17_card(self) -> None:
        """Owner-approved narrow authorization (Sprint 17, 2026-10-06): the identity ``t9-delayed-post-stage-any-v6``
        may appear in exactly one run card, ``s17-post-stage-v6-probe-1``, bound to the registered digest; no wildcard,
        no folder family, no generic builder or runner. A changed source is a new identity that needs new approval."""
        from miaosuan_agent.evaluation import exploratory as xp
        self.assertEqual((sp.CARD_ID, sp.STUDY_ID, sp.CANDIDATE_ID),
                         ("s17-post-stage-v6-probe-1", "s17-first-divergence-probe", c6.CANDIDATE_ID))
        frozen = "b60e3812a8d43ffaf3a015c87783f7693d8e98894c4fb2363b90ea59dd306ec0"
        self.assertEqual(sp.CANDIDATE_DIGEST, frozen)
        cards, seen = 0, set()
        for path in sorted((ROOT / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if c6.CANDIDATE_ID not in text and frozen not in text:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = json.loads(text)
            if isinstance(data, dict) and (xp.is_card(data) or path.name == "manifest.json"):
                cards += 1
                seen.add(rel)
                self.assertEqual(rel, f"evaluation/{sp.CARD_ID}/manifest.json")
                self.assertEqual(((data.get("screen") or {}).get("id"), data.get("candidate")),
                                 (sp.STUDY_ID, sp.CANDIDATE_ID))
                source = data["policies"][sp.CANDIDATE_ID]["policy_source"]
                self.assertEqual(source["sha256"], frozen)
                self.assertIn("experiments/t9_post_stage_v6.py", source["files"])
                self.assertNotIn("t9-batch-capacity-v3", text)  # the v3 whitelist is not broadened
                self.assertNotIn("9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8", text)
                continue
            self.assertTrue(rel.startswith(f"evaluation/{sp.STUDY_ID}/"), rel)
            self.assertFalse(isinstance(data, dict) and data.get("executable"), rel)
        self.assertEqual(cards, 1, "exactly the approved Sprint 17 card binds the candidate")
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "build_t9_diagnostic_card.py",
                     "run_evaluation.py", "run_s12_game.py", "run_s16_game.py", "build_s16_card.py"):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn("t9_post_stage_v6", text, name)
            self.assertNotIn(c6.CANDIDATE_ID, text, name)
        users = sorted(p.name for p in (ROOT / "scripts").glob("*.py")
                       if "t9_post_stage_v6" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["build_s17_card.py", "mutate_s17.py", "run_s17_game.py", "s17_analysis.py"])


if __name__ == "__main__":
    unittest.main()
