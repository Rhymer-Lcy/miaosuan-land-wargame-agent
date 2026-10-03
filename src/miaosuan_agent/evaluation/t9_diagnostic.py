"""Sprint 10 full-step diagnosis of frozen ``t9-capacity-allocation-v1``.

The observer is deliberately outside the policy source set.  It records both seat observations and the
all-seeing state for analysis, but reconstructs the baseline and T9 decision using only the diagnosed seat's
observation, setup movement costs and policy memory.  Nothing produced here reaches a policy or the engine.
"""

from __future__ import annotations

import hashlib
import pickle
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import Memory, digest, gate
from ..decision.candidates import move_candidates
from ..decision.context import build_context
from ..experiments.exploratory_addon import AddonMemory, canonical_json
from ..experiments.shoot_reservation import ShootReservationPolicy
from ..experiments.t9_allocation import CAPACITY, DETOUR, GROUND, MOVE, destination
from . import residual516 as rd

CAPTURE_SCHEMA = "miaosuan-t9-diagnostic-capture/1"
SAMPLE_EVERY = 1


@dataclass(frozen=True)
class AllocationAudit:
    """Seat-local reconstruction of one frozen T9-v1 add-on decision."""

    actions: Tuple[Mapping[str, Any], ...]
    changes: Tuple[Mapping[str, Any], ...]
    moves: Tuple[Mapping[str, Any], ...]
    initial_commitments: Mapping[int, int]
    final_commitments: Mapping[int, int]


def _plain_counter(values: Mapping[int, int]) -> Dict[str, int]:
    return {str(k): int(v) for k, v in sorted(values.items()) if v}


def audit_allocation(observation: Observation, seat: int, faction: int, base_actions: Sequence[Mapping[str, Any]],
                     baseline: ShootReservationPolicy) -> AllocationAudit:
    """Reproduce T9-v1 and retain every capacity and alternative test it performs.

    This mirrors :mod:`experiments.t9_allocation` without importing or changing its policy class.  Synthetic tests
    require the reconstructed actions and changes to equal the frozen implementation byte for byte.
    """
    actions = tuple(base_actions)
    if observation.time().stage != Stage.PLAY or not any(a.get("type") == MOVE for a in actions):
        return AllocationAudit(actions, (), (), {}, {})
    context = build_context(observation, seat, faction)
    router = baseline.router
    if router is None:
        return AllocationAudit(actions, (), (), {}, {})
    router.targets = frozenset(city.coord for city in context.objectives)
    cities = {city.coord: city for city in (observation.cities() or ())}
    unheld = {city.coord: city for city in context.objectives}
    kinds = {unit.obj_id: unit.fields.get("type") for unit in observation.operators() if unit.color == faction}
    commitments: Counter = Counter()
    for unit in observation.operators():
        if unit.color != faction or unit.fields.get("type") not in GROUND:
            continue
        path = unit.move_path or ()
        end = path[-1] if path else unit.cur_hex
        if end in cities:
            commitments[end] += 1
    initial = Counter(commitments)
    final: List[Optional[Mapping[str, Any]]] = []
    planned: List[Tuple[int, Mapping[str, Any], Mapping[str, Any], int]] = []
    changes: List[Dict[str, Any]] = []
    moves: List[Dict[str, Any]] = []
    for action in actions:
        if action.get("type") != MOVE or kinds.get(action.get("obj_id")) not in GROUND:
            final.append(action)
            continue
        dest = destination(action)
        row: Dict[str, Any] = {"obj_id": action.get("obj_id"), "baseline_destination": dest,
                               "commitments_before": _plain_counter(commitments)}
        if dest is None:
            final.append(action)
            row.update(outcome="keep", reason="move without a readable destination")
            moves.append(row)
            continue
        row["destination_commitments_before"] = commitments[dest]
        if commitments[dest] < CAPACITY:
            commitments[dest] += 1
            final.append(action)
            row.update(outcome="keep", reason="destination under capacity",
                       commitments_after=_plain_counter(commitments))
            moves.append(row)
            continue
        unit = context.unit(action["obj_id"])
        candidates, reason = move_candidates(unit, context, router) if unit is not None else ([], "not a unit")
        costs = {dict(c.detail)["destination"]: dict(c.detail)["cost"] for c in candidates}
        base_cost = costs.get(dest)
        options = []
        considered = []
        for candidate in candidates:
            detail = dict(candidate.detail)
            coord, cost = detail["destination"], detail["cost"]
            rejection = None
            if coord == dest:
                rejection = "baseline destination full"
            elif coord not in unheld:
                rejection = "objective held"
            elif commitments[coord] >= CAPACITY:
                rejection = "alternative at capacity"
            elif base_cost is None:
                rejection = "baseline cost unavailable"
            elif cost > DETOUR * base_cost:
                rejection = "outside detour bound"
            value = unheld[coord].value if coord in unheld else None
            weight = value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 1
            rank = [cost / weight, cost, coord]
            considered.append({"destination": coord, "cost": cost, "value": value, "rank": rank,
                               "commitments": commitments[coord], "rejection": rejection})
            if rejection is None:
                options.append((tuple(rank), candidate, coord, cost))
        row.update(base_cost=base_cost, move_candidate_reason=reason, alternatives=considered)
        if not options:
            final.append(None)
            change = {"kind": "withhold", "obj_id": action["obj_id"], "destination": dest,
                      "commitments": commitments[dest], "reason": reason or "no objective under capacity"}
            changes.append(change)
            row.update(outcome="withhold", reason=change["reason"], commitments_after=_plain_counter(commitments))
            moves.append(row)
            continue
        _, chosen, coord, cost = min(options, key=lambda option: option[0])
        replacement = chosen.action(seat)
        commitments[coord] += 1
        planned.append((len(final), action, replacement, len(moves)))
        final.append(replacement)
        change = {"kind": "replace", "obj_id": action["obj_id"], "from": dest, "to": coord,
                  "from_cost": base_cost, "to_cost": cost, "commitments_at_from": commitments[dest]}
        changes.append(change)
        row.update(outcome="replace", chosen_destination=coord, chosen_cost=cost,
                   commitments_after=_plain_counter(commitments))
        moves.append(row)
    proposals = [a for a in final if a is not None]
    checked = gate.check(proposals, context, router)
    rejected = {r.obj_id for r in checked.rejected}
    for index, original, replacement, move_index in planned:
        if replacement["obj_id"] in rejected:
            final[index] = original
            reason = next(r.reason for r in checked.rejected if r.obj_id == original["obj_id"])
            changes.append({"kind": "revert", "obj_id": original["obj_id"], "reason": reason})
            moves[move_index]["outcome"] = "revert"
            moves[move_index]["gate_rejection"] = reason
    return AllocationAudit(tuple(a for a in final if a is not None), tuple(changes), tuple(moves),
                           dict(initial), dict(commitments))


