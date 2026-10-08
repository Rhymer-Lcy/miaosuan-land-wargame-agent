"""Sprint 24 frozen selection rule (``docs/SPRINT24_TACTICAL_FRONTIER_RESELECTION.md`` sections 8 to 11, ``rubric.json``).

Pure functions over one candidate table: the computed criteria G and P (P lowered by one level when its published
basis is not the trigger itself), the leverage cap for stakes without registered support, the cost economy C, the
eligibility rules (excluded families, closed increments, unidentified semantics, stopped data, session and engineering
caps, the interaction-class rule), the weighted score W, the tie band with its cost-aware tie order, the 27 weight
variants, the judgement-perturbation check and the outcome. Every number (weights, band, minima, caps, thresholds) is
read from ``rubric.json``; nothing here is tuned.

A candidate is a mapping with ``family`` and ``scores`` (integers 0 to 5 for G, L, O, I, M, R, P, E after the
computed and capped values are applied) and the declared facts ``next_sessions``, ``follow_sessions``,
``engineering`` (K), ``interaction`` (X), ``next_offline``, ``conflict_measured``, ``repairs``,
``depends_on_unidentified``, ``uses_stopped_data`` and ``admitted``.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CRITERIA = ("G", "L", "O", "I", "M", "R", "P")
JUDGED = ("L", "O", "I", "M", "R", "E")
EPS = 1e-9
OUTCOMES = ("NEXT_INCREMENT_SELECTED", "FRONTIER_TIE", "NO_READY_INCREMENT")


def level(share: float, thresholds: Sequence[Sequence[float]]) -> int:
    """The anchor level of a share: the first threshold it reaches; a share of 0 is level 0."""
    if share <= 0:
        return 0
    for bound, value in thresholds:
        if share + EPS >= bound:
            return int(value)
    return 0


def basis_level(share: float, thresholds: Sequence[Sequence[float]], basis: str,
                penalties: Mapping[str, int]) -> int:
    """P: the level of the published share, lowered by the basis penalty (never below 0)."""
    if basis not in penalties:
        raise ValueError(f"unknown opportunity basis {basis!r}")
    return max(0, level(share, thresholds) - int(penalties[basis]))


def leverage_cap(stakes: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]) -> int:
    """The highest L a candidate may carry: 5 when at least one cited stake has a registered level and at least the
    rule's number of distinct scenario-sides, otherwise the rule's maximum."""
    strong = set(rule["registered_levels"])
    need = int(rule["min_distinct_scenario_sides"])
    for item in stakes:
        sides = item.get("scenario_sides")
        if item.get("level") in strong and isinstance(sides, int) and sides >= need:
            return 5
    return int(rule["max_without_registered_stake"])


def cost_economy(next_sessions: int, follow_sessions: int, engineering: int) -> int:
    """C, used only by the two cost variants: 5 less the engine sessions to the mechanism answer, less every
    engineering class above 1; never below 0."""
    return max(0, 5 - int(next_sessions) - int(follow_sessions) - max(0, int(engineering) - 1))


def weighted(scores: Mapping[str, int], weights: Mapping[str, float]) -> float:
    return sum(weights[c] * scores[c] for c in weights)


def ineligibility(candidate: Mapping[str, Any], rubric: Mapping[str, Any]) -> List[str]:
    """Every eligibility rule the candidate fails (empty when eligible), in the rubric's order."""
    rules = rubric["eligibility"]
    s = candidate["scores"]
    reasons: List[str] = []
    if candidate["family"] in rules["excluded_families"]:
        reasons.append("excluded family")
    if not candidate.get("admitted", False):
        reasons.append("not admitted")
    if candidate.get("repairs"):
        reasons.append("repairs or restates a closed increment")
    if candidate.get("depends_on_unidentified"):
        reasons.append("endpoint depends on unidentified semantics")
    if candidate.get("uses_stopped_data"):
        reasons.append("uses stopped or withheld data")
    for c, minimum in rules["min"].items():
        if s[c] < minimum:
            reasons.append(f"{c} below {minimum}")
    if candidate["next_sessions"] > rules["max_next_sessions"]:
        reasons.append("next experiment needs too many engine sessions")
    if candidate["follow_sessions"] > rules["max_follow_sessions"]:
        reasons.append("the engine step it leads to needs too many sessions")
    if candidate["engineering"] > rules["max_engineering"]:
        reasons.append("engineering class too high")
    if candidate["interaction"] >= rules["interaction_offline_from"] and not (
            candidate.get("next_offline") and candidate.get("conflict_measured")):
        reasons.append("withholding interaction without an offline conflict measure first")
    return reasons


