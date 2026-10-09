"""The non-executable T12-O1 objective-zone dispersion shadow (``experiments/t12_dispersion_shadow.py``, Sprint 28)."""

from __future__ import annotations

import copy
import unittest
from types import MappingProxyType

from miaosuan_agent.decision import policy
from miaosuan_agent.experiments import t12_dispersion_shadow as ts
from miaosuan_agent.evaluation.t7_visibility import hex_distance

RED, BLUE = 0, 1
OBJ = 505
ACTOR = 7


class FakeCosts:
    """A rows x cols map whose infantry graph links every hex to its geometric neighbours at cost 1; the vehicle graph
    is the same minus ``vehicle_cut`` edges; the march graph is empty unless ``march`` lists edges."""

    def __init__(self, rows: int = 10, cols: int = 10, vehicle_cut=(), costs=None, march=(), all_cut=()) -> None:
        self.rows, self.cols = rows, cols
        self.vehicle_cut = set(vehicle_cut)
        self.all_cut = set(all_cut)
        self.costs = dict(costs or {})
        self.march = set(march)

    def neighbours(self, mode, h):
        out = {}
        for n in ts.neighbours(h, self.rows, self.cols):
            if (h, n) in self.all_cut:
                continue
            cost = self.costs.get((h, n), 1.0)
            if mode == 2 or (mode == 0 and (h, n) not in self.vehicle_cut) or (mode == 1 and (h, n) in self.march):
                out[n] = cost
        return MappingProxyType(out)


NB = ts.neighbours(OBJ, 10, 10)


def unit(obj, h=OBJ, kind=2, **kw):
    u = {"obj_id": obj, "type": kind, "sub_type": 0, "color": RED, "cur_hex": h, "move_path": (), "speed": 0,
         "keep": 0, "move_state": 0}
    u.update(kw)
    return u


def move(obj, route):
    return {"actor": ACTOR, "obj_id": obj, "type": 1, "move_path": list(route)}


def ctx(own, flags=None, actions=(), valid=None, extras=None, enemies=(), roadblocks=(), step=10, stage=2,
        costs=None):
    own_map = {u["obj_id"]: u for u in own}
    if valid is None:
        valid = {o: {1: None} for o in own_map}
    if extras is None:
        extras = {}
    full = {o: {"stop": 1, "move_to_stop_remain_time": 0, "change_state_remain_time": 0, "get_on_remain_time": 0,
                "get_off_remain_time": 0, **extras.get(o, {})} for o in own_map}
    return ts.Context(RED, step, stage, own_map, tuple(enemies), {OBJ: RED} if flags is None else flags, valid,
                      tuple(actions), costs or FakeCosts(), frozenset(roadblocks), full, ACTOR)


def only(checks):
    (c,) = [x for x in checks if x.objective == OBJ]
    return c


