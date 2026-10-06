"""ANALYSIS-SIDE shadows of Sprint 16 (``docs/SPRINT16_MECHANISM_CAPTURE.md``): identity ``s16-delayed-shadow-v6``.

Not a policy. Nothing here can act in an engine: the module defines no policy, agent or add-on class, appears in no run
card, and is evaluated only on recorded observations after the fact. It restates the six Sprint 15 delayed rules
(``experiments/t9_delayed.py``, identity ``t9-<rule>-v5``, frozen and unchanged) under one correction of their memory,
the one disclosed in Sprint 15's results (section R7) and implemented post hoc in ``scripts/s15_posthoc.py``:

* frozen v5: a unit observed standing on ANY objective loses its record;
* v6: a unit observed standing on an objective ends its record only when the side does NOT hold that objective. A unit
  standing on an objective its side holds keeps its record; ``baseline-v2`` never orders a unit standing on an
  objective the side does not hold, so such a unit is a deferred claimant, not a committed one.

Every other memory transition, every trigger, the allocation (Sprint 14's ``feasible-value-redirect`` restricted to
eligible overflow claimants, on v3's stage 1) and the fail-closed behaviour are the frozen v5 code, called unchanged:
:func:`allocate` runs :func:`observe` (the corrected update) and then ``t9_delayed._allocate_or_fail``. With no
claimant eligible the result equals v3 (``t9_batch.allocate``) exactly; that identity is what makes a recorded v3 game
a shadow's own trajectory until the shadow's first different action.

The module imports nothing from the analysis or the engine (seat-local): its inputs are the observation, seat, faction,
``baseline-v2``'s actions, the router, the rule and the memory.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from ..decision.routing import Router
from ..experiments import t9_delayed as td

SHADOW_ID = "s16-delayed-shadow-v6"
#: The six frozen Sprint 15 triggers, unchanged (declared order of simplicity).
RULES: Dict[str, td.DelayedRule] = dict(td.RULES)
#: The scientific target of Sprint 16: the only Sprint 15 trigger that restored post-opening redistribution as red.
TARGET = "delayed-post-stage-any"
#: Record-ending reasons of :func:`observe` (the second is the corrected condition).
ABSENT, MOVING, STANDING_UNHELD, SOURCE_HELD = ("absent", "moving to an objective",
                                                "standing on an objective the side does not hold",
                                                "source held by the side")


def identity(name: str) -> str:
    """The analysis identity of one shadow rule (never a policy identity)."""
    return f"s16-{name}-shadow-v6"


def observe(observation: Observation, faction: int, records: Dict[int, List[int]]) -> Dict[int, str]:
    """``t9_delayed.observe`` with the corrected record-ending condition (in place); returns the ended records'
    reasons. The only difference from v5 is the third branch: standing on an objective ends the record only when the
    side does not hold that objective."""
    ended: Dict[int, str] = {}
    own = {u.obj_id: u for u in observation.operators() if u.color == faction and u.unit_type in td.GROUND}
    cities = {c.coord: c for c in (observation.cities() or ())}
    for unit_id in sorted(records):
        record = records[unit_id]
        unit = own.get(unit_id)
        path = tuple(unit.move_path or ()) if unit is not None else ()
        if unit is None:
            reason = ABSENT
        elif path and path[-1] in cities:
            reason = MOVING
        elif not path and unit.cur_hex in cities and cities[unit.cur_hex].flag != faction:
            reason = STANDING_UNHELD
        else:
            reason = None
        if reason is not None:
            ended[unit_id] = reason
            del records[unit_id]
            continue
        if record[td.SOURCE] in cities and cities[record[td.SOURCE]].flag == faction:
            # the episode ends with its source; what the unit itself did (a completed staging move) is kept
            ended[unit_id] = SOURCE_HELD
            for index in (td.SOURCE, td.COUNT, td.ALTERNATIVE, td.SATURATED, td.REDIRECTED, td.FIRST):
                record[index] = 0
        if record[td.STAGED] and not path and unit.cur_hex == record[td.STAGED]:
            record[td.DONE] = 1
        if not any(record):
            del records[unit_id]
    return ended


def allocate(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, object]],
             router: Optional[Router], rule: Optional[td.DelayedRule],
             memory: Sequence[Sequence[int]] = ()) -> td.Allocation:
    """One shadow decision: the corrected memory update, then the frozen v5 allocation. ``rule`` None: nobody is
    eligible (equals v3)."""
    actions = tuple(actions)
    records, errors = td.decode(memory)
    if observation.time().stage != Stage.PLAY:
        return td.Allocation(actions, td.encode(records))
    try:
        ended = observe(observation, faction, records)
    except ContractError:
        raise
    except Exception:  # noqa: BLE001 - memory that cannot be updated is forgotten: no redirect can follow from it
        errors.append("memory update failed")
        ended = {unit_id: "memory update failed" for unit_id in records}
        records = {}
    return td._allocate_or_fail(observation, seat, faction, actions, router, rule, records, ended, errors, False)


def shadow_rules() -> Tuple[Tuple[str, str, str, int, bool], ...]:
    """(name, identity, trigger, count, same_source) of every shadow, for the frozen inputs."""
    return tuple((name, identity(name), r.trigger, r.count, r.same_source) for name, r in RULES.items())
