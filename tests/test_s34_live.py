"""Sprint 34 live rules, observer and game-loop rehearsal (SYNTHETIC states; no engine, no SDK data)."""

from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s34_live as sl
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.s34_capture import S34Timeline
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from miaosuan_agent.integrated.agent import CommanderAgent
from miaosuan_agent.integrated.config import MO
from miaosuan_agent.integrated.policy import candidate_id
from tests.fixtures import s34_states as S
from tests.fixtures.s34_engine import ModelEnv

CAND = candidate_id(MO)


def reference(mean=100.0, sd=50.0, lo=0.0, hi=200.0, occ=(310.0, 310.0)):
    win = {"n": 15, "mean": mean, "sd": sd, "min": lo, "max": hi}
    return {"win": win, "occupy": {"n": 15, "mean": occ[0], "sd": 0.0, "min": occ[0], "max": occ[1]}}


def facts(position, win, occupy=310, **changes):
    game = sl.schedule(CAND)[position - 1]
    base = {"position": position, "batch": game["batch"], "condition": game["condition"],
            "scenario_id": game["scenario_id"], "status": "COMPLETED", "candidate": {"win": win, "occupy": occupy},
            "reference": reference(), "z": (win - 100.0) / 50.0, "contract_errors": 0, "replay_mismatches": 0,
            "observer_errors": 0, "reconstructed": 2880, "reconstruction_mismatches": 0, "decisions": 2880,
            "fallbacks": 0, "refusals": {"refused": 1, "refused_non_shoot": 0}, "unit_actions": 400}
    base.update(changes)
    return base


class ScheduleTests(unittest.TestCase):
    def test_twenty_four_games_in_four_batches(self):
        games = sl.schedule(CAND)
        self.assertEqual([g["session"] for g in games], list(range(2803, 2827)))
        self.assertEqual([sum(1 for g in games if g["batch"] == b) for b in sl.BATCHES], [8, 8, 4, 4])
        self.assertEqual(len({g["game_id"] for g in games}), 24)
        for g in games:
            side = sl.CANDIDATE_SIDE[g["condition"]]
            self.assertEqual(g[side], CAND)
            other = g["blue" if side == "red" else "red"]
            self.assertEqual(other, sl.V2 if g["condition"] in ("H1", "H2") else INERT_ID)
        a = [(g["scenario_id"], g["condition"]) for g in games if g["stage"] == "A"]
        self.assertEqual(sorted(set(a)), sorted((s, c) for s in sl.STAGE_A_SCENARIOS for c in ("H1", "H2")))
        self.assertTrue(all(a.count(x) == 2 for x in set(a)))
        b = [(g["scenario_id"], g["condition"]) for g in games if g["stage"] == "B"]
        self.assertEqual(sorted(set(b)), sorted((s, c) for s in sl.STAGE_B_SCENARIOS for c in ("C2", "C3")))


class LedgerTests(unittest.TestCase):
    def records(self, n, overrides=None):
        overrides = overrides or {}
        games = sl.schedule(CAND)
        out = [{"event": "session-open", "session": "2802"}, {"event": "session-close", "session": "2802"}]
        for g in games[:n]:
            out.append({"event": "session-open", "session": str(g["session"])})
            close = {"event": "session-close", "session": str(g["session"]), "outcome": {"game_id": g["game_id"]},
                     "integrity": {"ok": True}, "state_changed": False, "home_changed": False}
            close.update(overrides.get(g["position"], {}))
            out.append(close)
        return out

    def test_clean_and_planted(self):
        games = sl.schedule(CAND)
        self.assertEqual(sl.ledger_audit(self.records(3), games)["problems"], {})
        self.assertEqual(sl.ledger_audit(self.records(3), games)["sessions"], 3)
        bad = self.records(3, {2: {"outcome": {"game_id": "other"}}})
        self.assertIn("S2", sl.ledger_audit(bad, games)["problems"])
        bad = self.records(3, {3: {"state_changed": True}})
        self.assertIn("S2", sl.ledger_audit(bad, games)["problems"])
        open_only = self.records(2) + [{"event": "session-open", "session": "2805"}]
        self.assertIn("S2", sl.ledger_audit(open_only, games)["problems"])
        gap = [r for r in self.records(3) if r["session"] != "2804"]
        self.assertIn("S2", sl.ledger_audit(gap, games)["problems"])


