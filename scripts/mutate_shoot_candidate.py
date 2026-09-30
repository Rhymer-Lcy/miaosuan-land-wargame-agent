"""Mutation test of the shoot-target-reservation candidate against its public tests.

    python scripts/mutate_shoot_candidate.py [--check]

The repository's files (tracked, or new and not ignored) are copied to a temporary directory; each mutant replaces exactly one fragment of the
copy's ``src/miaosuan_agent/experiments/shoot_reservation.py`` and ``tests.test_shoot_reservation`` runs
against that copy. The checkout itself is never modified. A mutant is killed when the tests fail.

Both classes are declared before running. A non-equivalent mutant changes a result the registered
behaviour fixes and must be killed. An equivalent mutant changes no decision or trace: its argument is
recorded with it and it is expected to survive; being killed would mean the argument or a test is wrong,
and fails the run like a surviving non-equivalent mutant. The outcome is written to
``evaluation/baseline-v2-candidate-shoot-target-reservation/mutation.json``; ``--check`` reruns and
compares.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = "src/miaosuan_agent/experiments/shoot_reservation.py"
TESTS = ("tests.test_shoot_reservation",)
OUT = REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "mutation.json"
SCHEMA = "miaosuan-shoot-mutation/1"
NL = chr(10)
RESERVE = "                targets[target_of(selected)] = unit.obj_id"
GATED = "            if selected.category is Category.ENGAGE and gate.check([proposal], context, self.router).accepted:"
FRESH = "        targets: Dict[int, int] = {}  # shoot target -> unit whose emitted shoot reserved it; looked up only"
EXCLUDE = "            excluded = [c for c in engage if target_of(c) in targets]"
FILTER = "                by_category[Category.ENGAGE] = [c for c in engage if target_of(c) not in targets]"
DISPLACED = "            displaced = bool(excluded) and target_of(best(engage)) in targets"

NON_EQUIVALENT = [
    ("reserve before gate acceptance", GATED, "            if selected.category is Category.ENGAGE:"),
    ("gate verdict over the step's proposals so far", GATED,
     "            if selected.category is Category.ENGAGE and gate.check(proposals, context, self.router).accepted:"),
    ("reservations not cleared per step", FRESH,
     "        targets: Dict[int, int] = self.__dict__.setdefault('_kept_targets', {})"),
    ("reservations shared across seats within a step", FRESH,
     "        targets: Dict[int, int] = SHARED.setdefault(context.cur_step, {})" + NL + "        SHARED.pop(context.cur_step - 1, None)"),
    ("weapon reserved instead of target", RESERVE, "                targets[dict(selected.params)['weapon_id']] = unit.obj_id"),
    ("next-best shoot option skipped", FILTER,
     "                by_category[Category.ENGAGE] = [] if displaced else [c for c in engage if target_of(c) not in targets]"),
    ("unit order reversed", "        for unit in context.units:", "        for unit in reversed(context.units):"),
    ("shoot ranking changed (higher target id first)", "                selected = best(options)",
     "                selected = best(options) if category is not Category.ENGAGE else min(options, key=lambda c: (c.rank[0], -c.rank[1], c.rank[2]))"),
    ("all shooting suppressed after the first shot", FILTER, "                by_category[Category.ENGAGE] = []" + NL
     + "            if targets:" + NL + "                by_category[Category.ENGAGE] = []"),
    ("two shots allowed per target", RESERVE,
     "                targets.setdefault(-target_of(selected), unit.obj_id) if -target_of(selected) not in targets else targets.setdefault(target_of(selected), unit.obj_id)"),
    ("no reservation at all", RESERVE, "                pass"),
    ("unchanged selections labelled as displaced", DISPLACED, "            displaced = bool(excluded)"),
    ("exclusion names the excluded unit as the reserver", "tuple(_excluded(c, targets[target_of(c)]) for c in excluded)",
     "tuple(_excluded(c, unit.obj_id) for c in excluded)"),
    ("inherited occupation reservation dropped", "                if category is Category.OCCUPY and unit.cur_hex in reserved:",
     "                if False:"),
    ("reservation reason missing from the no-op reason",
     '                        parts.append(f"shoot targets reserved: {ShootCoordination.TARGET_RESERVED.value}")',
     "                        pass"),
    ("displaced unit's markers dropped",
     '                detail += (("shoot_target_reserved", target_of(best(engage))), ("shoot_reservation", effect.value))',
     "                pass"),
    ("exclusions not recorded", "                shoot_reserved.append((unit.obj_id, tuple(_excluded(c, targets[target_of(c)]) for c in excluded),",
     "                (unit.obj_id, tuple(_excluded(c, targets[target_of(c)]) for c in excluded),"),
]
EQUIVALENT = [
    ("runtime r1 targets not set", "            self.router.targets = frozenset(city.coord for city in context.objectives)  # runtime r1, unchanged",
     "            pass",
     "without targets the bounded router runs the frozen full search, whose costs and paths for every objective are "
     "the bounded search's (routing-remediation-1, E3-E5); only work changes"),
    ("exclusion test on the filtered list", DISPLACED,
     "            displaced = bool(excluded) and best(engage) in excluded",
     "best(engage) is in excluded exactly when its target is reserved, since excluded holds every option with a "
     "reserved target"),
]
SHARED_PREAMBLE = ("CANDIDATE_ID = \"baseline-v2-candidate-shoot-target-reservation\"",
                   "SHARED: Dict[int, Dict[int, int]] = {}" + NL + "CANDIDATE_ID = \"baseline-v2-candidate-shoot-target-reservation\"")


def tracked_copy(destination: Path) -> None:
    """Every file git tracks or would track (not ignored): the committed tree plus any new source."""
    listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-co", "--exclude-standard"], capture_output=True,
                            text=True, check=True)
    for name in listed.stdout.splitlines():
        source = REPO_ROOT / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def killed(root: Path) -> bool:
    result = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, capture_output=True, text=True,
                            timeout=1800)
    return result.returncode != 0


def build() -> Dict[str, Any]:
    original = (REPO_ROOT / TARGET).read_bytes()
    text = original.decode("utf-8")
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="shoot-mutation-") as temporary:
        root = Path(temporary)
        tracked_copy(root)
        target = root / TARGET
        target.write_bytes(original)
        if killed(root):
            raise SystemExit("the unmutated copy fails its tests")
        mutants = [(name, old, new, None) for name, old, new in NON_EQUIVALENT] + list(EQUIVALENT)
        for name, old, new, argument in mutants:
            if text.count(old) != 1:
                raise SystemExit(f"mutant {name!r}: the fragment occurs {text.count(old)} times, not once")
            mutated = text.replace(old, new)
            if "SHARED." in new:
                mutated = mutated.replace(*SHARED_PREAMBLE)
            target.write_bytes(mutated.encode("utf-8"))
            try:
                outcome = "killed" if killed(root) else "survived"
            finally:
                target.write_bytes(original)
            row = {"mutant": name, "class": "non-equivalent" if argument is None else "equivalent", "outcome": outcome,
                   "expected": "killed" if argument is None else "survived"}
            if argument is not None:
                row["argument"] = argument
            rows.append(row)
            print(f"{outcome:9s} {row['class']:15s} {name}", flush=True)
    unexpected = [r["mutant"] for r in rows if r["outcome"] != r["expected"]]
    return {"schema": SCHEMA, "target": TARGET, "target_sha256": hashlib.sha256(original).hexdigest(),
            "tests": list(TESTS), "mutants": rows,
            "non_equivalent": {"total": len(NON_EQUIVALENT),
                               "killed": sum(1 for r in rows if r["class"] == "non-equivalent" and r["outcome"] == "killed")},
            "equivalent": {"total": len(EQUIVALENT),
                           "survived": sum(1 for r in rows if r["class"] == "equivalent" and r["outcome"] == "survived")},
            "unexpected": unexpected, "pass": not unexpected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}; pass={result['pass']}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
