"""T6-G threat-entry gate: the frozen gate and hold state machine of Sprint 19 (``docs/SPRINT19_T6G_SHADOW.md``).

OFFLINE ONLY. Not registered as a policy, not packaged, not in ``decision.policy.POLICIES``, and in no run card. It
filters an action list that ``baseline-v2`` has already produced for one seat at one decision; nothing it returns
reaches an engine in Sprint 19.

The gate (registration, section 4). A ``baseline-v2`` move (action type 1) is dropped from the list when all hold:

1. the actor is an own ground unit (type 1 or 2) in the seat's own operators;
2. its current hex is outside every qualifying visible threat: for every currently visible enemy unit with at least one
   direct-fire weapon whose published range against the mover's class is known, ``hex_distance(current, enemy) >
   range``; if no such enemy is visible the gate does not fire;
3. at least one of the first ``ROUTE_PREFIX`` hexes of the ordered route (``move_path``, which lists the hexes after
   the current one) is inside one: ``hex_distance(route_hex, enemy) <= range`` for at least one qualifying enemy; an
   empty route cannot trigger, a shorter route uses every hex it has;
4. the unit is not in its post-release cooldown, and its current hold episode has not reached ``HOLD_LIMIT`` steps.

The range of an enemy against the mover's class is ``evaluation.t7_candidates.weapon_range`` over the enemy's
``carry_weapon_ids``: the longest published direct-fire range of its weapons against personnel (mover type 1) or
vehicles (mover type 2), the table Sprint 5 transcribed from the published rules and Sprint 18 used for its exposure
figures. A weapon outside that table (indirect artillery among them) or without a published range for the class adds
nothing. "Any weapon covers" equals "the longest range covers", so the maximum is exact, not an average. Distances
are ``evaluation.t7_visibility.hex_distance``. No other threat filter is applied: no cooldown, suppression, line of
fire, prediction, memory of unseen enemies, probability or value.

Dropping is the only change: no replacement move, route, stop, new action type or change to any other action; the
remaining actions keep their order.

The hold state machine (registration, section 5), per unit, on ``cur_step``:

* no state, condition holds: the move is dropped and a hold episode starts (``hold_start = cur_step``);
* in a hold, a move arrives: if ``cur_step - hold_start >= HOLD_LIMIT`` the episode is released (reason
  ``hold_limit``) and the move passes; else if the condition holds the move is dropped again (a repeat); else the
  episode is released (reason ``condition_cleared``) and the move passes;
* in a hold, no move for the unit in this decision's list: the episode is released (reason ``no_baseline_move``);
  no future move is inferred;
* every release sets ``release = cur_step``; while ``cur_step - release < COOLDOWN`` the unit cannot start a hold (a
  move meeting the condition then passes and is counted as a cooldown suppression); at exactly ``COOLDOWN`` it is
  eligible again;
* a unit absent from the seat's own operators loses its state (an open episode ends with reason ``unit_absent``);
* a new game starts from an empty :class:`GateMemory`.

Every unreadable field fails closed to "no gate": the move passes unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..evaluation.t7_candidates import weapon_range
from ..evaluation.t7_visibility import hex_distance

GATE_ID = "t6-threat-entry-gate-shadow"
MOVE = 1
GROUND = (1, 2)
ROUTE_PREFIX = 5
HOLD_LIMIT = 150
COOLDOWN = 300
HOLD, COOL = "hold", "cooldown"
#: Release reasons, and the reason an episode still open at the last decision is closed with by the analysis.
RELEASE_REASONS = ("condition_cleared", "hold_limit", "no_baseline_move", "unit_absent")
#: Why a move does not meet the threat-entry condition (``eligible`` when it does).
CHECK_REASONS = ("eligible", "not_ground", "unreadable_mover", "no_qualifying_threat", "current_hex_inside",
                 "unreadable_route", "empty_route", "no_route_entry")


def _hex(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True)
class Threat:
    """A currently visible enemy with a published direct-fire range against the mover's class (private fields)."""

    enemy: Any
    hex: int
    reach: int


@dataclass(frozen=True)
class EntryCheck:
    """The threat-entry condition for one move: whether it holds, why, and the facts behind it."""

    eligible: bool
    reason: str
    threats: Tuple[Threat, ...] = ()
    causing: Tuple[Threat, ...] = ()
    inspected: Tuple[int, ...] = ()
    first_entry_index: Optional[int] = None


@dataclass(frozen=True)
class GateRules:
    """The frozen parameters. ``condition`` replaces the threat-entry condition only in known-answer smoke runs."""

    route_prefix: int = ROUTE_PREFIX
    hold_limit: int = HOLD_LIMIT
    cooldown: int = COOLDOWN
    condition: Optional[Callable[[Optional[Mapping[str, Any]], Sequence[Any], Iterable[Mapping[str, Any]]], "EntryCheck"]] = None


FROZEN = GateRules()


def qualifying_threats(enemies: Iterable[Mapping[str, Any]], mover_type: Any) -> Tuple[Threat, ...]:
    """Every visible enemy with a readable hex and a published direct-fire range against ``mover_type``, by id."""
    out = []
    for enemy in enemies:
        h = _hex(enemy.get("cur_hex"))
        reach = weapon_range(enemy.get("carry_weapon_ids") or (), mover_type)
        if h is None or reach is None:
            continue
        out.append(Threat(enemy.get("obj_id"), h, reach))
    return tuple(sorted(out, key=lambda t: (str(t.enemy), t.hex)))


