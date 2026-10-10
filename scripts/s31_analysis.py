"""Analyse the Sprint 31 pilot's games (``docs/SPRINT31_T13_K2_PILOT.md``, section 6).

    python scripts/s31_analysis.py [--work DIR] game --position N [--check]
    python scripts/s31_analysis.py [--work DIR] report --engine-install DIR [--check]

``game`` reads one recorded game (its record and the four capture files, each checked against the digest the record
carries), evaluates the structural stops S1, S4, S6 and S7, the candidate seat's facts, the mechanism failures, the
harm stops and the registered gate (``evaluation/s31_pilot.py``), and writes the private analysis
``<work>/analysis/game-pNN.json`` (``--check`` regenerates and compares). The stage runner calls the same functions
before every later session. ``report`` writes the public ``evaluation/s31-t13-k2/game-pNN.json`` of every recorded
game and ``evaluation/s31-t13-k2/disposition.json`` (aggregates and labels only; sanitised, or nothing is written),
using the ledger audit of the installation's ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s31_pilot as sp  # noqa: E402

CAPTURES = ("explore.json", "exploreseries.json.gz", "timeline.json", "timeline.pkl")
CARD = REPO_ROOT / "evaluation" / sp.CARD_ID / "manifest.json"
PUBLIC = REPO_ROOT / "evaluation" / sp.STUDY_ID
SCHEMA_GAME = "miaosuan-s31-game/1"


def candidate_seat(record: Mapping[str, Any]) -> Tuple[int, int]:
    seat = next(s for s in record["seats"] if s["policy"] == sp.CANDIDATE_ID)
    return seat["seat"], seat["faction"]


def seat_view(windows: Mapping[str, Any], timeline: Mapping[str, Any], seat: int) -> Dict[str, Any]:
    """The candidate seat's observation at every decision, the final observation, the reconstruction rows, the live
    actions and the number of refused own actions."""
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    raws = [pickle.loads(s["seats"][seat]["observation"]) for s in samples]
    final = windows.get("final")
    final_raw = pickle.loads(final["seats"][seat]["observation"]) if final and seat in final["seats"] else None
    steps = timeline["steps"]
    rows = [step["s31"][str(seat)] for step in steps]
    emitted = [[a["action"] for a in step["submitted"] if a["seat"] == seat] for step in steps]
    errors = sum(1 for step in steps for f in step.get("feedback") or ()
                 if f.get("error") and (f.get("message") or {}).get("actor") == seat)
    if len(raws) != len(steps) or [s["k"] for s in samples] != list(range(len(steps))):
        raise ValueError("the timeline's samples are not one per decision")
    return {"raws": raws, "final": final_raw, "rows": rows, "emitted": emitted, "errors": errors}


def structural(entry: Mapping[str, Any], record: Mapping[str, Any], files: Sequence[bytes],
               windows: Mapping[str, Any]) -> Dict[str, List[str]]:
    digests = {name: ((record.get("capture") or {}).get(name), hashlib.sha256(data).hexdigest())
               for name, data in zip(CAPTURES, files)}
    timeline = json.loads(files[2])
    explore = json.loads(files[0])
    max_step = None
    try:
        seat, _ = candidate_seat(record)
        first = sorted(windows["samples"], key=lambda s: s["k"])[0]
        max_step = (pickle.loads(first["seats"][seat]["observation"]).get("time") or {}).get("max_step")
    except Exception:  # noqa: BLE001 - an unreadable capture is a structural finding, never a pass
        pass
    return sp.game_stops(entry, record, explore, timeline, max_step, digests)


def load_game(work: Path, entry: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[bytes]]:
    record = json.loads((work / "games" / f"{entry['game_id']}.json").read_text(encoding="utf-8"))
    files = [(work / "capture" / f"{entry['game_id']}.{suffix}").read_bytes() for suffix in CAPTURES]
    return record, files


def analyse(card: Mapping[str, Any], position: int, work: Path) -> Dict[str, Any]:
    """The private analysis of the game at ``position``; an unreadable game is an S7 finding."""
    entry = next(g for g in card["games"] if g["screen_position"] == position)
    out: Dict[str, Any] = {"schema": SCHEMA_GAME, "position": position, "game_id": entry["game_id"],
                           "scenario_id": entry["scenario_id"], "condition": entry["condition"],
                           "candidate_side": sp.candidate_side(entry), "opponent": sp.opponent(entry)}
    try:
        record, files = load_game(work, entry)
    except OSError as exc:
        stops = {"S7": [f"the record or a capture is missing: {type(exc).__name__}"]}
        return {**out, "completed": False, "structural": stops, "mechanism": {}, "harm": [],
                "gate": sp.gate(False, sp.structural_stops(stops), {}, [])}
    windows = pickle.loads(files[3])
    stops = structural(entry, record, files, windows)
    completed = record.get("status") == "COMPLETED"
    facts: Dict[str, Any] = {}
    mechanism: Dict[str, List[str]] = {}
    harm: List[str] = []
    if completed:
        try:
            seat, _ = candidate_seat(record)
            view = seat_view(windows, json.loads(files[2]), seat)
            facts = sp.game_facts(entry, view["raws"], view["final"], view["rows"], view["emitted"], view["errors"],
                                  record.get("final_scores") or {})
            mechanism = sp.mechanism_failures(facts)
            harm = sp.harm_stops(position, facts)
        except Exception as exc:  # noqa: BLE001 - a failure to analyse is a structural finding
            stops.setdefault("S7", []).append(f"the game could not be analysed: {type(exc).__name__}: {exc}"[:300])
    codes = sp.structural_stops(stops)
    return {**out, "session": record.get("session"), "steps": record.get("steps"), "completed": completed,
            "record_sha256": hashlib.sha256((work / "games" / f"{entry['game_id']}.json").read_bytes()).hexdigest(),
            "structural": stops, "facts": facts, "mechanism": mechanism, "harm": harm,
            "gate": sp.gate(completed, codes, mechanism, harm)}


def analysis_path(work: Path, position: int) -> Path:
    return work / "analysis" / f"game-p{position:02d}.json"


def text_of(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, default=str) + "\n"


def earlier_gates(card: Mapping[str, Any], position: int, work: Path) -> str:
    """Why the game at ``position`` may not open: an earlier game's stored analysis is missing, does not regenerate
    byte for byte from its record and captures, or does not authorize the next session; '' when every one does."""
    for p in range(1, position):
        path = analysis_path(work, p)
        if not path.exists():
            return f"no stored analysis of position {p}"
        text = text_of(analyse(card, p, work))
        if path.read_text(encoding="utf-8") != text:
            return f"the stored analysis of position {p} does not regenerate"
        gate = json.loads(text)["gate"]
        if not gate["next_session_authorized"]:
            return f"position {p} closed the gate: {gate['reasons']}"
    return ""


def public_game(result: Mapping[str, Any]) -> Dict[str, Any]:
    facts = {k: v for k, v in (result.get("facts") or {}).items() if k != "private"}
    controls = sp.RULES["inert_harm"]["positions"].get(str(result["position"])) or \
        sp.RULES["head_to_head_harm"]["positions"][str(result["position"])]
    return {"schema": SCHEMA_GAME, "card": sp.CARD_ID, "position": result["position"], "game_id": result["game_id"],
            "scenario_id": result["scenario_id"], "condition": result["condition"],
            "candidate_side": result["candidate_side"],
            "opponent": "baseline-v2" if result["opponent"] == sp.V2_ID else "inert control",
            "session": result.get("session"), "steps": result.get("steps"), "completed": result["completed"],
            "structural_stops": {k: len(v) for k, v in (result.get("structural") or {}).items()},
            "mechanism_failures": dict(result.get("mechanism") or {}), "harm_stops": list(result.get("harm") or ()),
            "gate": result["gate"], "registered_references": controls, "facts": facts}


def private_values(work: Path, card: Mapping[str, Any], positions: Sequence[int]) -> set:
    values: set = set()
    for p in positions:
        entry = next(g for g in card["games"] if g["screen_position"] == p)
        record, files = load_game(work, entry)
        windows = pickle.loads(files[3])
        for sample in windows["samples"]:
            for snap in sample["seats"].values():
                raw = pickle.loads(snap["observation"])
                for u in raw.get("operators") or ():
                    values.update(str(x) for x in (u.get("obj_id"), u.get("cur_hex")) if x is not None)
                    values.update(str(h) for h in u.get("move_path") or ())
                for c in raw.get("cities") or ():
                    values.add(str(c.get("coord")))
    return values


def cmd_game(args: argparse.Namespace) -> int:
    card = json.loads(CARD.read_text(encoding="utf-8"))
    text = text_of(analyse(card, args.position, args.work))
    path = analysis_path(args.work, args.position)
    if args.check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print("analysis identical" if same else "MISMATCH")
        return 0 if same else 1
    if path.exists() and path.read_text(encoding="utf-8") != text:
        print("REFUSED: a different analysis of this game exists", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    result = json.loads(text)
    print(f"position {args.position}: completed {result['completed']}, structural {sorted(result['structural'])}, "
          f"mechanism {sorted(result['mechanism'])}, harm {result['harm']}, gate {result['gate']}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    card = json.loads(CARD.read_text(encoding="utf-8"))
    ledger = [json.loads(line) for line in (args.engine_install / "usage-ledger.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    audit = sp.ledger_audit(ledger, card)
    positions = [g["screen_position"] for g in card["games"] if g["game_id"] in audit["games"]]
    results = [json.loads(text_of(analyse(card, p, args.work))) for p in positions]
    games = [{"position": r["position"], "completed": r["completed"], "structural": sp.structural_stops(r["structural"]),
              "mechanism": r["mechanism"], "harm": r["harm"], "facts": r.get("facts") or {}} for r in results]
    verdict = sp.disposition(games, audit["ok"])
    public = {f"game-p{r['position']:02d}.json": public_game(r) for r in results}
    public["disposition.json"] = {"schema": sp.SCHEMA, "card": sp.CARD_ID, **verdict,
                                  "ledger": {"sessions_after_2797": audit["sessions"], "ok": audit["ok"],
                                             "problems": audit["problems"]},
                                  "gates": {f"position {r['position']}": r["gate"] for r in results}}
    values = private_values(args.work, card, positions)
    scenarios = {g["scenario_id"] for g in card["games"]}
    for name, data in public.items():
        problems = sp.public_problems(data, values, scenarios)
        if problems:
            print(f"the public sanitizer refused {name}: {problems[:3]}")
            return 1
    texts = {name: sp.dump(data) for name, data in public.items()}
    if args.check:
        same = all((PUBLIC / n).exists() and (PUBLIC / n).read_text(encoding="utf-8") == t for n, t in texts.items())
        print("report identical" if same else "MISMATCH")
        return 0 if same else 1
    PUBLIC.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (PUBLIC / name).write_text(text, encoding="utf-8", newline="\n")
    print("wrote", ", ".join(sorted(texts)), "| disposition", verdict["disposition"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--position", type=int, required=True)
    game.add_argument("--check", action="store_true")
    game.set_defaults(func=cmd_game)
    report = sub.add_parser("report")
    report.add_argument("--engine-install", type=Path, default=REPO_ROOT / "local" / "engines" / "sdk-4.1.0")
    report.add_argument("--check", action="store_true")
    report.set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.work = (args.work or REPO_ROOT / "local" / "evaluation" / sp.CARD_ID).resolve()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
