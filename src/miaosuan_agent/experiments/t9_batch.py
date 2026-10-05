"""OFFLINE-ONLY design candidate ``t9-batch-capacity-v3``: allocate each objective's four places by feasible arrival.

Sprint 11 design study (``docs/SPRINT11_BATCH_ALLOCATOR.md``). Not in any run card, never packaged, never played: it
exists so that the design can be replayed on frozen captures. A later engine use needs its own approval and card.

``baseline-v2`` decides first, unchanged (:mod:`.exploratory_addon`). T9-v1 and T9-v2 admitted ground moves to an
objective in ``baseline-v2``'s emission order until four commitments were counted, and counted every unit whose path
ended there, including units that could not reach it before the game ended. This add-on instead, for one decision:

* incumbents of an objective are the own ground units standing on it with no move path (always counted) and the
  units whose move path ends on it (movers). No policy action can change a mover's path (``valid_actions`` never
  lists a move for a unit with a path; Sprint 11 audit), so movers are never re-ranked or displaced. A mover is
  counted unless its remaining free-flow time, excluding the hex it is entering, already reaches the end of the game:
  free-flow time is a lower bound on arrival (Sprint 3 hex-time fact; Sprint 11 audit), so such a mover cannot stand
  on the objective before the game ends and holds no place;
* claimants are the own ground units for which ``baseline-v2`` emits a move to an objective in this decision. All
  claimants of one objective are ranked together by free-flow time along ``baseline-v2``'s own path (sum of
  ``720 / basic_speed * cost`` per hex, rounded per hex), then route cost, path length and unit id; emission order is
  never used. A claimant that cannot arrive before the game ends is never selected;
* the objective's free places are ``CAPACITY`` minus the counted incumbents; the best-ranked selectable claimants
  take them and keep ``baseline-v2``'s move unchanged;
* every other claimant keeps its objective and route: it is staged on the farthest hex of ``baseline-v2``'s path that
  is not an objective and holds fewer than ``STAGE_CAP`` own ground units (standing there or with a path ending there,
  this decision's staged moves included), processed in rank order; with no such hex it is withheld this decision.
  ``STAGE_CAP`` is one below the stacking limit, so a staging hex never closes a corridor to passing units.
  ``baseline-v2`` reconsiders staged and withheld units at its next decision, from their new position.

Staged moves pass the project gate together with the step's other actions; a rejected staged move is withheld. Shots,
occupations, air units, units ``baseline-v2`` leaves idle and every other action are unchanged and keep their order.
Fail closed: if the allocation cannot be computed, every ground move to an objective is withheld for this decision
(never emitted unchecked) and the error is recorded. Inputs are the seat's own observation and the setup cost data.
Stateless: no memory.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from ..decision import gate
from ..decision.context import build_context
from ..decision.routing import Router, move_mode
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int, is_number

CANDIDATE_ID = "t9-batch-capacity-v3"
MOVE = 1
GROUND = (1, 2)
CAPACITY = 4
STAGE_CAP = CAPACITY - 1
SECONDS_PER_HEX_AT_1KMH = 720.0


def hex_time(basic_speed: Any, cost: Any) -> Optional[int]:
    """Steps to enter one hex, ``720 / basic_speed * cost`` rounded (the Sprint 3 relation); ``None`` if unreadable.

    The same formula as ``evaluation.ps1_model.hex_time``; repeated so that the candidate's source set holds no
    analysis module.
    """
    if not (is_number(basic_speed) and is_number(cost) and basic_speed > 0 and cost > 0):
        return None
    return int(SECONDS_PER_HEX_AT_1KMH / basic_speed * cost + 0.5)


def path_times(router: Router, unit_type: Any, move_state: Any, basic_speed: Any, start: Any,
               path: Sequence[Any]) -> Tuple[Optional[List[int]], Optional[float]]:
    """Per-hex free-flow times and the route cost of ``path`` from ``start``; ``(None, None)`` if any part is
    unreadable (unknown mode, speed or edge)."""
    mode = move_mode(unit_type, move_state) if is_int(unit_type) else None
    if mode is None or not is_int(start) or not path:
        return None, None
    times, cost, previous = [], 0.0, start
    for hex_ in path:
        edges = router.costs.neighbours(mode, previous)
        if not is_int(hex_) or hex_ not in edges:
            return None, None
        step = hex_time(basic_speed, edges[hex_])
        if step is None:
            return None, None
        times.append(step)
        cost += edges[hex_]
        previous = hex_
    return times, cost


@dataclass(frozen=True)
class Claimant:
    obj_id: int
    objective: int
    path: Tuple[int, ...]
    free_flow: Optional[int]
    cost: Optional[float]
    feasible: bool
    index: int  # position in baseline-v2's emission order (recorded, never used for ranking)
    status: str = "no place under capacity"  # why the claimant is not selected if it is not


def free_flow_key(claimant: Claimant) -> Tuple[Any, ...]:
    """The selected rank: selectable first, then free-flow time, route cost, path length, unit id."""
    unrated = claimant.free_flow is None
    return (not claimant.feasible, unrated, claimant.free_flow or 0, claimant.cost or 0.0, len(claimant.path),
            claimant.obj_id)


@dataclass
class Allocation:
    """Everything one decision's allocation computed (the add-on emits ``actions``; analyses read the rest)."""

    actions: Tuple[Mapping[str, Any], ...]
    changes: List[Dict[str, Any]] = field(default_factory=list)
    skipped: collections.Counter = field(default_factory=collections.Counter)
    objectives: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    claimants: Dict[int, Claimant] = field(default_factory=dict)
    selected: Dict[int, int] = field(default_factory=dict)        # obj_id -> objective
    staged: Dict[int, Tuple[int, ...]] = field(default_factory=dict)  # obj_id -> staged path
    withheld: Dict[int, str] = field(default_factory=dict)         # obj_id -> reason
    error: Optional[str] = None


