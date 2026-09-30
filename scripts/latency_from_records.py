"""Reconstruct the decision-latency distribution of baseline-v1 from the variance-study game records.

    python scripts/latency_from_records.py [--check]

Reads the 192 new and the 64 reused records of ``baseline-v1-variance-study-1`` (private, never
modified), builds one row per decision of every seat (the policy under test and the inert control),
writes those rows privately to ``local/diagnostics/latency/record-decisions.jsonl.gz`` and a
public aggregate to ``evaluation/latency-diagnostic-1/record-tail.json``: threshold counts and
their concentration by scenario, condition, repetition, decision index, stage and first-play
status, and the latency profile over game time of the configurations with a tail. ``--check``
rebuilds the aggregate and compares it with the committed file.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.diagnostics import latency as lat  # noqa: E402
from miaosuan_agent.evaluation import variance_study as vs  # noqa: E402

SCHEMA = "miaosuan-latency-record-tail/1"
OUT = REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "record-tail.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "latency" / "record-decisions.jsonl.gz"
BIN = 250


def load_records(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = []
    source = manifest["historical_records"]["source_evaluation"]
    for row in manifest["historical_records"]["records"]:
        path = REPO_ROOT / "local" / "evaluation" / source / "games" / f"{row['game_id']}.json"
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["record_sha256"]:
            raise SystemExit(f"{path.name} does not match its pinned digest")
        records.append(dict(json.loads(data.decode("utf-8")), source="historical"))
    for entry in manifest["schedule"]:
        path = REPO_ROOT / "local" / "evaluation" / vs.STUDY_NAME / "games" / f"{entry['game_id']}.json"
        records.append(dict(json.loads(path.read_text(encoding="utf-8")), source="new"))
    return records


def profile(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    bins: Dict[int, List[int]] = {}
    for row in rows:
        bins.setdefault(row["decision"] // BIN * BIN, []).append(row["latency_us"])
    return {str(start): dict(lat.summary(values), **{f">{t}ms": sum(1 for v in values if v > t * 1000)
                                                     for t in (10, 100, 400)})
            for start, values in sorted(bins.items())}


def build() -> Dict[str, Any]:
    manifest = json.loads((REPO_ROOT / "evaluation" / vs.STUDY_NAME / "manifest.json").read_text(encoding="utf-8"))
    policy = manifest["policy_under_test"]
    records = load_records(manifest)
    rows: List[Dict[str, Any]] = []
    for record in records:
        for row in lat.decision_rows(record, (policy, INERT_ID)):
            row["source"] = record["source"]
            rows.append(row)
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(PRIVATE, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    tested = [r for r in rows if r["policy"] == policy]
    inert = [r for r in rows if r["policy"] == INERT_ID]
    games_over = {t: sorted({r["game_id"] for r in tested if r["latency_us"] > t * 1000}) for t in lat.THRESHOLDS_MS}
    tail_configs = sorted({f"{r['scenario_id']}.{r['condition']}" for r in tested if r["latency_us"] > 400_000})
    result = {
        "schema": SCHEMA, "study": vs.STUDY_NAME, "policy": policy,
        "games": len(records), "decisions": {"policy": len(tested), "inert": len(inert)},
        "thresholds_ms": list(lat.THRESHOLDS_MS),
        "policy_tail": lat.threshold_counts(tested), "inert_tail": lat.threshold_counts(inert),
        "policy_summary": lat.summary([r["latency_us"] for r in tested]),
        "games_with_a_decision_over": {f">{t}ms": len(v) for t, v in games_over.items()},
        "by_scenario_condition": lat.grouped(tested, ("scenario_id", "condition")),
        "by_condition": lat.grouped(tested, ("condition",)),
        "by_repetition": lat.grouped(tested, ("repetition",)),
        "by_stage": lat.grouped(tested, ("stage",)),
        "by_first_play": lat.grouped(tested, ("first_play",)),
        "by_source": lat.grouped(tested, ("source",)),
        "inert_by_scenario_condition_seat": lat.grouped(inert, ("scenario_id", "condition", "seat")),
        "concentration": {f">{t}ms": {
            "by_scenario_condition": lat.concentration(tested, t, ("scenario_id", "condition")),
            "by_decision": lat.concentration(tested, t, ("decision",)),
            "by_first_play": lat.concentration(tested, t, ("first_play",))} for t in (100, 400, 1000)},
        "profile_over_game_time": {config: profile([r for r in tested if f"{r['scenario_id']}.{r['condition']}" == config])
                                   for config in tail_configs},
        "inert_profile_over_game_time": {
            f"{s}.{c}": profile([r for r in inert if r["scenario_id"] == s and r["condition"] == c])
            for s, c in sorted({(r["scenario_id"], r["condition"]) for r in inert if r["latency_us"] > 100_000})},
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed aggregate")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()} and the private rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
