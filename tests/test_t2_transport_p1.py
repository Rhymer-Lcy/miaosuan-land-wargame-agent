"""The Sprint 22 mechanism-probe candidate ``t2-transport-p1`` (``experiments/t2_transport_p1.py``).
SYNTHETIC observations on the 10 x 10 synthetic map (``tests/fixtures/synthetic.py``); routes and costs come from the
project's router, never typed by hand.

What is pinned here: the trigger (exact pair, same hex, stationarity, suppression, transitions, capacity, a carrier
already carrying infantry, the listing and its key set, baseline-v2's MOVE for both units); the embark and disembark
actions are copies of the listed options; the infantry's move is replaced in place and nothing else changes; the
carrier's MOVE is withheld exactly in the hold states and its other actions pass; every transition of the state
machine and every bound at its exact boundary; the stacking limit at 3 and 4 own ground units; the destination is the
end of baseline-v2's first carrier move after release; unit disappearance, inconsistent representation, a passenger
leaving early and a carrier leaving the destination end the pair; malformed memory never edits; memory is empty in every
game; and, in a stand-in transport world that plays the real baseline-v2, the complete chain embark, carry, arrival,
hold, disembark runs with every difference from baseline-v2 a registered edit.
"""

from __future__ import annotations

import ast
import copy
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision.routing import Router, move_mode
from miaosuan_agent.evaluation import s22_probe as sp
from miaosuan_agent.experiments import t2_transport_p1 as t2
from miaosuan_agent.experiments.exploratory_addon import AddonMemory
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
SEAT, RED, BLUE = syn.RED_SEAT, 0, 1
INF, CAR, CAR2, OTHER, INF2 = 900301, 900302, 900303, 900304, 900305
START, DEST, FAR = 202, 505, 909
COSTS = MoveCosts.from_raw(syn.cost_data())
ROUTER = Router(COSTS)


def route(start: int, goal: int, unit_type: int = 2) -> List[int]:
    return list(ROUTER.shortest_paths(start, move_mode(unit_type, 0)).path_to(goal))


def unit(obj_id: int, hex_: int, *, kind: str = "ifv", color: int = RED, **extra: Any) -> Dict[str, Any]:
    unit_type, sub_type = {"ifv": (2, 1), "infantry": (1, 2), "tank": (2, 0), "munition": (3, 7)}[kind]
    record = {"obj_id": obj_id, "color": color, "type": unit_type, "sub_type": sub_type, "cur_hex": hex_,
              "move_state": 0, "move_path": [], "speed": 0, "move_to_stop_remain_time": 0, "keep": 0, "on_board": 0,
              "car": None, "passenger_ids": [], "get_on_remain_time": 0, "get_on_partner_id": [],
              "get_off_remain_time": 0, "get_off_partner_id": [], "basic_speed": 36 if unit_type == 2 else 5,
              "valid_passenger_types": [2, 4, 7] if kind == "ifv" else [], "stop": 1,
              "max_passenger_nums": {2: 1, 4: 1, 7: 2} if kind == "ifv" else {}}
    record.update(extra)
    return record


