"""OFFLINE SHADOW of the T7 candidate ``t7-idle-concealment`` (``docs/T7_DESIGN.md``, section 14).

Not registered, not packaged, not a production policy: no runner, manifest or package imports it, and it is not in
``decision.policy.POLICIES``. It decides on one captured seat observation and its own memory and returns what
``baseline-v2`` plus the candidate would emit; nothing it returns reaches an engine.

``baseline-v2`` (``experiments/shoot_reservation.py``) decides first, unchanged. Then each own unit, in ascending id,
that received no ``baseline-v2`` action is checked against the trigger; a unit that meets it is ordered into
concealment (action 6, ``target_state`` 4). Action 6 is not in the project gate's catalogue, so the shadow checks its
own actions: the option is listed for the unit in this observation, the key set is exact, and no unit gets two actions.
Every condition fails closed: a missing or malformed field means no order, counted by reason.

Written separately from :func:`miaosuan_agent.evaluation.t7_candidates.a2` (the pool predicate) so that the two can
be compared as independent implementations.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, Observation, Operator, Stage
from ..decision import Memory
from ..decision.policy import Decision
from .shoot_reservation import ShootReservationPolicy

SHADOW_ID = "t7-idle-concealment-shadow"
CHANGE_STATE = 6
CONCEAL = 4
GROUND = (1, 2)
#: Steps during which the shadow does not repeat an order to the same unit (one documented transition).
REPEAT_WINDOW = 75
#: Fields that must read 0: a positive value means the unit is in some transition.
TRANSITION_FIELDS = ("change_state_remain_time", "move_to_stop_remain_time", "weapon_unfold_time",
                     "get_on_remain_time", "get_off_remain_time")
ACTION_KEYS = frozenset({"actor", "obj_id", "type", "target_state"})


@dataclass(frozen=True)
class ShadowMemory:
    """``baseline-v2``'s memory plus, per unit, the ``cur_step`` of the shadow's last change-state order."""

    baseline: Memory = field(default_factory=Memory)
    last_order: Tuple[Tuple[int, int], ...] = ()


@dataclass(frozen=True)
class ShadowDecision:
    actions: Tuple[Mapping[str, Any], ...]
    baseline: Decision
    added: Tuple[Mapping[str, Any], ...]
    skipped: Tuple[Tuple[str, int], ...]
    memory: ShadowMemory


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def conceal_option(options: Any) -> Tuple[Optional[Mapping[str, Any]], bool]:
    """The listed option with ``target_state`` 4, and whether any listed option was malformed."""
    found, malformed = None, False
    for option in options or ():
        if not isinstance(option, Mapping) or not _is_int(option.get("target_state")):
            malformed = True
            continue
        if option["target_state"] == CONCEAL and found is None:
            found = option
    return found, malformed


def refusal(unit: Operator, listed: Mapping[int, Any], enemy_seen: bool, cur_step: int,
            last_order: Mapping[int, int]) -> Optional[str]:
    """Why the trigger does not hold for an own unit without a ``baseline-v2`` action, or ``None`` if it holds."""
    fields = unit.fields
    if fields.get("type") not in GROUND:
        return "not a ground unit"
    if CHANGE_STATE not in listed:
        return "change state not listed"
    option, malformed = conceal_option(listed[CHANGE_STATE])
    state = fields.get("move_state")
    if not _is_int(state):
        return "missing or malformed move_state"
    if option is None:
        return "malformed change-state option" if malformed else "concealment not listed"
    if state == CONCEAL:
        return "contradictory: concealment listed for a concealed unit"
    for name in TRANSITION_FIELDS:
        value = fields.get(name)
        if not _is_number(value):
            return f"missing or malformed {name}"
        if value != 0:
            return "in a transition"
    if fields.get("stop") != 1:
        return "not stopped" if _is_int(fields.get("stop")) else "missing or malformed stop"
    path = fields.get("move_path")
    if not isinstance(path, (list, tuple)):
        return "missing or malformed move_path"
    if path:
        return "has a move path"
    keep = fields.get("keep")
    if not _is_number(keep):
        return "missing or malformed keep"
    if keep != 0:
        return "suppressed"
    if enemy_seen:
        return "an enemy is seen"
    last = last_order.get(unit.obj_id)
    if last is not None and cur_step - last < REPEAT_WINDOW:
        return "ordered within the repeat window"
    return None


def own_check(action: Mapping[str, Any], listed: Mapping[int, Mapping[int, Any]],
              taken: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """The shadow's own legality check of one added action (``None`` when it passes)."""
    if set(action) != ACTION_KEYS:
        return "key set differs"
    if action["type"] != CHANGE_STATE or action["target_state"] != CONCEAL:
        return "not a concealment order"
    option, _ = conceal_option((listed.get(action["obj_id"]) or {}).get(CHANGE_STATE))
    if option is None:
        return "option not listed for the unit"
    if any(a.get("obj_id") == action["obj_id"] for a in taken):
        return "unit already has an action"
    return None


class IdleConcealmentShadow:
    identity = SHADOW_ID

    def __init__(self, costs: Optional[MoveCosts]) -> None:
        self.baseline = ShootReservationPolicy(costs)

    def decide(self, observation: Observation, seat: int, faction: int, memory: ShadowMemory) -> ShadowDecision:
        base = self.baseline.decide(observation, seat, faction, memory.baseline)
        new_memory = replace(memory, baseline=base.memory)
        time = observation.time()
        if time.stage != Stage.PLAY:
            return ShadowDecision(tuple(base.actions), base, (), (), new_memory)
        listed = observation.valid_actions()
        units = sorted(observation.operators(), key=lambda u: u.obj_id)
        enemy_seen = any(u.color != faction for u in units)
        acted = {a.get("obj_id") for a in base.actions}
        last = dict(memory.last_order)
        added: List[Dict[str, Any]] = []
        skipped: collections.Counter = collections.Counter()
        for unit in units:
            if unit.color != faction or unit.obj_id in acted:
                continue
            reason = refusal(unit, listed.get(unit.obj_id) or {}, enemy_seen, time.cur_step, last)
            if reason is not None:
                skipped[reason] += 1
                continue
            option, _ = conceal_option((listed.get(unit.obj_id) or {}).get(CHANGE_STATE))
            target = option["target_state"] if option is not None else CONCEAL
            action = {"actor": seat, "obj_id": unit.obj_id, "type": CHANGE_STATE, "target_state": target}
            failed = own_check(action, listed, list(base.actions) + added)
            if failed is not None:
                skipped[f"own check: {failed}"] += 1
                continue
            added.append(action)
            last[unit.obj_id] = time.cur_step
        memory_out = replace(new_memory, last_order=tuple(sorted(last.items())))
        return ShadowDecision(tuple(base.actions) + tuple(added), base, tuple(added), tuple(sorted(skipped.items())),
                              memory_out)
