"""Pre-registration validation of the T9 confirmatory study's analysis and capture (``docs/T9_CONFIRMATION.md``).

    python scripts/t9_confirmation_validation.py [--check]

Run on the evaluation server before the study's first engine session; writes
``evaluation/t9-confirmation-1/validation.json`` (aggregates only). Three parts:

1. calibration: the registered interval procedure (and its two sensitivity intervals) applied to simulated phase-A
   data: the rate at which the lower limit lies above 0 when the true contrast is 0 (nominal 2.5%) and when it is the
   exploratory estimate or half of it, under the planning standard deviations, for normal and for empirical shapes
   (the 15 historical C1 margins of 2130511121, standardised); and an independent NumPy implementation of the
   studentized bootstrap compared with the registered one on fixed data sets;
2. rehearsal: the registered per-game extraction and phase-A contrasts on existing real records (Sprint 8's six
   2130511121 head-to-head games of the candidate, the shoot-reservation experiment's 15 C1 games of the same
   scenario), checked against independently produced numbers (the exploratory reports' margins, the engine's
   ``<side>_win``, the records' own counts); the record-identity check must reject every one of these records,
   which belong to other registrations. A rehearsal, not a result: these games are never pooled into the study;
3. capture: the study's mechanism capture and Sprint 8's exploratory capture fed with the real all-seeing states of
   the two captured head-to-head games of the T7 mechanism probe (2120531121, every decision), with the candidate
   deciding offline for the ``baseline-v2`` seat on its recorded observation and memory; the two captures' common
   counts must agree, and the other seat's recorded move orders must equal its record's count.

Every private file read is pinned by SHA-256 in the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import pickle
import random
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, StateForm, StateView  # noqa: E402
from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import stats  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402
from miaosuan_agent.experiments.t9_allocation import AllocationPolicy  # noqa: E402

OUT = REPO_ROOT / "evaluation" / tc.STUDY_ID / "validation.json"
PLANNING = REPO_ROOT / "evaluation" / tc.STUDY_ID / "planning.json"
LOCAL = REPO_ROOT / "local" / "evaluation"
SIMULATIONS = 2000
SIM_RESAMPLES = 1000
CHUNK = 50
REHEARSAL_H2H = (("s8-t9-v1-h2h", "2130511121.H1.s8-t9-v1-h2h.g05"), ("s8-t9-v1-h2h", "2130511121.H2.s8-t9-v1-h2h.g06"),
                 ("s8-t9-v1-rep", "2130511121.H1.s8-t9-v1-rep.g01"), ("s8-t9-v1-rep", "2130511121.H2.s8-t9-v1-rep.g02"),
                 ("s8-t9-v1-rep", "2130511121.H1.s8-t9-v1-rep.g03"), ("s8-t9-v1-rep", "2130511121.H2.s8-t9-v1-rep.g04"))
CAPTURE_GAMES = ("2120531121.H1.pb1", "2120531121.H2.pb2")
T7_PROBE = "t7-mechanism-probe-1"


def sha256_file(path: Path, inventory: Dict[str, str]) -> bytes:
    data = path.read_bytes()
    inventory[path.relative_to(REPO_ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    return data


# ------------------------------------------------------------------------------------------------
# 1. Calibration


def simulate_chunk(task: Tuple[str, str, float, float, float, Tuple[float, ...], float, int]) -> List[List[bool]]:
    """``CHUNK`` simulated phase A analyses: [lower > 0 by bootstrap-t, by percentile, by Welch] each."""
    label, shape, sd1, sd2, effect, c1_values, c1_mean, chunk = task
    rng = random.Random(int(hashlib.sha256(f"calibration:{label}:{shape}:{effect}:{chunk}".encode()).hexdigest()[:12], 16))
    centred = [(v - statistics.mean(c1_values)) / stats.sd(c1_values) for v in c1_values]

    def draw(sd: float) -> float:
        z = rng.gauss(0.0, 1.0) if shape == "normal" else centred[stats.draw(rng, len(centred))]
        return sd * z

    out = []
    for k in range(CHUNK):
        h1 = tuple(c1_mean + effect + draw(sd1) for _ in range(15))
        h2 = tuple(-c1_mean + effect + draw(sd2) for _ in range(15))
        c1 = tuple(0.0 for _ in range(15))  # (red + blue) / 2 of a zero-sum C1 game
        strata = [tc.Stratum("H1 red", 0.5, h1), tc.Stratum("H2 blue", 0.5, h2), tc.Stratum("C1 seat average", -1.0, c1)]
        result = tc.contrast(strata, f"cal:{label}:{shape}:{effect}:{chunk}:{k}", SIM_RESAMPLES)
        out.append([result["ci_low"] > 0, result["percentile_ci"][0] > 0, result["welch_ci"][0] > 0])
    return out


def numpy_bootstrap_t(strata: List[Tuple[float, List[float]]], resamples: int, seed: int) -> Tuple[float, float]:
    """An independent implementation (NumPy, its own generator) of the studentized bootstrap interval."""
    import numpy as np

    rng = np.random.default_rng(seed)

    def est_se(groups):
        point = sum(w * g.mean(axis=-1) for w, g in groups)
        var = sum(w * w * g.var(axis=-1, ddof=1) / g.shape[-1] for w, g in groups)
        return point, np.sqrt(var)

    data = [(w, np.asarray(v, dtype=float)) for w, v in strata]
    point, se = est_se(data)
    boot = [(w, v[rng.integers(0, len(v), size=(resamples, len(v)))]) for w, v in data]
    bpoint, bse = est_se(boot)
    t = (bpoint - point) / bse
    q_low, q_high = np.quantile(t, [0.025, 0.975], method="inverted_cdf")
    return float(point - q_high * se), float(point - q_low * se)


def calibration(planning: Dict[str, Any], pool: Any) -> Dict[str, Any]:
    primary = planning["primary"]
    c1 = planning["historical_control"]["2130511121 C1"]
    c1_values = tuple(float(v) for v in c1["values"])
    assumptions = {
        "optimistic": (primary["c1_sd_sample"], primary["c1_sd_sample"]),
        "observed exploratory": (primary["exploratory_sd_h1"], primary["exploratory_sd_h2"]),
        "conservative (80% upper bounds, 2 df)": tuple(
            primary["assumptions"]["conservative: 80% upper confidence bound of each seat's exploratory SD (2 df)"][k]
            for k in ("sd_h1", "sd_h2")),
    }
    effects = {"null": 0.0, "half the exploratory estimate": primary["exploratory_estimate"] / 2,
               "exploratory estimate": primary["exploratory_estimate"]}
    tasks, cells = [], []
    for label, (sd1, sd2) in assumptions.items():
        for shape in ("normal", "empirical C1 shape"):
            for name, effect in effects.items():
                cells.append((label, shape, name))
                tasks.extend((label, shape, sd1, sd2, effect, c1_values, c1["mean"], chunk)
                             for chunk in range(SIMULATIONS // CHUNK))
    outcomes = pool.map(simulate_chunk, tasks)
    per_cell = len(tasks) // len(cells)
    table = {}
    for i, (label, shape, name) in enumerate(cells):
        rows = [row for chunk in outcomes[i * per_cell:(i + 1) * per_cell] for row in chunk]
        rates = [sum(r[j] for r in rows) / len(rows) for j in range(3)]
        table[f"{label} | {shape} | {name}"] = {
            "simulations": len(rows), "lower_limit_above_0": {"studentized (registered)": rates[0],
                                                               "percentile": rates[1], "welch": rates[2]},
            "monte_carlo_se": {"studentized (registered)": math.sqrt(rates[0] * (1 - rates[0]) / len(rows))}}
    checks = {}
    rng = random.Random(20261003)
    for n, label in ((15, "15 per stratum"), (5, "5 per stratum")):
        h1 = [rng.gauss(-600, 150) for _ in range(n)]
        h2 = [rng.gauss(1100, 110) for _ in range(n)]
        c1s = [0.0] * n
        mine = tc.contrast([tc.Stratum("H1 red", 0.5, tuple(h1)), tc.Stratum("H2 blue", 0.5, tuple(h2)),
                            tc.Stratum("C1 seat average", -1.0, tuple(c1s))], f"check:{label}", 200000)
        theirs = numpy_bootstrap_t([(0.5, h1), (0.5, h2), (-1.0, c1s)], 200000, 7)
        checks[label] = {"registered": [mine["ci_low"], mine["ci_high"]], "independent_numpy": list(theirs),
                         "se": mine["se"], "max_difference_in_se": max(abs(mine["ci_low"] - theirs[0]),
                                                                       abs(mine["ci_high"] - theirs[1])) / mine["se"]}
    return {"simulations_per_cell": SIMULATIONS, "resamples_per_interval": SIM_RESAMPLES,
            "note": "the registered analysis uses 20,000 resamples; the calibration uses 1,000 per simulated interval "
                    "for speed. Nominal one-sided error of 'lower limit above 0' is 2.5%. The C1 stratum enters as the "
                    "zero values a zero-sum C1 game gives",
            "assumptions": {k: list(v) for k, v in assumptions.items()}, "effects": effects, "table": table,
            "independent_implementation": checks}


# ------------------------------------------------------------------------------------------------
# 2. Rehearsal on real records


def rehearsal(planning: Dict[str, Any], inventory: Dict[str, str]) -> Dict[str, Any]:
    entries, facts, problems = [], [], []
    identity_rejections = 0
    published: Dict[str, int] = {}
    for card, game in REHEARSAL_H2H:
        results = json.loads(sha256_file(REPO_ROOT / "evaluation" / card / "results.json", inventory))
        published.update({g["game_id"]: g["candidate_margin"] for g in results["games"]})
    sources = [(card, game, LOCAL / card / "games" / f"{game}.json") for card, game in REHEARSAL_H2H]
    sources += [(tc.V2_ID, f"2130511121.C1.C.r{r}", LOCAL / tc.V2_ID / "games" / f"2130511121.C1.C.r{r}.json")
                for r in range(1, 16)]
    for card, game, path in sources:
        record = json.loads(sha256_file(path, inventory))
        cell = game.split(".")[1] if card != tc.V2_ID else "C1"
        entry = {"game_id": game, "phase": "A", "phase_position": len(entries) + 1, "scenario_id": "2130511121",
                 "cell": cell, "repetition": len(entries) + 1, "red": record["policies"]["red"],
                 "blue": record["policies"]["blue"]}
        f = tc.game_facts(entry, record, None, None)
        entries.append(entry)
        facts.append(f)
        if not f["margin_identity"]:
            problems.append(f"{game}: margin convention differs from <side>_win")
        if card != tc.V2_ID:
            side = "red" if cell == "H1" else "blue"
            if f["margins"][side] != published[game]:
                problems.append(f"{game}: margin {f['margins'][side]} differs from the exploratory report's {published[game]}")
        for seat_name, seat in f["seats"].items():
            original = next(s for s in record["seats"] if tc.SIDES[s["faction"]] == seat_name)
            if seat["latency"]["decisions"] != record["steps"]:
                problems.append(f"{game}: {seat_name} latency count {seat['latency']['decisions']} != steps")
            if sum(c[3] for c in seat["refusal_classes"]) != sum(original["feedback_errors_by_code"].values()):
                problems.append(f"{game}: {seat_name} refusal classes do not add up to the record's errors")
        foreign = {"policies": {p: {"policy_source": {"sha256": "x"}} for p in (tc.V2_ID, tc.CANDIDATE_ID)},
                   "execution": {"scheduler": "x"}}
        rejected = tc.record_identity_problems(record, foreign, "x" * 64)
        identity_rejections += bool(rejected)
    analysis = tc.h2h_analysis(facts, "2130511121", "rehearsal")
    seat_average = analysis["seat_average"]
    h1 = [f["margins"]["red"] for f in facts if f["cell"] == "H1"]
    h2 = [f["margins"]["blue"] for f in facts if f["cell"] == "H2"]
    expected = 0.5 * (statistics.mean(h1) + statistics.mean(h2))
    if abs(seat_average["estimate"] - expected) > 1e-9:
        problems.append("the seat average differs from 1/2 (mean H1 + mean H2)")
    if abs(expected - planning["primary"]["exploratory_estimate"]) > 1e-9:
        problems.append("the rehearsal estimate differs from the planning's exploratory estimate")
    if analysis["c1_seat_average_values"] != [0.0]:
        problems.append("a C1 game is not zero-sum")
    c1 = sorted(f["margins"]["red"] for f in facts if f["cell"] == "C1")
    if c1 != planning["historical_control"]["2130511121 C1"]["values"]:
        problems.append("the C1 margins differ from the planning's")
    systemic = tc.systemic_checks(facts)
    return {"records": len(facts), "problems": problems, "ok": not problems,
            "identity_check_rejected": identity_rejections,
            "systemic_checks": {"ok": systemic["ok"], "totals": systemic["totals"],
                                "new_refusal_classes": systemic["new_refusal_classes"]},
            "label": "REHEARSAL on exploratory and historical records: not a result of this study, never pooled",
            "seat_average": {k: seat_average[k] for k in ("estimate", "se", "ci_low", "ci_high", "percentile_ci",
                                                          "welch_ci")},
            "seat_contrasts": {s: {k: analysis[s][k] for k in ("estimate", "ci_low", "ci_high")} for s in ("red", "blue")}}


# ------------------------------------------------------------------------------------------------
# 3. Capture on real states


def view_of(fields: Dict[str, Any]) -> StateView:
    observation = Observation.from_raw(fields)
    return StateView(form=StateForm.MAPPING, red=observation, blue=observation, global_observation=observation,
                     extra_slots={})


def capture_replay(game: str, inventory: Dict[str, str]) -> Dict[str, Any]:
    record = json.loads(sha256_file(LOCAL / T7_PROBE / "games" / f"{game}.json", inventory))
    windows = pickle.loads(sha256_file(LOCAL / T7_PROBE / "capture" / f"{game}.windows.pkl", inventory))
    scenario = record["scenario_id"]
    inputs = sdk_data.load_inputs(LOCAL / T7_PROBE / "data" / scenario / "Data", scenario, record["map_id"])
    costs = MoveCosts.from_raw(inputs.cost)
    v2_faction = 0 if record["policies"]["red"] == tc.V2_ID else 1
    v2_seat = 1 if v2_faction == 0 else 11
    other_seat = 11 if v2_seat == 1 else 1
    policies = {0: record["policies"]["red"], 1: record["policies"]["blue"]}
    policies[v2_faction] = tc.CANDIDATE_ID
    samples = windows["samples"]
    if [s["k"] for s in samples] != list(range(record["steps"])) or windows["final"]["k"] != record["steps"]:
        raise SystemExit(f"{game}: the snapshots are not one per decision")
    states = [pickle.loads(s["global"]) for s in samples] + [pickle.loads(windows["final"]["global"])]
    mechanism, explore = tc.T9Capture(), xp.ExploreCapture((tc.CANDIDATE_ID, policies[1 - v2_faction]))
    observer = tc.Tee(mechanism, explore)
    observer.setup(None, (), policies)
    policy = AllocationPolicy(costs)
    candidate_moves = other_moves = 0
    empty = SimpleNamespace(addon_name="")
    for k, sample in enumerate(samples):
        seat = sample["seats"][v2_seat]
        memory = AddonMemory(baseline=pickle.loads(seat["memory"]))
        decision = policy.decide(Observation.from_raw(pickle.loads(seat["observation"])), v2_seat, v2_faction, memory)
        actions = [dict(a) for a in decision.actions]
        candidate_moves += sum(1 for a in actions if a.get("type") == tc.MOVE)
        other = sample["seats"][other_seat]
        other_moves += sum(1 for a in other["actions"] if a.get("type") == tc.MOVE)
        decisions = [{"seat": v2_seat, "faction": v2_faction, "policy": tc.CANDIDATE_ID, "submitted": actions,
                      "actions": actions, "trace": decision.trace},
                     {"seat": other_seat, "faction": 1 - v2_faction, "policy": policies[1 - v2_faction],
                      "submitted": other["actions"], "actions": other["actions"], "trace": empty}]
        observer.step(k, view_of(states[k]), view_of(states[k + 1]), decisions)
    compact = json.loads(mechanism.file())
    explore_compact = json.loads(explore.files()[0])
    problems = []
    for color in ("0", "1"):
        if compact["series_checks"][color]["waiting"] != explore_compact["waiting_ground_units"][color]:
            problems.append(f"waiting series of side {color}")
        if compact["series_checks"][color]["commitment_max"] != explore_compact["max_objective_commitment"][color]:
            problems.append(f"commitment series of side {color}")
    if compact["addon_changes"] != explore_compact["addon_changes"]:
        problems.append("add-on changes")
    if compact["addon_skips"] != explore_compact["addon_skips"]:
        problems.append("add-on skips")
    if compact["steps"] != record["steps"]:
        problems.append("step count")
    if compact["seats"][str(v2_faction)]["moves"]["emitted"] != candidate_moves:
        problems.append("candidate move orders")
    recorded = next(s for s in record["seats"] if s["faction"] != v2_faction)["actions_by_type"].get("1", 0)
    if compact["seats"][str(1 - v2_faction)]["moves"]["emitted"] != recorded or other_moves != recorded:
        problems.append("the other seat's move orders differ from its record's count")
    final = states[-1]
    held_value = {f: sum(c["value"] for c in final["cities"] if c["flag"] == f) for f in (0, 1)}
    occupy = {f: record["final_scores"][f"{tc.SIDES[f]}_occupy"] for f in (0, 1)}
    if compact["seats"][str(v2_faction)]["objectives"]["held_value_at_end"] != held_value[v2_faction]:
        problems.append("held value at the end")
    seat = compact["seats"][str(v2_faction)]
    return {"game": game, "steps": record["steps"], "candidate_side": tc.SIDES[v2_faction], "problems": problems,
            "ok": not problems, "candidate_moves_offline": candidate_moves, "other_seat_moves": other_moves,
            "final_held_value": {tc.SIDES[f]: v for f, v in held_value.items()},
            "final_occupy_score": {tc.SIDES[f]: v for f, v in occupy.items()},
            "held_value_equals_occupy_score": held_value == occupy,
            "candidate_seat_facts_offline": {k: seat[k] for k in ("moves", "withholding", "waiting_in_front_of_full_hex",
                                                                  "max_objective_commitment")},
            "note": "the candidate decided offline on states produced by baseline-v2's play; its counts describe "
                    "the capture's behaviour on real observations, not the candidate's play"}


# ------------------------------------------------------------------------------------------------


def build() -> Dict[str, Any]:
    inventory: Dict[str, str] = {}
    planning = json.loads(sha256_file(PLANNING, inventory))
    with multiprocessing.Pool(min(32, multiprocessing.cpu_count())) as pool:
        cal = calibration(planning, pool)
    rehearse = rehearsal(planning, inventory)
    captures = [capture_replay(game, inventory) for game in CAPTURE_GAMES]
    digest = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(inventory.items())).encode("utf-8")).hexdigest()
    return {"schema": "miaosuan-t9-confirmation-validation/1", "study_id": tc.STUDY_ID,
            "inventory": {"files": len(inventory), "sha256": digest,
                          "planning_sha256": inventory[PLANNING.relative_to(REPO_ROOT).as_posix()]},
            "calibration": cal, "rehearsal": rehearse, "capture": captures,
            "ok": bool(rehearse["ok"] and all(c["ok"] for c in captures))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    print(f"rehearsal ok {result['rehearsal']['ok']} {result['rehearsal']['problems']}; captures "
          f"{[(c['game'], c['ok'], c['problems']) for c in result['capture']]}")
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {OUT.relative_to(REPO_ROOT).as_posix()}")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()} sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
