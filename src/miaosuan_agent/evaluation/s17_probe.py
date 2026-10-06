"""The registered Sprint 17 first-divergence mechanism probe (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``): every rule.

Two exclusive engine sessions of the executable candidate ``t9-delayed-post-stage-any-v6``
(``experiments/t9_post_stage_v6.py``) against the inert control: 1930331196 C2 (candidate red) and 2120531121 C3
(candidate blue), serially, under the full-step capture of :mod:`.s17_capture`. Not a score screen, not a
confirmation, not a performance comparison; nothing is promoted and no score enters any rule.

This module fixes, before session 2794: the identities, the card and its pins, the session budget and the ledger audit,
the per-game structural checks, the prefix check against Sprint 16's frozen trajectories, the direct-fire endpoints of
1930331196 C2, the first-ownership and EARLY-PLACE BLOCK audit of 2120531121 C3, both retirement rules, the disposition
and the public sanitization. Nothing here reads an engine, a capture or the ledger by itself; callers pass the data in.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..decision import INERT_ID
from ..experiments import t9_batch as tb
from ..experiments import t9_post_stage_v6 as c6
from . import exploratory as xp
from . import manifest as mf
from . import s12_screen as sc

STUDY_ID = "s17-first-divergence-probe"
CARD_ID = "s17-post-stage-v6-probe-1"
SCHEMA = "miaosuan-s17-probe/1"
CANDIDATE_ID = c6.CANDIDATE_ID
#: The candidate's policy source (baseline-v2's set, the add-on wrapper, the frozen t9_batch, t9_redistribution and
#: t9_delayed modules, and t9_post_stage_v6), fixed before session 2794.
CANDIDATE_DIGEST = "b60e3812a8d43ffaf3a015c87783f7693d8e98894c4fb2363b90ea59dd306ec0"
V2_ID, V2_DIGEST = sc.V2_ID, sc.V2_DIGEST
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2793
SESSION_CEILING = 2
WORKERS = 1
C2 = "1930331196 C2"
C212 = "2120531121 C3"
CONFIGS = (C2, C212)
#: (position, scenario, condition, red, blue): Sprint 10's and Sprint 16's seats (C2 = the candidate red against the
#: inert blue control, C3 = the inert red control against the candidate blue), in the owner's order.
SCHEDULE = ((1, "1930331196", "C2", CANDIDATE_ID, INERT_ID), (2, "2120531121", "C3", INERT_ID, CANDIDATE_ID))
EXPECTED_SESSIONS = (2794, 2795)
#: Sprint 16's frozen v3 games of the same configurations: the reference trajectories of the prefix check.
SOURCE_CARD = "s16-v3-mechanism-capture-1"
SOURCE_GAMES = {C2: "1930331196.C2.s16-v3-mechanism-capture-1.p02",
                C212: "2120531121.C3.s16-v3-mechanism-capture-1.p03"}
MOVE, SHOOT = 1, 2
FORMS = ("KEEP", "REDIRECT", "STAGE", "WITHHOLD")

#: Every threshold and anchor, fixed before session 2794 (values from Sprint 16's committed public files).
RULES: Dict[str, Any] = {
    "max_step": 2880,
    "capacity": 4,
    # Sprint 16's target first divergence on the frozen v3 trajectory: decision and number of redirected vehicles
    "first_divergence": {C2: 421, C212: 361},
    "first_divergence_redirected_vehicles": {C2: 2, C212: 2},
    # 1930331196 C2: the decisions of v3's two direct-fire orders (both accepted) in Sprint 16's game
    "protected_fire_decisions": [611, 686],
    # 2120531121 C3: the problem objective (Sprint 11's label) and v3's first ownership of it in Sprint 16's game
    "problem_objective": "80-point objective A",
    "first_ownership_deadline": 564,
    "early_place_blocks_allowed": 0,
}
STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7", "SP")
STOP_MEANING = {
    "S1": "engine-installation integrity failure (session close or the ledger's state chain)",
    "S2": "ledger inconsistency, a wrong card or digest, an unclosed session or more than two sessions",
    "S3": "privacy exposure: a file outside the ignored tree appeared during the game",
    "S4": "a contract error, a wrong margin identity or a game that did not complete",
    "S6": "a replay mismatch",
    "S7": "capture or reconstruction failure: an observer error, a missing or digest-mismatched capture, a live decision "
          "or memory that differs from the seat-local reconstruction, a candidate add-on error, disagreeing counts, a "
          "wrong scenario, condition or seat, or a max_step other than 2,880",
    "SP": "prefix failure: the candidate did not reproduce frozen v3 before the registered first divergence, its memory "
          "differs from the Sprint 16 corrected-memory chain, or the first divergence is not the registered redirect",
}
C2_CLASSES = ("C2_MECHANISM_PRESERVED", "C2_FIRE_MECHANISM_LOST")
C212_CLASSES = ("C3_212_MECHANISM_PRESERVED", "C3_212_MECHANISM_LOST")
DISPOSITIONS = ("CAPTURE_INVALID", "MECHANISM_REFUTED_BOTH", "MECHANISM_REFUTED_C2", "MECHANISM_REFUTED_212",
                "MECHANISM_CROSSED_WITHOUT_KNOWN_REGRESSION")

#: Files whose normalised SHA-256 the card pins. None may change after the registration: the game entry point and the
#: runner refuse a card whose pins differ from the checkout. The stage-1 allocator (t9_batch.py) is among them.
FROZEN_FILES = (
    "src/miaosuan_agent/experiments/t9_post_stage_v6.py",
    "src/miaosuan_agent/experiments/t9_delayed.py",
    "src/miaosuan_agent/experiments/t9_redistribution.py",
    "src/miaosuan_agent/experiments/t9_batch.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "src/miaosuan_agent/evaluation/s17_probe.py",
    "src/miaosuan_agent/evaluation/s17_capture.py",
    "src/miaosuan_agent/evaluation/s16_shadow.py",
    "src/miaosuan_agent/evaluation/s16_mechanism.py",
    "src/miaosuan_agent/evaluation/s15_delayed.py",
    "src/miaosuan_agent/evaluation/s14_design.py",
    "src/miaosuan_agent/evaluation/s13_diagnosis.py",
    "src/miaosuan_agent/evaluation/s12_capture.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/t9_confirmation.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/game.py",
    "scripts/build_s17_card.py",
    "scripts/run_s17_game.py",
    "scripts/run_s17_probe.py",
    "scripts/s17_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_s12_stage.py",
    "scripts/s14_design_replay.py",
    "tests/test_t9_post_stage_v6.py",
    "tests/test_s17_probe.py",
)

TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED MECHANISM PROBE - NOT A SCORE SCREEN - NOT ELIGIBLE FOR PROMOTION",
    "version": "t9-delayed-post-stage-any-v6, Sprint 17 first-divergence probe (docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md)",
    "mechanism": "the executable delayed-post-stage-any v6 candidate plays its seat: frozen stage 1, Sprint 16's corrected "
                 "deferred-history memory, the frozen post-stage-any trigger, Sprint 14's feasible-value redirect, at "
                 "most one redirect per memory episode; it is expected to equal the frozen stage-1 allocator until the "
                 "registered first divergences (decision 421 in 1930331196 C2, decision 361 in 2120531121 C3)",
    "controls": "none: the inert control seat; no score is compared and nothing is pooled",
    "configurations": "1930331196 C2 and 2120531121 C3 against the inert control, one game each, serially",
    "safety_checks": ["structural stops after every game (S1, S2, S3, S4, S6, S7 and the prefix check SP)",
                      "exactly two sessions after closed session 2793; exclusive diagnostic sessions, one at a time",
                      "every frozen implementation file pinned by digest; any difference refuses the card",
                      "the candidate's policy source pinned to b60e3812...; baseline-v2's to 7cbaf032..."],
    "intended_observations": ["Sprint 9's T9Capture, the exploratory capture and the Sprint 17 full-step timeline with "
                              "the seat-local reconstruction of baseline-v2, the stage-1 allocator and the candidate, "
                              "with its memory chain, at every decision"],
    "next_step_rule": "none automatic: after the analysis the study returns to the owner",
}


# ------------------------------------------------------------------------------------------------
# Identities, card, budget


def normalized_sha256(path: Path) -> str:
    return sc.normalized_sha256(path)


def frozen_digests(repo: Path) -> Dict[str, str]:
    return {rel: normalized_sha256(repo / rel) for rel in FROZEN_FILES}


def rules_digest() -> str:
    return hashlib.sha256(json.dumps(RULES, sort_keys=True).encode("utf-8")).hexdigest()


def config_key(scenario: str, condition: str) -> str:
    return f"{scenario} {condition}"


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
               frozen: Mapping[str, str], reference: Mapping[str, Any]) -> Dict[str, Any]:
    """The Sprint 17 run card. ``reference``: Sprint 16's card id and canonical digest (the prefix trajectories)."""
    by_id = {p["id"]: p for p in policies}
    if sorted(by_id) != sorted((V2_ID, CANDIDATE_ID)):
        raise ValueError("the card's policies are baseline-v2 and the Sprint 17 candidate only")
    if (by_id[CANDIDATE_ID]["policy_source"]["sha256"] != CANDIDATE_DIGEST
            or by_id[V2_ID]["policy_source"]["sha256"] != V2_DIGEST):
        raise ValueError("a policy source is not the registered one")
    if sorted(frozen) != sorted(FROZEN_FILES):
        raise ValueError("the frozen file set differs from FROZEN_FILES")
    rows = games()
    budget = {"batch_sessions": len(rows), "ledger_base_session": LEDGER_BASE_SESSION,
              "sprint_session_cap": SESSION_CEILING}
    card = xp.build(CARD_ID, TEXTS, shoot_manifest, shoot_manifest_sha256, policies, CANDIDATE_ID, rows, RUNTIME,
                    WORKERS, budget)
    for row, game in zip(card["games"], rows):
        row["screen_position"] = game["screen_position"]
    card["screen"] = {"id": STUDY_ID, "stage": "probe", "rules": RULES, "rules_sha256": rules_digest(),
                      "frozen_files": dict(sorted(frozen.items())), "expected_sessions": list(EXPECTED_SESSIONS),
                      "structural_stops": list(STRUCTURAL_STOPS), "prefix_reference": dict(reference)}
    return card


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout: identity, rules, frozen files, policies, budget, schedule."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != CARD_ID or screen.get("id") != STUDY_ID:
        return ["not the Sprint 17 probe card"]
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
        problems.append("the card's candidate is not the Sprint 17 candidate")
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
    """Every session opened after 2793 must be the next game of the card in schedule order (session 2793 + n plays
    position n) under the card's digest, opened once and closed with integrity ok, the state chain continuous, at most
    two sessions and none unclosed."""
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
                problems["S2"].append(f"session {session} is not under the Sprint 17 card")
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
    return {"sessions": len(opened), "games": dict(sorted(seen.items())), "unclosed": unclosed, "problems": problems,
            "ok": not any(problems.values())}


