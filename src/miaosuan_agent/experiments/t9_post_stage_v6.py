"""EXPLORATORY engine candidate ``t9-delayed-post-stage-any-v6`` (Sprint 17, ``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``).

Exploratory track: not eligible for promotion and never packaged. Its only authorized use is the two-game registered
mechanism probe of Sprint 17 (card ``s17-post-stage-v6-probe-1``); any other engine use needs new owner approval.

It is the executable form of Sprint 16's analysis-side target shadow ``s16-delayed-post-stage-any-shadow-v6``
(``evaluation/s16_shadow.py``) and adds no tactical condition to it. ``baseline-v2`` decides first, unchanged
(:mod:`.exploratory_addon`); one decision is then allocated by:

1. frozen v3's stage 1 (``t9_batch``: counted incumbents, claimants ranked by free-flow time, places by rank),
   computed inside the frozen Sprint 15 allocation, which restates it unchanged;
2. Sprint 16's corrected deferred-history memory: :func:`observe` below is the Sprint 16 shadow's ``observe``, copied
   verbatim (a test compares the two function bodies), so that the candidate's source set holds no analysis module.
   The one difference from the frozen v5 update: a unit observed standing on an objective ends its record only when the
   side does NOT hold that objective;
3. the frozen ``delayed-post-stage-any`` eligibility (``t9_delayed.RULES``): an overflow claimant that completed a
   staging move this add-on emitted, toward any source;
4. Sprint 14's ``feasible-value-redirect`` admissibility and ranking for eligible claimants (objective not held, fewer
   than four counted places, route cost at most twice the cost to the own objective, free-flow arrival before the end;
   alternatives ranked by cost / value, cost, hex), in v3's claimant order;
5. at most one redirect per memory episode (the record's ``redirected`` flag);
6. deterministic, seat-local memory: integer pairs of own unit ids, own hexes and objective coordinates read from the
   seat's own observation, deleted with the unit, empty at the start of every game (``AddonAgent.setup``/``reset``);
7. fail closed: if the memory cannot be updated it is forgotten (nobody eligible, v3's decision); if the allocation
   cannot be computed every own ground move to an objective is withheld for this decision; if the add-on raises, the
   wrapper falls back to ``baseline-v2`` and records the error.

With nobody eligible the decision equals frozen v3's (``t9_batch.allocate``) exactly, actions and order included; with
an empty memory nobody is eligible. The frozen modules ``t9_batch``, ``t9_redistribution`` and ``t9_delayed`` are
imported and called unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from ..decision.routing import Router
from . import t9_delayed as td
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult

CANDIDATE_ID = "t9-delayed-post-stage-any-v6"
ADDON_NAME = "t9_delayed_v6"
#: The frozen Sprint 15 trigger, unchanged: completed a staging move this add-on emitted, toward any source.
RULE: td.DelayedRule = td.RULES["delayed-post-stage-any"]
#: Record-ending reasons of :func:`observe` (the same strings as the Sprint 16 shadow).
ABSENT, MOVING, STANDING_UNHELD, SOURCE_HELD = ("absent", "moving to an objective",
                                                "standing on an objective the side does not hold",
                                                "source held by the side")


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


def allocate(observation: Observation, seat: int, faction: int, actions: Sequence[Mapping[str, Any]],
             router: Router, memory: Sequence[Sequence[int]] = ()) -> td.Allocation:
    """One decision: the corrected memory update, then the frozen v5 allocation under the frozen post-stage-any rule."""
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
    return td._allocate_or_fail(observation, seat, faction, actions, router, RULE, records, ended, errors, False)


def trace_changes(result: td.Allocation) -> Tuple[Dict[str, Any], ...]:
    """The add-on's change records for one allocation (``t9_delayed.DelayedAddon``'s form)."""
    changes = list(result.changes)
    if result.error is not None:
        changes.append({"kind": "error", "reason": result.error})
    for unit_id, reason in sorted(result.ended.items()):
        changes.append({"kind": "memory-ended", "obj_id": unit_id, "reason": reason})
    return tuple(changes)


class PostStageAnyV6Addon(Addon):
    name = ADDON_NAME

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        result = allocate(observation, seat, faction, tuple(base.actions), self.baseline.router, memory)
        return AddonResult(result.actions, trace_changes(result), tuple(sorted(result.skipped.items())), result.memory)


class PostStageAnyV6Policy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = PostStageAnyV6Addon


class PostStageAnyV6Agent(AddonAgent):
    policy_class = PostStageAnyV6Policy
