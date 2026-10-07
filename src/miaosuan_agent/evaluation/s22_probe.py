"""The registered Sprint 22 T2-P1 transport mechanism probe (``docs/SPRINT22_T2_TRANSPORT_PROBE.md``): every rule.

At most one exclusive engine session (2796) of the exploratory mechanism candidate ``t2-transport-p1``
(``experiments/t2_transport_p1.py``) against the inert control, in the configuration of the deterministic witness
selected offline by :func:`select_witness`, under the full-step capture of :mod:`.s22_capture`. A mechanism probe: not a
score screen, not a confirmation; nothing is promoted and no score, margin, winner or kill count enters any rule.

This module fixes, before session 2796: the witness-selection procedure (corpus tiers, minimum criteria, the ranking),
the identities, the card and its pins, the session budget and the ledger audit, the per-game structural checks, the
prefix check, the registered-difference check, every mechanism endpoint, the disposition order and the public
sanitization. Nothing here reads an engine, a capture or the ledger by itself; callers pass the data in.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..decision import INERT_ID
from ..experiments import t2_transport_p1 as t2
from . import exploratory as xp
from . import manifest as mf
from . import s12_screen as sc

STUDY_ID = "s22-t2-transport-probe"
CARD_ID = "s22-t2-transport-probe-1"
SCHEMA = "miaosuan-s22-probe/1"
CANDIDATE_ID = t2.CANDIDATE_ID
V2_ID, V2_DIGEST = sc.V2_ID, sc.V2_DIGEST
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2795
SESSION_CEILING = 1
EXPECTED_SESSIONS = (2796,)
WORKERS = 1
MOVE, SHOOT, EMBARK, DISEMBARK, OCCUPY, INDIRECT, GUIDED = 1, 2, 3, 4, 5, 8, 9
FIRE_TYPES = (SHOOT, INDIRECT, GUIDED)

# ------------------------------------------------------------------------------------------------
# Witness selection (section 8 and 9 of the registration): frozen before the search was run


#: Corpus tiers. Tier 1: an actual baseline-v2-versus-inert game. Tier 2 (considered only when no tier-1 game meets
#: every minimum): another inert-control game whose candidate seat emitted exactly baseline-v2's reconstructed actions
#: at every decision up to and including the trigger decision.
TIERS = {1: "actual baseline-v2 against the inert control",
         2: "inert-control game whose seat equals reconstructed baseline-v2 through the trigger"}
#: Minimum criteria of a witness (all must hold), in the order they are checked.
MINIMUMS = (
    "full_step_capture",          # Sprint 21's usable-capture rule: every pre-step snapshot, pre-execution copies,
                                  # feedback, judge records, final state
    "inert_opponent",             # the other seat is the inert control
    "reconstruction_exact",       # baseline-v2 reconstructed from the seat's observation and memory equals the
                                  # recorded actions at every decision up to the trigger (tier 2: equals the emitted)
    "trigger",                    # the candidate's own trigger fires (t2_transport_p1.trigger) at some decision
    "before_first_fire",          # the trigger decision precedes the game's first fire order or judge record
    "carrier_route_to_objective", # baseline-v2's move for the carrier at the trigger ends on an objective
    "time_feasible",              # trigger step + documented embark + carrier free flow + documented stop
                                  # transition + documented disembark < max_step
)
#: Ranking of witnesses meeting every minimum (lexicographic, smaller first).
RANKING = ("tier", "destination_saturated_in_history", "destination_taken_by_another_unit_before_release",
           "no_free_flow_saving", "infantry_can_arrive_on_foot", "trigger_step", "game")


def feasible(trigger_step: int, carrier_free_flow: int, max_step: int) -> bool:
    """The earliest possible completion fits the game: documented embark, the carrier's free flow, the documented stop
    transition and the documented disembark."""
    return trigger_step + 3 * t2.DOCUMENTED_TRANSITION + carrier_free_flow < max_step


def rank_key(row: Mapping[str, Any]) -> Tuple[Any, ...]:
    """The frozen witness ranking (``RANKING``)."""
    return (row["tier"], bool(row["destination_saturated_in_history"]),
            bool(row["destination_taken_by_another_unit_before_release"]), not (row["free_flow_saving"] > 0),
            not row["infantry_cannot_arrive_on_foot"], row["trigger_step"], row["game"])


def minimum_failures(row: Mapping[str, Any]) -> List[str]:
    return [name for name in MINIMUMS if not row.get(name)]


def select_witness(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The selection: tier-1 games first; tier 2 only if no tier-1 game meets every minimum. Among eligible rows, the
    smallest :func:`rank_key`. Returns the chosen row (or None) and the eligibility of every row."""
    eligible = [r for r in rows if not minimum_failures(r)]
    tier1 = [r for r in eligible if r["tier"] == 1]
    pool = tier1 or [r for r in eligible if r["tier"] == 2]
    chosen = min(pool, key=rank_key) if pool else None
    return {"chosen": chosen, "eligible": [r["game"] for r in sorted(eligible, key=rank_key)],
            "failures": {r["game"]: minimum_failures(r) for r in rows}}


