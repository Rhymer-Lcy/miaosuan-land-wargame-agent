"""EXPLORATORY mechanism-probe candidate ``t2-transport-p1`` (Sprint 22, ``docs/SPRINT22_T2_TRANSPORT_PROBE.md``).

Exploratory track: not a baseline, not eligible for promotion and never packaged. Its only authorized use is the
one-session registered transport mechanism probe of Sprint 22 (card ``s22-t2-transport-probe-1``); any other engine
use needs new owner approval.

``baseline-v2`` decides first, on the seat's own observation and memory, unchanged (:mod:`.exploratory_addon`). The
add-on then edits that decision for at most ONE infantry-carrier pair per game and only in these registered ways:

1. **embark** at the trigger: the selected infantry's ``baseline-v2`` move is replaced, in place, by the embark
   action copied from the infantry's own listing (``{actor, obj_id: infantry, type: 3, target_obj_id: carrier}``);
2. **carrier hold**: the selected carrier's ``baseline-v2`` MOVE is withheld while the pair is in a registered
   transport transition: from the trigger until the infantry is observed aboard (the embark transition), and from the
   carrier's arrival on its destination until the infantry is observed back on the ground (the stop transition and
   the disembark transition; the owner's clarification of 2026-10-07). Every other ``baseline-v2`` action of the
   carrier passes unchanged;
3. **disembark** at the destination: when the carrier's own listing offers disembark for the selected infantry, the
   carrier's ``baseline-v2`` action (if any) is replaced by the disembark action copied from that listing
   (``{actor, obj_id: carrier, type: 4, target_obj_id: infantry}``), unless the destination hex already holds the
   stacking limit of own ground units.

Outside these edits the decision is ``baseline-v2``'s, actions and order included. The carrier's route and objective
are ``baseline-v2``'s: the destination is the end hex of the first ``baseline-v2`` move emitted for the carrier after
the infantry is aboard; it is recorded, never chosen.

**Trigger** (state READY, play stage), evaluated on the seat's own observation and ``baseline-v2``'s decision: own
infantry units (type 1, sub_type 2) in ascending id, then their embark options in ascending carrier id; the first pair
where the infantry and the carrier (an own infantry fighting vehicle: type 2, sub_type 1) are both controlled by the
seat, stand in the same hex, have no move path, zero speed, no stop transition, no suppression and no embark or
disembark under way, the infantry is not on board, the carrier carries no infantry and lists infantry among its
passenger types with room under its own per-type capacity, the option's key set is exactly ``target_obj_id``, and
``baseline-v2`` emits exactly one action for each of them and it is a MOVE.

**State machine** (seat-local, deterministic): READY, EMBARK_REQUESTED, ABOARD, CARRIER_RELEASED, AT_DESTINATION,
DISEMBARK_REQUESTED, DISEMBARKED, DONE, FAILED. Every transition reads only the seat's own observation and the
bounded memory below; the conditions are in :func:`step`. Bounds (frozen, twice the documented 75-step embark and
disembark time and the 75-step stop transition): the infantry must be aboard within 150 steps of the embark order;
disembark must be listed within 150 steps of the carrier's arrival on the destination; the infantry must be back on the
ground within 150 steps of the disembark order. A failed transition ends the pair (FAILED, with a reason); from then
on the decision is ``baseline-v2``'s exactly, as it is in DONE.

**Memory**: integer pairs (field, value) in ``AddonMemory.addon``: the state, the two unit ids, the steps of the embark
order, of the aboard observation, of the arrival and of the disembark order, the destination hex, the end step and the
failure reason. Empty at the start of every game (``AddonAgent.setup``/``reset``); malformed memory is never
re-interpreted: it ends the pair (FAILED, no further edit). Nothing reads another seat's view, the all-seeing state,
the clock or randomness.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Stage
from .exploratory_addon import Addon, AddonAgent, AddonPolicy, AddonResult, is_int, is_number

CANDIDATE_ID = "t2-transport-p1"
ADDON_NAME = "t2_transport_p1"

#: Documented codes (reference_actions, reference_observations; sub_type: tank 0, infantry fighting vehicle 1,
#: infantry 2, artillery 3, unmanned ground vehicle 4, unmanned aerial vehicle 5, helicopter 6, loitering munition 7).
MOVE, EMBARK, DISEMBARK = 1, 3, 4
INFANTRY_TYPE, VEHICLE_TYPE = 1, 2
INFANTRY_SUB, IFV_SUB = 2, 1
#: Frozen mechanism constants: the documented transport time (rules: embark and disembark take 75 s each), the bound
#: of every transition (twice the documented time) and the documented stacking limit of own ground units per hex.
DOCUMENTED_TRANSITION = 75
BOUND = 150
STACK_LIMIT = 4

STATES = ("READY", "EMBARK_REQUESTED", "ABOARD", "CARRIER_RELEASED", "AT_DESTINATION", "DISEMBARK_REQUESTED",
          "DISEMBARKED", "DONE", "FAILED")
READY, EMBARK_REQUESTED, ABOARD, CARRIER_RELEASED, AT_DESTINATION, DISEMBARK_REQUESTED, DISEMBARKED, DONE, FAILED = \
    range(len(STATES))
#: The states in which the carrier's baseline-v2 MOVE is withheld.
HOLD_STATES = (EMBARK_REQUESTED, AT_DESTINATION, DISEMBARK_REQUESTED)
TERMINAL = (DONE, FAILED)

REASONS = ("", "embark not aboard within the bound", "a unit of the pair is absent",
           "inconsistent passenger state", "passenger left the carrier before disembark",
           "disembark not listed within the bound", "destination at the stacking limit",
           "disembark not completed within the bound", "carrier left the destination", "memory not interpretable")
(NO_REASON, EMBARK_TIMEOUT, UNIT_ABSENT, INCONSISTENT, PASSENGER_LEFT, NOT_LISTED, CAPACITY, DISEMBARK_TIMEOUT,
 CARRIER_LEFT, MEMORY_BAD) = range(len(REASONS))

#: Memory fields (codes of the (field, value) pairs).
FIELDS = ("state", "infantry", "carrier", "embark_step", "aboard_step", "destination", "arrival_step",
          "disembark_step", "end_step", "reason")
F_STATE, F_INF, F_CAR, F_EMBARK, F_ABOARD, F_DEST, F_ARRIVE, F_DISEMBARK, F_END, F_REASON = range(1, len(FIELDS) + 1)


# ------------------------------------------------------------------------------------------------
# memory


def encode(record: Mapping[int, int]) -> Tuple[Tuple[int, int], ...]:
    return tuple(sorted((int(k), int(v)) for k, v in record.items()))


def decode(memory: Sequence[Sequence[int]]) -> Optional[Dict[int, int]]:
    """The record, ``{}`` for an empty memory, or ``None`` when the memory cannot be interpreted."""
    record: Dict[int, int] = {}
    try:
        for pair in memory or ():
            key, value = pair
            if not (is_int(key) and is_int(value)) or key in record or not 1 <= key <= len(FIELDS):
                return None
            record[key] = value
    except (TypeError, ValueError):
        return None
    if not record:
        return {}
    if record.get(F_STATE) not in range(1, len(STATES)) or not record.get(F_INF) or not record.get(F_CAR):
        return None
    return record


# ------------------------------------------------------------------------------------------------
# reading the seat's own observation


def field(unit: Any, name: str) -> Any:
    return unit.fields.get(name)


def zero(unit: Any, name: str) -> bool:
    value = field(unit, name)
    return is_number(value) and value == 0


def quiet(unit: Any) -> bool:
    """No move path, zero speed, no stop transition, not suppressed, no embark or disembark under way, not aboard."""
    path = field(unit, "move_path")
    return (isinstance(path, (list, tuple)) and not path and zero(unit, "speed")
            and zero(unit, "move_to_stop_remain_time") and zero(unit, "keep")
            and zero(unit, "get_on_remain_time") and zero(unit, "get_off_remain_time") and zero(unit, "on_board")
            and not field(unit, "get_on_partner_id") and not field(unit, "get_off_partner_id"))


def is_class(unit: Any, unit_type: int, sub_type: int) -> bool:
    return field(unit, "type") == unit_type and field(unit, "sub_type") == sub_type


def ids(value: Any) -> List[int]:
    return [v for v in value if is_int(v)] if isinstance(value, (list, tuple)) else []


def per_type(value: Any, sub_type: int) -> Optional[int]:
    if not isinstance(value, Mapping):
        return None
    for key, count in value.items():
        if (key == sub_type or (isinstance(key, str) and key.strip() == str(sub_type))) and is_int(count):
            return count
    return None


def infantry_room(carrier: Any, passengers: Mapping[int, Any]) -> bool:
    """The carrier lists infantry among its passenger types, carries no infantry, and its own per-type capacity for
    infantry is at least one."""
    types = field(carrier, "valid_passenger_types")
    aboard = ids(field(carrier, "passenger_ids"))
    if not isinstance(types, (list, tuple)) or INFANTRY_SUB not in types:
        return False
    if any(p in passengers and field(passengers[p], "type") == INFANTRY_TYPE for p in aboard):
        return False
    capacity = per_type(field(carrier, "max_passenger_nums"), INFANTRY_SUB)
    return capacity is not None and capacity >= 1


def listed_option(valid: Mapping[int, Any], actor: int, action_type: int, target: int) -> Optional[Mapping[str, Any]]:
    """The listed option of ``action_type`` for ``actor`` whose key set is exactly ``target_obj_id`` = ``target``."""
    for option in (valid.get(actor) or {}).get(action_type) or ():
        if set(option) == {"target_obj_id"} and option.get("target_obj_id") == target:
            return option
    return None


def actions_of(actions: Sequence[Mapping[str, Any]], obj_id: int) -> List[int]:
    return [i for i, a in enumerate(actions) if a.get("obj_id") == obj_id]


class View:
    """The seat's own units, passengers, listings and controlled ids."""

    def __init__(self, observation: Observation, seat: int, faction: int) -> None:
        self.own = {u.obj_id: u for u in observation.operators() if u.color == faction}
        self.passengers = {u.obj_id: u for u in observation.passengers() if u.color == faction}
        self.valid = observation.valid_actions()
        self.controlled = set(observation.seat(seat).operators)
        self.cur_step = observation.time().cur_step

    def ground_on(self, hex_: int) -> int:
        """Own ground units (infantry and vehicles) standing on ``hex_`` (passengers excluded)."""
        return sum(1 for u in self.own.values() if u.unit_type in (INFANTRY_TYPE, VEHICLE_TYPE) and u.cur_hex == hex_)

    def aboard(self, infantry: int, carrier: int) -> Optional[bool]:
        """True aboard the carrier, False not aboard it, None inconsistent (in both lists, or aboard another unit)."""
        in_ops, in_pas = infantry in self.own, infantry in self.passengers
        car = self.own.get(carrier)
        if in_ops and in_pas:
            return None
        if not in_pas:
            return False
        p = self.passengers[infantry]
        listed = car is not None and infantry in ids(field(car, "passenger_ids"))
        if field(p, "car") != carrier or field(p, "on_board") != 1 or not listed:
            return None
        return True

    def on_ground(self, infantry: int, carrier: int) -> bool:
        car = self.own.get(carrier)
        return (infantry in self.own and infantry not in self.passengers
                and not (car is not None and infantry in ids(field(car, "passenger_ids"))))

    def settled(self, infantry: int, carrier: int, prefix: str) -> bool:
        """The embark (``get_on``) or disembark (``get_off``) transition is over on both units: zero remaining time
        and no partner listed."""
        units = [self.own.get(carrier), self.own.get(infantry) or self.passengers.get(infantry)]
        return all(u is not None and zero(u, f"{prefix}_remain_time") and not field(u, f"{prefix}_partner_id")
                   for u in units)


