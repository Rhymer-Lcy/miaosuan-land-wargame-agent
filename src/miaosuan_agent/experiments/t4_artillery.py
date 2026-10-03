"""EXPLORATORY candidate ``t4-artillery-v1``: give ``baseline-v2``'s idle artillery an indirect-fire target.

EXPLORATORY track (``docs/EXPLORATORY_TRACK.md``): not eligible for baseline promotion, never packaged.

``baseline-v2`` decides first, unchanged (:mod:`.exploratory_addon`). Then every own unit that received no
``baseline-v2`` action and lists indirect fire (action 8) with an int ``weapon_id`` option is considered, in
ascending id; the rule is capability-driven (a listing, not a unit kind). Such a unit is ordered to fire
``{actor, obj_id, type 8, jm_pos, weapon_id}`` at the best remaining target hex, when:

* its ``weapon_cool_time`` is 0 (the engine names a weapon-cooling refusal for indirect fire), and
* the candidate did not order it within the last ``REFIRE_GAP`` steps.

Target hexes are the hexes of enemy ground units the seat currently sees. A hex is excluded when

* an own ground unit stands within ``SAFE_OWN`` hexes of it, or a hex of an own unit's move path lies within
  ``SAFE_PATH`` hexes of it (the rules say indirect fire also damages own units, and units that enter the hex
  while it explodes);
* an own indirect-fire point listed in ``jm_points`` (flying or exploding) is on it, or the candidate aimed at it in
  the last ``AIM_MEMORY`` steps;
* another unit was given it earlier in the same step.

Remaining hexes are ranked by: more stationary enemy units (empty move path; a moving unit may leave before the
round lands), then whether the hex is an objective, then the summed ``value`` of the enemy units (1 when absent),
then more enemy units, then the lower hex. No range limit is applied: the engine's refusal catalogue names no
out-of-range class for indirect fire (it names moving, weapon cooling, weapon locked, wrong weapon, out of map and
splitting), so range is left to the mechanism games to establish.

Memory: per unit, the step of its last order, and per aimed hex, the step it was last aimed at.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..boundary import Observation, Stage
from ..decision.policy import Decision
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, hex_distance, is_int, is_number

CANDIDATE_ID = "t4-artillery-v1"
INDIRECT = 8
GROUND = (1, 2)
SAFE_OWN = 2
SAFE_PATH = 1
REFIRE_GAP = 5
AIM_MEMORY = 5
ACTIVE_JM = (0, 1)  # flying, exploding
ACTION_KEYS = frozenset({"actor", "obj_id", "type", "jm_pos", "weapon_id"})
#: Memory keys: a unit id is stored as itself; an aimed hex as AIM_KEY_BASE + hex (the two ranges never overlap).
AIM_KEY_BASE = 10 ** 9


def indirect_weapon(options: Any) -> Tuple[Optional[int], bool]:
    """The lowest int ``weapon_id`` among the listed indirect-fire options, and whether any option was malformed."""
    weapons, malformed = [], False
    for option in options or ():
        if isinstance(option, Mapping) and is_int(option.get("weapon_id")):
            weapons.append(option["weapon_id"])
        else:
            malformed = True
    return (min(weapons) if weapons else None), malformed


def own_check(action: Mapping[str, Any], listed: Mapping[int, Mapping[int, Any]],
              taken: List[Mapping[str, Any]]) -> Optional[str]:
    """The add-on's own legality check of one indirect-fire action (``None`` when it passes)."""
    if set(action) != ACTION_KEYS:
        return "key set differs"
    if action["type"] != INDIRECT or not is_int(action["jm_pos"]) or not is_int(action["weapon_id"]):
        return "not an indirect-fire order with int parameters"
    options = (listed.get(action["obj_id"]) or {}).get(INDIRECT)
    if not any(isinstance(o, Mapping) and o.get("weapon_id") == action["weapon_id"] for o in options or ()):
        return "weapon not listed for the unit"
    if any(a.get("obj_id") == action["obj_id"] for a in taken):
        return "unit already has an action"
    return None


