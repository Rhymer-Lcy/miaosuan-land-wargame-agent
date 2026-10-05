"""The registered Sprint 12 EXPLORATORY screen of ``t9-batch-capacity-v3`` (``docs/SPRINT12_V3_SCREEN.md``).

Approved proposal: ``docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md`` (draft companion
``evaluation/s12-batch-allocator-draft/draft.json``, kept as historical proposal evidence). This module freezes every
rule of the screen before its first engine session: the identities, the session ceiling, the four stage cards and how
each later card follows mechanically from the committed report of the stage before it, the primary and adverse
classifications, the replication triggers, the immediate stops S1 to S14 as they are decided from per-game facts, the
stage decisions, the final disposition, and the public sanitization of every report. The per-game facts themselves
are extracted from the private captures by :mod:`.s12_timeline`; the observers are :mod:`.s12_capture`.

Nothing here reads an engine, a private capture or the ledger by itself; callers pass the data in.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..decision import INERT_ID
from . import exploratory as xp
from . import manifest as mf
from .shoot_experiment import CANDIDATE_ID as V2_ID
from .shoot_experiment import KNOWN_CLASSES

SCREEN_ID = "s12-v3-screen"
SCHEMA_REPORT = "miaosuan-s12-stage-report/1"
SCHEMA_DISPOSITION = "miaosuan-s12-disposition/1"
V3_ID = "t9-batch-capacity-v3"
V3_DIGEST = "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8"
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2786
SESSION_CEILING = 12
WORKERS = 1

STAGE_ORDER = ("P1", "P2", "A1", "A2")
CARD_IDS = {"P1": "s12-v3-primary-1", "P2": "s12-v3-primary-2", "A1": "s12-v3-adverse-1", "A2": "s12-v3-adverse-2"}
STAGE_OF_CARD = {card: stage for stage, card in CARD_IDS.items()}
PRIMARY_SCENARIO = "2130511121"
#: A1's order: the configuration the end-of-game test was designed for first, then the one whose opening differs
#: from T9-v2's, then the one whose opening equals it.
ADVERSE = (("2120531121", "C3"), ("1930331196", "C2"), ("1930331196", "C3"))
#: (screen position, scenario, condition, red, blue) of every game the screen may play.
SCHEDULE = {
    "P1": ((1, PRIMARY_SCENARIO, "H1", V3_ID, V2_ID), (2, PRIMARY_SCENARIO, "H2", V2_ID, V3_ID),
           (3, PRIMARY_SCENARIO, "H1", V3_ID, V2_ID), (4, PRIMARY_SCENARIO, "H2", V2_ID, V3_ID)),
    "P2": ((5, PRIMARY_SCENARIO, "H1", V3_ID, V2_ID), (6, PRIMARY_SCENARIO, "H2", V2_ID, V3_ID)),
    "A1": ((7, "2120531121", "C3", INERT_ID, V3_ID), (8, "1930331196", "C2", V3_ID, INERT_ID),
           (9, "1930331196", "C3", INERT_ID, V3_ID)),
    "A2": ((10, "2120531121", "C3", INERT_ID, V3_ID), (11, "1930331196", "C2", V3_ID, INERT_ID),
           (12, "1930331196", "C3", INERT_ID, V3_ID)),
}

#: Every threshold of the screen, as approved in the draft (section 6) and nowhere else.
RULES = {
    "h1_coverage_floor": 0.6184027777777777,  # lowest red coverage of T9-v1's 15 registered H1 games
    "h2_margin_floor": 865,  # lowest blue margin of T9-v1's 15 registered H2 games
    "h1_collapse_below": -1195,  # lowest red margin of the 15 fresh Sprint 9 baseline-v2 C1 games
    "h2_collapse_below": 217,  # lowest blue margin of the same games
    "preserved_seat_average_at_least": 130.5,  # half of T9-v1's exploratory estimate 261.0
    "adverse": {
        "2120531121 C3": {"side": "blue", "occupy_all": 310, "margin_at_least": 559},
        "1930331196 C3": {"side": "blue", "occupy_all": 310, "attack_at_least": 78, "attack_at_most_regressed": 61},
        "1930331196 C2": {"side": "red", "occupy_all": 310, "attack_at_least": 16, "attack_at_most_regressed": 0},
    },
    "late_capture_window_steps": 144,  # 2120531121 C3 replication trigger: the final infantry hex time
    "max_step": 2880,
    "capacity": 4,
    "stage_cap": 3,
    "long_hold_flag_decisions": 1440,
    "staging_wait_flag_steps": 144,
    "latency_flag_p99_ms": 10.0,
    "latency_flag_max_ms": 5000.0,
    "queue_flag_above": {"H1": 791, "H2": 6},
}
#: Firing periods of the frozen full-step baseline-v2 diagnostic games of Sprint 10 (sessions 2776 and 2778).
REFERENCE_FIRE_DECISIONS = {"1930331196 C3": (742, 804, 841, 876), "1930331196 C2": (611,)}
#: Refusal classes known before the screen: baseline-v2's four (shoot experiment) and the duplicate occupation of
#: ``docs/REFUSAL_TAXONOMY.md``.
KNOWN_REFUSAL_CLASSES = tuple(tuple(c) for c in KNOWN_CLASSES) + ((5, 1804, "CantOccupyCauseAlreadyMy"),)

STOP_CODES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13", "S14")
#: Stops that are by definition a defect of the candidate: its own error or a broken invariant of its rule.
V3_DEFECT_STOPS = frozenset({"S5", "S8", "S9", "S10", "S11", "S12", "S14"})
STOP_TEXT = {
    "S1": "engine-installation integrity failure",
    "S2": "ledger inconsistency",
    "S3": "privacy exposure",
    "S4": "contract error or a game that did not complete",
    "S5": "candidate add-on error",
    "S6": "replay mismatch",
    "S7": "observer error or seat-local reconstruction differs from the live decision",
    "S8": "objective commitment above four",
    "S9": "staging endpoint above the staging cap",
    "S10": "staged move not a strict prefix of baseline-v2's path, or ending on an objective",
    "S11": "cross-objective redirection",
    "S12": "unrelated baseline-v2 action changed, or a move invented",
    "S13": "project-gate rejection, or an unexplained refusal class in a v3 seat",
    "S14": "structural design failure in 2120531121 C3",
}

#: Files whose normalised SHA-256 every stage card pins. After the first session none of them may change: the game
#: entry point and the stage runner refuse a card whose pins differ from the checkout.
FROZEN_FILES = (
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/s12_capture.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/t9_confirmation.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/t9_batch_replay.py",
    "src/miaosuan_agent/evaluation/game.py",
    "src/miaosuan_agent/experiments/t9_batch.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "scripts/build_s12_card.py",
    "scripts/run_s12_stage.py",
    "scripts/run_s12_game.py",
    "scripts/s12_screen_analysis.py",
    "scripts/run_evaluation.py",
    "tests/test_s12_screen.py",
    "tests/test_s12_capture.py",
    "tests/test_s12_timeline.py",
)


class NotPermitted(Exception):
    """A stage card that the committed reports do not (yet) permit."""


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def frozen_digests(repo: Path) -> Dict[str, str]:
    return {rel: normalized_sha256(repo / rel) for rel in FROZEN_FILES}


def rules_digest() -> str:
    return hashlib.sha256(json.dumps(RULES, sort_keys=True).encode("utf-8")).hexdigest()


def game_id(stage: str, position: int, scenario: str, condition: str) -> str:
    return f"{scenario}.{condition}.{CARD_IDS[stage]}.p{position:02d}"


def config_key(scenario: str, condition: str) -> str:
    return f"{scenario} {condition}"


def candidate_side(red: str, blue: str) -> str:
    if (red == V3_ID) == (blue == V3_ID):
        raise ValueError("a screen game plays v3 in exactly one seat")
    return "red" if red == V3_ID else "blue"


# ------------------------------------------------------------------------------------------------
# Primary rules (draft sections 6.2 and 6.3)


def t9v2_like(cell: str, facts: Mapping[str, Any], rules: Mapping[str, Any] = RULES) -> bool:
    if cell == "H1":
        return facts["coverage"] < rules["h1_coverage_floor"]
    if cell == "H2":
        return facts["margin"] < rules["h2_margin_floor"]
    raise ValueError(f"not a primary cell: {cell}")


def collapse(cell: str, facts: Mapping[str, Any], rules: Mapping[str, Any] = RULES) -> bool:
    key = {"H1": "h1_collapse_below", "H2": "h2_collapse_below"}[cell]
    return facts["margin"] < rules[key]


def primary_counts(games: Sequence[Mapping[str, Any]], rules: Mapping[str, Any] = RULES) -> Dict[str, Any]:
    h1 = [g for g in games if g["condition"] == "H1"]
    h2 = [g for g in games if g["condition"] == "H2"]
    if len(h1) + len(h2) != len(games):
        raise ValueError("a primary game is neither H1 nor H2")
    collapses = sum(collapse(g["condition"], g, rules) for g in games)
    like_h1 = sum(t9v2_like("H1", g, rules) for g in h1)
    like_h2 = sum(t9v2_like("H2", g, rules) for g in h2)
    average = None
    if h1 and h2:
        average = (sum(g["margin"] for g in h1) / len(h1) + sum(g["margin"] for g in h2) / len(h2)) / 2
    return {"games_h1": len(h1), "games_h2": len(h2), "collapse_games": collapses, "t9v2_like_h1": like_h1,
            "t9v2_like_h2": like_h2, "seat_average": average}


def interim_stop(games: Sequence[Mapping[str, Any]], rules: Mapping[str, Any] = RULES) -> bool:
    """After two games per seat: two or more collapse games, or all four games T9-v2-like."""
    counts = primary_counts(games, rules)
    if (counts["games_h1"], counts["games_h2"]) != (2, 2):
        raise ValueError("the interim rule needs exactly two games per seat")
    return counts["collapse_games"] >= 2 or counts["t9v2_like_h1"] + counts["t9v2_like_h2"] == 4


def primary_class(games: Sequence[Mapping[str, Any]], rules: Mapping[str, Any] = RULES) -> str:
    """After three games per seat: NOT_PRESERVED, PRESERVED_DIRECTIONALLY or AMBIGUOUS."""
    counts = primary_counts(games, rules)
    if (counts["games_h1"], counts["games_h2"]) != (3, 3):
        raise ValueError("the final rule needs exactly three games per seat")
    if counts["collapse_games"] >= 2 or (counts["t9v2_like_h1"] >= 2 and counts["t9v2_like_h2"] >= 2):
        return "NOT_PRESERVED"
    if (counts["collapse_games"] == 0 and counts["t9v2_like_h1"] + counts["t9v2_like_h2"] <= 1
            and counts["seat_average"] >= rules["preserved_seat_average_at_least"]):
        return "PRESERVED_DIRECTIONALLY"
    return "AMBIGUOUS"


# ------------------------------------------------------------------------------------------------
# Adverse rules (draft section 6.4)


def adverse_class(config: str, facts: Mapping[str, Any], rules: Mapping[str, Any] = RULES) -> str:
    limits = rules["adverse"][config]
    if config == "2120531121 C3":
        if facts["occupy"] < limits["occupy_all"]:
            return "NOT_REPAIRED"
        return "REPAIRED" if facts["margin"] >= limits["margin_at_least"] else "PARTIAL"
    if facts["occupy"] < limits["occupy_all"] or facts["attack"] <= limits["attack_at_most_regressed"]:
        return "REGRESSED"
    return "AVOIDED" if facts["attack"] >= limits["attack_at_least"] else "AMBIGUOUS"


FAVOURABLE = frozenset({"REPAIRED", "AVOIDED"})
UNFAVOURABLE = frozenset({"NOT_REPAIRED", "REGRESSED"})


def replication_triggers(config: str, facts: Mapping[str, Any], rules: Mapping[str, Any] = RULES) -> List[str]:
    """Why an A1 game is replicated in A2 (empty: it is not)."""
    reasons = []
    cls = adverse_class(config, facts, rules)
    if cls not in FAVOURABLE:
        reasons.append(f"class {cls}")
    if config == "2120531121 C3":
        last = facts.get("fifth_objective_last_to_own_step")
        if last is not None and last > rules["max_step"] - rules["late_capture_window_steps"]:
            reasons.append("the fifth objective last changed to own control within the final 144 steps")
    return reasons


def config_result(classes: Sequence[str]) -> str:
    if not classes:
        return "NOT_PLAYED"
    if all(c in FAVOURABLE for c in classes):
        return "FAVOURABLE"
    if all(c in UNFAVOURABLE for c in classes):
        return "UNFAVOURABLE"
    return "MIXED" if len(classes) > 1 else "IN_BETWEEN"


# ------------------------------------------------------------------------------------------------
# Stops


def stop_codes(game: Mapping[str, Any]) -> List[str]:
    """The immediate stops a game's facts trigger (S1 to S14), in code order."""
    return [code for code in STOP_CODES if (game.get("stops") or {}).get(code)]


