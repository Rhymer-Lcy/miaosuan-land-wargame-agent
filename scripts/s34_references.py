"""Sprint 34 historical ``baseline-v2`` reference distributions (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 10).

    python scripts/s34_references.py [--check]

Reads the group C records of the registered shoot-reservation experiment (``baseline-v2``'s promotion experiment:
15 games per scenario and condition, ``<scenario>.<condition>.C.r<n>``) for the configurations Sprint 34 compares
against, and writes ``evaluation/s34-integrated-agent/references.json``: per configuration and seat, the number of
games and the mean, sample standard deviation, minimum and maximum of the seat's margin (``<seat>_win``), objective
score, attack score and remaining-force score, plus the SHA-256 of every record read. Summary statistics only. It runs
on the evaluation server, where the private records are; ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS = REPO_ROOT / "local" / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "games"
OUT = REPO_ROOT / "evaluation" / "s34-integrated-agent" / "references.json"
SCHEMA = "miaosuan-s34-references/1"
V2 = "baseline-v2-candidate-shoot-target-reservation"
INERT = "inert-v0"
CONFIGS = ("2130511121.C1", "2120531121.C1", "1930331196.C1", "1910631192.C1",
           "2120531121.C2", "2120531121.C3", "1930331196.C2", "1930331196.C3")
FIELDS = ("win", "occupy", "attack", "remain", "total")


def stats(values: List[float]) -> Dict[str, Any]:
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": round(mean, 6), "sd": round(sd, 6), "min": min(values), "max": max(values)}


def build() -> Dict[str, Any]:
    out: Dict[str, Any] = {"schema": SCHEMA, "source": "baseline-v2 promotion experiment, group C", "configs": {},
                           "records": {}}
    for config in CONFIGS:
        paths = sorted(RECORDS.glob(f"{config}.C.r*.json"), key=lambda p: int(p.stem.rsplit(".r", 1)[1]))
        if len(paths) != 15:
            raise SystemExit(f"{config}: {len(paths)} group C records, expected 15")
        seats: Dict[str, Dict[str, List[float]]] = {"red": {f: [] for f in FIELDS}, "blue": {f: [] for f in FIELDS}}
        for path in paths:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["status"] != "COMPLETED":
                raise SystemExit(f"{path.name} did not complete")
            policies = record["policies"]
            expected = {"C1": (V2, V2), "C2": (V2, INERT), "C3": (INERT, V2)}[config.split(".")[1]]
            if (policies["red"], policies["blue"]) != expected:
                raise SystemExit(f"{path.name}: unexpected policies {policies}")
            scores = record["final_scores"]
            for seat in ("red", "blue"):
                for field in FIELDS:
                    seats[seat][field].append(float(scores[f"{seat}_{field}"]))
            out["records"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        out["configs"][config] = {seat: {field: stats(values) for field, values in fields.items()}
                                  for seat, fields in seats.items()}
    out["records"] = dict(sorted(out["records"].items()))
    return out


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = dump(build())
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print("references identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(text[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
