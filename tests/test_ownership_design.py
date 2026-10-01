"""The analysis-only model of the target-ownership design study (``evaluation/ownership_design.py``). SYNTHETIC.

The shoot graph and its S1/S2/S3 components, the designed ownership rule and the key that decides a change, the
single-proposal gate precheck, the S1 oracle on the frozen baseline-v2 (simple, three shooters, a fallback to
occupation, a failed precheck) and the structural fingerprint (deterministic, free of ids, sensitive to structure).
"""

from __future__ import annotations

import unittest
from unittest import mock

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import Memory
from miaosuan_agent.decision import gate
from miaosuan_agent.evaluation import ownership_design as od
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_shoot_reservation import ENEMY_C, SEAT, situation

MEMORY = Memory(deployment_sent=True)
CONFIG = "999 C9"


def decide(raw):
    return ShootReservationPolicy(ds.costs()).decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED, MEMORY)


def graph_of(raw):
    return od.shoot_graph(raw, SEAT, ds.RED)


def oracle(raw, component, graph):
    return od.s1_oracle(raw, SEAT, ds.RED, decide(raw), component, graph, lambda: ShootReservationPolicy(ds.costs()),
                        MEMORY)


def shoot(target, level, weapon=ds.GUN):
    return ds.shoot(target, weapon, level)


class GraphTest(unittest.TestCase):
    def test_kinds(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 5)]},
                         ds.UNIT_C: {2: [shoot(ds.ENEMY_B, 2), shoot(ENEMY_C, 1)]}, ds.UNIT_D: {1: None}})
        order, graph = graph_of(raw)
        self.assertEqual(order, [ds.UNIT_A, ds.UNIT_B, ds.UNIT_C, ds.UNIT_D])
        comps = od.components(order, graph)
        self.assertEqual([(c.shooters, c.targets, c.edges, c.kind) for c in comps],
                         [((ds.UNIT_A, ds.UNIT_B), (ds.ENEMY_A,), 2, "S1"),
                          ((ds.UNIT_C,), (ds.ENEMY_B, ENEMY_C), 2, "S3")])

    def test_a_second_target_of_one_shooter_makes_the_component_coupled(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3), shoot(ds.ENEMY_B, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 5)]}})
        [comp] = od.components(*graph_of(raw))
        self.assertEqual((comp.kind, comp.targets, comp.edges), ("S2", (ds.ENEMY_A, ds.ENEMY_B), 3))
        with self.assertRaises(ValueError):
            od.owners(comp, graph_of(raw)[1])

    def test_edges_carry_the_best_candidate_on_the_target(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 2, ds.MISSILE), shoot(ds.ENEMY_A, 4, ds.MISSILE),
                                         shoot(ds.ENEMY_A, 4, ds.GUN), shoot(ds.ENEMY_B, 0)]}})
        _, graph = graph_of(raw)
        self.assertEqual(graph, {ds.UNIT_A: {ds.ENEMY_A: (4, ds.GUN)}})

    def test_processing_order_is_the_baselines(self) -> None:
        valid = {u: {2: [shoot(ds.ENEMY_A, 3)]} for u in (ds.UNIT_C, ds.UNIT_A, ds.UNIT_B)}
        raw = situation(valid, units=[ds.UNIT_C, ds.UNIT_A, ds.UNIT_B])
        order, graph = graph_of(raw)
        self.assertEqual(od.components(order, graph)[0].shooters, (ds.UNIT_A, ds.UNIT_B, ds.UNIT_C))


class OwnershipTest(unittest.TestCase):
    def owners(self, valid):
        order, graph = graph_of(situation(valid))
        return od.owners(od.components(order, graph)[0], graph)

    def test_higher_attack_level(self) -> None:
        own = self.owners({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 5)]}})
        self.assertEqual((own["baseline_owner"], own["designated_owner"], own["key"]), (ds.UNIT_A, ds.UNIT_B,
                                                                                       "higher attack level"))
        self.assertTrue(own["lower_attack_level_owner"])
        self.assertEqual(own["levels"], [3, 5])

    def test_weapon_tie_break(self) -> None:
        own = self.owners({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3, ds.MISSILE)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3, ds.GUN)]}})
        self.assertEqual((own["designated_owner"], own["key"], own["lower_attack_level_owner"]),
                         (ds.UNIT_B, "weapon tie-break", False))

    def test_full_tie_keeps_the_first(self) -> None:
        own = self.owners({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3)]},
                           ds.UNIT_C: {2: [shoot(ds.ENEMY_A, 2)]}})
        self.assertEqual((own["designated_owner"], own["key"]), (ds.UNIT_A, "unchanged"))

    def test_the_first_highest_wins_among_later_equals(self) -> None:
        own = self.owners({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]},
                           ds.UNIT_C: {2: [shoot(ds.ENEMY_A, 4)]}})
        self.assertEqual(own["designated_owner"], ds.UNIT_B)

    def test_gate_precheck(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 3)]}})
        self.assertTrue(od.gate_precheck(raw, SEAT, ds.RED, ds.UNIT_A, ds.ENEMY_A))
        with mock.patch.object(gate, "check", return_value=gate.GateResult(accepted=(), rejected=())):
            self.assertFalse(od.gate_precheck(raw, SEAT, ds.RED, ds.UNIT_A, ds.ENEMY_A))


