"""Build (or check) the registered evaluation manifest from a verified local SDK archive.

    python scripts/build_evaluation_manifest.py --sdk-archive ZIP [--out FILE] [--check]

The manifest records the scenario survey, the selection, the conditions, the caps, the gate
criteria, the metric definitions and the identity of the policy code. Generation is
deterministic: ``--check`` rebuilds it and fails unless the file on disk has exactly the same
content. The SDK archive is only read.
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

from miaosuan_agent import sdk_provenance as prov  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402
from miaosuan_agent.evaluation.selection import select, survey  # noqa: E402
from miaosuan_agent.sdk_data import map_paths, open_data_archive  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "evaluation" / "baseline-v0" / "manifest.json"


def build(sdk_archive: Path) -> dict:
    data = open_data_archive(sdk_archive)
    facts = survey(data)
    picks = select(facts)
    digests = {}
    for pick in picks:
        members = {"scenario": f"Data/scenarios/{pick.scenario_id}.json"}
        members.update({role: f"Data/maps/map_{pick.map_id}/{path.name}"
                        for role, path in map_paths(Path("."), pick.map_id).items()})
        digests[pick.scenario_id] = {role: hashlib.sha256(data.read(name)).hexdigest() for role, name in members.items()}
    manifest = mf.build(facts, picks, digests, prov.SDK_ARCHIVE_SHA256, prov.ENGINE_VERSION)
    source, files = policy_source_digest()
    manifest["policy_source"] = {"sha256": source, "files": files,
                                 "rule": "sorted relative paths, CRLF normalized to LF; see evaluation/identity.py"}
    return manifest


def render(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sdk-archive", type=Path, default=prov.default_archive_dir(REPO_ROOT) / prov.SDK_ARCHIVE_NAME)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="compare with the file instead of writing it")
    args = parser.parse_args()
    manifest = build(args.sdk_archive)
    text = render(manifest)
    if args.check:
        on_disk = json.loads(args.out.read_text(encoding="utf-8"))
        if on_disk != manifest:
            changed = sorted(k for k in set(on_disk) | set(manifest) if on_disk.get(k) != manifest.get(k))
            print(f"MISMATCH: {args.out} differs from the rebuilt manifest in {changed}", file=sys.stderr)
            return 1
        print(f"OK {args.out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={mf.digest(manifest)}")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={mf.digest(manifest)} "
          f"games={len(mf.games(manifest))} gate1={len(mf.gate1_games(manifest))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
