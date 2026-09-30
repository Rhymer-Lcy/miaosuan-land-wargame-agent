"""Pin the historical game records that the variance study reuses as repetitions 1 and 2.

    python scripts/pin_study_history.py [--check]

Reads the frozen baseline-v1 suite records under the git-ignored ``local/evaluation/`` (never
modifies them) and writes ``evaluation/baseline-v1-variance-study-1/historical-records.json``:
game id, configuration, repetition, engine session, status, harness commit and the SHA-256 of
each private record file. The registration embeds this list, so a reused record that changes, or
a game quietly swapped for another, no longer matches. ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import variance_study as vs  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID  # noqa: E402

OUT = REPO_ROOT / "evaluation" / vs.STUDY_NAME / "historical-records.json"
RECORDS = REPO_ROOT / "local" / "evaluation" / CANDIDATE_ID / "games"
RESULTS = REPO_ROOT / "evaluation" / CANDIDATE_ID / "results.json"


def build() -> dict:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    rows = []
    for game in results["suite"]["games"]:
        path = RECORDS / f"{game['game_id']}.json"
        if not path.is_file():
            raise SystemExit(f"missing private record {path.name}: run this on the machine that holds the records")
        data = path.read_bytes()
        record = json.loads(data.decode("utf-8"))
        if record["game_id"] != game["game_id"]:
            raise SystemExit(f"{path.name} holds game {record['game_id']}")
        rows.append({"game_id": game["game_id"], "scenario_id": game["scenario_id"], "condition": game["condition"],
                     "repetition": game["repetition"], "session": record["session"], "status": record["status"],
                     "harness_commit": record["harness"]["commit"], "record_sha256": hashlib.sha256(data).hexdigest()})
    return {"source_evaluation": CANDIDATE_ID,
            "source_results_sha256": hashlib.sha256(RESULTS.read_bytes()).hexdigest(),
            "rule": "SHA-256 of the private record file bytes under local/evaluation/<source_evaluation>/games/",
            "records": sorted(rows, key=lambda r: r["game_id"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed file instead of writing it")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"MISMATCH: {OUT.relative_to(REPO_ROOT).as_posix()} differs from the records", file=sys.stderr)
            return 1
        print(f"OK {OUT.relative_to(REPO_ROOT).as_posix()}")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
