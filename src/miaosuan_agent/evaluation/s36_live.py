"""Sprint 36 live study rules (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 19). A PROPOSAL: no session is authorized.

Budget proposed: at most 51 sessions after session 2845 (positions 1 to 51 open sessions 2846 to 2896), one game per
exclusive session, serially, in four batches. The next unopened session number is not an authorization.

* ``A1`` (positions 1 to 23): in each of the five Sprint 35 Stage A scenarios the Sprint 36 candidate and a fresh
  Sprint 34 control each play red against ``baseline-v2`` (``H1``) and blue against it (``H2``), interleaved as in
  Sprint 35; after the four games of each scenario in which the Sprint 35 candidate regressed as blue (2130511121,
  1930331196, 1910631192) the frozen Sprint 35 candidate plays that blue configuration once (a replication of the
  regression, reported beside the comparison, never part of it).
* ``A2`` (24 to 43): the twenty candidate and control games again, the other order.
* ``H1`` (44 to 47): the held-out scenario 2010211129 (never used to design or tune any Sprint 36 rule), candidate and
  control, both seats.
* ``B1`` (48 to 51): the candidate against the inert control in 201033019601 and 2010131194, both seats: two scenarios
  where Sprint 35's candidate took no objective in the model world (the coverage regression), now on the engine.

Comparison scale. Sprint 35 compared ``z = (margin - mean) / sd`` against ``baseline-v2``'s own games; where that
reference SD is small one game dominates (a Sprint 34 control game in 2130511121 as red scored z = 17.9). Sprint 36
compares the **share of the stake**: margin divided by the scenario's stake (objective total plus both sides' maximum
remaining-force scores, read from each game's own record). ``d`` per configuration = mean share of the candidate's
games minus that of the control's games; ``Dbar`` the mean of the ten Stage A ``d``; ``d_s`` per scenario.

Calibration (``scripts/s36_calibration.py``, ``evaluation/s36-tactical-recovery/live-calibration.json``, from the
Sprint 34 control's 26 recorded Stage A games): the pooled within-configuration SD of the share is ``SHARE_SD``; with two
games per policy and configuration over ten configurations, ``Dbar`` has a null SD of ``SHARE_SD / sqrt(10)``.
Thresholds: ``UNFAVOURABLE_DBAR = -1.96`` null SDs (two-sided 5%, normal approximation, 16 degrees of freedom: an
approximation, stated as such); after A1 alone (one game each) ``EARLY_FUTILITY = -2.576`` null SDs of that batch.

Stops (``evaluation.s36_study``; the runner and the report derive the same state from the same records):

* invalid experiment (``S36_LIVE_INVALID``), any game: incomplete game, ledger or file change (runner), observer
  error, replay or reconstruction mismatch, refusal facts not retained, an echo-count mismatch; and any contract or
  quality failure of a frozen control (below);
* systemic agent failure (``S36_AGENT_FAILURE``), candidate games: a contract error, more than 1% fallbacks, latency
  p99 above 200 ms or maximum above 3,000 ms, memory above 200,000 bytes, a damaging attack on an own unit, a structural
  or systemic refusal finding (``evaluation.s36_refusals``, ``s36-refusal-gate-1``), a ground unit waiting 600 or more
  consecutive steps in front of a full hex (a deadlock, cause read by ``evaluation.s36_capture``);
* severe harm (``S36_SEVERE_HARM``): a candidate margin more than three reference SDs below the reference minimum
  (any game; 0 of the control's 26 and 0 of the Sprint 35 candidate's 9 recorded games); after A2, a configuration whose
  two candidate margins are both below the reference minimum; at the end, Stage B objective score below the reference
  minimum in two or more of four games;
* unfavourable (``S36_UNFAVOURABLE``): ``Dbar`` after A1 at or below ``EARLY_FUTILITY``, or after A2 at or below
  ``UNFAVOURABLE_DBAR`` (H1 and B1 are then not played).

Dispositions at the end of the schedule (first match): ``S36_SEVERE_HARM`` (Stage B coverage), ``S36_UNFAVOURABLE``;
``S36_PROMISING`` (``Dbar`` at least ``-UNFAVOURABLE_DBAR``, ``d_s`` positive in at least four of five scenarios, the
held-out mean ``d`` at least 0, no Stage B objective score below the reference minimum);
``S36_INCONCLUSIVE_UNFAVOURABLE_DIRECTION`` (``Dbar`` below 0: ordinary unfavourable stochastic performance);
otherwise ``S36_INCONCLUSIVE``. Two games per configuration are exploratory: ``PROMISING`` justifies a confirmation,
never a promotion.
"""

