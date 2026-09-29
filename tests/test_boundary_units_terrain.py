from __future__ import annotations

import unittest

from miaosuan_agent.boundary import ContractError, MoveCosts, MoveMode, Observation, Origin, hex_of
from tests.fixtures import synthetic as syn


def error_of(callable_) -> ContractError:
    try:
        callable_()
    except ContractError as exc:
        return exc
    raise AssertionError("expected ContractError")


def red(**kwargs) -> dict:
    return syn.observation(0, stage=2, **kwargs)


class UnitFieldTest(unittest.TestCase):
    def test_typed_fields(self) -> None:
        raw = red()
        raw["operators"][0]["move_path"] = [103, 104]
        unit = Observation.from_raw(raw).operators()[0]
        self.assertEqual((unit.color, unit.unit_type, unit.sub_type, unit.cur_hex, unit.move_state),
                         (0, 2, 0, syn.RED_HEX, 0))
        self.assertEqual(unit.move_path, (103, 104))

    def test_absent_optional_fields(self) -> None:
        raw = red()
        for name in ("move_path", "move_state", "sub_type"):
            del raw["operators"][0][name]
        unit = Observation.from_raw(raw).operators()[0]
        self.assertIsNone(unit.move_path)
        self.assertIsNone(unit.move_state)
        self.assertIsNone(unit.sub_type)

    def test_malformed_fields_name_their_path(self) -> None:
        cases = {
            "cur_hex missing": (lambda u: u.pop("cur_hex"), "cur_hex", "observation.operators[0].cur_hex"),
            "color a bool": (lambda u: u.__setitem__("color", False), "color", "observation.operators[0].color"),
            "type a string": (lambda u: u.__setitem__("type", "2"), "unit_type", "observation.operators[0].type"),
            "path entry a string": (lambda u: u.__setitem__("move_path", ["103"]), "move_path",
                                    "observation.operators[0].move_path[0]"),
            "path not a list": (lambda u: u.__setitem__("move_path", 103), "move_path",
                                "observation.operators[0].move_path"),
        }
        for name, (mutate, attribute, path) in cases.items():
            raw = red()
            mutate(raw["operators"][0])
            unit = Observation.from_raw(raw).operators()[0]
            with self.subTest(case=name):
                self.assertEqual(error_of(lambda: getattr(unit, attribute)).path, path)


class CitiesAndRoadblocksTest(unittest.TestCase):
    def test_cities(self) -> None:
        raw = red()
        raw["cities"] = [syn.city(505, flag=0, value=9), syn.city(303)]
        cities = Observation.from_raw(raw).cities()
        self.assertEqual([(c.coord, c.flag, c.value) for c in cities], [(505, 0, 9), (303, -1, 7)])
        self.assertEqual(cities[0].name, "synthetic objective")

    def test_cities_absent_or_malformed(self) -> None:
        raw = red()
        del raw["cities"]
        self.assertIsNone(Observation.from_raw(raw).cities())
        raw = red()
        raw["cities"] = [{"coord": "505"}]
        self.assertEqual(error_of(Observation.from_raw(raw).cities).path, "observation.cities[0].coord")

    def test_roadblocks(self) -> None:
        raw = syn.build_observation(units=[syn.unit(syn.RED_UNIT, 0, syn.RED_HEX)], valid_actions={},
                                    seats={}, roadblocks=[304, 305])
        self.assertEqual(Observation.from_raw(raw).roadblocks(), (304, 305))
        del raw["landmarks"]["roadblocks"]
        self.assertEqual(Observation.from_raw(raw).roadblocks(), ())
        del raw["landmarks"]
        self.assertIsNone(Observation.from_raw(raw).roadblocks())

    def test_roadblock_without_hex(self) -> None:
        raw = syn.build_observation(units=[], valid_actions={}, seats={}, roadblocks=[304])
        del raw["landmarks"]["roadblocks"][0]["hex"]
        self.assertEqual(error_of(Observation.from_raw(raw).roadblocks).path, "observation.landmarks.roadblocks[0].hex")


class MoveCostsTest(unittest.TestCase):
    def test_synthetic_grid(self) -> None:
        costs = MoveCosts.from_raw(syn.cost_data(entry_costs={hex_of(2, 3): 2.5}))
        self.assertEqual((costs.rows, costs.cols), (10, 10))
        self.assertEqual(dict(costs.neighbours(MoveMode.VEHICLE, 102)),
                         {n: (2.5 if n == hex_of(2, 3) else 1.0) for n in syn.grid_neighbours(102)})
        self.assertEqual(costs.neighbours(MoveMode.INFANTRY, 202)[203], 2.5)
        self.assertEqual(dict(costs.neighbours(MoveMode.AIR, 9999)), {})
        self.assertTrue(costs.contains(909))
        self.assertFalse(costs.contains(910) or costs.contains(1000) or costs.contains(-1) or costs.contains(True))

    def test_json_origin(self) -> None:
        engine = MoveCosts.from_raw(syn.cost_data())
        json_ = MoveCosts.from_raw(syn.json_round_trip(syn.cost_data()), Origin.JSON)
        self.assertEqual({k: dict(v) for k, v in engine.edges[0].items()},
                         {k: dict(v) for k, v in json_.edges[0].items()})
        with self.assertRaises(ContractError):
            MoveCosts.from_raw(syn.json_round_trip(syn.cost_data()), Origin.ENGINE)

    def test_malformed_cost_data(self) -> None:
        def mutated(change):
            data = syn.cost_data(rows=3, cols=3)
            change(data)
            return data

        cases = {
            "three modes": (mutated(lambda d: d.pop()), "cost_data"),
            "row count differs": (mutated(lambda d: d[2].pop()), "cost_data[2]"),
            "column count differs": (mutated(lambda d: d[1][0].pop()), "cost_data[1][0]"),
            "cell not a mapping": (mutated(lambda d: d[0][0].__setitem__(0, [1])), "cost_data[0][0][0]"),
            "zero cost": (mutated(lambda d: d[0][0][0].__setitem__(1, 0)), "cost_data[0][0][0][1]"),
            "bool cost": (mutated(lambda d: d[0][0][0].__setitem__(1, True)), "cost_data[0][0][0][1]"),
            "infinite cost": (mutated(lambda d: d[0][0][0].__setitem__(1, float("inf"))), "cost_data[0][0][0][1]"),
            "nan cost": (mutated(lambda d: d[0][0][0].__setitem__(1, float("nan"))), "cost_data[0][0][0][1]"),
            "neighbour outside": (mutated(lambda d: d[0][0][0].__setitem__(303, 1)), "cost_data[0][0][0][303]"),
        }
        for name, (data, path) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(error_of(lambda: MoveCosts.from_raw(data)).path, path)


if __name__ == "__main__":
    unittest.main()