def structural_stops(stops: Mapping[str, Sequence[str]]) -> List[str]:
    return [code for code in STRUCTURAL_STOPS if stops.get(code)]


# ------------------------------------------------------------------------------------------------
# Per-game structural checks (S1, S4, S6, S7) from a record and its captures


def game_stops(entry: Mapping[str, Any], record: Mapping[str, Any], t9cap: Mapping[str, Any],
               explore: Mapping[str, Any], timeline: Mapping[str, Any], max_step: Any,
               capture_digests: Mapping[str, Tuple[Optional[str], Optional[str]]]) -> Dict[str, List[str]]:
    """The structural findings of one game. ``max_step``: the value the seat observed; ``capture_digests``: capture
    name -> (digest in the record, digest of the file)."""
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
# Prefix check (SP) against Sprint 16's frozen trajectory


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")
                          ).hexdigest()


def actions_digest(actions: Sequence[Mapping[str, Any]]) -> str:
    """Emitted actions in emission order (content and order)."""
    return canonical_sha256([{str(k): v for k, v in dict(a).items()} for a in actions])


def memory_digest(addon_memory: Sequence[Sequence[int]]) -> str:
    return canonical_sha256([list(pair) for pair in addon_memory or ()])


def prefix_problems(reference: Mapping[str, Any], live_actions: Sequence[str], live_memory: Sequence[str],
                    live_changed: Sequence[Any], live_redirects: Mapping[str, Any]) -> List[str]:
    """SP for one game. ``reference`` (frozen before session 2794 from Sprint 16's v3 game and its corrected-memory
    chain): ``divergence`` k, ``v3_actions`` (digests of v3's emitted actions at decisions 0..k), ``expected_actions``
    (the digest of the registered first-divergence actions at k), ``memory_in`` (digests of the corrected-memory chain
    before decisions 0..k+1), ``changed`` (the units whose actions differ at k) and ``redirects`` (unit -> objective and
    route at k). ``live_*``: the same quantities read from the new game (actions and memory per decision from 0)."""
    problems = []
    k = reference["divergence"]
    if len(live_actions) <= k or len(live_memory) <= k + 1:
        return [f"the game ended before decision {k + 1}"]
    early = [j for j in range(k) if live_actions[j] != reference["v3_actions"][j]]
    if early:
        problems.append(f"the candidate's actions differ from frozen v3 before decision {k} (first at {early[0]})")
    if live_actions[k] == reference["v3_actions"][k]:
        problems.append(f"no divergence at decision {k}")
    elif live_actions[k] != reference["expected_actions"]:
        problems.append(f"the divergence at decision {k} is not the registered first-divergence decision")
    memory = [j for j in range(k + 2) if live_memory[j] != reference["memory_in"][j]]
    if memory:
        problems.append(f"the candidate's memory differs from the corrected-memory chain (first before decision "
                        f"{memory[0]})")
    if sorted(map(str, live_changed)) != sorted(map(str, reference["changed"])):
        problems.append("the units changed at the first divergence are not the registered ones")
    if {str(u): r for u, r in dict(live_redirects).items()} != {str(u): r for u, r in reference["redirects"].items()}:
        problems.append("the first divergence's redirects (unit, objective, route) are not the registered ones")
    return problems