def tie_key(candidate: Mapping[str, Any]) -> Tuple[int, int, int]:
    """Inside the band: higher E, then fewer engine sessions to the mechanism answer, then lower engineering class."""
    return (-candidate["scores"]["E"], candidate["next_sessions"] + candidate["follow_sessions"],
            candidate["engineering"])


def variant_key(candidate: Mapping[str, Any], family: str) -> Tuple[Any, ...]:
    """The fully ordered tie key of the variants: the main key, then L, then R, then the identifier."""
    return tie_key(candidate) + (-candidate["scores"]["L"], -candidate["scores"]["R"], family)


def main_rule(candidates: Mapping[str, Mapping[str, Any]], rubric: Mapping[str, Any]) -> Dict[str, Any]:
    """Eligibility, ranking by W, the band and its tie order; no robustness."""
    weights = rubric["weights"]
    band = float(rubric["tie_band"])
    w = {f: weighted(c["scores"], weights) for f, c in candidates.items()}
    why = {f: ineligibility(c, rubric) for f, c in candidates.items()}
    ranking = sorted((f for f in candidates if not why[f]), key=lambda f: (-round(w[f], 9), f))
    out: Dict[str, Any] = {"weighted": w, "ineligible": why, "ranking": ranking}
    if not ranking:
        out.update({"outcome": "NO_READY_INCREMENT", "winner": None, "band": [], "tied": []})
        return out
    top = w[ranking[0]]
    in_band = [f for f in ranking if top - w[f] <= band + EPS]
    ordered = sorted(in_band, key=lambda f: (tie_key(candidates[f]), f))
    out["band"] = in_band
    if len(ordered) > 1 and tie_key(candidates[ordered[0]]) == tie_key(candidates[ordered[1]]):
        best = tie_key(candidates[ordered[0]])
        out.update({"outcome": "FRONTIER_TIE", "winner": None,
                    "tied": sorted(f for f in in_band if tie_key(candidates[f]) == best)})
        return out
    out.update({"outcome": "NEXT_INCREMENT_SELECTED", "winner": ordered[0], "tied": []})
    return out


def rescaled(weights: Mapping[str, float], changed: Mapping[str, float]) -> Dict[str, float]:
    """``changed`` set as given; every other weight rescaled so the total stays 1."""
    rest = {k: v for k, v in weights.items() if k not in changed}
    scale = (1.0 - sum(changed.values())) / sum(rest.values())
    return {**{k: v * scale for k, v in rest.items()}, **dict(changed)}


def variants(weights: Mapping[str, float]) -> Dict[str, Dict[str, float]]:
    """The 27 declared variants (section 11): Sprint 18's 25, then C at 0.10 and 0.20."""
    out: Dict[str, Dict[str, float]] = {"equal weights": {c: 1 / len(weights) for c in weights}}
    for c, w in weights.items():
        out[f"{c} +0.05"] = rescaled(weights, {c: w + 0.05})
        out[f"{c} -0.05"] = rescaled(weights, {c: w - 0.05})
        out[f"without {c}"] = rescaled(weights, {c: 0.0})
    out["leverage 0.40"] = rescaled(weights, {"L": 0.40})
    for extra in ("E", "C"):
        for share in (0.10, 0.20):
            out[f"{extra} as a criterion at {share:.2f}"] = rescaled({**weights, extra: 0.0}, {extra: share})
    return out


def first_in_variant(candidates: Mapping[str, Mapping[str, Any]], weights: Mapping[str, float], band: float) -> str:
    totals = {f: weighted(c["scores"], weights) for f, c in candidates.items()}
    best = max(totals.values())
    pool = [f for f, t in totals.items() if best - t <= band + EPS]
    return sorted(pool, key=lambda f: variant_key(candidates[f], f))[0]


