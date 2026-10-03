"""Build, or check, an EXPLORATORY run card (``docs/EXPLORATORY_TRACK.md``).

    python scripts/build_run_card.py --card s8-t4-v1-mechanism [--check]
    python scripts/build_run_card.py --list

A card is written to ``evaluation/<card>/manifest.json`` and committed before the first game of its batch. Its inputs
are committed: the shoot-reservation experiment's manifest (the frozen scenarios with their input digests, players,
caps and randomness procedure); every policy's source digest is computed from this checkout, and ``baseline-v2``'s
must equal the frozen digest. Cards are only ever added to ``CARDS``: a card's definition is not edited after its
batch has started (a new version gets a new card). ``--check`` fails unless the committed card is byte-identical to a
fresh build.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t4_artillery as t4  # noqa: E402
from miaosuan_agent.experiments import t4_artillery_v2 as t4b  # noqa: E402
from miaosuan_agent.experiments import t4_artillery_v3 as t4c  # noqa: E402
from miaosuan_agent.experiments import t9_allocation as t9  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
V2_ID = sx.CANDIDATE_ID
ADDON = "experiments/exploratory_addon.py"
RUNTIME = "baseline-v1-runtime-r2"
CANDIDATES = {
    t4.CANDIDATE_ID: {"label": "T4 indirect artillery fire, version 1", "modules": (ADDON, "experiments/t4_artillery.py")},
    t4b.CANDIDATE_ID: {"label": "T4 indirect artillery fire, version 2",
                       "modules": (ADDON, "experiments/t4_artillery.py", "experiments/t4_artillery_v2.py")},
    t4c.CANDIDATE_ID: {"label": "T4 indirect artillery fire, version 3",
                       "modules": (ADDON, "experiments/t4_artillery.py", "experiments/t4_artillery_v2.py",
                                   "experiments/t4_artillery_v3.py")},
    t9.CANDIDATE_ID: {"label": "T9 capacity-limited objective allocation, version 1",
                      "modules": (ADDON, "experiments/t9_allocation.py")},
}

COMMON_SAFETY = [
    "every game through scripts/run_explore.sh: persistent engine installation, session ledger, "
    "integrity check at session open and close, no reinstall, no change to the engine or its state file",
    "policy source digests of baseline-v2 and the candidate checked before the first game, by every game and after the "
    "last game; baseline-v2's digest must be the frozen 7cbaf032...",
    "the batch is refused if the sprint's ledger-counted session cap (24 after session 2464) would be exceeded",
    "clean committed tree; records and captures are never overwritten; no game is retried or replaced",
    "stop the sprint on an integrity failure, a ledger inconsistency, a privacy exposure or an unexplained systemic "
    "contract failure (contract errors, add-on errors or a game failure without an understood cause)",
]
HISTORICAL_CONTROL = ("baseline-v2's own games of the registered shoot-reservation experiment (group C, 15 per "
                      "configuration, same engine and code identity; baseline-v1-runtime-r2 makes the same decisions): "
                      "C1 mirror for a head-to-head seat, C2 or C3 for a game against the inert control")

CARDS: Dict[str, Dict[str, Any]] = {
    "s8-t4-v1-mechanism": {
        "candidate": t4.CANDIDATE_ID, "workers": 2,
        "games": [("2120531121", "H1", "t4", V2_ID), ("1930331196", "C2", "t4", INERT_ID)],
        "texts": {
            "version": "t4-artillery-v1, mechanism batch 1",
            "mechanism": "baseline-v2 leaves artillery idle; the candidate orders each idle unit that lists indirect "
                         "fire (action 8, option weapon_id) to fire at the best safe hex holding seen enemy ground units "
                         "(stationary first, objectives next, then summed value), at most one unit per hex per step, "
                         "skipping hexes near own ground units or own move paths, hexes under own fire, and units whose "
                         "weapon_cool_time is positive",
            "controls": HISTORICAL_CONTROL + "; within each game, the add-on block's baseline_trace_sha256 gives "
                        "baseline-v2's own decision for every candidate decision",
            "configurations": "2120531121 H1: candidate red against baseline-v2 blue (active opponent; enemies within "
                              "about 15 hexes of the artillery early); 1930331196 C2: candidate red against the inert "
                              "control (stationary enemies 20 to 35 hexes away: range and damage against stationary "
                              "targets)",
            "safety_checks": COMMON_SAFETY + [
                "the add-on checks every indirect-fire order itself: listed weapon, exact key set, one action per unit",
                "baseline-v2's actions are emitted first and unchanged"],
            "intended_observations": [
                "whether indirect-fire orders are accepted, and every refusal code and message",
                "flight and explosion durations from jm_points; the plan's cooldown from weapon_cool_time",
                "whether ammunition counters change (artillery lists remain_bullet_nums of 0)",
                "indirect-fire judgements: hit or scatter, correction status, damage, and any own unit damaged",
                "whether a target beyond 20 hexes is accepted (the engine data lists 20 for weapon 72)",
                "terminal scores against the historical baseline-v2 control; decision latency"],
            "next_step_rule": "a candidate that cannot execute its order, causes an unexplained refusal or hits own "
                              "units is corrected or rejected before it receives more games; one that works goes to "
                              "a matched head-to-head batch against baseline-v2 in the artillery scenarios, both seats",
        },
    },
    "s8-t9-v1-mechanism": {
        "candidate": t9.CANDIDATE_ID, "workers": 2,
        "games": [("2130511121", "C3", INERT_ID, "t9"), ("2120531121", "C2", "t9", INERT_ID)],
        "texts": {
            "version": "t9-capacity-allocation-v1, mechanism batch 1",
            "mechanism": "baseline-v2 sends every movable unit to the cheapest unheld objective, so a dozen or more "
                         "ground units converge on one hex that holds four; the candidate keeps a ground move only "
                         "while its destination has fewer than 4 commitments (standing, en route, assigned this step), "
                         "otherwise re-assigns it to the unheld objective under capacity with the lowest path cost per "
                         "objective value within twice the original cost, or withholds it for this step",
            "controls": HISTORICAL_CONTROL + "; within each game, the add-on block's baseline_trace_sha256 gives "
                        "baseline-v2's own decision for every candidate decision",
            "configurations": "2130511121 C3: candidate blue against the inert control (largest force, 7 objectives); "
                              "2120531121 C2: candidate red against the inert control (5 objectives)",
            "safety_checks": COMMON_SAFETY + [
                "every replaced move passes the project gate with the step's other actions, or reverts to baseline-v2's",
                "only ground move orders change; shots, occupations, air units and idle units are untouched"],
            "intended_observations": [
                "how many moves are kept, replaced and withheld, and whether replaced moves are accepted",
                "own ground units waiting in front of a full hex, and the largest objective commitment, per step",
                "objectives held over time and terminal scores against the historical baseline-v2 control",
                "refusals, contract errors, add-on errors and decision latency"],
            "next_step_rule": "a candidate whose replaced moves are refused, that leaves units withheld for long "
                              "periods without reaching objectives, or that loses clearly against the inert control is "
                              "corrected or rejected; one that works goes to a matched head-to-head batch against "
                              "baseline-v2, both seats",
        },
    },
    "s8-t9-v1-h2h": {
        "candidate": t9.CANDIDATE_ID, "workers": 1,
        "games": [("2120531121", "H1", "t9", V2_ID), ("2120531121", "H2", V2_ID, "t9"),
                  ("1930331196", "H1", "t9", V2_ID), ("1930331196", "H2", V2_ID, "t9"),
                  ("2130511121", "H1", "t9", V2_ID), ("2130511121", "H2", V2_ID, "t9")],
        "texts": {
            "version": "t9-capacity-allocation-v1 (unchanged), head-to-head batch 1",
            "mechanism": "as in s8-t9-v1-mechanism: ground moves kept while the destination has fewer than 4 "
                         "commitments, otherwise re-assigned within twice the cost by cost per value, or withheld",
            "controls": HISTORICAL_CONTROL + "; the mechanism batch placed the candidate above all 15 control games "
                        "against the inert control in both scenarios it played (s8-t9-v1-mechanism)",
            "configurations": "the three large scenarios (5, 5 and 7 objectives, where baseline-v2 commits up to 17 "
                              "ground units to one objective): H1 candidate red against baseline-v2 blue and H2 "
                              "baseline-v2 red against candidate blue, one game each",
            "safety_checks": COMMON_SAFETY + [
                "every replaced move passes the project gate with the step's other actions, or reverts to baseline-v2's",
                "only ground move orders change; shots, occupations, air units and idle units are untouched"],
            "intended_observations": [
                "candidate margin per game against the C1 mirror control of the same seat (directional only: the "
                "control's standard deviation is 111 to 567 points)",
                "occupation and attack score components, losses (remain), objectives held at the end",
                "kept, replaced and withheld moves; waiting ground units; refusals, errors and latency"],
            "next_step_rule": "if the candidate is at or above the control mean in most games without a new failure "
                              "class it is the leading candidate for a confirmatory study; a clear loss pattern "
                              "against active opponents (for example withheld units never committed while objectives "
                              "are lost) is diagnosed from the captures and answered by a new version",
        },
    },
    "s8-t4-v2-batch": {
        "candidate": t4b.CANDIDATE_ID, "workers": 1,
        "games": [("1930331196", "C2", "t4b", INERT_ID),
                  ("2120531121", "H1", "t4b", V2_ID), ("2120531121", "H2", V2_ID, "t4b"),
                  ("1930331196", "H1", "t4b", V2_ID), ("1930331196", "H2", V2_ID, "t4b"),
                  ("2130511121", "H1", "t4b", V2_ID), ("2130511121", "H2", V2_ID, "t4b")],
        "texts": {
            "version": "t4-artillery-v2, mechanism check and head-to-head batch 1",
            "mechanism": "version 1 (s8-t4-v1-mechanism) plus two changes answering its recorded failures: enemy ground "
                         "units last seen stationary are remembered for 600 steps at their last hex (version 1 fired "
                         "once in 2,880 steps against the inert control because the enemy was out of sight), and only "
                         "hexes with an own round still in flight are excluded (a round lands about 150 steps after "
                         "the order and the hex explodes for about 300 steps; units inside are judged on landing)",
            "controls": HISTORICAL_CONTROL + "; version 1's games in s8-t4-v1-mechanism; within each game the add-on "
                        "block's baseline_trace_sha256",
            "configurations": "1930331196 C2: candidate red against the inert control, the configuration of version 1's "
                              "game 2 (control 272.9, SD 4.0); then the three artillery scenarios head to head, H1 "
                              "candidate red against baseline-v2 blue and H2 baseline-v2 red against candidate blue",
            "safety_checks": COMMON_SAFETY + [
                "the add-on checks every indirect-fire order itself: listed weapon, exact key set, one action per unit",
                "baseline-v2's actions are emitted first and unchanged",
                "any indirect-fire judgement on an own unit is reported per game (none in version 1's games)"],
            "intended_observations": [
                "orders per game and their tier (seen, remembered, moving), acceptance and refusals",
                "judgements: correction status, damage to enemy units, any damage to own units",
                "candidate margin per game against the control of the same seat; attack and remain components",
                "decision latency"],
            "next_step_rule": "if remembered targets produce damage and the margins sit at or above the control mean "
                              "without own damage, T4 is a candidate for confirmation; own damage, refusals or a clear "
                              "loss pattern lead to a corrected version or to shelving",
        },
    },
    "s8-t9-v1-rep": {
        "candidate": t9.CANDIDATE_ID, "workers": 1,
        "games": [("2130511121", "H1", "t9", V2_ID), ("2130511121", "H2", V2_ID, "t9"),
                  ("2130511121", "H1", "t9", V2_ID), ("2130511121", "H2", V2_ID, "t9")],
        "texts": {
            "version": "t9-capacity-allocation-v1 (unchanged), head-to-head replication in the largest scenario",
            "mechanism": "as in s8-t9-v1-mechanism and s8-t9-v1-h2h, unchanged",
            "controls": HISTORICAL_CONTROL + "; 2130511121 is the head-to-head scenario with the least variable control "
                        "(C1 mirror margin SD 111 over 15 games), where s8-t9-v1-h2h placed the candidate above the "
                        "control mean in both seats (+0.49 and +2.37 standard deviations)",
            "configurations": "2130511121: H1 candidate red against baseline-v2 blue and H2 baseline-v2 red against "
                              "candidate blue, two games each",
            "safety_checks": COMMON_SAFETY + [
                "every replaced move passes the project gate with the step's other actions, or reverts to baseline-v2's",
                "only ground move orders change; shots, occupations, air units and idle units are untouched"],
            "intended_observations": [
                "whether the placement above the control repeats in fresh games of the same configurations",
                "kept, replaced and withheld moves; waiting ground units on both sides; refusals, errors and latency"],
            "next_step_rule": "the four games plus s8-t9-v1-h2h decide whether T9 is proposed for a confirmatory "
                              "study; they are not that study and are never pooled into it",
        },
    },
    "s8-t4-v3-check": {
        "candidate": t4c.CANDIDATE_ID, "workers": 1,
        "games": [("2130511121", "H1", "t4c", V2_ID), ("2130511121", "H2", V2_ID, "t4c")],
        "texts": {
            "version": "t4-artillery-v3, friendly-fire mechanism check",
            "mechanism": "version 2 (s8-t4-v2-batch) plus one exclusion: no target hex within 4 hexes of any objective; "
                         "in version 2's games 55 of 58 own-unit judgements came from own units entering a still "
                         "exploding hex, and every such hex lay within 4 hexes of an objective",
            "controls": HISTORICAL_CONTROL + "; version 2's games of the same configurations in s8-t4-v2-batch, which "
                        "judged own units 14 and 15 times",
            "configurations": "2130511121: H1 candidate red against baseline-v2 blue and H2 baseline-v2 red against "
                              "candidate blue, one game each",
            "safety_checks": COMMON_SAFETY + [
                "the add-on checks every indirect-fire order itself: listed weapon, exact key set, one action per unit",
                "baseline-v2's actions are emitted first and unchanged",
                "every indirect-fire judgement on an own unit is reported"],
            "intended_observations": [
                "own-unit judgements and own damage from own indirect fire (version 2: 14 and 15 judgements)",
                "orders per game and damage to enemy units, against version 2's",
                "candidate margin against the control of the same seat"],
            "next_step_rule": "if own judgements disappear and orders remain, version 3 is the T4 form for any later "
                              "batch; if own judgements remain, the exclusion zone is not the mechanism and T4 needs "
                              "a movement-side guard, which is outside an add-on that leaves baseline-v2's moves alone",
        },
    },
}


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def policy_source(sources: Tuple[str, ...]) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def game_rows(card_id: str, card: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate = card["candidate"]
    short = {"t4": t4.CANDIDATE_ID, "t4b": t4b.CANDIDATE_ID, "t4c": t4c.CANDIDATE_ID, "t9": t9.CANDIDATE_ID}
    rows = []
    for k, (sid, condition, red, blue) in enumerate(card["games"], start=1):
        red, blue = short.get(red, red), short.get(blue, blue)
        if candidate not in (red, blue):
            raise SystemExit(f"{card_id}: game {k} does not play the candidate")
        rows.append({"game_id": f"{sid}.{condition}.{card_id}.g{k:02d}", "scenario_id": sid, "condition": condition,
                     "red": red, "blue": blue})
    return rows


def build(card_id: str) -> Dict[str, Any]:
    card = CARDS[card_id]
    shoot = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
    shoot_manifest = load(shoot)
    baseline = policy_source(V2_SOURCES)
    if baseline["sha256"] != V2_DIGEST:
        raise SystemExit(f"baseline-v2's source is {baseline['sha256']}, not the frozen digest")
    entry = CANDIDATES[card["candidate"]]
    policies = [{"id": V2_ID, "label": "baseline-v2 (frozen)", "policy_source": baseline},
                {"id": card["candidate"], "label": entry["label"], "policy_source": policy_source(V2_SOURCES + entry["modules"])}]
    games = game_rows(card_id, card)
    texts = {"status": "EXPLORATORY - NOT ELIGIBLE FOR BASELINE PROMOTION", **card["texts"]}
    return xp.build(card_id, texts, shoot_manifest, mf.digest(shoot_manifest), policies, card["candidate"], games,
                    RUNTIME, card["workers"], {"batch_sessions": len(games), "ledger_base_session": xp.LEDGER_BASE_SESSION,
                                               "sprint_session_cap": xp.SPRINT_SESSION_CAP})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", choices=sorted(CARDS))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for card_id in CARDS:
            print(card_id)
        return 0
    if not args.card:
        parser.error("--card is required")
    out = REPO_ROOT / "evaluation" / args.card / "manifest.json"
    card = build(args.card)
    text = json.dumps(card, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    digest = xp.digest(card)
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
        return 0 if same else 1
    if out.exists():
        if out.read_text(encoding="utf-8") == text:
            print(f"unchanged {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
            return 0
        print(f"REFUSED: {out.relative_to(REPO_ROOT).as_posix()} exists with other content; a card is never rewritten",
              file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
