"""Sprint 36 live analysis (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 19). No session is authorized.

    python scripts/s36_analysis.py position --position N [--work DIR]   facts and game stop of one played game
    python scripts/s36_analysis.py state [--work DIR]                   the study state from every recorded game
    python scripts/s36_analysis.py report [--work DIR] [--public]      every game, the state and the disposition

Facts of every recorded position (``evaluation.s36_live.game_facts``) are recomputed from the record and the compact
timeline whenever they are needed; ``WORK/analysis/pNN.json`` is a cache that must regenerate byte for byte. The study
state and disposition come from ``evaluation.s36_study.report`` with ``evaluation.s36_live.RULES`` (the derivation and
its independent restatement must agree); nothing is read from a stored gate. ``report --public`` writes
``evaluation/s36-tactical-live-1/results.json`` (aggregates only) with the value-preserving publication policy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s36_live as sl  # noqa: E402
from miaosuan_agent.evaluation import s36_publish as pub  # noqa: E402
from miaosuan_agent.evaluation import s36_study as study  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s36a_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CARDS = load("build_s36_card")
REFERENCES = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "references.json"
PUBLIC = REPO_ROOT / "evaluation" / sl.CARD_ID / "results.json"
PUBLIC_KEYS = ("position", "batch", "session", "scenario_id", "condition", "tag", "candidate_side", "status", "steps",
               "candidate", "opponent", "share", "stake", "z", "unit_actions", "refusal_summary", "halts", "fallbacks",
               "reconstruction_mismatches", "latency_ms_p99", "latency_ms_max", "memory_bytes_max", "objectives", "force",
               "module_actions")


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def game_of(position: int) -> Dict[str, Any]:
    return next(g for g in sl.schedule(CARDS.CANDIDATE_ID) if g["position"] == position)


def facts_of(position: int, work: Path) -> Optional[Dict[str, Any]]:
    game = game_of(position)
    record_path = work / "games" / f"{game['game_id']}.json"
    compact_path = work / "capture" / f"{game['game_id']}.timeline.json"
    if not record_path.exists():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    compact = json.loads(compact_path.read_text(encoding="utf-8")) if compact_path.exists() else {}
    references = json.loads(REFERENCES.read_text(encoding="utf-8"))
    return sl.game_facts(game, record, compact, references)


def analysis_path(work: Path, position: int) -> Path:
    return work / "analysis" / f"p{position:02d}.json"


def analyse(position: int, work: Path) -> Dict[str, Any]:
    facts = facts_of(position, work)
    if facts is None:
        return {"position": position, "recorded": False, "facts": None, "game_stop": None}
    stop = sl.game_stop(facts, [facts])
    return {"position": position, "recorded": True, "facts": facts,
            "game_stop": {"kind": stop[0], "findings": list(stop[1])} if stop else None}


def played(work: Path) -> Dict[int, Dict[str, Any]]:
    out = {}
    for position in range(1, sl.SESSION_CAP + 1):
        facts = facts_of(position, work)
        if facts is not None:
            out[position] = facts
    return out


def state(work: Path, authorized: bool = True) -> Dict[str, Any]:
    return study.report(sl.RULES, played(work), authorized)


def stored_problems(work: Path) -> str:
    """'' when every stored analysis regenerates byte for byte; else the first position that does not."""
    for position in range(1, sl.SESSION_CAP + 1):
        path = analysis_path(work, position)
        if path.exists() and path.read_text(encoding="utf-8") != dump(analyse(position, work)):
            return f"the stored analysis of position {position} does not regenerate"
    return ""


def report(work: Path) -> Dict[str, Any]:
    facts = played(work)
    derived = study.report(sl.RULES, facts)
    games = [{k: f.get(k) for k in PUBLIC_KEYS} for _, f in sorted(facts.items())]
    return {"card": sl.CARD_ID, "rules": sl.RULES_ID, "games": games, "state": derived}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("position")
    p.add_argument("--position", type=int, required=True)
    s = sub.add_parser("state")
    r = sub.add_parser("report")
    r.add_argument("--public", action="store_true")
    for x in (p, s, r):
        x.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    args = parser.parse_args()
    if args.command == "position":
        print(dump(analyse(args.position, args.work)))
        return 0
    if args.command == "state":
        print(dump(state(args.work)))
        return 0
    result = report(args.work)
    if args.public:
        PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC.write_text(pub.dumps(result, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
                          newline="\n")
    print(dump({"disposition": result["state"]["disposition"], "games": len(result["games"]),
                "stop": result["state"]["stop"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
