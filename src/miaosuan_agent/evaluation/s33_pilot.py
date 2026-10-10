"""The registered Sprint 33 live stop mechanism check of ``t7-b1-stop-engage-1`` (``docs/SPRINT33_T7_B1_LIVE.md``).

At most two exclusive engine sessions, 2801 and 2802, of the exploratory candidate in the owner's two selected
configurations (:data:`SCHEDULE`: the candidate blue against the inert red, 2120531121 C3 then 1930331196 C3), the
second opened only when the first passed its registered gate. A mechanism qualification: score improvement is not an
endpoint, nothing is promoted or uploaded, and a two-game result authorizes no wider test.

This module fixes, before session 2801: the identities, the card and its pins, the session budget and the ledger audit,
the per-game structural stops, the frames and stop orders read from the full-step capture, the per-stop classification
(:mod:`.s33_mechanism`: Sprint 32's rules with one registered correction, plus supplementary endpoints), the harm screen
and its thresholds (read from Sprint 30's committed controls), the per-game gate, the disposition with its evidence level,
and the public sanitization. Nothing here reads an engine, a capture or the ledger by itself; callers pass the data in.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..decision import INERT_ID
from ..experiments import t7_b1_stop_engage as cand
from . import exploratory as xp
from . import manifest as mf
from . import s12_screen as sc
from . import s27_probe as sp27
from . import s32_mechanism as m32
from . import s33_mechanism as mm

STUDY_ID = "s33-t7-b1-live"
CARD_ID = "s33-t7-b1-live-1"
SCHEMA = "miaosuan-s33-live/1"
CANDIDATE_ID = cand.CANDIDATE_ID
V2_ID, V2_DIGEST = sc.V2_ID, sc.V2_DIGEST
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2800
SESSION_CEILING = 2
EXPECTED_SESSIONS = (2801, 2802)
WORKERS = 1
GROUND = (1, 2)
PLAY_STAGE = 2
#: (position, scenario, condition, red, blue): the owner's order; C3 = the inert red against the candidate blue.
#: Position n opens session 2800 + n.
SCHEDULE: Tuple[Tuple[int, str, str, str, str], ...] = (
    (1, "2120531121", "C3", INERT_ID, CANDIDATE_ID),
    (2, "1930331196", "C3", INERT_ID, CANDIDATE_ID))
#: The candidate's policy source (baseline-v2's 22 files, the add-on wrapper and the candidate: 24 files).
CANDIDATE_DIGEST = "97658f4d89e47eb247704f1995754a1e81d32e8b60dcce9ae4ed61c6e068fd84"
CONTROLS = "evaluation/s30-t13-k1/controls.json"
CONTROLS_SHA256 = "27dffdfdfa2f920a921cb68da389bed80bb7a6e01950de7ffaac54b34c186e93"
PREFLIGHT = "evaluation/s32-t7-b1/preflight.json"
PREFLIGHT_SHA256 = "ec94e9847fe5ceedfcde210b61040b5572696af3b28b3a5829ee065684b946f0"

# ------------------------------------------------------------------------------------------------
# Rules (frozen before session 2801)

RULES: Dict[str, Any] = {
    "max_step": 2880,
    "controls": f"{CONTROLS} (Sprint 30, SHA-256 {CONTROLS_SHA256}): baseline-v2's group C games of the registered "
                "shoot-reservation experiment against the inert control, fifteen per configuration; margin = own total "
                "minus the opponent's total, equal to the engine's margin field",
    "inert_harm": {
        "rule": "REJECT (verdict HARM) when the candidate's occupy score is below the configuration's baseline-v2 occupy "
                "score (constant over its fifteen games), or its margin is below the baseline-v2 margin minimum minus "
                "50; the boundaries themselves pass; a safety screen, not an improvement test",
        "positions": {"1": {"configuration": "2120531121 C3 baseline-v2 blue", "occupy": 310, "margin_minimum": 559,
                            "margin_floor": 509},
                      "2": {"configuration": "1930331196 C3 baseline-v2 blue", "occupy": 310, "margin_minimum": 570,
                            "margin_floor": 520}}},
    "opportunity": {
        "source": f"{PREFLIGHT}: the first divergence of each configuration's genuine full-step baseline-v2 record",
        "positions": {"1": {"first_divergence_step": 380, "reaching_weapon": "vehicle-mounted missile",
                            "distance": 18, "range": 20},
                      "2": {"first_divergence_step": 620, "reaching_weapon": "vehicle-mounted missile",
                            "distance": 20, "range": 20}},
        "use": "descriptive only: whether the live game's first stop falls at the recorded step is reported; no stop or "
               "gate depends on it, and no later step is predicted"},
    "mechanism": {
        "rules": mm.RULES_ID,
        "base": "evaluation/s32_mechanism.py, unchanged: tolerance 2 steps; feedback window 2 steps; path cleared by "
                "s0 + h0 + 2 at the latest; completion within the clearing step + 75 plus or minus 2; movement relisted, "
                "shooting listed and the shot within 2 steps of completion; a shot accepted when echoed without error "
                "and named as attacker by a judge record in its step or the next; deadlock run 300 frames",
        "adverse": list(mm.ADVERSE),
        "correction": "Sprint 32's 'deferred' (flag_force_stop 1 at any later frame) is replaced by "
                      "'deferred_indefinite' (flag_force_stop 1 with a non-empty path at a frame at or after the clearing "
                      "deadline); the transient flag is reported",
        "censored": "the unit absent before the path cleared or during the transition, the game over before an event's "
                    "deadline, or the unit suppressed at completion; never positive evidence and never adverse",
        "verdicts": list(mm.GAME_VERDICTS),
        "evidence_levels": {"T7B1_MECH_SUPPORTED": list(mm.SUPPORTED_LEVELS),
                            "T7B1_MECH_STOP_ONLY": list(mm.STOP_ONLY_LEVELS)},
        "preserved": "Sprint 32's own per-stop adverse list, game verdict and disposition are computed and reported "
                     "beside Sprint 33's"},
    "gate": "session 2802 opens only when game one completed with no structural stop and its Sprint 33 verdict is "
            "UNTESTED, STOP_ONLY or OBSERVED; STRUCTURAL, ADVERSE (an adverse stop outcome or a deadlock), HARM or "
            "NOT_ENGAGING closes it; after session 2802 the check stops whatever the result",
    "untested_continuation": "an UNTESTED first game does not close the gate because the second configuration's "
                             "opportunity is verified from its own genuine full-step record (step 620 in 1930331196 C3), "
                             "independently of the first configuration",
    "disposition": "first match over the opened games (evaluation/s32_mechanism.disposition on Sprint 33's verdicts): "
                   "T7B1_MECH_INVALID, T7B1_MECH_REJECT, T7B1_MECH_NOT_ENGAGING, T7B1_MECH_SUPPORTED, "
                   "T7B1_MECH_STOP_ONLY, T7B1_MECH_UNTESTED; an incomplete game or a ledger problem is INVALID",
}
STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7")
STOP_MEANING = {
    "S1": "engine-installation integrity failure (session close or the ledger's state chain)",
    "S2": "ledger inconsistency, a wrong card, game or digest, an unclosed session, a session out of order or beyond 2802",
    "S3": "privacy or repository exposure: a file outside the ignored tree appeared, or a tracked file changed",
    "S4": "a contract error, a wrong margin identity or a game that did not complete",
    "S6": "a replay mismatch",
    "S7": "capture, reconstruction or action-fidelity failure: an observer error, a missing or digest-mismatched capture, "
          "a live decision or memory that differs from its seat-local reconstruction, an action list that is not "
          "baseline-v2's followed by the rule's documented stops, a unit stopped twice, an independent-check finding, an "
          "add-on error, disagreeing counts, a wrong scenario, condition, seat or opponent, or a max_step other than 2,880",
}
DISPOSITIONS = mm.DISPOSITIONS

#: Files whose normalised SHA-256 the card pins.
FROZEN_FILES = (
    "src/miaosuan_agent/experiments/t7_b1_stop_engage.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "src/miaosuan_agent/evaluation/s33_pilot.py",
    "src/miaosuan_agent/evaluation/s33_capture.py",
    "src/miaosuan_agent/evaluation/s33_mechanism.py",
    "src/miaosuan_agent/evaluation/s32_mechanism.py",
    "src/miaosuan_agent/evaluation/s32_preflight.py",
    "src/miaosuan_agent/evaluation/t7_candidates.py",
    "src/miaosuan_agent/evaluation/t7_visibility.py",
    "src/miaosuan_agent/evaluation/s27_probe.py",
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/game.py",
    "scripts/build_s33_card.py",
    "scripts/run_s33_game.py",
    "scripts/run_s33_pilot.py",
    "scripts/s33_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_s12_stage.py",
    "tests/test_t7_b1_stop_engage.py",
    "tests/test_s32_mechanism.py",
    "tests/test_s33_mechanism.py",
    "tests/test_s33_pilot.py",
    "tests/fixtures/s33_engine.py",
)

TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED TWO-GAME MECHANISM QUALIFICATION - NOT A CONFIRMATION - NOT ELIGIBLE FOR "
              "PROMOTION",
    "version": "t7-b1-stop-engage-1, Sprint 33 live stop mechanism check (docs/SPRINT33_T7_B1_LIVE.md)",
    "mechanism": "baseline-v2 plays the seat on its own observation at every decision; the add-on appends a documented "
                 "stop (action 10) for a traversing non-tank ground unit that baseline-v2 leaves without an action, "
                 "with an enemy ground unit in its own view within published range of the hex where the stop takes "
                 "effect, at most once per unit and game",
    "controls": "historical and descriptive: Sprint 30's committed baseline-v2 controls against the inert control "
                "(fifteen games per configuration); no new control game",
    "configurations": "2120531121 C3 then 1930331196 C3, the candidate blue against the inert control in both",
    "safety_checks": ["structural stops after every game (S1, S2, S3, S4, S6, S7)",
                      "the per-stop mechanism classification, the deadlock bound and the harm screen, then the "
                      "registered gate before session 2802",
                      "at most two sessions after closed session 2800, in schedule order, exclusive diagnostic sessions",
                      "every frozen implementation file pinned by digest; baseline-v2's policy source to 7cbaf032..."],
    "intended_observations": ["the exploratory capture and the Sprint 33 full-step timeline with the seat-local "
                              "reconstruction, the action-fidelity check and the independent check at every decision"],
    "next_step_rule": "the registered gate after game one (s33_pilot.gate); after game two the disposition",
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
    others = [side for side in ("red", "blue") if entry.get(side) == INERT_ID]
    if len(sides) != 1 or len(others) != 1:
        raise ValueError("a game must seat the candidate against the inert control")
    return sides[0]


def opponent(entry: Mapping[str, Any]) -> str:
    return entry["blue"] if candidate_side(entry) == "red" else entry["red"]


def build_card(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, policies: Sequence[Mapping[str, Any]],
               frozen: Mapping[str, str]) -> Dict[str, Any]:
    by_id = {p["id"]: p for p in policies}
    if sorted(by_id) != sorted((V2_ID, CANDIDATE_ID)):
        raise ValueError("the card's policies are baseline-v2 and the Sprint 33 candidate only")
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
    card["screen"] = {"id": STUDY_ID, "stage": "mechanism", "rules": RULES, "rules_sha256": rules_digest(),
                      "mechanism_rules": mm.RULES_ID, "frozen_files": dict(sorted(frozen.items())),
                      "expected_sessions": list(EXPECTED_SESSIONS), "structural_stops": list(STRUCTURAL_STOPS),
                      "dispositions": list(DISPOSITIONS), "controls_sha256": CONTROLS_SHA256,
                      "preflight_sha256": PREFLIGHT_SHA256}
    return card


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout: identity, rules, frozen files, policies, budget, schedule,
    and the committed controls and preflight it rests on."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != CARD_ID or screen.get("id") != STUDY_ID:
        return ["not the Sprint 33 card"]
    if screen.get("rules") != RULES or screen.get("rules_sha256") != rules_digest() \
            or screen.get("mechanism_rules") != mm.RULES_ID:
        problems.append("the card's rules are not the frozen rules")
    if (screen.get("structural_stops"), screen.get("dispositions")) != (list(STRUCTURAL_STOPS), list(DISPOSITIONS)):
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
        problems.append("the card's candidate is not the Sprint 33 candidate")
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
    """Every session opened after 2800 must be the card's game in schedule position (session 2800 + n plays position
    n) under the card's digest and the candidate's registered digest, opened once and closed with integrity ok, the
    state chain continuous, at most two sessions and none unclosed."""
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
                problems["S2"].append(f"session {session} is not under the Sprint 33 card")
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
    """Before the game at ``position``: exactly the card's first ``position - 1`` games opened after 2800, in order."""
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
    scores = record.get("final_scores") or {}
    if not scores or scores.get(f"{side}_win") != scores.get(f"{side}_total", 0) - scores.get(f"{other}_total", 0):
        stops["S4"].append("the margin is missing or not the engine's <side>_win")
    if record.get("observer_errors"):
        stops["S7"].append(f"{len(record['observer_errors'])} observer errors")
    for name, (recorded, actual) in dict(capture_digests).items():
        if recorded is None or recorded != actual:
            stops["S7"].append(f"capture {name} missing or not the recorded digest")
    for key, label in (("consistency_errors", "decisions differ from the seat-local reconstruction or memory chain"),
                       ("unregistered_differences", "decisions are not baseline-v2's actions plus the rule's stops"),
                       ("independent_problems", "decisions with an independent-check finding"),
                       ("repeated_stops", "decisions stop a unit a second time")):
        if timeline.get(key):
            stops["S7"].append(f"{len(timeline[key])} {label}")
    steps = timeline.get("steps") or []
    if len(steps) != record.get("steps") or explore.get("steps") != record.get("steps"):
        stops["S7"].append("the captures and the record disagree on the number of steps")
    if timeline.get("reconstructed_decisions") != len(steps) or timeline.get("policy_decisions") != len(steps):
        stops["S7"].append("not every decision of the policy seat was reconstructed")
    candidate = next((s for s in seats if s.get("policy") == CANDIDATE_ID), {})
    seat = candidate.get("seat")
    by_type = candidate.get("actions_by_type") or {}
    for kind in (cand.MOVE, cand.STOP):
        count = sum(1 for step in steps for a in step.get("submitted") or () if a["seat"] == seat
                    and a["action"].get("type") == kind)
        if count != int(by_type.get(str(kind), 0)):
            stops["S7"].append(f"the timeline and the record disagree on the candidate seat's type {kind} actions")
    if timeline.get("stops_emitted") != int(by_type.get(str(cand.STOP), 0)):
        stops["S7"].append("the observer's stop count and the record disagree")
    if explore.get("addon_errors"):
        stops["S7"].append(f"{len(explore['addon_errors'])} candidate add-on errors")
    if max_step != RULES["max_step"]:
        stops["S7"].append(f"max_step {max_step} is not the registered {RULES['max_step']}")
    return {code: found for code, found in stops.items() if found}


