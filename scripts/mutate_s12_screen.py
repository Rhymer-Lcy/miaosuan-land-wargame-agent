"""Mutation test of the Sprint 12 screen's frozen logic (``docs/SPRINT12_V3_SCREEN.md``).

    python scripts/mutate_s12_screen.py [--check]

Copies ``src``, ``tests`` and ``scripts`` to a temporary directory, first runs the three Sprint 12 test modules
unmutated (they must pass, or every later kill would be vacuous), then applies each registered mutation to its source
file, runs the tests in a fresh process and records whether they failed (the mutation was killed). Every mutation's
original text must occur exactly once. The mutations cover every rule value and comparison of the primary and adverse
classifications, the interim and final rules, the replication trigger, the card prerequisites, the disposition,
the ledger audit, the public sanitizer, each recomputed stop S1 and S4 to S14, the place outcomes and the observers'
reconstruction. Writes (or with ``--check`` compares) ``evaluation/s12-v3-screen/mutation.json``.
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
SCREEN = Path("src/miaosuan_agent/evaluation/s12_screen.py")
TIMELINE = Path("src/miaosuan_agent/evaluation/s12_timeline.py")
CAPTURE = Path("src/miaosuan_agent/evaluation/s12_capture.py")
TESTS = ("tests.test_s12_screen", "tests.test_s12_timeline", "tests.test_s12_capture")
OUT = REPO_ROOT / "evaluation" / "s12-v3-screen" / "mutation.json"
MUTATIONS = [
    # -- rule values ------------------------------------------------------------------------------------------------
    (SCREEN, "H2 floor changed", '"h2_margin_floor": 865,', '"h2_margin_floor": 864,'),
    (SCREEN, "H1 coverage floor changed", '"h1_coverage_floor": 0.6184027777777777,', '"h1_coverage_floor": 0.62,'),
    (SCREEN, "red collapse floor changed", '"h1_collapse_below": -1195,', '"h1_collapse_below": -1194,'),
    (SCREEN, "preserved seat average changed", '"preserved_seat_average_at_least": 130.5,',
     '"preserved_seat_average_at_least": 131,'),
    (SCREEN, "2120531121 C3 margin limit changed", '"margin_at_least": 559}', '"margin_at_least": 560}'),
    (SCREEN, "1930331196 C3 attack limit changed", '"attack_at_least": 78,', '"attack_at_least": 79,'),
    (SCREEN, "ceiling raised", "SESSION_CEILING = 12", "SESSION_CEILING = 13"),
    # -- comparisons -------------------------------------------------------------------------------------------------
    (SCREEN, "coverage floor inclusive", 'return facts["coverage"] < rules["h1_coverage_floor"]',
     'return facts["coverage"] <= rules["h1_coverage_floor"]'),
    (SCREEN, "H2 floor inclusive", 'return facts["margin"] < rules["h2_margin_floor"]',
     'return facts["margin"] <= rules["h2_margin_floor"]'),
    (SCREEN, "collapse inclusive", "    return facts[\"margin\"] < rules[key]", "    return facts[\"margin\"] <= rules[key]"),
    (SCREEN, "interim stop needs three collapses",
     'return counts["collapse_games"] >= 2 or counts["t9v2_like_h1"] + counts["t9v2_like_h2"] == 4',
     'return counts["collapse_games"] >= 3 or counts["t9v2_like_h1"] + counts["t9v2_like_h2"] == 4'),
    (SCREEN, "final stop on either seat",
     'counts["t9v2_like_h1"] >= 2 and counts["t9v2_like_h2"] >= 2', 'counts["t9v2_like_h1"] >= 2 or counts["t9v2_like_h2"] >= 2'),
    (SCREEN, "preserved allows two T9-v2-like games", 'counts["t9v2_like_h1"] + counts["t9v2_like_h2"] <= 1',
     'counts["t9v2_like_h1"] + counts["t9v2_like_h2"] <= 2'),
    (SCREEN, "preserved average exclusive", 'and counts["seat_average"] >= rules["preserved_seat_average_at_least"]',
     'and counts["seat_average"] > rules["preserved_seat_average_at_least"]'),
    (SCREEN, "fifth objective missed not detected", 'if facts["occupy"] < limits["occupy_all"]:\n            return "NOT_REPAIRED"',
     'if facts["occupy"] < limits["occupy_all"] - 80:\n            return "NOT_REPAIRED"'),
    (SCREEN, "repaired margin exclusive", 'return "REPAIRED" if facts["margin"] >= limits["margin_at_least"] else "PARTIAL"',
     'return "REPAIRED" if facts["margin"] > limits["margin_at_least"] else "PARTIAL"'),
    (SCREEN, "regressed limit exclusive", 'facts["attack"] <= limits["attack_at_most_regressed"]',
     'facts["attack"] < limits["attack_at_most_regressed"]'),
    (SCREEN, "avoided limit exclusive", 'return "AVOIDED" if facts["attack"] >= limits["attack_at_least"] else "AMBIGUOUS"',
     'return "AVOIDED" if facts["attack"] > limits["attack_at_least"] else "AMBIGUOUS"'),
    (SCREEN, "late capture boundary inclusive", 'if last is not None and last > rules["max_step"] - rules["late_capture_window_steps"]:',
     'if last is not None and last >= rules["max_step"] - rules["late_capture_window_steps"]:'),
    (SCREEN, "unfavourable A1 game not replicated", '    if cls not in FAVOURABLE:\n        reasons.append',
     '    if cls in UNFAVOURABLE and False:\n        reasons.append'),
    # -- stages, cards, disposition, ledger, privacy -----------------------------------------------------------------
    (SCREEN, "P1 permits A1", 'out.update(decision="CONTINUE", permits=CARD_IDS["P2"])',
     'out.update(decision="CONTINUE", permits=CARD_IDS["A1"])'),
    (SCREEN, "prerequisite ignores what the report permits",
     'if decision.get("decision") != "CONTINUE" or decision.get("permits") != CARD_IDS[stage]:',
     'if decision.get("decision") != "CONTINUE":'),
    (SCREEN, "A2 not restricted to the triggered configurations",
     'games = stage_games(stage, configs if stage == "A2" else None)', "games = stage_games(stage, None)"),
    (SCREEN, "S14 not a v3 defect", 'V3_DEFECT_STOPS = frozenset({"S5", "S8", "S9", "S10", "S11", "S12", "S14"})',
     'V3_DEFECT_STOPS = frozenset({"S5", "S8", "S9", "S10", "S11", "S12"})'),
    (SCREEN, "staging blocks ignored by readiness", "and attributed and blocks == 0", "and attributed"),
    (SCREEN, "ceiling check off by one", "if len(opened) > SESSION_CEILING:", "if len(opened) >= SESSION_CEILING:"),
    (SCREEN, "integrity failure not a stop", '                problems["S1"].append(f"session {session} closed with an integrity failure")',
     "                pass"),
    (SCREEN, "unit id key allowed in public files", 'FORBIDDEN_KEYS = frozenset({"obj_id", ', 'FORBIDDEN_KEYS = frozenset({'),
    (SCREEN, "frozen file changes not detected", "        problems.append(f\"frozen implementation files differ from the card: {changed}\")",
     "        pass"),
    # -- recomputed stops and outcomes -------------------------------------------------------------------------------
    (TIMELINE, "S1 not read from the session close",
     '        stops["S1"].append("the session did not close with integrity ok")', "        pass"),
    (TIMELINE, "S9 at the stacking limit instead of the staging cap",
     'staging_excess(state.units, baseline, submitted, rules["stage_cap"])',
     'staging_excess(state.units, baseline, submitted, rules["capacity"])'),
    (TIMELINE, "S8 stacking inclusive", 'if stacked > rules["capacity"]:', 'if stacked >= rules["capacity"]:'),
    (TIMELINE, "S8 counted places not checked", '            if counted > rules["capacity"]:\n                stops["S8"]',
     '            if counted > rules["capacity"] + 9:\n                stops["S8"]'),
    (TIMELINE, "S10 ignored", 'if checks.get("prefix_failures"):', "if False:"),
    (TIMELINE, "S11 ignored", 'if checks.get("cross_objective"):', "if False:"),
    (TIMELINE, "S12 ignores invented moves", 'if checks.get("unrelated_changed") or checks.get("invented"):',
     'if checks.get("unrelated_changed"):'),
    (TIMELINE, "S7 ignores missing reconstructions",
     'if timeline.get("reconstructed_decisions") != policy_seats * len(steps):', "if False:"),
    (TIMELINE, "S13 ignores refusal classes known from earlier games",
     "known = {tuple(c) for c in sc.KNOWN_REFUSAL_CLASSES} | {tuple(c) for c in extra_known}",
     "known = {tuple(c) for c in sc.KNOWN_REFUSAL_CLASSES}"),
    (TIMELINE, "S14 ignores units standing on the objective",
     'if hold["objective"] != coord or hold["physical"] or not hold["holders"] or hold["free_flow"] is None:',
     'if hold["objective"] != coord or not hold["holders"] or hold["free_flow"] is None:'),
    (TIMELINE, "S14 accepts a holder that arrived", "            if any(a is not None for a in arrivals):\n                continue",
     "            if all(a is not None for a in arrivals):\n                continue"),
    (TIMELINE, "occupation counted without acceptance",
     'occupied = (order is not None and order[1] == "accepted" and states[order[0] + 1].flags.get(coord) == faction)',
     "occupied = (order is not None and states[order[0] + 1].flags.get(coord) == faction)"),
    (TIMELINE, "slack off by one", 'out["arrival_slack"] = states[arrival].max_step - states[arrival].cur_step',
     'out["arrival_slack"] = states[arrival].max_step - states[arrival].cur_step + 1'),
    (TIMELINE, "lost and never-arrived swapped", 'out["outcome"] = "LOST" if lost_at is not None else "NEVER_ARRIVED"',
     'out["outcome"] = "NEVER_ARRIVED" if lost_at is not None else "LOST"'),
    (TIMELINE, "redundant before held", "    elif held:\n        out[\"outcome\"] = \"HELD\"\n    elif own_at_arrival:",
     "    elif own_at_arrival and False:\n        out[\"outcome\"] = \"HELD\"\n    elif own_at_arrival:"),
    (TIMELINE, "fifth objective is the first captured",
     'fifth = max(own_end, key=lambda c: (history[c]["last_to_own_step"], c))',
     'fifth = min(own_end, key=lambda c: (history[c]["last_to_own_step"], c))'),
    # -- observers ---------------------------------------------------------------------------------------------------
    (CAPTURE, "live actions not compared", '        return {"actions": live == rebuilt["actions"],\n                "changes"',
     '        return {"actions": True,\n                "changes"'),
    (CAPTURE, "timeline not full-step", "super().__init__(policies, sample_every=1, clock=clock)",
     "super().__init__(policies, sample_every=2, clock=clock)"),
    (CAPTURE, "staging not counted in hold episodes", 'if change["kind"] in ("stage", "withhold"):',
     'if change["kind"] in ("withhold",):'),
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
        shutil.copytree(REPO_ROOT / "evaluation" / "s12-batch-allocator-draft", root / "evaluation" /
                        "s12-batch-allocator-draft")
        shutil.copytree(REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation",
                        root / "evaluation" / "baseline-v2-candidate-shoot-target-reservation")
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
    payload = {"schema": "miaosuan-s12-screen-mutation/1",
               "sources": {p.as_posix(): digest(p) for p in (SCREEN, TIMELINE, CAPTURE)},
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
