"""Build (or check) the registration of the routing remediation.

    python scripts/build_remediation_registration.py --pin-corpus   (on the machine holding the private inputs)
    python scripts/build_remediation_registration.py [--check]

``--pin-corpus`` records the SHA-256 and decision count of every private replay input under the
git-ignored ``local/`` tree in ``evaluation/routing-remediation-1/corpus.json`` (digests only, no
content). The registration itself is built from that file and the constants of
``miaosuan_agent.evaluation.runtime_remediation``; ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402

OUT_DIR = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID
PATTERNS = (("replay corpus game", "local/replay-corpus/*.jsonl.gz"),
            ("latency diagnostic state", "local/diagnostics/latency/states/*.json"),
            ("latency diagnostic captured slow state", "local/diagnostics/latency/states-engine/*.json"),
            ("latency diagnostic captures", "local/diagnostics/latency/engine/*.captures.jsonl.gz"))


def decisions(path: Path) -> int:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            lines = sum(1 for _ in handle)
        return lines - 1 if "replay-corpus" in path.as_posix() else lines
    return 1


def pin_corpus() -> dict:
    files = []
    for role, pattern in PATTERNS:
        matched = sorted(REPO_ROOT.glob(pattern))
        if not matched:
            raise SystemExit(f"no files for {pattern}: run this on the machine that holds the private inputs")
        for path in matched:
            files.append({"path": path.relative_to(REPO_ROOT).as_posix(), "role": role,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "decisions": decisions(path)})
    return {"rule": "SHA-256 of each private file; decisions = lines holding one recorded decision",
            "files": files, "decisions_total": sum(f["decisions"] for f in files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pin-corpus", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    corpus_path = OUT_DIR / "corpus.json"
    if args.pin_corpus:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        corpus_path.write_text(json.dumps(pin_corpus(), indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {corpus_path.relative_to(REPO_ROOT).as_posix()}")
    registration = rr.build(json.loads(corpus_path.read_text(encoding="utf-8")))
    out = OUT_DIR / "registration.json"
    text = json.dumps(registration, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + f"{out.relative_to(REPO_ROOT).as_posix()} "
              f"sha256(canonical)={mf.digest(registration)}")
        return 0 if same else 1
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={mf.digest(registration)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
