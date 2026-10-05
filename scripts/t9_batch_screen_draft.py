"""DRAFT schedule and frozen reference values of a proposed Sprint 12 screen of ``t9-batch-capacity-v3``.

    python scripts/t9_batch_screen_draft.py [--check]

DRAFT - UNAPPROVED - NO ENGINE AUTHORIZATION (``docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md``). Writes
``evaluation/s12-batch-allocator-draft/draft.json``: the proposed stages and games, the session ceiling, every
reference value the proposal's rules use, and the behaviour of those rules on games that already exist. The file is not
a run card: its schema is not the run-card schema, so ``scripts/run_explore.sh`` refuses it, and it carries
``executable: false``. Nothing here opens, plans or authorizes an engine session.

Inputs are committed public files only, pinned by SHA-256 in the output: Sprint 9's phase A and phase B results and its
planning file, and Sprint 10's exploratory results. One declared constant is not derived here: the approximate
objective coverage of the two Sprint 10 T9-v2 head-to-head games, read once from their private 50-step capture
snapshots (``T9V2_SNAPSHOT_COVERAGE``, with its calibration against the every-step definition).

The rule checks are descriptive properties of the proposed rules, measured on existing games before any Sprint 12 game
exists, so that the rules are not chosen from Sprint 12 results. They are not significance tests and carry no
confirmatory meaning. Where a threshold is the extreme of a reference population, the check recomputes it without the
games being classified (leave-out), so that a game is never compared with a floor it defines itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.evaluation.metrics import nearest_rank  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "s12-batch-allocator-draft" / "draft.json"
SCHEMA = "miaosuan-proposal-draft/1"
STATUS = "DRAFT — UNAPPROVED — NO ENGINE AUTHORIZATION"
V3_ID = "t9-batch-capacity-v3"
V2_ID = "baseline-v2-candidate-shoot-target-reservation"
INERT_ID = "inert-v0"
V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
V3_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_batch.py")
FROZEN = {"baseline-v2": "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae",
          "t9-capacity-allocation-v1": "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa",
          "t9-capacity-staging-v2": "66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece",
          V3_ID: "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8"}
LEDGER_BASE_SESSION = 2786
SESSION_CEILING = 12
MAX_STEP = 2880
INFANTRY_HEX_STEPS = 144  # one infantry hex time on the Sprint 2 diagnosed route (docs/TACTICAL_FRONTIER.md)
HALF_PLAY = 1440  # half the play stage, the convention of Sprint 9's "units idle for half the play stage"
SIMULATIONS = 20000
SEED = 20261005

INPUTS = {
    "phase_a": "evaluation/t9-confirmation-1/phase-A.json",
    "phase_b": "evaluation/t9-confirmation-1/phase-B.json",
    "planning": "evaluation/t9-confirmation-1/planning.json",
    "s10_results": "evaluation/s10-t9-v2-exploration/results.json",
}

#: Read once, read-only, from the private Sprint 10 captures of sessions 2785 and 2786 (50-step snapshots, 57 per game,
#: play stage). The same approximation applied to the 45 Sprint 9 phase A games differs from the every-step mean by
#: -0.0320 to +0.0636 for the red seat and -0.0281 to +0.0714 for the blue seat.
T9V2_SNAPSHOT_COVERAGE = {"H1": 0.4211, "H2": 5.8772}
#: The same approximation for the six Sprint 8 exploratory T9-v1 games of 2130511121 (sessions 2473, 2474, 2484 to
#: 2487), in session order per seat.
T9V1_EXPLORATORY_SNAPSHOT_COVERAGE = {"H1": [0.7544, 1.1930, 1.1579], "H2": [5.4561, 5.3684, 5.4737]}
SNAPSHOT_CALIBRATION = {"games": 45, "red": [-0.0320, 0.0636], "blue": [-0.0281, 0.0714]}

STAGES = (
    {"stage": "P1", "proposed_card": "s12-v3-primary-1", "max_sessions": 4,
     "runs_if": "the owner approves and the screen is registered; nothing earlier",
     "games": (("2130511121", "H1", V3_ID, V2_ID), ("2130511121", "H2", V2_ID, V3_ID),
               ("2130511121", "H1", V3_ID, V2_ID), ("2130511121", "H2", V2_ID, V3_ID))},
    {"stage": "P2", "proposed_card": "s12-v3-primary-2", "max_sessions": 2,
     "runs_if": "the committed P1 report finds no stop and no interim tactical stop",
     "games": (("2130511121", "H1", V3_ID, V2_ID), ("2130511121", "H2", V2_ID, V3_ID))},
    {"stage": "A1", "proposed_card": "s12-v3-adverse-1", "max_sessions": 3,
     "runs_if": "the committed primary report classifies the primary PRESERVED_DIRECTIONALLY or AMBIGUOUS",
     "games": (("2120531121", "C3", INERT_ID, V3_ID), ("1930331196", "C2", V3_ID, INERT_ID),
               ("1930331196", "C3", INERT_ID, V3_ID))},
    {"stage": "A2", "proposed_card": "s12-v3-adverse-2", "max_sessions": 3,
     "runs_if": "per configuration, only if the committed A1 report names a replication trigger for it",
     "games": (("2120531121", "C3", INERT_ID, V3_ID), ("1930331196", "C2", V3_ID, INERT_ID),
               ("1930331196", "C3", INERT_ID, V3_ID))},
)

ADVERSE = {"2120531121 C3": {"cell": "C3", "side": "blue", "occupy_all": 310},
           "1930331196 C3": {"cell": "C3", "side": "blue", "occupy_all": 310},
           "1930331196 C2": {"cell": "C2", "side": "red", "occupy_all": 310}}


def read(relative: str, inventory: Dict[str, str]) -> Any:
    data = (REPO_ROOT / relative).read_bytes()
    inventory[relative] = hashlib.sha256(data).hexdigest()
    return json.loads(data.decode("utf-8"))


def describe(values: Sequence[float]) -> Dict[str, Any]:
    ordered = sorted(values)
    return {"n": len(ordered), "min": ordered[0], "median": nearest_rank(ordered, 50), "max": ordered[-1],
            "mean": round(sum(ordered) / len(ordered), 4), "values": ordered}


# ------------------------------------------------------------------------------------------------
# Primary-scenario references (2130511121)


def primary_rows(phase_a: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Per-game seat facts of Sprint 9 phase A: T9-v1 H1 red, T9-v1 H2 blue, baseline-v2 C1 red and blue."""
    rows: Dict[str, List[Dict[str, Any]]] = {"t9v1 H1": [], "t9v1 H2": [], "v2 C1 red": [], "v2 C1 blue": []}
    for game in sorted(phase_a["games"], key=lambda g: (g["cell"], g["repetition"])):
        for side in ("red", "blue"):
            other = "blue" if side == "red" else "red"
            if game["cell"] == "H1" and side != "red" or game["cell"] == "H2" and side != "blue":
                continue
            key = {"H1": "t9v1 H1", "H2": "t9v1 H2"}.get(game["cell"], f"v2 C1 {side}")
            mechanism = game["seats"][side]["mechanism"]
            scores = game["scores"]
            if game["margins"][side] != scores[f"{side}_win"]:
                raise SystemExit(f"{game['game_id']}: margin is not the engine's {side}_win")
            rows[key].append({"repetition": game["repetition"], "margin": game["margins"][side],
                              "coverage": mechanism["objectives"]["mean_held"],
                              "held_at_end": mechanism["objectives"]["held_at_end"],
                              "lost": mechanism["losses"]["lost"],
                              "waiting": mechanism["waiting_in_front_of_full_hex"]["sum"],
                              "attack": scores[f"{side}_attack"], "remain": scores[f"{side}_remain"],
                              "opponent_total": scores[f"{other}_total"]})
    if any(len(v) != 15 for v in rows.values()):
        raise SystemExit("phase A does not hold 15 games per seat population")
    return rows


