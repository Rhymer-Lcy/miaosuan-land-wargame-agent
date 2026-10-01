"""The committed target-ownership design figures, checked against each other and the declared decision rule.

``problems`` closes the structural analysis's counts and recomputes the next-step decision from them; planted errors
must each be caught. The sensitivity table regenerates from public inputs everywhere; the structural analysis
regenerates byte-identically only where the private corpora exist.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / "target-ownership-design-1"
PRIVATE = ROOT / "local" / "evaluation" / "baseline-v2-residual-516-diagnostic-1"
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
DECISIONS = ("RUN PROSPECTIVE V2 PREVALENCE DIAGNOSTIC", "IMPLEMENT CANDIDATE FOR OFFLINE VALIDATION",
             "ABANDON TARGET-ALLOCATION LINE")
AUDIT_MISMATCH_SITUATIONS = 6


def total(histogram):
    return sum(histogram.values())


def decision(r):
    """The decision rule declared in docs/TARGET_OWNERSHIP_DESIGN.md before the analysis ran."""
    s1, hist = r["s1"], r["historical_mismatch_groups"]
    if hist["retained_identity_situations"] == 0 or s1["designated_owner_shoots_target"] != s1["owner_changed"]:
        return DECISIONS[2]
    if s1["by_corpus"].get("D1", 0) > 0 and r["levels"]["D1"]["games_with_a_mismatch"] >= 2:
        return DECISIONS[1]
    return DECISIONS[0]


def problems(r):
    found = []

    def expect(condition, message):
        if not condition:
            found.append(message)

    f, g, s1, hist, sit, lv = r["fidelity"], r["graph"], r["s1"], r["historical_mismatch_groups"], r["situations"], r["levels"]
    expect(r["baseline"]["policy_source_sha256"] == V2_DIGEST, "baseline identity")
    expect(f.get("consistency problems") == 0 and f.get("S1 oracle repeated runs differing") == 0, "fidelity problems")
    expect(f["D1 baseline-v2 exact"] == f["D1 decisions"] == r["decisions"]["D1"], "D1 fidelity")
    expect(f["D2 baseline-v0 exact"] == f["D2 baseline-v2 explained"] == f["D2 decisions"] == r["decisions"]["D2"], "D2 fidelity")
    expect(f["D3 baseline-v1 exact"] + f.get("D3 excluded: baseline-v1 not reproduced", 0) == f["D3 decisions"], "D3 fidelity")
    expect(r["decisions"]["D3"] == f["D3 baseline-v2 explained"], "D3 audited")
    expect(r["d1_coverage"]["captured_decisions"] == r["decisions"]["D1"] < r["d1_coverage"]["policy_seat_steps"], "D1 coverage")
    kinds = g["components_by_kind"]
    expect(total(g["components_by_kind_and_corpus"]) == total(kinds), "components by corpus")
    for kind in kinds:
        expect(sum(v for k, v in g["components_by_kind_and_corpus"].items() if k.endswith(" " + kind)) == kinds[kind],
               f"kind {kind} by corpus")
    expect(total(g["s1_shooters"]) == kinds.get("S1", 0) == s1["components"], "S1 components")
    expect(total(g["s2_shape"]) == kinds.get("S2", 0), "S2 shapes")
    expect(all(int(k) >= 2 for k in g["s1_shooters"]), "S1 has at least two shooters")
    expect(all(int(k.split()[0]) >= 2 and int(k.split(", ")[1].split()[0]) >= 2 for k in g["s2_shape"]), "S2 shape")
    expect(g["decisions_with_kind"]["S1"] <= kinds.get("S1", 0), "decisions with S1")
    expect(g["s2_with_a_collision"] == g["collision_components_by_kind"].get("S2", 0), "S2 collisions fall back")
    expect(g["collision_components_by_kind"].get("S1", 0) <= kinds.get("S1", 0), "S1 collisions")
    expect(total(g["collision_components_by_kind"]) == sit["collision_components"], "collision components")
    expect(total(s1["key"]) == s1["components"], "S1 keys")
    expect(s1["key"].get("unchanged", 0) + s1["owner_changed"] + s1["gate_precheck_failures"] == s1["components"], "S1 split")
    expect(s1["lower_attack_level_owner"] == s1["key"].get("higher attack level", 0), "lower attack level owners")
    changed = s1["owner_changed"]
    for key in ("level_gain", "former_owner_then", "designated_owner_before", "shot_delta", "changed_units",
                "earlier_non_owners", "later_non_owners", "by_corpus"):
        expect(total(s1[key]) == changed, f"S1 {key}")
    expect(s1["simple"] <= changed and s1["designated_owner_shoots_target"] <= changed, "S1 bounds")
    expect(s1["simple"] == s1["changed_units"].get("2", 0), "simple = two changed units")
    expect(all(int(k) > 0 for k in s1["level_gain"]) or s1["key"].get("weapon tie-break", 0), "level gains")
    expect(s1["games_changed"] <= s1["identity_situations_changed"] <= s1["decisions_changed"] <= changed, "S1 clustering")
    expect(s1["fingerprints_changed"] <= s1["decisions_changed"], "S1 fingerprints")
    expect(total(hist["by_kind"]) == hist["groups"], "historical groups")
    expect(hist["retained_identity_situations"] + hist["excluded_identity_situations"] == AUDIT_MISMATCH_SITUATIONS,
           "historical situations")
    expect(hist["by_kind"].get("S1", 0) == changed - s1["key"].get("weapon tie-break", 0), "retained groups = S1 changes")
    expect(total(sit["fingerprint_multiplicity"]) == sit["fingerprints"] == len(sit["table"]), "fingerprints")
    expect(sum(int(k) * v for k, v in sit["fingerprint_multiplicity"].items()) == sit["collision_components"], "occurrences")
    expect(sum(row["occurrences"] for row in sit["table"]) == sit["collision_components"], "table occurrences")
    expect(sit["repeated_fingerprints"] == sum(v for k, v in sit["fingerprint_multiplicity"].items() if int(k) > 1), "repeats")
    expect(sum(1 for row in sit["table"] if row["lower_attack_reserver"]) == sit["fingerprints_with_a_lower_attack_reserver"],
           "mismatch fingerprints")
    expect(total(sit["mismatch_fingerprints_by_kind"]) == sit["fingerprints_with_a_lower_attack_reserver"], "mismatch kinds")
    expect(sum(1 for row in sit["table"] if row["s1_owner_changed"]) == s1["fingerprints_changed"], "changed fingerprints")
    expect(sum(row["games"] for row in sit["table"]) == sit["fingerprint_game_pairs"], "fingerprint-game pairs")
    expect(sum(1 for row in sit["table"] if row["games"] > 1) == sit["fingerprints_spanning_games"], "spanning")
    expect(total(sit["fingerprints_by_kind"]) == sit["fingerprints"], "fingerprints by kind")
    expect(sum(lv[c]["groups"] for c in lv) == sit["collision_groups"], "groups by corpus")
    expect(sum(lv[c]["mismatch_groups"] for c in lv) == hist["groups"], "mismatch groups by corpus")
    expect(sum(lv[c]["identity_situations_with_mismatch"] for c in lv) == AUDIT_MISMATCH_SITUATIONS, "identity mismatch")
    expect(sum(lv[c]["games_with_a_mismatch"] for c in lv) == sit["games_with_a_lower_attack_reserver"], "mismatch games")
    for corpus, block in lv.items():
        expect(sum(block["mismatch_groups_per_affected_game"]) == block["mismatch_groups"], f"{corpus} per game")
        expect(len(block["mismatch_groups_per_affected_game"]) == block["games_with_a_mismatch"], f"{corpus} affected games")
        expect(block["games_with_a_mismatch"] <= block["games_with_a_collision"] <= block["games_in_corpus"], f"{corpus} games")
        expect((block["game_prevalence_exact_95"] is not None) == block["complete_games"], f"{corpus} interval only if complete")
    expect(decision(r) in DECISIONS, "decision")
    return found


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesignResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = json.loads((DIRECTORY / "analysis.json").read_text(encoding="utf-8"))
        cls.s = json.loads((DIRECTORY / "sensitivity.json").read_text(encoding="utf-8"))

    def test_figures_close(self) -> None:
        self.assertEqual(problems(self.r), [])

    def test_decision_follows_the_declared_rule(self) -> None:
        self.assertEqual(decision(self.r), "RUN PROSPECTIVE V2 PREVALENCE DIAGNOSTIC")

    def test_planted_errors_are_caught(self) -> None:
        plants = [("s1", "owner_changed", 1), ("s1", "simple", 1), ("s1", "components", 1), ("situations", "fingerprints", 1),
                  ("situations", "collision_components", 1), ("situations", "repeated_fingerprints", 1),
                  ("historical_mismatch_groups", "retained_identity_situations", 1), ("graph", "s2_with_a_collision", 1),
                  ("situations", "fingerprint_game_pairs", 1), ("s1", "fingerprints_changed", 1)]
        for section, key, delta in plants:
            with self.subTest(plant=f"{section}.{key}"):
                planted = copy.deepcopy(self.r)
                planted[section][key] += delta
                self.assertTrue(problems(planted))
        for path in (("graph", "components_by_kind"), ("s1", "level_gain"), ("situations", "fingerprint_multiplicity"),
                     ("historical_mismatch_groups", "by_kind")):
            with self.subTest(plant=".".join(path)):
                planted = copy.deepcopy(self.r)
                block = planted[path[0]][path[1]]
                block[sorted(block)[0]] += 1
                self.assertTrue(problems(planted))
        planted = copy.deepcopy(self.r)
        planted["levels"]["D1"]["game_prevalence_exact_95"] = [0.0, 0.1]
        self.assertTrue(problems(planted))
        planted = copy.deepcopy(self.r)
        planted["situations"]["table"][0]["occurrences"] += 1
        self.assertTrue(problems(planted))

    def test_the_decision_rule_reacts(self) -> None:
        planted = copy.deepcopy(self.r)
        planted["historical_mismatch_groups"]["retained_identity_situations"] = 0
        self.assertEqual(decision(planted), "ABANDON TARGET-ALLOCATION LINE")
        planted = copy.deepcopy(self.r)
        planted["s1"]["by_corpus"]["D1"] = 2
        planted["levels"]["D1"]["games_with_a_mismatch"] = 2
        self.assertEqual(decision(planted), "IMPLEMENT CANDIDATE FOR OFFLINE VALIDATION")

    def test_sensitivity_regenerates(self) -> None:
        self.assertEqual(load_script("ownership_sensitivity").build(), self.s)
        self.assertEqual(self.s["registered_arm_displaced_units_by_condition"], {"C1": 1143, "C2": 57, "C3": 129})
        for row in self.s["grid"]:
            needed = row["diagnostic_games_for_affected"]
            self.assertLess(int(needed["5"]), int(needed["10"]))
            self.assertLess(int(needed["10"]), int(needed["20"]))

    @unittest.skipUnless(PRIVATE.exists(), "private corpora not present")
    def test_analysis_regenerates_from_the_private_corpora(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze_ownership_design.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("analysis identical", result.stdout)


if __name__ == "__main__":
    unittest.main()