# ------------------------------------------------------------------------------------------------
# Frames and orders (the inputs of the Sprint 32 and Sprint 33 classification)


def listed_types(raw: Mapping[str, Any], unit: int) -> Tuple[int, ...]:
    per = cand.unit_listing(raw, unit) or {}
    out = []
    for key in per:
        try:
            out.append(int(key))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(out))


def snap(raw: Mapping[str, Any], u: Mapping[str, Any]) -> m32.Snap:
    return m32.Snap(hex=u.get("cur_hex"), path=tuple(u.get("move_path") or ()), speed=u.get("speed"), stop=u.get("stop"),
                    timer=u.get("move_to_stop_remain_time"), force=u.get("flag_force_stop"),
                    listed=listed_types(raw, u["obj_id"]), see=tuple(u.get("see_enemy_bop_ids") or ()),
                    keep=u.get("keep", 0))


def frames_of(raws: Sequence[Mapping[str, Any]], steps: Sequence[Mapping[str, Any]], seat: int,
              faction: int) -> List[Dict[str, Any]]:
    """One frame per decision of the candidate seat: its own ground units, the enemy ground units in its view, the
    step's feedback and new judge records, and the seat's emitted actions (``s32_mechanism``'s frame form)."""
    if len(raws) != len(steps) or not raws:
        raise ValueError("the observations and the timeline steps do not align")
    out = []
    for raw, step in zip(raws, steps):
        ops = [u for u in raw.get("operators") or () if isinstance(u, Mapping)]
        out.append({"step": (raw.get("time") or {}).get("cur_step"),
                    "units": {u["obj_id"]: snap(raw, u) for u in ops if u.get("color") == faction
                              and u.get("type") in GROUND},
                    "enemies": {u["obj_id"]: (u.get("cur_hex"), u.get("type")) for u in ops
                                if u.get("color") != faction and u.get("type") in GROUND},
                    "feedback": list(step.get("feedback") or ()), "judge": list(step.get("judge_new") or ()),
                    "emitted": [a["action"] for a in step.get("submitted") or () if a["seat"] == seat]})
    return out


