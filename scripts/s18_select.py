"""Apply Sprint 18's frozen rubric to the scored increments (``docs/SPRINT18_FRONTIER_RESET.md`` sections 9 to 11).

    python scripts/s18_select.py [--check]

Reads ``rubric.json`` (registered before scoring), ``scores.json`` (judgement scores with reasons and, for G and P, the
public source each is computed from), ``census.json``, ``admission.json``, Sprint 1's census and the ownership design
study's analysis; computes G and P from their sources with the rubric's thresholds; applies the eligibility, tie band,
E tie-break, sensitivity variants and robustness rule (``evaluation/s18_selection.py``); writes ``selection.json``.
Every input is public, so ``--check`` runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s18_selection as sel  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / "s18-frontier-reset"
OUT = DIRECTORY / "selection.json"
SOURCES = {"census": DIRECTORY / "census.json", "admission": DIRECTORY / "admission.json",
           "sprint1": REPO_ROOT / "evaluation" / "tactical-frontier-1" / "census.json",
           "ownership": REPO_ROOT / "evaluation" / "target-ownership-design-1" / "analysis.json"}
SCHEMA = "miaosuan-s18-selection/1"


def lookup(data: Any, key: Sequence[str]) -> Any:
    for part in key:
        data = data[part]
    return data


def computed(spec: Mapping[str, Any], sources: Mapping[str, Any], thresholds: Any) -> Dict[str, Any]:
    data = sources[spec["file"]]
    count = lookup(data, spec["key"])
    of = spec["of"] if "of" in spec else lookup(data, spec["of_key"])
    if not isinstance(count, int) or not isinstance(of, int) or of <= 0 or not 0 <= count <= of:
        raise SystemExit(f"unusable source {spec}")
    return {"count": count, "of": of, "share": round(count / of, 4), "score": sel.level(count / of, thresholds)}


def build() -> Dict[str, Any]:
    rubric = json.loads((DIRECTORY / "rubric.json").read_text(encoding="utf-8"))
    raw = json.loads((DIRECTORY / "scores.json").read_text(encoding="utf-8"))["candidates"]
    sources = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in SOURCES.items()}
    excluded = set(rubric["eligibility"]["excluded_families"])
    if excluded & set(raw):
        raise SystemExit(f"excluded families scored: {sorted(excluded & set(raw))}")
    table: Dict[str, Dict[str, Any]] = {}
    scores: Dict[str, Dict[str, int]] = {}
    for family, entry in sorted(raw.items()):
        g = computed(entry["G"], sources, rubric["criteria"]["G"]["thresholds"])
        p = computed(entry["P"], sources, rubric["criteria"]["P"]["thresholds"])
        s = {"G": g["score"], "P": p["score"]}
        for c in ("L", "O", "I", "M", "R", "E"):
            value, reason = entry[c]
            if not isinstance(reason, str) or not reason:
                raise SystemExit(f"{family} {c}: every judgement score needs a reason")
            s[c] = value
        scores[family] = s
        table[family] = {"increment": entry["increment"], "scores": s, "G_source": g, "P_source": p,
                         "reasons": {c: entry[c][1] for c in ("L", "O", "I", "M", "R", "E")}}
    result = sel.select(scores, rubric)
    return {"schema": SCHEMA, "study_id": "s18-frontier-reset", "weights": rubric["weights"],
            "tie_band": rubric["tie_band"], "robust_min_first": rubric["robust_min_first"],
            "candidates": table, **result,
            "note": "a research prioritisation under the rubric registered before scoring; not evidence that any tactic works"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("selection identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
