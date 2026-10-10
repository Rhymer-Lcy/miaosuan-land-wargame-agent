"""The world view of one decision: what the seat's own observation says, read once, in project terms.

Built only from the canonical :class:`~miaosuan_agent.boundary.Observation` of the deciding seat. Enemy units are
the ones the seat's observation lists (visible ones); their masked relation fields are never read. Every collection
is sorted by an explicit key so that nothing downstream depends on the engine's delivery order.

Unit states (measured on genuine captures, ``docs/SPRINT34_INTEGRATED_AGENT.md`` section 3):

* ``MOVING``: a move path and positive speed (traversing a hex);
* ``WAITING``: a move path and zero speed (in front of a full hex; only the stop action is listed);
* ``TRANSITION``: no path, ``move_to_stop_remain_time`` positive (the 75-step post-arrival transition; movement and,
  when the zone is clear, occupation are listed);
* ``BOARDING`` / ``UNLOADING`` / ``CHANGING``: an embark, disembark or state-change timer running;
* ``SETTLED``: none of the above.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from ..boundary import ContractError, Observation, Stage
from ..boundary.observation import ActionOptions, Operator
from . import facts as F


class State(str, enum.Enum):
    MOVING = "moving"
    WAITING = "waiting"
    TRANSITION = "transition"
    BOARDING = "boarding"
    UNLOADING = "unloading"
    CHANGING = "changing"
    SETTLED = "settled"


def _ints(value: Any) -> Tuple[int, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(v for v in value if F.is_int(v))
    return ()


@dataclass(frozen=True)
class Unit:
    """One own unit as the seat sees it."""

    obj_id: int
    type: int
    sub_type: int
    hex: int
    path: Tuple[int, ...]
    speed: float
    cur_pos: float
    basic_speed: float
    blood: float
    max_blood: float
    value: float
    move_to_stop: float
    get_on_time: float
    get_off_time: float
    change_time: float
    aboard: bool
    passengers: Tuple[int, ...]
    passenger_types: Tuple[int, ...]
    weapons: Tuple[int, ...]
    sees: Tuple[int, ...]
    armor: int
    move_state: int
    actions: Mapping[int, ActionOptions]
    controllable: bool

    @property
    def state(self) -> State:
        if self.path:
            return State.MOVING if self.speed > 0 else State.WAITING
        if self.get_on_time > 0:
            return State.BOARDING
        if self.get_off_time > 0:
            return State.UNLOADING
        if self.change_time > 0:
            return State.CHANGING
        if self.move_to_stop > 0:
            return State.TRANSITION
        return State.SETTLED

    @property
    def ground(self) -> bool:
        return self.type in F.GROUND

    @property
    def air(self) -> bool:
        return self.type == F.AIRCRAFT

    @property
    def artillery(self) -> bool:
        """Indirect-fire capable and never mobile on engine 4.1.0 (Sprint 34 measurement)."""
        return F.INDIRECT in self.actions or (self.type == F.VEHICLE and self.sub_type == F.ARTILLERY)

    @property
    def can_move(self) -> bool:
        return F.MOVE in self.actions

    @property
    def destination(self) -> Optional[int]:
        return self.path[-1] if self.path else None

    @property
    def carrier(self) -> bool:
        """A vehicle that can carry an infantry squad: its ``valid_passenger_types`` lists passenger sub_types, and
        names sub_type 2 (squad) on the infantry fighting vehicles of the SDK scenarios (checked in Sprint 34)."""
        return self.type == F.VEHICLE and F.SQUAD in self.passenger_types

    @property
    def mobile_ground(self) -> bool:
        return self.ground and not self.artillery and not self.aboard

    def seconds_into_next_hex(self) -> int:
        """Steps until the next hex entry of a traversing unit (the measured ``ceil((1 - cur_pos) / speed)``)."""
        if not self.path or self.speed <= 0:
            return 0
        remaining = max(0.0, 1.0 - self.cur_pos)
        steps = remaining / self.speed
        return int(steps) if abs(steps - int(steps)) < 1e-9 else int(steps) + 1


@dataclass(frozen=True)
class Enemy:
    obj_id: int
    type: int
    sub_type: int
    hex: int
    path: Tuple[int, ...]
    speed: float
    basic_speed: float
    blood: float
    value: float
    weapons: Tuple[int, ...]

    @property
    def ground(self) -> bool:
        return self.type in F.GROUND


@dataclass(frozen=True)
class Objective:
    hex: int
    value: float
    flag: Optional[int]
    zone: FrozenSet[int]


@dataclass(frozen=True)
class World:
    seat: int
    faction: int
    stage: int
    step: int
    max_step: int
    rows: int
    cols: int
    units: Tuple[Unit, ...]
    passengers: Tuple[Unit, ...]
    allies: Tuple[Unit, ...]
    enemies: Tuple[Enemy, ...]
    objectives: Tuple[Objective, ...]
    roadblocks: FrozenSet[int]
    impact_points: Tuple[Tuple[int, int, float], ...]
    excluded: Tuple[Tuple[int, str], ...]

    @property
    def remaining(self) -> int:
        return max(0, self.max_step - self.step)

    def unit(self, obj_id: int) -> Optional[Unit]:
        for unit in self.units:
            if unit.obj_id == obj_id:
                return unit
        return None

    def passenger(self, obj_id: int) -> Optional[Unit]:
        for unit in self.passengers:
            if unit.obj_id == obj_id:
                return unit
        return None

    def ground_occupancy(self) -> Dict[int, int]:
        """Own ground units physically in each hex (controllable or not, passengers excluded)."""
        counts: Dict[int, int] = {}
        for unit in self.units + self.allies:
            if unit.ground and not unit.aboard:
                counts[unit.hex] = counts.get(unit.hex, 0) + 1
        return counts

    def objective(self, hex_: int) -> Optional[Objective]:
        for objective in self.objectives:
            if objective.hex == hex_:
                return objective
        return None


def _unit(operator: Operator, actions: Mapping[int, ActionOptions], controllable: bool, aboard: bool) -> Unit:
    f = operator.fields
    path = operator.move_path or ()
    return Unit(
        obj_id=operator.obj_id, type=operator.unit_type, sub_type=operator.sub_type if operator.sub_type is not None else -1,
        hex=operator.cur_hex, path=tuple(path), speed=F.number(f.get("speed")), cur_pos=F.number(f.get("cur_pos")),
        basic_speed=F.number(f.get("basic_speed")), blood=F.number(f.get("blood")), max_blood=F.number(f.get("max_blood")),
        value=F.number(f.get("value")), move_to_stop=F.number(f.get("move_to_stop_remain_time")),
        get_on_time=F.number(f.get("get_on_remain_time")), get_off_time=F.number(f.get("get_off_remain_time")),
        change_time=F.number(f.get("change_state_remain_time")),
        aboard=aboard or bool(f.get("on_board")), passengers=tuple(sorted(_ints(f.get("passenger_ids")))),
        passenger_types=tuple(sorted(_ints(f.get("valid_passenger_types")))),
        weapons=tuple(sorted(_ints(f.get("carry_weapon_ids")))), sees=tuple(sorted(_ints(f.get("see_enemy_bop_ids")))),
        armor=int(f.get("armor")) if F.is_int(f.get("armor")) else 0,
        move_state=operator.move_state if operator.move_state is not None else 0, actions=actions,
        controllable=controllable,
    )


def build_world(observation: Observation, seat: int, faction: int, rows: int, cols: int) -> World:
    """The world view of the seat ``seat`` (faction ``faction``) from its own observation."""
    time_info = observation.time()
    seat_info = observation.seat(seat)
    if seat_info.faction is not None and seat_info.faction != faction:
        raise ContractError(f"{observation.path}.role_and_grouping_info[{seat}].faction",
                            f"the faction given at setup ({faction})", seat_info.faction)
    controllable = set(seat_info.operators)
    valid = observation.valid_actions()
    units: List[Unit] = []
    allies: List[Unit] = []
    enemies: List[Enemy] = []
    excluded: List[Tuple[int, str]] = []
    on_map = set()
    for operator in sorted(observation.operators(), key=lambda u: u.obj_id):
        on_map.add(operator.obj_id)
        if operator.color == faction:
            if operator.obj_id in controllable:
                units.append(_unit(operator, valid.get(operator.obj_id, {}), True, False))
            else:
                allies.append(_unit(operator, {}, False, False))
                excluded.append((operator.obj_id, "not controlled by this seat"))
            continue
        f = operator.fields
        enemies.append(Enemy(obj_id=operator.obj_id, type=operator.unit_type,
                             sub_type=operator.sub_type if operator.sub_type is not None else -1,
                             hex=operator.cur_hex, path=tuple(operator.move_path or ()), speed=F.number(f.get("speed")),
                             basic_speed=F.number(f.get("basic_speed")), blood=F.number(f.get("blood")),
                             value=F.number(f.get("value")), weapons=tuple(sorted(_ints(f.get("carry_weapon_ids"))))))
    passengers: List[Unit] = []
    for operator in sorted(observation.passengers(), key=lambda u: u.obj_id):
        if operator.color == faction and operator.obj_id in controllable:
            passengers.append(_unit(operator, valid.get(operator.obj_id, {}), True, True))
    present = on_map | {p.obj_id for p in passengers}
    excluded.extend((obj_id, "listed for the seat but not observed") for obj_id in sorted(controllable - present))
    objectives = []
    for city in sorted(observation.cities() or (), key=lambda c: c.coord):
        objectives.append(Objective(hex=city.coord, value=float(city.value or 0), flag=city.flag,
                                    zone=F.zone(city.coord, rows, cols)))
    impacts = []
    for point in observation.fields.get("jm_points") or ():
        if isinstance(point, Mapping) and F.is_int(point.get("pos")):
            impacts.append((int(point["pos"]), int(point.get("status")) if F.is_int(point.get("status")) else -1,
                            F.number(point.get("boom_time")) + F.number(point.get("fly_time"))))
    max_step = time_info.max_step if time_info.max_step else (time_info.max_time or 0)
    return World(
        seat=seat, faction=faction, stage=time_info.stage, step=time_info.cur_step, max_step=int(max_step),
        rows=rows, cols=cols, units=tuple(units), passengers=tuple(passengers), allies=tuple(allies),
        enemies=tuple(enemies), objectives=tuple(objectives), roadblocks=frozenset(observation.roadblocks() or ()),
        impact_points=tuple(sorted(impacts)), excluded=tuple(sorted(excluded)),
    )


def is_play(world: World) -> bool:
    return world.stage == Stage.PLAY
