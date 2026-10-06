"""OFFLINE design candidates of Sprint 15 (``experiments/t9_delayed.py``). SYNTHETIC observations.

Geometry is computed with the project's router on the 10 x 10 synthetic grid (uniform cost 1 per hex) and asserted as
a precondition, never typed by hand. Vehicles have ``basic_speed`` 36 (20 steps per hex). Objective A is 505.

Scenes:

* WITHHELD: four own units stand on A; X stands next to A (506) and can only claim A (a one-hex path, so no staging hex
  exists and v3 withholds it); objective E (508) is within twice X's cost to A.
* STAGED: the same four units on A; X starts at 1, claims A along a seven-hex path and is staged on 405 (the last
  non-objective hex); from 405 objective F (407) is within twice the cost to A, from 1 it is not nearer than A.
"""

from __future__ import annotations

import ast
import json
import random
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, Observation
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments import t9_delayed as td
from miaosuan_agent.experiments import t9_redistribution as tr
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn
from tests.test_t9_redistribution import RED, SEAT, SHOT, cost, observation, route, unit

A, E, F = 505, 508, 407
X = 905000
HOLDERS = [905100 + k for k in range(4)]


def outcome(result: td.Allocation) -> tuple:
    return (dict(result.selected), {u: (o.objective, tuple(o.path)) for u, o in result.redirected.items()},
            {u: tuple(p) for u, p in result.staged.items()}, dict(result.withheld))


def holders(at: int = A) -> List[Dict[str, Any]]:
    return [unit(h, at) for h in HOLDERS]


class DelayedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())

    def base(self, obs: Observation):
        policy = ShootReservationPolicy(self.costs)
        return policy, tuple(policy.decide(obs, SEAT, RED, Memory()).actions)

    def run_rule(self, obs: Observation, rule: Optional[str], memory=(), actions=None, everyone=False,
                 router=None) -> td.Allocation:
        policy, base = self.base(obs)
        rule_ = None if rule is None else td.RULES[rule]
        return td.allocate(obs, SEAT, RED, base if actions is None else actions, router or policy.router, rule_,
                           memory, everyone)

    def sequence(self, rule: str, observations: Sequence[Observation]) -> List[td.Allocation]:
        memory, out = (), []
        for obs in observations:
            result = self.run_rule(obs, rule, memory)
            out.append(result)
            memory = result.memory
        return out

    # -- scenes --------------------------------------------------------------------------------------------------
    def withheld_scene(self, **kw: Any) -> Observation:
        self.assertEqual(route(506, A), [A])
        self.assertLessEqual(cost(506, E), tr.DETOUR * cost(506, A))
        self.assertLess(cost(506, A), cost(506, E))
        return observation(holders() + [unit(X, 506)], cities=(A, E), movable=[X], **kw)

    def staged_scene_start(self) -> Observation:
        path = route(1, A)
        self.assertEqual(path[-2], 405)
        self.assertLess(cost(1, A), cost(1, F))
        self.assertLessEqual(cost(1, F), tr.DETOUR * cost(1, A))
        return observation(holders() + [unit(X, 1)], cities=(A, F), movable=[X])

    def staged_scene_arrived(self, **kw: Any) -> Observation:
        self.assertLessEqual(cost(405, F), tr.DETOUR * cost(405, A))
        self.assertLess(cost(405, A), cost(405, F))
        return observation(holders() + [unit(X, 405)], cities=(A, F), movable=[X], **kw)

    # -- identities ----------------------------------------------------------------------------------------------
    def test_no_eligible_claimant_equals_v3_and_everyone_equals_the_minimal_rule(self) -> None:
        shapes = [self.withheld_scene(), self.staged_scene_start(), self.staged_scene_arrived(),
                  self.seven_objectives(), observation([unit(905200 + k, h) for k, h in enumerate((503, 507, 303, 703,
                                                                                                  100))], cities=(A,))]
        for obs in shapes:
            policy, base = self.base(obs)
            v3 = tb.allocate(obs, SEAT, RED, base, policy.router)
            mine = td.allocate(obs, SEAT, RED, base, policy.router, None)
            self.assertEqual([dict(a) for a in mine.actions], [dict(a) for a in v3.actions])
            self.assertEqual((mine.selected, mine.staged, mine.withheld, mine.redirected),
                             (v3.selected, v3.staged, v3.withheld, {}))
            o2 = tr.allocate(obs, SEAT, RED, base, policy.router, tr.RULES["feasible-value-redirect"])
            everyone = td.allocate(obs, SEAT, RED, base, policy.router, None, everyone=True)
            self.assertEqual([dict(a) for a in everyone.actions], [dict(a) for a in o2.actions])
            self.assertEqual({u: (o.objective, o.path) for u, o in everyone.redirected.items()},
                             {u: (o.objective, o.path) for u, o in o2.redirected.items()})
            self.assertEqual((everyone.staged, everyone.withheld), (o2.staged, o2.withheld))
            for name in td.RULES:  # with no memory no rule is eligible: v3 exactly
                fresh = td.allocate(obs, SEAT, RED, base, policy.router, td.RULES[name])
                self.assertEqual([dict(a) for a in fresh.actions], [dict(a) for a in v3.actions], name)

    def test_the_scenes_are_what_they_claim(self) -> None:
        first = self.run_rule(self.withheld_scene(), None, everyone=True)
        self.assertEqual(first.redirected[X].objective, E)  # O2 would redirect at once
        self.assertEqual(self.run_rule(self.withheld_scene(), None).withheld, {X: tr.FULL})
        start = self.run_rule(self.staged_scene_start(), None)
        self.assertEqual(start.staged[X][-1], 405)
        self.assertEqual(self.run_rule(self.staged_scene_start(), None, everyone=True).redirected[X].objective, F)

    # -- triggers on sequences -----------------------------------------------------------------------------------
    def test_repeat_two_defers_the_first_overflow_and_redirects_the_second(self) -> None:
        first, second = self.sequence("delayed-repeat-2", [self.withheld_scene()] * 2)
        self.assertEqual(first.redirected, {})
        self.assertEqual(first.withheld, {X: tr.FULL})
        self.assertEqual(first.eligible, ())
        self.assertEqual(second.redirected[X].objective, E)
        self.assertEqual(second.eligible, (X,))

    def test_repeat_three_needs_three_observations(self) -> None:
        results = self.sequence("delayed-repeat-3", [self.withheld_scene()] * 3)
        self.assertEqual([bool(r.redirected) for r in results], [False, False, True])

    def test_stable_alternative_needs_the_same_best_alternative_twice(self) -> None:
        results = self.sequence("delayed-stable-alternative", [self.withheld_scene()] * 2)
        self.assertEqual([bool(r.redirected) for r in results], [False, True])
        # the alternative is held by the side at the second observation: no alternative, no redirect
        moved = self.sequence("delayed-stable-alternative", [self.withheld_scene(),
                                                             self.withheld_scene(held=(E,))])
        self.assertEqual([bool(r.redirected) for r in moved], [False, False])

    def test_saturated_source_needs_four_standing_units_twice(self) -> None:
        results = self.sequence("delayed-saturated-source", [self.withheld_scene()] * 2)
        self.assertEqual([bool(r.redirected) for r in results], [False, True])
        # three standing units and a counted mover: full but not saturated
        mover = unit(905150, 504, move_path=route(504, A))
        obs = observation([unit(h, A) for h in HOLDERS[:3]] + [mover, unit(X, 506)], cities=(A, E), movable=[X])
        results = self.sequence("delayed-saturated-source", [obs, obs])
        self.assertEqual([bool(r.redirected) for r in results], [False, False])
        self.assertEqual(results[1].overflow, (X,))
        self.assertEqual(self.sequence("delayed-repeat-2", [obs, obs])[1].redirected[X].objective, E)

    def test_post_stage_rules_wait_for_the_completed_staging_move(self) -> None:
        for name in ("delayed-post-stage-same", "delayed-post-stage-any"):
            start, arrived = self.sequence(name, [self.staged_scene_start(), self.staged_scene_arrived()])
            self.assertEqual(start.redirected, {})
            self.assertEqual(start.staged[X][-1], 405)
            self.assertEqual(arrived.redirected[X].objective, F, name)
            # still on the way (a path to the staging hex): not a claimant, nothing changes
            moving = observation(holders() + [unit(X, 304, move_path=[405])], cities=(A, F), movable=[])
            _, on_way = self.sequence(name, [self.staged_scene_start(), moving])
            self.assertEqual(on_way.claimants, {})
            # stopped short of the staging hex: the staging move did not complete
            short = observation(holders() + [unit(X, 304)], cities=(A, F), movable=[X])
            _, stopped = self.sequence(name, [self.staged_scene_start(), short])
            self.assertEqual(stopped.redirected, {}, name)
        # the repeat rule also fires there (second overflow of the same source), the withheld scene never stages
        self.assertTrue(self.sequence("delayed-repeat-2", [self.staged_scene_start(),
                                                           self.staged_scene_arrived()])[1].redirected)
        self.assertEqual([bool(r.redirected) for r in self.sequence(
            "delayed-post-stage-same", [self.withheld_scene()] * 3)], [False, False, False])

    def test_post_stage_any_survives_a_change_of_source_and_same_does_not(self) -> None:
        record = [0] * len(td.FIELD_NAMES)
        record[td.SOURCE], record[td.COUNT], record[td.STAGED], record[td.DONE], record[td.STAGE_SOURCE] = A, 1, 405, 1, A
        self.assertTrue(td.eligible(td.RULES["delayed-post-stage-any"], record, F, 0, False))
        self.assertFalse(td.eligible(td.RULES["delayed-post-stage-same"], record, F, 0, False))
        self.assertTrue(td.eligible(td.RULES["delayed-post-stage-same"], record, A, 0, False))
        for name in ("delayed-repeat-2", "delayed-stable-alternative", "delayed-saturated-source"):
            self.assertFalse(td.eligible(td.RULES[name], record, F, E, True), name)  # a new source starts over

    # -- memory semantics ----------------------------------------------------------------------------------------
    def test_codec_round_trip_and_malformed_entries_are_dropped(self) -> None:
        records = {7: [A, 3, 405, 1, E, 1, 0, 100, A], 905000: [E, 1, 0, 0, 0, 0, 1, 2, 0]}
        encoded = td.encode(records)
        self.assertEqual(list(encoded), sorted(encoded))
        self.assertEqual(td.decode(encoded), (records, []))
        decoded, errors = td.decode(encoded + ((-1, 2), ("x", 1), (7 * td.FIELDS + 15, 1), (1, 2, 3)))
        self.assertEqual(decoded, records)
        self.assertEqual(len(errors), 4)
        # dropped entries never make a unit eligible: a malformed state gives v3 for that decision
        result = self.run_rule(self.withheld_scene(), "delayed-repeat-2", memory=((X * td.FIELDS, "bad"),))
        self.assertEqual(result.redirected, {})
        self.assertIn("memory-dropped", [c["kind"] for c in result.changes])

    def test_records_end_with_the_unit_and_never_outlive_it(self) -> None:
        first = self.run_rule(self.withheld_scene(), "delayed-repeat-2")
        self.assertEqual(set(td.decode(first.memory)[0]), {X})
        gone = observation(holders(), cities=(A, E), movable=[])
        after = self.run_rule(gone, "delayed-repeat-2", first.memory)
        self.assertEqual(td.decode(after.memory)[0], {})
        self.assertEqual(after.ended, {X: "absent"})
        mover = observation(holders() + [unit(X, 506, move_path=[507, E])], cities=(A, E), movable=[])
        self.assertEqual(self.run_rule(mover, "delayed-repeat-2", first.memory).ended, {X: "moving to an objective"})
        standing = observation(holders() + [unit(X, E)], cities=(A, E), movable=[])
        self.assertEqual(self.run_rule(standing, "delayed-repeat-2", first.memory).ended, {X: "standing on an objective"})

    def test_capture_of_the_source_ends_the_episode_but_keeps_the_staging_fact(self) -> None:
        start = self.run_rule(self.staged_scene_start(), "delayed-post-stage-any")
        records = td.decode(start.memory)[0]
        self.assertEqual(records[X][td.STAGED], 405)
        held = observation(holders() + [unit(X, 405)], cities=(A, F), movable=[], held=(A,))
        after = self.run_rule(held, "delayed-post-stage-any", start.memory)
        record = td.decode(after.memory)[0][X]
        self.assertEqual((record[td.SOURCE], record[td.COUNT], record[td.REDIRECTED]), (0, 0, 0))
        self.assertEqual((record[td.STAGED], record[td.DONE], record[td.STAGE_SOURCE]), (405, 1, A))
        self.assertEqual(after.ended, {X: "source held by the side"})
        # a stale episode does not survive the capture: repeat counts start again
        withheld = self.run_rule(self.withheld_scene(), "delayed-repeat-2")
        captured = self.run_rule(self.withheld_scene(held=(A,)), "delayed-repeat-2", withheld.memory)
        self.assertNotIn(X, td.decode(captured.memory)[0])
        again = self.run_rule(self.withheld_scene(), "delayed-repeat-2", captured.memory)
        self.assertEqual(again.redirected, {})

    def test_a_place_given_by_stage_one_ends_the_record(self) -> None:
        first = self.run_rule(self.withheld_scene(), "delayed-repeat-2")
        room = observation([unit(h, A) for h in HOLDERS[:3]] + [unit(X, 506)], cities=(A, E), movable=[X])
        after = self.run_rule(room, "delayed-repeat-2", first.memory)
        self.assertEqual(after.selected, {X: A})
        self.assertEqual(after.ended, {X: "given a place"})
        self.assertEqual(after.memory, ())

    def test_at_most_one_redirect_per_episode_and_no_oscillation(self) -> None:
        results = self.sequence("delayed-repeat-2", [self.withheld_scene()] * 5)
        self.assertEqual([bool(r.redirected) for r in results], [False, True, False, False, False])
        self.assertEqual(results[2].withheld, {X: tr.FULL})  # treated as deferred, never as re-assigned to A
        record = td.decode(results[-1].memory)[0][X]
        self.assertEqual((record[td.REDIRECTED], record[td.SOURCE]), (1, A))
        # on-policy the redirected unit is a mover to E: its record ends; at E it starts from zero
        mover = observation(holders() + [unit(X, 506, move_path=[507, E])], cities=(A, E), movable=[])
        cleared = self.run_rule(mover, "delayed-repeat-2", results[1].memory)
        self.assertEqual(cleared.memory, ())

    def test_memory_is_bounded_by_the_units_present(self) -> None:
        obs = self.seven_objectives()
        memory = ()
        for name in td.RULES:
            memory = ()
            for _ in range(6):
                result = self.run_rule(obs, name, memory)
                memory = result.memory
                records = td.decode(memory)[0]
                own = {u.obj_id for u in obs.operators() if u.color == RED}
                self.assertLessEqual(set(records), own)
                self.assertTrue(all(len(r) == len(td.FIELD_NAMES) for r in records.values()))
                self.assertTrue(all(0 <= r[td.COUNT] <= td.COUNT_CAP for r in records.values()))
        record = [A, td.COUNT_CAP, 0, 0, 0, 0, 0, 1, 0]
        capped = self.run_rule(self.withheld_scene(), "delayed-repeat-3", td.encode({X: record}))
        self.assertEqual(td.decode(capped.memory)[0][X][td.COUNT], td.COUNT_CAP)

    # -- invariance and determinism ------------------------------------------------------------------------------
    def seven_objectives(self) -> Observation:
        cities = (101, 105, 108, 404, 707, 902, 908)
        starts = [100 + i for i in range(10)] + [900 + i for i in range(10)] + [500 + i for i in range(10)]
        units = [unit(904000 + i, h) for i, h in enumerate(starts) if h not in cities]
        return observation(units, cities=cities, values={101: 50, 105: 80, 108: 50, 404: 80, 707: 50, 902: 80,
                                                          908: 50})

    def test_decisions_and_memory_are_free_of_emission_and_operator_order(self) -> None:
        obs = self.seven_objectives()
        _, base = self.base(obs)
        everyone = self.run_rule(obs, None, everyone=True)
        self.assertTrue(everyone.redirected)
        # a memory under which every overflow claimant is eligible for the repeat rule
        records = {u: [tb.destination(a), 1, 0, 0, 0, 0, 0, 1, 0] for u, a in
                   ((a["obj_id"], a) for a in base if a.get("type") == 1)}
        memory = td.encode(records)
        rng = random.Random(15)
        orders = [list(reversed(range(len(base))))] + [rng.sample(range(len(base)), len(base)) for _ in range(6)]
        for name in td.RULES:
            reference = self.run_rule(obs, name, memory, base)
            for order in orders:
                other = self.run_rule(obs, name, memory, [base[i] for i in order])
                self.assertEqual(outcome(other), outcome(reference), name)
                self.assertEqual(other.memory, reference.memory, name)
                self.assertEqual({a["obj_id"]: dict(a) for a in other.actions},
                                 {a["obj_id"]: dict(a) for a in reference.actions}, name)
        reference = self.run_rule(obs, "delayed-repeat-2", memory, base)
        self.assertTrue(reference.redirected)
        raw = dict(obs.fields)
        shuffled = dict(raw, operators=list(reversed(raw["operators"])))
        flipped = Observation.from_raw(shuffled, obs.origin)
        other = self.run_rule(flipped, "delayed-repeat-2", memory, base)
        self.assertEqual((outcome(other), other.memory), (outcome(reference), reference.memory))

    def test_fresh_router_gives_identical_decisions_and_memory(self) -> None:
        from miaosuan_agent.decision.routing import Router
        obs = self.seven_objectives()
        for name in td.RULES:
            memory = ()
            for _ in range(3):
                first = self.run_rule(obs, name, memory)
                second = self.run_rule(obs, name, memory, router=Router(self.costs))
                self.assertEqual((outcome(first), first.memory), (outcome(second), second.memory), name)
                memory = first.memory

    def test_capacity_counts_this_decisions_redirects(self) -> None:
        y = 905001  # a second unit on X's hex: both claim A and both have E as their only alternative
        standing_at_e = [unit(905300 + k, E) for k in range(3)]
        obs = observation(holders() + standing_at_e + [unit(X, 506), unit(y, 506)], cities=(A, E), movable=[X, y])
        records = {u: [A, 1, 0, 0, E, 1, 0, 1, 0] for u in (X, y)}
        result = self.run_rule(obs, "delayed-repeat-2", td.encode(records))
        self.assertEqual(len(result.redirected), 1)  # E had one place left
        self.assertEqual(len(result.withheld), 1)

    # -- failure ----------------------------------------------------------------------------------------------------
    def test_internal_failure_withholds_objective_moves_and_keeps_memory(self) -> None:
        first = self.run_rule(self.withheld_scene(), "delayed-repeat-2")
        obs = self.withheld_scene()
        _, base = self.base(obs)
        with mock.patch.object(td, "path_times", side_effect=RuntimeError("planted")):
            result = self.run_rule(obs, "delayed-repeat-2", first.memory, list(base) + [SHOT])
        self.assertEqual([dict(a) for a in result.actions], [SHOT])
        self.assertIn("planted", result.error)
        self.assertEqual(td.decode(result.memory)[0], td.decode(first.memory)[0])

    def test_failed_memory_update_forgets_and_redirects_nothing(self) -> None:
        first = self.run_rule(self.withheld_scene(), "delayed-repeat-2")
        with mock.patch.object(td, "observe", side_effect=RuntimeError("planted")):
            result = self.run_rule(self.withheld_scene(), "delayed-repeat-2", first.memory)
        self.assertEqual(result.redirected, {})
        self.assertIn("memory-dropped", [c["kind"] for c in result.changes])

    def test_non_play_stage_keeps_memory_and_actions(self) -> None:
        first = self.run_rule(self.withheld_scene(), "delayed-repeat-2")
        obs = self.withheld_scene(stage=1)
        result = self.run_rule(obs, "delayed-repeat-2", first.memory)
        self.assertEqual(result.memory, first.memory)
        _, base = self.base(obs)
        self.assertEqual([dict(a) for a in result.actions], [dict(a) for a in base])

    # -- policies, agent replay, reset, scope ---------------------------------------------------------------------
    def test_frozen_rule_table(self) -> None:
        table = {name: (r.trigger, r.count, r.same_source, r.identity) for name, r in td.RULES.items()}
        self.assertEqual(table, {
            "delayed-repeat-2": ("repeat", 2, True, "t9-delayed-repeat-2-v5"),
            "delayed-repeat-3": ("repeat", 3, True, "t9-delayed-repeat-3-v5"),
            "delayed-stable-alternative": ("stable", 0, True, "t9-delayed-stable-alternative-v5"),
            "delayed-post-stage-same": ("staged", 0, True, "t9-delayed-post-stage-same-v5"),
            "delayed-post-stage-any": ("staged", 0, False, "t9-delayed-post-stage-any-v5"),
            "delayed-saturated-source": ("saturated", 0, True, "t9-delayed-saturated-source-v5")})
        self.assertIs(td.BASE_RULE, tr.RULES["feasible-value-redirect"])
        self.assertEqual((td.FIELDS, td.COUNT_CAP, len(td.FIELD_NAMES)), (16, 1000, 9))
        self.assertEqual({p.identity for p in td.POLICIES.values()}, {r.identity for r in td.RULES.values()})

    def test_policy_memory_flows_through_the_wrapper_and_agent_replay_reproduces_it(self) -> None:
        policy = td.POLICIES["delayed-repeat-2"](self.costs)
        obs = self.withheld_scene()
        first = policy.decide(obs, SEAT, RED, ea.AddonMemory())
        self.assertTrue(first.memory.addon)
        second = policy.decide(obs, SEAT, RED, first.memory)
        kinds = [json.loads(c)["kind"] for c in second.trace.changes]
        self.assertIn("redirect", kinds)
        self.assertEqual(second.trace.policy, "t9-delayed-repeat-2-v5")
        agent = td.AGENTS["delayed-repeat-2"]()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(obs.fields)
        agent.step(raw)
        memory = agent.memory
        self.assertTrue(memory.addon)
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        self.assertIn("redirect", [json.loads(c)["kind"] for c in agent.last_trace.changes])
        agent.reset()
        self.assertEqual(agent.memory, ea.AddonMemory())
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        self.assertEqual(agent.memory, ea.AddonMemory())
        agent.step(raw)  # a new game starts from nothing: the first overflow is deferred again
        self.assertNotIn("redirect", [json.loads(c)["kind"] for c in agent.last_trace.changes])

    def test_module_reads_no_analysis_code_and_holds_no_special_case_literal(self) -> None:
        source = Path(td.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse([m for m in imported if m and ("evaluation" in m or "engine" in m)], imported)
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                    and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}
        self.assertEqual(literals, {0, 1, 2, 3, 16, 300, 1000}, literals)  # 2, 3: rule counts; 16, 1000: memory
        self.assertNotIn("decision_index", source)
        self.assertNotIn("scenario", source.split('"""', 2)[2])


if __name__ == "__main__":
    unittest.main()
