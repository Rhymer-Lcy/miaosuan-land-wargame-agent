"""Candidate ``baseline-v3-candidate-launcher-dependent-shoot-reservation``: baseline-v2 plus one change.

The only change: within one seat's decision step, once a shoot action at some unit has passed the final safety
gate, a later unit of the same seat does not select a shoot option whose target, in the seat's own observation,
names that unit as its ``launcher``. The rule means "avoid a dependent-target shot after scheduling a shot at its
launcher"; it does not mean that the dependent target is known to be destroyed, it predicts no damage and assumes
nothing about whether the launcher survives.

Everything else is ``baseline-v2``: the tactical context, candidate generation, the per-unit priority (engage,
occupy, move), every ranking and tie-break, the same-step occupation reservation, the same-step shoot-target
reservation, the target-bounded router, deployment and the final safety gate, with units processed in the same
ascending id order. The shot targets that the shoot-target reservation records (target -> the unit whose
gate-accepted shot reserved it) are also the launcher set: a target is a reserved launcher exactly when it is a
reserved target. The launcher rule excludes, among the options the shoot-target reservation leaves, those whose
target's launcher is reserved; baseline-v2's logic then runs unchanged on the remaining options (its shoot-target
reservation judging displacement on them, exactly as baseline-v2 deciding on those options would), and the unit
selects as baseline-v2 would, down the unchanged hierarchy. A shot the gate would reject reserves nothing.

The relation is read from the seat's observation only: an operator's ``launcher`` field, ``None`` meaning no
relation. Any other value that is not an int (bools excluded) is malformed: it creates no exclusion and is reported
as a diagnostic, never repaired. Nothing is read from the all-seeing view, nothing crosses seats and nothing is
carried between steps.

The trace records, for every unit with at least one option excluded by the launcher rule, the excluded options
(target, its launcher, weapon, attack level, the unit whose shot reserved the launcher and that shot's position in
the seat's proposals), the effect on the unit's selection and the project-owned reason
``same-step-launcher-target-reserved``.
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
from .occupy_reservation import Coordination
from .shoot_reservation import (Effect, Excluded, ShootCoordination, ShootReservationAgent, ShootReservationPolicy,
                                ShootReservationTrace, _excluded, target_of)

CANDIDATE_ID = "baseline-v3-candidate-launcher-dependent-shoot-reservation"
TRACE_SCHEMA = "miaosuan-decision-trace/1+occupy-reservation+shoot-reservation+launcher-reservation"

#: One option excluded by the launcher rule: (target, its launcher, weapon, attack level, unit whose gate-accepted
#: shot reserved the launcher, that shot's position in the seat's proposals).
LauncherExcluded = Tuple[int, int, int, int, int, int]


class LauncherCoordination(str, enum.Enum):
    """Project-owned reason code of the change. Not an engine or gate verdict."""

    LAUNCHER_TARGET_RESERVED = "same-step-launcher-target-reserved"


@dataclass(frozen=True)
class LauncherReservationTrace(ShootReservationTrace):
    """baseline-v2's trace plus the launcher-rule exclusions of the step: (unit, excluded options, effect, reason)."""

    launcher_reserved: Tuple[Tuple[int, Tuple[LauncherExcluded, ...], str, str], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["schema"] = TRACE_SCHEMA
        payload["launcher_reserved"] = [
            {"obj_id": unit, "effect": effect, "reason": reason,
             "excluded": [{"target_obj_id": t, "launcher": launcher, "weapon_id": w, "attack_level": level,
                           "reserved_by": by, "reserved_by_position": position}
                          for t, launcher, w, level, by, position in excluded]}
            for unit, excluded, effect, reason in self.launcher_reserved]
        return payload


def _with_launcher(trace: StepTrace, launcher_reserved: Tuple[Tuple[int, Tuple[LauncherExcluded, ...], str, str], ...]
                   ) -> LauncherReservationTrace:
    names = [f.name for f in fields(ShootReservationTrace)]
    values = {name: getattr(trace, name, ()) for name in names}
    return LauncherReservationTrace(**values, launcher_reserved=launcher_reserved)


def launcher_relations(observation: Observation) -> Tuple[Dict[int, int], Tuple[str, ...]]:
    """obj_id -> launcher id for every operator of the observation that names one, and diagnostics for malformed
    values. ``None`` (or an absent field) is no relation."""
    relations: Dict[int, int] = {}
    notes: List[str] = []
    for operator in observation.operators():
        value = operator.fields.get("launcher")
        if value is None:
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            relations[operator.obj_id] = value
        else:
            notes.append(f"unit {operator.obj_id}: malformed launcher relation skipped: {value!r}")
    return relations, tuple(sorted(notes))


class LauncherReservationPolicy(ShootReservationPolicy):
    """baseline-v2 with per-seat, per-step launcher-dependent shoot reservation."""

    identity = CANDIDATE_ID

    def __init__(self, costs: Any = None) -> None:
        super().__init__(costs)
        self._relations: Dict[int, int] = {}
        self._relation_notes: Tuple[str, ...] = ()

    def decide(self, observation: Observation, seat: int, faction: int, memory: Memory) -> Decision:
        self._relations, self._relation_notes = launcher_relations(observation)
        try:
            decision = super().decide(observation, seat, faction, memory)
        finally:
            self._relations, self._relation_notes = {}, ()
        if isinstance(decision.trace, LauncherReservationTrace):
            return decision
        return replace(decision, trace=_with_launcher(decision.trace, ()))

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        if self.router is not None:
            self.router.targets = frozenset(city.coord for city in context.objectives)  # runtime r1, unchanged
        proposals: List[Mapping[str, Any]] = []
        units: List[UnitDecision] = []
        diagnostics: List[str] = []
        reserved: Dict[int, int] = {}  # objective hex -> reserving unit (baseline-v1); looked up only, never iterated
        suppressed: List[Tuple[int, int, int, str]] = []
        targets: Dict[int, int] = {}  # shoot target -> unit whose emitted shoot reserved it (baseline-v2)
        positions: Dict[int, int] = {}  # shoot target -> position of that shot in the seat's proposals
        shoot_reserved: List[Tuple[int, Tuple[Excluded, ...], str, str]] = []
        launcher_reserved: List[Tuple[int, Tuple[LauncherExcluded, ...], str, str]] = []
        for unit in context.units:
            engage, notes = engage_candidates(unit)
            diagnostics.extend(notes)
            move, move_reason = move_candidates(unit, context, self.router)
            by_category = {Category.ENGAGE: engage, Category.OCCUPY: occupy_candidates(unit), Category.MOVE: move}
            counts = tuple((category.value, len(by_category[category])) for category in PRIORITY)
            excluded = [c for c in engage if target_of(c) in targets]
            remaining = [c for c in engage if target_of(c) not in targets]
            dependent = [c for c in remaining if self._relations.get(target_of(c)) in targets]
            offered = [c for c in engage if c not in dependent]  # baseline-v2's logic runs on what the rule leaves
            displaced = bool(excluded) and target_of(best(offered)) in targets
            baseline = best(remaining) if remaining else None  # baseline-v2's shoot choice after its own exclusion
            displaced_dependent = baseline is not None and baseline in dependent
            if excluded or dependent:
                by_category[Category.ENGAGE] = [c for c in remaining if c not in dependent]
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
            outcome = {None: Effect.NONE, Category.ENGAGE: Effect.ALTERNATE_TARGET, Category.OCCUPY: Effect.OCCUPY,
                       Category.MOVE: Effect.MOVE}[None if selected is None else selected.category]
            if excluded:
                effect = outcome if displaced else Effect.UNCHANGED
                shoot_reserved.append((unit.obj_id, tuple(_excluded(c, targets[target_of(c)]) for c in excluded),
                                       effect.value, ShootCoordination.TARGET_RESERVED.value))
            if dependent:
                effect = outcome if displaced_dependent else Effect.UNCHANGED
                launcher_reserved.append((unit.obj_id, tuple(
                    (target_of(c), self._relations[target_of(c)], dict(c.params)["weapon_id"],
                     dict(c.detail)["attack_level"], targets[self._relations[target_of(c)]],
                     positions[self._relations[target_of(c)]]) for c in dependent),
                    effect.value, LauncherCoordination.LAUNCHER_TARGET_RESERVED.value))
            if selected is None:
                if displaced or displaced_dependent or blocked:
                    parts = []
                    if displaced:
                        parts.append(f"shoot targets reserved: {ShootCoordination.TARGET_RESERVED.value}")
                    if displaced_dependent:
                        parts.append(f"launcher targets reserved: {LauncherCoordination.LAUNCHER_TARGET_RESERVED.value}")
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
                detail += (("shoot_target_reserved", target_of(best(offered))), ("shoot_reservation", outcome.value))
            if displaced_dependent:
                detail += (("launcher_target_reserved", target_of(baseline)), ("launcher_reservation", outcome.value))
            proposal = selected.action(context.seat)
            proposals.append(proposal)
            if selected.category is Category.ENGAGE and gate.check([proposal], context, self.router).accepted:
                targets[target_of(selected)] = unit.obj_id
                positions[target_of(selected)] = len(proposals) - 1
            units.append(UnitDecision(unit.obj_id, counts, selected.category.value, int(selected.action_type),
                                      selected.rank, detail))
        result = gate.check(proposals, context, self.router)
        reasons = {rejection.obj_id: rejection.reason for rejection in result.rejected}
        units = [replace(u, validation=("rejected: " + reasons[u.obj_id]) if u.obj_id in reasons
                         else "accepted" if u.action_type is not None else "not applicable") for u in units]
        diagnostics.extend(self._relation_notes)  # after baseline-v2's own, so its order is unchanged
        trace = self._trace(context, None, tuple(units), result.accepted, result.rejected, tuple(diagnostics))
        shoot_trace = ShootReservationTrace(**{f.name: getattr(trace, f.name) for f in fields(StepTrace)},
                                            suppressed=tuple(suppressed), shoot_reserved=tuple(shoot_reserved))
        return Decision(result.accepted, _with_launcher(shoot_trace, tuple(launcher_reserved)), memory)


class LauncherReservationAgent(ShootReservationAgent):
    """The platform agent interface around the candidate (same contract as baseline-v2's agent)."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = CANDIDATE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = LauncherReservationPolicy(self.costs)

    def replay(self, observation: Any, memory: Memory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = LauncherReservationPolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)
