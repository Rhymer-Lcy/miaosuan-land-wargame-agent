"""EXPLORATORY add-on wrapper: ``baseline-v2`` decides first, then one add-on rule edits that decision.

EXPLORATORY track (``docs/EXPLORATORY_TRACK.md``): candidates built on this wrapper are not eligible for baseline
promotion and are never packaged for the platform. A later claim of improvement needs its own registered
confirmatory study.

The frozen ``baseline-v2`` (:class:`.shoot_reservation.ShootReservationPolicy`) is imported and run unchanged. Its
decision is handed to the add-on, which returns the final list of actions together with a record of what it changed
(added, replaced or withheld actions) and why it left units alone. The add-on checks every action it adds or
replaces itself; action types outside the project gate's catalogue are checked against the unit's listing in the
current observation, with an exact key set and at most one action per unit.

Fail closed: if the add-on raises anything other than a contract violation, the decision is ``baseline-v2``'s alone
(recomputed by a fresh instance) and the trace records the error; a contract violation is handled by the agent
exactly as for ``baseline-v2`` (no action).

The trace is ``baseline-v2``'s trace with the candidate's identity, every emitted action in ``emitted``, and one
block named after the add-on: the SHA-256 of ``baseline-v2``'s own trace for the decision (so a game can be compared,
decision by decision, with what ``baseline-v2`` alone would have done), the changes and the skip counts.

Inputs are the seat's own observation, the setup cost data and the memory; nothing reads another seat's view.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, Dict, Mapping, Optional, Tuple

from ..boundary import ContractError, MoveCosts, Observation, Origin
from ..decision import Memory, StepTrace, digest
from ..decision.policy import Decision
from ..decision.trace import canonical_json, failed
from .shoot_reservation import ShootReservationAgent, ShootReservationPolicy, ShootReservationTrace

BASE_SCHEMA = "miaosuan-decision-trace/1+occupy-reservation+shoot-reservation"


@dataclass(frozen=True)
class AddonMemory:
    """``baseline-v2``'s memory plus the add-on's own state as sorted (key, value) pairs of ints."""

    baseline: Memory = field(default_factory=Memory)
    addon: Tuple[Tuple[int, int], ...] = ()


@dataclass(frozen=True)
class AddonResult:
    """What an add-on returns: the final actions in emission order, its changes (JSON-safe mappings), its skip
    counts by reason, and its next state."""

    actions: Tuple[Mapping[str, Any], ...]
    changes: Tuple[Mapping[str, Any], ...] = ()
    skipped: Tuple[Tuple[str, int], ...] = ()
    addon_memory: Tuple[Tuple[int, int], ...] = ()


class Addon:
    """One add-on rule. Subclasses set ``name`` and implement :meth:`apply`."""

    name = "addon"

    def __init__(self, costs: Optional[MoveCosts], baseline: ShootReservationPolicy) -> None:
        self.costs = costs
        self.baseline = baseline

    def apply(self, observation: Observation, seat: int, faction: int, base: Decision,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        raise NotImplementedError


@dataclass(frozen=True)
class AddonTrace(ShootReservationTrace):
    """``baseline-v2``'s trace plus the add-on block (``changes`` holds canonical JSON strings)."""

    addon_name: str = ""
    baseline_trace_sha256: str = ""
    changes: Tuple[str, ...] = ()
    skipped: Tuple[Tuple[str, int], ...] = ()
    addon_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["schema"] = f"{BASE_SCHEMA}+{self.addon_name}"
        payload[self.addon_name] = {"baseline_trace_sha256": self.baseline_trace_sha256,
                                    "changes": list(self.changes),
                                    "skipped": {reason: count for reason, count in self.skipped},
                                    "error": self.addon_error}
        return payload


def _composite(identity: str, name: str, base: StepTrace, actions: Tuple[Mapping[str, Any], ...],
               changes: Tuple[Mapping[str, Any], ...], skipped: Tuple[Tuple[str, int], ...],
               error: Optional[str]) -> AddonTrace:
    values = {f.name: getattr(base, f.name) for f in fields(ShootReservationTrace) if hasattr(base, f.name)}
    values.update(policy=identity, emitted=tuple((int(a["type"]), a.get("obj_id")) for a in actions))
    return AddonTrace(**values, addon_name=name, baseline_trace_sha256=digest(base),
                      changes=tuple(canonical_json(dict(c)) for c in changes), skipped=tuple(skipped),
                      addon_error=error)


class AddonPolicy:
    """``baseline-v2`` then one add-on. Subclasses set ``identity`` and ``addon_class``."""

    identity = "exploratory-addon"
    addon_class = Addon

    def __init__(self, costs: Optional[MoveCosts]) -> None:
        self.costs = costs
        self.baseline = ShootReservationPolicy(costs)
        self.addon = self.addon_class(costs, self.baseline)

    def decide(self, observation: Observation, seat: int, faction: int, memory: AddonMemory) -> Decision:
        base = self.baseline.decide(observation, seat, faction, memory.baseline)
        try:
            result = self.addon.apply(observation, seat, faction, base, memory.addon)
        except ContractError:
            raise
        except Exception as exc:  # noqa: BLE001 - the add-on layer fails closed to baseline-v2
            fresh = ShootReservationPolicy(self.costs).decide(observation, seat, faction, memory.baseline)
            error = f"{type(exc).__name__}: {exc}"[:300]
            trace = _composite(self.identity, self.addon.name, fresh.trace, tuple(fresh.actions), (), (), error)
            return Decision(tuple(fresh.actions), trace, replace(memory, baseline=fresh.memory))
        trace = _composite(self.identity, self.addon.name, base.trace, tuple(result.actions), result.changes,
                           result.skipped, None)
        return Decision(tuple(result.actions), trace, AddonMemory(base.memory, tuple(result.addon_memory)))


class AddonAgent(ShootReservationAgent):
    """The platform agent interface around an :class:`AddonPolicy` subclass (exploratory use only)."""

    policy_class = AddonPolicy

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = self.policy_class.identity

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = self.policy_class(self.costs)
        self.memory = AddonMemory()

    def replay(self, observation: Any, memory: AddonMemory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = self.policy_class(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)

    def reset(self) -> None:
        super().reset()
        self.memory = AddonMemory()


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def hex_distance(a: int, b: int) -> int:
    """Hex distance between two four-digit hexes (row * 100 + col, odd rows shifted), via cube coordinates.

    The same formula as ``evaluation.t7_visibility.hex_distance``; repeated here so that a candidate's source set
    does not include an analysis module.
    """
    (r1, c1), (r2, c2) = divmod(a, 100), divmod(b, 100)
    q1, q2 = c1 - (r1 - (r1 & 1)) // 2, c2 - (r2 - (r2 & 1)) // 2
    return (abs(q1 - q2) + abs(r1 - r2) + abs((-q1 - r1) - (-q2 - r2))) // 2
