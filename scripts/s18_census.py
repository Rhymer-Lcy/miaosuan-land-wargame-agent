"""Sprint 18 supplemental capability and opportunity census (``docs/SPRINT18_FRONTIER_RESET.md``).

    python scripts/s18_census.py freeze [--check]

``freeze`` pins every input of the census by SHA-256 in ``evaluation/s18-frontier-reset/inputs.json`` before the
census runs: the SDK archive (population S), the 8 replay-corpus games (H0, as pinned by the routing remediation's
corpus list), the record, timeline and timeline index of the 4 Sprint 12 head-to-head games (HH) and of the 5 Sprint 16
and 17 games against the inert control (HI), and the inventory of every completed game record (R) except the
prevalence study's, whose registered stop keeps its data unexamined. The record inventory itself is private (the
evaluation server's ``local/diagnostics/s18/record-inventory.txt``); the public file holds its digest and the record
counts by folder. ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "evaluation" / "s18-frontier-reset"
INPUTS = OUT_DIR / "inputs.json"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s18"
ARCHIVE = "local/source-archives/land_wargame_sdk.zip"
ARCHIVE_SHA256 = "ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
HH_FOLDER = "s12-v3-primary-1"
HH_GAMES = ("2130511121.H1.s12-v3-primary-1.p01", "2130511121.H2.s12-v3-primary-1.p02",
            "2130511121.H1.s12-v3-primary-1.p03", "2130511121.H2.s12-v3-primary-1.p04")
HI_GAMES = (("s16-v3-mechanism-capture-1", "1930331196.C3.s16-v3-mechanism-capture-1.p01"),
            ("s16-v3-mechanism-capture-1", "1930331196.C2.s16-v3-mechanism-capture-1.p02"),
            ("s16-v3-mechanism-capture-1", "2120531121.C3.s16-v3-mechanism-capture-1.p03"),
            ("s17-post-stage-v6-probe-1", "1930331196.C2.s17-post-stage-v6-probe-1.p01"),
            ("s17-post-stage-v6-probe-1", "2120531121.C3.s17-post-stage-v6-probe-1.p02"))
#: Record folders the census does not read, and why (section 5 of the registration).
EXCLUDED_RECORD_FOLDERS = {
    "baseline-v2-target-ownership-prevalence-1": "registered stop: its data stay unexamined",
}
SCHEMA_INPUTS = "miaosuan-s18-inputs/1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def game_files(folder: str, game: str) -> Dict[str, str]:
    base = f"local/evaluation/{folder}"
    return {"record": f"{base}/games/{game}.json", "timeline": f"{base}/capture/{game}.timeline.pkl",
            "timeline_index": f"{base}/capture/{game}.timeline.json"}


def record_inventory(root: Path = REPO_ROOT) -> Tuple[List[str], Dict[str, int]]:
    """Every completed record outside the excluded folders, as ``relative path:sha256`` lines, and counts by folder."""
    lines: List[str] = []
    counts: Dict[str, int] = {}
    for folder in sorted(p for p in (root / "local" / "evaluation").iterdir() if p.is_dir()):
        if folder.name in EXCLUDED_RECORD_FOLDERS or not (folder / "games").is_dir():
            continue
        n = 0
        for path in sorted((folder / "games").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("status") != "COMPLETED":
                continue
            lines.append(f"{path.relative_to(root).as_posix()}:{sha256(path)}")
            n += 1
        if n:
            counts[folder.name] = n
    return lines, counts


def freeze(root: Path = REPO_ROOT) -> Tuple[Dict[str, Any], str]:
    if sha256(root / ARCHIVE) != ARCHIVE_SHA256:
        raise SystemExit("the SDK archive does not match its pinned digest")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    h0 = []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        if sha256(root / entry["path"]) != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        h0.append({"path": entry["path"], "sha256": entry["sha256"], "decisions": entry["decisions"]})
    hh = [{"game": g, **{k: {"path": p, "sha256": sha256(root / p)} for k, p in game_files(HH_FOLDER, g).items()}}
          for g in HH_GAMES]
    hi = [{"game": g, **{k: {"path": p, "sha256": sha256(root / p)} for k, p in game_files(f, g).items()}}
          for f, g in HI_GAMES]
    lines, counts = record_inventory(root)
    inventory = "\n".join(lines) + "\n"
    out = {"schema": SCHEMA_INPUTS, "study_id": "s18-frontier-reset",
           "S": {"path": ARCHIVE, "sha256": ARCHIVE_SHA256},
           "H0": {"corpus_list": "evaluation/routing-remediation-1/corpus.json", "games": h0},
           "HH": {"games": hh, "analysed_side": "the baseline-v2 seat"},
           "HI": {"games": hi, "use": "listing, starting-configuration and movement-timing figures only"},
           "R": {"records": len(lines), "records_by_folder": counts,
                 "inventory_sha256": hashlib.sha256(inventory.encode("utf-8")).hexdigest(),
                 "inventory_line": "<relative path>:<sha256 of the record file>, sorted, one per line",
                 "excluded_folders": dict(EXCLUDED_RECORD_FOLDERS)}}
    return out, inventory


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_freeze = sub.add_parser("freeze")
    p_freeze.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        data, inventory = freeze()
        text = dump(data)
        if args.check:
            same = INPUTS.exists() and INPUTS.read_text(encoding="utf-8") == text
            print("inputs identical" if same else "MISMATCH")
            return 0 if same else 1
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(text, encoding="utf-8", newline="\n")
        PRIVATE.mkdir(parents=True, exist_ok=True)
        (PRIVATE / "record-inventory.txt").write_text(inventory, encoding="utf-8", newline="\n")
        print(f"wrote {INPUTS.relative_to(REPO_ROOT).as_posix()} ({data['R']['records']} records)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
