"""The Sprint 12 observers (``evaluation/s12_capture.py``) on stand-in games: read-only, complete, and the
seat-local reconstruction equal to the live decision (and different from a decision that is not v3's)."""

from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import s12_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonResult  # noqa: E402
from tests.fixtures import ps1_probe_engine as pe  # noqa: E402
from tests.fixtures import s12_engine as se  # noqa: E402


class DroppingAddon(tb.BatchAddon):
    """A planted defect: the add-on drops the last staged move after allocating (the live decision then differs from
    the allocation the observer reconstructs)."""

    def apply(self, observation, seat, faction, base, memory):
        result = super().apply(observation, seat, faction, base, memory)
        actions = list(result.actions)
        for i in range(len(actions) - 1, -1, -1):
            if actions[i].get("type") == 1 and any(c.get("kind") == "stage" and c.get("obj_id") == actions[i]["obj_id"]
                                                   for c in result.changes):
                del actions[i]
                break
        return AddonResult(tuple(actions), result.changes, result.skipped)


class DroppingPolicy(tb.BatchPolicy):
    addon_class = DroppingAddon


class DroppingAgent(tb.BatchAgent):
    policy_class = DroppingPolicy


class ObserverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record, cls.t9, cls.v3, cls.timeline, cls.windows = se.play_screen_game()

    def test_the_game_completes_without_observer_errors(self) -> None:
        self.assertEqual(self.record["status"], "COMPLETED")
        self.assertEqual(self.record["observer_errors"], [])

    def test_observers_do_not_change_the_game(self) -> None:
        spec = GameSpec(game_id="synthetic.C3.s12", scenario_id="900000001", map_id="9000", condition="C3",
                        red=INERT_ID, blue=sc.V3_ID, repetition=1, max_time=90)
        ticks = itertools.count()
        bare = play(lambda: se.ScreenEnv(play_steps=90), se.FACTORIES, spec, pe.Inputs, PLAYERS,
                    clock=lambda: next(ticks) * 0.001, replay_policies={sc.V3_ID})
        self.assertEqual(bare["state_chain"], self.record["state_chain"])
        self.assertEqual([s["trace_chain"] for s in bare["seats"]], [s["trace_chain"] for s in self.record["seats"]])
        self.assertEqual(bare["final_scores"], self.record["final_scores"])

    def test_the_timeline_is_full_step_and_reconstructs_every_decision(self) -> None:
        steps = self.record["steps"]
        self.assertEqual([s["k"] for s in self.windows["samples"]], list(range(steps)))
        self.assertIsNotNone(self.windows["final"])
        self.assertEqual(self.timeline["reconstructed_decisions"], steps)
        self.assertEqual(self.timeline["consistency_errors"], [])
        rows = [e["s12"]["11"] for e in self.timeline["steps"]]
        self.assertEqual(len(rows), steps)
        selected = [r for r in rows if r["allocation"]["selected"]]
        self.assertTrue(selected, "the candidate selected places in the stand-in game")
        first = selected[0]["allocation"]
        self.assertEqual(len(first["selected"]), 4)
        self.assertEqual(len(first["staged"]), 2)
        for claimant in first["claimants"].values():
            for key in ("objective", "path", "free_flow", "cost", "path_length", "feasible", "index", "status"):
                self.assertIn(key, claimant)
        for info in first["objectives"].values():
            for key in ("physical", "movers", "phantom", "mover_bounds", "free", "claimants", "ranked", "selected"):
                self.assertIn(key, info)

    def test_the_compact_capture_counts_the_trace_block(self) -> None:
        v3 = self.v3["v3"]
        self.assertEqual(v3["changes"].get("1:stage"), 4)
        self.assertEqual(v3["errors"], [])
        self.assertEqual(sum(e["kinds"].get("stage", 0) for e in v3["hold_episodes"]), 4)
        self.assertEqual(self.v3["schema"], cap.COMPACT_SCHEMA)

    def test_t9_capture_runs_unchanged_beside_them(self) -> None:
        seat = self.t9["seats"]["1"]
        self.assertEqual(seat["policy"], sc.V3_ID)
        self.assertEqual(seat["moves"]["emitted"], int(self.record["seats"][1]["actions_by_type"]["1"]))
        self.assertEqual(seat["objectives"]["held_at_end"], 2)

    def test_a_live_decision_that_is_not_the_allocation_is_caught(self) -> None:
        factories = dict(se.FACTORIES, **{sc.V3_ID: lambda: DroppingAgent()})
        spec = GameSpec(game_id="synthetic.C3.s12", scenario_id="900000001", map_id="9000", condition="C3",
                        red=INERT_ID, blue=sc.V3_ID, repetition=1, max_time=60)
        timeline = cap.V3Timeline((INERT_ID, sc.V3_ID), se.costs())
        ticks = itertools.count()
        play(lambda: se.ScreenEnv(play_steps=60), factories, spec, pe.Inputs, PLAYERS,
             clock=lambda: next(ticks) * 0.001, replay_policies={sc.V3_ID}, observer=timeline)
        self.assertTrue(timeline.consistency_errors)
        self.assertFalse(timeline.consistency_errors[0]["actions"])

    def test_a_baseline_seat_is_reconstructed_too(self) -> None:
        record, _, _, timeline, _ = se.play_screen_game(blue=sc.V2_ID, play_steps=40)
        self.assertEqual(record["status"], "COMPLETED")
        self.assertEqual(timeline["reconstructed_decisions"], record["steps"])
        self.assertEqual(timeline["consistency_errors"], [])
        self.assertNotIn("allocation", timeline["steps"][5]["s12"]["11"])


if __name__ == "__main__":
    unittest.main()
