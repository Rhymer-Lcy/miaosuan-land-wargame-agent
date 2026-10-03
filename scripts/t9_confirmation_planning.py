"""Planning figures of the T9 confirmatory study, computed before registration (``docs/T9_CONFIRMATION.md``).

    python scripts/t9_confirmation_planning.py [--check]

Reads private records (evaluation server): ``baseline-v2``'s games of the registered shoot-reservation experiment
(group C, 15 per configuration) for every configuration the study plays, and the Sprint 8 exploratory games of the
candidate. Writes ``evaluation/t9-confirmation-1/planning.json``: per-configuration control distributions (sample and
population standard deviations), the candidate's exploratory margins, the prospective power of the primary contrast
under optimistic and conservative variance assumptions, planning figures of the secondary phases and the false-alarm
rates of the phase B and D gates on ``baseline-v2``'s own games (the null: both arms are ``baseline-v2``). The record
inventory (SHA-256 of every file read) is pinned in the output, so a later change of the records is detected.

The Sprint 8 games enter only the planning variance and the effect sizes of the power table; they are never pooled
into the study.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import stats  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402

OUT = REPO_ROOT / "evaluation" / tc.STUDY_ID / "planning.json"
CONTROL = REPO_ROOT / "local" / "evaluation" / tc.V2_ID / "games"
SPRINT8 = [REPO_ROOT / "local" / "evaluation" / card / "games" for card in
           ("s8-t9-v1-mechanism", "s8-t9-v1-h2h", "s8-t9-v1-rep")]
N = 15
NULL_SIMULATIONS = 2000
NULL_RESAMPLES = 1000
EFFECT_FRACTIONS = (1.0, 0.5, 0.25)


def read(path: Path, inventory: Dict[str, str]) -> Dict[str, Any]:
    data = path.read_bytes()
    inventory[path.relative_to(REPO_ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    return json.loads(data.decode("utf-8"))


def describe(values: List[int]) -> Dict[str, Any]:
    return {"n": len(values), "mean": statistics.mean(values), "sd_sample": stats.sd(values),
            "sd_population": statistics.pstdev(values), "min": min(values), "max": max(values),
            "distinct": len(set(values)), "values": sorted(values)}


def chi2_upper_sd(sd: float, df: int, confidence: float) -> float:
    """The one-sided upper confidence bound of a standard deviation from ``df`` degrees of freedom."""
    return sd * math.sqrt(df / stats.chi2_quantile(1.0 - confidence, df))


def primary_se(sd_h1: float, sd_h2: float, n: int = N) -> float:
    """Standard error of the seat-averaged contrast: the C1 games contribute 0 (zero-sum margins)."""
    return 0.5 * math.sqrt(sd_h1 ** 2 / n + sd_h2 ** 2 / n)


CHUNK = 100


def false_alarm_chunk(task: Tuple[str, str, List[int], int]) -> int:
    """Alarms in one chunk of simulated phases: both arms drawn (with replacement) from ``baseline-v2``'s own games
    of the configuration, the phase's registered rule applied."""
    phase, key, values, chunk = task
    rng = random.Random(int(hashlib.sha256(f"planning:{phase}:{key}:{chunk}".encode("utf-8")).hexdigest()[:12], 16))
    n = tc.PHASES[phase]["repetitions"]
    alarms = 0
    for k in range(CHUNK):
        t9 = tuple(float(values[stats.draw(rng, len(values))]) for _ in range(n))
        v2 = tuple(float(values[stats.draw(rng, len(values))]) for _ in range(n))
        strata = [tc.Stratum("T9", 1.0, t9), tc.Stratum("V2", -1.0, v2)]
        if phase == "D":
            alarms += tc.estimate(strata) < -tc.MATERIAL_MARGIN
        else:
            alarms += tc.contrast(strata, f"null:{key}:{chunk}:{k}", NULL_RESAMPLES)["ci_high"] < -tc.MATERIAL_MARGIN
    return alarms


