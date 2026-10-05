"""Sprint 11 one-step action replay of the offline candidate ``t9-batch-capacity-v3`` and its design variants.

Pure functions over one captured seat decision: the seat's raw observation, ``baseline-v2``'s actions for it, and
the frozen T9-v1 actions for it. Each variant of the batch allocator, and frozen T9-v2, is applied to that one
decision; nothing is simulated beyond it, so every figure is an action-level difference on a recorded state, never an
outcome. Results carry unit ids only inside the per-decision rows that the private driver keeps under ``local/``;
:func:`public` strips them.
"""

from __future__ import annotations

import collections
import math
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import Observation, Stage
from ..decision.routing import Router
from ..experiments import t9_batch as tb
from ..experiments.t9_staging import StagingAddon

GROUND = tb.GROUND
MOVE = tb.MOVE


def emission_key(claimant: tb.Claimant) -> Tuple[Any, ...]:
    """The rule T9-v1 and T9-v2 used: baseline-v2's emission order (feasibility kept, so only the order differs)."""
    return (not claimant.feasible, claimant.index)


def cost_key(claimant: tb.Claimant) -> Tuple[Any, ...]:
    """Rank candidate R1: route cost in the unit's own movement mode, ignoring speed."""
    return (not claimant.feasible, math.inf if claimant.cost is None else claimant.cost, len(claimant.path),
            claimant.obj_id)


#: Design variants replayed beside the candidate. Each differs from it in exactly one respect.
VARIANTS: Dict[str, Dict[str, Any]] = {
    "candidate": {},
    "emission-order": {"key": emission_key},
    "route-cost": {"key": cost_key},
    "no-end-of-game-test": {"use_end": False},
    "withhold-only": {"stage": False},
    "stage-cap-4": {"stage_cap": 4},
    "horizon-1440": {"horizon": 1440},
    "horizon-720": {"horizon": 720},
    "horizon-360": {"horizon": 360},
}


def run_variant(observation: Observation, seat: int, faction: int, baseline: Sequence[Mapping[str, Any]],
                router: Router, options: Mapping[str, Any]) -> tb.Allocation:
    options = dict(options)
    if not options.pop("use_end", True):
        observation = _without_end(observation)
    return tb.allocate(observation, seat, faction, baseline, router, **options)


def _without_end(observation: Observation) -> Observation:
    raw = dict(observation.fields)
    time_info = dict(raw.get("time") or {})
    time_info.pop("max_step", None)
    raw["time"] = time_info
    return Observation.from_raw(raw, observation.origin, observation.path)


def own_ground(observation: Observation, faction: int) -> Dict[int, Any]:
    return {u.obj_id: u for u in observation.operators() if u.color == faction and u.unit_type in GROUND}


def ground_moves(actions: Iterable[Mapping[str, Any]], ground: Mapping[int, Any]) -> Dict[int, Mapping[str, Any]]:
    return {a["obj_id"]: a for a in actions if a.get("type") == MOVE and a.get("obj_id") in ground}


def free_flow(router: Router, unit: Any, path: Sequence[int], skip_first: bool = False) -> Optional[int]:
    times, _ = tb.path_times(router, unit.unit_type, unit.move_state, unit.fields.get("basic_speed"), unit.cur_hex,
                             path)
    if times is None:
        return None
    return sum(times[1:] if skip_first else times)


