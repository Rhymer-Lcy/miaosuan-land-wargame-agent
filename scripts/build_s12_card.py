"""Build, or check, a Sprint 12 stage card (``docs/SPRINT12_V3_SCREEN.md``).

    python scripts/build_s12_card.py --stage P1|P2|A1|A2 [--check]

A stage card is ``evaluation/<card>/manifest.json`` in the exploratory run-card schema, with a ``screen`` block that
pins the frozen rules, every frozen implementation file and, for a later stage, the committed report that permits it.
P1's card follows from this checkout alone. P2's, A1's and A2's follow mechanically from the committed report of the
stage before (``s12_screen.build_card``): the script refuses to build a card that report does not permit, and A2 holds
exactly the configurations the A1 report names. A card is never rewritten once it exists with other content;
``--check`` fails unless the committed card is byte-identical to a fresh build. This is separate from
``scripts/build_run_card.py``, whose cards are unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
V3_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_batch.py")


def policy_source(sources) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def committed_reports(repo: Path = REPO_ROOT) -> Dict[str, Mapping[str, Any]]:
    out = {}
    for stage in sc.STAGE_ORDER:
        path = repo / sc.report_path(stage)
        if path.exists():
            out[stage] = json.loads(path.read_text(encoding="utf-8"))
    return out


def build_stage(stage: str, repo: Path = REPO_ROOT) -> Dict[str, Any]:
    shoot = json.loads((repo / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
    policies = [{"id": sc.V2_ID, "label": "baseline-v2 (frozen)", "policy_source": policy_source(V2_SOURCES)},
                {"id": sc.V3_ID, "label": "T9 batch capacity allocator, version 3 (frozen)",
                 "policy_source": policy_source(V3_SOURCES)}]
    reports = committed_reports(repo)
    digests = {stage_: sc.normalized_sha256(repo / sc.report_path(stage_)) for stage_ in reports}
    return sc.build_card(stage, shoot, mf.digest(shoot), policies, sc.frozen_digests(repo), reports, digests)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", required=True, choices=sc.STAGE_ORDER)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    out = REPO_ROOT / "evaluation" / sc.CARD_IDS[args.stage] / "manifest.json"
    try:
        card = build_stage(args.stage)
    except sc.NotPermitted as exc:
        print(f"NOT PERMITTED: {exc}", file=sys.stderr)
        return 1
    text = sc.dump(card)
    digest = mf.digest(card)
    rel = out.relative_to(REPO_ROOT).as_posix()
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {rel} sha256(canonical)={digest}")
        return 0 if same else 1
    if out.exists():
        if out.read_text(encoding="utf-8") == text:
            print(f"unchanged {rel} sha256(canonical)={digest}")
            return 0
        print(f"REFUSED: {rel} exists with other content; a card is never rewritten", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {rel} sha256(canonical)={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