# ------------------------------------------------------------------------------------------------
# 1930331196 C2: direct-fire endpoints


def fire_endpoint(k: int, unit: Any, listed_types: Iterable[int], orders: Sequence[Tuple[Mapping[str, Any], str]]
                  ) -> Dict[str, Any]:
    """The protected direct-fire mechanism at decision ``k`` for the protected unit: a direct-fire action (type 2)
    listed for the unit in the seat's own observation, a direct-fire order by the unit emitted at ``k``, and the
    engine's response ``accepted``. ``orders``: (emitted action, response) of the seat at ``k``."""
    mine = [(a, r) for a, r in orders if a.get("type") == SHOOT and a.get("obj_id") == unit]
    listed = SHOOT in {int(t) for t in listed_types}
    out = {"decision": k, "listed": listed, "emitted": bool(mine), "accepted": any(r == "accepted" for _, r in mine),
           "orders_by_unit": len(mine)}
    out["preserved"] = out["listed"] and out["emitted"] and out["accepted"]
    return out


def classify_c2(endpoints: Mapping[int, Mapping[str, Any]], rules: Mapping[str, Any] = RULES) -> Dict[str, Any]:
    """C2 retirement: RETIRED BY C2 when either protected mechanism (611, 686) is not listed, not emitted or not
    accepted. Later shots, other units' shots, total attack and score never rescue it."""
    decisions = list(rules["protected_fire_decisions"])
    if sorted(int(k) for k in endpoints) != sorted(decisions):
        raise ValueError("the C2 endpoints are not the registered decisions")
    lost = []
    for k in decisions:
        e = endpoints[k]
        missing = [name for name in ("listed", "emitted", "accepted") if not e[name]]
        if missing:
            lost.append(f"decision {k}: not {', not '.join(missing)}")
    if lost:
        return {"class": C2_CLASSES[1], "retired": True, "reasons": lost}
    return {"class": C2_CLASSES[0], "retired": False, "reasons": []}