def t9v2_smoke(s10: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for game in s10["games"]:
        if game["scenario_id"] != "2130511121":
            continue
        side = game["candidate_side"]
        other = "blue" if side == "red" else "red"
        scores = game["scores"]
        out[game["condition"]] = {"session": game["session"], "margin": game["candidate_margin"],
                                  "attack": scores[f"{side}_attack"], "occupy": scores[f"{side}_occupy"],
                                  "remain": scores[f"{side}_remain"], "opponent_total": scores[f"{other}_total"],
                                  "objectives_at_end": game["objectives_final"]["candidate"],
                                  "waiting_sum": game["waiting_ground_units"][str(0 if side == "red" else 1)]["sum"],
                                  "withheld_unit_decisions": game["mechanism"]["withhold_actions"],
                                  "stage_actions": game["mechanism"]["stage_actions"],
                                  "coverage_snapshot_approx": T9V2_SNAPSHOT_COVERAGE[game["condition"]]}
    if sorted(out) != ["H1", "H2"]:
        raise SystemExit("Sprint 10 results do not hold one H1 and one H2 game of 2130511121")
    return out


def thresholds(t9v1_h1: Sequence[Mapping[str, Any]], t9v1_h2: Sequence[Mapping[str, Any]],
               v2_red: Sequence[Mapping[str, Any]], v2_blue: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """The primary rule's floors: T9-v1's lowest H1 coverage and lowest H2 margin; collapse below the lowest fresh
    baseline-v2 margin of the seat."""
    return {"h1_coverage_floor": min(r["coverage"] for r in t9v1_h1),
            "h2_margin_floor": min(r["margin"] for r in t9v1_h2),
            "h1_collapse_below": min(r["margin"] for r in v2_red),
            "h2_collapse_below": min(r["margin"] for r in v2_blue)}


def t9v2_like(seat: str, game: Mapping[str, Any], floors: Mapping[str, float]) -> bool:
    if seat == "H1":
        return game["coverage"] < floors["h1_coverage_floor"]
    return game["margin"] < floors["h2_margin_floor"]


def collapse(seat: str, game: Mapping[str, Any], floors: Mapping[str, float]) -> bool:
    key = "h1_collapse_below" if seat == "H1" else "h2_collapse_below"
    return game["margin"] < floors[key]


def interim_stop(h1: Sequence[Mapping[str, Any]], h2: Sequence[Mapping[str, Any]], floors: Mapping[str, float]) -> bool:
    """After two games per seat: stop on two or more collapse games, or when all four games are T9-v2-like."""
    collapses = sum(collapse("H1", g, floors) for g in h1) + sum(collapse("H2", g, floors) for g in h2)
    like = sum(t9v2_like("H1", g, floors) for g in h1) + sum(t9v2_like("H2", g, floors) for g in h2)
    return collapses >= 2 or like == len(h1) + len(h2)


def final_class(h1: Sequence[Mapping[str, Any]], h2: Sequence[Mapping[str, Any]], floors: Mapping[str, float],
                preserved_seat_average: float) -> str:
    """After three games per seat."""
    collapses = sum(collapse("H1", g, floors) for g in h1) + sum(collapse("H2", g, floors) for g in h2)
    like_h1 = sum(t9v2_like("H1", g, floors) for g in h1)
    like_h2 = sum(t9v2_like("H2", g, floors) for g in h2)
    if collapses >= 2 or (like_h1 >= 2 and like_h2 >= 2):
        return "NOT_PRESERVED"
    seat_average = (sum(g["margin"] for g in h1) / len(h1) + sum(g["margin"] for g in h2) / len(h2)) / 2
    if collapses == 0 and like_h1 + like_h2 <= 1 and seat_average >= preserved_seat_average:
        return "PRESERVED_DIRECTIONALLY"
    return "AMBIGUOUS"


def simulate(name: str, h1_pool: Sequence[Mapping[str, Any]], h2_pool: Sequence[Mapping[str, Any]],
             reference: Tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]], v2_red, v2_blue,
             preserved: float, leave_out: bool, shared_games: bool) -> Dict[str, Any]:
    """Apply the proposed primary rules to draws of three games per seat from existing games.

    ``leave_out``: the T9-v1 floors are recomputed from the reference games not drawn (the pools are the reference).
    ``shared_games``: the H1 and H2 pools are the two seats of the same games (C1), so draws use distinct games."""
    rng = random.Random(f"{SEED}:{name}")
    counts = {"interim stop": 0, "NOT_PRESERVED": 0, "AMBIGUOUS": 0, "PRESERVED_DIRECTIONALLY": 0}
    for _ in range(SIMULATIONS):
        if shared_games:
            picked = rng.sample(range(len(h1_pool)), 6)
            i1, i2 = picked[:3], picked[3:]
        else:
            i1, i2 = rng.sample(range(len(h1_pool)), 3), rng.sample(range(len(h2_pool)), 3)
        h1 = [h1_pool[i] for i in i1]
        h2 = [h2_pool[i] for i in i2]
        if leave_out:
            ref_h1 = [g for i, g in enumerate(reference[0]) if i not in i1]
            ref_h2 = [g for i, g in enumerate(reference[1]) if i not in i2]
        else:
            ref_h1, ref_h2 = reference
        floors = thresholds(ref_h1, ref_h2, v2_red, v2_blue)
        if interim_stop(h1[:2], h2[:2], floors):
            counts["interim stop"] += 1
            continue
        counts[final_class(h1, h2, floors, preserved)] += 1
    rates = {k: round(v / SIMULATIONS, 4) for k, v in counts.items()}
    rates["stopped before the adverse stage"] = round((counts["interim stop"] + counts["NOT_PRESERVED"]) / SIMULATIONS, 4)
    return {"draws": SIMULATIONS, "seed": f"{SEED}:{name}", "leave_out_floors": leave_out, "rates": rates}


