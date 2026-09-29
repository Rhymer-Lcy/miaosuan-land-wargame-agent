"""The final safety gate: nothing leaves the policy layer without passing it.

The gate trusts nothing the policy computed. It re-derives every check from the tactical context
and the action catalog, and rejects (with a reason) instead of repairing:

* the action is a mapping whose ``type`` is a catalogued int action type;
* its key set is exactly the catalogued one, and ``actor`` is this seat;
* the current stage is one the action is allowed in;
* deployment completion: available to the seat, and at most once per step;
* unit actions: ``obj_id`` is a controllable unit, the unit has no other action this step, and the
  type is listed for the unit in the current ``valid_actions``;
* option parameters (shoot): ints equal to one option listed in ``valid_actions``;
* constructed paths (move): the unit is not executing a move (the rules forbid changing an issued
  move), and ``move_path`` is a non-empty list of distinct int hexes, each a traversable neighbour
  of the previous one in the unit's cost mode, never the start hex, never a roadblock for vehicles.

Rejected actions are not emitted; the remaining actions of the step are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Set, Tuple

from .context import TacticalContext
from .routing import ROADBLOCKED_MODES, Router, move_mode
from .semantics import CATALOG, ActionType, Legality, Parameters


@dataclass(frozen=True)
class Rejection:
    action_type: Any
    obj_id: Any
    reason: str


@dataclass(frozen=True)
class GateResult:
    accepted: Tuple[Mapping[str, Any], ...]
    rejected: Tuple[Rejection, ...]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _label(value: Any) -> Any:
    """A JSON-safe label for a field of a rejected action."""
    return value if value is None or _is_int(value) else repr(value)


def _path_problem(path: Any, start: int, mode, blocked, router: Optional[Router]) -> Optional[str]:
    if router is None:
        return "no movement-cost data to check the path"
    if not isinstance(path, list) or not path or not all(_is_int(h) for h in path):
        return "move_path must be a non-empty list of int hexes"
    if len(set(path)) != len(path) or start in path:
        return "move_path repeats a hex or revisits the start"
    previous = start
    for hex_ in path:
        if hex_ not in router.costs.neighbours(mode, previous):
            return f"hex {hex_} is not a traversable neighbour of {previous}"
        if hex_ in blocked:
            return f"hex {hex_} is a roadblock"
        previous = hex_
    return None


def _problem(action: Any, context: TacticalContext, router: Optional[Router], seen_units: Set[int],
             deployment_seen: bool) -> Optional[str]:
    """Why ``action`` must not be emitted, or ``None`` when it may."""
    if not isinstance(action, Mapping):
        return "action is not a mapping"
    action_type = action.get("type")
    if not _is_int(action_type) or action_type not in CATALOG:
        return "action type not in the catalog"
    semantics = CATALOG[ActionType(action_type)]
    if set(action) != semantics.keys:
        return f"keys {sorted(map(str, action))} differ from {sorted(semantics.keys)}"
    if not _is_int(action["actor"]) or action["actor"] != context.seat:
        return "actor is not this seat"
    if context.stage not in semantics.stages:
        return f"not allowed in stage {context.stage}"
    if semantics.legality is Legality.DEPLOYMENT_EXCEPTION:
        if deployment_seen:
            return "duplicate deployment completion"
        if not context.deployment_available:
            return "deployment completion not available"
        return None
    obj_id = action["obj_id"]
    unit = context.unit(obj_id) if _is_int(obj_id) else None
    if unit is None:
        return "obj_id is not a controllable unit"
    if obj_id in seen_units:
        return "second action for the same unit in one step"
    if semantics.action_type not in unit.actions:
        return "action type not listed for the unit in valid_actions"
    if semantics.parameters is Parameters.OPTION:
        chosen = [action[name] for name in semantics.fields]
        if not all(_is_int(value) for value in chosen):
            return "option parameters must be ints"
        offered = [[option.get(name) for name in semantics.fields]
                   for option in unit.actions[semantics.action_type] or ()]
        if chosen not in offered:
            return "parameters match no option in valid_actions"
    elif semantics.parameters is Parameters.CONSTRUCTED_PATH:
        if unit.move_path:
            return "unit is executing a move, which cannot be changed"
        mode = move_mode(unit.unit_type, unit.move_state)
        if mode is None:
            return "unit type has no documented movement mode"
        blocked = context.roadblocks if mode in ROADBLOCKED_MODES else frozenset()
        return _path_problem(action["move_path"], unit.cur_hex, mode, blocked, router)
    return None


def check(actions: Sequence[Any], context: TacticalContext, router: Optional[Router]) -> GateResult:
    """Split ``actions`` into the ones that may be emitted (in order) and the rejected ones."""
    accepted: List[Mapping[str, Any]] = []
    rejected: List[Rejection] = []
    seen_units: Set[int] = set()
    deployment_seen = False
    for action in actions:
        problem = _problem(action, context, router, seen_units, deployment_seen)
        if problem is not None:
            fields = action if isinstance(action, Mapping) else {}
            rejected.append(Rejection(_label(fields.get("type")), _label(fields.get("obj_id")), problem))
            continue
        if action["type"] == ActionType.END_DEPLOYMENT:
            deployment_seen = True
        else:
            seen_units.add(action["obj_id"])
        accepted.append(dict(action))
    return GateResult(accepted=tuple(accepted), rejected=tuple(rejected))
