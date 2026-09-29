"""The deterministic baseline policy ``baseline-v0`` and the inert control policy ``inert-v0``.

Baseline decision hierarchy, applied to canonical boundary objects only:

1. Deployment stage (``time.stage == 1``): end the seat's deployment once, when available; no unit
   actions are proposed while deploying.
2. Play stage (``time.stage == 2``): each controllable unit, in ascending ``obj_id`` order, gets at
   most one action, from the first category that has a candidate:

   a. engage: the listed shoot option with the highest attack level (at least 1); ties by lower
      target id, then lower weapon id;
   b. occupy: when occupation is listed for the unit;
   c. move: towards the objective not held by the unit's faction with the lowest path cost from the
      unit's hex (ties: lower hex), along the cheapest path, avoiding roadblocks for vehicles; not
      while the unit is executing a move, and not away from an objective it stands on;

   otherwise the unit does nothing, and the trace records why.
3. Any other stage value: no action.

The inert control ends its deployment the same way (the game cannot start otherwise) and never
issues a unit action. Every proposed action passes :mod:`.gate`. Neither policy uses randomness,
the clock, or any state other than the explicit :class:`Memory` passed in and returned.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Stage
from . import gate
from .candidates import (Candidate, Category, deployment_candidates, engage_candidates, move_candidates,
                         occupy_candidates)
from .context import TacticalContext, build_context
from .routing import Router
from .trace import StepTrace, UnitDecision

BASELINE_ID = "baseline-v0"
INERT_ID = "inert-v0"
#: Per-unit category order in the play stage.
PRIORITY = (Category.ENGAGE, Category.OCCUPY, Category.MOVE)


@dataclass(frozen=True)
class Memory:
    """The only state carried between steps: whether this seat already ended its deployment."""

    deployment_sent: bool = False


@dataclass(frozen=True)
class Decision:
    actions: Tuple[Mapping[str, Any], ...]
    trace: StepTrace
    memory: Memory


def best(candidates: Sequence[Candidate]) -> Candidate:
    """The candidate with the smallest rank. Ranks within one category never tie (they end in ids)."""
    return min(candidates, key=lambda candidate: candidate.rank)


class BaselinePolicy:
    identity = BASELINE_ID

    def __init__(self, costs: Optional[MoveCosts]) -> None:
        self.router = Router(costs) if costs is not None else None

    def decide(self, observation: Observation, seat: int, faction: int, memory: Memory) -> Decision:
        context = build_context(observation, seat, faction)
        if context.stage == Stage.DEPLOYMENT:
            return self._deploy(context, memory)
        if context.stage == Stage.PLAY:
            return self._play(context, memory)
        trace = self._trace(context, None, (), (), (), (f"stage {context.stage} is not interpreted; no action",))
        return Decision(actions=(), trace=trace, memory=memory)

    def _deploy(self, context: TacticalContext, memory: Memory) -> Decision:
        if memory.deployment_sent:
            return Decision((), self._trace(context, "already sent", (), (), (), ()), memory)
        candidates = deployment_candidates(context)
        if not candidates:
            return Decision((), self._trace(context, "not available", (), (), (), ()), memory)
        result = gate.check([candidates[0].action(context.seat)], context, self.router)
        status = "emitted" if result.accepted else "rejected by the gate"
        trace = self._trace(context, status, (), result.accepted, result.rejected, ())
        return Decision(result.accepted, trace, replace(memory, deployment_sent=bool(result.accepted)))

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        proposals: List[Mapping[str, Any]] = []
        units: List[UnitDecision] = []
        diagnostics: List[str] = []
        for unit in context.units:
            engage, notes = engage_candidates(unit)
            diagnostics.extend(notes)
            move, move_reason = move_candidates(unit, context, self.router)
            by_category = {Category.ENGAGE: engage, Category.OCCUPY: occupy_candidates(unit), Category.MOVE: move}
            counts = tuple((category.value, len(by_category[category])) for category in PRIORITY)
            selected = next((best(by_category[c]) for c in PRIORITY if by_category[c]), None)
            if selected is None:
                reason = "no action listed" if not unit.actions else f"no candidate; move: {move_reason}"
                units.append(UnitDecision(unit.obj_id, counts, "none", no_op_reason=reason))
                continue
            proposals.append(selected.action(context.seat))
            units.append(UnitDecision(unit.obj_id, counts, selected.category.value, int(selected.action_type),
                                      selected.rank, selected.detail))
        result = gate.check(proposals, context, self.router)
        reasons = {rejection.obj_id: rejection.reason for rejection in result.rejected}
        units = [replace(u, validation=("rejected: " + reasons[u.obj_id]) if u.obj_id in reasons
                         else "accepted" if u.action_type is not None else "not applicable") for u in units]
        trace = self._trace(context, None, tuple(units), result.accepted, result.rejected, tuple(diagnostics))
        return Decision(result.accepted, trace, memory)

    def _trace(self, context: TacticalContext, deployment: Optional[str], units: Tuple[UnitDecision, ...],
               accepted: Sequence[Mapping[str, Any]], rejected: Sequence[gate.Rejection],
               diagnostics: Tuple[str, ...]) -> StepTrace:
        return StepTrace(
            policy=self.identity, step=context.cur_step, stage=context.stage, seat=context.seat,
            faction=context.faction, deployment=deployment, units=units, excluded=context.excluded,
            emitted=tuple((int(a["type"]), a.get("obj_id")) for a in accepted),
            rejected=tuple((r.action_type, r.obj_id, r.reason) for r in rejected),
            diagnostics=diagnostics,
        )


class InertPolicy(BaselinePolicy):
    """Control policy: ends deployment like the baseline, then never issues a unit action."""

    identity = INERT_ID

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        units = tuple(UnitDecision(unit.obj_id, (), "none", no_op_reason="inert control policy")
                      for unit in context.units)
        return Decision((), self._trace(context, None, units, (), (), ()), memory)


POLICIES = {BASELINE_ID: BaselinePolicy, INERT_ID: InertPolicy}
