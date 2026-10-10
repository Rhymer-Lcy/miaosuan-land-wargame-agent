"""Sprint 35 live rules, observer and game-loop rehearsal (SYNTHETIC states; no engine, no SDK data)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from miaosuan_agent.agent import PolicyAgent
from miaosuan_agent.boundary import MoveCosts
from miaosuan_agent.coalition.agent import CoalitionAgent
from miaosuan_agent.coalition.config import CM
from miaosuan_agent.coalition.policy import candidate_id
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s35_live as sl
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.evaluation.game import play
from miaosuan_agent.evaluation.s35_capture import S35Timeline
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from miaosuan_agent.integrated.agent import CommanderAgent
from miaosuan_agent.integrated.config import MO
from tests.fixtures import s34_states as S
from tests.fixtures.s34_engine import ModelEnv

CAND = candidate_id(CM)


def reference(mean=100.0, sd=50.0, lo=0.0, hi=200.0, occ=310.0, remain=(50.0, 80.0)):
    return {"win": {"n": 15, "mean": mean, "sd": sd, "min": lo, "max": hi},
            "occupy": {"n": 15, "mean": occ, "sd": 0.0, "min": occ, "max": occ},
            "remain": {"n": 15, "mean": remain[1], "sd": 5.0, "min": remain[0], "max": remain[1]}}


def facts(position, win, occupy=310, remain=80, **changes):
    game = sl.schedule(CAND)[position - 1]
    base = {"position": position, "batch": game["batch"], "condition": game["condition"], "tag": game["tag"],
            "scenario_id": game["scenario_id"], "status": "COMPLETED",
            "candidate": {"win": win, "occupy": occupy, "remain": remain},
            "reference": reference(), "z": (win - 100.0) / 50.0, "contract_errors": 0, "replay_mismatches": 0,
            "observer_errors": 0, "reconstructed": 2880, "reconstruction_mismatches": 0, "decisions": 2880,
            "fallbacks": 0, "refusals": {"refused": 1, "refused_non_shoot": 0}, "unit_actions": 400,
            "latency_ms_p99": 30.0, "latency_ms_max": 900.0, "fire": {"friendly_damage": 0},
            "memory_bytes_max": 4000, "force": {"longest_wait": 0}}
    base.update(changes)
    return base


def played(win_s35, win_s34, win_b=300, n=48, b_changes=None):
    """Facts of the first ``n`` positions; ``b_changes``: position -> changes of a Stage B game's candidate scores."""
    out = []
    for p in range(1, n + 1):
        game = sl.schedule(CAND)[p - 1]
        if game["stage"] == "B":
            change = dict((b_changes or {}).get(p, {}))
            out.append(facts(p, change.pop("win", win_b), **change))
        else:
            out.append(facts(p, win_s35(game) if game["tag"] == "s35" else win_s34(game)))
    return out


class ScheduleTests(unittest.TestCase):
    def test_forty_eight_games_in_four_batches(self):
        games = sl.schedule(CAND)
        self.assertEqual([g["session"] for g in games], list(range(2827, 2875)))
        self.assertEqual([sum(1 for g in games if g["batch"] == b) for b in sl.BATCHES], [20, 20, 4, 4])
        self.assertEqual(len({g["game_id"] for g in games}), 48)
        for g in games:
            side = sl.CANDIDATE_SIDE[g["condition"]]
            self.assertEqual(g[side], g["policy"])
            other = g["blue" if side == "red" else "red"]
            self.assertEqual(other, sl.V2 if g["condition"] in ("H1", "H2") else INERT_ID)
            self.assertEqual(g["policy"], CAND if g["tag"] == "s35" else sl.S34_CONTROL)
        a = [(g["scenario_id"], g["condition"], g["tag"]) for g in games if g["stage"] == "A"]
        self.assertEqual(len(set(a)), 20)
        self.assertTrue(all(a.count(x) == 2 for x in set(a)))
        b = [(g["scenario_id"], g["condition"], g["tag"]) for g in games if g["stage"] == "B"]
        self.assertEqual(sorted(set(b)), sorted((s, c, "s35") for s in sl.STAGE_B_SCENARIOS for c in ("C2", "C3")))

    def test_order_is_interleaved(self):
        games = sl.schedule(CAND)
        firsts = [(g["tag"], g["condition"]) for g in games if g["stage"] == "A" and (g["position"] - 1) % 4 == 0]
        self.assertEqual(firsts, [("s35", "H1"), ("s34", "H1"), ("s35", "H1"), ("s34", "H1"), ("s35", "H1"),
                                  ("s34", "H1"), ("s35", "H1"), ("s34", "H1"), ("s35", "H1"), ("s34", "H1")])
        for sid in sl.STAGE_A_SCENARIOS:
            reps = [[(g["tag"], g["condition"]) for g in games if g["scenario_id"] == sid and g["stage"] == "A"
                     and g["repetition"] == r] for r in (1, 2)]
            self.assertNotEqual(reps[0], reps[1])
            self.assertEqual(sorted(reps[0]), sorted(reps[1]))


