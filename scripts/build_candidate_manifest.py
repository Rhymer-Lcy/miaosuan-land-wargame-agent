"""Build (or check) the registered manifest of the occupation-reservation candidate experiment.

    python scripts/build_candidate_manifest.py [--check]

Inputs are all committed files: the registered baseline-v0 manifest, results and diagnostics, the
candidate's policy sources, and the public aggregate of the counterfactual replay. Generation is
deterministic; ``--check`` rebuilds the manifest and fails unless the file on disk is identical.
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

from miaosuan_agent.evaluation import candidate_manifest as cm  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest  # noqa: E402

V0 = REPO_ROOT / "evaluation" / "baseline-v0"
OUT_DIR = REPO_ROOT / "evaluation" / cm.EVALUATION_NAME


def build() -> dict:
    v0_manifest = json.loads((V0 / "manifest.json").read_text(encoding="utf-8"))
    v0_diagnostics = json.loads((V0 / "diagnostics.json").read_text(encoding="utf-8"))
    replay_path = OUT_DIR / "counterfactual-replay.json"
    replay_bytes = replay_path.read_bytes()
    digest, files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
    return cm.build(v0_manifest, hashlib.sha256((V0 / "results.json").read_bytes()).hexdigest(), v0_diagnostics,
                    digest, files, json.loads(replay_bytes.decode("utf-8")), hashlib.sha256(replay_bytes).hexdigest())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the file instead of writing it")
    args = parser.parse_args()
    manifest = build()
    out = OUT_DIR / "manifest.json"
    if args.check:
        on_disk = json.loads(out.read_text(encoding="utf-8"))
        if on_disk != manifest:
            changed = sorted(k for k in set(on_disk) | set(manifest) if on_disk.get(k) != manifest.get(k))
            print(f"MISMATCH: {out} differs from the rebuilt manifest in {changed}", file=sys.stderr)
            return 1
        print(f"OK {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={mf.digest(manifest)}")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                   newline="\n")
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={mf.digest(manifest)} "
          f"games={len(mf.games(manifest))} gate1={len(mf.gate1_games(manifest))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