class GeometryTest(unittest.TestCase):
    def test_documented_neighbour_example(self) -> None:
        self.assertEqual(set(ts.neighbours(739, 100, 100)), {740, 640, 639, 738, 839, 840})

    def test_six_neighbours_inside_and_fewer_at_the_edge(self) -> None:
        self.assertEqual(len(NB), 6)
        self.assertTrue(all(hex_distance(OBJ, n) == 1 for n in NB))
        self.assertEqual(ts.neighbours(0, 10, 10), (1, 100))
        self.assertTrue(all(0 <= n // 100 < 10 and 0 <= n % 100 < 10 for n in ts.neighbours(909, 10, 10)))

    def test_even_and_odd_rows_shift(self) -> None:
        self.assertEqual(set(ts.neighbours(404, 10, 10)), {403, 405, 303, 304, 503, 504})
        self.assertEqual(set(ts.neighbours(505, 10, 10)), {504, 506, 405, 406, 605, 606})


class IdleTest(unittest.TestCase):
    def level(self, u, extra=None, acted=None):
        full = {"stop": 1, "move_to_stop_remain_time": 0, "change_state_remain_time": 0, "get_on_remain_time": 0,
                "get_off_remain_time": 0}
        full.update(extra or {})
        return ts.idle_level(u, full, acted or {}, u["obj_id"])

    def test_each_level_in_order(self) -> None:
        self.assertEqual(self.level(unit(1, speed=1, move_path=(504,))), "A_stationary")
        self.assertEqual(self.level(unit(1, move_path=(504,))), "B_no_route")
        self.assertEqual(self.level(unit(1), {"stop": 0}), "C_no_transition")
        self.assertEqual(self.level(unit(1), {"move_to_stop_remain_time": 5}), "C_no_transition")
        self.assertEqual(self.level(unit(1), {"change_state_remain_time": 5}), "C_no_transition")
        self.assertEqual(self.level(unit(1), {"get_on_remain_time": 5}), "D_no_transport_transition")
        self.assertEqual(self.level(unit(1), {"get_off_remain_time": 5}), "D_no_transport_transition")
        self.assertEqual(self.level(unit(1, keep=1)), "E_not_suppressed")
        self.assertEqual(self.level(unit(1), acted={1: [1]}), "F_no_baseline_move")
        self.assertEqual(self.level(unit(1), acted={1: [2]}), "G_no_baseline_action")
        self.assertEqual(self.level(unit(1)), "idle")

    def test_earlier_level_reported_first(self) -> None:
        self.assertEqual(self.level(unit(1, speed=2, keep=1), {"stop": 0}, {1: [1]}), "A_stationary")
        self.assertEqual(self.level(unit(1, keep=1), {"get_on_remain_time": 1}, {1: [1]}), "D_no_transport_transition")

    def test_missing_fields_are_no_transition(self) -> None:
        self.assertEqual(ts.idle_level(unit(1), {}, {}, 1), "idle")
        self.assertEqual(ts.idle_level(unit(1), {"stop": None, "move_to_stop_remain_time": None}, {}, 1), "idle")


class TriggerTest(unittest.TestCase):
    def test_two_idle_on_a_held_objective_trigger(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2)])))
        self.assertTrue(c.trigger)
        self.assertEqual(c.idle, (1, 2))

    def test_one_idle_does_not(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2, speed=1)])))
        self.assertFalse(c.trigger)
        self.assertEqual(dict(c.centre_units), {1: "idle", 2: "A_stationary"})

    def test_unheld_objective_not_examined(self) -> None:
        self.assertEqual(ts.evaluate(ctx([unit(1), unit(2)], flags={OBJ: BLUE})), ())
        self.assertEqual(ts.evaluate(ctx([unit(1), unit(2)], flags={OBJ: -1})), ())

    def test_non_play_stage(self) -> None:
        self.assertEqual(ts.evaluate(ctx([unit(1), unit(2)], stage=1)), ())

    def test_every_neighbour_full(self) -> None:
        own = [unit(1), unit(2)] + [unit(100 + 10 * i + j, n) for i, n in enumerate(NB) for j in range(4)]
        c = only(ts.evaluate(ctx(own)))
        self.assertFalse(c.trigger)
        own = own[:-1]
        self.assertTrue(only(ts.evaluate(ctx(own))).trigger)

    def test_passable_in_any_ground_mode(self) -> None:
        cut = {(OBJ, n) for n in NB}
        self.assertTrue(only(ts.evaluate(ctx([unit(1), unit(2)], costs=FakeCosts(vehicle_cut=cut)))).trigger)

    def test_impassable_in_every_mode(self) -> None:
        cut = {(OBJ, n) for n in NB}
        c = only(ts.evaluate(ctx([unit(1), unit(2)], costs=FakeCosts(all_cut=cut))))
        self.assertFalse(c.trigger)
        self.assertEqual({p for _, _, p in c.neighbour_counts}, {False})
        c = only(ts.evaluate(ctx([unit(1), unit(2)], costs=FakeCosts(all_cut=cut - {(OBJ, NB[5])}))))
        self.assertTrue(c.trigger)

    def test_held_units_are_not_idle_holders(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2)]), held={2}))
        self.assertFalse(c.trigger)
        self.assertEqual((c.idle, c.held_out), ((1,), (2,)))

    def test_passengers_and_aircraft_do_not_count(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2, kind=3)])))
        self.assertFalse(c.trigger)
        self.assertEqual(c.centre_units, ((1, "idle"),))