def orders_of(raws: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], faction: int) -> List[m32.Order]:
    """Every stop the candidate emitted, from the timeline's reconstruction rows (their change records) and the seat's
    observation at that decision."""
    out = []
    for k, row in enumerate(rows):
        for text in row.get("changes") or ():
            change = json.loads(text)
            if change.get("kind") != "added_stop":
                continue
            u = next(x for x in raws[k].get("operators") or () if x.get("obj_id") == change["obj_id"]
                     and x.get("color") == faction)
            out.append(m32.Order(k=k, step=change["step"], unit=change["obj_id"], h0=change["hex_steps"],
                                 start_hex=u.get("cur_hex"), next_hex=change["next_hex"],
                                 weapons=tuple(u.get("carry_weapon_ids") or ())))
    return out


# ------------------------------------------------------------------------------------------------
# Facts, harm, gate and disposition

PUBLIC_STOP_KEYS = ("step", "h0", "adverse", "s32_adverse", "censored", "where", "fire_evaluable", "fire_listed",
                    "shot_accepted", "move_relisted")


def public_stop(result: Mapping[str, Any], order: m32.Order) -> Dict[str, Any]:
    """One stop's public row: steps as offsets from the order, labels and booleans; no unit, hex or target."""
    row = {key: result[key] for key in PUBLIC_STOP_KEYS}
    row["cleared_offset"] = None if result["cleared_step"] is None else result["cleared_step"] - order.step
    row["completed_offset"] = None if result["completed_step"] is None else result["completed_step"] - order.step
    e = dict(result["endpoints"])
    for key in ("expected_entry_step", "entry_step", "resume_order_step"):
        value = e.pop(key)
        e[key.replace("_step", "_offset")] = None if value is None else value - order.step
    row["endpoints"] = e
    return row


