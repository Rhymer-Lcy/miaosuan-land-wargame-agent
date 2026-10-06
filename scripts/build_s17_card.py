"""Build, or check, the Sprint 17 probe card (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``).

    python scripts/build_s17_card.py [--check]

The card is ``evaluation/s17-post-stage-v6-probe-1/manifest.json`` in the exploratory run-card schema: two games of the
executable candidate ``t9-delayed-post-stage-any-v6`` against the inert control (``s17_probe.SCHEDULE``), the frozen
rules, the normalised SHA-256 of every frozen implementation file, and Sprint 16's card (id and canonical digest) as
the source of the prefix trajectories. A card is never rewritten once it exists with other content; ``--check`` fails
unless the committed card is byte-identical to a fresh build. Separate from every earlier card builder, whose cards are
unchanged.
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
from miaosuan_agent.evaluation import s17_probe as sp  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
CANDIDATE_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_batch.py",
                                  "experiments/t9_redistribution.py", "experiments/t9_delayed.py",
                                  "experiments/t9_post_stage_v6.py")
CARD = REPO_ROOT / "evaluation" / sp.CARD_ID / "manifest.json"
SOURCE_CARD = REPO_ROOT / "evaluation" / sp.SOURCE_CARD / "manifest.json"


def policy_source(sources) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def reference() -> Dict[str, Any]:
    source = json.loads(SOURCE_CARD.read_text(encoding="utf-8"))
    return {"card": sp.SOURCE_CARD, "canonical_sha256": mf.digest(source),
            "games": {config: sp.SOURCE_GAMES[config] for config in sp.CONFIGS}}


def build(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    shoot = json.loads((repo / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
    policies = [{"id": sp.V2_ID, "label": "baseline-v2 (frozen)", "policy_source": policy_source(V2_SOURCES)},
                {"id": sp.CANDIDATE_ID, "label": "delayed post-stage-any redistribution, version 6 (Sprint 17 "
                                                "executable candidate)", "policy_source": policy_source(CANDIDATE_SOURCES)}]
    return sp.build_card(shoot, mf.digest(shoot), policies, sp.frozen_digests(repo), reference())


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
