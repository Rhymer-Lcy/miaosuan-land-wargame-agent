"""Deterministic decision making above the canonical boundary.

The pipeline for one step: canonical observation -> tactical context (:mod:`.context`) ->
candidates from the current legal-action information (:mod:`.candidates`) -> priority and
tie-breaking (:mod:`.policy`) -> final safety gate (:mod:`.gate`) -> emitted actions plus a
decision trace (:mod:`.trace`). Action meanings and their evidence live in :mod:`.semantics`.
"""

from .gate import GateResult, Rejection
from .policy import BASELINE_ID, INERT_ID, POLICIES, BaselinePolicy, Decision, InertPolicy, Memory
from .semantics import CATALOG, MIN_ATTACK_LEVEL, ActionSemantics, ActionType, Legality, Parameters
from .trace import SCHEMA as TRACE_SCHEMA
from .trace import StepTrace, UnitDecision, canonical_json, digest

__all__ = [
    "BASELINE_ID", "CATALOG", "INERT_ID", "MIN_ATTACK_LEVEL", "POLICIES", "TRACE_SCHEMA", "ActionSemantics",
    "ActionType", "BaselinePolicy", "Decision", "GateResult", "InertPolicy", "Legality", "Memory",
    "Parameters", "Rejection", "StepTrace", "UnitDecision", "canonical_json", "digest",
]
