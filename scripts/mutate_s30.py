"""Mutation test of the Sprint 30 rules (``docs/SPRINT30_T13_K1_PILOT.md``).

    python scripts/mutate_s30.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the Sprint 30 test
modules unmutated (they must pass, or every later kill would be vacuous), then plants each defect into the candidate
(``experiments/t13_keep_one_k1.py``), the preflight rules (``evaluation/s30_preflight.py``) or the committed evaluation
tree (a planted run card naming the candidate), runs the tests in a fresh process and records whether they failed.
Every planted defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s30-t13-k1/mutation.json``.
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
CAND = Path("src/miaosuan_agent/experiments/t13_keep_one_k1.py")
RULES = Path("src/miaosuan_agent/evaluation/s30_preflight.py")
CARD = Path("evaluation/s30-planted/manifest.json")
TESTS = ("tests.test_t13_keep_one_k1", "tests.test_s30_preflight", "tests.test_s30_results")
OUT = REPO_ROOT / "evaluation" / "s30-t13-k1" / "mutation.json"
PLANTED_CARD = json.dumps({"schema": "miaosuan-exploratory-run-card/1", "card_id": "s30-planted",
                           "candidate": "t13-keep-one-k1"}) + "\n"
MUTATIONS = [
    # -- the candidate: eligibility levels, trigger, selection, held objectives, stage, edit
    (CAND, "speed ignored", '    if positive(unit.get("speed")):\n        return ELIGIBILITY[0]',
     '    if False:\n        return ELIGIBILITY[0]'),
    (CAND, "route ignored", '    if unit.get("move_path"):\n        return ELIGIBILITY[1]',
     '    if False:\n        return ELIGIBILITY[1]'),
    (CAND, "stop flag ignored", '    if unit.get("stop") == 0 or positive(unit.get("move_to_stop_remain_time")) \\',
     '    if False or positive(unit.get("move_to_stop_remain_time")) \\'),
    (CAND, "stop transition time ignored",
     '    if unit.get("stop") == 0 or positive(unit.get("move_to_stop_remain_time")) \\',
     '    if unit.get("stop") == 0 or False \\'),
    (CAND, "state transition ignored", '            or positive(unit.get("change_state_remain_time")):',
     '            or False:'),
    (CAND, "transport transition ignored",
     '    if positive(unit.get("get_on_remain_time")) or positive(unit.get("get_off_remain_time")):',
     '    if positive(unit.get("get_on_remain_time")):'),
    (CAND, "several actions tolerated", "    if len(own_actions) != 1:", "    if len(own_actions) > 2:"),
    (CAND, "route ending on the centre tolerated", "            or any(as_int(h) is None for h in route) or route[-1] == centre:",
     "            or any(as_int(h) is None for h in route):"),
    (CAND, "a remaining occupant ignored", "        if any(not o.departs for o in occupants):", "        if False:"),
    (CAND, "already-moving units counted as remaining",
     '            departs = bool(u.get("move_path")) or by_move', "            departs = by_move"),
    (CAND, "all-moving case acted on", "        if not any(o.by_move for o in occupants):", "        if False:"),
    (CAND, "shortest time selected", "        best = min(ranked, key=lambda o: (-o.travel, o.unit))",
     "        best = min(ranked, key=lambda o: (o.travel, o.unit))"),
    (CAND, "tie to the higher id", "        best = min(ranked, key=lambda o: (-o.travel, o.unit))",
     "        best = min(ranked, key=lambda o: (-o.travel, -o.unit))"),
    (CAND, "unreadable times ranked", "        ranked = [o for o in eligible if o.travel is not None]",
     "        ranked = [o for o in eligible if o.travel is not None] or eligible[:1]"),
    (CAND, "unheld objectives treated as held", "        if city.get(\"flag\") == faction:",
     "        if city.get(\"flag\") != -1:"),
    (CAND, "infantry not an occupant",
     "        if isinstance(u, Mapping) and u.get(\"color\") == faction and u.get(\"type\") in GROUND \\",
     "        if isinstance(u, Mapping) and u.get(\"color\") == faction and u.get(\"type\") == 2 \\"),
    (CAND, "non-play decisions edited", "    if stage != PLAY_STAGE:", "    if stage == -1:"),
    (CAND, "every eligible MOVE withheld", "    drop = set(withheld)\n",
     "    drop = set(withheld) | {o.index for c in checks for o in c.occupants if o.level == ELIGIBLE}\n"),
    (CAND, "memory tolerated", "        if memory:\n            raise ValueError", "        if False:\n            raise ValueError"),
    # -- the preflight rules: independent check, validity, stop rule, inert priority
    (RULES, "missed trigger not reported", "    for centre in sorted(set(expected) - set(got)):",
     "    for centre in []:"),
    (RULES, "wrong holder accepted", "        elif where not in expected or expected[where][0] != a.get(\"obj_id\"):",
     "        elif where not in expected:"),
    (RULES, "non-MOVE removal accepted", "        if a.get(\"type\") != MOVE:\n            problems.append",
     "        if False:\n            problems.append"),
    (RULES, "free-flow rounding dropped", "        total += int(720.0 / speed * cost + 0.5)",
     "        total += int(720.0 / speed * cost)"),
    (RULES, "unsupported H0 prefix accepted", "                                   or first_difference >= first[\"k\"])",
     "                                   or True)"),
    (RULES, "HI not genuine", 'GENUINE = ("HH", "HI")', 'GENUINE = ("HH",)'),
    (RULES, "red opportunity not required",
     '        elif not any(s["verified_opportunity"] for s in group):', "        elif False:"),
    (RULES, "one inert configuration enough", "    if len(inert) < INERT_GAMES_NEEDED:", "    if len(inert) < 1:"),
    (RULES, "independent findings ignored", '    if any(s["independent_check_findings"] for s in sides):',
     "    if False:"),
    (RULES, "inert priority by sort order", "    return [c for c in INERT_PRIORITY if c in ok][:INERT_GAMES_NEEDED]",
     "    return sorted(c for c in INERT_PRIORITY if c in ok)[:INERT_GAMES_NEEDED]"),
    (RULES, "verified without validity", '               "verified_opportunity": bool(valid and not problems),',
     '               "verified_opportunity": bool(first is not None and not problems),'),
    # -- the committed tree: a run card naming the candidate
    (CARD, "a run card names the candidate", None, PLANTED_CARD),
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
        (root / source).parent.mkdir(parents=True, exist_ok=True)
        (root / source).write_text(text, encoding="utf-8", newline="\n")


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=900)
    return done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]


def mutated(mutation) -> dict:
    source, name, old, new = mutation
    if old is None:
        if (REPO_ROOT / source).exists():
            raise SystemExit(f"mutation {name!r}: {source} exists")
        return {source: new}
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    return {source: text.replace(old, new)}


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    names = [m[1] for m in MUTATIONS]
    if len(set(names)) != len(names):
        raise SystemExit("two mutations share a name")
    plans = [mutated(m) for m in MUTATIONS]
    passed, log = tests_pass({})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = []
    for (source, name, _, _), plan in zip(MUTATIONS, plans):
        ok, _ = tests_pass(plan)
        results.append({"mutation": name, "module": source.as_posix(), "killed": not ok})
    sources = (CAND, RULES) + tuple(Path(f"{t.replace('.', '/')}.py") for t in TESTS)
    payload = {"schema": "miaosuan-s30-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']}")
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
