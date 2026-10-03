"""EXPLORATORY candidate ``t4-artillery-v2`` (``experiments/t4_artillery_v2.py``). SYNTHETIC observations only."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List
from unittest import mock

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t4_artillery_v2 as t4b
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import synthetic as syn
from tests.test_t4_artillery import ART, ART2, E1, E2, FIRE, RED, SEAT, TANK, artillery, observation, unit


class ArtilleryV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        self.policy = t4b.ArtilleryV2Policy(self.costs)

    def decide(self, obs, memory=None):
        return self.policy.decide(obs, SEAT, RED, memory or ea.AddonMemory())

    @staticmethod
    def added(decision) -> List[Dict[str, Any]]:
        return [dict(a) for a in decision.actions if a["type"] == 8]

    def sighting(self, step: int = 100, **enemy: Any):
        """A decision in which E1 is seen and the artillery is cooling, so it only updates the memory."""
        return self.decide(observation([artillery(ART, 101, weapon_cool_time=50), unit(E1, 1, 808, **enemy)],
                                       {ART: FIRE}, cur_step=step))

    def test_fires_at_a_remembered_stationary_enemy(self) -> None:
        seen = self.sighting()
        self.assertEqual(self.added(seen), [])
        self.assertIn((t4b.ENEMY_KEY_BASE + E1, 100 * t4b.HEX_SPAN + 808), seen.memory.addon)
        later = self.decide(observation([artillery(ART, 101)], {ART: FIRE}, cur_step=300), seen.memory)
        self.assertEqual(self.added(later), [{"actor": SEAT, "obj_id": ART, "type": 8, "jm_pos": 808, "weapon_id": 72}])
        self.assertEqual(json.loads(later.trace.changes[0])["tier"], t4b.REMEMBERED)

    def test_memory_expires_and_moving_units_are_forgotten(self) -> None:
        seen = self.sighting()
        late = self.decide(observation([artillery(ART, 101)], {ART: FIRE}, cur_step=100 + t4b.REMEMBER), seen.memory)
        self.assertEqual(self.added(late), [])
        self.assertNotIn(t4b.ENEMY_KEY_BASE + E1, dict(late.memory.addon))
        moving = self.decide(observation([artillery(ART, 101, weapon_cool_time=50),
                                          unit(E1, 1, 808, move_path=[809], speed=1, stop=0)], {ART: FIRE},
                                         cur_step=150), seen.memory)
        self.assertNotIn(t4b.ENEMY_KEY_BASE + E1, dict(moving.memory.addon))
        after = self.decide(observation([artillery(ART, 101)], {ART: FIRE}, cur_step=200), moving.memory)
        self.assertEqual(self.added(after), [])

    def test_a_unit_in_sight_replaces_its_memory(self) -> None:
        seen = self.sighting()
        moved = self.decide(observation([artillery(ART, 101), unit(E1, 1, 606)], {ART: FIRE}, cur_step=200), seen.memory)
        self.assertEqual([a["jm_pos"] for a in self.added(moved)], [606])
        self.assertIn((t4b.ENEMY_KEY_BASE + E1, 200 * t4b.HEX_SPAN + 606), moved.memory.addon)

    def test_tiers_seen_stationary_then_remembered_then_moving(self) -> None:
        seen = self.decide(observation([artillery(ART, 101, weapon_cool_time=50), unit(E2, 1, 909)], {ART: FIRE},
                                       cur_step=100))
        units = [artillery(ART, 101), artillery(ART2, 102), artillery(900304, 103),
                 unit(E1, 1, 808, move_path=[809], speed=1, stop=0), unit(900404, 1, 606)]
        d = self.decide(observation(units, {ART: FIRE, ART2: FIRE, 900304: FIRE}, cur_step=200), seen.memory)
        self.assertEqual([(a["obj_id"], a["jm_pos"]) for a in self.added(d)], [(ART, 606), (ART2, 909), (900304, 808)])
        self.assertEqual([json.loads(c)["tier"] for c in d.trace.changes],
                         [t4b.SEEN_STATIONARY, t4b.REMEMBERED, t4b.SEEN_MOVING])

    def test_exploding_hex_is_a_target_and_a_flying_one_is_not(self) -> None:
        point = {"obj_id": ART2, "color": RED, "weapon_id": 72, "pos": 808, "status": 1, "fly_time": 150, "boom_time": 9}
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}, jm_points=[point]))
        self.assertEqual([a["jm_pos"] for a in self.added(d)], [808])
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE},
                                    jm_points=[dict(point, status=0)]))
        self.assertEqual(self.added(d), [])
        self.assertIn(("hex excluded: target under an own round in flight", 1), d.trace.skipped)

    def test_version_one_safety_rules_hold(self) -> None:
        seen = self.sighting()
        near = self.decide(observation([artillery(ART, 101), unit(TANK, RED, 707)], {ART: FIRE}, cur_step=300),
                           seen.memory)
        self.assertEqual(self.added(near), [])
        self.assertIn(("hex excluded: target near an own ground unit", 1), near.trace.skipped)
        cooling = self.decide(observation([artillery(ART, 101, weapon_cool_time=3), unit(E1, 1, 808)], {ART: FIRE}))
        self.assertIn(("weapon cooling", 1), cooling.trace.skipped)

    def test_baseline_v2_first_and_fallback(self) -> None:
        obs = observation([artillery(ART, 101), unit(TANK, RED, 202), unit(E1, 1, 808)], {ART: FIRE, TANK: {1: None}},
                          cities=[syn.city(505, flag=-1)])
        d = self.decide(obs)
        v2 = ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())
        self.assertTrue(v2.actions)
        self.assertEqual([dict(a) for a in d.actions[:len(v2.actions)]], [dict(a) for a in v2.actions])
        self.assertEqual(d.trace.baseline_trace_sha256, digest(v2.trace))
        with mock.patch.object(t4b, "hex_distance", side_effect=RuntimeError("planted")):
            failed = self.decide(obs)
        self.assertEqual([dict(a) for a in failed.actions], [dict(a) for a in v2.actions])
        self.assertIn("RuntimeError: planted", failed.trace.addon_error)
        self.assertEqual(failed.trace.policy, t4b.CANDIDATE_ID)

    def test_agent_replay(self) -> None:
        agent = t4b.ArtilleryV2Agent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}).fields)
        memory = agent.memory
        self.assertEqual([a["type"] for a in agent.step(raw)], [8])
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))


if __name__ == "__main__":
    unittest.main()