def structural(observation: Observation, faction: int, baseline: Sequence[Mapping[str, Any]],
               emitted: Sequence[Mapping[str, Any]], router: Router) -> Dict[str, Any]:
    """Policy-independent checks of one emitted action list against baseline-v2's (every variant and T9-v1/v2).

    * ``unrelated_changed``: the actions other than own ground moves, in order, differ from baseline-v2's;
    * ``invented``: a ground move for a unit that baseline-v2 did not move;
    * ``cross_objective``: an emitted ground move whose endpoint is neither baseline-v2's destination nor a hex of
      baseline-v2's path for that unit (T9-v1's replacements are the only expected source);
    * ``prefix_failures``: a shortened move that is not a strict prefix of baseline-v2's path, or ends on an
      objective other than baseline-v2's destination;
    * per kept / staged / withheld counts, hexes removed by each shortened move, and the places granted to moves that
      cannot arrive before the game ends (``late_owners``: an emitted move to an objective whose free-flow time
      reaches the end).
    """
    ground = own_ground(observation, faction)
    cities = {c.coord for c in (observation.cities() or ())}
    time_info = observation.time()
    end = time_info.max_step
    base_moves, out_moves = ground_moves(baseline, ground), ground_moves(emitted, ground)
    rest_base = [a for a in baseline if not (a.get("type") == MOVE and a.get("obj_id") in ground)]
    rest_out = [a for a in emitted if not (a.get("type") == MOVE and a.get("obj_id") in ground)]
    row: Dict[str, Any] = collections.Counter()
    row["unrelated_changed"] = int([dict(a) for a in rest_base] != [dict(a) for a in rest_out])
    removed: List[int] = []
    owners: Dict[int, List[int]] = collections.defaultdict(list)
    for obj_id, action in out_moves.items():
        if obj_id not in base_moves:
            row["invented"] += 1
            continue
        before, after = list(base_moves[obj_id]["move_path"]), list(action["move_path"])
        if after == before:
            row["kept"] += 1
        elif after and after[-1] in cities and after[-1] != before[-1]:
            row["cross_objective"] += 1
        elif after[-1] not in before:
            row["cross_objective"] += 1
        else:
            row["shortened"] += 1
            removed.append(len(before) - len(after))
            if not (1 <= len(after) < len(before) and after == before[:len(after)]) or after[-1] in cities:
                row["prefix_failures"] += 1
        if after and after[-1] in cities:
            owners[after[-1]].append(obj_id)
            ff = free_flow(router, ground[obj_id], after)
            if ff is not None and end is not None and time_info.cur_step + ff >= end:
                row["late_owners"] += 1
    row["withheld"] = sum(1 for obj_id in base_moves if obj_id not in out_moves)
    row["baseline_ground_moves"] = len(base_moves)
    row["baseline_objective_moves"] = sum(1 for a in base_moves.values() if a["move_path"][-1] in cities)
    result = dict(row)
    result["removed"] = removed
    result["owners"] = {coord: sorted(ids) for coord, ids in owners.items()}
    return result


def commitments(observation: Observation, faction: int, router: Router) -> Dict[int, Dict[str, int]]:
    """Incumbents per objective before the decision: physical, movers that can arrive, movers that cannot."""
    cities = {c.coord for c in (observation.cities() or ())}
    time_info = observation.time()
    out = {coord: {"physical": 0, "movers": 0, "phantom": 0} for coord in cities}
    for unit in own_ground(observation, faction).values():
        path = tuple(unit.move_path or ())
        stop = path[-1] if path else unit.cur_hex
        if stop not in cities:
            continue
        if not path:
            out[stop]["physical"] += 1
            continue
        bound = free_flow(router, unit, path, skip_first=True)
        late = bound is not None and time_info.max_step is not None and time_info.cur_step + bound >= time_info.max_step
        out[stop]["phantom" if late else "movers"] += 1
    return out


def capacity_check(before: Mapping[int, Mapping[str, int]], owners: Mapping[int, Sequence[int]],
                   capacity: int = tb.CAPACITY) -> Dict[str, int]:
    """Commitments after the decision. ``caused`` counts objectives the decision itself pushed above ``capacity``
    (counted incumbents plus newly granted places); ``inherited`` objectives were above it before the decision
    (possible only on another policy's recorded state); ``phantom_inclusive`` also counts movers that cannot arrive."""
    out = collections.Counter()
    for coord, info in before.items():
        granted = len(owners.get(coord, ()))
        counted = info["physical"] + info["movers"]
        if counted > capacity:
            out["inherited"] += 1
        if granted and counted + granted > capacity:
            out["caused"] += 1
        if granted and counted + info["phantom"] + granted > capacity:
            out["phantom_inclusive"] += 1
    return dict(out)


def decision(observation: Observation, seat: int, faction: int, baseline: Sequence[Mapping[str, Any]],
             t9v1: Sequence[Mapping[str, Any]], router: Router, staging: StagingAddon,
             variants: Mapping[str, Mapping[str, Any]] = VARIANTS) -> Optional[Dict[str, Any]]:
    """Every policy's actions and checks for one captured decision, or ``None`` outside the play stage or when
    baseline-v2 moves no own ground unit to an objective."""
    if observation.time().stage != Stage.PLAY:
        return None
    ground = own_ground(observation, faction)
    cities = {c.coord for c in (observation.cities() or ())}
    if not any(a["move_path"][-1] in cities for a in ground_moves(baseline, ground).values()):
        return None
    before = commitments(observation, faction, router)
    row: Dict[str, Any] = {"before": before, "policies": {}, "allocations": {}}
    v2 = staging.apply(observation, seat, faction, SimpleNamespace(actions=tuple(baseline)), ())
    emitted = {"t9-v1": tuple(t9v1), "t9-v2": tuple(v2.actions)}
    for name, options in variants.items():
        allocation = run_variant(observation, seat, faction, baseline, router, options)
        emitted[name] = allocation.actions
        row["allocations"][name] = allocation
    for name, actions in emitted.items():
        checks = structural(observation, faction, baseline, actions, router)
        checks["capacity"] = capacity_check(before, checks["owners"])
        row["policies"][name] = checks
    row["emitted"] = emitted
    return row


