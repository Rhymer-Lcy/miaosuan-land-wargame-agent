"""Play one registered game and return its private record.

The engine class and the agent factories are passed in, so this module never imports the SDK
and can be tested against a stand-in engine. Every state passes through the boundary. Durations
use ``time.perf_counter`` (monotonic); nothing here reads the wall clock or a random source.

The record is private: it holds per-step digests, raw latencies and feedback details that refer
to scenario content. :mod:`.metrics` derives the sanitized public summary from it.

Alignment: ``state_steps[k]`` digests the all-seeing state that decision ``k`` observed (index 0
is the setup state), and each seat's ``trace_steps[k]`` digests decision ``k``.
"""

from __future__ import annotations

import hashlib
import re
import time
import traceback
from collections import Counter
from typing import Any, Callable, Collection, Dict, List, Mapping, Optional, Sequence

from ..boundary import ContractError, Origin, Stage, StateView, normalize_state
from ..decision import BASELINE_ID, digest
from . import effects
from .canonical import value_digest
from .manifest import REPLAY_CHECK_EVERY, WALL_CAP_SECONDS, GameSpec

SCHEMA = "miaosuan-game-record/1"
PREFIX = 16  # hex characters kept per step digest (64 bits): enough to locate a divergence
EXAMPLES_PER_CODE = 5  # private examples kept per engine error code and seat


def sanitize(reason: str) -> str:
    """A reason with every number replaced, so it can be counted publicly without scenario content."""
    return re.sub(r"-?\d+(?:\.\d+)?", "N", reason)


class SeatLog:
    """Per-seat accumulators for one game."""

    def __init__(self, seat: int, faction: int, policy: str) -> None:
        self.seat, self.faction, self.policy = seat, faction, policy
        self.latency_us: List[int] = []
        self.trace_chain = hashlib.sha256()
        self.trace_steps: List[str] = []
        self.actions: Counter = Counter()
        self.steps_with_action = 0
        self.first_step: Dict[int, int] = {}
        self.units_seen: set = set()
        self.units_acted: set = set()
        self.no_op: Counter = Counter()
        self.rejections: Counter = Counter()
        self.contract_errors = 0
        self.diagnostics = 0
        self.replay_checks = 0
        self.replay_mismatches = 0
        self.effects: Dict[int, Counter] = {}
        self.feedback_entries = 0
        self.feedback_errors: Counter = Counter()
        self.feedback_errors_by_type: Counter = Counter()
        self.feedback_error_examples: Dict[str, List[Dict[str, Any]]] = {}
        self.refusal_contexts: Counter = Counter()
        self.suppressions = 0
        self.steps_with_suppression = 0
        self.duplicate_occupation_steps = 0
        self.duplicate_occupation_commands = 0

    def record(self, step: int, trace, produced: Sequence[Mapping[str, Any]], latency: float) -> None:
        self.latency_us.append(round(latency * 1e6))
        trace_digest = digest(trace)
        self.trace_chain.update(trace_digest.encode("ascii"))
        self.trace_steps.append(trace_digest[:PREFIX])
        if trace.error is not None:
            self.contract_errors += 1
        suppressed = getattr(trace, "suppressed", ())
        self.suppressions += len(suppressed)
        self.steps_with_suppression += bool(suppressed)
        self.diagnostics += len(trace.diagnostics)
        for _, _, reason in trace.rejected:
            self.rejections[sanitize(reason)] += 1
        for unit in trace.units:
            self.units_seen.add(unit.obj_id)
            if unit.no_op_reason is not None:
                self.no_op[sanitize(unit.no_op_reason)] += 1
        if produced:
            self.steps_with_action += 1
        for action in produced:
            kind = int(action["type"])
            self.actions[kind] += 1
            self.first_step.setdefault(kind, step)
            if "obj_id" in action:
                self.units_acted.add(action["obj_id"])

    def feedback_error(self, code: Any, entry: Mapping[str, Any], step: int) -> None:
        """Count an engine-reported error by code and by action type; keep a few private examples."""
        message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
        error = entry.get("error") if isinstance(entry.get("error"), Mapping) else {}
        self.feedback_errors[code] += 1
        self.feedback_errors_by_type[f"{code}/{message.get('type')}"] += 1
        examples = self.feedback_error_examples.setdefault(str(code), [])
        if len(examples) < EXAMPLES_PER_CODE:
            examples.append({"step": step, "action": dict(message),
                             "error_message": str(error.get("message"))[:200]})

    def effect(self, kind: int, outcome: str) -> None:
        self.effects.setdefault(kind, Counter())[outcome] += 1

    def summary(self) -> Dict[str, Any]:
        return {
            "seat": self.seat, "faction": self.faction, "policy": self.policy,
            "decisions": len(self.latency_us), "latency_us": self.latency_us,
            "trace_chain": self.trace_chain.hexdigest(), "trace_steps": self.trace_steps,
            "actions_by_type": {str(k): v for k, v in sorted(self.actions.items())},
            "steps_with_action": self.steps_with_action,
            "first_step_by_type": {str(k): v for k, v in sorted(self.first_step.items())},
            "units_seen": len(self.units_seen), "units_acted": len(self.units_acted),
            "no_op_reasons": dict(sorted(self.no_op.items())),
            "gate_rejections": dict(sorted(self.rejections.items())),
            "contract_errors": self.contract_errors, "diagnostics": self.diagnostics,
            "replay_checks": self.replay_checks, "replay_mismatches": self.replay_mismatches,
            "effects_by_type": {str(k): dict(sorted(v.items())) for k, v in sorted(self.effects.items())},
            "feedback_entries": self.feedback_entries,
            "feedback_errors_by_code": {str(k): v for k, v in sorted(self.feedback_errors.items(), key=str)},
            "feedback_errors_by_code_and_type": dict(sorted(self.feedback_errors_by_type.items())),
            "feedback_error_examples": self.feedback_error_examples,
            "refusal_contexts": dict(sorted(self.refusal_contexts.items())),
            "suppressions": self.suppressions, "steps_with_suppression": self.steps_with_suppression,
            "duplicate_occupation_steps": self.duplicate_occupation_steps,
            "duplicate_occupation_commands": self.duplicate_occupation_commands,
        }


