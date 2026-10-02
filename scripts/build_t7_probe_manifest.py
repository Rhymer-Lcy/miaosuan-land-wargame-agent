"""Build, or check, the registered manifest of the T7 mechanism probe ``t7-mechanism-probe-1``.

    python scripts/build_t7_probe_manifest.py [--check]

Every input is committed: the deployment-split screen's manifest (the scenarios, players, randomness and caps, the
reference game's seats and the head-to-head seat conventions), the shoot-reservation experiment's manifest
(``baseline-v2``'s source set), the runtime thread qualification's results (the promoted runtime and the qualified
scheduler, whose identity must equal the one this checkout computes), the line-ending-normalised SHA-256 of every
implementation and test file the probe relies on, and the digests of its private and public inputs. Generation is
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
from miaosuan_agent.evaluation import t7_probe as tp  # noqa: E402

OUT = REPO_ROOT / "evaluation" / tp.PROBE_ID / "manifest.json"
#: The probe's own files, frozen from registration on, and the shared runner it changed (the game loop and the
#: step capture are identified by the registration commit, which every game record carries).
FILES = (
    "src/miaosuan_agent/experiments/t7_idle_concealment.py",
    "src/miaosuan_agent/experiments/t7_concealment.py",
    "src/miaosuan_agent/evaluation/t7_probe.py",
    "src/miaosuan_agent/evaluation/t7_probe_metrics.py",
    "src/miaosuan_agent/evaluation/t7_probe_endpoints.py",
    "src/miaosuan_agent/evaluation/t7_visibility.py",
    "src/miaosuan_agent/evaluation/t7_candidates.py",
    "src/miaosuan_agent/evaluation/t7_audit.py",
    "scripts/t7_probe_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_evaluation.sh",
)
TESTS = (
    "tests/test_t7_concealment.py",
    "tests/test_t7_visibility.py",
    "tests/test_t7_probe_analysis.py",
    "tests/test_real_t7_probe.py",
    "tests/fixtures/t7_probe_engine.py",
    "scripts/mutate_t7_probe.py",
)
#: Digests of the private inputs the analyses read (computed on the evaluation server, 2026-10-03 +08:00): the
#: reference game (Sprint 2 game b, session 2459; the record's digest equals the one pinned by ps1-engine-probe-1 and
#: the capture's equal those recorded by t7-design-1), the private premise (the units of the predicted orders), and
#: the Sprint 1 records of the same configuration read by the dry run.
PRIVATE_INPUTS = {
    "reference_record_sha256": "00abf939cbf2641395a0e62715a1b81793b09b6079db67e95d914f5c40837234",
    "reference_capture_sha256": "f2403356026cceb871dc16d78109164a9ff3031e07fdb70a24831f99a4b3ba11",
    "reference_windows_sha256": "10bfab15fc7ccc43c9000f03e86432caef419fe2912a103bf711d80a866d69de",
    "premise_private_sha256": "433a80300bee0f59885eadb32492e176c881c8c207b0de24b4cbd82edcffb41c",
    "sprint1_b_x01_record_sha256": "23f013dc331f1ee63d0dbd79f12b511c3d9e8e42a99a2ffb7b7a99100cabc2f9",
    "sprint1_b_x02_record_sha256": "3cbbd5564b9f0e0805e22911eec0eb74accbc23a924e30a4b4f545d62bfa8d1a",
    "sprint1_b_x03_record_sha256": "fa89a06c2be921fb12298237158dd8c6a1a00f0c42f2617b28f237d5a51b6a89",
}
PUBLIC_INPUTS = (
    "evaluation/t7-mechanism-probe-1/calibration.json",
    "evaluation/t7-mechanism-probe-1/premise.json",
    "evaluation/t7-mechanism-probe-1/equivalence.json",
    "evaluation/t7-mechanism-probe-1/dryrun.json",
    "evaluation/t7-mechanism-probe-1/mutation.json",
    "evaluation/t7-design-1/gates.json",
    "evaluation/t7-design-1/shadow.json",
    "evaluation/routing-remediation-1/corpus.json",
    "docs/T7_SCREEN_PROPOSAL.md",
)


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def current_scheduler() -> str:
    spec = importlib.util.spec_from_file_location("run_game_pool", REPO_ROOT / "scripts" / "run_game_pool.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scheduler_identity()


def build() -> Dict[str, Any]:
    screen = load(REPO_ROOT / "evaluation" / tp.SCREEN_ID / "manifest.json")
    shoot = load(REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "manifest.json")
    results_path = REPO_ROOT / "evaluation" / "runtime-thread-qualification-1" / "results.json"
    files = {rel: tp.normalized_sha256(REPO_ROOT / rel) for rel in FILES}
    tests = {rel: tp.normalized_sha256(REPO_ROOT / rel) for rel in TESTS}
    inputs = dict(PRIVATE_INPUTS)
    inputs.update({f"{rel} (normalised sha256)": tp.normalized_sha256(REPO_ROOT / rel) for rel in PUBLIC_INPUTS})
    manifest = tp.build(screen, mf.digest(screen), shoot, mf.digest(shoot), load(results_path),
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
