"""T7 design study (``t7-design-1``, ``docs/T7_DESIGN.md``): action-semantics and opportunity audit.

Pure functions over raw seat observations (engine form: integer keys, as the replay corpus decodes and the capture
pickles hold them). No engine, no policy. The counts follow section 7 of the protocol:

1. decisions listing an action of a family for at least one own unit;
2. unit-decisions listing it, and the change-state options listed;
3. distinct situations by the structural fingerprint;
4. issued actions of the family;
5. observed transitions (see :class:`Transitions`);
6. what the frozen policy did with the unit instead;
7. listings with no executable opportunity;
8. missing and malformed records.

Units are read from the seat view's ``operators`` (own units have the seat's faction as ``color``); a unit listed in
``valid_actions`` but absent from ``operators`` (a passenger) is counted under archetype ``None``.
"""

from __future__ import annotations

import collections
import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

FAMILIES: Mapping[str, Tuple[int, ...]] = {"A": (6,), "B": (10,), "C": (11, 12)}
T7_TYPES = (6, 10, 11, 12)
NAMES = {6: "change state", 10: "stop", 11: "weapon lock", 12: "weapon unfold"}
SHOOT, MOVE, OCCUPY = 2, 1, 5
#: Fields of a unit record the audit reads (missing values are counted, never imputed).
FIELDS = ("type", "sub_type", "move_state", "stop", "move_path", "change_state_remain_time", "weapon_unfold_state",
          "keep", "tire", "speed", "move_to_stop_remain_time", "target_state", "weapon_unfold_time", "can_to_move",
          "flag_force_stop", "tire_accumulate_time", "A1", "passenger_ids", "basic_speed")


def number(value: Any) -> Optional[float]:
    """A plain int or float (never a bool), else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def integer(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def family_of(action_type: int) -> Optional[str]:
    for family, types in FAMILIES.items():
        if action_type in types:
            return family
    return None


def operators(raw: Mapping[str, Any]) -> Dict[int, Mapping[str, Any]]:
    out = {}
    for unit in raw.get("operators") or ():
        if isinstance(unit, Mapping) and integer(unit.get("obj_id")) is not None:
            out[unit["obj_id"]] = unit
    return out


def enemy_seen(raw: Mapping[str, Any], faction: int) -> bool:
    return any(unit.get("color") != faction for unit in operators(raw).values())


def listings(raw: Mapping[str, Any]) -> Dict[int, Dict[int, Any]]:
    """``valid_actions`` as {unit id: {action type: options}} with integer keys (engine form)."""
    out: Dict[int, Dict[int, Any]] = {}
    for unit_id, actions in (raw.get("valid_actions") or {}).items():
        if integer(unit_id) is None or not isinstance(actions, Mapping):
            continue
        out[unit_id] = {t: options for t, options in actions.items() if integer(t) is not None}
    return out


def target_states(options: Any) -> Tuple[Tuple[int, ...], int]:
    """Sorted distinct ``target_state`` values of change-state options, and the number of malformed options."""
    values, malformed = set(), 0
    for option in options or ():
        value = option.get("target_state") if isinstance(option, Mapping) else None
        if integer(value) is None:
            malformed += 1
        else:
            values.add(value)
    return tuple(sorted(values)), malformed


def archetype(unit: Optional[Mapping[str, Any]]) -> Optional[str]:
    if unit is None:
        return None
    return f"{unit.get('type')}.{unit.get('sub_type')}"


def has_path(unit: Mapping[str, Any]) -> Optional[bool]:
    path = unit.get("move_path")
    if path is None:
        return None
    return bool(path)


def positive(unit: Mapping[str, Any], name: str) -> Optional[bool]:
    value = number(unit.get(name))
    return None if value is None else value > 0


def situation(unit: Mapping[str, Any]) -> Tuple[Any, ...]:
    """The unit's movement-state situation (``None`` marks a missing field)."""
    return (unit.get("move_state"), unit.get("stop"), has_path(unit), positive(unit, "speed"),
            positive(unit, "change_state_remain_time"), positive(unit, "move_to_stop_remain_time"),
            unit.get("weapon_unfold_state"), positive(unit, "keep"), unit.get("tire"))


