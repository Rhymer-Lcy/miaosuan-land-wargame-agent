"""Deterministic decision making above the canonical boundary.

Action meanings and their evidence live in :mod:`.semantics`; candidates are generated from the
current legal-action information (:mod:`.candidates`) over a tactical context (:mod:`.context`);
:mod:`.trace` records why each action was chosen.
"""

from .semantics import CATALOG, MIN_ATTACK_LEVEL, ActionSemantics, ActionType, Legality, Parameters
from .trace import SCHEMA as TRACE_SCHEMA
from .trace import StepTrace, UnitDecision, canonical_json, digest

__all__ = [
    "CATALOG", "MIN_ATTACK_LEVEL", "TRACE_SCHEMA", "ActionSemantics", "ActionType", "Legality", "Parameters",
    "StepTrace", "UnitDecision", "canonical_json", "digest",
]
