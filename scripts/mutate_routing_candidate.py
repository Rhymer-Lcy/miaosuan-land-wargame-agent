"""Mutation test of the routing candidate against the public routing tests (routing-remediation-1, E4).

    python scripts/mutate_routing_candidate.py [--check]

The tracked files are copied to a temporary directory; each mutant replaces exactly one fragment of the
copy's ``src/miaosuan_agent/experiments/routing_bounded.py`` and the routing tests
(``tests.test_routing_bounded``, ``tests.test_routing_contract``) run against that copy. The checkout
itself is never modified. A mutant is killed when the tests fail.

Two classes are declared before running. A non-equivalent mutant changes some result the registered
contract fixes and must be killed. An equivalent mutant changes no result: its argument is recorded
with it, and it is expected to survive; being killed would mean the argument or a test is wrong, and
fails the run like a surviving non-equivalent mutant. The outcome is written to
``evaluation/routing-remediation-1/mutation.json``; ``--check`` reruns and compares.
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
TARGET = "src/miaosuan_agent/experiments/routing_bounded.py"
TESTS = ("tests.test_routing_bounded", "tests.test_routing_contract")
OUT = REPO_ROOT / "evaluation" / "routing-remediation-1" / "mutation.json"
SCHEMA = "miaosuan-routing-mutation/1"
NL = chr(10)
KEY = "        key = (start, int(mode), blocked, targets)"
TARGETS_LINE = "            self.router.targets = frozenset(city.coord for city in context.objectives)"

NON_EQUIVALENT = [
    ("stop one target too early", "            if not remaining:" + NL + "                break",
     "            if len(remaining) <= 1:" + NL + "                break"),
    ("omit one target from the stop condition", "        remaining = set(targets)",
     "        remaining = set(sorted(targets)[1:])"),
    ("relaxation < becomes <=", "if neighbour not in cost or candidate < cost[neighbour]:",
     "if neighbour not in cost or candidate <= cost[neighbour]:"),
    ("predecessor kept from the first relaxation", "                    previous[neighbour] = node",
     "                    previous.setdefault(neighbour, node)"),
    ("movement mode ignored", "            edges = self.costs.neighbours(mode, node)",
     "            edges = self.costs.neighbours(MoveMode.VEHICLE, node)"),
    ("roadblocks dropped from the key", KEY, "        key = (start, int(mode), targets)"),
    ("targets dropped from the key", KEY, "        key = (start, int(mode), blocked)"),
    ("mode dropped from the key", KEY, "        key = (start, blocked, targets)"),
    ("roadblocks ignored in the search", "                if neighbour in blocked or neighbour in done:",
     "                if neighbour in done:"),
    ("stop before settling the last target",
     "            done.add(node)" + NL + "            remaining.discard(node)" + NL + "            if not remaining:" + NL
     + "                break",
     "            if remaining == {node}:" + NL + "                break" + NL + "            done.add(node)" + NL
     + "            remaining.discard(node)"),
    ("tentative costs exposed", "cost=MappingProxyType({node: cost[node] for node in done})", "cost=MappingProxyType(cost)"),
    ("tentative predecessors exposed",
     "previous=MappingProxyType({node: previous[node] for node in done if node in previous})",
     "previous=MappingProxyType(previous)"),
    ("policy never sets targets", TARGETS_LINE, "            pass"),
    ("targets from the first objective only", TARGETS_LINE,
     "            self.router.targets = frozenset(city.coord for city in context.objectives[:1])"),
    ("candidate keeps the frozen router",
     "        self.router = BoundedRouter(costs) if costs is not None else None", "        pass"),
]
EQUIVALENT = [
    ("duplicate-pop guard removed", "            if node in done:" + NL + "                continue" + NL, "",
     "a stale heap entry has a larger distance than the hex's settled cost; re-expanding it can offer no neighbour a "
     "strictly lower cost (entry costs are positive and float addition is monotone), and the stop test is unaffected"),
    ("settle and discard swapped", "            done.add(node)" + NL + "            remaining.discard(node)",
     "            remaining.discard(node)" + NL + "            done.add(node)",
     "two independent operations on different sets, with nothing between them"),
    ("memo capacity 1", "memo_size: int = 32", "memo_size: int = 1",
     "every memo entry is a pure function of its full key, so recomputation returns an equal result; only work changes"),
    ("mode kept as an enum in the key", KEY, "        key = (start, mode, blocked, targets)",
     "MoveMode is an IntEnum: each member hashes and compares equal to its integer value"),
    ("settled neighbours not skipped", "                if neighbour in blocked or neighbour in done:",
     "                if neighbour in blocked:",
     "a settled neighbour's cost is at most the current distance, so distance plus a positive entry cost is never "
     "strictly lower; the relaxation never fires"),
]


def tracked_copy(destination: Path) -> None:
    listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"], capture_output=True, text=True, check=True)
    for name in listed.stdout.splitlines():
        source = REPO_ROOT / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def killed(root: Path) -> bool:
    result = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, capture_output=True, text=True,
                            timeout=1800, env=None)
    return result.returncode != 0


def build() -> Dict[str, Any]:
    original = (REPO_ROOT / TARGET).read_bytes()
    text = original.decode("utf-8")
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="routing-mutation-") as temporary:
        root = Path(temporary)
        tracked_copy(root)
        target = root / TARGET
        if killed(root):
            raise SystemExit("the unmutated copy fails its routing tests")
        mutants = [(name, old, new, None) for name, old, new in NON_EQUIVALENT] + list(EQUIVALENT)
        for name, old, new, argument in mutants:
            if text.count(old) != 1:
                raise SystemExit(f"mutant {name!r}: the fragment occurs {text.count(old)} times, not once")
            target.write_bytes(text.replace(old, new).encode("utf-8"))
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
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}; pass={result['pass']}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
