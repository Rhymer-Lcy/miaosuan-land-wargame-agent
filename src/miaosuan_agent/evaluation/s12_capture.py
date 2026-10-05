"""Read-only observers of the Sprint 12 screen (``docs/SPRINT12_V3_SCREEN.md``).

Every screen game runs three observers together through Sprint 9's ``Tee``: Sprint 9's ``T9Capture`` unchanged (seat
facts by the definitions that produced the reference populations), :class:`V3CompactCapture` (the candidate's trace
block, comparable with Sprint 10's T9-v2 capture) and :class:`V3Timeline` (a full-step private timeline). Nothing an
observer computes reaches a policy or the engine (``evaluation.game.play``).

:class:`V3Timeline` keeps, for every step, the all-seeing state and every seat's observation and memory (Sprint 10's
full-step form), and the post-step state of the last step. At every decision of a ``baseline-v2`` or v3 seat it
re-decides from that seat's own observation and memory only: ``baseline-v2``'s actions and trace digest, and for a v3
seat the complete batch allocation (incumbents, counted and excluded movers, ranked claimants with their features,
selected claimants, staged paths, withheld units and reasons). It compares the reconstruction with the live decision
(actions, add-on changes and skip counts, and ``baseline-v2``'s trace digest) and records every difference. Raw
identifiers stay in its files, which are written only under the ignored ``local/``.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pickle
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import digest
from ..experiments import t9_batch as tb
from ..experiments.exploratory_addon import AddonMemory
from ..decision.trace import canonical_json
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import residual516 as rd
from .exploratory import ExploreCapture
from .shoot_experiment import CANDIDATE_ID as V2_ID

COMPACT_SCHEMA = "miaosuan-s12-v3-compact-capture/1"
TIMELINE_SCHEMA = "miaosuan-s12-timeline-capture/1"
V3_ID = tb.CANDIDATE_ID
ADDON = "t9_batch"


class V3CompactCapture(ExploreCapture):
    """The exploratory capture plus the candidate's trace block: changes by kind, path hexes removed by staging, and
    per unit the episodes of consecutive decisions in which its baseline-v2 move was staged or withheld."""

    def __init__(self, policies: Sequence[str], clock: Any = None) -> None:
        super().__init__(policies) if clock is None else super().__init__(policies, clock)
        self.kinds: collections.Counter = collections.Counter()
        self.stage_removed: collections.Counter = collections.Counter()
        self.open: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.episodes: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []

    def _close(self, key: Tuple[int, int], end: int) -> None:
        row = self.open.pop(key)
        row["end"] = end
        row["decisions"] = end - row["start"] + 1
        self.episodes.append(row)

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        held: Dict[Tuple[int, int], str] = {}
        for decision in decisions:
            trace = decision["trace"]
            if getattr(trace, "addon_name", "") != ADDON:
                continue
            faction = int(decision["faction"])
            if getattr(trace, "addon_error", None):
                self.errors.append({"k": index, "faction": faction, "error": trace.addon_error})
            for encoded in getattr(trace, "changes", ()):
                change = json.loads(encoded)
                self.kinds[f"{faction}:{change['kind']}"] += 1
                if change["kind"] == "error":
                    self.errors.append({"k": index, "faction": faction, "error": change.get("reason")})
                if change["kind"] == "stage":
                    self.stage_removed[str(int(change["path_length"]) - int(change["staged_path_length"]))] += 1
                if change["kind"] in ("stage", "withhold"):
                    held[(faction, int(change["obj_id"]))] = change["kind"]
        for key in tuple(self.open):
            if key not in held:
                self._close(key, index - 1)
        for key, kind in held.items():
            row = self.open.setdefault(key, {"faction": key[0], "obj_id": key[1], "start": index, "kinds": {}})
            row["kinds"][kind] = row["kinds"].get(kind, 0) + 1

    def all_episodes(self) -> List[Dict[str, Any]]:
        last = self.steps - 1
        rows = list(self.episodes) + [dict(row, end=last, decisions=last - row["start"] + 1)
                                      for row in self.open.values()]
        return sorted(rows, key=lambda r: (r["faction"], r["start"], r["obj_id"]))

    def compact(self) -> Dict[str, Any]:
        out = super().compact()
        out["schema"] = COMPACT_SCHEMA
        episodes = self.all_episodes()
        out["v3"] = {"changes": dict(sorted(self.kinds.items())),
                     "stage_path_hexes_removed": dict(sorted(self.stage_removed.items(), key=lambda i: int(i[0]))),
                     "hold_episodes": episodes,
                     "hold_longest_decisions": max((r["decisions"] for r in episodes), default=0),
                     "errors": self.errors}
        return out

    def summary(self, compact: bytes, series: bytes) -> Dict[str, Any]:
        out = super().summary(compact, series)
        out["schema"] = COMPACT_SCHEMA
        out["v3_errors"] = len(self.errors)
        return out


def plain_allocation(allocation: tb.Allocation) -> Dict[str, Any]:
    """Everything one allocation computed, in JSON form (private: unit ids and hexes)."""
    return {
        "objectives": {str(coord): {**{k: v for k, v in info.items() if k != "mover_bounds"},
                                    "mover_bounds": {str(u): b for u, b in sorted(info["mover_bounds"].items())}}
                       for coord, info in sorted(allocation.objectives.items())},
        "claimants": {str(c.obj_id): {"objective": c.objective, "path": list(c.path), "free_flow": c.free_flow,
                                      "cost": c.cost, "path_length": len(c.path), "feasible": c.feasible,
                                      "index": c.index, "status": c.status}
                      for c in sorted(allocation.claimants.values(), key=lambda c: c.obj_id)},
        "selected": {str(u): coord for u, coord in sorted(allocation.selected.items())},
        "staged": {str(u): list(path) for u, path in sorted(allocation.staged.items())},
        "withheld": {str(u): reason for u, reason in sorted(allocation.withheld.items())},
        "changes": [dict(c) for c in allocation.changes],
        "skipped": dict(sorted(allocation.skipped.items())),
        "error": allocation.error,
    }


def addon_changes(allocation: tb.Allocation) -> Tuple[str, ...]:
    """The trace's change strings that :class:`t9_batch.BatchAddon` derives from an allocation."""
    changes = list(allocation.changes)
    if allocation.error is not None:
        changes.append({"kind": "error", "reason": allocation.error})
    return tuple(canonical_json(dict(c)) for c in changes)


