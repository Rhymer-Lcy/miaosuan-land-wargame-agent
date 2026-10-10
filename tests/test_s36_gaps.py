"""Sprint 36 tests added after the first mutation run (``evaluation/s36-tactical-recovery/mutation.json``).

The first run killed 40 of 47 planted defects. Five survivors were test gaps, closed here; two were equivalent mutants
(an enemy in the zone also has arrival 0, so the race check refuses it anyway; replication games carry a tag the
comparison never reads), replaced in ``scripts/mutate_s36.py`` by defects these tests also cover.
"""

from __future__ import annotations

import unittest

from miaosuan_agent.coalition import coalition as K
from miaosuan_agent.evaluation import s36_capture as cap
from miaosuan_agent.evaluation import s36_live as L
from miaosuan_agent.evaluation import s36_study as st
from miaosuan_agent.integrated import facts as F
from miaosuan_agent.tactical.memory import TacticalMemory
from tests.fixtures import s34_states as S
from tests.test_s36_live import GAMES, facts as live_facts
from tests.test_s36_study import RULES, games
from tests.test_s36_tactical import BLUE, MOVE_ONLY, RED, assess, tank


class StudyMessageTests(unittest.TestCase):
    def test_a_game_after_a_stop_is_named_as_such(self):
        d = st.derive(RULES, games(4, p2={"stop": "harm"}))
        self.assertTrue(any("after the study stopped at 2" in p for p in d["protocol_problems"]))
        gap = games(3)
        del gap[2]
        d = st.derive(RULES, gap)
        self.assertTrue(any("was played while position 2 was not" in p for p in d["protocol_problems"]))


class RememberedThreatTests(unittest.TestCase):
    def test_withdrawal_needs_a_visible_threat(self):
        # three tanks known only from a sighting 10 steps old (confidence 590/600), 3 hexes from 505
        own = [S.unit(1, RED, 505, sub_type=F.IFV, value=8), tank(2, RED, 505)]
        seen = tuple((901 + i, 502, 50, F.TANK, 1000) for i in range(3))
        memory = TacticalMemory(deployment_sent=True, seen=seen)
        obs = S.obs(RED, own, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=[S.city(505, RED, 80), S.city(909, RED, 50)],
                    step=60)
        a = assess(obs, memory=memory)[505]
        self.assertEqual(a.stance, K.DELAY)
        self.assertAlmostEqual(a.visible_threat, 0.0)
        self.assertEqual((a.keep, a.withdraw), ((1, 2), ()))                  # nobody leaves on memory alone

    def test_a_remembered_enemy_contests_the_race(self):
        # an enemy tank seen 10 steps ago at 507 (outside 505's zone, arrival 20 steps): no opportunity capture for
        # a tank 6 hexes away (arrival 120)
        own = [tank(1, RED, 101)]
        memory = TacticalMemory(deployment_sent=True, seen=((901, 507, 50, F.TANK, 1000),))
        obs = S.obs(RED, own, {1: MOVE_ONLY}, cities=[S.city(505, -1, 80)], step=60)
        self.assertNotEqual(assess(obs, memory=memory)[505].stance, K.CAPTURE)


class FallbackHexTests(unittest.TestCase):
    def test_the_fallback_hex_is_outside_every_objective_zone(self):
        enemies = [tank(901, BLUE, 502, basic_speed=4), tank(902, BLUE, 402, basic_speed=4),
                   tank(903, BLUE, 602, basic_speed=4)]
        cities = [S.city(505, RED, 80), S.city(306, BLUE, 50)]                # an enemy-held objective to the north-east
        a = assess(S.obs(RED, [tank(2, RED, 505)] + enemies, {2: MOVE_ONLY}, cities=cities))[505]
        dest = a.withdraw[0][1]
        self.assertNotIn(dest, F.zone(306, S.ROWS, S.COLS))
        self.assertNotIn(dest, F.zone(505, S.ROWS, S.COLS))
        self.assertEqual(dest, 507)


class WaitCauseTests(unittest.TestCase):
    def test_causes(self):
        self.assertEqual(cap.wait_cause(4, 1, 1, 1), cap.FULL)
        self.assertEqual(cap.wait_cause(3, 1, 0, 1), cap.SUPPRESSED)
        self.assertEqual(cap.wait_cause(3, 0, 1, 1), cap.STOPPED)
        self.assertEqual(cap.wait_cause(0, 0, 0, 1), cap.ENEMY)
        self.assertEqual(cap.wait_cause(3, 0, 0, 0), cap.UNEXPLAINED)

    def test_halted_units_counts_own_ground_units_on_the_next_hex(self):
        unit = {"obj_id": 1, "color": 0, "type": 2, "move_path": [506, 507], "speed": 0, "keep": 0,
                "flag_force_stop": 0}
        own = [{"obj_id": 10 + i, "color": 0, "type": 2, "cur_hex": 506, "on_board": 0} for i in range(4)]
        raw = {"operators": [unit]}
        self.assertEqual(cap.halted_units(raw, 0, own), [[1, cap.FULL]])
        self.assertEqual(cap.halted_units(raw, 0, own[:3]), [[1, cap.UNEXPLAINED]])
        aboard = own[:3] + [dict(own[3], on_board=1)]
        self.assertEqual(cap.halted_units(raw, 0, aboard), [[1, cap.UNEXPLAINED]])

    def test_only_full_hex_runs_count_as_a_deadlock(self):
        halts = [[k, 7, cap.SUPPRESSED] for k in range(700)]
        self.assertEqual(L.halt_facts({"halts": halts})["longest_full_hex_wait"], 0)
        halts = [[k, 7, cap.FULL] for k in range(600)] + [[k, 8, cap.FULL] for k in range(0, 1200, 2)]
        facts = L.halt_facts({"halts": halts})
        self.assertEqual(facts["longest_full_hex_wait"], 600)                    # unit 8's steps are not consecutive
        self.assertEqual(facts["by_cause"], {cap.FULL: 1200})


class ComparisonBatchTests(unittest.TestCase):
    def test_the_a1_comparison_ignores_later_batches(self):
        history = []
        for g in GAMES[:43]:
            share = -1.0 if (g["tag"] == "s36" and g["batch"] == "A2") else 0.0
            history.append(live_facts(g, share=share))
        self.assertEqual(L.comparison(history, ("A1",))["dbar"], 0.0)
        self.assertEqual(L.comparison(history)["dbar"], -0.5)

    def test_the_held_out_reading_uses_only_held_out_games(self):
        history = [live_facts(g, share=(0.4 if g["tag"] == "s36" else 0.0)) for g in GAMES[:47]]
        self.assertEqual(L.held_out(history), 0.4)
        self.assertIsNone(L.held_out(history[:43]))


if __name__ == "__main__":
    unittest.main()
