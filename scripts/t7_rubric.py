"""T7 design study: score the candidate pool with the frozen rubric and select (``docs/T7_DESIGN.md``, section 9).

    python scripts/t7_rubric.py [--check]

Inputs: ``evaluation/t7-design-1/rubric.json`` (frozen with the protocol) and ``candidates.json`` (the study's public
output). Generality (G) and opportunity cost (C) are computed from the H0 activations by the rubric's anchors; the
other criteria are judgement scores, each with its reason, written below. A cell whose decisive evidence is UNKNOWN is
capped at 2 and flagged. Outputs ``scores.json`` (every score with its reason) and ``selection.json`` (weighted scores,
mandatory conditions, the selection, and the 28 declared sensitivity variants).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "t7-design-1"
CAP = 2

#: Judgement scores: criterion -> (score, flagged UNKNOWN, reason). G and C are computed, not listed here.
JUDGED: Mapping[str, Mapping[str, Tuple[int, bool, str]]] = {
    "A1": {
        "L": (1, False, "documented road speeds exceed normal speed, but none of the 9 H0 orders that reached the saving "
                        "test gains time once the four 75 s transitions are counted (funnel, private)"),
        "O": (4, False, "seat fields, the setup cost graph and documented speeds (class 2)"),
        "E": (2, True, "the march option (target state 1) was never listed for any unit in H0, H1 or H2; whether it is "
                       "listed after a lock is unknown; documented only"),
        "I": (2, False, "a four-action sequence: lock, change state, move, unfold"),
        "S": (1, False, "documented: a marching unit is blocked by any stopped or non-marching unit in its next hex, and "
                        "baseline-v2 moves in columns; a blocked march can freeze units"),
        "M": (5, False, "move_state and weapon_unfold_state are seat fields recorded by the full-step capture"),
    },
    "A2": {
        "L": (3, False, "documented: half observation distance against the unit and favourable direct- and indirect-fire "
                        "target modifiers, effective only when an enemy observes or fires at the unit (conditional)"),
        "O": (4, False, "seat fields, listed options, baseline-v2's own decision on the same observation and the "
                        "candidate's own memory (class 2)"),
        "E": (3, False, "target state 4 is listed for idle stationary ground units in all three populations (observed); "
                        "its effects are documented; acceptance and duration were never observed"),
        "I": (4, False, "one action type, only on units baseline-v2 leaves idle, replacing nothing; needs a 75-step "
                        "memory against repeated orders"),
        "S": (3, False, "a bounded window of at most 75 s without other commands (documented); afterwards moving or "
                        "firing ends concealment at no time cost (documented); no known unsafe case"),
        "M": (5, False, "change_state_remain_time and move_state are seat fields recorded by the full-step capture"),
    },
    "A3": {
        "L": (1, False, "documented double speed for at most two hexes before an objective: at most 144 steps, and no "
                        "H0 order qualifies (funnel, private)"),
        "O": (4, False, "seat fields, listed options and baseline-v2's decision (class 2)"),
        "E": (3, False, "target state 2 is listed for stationary infantry (observed); speed and fatigue documented"),
        "I": (3, False, "a two-step sequence of one mechanism (change state, then move)"),
        "S": (2, True, "the charge transition time is not documented; fatigue 2 stops movement (documented, recovers "
                       "one level per 75 s)"),
        "M": (5, False, "move_state and tire are seat fields recorded by the full-step capture"),
    },
    "B1": {
        "L": (3, False, "a stopped unit can fire after its transition (documented); a shot needs the enemy to stay in "
                        "range (conditional)"),
        "O": (4, False, "seat fields, enemy positions in the seat view and published weapon ranges (class 2)"),
        "E": (2, True, "a stop on a traversing unit was never issued in this project; documented only"),
        "I": (5, False, "one action type, only on moving units, to which baseline-v2 gives no action"),
        "S": (2, False, "Sprint 4: a stop on a unit waiting in front of a full hex freezes it; speed above 0 excludes "
                        "waiting units but not a traversing unit whose next hex fills (448 such unit-steps in the Sprint "
                        "2 split game, docs/PS1_DESIGN.md 11.2), so the known-unsafe case is excluded only by an "
                        "unverified rule"),
        "M": (5, False, "the shoot listing after the transition is a seat field change"),
    },
    "B2": {
        "L": (2, False, "halting outside a seen enemy's documented observation distance has no documented effect on "
                        "losses, occupation or fire; the benefit is hypothesised"),
        "O": (4, False, "seat fields, enemy positions in the seat view and published observation distances (class 2)"),
        "E": (2, True, "a stop on a traversing unit was never issued in this project; documented only"),
        "I": (5, False, "one action type, only on moving units, to which baseline-v2 gives no action"),
        "S": (2, False, "the same known-unsafe stop case as B1, excluded only by an unverified rule"),
        "M": (4, False, "whether the unit was observed needs the opposing view (the all-seeing capture records it)"),
    },
    "C0": {
        "L": (0, False, "no documented benefit of locking without march"),
        "O": (5, False, "seat fields only"),
        "E": (3, False, "action 11 is listed for stationary unfolded vehicles (observed); its effect (no fire until "
                        "unfolded) is documented"),
        "I": (5, False, "one action type on idle units"),
        "S": (3, False, "a bounded window: unfolding takes 75 s (documented)"),
        "M": (5, False, "weapon_unfold_state is a seat field recorded by the full-step capture"),
    },
}


def generality(entry: Mapping[str, Any]) -> Tuple[int, str]:
    n, archetypes = len(entry["scenarios"]), len(entry["archetypes"])
    if n == 8 and archetypes >= 3:
        score = 5
    elif n >= 6:
        score = 4
    elif n >= 4:
        score = 3
    elif n >= 2:
        score = 2
    elif n == 1:
        score = 1
    else:
        score = 0
    return score, f"H0 activations in {n} of 8 scenarios and {archetypes} archetypes"


def opportunity(entry: Mapping[str, Any]) -> Tuple[int, bool, str]:
    n, exposed = entry["activations"], entry["exposure"]
    if n == 0:
        return CAP, True, "no H0 activation, so the exposure is unknown"
    share = exposed / n
    for limit, score in ((0.01, 5), (0.05, 4), (0.15, 3), (0.30, 2)):
        if share <= limit:
            return score, False, f"exposure {exposed} of {n} H0 activations"
    return 1, False, f"exposure {exposed} of {n} H0 activations"


def scores(rubric: Mapping[str, Any], candidates: Mapping[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for cand in rubric["candidate_pool_order"]:
        h0 = candidates["summary"]["H0"][cand]
        row: Dict[str, Dict[str, Any]] = {}
        g, why = generality(h0)
        row["G"] = {"score": g, "unknown": False, "reason": why}
        c, unknown, why = opportunity(h0)
        row["C"] = {"score": c, "unknown": unknown, "reason": why}
        for crit, (score, unknown, why) in JUDGED[cand].items():
            if unknown and score > CAP:
                raise SystemExit(f"{cand} {crit}: an UNKNOWN cell above the cap")
            row[crit] = {"score": score, "unknown": unknown, "reason": why}
        if set(row) != set(rubric["criteria"]):
            raise SystemExit(f"{cand}: criteria {sorted(row)} do not match the rubric")
        out[cand] = row
    return out


def weighted(row: Mapping[str, Mapping[str, Any]], weights: Mapping[str, float], unknown_value: Optional[int] = None) -> float:
    total = 0.0
    for crit, w in weights.items():
        cell = row[crit]
        value = unknown_value if (unknown_value is not None and cell["unknown"]) else cell["score"]
        total += w * value
    return round(total, 4)


def eligible(row: Mapping[str, Mapping[str, Any]], rubric: Mapping[str, Any]) -> bool:
    return all(row[c]["score"] >= rubric["criteria"][c]["mandatory_minimum"]
               for c in rubric["criteria"] if "mandatory_minimum" in rubric["criteria"][c])


def pick(table: Mapping[str, Mapping[str, Mapping[str, Any]]], rubric: Mapping[str, Any], weights: Mapping[str, float],
         unknown_value: Optional[int] = None) -> Optional[str]:
    order = rubric["candidate_pool_order"]
    pool = [c for c in order if eligible(table[c], rubric)]
    if not pool:
        return None
    return max(pool, key=lambda c: (weighted(table[c], weights, unknown_value), table[c]["L"]["score"],
                                    table[c]["S"]["score"], table[c]["I"]["score"], -order.index(c)))


def variants(base: Mapping[str, float]) -> List[Tuple[str, Dict[str, float], Optional[int]]]:
    out: List[Tuple[str, Dict[str, float], Optional[int]]] = []
    keys = list(base)
    out.append(("equal weights", {k: 1 / len(keys) for k in keys}, None))
    for k in keys:
        for delta in (0.05, -0.05):
            w = dict(base)
            w[k] = base[k] + delta
            rest = sum(v for j, v in base.items() if j != k)
            for j in keys:
                if j != k:
                    w[j] = base[j] * (1 - w[k]) / rest
            out.append((f"{k} {'+' if delta > 0 else '-'}0.05", w, None))
    for k in keys:
        rest = sum(v for j, v in base.items() if j != k)
        out.append((f"without {k}", {j: (0.0 if j == k else base[j] / rest) for j in keys}, None))
    w = dict(base)
    w["L"] = 0.40
    rest = sum(v for j, v in base.items() if j != "L")
    for j in keys:
        if j != "L":
            w[j] = base[j] * 0.60 / rest
    out.append(("leverage 0.40", w, None))
    out.append(("unknown cells at 0", dict(base), 0))
    out.append(("unknown cells at 5", dict(base), 5))
    return out


def build() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rubric = json.loads((OUT / "rubric.json").read_text(encoding="utf-8"))
    candidates = json.loads((OUT / "candidates.json").read_text(encoding="utf-8"))
    weights = {k: v["weight"] for k, v in rubric["criteria"].items()}
    table = scores(rubric, candidates)
    base = {c: {"weighted": weighted(table[c], weights), "eligible": eligible(table[c], rubric),
                "failed_mandatory": [k for k, v in rubric["criteria"].items() if "mandatory_minimum" in v
                                     and table[c][k]["score"] < v["mandatory_minimum"]]}
            for c in rubric["candidate_pool_order"]}
    selected = pick(table, rubric, weights)
    runs = []
    for name, w, unknown in variants(weights):
        if abs(sum(w.values()) - 1.0) > 1e-9:
            raise SystemExit(f"variant {name} weights do not sum to 1")
        runs.append({"variant": name, "selected": pick(table, rubric, w, unknown),
                     "highest_overall": max(rubric["candidate_pool_order"],
                                            key=lambda c: weighted(table[c], w, unknown))})
    if len(runs) != rubric["sensitivity"]["variants"]:
        raise SystemExit("variant count differs from the rubric")
    first = sum(1 for r in runs if r["selected"] == selected)
    selection = {"schema": "miaosuan-t7-selection/1", "study_id": "t7-design-1", "base": base, "selected": selected,
                 "sensitivity": {"variants": len(runs), "selected_first_in": first,
                                 "fragile": first < rubric["sensitivity"]["fragile_if_first_in_fewer_than"],
                                 "runs": runs}}
    scored = {"schema": "miaosuan-t7-scores/1", "study_id": "t7-design-1", "cap_for_unknown": CAP, "scores": table}
    return scored, selection


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    scored, selection = build()
    texts = {OUT / "scores.json": dump(scored), OUT / "selection.json": dump(selection)}
    if args.check:
        same = all(p.exists() and p.read_text(encoding="utf-8") == t for p, t in texts.items())
        print("outputs identical" if same else "MISMATCH")
        return 0 if same else 1
    for path, text in texts.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
    print(json.dumps({c: v["weighted"] for c, v in selection["base"].items()}), "selected:", selection["selected"],
          "first in", selection["sensitivity"]["selected_first_in"], "of", selection["sensitivity"]["variants"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