# ------------------------------------------------------------------------------------------------
# 2120531121 C3: first ownership and the EARLY-PLACE BLOCK audit


def first_ownership(flags_by_decision: Sequence[Mapping[Any, Any]], coord: Any, faction: int) -> Optional[int]:
    """The first decision whose observed state shows ``coord`` own (Sprint 16's definition), or None."""
    return next((k for k, flags in enumerate(flags_by_decision) if flags.get(coord) == faction), None)


def form(baseline_path: Optional[Sequence[Any]], emitted_path: Optional[Sequence[Any]],
         redirected: bool) -> str:
    """The candidate's actual form for one claimant: KEEP (baseline-v2's move emitted unchanged), REDIRECT, STAGE (a
    strict prefix of baseline-v2's path) or WITHHOLD (no move emitted)."""
    if redirected:
        return "REDIRECT"
    if emitted_path is None:
        return "WITHHOLD"
    if baseline_path is not None and tuple(emitted_path) == tuple(baseline_path):
        return "KEEP"
    return "STAGE"


def early_place_rows(claimants: Sequence[Mapping[str, Any]], counted: int, early_counted: int,
                     selected: Iterable[Any], capacity: int = RULES["capacity"]) -> List[Dict[str, Any]]:
    """The EARLY-PLACE BLOCK test at one decision for one objective (the problem objective).

    ``claimants``: every unit for which baseline-v2 emits a move to the objective at this decision (stage-1
    claimants), each {unit, feasible (can arrive before the end), key (v3's rank key), form}; ``counted``: the
    objective's counted incumbents before stage 1 (own ground units standing on it plus counted movers);
    ``early_counted``: how many of those counted places belong to the two decision-361 redirected units; ``selected``:
    the units stage 1 actually gave a place.

    A claimant is EARLY-PLACE BLOCKED when (1) it is selectable (feasible) under v3's frozen ranking, (2) it does not
    receive a place, and (3) with only the early places removed (``counted - early_counted``) v3's ranking gives it a
    place. Raises when the ranking does not reproduce ``selected`` (the audit then does not describe the candidate)."""
    if not 0 <= early_counted <= counted:
        raise ValueError("early places must be among the counted places")
    ranked = sorted((c for c in claimants if c["feasible"]), key=lambda c: tuple(c["key"]))
    free = max(capacity - counted, 0)
    free_without = max(capacity - (counted - early_counted), 0)
    actual = {c["unit"] for c in ranked[:free]}
    if actual != set(selected):
        raise ValueError("v3's ranking does not reproduce stage 1's selection")
    without = {c["unit"] for c in ranked[:free_without]}
    position = {c["unit"]: i + 1 for i, c in enumerate(ranked)}
    rows = []
    for c in sorted(claimants, key=lambda c: tuple(c["key"])):
        blocked = c["feasible"] and c["unit"] not in actual and c["unit"] in without
        rows.append({"unit": c["unit"], "feasible": c["feasible"], "rank": position.get(c["unit"]),
                     "placed": c["unit"] in actual, "placed_without_early_places": c["unit"] in without,
                     "form": c["form"], "early_place_block": blocked})
    return rows