class LedgerTests(unittest.TestCase):
    def records(self, n, overrides=None):
        overrides = overrides or {}
        games = sl.schedule(CAND)
        out = [{"event": "session-open", "session": "2826"}, {"event": "session-close", "session": "2826"}]
        for g in games[:n]:
            out.append({"event": "session-open", "session": str(g["session"])})
            close = {"event": "session-close", "session": str(g["session"]), "outcome": {"game_id": g["game_id"]},
                     "integrity": {"ok": True}, "state_changed": False, "home_changed": False}
            close.update(overrides.get(g["position"], {}))
            out.append(close)
        return out

    def test_clean_and_planted(self):
        games = sl.schedule(CAND)
        self.assertEqual(sl.ledger_audit(self.records(3), games), {"sessions": 3, "games": [g["game_id"] for g in games[:3]],
                                                                    "problems": {}})
        self.assertIn("S2", sl.ledger_audit(self.records(3, {2: {"outcome": {"game_id": "x"}}}), games)["problems"])
        self.assertIn("S2", sl.ledger_audit(self.records(3, {3: {"home_changed": True}}), games)["problems"])
        self.assertIn("S2", sl.ledger_audit(self.records(2) + [{"event": "session-open", "session": "2829"}],
                                            games)["problems"])
        gap = [r for r in self.records(3) if r["session"] != "2828"]
        self.assertIn("S2", sl.ledger_audit(gap, games)["problems"])


