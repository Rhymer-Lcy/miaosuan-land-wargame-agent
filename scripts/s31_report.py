"""Write the Sprint 31 pilot's public report (``docs/SPRINT31_T13_K2_PILOT.md``, Amendment A1). Reporting only.

    python scripts/s31_report.py [--work DIR] [--engine-install DIR] [--check]

The registered report command (``scripts/s31_analysis.py report``) refused to write, as its sanitizer is designed to:
it published each game's session as a string of digits and keyed the gates by "position n", words made only of digits.
This script calls the registered, unchanged functions (``s31_analysis.analyse``, ``s31_pilot.ledger_audit``,
``s31_pilot.disposition`` and ``s31_analysis.public_game``) and changes only the presentation: the session is published
as a number and the gates are keyed ``p01`` to ``p04``. It writes ``evaluation/s31-t13-k2/game-pNN.json`` for every
recorded game and ``disposition.json``, sanitised by the registered checks, or nothing; ``--check`` compares instead.
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

from miaosuan_agent.evaluation import s31_pilot as sp  # noqa: E402


def analysis_module():
    spec = importlib.util.spec_from_file_location("s31_report_analysis", REPO_ROOT / "scripts" / "s31_analysis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(work: Path, install: Path):
    an = analysis_module()
    card = json.loads(an.CARD.read_text(encoding="utf-8"))
    ledger = [json.loads(line) for line in (install / "usage-ledger.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    audit = sp.ledger_audit(ledger, card)
    positions = [g["screen_position"] for g in card["games"] if g["game_id"] in audit["games"]]
    results = [json.loads(an.text_of(an.analyse(card, p, work))) for p in positions]
    games = [{"position": r["position"], "completed": r["completed"], "structural": sp.structural_stops(r["structural"]),
              "mechanism": r["mechanism"], "harm": r["harm"], "facts": r.get("facts") or {}} for r in results]
    verdict = sp.disposition(games, audit["ok"])
    public = {}
    for r in results:
        game = an.public_game(r)
        game["session"] = int(r["session"]) if r.get("session") is not None else None
        public[f"game-p{r['position']:02d}.json"] = game
    public["disposition.json"] = {"schema": sp.SCHEMA, "card": sp.CARD_ID, **verdict,
                                  "ledger": {"sessions_after_base": audit["sessions"], "ok": audit["ok"],
                                             "problems": audit["problems"]},
                                  "gates": {f"p{r['position']:02d}": r["gate"] for r in results}}
    values = an.private_values(work, card, positions)
    scenarios = {g["scenario_id"] for g in card["games"]}
    problems = {name: sp.public_problems(data, values, scenarios) for name, data in public.items()}
    return {name: sp.dump(data) for name, data in public.items()}, {k: v for k, v in problems.items() if v}, verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path)
    parser.add_argument("--engine-install", type=Path, default=REPO_ROOT / "local" / "engines" / "sdk-4.1.0")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    work = (args.work or REPO_ROOT / "local" / "evaluation" / sp.CARD_ID).resolve()
    texts, problems, verdict = build(work, args.engine_install.resolve())
    if problems:
        print(f"the public sanitizer refused {sorted(problems)}: {list(problems.values())[0][:3]}; nothing written")
        return 1
    out = REPO_ROOT / "evaluation" / sp.STUDY_ID
    if args.check:
        same = all((out / n).exists() and (out / n).read_text(encoding="utf-8") == t for n, t in texts.items())
        print("report identical" if same else "MISMATCH")
        return 0 if same else 1
    for name, text in texts.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    print("wrote", ", ".join(sorted(texts)), "| disposition", verdict["disposition"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
