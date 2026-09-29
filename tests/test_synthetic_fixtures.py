"""The public fixtures stay synthetic, internally consistent and in sync with their builders."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from miaosuan_agent.boundary import Origin, normalize_state
from tests.fixtures import synthetic as syn

STATIC = Path(__file__).resolve().parent / "fixtures" / "synthetic_state_json.json"


class StaticFixtureTest(unittest.TestCase):
    def test_static_json_equals_builder_output(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        self.assertIs(document["synthetic"], True)
        self.assertEqual(document["state"], syn.json_round_trip(syn.state(stage=1)))

    def test_static_json_shows_stringified_keys(self) -> None:
        state = json.loads(STATIC.read_text(encoding="utf-8"))["state"]
        self.assertEqual(sorted(state), ["-1", "0", "1"])
        self.assertEqual(list(state["0"]["valid_actions"]), [str(syn.RED_UNIT)])
        view = normalize_state(state, Origin.JSON)
        self.assertEqual(view.red.operators()[0].obj_id, syn.RED_UNIT)


class SyntheticValuesTest(unittest.TestCase):
    def test_identifiers_are_in_fabricated_ranges(self) -> None:
        view = normalize_state(syn.state(stage=2))
        for observation in (view.red, view.blue, view.global_observation):
            self.assertTrue(all(unit.obj_id >= 900000 for unit in observation.operators()))
            self.assertTrue(set(observation.role_and_grouping()) <= {syn.RED_SEAT, syn.BLUE_SEAT})
            self.assertTrue(all(seat.user_name.startswith("synthetic-")
                                for seat in observation.role_and_grouping().values()))
            self.assertEqual((observation.scenario_id(), observation.terrain_id()), (syn.SCENARIO_ID, syn.TERRAIN_ID))

    def test_every_string_value_is_a_field_name_or_marked_synthetic(self) -> None:
        values = set()
        state = syn.state(stage=1)

        def walk(value):
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, str):
                values.add(value)

        walk(state)
        self.assertTrue(values)
        self.assertTrue(all("synthetic" in value or value == "preserved" for value in values), values)


if __name__ == "__main__":
    unittest.main()
