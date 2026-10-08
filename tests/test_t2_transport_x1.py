"""The PROPOSED, NON-EXECUTABLE Sprint 23 candidate ``t2-transport-x1`` (``experiments/t2_transport_x1.py``).
SYNTHETIC observations on the 10 x 10 synthetic map (``tests/fixtures/synthetic.py``, through the Sprint 22 test
helpers); routes and free-flow times come from the project's router, never typed by hand.

What is pinned here: the nine trigger conditions in their order (co-location, eligibility, the exact listing,
baseline-v2's MOVE for both, the same objective, no competitive foot arrival, a positive feasible saving, infantry
capacity, destination admission); the matching order and its conflicts (two infantry for one carrier, two carriers for
one infantry), independent pairs, permutation invariance; admission with occupancy 2, 3 and reservations of active
episodes; the time model at its exact end-of-game boundary; the embark and disembark actions as listed copies and every
other baseline-v2 action unchanged; every state of the episode machine and each bound at its exact boundary; the
recovery of a live passenger and its exhaustion (STRANDED); independence of several episodes; malformed memory; and the
identity's status: non-executable, refused by its agent, in no run card.
"""

from __future__ import annotations

import ast
import itertools
import json
import unittest
from pathlib import Path
from typing import Any, Dict, List, Sequence

from miaosuan_agent.evaluation import s23_design as sd
from miaosuan_agent.experiments import t2_transport_x1 as x1
from miaosuan_agent.experiments import t9_batch as tb
from tests import test_t2_transport_p1 as tt

ROOT = Path(__file__).resolve().parents[1]
SEAT, RED = tt.SEAT, tt.RED
INF, CAR, CAR2, OTHER, INF2 = tt.INF, tt.CAR, tt.CAR2, tt.OTHER, tt.INF2
INF3, CAR3 = 900306, 900307
START, DEST, FAR = tt.START, tt.DEST, tt.FAR
FF = x1.router_free_flow(tt.ROUTER)
unit, obs, move, route = tt.unit, tt.obs, tt.move, tt.route


def ff(kind: str, start: int, goal: int) -> int:
    probe = obs([unit(1, start, kind=kind)], (), {}).operators()[0]
    return FF(probe, route(start, goal, 1 if kind == "infantry" else 2))


def run(observation, actions, memory=()):
    return x1.step(observation, SEAT, RED, actions, memory, FF)


def embark(inf: int, car: int) -> Dict[str, Any]:
    return {"actor": SEAT, "obj_id": inf, "type": 3, "target_obj_id": car}


def episode(state: int, inf: int = INF, car: int = CAR, dest: int = DEST, **fields: int) -> Dict[int, int]:
    ep = {x1.F_STATE: state, x1.F_INF: inf, x1.F_CAR: car, x1.F_DEST: dest, x1.F_EMBARK: 100, x1.F_FF: 100}
    ep.update({getattr(x1, f"F_{name}"): value for name, value in fields.items()})
    return ep


def mem(*episodes: Dict[int, int]):
    return x1.encode(list(episodes))


def states(memory) -> List[str]:
    return [x1.STATES[ep[x1.F_STATE] - 1] for ep in x1.decode(memory)]


def scene(*, pairs=((INF, CAR, START),), dests=None, cur_step: int = 100, extra_units=(), cities=(DEST, FAR),
          held=(), passengers=(), unit_extra=None, valid=None, actions=None, controlled=None, stage: int = 2):
    """Co-located infantry-carrier pairs, embark listed for each pair, baseline-v2 moving every unit of a pair to its
    destination (DEST unless ``dests`` says otherwise), plus an unrelated tank moving to FAR."""
    unit_extra = unit_extra or {}
    dests = dests or {}
    units, listing, moves = [], {}, [move(OTHER, START, FAR)]
    for inf, car, hex_ in pairs:
        units.append(unit(inf, hex_, kind="infantry", **unit_extra.get(inf, {})))
        units.append(unit(car, hex_, **unit_extra.get(car, {})))
        listing.setdefault(inf, {1: None, 3: []})[3].append({"target_obj_id": car})
        listing.setdefault(car, {1: None})
        goal = dests.get(inf, DEST)
        if move(inf, hex_, goal, 1) not in moves:
            moves.append(move(inf, hex_, dests.get(inf, DEST), 1))
        if all(m.get("obj_id") != car for m in moves):
            moves.append(move(car, hex_, dests.get(car, DEST)))
    seen, unique = set(), []
    for u in units:
        if u["obj_id"] not in seen:
            seen.add(u["obj_id"])
            unique.append(u)
    unique.append(unit(OTHER, START, kind="tank"))
    unique.extend(extra_units)
    listing[OTHER] = {1: None}
    observation = obs(unique, passengers, valid if valid is not None else listing, cur_step=cur_step,
                      cities=cities, held=held, controlled=controlled, stage=stage)
    return observation, actions if actions is not None else moves


