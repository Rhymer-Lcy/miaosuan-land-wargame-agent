"""Sprint 36 live rules: schedule, stops by category, batch gates and dispositions (SYNTHETIC facts)."""

from __future__ import annotations

import copy
import math
import unittest

from miaosuan_agent.evaluation import s36_live as L
from miaosuan_agent.evaluation import s36_study as st

CAND = "s36-tactical-guarded-orchestrator-1"


def refusal(fire=10, other=20, classes=None, retained=True, echo=True):
    counts = {f"{c}_{g}": 0 for c in ("A", "B", "D", "R", "E") for g in ("fire", "other")}
    counts.update(classes or {})
    return {"retained": retained, "echo_matches": echo, "echo": fire + other, "unit_actions": fire + other,
            "fire_actions": fire, "other_actions": other, "classes": counts, "repeat_actor_max": 0}


def facts(game, share=0.0, win=0, ref_min=-1000, ref_sd=100.0, occupy=310, occ_min=0, **over):
    f = {"position": game["position"], "batch": game["batch"], "tag": game["tag"], "condition": game["condition"],
         "scenario_id": game["scenario_id"], "status": "COMPLETED", "observer_errors": 0, "replay_mismatches": 0,
         "reconstructed": 100, "reconstruction_mismatches": 0, "contract_errors": 0, "decisions": 100, "fallbacks": 0,
         "latency_ms_p99": 10.0, "latency_ms_max": 50.0, "memory_bytes_max": 3000, "fire": {"friendly_damage": 0},
         "refusal_summary": refusal(), "halts": {"by_cause": {}, "longest_full_hex_wait": 0}, "share": share,
         "candidate": {"win": win, "occupy": occupy},
         "reference": {"win": {"min": ref_min, "sd": ref_sd}, "occupy": {"min": occ_min}}}
    f.update(over)
    return f


GAMES = L.schedule(CAND)


def played(n, special=None, share_s36=0.0, share_s34=0.0):
    out = {}
    for g in GAMES[:n]:
        share = share_s36 if g["tag"] == "s36" else share_s34
        out[g["position"]] = facts(g, share=share)
    for p, change in (special or {}).items():
        out[p] = dict(out[p], **change)
    return out


def name(d):
    return d["disposition"]["disposition"]


