"""The registered analysis of the T9 confirmatory study (``docs/T9_CONFIRMATION.md``).

    python scripts/t9_confirmation_analysis.py phase --phase A|D|B|C [--work DIR] [--engine-install DIR] [--check]
    python scripts/t9_confirmation_analysis.py disposition [--check]

``phase`` reads the phase's private records and captures (``local/evaluation/t9-confirmation-1/``) and the engine
ledger (read only; the engine's state file is never read), and writes ``evaluation/t9-confirmation-1/phase-X.json``:
completion, integrity (ledger audit, record identities, capture digests and cross-checks), systemic failures, the
phase's registered estimands with their intervals, adverse signals, descriptive flags, mechanism summaries, the
per-game facts (aggregates only: scores, margins, counts, durations; no unit ids, hexes or positions) and the gate.
The ledger is read up to the last record of the study's sessions of this and earlier phases, so a phase file
regenerates byte-identically after later phases. Earlier phases are re-derived for their ``baseline-v2`` refusal
classes. ``--check`` compares with the committed file instead of writing it.

``disposition`` derives the registered research disposition from the committed phase files, in phase order, up to
the first phase that has none, and writes ``evaluation/t9-confirmation-1/disposition.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install as ei  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402

OUT_DIR = REPO_ROOT / "evaluation" / tc.STUDY_ID
MANIFEST = OUT_DIR / "manifest.json"


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_capture(path: Path, expected: Optional[str]) -> Optional[Dict[str, Any]]:
    """A capture file, only when its SHA-256 equals the digest its record carries."""
    if expected is None or not path.exists():
        return None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        return None
    return json.loads(data.decode("utf-8"))


def phase_facts(manifest: Mapping[str, Any], phase: str, work: Path) -> List[Dict[str, Any]]:
    facts = []
    for entry in tc.phase_games(manifest, phase):
        record = read_json(work / "games" / f"{entry['game_id']}.json")
        capture = explore = None
        if record is not None:
            summary = record.get("capture") or {}
            capture = load_capture(work / "capture" / f"{entry['game_id']}.t9.json", summary.get("t9_sha256"))
            explore = load_capture(work / "capture" / f"{entry['game_id']}.explore.json", summary.get("explore_sha256"))
        facts.append(tc.game_facts(entry, record, capture, explore))
    return facts


def ledger_prefix(ledger: Sequence[Mapping[str, Any]], manifest_sha256: str, phases: Sequence[str],
                  manifest: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """The ledger up to the last record of a session of the study's games in ``phases`` (all of it if none)."""
    ids = {g["game_id"] for g in manifest["games"] if g["phase"] in phases}
    sessions = {r["session"] for r in ledger if r.get("event") == "session-open"
                and (r.get("harness") or {}).get("manifest_sha256") == manifest_sha256
                and (r.get("harness") or {}).get("game_id") in ids}
    last = max((i for i, r in enumerate(ledger) if r.get("session") in sessions), default=None)
    return list(ledger) if last is None else list(ledger[:last + 1])


def analyse(manifest: Mapping[str, Any], phase: str, work: Path, ledger: Sequence[Mapping[str, Any]],
            resamples: int = tc.BOOTSTRAP["resamples"]) -> Dict[str, Any]:
    digest = mf.digest(manifest)
    index = tc.PHASE_ORDER.index(phase)
    phases = tc.PHASE_ORDER[:index + 1]
    prefix = ledger_prefix(ledger, digest, phases, manifest)
    audit = tc.ledger_audit(prefix, digest, [g["game_id"] for g in manifest["games"] if g["phase"] in phases])
    games = phase_facts(manifest, phase, work)
    prior: List[Dict[str, Any]] = []
    for earlier in tc.PHASE_ORDER[:index]:
        prior.extend(phase_facts(manifest, earlier, work))
    identity: Dict[str, List[str]] = {}
    for entry in tc.phase_games(manifest, phase):
        record = read_json(work / "games" / f"{entry['game_id']}.json")
        if record is None:
            continue
        problems = tc.record_identity_problems(record, manifest, digest)
        if audit["games"].get(entry["game_id"]) != record.get("session"):
            problems.append("session differs from the ledger's")
        identity[entry["game_id"]] = problems
    result = tc.analyse_phase(manifest, phase, games, audit, identity, prior, resamples)
    result["manifest_sha256"] = digest
    result["games"] = games
    return result


def phase_text(manifest: Mapping[str, Any], phase: str, work: Path, ledger: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(analyse(manifest, phase, work, ledger), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def disposition_text(out_dir: Path = OUT_DIR) -> str:
    results: Dict[str, Any] = {}
    for phase in tc.PHASE_ORDER:
        data = read_json(out_dir / f"phase-{phase}.json")
        if data is None:
            break
        results[phase] = data
    payload = {"schema": "miaosuan-t9-confirmation-disposition/1", "study_id": tc.STUDY_ID,
               "phase_files_sha256": {p: hashlib.sha256((out_dir / f"phase-{p}.json").read_bytes()).hexdigest()
                                      for p in results},
               **tc.disposition(results)}
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_or_check(path: Path, text: str, check: bool) -> int:
    if check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {path.relative_to(REPO_ROOT).as_posix()}")
        return 0 if same else 1
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(REPO_ROOT).as_posix()} sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("phase")
    one.add_argument("--phase", required=True, choices=tc.PHASE_ORDER)
    one.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / tc.STUDY_ID)
    one.add_argument("--engine-install", type=Path, default=REPO_ROOT / "local" / "engines" / "sdk-4.1.0")
    one.add_argument("--check", action="store_true")
    final = sub.add_parser("disposition")
    final.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.command == "disposition":
        return write_or_check(OUT_DIR / "disposition.json", disposition_text(), args.check)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ledger = ei.read_ledger(ei.EngineInstall(args.engine_install.resolve()))
    text = phase_text(manifest, args.phase, args.work.resolve(), ledger)
    result = json.loads(text)
    gate = result["gate"]
    print(f"phase {args.phase}: completion {result['completion']['ok']}, integrity {result['integrity']['ok']}, "
          f"systemic {result['systemic']['ok']}, adverse {len(result['adverse_signals'])}; gate {gate['decision']} "
          f"{gate['reasons']}")
    if "primary" in result:
        p = result["primary"]
        print(f"primary: tested {p['tested']}, estimate {p['estimate']}, 95% interval [{p['ci_low']}, {p['ci_high']}], "
              f"supported {p['supported']}")
    return write_or_check(OUT_DIR / f"phase-{args.phase}.json", text, args.check)


if __name__ == "__main__":
    sys.exit(main())
