"""Sprint 36 live-study calibration from the recorded control games (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 19).

    python scripts/s36_calibration.py [--check]

From the private records of the 26 Stage A games of the Sprint 34 control (16 in Sprint 34's card, 10 as Sprint 35's
fresh control) and the 9 games of the Sprint 35 candidate: each game's stake (``evaluation.s36_live.stake``) and share
of the stake, the pooled within-configuration SD of the control's shares, the thresholds derived from it, the
empirical trigger counts of the severe-harm rules on both policies' games, and, beside it, the Sprint 35 z of each game
(the scale Sprint 36 replaces). Refuses to publish when the derived constants differ from ``evaluation.s36_live``'s.
Writes ``evaluation/s36-tactical-recovery/live-calibration.json`` (no unit id or hex); ``--check`` compares.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s36_live as L  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "live-calibration.json"
REFERENCES = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "references.json"
CARDS = ("s34-integrated-live-1", "s35-coalition-live-1")


def games() -> List[Dict[str, Any]]:
    refs = json.loads(REFERENCES.read_text(encoding="utf-8"))["configs"]
    rows = []
    for card in CARDS:
        base = REPO_ROOT / "local" / "evaluation" / card
        for path in sorted((base / "games").glob("*.json")):
            if ".H1." not in path.name and ".H2." not in path.name:
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            compact = json.loads((base / "capture" / f"{path.stem}.timeline.json").read_text(encoding="utf-8"))
            condition = record["condition"]
            side = "red" if condition == "H1" else "blue"
            policy = record["policies"][side]
            total = L.stake(record, compact)
            margin = record["final_scores"][f"{side}_win"]
            ref = refs[f"{record['scenario_id']}.C1"][side]["win"]
            rows.append({"card": card, "scenario_id": record["scenario_id"], "side": side,
                         "policy": "S34-MO" if policy == L.S34_CONTROL else "S35-CM" if policy == L.S35_CONTROL
                         else policy, "margin": margin, "stake": total, "share": round(margin / total, 6),
                         "z_sprint35_scale": round((margin - ref["mean"]) / ref["sd"], 6) if ref["sd"] else None,
                         "below_reference_min": margin < ref["min"],
                         "below_min_minus_3sd": margin < ref["min"] - L.SEVERE_SD * ref["sd"]})
    return rows


def build() -> Dict[str, Any]:
    rows = games()
    control = [r for r in rows if r["policy"] == "S34-MO"]
    by = collections.defaultdict(list)
    for r in control:
        by[(r["scenario_id"], r["side"])].append(r["share"])
    ss, df = 0.0, 0
    for values in by.values():
        if len(values) > 1:
            mean = sum(values) / len(values)
            ss += sum((v - mean) ** 2 for v in values)
            df += len(values) - 1
    sd = round(math.sqrt(ss / df), 4)
    derived = {"share_sd": sd, "null_sd_dbar": round(sd / math.sqrt(10), 4),
               "unfavourable_dbar": round(-1.96 * round(sd / math.sqrt(10), 4), 4),
               "null_sd_dbar_a1": round(sd * math.sqrt(2) / math.sqrt(10), 4),
               "early_futility": round(-2.576 * round(sd * math.sqrt(2) / math.sqrt(10), 4), 4)}
    registered = {"share_sd": L.SHARE_SD, "null_sd_dbar": L.NULL_SD_DBAR, "unfavourable_dbar": L.UNFAVOURABLE_DBAR,
                  "null_sd_dbar_a1": L.NULL_SD_DBAR_A1, "early_futility": L.EARLY_FUTILITY}
    if derived != registered:
        raise SystemExit(f"derived constants {derived} differ from evaluation.s36_live {registered}")
    stakes = {f"{r['scenario_id']}": r["stake"] for r in rows}
    cm = [r for r in rows if r["policy"] == "S35-CM"]
    descriptive = {}
    for sid in L.STAGE_A_SCENARIOS:
        for side in ("red", "blue"):
            a = [r for r in cm if (r["scenario_id"], r["side"]) == (sid, side)]
            b = [r for r in control if (r["scenario_id"], r["side"]) == (sid, side)]
            if a and b:
                descriptive[f"{sid} {side}"] = {
                    "share_difference": round(sum(x["share"] for x in a) / len(a) - sum(x["share"] for x in b) / len(b), 6),
                    "z_difference": round(sum(x["z_sprint35_scale"] for x in a) / len(a)
                                          - sum(x["z_sprint35_scale"] for x in b) / len(b), 6)}
    mean_share = round(sum(v["share_difference"] for v in descriptive.values()) / len(descriptive), 6)
    mean_z = round(sum(v["z_difference"] for v in descriptive.values()) / len(descriptive), 6)
    return {
        "schema": "miaosuan-s36-live-calibration/1",
        "source": "Sprint 34 control: 16 Sprint 34 Stage A games and 10 Sprint 35 control games; Sprint 35 candidate: "
                  "9 games (development data, descriptive only)",
        "stakes": dict(sorted(stakes.items())), "control_games": len(control), "candidate_games_s35": len(cm),
        "configurations": len(by), "degrees_of_freedom": df, "derived": derived,
        "control_shares": {f"{k[0]} {k[1]}": v for k, v in sorted(by.items())},
        "severe_harm_rule_triggers": {
            "control_below_min_minus_3sd": sum(r["below_min_minus_3sd"] for r in control),
            "candidate_s35_below_min_minus_3sd": sum(r["below_min_minus_3sd"] for r in cm),
            "control_below_reference_min": sum(r["below_reference_min"] for r in control),
            "candidate_s35_below_reference_min": sum(r["below_reference_min"] for r in cm)},
        "z_scale_artifact": {"largest_control_z": max(r["z_sprint35_scale"] for r in control),
                             "its_configuration": next(f"{r['scenario_id']} {r['side']}" for r in control
                                                       if r["z_sprint35_scale"] == max(x["z_sprint35_scale"]
                                                                                       for x in control))},
        "sprint35_descriptive_difference": {"per_configuration": descriptive, "mean_share_difference": mean_share,
                                            "mean_z_difference": mean_z,
                                            "note": "one game per configuration and policy, nine configurations, "
                                                    "development data: not a registered comparison"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("live calibration identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(text[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
