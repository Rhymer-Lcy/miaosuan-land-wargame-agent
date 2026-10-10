"""Read-only full-step observer of the Sprint 31 pilot (``docs/SPRINT31_T13_K2_PILOT.md``).

Each pilot game runs two observers together through Sprint 9's ``Tee``: the exploratory capture
(``evaluation.exploratory.ExploreCapture``, unchanged) and :class:`K2Timeline`. Nothing an observer computes reaches a
policy or the engine (``evaluation.game.play``).

:class:`K2Timeline` is Sprint 27's full-step timeline adapted to the keep-one candidate. It keeps, for every step, the
all-seeing state and the observations, memories, actions and pre-execution copies of the seats played by
``baseline-v2`` or the candidate (the inert seat is not a policy seat), the engine's feedback, and the post-step state
of the last step. At every decision it re-decides from that seat's own observation and memory only:

* the candidate's seat: ``baseline-v2``'s actions, trace digest and next memory from a fresh instance, then the
  registered rule on those actions (``t13_keep_one_k2.apply_rule`` over the setup cost data); it compares the
  reconstruction with the live decision (emitted actions, change records, skip counts, ``baseline-v2``'s trace digest,
  no add-on error, the policy and add-on names, an empty add-on memory), checks the memory chain (the memory the seat
  carries into a decision equals the reconstruction's memory after the previous decision, and is empty before the
  first), checks that every difference between the live actions and ``baseline-v2``'s is a registered withholding
  (``s27_probe.unregistered_differences``: ``baseline-v2``'s list with exactly the withheld MOVEs removed, in order),
  and runs the K2 preflight's independent restatement of the rule (``s31_preflight.independent_problems``);
* the ``baseline-v2`` seat: its actions, trace digest and memory chain.

Every finding is recorded. Raw identifiers stay in its files, which are written only under the ignored ``local/``.
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
from ..experiments import t13_keep_one_k2 as cand
from ..experiments.exploratory_addon import AddonMemory
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import residual516 as rd
from .s27_probe import unregistered_differences
from .s31_preflight import independent_problems
from .s12_screen import V2_ID

TIMELINE_SCHEMA = "miaosuan-s31-timeline-capture/1"
CANDIDATE_ID = cand.CANDIDATE_ID


def split_memory(memory: Any) -> Tuple[Any, Tuple[Tuple[int, int], ...]]:
    if isinstance(memory, AddonMemory):
        return memory.baseline, tuple(tuple(p) for p in memory.addon)
    return memory, ()


def check_rows(result: cand.K2Result) -> List[List[Any]]:
    """The rule's objective checks as plain rows (centre, status, selected unit, index, travel, occupants with their
    level)."""
    return [[c.centre, c.status, c.selected, c.index, c.travel, [[o.unit, o.level] for o in c.occupants]]
            for c in result.checks]


def reconstruct(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts,
                travel: Optional[cand.Travel] = None) -> Dict[str, Any]:
    """Seat-local reconstruction of one candidate decision from the seat's observation and memory."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory, addon_memory = split_memory(memory)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, base_memory)
    travel = travel or cand.router_travel(Router(costs))
    result = cand.apply_rule(raw, faction, tuple(base.actions), travel)
    return {"baseline_actions": rd.plain(base.actions), "baseline_trace_sha256": digest(base.trace),
            "baseline_memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY,
            "actions": rd.plain(result.actions), "withheld": list(result.withheld),
            "changes": tuple(canonical_json(dict(c)) for c in cand.change_records(result)),
            "skipped": cand.skip_counts(result), "memory_in": addon_memory, "checks": check_rows(result)}