class ConstantsAndIdentityTest(unittest.TestCase):
    def test_sprint22_constants_are_reused_and_restated_equal_in_the_analysis(self) -> None:
        self.assertEqual((x1.TRANSITION, x1.BOUND, x1.STACK_LIMIT), (75, 150, 4))
        self.assertEqual((sd.TRANSITION, sd.BOUND, sd.STACK_LIMIT, sd.PLACES, sd.CHAIN_TRANSITIONS),
                         (x1.TRANSITION, x1.BOUND, x1.STACK_LIMIT, x1.PLACES, x1.CHAIN_TRANSITIONS))
        self.assertEqual((x1.MOVE, x1.EMBARK, x1.DISEMBARK), (sd.MOVE, sd.EMBARK, sd.DISEMBARK))

    def test_status_is_proposed_non_executable_and_the_agent_refuses_setup(self) -> None:
        self.assertFalse(x1.EXECUTABLE)
        self.assertEqual(x1.STATUS, "PROPOSED - NON-EXECUTABLE - UNAPPROVED")
        with self.assertRaises(RuntimeError):
            x1.TransportXAgent().setup({})

    def test_candidate_imports_no_analysis_module_and_the_analysis_not_the_candidate(self) -> None:
        tree = ast.parse((ROOT / "src/miaosuan_agent/experiments/t2_transport_x1.py").read_text(encoding="utf-8"))
        modules = {(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertFalse(any("evaluation" in m for m in modules), modules)
        analysis = (ROOT / "src/miaosuan_agent/evaluation/s23_design.py").read_text(encoding="utf-8")
        self.assertNotIn("t2_transport", analysis)

    def test_identity_is_in_no_run_card_and_only_the_sprint23_scripts_import_it(self) -> None:
        from miaosuan_agent.evaluation import exploratory as xp
        for path in sorted((ROOT / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if x1.CANDIDATE_ID not in text:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = json.loads(text)
            self.assertFalse(isinstance(data, dict) and (xp.is_card(data) or path.name == "manifest.json"), rel)
            self.assertTrue(rel.startswith(f"evaluation/{sd.STUDY_ID}/"), rel)
            self.assertFalse(isinstance(data, dict) and data.get("executable"), rel)
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "run_evaluation.py",
                     "run_game_pool.py", "run_s22_game.py", "build_s22_card.py", "run_s22_probe.py"):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn("t2_transport_x1", text, name)
            self.assertNotIn(x1.CANDIDATE_ID, text, name)
        users = sorted(p.name for p in (ROOT / "scripts").glob("*.py")
                       if "t2_transport_x1" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["mutate_s23.py", "s23_t2_design.py"])


class TriggerTest(unittest.TestCase):
    def test_same_objective_pair_embarks_in_place_and_holds_the_carrier_move(self) -> None:
        observation, actions = scene()
        out, changes, memory = run(observation, actions)
        self.assertEqual([dict(a) for a in out], [actions[0], embark(INF, CAR)])
        self.assertEqual(states(memory), ["EMBARK_REQUESTED"])
        ep = x1.decode(memory)[0]
        self.assertEqual((ep[x1.F_INF], ep[x1.F_CAR], ep[x1.F_DEST], ep[x1.F_EMBARK], ep[x1.F_FF]),
                         (INF, CAR, DEST, 100, ff("ifv", START, DEST)))
        self.assertEqual([c["kind"] for c in changes], ["embark", "transition", "carrier-move-withheld"])
        self.assertEqual(sd.batch_problems(observation.fields, SEAT, RED, actions, out, [(INF, CAR)], _raw_ff), [])

    def test_conditions_fail_in_their_registered_order(self) -> None:
        near = 203
        cases = {
            "c2_eligible": [dict(unit_extra={INF: {"keep": 1}}), dict(unit_extra={CAR: {"move_path": [303]}}),
                            dict(unit_extra={CAR: {"move_to_stop_remain_time": 5}}), dict(controlled=[INF, OTHER]),
                            dict(unit_extra={INF: {"get_on_remain_time": 3, "get_on_partner_id": [CAR]}})],
            "c3_listing": [dict(valid={INF: {1: None}, CAR: {1: None}, OTHER: {1: None}}),
                           dict(valid={INF: {3: [{"target_obj_id": CAR, "x": 1}]}, CAR: {}, OTHER: {}})],
            "c4_both_move": [dict(actions=[move(INF, START, DEST, 1)]), dict(actions=[move(CAR, START, DEST)]),
                             dict(actions=[move(INF, START, DEST, 1), {"actor": SEAT, "obj_id": CAR, "type": 5}])],
            "c5_same_objective": [dict(dests={INF: FAR}), dict(dests={INF: 404, CAR: 404})],
            "c6_no_timely_foot": [dict(dests={INF: near, CAR: near}, cities=(near, DEST))],
            "c7_positive_saving": [dict(cur_step=2600)],
            "c8_capacity": [dict(unit_extra={CAR: {"max_passenger_nums": {2: 0, 4: 1, 7: 2}}}),
                            dict(unit_extra={CAR: {"valid_passenger_types": [4, 7]}}),
                            dict(unit_extra={CAR: {"passenger_ids": [INF2]}},
                                 passengers=[unit(INF2, START, kind="infantry", on_board=1, car=CAR)])],
        }
        for expected, variants in cases.items():
            for variant in variants:
                with self.subTest(expected=expected, variant=variant):
                    observation, actions = scene(**variant)
                    view = x1.p1.View(observation, SEAT, RED)
                    found = x1.pairs(observation, view, actions, (), FF)
                    self.assertEqual([p.failed for p in found], [expected])
                    out, changes, memory = run(observation, actions)
                    self.assertEqual(([dict(a) for a in out], changes, memory), (actions, (), ()))

    def test_different_hexes_never_pair(self) -> None:
        observation, actions = scene(pairs=((INF, CAR, START),), unit_extra={CAR: {"cur_hex": 303}})
        self.assertEqual(x1.pairs(observation, x1.p1.View(observation, SEAT, RED), actions, (), FF), [])

    def test_carrying_other_passenger_types_leaves_room(self) -> None:
        munition = unit(INF2, START, kind="munition", on_board=1, car=CAR)
        observation, actions = scene(unit_extra={CAR: {"passenger_ids": [INF2]}}, passengers=[munition])
        self.assertEqual(states(run(observation, actions)[2]), ["EMBARK_REQUESTED"])

    def test_end_of_game_boundary_is_strict(self) -> None:
        t_car = ff("ifv", START, DEST)
        last = 2880 - 1 - x1.CHAIN_TRANSITIONS * x1.TRANSITION - t_car
        for now, expected in ((last, ["EMBARK_REQUESTED"]), (last + 1, [])):
            observation, actions = scene(cur_step=now)
            memory = run(observation, actions)[2]
            self.assertEqual(states(memory) if memory else [], expected, now)

    def test_time_conditions_at_their_boundaries(self) -> None:
        self.assertEqual(x1.time_condition(500, 500, 2880), "c6_no_timely_foot")  # a tie is a competitive foot arrival
        self.assertEqual(x1.time_condition(500, 499, 2880), "c6_no_timely_foot")
        self.assertIsNone(x1.time_condition(500, 501, 2880))
        self.assertIsNone(x1.time_condition(2879, 2880, 2880))
        self.assertEqual(x1.time_condition(2880, 3000, 2880), "c7_positive_saving")
        self.assertEqual(x1.time_condition(2900, 2880, 2880), "c7_positive_saving")  # foot cannot arrive either

    def test_a_carrier_action_with_a_route_that_is_not_a_move_fails_condition_4(self) -> None:
        odd = dict(move(CAR, START, DEST), type=10)
        observation, actions = scene(actions=[move(INF, START, DEST, 1), odd])
        self.assertEqual([p.failed for p in x1.pairs(observation, x1.p1.View(observation, SEAT, RED), actions, (),
                                                      FF)], ["c4_both_move"])

    def test_time_model(self) -> None:
        self.assertEqual(x1.timing(100, 2880, 900, 100), (100 + 225 + 100, 1000, 1000 - 425, False))
        self.assertEqual(x1.timing(100, 2880, 2780, 100)[3], True)
        self.assertEqual(x1.timing(100, 2880, 2779, 100)[3], False)
        self.assertIsNone(x1.timing(100, 2880, None, 100))
        observation, actions = scene()
        pair = x1.pairs(observation, x1.p1.View(observation, SEAT, RED), actions, (), FF)[0]
        self.assertEqual(pair.saving, ff("infantry", START, DEST) - 3 * 75 - ff("ifv", START, DEST))
        self.assertGreater(pair.saving, 0)


class MatchingTest(unittest.TestCase):
    def test_two_infantry_for_one_carrier_take_the_larger_saving(self) -> None:
        # INF2 starts at the same hex but baseline-v2 routes it along a longer path to the same objective
        observation, actions = scene(pairs=((INF, CAR, START), (INF2, CAR, START)))
        long_route = move(INF2, START, DEST, 1)
        long_route["move_path"] = route(START, 101, 1) + route(101, DEST, 1)
        actions = [a if a.get("obj_id") != INF2 else long_route for a in actions]
        view = x1.p1.View(observation, SEAT, RED)
        selected, outcome = x1.match(x1.pairs(observation, view, actions, (), FF), view, {})
        self.assertEqual([(p.infantry, p.carrier) for p in selected], [(INF2, CAR)])
        self.assertEqual(outcome[(INF, CAR)], "carrier_conflict")

    def test_two_carriers_for_one_infantry_take_one(self) -> None:
        observation, actions = scene(pairs=((INF, CAR, START), (INF, CAR2, START)))
        view = x1.p1.View(observation, SEAT, RED)
        selected, outcome = x1.match(x1.pairs(observation, view, actions, (), FF), view, {})
        self.assertEqual([(p.infantry, p.carrier) for p in selected], [(INF, CAR)])  # equal saving: lower carrier id
        self.assertEqual(outcome[(INF, CAR2)], "infantry_conflict")
        out, changes, memory = run(observation, actions)
        self.assertEqual([a for a in out if a.get("obj_id") == CAR2], [a for a in actions if a.get("obj_id") == CAR2])

    def test_independent_pairs_are_all_selected_with_every_other_action_unchanged(self) -> None:
        observation, actions = scene(pairs=((INF, CAR, START), (INF2, CAR2, 303)), dests={INF2: FAR, CAR2: FAR})
        out, changes, memory = run(observation, actions)
        self.assertEqual(sorted((ep[x1.F_INF], ep[x1.F_CAR]) for ep in x1.decode(memory)),
                         [(INF, CAR), (INF2, CAR2)])
        self.assertEqual([dict(a) for a in out], [actions[0], embark(INF, CAR), embark(INF2, CAR2)])
        self.assertEqual(len({json.dumps(a, sort_keys=True) for a in out}), len(out))
        self.assertEqual(sd.batch_problems(observation.fields, SEAT, RED, actions, out, [(INF, CAR), (INF2, CAR2)],
                                           _raw_ff), [])

    def test_admission_occupancy_two_admits_three_rejects(self) -> None:
        for ground, expected in ((2, ["EMBARK_REQUESTED"]), (3, [])):
            tanks = [unit(800000 + i, DEST, kind="tank") for i in range(ground)]
            observation, actions = scene(extra_units=tanks)
            memory = run(observation, actions)[2]
            self.assertEqual(states(memory) if memory else [], expected, ground)

    def test_two_pairs_to_a_nearly_full_objective(self) -> None:
        for ground, expected in ((0, 2), (1, 1)):
            tanks = [unit(800000 + i, DEST, kind="tank") for i in range(ground)]
            observation, actions = scene(pairs=((INF, CAR, START), (INF2, CAR2, 303)), extra_units=tanks)
            view = x1.p1.View(observation, SEAT, RED)
            selected, outcome = x1.match(x1.pairs(observation, view, actions, (), FF), view, {})
            self.assertEqual(len(selected), expected, ground)
            if expected == 1:
                self.assertIn("c9_destination", outcome.values())

    def test_active_episode_reservations_count_in_the_admission(self) -> None:
        busy = unit(CAR3, START, get_on_remain_time=10, get_on_partner_id=[INF3])
        rider = unit(INF3, START, kind="infantry", get_on_remain_time=10, get_on_partner_id=[CAR3])
        for ground, expected in ((0, ["EMBARK_REQUESTED", "EMBARK_REQUESTED"]), (1, ["EMBARK_REQUESTED"])):
            tanks = [unit(800000 + i, DEST, kind="tank") for i in range(ground)]
            observation, actions = scene(pairs=((INF, CAR, 303),), extra_units=tanks + [busy, rider])
            active = episode(x1.EMBARK_REQUESTED, INF3, CAR3)
            memory = run(observation, actions, mem(active))[2]
            self.assertEqual(states(memory), expected, ground)

    def test_a_carrier_already_on_the_destination_reserves_only_the_infantry_place(self) -> None:
        settled = unit(CAR3, DEST, passenger_ids=[INF3])
        rider = unit(INF3, DEST, kind="infantry", on_board=1, car=CAR3)
        tank = unit(800001, DEST, kind="tank")
        for extra, expected in (([], ["AT_DESTINATION", "EMBARK_REQUESTED"]), ([tank], ["AT_DESTINATION"])):
            observation, actions = scene(pairs=((INF, CAR, 303),), extra_units=[settled] + extra, passengers=[rider])
            active = episode(x1.AT_DESTINATION, INF3, CAR3, ARRIVE=95)
            view = x1.p1.View(observation, SEAT, RED)
            self.assertEqual(x1.reservations(view, x1.decode(mem(active))), {DEST: 1})
            self.assertEqual(states(run(observation, actions, mem(active))[2]), expected, extra)

    def test_selection_does_not_depend_on_input_order(self) -> None:
        results = set()
        units_spec = ((INF, CAR, START), (INF2, CAR2, 303), (INF3, CAR, START))
        for perm in itertools.permutations(units_spec):
            observation, actions = scene(pairs=perm, dests={INF2: FAR, CAR2: FAR})
            memory = run(observation, sorted(actions, key=lambda a: -a["obj_id"]))[2]
            results.add(tuple(sorted((ep[x1.F_INF], ep[x1.F_CAR]) for ep in x1.decode(memory))))
        self.assertEqual(len(results), 1)

    def test_rank_key_order(self) -> None:
        def pair(inf, car, saving, unable, arrival):
            return x1.Pair(inf, car, START, None, DEST, saving=saving, unable_on_foot=unable,
                           transported_arrival=arrival)
        ordered = sorted([pair(5, 9, 100, False, 300), pair(4, 9, 100, True, 400), pair(3, 9, 100, True, 350),
                          pair(2, 9, 200, False, 900), pair(1, 8, 100, True, 350)], key=x1.rank_key)
        self.assertEqual([(p.infantry, p.carrier) for p in ordered], [(2, 9), (1, 8), (3, 9), (4, 9), (5, 9)])

    def test_units_of_a_past_episode_are_never_selected_again(self) -> None:
        observation, actions = scene()
        for state in x1.TERMINAL:
            memory = mem(episode(state))
            out, changes, memory_out = run(observation, actions, memory)
            self.assertFalse(any(c["kind"] == "embark" for c in changes), x1.STATES[state - 1])


def _raw_ff(unit_raw, path):
    times, _ = tb.path_times(tt.ROUTER, unit_raw.get("type"), unit_raw.get("move_state"), unit_raw.get("basic_speed"),
                             unit_raw.get("cur_hex"), list(path))
    return None if times is None else sum(times)


def aboard(cur_step: int, *, car_hex: int = START, carrier_extra=None, inf_extra=None, valid=None, others=(),
           held=()):
    car = unit(CAR, car_hex, passenger_ids=[INF], **(carrier_extra or {}))
    inf = unit(INF, car_hex, kind="infantry", on_board=1, car=CAR, **(inf_extra or {}))
    return obs([car, unit(OTHER, START, kind="tank")] + list(others), [inf],
               valid if valid is not None else {CAR: {1: None}, OTHER: {1: None}}, cur_step=cur_step, held=held)


def landed(cur_step: int, hex_: int = DEST, valid=None, others=()):
    return obs([unit(CAR, hex_), unit(INF, hex_, kind="infantry"), unit(OTHER, START, kind="tank")] + list(others), (),
               valid or {}, cur_step=cur_step)


CARRIER_MOVE = move(CAR, DEST, FAR)


class StateMachineTest(unittest.TestCase):
    def test_embark_transition_holds_only_the_carrier_move(self) -> None:
        inf = unit(INF, START, kind="infantry", get_on_remain_time=40, get_on_partner_id=[CAR])
        car = unit(CAR, START, get_on_remain_time=40, get_on_partner_id=[INF])
        shot = {"actor": SEAT, "obj_id": CAR, "type": 2, "target_obj_id": 1, "weapon_id": 1}
        for carrier_action, kept in ((move(CAR, START, DEST), []), (shot, [shot])):
            out, _, memory = run(obs([inf, car, unit(OTHER, START)], (), {}, cur_step=140),
                                 [move(OTHER, START, FAR), carrier_action], mem(episode(x1.EMBARK_REQUESTED)))
            self.assertEqual(states(memory), ["EMBARK_REQUESTED"])
            self.assertEqual([dict(a) for a in out], [move(OTHER, START, FAR)] + kept)

    def test_embark_not_taken_releases_at_once(self) -> None:
        observation = obs([unit(INF, START, kind="infantry"), unit(CAR, START)], (), {}, cur_step=101)
        out, _, memory = run(observation, [move(CAR, START, DEST)], mem(episode(x1.EMBARK_REQUESTED)))
        self.assertEqual(states(memory), ["FAILED_GROUND"])
        self.assertEqual(x1.decode(memory)[0][x1.F_REASON], x1.EMBARK_NOT_TAKEN)
        self.assertEqual([dict(a) for a in out], [move(CAR, START, DEST)])
        same_step = obs([unit(INF, START, kind="infantry"), unit(CAR, START)], (), {}, cur_step=100)
        self.assertEqual(states(run(same_step, [], mem(episode(x1.EMBARK_REQUESTED)))[2]), ["EMBARK_REQUESTED"])

    def test_embark_bound_is_exact(self) -> None:
        inf = unit(INF, START, kind="infantry", get_on_remain_time=1, get_on_partner_id=[CAR])
        for now, expected in ((100 + x1.BOUND, "EMBARK_REQUESTED"), (101 + x1.BOUND, "FAILED_GROUND")):
            memory = run(obs([inf, unit(CAR, START)], (), {}, cur_step=now), [], mem(episode(x1.EMBARK_REQUESTED)))[2]
            self.assertEqual(states(memory), [expected])

    def test_aboard_releases_the_carrier_and_its_move_passes(self) -> None:
        observation = aboard(175)
        actions = [move(OTHER, START, FAR), move(CAR, START, DEST)]
        out, _, memory = run(observation, actions, mem(episode(x1.EMBARK_REQUESTED)))
        self.assertEqual(states(memory), ["CARRIER_RELEASED"])
        self.assertEqual(x1.decode(memory)[0][x1.F_RELEASE], 175)
        self.assertEqual([dict(a) for a in out], actions)

    def test_arrival_starts_the_destination_hold_and_transit_bound_is_exact(self) -> None:
        arrived = aboard(300, car_hex=DEST, carrier_extra={"move_to_stop_remain_time": 75})
        out, _, memory = run(arrived, [CARRIER_MOVE], mem(episode(x1.CARRIER_RELEASED, RELEASE=175)))
        self.assertEqual((states(memory), [dict(a) for a in out]), (["AT_DESTINATION"], []))
        bound = 175 + 100 + x1.BOUND
        for now, expected in ((bound, "CARRIER_RELEASED"), (bound + 1, "RECOVERY_WAIT")):
            moving_car = aboard(now, car_hex=303, carrier_extra={"move_path": route(303, DEST)})
            memory = run(moving_car, [], mem(episode(x1.CARRIER_RELEASED, RELEASE=175)))[2]
            self.assertEqual(states(memory), [expected])

    def destination(self, ground: int, listed: bool = True, now: int = 380):
        others = [unit(800000 + i, DEST, kind="tank") for i in range(ground - 1)]
        valid = {CAR: {1: None, **({4: [{"target_obj_id": INF}]} if listed else {})}}
        return aboard(now, car_hex=DEST, valid=valid, others=others)

    def test_disembark_at_occupancy_three_and_hold_at_four(self) -> None:
        out, _, memory = run(self.destination(3), [CARRIER_MOVE], mem(episode(x1.AT_DESTINATION, ARRIVE=300)))
        self.assertEqual(states(memory), ["DISEMBARK_REQUESTED"])
        self.assertEqual([dict(a) for a in out], [{"actor": SEAT, "obj_id": CAR, "type": 4, "target_obj_id": INF}])
        out, _, memory = run(self.destination(4), [CARRIER_MOVE], mem(episode(x1.AT_DESTINATION, ARRIVE=300)))
        self.assertEqual((states(memory), [dict(a) for a in out]), (["AT_DESTINATION"], []))

    def test_destination_bound_is_exact_and_classifies_the_reason(self) -> None:
        for ground, listed, now, expected, reason in (
                (2, False, 300 + x1.BOUND, "AT_DESTINATION", None), (2, False, 301 + x1.BOUND, "RECOVERY_WAIT",
                                                                      x1.NOT_LISTED),
                (4, True, 301 + x1.BOUND, "RECOVERY_WAIT", x1.CAPACITY)):
            out, changes, memory = run(self.destination(ground, listed, now), [CARRIER_MOVE],
                                       mem(episode(x1.AT_DESTINATION, ARRIVE=300)))
            self.assertEqual(states(memory), [expected])
            if reason is not None:
                self.assertEqual(changes[-1]["reason"], x1.REASONS[reason])
                self.assertEqual([dict(a) for a in out], [CARRIER_MOVE])  # released at once

    def test_disembark_completion_retry_and_bound(self) -> None:
        memory = mem(episode(x1.DISEMBARK_REQUESTED, ARRIVE=300, DISEMBARK=380))
        self.assertEqual(states(run(landed(456), [CARRIER_MOVE], memory)[2]), ["DONE"])
        in_progress = aboard(400, car_hex=DEST, inf_extra={"get_off_remain_time": 50, "get_off_partner_id": [CAR]})
        out, _, out_memory = run(in_progress, [CARRIER_MOVE], memory)
        self.assertEqual((states(out_memory), [dict(a) for a in out]), (["DISEMBARK_REQUESTED"], []))
        refused = self.destination(2, now=382)
        out, _, out_memory = run(refused, [CARRIER_MOVE], memory)
        self.assertEqual([dict(a) for a in out], [{"actor": SEAT, "obj_id": CAR, "type": 4, "target_obj_id": INF}])
        late = aboard(381 + x1.BOUND, car_hex=DEST, inf_extra={"get_off_remain_time": 5, "get_off_partner_id": [CAR]})
        self.assertEqual(states(run(late, [CARRIER_MOVE], memory)[2]), ["RECOVERY_WAIT"])

    def test_recovery_disembarks_a_live_passenger_at_the_carrier_next_stop(self) -> None:
        waiting = mem(episode(x1.RECOVERY_WAIT, ARRIVE=300, HOLD_STEP=460))
        moving_car = aboard(470, car_hex=303, carrier_extra={"move_path": route(303, FAR)})
        out, _, memory = run(moving_car, [], waiting)
        self.assertEqual(states(memory), ["RECOVERY_WAIT"])
        stopped = aboard(520, car_hex=606, carrier_extra={"move_to_stop_remain_time": 70})
        out, _, memory = run(stopped, [move(CAR, 606, FAR)], waiting)
        self.assertEqual((states(memory), [dict(a) for a in out]), (["RECOVERY_HOLD"], []))
        ep = x1.decode(memory)[0]
        self.assertEqual((ep[x1.F_ATTEMPTS], ep[x1.F_HOLD_HEX], ep[x1.F_HOLD_STEP]), (1, 606, 520))
        listed = aboard(600, car_hex=606, valid={CAR: {1: None, 4: [{"target_obj_id": INF}]}})
        out, _, memory = run(listed, [move(CAR, 606, FAR)], memory)
        self.assertEqual(states(memory), ["RECOVERY_DISEMBARK"])
        self.assertEqual([dict(a) for a in out], [{"actor": SEAT, "obj_id": CAR, "type": 4, "target_obj_id": INF}])
        self.assertEqual(states(run(landed(676, 606), [], memory)[2]), ["RECOVERED"])

    def test_recovery_does_not_start_at_the_failure_decision_or_on_a_full_hex(self) -> None:
        same = mem(episode(x1.RECOVERY_WAIT, HOLD_STEP=520))
        self.assertEqual(states(run(aboard(520, car_hex=606), [move(CAR, 606, FAR)], same)[2]), ["RECOVERY_WAIT"])
        full = [unit(800000 + i, 606, kind="tank") for i in range(3)]
        self.assertEqual(states(run(aboard(530, car_hex=606, others=full), [], same)[2]), ["RECOVERY_WAIT"])

    def test_recovery_attempts_are_bounded_then_stranded(self) -> None:
        hold = mem(episode(x1.RECOVERY_HOLD, ATTEMPTS=1, HOLD_STEP=500, HOLD_HEX=606))
        expired = aboard(501 + x1.BOUND, car_hex=606)
        self.assertEqual(states(run(expired, [], hold)[2]), ["RECOVERY_WAIT"])
        last = mem(episode(x1.RECOVERY_HOLD, ATTEMPTS=x1.RECOVERY_ATTEMPTS, HOLD_STEP=500, HOLD_HEX=606))
        out, changes, memory = run(expired, [move(CAR, 606, FAR)], last)
        self.assertEqual(states(memory), ["STRANDED"])
        self.assertEqual(x1.decode(memory)[0][x1.F_REASON], x1.EXHAUSTED)
        self.assertEqual([dict(a) for a in out], [move(CAR, 606, FAR)])
        self.assertEqual(states(run(expired, [move(CAR, 606, FAR)], memory)[2]), ["STRANDED"])

    def test_carrier_hold_is_bounded_over_a_whole_game(self) -> None:
        """A carrier stuck on a full destination: every hold ends within its bound and the episode ends."""
        memory = mem(episode(x1.AT_DESTINATION, ARRIVE=300))
        full = [unit(800000 + i, DEST, kind="tank") for i in range(3)]
        valid = {CAR: {1: None, 4: [{"target_obj_id": INF}]}}
        held = 0
        for now in range(300, 2880):
            out, _, memory = run(aboard(now, car_hex=DEST, valid=valid, others=full), [CARRIER_MOVE], memory)
            held += not out
        self.assertEqual(states(memory), ["RECOVERY_WAIT"])  # a full hex never starts a recovery hold
        self.assertEqual(held, x1.BOUND + 1)

    def test_lost_and_inconsistent(self) -> None:
        no_carrier = obs([unit(INF, START, kind="infantry")], (), {}, cur_step=150)
        for state in (x1.EMBARK_REQUESTED, x1.CARRIER_RELEASED, x1.AT_DESTINATION, x1.DISEMBARK_REQUESTED,
                      x1.RECOVERY_WAIT, x1.RECOVERY_HOLD, x1.RECOVERY_DISEMBARK):
            memory = run(no_carrier, [], mem(episode(state, ARRIVE=140, DISEMBARK=140, HOLD_STEP=140, HOLD_HEX=303)))[2]
            self.assertEqual(states(memory), ["LOST"], x1.STATES[state - 1])
        no_infantry = obs([unit(CAR, START)], (), {}, cur_step=150)
        self.assertEqual(states(run(no_infantry, [], mem(episode(x1.EMBARK_REQUESTED)))[2]), ["EMBARK_REQUESTED"])
        self.assertEqual(states(run(no_infantry, [], mem(episode(x1.CARRIER_RELEASED, RELEASE=120)))[2]), ["LOST"])
        late = obs([unit(CAR, START)], (), {}, cur_step=251)
        self.assertEqual(states(run(late, [], mem(episode(x1.EMBARK_REQUESTED)))[2]), ["LOST"])
        both = obs([unit(INF, START, kind="infantry"), unit(CAR, START, passenger_ids=[INF])],
                   [unit(INF, START, kind="infantry", on_board=1, car=CAR)], {}, cur_step=150)
        self.assertEqual(states(run(both, [], mem(episode(x1.CARRIER_RELEASED, RELEASE=120)))[2]), ["INCONSISTENT"])

    def test_episodes_are_independent(self) -> None:
        second = episode(x1.AT_DESTINATION, INF2, CAR2, ARRIVE=300)
        car2 = unit(CAR2, DEST, passenger_ids=[INF2])
        inf2 = unit(INF2, DEST, kind="infantry", on_board=1, car=CAR2)
        observation = obs([unit(INF, START, kind="infantry"), car2, unit(OTHER, START)], [inf2],
                          {CAR2: {1: None, 4: [{"target_obj_id": INF2}]}}, cur_step=380)
        out, _, memory = run(observation, [move(CAR2, DEST, FAR)], mem(episode(x1.CARRIER_RELEASED, RELEASE=120),
                                                                        second))
        self.assertEqual(states(memory), ["LOST", "DISEMBARK_REQUESTED"])
        self.assertEqual([dict(a) for a in out], [{"actor": SEAT, "obj_id": CAR2, "type": 4, "target_obj_id": INF2}])

    def test_malformed_memory_disables_every_edit(self) -> None:
        observation, actions = scene()
        for bad in (((1, 1),), ((x1.SLOT + 1, 1),), ((1, x1.EMBARK_REQUESTED), (1, 2)), (("x", 1),),
                    mem(episode(x1.EMBARK_REQUESTED), episode(x1.EMBARK_REQUESTED))):
            out, changes, memory = run(observation, actions, bad)
            self.assertEqual(([dict(a) for a in out], memory), (actions, x1.DISABLED), bad)
            out, changes, memory = run(observation, actions, memory)
            self.assertEqual(([dict(a) for a in out], changes, memory), (actions, (), x1.DISABLED))

    def test_non_play_stage_changes_nothing(self) -> None:
        observation, actions = scene(stage=1)
        out, changes, memory = run(observation, actions, mem(episode(x1.EMBARK_REQUESTED)))
        self.assertEqual(([dict(a) for a in out], changes), (actions, ()))
        self.assertEqual(states(memory), ["EMBARK_REQUESTED"])

    def test_memory_round_trip(self) -> None:
        eps = [episode(x1.EMBARK_REQUESTED), episode(x1.DONE, INF2, CAR2, END=500, REASON=0)]
        self.assertEqual(x1.decode(x1.encode(eps)), eps)
        self.assertEqual(x1.decode(()), [])


if __name__ == "__main__":
    unittest.main()
