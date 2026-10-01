"""Exploratory tactical candidate ``tactic-deployment-split-1``: deployment disaggregation on top of ``baseline-v2``.

EXPLORATORY: not eligible for baseline promotion.

The one change. During the deployment stage, before ending its deployment, the seat splits every eligible own
operator with the deployment split action (type 314) and, in the next deployment decision, splits the resulting
operators that are still eligible; it ends its deployment (type 333, through ``baseline-v2``'s own deployment rule)
in the first deployment decision in which no operator is eligible, and after two split rounds whatever remains. Per
the platform rules a split turns an operator of 4 vehicles or squads into 2 + 2, of 3 into 2 + 1, of 2 into 1 + 1,
so two rounds take every eligible operator to operators of one vehicle or squad.

An operator is eligible (``can_split``) when the seat controls it, it is on the map (not a passenger), its ``type``
is 1 (infantry) or 2 (vehicle), its ``sub_type`` is not 3 (artillery, which the rules exclude from splitting), and
its ``blood`` is at least 2. Everything is read from the seat's own observation; no scenario, map or unit
identifier is used. The play stage is ``baseline-v2``'s, unchanged.

Legality. Deployment actions are absent from ``valid_actions`` by design (documented), so eligibility comes from the
operator's own fields, and the engine's feedback decides acceptance (recorded by the harness). The project gate does
not catalogue type 314; this module re-checks every split it emits (int fields, this seat, an eligible controllable
operator, the deployment stage, deployment still open) and records each one in the trace's diagnostics.

State. Decisions stay a function of the observation and the memory: ``SplitMemory`` extends ``baseline-v2``'s memory
with the number of split rounds already issued, so the in-game replay check recomputes the same decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, List, Mapping, Optional, Tuple

from ..boundary import ContractError, Observation, Origin
from ..boundary.observation import Stage
from ..decision import Memory, StepTrace
from ..decision.context import TacticalContext, build_context
from ..decision.policy import Decision
from ..decision.trace import failed
from .shoot_reservation import ShootReservationAgent, ShootReservationPolicy, _with_reservations

CANDIDATE_ID = "tactic-deployment-split-1"
DEPLOY_SPLIT = 314
MAX_SPLIT_ROUNDS = 2
GROUND_TYPES = (1, 2)
ARTILLERY = 3
MIN_BLOOD = 2


@dataclass(frozen=True)
class SplitMemory(Memory):
    """``baseline-v2``'s memory plus the number of deployment split rounds this seat has issued."""

    split_rounds: int = 0


def can_split(operator: Any) -> bool:
    """A ground operator of two or more vehicles or squads that is not artillery (observed fields only)."""
    fields = operator.fields
    blood, unit_type, sub_type = fields.get("blood"), fields.get("type"), fields.get("sub_type")
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (blood, unit_type)):
        return False
    return unit_type in GROUND_TYPES and sub_type != ARTILLERY and blood >= MIN_BLOOD


def splittable(observation: Observation, context: TacticalContext) -> List[Tuple[int, int]]:
    """(obj_id, blood) of every eligible operator the seat controls, ascending obj_id."""
    controllable = {unit.obj_id for unit in context.units}
    return sorted((op.obj_id, op.fields["blood"]) for op in observation.operators()
                  if op.obj_id in controllable and can_split(op))


def split_problem(action: Mapping[str, Any], context: TacticalContext, eligible: Tuple[int, ...]) -> Optional[str]:
    """Why a deployment split must not be emitted, or None (the module's own check for type 314)."""
    if set(action) != {"actor", "obj_id", "type"} or action.get("type") != DEPLOY_SPLIT:
        return "not a deployment split"
    if not all(isinstance(action[k], int) and not isinstance(action[k], bool) for k in ("actor", "obj_id")):
        return "fields must be ints"
    if action["actor"] != context.seat:
        return "actor is not this seat"
    if context.stage != Stage.DEPLOYMENT or not context.deployment_available:
        return "deployment is not open"
    if action["obj_id"] not in eligible:
        return "not an eligible controllable operator"
    return None


class DeploymentSplitPolicy(ShootReservationPolicy):
    identity = CANDIDATE_ID

    def decide(self, observation: Observation, seat: int, faction: int, memory: Memory) -> Decision:
        context = build_context(observation, seat, faction)
        rounds = getattr(memory, "split_rounds", 0)
        if (context.stage == Stage.DEPLOYMENT and not memory.deployment_sent and context.deployment_available
                and rounds < MAX_SPLIT_ROUNDS):
            eligible = splittable(observation, context)
            if eligible:
                ids = tuple(obj_id for obj_id, _ in eligible)
                proposals = [{"actor": seat, "obj_id": obj_id, "type": DEPLOY_SPLIT} for obj_id in ids]
                accepted = tuple(p for p in proposals if split_problem(p, context, ids) is None)
                notes = tuple(f"deployment split {obj_id} (blood {blood})" for obj_id, blood in eligible)
                trace = _with_reservations(self._trace(context, f"deployment split round {rounds + 1}: "
                                                                f"{len(accepted)} operators", (), accepted, (), notes),
                                           (), ())
                successor = memory if isinstance(memory, SplitMemory) else SplitMemory(memory.deployment_sent)
                return Decision(accepted, trace, replace(successor, split_rounds=rounds + 1))
        return super().decide(observation, seat, faction, memory)


class DeploymentSplitAgent(ShootReservationAgent):
    """The platform agent interface around the candidate."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = CANDIDATE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = DeploymentSplitPolicy(self.costs)
        self.memory = SplitMemory()

    def replay(self, observation: Any, memory: Memory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = DeploymentSplitPolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)

    def reset(self) -> None:
        super().reset()
        self.memory = SplitMemory()
