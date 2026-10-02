"""The PS-1 probe's post-hoc descriptions (``scripts/ps1_probe_posthoc.py``) on SYNTHETIC inputs.

The order-aware reading of arbitration and re-wait steps agrees with trajectories generated in ascending processing
order and not with descending ones; the post-hoc M1d equals M1c unless a move is ordered into a full first hex, where it
waits at once; the stop footprint counts each stopped unit's state before and after its stop on the stand-in engine.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import ps1_model as pm

from tests.fixtures import ps1_probe_engine as pe
from tests.fixtures import ps1_trajectories as tr

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ps1_probe_posthoc", ROOT / "scripts" / "ps1_probe_posthoc.py")
ph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ph)
an = tr.analysis


class OrderAwareTest(unittest.TestCase):
    def test_ascending_data_agrees_and_descending_data_does_not(self) -> None:
        t, _ = tr.contention_case("M1c")
        result = ph.order_aware(t.b, t.ks)
        self.assertGreater(result["steps_with_a_re_wait"], 0)
        self.assertEqual(result["order_aware_disagrees"], 0)
        reverse, _ = tr.contention_case("descending")
        self.assertGreater(ph.order_aware(reverse.b, reverse.ks)["order_aware_disagrees"], 0)


class M1dTest(unittest.TestCase):
    def test_equal_to_m1c_without_an_order_into_a_full_hex(self) -> None:
        units = [pm.Unit(1, 1, tr.SPEED, 0), pm.Unit(2, 4, tr.SPEED, 0)]
        orders = {0: [("move", 1, (2, 3))], 5: [("move", 2, (5,))]}
        t, _ = tr.generate(units, tr.line(5), 60, orders)
        self.assertEqual(ph.replay_m1d(t, 0, tr.line(5), 0, orders), an.replay(t, 0, tr.line(5), 0, orders=orders).entries)

    def test_an_order_into_a_full_hex_waits_at_once(self) -> None:
        # hex 2 holds four units, two of which leave at once; unit 9 is ordered into hex 2 in the same decision
        units = [pm.Unit(i, 2, tr.SPEED, 0) for i in (1, 2, 3, 4)] + [pm.Unit(9, 1, tr.SPEED, 0)]
        orders = {0: [("move", 1, (3,)), ("move", 2, (3,)), ("move", 9, (2,))]}
        t, _ = tr.generate(units, tr.line(5), 40, orders)
        m1c = {u: k for k, u, h in an.replay(t, 0, tr.line(5), 0, orders=orders).entries if h == 2}
        m1d = {u: k for k, u, h in ph.replay_m1d(t, 0, tr.line(5), 0, orders) if h == 2}
        # M1c starts the traversal at the order (entry a hex time later, the leavers having gone); M1d waits at once,
        # restarts when room appears and needs a full hex time from there
        self.assertEqual(m1c[9], 5)
        self.assertEqual(m1d[9], 9)


class FootprintTest(unittest.TestCase):
    def test_states_before_and_after_the_stop_on_the_stand_in(self) -> None:
        record, compact, windows = pe.play_probe(play_steps=140)
        game = an.Game(record, compact, windows)
        k0 = an.hook_events(game)["trigger_k"]
        group = sorted(a["action"]["obj_id"] for a in game.steps[k0]["submitted"] if a["action"]["type"] == 10)
        result = ph.stop_footprint(game, group, k0)
        self.assertEqual((result["units"], result["path_kept_to_the_end"]), (4, 0))  # the stand-in stops in place
        after = result["states"]["after"]
        self.assertTrue(any("listed=[]" in key for key in after))  # nothing listed during the transition
        self.assertTrue(any("listed=[1]" in key for key in after))  # the move listed again afterwards
        self.assertEqual(sum(after.values()), 4 * (game.steps[-1]["k"] - k0))


if __name__ == "__main__":
    unittest.main()
