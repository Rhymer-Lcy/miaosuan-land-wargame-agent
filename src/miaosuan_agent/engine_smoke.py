"""Drive the SDK engine through one short game, reading every state through the boundary.

The engine class is passed in by the caller, so this module never imports the SDK and can be
tested against a stand-in. Every state the engine returns is normalized and fully validated by
:mod:`miaosuan_agent.boundary` (the accepted contract) and compared with the observed profile
(:mod:`miaosuan_agent.boundary.profile`). Outcomes:

* ``BLOCKED`` - the engine printed an authentication failure; nothing further was attempted;
* ``FAIL``    - an exception or contract violation occurred, or deployment did not observably end;
* ``PASS``    - setup succeeded, every state satisfied the accepted contract, and deployment ended.

Deviations from the observed profile are reported next to the status. They are findings about the
engine or scenario, not failures of the run.

An optional ``capture`` callback receives the raw state at three points: ``setup``,
``after-deployment`` (the first state in the play stage) and ``play-step`` (the state after it).
Durations are measured with ``time.perf_counter``, never with the wall clock.
"""

from __future__ import annotations

import copy
import json
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .boundary import ContractError, Origin, Stage, StateView, normalize_state
from .boundary.profile import PROFILE_ID, check_deployment_transition, check_state, summarize
from .fingerprint import Detail, digest, fingerprint
from .sdk_data import ScenarioInputs

AUTH_FAILURE_MARKERS = ("did not pass authentication", "failed to initialize authenticator")
AUTH_SUCCESS_MARKER = "did pass authentication"
CAPTURE_POINTS = ("setup", "after-deployment", "play-step")
MAX_RECORDED = 20

#: Player list as used by the SDK's single-agent demo runner (the artifact shipped with the engine).
DEFAULT_PLAYERS: Sequence[Mapping[str, Any]] = (
    {"seat": 1, "faction": 0, "role": 1, "user_name": "demo", "user_id": 0},
    {"seat": 11, "faction": 1, "role": 1, "user_name": "demo", "user_id": 0},
)

Capture = Callable[[str, Any], None]


@dataclass(frozen=True)
class SmokeLimits:
    max_steps: int
    max_seconds: float


def _json_default(value: Any) -> Any:
    for attr in ("tolist", "item"):
        if hasattr(value, attr):
            return getattr(value, attr)()
    return repr(value)


def write_json(path: Path, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=_json_default),
                          encoding="utf-8")


def _slot_digests(view: StateView) -> Dict[str, str]:
    return {name: digest(fingerprint(dict(obs.fields), Detail.PUBLIC))
            for name, obs in (("red", view.red), ("blue", view.blue), ("global", view.global_observation))}


