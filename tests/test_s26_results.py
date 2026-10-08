"""Sprint 26 registration and result binding (``evaluation/s26-t6s-shadow/``).

* The committed ``protocol.json`` equals a fresh derivation: every frozen source is unchanged since the registration
  (this pin is deliberately not among the mutation tests, so mutants are judged by behaviour).
* After the run: the disposition is the registered rule applied to the committed public rows (stops A, B and C
  recomputed from ``episodes-*.json`` and the side summaries); the pooled tables are sums of the side rows; every
  fidelity anchor holds or the disposition is invalid; no public file carries a forbidden key, a small private-like
  identifier or a digit-only word other than a scenario identifier; every side reports zero unexplained action
  differences; the certificates agree with the side summaries.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s26_t6s as st

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / st.STUDY_ID
SPEC = importlib.util.spec_from_file_location("s26_driver_results", ROOT / "scripts" / "s26_t6s.py")
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
        cls.disposition, cls.census, cls.divergence, cls.fidelity = (load("disposition.json"), load("census.json"),
                                                                     load("divergence.json"), load("fidelity.json"))
        cls.rows = {}
        for pop in ("H0", "HH"):
            parts = sorted(OUT.glob(f"episodes-{pop}*.json"))
            cls.rows[pop] = [r for p in parts for r in json.loads(p.read_text(encoding="utf-8"))["rows"]]
        cls.sides = cls.census["sides"]

    def test_episode_rows_match_the_side_summaries(self) -> None:
        self.assertEqual(len(self.sides), 20)
        for pop in ("H0", "HH"):
            by_side = {s["side_game"]: s["episodes"] for s in self.sides if s["population"] == pop}
            got = {k: sum(1 for r in self.rows[pop] if r["side_game"] == k) for k in by_side}
            self.assertEqual(got, by_side, pop)

    def test_stops_recomputed_from_the_public_rows(self) -> None:
        stops = self.disposition["stops"]
        hh = {s["side_game"]: s["episodes"] for s in self.sides if s["population"] == "HH"}
        a = stops["A_hh_opportunity"]
        self.assertEqual(a["episodes_by_hh_side_game"], hh)
        self.assertEqual(a["met"], len(hh) != 4 or any(n < 10 for n in hh.values()))
        h0_sides = {r["scenario_side"] for r in self.rows["H0"]}
        b = stops["B_h0_generality"]
        self.assertEqual((b["h0_scenario_sides_with_an_episode"], b["met"]), (len(h0_sides), len(h0_sides) < 4))
        everything = self.rows["H0"] + self.rows["HH"]
        counted = [r for r in everything if r["counted_in_stop_c"]]
        risk = sum(1 for r in counted if r["first_owner_risk_in_any_replica"])
        c = stops["C_onward_capture_conflict"]
        self.assertEqual((c["episodes_raw"], c["episodes_distinct"], c["first_owner_risk_episodes"]),
                         (len(everything), len(counted), risk))
        self.assertEqual(c["met"], not counted or 2 * risk > len(counted))
        for r in everything:
            self.assertEqual(r["first_owner_risk"], any(f["first_owner"] for f in r["followers"]))

    def test_disposition_is_the_rule(self) -> None:
        unexplained = sum(s["unexplained_action_differences"] for s in self.sides)
        integrity = all(all(s["integrity"].values()) for s in self.sides)
        verdict = st.disposition(self.fidelity["ok"], integrity, unexplained, self.disposition["stops"])
        self.assertEqual({k: self.disposition[k] for k in verdict}, verdict)
        self.assertEqual(unexplained, 0)

    def test_fidelity(self) -> None:
        self.assertEqual(self.fidelity["ok"], all(a["equal"] for a in self.fidelity["anchors"].values())
                         and all(self.fidelity["blocks"].values()) and all(self.fidelity["side_integrity"].values()))
        self.assertEqual((len(self.fidelity["anchors"]), len(self.fidelity["blocks"]), len(self.fidelity["side_integrity"])),
                         (27, 8, 20))

    def test_pooled_tables_are_sums_of_the_sides(self) -> None:
        for pop in ("H0", "HH"):
            sides = [s for s in self.sides if s["population"] == pop]
            self.assertEqual(self.census[pop]["episodes"], sum(s["episodes"] for s in sides))
            for key in self.census[pop]["census"]:
                self.assertEqual(self.census[pop]["census"][key], sum(s["census"].get(key, 0) for s in sides), key)
            for key in self.census[pop]["exposure"]:
                self.assertEqual(self.census[pop]["exposure"][key], sum(s["exposure"].get(key, 0) for s in sides), key)
        self.assertEqual(self.census["pooled"]["episodes"], len(self.rows["H0"]) + len(self.rows["HH"]))

    def test_certificates_agree_with_the_sides(self) -> None:
        firsts = {s["side_game"]: s["first_divergence"] for s in self.sides}
        certs = {c["side_game"]: c for c in self.divergence["certificates"]}
        self.assertEqual(set(certs), {k for k, v in firsts.items() if v is not None})
        for name, c in certs.items():
            self.assertEqual((c["decision"], c["step"], c["prefix_supported"]),
                             (firsts[name]["decision"], firsts[name]["step"], firsts[name]["prefix_supported"]))
            self.assertTrue(c["only_follower_moves_withheld"] and c["leader_moves_kept"] and c["unrelated_actions_unchanged"])

    def test_no_forbidden_key_small_id_or_digit_word(self) -> None:
        names = [p.name for p in OUT.glob("*.json") if p.name not in ("protocol.json", "inputs.json", "mutation.json")]
        self.assertGreaterEqual(len(names), 7)
        scenarios = {s["scenario_side"].split()[0] for s in self.sides}
        for name in names:
            self.assertEqual(st.public_problems(load(name), range(50)), [], name)
            self.assertEqual(st.digit_words(load(name), scenarios), [], name)


if __name__ == "__main__":
    unittest.main()
