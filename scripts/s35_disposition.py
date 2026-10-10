"""Sprint 35 registered disposition after a structural stop (reporting only; no rule changed).

    python scripts/s35_disposition.py [--work DIR] [--check]

``scripts/s35_analysis.py report`` hands ``evaluation.s35_live.disposition`` the stored batch gates only, and a structural
stop inside a batch leaves no gate file, so the report printed a disposition that ignores the stop. The registered rules
say that any structural stop closes the study at once with ``S35_LIVE_INVALID``. This script applies the registered
functions unchanged to the games actually played: the facts of every recorded position (``s35_analysis.facts_of``), the
gate of the interrupted batch computed by ``evaluation.s35_live.batch_gate`` over those facts, then
``evaluation.s35_live.disposition``. It writes ``evaluation/s35-coalition-live-1/disposition.json``, and the public
``results.json``: the registered report (``s35_analysis.report``) with each game's ``mean_held_value`` removed (one value
matches a pattern of the project's pre-push privacy scan, whose accepted baseline is not changed for it; the private
analysis files keep it).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s35_live as sl  # noqa: E402

OUT = REPO_ROOT / "evaluation" / sl.CARD_ID / "disposition.json"
RESULTS = REPO_ROOT / "evaluation" / sl.CARD_ID / "results.json"


def main() -> int:
    spec = importlib.util.spec_from_file_location("s35d_analysis", REPO_ROOT / "scripts" / "s35_analysis.py")
    analysis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analysis)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    played = []
    for position in range(1, 49):
        facts = analysis.facts_of(position, args.work)
        if facts is None:
            break
        played.append(facts)
    if not played:
        raise SystemExit("no played game")
    last = played[-1]
    batch = last["batch"]
    stored = [json.loads(analysis.gate_path(args.work, b).read_text(encoding="utf-8"))
              for b in sl.BATCHES if analysis.gate_path(args.work, b).exists()]
    interrupted = sl.batch_gate(batch, played)
    stops = {str(f["position"]): sl.structural(f) for f in played if sl.structural(f)}
    result = {"schema": "miaosuan-s35-disposition/1", "games_played": len(played),
              "sessions": [f["session"] for f in played], "last_position": last["position"], "interrupted_batch": batch,
              "stored_gates": stored, "interrupted_batch_gate": interrupted, "structural_stops": stops,
              "disposition": sl.disposition(played, stored + [interrupted]),
              "note": "registered functions applied unchanged to the games played; reporting only"}
    text = json.dumps(result, indent=1, sort_keys=True) + "\n"
    report = analysis.report(args.work)
    for game in report["games"]:
        game["objectives"].pop("mean_held_value", None)
    public = analysis.dump(report)
    if args.check:
        same = (OUT.exists() and OUT.read_text(encoding="utf-8") == text and RESULTS.exists()
                and RESULTS.read_text(encoding="utf-8") == public)
        print("disposition and results identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    RESULTS.write_text(public, encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("games_played", "interrupted_batch", "structural_stops")}, indent=1))
    print(json.dumps(result["disposition"], indent=1)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