def dominated_movers(allocation: tb.Allocation) -> List[int]:
    """Counted incumbent movers that a non-selected selectable claimant of the same objective would outrank if
    movers could be re-ordered (remaining lower bound above that claimant's free-flow time): these are retained only
    because no action can change them. Movers with an unreadable bound are not judged."""
    out = []
    for coord, info in allocation.objectives.items():
        waiting = [c.free_flow for c in allocation.claimants.values()
                   if c.objective == coord and c.feasible and c.obj_id not in allocation.selected]
        if not waiting:
            continue
        best = min(waiting)
        out.extend(obj_id for obj_id, bound in sorted(info["mover_bounds"].items())
                   if bound is not None and bound > best)
    return out


#: Policies whose rule counts every mover, including those that cannot arrive before the end.
COUNTS_EVERY_MOVER = frozenset({"t9-v1", "t9-v2", "no-end-of-game-test"})


def hold_back_causes(name: str, observation: Observation, faction: int, baseline: Sequence[Mapping[str, Any]],
                     emitted: Sequence[Mapping[str, Any]], before: Mapping[int, Mapping[str, int]],
                     router: Router) -> Dict[str, int]:
    """Why each baseline-v2 objective move that ``name`` did not keep was held back:

    * ``claimant cannot arrive before the end``: the held unit's own free-flow time reaches the end of the game;
    * ``a place is held by a unit that cannot arrive``: the policy counted, or granted in this decision, a place to a
      unit whose (lower-bound) arrival reaches the end of the game;
    * ``places held by units that can arrive``: every place of the objective is held by a unit that can arrive.
    """
    ground = own_ground(observation, faction)
    cities = {c.coord for c in (observation.cities() or ())}
    time_info = observation.time()
    end, now = time_info.max_step, time_info.cur_step
    base_moves, out_moves = ground_moves(baseline, ground), ground_moves(emitted, ground)
    late_granted: collections.Counter = collections.Counter()
    for obj_id, action in out_moves.items():
        path = list(action["move_path"])
        if path and path[-1] in cities:
            ff = free_flow(router, ground[obj_id], path)
            if ff is not None and end is not None and now + ff >= end:
                late_granted[path[-1]] += 1
    out: collections.Counter = collections.Counter()
    for obj_id, action in base_moves.items():
        dest = action["move_path"][-1]
        if dest not in cities or dict(out_moves.get(obj_id) or {}) == dict(action):
            continue
        ff = free_flow(router, ground[obj_id], action["move_path"])
        if ff is not None and end is not None and now + ff >= end:
            out["claimant cannot arrive before the end"] += 1
        elif late_granted[dest] or (name in COUNTS_EVERY_MOVER and before.get(dest, {}).get("phantom", 0)):
            out["a place is held by a unit that cannot arrive"] += 1
        else:
            out["places held by units that can arrive"] += 1
    return dict(out)


def permutation_invariant(observation: Observation, seat: int, faction: int, baseline: Sequence[Mapping[str, Any]],
                          router: Router, orders: Sequence[Sequence[int]],
                          allocate: Callable[..., tb.Allocation] = tb.allocate) -> bool:
    """The candidate's per-unit outcome (kept, staged path, withheld) is identical under every given reordering
    of baseline-v2's actions."""
    def outcome(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, Any]:
        result = allocate(observation, seat, faction, actions, router)
        return {a.get("obj_id", ("seat", i)): tuple(sorted((k, repr(v)) for k, v in dict(a).items()))
                for i, a in enumerate(result.actions)}

    reference = outcome(baseline)
    return all(outcome([baseline[i] for i in order]) == reference for order in orders)


#: The unit fields the timing checks read (kept per decision instead of whole records).
TIMING_FIELDS = ("cur_hex", "move_path", "type", "move_state", "basic_speed", "move_to_stop_remain_time", "speed")


def timing_units(raw: Mapping[str, Any], faction: int) -> Dict[int, Dict[str, Any]]:
    return {u["obj_id"]: {f: u.get(f) for f in TIMING_FIELDS} for u in raw.get("operators") or ()
            if u.get("color") == faction and u.get("type") in GROUND}


