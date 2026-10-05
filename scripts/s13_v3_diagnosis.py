"""Sprint 13 offline diagnosis of the T9-v3 primary-scenario failure (``docs/SPRINT13_V3_DIAGNOSIS.md``), server only.

    python scripts/s13_v3_diagnosis.py freeze [--check]     # evaluation/s13-v3-diagnosis/inputs.json

``freeze`` pins, by SHA-256, every private input the diagnosis reads: the four Sprint 12 P1 records with their five
capture files each, the scenario's setup cost data, and the 30 Sprint 9 phase-A primary T9-v1 records with their
``T9Capture`` and exploratory capture files. It also recomputes the four frozen policy identities from the checkout and
refuses to write if any differs from the frozen value. ``--check`` regenerates the file in memory and compares it byte
for byte. No engine is opened; the ledger is only read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402

SCHEMA_INPUTS = "miaosuan-s13-inputs/1"
OUT_DIR = REPO_ROOT / "evaluation" / "s13-v3-diagnosis"
INPUTS = OUT_DIR / "inputs.json"
EV = REPO_ROOT / "local" / "evaluation"
S12_CARD = "s12-v3-primary-1"
S12_CAPTURES = ("t9.json", "v3.json", "v3series.json.gz", "timeline.json", "timeline.pkl")
S9_STUDY = "t9-confirmation-1"
S9_CAPTURES = ("t9.json", "explore.json")
SCENARIO = "2130511121"
LEDGER = REPO_ROOT / "local" / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"

#: The frozen policy-source identities (docs/SPRINT13_V3_DIAGNOSIS.md, section 1).
FROZEN = {
    "baseline-v2": "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae",
    "t9-v1": "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa",
    "t9-v2": "66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece",
    "t9-v3": "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8",
}
ADDON_MODULES = {"baseline-v2": (), "t9-v1": ("experiments/exploratory_addon.py", "experiments/t9_allocation.py"),
                 "t9-v2": ("experiments/exploratory_addon.py", "experiments/t9_staging.py"),
                 "t9-v3": ("experiments/exploratory_addon.py", "experiments/t9_batch.py")}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def policy_digests() -> Dict[str, str]:
    """Each policy's source digest recomputed from the checkout (the exploratory run cards' construction)."""
    base = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
    return {name: digest_of_files(policy_source_files(sources=base + extra)) for name, extra in ADDON_MODULES.items()}


def tree_digest(root: Path) -> Dict[str, Any]:
    """One digest over every file under ``root`` (sorted relative path and file digest); names are not published."""
    rows = sorted((p.relative_to(root).as_posix(), sha256(p)) for p in root.rglob("*") if p.is_file())
    digest = hashlib.sha256("".join(f"{name}\0{value}\n" for name, value in rows).encode("utf-8")).hexdigest()
    return {"files": len(rows), "sha256": digest}


def s12_games(repo: Path = REPO_ROOT) -> List[Dict[str, Any]]:
    card = json.loads((repo / "evaluation" / S12_CARD / "manifest.json").read_text(encoding="utf-8"))
    return [dict(g) for g in card["games"]]


def s9_games(repo: Path = REPO_ROOT) -> List[Dict[str, Any]]:
    phase = json.loads((repo / "evaluation" / S9_STUDY / "phase-A.json").read_text(encoding="utf-8"))
    return [{"game_id": g["game_id"], "cell": g["cell"], "session": g["session"]} for g in phase["games"]
            if g["scenario_id"] == SCENARIO and g["cell"] in ("H1", "H2")]


def build_inputs(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    digests = policy_digests()
    wrong = {k: v for k, v in digests.items() if v != FROZEN[k]}
    if wrong:
        raise SystemExit(f"refused: policy identities differ from the frozen values: {sorted(wrong)}")
    ev = repo / "local" / "evaluation"
    s12 = []
    for game in s12_games(repo):
        gid = game["game_id"]
        record = ev / S12_CARD / "games" / f"{gid}.json"
        session = json.loads(record.read_text(encoding="utf-8")).get("session")
        s12.append({"game_id": gid, "screen_position": game["screen_position"], "session": session,
                    "record_sha256": sha256(record),
                    "captures": {suffix: sha256(ev / S12_CARD / "capture" / f"{gid}.{suffix}") for suffix in S12_CAPTURES}})
    s9 = []
    for game in s9_games(repo):
        gid = game["game_id"]
        s9.append({**game, "record_sha256": sha256(ev / S9_STUDY / "games" / f"{gid}.json"),
                   "captures": {suffix: sha256(ev / S9_STUDY / "capture" / f"{gid}.{suffix}") for suffix in S9_CAPTURES}})
    if len(s12) != 4 or len(s9) != 30:
        raise SystemExit(f"refused: expected 4 Sprint 12 and 30 Sprint 9 games, found {len(s12)} and {len(s9)}")
    return {"schema": SCHEMA_INPUTS, "policies": dict(sorted(digests.items())),
            "s12": {"card": S12_CARD, "card_manifest_sha256": sha256(repo / "evaluation" / S12_CARD / "manifest.json"),
                    "report_sha256": sha256(repo / "evaluation" / S12_CARD / "report.json"),
                    "cost_data": tree_digest(ev / S12_CARD / "data" / SCENARIO), "games": s12},
            "s9": {"study": S9_STUDY, "phase_file_sha256": sha256(repo / "evaluation" / S9_STUDY / "phase-A.json"),
                   "games": s9},
            "note": "private inputs pinned before the Sprint 13 analysis; files stay under the ignored local/ tree"}


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def check_inputs(repo: Path = REPO_ROOT) -> Mapping[str, Any]:
    """The committed inputs file, after verifying that every pinned input still has its digest."""
    committed = INPUTS.read_text(encoding="utf-8")
    if dump(build_inputs(repo)) != committed:
        raise SystemExit("refused: a private input or a policy identity differs from evaluation/s13-v3-diagnosis/inputs.json")
    return json.loads(committed)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="pin every private input by SHA-256")
    freeze.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "freeze":
        text = dump(build_inputs())
        if args.check:
            same = INPUTS.exists() and INPUTS.read_text(encoding="utf-8") == text
            print("inputs: identical" if same else "inputs: MISMATCH")
            return 0 if same else 1
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {INPUTS.relative_to(REPO_ROOT).as_posix()}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
