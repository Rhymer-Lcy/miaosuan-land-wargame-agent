"""The Sprint 23 offline design rules (``evaluation/s23_design.py``): the independent batch check, the projections of
one episode, the roles, the readiness rule and the screen-construction rule. SYNTHETIC data only.

What is pinned here: the batch check accepts the candidate's own batches and refuses every planted defect (a kept carrier
MOVE, a wrong embark target, a changed unrelated action, a unit in two pairs, an over-committed destination, an
admissible pair left unselected, a pair with different destinations, a duplicate action); the projected arrival,
delivery, saving and on-objective gain; saturation at the projected arrival with the pair's own units excluded; roles A,
B, C and D at their boundaries; the carrier's recorded hold exposure (arrival, first move delay, the 150-step window, a
claimant elsewhere); the readiness rule at every threshold and in its order; the screen rule's choices and ceiling; and
the public sanitizer.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from miaosuan_agent.evaluation import s23_design as sd
from miaosuan_agent.experiments import t2_transport_x1 as x1
from tests import test_t2_transport_x1 as tx

SEAT, RED = tx.SEAT, tx.RED
INF, CAR, INF2, CAR2, OTHER = tx.INF, tx.CAR, tx.INF2, tx.CAR2, tx.OTHER
START, DEST, FAR = tx.START, tx.DEST, tx.FAR


def batch(observation, actions, pairs, live=None):
    if live is None:
        live = list(tx.run(observation, actions)[0])
    return sd.batch_problems(observation.fields, SEAT, RED, actions, live, pairs, tx._raw_ff)


class BatchCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.observation, self.actions = tx.scene(pairs=((INF, CAR, START), (INF2, CAR2, 303)),
                                                  dests={INF2: FAR, CAR2: FAR})
        self.live = [dict(a) for a in tx.run(self.observation, self.actions)[0]]
        self.pairs = [(INF, CAR), (INF2, CAR2)]

    def test_the_candidate_batch_passes(self) -> None:
        self.assertEqual(batch(self.observation, self.actions, self.pairs, self.live), [])

    def test_planted_defects_are_caught(self) -> None:
        carrier_kept = self.live + [a for a in self.actions if a.get("obj_id") == CAR]
        wrong_target = [dict(a, target_obj_id=CAR2) if a.get("obj_id") == INF else a for a in self.live]
        unrelated = [dict(a, move_path=[203]) if a.get("obj_id") == OTHER else a for a in self.live]
        duplicate = self.live + [self.live[-1]]
        reordered = list(reversed(self.live))
        for name, live, pairs in (("carrier MOVE kept", carrier_kept, self.pairs),
                                  ("wrong embark target", wrong_target, self.pairs),
                                  ("unrelated action changed", unrelated, self.pairs),
                                  ("duplicate", duplicate, self.pairs), ("order", reordered, self.pairs),
                                  ("a unit in two pairs", self.live, self.pairs + [(INF, CAR2)]),
                                  ("an admissible pair left unselected",
                                   [a for a in self.live if a.get("obj_id") != INF2], [(INF, CAR)])):
            with self.subTest(name):
                self.assertNotEqual(batch(self.observation, self.actions, pairs, live), [])

    def test_unselected_admissible_pair_is_named(self) -> None:
        observation, actions = tx.scene(pairs=((INF, CAR, START), (INF2, CAR2, 303)), dests={INF2: FAR, CAR2: FAR})
        only_first = [actions[0], tx.embark(INF, CAR)] + [a for a in actions if a.get("obj_id") in (INF2, CAR2)]
        self.assertEqual(batch(observation, actions, [(INF, CAR)], only_first),
                         ["an admissible pair with both units free was left unselected"])

    def test_over_committed_destination_and_different_destination(self) -> None:
        tank = [tx.unit(800001, DEST, kind="tank")]
        observation, actions = tx.scene(pairs=((INF, CAR, START), (INF2, CAR2, 303)), extra_units=tank)
        live = [actions[0]] + [tx.embark(INF, CAR), tx.embark(INF2, CAR2)]
        self.assertIn("a destination is over-committed", batch(observation, actions, [(INF, CAR), (INF2, CAR2)], live))
        observation, actions = tx.scene(dests={INF: FAR})
        live = [actions[0], tx.embark(INF, CAR)]
        self.assertIn("pair fails: not the same objective", batch(observation, actions, [(INF, CAR)], live))

    def test_reserved_places_count(self) -> None:
        observation, actions = tx.scene()
        live = [dict(a) for a in tx.run(observation, actions)[0]]
        self.assertEqual(sd.batch_problems(observation.fields, SEAT, RED, actions, live, [(INF, CAR)], tx._raw_ff,
                                           {DEST: 2}), [])
        self.assertIn("a destination is over-committed",
                      sd.batch_problems(observation.fields, SEAT, RED, actions, live, [(INF, CAR)], tx._raw_ff,
                                        {DEST: 3}))


def moment(k: int, step: int, *, flags=None, ground=None, where=None, orders=None) -> sd.Moment:
    return sd.Moment(k=k, cur_step=step, flags=dict(flags or {}), ground=dict(ground or {}), where=dict(where or {}),
                     orders=dict(orders or {}))


def history(n: int = 1200) -> List[sd.Moment]:
    return [moment(i, i) for i in range(n)]


class RunsTest(unittest.TestCase):
    def test_a_run_of_consecutive_selections_is_one_episode(self) -> None:
        a, b = (1, 2), (3, 4)
        selections = [(5, [a]), (6, [a, b]), (7, [a]), (9, [a]), (10, [b])]
        self.assertEqual(sd.group_runs(selections), [(5, a), (6, b), (9, a), (10, b)])
        self.assertEqual(sd.group_runs([]), [])


class ProjectionTest(unittest.TestCase):
    def test_arrival_delivery_saving_and_gain(self) -> None:
        h = history(1000)
        out = sd.project(h, 10, RED, 2880, (INF, CAR), DEST, carrier_ff=100, infantry_ff=900)
        self.assertEqual((out["projected_carrier_arrival"], out["projected_delivery"], out["foot_arrival"]),
                         (10 + 75 + 100, 10 + 225 + 100, 910))
        self.assertEqual((out["projected_saving"], out["on_objective_gain"], out["unable_on_foot"]),
                         (910 - 335, 910 - 335, False))
        late = sd.project(h, 10, RED, 2880, (INF, CAR), DEST, carrier_ff=100, infantry_ff=3000)
        self.assertEqual((late["unable_on_foot"], late["on_objective_gain"]), (True, 2880 - 335))

    def test_saturation_excludes_the_pair_and_uses_three_others(self) -> None:
        arrival = 10 + 75 + 100
        for others, pair_on_dest, expected in ((3, False, True), (2, False, False), (2, True, False),
                                               (3, True, True)):
            h = history(1000)
            h[arrival].ground = {DEST: others + int(pair_on_dest)}
            h[arrival].where = {CAR: (DEST, False)} if pair_on_dest else {}
            out = sd.project(h, 10, RED, 2880, (INF, CAR), DEST, carrier_ff=100, infantry_ff=900)
            self.assertEqual(out["saturated_at_arrival"], expected, (others, pair_on_dest))
            self.assertEqual(out["others_at_projected_arrival"], others)
        h = history(1000)
        for j in range(arrival, arrival + 151):
            h[j].ground = {DEST: 3}
        self.assertTrue(sd.project(h, 10, RED, 2880, (INF, CAR), DEST, 100, 900)["saturated_through_settle_bound"])
        h[arrival + 150].ground = {DEST: 2}
        self.assertFalse(sd.project(h, 10, RED, 2880, (INF, CAR), DEST, 100, 900)["saturated_through_settle_bound"])

    def test_roles(self) -> None:
        delivery = 335
        h = history(1000)
        self.assertEqual(sd.role(h, 10, RED, 2880, DEST, delivery), "A")
        h[delivery].flags = {DEST: RED}
        self.assertEqual(sd.role(h, 10, RED, 2880, DEST, delivery), "B")
        h = history(1000)
        h[5].flags = {DEST: RED}
        self.assertEqual(sd.role(h, 10, RED, 2880, DEST, delivery), "D")  # owned before, not at delivery
        h = history(1000)
        h[delivery].flags = {DEST: 1}
        self.assertEqual(sd.role(h, 10, RED, 2880, DEST, delivery), "A")  # the enemy's: never the side's own
        self.assertEqual(sd.role(h, 10, RED, delivery, DEST, delivery), "C")
        self.assertEqual(sd.role(h, 10, RED, delivery + 1, DEST, delivery), "A")
        self.assertEqual(sd.role(history(300), 10, RED, 2880, DEST, delivery), "D")  # no recorded state that late

    def test_carrier_hold_exposure(self) -> None:
        h = history(1000)
        h[200].where = {CAR: (DEST, False)}
        h[200].flags = {DEST: RED, FAR: -1}
        h[230].orders = {CAR: FAR}
        h[230].flags = {DEST: RED, FAR: -1}
        out = sd.carrier_hold(h, 10, RED, CAR, DEST)
        self.assertEqual((out["carrier_arrived_in_history"], out["first_move_delay"], out["moves_in_expected_hold"],
                          out["claimant_elsewhere"], out["destination_held_at_arrival"],
                          out["projected_suppressed_decisions"]), (True, 30, 1, True, True, 120))
        h[230].flags = {DEST: RED, FAR: RED}
        self.assertFalse(sd.carrier_hold(h, 10, RED, CAR, DEST)["claimant_elsewhere"])
        h[230].orders = {CAR: 303}
        h[230].flags = {DEST: RED, FAR: -1}
        self.assertFalse(sd.carrier_hold(h, 10, RED, CAR, DEST)["claimant_elsewhere"])  # not an objective
        h[230].orders = {}
        h[351].orders = {CAR: FAR}
        h[351].flags = {FAR: -1}
        out = sd.carrier_hold(h, 10, RED, CAR, DEST)
        self.assertEqual((out["moves_in_expected_hold"], out["claimant_elsewhere"]), (0, False))
        h[350].orders = {CAR: FAR}
        h[350].flags = {FAR: -1}
        self.assertEqual(sd.carrier_hold(h, 10, RED, CAR, DEST)["first_move_delay"], 150)
        self.assertFalse(sd.carrier_hold(history(400), 10, RED, CAR, DEST)["carrier_arrived_in_history"])


def ep(population: str, scenario: str, saturated: bool = False, claimant: bool = False) -> Dict[str, Any]:
    return {"population": population, "scenario": scenario, "saturated_at_arrival": saturated,
            "claimant_elsewhere": claimant}


class DispositionTest(unittest.TestCase):
    def test_invalid_comes_first(self) -> None:
        good = [ep("HH", "a"), ep("HH", "b"), ep("HI", "a"), ep("HI", "b")]
        self.assertEqual(sd.disposition(["x"], good)["disposition"], sd.INVALID)
        self.assertEqual(sd.disposition([], good)["disposition"], sd.READY)

    def test_opportunity_minimums_at_their_boundaries(self) -> None:
        cases = (([ep("HH", "a"), ep("HH", "b"), ep("HI", "a")], ["first_divergence_episodes"]),
                 ([ep("HH", "a"), ep("HI", "b"), ep("HI", "a"), ep("HI", "c")], ["acting_opponent_episodes"]),
                 ([ep("HH", "a"), ep("H0", "a"), ep("HI", "a"), ep("HI", "a")], ["scenarios"]),
                 ([ep("HH", "a"), ep("H0", "b"), ep("HI", "a"), ep("HI", "a")], None))
        for episodes, short in cases:
            out = sd.disposition([], episodes)
            if short is None:
                self.assertEqual(out["disposition"], sd.READY)
            else:
                self.assertEqual((out["disposition"], out["below_minimum"]), (sd.NO_OPPORTUNITY, short))

    def test_risk_shares_at_their_boundaries(self) -> None:
        base = [ep("HH", "a"), ep("HH", "b"), ep("HI", "a"), ep("HI", "b")]
        one_sat = [dict(base[0], saturated_at_arrival=True)] + base[1:]
        two_sat = [dict(e, saturated_at_arrival=i < 2) for i, e in enumerate(base)]
        two_claim = [dict(e, claimant_elsewhere=i < 2) for i, e in enumerate(base)]
        three_claim = [dict(e, claimant_elsewhere=i < 3) for i, e in enumerate(base)]
        self.assertEqual(sd.disposition([], one_sat)["disposition"], sd.READY)
        self.assertEqual(sd.disposition([], two_sat)["above_maximum"], ["saturated_share"])
        self.assertEqual(sd.disposition([], two_claim)["disposition"], sd.READY)
        self.assertEqual(sd.disposition([], three_claim)["above_maximum"], ["claimant_share"])
        self.assertEqual(sd.disposition([], three_claim)["claimant_share"], "3/4")

    def test_shares_are_published_unreduced_and_pass_the_sanitizer_with_small_private_ids(self) -> None:
        """Amendment A1: a reduced share ("0", "1") equals a small private unit id as a word of a string."""
        base = [ep("HH", "a"), ep("HH", "b"), ep("HI", "a"), ep("HI", "b")]
        for flags, expected in (((False,) * 4, "0/4"), ((True,) * 4, "4/4"), ((True, True, False, False), "2/4")):
            episodes = [dict(e, claimant_elsewhere=f) for e, f in zip(base, flags)]
            out = sd.disposition([], episodes)
            self.assertEqual((out["claimant_share"], out["saturated_share"]), (expected, "0/4"))
            self.assertEqual(sd.public_problems(out, range(50)), [])
        self.assertTrue(sd.public_problems({"share": "0"}, range(50)))

    def test_no_episode_is_no_opportunity(self) -> None:
        self.assertEqual(sd.disposition([], [])["disposition"], sd.NO_OPPORTUNITY)


class ScreenTest(unittest.TestCase):
    def batches(self, hi=1, hh=1) -> List[Dict[str, Any]]:
        return [{"population": "HI", "game": "g2", "scenario": "s1", "condition": "C3", "side": "blue",
                 "batch_size": hi},
                {"population": "HI", "game": "g1", "scenario": "s1", "condition": "C2", "side": "red",
                 "batch_size": hi},
                {"population": "HH", "game": "h1", "scenario": "s9", "condition": "H1", "side": "blue",
                 "batch_size": hh}]

    def test_phase_m_only_with_an_inert_multi_pair_batch(self) -> None:
        episodes = [ep("HH", "s9"), ep("H0", "s3"), ep("H0", "s3")]
        self.assertIsNone(sd.screen(episodes, self.batches(hi=1))["phase_m"])
        out = sd.screen(episodes, self.batches(hi=2))
        self.assertEqual((out["phase_m"]["source"], out["phase_m"]["condition"]), ("g1", "C2"))
        self.assertEqual(out["phase_h"]["scenario"], "s3")
        self.assertEqual(out["sessions"], 3)

    def test_phase_h_ties_prefer_hh_then_scenario_id(self) -> None:
        self.assertEqual(sd.screen([ep("H0", "s3"), ep("HH", "s9")], self.batches())["phase_h"]["scenario"], "s9")
        self.assertEqual(sd.screen([ep("H0", "s3"), ep("H0", "s1")], self.batches())["phase_h"]["scenario"], "s1")
        self.assertIsNone(sd.screen([ep("HI", "s1")], self.batches()))

    def test_ceiling(self) -> None:
        self.assertLessEqual(sd.screen([ep("HH", "s9")], self.batches(hi=3))["sessions"], sd.SCREEN_SESSION_CEILING)


class PublicTest(unittest.TestCase):
    def test_sanitizer(self) -> None:
        self.assertEqual(sd.public_problems({"count": 4321, "label": "80-point objective A"}, [4321, 505]), [])
        self.assertTrue(sd.public_problems({"path": 1}, []))
        self.assertTrue(sd.public_problems({"note": "unit 4321 moved"}, [4321]))
        self.assertTrue(sd.public_problems({"4321": 1}, [4321]))

    def test_rules_digest_is_stable(self) -> None:
        self.assertEqual(sd.rules_digest(), sd.rules_digest())
        self.assertEqual(len(sd.rules_digest()), 64)


if __name__ == "__main__":
    unittest.main()