def reconstruct(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts,
                v3: bool) -> Dict[str, Any]:
    """Seat-local reconstruction of one decision: baseline-v2 from the seat's observation and memory, then (for a v3
    seat) the batch allocation of baseline-v2's actions."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory = memory.baseline if isinstance(memory, AddonMemory) else memory
    policy = ShootReservationPolicy(costs)
    base = policy.decide(observation, seat, faction, base_memory)
    out: Dict[str, Any] = {"baseline_actions": rd.plain(base.actions), "baseline_trace_sha256": digest(base.trace),
                           "cur_step": observation.time().cur_step, "max_step": observation.time().max_step,
                           "play": observation.time().stage == Stage.PLAY}
    if v3:
        allocation = tb.allocate(observation, seat, faction, base.actions, policy.router)
        out.update(actions=rd.plain(allocation.actions), changes=addon_changes(allocation),
                   skipped=tuple(sorted(allocation.skipped.items())), allocation=plain_allocation(allocation))
    else:
        out.update(actions=rd.plain(base.actions), trace_sha256=digest(base.trace))
    return out


def consistency(decision: Mapping[str, Any], rebuilt: Mapping[str, Any]) -> Dict[str, bool]:
    """Reconstruction against the live decision: the emitted actions, and for v3 the add-on changes, skip counts and
    baseline-v2's trace digest; for baseline-v2 its own trace digest."""
    trace = decision["trace"]
    live = rd.plain(decision["submitted"])
    if decision["policy"] == V3_ID:
        return {"actions": live == rebuilt["actions"],
                "changes": tuple(getattr(trace, "changes", ())) == tuple(rebuilt["changes"]),
                "skipped": tuple(getattr(trace, "skipped", ())) == tuple(rebuilt["skipped"]),
                "baseline_trace": getattr(trace, "baseline_trace_sha256", None) == rebuilt["baseline_trace_sha256"],
                "addon_error": getattr(trace, "addon_error", None) is None}
    return {"actions": live == rebuilt["actions"], "trace": digest(trace) == rebuilt["trace_sha256"]}


