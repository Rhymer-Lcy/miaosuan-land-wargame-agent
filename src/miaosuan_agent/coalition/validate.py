"""Independent validation of the coalition agent's actions: Sprint 34's validator plus guided fire.

Every action other than guided fire (action 9) goes through ``integrated.validate.validate`` unchanged. A guided-fire
action passes only when it is a mapping with exactly the keys ``actor``, ``type``, ``obj_id``, ``target_obj_id``,
``weapon_id`` and ``guided_obj_id``; the actor is this seat; the stage is play; the unit is controllable and on the map;
it has no other action in the step; action 9 is listed for it; (target, weapon, guided carrier) equals one listed option
exactly; and the guided carrier has no action of its own in the step. One action per unit holds across both validators.
"""

from __future__ import annotations

from typing import Any, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import Stage
from ..integrated import facts as F
from ..integrated.validate import Verdict, validate as base_validate
from ..integrated.world import World

GUIDED_KEYS = frozenset({"actor", "type", "obj_id", "target_obj_id", "weapon_id", "guided_obj_id"})


def _guided_problem(action: Mapping[str, Any], world: World, seen: Set[int], carriers_acting: Set[int]) -> Optional[str]:
    if set(action) != GUIDED_KEYS:
        return f"keys {sorted(map(str, action))} differ from {sorted(GUIDED_KEYS)}"
    if not F.is_int(action["actor"]) or action["actor"] != world.seat:
        return "actor is not this seat"
    if world.stage != Stage.PLAY:
        return f"unit action in stage {world.stage}"
    obj_id = action["obj_id"]
    unit = world.unit(obj_id) if F.is_int(obj_id) else None
    if unit is None:
        return "obj_id is not a controllable unit on the map"
    if obj_id in seen:
        return "second action for the same unit in one step"
    if F.GUIDED not in unit.actions:
        return "action type not listed for the unit"
    chosen = [action["target_obj_id"], action["weapon_id"], action["guided_obj_id"]]
    if not all(F.is_int(v) for v in chosen):
        return "option parameters must be ints"
    offered = [[o.get("target_obj_id"), o.get("weapon_id"), o.get("guided_obj_id")] for o in unit.actions[F.GUIDED] or ()]
    if chosen not in offered:
        return "parameters match no listed option"
    if action["guided_obj_id"] in carriers_acting:
        return "the guided carrier has its own action in this step"
    return None


def validate(actions: Sequence[Any], world: World, terrain, enabled: FrozenSet[int], deployment_available: bool,
             guided_enabled: bool) -> Verdict:
    plain = [a for a in actions if not (isinstance(a, Mapping) and a.get("type") == F.GUIDED)]
    guided = [a for a in actions if isinstance(a, Mapping) and a.get("type") == F.GUIDED]
    base = base_validate(plain, world, terrain, enabled, deployment_available)
    accepted: List[Mapping[str, Any]] = list(base.accepted)
    rejected: List[Tuple[Any, Any, str]] = list(base.rejected)
    seen: Set[int] = {a["obj_id"] for a in accepted if "obj_id" in a}
    for action in guided:
        if not guided_enabled:
            problem = "action type not in the enabled catalog"
        else:
            problem = _guided_problem(action, world, seen, seen)
        if problem is not None:
            rejected.append((F.GUIDED, action.get("obj_id") if F.is_int(action.get("obj_id")) else None, problem))
            continue
        seen.add(action["obj_id"])
        seen.add(action["guided_obj_id"])
        accepted.append(dict(action))
    return Verdict(tuple(accepted), tuple(rejected))
