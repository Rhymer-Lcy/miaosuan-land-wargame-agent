"""OFFLINE-ONLY design candidate ``t9-batch-capacity-v3`` (``experiments/t9_batch.py``). SYNTHETIC observations.

Geometry is never typed by hand: every free-flow time a test relies on is computed with the project's router on the
10 x 10 synthetic grid (uniform cost 1 per hex) and asserted as a precondition. Vehicles have ``basic_speed`` 36 (20
steps per hex), infantry 5 (144 steps per hex). The game clock is set to ``cur_step`` 100 of ``max_step`` 2880 unless a
test needs the end of the game.
"""

from __future__ import annotations

import itertools
import json
import random
import unittest
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import Memory, digest, gate
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_batch as tb
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from tests.fixtures import synthetic as syn

SEAT, RED = syn.RED_SEAT, 0
A, B = 505, 909
VEHICLE, INFANTRY = (2, 36), (1, 5)
ROUTER = Router(MoveCosts.from_raw(syn.cost_data()))


def route(start: int, goal: int, kind=VEHICLE) -> List[int]:
    """The router's shortest path from ``start`` to ``goal`` for ``kind`` (never typed by hand)."""
    from miaosuan_agent.decision.routing import move_mode
    return list(ROUTER.shortest_paths(start, move_mode(kind[0], 0)).path_to(goal))


def unit(obj_id: int, hex_: int, kind=VEHICLE, move_path: Sequence[int] = (), color: int = RED,
         **extra: Any) -> Dict[str, Any]:
    record = syn.unit(obj_id, color, hex_, unit_type=kind[0], move_path=move_path)
    record.update({"basic_speed": kind[1], "speed": 0 if not move_path else 1, "stop": 0 if move_path else 1})
    record.update(extra)
    return record


def observation(units: Sequence[Dict[str, Any]], cities: Sequence[int] = (A,), *, movable: Optional[Sequence[int]] = None,
                listings: Optional[Dict[int, Any]] = None, cur_step: int = 100, max_step: Optional[int] = 2880,
                stage: int = 2, held: Sequence[int] = ()) -> Observation:
    own = [u["obj_id"] for u in units if u["color"] == RED]
    if listings is None:
        ids = movable if movable is not None else [u["obj_id"] for u in units if not u["move_path"]]
        listings = {i: {1: None} for i in ids}
    raw = syn.build_observation(units=units, valid_actions=listings, stage=stage, cur_step=cur_step,
                                seats={SEAT: syn.seat_record(SEAT, RED, own, True)},
                                cities=[syn.city(c, flag=RED if c in held else -1) for c in cities])
    if max_step is None:
        del raw["time"]["max_step"]
    else:
        raw["time"]["max_step"] = max_step
    return Observation.from_raw(raw, Origin.ENGINE)


class BatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())
        self.router = Router(self.costs)
        self.policy = tb.BatchPolicy(self.costs)

    # -- helpers -------------------------------------------------------------------------------------------------
    def baseline(self, obs: Observation):
        return ShootReservationPolicy(self.costs).decide(obs, SEAT, RED, Memory())

    def decide(self, obs: Observation):
        return self.policy.decide(obs, SEAT, RED, ea.AddonMemory())

    def allocate(self, obs: Observation, actions=None, **options):
        actions = self.baseline(obs).actions if actions is None else actions
        return tb.allocate(obs, SEAT, RED, actions, self.router, **options)

    @staticmethod
    def moves(actions) -> Dict[int, List[int]]:
        return {a["obj_id"]: list(a["move_path"]) for a in actions if a["type"] == 1}

    def free_flow(self, obs: Observation, obj_id: int, path: Sequence[int]) -> int:
        u = next(x for x in obs.operators() if x.obj_id == obj_id)
        times, _ = tb.path_times(self.router, u.unit_type, u.move_state, u.fields["basic_speed"], u.cur_hex, path)
        return sum(times)

    def selected_after(self, obs: Observation, order: Sequence[int]):
        base = list(self.baseline(obs).actions)
        result = self.allocate(obs, [base[i] for i in order])
        return frozenset(result.selected), {k: tuple(v) for k, v in result.staged.items()}, dict(result.withheld)

    def six_claimants(self):
        """Two near vehicles, two far vehicles, two infantry: all six of baseline-v2's moves go to A."""
        units = [unit(900901, 503), unit(900902, 504), unit(900903, 100), unit(900904, 900),
                 unit(900905, 405, INFANTRY), unit(900906, 606, INFANTRY)]
        return observation(units)

    # -- ranking -------------------------------------------------------------------------------------------------
    def test_six_claimants_take_four_places_by_free_flow_time_in_every_permutation(self) -> None:
        obs = self.six_claimants()
        base = self.baseline(obs)
        moves = self.moves(base.actions)
        self.assertEqual({p[-1] for p in moves.values()}, {A})
        times = {i: self.free_flow(obs, i, p) for i, p in moves.items()}
        best = frozenset(sorted(times, key=lambda i: (times[i], i))[:tb.CAPACITY])
        self.assertLess(max(times[i] for i in best), min(t for i, t in times.items() if i not in best))
        outcomes = {self.selected_after(obs, order)[0] for order in itertools.permutations(range(len(base.actions)))}
        self.assertEqual(outcomes, {best})

    def test_four_slow_moves_emitted_before_two_near_claimants(self) -> None:
        obs = self.six_claimants()
        base = list(self.baseline(obs).actions)
        times = {a["obj_id"]: self.free_flow(obs, a["obj_id"], a["move_path"]) for a in base}
        slow_first = sorted(range(len(base)), key=lambda i: -times[base[i]["obj_id"]])
        near = sorted(times, key=times.get)[:2]
        for order in (slow_first, list(reversed(slow_first))):
            selected, _, _ = self.selected_after(obs, order)
            self.assertTrue(set(near) <= selected)
            self.assertEqual(len(selected), tb.CAPACITY)
        self.assertEqual(self.selected_after(obs, slow_first), self.selected_after(obs, list(reversed(slow_first))))

    def test_infantry_does_not_outrank_a_vehicle_at_equal_route_cost(self) -> None:
        units = [unit(900911, 503, INFANTRY), unit(900912, 507)] + [unit(900913 + k, h) for k, h in
                                                                     enumerate((404, 405, 604))]
        obs = observation(units)
        moves = self.moves(self.baseline(obs).actions)
        self.assertEqual(len(moves[900911]), len(moves[900912]))
        result = self.allocate(obs)
        self.assertNotIn(900911, result.selected)
        self.assertIn(900912, result.selected)

    def test_equal_free_flow_ties_break_by_unit_id_in_every_order(self) -> None:
        units = [unit(900920 + k, h) for k, h in enumerate((503, 507, 303, 703, 307, 707))]
        obs = observation(units)
        moves = self.moves(self.baseline(obs).actions)
        times = {i: self.free_flow(obs, i, p) for i, p in moves.items()}
        ranked = sorted(times.values())
        self.assertEqual(ranked[tb.CAPACITY - 1], ranked[tb.CAPACITY], times)  # the tie straddles the cut
        expected = frozenset(sorted(times, key=lambda i: (times[i], i))[:tb.CAPACITY])
        self.assertNotEqual(expected, frozenset(sorted(times, key=lambda i: (times[i], -i))[:tb.CAPACITY]))
        rng = random.Random(11)
        orders = [list(range(6)), list(reversed(range(6)))] + [rng.sample(range(6), 6) for _ in range(8)]
        self.assertEqual({self.selected_after(obs, o)[0] for o in orders}, {expected})
        staged = {repr(self.selected_after(obs, o)[1:]) for o in orders}
        self.assertEqual(len(staged), 1)

    # -- incumbents ----------------------------------------------------------------------------------------------
    def test_physical_incumbents_reduce_free_places(self) -> None:
        for present in range(1, tb.CAPACITY + 1):
            standing = [unit(900930 + k, A) for k in range(present)]
            obs = observation(standing + [unit(900940 + k, h) for k, h in enumerate((503, 507, 303, 703))],
                              movable=[900940 + k for k in range(4)])
            result = self.allocate(obs)
            self.assertEqual(result.objectives[A]["physical"], present)
            self.assertEqual(len(result.selected), tb.CAPACITY - present)
            self.assertEqual(len(result.staged) + len(result.withheld), present)

    def test_active_movers_count_are_retained_and_never_reordered(self) -> None:
        movers = [unit(900950 + k, h, move_path=route(h, A)) for k, h in enumerate((303, 703))]
        claimants = [unit(900960 + k, h) for k, h in enumerate((504, 506, 405, 605))]
        obs = observation(movers + claimants)
        result = self.allocate(obs)
        self.assertEqual(result.objectives[A]["movers"], 2)
        self.assertEqual(len(result.selected), 2)
        emitted = {a["obj_id"] for a in result.actions}
        self.assertFalse(emitted & {900950, 900951})  # nothing is issued to a unit with an active path

    def test_a_dominated_mover_is_retained_not_displaced(self) -> None:
        far = unit(900970, 100, INFANTRY, move_path=route(100, A, INFANTRY))
        obs = observation([far] + [unit(900971 + k, h) for k, h in enumerate((504, 506, 405, 605))])
        result = self.allocate(obs)
        self.assertEqual(result.objectives[A]["movers"], 1)
        self.assertEqual(len(result.selected), 3)
        self.assertGreater(result.objectives[A]["mover_bounds"][900970],
                           min(c.free_flow for c in result.claimants.values() if c.obj_id not in result.selected))
        self.assertNotIn(900970, {a["obj_id"] for a in result.actions})

    def test_a_mover_that_cannot_arrive_before_the_end_holds_no_place(self) -> None:
        path = route(100, A, INFANTRY)
        far = [unit(900980 + k, 100, INFANTRY, move_path=path) for k in range(tb.CAPACITY)]
        near = [unit(900990 + k, h) for k, h in enumerate((504, 506))]
        bound = 144 * (len(path) - 1)
        late = observation(far + near, cur_step=2880 - bound)
        result = self.allocate(late)
        self.assertEqual((result.objectives[A]["movers"], result.objectives[A]["phantom"]), (0, tb.CAPACITY))
        self.assertEqual(set(result.selected), {900990, 900991})
        early = observation(far + near, cur_step=2880 - bound - 1)
        result = self.allocate(early)
        self.assertEqual((result.objectives[A]["movers"], result.objectives[A]["phantom"]), (tb.CAPACITY, 0))
        self.assertEqual(result.selected, {})

    def test_a_claimant_that_cannot_arrive_before_the_end_is_never_selected(self) -> None:
        obs = observation([unit(901001, 503, INFANTRY)], cur_step=2880 - 100)
        moves = self.moves(self.baseline(obs).actions)
        self.assertGreaterEqual(self.free_flow(obs, 901001, moves[901001]), 100)
        result = self.allocate(obs)
        self.assertEqual(result.selected, {})
        self.assertEqual(result.claimants[901001].status, "cannot arrive before the end")

    def test_end_of_game_boundary_is_exact(self) -> None:
        probe = observation([unit(901005, 503, INFANTRY)])
        free_flow = self.free_flow(probe, 901005, self.moves(self.baseline(probe).actions)[901005])
        at_end = self.allocate(observation([unit(901005, 503, INFANTRY)], cur_step=2880 - free_flow))
        self.assertEqual(at_end.claimants[901005].status, "cannot arrive before the end")
        self.assertEqual(at_end.selected, {})
        before_end = self.allocate(observation([unit(901005, 503, INFANTRY)], cur_step=2880 - free_flow - 1))
        self.assertEqual(set(before_end.selected), {901005})

    def test_staging_never_ends_on_another_objective_on_the_route(self) -> None:
        probe = observation([unit(901006, 501)])
        path = self.moves(self.baseline(probe).actions)[901006]
        self.assertGreaterEqual(len(path), 3)
        other = path[-2]  # a held objective right in front of A on every claimant's route
        units = [unit(901200 + k, 501) for k in range(6)]
        obs = observation(units, cities=(A, other), held=(other,))
        base = self.moves(self.baseline(obs).actions)
        self.assertTrue(all(p == path for p in base.values()))
        result = self.allocate(obs)
        self.assertEqual(len(result.staged), 2)
        self.assertTrue(all(p[-1] != other for p in result.staged.values()))
        self.assertTrue(all(p == tuple(path[:len(p)]) for p in result.staged.values()))

    def test_staged_unit_returning_later_competes_again_from_its_new_position(self) -> None:
        first = observation([unit(901010 + k, h) for k, h in enumerate((503, 507, 303, 703, 100))])
        result = self.allocate(first)
        (staged_id, staged_path), = result.staged.items()
        self.assertNotIn(staged_path[-1], (A,))
        returning = [unit(901010 + k, h, move_path=route(h, A)) for k, h in enumerate((503, 507, 303, 703, 100))
                     if 901010 + k != staged_id][:2]
        later = observation(returning + [unit(staged_id, staged_path[-1])], movable=[staged_id])
        again = self.allocate(later)
        self.assertEqual(set(again.selected), {staged_id})

    def test_objective_held_between_decisions_releases_waiting_units(self) -> None:
        units = [unit(901020 + k, h) for k, h in enumerate((503, 507, 303, 703, 100))]
        before = self.allocate(observation(units, cities=(A, B)))
        self.assertTrue(before.staged or before.withheld)
        after_obs = observation(units, cities=(A, B), held=(A,))
        moves = self.moves(self.baseline(after_obs).actions)
        self.assertEqual({p[-1] for p in moves.values()}, {B})
        after = self.allocate(after_obs)
        self.assertEqual(len(after.selected), tb.CAPACITY)
        self.assertTrue(all(c.objective == B for c in after.claimants.values()))

    def test_every_objective_already_held_leaves_baseline_unchanged(self) -> None:
        obs = observation([unit(901030 + k, h) for k, h in enumerate((503, 507))], cities=(A, B), held=(A, B))
        decision = self.decide(obs)
        self.assertEqual([dict(a) for a in decision.actions], [dict(a) for a in self.baseline(obs).actions])
        self.assertEqual(decision.trace.changes, ())

    def test_every_target_objective_full_stages_or_withholds_without_over_capacity(self) -> None:
        committed = [unit(901040 + k, h, move_path=route(h, A)) for k, h in enumerate((504, 506, 404, 604))]
        claimants = [unit(901050 + k, h) for k, h in enumerate((503, 507, 303, 703, 100, 900))]
        result = self.allocate(observation(committed + claimants))
        self.assertEqual(result.selected, {})
        self.assertFalse(any(p[-1] == A for p in self.moves(result.actions).values()))
        self.assertEqual(len(result.staged) + len(result.withheld), len(claimants))

    # -- staging -------------------------------------------------------------------------------------------------
    def test_staging_is_a_same_route_prefix_and_no_staging_hex_gets_a_fourth_unit(self) -> None:
        units = [unit(901060 + k, 100) for k in range(9)]
        obs = observation(units)
        base = self.moves(self.baseline(obs).actions)
        result = self.allocate(obs)
        ends = [p[-1] for p in result.staged.values()]
        for obj_id, path in result.staged.items():
            self.assertEqual(list(path), base[obj_id][:len(path)])
            self.assertLess(len(path), len(base[obj_id]))
            self.assertNotEqual(path[-1], A)
        self.assertTrue(all(ends.count(h) < tb.CAPACITY for h in ends))
        self.assertLessEqual(max(ends.count(h) for h in ends), tb.STAGE_CAP)

    def test_staged_move_rejected_by_the_gate_is_withheld(self) -> None:
        obs = observation([unit(901070 + k, h) for k, h in enumerate((503, 507, 303, 703, 100))])
        real = gate.check

        def reject_staging(proposals, context, router):
            result = real(proposals, context, router)
            staged = [p for p in proposals if p.get("type") == 1 and p["move_path"][-1] != A]
            return gate.GateResult(tuple(p for p in result.accepted if p not in staged),
                                   tuple(result.rejected) + tuple(gate.Rejection(1, p["obj_id"], "planted")
                                                                  for p in staged))

        with mock.patch.object(tb.gate, "check", side_effect=reject_staging):
            result = self.allocate(obs)
        self.assertEqual(result.staged, {})
        self.assertEqual(len(result.selected), tb.CAPACITY)
        self.assertEqual(sum(p[-1] == A for p in self.moves(result.actions).values()), tb.CAPACITY)
        self.assertTrue(all(p[-1] == A for p in self.moves(result.actions).values()))
        self.assertIn("staged move rejected by the gate", result.withheld.values())

    # -- scope and failure ---------------------------------------------------------------------------------------
    def test_unrelated_actions_and_their_order_are_unchanged(self) -> None:
        obs = self.six_claimants()
        shot = {"actor": SEAT, "type": 2, "obj_id": 999999, "target_obj_id": 1, "weapon_id": 1}
        base = list(self.baseline(obs).actions)
        mixed = base[:3] + [shot] + base[3:]
        result = self.allocate(obs, mixed)
        self.assertIn(shot, [dict(a) for a in result.actions])
        others = [dict(a) for a in result.actions if a.get("type") != 1]
        self.assertEqual(others, [shot])
        kept = [a["obj_id"] for a in result.actions if a.get("type") == 1]
        self.assertEqual(kept, [a["obj_id"] for a in base if a["obj_id"] in kept])

    def test_non_play_stage_is_unchanged(self) -> None:
        obs = observation([unit(901080, 503)], stage=1)
        self.assertEqual([dict(a) for a in self.decide(obs).actions], [dict(a) for a in self.baseline(obs).actions])

    def test_unavailable_suppressed_transitioning_destroyed_units_get_nothing_invented(self) -> None:
        unavailable = unit(901091, 503)
        suppressed = unit(901092, 507, keep=1, speed=0)
        transitioning = unit(901093, 303, move_to_stop_remain_time=40)
        obs = observation([unavailable, suppressed, transitioning], listings={})
        decision = self.decide(obs)
        self.assertEqual(decision.actions, self.baseline(obs).actions)
        self.assertEqual(decision.actions, ())

    def test_missing_speed_is_never_selected_and_missing_clock_counts_conservatively(self) -> None:
        nospeed = unit(901101, 503)
        del nospeed["basic_speed"]
        result = self.allocate(observation([nospeed, unit(901102, 507)]))
        self.assertEqual(set(result.selected), {901102})
        self.assertEqual(result.claimants[901101].status, "free-flow time unreadable")
        path = route(100, A, INFANTRY)
        far = [unit(901110 + k, 100, INFANTRY, move_path=path) for k in range(tb.CAPACITY)]
        noclock = self.allocate(observation(far + [unit(901120, 504)], cur_step=2870, max_step=None))
        self.assertEqual((noclock.objectives[A]["movers"], noclock.objectives[A]["phantom"]), (tb.CAPACITY, 0))
        self.assertEqual(noclock.selected, {})

    def test_internal_failure_withholds_every_ground_objective_move_and_keeps_the_rest(self) -> None:
        obs = self.six_claimants()
        shot = {"actor": SEAT, "type": 2, "obj_id": 999999, "target_obj_id": 1, "weapon_id": 1}
        with mock.patch.object(tb, "path_times", side_effect=RuntimeError("planted")):
            result = self.allocate(obs, list(self.baseline(obs).actions) + [shot])
        self.assertEqual([dict(a) for a in result.actions], [shot])
        self.assertIn("planted", result.error)
        with mock.patch.object(tb, "path_times", side_effect=RuntimeError("planted")):
            decision = self.decide(obs)
        self.assertEqual(decision.actions, ())
        self.assertIn("error", [json.loads(c)["kind"] for c in decision.trace.changes])

    def test_seven_objective_shape_is_deterministic_bounded_and_order_free(self) -> None:
        cities = (101, 105, 108, 404, 707, 902, 908)
        starts = [100 + i for i in range(10)] + [900 + i for i in range(10)] + [500 + i for i in range(10)]
        units = [unit(902000 + i, h) for i, h in enumerate(starts) if h not in cities]
        obs = observation(units, cities=cities)
        base = list(self.baseline(obs).actions)
        result = self.allocate(obs, base)
        counts = {c: sum(p[-1] == c for p in self.moves(result.actions).values()) for c in cities}
        self.assertTrue(all(v <= tb.CAPACITY for v in counts.values()), counts)
        self.assertGreater(len(result.staged) + len(result.withheld), 0)
        rng = random.Random(7)
        for _ in range(5):
            order = rng.sample(range(len(base)), len(base))
            other = self.allocate(obs, [base[i] for i in order])
            self.assertEqual((other.selected, other.staged, other.withheld),
                             (result.selected, result.staged, result.withheld))

    def test_agent_replay_reproduces_the_trace(self) -> None:
        agent = tb.BatchAgent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        raw = dict(self.six_claimants().fields)
        memory = agent.memory
        agent.step(raw)
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        kinds = {json.loads(change)["kind"] for change in agent.last_trace.changes}
        self.assertTrue(kinds and kinds <= {"stage", "withhold"}, kinds)

    def test_candidate_occurs_only_in_the_approved_sprint12_stage_cards(self) -> None:
        """Owner-approved whitelist (Sprint 12 registration, 2026-10-05): v3 may appear in a run card only as one of
        the four Sprint 12 stage cards, each binding exactly the frozen v3 source digest; no historical card or
        builder may acquire it, and any other manifest that names it fails. A changed v3 source is a new identity
        that needs new owner approval, so its digest is pinned here too."""
        import importlib.util
        from pathlib import Path
        from miaosuan_agent.evaluation import exploratory as xp
        from miaosuan_agent.evaluation import s12_screen as sc
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("brc", root / "scripts" / "build_run_card.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertNotIn(tb.CANDIDATE_ID, module.CANDIDATES)
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "build_t9_diagnostic_card.py"):
            self.assertNotIn("t9_batch", (root / "scripts" / name).read_text(encoding="utf-8"), name)
        frozen = "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8"
        self.assertEqual((tb.CANDIDATE_ID, sc.V3_ID, sc.V3_DIGEST), ("t9-batch-capacity-v3", tb.CANDIDATE_ID, frozen))
        from miaosuan_agent.evaluation import runtime_remediation as rr
        from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files
        rr_sources = rr.candidate_sources() + ("experiments/shoot_reservation.py", "experiments/exploratory_addon.py",
                                               "experiments/t9_batch.py")
        self.assertEqual(digest_of_files(policy_source_files(sources=rr_sources)), frozen)
        approved = set(sc.CARD_IDS.values())
        checked = 0
        for path in sorted((root / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if tb.CANDIDATE_ID not in text and frozen not in text:
                continue
            rel = path.relative_to(root).as_posix()
            data = json.loads(text)
            is_card = isinstance(data, dict) and (xp.is_card(data) or path.name == "manifest.json")
            if not is_card:
                self.assertTrue(rel.startswith(("evaluation/s11-batch-allocator/", "evaluation/s12-batch-allocator-draft/",
                                                "evaluation/s12-v3-")), rel)
                self.assertFalse(isinstance(data, dict) and data.get("executable"), rel)
                continue
            checked += 1
            self.assertIn(path.parent.name, approved, rel)
            self.assertEqual(rel, f"evaluation/{path.parent.name}/manifest.json")
            self.assertEqual((data.get("card_id"), (data.get("screen") or {}).get("id")),
                             (path.parent.name, sc.SCREEN_ID), rel)
            source = data["policies"][tb.CANDIDATE_ID]["policy_source"]
            self.assertEqual(source["sha256"], frozen, rel)
            self.assertIn("experiments/t9_batch.py", source["files"], rel)
        self.assertGreaterEqual(checked, 1, "the approved P1 stage card exists and is checked")


if __name__ == "__main__":
    unittest.main()
