"""Read-only full-step observer of the Sprint 27 probe (``docs/SPRINT27_T6S_PROBE.md``).

Each probe game runs three observers together through Sprint 9's ``Tee``: Sprint 9's ``T9Capture`` unchanged, the
exploratory capture (``evaluation.exploratory.ExploreCapture``, unchanged) and :class:`StaggerTimeline`. Nothing an
observer computes reaches a policy or the engine (``evaluation.game.play``).

:class:`StaggerTimeline` is Sprint 22's full-step timeline adapted to a head-to-head game with the stagger candidate: it
keeps, for every step, the all-seeing state and both seats' observations, memories, actions and pre-execution copies,
the engine's feedback, and the post-step state of the last step. At every decision of either seat it re-decides from
that seat's own observation and memory only. For the candidate's seat: ``baseline-v2``'s actions, trace digest and next
memory, then the candidate's rule on those actions (``t6s_column_stagger_p1.apply_rule``: the emitted list, the
withheld indices, the rule events, the next memory); it compares the reconstruction with the live decision (emitted
actions, change records, skip counts, ``baseline-v2``'s trace digest, no add-on error, the policy and add-on names),
checks the memory chain (the memory the seat carries into a decision equals the reconstruction's memory after the
previous decision, and is empty before the first), and checks that every difference between the live actions and
``baseline-v2``'s is the rule's registered withholding (``s27_probe.unregistered_differences``). For the
``baseline-v2`` seat: its actions, trace digest and memory chain. Every finding is recorded. Raw identifiers stay in its
files, which are written only under the ignored ``local/``.
"""

from __future__ import annotations

import hashlib
import pickle
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import Memory, digest
from ..decision.routing import Router
from ..decision.trace import canonical_json
from ..experiments import t6s_column_stagger_p1 as cand
from ..experiments.exploratory_addon import AddonMemory
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import residual516 as rd
from . import s27_probe as sp

TIMELINE_SCHEMA = "miaosuan-s27-timeline-capture/1"
CANDIDATE_ID = cand.CANDIDATE_ID
V2_ID = sp.V2_ID


def split_memory(memory: Any) -> Tuple[Any, Tuple[Tuple[int, int], ...]]:
    if isinstance(memory, AddonMemory):
        return memory.baseline, tuple(tuple(p) for p in memory.addon)
    return memory, ()


def event_rows(result: Any) -> List[List[Any]]:
    """The rule's events as plain rows (kind, episode, unit, step, index, reason, moved)."""
    return [[e.kind, e.eid, e.unit, e.step, e.index, e.reason, e.moved] for e in result.events]


def reconstruct(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts,
                travel: Optional[cand.Travel] = None) -> Dict[str, Any]:
    """Seat-local reconstruction of one candidate decision from the seat's observation and memory."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory, addon_memory = split_memory(memory)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, base_memory)
    travel = travel or cand.router_travel(Router(costs))
    result, memory_out = cand.apply_rule(raw, faction, tuple(base.actions), addon_memory, travel)
    return {"baseline_actions": rd.plain(base.actions), "baseline_trace_sha256": digest(base.trace),
            "baseline_memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY,
            "actions": rd.plain(result.actions), "withheld": list(result.withheld),
            "changes": tuple(canonical_json(dict(c)) for c in cand.change_records(result)),
            "skipped": cand.skip_counts(result), "memory_in": addon_memory, "memory_out": tuple(memory_out),
            "events": event_rows(result), "active_episodes": len(result.memory.episodes)}


def reconstruct_v2(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts) -> Dict[str, Any]:
    """Seat-local reconstruction of one ``baseline-v2`` decision."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, memory)
    return {"baseline_actions": rd.plain(base.actions), "trace_sha256": digest(base.trace),
            "memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY}


def consistency(decision: Mapping[str, Any], rebuilt: Mapping[str, Any],
                expected_memory: Tuple[Any, Tuple[Tuple[int, int], ...]]) -> Dict[str, bool]:
    trace = decision["trace"]
    base_memory, addon_memory = split_memory(decision["memory"])
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["actions"],
            "changes": tuple(getattr(trace, "changes", ())) == tuple(rebuilt["changes"]),
            "skipped": tuple(getattr(trace, "skipped", ())) == tuple(rebuilt["skipped"]),
            "baseline_trace": getattr(trace, "baseline_trace_sha256", None) == rebuilt["baseline_trace_sha256"],
            "addon_error": getattr(trace, "addon_error", None) is None,
            "addon_name": getattr(trace, "addon_name", None) == cand.ADDON_NAME,
            "policy": getattr(trace, "policy", None) == CANDIDATE_ID,
            "baseline_memory": base_memory == expected_memory[0],
            "addon_memory": addon_memory == expected_memory[1]}


