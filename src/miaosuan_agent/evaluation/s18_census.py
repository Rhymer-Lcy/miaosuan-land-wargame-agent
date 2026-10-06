"""Sprint 18 supplemental census (``docs/SPRINT18_FRONTIER_RESET.md``, sections 5 to 7): pure functions over frames.

A :class:`Frame` is one side's view at one decision: its own units (seat observation, its colour), its units on board,
the enemy units it sees, its listed actions, the objective flags, the ``baseline-v2`` actions for that side at that
decision (reconstructed on H0, recorded on HH) and the concealment orders Sprint 5's A2 shadow would add. A
:class:`Game` holds both sides' frames by decision index and the game's damage events (``judge_info`` records with a
positive ``damage``, de-duplicated by content, placed at the first decision that carries them).

Every function here reads frames and events only; nothing reaches a policy or an engine. Definitions follow section 6
of the registration; where a definition needed an implementation reading, the docstring says which.
"""

from __future__ import annotations

import collections
import json
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .t7_candidates import observation_distance, weapon_range
from .t7_visibility import hex_distance

INFANTRY, VEHICLE, AIRCRAFT = 1, 2, 3
GROUND = (INFANTRY, VEHICLE)
ARTILLERY_SUB = 3
LOOKBACK = 300
CONCEAL_DELAY = 75
THREAT_PATH_HEXES = 5
#: Unit fields kept in a frame (everything else of the observation is dropped at extraction).
UNIT_FIELDS = ("obj_id", "type", "sub_type", "color", "cur_hex", "move_path", "speed", "stop", "keep",
               "keep_remain_time", "stack", "close_combat", "blood", "max_blood", "observe_distance",
               "carry_weapon_ids", "guide_ability", "on_board", "basic_speed", "move_state", "value")
ACTION_NAMES = {1: "move", 2: "shoot", 3: "embark", 4: "disembark", 5: "occupy", 6: "change state",
                7: "remove suppression", 8: "indirect fire", 9: "guided fire", 10: "stop", 11: "weapon lock",
                12: "weapon unfold", 13: "cancel indirect fire", 14: "split", 15: "merge", 16: "change altitude",
                17: "correction radar", 18: "enter fortification", 19: "exit fortification", 20: "lay mine"}


def as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def unit_view(u: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: u.get(k) for k in UNIT_FIELDS}
    out["move_path"] = tuple(u.get("move_path") or ())
    out["carry_weapon_ids"] = tuple(u.get("carry_weapon_ids") or ())
    return out


def listings(raw: Mapping[str, Any]) -> Dict[int, Dict[int, Any]]:
    out: Dict[int, Dict[int, Any]] = {}
    for obj, actions in (raw.get("valid_actions") or {}).items():
        oid = as_int(obj)
        if oid is None or not isinstance(actions, Mapping):
            continue
        out[oid] = {t: options for t, options in ((as_int(k), v) for k, v in actions.items()) if t is not None}
    return out


@dataclass
class Frame:
    k: int
    cur_step: int
    max_step: Optional[int]
    stage: Any
    faction: int
    own: Dict[int, Dict[str, Any]]
    aboard: Dict[int, Dict[str, Any]]
    enemies: Dict[int, Dict[str, Any]]
    valid: Dict[int, Dict[int, Any]]
    flags: Dict[int, Any]
    actions: List[Mapping[str, Any]] = field(default_factory=list)
    concealment: List[int] = field(default_factory=list)


def frame_from_raw(k: int, raw: Mapping[str, Any], faction: int, actions: Sequence[Mapping[str, Any]] = (),
                   concealment: Sequence[int] = ()) -> Frame:
    time_info = raw.get("time") or {}
    own, aboard, enemies = {}, {}, {}
    for u in raw.get("operators") or ():
        if not isinstance(u, Mapping) or as_int(u.get("obj_id")) is None:
            continue
        (own if u.get("color") == faction else enemies)[u["obj_id"]] = unit_view(u)
    for u in raw.get("passengers") or ():
        if isinstance(u, Mapping) and u.get("color") == faction and as_int(u.get("obj_id")) is not None:
            aboard[u["obj_id"]] = unit_view(u)
    flags = {c.get("coord"): c.get("flag") for c in raw.get("cities") or () if isinstance(c, Mapping)}
    return Frame(k=k, cur_step=time_info.get("cur_step"), max_step=time_info.get("max_step"),
                 stage=time_info.get("stage"), faction=faction, own=own, aboard=aboard, enemies=enemies,
                 valid=listings(raw), flags=flags, actions=[dict(a) for a in actions], concealment=list(concealment))


