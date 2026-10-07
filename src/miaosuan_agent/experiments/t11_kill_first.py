"""OFFLINE ANALYSIS of the T11-O1 kill-first target rule (``docs/SPRINT20_T11_REPLAY.md``, sections 4 to 6).

Not registered as an engine policy, not packaged and in no run card: no runner, manifest or package imports it, and it
is not in ``decision.policy.POLICIES``. It decides on one recorded seat observation with its own memory and returns what
it would emit; nothing it returns reaches an engine.

:class:`RankedReservationPolicy` is ``baseline-v2`` (``experiments/shoot_reservation.py``) with one variable exposed:
how a unit ranks the engage candidates that remain after the same-step shoot-target reservation has excluded the
reserved targets. Its play step is ``ShootReservationPolicy._play`` restated line for line, so that it can record, for
every unit, the state each selection was made from; everything else is inherited unchanged (deployment, memory, the
tactical context, candidate generation, the hierarchy engage, occupy, move, the occupation reservation, the bounded
router, the final gate and the ascending unit order). With ``ranking=BASELINE`` it must emit exactly what
``baseline-v2`` emits; the Sprint 20 replay checks that on every recorded decision.

With ``ranking=KILL_FIRST`` (the frozen T11-O1 rule) a unit's remaining engage candidates are ranked as follows:

1. group them by target; read each target's ``blood`` from the seat's current observation (the enemy unit with that
   ``obj_id`` among ``operators``);
2. if any of those targets is not a visible enemy, has no ``blood`` field, or has a ``blood`` that is not a
   non-negative integer (booleans excluded), the unit falls back to ``baseline-v2``'s ranking (fail closed);
3. otherwise keep the candidates whose target has the lowest blood and select among them by ``baseline-v2``'s own
   rank (highest attack level, then lower target id, then lower weapon id). Among targets tied on blood this keeps
   ``baseline-v2``'s target order, and on the chosen target it is the highest attack level, then the lower weapon id.

No other quantity enters: no target class or value, objective, threat, distance, retaliation, visibility or
ammunition. The reservation is unchanged: a shot that passes the gate reserves its target for the rest of the seat's
decision, and later units see the reservations of the shots actually selected before them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from ..boundary import Observation
from ..decision import Memory, UnitDecision
from ..decision import gate
from ..decision.candidates import Candidate, Category, engage_candidates, move_candidates, occupy_candidates
from ..decision.context import TacticalContext
from ..decision.policy import PRIORITY, Decision, best
from .occupy_reservation import Coordination
from .shoot_reservation import Effect, ShootCoordination, ShootReservationPolicy, _excluded, _with_reservations, target_of

SHADOW_ID = "t11-kill-first-shadow"
BASELINE = "baseline"
KILL_FIRST = "kill-first"
RANKINGS = (BASELINE, KILL_FIRST)
#: Fail-closed reasons of the kill-first ranking (the unit then uses baseline-v2's ranking).
NOT_VISIBLE = "target_not_visible"
BLOOD_MISSING = "blood_missing"
BLOOD_MALFORMED = "blood_malformed"
FALLBACKS = (NOT_VISIBLE, BLOOD_MISSING, BLOOD_MALFORMED)

#: One shoot choice: (target, weapon, attack level).
Choice = Tuple[int, int, int]


def choice(candidate: Optional[Candidate]) -> Optional[Choice]:
    if candidate is None:
        return None
    params = dict(candidate.params)
    return params["target_obj_id"], params["weapon_id"], dict(candidate.detail)["attack_level"]


def blood_value(value: Any) -> Optional[int]:
    """A comparable observed blood: a non-negative int that is not a bool; anything else is ``None``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


@dataclass(frozen=True)
class UnitView:
    """What the seat sees of one unit on the map: colour, class and raw ``blood`` field (``present`` False if absent)."""

    color: Any
    unit_type: Any
    sub_type: Any
    blood: Any
    present: bool


