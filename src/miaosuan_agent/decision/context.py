"""Tactical context: the project-owned facts one decision step works from.

Built only from canonical boundary objects. Every collection is sorted by an explicit key, so
nothing downstream depends on the order in which the engine delivered fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Mapping, Optional, Tuple

from ..boundary import City, ContractError, Observation, deployment_completion_available
from ..boundary.observation import ActionOptions


@dataclass(frozen=True)
class UnitContext:
    obj_id: int
    cur_hex: int
    unit_type: int
    move_state: Optional[int]
    move_path: Tuple[int, ...]
    actions: Mapping[int, ActionOptions]


@dataclass(frozen=True)
class TacticalContext:
    seat: int
    faction: int
    stage: int
    cur_step: int
    deployment_available: bool
    units: Tuple[UnitContext, ...]
    objectives: Tuple[City, ...]
    roadblocks: FrozenSet[int]
    excluded: Tuple[Tuple[int, str], ...]

    @property
    def unit_ids(self) -> FrozenSet[int]:
        return frozenset(unit.obj_id for unit in self.units)

    def unit(self, obj_id: int) -> Optional[UnitContext]:
        for unit in self.units:
            if unit.obj_id == obj_id:
                return unit
        return None


def build_context(observation: Observation, seat: int, faction: int) -> TacticalContext:
    """Controllable units, objectives not held by ``faction``, and roadblocks for one step.

    A unit is controllable when the seat's ``role_and_grouping_info`` entry lists it and it is on
    the map in this view with the seat's colour. Listed units that are absent (for example
    passengers), visible units of the seat's colour that the seat does not control, and units that
    ``valid_actions`` lists without being controllable are recorded in ``excluded``; enemy units
    are simply not candidates. A seat whose recorded faction differs from ``faction`` is a contract
    violation.
    """
    time_info = observation.time()
    seat_info = observation.seat(seat)
    if seat_info.faction is not None and seat_info.faction != faction:
        raise ContractError(f"{observation.path}.role_and_grouping_info[{seat}].faction",
                            f"the faction given at setup ({faction})", seat_info.faction)
    controllable = set(seat_info.operators)
    valid = observation.valid_actions()
    units = []
    excluded = []
    on_map = set()
    for operator in sorted(observation.operators(), key=lambda unit: unit.obj_id):
        on_map.add(operator.obj_id)
        if operator.color != faction:
            continue
        if operator.obj_id not in controllable:
            excluded.append((operator.obj_id, "not controlled by this seat"))
            continue
        units.append(UnitContext(
            obj_id=operator.obj_id, cur_hex=operator.cur_hex, unit_type=operator.unit_type,
            move_state=operator.move_state, move_path=operator.move_path or (),
            actions=valid.get(operator.obj_id, {}),
        ))
    excluded.extend((obj_id, "listed for the seat but not on the map") for obj_id in sorted(controllable - on_map))
    accounted = {unit.obj_id for unit in units} | {obj_id for obj_id, _ in excluded}
    excluded.extend((obj_id, "listed in valid_actions but not a controllable unit")
                    for obj_id in sorted(set(valid) - accounted))
    objectives = tuple(sorted((city for city in (observation.cities() or ()) if city.flag != faction),
                              key=lambda city: city.coord))
    return TacticalContext(
        seat=seat, faction=faction, stage=time_info.stage, cur_step=time_info.cur_step,
        deployment_available=deployment_completion_available(observation, seat),
        units=tuple(units), objectives=objectives,
        roadblocks=frozenset(observation.roadblocks() or ()),
        excluded=tuple(sorted(excluded)),
    )
