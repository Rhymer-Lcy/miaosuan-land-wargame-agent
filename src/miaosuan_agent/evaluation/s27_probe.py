"""The registered Sprint 27 T6-S two-seat mechanism probe (``docs/SPRINT27_T6S_PROBE.md``): every rule.

At most two exclusive engine sessions, 2797 then 2798, of the exploratory mechanism candidate ``t6s-column-stagger-p1``
(``experiments/t6s_column_stagger_p1.py``) against frozen ``baseline-v2`` in scenario 2130511121: stage A (session
2797) the candidate blue, stage B (session 2798) the candidate red, the second only if the first passes the registered
stage gate. An exploratory mechanism probe: not a score screen, not a confirmation; nothing is promoted and no score,
margin, winner or kill count enters any rule.

This module fixes, before session 2797: the identities, the card and its pins, the session budget and the ledger
audit, the per-game structural checks, the registered-difference check, the frozen HH references and the P1 and P2
rules, every mechanism fact, the mechanism-observation rule, the stage gate, the disposition order and the public
sanitization. Nothing here reads an engine, a capture or the ledger by itself; callers pass the data in.
"""

from __future__ import annotations

import collections
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..experiments import t6s_column_stagger_p1 as cand
from . import exploratory as xp
from . import manifest as mf
from . import s12_screen as sc
from . import s18_census as census
from .t7_candidates import weapon_range
from .t7_visibility import hex_distance

STUDY_ID = "s27-t6s-probe"
CARD_ID = "s27-t6s-probe-1"
SCHEMA = "miaosuan-s27-probe/1"
CANDIDATE_ID = cand.CANDIDATE_ID
V2_ID, V2_DIGEST = sc.V2_ID, sc.V2_DIGEST
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2796
SESSION_CEILING = 2
EXPECTED_SESSIONS = (2797, 2798)
WORKERS = 1
SCENARIO = "2130511121"
MOVE = 1
#: (position, scenario, condition, red, blue). Position 1 is stage A (session 2797): the candidate blue against
#: baseline-v2 red; position 2 is stage B (session 2798): the candidate red against baseline-v2 blue. Conditions follow
#: Sprint 12's labels (H1 the candidate red, H2 the candidate blue).
SCHEDULE: Tuple[Tuple[int, str, str, str, str], ...] = ((1, SCENARIO, "H2", V2_ID, CANDIDATE_ID),
                                                        (2, SCENARIO, "H1", CANDIDATE_ID, V2_ID))
STAGES = {"A": 1, "B": 2}
HH_LABELS = {"blue": ("HH p01 baseline-v2 blue", "HH p03 baseline-v2 blue"),
             "red": ("HH p02 baseline-v2 red", "HH p04 baseline-v2 red")}
OBJECTIVES = ("50-point objective A", "50-point objective B", "50-point objective C", "50-point objective D",
              "80-point objective A", "80-point objective B", "80-point objective C")

# ------------------------------------------------------------------------------------------------
# Rules (frozen before session 2797)