class ArtilleryAddon(Addon):
    name = "t4"

    def apply(self, observation: Observation, seat: int, faction: int, base: Decision,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        actions = tuple(base.actions)
        if observation.time().stage != Stage.PLAY:
            return AddonResult(actions, addon_memory=memory)
        cur_step = observation.time().cur_step
        state: Dict[int, int] = dict(memory)
        listed = observation.valid_actions()
        units = sorted(observation.operators(), key=lambda u: u.obj_id)
        own = [u for u in units if u.color == faction]
        own_ground = [u.cur_hex for u in own if u.fields.get("type") in GROUND]
        own_path = sorted({h for u in own for h in (u.move_path or ()) if is_int(h)})
        objectives = {c.coord for c in (observation.cities() or ())}
        active = set()
        for point in observation.fields.get("jm_points") or ():
            if (isinstance(point, Mapping) and point.get("color") == faction and point.get("status") in ACTIVE_JM
                    and is_int(point.get("pos"))):
                active.add(point["pos"])
        recent = {key - AIM_KEY_BASE for key, step in state.items()
                  if key >= AIM_KEY_BASE and cur_step - step < AIM_MEMORY}
        stats: Dict[int, List[int]] = collections.defaultdict(lambda: [0, 0, 0])  # stationary, value, units
        for enemy in units:
            if enemy.color == faction or enemy.fields.get("type") not in GROUND:
                continue
            entry = stats[enemy.cur_hex]
            entry[0] += not enemy.move_path
            value = enemy.fields.get("value")
            entry[1] += value if is_int(value) and value > 0 else 1
            entry[2] += 1
        excluded: collections.Counter = collections.Counter()
        targets = []
        for hex_, (stationary, value, count) in stats.items():
            if any(hex_distance(hex_, h) <= SAFE_OWN for h in own_ground):
                excluded["target near an own ground unit"] += 1
            elif any(hex_distance(hex_, h) <= SAFE_PATH for h in own_path):
                excluded["target near an own move path"] += 1
            elif hex_ in active:
                excluded["target under own fire"] += 1
            elif hex_ in recent:
                excluded["target aimed at recently"] += 1
            else:
                targets.append(((-stationary, -(hex_ in objectives), -value, -count, hex_), hex_, count, stationary))
        targets.sort()
        acted = {a.get("obj_id") for a in actions}
        added: List[Dict[str, Any]] = []
        changes: List[Dict[str, Any]] = []
        skipped: collections.Counter = collections.Counter()
        for unit in own:
            if unit.obj_id in acted:
                continue
            options = (listed.get(unit.obj_id) or {}).get(INDIRECT)
            if options is None:
                continue
            weapon, malformed = indirect_weapon(options)
            if weapon is None:
                skipped["malformed indirect-fire option" if malformed else "no weapon listed"] += 1
                continue
            cool = unit.fields.get("weapon_cool_time")
            if not is_number(cool):
                skipped["missing or malformed weapon_cool_time"] += 1
                continue
            if cool > 0:
                skipped["weapon cooling"] += 1
                continue
            last = state.get(unit.obj_id)
            if last is not None and cur_step - last < REFIRE_GAP:
                skipped["ordered recently"] += 1
                continue
            if not targets:
                skipped["no safe target"] += 1
                continue
            _, hex_, count, stationary = targets.pop(0)
            action = {"actor": seat, "obj_id": unit.obj_id, "type": INDIRECT, "jm_pos": hex_, "weapon_id": weapon}
            problem = own_check(action, listed, list(actions) + added)
            if problem is not None:
                skipped[f"own check: {problem}"] += 1
                continue
            added.append(action)
            state[unit.obj_id] = cur_step
            state[AIM_KEY_BASE + hex_] = cur_step
            changes.append({"kind": "add", "obj_id": unit.obj_id, "type": INDIRECT, "jm_pos": hex_,
                            "weapon_id": weapon, "enemy_units": count, "stationary": stationary,
                            "distance": hex_distance(unit.cur_hex, hex_)})
        for reason, count in excluded.items():
            skipped[f"hex excluded: {reason}"] += count
        kept = {key: step for key, step in state.items()
                if cur_step - step < (AIM_MEMORY if key >= AIM_KEY_BASE else REFIRE_GAP)}
        return AddonResult(actions + tuple(added), tuple(changes), tuple(sorted(skipped.items())),
                           tuple(sorted(kept.items())))


class ArtilleryPolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = ArtilleryAddon


class ArtilleryAgent(AddonAgent):
    policy_class = ArtilleryPolicy
