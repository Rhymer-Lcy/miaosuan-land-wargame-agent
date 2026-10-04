"""Synthetic safeguards for exploratory ``t9-capacity-staging-v2``."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import Memory, digest, gate
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_staging as t9s
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn
from tests.test_t9_allocation import A, B, IDS, RED, SEAT, movers, observation, unit


class StagingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        self.policy = t9s.StagingPolicy(self.costs)

    def decide(self, obs):
        return self.policy.decide(obs, SEAT, RED, ea.AddonMemory())

    def baseline(self, obs):
        return ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())

    @staticmethod
    def moves(decision):
        return {a["obj_id"]: a for a in decision.actions if a["type"] == 1}

    def test_overflow_stages_on_the_baseline_route_and_preserves_capacity(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        base, revised = self.baseline(obs), self.decide(obs)
        base_moves, revised_moves = self.moves(base), self.moves(revised)
        self.assertEqual(len(revised_moves), len(IDS))
        self.assertEqual(sum(a["move_path"][-1] == A for a in revised_moves.values()), t9s.CAPACITY)
        for obj_id in IDS[t9s.CAPACITY:]:
            self.assertEqual(revised_moves[obj_id]["move_path"],
                             base_moves[obj_id]["move_path"][:len(revised_moves[obj_id]["move_path"])])
            self.assertNotIn(revised_moves[obj_id]["move_path"][-1], {A, B})
        changes = [json.loads(value) for value in revised.trace.changes]
        self.assertEqual([change["kind"] for change in changes], ["stage", "stage"])
        self.assertEqual(revised.trace.baseline_trace_sha256, digest(base.trace))

    def test_existing_commitments_do_not_block_progress_to_a_staging_point(self) -> None:
        committed = [unit(910000 + k, 101 + k, move_path=[A]) for k in range(t9s.CAPACITY)]
        moving = unit(920000, 201)
        obs = observation(committed + [moving], {920000: {1: None}}, [syn.city(A)])
        base, revised = self.baseline(obs), self.decide(obs)
        self.assertEqual(len(base.actions), 1)
        self.assertEqual(len(revised.actions), 1)
        self.assertLess(len(revised.actions[0]["move_path"]), len(base.actions[0]["move_path"]))
        self.assertEqual(revised.actions[0]["move_path"],
                         base.actions[0]["move_path"][:len(revised.actions[0]["move_path"])])

    def test_staging_retains_a_tactical_corridor_instead_of_cross_objective_redirect(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        base, revised = self.baseline(obs), self.decide(obs)
        for obj_id in IDS[t9s.CAPACITY:]:
            self.assertNotEqual(self.moves(revised)[obj_id]["move_path"][-1], B)
            self.assertTrue(self.moves(base)[obj_id]["move_path"][:len(self.moves(revised)[obj_id]["move_path"])]
                            == self.moves(revised)[obj_id]["move_path"])

    def test_every_objective_at_capacity_and_no_staging_hex_withholds(self) -> None:
        committed = ([unit(930000 + k, 101 + k, move_path=[A]) for k in range(t9s.CAPACITY)] +
                     [unit(940000 + k, 701 + k, move_path=[B]) for k in range(t9s.CAPACITY)])
        mover = unit(950000, 405)
        obs = observation(committed + [mover], {950000: {1: None}}, [syn.city(A), syn.city(B)])
        revised = self.decide(obs)
        self.assertEqual(revised.actions, ())
        change = json.loads(revised.trace.changes[0])
        self.assertEqual(change["kind"], "withhold")
        self.assertEqual(change["commitments"], t9s.CAPACITY)

    def test_staging_gate_rejection_withholds_instead_of_overcommitting(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        real = gate.check

        def reject_staging(proposals, context, router):
            result = real(proposals, context, router)
            staged = [p for p in proposals if p.get("type") == 1 and p["move_path"][-1] not in {A, B}]
            return gate.GateResult(tuple(p for p in result.accepted if p not in staged),
                                   tuple(result.rejected) + tuple(
                                       gate.Rejection(1, p["obj_id"], "planted") for p in staged))

        with mock.patch.object(t9s.gate, "check", side_effect=reject_staging):
            revised = self.decide(obs)
        self.assertEqual(len(self.moves(revised)), t9s.CAPACITY)
        self.assertEqual([json.loads(v)["kind"] for v in revised.trace.changes],
                         ["stage", "stage", "stage-rejected", "stage-rejected"])

    def test_unrelated_actions_and_non_play_states_are_unchanged(self) -> None:
        obs = observation(movers(), {}, [syn.city(A), syn.city(B)])
        self.assertEqual(self.decide(obs).actions, self.baseline(obs).actions)
        deploy = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)], stage=1)
        self.assertEqual([dict(a) for a in self.decide(deploy).actions],
                         [dict(a) for a in self.baseline(deploy).actions])

    def test_unavailable_suppressed_transitioning_and_destroyed_units_are_not_invented(self) -> None:
        unavailable = unit(970001, 303)
        suppressed = unit(970002, 304)
        suppressed.update({"suppressed": 1, "speed": 0})
        transitioning = unit(970003, 305)
        transitioning.update({"move_state": 1, "speed": 1})
        # The destroyed unit is absent. None of the present units has a listed move action.
        obs = observation([unavailable, suppressed, transitioning], {}, [syn.city(A)])
        revised, base = self.decide(obs), self.baseline(obs)
        self.assertEqual(revised.actions, base.actions)
        self.assertEqual(revised.trace.changes, ())

    def test_malformed_staging_action_fails_closed_to_baseline(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        with mock.patch.object(t9s, "_stage", side_effect=ValueError("planted malformed observation")):
            revised = self.decide(obs)
        self.assertEqual([dict(a) for a in revised.actions], [dict(a) for a in self.baseline(obs).actions])
        self.assertIn("ValueError", revised.trace.addon_error)

    def test_primary_scale_seven_objective_shape_is_deterministic_and_bounded(self) -> None:
        # Regression shape of the previously successful primary scenario: seven objectives and many ground movers.
        cities = [syn.city(coord, value=50 + 10 * (index % 2))
                  for index, coord in enumerate((505, 507, 509, 705, 707, 709, 909))]
        starts = [101 + index for index in range(9)] + [201 + index for index in range(9)]
        ids = [960000 + index for index in range(len(starts))]
        units = [unit(obj_id, start) for obj_id, start in zip(ids, starts)]
        obs = observation(units, {obj_id: {1: None} for obj_id in ids}, cities)
        first, second = self.decide(obs), self.decide(obs)
        self.assertEqual([dict(a) for a in first.actions], [dict(a) for a in second.actions])
        destinations = [a["move_path"][-1] for a in first.actions if a["type"] == 1]
        self.assertTrue(all(destinations.count(city["coord"]) <= t9s.CAPACITY for city in cities))

    def test_agent_replay(self) -> None:
        agent = t9s.StagingAgent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)]).fields)
        memory = agent.memory
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))


if __name__ == "__main__":
    unittest.main()
