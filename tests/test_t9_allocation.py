"""EXPLORATORY candidate ``t9-capacity-allocation-v1`` (``experiments/t9_allocation.py``). SYNTHETIC observations.

Geometry (uniform cost 1 per hex on the 10 x 10 synthetic grid; costs from the project's router): objective A = 505,
B = 707, C = 909. From 303 / 304 / 305 / 404 / 306 / 201 the cost to A is 3 / 2 / 2 / 2 / 2 / 6 and to B 6 / 5 / 4 /
5 / 4 / 9, so baseline-v2 sends all six to A, and B is within twice the cost of A from 303, 305, 306 and 201 only.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, MoveMode, Observation, Origin
from miaosuan_agent.decision import Memory, digest, gate
from miaosuan_agent.decision.context import build_context
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_allocation as t9
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import synthetic as syn

SEAT, RED = syn.RED_SEAT, 0
A, B, C = 505, 707, 909
START = (303, 304, 305, 404, 306, 201)
IDS = tuple(900501 + k for k in range(len(START)))


def unit(obj_id: int, hex_: int, *, unit_type: int = 2, move_path: Sequence[int] = (), color: int = RED) -> Dict[str, Any]:
    record = syn.unit(obj_id, color, hex_, unit_type=unit_type, move_path=move_path)
    record.update({"speed": 0, "stop": 1})
    return record


def observation(units: Sequence[Dict[str, Any]], listings: Dict[int, Any], cities: List[Dict[str, Any]],
                stage: int = 2) -> Observation:
    own = [u["obj_id"] for u in units if u["color"] == RED]
    raw = syn.build_observation(units=units, valid_actions=listings, stage=stage, cur_step=50,
                                seats={SEAT: syn.seat_record(SEAT, RED, own, True)}, cities=cities)
    return Observation.from_raw(raw, Origin.ENGINE)


def movers(hexes: Sequence[int] = START, ids: Sequence[int] = IDS) -> List[Dict[str, Any]]:
    return [unit(i, h) for i, h in zip(ids, hexes)]


class AllocationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        self.policy = t9.AllocationPolicy(self.costs)
        self.router = Router(self.costs)

    def cost(self, start: int, goal: int) -> float:
        return self.router.shortest_paths(start, MoveMode.VEHICLE).cost[goal]

    def decide(self, obs: Observation):
        return self.policy.decide(obs, SEAT, RED, ea.AddonMemory())

    def v2(self, obs: Observation):
        return ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())

    @staticmethod
    def destinations(decision) -> Dict[int, Optional[int]]:
        return {a["obj_id"]: a["move_path"][-1] for a in decision.actions if a["type"] == 1}

    def test_geometry(self) -> None:
        self.assertEqual([self.cost(h, A) for h in START], [3, 2, 2, 2, 2, 6])
        self.assertEqual([self.cost(h, B) for h in START], [6, 5, 4, 5, 4, 9])

    def test_keeps_four_and_reassigns_the_rest(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        self.assertEqual(set(self.destinations(self.v2(obs)).values()), {A})
        d = self.decide(obs)
        dest = self.destinations(d)
        self.assertEqual([dest[i] for i in IDS], [A, A, A, A, B, B])
        self.assertEqual(self.destinations(self.v2(obs))[IDS[0]], A)
        v2 = self.v2(obs)
        self.assertEqual([dict(a) for a in d.actions[:4]], [dict(a) for a in v2.actions[:4]])
        changes = [json.loads(c) for c in d.trace.changes]
        self.assertEqual([(c["kind"], c["obj_id"], c["from"], c["to"]) for c in changes],
                         [("replace", IDS[4], A, B), ("replace", IDS[5], A, B)])
        context = build_context(obs, SEAT, RED)
        self.policy.baseline.router.targets = frozenset(c.coord for c in context.objectives)
        result = gate.check(list(d.actions), context, self.policy.baseline.router)
        self.assertEqual(len(result.accepted), 6)
        self.assertEqual(result.rejected, ())
        self.assertEqual(d.trace.baseline_trace_sha256, digest(v2.trace))
        self.assertEqual(d.trace.to_dict()["t9"]["skipped"], {"kept: destination under capacity": 4})

    def test_existing_commitments_count(self) -> None:
        en_route = [unit(900601 + k, 102 + k, move_path=[203 + k, 304, 404, A]) for k in range(3)]
        obs = observation(movers() + en_route, {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        d = self.decide(obs)
        # A holds 3: the first move keeps A; 304 and 404 have no objective within the detour bound and wait
        self.assertEqual(self.destinations(d), {IDS[0]: A, IDS[2]: B, IDS[4]: B, IDS[5]: B})
        self.assertEqual([json.loads(c)["obj_id"] for c in d.trace.changes if json.loads(c)["kind"] == "withhold"],
                         [IDS[1], IDS[3]])
        standing = [unit(900611, A)]
        obs = observation(movers() + en_route + standing, {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        self.assertEqual(self.destinations(self.decide(obs)), {IDS[0]: B, IDS[2]: B, IDS[4]: B, IDS[5]: B})

    def test_withholds_when_no_objective_is_under_capacity(self) -> None:
        full_b = [unit(900701 + k, 800 + k, move_path=[B]) for k in range(t9.CAPACITY)]
        obs = observation(movers() + full_b, {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        d = self.decide(obs)
        dest = self.destinations(d)
        self.assertEqual(sorted(dest), sorted(IDS[:4]))
        changes = [json.loads(c) for c in d.trace.changes]
        self.assertEqual([(c["kind"], c["obj_id"]) for c in changes], [("withhold", IDS[4]), ("withhold", IDS[5])])
        self.assertTrue(all(c["commitments"] == t9.CAPACITY for c in changes))

    def test_detour_bound(self) -> None:
        # from 404, A costs 2 and C costs 8, more than twice A's cost
        hexes = (303, 304, 305, 306, 404)
        ids = IDS[:5]
        self.assertGreater(self.cost(404, C), t9.DETOUR * self.cost(404, A))
        obs = observation(movers(hexes, ids), {i: {1: None} for i in ids}, [syn.city(A), syn.city(C)])
        d = self.decide(obs)
        self.assertNotIn(ids[4], self.destinations(d))
        self.assertEqual(json.loads(d.trace.changes[0])["kind"], "withhold")

    def test_value_weighted_choice(self) -> None:
        hexes = (303, 304, 305, 306, 307)
        ids = IDS[:5]
        self.assertEqual((self.cost(307, A), self.cost(307, B), self.cost(307, C)), (3, 4, 6))
        cities = [syn.city(A, value=10), syn.city(B, value=10), syn.city(C, value=100)]
        obs = observation(movers(hexes, ids), {i: {1: None} for i in ids}, cities)
        self.assertEqual(self.destinations(self.v2(obs))[ids[4]], A)
        self.assertEqual(self.destinations(self.decide(obs))[ids[4]], C)
        cities = [syn.city(A, value=10), syn.city(B, value=10), syn.city(C, value=10)]
        obs = observation(movers(hexes, ids), {i: {1: None} for i in ids}, cities)
        self.assertEqual(self.destinations(self.decide(obs))[ids[4]], B)

    def test_air_units_and_held_objectives(self) -> None:
        heli = unit(900801, 302, unit_type=3)
        obs = observation(movers() + [heli], {**{i: {1: None} for i in IDS}, 900801: {1: None}},
                          [syn.city(A), syn.city(B)])
        d = self.decide(obs)
        self.assertEqual(self.destinations(d)[900801], self.destinations(self.v2(obs))[900801])
        self.assertEqual(sum(1 for c in d.trace.changes if json.loads(c)["kind"] == "replace"), 2)
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B, flag=RED)])
        d = self.decide(obs)
        self.assertEqual(sorted(self.destinations(d)), sorted(IDS[:4]))  # B is held: no alternative, two withheld

    def test_gate_rejection_reverts_to_baseline_v2(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        real = gate.check

        def reject_replacements(proposals, context, router):
            result = real(proposals, context, router)
            bad = [p for p in proposals if p.get("type") == 1 and p["move_path"][-1] == B]
            return gate.GateResult(tuple(p for p in result.accepted if p not in bad),
                                   tuple(result.rejected) + tuple(gate.Rejection(1, p["obj_id"], "planted") for p in bad))

        with mock.patch.object(t9.gate, "check", side_effect=reject_replacements):
            d = self.decide(obs)
        self.assertEqual([dict(a) for a in d.actions], [dict(a) for a in self.v2(obs).actions])
        kinds = [json.loads(c)["kind"] for c in d.trace.changes]
        self.assertEqual(kinds, ["replace", "replace", "revert", "revert"])

    def test_untouched_without_moves_or_outside_play(self) -> None:
        obs = observation(movers(), {}, [syn.city(A), syn.city(B)])
        d = self.decide(obs)
        self.assertEqual(d.actions, ())
        self.assertEqual(d.trace.changes, ())
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)], stage=1)
        self.assertEqual([dict(a) for a in self.decide(obs).actions], [dict(a) for a in self.v2(obs).actions])

    def test_agent_replay(self) -> None:
        agent = t9.AllocationAgent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)]).fields)
        memory = agent.memory
        actions = agent.step(raw)
        self.assertEqual(len(actions), 6)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))


if __name__ == "__main__":
    unittest.main()
