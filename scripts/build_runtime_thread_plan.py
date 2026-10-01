"""Write (or ``--check``) the registered plan of the runtime thread-pool qualification.

    python scripts/build_runtime_thread_plan.py [--check]

The workload and serial references come from the committed concurrency-qualification plan, cited by its digest;
the plan also pins the call-counting shim's source digest and the production scheduler's identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import concurrency as cq  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_threads as rt  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402

PLAN = REPO_ROOT / "evaluation" / rt.PLAN_ID / "plan.json"
CQ_PLAN = REPO_ROOT / "evaluation" / cq.PLAN_ID / "plan.json"
MANIFEST = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"


def scheduler_identity() -> str:
    """The qualified production scheduler the runs use: the one the concurrency qualification's equivalence
    run recorded (the pool's identity at registration; later scheduler revisions get identities of their own)."""
    results = json.loads((REPO_ROOT / "evaluation" / cq.PLAN_ID / "results.json").read_text(encoding="utf-8"))
    (identity,) = results["equivalence"]["scheduler"]
    return identity


def build() -> str:
    cq_plan = json.loads(CQ_PLAN.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    probe = hashlib.sha256((REPO_ROOT / rt.PROBE["source"]).read_bytes()).hexdigest()
    plan = rt.build(cq_plan, cq.digest(cq_plan), manifest, mf.digest(manifest), probe, scheduler_identity())
    return rt.text(plan)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed plan instead of writing")
    args = parser.parse_args()
    text = build()
    if args.check:
        if not PLAN.is_file() or PLAN.read_text(encoding="utf-8") != text:
            print(f"MISMATCH {PLAN.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        print(f"OK {PLAN.relative_to(REPO_ROOT)} sha256(canonical)={rt.digest(json.loads(text))}")
        return 0
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PLAN.relative_to(REPO_ROOT)} sha256(canonical)={rt.digest(json.loads(text))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
