"""Analysis of the Sprint 12 screen (``docs/SPRINT12_V3_SCREEN.md``): per game, per stage and the disposition.

    python scripts/s12_screen_analysis.py game --stage S --game-id ID      # one game's facts and stops (exit 3: stop)
    python scripts/s12_screen_analysis.py report --stage S [--check]       # evaluation/<card>/report.json
    python scripts/s12_screen_analysis.py disposition [--check]            # evaluation/s12-v3-screen/disposition.json

Reads the private records and captures under ``local/evaluation/<card>/`` and the session ledger (read only), and
applies the frozen rules of ``evaluation.s12_screen``. ``report`` writes the public stage report, whose decision is the
only thing that can permit the next stage card, and the private facts beside the captures
(``local/diagnostics/s12/<card>-private.json``); ``--check`` regenerates the report in memory and compares it byte for
byte. ``disposition`` reads only the committed reports (and, if present, the committed stop attribution
``evaluation/s12-v3-screen/stop-attribution.json``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Origin  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation.t9_confirmation import refusal_classes  # noqa: E402

CAPTURES = ("t9.json", "v3.json", "v3series.json.gz", "timeline.json", "timeline.pkl")
DISPOSITION = REPO_ROOT / "evaluation" / sc.SCREEN_ID / "disposition.json"
ATTRIBUTION = REPO_ROOT / "evaluation" / sc.SCREEN_ID / "stop-attribution.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s12"
INSTALL = REPO_ROOT / "local" / "engines" / "sdk-4.1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def card(stage: str, repo: Path = REPO_ROOT) -> Optional[Dict[str, Any]]:
    path = repo / "evaluation" / sc.CARD_IDS[stage] / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def committed_cards(repo: Path = REPO_ROOT) -> Dict[str, Dict[str, Any]]:
    return {sc.CARD_IDS[s]: c for s in sc.STAGE_ORDER for c in [card(s, repo)] if c is not None}


def work_dir(card_id: str, repo: Path = REPO_ROOT) -> Path:
    return repo / "local" / "evaluation" / card_id


def costs_for(work: Path, the_card: Mapping[str, Any], scenario: str) -> MoveCosts:
    map_id = next(s["map_id"] for s in the_card["scenarios"] if s["scenario_id"] == scenario)
    inputs = sdk_data.load_inputs(work / "data" / scenario / "Data", scenario, map_id)
    return MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")


def played_records(repo: Path = REPO_ROOT) -> List[Tuple[int, Dict[str, Any]]]:
    """(screen position, record) of every screen game with a record, in screen order."""
    out = []
    for card_id, the_card in committed_cards(repo).items():
        for entry in the_card["games"]:
            path = work_dir(card_id, repo) / "games" / f"{entry['game_id']}.json"
            if path.exists():
                out.append((entry["screen_position"], json.loads(path.read_text(encoding="utf-8"))))
    return sorted(out, key=lambda item: item[0])


def baseline_classes(before_position: int, repo: Path = REPO_ROOT) -> Set[Tuple[Any, Any, str]]:
    """Refusal classes seen in baseline-v2 seats of the screen games played before ``before_position``."""
    known: Set[Tuple[Any, Any, str]] = set()
    for position, record in played_records(repo):
        if position >= before_position:
            continue
        for seat in record.get("seats", []):
            if seat["policy"] == sc.V2_ID:
                known |= set(refusal_classes(seat))
    return known


def game_facts(the_card: Mapping[str, Any], entry: Mapping[str, Any], repo: Path = REPO_ROOT,
               work: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Private facts of one game, or None if it has no record."""
    work = work or work_dir(the_card["card_id"], repo)
    record_path = work / "games" / f"{entry['game_id']}.json"
    if not record_path.exists():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    paths = {name: work / "capture" / f"{entry['game_id']}.{name}" for name in CAPTURES}
    recorded = record.get("capture") or {}
    digests = {name: (recorded.get(name), sha256(path) if path.exists() else None) for name, path in paths.items()}
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return {"game_id": entry["game_id"], "screen_position": entry["screen_position"],
                "scenario_id": entry["scenario_id"], "condition": entry["condition"], "status": record.get("status"),
                "stops": {"S7": [f"capture files missing: {missing}"]}}
    with paths["timeline.pkl"].open("rb") as handle:
        windows = pickle.load(handle)
    facts = tl.analyze(entry, the_card["card_id"], record,
                       json.loads(paths["t9.json"].read_text(encoding="utf-8")),
                       json.loads(paths["v3.json"].read_text(encoding="utf-8")),
                       json.loads(paths["timeline.json"].read_text(encoding="utf-8")), windows,
                       costs_for(work, the_card, entry["scenario_id"]), capture_digests=digests,
                       extra_known=baseline_classes(entry["screen_position"], repo))
    facts["record_sha256"] = sha256(record_path)
    return facts