#: Every threshold, reference and window. The references are the committed ``evaluation/s27-t6s-probe/references.json``
#: (scripts/s27_analysis.py references): Sprint 26's published per-side exposure of the four HH ``baseline-v2`` seats
#: and their first-ownership steps by Sprint 26's own loader and functions.
RULES: Dict[str, Any] = {
    "max_step": 2880,
    "scenario": SCENARIO,
    "follow_up_window_steps": 300,
    "p1": {
        "endpoint": "E4: over the play decisions of the candidate's seat-game, the own ground unit-decisions in which "
                    "the unit is moving (a non-empty route or a positive speed), stacked (the engine's stack field) "
                    "and inside an applicable envelope (a visible enemy's published direct-fire range against the "
                    "unit's type covers its hex); evaluation/s26_t6s.exposure, key moving_stacked_inside_envelope",
        "rule": "triggered when candidate E4 exceeds one half of the arithmetic mean of E4 over the two same-colour "
                "HH baseline-v2 seat-games (in exact integers: four times candidate E4 exceeds their sum); equality "
                "passes",
        "references": {"blue": {"HH p01 baseline-v2 blue": 9122, "HH p03 baseline-v2 blue": 29248},
                       "red": {"HH p02 baseline-v2 red": 6518, "HH p04 baseline-v2 red": 6489}},
    },
    "p2": {
        "endpoint": "the first-ownership step of an objective: the cur_step of the first play decision of the seat at "
                    "which the objective's flag reads the seat's colour (evaluation/s26_t6s.first_ownership); never "
                    "when no play decision of the seat-game shows it",
        "rule": "owner-approved same-colour reading: for every objective first owned by the candidate's colour in at "
                "least one of its two same-colour HH references, the reference step is the latest finite "
                "first-ownership step among those two; P2 is triggered when the candidate never first-owns that "
                "objective or first-owns it at a later step; equality passes; an objective neither same-colour "
                "reference first-owned has no timing reference and is reported separately",
        "references": {
            "blue": {"50-point objective A": {"HH p01 baseline-v2 blue": 161, "HH p03 baseline-v2 blue": 161},
                     "50-point objective B": {"HH p01 baseline-v2 blue": 222, "HH p03 baseline-v2 blue": 222},
                     "50-point objective C": {"HH p01 baseline-v2 blue": 364, "HH p03 baseline-v2 blue": 364},
                     "50-point objective D": {"HH p01 baseline-v2 blue": 442, "HH p03 baseline-v2 blue": 442},
                     "80-point objective A": {"HH p01 baseline-v2 blue": 421, "HH p03 baseline-v2 blue": 421},
                     "80-point objective B": {"HH p01 baseline-v2 blue": 283, "HH p03 baseline-v2 blue": 283},
                     "80-point objective C": {"HH p01 baseline-v2 blue": 161, "HH p03 baseline-v2 blue": 161}},
            "red": {"50-point objective A": {"HH p02 baseline-v2 red": 421, "HH p04 baseline-v2 red": 421},
                    "50-point objective B": {"HH p02 baseline-v2 red": 543, "HH p04 baseline-v2 red": 543},
                    "50-point objective C": {"HH p02 baseline-v2 red": 2737, "HH p04 baseline-v2 red": 561},
                    "50-point objective D": {"HH p02 baseline-v2 red": 401, "HH p04 baseline-v2 red": 401},
                    "80-point objective A": {"HH p02 baseline-v2 red": None, "HH p04 baseline-v2 red": None},
                    "80-point objective B": {"HH p02 baseline-v2 red": 482, "HH p04 baseline-v2 red": 482},
                    "80-point objective C": {"HH p02 baseline-v2 red": None, "HH p04 baseline-v2 red": 604}}},
        "sensitivity": "Sprint 24's wording read with all four HH baseline-v2 seats (both colours): the latest finite "
                       "first-ownership step among the four; reported only, never a stop",
    },
    "mechanism": {
        "executed_episode": "an episode on the live trajectory that completed before the game's end and in which at "
                            "least one withheld follower was released because its reference was observed off the "
                            "shared start hex (release reason reference_left) and was afterwards observed on a "
                            "readable hex other than the start hex",
        "observed": "a session observes the mechanism when it has at least one executed episode; otherwise the "
                    "session is MECHANISM_NOT_OBSERVED whatever its exposure",
    },
    "stage_gate": "stage B (session 2798) is authorized only when session 2797 completed with no structural stop, P1 "
                  "and P2 not triggered and the mechanism observed",
    "expected_opening_divergence_steps": {"blue": 161, "red": 401},
}
STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7", "SF")
STOP_MEANING = {
    "S1": "engine-installation integrity failure (session close or the ledger's state chain)",
    "S2": "ledger inconsistency, a wrong card, game, stage or digest, an unclosed session, or a session beyond 2797 "
          "and 2798 or out of order",
    "S3": "privacy or repository exposure: a file outside the ignored tree appeared, or a tracked file changed, during "
          "the game",
    "S4": "a contract error, a wrong margin identity or a game that did not complete",
    "S6": "a replay mismatch",
    "S7": "capture or reconstruction failure: an observer error, a missing or digest-mismatched capture, a live "
          "decision or memory of either seat that differs from its seat-local reconstruction, a difference from "
          "baseline-v2 that is not a registered withholding, a candidate add-on error, disagreeing counts, a wrong "
          "scenario, condition, seat or opponent policy, a max_step other than 2,880, or objective labels other than "
          "the registered seven",
    "SF": "offline fidelity failure: a decision whose emitted list differs from Sprint 26's frozen rule replayed on the "
          "live trajectory through Sprint 26's own analysis, an unexplained difference under Sprint 26's independent "
          "check, rule events that differ from the frozen rule's, an offline re-derivation or memory-chain difference "
          "of either seat, or a candidate list other than baseline-v2's before the first withholding",
}
DISPOSITIONS = ("T6S_P1_INVALID", "T6S_P1_MECHANISM_NOT_OBSERVED", "T6S_P1_MECHANISM_NOT_SUPPORTED",
                "T6S_P1_MECHANISM_SUPPORTED")
INVALID, NOT_OBSERVED, NOT_SUPPORTED, SUPPORTED = DISPOSITIONS

#: Files whose normalised SHA-256 the card pins.
FROZEN_FILES = (
    "src/miaosuan_agent/experiments/t6s_column_stagger_p1.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "src/miaosuan_agent/experiments/t9_batch.py",
    "src/miaosuan_agent/evaluation/t7_candidates.py",
    "src/miaosuan_agent/evaluation/t7_audit.py",
    "src/miaosuan_agent/evaluation/t7_visibility.py",
    "src/miaosuan_agent/evaluation/s27_probe.py",
    "src/miaosuan_agent/evaluation/s27_capture.py",
    "src/miaosuan_agent/evaluation/s26_t6s.py",
    "src/miaosuan_agent/evaluation/s18_census.py",
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/t9_confirmation.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/game.py",
    "scripts/build_s27_card.py",
    "scripts/run_s27_game.py",
    "scripts/run_s27_probe.py",
    "scripts/s27_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_s12_stage.py",
    "tests/test_t6s_column_stagger_p1.py",
    "tests/test_s27_probe.py",
    "tests/fixtures/s27_engine.py",
)

TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED MECHANISM PROBE - NOT A SCORE SCREEN - NOT ELIGIBLE FOR PROMOTION",
    "version": "t6s-column-stagger-p1, Sprint 27 T6-S two-seat mechanism probe (docs/SPRINT27_T6S_PROBE.md)",
    "mechanism": "baseline-v2 plays the seat on its own observation at every decision; Sprint 26's frozen T6-S rule "
                 "lets the leader of a stacked co-departure under visible threat go and withholds the followers' "
                 "baseline-v2 MOVEs until the reference has left the shared start hex (wait bound 2 * hex time + 10)",
    "controls": "historical and descriptive only: the two same-colour Sprint 12 HH baseline-v2 seat-games of each seat "
                "order; no new control game; not a randomized or paired control",
    "configurations": "2130511121 head to head against frozen baseline-v2: stage A the candidate blue (session 2797), "
                      "stage B the candidate red (session 2798) only if stage A passes its gate",
    "safety_checks": ["structural stops after every game (S1, S2, S3, S4, S6, S7) and the offline fidelity stop SF",
                      "at most two sessions after closed session 2796, in schedule order, exclusive diagnostic sessions",
                      "every frozen implementation file pinned by digest; any difference refuses the card",
                      "the candidate's policy source pinned; baseline-v2's to 7cbaf032..."],
    "intended_observations": ["Sprint 9's T9Capture, the exploratory capture and the Sprint 27 full-step timeline with "
                              "the seat-local reconstruction of both seats and the candidate's memory chain at every "
                              "decision"],
    "next_step_rule": "mechanical stage gate after session 2797 (s27_probe.stage_gate); after the analysis the study "
                      "returns to the owner",
}
#: The candidate's policy source (baseline-v2's set, the add-on wrapper, the free-flow and published-range helpers and
#: the candidate module), fixed before session 2797.
CANDIDATE_DIGEST = "9d74eb78208ff7ad10b33b3974f2831754122dba2bff1684177d6fbd4b44e29e"


