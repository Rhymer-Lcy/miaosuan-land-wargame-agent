"""Re-derive Sprint 35's registered disposition from its recorded games with the Sprint 36 study derivation.

    python scripts/s36_s35_rederive.py [--work DIR] [--check]

Facts of every recorded position are recomputed from the private records by Sprint 35's own analysis
(``scripts/s35_analysis.py facts_of``), never read from its stored analysis files; the study is derived by
``evaluation.s36_study.report`` with Sprint 35's registered rules (``evaluation.s36_s35_rules``), and refused unless the
independent restatement agrees. Beside it the script records what Sprint 35's original report function computed from
the stored gates only (the defect), and what its reporting-only correction stored, as separate historical facts.
Public output ``evaluation/s36-tactical-recovery/s35-rederivation.json``: positions, stop, dispositions and each game's
public facts, written with the value-preserving publication policy (``evaluation.s36_publish``) so that no metric is
dropped. ``--check`` regenerates and compares byte for byte.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s35_live as sl  # noqa: E402
from miaosuan_agent.evaluation import s36_publish as pub  # noqa: E402
from miaosuan_agent.evaluation import s36_study as study  # noqa: E402
from miaosuan_agent.evaluation.s36_s35_rules import RULES  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "s35-rederivation.json"
STORED_DISPOSITION = REPO_ROOT / "evaluation" / sl.CARD_ID / "disposition.json"
PUBLIC_KEYS = ("position", "batch", "session", "scenario_id", "condition", "tag", "candidate_side", "status", "steps",
               "candidate", "opponent", "z", "unit_actions", "refusals", "fallbacks", "reconstruction_mismatches",
               "latency_ms_p99", "latency_ms_max", "memory_bytes_max", "objectives", "force")


def load_analysis() -> Any:
    spec = importlib.util.spec_from_file_location("s36_s35_analysis", REPO_ROOT / "scripts" / "s35_analysis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(work: Path) -> Dict[str, Any]:
    analysis = load_analysis()
    played: Dict[int, Dict[str, Any]] = {}
    for position in range(1, sl.SESSION_CAP + 1):
        facts = analysis.facts_of(position, work)
        if facts is not None:
            played[position] = facts
    derived = study.report(RULES, played)
    stored_gates = [json.loads(analysis.gate_path(work, b).read_text(encoding="utf-8"))
                    for b in sl.BATCHES if analysis.gate_path(work, b).exists()]
    original = sl.disposition(list(played.values()), stored_gates)
    correction = json.loads(STORED_DISPOSITION.read_text(encoding="utf-8"))
    games = []
    for position in sorted(played):
        f = played[position]
        games.append({k: f.get(k) for k in PUBLIC_KEYS})
    return {
        "schema": "miaosuan-s36-s35-rederivation/1",
        "derivation": derived,
        "historical": {
            "original_report_from_stored_gates": {"stored_gates": len(stored_gates),
                                                  "disposition": original["disposition"]},
            "reporting_only_correction": {"file": str(STORED_DISPOSITION.relative_to(REPO_ROOT)).replace("\\", "/"),
                                          "disposition": correction["disposition"]["disposition"],
                                          "interrupted_batch": correction.get("interrupted_batch")},
        },
        "agrees_with_correction": derived["disposition"]["disposition"] == correction["disposition"]["disposition"],
        "games": games,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build(args.work.resolve())
    if not result["agrees_with_correction"]:
        print("the re-derivation does not reproduce the registered disposition", file=sys.stderr)
        return 1
    text = pub.dumps(result, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("s35 re-derivation identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    d = result["derivation"]
    print(json.dumps({"disposition": d["disposition"], "stop": d["stop"], "walked": d["walked_games"],
                      "historical": result["historical"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