from __future__ import annotations

import collections
import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import s34_live as s34
from . import s35_live as s35
from . import s36_refusals as R
from .s36_capture import FULL
from .s36_study import Rules

STUDY_ID = "s36-tactical-live"
CARD_ID = "s36-tactical-live-1"
RULES_ID = "s36-tactical-live-rules-1"
LEDGER_BASE_SESSION = 2845
SESSION_CAP = 51
V2 = s34.V2
INERT = s34.INERT
S34_CONTROL = "s34-integrated-mission-orchestrator-1"
S35_CONTROL = "s35-coalition-coalition-mission-planner-2"
STAGE_A_SCENARIOS = s35.STAGE_A_SCENARIOS
REPLICATION = ("2130511121", "1930331196", "1910631192")
HELD_OUT = "2010211129"
STAGE_B = (("201033019601", "C2"), ("201033019601", "C3"), ("2010131194", "C2"), ("2010131194", "C3"))
BATCHES = {"A1": range(1, 24), "A2": range(24, 44), "H1": range(44, 48), "B1": range(48, 52)}
CANDIDATE_SIDE = s34.CANDIDATE_SIDE
REFERENCE_CONDITION = s34.REFERENCE_CONDITION
ORDER = s35.ORDER
TAGS = ("s36", "s34", "s35")

#: Calibrated on the Sprint 34 control's 26 recorded Stage A games (live-calibration.json).
SHARE_SD = 0.4187
NULL_SD_DBAR = round(SHARE_SD / math.sqrt(10), 4)
UNFAVOURABLE_DBAR = round(-1.96 * NULL_SD_DBAR, 4)
NULL_SD_DBAR_A1 = round(SHARE_SD * math.sqrt(2) / math.sqrt(10), 4)
EARLY_FUTILITY = round(-2.576 * NULL_SD_DBAR_A1, 4)
SEVERE_SD = s34.SEVERE_SD
FALLBACK_SHARE = s34.FALLBACK_SHARE
LATENCY_P99_MS, LATENCY_MAX_MS = s35.LATENCY_P99_MS, s35.LATENCY_MAX_MS
MEMORY_BYTES = s35.MEMORY_BYTES
DEADLOCK_WAIT = s35.DEADLOCK_WAIT
STAGE_B_COVERAGE_LIMIT = 2
DISPOSITIONS = ("S36_ENGINEERING_BLOCKED", "S36_LIVE_NOT_AUTHORIZED", "S36_LIVE_IN_PROGRESS", "S36_LIVE_INVALID",
                "S36_AGENT_FAILURE", "S36_SEVERE_HARM", "S36_UNFAVOURABLE", "S36_INCONCLUSIVE_UNFAVOURABLE_DIRECTION",
                "S36_INCONCLUSIVE", "S36_PROMISING")


def schedule(candidate: str) -> List[Dict[str, Any]]:
    ids = {"s36": candidate, "s34": S34_CONTROL, "s35": S35_CONTROL}
    games: List[Dict[str, Any]] = []

    def add(tag: str, condition: str, sid: str, repetition: int) -> None:
        policy = ids[tag]
        other = INERT if condition in ("C2", "C3") else V2
        red = policy if condition in ("H1", "C2") else other
        blue = other if condition in ("H1", "C2") else policy
        games.append({"position": len(games) + 1, "condition": condition, "scenario_id": sid, "repetition": repetition,
                      "tag": tag, "policy": policy, "red": red, "blue": blue})

    for repetition in (1, 2):
        for index, sid in enumerate(STAGE_A_SCENARIOS):
            for tag, condition in ORDER[(index + repetition - 1) % 2]:
                add({"s35": "s36"}.get(tag, tag), condition, sid, repetition)
            if repetition == 1 and sid in REPLICATION:
                add("s35", "H2", sid, 1)
    for tag, condition in ORDER[0]:
        add({"s35": "s36"}.get(tag, tag), condition, HELD_OUT, 1)
    for sid, condition in STAGE_B:
        add("s36", condition, sid, 1)
    for g in games:
        g["game_id"] = f"{g['scenario_id']}.{g['condition']}.{g['tag']}.{CARD_ID}.p{g['position']:02d}"
        g["session"] = LEDGER_BASE_SESSION + g["position"]
        g["batch"] = next(b for b, r in BATCHES.items() if g["position"] in r)
        g["stage"] = g["batch"][0]
    return games


