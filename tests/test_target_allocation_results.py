"""The committed target-allocation audit, checked against its own figures and the gate declared before it ran.

``problems`` closes every count against the others and recomputes the gate and the disposition from the figures;
planted errors must each be caught. The byte-identical regeneration from the private corpora runs only where they
exist.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import allocation_audit as aa

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "evaluation" / "target-allocation-audit-1" / "audit.json"
PRIVATE = ROOT / "local" / "evaluation" / "baseline-v2-residual-516-diagnostic-1"
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
FALLBACKS = tuple(aa.FALLBACK.values())
CORPORA = ("D1", "D2", "D3")


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def total(histogram):
    return sum(histogram.values())


def problems(r):
    """Every disagreement between the audit's figures (empty when they close)."""
    found = []

    def expect(condition, message):
        if not condition:
            found.append(message)

    f, pop, own, disp, no_op = r["fidelity"], r["population"], r["ownership"], r["displaced"], r["no_op"]
    groups, units = pop["collision_groups"], pop["displaced_units"]
    expect(r["baseline"]["policy_source_sha256"] == V2_DIGEST, "baseline identity")
    for corpus in CORPORA:
        verified = {"D1": "D1 baseline-v2 exact", "D2": "D2 baseline-v2 explained", "D3": "D3 baseline-v2 explained"}[corpus]
        excluded = sum(v for k, v in f.items() if k.startswith(f"{corpus} excluded"))
        expect(f.get(verified, 0) + excluded == f.get(f"{corpus} decisions", -1), f"{corpus} fidelity closure")
        expect(r["decisions"].get(corpus, 0) == f.get(verified, 0), f"{corpus} audited decisions")
    expect(pop["collision_decisions"] == sum(r["decisions"].get(f"{c} with exclusions", 0) for c in CORPORA),
           "collision decisions")
    expect(total(pop["groups_by_corpus"]) == groups, "groups by corpus")
    expect(total(pop["displaced_by_corpus"]) == units, "displaced by corpus")
    s = r["structure"]
    for key in ("claimants_per_group", "eligible_per_group"):
        expect(total(s[key]) == groups, key)
    expect(sum(int(k) * v for k, v in s["claimants_per_group"].items()) == groups + units, "claimants = reservers + displaced")
    expect(total(s["targets_per_component"]) == s["components"], "components")
    expect(sum(int(k) * v for k, v in s["targets_per_component"].items()) == groups, "groups in components")
    expect(s["targets_per_component"].get("1", 0) == s["single_target_components"], "single-target components")
    expect(sum(v["collision groups"] for v in s["by_configuration"].values()) == groups, "groups by configuration")
    expect(sum(v["displaced units"] for v in s["by_configuration"].values()) == units, "units by configuration")
    expect(sum(v["no-op displaced units"] for v in s["by_configuration"].values()) == no_op["units"], "no-ops by configuration")
    expect(own["reserver_is_strongest_claimant"] + own["reserver_weaker_than_a_claimant"] == groups, "ownership split")
    expect(own["reserver_weaker_than_a_claimant"] == own["groups_with_stronger_displaced"], "weaker reserver = stronger displaced")
    for key in ("reserver_rank", "level_gap", "reserver_level"):
        expect(total(own[key]) == groups, key)
    expect(own["level_gap"].get("0", 0) == own["reserver_is_strongest_claimant"], "zero gap = strongest reserver")
    expect(own["reserver_rank"].get("1", 0) == own["reserver_is_strongest_claimant"], "rank 1 = strongest reserver")
    expect(total(own["stronger_displaced_fallback"]) == own["stronger_displaced_units"], "stronger displaced fallback")
    expect(own["stronger_displaced_units"] >= own["groups_with_stronger_displaced"], "stronger units >= groups")
    expect(total(disp["fallback"]) == units, "fallback total")
    expect(set(disp["fallback"]) <= set(FALLBACKS), "fallback labels")
    for label in FALLBACKS:
        expect(sum(h.get(label, 0) for h in disp["fallback_by_corpus"].values()) == disp["fallback"].get(label, 0),
               f"fallback by corpus {label}")
    expect(no_op["units"] == disp["fallback"].get("F4 no-op", 0), "no-op units")
    for key in ("shoot", "occupy", "move", "joint", "by_configuration"):
        expect(total(no_op[key]) == no_op["units"], f"no-op {key}")
    expect(no_op["move_reason_equals_trace"] <= no_op["units"], "move reason")
    expect(no_op["defects"] <= no_op["units"], "defects")
    t = r["target_outcome"]
    expect(total(t["classes"]) == groups, "outcome classes")
    expect(total(t["by_stronger_displacement"]) == groups, "outcome by stronger displacement")
    expect(total(t["by_fallback"]) == units, "outcome by fallback")
    expect(total(t["reserving_shot"]) == groups, "reserving shot")
    for label in ("T1", "T2", "T3"):
        expect(sum(v for k, v in t["by_stronger_displacement"].items() if k.startswith(label + " "))
               == t["classes"].get(label, 0), f"outcome cross-tab {label}")
    for fallback, block in r["follow_up"]["by_fallback"].items():
        for horizon in map(str, r["follow_up"]["horizons"]):
            row = block[horizon]
            expect(row["observed"] <= block["units"], f"follow-up {fallback} {horizon}")
            expect(all(v <= row["observed"] for v in row.values()), f"follow-up bounds {fallback} {horizon}")
    expect(r["follow_up"]["horizons"] == list(aa.HORIZONS), "horizons")
    red = r["redirects"]
    expect(red["units"] == disp["fallback"].get("F1 alternate shoot", 0), "redirect units")
    expect(total(red["level_drop"]) == red["units"] and total(red["outcome"]) == red["units"], "redirect totals")
    expect(red["level_drop"].get("0", 0) == red["same_level"], "same level")
    expect(sum(v for k, v in red["level_drop"].items() if int(k) > 0) == red["lower_level"], "lower level")
    o = r["oracle_b"]
    expect(o["groups"] == groups and o["owner_unchanged"] + o["owner_changed"] == groups, "oracle totals")
    expect(o["unambiguous"] + o["coupled_or_ambiguous"] == o["owner_changed"], "oracle split")
    expect(total(o["promoted_by"]) == o["owner_changed"], "promoted by")
    for key in ("promoted_level_gain", "former_owner_then", "promoted_claimant_before", "shot_delta"):
        expect(total(o[key]) == o["unambiguous"], key)
    expect(total(o["changed_units_when_coupled"]) == o["coupled_or_ambiguous"], "coupled changes")
    expect(o["promoted_by"].get("higher attack level", 0) == own["groups_with_stronger_displaced"], "promotions")
    expect(o["decisions_changed"] <= min(o["owner_changed"], pop["collision_decisions"]), "decisions changed")
    sit = r["situations"]
    expect(total(sit["occurrences_per_situation"]) == sit["distinct"], "situations")
    expect(sum(int(k) * v for k, v in sit["occurrences_per_situation"].items()) == groups, "occurrences")
    expect(total(sit["occurrences_per_stronger_situation"]) == sit["distinct_with_a_stronger_displaced_claimant"],
           "stronger situations")
    expect(sum(int(k) * v for k, v in sit["occurrences_per_stronger_situation"].items())
           >= own["groups_with_stronger_displaced"], "stronger occurrences")
    expect(sit["distinct_with_a_stronger_displaced_claimant"] <= own["groups_with_stronger_displaced"], "stronger distinct")
    expect(sit["distinct_with_a_no_op_unit"] <= no_op["units"], "no-op situations")
    expect(sit["games_with_a_stronger_displaced_claimant"] <= sit["distinct_with_a_stronger_displaced_claimant"], "games")
    expect(total(sit["steps_between_recurrences"]) == groups - sit["distinct"], "recurrences")
    recorded = sit["recorded_trajectory_next_step"]
    expect(total(recorded) == groups, "recorded trajectory")
    for corpus in CORPORA:
        expect(sum(v for k, v in recorded.items() if k.startswith(corpus + " "))
               == pop["groups_by_corpus"].get(corpus, 0), f"recorded trajectory {corpus}")
    expect(sum(v for k, v in recorded.items() if k.endswith("| stronger displaced")) == own["groups_with_stronger_displaced"],
           "recorded trajectory, stronger displaced")
    gate = list(r["gate"].values())
    stronger = own["groups_with_stronger_displaced"]
    scenarios = {c.split()[0] for c, v in s["by_configuration"].items() if v["groups with a stronger displaced claimant"]}
    expected = [groups >= aa.MIN_GROUPS, stronger >= 10 and 10 * stronger >= groups, len(scenarios) >= 2, True,
                f.get("O-B repeated runs differing", 0) == 0, o["decisions_changed"] >= 10,
                o["owner_changed"] > 0 and 2 * o["unambiguous"] >= o["owner_changed"],
                f.get("reconstruction inconsistencies", 0) == 0 and no_op["defects"] == 0]
    expect(len(gate) == 8, "gate size")
    for index, value in enumerate(expected[:len(gate)]):
        expect(gate[index] == value, f"gate G{index}")
    disposition = ("BLOCKED BY INSUFFICIENT REPLAY EVIDENCE" if not gate[0] else
                   "DESIGN TARGET-ALLOCATION CANDIDATE" if all(gate) else "NO TARGET-ALLOCATION EXPERIMENT JUSTIFIED")
    expect(r["disposition"] == disposition, "disposition")
    return found


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = json.loads(RESULT.read_text(encoding="utf-8"))

    def test_figures_close(self) -> None:
        self.assertEqual(problems(self.r), [])

    def test_registered_arm_context(self) -> None:
        driver = load_script("audit_target_allocation")
        self.assertEqual(self.r["registered_arm"], driver.registered_arm())
        self.assertEqual(self.r["registered_arm"]["totals"],
                         {"F1 alternate shoot": 840, "F2 occupy": 17, "F3 move": 12, "F4 no-op": 460})

    def test_planted_errors_are_caught(self) -> None:
        plants = [("population", "collision_groups", 1), ("population", "displaced_units", 1),
                  ("ownership", "groups_with_stronger_displaced", 1), ("ownership", "reserver_is_strongest_claimant", -1),
                  ("no_op", "units", 1), ("no_op", "defects", 1), ("redirects", "same_level", 1),
                  ("oracle_b", "unambiguous", 1), ("oracle_b", "decisions_changed", 10), ("structure", "components", 1),
                  ("situations", "distinct", 1), ("situations", "distinct_with_a_stronger_displaced_claimant", 1)]
        for section, key, delta in plants:
            with self.subTest(plant=f"{section}.{key}"):
                planted = copy.deepcopy(self.r)
                planted[section][key] += delta
                self.assertTrue(problems(planted))
        for section, key in (("displaced", "fallback"), ("target_outcome", "classes"), ("ownership", "level_gap"),
                             ("situations", "steps_between_recurrences"), ("situations", "recorded_trajectory_next_step")):
            with self.subTest(plant=f"{section}.{key} histogram"):
                planted = copy.deepcopy(self.r)
                first = sorted(planted[section][key])[0]
                planted[section][key][first] += 1
                self.assertTrue(problems(planted))
        planted = copy.deepcopy(self.r)
        planted["disposition"] = next(d for d in ("DESIGN TARGET-ALLOCATION CANDIDATE",
                                                  "NO TARGET-ALLOCATION EXPERIMENT JUSTIFIED") if d != self.r["disposition"])
        self.assertTrue(problems(planted))
        planted = copy.deepcopy(self.r)
        planted["fidelity"]["D1 decisions"] += 1
        self.assertTrue(problems(planted))

    @unittest.skipUnless(PRIVATE.exists(), "private corpora not present")
    def test_regenerates_from_the_private_corpora(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_target_allocation.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("audit identical", result.stdout)


if __name__ == "__main__":
    unittest.main()
