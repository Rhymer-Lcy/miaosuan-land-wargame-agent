"""Counterfactual comparison of ``baseline-v0`` and the occupation-reservation candidate on one input.

Both policies decide on the same canonical start-of-step observation. The candidate's registered
change predicts its output exactly, through an oracle that does not use the candidate's code:

* duplicate occupiers are the units whose v0 selection is an occupation of an objective that an
  earlier unit, in v0's own processing order, already selected in the step (read off v0's trace);
* with none, the candidate must equal v0: same actions, same memory, same trace apart from the
  policy name, the trace schema and an empty suppression list;
* with some, the candidate must suppress exactly those units, in that order, and its actions must
  equal what v0 emits when occupation is withdrawn from exactly those units' legal actions;
  every other unit's action must be identical to v0's.

Anything else is an unexplained delta.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ..boundary import Observation, Origin
from ..decision import BaselinePolicy, Decision, Memory, StepTrace

OCCUPY = 5


def duplicate_occupiers(trace: StepTrace, observation: Observation) -> Tuple[int, ...]:
    hexes = {unit.obj_id: unit.cur_hex for unit in observation.operators()}
    claimed, duplicates = set(), []
    for unit in trace.units:
        if unit.rule == "occupy":
            hex_ = hexes[unit.obj_id]
            if hex_ in claimed:
                duplicates.append(unit.obj_id)
            else:
                claimed.add(hex_)
    return tuple(duplicates)


def without_occupation(raw: Mapping[str, Any], obj_ids: Sequence[int]) -> Dict[str, Any]:
    """A copy of the raw observation in which the listed units' legal actions no longer offer occupation."""
    result = copy.deepcopy(dict(raw))
    targets = set(obj_ids)
    for key, per_unit in result["valid_actions"].items():
        if int(key) in targets:
            for action_key in [k for k in per_unit if int(k) == OCCUPY]:
                del per_unit[action_key]
    return result


def normalized(trace: StepTrace) -> Dict[str, Any]:
    payload = trace.to_dict()
    for key in ("policy", "schema", "suppressed"):
        payload.pop(key, None)
    return payload


def _by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, Mapping[str, Any]]:
    return {action.get("obj_id", "seat"): dict(action) for action in actions}


@dataclass(frozen=True)
class StateComparison:
    identical: bool
    explained: bool
    duplicates: Tuple[int, ...]
    suppressed: Tuple[int, ...]
    changed_types: Tuple[int, ...]  # types of v0 actions absent from, or different in, the candidate output
    problem: Optional[str] = None


def compare(raw: Mapping[str, Any], seat: int, faction: int, v0: BaselinePolicy, candidate: BaselinePolicy,
            v0_memory: Memory, candidate_memory: Memory, origin: Origin = Origin.ENGINE,
            ) -> Tuple[StateComparison, Decision, Decision]:
    observation = Observation.from_raw(raw, origin)
    first = v0.decide(observation, seat, faction, v0_memory)
    second = candidate.decide(Observation.from_raw(raw, origin), seat, faction, candidate_memory)
    duplicates = duplicate_occupiers(first.trace, observation)
    suppressed = tuple(entry[0] for entry in getattr(second.trace, "suppressed", ()))
    old, new = _by_unit(first.actions), _by_unit(second.actions)
    changed = tuple(sorted({int(action["type"]) for key, action in old.items() if new.get(key) != action}))

    def result(explained: bool, problem: Optional[str]) -> Tuple[StateComparison, Decision, Decision]:
        return (StateComparison(identical=explained and not duplicates, explained=explained, duplicates=duplicates,
                                suppressed=suppressed, changed_types=changed, problem=problem), first, second)

    if first.memory != second.memory:
        return result(False, "memory differs")
    if not duplicates:
        if suppressed:
            return result(False, "suppression without a duplicate occupier")
        if tuple(first.actions) != tuple(second.actions):
            return result(False, "actions differ without a duplicate occupier")
        if normalized(first.trace) != normalized(second.trace):
            return result(False, "trace differs without a duplicate occupier")
        return result(True, None)
    if suppressed != duplicates:
        return result(False, f"suppressed {suppressed} but duplicate occupiers are {duplicates}")
    oracle = BaselinePolicy(v0.router.costs if v0.router else None).decide(
        Observation.from_raw(without_occupation(raw, duplicates), origin), seat, faction, v0_memory)
    if tuple(oracle.actions) != tuple(second.actions):
        return result(False, "actions differ from the oracle")
    # Implied by the oracle comparison above (the oracle equals v0 for every unit that is not a
    # duplicate occupier); kept to name that failure explicitly.
    for key, action in old.items():
        if key not in duplicates and new.get(key) != action:
            return result(False, f"a non-duplicate unit's action changed ({key})")
    if any(old[key]["type"] != OCCUPY for key in duplicates):
        return result(False, "a duplicate occupier's v0 action is not an occupation")
    return result(True, None)
