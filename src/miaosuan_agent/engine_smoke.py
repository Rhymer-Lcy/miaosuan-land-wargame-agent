"""Drive the SDK engine through one short game and record the observed interface contract.

The engine class is passed in by the caller, so this module never imports the SDK and can be
tested against a stand-in. The run stops at the first authentication failure, exception or limit,
and the report distinguishes three outcomes:

* ``BLOCKED`` - the engine printed an authentication failure; nothing further was attempted;
* ``FAIL``    - an exception occurred, the state had an unexpected shape, or deployment did not
  observably end within the limits;
* ``PASS``    - setup succeeded, stepping raised nothing, and the deployment stage was seen to end.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .sdk_data import ScenarioInputs

RED, BLUE, GREEN = 0, 1, -1
AUTH_FAILURE_MARKERS = ("did not pass authentication", "failed to initialize authenticator")
AUTH_SUCCESS_MARKER = "did pass authentication"
DEPLOYMENT_STAGE = 1
MAX_RECORDED_ERRORS = 20

#: Player list as used by the SDK's single-agent demo runner (the artifact shipped with the engine).
DEFAULT_PLAYERS: Sequence[Mapping[str, Any]] = (
    {"seat": 1, "faction": 0, "role": 1, "user_name": "demo", "user_id": 0},
    {"seat": 11, "faction": 1, "role": 1, "user_name": "demo", "user_id": 0},
)


@dataclass(frozen=True)
class SmokeLimits:
    max_steps: int
    max_seconds: float


def _type_name(value: Any) -> str:
    return type(value).__name__


def describe(value: Any, depth: int = 0, max_depth: int = 3, max_items: int = 4) -> Dict[str, Any]:
    """Summarise the Python types inside a value without copying its bulk."""
    if isinstance(value, Mapping):
        keys = list(value.keys())
        summary: Dict[str, Any] = {
            "type": _type_name(value),
            "len": len(keys),
            "key_types": sorted({_type_name(k) for k in keys}),
            "sample_keys": [repr(k) for k in keys[:max_items]],
        }
        if depth < max_depth:
            summary["values"] = {repr(k): describe(value[k], depth + 1, max_depth, max_items)
                                 for k in keys[:max_items]}
        return summary
    if isinstance(value, (list, tuple)):
        summary = {
            "type": _type_name(value),
            "len": len(value),
            "element_types": sorted({_type_name(v) for v in value}),
        }
        if value and depth < max_depth:
            summary["first"] = describe(value[0], depth + 1, max_depth, max_items)
        return summary
    shape = getattr(value, "shape", None)
    if shape is not None and hasattr(value, "dtype"):
        return {"type": _type_name(value), "dtype": str(value.dtype), "shape": list(shape)}
    if isinstance(value, (bool, int, float)) or (isinstance(value, str) and len(value) <= 40):
        return {"type": _type_name(value), "value": value}
    return {"type": _type_name(value)}


def contract_summary(observation: Any) -> Dict[str, Any]:
    """Record the fields the SDK audit flagged as uncertain, with their Python types."""
    if not isinstance(observation, Mapping):
        return {"observation": describe(observation)}
    summary: Dict[str, Any] = {"top_level_keys": sorted(str(k) for k in observation.keys())}
    time_info = observation.get("time")
    summary["time"] = describe(time_info)
    valid = observation.get("valid_actions")
    if isinstance(valid, Mapping):
        inner_key_types = set()
        inner_value_types = set()
        for per_operator in valid.values():
            if isinstance(per_operator, Mapping):
                inner_key_types.update(_type_name(k) for k in per_operator.keys())
                inner_value_types.update(_type_name(v) for v in per_operator.values())
        summary["valid_actions"] = {
            "operator_key_types": sorted({_type_name(k) for k in valid.keys()}),
            "action_key_types": sorted(inner_key_types),
            "action_value_types": sorted(inner_value_types),
            "sample": describe(valid, max_depth=2),
        }
    else:
        summary["valid_actions"] = describe(valid)
    for field in ("role_and_grouping_info", "communication", "cities", "scores", "actions",
                  "judge_info", "jm_points", "landmarks"):
        summary[field] = describe(observation[field]) if field in observation else {"present": False}
    for field in ("operators", "passengers"):
        items = observation.get(field)
        if isinstance(items, list):
            summary[field] = {
                "len": len(items),
                "obj_id_types": sorted({_type_name(item.get("obj_id")) for item in items
                                        if isinstance(item, Mapping)}),
                "first": describe(items[0], max_depth=1) if items else None,
            }
        else:
            summary[field] = describe(items)
    return summary


def _stage(observation: Any) -> Any:
    if isinstance(observation, Mapping) and isinstance(observation.get("time"), Mapping):
        return observation["time"].get("stage", "<absent>")
    return "<no time field>"


def _json_default(value: Any) -> Any:
    for attr in ("tolist", "item"):
        if hasattr(value, attr):
            return getattr(value, attr)()
    return repr(value)


def write_json(path: Path, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=_json_default),
                          encoding="utf-8")


def run_smoke(
    train_env_cls: Callable[[], Any],
    agent_factory: Callable[[], Any],
    inputs: ScenarioInputs,
    limits: SmokeLimits,
    evidence_dir: Path,
    captured_output: Callable[[], str],
    players: Sequence[Mapping[str, Any]] = DEFAULT_PLAYERS,
) -> Dict[str, Any]:
    """Run one controlled game and return the report. Raw observations go to ``evidence_dir``."""
    evidence_dir = Path(evidence_dir)
    report: Dict[str, Any] = {"scenario_id": inputs.scenario_id, "map_id": inputs.map_id,
                              "limits": {"max_steps": limits.max_steps, "max_seconds": limits.max_seconds},
                              "players": [dict(p) for p in players], "phase": "construct",
                              "status": "FAIL", "reasons": []}
    timings: Dict[str, float] = {}
    report["timings_seconds"] = timings

    def auth_blocked() -> bool:
        text = captured_output()
        report["auth_markers_seen"] = sorted(m for m in AUTH_FAILURE_MARKERS + (AUTH_SUCCESS_MARKER,)
                                             if m in text)
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
        auth_blocked()  # an authentication failure explains the exception better than the exception does
        return report

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

    report["initial_state"] = describe(state, max_depth=1)
    try:
        red_obs, blue_obs, green_obs = state[RED], state[BLUE], state[GREEN]
    except Exception as exc:  # noqa: BLE001
        return fail(exc)
    report["contract_initial_red"] = contract_summary(red_obs)
    report["contract_initial_green_top_level_keys"] = (sorted(str(k) for k in green_obs.keys())
                                                       if isinstance(green_obs, Mapping) else None)
    write_json(evidence_dir / "observation-red-initial.json", red_obs)

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
    stage_transitions: List[Dict[str, Any]] = [{"step": 0, "stage": _stage(red_obs)}]
    issued: List[Dict[str, Any]] = []
    errors: List[Any] = []
    done: Any = False
    steps = 0
    first_play_saved = False
    loop_started = time.perf_counter()
    try:
        while steps < limits.max_steps and time.perf_counter() - loop_started < limits.max_seconds:
            actions: List[Any] = []
            for player, agent in zip(players, agents):
                observation = state[RED] if player["faction"] == 0 else state[BLUE]
                produced = agent.step(observation)
                if produced:
                    issued.append({"step": steps, "seat": player["seat"], "actions": produced})
                actions.extend(produced)
            result = env.step(actions)
            steps += 1
            if not (isinstance(result, tuple) and len(result) == 2):
                report["step_return"] = describe(result, max_depth=1)
                raise TypeError(f"env.step returned {type(result).__name__}, expected a 2-tuple (state, done)")
            state, done = result
            if steps == 1:
                report["step_return"] = {"state": describe(state, max_depth=0), "done": describe(done)}
            red_obs = state[RED]
            stage = _stage(red_obs)
            if stage != stage_transitions[-1]["stage"]:
                stage_transitions.append({"step": steps, "stage": stage})
            if isinstance(red_obs, Mapping):
                for entry in red_obs.get("actions") or []:
                    if isinstance(entry, Mapping) and entry.get("error") and len(errors) < MAX_RECORDED_ERRORS:
                        errors.append({"step": steps, "entry": entry})
            if not first_play_saved and stage not in (DEPLOYMENT_STAGE, "<absent>", "<no time field>"):
                report["contract_first_play_red"] = contract_summary(red_obs)
                write_json(evidence_dir / "observation-red-first-play.json", red_obs)
                first_play_saved = True
            if done:
                break
    except Exception as exc:  # noqa: BLE001
        report.update(steps=steps, stage_transitions=stage_transitions, issued_actions=issued,
                      action_errors=errors)
        return fail(exc)
    timings["step_loop"] = time.perf_counter() - loop_started

    report.update(steps=steps, done=bool(done), stage_transitions=stage_transitions, issued_actions=issued,
                  action_errors=errors)
    report["completion"] = ("done" if done else
                            "step_limit" if steps >= limits.max_steps else "time_limit")
    if isinstance(red_obs, Mapping):
        report["final_time"] = red_obs.get("time")
        report["final_scores"] = red_obs.get("scores")
    write_json(evidence_dir / "observation-red-final.json", red_obs)

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
    if stages_seen[0] != DEPLOYMENT_STAGE:
        report["reasons"].append(f"initial stage was {stages_seen[0]!r}, not {DEPLOYMENT_STAGE}; "
                                 "deployment completion cannot be verified")
    elif len(stages_seen) < 2:
        report["reasons"].append("the deployment stage never ended within the limits")
    else:
        report["status"] = "PASS"
    return report