class OracleTest(unittest.TestCase):
    def run_oracle(self, raw):
        order, graph = graph_of(raw)
        return oracle(raw, od.components(order, graph)[0], graph)

    def test_unchanged_owner(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 5)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3)]}})
        self.assertEqual(self.run_oracle(raw), {"key": "unchanged", "levels": [5, 3], "baseline_owner_shot_emitted": True,
                                                "owner_changed": False})

    def test_simple_swap(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4, ds.MISSILE)]}})
        result = self.run_oracle(raw)
        self.assertEqual(result, {"key": "higher attack level", "levels": [1, 4], "baseline_owner_shot_emitted": True,
                                  "owner_changed": True, "designated_owner_shoots_target": True, "simple": True,
                                  "changed_units": 2, "level_gain": 3, "former_owner_then": "none",
                                  "designated_owner_before": "none", "shot_delta": 0, "non_shoot_changes": 0,
                                  "earlier_non_owners": 1, "later_non_owners": 0})

    def test_three_shooters(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 1)]},
                         ds.UNIT_C: {2: [shoot(ds.ENEMY_A, 5)]}, ds.UNIT_D: {2: [shoot(ds.ENEMY_A, 2)]}})
        result = self.run_oracle(raw)
        self.assertTrue(result["simple"] and result["designated_owner_shoots_target"])
        self.assertEqual((result["changed_units"], result["earlier_non_owners"], result["later_non_owners"]), (2, 2, 1))

    def test_former_owner_falls_back_to_occupation(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)], 5: None}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3)]}},
                        cities=[syn.city(505)], hexes={ds.UNIT_A: 505})
        result = self.run_oracle(raw)
        self.assertEqual((result["former_owner_then"], result["non_shoot_changes"], result["shot_delta"]), ("occupy", 1, 0))
        self.assertTrue(result["simple"])

    def test_a_third_unit_makes_the_swap_not_simple(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)], 5: None}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 3)]},
                         ds.UNIT_C: {5: None}}, cities=[syn.city(505)], hexes={ds.UNIT_A: 505, ds.UNIT_C: 505})
        result = self.run_oracle(raw)
        self.assertTrue(result["owner_changed"] and result["designated_owner_shoots_target"])
        self.assertFalse(result["simple"])
        self.assertEqual((result["changed_units"], result["non_shoot_changes"], result["former_owner_then"]),
                         (3, 2, "occupy"))

    def test_shot_delta_counts_every_changed_shot(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        richer = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]},
                            ds.UNIT_C: {2: [shoot(ds.ENEMY_B, 2)]}})
        order, graph = graph_of(raw)
        result = od.s1_oracle(raw, SEAT, ds.RED, decide(richer), od.components(order, graph)[0], graph,
                              lambda: ShootReservationPolicy(ds.costs()), MEMORY)
        self.assertEqual((result["shot_delta"], result["simple"], result["changed_units"]), (-1, False, 3))

    def test_a_failed_precheck_keeps_the_baseline(self) -> None:
        raw = situation({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        order, graph = graph_of(raw)
        decision = decide(raw)
        with mock.patch.object(od, "gate_precheck", return_value=False):
            result = od.s1_oracle(raw, SEAT, ds.RED, decision, od.components(order, graph)[0], graph,
                                  lambda: ShootReservationPolicy(ds.costs()), MEMORY)
        self.assertEqual((result["owner_changed"], result["fallback"]),
                         (False, "designated owner failed the gate precheck"))


class FingerprintTest(unittest.TestCase):
    def fp(self, valid, config=CONFIG, **kwargs):
        raw = situation(valid, **kwargs)
        order, graph = graph_of(raw)
        return od.fingerprint(config, raw, SEAT, ds.RED, od.components(order, graph)[0], graph)

    def test_structure_not_ids(self) -> None:
        base = self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        self.assertRegex(base, r"^[0-9a-f]{16}$")
        self.assertEqual(base, self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}}))
        self.assertEqual(base, self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_B, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_B, 4)]}}))
        self.assertEqual(base, self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1, 99)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4, 99)]}}))
        self.assertEqual(base, self.fp({ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_C: {2: [shoot(ds.ENEMY_A, 4)]}}))

    def test_structure_changes_the_fingerprint(self) -> None:
        base = self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}})
        variants = [
            self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 4)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 1)]}}),
            self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}}, config="999 C8"),
            self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)], 1: None}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}}),
            self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1, ds.MISSILE)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}}),
            self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}}, cities=[]),
            self.fp({ds.UNIT_A: {2: [shoot(ds.ENEMY_A, 1)]}, ds.UNIT_B: {2: [shoot(ds.ENEMY_A, 4)]}}, hexes={ds.UNIT_A: 909}),
        ]
        self.assertEqual(len({base, *variants}), 1 + len(variants))


if __name__ == "__main__":
    unittest.main()