class GateTests(unittest.TestCase):
    def test_structural_codes(self):
        self.assertEqual(sl.structural(facts(1, 100)), {})
        planted = {"S1": {"status": "CAPPED"}, "S4": {"replay_mismatches": 1},
                   "S5": {"reconstruction_mismatches": 1},
                   "S6": {"refusals": {"refused": 9, "refused_non_shoot": 0}, "unit_actions": 400}}
        for code, change in planted.items():
            self.assertEqual(sorted(sl.structural(facts(1, 100, **change))), [code], code)
        self.assertIn("S5", sl.structural(facts(1, 100, fallbacks=29)))
        self.assertEqual(sl.structural(facts(1, 100, fallbacks=28)), {})
        self.assertIn("S6", sl.structural(facts(1, 100, refusals={"refused": 6, "refused_non_shoot": 6})))
        self.assertIn("S5", sl.structural(facts(1, 100, reconstructed=0)))

    def test_severe_harm(self):
        a1 = [facts(p, 100) for p in range(1, 9)]
        self.assertTrue(sl.batch_gate("A1", a1)["open"])
        a1[3] = facts(4, -151)
        gate = sl.batch_gate("A1", a1)
        self.assertEqual((gate["open"], gate["reason"]), (False, "severe harm"))
        a1[3] = facts(4, -149)
        self.assertTrue(sl.batch_gate("A1", a1)["open"])
        stage_a = [facts(p, 100) for p in range(1, 17)]
        stage_a[0] = facts(1, -1)
        self.assertTrue(sl.batch_gate("A2", stage_a)["open"])
        stage_a[8] = facts(9, -1)  # the same configuration's second repetition
        self.assertEqual(sl.batch_gate("A2", stage_a)["reason"], "severe harm")
        stage_a[0] = facts(1, 0)  # equal to the minimum is not below it
        self.assertTrue(sl.batch_gate("A2", stage_a)["open"])

    def test_a_structural_stop_closes_any_gate(self):
        played = [facts(p, 100) for p in range(1, 18)]
        played[16] = facts(17, 100, status="FAIL")
        self.assertEqual(sl.batch_gate("B1", played)["reason"], "structural stop")
        self.assertFalse(sl.batch_gate("B2", [facts(p, 100) for p in range(1, 25)])["open"])

    def test_dispositions(self):
        open_gate = [{"batch": "A1", "open": True, "reason": "x"}]
        good = [facts(p, 160 if p <= 16 else 300) for p in range(1, 25)]
        self.assertEqual(sl.disposition(good, open_gate)["disposition"], "S34_INTEGRATED_PROMISING")
        flat = [facts(p, 100) for p in range(1, 25)]
        self.assertEqual(sl.disposition(flat, open_gate)["disposition"], "S34_INTEGRATED_INCONCLUSIVE")
        bad = [facts(p, 75 if p <= 16 else 300) for p in range(1, 25)]
        self.assertEqual(sl.disposition(bad, open_gate)["disposition"], "S34_INTEGRATED_REJECT")
        abandon = [facts(p, 160, occupy=230 if p in (17, 18, 21) else 310) for p in range(1, 25)]
        self.assertEqual(sl.disposition(abandon, open_gate)["disposition"], "S34_INTEGRATED_REJECT")
        one_short = [facts(p, 160, occupy=230 if p == 17 else 310) for p in range(1, 25)]
        self.assertEqual(sl.disposition(one_short, open_gate)["disposition"], "S34_INTEGRATED_INCONCLUSIVE")
        invalid = sl.disposition(good, [{"batch": "A1", "open": False, "reason": "structural stop"}])
        self.assertEqual(invalid["disposition"], "S34_LIVE_INVALID")
        harm = sl.disposition(good, [{"batch": "A1", "open": False, "reason": "severe harm"}])
        self.assertEqual(harm["disposition"], "S34_INTEGRATED_REJECT")
        partial = [facts(p, 160) for p in range(1, 9)]
        self.assertEqual(sl.disposition(partial, open_gate)["disposition"], "S34_INTEGRATED_INCONCLUSIVE")

    def test_bootstrap_is_deterministic(self):
        values = [0.1, -0.4, 0.9, 1.2, -0.2, 0.3]
        self.assertEqual(sl.bootstrap_interval(values), sl.bootstrap_interval(values))
        lo, hi = sl.bootstrap_interval(values)
        self.assertLess(lo, sum(values) / len(values))
        self.assertGreater(hi, sum(values) / len(values))


