"""The tactical agent's memory: Sprint 35's ``CoalitionMemory`` plus enemy posts and recent objective losses.

``posts`` keeps, for each enemy ground unit seen standing without a move path, the hex and the step since which it has
been seen standing there; an enemy seen moving loses its post. ``lost`` keeps the step each held objective was last
lost. Both are sorted tuples of ints (equal memories are equal values) and bounded: posts expire with the sighting
lifetime and are capped at ``MAX_POSTS``; one loss record per objective.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Optional, Tuple

from ..coalition import memory as CM

MAX_POSTS = 96

Post = Tuple[int, int, int, int]      # (enemy, hex, since step, last seen step)
Loss = Tuple[int, int]                # (objective hex, step it was last lost)


@dataclass(frozen=True)
class TacticalMemory(CM.CoalitionMemory):
    posts: Tuple[Post, ...] = ()
    lost: Tuple[Loss, ...] = ()
    held: Tuple[int, ...] = ()

    def post_of(self, enemy: int) -> Optional[Post]:
        for p in self.posts:
            if p[0] == enemy:
                return p
        return None

    def lost_at(self, hex_: int) -> Optional[int]:
        for h, step in self.lost:
            if h == hex_:
                return step
        return None

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["posts"] = [list(p) for p in self.posts]
        payload["lost"] = [list(x) for x in self.lost]
        payload["held"] = list(self.held)
        return payload


def canonical(memory: TacticalMemory) -> TacticalMemory:
    base = CM.canonical(memory)
    return replace(base, posts=tuple(sorted(set(memory.posts))), lost=tuple(sorted(set(memory.lost))),
                   held=tuple(sorted(set(memory.held))))


def updated_posts(previous: Iterable[Post], standing: Iterable[Tuple[int, int]], moving: Iterable[int], step: int,
                  ttl: int) -> Tuple[Post, ...]:
    """``standing``: (enemy, hex) seen now without a path; ``moving``: enemies seen now with a path."""
    latest: Dict[int, Post] = {}
    for p in previous:
        if step - p[3] <= ttl:
            latest[p[0]] = p
    for enemy in moving:
        latest.pop(enemy, None)
    for enemy, hex_ in standing:
        prior = latest.get(enemy)
        since = prior[2] if prior is not None and prior[1] == hex_ else step
        latest[enemy] = (enemy, hex_, since, step)
    kept = sorted(latest.values(), key=lambda p: (-p[3], p[0]))[:MAX_POSTS]
    return tuple(sorted(kept))


def updated_losses(previous: Iterable[Loss], held_before: Iterable[int], held_now: Iterable[int],
                   step: int) -> Tuple[Loss, ...]:
    out = {h: s for h, s in previous}
    now = set(held_now)
    for h in held_before:
        if h not in now:
            out[h] = step
    return tuple(sorted(out.items()))
