"""Mutation test of the Sprint 31 rules (``docs/SPRINT31_T13_K2_PILOT.md``).

    python scripts/mutate_s31.py --phase preflight|pilot [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the phase's test modules
unmutated (they must pass, or every later kill would be vacuous), then plants each defect of the phase, runs the tests
in a fresh process and records whether they failed. Every planted defect's original text must occur exactly once.
Phase ``preflight``: the K2 candidate's change (``experiments/t13_keep_one_k2.py``) and the K2 preflight rules
(``evaluation/s31_preflight.py``), record ``evaluation/s31-t13-k2/mutation-preflight.json``, written before the
preflight runs. Phase ``pilot``: the pilot's rules, observer and runner checks, record
``evaluation/s31-t13-k2/mutation-pilot.json``, written before session 2798.
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
CAND = Path("src/miaosuan_agent/experiments/t13_keep_one_k2.py")
PRE = Path("src/miaosuan_agent/evaluation/s31_preflight.py")
PILOT = Path("src/miaosuan_agent/evaluation/s31_pilot.py")
CAPTURE = Path("src/miaosuan_agent/evaluation/s31_capture.py")
OUT = REPO_ROOT / "evaluation" / "s31-t13-k2"
PHASES = {
    "preflight": {
        "tests": ("tests.test_t13_keep_one_k2", "tests.test_s31_preflight"),
        "out": OUT / "mutation-preflight.json",
        "mutations": [
            (CAND, "no stop transition read as settling",
             '    if not (unit.get("stop") == 0 or positive(unit.get("move_to_stop_remain_time"))):\n        return False',
             '    if not (unit.get("stop") == 0):\n        return False'),
            (CAND, "missing settle fields tolerated", "    if not all(is_number(v) for v in values):\n        return None",
             "    if False:\n        return None"),
            (CAND, "timer upper bound dropped", "0 < timer <= SETTLE_STEPS", "0 < timer"),
            (CAND, "timer lower bound dropped", "0 < timer <= SETTLE_STEPS", "timer <= SETTLE_STEPS"),
            (CAND, "deferred stop order tolerated", "and force == 0 and change == 0", "and change == 0"),
            (CAND, "moving speed tolerated", "    if speed == 0 and stop == 0 and", "    if stop == 0 and"),
            (CAND, "stop flag 1 tolerated in settling", "    if speed == 0 and stop == 0 and", "    if speed == 0 and"),
            (CAND, "state change tolerated in settling", "force == 0 and change == 0 and on == 0", "force == 0 and on == 0"),
            (CAND, "embark tolerated in settling", "and on == 0 and off == 0:", "and off == 0:"),
            (CAND, "settling limit widened", "SETTLE_STEPS = 75\n", "SETTLE_STEPS = 150\n"),
            (CAND, "ambiguous state admitted", "    if settling(unit) is None or positive(unit.get(\"change_state_remain_time\")):",
             "    if settling(unit) is False and positive(unit.get(\"change_state_remain_time\")):"),
            (CAND, "state change ignored for settled units",
             "    if settling(unit) is None or positive(unit.get(\"change_state_remain_time\")):",
             "    if settling(unit) is None:"),
            (CAND, "K1 level C restored", "    if settling(unit) is None or positive(unit.get(\"change_state_remain_time\")):",
             "    if unit.get(\"stop\") == 0 or positive(unit.get(\"move_to_stop_remain_time\")) "
             "or positive(unit.get(\"change_state_remain_time\")):"),
            (PRE, "restated fields tolerated missing", "        if not all(number(v) for v in values.values()):\n            return False",
             "        if False:\n            return False"),
            (PRE, "restated deferred stop tolerated",
             '        if values["speed"] != 0 or values["stop"] != 0 or values["flag_force_stop"] != 0:',
             '        if values["speed"] != 0 or values["stop"] != 0:'),
            (PRE, "restated timer bound dropped", '        if not 0 < values["move_to_stop_remain_time"] <= SETTLE_LIMIT:',
             '        if not 0 < values["move_to_stop_remain_time"]:'),
            (PRE, "restated state change for settled units ignored",
             '    elif pf.positive(u.get("change_state_remain_time")):\n        return False',
             '    elif False:\n        return False'),
            (PRE, "independent findings ignored", '    if any(s["independent_check_findings"] for s in sides):',
             "    if False:"),
            (PRE, "HH colour opportunity not required", '        elif not any(s["verified_opportunity"] for s in group):',
             "        elif False:"),
            (PRE, "fixed inert configuration not required", '        elif not group[0]["verified_opportunity"]:',
             "        elif False:"),
            (PRE, "inert configurations by priority", 'PILOT_INERT = (("2120531121", "C3"), ("1930331196", "C2"))',
             'PILOT_INERT = (("1930331196", "C3"), ("1930331196", "C2"))'),
            (PRE, "names not restored", "    finally:\n        for n, v in saved.items():\n            setattr(module, n, v)",
             "    finally:\n        pass"),
            (PRE, "K1 rule in the analysis", "    with swapped(pf, k1=k2, independent_problems=independent_problems):",
             "    with swapped(pf, independent_problems=independent_problems):"),
        ],
    },
}


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


def tests_pass(tests, replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *tests], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=1800)
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
    parser.add_argument("--phase", required=True, choices=sorted(PHASES))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    phase = PHASES[args.phase]
    mutations, tests = phase["mutations"], phase["tests"]
    names = [m[1] for m in mutations]
    if len(set(names)) != len(names):
        raise SystemExit("two mutations share a name")
    plans = [mutated(m) for m in mutations]
    passed, log = tests_pass(tests, {})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = []
    for (source, name, _, _), plan in zip(mutations, plans):
        ok, _ = tests_pass(tests, plan)
        results.append({"mutation": name, "module": source.as_posix(), "killed": not ok})
    sources = sorted({m[0] for m in mutations if (REPO_ROOT / m[0]).exists()} |
                     {Path(f"{t.replace('.', '/')}.py") for t in tests}, key=lambda p: p.as_posix())
    payload = {"schema": "miaosuan-s31-mutation/1", "phase": args.phase,
               "sources": {p.as_posix(): digest(p) for p in sources}, "tests": list(tests),
               "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    out = phase["out"]
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + out.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']}")
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