# ------------------------------------------------------------------------------------------------
# Rules, card, budget (filled at registration from the selected witness)

#: Every threshold and anchor, fixed before session 2796.
RULES: Dict[str, Any] = {
    "max_step": 2880,
    "timing_basis": "DOCUMENTED_75",
    "documented_transition_steps": t2.DOCUMENTED_TRANSITION,
    "transition_bound_steps": t2.BOUND,
    "stacking_limit": t2.STACK_LIMIT,
    "witness": None,
}
SCHEDULE: Tuple[Tuple[int, str, str, str, str], ...] = ()
STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7", "SP")
STOP_MEANING = {
    "S1": "engine-installation integrity failure (session close or the ledger's state chain)",
    "S2": "ledger inconsistency, a wrong card or digest, an unclosed session or more than one session",
    "S3": "privacy exposure: a file outside the ignored tree appeared, or a tracked file changed, during the game",
    "S4": "a contract error, a wrong margin identity or a game that did not complete",
    "S6": "a replay mismatch",
    "S7": "capture or reconstruction failure: an observer error, a missing or digest-mismatched capture, a live decision "
          "or memory that differs from the seat-local reconstruction, a difference from baseline-v2 that is not a "
          "registered transport edit, a candidate add-on error, disagreeing counts, a wrong scenario, condition or "
          "seat, or a max_step other than 2,880",
    "SP": "prefix failure: the candidate did not equal baseline-v2 before the registered trigger decision, or the "
          "trigger is not the registered pair at the registered decision with the registered actions",
}
DISPOSITIONS = ("T2_P1_PROTOCOL_AMBIGUOUS", "T2_P1_NO_DETERMINISTIC_WITNESS", "CAPTURE_INVALID",
                "T2_P1_DESTINATION_CAPACITY_BLOCKED", "T2_P1_MECHANISM_REFUTED", "T2_P1_MECHANISM_SUPPORTED")
(AMBIGUOUS, NO_WITNESS, INVALID, BLOCKED, REFUTED, SUPPORTED) = DISPOSITIONS

#: Files whose normalised SHA-256 the card pins.
FROZEN_FILES = (
    "src/miaosuan_agent/experiments/t2_transport_p1.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "src/miaosuan_agent/evaluation/s22_probe.py",
    "src/miaosuan_agent/evaluation/s22_capture.py",
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/t9_confirmation.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/game.py",
    "scripts/build_s22_card.py",
    "scripts/run_s22_game.py",
    "scripts/run_s22_probe.py",
    "scripts/s22_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_s12_stage.py",
    "tests/test_t2_transport_p1.py",
    "tests/test_s22_probe.py",
)

TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED MECHANISM PROBE - NOT A SCORE SCREEN - NOT ELIGIBLE FOR PROMOTION",
    "version": "t2-transport-p1, Sprint 22 transport mechanism probe (docs/SPRINT22_T2_TRANSPORT_PROBE.md)",
    "mechanism": "baseline-v2 plays the seat; for one infantry-carrier pair the candidate replaces the infantry's move "
                 "by embark at the registered trigger, withholds the carrier's move during the embark transition and "
                 "at its destination, and issues disembark there when it is listed and the hex is below the stacking "
                 "limit",
    "controls": "none: the inert control seat; no score is compared and nothing is pooled",
    "configurations": "the configuration of the deterministic witness selected offline, one game",
    "safety_checks": ["structural stops after the game (S1, S2, S3, S4, S6, S7 and the prefix check SP)",
                      "exactly one session after closed session 2795; an exclusive diagnostic session",
                      "every frozen implementation file pinned by digest; any difference refuses the card",
                      "the candidate's policy source pinned; baseline-v2's to 7cbaf032..."],
    "intended_observations": ["Sprint 9's T9Capture, the exploratory capture and the Sprint 22 full-step timeline with "
                              "the seat-local reconstruction of baseline-v2 and the candidate, with its memory chain, "
                              "at every decision"],
    "next_step_rule": "none automatic: after the analysis the study returns to the owner",
}
#: The candidate's policy source, fixed at registration (set by the registration commit).
CANDIDATE_DIGEST = ""


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


def build_card(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, policies: Sequence[Mapping[str, Any]],
               frozen: Mapping[str, str]) -> Dict[str, Any]:
    by_id = {p["id"]: p for p in policies}
    if sorted(by_id) != sorted((V2_ID, CANDIDATE_ID)):
        raise ValueError("the card's policies are baseline-v2 and the Sprint 22 candidate only")
    if (by_id[CANDIDATE_ID]["policy_source"]["sha256"] != CANDIDATE_DIGEST
            or by_id[V2_ID]["policy_source"]["sha256"] != V2_DIGEST):
        raise ValueError("a policy source is not the registered one")
    if sorted(frozen) != sorted(FROZEN_FILES):
        raise ValueError("the frozen file set differs from FROZEN_FILES")
    rows = games()
    if len(rows) != SESSION_CEILING:
        raise ValueError("the schedule is not exactly one game")
    budget = {"batch_sessions": len(rows), "ledger_base_session": LEDGER_BASE_SESSION,
              "sprint_session_cap": SESSION_CEILING}
    card = xp.build(CARD_ID, TEXTS, shoot_manifest, shoot_manifest_sha256, policies, CANDIDATE_ID, rows, RUNTIME,
                    WORKERS, budget)
    for row, game in zip(card["games"], rows):
        row["screen_position"] = game["screen_position"]
    card["screen"] = {"id": STUDY_ID, "stage": "probe", "rules": RULES, "rules_sha256": rules_digest(),
                      "frozen_files": dict(sorted(frozen.items())), "expected_sessions": list(EXPECTED_SESSIONS),
                      "structural_stops": list(STRUCTURAL_STOPS)}
    return card


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout: identity, rules, frozen files, policies, budget, schedule."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != CARD_ID or screen.get("id") != STUDY_ID:
        return ["not the Sprint 22 probe card"]
    if screen.get("rules") != RULES or screen.get("rules_sha256") != rules_digest():
        problems.append("the card's rules are not the frozen rules")
    if screen.get("structural_stops") != list(STRUCTURAL_STOPS):
        problems.append("the card's structural stops are not the frozen ones")
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
        problems.append("the card's candidate is not the Sprint 22 candidate")
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
    """Every session opened after 2795 must be the card's game (session 2795 + n plays position n) under the card's
    digest and the candidate's registered digest, opened once and closed with integrity ok, the state chain continuous,
    at most one session and none unclosed."""
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
                problems["S2"].append(f"session {session} is not under the Sprint 22 card")
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
    if any(int(s) not in EXPECTED_SESSIONS for s in opened):
        problems["S2"].append(f"sessions {sorted(opened)} are not the expected {list(EXPECTED_SESSIONS)}")
    return {"sessions": len(opened), "games": dict(sorted(seen.items())), "unclosed": unclosed, "problems": problems,
            "ok": not any(problems.values())}


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
    if by_faction != {faction: CANDIDATE_ID, 1 - faction: INERT_ID}:
        stops["S7"].append(f"the record's seats {sorted(by_faction.items())} are not the card's")
    if (record.get("scenario_id"), record.get("condition")) != (entry.get("scenario_id"), entry.get("condition")):
        stops["S7"].append("the record's scenario or condition is not the card's")
    harness = record.get("harness") or {}
    if harness.get("game_id") != entry.get("game_id") or harness.get("card") != CARD_ID:
        stops["S7"].append("the record is not this card's game")
    if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:
        stops["S7"].append("the record's candidate digest is not the registered one")
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
                           "edit that is not a registered transport edit")
    steps = timeline.get("steps") or []
    if len(steps) != record.get("steps") or t9cap.get("steps") != record.get("steps") \
            or explore.get("steps") != record.get("steps"):
        stops["S7"].append("the captures and the record disagree on the number of steps")
    if timeline.get("reconstructed_decisions") != len(steps):
        stops["S7"].append("not every candidate decision was reconstructed")
    candidate = next((s for s in seats if s.get("policy") == CANDIDATE_ID), {})
    seat_facts = (t9cap.get("seats") or {}).get(str(faction)) or {}
    if (seat_facts.get("moves") or {}).get("emitted") != int((candidate.get("actions_by_type") or {}).get("1", 0)):
        stops["S7"].append("the T9 capture and the record disagree on the seat's move orders")
    if explore.get("addon_errors"):
        stops["S7"].append(f"{len(explore['addon_errors'])} candidate add-on errors")
    if max_step != RULES["max_step"]:
        stops["S7"].append(f"max_step {max_step} is not the registered {RULES['max_step']}")
    return {code: found for code, found in stops.items() if found}


