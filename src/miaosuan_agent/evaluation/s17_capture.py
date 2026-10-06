"""Read-only full-step observer of the Sprint 17 probe (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``).

Every probe game runs three observers together through Sprint 9's ``Tee``: Sprint 9's ``T9Capture`` unchanged, the
exploratory capture (``evaluation.exploratory.ExploreCapture``, unchanged: add-on change kinds, skip counts and add-on
errors per faction) and :class:`CandidateTimeline`. Nothing an observer computes reaches a policy or the engine
(``evaluation.game.play``).

:class:`CandidateTimeline` is Sprint 12's full-step timeline (``s12_capture.V3Timeline``) for the Sprint 17 candidate:
it keeps, for every step, the all-seeing state and every seat's observation and memory, and the post-step state of the
last step. At every decision of the candidate seat it re-decides from that seat's own observation and memory only:
``baseline-v2``'s actions, trace digest and next memory; the frozen stage-1 allocator's complete allocation on that
state (``t9_batch.allocate``: incumbents, counted movers, ranked claimants, selections, staging, withholding); and the
candidate's allocation (``t9_post_stage_v6.allocate``: claimants, overflow, eligibility, best alternatives,
redirects, staging, withholding, ended records and the next memory). It compares the reconstruction with the live
decision (the emitted actions, the add-on changes and skip counts, ``baseline-v2``'s trace digest, no add-on error)
and checks the memory chain: the live memory before a decision must equal the reconstruction's memory after the
previous one, and be empty before the first decision of the game. Every difference is recorded. Raw identifiers stay
in its files, which are written only under the ignored ``local/``.
"""

from __future__ import annotations

import hashlib
import pickle
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import Memory, digest
from ..decision.trace import canonical_json
from ..experiments import t9_batch as tb
from ..experiments import t9_delayed as td
from ..experiments import t9_post_stage_v6 as c6
from ..experiments.exploratory_addon import AddonMemory
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import residual516 as rd
from .s12_capture import plain_allocation

TIMELINE_SCHEMA = "miaosuan-s17-timeline-capture/1"
CANDIDATE_ID = c6.CANDIDATE_ID


def plain_candidate(allocation: td.Allocation) -> Dict[str, Any]:
    """Everything one candidate allocation computed, in JSON form (private: unit ids and hexes)."""
    return {
        "claimants": {str(c.obj_id): {"objective": c.objective, "path": list(c.path), "free_flow": c.free_flow,
                                      "cost": c.cost, "path_length": len(c.path), "feasible": c.feasible,
                                      "index": c.index, "status": c.status, "key": list(tb.free_flow_key(c))}
                      for c in sorted(allocation.claimants.values(), key=lambda c: c.obj_id)},
        "selected": {str(u): coord for u, coord in sorted(allocation.selected.items())},
        "overflow": list(allocation.overflow),
        "eligible": list(allocation.eligible),
        "best": {str(u): coord for u, coord in sorted(allocation.best.items())},
        "redirected": {str(u): {"objective": o.objective, "path": list(o.path), "cost": o.cost,
                                "base_cost": o.base_cost, "free_flow": o.free_flow, "prefix": o.prefix}
                       for u, o in sorted(allocation.redirected.items())},
        "staged": {str(u): list(path) for u, path in sorted(allocation.staged.items())},
        "withheld": {str(u): reason for u, reason in sorted(allocation.withheld.items())},
        "ended": {str(u): reason for u, reason in sorted(allocation.ended.items())},
        "changes": [dict(c) for c in allocation.changes],
        "skipped": dict(sorted(allocation.skipped.items())),
        "error": allocation.error,
        "memory_out": [list(pair) for pair in allocation.memory],
    }


def split_memory(memory: Any) -> Tuple[Any, Tuple[Tuple[int, int], ...]]:
    if isinstance(memory, AddonMemory):
        return memory.baseline, tuple(tuple(p) for p in memory.addon)
    return memory, ()