def threat_entry(mover: Optional[Mapping[str, Any]], route: Sequence[Any], enemies: Iterable[Mapping[str, Any]],
                 route_prefix: int = ROUTE_PREFIX) -> EntryCheck:
    """The threat-entry condition (conditions 1 to 3 of the module docstring) for one move."""
    if mover is None or mover.get("type") not in GROUND:
        return EntryCheck(False, "not_ground")
    current = _hex(mover.get("cur_hex"))
    if current is None:
        return EntryCheck(False, "unreadable_mover")
    threats = qualifying_threats(enemies, mover.get("type"))
    if not threats:
        return EntryCheck(False, "no_qualifying_threat")
    if any(hex_distance(current, t.hex) <= t.reach for t in threats):
        return EntryCheck(False, "current_hex_inside", threats)
    prefix = list(route or ())[:max(0, route_prefix)]
    if any(_hex(h) is None for h in prefix):
        return EntryCheck(False, "unreadable_route", threats)
    inspected = tuple(prefix)
    if not inspected:
        return EntryCheck(False, "empty_route", threats)
    causing = tuple(t for t in threats if any(hex_distance(h, t.hex) <= t.reach for h in inspected))
    if not causing:
        return EntryCheck(False, "no_route_entry", threats, (), inspected)
    first = min(i for i, h in enumerate(inspected, start=1) if any(hex_distance(h, t.hex) <= t.reach for t in threats))
    return EntryCheck(True, "eligible", threats, causing, inspected, first)


@dataclass(frozen=True)
class GateMemory:
    """Per unit ``(obj_id, phase, step)``, sorted by id: phase ``hold`` with its start step or ``cooldown`` with its
    release step. Units without state are absent."""

    entries: Tuple[Tuple[Any, str, int], ...] = ()


@dataclass(frozen=True)
class GateEvent:
    """``gate_start``, ``gate_repeat``, ``release`` (with ``reason``) or ``cooldown_suppressed``."""

    kind: str
    obj_id: Any
    step: int
    index: Optional[int] = None
    reason: Optional[str] = None
    hold_start: Optional[int] = None
    check: Optional[EntryCheck] = None


@dataclass(frozen=True)
class GateResult:
    actions: Tuple[Mapping[str, Any], ...]
    dropped: Tuple[int, ...]
    events: Tuple[GateEvent, ...]
    checks: Tuple[Tuple[int, Any, EntryCheck], ...]
    memory: GateMemory


def apply_gate(cur_step: int, own: Mapping[Any, Mapping[str, Any]], enemies: Iterable[Mapping[str, Any]],
               actions: Sequence[Mapping[str, Any]], memory: GateMemory, rules: GateRules = FROZEN) -> GateResult:
    """One decision of the gate: the filtered action list, the dropped indices, the events, the condition of every move
    and the new memory. Deterministic; the input list and memory are not modified."""
    enemies = list(enemies)
    state: Dict[Any, Tuple[str, int]] = {obj: (phase, step) for obj, phase, step in memory.entries}
    events: List[GateEvent] = []
    for obj in sorted(state, key=str):
        phase, step = state[obj]
        if obj not in own:
            if phase == HOLD:
                events.append(GateEvent("release", obj, cur_step, reason="unit_absent", hold_start=step))
            del state[obj]
        elif phase == COOL and cur_step - step >= rules.cooldown:
            del state[obj]
    dropped: List[int] = []
    checks: List[Tuple[int, Any, EntryCheck]] = []
    touched = set()
    for i, action in enumerate(actions):
        if action.get("type") != MOVE:
            continue
        obj = action.get("obj_id")
        route = action.get("move_path") or ()
        if rules.condition is not None:
            check = rules.condition(own.get(obj), route, enemies)
        else:
            check = threat_entry(own.get(obj), route, enemies, rules.route_prefix)
        checks.append((i, obj, check))
        entry = state.get(obj)
        touched.add(obj)
        if entry is not None and entry[0] == COOL:
            if check.eligible:
                events.append(GateEvent("cooldown_suppressed", obj, cur_step, index=i, check=check))
            continue
        if entry is not None and entry[0] == HOLD:
            start = entry[1]
            if cur_step - start >= rules.hold_limit:
                events.append(GateEvent("release", obj, cur_step, index=i, reason="hold_limit", hold_start=start,
                                        check=check))
                state[obj] = (COOL, cur_step)
            elif check.eligible:
                dropped.append(i)
                events.append(GateEvent("gate_repeat", obj, cur_step, index=i, hold_start=start, check=check))
            else:
                events.append(GateEvent("release", obj, cur_step, index=i, reason="condition_cleared",
                                        hold_start=start, check=check))
                state[obj] = (COOL, cur_step)
            continue
        if check.eligible:
            dropped.append(i)
            state[obj] = (HOLD, cur_step)
            events.append(GateEvent("gate_start", obj, cur_step, index=i, hold_start=cur_step, check=check))
    for obj in sorted(state, key=str):
        phase, step = state[obj]
        if phase == HOLD and obj not in touched:
            events.append(GateEvent("release", obj, cur_step, reason="no_baseline_move", hold_start=step))
            state[obj] = (COOL, cur_step)
    kept = set(dropped)
    out = tuple(dict(a) for i, a in enumerate(actions) if i not in kept)
    entries = tuple(sorted(((obj, phase, step) for obj, (phase, step) in state.items()), key=lambda e: str(e[0])))
    return GateResult(out, tuple(dropped), tuple(events), tuple(checks), GateMemory(entries))
