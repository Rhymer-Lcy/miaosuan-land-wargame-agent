"""The exploratory candidate ``tactic-deployment-split-1`` against ``baseline-v2``. SYNTHETIC data only.

Eligibility from observed fields (ground, not artillery, two or more vehicles or squads, controlled, on the map); two
split rounds, then the baseline's own end of deployment; no split once deployment ended or outside the deployment
stage; the module's own check of type 314; play-stage decisions identical to ``baseline-v2``; the agent's memory and
replay; determinism; the frozen ``baseline-v2`` source digest.
"""

from __future__ import annotations

import copy
import random
import unittest

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.decision.context import build_context
from miaosuan_agent.evaluation import runtime_remediation as rr
from miaosuan_agent.evaluation.identity import policy_source_digest
from miaosuan_agent.experiments import deployment_split as dsp
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy

from tests.fixtures import decision_scenarios as ds
from tests.fixtures import synthetic as syn
from tests.test_shoot_reservation import GENERATED_SEED, SEAT, rich_situation, situation

V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
UNCONTROLLED = 900140
ENEMY = 900240


def unit(obj_id, color=ds.RED, hex_=102, *, unit_type=2, sub_type=0, blood=3):
    return dict(syn.unit(obj_id, color, hex_, unit_type=unit_type), sub_type=sub_type, blood=blood)


def deployment(units, controlled=None, ended=False):
    controlled = [u["obj_id"] for u in units if u["color"] == ds.RED and u["obj_id"] != UNCONTROLLED] \
        if controlled is None else controlled
    valid = {u["obj_id"]: {1: None} for u in units if u["color"] == ds.RED}
    return ds.play_observation(units, valid, stage=1, cur_step=0, ended=ended, controlled=controlled)


def decide(raw, memory=None, policy=dsp.DeploymentSplitPolicy):
    memory = dsp.SplitMemory() if memory is None else memory
    return policy(ds.costs()).decide(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED, memory)


def kinds(decision):
    return [(int(a["type"]), a.get("obj_id")) for a in decision.actions]


FORCE = [unit(ds.UNIT_A, blood=4), unit(ds.UNIT_B, unit_type=1, sub_type=2, blood=3),
         unit(ds.UNIT_C, sub_type=3, blood=3), unit(ds.UNIT_D, blood=1), unit(UNCONTROLLED, blood=4),
         unit(ENEMY, color=ds.BLUE, hex_=807, blood=4)]


class SplitTest(unittest.TestCase):
    def test_first_round_splits_every_eligible_operator(self) -> None:
        decision = decide(deployment(FORCE))
        self.assertEqual(kinds(decision), [(314, ds.UNIT_A), (314, ds.UNIT_B)])
        self.assertEqual(decision.memory, dsp.SplitMemory(deployment_sent=False, split_rounds=1))
        self.assertEqual(decision.trace.deployment, "deployment split round 1: 2 operators")
        self.assertEqual(decision.trace.diagnostics, (f"deployment split {ds.UNIT_A} (blood 4)",
                                                      f"deployment split {ds.UNIT_B} (blood 3)"))
        self.assertEqual(decision.trace.policy, dsp.CANDIDATE_ID)
        self.assertTrue(all(set(a) == {"actor", "obj_id", "type"} and a["actor"] == SEAT for a in decision.actions))

    def test_second_round_then_the_baseline_ends_deployment(self) -> None:
        raw = deployment(FORCE)
        second = decide(raw, dsp.SplitMemory(split_rounds=1))
        self.assertEqual(kinds(second), [(314, ds.UNIT_A), (314, ds.UNIT_B)])
        self.assertEqual(second.memory.split_rounds, 2)
        third = decide(raw, dsp.SplitMemory(split_rounds=2))
        self.assertEqual(kinds(third), [(333, None)])
        self.assertEqual(third.memory, dsp.SplitMemory(deployment_sent=True, split_rounds=2))
        self.assertEqual(kinds(third), kinds(decide(raw, Memory(), ShootReservationPolicy)))

    def test_nothing_eligible_ends_deployment_at_once(self) -> None:
        raw = deployment([unit(ds.UNIT_A, blood=1), unit(ds.UNIT_C, sub_type=3, blood=4),
                          unit(ds.UNIT_D, unit_type=3, sub_type=5, blood=2)])
        decision = decide(raw)
        self.assertEqual(kinds(decision), [(333, None)])
        self.assertEqual(decision.memory, dsp.SplitMemory(deployment_sent=True, split_rounds=0))

    def test_no_split_after_deployment_ended_or_in_play(self) -> None:
        self.assertEqual(kinds(decide(deployment(FORCE), dsp.SplitMemory(deployment_sent=True))), [])
        ended = decide(deployment(FORCE, ended=True))
        self.assertEqual((kinds(ended), ended.memory, ended.trace.deployment), ([], dsp.SplitMemory(), "not available"))
        play = ds.play_observation(FORCE[:2], {ds.UNIT_A: {1: None}, ds.UNIT_B: {1: None}}, cities=[syn.city(909)])
        self.assertFalse([a for a in decide(play).actions if a["type"] == 314])

    def test_baseline_memory_is_accepted(self) -> None:
        decision = decide(deployment(FORCE), Memory())
        self.assertEqual(decision.memory, dsp.SplitMemory(deployment_sent=False, split_rounds=1))

    def test_eligibility(self) -> None:
        def eligible(**fields):
            return dsp.can_split(type("Op", (), {"fields": fields})())
        self.assertTrue(eligible(type=1, sub_type=2, blood=2))
        self.assertTrue(eligible(type=2, sub_type=None, blood=4))
        self.assertFalse(eligible(type=2, sub_type=3, blood=4))
        self.assertFalse(eligible(type=3, sub_type=5, blood=4))
        self.assertFalse(eligible(type=2, sub_type=0, blood=1))
        self.assertFalse(eligible(type=2, sub_type=0, blood=True))
        self.assertFalse(eligible(type=2, sub_type=0, blood="4"))
        self.assertFalse(eligible(type=2, sub_type=0))

    def test_split_check(self) -> None:
        raw = deployment(FORCE)
        context = build_context(Observation.from_raw(raw, Origin.ENGINE), SEAT, ds.RED)
        ok = {"actor": SEAT, "obj_id": ds.UNIT_A, "type": 314}
        self.assertIsNone(dsp.split_problem(ok, context, (ds.UNIT_A,)))
        for bad, reason in ((dict(ok, actor=SEAT + 1), "actor is not this seat"),
                            (dict(ok, obj_id=UNCONTROLLED), "not an eligible controllable operator"),
                            (dict(ok, obj_id=True), "fields must be ints"),
                            (dict(ok, extra=1), "not a deployment split"), (dict(ok, type=14), "not a deployment split")):
            self.assertEqual(dsp.split_problem(bad, context, (ds.UNIT_A,)), reason)
        closed = build_context(Observation.from_raw(deployment(FORCE, ended=True), Origin.ENGINE), SEAT, ds.RED)
        self.assertEqual(dsp.split_problem(ok, closed, (ds.UNIT_A,)), "deployment is not open")

    def test_determinism_and_input_order(self) -> None:
        raw = deployment(FORCE)
        shuffled = copy.deepcopy(raw)
        shuffled["operators"] = list(reversed(shuffled["operators"]))
        self.assertEqual(digest(decide(raw).trace), digest(decide(shuffled).trace))
        self.assertEqual(raw, deployment(FORCE))


