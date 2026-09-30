"""Derive the factual refusal classes of the historical evaluations from their private game records.

    python scripts/derive_historical_refusal_facts.py [--check]

Reads the records under the git-ignored ``local/evaluation/`` (never modifies them) and writes
``evaluation/refusal-taxonomy-correction/historical-refusal-facts.json``: for each historical set
of games, the engine refusals of the policy under test by code (as recorded), by code and action
type where the harness recorded the type, and by factual class (action type, code, normalized
engine message) as far as the records retain an example of each refusal. A refusal whose type or
message was not recorded is counted as not retained; nothing is filled in from other games or
from the code. ``--check`` rebuilds the file and fails unless it is identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import refusals  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID  # noqa: E402

SCHEMA = "miaosuan-historical-refusal-facts/1"
OUT = REPO_ROOT / "evaluation" / "refusal-taxonomy-correction" / "historical-refusal-facts.json"
LOCAL = REPO_ROOT / "local" / "evaluation"
CANDIDATE_DIR = f"evaluation/{CANDIDATE_ID}"
#: (evaluation, part, policy under test, record directory, game-id filter, committed public file, part in it)
SETS = (
    ("baseline-v0", "gate1", "baseline-v0", "baseline-v0/games", "gate1.", "evaluation/baseline-v0/results.json",
     "gate1"),
    ("baseline-v0", "suite", "baseline-v0", "baseline-v0/games", "", "evaluation/baseline-v0/results.json", "suite"),
    ("baseline-v0", "diagnostics", "baseline-v0", "baseline-v0-diagnostics/games", "",
     "evaluation/baseline-v0/diagnostics.json", "engine_messages"),
    (CANDIDATE_ID, "gate1-attempt-1", CANDIDATE_ID, f"{CANDIDATE_ID}/registration-1-gate1/games", "gate1.",
     f"{CANDIDATE_DIR}/results-gate1-attempt-1.json", "gate1"),
    (CANDIDATE_ID, "gate1", CANDIDATE_ID, f"{CANDIDATE_ID}/games", "gate1.", f"{CANDIDATE_DIR}/results.json", "gate1"),
    (CANDIDATE_ID, "suite", CANDIDATE_ID, f"{CANDIDATE_ID}/games", "", f"{CANDIDATE_DIR}/results.json", "suite"),
)
SUPERSEDED = (
    {"where": f"{CANDIDATE_DIR}/manifest.json (refusal_taxonomy.codes.203) and {CANDIDATE_DIR}/results.json "
              "(refusal_decomposition.by_code_category)",
     "said": "code 203: action type shoot; category 'same-step conflict: shooter destroyed earlier in the step'",
     "correction": "The category was assigned to every code 203 from the code alone. The candidate suite recorded "
                   "code 203 with the message CantControlDiedOperator on shots and on an occupation (see the facts "
                   "of its suite set), so the category misnames the occupation. The registered files are left "
                   "unchanged; the factual classes in this file supersede the category."},
    {"where": "docs/EVALUATION.md (engine-reported errors table and summary) and docs/BASELINE.md (limitations)",
     "said": "code 203 is a shot by a unit destroyed earlier in the step; the table gives action 'shoot' and a "
             "message for the suite refusals with code 203",
     "correction": "The baseline-v0 suite records hold the code only: the action type and the message in that table "
                   "were taken from separate diagnostic games, where every code-203 refusal was a shot. The action "
                   "type and the message of the suite refusals with code 203 were not recorded and are unknown."},
    {"where": "attribution 1 (src/miaosuan_agent/evaluation/effects.py, refusal_context), used for the candidate results",
     "said": "a code-203 refusal is classified only for shots ('shooter present at step start')",
     "correction": "It left the occupation unclassified, which was correct, but read the code as shooting-specific. "
                   "Attribution 2 (src/miaosuan_agent/evaluation/refusals.py) applies the code-203 rule to any action type and "
                   "requires the actor's absence after the step as evidence."},
)


def sha256(relative: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()


def load(directory: str, prefix: str) -> List[Dict[str, Any]]:
    files = sorted((LOCAL / directory).glob("*.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in files
            if path.name.startswith(prefix) and (prefix or not path.name.startswith("gate1."))]


def add(counts: Dict[str, int], key: str, value: int) -> None:
    counts[key] = counts.get(key, 0) + value


def derive(records: List[Mapping[str, Any]], policy: str) -> Dict[str, Any]:
    by_code: Dict[str, int] = {}
    by_code_and_type: Optional[Dict[str, int]] = {}
    groups: Dict[str, Dict[str, Any]] = {}
    seats = [seat for record in records for seat in record["seats"] if seat["policy"] == policy]
    for seat in seats:
        codes = seat["feedback_errors_by_code"]
        typed = seat.get("feedback_errors_by_code_and_type")
        for code, count in codes.items():
            add(by_code, code, count)
        if typed is None or (codes and not typed):
            by_code_and_type = None
        elif by_code_and_type is not None:
            for key, count in typed.items():
                add(by_code_and_type, key, count)
        examples = seat.get("feedback_error_examples") or {}
        per_seat = typed if typed else {f"{code}/None": count for code, count in codes.items()}
        for key, count in per_seat.items():
            code, kind = key.split("/", 1)
            group = groups.setdefault(key, {"code": int(code), "action_type": None if kind == "None" else int(kind),
                                            "count": 0, "messages": {}, "message_not_retained": 0})
            group["count"] += count
            retained = [e for e in examples.get(code, []) if kind != "None" and str(e["action"].get("type")) == kind]
            for example in retained:
                add(group["messages"], refusals.normalize_message(example.get("error_message")), 1)
            group["message_not_retained"] += count - len(retained)
    facts = [dict(group, messages=dict(sorted(group["messages"].items())))
             for _, group in sorted(groups.items(), key=lambda item: (item[1]["code"], str(item[1]["action_type"])))]
    return {"games": len(records), "seats_of_policy": len(seats), "by_code": dict(sorted(by_code.items())),
            "by_code_and_type": None if by_code_and_type is None else dict(sorted(by_code_and_type.items())),
            "facts": facts,
            "complete": all(f["message_not_retained"] == 0 and f["action_type"] is not None for f in facts)}


def build() -> Dict[str, Any]:
    sets = []
    for evaluation, part, policy, directory, prefix, public, public_part in SETS:
        records = load(directory, prefix)
        if not records:
            raise SystemExit(f"no records in local/evaluation/{directory}: run this on the machine that holds them")
        sets.append({"evaluation": evaluation, "part": part, "policy": policy, "public_file": public,
                     "public_part": public_part, "public_sha256": sha256(public), **derive(records, policy)})
    return {"schema": SCHEMA, "fact": "(action type, error code, normalized engine message); see evaluation/refusals.py",
            "derived_by": "scripts/derive_historical_refusal_facts.py from the private game records, unchanged",
            "sets": sets, "superseded": list(SUPERSEDED)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed file instead of writing it")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        on_disk = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if on_disk != text:
            print(f"MISMATCH: {OUT.relative_to(REPO_ROOT).as_posix()} differs from the rebuilt file", file=sys.stderr)
            return 1
        print(f"OK {OUT.relative_to(REPO_ROOT).as_posix()}")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}: {len(result['sets'])} sets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