def control_counts(raw: Mapping[str, Any], faction: int, actions: Sequence[Mapping[str, Any]],
                   baseline: Sequence[Mapping[str, Any]]) -> collections.Counter:
    """What the seat can order its own ground units, from one raw seat observation: per movement state (no path,
    path and ``speed`` above 0, path and ``speed`` 0), whether move (1) and stop (10) are listed; and how many of the
    seat's emitted actions and of baseline-v2's actions are moves for a unit with an active path, or stops."""
    out: collections.Counter = collections.Counter()
    listed = raw.get("valid_actions") or {}
    units = {u["obj_id"]: u for u in raw.get("operators") or ()
             if u.get("color") == faction and u.get("type") in GROUND}
    for obj_id, u in units.items():
        path = u.get("move_path") or []
        state = "no path" if not path else ("path, speed above 0" if (u.get("speed") or 0) > 0 else "path, speed 0")
        keys = {int(k) for k in (listed.get(obj_id) or {})}
        out[f"{state}: unit-decisions"] += 1
        out[f"{state}: move listed"] += MOVE in keys
        out[f"{state}: stop listed"] += 10 in keys
    for source, rows in (("emitted", actions), ("baseline-v2", baseline)):
        for a in rows:
            u = units.get(a.get("obj_id"))
            if u is None:
                continue
            if a.get("type") == MOVE and u.get("move_path"):
                out[f"{source}: move for a unit with an active path"] += 1
            if a.get("type") == 10:
                out[f"{source}: stop"] += 1
    return out


def move_timing(series: Sequence[Mapping[int, Mapping[str, Any]]], orders: Sequence[Tuple[int, Mapping[str, Any]]],
                router: Router) -> collections.Counter:
    """For every emitted ground move ``(k, action)`` with ``series[k]`` the seat's own ground units at decision ``k``:

    * first-hex delay minus the hex time of the first hex (``delay-tau: d``), split by whether the unit was still in
      its move-to-stop transition (``move_to_stop_remain_time`` above 0) at the order;
    * arrival at the path's end against the free-flow time: exact, late, early (would refute the lower bound) or never.
    """
    out: collections.Counter = collections.Counter()
    for k, action in orders:
        unit = series[k].get(action["obj_id"])
        if unit is None:
            continue
        path = list(action["move_path"])
        state = "transition" if (unit.get("move_to_stop_remain_time") or 0) > 0 else "settled"
        times, _ = tb.path_times(router, unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                                 unit.get("cur_hex"), path)
        if times is None:
            out["unreadable"] += 1
            continue
        entered = next((j for j in range(k + 1, len(series))
                        if (series[j].get(action["obj_id"]) or {}).get("cur_hex") == path[0]), None)
        out[f"{state}: delay-tau: {'never' if entered is None else entered - k - times[0]}"] += 1
        arrived = next((j for j in range(k + 1, len(series))
                        if (series[j].get(action["obj_id"]) or {}).get("cur_hex") == path[-1]
                        and not (series[j][action["obj_id"]].get("move_path"))), None)
        predicted = k + sum(times)
        out["arrival: " + ("never" if arrived is None else "early" if arrived < predicted else
                           "exact" if arrived == predicted else "late")] += 1
    return out


def remaining_bound_check(series: Sequence[Mapping[int, Mapping[str, Any]]], router: Router,
                          every: int = 20) -> collections.Counter:
    """At every ``every``-th decision, each own ground unit with an active path: does it reach the path's end no sooner
    than the conservative remaining bound (free-flow time excluding the hex being entered)?"""
    out: collections.Counter = collections.Counter()
    for k in range(0, len(series), every):
        for obj_id, unit in series[k].items():
            path = list(unit.get("move_path") or [])
            if not path:
                continue
            times, _ = tb.path_times(router, unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                                     unit.get("cur_hex"), path)
            if times is None:
                out["unreadable"] += 1
                continue
            arrived = next((j for j in range(k, len(series)) if obj_id in series[j]
                            and series[j][obj_id].get("cur_hex") == path[-1]
                            and not series[j][obj_id].get("move_path")), None)
            if arrived is None:
                out["not observed to arrive"] += 1
                continue
            out["checked"] += 1
            out["arrived sooner than the bound"] += int(arrived - k < sum(times[1:]))
    return out


class Episodes:
    """Continuous hypothetical hold-back episodes (staged or withheld in consecutive replayed decisions) per unit."""

    def __init__(self) -> None:
        self.open: Dict[int, int] = {}
        self.lengths: List[int] = []

    def update(self, k: int, held: Iterable[int]) -> None:
        held = set(held)
        for unit in list(self.open):
            if unit not in held:
                self.lengths.append(k - self.open.pop(unit))
        for unit in held:
            self.open.setdefault(unit, k)

    def finish(self, k: int) -> List[int]:
        for unit in list(self.open):
            self.lengths.append(k + 1 - self.open.pop(unit))
        return sorted(self.lengths)


def distribution(values: Sequence[int]) -> Dict[str, Any]:
    values = sorted(values)
    if not values:
        return {"n": 0}
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {"n": len(values), "max": values[-1], "median": median, "sum": sum(values),
            "counts": {str(v): c for v, c in sorted(collections.Counter(values).items())}}