def unit_views(observation: Observation) -> Dict[int, UnitView]:
    """Every unit of the seat's ``operators`` list (own and enemy), keyed by ``obj_id``."""
    out: Dict[int, UnitView] = {}
    for unit in observation.operators():
        fields = unit.fields
        out[unit.obj_id] = UnitView(fields.get("color"), fields.get("type"), fields.get("sub_type"), fields.get("blood"),
                                    "blood" in fields)
    return out


def enemies_of(views: Mapping[int, UnitView], faction: int) -> Dict[int, UnitView]:
    return {obj: v for obj, v in views.items() if v.color != faction}


def kill_first(options: Sequence[Candidate], enemies: Mapping[int, UnitView]) -> Tuple[Candidate, Optional[str]]:
    """The kill-first selection among ``options`` (non-empty), and the fail-closed reason if it fell back."""
    values: Dict[int, int] = {}
    for target in sorted({target_of(c) for c in options}):
        view = enemies.get(target)
        if view is None:
            return best(options), NOT_VISIBLE
        if not view.present:
            return best(options), BLOOD_MISSING
        value = blood_value(view.blood)
        if value is None:
            return best(options), BLOOD_MALFORMED
        values[target] = value
    lowest = min(values.values())
    return best([c for c in options if values[target_of(c)] == lowest]), None


@dataclass(frozen=True)
class UnitRecord:
    """The state one unit's selection was made from, and the selection (analysis only)."""

    obj_id: int
    unit_type: int
    engage: Tuple[Choice, ...]            # every well-formed engage candidate of the unit (sorted)
    excluded: Tuple[Choice, ...]          # those excluded because their target was reserved earlier in the step
    remaining: Tuple[Choice, ...]         # the rest, which the ranking sees (sorted)
    baseline_choice: Optional[Choice]     # baseline-v2's rank over ``remaining``
    ranked_choice: Optional[Choice]       # this policy's ranking over ``remaining``
    fallback: Optional[str]               # kill-first fail-closed reason, if any
    occupy_blocked: bool                  # occupation listed but the hex reserved earlier in the step
    category: str                         # selected category value, or "none"
    proposal: Optional[Tuple[Tuple[str, Any], ...]]
    reserved_before: FrozenSet[int]       # shoot targets reserved before this unit
    occupied_before: FrozenSet[int]       # objective hexes reserved before this unit
    reserved_by_unit: Optional[int]       # the target this unit's shot reserved, if any


