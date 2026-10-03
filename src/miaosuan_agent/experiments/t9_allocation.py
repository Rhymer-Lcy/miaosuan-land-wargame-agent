"""EXPLORATORY candidate ``t9-capacity-allocation-v1``: stop ``baseline-v2`` from over-committing ground units to one
objective.

EXPLORATORY track (``docs/EXPLORATORY_TRACK.md``): not eligible for baseline promotion, never packaged.

``baseline-v2`` decides first, unchanged (:mod:`.exploratory_addon`). It sends every movable unit to the cheapest
objective its side does not hold, so in the large scenarios a dozen or more ground units converge on one objective
hex, which holds at most four own ground units; the rest queue in front of full hexes, and an issued move cannot be
changed (``docs/T1R_DIAGNOSIS.md``, ``docs/PS1_ENGINE_PROBE.md``). This add-on edits only ``baseline-v2``'s move
orders for ground units (types 1 and 2), in ``baseline-v2``'s emission order:

* commitments: for every objective hex, the own ground units standing on it with no move path, plus those whose
  move path ends on it, plus the moves already kept or assigned in this step;
* a move whose destination has fewer than ``CAPACITY`` commitments is kept and counted;
* otherwise the unit is re-assigned to the objective outside own control with fewer than ``CAPACITY`` commitments
  that minimises path cost divided by objective value (``value``, 1 when absent or not positive), among objectives
  whose path cost is at most ``DETOUR`` times the cost of ``baseline-v2``'s choice; ties go to the lower cost, then
  the lower hex. Paths come from ``baseline-v2``'s own router and candidate builder;
* with no such objective the move is withheld and the unit waits for this step (it is reconsidered next step).

Every replaced move passes the project gate (``decision.gate``) together with the step's other actions; a replaced
move the gate rejects reverts to ``baseline-v2``'s original. Nothing else changes: shots, occupations, air units and
units ``baseline-v2`` leaves idle are untouched, and no prediction of the engine's movement timing is attempted.
Stateless: no memory.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..boundary import Observation, Stage
from ..decision import gate
from ..decision.candidates import move_candidates
from ..decision.context import build_context
from ..decision.policy import Decision
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int

CANDIDATE_ID = "t9-capacity-allocation-v1"
MOVE = 1
GROUND = (1, 2)
CAPACITY = 4
DETOUR = 2.0


def destination(action: Mapping[str, Any]) -> Optional[int]:
    path = action.get("move_path")
    if isinstance(path, (list, tuple)) and path and is_int(path[-1]):
        return path[-1]
    return None


class AllocationAddon(Addon):
    name = "t9"

    def apply(self, observation: Observation, seat: int, faction: int, base: Decision,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        actions = tuple(base.actions)
        if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
            return AddonResult(actions)
        context = build_context(observation, seat, faction)
        router = self.baseline.router
        if router is None:
            return AddonResult(actions, skipped=(("no movement-cost data", 1),))
        router.targets = frozenset(city.coord for city in context.objectives)  # as baseline-v2 sets it
        cities = {city.coord: city for city in (observation.cities() or ())}
        unheld = {city.coord: city for city in context.objectives}
        kinds = {unit.obj_id: unit.fields.get("type") for unit in observation.operators() if unit.color == faction}
        commitments: collections.Counter = collections.Counter()
        for unit in observation.operators():
            if unit.color != faction or unit.fields.get("type") not in GROUND:
                continue
            path = unit.move_path or ()
            end = path[-1] if path else unit.cur_hex
            if end in cities:
                commitments[end] += 1
        final: List[Optional[Mapping[str, Any]]] = []
        planned: List[Tuple[int, Mapping[str, Any], Mapping[str, Any]]] = []  # index, original, replacement
        changes: List[Dict[str, Any]] = []
        skipped: collections.Counter = collections.Counter()
        for action in actions:
            if action.get("type") != MOVE or kinds.get(action.get("obj_id")) not in GROUND:
                final.append(action)
                continue
            dest = destination(action)
            if dest is None:
                final.append(action)
                skipped["move without a readable destination"] += 1
                continue
            if commitments[dest] < CAPACITY:
                commitments[dest] += 1
                final.append(action)
                skipped["kept: destination under capacity"] += 1
                continue
            unit = context.unit(action["obj_id"])
            candidates, reason = move_candidates(unit, context, router) if unit is not None else ([], "not a unit")
            costs = {dict(c.detail)["destination"]: dict(c.detail)["cost"] for c in candidates}
            base_cost = costs.get(dest)
            options = []
            for candidate in candidates:
                detail = dict(candidate.detail)
                coord, cost = detail["destination"], detail["cost"]
                if coord == dest or coord not in unheld or commitments[coord] >= CAPACITY:
                    continue
                if base_cost is None or cost > DETOUR * base_cost:
                    continue
                value = unheld[coord].value
                weight = value if is_int(value) and value > 0 else 1
                options.append(((cost / weight, cost, coord), candidate, coord, cost))
            if not options:
                final.append(None)
                commitments_at = commitments[dest]
                changes.append({"kind": "withhold", "obj_id": action["obj_id"], "destination": dest,
                                "commitments": commitments_at, "reason": reason or "no objective under capacity"})
                continue
            _, chosen, coord, cost = min(options, key=lambda option: option[0])
            replacement = chosen.action(seat)
            commitments[coord] += 1
            planned.append((len(final), action, replacement))
            final.append(replacement)
            changes.append({"kind": "replace", "obj_id": action["obj_id"], "from": dest, "to": coord,
                            "from_cost": base_cost, "to_cost": cost, "commitments_at_from": commitments[dest]})
        proposals = [a for a in final if a is not None]
        result = gate.check(proposals, context, router)
        rejected = {r.obj_id for r in result.rejected}
        for index, original, replacement in planned:
            if replacement["obj_id"] in rejected:
                final[index] = original
                changes.append({"kind": "revert", "obj_id": original["obj_id"],
                                "reason": next(r.reason for r in result.rejected if r.obj_id == original["obj_id"])})
        emitted = tuple(a for a in final if a is not None)
        return AddonResult(emitted, tuple(changes), tuple(sorted(skipped.items())))


class AllocationPolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = AllocationAddon


class AllocationAgent(AddonAgent):
    policy_class = AllocationPolicy