def stage_stops(games: Sequence[Mapping[str, Any]], stage_level: Mapping[str, Any] = ()) -> List[Dict[str, Any]]:
    out = []
    for game in games:
        for code in stop_codes(game):
            out.append({"game": game["game_id"], "code": code, "text": STOP_TEXT[code]})
    for code, problems in dict(stage_level or {}).items():
        if problems:
            out.append({"game": None, "code": code, "text": STOP_TEXT[code]})
    return out


# ------------------------------------------------------------------------------------------------
# Stage decisions


def decide(stage: str, games: Sequence[Mapping[str, Any]], expected: int, earlier: Sequence[Mapping[str, Any]] = (),
           stage_level: Mapping[str, Any] = (), rules: Mapping[str, Any] = RULES) -> Dict[str, Any]:
    """The decision of a completed (or stopped) stage from its games' facts. ``expected`` is the number of games of
    the stage's card; ``earlier`` are the facts of P1's games when ``stage`` is P2 (the primary classification covers
    both); ``stage_level`` maps stop codes found outside the games (ledger, privacy) to their problems."""
    stops = stage_stops(list(earlier) + list(games), stage_level)
    out: Dict[str, Any] = {"stage": stage, "stops": stops}
    if stops:
        out.update(decision="STOP", kind="immediate", permits=None)
        return out
    if len(games) != expected:
        out.update(decision="STOP", kind="incomplete", permits=None,
                   reason=f"{len(games)} of {expected} games have facts")
        return out
    if stage == "P1":
        counts = primary_counts(games, rules)
        stop = interim_stop(games, rules)
        out.update(primary=counts, interim_stop=stop)
        if stop:
            out.update(decision="STOP", kind="tactical", permits=None)
        else:
            out.update(decision="CONTINUE", permits=CARD_IDS["P2"])
    elif stage == "P2":
        both = list(earlier) + list(games)
        counts = primary_counts(both, rules)
        cls = primary_class(both, rules)
        out.update(primary=counts, primary_class=cls)
        if cls == "NOT_PRESERVED":
            out.update(decision="STOP", kind="tactical", permits=None)
        else:
            out.update(decision="CONTINUE", permits=CARD_IDS["A1"])
    elif stage == "A1":
        rows, triggered = {}, []
        for game in games:
            config = config_key(game["scenario_id"], game["condition"])
            reasons = replication_triggers(config, game, rules)
            rows[config] = {"class": adverse_class(config, game, rules), "replication_triggers": reasons}
            if reasons:
                triggered.append(config)
        out.update(adverse=rows, replicate=[c for c in (config_key(*a) for a in ADVERSE) if c in triggered])
        if triggered:
            out.update(decision="CONTINUE", permits=CARD_IDS["A2"])
        else:
            out.update(decision="COMPLETE", permits=None)
    elif stage == "A2":
        out.update(adverse={config_key(g["scenario_id"], g["condition"]): {
            "class": adverse_class(config_key(g["scenario_id"], g["condition"]), g, rules)} for g in games})
        out.update(decision="COMPLETE", permits=None)
    else:
        raise ValueError(stage)
    return out