def rules_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def reference(references: Mapping[str, Any], game: Mapping[str, Any]) -> Dict[str, Any]:
    config = f"{game['scenario_id']}.{REFERENCE_CONDITION[game['condition']]}"
    return references["configs"][config][CANDIDATE_SIDE[game["condition"]]]


# ------------------------------------------------------------------------------------------------ facts
def stake(record: Mapping[str, Any], compact: Mapping[str, Any]) -> Optional[float]:
    """Objective total plus both sides' maximum remaining-force scores, from the game's own record."""
    scores = record.get("final_scores") or {}
    steps = compact.get("steps") or []
    if not steps or "red_remain_max" not in scores or "blue_remain_max" not in scores:
        return None
    objectives = sum(c[2] or 0 for c in steps[0]["cities"])
    return float(objectives + scores["red_remain_max"] + scores["blue_remain_max"])


def halt_facts(compact: Mapping[str, Any]) -> Dict[str, Any]:
    """Halted unit-steps by cause and the longest consecutive run in front of a full hex (``s36_capture``)."""
    by_cause = collections.Counter(h[2] for h in compact.get("halts") or ())
    runs: Dict[Any, Tuple[int, int]] = {}
    longest = 0
    for k, unit, cause in sorted(compact.get("halts") or (), key=lambda h: (h[1], h[0])):
        if cause != FULL:
            continue
        last, length = runs.get(unit, (None, 0))
        length = length + 1 if last == k - 1 else 1
        runs[unit] = (k, length)
        longest = max(longest, length)
    return {"by_cause": dict(sorted(by_cause.items())), "longest_full_hex_wait": longest}


def game_facts(game: Mapping[str, Any], record: Mapping[str, Any], compact: Mapping[str, Any],
               references: Mapping[str, Any]) -> Dict[str, Any]:
    facts = s35.game_facts(game, record, compact, references)
    side = CANDIDATE_SIDE[game["condition"]]
    colour = 0 if side == "red" else 1
    seat_log = next((s for s in record.get("seats", []) if s["faction"] == colour), {})
    total = stake(record, compact)
    margin = facts["candidate"]["win"]
    summary = R.seat_summary(seat_log) if seat_log else None
    facts.update(stake=total, share=(round(margin / total, 6) if (total and margin is not None) else None),
                 refusal_summary=summary, halts=halt_facts(compact),
                 echo_matches=(summary or {}).get("echo_matches"), retained=(summary or {}).get("retained"))
    return facts


# ------------------------------------------------------------------------------------------------ game stops
def invalid_findings(facts: Mapping[str, Any]) -> List[str]:
    """Findings that make the experiment uninterpretable whichever policy played."""
    found = []
    if facts.get("status") != "COMPLETED":
        found.append(f"status {facts.get('status')}")
    if facts.get("observer_errors") or facts.get("replay_mismatches"):
        found.append(f"observer errors {facts.get('observer_errors')}, replay mismatches {facts.get('replay_mismatches')}")
    if not facts.get("reconstructed") or facts.get("reconstruction_mismatches"):
        found.append(f"reconstructed {facts.get('reconstructed')}, mismatches {facts.get('reconstruction_mismatches')}")
    summary = facts.get("refusal_summary")
    if not summary or not summary.get("retained"):
        found.append("refusal facts not retained")
    elif not summary.get("echo_matches"):
        found.append(f"echo {summary.get('echo')} of {summary.get('unit_actions')} unit actions")
    return found