def run_smoke(
    train_env_cls: Callable[[], Any],
    agent_factory: Callable[[], Any],
    inputs: ScenarioInputs,
    limits: SmokeLimits,
    evidence_dir: Path,
    captured_output: Callable[[], str],
    players: Sequence[Mapping[str, Any]] = DEFAULT_PLAYERS,
    capture: Optional[Capture] = None,
) -> Dict[str, Any]:
    """Run one controlled game and return the report. Raw red observations go to ``evidence_dir``."""
    evidence_dir = Path(evidence_dir)
    report: Dict[str, Any] = {"scenario_id": inputs.scenario_id, "map_id": inputs.map_id,
                              "limits": {"max_steps": limits.max_steps, "max_seconds": limits.max_seconds},
                              "players": [dict(p) for p in players], "profile_id": PROFILE_ID,
                              "phase": "construct", "status": "FAIL", "reasons": []}
    timings: Dict[str, float] = {}
    report["timings_seconds"] = timings
    deviations: List[Dict[str, Any]] = []
    deviation_count = 0

    def auth_blocked() -> bool:
        text = captured_output()
        report["auth_markers_seen"] = sorted(m for m in AUTH_FAILURE_MARKERS + (AUTH_SUCCESS_MARKER,) if m in text)
        hit = [m for m in AUTH_FAILURE_MARKERS if m in text]
        if hit:
            report["status"] = "BLOCKED"
            report["reasons"].append(f"engine reported authentication failure: {hit}")
            return True
        return False

    def fail(exc: BaseException) -> Dict[str, Any]:
        report["status"] = "FAIL"
        report["reasons"].append(f"{type(exc).__name__} during {report['phase']}: {exc}")
        report["traceback"] = traceback.format_exc()
        report["profile_deviation_count"] = deviation_count
        report["profile_deviations"] = deviations
        auth_blocked()  # an authentication failure explains the exception better than the exception does
        return report

    def profile(step: int, raw_state: Any) -> None:
        nonlocal deviation_count
        found = check_state(raw_state)
        deviation_count += len(found.deviations)
        for item in summarize(found, MAX_RECORDED - len(deviations)):
            deviations.append({"step": step, **item})

    try:
        started = time.perf_counter()
        env = train_env_cls()
        timings["construct"] = time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001 - every engine failure must be reported, not raised
        return fail(exc)
    if auth_blocked():
        return report

    report["phase"] = "setup"
    setup_info = {"scenario_data": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                  "see_data": inputs.see, "player_info": [dict(p) for p in players]}
    try:
        started = time.perf_counter()
        state = env.setup(setup_info)
        timings["setup"] = time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001
        return fail(exc)
    if auth_blocked():
        return report

    report["phase"] = "setup-contract"
    try:
        view = normalize_state(state, Origin.ENGINE)
    except ContractError as exc:
        return fail(exc)
    report["state_form"] = view.form.value
    report["state_container"] = {"type": type(state).__name__,
                                 "keys": [repr(k) for k in state] if isinstance(state, Mapping) else None}
    profile(0, state)
    setup_state, setup_snapshot = state, copy.deepcopy(state)
    report["fingerprints"] = {"setup": _slot_digests(view)}
    report["red_setup_fingerprint"] = fingerprint(dict(view.red.fields), Detail.PUBLIC)
    write_json(evidence_dir / "observation-red-initial.json", dict(view.red.fields))
    try:
        if capture:
            report["phase"] = "capture"
            capture("setup", state)
    except Exception as exc:  # noqa: BLE001
        return fail(exc)

    report["phase"] = "agents"
    agents: List[Any] = []
    try:
        for player in players:
            agent = agent_factory()
            agent.setup({"scenario": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                         "see_data": inputs.see, "seat": player["seat"], "faction": player["faction"],
                         "role": player["role"], "user_name": player["user_name"],
                         "user_id": player["user_id"], "state": state})
            agents.append(agent)
    except Exception as exc:  # noqa: BLE001
        return fail(exc)

    report["phase"] = "step"
    stage_transitions: List[Dict[str, Any]] = [{"step": 0, "stage": view.red.time().stage}]
    issued: List[Dict[str, Any]] = []
    feedback_errors: List[Dict[str, Any]] = []
    captured: List[str] = ["setup"] if capture else []
    done: Any = False
    steps = 0
    loop_started = time.perf_counter()
    try:
        while steps < limits.max_steps and time.perf_counter() - loop_started < limits.max_seconds:
            actions: List[Any] = []
            for player, agent in zip(players, agents):
                produced = agent.step(view.for_faction(player["faction"]).fields)
                if produced:
                    issued.append({"step": steps, "seat": player["seat"], "actions": produced})
                actions.extend(produced)
            result = env.step(actions)
            steps += 1
            if not (isinstance(result, tuple) and len(result) == 2):
                raise TypeError(f"env.step returned {type(result).__name__}, expected a 2-tuple (state, done)")
            previous_state = state
            state, done = result
            if steps == 1:
                report["step_return"] = {"state_type": type(state).__name__, "done_type": type(done).__name__}
                report["state_object_reused_by_step"] = state is previous_state
                report["setup_state_changed_by_first_step"] = setup_state != setup_snapshot
            view = normalize_state(state, Origin.ENGINE)
            profile(steps, state)
            stage = view.red.time().stage
            if stage != stage_transitions[-1]["stage"]:
                stage_transitions.append({"step": steps, "stage": stage})
            for entry in view.global_observation.action_feedback() or ():
                if entry.get("error") and len(feedback_errors) < MAX_RECORDED:
                    feedback_errors.append({"step": steps, "entry": dict(entry)})
            if view.red.time().is_play and "after-deployment" not in report["fingerprints"]:
                report["fingerprints"]["after-deployment"] = _slot_digests(view)
                transition = check_deployment_transition(setup_snapshot, state)
                report["deployment_transition_matches_profile"] = transition.matches
                report["deployment_transition_deviations"] = summarize(transition)
                write_json(evidence_dir / "observation-red-first-play.json", dict(view.red.fields))
                if capture:
                    capture("after-deployment", state)
                    captured.append("after-deployment")
            elif "after-deployment" in report["fingerprints"] and "play-step" not in report["fingerprints"]:
                report["fingerprints"]["play-step"] = _slot_digests(view)
                if capture:
                    capture("play-step", state)
                    captured.append("play-step")
            if done:
                break
    except Exception as exc:  # noqa: BLE001
        report.update(steps=steps, stage_transitions=stage_transitions, issued_actions=issued,
                      action_feedback_errors=feedback_errors, captured_points=captured)
        return fail(exc)
    timings["step_loop"] = time.perf_counter() - loop_started

    report.update(steps=steps, done=bool(done), stage_transitions=stage_transitions, issued_actions=issued,
                  action_feedback_errors=feedback_errors, captured_points=captured,
                  profile_deviation_count=deviation_count, profile_deviations=deviations)
    report["completion"] = ("done" if done else "step_limit" if steps >= limits.max_steps else "time_limit")
    final_time = view.red.time()
    report["final_time"] = {"cur_step": final_time.cur_step, "stage": final_time.stage,
                            "max_time": final_time.max_time, "max_step": final_time.max_step}
    report["final_scores"] = dict(view.red.fields.get("scores") or {})
    write_json(evidence_dir / "observation-red-final.json", dict(view.red.fields))

    report["phase"] = "reset"
    try:
        env.reset()
        for agent in agents:
            agent.reset()
    except Exception as exc:  # noqa: BLE001
        return fail(exc)
    report["phase"] = "finished"

    if auth_blocked():
        return report
    stages_seen = [t["stage"] for t in stage_transitions]
    if stages_seen[0] != Stage.DEPLOYMENT:
        report["reasons"].append(f"initial stage was {stages_seen[0]!r}, not {int(Stage.DEPLOYMENT)}; "
                                 "deployment completion cannot be verified")
    elif Stage.PLAY not in stages_seen:
        report["reasons"].append("the deployment stage never ended within the limits")
    else:
        report["status"] = "PASS"
    return report
