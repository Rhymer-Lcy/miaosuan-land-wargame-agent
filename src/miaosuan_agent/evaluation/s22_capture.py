"""Read-only full-step observer of the Sprint 22 probe (``docs/SPRINT22_T2_TRANSPORT_PROBE.md``).

The probe game runs three observers together through Sprint 9's ``Tee``: Sprint 9's ``T9Capture`` unchanged, the
exploratory capture (``evaluation.exploratory.ExploreCapture``, unchanged) and :class:`TransportTimeline`. Nothing an
observer computes reaches a policy or the engine (``evaluation.game.play``).

:class:`TransportTimeline` is Sprint 17's full-step timeline adapted to the transport candidate: it keeps, for every
step, the all-seeing state and every policy seat's observation, memory, actions and pre-execution copies, the engine's
feedback, units boarded and landed, and the post-step state of the last step. At every decision of the candidate's seat
it re-decides from that seat's own observation and memory only: ``baseline-v2``'s actions, trace digest and next memory,
and the candidate's edit (``t2_transport_p1.step``: actions, change records, next memory, state). It compares the
reconstruction with the live decision (emitted actions, change records, the state recorded as the skip reason,
``baseline-v2``'s trace digest, no add-on error, the policy and add-on names), checks the memory chain (the memory the
seat carries into a decision equals the reconstruction's memory after the previous decision, and is empty before the
first), and checks that every difference between the live actions and ``baseline-v2``'s is a registered transport edit
(``s22_probe.unregistered_differences``). Every finding is recorded. Raw identifiers stay in its files, which are written
only under the ignored ``local/``.
"""

from __future__ import annotations

import hashlib
import pickle
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Origin, Stage
from ..decision import Memory, digest
from ..decision.trace import canonical_json
from ..experiments import t2_transport_p1 as t2
from ..experiments.exploratory_addon import AddonMemory
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import residual516 as rd
from . import s22_probe as sp

TIMELINE_SCHEMA = "miaosuan-s22-timeline-capture/1"
CANDIDATE_ID = t2.CANDIDATE_ID


def split_memory(memory: Any) -> Tuple[Any, Tuple[Tuple[int, int], ...]]:
    if isinstance(memory, AddonMemory):
        return memory.baseline, tuple(tuple(p) for p in memory.addon)
    return memory, ()


def state_name(addon_memory: Sequence[Sequence[int]]) -> str:
    record = t2.decode(addon_memory)
    if record is None:
        return "UNINTERPRETABLE"
    return t2.STATES[record.get(t2.F_STATE, t2.READY)]


def pair_of(addon_memory: Sequence[Sequence[int]]) -> Optional[Tuple[int, int]]:
    record = t2.decode(addon_memory)
    if not record or record.get(t2.F_INF, -1) < 0:
        return None
    return record[t2.F_INF], record[t2.F_CAR]


def reconstruct(raw: Mapping[str, Any], seat: int, faction: int, memory: Any, costs: MoveCosts) -> Dict[str, Any]:
    """Seat-local reconstruction of one candidate decision from the seat's observation and memory."""
    observation = Observation.from_raw(raw, Origin.ENGINE)
    base_memory, addon_memory = split_memory(memory)
    base = ShootReservationPolicy(costs).decide(observation, seat, faction, base_memory)
    actions, changes, memory_out, state = t2.step(observation, seat, faction, tuple(base.actions), addon_memory)
    return {"baseline_actions": rd.plain(base.actions), "baseline_trace_sha256": digest(base.trace),
            "baseline_memory_out": base.memory, "cur_step": observation.time().cur_step,
            "max_step": observation.time().max_step, "play": observation.time().stage == Stage.PLAY,
            "actions": rd.plain(actions), "changes": tuple(canonical_json(dict(c)) for c in changes),
            "skipped": ((f"state {state}", 1),), "memory_in": addon_memory, "memory_out": tuple(memory_out),
            "state_before": state_name(addon_memory), "state_after": state,
            "pair": pair_of(memory_out) or pair_of(addon_memory)}