class ScheduleTests(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(len(GAMES), L.SESSION_CAP)
        self.assertEqual([g["session"] for g in GAMES], list(range(2846, 2897)))
        counts = {b: sum(1 for g in GAMES if g["batch"] == b) for b in L.BATCHES}
        self.assertEqual(counts, {"A1": 23, "A2": 20, "H1": 4, "B1": 4})
        self.assertEqual(sum(1 for g in GAMES if g["tag"] == "s35"), 3)
        self.assertEqual({(g["scenario_id"], g["condition"]) for g in GAMES if g["tag"] == "s35"},
                         {("2130511121", "H2"), ("1930331196", "H2"), ("1910631192", "H2")})
        for g in GAMES:
            if g["batch"] in ("A1", "A2", "H1"):
                self.assertIn(L.V2, (g["red"], g["blue"]))
            else:
                self.assertIn(L.INERT, (g["red"], g["blue"]))
        # each Stage A configuration: two candidate and two control games
        for sid in L.STAGE_A_SCENARIOS:
            for cond in ("H1", "H2"):
                for tag in ("s36", "s34"):
                    self.assertEqual(sum(1 for g in GAMES if (g["scenario_id"], g["condition"], g["tag"]) ==
                                         (sid, cond, tag)), 2)
        self.assertEqual(len({g["game_id"] for g in GAMES}), len(GAMES))

    def test_calibrated_constants(self):
        self.assertEqual(L.SHARE_SD, 0.4187)
        self.assertAlmostEqual(L.NULL_SD_DBAR, round(0.4187 / math.sqrt(10), 4))
        self.assertEqual((L.UNFAVOURABLE_DBAR, L.EARLY_FUTILITY), (-0.2595, -0.4822))


class StopTests(unittest.TestCase):
    def test_in_progress_and_completion(self):
        self.assertEqual(name(st.report(L.RULES, {})), "S36_LIVE_NOT_AUTHORIZED")
        self.assertEqual(name(st.report(L.RULES, played(10))), "S36_LIVE_IN_PROGRESS")
        d = st.report(L.RULES, played(51))
        self.assertTrue(d["complete"])
        self.assertEqual(name(d), "S36_INCONCLUSIVE")

    def test_one_race_refusal_in_a_small_game_is_not_a_stop(self):
        small = {"refusal_summary": refusal(fire=4, other=2, classes={"D_fire": 1})}
        d = st.report(L.RULES, played(19, {19: small}))
        self.assertEqual(name(d), "S36_LIVE_IN_PROGRESS")

    def test_a_control_contract_refusal_invalidates_and_a_candidate_one_is_an_agent_failure(self):
        a = {"refusal_summary": refusal(classes={"A_fire": 1})}
        control = next(g["position"] for g in GAMES if g["tag"] == "s34")
        cand = next(g["position"] for g in GAMES if g["tag"] == "s36")
        self.assertEqual(name(st.report(L.RULES, played(control, {control: a}))), "S36_LIVE_INVALID")
        self.assertEqual(name(st.report(L.RULES, played(cand, {cand: a}))), "S36_AGENT_FAILURE")

    def test_harness_failures_are_invalid_whoever_played(self):
        cand = next(g["position"] for g in GAMES if g["tag"] == "s36")
        for change in ({"status": "FAILED"}, {"reconstruction_mismatches": 1}, {"observer_errors": 1},
                       {"refusal_summary": refusal(retained=False)}, {"refusal_summary": refusal(echo=False)}):
            self.assertEqual(name(st.report(L.RULES, played(cand, {cand: change}))), "S36_LIVE_INVALID", change)

    def test_candidate_quality_failures(self):
        cand = next(g["position"] for g in GAMES if g["tag"] == "s36")
        for change in ({"fallbacks": 2}, {"latency_ms_max": 3000.5}, {"memory_bytes_max": 200001},
                       {"fire": {"friendly_damage": 1}}, {"contract_errors": 1},
                       {"halts": {"by_cause": {}, "longest_full_hex_wait": 600}},
                       {"refusal_summary": refusal(fire=300, classes={"D_fire": 13})}):
            self.assertEqual(name(st.report(L.RULES, played(cand, {cand: change}))), "S36_AGENT_FAILURE", change)
        ok = {"halts": {"by_cause": {"suppressed": 700}, "longest_full_hex_wait": 599}}
        self.assertEqual(name(st.report(L.RULES, played(cand, {cand: ok}))), "S36_LIVE_IN_PROGRESS")

    def test_unexplained_refusals_accumulate_over_the_study(self):
        e1 = {"refusal_summary": refusal(classes={"E_other": 1})}
        positions = [g["position"] for g in GAMES[:6]]
        changes = {p: e1 for p in positions[:3]}
        d = st.report(L.RULES, played(6, changes))
        self.assertEqual(d["stop"]["position"], positions[2])         # the third unexplained refusal of the study

    def test_game_level_severe_harm(self):
        cand = next(g["position"] for g in GAMES if g["tag"] == "s36")
        d = st.report(L.RULES, played(cand, {cand: {"candidate": {"win": -1301, "occupy": 0}}}))
        self.assertEqual(name(d), "S36_SEVERE_HARM")                   # -1000 - 3 x 100 = -1300
        d = st.report(L.RULES, played(cand, {cand: {"candidate": {"win": -1300, "occupy": 0}}}))
        self.assertEqual(name(d), "S36_LIVE_IN_PROGRESS")
        control = next(g["position"] for g in GAMES if g["tag"] == "s34")
        d = st.report(L.RULES, played(control, {control: {"candidate": {"win": -5000, "occupy": 0}}}))
        self.assertEqual(name(d), "S36_LIVE_IN_PROGRESS")             # harm is read on candidate games only


class GateTests(unittest.TestCase):
    def test_early_futility_after_a1(self):
        d = st.report(L.RULES, played(23, share_s36=-0.5, share_s34=0.0))
        self.assertEqual((name(d), d["stop"]["batch"], d["stop"]["at"]), ("S36_UNFAVOURABLE", "A1", "batch"))
        d = st.report(L.RULES, played(23, share_s36=-0.48, share_s34=0.0))
        self.assertEqual(name(d), "S36_LIVE_IN_PROGRESS")             # -0.48 > -0.4822

    def test_a2_futility_and_harm(self):
        d = st.report(L.RULES, played(43, share_s36=-0.26, share_s34=0.0))
        self.assertEqual((name(d), d["stop"]["batch"]), ("S36_UNFAVOURABLE", "A2"))
        d = st.report(L.RULES, played(43, share_s36=-0.25, share_s34=0.0))
        self.assertEqual(name(d), "S36_LIVE_IN_PROGRESS")
        both = {p: {"candidate": {"win": -1001, "occupy": 0}} for p in (1, 25)}
        self.assertEqual((GAMES[0]["scenario_id"], GAMES[0]["condition"]), (GAMES[24]["scenario_id"],
                                                                         GAMES[24]["condition"]))
        d = st.report(L.RULES, played(43, both))
        self.assertEqual((name(d), d["stop"]["batch"]), ("S36_SEVERE_HARM", "A2"))

    def test_final_dispositions(self):
        self.assertEqual(name(st.report(L.RULES, played(51, share_s36=0.3))), "S36_PROMISING")
        self.assertEqual(name(st.report(L.RULES, played(51, share_s36=-0.1))),
                         "S36_INCONCLUSIVE_UNFAVOURABLE_DIRECTION")
        self.assertEqual(name(st.report(L.RULES, played(51, share_s36=0.2))), "S36_INCONCLUSIVE")
        coverage = {p: {"candidate": {"win": 0, "occupy": 0}, "reference": {"win": {"min": -1000, "sd": 100.0},
                                                                            "occupy": {"min": 80}}}
                    for p in (48, 49)}
        self.assertEqual(name(st.report(L.RULES, played(51, coverage, share_s36=0.3))), "S36_SEVERE_HARM")
        held = {p: {"share": -0.5} for p in (44, 47)}
        self.assertEqual(name(st.report(L.RULES, played(51, held, share_s36=0.3))), "S36_INCONCLUSIVE")

    def test_replication_games_are_not_in_the_comparison(self):
        base = played(43, share_s36=0.0, share_s34=0.0)
        cm = copy.deepcopy(base)
        for p, f in cm.items():
            if f["tag"] == "s35":
                f["share"] = -9.0
        self.assertEqual(L.comparison(list(base.values())), L.comparison(list(cm.values())))


if __name__ == "__main__":
    unittest.main()
