"""The registered candidate ``t7-idle-concealment`` (``experiments/t7_concealment.py``). SYNTHETIC observations.

The rule is the Sprint 5 shadow, imported unchanged; these tests check the wrapper: the emitted actions are the
shadow's, ``baseline-v2``'s actions come first and unchanged, the trace's t7 block records the baseline trace digest,
the added orders and the skip reasons, an unexpected error in the candidate layer falls back to ``baseline-v2``, a
contract violation is handled as for ``baseline-v2``, and the policy source is the frozen set plus the two modules.
"""

from __future__ import annotations

import pickle
import unittest
from unittest import mock

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.evaluation import t7_probe as tp
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files
from miaosuan_agent.experiments import t7_concealment as cand
from miaosuan_agent.experiments import t7_idle_concealment as sh
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import t7_probe_engine as fx

BLUE_SEAT, BLUE = 11, 1


class WrapperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, _, windows = fx.play_t7(play_steps=120, flips=((60, fx.OBJ_B, fx.RED),))
        cls.observations = [pickle.loads(s["seats"][BLUE_SEAT]["observation"])
                            for s in sorted(windows["samples"], key=lambda s: s["k"])]
        cls.costs = MoveCosts.from_raw(fx.Inputs.cost)

    def test_equals_the_shadow_and_starts_with_baseline_v2(self) -> None:
        policy, shadow, v2 = cand.ConcealmentPolicy(self.costs), sh.IdleConcealmentShadow(self.costs), \
            ShootReservationPolicy(self.costs)
        m_c, m_s, m_v = sh.ShadowMemory(), sh.ShadowMemory(), Memory()
        added = 0
        for raw in self.observations:
            obs = Observation.from_raw(raw, Origin.ENGINE)
            dc, ds, dv = policy.decide(obs, BLUE_SEAT, BLUE, m_c), shadow.decide(obs, BLUE_SEAT, BLUE, m_s), \
                v2.decide(obs, BLUE_SEAT, BLUE, m_v)
            m_c, m_s, m_v = dc.memory, ds.memory, dv.memory
            self.assertEqual([dict(a) for a in dc.actions], [dict(a) for a in ds.actions])
            self.assertEqual([dict(a) for a in dc.actions[:len(dv.actions)]], [dict(a) for a in dv.actions])
            self.assertEqual(dc.trace.baseline_trace_sha256, digest(dv.trace))
            self.assertEqual([list(a) for a in dc.trace.added], [[a["obj_id"], a["target_state"]] for a in ds.added])
            self.assertEqual(tuple(dc.trace.skipped), tuple(ds.skipped))
            self.assertEqual(dc.trace.policy, cand.CANDIDATE_ID)
            self.assertEqual(list(dc.trace.emitted), [(int(a["type"]), a.get("obj_id")) for a in dc.actions])
            self.assertIsNone(dc.trace.t7_error)
            payload = dc.trace.to_dict()
            self.assertEqual(payload["schema"], cand.TRACE_SCHEMA)
            self.assertEqual(payload["t7"]["baseline_trace_sha256"], digest(dv.trace))
            added += len(dc.trace.added)
        # the three idle blue units at the first play decision; baseline-v2 moves them to the objective that flips at
        # step 60 once they are concealed, and the candidate orders each again when it stands idle there
        self.assertEqual(added, 6)

    def test_an_unexpected_error_falls_back_to_baseline_v2(self) -> None:
        v2_policy = ShootReservationPolicy(self.costs)
        obs = next(o for o in (Observation.from_raw(raw, Origin.ENGINE) for raw in self.observations[1:])
                   if v2_policy.decide(o, BLUE_SEAT, BLUE, Memory()).actions)  # a decision where baseline-v2 acts
        with mock.patch.object(sh, "replace", side_effect=RuntimeError("planted")):  # inside the shadow only
            d = cand.ConcealmentPolicy(self.costs).decide(obs, BLUE_SEAT, BLUE, sh.ShadowMemory())
        v2 = ShootReservationPolicy(self.costs).decide(obs, BLUE_SEAT, BLUE, Memory())
        self.assertTrue(v2.actions)
        self.assertEqual([dict(a) for a in d.actions], [dict(a) for a in v2.actions])
        self.assertIn("RuntimeError: planted", d.trace.t7_error)
        self.assertEqual(d.trace.added, ())
        self.assertEqual(d.trace.baseline_trace_sha256, digest(v2.trace))
        self.assertEqual(d.memory.last_order, ())

    def test_contract_violation_gives_no_action(self) -> None:
        agent = cand.ConcealmentAgent()
        agent.setup({"seat": BLUE_SEAT, "faction": BLUE, "cost_data": fx.Inputs.cost})
        self.assertEqual(agent.step({"operators": "not a list"}), [])
        self.assertIsNotNone(agent.last_trace.error)
        self.assertEqual(agent.last_trace.policy, cand.CANDIDATE_ID)

    def test_agent_replay_reproduces_and_reset_clears_memory(self) -> None:
        agent = cand.ConcealmentAgent()
        agent.setup({"seat": BLUE_SEAT, "faction": BLUE, "cost_data": fx.Inputs.cost})
        for raw in self.observations[:3]:
            memory = agent.memory
            agent.step(raw)
            self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        self.assertNotEqual(agent.memory.last_order, ())
        agent.reset()
        self.assertEqual(agent.memory, sh.ShadowMemory())

    def test_no_order_in_deployment(self) -> None:
        raw = dict(self.observations[1])
        raw["time"] = dict(raw["time"], stage=1)
        d = cand.ConcealmentPolicy(self.costs).decide(Observation.from_raw(raw, Origin.ENGINE), BLUE_SEAT, BLUE,
                                                      sh.ShadowMemory())
        self.assertEqual(d.trace.added, ())
        self.assertFalse(any(a.get("type") == 6 for a in d.actions))


class IdentityTest(unittest.TestCase):
    def test_source_set_is_baseline_v2_plus_the_two_modules(self) -> None:
        baseline_sources = ("agent.py", "boundary", "decision", "experiments/__init__.py",
                            "experiments/occupy_reservation.py", "experiments/routing_bounded.py",
                            "experiments/shoot_reservation.py")
        baseline_files = policy_source_files(sources=baseline_sources)
        self.assertEqual(digest_of_files(baseline_files), tp.BASELINE_V2_SOURCE_SHA256)
        source = tp.candidate_policy_source({"sources": list(baseline_sources)})
        self.assertEqual(sorted(set(source["files"]) - set(baseline_files)),
                         ["experiments/t7_concealment.py", "experiments/t7_idle_concealment.py"])
        self.assertEqual(digest_of_files(source["files"]), source["sha256"])


if __name__ == "__main__":
    unittest.main()