def consistency(decision: Mapping[str, Any], rebuilt: Mapping[str, Any],
                expected_memory: Tuple[Any, Tuple[Tuple[int, int], ...]]) -> Dict[str, bool]:
    trace = decision["trace"]
    base_memory, addon_memory = split_memory(decision["memory"])
    return {"actions": rd.plain(decision["submitted"]) == rebuilt["actions"],
            "changes": tuple(getattr(trace, "changes", ())) == tuple(rebuilt["changes"]),
            "skipped": tuple(getattr(trace, "skipped", ())) == tuple(rebuilt["skipped"]),
            "baseline_trace": getattr(trace, "baseline_trace_sha256", None) == rebuilt["baseline_trace_sha256"],
            "addon_error": getattr(trace, "addon_error", None) is None,
            "addon_name": getattr(trace, "addon_name", None) == t2.ADDON_NAME,
            "policy": getattr(trace, "policy", None) == CANDIDATE_ID,
            "baseline_memory": base_memory == expected_memory[0],
            "addon_memory": addon_memory == expected_memory[1]}


def actions_digest(actions: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json([{str(k): v for k, v in dict(a).items()} for a in actions]).encode("utf-8")
                          ).hexdigest()


def prefix_inputs(timeline: Mapping[str, Any], seat: int, trigger_decision: int) -> Dict[str, Any]:
    """What the prefix check reads from one game: digests of the live and the reconstructed baseline-v2 actions per
    decision, the live actions' digest at the registered trigger decision, and the pair the candidate recorded there."""
    steps = timeline.get("steps") or []
    live, baseline = [], []
    for step in steps:
        row = (step.get("s22") or {}).get(str(seat)) or {}
        live.append(actions_digest([a["action"] for a in step.get("submitted") or () if a["seat"] == seat]))
        baseline.append(actions_digest(row.get("baseline_actions") or []))
    trigger_actions = live[trigger_decision] if trigger_decision < len(live) else None
    pair = None
    if trigger_decision < len(steps):
        pair = ((steps[trigger_decision].get("s22") or {}).get(str(seat)) or {}).get("pair")
    return {"live": live, "baseline": baseline, "trigger_actions": trigger_actions, "pair": pair}


class TransportTimeline(rd.Capture):
    """Full-step private timeline with the seat-local reconstruction of every candidate decision."""

    def __init__(self, policies: Sequence[str], costs: MoveCosts, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__(policies, sample_every=1, clock=clock)
        self.costs = costs
        self.consistency_errors: List[Dict[str, Any]] = []
        self.unregistered: List[Dict[str, Any]] = []
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
            differences = sp.unregistered_differences(rebuilt["baseline_actions"], rd.plain(copies),
                                                      rebuilt["state_before"], rebuilt["state_after"],
                                                      rebuilt["pair"])
            rows[str(seat)] = {"policy": decision["policy"], "consistency": checks,
                               "baseline_actions": rebuilt["baseline_actions"],
                               "baseline_trace_sha256": rebuilt["baseline_trace_sha256"],
                               "cur_step": rebuilt["cur_step"], "max_step": rebuilt["max_step"],
                               "play": rebuilt["play"], "changes": list(rebuilt["changes"]),
                               "state_before": rebuilt["state_before"], "state_after": rebuilt["state_after"],
                               "pair": list(rebuilt["pair"]) if rebuilt["pair"] else None,
                               "memory_in": [list(p) for p in rebuilt["memory_in"]],
                               "memory_out": [list(p) for p in rebuilt["memory_out"]],
                               "unregistered_differences": differences}
            if not all(checks.values()):
                self.consistency_errors.append({"k": index, "seat": seat, **checks})
            if differences:
                self.unregistered.append({"k": index, "seat": seat, "problems": differences})
            seat_snapshot = self.ring[-1]["seats"].get(seat)
            if seat_snapshot is not None:
                seat_snapshot["submitted"] = rd.plain(copies)
        entry["submitted"] = submitted
        entry["s22"] = rows
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
