"""Candidate ``baseline-v1-candidate-occupy-reservation``: ``baseline-v0`` plus one registered change.

The only change: within one decision step, at most one occupation command is issued per objective.
The objective an occupation takes is the one the occupying unit stands on, so the reservation key
is the unit's hex, which for an objective is the objective's ``coord``.

Everything else is ``baseline-v0``, reused by import: the tactical context, candidate generation,
the per-unit priority (engage, occupy, move), every ranking and tie-break, the deployment
behaviour and the final safety gate. Units are processed in the same ascending id order. When a
unit would select occupation for an objective an earlier unit already selected in this step, the
occupation is suppressed and the unit continues down the unchanged baseline hierarchy (in
practice: movement, which the baseline forbids away from an unheld objective the unit stands on,
so the unit does nothing). The suppression is recorded in the trace with a stable reason code. The
reservation lives only for the current decision step; no state is carried between steps.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..agent import PolicyAgent
from ..boundary import ContractError, MoveCosts, Observation, Origin
from ..boundary.checks import require_int
from ..decision import BASELINE_ID, Memory, StepTrace, UnitDecision
from ..decision import gate
from ..decision.candidates import Category, engage_candidates, move_candidates, occupy_candidates
from ..decision.context import TacticalContext
from ..decision.policy import PRIORITY, BaselinePolicy, Decision, best
from ..decision.trace import failed

CANDIDATE_ID = "baseline-v1-candidate-occupy-reservation"
TRACE_SCHEMA = "miaosuan-decision-trace/1+occupy-reservation"


class Coordination(str, enum.Enum):
    """Project-owned reason codes for same-step coordination. Not an engine or gate verdict: the
    suppressed occupation was legal at the start of the step."""

    OBJECTIVE_RESERVED = "same-step-objective-reserved"


@dataclass(frozen=True)
class ReservationTrace(StepTrace):
    """A baseline trace plus the occupations suppressed in the step: (unit, objective hex, reserving unit, reason)."""

    suppressed: Tuple[Tuple[int, int, int, str], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["schema"] = TRACE_SCHEMA
        payload["suppressed"] = [{"obj_id": u, "objective": h, "reserved_by": r, "reason": c}
                                 for u, h, r, c in self.suppressed]
        return payload


def _with_suppressed(trace: StepTrace, suppressed: Tuple[Tuple[int, int, int, str], ...]) -> ReservationTrace:
    return ReservationTrace(**{f.name: getattr(trace, f.name) for f in fields(StepTrace)}, suppressed=suppressed)


class OccupyReservationPolicy(BaselinePolicy):
    identity = CANDIDATE_ID

    def decide(self, observation: Observation, seat: int, faction: int, memory: Memory) -> Decision:
        decision = super().decide(observation, seat, faction, memory)
        if isinstance(decision.trace, ReservationTrace):
            return decision
        return replace(decision, trace=_with_suppressed(decision.trace, ()))

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        proposals: List[Mapping[str, Any]] = []
        units: List[UnitDecision] = []
        diagnostics: List[str] = []
        reserved: Dict[int, int] = {}  # objective hex -> reserving unit; looked up only, never iterated
        suppressed: List[Tuple[int, int, int, str]] = []
        for unit in context.units:
            engage, notes = engage_candidates(unit)
            diagnostics.extend(notes)
            move, move_reason = move_candidates(unit, context, self.router)
            by_category = {Category.ENGAGE: engage, Category.OCCUPY: occupy_candidates(unit), Category.MOVE: move}
            counts = tuple((category.value, len(by_category[category])) for category in PRIORITY)
            selected: Optional[Any] = None
            blocked = False
            for category in PRIORITY:
                options = by_category[category]
                if not options:
                    continue
                if category is Category.OCCUPY and unit.cur_hex in reserved:
                    blocked = True
                    suppressed.append((unit.obj_id, unit.cur_hex, reserved[unit.cur_hex],
                                       Coordination.OBJECTIVE_RESERVED.value))
                    continue
                selected = best(options)
                break
            if selected is None:
                if blocked:
                    reason = f"occupation suppressed: {Coordination.OBJECTIVE_RESERVED.value}; move: {move_reason}"
                else:
                    reason = "no action listed" if not unit.actions else f"no candidate; move: {move_reason}"
                units.append(UnitDecision(unit.obj_id, counts, "none", no_op_reason=reason))
                continue
            if selected.category is Category.OCCUPY:
                reserved[unit.cur_hex] = unit.obj_id
            detail = selected.detail + ((("suppressed", Coordination.OBJECTIVE_RESERVED.value),) if blocked else ())
            proposals.append(selected.action(context.seat))
            units.append(UnitDecision(unit.obj_id, counts, selected.category.value, int(selected.action_type),
                                      selected.rank, detail))
        result = gate.check(proposals, context, self.router)
        reasons = {rejection.obj_id: rejection.reason for rejection in result.rejected}
        units = [replace(u, validation=("rejected: " + reasons[u.obj_id]) if u.obj_id in reasons
                         else "accepted" if u.action_type is not None else "not applicable") for u in units]
        trace = self._trace(context, None, tuple(units), result.accepted, result.rejected, tuple(diagnostics))
        return Decision(result.accepted, _with_suppressed(trace, tuple(suppressed)), memory)


class ReservationAgent(PolicyAgent):
    """The platform agent interface around the candidate policy (same contract as ``PolicyAgent``)."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(BASELINE_ID, origin, strict)
        self.policy_id = CANDIDATE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        self.seat = require_int(setup_info["seat"], "setup_info.seat")
        self.faction = require_int(setup_info["faction"], "setup_info.faction")
        raw_costs = setup_info.get("cost_data")
        self.costs = None if raw_costs is None else MoveCosts.from_raw(raw_costs, self.origin, "setup_info.cost_data")
        self.policy = OccupyReservationPolicy(self.costs)
        self.memory = Memory()
        self.last_trace = None

    def replay(self, observation: Any, memory: Memory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = OccupyReservationPolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)
