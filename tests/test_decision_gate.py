"""The final safety gate rejects every malformed or illegal action, and only those."""

from __future__ import annotations

import json
import unittest

from miaosuan_agent.decision import gate
from miaosuan_agent.decision.routing import Router

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn

SEAT = syn.RED_SEAT


def play_context(**overrides):
    units = overrides.pop("units", [
        syn.unit(ds.UNIT_A, ds.RED, 102, unit_type=ds.VEHICLE),
        syn.unit(ds.UNIT_B, ds.RED, 500, unit_type=ds.VEHICLE),
        syn.unit(ds.UNIT_C, ds.RED, 500, unit_type=ds.INFANTRY),
        syn.unit(ds.UNIT_D, ds.RED, 808, unit_type=ds.VEHICLE, move_path=(807,)),
        syn.unit(ds.ENEMY_A, ds.BLUE, 304),
    ])
    valid = overrides.pop("valid", {
        ds.UNIT_A: {1: None, 2: [ds.shoot(ds.ENEMY_A, ds.GUN, 2)], 5: None},
        ds.UNIT_B: {1: None},
        ds.UNIT_C: {1: None},
        ds.UNIT_D: {1: None},
    })
    return ds.context_of(ds.play_observation(units, valid, roadblocks=(501,), **overrides))


def move(obj_id, path):
    return {"actor": SEAT, "type": 1, "obj_id": obj_id, "move_path": list(path)}


def shoot(obj_id, target, weapon):
    return {"actor": SEAT, "type": 2, "obj_id": obj_id, "target_obj_id": target, "weapon_id": weapon}


def occupy(obj_id):
    return {"actor": SEAT, "type": 5, "obj_id": obj_id}


