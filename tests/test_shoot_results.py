"""The committed results of the shoot-reservation experiment, recomputed from their own public per-game values.

The registered estimates, their bootstrap intervals, the group totals and P1-P10 must follow from the
sanitized per-game metrics in results.json and from the manifest; the private records are not needed.
Public: committed files only.
"""

from __future__ import annotations

import json
import statistics
import unittest
from collections import Counter
from pathlib import Path

from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import shoot_experiment as sx

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / sx.EXPERIMENT_NAME
INSTANCE_KEYS = {"refusals", "observation", "trace_steps", "latency_us", "state_steps", "feedback_error_examples"}
GAME_KEYS = {"game_id", "group", "scenario_id", "condition", "repetition", "position", "session", "status", "values",
             "facts", "margin_fields_consistent"}


def per_config(games, group, metric, conditions=sx.ACTIVE_CONDITIONS):
    table = {}
    for game in games:
        if game["group"] == group and game["condition"] in conditions:
            table.setdefault(f"{game['scenario_id']}.{game['condition']}", []).append(game["values"][metric])
    return table


def macro(table):
    means = [statistics.fmean(v for v in values if v is not None) for values in table.values()]
    return sum(means) / len(means)


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        cls.results = json.loads((DIRECTORY / "results.json").read_text(encoding="utf-8"))
        cls.games = cls.results["games"]

    def test_the_run_is_complete_valid_and_registered(self) -> None:
        validation = self.results["validation"]
        self.assertTrue(validation["valid"] and validation["complete"], validation["problems"])
        self.assertEqual(validation["manifest_sha256"], mf.digest(self.manifest))
        self.assertEqual((validation["recorded"], validation["scheduled"]), (720, 720))
        self.assertEqual(validation["status_by_group"], {"B": {"COMPLETED": 360}, "C": {"COMPLETED": 360}})
        self.assertEqual(validation["sessions"], {"first": "0354", "last": "1073", "count": 720, "contiguous": True})
        order = validation["registration_order"]
        push = json.loads((DIRECTORY / "registration-push.json").read_text(encoding="utf-8"))
        self.assertTrue(order["verified"])
        self.assertEqual(order["registration_commit"], push["registration_commit"])
        self.assertGreater(order["minutes_between"], 0)
        self.assertEqual(validation["policy_sources_at_analysis"],
                         {g: self.manifest["groups"][g]["policy_source"]["sha256"] for g in sx.GROUPS})

    def test_games_are_the_schedule(self) -> None:
        schedule = {e["game_id"]: e for e in self.manifest["schedule"]}
        self.assertEqual(sorted(g["game_id"] for g in self.games), sorted(schedule))
        for game in self.games:
            entry = schedule[game["game_id"]]
            self.assertEqual((game["group"], game["position"], game["repetition"]),
                             (entry["group"], entry["position"], entry["repetition"]))
            self.assertEqual(set(game), GAME_KEYS, game["game_id"])
            self.assertFalse(INSTANCE_KEYS & set(game), game["game_id"])
            for name, value in game["values"].items():
                self.assertTrue(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)),
                                (game["game_id"], name))
            for item in game["facts"]:
                self.assertEqual(set(item), {"action_type", "code", "message_class", "count"})
        cells = Counter((g["scenario_id"], g["condition"], g["group"]) for g in self.games)
        self.assertEqual((len(cells), set(cells.values())), (48, {15}))

    def test_primary_estimate_follows_from_the_games(self) -> None:
        primary = self.results["primary"]
        baseline = per_config(self.games, "B", sx.PRIMARY_METRIC)
        candidate = per_config(self.games, "C", sx.PRIMARY_METRIC)
        self.assertEqual(len(baseline), 24)
        self.assertAlmostEqual(primary["baseline_mean"], macro(baseline), places=5)
        self.assertAlmostEqual(primary["candidate_mean"], macro(candidate), places=5)
        self.assertAlmostEqual(primary["delta"], macro(candidate) - macro(baseline), places=5)
        self.assertAlmostEqual(primary["relative_change"], (macro(candidate) - macro(baseline)) / macro(baseline), places=5)
        recomputed = sx.contrast(baseline, candidate, sx.PRIMARY_METRIC)
        for key in ("ci_low", "ci_high", "analytic_ci_low", "analytic_ci_high"):
            self.assertAlmostEqual(primary[key], recomputed[key], places=4, msg=key)
        verdict = sx.primary_verdict(primary)
        self.assertEqual(primary["verdict"], verdict)
        self.assertEqual(verdict["pass"], primary["ci_high"] < 0 and -primary["relative_change"] >= 0.25)

    def test_non_inferiority_follows_from_the_games(self) -> None:
        result = self.results["non_inferiority"]
        baseline = per_config(self.games, "B", sx.MARGIN_METRIC, ("C2", "C3"))
        candidate = per_config(self.games, "C", sx.MARGIN_METRIC, ("C2", "C3"))
        self.assertEqual(len(baseline), 16)
        self.assertAlmostEqual(result["delta"], macro(candidate) - macro(baseline), places=5)
        recomputed = sx.contrast(baseline, candidate, sx.MARGIN_METRIC)
        self.assertAlmostEqual(result["ci_low"], recomputed["ci_low"], places=4)
        self.assertAlmostEqual(result["ci_high"], recomputed["ci_high"], places=4)
        self.assertEqual(result["verdict"], sx.non_inferiority_verdict(result))
        self.assertEqual(result["verdict"]["pass"], result["ci_low"] > -10.0)

    def test_totals_and_mechanism_identities(self) -> None:
        totals = self.results["totals"]
        for group in sx.GROUPS:
            for name, value in totals[group].items():
                summed = sum(g["values"][name] for g in self.games if g["group"] == group and g["values"][name] is not None)
                self.assertAlmostEqual(value, summed, places=4, msg=(group, name))
            self.assertEqual(totals[group]["unique_targets_engaged"],
                             totals[group]["shots"] - totals[group]["duplicate_shoot_target_commands"])
            self.assertEqual(totals[group]["code_516"], totals[group]["code_516_repeat_fire"]
                             + totals[group]["code_516_single_fire"] + totals[group]["code_516_no_evidence"])
        c = totals["C"]
        self.assertEqual(c["reserved_target_exclusions"], c["alternate_target_redirections"] + c["fallback_occupy"]
                         + c["fallback_move"] + c["fallback_none"])
        for name in ("reserved_target_exclusions", "alternate_target_redirections", "excluded_options"):
            self.assertEqual(totals["B"][name], 0, name)

    def test_promotion_follows_mechanically(self) -> None:
        totals, criteria = self.results["totals"], self.results["promotion"]["criteria"]
        self.assertEqual(set(criteria), {f"P{i}" for i in range(1, 11)})
        expected = {
            "P2": totals["C"]["duplicate_shoot_target_commands"] == 0 and totals["C"]["replay_mismatches"] == 0,
            "P4": totals["C"]["gate_rejections"] == 0,
            "P5": totals["C"]["code_1804"] == 0 and totals["C"]["duplicate_occupation_commands"] == 0,
            "P6": self.results["primary"]["verdict"]["pass"],
            "P7": self.results["non_inferiority"]["verdict"]["pass"],
            "P8": not self.results["refusal_classes_new_in_candidate"],
        }
        for name, value in expected.items():
            self.assertEqual(criteria[name]["pass"], value, name)
        known = {tuple(c) for c in self.manifest["known_refusal_classes"]}
        baseline = {(c["action_type"], c["code"], c["message_class"]) for c in self.results["refusal_classes"]["B"]}
        new = [c for c in self.results["refusal_classes"]["C"]
               if (c["action_type"], c["code"], c["message_class"]) not in known | baseline]
        self.assertEqual(new, [])
        all_pass = all(c["pass"] for c in criteria.values())
        self.assertEqual(self.results["promotion"]["all_pass"], all_pass)
        self.assertEqual(self.results["promotion"]["disposition"],
                         "PROMOTED AS baseline-v2" if all_pass else "RETAINED AS PARTIAL/NEGATIVE CANDIDATE")


if __name__ == "__main__":
    unittest.main()
