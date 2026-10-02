"""Build, or check, the registered manifest of the PS-1 engine probe ``ps1-engine-probe-1``.

    python scripts/build_ps1_probe_manifest.py [--check]

Every input is committed: the deployment-split screen's manifest (the split candidate's policy source, the two
scenarios, players, randomness and caps, the original seats of both configurations), the runtime thread
qualification's results (the promoted runtime and the qualified scheduler, whose identity must equal the one this
checkout computes), the line-ending-normalised SHA-256 of every implementation and test file the probe relies on, and
the digests of its private and public inputs. Generation is deterministic; ``--check`` fails unless the committed
manifest is byte-identical to a fresh build.
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
from miaosuan_agent.evaluation import ps1_probe as pp  # noqa: E402

OUT = REPO_ROOT / "evaluation" / pp.PROBE_ID / "manifest.json"
#: The probe's own files, frozen from registration on (later work adds new modules instead of changing these). The
#: shared runner and capture harness (game loop, runner, step capture) are identified by the registration commit,
#: which every game record carries in its harness block.
FILES = (
    "src/miaosuan_agent/evaluation/ps1_model.py",
    "src/miaosuan_agent/experiments/ps1_probe_hook.py",
    "src/miaosuan_agent/evaluation/ps1_probe.py",
    "scripts/ps1_probe_analysis.py",
    "scripts/ps1_study.py",
    "scripts/ps1_posthoc.py",
    "scripts/ps1_probe_verify_hook.py",
    "scripts/ps1_probe_dryrun.py",
)
TESTS = (
    "tests/test_ps1_probe_hook.py",
    "tests/test_ps1_probe_analysis.py",
    "tests/fixtures/ps1_probe_engine.py",
    "tests/fixtures/ps1_trajectories.py",
    "tests/test_ps1_model.py",
    "tests/test_ps1_study.py",
    "tests/test_ps1_posthoc.py",
    "scripts/mutate_ps1_probe.py",
)
#: Digests of the inputs the analyses read (private files: computed on the evaluation server, 2026-10-02).
PRIVATE_INPUTS = {
    "sprint2_split_record_sha256": "bfd058bf2a4b444823ea808762bf0af67b2406a7515f8cde993135d2f188845a",
    "sprint2_baseline_record_sha256": "00abf939cbf2641395a0e62715a1b81793b09b6079db67e95d914f5c40837234",
    "sprint2_split_capture_sha256": "51f571c75f9412a4495341124ee5d3054b35324d7b11bd76c01d015de8175e87",
    "sprint2_split_windows_sha256": "c45902f71334eb564b51f0958b78954e737437f8b9fefedf82995339fe5f5d7c",
    "sprint3_a2_certificate_sha256": "64906eb7181ebba413f4e2092fcb1c69c18fb6a46ebe46ed6b1b368953b0fe58",
}
PUBLIC_INPUTS = ("evaluation/ps1-design-1/summary.json", "evaluation/ps1-design-1/posthoc.json",
                 "evaluation/t1r-diagnosis-1/analysis.json", "evaluation/ps1-engine-probe-1/mutation.json")


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def current_scheduler() -> str:
    spec = importlib.util.spec_from_file_location("run_game_pool", REPO_ROOT / "scripts" / "run_game_pool.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scheduler_identity()


def build() -> Dict[str, Any]:
    screen = load(REPO_ROOT / "evaluation" / pp.SCREEN_ID / "manifest.json")
    results_path = REPO_ROOT / "evaluation" / "runtime-thread-qualification-1" / "results.json"
    files = {rel: pp.normalized_sha256(REPO_ROOT / rel) for rel in FILES}
    tests = {rel: pp.normalized_sha256(REPO_ROOT / rel) for rel in TESTS}
    inputs = dict(PRIVATE_INPUTS)
    inputs.update({f"{rel} (normalised sha256)": pp.normalized_sha256(REPO_ROOT / rel) for rel in PUBLIC_INPUTS})
    manifest = pp.build(screen, mf.digest(screen), load(results_path),
                        hashlib.sha256(results_path.read_bytes()).hexdigest(), files, tests, inputs)
    if manifest["execution"]["scheduler"] != current_scheduler():
        raise SystemExit("the production scheduler of this checkout is not the qualified one")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed manifest instead of writing")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} differs from a fresh build", file=sys.stderr)
            return 1
        print(f"{OUT} matches a fresh build (canonical SHA-256 {mf.digest(json.loads(text))})")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} (canonical SHA-256 {mf.digest(json.loads(text))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
