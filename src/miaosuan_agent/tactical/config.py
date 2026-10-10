"""Named configurations of the Sprint 36 tactical agent (``docs/SPRINT36_TACTICAL_RECOVERY.md`` sections 6 to 10).

Three architectures, each a new identity; the frozen Sprint 34 package ``integrated`` and Sprint 35 package
``coalition`` are imported and never edited:

* ``TA`` survival-aware defence and opportunity-aware capture on the Sprint 35 coalition architecture (stances,
  coalition allocator, Sprint 34 fire and transport);
* ``TB`` mission coordination: ``TA`` plus a mobile reserve at threatened held objectives, counterattack priority for
  objectives lost recently, stance-driven artillery support with arrival fire, guided fire and transport only to
  objectives without a known threat (the Sprint 35 mission-planner features);
* ``TC`` the Sprint 34 mission orchestrator (``S34-MO``) unchanged, with a survival guard applied to its decision: no
  valuable unit is sent into, or kept in, a zone the guard judges untenable, and the guard's withdrawal moves are routed
  through the same traffic ledger. With the guard off ``TC`` decides exactly as ``S34-MO`` (a tested property).

Every number is a design choice stated with its reason in the report (section 6 and 7) or calibrated on recorded
games (section 7.2); none was tuned on a Sprint 36 engine outcome (there is none).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict

from ..coalition.config import CA, CM, CoalitionConfig
from ..integrated.config import MO, Config


@dataclass(frozen=True)
class TacticalConfig:
    name: str
    #: "stances" (TA, TB: the stance planner drives the allocation) or "guard" (TC: Sprint 34's allocation, guarded).
    architecture: str
    coalition: CoalitionConfig = CA
    revision: int = 1
    # -- threat reading (section 7.2) ------------------------------------------------------------------------------
    #: An enemy ground unit seen standing on the same hex without a move path for at least this many steps, outside
    #: the zone being assessed, is static: it neither blocks nor contests that zone (one 75-step arrival transition;
    #: recorded baseline-v2 units never stood still outside an objective zone for more than one step in 40 games).
    static_steps: int = 75
    static_filter: bool = True
    # -- capture (section 7) -----------------------------------------------------------------------------------------
    #: Opportunity capture: with no enemy in the zone, a free unit arriving at least ``race_margin`` steps before every
    #: contesting enemy's optimistic arrival is sent without a coalition (first ownership before contact).
    opportunity_capture: bool = True
    race_margin: int = 10
    # -- defence (section 6) -----------------------------------------------------------------------------------------
    #: A unit is cheap when its value is at most this share of the highest value among the side's mobile ground units
    #: (tank 10 -> squads 4, unmanned ground vehicles 5); a cheap unit may be the delaying holder.
    cheap_share: float = 0.5
    #: "survival" (Sprint 36: one cheap delaying holder, the others withdraw) or "legacy" (Sprint 35's delay stance,
    #: kept for the equivalence test of ``ta-as-ca``).
    defence: str = "survival"
    #: Untenable held objective: keep one cheap holder to deny occupation; withdraw the others.
    delay_holder: bool = True
    withdrawal: bool = True
    #: Withdrawal needs the contact to be at least this many steps away (time to leave the zone before fire).
    withdraw_lead: int = 40
    #: Withdrawal needs at least this share of the threat to be visible now (Sprint 35's rule, kept).
    withdraw_visible_share: float = 0.5
    #: A withdrawing unit's fallback hex is at least this many hexes farther from every visible threat member than the
    #: unit is now (contact is broken, not escaped: tank weapons reach 18 to 20 hexes).
    safe_margin: int = 2
    #: Held objective with nobody standing in its zone and a known threat: a cheap free unit arriving before the enemy
    #: takes one delaying place.
    empty_holder: bool = True
    #: In the last ``end_window`` steps every defender of a held objective stays (the final ownership is scored).
    end_window: int = 300
    # -- mission coordination (TB) -------------------------------------------------------------------------------------
    #: Objectives lost within this many steps get a counterattack bonus on their coalition places.
    counterattack_window: int = 600
    counterattack_bonus: float = 0.25
    # -- guard (TC) -------------------------------------------------------------------------------------------------
    guard: bool = True
    #: The guard keeps the units the assessment keeps in a held objective's zone (Sprint 35's retention, applied to
    #: Sprint 34's moves).
    retention: bool = True


TA = TacticalConfig(name="survival-capture", architecture="stances", coalition=CA)
TB = TacticalConfig(name="mission-coordinator", architecture="stances",
                    coalition=replace(CM, name="coalition-mission-planner"), counterattack_bonus=0.25)
TC = TacticalConfig(name="guarded-orchestrator", architecture="guard", coalition=replace(CA, base=MO))

_NO_TRANSPORT_BASE: Config = replace(MO, name="mission-orchestrator-no-transport", transport=False)
_NO_ARTILLERY_BASE: Config = replace(MO, name="mission-orchestrator-no-artillery", artillery=False)
_NO_TRAFFIC_BASE: Config = replace(MO, name="mission-orchestrator-no-traffic-repair", recovery=False, dispersal=False)

ABLATIONS: Dict[str, TacticalConfig] = {
    "ta-no-delay-holder": replace(TA, name="ta-no-delay-holder", delay_holder=False, empty_holder=False),
    "ta-no-withdrawal": replace(TA, name="ta-no-withdrawal", withdrawal=False),
    "ta-no-static-filter": replace(TA, name="ta-no-static-filter", static_filter=False),
    "ta-r1-attribution": replace(TA, name="ta-r1-attribution",
                                 coalition=replace(CA, revision=1, attribution="first")),
    "ta-no-opportunity-capture": replace(TA, name="ta-no-opportunity-capture", opportunity_capture=False),
    "ta-no-coalition-capture": replace(TA, name="ta-no-coalition-capture",
                                       coalition=replace(CA, coalition_capture=False)),
    "ta-no-end-window": replace(TA, name="ta-no-end-window", end_window=0),
    "ta-no-traffic-repair": replace(TA, name="ta-no-traffic-repair", coalition=replace(CA, base=_NO_TRAFFIC_BASE)),
    "tb-no-reserve": replace(TB, name="tb-no-reserve", coalition=replace(TB.coalition, reserve=False)),
    "tb-no-artillery": replace(TB, name="tb-no-artillery", coalition=replace(TB.coalition, base=_NO_ARTILLERY_BASE)),
    "tb-no-transport": replace(TB, name="tb-no-transport", coalition=replace(TB.coalition, base=_NO_TRANSPORT_BASE)),
    "tb-no-guided-fire": replace(TB, name="tb-no-guided-fire", coalition=replace(TB.coalition, guided_fire=False)),
    "tb-no-counterattack": replace(TB, name="tb-no-counterattack", counterattack_bonus=0.0),
    "tc-no-guard": replace(TC, name="tc-no-guard", guard=False),
    "tc-no-withdrawal": replace(TC, name="tc-no-withdrawal", withdrawal=False),
    "tc-no-retention": replace(TC, name="tc-no-retention", retention=False),
    #: TA with every Sprint 36 change switched off: must decide as Sprint 35's CA (a tested property).
    "ta-as-ca": replace(TA, name="ta-as-ca", defence="legacy", static_filter=False, opportunity_capture=False,
                        empty_holder=False, end_window=0),
}
VARIANTS: Dict[str, TacticalConfig] = {"TA": TA, "TB": TB, "TC": TC, **ABLATIONS}
#: No candidate is frozen until the registered offline selection has run (section 15).
LIVE = None
