"""E3b configuration search (``t7-e3b-search-1``): consistency of the committed public outputs (no private data)."""

from __future__ import annotations

import collections
import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "evaluation" / "t7-e3b-search-1"
FILES = ("inputs", "validation", "search", "certificates", "crosscheck", "decision", "posthoc", "mutation")


def load(name):
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def search_module():
    spec = importlib.util.spec_from_file_location("t7_e3b_search", REPO / "scripts" / "t7_e3b_search.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Outputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.j = {name: load(name) for name in FILES}

    def test_every_dataset_of_the_protocol_was_searched_and_cross_checked(self):
        expected = {"A-b", "A-pb1", "A-pb2", "B-c", "B-p2", "B-r516", "B-smoke", "C-h0"}
        self.assertEqual(set(self.j["search"]["datasets"]), expected)
        self.assertEqual(set(self.j["crosscheck"]["datasets"]), expected)
        frozen = {ds["id"] for ds in self.j["inputs"]["datasets"]}
        self.assertEqual(frozen, expected | {"K-pa", "K-pb1", "K-pb2"})

    def test_the_frozen_identities_are_the_registered_ones(self):
        ids = self.j["inputs"]["identities"]
        for name in ("baseline-v2-candidate-shoot-target-reservation", "t7-idle-concealment", "tactic-deployment-split-1"):
            self.assertEqual(ids[name]["registered"], ids[name]["recomputed"], name)
        self.assertEqual(ids["t7-idle-concealment"]["registered"],
                         "6b73c39ad785938cc1c54b72065858fbf6460a66ceebae627bad4e99fa1a50f0")
        digests = [e["sha256"] for ds in self.j["inputs"]["datasets"] for g in ds.get("games", ())
                   for e in g["files"].values()]
        self.assertEqual(len(digests), 3 * (3 + 2 + 3 + 32 + 8))

    def test_the_known_answer_validation(self):
        v = self.j["validation"]
        self.assertTrue(v["passed"])
        self.assertEqual((v["orders"], v["units"]), (16, 16))
        for seat in v["seats"].values():
            self.assertEqual(seat["classes"], {"DT during the transition": seat["recorded_orders"]})
            self.assertEqual(seat["d"], [1])
            self.assertTrue(seat["orders_equal"] and seat["pool_predicate_equal"])

    def test_classes_sum_and_agree_with_the_cross_check(self):
        for ds, data in self.j["search"]["datasets"].items():
            cross = self.j["crosscheck"]["datasets"][ds]
            if "summary" in data:
                s = data["summary"]
                ours = {"unconditional": s["unconditional"], "conditional": s["conditional"]}
                self.assertEqual(sum(s["unconditional"].values()) + sum(s["conditional"].values()), s["episodes"], ds)
            else:
                ours = data["classes"]
            self.assertEqual(ours, cross["classes"], ds)
            self.assertEqual(data["W_categories"], cross["W_categories"], ds)

    def test_certificates_match_the_witness_count(self):
        certificates = self.j["certificates"]["certificates"]
        by = collections.Counter(f"{c['category']} {'conditional' if c['conditional_on'] else 'unconditional'}"
                                 for c in certificates)
        self.assertEqual(dict(by), self.j["search"]["W_episodes_by_category"])
        for c in certificates:
            self.assertGreaterEqual(c["observed_historical_facts"]["interval_d"], 75)
            self.assertEqual(set(c) >= {"observed_historical_facts", "offline_replay_decisions",
                                        "hypothetical_consequences"}, True)
            self.assertNotIn("unit", c)

    def test_the_decision_follows_from_the_committed_outputs(self):
        module = search_module()
        self.assertEqual(module.decide(), self.j["decision"])
        d = self.j["decision"]
        self.assertEqual(d["disposition"], "E3B_CONFIGURATION_UNCERTAIN")
        self.assertEqual(self.j["search"]["feasible_configurations"], 0)

    def test_the_two_leads(self):
        leads = self.j["search"]["leads"]
        self.assertEqual(len(leads), 2)
        self.assertEqual(sorted(l["is_move_or_direct_fire_by_baseline_v2"] for l in leads), [False, True])
        for l in leads:
            self.assertNotIn("unit", l)
            self.assertNotIn("game", l)

    def test_posthoc_is_labelled_and_the_instrument_saw_commands(self):
        p = self.j["posthoc"]
        self.assertTrue(p["status"].startswith("POST HOC"))
        for ds, x in p["instrument_control"].items():
            self.assertGreater(x["commands_to_ground_units"], 0, ds)
            self.assertLessEqual(self.j["search"]["datasets"][ds]["D2"]["runs"],
                                 x["commands_after_an_idle_run_of_at_least_75"], ds)

    def test_mutation_results(self):
        m = self.j["mutation"]
        self.assertEqual(m["killed"] + sum(1 for r in m["mutations"] if not r["killed"]), m["total"])
        self.assertTrue(all(r["killed"] or r["reason_if_surviving"] for r in m["mutations"]))


if __name__ == "__main__":
    unittest.main()