def judge_key(record: Mapping[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


def is_damage(record: Mapping[str, Any]) -> bool:
    return is_number(record.get("damage")) and record["damage"] > 0


@dataclass
class Game:
    population: str
    game: str
    scenario: str
    sides: Dict[int, List[Frame]]
    events: List[Tuple[int, Mapping[str, Any]]]
    analysed: Tuple[int, ...]


class EventCollector:
    """De-duplicates ``judge_info`` records by content and keeps the first decision that carries each."""

    def __init__(self) -> None:
        self.seen: Set[str] = set()
        self.events: List[Tuple[int, Mapping[str, Any]]] = []

    def add(self, k: int, records: Iterable[Any]) -> None:
        for record in records or ():
            if not isinstance(record, Mapping):
                continue
            key = judge_key(record)
            if key in self.seen:
                continue
            self.seen.add(key)
            if is_damage(record):
                self.events.append((k, dict(record)))


# ------------------------------------------------------------------------------------------------
# helpers over frames

def unit_class(u: Mapping[str, Any]) -> str:
    t, s = u.get("type"), u.get("sub_type")
    if t == INFANTRY:
        return "infantry"
    if t == VEHICLE:
        return "artillery" if s == ARTILLERY_SUB else "vehicle"
    if t == AIRCRAFT:
        return "aircraft"
    return "other"


def moving(u: Mapping[str, Any]) -> bool:
    return bool(u.get("move_path")) or (is_number(u.get("speed")) and u["speed"] > 0)


def last_seen_unit(frames: Sequence[Frame], k: int, obj: int) -> Tuple[Optional[Dict[str, Any]], bool]:
    """The unit as last seen by its own side at or before decision ``k`` (own or on board), and whether on board."""
    for j in range(min(k, len(frames) - 1), -1, -1):
        f = frames[j]
        if obj in f.own:
            return f.own[obj], False
        if obj in f.aboard:
            return f.aboard[obj], True
    return None, False


def lost_units(frames: Sequence[Frame]) -> Dict[int, int]:
    """Units that leave both ``operators`` and ``passengers`` of their side for the rest of the game: decision of the
    first absence."""
    last: Dict[int, int] = {}
    for f in frames:
        for obj in list(f.own) + list(f.aboard):
            last[obj] = f.k
    end = frames[-1].k if frames else -1
    return {obj: k + 1 for obj, k in last.items() if k < end}


def seen_history(frames: Sequence[Frame]) -> Dict[int, List[int]]:
    """Per enemy unit, the ``cur_step`` values at which the side saw it."""
    out: Dict[int, List[int]] = collections.defaultdict(list)
    for f in frames:
        for obj in f.enemies:
            out[obj].append(f.cur_step)
    return out


def seen_before(history: Mapping[int, List[int]], attacker: Any, step: int, window: Optional[int] = LOOKBACK) -> bool:
    steps = history.get(attacker) or ()
    lo = -10 ** 9 if window is None else step - window
    return any(lo <= s < step for s in steps)


def city_hexes(frame: Frame) -> Set[Any]:
    return set(frame.flags)


def median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def quantile(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


# ------------------------------------------------------------------------------------------------
# damage events

def event_rows(game: Game, faction: int) -> List[Dict[str, Any]]:
    """The damage events whose victim belongs to ``faction``, with the victim's state, the attacker's visibility and
    the facts the families use."""
    frames = game.sides[faction]
    history = seen_history(frames)
    lost = lost_units(frames)
    rows = []
    for k, record in game.events:
        if record.get("target_color") != faction:
            continue
        target = record.get("target_obj_id")
        victim, aboard = last_seen_unit(frames, k, target)
        frame = frames[min(k, len(frames) - 1)]
        step = record.get("cur_step") if is_number(record.get("cur_step")) else frame.cur_step
        attacker = record.get("att_obj_id")
        attacker_side = game.sides.get(record.get("attack_color"))
        att_unit = None
        if attacker_side:
            att_unit, _ = last_seen_unit(attacker_side, k, attacker)
        previous, _ = last_seen_unit(frames, k - 1, target) if k > 0 else (None, False)
        row = {
            "k": k, "step": step, "damage": record.get("damage"), "type": str(record.get("type")),
            "distance": record.get("distance") if is_number(record.get("distance")) else None,
            "ele_diff": record.get("ele_diff"), "victim": target, "attacker": attacker,
            "victim_class": unit_class(victim) if victim else "unknown",
            "aboard": aboard, "moving": bool(victim) and not aboard and moving(victim),
            "on_objective": bool(victim) and victim.get("cur_hex") in city_hexes(frame),
            "stacked": bool(victim) and bool(victim.get("stack")),
            "close_combat": bool(victim) and bool(victim.get("close_combat")),
            "suppressed_before": bool(previous) and bool(previous.get("keep")),
            "seen_at_event": attacker in frame.enemies,
            "seen_before": seen_before(history, attacker, step),
            "ever_seen_before": seen_before(history, attacker, step, None),
            "attacker_class": unit_class(att_unit) if att_unit else "unknown",
            "attacker_observe": observation_distance(att_unit, victim.get("type")) if att_unit and victim else None,
            "lost": target in lost, "lost_at": lost.get(target),
        }
        rows.append(row)
    return rows


# ------------------------------------------------------------------------------------------------
# families

def t7c(game: Game, faction: int, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    frames = game.sides[faction]
    first: Dict[int, int] = {}
    orders = 0
    for f in frames:
        for obj in f.concealment:
            orders += 1
            first.setdefault(obj, f.cur_step)
    concealable = []
    for r in rows:
        start = first.get(r["victim"])
        if start is None or r["step"] < start + CONCEAL_DELAY or r["aboard"]:
            continue
        victim, _ = last_seen_unit(frames, r["k"], r["victim"])
        if victim is None or victim.get("move_path"):
            continue
        concealable.append(r)
    exposure_units, exposure_actions = set(), 0
    for f in frames:
        for a in f.actions:
            obj = a.get("obj_id")
            if obj in first and a.get("type") in (1, 2) and f.cur_step >= first[obj] + CONCEAL_DELAY:
                exposure_units.add(obj)
                exposure_actions += 1

    def beyond_half(r: Mapping[str, Any]) -> bool:
        return r["distance"] is not None and r["attacker_observe"] is not None and r["distance"] > r["attacker_observe"] / 2

    return {"orders": orders, "units_ordered": len(first),
            "concealable_events": len(concealable),
            "concealable_damage": sum(r["damage"] for r in concealable),
            "concealable_units_damaged": len({r["victim"] for r in concealable}),
            "concealable_by_ground_attacker": sum(r["attacker_class"] in ("infantry", "vehicle", "artillery") for r in concealable),
            "concealable_by_aircraft": sum(r["attacker_class"] == "aircraft" for r in concealable),
            "concealable_ground_beyond_half_distance": sum(r["attacker_class"] in ("infantry", "vehicle", "artillery")
                                                           and beyond_half(r) for r in concealable),
            "concealable_ground_beyond_half_equal_elevation": sum(r["attacker_class"] in ("infantry", "vehicle", "artillery")
                                                                   and beyond_half(r) and r["ele_diff"] == 0
                                                                   for r in concealable),
            "concealable_lost": len({r["victim"] for r in concealable if r["lost"]}),
            "e3b_exposure_units": len(exposure_units), "e3b_exposure_actions": exposure_actions}


def travel(router_for: Callable[[Frame], Any], path_times: Callable[..., Any], frame: Frame,
           action: Mapping[str, Any]) -> Optional[Tuple[str, int, int]]:
    """(class, free-flow steps of the ordered route, steps left) of a move order, or ``None`` if unreadable."""
    unit = frame.own.get(action.get("obj_id"))
    path = action.get("move_path")
    if unit is None or not path or not is_number(frame.max_step) or not is_number(frame.cur_step):
        return None
    times, _ = path_times(router_for(frame), unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                          unit.get("cur_hex"), list(path))
    if times is None:
        return None
    return unit_class(unit), sum(times), int(frame.max_step - frame.cur_step)


def t2(game: Game, faction: int, rows: Sequence[Mapping[str, Any]], router_for, path_times) -> Dict[str, Any]:
    frames = [f for f in game.sides[faction] if f.stage == 2]
    if not frames:
        return {}
    first, last = frames[0], frames[-1]
    start_ground = sum(1 for u in first.own.values() if u.get("type") == INFANTRY)
    start_aboard = sum(1 for u in first.aboard.values() if u.get("type") == INFANTRY)
    end_aboard_units = sum(1 for u in last.aboard.values() if u.get("type") == INFANTRY)
    end_aboard_squads = sum((u.get("blood") or 0) for u in last.aboard.values() if u.get("type") == INFANTRY)
    listed = collections.Counter()
    for f in frames:
        seen_types = set()
        for obj, acts in f.valid.items():
            u = f.own.get(obj) or f.aboard.get(obj)
            if u is None:
                continue
            for t in (3, 4):
                if t in acts:
                    listed[f"unit_decisions_{t}_{unit_class(u)}"] += 1
                    seen_types.add(t)
        for t in seen_types:
            listed[f"decisions_{t}"] += 1
    issued = collections.Counter(a.get("type") for f in frames for a in f.actions if a.get("type") in (3, 4))
    times = collections.defaultdict(list)
    late = collections.Counter()
    unreadable = 0
    for f in frames:
        for a in f.actions:
            if a.get("type") != 1:
                continue
            result = travel(router_for, path_times, f, a)
            if result is None:
                unreadable += 1
                continue
            cls, steps, left = result
            times[cls].append(steps)
            late[cls] += steps > left
    infantry_on_ground = {obj for f in frames for obj, u in f.own.items() if u.get("type") == INFANTRY}
    on_objective = {obj for f in frames for obj, u in f.own.items()
                    if u.get("type") == INFANTRY and u.get("cur_hex") in f.flags}
    return {"start_infantry_on_ground": start_ground, "start_infantry_aboard": start_aboard,
            "end_infantry_aboard_units": end_aboard_units, "end_infantry_aboard_squads": end_aboard_squads,
            "listings": dict(sorted(listed.items())), "issued_embark": issued.get(3, 0), "issued_disembark": issued.get(4, 0),
            "damage_events_on_board": sum(1 for r in rows if r["aboard"]),
            "move_orders_by_class": {c: len(v) for c, v in sorted(times.items())},
            "move_orders_unable_to_arrive": dict(sorted(late.items())),
            "move_order_free_flow_steps": {c: v for c, v in sorted(times.items())},
            "move_orders_unreadable": unreadable,
            "infantry_on_ground_units": len(infantry_on_ground),
            "infantry_never_on_objective": len(infantry_on_ground - on_objective)}


def threat_exposed(frame: Frame, action: Mapping[str, Any]) -> Optional[bool]:
    """Whether a visible enemy's published weapon range covers the mover's hex or one of the first
    ``THREAT_PATH_HEXES`` hexes of the route it is given; ``None`` if the mover or every enemy is unreadable."""
    unit = frame.own.get(action.get("obj_id"))
    if unit is None or as_int(unit.get("cur_hex")) is None:
        return None
    hexes = [unit["cur_hex"]] + [h for h in list(action.get("move_path") or ())[:THREAT_PATH_HEXES] if as_int(h) is not None]
    readable = False
    for enemy in frame.enemies.values():
        reach = weapon_range(enemy.get("carry_weapon_ids") or (), unit.get("type"))
        if reach is None or as_int(enemy.get("cur_hex")) is None:
            continue
        readable = True
        if any(hex_distance(enemy["cur_hex"], h) <= reach for h in hexes):
            return True
    return False if readable or not frame.enemies else None


def t6(game: Game, faction: int, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    frames = game.sides[faction]
    by_state = collections.Counter()
    for r in rows:
        state = ("aboard" if r["aboard"] else "aircraft" if r["victim_class"] == "aircraft"
                 else "moving ground" if r["moving"] else "stationary ground" if r["victim_class"] != "unknown" else "unknown")
        by_state[state] += 1
    moving_rows = [r for r in rows if r["moving"] and r["victim_class"] in ("infantry", "vehicle", "artillery")]
    lost = lost_units(frames)
    lost_en_route = 0
    for obj, k in lost.items():
        unit, aboard = last_seen_unit(frames, k - 1, obj)
        lost_en_route += bool(unit) and not aboard and bool(unit.get("move_path")) and unit.get("type") in GROUND
    exposed = damaged_after = unreadable = orders = 0
    damage_steps = collections.defaultdict(list)
    for r in rows:
        damage_steps[r["victim"]].append(r["step"])
    for f in frames:
        for a in f.actions:
            if a.get("type") != 1:
                continue
            orders += 1
            verdict = threat_exposed(f, a)
            if verdict is None:
                unreadable += 1
            elif verdict:
                exposed += 1
                damaged_after += any(f.cur_step <= s <= f.cur_step + LOOKBACK for s in damage_steps.get(a.get("obj_id"), ()))
    return {"events_by_victim_state": dict(sorted(by_state.items())),
            "moving_ground_events": len(moving_rows),
            "moving_ground_seen_before": sum(r["seen_before"] for r in moving_rows),
            "moving_ground_seen_at_event": sum(r["seen_at_event"] for r in moving_rows),
            "units_lost": len(lost), "ground_units_lost_with_a_move_path": lost_en_route,
            "move_orders": orders, "threat_exposed_orders": exposed, "threat_exposed_then_damaged": damaged_after,
            "threat_unreadable_orders": unreadable}


def visibility_gaps(frames: Sequence[Frame]) -> Tuple[int, List[int]]:
    """Episodes in which a visible enemy disappears from view and reappears: count and gap lengths (steps)."""
    gaps: List[int] = []
    last_seen: Dict[int, int] = {}
    visible_prev: Set[int] = set()
    for f in frames:
        now = set(f.enemies)
        for obj in now - visible_prev:
            if obj in last_seen:
                gaps.append(f.cur_step - last_seen[obj])
        for obj in now:
            last_seen[obj] = f.cur_step
        visible_prev = now
    return len(gaps), gaps


def t3(game: Game, faction: int, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    n, gaps = visibility_gaps(game.sides[faction])
    return {"reappearance_episodes": n, "reappearance_gap_steps": gaps,
            "events_attacker_seen_at_event": sum(r["seen_at_event"] for r in rows),
            "events_attacker_unseen_but_seen_within_window": sum((not r["seen_at_event"]) and r["seen_before"] for r in rows),
            "events_attacker_unseen_seen_earlier_outside_window": sum((not r["seen_at_event"]) and (not r["seen_before"])
                                                                      and r["ever_seen_before"] for r in rows),
            "events_attacker_never_seen_before": sum((not r["seen_at_event"]) and not r["ever_seen_before"] for r in rows)}


def listing_counts(frames: Sequence[Frame], types: Iterable[int]) -> Dict[str, int]:
    wanted = set(types)
    out = collections.Counter()
    for f in frames:
        if f.stage != 2:
            continue
        present = set()
        for obj, acts in f.valid.items():
            if obj not in f.own and obj not in f.aboard:
                continue
            for t in wanted & set(acts):
                out[f"unit_decisions_{t:02d}"] += 1
                present.add(t)
        for t in present:
            out[f"decisions_{t:02d}"] += 1
    return dict(sorted(out.items()))


def issued_counts(frames: Sequence[Frame]) -> Dict[str, int]:
    return dict(sorted(collections.Counter(f"type_{a.get('type'):02d}" for f in frames for a in f.actions
                                           if as_int(a.get("type")) is not None).items()))


# ------------------------------------------------------------------------------------------------
# scan items

def suppression(game: Game, faction: int, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    frames = [f for f in game.sides[faction] if f.stage == 2]
    onsets = collections.Counter()
    remain_at_onset: List[float] = []
    previous: Dict[int, Any] = {}
    listed = collections.Counter()
    for f in frames:
        for obj, u in f.own.items():
            keep = bool(u.get("keep"))
            if keep and obj in previous and not previous[obj]:
                onsets[unit_class(u)] += 1
                if is_number(u.get("keep_remain_time")):
                    remain_at_onset.append(u["keep_remain_time"])
            previous[obj] = keep
            if 7 in f.valid.get(obj, {}):
                listed["keep_1" if keep else "keep_0"] += 1
    return {"onsets_by_class": dict(sorted(onsets.items())), "keep_remain_time_at_onset": remain_at_onset,
            "remove_suppression_unit_decisions": dict(sorted(listed.items())),
            "infantry_events_already_suppressed": sum(1 for r in rows if r["victim_class"] == "infantry" and r["suppressed_before"]),
            "infantry_events": sum(1 for r in rows if r["victim_class"] == "infantry")}


def fire_choice(game: Game, faction: int) -> Dict[str, int]:
    shots = multi = lower = 0
    for f in game.sides[faction]:
        for a in f.actions:
            if a.get("type") != 2:
                continue
            shots += 1
            options = f.valid.get(a.get("obj_id"), {}).get(2) or []
            targets = {o.get("target_obj_id") for o in options if isinstance(o, Mapping)}
            if len(targets) < 2:
                continue
            multi += 1
            blood = {t: (f.enemies.get(t) or {}).get("blood") for t in targets}
            chosen = blood.get(a.get("target_obj_id"))
            if is_number(chosen) and any(is_number(b) and b < chosen for b in blood.values()):
                lower += 1
    return {"shots": shots, "shots_with_two_or_more_targets": multi, "lower_blood_target_listed": lower}


def objective_defence(game: Game, faction: int) -> Dict[str, int]:
    frames = [f for f in game.sides[faction] if f.stage == 2]
    losses = stood = 0
    held_prev: Dict[Any, bool] = {}
    previous_frame: Optional[Frame] = None
    for f in frames:
        for coord, flag in f.flags.items():
            held = flag == faction
            if held_prev.get(coord) and not held:
                losses += 1
                if previous_frame is not None and any(u.get("cur_hex") == coord for u in previous_frame.own.values()):
                    stood += 1
            held_prev[coord] = held
        previous_frame = f
    held_at_end = sum(1 for held in held_prev.values() if held)
    return {"objective_losses": losses, "losses_with_own_unit_on_it_before": stood, "held_at_end": held_at_end}


def first_ownership_steps(game: Game, faction: int) -> List[int]:
    seen: Dict[Any, int] = {}
    for f in game.sides[faction]:
        for coord, flag in f.flags.items():
            if flag == faction and coord not in seen:
                seen[coord] = f.cur_step
    return sorted(seen.values())


def idle(game: Game, faction: int) -> Dict[str, int]:
    out = collections.Counter()
    for f in game.sides[faction]:
        if f.stage != 2:
            continue
        acted = {a.get("obj_id") for a in f.actions}
        enemy = "enemy_visible" if f.enemies else "no_enemy"
        for obj, u in f.own.items():
            if u.get("type") not in GROUND or u.get("move_path") or obj in acted:
                continue
            out[f"{unit_class(u)}_{enemy}"] += 1
    return dict(sorted(out.items()))


def close_combat(game: Game, faction: int, rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    unit_decisions = sum(1 for f in game.sides[faction] for u in f.own.values() if u.get("close_combat"))
    return {"unit_decisions_in_close_combat": unit_decisions,
            "events_at_distance_0": sum(1 for r in rows if r["distance"] == 0)}


def aircraft(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    air = [r for r in rows if r["victim_class"] == "aircraft"]
    return {"events": len(air), "events_while_moving": sum(r["moving"] for r in air),
            "units_lost": len({r["victim"] for r in air if r["lost"]})}


def stacking(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    ground = [r for r in rows if r["victim_class"] in ("infantry", "vehicle", "artillery") and not r["aboard"]]
    return {"ground_events": len(ground), "ground_events_victim_stacked": sum(r["stacked"] for r in ground)}


def distances_by_type(rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = collections.defaultdict(list)
    for r in rows:
        if r["distance"] is not None:
            out[r["type"]].append(r["distance"])
    return dict(out)
