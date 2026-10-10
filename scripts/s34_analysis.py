"""Sprint 34 live analysis (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 10).

    python scripts/s34_analysis.py position --position N [--work DIR]   facts and stops of one played game
    python scripts/s34_analysis.py gate --batch B [--work DIR]         the gate after a completed batch
    python scripts/s34_analysis.py report [--work DIR] [--public]      every game, the gates and the disposition

Each position's facts (``evaluation.s34_live.game_facts``) are written to ``WORK/analysis/pNN.json`` and each batch's
gate to ``WORK/analysis/gate-B.json``; both regenerate byte for byte from the record and the compact timeline.
``report --public`` writes ``evaluation/s34-integrated-live-1/results.json`` (aggregates only: scores, counts and
steps; no unit id, hex or coordinate).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s34_live as sl  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s34a_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CARDS = load("build_s34_card")
REFERENCES = REPO_ROOT / "evaluation" / "s34-integrated-agent" / "references.json"
PUBLIC = REPO_ROOT / "evaluation" / sl.CARD_ID / "results.json"


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


def gate_path(work: Path, batch: str) -> Path:
    return work / "analysis" / f"gate-{batch}.json"


def analyse(position: int, work: Path) -> Dict[str, Any]:
    facts = facts_of(position, work)
    if facts is None:
        return {"position": position, "completed": False, "structural": {"S1": ["no record"]}, "facts": None}
    return {"position": position, "completed": facts["status"] == "COMPLETED", "structural": sl.structural(facts),
            "facts": facts}


def batch_gate(batch: str, work: Path) -> Dict[str, Any]:
    played = []
    for position in range(1, max(sl.BATCHES[batch]) + 1):
        facts = facts_of(position, work)
        if facts is None:
            return {"batch": batch, "open": False, "reason": f"position {position} has no record"}
        played.append(facts)
    return sl.batch_gate(batch, played)


def earlier_gates(position: int, work: Path) -> str:
    """'' when every earlier position's analysis regenerates and every earlier batch's gate is open; else why not."""
    for p in range(1, position):
        path = analysis_path(work, p)
        if not path.exists() or path.read_text(encoding="utf-8") != dump(analyse(p, work)):
            return f"the stored analysis of position {p} is missing or does not regenerate"
    batch = game_of(position)["batch"]
    order = list(sl.BATCHES)
    for earlier in order[:order.index(batch)]:
        path = gate_path(work, earlier)
        gate = batch_gate(earlier, work)
        if not path.exists() or path.read_text(encoding="utf-8") != dump(gate):
            return f"the gate of batch {earlier} is missing or does not regenerate"
        if not gate["open"]:
            return f"the gate of batch {earlier} is closed: {gate['reason']}"
    return ""


def report(work: Path) -> Dict[str, Any]:
    facts: List[Dict[str, Any]] = []
    for position in range(1, 25):
        f = facts_of(position, work)
        if f is not None:
            facts.append(f)
    gates = [json.loads(gate_path(work, b).read_text(encoding="utf-8")) for b in sl.BATCHES if gate_path(work, b).exists()]
    return {"card": sl.CARD_ID, "rules": sl.RULES_ID, "games": facts, "gates": gates,
            "disposition": sl.disposition(facts, gates)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("position")
    p.add_argument("--position", type=int, required=True)
    g = sub.add_parser("gate")
    g.add_argument("--batch", required=True, choices=list(sl.BATCHES))
    r = sub.add_parser("report")
    r.add_argument("--public", action="store_true")
    for s in (p, g, r):
        s.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    args = parser.parse_args()
    if args.command == "position":
        print(dump(analyse(args.position, args.work)))
        return 0
    if args.command == "gate":
        print(dump(batch_gate(args.batch, args.work)))
        return 0
    result = report(args.work)
    if args.public:
        PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC.write_text(dump(result), encoding="utf-8", newline="\n")
    print(dump({"disposition": result["disposition"], "games": len(result["games"]),
                "gates": [(g["batch"], g["open"], g["reason"]) for g in result["gates"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
