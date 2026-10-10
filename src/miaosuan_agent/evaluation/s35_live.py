"""Sprint 35 live evaluation rules (``docs/SPRINT35_COALITION_AGENT.md`` section 11), frozen before any session.

A PROPOSAL until the owner authorizes the budget: at most 48 sessions, 2827 to 2874, positions 1 to 48 (position n opens
session 2826 + n), one game per exclusive session, serially, in four batches.

Stage A (positions 1 to 40): in each of five scenarios, the Sprint 35 candidate and a fresh Sprint 34 control (the
frozen Sprint 34 live candidate) each play red against ``baseline-v2`` (condition ``H1``) and blue against it (``H2``);
batch A1 is the first repetition of the twenty configurations, A2 the second. Inside a repetition the four games of a
scenario are ordered so that neither policy nor seat always comes first (``ORDER``), and the second repetition uses the
other order. Stage B (positions 41 to 48): the candidate against the inert control, red (``C2``) and blue (``C3``), in
2120531121 and 1930331196; batch B1 the first repetition, B2 the second. Stage B runs only when the A2 gate is open.

Seeds: the card's fixed global seed is set before every game, as in every earlier card; it is not claimed to pair the
engine's randomness across games (Sprint 26's prefix check failed on stochastic games), so the comparisons are between
independent stochastic runs grouped by scenario and seat.

References (``evaluation/s35-coalition-agent/references.json``): ``baseline-v2``'s own games, same scenario, condition and
seat, 15 per configuration (the rule of Sprint 34, plus 2010431153). ``z = (margin - reference mean) / reference SD``.

Structural stops (either policy's game; any closes the study at once; ``S35_LIVE_INVALID``): S1 to S6 as in Sprint 34
(``s34_live.structural``: incomplete game, ledger, tracked file or source change, contract or observer error,
reconstruction mismatch or more than 1% fallbacks, more than 2% refused unit actions or more than 5 refused non-shoot
actions); S7 decision latency p99 above 200 ms or maximum above 3,000 ms (Sprint 34's live p99 at most 24.77 ms, maximum
988.354 ms); S8 any damaging judged attack by the policy on its own units (Sprint 34: none in 24 games); S9 the policy's
memory larger than 200,000 bytes of canonical JSON at any decision (bounded by design to a few thousand).

Severe harm (candidate games only; closes the gate; ``S35_INTEGRATED_REJECT``): after A1, a candidate margin more than
three reference SDs below the reference minimum (Sprint 34's rule); after A2, a configuration whose two candidate
margins are both below the reference minimum (about 1 in 256 under ``baseline-v2``'s own distribution); at any batch, a
candidate ground unit waiting 600 or more consecutive steps in front of a full hex (Sprint 34's candidate: 0 waits in 24
games; ``baseline-v2`` opponents up to 1,798). The A2 gate also closes when ``Dbar`` (below) is at or below -0.5.

Comparison: for each Stage A configuration (scenario and seat) ``d = mean z of the candidate - mean z of the control``
(two games each), ``Dbar`` the mean of the ten ``d``, ``d_s`` the mean of a scenario's two ``d``.

Dispositions (first match): ``S35_LIVE_INVALID``; ``S35_INTEGRATED_REJECT`` (severe harm; ``Dbar`` at or below -0.5;
Stage B objective score below the reference minimum in three or more games; Stage B remaining-force score below the
reference minimum in three or more games); ``S35_INTEGRATED_PROMISING`` (both stages complete, ``Dbar`` at least +0.5,
``d_s`` positive in at least four of the five scenarios, no ``d_s`` at or below -1.0, the candidate's mean ``z`` over
its twenty Stage A games at least +0.5, no Stage B objective score below the reference minimum, and a Stage B margin at
least the reference minimum minus 50 in at least seven of eight games); otherwise ``S35_INTEGRATED_INCONCLUSIVE``.
Two games per configuration are exploratory: no claim of statistical superiority, and nothing is promoted.
"""

from __future__ import annotations

import collections
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from . import s34_live as s34

