"""Named configurations of the coalition agent: the two Sprint 35 architectures and their ablations.

Both architectures run on the Sprint 34 mission-orchestrator configuration (``integrated.config.MO``: greedy whole-force
allocation, lifts, guarded indirect fire, threat-aware routes, economic holders, the friendly-traffic ledger) and change
how objectives are assessed and served (``coalition.coalition``). Every number below is a design choice stated with its
reason in ``docs/SPRINT35_COALITION_AGENT.md`` section 7; the class weights come from recorded engine games
(``evaluation/s35-coalition-agent/capability.json``); none was tuned on a Sprint 35 engine outcome.

Variant A, ``coalition-allocator`` (CA): capability-weighted threat and defence estimates per objective, stances
(quiet hold, secure, defend with reinforcement deadlines, delay with justified withdrawal, coalition capture, skip),
last-defender retention, a small mobile reserve at threatened held objectives. Sprint 34's fire and transport unchanged.

Variant B, ``coalition-mission-planner`` (CM): variant A plus fire support tied to the stances (indirect fire first at
enemies threatening a held objective, and at the destination of an enemy whose arrival falls inside the impact window),
guided fire where the engine lists it, and transport limited to objectives without a known threat.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Mapping, Tuple

from ..integrated.config import MO, Config

#: Relative direct-fire capability by sub_type, from the damage dealt per 1,000 alive unit-steps in the 24 Sprint 34
#: live games (tank 2.2945, infantry fighting vehicle 0.5593, unmanned ground vehicle 0.4242, squad 0.0886, other ground
#: classes 0.3861), divided by the tank's and rounded to 0.05. A floor keeps every ground unit worth something: any own
#: ground unit in a zone prevents the enemy's occupation.
CLASS_WEIGHT: Mapping[int, float] = {0: 1.0, 1: 0.25, 2: 0.05, 4: 0.2}
OTHER_WEIGHT = 0.15
FLOOR_WEIGHT = 0.05


@dataclass(frozen=True)
class CoalitionConfig:
    name: str
    base: Config = MO
    #: Revision of the identity: 1 registered first; 2 corrects the threat attribution after revision 1 failed its
    #: registered gate G9 (docs/SPRINT35_COALITION_AGENT.md section 10).
    revision: int = 2
    #: Threat attribution: "unheld" (revision 2) or "first" (revision 1), see ``capability.attribute``.
    attribution: str = "unheld"
    #: A held objective is secure when its defenders' power is at least ``defend_ratio`` times the threat.
    defend_ratio: float = 1.0
    #: Reinforcement is committed only if defenders plus reachable reinforcements reach ``commit_ratio`` times the threat.
    commit_ratio: float = 0.6
    #: A contested objective not held is attacked only by a coalition reaching ``capture_ratio`` times its threat.
    capture_ratio: float = 1.2
    #: Known enemies whose optimistic arrival at a zone is later than this many steps are not part of its threat.
    threat_horizon: int = 600
    #: Remembered sightings lose confidence linearly over this many steps (Sprint 34's sighting lifetime).
    sighting_ttl: int = 600
    #: A reinforcement may arrive this many steps after the enemy's optimistic arrival (median time from the first
    #: enemy ground unit in the zone to the loss in Sprint 34's 57 losses: 41 steps).
    deadline_grace: int = 40
    #: A downgrade of a stance (defend -> delay) waits this many steps after the stance was set; upgrades are immediate.
    stance_dwell: int = 75
    #: Withdrawal needs at least this share of the threat to come from enemies visible now.
    withdraw_visible_share: float = 0.5
    #: Reserve places (beyond the requirement) offered at each threatened held objective, and their slot weight.
    reserve_places: int = 2
    reserve_weight: float = 0.25
    #: Weight of a reinforcement or coalition place (fraction of the objective's value).
    reinforce_weight: float = 1.0
    coalition_weights: Tuple[float, ...] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
    #: Variant B features (each its own gate).
    fire_support: bool = False
    arrival_fire: bool = False
    guided_fire: bool = False
    safe_transport: bool = False
    #: Arrival fire: the enemy's free-flow arrival at its path end must fall in [flight, flight + window) steps.
    arrival_window: int = 225
    #: Ablation switches of the variant A core.
    retention: bool = True
    withdrawal: bool = True
    reinforcement: bool = True
    coalition_capture: bool = True
    reserve: bool = True


CA = CoalitionConfig(name="coalition-allocator")
CM = CoalitionConfig(name="coalition-mission-planner", fire_support=True, arrival_fire=True, guided_fire=True,
                     safe_transport=True)

ABLATIONS: Dict[str, CoalitionConfig] = {
    "ca-no-retention": replace(CA, name="ca-no-retention", retention=False),
    "ca-no-withdrawal": replace(CA, name="ca-no-withdrawal", withdrawal=False),
    "ca-no-reinforcement": replace(CA, name="ca-no-reinforcement", reinforcement=False),
    "ca-no-coalition-capture": replace(CA, name="ca-no-coalition-capture", coalition_capture=False),
    "ca-no-reserve": replace(CA, name="ca-no-reserve", reserve=False),
    "cm-no-fire-support": replace(CM, name="cm-no-fire-support", fire_support=False, arrival_fire=False),
    "cm-no-arrival-fire": replace(CM, name="cm-no-arrival-fire", arrival_fire=False),
    "cm-no-guided-fire": replace(CM, name="cm-no-guided-fire", guided_fire=False),
    "cm-no-safe-transport": replace(CM, name="cm-no-safe-transport", safe_transport=False),
    "cm-no-transport": replace(CM, name="cm-no-transport", base=replace(MO, name="mission-orchestrator-no-transport",
                                                                          transport=False)),
    "ca-r1-attribution": replace(CA, name="ca-r1-attribution", revision=1, attribution="first"),
    "cm-r1-attribution": replace(CM, name="cm-r1-attribution", revision=1, attribution="first"),
}
VARIANTS: Dict[str, CoalitionConfig] = {"CA": CA, "CM": CM, **ABLATIONS}
