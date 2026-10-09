"""Sprint 28 registration and result binding (``evaluation/s28-t12-o1/``).

* The committed ``protocol.json`` equals a fresh derivation: every frozen source is unchanged since the registration
  (this pin is deliberately not among the mutation tests, so mutants are judged by behaviour).
* After the run: the disposition is the registered rule applied to the committed public rows (the opportunity stop and
  the legality gate recomputed from the side summaries, the interaction criteria from ``episodes-*.json``); the pooled
  tables are sums of the side rows; every fidelity anchor holds or the disposition is invalid; no public file carries a
  forbidden key, a small private-like identifier or a digit-only word other than a scenario identifier; every side
  reports zero unexplained action differences; the certificates agree with the side summaries; the damage summary is
  the count of the damage rows.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s28_t12 as st

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / st.STUDY_ID
SPEC = importlib.util.spec_from_file_location("s28_driver_results", ROOT / "scripts" / "s28_t12.py")
drv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drv)
PARTIAL = ("no_destination_left", "no_admissible_destination")


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(prefix: str):
    return [r for p in sorted(OUT.glob(f"{prefix}*.json")) for r in json.loads(p.read_text(encoding="utf-8"))["rows"]]


class ProtocolPinTest(unittest.TestCase):
    def test_protocol_matches_the_frozen_sources(self) -> None:
        self.assertEqual((OUT / "protocol.json").read_text(encoding="utf-8"), drv.dump(drv.protocol()))


@unittest.skipUnless((OUT / "disposition.json").exists() and (OUT / "census.json").exists(), "the study has not run")
class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.disposition, cls.census, cls.divergence, cls.fidelity = (load("disposition.json"), load("census.json"),
                                                                     load("divergence.json"), load("fidelity.json"))
        cls.rows = {pop: rows(f"episodes-{pop}") for pop in ("H0", "HH")}
        cls.damage = rows("damage")
        cls.sides = rows("sides")

    def test_episode_rows_match_the_side_summaries(self) -> None:
        self.assertEqual(len(self.sides), 20)
        for pop in ("H0", "HH"):
            by_side = {s["side_game"]: s["legal_episodes"] for s in self.sides if s["population"] == pop}
            got = {k: sum(1 for r in self.rows[pop] if r["side_game"] == k) for k in by_side}
            self.assertEqual(got, by_side, pop)

    def test_stops_recomputed_from_the_side_summaries(self) -> None:
        stops = self.disposition["stops"]
        hh = {s["side_game"]: s["trigger_episodes"] for s in self.sides if s["population"] == "HH"}
        self.assertEqual(stops["opportunity_stop"]["trigger_episodes_by_hh_side_game"], hh)
        self.assertEqual(stops["opportunity_stop"]["met"], len(hh) != 4 or any(n < 1 for n in hh.values()))
        legal = {s["side_game"]: s["legal_episodes"] for s in self.sides if s["population"] == "HH"}
        self.assertEqual(stops["legality_gate"]["legal_episodes_by_hh_side_game"], legal)
        self.assertEqual(stops["legality_gate"]["met"], len(legal) != 4 or any(n < 1 for n in legal.values()))
        h0 = {s["side_game"]: s["trigger_episodes"] for s in self.sides if s["population"] == "H0"}
        self.assertEqual(stops["h0_readings"]["trigger_episodes_by_h0_side_game"], h0)
        self.assertEqual(stops["h0_readings"]["average_reading_met"], sum(h0.values()) < len(h0))

    def test_interaction_recomputed_from_the_episode_rows(self) -> None:
        inter = self.disposition["interaction"]
        groups = {"HH": self.rows["HH"], "H0": self.rows["H0"], "pooled": self.rows["H0"] + self.rows["HH"]}
        for name, part in groups.items():
            counted = [r for r in part if r["counted_as_distinct"]]
            units = [u for r in counted for u in r["dispersed"]]
            claim = sum(1 for u in units if u.get("claimant"))
            holder = sum(1 for r in counted if r["holder_ordered_off_while_held"])
            partial = sum(1 for r in counted if any(o in PARTIAL for o, _ in r["outcomes"]))
            got = inter[name]
            self.assertEqual((got["distinct_legal_episodes"], got["dispersed_units"], got["claimant_units"],
                              got["episodes_holder_ordered_off_while_held"], got["episodes_partial_dispersion"]),
                             (len(counted), len(units), claim, holder, partial), name)
            self.assertEqual(got["I1_tactical_isolation"], bool(units) and 2 * claim > len(units))
            self.assertEqual(got["I2_holder_ordered_off"], bool(counted) and 2 * holder > len(counted))
            self.assertEqual(got["I3_partial_dispersion"], bool(counted) and 2 * partial > len(counted))

    def test_disposition_is_the_rule(self) -> None:
        unexplained = sum(s["unexplained_action_differences"] for s in self.sides)
        integrity = all(all(s["integrity"].values()) for s in self.sides) and all(self.fidelity["side_integrity"].values())
        verdict = st.disposition(self.fidelity["ok"], integrity, unexplained, self.disposition["stops"],
                                 self.disposition["interaction"])
        self.assertEqual({k: self.disposition[k] for k in verdict}, verdict)
        self.assertEqual(unexplained, 0)

    def test_fidelity(self) -> None:
        self.assertEqual(self.fidelity["ok"], all(a["equal"] for a in self.fidelity["anchors"].values())
                         and all(self.fidelity["blocks"].values()) and all(self.fidelity["side_integrity"].values()))
        self.assertEqual((len(self.fidelity["anchors"]), len(self.fidelity["blocks"]), len(self.fidelity["side_integrity"])),
                         (18, 10, 20))

    def test_pooled_tables_are_sums_of_the_sides(self) -> None:
        for pop in ("H0", "HH"):
            sides = [s for s in self.sides if s["population"] == pop]
            self.assertEqual(self.census[pop]["legal_episodes"], sum(s["legal_episodes"] for s in sides))
            self.assertEqual(self.census[pop]["trigger_episodes"], sum(s["trigger_episodes"] for s in sides))
            for block, values in self.census[pop]["census"].items():
                for key, value in values.items():
                    if isinstance(value, int):
                        self.assertEqual(value, sum(s["census"][block].get(key, 0) for s in sides), (block, key))
        self.assertEqual(self.census["pooled"]["legal_episodes"], len(self.rows["H0"]) + len(self.rows["HH"]))

    def test_certificates_agree_with_the_sides(self) -> None:
        firsts = {s["side_game"]: s["first_divergence"] for s in self.sides}
        certs = {c["side_game"]: c for c in self.divergence["certificates"]}
        self.assertEqual(set(certs), {k for k, v in firsts.items() if v is not None})
        for name, c in certs.items():
            self.assertEqual((c["decision"], c["step"], c["prefix_supported"]),
                             (firsts[name]["decision"], firsts[name]["step"], firsts[name]["prefix_supported"]))
            for key in ("holder_retained", "only_registered_moves_added", "baseline_actions_preserved",
                        "no_baseline_action_for_dispersed_units", "objective_held"):
                self.assertTrue(c[key], (name, key))

    def test_damage_summary_counts_the_rows(self) -> None:
        summary = load(sorted(p.name for p in OUT.glob("damage*.json"))[0])["summary"]
        for pop in ("H0", "HH"):
            part = [r for r in self.damage if r["population"] == pop]
            self.assertEqual(summary[pop]["stationary_on_objective_ground_events"], len(part))
            self.assertEqual(summary[pop]["stacked"], sum(1 for r in part if r["stacked"]))
            self.assertEqual(summary[pop]["stacked_held_with_an_earlier_legal_dispersal"],
                             sum(1 for r in part if r["stacked"] and r["held"] and r["earlier_legal"]))

    def test_no_forbidden_key_small_id_or_digit_word(self) -> None:
        names = [p.name for p in OUT.glob("*.json") if p.name not in ("protocol.json", "inputs.json", "mutation.json")]
        self.assertGreaterEqual(len(names), 7)
        scenarios = {s["scenario_side"].split()[0] for s in self.sides}
        for name in names:
            self.assertEqual(st.public_problems(load(name), range(50)), [], name)
            self.assertEqual(st.digit_words(load(name), scenarios), [], name)


if __name__ == "__main__":
    unittest.main()