def trigger(view: View, actions: Sequence[Mapping[str, Any]]) -> Optional[Tuple[int, int, Mapping[str, Any]]]:
    """The first eligible (infantry, carrier, embark option), or None."""
    for inf_id in sorted(view.own):
        inf = view.own[inf_id]
        if not is_class(inf, INFANTRY_TYPE, INFANTRY_SUB) or inf_id not in view.controlled or not quiet(inf):
            continue
        mine = actions_of(actions, inf_id)
        if len(mine) != 1 or actions[mine[0]].get("type") != MOVE:
            continue
        options = [o for o in (view.valid.get(inf_id) or {}).get(EMBARK) or ()
                   if set(o) == {"target_obj_id"} and is_int(o.get("target_obj_id"))]
        for option in sorted(options, key=lambda o: o["target_obj_id"]):
            car_id = option["target_obj_id"]
            car = view.own.get(car_id)
            if car is None or not is_class(car, VEHICLE_TYPE, IFV_SUB) or car_id not in view.controlled:
                continue
            if car.cur_hex != inf.cur_hex or not quiet(car) or not infantry_room(car, view.passengers):
                continue
            theirs = actions_of(actions, car_id)
            if len(theirs) != 1 or actions[theirs[0]].get("type") != MOVE:
                continue
            return inf_id, car_id, option
    return None


