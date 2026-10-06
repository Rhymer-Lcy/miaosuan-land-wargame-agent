"""Build, or check, the Sprint 16 mechanism-capture card (``docs/SPRINT16_MECHANISM_CAPTURE.md``).

    python scripts/build_s16_card.py [--check]

The card is ``evaluation/s16-v3-mechanism-capture-1/manifest.json`` in the exploratory run-card schema: three games of
the frozen ``t9-batch-capacity-v3`` against the inert control (``s16_mechanism.SCHEDULE``), the frozen rules, the
normalised SHA-256 of every frozen implementation file, and, for reference only, the analysis identity of the
shadows (``s16-delayed-shadow-v6``), marked not executable. A card is never rewritten once it exists with other
content; ``--check`` fails unless the committed card is byte-identical to a fresh build. Separate from
``scripts/build_run_card.py`` and ``scripts/build_s12_card.py``, whose cards are unchanged.
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
from miaosuan_agent.evaluation import s16_mechanism as ms  # noqa: E402
from miaosuan_agent.evaluation import s16_shadow as sh  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
V3_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_batch.py")
SHADOW_SOURCES = V3_SOURCES + ("experiments/t9_redistribution.py", "experiments/t9_delayed.py",
                               "evaluation/s16_shadow.py")
CARD = REPO_ROOT / "evaluation" / ms.CARD_ID / "manifest.json"


def policy_source(sources) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def shadow_identity() -> Dict[str, Any]:
    files = policy_source_files(sources=SHADOW_SOURCES)
    return {"id": sh.SHADOW_ID, "source_sha256": digest_of_files(files), "files": files,
            "rules": [{"rule": name, "identity": ident, "trigger": trigger, "count": count, "same_source": same}
                      for name, ident, trigger, count, same in sh.shadow_rules()],
            "target": sh.TARGET}


def build(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    shoot = json.loads((repo / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
    policies = [{"id": ms.V2_ID, "label": "baseline-v2 (frozen)", "policy_source": policy_source(V2_SOURCES)},
                {"id": ms.V3_ID, "label": "T9 batch capacity allocator, version 3 (frozen, unchanged)",
                 "policy_source": policy_source(V3_SOURCES)}]
    return ms.build_card(shoot, mf.digest(shoot), policies, ms.frozen_digests(repo), shadow_identity())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    card = build()
    text = ms.dump(card)
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