class V3Timeline(rd.Capture):
    """Full-step private timeline with the seat-local reconstruction of every baseline-v2 and v3 decision."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=1, clock=clock)
        self.costs = costs
        self.consistency_errors: List[Dict[str, Any]] = []
        self.reconstructed = 0
        self._after: Any = None
        self._seats: List[Tuple[int, int]] = []
        self._last = -1

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        tick = self.clock()
        entry = self.steps[-1]
        rows: Dict[str, Any] = {}
        submitted = []
        for decision in decisions:
            copies = decision.get("submitted")
            if copies is None:
                raise ValueError("the game loop passed no pre-execution copy of the actions")
            for j, action in enumerate(copies):
                submitted.append({"seat": decision["seat"], "faction": decision["faction"], "j": j,
                                  "action": rd.plain(action)})
            if decision["policy"] not in (V3_ID, V2_ID):
                continue
            rebuilt = reconstruct(decision["observation"], decision["seat"], decision["faction"], decision["memory"],
                                  self.costs, decision["policy"] == V3_ID)
            checks = consistency(decision, rebuilt)
            self.reconstructed += 1
            row = {"policy": decision["policy"], "consistency": checks, "baseline_actions": rebuilt["baseline_actions"],
                   "baseline_trace_sha256": rebuilt["baseline_trace_sha256"], "cur_step": rebuilt["cur_step"],
                   "max_step": rebuilt["max_step"], "play": rebuilt["play"]}
            if decision["policy"] == V3_ID:
                row["allocation"] = rebuilt["allocation"]
            rows[str(decision["seat"])] = row
            if not all(checks.values()):
                self.consistency_errors.append({"k": index, "seat": decision["seat"], **checks})
            seat_snapshot = self.ring[-1]["seats"].get(decision["seat"])
            if seat_snapshot is not None:
                seat_snapshot["submitted"] = rd.plain(copies)
        entry["submitted"] = submitted
        entry["s12"] = rows
        if index == 0 or (self.events and self.events[-1]["k"] == index):
            self.samples.append(self.ring[-1])
        self._after, self._seats, self._last = after, [(d["seat"], d["faction"]) for d in decisions], index
        self.seconds += self.clock() - tick

    def _final(self) -> Optional[Dict[str, Any]]:
        if self._after is None:
            return None
        everything = self._after.global_observation
        return {"k": self._last + 1, "cur_step": everything.time().cur_step,
                "global": pickle.dumps(dict(everything.fields), protocol=4),
                "seats": {seat: {"faction": faction,
                                 "observation": pickle.dumps(dict(self._after.for_faction(faction).fields), protocol=4)}
                          for seat, faction in self._seats}}

    def compact(self) -> Dict[str, Any]:
        out = super().compact()
        out["timeline_schema"] = TIMELINE_SCHEMA
        out["consistency_errors"] = self.consistency_errors
        out["reconstructed_decisions"] = self.reconstructed
        return out

    def windows(self) -> Dict[str, Any]:
        out = super().windows()
        out["final"] = self._final()
        return out

    def summary(self, compact: bytes, windows: bytes) -> Dict[str, Any]:
        return {"schema": TIMELINE_SCHEMA, "steps": len(self.steps), "full_step_snapshots": len(self.samples),
                "reconstructed_decisions": self.reconstructed, "consistency_errors": len(self.consistency_errors),
                "observer_seconds": self.seconds, "compact_sha256": hashlib.sha256(compact).hexdigest(),
                "windows_sha256": hashlib.sha256(windows).hexdigest()}
