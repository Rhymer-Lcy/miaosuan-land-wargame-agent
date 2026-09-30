"""Build, or check, the registered manifest of the shoot-target-reservation experiment.

    python scripts/build_shoot_experiment_manifest.py [--check]

Every input is a committed file: the variance-study manifest and results (scenarios, players, caps,
randomness procedure, planning figures), the routing remediation's records (the identity of
baseline-v1-runtime-r1), the candidate's policy source, and the pinned counterfactual replay and
mutation results. Generation is deterministic; ``--check`` fails unless the committed manifest is
byte-identical to a fresh build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME
OUT = DIRECTORY / "manifest.json"


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs() -> Dict[str, Any]:
    study = REPO_ROOT / "evaluation" / "baseline-v1-variance-study-1"
    routing = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID
    runtime_sha, runtime_files = policy_source_digest(sources=rr.candidate_sources())
    candidate_sources = rr.candidate_sources() + (sx.CANDIDATE_FILE,)
    candidate_sha, candidate_files = policy_source_digest(sources=candidate_sources)
    runtime = {"identity": sx.RUNTIME_R1_ID, "code_identity": sx.RUNTIME_R1_CODE_ID,
               "policy_source_sha256": runtime_sha, "files": list(runtime_files), "sources": list(rr.candidate_sources()),
               "identity_document": "docs/BASELINE_V1_RUNTIME_R1.md",
               "remediation": {"registration_sha256": mf.digest(load(routing / "registration.json")),
                               "equivalence_sha256": sha(routing / "equivalence.json"),
                               "mutation_sha256": sha(routing / "mutation.json"),
                               "benchmark_sha256": sha(routing / "benchmark.json"),
                               "engine_sha256": sha(routing / "engine.json")}}
    candidate = {"identity": sx.CANDIDATE_ID, "policy_source_sha256": candidate_sha, "files": list(candidate_files),
                 "sources": list(candidate_sources), "golden_trace_chain": sx.CANDIDATE_GOLDEN_TRACE_CHAIN}
    return {"study_manifest": load(study / "manifest.json"), "study_results": load(study / "results.json"),
            "study_results_sha256": sha(study / "results.json"), "runtime": runtime, "candidate": candidate,
            "counterfactual": load(DIRECTORY / "counterfactual-replay.json"),
            "counterfactual_sha256": sha(DIRECTORY / "counterfactual-replay.json"),
            "mutation": load(DIRECTORY / "mutation.json"), "mutation_sha256": sha(DIRECTORY / "mutation.json")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed manifest instead of writing")
    args = parser.parse_args()
    manifest = sx.build(**inputs())
    text = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    digest = mf.digest(manifest)
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {OUT.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
