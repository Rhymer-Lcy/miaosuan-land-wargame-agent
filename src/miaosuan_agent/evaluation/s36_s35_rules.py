"""Sprint 35's registered rules expressed for the Sprint 36 study derivation (``evaluation.s36_study``).

Nothing of Sprint 35 is changed: the functions called are ``evaluation.s35_live.structural``, ``batch_gate`` and
``disposition`` exactly as registered (rules ``s35-coalition-live-rules-1``). The adapter only says where each applies:
the structural stops after every game ("any one closes the study at once"), the batch gate after a batch's last game,
the disposition at the end of a complete schedule. Applied to the 19 recorded games it must reproduce the registered
disposition ``S35_LIVE_INVALID`` with the stop at position 19 (``scripts/s36_s35_rederive.py``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import s35_live as sl
from .s36_study import Rules

REASON_KIND = {"structural stop": "structural", "severe harm": "harm",
               "Dbar at or below the reject threshold": "futility", "schedule complete": "complete"}


def _game_stop(facts: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> Optional[Tuple[str, List[str]]]:
    stops = sl.structural(facts)
    if stops:
        return "structural", [f"{code}: {text}" for code, texts in sorted(stops.items()) for text in texts]
    return None


def _batch_gate(batch: str, history: Sequence[Mapping[str, Any]]) -> Optional[Tuple[str, List[str]]]:
    gate = sl.batch_gate(batch, list(history))
    if gate["open"]:
        return None
    kind = REASON_KIND[gate["reason"]]
    return kind, [gate["reason"]] + list(gate.get("findings") or [])


def _final(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    gates = []
    for batch, positions in sl.BATCHES.items():
        played = [f for f in history if f["position"] <= max(positions)]
        gates.append(sl.batch_gate(batch, played))
    return sl.disposition(list(history), gates)


RULES = Rules(
    rules_id=sl.RULES_ID,
    batches=tuple((b, tuple(r)) for b, r in sl.BATCHES.items()),
    game_stop=_game_stop, batch_gate=_batch_gate, final=_final,
    stop_dispositions={"protocol": "S35_LIVE_INVALID", "structural": "S35_LIVE_INVALID",
                       "agent": "S35_LIVE_INVALID", "harm": "S35_INTEGRATED_REJECT",
                       "futility": "S35_INTEGRATED_REJECT", "complete": "S35_INTEGRATED_INCONCLUSIVE"},
    not_started="S35_LIVE_NOT_AUTHORIZED", in_progress="S35 schedule in progress (no registered disposition)",
    sources=(sl.structural, sl.batch_gate, sl.disposition),
)

__all__ = ["RULES"]