STUDY_ID = "s35-coalition-live"
CARD_ID = "s35-coalition-live-1"
RULES_ID = "s35-coalition-live-rules-1"
LEDGER_BASE_SESSION = 2826
SESSION_CAP = 48
V2 = s34.V2
INERT = s34.INERT
S34_CONTROL = "s34-integrated-mission-orchestrator-1"
STAGE_A_SCENARIOS = ("2130511121", "2120531121", "1930331196", "1910631192", "2010431153")
STAGE_B_SCENARIOS = ("2120531121", "1930331196")
BATCHES = {"A1": range(1, 21), "A2": range(21, 41), "B1": range(41, 45), "B2": range(45, 49)}
CANDIDATE_SIDE = s34.CANDIDATE_SIDE
#: Orders of a scenario's four Stage A games: (policy tag, condition).
ORDER = {0: (("s35", "H1"), ("s34", "H1"), ("s34", "H2"), ("s35", "H2")),
         1: (("s34", "H1"), ("s35", "H1"), ("s35", "H2"), ("s34", "H2"))}
LATENCY_P99_MS = 200.0
LATENCY_MAX_MS = 3000.0
MEMORY_BYTES = 200_000
DEADLOCK_WAIT = 600
SEVERE_SD = s34.SEVERE_SD
REJECT_DBAR, PROMISING_DBAR, PROMISING_ZBAR = -0.5, 0.5, 0.5
COLLAPSE_DS = -1.0
STAGE_B_MARGIN_SLACK = s34.STAGE_B_MARGIN_SLACK
DISPOSITIONS = ("S35_ENGINEERING_BLOCKED", "S35_LIVE_NOT_AUTHORIZED", "S35_LIVE_INVALID", "S35_INTEGRATED_REJECT",
                "S35_INTEGRATED_INCONCLUSIVE", "S35_INTEGRATED_PROMISING")


def schedule(candidate: str) -> List[Dict[str, Any]]:
    ids = {"s35": candidate, "s34": S34_CONTROL}
    games = []
    position = 0
    for repetition in (1, 2):
        for index, sid in enumerate(STAGE_A_SCENARIOS):
            order = ORDER[(index + repetition - 1) % 2]
            for tag, condition in order:
                position += 1
                policy = ids[tag]
                games.append({"position": position, "condition": condition, "scenario_id": sid,
                              "repetition": repetition, "tag": tag, "policy": policy,
                              "red": policy if condition == "H1" else V2, "blue": V2 if condition == "H1" else policy})
    for repetition in (1, 2):
        for sid in STAGE_B_SCENARIOS:
            for condition in ("C2", "C3"):
                position += 1
                games.append({"position": position, "condition": condition, "scenario_id": sid,
                              "repetition": repetition, "tag": "s35", "policy": candidate,
                              "red": candidate if condition == "C2" else INERT,
                              "blue": INERT if condition == "C2" else candidate})
    for g in games:
        g["game_id"] = f"{g['scenario_id']}.{g['condition']}.{g['tag']}.{CARD_ID}.p{g['position']:02d}"
        g["session"] = LEDGER_BASE_SESSION + g["position"]
        g["batch"] = next(b for b, r in BATCHES.items() if g["position"] in r)
        g["stage"] = g["batch"][0]
    return games


def rules_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------------------------------------ facts
def game_facts(game: Mapping[str, Any], record: Mapping[str, Any], compact: Mapping[str, Any],
               references: Mapping[str, Any]) -> Dict[str, Any]:
    """Sprint 34's per-game facts (``s34_live.game_facts``) for the policy under test, plus its tag and the memory and
    friendly-fire figures Sprint 35's stops read."""
    facts = s34.game_facts(game, record, compact, references)
    checks = compact.get("checks") or {}
    facts.update(tag=game["tag"], policy=game["policy"], memory_bytes_max=checks.get("memory_bytes_max", 0))
    facts["reference"]["remain"] = s34.reference(references, game)["remain"]
    return facts


def structural(facts: Mapping[str, Any]) -> Dict[str, List[str]]:
    stops = s34.structural(facts)

    def add(code: str, text: str) -> None:
        stops.setdefault(code, []).append(text)

    if facts.get("latency_ms_p99", 0) > LATENCY_P99_MS or facts.get("latency_ms_max", 0) > LATENCY_MAX_MS:
        add("S7", f"latency p99 {facts.get('latency_ms_p99')} ms, maximum {facts.get('latency_ms_max')} ms")
    if (facts.get("fire") or {}).get("friendly_damage", 0) > 0:
        add("S8", f"{facts['fire']['friendly_damage']} damaging attacks on own units")
    if facts.get("memory_bytes_max", 0) > MEMORY_BYTES:
        add("S9", f"memory {facts['memory_bytes_max']} bytes")
    return stops


