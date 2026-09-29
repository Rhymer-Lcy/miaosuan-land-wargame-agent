from __future__ import annotations

import unittest

from miaosuan_agent.boundary import REQUIRED_FIELDS, ContractError, Observation, Origin, Stage
from tests.fixtures import synthetic as syn


def red(**kwargs) -> dict:
    return syn.observation(0, **kwargs)


def obs(raw: dict, origin: Origin = Origin.ENGINE) -> Observation:
    return Observation.from_raw(raw, origin)


def error_of(callable_) -> ContractError:
    try:
        callable_()
    except ContractError as exc:
        return exc
    raise AssertionError("expected ContractError")


class TimeTest(unittest.TestCase):
    def test_valid_time(self) -> None:
        info = obs(red(stage=1, cur_step=3)).time()
        self.assertEqual((info.cur_step, info.stage, info.tick, info.max_time, info.max_step), (3, 1, 1.0, 50, 50))
        self.assertTrue(info.is_deployment)
        self.assertIs(info.known_stage, Stage.DEPLOYMENT)
        play = obs(red(stage=2)).time()
        self.assertTrue(play.is_play)
        self.assertFalse(play.is_deployment)

    def test_unknown_stage_value_is_reported_not_guessed(self) -> None:
        info = obs(red(stage=3)).time()
        self.assertIsNone(info.known_stage)
        self.assertFalse(info.is_deployment or info.is_play)

    def test_missing_time_and_stage(self) -> None:
        raw = red()
        del raw["time"]
        self.assertEqual(error_of(obs(raw).time).path, "observation.time")
        raw = red()
        del raw["time"]["stage"]
        self.assertEqual(error_of(obs(raw).time).path, "observation.time.stage")
        raw = red()
        raw["time"] = [0, 1]
        self.assertEqual(error_of(obs(raw).time).expected, "a mapping")

    def test_wrong_stage_types(self) -> None:
        for value in ("1", 1.0, True, None):
            raw = red()
            raw["time"]["stage"] = value
            with self.subTest(value=value):
                self.assertEqual(error_of(obs(raw).time).path, "observation.time.stage")

    def test_tick_accepts_int_and_extra_time_fields_are_kept(self) -> None:
        raw = red()
        raw["time"]["tick"] = 1
        raw["time"]["future"] = "x"
        info = obs(raw).time()
        self.assertEqual(info.tick, 1.0)
        self.assertIsInstance(info.tick, float)
        self.assertEqual(dict(info.extra), {"future": "x"})


class ValidActionsTest(unittest.TestCase):
    def test_engine_form(self) -> None:
        actions = obs(red()).valid_actions()
        self.assertEqual(list(actions), [syn.RED_UNIT])
        self.assertIsNone(actions[syn.RED_UNIT][1])
        self.assertEqual(actions[syn.RED_UNIT][6][0]["target_state"], 2)
        with self.assertRaises(TypeError):
            actions[syn.RED_UNIT][6][0]["target_state"] = 5  # read-only

    def test_json_form_matches_engine_form(self) -> None:
        engine = obs(red()).valid_actions()
        json_ = obs(syn.json_round_trip(red()), Origin.JSON).valid_actions()
        self.assertEqual({k: dict(v) for k, v in engine.items()}, {k: dict(v) for k, v in json_.items()})

    def test_json_data_read_as_engine_data_fails(self) -> None:
        exc = error_of(obs(syn.json_round_trip(red())).valid_actions)
        self.assertEqual(exc.path, f"observation.valid_actions['{syn.RED_UNIT}']")

    def test_tuple_options_are_accepted(self) -> None:
        raw = red()
        raw["valid_actions"][syn.RED_UNIT][6] = ({"target_state": 2},)
        self.assertEqual(len(obs(raw).valid_actions()[syn.RED_UNIT][6]), 1)

    def test_malformed_values(self) -> None:
        cases = {
            "outer not a mapping": ([], "observation.valid_actions"),
            "inner not a mapping": ({syn.RED_UNIT: [1]}, f"observation.valid_actions[{syn.RED_UNIT}]"),
            "options a dict": ({syn.RED_UNIT: {6: {"target_state": 2}}}, f"observation.valid_actions[{syn.RED_UNIT}][6]"),
            "options a string": ({syn.RED_UNIT: {6: "none"}}, f"observation.valid_actions[{syn.RED_UNIT}][6]"),
            "option not a mapping": ({syn.RED_UNIT: {6: [4]}}, f"observation.valid_actions[{syn.RED_UNIT}][6][0]"),
        }
        for name, (value, path) in cases.items():
            raw = red()
            raw["valid_actions"] = value
            with self.subTest(case=name):
                self.assertEqual(error_of(obs(raw).valid_actions).path, path)


