from __future__ import annotations

import unittest
from typing import Any, Iterator, Mapping, Tuple

from miaosuan_agent.boundary import ContractError, Origin, normalize_int_key, normalize_int_keyed


class _PairMapping(Mapping):
    """A Mapping that yields the given pairs verbatim, duplicates included (defensive-branch test)."""

    def __init__(self, pairs: Tuple[Tuple[Any, Any], ...]) -> None:
        self._pairs = pairs

    def __getitem__(self, key: Any) -> Any:
        for k, v in self._pairs:
            if k == key:
                return v
        raise KeyError(key)

    def __iter__(self) -> Iterator[Any]:
        return (k for k, _ in self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)

    def items(self):  # type: ignore[override]
        return list(self._pairs)


class EngineOriginTest(unittest.TestCase):
    def test_int_keys_pass_through(self) -> None:
        self.assertEqual(normalize_int_key(-1, Origin.ENGINE, "k"), -1)
        self.assertEqual(normalize_int_keyed({0: "a", 900101: "b"}, Origin.ENGINE, "m"), {0: "a", 900101: "b"})

    def test_string_keys_are_rejected(self) -> None:
        with self.assertRaises(ContractError) as caught:
            normalize_int_keyed({"1": "a"}, Origin.ENGINE, "valid_actions")
        self.assertEqual(caught.exception.path, "valid_actions['1']")
        self.assertIn("int key", caught.exception.expected)

    def test_bool_and_float_keys_are_rejected(self) -> None:
        for key in (True, False, 1.0):
            with self.subTest(key=key), self.assertRaises(ContractError):
                normalize_int_key(key, Origin.ENGINE, "k")


class JsonOriginTest(unittest.TestCase):
    def test_canonical_decimal_strings_are_converted(self) -> None:
        self.assertEqual(normalize_int_keyed({"0": 1, "-1": 2, "900101": 3}, Origin.JSON, "m"),
                         {0: 1, -1: 2, 900101: 3})

    def test_non_canonical_strings_are_rejected(self) -> None:
        for key in ("01", "-0", "+1", " 1", "1 ", "1.0", "", "one", "٣", "1_000"):
            with self.subTest(key=key), self.assertRaises(ContractError):
                normalize_int_key(key, Origin.JSON, "k")

    def test_int_keys_are_rejected_for_json(self) -> None:
        with self.assertRaises(ContractError):
            normalize_int_keyed({1: "a"}, Origin.JSON, "m")


class MixedAndInvalidTest(unittest.TestCase):
    def test_mixed_forms_fail_under_either_origin(self) -> None:
        with self.assertRaises(ContractError) as engine:
            normalize_int_keyed({1: "a", "2": "b"}, Origin.ENGINE, "m")
        self.assertEqual(engine.exception.path, "m['2']")
        with self.assertRaises(ContractError) as json_:
            normalize_int_keyed({"1": "a", 2: "b"}, Origin.JSON, "m")
        self.assertEqual(json_.exception.path, "m[2]")

    def test_duplicate_keys_after_normalization_fail(self) -> None:
        with self.assertRaises(ContractError) as caught:
            normalize_int_keyed(_PairMapping((("5", "a"), ("5", "b"))), Origin.JSON, "m")
        self.assertIn("unique", caught.exception.expected)

    def test_non_mapping_fails(self) -> None:
        for value in ([("1", 2)], "12", None, 3):
            with self.subTest(value=value), self.assertRaises(ContractError):
                normalize_int_keyed(value, Origin.ENGINE, "m")

    def test_input_is_not_modified_and_order_is_kept(self) -> None:
        source = {"3": "c", "1": "a"}
        result = normalize_int_keyed(source, Origin.JSON, "m")
        self.assertEqual(list(result), [3, 1])
        self.assertEqual(source, {"3": "c", "1": "a"})


if __name__ == "__main__":
    unittest.main()
