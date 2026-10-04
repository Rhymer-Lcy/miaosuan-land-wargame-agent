"""Sprint 10 T9 diagnostic reconstruction and run-card safeguards."""

from __future__ import annotations

import importlib.util
import json
import unittest

from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import Memory
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_allocation as t9
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy
from miaosuan_agent.evaluation.t9_diagnostic import audit_allocation
from tests.fixtures import synthetic as syn
from tests.test_t9_allocation import A, B, C, IDS, RED, SEAT, movers, observation, unit


class AuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.costs = MoveCosts.from_raw(syn.cost_data())

    def compare(self, obs):
        baseline = ShootReservationPolicy(self.costs)
        base = baseline.decide(obs, SEAT, RED, Memory())
        audit = audit_allocation(obs, SEAT, RED, base.actions, baseline)
        actual = t9.AllocationPolicy(self.costs).decide(obs, SEAT, RED, ea.AddonMemory())
        self.assertEqual([dict(a) for a in audit.actions], [dict(a) for a in actual.actions])
        self.assertEqual([json.dumps(c, sort_keys=True, separators=(",", ":")) for c in audit.changes],
                         list(actual.trace.changes))
        return audit

    def test_replacements_and_alternative_reasons_match_frozen_v1(self) -> None:
        obs = observation(movers(), {i: {1: None} for i in IDS}, [syn.city(A), syn.city(B)])
        audit = self.compare(obs)
        changed = [m for m in audit.moves if m["outcome"] == "replace"]
        self.assertEqual([m["chosen_destination"] for m in changed], [B, B])
        self.assertTrue(all(any(a["rejection"] == "baseline destination full" for a in m["alternatives"])
                            for m in changed))

    def test_capacity_and_detour_withholding_match_frozen_v1(self) -> None:
        full_b = [unit(901000 + k, 800 + k, move_path=[B]) for k in range(t9.CAPACITY)]
        audit = self.compare(observation(movers() + full_b, {i: {1: None} for i in IDS},
                                         [syn.city(A), syn.city(B)]))
        self.assertEqual(sum(m["outcome"] == "withhold" for m in audit.moves), 2)
        ids = IDS[:5]
        audit = self.compare(observation(movers((303, 304, 305, 306, 404), ids),
                                         {i: {1: None} for i in ids}, [syn.city(A), syn.city(C)]))
        withheld = next(m for m in audit.moves if m["outcome"] == "withhold")
        self.assertIn("outside detour bound", {a["rejection"] for a in withheld["alternatives"]})


class CardTest(unittest.TestCase):
    def test_card_freezes_four_sessions_after_2772(self) -> None:
        spec = importlib.util.spec_from_file_location("builder", "scripts/build_t9_diagnostic_card.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        card = builder.build()
        self.assertEqual(card["budget"], {"batch_sessions": 4, "ledger_base_session": 2772,
                                          "sprint_session_cap": 14})
        self.assertEqual(len(card["games"]), 4)
        self.assertFalse(card["eligible_for_promotion"])
        self.assertEqual({g["scenario_id"] for g in card["games"]}, {"2120531121", "1930331196"})

    def test_conditional_c2_card_freezes_two_red_seat_sessions(self) -> None:
        spec = importlib.util.spec_from_file_location("builder", "scripts/build_t9_diagnostic_card.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        card = builder.build(builder.C2_CARD_ID)
        self.assertEqual(card["budget"], {"batch_sessions": 2, "ledger_base_session": 2772,
                                          "sprint_session_cap": 14})
        self.assertEqual(len(card["games"]), 2)
        self.assertFalse(card["eligible_for_promotion"])
        self.assertEqual({g["condition"] for g in card["games"]}, {"C2"})
        self.assertEqual([g["red"] for g in card["games"]], [t9.CANDIDATE_ID, builder.V2_ID])


if __name__ == "__main__":
    unittest.main()