def normalized_sha256(path: Path) -> str:
    return sc.normalized_sha256(path)


def frozen_digests(repo: Path) -> Dict[str, str]:
    return {rel: normalized_sha256(repo / rel) for rel in FROZEN_FILES}


def rules_digest() -> str:
    return hashlib.sha256(json.dumps(RULES, sort_keys=True).encode("utf-8")).hexdigest()


def game_id(position: int, scenario: str, condition: str) -> str:
    return f"{scenario}.{condition}.{CARD_ID}.p{position:02d}"


def games() -> List[Dict[str, Any]]:
    return [{"game_id": game_id(p, s, c), "scenario_id": s, "condition": c, "red": r, "blue": b, "screen_position": p}
            for p, s, c, r, b in SCHEDULE]


def candidate_side(entry: Mapping[str, Any]) -> str:
    sides = [side for side in ("red", "blue") if entry.get(side) == CANDIDATE_ID]
    others = [side for side in ("red", "blue") if entry.get(side) == V2_ID]
    if len(sides) != 1 or len(others) != 1:
        raise ValueError("a game must seat the candidate against baseline-v2")
    return sides[0]


def build_card(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, policies: Sequence[Mapping[str, Any]],
               frozen: Mapping[str, str]) -> Dict[str, Any]:
    by_id = {p["id"]: p for p in policies}
    if sorted(by_id) != sorted((V2_ID, CANDIDATE_ID)):
        raise ValueError("the card's policies are baseline-v2 and the Sprint 27 candidate only")
    if (by_id[CANDIDATE_ID]["policy_source"]["sha256"] != CANDIDATE_DIGEST
            or by_id[V2_ID]["policy_source"]["sha256"] != V2_DIGEST):
        raise ValueError("a policy source is not the registered one")
    if sorted(frozen) != sorted(FROZEN_FILES):
        raise ValueError("the frozen file set differs from FROZEN_FILES")
    rows = games()
    if len(rows) != SESSION_CEILING:
        raise ValueError("the schedule is not exactly the two registered games")
    budget = {"batch_sessions": len(rows), "ledger_base_session": LEDGER_BASE_SESSION,
              "sprint_session_cap": SESSION_CEILING}
    card = xp.build(CARD_ID, TEXTS, shoot_manifest, shoot_manifest_sha256, policies, CANDIDATE_ID, rows, RUNTIME,
                    WORKERS, budget)
    for row, game in zip(card["games"], rows):
        row["screen_position"] = game["screen_position"]
    card["screen"] = {"id": STUDY_ID, "stage": "probe", "stages": {k: v for k, v in STAGES.items()},
                      "rules": RULES, "rules_sha256": rules_digest(), "frozen_files": dict(sorted(frozen.items())),
                      "expected_sessions": list(EXPECTED_SESSIONS), "structural_stops": list(STRUCTURAL_STOPS)}
    return card


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout: identity, rules, frozen files, policies, budget, schedule."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != CARD_ID or screen.get("id") != STUDY_ID:
        return ["not the Sprint 27 probe card"]
    if screen.get("rules") != RULES or screen.get("rules_sha256") != rules_digest():
        problems.append("the card's rules are not the frozen rules")
    if screen.get("structural_stops") != list(STRUCTURAL_STOPS) or screen.get("stages") != STAGES:
        problems.append("the card's structural stops or stages are not the frozen ones")
    current = frozen_digests(repo)
    pinned = screen.get("frozen_files") or {}
    changed = sorted(rel for rel, digest in pinned.items() if current.get(rel) != digest)
    if changed or sorted(pinned) != sorted(FROZEN_FILES):
        problems.append(f"frozen implementation files differ from the card: {changed}")
    policies = card.get("policies") or {}
    if (sorted(policies) != sorted((V2_ID, CANDIDATE_ID))
            or policies[CANDIDATE_ID].get("policy_source", {}).get("sha256") != CANDIDATE_DIGEST
            or policies[V2_ID].get("policy_source", {}).get("sha256") != V2_DIGEST):
        problems.append("policy identities are not the registered ones")
    if card.get("candidate") != CANDIDATE_ID:
        problems.append("the card's candidate is not the Sprint 27 candidate")
    budget = card.get("budget") or {}
    if (budget.get("ledger_base_session"), budget.get("sprint_session_cap"), budget.get("batch_sessions")) != (
            LEDGER_BASE_SESSION, SESSION_CEILING, len(SCHEDULE)):
        problems.append("budget is not the registered ceiling")
    planned = [(g.get("game_id"), g.get("scenario_id"), g.get("condition"), g.get("red"), g.get("blue"))
               for g in card.get("games") or ()]
    if planned != [(g["game_id"], g["scenario_id"], g["condition"], g["red"], g["blue"]) for g in games()]:
        problems.append("the games are not the registered schedule")
    return problems


