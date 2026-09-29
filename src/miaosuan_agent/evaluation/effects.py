"""Whether each emitted action visibly took effect, judged from the next all-seeing observation.

The engine's own feedback channel (the ``actions`` field, with an ``error`` on failure) is used
when it reports anything; this check is independent of it, because a silent engine would
otherwise make every action look accepted. Outcomes:

* ``confirmed``     the documented effect is visible after the step;
* ``not observed``  it is not (the action may have been refused, or its precondition changed
  within the step);
* ``indeterminate`` the evidence is unavailable (the unit left the view, or a field is absent).

Documented effects used: deployment completion sets the seat's ``end_deployment`` (or the play
stage begins); a move gives the unit a non-empty ``move_path`` or a new ``cur_hex``; occupation
sets the objective's ``flag`` to the faction (no waiting time); direct fire adds a ``judge_info``
record with the shooter as ``att_obj_id`` and the target as ``target_obj_id``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..boundary import ContractError, Observation, Stage
from ..decision import ActionType

CONFIRMED, NOT_OBSERVED, INDETERMINATE = "confirmed", "not observed", "indeterminate"


def _unit(observation: Observation, obj_id: int):
    for unit in observation.operators():
        if unit.obj_id == obj_id:
            return unit
    return None


def _judge_records(observation: Observation):
    records = observation.fields.get("judge_info")
    return records if isinstance(records, list) else None


def classify(action: Mapping[str, Any], faction: int, before: Observation, after: Observation,
             decision_step: int) -> str:
    """Classify one action emitted on ``before`` (the all-seeing view) against ``after``."""
    try:
        kind = action["type"]
        if kind == ActionType.END_DEPLOYMENT:
            seat = after.role_and_grouping().get(action["actor"])
            if after.time().stage == Stage.PLAY or (seat is not None and seat.end_deployment is True):
                return CONFIRMED
            return NOT_OBSERVED if seat is not None else INDETERMINATE
        unit_before, unit_after = _unit(before, action["obj_id"]), _unit(after, action["obj_id"])
        if unit_before is None or unit_after is None:
            return INDETERMINATE
        if kind == ActionType.MOVE:
            moving = unit_after.move_path
            if moving is None:
                return INDETERMINATE
            return CONFIRMED if moving or unit_after.cur_hex != unit_before.cur_hex else NOT_OBSERVED
        if kind == ActionType.OCCUPY:
            city = next((c for c in (after.cities() or ()) if c.coord == unit_before.cur_hex), None)
            if city is None or city.flag is None:
                return INDETERMINATE
            return CONFIRMED if city.flag == faction else NOT_OBSERVED
        if kind == ActionType.SHOOT:
            records = _judge_records(after)
            if records is None:
                return INDETERMINATE
            for record in records:
                if (isinstance(record, Mapping) and record.get("att_obj_id") == action["obj_id"]
                        and record.get("target_obj_id") == action["target_obj_id"]
                        and not (isinstance(record.get("cur_step"), int) and record["cur_step"] < decision_step)):
                    return CONFIRMED
            return NOT_OBSERVED
    except ContractError:
        return INDETERMINATE
    return INDETERMINATE


def feedback_actor(entry: Mapping[str, Any]) -> Optional[int]:
    """The seat that issued an entry of the ``actions`` feedback field, if recorded."""
    message = entry.get("message")
    actor = message.get("actor") if isinstance(message, Mapping) else None
    return actor if isinstance(actor, int) and not isinstance(actor, bool) else None


def feedback_error_code(entry: Mapping[str, Any]) -> Optional[Any]:
    error = entry.get("error")
    if not error:
        return None
    code = error.get("code") if isinstance(error, Mapping) else None
    return code if code is not None else "unspecified"


#: Start-of-step context classes of a refused action (instance level). Anything not matched is
#: reported as unexplained or unclassified, never assigned a benign cause by default.
DUPLICATE_OCCUPATION = "same-step: several own occupations of the objective"
OBJECTIVE_ALREADY_OWN = "objective held by own side at step start"
TARGET_SHOT_TWICE = "same-step: target fired at more than once by own side"
TARGET_ABSENT = "target absent at step start"
SHOOTER_DESTROYED = "same-step: shooter present at step start"
SHOOTER_ABSENT = "shooter absent at step start"
UNEXPLAINED = "unexplained"
UNCLASSIFIED = "unclassified"


def refusal_context(entry: Mapping[str, Any], code: Any, faction: int, start_hexes: Mapping[int, int],
                    start_flags: Mapping[int, Any], own_emitted: Any) -> str:
    """``code/action type/context class`` for one refused action, from the start of its step.

    ``start_hexes`` maps unit ids on the map at the start of the step to hexes, ``start_flags`` maps
    objective hexes to flags, and ``own_emitted`` is every action the refused action's seat emitted in
    that step.
    """
    action = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
    kind, obj_id = action.get("type"), action.get("obj_id")
    label = UNCLASSIFIED
    if kind == ActionType.OCCUPY and code == 1804:
        hex_ = start_hexes.get(obj_id)
        same_hex = sum(1 for a in own_emitted if a.get("type") == ActionType.OCCUPY
                       and start_hexes.get(a.get("obj_id")) == hex_)
        if hex_ is not None and start_flags.get(hex_) == faction:
            label = OBJECTIVE_ALREADY_OWN
        elif hex_ is not None and same_hex >= 2:
            label = DUPLICATE_OCCUPATION
        else:
            label = UNEXPLAINED
    elif kind == ActionType.SHOOT and code == 516:
        target = action.get("target_obj_id")
        shots = sum(1 for a in own_emitted if a.get("type") == ActionType.SHOOT and a.get("target_obj_id") == target)
        label = TARGET_ABSENT if target not in start_hexes else TARGET_SHOT_TWICE if shots >= 2 else UNEXPLAINED
    elif kind == ActionType.SHOOT and code == 203:
        label = SHOOTER_DESTROYED if obj_id in start_hexes else SHOOTER_ABSENT
    return f"{code}/{kind}/{label}"
