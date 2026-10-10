"""The registered Sprint 31 T13-K2 exploratory pilot (``docs/SPRINT31_T13_K2_PILOT.md``, section 6): every rule.

At most four exclusive engine sessions, 2798 to 2801, of the exploratory candidate ``t13-keep-one-k2`` in the owner's
fixed order (:data:`SCHEDULE`), each opened only when every earlier game passed its registered gate. Exploratory: a
directional screen, not a confirmation; nothing is promoted or uploaded.

This module fixes, before session 2798: the identities, the card and its pins, the session budget and the ledger audit,
the per-game structural stops, the mechanism facts read from the full-step capture and the mechanism failures, the harm
stops and their thresholds (read from Sprint 30's committed controls), the objective and score facts, the per-game gate,
the dispositions and the public sanitization. Nothing here reads an engine, a capture or the ledger by itself; callers
pass the data in.
"""

from __future__ import annotations

import collections
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..decision import INERT_ID
from ..experiments import t13_keep_one_k2 as cand
from . import exploratory as xp
from . import manifest as mf
from . import s12_screen as sc
from . import s27_probe as sp
from .s12_timeline import labels

STUDY_ID = "s31-t13-k2"
CARD_ID = "s31-t13-k2-pilot-1"
SCHEMA = "miaosuan-s31-pilot/1"
CANDIDATE_ID = cand.CANDIDATE_ID
V2_ID, V2_DIGEST = sc.V2_ID, sc.V2_DIGEST
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2797
SESSION_CEILING = 4
EXPECTED_SESSIONS = (2798, 2799, 2800, 2801)
WORKERS = 1
MOVE = 1
GROUND = (1, 2)
PLAY_STAGE = 2
#: (position, scenario, condition, red, blue): the owner's order. C3 = inert red against the candidate blue; C2 = the
#: candidate red against inert blue; H1 = the candidate red against baseline-v2 blue; H2 = baseline-v2 red against the
#: candidate blue. Position n opens session 2797 + n.
SCHEDULE: Tuple[Tuple[int, str, str, str, str], ...] = (
    (1, "2120531121", "C3", INERT_ID, CANDIDATE_ID),
    (2, "1930331196", "C2", CANDIDATE_ID, INERT_ID),
    (3, "2130511121", "H1", CANDIDATE_ID, V2_ID),
    (4, "2130511121", "H2", V2_ID, CANDIDATE_ID))
#: The candidate's policy source (baseline-v2's 22 files, the add-on wrapper, the free-flow relation, the candidate).
CANDIDATE_DIGEST = "8544257fa894c25ba4b97c2abf641f59cf20e2bea79109dddc12e94ee448f3d7"
CONTROLS = "evaluation/s30-t13-k1/controls.json"
CONTROLS_SHA256 = "27dffdfdfa2f920a921cb68da389bed80bb7a6e01950de7ffaac54b34c186e93"
PREFLIGHT = "evaluation/s31-t13-k2/preflight.json"
PREFLIGHT_SHA256 = "59a38cead7f56c683e08009424c9a9fc1af94093c574061d0eae0490c1f861f1"

# ------------------------------------------------------------------------------------------------
# Rules (frozen before session 2798)

