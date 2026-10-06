"""Sprint 18 frozen selection rule (``docs/SPRINT18_FRONTIER_RESET.md`` sections 9 to 11, ``rubric.json``).

Pure functions: computed criteria (G, P) from a share, the weighted score W, eligibility, the tie band with E as the
tie-breaker, the 25 sensitivity variants with their tie order, the robustness rule and the outcome. The rubric's
numbers (weights, band, minima, the robustness threshold) are read from ``rubric.json``; nothing here is tuned.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CRITERIA = ("G", "L", "O", "I", "M", "R", "P")
EPS = 1e-9


def level(share: float, thresholds: Sequence[Sequence[float]]) -> int:
    """The anchor level of a share: the first threshold it reaches; a share of 0 is level 0 (absent / none)."""
    if share <= 0:
        return 0
    for bound, value in thresholds:
        if share + EPS >= bound:
            return int(value)
    return 0


def weighted(scores: Mapping[str, int], weights: Mapping[str, float]) -> float:
    return sum(weights[c] * scores[c] for c in weights)


def eligible(scores: Mapping[str, int], minima: Mapping[str, int], family: str, excluded: Sequence[str]) -> bool:
    return family not in excluded and all(scores[c] >= m for c, m in minima.items())


def rescaled(weights: Mapping[str, float], changed: Mapping[str, float]) -> Dict[str, float]:
    """``changed`` set as given; every other weight rescaled so the total stays 1."""
    rest = {k: v for k, v in weights.items() if k not in changed}
    scale = (1.0 - sum(changed.values())) / sum(rest.values())
    return {**{k: v * scale for k, v in rest.items()}, **dict(changed)}


def variants(weights: Mapping[str, float]) -> Dict[str, Dict[str, float]]:
    """The 25 declared variants (section 11); E enters only the last two."""
    out: Dict[str, Dict[str, float]] = {"equal weights": {c: 1 / len(weights) for c in weights}}
    for c, w in weights.items():
        out[f"{c} +0.05"] = rescaled(weights, {c: w + 0.05})
        out[f"{c} -0.05"] = rescaled(weights, {c: w - 0.05})
        out[f"without {c}"] = rescaled(weights, {c: 0.0})
    out["leverage 0.40"] = rescaled(weights, {"L": 0.40})
    out["E as a criterion at 0.10"] = rescaled({**weights, "E": 0.0}, {"E": 0.10})
    out["E as a criterion at 0.20"] = rescaled({**weights, "E": 0.0}, {"E": 0.20})
    return out


def first_in_variant(candidates: Mapping[str, Mapping[str, int]], weights: Mapping[str, float],
                     band: float) -> str:
    """The first candidate under ``weights``: within ``band`` of the best W, higher E, then L, then R, then id."""
    totals = {f: weighted(s, weights) for f, s in candidates.items()}
    best = max(totals.values())
    pool = [f for f, t in totals.items() if best - t <= band + EPS]
    return sorted(pool, key=lambda f: (-candidates[f]["E"], -candidates[f]["L"], -candidates[f]["R"], f))[0]


def select(scores: Mapping[str, Mapping[str, int]], rubric: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply section 10 to integer scores (G..P and E for every family)."""
    weights = rubric["weights"]
    band = float(rubric["tie_band"])
    minima = rubric["eligibility"]["min"]
    excluded = rubric["eligibility"]["excluded_families"]
    for f, s in scores.items():
        missing = [c for c in CRITERIA + ("E",) if not isinstance(s.get(c), int) or not 0 <= s[c] <= 5]
        if missing:
            raise ValueError(f"{f}: criteria {missing} need an integer from 0 to 5")
    w = {f: weighted(s, weights) for f, s in scores.items()}
    ok = {f: eligible(s, minima, f, excluded) for f, s in scores.items()}
    ranking = sorted((f for f in scores if ok[f]), key=lambda f: (-round(w[f], 9), f))
    result: Dict[str, Any] = {"weighted": {f: round(v, 4) for f, v in sorted(w.items())},
                              "eligible": dict(sorted(ok.items())), "ranking": ranking}
    if not ranking:
        result.update({"outcome": "NO_READY_FAMILY", "selected": None, "band": [], "tied": []})
        return result
    top = w[ranking[0]]
    in_band = [f for f in ranking if top - w[f] <= band + EPS]
    best_e = max(scores[f]["E"] for f in in_band)
    winners = sorted(f for f in in_band if scores[f]["E"] == best_e)
    result["band"] = in_band
    if len(winners) > 1:
        result.update({"outcome": "FRONTIER_TIE", "selected": None, "tied": winners})
        return result
    selected = winners[0]
    eligible_scores = {f: scores[f] for f in ranking}
    firsts = {name: first_in_variant(eligible_scores, vw, band) for name, vw in variants(weights).items()}
    stays = sum(1 for f in firsts.values() if f == selected)
    others = [f for f in firsts.values() if f != selected]
    challenger: Optional[str] = None
    if others:
        counts: Dict[str, int] = {}
        for f in others:
            counts[f] = counts.get(f, 0) + 1
        challenger = sorted(counts, key=lambda f: (-counts[f], f))[0]
    result.update({"variants": firsts, "variants_total": len(firsts), "selected_first_in": stays,
                   "most_frequent_other_first": challenger})
    if stays < int(rubric["robust_min_first"]):
        result.update({"outcome": "FRONTIER_TIE", "selected": None, "tied": sorted([selected, challenger])})
        return result
    second = next((f for f in ranking if f != selected), None)
    result.update({"outcome": "NEXT_FAMILY_SELECTED", "selected": selected, "tied": [], "runner_up": second,
                   "margin_over_runner_up": round(w[selected] - w[second], 4) if second else None})
    return result
