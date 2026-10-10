"""Sprint 36 refusal taxonomy and the refusal quality gate (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 3).

Sprint 35's stop S6 (copied from Sprint 34) fired when more than 2% of a policy's unit actions were refused. In the
small scenarios a policy issues 6 to 31 unit actions per game, so one or two ordinary same-step races (the shooter
destroyed, or the target destroyed, earlier in the same step) exceed 2% and closed the whole study. This module keeps
S6 unchanged for the historical record and defines a new, separately named rule.

**Taxonomy** (``taxonomy`` ``s36-refusal-taxonomy-1``). A refusal is classified from its factual record
(``evaluation.refusals``, schema ``miaosuan-refusal-fact/1``: action type, code, normalized message, whether the
action passed the project gate, whether it was listed for the unit at the start of the step, the step evidence) and its
attribution-2 label. Nothing is inferred from a code alone:

* ``A`` contract: the action did not pass the project gate, or was not listed for the unit at the start of the step
  (a shot also needs the same target and weapon listed), and is not a movement or state action; or its message is
  ``ErrorActionType`` (the engine does not accept the action type);
* ``B`` movement or transition: a move, embark, disembark, state change or stop that was not listed at the start of
  the step;
* ``D`` same-step race: listed and gate-passed, and attribution 2 says the actor (any action type, code 203
  ``CantControlDiedOperator``) or the target (shot, code 516 ``CantShootToDiedBop``) was no longer alive at
  resolution, with no second own shot at that target in the step;
* ``R`` redundant own action: listed and gate-passed, and either a 516 target-gone shot with at least two own shots at
  the target in the step, or an occupation refused because the objective was already own or occupied twice in the step
  (code 1804, attribution 2);
* ``E`` unexplained: listed and gate-passed, but no attribution rule covers the factual class, or its evidence is
  missing or contradicts the rule (for example code 404 ``CantMoveKeptPeople`` on a move, four times in the history).

Dangerous accepted actions (``C``) are not refusals: a damaging attack on an own unit, or an emitted action type the
policy does not declare. They are counted from the game facts.

**Gate** (``s36-refusal-gate-1``), applied to each game of a policy under test (never to its opponent):

* structural (any one closes the study at once): ``A >= 1``, ``B >= 1``, ``C >= 1``, ``E >= 2`` in one game, or
  ``E >= 3`` over the study so far; an echo-count mismatch (the engine echoed a different number of the seat's actions
  than it emitted) makes the denominator untrustworthy and is structural too;
* systemic (a pattern, closes the study as an agent failure when the game is the candidate's): for the fire actions
  (shots and guided shots) and the other unit actions separately, ``D`` refusals at least ``SYSTEMIC_MIN`` and their
  upper binomial tail under the calibrated reference race rate below ``SYSTEMIC_ALPHA``; or ``R`` refusals at least
  ``SYSTEMIC_MIN`` with the same tail test under the reference redundancy rate; or one unit refused ``REPEAT_ACTOR``
  times or more in one game.

The reference rates, ``SYSTEMIC_MIN``, ``SYSTEMIC_ALPHA`` and ``REPEAT_ACTOR`` are set from the complete historical
population (``scripts/s36_refusal_audit.py``, ``evaluation/s36-tactical-recovery/refusal-audit.json``), never from a
Sprint 36 engine game.
"""

from __future__ import annotations

import collections
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

TAXONOMY_ID = "s36-refusal-taxonomy-1"
GATE_ID = "s36-refusal-gate-1"
SHOOT, GUIDED = 2, 9
FIRE_TYPES = frozenset({SHOOT, GUIDED})
MOVEMENT_TYPES = frozenset({1, 3, 4, 6, 10})          # move, embark, disembark, change state, stop
END_DEPLOYMENT = "333"
CLASSES = ("A", "B", "D", "R", "E")
NOT_RETAINED = "not retained"

ACTOR_GONE = "actor no longer alive at resolution"
TARGET_GONE = "target no longer alive at resolution"
OBJECTIVE_HELD = "objective already held by own side at step start"
DUPLICATE_OCCUPATION = "same-step duplicate objective occupation"

# -- calibrated constants (section 3.4; evaluation/s36-tactical-recovery/refusal-audit.json) ---------------------------
#: Pooled rates of the reference policies (``baseline-v2``, the Sprint 34 and Sprint 35 live candidates) over every
#: completed historical game whose refusal facts were retained (1,427 seat-games): race refusals per fire action (219 of
#: 28,195) and per other unit action (4 of 58,199); no redundant refusal (all three carry the shoot-target reservation).
#: ``scripts/s36_refusal_audit.py`` recomputes them and refuses to publish when they differ.
REFERENCE_RATES: Mapping[str, float] = {"race_fire": 0.00776733, "race_other": 6.873e-05, "redundant_fire": 0.0,
                                        "redundant_other": 0.0}
