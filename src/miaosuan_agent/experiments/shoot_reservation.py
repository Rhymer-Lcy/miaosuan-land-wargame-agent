"""Candidate ``baseline-v2-candidate-shoot-target-reservation``: baseline-v1 on runtime r1, plus one change.

The only change: within one seat's decision step, at most one emitted shoot action targets the same
enemy object.

Everything else is ``baseline-v1`` run on ``baseline-v1-runtime-r1``: the tactical context, candidate
generation, the per-unit priority (engage, occupy, move), every ranking and tie-break (highest attack
level, then lower target id, then lower weapon id), the same-step occupation reservation, the
target-bounded router, deployment and the final safety gate. Units are processed in the same
ascending id order.

The reservation is local to one seat and one decision step. It starts empty. When a unit's selected
shoot action passes the final safety gate, its ``target_obj_id`` is reserved for the rest of the
step. A later unit's shoot options whose target is reserved are excluded before selection; the unit
then selects exactly as baseline-v1 would among what remains: the next shoot option in baseline
order, or, with none left, occupation, movement or nothing, down the unchanged hierarchy. An
action the gate would reject reserves nothing. The gate is applied to the step's proposals
together, as in baseline-v1; for one unit's proposal its verdict does not depend on the other
proposals (its only cross-proposal checks are a second action for the same unit, which cannot
occur because each unit proposes at most one action, and a duplicate deployment completion, which
cannot occur in the play stage), so a proposal is reserved when the gate accepts it on its own.
No state is carried between steps and nothing crosses seats.

The trace records every unit that had a shoot option excluded, the excluded options, the unit that
reserved each target, and the effect on the unit's selection, with a stable project-owned reason.
An excluded option was legal at the start of the step; the exclusion is a coordination decision,
not a legality verdict.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..boundary import ContractError, Observation, Origin
from ..decision import Memory, StepTrace, UnitDecision
from ..decision import gate
from ..decision.candidates import Candidate, Category, engage_candidates, move_candidates, occupy_candidates
from ..decision.context import TacticalContext
from ..decision.policy import PRIORITY, Decision, best
from ..decision.trace import failed
from .occupy_reservation import Coordination, ReservationTrace
from .routing_bounded import BoundedRoutingAgent, BoundedRoutingPolicy

CANDIDATE_ID = "baseline-v2-candidate-shoot-target-reservation"
TRACE_SCHEMA = "miaosuan-decision-trace/1+occupy-reservation+shoot-reservation"


class ShootCoordination(str, enum.Enum):
    """Project-owned reason code of the change. Not an engine or gate verdict."""

    TARGET_RESERVED = "same-step-shoot-target-reserved"


class Effect(str, enum.Enum):
    """What excluding reserved targets did to one unit's selection."""

    UNCHANGED = "unchanged"                # the unit's best shoot option was not excluded
    ALTERNATE_TARGET = "alternate-target"  # the best was excluded; another, unreserved target selected
    OCCUPY = "fallback-occupy"             # no unreserved shoot option; occupation selected
    MOVE = "fallback-move"                 # no unreserved shoot option; movement selected
    NONE = "fallback-none"                 # no unreserved shoot option; nothing selected


#: One excluded option: (target, weapon, attack level, unit whose emitted shoot reserved the target).
Excluded = Tuple[int, int, int, int]