class LegalTest(unittest.TestCase):
    def reasons(self, c, u):
        return dict(next(x for x in c.units if x.unit == u).legal)

    def test_not_listed(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2)], valid={1: {1: None}, 2: {2: []}})))
        self.assertEqual(set(self.reasons(c, 2).values()), {"move_not_listed"})
        self.assertEqual(set(self.reasons(c, 1).values()), {"legal"})

    def test_gate_refuses_a_missing_vehicle_edge_but_not_infantry(self) -> None:
        cut = {(OBJ, NB[0])}
        c = only(ts.evaluate(ctx([unit(1), unit(2), unit(3, kind=1)], costs=FakeCosts(vehicle_cut=cut))))
        self.assertEqual(self.reasons(c, 1)[NB[0]], "gate_path_refused")
        self.assertEqual(self.reasons(c, 3)[NB[0]], "legal")

    def test_march_mode_uses_the_march_graph(self) -> None:
        c = only(ts.evaluate(ctx([unit(1, move_state=1), unit(2)], costs=FakeCosts(march={(OBJ, NB[2])}))))
        r = self.reasons(c, 1)
        self.assertEqual(r[NB[2]], "legal")
        self.assertEqual(sum(1 for v in r.values() if v == "gate_path_refused"), 5)

    def test_roadblock_stops_vehicles_only(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2, kind=1)], roadblocks={NB[1]})))
        self.assertEqual(self.reasons(c, 1)[NB[1]], "gate_path_refused")
        self.assertEqual(self.reasons(c, 2)[NB[1]], "legal")

    def test_stack_full(self) -> None:
        own = [unit(1), unit(2)] + [unit(100 + j, NB[0]) for j in range(4)]
        c = only(ts.evaluate(ctx(own)))
        self.assertEqual(self.reasons(c, 1)[NB[0]], "stack_full")
        own = [unit(1), unit(2)] + [unit(100 + j, NB[0]) for j in range(3)]
        self.assertEqual(self.reasons(only(ts.evaluate(ctx(own))), 1)[NB[0]], "legal")


class AdmissibleTest(unittest.TestCase):
    def admissible(self, c, u):
        return next(x for x in c.units if x.unit == u).admissible

    def test_exclusions(self) -> None:
        flags = {OBJ: RED, NB[0]: BLUE}
        enemy = {"obj_id": 900, "type": 2, "color": BLUE, "cur_hex": NB[1]}
        mover = unit(50, 808, move_path=(707, NB[2]))
        acts = [move(51, (NB[3], 304))]
        own = [unit(1), unit(2), mover, unit(51, 404)]
        c = only(ts.evaluate(ctx(own, flags=flags, enemies=[enemy], actions=acts)))
        self.assertEqual(set(self.admissible(c, 1)), set(NB) - {NB[0], NB[1], NB[2], NB[3]})
        f = ctx(own, flags=flags, enemies=[enemy], actions=acts)
        routes = ts.route_hexes(f)
        hexes = frozenset({NB[1]})
        self.assertEqual(ts.admissible_reason(f, NB[0], routes, hexes), "objective_hex")
        self.assertEqual(ts.admissible_reason(f, NB[1], routes, hexes), "visible_enemy")
        self.assertEqual(ts.admissible_reason(f, NB[2], routes, hexes), "own_route_hex")
        self.assertEqual(ts.admissible_reason(f, NB[3], routes, hexes), "own_route_hex")
        self.assertEqual(ts.admissible_reason(f, NB[4], routes, hexes), "admissible")


