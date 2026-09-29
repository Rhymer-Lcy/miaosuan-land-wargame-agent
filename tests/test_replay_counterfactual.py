"""The counterfactual replay script over a synthetic recorded game. SYNTHETIC data only."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_replay_spec = importlib.util.spec_from_file_location("replay_counterfactual", ROOT / "scripts" / "replay_counterfactual.py")
replay_script = importlib.util.module_from_spec(_replay_spec)
_replay_spec.loader.exec_module(replay_script)  # type: ignore[union-attr]


class ReplayScriptTest(unittest.TestCase):
    """The replay over a synthetic recorded game: fidelity, identical states and explained deltas."""

    def corpus(self, tamper=False):
        from miaosuan_agent import typed_json
        from miaosuan_agent.agent import BaselineAgent
        from miaosuan_agent.decision import digest
        from tests.fixtures import decision_scenarios as ds
        from tests.fixtures import synthetic as syn

        agent = BaselineAgent(strict=True)
        agent.setup({"seat": syn.RED_SEAT, "faction": ds.RED, "cost_data": syn.cost_data()})
        deploy = ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 505), syn.unit(ds.UNIT_B, ds.RED, 505)],
                                     {ds.UNIT_A: {1: None}, ds.UNIT_B: {1: None}}, stage=1, cur_step=0, ended=False)
        duplicate = ds.play_observation([syn.unit(ds.UNIT_A, ds.RED, 505), syn.unit(ds.UNIT_B, ds.RED, 505)],
                                        {ds.UNIT_A: {1: None, 5: None}, ds.UNIT_B: {1: None, 5: None}})
        records = []
        for step, raw in enumerate([deploy, ds.rich_observation(), duplicate]):
            actions = agent.step(raw)
            if tamper and step == 1:
                actions = actions[1:]
            records.append({"step": step, "seat": syn.RED_SEAT, "faction": ds.RED,
                            "observation": typed_json.encode(raw)[0], "actions": actions,
                            "trace_digest": digest(agent.last_trace)})
        return records

    def test_synthetic_game(self) -> None:
        from miaosuan_agent.boundary import MoveCosts
        from tests.fixtures import synthetic as syn

        tally = replay_script.Tally()
        replay_script.replay_sequence(self.corpus(), MoveCosts.from_raw(syn.cost_data()), tally, "synthetic")
        self.assertEqual((tally.states, tally.identical, tally.differing, tally.unexplained), (3, 2, 1, 0))
        self.assertEqual((tally.fidelity_checked, tally.fidelity_mismatches), (3, 0))
        self.assertEqual((tally.suppressed, tally.states_with_suppression, tally.v0_duplicates), (1, 1, 1))
        self.assertEqual(dict(tally.changed_types), {"5": 1})

    def test_unfaithful_recording_is_reported(self) -> None:
        from miaosuan_agent.boundary import MoveCosts
        from tests.fixtures import synthetic as syn

        tally = replay_script.Tally()
        replay_script.replay_sequence(self.corpus(tamper=True), MoveCosts.from_raw(syn.cost_data()), tally, "synthetic")
        self.assertEqual(tally.fidelity_mismatches, 1)
        self.assertEqual(tally.problems[0]["problem"], "baseline-v0 did not reproduce the recorded decision")


if __name__ == "__main__":
    unittest.main()
