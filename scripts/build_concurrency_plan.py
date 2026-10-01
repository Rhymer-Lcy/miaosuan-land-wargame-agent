"""Write (or ``--check``) the registered plan of the concurrency qualification.

    python scripts/build_concurrency_plan.py [--check]

The serial references are derived from the shoot experiment's private game records (15 repetitions of each
block configuration in groups B and C); only digests, prefix lengths and the median wall time enter the plan.
Each record must carry its group's registered policy digest and the experiment's manifest digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import concurrency as cq  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402

MANIFEST = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
RECORDS = REPO_ROOT / "local" / "evaluation" / sx.EXPERIMENT_NAME / "games"
PLAN = REPO_ROOT / "evaluation" / cq.PLAN_ID / "plan.json"


def references(manifest: dict) -> dict:
    digest = mf.digest(manifest)
    result: dict = {group: {} for group in sx.GROUPS}
    for group in sx.GROUPS:
        policy_digest = manifest["groups"][group]["policy_source"]["sha256"]
        for config in cq.BLOCK_CONFIGS:
            records = []
            for repetition in range(1, int(manifest["repetitions"]) + 1):
                path = RECORDS / f"{config}.{group}.r{repetition}.json"
                record = json.loads(path.read_text(encoding="utf-8"))
                harness = record["harness"]
                if (harness["manifest_sha256"], harness["policy_source_sha256"], harness.get("group")) != (
                        digest, policy_digest, group) or record["status"] != "COMPLETED":
                    raise SystemExit(f"{path}: not a completed registered record of group {group}")
                records.append(record)
            result[group][config] = cq.reference(records)
    return result


def build() -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    group = manifest["groups"]["C"]
    plan = cq.build(manifest, mf.digest(manifest), references(manifest), group["policy_source"],
                    group["golden_trace_chain"])
    return cq.text(plan)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed plan instead of writing")
    args = parser.parse_args()
    text = build()
    if args.check:
        if not PLAN.is_file() or PLAN.read_text(encoding="utf-8") != text:
            print(f"MISMATCH {PLAN.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        print(f"OK {PLAN.relative_to(REPO_ROOT)} sha256(canonical)={cq.digest(json.loads(text))}")
        return 0
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PLAN.relative_to(REPO_ROOT)} sha256(canonical)={cq.digest(json.loads(text))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