class BatchTest(unittest.TestCase):
    def outcomes(self, c):
        return {x.unit: (x.outcome, x.destination) for x in c.units}

    def test_holder_is_fewest_admissible_then_lowest_id(self) -> None:
        c = only(ts.evaluate(ctx([unit(3), unit(1), unit(2)])))
        self.assertEqual(c.holder, 1)
        valid = {1: {1: None}, 2: {}, 3: {1: None}}
        c = only(ts.evaluate(ctx([unit(1), unit(2), unit(3)], valid=valid)))
        self.assertEqual(c.holder, 2)
        self.assertEqual(self.outcomes(c)[1][0], "dispersed")
        self.assertEqual(self.outcomes(c)[3][0], "dispersed")

    def test_holder_never_moves_and_legal_tier(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2)])))
        self.assertTrue(c.legal_tier)
        self.assertEqual(self.outcomes(c)[1], ("holder", None))
        self.assertEqual(c.dispersed, ((2, NB[0]),))

    def test_destination_fewest_then_cost_then_hex(self) -> None:
        own = [unit(1), unit(2)] + [unit(100 + i, n) for i, n in enumerate(NB[:3])]
        c = only(ts.evaluate(ctx(own)))
        self.assertEqual(c.dispersed, ((2, NB[3]),))
        costs = FakeCosts(costs={(OBJ, NB[3]): 3.0, (OBJ, NB[4]): 2.0, (OBJ, NB[5]): 2.0})
        c = only(ts.evaluate(ctx(own, costs=costs)))
        self.assertEqual(c.dispersed, ((2, NB[4]),))

    def test_second_unit_takes_another_empty_hex(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2), unit(3)])))
        self.assertEqual(c.dispersed, ((2, NB[0]), (3, NB[1])))

    def test_room_runs_out(self) -> None:
        valid = {o: {1: None} for o in range(1, 6)}
        cut = {(OBJ, n) for n in NB[1:]}
        others = [unit(100, NB[0]), unit(101, NB[0])]
        own = [unit(1, kind=2), unit(2), unit(3), unit(4), unit(5)] + others
        c = only(ts.evaluate(ctx(own, valid=valid, costs=FakeCosts(vehicle_cut=cut))))
        got = self.outcomes(c)
        self.assertEqual(sorted(v[0] for v in got.values()),
                         ["dispersed", "dispersed", "holder", "no_destination_left", "no_destination_left"])

    def test_no_admissible_destination(self) -> None:
        valid = {1: {1: None}, 2: {}, 3: {}}
        c = only(ts.evaluate(ctx([unit(1), unit(2), unit(3)], valid=valid)))
        self.assertEqual(self.outcomes(c)[3][0], "no_admissible_destination")
        self.assertEqual(c.holder, 2)
        self.assertEqual(self.outcomes(c)[1][0], "dispersed")

    def test_no_dispersal_means_no_legal_tier(self) -> None:
        c = only(ts.evaluate(ctx([unit(1), unit(2)], valid={1: {}, 2: {}})))
        self.assertTrue(c.trigger)
        self.assertFalse(c.legal_tier)
        self.assertEqual(c.dispersed, ())

    def test_two_objectives_share_one_count(self) -> None:
        other = 507
        flags = {OBJ: RED, other: RED}
        shared = sorted(set(NB) & set(ts.neighbours(other, 10, 10)))
        self.assertTrue(shared)
        keep = set(shared)
        valid = {o: {1: None} for o in (1, 2, 3, 4)}
        cut = {(OBJ, n) for n in NB if n not in keep} | {(other, n) for n in ts.neighbours(other, 10, 10) if n not in keep}
        own = [unit(1), unit(2), unit(3, other), unit(4, other)] + [unit(100 + j, shared[0]) for j in range(3)]
        checks = ts.evaluate(ctx(own, flags=flags, valid=valid, costs=FakeCosts(vehicle_cut=cut)))
        self.assertEqual([c.objective for c in checks], [OBJ, other])
        self.assertEqual([d for c in checks for d in c.dispersed], [(2, shared[0])])
        self.assertEqual({x.unit: x.outcome for x in checks[1].units}, {3: "holder", 4: "no_destination_left"})