# ------------------------------------------------------------------------------------------------
# Ledger (S1, S2)


def ledger_audit(ledger: Sequence[Mapping[str, Any]], card: Mapping[str, Any]) -> Dict[str, Any]:
    """Every session opened after 2796 must be the card's game in schedule position (session 2796 + n plays position
    n) under the card's digest and the candidate's registered digest, opened once and closed with integrity ok, the
    state chain continuous, at most two sessions (2797, 2798) and none unclosed."""
    order = [g["game_id"] for g in card["games"]]
    digest = mf.digest(card)
    problems: Dict[str, List[str]] = {"S1": [], "S2": []}
    opened: Dict[Any, str] = {}
    ended: Dict[Any, Mapping[str, Any]] = {}
    seen: Dict[str, Any] = {}
    previous = None
    for record in ledger:
        session = record.get("session")
        later = session is not None and int(session) > LEDGER_BASE_SESSION
        if later and record.get("event") == "session-open":
            harness = record.get("harness") or {}
            game = harness.get("game_id")
            position = int(session) - LEDGER_BASE_SESSION
            if game not in order:
                problems["S2"].append(f"session {session} plays a game outside the card")
            elif position > len(order) or order[position - 1] != game:
                problems["S2"].append(f"session {session} is not the card's game in schedule position {position}")
            if harness.get("card") != CARD_ID or harness.get("manifest_sha256") != digest:
                problems["S2"].append(f"session {session} is not under the Sprint 27 card")
            if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:
                problems["S2"].append(f"session {session} did not play the registered candidate digest")
            if game in seen:
                problems["S2"].append(f"game opened twice (sessions {seen[game]} and {session})")
            seen[game] = session
            opened[session] = game
            if previous is not None and record.get("state") != previous.get("state"):
                problems["S1"].append(f"session {session} opened with a state other than the previous record's")
        elif later and record.get("event") in ("session-close", "session-recovered"):
            if session in ended:
                problems["S2"].append(f"session {session} ended twice")
            ended[session] = record
            if record.get("event") == "session-recovered":
                problems["S2"].append(f"session {session} was recovered")
            elif not (record.get("integrity") or {}).get("ok"):
                problems["S1"].append(f"session {session} closed with an integrity failure")
        previous = record
    unclosed = sorted(set(opened) - set(ended))
    if unclosed:
        problems["S2"].append(f"unclosed sessions {unclosed}")
    if len(opened) > SESSION_CEILING:
        problems["S2"].append(f"{len(opened)} sessions exceed the ceiling of {SESSION_CEILING}")
    if sorted(int(s) for s in opened) != list(EXPECTED_SESSIONS[:len(opened)]):
        problems["S2"].append(f"sessions {sorted(opened)} are not the expected {list(EXPECTED_SESSIONS)} in order")
    return {"sessions": len(opened), "games": dict(sorted(seen.items())), "unclosed": unclosed, "problems": problems,
            "ok": not any(problems.values())}


def stage_ledger_problem(audit: Mapping[str, Any], stage: str, card: Mapping[str, Any]) -> Optional[str]:
    """Before a stage's game: stage A needs no session after 2796; stage B needs exactly session 2797, the card's first
    game, and nothing else."""
    if not audit["ok"]:
        return f"the ledger audit fails: {audit['problems']}"
    order = [g["game_id"] for g in card["games"]]
    if stage == "A" and audit["sessions"] != 0:
        return f"{audit['sessions']} sessions already opened after {LEDGER_BASE_SESSION}; stage A needs none"
    if stage == "B" and (audit["sessions"] != 1 or list(audit["games"]) != [order[0]]):
        return "stage B needs exactly session 2797 (the card's first game) after 2796"
    if stage not in STAGES:
        return f"unknown stage {stage}"
    return None


def structural_stops(stops: Mapping[str, Sequence[str]]) -> List[str]:
    return [code for code in STRUCTURAL_STOPS if stops.get(code)]


# ------------------------------------------------------------------------------------------------
# Per-game structural checks (S1, S4, S6, S7)