@dataclass(frozen=True)
class ShootReservationTrace(ReservationTrace):
    """baseline-v1's trace, occupation suppressions included, plus the shoot-target exclusions of the step:
    (unit, excluded options, effect, reason) for every unit that had at least one option excluded."""

    shoot_reserved: Tuple[Tuple[int, Tuple[Excluded, ...], str, str], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["schema"] = TRACE_SCHEMA
        payload["shoot_reserved"] = [
            {"obj_id": unit, "effect": effect, "reason": reason,
             "excluded": [{"target_obj_id": t, "weapon_id": w, "attack_level": level, "reserved_by": by}
                          for t, w, level, by in excluded]}
            for unit, excluded, effect, reason in self.shoot_reserved]
        return payload


def _with_reservations(trace: StepTrace, suppressed: Tuple[Tuple[int, int, int, str], ...],
                       shoot_reserved: Tuple[Tuple[int, Tuple[Excluded, ...], str, str], ...]) -> ShootReservationTrace:
    return ShootReservationTrace(**{f.name: getattr(trace, f.name) for f in fields(StepTrace)},
                                 suppressed=suppressed, shoot_reserved=shoot_reserved)


def target_of(candidate: Candidate) -> int:
    return dict(candidate.params)["target_obj_id"]


def _excluded(candidate: Candidate, reserved_by: int) -> Excluded:
    params = dict(candidate.params)
    return params["target_obj_id"], params["weapon_id"], dict(candidate.detail)["attack_level"], reserved_by


class ShootReservationPolicy(BoundedRoutingPolicy):
    """baseline-v1 on runtime r1 with per-seat, per-step shoot-target reservation."""

    identity = CANDIDATE_ID

    def decide(self, observation: Observation, seat: int, faction: int, memory: Memory) -> Decision:
        decision = super().decide(observation, seat, faction, memory)
        if isinstance(decision.trace, ShootReservationTrace):
            return decision
        return replace(decision, trace=_with_reservations(decision.trace, getattr(decision.trace, "suppressed", ()), ()))

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        if self.router is not None:
            self.router.targets = frozenset(city.coord for city in context.objectives)  # runtime r1, unchanged
        proposals: List[Mapping[str, Any]] = []
        units: List[UnitDecision] = []
        diagnostics: List[str] = []
        reserved: Dict[int, int] = {}  # objective hex -> reserving unit (baseline-v1); looked up only, never iterated
        suppressed: List[Tuple[int, int, int, str]] = []
        targets: Dict[int, int] = {}  # shoot target -> unit whose emitted shoot reserved it; looked up only
        shoot_reserved: List[Tuple[int, Tuple[Excluded, ...], str, str]] = []
        for unit in context.units:
            engage, notes = engage_candidates(unit)
            diagnostics.extend(notes)
            move, move_reason = move_candidates(unit, context, self.router)
            by_category = {Category.ENGAGE: engage, Category.OCCUPY: occupy_candidates(unit), Category.MOVE: move}
            counts = tuple((category.value, len(by_category[category])) for category in PRIORITY)
            excluded = [c for c in engage if target_of(c) in targets]
            displaced = bool(excluded) and target_of(best(engage)) in targets
            if excluded:
                by_category[Category.ENGAGE] = [c for c in engage if target_of(c) not in targets]
            selected: Optional[Candidate] = None
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
            if excluded:
                effect = Effect.UNCHANGED
                if displaced:
                    effect = {None: Effect.NONE, Category.ENGAGE: Effect.ALTERNATE_TARGET, Category.OCCUPY: Effect.OCCUPY,
                              Category.MOVE: Effect.MOVE}[None if selected is None else selected.category]
                shoot_reserved.append((unit.obj_id, tuple(_excluded(c, targets[target_of(c)]) for c in excluded),
                                       effect.value, ShootCoordination.TARGET_RESERVED.value))
            if selected is None:
                if displaced or blocked:
                    parts = []
                    if displaced:
                        parts.append(f"shoot targets reserved: {ShootCoordination.TARGET_RESERVED.value}")
                    if blocked:
                        parts.append(f"occupation suppressed: {Coordination.OBJECTIVE_RESERVED.value}")
                    reason = "; ".join(parts) + f"; move: {move_reason}"
                else:
                    reason = "no action listed" if not unit.actions else f"no candidate; move: {move_reason}"
                units.append(UnitDecision(unit.obj_id, counts, "none", no_op_reason=reason))
                continue
            if selected.category is Category.OCCUPY:
                reserved[unit.cur_hex] = unit.obj_id
            detail = selected.detail + ((("suppressed", Coordination.OBJECTIVE_RESERVED.value),) if blocked else ())
            if displaced:
                detail += (("shoot_target_reserved", target_of(best(engage))), ("shoot_reservation", effect.value))
            proposal = selected.action(context.seat)
            proposals.append(proposal)
            if selected.category is Category.ENGAGE and gate.check([proposal], context, self.router).accepted:
                targets[target_of(selected)] = unit.obj_id
            units.append(UnitDecision(unit.obj_id, counts, selected.category.value, int(selected.action_type),
                                      selected.rank, detail))
        result = gate.check(proposals, context, self.router)
        reasons = {rejection.obj_id: rejection.reason for rejection in result.rejected}
        units = [replace(u, validation=("rejected: " + reasons[u.obj_id]) if u.obj_id in reasons
                         else "accepted" if u.action_type is not None else "not applicable") for u in units]
        trace = self._trace(context, None, tuple(units), result.accepted, result.rejected, tuple(diagnostics))
        return Decision(result.accepted, _with_reservations(trace, tuple(suppressed), tuple(shoot_reserved)), memory)


class ShootReservationAgent(BoundedRoutingAgent):
    """The platform agent interface around the candidate (same contract as baseline-v1's agent)."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = CANDIDATE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = ShootReservationPolicy(self.costs)

    def replay(self, observation: Any, memory: Memory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = ShootReservationPolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)
