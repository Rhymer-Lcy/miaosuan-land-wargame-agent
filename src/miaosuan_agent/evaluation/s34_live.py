"""Sprint 34 live evaluation rules (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 10), frozen before the first session.

Schedule: 24 games, positions 1 to 24, sessions 2803 to 2826, in four batches. Stage A (positions 1 to 16): in each of
four scenarios the candidate plays red against ``baseline-v2`` (condition ``H1``) and blue against it (``H2``); batch A1
is the first repetition of the eight configurations, A2 the second. Stage B (positions 17 to 24): the candidate against
the inert control as red (``C2``) and blue (``C3``) in 2120531121 and 1930331196; batch B1 the first repetition, B2 the
second. Stage B runs only when Stage A's gate is open.

References: ``evaluation/s34-integrated-agent/references.json`` (``baseline-v2``'s own games of the same scenario,
condition and seat; 15 per configuration). These are unpaired historical comparisons, never paired causal estimates.

Structural stops (any closes the study at once; disposition ``S34_LIVE_INVALID``):

* S1 the game did not complete;
* S2 the ledger is not exactly the schedule's games so far, in order, each closed with integrity ok and the state file
  unchanged (checked by the position runner);
* S3 a tracked file, the SDK archive, or a policy source changed during the game (position runner);
* S4 a contract error of the candidate seat, an in-game replay mismatch, or an observer error;
* S5 the observer's fresh reconstruction of any candidate decision differs from the live one, or more than 1% of the
  candidate's decisions fell back to ``baseline-v2``;
* S6 the engine refused more than 2% of the candidate's unit actions, or more than 5 of its non-shoot actions.

Severe harm (Stage A, prospective): after A1, a candidate margin more than three reference standard deviations below
the reference minimum; after A2, a configuration whose two candidate margins are both below the reference minimum (under
``baseline-v2``'s own distribution each game has a 1 in 16 chance of that, both games about 1 in 256). Either closes the
gate; disposition ``S34_INTEGRATED_REJECT``.

Dispositions (first match): ``S34_LIVE_INVALID``; ``S34_INTEGRATED_REJECT`` (severe harm, or after Stage A the mean
standardized margin ``Zbar`` of the 16 games at or below -0.5, or Stage B objective value below the reference minimum in
3 or more of its 8 games); ``S34_INTEGRATED_PROMISING`` (both stages complete, ``Zbar`` at least +0.5, a positive mean
``z`` in at least 3 of the 4 scenarios, Stage B objective value never below the reference minimum and margin at least the
reference minimum minus 50 in at least 7 of 8 games); otherwise ``S34_INTEGRATED_INCONCLUSIVE``. Two repetitions per
seat are exploratory: no claim of statistical superiority follows from any of this.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STUDY_ID = "s34-integrated-live"
CARD_ID = "s34-integrated-live-1"
RULES_ID = "s34-integrated-live-rules-1"
LEDGER_BASE_SESSION = 2802
SESSION_CAP = 24
V2 = "baseline-v2-candidate-shoot-target-reservation"
INERT = "inert-v0"
STAGE_A_SCENARIOS = ("2130511121", "2120531121", "1930331196", "1910631192")
STAGE_B_SCENARIOS = ("2120531121", "1930331196")
BATCHES = {"A1": range(1, 9), "A2": range(9, 17), "B1": range(17, 21), "B2": range(21, 25)}
REFERENCE_CONDITION = {"H1": "C1", "H2": "C1", "C2": "C2", "C3": "C3"}
CANDIDATE_SIDE = {"H1": "red", "H2": "blue", "C2": "red", "C3": "blue"}
REFUSAL_SHARE = 0.02
NON_SHOOT_REFUSALS = 5
FALLBACK_SHARE = 0.01
SEVERE_SD = 3.0
REJECT_ZBAR, PROMISING_ZBAR = -0.5, 0.5
STAGE_B_MARGIN_SLACK = 50
GROUND = (1, 2)
DISPOSITIONS = ("S34_ENGINEERING_BLOCKED", "S34_LIVE_INVALID", "S34_INTEGRATED_REJECT", "S34_INTEGRATED_INCONCLUSIVE",
                "S34_INTEGRATED_PROMISING")


def schedule(candidate: str) -> List[Dict[str, Any]]:
    games = []
    position = 0
    for repetition in (1, 2):
        for sid in STAGE_A_SCENARIOS:
            for condition in ("H1", "H2"):
                position += 1
                games.append({"position": position, "condition": condition, "scenario_id": sid, "repetition": repetition,
                              "red": candidate if condition == "H1" else V2, "blue": V2 if condition == "H1" else candidate})
    for repetition in (1, 2):
        for sid in STAGE_B_SCENARIOS:
            for condition in ("C2", "C3"):
                position += 1
                games.append({"position": position, "condition": condition, "scenario_id": sid, "repetition": repetition,
                              "red": candidate if condition == "C2" else INERT,
                              "blue": INERT if condition == "C2" else candidate})
    for g in games:
        g["game_id"] = f"{g['scenario_id']}.{g['condition']}.{CARD_ID}.p{g['position']:02d}"
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
def _side_of(color: int) -> str:
    return "red" if color == 0 else "blue"


def objective_facts(steps: Sequence[Mapping[str, Any]], colour: int) -> Dict[str, Any]:
    """First ownership, losses, recaptures, final ownership and mean held value, objectives labelled by value rank."""
    first = steps[0]["cities"]
    order = sorted(range(len(first)), key=lambda i: (-(first[i][2] or 0), i))
    label = {first[i][0]: f"objective {n + 1} ({first[i][2]})" for n, i in enumerate(order)}
    owned_first: Dict[str, Dict[str, Optional[int]]] = {label[c[0]]: {"own": None, "enemy": None} for c in first}
    losses = recaptures = 0
    held_value = 0.0
    prev = {c[0]: c[1] for c in first}
    lost_once = set()
    play = [s for s in steps if s["k"] >= 0]
    for s in play:
        for coord, flag, value in s["cities"]:
            key = label[coord]
            if flag == colour and owned_first[key]["own"] is None:
                owned_first[key]["own"] = s["cur_step"]
            if flag == 1 - colour and owned_first[key]["enemy"] is None:
                owned_first[key]["enemy"] = s["cur_step"]
            if prev.get(coord) == colour and flag != colour:
                losses += 1
                lost_once.add(coord)
            if prev.get(coord) != colour and flag == colour and coord in lost_once:
                recaptures += 1
            prev[coord] = flag
            if flag == colour:
                held_value += value or 0
    final = play[-1]["cities"] if play else first
    return {"first_owned_step": owned_first, "losses": losses, "recaptures": recaptures,
            "final_owned": sum(1 for c in final if c[1] == colour), "final_enemy": sum(1 for c in final if c[1] == 1 - colour),
            "objectives": len(final), "mean_held_value": round(held_value / max(1, len(play)), 3),
            "first_owned_count": sum(1 for v in owned_first.values() if v["own"] is not None),
            "first_owned_before_enemy": sum(1 for v in owned_first.values() if v["own"] is not None
                                            and (v["enemy"] is None or v["own"] < v["enemy"]))}


def force_facts(steps: Sequence[Mapping[str, Any]], colour: int) -> Dict[str, Any]:
    start = {r[0]: r for r in steps[0]["units"] if r[1] == colour}
    end = {r[0] for r in steps[-1]["units"] if r[1] == colour}
    lost = [r for uid, r in start.items() if uid not in end]
    by_class = collections.Counter(f"type {r[2]} sub_type {r[3]}" for r in lost)
    waits: Dict[Any, int] = {}
    runs: Dict[Any, int] = {}
    wait_steps = 0
    for s in steps:
        for r in s["units"]:
            if r[1] != colour or r[2] not in GROUND or r[9]:
                continue
            if r[5] > 0 and not r[6]:
                wait_steps += 1
                runs[r[0]] = runs.get(r[0], 0) + 1
                waits[r[0]] = max(waits.get(r[0], 0), runs[r[0]])
            else:
                runs[r[0]] = 0
    return {"units_at_start": len(start), "units_lost": len(lost), "value_lost": sum(r[8] or 0 for r in lost),
            "lost_by_class": dict(sorted(by_class.items())), "wait_unit_steps": wait_steps,
            "longest_wait": max(waits.values(), default=0)}


def fire_facts(steps: Sequence[Mapping[str, Any]], colour: int) -> Dict[str, Any]:
    own_ids = {r[0] for s in steps for r in s["units"] if r[1] == colour}
    shots = hits = friendly = 0
    for s in steps:
        for j in s.get("judge") or ():
            attacker, target = j.get("att_obj_id"), j.get("target_obj_id")
            if attacker in own_ids:
                shots += 1
                hits += (j.get("damage") or 0) > 0
                friendly += target in own_ids and (j.get("damage") or 0) > 0
    return {"judged_attacks": shots, "damaging_attacks": hits, "friendly_damage": friendly}


def refusal_facts(steps: Sequence[Mapping[str, Any]], seat: int) -> Dict[str, Any]:
    by = collections.Counter()
    for s in steps:
        for e in s.get("refusals") or ():
            message = e.get("message") or {}
            if message.get("actor") == seat:
                code = (e.get("error") or {}).get("code")
                by[f"type {message.get('type')} code {code}"] += 1
    total = sum(by.values())
    non_shoot = sum(v for k, v in by.items() if not k.startswith("type 2 "))
    return {"refused": total, "refused_non_shoot": non_shoot, "by_type_and_code": dict(sorted(by.items()))}


def game_facts(game: Mapping[str, Any], record: Mapping[str, Any], compact: Mapping[str, Any],
               references: Mapping[str, Any]) -> Dict[str, Any]:
    side = CANDIDATE_SIDE[game["condition"]]
    colour = 0 if side == "red" else 1
    seat = next(s["seat"] for s in record.get("seats", []) if s["faction"] == colour) if record.get("seats") else None
    seat_log = next((s for s in record.get("seats", []) if s["faction"] == colour), {})
    scores = record.get("final_scores") or {}
    ref = reference(references, game)
    margin = scores.get(f"{side}_win")
    z = None
    if margin is not None and ref["win"]["sd"] > 0:
        z = round((margin - ref["win"]["mean"]) / ref["win"]["sd"], 6)
    steps = compact.get("steps") or []
    checks = compact.get("checks") or {}
    unit_actions = sum(v for k, v in (seat_log.get("actions_by_type") or {}).items() if k != "333")
    latency = sorted(seat_log.get("latency_us") or [0])
    facts = {
        "position": game["position"], "batch": game["batch"], "condition": game["condition"],
        "scenario_id": game["scenario_id"], "candidate_side": side, "status": record.get("status"),
        "steps": record.get("steps"), "session": record.get("session"),
        "candidate": {k: scores.get(f"{side}_{k}") for k in ("occupy", "attack", "remain", "total", "win")},
        "opponent": {k: scores.get(f"{'blue' if side == 'red' else 'red'}_{k}")
                     for k in ("occupy", "attack", "remain", "total", "win")},
        "reference": {"win": ref["win"], "occupy": ref["occupy"]},
        "z": z,
        "objectives": objective_facts(steps, colour) if steps else {},
        "force": force_facts(steps, colour) if steps else {},
        "opponent_force": force_facts(steps, 1 - colour) if steps else {},
        "fire": fire_facts(steps, colour) if steps else {},
        "refusals": refusal_facts(steps, seat) if steps and seat is not None else {},
        "actions_by_type": dict(seat_log.get("actions_by_type") or {}),
        "unit_actions": unit_actions,
        "decisions": checks.get("decisions", 0), "fallbacks": checks.get("fallbacks", 0),
        "validation_rejections": checks.get("validation_rejections", 0),
        "reconstructed": checks.get("reconstructed", 0),
        "reconstruction_mismatches": checks.get("reconstruction_mismatch", 0),
        "decisions_differing_from_v2": checks.get("decisions_differing_from_v2", 0),
        "differing_by_module": dict(compact.get("differing_by_module") or {}),
        "module_actions": dict(compact.get("module_actions") or {}),
        "contract_errors": seat_log.get("contract_errors"), "replay_checks": seat_log.get("replay_checks"),
        "replay_mismatches": seat_log.get("replay_mismatches"),
        "observer_errors": len(record.get("observer_errors") or []),
        "latency_ms_max": round(latency[-1] / 1000.0, 3),
        "latency_ms_p99": round(latency[min(len(latency) - 1, int(0.99 * len(latency)))] / 1000.0, 3),
    }
    return facts


def structural(facts: Mapping[str, Any]) -> Dict[str, List[str]]:
    stops: Dict[str, List[str]] = {}

    def add(code: str, text: str) -> None:
        stops.setdefault(code, []).append(text)

    if facts.get("status") != "COMPLETED":
        add("S1", f"status {facts.get('status')}")
    if facts.get("contract_errors") or facts.get("replay_mismatches") or facts.get("observer_errors"):
        add("S4", f"contract errors {facts.get('contract_errors')}, replay mismatches {facts.get('replay_mismatches')}, "
                  f"observer errors {facts.get('observer_errors')}")
    if not facts.get("reconstructed"):
        add("S5", "no candidate decision was reconstructed")
    if facts.get("reconstruction_mismatches"):
        add("S5", f"{facts['reconstruction_mismatches']} reconstruction mismatches")
    if facts.get("decisions") and facts.get("fallbacks", 0) > FALLBACK_SHARE * facts["decisions"]:
        add("S5", f"{facts['fallbacks']} fallbacks of {facts['decisions']} decisions")
    refused = facts.get("refusals") or {}
    if refused.get("refused", 0) > REFUSAL_SHARE * max(1, facts.get("unit_actions", 0)):
        add("S6", f"{refused['refused']} refused of {facts.get('unit_actions')} unit actions")
    if refused.get("refused_non_shoot", 0) > NON_SHOOT_REFUSALS:
        add("S6", f"{refused['refused_non_shoot']} refused non-shoot actions")
    return stops


def ledger_audit(records: Iterable[Mapping[str, Any]], games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The ledger's sessions after the base: exactly the schedule's games so far, in order, each closed with integrity
    ok and neither the state file nor the home directory changed (structural stop S2 otherwise)."""
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