def perturbations(candidates: Mapping[str, Mapping[str, Any]], names: Sequence[str],
                  caps: Mapping[str, int]) -> List[Tuple[str, str, int, Dict[str, Mapping[str, Any]]]]:
    """Every single judgement score of the named candidates moved by one point within 0 to 5 (L also within its
    cap); perturbations that change nothing are not counted."""
    out = []
    for name in names:
        for c in JUDGED:
            for step in (-1, 1):
                value = candidates[name]["scores"][c] + step
                ceiling = caps.get(name, 5) if c == "L" else 5
                if not 0 <= value <= ceiling:
                    continue
                changed = {f: dict(v) for f, v in candidates.items()}
                changed[name] = {**changed[name], "scores": {**changed[name]["scores"], c: value}}
                out.append((name, c, step, changed))
    return out


def select(candidates: Mapping[str, Mapping[str, Any]], rubric: Mapping[str, Any],
           caps: Optional[Mapping[str, int]] = None) -> Dict[str, Any]:
    """Apply sections 9 and 10 to the candidate table (scores already computed and capped)."""
    caps = dict(caps or {})
    for f, c in candidates.items():
        bad = [k for k in CRITERIA + ("E", "C") if not isinstance(c["scores"].get(k), int) or not 0 <= c["scores"][k] <= 5]
        if bad:
            raise ValueError(f"{f}: criteria {bad} need an integer from 0 to 5")
    main = main_rule(candidates, rubric)
    result: Dict[str, Any] = {
        "weighted": {f: round(v, 4) for f, v in sorted(main["weighted"].items())},
        "ineligible": {f: v for f, v in sorted(main["ineligible"].items()) if v},
        "eligible": sorted(f for f, v in main["ineligible"].items() if not v),
        "ranking": main["ranking"], "band": main["band"]}
    if main["outcome"] != "NEXT_INCREMENT_SELECTED":
        result.update({"outcome": main["outcome"], "selected": None, "tied": main["tied"], "stage": "main"})
        return result
    selected = main["winner"]
    eligible = {f: candidates[f] for f in main["ranking"]}
    band = float(rubric["tie_band"])
    firsts = {name: first_in_variant(eligible, vw, band) for name, vw in variants(rubric["weights"]).items()}
    stays = sum(1 for f in firsts.values() if f == selected)
    counts: Dict[str, int] = {}
    for f in firsts.values():
        if f != selected:
            counts[f] = counts.get(f, 0) + 1
    challenger = sorted(counts, key=lambda f: (-counts[f], f))[0] if counts else None
    runner_up = next((f for f in main["ranking"] if f != selected), None)
    result.update({"variants": firsts, "variants_total": len(firsts), "selected_first_in": stays,
                   "most_frequent_other_first": challenger, "runner_up": runner_up,
                   "margin_over_runner_up": round(main["weighted"][selected] - main["weighted"][runner_up], 4)
                   if runner_up else None})
    if stays < int(rubric["robust_min_first"]):
        result.update({"outcome": "FRONTIER_TIE", "selected": None, "tied": sorted([selected, challenger]),
                       "stage": "variants"})
        return result
    names = [selected] + ([runner_up] if runner_up else [])
    rows, flips, winners = [], 0, {}
    for name, c, step, changed in perturbations(candidates, names, caps):
        outcome = main_rule(changed, rubric)
        winner = outcome["winner"] if outcome["outcome"] == "NEXT_INCREMENT_SELECTED" else None
        flipped = winner != selected
        if flipped:
            flips += 1
            key = winner or "+".join(outcome["tied"]) or "none"
            winners[key] = winners.get(key, 0) + 1
        rows.append({"candidate": name, "criterion": c, "step": step, "outcome": outcome["outcome"],
                     "winner": winner, "tied": outcome["tied"], "flipped": flipped})
    limit = Fraction(rubric["perturbation"]["max_flip_share"])
    result.update({"perturbations": rows, "perturbations_total": len(rows), "perturbation_flips": flips,
                   "perturbation_flip_share": f"{flips}/{len(rows)}",
                   "perturbation_winners": dict(sorted(winners.items()))})
    if rows and Fraction(flips, len(rows)) > limit:
        result.update({"outcome": "FRONTIER_TIE", "selected": None, "tied": sorted(names), "stage": "perturbation"})
        return result
    result.update({"outcome": "NEXT_INCREMENT_SELECTED", "selected": selected, "tied": [], "stage": "robust"})
    return result