def raw_observation(units: Sequence[Dict[str, Any]], passengers: Sequence[Dict[str, Any]] = (),
                    valid: Optional[Dict[int, Any]] = None, *, cur_step: int = 100, stage: int = 2,
                    cities: Sequence[int] = (DEST, FAR), held: Sequence[int] = (),
                    controlled: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    own = [u["obj_id"] for u in list(units) + list(passengers) if u["color"] == RED]
    raw = syn.build_observation(units=units, valid_actions=dict(valid or {}), stage=stage, cur_step=cur_step,
                                seats={SEAT: syn.seat_record(SEAT, RED, own if controlled is None else controlled,
                                                             True)},
                                cities=[syn.city(c, flag=RED if c in held else -1) for c in cities])
    raw["passengers"] = [dict(p) for p in passengers]
    raw["time"]["max_step"] = 2880
    return raw


def obs(*args: Any, **kwargs: Any) -> Observation:
    return Observation.from_raw(raw_observation(*args, **kwargs), Origin.ENGINE)


def move(obj_id: int, start: int, goal: int, unit_type: int = 2) -> Dict[str, Any]:
    return {"actor": SEAT, "obj_id": obj_id, "type": 1, "move_path": route(start, goal, unit_type)}


def trigger_scene(**overrides: Any):
    """Infantry and IFV stationary in START, embark listed, baseline-v2 moves both (plus an unrelated tank)."""
    inf = unit(INF, START, kind="infantry", **overrides.pop("inf", {}))
    car = unit(CAR, START, **overrides.pop("car", {}))
    tank = unit(OTHER, START)
    valid = overrides.pop("valid", {INF: {1: None, 3: [{"target_obj_id": CAR}]}, CAR: {1: None}, OTHER: {1: None}})
    actions = overrides.pop("actions", [move(OTHER, START, FAR), move(INF, START, DEST, 1), move(CAR, START, DEST)])
    observation = obs([inf, car, tank], overrides.pop("passengers", ()), valid, **overrides)
    return observation, actions


def state_of(memory) -> str:
    record = t2.decode(memory)
    return t2.STATES[record.get(t2.F_STATE, t2.READY)] if record is not None else "BAD"


def record_memory(state: int, **fields: int):
    record = {t2.F_STATE: state, t2.F_INF: INF, t2.F_CAR: CAR, t2.F_EMBARK: 100}
    record.update({getattr(t2, f"F_{name}"): value for name, value in fields.items()})
    return t2.encode(record)


class TriggerTest(unittest.TestCase):
    def run_step(self, observation, actions, memory=()):
        return t2.step(observation, SEAT, RED, actions, memory)

    def test_embark_is_the_listed_option_copied_and_replaces_the_infantry_move_in_place(self) -> None:
        observation, actions = trigger_scene()
        out, changes, memory, state = self.run_step(observation, actions)
        self.assertEqual(state, "EMBARK_REQUESTED")
        self.assertEqual([dict(a) for a in out], [actions[0], {"actor": SEAT, "obj_id": INF, "type": 3,
                                                                "target_obj_id": CAR}])
        self.assertEqual(set(out[1]), {"actor", "obj_id", "type", "target_obj_id"})
        self.assertEqual([c["kind"] for c in changes], ["embark", "transition", "carrier-move-withheld"])
        record = t2.decode(memory)
        self.assertEqual((record[t2.F_INF], record[t2.F_CAR], record[t2.F_EMBARK]), (INF, CAR, 100))
        self.assertEqual(sp.unregistered_differences(actions, out, "READY", "EMBARK_REQUESTED", (INF, CAR)), [])

    def test_no_trigger_cases(self) -> None:
        cases = {
            "embark not listed": dict(valid={INF: {1: None}, CAR: {1: None}, OTHER: {1: None}}),
            "option key set not exact": dict(valid={INF: {1: None, 3: [{"target_obj_id": CAR, "x": 1}]},
                                                    CAR: {1: None}, OTHER: {1: None}}),
            "different hex": dict(car={"cur_hex": START + 1}),
            "infantry moving": dict(inf={"move_path": [START + 1]}),
            "carrier speed": dict(car={"speed": 0.5}),
            "carrier stop transition": dict(car={"move_to_stop_remain_time": 10}),
            "infantry suppressed": dict(inf={"keep": 1}),
            "carrier suppressed": dict(car={"keep": 1}),
            "embark under way": dict(inf={"get_on_remain_time": 30, "get_on_partner_id": [CAR]}),
            "disembark under way": dict(car={"get_off_remain_time": 30, "get_off_partner_id": [INF2]}),
            "infantry on board": dict(inf={"on_board": 1}),
            "no infantry among passenger types": dict(car={"valid_passenger_types": [4, 7]}),
            "no infantry capacity": dict(car={"max_passenger_nums": {2: 0, 4: 1, 7: 2}}),
            "capacity field missing": dict(car={"max_passenger_nums": {4: 1}}),
            "carrier already carries infantry": dict(car={"passenger_ids": [INF2]},
                                                     passengers=[unit(INF2, START, kind="infantry", on_board=1,
                                                                      car=CAR)]),
            "carrier not an IFV": dict(car={"sub_type": 0}),
            "carrier of the other side": dict(car={"color": BLUE}),
            "carrier not controlled": dict(controlled=[INF, OTHER]),
            "infantry not controlled": dict(controlled=[CAR, OTHER]),
            "baseline-v2 does not move the infantry": dict(actions=[move(OTHER, START, FAR), move(CAR, START, DEST)]),
            "baseline-v2 does not move the carrier": dict(actions=[move(OTHER, START, FAR),
                                                                   move(INF, START, DEST, 1)]),
            "baseline-v2 occupies with the carrier": dict(actions=[move(INF, START, DEST, 1),
                                                                   {"actor": SEAT, "obj_id": CAR, "type": 5}]),
            "baseline-v2 occupies with the infantry": dict(actions=[{"actor": SEAT, "obj_id": INF, "type": 5},
                                                                    move(CAR, START, DEST)]),
        }
        for name, change in cases.items():
            with self.subTest(name):
                observation, actions = trigger_scene(**copy.deepcopy(change))
                out, changes, memory, state = self.run_step(observation, actions)
                self.assertEqual((state, memory, changes), ("READY", (), ()))
                self.assertEqual([dict(a) for a in out], actions)

    def test_carrying_other_passenger_types_leaves_room_for_infantry(self) -> None:
        munitions = [unit(INF2, START, kind="munition", on_board=1, car=CAR)]
        observation, actions = trigger_scene(car={"passenger_ids": [INF2]}, passengers=munitions)
        self.assertEqual(self.run_step(observation, actions)[3], "EMBARK_REQUESTED")

    def test_pair_choice_is_lowest_infantry_then_lowest_carrier_whatever_the_listing_order(self) -> None:
        inf = unit(INF, START, kind="infantry")
        inf2 = unit(INF2, START, kind="infantry")
        cars = [unit(CAR, START), unit(CAR2, START)]
        valid = {INF: {1: None, 3: [{"target_obj_id": CAR2}, {"target_obj_id": CAR}]},
                 INF2: {1: None, 3: [{"target_obj_id": CAR}]}, CAR: {1: None}, CAR2: {1: None}}
        actions = [move(INF2, START, DEST, 1), move(INF, START, DEST, 1), move(CAR, START, DEST),
                   move(CAR2, START, DEST)]
        out, changes, memory, _ = t2.step(obs([inf2, cars[1], inf, cars[0]], (), valid), SEAT, RED, actions, ())
        record = t2.decode(memory)
        self.assertEqual((record[t2.F_INF], record[t2.F_CAR]), (INF, CAR))
        self.assertEqual([a.get("obj_id") for a in out], [INF2, INF, CAR2])

    def test_a_second_trigger_never_fires_after_the_first(self) -> None:
        observation, actions = trigger_scene()
        for state in range(1, len(t2.STATES)):
            if state in (t2.READY,):
                continue
            memory = record_memory(state, DEST=DEST, ARRIVE=100, DISEMBARK=100)
            out, changes, _, _ = t2.step(observation, SEAT, RED, actions, memory)
            self.assertFalse(any(c["kind"] == "embark" for c in changes), t2.STATES[state])

    def test_non_play_stage_keeps_actions_and_memory(self) -> None:
        observation, actions = trigger_scene(stage=1)
        self.assertEqual(t2.step(observation, SEAT, RED, actions, ())[2:], ((), "READY"))
        memory = record_memory(t2.EMBARK_REQUESTED)
        out, changes, memory_out, _ = t2.step(observation, SEAT, RED, actions, memory)
        self.assertEqual((memory_out, changes, [dict(a) for a in out]), (memory, (), actions))


def aboard_scene(cur_step: int, *, inf_hex: int = START, car_hex: int = START, carrier_extra=None, inf_extra=None,
                 actions=None, valid=None, held=(), others=()):
    car = unit(CAR, car_hex, passenger_ids=[INF], **(carrier_extra or {}))
    inf = unit(INF, inf_hex, kind="infantry", on_board=1, car=CAR, **(inf_extra or {}))
    observation = obs([car, unit(OTHER, START)] + list(others), [inf],
                      valid if valid is not None else {CAR: {1: None}, OTHER: {1: None}}, cur_step=cur_step,
                      held=held)
    return observation, actions if actions is not None else [move(OTHER, START, FAR), move(CAR, car_hex, DEST)]


class StateMachineTest(unittest.TestCase):
    def test_embark_transition_holds_the_carrier_move_only_and_passes_its_other_actions(self) -> None:
        inf = unit(INF, START, kind="infantry", get_on_remain_time=40, get_on_partner_id=[CAR])
        car = unit(CAR, START, get_on_remain_time=40, get_on_partner_id=[INF])
        shot = {"actor": SEAT, "obj_id": CAR, "type": 2, "target_obj_id": 1, "weapon_id": 1}
        for carrier_action, expected in ((move(CAR, START, DEST), []), (shot, [shot])):
            actions = [move(OTHER, START, FAR), carrier_action]
            out, changes, memory, state = t2.step(obs([inf, car, unit(OTHER, START)], (), {}, cur_step=140),
                                                  SEAT, RED, actions, record_memory(t2.EMBARK_REQUESTED))
            self.assertEqual(state, "EMBARK_REQUESTED")
            self.assertEqual([dict(a) for a in out], [actions[0]] + expected)

    def test_embark_bound_is_exact(self) -> None:
        inf = unit(INF, START, kind="infantry", get_on_remain_time=1, get_on_partner_id=[CAR])
        car = unit(CAR, START)
        for now, expected in ((100 + t2.BOUND, "EMBARK_REQUESTED"), (100 + t2.BOUND + 1, "FAILED")):
            _, _, memory, state = t2.step(obs([inf, car], (), {}, cur_step=now), SEAT, RED, [],
                                          record_memory(t2.EMBARK_REQUESTED))
            self.assertEqual(state, expected)
        self.assertEqual(t2.decode(memory)[t2.F_REASON], t2.EMBARK_TIMEOUT)

    def test_aboard_releases_the_carrier_at_once_and_fixes_the_destination_from_its_first_move(self) -> None:
        observation, actions = aboard_scene(175)
        out, changes, memory, state = t2.step(observation, SEAT, RED, actions, record_memory(t2.EMBARK_REQUESTED))
        self.assertEqual(state, "CARRIER_RELEASED")
        self.assertEqual([dict(a) for a in out], actions)  # baseline-v2's move passes
        record = t2.decode(memory)
        self.assertEqual((record[t2.F_ABOARD], record[t2.F_DEST]), (175, DEST))
        self.assertEqual([c.get("to") for c in changes if c["kind"] == "transition"], ["ABOARD", "CARRIER_RELEASED"])

    def test_aboard_requires_the_embark_transition_to_be_over_on_both_units(self) -> None:
        for extra in ({"carrier_extra": {"get_on_remain_time": 1}}, {"inf_extra": {"get_on_partner_id": [CAR]}}):
            observation, actions = aboard_scene(175, **extra)
            out, _, _, state = t2.step(observation, SEAT, RED, actions, record_memory(t2.EMBARK_REQUESTED))
            self.assertEqual(state, "EMBARK_REQUESTED")
            self.assertEqual([dict(a) for a in out], actions[:1])

    def test_inconsistent_representations_fail(self) -> None:
        inf_ground = unit(INF, START, kind="infantry")
        inf_air = unit(INF, START, kind="infantry", on_board=1, car=CAR)
        both = obs([inf_ground, unit(CAR, START, passenger_ids=[INF])], [inf_air], {}, cur_step=150)
        other_car = obs([unit(CAR, START, passenger_ids=[]), unit(CAR2, START, passenger_ids=[INF])],
                        [unit(INF, START, kind="infantry", on_board=1, car=CAR2)], {}, cur_step=150)
        for observation in (both, other_car):
            for state in (t2.EMBARK_REQUESTED, t2.CARRIER_RELEASED):
                _, _, memory, out_state = t2.step(observation, SEAT, RED, [], record_memory(state, DEST=DEST))
                self.assertEqual((out_state, t2.decode(memory)[t2.F_REASON]), ("FAILED", t2.INCONSISTENT))

    def test_infantry_between_lists_waits_inside_a_transition_but_fails_outside(self) -> None:
        observation = obs([unit(CAR, START)], (), {}, cur_step=150)
        self.assertEqual(t2.step(observation, SEAT, RED, [], record_memory(t2.EMBARK_REQUESTED))[3], "EMBARK_REQUESTED")
        _, _, memory, state = t2.step(observation, SEAT, RED, [], record_memory(t2.CARRIER_RELEASED, DEST=DEST))
        self.assertEqual((state, t2.decode(memory)[t2.F_REASON]), ("FAILED", t2.UNIT_ABSENT))

    def test_carrier_disappearance_fails_in_every_live_state(self) -> None:
        observation = obs([unit(INF, START, kind="infantry")], (), {}, cur_step=150)
        for state in (t2.EMBARK_REQUESTED, t2.CARRIER_RELEASED, t2.AT_DESTINATION, t2.DISEMBARK_REQUESTED):
            _, _, memory, out = t2.step(observation, SEAT, RED, [],
                                        record_memory(state, DEST=DEST, ARRIVE=140, DISEMBARK=145))
            self.assertEqual((out, t2.decode(memory)[t2.F_REASON]), ("FAILED", t2.UNIT_ABSENT), t2.STATES[state])

    def test_passenger_leaving_before_disembark_fails(self) -> None:
        observation = obs([unit(CAR, 303), unit(INF, 303, kind="infantry")], (), {}, cur_step=300)
        _, _, memory, state = t2.step(observation, SEAT, RED, [], record_memory(t2.CARRIER_RELEASED, DEST=DEST))
        self.assertEqual((state, t2.decode(memory)[t2.F_REASON]), ("FAILED", t2.PASSENGER_LEFT))

    def test_carry_passes_every_baseline_action_and_arrival_starts_the_hold(self) -> None:
        moving = aboard_scene(250, car_hex=303, carrier_extra={"move_path": route(303, DEST)}, inf_hex=303,
                              actions=[move(OTHER, START, FAR)])
        out, _, memory, state = t2.step(*moving[:1], SEAT, RED, moving[1], record_memory(t2.CARRIER_RELEASED,
                                                                                          DEST=DEST))
        self.assertEqual((state, [dict(a) for a in out]), ("CARRIER_RELEASED", moving[1]))
        arrived = aboard_scene(300, car_hex=DEST, inf_hex=DEST, held=(DEST,),
                               carrier_extra={"move_to_stop_remain_time": 75},
                               actions=[move(OTHER, START, FAR), move(CAR, DEST, FAR)])
        out, changes, memory, state = t2.step(arrived[0], SEAT, RED, arrived[1],
                                              record_memory(t2.CARRIER_RELEASED, DEST=DEST))
        self.assertEqual(state, "AT_DESTINATION")
        self.assertEqual([dict(a) for a in out], arrived[1][:1])
        self.assertEqual(t2.decode(memory)[t2.F_ARRIVE], 300)
        self.assertEqual(sp.unregistered_differences(arrived[1], out, "CARRIER_RELEASED", "AT_DESTINATION",
                                                     (INF, CAR)), [])

    def test_occupy_by_the_carrier_passes_during_the_hold(self) -> None:
        occupy = {"actor": SEAT, "obj_id": CAR, "type": 5}
        scene = aboard_scene(300, car_hex=DEST, inf_hex=DEST, carrier_extra={"move_to_stop_remain_time": 74},
                             actions=[occupy])
        out, _, _, state = t2.step(scene[0], SEAT, RED, scene[1], record_memory(t2.AT_DESTINATION, DEST=DEST,
                                                                               ARRIVE=299))
        self.assertEqual((state, [dict(a) for a in out]), ("AT_DESTINATION", [occupy]))

    def destination_scene(self, ground: int, listed: bool = True, cur_step: int = 380, keys=None):
        others = [unit(800000 + i, DEST, kind="tank") for i in range(ground - 1)]
        valid = {CAR: {1: None, **({4: [keys or {"target_obj_id": INF}]} if listed else {})}, OTHER: {1: None}}
        return aboard_scene(cur_step, car_hex=DEST, inf_hex=DEST, valid=valid, held=(DEST,), others=others,
                            actions=[move(OTHER, START, FAR), move(CAR, DEST, FAR)])

    def test_disembark_is_the_listed_option_copied_below_the_stacking_limit(self) -> None:
        observation, actions = self.destination_scene(ground=3)
        out, changes, memory, state = t2.step(observation, SEAT, RED, actions,
                                              record_memory(t2.AT_DESTINATION, DEST=DEST, ARRIVE=300))
        self.assertEqual(state, "DISEMBARK_REQUESTED")
        self.assertEqual([dict(a) for a in out], [actions[0], {"actor": SEAT, "obj_id": CAR, "type": 4,
                                                                "target_obj_id": INF}])
        self.assertEqual(sp.unregistered_differences(actions, out, "AT_DESTINATION", "DISEMBARK_REQUESTED",
                                                     (INF, CAR)), [])
        self.assertEqual(t2.decode(memory)[t2.F_DISEMBARK], 380)

    def test_destination_at_the_stacking_limit_blocks_without_issuing(self) -> None:
        observation, actions = self.destination_scene(ground=4)
        out, changes, memory, state = t2.step(observation, SEAT, RED, actions,
                                              record_memory(t2.AT_DESTINATION, DEST=DEST, ARRIVE=300))
        self.assertEqual((state, t2.decode(memory)[t2.F_REASON]), ("FAILED", t2.CAPACITY))
        self.assertEqual([dict(a) for a in out], actions)  # nothing issued, the hold ends
        self.assertFalse(any(a.get("type") == 4 for a in out))

    def test_disembark_needs_its_exact_listing(self) -> None:
        for name, (listed, keys) in {"absent": (False, None), "other target": (True, {"target_obj_id": INF2}),
                                     "extra key": (True, {"target_obj_id": INF, "x": 1})}.items():
            observation, actions = self.destination_scene(ground=2, listed=listed, keys=keys)
            out, _, _, state = t2.step(observation, SEAT, RED, actions,
                                       record_memory(t2.AT_DESTINATION, DEST=DEST, ARRIVE=300))
            self.assertEqual(state, "AT_DESTINATION", name)
            self.assertEqual([dict(a) for a in out], actions[:1], name)

    def test_settle_bound_is_exact_and_classifies_capacity(self) -> None:
        for ground, now, expected, reason in ((2, 300 + t2.BOUND, "AT_DESTINATION", None),
                                              (2, 301 + t2.BOUND, "FAILED", t2.NOT_LISTED),
                                              (4, 301 + t2.BOUND, "FAILED", t2.CAPACITY)):
            observation, actions = self.destination_scene(ground=ground, listed=False, cur_step=now)
            _, _, memory, state = t2.step(observation, SEAT, RED, actions,
                                          record_memory(t2.AT_DESTINATION, DEST=DEST, ARRIVE=300))
            self.assertEqual(state, expected)
            self.assertEqual(t2.decode(memory).get(t2.F_REASON), reason)

    def test_carrier_leaving_the_destination_fails(self) -> None:
        observation, actions = aboard_scene(380, car_hex=303, inf_hex=303)
        for state in (t2.AT_DESTINATION, t2.DISEMBARK_REQUESTED):
            _, _, memory, out = t2.step(observation, SEAT, RED, actions,
                                        record_memory(state, DEST=DEST, ARRIVE=300, DISEMBARK=376))
            self.assertEqual((out, t2.decode(memory)[t2.F_REASON]), ("FAILED", t2.CARRIER_LEFT))

    def test_disembark_completes_only_on_the_ground_with_the_transition_over(self) -> None:
        car = unit(CAR, DEST)
        ground = unit(INF, DEST, kind="infantry")
        done = obs([car, ground], (), {}, cur_step=460)
        _, changes, memory, state = t2.step(done, SEAT, RED, [move(CAR, DEST, FAR)],
                                            record_memory(t2.DISEMBARK_REQUESTED, DEST=DEST, ARRIVE=300,
                                                          DISEMBARK=385))
        self.assertEqual(state, "DONE")
        self.assertEqual([c.get("to") for c in changes if c["kind"] == "transition"], ["DISEMBARKED", "DONE"])
        pending = obs([unit(CAR, DEST, get_off_remain_time=3, get_off_partner_id=[INF]), ground], (), {}, cur_step=460)
        out, _, _, state = t2.step(pending, SEAT, RED, [move(CAR, DEST, FAR)],
                                   record_memory(t2.DISEMBARK_REQUESTED, DEST=DEST, ARRIVE=300, DISEMBARK=385))
        self.assertEqual((state, list(out)), ("DISEMBARK_REQUESTED", []))

    def test_disembark_bound_is_exact(self) -> None:
        for now, expected in ((385 + t2.BOUND, "DISEMBARK_REQUESTED"), (386 + t2.BOUND, "FAILED")):
            observation, actions = aboard_scene(now, car_hex=DEST, inf_hex=DEST)
            _, _, memory, state = t2.step(observation, SEAT, RED, actions,
                                          record_memory(t2.DISEMBARK_REQUESTED, DEST=DEST, ARRIVE=300,
                                                        DISEMBARK=385))
            self.assertEqual(state, expected)
        self.assertEqual(t2.decode(memory)[t2.F_REASON], t2.DISEMBARK_TIMEOUT)

    def test_terminal_states_are_baseline_v2_exactly(self) -> None:
        observation, actions = trigger_scene()
        for state in t2.TERMINAL:
            memory = record_memory(state, END=200, REASON=1)
            out, changes, memory_out, _ = t2.step(observation, SEAT, RED, actions, memory)
            self.assertEqual(([dict(a) for a in out], changes, memory_out), (actions, (), memory))

    def test_malformed_memory_fails_without_editing(self) -> None:
        observation, actions = trigger_scene()
        for bad in (((1, 1),), ((t2.F_STATE, 99), (t2.F_INF, INF), (t2.F_CAR, CAR)), ((99, 1),), ((1, "x"),),
                    ((t2.F_STATE, 1), (t2.F_STATE, 2)), ("garbage",)):
            out, changes, memory, state = t2.step(observation, SEAT, RED, actions, bad)
            self.assertEqual(state, "FAILED")
            self.assertEqual([dict(a) for a in out], actions)
            self.assertEqual(t2.decode(memory)[t2.F_REASON], t2.MEMORY_BAD)
            again = t2.step(observation, SEAT, RED, actions, memory)
            self.assertEqual(([dict(a) for a in again[0]], again[1]), (actions, ()))


class StandInWorld:
    """A stand-in transport engine on the synthetic map, with the documented semantics only: embark and disembark take
    75 steps; a unit moves one hex per ``hex_steps`` steps (the unrelated unit per ``slow_steps``, so that it takes no
    objective before the carrier) and its passengers move with it; a unit ending a move has a
    75-step stop transition; disembark is listed for a settled carrier; a unit whose path ends on an objective takes
    it. Its seat view is the full state of the seat's side."""

    def __init__(self, hex_steps: int = 5, extra_ground_at_dest: int = 0, slow_steps: int = 400) -> None:
        self.step_no = 0
        self.units = {INF: unit(INF, START, kind="infantry"), CAR: unit(CAR, START), OTHER: unit(OTHER, 707)}
        for i in range(extra_ground_at_dest):
            self.units[800000 + i] = unit(800000 + i, DEST, kind="tank")
        self.passengers: Dict[int, Dict[str, Any]] = {}
        self.flags = {DEST: -1, FAR: -1}
        self.hex_steps = {u: (slow_steps if u == OTHER else hex_steps) for u in self.units}
        self.timers: Dict[str, int] = {}
        self.log: List[str] = []
        self.fixed = {u for u in self.units if 800000 <= u < 800100}  # the blocking tanks list no action
        self.landed_hex: Optional[int] = None

    def valid(self) -> Dict[int, Any]:
        out: Dict[int, Any] = {}
        for u in self.units.values():
            busy = u["get_on_remain_time"] or u["get_off_remain_time"]
            if busy or u["obj_id"] in self.fixed:
                continue
            entry: Dict[int, Any] = {1: None}
            settled = not u["move_path"] and not u["move_to_stop_remain_time"]
            if u["type"] == 1 and settled:
                cars = [c for c in self.units.values() if c["sub_type"] == 1 and c["type"] == 2 and
                        c["cur_hex"] == u["cur_hex"] and not c["move_path"] and not c["move_to_stop_remain_time"]
                        and not c["passenger_ids"]]
                if cars:
                    entry[3] = [{"target_obj_id": c["obj_id"]} for c in cars]
            if u["sub_type"] == 1 and settled and u["passenger_ids"]:
                entry[4] = [{"target_obj_id": p} for p in u["passenger_ids"]]
            out[u["obj_id"]] = entry
        return out

    def observation(self) -> Dict[str, Any]:
        cities = [syn.city(c, flag=f) for c, f in self.flags.items()]
        raw = syn.build_observation(units=list(self.units.values()), valid_actions=self.valid(), stage=2,
                                    cur_step=self.step_no,
                                    seats={SEAT: syn.seat_record(SEAT, RED, sorted(self.units) + sorted(self.passengers),
                                                                 True)}, cities=cities)
        raw["passengers"] = [dict(p) for p in self.passengers.values()]
        raw["time"]["max_step"] = 2880
        return copy.deepcopy(raw)

    def apply(self, actions: Sequence[Dict[str, Any]]) -> None:
        for a in actions:
            u = self.units.get(a["obj_id"])
            if a["type"] == 1 and u is not None and not u["move_path"]:
                u["move_path"], u["move_to_stop_remain_time"] = list(a["move_path"]), 0
                self.timers[f"hex{u['obj_id']}"] = self.hex_steps.get(u["obj_id"], 5)
            elif a["type"] == 3:
                car = self.units[a["target_obj_id"]]
                for x, partner in ((u, car), (car, u)):
                    x["get_on_remain_time"], x["get_on_partner_id"] = t2.DOCUMENTED_TRANSITION, [partner["obj_id"]]
                self.log.append(f"embark {self.step_no}")
            elif a["type"] == 4:
                p = self.passengers[a["target_obj_id"]]
                for x, partner in ((u, p), (p, u)):
                    x["get_off_remain_time"], x["get_off_partner_id"] = t2.DOCUMENTED_TRANSITION, [partner["obj_id"]]
                self.log.append(f"disembark {self.step_no}")
        self.advance()

    def advance(self) -> None:
        self.step_no += 1
        for u in list(self.units.values()):
            if u["get_on_remain_time"]:
                u["get_on_remain_time"] -= 1
                if not u["get_on_remain_time"]:
                    partner = u["get_on_partner_id"][0]
                    u["get_on_partner_id"] = []
                    if u["type"] == 1:
                        del self.units[u["obj_id"]]
                        u.update(on_board=1, car=partner)
                        self.passengers[u["obj_id"]] = u
                        self.units[partner]["passenger_ids"] = [u["obj_id"]]
            if u["move_to_stop_remain_time"]:
                u["move_to_stop_remain_time"] -= 1
            if u["move_path"]:
                key = f"hex{u['obj_id']}"
                self.timers[key] -= 1
                u["speed"] = 1
                if not self.timers[key]:
                    u["cur_hex"] = u["move_path"].pop(0)
                    self.timers[key] = self.hex_steps.get(u["obj_id"], 5)
                    for p in u["passenger_ids"]:
                        self.passengers[p]["cur_hex"] = u["cur_hex"]
                    if not u["move_path"]:
                        u["speed"], u["move_to_stop_remain_time"] = 0, t2.DOCUMENTED_TRANSITION
                        if u["cur_hex"] in self.flags:
                            self.flags[u["cur_hex"]] = RED
        for p in list(self.passengers.values()):
            if p["get_off_remain_time"]:
                p["get_off_remain_time"] -= 1
                car = self.units[p["get_off_partner_id"][0]]
                car["get_off_remain_time"] = p["get_off_remain_time"]
                if not p["get_off_remain_time"]:
                    p["get_off_partner_id"], car["get_off_partner_id"] = [], []
                    car["passenger_ids"] = []
                    p.update(on_board=0, car=None, cur_hex=car["cur_hex"])
                    del self.passengers[p["obj_id"]]
                    self.units[p["obj_id"]] = p
                    self.log.append(f"landed {self.step_no}")
                    self.landed_hex = p["cur_hex"]


class StandInChainTest(unittest.TestCase):
    def play(self, world: StandInWorld, steps: int):
        policy = t2.TransportPolicy(COSTS)
        memory = AddonMemory()
        states, problems = [], []
        for _ in range(steps):
            raw = world.observation()
            observation = Observation.from_raw(raw, Origin.ENGINE)
            v2 = ShootReservationPolicy(COSTS).decide(observation, SEAT, RED, memory.baseline)
            before = state_of(memory.addon)
            decision = policy.decide(observation, SEAT, RED, memory)
            after = state_of(decision.memory.addon)
            record = t2.decode(decision.memory.addon) or {}
            pair = (record[t2.F_INF], record[t2.F_CAR]) if record.get(t2.F_INF) else None
            problems.extend(sp.unregistered_differences(v2.actions, decision.actions, before, after, pair))
            states.append(after)
            memory = decision.memory
            world.apply([dict(a) for a in decision.actions])
        return states, problems, t2.decode(memory.addon)

    def test_complete_chain_in_the_stand_in_world(self) -> None:
        world = StandInWorld()
        states, problems, record = self.play(world, 900)
        self.assertEqual(problems, [])
        self.assertEqual(states[-1], "DONE")
        order = [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]
        self.assertEqual(order, ["EMBARK_REQUESTED", "CARRIER_RELEASED", "AT_DESTINATION", "DISEMBARK_REQUESTED",
                                 "DONE"])
        self.assertEqual(record[t2.F_DEST], DEST)
        self.assertEqual(record[t2.F_ABOARD] - record[t2.F_EMBARK], t2.DOCUMENTED_TRANSITION)
        self.assertEqual(world.landed_hex, DEST)
        self.assertNotIn(INF, world.passengers)
        self.assertEqual([e.split()[0] for e in world.log], ["embark", "disembark", "landed"])

    def test_chain_blocked_at_the_stacking_limit(self) -> None:
        world = StandInWorld(extra_ground_at_dest=3)
        states, problems, record = self.play(world, 900)
        self.assertEqual(problems, [])
        self.assertEqual((states[-1], record[t2.F_REASON]), ("FAILED", t2.CAPACITY))
        self.assertIn(INF, world.passengers)
        self.assertNotIn("disembark", " ".join(world.log))

    def test_memory_is_empty_in_every_game(self) -> None:
        agent = t2.TransportAgent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        self.assertEqual(agent.memory, AddonMemory())
        agent.memory = AddonMemory(agent.memory.baseline, record_memory(t2.CARRIER_RELEASED, DEST=DEST))
        agent.reset()
        self.assertEqual(agent.memory, AddonMemory())
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        self.assertEqual(agent.memory, AddonMemory())


class IdentityTest(unittest.TestCase):
    def test_module_reads_no_analysis_code_and_holds_only_mechanism_literals(self) -> None:
        source = Path(t2.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = sorted(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        self.assertEqual(imported, ["__future__", "boundary", "exploratory_addon", "typing"])
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                    and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}
        # documented action and class codes, the documented 75-step transition, its bound, the stacking limit
        self.assertEqual(literals, {0, 1, 2, 3, 4, 75, 150}, literals)
        code = source.split('"""', 2)[2]
        for word in ("scenario", "1930331196", "2120531121", "threat", "random", "time.time", "score"):
            self.assertNotIn(word, code)

    def test_source_identity_is_pinned(self) -> None:
        import importlib.util
        from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files
        spec = importlib.util.spec_from_file_location("bs22_identity", ROOT / "scripts" / "build_s22_card.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        files = policy_source_files(sources=module.CANDIDATE_SOURCES)
        self.assertIn("experiments/t2_transport_p1.py", files)
        self.assertEqual(digest_of_files(files), sp.CANDIDATE_DIGEST)
        self.assertEqual(sp.CANDIDATE_DIGEST, "1cb53199a246557bb0e564a7f5156b68396680c4b3a39a39c12023b98b96f65f")
        self.assertEqual(digest_of_files(policy_source_files(sources=module.V2_SOURCES)), sp.V2_DIGEST)

    def test_identity_and_policy_classes(self) -> None:
        self.assertEqual((t2.CANDIDATE_ID, t2.ADDON_NAME), ("t2-transport-p1", "t2_transport_p1"))
        self.assertEqual(t2.TransportPolicy.identity, t2.CANDIDATE_ID)
        self.assertIs(t2.TransportAgent.policy_class, t2.TransportPolicy)
        self.assertEqual(len(t2.STATES), 9)
        self.assertEqual(t2.HOLD_STATES, (t2.EMBARK_REQUESTED, t2.AT_DESTINATION, t2.DISEMBARK_REQUESTED))
        self.assertEqual((t2.DOCUMENTED_TRANSITION, t2.BOUND, t2.STACK_LIMIT), (75, 150, 4))


if __name__ == "__main__":
    unittest.main()
