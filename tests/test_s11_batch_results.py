"""The committed Sprint 11 offline results (``evaluation/s11-batch-allocator/``) against the claims made from them.

These tests read only the public JSON files and the checkout. Regenerating the files from the private captures is
``tests/test_real_t9_batch.py`` (server only).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "evaluation" / "s11-batch-allocator"
INVARIANTS = ("cross_objective", "prefix_failures", "invented", "unrelated_changed")


def load(name: str):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


def module(path: str):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class ReplayResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.replay = load("replay.json")
        cls.driver = module("scripts/t9_batch_replay.py")

    def test_results_belong_to_the_current_candidate_source(self) -> None:
        self.assertEqual(self.replay["candidate"]["policy_source_sha256"], self.driver.candidate_digest())
        self.assertEqual(len(self.replay["games"]), 6)
        self.assertEqual(len(self.replay["inputs"]), 6)

    def test_faithfulness_checks_ran_on_every_game(self) -> None:
        for game in self.replay["games"]:
            checks = game["checks"]
            self.assertEqual(checks["play decisions"], 2880, game["game"])
            self.assertEqual(checks["baseline ground-move count cross-checked"], 2880, game["game"])
            self.assertEqual(checks["baseline-v2 re-decided equal"], checks["candidate policy equals pure allocation"])
            self.assertGreaterEqual(checks["baseline-v2 re-decided equal"], 29)
            self.assertGreater(checks["permutation checks passed"], 0, game["game"])

    def test_every_batch_variant_keeps_the_structural_invariants(self) -> None:
        for game in self.replay["games"]:
            for name, row in game["policies"].items():
                if name in ("t9-v1",):
                    continue
                for key in INVARIANTS:
                    self.assertEqual(row.get(key, 0), 0, (game["game"], name, key))
                self.assertEqual(row.get("capacity caused", 0), 0, (game["game"], name))
            for name, row in game["design"].items():
                self.assertEqual((row.get("errors", 0), row.get("stage-rejected", 0)), (0, 0), (game["game"], name))

    def test_candidate_grants_no_place_that_cannot_be_reached(self) -> None:
        for game in self.replay["games"]:
            for name in ("candidate", "emission-order", "route-cost", "withhold-only", "stage-cap-4"):
                self.assertEqual(game["policies"][name].get("late_owners", 0), 0, (game["game"], name))
                self.assertNotIn("hold-back: a place is held by a unit that cannot arrive", game["policies"][name])
        late = {g["game"]: (g["policies"]["t9-v1"].get("late_owners", 0), g["policies"]["t9-v2"].get("late_owners", 0))
                for g in self.replay["games"]}
        self.assertEqual(late["2120531121.C3.s10-t9-v1-diagnosis.g01"], (6, 4))

    def test_t9_v1_cross_objective_moves_are_seen(self) -> None:
        for game in self.replay["games"]:
            self.assertGreater(game["policies"]["t9-v1"].get("cross_objective", 0), 0, game["game"])

    def test_control_audit(self) -> None:
        total = {}
        for game in self.replay["games"]:
            for key, value in game["control_audit"].items():
                total[key] = total.get(key, 0) + value
        self.assertEqual(total["path, speed above 0: move listed"] + total["path, speed 0: move listed"], 0)
        self.assertEqual(total["path, speed above 0: stop listed"], total["path, speed above 0: unit-decisions"])
        self.assertEqual(total["path, speed 0: stop listed"], total["path, speed 0: unit-decisions"])
        self.assertNotIn("emitted: move for a unit with an active path", total)
        self.assertNotIn("baseline-v2: move for a unit with an active path", total)
        self.assertNotIn("emitted: stop", total)
        delays = {k: v for k, v in total.items() if "delay-tau" in k}
        self.assertEqual(set(delays), {"settled: delay-tau: 0", "transition: delay-tau: 0"})
        self.assertNotIn("arrival: early", total)
        self.assertEqual(total["remaining bound: arrived sooner than the bound"], 0)
        self.assertGreater(total["remaining bound: checked"], 0)

    def test_certificate(self) -> None:
        cert = self.replay["certificate_2120531121_C3"]
        self.assertEqual(cert["objective"], "80-point objective A")
        self.assertTrue(cert["same_initial_play_state"])
        for game in cert["decision_1"].values():
            places = game["places"]
            missed = places["t9-v1"][cert["objective"]]
            self.assertEqual((missed["places"], missed["cannot_arrive_before_the_end"], missed["kinds"]),
                             (4, 4, {"infantry": 4}))
            other = places["t9-v2"]["80-point objective B"]
            self.assertEqual((other["places"], other["cannot_arrive_before_the_end"]), (4, 4))
            self.assertTrue(all(row["cannot_arrive_before_the_end"] == 0 for row in places["candidate"].values()))
            self.assertNotIn(cert["objective"], places["candidate"])
        blocked = cert["t9_v1_blocked_decisions"]["counts"]
        incumbents = [k for k in blocked if k.startswith("incumbents before the decision")]
        self.assertEqual(incumbents, ["incumbents before the decision: 0 standing, 0 movers that can arrive, "
                                      "4 that cannot"])
        self.assertEqual(blocked[incumbents[0]], blocked["decisions"])
        self.assertEqual(blocked["candidate: places granted (unit-decisions)"],
                         blocked["candidate: places granted to claimants T9-v1 held back (unit-decisions)"])
        self.assertGreater(blocked["candidate: places granted (unit-decisions)"], 0)
        self.assertEqual(blocked["candidate: a held-back claimant of the objective arrives sooner than a selected one"],
                         0)
        for name in ("t9-v1", "t9-v2", "no-end-of-game-test"):
            self.assertEqual(blocked[f"{name}: places granted (unit-decisions)"], 0)
        capturers = cert["baseline_v2_capturers"]
        self.assertEqual(capturers["counts"],
                         {"candidate at the baseline-v2 order that sent the capturer: selected": capturers["units"]})

    def test_no_identifiers_or_hexes_are_published(self) -> None:
        text = (FOLDER / "replay.json").read_text(encoding="utf-8") + (FOLDER / "prevalence.json").read_text(
            encoding="utf-8")
        for forbidden in ("obj_id", "cur_hex", "move_path", "coord", "\"owners\"", "\"held\""):
            self.assertNotIn(forbidden, text)


class PrevalenceAndMutationTest(unittest.TestCase):
    def test_prevalence_invariants_hold_on_every_seat(self) -> None:
        data = load("prevalence.json")
        self.assertEqual(len(data["games"]), 8)
        for game in data["games"]:
            self.assertEqual(len(game["seats"]), 2)
            for seat in game["seats"]:
                checks = seat["checks"]
                self.assertEqual(checks["decisions"], checks["baseline-v0 reproduced, baseline-v2 reconstructed"])
                for name in ("t9-v2", "candidate", "emission-order", "route-cost", "no-end-of-game-test"):
                    row = seat["policies"][name]
                    for key in INVARIANTS:
                        self.assertEqual(row.get(key, 0), 0, (game["game"], name, key))
                    self.assertEqual(row.get("capacity caused", 0), 0)
                self.assertEqual(seat["policies"]["candidate"].get("late_owners", 0), 0)
                self.assertEqual(seat["design"].get("errors", 0), 0)

    def test_mutation_record_matches_the_current_sources(self) -> None:
        data = load("mutation.json")
        self.assertTrue(data["unmutated_tests_pass"])
        self.assertEqual(data["killed"], data["total"])
        self.assertEqual(data["total"], len(data["mutations"]))
        self.assertGreaterEqual(data["total"], 28)
        for path, digest in data["sources"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest(), digest,
                             path)
        names = {row["mutation"] for row in data["mutations"]}
        self.assertTrue({"rank by emission order", "objective group left in emission order",
                         "staging processed in emission order", "ties broken by emission order"} <= names)


if __name__ == "__main__":
    unittest.main()
