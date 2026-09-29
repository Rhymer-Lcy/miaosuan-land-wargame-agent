"""Observed contract profile of the locally supplied SDK engine.

A profile states what was *measured* from one engine build, and nothing more. It is deliberately
stricter than the accepted boundary (exact key sets, exact Python types) so that any change in a
new engine build, scenario or platform shows up as a deviation. A deviation is a finding, not
necessarily an error: the boundary may still accept the input.

Evidence scope of ``local-sdk-4.1.0``: engine ``land_wargame_train_env`` 4.1.0, scenario
201033019601 on map 9601, two controlled runs on 2026-09-29 (a disposable first probe, then the
first session of the persistent installation, which captured all three slots at setup, after
deployment and during play; see ``docs/CONTRACT.md``). Facts that depend on the scenario (unit
counts, positions, values) are not part of the profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from .errors import describe_value

PROFILE_ID = "local-sdk-4.1.0"

STATE_SLOTS = (0, 1, -1)
PLAYER_FIELDS = frozenset({
    "cities", "communication", "jm_points", "judge_info", "landmarks", "operators", "passengers",
    "role_and_grouping_info", "scenario_id", "scores", "terrain_id", "time", "valid_actions",
})
GLOBAL_ONLY_FIELDS = frozenset({"actions"})
FIELD_TYPES: Mapping[str, type] = {
    "actions": list, "cities": list, "communication": list, "jm_points": list, "judge_info": list,
    "landmarks": dict, "operators": list, "passengers": list, "role_and_grouping_info": dict,
    "scenario_id": int, "scores": dict, "terrain_id": int, "time": dict, "valid_actions": dict,
}
TIME_FIELD_TYPES: Mapping[str, type] = {"cur_step": int, "tick": float, "max_time": int, "max_step": int,
                                        "stage": int}
OBSERVED_STAGES = frozenset({1, 2})
SEAT_FIELD_TYPES: Mapping[str, type] = {"faction": int, "role": int, "operators": list, "user_id": int,
                                        "user_name": str, "end_deployment": bool}
LANDMARK_FIELDS = frozenset({"roadblocks", "minefields", "fortifications"})
SCORE_FIELDS = frozenset({
    "red_occupy", "red_remain", "red_remain_max", "red_attack", "red_total", "red_win",
    "blue_occupy", "blue_remain", "blue_remain_max", "blue_attack", "blue_total", "blue_win",
})
#: Key under which the all-seeing view lists the director's options instead of a unit's.
DIRECTOR_KEY = -1
#: Director action types observed under ``DIRECTOR_KEY`` (all with option value ``None``).
DIRECTOR_ACTION_TYPES = frozenset({401, 402, 403, 404})
#: Slots whose field contents (not only their key sets) are covered by the evidence.
DETAIL_VERIFIED_SLOTS: Tuple[int, ...] = (0, 1, -1)


@dataclass(frozen=True)
class Deviation:
    path: str
    expected: str
    actual: str


@dataclass(frozen=True)
class ProfileReport:
    profile_id: str
    deviations: Tuple[Deviation, ...]

    @property
    def matches(self) -> bool:
        return not self.deviations


class _Recorder:
    def __init__(self) -> None:
        self.items: List[Deviation] = []

    def __call__(self, path: str, expected: str, actual: Any, as_text: bool = False) -> None:
        self.items.append(Deviation(path, expected, actual if as_text else describe_value(actual)))

    def report(self) -> ProfileReport:
        return ProfileReport(PROFILE_ID, tuple(self.items))


def _exact(value: Any, kind: type) -> bool:
    return type(value) is kind


def _key_set(record: Mapping[Any, Any], expected: frozenset, path: str, dev: _Recorder) -> None:
    keys = set(record)
    if keys != expected:
        missing = sorted(map(str, expected - keys))
        extra = sorted(map(repr, keys - expected))
        dev(path, f"exactly {len(expected)} fields", f"missing {missing}, unexpected {extra}", as_text=True)


def _check_int_keys(mapping: Mapping[Any, Any], path: str, dev: _Recorder) -> None:
    for key in mapping:
        if not _exact(key, int):
            dev(f"{path}[{key!r}]", "an int key", key)


def _unit_ids(obs: Mapping[str, Any]) -> set:
    ids = set()
    for name in ("operators", "passengers"):
        for unit in obs.get(name) or []:
            if _exact(unit, dict) and "obj_id" in unit:
                ids.add(unit["obj_id"])
    return ids


def _check_detail(obs: Mapping[str, Any], slot: int, path: str, dev: _Recorder) -> None:
    for name, kind in FIELD_TYPES.items():
        if name in obs and not _exact(obs[name], kind):
            dev(f"{path}.{name}", kind.__name__, obs[name])

    time_info = obs.get("time")
    if _exact(time_info, dict):
        _key_set(time_info, frozenset(TIME_FIELD_TYPES), f"{path}.time", dev)
        for name, kind in TIME_FIELD_TYPES.items():
            if name in time_info and not _exact(time_info[name], kind):
                dev(f"{path}.time.{name}", kind.__name__, time_info[name])
        if _exact(time_info.get("stage"), int) and time_info["stage"] not in OBSERVED_STAGES:
            dev(f"{path}.time.stage", f"one of {sorted(OBSERVED_STAGES)}", time_info["stage"])

    valid = obs.get("valid_actions")
    if _exact(valid, dict):
        _check_int_keys(valid, f"{path}.valid_actions", dev)
        allowed = _unit_ids(obs) | ({DIRECTOR_KEY} if slot == -1 else set())
        strangers = sorted(repr(key) for key in valid if key not in allowed)
        if strangers:
            dev(f"{path}.valid_actions", "keys that are unit ids" + (" or the director key" if slot == -1 else ""),
                f"other keys {strangers[:5]}", as_text=True)
        if slot == -1:
            director = valid.get(DIRECTOR_KEY)
            if not _exact(director, dict) or set(director) != DIRECTOR_ACTION_TYPES:
                dev(f"{path}.valid_actions[{DIRECTOR_KEY}]", f"action types {sorted(DIRECTOR_ACTION_TYPES)}",
                    str(sorted(map(repr, director))) if _exact(director, dict) else director,
                    as_text=_exact(director, dict))
        for obj_id, per_unit in valid.items():
            unit_path = f"{path}.valid_actions[{obj_id!r}]"
            if not _exact(per_unit, dict):
                dev(unit_path, "dict", per_unit)
                continue
            _check_int_keys(per_unit, unit_path, dev)
            for action_type, options in per_unit.items():
                option_path = f"{unit_path}[{action_type!r}]"
                if options is None:
                    continue
                if not _exact(options, list) or not all(_exact(option, dict) for option in options):
                    dev(option_path, "None or a list of dicts", options)

    seats = obs.get("role_and_grouping_info")
    if _exact(seats, dict):
        _check_int_keys(seats, f"{path}.role_and_grouping_info", dev)
        for seat, record in seats.items():
            seat_path = f"{path}.role_and_grouping_info[{seat!r}]"
            if not _exact(record, dict):
                dev(seat_path, "dict", record)
                continue
            _key_set(record, frozenset(SEAT_FIELD_TYPES), seat_path, dev)
            for name, kind in SEAT_FIELD_TYPES.items():
                if name in record and not _exact(record[name], kind):
                    dev(f"{seat_path}.{name}", kind.__name__, record[name])
            if _exact(record.get("operators"), list):
                for index, value in enumerate(record["operators"]):
                    if not _exact(value, int):
                        dev(f"{seat_path}.operators[{index}]", "int", value)

    landmarks = obs.get("landmarks")
    if _exact(landmarks, dict):
        _key_set(landmarks, LANDMARK_FIELDS, f"{path}.landmarks", dev)
        for name in LANDMARK_FIELDS & set(landmarks):
            if not _exact(landmarks[name], list):
                dev(f"{path}.landmarks.{name}", "list", landmarks[name])

    scores = obs.get("scores")
    if _exact(scores, dict):
        _key_set(scores, SCORE_FIELDS, f"{path}.scores", dev)
        for name, value in scores.items():
            if not _exact(value, int):
                dev(f"{path}.scores[{name!r}]", "int", value)


def check_state(raw_state: Any) -> ProfileReport:
    """Compare one raw in-process engine state against the observed profile."""
    dev = _Recorder()
    if not _exact(raw_state, dict):
        dev("state", "dict", raw_state)
        return dev.report()
    keys = list(raw_state)
    if set(keys) != set(STATE_SLOTS) or not all(_exact(key, int) for key in keys):
        dev("state", "int keys exactly 0, 1, -1", sorted(map(repr, keys)), as_text=True)
    for slot in STATE_SLOTS:
        if slot not in raw_state:
            continue
        obs = raw_state[slot]
        path = f"state[{slot}]"
        if not _exact(obs, dict):
            dev(path, "dict", obs)
            continue
        expected = PLAYER_FIELDS | GLOBAL_ONLY_FIELDS if slot == -1 else PLAYER_FIELDS
        _key_set(obs, expected, path, dev)
        if slot in DETAIL_VERIFIED_SLOTS:
            _check_detail(obs, slot, path, dev)
    return dev.report()


def check_deployment_transition(before: Any, after: Any) -> ProfileReport:
    """Check the observed deployment transition between two raw states.

    For every detail-verified player slot: ``time.stage`` goes from 1 to 2 and every seat's
    ``end_deployment`` goes from False to True.
    """
    dev = _Recorder()
    for slot in DETAIL_VERIFIED_SLOTS:
        if slot not in (0, 1):
            continue
        first, second = _dig(before, slot), _dig(after, slot)
        if not _exact(first, dict) or not _exact(second, dict):
            dev(f"state[{slot}]", "a dict in both states", first if not _exact(first, dict) else second)
            continue
        stages = (_dig(first, "time", "stage"), _dig(second, "time", "stage"))
        if stages != (1, 2):
            dev(f"state[{slot}].time.stage", "1 before and 2 after", f"{stages[0]!r} -> {stages[1]!r}", as_text=True)
        seats = _dig(first, "role_and_grouping_info")
        for seat in (seats if _exact(seats, dict) else {}):
            flags = (_dig(first, "role_and_grouping_info", seat, "end_deployment"),
                     _dig(second, "role_and_grouping_info", seat, "end_deployment"))
            if flags != (False, True):
                dev(f"state[{slot}].role_and_grouping_info[{seat!r}].end_deployment", "False before and True after",
                    f"{flags[0]!r} -> {flags[1]!r}", as_text=True)
    return dev.report()


def _dig(value: Any, *keys: Any) -> Any:
    """Follow ``keys`` through nested dicts; ``None`` as soon as a level is not a dict or lacks the key."""
    for key in keys:
        if not _exact(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def summarize(report: ProfileReport, limit: int = 20) -> List[Dict[str, str]]:
    """JSON-friendly list of the first ``limit`` deviations."""
    return [{"path": d.path, "expected": d.expected, "actual": d.actual} for d in report.deviations[:limit]]