def game_stops(entry: Mapping[str, Any], record: Mapping[str, Any], t9cap: Mapping[str, Any],
               explore: Mapping[str, Any], timeline: Mapping[str, Any], max_step: Any,
               capture_digests: Mapping[str, Tuple[Optional[str], Optional[str]]]) -> Dict[str, List[str]]:
    stops: Dict[str, List[str]] = {code: [] for code in ("S1", "S4", "S6", "S7")}
    if not ((record.get("session_close") or {}).get("integrity") or {}).get("ok", False):
        stops["S1"].append("the session did not close with integrity ok")
    if record.get("status") != "COMPLETED":
        stops["S4"].append(f"status {record.get('status')}")
    seats = record.get("seats") or []
    for s in seats:
        if s.get("contract_errors"):
            stops["S4"].append(f"{s['contract_errors']} contract errors in the {s.get('policy')} seat")
        if s.get("replay_mismatches"):
            stops["S6"].append(f"{s['replay_mismatches']} replay mismatches in the {s.get('policy')} seat")
    side = candidate_side(entry)
    faction = 0 if side == "red" else 1
    other = "blue" if side == "red" else "red"
    by_faction = {s.get("faction"): s.get("policy") for s in seats}
    if by_faction != {faction: CANDIDATE_ID, 1 - faction: V2_ID}:
        stops["S7"].append(f"the record's seats {sorted(by_faction.items())} are not the card's")
    if (record.get("scenario_id"), record.get("condition")) != (entry.get("scenario_id"), entry.get("condition")):
        stops["S7"].append("the record's scenario or condition is not the card's")
    harness = record.get("harness") or {}
    if harness.get("game_id") != entry.get("game_id") or harness.get("card") != CARD_ID:
        stops["S7"].append("the record is not this card's game")
    if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:
        stops["S7"].append("the record's candidate digest is not the registered one")
    if (harness.get("policy_sources") or {}).get(V2_ID) != V2_DIGEST:
        stops["S7"].append("the opponent's policy source is not frozen baseline-v2")
    scores = record.get("final_scores") or {}
    if scores and scores.get(f"{side}_win") != scores.get(f"{side}_total", 0) - scores.get(f"{other}_total", 0):
        stops["S4"].append("the margin is not the engine's <side>_win")
    if record.get("observer_errors"):
        stops["S7"].append(f"{len(record['observer_errors'])} observer errors")
    for name, (recorded, actual) in dict(capture_digests).items():
        if recorded is None or recorded != actual:
            stops["S7"].append(f"capture {name} missing or not the recorded digest")
    if timeline.get("consistency_errors"):
        stops["S7"].append(f"{len(timeline['consistency_errors'])} decisions differ from the seat-local reconstruction")
    if timeline.get("unregistered_differences"):
        stops["S7"].append(f"{len(timeline['unregistered_differences'])} decisions differ from baseline-v2 by an "
                           "edit that is not a registered withholding")
    steps = timeline.get("steps") or []
    if len(steps) != record.get("steps") or t9cap.get("steps") != record.get("steps") \
            or explore.get("steps") != record.get("steps"):
        stops["S7"].append("the captures and the record disagree on the number of steps")
    if timeline.get("reconstructed_decisions") != 2 * len(steps):
        stops["S7"].append("not every decision of both seats was reconstructed")
    candidate = next((s for s in seats if s.get("policy") == CANDIDATE_ID), {})
    seat_facts = (t9cap.get("seats") or {}).get(str(faction)) or {}
    if (seat_facts.get("moves") or {}).get("emitted") != int((candidate.get("actions_by_type") or {}).get("1", 0)):
        stops["S7"].append("the T9 capture and the record disagree on the candidate seat's move orders")
    if explore.get("addon_errors"):
        stops["S7"].append(f"{len(explore['addon_errors'])} candidate add-on errors")
    if max_step != RULES["max_step"]:
        stops["S7"].append(f"max_step {max_step} is not the registered {RULES['max_step']}")
    return {code: found for code, found in stops.items() if found}


# ------------------------------------------------------------------------------------------------
# The registered-difference check (live and offline)


def canonical(action: Mapping[str, Any]) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True, separators=(",", ":"), default=repr)


def unregistered_differences(baseline: Sequence[Mapping[str, Any]], live: Sequence[Mapping[str, Any]],
                             withheld: Sequence[int]) -> List[str]:
    """Differences between ``baseline-v2``'s reconstructed actions and the live candidate actions at one decision that
    are not the rule's registered withholding: the live list must be baseline-v2's with exactly the rule's withheld
    indices removed and the rest in order, and every withheld action must be a MOVE."""
    problems: List[str] = []
    base = [canonical(a) for a in baseline]
    out = [canonical(a) for a in live]
    drop = set(withheld)
    if any(i < 0 or i >= len(base) for i in drop):
        problems.append("a withheld index lies outside baseline-v2's list")
        return problems
    if any(dict(baseline[i]).get("type") != MOVE for i in drop):
        problems.append("a withheld action is not a MOVE")
    if out != [a for i, a in enumerate(base) if i not in drop]:
        problems.append("the live actions are not baseline-v2's with exactly the withheld MOVEs removed, in order")
    return problems


#: Offline fidelity counts that must all be zero (SF).
FIDELITY_ZERO = ("candidate_offline_differences", "candidate_memory_chain_differences",
                 "candidate_unregistered_differences", "opponent_offline_differences",
                 "opponent_memory_chain_differences", "independent_check_unexplained")


def fidelity_problems(fidelity: Mapping[str, Any]) -> List[str]:
    """SF from the offline re-derivation of one game: a snapshot per decision; zero offline, memory-chain,
    unregistered, opponent and independent-check differences; every decision equal to Sprint 26's frozen rule replayed on
    the trajectory, with equal rule events; the candidate equal to baseline-v2 before the first withholding."""
    problems = []
    if not fidelity.get("one_snapshot_per_decision"):
        problems.append("the timeline does not hold one snapshot per decision")
    for key in FIDELITY_ZERO:
        if fidelity.get(key) != 0:
            problems.append(f"{key.replace('_', ' ')}: {fidelity.get(key)}")
    if fidelity.get("frozen_rule_equal_decisions") != fidelity.get("decisions") or not fidelity.get("decisions"):
        problems.append("a decision differs from Sprint 26's frozen rule replayed on the trajectory")
    if fidelity.get("frozen_rule_events_equal") is not True:
        problems.append("the rule events differ from the frozen rule's")
    if fidelity.get("candidate_equals_baseline_v2_before_the_first_withholding") is not True:
        problems.append("the candidate differs from baseline-v2 before the first withholding")
    return problems


# ------------------------------------------------------------------------------------------------
# P1 and P2


def frac(value: Fraction) -> Any:
    """An exact value for a public file: an integer, or the string ``numerator/denominator``."""
    return f"{value.numerator}/{value.denominator}" if value.denominator != 1 else value.numerator


