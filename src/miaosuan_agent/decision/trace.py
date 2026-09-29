"""Decision traces: a compact, stable, project-owned record of why each action was chosen.

Traces carry unit ids and hexes, which come from scenario data, so runtime traces are written only
under the git-ignored ``local/`` tree. ``digest`` gives a stable hash for step-by-step comparison:
the canonical JSON form sorts every mapping by key and uses Python's shortest round-trip float
representation, so equal traces hash equally on every platform.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

SCHEMA = "miaosuan-decision-trace/1"


@dataclass(frozen=True)
class UnitDecision:
    obj_id: int
    candidates: Tuple[Tuple[str, int], ...]
    rule: str
    action_type: Optional[int] = None
    rank: Optional[Tuple[Any, ...]] = None
    detail: Tuple[Tuple[str, Any], ...] = ()
    no_op_reason: Optional[str] = None
    validation: str = "not applicable"


@dataclass(frozen=True)
class StepTrace:
    """One decision step. ``step`` and ``stage`` are ``None`` only when the observation was unreadable."""

    policy: str
    step: Optional[int]
    stage: Optional[int]
    seat: int
    faction: int
    deployment: Optional[str]
    units: Tuple[UnitDecision, ...]
    excluded: Tuple[Tuple[int, str], ...]
    emitted: Tuple[Tuple[int, Optional[int]], ...]
    rejected: Tuple[Tuple[Any, Any, str], ...] = ()
    diagnostics: Tuple[str, ...] = ()
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA, "policy": self.policy, "step": self.step, "stage": self.stage, "seat": self.seat,
            "faction": self.faction, "deployment": self.deployment,
            "units": [{
                "obj_id": u.obj_id, "candidates": dict(u.candidates), "rule": u.rule, "action_type": u.action_type,
                "rank": None if u.rank is None else list(u.rank), "detail": dict(u.detail),
                "no_op_reason": u.no_op_reason, "validation": u.validation,
            } for u in self.units],
            "excluded": [list(item) for item in self.excluded],
            "emitted": [list(item) for item in self.emitted],
            "rejected": [list(item) for item in self.rejected],
            "diagnostics": list(self.diagnostics),
            "error": self.error,
        }


def failed(policy: str, seat: int, faction: int, error: BaseException) -> StepTrace:
    """The trace of a step whose observation violated the contract: nothing was emitted."""
    return StepTrace(policy=policy, step=None, stage=None, seat=seat, faction=faction, deployment=None,
                     units=(), excluded=(), emitted=(), error=f"{type(error).__name__}: {error}")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(trace: StepTrace) -> str:
    return hashlib.sha256(canonical_json(trace.to_dict()).encode("utf-8")).hexdigest()