def play(train_env_cls: Callable[[], Any], agent_factories: Mapping[str, Callable[[], Any]], spec: GameSpec,
         inputs: Any, players: Sequence[Mapping[str, Any]], rng_probe: Optional[Callable[[], Dict[str, str]]] = None,
         wall_cap: float = WALL_CAP_SECONDS, clock: Callable[[], float] = time.perf_counter,
         replay_policies: Collection[str] = frozenset({BASELINE_ID})) -> Dict[str, Any]:
    """Run ``spec`` to the engine's done flag or a cap. Never raises; failures are recorded.

    Seats playing a policy in ``replay_policies`` (the policy under test) get in-game replay checks.
    """
    policies = {0: spec.red, 1: spec.blue}
    record: Dict[str, Any] = {"schema": SCHEMA, "game_id": spec.game_id, "scenario_id": spec.scenario_id,
                              "map_id": spec.map_id, "condition": spec.condition, "repetition": spec.repetition,
                              "policies": {"red": spec.red, "blue": spec.blue}, "step_cap": spec.step_cap,
                              "wall_cap_seconds": wall_cap, "status": "FAIL", "phase": "construct",
                              "failure": None, "rng_probe": {}}
    probe = (lambda point: record["rng_probe"].__setitem__(point, rng_probe())) if rng_probe else (lambda point: None)
    timings = {"engine_step": 0.0, "decisions": 0.0}
    logs: List[SeatLog] = []
    state_chain = hashlib.sha256()
    state_steps: List[str] = []
    started = clock()
    probe("before-construct")

    def fail(origin: str, exc: BaseException) -> Dict[str, Any]:
        record["failure"] = {"origin": origin, "phase": record["phase"], "type": type(exc).__name__,
                             "message": str(exc)[:500], "traceback": traceback.format_exc()[-4000:]}
        return finish()

    def finish() -> Dict[str, Any]:
        wall = clock() - started
        record["timings_seconds"] = {"wall": wall, "engine_step": timings["engine_step"],
                                     "decisions": timings["decisions"],
                                     "harness": wall - timings["engine_step"] - timings["decisions"]}
        record["seats"] = [log.summary() for log in logs]
        record["state_chain"] = state_chain.hexdigest()
        record["state_steps"] = state_steps
        return record

    try:
        env = train_env_cls()
    except Exception as exc:  # noqa: BLE001 - every engine failure is recorded
        return fail("engine", exc)
    probe("after-construct")
    record["phase"] = "setup"
    try:
        state = env.setup({"scenario_data": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                           "see_data": inputs.see, "player_info": [dict(p) for p in players]})
    except Exception as exc:  # noqa: BLE001
        return fail("engine-setup", exc)
    probe("after-setup")
    try:
        view = normalize_state(state, Origin.ENGINE)
        setup_digest = value_digest(dict(view.global_observation.fields))
    except ContractError as exc:
        return fail("contract", exc)
    state_chain.update(setup_digest.encode("ascii"))
    state_steps.append(setup_digest[:PREFIX])

    record["phase"] = "agents"
    agents = []
    try:
        for player in players:
            agent = agent_factories[policies[player["faction"]]]()
            agent.setup({"scenario": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                         "see_data": inputs.see, "seat": player["seat"], "faction": player["faction"],
                         "role": player["role"], "user_name": player["user_name"], "user_id": player["user_id"],
                         "state": state})
            agents.append(agent)
            logs.append(SeatLog(player["seat"], player["faction"], policies[player["faction"]]))
    except Exception as exc:  # noqa: BLE001
        return fail("agent-setup", exc)

    record["phase"] = "play"
    seats = {log.seat: log for log in logs}
    stages = [{"step": 0, "stage": view.global_observation.time().stage}]
    steps, done = 0, False
    while steps < spec.step_cap and clock() - started < wall_cap:
        before: StateView = view
        emitted = []
        for player, agent, log in zip(players, agents, logs):
            observation = before.for_faction(player["faction"]).fields
            memory = agent.memory
            try:
                tick = clock()
                produced = agent.step(observation)
                elapsed = clock() - tick
            except Exception as exc:  # noqa: BLE001
                record["steps"] = steps
                return fail(f"agent-{player['faction']}", exc)
            timings["decisions"] += elapsed
            log.record(steps, agent.last_trace, produced, elapsed)
            if log.policy in replay_policies and steps % REPLAY_CHECK_EVERY == 0:
                log.replay_checks += 1
                if digest(agent.replay(observation, memory)) != digest(agent.last_trace):
                    log.replay_mismatches += 1
            emitted.extend((log, action) for action in produced)
        start_hexes = {unit.obj_id: unit.cur_hex for unit in before.global_observation.operators()}
        start_flags = {city.coord: city.flag for city in (before.global_observation.cities() or ())}
        for log in logs:
            per_objective = Counter(start_hexes.get(a.get("obj_id")) for owner, a in emitted
                                    if owner is log and a.get("type") == 5)
            extra = sum(count - 1 for count in per_objective.values() if count > 1)
            log.duplicate_occupation_steps += bool(extra)
            log.duplicate_occupation_commands += extra
        try:
            tick = clock()
            result = env.step([action for _, action in emitted])
            timings["engine_step"] += clock() - tick
            if not (isinstance(result, tuple) and len(result) == 2):
                raise TypeError(f"env.step returned {type(result).__name__}, expected (state, done)")
            state, done = result
        except Exception as exc:  # noqa: BLE001
            record["steps"] = steps
            return fail("engine-step", exc)
        steps += 1
        if steps == 1:
            probe("after-first-step")
        try:
            view = normalize_state(state, Origin.ENGINE)
            everything = view.global_observation
            step_digest = value_digest(dict(everything.fields))
            state_chain.update(step_digest.encode("ascii"))
            state_steps.append(step_digest[:PREFIX])
            stage = everything.time().stage
            if stage != stages[-1]["stage"]:
                stages.append({"step": steps, "stage": stage})
            for entry in everything.action_feedback() or ():
                actor = effects.feedback_actor(entry)
                if actor in seats:
                    seats[actor].feedback_entries += 1
                    code = effects.feedback_error_code(entry)
                    if code is not None:
                        seats[actor].feedback_error(code, entry, steps)
                        own = [a for owner, a in emitted if owner.seat == actor]
                        seats[actor].refusal_contexts[effects.refusal_context(
                            entry, code, seats[actor].faction, start_hexes, start_flags, own)] += 1
            decision_step = before.global_observation.time().cur_step
            for log, action in emitted:
                outcome = effects.classify(action, log.faction, before.global_observation, everything, decision_step)
                log.effect(int(action["type"]), outcome)
        except ContractError as exc:
            record["steps"] = steps
            return fail("contract", exc)
        if done:
            break
    probe("end")

    record["phase"] = "reset"
    final = view.global_observation
    record.update(steps=steps, done=bool(done), stage_transitions=stages,
                  completion="done" if done else "step_cap" if steps >= spec.step_cap else "wall_cap",
                  final_time={"cur_step": final.time().cur_step, "stage": final.time().stage,
                              "max_time": final.time().max_time},
                  final_scores=dict(final.fields.get("scores") or {}),
                  deployment_ended=any(t["stage"] == Stage.PLAY for t in stages))
    try:
        env.reset()
        for agent in agents:
            agent.reset()
    except Exception as exc:  # noqa: BLE001
        return fail("reset", exc)
    record["phase"] = "finished"
    record["status"] = "COMPLETED" if done else "CAPPED"
    return finish()
