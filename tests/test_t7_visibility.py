"""The documented observation model of the T7 probe's E4 analysis (``evaluation/t7_visibility.py``). SYNTHETIC map."""

from __future__ import annotations

import unittest

from miaosuan_agent.evaluation import t7_visibility as tv

from tests.fixtures import t7_probe_engine as fx


def unit(uid, kind, hex_, sub_type=0):
    return {"obj_id": uid, "type": kind, "sub_type": sub_type, "cur_hex": hex_}


class ModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = tv.MapData(fx.basic_data(), fx.los_table())

    def test_hex_distance_on_a_row_and_symmetry(self) -> None:
        self.assertEqual(tv.hex_distance(1010, 1015), 5)
        self.assertEqual(tv.hex_distance(1000, 1023), 23)
        self.assertEqual(tv.hex_distance(1010, 1110), tv.hex_distance(1110, 1010))
        self.assertEqual(tv.hex_distance(1010, 1010), 0)

    def test_published_distances(self) -> None:
        self.assertEqual(tv.normal_distance(unit(1, 2, 0), unit(2, 1, 0)), 10.0)
        self.assertEqual(tv.normal_distance(unit(1, 1, 0), unit(2, 2, 0)), 25.0)
        self.assertEqual(tv.normal_distance(unit(1, 3, 0, sub_type=6), unit(2, 2, 0)), 25.0)
        self.assertEqual(tv.normal_distance(unit(1, 3, 0, sub_type=5), unit(2, 2, 0)), 2.0)
        self.assertEqual(tv.normal_distance(unit(1, 3, 0, sub_type=7), unit(2, 1, 0)), 2.0)
        self.assertIsNone(tv.normal_distance(unit(1, 2, 0), unit(2, 3, 0)))

    def test_unconcealed_with_terrain_halving_and_the_half_hex_boundary(self) -> None:
        m = tv.MapData(fx.basic_data(forest=[1000]), fx.los_table())
        target = unit(9, 2, 1000)
        self.assertTrue(tv.sees_unconcealed(m, unit(1, 2, 1012), target))     # 12 <= 12.5
        self.assertFalse(tv.sees_unconcealed(m, unit(1, 2, 1013), target))    # 13 > 12.5
        self.assertTrue(tv.sees_unconcealed(self.m, unit(1, 2, 1023), target))  # no forest: 23 <= 25
        infantry = unit(9, 1, 1000)
        self.assertTrue(tv.sees_unconcealed(m, unit(1, 2, 1005), infantry))
        self.assertFalse(tv.sees_unconcealed(m, unit(1, 2, 1006), infantry))

    def test_line_of_sight_and_modes(self) -> None:
        screened = unit(1, 2, 1)  # in the synthetic screen
        self.assertFalse(tv.sees_unconcealed(self.m, screened, unit(9, 2, 5)))
        see = fx.los_table()
        see[0][10, 0, 10, 5] = see[0][10, 5, 10, 0] = False
        m = tv.MapData(fx.basic_data(), see)
        self.assertFalse(tv.sees_unconcealed(m, unit(1, 2, 1000), unit(9, 1, 1005)))  # ground: mode 0
        self.assertTrue(tv.sees_unconcealed(m, unit(1, 3, 1000, sub_type=6), unit(9, 1, 1005)))  # aerial: mode 2


class BandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = tv.MapData(fx.basic_data(elevations={1020: 3}), fx.los_table())

    def label(self, observer_hex, kind, observer_kind=2, sub_type=0):
        return tv.band(self.m, unit(1, observer_kind, observer_hex, sub_type), unit(9, kind, 1000)).band

    def test_infantry_bands(self) -> None:
        self.assertEqual(self.label(1005, 1), tv.INSIDE)
        self.assertEqual(self.label(1006, 1), tv.BETWEEN)
        self.assertEqual(self.label(1010, 1), tv.BETWEEN)
        self.assertEqual(self.label(1011, 1), tv.OUTSIDE)

    def test_vehicle_bands_and_the_boundary(self) -> None:
        self.assertEqual(self.label(1012, 2), tv.INSIDE)
        self.assertEqual(self.label(1013, 2), tv.BOUNDARY)
        self.assertEqual(self.label(1014, 2), tv.BETWEEN)
        self.assertEqual(self.label(1023, 2), tv.BETWEEN)

    def test_no_line_of_sight_and_short_sighted(self) -> None:
        self.assertEqual(tv.band(self.m, unit(1, 2, 1), unit(9, 1, 3)).band, tv.NO_LOS)
        self.assertEqual(self.label(1001, 1, observer_kind=3, sub_type=5), tv.INSIDE)
        self.assertEqual(self.label(1002, 1, observer_kind=3, sub_type=5), tv.BETWEEN)
        self.assertEqual(self.label(1003, 1, observer_kind=3, sub_type=5), tv.OUTSIDE)

    def test_lower_vehicle_flag(self) -> None:
        pair = tv.band(self.m, unit(1, 2, 1020), unit(9, 2, 1000))
        self.assertTrue(pair.lower_vehicle)
        self.assertFalse(tv.band(self.m, unit(1, 2, 1010), unit(9, 2, 1000)).lower_vehicle)
        self.assertIsNone(tv.band(self.m, unit(1, 3, 1020, 6), unit(9, 2, 1000)).lower_vehicle)
        self.assertIsNone(tv.band(self.m, unit(1, 2, 1020), unit(9, 1, 1000)).lower_vehicle)


class ClassifyTest(unittest.TestCase):
    def classify(self, observers, target, elevations=None, forest=()):
        m = tv.MapData(fx.basic_data(elevations=elevations, forest=forest), fx.los_table())
        return tv.classify(m, observers, target)[0]

    def test_each_class(self) -> None:
        squad, tank = unit(9, 1, 1000), unit(8, 2, 1000)
        self.assertEqual(self.classify([], squad), tv.EXPECTED_HIDDEN)
        self.assertEqual(self.classify([unit(1, 2, 1011)], squad), tv.EXPECTED_HIDDEN)
        self.assertEqual(self.classify([unit(1, 2, 1007)], squad), tv.DISCRIMINATING)
        self.assertEqual(self.classify([unit(1, 2, 1007), unit(2, 2, 1004)], squad), tv.EXPECTED_VISIBLE)
        self.assertEqual(self.classify([unit(1, 2, 1007)], squad, forest=[1000]), tv.TERRAIN)
        self.assertEqual(self.classify([unit(1, 2, 1016)], tank), tv.DISCRIMINATING)
        self.assertEqual(self.classify([unit(1, 2, 1013)], tank), tv.AMBIGUOUS_BOUNDARY)
        self.assertEqual(self.classify([unit(1, 2, 1016)], tank, elevations={1016: 2}), tv.EXCEPTION_VISIBLE)
        self.assertEqual(self.classify([unit(1, 3, 1016, 6)], tank), tv.AMBIGUOUS_AIR)
        self.assertEqual(self.classify([unit(1, 3, 1007, 6)], squad), tv.DISCRIMINATING)  # infantry: halving applies

    def test_priorities(self) -> None:
        tank = unit(8, 2, 1000)
        # terrain first, then the exception, then an aerial observer, then a close observer, the boundary, the band
        self.assertEqual(self.classify([unit(1, 2, 1016)], tank, elevations={1016: 2}, forest=[1000]), tv.TERRAIN)
        self.assertEqual(self.classify([unit(1, 2, 1016), unit(2, 3, 1010, 6)], tank, elevations={1016: 2}),
                         tv.EXCEPTION_VISIBLE)
        self.assertEqual(self.classify([unit(1, 2, 1005), unit(2, 3, 1016, 6)], tank), tv.AMBIGUOUS_AIR)
        self.assertEqual(self.classify([unit(1, 2, 1013), unit(2, 2, 1016)], tank), tv.AMBIGUOUS_BOUNDARY)
        self.assertEqual(self.classify([unit(1, 2, 1012), unit(2, 2, 1013)], tank), tv.EXPECTED_VISIBLE)
        # a terrain target with nobody near stays expected hidden
        self.assertEqual(self.classify([unit(1, 2, 1, 0)], tank, forest=[1000]), tv.EXPECTED_HIDDEN)


if __name__ == "__main__":
    unittest.main()