# ------------------------------------------------------------------------------------------------
# one decision


def withhold_carrier_move(actions: List[Mapping[str, Any]], carrier: int, state: int,
                          changes: List[Dict[str, Any]]) -> None:
    for i in reversed(actions_of(actions, carrier)):
        if actions[i].get("type") == MOVE:
            changes.append({"kind": "carrier-move-withheld", "obj_id": carrier, "state": STATES[state],
                            "move_end": (list(actions[i].get("move_path") or ()) or [None])[-1]})
            del actions[i]


def step(observation: Observation, seat: int, faction: int, base_actions: Sequence[Mapping[str, Any]],
         memory: Sequence[Sequence[int]]) -> Tuple[Tuple[Mapping[str, Any], ...], Tuple[Dict[str, Any], ...],
                                                    Tuple[Tuple[int, int], ...], str]:
    """One decision: (actions, changes, next memory, state name after the decision)."""
    actions: List[Mapping[str, Any]] = [dict(a) for a in base_actions]
    changes: List[Dict[str, Any]] = []
    record = decode(memory)
    if record is None:
        changes.append({"kind": "transition", "from": "unknown", "to": STATES[FAILED], "reason": REASONS[MEMORY_BAD]})
        return tuple(actions), tuple(changes), encode({F_STATE: FAILED, F_INF: -1, F_CAR: -1, F_REASON: MEMORY_BAD}), \
            STATES[FAILED]
    if observation.time().stage != Stage.PLAY:
        state = record.get(F_STATE, READY)
        return tuple(actions), (), encode(record), STATES[state]
    view = View(observation, seat, faction)
    now = view.cur_step

    def go(to: int, reason: int = NO_REASON) -> None:
        changes.append({"kind": "transition", "from": STATES[record.get(F_STATE, READY)], "to": STATES[to],
                        "reason": REASONS[reason]})
        record[F_STATE] = to
        if to in TERMINAL:
            record[F_END] = now
            record[F_REASON] = reason

    if not record:
        found = trigger(view, actions)
        if found is None:
            return tuple(actions), (), (), STATES[READY]
        inf_id, car_id, option = found
        index = actions_of(actions, inf_id)[0]
        embark = {"actor": seat, "obj_id": inf_id, "type": EMBARK, "target_obj_id": option["target_obj_id"]}
        changes.append({"kind": "embark", "obj_id": inf_id, "target_obj_id": car_id,
                        "replaced_type": actions[index].get("type")})
        actions[index] = embark
        record.update({F_INF: inf_id, F_CAR: car_id, F_EMBARK: now})
        go(EMBARK_REQUESTED)
        withhold_carrier_move(actions, car_id, EMBARK_REQUESTED, changes)
        return tuple(actions), tuple(changes), encode(record), STATES[record[F_STATE]]

    inf_id, car_id = record[F_INF], record[F_CAR]
    state = record[F_STATE]
    if state in TERMINAL:
        return tuple(actions), (), encode(record), STATES[state]
    car = view.own.get(car_id)
    aboard = view.aboard(inf_id, car_id)

    # Inside a transition (EMBARK_REQUESTED, DISEMBARK_REQUESTED) the infantry may be between the two lists for a
    # step: the pair waits, within the bound. Outside it, the infantry must be aboard at every decision.
    if state == EMBARK_REQUESTED:
        if car is None:
            go(FAILED, UNIT_ABSENT)
        elif aboard is None:
            go(FAILED, INCONSISTENT)
        elif aboard and view.settled(inf_id, car_id, "get_on"):
            record[F_ABOARD] = now
            go(ABOARD)
            go(CARRIER_RELEASED)
        elif now - record[F_EMBARK] > BOUND:
            go(FAILED, EMBARK_TIMEOUT)
        else:
            withhold_carrier_move(actions, car_id, EMBARK_REQUESTED, changes)
    elif state in (CARRIER_RELEASED, AT_DESTINATION):
        if car is None or not (inf_id in view.own or inf_id in view.passengers):
            go(FAILED, UNIT_ABSENT)
        elif aboard is None:
            go(FAILED, INCONSISTENT)
        elif not aboard:
            go(FAILED, PASSENGER_LEFT)
    elif state == DISEMBARK_REQUESTED:
        if car is None:
            go(FAILED, UNIT_ABSENT)
        elif aboard is None:
            go(FAILED, INCONSISTENT)
        elif car.cur_hex != record.get(F_DEST):
            go(FAILED, CARRIER_LEFT)
        elif view.on_ground(inf_id, car_id) and view.settled(inf_id, car_id, "get_off"):
            go(DISEMBARKED)
            go(DONE)
        elif now - record[F_DISEMBARK] > BOUND:
            go(FAILED, DISEMBARK_TIMEOUT)
        else:
            withhold_carrier_move(actions, car_id, DISEMBARK_REQUESTED, changes)

    if record[F_STATE] == CARRIER_RELEASED:
        if not record.get(F_DEST):
            mine = actions_of(actions, car_id)
            moves = [actions[i] for i in mine if actions[i].get("type") == MOVE]
            path = list(moves[0].get("move_path") or ()) if moves else []
            if path and is_int(path[-1]):
                record[F_DEST] = path[-1]
                changes.append({"kind": "destination", "obj_id": car_id, "hex": path[-1]})
        dest = record.get(F_DEST)
        if dest and car.cur_hex == dest and not (field(car, "move_path") or ()):
            record[F_ARRIVE] = now
            go(AT_DESTINATION)

    if record[F_STATE] == AT_DESTINATION:
        dest = record[F_DEST]
        option = listed_option(view.valid, car_id, DISEMBARK, inf_id)
        if car.cur_hex != dest:
            go(FAILED, CARRIER_LEFT)
        elif option is not None:
            if view.ground_on(dest) >= STACK_LIMIT:
                go(FAILED, CAPACITY)
            else:
                disembark = {"actor": seat, "obj_id": car_id, "type": DISEMBARK, "target_obj_id": option["target_obj_id"]}
                mine = actions_of(actions, car_id)
                changes.append({"kind": "disembark", "obj_id": car_id, "target_obj_id": inf_id,
                                "replaced_type": actions[mine[0]].get("type") if mine else None})
                if mine:
                    actions[mine[0]] = disembark
                    for i in reversed(mine[1:]):
                        del actions[i]
                else:
                    actions.append(disembark)
                record[F_DISEMBARK] = now
                go(DISEMBARK_REQUESTED)
        elif now - record[F_ARRIVE] > BOUND:
            go(FAILED, CAPACITY if view.ground_on(dest) >= STACK_LIMIT else NOT_LISTED)
        else:
            withhold_carrier_move(actions, car_id, AT_DESTINATION, changes)

    return tuple(actions), tuple(changes), encode(record), STATES[record[F_STATE]]


class TransportAddon(Addon):
    name = ADDON_NAME

    def apply(self, observation: Observation, seat: int, faction: int, base,
              memory: Tuple[Tuple[int, int], ...]) -> AddonResult:
        try:
            actions, changes, memory_out, state = step(observation, seat, faction, tuple(base.actions), memory)
        except ContractError:
            raise
        return AddonResult(actions, changes, ((f"state {state}", 1),), memory_out)


class TransportPolicy(AddonPolicy):
    identity = CANDIDATE_ID
    addon_class = TransportAddon


class TransportAgent(AddonAgent):
    policy_class = TransportPolicy
