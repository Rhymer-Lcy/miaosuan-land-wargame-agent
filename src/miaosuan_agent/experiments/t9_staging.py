"""EXPLORATORY ``t9-capacity-staging-v2``: preserve baseline routes while bounding objective arrivals.

T9-v1's cross-objective replacements fixed objective queues, but Sprint 10 full-step captures showed two
side-effects: slow, distant replacements could reserve all four slots of a valuable objective for the whole game,
and a replacement could remove the movement corridor that later produced a legal firing opportunity.  This
revision keeps the four-unit objective cap but never substitutes another objective.

When a baseline ground move would exceed the destination's four commitments, the move is shortened to the nearest
non-objective hex on the same baseline path whose own endpoint has fewer than four commitments.  The unit therefore
advances along the baseline corridor, stops before joining the full objective, and is reconsidered from a fresh
seat-local observation.  If no such staging endpoint exists, the move is withheld.  Staging actions are gated with
the same project safety gate; a rejected staging action is withheld rather than reverting to the over-capacity
baseline move.

Only the diagnosed seat's observation, baseline action and setup movement costs are used.  Shooting, occupation,
aviation and every unrelated baseline action are unchanged.  The policy is exploratory and is not eligible for
baseline promotion.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..boundary import Observation, Stage
from ..decision import gate
from ..decision.context import build_context
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int

CANDIDATE_ID = "t9-capacity-staging-v2"
MOVE = 1
GROUND = (1, 2)
CAPACITY = 4


def destination(action: Mapping[str, Any]) -> Optional[int]:
    path = action.get("move_path")
    if isinstance(path, (list, tuple)) and path and is_int(path[-1]):
        return path[-1]
    return None


def _stage(action: Mapping[str, Any], cities: Mapping[int, Any], endpoints: collections.Counter) -> Optional[Dict[str, Any]]:
    path = action.get("move_path")
    if not isinstance(path, (list, tuple)) or len(path) < 2:
        return None
    for index in range(len(path) - 2, -1, -1):
        coord = path[index]
        if is_int(coord) and coord not in cities and endpoints[coord] < CAPACITY:
            replacement = dict(action)
            replacement["move_path"] = list(path[:index + 1])
            return replacement
    return None


class StagingAddon(Addon):
    name = "t9_staging"

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        actions = tuple(base.actions)
        if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
            return AddonResult(actions)
        context = build_context(observation, seat, faction)
        router = self.baseline.router
        if router is None:
            return AddonResult(actions, skipped=(("no movement-cost data", 1),))
        cities = {city.coord: city for city in (observation.cities() or ())}
        router.targets = frozenset(cities)
        own_ground = {unit.obj_id: unit for unit in observation.operators()
                      if unit.color == faction and unit.fields.get("type") in GROUND}
        commitments: collections.Counter = collections.Counter()
        endpoints: collections.Counter = collections.Counter()
        for unit in own_ground.values():
            path = unit.move_path or ()
            end = path[-1] if path else unit.cur_hex
            endpoints[end] += 1
            if end in cities:
                commitments[end] += 1

        final: List[Optional[Mapping[str, Any]]] = []
        planned: List[Tuple[int, Mapping[str, Any], Mapping[str, Any]]] = []
        changes: List[Dict[str, Any]] = []
        skipped: collections.Counter = collections.Counter()
        for action in actions:
            obj_id = action.get("obj_id")
            if action.get("type") != MOVE or obj_id not in own_ground:
                final.append(action)
                continue
            dest = destination(action)
            if dest is None:
                final.append(action)
                skipped["move without a readable destination"] += 1
                continue
            if commitments[dest] < CAPACITY:
                commitments[dest] += 1
                endpoints[dest] += 1
                final.append(action)
                skipped["kept: destination under capacity"] += 1
                continue
            replacement = _stage(action, cities, endpoints)
            if replacement is None:
                final.append(None)
                changes.append({"kind": "withhold", "obj_id": obj_id, "destination": dest,
                                "commitments": commitments[dest],
                                "reason": "no same-route staging endpoint under capacity"})
                continue
            stage = destination(replacement)
            endpoints[stage] += 1
            planned.append((len(final), action, replacement))
            final.append(replacement)
            changes.append({"kind": "stage", "obj_id": obj_id, "destination": dest, "staging": stage,
                            "commitments": commitments[dest], "path_length": len(action["move_path"]),
                            "staged_path_length": len(replacement["move_path"])})

        proposals = [action for action in final if action is not None]
        checked = gate.check(proposals, context, router)
        rejected = {rejection.obj_id: rejection.reason for rejection in checked.rejected}
        for index, original, replacement in planned:
            obj_id = replacement["obj_id"]
            if obj_id in rejected:
                final[index] = None
                changes.append({"kind": "stage-rejected", "obj_id": original["obj_id"],
                                "reason": rejected[obj_id]})
        emitted = tuple(action for action in final if action is not None)
        return AddonResult(emitted, tuple(changes), tuple(sorted(skipped.items())))


class StagingPolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = StagingAddon


class StagingAgent(AddonAgent):
    policy_class = StagingPolicy