def p1(candidate_e4: int, references: Mapping[str, int]) -> Dict[str, Any]:
    """P1 in exact arithmetic: triggered when candidate E4 > (mean of the two references) / 2; equality passes."""
    if len(references) != 2 or any(not isinstance(v, int) or isinstance(v, bool) for v in references.values()):
        raise ValueError("P1 needs exactly two integer same-colour references")
    total = sum(references.values())
    mean = Fraction(total, len(references))
    half = mean / 2
    triggered = Fraction(candidate_e4) > half
    return {"candidate_e4": candidate_e4, "references": dict(sorted(references.items())), "reference_sum": total,
            "reference_mean": frac(mean), "half_reference_mean": frac(half), "triggered": triggered,
            "candidate_over_reference_mean": round(float(Fraction(candidate_e4) / mean), 4) if mean else None,
            "absolute_change_from_reference_mean": frac(Fraction(candidate_e4) - mean)}


def p2(candidate_first: Mapping[str, Optional[int]],
       references: Mapping[str, Mapping[str, Optional[int]]]) -> Dict[str, Any]:
    """P2 by objective under the owner-approved same-colour reading (``RULES['p2']['rule']``)."""
    if sorted(candidate_first) != sorted(references):
        raise ValueError("the candidate's objectives are not the referenced objectives")
    rows = []
    for label in sorted(references):
        refs = dict(references[label])
        finite = [s for s in refs.values() if s is not None]
        c = candidate_first[label]
        row: Dict[str, Any] = {"objective": label, "candidate_first_ownership_step": c,
                               "reference_steps": dict(sorted(refs.items())),
                               "differences_from_each_reference": {k: (c - s) if c is not None and s is not None else None
                                                                   for k, s in sorted(refs.items())}}
        if not finite:
            row.update(reference_step=None, status="no historical timing reference", triggered=False)
        else:
            ref = max(finite)
            triggered = c is None or c > ref
            row.update(reference_step=ref, triggered=triggered,
                       status="never first-owned" if c is None else ("later than the reference" if triggered
                                                                     else "at or before the reference"))
        rows.append(row)
    return {"rows": rows, "triggered": any(r["triggered"] for r in rows),
            "objectives_without_reference": [r["objective"] for r in rows if r["reference_step"] is None]}


def p2_sensitivity(candidate_first: Mapping[str, Optional[int]],
                   all_four: Mapping[str, Mapping[str, Optional[int]]]) -> Dict[str, Any]:
    """Sprint 24's four-game mixed-colour reading (reported only): later than the latest finite step among the four
    HH baseline-v2 seats, or never where one of them owned it."""
    out = p2(candidate_first, all_four)
    out["note"] = "sensitivity only, not a stop; mixes seat colours whose distances to each objective differ"
    return out


# ------------------------------------------------------------------------------------------------
# Mechanism facts on the live trajectory (pure functions over Sprint 18 frames)


def accepted(feedback: Sequence[Mapping[str, Any]], action: Mapping[str, Any]) -> Optional[bool]:
    """True when exactly one echo of ``action`` (type, unit) carries no error, False when it carries an error, None
    when the echo is absent or ambiguous."""
    echoes = [f for f in feedback or () if isinstance(f.get("message"), Mapping)
              and all((f["message"]).get(k) == action.get(k) for k in ("type", "obj_id", "target_obj_id"))]
    if len(echoes) != 1:
        return None
    return not echoes[0].get("error")


def _hex(frame: Any, unit: Any) -> Optional[int]:
    return census.as_int((frame.own.get(unit) or {}).get("cur_hex"))


def departure(frames: Sequence[Any], unit: Any, origin: int, after: int) -> Tuple[Optional[int], Optional[str]]:
    """The first decision after ``after`` at which ``unit`` is absent from the own operators (``absent``) or observed on
    a readable hex other than ``origin`` (``moved``)."""
    for j in range(after + 1, len(frames)):
        if unit not in frames[j].own:
            return j, "absent"
        h = _hex(frames[j], unit)
        if h is not None and h != origin:
            return j, "moved"
    return None, None


def arrival(frames: Sequence[Any], unit: Any, hex_: Any, after: int) -> Optional[int]:
    for j in range(after + 1, len(frames)):
        if _hex(frames[j], unit) == hex_:
            return j
    return None


def in_envelope(unit: Mapping[str, Any], enemies: Iterable[Mapping[str, Any]]) -> bool:
    """Sprint 26's applicable-envelope test (``s26_t6s.in_envelope``)."""
    h = census.as_int(unit.get("cur_hex"))
    if h is None:
        return False
    for e in enemies:
        reach = weapon_range(e.get("carry_weapon_ids") or (), unit.get("type"))
        if reach is not None and census.as_int(e.get("cur_hex")) is not None and hex_distance(e["cur_hex"], h) <= reach:
            return True
    return False


def first_ownership(frames: Sequence[Any], faction: int, coord: Any) -> Optional[int]:
    """Sprint 26's first ownership (``s26_t6s.first_ownership``): the decision of the side's first play-stage frame whose
    flag for ``coord`` reads the side's colour."""
    for f in frames:
        if f.stage == 2 and f.flags.get(coord) == faction:
            return f.k
    return None


def member_state(frames: Sequence[Any], k: int, unit: Any, origin: int, pending: bool) -> str:
    """The state of an episode member at decision ``k``: waiting on the start hex (pending and on it), moving stacked,
    moving alone, stationary, or absent."""
    frame = frames[min(k, len(frames) - 1)]
    u = frame.own.get(unit)
    if u is None:
        return "absent"
    if pending and census.as_int(u.get("cur_hex")) == origin:
        return "waiting on the start hex"
    if census.moving(u):
        return "moving stacked" if u.get("stack") else "moving alone"
    return "stationary"


