"""PROPOSED - NON-EXECUTABLE - UNAPPROVED exploratory candidate ``t2-transport-x1`` (Sprint 23,
``docs/SPRINT23_T2_POLICY_DESIGN.md``).

Offline design only. No run card may name this identity, no runner or game entry point imports it, and its agent
class refuses ``setup``: any engine use needs a new owner approval and a registered study. It exists so that the
proposed policy is specified exactly, tested, and replayed on recorded states.

It generalises Sprint 22's mechanically supported one-pair transport (``t2_transport_p1``, imported unchanged for its
observation helpers and constants) from one selected infantry-carrier pair to every independent eligible pair of the
seat, with the same three intervention classes and nothing else:

A. **embark**: a selected infantry's ``baseline-v2`` MOVE is replaced, in place, by the embark action copied from the
   infantry's own listing (``{actor, obj_id: infantry, type: 3, target_obj_id: carrier}``);
B. **carrier hold**: the selected carrier's ``baseline-v2`` MOVE is withheld during the embark transition and, at the
   registered objective, while the carrier settles and the infantry disembarks; every other ``baseline-v2`` action of
   the carrier passes;
C. **disembark** at the registered objective: when the carrier's own listing offers disembark for the infantry and the
   hex holds fewer than the stacking limit of own ground units, the carrier's ``baseline-v2`` action (if any) is
   replaced by the disembark copied from that listing (``{actor, obj_id: carrier, type: 4, target_obj_id: infantry}``).

Failure handling R (bounded recovery of a live passenger; not a tactical edit): when an episode fails with the infantry
still aboard, the carrier is released to ``baseline-v2``; at most ``RECOVERY_ATTEMPTS`` times, when the carrier next
stands without a move path on a hex below the stacking limit, its MOVE is withheld (class B) until disembark is listed
there and the listed disembark is issued (class C's action at that hex), each attempt bounded like the registered
transitions. After the last attempt the episode is STRANDED and the infantry stays aboard: an exclusion from engine
readiness that the screen proposal must carry as a registered stop.

**Trigger** (play stage; evaluated on the seat's own observation and ``baseline-v2``'s decision; conditions in the
order :data:`CONDITIONS` records them): (1) an own infantry (type 1, sub_type 2) and an own infantry fighting vehicle
(type 2, sub_type 1) stand in the same hex, both as operators; (2) both are controlled by the seat, stationary (no move
path, zero speed, no stop transition), not suppressed, not in an embark or disembark, the infantry not aboard, and
neither has been in an episode of this game; (3) the infantry's listing offers embark naming that carrier with the key
set exactly ``target_obj_id``; (4) ``baseline-v2`` emits exactly one action for each and it is a MOVE with a route;
(5) both routes end on the same hex and it is an objective; (6) the infantry has no competitive timely arrival on foot
(its free-flow arrival is at or after the end of the game, or later than the transported one); (7) the transported
arrival is before the end and strictly earlier than the foot arrival; (8) the carrier lists infantry among its
passenger types, carries no infantry and has infantry capacity; (9) the destination admits the episode (section
"admission" below).

**Time model** (frozen; documented transitions): transported arrival = trigger step + embark (75) + the carrier's
free-flow time along its ``baseline-v2`` route + the stop transition (75) + disembark (75); foot arrival = trigger step
+ the infantry's free-flow time along its own ``baseline-v2`` route (``720 / basic_speed * cost`` per hex,
``t9_batch.path_times``). A projected mechanical quantity, not a prediction of the game.

**Matching** (deterministic, seat-local): the pairs that pass conditions 1 to 8 are ranked by larger projected saving,
then infantry unable to arrive on foot before the end first, then earlier transported arrival, then infantry id, then
carrier id; in that order a pair is selected unless its infantry or its carrier was already selected at this decision
(an infantry conflict or a carrier conflict) or its destination does not admit it.

**Admission** (condition 9, current occupancy and bounded own reservations only): own ground units standing on the
destination now, plus the places still needed by this seat's active episodes to that destination (one for a carrier
not yet standing there, one for an infantry not yet on the ground there), plus two places for every pair already
selected to it at this decision, plus two for the pair itself, must not exceed the stacking limit of 4.

**Episode states**: EMBARK_REQUESTED, CARRIER_RELEASED, AT_DESTINATION, DISEMBARK_REQUESTED, then the recovery states
RECOVERY_WAIT, RECOVERY_HOLD, RECOVERY_DISEMBARK, and the terminal states DONE, FAILED_GROUND (ended with the infantry
on the ground before carriage), RECOVERED, STRANDED, LOST (a unit absent) and INCONSISTENT. Every transition reads only
the seat's own observation and the bounded memory below; :func:`advance` holds the conditions. ABOARD and DISEMBARKED of
Sprint 22 are instantaneous here (the release and DONE happen at the decision they are observed).

**Memory**: integer pairs ``(index * SLOT + field, value)`` in ``AddonMemory.addon``, one block per episode in the order
the episodes began; at most one episode per own infantry. Empty at the start of every game. Memory that cannot be
interpreted disables the add-on for the rest of the game (no edit). Nothing reads another seat's view, the all-seeing
state, the clock or randomness.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from . import t2_transport_p1 as p1
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int
from .t9_batch import path_times

CANDIDATE_ID = "t2-transport-x1"
ADDON_NAME = "t2_transport_x1"
STATUS = "PROPOSED - NON-EXECUTABLE - UNAPPROVED"
EXECUTABLE = False

MOVE, EMBARK, DISEMBARK = p1.MOVE, p1.EMBARK, p1.DISEMBARK
INFANTRY_TYPE, VEHICLE_TYPE, INFANTRY_SUB, IFV_SUB = p1.INFANTRY_TYPE, p1.VEHICLE_TYPE, p1.INFANTRY_SUB, p1.IFV_SUB
#: Sprint 22's frozen constants, unchanged: the documented transition (75), the bound of every transition (150) and the
#: stacking limit of own ground units per hex (4).
TRANSITION, BOUND, STACK_LIMIT = p1.DOCUMENTED_TRANSITION, p1.BOUND, p1.STACK_LIMIT
#: Transitions of the transport chain the time model adds to the carrier's free flow: embark, the carrier's stop
#: transition on arrival, disembark.
CHAIN_TRANSITIONS = 3
#: Own ground places an episode adds to its destination at disembark: the carrier and the infantry.
PLACES = 2
#: Bounded recovery attempts of a live passenger after a failed episode.
RECOVERY_ATTEMPTS = 2

STATES = ("EMBARK_REQUESTED", "CARRIER_RELEASED", "AT_DESTINATION", "DISEMBARK_REQUESTED", "RECOVERY_WAIT",
          "RECOVERY_HOLD", "RECOVERY_DISEMBARK", "DONE", "FAILED_GROUND", "RECOVERED", "STRANDED", "LOST",
          "INCONSISTENT")
(EMBARK_REQUESTED, CARRIER_RELEASED, AT_DESTINATION, DISEMBARK_REQUESTED, RECOVERY_WAIT, RECOVERY_HOLD,
 RECOVERY_DISEMBARK, DONE, FAILED_GROUND, RECOVERED, STRANDED, LOST, INCONSISTENT) = range(1, len(STATES) + 1)
#: States heading for the registered destination (their places count in the admission).
TO_DESTINATION = (EMBARK_REQUESTED, CARRIER_RELEASED, AT_DESTINATION, DISEMBARK_REQUESTED)
#: States in which the carrier's baseline-v2 MOVE is withheld.
HOLD_STATES = (EMBARK_REQUESTED, AT_DESTINATION, DISEMBARK_REQUESTED, RECOVERY_HOLD, RECOVERY_DISEMBARK)
TERMINAL = (DONE, FAILED_GROUND, RECOVERED, STRANDED, LOST, INCONSISTENT)

REASONS = ("", "embark not taken or interrupted", "embark not aboard within the bound", "a unit of the pair is absent",
           "inconsistent passenger state", "passenger left the carrier", "carrier not on the destination within the bound",
           "carrier left the destination", "disembark not listed within the bound", "destination at the stacking limit",
           "disembark not completed within the bound", "recovery attempts exhausted", "recovery hold ended")
(NO_REASON, EMBARK_NOT_TAKEN, EMBARK_TIMEOUT, UNIT_ABSENT, INCONSISTENT_STATE, PASSENGER_LEFT, TRANSIT_TIMEOUT,
 CARRIER_LEFT, NOT_LISTED, CAPACITY, DISEMBARK_TIMEOUT, EXHAUSTED, HOLD_ENDED) = range(len(REASONS))

FIELDS = ("state", "infantry", "carrier", "destination", "embark_step", "carrier_free_flow", "release_step",
          "arrival_step", "disembark_step", "end_step", "reason", "attempts", "hold_step", "hold_hex")
(F_STATE, F_INF, F_CAR, F_DEST, F_EMBARK, F_FF, F_RELEASE, F_ARRIVE, F_DISEMBARK, F_END, F_REASON, F_ATTEMPTS,
 F_HOLD_STEP, F_HOLD_HEX) = range(1, len(FIELDS) + 1)
REQUIRED = (F_STATE, F_INF, F_CAR, F_DEST, F_EMBARK, F_FF)
SLOT = 32
#: The memory of a disabled add-on (memory that could not be interpreted).
DISABLED = ((0, 1),)

CONDITIONS = ("c2_eligible", "c3_listing", "c4_both_move", "c5_same_objective", "c6_no_timely_foot",
              "c7_positive_saving", "c8_capacity")
OUTCOMES = ("selected", "infantry_conflict", "carrier_conflict", "c9_destination")

FreeFlow = Callable[[Any, Sequence[Any]], Optional[int]]


# ------------------------------------------------------------------------------------------------
# memory


def encode(episodes: Sequence[Mapping[int, int]]) -> Tuple[Tuple[int, int], ...]:
    return tuple(sorted((index * SLOT + int(k), int(v)) for index, ep in enumerate(episodes) for k, v in ep.items()))


def decode(memory: Sequence[Sequence[int]]) -> Optional[List[Dict[int, int]]]:
    """The episodes in the order they began, ``[]`` for an empty memory, or ``None`` when the memory cannot be
    interpreted (including the disabled marker)."""
    blocks: Dict[int, Dict[int, int]] = {}
    try:
        for pair in memory or ():
            key, value = pair
            if not (is_int(key) and is_int(value)):
                return None
            index, name = divmod(key, SLOT)
            if index < 0 or not 1 <= name <= len(FIELDS) or name in blocks.get(index, {}):
                return None
            blocks.setdefault(index, {})[name] = value
    except (TypeError, ValueError):
        return None
    if sorted(blocks) != list(range(len(blocks))):
        return None
    episodes = [blocks[i] for i in range(len(blocks))]
    for ep in episodes:
        if any(f not in ep for f in REQUIRED) or ep[F_STATE] not in range(1, len(STATES) + 1):
            return None
    units = [ep[F_INF] for ep in episodes] + [ep[F_CAR] for ep in episodes]
    if len(set(units)) != len(units):
        return None
    return episodes


# ------------------------------------------------------------------------------------------------
# reading the seat's own observation


def moving(unit: Any) -> bool:
    return bool(p1.field(unit, "move_path") or ())


def uncontrolled(view: p1.View, unit_id: int) -> bool:
    return unit_id not in view.controlled


def is_objective(observation: Observation, hex_: Any) -> bool:
    return any(city.coord == hex_ for city in observation.cities() or ())


def timing(trigger_step: int, max_step: int, infantry_ff: Optional[int], carrier_ff: Optional[int]
           ) -> Optional[Tuple[int, int, int, bool]]:
    """(transported arrival, foot arrival, projected saving, infantry unable to arrive on foot before the end), or
    None when a free-flow time is unreadable."""
    if infantry_ff is None or carrier_ff is None:
        return None
    transported = trigger_step + CHAIN_TRANSITIONS * TRANSITION + carrier_ff
    foot = trigger_step + infantry_ff
    return transported, foot, foot - transported, foot >= max_step


def time_condition(transported: int, foot: int, max_step: int) -> Optional[str]:
    """Conditions 6 and 7: the first one failed, or None. Condition 6: the foot arrival is at or after the end, or
    later than the transported one. Condition 7: the transported arrival is strictly before the end and strictly
    earlier than the foot arrival."""
    if not (foot >= max_step or foot > transported):
        return "c6_no_timely_foot"
    if not (transported < max_step and foot - transported > 0):
        return "c7_positive_saving"
    return None


@dataclass(frozen=True)
class Pair:
    """One co-located own infantry-IFV pair at one decision, with the first trigger condition it fails (``None`` when it
    passes conditions 2 to 8) and its projected times."""

    infantry: int
    carrier: int
    shared_hex: int
    failed: Optional[str]
    destination: Optional[int] = None
    option: Optional[Tuple[Tuple[str, Any], ...]] = None
    infantry_free_flow: Optional[int] = None
    carrier_free_flow: Optional[int] = None
    transported_arrival: Optional[int] = None
    foot_arrival: Optional[int] = None
    saving: Optional[int] = None
    unable_on_foot: bool = False


def rank_key(pair: Pair) -> Tuple[Any, ...]:
    """The frozen matching order: larger saving, infantry unable to arrive on foot first, earlier transported arrival,
    infantry id, carrier id."""
    return (-(pair.saving or 0), not pair.unable_on_foot, pair.transported_arrival or 0, pair.infantry, pair.carrier)


def id_key(pair: Pair) -> Tuple[Any, ...]:
    """The sensitivity order (not the candidate's): infantry id, then carrier id, as Sprint 22's single-pair trigger."""
    return (pair.infantry, pair.carrier)


def pairs(observation: Observation, view: p1.View, actions: Sequence[Mapping[str, Any]], used: Sequence[int],
          free_flow: FreeFlow) -> List[Pair]:
    """Every co-located own infantry-IFV pair (both operators), with its first failed condition and its times."""
    now = view.cur_step
    max_step = observation.time().max_step
    infantry = sorted(u for u, x in view.own.items() if p1.is_class(x, INFANTRY_TYPE, INFANTRY_SUB))
    carriers = sorted(u for u, x in view.own.items() if p1.is_class(x, VEHICLE_TYPE, IFV_SUB))
    out: List[Pair] = []
    for inf_id in infantry:
        inf = view.own[inf_id]
        for car_id in carriers:
            car = view.own[car_id]
            if car.cur_hex != inf.cur_hex:
                continue
            base = dict(infantry=inf_id, carrier=car_id, shared_hex=inf.cur_hex)
            if (inf_id in used or car_id in used or uncontrolled(view, inf_id) or uncontrolled(view, car_id)
                    or not p1.quiet(inf) or not p1.quiet(car)):
                out.append(Pair(**base, failed="c2_eligible"))
                continue
            option = p1.listed_option(view.valid, inf_id, EMBARK, car_id)
            if option is None:
                out.append(Pair(**base, failed="c3_listing"))
                continue
            mine, theirs = p1.actions_of(actions, inf_id), p1.actions_of(actions, car_id)
            if (len(mine) != 1 or len(theirs) != 1 or actions[mine[0]].get("type") != MOVE
                    or actions[theirs[0]].get("type") != MOVE or not actions[mine[0]].get("move_path")
                    or not actions[theirs[0]].get("move_path")):
                out.append(Pair(**base, failed="c4_both_move"))
                continue
            inf_path, car_path = list(actions[mine[0]]["move_path"]), list(actions[theirs[0]]["move_path"])
            dest = car_path[-1]
            if inf_path[-1] != dest or not is_objective(observation, dest):
                out.append(Pair(**base, failed="c5_same_objective"))
                continue
            t_inf, t_car = free_flow(inf, inf_path), free_flow(car, car_path)
            times = timing(now, max_step, t_inf, t_car)
            extra = dict(destination=dest, option=tuple(sorted(option.items())), infantry_free_flow=t_inf,
                         carrier_free_flow=t_car)
            if times is None:
                out.append(Pair(**base, **extra, failed="c7_positive_saving"))
                continue
            transported, foot, saving, cannot = times
            extra.update(transported_arrival=transported, foot_arrival=foot, saving=saving, unable_on_foot=cannot)
            failed_time = time_condition(transported, foot, max_step)
            if failed_time is not None:
                out.append(Pair(**base, **extra, failed=failed_time))
            elif not p1.infantry_room(car, view.passengers):
                out.append(Pair(**base, **extra, failed="c8_capacity"))
            else:
                out.append(Pair(**base, **extra, failed=None))
    return out


def reservations(view: p1.View, episodes: Sequence[Mapping[int, int]]) -> Dict[int, int]:
    """Places still needed at each destination by the seat's active episodes heading there: one for a carrier not
    standing on it, one for an infantry not on the ground there."""
    need: Dict[int, int] = collections.Counter()
    for ep in episodes:
        if ep[F_STATE] not in TO_DESTINATION:
            continue
        dest = ep[F_DEST]
        car, inf = view.own.get(ep[F_CAR]), view.own.get(ep[F_INF])
        need[dest] += (0 if car is not None and car.cur_hex == dest else 1)
        need[dest] += (0 if inf is not None and inf.cur_hex == dest and ep[F_INF] not in view.passengers else 1)
    return dict(need)


def match(candidates: Sequence[Pair], view: p1.View, reserved: Mapping[int, int],
          order: Callable[[Pair], Tuple[Any, ...]] = rank_key) -> Tuple[List[Pair], Dict[Tuple[int, int], str]]:
    """The selected pairs in ``order`` and the outcome of every pair that passed conditions 2 to 8."""
    taken_inf: set = set()
    taken_car: set = set()
    added: Dict[int, int] = collections.Counter()
    selected: List[Pair] = []
    outcome: Dict[Tuple[int, int], str] = {}
    for pair in sorted((p for p in candidates if p.failed is None), key=order):
        key = (pair.infantry, pair.carrier)
        if pair.infantry in taken_inf:
            outcome[key] = "infantry_conflict"
        elif pair.carrier in taken_car:
            outcome[key] = "carrier_conflict"
        elif (view.ground_on(pair.destination) + reserved.get(pair.destination, 0)
              + PLACES * (added[pair.destination] + 1)) > STACK_LIMIT:
            outcome[key] = "c9_destination"
        else:
            outcome[key] = "selected"
            selected.append(pair)
            taken_inf.add(pair.infantry)
            taken_car.add(pair.carrier)
            added[pair.destination] += 1
    return selected, outcome


# ------------------------------------------------------------------------------------------------
# one episode at one decision


def advance(ep: Dict[int, int], view: p1.View, go: Callable[[Dict[int, int], int, int], None]) -> Any:
    """Moves one non-terminal episode on from the current observation. Returns ``"hold"`` (withhold the carrier's
    MOVE), ``("disembark", option)`` (issue the listed disembark from the carrier) or ``None`` (no edit)."""
    now = view.cur_step
    inf, car = ep[F_INF], ep[F_CAR]
    carrier = view.own.get(car)
    if carrier is None:
        go(ep, LOST, UNIT_ABSENT)
        return None
    if not (inf in view.own or inf in view.passengers):
        # Inside an embark or disembark transition the infantry may be in neither list for a step (Sprint 22's
        # reading): the pair waits within the transition's bound; anywhere else, or after the bound, it is lost.
        since = {EMBARK_REQUESTED: F_EMBARK, DISEMBARK_REQUESTED: F_DISEMBARK, RECOVERY_DISEMBARK: F_DISEMBARK}
        if ep[F_STATE] in since and now - ep[since[ep[F_STATE]]] <= BOUND:
            return "hold"
        go(ep, LOST, UNIT_ABSENT)
        return None
    aboard = view.aboard(inf, car)
    if aboard is None:
        go(ep, INCONSISTENT, INCONSISTENT_STATE)
        return None

    def to_recovery(reason: int) -> None:
        if ep.get(F_ATTEMPTS, 0) < RECOVERY_ATTEMPTS:
            ep[F_HOLD_STEP] = now  # a recovery hold may start only at a later decision: the carrier is released now
            go(ep, RECOVERY_WAIT, reason)
        else:
            go(ep, STRANDED, EXHAUSTED)

    def disembark_option() -> Optional[Mapping[str, Any]]:
        option = p1.listed_option(view.valid, car, DISEMBARK, inf)
        return option if option is not None and view.ground_on(carrier.cur_hex) < STACK_LIMIT else None

    state = ep[F_STATE]
    if state == EMBARK_REQUESTED:
        if aboard and view.settled(inf, car, "get_on"):
            ep[F_RELEASE] = now
            go(ep, CARRIER_RELEASED, NO_REASON)
        elif not aboard and inf in view.own and view.settled(inf, car, "get_on") and now > ep[F_EMBARK]:
            go(ep, FAILED_GROUND, EMBARK_NOT_TAKEN)
            return None
        elif now - ep[F_EMBARK] > BOUND:
            go(ep, FAILED_GROUND, EMBARK_TIMEOUT)
            return None
        else:
            return "hold"
    if ep[F_STATE] == CARRIER_RELEASED:
        if not aboard:
            go(ep, FAILED_GROUND, PASSENGER_LEFT)
            return None
        if carrier.cur_hex == ep[F_DEST] and not moving(carrier):
            ep[F_ARRIVE] = now
            go(ep, AT_DESTINATION, NO_REASON)
        elif now > ep[F_RELEASE] + ep[F_FF] + BOUND:
            to_recovery(TRANSIT_TIMEOUT)
        else:
            return None
    if ep[F_STATE] == AT_DESTINATION:
        if not aboard:
            go(ep, FAILED_GROUND, PASSENGER_LEFT)
            return None
        if carrier.cur_hex != ep[F_DEST]:
            to_recovery(CARRIER_LEFT)
        else:
            option = disembark_option()
            if option is not None:
                ep[F_DISEMBARK] = now
                go(ep, DISEMBARK_REQUESTED, NO_REASON)
                return ("disembark", option)
            if now - ep[F_ARRIVE] > BOUND:
                to_recovery(CAPACITY if view.ground_on(ep[F_DEST]) >= STACK_LIMIT else NOT_LISTED)
            else:
                return "hold"
    if ep[F_STATE] in (DISEMBARK_REQUESTED, RECOVERY_DISEMBARK):
        where = ep[F_DEST] if ep[F_STATE] == DISEMBARK_REQUESTED else ep[F_HOLD_HEX]
        done = DONE if ep[F_STATE] == DISEMBARK_REQUESTED else RECOVERED
        if view.on_ground(inf, car) and view.settled(inf, car, "get_off"):
            go(ep, done, NO_REASON)
            return None
        if carrier.cur_hex != where:
            to_recovery(CARRIER_LEFT)
        elif now - ep[F_DISEMBARK] > BOUND:
            to_recovery(DISEMBARK_TIMEOUT)
        else:
            if aboard and view.settled(inf, car, "get_off") and now > ep[F_DISEMBARK]:
                option = disembark_option()
                if option is not None:
                    return ("disembark", option)  # bounded re-issue after an interrupted or refused disembark
            return "hold"
    if ep[F_STATE] == RECOVERY_WAIT:
        if not aboard:
            go(ep, RECOVERED, NO_REASON)
            return None
        if now <= ep.get(F_HOLD_STEP, now) or moving(carrier) or view.ground_on(carrier.cur_hex) >= STACK_LIMIT:
            return None
        ep[F_ATTEMPTS] = ep.get(F_ATTEMPTS, 0) + 1
        ep[F_HOLD_STEP], ep[F_HOLD_HEX] = now, carrier.cur_hex
        go(ep, RECOVERY_HOLD, NO_REASON)
    if ep[F_STATE] == RECOVERY_HOLD:
        if not aboard:
            go(ep, RECOVERED, NO_REASON)
            return None
        if carrier.cur_hex != ep[F_HOLD_HEX]:
            to_recovery(HOLD_ENDED)
            return None
        option = disembark_option()
        if option is not None:
            ep[F_DISEMBARK] = now
            go(ep, RECOVERY_DISEMBARK, NO_REASON)
            return ("disembark", option)
        if now - ep[F_HOLD_STEP] > BOUND:
            to_recovery(HOLD_ENDED)
            return None
        return "hold"
    return None


# ------------------------------------------------------------------------------------------------
# one decision


def withhold_move(actions: List[Mapping[str, Any]], carrier: int, changes: List[Dict[str, Any]], state: str) -> None:
    for i in reversed(p1.actions_of(actions, carrier)):
        if actions[i].get("type") == MOVE:
            changes.append({"kind": "carrier-move-withheld", "obj_id": carrier, "state": state})
            del actions[i]


def issue_disembark(actions: List[Mapping[str, Any]], seat: int, carrier: int, option: Mapping[str, Any],
                    changes: List[Dict[str, Any]]) -> None:
    disembark = {"actor": seat, "obj_id": carrier, "type": DISEMBARK, "target_obj_id": option["target_obj_id"]}
    mine = p1.actions_of(actions, carrier)
    changes.append({"kind": "disembark", "obj_id": carrier, "target_obj_id": option["target_obj_id"],
                    "replaced_type": actions[mine[0]].get("type") if mine else None})
    if mine:
        actions[mine[0]] = disembark
        for i in reversed(mine[1:]):
            del actions[i]
    else:
        actions.append(disembark)


def step(observation: Observation, seat: int, faction: int, base_actions: Sequence[Mapping[str, Any]],
         memory: Sequence[Sequence[int]], free_flow: FreeFlow
         ) -> Tuple[Tuple[Mapping[str, Any], ...], Tuple[Dict[str, Any], ...], Tuple[Tuple[int, int], ...]]:
    """One decision: (actions, changes, next memory)."""
    actions: List[Mapping[str, Any]] = [dict(a) for a in base_actions]
    if tuple(tuple(p) for p in memory or ()) == DISABLED:
        return tuple(actions), (), DISABLED
    episodes = decode(memory)
    if episodes is None:
        return tuple(actions), ({"kind": "disabled", "reason": "memory not interpretable"},), DISABLED
    if observation.time().stage != Stage.PLAY:
        return tuple(actions), (), encode(episodes)
    view = p1.View(observation, seat, faction)
    changes: List[Dict[str, Any]] = []

    def go(ep: Dict[int, int], to: int, reason: int) -> None:
        changes.append({"kind": "transition", "infantry": ep[F_INF], "from": STATES[ep[F_STATE] - 1],
                        "to": STATES[to - 1], "reason": REASONS[reason]})
        ep[F_STATE] = to
        if to in TERMINAL:
            ep[F_END] = view.cur_step
            ep[F_REASON] = reason

    for ep in episodes:
        if ep[F_STATE] in TERMINAL:
            continue
        edit = advance(ep, view, go)
        if edit == "hold":
            withhold_move(actions, ep[F_CAR], changes, STATES[ep[F_STATE] - 1])
        elif isinstance(edit, tuple):
            issue_disembark(actions, seat, ep[F_CAR], edit[1], changes)

    used = [ep[F_INF] for ep in episodes] + [ep[F_CAR] for ep in episodes]
    candidates = pairs(observation, view, actions, used, free_flow)
    selected, _ = match(candidates, view, reservations(view, episodes))
    for pair in selected:
        index = p1.actions_of(actions, pair.infantry)[0]
        option = dict(pair.option or ())
        changes.append({"kind": "embark", "obj_id": pair.infantry, "target_obj_id": pair.carrier,
                        "replaced_type": actions[index].get("type"), "saving": pair.saving})
        actions[index] = {"actor": seat, "obj_id": pair.infantry, "type": EMBARK,
                          "target_obj_id": option["target_obj_id"]}
        ep = {F_STATE: EMBARK_REQUESTED, F_INF: pair.infantry, F_CAR: pair.carrier, F_DEST: pair.destination,
              F_EMBARK: view.cur_step, F_FF: pair.carrier_free_flow}
        changes.append({"kind": "transition", "infantry": pair.infantry, "from": "READY", "to": "EMBARK_REQUESTED",
                        "reason": ""})
        episodes.append(ep)
        withhold_move(actions, pair.carrier, changes, "EMBARK_REQUESTED")
    return tuple(actions), tuple(changes), encode(episodes)


def router_free_flow(router: Any) -> FreeFlow:
    """Free-flow time of ``path`` for ``unit`` (an :class:`Observation` operator) on ``router``'s cost data."""

    def free_flow(unit: Any, path: Sequence[Any]) -> Optional[int]:
        times, _ = path_times(router, p1.field(unit, "type"), p1.field(unit, "move_state"),
                              p1.field(unit, "basic_speed"), unit.cur_hex, list(path))
        return None if times is None else sum(times)

    return free_flow


class TransportXAddon(Addon):
    name = ADDON_NAME

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        try:
            actions, changes, memory_out = step(observation, seat, faction, tuple(base.actions), memory,
                                                router_free_flow(self.baseline.router))
        except ContractError:
            raise
        return AddonResult(actions, changes, (), memory_out)


class TransportXPolicy(AddonPolicy):
    """Offline replay only (``EXECUTABLE`` is False)."""

    identity = CANDIDATE_ID
    addon_class = TransportXAddon


class TransportXAgent(AddonAgent):
    """Refuses to set up: the identity is proposed, non-executable and unapproved."""

    policy_class = TransportXPolicy

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        raise RuntimeError(f"{CANDIDATE_ID} is {STATUS}: no engine use without a new owner approval")