def policy_findings(facts: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> List[str]:
    """Contract and quality findings of the policy under test (an agent failure for the candidate; for a frozen
    control the comparison basis is broken and the experiment is invalid)."""
    found = []
    if facts.get("contract_errors"):
        found.append(f"{facts['contract_errors']} contract errors")
    if facts.get("decisions") and facts.get("fallbacks", 0) > FALLBACK_SHARE * facts["decisions"]:
        found.append(f"{facts['fallbacks']} fallbacks of {facts['decisions']} decisions")
    if facts.get("latency_ms_p99", 0) > LATENCY_P99_MS or facts.get("latency_ms_max", 0) > LATENCY_MAX_MS:
        found.append(f"latency p99 {facts.get('latency_ms_p99')} ms, maximum {facts.get('latency_ms_max')} ms")
    if facts.get("memory_bytes_max", 0) > MEMORY_BYTES:
        found.append(f"memory {facts['memory_bytes_max']} bytes")
    if (facts.get("fire") or {}).get("friendly_damage", 0) > 0:
        found.append(f"{facts['fire']['friendly_damage']} damaging attacks on own units")
    summary = facts.get("refusal_summary")
    if summary and summary.get("retained"):
        e_before = sum(R.total(f["refusal_summary"], "E") for f in history[:-1]
                       if f.get("refusal_summary") and f["refusal_summary"].get("retained"))
        found += R.structural_findings(summary, 0, e_before)
        found += R.systemic_findings(summary)
    if (facts.get("halts") or {}).get("longest_full_hex_wait", 0) >= DEADLOCK_WAIT:
        found.append(f"a ground unit waited {facts['halts']['longest_full_hex_wait']} steps in front of a full hex")
    return found


def harm_findings(facts: Mapping[str, Any]) -> List[str]:
    if facts.get("tag") != "s36" or facts.get("batch") not in ("A1", "A2", "H1"):
        return []
    ref = facts["reference"]["win"]
    margin = facts["candidate"]["win"]
    if margin is not None and margin < ref["min"] - SEVERE_SD * ref["sd"]:
        return [f"position {facts['position']}: margin more than {SEVERE_SD} reference SDs below the reference minimum"]
    return []


def game_stop(facts: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> Optional[Tuple[str, List[str]]]:
    invalid = invalid_findings(facts)
    if invalid:
        return "structural", invalid
    policy = policy_findings(facts, history)
    if policy:
        return ("agent" if facts.get("tag") == "s36" else "structural"), policy
    harm = harm_findings(facts)
    if harm:
        return "harm", harm
    return None


# ------------------------------------------------------------------------------------------------ comparison
def _config(f: Mapping[str, Any]) -> Tuple[str, str]:
    return f["scenario_id"], CANDIDATE_SIDE[f["condition"]]


def comparison(facts: Sequence[Mapping[str, Any]], batches: Sequence[str] = ("A1", "A2")) -> Dict[str, Any]:
    shares: Dict[Tuple[str, str, str], List[float]] = collections.defaultdict(list)
    for f in facts:
        if f["batch"] in batches and f["tag"] in ("s36", "s34") and f.get("share") is not None:
            shares[(f["tag"], *_config(f))].append(f["share"])
    d: Dict[str, float] = {}
    for sid in STAGE_A_SCENARIOS:
        for side in ("red", "blue"):
            a, b = shares.get(("s36", sid, side), []), shares.get(("s34", sid, side), [])
            if a and b:
                d[f"{sid} {side}"] = round(sum(a) / len(a) - sum(b) / len(b), 6)
    ds = {}
    for sid in STAGE_A_SCENARIOS:
        pair = [d[k] for k in (f"{sid} red", f"{sid} blue") if k in d]
        if len(pair) == 2:
            ds[sid] = round(sum(pair) / 2, 6)
    complete = len(d) == 2 * len(STAGE_A_SCENARIOS)
    return {"d": d, "d_s": ds, "dbar": round(sum(d.values()) / len(d), 6) if complete else None,
            "dbar_interval": s34.bootstrap_interval(list(d.values()), seed=36) if complete else None,
            "configurations_compared": len(d)}


def held_out(facts: Sequence[Mapping[str, Any]]) -> Optional[float]:
    by = collections.defaultdict(list)
    for f in facts:
        if f["batch"] == "H1" and f.get("share") is not None:
            by[(f["tag"], CANDIDATE_SIDE[f["condition"]])].append(f["share"])
    d = [sum(by[("s36", s)]) / len(by[("s36", s)]) - sum(by[("s34", s)]) / len(by[("s34", s)])
         for s in ("red", "blue") if by.get(("s36", s)) and by.get(("s34", s))]
    return round(sum(d) / len(d), 6) if len(d) == 2 else None


def replication(facts: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The Sprint 35 candidate's replication games beside the control's A1 game of the same configuration."""
    out = []
    for f in facts:
        if f["tag"] != "s35":
            continue
        control = [g["share"] for g in facts if g["tag"] == "s34" and g["batch"] == "A1" and _config(g) == _config(f)]
        out.append({"scenario_id": f["scenario_id"], "side": CANDIDATE_SIDE[f["condition"]], "share": f["share"],
                    "control_share": control[0] if control else None})
    return out


def coverage_below(facts: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for f in facts if f["batch"] == "B1" and f["candidate"]["occupy"] < f["reference"]["occupy"]["min"])


def batch_gate(batch: str, history: Sequence[Mapping[str, Any]]) -> Optional[Tuple[str, List[str]]]:
    if batch == "A1":
        cmp_ = comparison(history, ("A1",))
        if cmp_["dbar"] is not None and cmp_["dbar"] <= EARLY_FUTILITY:
            return "futility", [f"A1 Dbar {cmp_['dbar']} at or below {EARLY_FUTILITY}"]
    if batch == "A2":
        by: Dict[Tuple[str, str], List[Mapping[str, Any]]] = collections.defaultdict(list)
        for f in history:
            if f["tag"] == "s36" and f["batch"] in ("A1", "A2"):
                by[(f["scenario_id"], f["condition"])].append(f)
        harm = [f"{sid} {cond}: both candidate margins below the reference minimum"
                for (sid, cond), gs in sorted(by.items())
                if len(gs) == 2 and all(g["candidate"]["win"] < g["reference"]["win"]["min"] for g in gs)]
        if harm:
            return "harm", harm
        cmp_ = comparison(history)
        if cmp_["dbar"] is not None and cmp_["dbar"] <= UNFAVOURABLE_DBAR:
            return "futility", [f"Dbar {cmp_['dbar']} at or below {UNFAVOURABLE_DBAR}"]
    return None


def final(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    cmp_ = comparison(history)
    h = held_out(history)
    below = coverage_below(history)
    positive = sum(1 for v in cmp_["d_s"].values() if v > 0)
    summary = {**cmp_, "held_out_d": h, "stage_b_objective_below_reference_min": below,
               "scenarios_with_positive_d": positive, "replication": replication(history),
               "thresholds": {"unfavourable": UNFAVOURABLE_DBAR, "promising": -UNFAVOURABLE_DBAR}}
    if below >= STAGE_B_COVERAGE_LIMIT:
        return {"disposition": "S36_SEVERE_HARM", "why": "Stage B objective score below the reference minimum in "
                                                         "two or more games", **summary}
    dbar = cmp_["dbar"]
    if dbar is not None and dbar <= UNFAVOURABLE_DBAR:
        return {"disposition": "S36_UNFAVOURABLE", "why": f"Dbar at or below {UNFAVOURABLE_DBAR}", **summary}
    if dbar is not None and dbar >= -UNFAVOURABLE_DBAR and positive >= 4 and h is not None and h >= 0 and below == 0:
        return {"disposition": "S36_PROMISING", "why": "every promising clause holds", **summary}
    if dbar is not None and dbar < 0:
        return {"disposition": "S36_INCONCLUSIVE_UNFAVOURABLE_DIRECTION", "why": "Dbar below 0 within the null band",
                **summary}
    return {"disposition": "S36_INCONCLUSIVE", "why": "neither unfavourable nor promising", **summary}


RULES = Rules(
    rules_id=RULES_ID, batches=tuple((b, tuple(r)) for b, r in BATCHES.items()),
    game_stop=game_stop, batch_gate=batch_gate, final=final,
    stop_dispositions={"protocol": "S36_LIVE_INVALID", "structural": "S36_LIVE_INVALID", "agent": "S36_AGENT_FAILURE",
                       "harm": "S36_SEVERE_HARM", "futility": "S36_UNFAVOURABLE", "complete": "S36_INCONCLUSIVE"},
    not_started="S36_LIVE_NOT_AUTHORIZED", in_progress="S36_LIVE_IN_PROGRESS",
    sources=(invalid_findings, policy_findings, harm_findings, comparison, held_out, coverage_below,
             R.structural_findings, R.systemic_findings, R.classify))


def ledger_audit(records, games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Sprint 35's audit with Sprint 36's base session."""
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


__all__ = ["schedule", "game_facts", "game_stop", "batch_gate", "final", "comparison", "RULES", "ledger_audit",
           "reference", "stake"]