def disposition(reports: Mapping[str, Mapping[str, Any]], attribution: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """The screen's disposition from its committed stage reports (the first matching row of the draft's table).

    ``attribution`` maps a stop code outside ``V3_DEFECT_STOPS`` to ``"v3"`` when a committed investigation showed
    the stop to be a defect of v3; without it such a stop is not attributed to v3."""
    attribution = dict(attribution or {})
    stops = [s for stage in STAGE_ORDER for s in (reports.get(stage) or {}).get("decision", {}).get("stops", [])]
    if stops:
        codes = sorted({s["code"] for s in stops}, key=STOP_CODES.index)
        v3 = [c for c in codes if c in V3_DEFECT_STOPS or attribution.get(c) == "v3"]
        return {"disposition": "STRUCTURAL_FAILURE" if v3 else "SCREEN_INCOMPLETE", "stop_codes": codes}
    for stage in ("P1", "P2"):
        decision = (reports.get(stage) or {}).get("decision") or {}
        if decision.get("decision") == "STOP" and decision.get("kind") == "tactical":
            return {"disposition": "NOT_PRESERVED_IN_PRIMARY", "stage": stage}
    if "A1" not in reports:
        return {"disposition": "IN_PROGRESS"}
    a1 = reports["A1"]["decision"]
    if a1.get("decision") == "CONTINUE" and "A2" not in reports:
        return {"disposition": "IN_PROGRESS"}
    if a1.get("decision") == "STOP" or (reports.get("A2") or {}).get("decision", {}).get("decision") == "STOP":
        return {"disposition": "SCREEN_INCOMPLETE", "stop_codes": []}
    primary = reports["P2"]["decision"]["primary_class"]
    classes: Dict[str, List[str]] = {config_key(*a): [] for a in ADVERSE}
    for stage in ("A1", "A2"):
        for config, row in ((reports.get(stage) or {}).get("decision") or {}).get("adverse", {}).items():
            classes[config].append(row["class"])
    results = {config: config_result(values) for config, values in classes.items()}
    games = [g for stage in ("A1", "A2") for g in (reports.get(stage) or {}).get("games", [])]
    attributed = all(g.get("fifth_objective_attributed_to_v3_selection") for g in games
                     if config_key(g["scenario_id"], g["condition"]) == "2120531121 C3")
    blocks = sum(g.get("staging_blocks_to_end", 0) for stage in STAGE_ORDER
                 for g in (reports.get(stage) or {}).get("games", []))
    clean = all(r == "FAVOURABLE" for r in results.values()) and attributed and blocks == 0
    if clean and primary == "PRESERVED_DIRECTIONALLY":
        verdict = "READY_FOR_CONFIRMATORY_PROPOSAL"
    elif clean and primary == "AMBIGUOUS":
        verdict = "PROMISING_PRIMARY_UNRESOLVED"
    else:
        verdict = "NEEDS_REVISION"
    return {"disposition": verdict, "primary_class": primary, "adverse": results,
            "fifth_objective_attributed": attributed, "staging_blocks_to_end": blocks}


# ------------------------------------------------------------------------------------------------
# Stage cards


def stage_games(stage: str, configs: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    wanted = None if configs is None else set(configs)
    rows = []
    for position, scenario, condition, red, blue in SCHEDULE[stage]:
        if wanted is not None and config_key(scenario, condition) not in wanted:
            continue
        rows.append({"game_id": game_id(stage, position, scenario, condition), "scenario_id": scenario,
                     "condition": condition, "red": red, "blue": blue, "screen_position": position})
    return rows


def prerequisite(stage: str, reports: Mapping[str, Mapping[str, Any]]) -> Tuple[Optional[str], List[str]]:
    """``(previous stage, A2 configurations)`` if the committed reports permit ``stage``; raises NotPermitted."""
    if stage == "P1":
        return None, []
    previous = STAGE_ORDER[STAGE_ORDER.index(stage) - 1]
    report = reports.get(previous)
    if report is None:
        raise NotPermitted(f"{stage} needs the committed report of {previous}")
    decision = report.get("decision") or {}
    if decision.get("decision") != "CONTINUE" or decision.get("permits") != CARD_IDS[stage]:
        raise NotPermitted(f"the report of {previous} does not permit {CARD_IDS[stage]}")
    configs = list(decision.get("replicate") or []) if stage == "A2" else []
    if stage == "A2" and not configs:
        raise NotPermitted("the A1 report names no replication")
    return previous, configs


TEXTS = {
    "status": "EXPLORATORY SCREEN - REGISTERED STAGE CARD - NOT ELIGIBLE FOR BASELINE PROMOTION",
    "version": "t9-batch-capacity-v3, Sprint 12 screen (docs/SPRINT12_V3_SCREEN.md)",
    "mechanism": "baseline-v2 decides first; each objective's claimants are ranked together by free-flow arrival; a "
                 "mover or claimant that cannot arrive before the end holds no place; at most four counted places per "
                 "objective; overflow is staged on its own route at a hex holding fewer than three own ground units, "
                 "or withheld; no cross-objective move; every other baseline-v2 action unchanged",
    "controls": "historical only and descriptive: Sprint 9's registered T9-v1 and baseline-v2 games, the shoot "
                "experiment's group C, Sprint 8 and Sprint 10 games; no new control game; never pooled",
    "configurations": "P1 and P2: 2130511121 head to head, H1 and H2 alternating; A1: 2120531121 C3, 1930331196 C2, "
                      "1930331196 C3 against the inert control; A2: only the A1 configurations with a replication "
                      "trigger",
    "safety_checks": ["immediate stops S1 to S14 after every game (s12_screen.STOP_TEXT)",
                      "at most 12 sessions after closed session 2786; exclusive diagnostic sessions, one game at a time",
                      "every frozen implementation file pinned by digest; any difference refuses the stage and the game",
                      "the candidate's policy source pinned to 9b2003a7...; baseline-v2's to 7cbaf032..."],
    "intended_observations": ["Sprint 9's T9Capture unchanged, a compact v3 capture and a full-step private timeline "
                              "with seat-local reconstruction of baseline-v2 and v3 at every decision"],
    "next_step_rule": "mechanical: the committed stage report decides (s12_screen.decide); no rule may change after "
                      "the first session",
}


def build_card(stage: str, shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str,
               policies: Sequence[Mapping[str, Any]], frozen: Mapping[str, str],
               reports: Mapping[str, Mapping[str, Any]], report_digests: Mapping[str, str]) -> Dict[str, Any]:
    """The run card of ``stage``. Raises NotPermitted when the committed reports do not permit it."""
    previous, configs = prerequisite(stage, reports)
    games = stage_games(stage, configs if stage == "A2" else None)
    by_id = {p["id"]: p for p in policies}
    if by_id[V3_ID]["policy_source"]["sha256"] != V3_DIGEST or by_id[V2_ID]["policy_source"]["sha256"] != V2_DIGEST:
        raise ValueError("a policy source is not the frozen one")
    if sorted(frozen) != sorted(FROZEN_FILES):
        raise ValueError("the frozen file set differs from FROZEN_FILES")
    budget = {"batch_sessions": len(games), "ledger_base_session": LEDGER_BASE_SESSION,
              "sprint_session_cap": SESSION_CEILING}
    card = xp.build(CARD_IDS[stage], TEXTS, shoot_manifest, shoot_manifest_sha256, policies, V3_ID, games, RUNTIME,
                    WORKERS, budget)
    for row, game in zip(card["games"], games):
        row["screen_position"] = game["screen_position"]
    card["screen"] = {"id": SCREEN_ID, "stage": stage, "rules": RULES, "rules_sha256": rules_digest(),
                      "frozen_files": dict(sorted(frozen.items())),
                      "prerequisite": None if previous is None else {
                          "stage": previous, "report": report_path(previous),
                          "report_sha256": report_digests[previous]},
                      "replicated_configurations": configs}
    return card


def report_path(stage: str) -> str:
    return f"evaluation/{CARD_IDS[stage]}/report.json"


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout (frozen files, identities, budget fields)."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") not in STAGE_OF_CARD or screen.get("id") != SCREEN_ID:
        problems.append("not a Sprint 12 stage card")
        return problems
    if screen.get("rules") != RULES or screen.get("rules_sha256") != rules_digest():
        problems.append("the card's rules are not the frozen rules")
    current = frozen_digests(repo)
    changed = sorted(rel for rel, digest in (screen.get("frozen_files") or {}).items() if current.get(rel) != digest)
    if changed or sorted(screen.get("frozen_files") or {}) != sorted(FROZEN_FILES):
        problems.append(f"frozen implementation files differ from the card: {changed}")
    policies = card.get("policies") or {}
    if (policies.get(V3_ID, {}).get("policy_source", {}).get("sha256") != V3_DIGEST
            or policies.get(V2_ID, {}).get("policy_source", {}).get("sha256") != V2_DIGEST):
        problems.append("policy identities are not the frozen ones")
    budget = card.get("budget") or {}
    if (budget.get("ledger_base_session"), budget.get("sprint_session_cap")) != (LEDGER_BASE_SESSION, SESSION_CEILING):
        problems.append("budget is not the registered ceiling")
    return problems


# ------------------------------------------------------------------------------------------------
# Ledger (S1, S2)


def ledger_audit(ledger: Sequence[Mapping[str, Any]], cards: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Every session opened after the base must be a game of a committed stage card under that card's digest, opened
    once, closed with integrity ok, with the state chain continuous; at most the ceiling."""
    expected = {g["game_id"]: (card_id, mf.digest(card)) for card_id, card in cards.items() for g in card["games"]}
    problems: Dict[str, List[str]] = {"S1": [], "S2": []}
    opened: Dict[str, str] = {}
    ended: Dict[str, Mapping[str, Any]] = {}
    games: Dict[str, str] = {}
    previous = None
    for record in ledger:
        session = record.get("session")
        later = session is not None and int(session) > LEDGER_BASE_SESSION
        if later and record.get("event") == "session-open":
            harness = record.get("harness") or {}
            game = harness.get("game_id")
            if game not in expected:
                problems["S2"].append(f"session {session} plays a game outside the screen")
            elif harness.get("card") != expected[game][0] or harness.get("manifest_sha256") != expected[game][1]:
                problems["S2"].append(f"session {session} is not under its stage card")
            if game in games:
                problems["S2"].append(f"game opened twice (sessions {games[game]} and {session})")
            games[game] = session
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
    return {"sessions": len(opened), "games": dict(sorted(games.items())), "unclosed": unclosed,
            "problems": problems, "ok": not any(problems.values())}


# ------------------------------------------------------------------------------------------------
# Public sanitization (S3)

#: Keys that never appear in a public file at any depth.
FORBIDDEN_KEYS = frozenset({"obj_id", "unit", "units", "cur_hex", "hex", "move_path", "path", "coord", "coords",
                            "observation", "raw", "memory", "actions", "submitted", "target_obj_id", "actor",
                            "places_private", "selection_private"})
PUBLIC_GAME_FIELDS = (
    "game_id", "card", "screen_position", "scenario_id", "condition", "candidate_side", "status", "steps",
    "session", "margin", "scores", "attack", "occupy", "remain", "opponent_total", "coverage", "held_at_end",
    "objectives_at_end", "lost", "waiting_unit_steps", "waiting_max", "latency", "stops", "stop_details_count",
    "t9v2_like", "collapse", "adverse_class", "replication_triggers", "fifth_objective_last_to_own_step",
    "fifth_objective_attributed_to_v3_selection", "capture_order", "objectives", "places", "unproductive",
    "commitments", "staging", "staging_blocks_to_end", "holds", "fire", "occupation", "refusal_classes",
    "addon_changes", "premise", "flags", "consistency", "capture_digests", "observer_seconds",
)


def public_game(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """The public form of one game's facts: only whitelisted aggregate fields."""
    out = {key: facts[key] for key in PUBLIC_GAME_FIELDS if key in facts}
    problems = privacy_problems(out)
    if problems:
        raise ValueError(f"public game facts carry private content: {problems[:3]}")
    return out


def privacy_problems(value: Any, secrets: Iterable[Any] = (), path: str = "$") -> List[str]:
    """Forbidden keys anywhere in ``value``, and any of ``secrets`` (unit ids, hexes) as a number or inside a string."""
    secrets = {str(s) for s in secrets}
    problems: List[str] = []

    def walk(node: Any, where: str) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                if str(key) in FORBIDDEN_KEYS:
                    problems.append(f"{where}.{key}: forbidden key")
                if str(key) in secrets:
                    problems.append(f"{where}.{key}: secret as key")
                walk(item, f"{where}.{key}")
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                walk(item, f"{where}[{i}]")
        elif isinstance(node, bool) or node is None:
            return
        elif isinstance(node, (int, float)):
            if str(node) in secrets:
                problems.append(f"{where}: secret value")
        elif isinstance(node, str):
            for secret in secrets:
                if secret and secret in node.split() or node == secret:
                    problems.append(f"{where}: secret in text")

    walk(value, path)
    return problems


def report(stage: str, games: Sequence[Mapping[str, Any]], decision: Mapping[str, Any],
           inputs: Mapping[str, str]) -> Dict[str, Any]:
    """The public stage report (``evaluation/<card>/report.json``) from the games' public facts
    (``s12_timeline.public``), which are checked again here."""
    out = {"schema": SCHEMA_REPORT, "screen": SCREEN_ID, "stage": stage, "card": CARD_IDS[stage],
           "track": "EXPLORATORY", "eligible_for_promotion": False, "rules_sha256": rules_digest(),
           "games": [public_game(g) for g in games], "decision": dict(decision),
           "inputs": dict(sorted(inputs.items())),
           "note": "exploratory and directional; historical references are descriptive; nothing is promoted"}
    problems = privacy_problems(out)
    if problems:
        raise ValueError(f"the report carries private content: {problems[:3]}")
    return out


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