RULES: Dict[str, Any] = {
    "max_step": 2880,
    "controls": f"{CONTROLS} (Sprint 30, SHA-256 {CONTROLS_SHA256}): baseline-v2's group C games of the registered "
                "shoot-reservation experiment, fifteen per configuration and seat; margin = own total minus the "
                "opponent's total, equal to the engine's margin field",
    "inert_harm": {
        "rule": "REJECT when the candidate's occupy score is below the configuration's baseline-v2 occupy score "
                "(constant over its fifteen games), or its margin is below the baseline-v2 margin minimum minus 50; "
                "the boundaries themselves pass",
        "positions": {"1": {"configuration": "2120531121 C3 baseline-v2 blue", "occupy": 310, "margin_minimum": 559,
                            "margin_floor": 509},
                      "2": {"configuration": "1930331196 C2 baseline-v2 red", "occupy": 310, "margin_minimum": 258,
                            "margin_floor": 208}}},
    "head_to_head_harm": {
        "rule": "REJECT when the candidate's margin is below the minimum of the fifteen same-seat baseline-v2 mirror "
                "games (worse than every one of them), or its occupy score at the end is below their minimum, or an "
                "opening objective is never first-owned by the candidate's colour; the boundaries themselves pass",
        "opening_objectives": "the objectives that both same-colour Sprint 12 head-to-head baseline-v2 seats first-owned "
                              "at the same step (Sprint 27's registered references, evaluation/s27_probe.RULES p2): an "
                              "opponent-independent opening capture",
        "positions": {"3": {"seat": "red", "margin_minimum": -1055, "occupy_minimum": 0, "occupy_maximum": 50,
                            "margin_mean": "-13049/15",
                            "opening_objectives": ["50-point objective A", "50-point objective B",
                                                   "50-point objective D", "80-point objective B"]},
                      "4": {"seat": "blue", "margin_minimum": 719, "occupy_minimum": 390, "occupy_maximum": 440,
                            "margin_mean": "13049/15",
                            "opening_objectives": ["50-point objective A", "50-point objective B",
                                                   "50-point objective C", "50-point objective D",
                                                   "80-point objective A", "80-point objective B",
                                                   "80-point objective C"]}}},
    "mechanism": {
        "withholding": "a decision at which the candidate's list is baseline-v2's with the selected holder's MOVE removed",
        "retained": "a withholding after which, at the candidate's next decision, the holder is an own operator standing "
                    "on the same centre with an empty move path",
        "executed_episode": "a garrison episode with at least one retained withholding",
        "M1_departure_without_release": "after a withholding the holder is an own operator at the next decision but "
                                        "off the centre or with a non-empty move path, although the candidate emitted "
                                        "no MOVE for it",
        "M2_no_executed_episode": "a game that completes without an executed garrison episode (the preflight verified "
                                  "an opportunity in all four configurations)",
        "M3_persistent_interference": "own ground units waiting (non-empty move path, speed not positive) whose next "
                                      "hex is a centre with an active holder and four own ground units, during a run "
                                      "of consecutive steps of at least 300 (the registered hold limit of Sprint 25's "
                                      "garrison rule); shorter runs are reported",
        "interference_limit_steps": 300},
    "gate": "the next session opens only when every opened game completed with no structural stop, no mechanism failure "
            "and no harm stop",
    "promising": "all four games completed with no stop, an executed garrison episode in both head-to-head games, the "
                 "candidate red's occupy at the end above the red mirror maximum (50) and its margin at or above the "
                 "red mirror mean (-13049/15)",
}
STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7")
STOP_MEANING = {
    "S1": "engine-installation integrity failure (session close or the ledger's state chain)",
    "S2": "ledger inconsistency, a wrong card, game or digest, an unclosed session, a session out of order or beyond 2801",
    "S3": "privacy or repository exposure: a file outside the ignored tree appeared, or a tracked file changed",
    "S4": "a contract error, a wrong margin identity or a game that did not complete",
    "S6": "a replay mismatch",
    "S7": "capture or reconstruction failure: an observer error, a missing or digest-mismatched capture, a live decision "
          "or memory that differs from its seat-local reconstruction, a difference from baseline-v2 that is not the "
          "registered withholding, an independent-check finding, an add-on error, disagreeing counts, a wrong scenario, "
          "condition, seat or opponent, or a max_step other than 2,880",
}
MECHANISM_FAILURES = ("M1", "M2", "M3")
DISPOSITIONS = ("K2_PILOT_INVALID", "K2_PILOT_REJECT", "K2_PILOT_INCONCLUSIVE", "K2_PILOT_PROMISING")
INVALID, REJECT, INCONCLUSIVE, PROMISING = DISPOSITIONS

#: Files whose normalised SHA-256 the card pins.
FROZEN_FILES = (
    "src/miaosuan_agent/experiments/t13_keep_one_k2.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "src/miaosuan_agent/experiments/t9_batch.py",
    "src/miaosuan_agent/evaluation/s31_pilot.py",
    "src/miaosuan_agent/evaluation/s31_capture.py",
    "src/miaosuan_agent/evaluation/s31_preflight.py",
    "src/miaosuan_agent/evaluation/s30_preflight.py",
    "src/miaosuan_agent/evaluation/s27_probe.py",
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/game.py",
    "scripts/build_s31_card.py",
    "scripts/run_s31_game.py",
    "scripts/run_s31_pilot.py",
    "scripts/s31_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_s12_stage.py",
    "tests/test_t13_keep_one_k2.py",
    "tests/test_s31_pilot.py",
    "tests/fixtures/s31_engine.py",
)

TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED FOUR-GAME PILOT - NOT A CONFIRMATION - NOT ELIGIBLE FOR PROMOTION",
    "version": "t13-keep-one-k2, Sprint 31 arrival-transition garrison pilot (docs/SPRINT31_T13_K2_PILOT.md)",
    "mechanism": "baseline-v2 plays the seat on its own observation at every decision; when every own ground unit on "
                 "the centre of an objective the side holds departs and at least one by a new baseline-v2 MOVE, the "
                 "rule withholds the MOVE of one eligible holder (longest free-flow time, then lower id); K2 admits a "
                 "holder in the documented post-arrival stop transition",
    "controls": "historical and descriptive: Sprint 30's committed baseline-v2 controls (fifteen games per "
                "configuration and seat); no new control game",
    "configurations": "2120531121 C3 (candidate blue against the inert control), 1930331196 C2 (candidate red against "
                      "the inert control), then 2130511121 against frozen baseline-v2 with the candidate red, then blue",
    "safety_checks": ["structural stops after every game (S1, S2, S3, S4, S6, S7)",
                      "mechanism failures M1, M2, M3 and the harm stops, then the registered gate before every session",
                      "at most four sessions after closed session 2797, in schedule order, exclusive diagnostic sessions",
                      "every frozen implementation file pinned by digest; baseline-v2's policy source to 7cbaf032..."],
    "intended_observations": ["the exploratory capture and the Sprint 31 full-step timeline with the seat-local "
                              "reconstruction of every policy seat and the independent check at every decision"],
    "next_step_rule": "the registered gate after each game (s31_pilot.gate); after the last game the disposition",
}


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
    others = [side for side in ("red", "blue") if entry.get(side) in (V2_ID, INERT_ID)]
    if len(sides) != 1 or len(others) != 1:
        raise ValueError("a game must seat the candidate against baseline-v2 or the inert control")
    return sides[0]


def opponent(entry: Mapping[str, Any]) -> str:
    return entry["blue"] if candidate_side(entry) == "red" else entry["red"]


def build_card(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, policies: Sequence[Mapping[str, Any]],
               frozen: Mapping[str, str]) -> Dict[str, Any]:
    by_id = {p["id"]: p for p in policies}
    if sorted(by_id) != sorted((V2_ID, CANDIDATE_ID)):
        raise ValueError("the card's policies are baseline-v2 and the Sprint 31 candidate only")
    if (by_id[CANDIDATE_ID]["policy_source"]["sha256"] != CANDIDATE_DIGEST
            or by_id[V2_ID]["policy_source"]["sha256"] != V2_DIGEST):
        raise ValueError("a policy source is not the registered one")
    if sorted(frozen) != sorted(FROZEN_FILES):
        raise ValueError("the frozen file set differs from FROZEN_FILES")
    rows = games()
    if len(rows) != SESSION_CEILING:
        raise ValueError("the schedule is not exactly the four registered games")
    budget = {"batch_sessions": len(rows), "ledger_base_session": LEDGER_BASE_SESSION,
              "sprint_session_cap": SESSION_CEILING}
    card = xp.build(CARD_ID, TEXTS, shoot_manifest, shoot_manifest_sha256, policies, CANDIDATE_ID, rows, RUNTIME,
                    WORKERS, budget)
    for row, game in zip(card["games"], rows):
        row["screen_position"] = game["screen_position"]
    card["screen"] = {"id": STUDY_ID, "stage": "pilot", "rules": RULES, "rules_sha256": rules_digest(),
                      "frozen_files": dict(sorted(frozen.items())), "expected_sessions": list(EXPECTED_SESSIONS),
                      "structural_stops": list(STRUCTURAL_STOPS), "mechanism_failures": list(MECHANISM_FAILURES),
                      "dispositions": list(DISPOSITIONS), "controls_sha256": CONTROLS_SHA256,
                      "preflight_sha256": PREFLIGHT_SHA256}
    return card


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout: identity, rules, frozen files, policies, budget, schedule,
    and the committed controls and preflight it rests on."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != CARD_ID or screen.get("id") != STUDY_ID:
        return ["not the Sprint 31 pilot card"]
    if screen.get("rules") != RULES or screen.get("rules_sha256") != rules_digest():
        problems.append("the card's rules are not the frozen rules")
    if (screen.get("structural_stops"), screen.get("mechanism_failures"), screen.get("dispositions")) != (
            list(STRUCTURAL_STOPS), list(MECHANISM_FAILURES), list(DISPOSITIONS)):
        problems.append("the card's stops or dispositions are not the frozen ones")
    current = frozen_digests(repo)
    pinned = screen.get("frozen_files") or {}
    changed = sorted(rel for rel, digest in pinned.items() if current.get(rel) != digest)
    if changed or sorted(pinned) != sorted(FROZEN_FILES):
        problems.append(f"frozen implementation files differ from the card: {changed}")
    for rel, digest, key in ((CONTROLS, CONTROLS_SHA256, "controls_sha256"), (PREFLIGHT, PREFLIGHT_SHA256,
                                                                                "preflight_sha256")):
        path = repo / rel
        if screen.get(key) != digest or not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"{rel} is not the pinned file")
    policies = card.get("policies") or {}
    if (sorted(policies) != sorted((V2_ID, CANDIDATE_ID))
            or policies[CANDIDATE_ID].get("policy_source", {}).get("sha256") != CANDIDATE_DIGEST
            or policies[V2_ID].get("policy_source", {}).get("sha256") != V2_DIGEST):
        problems.append("policy identities are not the registered ones")
    if card.get("candidate") != CANDIDATE_ID:
        problems.append("the card's candidate is not the Sprint 31 candidate")
    budget = card.get("budget") or {}
    if (budget.get("ledger_base_session"), budget.get("sprint_session_cap"), budget.get("batch_sessions")) != (
            LEDGER_BASE_SESSION, SESSION_CEILING, len(SCHEDULE)):
        problems.append("budget is not the registered ceiling")
    planned = [(g.get("game_id"), g.get("scenario_id"), g.get("condition"), g.get("red"), g.get("blue"),
                g.get("screen_position")) for g in card.get("games") or ()]
    if planned != [(g["game_id"], g["scenario_id"], g["condition"], g["red"], g["blue"], g["screen_position"])
                   for g in games()]:
        problems.append("the games are not the registered schedule")
    return problems