def harm_control(position: int) -> Dict[str, int]:
    p = RULES["inert_harm"]["positions"][str(position)]
    return {"occupy": p["occupy"], "margin_min": p["margin_minimum"]}


def game_facts(position: int, entry: Mapping[str, Any], raws: Sequence[Mapping[str, Any]],
               final: Optional[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]],
               steps: Sequence[Mapping[str, Any]], seat: int, scores: Mapping[str, Any],
               structural: Sequence[str]) -> Dict[str, Any]:
    """The candidate seat's facts and the game verdict. ``raws``: its observation at each decision; ``final``: its
    observation after the last step; ``rows``: the timeline's reconstruction rows; ``steps``: the timeline steps."""
    side = candidate_side(entry)
    faction = 0 if side == "red" else 1
    other = "blue" if side == "red" else "red"
    if len(rows) != len(raws):
        raise ValueError("the decisions and rows do not align")
    frames = frames_of(raws, steps, seat, faction)
    orders = orders_of(raws, rows, faction)
    results = [mm.classify(o, frames) for o in orders]
    runs = m32.deadlock_runs(orders, results, frames)
    margin = scores.get(f"{side}_total", 0) - scores.get(f"{other}_total", 0)
    occupy = scores.get(f"{side}_occupy")
    verdict = mm.game_verdict(structural, results, runs, occupy if occupy is not None else -1, margin,
                              harm_control(position))
    predicted = RULES["opportunity"]["positions"][str(position)]["first_divergence_step"]
    first_play = next((k for k, r in enumerate(raws) if (r.get("time") or {}).get("stage") == PLAY_STAGE), 0)
    start_units = {u["obj_id"]: u for u in raws[first_play].get("operators") or () if u.get("color") == faction
                   and u.get("type") in GROUND}
    end_raw = final if final is not None else raws[-1]
    end_units = {u["obj_id"] for u in end_raw.get("operators") or () if u.get("color") == faction}
    refused = sum(1 for step in steps for f in step.get("feedback") or ()
                  if f.get("error") and (f.get("message") or {}).get("actor") == seat)
    return {
        "candidate_side": side,
        "scores": {"occupy": occupy, "attack": scores.get(f"{side}_attack"), "remain": scores.get(f"{side}_remain"),
                   "total": scores.get(f"{side}_total"), "margin": margin,
                   "opponent_total": scores.get(f"{other}_total")},
        "stops": len(orders),
        "first_stop_step": orders[0].step if orders else None,
        "recorded_first_divergence_step": predicted,
        "first_stop_at_recorded_step": bool(orders) and orders[0].step == predicted,
        "stop_rows": [public_stop(r, o) for r, o in zip(results, orders)],
        "deadlock_runs": list(runs),
        "verdict": verdict,
        "own_ground_units_at_start": len(start_units),
        "units_lost_total": sum(1 for u in start_units if u not in end_units),
        "refused_actions": refused,
        "private": {"orders": [o.__dict__ for o in orders], "results": results},
    }


