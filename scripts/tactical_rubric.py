"""Apply the committed tactical selection rubric to the committed scores (``tactical-frontier-1``).

    python scripts/tactical_rubric.py [--check]

Reads ``rubric.json`` (weights, anchors, selection rule and sensitivity checks, committed before scoring) and
``scores.json``; writes ``selection.json``: each family's weighted score, the ranking, the selected family (ties by
L, then R) and, for every declared sensitivity variant, the first family and whether it is the selected one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = REPO_ROOT / "evaluation" / "tactical-frontier-1"
OUT = DIRECTORY / "selection.json"


def rescaled(weights: Dict[str, float], changed: Dict[str, float]) -> Dict[str, float]:
    """``changed`` set as given; every other weight rescaled so the total stays 1."""
    rest = {k: v for k, v in weights.items() if k not in changed}
    free = 1.0 - sum(changed.values())
    scale = free / sum(rest.values())
    return {**{k: v * scale for k, v in rest.items()}, **changed}


def ranking(scores: Dict[str, Dict[str, int]], weights: Dict[str, float]) -> List[Tuple[str, float]]:
    totals = {f: sum(weights[c] * scores[f][c] for c in weights) for f in scores}
    return sorted(totals.items(), key=lambda kv: (-round(kv[1], 9), -scores[kv[0]]["L"], -scores[kv[0]]["R"], kv[0]))


def build() -> Dict[str, object]:
    rubric = json.loads((DIRECTORY / "rubric.json").read_text(encoding="utf-8"))
    raw = json.loads((DIRECTORY / "scores.json").read_text(encoding="utf-8"))["scores"]
    weights = rubric["weights"]
    if abs(sum(weights.values()) - 1.0) > 1e-9 or sorted(raw) != sorted(rubric["families"]):
        raise SystemExit("weights must sum to 1 and every family must be scored")
    scores = {f: {c: int(v[0]) for c, v in raw[f].items()} for f in raw}
    for f, s in scores.items():
        if sorted(s) != sorted(weights) or not all(0 <= v <= 5 for v in s.values()):
            raise SystemExit(f"{f}: every criterion needs an integer score from 0 to 5")
    main = ranking(scores, weights)
    selected = main[0][0]
    variants: Dict[str, Dict[str, float]] = {"equal weights": {c: 1 / len(weights) for c in weights},
                                             "leverage 0.40": rescaled(weights, {"L": 0.40})}
    for c, w in weights.items():
        variants[f"{c} +0.05"] = rescaled(weights, {c: w + 0.05})
        variants[f"{c} -0.05"] = rescaled(weights, {c: w - 0.05})
        variants[f"without {c}"] = rescaled(weights, {c: 0.0})
    sensitivity = {}
    for name, w in variants.items():
        order = ranking(scores, w)
        sensitivity[name] = {"first": order[0][0], "score": round(order[0][1], 4), "second": order[1][0],
                             "selected_stays_first": order[0][0] == selected}
    return {"schema": "miaosuan-tactical-selection/1", "study_id": "tactical-frontier-1",
            "weights": weights, "weighted": {f: round(v, 4) for f, v in main}, "ranking": [f for f, _ in main],
            "selected": selected, "margin_over_second": round(main[0][1] - main[1][1], 4),
            "sensitivity": sensitivity,
            "variants_where_selection_changes": sorted(n for n, v in sensitivity.items() if not v["selected_stays_first"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("selection identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
