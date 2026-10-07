"""Build, or check, the Sprint 22 probe card (``docs/SPRINT22_T2_TRANSPORT_PROBE.md``).

    python scripts/build_s22_card.py [--check]

The card is ``evaluation/s22-t2-transport-probe-1/manifest.json`` in the exploratory run-card schema: one game of the
mechanism-probe candidate ``t2-transport-p1`` against the inert control in the witness configuration
(``s22_probe.SCHEDULE``), the frozen rules and the normalised SHA-256 of every frozen implementation file. A card is
never rewritten once it exists with other content; ``--check`` fails unless the committed card is byte-identical to a
fresh build. Separate from every earlier card builder, whose cards are unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import s22_probe as sp  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
CANDIDATE_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t2_transport_p1.py")
CARD = REPO_ROOT / "evaluation" / sp.CARD_ID / "manifest.json"


def policy_source(sources) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def build(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    shoot = json.loads((repo / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
    policies = [{"id": sp.V2_ID, "label": "baseline-v2 (frozen)", "policy_source": policy_source(V2_SOURCES)},
                {"id": sp.CANDIDATE_ID, "label": "T2-P1 transport mechanism probe (Sprint 22 exploratory candidate)",
                 "policy_source": policy_source(CANDIDATE_SOURCES)}]
    return sp.build_card(shoot, mf.digest(shoot), policies, sp.frozen_digests(repo))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    card = build()
    text = sp.dump(card)
    digest = mf.digest(card)
    rel = CARD.relative_to(REPO_ROOT).as_posix()
    if args.check:
        same = CARD.exists() and CARD.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {rel} sha256(canonical)={digest}")
        return 0 if same else 1
    if CARD.exists():
        if CARD.read_text(encoding="utf-8") == text:
            print(f"unchanged {rel} sha256(canonical)={digest}")
            return 0
        print(f"REFUSED: {rel} exists with other content; a card is never rewritten", file=sys.stderr)
        return 1
    CARD.parent.mkdir(parents=True, exist_ok=True)
    CARD.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {rel} sha256(canonical)={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