def ledger_audit(records, games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Sprint 34's audit with Sprint 35's base session."""
    opened: Dict[int, Mapping[str, Any]] = {}
    closed: Dict[int, Mapping[str, Any]] = {}
    for r in records:
        if r.get("session") is None:
            continue
        session = int(r["session"])
        if session <= LEDGER_BASE_SESSION:
            continue
        if r.get("event") == "session-open":
            opened[session] = r
        elif r.get("event") == "session-close":
            closed[session] = r
    problems: List[str] = []
    sessions = sorted(opened)
    expected = [g["session"] for g in games][:len(sessions)]
    if sessions != expected:
        problems.append(f"sessions after {LEDGER_BASE_SESSION} are {sessions}, expected {expected}")
    played = []
    for session, game in zip(sessions, games):
        close = closed.get(session)
        if close is None:
            problems.append(f"session {session} is not closed")
            continue
        outcome = close.get("outcome") or {}
        if outcome.get("game_id") != game["game_id"]:
            problems.append(f"session {session} played {outcome.get('game_id')}, expected {game['game_id']}")
        if not (close.get("integrity") or {}).get("ok") or close.get("state_changed") or close.get("home_changed"):
            problems.append(f"session {session} closed with an integrity, state or home change")
        played.append(outcome.get("game_id"))
    return {"sessions": len(sessions), "games": played, "problems": {"S2": problems} if problems else {}}


# ------------------------------------------------------------------------------------------------ comparison
def _config(f: Mapping[str, Any]) -> Tuple[str, str]:
    return f["scenario_id"], CANDIDATE_SIDE[f["condition"]]


def comparison(facts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """``d`` per configuration with two games of each policy; ``d_s`` per scenario with both seats; ``Dbar``."""
    z: Dict[Tuple[str, str, str], List[float]] = collections.defaultdict(list)
    for f in facts:
        if f["batch"] in ("A1", "A2") and f["z"] is not None:
            z[(f["tag"], *_config(f))].append(f["z"])
    d: Dict[str, float] = {}
    for sid in STAGE_A_SCENARIOS:
        for side in ("red", "blue"):
            a, b = z.get(("s35", sid, side), []), z.get(("s34", sid, side), [])
            if a and b:
                d[f"{sid} {side}"] = round(sum(a) / len(a) - sum(b) / len(b), 6)
    ds: Dict[str, float] = {}
    for sid in STAGE_A_SCENARIOS:
        pair = [d[k] for k in (f"{sid} red", f"{sid} blue") if k in d]
        if len(pair) == 2:
            ds[sid] = round(sum(pair) / 2, 6)
    complete = len(d) == 2 * len(STAGE_A_SCENARIOS)
    candidate_z = [v for (tag, _, _), vs in z.items() if tag == "s35" for v in vs]
    control_z = [v for (tag, _, _), vs in z.items() if tag == "s34" for v in vs]
    return {"d": d, "d_s": ds, "dbar": round(sum(d.values()) / len(d), 6) if complete else None,
            "dbar_interval": s34.bootstrap_interval(list(d.values()), seed=35) if complete else None,
            "zbar_candidate": round(sum(candidate_z) / len(candidate_z), 6) if candidate_z else None,
            "zbar_control": round(sum(control_z) / len(control_z), 6) if control_z else None,
            "configurations_compared": len(d)}


# ------------------------------------------------------------------------------------------------ gates
def severe_harm(batch: str, facts: Sequence[Mapping[str, Any]]) -> List[str]:
    """Severe-harm findings after a completed batch (facts of every game played so far, both policies)."""
    found = []
    candidate = [f for f in facts if f["tag"] == "s35"]
    for f in candidate:
        if (f.get("force") or {}).get("longest_wait", 0) >= DEADLOCK_WAIT:
            found.append(f"position {f['position']}: a ground unit waited {f['force']['longest_wait']} steps")
    stage_a = [f for f in candidate if f["batch"] in ("A1", "A2")]
    if batch == "A1":
        for f in stage_a:
            ref = f["reference"]["win"]
            if f["candidate"]["win"] is not None and f["candidate"]["win"] < ref["min"] - SEVERE_SD * ref["sd"]:
                found.append(f"position {f['position']}: margin more than {SEVERE_SD} reference SDs below the "
                             "reference minimum")
    if batch == "A2":
        by_config: Dict[Tuple[str, str], List[Mapping[str, Any]]] = collections.defaultdict(list)
        for f in stage_a:
            by_config[(f["scenario_id"], f["condition"])].append(f)
        for (sid, condition), games in sorted(by_config.items()):
            if len(games) == 2 and all(g["candidate"]["win"] < g["reference"]["win"]["min"] for g in games):
                found.append(f"{sid} {condition}: both candidate margins below the reference minimum")
    return found


def batch_gate(batch: str, facts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Whether the next batch may open, from every played game's facts (positions in order)."""
    stops = {f["position"]: structural(f) for f in facts}
    if any(stops.values()):
        return {"batch": batch, "open": False, "reason": "structural stop",
                "stops": {str(p): s for p, s in stops.items() if s}}
    harm = severe_harm(batch, facts)
    if harm:
        return {"batch": batch, "open": False, "reason": "severe harm", "findings": harm}
    if batch == "A2":
        dbar = comparison(facts)["dbar"]
        if dbar is not None and dbar <= REJECT_DBAR:
            return {"batch": batch, "open": False, "reason": "Dbar at or below the reject threshold", "dbar": dbar}
    if batch == "B2":
        return {"batch": batch, "open": False, "reason": "schedule complete"}
    return {"batch": batch, "open": True, "reason": "no structural stop and no severe harm"}


def disposition(facts: Sequence[Mapping[str, Any]], gates: Sequence[Mapping[str, Any]],
                authorized: bool = True) -> Dict[str, Any]:
    if not authorized:
        return {"disposition": "S35_LIVE_NOT_AUTHORIZED", "why": "no session budget was authorized"}
    if any(g["reason"] == "structural stop" for g in gates):
        return {"disposition": "S35_LIVE_INVALID", "why": "a structural stop fired"}
    if any(g["reason"] == "severe harm" for g in gates):
        return {"disposition": "S35_INTEGRATED_REJECT", "why": "severe harm"}
    stage_a = [f for f in facts if f["batch"] in ("A1", "A2")]
    stage_b = [f for f in facts if f["batch"] in ("B1", "B2")]
    cmp_ = comparison(facts)
    b_occupy = sum(1 for f in stage_b if f["candidate"]["occupy"] < f["reference"]["occupy"]["min"])
    b_remain = sum(1 for f in stage_b if f["candidate"]["remain"] < f["reference"]["remain"]["min"])
    margins_ok = sum(1 for f in stage_b if f["candidate"]["win"] >= f["reference"]["win"]["min"] - STAGE_B_MARGIN_SLACK)
    summary = {**cmp_, "stage_a_games": len(stage_a), "stage_b_games": len(stage_b),
               "stage_b_objective_below_reference_min": b_occupy, "stage_b_remain_below_reference_min": b_remain,
               "stage_b_margins_within_slack": margins_ok}
    if cmp_["dbar"] is not None and cmp_["dbar"] <= REJECT_DBAR:
        return {"disposition": "S35_INTEGRATED_REJECT", "why": "Dbar at or below -0.5", **summary}
    if b_occupy >= 3 or b_remain >= 3:
        return {"disposition": "S35_INTEGRATED_REJECT", "why": "Stage B objective or remaining-force score below the "
                                                              "reference minimum in three or more games", **summary}
    positive = sum(1 for v in cmp_["d_s"].values() if v > 0)
    collapse = any(v <= COLLAPSE_DS for v in cmp_["d_s"].values())
    if (len(stage_a) == 40 and len(stage_b) == 8 and cmp_["dbar"] is not None and cmp_["dbar"] >= PROMISING_DBAR
            and positive >= 4 and not collapse and (cmp_["zbar_candidate"] or 0) >= PROMISING_ZBAR
            and b_occupy == 0 and margins_ok >= 7):
        return {"disposition": "S35_INTEGRATED_PROMISING", "why": "every promising clause holds", **summary}
    return {"disposition": "S35_INTEGRATED_INCONCLUSIVE", "why": "neither reject nor promising", **summary}


def reference(references: Mapping[str, Any], game: Mapping[str, Any]) -> Dict[str, Any]:
    return s34.reference(references, game)


__all__ = ["schedule", "game_facts", "structural", "ledger_audit", "comparison", "severe_harm", "batch_gate",
           "disposition", "reference"]