#: Fewest race refusals of one group that can be systemic: two never are (Sprint 35's position 19 had two races in 14
#: fire actions; nine reference games had two in at most nine).
SYSTEMIC_MIN = 3
#: Redundant refusals are avoidable by construction (the reservation), and the reference policies made none: two in one
#: game are a pattern.
REDUNDANT_MIN = 2
#: Upper binomial tail below which a race count is systemic: the largest power of ten at which no reference game of the
#: complete history triggers (at 1e-5 one does: four races in 16 fire actions).
SYSTEMIC_ALPHA = 1e-6
#: Below this many actions of a group the tail test is not used and ``SYSTEMIC_MIN`` alone decides (three races among
#: fewer than ten actions has never happened in a reference game).
MIN_DENOMINATOR = 10
#: One unit refused this many times in one game (reference maximum 2, ``baseline-v1`` up to 4).
REPEAT_ACTOR = 3
E_PER_GAME = 2
E_PER_STUDY = 3


# ------------------------------------------------------------------------------------------------ classification
def _listed(record: Mapping[str, Any]) -> bool:
    return record.get("legal_at_start") is True


def classify(record: Mapping[str, Any]) -> str:
    """The class of one refusal fact (``miaosuan-refusal-fact/1``)."""
    kind = record.get("action_type")
    message = record.get("message_class")
    label = record.get("attribution") or ""
    evidence = record.get("evidence") or {}
    if message == "ErrorActionType":
        return "A"
    if not _listed(record) or record.get("passed_project_gate") is not True:
        return "B" if kind in MOVEMENT_TYPES else "A"
    if label == ACTOR_GONE:
        return "D"
    if label == TARGET_GONE:
        shots = evidence.get("own_shots_at_target")
        if isinstance(shots, int) and shots >= 2:
            return "R"
        if isinstance(shots, int) and shots == 1:
            return "D"
        return "E"
    if label in (OBJECTIVE_HELD, DUPLICATE_OCCUPATION):
        return "R"
    return "E"


def group(action_type: Any) -> str:
    return "fire" if action_type in FIRE_TYPES else "other"


# ------------------------------------------------------------------------------------------------ one seat's game
def seat_summary(seat: Mapping[str, Any]) -> Dict[str, Any]:
    """Denominators and refusal classes of one seat of one game record (``miaosuan-game-record/1``).

    ``unit_actions`` counts the actions the seat emitted, without the deployment completion (333), which the engine does
    not echo; ``echo`` is the number of the engine's feedback entries attributed to the seat. A refusal fact list is
    required for classification; records that kept only codes are marked ``retained: False`` and never classified."""
    by_type = {str(k): int(v) for k, v in (seat.get("actions_by_type") or {}).items()}
    unit_actions = sum(v for k, v in by_type.items() if k != END_DEPLOYMENT)
    fire = sum(v for k, v in by_type.items() if k.isdigit() and int(k) in FIRE_TYPES)
    facts = seat.get("refusals")
    retained = isinstance(facts, list) and all(isinstance(r, dict) for r in facts) and "refusal_facts" in seat
    counts = {f"{c}_{g}": 0 for c in CLASSES for g in ("fire", "other")}
    per_actor: Dict[Any, int] = collections.Counter()
    by_fact: Dict[str, int] = collections.Counter()
    refused = sum(int(v) for v in (seat.get("feedback_errors_by_code") or {}).values())
    if retained:
        for r in facts:
            cls = classify(r)
            counts[f"{cls}_{group(r.get('action_type'))}"] += 1
            per_actor[r.get("obj_id")] += 1
            by_fact[f"type {r.get('action_type')} code {r.get('code')} {r.get('message_class')}: {cls}"] += 1
    shoot_refused = sum(v for k, v in (seat.get("feedback_errors_by_code_and_type") or {}).items()
                        if k.endswith("/2"))
    return {
        "policy": seat.get("policy"), "unit_actions": unit_actions, "fire_actions": fire,
        "other_actions": unit_actions - fire, "echo": seat.get("feedback_entries"),
        "echo_matches": seat.get("feedback_entries") == unit_actions, "refused": refused,
        "refused_shoot": shoot_refused, "retained": retained, "classes": counts,
        "repeat_actor_max": max(per_actor.values()) if per_actor else 0, "by_fact": dict(sorted(by_fact.items())),
        "units_seen": seat.get("units_seen"),
    }


def total(summary: Mapping[str, Any], cls: str) -> int:
    return summary["classes"][f"{cls}_fire"] + summary["classes"][f"{cls}_other"]


