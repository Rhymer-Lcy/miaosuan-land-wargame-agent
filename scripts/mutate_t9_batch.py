"""Mutation test of the Sprint 11 offline candidate ``t9-batch-capacity-v3`` and its replay analysis.

    python scripts/mutate_t9_batch.py [--check]

Copies ``src``, ``tests`` and ``scripts`` to a temporary directory, first runs the two test modules unmutated (they
must pass, or every later kill would be vacuous), then applies each registered mutation to its source file, runs the
tests in a fresh process and records whether they failed (the mutation was killed). Every mutation's original text
must occur exactly once. Writes (or with ``--check`` compares) ``evaluation/s11-batch-allocator/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t9_batch.py")
ANALYSIS = Path("src/miaosuan_agent/evaluation/t9_batch_replay.py")
TESTS = ("tests.test_t9_batch", "tests.test_t9_batch_replay")
OUT = REPO_ROOT / "evaluation" / "s11-batch-allocator" / "mutation.json"
MUTATIONS = [
    # -- first-come order restored ----------------------------------------------------------------------------------
    (CANDIDATE, "rank by emission order",
     "    return (not claimant.feasible, unrated, claimant.free_flow or 0, claimant.cost or 0.0, len(claimant.path),\n"
     "            claimant.obj_id)",
     "    return (not claimant.feasible, claimant.index)"),
    (CANDIDATE, "objective group left in emission order", "        ranked = sorted(group, key=key)",
     "        ranked = list(group)"),
    (CANDIDATE, "staging processed in emission order",
     "    rest = sorted((c for c in claimants.values() if c.obj_id not in out.selected), key=key)",
     "    rest = [c for c in claimants.values() if c.obj_id not in out.selected]"),
    (CANDIDATE, "ties broken by emission order",
     "    return (not claimant.feasible, unrated, claimant.free_flow or 0, claimant.cost or 0.0, len(claimant.path),\n"
     "            claimant.obj_id)",
     "    return (not claimant.feasible, unrated, claimant.free_flow or 0, claimant.cost or 0.0, len(claimant.path),\n"
     "            claimant.index)"),
    (CANDIDATE, "rank by route cost only (speed ignored)",
     "    return (not claimant.feasible, unrated, claimant.free_flow or 0, claimant.cost or 0.0, len(claimant.path),\n"
     "            claimant.obj_id)",
     "    return (not claimant.feasible, unrated, claimant.cost or 0.0, len(claimant.path), claimant.obj_id)"),
    # -- reservations that cannot arrive -----------------------------------------------------------------------------
    (CANDIDATE, "movers that cannot arrive still hold places",
     "        if bound is not None and end is not None and now + bound >= end:",
     "        if False:"),
    (CANDIDATE, "mover bound includes the hex being entered", "        bound = None if times is None else sum(times[1:])",
     "        bound = None if times is None else sum(times)"),
    (CANDIDATE, "late claimants selectable", "        chosen = [c for c in ranked if c.feasible][:max(free, 0)]",
     "        chosen = [c for c in ranked if c.free_flow is not None][:max(free, 0)]"),
    (CANDIDATE, "end of game off by one", "        elif end is not None and now + free_flow >= end:",
     "        elif end is not None and now + free_flow > end:"),
    (CANDIDATE, "missing clock treated as the end", "    end = time_info.max_step if is_int(time_info.max_step) else None",
     "    end = time_info.max_step if is_int(time_info.max_step) else time_info.cur_step"),
    # -- capacity and incumbents -------------------------------------------------------------------------------------
    (CANDIDATE, "counted movers ignored", "        free = capacity - row[\"physical\"] - row[\"movers\"]",
     "        free = capacity - row[\"physical\"]"),
    (CANDIDATE, "standing units ignored", "        free = capacity - row[\"physical\"] - row[\"movers\"]",
     "        free = capacity - row[\"movers\"]"),
    (CANDIDATE, "staging hex allowed a fourth unit", "STAGE_CAP = CAPACITY - 1", "STAGE_CAP = CAPACITY"),
    (CANDIDATE, "staged endpoints not counted", "        endpoints[staged_path[-1]] += 1\n", ""),
    (CANDIDATE, "staging allowed on an objective", "                if hex_ not in cities and endpoints[hex_] < stage_cap:",
     "                if endpoints[hex_] < stage_cap:"),
    # -- failure and gate --------------------------------------------------------------------------------------------
    (CANDIDATE, "rejected staged move emitted anyway", "            final[position] = None\n            out.staged.pop",
     "            out.staged.pop"),
    (CANDIDATE, "internal failure falls back to baseline-v2",
     "        return Allocation(tuple(kept), changes, error=f\"{type(exc).__name__}: {exc}\"[:300])",
     "        return Allocation(actions, changes, error=f\"{type(exc).__name__}: {exc}\"[:300])"),
    (CANDIDATE, "unreadable free-flow time selectable",
     "        claimants[obj_id] = Claimant(obj_id, dest, path, free_flow, cost, status == \"no place under capacity\", index,",
     "        claimants[obj_id] = Claimant(obj_id, dest, path, free_flow, cost, status != \"cannot arrive before the end\", index,"),
    # -- replay analysis ---------------------------------------------------------------------------------------------
    (ANALYSIS, "cross-objective test blind to other objectives",
     "        elif after and after[-1] in cities and after[-1] != before[-1]:\n            row[\"cross_objective\"] += 1\n",
     ""),
    (ANALYSIS, "prefix test accepts any shortening",
     "            if not (1 <= len(after) < len(before) and after == before[:len(after)]) or after[-1] in cities:",
     "            if after[-1] in cities:"),
    (ANALYSIS, "unrelated actions compared without order",
     "    row[\"unrelated_changed\"] = int([dict(a) for a in rest_base] != [dict(a) for a in rest_out])",
     "    row[\"unrelated_changed\"] = int(len(rest_base) != len(rest_out))"),
    (ANALYSIS, "late owners never counted", "            if ff is not None and end is not None and time_info.cur_step + ff >= end:\n"
     "                row[\"late_owners\"] += 1", "            pass"),
    (ANALYSIS, "caused capacity never counted", "        if granted and counted + granted > capacity:",
     "        if False:"),
    (ANALYSIS, "permutation check compares counts only",
     "    return all(outcome([baseline[i] for i in order]) == reference for order in orders)",
     "    return all(len(outcome([baseline[i] for i in order])) == len(reference) for order in orders)"),
    (ANALYSIS, "move listing never counted", "        out[f\"{state}: move listed\"] += MOVE in keys",
     "        out[f\"{state}: move listed\"] += 0"),
    (ANALYSIS, "early arrivals reported as exact",
     "\"never\" if arrived is None else \"early\" if arrived < predicted else",
     "\"never\" if arrived is None else"),
    (ANALYSIS, "remaining bound includes the hex being entered",
     "            out[\"arrived sooner than the bound\"] += int(arrived - k < sum(times[1:]))",
     "            out[\"arrived sooner than the bound\"] += int(arrived - k < sum(times))"),
    (ANALYSIS, "phantom places blamed on the candidate too",
     "        elif late_granted[dest] or (name in COUNTS_EVERY_MOVER and before.get(dest, {}).get(\"phantom\", 0)):",
     "        elif late_granted[dest] or before.get(dest, {}).get(\"phantom\", 0):"),
]


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    return {"mutation": name, "file": source.as_posix(), "killed": not tests_pass({source: text.replace(old, new)})}


def tests_pass(replacements) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for folder in ("src", "tests", "scripts"):
            shutil.copytree(REPO_ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
        for source, text in replacements.items():
            (root / source).write_text(text, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONPATH"] = str(root / "src")
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env, capture_output=True,
                              text=True, timeout=900)
    return done.returncode == 0


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not tests_pass({}):
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous")
    results = [run(m) for m in MUTATIONS]
    payload = {"schema": "miaosuan-s11-batch-mutation/1",
               "sources": {p.as_posix(): digest(p) for p in (CANDIDATE, ANALYSIS)},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']}")
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
