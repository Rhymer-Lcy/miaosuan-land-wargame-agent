"""EXPLORATORY candidate ``t4-artillery-v2``: version 2 of the indirect-fire add-on (``docs/SPRINT8_EXPLORATION.md``).

EXPLORATORY track (``docs/EXPLORATORY_TRACK.md``): not eligible for baseline promotion, never packaged. Version 1
(:mod:`.t4_artillery`) stays frozen; this module reuses its option parsing and its own legality check.

Two changes, each answering a failure recorded by the version 1 mechanism games (``s8-t4-v1-mechanism``):

* Version 1 aimed only at enemy units seen in the current step. Against the inert control the enemy was out of sight
  almost all game, and the artillery fired once in 2,880 steps. Version 2 also remembers each enemy ground unit last
  seen stationary (empty move path) for ``REMEMBER`` steps, at the hex where it was seen; the memory of a unit is
  dropped when it is seen moving or when ``REMEMBER`` steps have passed. A remembered unit currently in sight is
  taken from the current observation instead.
* Version 1 excluded every hex under its own fire, flying or exploding. In the engine a round lands about 150 steps
  after the order and the hex then explodes for about 300 steps; the units in the hex are judged when it lands, so a
  stationary target in an exploding hex can be judged again only by a new round. Version 2 excludes only hexes with
  an own round still in flight (and hexes it aimed at within ``AIM_MEMORY`` steps).

Everything else is version 1: ``baseline-v2`` decides first and is never changed; units listing indirect fire, in
ascending id, with ``weapon_cool_time`` 0 and not ordered within ``REFIRE_GAP`` steps; one unit per hex per step; the
own-unit and own-path exclusions. Ranking: stationary units seen now, then remembered stationary units, then units
seen moving (``tier``), then whether the hex is an objective, then summed value, then count, then the lower hex.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List, Mapping, Tuple

from ..boundary import Observation, Stage
from ..decision.policy import Decision
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, hex_distance, is_int, is_number
from .t4_artillery import (ACTION_KEYS, AIM_KEY_BASE, AIM_MEMORY, GROUND, INDIRECT, REFIRE_GAP, SAFE_OWN, SAFE_PATH,
                           indirect_weapon, own_check)

CANDIDATE_ID = "t4-artillery-v2"
FLYING = 0
REMEMBER = 600
#: Memory keys: unit ids as themselves, aimed hexes at AIM_KEY_BASE + hex, remembered enemies at ENEMY_KEY_BASE + id
#: with the value step * HEX_SPAN + hex (hexes are four-digit, so they stay below HEX_SPAN).
ENEMY_KEY_BASE = 2 * 10 ** 9
HEX_SPAN = 10 ** 4
SEEN_STATIONARY, REMEMBERED, SEEN_MOVING = 0, 1, 2
__all__ = ["ACTION_KEYS", "CANDIDATE_ID", "ArtilleryV2Addon", "ArtilleryV2Agent", "ArtilleryV2Policy"]


class ArtilleryV2Addon(Addon):
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
        flying = set()
        for point in observation.fields.get("jm_points") or ():
            if (isinstance(point, Mapping) and point.get("color") == faction and point.get("status") == FLYING
                    and is_int(point.get("pos"))):
                flying.add(point["pos"])
        recent = {key - AIM_KEY_BASE for key, step in state.items()
                  if AIM_KEY_BASE <= key < ENEMY_KEY_BASE and cur_step - step < AIM_MEMORY}
        # enemies: seen now, and remembered stationary ones not seen now
        enemies: List[Tuple[int, int, int, int]] = []  # tier, hex, value, obj_id
        seen = set()
        for enemy in units:
            if enemy.color == faction or enemy.fields.get("type") not in GROUND:
                continue
            seen.add(enemy.obj_id)
            value = enemy.fields.get("value")
            value = value if is_int(value) and value > 0 else 1
            key = ENEMY_KEY_BASE + enemy.obj_id
            if enemy.move_path:
                state.pop(key, None)
                enemies.append((SEEN_MOVING, enemy.cur_hex, value, enemy.obj_id))
            else:
                state[key] = cur_step * HEX_SPAN + enemy.cur_hex
                enemies.append((SEEN_STATIONARY, enemy.cur_hex, value, enemy.obj_id))
        for key, packed in sorted(state.items()):
            if key < ENEMY_KEY_BASE or key - ENEMY_KEY_BASE in seen:
                continue
            step, hex_ = divmod(packed, HEX_SPAN)
            if cur_step - step < REMEMBER:
                enemies.append((REMEMBERED, hex_, 1, key - ENEMY_KEY_BASE))
        stats: Dict[int, List[int]] = collections.defaultdict(lambda: [3, 0, 0])  # best tier, value, count
        for tier, hex_, value, _ in enemies:
            entry = stats[hex_]
            entry[0] = min(entry[0], tier)
            entry[1] += value
            entry[2] += 1
        excluded: collections.Counter = collections.Counter()
        targets = []
        for hex_, (tier, value, count) in stats.items():
            if any(hex_distance(hex_, h) <= SAFE_OWN for h in own_ground):
                excluded["target near an own ground unit"] += 1
            elif any(hex_distance(hex_, h) <= SAFE_PATH for h in own_path):
                excluded["target near an own move path"] += 1
            elif hex_ in flying:
                excluded["target under an own round in flight"] += 1
            elif hex_ in recent:
                excluded["target aimed at recently"] += 1
            else:
                targets.append(((tier, -(hex_ in objectives), -value, -count, hex_), hex_, count, tier))
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
            _, hex_, count, tier = targets.pop(0)
            action = {"actor": seat, "obj_id": unit.obj_id, "type": INDIRECT, "jm_pos": hex_, "weapon_id": weapon}
            problem = own_check(action, listed, list(actions) + added)
            if problem is not None:
                skipped[f"own check: {problem}"] += 1
                continue
            added.append(action)
            state[unit.obj_id] = cur_step
            state[AIM_KEY_BASE + hex_] = cur_step
            changes.append({"kind": "add", "obj_id": unit.obj_id, "type": INDIRECT, "jm_pos": hex_,
                            "weapon_id": weapon, "enemy_units": count, "tier": tier,
                            "distance": hex_distance(unit.cur_hex, hex_)})
        for reason, count in excluded.items():
            skipped[f"hex excluded: {reason}"] += count
        kept = {}
        for key, value in state.items():
            if key >= ENEMY_KEY_BASE:
                if cur_step - value // HEX_SPAN < REMEMBER:
                    kept[key] = value
            elif cur_step - value < (AIM_MEMORY if key >= AIM_KEY_BASE else REFIRE_GAP):
                kept[key] = value
        return AddonResult(actions + tuple(added), tuple(changes), tuple(sorted(skipped.items())),
                           tuple(sorted(kept.items())))


class ArtilleryV2Policy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = ArtilleryV2Addon


class ArtilleryV2Agent(AddonAgent):
    policy_class = ArtilleryV2Policy