def episode_facts(frames: Sequence[Any], row: Mapping[str, Any], emitted: Sequence[Sequence[Mapping[str, Any]]],
                  feedback: Sequence[Sequence[Mapping[str, Any]]], hits: Mapping[Any, Sequence[Tuple[int, int]]],
                  lost: Mapping[Any, int], names: Mapping[Any, str], faction: int,
                  window: int = RULES["follow_up_window_steps"]) -> Dict[str, Any]:
    """The live facts of one episode (``row``: an episode row of Sprint 26's ``run_shadow`` on the live trajectory).
    Private fields (unit ids, hexes) are confined to the ``private`` block."""
    k0, s0, origin = row["start_k"], row["start_step"], row["origin"]
    chain = list(row["chain"])
    leader, followers = chain[0], chain[1:]
    n = len(frames)
    start = frames[k0]
    out: Dict[str, Any] = {"start_step": s0, "group_size": len(chain),
                           "classes": [census.unit_class(start.own[u]) for u in chain],
                           "hex_times": list(row["hex_times"]), "repeats": row["repeats"], "end": row["end"],
                           "end_steps_after_start": (row["end_step"] - s0) if row["end_step"] is not None else None,
                           "completed": row["end"] == "complete", "private": {"leader": leader, "origin": origin}}
    leader_move = [a for a in emitted[k0] if a.get("type") == MOVE and a.get("obj_id") == leader]
    out["leader_move_emitted"] = len(leader_move) == 1
    out["leader_move_accepted"] = accepted(feedback[k0], leader_move[0]) if len(leader_move) == 1 else None
    out["followers_withheld_at_start"] = sum(1 for u in followers
                                             if not any(a.get("type") == MOVE and a.get("obj_id") == u
                                                        for a in emitted[k0]))
    l_k, l_kind = departure(frames, leader, origin, k0)
    out["leader_departure_steps"] = (frames[l_k].cur_step - s0) if l_kind == "moved" else None
    out["leader_absent_before_departure"] = l_kind == "absent"
    pending_until: Dict[Any, Optional[int]] = {}
    rows_f = []
    for i, u in enumerate(followers, start=1):
        rel, q = row["releases"].get(u), row["queue"].get(u)
        f: Dict[str, Any] = {"position": i, "class": census.unit_class(start.own[u]),
                             "projected_wait": sum(row["hex_times"][:i])}
        if rel is not None:
            f.update(outcome="released", release_reason=rel["reason"], wait_steps=rel["step"] - s0,
                     moved_at_release=bool(rel["moved"]))
            moves = [a for a in emitted[rel["k"]] if a.get("type") == MOVE and a.get("obj_id") == u]
            f["release_move_accepted"] = accepted(feedback[rel["k"]], moves[0]) if len(moves) == 1 else None
            pending_until[u] = rel["k"]
        elif q is not None:
            f.update(outcome=f"left the queue, {q['reason']}", wait_steps=q["step"] - s0, moved_at_release=None,
                     release_move_accepted=None)
            pending_until[u] = q["k"]
        else:
            f.update(outcome="pending at the end", wait_steps=None, moved_at_release=None, release_move_accepted=None)
            pending_until[u] = None
        d_k, d_kind = departure(frames, u, origin, k0)
        f["departed"] = d_kind == "moved"
        f["departure_steps"] = (frames[d_k].cur_step - s0) if d_kind == "moved" else None
        f["departed_after_release"] = bool(d_kind == "moved" and rel is not None and d_k > rel["k"])
        f["destroyed_before_departure"] = d_kind == "absent" and u in lost
        lp = _hex(frames[d_k], leader) if d_kind == "moved" else None
        fp = _hex(frames[d_k], u) if d_kind == "moved" else None
        f["separation_from_leader_at_departure_hexes"] = hex_distance(lp, fp) if lp is not None and fp is not None \
            else None
        f["damage_events_while_waiting_on_the_start_hex"] = sum(
            1 for k, s in hits.get(u, ()) if s >= s0 and k >= k0
            and (pending_until[u] is None or k <= pending_until[u])
            and member_state(frames, k, u, origin, True) == "waiting on the start hex")
        dest = row["members"][u].route[-1]
        f["destination"] = names.get(dest) if dest in names else None
        first_k = first_ownership(frames, faction, dest) if dest in names else None
        after = first_k is not None and first_k > k0
        f["destination_first_owned_after_start"] = after
        f["destination_first_owned_before_start"] = first_k is not None and not after
        if after:
            standing = [o for o, x in frames[first_k].own.items() if x.get("type") in census.GROUND
                        and x.get("cur_hex") == dest]
            f["steps_start_to_destination_first_ownership"] = frames[first_k].cur_step - s0
            f["follower_among_first_owners"] = u in standing
            f["leader_among_first_owners"] = leader in standing
            f["other_own_units_among_first_owners"] = any(o not in chain for o in standing)
        else:
            f.update(steps_start_to_destination_first_ownership=None, follower_among_first_owners=None,
                     leader_among_first_owners=None, other_own_units_among_first_owners=None)
        a_k = arrival(frames, u, dest, k0)
        f["follower_arrival_steps"] = (frames[a_k].cur_step - s0) if a_k is not None else None
        leader_dest = row["members"][leader].route[-1]
        la_k = arrival(frames, leader, leader_dest, k0)
        f["same_destination_as_leader"] = dest == leader_dest
        f["arrival_lag_behind_leader_steps"] = (frames[a_k].cur_step - frames[la_k].cur_step) \
            if a_k is not None and la_k is not None and dest == leader_dest else None
        f["follower_lost_later"] = u in lost and lost[u] > k0
        rows_f.append(f)
    out["followers"] = rows_f
    out["followers_released"] = sum(1 for f in rows_f if f["outcome"] == "released")
    out["followers_released_reference_left"] = sum(1 for f in rows_f if f.get("release_reason") == "reference_left")
    out["followers_released_timeout"] = sum(1 for f in rows_f if f.get("release_reason") == "timeout")
    out["executed"] = out["completed"] and any(f.get("release_reason") == "reference_left" and f["departed_after_release"]
                                               for f in rows_f)
    together, shared_hexes, first_reunion, stacked_inside = 0, set(), None, 0
    damage = collections.Counter()
    for j in range(k0 + 1, n):
        g = frames[j]
        if g.cur_step - s0 > window:
            break
        states = [(u, g.own[u]) for u in chain if u in g.own and census.moving(g.own[u])]
        here = collections.Counter(s.get("cur_hex") for _, s in states)
        shared = {h for h, c in here.items() if c >= 2 and h != origin and h is not None}
        if shared:
            together += 1
            shared_hexes |= shared
            first_reunion = first_reunion if first_reunion is not None else g.cur_step - s0
        stacked_inside += sum(1 for _, s in states if s.get("stack") and in_envelope(s, g.enemies.values()))
    for u in chain:
        for k, s in hits.get(u, ()):
            if s0 <= s <= s0 + window and k >= k0:
                pend = u in pending_until and (pending_until[u] is None or k <= pending_until[u])
                damage[member_state(frames, k, u, origin, pend)] += 1
    out.update(co_located_moving_beyond_start=bool(shared_hexes), co_located_moving_hexes_beyond_start=len(shared_hexes),
               co_located_moving_decisions=together, first_co_location_beyond_start_steps=first_reunion,
               stacked_moving_inside_envelope_member_unit_decisions=stacked_inside,
               member_damage_events_by_state=dict(sorted(damage.items())))
    return out


