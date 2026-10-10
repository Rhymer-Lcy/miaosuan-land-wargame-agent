"""Read-only full-step observer of the Sprint 33 live stop mechanism check (``docs/SPRINT33_T7_B1_LIVE.md``).

Each game runs two observers together through Sprint 9's ``Tee``: the exploratory capture
(``evaluation.exploratory.ExploreCapture``, unchanged) and :class:`StopTimeline`. Nothing an observer computes reaches a
policy or the engine (``evaluation.game.play``).

:class:`StopTimeline` is Sprint 31's full-step timeline (``evaluation.s31_capture.K2Timeline``) adapted to the stop
candidate ``t7-b1-stop-engage-1``. It keeps, for every step, the all-seeing state, the policy seats' observations,
memories, actions and pre-execution copies, the engine's feedback and the new judge records, and the post-step state of
the last step. At every decision of the candidate's seat it re-decides from that seat's own observation and memory only:
``baseline-v2``'s actions, trace digest and next memory from a fresh instance, then the frozen rule
(``t7_b1_stop_engage.decide``) on those actions and the add-on memory the seat carried in. It records a finding when:

* the live decision differs from the reconstruction (emitted actions, change records, skip counts, ``baseline-v2``'s
  trace digest, an add-on error, the policy or add-on name);
* a memory chain breaks (the ``baseline-v2`` memory or the add-on memory the seat carries into a decision is not the
  reconstruction's memory after the previous decision, or not empty before the first);
* the live actions are not ``baseline-v2``'s list, unchanged and in order, followed by exactly the rule's stops in the
  documented key set ``actor``, ``obj_id``, ``type`` (:func:`appended_only`);
* a unit is stopped a second time in the game;
* Sprint 32's independent restatement of the trigger (``s32_preflight.independent_triggers``) selects other units.

Raw identifiers stay in its files, which are written only under the ignored ``local/``.
"""

from __future__ import annotations

import hashlib
import pickle
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import Memory, digest
from ..decision.trace import canonical_json
from ..experiments import t7_b1_stop_engage as cand
from ..experiments.exploratory_addon import AddonMemory
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import residual516 as rd
from .s12_screen import V2_ID
from .s32_preflight import independent_triggers

TIMELINE_SCHEMA = "miaosuan-s33-timeline-capture/1"
CANDIDATE_ID = cand.CANDIDATE_ID


def split_memory(memory: Any) -> Tuple[Any, Tuple[Tuple[int, int], ...]]:
    if isinstance(memory, AddonMemory):
        return memory.baseline, tuple(tuple(p) for p in memory.addon)
    return memory, ()


def reconstruct(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts) -> Dict[str, Any]:
    """Seat-local reconstruction of one candidate decision from the seat's observation and memory."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory, addon_memory = split_memory(memory)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, base_memory)
    result = cand.decide(raw, seat, faction, tuple(base.actions), addon_memory)
    cand.own_check(result, raw, seat, tuple(base.actions))
    return {"baseline_actions": rd.plain(base.actions), "baseline_trace_sha256": digest(base.trace),
            "baseline_memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY,
            "actions": rd.plain(result.actions), "stops": list(result.stops),
            "changes": tuple(canonical_json(dict(c)) for c in cand.change_records(result)),
            "skipped": cand.skip_counts(result), "memory_in": addon_memory, "memory_out": tuple(result.memory)}


def reconstruct_v2(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts) -> Dict[str, Any]:
    """Seat-local reconstruction of one ``baseline-v2`` decision (used only if a ``baseline-v2`` seat is played)."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, memory)
    return {"baseline_actions": rd.plain(base.actions), "trace_sha256": digest(base.trace),
            "memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY}


def consistency(decision: Mapping[str, Any], rebuilt: Mapping[str, Any], expected_memory: Any,
                expected_addon: Tuple[Tuple[int, int], ...]) -> Dict[str, bool]:
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
            "addon_memory": addon_memory == tuple(expected_addon)}


def consistency_v2(decision: Mapping[str, Any], rebuilt: Mapping[str, Any], expected_memory: Any) -> Dict[str, bool]:
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["baseline_actions"],
            "trace": digest(decision["trace"]) == rebuilt["trace_sha256"],
            "policy": decision["policy"] == V2_ID,
            "memory": decision["memory"] == expected_memory}