class DecideTest(unittest.TestCase):
    def test_appended_after_baseline_and_hold(self) -> None:
        base = [{"actor": ACTOR, "obj_id": 9, "type": 2, "target_obj_id": 1, "weapon_id": 1}]
        own = [unit(1), unit(2), unit(9, 909)]
        r = ts.decide(ctx(own, actions=base), ts.DispersionMemory())
        self.assertEqual(list(r.actions), base + [{"actor": ACTOR, "obj_id": 2, "type": 1, "move_path": [NB[0]]}])
        self.assertEqual(r.memory.holds, ((2, OBJ, NB[0], 10),))
        self.assertEqual([e.kind for e in r.events], ["disperse"])

    def test_later_move_withheld_and_not_redispersed(self) -> None:
        own = [unit(1), unit(2)]
        m = ts.decide(ctx(own), ts.DispersionMemory()).memory
        own2 = [unit(1), unit(2, NB[0])]
        r = ts.decide(ctx(own2, actions=[move(2, (NB[0], 303))], step=11), m)
        self.assertEqual(r.actions, ())
        self.assertEqual(r.withheld, (0,))
        self.assertEqual(r.memory, m)
        r = ts.decide(ctx([unit(1), unit(2)], step=12), m)
        self.assertEqual(r.added, ())

    def test_releases(self) -> None:
        m = ts.DispersionMemory(((2, OBJ, NB[0], 10),))
        r = ts.decide(ctx([unit(1), unit(2, NB[0])], flags={OBJ: BLUE}, actions=[move(2, (NB[0],))], step=20), m)
        self.assertEqual(r.memory.holds, ())
        self.assertEqual(r.withheld, ())
        self.assertEqual([(e.kind, e.reason) for e in r.events], [("release", "objective_not_held")])
        r = ts.decide(ctx([unit(1)], step=20), m)
        self.assertEqual([(e.kind, e.reason) for e in r.events], [("release", "unit_absent")])

    def test_non_play_unchanged(self) -> None:
        m = ts.DispersionMemory(((2, OBJ, NB[0], 10),))
        r = ts.decide(ctx([unit(1), unit(2)], stage=1, actions=[move(2, (NB[0],))]), m)
        self.assertEqual((r.actions, r.memory, r.events), ((move(2, (NB[0],)),), m, ()))

    def test_deterministic_and_inputs_unmodified(self) -> None:
        c = ctx([unit(3), unit(1), unit(2)], actions=[move(5, (101,))])
        before = copy.deepcopy((dict(c.own), c.actions))
        a, b = ts.decide(c, ts.DispersionMemory()), ts.decide(c, ts.DispersionMemory())
        self.assertEqual(a, b)
        self.assertEqual((dict(c.own), c.actions), before)


class IdentityTest(unittest.TestCase):
    def test_not_executable_and_not_a_policy(self) -> None:
        self.assertFalse(ts.EXECUTABLE)
        self.assertEqual(ts.STATUS, "ANALYSIS SHADOW - NON-EXECUTABLE")
        self.assertNotIn(ts.SHADOW_ID, policy.POLICIES)
        self.assertFalse(any(isinstance(v, type) and hasattr(v, "setup") for v in vars(ts).values()))

    def test_only_this_sprints_files_name_the_shadow(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        users = sorted(p.relative_to(root).as_posix() for folder in ("src", "scripts", "tests")
                       for p in (root / folder).rglob("*.py") if "t12_dispersion_shadow" in p.read_text(encoding="utf-8")
                       and p.name != "t12_dispersion_shadow.py")
        self.assertEqual(users, ["scripts/mutate_s28.py", "scripts/s28_t12.py",
                                 "src/miaosuan_agent/evaluation/s28_t12.py", "tests/test_s28_t12.py",
                                 "tests/test_t12_dispersion_shadow.py"])

    def test_frozen_parameters(self) -> None:
        self.assertEqual((ts.MIN_IDLE, ts.STACK_LIMIT, tuple(int(m) for m in ts.GROUND_MODES)), (2, 4, (0, 1, 2)))
        self.assertEqual(ts.IDLE_LEVELS, ("A_stationary", "B_no_route", "C_no_transition", "D_no_transport_transition",
                                          "E_not_suppressed", "F_no_baseline_move", "G_no_baseline_action"))
        self.assertEqual(ts.RELEASE_REASONS, ("objective_not_held", "unit_absent"))

    def test_labels_carry_no_digit_word(self) -> None:
        for label in ts.IDLE_LEVELS + ts.LEGAL_REASONS + ts.ADMISSIBLE_REASONS + ts.BATCH_OUTCOMES + ts.RELEASE_REASONS:
            self.assertFalse(any(w.isdigit() for w in label.replace("_", " ").split()), label)


if __name__ == "__main__":
    unittest.main()