def mechanism_observed(episodes: Sequence[Mapping[str, Any]]) -> bool:
    """The registered rule: at least one executed episode (``RULES['mechanism']``)."""
    return any(e["executed"] for e in episodes)


def stage_gate(stops: Sequence[str], completed: bool, p1_result: Mapping[str, Any], p2_result: Mapping[str, Any],
               observed: bool) -> Dict[str, Any]:
    """Stage B is authorized only after a completed session 2797 with no structural stop, P1 and P2 not triggered and
    the mechanism observed (``RULES['stage_gate']``)."""
    reasons = []
    if stops:
        reasons.append(f"structural stops {list(stops)}")
    if not completed:
        reasons.append("the game did not complete")
    if p1_result.get("triggered"):
        reasons.append("P1 exposure stop triggered")
    if p2_result.get("triggered"):
        reasons.append("P2 onward-capture stop triggered")
    if not observed:
        reasons.append("mechanism not observed")
    return {"stage_b_authorized": not reasons, "reasons": reasons}


def disposition(sessions: Sequence[Mapping[str, Any]], stage_b_authorized: bool, stage_b_opened: bool) -> Dict[str, Any]:
    """First match over the opened sessions (each: ``structural_stops``, ``completed``, ``mechanism_observed``,
    ``p1_triggered``, ``p2_triggered``): INVALID (a structural or fidelity stop, an incomplete game, no session, or a
    stage B that was authorized and not run); MECHANISM_NOT_OBSERVED (a session without the mechanism);
    MECHANISM_NOT_SUPPORTED (P1 or P2 triggered in a session); MECHANISM_SUPPORTED (both sessions ran, each observed
    the mechanism and passed P1 and P2)."""
    count = len(sessions)
    early = count == 1
    base = {"sessions_opened": count, "paired_probe_terminated_early": early, "order": list(DISPOSITIONS)}
    problems = [f"session {i + 1}: {s['structural_stops']}" for i, s in enumerate(sessions) if s["structural_stops"]]
    problems += [f"session {i + 1}: incomplete" for i, s in enumerate(sessions) if not s["completed"]]
    if count == 0 or count > SESSION_CEILING:
        problems.append(f"{count} sessions")
    if stage_b_authorized and not stage_b_opened:
        problems.append("stage B was authorized but not run")
    if early and stage_b_opened:
        problems.append("stage B opened without a recorded game")
    if problems:
        return {**base, "disposition": INVALID, "problems": problems}
    if any(not s["mechanism_observed"] for s in sessions):
        return {**base, "disposition": NOT_OBSERVED}
    if any(s["p1_triggered"] or s["p2_triggered"] for s in sessions):
        return {**base, "disposition": NOT_SUPPORTED}
    if count != SESSION_CEILING:
        return {**base, "disposition": INVALID, "problems": ["the paired probe is incomplete"]}
    return {**base, "disposition": SUPPORTED}


# ------------------------------------------------------------------------------------------------
# Public sanitization


def public_check(value: Any, private_values: Iterable[Any] = ()) -> List[str]:
    """Forbidden keys at any depth and any private value (unit ids, hexes) as a number, key or word."""
    return sc.privacy_problems(value, private_values)


def mask_numbers(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {k: mask_numbers(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [mask_numbers(v) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return None
    return node


def digit_words(data: Any, allowed: Iterable[str] = ()) -> List[str]:
    """Every word made only of digits in a key or string of ``data`` except the ``allowed`` ones."""
    keep = set(allowed)
    out: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for k, v in node.items():
                out.extend(w for w in str(k).split() if w.isdigit() and w not in keep)
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            out.extend(w for w in node.split() if w.isdigit() and w not in keep)

    walk(data)
    return out


def public_problems(data: Any, private_values: Iterable[Any], scenarios: Iterable[str] = (SCENARIO,)) -> List[str]:
    """Forbidden keys; private values as keys or words (numeric leaves masked: aggregates, steps and distances by
    construction); words made only of digits other than the named scenario identifiers (by default the probe's)."""
    values = sorted({str(v) for v in private_values})
    return (sc.privacy_problems(data) + sc.privacy_problems(mask_numbers(data), values)
            + [f"digit word {w!r}" for w in digit_words(data, tuple(scenarios))])


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