# ------------------------------------------------------------------------------------------------
# The registered-difference check (section 20) and the prefix check (SP)


def canonical(action: Mapping[str, Any]) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True, separators=(",", ":"), default=repr)


def unregistered_differences(baseline: Sequence[Mapping[str, Any]], live: Sequence[Mapping[str, Any]],
                             state_before: str, state_after: str, pair: Optional[Tuple[int, int]]) -> List[str]:
    """Differences between baseline-v2's reconstructed actions and the live candidate actions at one decision that are
    not a registered transport edit. Registered: the infantry's MOVE replaced by EMBARK (READY to EMBARK_REQUESTED);
    the carrier's MOVE removed when the decision ends in a hold state (EMBARK_REQUESTED, AT_DESTINATION,
    DISEMBARK_REQUESTED); the carrier's action replaced by, or a lone DISEMBARK appended for, the carrier when the
    decision issues disembark (to DISEMBARK_REQUESTED from CARRIER_RELEASED or AT_DESTINATION). Order of the remaining
    actions must be baseline-v2's."""
    problems: List[str] = []
    base = [dict(a) for a in baseline]
    out = [dict(a) for a in live]
    if pair is None:
        if [canonical(a) for a in base] != [canonical(a) for a in out]:
            problems.append("actions differ from baseline-v2 with no transport pair")
        return problems
    inf, car = pair
    others_base = [canonical(a) for a in base if a.get("obj_id") not in (inf, car)]
    others_live = [canonical(a) for a in out if a.get("obj_id") not in (inf, car)]
    if others_base != others_live:
        problems.append("an action of a unit outside the pair differs from baseline-v2")
    b_inf = [a for a in base if a.get("obj_id") == inf]
    l_inf = [a for a in out if a.get("obj_id") == inf]
    b_car = [a for a in base if a.get("obj_id") == car]
    l_car = [a for a in out if a.get("obj_id") == car]
    if [canonical(a) for a in b_inf] != [canonical(a) for a in l_inf]:
        trigger = (state_before == "READY" and state_after == "EMBARK_REQUESTED" and len(b_inf) == 1
                   and b_inf[0].get("type") == MOVE and len(l_inf) == 1 and l_inf[0].get("type") == EMBARK
                   and l_inf[0].get("obj_id") == inf and l_inf[0].get("target_obj_id") == car)
        if not trigger:
            problems.append("the infantry's action differs from baseline-v2 outside the registered embark")
    if [canonical(a) for a in b_car] != [canonical(a) for a in l_car]:
        withheld = [a for a in b_car if a.get("type") == MOVE]
        kept = [a for a in b_car if a.get("type") != MOVE]
        hold = state_after in ("EMBARK_REQUESTED", "AT_DESTINATION", "DISEMBARK_REQUESTED")
        hold_ok = hold and bool(withheld) and [canonical(a) for a in kept] == [canonical(a) for a in l_car]
        disembark_ok = (state_before in ("CARRIER_RELEASED", "AT_DESTINATION") and state_after == "DISEMBARK_REQUESTED"
                        and len(l_car) == 1 and l_car[0].get("type") == DISEMBARK and l_car[0].get("obj_id") == car
                        and l_car[0].get("target_obj_id") == inf and len(b_car) <= 1)
        if not (hold_ok or disembark_ok):
            problems.append("the carrier's action differs from baseline-v2 outside the registered hold or disembark")
    return problems