class GateTests(unittest.TestCase):
    def test_structural_codes_fire_alone(self):
        self.assertEqual(sl.structural(facts(1, 100)), {})
        planted = {"S1": {"status": "CAPPED"}, "S4": {"contract_errors": 1}, "S5": {"reconstruction_mismatches": 1},
                   "S6": {"refusals": {"refused": 9, "refused_non_shoot": 0}}, "S7": {"latency_ms_p99": 200.5},
                   "S8": {"fire": {"friendly_damage": 1}}, "S9": {"memory_bytes_max": 200_001}}
        for code, change in planted.items():
            self.assertEqual(sorted(sl.structural(facts(1, 100, **change))), [code], code)
        self.assertEqual(sorted(sl.structural(facts(1, 100, latency_ms_max=3000.5))), ["S7"])
        self.assertEqual(sl.structural(facts(1, 100, latency_ms_p99=200.0, latency_ms_max=3000.0,
                                             memory_bytes_max=200_000)), {})

    def test_severe_harm(self):
        a1 = [facts(p, 100) for p in range(1, 21)]
        self.assertTrue(sl.batch_gate("A1", a1)["open"])
        first_s35 = next(g["position"] for g in sl.schedule(CAND) if g["tag"] == "s35")
        first_s34 = next(g["position"] for g in sl.schedule(CAND) if g["tag"] == "s34")
        a1[first_s34 - 1] = facts(first_s34, -151)           # the control's margins never gate
        self.assertTrue(sl.batch_gate("A1", a1)["open"])
        a1[first_s35 - 1] = facts(first_s35, -151)           # 0 - 3 x 50 = -150
        self.assertEqual(sl.batch_gate("A1", a1)["reason"], "severe harm")
        a1[first_s35 - 1] = facts(first_s35, -150)
        self.assertTrue(sl.batch_gate("A1", a1)["open"])
        stage_a = [facts(p, 100) for p in range(1, 41)]
        game = sl.schedule(CAND)[first_s35 - 1]
        twin = next(g["position"] for g in sl.schedule(CAND) if g["tag"] == "s35" and g["repetition"] == 2
                    and g["scenario_id"] == game["scenario_id"] and g["condition"] == game["condition"])
        stage_a[first_s35 - 1] = facts(first_s35, -1)
        self.assertTrue(sl.batch_gate("A2", stage_a)["open"])
        stage_a[twin - 1] = facts(twin, -1)
        self.assertEqual(sl.batch_gate("A2", stage_a)["reason"], "severe harm")
        deadlock = [facts(p, 100) for p in range(1, 21)]
        deadlock[first_s35 - 1] = facts(first_s35, 100, force={"longest_wait": 600})
        self.assertEqual(sl.batch_gate("A1", deadlock)["reason"], "severe harm")
        deadlock[first_s35 - 1] = facts(first_s35, 100, force={"longest_wait": 599})
        self.assertTrue(sl.batch_gate("A1", deadlock)["open"])

    def test_a2_gate_closes_on_dbar(self):
        low = played(lambda g: 75, lambda g: 100, n=40)        # d = -0.5 in every configuration
        gate = sl.batch_gate("A2", low)
        self.assertEqual((gate["open"], gate["reason"]), (False, "Dbar at or below the reject threshold"))
        self.assertTrue(sl.batch_gate("A2", played(lambda g: 76, lambda g: 100, n=40))["open"])

    def test_comparison_by_hand(self):
        # candidate +1 SD everywhere except 2010431153 blue (-1 SD); control at the mean
        def cand(g):
            return 50 if (g["scenario_id"] == "2010431153" and g["condition"] == "H2") else 150
        c = sl.comparison(played(cand, lambda g: 100, n=40))
        self.assertEqual(c["configurations_compared"], 10)
        self.assertEqual(c["d"]["2010431153 blue"], -1.0)
        self.assertEqual(c["d"]["2130511121 red"], 1.0)
        self.assertEqual(c["d_s"]["2010431153"], 0.0)
        self.assertEqual(c["dbar"], 0.8)                       # (9 x 1 - 1) / 10
        self.assertEqual(c["zbar_candidate"], 0.8)
        self.assertEqual(c["zbar_control"], 0.0)
        after_a1 = sl.comparison(played(cand, lambda g: 100, n=20))        # one game of each policy per configuration
        self.assertEqual((after_a1["configurations_compared"], after_a1["dbar"]), (10, 0.8))
        self.assertIsNone(sl.comparison(played(cand, lambda g: 100, n=12))["dbar"])   # three scenarios only

    def test_dispositions(self):
        gate = [{"batch": "A1", "open": True, "reason": "x"}]
        better = played(lambda g: 150, lambda g: 100)
        self.assertEqual(sl.disposition(better, gate)["disposition"], "S35_INTEGRATED_PROMISING")
        self.assertEqual(sl.disposition(better, gate, authorized=False)["disposition"], "S35_LIVE_NOT_AUTHORIZED")
        same = played(lambda g: 100, lambda g: 100)
        self.assertEqual(sl.disposition(same, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")
        worse = played(lambda g: 75, lambda g: 100)
        self.assertEqual(sl.disposition(worse, gate)["disposition"], "S35_INTEGRATED_REJECT")
        # breadth: positive in three scenarios only
        three = played(lambda g: 200 if g["scenario_id"] in sl.STAGE_A_SCENARIOS[:3] else 95, lambda g: 100)
        self.assertGreaterEqual(sl.comparison(three)["dbar"], 0.5)
        self.assertEqual(sl.disposition(three, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")
        # collapse: one scenario at d_s = -1 despite a large Dbar
        collapse = played(lambda g: 50 if g["scenario_id"] == "2010431153" else 250, lambda g: 100)
        self.assertEqual(sl.comparison(collapse)["d_s"]["2010431153"], -1.0)
        self.assertEqual(sl.disposition(collapse, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")
        # the candidate's own z must reach +0.5 too
        both_low = played(lambda g: 100, lambda g: 50)
        self.assertEqual(sl.disposition(both_low, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")
        occupy = played(lambda g: 150, lambda g: 100, b_changes={p: {"occupy": 230} for p in (41, 42, 45)})
        self.assertEqual(sl.disposition(occupy, gate)["disposition"], "S35_INTEGRATED_REJECT")
        remain = played(lambda g: 150, lambda g: 100, b_changes={p: {"remain": 49} for p in (41, 43, 46)})
        self.assertEqual(sl.disposition(remain, gate)["disposition"], "S35_INTEGRATED_REJECT")
        two_short = played(lambda g: 150, lambda g: 100, b_changes={p: {"remain": 49} for p in (41, 43)})
        self.assertEqual(sl.disposition(two_short, gate)["disposition"], "S35_INTEGRATED_PROMISING")
        one_occ = played(lambda g: 150, lambda g: 100, b_changes={41: {"occupy": 230}})
        self.assertEqual(sl.disposition(one_occ, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")
        slack = played(lambda g: 150, lambda g: 100, b_changes={p: {"win": -51} for p in (41, 42)})  # min 0 - 50
        self.assertEqual(sl.disposition(slack, gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")
        self.assertEqual(sl.disposition(better, [{"batch": "A1", "open": False, "reason": "structural stop"}])
                         ["disposition"], "S35_LIVE_INVALID")
        self.assertEqual(sl.disposition(better, [{"batch": "A1", "open": False, "reason": "severe harm"}])
                         ["disposition"], "S35_INTEGRATED_REJECT")
        self.assertEqual(sl.disposition(better[:20], gate)["disposition"], "S35_INTEGRATED_INCONCLUSIVE")


def tiny_scenario():
    units = [S.unit(900101, 0, 101), S.unit(900102, 0, 102), S.unit(900103, 0, 101, type_=1, sub_type=2,
                                                                     basic_speed=5, value=4),
             S.unit(900104, 0, 102, sub_type=1, passenger_types=[2, 4, 7], value=8),
             S.unit(900201, 1, 1110), S.unit(900202, 1, 1111)]
    return {"scenario_id": 900000035, "time": {"cur_step": 0, "tick": 1.0, "max_time": 300},
            "cities": [S.city(808), S.city(1003, value=50), S.city(1108, value=50)], "operators": units}


class RehearsalTests(unittest.TestCase):
    """The real game loop, the live observers and the facts on the stand-in engine (the model world)."""

    def run_game(self, policy, config, factory):
        cost = S.costs()
        inputs = SimpleNamespace(scenario=tiny_scenario(), basic={}, cost=cost, see=None)
        spec = mf.GameSpec(game_id="rehearsal", scenario_id="900000035", map_id="12", condition="H1", red=policy,
                           blue=sl.V2, repetition=1, max_time=300)
        players = [{"seat": 1, "faction": 0, "role": 1, "user_name": "demo", "user_id": 0},
                   {"seat": 11, "faction": 1, "role": 1, "user_name": "demo", "user_id": 0}]
        factories = {policy: factory, sl.V2: lambda: ShootReservationAgent(), INERT_ID: lambda: PolicyAgent(INERT_ID)}
        explore = xp.ExploreCapture((policy, sl.V2))
        timeline = S35Timeline(policy, config, MoveCosts.from_raw(cost))
        record = play(ModelEnv, factories, spec, inputs, players, replay_policies={policy, sl.V2},
                      observer=tc.Tee(explore, timeline))
        return record, json.loads(timeline.files()[0])

    def test_candidate_and_control(self):
        for tag, policy, config, factory in (("s35", CAND, CM, lambda: CoalitionAgent(CM)),
                                             ("s34", sl.S34_CONTROL, MO, lambda: CommanderAgent(MO))):
            record, compact = self.run_game(policy, config, factory)
            self.assertEqual(record["status"], "COMPLETED", record.get("failure"))
            self.assertEqual(record["observer_errors"], [])
            self.assertEqual(compact["schema"], "miaosuan-s35-timeline/1")
            self.assertEqual(compact["checks"]["reconstructed"], compact["checks"]["decisions"])
            self.assertGreater(compact["checks"]["decisions"], 200)
            self.assertEqual(compact["checks"].get("reconstruction_mismatch", 0), 0)
            self.assertGreater(compact["checks"]["memory_bytes_max"], 0)
            game = dict(next(g for g in sl.schedule(CAND) if g["tag"] == tag and g["condition"] == "H1"),
                        game_id="rehearsal")
            refs = {"configs": {f"{game['scenario_id']}.C1": {"red": reference(), "blue": reference()}}}
            f = sl.game_facts(game, record, compact, refs)
            self.assertEqual(sl.structural(f), {}, tag)
            self.assertEqual((f["tag"], f["policy"]), (tag, policy))
            self.assertIn("remain", f["reference"])
            self.assertIsNotNone(f["z"])

    def test_observer_refuses_an_unknown_configuration(self):
        with self.assertRaises(TypeError):
            S35Timeline(CAND, object(), MoveCosts.from_raw(S.costs()))


if __name__ == "__main__":
    unittest.main()
