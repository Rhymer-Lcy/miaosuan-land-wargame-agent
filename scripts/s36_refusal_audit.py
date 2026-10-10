"""Sprint 36 refusal audit: every recorded engine game, classified and used to calibrate the new refusal gate.

    python scripts/s36_refusal_audit.py [--evaluation DIR] [--check]

Reads every game record (``miaosuan-game-record/1``) under ``DIR`` (default ``local/evaluation``; private), one summary
per seat (``evaluation.s36_refusals.seat_summary``), and publishes aggregates only to
``evaluation/s36-tactical-recovery/refusal-audit.json``: denominators, refusal facts by factual class and taxonomy class,
the echo check, the reference rates (refused when they differ from the module's calibrated constants), and the
empirical trigger frequency of Sprint 35's S6 and of the alternatives by policy group, scale and scenario. No unit id,
hex or step is published. ``--check`` regenerates and compares byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s36_refusals as R  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "refusal-audit.json"
SKIP = (".timeline.json", ".explore.json", "manifest.json", "results.json")
REFERENCE = ("baseline-v2-candidate-shoot-target-reservation", "s34-integrated-mission-orchestrator-1",
             "s35-coalition-coalition-mission-planner-2")
INERT = "inert-v0"


def records(root: Path) -> List[Dict[str, Any]]:
    rows = []
    for path in sorted(glob.glob(str(root / "*" / "**" / "*.json"), recursive=True)):
        if path.endswith(SKIP):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "seats" not in data or "final_scores" not in data:
            continue
        folder = os.path.relpath(path, root).split(os.sep)[0]
        for seat in data["seats"]:
            row = R.seat_summary(seat)
            row.update(folder=folder, scenario=data.get("scenario_id"), status=data.get("status"),
                       session=data.get("session"))
            rows.append(row)
    return rows


def policy_group(policy: str) -> str:
    if policy in REFERENCE:
        return "reference (baseline-v2, Sprint 34 and Sprint 35 live candidates)"
    if policy.startswith("baseline-v1"):
        return "baseline-v1 (no shoot-target reservation)"
    if policy.startswith("baseline-v0"):
        return "baseline-v0"
    if policy.startswith("tactic-deployment-split"):
        return "deployment-split screen"
    return "other exploratory candidates"


def scale(unit_actions: int) -> str:
    if unit_actions <= 30:
        return "up to 30 unit actions"
    if unit_actions <= 100:
        return "31 to 100"
    if unit_actions <= 300:
        return "101 to 300"
    return "over 300"


RULES = {
    "sprint35_s6": R.s6_sprint35,
    "absolute_3": lambda s: R.absolute(s, 3),
    "rate_2pct_min_100": lambda s: R.rate_with_floor(s, 100, 0.02),
    "s36_structural": lambda s: bool(R.structural_findings(s)),
    "s36_systemic": lambda s: bool(R.systemic_findings(s)),
}


def audit(root: Path) -> Dict[str, Any]:
    rows = records(root)
    if not rows:
        raise SystemExit(f"no game record under {root}")
    tested = [r for r in rows if r["policy"] != INERT and r["status"] == "COMPLETED"]
    retained = [r for r in tested if r["retained"]]
    reference = [r for r in retained if r["policy"] in REFERENCE]
    rates = R.pooled_rates(reference)
    if rates != dict(R.REFERENCE_RATES):
        raise SystemExit(f"reference rates {rates} differ from the calibrated constants {dict(R.REFERENCE_RATES)}")
    facts = collections.Counter()
    classes = collections.Counter()
    for r in retained:
        for k, v in r["by_fact"].items():
            facts[k] += v
        for k, v in r["classes"].items():
            classes[f"{policy_group(r['policy'])}: {k}"] += v
    echo = collections.Counter((policy_group(r["policy"]), r["echo_matches"]) for r in tested)
    triggers: Dict[str, Dict[str, Any]] = collections.defaultdict(lambda: collections.Counter())
    by_scenario: Dict[str, Dict[str, Any]] = collections.defaultdict(lambda: collections.Counter())
    for r in retained:
        key = f"{policy_group(r['policy'])} | {scale(r['unit_actions'])}"
        triggers[key]["seat_games"] += 1
        for name, rule in RULES.items():
            triggers[key][name] += int(rule(r))
        if r["policy"] in REFERENCE:
            skey = f"{r['scenario']}"
            by_scenario[skey]["seat_games"] += 1
            for name, rule in RULES.items():
                by_scenario[skey][name] += int(rule(r))
    denominators = collections.defaultdict(list)
    for r in reference:
        denominators[scale(r["unit_actions"])].append(r["unit_actions"])
    s35 = [r for r in tested if r["folder"] == "s35-coalition-live-1"]
    position19 = [r for r in s35 if r["session"] == "2845" and r["policy"] != REFERENCE[0]]
    return {
        "schema": "miaosuan-s36-refusal-audit/1", "taxonomy": R.TAXONOMY_ID, "gate": R.GATE_ID,
        "population": {"game_records": len({(r['folder'], r['session'], r['scenario']) for r in rows}),
                       "seat_games": len(rows), "seat_games_under_test_completed": len(tested),
                       "with_refusal_facts": len(retained), "reference_seat_games": len(reference),
                       "reference_fire_actions": sum(r["fire_actions"] for r in reference),
                       "reference_other_actions": sum(r["other_actions"] for r in reference)},
        "reference_rates": rates,
        "constants": {"systemic_min": R.SYSTEMIC_MIN, "redundant_min": R.REDUNDANT_MIN,
                      "systemic_alpha": R.SYSTEMIC_ALPHA, "min_denominator": R.MIN_DENOMINATOR,
                      "repeat_actor": R.REPEAT_ACTOR, "unexplained_per_game": R.E_PER_GAME,
                      "unexplained_per_study": R.E_PER_STUDY},
        "refusal_facts_by_class": dict(sorted(facts.items())),
        "taxonomy_counts": {k: v for k, v in sorted(classes.items()) if v},
        "echo_matches_unit_actions": {f"{g} | {'equal' if ok else 'different'}": n for (g, ok), n in sorted(echo.items())},
        "reference_unit_actions_by_scale": {k: {"seat_games": len(v), "min": min(v), "max": max(v)}
                                            for k, v in sorted(denominators.items())},
        "trigger_frequency_by_group_and_scale": {k: dict(v) for k, v in sorted(triggers.items())},
        "reference_trigger_frequency_by_scenario": {k: dict(v) for k, v in sorted(by_scenario.items())},
        "sprint35_position19_control": [{"unit_actions": r["unit_actions"], "fire_actions": r["fire_actions"],
                                         "classes": {k: v for k, v in r["classes"].items() if v},
                                         "by_fact": r["by_fact"], "sprint35_s6": R.s6_sprint35(r),
                                         "s36": R.proposed(r)} for r in position19],
        "note": "empirical trigger frequencies on recorded games, not false-positive rates: no external ground truth "
                "classifies these games as healthy or defective, except the documented defect classes named in "
                "docs/SPRINT36_TACTICAL_RECOVERY.md section 3",
    }


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evaluation", type=Path, default=REPO_ROOT / "local" / "evaluation")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = dump(audit(args.evaluation.resolve()))
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("refusal audit identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