def ledger_problems(repo: Path = REPO_ROOT, install: Path = INSTALL) -> Dict[str, List[str]]:
    path = install / "usage-ledger.jsonl"
    with path.open(encoding="utf-8") as handle:
        ledger = [json.loads(line) for line in handle if line.strip()]
    audit = sc.ledger_audit(ledger, committed_cards(repo))
    return {code: problems for code, problems in audit["problems"].items() if problems}


def stage_report(stage: str, repo: Path = REPO_ROOT, install: Path = INSTALL) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    the_card = card(stage, repo)
    if the_card is None:
        raise SystemExit(f"no committed card for {stage}")
    facts = [f for f in (game_facts(the_card, entry, repo) for entry in the_card["games"]) if f is not None]
    earlier: List[Dict[str, Any]] = []
    if stage == "P2":
        p1 = card("P1", repo)
        earlier = [f for f in (game_facts(p1, entry, repo) for entry in p1["games"]) if f is not None]
    stage_level = ledger_problems(repo, install)
    decision = sc.decide(stage, facts, expected=len(the_card["games"]), earlier=earlier, stage_level=stage_level)
    inputs = {f["game_id"]: f.get("record_sha256", "missing") for f in earlier + facts}
    report = sc.report(stage, [tl.public(f) for f in earlier + facts], decision, inputs)
    return report, earlier + facts


def cmd_game(args: argparse.Namespace) -> int:
    the_card = card(args.stage)
    entry = next((g for g in the_card["games"] if g["game_id"] == args.game_id), None) if the_card else None
    if entry is None:
        print(f"unknown game {args.game_id} in stage {args.stage}", file=sys.stderr)
        return 2
    facts = game_facts(the_card, entry)
    if facts is None:
        print(f"no record of {args.game_id}", file=sys.stderr)
        return 2
    stops = dict(facts.get("stops") or {})
    for code, problems in ledger_problems().items():
        stops.setdefault(code, []).extend(problems)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "games").mkdir(exist_ok=True)
    (PRIVATE / "games" / f"{args.game_id}.json").write_text(sc.dump(facts), encoding="utf-8", newline="\n")
    codes = [c for c in sc.STOP_CODES if stops.get(c)]
    print(f"{args.game_id}: stops {codes or 'none'}; class "
          f"{facts.get('adverse_class') or ('T9-v2-like' if facts.get('t9v2_like') else 'primary')}")
    for code in codes:
        for problem in stops[code][:5]:
            print(f"  {code}: {problem}")
    return 3 if codes else 0


def cmd_report(args: argparse.Namespace) -> int:
    report, facts = stage_report(args.stage)
    text = sc.dump(report)
    out = REPO_ROOT / sc.report_path(args.stage)
    rel = out.relative_to(REPO_ROOT).as_posix()
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {rel}")
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / f"{sc.CARD_IDS[args.stage]}-private.json").write_text(sc.dump(facts), encoding="utf-8", newline="\n")
    print(f"wrote {rel}: decision {report['decision']['decision']}")
    return 0


def cmd_disposition(args: argparse.Namespace) -> int:
    reports = {}
    for stage in sc.STAGE_ORDER:
        path = REPO_ROOT / sc.report_path(stage)
        if path.exists():
            reports[stage] = json.loads(path.read_text(encoding="utf-8"))
    attribution = json.loads(ATTRIBUTION.read_text(encoding="utf-8")) if ATTRIBUTION.exists() else None
    result = {"schema": sc.SCHEMA_DISPOSITION, "screen": sc.SCREEN_ID, "rules_sha256": sc.rules_digest(),
              "reports": {s: sc.normalized_sha256(REPO_ROOT / sc.report_path(s)) for s in reports},
              **sc.disposition(reports, attribution)}
    text = sc.dump(result)
    if args.check:
        same = DISPOSITION.exists() and DISPOSITION.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {DISPOSITION.relative_to(REPO_ROOT).as_posix()}")
        return 0 if same else 1
    DISPOSITION.parent.mkdir(parents=True, exist_ok=True)
    DISPOSITION.write_text(text, encoding="utf-8", newline="\n")
    print(f"disposition {result['disposition']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--stage", required=True, choices=sc.STAGE_ORDER)
    game.add_argument("--game-id", required=True)
    game.set_defaults(func=cmd_game)
    rep = sub.add_parser("report")
    rep.add_argument("--stage", required=True, choices=sc.STAGE_ORDER)
    rep.add_argument("--check", action="store_true")
    rep.set_defaults(func=cmd_report)
    disp = sub.add_parser("disposition")
    disp.add_argument("--check", action="store_true")
    disp.set_defaults(func=cmd_disposition)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
