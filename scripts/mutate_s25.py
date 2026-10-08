"""Mutation test of the Sprint 25 T13-D1 rules (``docs/SPRINT25_T13_D1.md``).

    python scripts/mutate_s25.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the Sprint 25 test
modules unmutated (they must pass, or every later kill would be vacuous), then plants each defect into the garrison
shadow (``experiments/t13_garrison_shadow.py``), the analysis (``evaluation/s25_t13.py``) or the driver
(``scripts/s25_t13_d1.py``), runs the tests in a fresh process and records whether they failed. Every planted defect's
original text must occur exactly once. The protocol pin test (``tests/test_s25_results.py``) is not among the tests
run, so a mutant is killed by behaviour, never by its changed digest. Writes (or with ``--check`` compares)
``evaluation/s25-t13-d1/mutation.json``.
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
SHADOW = Path("src/miaosuan_agent/experiments/t13_garrison_shadow.py")
RULES = Path("src/miaosuan_agent/evaluation/s25_t13.py")
DRIVER = Path("scripts/s25_t13_d1.py")
TESTS = ("tests.test_t13_garrison_shadow", "tests.test_s25_t13", "tests.test_s25_driver")
OUT = REPO_ROOT / "evaluation" / "s25-t13-d1" / "mutation.json"
MUTATIONS = [
    # -- the garrison shadow: zone, eligibility, trigger, threat, hold, cooldown, overlap
    (SHADOW, "zone radius two hexes", "ZONE_RADIUS = 1\n", "ZONE_RADIUS = 2\n"),
    (SHADOW, "threat margin zero", "THREAT_MARGIN = 1\n", "THREAT_MARGIN = 0\n"),
    (SHADOW, "threat at range plus margin excluded", "        if d <= reach + THREAT_MARGIN:",
     "        if d < reach + THREAT_MARGIN:"),
    (SHADOW, "artillery eligible as defender",
     '    return is_ground(u) and not (u.get("type") == VEHICLE and u.get("sub_type") == ARTILLERY_SUB)',
     "    return is_ground(u)"),
    (SHADOW, "artillery not counted as an occupant",
     "    return tuple(sorted((obj for obj, u in own.items() if is_ground(u) and in_zone(u.get(\"cur_hex\"), objective)),",
     "    return tuple(sorted((obj for obj, u in own.items() if is_eligible_defender(u) and in_zone(u.get(\"cur_hex\"), objective)),"),
    (SHADOW, "a second occupant tolerated", "    if zone_occupants(own, objective) != (unit_id,):\n        return \"zone_not_single\", ()",
     "    if unit_id not in zone_occupants(own, objective):\n        return \"zone_not_single\", ()"),
    (SHADOW, "route must leave entirely", "    return any(not in_zone(h, objective) for h in hexes)",
     "    return all(not in_zone(h, objective) for h in hexes)"),
    (SHADOW, "existing path ignored", "    if existing and route_exits(existing, objective) is not False:",
     "    if False:"),
    (SHADOW, "transport commitment ignored", "    if transport:\n        return \"transport_committed\", ()",
     "    if False:\n        return \"transport_committed\", ()"),
    (SHADOW, "unknown range treated as a threat",
     "        if h is None or reach is None:\n            continue\n        d = hex_distance(h, objective)",
     "        if h is None:\n            continue\n        reach = 99 if reach is None else reach\n        d = hex_distance(h, objective)"),
    (SHADOW, "enemy aircraft counted as threats", "    for e in enemies:\n        if not is_ground(e):\n            continue",
     "    for e in enemies:\n        if False:\n            continue"),
    (SHADOW, "hold limit released one step late", "    if cur_step - start >= HOLD_LIMIT:", "    if cur_step - start > HOLD_LIMIT:"),
    (SHADOW, "cooldown one step short",
     "    cooldown: Dict[int, int] = {c: s for c, s in memory.cooldowns if cur_step - s < COOLDOWN}",
     "    cooldown: Dict[int, int] = {c: s for c, s in memory.cooldowns if cur_step - s < COOLDOWN - 1}"),
    (SHADOW, "no cooldown after a release", "            del holds[c]\n            cooldown[c] = cur_step",
     "            del holds[c]"),
    (SHADOW, "backup entry does not release", "    if zone_occupants(own, objective) != (unit_id,):\n        return \"backup_entered\"",
     "    if False:\n        return \"backup_entered\""),
    (SHADOW, "threat clearance does not release",
     "    if not qualifying_threats(enemies, objective, unit.get(\"type\")):\n        return \"threat_cleared\"",
     "    if False:\n        return \"threat_cleared\""),
    (SHADOW, "defender outside the zone does not release",
     "    if not in_zone(unit.get(\"cur_hex\"), objective):\n        return \"defender_outside_zone\"",
     "    if False:\n        return \"defender_outside_zone\""),
    (SHADOW, "repeat moves pass during a hold", "            if exits:\n                withheld.append(i)",
     "            if False:\n                withheld.append(i)"),
    (SHADOW, "overlap owner by hex only",
     "    zones = sorted((c for c in held_objectives(flags, faction) if in_zone(h, c)), key=lambda c: (hex_distance(h, c), c))",
     "    zones = sorted((c for c in held_objectives(flags, faction) if in_zone(h, c)), key=lambda c: c)"),
    (SHADOW, "non-play decisions examined", "    if stage != PLAY_STAGE:", "    if False:"),
    (SHADOW, "release order: threat before backup",
     '    if zone_occupants(own, objective) != (unit_id,):\n        return "backup_entered"\n'
     '    if not qualifying_threats(enemies, objective, unit.get("type")):\n        return "threat_cleared"',
     '    if not qualifying_threats(enemies, objective, unit.get("type")):\n        return "threat_cleared"\n'
     '    if zone_occupants(own, objective) != (unit_id,):\n        return "backup_entered"'),
    # -- the analysis: loss events, V classes, attribution, categories, enemy information, onward, stops, disposition
    (RULES, "a neutral flag after holding is not a loss", "            held = flag == faction\n            if held_prev",
     "            held = flag != 1 - faction\n            if held_prev"),
    (RULES, "destruction without a damage record at the disappearance",
     "        elif lost.get(d) == e and d not in by_k[e].aboard and e in damaged.get(d, ()):",
     "        elif lost.get(d) == e and d not in by_k[e].aboard:"),
    (RULES, "departure attributed without the route", '"attributable": bool(found) and after.get("cur_hex") in route}',
     '"attributable": bool(found)}'),
    (RULES, "zone occupied at the loss not checked", "    if occ[k]:\n        row.update(v_class=V_OTHER",
     "    if False:\n        row.update(v_class=V_OTHER"),
    (RULES, "mixed fates read as V_ORDER",
     "    if kinds == {ALIVE_OUT} and all(o[\"attributable\"] for o in orders.values()):",
     "    if ALIVE_OUT in kinds and all(o[\"attributable\"] for o in orders.values()):"),
    (RULES, "several defenders actionable",
     '    if len(row["defenders"]) != 1:\n        row.update(category=NON_ACTIONABLE, category_reason="several last defenders")\n        return',
     '    if not row["defenders"]:\n        return'),
    (RULES, "order from outside the zone actionable", '    if not row["departure"]["ordered_from_inside_zone"]:',
     "    if False:"),
    (RULES, "H0 baseline-v2 agreement ignored", '    elif row["departure"]["baseline_v2_same_move"] != "identical":',
     "    elif False:"),
    (RULES, "prefix support not required", "        if prefix_supported(side, j):", "        if True:"),
    (RULES, "post-divergence counted as touched",
     '        row.update(category=POST_DIVERGENCE, category_reason="after the side\'s first divergence")',
     '        row.update(category=TOUCHED, category_reason="after the side\'s first divergence")'),
    (RULES, "lookback window open at its lower edge", "    elif any(f.cur_step - LOOKBACK <= s < f.cur_step for s in seen):",
     "    elif any(f.cur_step - LOOKBACK < s < f.cur_step for s in seen):"),
    (RULES, "first owner before the order counted", "    risk = after and unit in participants",
     "    risk = unit in participants"),
    (RULES, "non-objective destination has no next objective",
     '        for g in frames[j + 1:]:\n            u = g.own.get(unit)', '        for g in ():\n            u = g.own.get(unit)'),
    (RULES, "independent withholding check skipped", "        problems = withheld_reasons(frame, faction, a)",
     "        problems = []"),
    (RULES, "stop A: exactly half fails", '"met": len(rows) == 0 or 2 * v < len(rows)}', '"met": len(rows) == 0 or 2 * v <= len(rows)}'),
    (RULES, "stop A: pooled only", '    out["A_departure_not_dominant"] = {"by_population": a_items, "met": any(i["met"] for i in a_items.values())}',
     '    out["A_departure_not_dominant"] = {"by_population": a_items, "met": a_items["pooled"]["met"]}'),
    (RULES, "stop B: three touched suffice", "STOP_B_MIN_TOUCHED = 4\n", "STOP_B_MIN_TOUCHED = 3\n"),
    (RULES, "stop B: one scenario-side suffices", "STOP_B_MIN_SCENARIO_SIDES = 2\n", "STOP_B_MIN_SCENARIO_SIDES = 1\n"),
    (RULES, "stop B: replicas counted", "        \"met\": len(touched) < STOP_B_MIN_TOUCHED or len(sides) < STOP_B_MIN_SCENARIO_SIDES}",
     "        \"met\": raw < STOP_B_MIN_TOUCHED or len(sides) < STOP_B_MIN_SCENARIO_SIDES}"),
    (RULES, "stop C: exactly half fails", '"met": n == 0 or 2 * risk > n}', '"met": n == 0 or 2 * risk >= n}'),
    (RULES, "stop C: no touched loss passes", '"met": n == 0 or 2 * risk > n}', '"met": n > 0 and 2 * risk > n}'),
    (RULES, "disposition: not-ready before invalid",
     "    outcome = DISPOSITIONS[0] if invalid else DISPOSITIONS[1] if met else DISPOSITIONS[2]",
     "    outcome = DISPOSITIONS[1] if met else DISPOSITIONS[0] if invalid else DISPOSITIONS[2]"),
    (RULES, "disposition: unexplained differences ignored",
     "    invalid = not fidelity_ok or not integrity_ok or unexplained != 0",
     "    invalid = not fidelity_ok or not integrity_ok"),
    # -- the driver
    (DRIVER, "recorded actions in file order", "            out[(header[\"game_id\"], faction)] = [steps[s] for s in sorted(steps)]",
     "            out[(header[\"game_id\"], faction)] = list(steps.values())"),
    (DRIVER, "side colours swapped", '    colour = "red" if faction == 0 else "blue"\n    if population == "HH":',
     '    colour = "blue" if faction == 0 else "red"\n    if population == "HH":'),
    (DRIVER, "split parts may exceed the limit", "        if parts[-1] and len(dump(trial).encode(\"utf-8\")) > PUBLIC_LIMIT:",
     "        if parts[-1] and len(dump(trial).encode(\"utf-8\")) > 2 * PUBLIC_LIMIT:"),
]


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def prepare(root: Path, replacements) -> None:
    for name in ("src", "tests", "scripts", "evaluation"):
        shutil.copytree(REPO_ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for source, text in replacements.items():
        (root / source).write_text(text, encoding="utf-8", newline="\n")


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=900)
    return done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    passed, _ = tests_pass({source: text.replace(old, new)})
    return {"mutation": name, "module": source.as_posix(), "killed": not passed}


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for source, name, old, _ in MUTATIONS:
        count = (REPO_ROOT / source).read_text(encoding="utf-8").count(old)
        if count != 1:
            raise SystemExit(f"mutation {name!r}: original text occurs {count} times")
    passed, log = tests_pass({})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = [run(m) for m in MUTATIONS]
    sources = (SHADOW, RULES, DRIVER) + tuple(Path(f"{t.replace('.', '/')}.py") for t in TESTS)
    payload = {"schema": "miaosuan-s25-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
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
