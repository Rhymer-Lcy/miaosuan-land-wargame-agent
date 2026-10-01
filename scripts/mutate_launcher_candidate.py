"""Mutation test of the launcher-dependent shoot-reservation candidate.

    python scripts/mutate_launcher_candidate.py [--check]

Applies each registered mutation to ``src/miaosuan_agent/experiments/launcher_reservation.py`` in a temporary copy
of the package, runs ``tests.test_launcher_reservation`` against it in a fresh process and records whether the tests
failed (the mutation was killed). Every mutation's original text must occur exactly once. Writes (or with
``--check`` compares) ``evaluation/launcher-dependency-counterfactual-1/mutation.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/miaosuan_agent/experiments/launcher_reservation.py")
OUT = REPO_ROOT / "evaluation" / "launcher-dependency-counterfactual-1" / "mutation.json"
MUTATIONS = [
    ("no launcher exclusion", "dependent = [c for c in remaining if self._relations.get(target_of(c)) in targets]",
     "dependent = []"),
    ("inverted relation test", "dependent = [c for c in remaining if self._relations.get(target_of(c)) in targets]",
     "dependent = [c for c in remaining if self._relations.get(target_of(c)) not in targets]"),
    ("claims options the shoot-target reservation excludes",
     "dependent = [c for c in remaining if self._relations.get(target_of(c)) in targets]",
     "dependent = [c for c in engage if self._relations.get(target_of(c)) in targets]"),
    ("displacement judged on all options", "displaced = bool(excluded) and target_of(best(offered)) in targets",
     "displaced = bool(excluded) and target_of(best(engage)) in targets"),
    ("effect never recorded", "displaced_dependent = baseline is not None and baseline in dependent",
     "displaced_dependent = False"),
    ("rejected shots reserve", "if selected.category is Category.ENGAGE and gate.check([proposal], context, self.router).accepted:",
     "if selected.category is Category.ENGAGE:"),
    ("position off by one", "positions[target_of(selected)] = len(proposals) - 1",
     "positions[target_of(selected)] = len(proposals)"),
    ("bools accepted as relations", "if isinstance(value, int) and not isinstance(value, bool):",
     "if isinstance(value, int):"),
    ("strings coerced to relations", "if isinstance(value, int) and not isinstance(value, bool):",
     "if isinstance(value, (int, str)) and not isinstance(value, bool):"),
    ("relations kept after the step", "            self._relations, self._relation_notes = {}, ()\n        if isinstance",
     "            pass\n        if isinstance"),
    ("reason code reused", 'LAUNCHER_TARGET_RESERVED = "same-step-launcher-target-reserved"',
     'LAUNCHER_TARGET_RESERVED = "same-step-shoot-target-reserved"'),
    ("diagnostics reordered", "        diagnostics.extend(self._relation_notes)  # after baseline-v2's own, so its order is unchanged\n",
     "        diagnostics.sort()\n        diagnostics.extend(self._relation_notes)\n"),
]


def run(mutation: tuple) -> dict:
    name, old, new = mutation
    text = (REPO_ROOT / SOURCE).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(REPO_ROOT / "src", root / "src")
        shutil.copytree(REPO_ROOT / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        (root / SOURCE).write_text(text.replace(old, new), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONPATH"] = str(root / "src")
        done = subprocess.run([sys.executable, "-m", "unittest", "tests.test_launcher_reservation"], cwd=root, env=env,
                              capture_output=True, text=True, timeout=600)
    return {"mutation": name, "killed": done.returncode != 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = [run(m) for m in MUTATIONS]
    payload = {"schema": "miaosuan-launcher-mutation/1", "source": SOURCE.as_posix(),
               "source_sha256": hashlib.sha256((REPO_ROOT / SOURCE).read_bytes()).hexdigest(),
               "tests": "tests.test_launcher_reservation", "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("mutation results identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']}: "
          + ", ".join(r["mutation"] for r in results if not r["killed"]) if payload["killed"] != payload["total"]
          else f"killed {payload['killed']} of {payload['total']}")
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