SITUATION_FIELDS = ("move_state", "stop", "has_path", "speed>0", "change_state_remain_time>0",
                    "move_to_stop_remain_time>0", "weapon_unfold_state", "keep>0", "tire")


def option_signature(family: str, unit_actions: Mapping[int, Any]) -> Tuple[Any, ...]:
    """The family's listed types and, for change state, the sorted listed target states."""
    out: List[Any] = []
    for t in FAMILIES[family]:
        if t in unit_actions:
            out.append((t, target_states(unit_actions[t])[0]) if t == 6 else (t,))
    return tuple(out)


def fingerprint(family: str, unit: Optional[Mapping[str, Any]], unit_actions: Mapping[int, Any], seen: bool) -> str:
    """Section 7's structural fingerprint, as a short digest (no identifiers, hexes or steps)."""
    u = unit or {}
    others = sorted(t for t in unit_actions if family_of(t) != family)
    key = [family, u.get("type"), u.get("sub_type"), u.get("move_state"), u.get("stop"),
           has_path(u) if unit else None, positive(u, "change_state_remain_time") if unit else None,
           u.get("weapon_unfold_state"), positive(u, "keep") if unit else None, u.get("tire"), seen,
           [list(x) if isinstance(x, tuple) else x for x in option_signature(family, unit_actions)], others]
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=repr).encode("utf-8")).hexdigest()[:16]


def no_opportunity(action_type: int, unit: Optional[Mapping[str, Any]], options: Any) -> Optional[str]:
    """Why a listing offers nothing executable (section 7, count 7), or ``None``."""
    if unit is None:
        return "unit not in operators"
    if action_type == 6:
        states, _ = target_states(options)
        if not states:
            return "no well-formed option"
        if all(s == unit.get("move_state") for s in states):
            return "only the current state"
        return None
    if action_type == 10:
        path = has_path(unit)
        if path is None:
            return "move path missing"
        if not path:
            return "empty move path"
        if positive(unit, "speed") is False:
            if unit.get("type") == 3:
                return "speed 0 with a move path (aircraft)"
            return "speed 0 with a move path (ground unit; the Sprint 4 case when its next hex is full)"
        return None
    if action_type == 11:
        return "already locked" if unit.get("weapon_unfold_state") == 0 else None
    if action_type == 12:
        return "already unfolded" if unit.get("weapon_unfold_state") == 1 else None
    return None


def frozen_category(actions: Sequence[Mapping[str, Any]]) -> Dict[int, str]:
    """Per unit id, the category of the action the frozen policy emitted (``other`` for anything else)."""
    names = {SHOOT: "shoot", OCCUPY: "occupy", MOVE: "move"}
    out = {}
    for action in actions:
        obj = action.get("obj_id")
        if integer(obj) is not None:
            out[obj] = names.get(action.get("type"), f"type {action.get('type')}")
    return out


