"""Build (or check) the registered manifest of the baseline-v1 variance study.

    python scripts/build_variance_study_manifest.py [--check]

Inputs are committed files only: the frozen baseline-v1 evaluation manifest and results, the pinned
historical records (scripts/pin_study_history.py) and the baseline-v1 policy sources. Generation is
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

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import variance_study as vs  # noqa: E402
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID  # noqa: E402

V1 = REPO_ROOT / "evaluation" / CANDIDATE_ID
OUT_DIR = REPO_ROOT / "evaluation" / vs.STUDY_NAME


def build() -> dict:
    v1_manifest = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
    results_bytes = (V1 / "results.json").read_bytes()
    history = json.loads((OUT_DIR / "historical-records.json").read_text(encoding="utf-8"))
    digest, files = policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)
    return vs.build(v1_manifest, json.loads(results_bytes.decode("utf-8")), hashlib.sha256(results_bytes).hexdigest(),
                    history, files, digest, OCCUPY_RESERVATION_SOURCES)


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
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                   newline="\n")
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={mf.digest(manifest)} "
          f"new games={len(manifest['schedule'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
