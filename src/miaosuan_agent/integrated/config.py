"""Named configurations of the integrated agent: the two architectural variants and their offline ablations.

A configuration is frozen code, covered by the candidate's policy source digest; the live candidate is exactly one of
them (``LIVE``), chosen offline before any engine result of Sprint 34 was seen. Every number below is a design choice
stated in ``docs/SPRINT34_INTEGRATED_AGENT.md`` section 6 with its reason; none was tuned on engine outcomes.

Variant A, ``capacity-traffic`` (CT): whole-force maximum-utility matching of mobile ground units to objective slots
(Hungarian, exact), capacity-capped destinations and traffic-closed hexes, retention through hold slots with
persistence, aircraft support, ``baseline-v2``'s fire ranking.

Variant B, ``mission-orchestrator`` (MO): the same capacity and traffic core with a greedy allocator that also allocates
infantry-carrier lift pairs (transport), economic holder preference, threat-aware route costs, guarded indirect fire
with own-route exclusion, and a fire tie-break toward the target with the least remaining strength.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Tuple


@dataclass(frozen=True)
class Config:
    name: str
    solver: str                     # "hungarian" | "greedy"
    transport: bool
    artillery: bool
    threat_routing: bool
    economic_holders: bool
    fire_blood_tiebreak: bool
    recovery: bool = True
    #: Surplus units with no slot step off a full objective hex into its zone.
    dispersal: bool = True
    #: Utility points lost per step of travel (an 80-point objective stays worth taking at 2,000 steps).
    time_cost: float = 0.01
    #: Slot weights (fraction of the objective's value) for the k-th unit sent to an objective not held.
    capture_contested: Tuple[float, ...] = (1.0, 0.5, 0.3)
    capture_clear: Tuple[float, ...] = (1.0, 0.15)
    #: Hold slot weights for a held objective: first holder when a known enemy can reach it before the end, first
    #: holder otherwise, second unit while contested.
    hold_threatened: float = 0.9
    hold_quiet: float = 0.35
    reinforce: float = 0.35
    #: Bonus for keeping a unit's current task target or the objective it stands on (persistence).
    stickiness: float = 6.0
    #: Economic holder bonus per point of unit value below the force's highest value (variant B).
    economy_per_value: float = 0.6
    infantry_holder_bonus: float = 4.0
    #: Most own ground units planned to stand on one objective hex (one below the stacking limit keeps it passable).
    destination_cap: int = 3
    #: Steps of slack required between a planned arrival and the end of the game.
    arrival_margin: int = 20
    #: A known enemy ground unit within this many hexes of an objective makes it contested.
    contest_radius: int = 4
    #: Known enemies further than this are ignored in an objective's threat.
    threat_radius: int = 14
    #: Extra route cost (cost units) per visible enemy whose published range covers a hex (variant B).
    threat_cost: float = 1.5
    threat_cost_cap: float = 6.0
    #: A lift must beat walking by this many steps.
    lift_gain: int = 150
    #: A passenger is not offered a new lift within this many steps of its previous embark order.
    lift_cooldown: int = 600
    #: Indirect fire: no impact within this many hexes of an own ground unit, its remaining path or a planned stand.
    artillery_clearance: int = 2


CT = Config(name="capacity-traffic", solver="hungarian", transport=False, artillery=False, threat_routing=False,
            economic_holders=False, fire_blood_tiebreak=False)
MO = Config(name="mission-orchestrator", solver="greedy", transport=True, artillery=True, threat_routing=True,
            economic_holders=True, fire_blood_tiebreak=True)

ABLATIONS: Dict[str, Config] = {
    "mo-no-transport": replace(MO, name="mo-no-transport", transport=False),
    "mo-no-artillery": replace(MO, name="mo-no-artillery", artillery=False),
    "mo-no-threat-routing": replace(MO, name="mo-no-threat-routing", threat_routing=False),
    "mo-no-economy": replace(MO, name="mo-no-economy", economic_holders=False),
    "mo-no-recovery": replace(MO, name="mo-no-recovery", recovery=False),
    "ct-greedy": replace(CT, name="ct-greedy", solver="greedy"),
    "mo-hungarian-no-transport": replace(MO, name="mo-hungarian-no-transport", solver="hungarian", transport=False),
}
VARIANTS: Dict[str, Config] = {"CT": CT, "MO": MO, **ABLATIONS}
