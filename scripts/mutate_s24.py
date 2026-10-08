"""Mutation test of the Sprint 24 selection rule and driver (``docs/SPRINT24_TACTICAL_FRONTIER_RESELECTION.md``).

    python scripts/mutate_s24.py [--check]

Copies ``src``, ``tests``, ``scripts``, ``evaluation`` and ``docs`` to a temporary directory, first runs the Sprint 24
tests unmutated (they must pass, or every later kill would be vacuous), then plants each defect into the rules module
(``evaluation/s24_selection.py``) or the driver (``scripts/s24_select.py``), re-pins the inputs inside the copy (so a
mutant is never killed by the digest pin alone), runs the tests in a fresh process and records whether they failed.
Every planted defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s24-tactical-frontier-reselection/mutation.json``.
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
RULES = Path("src/miaosuan_agent/evaluation/s24_selection.py")
DRIVER = Path("scripts/s24_select.py")
TESTS = ("tests.test_s24_selection",)
OUT = REPO_ROOT / "evaluation" / "s24-tactical-frontier-reselection" / "mutation.json"
MUTATIONS = [
    # -- computed criteria and caps
    (RULES, "level: a share at a threshold falls below it", "        if share + EPS >= bound:", "        if share > bound:"),
    (RULES, "P: the basis penalty ignored", "    return max(0, level(share, thresholds) - int(penalties[basis]))",
     "    return max(0, level(share, thresholds))"),
    (RULES, "L cap: the level of the stake ignored",
     "        if item.get(\"level\") in strong and isinstance(sides, int) and sides >= need:",
     "        if isinstance(sides, int) and sides >= need:"),
    (RULES, "L cap: the side minimum made strict",
     "        if item.get(\"level\") in strong and isinstance(sides, int) and sides >= need:",
     "        if item.get(\"level\") in strong and isinstance(sides, int) and sides > need:"),
    (RULES, "C: the engineering term dropped",
     "    return max(0, 5 - int(next_sessions) - int(follow_sessions) - max(0, int(engineering) - 1))",
     "    return max(0, 5 - int(next_sessions) - int(follow_sessions))"),
    # -- eligibility
    (RULES, "eligibility: excluded families allowed",
     "    if candidate[\"family\"] in rules[\"excluded_families\"]:\n        reasons.append(\"excluded family\")\n", ""),
    (RULES, "eligibility: admission not required",
     "    if not candidate.get(\"admitted\", False):\n        reasons.append(\"not admitted\")\n", ""),
    (RULES, "eligibility: repairs of closed increments allowed",
     "    if candidate.get(\"repairs\"):\n        reasons.append(\"repairs or restates a closed increment\")\n", ""),
    (RULES, "eligibility: unidentified semantics allowed",
     "    if candidate.get(\"depends_on_unidentified\"):\n", "    if False:\n"),
    (RULES, "eligibility: stopped data allowed", "    if candidate.get(\"uses_stopped_data\"):\n", "    if False:\n"),
    (RULES, "eligibility: minima made strict", "        if s[c] < minimum:", "        if s[c] <= minimum:"),
    (RULES, "eligibility: the next-session cap made strict",
     "    if candidate[\"next_sessions\"] > rules[\"max_next_sessions\"]:",
     "    if candidate[\"next_sessions\"] >= rules[\"max_next_sessions\"]:"),
    (RULES, "eligibility: the follow-session cap dropped",
     "    if candidate[\"follow_sessions\"] > rules[\"max_follow_sessions\"]:",
     "    if False:"),
    (RULES, "eligibility: the engineering cap made strict",
     "    if candidate[\"engineering\"] > rules[\"max_engineering\"]:",
     "    if candidate[\"engineering\"] >= rules[\"max_engineering\"]:"),
    (RULES, "eligibility: X2 without the conflict measure allowed",
     "            candidate.get(\"next_offline\") and candidate.get(\"conflict_measured\")):",
     "            candidate.get(\"next_offline\")):"),
    # -- the band, its order and the main outcome
    (RULES, "tie order: lower E preferred", "    return (-candidate[\"scores\"][\"E\"], candidate[\"next_sessions\"]",
     "    return (candidate[\"scores\"][\"E\"], candidate[\"next_sessions\"]"),
    (RULES, "tie order: sessions dropped",
     "    return (-candidate[\"scores\"][\"E\"], candidate[\"next_sessions\"] + candidate[\"follow_sessions\"],",
     "    return (-candidate[\"scores\"][\"E\"], 0,"),
    (RULES, "tie order: engineering dropped", "            candidate[\"engineering\"])", "            0)"),
    (RULES, "band: the edge excluded", "    in_band = [f for f in ranking if top - w[f] <= band + EPS]",
     "    in_band = [f for f in ranking if top - w[f] < band]"),
    (RULES, "main: equal tie keys resolved by identifier",
     "    if len(ordered) > 1 and tie_key(candidates[ordered[0]]) == tie_key(candidates[ordered[1]]):",
     "    if False:"),
    (RULES, "ranking: ineligible candidates ranked",
     "    ranking = sorted((f for f in candidates if not why[f]), key=lambda f: (-round(w[f], 9), f))",
     "    ranking = sorted(candidates, key=lambda f: (-round(w[f], 9), f))"),
    # -- robustness
    (RULES, "variants: the cost variants dropped", "    for extra in (\"E\", \"C\"):", "    for extra in (\"E\",):"),
    (RULES, "variants: the band ignored",
     "    pool = [f for f, t in totals.items() if best - t <= band + EPS]",
     "    pool = [f for f, t in totals.items() if best - t <= EPS]"),
    (RULES, "robustness: the threshold made inclusive", "    if stays < int(rubric[\"robust_min_first\"]):",
     "    if stays <= int(rubric[\"robust_min_first\"]) - 2:"),
    (RULES, "robustness: the challenger chosen by identifier",
     "    challenger = sorted(counts, key=lambda f: (-counts[f], f))[0] if counts else None",
     "    challenger = sorted(counts)[-1] if counts else None"),
    (RULES, "perturbation: the leverage cap ignored",
     "                ceiling = caps.get(name, 5) if c == \"L\" else 5", "                ceiling = 5"),
    (RULES, "perturbation: only the selected candidate perturbed",
     "    names = [selected] + ([runner_up] if runner_up else [])", "    names = [selected]"),
    (RULES, "perturbation: only upward steps", "            for step in (-1, 1):", "            for step in (1,):"),
    (RULES, "perturbation: the flip share made inclusive", "    if rows and Fraction(flips, len(rows)) > limit:",
     "    if rows and Fraction(flips, len(rows)) >= limit - Fraction(1, 100):"),
    # -- the driver: evidence, pins, caps, public content
    (DRIVER, "evidence: an equal float accepted for an int",
     "            if found != item[\"value\"] or type(found) is not type(item[\"value\"]):",
     "            if found != item[\"value\"]:"),
    (DRIVER, "evidence: quotes not whitespace-normalised", "    return \" \".join(text.split())", "    return text"),
    (DRIVER, "evidence: the value not required in its quote", "            elif not number_in(item[\"value\"], quote):",
     "            elif False:"),
    (DRIVER, "evidence: the level not checked",
     "        if item[\"level\"] not in rubric[\"evidence_levels\"]:", "        if False:"),
    (DRIVER, "whole number: separators not rejected after the number",
     "r\"(?![\\w/]|[.,]\\d)\"", "r\"(?![\\w/])\""),
    (DRIVER, "pins: the rules digest not compared", "    for key in (\"rubric_sha256\", \"rules_sha256\"):",
     "    for key in (\"rubric_sha256\",):"),
    (DRIVER, "public: identities not checked",
     "    problems += [f\"candidate identity {i!r} in a public file\" for i in IDENTITIES if i in text]", "    pass"),
    (DRIVER, "table: the leverage cap not applied", "        if s[\"L\"] > cap:", "        if False:"),
    (DRIVER, "table: the X2 cap on I not applied", "        if exp[\"interaction\"] == 2 and s[\"I\"] > 3:",
     "        if False:"),
    (DRIVER, "table: P over any denominator", "                if of != criteria[\"P\"][\"of\"]:", "                if False:"),
    (DRIVER, "table: a keyless P without a reason",
     "            if spec[\"key\"] is None and not str(spec.get(\"zero_reason\", \"\")).strip():",
     "            if False:"),
    (DRIVER, "table: new families admitted by default",
     "        admitted = (not exp[\"new_family\"]) or bool(admission.get(family, {}).get(\"admitted\"))",
     "        admitted = True"),
    (DRIVER, "experiments: unknown closed increments accepted",
     "            if name not in closed:\n                problems.append(f\"{family}: {name!r} is not a registered closed increment\")",
     "            if False:\n                problems.append(f\"{family}: {name!r} is not a registered closed increment\")"),
]


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def prepare(root: Path, replacements) -> None:
    for name in ("src", "tests", "scripts", "evaluation", "docs"):
        shutil.copytree(REPO_ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for source, text in replacements.items():
        (root / source).write_text(text, encoding="utf-8", newline="\n")


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        pin = subprocess.run([sys.executable, str(root / DRIVER), "freeze"], cwd=root, env=env_for(root),
                             capture_output=True, text=True, timeout=300)
        if pin.returncode != 0:
            return False, "re-pin failed: " + pin.stdout[-800:] + pin.stderr[-800:]
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
    sources = (RULES, DRIVER) + tuple(Path(f"{t.replace('.', '/')}.py") for t in TESTS)
    payload = {"schema": "miaosuan-s24-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
