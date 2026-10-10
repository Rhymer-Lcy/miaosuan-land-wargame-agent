"""Independent validation of every action the integrated agent emits.

It re-derives each check from the seat's observation (through the world view), the setup cost graph and the catalog
below, never from the planner's own reasoning, and rejects instead of repairing. An action passes only when:

* it is a mapping with an int ``type`` in the catalog of enabled actions and exactly the catalogued keys;
* ``actor`` is this seat and the stage allows the type (deployment completion only while deploying, at most once;
  unit actions only in play);
* ``obj_id`` is a unit this seat controls in this observation, with no other action in this step;
* the type is listed for the unit in the current ``valid_actions``;
* option parameters equal one listed option: shoot (target, weapon), embark (target), disembark (target), indirect
  fire (weapon); indirect fire's ``jm_pos`` is a hex inside the map;
* a move's unit has no move path, has a documented movement mode, and ``move_path`` is a non-empty list of distinct int
  hexes, each a traversable neighbour of the previous one in that mode, never the start hex, never a roadblock for a
  vehicle mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import Stage
from ..decision.routing import ROADBLOCKED_MODES
from . import facts as F
from .movement import Terrain, unit_mode
from .world import World

KEYS: Mapping[int, FrozenSet[str]] = {
    F.MOVE: frozenset({"actor", "type", "obj_id", "move_path"}),
    F.SHOOT: frozenset({"actor", "type", "obj_id", "target_obj_id", "weapon_id"}),
    F.GET_ON: frozenset({"actor", "type", "obj_id", "target_obj_id"}),
    F.GET_OFF: frozenset({"actor", "type", "obj_id", "target_obj_id"}),
    F.OCCUPY: frozenset({"actor", "type", "obj_id"}),
    F.INDIRECT: frozenset({"actor", "type", "obj_id", "jm_pos", "weapon_id"}),
    F.END_DEPLOYMENT: frozenset({"actor", "type"}),
}
OPTION_FIELDS: Mapping[int, Tuple[str, ...]] = {
    F.SHOOT: ("target_obj_id", "weapon_id"), F.GET_ON: ("target_obj_id",), F.GET_OFF: ("target_obj_id",),
    F.INDIRECT: ("weapon_id",),
}


@dataclass(frozen=True)
class Verdict:
    accepted: Tuple[Mapping[str, Any], ...]
    rejected: Tuple[Tuple[Any, Any, str], ...]


def _problem(action: Any, world: World, terrain: Optional[Terrain], enabled: FrozenSet[int], seen: Set[int],
             deployment_seen: bool, deployment_available: bool) -> Optional[str]:
    if not isinstance(action, Mapping):
        return "action is not a mapping"
    kind = action.get("type")
    if not F.is_int(kind) or kind not in KEYS or kind not in enabled:
        return "action type not in the enabled catalog"
    if set(action) != KEYS[kind]:
        return f"keys {sorted(map(str, action))} differ from {sorted(KEYS[kind])}"
    if not F.is_int(action["actor"]) or action["actor"] != world.seat:
        return "actor is not this seat"
    if kind == F.END_DEPLOYMENT:
        if world.stage != Stage.DEPLOYMENT:
            return "deployment completion outside the deployment stage"
        if deployment_seen:
            return "duplicate deployment completion"
        if not deployment_available:
            return "deployment completion not available"
        return None
    if world.stage != Stage.PLAY:
        return f"unit action in stage {world.stage}"
    obj_id = action["obj_id"]
    unit = world.unit(obj_id) if F.is_int(obj_id) else None
    if unit is None:
        return "obj_id is not a controllable unit on the map"
    if obj_id in seen:
        return "second action for the same unit in one step"
    if kind not in unit.actions:
        return "action type not listed for the unit"
    if kind in OPTION_FIELDS:
        fields = OPTION_FIELDS[kind]
        chosen = [action[name] for name in fields]
        if not all(F.is_int(v) for v in chosen):
            return "option parameters must be ints"
        offered = [[option.get(name) for name in fields] for option in unit.actions[kind] or ()]
        if chosen not in offered:
            return "parameters match no listed option"
        if kind == F.INDIRECT:
            pos = action["jm_pos"]
            if not F.is_int(pos) or not (0 <= pos // 100 < world.rows and 0 <= pos % 100 < world.cols):
                return "jm_pos is not a hex inside the map"
        return None
    if kind == F.MOVE:
        if terrain is None:
            return "no movement-cost data to check the path"
        if unit.path:
            return "unit is executing a move, which cannot be changed"
        mode = unit_mode(unit.type, unit.move_state)
        if mode is None:
            return "unit type has no documented movement mode"
        path = action["move_path"]
        if not isinstance(path, list) or not path or not all(F.is_int(h) for h in path):
            return "move_path must be a non-empty list of int hexes"
        if len(set(path)) != len(path) or unit.hex in path:
            return "move_path repeats a hex or revisits the start"
        blocked = world.roadblocks if mode in ROADBLOCKED_MODES else frozenset()
        here = unit.hex
        for hex_ in path:
            if hex_ not in terrain.costs.neighbours(mode, here):
                return f"hex {hex_} is not a traversable neighbour of {here}"
            if hex_ in blocked:
                return f"hex {hex_} is a roadblock"
            here = hex_
        return None
    return None


def validate(actions: Sequence[Any], world: World, terrain: Optional[Terrain], enabled: FrozenSet[int],
             deployment_available: bool) -> Verdict:
    accepted: List[Mapping[str, Any]] = []
    rejected: List[Tuple[Any, Any, str]] = []
    seen: Set[int] = set()
    deployment_seen = False
    for action in actions:
        problem = _problem(action, world, terrain, enabled, seen, deployment_seen, deployment_available)
        fields = action if isinstance(action, Mapping) else {}
        if problem is not None:
            rejected.append((fields.get("type") if F.is_int(fields.get("type")) else None,
                             fields.get("obj_id") if F.is_int(fields.get("obj_id")) else None, problem))
            continue
        if action["type"] == F.END_DEPLOYMENT:
            deployment_seen = True
        else:
            seen.add(action["obj_id"])
        accepted.append(dict(action))
    return Verdict(tuple(accepted), tuple(rejected))