class RankedReservationPolicy(ShootReservationPolicy):
    """``baseline-v2`` with the engage ranking as the only variable; records every unit's selection state."""

    identity = SHADOW_ID

    def __init__(self, costs: Any, ranking: str = KILL_FIRST) -> None:
        if ranking not in RANKINGS:
            raise ValueError(f"unknown ranking {ranking!r}")
        super().__init__(costs)
        self.ranking = ranking
        self.records: Tuple[UnitRecord, ...] = ()
        self.views: Dict[int, UnitView] = {}
        self.enemies: Dict[int, UnitView] = {}
        self._observation: Optional[Observation] = None

    def decide(self, observation: Observation, seat: int, faction: int, memory: Memory) -> Decision:
        self._observation = observation
        self.records = ()
        self.views, self.enemies = {}, {}
        try:
            return super().decide(observation, seat, faction, memory)
        finally:
            self._observation = None

    def rank_engage(self, options: Sequence[Candidate]) -> Tuple[Candidate, Optional[str]]:
        if self.ranking == BASELINE:
            return best(options), None
        return kill_first(options, self.enemies)

    def _play(self, context: TacticalContext, memory: Memory) -> Decision:
        if self._observation is not None:
            self.views = unit_views(self._observation)
            self.enemies = enemies_of(self.views, context.faction)
        if self.router is not None:
            self.router.targets = frozenset(city.coord for city in context.objectives)  # runtime r1, unchanged
        proposals: List[Mapping[str, Any]] = []
        units: List[UnitDecision] = []
        diagnostics: List[str] = []
        reserved: Dict[int, int] = {}
        suppressed: List[Tuple[int, int, int, str]] = []
        targets: Dict[int, int] = {}
        shoot_reserved: List[Tuple[int, Tuple[Any, ...], str, str]] = []
        records: List[UnitRecord] = []
        for unit in context.units:
            reserved_before, occupied_before = frozenset(targets), frozenset(reserved)
            engage, notes = engage_candidates(unit)
            diagnostics.extend(notes)
            move, move_reason = move_candidates(unit, context, self.router)
            by_category = {Category.ENGAGE: engage, Category.OCCUPY: occupy_candidates(unit), Category.MOVE: move}
            counts = tuple((category.value, len(by_category[category])) for category in PRIORITY)
            excluded = [c for c in engage if target_of(c) in targets]
            displaced = bool(excluded) and target_of(best(engage)) in targets
            if excluded:
                by_category[Category.ENGAGE] = [c for c in engage if target_of(c) not in targets]
            remaining = by_category[Category.ENGAGE]
            selected: Optional[Candidate] = None
            blocked = False
            fallback: Optional[str] = None
            ranked: Optional[Candidate] = None
            for category in PRIORITY:
                options = by_category[category]
                if not options:
                    continue
                if category is Category.OCCUPY and unit.cur_hex in reserved:
                    blocked = True
                    suppressed.append((unit.obj_id, unit.cur_hex, reserved[unit.cur_hex],
                                       Coordination.OBJECTIVE_RESERVED.value))
                    continue
                if category is Category.ENGAGE:
                    ranked, fallback = self.rank_engage(options)
                    selected = ranked
                else:
                    selected = best(options)
                break
            effect = Effect.UNCHANGED
            if excluded:
                if displaced:
                    effect = {None: Effect.NONE, Category.ENGAGE: Effect.ALTERNATE_TARGET, Category.OCCUPY: Effect.OCCUPY,
                              Category.MOVE: Effect.MOVE}[None if selected is None else selected.category]
                shoot_reserved.append((unit.obj_id, tuple(_excluded(c, targets[target_of(c)]) for c in excluded),
                                       effect.value, ShootCoordination.TARGET_RESERVED.value))
            reserved_now: Optional[int] = None
            proposal: Optional[Mapping[str, Any]] = None
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
            else:
                if selected.category is Category.OCCUPY:
                    reserved[unit.cur_hex] = unit.obj_id
                detail = selected.detail + ((("suppressed", Coordination.OBJECTIVE_RESERVED.value),) if blocked else ())
                if displaced:
                    detail += (("shoot_target_reserved", target_of(best(engage))), ("shoot_reservation", effect.value))
                proposal = selected.action(context.seat)
                proposals.append(proposal)
                if selected.category is Category.ENGAGE and gate.check([proposal], context, self.router).accepted:
                    targets[target_of(selected)] = unit.obj_id
                    reserved_now = target_of(selected)
                units.append(UnitDecision(unit.obj_id, counts, selected.category.value, int(selected.action_type),
                                          selected.rank, detail))
            records.append(UnitRecord(
                obj_id=unit.obj_id, unit_type=unit.unit_type,
                engage=tuple(sorted(choice(c) for c in engage)),
                excluded=tuple(sorted(choice(c) for c in excluded)),
                remaining=tuple(sorted(choice(c) for c in remaining)),
                baseline_choice=choice(best(remaining)) if remaining else None,
                ranked_choice=choice(ranked), fallback=fallback, occupy_blocked=blocked,
                category="none" if selected is None else selected.category.value,
                proposal=None if proposal is None else tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                                                                    for k, v in proposal.items())),
                reserved_before=reserved_before, occupied_before=occupied_before, reserved_by_unit=reserved_now))
        result = gate.check(proposals, context, self.router)
        reasons = {rejection.obj_id: rejection.reason for rejection in result.rejected}
        units = [replace(u, validation=("rejected: " + reasons[u.obj_id]) if u.obj_id in reasons
                         else "accepted" if u.action_type is not None else "not applicable") for u in units]
        trace = self._trace(context, None, tuple(units), result.accepted, result.rejected, tuple(diagnostics))
        self.records = tuple(records)
        return Decision(result.accepted, _with_reservations(trace, tuple(suppressed), tuple(shoot_reserved)), memory)
