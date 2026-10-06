"""Mutation test of the Sprint 16 decision logic (``docs/SPRINT16_MECHANISM_CAPTURE.md``).

    python scripts/mutate_s16.py [--check]

Copies ``src``, ``tests``, ``scripts`` and the evaluation folders the tests read to a temporary directory, first runs
the Sprint 16 test modules unmutated (they must pass, or every later kill would be vacuous), then plants each
registered defect into the shadow module, the frozen rules module or the analysis driver, rebuilds the card in the
copy (the card pins those files' digests, so without the rebuild every defect would be caught by the pin alone and
the run would say nothing about the logic tests), runs the tests in a fresh process and records whether they failed.
A defect after which the card cannot be built at all counts as caught by the card builder and is labelled so. Every
planted defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s16-mechanism-capture/mutation.json``.
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
SHADOW = Path("src/miaosuan_agent/evaluation/s16_shadow.py")
RULES = Path("src/miaosuan_agent/evaluation/s16_mechanism.py")
ANALYSIS = Path("scripts/s16_analysis.py")
TESTS = ("tests.test_s16_shadow", "tests.test_s16_mechanism")
EVALUATION = ("s16-v3-mechanism-capture-1", "baseline-v2-candidate-shoot-target-reservation")
CARD = Path("evaluation/s16-v3-mechanism-capture-1/manifest.json")
OUT = REPO_ROOT / "evaluation" / "s16-mechanism-capture" / "mutation.json"
MUTATIONS = [
    # -- the corrected memory and every unchanged transition
    (SHADOW, "corrected reset reverted to v5 (any objective ends the record)",
     "        elif not path and unit.cur_hex in cities and cities[unit.cur_hex].flag != faction:",
     "        elif not path and unit.cur_hex in cities:"),
    (SHADOW, "standing on an unheld objective no longer ends the record",
     "        elif not path and unit.cur_hex in cities and cities[unit.cur_hex].flag != faction:", "        elif False:"),
    (SHADOW, "a move to an objective no longer ends the record", "        elif path and path[-1] in cities:",
     "        elif False:"),
    (SHADOW, "an absent unit keeps its record", "        if unit is None:\n            reason = ABSENT",
     "        if False:\n            reason = ABSENT"),
    (SHADOW, "the source's capture no longer ends the episode",
     "        if record[td.SOURCE] in cities and cities[record[td.SOURCE]].flag == faction:", "        if False:"),
    (SHADOW, "the source's capture wipes the staging fact",
     "            for index in (td.SOURCE, td.COUNT, td.ALTERNATIVE, td.SATURATED, td.REDIRECTED, td.FIRST):",
     "            for index in range(len(td.FIELD_NAMES)):"),
    (SHADOW, "staging completion detected away from the staging endpoint",
     "        if record[td.STAGED] and not path and unit.cur_hex == record[td.STAGED]:",
     "        if record[td.STAGED] and not path:"),
    (SHADOW, "every overflow claimant eligible", "records, ended, errors, False)", "records, ended, errors, True)"),
    # -- first divergence
    (RULES, "a reordering is not a divergence", "    return plain(v3_actions) != plain(shadow_actions)",
     "    return sorted(map(str, plain(v3_actions))) != sorted(map(str, plain(shadow_actions)))"),
    (RULES, "a withheld action is not a changed unit", "set(a) | set(b) if a.get(u) != b.get(u)",
     "set(a) & set(b) if a.get(u) != b.get(u)"),
    # -- risk windows and firing roles
    (RULES, "fire window ignores the new game's fire", "        decisions.extend(values)", "        pass"),
    (RULES, "fire risk window boundary exclusive", "    k = fsd[\"k\"]\n    if k > window_end:",
     "    k = fsd[\"k\"]\n    if k >= window_end:"),
    (RULES, "reservation risk window boundary exclusive", "    if fsd[\"k\"] > window_end:",
     "    if fsd[\"k\"] >= window_end:"),
    (RULES, "reservation window ignores the first ownership",
     "    return last_decision if first_own_decision is None else first_own_decision", "    return last_decision"),
    (RULES, "historical shooter protected only strictly before its firing decision",
     "    if unit in historical and k <= historical[unit]:", "    if unit in historical and k < historical[unit]:"),
    (RULES, "historical shooters ignored", "    if unit in historical and k <= historical[unit]:", "    if False:"),
    (RULES, "a fire role before the divergence still protects",
     "    if any(k <= d <= window_end for d in observed.get(unit, ())):",
     "    if any(d <= window_end for d in observed.get(unit, ())):"),
    (RULES, "a fire listing at the divergence itself does not protect",
     "    if any(k <= d <= window_end for d in observed.get(unit, ())):",
     "    if any(k < d <= window_end for d in observed.get(unit, ())):"),
    (RULES, "no divergence read as ambiguous",
     "        return {\"class\": names[\"safe\"], \"sublabel\": NO_TRIGGER, \"window_end\": window_end, \"reasons\": []}\n"
     "    k = fsd[\"k\"]",
     "        return {\"class\": names[\"ambiguous\"], \"sublabel\": NO_TRIGGER, \"window_end\": window_end, \"reasons\": []}\n"
     "    k = fsd[\"k\"]"),
    (RULES, "the opening topology ignored (fire)",
     "        reasons.append(\"divergence at the opening decision (Sprint 14's harmful opening-redirect topology)\")",
     "        pass"),
    (RULES, "an early non-shooter divergence read as safe",
     "    return {\"class\": names[\"ambiguous\"], \"sublabel\": \"first divergence inside the risk window on a unit with no firing \"",
     "    return {\"class\": names[\"safe\"], \"sublabel\": \"first divergence inside the risk window on a unit with no firing \""),
    # -- the reservation certificate
    (RULES, "the fourth clause without the capturer condition",
     "    if row[\"to_problem_objective\"] and row[\"consumes_last_place\"] and row[\"before_first_ownership\"] \\\n"
     "            and row[\"capturer_without_place\"]:",
     "    if row[\"to_problem_objective\"] and row[\"consumes_last_place\"] and row[\"before_first_ownership\"]:"),
    (RULES, "a dominated redirect is not bad", "    if row[\"dominated\"]:", "    if False:"),
    (RULES, "domination at equal free-flow time",
     "c[\"free_flow\"] is not None and c[\"free_flow\"] < redirect_free_flow",
     "c[\"free_flow\"] is not None and c[\"free_flow\"] <= redirect_free_flow"),
    (RULES, "domination ignores the place given", "    return any(c[\"feasible\"] and not c[\"placed\"] and",
     "    return any(c[\"feasible\"] and"),
    (RULES, "first ownership boundary inclusive", "    return {\"before_first_ownership\": first_own is None or k < first_own,",
     "    return {\"before_first_ownership\": first_own is None or k <= first_own,"),
    (RULES, "the opening topology ignored (reservation)",
     "        reasons.append(\"divergence at the opening decision\")", "        pass"),
    # -- disposition
    (RULES, "a capture problem does not invalidate", "    if problems or sorted(classes) != sorted(CONFIGS):",
     "    if sorted(classes) != sorted(CONFIGS):"),
    (RULES, "a missing configuration does not invalidate", "    if problems or sorted(classes) != sorted(CONFIGS):",
     "    if problems:"),
    (RULES, "an unsafe first divergence does not refute",
     "    bad = sorted(c for c, row in classes.items() if row[\"class\"] == CLASSES[c][\"bad\"])", "    bad = []"),
    (RULES, "ambiguity read as support",
     "    unclear = sorted(c for c, row in classes.items() if row[\"class\"] == CLASSES[c][\"ambiguous\"])",
     "    unclear = []"),
    # -- R3 and R4
    (RULES, "restoration counts units outside the reference", "        restored = ref & set(redirected.get(seat, ()))",
     "        restored = set(redirected.get(seat, ()))"),
    (RULES, "restoration threshold exclusive", "\"pass\": len(restored) >= rules[\"restoration_required\"][seat]}",
     "\"pass\": len(restored) > rules[\"restoration_required\"][seat]}"),
    (RULES, "tracker: a held objective ends the episode",
     "            elif not path and hex_ in flags and flags[hex_] != faction:",
     "            elif not path and hex_ in flags:"),
    (RULES, "tracker: a new source continues the episode",
     "            if unit in self.open and self.open[unit][\"source\"] != source:\n                self._close(unit)\n",
     ""),
    (RULES, "tracker: the source's capture does not end the episode",
     "            elif flags.get(episode[\"source\"]) == faction:", "            elif False:"),
    (RULES, "recourse allows a second redirect per episode",
     "            \"pass\": worst <= rules[\"recourse_per_episode_max\"] and multi == 0 and outside == 0}",
     "            \"pass\": worst <= rules[\"recourse_per_episode_max\"] + 1 and multi == 0 and outside == 0}"),
    (RULES, "recourse ignores redirects outside episodes",
     "            \"pass\": worst <= rules[\"recourse_per_episode_max\"] and multi == 0 and outside == 0}",
     "            \"pass\": worst <= rules[\"recourse_per_episode_max\"] and multi == 0}"),
    # -- identities, card, ledger, stops
    (RULES, "v3 digest changed", "V3_ID, V3_DIGEST = sc.V3_ID, sc.V3_DIGEST", "V3_ID, V3_DIGEST = sc.V3_ID, \"0\" * 64"),
    (RULES, "session mapping shifted", "EXPECTED_SESSIONS = (2791, 2792, 2793)", "EXPECTED_SESSIONS = (2792, 2793, 2794)"),
    (RULES, "ledger base moved", "LEDGER_BASE_SESSION = 2790", "LEDGER_BASE_SESSION = 2786"),
    (RULES, "C2 seats swapped", "(2, \"1930331196\", \"C2\", V3_ID, INERT_ID)", "(2, \"1930331196\", \"C2\", INERT_ID, V3_ID)"),
    (RULES, "ledger ignores the schedule position",
     "            elif position > len(order) or order[position - 1] != game:", "            elif position > len(order):"),
    (RULES, "ledger ignores the card digest",
     "            if harness.get(\"card\") != CARD_ID or harness.get(\"manifest_sha256\") != digest:",
     "            if harness.get(\"card\") != CARD_ID:"),
    (RULES, "ledger ceiling raised", "    if len(opened) > SESSION_CEILING:", "    if len(opened) > SESSION_CEILING + 1:"),
    (RULES, "reconstruction mismatch is not structural", "STRUCTURAL_STOPS = (\"S1\", \"S2\", \"S3\", \"S4\", \"S6\", \"S7\")",
     "STRUCTURAL_STOPS = (\"S1\", \"S2\", \"S3\", \"S4\", \"S6\")"),
    (RULES, "card check ignores the schedule", "    if planned != [", "    if False and planned != ["),
    (RULES, "card check ignores an executable shadow", "    if (screen.get(\"shadow\") or {}).get(\"executable\") is not False:",
     "    if False:"),
    (RULES, "restoration requirement lowered", "\"restoration_required\": {\"H1\": 8, \"H2\": 13}",
     "\"restoration_required\": {\"H1\": 7, \"H2\": 13}"),
    # -- analysis driver
    (ANALYSIS, "certificate episode count excludes this observation",
     "            \"episode_count\": (record[td.COUNT] + 1) if same else 1,",
     "            \"episode_count\": record[td.COUNT] if same else 1,"),
    (ANALYSIS, "last-place test off by one", "            \"consumes_last_place\": dest_before == ms.RULES[\"capacity\"] - 1,",
     "            \"consumes_last_place\": dest_before == ms.RULES[\"capacity\"],"),
    (ANALYSIS, "destination count ignores stage-1 selections and standing units",
     "        dest_before = dest_row.get(\"physical\", 0) + dest_row.get(\"movers\", 0) + selected_at[option.objective] + earlier",
     "        dest_before = selected_at[option.objective] + earlier"),
    (ANALYSIS, "public files may name the v3 identity", "        if ms.V3_ID in text or ms.V3_DIGEST in text:",
     "        if False:"),
    (ANALYSIS, "shadow memory carried across streams", "    memories = {n: () for n in SHADOWS}",
     "    memories = dict(CARRIED)"),
]


def prepare(root: Path, replacements) -> bool:
    for folder in ("src", "tests", "scripts"):
        shutil.copytree(REPO_ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    for name in EVALUATION:
        shutil.copytree(REPO_ROOT / "evaluation" / name, root / "evaluation" / name)
    for source, text in replacements.items():
        (root / source).write_text(text, encoding="utf-8", newline="\n")
    (root / CARD).unlink()
    built = subprocess.run([sys.executable, "scripts/build_s16_card.py"], cwd=root, env=env_for(root),
                           capture_output=True, text=True, timeout=300)
    if built.returncode != 0:
        shutil.copy2(REPO_ROOT / CARD, root / CARD)
    return built.returncode == 0


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    return env


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        built = prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=900)
    return done.returncode == 0, built


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    passed, built = tests_pass({source: text.replace(old, new)})
    return {"mutation": name, "module": source.as_posix(), "killed": not passed,
            "card_rebuilt": built}


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    passed, built = tests_pass({})
    if not (passed and built):
        raise SystemExit("the unmutated tests fail (or the card cannot be built) in the temporary copy; kills would "
                         "be vacuous")
    results = [run(m) for m in MUTATIONS]
    sources = (SHADOW, RULES, ANALYSIS, Path("tests/test_s16_shadow.py"), Path("tests/test_s16_mechanism.py"))
    payload = {"schema": "miaosuan-s16-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results),
               "killed_with_the_card_rebuilt": sum(r["killed"] and r["card_rebuilt"] for r in results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']} ({payload['killed_with_the_card_rebuilt']} with the card "
          "rebuilt)")
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
        elif not r["card_rebuilt"]:
            print("caught by the card builder only:", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