def reconstruct_v2(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts) -> Dict[str, Any]:
    """Seat-local reconstruction of one ``baseline-v2`` decision."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, memory)
    return {"baseline_actions": rd.plain(base.actions), "trace_sha256": digest(base.trace),
            "memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY}


def consistency(decision: Mapping[str, Any], rebuilt: Mapping[str, Any], expected_memory: Any) -> Dict[str, bool]:
    trace = decision["trace"]
    base_memory, addon_memory = split_memory(decision["memory"])
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["actions"],
            "changes": tuple(getattr(trace, "changes", ())) == tuple(rebuilt["changes"]),
            "skipped": tuple(getattr(trace, "skipped", ())) == tuple(rebuilt["skipped"]),
            "baseline_trace": getattr(trace, "baseline_trace_sha256", None) == rebuilt["baseline_trace_sha256"],
            "addon_error": getattr(trace, "addon_error", None) is None,
            "addon_name": getattr(trace, "addon_name", None) == cand.ADDON_NAME,
            "policy": getattr(trace, "policy", None) == CANDIDATE_ID,
            "baseline_memory": base_memory == expected_memory,
            "addon_memory": addon_memory == ()}


def consistency_v2(decision: Mapping[str, Any], rebuilt: Mapping[str, Any], expected_memory: Any) -> Dict[str, bool]:
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["baseline_actions"],
            "trace": digest(decision["trace"]) == rebuilt["trace_sha256"],
            "policy": decision["policy"] == V2_ID,
            "memory": decision["memory"] == expected_memory}


class K2Timeline(rd.Capture):
    """Full-step private timeline with the seat-local reconstruction of every decision of the policy seats."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=1, clock=clock)
        self.costs = costs
        self.travel = cand.router_travel(Router(costs))
        self.consistency_errors: List[Dict[str, Any]] = []
        self.unregistered: List[Dict[str, Any]] = []
        self.independent: List[Dict[str, Any]] = []
        self.reconstructed = 0
        self.policy_decisions = 0
        self._expected: Dict[int, Any] = {}
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
            if decision["policy"] not in (CANDIDATE_ID, V2_ID):
                continue
            self.policy_decisions += 1
            if decision["policy"] == CANDIDATE_ID:
                rebuilt = reconstruct(decision["observation"], seat, decision["faction"], decision["memory"],
                                      self.costs, self.travel)
                checks = consistency(decision, rebuilt, self._expected.get(seat, Memory()))
                self._expected[seat] = rebuilt["baseline_memory_out"]
                differences = unregistered_differences(rebuilt["baseline_actions"], rd.plain(copies),
                                                       rebuilt["withheld"])
                independent = independent_problems(decision["observation"], decision["faction"],
                                                   rebuilt["baseline_actions"], rd.plain(copies), self.costs)
                rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                                   "baseline_actions": rebuilt["baseline_actions"],
                                   "baseline_trace_sha256": rebuilt["baseline_trace_sha256"],
                                   "cur_step": rebuilt["cur_step"], "max_step": rebuilt["max_step"],
                                   "play": rebuilt["play"], "changes": list(rebuilt["changes"]),
                                   "withheld": rebuilt["withheld"], "checks": rebuilt["checks"],
                                   "unregistered_differences": differences, "independent_problems": independent}
                if independent:
                    self.independent.append({"k": index, "seat": seat, "problems": independent})
            else:
                rebuilt = reconstruct_v2(decision["observation"], seat, decision["faction"], decision["memory"],
                                         self.costs)
                checks = consistency_v2(decision, rebuilt, self._expected_v2.get(seat, Memory()))
                self._expected_v2[seat] = rebuilt["memory_out"]
                differences = []
                rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                                   "baseline_actions": rebuilt["baseline_actions"],
                                   "trace_sha256": rebuilt["trace_sha256"], "cur_step": rebuilt["cur_step"],
                                   "max_step": rebuilt["max_step"], "play": rebuilt["play"]}
            self.reconstructed += 1
            if not all(checks.values()):
                self.consistency_errors.append({"k": index, "seat": seat, **checks})
            if differences:
                self.unregistered.append({"k": index, "seat": seat, "problems": differences})
            seat_snapshot = self.ring[-1]["seats"].get(seat)
            if seat_snapshot is not None:
                seat_snapshot["submitted"] = rd.plain(copies)
        entry["submitted"] = submitted
        entry["s31"] = rows
        if index == 0 or (self.events and self.events[-1]["k"] == index):
            self.samples.append(self.ring[-1])
        self._after, self._seats, self._last = after, [(d["seat"], d["faction"]) for d in decisions
                                                       if d["policy"] in self.policies], index
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
        out["independent_problems"] = self.independent
        out["reconstructed_decisions"] = self.reconstructed
        out["policy_decisions"] = self.policy_decisions
        return out

    def windows(self) -> Dict[str, Any]:
        out = super().windows()
        out["final"] = self._final()
        return out

    def summary(self, compact: bytes, windows: bytes) -> Dict[str, Any]:
        return {"schema": TIMELINE_SCHEMA, "steps": len(self.steps), "full_step_snapshots": len(self.samples),
                "reconstructed_decisions": self.reconstructed, "consistency_errors": len(self.consistency_errors),
                "unregistered_differences": len(self.unregistered), "independent_problems": len(self.independent),
                "observer_seconds": self.seconds, "compact_sha256": hashlib.sha256(compact).hexdigest(),
                "windows_sha256": hashlib.sha256(windows).hexdigest()}
