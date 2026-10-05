"""Sprint 11 replay analysis (``evaluation/t9_batch_replay.py``) on SYNTHETIC decisions: every check must be able to
fail. Each test plants one defect in an emitted action list (or in an allocator) and requires the check to see it."""

from __future__ import annotations

import unittest

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.evaluation import t9_batch_replay as rp
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from miaosuan_agent.experiments.t9_staging import StagingAddon
from tests.fixtures import synthetic as syn
from tests.test_t9_batch import A, B, INFANTRY, RED, SEAT, observation, route, unit

SHOT = {"actor": SEAT, "type": 2, "obj_id": 999999, "target_obj_id": 1, "weapon_id": 1}


class ReplayAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        self.router = Router(self.costs)
        self.obs = observation([unit(903000 + k, h) for k, h in enumerate((503, 507, 303, 703, 100, 900))],
                               cities=(A, B))
        self.base = [dict(a) for a in ShootReservationPolicy(self.costs).decide(self.obs, SEAT, RED,
                                                                               rp_memory()).actions] + [SHOT]

    def check(self, emitted):
        return rp.structural(self.obs, RED, self.base, emitted, self.router)

    def test_baseline_itself_is_clean(self) -> None:
        row = self.check(self.base)
        self.assertEqual(row["kept"], 6)
        for key in ("cross_objective", "prefix_failures", "invented", "unrelated_changed", "withheld", "late_owners"):
            self.assertEqual(row.get(key, 0), 0, key)

    def test_candidate_is_clean_and_bounded(self) -> None:
        allocation = tb.allocate(self.obs, SEAT, RED, self.base, self.router)
        row = self.check(allocation.actions)
        self.assertEqual((row.get("cross_objective", 0), row.get("prefix_failures", 0), row.get("invented", 0),
                          row["unrelated_changed"]), (0, 0, 0, 0))
        self.assertEqual(row["kept"], tb.CAPACITY)
        before = rp.commitments(self.obs, RED, self.router)
        self.assertEqual(rp.capacity_check(before, row["owners"]).get("caused", 0), 0)

    def test_planted_cross_objective_move_is_seen(self) -> None:
        emitted = [dict(a) for a in self.base]
        emitted[0] = dict(emitted[0], move_path=route(emitted[0]["move_path"][0], B))
        self.assertEqual(self.check(emitted)["cross_objective"], 1)

    def test_planted_stop_on_another_objective_on_the_route_is_cross_objective(self) -> None:
        probe = observation([unit(903400, 501)])
        base = [dict(a) for a in ShootReservationPolicy(self.costs).decide(probe, SEAT, RED, rp_memory()).actions]
        path = base[0]["move_path"]
        self.assertGreaterEqual(len(path), 3)
        obs = observation([unit(903400, 501)], cities=(A, path[-2]), held=(path[-2],))
        emitted = [dict(base[0], move_path=path[:-1])]
        row = rp.structural(obs, RED, base, emitted, self.router)
        self.assertEqual((row.get("cross_objective", 0), row.get("shortened", 0)), (1, 0))

    def test_planted_off_route_shortening_is_seen(self) -> None:
        emitted = [dict(a) for a in self.base]
        path = emitted[0]["move_path"]
        detour = [h for h in syn.grid_neighbours(self.obs.operators()[0].cur_hex) if h not in path][:1]
        emitted[0] = dict(emitted[0], move_path=detour)
        self.assertEqual(self.check(emitted)["cross_objective"], 1)

    def test_planted_non_prefix_shortening_is_seen(self) -> None:
        emitted = [dict(a) for a in self.base]
        longest = max(range(6), key=lambda i: len(emitted[i]["move_path"]))
        path = emitted[longest]["move_path"]
        self.assertGreaterEqual(len(path), 3)
        emitted[longest] = dict(emitted[longest], move_path=[path[1]])  # ends on the route, skips its first hex
        self.assertEqual(self.check(emitted)["prefix_failures"], 1)

    def test_planted_invented_move_and_unrelated_change_are_seen(self) -> None:
        stranger = {"actor": SEAT, "type": 1, "obj_id": 903000, "move_path": [503]}
        withheld = [a for a in self.base if a.get("obj_id") != 903000]
        self.assertEqual(self.check(withheld)["withheld"], 1)
        extra = observation([unit(903000 + k, h) for k, h in enumerate((503, 507, 303, 703, 100, 900))] +
                            [unit(903100, 305)], cities=(A, B), movable=[903000 + k for k in range(6)])
        row = rp.structural(extra, RED, self.base, self.base + [dict(stranger, obj_id=903100)], self.router)
        self.assertEqual(row["invented"], 1)
        reordered = [SHOT] + [a for a in self.base if a is not SHOT]
        self.assertEqual(self.check(reordered)["unrelated_changed"], 0)  # moves only moved relative to the shot
        changed = [dict(a) for a in self.base[:-1]] + [dict(SHOT, weapon_id=2)]
        self.assertEqual(self.check(changed)["unrelated_changed"], 1)

    def test_late_owner_is_seen(self) -> None:
        late = observation([unit(903200, 503, INFANTRY)], cur_step=2880 - 10)
        base = [dict(a) for a in ShootReservationPolicy(self.costs).decide(late, SEAT, RED, rp_memory()).actions]
        self.assertEqual(rp.structural(late, RED, base, base, self.router)["late_owners"], 1)
        candidate = tb.allocate(late, SEAT, RED, base, self.router)
        self.assertEqual(rp.structural(late, RED, base, candidate.actions, self.router).get("late_owners", 0), 0)

    def test_capacity_check_separates_caused_inherited_and_phantom(self) -> None:
        before = {A: {"physical": 2, "movers": 1, "phantom": 2}, B: {"physical": 5, "movers": 0, "phantom": 0}}
        self.assertEqual(rp.capacity_check(before, {A: [1]}), {"phantom_inclusive": 1, "inherited": 1})
        self.assertEqual(rp.capacity_check(before, {A: [1, 2]}),
                         {"caused": 1, "phantom_inclusive": 1, "inherited": 1})

    def test_permutation_check_catches_an_order_dependent_allocator(self) -> None:
        orders = [list(reversed(range(len(self.base))))]
        self.assertTrue(rp.permutation_invariant(self.obs, SEAT, RED, self.base, self.router, orders))

        def first_come(observation_, seat, faction, actions, router):
            return tb.allocate(observation_, seat, faction, actions, router, key=rp.emission_key)

        self.assertFalse(rp.permutation_invariant(self.obs, SEAT, RED, self.base, self.router, orders,
                                                  allocate=first_come))

    def test_decision_row_covers_every_policy_and_variant(self) -> None:
        staging = StagingAddon(self.costs, ShootReservationPolicy(self.costs))
        row = rp.decision(self.obs, SEAT, RED, self.base, self.base, self.router, staging)
        self.assertEqual(set(row["policies"]), {"t9-v1", "t9-v2"} | set(rp.VARIANTS))
        self.assertEqual(row["policies"]["t9-v1"]["kept"], 6)  # the T9-v1 list given here is baseline itself
        self.assertEqual(row["policies"]["candidate"]["kept"], tb.CAPACITY)
        self.assertGreater(row["policies"]["no-end-of-game-test"]["kept"], 0)

    def test_dominated_movers_and_hold_back_causes(self) -> None:
        far = unit(903300, 100, INFANTRY, move_path=route(100, A, INFANTRY))
        near = [unit(903301 + k, h) for k, h in enumerate((504, 506, 405, 605, 503))]
        obs = observation([far] + near)
        base = [dict(a) for a in ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, rp_memory()).actions]
        allocation = tb.allocate(obs, SEAT, RED, base, self.router)
        self.assertEqual(rp.dominated_movers(allocation), [903300])
        before = rp.commitments(obs, RED, self.router)
        causes = rp.hold_back_causes("candidate", obs, RED, base, allocation.actions, before, self.router)
        self.assertEqual(causes, {"places held by units that can arrive": 2})
        bound = rp.free_flow(self.router, next(u for u in obs.operators() if u.obj_id == 903300),
                             route(100, A, INFANTRY), skip_first=True)
        late = observation([far] + near, cur_step=2880 - bound)
        base = [dict(a) for a in ShootReservationPolicy(self.costs).decide(late, SEAT, RED, rp_memory()).actions]
        before = rp.commitments(late, RED, self.router)
        self.assertEqual(before[A], {"physical": 0, "movers": 0, "phantom": 1})
        allocation = tb.allocate(late, SEAT, RED, base, self.router)
        self.assertEqual(rp.hold_back_causes("candidate", late, RED, base, allocation.actions, before, self.router),
                         {"places held by units that can arrive": 1})
        self.assertEqual(rp.hold_back_causes("t9-v2", late, RED, base, allocation.actions, before, self.router),
                         {"a place is held by a unit that cannot arrive": 1})

    def test_control_counts_see_moves_and_stops_for_moving_units(self) -> None:
        moving = unit(903500, 503, move_path=route(503, A))
        still = unit(903501, 507)
        obs = observation([moving, still], listings={903500: {10: None}, 903501: {1: None}})
        raw = dict(obs.fields)
        clean = rp.control_counts(raw, RED, [], [])
        self.assertEqual(clean["path, speed above 0: unit-decisions"], 1)
        self.assertEqual((clean["path, speed above 0: move listed"], clean["path, speed above 0: stop listed"]), (0, 1))
        self.assertEqual((clean["no path: move listed"], clean["no path: stop listed"]), (1, 0))
        planted = [{"actor": SEAT, "type": 1, "obj_id": 903500, "move_path": [504]},
                   {"actor": SEAT, "type": 10, "obj_id": 903500}]
        seen = rp.control_counts(raw, RED, planted, planted[:1])
        self.assertEqual((seen["emitted: move for a unit with an active path"], seen["emitted: stop"],
                          seen["baseline-v2: move for a unit with an active path"]), (1, 1, 1))

    def test_move_timing_and_remaining_bound(self) -> None:
        path = route(503, A)  # vehicle: 20 steps per hex on the uniform grid
        self.assertEqual(len(path), 2)
        start = {"cur_hex": 503, "move_path": [], "type": 2, "move_state": 0, "basic_speed": 36,
                 "move_to_stop_remain_time": 30, "speed": 0}

        def at(hex_, rest):
            return {903600: dict(start, cur_hex=hex_, move_path=list(rest), move_to_stop_remain_time=0)}

        series = [{903600: start}] + [at(503, path)] * 19 + [at(path[0], path[1:])] * 20 + [at(A, [])] * 5
        order = [(0, {"type": 1, "obj_id": 903600, "move_path": path})]
        timing = rp.move_timing(series, order, self.router)
        self.assertEqual(timing, {"transition: delay-tau: 0": 1, "arrival: exact": 1})
        early = series[:30] + [at(A, [])] * 15
        self.assertEqual(rp.move_timing(early, order, self.router)["arrival: early"], 1)
        bound = rp.remaining_bound_check(series, self.router, every=1)
        self.assertEqual((bound["checked"], bound["arrived sooner than the bound"]), (39, 0))
        planted = series[:21] + [at(A, [])] * 20
        self.assertGreater(rp.remaining_bound_check(planted, self.router, every=1)["arrived sooner than the bound"], 0)

    def test_episodes_and_distribution(self) -> None:
        episodes = rp.Episodes()
        for k, held in enumerate([{1}, {1, 2}, {2}, set(), {1}]):
            episodes.update(k, held)
        self.assertEqual(episodes.finish(4), [1, 2, 2])
        self.assertEqual(rp.distribution([1, 2, 2]), {"n": 3, "max": 2, "median": 2, "sum": 5,
                                                      "counts": {"1": 1, "2": 2}})
        self.assertEqual(rp.distribution([]), {"n": 0})


def rp_memory():
    from miaosuan_agent.decision import Memory
    return Memory()


if __name__ == "__main__":
    unittest.main()
