"""Mutation test of the Sprint 13 diagnosis analysis (``evaluation/s13_diagnosis.py``).

    python scripts/mutate_s13_diagnosis.py [--check]

Copies ``src``, ``tests`` and ``scripts`` to a temporary directory, first runs the test module unmutated (it must pass,
or every later kill would be vacuous), then plants each registered analysis defect into the module, runs the tests in a
fresh process and records whether they failed (the defect was caught). Every planted defect's original text must occur
exactly once. Writes (or with ``--check`` compares) ``evaluation/s13-v3-diagnosis/mutation.json``.
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
ANALYSIS = Path("src/miaosuan_agent/evaluation/s13_diagnosis.py")
TESTS = ("tests.test_s13_diagnosis",)
OUT = REPO_ROOT / "evaluation" / "s13-v3-diagnosis" / "mutation.json"
MUTATIONS = [
    # -- classification (section 4)
    ("redirect classes swapped", "        return {KEEP: CLASSES[0], STAGE: CLASSES[1], WITHHOLD: CLASSES[2]}[v3_form]",
     "        return {KEEP: CLASSES[0], STAGE: CLASSES[2], WITHHOLD: CLASSES[1]}[v3_form]"),
    ("end-of-game class on the wrong reason",
     "    if v1_form == KEEP and v3_form in (STAGE, WITHHOLD) and v3_reason == LATE:",
     "    if v1_form == KEEP and v3_form in (STAGE, WITHHOLD) and v3_reason == FULL:"),
    ("incumbent-mover class inverted", "    if v1_form == WITHHOLD and v3_form == KEEP and v1_with_v3_count == \"keep\":",
     "    if v1_form == WITHHOLD and v3_form == KEEP and v1_with_v3_count != \"keep\":"),
    ("staging against withholding not classed", "    if v1_form == WITHHOLD and v3_form == STAGE:\n        return CLASSES[6]",
     "    if False:\n        return CLASSES[6]"),
    ("redirect cause ignores phantoms",
     "            cause = \"PHANTOM_INCUMBENTS\" if (before is not None and before - phantom_at_dest < CAPACITY) else \"CAPACITY\"",
     "            cause = \"PHANTOM_INCUMBENTS\" if (before is not None and before < CAPACITY) else \"CAPACITY\""),
    ("T9-v1 restatement ignores the exclusion",
     "        if unit.color != faction or unit.fields.get(\"type\") not in GROUND or unit.obj_id in exclude:",
     "        if unit.color != faction or unit.fields.get(\"type\") not in GROUND:"),
    # -- oracles (section 7)
    ("O1 exclusion ignored", "        elif unit.obj_id in exclude:\n            row[\"excluded\"] += 1",
     "        elif False:\n            row[\"excluded\"] += 1"),
    ("O1 never given the doomed movers", "    for name, options in ((\"O1\", {\"exclude\": excluded}),",
     "    for name, options in ((\"O1\", {}),"),
    ("O2 redirect ignores the end-of-game test",
     "        if ff is None or (end is not None and now + ff >= end):\n            infeasible += 1",
     "        if ff is None:\n            infeasible += 1"),
    ("O2 redirect fills a full objective", "        if coord == own_dest or coord not in unheld or counted.get(coord, 0) >= CAPACITY:",
     "        if coord == own_dest or coord not in unheld or counted.get(coord, 0) > CAPACITY:"),
    ("O2 redirect beyond the detour bound", "        if base_cost is None or cost > DETOUR * base_cost:\n            continue\n        action",
     "        if base_cost is None:\n            continue\n        action"),
    ("phantom movers counted", "        if bound is not None and end is not None and now + bound >= end:\n            row[\"phantom\"] += 1",
     "        if False:\n            row[\"phantom\"] += 1"),
    ("mover bound includes the hex being entered", "        bound = free_flow(router, unit, path, skip_first=True)",
     "        bound = free_flow(router, unit, path)"),
    ("oracle selects regardless of feasibility", "        chosen = [c for c in ranked if c.feasible][:max(free, 0)]",
     "        chosen = ranked[:max(free, 0)]"),
    # -- verification (section 3)
    ("trace digest not verified", "    if decided[\"baseline_trace_sha256\"] != captured_row[\"baseline_trace_sha256\"]:",
     "    if False:"),
    ("submitted actions not verified", "    if rd.plain(decided[\"t9-v3\"]) != rd.plain(list(submitted)):", "    if False:"),
    ("captured selection not verified",
     "        if {str(u): c for u, c in allocation.selected.items()} != captured[\"selected\"]:", "        if False:"),
    # -- reservation episodes (section 6)
    ("selection one decision late", "                selected = k - 1 if (k - 1) in chosen.get(key, ()) else None",
     "                selected = k if k in chosen.get(key, ()) else None"),
    ("episodes never close", "            if key not in present:\n                out.append(open_.pop(key))",
     "            if False:\n                out.append(open_.pop(key))"),
    ("destruction before the episode counted", "    if lost is not None and lost >= start and (arrived is None or lost <= arrived):",
     "    if lost is not None and (arrived is None or lost <= arrived):"),
    # -- features (section 7)
    ("ties counted as wins", "            wins += 1.0 if p > n else 0.5 if p == n else 0.0",
     "            wins += 1.0 if p >= n else 0.0"),
    ("one game agreeing suffices",
     "        separating = all(g[\"auc\"] is not None and ((g[\"auc\"] > 0.5) if high else (g[\"auc\"] < 0.5)) for g in eligible)",
     "        separating = any(g[\"auc\"] is not None and ((g[\"auc\"] > 0.5) if high else (g[\"auc\"] < 0.5)) for g in eligible)"),
    ("low separation ignored", "    if pooled is not None and (pooled >= RULE[\"auc_high\"] or pooled <= RULE[\"auc_low\"]):",
     "    if pooled is not None and pooled >= RULE[\"auc_high\"]:"),
    ("own objective called contested", "    contested = city.get(\"flag\") != faction and (city.get(\"flag\") == enemy or any(",
     "    contested = (city.get(\"flag\") == enemy or any("),
    ("nearest enemy measured from the objective",
     "    nearest = min((hex_distance(unit[\"cur_hex\"], h) for h in seen_hexes), default=None)",
     "    nearest = min((hex_distance(objective, h) for h in seen_hexes), default=None)"),
    # -- sequences (section 8)
    ("equal counted as below", "        if v is None or f is None or not v < f:", "        if v is None or f is None or v > f:"),
    ("characteristic threshold exclusive", "            if count >= RULE[\"char_own\"]:", "            if count > RULE[\"char_own\"]:"),
    ("coverage includes the deployment snapshot", "        if row[\"k\"] == 0:\n            out.append(None)\n            continue\n",
     ""),
    # -- disposition (section 9)
    ("unit threshold exclusive", "    return {\"a_material\": a[\"distinct_redirected\"] >= RULE[\"a_min_units\"]",
     "    return {\"a_material\": a[\"distinct_redirected\"] > RULE[\"a_min_units\"]"),
    ("onset may equal the divergence", "        return step is not None and (divergence_step is None or step < divergence_step)",
     "        return step is not None and (divergence_step is None or step <= divergence_step)"),
    ("share threshold ignored for B",
     "            \"b_material\": b[\"distinct_admitted\"] >= RULE[\"b_min_units\"] and b_share >= RULE[\"b_min_share\"]",
     "            \"b_material\": b[\"distinct_admitted\"] >= RULE[\"b_min_units\"]"),
    ("both seats not required", "        return len(hit) >= RULE[\"games_needed\"] and {seats[g] for g in hit} >= {\"H1\", \"H2\"}, len(hit)",
     "        return len(hit) >= RULE[\"games_needed\"], len(hit)"),
    ("overlap boundary inclusive", "    elif overlap > RULE[\"overlap_max\"]:", "    elif overlap >= RULE[\"overlap_max\"]:"),
    ("ratio boundary inclusive", "    elif sb < RULE[\"ratio\"] * sa:", "    elif sb <= RULE[\"ratio\"] * sa:"),
    ("prospective evidence not required", "    reservation = \"RESERVATION_LIFETIME_DOMINANT\" if prospective else \"INSUFFICIENT_FOR_REVISION\"",
     "    reservation = \"RESERVATION_LIFETIME_DOMINANT\""),
    # -- privacy
    ("declared allowances widened", "    return [p for p in privacy_problems(value, private_values) if p.split(\":\")[0] not in allowed]",
     "    return [p for p in privacy_problems(value, private_values) if p.split(\":\")[0] in allowed]"),
]


def run(mutation) -> dict:
    name, old, new = mutation
    text = (REPO_ROOT / ANALYSIS).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    return {"mutation": name, "killed": not tests_pass({ANALYSIS: text.replace(old, new)})}


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
    payload = {"schema": "miaosuan-s13-diagnosis-mutation/1",
               "sources": {p.as_posix(): digest(p) for p in (ANALYSIS, Path("tests/test_s13_diagnosis.py"))},
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
