from __future__ import annotations

import collections
import enum
import json
import unittest

from miaosuan_agent import typed_json
from tests.fixtures import synthetic as syn


def through_json(value):
    encoded, inexact = typed_json.encode(value)
    return typed_json.decode(json.loads(json.dumps(encoded))), inexact


def same_types(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return list(a) == list(b) and all(type(k) is type(j) for k, j in zip(a, b)) and all(
            same_types(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same_types(x, y) for x, y in zip(a, b))
    return a == b


class RoundTripTest(unittest.TestCase):
    def test_engine_shaped_state_survives_exactly(self) -> None:
        state = syn.state(stage=2, communication=[{"type": 204, "pair": (1, 2)}])
        decoded, inexact = through_json(state)
        self.assertEqual(inexact, [])
        self.assertEqual(decoded, state)
        self.assertTrue(same_types(decoded, state))
        self.assertEqual(list(decoded), [0, 1, -1])

    def test_plain_json_is_not_faithful_but_typed_json_is(self) -> None:
        value = {1: (True, None, 2.5), "k": [-7]}
        self.assertEqual(json.loads(json.dumps(value)), {"1": [True, None, 2.5], "k": [-7]})
        self.assertTrue(same_types(through_json(value)[0], value))


class InexactValueTest(unittest.TestCase):
    def test_subclasses_and_foreign_types_are_reported(self) -> None:
        class Colour(enum.IntEnum):
            RED = 0

        value = {"ordered": collections.OrderedDict(a=1), "enum": Colour.RED, "set": {1}}
        decoded, inexact = through_json(value)
        self.assertEqual(len(inexact), 3)
        self.assertTrue(any("OrderedDict" in path for path in inexact))
        self.assertIsInstance(decoded["enum"], typed_json.Opaque)

    def test_decode_rejects_foreign_objects(self) -> None:
        for bad in ({"a": 1, "b": 2}, {"$unknown": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                typed_json.decode(bad)


if __name__ == "__main__":
    unittest.main()