# ------------------------------------------------------------------------------------------------ binomial tail
def upper_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), exact (log-space terms), 1.0 for k <= 0."""
    if k <= 0:
        return 1.0
    if n <= 0 or k > n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    log_p, log_q = math.log(p), math.log1p(-p)
    terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q
             for i in range(k, n + 1)]
    top = max(terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in terms))


# ------------------------------------------------------------------------------------------------ gate alternatives
def s6_sprint35(summary: Mapping[str, Any]) -> bool:
    """Sprint 34/35's S6 as registered (kept for comparison only): more than 2% of unit actions refused, or more than
    five refused non-shoot actions."""
    non_shoot = summary["refused"] - summary["refused_shoot"]
    return summary["refused"] > 0.02 * max(1, summary["unit_actions"]) or non_shoot > 5


def absolute(summary: Mapping[str, Any], k: int) -> bool:
    return summary["refused"] >= k


def rate_with_floor(summary: Mapping[str, Any], minimum: int, share: float) -> bool:
    return summary["unit_actions"] >= minimum and summary["refused"] > share * summary["unit_actions"]


def structural_findings(summary: Mapping[str, Any], dangerous: int = 0, e_before: int = 0) -> List[str]:
    """Structural refusal findings of one game (any one closes the study). ``dangerous``: count of class C facts
    (damaging attacks on own units, undeclared action types emitted); ``e_before``: class E refusals of the same
    policy-under-test seats in earlier games of the study."""
    found = []
    if not summary["retained"]:
        found.append("refusal facts not retained: the game cannot be classified")
        return found
    if not summary["echo_matches"]:
        found.append(f"the engine echoed {summary['echo']} actions of the seat, {summary['unit_actions']} emitted")
    for cls, text in (("A", "contract refusal"), ("B", "movement or transition refusal of an unlisted action")):
        if total(summary, cls):
            found.append(f"{total(summary, cls)} {text}(s)")
    if dangerous:
        found.append(f"{dangerous} dangerous accepted action(s)")
    e = total(summary, "E")
    if e >= E_PER_GAME:
        found.append(f"{e} unexplained refusals in one game")
    elif e and e + e_before >= E_PER_STUDY:
        found.append(f"{e + e_before} unexplained refusals in the study")
    return found


def systemic_findings(summary: Mapping[str, Any], rates: Mapping[str, float] = None,
                      minimum: int = None, alpha: float = None, repeat: int = None) -> List[str]:
    """Systemic refusal patterns of one game: race or redundant refusals far above the calibrated reference rate for
    the game's own denominator, or one unit refused again and again."""
    rates = REFERENCE_RATES if rates is None else rates
    minimum = SYSTEMIC_MIN if minimum is None else minimum
    alpha = SYSTEMIC_ALPHA if alpha is None else alpha
    repeat = REPEAT_ACTOR if repeat is None else repeat
    found = []
    if not summary["retained"]:
        return found
    for cls, name, least in (("D", "race", minimum), ("R", "redundant", REDUNDANT_MIN)):
        for grp, n in (("fire", summary["fire_actions"]), ("other", summary["other_actions"])):
            k = summary["classes"][f"{cls}_{grp}"]
            if k < least:
                continue
            if n < MIN_DENOMINATOR:
                found.append(f"{k} {name} refusals of {n} {grp} actions (fewer than {MIN_DENOMINATOR} actions)")
                continue
            tail = upper_tail(k, n, rates[f"{name}_{grp}"])
            if tail < alpha:
                found.append(f"{k} {name} refusals of {n} {grp} actions (tail {tail:.2e} below {alpha})")
    if summary["repeat_actor_max"] >= repeat:
        found.append(f"one unit refused {summary['repeat_actor_max']} times")
    return found


def proposed(summary: Mapping[str, Any], rates: Mapping[str, float] = None, **kwargs: Any) -> Dict[str, List[str]]:
    return {"structural": structural_findings(summary), "systemic": systemic_findings(summary, rates, **kwargs)}


def pooled_rates(summaries: Iterable[Mapping[str, Any]]) -> Dict[str, float]:
    """Race and redundancy rates pooled over retained summaries (sum of refusals over sum of actions)."""
    sums = collections.Counter()
    for s in summaries:
        if not s["retained"]:
            continue
        sums["fire"] += s["fire_actions"]
        sums["other"] += s["other_actions"]
        for cls, name in (("D", "race"), ("R", "redundant")):
            for grp in ("fire", "other"):
                sums[f"{name}_{grp}"] += s["classes"][f"{cls}_{grp}"]
    return {f"{name}_{grp}": (round(sums[f"{name}_{grp}"] / sums[grp], 8) if sums[grp] else 0.0)
            for name in ("race", "redundant") for grp in ("fire", "other")}


__all__ = ["classify", "seat_summary", "upper_tail", "structural_findings", "systemic_findings", "proposed",
           "pooled_rates", "s6_sprint35", "absolute", "rate_with_floor", "REFERENCE_RATES", "TAXONOMY_ID", "GATE_ID"]