class Audit:
    """Accumulates counts 1 to 4 and 6 to 8 for one population."""

    def __init__(self) -> None:
        self.decisions: collections.Counter = collections.Counter()
        self.listing_decisions: collections.Counter = collections.Counter()
        self.unit_listings: collections.Counter = collections.Counter()
        self.by_archetype: collections.Counter = collections.Counter()
        self.options6: collections.Counter = collections.Counter()
        self.option_sets6: collections.Counter = collections.Counter()
        self.fingerprints: Dict[str, set] = collections.defaultdict(set)
        self.fingerprints_by_game: Dict[str, set] = collections.defaultdict(set)
        self.issued: collections.Counter = collections.Counter()
        self.frozen: collections.Counter = collections.Counter()
        self.no_opportunity: collections.Counter = collections.Counter()
        self.missing: collections.Counter = collections.Counter()
        self.malformed: collections.Counter = collections.Counter()
        self.semantics: collections.Counter = collections.Counter()
        self.games: set = set()

    def add(self, game: str, faction: int, raw: Mapping[str, Any], actions: Sequence[Mapping[str, Any]]) -> None:
        stage = {1: "deployment", 2: "play"}.get((raw.get("time") or {}).get("stage"), "other")
        self.games.add(game)
        self.decisions[stage] += 1
        units = operators(raw)
        listed = listings(raw)
        seen = enemy_seen(raw, faction)
        frozen = frozen_category(actions)
        for action in actions:
            t = action.get("type")
            if t in T7_TYPES:
                self.issued[f"{stage}:{t}"] += 1
        decision_types = set()
        for unit_id, unit_actions in listed.items():
            unit = units.get(unit_id)
            if unit is not None and unit.get("color") != faction:
                continue
            if unit is not None:
                for name in FIELDS:
                    if name not in unit or unit.get(name) is None:
                        self.missing[f"{stage}:{name}"] += 1
            arch = archetype(unit)
            for t in T7_TYPES:
                if t not in unit_actions:
                    continue
                family = family_of(t)
                decision_types.add(t)
                self.unit_listings[f"{stage}:{t}"] += 1
                self.by_archetype[f"{stage}:{t}:{arch}"] += 1
                options = unit_actions[t]
                if t == 6:
                    states, malformed = target_states(options)
                    if malformed:
                        self.malformed[f"{stage}:6"] += malformed
                    for s in states:
                        self.options6[f"{stage}:{arch}:{s}"] += 1
                    self.option_sets6[f"{stage}:{arch}:{list(states)}"] += 1
                reason = no_opportunity(t, unit, options)
                if reason:
                    self.no_opportunity[f"{stage}:{t}:{reason}"] += 1
                self.frozen[f"{stage}:{t}:{frozen.get(unit_id, 'nothing')}"] += 1
                if unit is not None:
                    sig = list(option_signature(family, unit_actions)) if t == 6 else []
                    self.semantics[json.dumps([stage, t, arch, list(situation(unit)), sig], default=repr)] += 1
            for family, types in FAMILIES.items():
                if any(t in unit_actions for t in types):
                    fp = fingerprint(family, unit, unit_actions, seen)
                    self.fingerprints[f"{stage}:{family}"].add(fp)
                    self.fingerprints_by_game[f"{stage}:{family}:{game}"].add(fp)
        for t in decision_types:
            self.listing_decisions[f"{stage}:{t}"] += 1

    def summary(self) -> Dict[str, Any]:
        per_game: Dict[str, List[int]] = collections.defaultdict(list)
        for key, fps in sorted(self.fingerprints_by_game.items()):
            stage, family, _ = key.split(":", 2)
            per_game[f"{stage}:{family}"].append(len(fps))
        return {
            "games": len(self.games), "decisions": dict(sorted(self.decisions.items())),
            "decisions_listing": dict(sorted(self.listing_decisions.items())),
            "unit_listings": dict(sorted(self.unit_listings.items())),
            "unit_listings_by_archetype": dict(sorted(self.by_archetype.items())),
            "change_state_options": dict(sorted(self.options6.items())),
            "change_state_option_sets": dict(sorted(self.option_sets6.items())),
            "distinct_situations": {k: len(v) for k, v in sorted(self.fingerprints.items())},
            "distinct_situations_per_game": {k: sorted(v) for k, v in sorted(per_game.items())},
            "issued": dict(sorted(self.issued.items())),
            "frozen_policy_instead": dict(sorted(self.frozen.items())),
            "no_executable_opportunity": dict(sorted(self.no_opportunity.items())),
            "missing_fields": dict(sorted(self.missing.items())),
            "malformed_options": dict(sorted(self.malformed.items())),
        }

    def semantics_table(self) -> List[Dict[str, Any]]:
        rows = []
        for key, n in sorted(self.semantics.items()):
            stage, t, arch, sit, sig = json.loads(key)
            rows.append({"stage": stage, "type": t, "archetype": arch, "situation": dict(zip(SITUATION_FIELDS, sit)),
                         "options": sig, "unit_decisions": n})
        return rows


