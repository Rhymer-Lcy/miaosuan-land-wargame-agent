"""The coalition agent's memory: Sprint 34's ``CommanderMemory`` plus objective stances and class-aware sightings.

Both additions are sorted tuples of ints and strings, so equal memories are equal values and the decision stays a pure
function of (observation, memory). Sizes are bounded: one stance per objective, sightings expire after the configured
lifetime and are capped at ``MAX_SIGHTINGS``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Optional, Tuple

from ..integrated import memory as M

MAX_SIGHTINGS = 96

Stance = Tuple[int, str, int]                 # (objective hex, stance, since step)
Seen = Tuple[int, int, int, int, int]        # (enemy, hex, step, sub_type, strength per mille)


@dataclass(frozen=True)
class CoalitionMemory(M.CommanderMemory):
    stances: Tuple[Stance, ...] = ()
    seen: Tuple[Seen, ...] = ()

    def stance_of(self, hex_: int) -> Optional[Stance]:
        for s in self.stances:
            if s[0] == hex_:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["stances"] = [list(s) for s in self.stances]
        payload["seen"] = [list(s) for s in self.seen]
        return payload


def canonical(memory: CoalitionMemory) -> CoalitionMemory:
    base = M.canonical(memory)
    return replace(base, stances=tuple(sorted(set(memory.stances))), seen=tuple(sorted(set(memory.seen))))


def updated_seen(previous: Iterable[Seen], observed: Iterable[Tuple[int, int, int, int]], step: int,
                 ttl: int) -> Tuple[Seen, ...]:
    """Latest sighting per enemy ground unit: ``observed`` = (enemy, hex, sub_type, strength per mille) seen now."""
    latest: Dict[int, Seen] = {}
    for s in previous:
        if step - s[2] <= ttl:
            latest[s[0]] = s
    for enemy, hex_, sub_type, strength in observed:
        latest[enemy] = (enemy, hex_, step, sub_type, strength)
    kept = sorted(latest.values(), key=lambda s: (-s[2], s[0]))[:MAX_SIGHTINGS]
    return tuple(sorted(kept))