def gate(completed: bool, structural: Sequence[str], verdict: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    reasons = []
    if not completed:
        reasons.append("the game did not complete")
    if structural:
        reasons.append(f"structural stops {list(structural)}")
    if verdict is None:
        reasons.append("no verdict")
    elif not verdict["gate_open"]:
        reasons.append(f"verdict {verdict['verdict']}")
    return {"next_session_authorized": not reasons, "reasons": reasons}


def disposition(games_: Sequence[Mapping[str, Any]], ledger_ok: bool) -> Dict[str, Any]:
    """First match over the opened games (each: ``position``, ``completed``, ``structural`` and ``verdict``, the
    game's Sprint 33 verdict block): ``T7B1_MECH_INVALID`` when no game was opened, a game is out of order or did not
    complete, or the ledger audit fails; otherwise :func:`.s33_mechanism.disposition` over the verdicts (which maps a
    structural stop, a game behind a closed gate, too many games or too few with the gate open to INVALID)."""
    base = {"sessions_opened": len(games_), "order": list(DISPOSITIONS)}
    problems = []
    if not games_ or len(games_) > SESSION_CEILING or not ledger_ok:
        problems.append(f"{len(games_)} games, ledger ok {ledger_ok}")
    for i, g in enumerate(games_):
        if g["position"] != i + 1:
            problems.append("games out of order")
        if not g["completed"] or g.get("verdict") is None:
            problems.append(f"position {g['position']} did not complete")
    if problems:
        return {**base, "disposition": DISPOSITIONS[0], "problems": problems, "evidence_level": None,
                "demonstrated": [], "s32_disposition": DISPOSITIONS[0]}
    verdicts = []
    for g in games_:
        v = dict(g["verdict"])
        if g["structural"]:
            v.update(verdict=mm.GAME_VERDICTS[0], gate_open=False, s32_verdict=mm.GAME_VERDICTS[0])
        verdicts.append(v)
    return {**base, **mm.disposition(verdicts, SESSION_CEILING)}


# ------------------------------------------------------------------------------------------------
# Public sanitization


def public_problems(data: Any, private_values: Iterable[Any], scenarios: Iterable[str]) -> List[str]:
    return sp27.public_problems(data, private_values, scenarios)


def dump(data: Any) -> str:
    return sp27.dump(data)
