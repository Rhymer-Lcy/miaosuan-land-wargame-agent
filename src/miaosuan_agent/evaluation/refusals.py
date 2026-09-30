"""Engine refusals: the factual record first, a separately versioned attribution second.

A refusal is an entry of the engine's all-seeing ``actions`` feedback that carries an ``error``.
Its factual class is the triple (action type, error code, normalized engine message). The same
code can occur under different action types: code 203 with the message ``CantControlDiedOperator``
has been recorded on shots and on occupations, and those are two factual classes. Nothing about a
refusal's cause is read from its code.

Each refusal is recorded with what the harness can establish without interpretation: the decision
index and the engine step, the action the engine echoed, whether that action is one the seat
emitted in the step (every emitted action had passed the project safety gate, so this is the
gate fact), and whether its type (and, for a shot, its target and weapon) was listed for the unit
in the seat's start-of-step ``valid_actions``.

Attribution (``ATTRIBUTION_VERSION``) is a separate layer. A causal label is assigned only when the
factual class matches a rule of ``RULES`` and the evidence the rule names, read from the all-seeing
states before and after the step, is present and agrees with it. Otherwise the label states that
no rule covers the class, that evidence was missing, or that the evidence contradicted the rule.
Earlier layers are kept for their historical results and are not used by this one: the
start-of-step context classes of :func:`.effects.refusal_context` (attribution 1) and the
code-level categories of the occupation-reservation manifest, whose category for code 203 named
shots only.

Recording never raises: a failure while gathering evidence is stored with the refusal, because the
analysis layer must not be able to end a game.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

FACT_SCHEMA = "miaosuan-refusal-fact/1"
ATTRIBUTION_VERSION = "refusal-attribution/2"
MESSAGE_LIMIT = 120
NO_MESSAGE = "(no message)"
MOVE, SHOOT, OCCUPY = 1, 2, 5

DUPLICATE_OCCUPATION = "same-step duplicate objective occupation"
OBJECTIVE_HELD = "objective already held by own side at step start"
TARGET_GONE = "target no longer alive at resolution"
ACTOR_GONE = "actor no longer alive at resolution"
NO_RULE = "unclassified: no attribution rule for this factual class"
MISSING = "unclassified: evidence missing"
CONTRADICTED = "unclassified: evidence contradicts the rule"
EVIDENCE_FAILED = "unclassified: evidence could not be gathered"


@dataclass(frozen=True)
class Rule:
    """One attribution rule: the factual classes it covers and the evidence it requires."""

    code: int
    message: str
    action_types: Optional[FrozenSet[int]]  # None: any action type
    labels: Tuple[str, ...]
    evidence: str


RULES = (
    Rule(1804, "CantOccupyCauseAlreadyMy", frozenset({OCCUPY}), (OBJECTIVE_HELD, DUPLICATE_OCCUPATION),
         "objective held by own side at step start -> held; otherwise at least two own occupations of the "
         "objective in the step and the objective held by own side after it -> duplicate"),
    Rule(516, "CantShootToDiedBop", frozenset({SHOOT}), (TARGET_GONE,),
         "target on the map at step start and in no unit list after the step"),
    Rule(203, "CantControlDiedOperator", None, (ACTOR_GONE,),
         "acting unit on the map at step start and in no unit list after the step, whatever the action type"),
)


def normalize_message(message: Any) -> str:
    """The engine message with numbers replaced and whitespace collapsed, so it can be counted publicly."""
    if message is None:
        return NO_MESSAGE
    text = re.sub(r"-?\d+(?:\.\d+)?", "N", " ".join(str(message).split()))
    return text[:MESSAGE_LIMIT] or NO_MESSAGE


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def same_action(echo: Mapping[str, Any], emitted: Mapping[str, Any]) -> bool:
    """Whether the engine's echo of an action is the action emitted, on the fields that identify it."""
    for key in ("type", "obj_id", "target_obj_id", "weapon_id"):
        if echo.get(key) != emitted.get(key):
            return False
    return list(echo.get("move_path") or []) == list(emitted.get("move_path") or [])


def listed_at_start(action: Mapping[str, Any], valid_actions: Mapping[int, Mapping[int, Any]]) -> bool:
    """Whether the action's type (and, for a shot, its target and weapon) was listed for the unit."""
    listed = valid_actions.get(action.get("obj_id"))
    if not listed or action.get("type") not in listed:
        return False
    if action.get("type") != SHOOT:
        return True
    return any(option.get("target_obj_id") == action.get("target_obj_id")
               and option.get("weapon_id") == action.get("weapon_id") for option in listed[SHOOT] or ())


