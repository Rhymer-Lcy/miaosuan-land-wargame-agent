"""Sprint 30 committed results (``evaluation/s30-t13-k1/``) bound to the frozen rules (``docs/SPRINT30_T13_K1_PILOT.md``).

Checked: the preflight's inputs are the committed ones; its disposition, reasons and inert selection follow from its
own public rows by the frozen rule (``s30_preflight.disposition``) and are ``K1_PREFLIGHT_INADEQUATE`` with no inert
configuration; every fidelity anchor holds; the population tallies equal the sums of the side rows; the controls are
internally consistent; and, because the preflight stopped the pilot, no run card or manifest names the candidate and
only the preflight's own files import it.
"""

from __future__ import annotations

import collections
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import s30_preflight as pf
from miaosuan_agent.experiments import t13_keep_one_k1 as k1

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s30-t13-k1"


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreflightResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = load("preflight.json")

    def test_inputs_and_anchors(self) -> None:
        self.assertEqual(self.result["inputs_sha256"], sha256(OUT / "preflight-inputs.json"))
        self.assertEqual(self.result["engine_sessions"], 0)
        self.assertTrue(all(a["equal"] for a in self.result["fidelity"].values()))
        for name, value in pf.ANCHORS.items():
            self.assertEqual(self.result["fidelity"][name]["preflight"], value)

    def test_the_disposition_follows_from_the_rows(self) -> None:
        sides = self.result["sides"]
        verdict = pf.disposition(all(a["equal"] for a in self.result["fidelity"].values()), sides)
        self.assertEqual({k: self.result[k] for k in ("disposition", "reasons", "inert_configurations")}, verdict)
        self.assertEqual(verdict["disposition"], "K1_PREFLIGHT_INADEQUATE")
        self.assertEqual(verdict["inert_configurations"], [])
        self.assertEqual(sum(s["verified_opportunity"] for s in sides), 0)
        self.assertEqual(sum(s["independent_check_findings"] for s in sides), 0)
        self.assertEqual(collections.Counter(s["population"] for s in sides), {"H0": 16, "HH": 4, "HI": 3})

    def test_population_tallies_are_the_side_sums(self) -> None:
        for population, pooled in self.result["populations"].items():
            sides = [s for s in self.result["sides"] if s["population"] == population]
            outcomes: collections.Counter = collections.Counter()
            for s in sides:
                outcomes.update(s["outcomes"])
            self.assertEqual(pooled["objective_decision_outcomes"], dict(outcomes))
            self.assertEqual(pooled["departure_episodes"], sum(s["departure_episodes"]["count"] for s in sides))
            self.assertEqual(pooled["departure_episodes_with_a_withholding"],
                             sum(s["departure_episodes"]["with_a_withholding"] for s in sides))
            self.assertEqual(pooled["side_games"], len(sides))

    def test_controls_are_consistent(self) -> None:
        controls = load("controls.json")
        self.assertEqual(controls["inputs_sha256"], sha256(OUT / "preflight-inputs.json"))
        self.assertEqual(len(controls["configurations"]), 5)
        for row in controls["configurations"].values():
            self.assertEqual(row["games"], 15)
            for name in ("occupy", "attack", "remain", "total", "margin"):
                values = row[name]["values"]
                self.assertEqual((len(values), values, row[name]["min"], row[name]["max"]),
                                 (15, sorted(values), min(values), max(values)))
                mean = Fraction(sum(values), 15)
                self.assertEqual(row[name]["mean"], mean.numerator if mean.denominator == 1 else
                                 f"{mean.numerator}/{mean.denominator}")
            self.assertEqual(row["occupy_constant"], row["occupy"]["min"] == row["occupy"]["max"])


class WhitelistTest(unittest.TestCase):
    def test_no_run_card_names_the_candidate(self) -> None:
        """The preflight stopped the pilot before a card was registered: the identity ``t13-keep-one-k1`` appears in
        no run card or manifest, and any evaluation file naming it lies in ``evaluation/s30-t13-k1/``."""
        for path in sorted((ROOT / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if k1.CANDIDATE_ID not in text:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = json.loads(text)
            self.assertFalse(isinstance(data, dict) and xp.is_card(data), rel)
            self.assertNotEqual(path.name, "manifest.json", rel)
            self.assertTrue(rel.startswith("evaluation/s30-t13-k1/"), rel)

    def test_only_the_preflight_imports_the_candidate(self) -> None:
        users = sorted(p.relative_to(ROOT).as_posix() for folder in ("src", "scripts")
                       for p in (ROOT / folder).rglob("*.py")
                       if "t13_keep_one_k1" in p.read_text(encoding="utf-8") and p.name != "t13_keep_one_k1.py")
        self.assertEqual(users, ["scripts/mutate_s30.py", "scripts/s30_preflight.py",
                                 "src/miaosuan_agent/evaluation/s30_preflight.py"])
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "run_evaluation.py"):
            self.assertNotIn("t13_keep_one_k1", (ROOT / "scripts" / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