def appended_only(base: Sequence[Mapping[str, Any]], live: Sequence[Mapping[str, Any]], stops: Sequence[int],
                  seat: int) -> List[str]:
    """Why ``live`` is not ``baseline-v2``'s list ``base`` (unchanged, in order) followed by exactly one documented stop
    per unit of ``stops``, in that order; [] when it is."""
    live, base = [dict(a) for a in live], [dict(a) for a in base]
    problems = []
    if live[:len(base)] != base:
        problems.append("a baseline-v2 action was changed, removed or reordered")
    expected = [{"actor": seat, "obj_id": unit, "type": cand.STOP} for unit in stops]
    if live[len(base):] != expected:
        problems.append("the added actions are not exactly the rule's documented stops")
    return problems


def repeated(emitted: Sequence[int], stopped_before: set) -> List[int]:
    """The units of ``emitted`` (this decision's stops) stopped earlier in the game or twice in this decision."""
    return sorted(set(emitted) & set(stopped_before)) + sorted({u for u in emitted if list(emitted).count(u) > 1})


class StopTimeline(rd.Capture):
    """Full-step private timeline with the seat-local reconstruction of every decision of the policy seats."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=1, clock=clock)
        self.costs = costs
        self.consistency_errors: List[Dict[str, Any]] = []
        self.unregistered: List[Dict[str, Any]] = []
        self.independent: List[Dict[str, Any]] = []
        self.repeated: List[Dict[str, Any]] = []
        self.reconstructed = 0
        self.policy_decisions = 0
        self.stops_emitted = 0
        self._expected: Dict[int, Any] = {}
        self._expected_addon: Dict[int, Tuple[Tuple[int, int], ...]] = {}
        self._expected_v2: Dict[int, Any] = {}
        self._stopped: Dict[int, set] = {}
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
                                      self.costs)
                checks = consistency(decision, rebuilt, self._expected.get(seat, Memory()),
                                     self._expected_addon.get(seat, ()))
                self._expected[seat] = rebuilt["baseline_memory_out"]
                self._expected_addon[seat] = rebuilt["memory_out"]
                differences = appended_only(rebuilt["baseline_actions"], rd.plain(copies), rebuilt["stops"], seat)
                stopped = {pair[0] for pair in rebuilt["memory_in"]}
                restated = independent_triggers(decision["observation"], seat, decision["faction"],
                                                rebuilt["baseline_actions"], stopped)
                independent = [] if restated == set(rebuilt["stops"]) else \
                    [f"the restatement selects {len(restated)} units, the rule {len(rebuilt['stops'])}"]
                emitted = [a["obj_id"] for a in rd.plain(copies) if a.get("type") == cand.STOP]
                self.stops_emitted += len(emitted)
                seen = self._stopped.setdefault(seat, set())
                again = repeated(emitted, seen)
                seen.update(emitted)
                rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                                   "baseline_actions": rebuilt["baseline_actions"],
                                   "baseline_trace_sha256": rebuilt["baseline_trace_sha256"],
                                   "cur_step": rebuilt["cur_step"], "max_step": rebuilt["max_step"],
                                   "play": rebuilt["play"], "stops": rebuilt["stops"],
                                   "changes": list(rebuilt["changes"]), "skipped": [list(p) for p in rebuilt["skipped"]],
                                   "unregistered_differences": differences, "independent_problems": independent}
                if independent:
                    self.independent.append({"k": index, "seat": seat, "problems": independent})
                if again:
                    self.repeated.append({"k": index, "seat": seat, "units": len(again)})
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
        entry["s33"] = rows
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
        out["repeated_stops"] = self.repeated
        out["reconstructed_decisions"] = self.reconstructed
        out["policy_decisions"] = self.policy_decisions
        out["stops_emitted"] = self.stops_emitted
        return out

    def windows(self) -> Dict[str, Any]:
        out = super().windows()
        out["final"] = self._final()
        return out

    def summary(self, compact: bytes, windows: bytes) -> Dict[str, Any]:
        return {"schema": TIMELINE_SCHEMA, "steps": len(self.steps), "full_step_snapshots": len(self.samples),
                "reconstructed_decisions": self.reconstructed, "consistency_errors": len(self.consistency_errors),
                "unregistered_differences": len(self.unregistered), "independent_problems": len(self.independent),
                "repeated_stops": len(self.repeated), "stops_emitted": self.stops_emitted,
                "observer_seconds": self.seconds, "compact_sha256": hashlib.sha256(compact).hexdigest(),
                "windows_sha256": hashlib.sha256(windows).hexdigest()}
