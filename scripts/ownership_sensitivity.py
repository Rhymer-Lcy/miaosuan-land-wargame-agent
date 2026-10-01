"""Planning sensitivity for the target-ownership design study (``target-ownership-design-1``). Public inputs only.

    python scripts/ownership_sensitivity.py [--check]

Nothing here estimates an incidence or an effect. The unit is the game (a cluster), never a repeated collision
group: q is the share of baseline-v2 games containing at least one S1 component whose first-come owner has a lower
attack level than another claimant. For a grid of q it reports (1) how many unchanged-baseline diagnostic games are
needed to observe enough affected games, and what a diagnostic of the registered layout would show; (2) what a
720-game A/B of the registered layout could resolve, using the registered experiment's own C2/C3 score-margin
standard error as a stated planning assumption, and how much local loss its suite-level non-inferiority test would
hide; (3) the games a mechanism-targeted design would need. ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "target-ownership-design-1" / "sensitivity.json"
SHOOT_RESULTS = REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "results.json"
SCHEMA = "miaosuan-target-ownership-sensitivity/1"
GRID = (0.01, 0.025, 0.05, 0.10, 0.20)
TARGETS = (5, 10, 20)
ASSURANCE = 0.90
GAMES_PER_CONFIGURATION = 15
CONFIGURATIONS = 24  # 8 scenarios x C1-C3, the registered layout
ACTIVE_CONFIGURATIONS = 16  # C2 and C3, where the score margin is informative
NON_INFERIORITY_MARGIN = 10.0
TARGETED_AFFECTED_GAMES = 30
EFFECT_KEYS = ("alternate_target_redirections", "fallback_occupy", "fallback_move", "fallback_none")


def binom_tail_ge(k: int, n: int, p: float) -> float:
    return 1.0 - sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k))


def games_for(k: int, q: float, assurance: float = ASSURANCE) -> int:
    """The smallest number of games with probability at least ``assurance`` of k or more affected games."""
    n = k
    while binom_tail_ge(k, n, q) < assurance:
        n += 1
    return n


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> Any:
    def solve(f: Any, target: float, increasing: bool) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    low = 0.0 if x == 0 else solve(lambda p: binom_tail_ge(x, n, p), alpha / 2, True)
    high = 1.0 if x == n else solve(lambda p: 1.0 - binom_tail_ge(x + 1, n, p), alpha / 2, False)
    return [round(low, 4), round(high, 4)]


def build() -> Dict[str, Any]:
    results = json.loads(SHOOT_RESULTS.read_text(encoding="utf-8"))
    se = results["non_inferiority"]["analytic_se"]
    displaced: Dict[str, int] = {}
    for condition in ("C1", "C2", "C3"):
        total = 0.0
        for key in EFFECT_KEYS:
            for config, stats in results["descriptive"]["C"][key]["configurations"].items():
                if config.endswith(condition):
                    total += stats["mean"] * stats["n"]
        displaced[condition] = int(round(total))
    z = NormalDist().inv_cdf(0.975) + NormalDist().inv_cdf(0.80)
    diagnostic_games = GAMES_PER_CONFIGURATION * CONFIGURATIONS
    arm_games, active_games = diagnostic_games, GAMES_PER_CONFIGURATION * ACTIVE_CONFIGURATIONS
    rows = []
    for q in GRID:
        expected = diagnostic_games * q
        observed = int(round(expected))
        rows.append({
            "q": q,
            "diagnostic_games_for_affected": {str(k): games_for(k, q) for k in TARGETS},
            "registered_layout_diagnostic": {
                "games": diagnostic_games, "expected_affected_games": round(expected, 1),
                "probability_at_least": {str(k): round(binom_tail_ge(k, diagnostic_games, q), 3) for k in TARGETS},
                "exact_95_if_expected_count_observed": clopper_pearson(observed, diagnostic_games)},
            "ab_720": {
                "expected_affected_games_per_arm": round(arm_games * q, 1),
                "expected_affected_active_games_per_arm": round(active_games * q, 1),
                "per_affected_game_effect_for_80pct_at_registered_se": round(z * se / q, 1),
                "per_affected_game_loss_hidden_by_suite_margin": round(NON_INFERIORITY_MARGIN / q, 1)},
            "targeted_games_per_arm_for_affected": {str(TARGETED_AFFECTED_GAMES): math.ceil(TARGETED_AFFECTED_GAMES / q)},
        })
    return {
        "schema": SCHEMA, "study_id": "target-ownership-design-1",
        "unit": "game: share q of baseline-v2 games with at least one S1 component whose first-come owner has a lower "
                "attack level than another claimant; repeated collisions within a game add no independent evidence",
        "assumptions": {
            "assurance": ASSURANCE, "games_per_configuration": GAMES_PER_CONFIGURATION,
            "configurations": CONFIGURATIONS, "active_configurations": ACTIVE_CONFIGURATIONS,
            "registered_c2_c3_margin_se": se, "z_two_sided_5pct_plus_80pct": round(z, 4),
            "non_inferiority_margin": NON_INFERIORITY_MARGIN,
            "planning_only": "the standard error is the registered experiment's whole-suite C2/C3 margin estimate; it "
                             "assumes affected games add no variance and that unaffected games differ by zero in "
                             "expectation; the outcome variance in affected games is unknown"},
        "registered_arm_displaced_units_by_condition": displaced,
        "grid": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("sensitivity identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