def consistency_v2(decision: Mapping[str, Any], rebuilt: Mapping[str, Any], expected_memory: Any) -> Dict[str, bool]:
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["baseline_actions"],
            "trace": digest(decision["trace"]) == rebuilt["trace_sha256"],
            "policy": decision["policy"] == V2_ID,
            "memory": decision["memory"] == expected_memory}


class StaggerTimeline(rd.Capture):
    """Full-step private timeline with the seat-local reconstruction of every decision of both seats."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=1, clock=clock)
        self.costs = costs
        self.travel = cand.router_travel(Router(costs))
        self.consistency_errors: List[Dict[str, Any]] = []
        self.unregistered: List[Dict[str, Any]] = []
        self.reconstructed = 0
        self._expected: Dict[int, Tuple[Any, Tuple[Tuple[int, int], ...]]] = {}
        self._expected_v2: Dict[int, Any] = {}
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
            seat = decision["seat"]
            if decision["policy"] == CANDIDATE_ID:
                rebuilt = reconstruct(decision["observation"], seat, decision["faction"], decision["memory"],
                                      self.costs, self.travel)
                expected = self._expected.get(seat, (Memory(), ()))
                checks = consistency(decision, rebuilt, expected)
                self._expected[seat] = (rebuilt["baseline_memory_out"], rebuilt["memory_out"])
                differences = sp.unregistered_differences(rebuilt["baseline_actions"], rd.plain(copies),
                                                          rebuilt["withheld"])
                rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                                   "baseline_actions": rebuilt["baseline_actions"],
                                   "baseline_trace_sha256": rebuilt["baseline_trace_sha256"],
                                   "cur_step": rebuilt["cur_step"], "max_step": rebuilt["max_step"],
                                   "play": rebuilt["play"], "changes": list(rebuilt["changes"]),
                                   "withheld": rebuilt["withheld"], "events": rebuilt["events"],
                                   "active_episodes": rebuilt["active_episodes"],
                                   "memory_in": [list(p) for p in rebuilt["memory_in"]],
                                   "memory_out": [list(p) for p in rebuilt["memory_out"]],
                                   "unregistered_differences": differences}
            elif decision["policy"] == V2_ID:
                rebuilt = reconstruct_v2(decision["observation"], seat, decision["faction"], decision["memory"],
                                         self.costs)
                expected_v2 = self._expected_v2.get(seat, Memory())
                checks = consistency_v2(decision, rebuilt, expected_v2)
                self._expected_v2[seat] = rebuilt["memory_out"]
                differences = []
                rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                                   "baseline_actions": rebuilt["baseline_actions"],
                                   "trace_sha256": rebuilt["trace_sha256"], "cur_step": rebuilt["cur_step"],
                                   "max_step": rebuilt["max_step"], "play": rebuilt["play"]}
            else:
                continue
            self.reconstructed += 1
            if not all(checks.values()):
                self.consistency_errors.append({"k": index, "seat": seat, **checks})
            if differences:
                self.unregistered.append({"k": index, "seat": seat, "problems": differences})
            seat_snapshot = self.ring[-1]["seats"].get(seat)
            if seat_snapshot is not None:
                seat_snapshot["submitted"] = rd.plain(copies)
        entry["submitted"] = submitted
        entry["s27"] = rows
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
        out["unregistered_differences"] = self.unregistered
        out["reconstructed_decisions"] = self.reconstructed
        return out

    def windows(self) -> Dict[str, Any]:
        out = super().windows()
        out["final"] = self._final()
        return out

    def summary(self, compact: bytes, windows: bytes) -> Dict[str, Any]:
        return {"schema": TIMELINE_SCHEMA, "steps": len(self.steps), "full_step_snapshots": len(self.samples),
                "reconstructed_decisions": self.reconstructed, "consistency_errors": len(self.consistency_errors),
                "unregistered_differences": len(self.unregistered), "observer_seconds": self.seconds,
                "compact_sha256": hashlib.sha256(compact).hexdigest(),
                "windows_sha256": hashlib.sha256(windows).hexdigest()}
