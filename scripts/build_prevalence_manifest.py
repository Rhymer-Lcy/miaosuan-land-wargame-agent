"""Build, or check, the registered manifest of the target-ownership prevalence diagnostic.

    python scripts/build_prevalence_manifest.py [--check]

Every input is a committed file: the shoot-reservation experiment's manifest (baseline-v2's policy source and golden
chain, the scenarios, conditions, players, caps and randomness procedure), the study's references file (the serial
baseline-v2 reference of each configuration) and the runtime thread qualification's results (the promoted runtime and
the qualified production scheduler, whose identity must equal the one this checkout computes). Generation is
deterministic; ``--check`` fails unless the committed manifest is byte-identical to a fresh build.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import ownership_prevalence as op  # noqa: E402
from miaosuan_agent.evaluation import runtime_threads as rt  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402

OUT = REPO_ROOT / "evaluation" / op.STUDY_ID / "manifest.json"
REFERENCES = REPO_ROOT / "evaluation" / op.STUDY_ID / "references.json"


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def current_scheduler() -> str:
    spec = importlib.util.spec_from_file_location("run_game_pool", REPO_ROOT / "scripts" / "run_game_pool.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scheduler_identity()


def build() -> Dict[str, Any]:
    shoot = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
    results = REPO_ROOT / "evaluation" / rt.PLAN_ID / "results.json"
    shoot_manifest, references, rt_results = load(shoot), load(REFERENCES), load(results)
    manifest = op.build(shoot_manifest, mf.digest(shoot_manifest), references,
                        hashlib.sha256(REFERENCES.read_bytes()).hexdigest(), rt_results,
                        hashlib.sha256(results.read_bytes()).hexdigest())
    if manifest["execution"]["scheduler"] != current_scheduler():
        raise SystemExit("the production scheduler of this checkout is not the qualified one")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed manifest instead of writing")
    args = parser.parse_args()
    manifest = build()
    text = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    digest = op.digest(manifest)
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
