"""Sprint 36 revision 2: the counterattack bonus belongs to TB only (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 16).

Revision 1's dataclass default gave TA and the equivalence configuration ``ta-as-ca`` TB's counterattack bonus, so
``ta-as-ca`` differed from Sprint 35's CA at 5 genuine play decisions (registered gate G10). The synthetic tests of
revision 1 never had a recently lost objective in memory; this one does, and the bonus changes the decision in it.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from miaosuan_agent.tactical.config import TA, TB, TC, VARIANTS
from miaosuan_agent.tactical.policy import candidate_id
from tests.fixtures import s34_states as S
from tests.test_s36_tactical import BLUE, MOVE_ONLY, RED, by_unit, coalition, tactical, tank


def state():
    """Objective 505 (50 points) lost 100 steps ago, one enemy tank in its zone; objective 303 (80 points) also enemy-held
    and empty. The enemy holds every objective, so its tank counts against 505 (arrival 0): two own tanks form a
    coalition there (2.0 against 1.2 x 1.0), two places. Tank 1 at 404 (2 hexes from 505, 1 from 303): a coalition
    place is worth 1.0 x 50 x (0.5 + 1.0) = 75 without the bonus and 93.75 with it, the capture place at 303
    1.0 x 80 = 80 (each minus a travel cost below 1); tank 2 at 707 is outside the zone. The bonus changes the
    allocation."""
    own = [tank(1, RED, 404), tank(2, RED, 707)]
    enemy = [tank(901, BLUE, 506)]
    cities = [S.city(505, BLUE, 50), S.city(303, BLUE, 80)]
    return S.obs(RED, own + enemy, {1: MOVE_ONLY, 2: MOVE_ONLY}, cities=cities, step=600)


def with_loss(agent):
    agent.memory = replace(agent.memory, lost=((505, 500),))
    return agent


class CounterattackDefaultTests(unittest.TestCase):
    def test_only_tb_carries_the_bonus(self):
        self.assertEqual((TA.counterattack_bonus, TB.counterattack_bonus, TC.counterattack_bonus), (0.0, 0.25, 0.0))
        self.assertEqual(VARIANTS["ta-as-ca"].counterattack_bonus, 0.0)
        self.assertEqual(VARIANTS["tb-no-counterattack"].counterattack_bonus, 0.0)
        for config in VARIANTS.values():
            self.assertEqual(config.revision, 2)
        self.assertEqual(candidate_id(TC), "s36-tactical-guarded-orchestrator-2")

    def test_the_bonus_changes_this_decision(self):
        bonus = replace(VARIANTS["ta-as-ca"], name="ta-as-ca-with-bonus", counterattack_bonus=0.25)
        plain = by_unit(with_loss(tactical(VARIANTS["ta-as-ca"])).step(state()))
        boosted = by_unit(with_loss(tactical(bonus)).step(state()))
        self.assertNotEqual(plain, boosted)

    def test_ta_as_ca_decides_as_ca_after_a_loss(self):
        self.assertEqual(with_loss(tactical(VARIANTS["ta-as-ca"])).step(state()), coalition().step(state()))


if __name__ == "__main__":
    unittest.main()