class RoleAndGroupingTest(unittest.TestCase):
    def test_expected_shape(self) -> None:
        seats = obs(red(stage=1)).role_and_grouping()
        info = seats[syn.RED_SEAT]
        self.assertEqual((info.seat, info.role, info.faction, info.operators), (syn.RED_SEAT, 1, 0, (syn.RED_UNIT,)))
        self.assertEqual(info.user_name, "synthetic-red")
        self.assertIs(info.end_deployment, False)
        self.assertIs(obs(red(stage=2)).seat(syn.RED_SEAT).end_deployment, True)

    def test_documented_minimal_record_is_accepted(self) -> None:
        raw = red()
        raw["role_and_grouping_info"] = {syn.RED_SEAT: {"role": 0, "operators": [syn.RED_UNIT]}}
        info = obs(raw).seat(syn.RED_SEAT)
        self.assertIsNone(info.end_deployment)
        self.assertIsNone(info.faction)

    def test_unknown_seat_fields_are_kept(self) -> None:
        raw = red()
        raw["role_and_grouping_info"][syn.RED_SEAT]["team"] = "synthetic"
        self.assertEqual(dict(obs(raw).seat(syn.RED_SEAT).extra), {"team": "synthetic"})

    def test_malformed_records(self) -> None:
        seat_path = f"observation.role_and_grouping_info[{syn.RED_SEAT}]"
        cases = {
            "record not a mapping": (lambda r: r.__setitem__(syn.RED_SEAT, [1]), seat_path),
            "role missing": (lambda r: r[syn.RED_SEAT].pop("role"), f"{seat_path}.role"),
            "operators not a list": (lambda r: r[syn.RED_SEAT].__setitem__("operators", 5), f"{seat_path}.operators"),
            "operator id a string": (lambda r: r[syn.RED_SEAT].__setitem__("operators", ["9"]), f"{seat_path}.operators[0]"),
            "end_deployment an int": (lambda r: r[syn.RED_SEAT].__setitem__("end_deployment", 1), f"{seat_path}.end_deployment"),
        }
        for name, (mutate, path) in cases.items():
            raw = red()
            mutate(raw["role_and_grouping_info"])
            with self.subTest(case=name):
                self.assertEqual(error_of(obs(raw).role_and_grouping).path, path)

    def test_missing_seat(self) -> None:
        exc = error_of(lambda: obs(red()).seat(syn.BLUE_SEAT))
        self.assertIn(str(syn.RED_SEAT), exc.detail)


class CommunicationTest(unittest.TestCase):
    def test_empty_populated_and_absent(self) -> None:
        self.assertEqual(obs(red()).communication(), ())
        message = {"type": 204, "msg_body": "synthetic"}
        self.assertEqual(obs(red(communication=[message])).communication()[0]["msg_body"], "synthetic")
        raw = red()
        del raw["communication"]
        self.assertIsNone(obs(raw).communication())

    def test_invalid_types(self) -> None:
        for value, path in (({}, "observation.communication"), ("text", "observation.communication"),
                            ([["x"]], "observation.communication[0]")):
            raw = red()
            raw["communication"] = value
            with self.subTest(value=value):
                self.assertEqual(error_of(obs(raw).communication).path, path)

    def test_action_feedback_only_where_present(self) -> None:
        self.assertIsNone(obs(red()).action_feedback())
        self.assertEqual(obs(syn.observation(-1)).action_feedback(), ())


class IdentifierTest(unittest.TestCase):
    def test_scenario_id_forms(self) -> None:
        self.assertEqual(obs(red()).scenario_id(), syn.SCENARIO_ID)
        raw = red()
        raw["scenario_id"] = str(syn.SCENARIO_ID)
        self.assertEqual(obs(raw).scenario_id(), syn.SCENARIO_ID)
        for value in ("12a", "-5", " 5", "05", True, 1.0):
            raw = red()
            raw["scenario_id"] = value
            with self.subTest(value=value):
                self.assertEqual(error_of(obs(raw).scenario_id).path, "observation.scenario_id")

    def test_terrain_id_accepts_int_only(self) -> None:
        self.assertEqual(obs(red()).terrain_id(), syn.TERRAIN_ID)
        for value in (str(syn.TERRAIN_ID), True, None):
            raw = red()
            raw["terrain_id"] = value
            with self.subTest(value=value):
                self.assertEqual(error_of(obs(raw).terrain_id).path, "observation.terrain_id")

    def test_absent_identifiers(self) -> None:
        raw = red()
        del raw["scenario_id"], raw["terrain_id"]
        self.assertIsNone(obs(raw).scenario_id())
        self.assertIsNone(obs(raw).terrain_id())


class OperatorsAndRequiredFieldsTest(unittest.TestCase):
    def test_unit_fields_are_preserved(self) -> None:
        unit = obs(red()).operators()[0]
        self.assertEqual(unit.obj_id, syn.RED_UNIT)
        self.assertEqual(unit.fields["synthetic_field"], "preserved")

    def test_malformed_units(self) -> None:
        cases = {
            "missing obj_id": (lambda units: units[0].pop("obj_id"), "observation.operators[0].obj_id"),
            "bool obj_id": (lambda units: units[0].__setitem__("obj_id", True), "observation.operators[0].obj_id"),
            "duplicate obj_id": (lambda units: units.append(dict(units[0])), "observation.operators[1].obj_id"),
            "record not a mapping": (lambda units: units.append(7), "observation.operators[1]"),
        }
        for name, (mutate, path) in cases.items():
            raw = red()
            mutate(raw["operators"])
            with self.subTest(case=name):
                self.assertEqual(error_of(obs(raw).operators).path, path)

    def test_every_required_field_is_enforced(self) -> None:
        self.assertEqual(REQUIRED_FIELDS, {"time", "operators", "passengers", "valid_actions", "role_and_grouping_info"})
        for name in sorted(REQUIRED_FIELDS):
            raw = red()
            del raw[name]
            with self.subTest(field=name):
                self.assertEqual(error_of(obs(raw).validate).path, f"observation.{name}")


class ErrorQualityTest(unittest.TestCase):
    def test_messages_name_path_and_expectation_without_dumping_values(self) -> None:
        raw = red()
        raw["communication"] = {"payload": list(range(100000))}
        exc = error_of(obs(raw).communication)
        self.assertEqual(str(exc), "observation.communication: expected a list or tuple, got dict of length 1")
        raw = red()
        raw["scenario_id"] = "x" * 10000
        message = str(error_of(obs(raw).scenario_id))
        self.assertLess(len(message), 200)
        self.assertIn("...", message)


if __name__ == "__main__":
    unittest.main()