def fact(entry: Mapping[str, Any], code: Any, decision_index: int, engine_step: Optional[int],
         own_emitted: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The factual record of one refused action (no interpretation)."""
    action, error = _mapping(entry.get("message")), _mapping(entry.get("error"))
    raw = error.get("message")
    record = {"schema": FACT_SCHEMA, "decision_index": decision_index, "engine_step": engine_step,
              "action_type": action.get("type"), "obj_id": action.get("obj_id"), "code": code,
              "message": None if raw is None else str(raw)[:200], "message_class": normalize_message(raw),
              "passed_project_gate": any(same_action(action, emitted) for emitted in own_emitted),
              "legal_at_start": None}
    if action.get("type") == SHOOT:
        record.update(target_obj_id=action.get("target_obj_id"), weapon_id=action.get("weapon_id"))
    return record


def evidence(action: Mapping[str, Any], faction: int, before: Any, after: Any,
             own_emitted: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Facts about the step read from the all-seeing observations ``before`` and ``after`` it.

    "On the map" means listed in ``operators``; "present" means listed in ``operators`` or
    ``passengers`` (a unit that boarded is present, a destroyed unit is in neither list).
    """
    start = {unit.obj_id: unit.cur_hex for unit in before.operators()}
    present_after = {unit.obj_id for unit in after.operators()} | {unit.obj_id for unit in after.passengers()}
    actor, kind = action.get("obj_id"), action.get("type")
    result: Dict[str, Any] = {"actor_on_map_at_start": actor in start, "actor_present_after": actor in present_after}
    if kind == SHOOT:
        target = action.get("target_obj_id")
        result.update(target_on_map_at_start=target in start, target_present_after=target in present_after,
                      own_shots_at_target=sum(1 for a in own_emitted
                                              if a.get("type") == SHOOT and a.get("target_obj_id") == target))
    if kind == OCCUPY:
        hex_ = start.get(actor)
        flags_before = {city.coord: city.flag for city in (before.cities() or ())}
        flags_after = {city.coord: city.flag for city in (after.cities() or ())}
        result.update(
            objective_own_at_start=None if hex_ not in flags_before else flags_before[hex_] == faction,
            objective_own_after=None if hex_ not in flags_after else flags_after[hex_] == faction,
            own_occupations_of_objective=None if hex_ is None else sum(
                1 for a in own_emitted if a.get("type") == OCCUPY and start.get(a.get("obj_id")) == hex_))
    return result


def _code(value: Any) -> Any:
    """An error code as an int when it is one, in either the int or the string spelling."""
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def rule_for(record: Mapping[str, Any]) -> Optional[Rule]:
    for rule in RULES:
        if (_code(record.get("code")), record.get("message_class")) == (rule.code, rule.message) and (
                rule.action_types is None or record.get("action_type") in rule.action_types):
            return rule
    return None


def attribute(record: Mapping[str, Any], facts: Optional[Mapping[str, Any]]) -> str:
    """The attribution-2 label of one refusal from its factual record and its step evidence."""
    rule = rule_for(record)
    if rule is None:
        return NO_RULE
    if facts is None:
        return EVIDENCE_FAILED
    if rule.code == 1804:
        held, after, count = (facts.get("objective_own_at_start"), facts.get("objective_own_after"),
                              facts.get("own_occupations_of_objective"))
        if held is None:
            return MISSING
        if held:
            return OBJECTIVE_HELD
        if after is None or count is None:
            return MISSING
        return DUPLICATE_OCCUPATION if count >= 2 and after else CONTRADICTED
    subject = "target" if rule.code == 516 else "actor"
    at_start, present = facts.get(f"{subject}_on_map_at_start"), facts.get(f"{subject}_present_after")
    if at_start is None or present is None:
        return MISSING
    if at_start and not present:
        return rule.labels[0]
    return CONTRADICTED


def describe(entry: Mapping[str, Any], code: Any, faction: int, decision_index: int, before_view: Any,
             after: Any, own_emitted: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Fact, evidence and attribution of one refusal. ``before_view`` is the harness's state view at the
    start of the step (all-seeing and per-faction); ``after`` the all-seeing observation after it."""
    engine_step = None
    try:
        engine_step = before_view.global_observation.time().cur_step
    except Exception:  # noqa: BLE001 - a missing step number is recorded as None
        pass
    record = fact(entry, code, decision_index, engine_step, own_emitted)
    try:
        record["legal_at_start"] = listed_at_start(_mapping(entry.get("message")),
                                                   before_view.for_faction(faction).valid_actions())
    except Exception as exc:  # noqa: BLE001 - recorded, never raised
        record["legal_at_start_error"] = type(exc).__name__
    try:
        facts: Optional[Dict[str, Any]] = evidence(_mapping(entry.get("message")), faction,
                                                   before_view.global_observation, after, own_emitted)
    except Exception as exc:  # noqa: BLE001 - recorded, never raised
        facts = None
        record["evidence_error"] = type(exc).__name__
    record["evidence"] = facts
    record["attribution"] = attribute(record, facts)
    return record


def fact_key(record: Mapping[str, Any]) -> Tuple[Any, Any, str]:
    return record.get("action_type"), record.get("code"), record.get("message_class")


def fact_counts(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Counts by factual class, as a sorted list (JSON object keys would have to encode the triple)."""
    counts: Dict[Tuple[Any, Any, str], int] = {}
    for record in records:
        counts[fact_key(record)] = counts.get(fact_key(record), 0) + 1
    return [{"action_type": kind, "code": code, "message_class": message, "count": count}
            for (kind, code, message), count in sorted(counts.items(), key=lambda item: str(item[0]))]


def attribution_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in records:
        counts[record["attribution"]] = counts.get(record["attribution"], 0) + 1
    return dict(sorted(counts.items()))


def merge_fact_counts(lists: Sequence[Sequence[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    """Sum several ``fact_counts`` lists."""
    counts: Dict[Tuple[Any, Any, str], int] = {}
    for items in lists:
        for item in items:
            key = (item["action_type"], item["code"], item["message_class"])
            counts[key] = counts.get(key, 0) + item["count"]
    return [{"action_type": kind, "code": code, "message_class": message, "count": count}
            for (kind, code, message), count in sorted(counts.items(), key=lambda item: str(item[0]))]
