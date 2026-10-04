"""Private action-level capture for Sprint 10's exploratory T9-v2 screen.

The generic exploratory observer already records scores, objective snapshots, firing, waiting ground units and
objective commitment maxima.  This subclass adds the missing unit-level duration evidence for T9-v2: continuous
withholding episodes and same-route staging lengths.  Raw unit identifiers remain only in ignored ``local/``
captures; the public analyzer emits aggregates.
"""

from __future__ import annotations

import collections
import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .exploratory import ExploreCapture

CAPTURE_SCHEMA = "miaosuan-t9-v2-exploratory-capture/1"


class T9V2Capture(ExploreCapture):
    """Extend the read-only exploratory capture with T9-v2 action episodes."""

    def __init__(self, policies: Sequence[str], clock: Any = None) -> None:
        super().__init__(policies) if clock is None else super().__init__(policies, clock)
        self.stage_removed: collections.Counter = collections.Counter()
        self.stage_units: set[Tuple[int, int]] = set()
        self.withhold_units: set[Tuple[int, int]] = set()
        self.withhold_open: Dict[Tuple[int, int], int] = {}
        self.withhold_episodes: List[Dict[str, int]] = []

    def _close(self, key: Tuple[int, int], end: int) -> None:
        start = self.withhold_open.pop(key)
        self.withhold_episodes.append({"faction": key[0], "obj_id": key[1], "start": start, "end": end,
                                      "decisions": end - start + 1})

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        withheld: set[Tuple[int, int]] = set()
        for decision in decisions:
            trace = decision["trace"]
            if getattr(trace, "addon_name", "") != "t9_staging":
                continue
            faction = int(decision["faction"])
            for encoded in getattr(trace, "changes", ()):
                change = json.loads(encoded)
                obj_id = int(change["obj_id"])
                key = (faction, obj_id)
                if change["kind"] == "stage":
                    removed = int(change["path_length"]) - int(change["staged_path_length"])
                    self.stage_removed[str(removed)] += 1
                    self.stage_units.add(key)
                elif change["kind"] == "withhold":
                    withheld.add(key)
                    self.withhold_units.add(key)
        for key in tuple(self.withhold_open):
            if key not in withheld:
                self._close(key, index - 1)
        for key in withheld:
            self.withhold_open.setdefault(key, index)

    def _episodes(self) -> List[Dict[str, int]]:
        episodes = list(self.withhold_episodes)
        last = self.steps - 1
        episodes.extend({"faction": key[0], "obj_id": key[1], "start": start, "end": last,
                         "decisions": last - start + 1}
                        for key, start in self.withhold_open.items())
        return sorted(episodes, key=lambda row: (row["faction"], row["start"], row["obj_id"]))

    def compact(self) -> Dict[str, Any]:
        out = super().compact()
        episodes = self._episodes()
        out["schema"] = CAPTURE_SCHEMA
        out["t9_v2"] = {
            "stage_path_hexes_removed": dict(sorted(self.stage_removed.items(), key=lambda item: int(item[0]))),
            "stage_unique_units": len(self.stage_units),
            "withhold_unique_units": len(self.withhold_units),
            "withhold_episodes": episodes,
            "withhold_longest_decisions": max((row["decisions"] for row in episodes), default=0),
        }
        return out

    def summary(self, compact: bytes, series: bytes) -> Dict[str, Any]:
        out = super().summary(compact, series)
        out["schema"] = CAPTURE_SCHEMA
        details = self.compact()["t9_v2"]
        out.update(stage_unique_units=details["stage_unique_units"],
                   withhold_unique_units=details["withhold_unique_units"],
                   withhold_longest_decisions=details["withhold_longest_decisions"])
        return out