def build() -> Dict[str, Any]:
    inventory: Dict[str, str] = {}
    control: Dict[str, List[int]] = {}
    for path in sorted(CONTROL.glob("*.C.r*.json")):
        record = read(path, inventory) if path.name.split(".")[0] in {s for p in tc.PHASES.values() for s in p["scenarios"]} else None
        if record is None:
            continue
        if record["status"] != "COMPLETED":
            raise SystemExit(f"{path.name} did not complete")
        scores = record["final_scores"]
        if not tc.margin_identity(scores):
            raise SystemExit(f"{path.name}: the margin convention disagrees with <side>_win")
        control.setdefault(f"{record['scenario_id']} {record['condition']}", []).append(tc.seat_margin(scores, 0))
    if any(len(v) != N for v in control.values()) or len(control) != 3 * 8:
        raise SystemExit(f"unexpected control inventory: { {k: len(v) for k, v in control.items()} }")
    exploratory: Dict[str, List[int]] = {}
    for folder in SPRINT8:
        for path in sorted(folder.glob("*.json")):
            record = read(path, inventory)
            if record["status"] != "COMPLETED" or not tc.margin_identity(record["final_scores"]):
                raise SystemExit(f"{path.name}: not completed or margin convention disagrees")
            side = 0 if record["policies"]["red"] == tc.CANDIDATE_ID else 1
            exploratory.setdefault(f"{record['scenario_id']} {record['condition']}", []).append(
                tc.seat_margin(record["final_scores"], side))
    h1, h2 = exploratory["2130511121 H1"], exploratory["2130511121 H2"]
    c1 = control["2130511121 C1"]
    s_c1, s_h1, s_h2 = stats.sd(c1), stats.sd(h1), stats.sd(h2)
    pooled = math.sqrt(((len(h1) - 1) * s_h1 ** 2 + (len(h2) - 1) * s_h2 ** 2) / (len(h1) + len(h2) - 2))
    effect = 0.5 * (statistics.mean(h1) + statistics.mean(h2))
    assumptions = {
        "optimistic: both seats at the historical C1 standard deviation": (s_c1, s_c1),
        "observed exploratory standard deviations per seat (3 games each)": (s_h1, s_h2),
        "pooled exploratory standard deviation (6 games, 4 df)": (pooled, pooled),
        "conservative: 80% upper confidence bound of each seat's exploratory SD (2 df)":
            (chi2_upper_sd(s_h1, 2, 0.8), chi2_upper_sd(s_h2, 2, 0.8)),
        "conservative: 80% upper confidence bound of the pooled SD (4 df)":
            (chi2_upper_sd(pooled, 4, 0.8), chi2_upper_sd(pooled, 4, 0.8)),
        "very conservative: 95% upper confidence bound of each seat's exploratory SD (2 df)":
            (chi2_upper_sd(s_h1, 2, 0.95), chi2_upper_sd(s_h2, 2, 0.95)),
    }
    power = {}
    for label, (a, b) in assumptions.items():
        se = primary_se(a, b)
        power[label] = {"sd_h1": a, "sd_h2": b, "se": se,
                        "mde_80": stats.minimum_detectable(se, 0.05, 0.8),
                        "mde_90": stats.minimum_detectable(se, 0.05, 0.9),
                        "power": {f"{f:g} x exploratory estimate ({f * effect:.1f})":
                                  stats.power_two_sided(f * effect, se) for f in EFFECT_FRACTIONS}}
    secondary_c = {}
    for scenario in tc.PHASES["C"]["scenarios"]:
        s = stats.sd(control[f"{scenario} C1"])
        se = primary_se(s, s)
        secondary_c[scenario] = {"c1_sd_sample": s, "se_if_candidate_sd_equals_control": se,
                                 "mde_80": stats.minimum_detectable(se, 0.05, 0.8)}
    secondary_b = {}
    for scenario in tc.PHASES["B"]["scenarios"]:
        for condition in ("C2", "C3"):
            s = stats.sd(control[f"{scenario} {condition}"])
            se = math.sqrt(2 * s ** 2 / N)
            secondary_b[f"{scenario} {condition}"] = {"control_sd_sample": s, "se_if_candidate_sd_equals_control": se,
                                                      "mde_80": stats.minimum_detectable(se, 0.05, 0.8)}
    tasks, keys = [], []
    for phase in ("D", "B"):
        for scenario in tc.PHASES[phase]["scenarios"]:
            for condition in ("C2", "C3"):
                key = f"{scenario} {condition}"
                values = [m if condition == "C2" else -m for m in control[key]]
                keys.append((phase, key))
                tasks.extend((phase, key, values, chunk) for chunk in range(NULL_SIMULATIONS // CHUNK))
    with multiprocessing.Pool(min(32, multiprocessing.cpu_count())) as pool:
        counts = pool.map(false_alarm_chunk, tasks)
    alarms: Dict[Tuple[str, str], int] = {}
    for (phase, key, _, _), count in zip(tasks, counts):
        alarms[(phase, key)] = alarms.get((phase, key), 0) + count
    false_alarms = {f"{phase} {key}": {"simulations": NULL_SIMULATIONS, "alarms": alarms[(phase, key)],
                                       "rate": alarms[(phase, key)] / NULL_SIMULATIONS,
                                       "resamples_per_interval": NULL_RESAMPLES if phase == "B" else None}
                    for phase, key in keys}
    inventory_digest = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(inventory.items())).encode("utf-8")).hexdigest()
    return {
        "schema": "miaosuan-t9-confirmation-planning/1", "study_id": tc.STUDY_ID,
        "record_inventory": {"files": len(inventory), "sha256": inventory_digest},
        "margin_convention": "seat margin = own <side>_total - other side's total = the engine's <side>_win (checked "
                             "on every record read)",
        "historical_control": {k: describe(v) for k, v in sorted(control.items())},
        "candidate_exploratory": {k: describe(v) for k, v in sorted(exploratory.items())},
        "note_on_the_proposal": "docs/T9_CONFIRMATION_PROPOSAL.md quoted population standard deviations of the "
                                "controls (110.8, 566.7, 437.9); the sample standard deviations are the planning "
                                "basis here",
        "primary": {"exploratory_estimate": effect,
                    "exploratory_pair_nets": [a + b for a, b in zip(h1, h2)],
                    "se_formula": "1/2 sqrt(sd_H1^2 / 15 + sd_H2^2 / 15); the C1 games cancel from the seat average",
                    "c1_sd_sample": s_c1, "exploratory_sd_h1": s_h1, "exploratory_sd_h2": s_h2,
                    "pooled_exploratory_sd": pooled, "assumptions": power,
                    "caveat": "the exploratory estimate comes from 6 games selected for promise and is likely "
                              "overstated; 3 games per seat estimate a standard deviation imprecisely (the 95% "
                              "upper bound with 2 df is 4.4 times the estimate)"},
        "seat_contrast_se_example": {"sd_h1": s_h1, "sd_c1": s_c1,
                                     "se": math.sqrt(s_h1 ** 2 / N + s_c1 ** 2 / N)},
        "secondary_c": secondary_c, "secondary_b": secondary_b,
        "gate_false_alarms_on_baseline_v2": false_alarms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {OUT.relative_to(REPO_ROOT).as_posix()}")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()} sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
