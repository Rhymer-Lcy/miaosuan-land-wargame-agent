"""Synthetic play-stage situations for the decision tests. SYNTHETIC: nothing here is SDK data.

Built on :mod:`tests.fixtures.synthetic`: invented unit ids (900000 range), seats 7 and 17, a
10 x 10 map with the documented hex numbering and neighbour layout, invented weapon ids.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision.context import TacticalContext, build_context

from . import synthetic as syn

RED, BLUE = 0, 1
INFANTRY, VEHICLE, AIRCRAFT = 1, 2, 3
UNIT_A, UNIT_B, UNIT_C, UNIT_D = 900101, 900102, 900103, 900104
UNCONTROLLED, NOT_ON_MAP, ONLY_LISTED = 900109, 900110, 900111
ENEMY_A, ENEMY_B = 900201, 900202
GUN, MISSILE = 43, 71


def shoot(target: int, weapon: int, level: int) -> Dict[str, int]:
    return {"target_obj_id": target, "weapon_id": weapon, "attack_level": level}


def play_observation(units: Sequence[Dict[str, Any]], valid_actions: Mapping[int, Any], *,
                     cities: Optional[Sequence[Dict[str, Any]]] = None, roadblocks: Sequence[int] = (),
                     controlled: Optional[Sequence[int]] = None, stage: int = 2, cur_step: int = 5,
                     seat: int = syn.RED_SEAT, faction: int = RED, ended: bool = True) -> Dict[str, Any]:
    """An observation for ``seat``; by default the seat controls every visible unit of its faction."""
    if controlled is None:
        controlled = [u["obj_id"] for u in units if u["color"] == faction]
    seats = {seat: syn.seat_record(seat, faction, controlled, ended)}
    return syn.build_observation(units=units, valid_actions=valid_actions, seats=seats, stage=stage,
                                 cur_step=cur_step, cities=cities, roadblocks=roadblocks)


def costs(cost: float = 1, entry_costs: Optional[Mapping[int, float]] = None) -> MoveCosts:
    return MoveCosts.from_raw(syn.cost_data(cost=cost, entry_costs=entry_costs))


def context_of(raw: Mapping[str, Any], seat: int = syn.RED_SEAT, faction: int = RED,
               origin: Origin = Origin.ENGINE) -> TacticalContext:
    return build_context(Observation.from_raw(raw, origin), seat, faction)


def rich_observation() -> Dict[str, Any]:
    """Several units exercising every rule and tie-break at once.

    * A (vehicle, 102): three shoot options tie at level 3 -> target ENEMY_A, weapon GUN;
    * B (vehicle, 505): stands on the unheld objective with occupy listed -> occupy;
    * C (infantry, 707): movement only -> nearest unheld objective (505) through a roadblock;
    * D (vehicle, 808): executing a move -> nothing;
    * an own-colour unit the seat does not control, a listed unit absent from the map, and a unit
      listed only in ``valid_actions`` -> excluded; two visible enemy units.
    """
    units = [
        syn.unit(UNIT_A, RED, 102, unit_type=VEHICLE),
        syn.unit(UNIT_B, RED, 505, unit_type=VEHICLE),
        syn.unit(UNIT_C, RED, 707, unit_type=INFANTRY),
        syn.unit(UNIT_D, RED, 808, unit_type=VEHICLE, move_path=(807, 806)),
        syn.unit(UNCONTROLLED, RED, 909, unit_type=VEHICLE),
        syn.unit(ENEMY_A, BLUE, 304, unit_type=VEHICLE),
        syn.unit(ENEMY_B, BLUE, 305, unit_type=INFANTRY),
    ]
    valid = {
        UNIT_A: {1: None, 2: [shoot(ENEMY_B, MISSILE, 3), shoot(ENEMY_A, GUN, 3), shoot(ENEMY_A, MISSILE, 3),
                              shoot(ENEMY_B, GUN, 2), shoot(ENEMY_A, GUN, 0)]},
        UNIT_B: {1: None, 5: None},
        UNIT_C: {1: None},
        UNIT_D: {1: None},
        ONLY_LISTED: {1: None},
    }
    cities = [syn.city(505, flag=-1), syn.city(202, flag=BLUE), syn.city(909, flag=RED)]
    return play_observation(units, valid, cities=cities, roadblocks=(606, 706),
                            controlled=[UNIT_A, UNIT_B, UNIT_C, UNIT_D, NOT_ON_MAP])


def reordered(raw: Mapping[str, Any], key: int) -> Dict[str, Any]:
    """The same observation with every order the contract does not define changed.

    ``key`` selects one of several deterministic permutations (reversals and rotations) of the
    operator list, both key levels of ``valid_actions``, option lists, cities, roadblocks and the
    seat's operator list.
    """
    def permute(items: List[Any]) -> List[Any]:
        if not items:
            return items
        shift = key % len(items)
        rotated = items[shift:] + items[:shift]
        return rotated[::-1] if key % 2 else rotated

    def fields(mapping: Mapping[Any, Any]) -> Dict[Any, Any]:
        return {name: mapping[name] for name in permute(list(mapping))}

    def options(value: Any) -> Any:
        return [fields(option) for option in permute(list(value))] if isinstance(value, list) else value

    obs = copy.deepcopy(dict(raw))
    obs["operators"] = [fields(unit) for unit in permute(obs["operators"])]
    obs["cities"] = [fields(city) for city in permute(obs["cities"])]
    obs["landmarks"]["roadblocks"] = permute(obs["landmarks"]["roadblocks"])
    obs["valid_actions"] = {obj_id: {t: options(per_unit[t]) for t in permute(list(per_unit))}
                            for obj_id, per_unit in fields(obs["valid_actions"]).items()}
    for record in obs["role_and_grouping_info"].values():
        record["operators"] = permute(record["operators"])
    return fields(obs)