def classify_212(first_own: Optional[int], blocks: int, rules: Mapping[str, Any] = RULES) -> Dict[str, Any]:
    """212 retirement: RETIRED BY 212 when (A) the problem objective is not first owned by decision 564, or (B) at
    least one EARLY-PLACE BLOCK occurs before its first ownership. Score never overrides it."""
    reasons = []
    if first_own is None or first_own > rules["first_ownership_deadline"]:
        reasons.append(f"A: the problem objective is not first owned by decision {rules['first_ownership_deadline']}")
    if blocks > rules["early_place_blocks_allowed"]:
        reasons.append(f"B: {blocks} EARLY-PLACE BLOCK events before first ownership")
    if reasons:
        return {"class": C212_CLASSES[1], "retired": True, "reasons": reasons}
    return {"class": C212_CLASSES[0], "retired": False, "reasons": []}


# ------------------------------------------------------------------------------------------------
# Disposition


def disposition(problems: Sequence[str], c2: Optional[Mapping[str, Any]], c212: Optional[Mapping[str, Any]]
                ) -> Dict[str, Any]:
    """First match: CAPTURE_INVALID (any structural, fidelity or reconstruction problem, or a configuration without a
    valid game), MECHANISM_REFUTED_BOTH, MECHANISM_REFUTED_C2, MECHANISM_REFUTED_212, else
    MECHANISM_CROSSED_WITHOUT_KNOWN_REGRESSION."""
    if problems or c2 is None or c212 is None:
        missing = [name for name, row in ((C2, c2), (C212, c212)) if row is None]
        return {"disposition": DISPOSITIONS[0], "problems": list(problems)[:20], "configurations_missing": missing}
    if c2["class"] not in C2_CLASSES or c212["class"] not in C212_CLASSES:
        raise ValueError("an unknown class")
    c2_bad, b_bad = c2["class"] == C2_CLASSES[1], c212["class"] == C212_CLASSES[1]
    if c2_bad and b_bad:
        return {"disposition": DISPOSITIONS[1]}
    if c2_bad:
        return {"disposition": DISPOSITIONS[2]}
    if b_bad:
        return {"disposition": DISPOSITIONS[3]}
    return {"disposition": DISPOSITIONS[4]}


# ------------------------------------------------------------------------------------------------
# Public sanitization


def public_check(value: Any, private_values: Iterable[Any] = ()) -> List[str]:
    """Forbidden keys at any depth and any private value (unit ids, hexes) as a number, key or word."""
    return sc.privacy_problems(value, private_values)


def forbidden_identity(text: str) -> bool:
    """Public Sprint 17 files never name the frozen stage-1 allocator's identity or digest (its whitelist)."""
    return tb.CANDIDATE_ID in text or sc.V3_DIGEST in text


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def private_units(rows: Iterable[Mapping[str, Any]]) -> Set[Any]:
    return {r["unit"] for r in rows if "unit" in r}
