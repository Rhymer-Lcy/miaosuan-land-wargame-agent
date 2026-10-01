"""Observe garbage-collection pauses without changing collection behaviour.

A callback registered in ``gc.callbacks`` times every collection (start to stop) and keeps aggregates per
generation, plus the durations of pauses longer than a threshold, capped. It changes no threshold and
triggers no collection; it allocates only when a long pause is kept. Used by diagnostics to tell
collection pauses apart from contention in the decision-latency tail.
"""

from __future__ import annotations

import gc
import time
from typing import Any, Callable, Dict, List, Optional


class GcPauses:
    def __init__(self, keep_over_seconds: float = 0.05, cap: int = 256,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self.keep_over, self.cap, self.clock = keep_over_seconds, cap, clock
        self.count = [0, 0, 0]
        self.total = [0.0, 0.0, 0.0]
        self.longest = [0.0, 0.0, 0.0]
        self.kept: List[List[float]] = []
        self._started: Optional[float] = None
        self._installed = False

    def __call__(self, phase: str, info: Dict[str, Any]) -> None:
        if phase == "start":
            self._started = self.clock()
            return
        if self._started is None:
            return
        pause = self.clock() - self._started
        self._started = None
        generation = int(info.get("generation", 2))
        self.count[generation] += 1
        self.total[generation] += pause
        if pause > self.longest[generation]:
            self.longest[generation] = pause
        if pause > self.keep_over and len(self.kept) < self.cap:
            self.kept.append([generation, pause])

    def install(self) -> "GcPauses":
        gc.callbacks.append(self)
        self._installed = True
        return self

    def remove(self) -> None:
        if self._installed and self in gc.callbacks:
            gc.callbacks.remove(self)
        self._installed = False

    def summary(self) -> Dict[str, Any]:
        return {"count": list(self.count), "total_ms": [round(t * 1000, 3) for t in self.total],
                "max_ms": [round(t * 1000, 3) for t in self.longest],
                "kept_over_ms": round(self.keep_over * 1000, 3),
                "kept": [[int(g), round(p * 1000, 3)] for g, p in self.kept]}