# ------------------------------------------------------------------------------------------------
# Ledger (S1, S2)


def ledger_audit(ledger: Sequence[Mapping[str, Any]], card: Mapping[str, Any]) -> Dict[str, Any]:
    """Every session opened after 2797 must be the card's game in schedule position (session 2797 + n plays position
    n) under the card's digest and the candidate's registered digest, opened once and closed with integrity ok, the
    state chain continuous, at most four sessions and none unclosed."""
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
                problems["S2"].append(f"session {session} is not under the Sprint 31 card")
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
    games_by_session = dict(sorted(seen.items(), key=lambda kv: int(kv[1])))  # in session order, never by id
    return {"sessions": len(opened), "games": games_by_session, "unclosed": unclosed, "problems": problems,
            "ok": not any(problems.values())}


def position_ledger_problem(audit: Mapping[str, Any], position: int, card: Mapping[str, Any]) -> Optional[str]:
    """Before the game at ``position``: exactly the card's first ``position - 1`` games opened after 2797, in order."""
    if position not in [g["screen_position"] for g in card["games"]]:
        return f"unknown position {position}"
    if not audit["ok"]:
        return f"the ledger audit fails: {audit['problems']}"
    order = [g["game_id"] for g in card["games"]]
    if audit["sessions"] != position - 1 or list(audit["games"]) != order[:position - 1]:
        return (f"{audit['sessions']} sessions opened after {LEDGER_BASE_SESSION}; position {position} needs exactly the "
                "card's earlier games")
    return None


def structural_stops(stops: Mapping[str, Sequence[str]]) -> List[str]:
    return [code for code in STRUCTURAL_STOPS if stops.get(code)]


# ------------------------------------------------------------------------------------------------
# Per-game structural checks (S1, S4, S6, S7)


