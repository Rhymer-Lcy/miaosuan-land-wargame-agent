from __future__ import annotations

import unittest

from miaosuan_agent.boundary import ContractError, Observation, Origin, Slot, StateForm, normalize_state
from tests.fixtures import synthetic as syn


def unit_ids(observation: Observation) -> list:
    return [unit.obj_id for unit in observation.operators()]


class MappingFormTest(unittest.TestCase):
    def test_observed_mapping_form(self) -> None:
        view = normalize_state(syn.state())
        self.assertIs(view.form, StateForm.MAPPING)
        self.assertEqual(unit_ids(view.red), [syn.RED_UNIT])
        self.assertEqual(unit_ids(view.blue), [syn.BLUE_UNIT])
        self.assertEqual(unit_ids(view.global_observation), [syn.RED_UNIT, syn.BLUE_UNIT])
        self.assertIs(view.observation(Slot.GLOBAL), view.global_observation)
        self.assertIs(view.for_faction(0), view.red)
        self.assertIs(view.for_faction(1), view.blue)
        self.assertEqual(dict(view.extra_slots), {})

    def test_missing_slot(self) -> None:
        raw = syn.state()
        del raw[-1]
        with self.assertRaises(ContractError) as caught:
            normalize_state(raw)
        self.assertEqual(caught.exception.path, "state")
        self.assertIn("GLOBAL", caught.exception.detail)

    def test_extra_integer_slot_is_preserved(self) -> None:
        raw = syn.state()
        raw[2] = {"note": "future slot"}
        view = normalize_state(raw)
        self.assertEqual(dict(view.extra_slots), {2: {"note": "future slot"}})

    def test_bool_and_mixed_slot_keys_are_rejected(self) -> None:
        raw = syn.state()
        with self.assertRaises(ContractError):
            normalize_state({True: raw[0], 0: raw[1], -1: raw[-1]})
        mixed = syn.json_round_trip(syn.state())
        mixed[1] = mixed.pop("1")
        with self.assertRaises(ContractError) as caught:
            normalize_state(mixed, Origin.JSON)
        self.assertEqual(caught.exception.path, "state[1]")


class SequenceFormTest(unittest.TestCase):
    def test_documented_three_item_list_and_tuple(self) -> None:
        reference = normalize_state(syn.state())
        for raw in (syn.sequence_state(), tuple(syn.sequence_state())):
            with self.subTest(kind=type(raw).__name__):
                view = normalize_state(raw)
                self.assertIs(view.form, StateForm.SEQUENCE)
                self.assertEqual(unit_ids(view.red), unit_ids(reference.red))
                self.assertEqual(unit_ids(view.global_observation), unit_ids(reference.global_observation))

    def test_other_lengths_are_ambiguous(self) -> None:
        full = syn.sequence_state()
        for raw in (full[:2], full + [full[0]], []):
            with self.subTest(length=len(raw)), self.assertRaises(ContractError):
                normalize_state(raw)


class ContainerTypeTest(unittest.TestCase):
    def test_unexpected_container_types(self) -> None:
        for raw in (None, "state", b"state", 3, {0, 1, -1}):
            with self.subTest(kind=type(raw).__name__), self.assertRaises(ContractError):
                normalize_state(raw)

    def test_json_round_trip_needs_json_origin(self) -> None:
        raw = syn.json_round_trip(syn.state())
        self.assertEqual(sorted(raw), ["-1", "0", "1"])
        with self.assertRaises(ContractError) as caught:
            normalize_state(raw, Origin.ENGINE)
        self.assertIn("int key", caught.exception.expected)
        view = normalize_state(raw, Origin.JSON)
        self.assertEqual(unit_ids(view.red), [syn.RED_UNIT])


class ObservationLevelTest(unittest.TestCase):
    def test_eager_validation_names_the_slot(self) -> None:
        raw = syn.state()
        del raw[0]["time"]
        with self.assertRaises(ContractError) as caught:
            normalize_state(raw)
        self.assertEqual(caught.exception.path, "state[0].time")
        view = normalize_state(raw, validate=False)
        with self.assertRaises(ContractError):
            view.red.time()

    def test_unknown_fields_are_preserved(self) -> None:
        raw = syn.state()
        raw[0]["future_field"] = {"anything": [1, 2]}
        view = normalize_state(raw)
        self.assertEqual(view.red.unknown_fields(), frozenset({"future_field"}))
        self.assertEqual(view.red.fields["future_field"], {"anything": [1, 2]})

    def test_non_string_field_names_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            Observation.from_raw({1: "x"})

    def test_invalid_faction(self) -> None:
        view = normalize_state(syn.state())
        for faction in (2, -1, True, "0", None):
            with self.subTest(faction=faction), self.assertRaises(ContractError):
                view.for_faction(faction)


if __name__ == "__main__":
    unittest.main()
