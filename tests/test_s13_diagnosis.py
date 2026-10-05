"""Sprint 13 offline diagnosis (``evaluation/s13_diagnosis.py``). SYNTHETIC observations and rows.

Geometry is never typed by hand: the starting hexes of each scenario are chosen by the project's router on the 10 x 10
synthetic grid and asserted as preconditions (the helpers of ``tests/test_t9_batch.py``).
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Sequence

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import Memory
from miaosuan_agent.decision.routing import Router, move_mode
from miaosuan_agent.evaluation import s12_capture as cap
from miaosuan_agent.evaluation import s13_diagnosis as sd
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn
from tests.test_t9_batch import A, B, INFANTRY, RED, SEAT, VEHICLE, observation, route, unit

COSTS = MoveCosts.from_raw(syn.cost_data())
ROUTER = Router(COSTS)


def cost(start: int, goal: int, kind=VEHICLE) -> float:
    return ROUTER.shortest_paths(start, move_mode(kind[0], 0)).cost[goal]


def between(count: int, skip: Sequence[int] = ()) -> List[int]:
    """``count`` hexes from which A is the cheaper objective and B costs at most twice as much (T9-v1's detour)."""
    out = []
    for hex_ in sorted(range(0, 1000), key=lambda h: (cost(h, A) if 0 <= h % 100 < 10 and h // 100 < 10 else 99, h)):
        if hex_ % 100 >= 10 or hex_ // 100 >= 10 or hex_ in (A, B) or hex_ in skip:
            continue
        a, b = cost(hex_, A), cost(hex_, B)
        if a < b <= 2 * a:
            out.append(hex_)
        if len(out) == count:
            return out
    raise AssertionError("not enough hexes between the objectives")


def decide(obs, doomed=frozenset()) -> Dict[str, Any]:
    raw = dict(obs.fields)
    return sd.decide_policies(raw, SEAT, RED, ea.AddonMemory(), COSTS, lambda rows: frozenset(doomed))


def captured(obs) -> Dict[str, Any]:
    return cap.reconstruct(dict(obs.fields), SEAT, RED, ea.AddonMemory(), COSTS, True)


def classes(decided) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in sd.unit_forms(decided, RED):
        if row["class"]:
            out[row["class"]] = out.get(row["class"], 0) + 1
    return out


def admitted(decided, name: str = "O1") -> set:
    return set(decided[f"{name}_allocation"].selected) - set(decided["allocation"].selected)


class Scenarios(unittest.TestCase):
    """The four mechanism combinations of the protocol (section 11)."""

    def redistribution_only(self):
        starts = between(6)
        return observation([unit(930100 + i, h) for i, h in enumerate(starts)], cities=(A, B))

    def reservation_only(self):
        movers = [unit(930200 + i, h, move_path=route(h, A)) for i, h in enumerate((303, 703, 309, 709))]
        claimants = [unit(930210 + i, h) for i, h in enumerate((504, 506))]
        return observation(movers + claimants, cities=(A,)), 930200

    def test_redistribution_only(self) -> None:
        obs = self.redistribution_only()
        base = ShootReservationPolicy(COSTS).decide(obs, SEAT, RED, Memory())
        self.assertEqual({a["move_path"][-1] for a in base.actions if a["type"] == 1}, {A})  # precondition
        decided = decide(obs)
        self.assertEqual(sd.verify(decided, captured(obs), captured(obs)["actions"]), [])
        found = classes(decided)
        redirects = [r for r in sd.unit_forms(decided, RED) if r["v1"] == sd.REDIRECT]
        self.assertEqual(len(redirects), 2)
        self.assertTrue(all(r["v1_to"] == B and r["cause"] == "CAPACITY" for r in redirects))
        self.assertEqual(sum(found.get(c, 0) for c in sd.CLASSES[:3]), 2)
        self.assertEqual(admitted(decided), set())  # nothing doomed: O1 is v3
        self.assertEqual(set(decided["O2_allocation"].redirected), {r["unit"] for r in redirects
                                                                    if r["v3"] != sd.KEEP} | set(
            decided["O2_allocation"].redirected))
        self.assertEqual(len(decided["O2_allocation"].redirected), 2)
        self.assertTrue(all(to == B for _, to in decided["O2_allocation"].redirected.values()))

    def test_unproductive_reservation_only(self) -> None:
        obs, doomed = self.reservation_only()
        plain = decide(obs)
        self.assertEqual(len(plain["allocation"].selected), 0)  # four counted movers: no free place
        self.assertEqual(plain["incumbents"][A]["movers"], tb.CAPACITY)
        found = decide(obs, {doomed})
        self.assertEqual(sd.verify(found, captured(obs), captured(obs)["actions"]), [])
        self.assertEqual([r for r in sd.unit_forms(found, RED) if r["v1"] == sd.REDIRECT], [])
        self.assertEqual(len(admitted(found)), 1)
        self.assertEqual(found["O2_allocation"].redirected, {})
        self.assertEqual(admitted(found, "O3"), admitted(found))

    def test_both_mechanisms(self) -> None:
        starts = between(2)
        movers = [unit(930300 + i, h, move_path=route(h, A)) for i, h in enumerate((303, 703, 309, 709))]
        claimants = [unit(930310 + i, h) for i, h in enumerate(starts)]
        obs = observation(movers + claimants, cities=(A, B))
        decided = decide(obs, {930300})
        self.assertEqual(sd.verify(decided, captured(obs), captured(obs)["actions"]), [])
        redirected = {r["unit"] for r in sd.unit_forms(decided, RED) if r["v1"] == sd.REDIRECT}
        self.assertEqual(redirected, {930310, 930311})
        self.assertEqual(len(admitted(decided)), 1)
        self.assertTrue(admitted(decided) <= redirected)
        o3 = decided["O3_allocation"]
        self.assertEqual(len(o3.selected), 1)
        self.assertEqual(len(o3.redirected), 1)

    def test_neither(self) -> None:
        obs = observation([unit(930400 + i, h) for i, h in enumerate((503, 507))], cities=(A, B))
        decided = decide(obs)
        self.assertEqual(classes(decided), {})
        self.assertEqual(admitted(decided), set())
        self.assertEqual(admitted(decided, "O2"), set())
        for name in ("t9-v1", "t9-v2", "O1", "O2", "O3"):
            self.assertEqual(decided[name], decided["t9-v3"])

    def test_oracle_allocator_without_modifications_is_v3(self) -> None:
        cases = [self.redistribution_only(), self.reservation_only()[0],
                 observation([unit(930500 + k, 100, INFANTRY, move_path=route(100, A, INFANTRY)) for k in range(4)]
                             + [unit(930510, 504)], cur_step=2880 - 300),
                 observation([unit(930520 + k, 100) for k in range(9)])]
        for obs in cases:
            actions = ShootReservationPolicy(COSTS).decide(obs, SEAT, RED, Memory()).actions
            real = tb.allocate(obs, SEAT, RED, actions, ROUTER)
            mine = sd.oracle_allocate(obs, SEAT, RED, actions, ROUTER)
            self.assertEqual(mine.actions, real.actions)
            self.assertEqual((mine.selected, mine.staged, mine.withheld), (real.selected, real.staged, real.withheld))

    def test_redirect_to_an_alternative_that_cannot_arrive_is_dropped(self) -> None:
        starts = between(6)
        probe = observation([unit(930600 + i, h) for i, h in enumerate(starts)], cities=(A, B))
        decided = decide(probe)
        times = {u: sd.free_flow(ROUTER, next(x for x in probe.operators() if x.obj_id == u),
                                 route(next(x for x in probe.operators() if x.obj_id == u).cur_hex, B))
                 for u in decided["O2_allocation"].redirected}
        late_step = 2880 - min(times.values())
        late = observation([unit(930600 + i, h) for i, h in enumerate(starts)], cities=(A, B), cur_step=late_step)
        found = decide(late)
        self.assertEqual(found["O2_allocation"].redirected, {})
        self.assertGreater(found["O2_allocation"].redirect_infeasible, 0)
        self.assertGreater(sum(1 for r in sd.unit_forms(found, RED) if r["v1"] == sd.REDIRECT), 0)  # T9-v1 still would

    def test_no_redirect_to_a_full_alternative_or_beyond_the_detour_bound(self) -> None:
        starts = between(2)
        full_a = [unit(930610 + i, h, move_path=route(h, A)) for i, h in enumerate((303, 703, 309, 709))]
        full_b = [unit(930620 + i, h, move_path=route(h, B)) for i, h in enumerate((808, 708, 807, 707))]
        claimants = [unit(930630 + i, h) for i, h in enumerate(starts)]
        open_b = decide(observation(full_a + claimants, cities=(A, B)))
        self.assertEqual(len(open_b["O2_allocation"].redirected), 2)  # precondition: B open, both redirected
        both_full = decide(observation(full_a + full_b + claimants, cities=(A, B)))
        self.assertEqual(both_full["incumbents"][B]["movers"], tb.CAPACITY)
        self.assertEqual(both_full["O2_allocation"].redirected, {})
        far = next(h for h in range(100) if h % 100 < 10 and h not in (A, B) and cost(h, A) < cost(h, B)
                   and cost(h, B) > 2 * cost(h, A))
        detour = decide(observation(full_a + [unit(930640, far)], cities=(A, B)))
        self.assertIn(930640, detour["allocation"].claimants)
        self.assertEqual(detour["O2_allocation"].redirected, {})
        self.assertEqual(detour["v1_outcomes"].get(930640), "withhold")

    def test_mover_bound_excludes_the_hex_being_entered_at_the_exact_boundary(self) -> None:
        path = route(100, A, INFANTRY)
        times = tb.path_times(ROUTER, INFANTRY[0], 0, INFANTRY[1], 100, path)[0]
        movers = [unit(930650 + k, 100, INFANTRY, move_path=path) for k in range(tb.CAPACITY)]
        obs = observation(movers + [unit(930660, 504)], cities=(A,), cur_step=2880 - sum(times))
        rows, _ = sd.counted_incumbents(obs, RED, ROUTER)
        self.assertEqual((rows[A]["movers"], rows[A]["phantom"]), (tb.CAPACITY, 0))
        decided = decide(obs)
        self.assertEqual(decided["identity_allocation"].selected, decided["allocation"].selected)
        self.assertNotIn(930660, decided["allocation"].selected)

    def test_a_late_claimant_with_free_places_is_not_selected_by_the_oracle(self) -> None:
        obs = observation([unit(930670, 100, INFANTRY)], cities=(A,), cur_step=2880 - 100)
        decided = decide(obs)
        self.assertEqual(decided["allocation"].claimants[930670].status, sd.LATE)
        for name in ("identity", "O1", "O2", "O3"):
            self.assertEqual(decided[f"{name}_allocation"].selected, {})

    def test_a_planted_submission_difference_is_caught(self) -> None:
        obs = self.redistribution_only()
        decided = decide(obs)
        row = captured(obs)
        self.assertTrue(sd.verify(decided, row, row["actions"][1:]))
        bad = dict(row, baseline_trace_sha256="0" * 64)
        self.assertTrue(sd.verify(decided, bad, row["actions"]))
        moved = dict(row, allocation=dict(row["allocation"], selected={}))
        self.assertTrue(sd.verify(decided, moved, row["actions"]))


class Classification(unittest.TestCase):
    def test_every_class_in_order(self) -> None:
        K, R, S, W = sd.KEEP, sd.REDIRECT, sd.STAGE, sd.WITHHOLD
        self.assertEqual(sd.classify(R, K, None, None), "CROSS_OBJECTIVE_REDIRECTION_V1_ONLY")
        self.assertEqual(sd.classify(R, S, sd.FULL, None), "STAGING_VERSUS_REDIRECTION")
        self.assertEqual(sd.classify(R, W, sd.LATE, None), "WITHHOLDING_VERSUS_REDIRECTION")
        self.assertEqual(sd.classify(K, S, sd.LATE, None), "END_OF_GAME_FEASIBILITY_EXCLUSION")
        self.assertEqual(sd.classify(K, W, sd.LATE, None), "END_OF_GAME_FEASIBILITY_EXCLUSION")
        self.assertEqual(sd.classify(W, K, None, "keep"), "INCUMBENT_MOVER_DIFFERENCE")
        self.assertEqual(sd.classify(W, K, None, "withhold"), "SAME_OBJECTIVE_CAPACITY_SELECTION")
        self.assertEqual(sd.classify(K, S, sd.FULL, None), "SAME_OBJECTIVE_CAPACITY_SELECTION")
        self.assertEqual(sd.classify(W, S, sd.FULL, None), "STAGING_VERSUS_WITHHOLDING")
        self.assertEqual(sd.classify(K, K, None, None), "OTHER")

    def test_phantom_incumbents_are_the_incumbent_mover_class(self) -> None:
        bound = sum(tb.path_times(ROUTER, INFANTRY[0], 0, INFANTRY[1], 100, route(100, A, INFANTRY))[0][1:])
        far = [unit(930700 + k, 100, INFANTRY, move_path=route(100, A, INFANTRY)) for k in range(tb.CAPACITY)]
        obs = observation(far + [unit(930710, 504)], cities=(A,), cur_step=2880 - bound)
        decided = decide(obs)
        row = next(r for r in sd.unit_forms(decided, RED) if r["unit"] == 930710)
        self.assertEqual((row["v1"], row["v3"], row["class"]), (sd.WITHHOLD, sd.KEEP, "INCUMBENT_MOVER_DIFFERENCE"))

    def test_a_redirect_caused_only_by_phantom_incumbents(self) -> None:
        bound = sum(tb.path_times(ROUTER, INFANTRY[0], 0, INFANTRY[1], 100, route(100, A, INFANTRY))[0][1:])
        far = [unit(930720 + k, 100, INFANTRY, move_path=route(100, A, INFANTRY)) for k in range(tb.CAPACITY)]
        start = between(1)[0]
        obs = observation(far + [unit(930730, start)], cities=(A, B), cur_step=2880 - bound)
        decided = decide(obs)
        row = next(r for r in sd.unit_forms(decided, RED) if r["unit"] == 930730)
        self.assertEqual((row["v1"], row["v1_to"], row["v3"]), (sd.REDIRECT, B, sd.KEEP))
        self.assertEqual((row["class"], row["cause"]), ("CROSS_OBJECTIVE_REDIRECTION_V1_ONLY", "PHANTOM_INCUMBENTS"))
        self.assertEqual(row["phantom_at_destination"], tb.CAPACITY)


class Reservations(unittest.TestCase):
    def test_holder_destroyed_after_several_blocked_decisions_is_released_and_replaced(self) -> None:
        counted = [{}, {A: {7: 300}}, {A: {7: 280}}, {A: {7: 260}}, {}, {}]
        eps = sd.episodes(counted, {(7, A): [0]})
        self.assertEqual(len(eps), 1)
        ep = eps[0]
        self.assertEqual((ep["selection"], ep["first_counted"], ep["last_counted"]), (0, 1, 3))
        lost_at = {7: 4}
        self.assertEqual(sd.holder_fate(7, A, 1, lambda u, c, s: None, lost_at), ("DESTROYED", 4))
        self.assertEqual(lost_at[7], ep["last_counted"] + 1)  # released at the next decision

    def test_honoured_and_alive_holders(self) -> None:
        self.assertEqual(sd.holder_fate(8, A, 1, lambda u, c, s: 5, {}), ("HONOURED", None))
        self.assertEqual(sd.holder_fate(8, A, 1, lambda u, c, s: 5, {8: 9}), ("HONOURED", None))
        self.assertEqual(sd.holder_fate(8, A, 1, lambda u, c, s: None, {}), ("ALIVE_NOT_ARRIVED", None))
        self.assertEqual(sd.holder_fate(8, A, 6, lambda u, c, s: None, {8: 3}), ("ALIVE_NOT_ARRIVED", None))

    def test_a_reselected_unit_starts_a_new_episode_at_its_new_selection(self) -> None:
        counted = [{}, {A: {7: 300}}, {}, {}, {A: {7: 200}}, {A: {7: 180}}]
        eps = sd.episodes(counted, {(7, A): [0, 3]})
        self.assertEqual([(e["selection"], e["first_counted"], e["last_counted"]) for e in eps], [(0, 1, 1), (3, 4, 5)])

    def test_a_faster_claimant_blocked_by_an_incumbent(self) -> None:
        slow = unit(930800, 100, INFANTRY, move_path=route(100, A, INFANTRY))
        movers = [slow] + [unit(930801 + i, h, move_path=route(h, A)) for i, h in enumerate((303, 703, 309))]
        obs = observation(movers + [unit(930810, 504)], cities=(A,))
        decided = decide(obs)
        allocation = decided["allocation"]
        claimant = allocation.claimants[930810]
        self.assertNotIn(930810, allocation.selected)
        bound = decided["incumbents"][A]["mover_bounds"][930800]
        self.assertLess(claimant.free_flow, bound)  # the blocked claimant would arrive sooner
        self.assertEqual(admitted(decide(obs, {930800})), {930810})


class Features(unittest.TestCase):
    def raw(self, enemy_hexes, own_hex=303, blood=8, max_blood=10, keep=0, flag=-1):
        units = [unit(930900, own_hex, blood=blood, max_blood=max_blood, keep=keep)]
        units += [unit(930950 + i, h, color=1) for i, h in enumerate(enemy_hexes)]
        obs = observation(units, cities=(A,))
        raw = dict(obs.fields)
        raw["cities"] = [dict(c, flag=flag) for c in raw["cities"]]
        return raw

    def test_features_read_only_the_seat_observation(self) -> None:
        path = route(303, A)
        f = sd.features(self.raw([506]), RED, 930900, A, path, 120, 2)
        self.assertEqual(f["seen_enemies"], 1)
        self.assertEqual(f["nearest_seen_enemy"], ea.hex_distance(303, 506))
        self.assertEqual(f["route_nearest_seen_enemy"], min(ea.hex_distance(h, 506) for h in [303] + path))
        self.assertEqual(f["contested"], 1)  # an enemy within 2 hexes of the objective
        self.assertEqual(f["strength_fraction"], 0.8)
        self.assertEqual((f["free_flow"], f["route_length"], f["counted_incumbents"]), (120, len(path), 2))
        quiet = sd.features(self.raw([]), RED, 930900, A, path, 120, 0)
        self.assertEqual((quiet["seen_enemies"], quiet["nearest_seen_enemy"], quiet["contested"]), (0, None, 0))
        self.assertEqual(sd.features(self.raw([], flag=1), RED, 930900, A, path, 120, 0)["contested"], 1)
        self.assertEqual(sd.features(self.raw([], flag=RED), RED, 930900, A, path, 120, 0)["contested"], 0)
        self.assertEqual(sd.features(self.raw([506], flag=RED), RED, 930900, A, path, 120, 0)["contested"], 0)

    def test_no_feature_that_cannot_identify_destruction_is_called_separating(self) -> None:
        rows = []
        for game in ("g1", "g2", "g3", "g4"):
            for i in range(12):
                rows.append({"game": game, "lost": i % 3 == 0, "noise": i % 4, "planted": 10 if i % 3 == 0 else 1})
        self.assertFalse(sd.separation(rows, "noise")["separating"])
        found = sd.separation(rows, "planted")
        self.assertTrue(found["separating"])
        self.assertEqual(found["pooled_auc"], 1.0)
        reverse = [dict(r, planted=-r["planted"]) for r in rows]
        self.assertTrue(sd.separation(reverse, "planted")["separating"])
        self.assertEqual(sd.separation(reverse, "planted")["pooled_auc"], 0.0)
        # a pooled separation that one eligible game contradicts is not separating
        flipped = [dict(r, planted=(1 if r["lost"] else 10)) if r["game"] == "g4" else r for r in rows]
        self.assertFalse(sd.separation(flipped, "planted")["separating"])

    def test_auc_counts_ties_as_one_half_and_quartiles_cover_every_row(self) -> None:
        self.assertEqual(sd.auc([1, 2], [1, 2]), 0.5)
        self.assertEqual(sd.auc([3], [1, 2, 3]), 5 / 6)
        self.assertIsNone(sd.auc([], [1]))
        rows = [{"lost": i % 2 == 0, "x": i} for i in range(20)] + [{"lost": True, "x": None}]
        table = sd.quartile_table(rows, "x")
        self.assertEqual(sum(b["lost"] + b["other"] for b in table), 20)
        self.assertEqual(len(table), 4)
        binary = sd.quartile_table([{"lost": i < 3, "x": int(i < 5)} for i in range(10)], "x")
        self.assertEqual(binary, [{"from": 0.0, "to": 0.0, "lost": 0, "other": 5},
                                  {"from": 1.0, "to": 1.0, "lost": 3, "other": 2}])


class Sequences(unittest.TestCase):
    def test_stays_below_requires_every_later_snapshot(self) -> None:
        self.assertEqual(sd.stays_below([5, 1, 6, 1, 1], [3, 3, 3, 3, 3]), 3)
        self.assertIsNone(sd.stays_below([5, 1, 1, 1, 4], [3, 3, 3, 3, 3]))
        self.assertEqual(sd.stays_below([None, 1, 1], [None, 3, 3]), 1)
        self.assertIsNone(sd.stays_below([3, 3], [3, 3]))  # equal is not below

    def test_characteristic_pattern_and_contradiction(self) -> None:
        own = lambda labels: [{"k": 0, "own": []}, {"k": 50, "own": labels}]
        population = [own(["a"])] * 12 + [own([])] * 3
        pattern = sd.characteristic(population, ["a", "b"])
        self.assertEqual(pattern[1], {"a": "own", "b": "not own"})
        self.assertEqual(sd.first_contradiction(own([]), pattern), {"k": 50, "objective": "a", "expected": "own"})
        self.assertIsNone(sd.first_contradiction(own(["a"]), pattern))
        weaker = sd.characteristic([own(["a"])] * 11 + [own([])] * 4, ["a"])
        self.assertEqual(weaker[1], {})

    def test_coverage_capture_order_and_placement(self) -> None:
        series = [{"k": 0, "own": []}, {"k": 50, "own": ["b"]}, {"k": 100, "own": ["a", "b"]}]
        self.assertEqual(sd.coverage_series(series), [None, 1.0, 1.5])
        self.assertEqual(sd.capture_order(series), [(50, "b"), (100, "a")])
        self.assertEqual(sd.placement(5, [1, 5, 9, None]), {"value": 5, "n": 3, "min": 1, "median": 5, "max": 9,
                                                            "below": 1, "equal": 1})


class Disposition(unittest.TestCase):
    seats = {"g1": "H1", "g2": "H2", "g3": "H1", "g4": "H2"}

    @staticmethod
    def game(a_units=5, a_red=10, a_emit=20, b_units=5, b_adm=10, b_held=50, a_first=10, b_first=10, d=None):
        return sd.game_materiality({"distinct_redirected": a_units, "redirects": a_red, "v1_emitted_ground": a_emit,
                                    "first_step": a_first},
                                   {"distinct_admitted": b_units, "admitted_decisions": b_adm, "held_selectable": b_held,
                                    "first_step": b_first}, d)

    def test_materiality_thresholds_are_inclusive_and_onset_must_precede_divergence(self) -> None:
        self.assertTrue(self.game(a_units=4, a_red=5, a_emit=20)["a_material"])
        self.assertFalse(self.game(a_units=3)["a_material"])
        self.assertFalse(self.game(a_red=4, a_emit=20)["a_material"])
        self.assertTrue(self.game(b_units=4, b_adm=5, b_held=50)["b_material"])
        self.assertFalse(self.game(b_adm=4, b_held=50)["b_material"])
        self.assertFalse(self.game(b_units=3)["b_material"])
        self.assertFalse(self.game(a_first=100, d=100)["a_material"])
        self.assertTrue(self.game(a_first=99, d=100)["a_material"])
        self.assertFalse(self.game(b_first=None)["b_material"])
        self.assertFalse(self.game(a_emit=0)["a_material"])

    def rule(self, a, b, overlap=0.1, sa=20, sb=20, prospective=True):
        games = {g: {"a_material": g in a, "b_material": g in b} for g in self.seats}
        return sd.disposition(games, self.seats, overlap, sa, sb, prospective)

    def test_every_branch(self) -> None:
        every = ("g1", "g2", "g3", "g4")
        self.assertEqual(self.rule((), ())["label"], "INSUFFICIENT_FOR_REVISION")
        self.assertEqual(self.rule(every, ())["label"], "REDISTRIBUTION_DOMINANT")
        self.assertEqual(self.rule((), every)["label"], "RESERVATION_LIFETIME_DOMINANT")
        self.assertEqual(self.rule((), every, prospective=False)["label"], "INSUFFICIENT_FOR_REVISION")
        self.assertEqual(self.rule(every, every)["label"], "BOTH_MECHANISMS_MATERIAL")
        self.assertEqual(self.rule(every, every, sb=4, sa=20)["label"], "REDISTRIBUTION_DOMINANT")
        self.assertEqual(self.rule(every, every, sb=5, sa=20)["label"], "BOTH_MECHANISMS_MATERIAL")
        self.assertEqual(self.rule(every, every, sa=4, sb=20)["label"], "RESERVATION_LIFETIME_DOMINANT")
        self.assertEqual(self.rule(every, every, sa=4, sb=20, prospective=False)["label"], "INSUFFICIENT_FOR_REVISION")
        self.assertEqual(self.rule(every, every, overlap=0.6, sa=20, sb=19)["label"], "REDISTRIBUTION_DOMINANT")
        self.assertEqual(self.rule(every, every, overlap=0.6, sa=19, sb=20)["label"], "RESERVATION_LIFETIME_DOMINANT")
        self.assertEqual(self.rule(every, every, overlap=0.5)["label"], "BOTH_MECHANISMS_MATERIAL")

    def test_three_games_with_both_seats_are_needed(self) -> None:
        self.assertEqual(self.rule(("g1", "g2"), ())["label"], "INSUFFICIENT_FOR_REVISION")
        self.assertEqual(self.rule(("g1", "g2", "g3"), ())["label"], "REDISTRIBUTION_DOMINANT")
        only_h1 = {"g1": "H1", "g2": "H1", "g3": "H1", "g4": "H2"}
        games = {g: {"a_material": g != "g4", "b_material": False} for g in only_h1}
        self.assertEqual(sd.disposition(games, only_h1, 0.0, 1, 0, True)["label"], "INSUFFICIENT_FOR_REVISION")


class Privacy(unittest.TestCase):
    def test_public_check_rejects_private_keys_and_values(self) -> None:
        self.assertEqual(sd.public_check({"count": 3, "label": "80-point objective A"}, {930001, 4341}), [])
        self.assertTrue(sd.public_check({"unit": 3}, set()))
        self.assertTrue(sd.public_check({"rows": [{"move_path": [1]}]}, set()))
        self.assertTrue(sd.public_check({"count": 4341}, {4341}))
        self.assertTrue(sd.public_check({"text": "unit 930001 lost"}, {930001}))
        self.assertTrue(sd.public_check({"930001": 1}, {930001}))
        self.assertEqual(sd.public_check({"count": 4341}, {4341}, allowed={"$.count"}), [])

    def test_the_drivers_public_aggregates_carry_no_planted_id_or_hex(self) -> None:
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "scripts" / "s13_v3_diagnosis.py"
        spec = importlib.util.spec_from_file_location("s13_driver_under_test", path)
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        planted = {930001, 930002, 4341, 5038}
        episodes = [{"unit": 930001, "objective": 4341, "label": "80-point objective A", "fate": fate,
                     "counted_decisions": 7, "blocked_claimant_decisions": 3, "blocked_claimants": 1,
                     "blocked_free_flow": [120, 140, 160], "faster_blocked_decisions": 2, "faster_blocked_claimants": 1,
                     "selection_free_flow": 300, "hexes_reached": 2, "path_hexes": 5, "kind": "vehicle",
                     "destroyed_step": 812, "released_next_decision": True, "replacement_decision": 900,
                     "release_to_replacement_steps": 88, "replacement_outcomes": ["OCCUPIED"],
                     "replacement_to_arrival_steps": 60}
                    for fate in ("DESTROYED", "HONOURED", "ALIVE_NOT_ARRIVED")]
        summary = driver.episode_summary(episodes)
        self.assertEqual(summary["destroyed_blocking"]["holders"], 1)
        self.assertEqual(summary["destroyed_blocking"]["replacement_occupied_or_held"], 1)
        self.assertEqual(sd.public_check(summary, planted), [])
        holders = driver.holder_summary([{"fate": "DESTROYED", "decisions": 4, "near_share": 0.5,
                                          "weakened_share": 0.25, "unit": 930002}])
        self.assertEqual(sd.public_check(holders, planted), [])
        self.assertEqual(holders["DESTROYED"]["mean_share_with_enemy_within_3"], 0.5)


if __name__ == "__main__":
    unittest.main()
