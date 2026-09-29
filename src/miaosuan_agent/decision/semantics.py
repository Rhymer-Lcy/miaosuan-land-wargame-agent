"""Evidence-backed semantics of the SDK actions the baseline may emit.

Only four action types are catalogued: the ones the baseline uses. Each entry records what the
action means, which fields it needs, how its legality is established, and where that knowledge
comes from. Sources, in priority order: runtime observation of engine 4.1.0 (``docs/CONTRACT.md``),
the current public platform documentation (actions, observations and rules pages, read
2026-09-29), and the SDK's bundled material, which is not redistributed.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import FrozenSet, Mapping, Tuple

from ..boundary import END_DEPLOYMENT, Stage


class ActionType(enum.IntEnum):
    MOVE = 1
    SHOOT = 2
    OCCUPY = 5
    END_DEPLOYMENT = END_DEPLOYMENT


class Legality(enum.Enum):
    VALID_ACTIONS = "listed for the unit in the current valid_actions"
    DEPLOYMENT_EXCEPTION = "documented as absent from valid_actions; available while deploying"


class Parameters(enum.Enum):
    NONE = "no parameters"
    OPTION = "copied from one option reported in valid_actions"
    CONSTRUCTED_PATH = "path of adjacent hexes built from the setup cost graph"


@dataclass(frozen=True)
class ActionSemantics:
    action_type: ActionType
    meaning: str
    unit_level: bool
    fields: Tuple[str, ...]
    option_fields: Tuple[str, ...]
    legality: Legality
    parameters: Parameters
    stages: FrozenSet[int]
    persistence: str
    evidence: Tuple[str, ...]
    uncertainty: str

    @property
    def keys(self) -> FrozenSet[str]:
        """The exact key set of an emitted action."""
        return frozenset(("actor", "type") + (("obj_id",) if self.unit_level else ()) + self.fields)


#: Lowest attack level with a documented effect: the result tables start at level 1.
MIN_ATTACK_LEVEL = 1

CATALOG: Mapping[ActionType, ActionSemantics] = {
    ActionType.END_DEPLOYMENT: ActionSemantics(
        action_type=ActionType.END_DEPLOYMENT,
        meaning="end the seat's deployment stage",
        unit_level=False, fields=(), option_fields=(),
        legality=Legality.DEPLOYMENT_EXCEPTION, parameters=Parameters.NONE,
        stages=frozenset({Stage.DEPLOYMENT}),
        persistence="instantaneous; the seat's end_deployment flag becomes True",
        evidence=("public documentation: valid_actions excludes deployment actions, naming end of deployment",
                  "runtime 4.1.0: accepted from both seats; stage 1 -> 2 and end_deployment False -> True"),
        uncertainty="none observed",
    ),
    ActionType.MOVE: ActionSemantics(
        action_type=ActionType.MOVE,
        meaning="move a unit along a planned path of hexes",
        unit_level=True, fields=("move_path",), option_fields=(),
        legality=Legality.VALID_ACTIONS, parameters=Parameters.CONSTRUCTED_PATH,
        stages=frozenset({Stage.PLAY}),
        persistence=("persistent: executed hex by hex; once issued it cannot be changed, only stopped "
                     "(action 10) with a 75 s penalty"),
        evidence=("public documentation: action schema (move_path: list of int); observation move_path "
                  "(first element is the next target hex); movement rules",
                  "runtime 4.1.0: valid_actions lists type 1 with value None for movable units",
                  "SDK demo agent (not redistributed): builds move_path from the cost graph, excluding the "
                  "start hex, and maps vehicle / march / infantry / air to cost modes 0 / 1 / 2 / 3"),
        uncertainty=("acceptance of constructed paths by the engine is established by the real-engine "
                     "validation; the mode for vehicles in march state rests on the demo agent"),
    ),
    ActionType.SHOOT: ActionSemantics(
        action_type=ActionType.SHOOT,
        meaning="direct fire at a target with a weapon",
        unit_level=True, fields=("target_obj_id", "weapon_id"),
        option_fields=("target_obj_id", "weapon_id", "attack_level"),
        legality=Legality.VALID_ACTIONS, parameters=Parameters.OPTION,
        stages=frozenset({Stage.PLAY}),
        persistence="instantaneous; the weapon then cools for 75 s",
        evidence=("public documentation: action schema; valid_actions option fields; direct-fire rules "
                  "(target observed and in range, weapon unfolded and cooled, shooter stopped except tank "
                  "main guns); attack-level tables start at level 1",),
        uncertainty="attack levels below 1 have no documented effect and are not used",
    ),
    ActionType.OCCUPY: ActionSemantics(
        action_type=ActionType.OCCUPY,
        meaning="take control of the objective the unit stands on",
        unit_level=True, fields=(), option_fields=(),
        legality=Legality.VALID_ACTIONS, parameters=Parameters.NONE,
        stages=frozenset({Stage.PLAY}),
        persistence="instantaneous (no waiting time)",
        evidence=("public documentation: action schema; valid_actions lists it with value None; occupation "
                  "rules (unit at the objective centre, no enemy ground unit in it or its six neighbours; "
                  "not for air units or artillery)",),
        uncertainty="not yet observed at runtime before the baseline evaluation",
    ),
}
