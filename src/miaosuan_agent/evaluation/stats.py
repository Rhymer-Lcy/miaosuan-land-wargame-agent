"""Small, dependency-free statistics for the repeated-run studies.

Everything here is deterministic. Distribution functions are computed from the regularized
incomplete beta and gamma functions (continued fractions and series, Numerical Recipes style) and
inverted by bisection; the tests compare them with tabulated values. Resampling draws indices as
``int(random() * n)`` from ``random.Random(seed)``, whose output for an integer seed is the same on
every supported Python version (checked by a test), so a registered seed reproduces a bootstrap
exactly. The randomness belongs to the analysis only; nothing here is reachable from a policy.

Percentiles use the nearest-rank method, so every reported quantile is an observed value. Medians
and quartiles use :func:`.metrics.nearest_rank`, as every earlier result did; bootstrap interval
limits use :func:`exact_rank_value`, which computes the rank ceil(p * n / 100) in exact arithmetic
(the float product 2.5 / 100 * 1000 exceeds 25 and would select rank 26).
"""

from __future__ import annotations

import math
import random
from fractions import Fraction
from statistics import NormalDist
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .metrics import nearest_rank

_EPS = 1e-15
_TINY = 1e-300


def mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def variance(values: Sequence[float]) -> Optional[float]:
    """Sample variance (denominator n - 1); ``None`` below two values."""
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    return sum((v - m) ** 2 for v in values) / (n - 1)


def sd(values: Sequence[float]) -> Optional[float]:
    v = variance(values)
    return None if v is None else math.sqrt(v)


def _beta_cf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            return h
    raise ArithmeticError("incomplete beta continued fraction did not converge")


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if not 0.0 <= x <= 1.0:
        raise ValueError("x must be in [0, 1]")
    if x in (0.0, 1.0):
        return x
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_cf(a, b, x) / a
    return 1.0 - front * _beta_cf(b, a, 1.0 - x) / b


def gammainc(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x)."""
    if x < 0 or a <= 0:
        raise ValueError("need a > 0 and x >= 0")
    if x == 0:
        return 0.0
    log_front = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1.0:
        term = total = 1.0 / a
        ap = a
        for _ in range(10000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * _EPS:
                return total * math.exp(log_front)
        raise ArithmeticError("incomplete gamma series did not converge")
    b = x + 1.0 - a
    c, d = 1.0 / _TINY, 1.0 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = b + an / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            return 1.0 - math.exp(log_front) * h
    raise ArithmeticError("incomplete gamma continued fraction did not converge")


def t_cdf(t: float, df: float) -> float:
    tail = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t > 0 else tail


def chi2_cdf(x: float, df: float) -> float:
    return gammainc(df / 2.0, x / 2.0) if x > 0 else 0.0


def _invert(cdf: Callable[[float], float], p: float, low: float, high: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    while cdf(high) < p:
        high *= 2.0
    while cdf(low) > p:
        low = low * 2.0 if low < 0 else low / 2.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if cdf(middle) < p:
            low = middle
        else:
            high = middle
        if high - low < 1e-12 * max(1.0, abs(middle)):
            break
    return (low + high) / 2.0


def t_quantile(p: float, df: float) -> float:
    return _invert(lambda t: t_cdf(t, df), p, -10.0, 10.0)


def chi2_quantile(p: float, df: float) -> float:
    return _invert(lambda x: chi2_cdf(x, df), p, 1e-9, max(10.0, 3.0 * df))


def z_quantile(p: float) -> float:
    return NormalDist().inv_cdf(p)


def t_interval(values: Sequence[float], level: float = 0.95) -> Optional[Tuple[float, float]]:
    """Student-t interval for the mean; ``None`` below two values; zero width when every value is equal."""
    n = len(values)
    if n < 2:
        return None
    m, s = sum(values) / n, sd(values)
    half = t_quantile(0.5 + level / 2.0, n - 1) * s / math.sqrt(n)
    return m - half, m + half


def describe(values: Sequence[float], level: float = 0.95) -> Dict[str, Optional[float]]:
    """n, mean, SD, nearest-rank median and quartiles, min, max, Student-t interval for the mean."""
    interval = t_interval(values, level)
    return {"n": len(values), "mean": mean(values), "sd": sd(values),
            "median": nearest_rank(values, 50), "q1": nearest_rank(values, 25), "q3": nearest_rank(values, 75),
            "min": min(values) if values else None, "max": max(values) if values else None,
            "ci_low": None if interval is None else interval[0], "ci_high": None if interval is None else interval[1]}


def draw(rng: random.Random, n: int) -> int:
    """A uniform index in [0, n) from ``random()`` only (stable across Python versions)."""
    return int(rng.random() * n)


def bootstrap_means(groups: Sequence[Sequence[float]], resamples: int, seed: int) -> List[List[float]]:
    """For each group, ``resamples`` means of resamples drawn with replacement within that group.

    Groups are resampled independently (stratified bootstrap): configuration structure is kept,
    and nothing is resampled across configurations or below the game level.
    """
    rng = random.Random(seed)
    result = []
    for group in groups:
        n = len(group)
        result.append([sum(group[draw(rng, n)] for _ in range(n)) / n for _ in range(resamples)] if n else [])
    return result


def exact_rank_value(values: Sequence[float], percentile: float) -> float:
    """The nearest-rank percentile with the rank computed exactly from the decimal ``percentile``."""
    if not values:
        raise ValueError("no values")
    rank = math.ceil(Fraction(str(percentile)) * len(values) / 100)
    return sorted(values)[max(1, rank) - 1]


def percentile_interval(samples: Sequence[float], level: float = 0.95) -> Tuple[float, float]:
    tail = Fraction(1) - Fraction(str(level))
    low = float(tail / 2 * 100)
    return exact_rank_value(samples, low), exact_rank_value(samples, 100 - low)


def ranks(values: Sequence[float]) -> List[float]:
    """Ranks starting at 1, ties given their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return result


def pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    n = len(x)
    if n < 2 or len(y) != n:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx, syy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    return None if sxx == 0 or syy == 0 else sxy / math.sqrt(sxx * syy)


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    return pearson(ranks(x), ranks(y))


def power_two_sided(effect: float, se: float, alpha: float = 0.05) -> float:
    """Normal-approximation power of a two-sided test of a difference with standard error ``se``."""
    z = z_quantile(1.0 - alpha / 2.0)
    if se == 0:
        return 1.0 if effect != 0 else alpha
    shift = abs(effect) / se
    normal = NormalDist()
    return normal.cdf(shift - z) + normal.cdf(-shift - z)


def minimum_detectable(se: float, alpha: float = 0.05, power: float = 0.8) -> float:
    return (z_quantile(1.0 - alpha / 2.0) + z_quantile(power)) * se
