"""Canonical, read-only access to one SDK observation.

An :class:`Observation` wraps the raw mapping delivered to an agent (or one slot of the engine
state) and validates each part when it is first requested. Required fields are the ones present
in every documentation generation and in the observed engine; optional fields are the ones some
documented form lacks. Unknown fields are preserved and reported, never discarded.

Values that are returned are new read-only containers (tuples and ``MappingProxyType``); nested
data the boundary does not validate (for example most operator fields) is passed through as
delivered, with whatever key form its origin produced.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .checks import require_bool, require_int, require_mapping, require_number, require_sequence, require_str
from .errors import MISSING, ContractError
from .keys import Origin, is_canonical_decimal, normalize_int_keyed

#: Fields the boundary knows by name. Anything else is kept and listed by ``unknown_fields()``.
KNOWN_FIELDS = frozenset({
    "actions", "cities", "communication", "jm_points", "judge_info", "landmarks", "operators",
    "passengers", "role_and_grouping_info", "scenario_id", "scores", "terrain_id", "time",
    "valid_actions",
})
#: Fields whose absence is a contract violation.
REQUIRED_FIELDS = frozenset({"time", "operators", "passengers", "valid_actions", "role_and_grouping_info"})

_TIME_FIELDS = frozenset({"cur_step", "stage", "tick", "max_time", "max_step"})
_SEAT_FIELDS = frozenset({"role", "operators", "faction", "user_id", "user_name", "end_deployment"})


class Stage(enum.IntEnum):
    """``time.stage`` values whose meaning is documented and was observed."""

    DEPLOYMENT = 1
    PLAY = 2


@dataclass(frozen=True)
class TimeInfo:
    cur_step: int
    stage: int
    tick: Optional[float]
    max_time: Optional[int]
    max_step: Optional[int]
    extra: Mapping[str, Any]

    @property
    def known_stage(self) -> Optional[Stage]:
        """The stage as :class:`Stage`, or ``None`` for a value outside the known set."""
        try:
            return Stage(self.stage)
        except ValueError:
            return None

    @property
    def is_deployment(self) -> bool:
        return self.stage == Stage.DEPLOYMENT

    @property
    def is_play(self) -> bool:
        return self.stage == Stage.PLAY


@dataclass(frozen=True)
class Operator:
    """One unit record: its id, and every field exactly as delivered (read-only)."""

    obj_id: int
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class SeatInfo:
    """One entry of ``role_and_grouping_info``. Optional members are ``None`` when absent."""

    seat: int
    role: int
    operators: Tuple[int, ...]
    faction: Optional[int]
    user_id: Optional[int]
    user_name: Optional[str]
    end_deployment: Optional[bool]
    extra: Mapping[str, Any]


#: Options for one action type: ``None`` (the action takes no choice) or a tuple of option records.
ActionOptions = Optional[Tuple[Mapping[str, Any], ...]]


def _readonly(mapping: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(mapping))


def _records(value: Any, path: str) -> Tuple[Mapping[str, Any], ...]:
    items = require_sequence(value, path)
    return tuple(_readonly(require_mapping(item, f"{path}[{index}]")) for index, item in enumerate(items))


@dataclass(frozen=True)
class Observation:
    """Validated accessors over one raw observation mapping."""

    fields: Mapping[str, Any]
    origin: Origin
    path: str
    _cache: Dict[str, Any] = field(default_factory=dict, init=False, repr=False, compare=False)

    @classmethod
    def from_raw(cls, raw: Any, origin: Origin = Origin.ENGINE, path: str = "observation") -> "Observation":
        """Wrap a raw observation. Only its top level is checked here: a mapping of field names."""
        mapping = require_mapping(raw, path)
        for key in mapping:
            if not isinstance(key, str):
                raise ContractError(f"{path}[{key!r}]", "a str field name", key)
        return cls(fields=_readonly(mapping), origin=origin, path=path)

    # -- helpers -------------------------------------------------------------------------------

    def _memo(self, name: str, build: Callable[[], Any]) -> Any:
        if name not in self._cache:
            self._cache[name] = build()
        return self._cache[name]

    def _required(self, name: str) -> Any:
        if name not in self.fields:
            raise ContractError(f"{self.path}.{name}", "a present field", MISSING)
        return self.fields[name]

    # -- required fields -----------------------------------------------------------------------

    def time(self) -> TimeInfo:
        return self._memo("time", self._build_time)

    def _build_time(self) -> TimeInfo:
        path = f"{self.path}.time"
        raw = require_mapping(self._required("time"), path)

        def member(name: str, check: Callable[[Any, str], Any], required: bool) -> Any:
            if name not in raw:
                if required:
                    raise ContractError(f"{path}.{name}", "a present field", MISSING)
                return None
            return check(raw[name], f"{path}.{name}")

        return TimeInfo(
            cur_step=member("cur_step", require_int, True),
            stage=member("stage", require_int, True),
            tick=member("tick", require_number, False),
            max_time=member("max_time", require_int, False),
            max_step=member("max_step", require_int, False),
            extra=_readonly({k: v for k, v in raw.items() if k not in _TIME_FIELDS}),
        )

    def operators(self) -> Tuple[Operator, ...]:
        return self._memo("operators", lambda: self._units("operators"))

    def passengers(self) -> Tuple[Operator, ...]:
        return self._memo("passengers", lambda: self._units("passengers"))

    def _units(self, name: str) -> Tuple[Operator, ...]:
        path = f"{self.path}.{name}"
        units = []
        seen = set()
        for index, record in enumerate(_records(self._required(name), path)):
            id_path = f"{path}[{index}].obj_id"
            if "obj_id" not in record:
                raise ContractError(id_path, "a present field", MISSING)
            obj_id = require_int(record["obj_id"], id_path)
            if obj_id in seen:
                raise ContractError(id_path, "an obj_id unique within the list", obj_id)
            seen.add(obj_id)
            units.append(Operator(obj_id=obj_id, fields=record))
        return tuple(units)

    def valid_actions(self) -> Mapping[int, Mapping[int, ActionOptions]]:
        """Operator id -> action type -> options, with both key levels normalized to int."""
        return self._memo("valid_actions", self._build_valid_actions)

    def _build_valid_actions(self) -> Mapping[int, Mapping[int, ActionOptions]]:
        path = f"{self.path}.valid_actions"
        result: Dict[int, Mapping[int, ActionOptions]] = {}
        for obj_id, per_unit in normalize_int_keyed(self._required("valid_actions"), self.origin, path).items():
            unit_path = f"{path}[{obj_id}]"
            actions: Dict[int, ActionOptions] = {}
            for action_type, options in normalize_int_keyed(per_unit, self.origin, unit_path).items():
                actions[action_type] = (None if options is None
                                        else _records(options, f"{unit_path}[{action_type}]"))
            result[obj_id] = MappingProxyType(actions)
        return MappingProxyType(result)

    def role_and_grouping(self) -> Mapping[int, SeatInfo]:
        """Seat -> seat information, with the seat keys normalized to int."""
        return self._memo("role_and_grouping", self._build_role_and_grouping)

    def _build_role_and_grouping(self) -> Mapping[int, SeatInfo]:
        path = f"{self.path}.role_and_grouping_info"
        result: Dict[int, SeatInfo] = {}
        for seat, record in normalize_int_keyed(self._required("role_and_grouping_info"), self.origin, path).items():
            seat_path = f"{path}[{seat}]"
            entry = require_mapping(record, seat_path)

            def member(name: str, check: Callable[[Any, str], Any], required: bool) -> Any:
                if name not in entry:
                    if required:
                        raise ContractError(f"{seat_path}.{name}", "a present field", MISSING)
                    return None
                return check(entry[name], f"{seat_path}.{name}")

            operator_path = f"{seat_path}.operators"
            operators = tuple(require_int(value, f"{operator_path}[{index}]")
                              for index, value in enumerate(member("operators", require_sequence, True)))
            result[seat] = SeatInfo(
                seat=seat,
                role=member("role", require_int, True),
                operators=operators,
                faction=member("faction", require_int, False),
                user_id=member("user_id", require_int, False),
                user_name=member("user_name", require_str, False),
                end_deployment=member("end_deployment", require_bool, False),
                extra=_readonly({k: v for k, v in entry.items() if k not in _SEAT_FIELDS}),
            )
        return MappingProxyType(result)

    def seat(self, seat: int) -> SeatInfo:
        seats = self.role_and_grouping()
        if seat not in seats:
            present = sorted(seats)[:10]
            raise ContractError(f"{self.path}.role_and_grouping_info", f"an entry for seat {seat}", seats,
                                detail=f"seats present: {present}")
        return seats[seat]

    # -- optional fields -----------------------------------------------------------------------

    def communication(self) -> Optional[Tuple[Mapping[str, Any], ...]]:
        """Command and message records, or ``None`` if the field is absent."""
        if "communication" not in self.fields:
            return None
        return self._memo("communication", lambda: _records(self.fields["communication"], f"{self.path}.communication"))

    def action_feedback(self) -> Optional[Tuple[Mapping[str, Any], ...]]:
        """Records of the ``actions`` field (observed only in the all-seeing view), or ``None``."""
        if "actions" not in self.fields:
            return None
        return self._memo("actions", lambda: _records(self.fields["actions"], f"{self.path}.actions"))

    def scenario_id(self) -> Optional[int]:
        """The scenario id, or ``None`` if absent.

        A canonical non-negative decimal string is accepted as well as an int, because four of the
        SDK's own scenario files store the id as a string.
        """
        if "scenario_id" not in self.fields:
            return None
        value = self.fields["scenario_id"]
        path = f"{self.path}.scenario_id"
        if isinstance(value, str):
            if is_canonical_decimal(value) and not value.startswith("-"):
                return int(value)
            raise ContractError(path, "an int or a canonical non-negative decimal string", value)
        return require_int(value, path)

    def terrain_id(self) -> Optional[int]:
        """The terrain (map) id, or ``None`` if absent. Only an int is accepted."""
        if "terrain_id" not in self.fields:
            return None
        return require_int(self.fields["terrain_id"], f"{self.path}.terrain_id")

    # -- whole-observation checks ----------------------------------------------------------------

    def unknown_fields(self) -> frozenset:
        return frozenset(name for name in self.fields if name not in KNOWN_FIELDS)

    def validate(self) -> "Observation":
        """Validate every field the boundary understands; return ``self`` for chaining."""
        self.time()
        self.operators()
        self.passengers()
        self.valid_actions()
        self.role_and_grouping()
        self.communication()
        self.action_feedback()
        self.scenario_id()
        self.terrain_id()
        return self