# ------------------------------------------------------------------------------------------------
# Adverse configurations (against the inert control)


def adverse_rows(phase_b: Mapping[str, Any]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for game in phase_b["games"]:
        cell, arm = game["cell"].split("-")
        key = f"{game['scenario_id']} {cell}"
        if key not in ADVERSE:
            continue
        side = ADVERSE[key]["side"]
        scores = game["scores"]
        if game["margins"][side] != scores[f"{side}_win"]:
            raise SystemExit(f"{game['game_id']}: margin is not the engine's {side}_win")
        out.setdefault(key, {"T9": [], "V2": []})[arm].append(
            {"margin": game["margins"][side], "attack": scores[f"{side}_attack"], "occupy": scores[f"{side}_occupy"]})
    for key, arms in out.items():
        if sorted(arms) != ["T9", "V2"] or any(len(v) != 15 for v in arms.values()):
            raise SystemExit(f"phase B does not hold 15 games per arm in {key}")
    if sorted(out) != sorted(ADVERSE):
        raise SystemExit("phase B lacks an adverse configuration")
    return out


def adverse_thresholds(key: str, v2: Sequence[Mapping[str, Any]], t9: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    if key == "2120531121 C3":
        return {"margin_at_least": min(g["margin"] for g in v2)}
    return {"attack_at_least": min(g["attack"] for g in v2), "attack_at_most_regressed": max(g["attack"] for g in t9)}


def classify_adverse(key: str, game: Mapping[str, Any], limits: Mapping[str, int]) -> str:
    occupy_all = ADVERSE[key]["occupy_all"]
    if key == "2120531121 C3":
        if game["occupy"] < occupy_all:
            return "NOT_REPAIRED"
        return "REPAIRED" if game["margin"] >= limits["margin_at_least"] else "PARTIAL"
    if game["occupy"] < occupy_all or game["attack"] <= limits["attack_at_most_regressed"]:
        return "REGRESSED"
    return "AVOIDED" if game["attack"] >= limits["attack_at_least"] else "AMBIGUOUS"


def adverse_checks(rows: Mapping[str, Mapping[str, List[Dict[str, Any]]]], s10: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in sorted(ADVERSE):
        v2, t9 = rows[key]["V2"], rows[key]["T9"]
        limits = adverse_thresholds(key, v2, t9)
        loo: Dict[str, Dict[str, int]] = {"baseline-v2 arm": {}, "T9-v1 arm": {}}
        for label, arm in (("baseline-v2 arm", "V2"), ("T9-v1 arm", "T9")):
            for i, game in enumerate(rows[key][arm]):
                own_v2 = [g for j, g in enumerate(v2) if not (arm == "V2" and j == i)]
                own_t9 = [g for j, g in enumerate(t9) if not (arm == "T9" and j == i)]
                cls = classify_adverse(key, game, adverse_thresholds(key, own_v2, own_t9))
                loo[label][cls] = loo[label].get(cls, 0) + 1
        sprint10 = []
        for game in s10["games"]:
            if f"{game['scenario_id']} {game['condition']}" != key:
                continue
            side = game["candidate_side"]
            row = {"margin": game["candidate_margin"], "attack": game["scores"][f"{side}_attack"],
                   "occupy": game["scores"][f"{side}_occupy"]}
            sprint10.append({"session": game["session"], **row, "class": classify_adverse(key, row, limits)})
        out[key] = {"candidate_side": ADVERSE[key]["side"], "thresholds": limits,
                    "baseline_v2": {"margin": describe([g["margin"] for g in v2]),
                                    "attack": describe([g["attack"] for g in v2]),
                                    "occupy": sorted({g["occupy"] for g in v2})},
                    "t9_v1": {"margin": describe([g["margin"] for g in t9]),
                              "attack": describe([g["attack"] for g in t9]),
                              "occupy": sorted({g["occupy"] for g in t9})},
                    "leave_one_out_classes_of_sprint9_games": {k: dict(sorted(v.items())) for k, v in loo.items()},
                    "sprint10_t9_v2_games": sorted(sprint10, key=lambda r: r["session"])}
    return out


# ------------------------------------------------------------------------------------------------


def schedule() -> Dict[str, Any]:
    stages, position = [], 0
    for stage in STAGES:
        games = []
        for scenario, condition, red, blue in stage["games"]:
            position += 1
            games.append({"position": position, "scenario_id": scenario, "condition": condition, "red": red,
                          "blue": blue})
        if len(games) != stage["max_sessions"]:
            raise SystemExit(f"stage {stage['stage']}: games and sessions differ")
        stages.append({"stage": stage["stage"], "proposed_card": stage["proposed_card"],
                       "max_sessions": stage["max_sessions"], "runs_if": stage["runs_if"], "games": games})
    total = sum(s["max_sessions"] for s in stages)
    if total != SESSION_CEILING:
        raise SystemExit(f"the stages hold {total} sessions, not the ceiling {SESSION_CEILING}")
    return {"ledger_base_session": LEDGER_BASE_SESSION, "session_ceiling": SESSION_CEILING,
            "sessions_if_no_stop_and_no_replication": sum(s["max_sessions"] for s in stages[:3]),
            "workers": 1, "session_mode": "exclusive diagnostic sessions, serial",
            "runtime": "baseline-v1-runtime-r2", "stages": stages}


def build() -> Dict[str, Any]:
    inventory: Dict[str, str] = {}
    phase_a, phase_b = read(INPUTS["phase_a"], inventory), read(INPUTS["phase_b"], inventory)
    planning, s10 = read(INPUTS["planning"], inventory), read(INPUTS["s10_results"], inventory)
    identities = {name: digest_of_files(policy_source_files(sources=sources)) for name, sources in
                  (("baseline-v2", V2_SOURCES), (V3_ID, V3_SOURCES))}
    for name, value in identities.items():
        if value != FROZEN[name]:
            raise SystemExit(f"{name}'s policy source is {value}, not the frozen {FROZEN[name]}")

    rows = primary_rows(phase_a)
    h1, h2, red, blue = rows["t9v1 H1"], rows["t9v1 H2"], rows["v2 C1 red"], rows["v2 C1 blue"]
    floors = thresholds(h1, h2, red, blue)
    exploratory = planning["primary"]["exploratory_estimate"]
    preserved = exploratory / 2
    historical = planning["historical_control"]["2130511121 C1"]["values"]
    smoke = t9v2_smoke(s10)
    # The every-step value is at most the snapshot value minus the most negative calibration difference.
    smoke_classes = {"H1": smoke["H1"]["coverage_snapshot_approx"] - SNAPSHOT_CALIBRATION["red"][0]
                     < floors["h1_coverage_floor"],
                     "H2": smoke["H2"]["margin"] < floors["h2_margin_floor"]}
    exploratory_h2 = planning["candidate_exploratory"]["2130511121 H2"]["values"]
    # The every-step value is at least the snapshot value minus the largest calibration difference.
    exploratory_h1_below = sum(value - SNAPSHOT_CALIBRATION["red"][1] < floors["h1_coverage_floor"]
                               for value in T9V1_EXPLORATORY_SNAPSHOT_COVERAGE["H1"])
    fields = ("margin", "coverage", "held_at_end", "lost", "waiting", "attack", "remain", "opponent_total")
    primary = {
        "scenario": "2130511121",
        "populations": {
            label: {field: describe([r[field] for r in rows[key]]) for field in fields}
            for label, key in (("T9-v1 registered H1 red (Sprint 9 phase A)", "t9v1 H1"),
                               ("T9-v1 registered H2 blue (Sprint 9 phase A)", "t9v1 H2"),
                               ("baseline-v2 C1 red (Sprint 9 phase A)", "v2 C1 red"),
                               ("baseline-v2 C1 blue (Sprint 9 phase A)", "v2 C1 blue"))},
        "baseline_v2_historical_C1_red_margins": describe(historical),
        "t9_v1_exploratory_margins": {"H1": describe(planning["candidate_exploratory"]["2130511121 H1"]["values"]),
                                      "H2": describe(exploratory_h2)},
        "t9_v2_smoke": smoke,
        "registered_t9_v1_seat_average": 305.47,
        "exploratory_t9_v1_seat_average": exploratory,
        "t9_v2_smoke_seat_average": (smoke["H1"]["margin"] + smoke["H2"]["margin"]) / 2,
        "rule_values": {**floors, "preserved_seat_average_at_least": preserved},
        "t9_v2_smoke_games_below_the_floors": smoke_classes,
        "t9_v1_exploratory_h2_games_below_the_floor": sum(v < floors["h2_margin_floor"] for v in exploratory_h2),
        "t9_v1_exploratory_h1_games_possibly_below_the_floor": exploratory_h1_below,
        "rule_checks": {
            "candidate drawn from T9-v1's registered games, floors from the other twelve per seat":
                simulate("t9v1", h1, h2, (h1, h2), red, blue, preserved, leave_out=True, shared_games=False),
            "candidate drawn from baseline-v2's C1 games, floors from all fifteen T9-v1 games":
                simulate("v2", red, blue, (h1, h2), red, blue, preserved, leave_out=False, shared_games=True),
        },
    }
    return {
        "schema": SCHEMA, "status": STATUS, "executable": False, "approved": False, "registered": False,
        "proposal": "docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md",
        "candidate": {"id": V3_ID, "policy_source_sha256": identities[V3_ID]},
        "baseline": {"id": V2_ID, "policy_source_sha256": identities["baseline-v2"]},
        "frozen_identities": FROZEN,
        "inputs": dict(sorted(inventory.items())),
        "declared_constants": {
            "t9_v2_snapshot_coverage": T9V2_SNAPSHOT_COVERAGE, "snapshot_calibration": SNAPSHOT_CALIBRATION,
            "t9_v1_exploratory_snapshot_coverage": T9V1_EXPLORATORY_SNAPSHOT_COVERAGE,
            "max_step": MAX_STEP, "infantry_hex_steps": INFANTRY_HEX_STEPS, "half_play_stage": HALF_PLAY},
        "schedule": schedule(),
        "primary": primary,
        "adverse": adverse_checks(adverse_rows(phase_b), s10),
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
