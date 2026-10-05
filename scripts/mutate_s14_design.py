"""Mutation test of the Sprint 14 candidates and design analysis (``docs/SPRINT14_REDISTRIBUTION.md``).

    python scripts/mutate_s14_design.py [--check]

Copies ``src``, ``tests`` and ``scripts`` to a temporary directory, first runs the test modules unmutated (they must
pass, or every later kill would be vacuous), then plants each registered defect into the candidate module or the
analysis module, runs the tests in a fresh process and records whether they failed (the defect was caught). Every
planted defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s14-redistribution-design/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t9_redistribution.py")
ANALYSIS = Path("src/miaosuan_agent/evaluation/s14_design.py")
TESTS = ("tests.test_t9_redistribution", "tests.test_s14_design")
OUT = REPO_ROOT / "evaluation" / "s14-redistribution-design" / "mutation.json"
MUTATIONS = [
    # -- candidate rules (protocol section 3)
    (CANDIDATE, "claimants that cannot arrive are redirected",
     "    overflow = sorted((c for c in claimants.values() if c.obj_id not in out.selected and c.status == FULL),",
     "    overflow = sorted((c for c in claimants.values() if c.obj_id not in out.selected),"),
    (CANDIDATE, "overflow ranked by emission order", "                      key=free_flow_key)\n    if rule is not None",
     "                      key=lambda c: c.index)\n    if rule is not None"),
    (CANDIDATE, "detour bound exclusive", "        if cost > DETOUR * base_cost:", "        if cost >= DETOUR * base_cost:"),
    (CANDIDATE, "redirect arrival not tested", "        if end is not None and now + free_flow >= end:\n            dropped[LATE]",
     "        if False:\n            dropped[LATE]"),
    (CANDIDATE, "horizon exclusive", "        if rule.horizon is not None and free_flow > rule.horizon:",
     "        if rule.horizon is not None and free_flow >= rule.horizon:"),
    (CANDIDATE, "corridor bound ignored",
     "        if rule.min_prefix is not None and prefix < rule.min_prefix * len(claimant.path):",
     "        if False:"),
    (CANDIDATE, "corridor bound measured on the redirect's own route",
     "        prefix = shared_prefix(claimant.path, path)", "        prefix = shared_prefix(path, path)"),
    (CANDIDATE, "ranks swapped", "        key = (cost / weight, cost, coord) if rule.rank == \"value\" else (cost, coord)",
     "        key = (cost, coord) if rule.rank == \"value\" else (cost / weight, cost, coord)"),
    (CANDIDATE, "greedy fills a full objective",
     "                open_ = [o for o in options[claimant.obj_id] if counted[o.objective] < CAPACITY]",
     "                open_ = [o for o in options[claimant.obj_id] if counted[o.objective] <= CAPACITY]"),
    (CANDIDATE, "redirects not counted", "                counted[choice.objective] += 1\n", ""),
    (CANDIDATE, "stage-1 selections not counted", "            counted[coord] += 1\n", ""),
    (CANDIDATE, "batch exceeds the free places", "        add(node_of_objective[coord], sink, CAPACITY - counted[coord], 0)",
     "        add(node_of_objective[coord], sink, CAPACITY - counted[coord] + 1, 0)"),
    (CANDIDATE, "batch maximises cost", "                            int(round(option.key[0] * WEIGHT_SCALE)))",
     "                            -int(round(option.key[0] * WEIGHT_SCALE)))"),
    (CANDIDATE, "rejected redirect staged instead of withheld",
     "                out.withheld[obj_id] = \"redirect rejected by the gate\"",
     "                out.staged[obj_id] = ()"),
    (CANDIDATE, "late claimant boundary exclusive", "        elif end is not None and now + free_flow >= end:\n            status = LATE",
     "        elif end is not None and now + free_flow > end:\n            status = LATE"),
    (CANDIDATE, "fail-closed keeps the moves",
     "                changes.append({\"kind\": \"fail-closed\", \"obj_id\": action.get(\"obj_id\")})\n                continue",
     "                changes.append({\"kind\": \"fail-closed\", \"obj_id\": action.get(\"obj_id\")})"),
    (CANDIDATE, "phantom movers hold places", "        if bound is not None and end is not None and now + bound >= end:",
     "        if False:"),
    # -- analysis: per-decision checks (protocol sections 5 and 6)
    (ANALYSIS, "unrelated actions not compared", "    if other_actions(emitted, ground) != other_actions(base_actions, ground):",
     "    if False:"),
    (ANALYSIS, "invented moves not counted", "    violations[\"invented move\"] += len(set(out_moves) - set(base_moves))",
     "    violations[\"invented move\"] += 0"),
    (ANALYSIS, "capacity check loosened",
     "        if added and row.get(\"physical\", 0) + row.get(\"movers\", 0) + added > CAPACITY:",
     "        if added and row.get(\"physical\", 0) + row.get(\"movers\", 0) + added > 2 * CAPACITY:"),
    (ANALYSIS, "reachability not checked", "                if ff is None or (end is not None and now + ff >= end):",
     "                if ff is None:"),
    (ANALYSIS, "redirect route not compared", "            if target is None or target[0] != path:",
     "            if target is None:"),
    (ANALYSIS, "staging prefix not checked",
     "            if not (0 < len(path) < len(base_path) and path == base_path[:len(path)] and path[-1] not in cities):",
     "            if not (0 < len(path)):"),
    (ANALYSIS, "order differences never counted", "                    counts[\"order_differences\"] += 1", "                    pass"),
    (ANALYSIS, "repeat differences never counted", "            counts[\"repeat_differences\"] += 1", "            pass"),
    # -- analysis: gate, rubric, disposition (sections 7 to 9)
    (ANALYSIS, "share threshold exclusive", "    ok9 = (all(r is not None and r >= rules[\"restore_share_ratio_min\"]",
     "    ok9 = (all(r is not None and r > rules[\"restore_share_ratio_min\"]"),
    (ANALYSIS, "unit threshold exclusive", "           and all(n >= rules[\"restore_units_min\"] for n in units.values())",
     "           and all(n > rules[\"restore_units_min\"] for n in units.values())"),
    (ANALYSIS, "divergence threshold exclusive",
     "    ok10 = (slot_ratio is not None and slot_ratio <= rules[\"divergence_ratio_max\"]",
     "    ok10 = (slot_ratio is not None and slot_ratio < rules[\"divergence_ratio_max\"]"),
    (ANALYSIS, "certificate not required", "            and a[\"certificate_unit_decisions\"] >= a[\"v3_certificate_unit_decisions\"])",
     "            and a[\"certificate_unit_decisions\"] >= 0)"),
    (ANALYSIS, "shooters ignored", "        ok = (x[\"shooters_redirected\"] == 0 and x[\"first_decision_redirects\"] <= first_limit",
     "        ok = (True and x[\"first_decision_redirects\"] <= first_limit"),
    (ANALYSIS, "first-decision limit halves instead of thirds",
     "        first_limit = t9[\"first_decision_redirects_by_trajectory\"][\"t9-v1\"] // rules[\"adverse_first_divisor\"]",
     "        first_limit = t9[\"first_decision_redirects_by_trajectory\"][\"t9-v1\"] // 2"),
    (ANALYSIS, "latency limit doubled", "    item(\"G15_latency\", lat[\"p99\"] <= rules[\"latency_p99_ms_max\"]",
     "    item(\"G15_latency\", lat[\"p99\"] <= 2 * rules[\"latency_p99_ms_max\"]"),
    (ANALYSIS, "rubric keeps the smallest margin", "    best = max(band.values())\n    alive = [n for n in alive if band[n] == best]",
     "    best = min(band.values())\n    alive = [n for n in alive if band[n] == best]"),
    (ANALYSIS, "disposition inverted", "    if not passed:\n        return {\"disposition\": \"NO_ENGINE_CANDIDATE\"",
     "    if passed:\n        return {\"disposition\": \"NO_ENGINE_CANDIDATE\""),
]


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    return {"mutation": name, "module": source.as_posix(), "killed": not tests_pass({source: text.replace(old, new)})}


def tests_pass(replacements) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for folder in ("src", "tests", "scripts"):
            shutil.copytree(REPO_ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
        for source, text in replacements.items():
            (root / source).write_text(text, encoding="utf-8", newline="\n")
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
    sources = (CANDIDATE, ANALYSIS, Path("tests/test_t9_redistribution.py"), Path("tests/test_s14_design.py"))
    payload = {"schema": "miaosuan-s14-design-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
