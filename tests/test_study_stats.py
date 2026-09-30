"""The dependency-free statistics of evaluation/stats.py against tabulated values and edge cases."""

from __future__ import annotations

import math
import random
import unittest

from miaosuan_agent.evaluation import stats


class DistributionTest(unittest.TestCase):
    def test_t_quantiles_match_tables(self) -> None:
        for p, df, expected in ((0.975, 1, 12.706205), (0.975, 4, 2.776445), (0.975, 9, 2.262157),
                                (0.975, 24, 2.063899), (0.95, 30, 1.697261), (0.025, 9, -2.262157)):
            with self.subTest(p=p, df=df):
                self.assertAlmostEqual(stats.t_quantile(p, df), expected, places=5)

    def test_chi_square_quantiles_match_tables(self) -> None:
        for p, df, expected in ((0.10, 9, 4.168159), (0.90, 9, 14.683657), (0.05, 1, 0.00393214),
                                (0.10, 1, 0.0157908), (0.50, 100, 99.334129)):
            with self.subTest(p=p, df=df):
                self.assertAlmostEqual(stats.chi2_quantile(p, df), expected, places=5)

    def test_cdfs(self) -> None:
        self.assertAlmostEqual(stats.t_cdf(0.0, 5), 0.5, places=12)
        self.assertAlmostEqual(stats.t_cdf(2.262157163, 9), 0.975, places=8)
        self.assertAlmostEqual(stats.t_cdf(-2.262157163, 9), 0.025, places=8)
        self.assertEqual(stats.chi2_cdf(0.0, 3), 0.0)
        self.assertAlmostEqual(stats.gammainc(1.0, 2.0), 1 - math.exp(-2.0), places=12)
        self.assertAlmostEqual(stats.betainc(1.0, 1.0, 0.3), 0.3, places=12)
        self.assertEqual((stats.betainc(2.0, 3.0, 0.0), stats.betainc(2.0, 3.0, 1.0)), (0.0, 1.0))
        with self.assertRaises(ValueError):
            stats.t_quantile(1.0, 5)

    def test_normal_power_and_detectable_effect(self) -> None:
        self.assertAlmostEqual(stats.minimum_detectable(1.0), 1.959964 + 0.841621, places=5)
        self.assertAlmostEqual(stats.power_two_sided(stats.minimum_detectable(2.5), 2.5), 0.8, places=3)
        self.assertAlmostEqual(stats.power_two_sided(0.0, 1.0), 0.05, places=9)
        self.assertEqual(stats.power_two_sided(3.0, 0.0), 1.0)
        self.assertEqual(stats.power_two_sided(0.0, 0.0), 0.05)
        self.assertAlmostEqual(stats.power_two_sided(-2.0, 1.0), stats.power_two_sided(2.0, 1.0), places=12)


class DescriptiveTest(unittest.TestCase):
    def test_interval_and_summary(self) -> None:
        low, high = stats.t_interval([1, 2, 3, 4, 5])
        half = 2.776445 * math.sqrt(2.5) / math.sqrt(5)
        self.assertAlmostEqual(low, 3 - half, places=5)
        self.assertAlmostEqual(high, 3 + half, places=5)
        summary = stats.describe([7, 1, 3, 5, 9, 2, 8, 4, 6, 10])
        self.assertEqual((summary["n"], summary["median"], summary["q1"], summary["q3"]), (10, 5, 3, 8))
        self.assertEqual((summary["min"], summary["max"], summary["mean"]), (1, 10, 5.5))
        self.assertAlmostEqual(summary["sd"], math.sqrt(sum((v - 5.5) ** 2 for v in range(1, 11)) / 9))

    def test_zero_variance_and_small_samples(self) -> None:
        self.assertEqual(stats.t_interval([4, 4, 4]), (4.0, 4.0))
        self.assertIsNone(stats.t_interval([4]))
        self.assertIsNone(stats.sd([4]))
        empty = stats.describe([])
        self.assertEqual((empty["n"], empty["mean"], empty["ci_low"], empty["median"]), (0, None, None, None))

    def test_extreme_values_are_kept(self) -> None:
        values = [0.3, 0.3, 0.4, 0.3, 1304.3]
        summary = stats.describe(values)
        self.assertEqual(summary["max"], 1304.3)
        self.assertAlmostEqual(summary["mean"], sum(values) / 5)

    def test_ranks_and_correlation(self) -> None:
        self.assertEqual(stats.ranks([3, 1, 3, 2]), [3.5, 1.0, 3.5, 2.0])
        self.assertAlmostEqual(stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(stats.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertAlmostEqual(stats.spearman([1, 2, 3, 4], [1, 3, 2, 4]), 0.8)
        self.assertIsNone(stats.spearman([1, 2, 3], [5, 5, 5]))


class ResamplingTest(unittest.TestCase):
    def test_generator_output_is_pinned_across_python_versions(self) -> None:
        rng = random.Random(20260930)
        self.assertEqual([rng.random() for _ in range(3)],
                         [0.46278633479390463, 0.6305367777476237, 0.2223250469179695])

    def test_stratified_bootstrap_is_deterministic_and_stays_in_groups(self) -> None:
        groups = [[1.0, 2.0, 3.0], [10.0, 10.0], [], [5.0]]
        first = stats.bootstrap_means(groups, 200, 7)
        self.assertEqual(first, stats.bootstrap_means(groups, 200, 7))
        self.assertNotEqual(first, stats.bootstrap_means(groups, 200, 8))
        self.assertTrue(all(1.0 <= m <= 3.0 for m in first[0]))
        self.assertEqual(set(first[1]), {10.0})
        self.assertEqual((first[2], set(first[3])), ([], {5.0}))
        self.assertEqual(len(first[0]), 200)

    def test_percentile_interval(self) -> None:
        samples = list(range(1, 1001))
        self.assertEqual(stats.percentile_interval(samples), (25, 975))
        self.assertTrue(all(0 <= stats.draw(random.Random(1), 3) < 3 for _ in range(100)))


if __name__ == "__main__":
    unittest.main()