def reconstruct(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts) -> Dict[str, Any]:
    """Seat-local reconstruction of one candidate decision from the seat's observation and memory: baseline-v2, the
    stage-1 allocator's allocation of baseline-v2's actions, and the candidate's allocation with its next memory."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory, addon_memory = split_memory(memory)
    policy = ShootReservationPolicy(costs)
    base = policy.decide(observation, seat, faction, base_memory)
    v3 = tb.allocate(observation, seat, faction, base.actions, policy.router)
    candidate = c6.allocate(observation, seat, faction, base.actions, policy.router, addon_memory)
    return {"baseline_actions": rd.plain(base.actions), "baseline_trace_sha256": digest(base.trace),
            "baseline_memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY,
            "actions": rd.plain(candidate.actions),
            "changes": tuple(canonical_json(dict(c)) for c in c6.trace_changes(candidate)),
            "skipped": tuple(sorted(candidate.skipped.items())), "memory_in": addon_memory,
            "memory_out": tuple(candidate.memory), "v3_actions": rd.plain(v3.actions),
            "v3_allocation": plain_allocation(v3), "candidate": plain_candidate(candidate)}


def consistency(decision: Mapping[str, Any], rebuilt: Mapping[str, Any],
                expected_memory: Tuple[Any, Tuple[Tuple[int, int], ...]]) -> Dict[str, bool]:
    """Reconstruction against the live decision: the emitted actions, the add-on changes and skip counts,
    baseline-v2's trace digest, no add-on error, and the memory the seat carried into this decision (baseline-v2's
    and the add-on's) equal to the reconstruction of the previous decision (empty at the first)."""
    trace = decision["trace"]
    base_memory, addon_memory = split_memory(decision["memory"])
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["actions"],
            "changes": tuple(getattr(trace, "changes", ())) == tuple(rebuilt["changes"]),
            "skipped": tuple(getattr(trace, "skipped", ())) == tuple(rebuilt["skipped"]),
            "baseline_trace": getattr(trace, "baseline_trace_sha256", None) == rebuilt["baseline_trace_sha256"],
            "addon_error": getattr(trace, "addon_error", None) is None,
            "addon_name": getattr(trace, "addon_name", None) == c6.ADDON_NAME,
            "policy": getattr(trace, "policy", None) == CANDIDATE_ID,
            "baseline_memory": base_memory == expected_memory[0],
            "addon_memory": addon_memory == expected_memory[1]}


def prefix_inputs(timeline: Mapping[str, Any], windows: Mapping[str, Any], seat: int, divergence: int
                  ) -> Dict[str, Any]:
    """What the prefix check (``s17_probe.prefix_problems``) reads from one game: the digests of the seat's emitted
    actions at every decision and of the add-on memory it carried into every decision, and at the registered
    divergence the units whose actions differ from the stage-1 allocator's reconstruction and the candidate's
    redirects (unit -> [objective, route])."""
    from . import s17_probe as sp
    steps = timeline.get("steps") or []
    actions = [sp.actions_digest([a["action"] for a in step.get("submitted") or () if a["seat"] == seat])
               for step in steps]
    samples = sorted(windows.get("samples") or (), key=lambda s: s["k"])
    memory = []
    for sample in samples:
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        memory.append(sp.memory_digest(split_memory(pickle.loads(snap["memory"]))[1]))
    changed: List[Any] = []
    redirects: Dict[str, Any] = {}
    if divergence < len(steps):
        row = (steps[divergence].get("s17") or {}).get(str(seat)) or {}
        live = [a["action"] for a in steps[divergence].get("submitted") or () if a["seat"] == seat]
        changed = changed_units(row.get("v3_actions") or [], live)
        redirects = {u: [r["objective"], list(r["path"])]
                     for u, r in ((row.get("candidate") or {}).get("redirected") or {}).items()}
    return {"actions": actions, "memory": memory, "changed": changed, "redirects": redirects}


def changed_units(first: Sequence[Mapping[str, Any]], second: Sequence[Mapping[str, Any]]) -> List[Any]:
    """Units whose emitted actions differ between two action lists (an action present in one list only included)."""
    def by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, List[Dict[str, Any]]]:
        out: Dict[Any, List[Dict[str, Any]]] = {}
        for action in actions:
            out.setdefault(action.get("obj_id"), []).append({str(k): v for k, v in dict(action).items()})
        return out
    a, b = by_unit(first), by_unit(second)
    return sorted((u for u in set(a) | set(b) if a.get(u) != b.get(u)), key=str)


class CandidateTimeline(rd.Capture):
    """Full-step private timeline with the seat-local reconstruction of every candidate decision."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=1, clock=clock)
        self.costs = costs
        self.consistency_errors: List[Dict[str, Any]] = []
        self.reconstructed = 0
        self._expected: Dict[int, Tuple[Any, Tuple[Tuple[int, int], ...]]] = {}
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
            if decision["policy"] != CANDIDATE_ID:
                continue
            seat = decision["seat"]
            rebuilt = reconstruct(decision["observation"], seat, decision["faction"], decision["memory"], self.costs)
            expected = self._expected.get(seat, (Memory(), ()))
            checks = consistency(decision, rebuilt, expected)
            self._expected[seat] = (rebuilt["baseline_memory_out"], rebuilt["memory_out"])
            self.reconstructed += 1
            rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                               "baseline_actions": rebuilt["baseline_actions"],
                               "baseline_trace_sha256": rebuilt["baseline_trace_sha256"],
                               "cur_step": rebuilt["cur_step"], "max_step": rebuilt["max_step"],
                               "play": rebuilt["play"], "v3_actions": rebuilt["v3_actions"],
                               "v3_allocation": rebuilt["v3_allocation"], "candidate": rebuilt["candidate"],
                               "memory_in": [list(p) for p in rebuilt["memory_in"]]}
            if not all(checks.values()):
                self.consistency_errors.append({"k": index, "seat": seat, **checks})
            seat_snapshot = self.ring[-1]["seats"].get(seat)
            if seat_snapshot is not None:
                seat_snapshot["submitted"] = rd.plain(copies)
        entry["submitted"] = submitted
        entry["s17"] = rows
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
