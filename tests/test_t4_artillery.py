"""EXPLORATORY candidate ``t4-artillery-v1`` (``experiments/t4_artillery.py``). SYNTHETIC observations only."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t4_artillery as t4
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import synthetic as syn

SEAT, RED = syn.RED_SEAT, 0
ART, ART2, TANK = 900301, 900302, 900303
E1, E2, E3 = 900401, 900402, 900403


def unit(obj_id: int, color: int, hex_: int, **extra: Any) -> Dict[str, Any]:
    record = syn.unit(obj_id, color, hex_, unit_type=extra.pop("unit_type", 2), move_path=extra.pop("move_path", ()))
    record.update({"sub_type": 0, "speed": 0, "stop": 1, "weapon_cool_time": 0, "value": 5, "blood": 3})
    record.update(extra)
    return record


def artillery(obj_id: int, hex_: int, **extra: Any) -> Dict[str, Any]:
    return unit(obj_id, RED, hex_, sub_type=3, **extra)


def observation(units: Sequence[Dict[str, Any]], listings: Dict[int, Any], *, stage: int = 2, cur_step: int = 100,
                jm_points: Sequence[Dict[str, Any]] = (), cities: Optional[List[Dict[str, Any]]] = None) -> Observation:
    own = [u["obj_id"] for u in units if u["color"] == RED]
    raw = syn.build_observation(units=units, valid_actions=listings, stage=stage, cur_step=cur_step,
                                seats={SEAT: syn.seat_record(SEAT, RED, own, True)},
                                cities=cities if cities is not None else [syn.city(909, flag=RED)])
    raw["jm_points"] = [dict(p) for p in jm_points]
    return Observation.from_raw(raw, Origin.ENGINE)


FIRE = {8: [{"weapon_id": 72}], 6: [{"target_state": 4}], 11: None}


class ArtilleryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        self.policy = t4.ArtilleryPolicy(self.costs)

    def decide(self, obs: Observation, memory: Optional[ea.AddonMemory] = None):
        return self.policy.decide(obs, SEAT, RED, memory or ea.AddonMemory())

    def added(self, decision) -> List[Dict[str, Any]]:
        return [dict(a) for a in decision.actions if a["type"] == t4.INDIRECT]

    def test_fires_at_a_seen_enemy_with_the_listed_weapon(self) -> None:
        obs = observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE})
        d = self.decide(obs)
        self.assertEqual(self.added(d), [{"actor": SEAT, "obj_id": ART, "type": 8, "jm_pos": 808, "weapon_id": 72}])
        self.assertEqual(set(d.actions[0]), t4.ACTION_KEYS)
        changes = [json.loads(c) for c in d.trace.changes]
        self.assertEqual(changes[0]["kind"], "add")
        self.assertEqual(changes[0]["distance"], ea.hex_distance(101, 808))
        v2 = ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())
        self.assertEqual(d.trace.baseline_trace_sha256, digest(v2.trace))
        self.assertEqual(d.trace.policy, t4.CANDIDATE_ID)
        self.assertEqual(list(d.trace.emitted), [(8, ART)])
        payload = d.trace.to_dict()
        self.assertTrue(payload["schema"].endswith("+t4"))
        self.assertIsNone(payload["t4"]["error"])
        self.assertEqual(dict(d.memory.addon), {ART: 100, t4.AIM_KEY_BASE + 808: 100})

    def test_baseline_v2_actions_come_first_and_unchanged(self) -> None:
        tank = unit(TANK, RED, 202)
        obs = observation([artillery(ART, 101), tank, unit(E1, 1, 808)], {ART: FIRE, TANK: {1: None}},
                          cities=[syn.city(505, flag=-1)])
        d = self.decide(obs)
        v2 = ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())
        self.assertTrue(v2.actions)
        self.assertEqual([dict(a) for a in d.actions[:len(v2.actions)]], [dict(a) for a in v2.actions])
        # the tank's move path ends at 505, three hexes from the target, outside the path margin
        self.assertEqual([a["jm_pos"] for a in self.added(d)], [808])

    def test_target_near_an_own_ground_unit_is_excluded(self) -> None:
        for distance_hex in (707, 709, 607):  # distance 1 or 2 from 808
            self.assertLessEqual(ea.hex_distance(distance_hex, 808), t4.SAFE_OWN)
            obs = observation([artillery(ART, 101), unit(TANK, RED, distance_hex), unit(E1, 1, 808)], {ART: FIRE})
            d = self.decide(obs)
            self.assertEqual(self.added(d), [])
            self.assertIn(("hex excluded: target near an own ground unit", 1), d.trace.skipped)
            self.assertIn(("no safe target", 1), d.trace.skipped)
        obs = observation([artillery(ART, 101), unit(TANK, RED, 606), unit(E1, 1, 808)], {ART: FIRE})
        self.assertEqual(ea.hex_distance(606, 808), 3)
        self.assertEqual([a["jm_pos"] for a in self.added(self.decide(obs))], [808])

    def test_target_near_an_own_move_path_is_excluded(self) -> None:
        mover = unit(TANK, RED, 303, move_path=[404, 505, 606, 707], speed=1, stop=0)
        self.assertEqual(min(ea.hex_distance(h, 808) for h in (404, 505, 606, 707)), 1)
        obs = observation([artillery(ART, 101), mover, unit(E1, 1, 808)], {ART: FIRE})
        d = self.decide(obs)
        self.assertEqual(self.added(d), [])
        self.assertIn(("hex excluded: target near an own move path", 1), d.trace.skipped)

    def test_an_own_air_unit_does_not_exclude_but_its_path_does(self) -> None:
        heli = unit(TANK, RED, 707, unit_type=3)
        obs = observation([artillery(ART, 101), heli, unit(E1, 1, 808)], {ART: FIRE})
        self.assertEqual([a["jm_pos"] for a in self.added(self.decide(obs))], [808])

    def test_cooling_weapon_and_recent_order_are_skipped(self) -> None:
        obs = observation([artillery(ART, 101, weapon_cool_time=30), unit(E1, 1, 808)], {ART: FIRE})
        d = self.decide(obs)
        self.assertEqual(self.added(d), [])
        self.assertIn(("weapon cooling", 1), d.trace.skipped)
        first = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808), unit(E2, 1, 909)], {ART: FIRE},
                                        cur_step=100))
        self.assertEqual(len(self.added(first)), 1)
        again = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808), unit(E2, 1, 909)], {ART: FIRE},
                                        cur_step=100 + t4.REFIRE_GAP - 1), first.memory)
        self.assertEqual(self.added(again), [])
        self.assertIn(("ordered recently", 1), again.trace.skipped)
        later = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808), unit(E2, 1, 909)], {ART: FIRE},
                                        cur_step=100 + t4.REFIRE_GAP), first.memory)
        self.assertEqual(len(self.added(later)), 1)

    def test_missing_cool_time_fails_closed(self) -> None:
        art = artillery(ART, 101)
        del art["weapon_cool_time"]
        d = self.decide(observation([art, unit(E1, 1, 808)], {ART: FIRE}))
        self.assertEqual(self.added(d), [])
        self.assertIn(("missing or malformed weapon_cool_time", 1), d.trace.skipped)

    def test_hex_under_own_fire_or_recently_aimed_is_excluded(self) -> None:
        point = {"obj_id": ART2, "color": RED, "weapon_id": 72, "pos": 808, "status": 0, "fly_time": 10, "boom_time": 0}
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}, jm_points=[point]))
        self.assertEqual(self.added(d), [])
        self.assertIn(("hex excluded: target under own fire", 1), d.trace.skipped)
        enemy_point = dict(point, color=1)
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}, jm_points=[enemy_point]))
        self.assertEqual([a["jm_pos"] for a in self.added(d)], [808])
        memory = ea.AddonMemory(addon=((t4.AIM_KEY_BASE + 808, 98),))
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}), memory)
        self.assertEqual(self.added(d), [])
        self.assertIn(("hex excluded: target aimed at recently", 1), d.trace.skipped)

    def test_one_unit_per_hex_and_ranking(self) -> None:
        moving = unit(E1, 1, 808, move_path=[809], speed=1, stop=0)
        stationary = unit(E2, 1, 606)
        obs = observation([artillery(ART, 101), artillery(ART2, 102), moving, stationary], {ART: FIRE, ART2: FIRE})
        d = self.decide(obs)
        self.assertEqual([(a["obj_id"], a["jm_pos"]) for a in self.added(d)], [(ART, 606), (ART2, 808)])
        obs = observation([artillery(ART, 101), artillery(ART2, 102), stationary], {ART: FIRE, ART2: FIRE})
        d = self.decide(obs)
        self.assertEqual([(a["obj_id"], a["jm_pos"]) for a in self.added(d)], [(ART, 606)])
        self.assertIn(("no safe target", 1), d.trace.skipped)
        # objective beats value, value beats count
        obs = observation([artillery(ART, 101), unit(E1, 1, 808, value=50), unit(E2, 1, 606), unit(E3, 1, 909)],
                          {ART: FIRE}, cities=[syn.city(606, flag=1)])
        self.assertEqual([a["jm_pos"] for a in self.added(self.decide(obs))], [606])
        obs = observation([artillery(ART, 101), unit(E1, 1, 808, value=50), unit(E2, 1, 606),
                           unit(E3, 1, 606, move_path=[607], speed=1, stop=0)], {ART: FIRE})
        self.assertEqual([a["jm_pos"] for a in self.added(self.decide(obs))], [808])
        # but two stationary units outrank one of higher value
        obs = observation([artillery(ART, 101), unit(E1, 1, 808, value=50), unit(E2, 1, 606), unit(E3, 1, 606)],
                          {ART: FIRE})
        self.assertEqual([a["jm_pos"] for a in self.added(self.decide(obs))], [606])

    def test_air_enemies_are_not_targets_and_listing_is_required(self) -> None:
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808, unit_type=3)], {ART: FIRE}))
        self.assertEqual(self.added(d), [])
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: {6: [{"target_state": 4}]}}))
        self.assertEqual(self.added(d), [])
        d = self.decide(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: {8: [{"weapon_id": "72"}]}}))
        self.assertEqual(self.added(d), [])
        self.assertIn(("malformed indirect-fire option", 1), d.trace.skipped)

    def test_deployment_stage_is_untouched(self) -> None:
        obs = observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}, stage=1, cur_step=0)
        d = self.decide(obs)
        v2 = ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())
        self.assertEqual([dict(a) for a in d.actions], [dict(a) for a in v2.actions])
        self.assertEqual(d.trace.changes, ())

    def test_own_check(self) -> None:
        listed = {ART: {8: [{"weapon_id": 72}]}}
        good = {"actor": SEAT, "obj_id": ART, "type": 8, "jm_pos": 808, "weapon_id": 72}
        self.assertIsNone(t4.own_check(good, listed, []))
        self.assertEqual(t4.own_check(dict(good, weapon_id=73), listed, []), "weapon not listed for the unit")
        self.assertEqual(t4.own_check(dict(good, extra=1), listed, []), "key set differs")
        self.assertEqual(t4.own_check(dict(good, jm_pos="808"), listed, []),
                         "not an indirect-fire order with int parameters")
        self.assertEqual(t4.own_check(good, listed, [{"obj_id": ART}]), "unit already has an action")

    def test_an_unexpected_error_falls_back_to_baseline_v2(self) -> None:
        obs = observation([artillery(ART, 101), unit(TANK, RED, 202), unit(E1, 1, 808)], {ART: FIRE, TANK: {1: None}},
                          cities=[syn.city(505, flag=-1)])
        with mock.patch.object(t4, "hex_distance", side_effect=RuntimeError("planted")):
            d = self.decide(obs)
        v2 = ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())
        self.assertTrue(v2.actions)
        self.assertEqual([dict(a) for a in d.actions], [dict(a) for a in v2.actions])
        self.assertIn("RuntimeError: planted", d.trace.addon_error)
        self.assertEqual(d.trace.changes, ())

    def test_agent_replay_and_contract_violation(self) -> None:
        agent = t4.ArtilleryAgent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(observation([artillery(ART, 101), unit(E1, 1, 808)], {ART: FIRE}).fields)
        memory = agent.memory
        actions = agent.step(raw)
        self.assertEqual([a["type"] for a in actions], [8])
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        self.assertEqual(agent.step({"operators": "not a list"}), [])
        self.assertIsNotNone(agent.last_trace.error)


if __name__ == "__main__":
    unittest.main()