def destination(action: Mapping[str, Any]) -> Optional[int]:
    path = action.get("move_path")
    if isinstance(path, (list, tuple)) and path and is_int(path[-1]):
        return path[-1]
    return None


def allocate(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
             router: Optional[Router], key: Callable[[Claimant], Any] = free_flow_key,
             capacity: int = CAPACITY, stage_cap: int = STAGE_CAP, horizon: Optional[int] = None,
             stage: bool = True) -> Allocation:
    """One decision's batch allocation. Keyword arguments other than the defaults exist only for offline analysis
    (rank and disposition variants); the candidate always uses the defaults."""
    actions = tuple(actions)
    if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
        return Allocation(actions)
    try:
        return _allocate(observation, seat, faction, actions, router, key, capacity, stage_cap, horizon, stage)
    except ContractError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed: no ground move to an objective leaves unchecked
        cities = set()
        try:
            cities = {city.coord for city in (observation.cities() or ())}
        except Exception:  # noqa: BLE001
            pass
        ground = set()
        for unit in observation.operators():
            try:
                if unit.color == faction and unit.unit_type in GROUND:
                    ground.add(unit.obj_id)
            except ContractError:
                continue
        kept, changes = [], []
        for action in actions:
            if action.get("type") == MOVE and action.get("obj_id") in ground and (
                    not cities or destination(action) in cities or destination(action) is None):
                changes.append({"kind": "fail-closed", "obj_id": action.get("obj_id")})
                continue
            kept.append(action)
        return Allocation(tuple(kept), changes, error=f"{type(exc).__name__}: {exc}"[:300])