class FactTests(unittest.TestCase):
    def steps(self):
        unit = lambda uid, colour, hex_, path=0, speed=0.0: [uid, colour, 2, 0, hex_, path, speed, 3, 10, 0]  # noqa: E731
        start = {"k": -1, "cur_step": 0, "units": [unit(1, 0, 101), unit(2, 0, 102), unit(9, 1, 909)],
                 "cities": [[505, -1, 80], [606, -1, 50]]}
        s1 = {"k": 0, "cur_step": 0, "units": [unit(1, 0, 101, 2, 0.0), unit(2, 0, 102), unit(9, 1, 909)],
              "cities": [[505, 0, 80], [606, -1, 50]], "judge": [{"att_obj_id": 2, "target_obj_id": 9, "damage": 1}],
              "refusals": [{"message": {"actor": S.RED_SEAT, "type": 2}, "error": {"code": 516}}]}
        s2 = {"k": 1, "cur_step": 1, "units": [unit(1, 0, 101, 2, 0.0), unit(9, 1, 909)],
              "cities": [[505, 1, 80], [606, 0, 50]], "judge": [], "refusals": []}
        s3 = {"k": 2, "cur_step": 2, "units": [unit(1, 0, 101), unit(9, 1, 909)],
              "cities": [[505, 0, 80], [606, 0, 50]], "judge": [], "refusals": []}
        return [start, s1, s2, s3]

    def test_objectives_force_fire_refusals(self):
        o = sl.objective_facts(self.steps(), 0)
        self.assertEqual((o["losses"], o["recaptures"], o["final_owned"], o["first_owned_count"]), (1, 1, 2, 2))
        self.assertEqual(o["first_owned_step"]["objective 1 (80)"], {"own": 0, "enemy": 1})
        self.assertEqual(o["first_owned_before_enemy"], 2)
        f = sl.force_facts(self.steps(), 0)
        self.assertEqual((f["units_lost"], f["value_lost"], f["wait_unit_steps"], f["longest_wait"]), (1, 10, 2, 2))
        self.assertEqual(sl.fire_facts(self.steps(), 0), {"judged_attacks": 1, "damaging_attacks": 1,
                                                           "friendly_damage": 0})
        self.assertEqual(sl.refusal_facts(self.steps(), S.RED_SEAT)["refused"], 1)


def tiny_scenario():
    units = [S.unit(900101, 0, 101), S.unit(900102, 0, 102), S.unit(900103, 0, 101, type_=1, sub_type=2,
                                                                     basic_speed=5, value=4),
             S.unit(900104, 0, 102, sub_type=1, passenger_types=[2, 4, 7], value=8),
             S.unit(900201, 1, 1110), S.unit(900202, 1, 1111)]
    return {"scenario_id": 900000034, "time": {"cur_step": 0, "tick": 1.0, "max_time": 300},
            "cities": [S.city(808), S.city(1003, value=50), S.city(1108, value=50)], "operators": units}


class RehearsalTests(unittest.TestCase):
    """The real game loop, the live observers and the facts on the stand-in engine (the model world)."""

    def test_game_loop_observers_and_facts(self):
        cost = S.costs()
        inputs = SimpleNamespace(scenario=tiny_scenario(), basic={}, cost=cost, see=None)
        spec = mf.GameSpec(game_id="rehearsal", scenario_id="900000034", map_id="12", condition="H1", red=CAND,
                           blue=sl.V2, repetition=1, max_time=300)
        players = [{"seat": 1, "faction": 0, "role": 1, "user_name": "demo", "user_id": 0},
                   {"seat": 11, "faction": 1, "role": 1, "user_name": "demo", "user_id": 0}]
        factories = {CAND: lambda: CommanderAgent(MO), sl.V2: lambda: ShootReservationAgent(),
                     INERT_ID: lambda: PolicyAgent(INERT_ID)}
        explore = xp.ExploreCapture((CAND, sl.V2))
        timeline = S34Timeline(CAND, MO, MoveCosts.from_raw(cost))
        record = play(ModelEnv, factories, spec, inputs, players, replay_policies={CAND, sl.V2},
                      observer=tc.Tee(explore, timeline))
        self.assertEqual(record["status"], "COMPLETED", record.get("failure"))
        self.assertEqual(record["observer_errors"], [])
        compact = json.loads(timeline.files()[0])
        self.assertEqual(compact["checks"]["reconstructed"], compact["checks"]["decisions"])
        self.assertGreater(compact["checks"]["decisions"], 200)
        self.assertEqual(compact["checks"].get("reconstruction_mismatch", 0), 0)
        self.assertGreater(compact["checks"]["decisions_differing_from_v2"], 0)
        game = dict(sl.schedule(CAND)[0], game_id="rehearsal")
        references = {"configs": {f"{game['scenario_id']}.C1": {"red": reference(), "blue": reference()}}}
        f = sl.game_facts(game, record, compact, references)
        self.assertEqual(sl.structural(f), {})
        self.assertGreater(f["objectives"]["first_owned_count"], 0)
        self.assertGreater(sum(f["module_actions"].values()), 0)
        self.assertIsNotNone(f["z"])


if __name__ == "__main__":
    unittest.main()