def prefix_problems(reference: Mapping[str, Any], live_actions: Sequence[str], baseline_actions: Sequence[str],
                    trigger_actions: Optional[str], pair: Optional[Tuple[int, int]]) -> List[str]:
    """SP. ``reference``: the registered trigger decision ``k`` and the digest of the registered trigger actions and
    pair (private). ``live_actions``/``baseline_actions``: digests of the live candidate's and the reconstructed
    baseline-v2's actions per decision from 0."""
    k = reference["trigger_decision"]
    if len(live_actions) <= k or len(baseline_actions) <= k:
        return [f"the game ended before decision {k}"]
    problems = []
    early = [j for j in range(k) if live_actions[j] != baseline_actions[j]]
    if early:
        problems.append(f"the candidate differs from baseline-v2 before decision {k} (first at {early[0]})")
    if trigger_actions != reference["trigger_actions"]:
        problems.append(f"the actions at decision {k} are not the registered trigger actions")
    if pair is None or list(pair) != list(reference["pair"]):
        problems.append("the transport pair is not the registered one")
    return problems


# ------------------------------------------------------------------------------------------------
# Mechanism endpoints (sections 13 to 19)


def accepted(feedback: Sequence[Mapping[str, Any]], action: Mapping[str, Any]) -> Optional[bool]:
    """True when exactly one echo of ``action`` (type, unit, target) carries no error, False when it carries an error,
    None when the echo is absent or ambiguous."""
    echoes = [f for f in feedback or () if isinstance(f.get("message"), Mapping)
              and all((f["message"]).get(k) == action.get(k) for k in ("type", "obj_id", "target_obj_id"))]
    if len(echoes) != 1:
        return None
    return not echoes[0].get("error")


