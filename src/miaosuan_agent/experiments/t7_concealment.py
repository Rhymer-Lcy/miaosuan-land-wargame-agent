"""Registered T7 candidate ``t7-idle-concealment`` (``docs/T7_DESIGN.md``, section 14) for the mechanism probe.

EXPLORATORY: a mechanism probe candidate (``docs/T7_MECHANISM_PROBE.md``); not eligible for baseline promotion and
never packaged for the platform.

The rule is the Sprint 5 offline shadow, imported and unchanged: :class:`.t7_idle_concealment.IdleConcealmentShadow`
lets the frozen ``baseline-v2`` decide first, keeps every one of its actions in its order, and then orders each own
ground unit, in ascending id, that received no ``baseline-v2`` action and meets the frozen trigger into concealment
(action 6, ``target_state`` 4), after its own check (option listed, exact key set, one action per unit). The shadow's
module docstring predates this registration: this module is the one place that imports it for execution.

This module only adapts the shadow to the platform agent interface and records what it did:

* the trace is ``baseline-v2``'s trace with the candidate's identity, every emitted action in ``emitted``, and a
  ``t7`` block: the SHA-256 of ``baseline-v2``'s own trace for the decision (so a run can be compared, decision by
  decision, with a game ``baseline-v2`` played), every added order and the skip reasons counted by reason;
* fail closed beyond the shadow's own rules: if anything other than a contract violation is raised after
  ``baseline-v2`` decided, the decision is ``baseline-v2``'s alone (recomputed by a fresh instance) and the trace
  records the error; a contract violation is handled by the agent exactly as for ``baseline-v2`` (no action).

Nothing here reads another seat's view, the all-seeing state or hidden information: the inputs are the seat's own
observation, the setup cost data and the memory (``baseline-v2``'s memory plus, per unit, the step of the
candidate's last change-state order).
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Dict, Mapping, Optional, Tuple

from ..boundary import ContractError, MoveCosts, Observation, Origin
from ..decision import StepTrace, digest
from ..decision.policy import Decision
from ..decision.trace import failed
from .shoot_reservation import ShootReservationAgent, ShootReservationPolicy, ShootReservationTrace
from . import t7_idle_concealment as sh

CANDIDATE_ID = "t7-idle-concealment"
TRACE_SCHEMA = "miaosuan-decision-trace/1+occupy-reservation+shoot-reservation+t7-idle-concealment"


@dataclass(frozen=True)
class ConcealmentTrace(ShootReservationTrace):
    """``baseline-v2``'s trace plus the candidate's block.

    ``baseline_trace_sha256``: digest of ``baseline-v2``'s own trace object for this decision; ``added``: (unit,
    target_state) of every concealment order, in emission order; ``skipped``: (reason, count) for the own units
    without a ``baseline-v2`` action that were not ordered; ``error``-like failures of the candidate layer go to
    ``t7_error``.
    """

    baseline_trace_sha256: str = ""
    added: Tuple[Tuple[int, int], ...] = ()
    skipped: Tuple[Tuple[str, int], ...] = ()
    t7_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["schema"] = TRACE_SCHEMA
        payload["t7"] = {"baseline_trace_sha256": self.baseline_trace_sha256,
                         "added": [{"obj_id": u, "target_state": s} for u, s in self.added],
                         "skipped": {reason: count for reason, count in self.skipped},
                         "error": self.t7_error}
        return payload


def _composite(base: StepTrace, actions: Tuple[Mapping[str, Any], ...], added: Tuple[Mapping[str, Any], ...],
               skipped: Tuple[Tuple[str, int], ...], error: Optional[str]) -> ConcealmentTrace:
    values = {f.name: getattr(base, f.name) for f in fields(ShootReservationTrace) if hasattr(base, f.name)}
    values.update(policy=CANDIDATE_ID, emitted=tuple((int(a["type"]), a.get("obj_id")) for a in actions))
    return ConcealmentTrace(**values, baseline_trace_sha256=digest(base),
                            added=tuple((int(a["obj_id"]), int(a["target_state"])) for a in added),
                            skipped=tuple(skipped), t7_error=error)


class ConcealmentPolicy:
    """``baseline-v2`` then the frozen concealment rule (the shadow), with its decision trace."""

    identity = CANDIDATE_ID

    def __init__(self, costs: Optional[MoveCosts]) -> None:
        self.costs = costs
        self.shadow = sh.IdleConcealmentShadow(costs)

    def decide(self, observation: Observation, seat: int, faction: int, memory: sh.ShadowMemory) -> Decision:
        try:
            result = self.shadow.decide(observation, seat, faction, memory)
        except ContractError:
            raise
        except Exception as exc:  # noqa: BLE001 - the candidate layer fails closed to baseline-v2
            base = ShootReservationPolicy(self.costs).decide(observation, seat, faction, memory.baseline)
            error = f"{type(exc).__name__}: {exc}"[:300]
            trace = _composite(base.trace, tuple(base.actions), (), (), error)
            return Decision(tuple(base.actions), trace, replace(memory, baseline=base.memory))
        trace = _composite(result.baseline.trace, tuple(result.actions), result.added, result.skipped, None)
        return Decision(tuple(result.actions), trace, result.memory)


class ConcealmentAgent(ShootReservationAgent):
    """The platform agent interface around :class:`ConcealmentPolicy` (probe use only)."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = CANDIDATE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = ConcealmentPolicy(self.costs)
        self.memory = sh.ShadowMemory()

    def replay(self, observation: Any, memory: sh.ShadowMemory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = ConcealmentPolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)

    def reset(self) -> None:
        super().reset()
        self.memory = sh.ShadowMemory()