# ------------------------------------------------------------------------------------------------ gates
def severe_harm(batch: str, facts: Sequence[Mapping[str, Any]]) -> List[str]:
    """Severe-harm findings for a completed Stage A batch (facts of every Stage A game played so far)."""
    found = []
    if batch == "A1":
        for f in facts:
            ref = f["reference"]["win"]
            if f["candidate"]["win"] is not None and f["candidate"]["win"] < ref["min"] - SEVERE_SD * ref["sd"]:
                found.append(f"position {f['position']}: margin more than {SEVERE_SD} reference SDs below the "
                             "reference minimum")
    if batch == "A2":
        by_config: Dict[Tuple[str, str], List[Mapping[str, Any]]] = collections.defaultdict(list)
        for f in facts:
            by_config[(f["scenario_id"], f["condition"])].append(f)
        for (sid, condition), games in sorted(by_config.items()):
            if len(games) == 2 and all(g["candidate"]["win"] < g["reference"]["win"]["min"] for g in games):
                found.append(f"{sid} {condition}: both margins below the reference minimum")
    return found


def batch_gate(batch: str, facts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Whether the next batch may open, from every played game's facts (positions in order)."""
    stops = {f["position"]: structural(f) for f in facts}
    if any(stops.values()):
        return {"batch": batch, "open": False, "reason": "structural stop",
                "stops": {str(p): s for p, s in stops.items() if s}}
    if batch in ("A1", "A2"):
        harm = severe_harm(batch, [f for f in facts if f["batch"] in ("A1", "A2")])
        if harm:
            return {"batch": batch, "open": False, "reason": "severe harm", "findings": harm}
    if batch == "B2":
        return {"batch": batch, "open": False, "reason": "schedule complete"}
    return {"batch": batch, "open": True, "reason": "no structural stop and no severe harm"}


def zbar(facts: Sequence[Mapping[str, Any]]) -> Optional[float]:
    zs = [f["z"] for f in facts if f["batch"] in ("A1", "A2") and f["z"] is not None]
    return round(sum(zs) / len(zs), 6) if zs else None


def bootstrap_interval(values: Sequence[float], draws: int = 10000, seed: int = 34) -> Optional[Tuple[float, float]]:
    """Descriptive percentile bootstrap interval of the mean (fixed seed, deterministic)."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(draws))
    return round(means[int(0.025 * draws)], 6), round(means[int(0.975 * draws) - 1], 6)


def disposition(facts: Sequence[Mapping[str, Any]], gates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if any(g["reason"] == "structural stop" for g in gates):
        return {"disposition": "S34_LIVE_INVALID", "why": "a structural stop fired"}
    if any(g["reason"] == "severe harm" for g in gates):
        return {"disposition": "S34_INTEGRATED_REJECT", "why": "severe harm in Stage A"}
    stage_a = [f for f in facts if f["batch"] in ("A1", "A2")]
    stage_b = [f for f in facts if f["batch"] in ("B1", "B2")]
    z = zbar(stage_a)
    b_below = sum(1 for f in stage_b if f["candidate"]["occupy"] < f["reference"]["occupy"]["min"])
    by_scenario: Dict[str, List[float]] = collections.defaultdict(list)
    for f in stage_a:
        if f["z"] is not None:
            by_scenario[f["scenario_id"]].append(f["z"])
    positive = sum(1 for v in by_scenario.values() if v and sum(v) / len(v) > 0)
    summary = {"zbar": z, "zbar_interval": bootstrap_interval([f["z"] for f in stage_a if f["z"] is not None]),
               "scenarios_with_positive_mean_z": positive, "stage_b_objective_value_below_reference_min": b_below,
               "stage_a_games": len(stage_a), "stage_b_games": len(stage_b)}
    if len(stage_a) == 16 and z is not None and z <= REJECT_ZBAR:
        return {"disposition": "S34_INTEGRATED_REJECT", "why": "Zbar at or below -0.5", **summary}
    if b_below >= 3:
        return {"disposition": "S34_INTEGRATED_REJECT", "why": "Stage B objective value below the reference minimum "
                                                               "in 3 or more games", **summary}
    margins_ok = sum(1 for f in stage_b
                     if f["candidate"]["win"] >= f["reference"]["win"]["min"] - STAGE_B_MARGIN_SLACK)
    if (len(stage_a) == 16 and len(stage_b) == 8 and z is not None and z >= PROMISING_ZBAR and positive >= 3
            and b_below == 0 and margins_ok >= 7):
        return {"disposition": "S34_INTEGRATED_PROMISING", "why": "every promising clause holds", **summary}
    return {"disposition": "S34_INTEGRATED_INCONCLUSIVE", "why": "neither reject nor promising", **summary}