def _baseline_memory(memory: Any) -> Memory:
    return memory.baseline if isinstance(memory, AddonMemory) else memory


class T9DiagnosticCapture(rd.Capture):
    """Full-step private capture plus a seat-local reconstruction of baseline-v2 and T9-v1."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=SAMPLE_EVERY, clock=clock)
        self.costs = costs
        self.final: Optional[Dict[str, Any]] = None
        self._after: Any = None
        self._seats: List[Tuple[int, int]] = []
        self._last = -1
        self.consistency_errors: List[Dict[str, Any]] = []

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        tick = self.clock()
        entry = self.steps[-1]
        submitted, audits, rewritten = [], {}, 0
        for decision in decisions:
            copies = decision.get("submitted")
            if copies is None:
                raise ValueError("the game loop passed no pre-execution copy of the actions")
            for j, action in enumerate(copies):
                submitted.append({"seat": decision["seat"], "faction": decision["faction"], "j": j,
                                  "action": rd.plain(action)})
                if rd.plain(action) != rd.plain(decision["actions"][j]):
                    rewritten += 1
            raw = decision["observation"]
            observation = Observation.from_raw(raw, Origin.ENGINE)
            policy = ShootReservationPolicy(self.costs)
            base = policy.decide(observation, decision["seat"], decision["faction"],
                                 _baseline_memory(decision["memory"]))
            audit = audit_allocation(observation, decision["seat"], decision["faction"], base.actions, policy)
            trace = decision["trace"]
            actual_t9 = getattr(trace, "addon_name", "") == "t9"
            actions_match = (not actual_t9) or rd.plain(audit.actions) == rd.plain(copies)
            changes_match = (not actual_t9) or tuple(canonical_json(v) for v in audit.changes) == trace.changes
            baseline_trace_match = ((not actual_t9) or digest(base.trace) == trace.baseline_trace_sha256)
            row = {"policy": decision["policy"], "baseline_actions": rd.plain(base.actions),
                   "baseline_trace_sha256": digest(base.trace), "hypothetical_t9_actions": rd.plain(audit.actions),
                   "initial_commitments": _plain_counter(audit.initial_commitments),
                   "final_commitments": _plain_counter(audit.final_commitments), "moves": rd.plain(audit.moves),
                   "changes": rd.plain(audit.changes), "actual_t9": actual_t9,
                   "consistency": {"actions": actions_match, "changes": changes_match,
                                   "baseline_trace": baseline_trace_match}}
            audits[str(decision["seat"])] = row
            if not all(row["consistency"].values()):
                self.consistency_errors.append({"k": index, "seat": decision["seat"], **row["consistency"]})
            snapshot = self.ring[-1]
            seat_snapshot = snapshot["seats"].get(decision["seat"])
            if seat_snapshot is not None:
                seat_snapshot["submitted"] = rd.plain(copies)
                seat_snapshot["baseline_actions"] = rd.plain(base.actions)
                seat_snapshot["t9_audit"] = row
        entry["submitted"] = submitted
        entry["rewritten_in_place"] = rewritten
        entry["t9_audit"] = audits
        if index == 0 or (self.events and self.events[-1]["k"] == index):
            self.samples.append(self.ring[-1])
        self._after, self._seats, self._last = after, [(d["seat"], d["faction"]) for d in decisions], index
        self.seconds += self.clock() - tick

    def _final(self) -> Optional[Dict[str, Any]]:
        if self._after is None:
            return None
        global_observation = self._after.global_observation
        return {"k": self._last + 1, "cur_step": global_observation.time().cur_step,
                "global": pickle.dumps(dict(global_observation.fields), protocol=4),
                "seats": {seat: {"faction": faction,
                                  "observation": pickle.dumps(
                                      dict(self._after.for_faction(faction).fields), protocol=4)}
                          for seat, faction in self._seats}}

    def compact(self) -> Dict[str, Any]:
        out = super().compact()
        out["t9_diagnostic_capture_schema"] = CAPTURE_SCHEMA
        out["consistency_errors"] = self.consistency_errors
        return out

    def windows(self) -> Dict[str, Any]:
        out = super().windows()
        out["final"] = self._final()
        return out

    def summary(self, compact: bytes, windows: bytes) -> Dict[str, Any]:
        out = super().summary(compact, windows)
        out.update(schema=CAPTURE_SCHEMA, full_step_snapshots=len(self.samples),
                   consistency_errors=len(self.consistency_errors),
                   compact_sha256=hashlib.sha256(compact).hexdigest(),
                   windows_sha256=hashlib.sha256(windows).hexdigest())
        return out
