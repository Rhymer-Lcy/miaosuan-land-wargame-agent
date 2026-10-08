"""Sprint 25 registration and result binding (``evaluation/s25-t13-d1/``).

* The committed ``protocol.json`` equals a fresh derivation: every frozen source is unchanged since the registration
  (this pin is deliberately not among the mutation tests, so mutants are judged by behaviour).
* After the run: the disposition is the registered rule applied to the committed public rows (stops A, B and C
  recomputed from ``losses-*.json``); the pooled tables are the sums of the side rows; every fidelity anchor holds or
  the disposition is invalid; no public file carries a forbidden key; every side reports zero unexplained action
  differences.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s25_t13 as st

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / st.STUDY_ID
SPEC = importlib.util.spec_from_file_location("s25_driver_results", ROOT / "scripts" / "s25_t13_d1.py")
drv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drv)


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


class ProtocolPinTest(unittest.TestCase):
    def test_protocol_matches_the_frozen_sources(self) -> None:
        self.assertEqual((OUT / "protocol.json").read_text(encoding="utf-8"), drv.dump(drv.protocol()))


@unittest.skipUnless((OUT / "disposition.json").exists(), "the study has not run")
class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.disposition, cls.anatomy, cls.shadow, cls.fidelity = (load("disposition.json"), load("anatomy.json"),
                                                                  load("shadow.json"), load("fidelity.json"))
        cls.rows = {}
        for pop in ("H0", "HH"):
            parts = sorted(OUT.glob(f"losses-{pop}*.json"))
            cls.rows[pop] = [r for p in parts for r in json.loads(p.read_text(encoding="utf-8"))["rows"]]

    def test_loss_rows_are_complete(self) -> None:
        self.assertEqual({p: len(r) for p, r in self.rows.items()}, {"H0": 40, "HH": 26})
        for pop, rows in self.rows.items():
            self.assertTrue(all(r["population"] == pop and r["v_class"] in st.V_CLASSES
                                and r["category"] in st.CATEGORIES for r in rows))

    def test_stops_recomputed_from_the_public_rows(self) -> None:
        stops = self.disposition["stops"]
        everything = self.rows["H0"] + self.rows["HH"]
        for name, rows in (("H0", self.rows["H0"]), ("HH", self.rows["HH"]), ("pooled", everything)):
            v = sum(1 for r in rows if r["v_class"] == st.V_ORDER)
            a = stops["A_departure_not_dominant"]["by_population"][name]
            self.assertEqual((a["v_order"], a["losses"], a["met"]), (v, len(rows), not rows or 2 * v < len(rows)))
        self.assertEqual(stops["A_departure_not_dominant"]["met"],
                         any(i["met"] for i in stops["A_departure_not_dominant"]["by_population"].values()))
        touched = [r for r in everything if r["category"] == st.TOUCHED]
        counted = [r for r in touched if r["counted_in_stops_b_and_c"]]
        self.assertFalse(any(r["counted_in_stops_b_and_c"] for r in everything if r["category"] != st.TOUCHED))
        b = stops["B_insufficient_actionable_coverage"]
        sides = {r["scenario_side"] for r in counted}
        self.assertEqual((b["touched_raw"], b["touched_distinct"], b["distinct_scenario_sides"]),
                         (len(touched), len(counted), len(sides)))
        self.assertEqual(b["met"], len(counted) < 4 or len(sides) < 2)
        c = stops["C_onward_capture_interference"]
        risk = sum(1 for r in counted if r["departure"]["onward"]["first_owner"])
        self.assertEqual((c["first_owner"], c["touched_distinct"], c["met"]),
                         (risk, len(counted), not counted or 2 * risk > len(counted)))

    def test_disposition_is_the_rule(self) -> None:
        sides = self.shadow["sides"]
        unexplained = sum(s["unexplained_action_differences"] for s in sides)
        integrity = all(all(s["integrity"].values()) for s in sides)
        verdict = st.disposition(self.fidelity["ok"], integrity, unexplained, self.disposition["stops"])
        self.assertEqual({k: self.disposition[k] for k in verdict}, verdict)
        self.assertEqual(unexplained, 0)

    def test_fidelity(self) -> None:
        self.assertEqual(self.fidelity["ok"], all(a["equal"] for a in self.fidelity["anchors"].values())
                         and all(self.fidelity["blocks"].values()) and all(self.fidelity["side_integrity"].values()))
        self.assertEqual(len(self.fidelity["anchors"]), 12)

    def test_pooled_tables_are_sums_of_the_sides(self) -> None:
        for pop in ("H0", "HH"):
            sides = [s for s in self.anatomy["sides"] if s["population"] == pop]
            for c in st.V_CLASSES:
                self.assertEqual(self.anatomy[pop]["by_v_class"][c]["events"], sum(s["v_classes"][c] for s in sides))
            for c in st.CATEGORIES:
                self.assertEqual(self.anatomy[pop]["by_category"][c]["events"], sum(s["categories"][c] for s in sides))
            self.assertEqual(self.anatomy[pop]["losses"]["events"], len(self.rows[pop]))
        self.assertEqual(self.anatomy["pooled"]["losses"]["events"], 66)

    def test_no_forbidden_key_or_small_id_word(self) -> None:
        names = [p.name for p in OUT.glob("*.json") if p.name not in ("protocol.json", "inputs.json", "mutation.json")]
        self.assertGreaterEqual(len(names), 6)
        for name in names:
            self.assertEqual(st.public_problems(load(name), range(50)), [], name)


if __name__ == "__main__":
    unittest.main()