class PlayStageTest(unittest.TestCase):
    def test_play_decisions_equal_baseline_v2(self) -> None:
        rng = random.Random(GENERATED_SEED)
        states = [rich_situation(rng) for _ in range(400)]
        self.assertGreater(sum(1 for raw in states if decide(raw, Memory(deployment_sent=True),
                                                             ShootReservationPolicy).actions), 300)
        for raw in states:
            candidate = decide(raw, dsp.SplitMemory(deployment_sent=True, split_rounds=2))
            baseline = decide(raw, Memory(deployment_sent=True), ShootReservationPolicy)
            self.assertEqual([dict(a) for a in candidate.actions], [dict(a) for a in baseline.actions])
            first, second = candidate.trace.to_dict(), baseline.trace.to_dict()
            first.pop("policy"), second.pop("policy")
            self.assertEqual(first, second)

    def test_shoot_reservation_still_applies(self) -> None:
        raw = situation({ds.UNIT_A: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}, ds.UNIT_B: {2: [ds.shoot(ds.ENEMY_A, ds.GUN, 3)]}})
        self.assertEqual([a["obj_id"] for a in decide(raw, dsp.SplitMemory(deployment_sent=True)).actions], [ds.UNIT_A])


class AgentTest(unittest.TestCase):
    def setup_info(self):
        return {"seat": SEAT, "faction": ds.RED, "cost_data": None}

    def test_lifecycle_and_replay(self) -> None:
        agent = dsp.DeploymentSplitAgent()
        agent.setup(self.setup_info())
        self.assertEqual(agent.memory, dsp.SplitMemory())
        raw = deployment(FORCE)
        memory = agent.memory
        actions = agent.step(raw)
        self.assertEqual([(a["type"], a["obj_id"]) for a in actions], [(314, ds.UNIT_A), (314, ds.UNIT_B)])
        self.assertEqual(digest(agent.replay(raw, memory)), digest(agent.last_trace))
        self.assertEqual(agent.memory.split_rounds, 1)
        agent.reset()
        self.assertEqual(agent.memory, dsp.SplitMemory())
        self.assertIsNone(agent.policy)


class IdentityTest(unittest.TestCase):
    def test_baseline_v2_is_unchanged(self) -> None:
        self.assertEqual(policy_source_digest(sources=rr.candidate_sources() + ("experiments/shoot_reservation.py",))[0],
                         V2_DIGEST)

    def test_candidate_sources_add_one_file(self) -> None:
        sources = rr.candidate_sources() + ("experiments/shoot_reservation.py", "experiments/deployment_split.py")
        digest_value, files = policy_source_digest(sources=sources)
        self.assertNotEqual(digest_value, V2_DIGEST)
        self.assertIn("experiments/deployment_split.py", files)


if __name__ == "__main__":
    unittest.main()