class Transitions:
    """Observed transitions of own units between consecutive decisions of one seat (count 5).

    ``add`` takes decisions in order. Two decisions are consecutive when ``cur_step`` grows by exactly one; any other
    gap closes every open episode as ambiguous. Episodes: positive ``change_state_remain_time``, positive
    ``move_to_stop_remain_time``, positive ``weapon_unfold_time``; field changes of ``move_state``,
    ``weapon_unfold_state``, ``tire``, ``flag_force_stop`` and ``stop``; and arrivals (a move path becoming empty) with
    the steps until ``stop`` is 1 and until a shoot, occupy or move listing appears for the unit.
    """

    EPISODE_FIELDS = ("change_state_remain_time", "move_to_stop_remain_time", "weapon_unfold_time")
    CHANGE_FIELDS = ("move_state", "weapon_unfold_state", "tire", "flag_force_stop", "stop", "target_state")

    def __init__(self) -> None:
        self.previous: Optional[Tuple[int, Dict[int, Mapping[str, Any]]]] = None
        self.open: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self.arrivals: Dict[int, Dict[str, Any]] = {}
        self.episodes: List[Dict[str, Any]] = []
        self.changes: collections.Counter = collections.Counter()
        self.arrival_rows: List[Dict[str, Any]] = []
        self.gaps = 0

    def _close_all(self, how: str) -> None:
        for (unit_id, name), ep in sorted(self.open.items()):
            self.episodes.append(dict(ep, field=name, end=how))
        self.open.clear()
        for unit_id, arr in sorted(self.arrivals.items()):
            self.arrival_rows.append(dict(arr, end=how))
        self.arrivals.clear()

    def add(self, cur_step: int, faction: int, raw: Mapping[str, Any]) -> None:
        units = {i: u for i, u in operators(raw).items() if u.get("color") == faction}
        listed = listings(raw)
        if self.previous is not None and cur_step != self.previous[0] + 1:
            self.gaps += 1
            self._close_all("ambiguous gap")
            self.previous = None
        if self.previous is not None:
            before = self.previous[1]
            for unit_id, unit in units.items():
                old = before.get(unit_id)
                if old is None:
                    continue
                arch = archetype(unit)
                for name in self.CHANGE_FIELDS:
                    if old.get(name) != unit.get(name):
                        self.changes[f"{name}:{arch}:{old.get(name)}->{unit.get(name)}"] += 1
                if has_path(old) and has_path(unit) is False:
                    self.arrivals[unit_id] = {"archetype": arch, "start": cur_step, "stop_after": None,
                                              "listed_after": {}}
            for unit_id in set(before) - set(units):
                for key in [k for k in self.open if k[0] == unit_id]:
                    self.episodes.append(dict(self.open.pop(key), field=key[1], end="unit gone"))
                if unit_id in self.arrivals:
                    self.arrival_rows.append(dict(self.arrivals.pop(unit_id), end="unit gone"))
        for unit_id, unit in units.items():
            for name in self.EPISODE_FIELDS:
                value = number(unit.get(name))
                key = (unit_id, name)
                if value is not None and value > 0:
                    if key not in self.open:
                        self.open[key] = {"archetype": archetype(unit), "start": cur_step, "first_value": value,
                                          "state_before": unit.get("move_state"), "target_state": unit.get("target_state"),
                                          "steps": 0, "values": []}
                    ep = self.open[key]
                    ep["steps"] += 1
                    if len(ep["values"]) < 3:
                        ep["values"].append(value)
                elif key in self.open:
                    ep = self.open.pop(key)
                    self.episodes.append(dict(ep, field=name, end="completed", state_after=unit.get("move_state"),
                                              unfold_after=unit.get("weapon_unfold_state")))
            arr = self.arrivals.get(unit_id)
            if arr is not None:
                age = cur_step - arr["start"]
                if arr["stop_after"] is None and unit.get("stop") == 1:
                    arr["stop_after"] = age
                for t, name in ((SHOOT, "shoot"), (OCCUPY, "occupy"), (MOVE, "move")):
                    if t in listed.get(unit_id, {}) and name not in arr["listed_after"]:
                        arr["listed_after"][name] = age
                if has_path(unit):
                    self.arrival_rows.append(dict(self.arrivals.pop(unit_id), end="moved again"))
                elif arr["stop_after"] is not None and "move" in arr["listed_after"]:
                    self.arrival_rows.append(dict(self.arrivals.pop(unit_id), end="settled"))
        self.previous = (cur_step, units)

    def finish(self) -> None:
        self._close_all("censored at the last observation")
