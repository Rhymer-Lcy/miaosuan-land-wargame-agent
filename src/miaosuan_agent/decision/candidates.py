"""Candidate generation: every candidate originates in the current legal-action information.

* engagement: one candidate per shoot option listed in ``valid_actions`` for the unit;
* occupation: one candidate when occupation is listed for the unit;
* movement: when movement is listed for the unit, one candidate per reachable objective, with the
  ``move_path`` parameter built from the setup cost graph (``valid_actions`` reports movement
  availability only, with value ``None``);
* deployment completion: the documented exception, available while deploying.

Malformed option data is skipped with a diagnostic (fail closed), never repaired.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .context import TacticalContext, UnitContext
from .routing import ROADBLOCKED_MODES, Router, move_mode
from .semantics import MIN_ATTACK_LEVEL, ActionType


class Category(enum.Enum):
    DEPLOYMENT = "deployment"
    ENGAGE = "engage"
    OCCUPY = "occupy"
    MOVE = "move"


@dataclass(frozen=True)
class Candidate:
    """One possible action. ``rank`` sorts ascending: the smallest rank is preferred."""

    category: Category
    action_type: ActionType
    obj_id: Optional[int]
    params: Tuple[Tuple[str, Any], ...]
    rank: Tuple[Any, ...]
    detail: Tuple[Tuple[str, Any], ...] = ()

    def action(self, seat: int) -> dict:
        """The SDK action for this candidate, issued by ``seat``."""
        action = {"actor": seat, "type": int(self.action_type)}
        if self.obj_id is not None:
            action["obj_id"] = self.obj_id
        for name, value in self.params:
            action[name] = list(value) if isinstance(value, tuple) else value
        return action


def deployment_candidates(context: TacticalContext) -> List[Candidate]:
    if not context.deployment_available:
        return []
    return [Candidate(Category.DEPLOYMENT, ActionType.END_DEPLOYMENT, None, (), (0,))]


def _describe(option: Any) -> str:
    """An option's content, independent of the order in which the engine listed its fields."""
    try:
        return json.dumps(dict(option), sort_keys=True, default=repr, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(sorted(option.items(), key=lambda item: str(item[0])))


def engage_candidates(unit: UnitContext) -> Tuple[List[Candidate], List[str]]:
    """Shoot candidates plus diagnostics for skipped options (sorted, so option order never matters)."""
    options = unit.actions.get(ActionType.SHOOT)
    if not options:
        return [], []
    candidates, diagnostics = [], []
    for option in options:
        values = [option.get(name) for name in ("target_obj_id", "weapon_id", "attack_level")]
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            diagnostics.append(f"unit {unit.obj_id}: malformed shoot option skipped: {_describe(option)}")
            continue
        target, weapon, level = values
        if level < MIN_ATTACK_LEVEL:
            diagnostics.append(f"unit {unit.obj_id}: shoot option below attack level {MIN_ATTACK_LEVEL} "
                               f"skipped: {_describe(option)}")
            continue
        candidates.append(Candidate(Category.ENGAGE, ActionType.SHOOT, unit.obj_id,
                                    (("target_obj_id", target), ("weapon_id", weapon)),
                                    (-level, target, weapon), (("attack_level", level),)))
    return candidates, sorted(diagnostics)


def occupy_candidates(unit: UnitContext) -> List[Candidate]:
    if ActionType.OCCUPY not in unit.actions:
        return []
    return [Candidate(Category.OCCUPY, ActionType.OCCUPY, unit.obj_id, (), (0,))]


def move_candidates(unit: UnitContext, context: TacticalContext,
                    router: Optional[Router]) -> Tuple[List[Candidate], Optional[str]]:
    """Movement candidates, or none together with the reason."""
    if ActionType.MOVE not in unit.actions:
        return [], "movement not listed"
    if unit.move_path:
        return [], "already moving (an issued move cannot be changed)"
    if router is None:
        return [], "no movement-cost data"
    mode = move_mode(unit.unit_type, unit.move_state)
    if mode is None:
        return [], f"no documented movement mode for unit type {unit.unit_type}"
    if not context.objectives:
        return [], "no objective outside own control"
    if any(city.coord == unit.cur_hex for city in context.objectives):
        return [], "standing on an objective outside own control"
    blocked = context.roadblocks if mode in ROADBLOCKED_MODES else frozenset()
    paths = router.shortest_paths(unit.cur_hex, mode, blocked)
    candidates = []
    for city in context.objectives:
        path = paths.path_to(city.coord)
        if path:
            cost = paths.cost[city.coord]
            candidates.append(Candidate(Category.MOVE, ActionType.MOVE, unit.obj_id, (("move_path", path),),
                                        (cost, city.coord),
                                        (("destination", city.coord), ("cost", cost), ("hexes", len(path)))))
    if not candidates:
        return [], "no objective reachable"
    return candidates, None
