"""EXPLORATORY candidate ``t4-artillery-v3`` (``experiments/t4_artillery_v3.py``). SYNTHETIC observations only."""

from __future__ import annotations

import json
import unittest

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import digest
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t4_artillery_v2 as t4b
from miaosuan_agent.experiments import t4_artillery_v3 as t4c

from tests.fixtures import synthetic as syn
from tests.test_t4_artillery import ART, E1, E2, FIRE, RED, SEAT, artillery, observation, unit


class ArtilleryV3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())

    def decide(self, policy, obs, memory=None):
        return policy.decide(obs, SEAT, RED, memory or ea.AddonMemory())

    def test_targets_near_an_objective_are_excluded(self) -> None:
        for objective, allowed in ((808, False), (408, False), (308, True)):  # distances 0, 4 and 5 from 808
            self.assertEqual(ea.hex_distance(objective, 808) > t4c.OBJECTIVE_ZONE, allowed)
            obs = observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}, cities=[syn.city(objective, flag=1)])
            d = self.decide(t4c.ArtilleryV3Policy(self.costs), obs)
            fired = [a["jm_pos"] for a in d.actions if a["type"] == 8]
            self.assertEqual(fired, [808] if allowed else [])
            if not allowed:
                self.assertIn(("hex excluded: target near an objective", 1), d.trace.skipped)
            self.assertEqual(d.trace.policy, t4c.CANDIDATE_ID)

    def test_equals_version_two_away_from_objectives(self) -> None:
        v2, v3 = t4b.ArtilleryV2Policy(self.costs), t4c.ArtilleryV3Policy(self.costs)
        m2 = m3 = ea.AddonMemory()
        sequence = [
            ([artillery(ART, 101, weapon_cool_time=9), unit(E1, 1, 808), unit(E2, 1, 606, move_path=[607])], 100),
            ([artillery(ART, 101), unit(E2, 1, 607)], 200),
            ([artillery(ART, 101)], 400),
        ]
        orders = 0
        for units, step in sequence:
            obs = observation(units, {ART: FIRE}, cur_step=step, cities=[syn.city(109, flag=-1)])
            d2, d3 = self.decide(v2, obs, m2), self.decide(v3, obs, m3)
            m2, m3 = d2.memory, d3.memory
            self.assertEqual([dict(a) for a in d2.actions], [dict(a) for a in d3.actions])
            self.assertEqual(d2.trace.changes, d3.trace.changes)
            self.assertEqual(d2.memory, d3.memory)
            orders += len(d3.trace.changes)
        self.assertEqual(orders, 2)
        self.assertEqual(json.loads(d3.trace.changes[0])["tier"], t4b.REMEMBERED)

    def test_agent_replay(self) -> None:
        agent = t4c.ArtilleryV3Agent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE},
                               cities=[syn.city(109, flag=-1)]).fields)
        memory = agent.memory
        self.assertEqual([a["type"] for a in agent.step(raw)], [8])
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))


if __name__ == "__main__":
    unittest.main()
