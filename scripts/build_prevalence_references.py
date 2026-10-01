"""Write, or check, the serial references of the target-ownership prevalence diagnostic.

    python scripts/build_prevalence_references.py [--check]

For each of the 24 configurations (8 scenarios x C1, C2, C3), the reference is derived from the 15 serial games of
the shoot-reservation experiment's group C, which ran the frozen baseline-v2: the state and trace digests over the
prefix every repetition shares, the chains, and the class (deterministic when all 15 chains are equal). Only digests,
prefix lengths and the median wall time enter the public file; the records are private, so ``--check`` runs where they
exist. Each record must carry the experiment's manifest digest and group C's registered policy digest.
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
from miaosuan_agent.evaluation import ownership_prevalence as op  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402

MANIFEST = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
RECORDS = REPO_ROOT / "local" / "evaluation" / sx.EXPERIMENT_NAME / "games"
OUT = REPO_ROOT / "evaluation" / op.STUDY_ID / "references.json"


def build() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    digest = mf.digest(manifest)
    policy = manifest["groups"]["C"]["policy_source"]["sha256"]
    if policy != op.BASELINE_V2_SOURCE_SHA256:
        raise SystemExit("group C is not the frozen baseline-v2 source")
    references = {}
    for config in op.configurations([s["scenario_id"] for s in manifest["scenarios"]]):
        records = []
        for repetition in range(1, int(manifest["repetitions"]) + 1):
            path = RECORDS / f"{config}.C.r{repetition}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            harness = record["harness"]
            if (harness["manifest_sha256"], harness["policy_source_sha256"], harness.get("group")) != (digest, policy, "C") \
                    or record["status"] != "COMPLETED":
                raise SystemExit(f"{path}: not a completed registered record of group C")
            records.append(record)
        references[config] = cq.reference(records)
    return {"schema": op.REFERENCES_SCHEMA, "study_id": op.STUDY_ID, "source": sx.EXPERIMENT_NAME, "group": "C",
            "source_manifest_sha256": digest, "policy_source_sha256": policy, "configurations": references}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed file instead of writing")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {OUT.relative_to(REPO_ROOT).as_posix()}")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
