"""Sprint 36 historical ``baseline-v2`` reference distributions (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 19).

    python scripts/s36_references.py [--check]

Sprint 34's rule (``scripts/s34_references.py``) unchanged - the group C records of ``baseline-v2``'s registered promotion
experiment, 15 games per scenario and condition - for Sprint 35's nine configurations plus the held-out scenario
``2010211129.C1`` and the Stage B configurations ``201033019601.C2``, ``201033019601.C3``, ``2010131194.C2`` and
``2010131194.C3``. Writes ``evaluation/s36-tactical-recovery/references.json``; runs on the evaluation server, where the
records are; ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "references.json"
SCHEMA = "miaosuan-s36-references/1"
EXTRA = ("2010431153.C1", "2010211129.C1", "201033019601.C2", "201033019601.C3", "2010131194.C2", "2010131194.C3")


def _s34():
    spec = importlib.util.spec_from_file_location("s36_ref_s34", REPO_ROOT / "scripts" / "s34_references.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build():
    s34 = _s34()
    s34.CONFIGS = s34.CONFIGS + EXTRA
    data = s34.build()
    data["schema"] = SCHEMA
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = _s34().dump(build())
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print("references identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(text[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