def game_stops(entry: Mapping[str, Any], record: Mapping[str, Any], explore: Mapping[str, Any],
               timeline: Mapping[str, Any], max_step: Any,
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
    if by_faction != {faction: CANDIDATE_ID, 1 - faction: opponent(entry)}:
        stops["S7"].append(f"the record's seats {sorted(by_faction.items())} are not the card's")
    if (record.get("scenario_id"), record.get("condition")) != (entry.get("scenario_id"), entry.get("condition")):
        stops["S7"].append("the record's scenario or condition is not the card's")
    harness = record.get("harness") or {}
    if harness.get("game_id") != entry.get("game_id") or harness.get("card") != CARD_ID:
        stops["S7"].append("the record is not this card's game")
    if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:
        stops["S7"].append("the record's candidate digest is not the registered one")
    if opponent(entry) == V2_ID and (harness.get("policy_sources") or {}).get(V2_ID) != V2_DIGEST:
        stops["S7"].append("the opponent's policy source is not frozen baseline-v2")
    scores = record.get("final_scores") or {}
    if not scores or scores.get(f"{side}_win") != scores.get(f"{side}_total", 0) - scores.get(f"{other}_total", 0):
        stops["S4"].append("the margin is missing or not the engine's <side>_win")
    if record.get("observer_errors"):
        stops["S7"].append(f"{len(record['observer_errors'])} observer errors")
    for name, (recorded, actual) in dict(capture_digests).items():
        if recorded is None or recorded != actual:
            stops["S7"].append(f"capture {name} missing or not the recorded digest")
    for key, label in (("consistency_errors", "decisions differ from the seat-local reconstruction or memory chain"),
                       ("unregistered_differences", "decisions differ from baseline-v2 by an unregistered edit"),
                       ("independent_problems", "decisions with an independent-check finding")):
        if timeline.get(key):
            stops["S7"].append(f"{len(timeline[key])} {label}")
    steps = timeline.get("steps") or []
    if len(steps) != record.get("steps") or explore.get("steps") != record.get("steps"):
        stops["S7"].append("the captures and the record disagree on the number of steps")
    policy_seats = 2 if opponent(entry) == V2_ID else 1
    if timeline.get("reconstructed_decisions") != policy_seats * len(steps) or \
            timeline.get("policy_decisions") != policy_seats * len(steps):
        stops["S7"].append("not every decision of every policy seat was reconstructed")
    candidate = next((s for s in seats if s.get("policy") == CANDIDATE_ID), {})
    seat = candidate.get("seat")
    moves = sum(1 for step in steps for a in step.get("submitted") or () if a["seat"] == seat
                and a["action"].get("type") == MOVE)
    if moves != int((candidate.get("actions_by_type") or {}).get(str(MOVE), 0)):
        stops["S7"].append("the timeline and the record disagree on the candidate seat's move orders")
    if explore.get("addon_errors"):
        stops["S7"].append(f"{len(explore['addon_errors'])} candidate add-on errors")
    if max_step != RULES["max_step"]:
        stops["S7"].append(f"max_step {max_step} is not the registered {RULES['max_step']}")
    return {code: found for code, found in stops.items() if found}


# ------------------------------------------------------------------------------------------------
# Facts on the live trajectory (pure functions over the candidate seat's observations and the timeline rows)


def own_ground(raw: Mapping[str, Any], faction: int) -> Dict[int, Mapping[str, Any]]:
    return {u["obj_id"]: u for u in raw.get("operators") or ()
            if isinstance(u, Mapping) and u.get("color") == faction and u.get("type") in GROUND}


def flags(raw: Mapping[str, Any]) -> Dict[Any, Any]:
    return {c.get("coord"): c.get("flag") for c in raw.get("cities") or () if isinstance(c, Mapping)}


def settling(u: Mapping[str, Any]) -> bool:
    return bool(cand.settling(u))


def game_facts(entry: Mapping[str, Any], raws: Sequence[Mapping[str, Any]], final: Optional[Mapping[str, Any]],
               rows: Sequence[Mapping[str, Any]], emitted: Sequence[Sequence[Mapping[str, Any]]],
               feedback_errors: int, scores: Mapping[str, Any]) -> Dict[str, Any]:
    """The candidate seat's facts. ``raws``: its observation at each decision; ``final``: its observation after the
    last step; ``rows``: the timeline's reconstruction row at each decision (``withheld``, ``checks``,
    ``baseline_actions``); ``emitted``: the candidate's live actions at each decision. Unit ids and hexes appear only in
    the ``private`` block."""
    side = candidate_side(entry)
    faction = 0 if side == "red" else 1
    other = "blue" if side == "red" else "red"
    n = len(raws)
    if not (len(rows) == len(emitted) == n) or n == 0:
        raise ValueError("the decisions, rows and emitted lists do not align")
    values = {c.get("coord"): c.get("value") for c in raws[0].get("cities") or ()}
    names = labels(values)
    own = [own_ground(r, faction) for r in raws]
    fl = [flags(r) for r in raws]
    steps = [(r.get("time") or {}).get("cur_step") for r in raws]
    play = [(r.get("time") or {}).get("stage") == PLAY_STAGE for r in raws]
    moved = [{a.get("obj_id") for a in em if a.get("type") == MOVE} for em in emitted]
    withholdings = []
    for k, row in enumerate(rows):
        for c in row.get("checks") or ():
            centre, status, selected, index = c[0], c[1], c[2], c[3]
            if status == "withheld":
                action = row["baseline_actions"][index]
                withholdings.append({"k": k, "centre": centre, "unit": selected,
                                     "destination": (action.get("move_path") or [None])[-1],
                                     "settling": settling(own[k][selected])})
    # outcome of each withholding at the next decision
    outcome = collections.Counter()
    failures_m1 = []
    for w in withholdings:
        k, u, c = w["k"], w["unit"], w["centre"]
        if k + 1 >= n:
            w["next"] = "game_end"
        elif u not in own[k + 1]:
            w["next"] = "absent"
        elif own[k + 1][u].get("cur_hex") == c and not own[k + 1][u].get("move_path"):
            w["next"] = "retained"
        else:
            w["next"] = "departed_without_release"
            failures_m1.append({"k": k + 1, "step": steps[k + 1]})
        outcome[w["next"]] += 1
    # garrison episodes: from a withholding of a unit until it is no longer standing on that centre unordered
    episodes = []
    by_k = collections.defaultdict(list)
    for w in withholdings:
        by_k[w["k"]].append(w)
    active: Dict[int, Dict[str, Any]] = {}
    for k in range(n):
        # (a) each active episode against this decision's observation (the result of the decision before it)
        for u, e in list(active.items()):
            here = own[k].get(u)
            if here is None:
                e.update(end="holder_absent", end_k=k)
            elif u in moved[k - 1]:
                e.update(end="released", end_k=k - 1)
            elif here.get("cur_hex") != e["centre"] or here.get("move_path"):
                e.update(end="left_without_release", end_k=k)
            else:
                e["on_centre_decisions"] += 1
                if e["settling_at_start"] and here.get("stop") != 0 and not cand.positive(
                        here.get("move_to_stop_remain_time")):
                    e["transition_completed_on_centre"] = True
                if fl[k].get(e["centre"]) != faction:
                    e["objective_lost_with_holder"] += 1
                continue
            episodes.append(active.pop(u))
        # (b) withholdings at this decision start or continue an episode
        for w in by_k.get(k, ()):
            e = active.get(w["unit"])
            if e is not None and e["centre"] != w["centre"]:
                e.update(end="moved_to_another_centre", end_k=k)
                episodes.append(active.pop(w["unit"]))
                e = None
            if e is None:
                e = {"unit": w["unit"], "centre": w["centre"], "start_k": k, "start_step": steps[k],
                     "destination": w["destination"], "settling_at_start": w["settling"], "withholdings": 0,
                     "retained": 0, "on_centre_decisions": 0, "transition_completed_on_centre": False,
                     "objective_lost_with_holder": 0, "release": None}
                active[w["unit"]] = e
            e["withholdings"] += 1
            e["retained"] += w["next"] == "retained"
        # (c) a holder whose MOVE the candidate emits now is released; the reason is the objective's state now
        for u, e in active.items():
            if u in moved[k]:
                status = next((c[1] for c in rows[k].get("checks") or () if c[0] == e["centre"]), None)
                e["release"] = {None: "objective_not_held", "holder_remains": "another_occupant_remains",
                                "no_eligible_holder": "holder_no_longer_eligible",
                                "withheld": "another_holder_selected"}.get(status, f"objective {status}")
    for e in active.values():
        e.update(end="open_at_end", end_k=n - 1)
        episodes.append(e)
    for e in episodes:
        e["end_step"] = steps[min(e["end_k"], n - 1)]
        e["duration_steps"] = e["end_step"] - e["start_step"]
        e["executed"] = e["retained"] > 0
        dest = e["destination"]
        first = next((k for k in range(n) if play[k] and fl[k].get(dest) == faction), None)
        e["destination_label"] = names.get(dest, "not an objective")
        e["destination_first_owned_step"] = steps[first] if first is not None else None
        e["destination_owned_before_start"] = first is not None and first <= e["start_k"]
        e["objective_label"] = names.get(e["centre"])
    # persistent interference (M3)
    longest = 0
    runs: Dict[Any, int] = {}
    for k in range(n):
        holders = {}
        for e in episodes:
            if e["start_k"] <= k <= e["end_k"] and own[k].get(e["unit"], {}).get("cur_hex") == e["centre"]:
                holders[e["centre"]] = e["unit"]
        count = collections.Counter(u.get("cur_hex") for u in own[k].values())
        blocked = {u.get("move_path")[0] for u in own[k].values() if u.get("move_path")
                   and not cand.positive(u.get("speed")) and u.get("move_path")[0] in holders
                   and count[u.get("move_path")[0]] >= 4}
        for centre in list(runs):
            if centre not in blocked:
                longest = max(longest, runs.pop(centre))
        for centre in blocked:
            runs[centre] = runs.get(centre, 0) + 1
    longest = max([longest] + list(runs.values()))
    # objectives
    objective_rows = {}
    for coord, name in sorted(names.items(), key=lambda kv: kv[1]):
        first, losses, recaptures, held = None, 0, 0, False
        lost_with_holder = 0
        for k in range(n):
            if not play[k]:
                continue
            now = fl[k].get(coord) == faction
            if now and first is None:
                first = steps[k]
            if held and not now:
                losses += 1
                if any(e["centre"] == coord and e["start_k"] < k <= e["end_k"] + 1 for e in episodes):
                    lost_with_holder += 1
            if now and not held and first is not None and first != steps[k]:
                recaptures += 1
            held = now
        end = flags(final).get(coord) == faction if final is not None else held
        objective_rows[name] = {"first_ownership_step": first, "losses": losses, "recaptures": recaptures,
                                "held_at_end": end, "losses_with_a_holder_episode": lost_with_holder}
    first_play = next((k for k in range(n) if play[k]), 0)
    start_units = own[first_play]
    end_units = own_ground(final, faction) if final is not None else own[-1]
    lost_units = collections.Counter("artillery" if u.get("type") == 2 and u.get("sub_type") == 3 else
                                     ("infantry" if u.get("type") == 1 else "vehicle")
                                     for uid, u in start_units.items() if uid not in end_units)
    margin = scores.get(f"{side}_total", 0) - scores.get(f"{other}_total", 0)
    public_episodes = [{k: e[k] for k in ("start_step", "end_step", "duration_steps", "end", "settling_at_start",
                                          "withholdings", "retained", "on_centre_decisions", "executed",
                                          "transition_completed_on_centre", "objective_lost_with_holder",
                                          "objective_label", "destination_label", "destination_first_owned_step",
                                          "destination_owned_before_start")} | {"release": e.get("release")}
                       for e in episodes]
    return {
        "candidate_side": side,
        "scores": {"occupy": scores.get(f"{side}_occupy"), "attack": scores.get(f"{side}_attack"),
                   "remain": scores.get(f"{side}_remain"), "total": scores.get(f"{side}_total"), "margin": margin,
                   "opponent_occupy": scores.get(f"{other}_occupy"), "opponent_total": scores.get(f"{other}_total")},
        "mechanism": {"withholding_decisions": len({w["k"] for w in withholdings}), "withheld_moves": len(withholdings),
                      "withheld_from_settling_holders": sum(1 for w in withholdings if w["settling"]),
                      "next_decision_outcomes": dict(sorted(outcome.items())),
                      "episodes": len(episodes), "executed_episodes": sum(1 for e in episodes if e["executed"]),
                      "episodes_by_end": dict(sorted(collections.Counter(e["end"] for e in episodes).items())),
                      "transition_completed_on_centre": sum(1 for e in episodes if e["transition_completed_on_centre"]),
                      "holders_destroyed_while_holding": sum(1 for e in episodes if e["end"] == "holder_absent"),
                      "departures_without_release": len(failures_m1),
                      "longest_interference_run_steps": longest,
                      "episode_rows": public_episodes},
        "objectives": objective_rows,
        "objectives_held_at_end": sorted(k for k, v in objective_rows.items() if v["held_at_end"]),
        "ownership_losses": sum(v["losses"] for v in objective_rows.values()),
        "recaptures": sum(v["recaptures"] for v in objective_rows.values()),
        "units_lost": dict(sorted(lost_units.items())), "units_lost_total": sum(lost_units.values()),
        "own_ground_units_at_start": len(start_units),
        "refused_actions": feedback_errors,
        "private": {"withholdings": withholdings, "episodes": episodes, "m1": failures_m1},
    }


# ------------------------------------------------------------------------------------------------
# Mechanism failures, harm stops, gate and disposition


def mechanism_failures(facts: Mapping[str, Any]) -> Dict[str, List[str]]:
    m = facts["mechanism"]
    out: Dict[str, List[str]] = {}
    if m["departures_without_release"]:
        out["M1"] = [f"{m['departures_without_release']} holders left the centre without a released MOVE"]
    if m["executed_episodes"] == 0:
        out["M2"] = ["no executed garrison episode"]
    if m["longest_interference_run_steps"] >= RULES["mechanism"]["interference_limit_steps"]:
        out["M3"] = [f"a holder blocked waiting units for {m['longest_interference_run_steps']} consecutive steps"]
    return out


def harm_stops(position: int, facts: Mapping[str, Any]) -> List[str]:
    s = facts["scores"]
    out = []
    inert = RULES["inert_harm"]["positions"].get(str(position))
    if inert is not None:
        if s["occupy"] < inert["occupy"]:
            out.append(f"occupy {s['occupy']} below the baseline-v2 occupy {inert['occupy']}")
        if s["margin"] < inert["margin_floor"]:
            out.append(f"margin {s['margin']} below the floor {inert['margin_floor']}")
        return out
    h2h = RULES["head_to_head_harm"]["positions"][str(position)]
    if facts["candidate_side"] != h2h["seat"]:
        raise ValueError("the head-to-head position and the candidate's seat disagree")
    if s["margin"] < h2h["margin_minimum"]:
        out.append(f"margin {s['margin']} below the mirror minimum {h2h['margin_minimum']}")
    if s["occupy"] < h2h["occupy_minimum"]:
        out.append(f"occupy {s['occupy']} below the mirror minimum {h2h['occupy_minimum']}")
    never = [o for o in h2h["opening_objectives"] if facts["objectives"].get(o, {}).get("first_ownership_step") is None]
    if never:
        out.append(f"opening objectives never first-owned: {never}")
    return out


def gate(completed: bool, structural: Sequence[str], mechanism: Mapping[str, Any], harm: Sequence[str]) -> Dict[str, Any]:
    reasons = []
    if not completed:
        reasons.append("the game did not complete")
    if structural:
        reasons.append(f"structural stops {list(structural)}")
    if mechanism:
        reasons.append(f"mechanism failures {sorted(mechanism)}")
    if harm:
        reasons.append("harm stops: " + "; ".join(harm))
    return {"next_session_authorized": not reasons, "reasons": reasons}


def disposition(games_: Sequence[Mapping[str, Any]], ledger_ok: bool) -> Dict[str, Any]:
    """First match over the opened games (each: ``position``, ``completed``, ``structural``, ``mechanism``,
    ``harm``, ``facts``): INVALID (no game, a structural stop, an incomplete game, a ledger problem, a game opened after
    a closed gate or a gate open with fewer than four games); REJECT (a mechanism failure or a harm stop); PROMISING
    (four games, the registered directional criterion); INCONCLUSIVE."""
    base = {"sessions_opened": len(games_), "order": list(DISPOSITIONS)}
    problems = []
    if not games_ or len(games_) > SESSION_CEILING or not ledger_ok:
        problems.append(f"{len(games_)} games, ledger ok {ledger_ok}")
    for i, g in enumerate(games_):
        if g["structural"] or not g["completed"]:
            problems.append(f"position {g['position']}: structural {list(g['structural'])}, completed {g['completed']}")
        if g["position"] != i + 1:
            problems.append("games out of order")
    closed = [g["position"] for g in games_ if g["mechanism"] or g["harm"] or g["structural"] or not g["completed"]]
    if closed and closed[0] != games_[-1]["position"]:
        problems.append("a session was opened after a closed gate")
    if not closed and len(games_) < SESSION_CEILING:
        problems.append("the pilot stopped with an open gate")
    if problems:
        return {**base, "disposition": INVALID, "problems": problems}
    if closed:
        g = games_[-1]
        return {**base, "disposition": REJECT, "position": g["position"], "mechanism": dict(g["mechanism"]),
                "harm": list(g["harm"])}
    red = next(g for g in games_ if g["position"] == 3)["facts"]
    reasons = []
    if not all(next(g for g in games_ if g["position"] == p)["facts"]["mechanism"]["executed_episodes"] for p in (3, 4)):
        reasons.append("no executed episode in a head-to-head game")
    h2h = RULES["head_to_head_harm"]["positions"]["3"]
    if not red["scores"]["occupy"] > h2h["occupy_maximum"]:
        reasons.append("red occupy not above the mirror maximum")
    if not Fraction(red["scores"]["margin"]) >= Fraction(h2h["margin_mean"]):
        reasons.append("red margin below the mirror mean")
    return {**base, "disposition": INCONCLUSIVE if reasons else PROMISING, "not_promising_because": reasons}


# ------------------------------------------------------------------------------------------------
# Public sanitization


def public_problems(data: Any, private_values: Iterable[Any], scenarios: Iterable[str]) -> List[str]:
    return sp.public_problems(data, private_values, scenarios)


def dump(data: Any) -> str:
    return sp.dump(data)