def embark_endpoint(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """EMBARK succeeds only if: the order was emitted as registered and not refused (``response``), the infantry is
    represented aboard the selected carrier within the bound (``aboard_after`` steps), never in an inconsistent
    representation, and the carrier stayed present and controlled."""
    reasons = []
    if not facts.get("emitted"):
        reasons.append("embark not emitted")
    if facts.get("response") is False:
        reasons.append("embark refused")
    if facts.get("response") is None:
        reasons.append("no unique engine echo of the embark order")
    if facts.get("aboard_after") is None or facts["aboard_after"] > t2.BOUND:
        reasons.append("the infantry was not represented aboard the carrier within the bound")
    if facts.get("inconsistent_decisions"):
        reasons.append("inconsistent passenger representation")
    if not facts.get("carrier_present_and_controlled"):
        reasons.append("the carrier did not remain present and controlled")
    return {"ok": not reasons, "reasons": reasons}


def carry_endpoint(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """CARRY succeeds only if: after release a baseline-v2 move of the carrier was emitted and not refused, the carrier
    changed hex, the passenger stayed aboard (same carrier, never in ``operators``) at every decision until the
    disembark order, its position followed the carrier, no action was emitted for it while aboard, and the carrier
    stood on the registered destination (an objective) with no move path before the end."""
    reasons = []
    if not facts.get("move_emitted"):
        reasons.append("no carrier move after release")
    elif facts.get("move_response") is not True:
        reasons.append("the carrier's move after release was refused or not echoed")
    if not facts.get("carrier_moved"):
        reasons.append("the carrier never changed hex")
    if facts.get("passenger_breaks"):
        reasons.append("the passenger relation broke before disembark")
    if facts.get("position_mismatches"):
        reasons.append("the passenger's position did not follow the carrier")
    if facts.get("actions_for_passenger"):
        reasons.append("an action was emitted for the infantry while aboard")
    if not facts.get("destination_is_objective"):
        reasons.append("the destination is not an objective")
    if facts.get("arrival_decision") is None:
        reasons.append("the carrier did not reach the destination")
    return {"ok": not reasons, "reasons": reasons}


def stacking_endpoint(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """BLOCKED when the destination held the stacking limit of own ground units at the decision the candidate would
    have issued disembark (listing present), or at the end of the settle bound without a listing."""
    count = facts.get("ground_units_at_check")
    blocked = count is not None and count >= t2.STACK_LIMIT
    return {"blocked": blocked, "ground_units_at_check": count}


def disembark_endpoint(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """DISEMBARK succeeds only if: listed for the carrier with the selected infantry within the bound of arrival,
    emitted exactly once as listed, not refused, the passenger relation ended, the infantry is again an own ground unit
    (in ``operators``, not aboard) at the destination hex within the bound, and the carrier remained present."""
    reasons = []
    if facts.get("listed_after") is None or facts["listed_after"] > t2.BOUND:
        reasons.append("disembark not listed within the bound")
    if facts.get("emitted") != 1:
        reasons.append("disembark not emitted exactly once")
    if facts.get("response") is False:
        reasons.append("disembark refused")
    if facts.get("emitted") == 1 and facts.get("response") is None:
        reasons.append("no unique engine echo of the disembark order")
    if facts.get("ground_after") is None or facts["ground_after"] > t2.BOUND:
        reasons.append("the infantry did not return to the ground within the bound")
    if facts.get("ground_after") is not None and not facts.get("on_destination"):
        reasons.append("the infantry is not on the destination hex")
    if facts.get("inconsistent_decisions"):
        reasons.append("inconsistent representation during disembark")
    if not facts.get("carrier_present"):
        reasons.append("the carrier did not remain present")
    return {"ok": not reasons, "reasons": reasons}


def disposition(offline: Optional[str], problems: Sequence[str], embark: Optional[Mapping[str, Any]],
                carry: Optional[Mapping[str, Any]], stacking: Optional[Mapping[str, Any]],
                disembark: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """First match: an offline no-run disposition (PROTOCOL_AMBIGUOUS, NO_DETERMINISTIC_WITNESS); CAPTURE_INVALID
    (any structural, fidelity, prefix or registered-difference problem); DESTINATION_CAPACITY_BLOCKED (embark and carry
    succeeded and the destination was at the stacking limit); MECHANISM_REFUTED (any core transition failed);
    MECHANISM_SUPPORTED (every endpoint holds)."""
    if offline is not None:
        if offline not in (AMBIGUOUS, NO_WITNESS):
            raise ValueError("an offline disposition is PROTOCOL_AMBIGUOUS or NO_DETERMINISTIC_WITNESS")
        return {"disposition": offline}
    if problems or embark is None:
        return {"disposition": INVALID, "problems": list(problems)[:20]}
    if embark["ok"] and carry is not None and carry["ok"] and stacking is not None and stacking["blocked"]:
        return {"disposition": BLOCKED}
    failed = [name for name, e in (("embark", embark), ("carry", carry), ("disembark", disembark))
              if e is None or not e["ok"]]
    if failed:
        return {"disposition": REFUTED, "failed": failed}
    return {"disposition": SUPPORTED}


# ------------------------------------------------------------------------------------------------
# Public sanitization


def public_check(value: Any, private_values: Iterable[Any] = ()) -> List[str]:
    """Forbidden keys at any depth and any private value (unit ids, hexes) as a number, key or word."""
    return sc.privacy_problems(value, private_values)


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