def _allocate(observation: Observation, seat: int, faction: int, actions: Tuple[Mapping[str, Any], ...],
              router: Optional[Router], key: Callable[[Claimant], Any], capacity: int, stage_cap: int,
              horizon: Optional[int], stage: bool) -> Allocation:
    if router is None:
        raise ValueError("no movement-cost data")
    context = build_context(observation, seat, faction)
    time_info = observation.time()
    end = time_info.max_step if is_int(time_info.max_step) else None
    now = time_info.cur_step
    cities = {city.coord for city in (observation.cities() or ())}
    if not cities:
        raise ValueError("no objectives in the observation")

    own: Dict[int, Any] = {}
    for unit in observation.operators():
        if unit.color == faction and unit.unit_type in GROUND:
            own[unit.obj_id] = unit
    out = Allocation(actions)
    endpoints: collections.Counter = collections.Counter()
    incumbents = {coord: {"physical": 0, "movers": 0, "phantom": 0, "mover_bounds": {}} for coord in cities}
    for unit in own.values():
        path = tuple(unit.move_path or ())
        stop = path[-1] if path else unit.cur_hex
        endpoints[stop] += 1
        if stop not in cities:
            continue
        row = incumbents[stop]
        if not path:
            row["physical"] += 1
            continue
        times, _ = path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"),
                              unit.cur_hex, path)
        bound = None if times is None else sum(times[1:])  # the hex being entered may be partly done
        if bound is not None and end is not None and now + bound >= end:
            row["phantom"] += 1
            out.skipped["mover cannot arrive before the end: no place held"] += 1
        else:
            row["movers"] += 1
            row["mover_bounds"][unit.obj_id] = bound

    claimants: Dict[int, Claimant] = {}
    for index, action in enumerate(actions):
        obj_id = action.get("obj_id")
        if action.get("type") != MOVE or obj_id not in own:
            continue
        dest = destination(action)
        if dest is None:
            out.skipped["move without a readable destination: kept"] += 1
            continue
        if dest not in cities:
            out.skipped["move to a non-objective hex: kept"] += 1
            continue
        unit = own[obj_id]
        path = tuple(action["move_path"])
        times, cost = path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"),
                                 unit.cur_hex, path)
        free_flow = None if times is None else sum(times)
        if free_flow is None:
            status = "free-flow time unreadable"
        elif end is not None and now + free_flow >= end:
            status = "cannot arrive before the end"
        elif horizon is not None and free_flow > horizon:
            status = "beyond the commitment horizon"
        else:
            status = "no place under capacity"
        claimants[obj_id] = Claimant(obj_id, dest, path, free_flow, cost, status == "no place under capacity", index,
                                     status)
    out.claimants = claimants

    by_objective: Dict[int, List[Claimant]] = collections.defaultdict(list)
    for claimant in claimants.values():
        by_objective[claimant.objective].append(claimant)
    for coord, group in sorted(by_objective.items()):
        row = incumbents[coord]
        free = capacity - row["physical"] - row["movers"]
        ranked = sorted(group, key=key)
        chosen = [c for c in ranked if c.feasible][:max(free, 0)]
        for claimant in chosen:
            out.selected[claimant.obj_id] = coord
        out.objectives[coord] = {"physical": row["physical"], "movers": row["movers"], "phantom": row["phantom"],
                                 "mover_bounds": dict(row["mover_bounds"]),
                                 "free": free, "claimants": len(group),
                                 "ranked": [c.obj_id for c in ranked], "selected": [c.obj_id for c in chosen]}

    rest = sorted((c for c in claimants.values() if c.obj_id not in out.selected), key=key)
    replacements: Dict[int, Dict[str, Any]] = {}
    for claimant in rest:
        reason = claimant.status
        target = None
        if stage:
            for position in range(len(claimant.path) - 2, -1, -1):
                hex_ = claimant.path[position]
                if hex_ not in cities and endpoints[hex_] < stage_cap:
                    target = position
                    break
        if target is None:
            out.withheld[claimant.obj_id] = reason
            out.changes.append({"kind": "withhold", "obj_id": claimant.obj_id, "destination": claimant.objective,
                                "free_flow": claimant.free_flow, "reason": reason})
            continue
        staged_path = claimant.path[:target + 1]
        endpoints[staged_path[-1]] += 1
        out.staged[claimant.obj_id] = staged_path
        original = actions[claimant.index]
        replacement = dict(original)
        replacement["move_path"] = list(staged_path)
        replacements[claimant.obj_id] = replacement
        out.changes.append({"kind": "stage", "obj_id": claimant.obj_id, "destination": claimant.objective,
                            "staging": staged_path[-1], "free_flow": claimant.free_flow, "reason": reason,
                            "path_length": len(claimant.path), "staged_path_length": len(staged_path)})

    for coord in sorted(out.objectives):
        info = out.objectives[coord]
        out.skipped["kept: selected"] += len(info["selected"])
        out.skipped["incumbent movers retained (cannot be re-ordered)"] += info["movers"]

    final: List[Optional[Mapping[str, Any]]] = []
    for action in actions:
        obj_id = action.get("obj_id")
        if action.get("type") == MOVE and obj_id in claimants and obj_id not in out.selected:
            final.append(replacements.get(obj_id))
        else:
            final.append(action)
    checked = gate.check([a for a in final if a is not None], context, router)
    rejected = {rejection.obj_id: rejection.reason for rejection in checked.rejected}
    for position, action in enumerate(final):
        if action is None:
            continue
        obj_id = action.get("obj_id")
        if obj_id in replacements and obj_id in rejected:
            final[position] = None
            out.staged.pop(obj_id, None)
            out.withheld[obj_id] = "staged move rejected by the gate"
            out.changes.append({"kind": "stage-rejected", "obj_id": obj_id, "reason": rejected[obj_id]})
    out.actions = tuple(a for a in final if a is not None)
    return out


class BatchAddon(Addon):
    name = "t9_batch"

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        result = allocate(observation, seat, faction, tuple(base.actions), self.baseline.router)
        changes = list(result.changes)
        if result.error is not None:
            changes.append({"kind": "error", "reason": result.error})
        return AddonResult(result.actions, tuple(changes), tuple(sorted(result.skipped.items())))


class BatchPolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = BatchAddon


class BatchAgent(AddonAgent):
    policy_class = BatchPolicy