END = {"actor": SEAT, "type": 333}


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = Router(ds.costs())
        self.play = play_context()
        self.deploy = ds.context_of(ds.play_observation(
            [syn.unit(ds.UNIT_A, ds.RED, 102)], {ds.UNIT_A: {1: None}}, stage=1, ended=False))

    def reason(self, action, context=None, router="default"):
        result = gate.check([action], context or self.play, self.router if router == "default" else router)
        self.assertEqual(len(result.accepted) + len(result.rejected), 1)
        return result.rejected[0].reason if result.rejected else None

    def test_legal_actions_pass_unchanged(self) -> None:
        actions = [move(ds.UNIT_B, (401, 402, 403)), shoot(ds.UNIT_A, ds.ENEMY_A, ds.GUN), move(ds.UNIT_C, (501,))]
        result = gate.check(actions, self.play, self.router)
        self.assertEqual(result.rejected, ())
        self.assertEqual(list(result.accepted), actions)
        self.assertIsNone(self.reason(occupy(ds.UNIT_A)))
        self.assertIsNone(self.reason(END, self.deploy))

    def test_accepted_actions_are_copies(self) -> None:
        action = occupy(ds.UNIT_A)
        result = gate.check([action], self.play, self.router)
        action["obj_id"] = ds.UNIT_B
        self.assertEqual(result.accepted[0]["obj_id"], ds.UNIT_A)

    def test_shape_rejections(self) -> None:
        cases = {
            "not a mapping": ([1, 2], "action is not a mapping"),
            "unknown type": ({"actor": SEAT, "type": 999}, "action type not in the catalog"),
            "bool type": ({"actor": SEAT, "type": True, "obj_id": ds.UNIT_A, "move_path": [103]},
                          "action type not in the catalog"),
            "str type": ({"actor": SEAT, "type": "5", "obj_id": ds.UNIT_A}, "action type not in the catalog"),
            "missing type": ({"actor": SEAT, "obj_id": ds.UNIT_A}, "action type not in the catalog"),
            "extra key": ({**occupy(ds.UNIT_A), "note": 1}, "keys"),
            "missing key": ({"actor": SEAT, "type": 2, "obj_id": ds.UNIT_A, "weapon_id": ds.GUN}, "keys"),
            "other actor": ({**occupy(ds.UNIT_A), "actor": syn.BLUE_SEAT}, "actor is not this seat"),
            "bool actor": ({**occupy(ds.UNIT_A), "actor": True}, "actor is not this seat"),
        }
        for name, (action, expected) in cases.items():
            with self.subTest(case=name):
                self.assertTrue(self.reason(action).startswith(expected), self.reason(action))

    def test_stage_separation(self) -> None:
        self.assertEqual(self.reason(END), "not allowed in stage 2")
        self.assertEqual(self.reason(move(ds.UNIT_A, (103,)), self.deploy), "not allowed in stage 1")
        other = ds.context_of(ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102)], {ds.UNIT_A: {1: None}},
                                                  stage=3))
        self.assertEqual(self.reason(occupy(ds.UNIT_A), other), "not allowed in stage 3")

    def test_deployment_completion(self) -> None:
        ended = ds.context_of(ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 102)], {}, stage=1, ended=True))
        self.assertEqual(self.reason(END, ended), "deployment completion not available")
        result = gate.check([END, dict(END)], self.deploy, self.router)
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual([r.reason for r in result.rejected], ["duplicate deployment completion"])

    def test_unit_rejections(self) -> None:
        cases = {
            "enemy unit": (occupy(ds.ENEMY_A), "obj_id is not a controllable unit"),
            "unknown unit": (occupy(900999), "obj_id is not a controllable unit"),
            "bool unit": ({**occupy(ds.UNIT_A), "obj_id": True}, "obj_id is not a controllable unit"),
            "not listed": (occupy(ds.UNIT_B), "action type not listed for the unit in valid_actions"),
            "shoot not listed": (shoot(ds.UNIT_B, ds.ENEMY_A, ds.GUN),
                                 "action type not listed for the unit in valid_actions"),
            "unlisted option": (shoot(ds.UNIT_A, ds.ENEMY_A, ds.MISSILE), "parameters match no option in valid_actions"),
            "bool option": (shoot(ds.UNIT_A, ds.ENEMY_A, True), "option parameters must be ints"),
            "list option": (shoot(ds.UNIT_A, [ds.ENEMY_A], ds.GUN), "option parameters must be ints"),
        }
        for name, (action, expected) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.reason(action), expected)

    def test_one_action_per_unit(self) -> None:
        result = gate.check([occupy(ds.UNIT_A), shoot(ds.UNIT_A, ds.ENEMY_A, ds.GUN)], self.play, self.router)
        self.assertEqual([a["type"] for a in result.accepted], [5])
        self.assertEqual(result.rejected[0].reason, "second action for the same unit in one step")

    def test_rejected_action_does_not_block_the_unit(self) -> None:
        result = gate.check([shoot(ds.UNIT_A, ds.ENEMY_A, ds.MISSILE), occupy(ds.UNIT_A)], self.play, self.router)
        self.assertEqual([a["type"] for a in result.accepted], [5])

    def test_path_rejections(self) -> None:
        cases = {
            "moving unit": (move(ds.UNIT_D, (806,)), "unit is executing a move, which cannot be changed"),
            "empty path": (move(ds.UNIT_B, ()), "move_path must be a non-empty list of int hexes"),
            "tuple path": ({**move(ds.UNIT_B, ()), "move_path": (401,)}, "move_path must be a non-empty list"),
            "bool hex": ({**move(ds.UNIT_B, ()), "move_path": [True]}, "move_path must be a non-empty list"),
            "str hex": ({**move(ds.UNIT_B, ()), "move_path": ["401"]}, "move_path must be a non-empty list"),
            "repeat": (move(ds.UNIT_B, (401, 402, 401)), "move_path repeats a hex or revisits the start"),
            "start": (move(ds.UNIT_B, (401, 500)), "move_path repeats a hex or revisits the start"),
            "jump": (move(ds.UNIT_B, (402,)), "hex 402 is not a traversable neighbour of 500"),
            "off map": (move(ds.UNIT_A, (103, 9999)), "hex 9999 is not a traversable neighbour of 103"),
            "roadblock": (move(ds.UNIT_B, (501,)), "hex 501 is a roadblock"),
        }
        for name, (action, expected) in cases.items():
            with self.subTest(case=name):
                self.assertTrue(self.reason(action).startswith(expected), self.reason(action))

    def test_roadblocks_stop_vehicles_only(self) -> None:
        self.assertEqual(self.reason(move(ds.UNIT_B, (501,))), "hex 501 is a roadblock")
        self.assertIsNone(self.reason(move(ds.UNIT_C, (501,))))

    def test_path_needs_cost_data(self) -> None:
        self.assertEqual(self.reason(move(ds.UNIT_B, (401,)), router=None), "no movement-cost data to check the path")

    def test_unit_type_without_movement_mode(self) -> None:
        context = play_context(units=[syn.unit(ds.UNIT_A, ds.RED, 102, unit_type=7)], valid={ds.UNIT_A: {1: None}})
        self.assertEqual(self.reason(move(ds.UNIT_A, (103,)), context), "unit type has no documented movement mode")

    def test_rejections_are_json_safe(self) -> None:
        result = gate.check([{"actor": SEAT, "type": object(), "obj_id": [1]}, "text"], self.play, self.router)
        self.assertEqual(len(result.rejected), 2)
        json.dumps([[r.action_type, r.obj_id, r.reason] for r in result.rejected])


if __name__ == "__main__":
    unittest.main()
