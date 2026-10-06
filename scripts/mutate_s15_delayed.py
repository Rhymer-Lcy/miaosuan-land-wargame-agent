"""Mutation test of the Sprint 15 candidates and analysis (``docs/SPRINT15_DELAYED_REDISTRIBUTION.md``).

    python scripts/mutate_s15_delayed.py [--check]

Copies ``src``, ``tests`` and ``scripts`` to a temporary directory, first runs the test modules unmutated (they must
pass, or every later kill would be vacuous), then plants each registered defect into the candidate module or the
analysis module, runs the tests in a fresh process and records whether they failed (the defect was caught). Every
planted defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s15-delayed-redistribution/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t9_delayed.py")
ANALYSIS = Path("src/miaosuan_agent/evaluation/s15_delayed.py")
TESTS = ("tests.test_t9_delayed", "tests.test_s15_delayed")
OUT = REPO_ROOT / "evaluation" / "s15-delayed-redistribution" / "mutation.json"
MUTATIONS = [
    # -- triggers (protocol section 4)
    (CANDIDATE, "repeat threshold exclusive", "        return same and record[COUNT] + 1 >= rule.count",
     "        return same and record[COUNT] + 1 > rule.count"),
    (CANDIDATE, "repeat ignores the source", "        return same and record[COUNT] + 1 >= rule.count",
     "        return record[COUNT] + 1 >= rule.count"),
    (CANDIDATE, "stable ignores the alternative", "        return same and best != 0 and record[ALTERNATIVE] == best",
     "        return same and best != 0"),
    (CANDIDATE, "post-stage counts an emitted, not a completed, staging move",
     "        return bool(record[DONE]) and (not rule.same_source or record[STAGE_SOURCE] == source)",
     "        return bool(record[STAGED]) and (not rule.same_source or record[STAGE_SOURCE] == source)"),
    (CANDIDATE, "post-stage-same ignores the source",
     "        return bool(record[DONE]) and (not rule.same_source or record[STAGE_SOURCE] == source)",
     "        return bool(record[DONE])"),
    (CANDIDATE, "saturated ignores the previous observation",
     "        return same and saturated and bool(record[SATURATED])", "        return same and saturated"),
    (CANDIDATE, "redirect flag ignored (unbounded recourse)", "    if record is None or record[REDIRECTED]:",
     "    if record is None:"),
    # -- memory updates
    (CANDIDATE, "record survives a move to an objective",
     "        elif path and path[-1] in cities:\n            reason = \"moving to an objective\"",
     "        elif False:\n            reason = \"moving to an objective\""),
    (CANDIDATE, "record survives standing on an objective",
     "        elif not path and unit.cur_hex in cities:\n            reason = \"standing on an objective\"",
     "        elif False:\n            reason = \"standing on an objective\""),
    (CANDIDATE, "capture of the source does not end the episode",
     "        if record[SOURCE] in cities and cities[record[SOURCE]].flag == faction:", "        if False:"),
    (CANDIDATE, "capture of the source wipes the staging fact",
     "            for index in (SOURCE, COUNT, ALTERNATIVE, SATURATED, REDIRECTED, FIRST):",
     "            for index in range(len(FIELD_NAMES)):"),
    (CANDIDATE, "staging completion detected away from the endpoint",
     "        if record[STAGED] and not path and unit.cur_hex == record[STAGED]:",
     "        if record[STAGED] and not path:"),
    (CANDIDATE, "a new source does not reset the count",
     "            record[SOURCE], record[COUNT], record[FIRST] = claimant.objective, 0, now",
     "            record[SOURCE], record[FIRST] = claimant.objective, now"),
    (CANDIDATE, "a new source keeps the redirect flag", "            record[REDIRECTED] = 0\n", ""),
    (CANDIDATE, "redirect not remembered", "            record[REDIRECTED] = 1", "            record[REDIRECTED] = 0"),
    (CANDIDATE, "staging not remembered",
     "            record[STAGED], record[STAGE_SOURCE], record[DONE] = out.staged[obj_id][-1], claimant.objective, 0",
     "            pass"),
    (CANDIDATE, "a place given does not end the record", "        if obj_id in out.selected or claimant.status != FULL:",
     "        if claimant.status != FULL:"),
    (CANDIDATE, "alternative not recorded", "        record[ALTERNATIVE] = out.best.get(obj_id, 0)",
     "        record[ALTERNATIVE] = 0"),
    (CANDIDATE, "recorded saturation counts movers",
     "        record[SATURATED] = int(row[\"physical\"] >= CAPACITY and row[\"movers\"] == 0)",
     "        record[SATURATED] = int(row[\"physical\"] + row[\"movers\"] >= CAPACITY)"),
    (CANDIDATE, "current saturation counts movers",
     "            saturated = row[\"physical\"] >= CAPACITY and row[\"movers\"] == 0",
     "            saturated = row[\"physical\"] + row[\"movers\"] >= CAPACITY"),
    (CANDIDATE, "episode counter not capped", "        record[COUNT] = min(record[COUNT] + 1, COUNT_CAP)",
     "        record[COUNT] = record[COUNT] + 1"),
    (CANDIDATE, "decode accepts unknown fields", "        if index >= len(FIELD_NAMES):", "        if index >= FIELDS:"),
    (CANDIDATE, "failed memory update keeps the records",
     "        ended = {unit_id: \"memory update failed\" for unit_id in records}\n        records = {}",
     "        ended = {unit_id: \"memory update failed\" for unit_id in records}"),
    (CANDIDATE, "fail-closed loses the memory",
     "        out = Allocation(tuple(kept), encode(records), changes, error=f\"{type(exc).__name__}: {exc}\"[:300])",
     "        out = Allocation(tuple(kept), (), changes, error=f\"{type(exc).__name__}: {exc}\"[:300])"),
    # -- allocation
    (CANDIDATE, "everyone switch ignored", "            if everyone or (rule is not None and eligible(",
     "            if (rule is not None and eligible("),
    (CANDIDATE, "redirects not counted against capacity",
     "            counted[choice.objective] += 1\n            out.redirected[claimant.obj_id] = choice",
     "            out.redirected[claimant.obj_id] = choice"),
    (CANDIDATE, "overflow in emission order",
     "    overflow = sorted((c for c in claimants.values() if c.obj_id not in out.selected and c.status == FULL),\n"
     "                      key=free_flow_key)\n    out.overflow",
     "    overflow = sorted((c for c in claimants.values() if c.obj_id not in out.selected and c.status == FULL),\n"
     "                      key=lambda c: c.index)\n    out.overflow"),
    # -- analysis: gate items (section 7), adequacy (8), rubric (9), disposition (10)
    (ANALYSIS, "R2 requirement rounded down",
     "                           math.ceil(rules[\"restore_units_ratio_min\"] * t9[\"seats\"][seat][\"post_opening_units\"]))",
     "                           math.floor(rules[\"restore_units_ratio_min\"] * t9[\"seats\"][seat][\"post_opening_units\"]))"),
    (ANALYSIS, "R2 exclusive", "    item(\"R2_post_opening_restored\", all(units[s] >= needed[s] for s in (\"H1\", \"H2\")),",
     "    item(\"R2_post_opening_restored\", all(units[s] > needed[s] for s in (\"H1\", \"H2\")),"),
    (ANALYSIS, "R3 seats not strictly below",
     "    lower = {s: prim[\"seats\"][s][\"post_slot_vs_t9-v1\"] < v3[\"seats\"][s][\"post_slot_vs_t9-v1\"] for s in",
     "    lower = {s: prim[\"seats\"][s][\"post_slot_vs_t9-v1\"] <= v3[\"seats\"][s][\"post_slot_vs_t9-v1\"] for s in"),
    (ANALYSIS, "R3 ratio exclusive", "slot is not None and slot <= rules[\"divergence_ratio_max\"]",
     "slot is not None and slot < rules[\"divergence_ratio_max\"]"),
    (ANALYSIS, "R1 ignores the primary games",
     "    item(\"R1_no_opening_redistribution\", all(n == 0 for n in first.values()) and all(",
     "    item(\"R1_no_opening_redistribution\", True and all("),
    (ANALYSIS, "R4 exclusive", "recourse <= rules[\"recourse_max\"]", "recourse < rules[\"recourse_max\"]"),
    (ANALYSIS, "R4 ignores oscillations", "prim[\"pooled\"][\"oscillations\"] == 0 and recourse",
     "True and recourse"),
    (ANALYSIS, "A1 ignores shooters", "        good = (x[\"shooters_redirected\"] == 0 and", "        good = (True and"),
    (ANALYSIS, "A1 ignores the early limit", "                and x[\"early_redirects_baseline\"] <= early_limit)",
     "                and True)"),
    (ANALYSIS, "A2 certificate not required", "         and a[\"certificate_unit_decisions\"] >= v3_cert,",
     "         and a[\"certificate_unit_decisions\"] >= 0,"),
    (ANALYSIS, "G9 ignores memory problems", "inv[\"memory_problems\"] == 0 and inv[\"memory_checks\"] > 0",
     "inv[\"memory_checks\"] > 0"),
    (ANALYSIS, "adequacy never untested", "\"status\": \"TESTED\" if exposure > 0 else \"UNTESTED\"",
     "\"status\": \"TESTED\" if exposure >= 0 else \"UNTESTED\""),
    (ANALYSIS, "selection ignores adequacy",
     "    full = sorted((n for n, g in gates.items() if g[\"pass\"] and adequacies[n][\"all_tested\"]),",
     "    full = sorted((n for n, g in gates.items() if g[\"pass\"]),"),
    (ANALYSIS, "opportunity test inverted", "if row[\"o2_post_opening_units\"] < row[\"required\"])",
     "if row[\"o2_post_opening_units\"] > row[\"required\"])"),
    (ANALYSIS, "restoring candidates need not restore",
     "    restoring = sorted((n for n, g in gates.items() if g[\"groups\"][\"invariants\"] and g[\"groups\"][\"restoration\"]),",
     "    restoring = sorted((n for n, g in gates.items() if g[\"groups\"][\"invariants\"]),"),
    (ANALYSIS, "stray records ignored", "    if stray:\n", "    if False:\n"),
    (ANALYSIS, "counter bound loosened", "        if not 0 <= record[td.COUNT] <= td.COUNT_CAP",
     "        if not 0 <= record[td.COUNT] <= 2 * td.COUNT_CAP"),
    (ANALYSIS, "oscillation matches a repeat, not a return",
     "        if any(previous_source == target and previous_target == source",
     "        if any(previous_source == source and previous_target == target"),
    (ANALYSIS, "rubric keeps the smallest margin", "        best = max(band.values())", "        best = min(band.values())"),
    (ANALYSIS, "rubric tolerance dropped", "        alive = [n for n in alive if values[n] <= least * (1 + rules[\"rubric_tolerance\"])]",
     "        alive = [n for n in alive if values[n] <= least]"),
    (ANALYSIS, "bucket boundary shifted", "    if ordinal <= 6:", "    if ordinal < 6:"),
    (ANALYSIS, "rule search prefers primary over adverse", "            key = (-adverse, primary, -n, str(rule))",
     "            key = (primary, -adverse, -n, str(rule))"),
    (ANALYSIS, "determinism ignores memory",
     "            tuple(sorted(allocation.withheld.items())), tuple(allocation.memory))",
     "            tuple(sorted(allocation.withheld.items())), ())"),
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
        env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
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
    sources = (CANDIDATE, ANALYSIS, Path("tests/test_t9_delayed.py"), Path("tests/test_s15_delayed.py"))
    payload = {"schema": "miaosuan-s15-delayed-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
