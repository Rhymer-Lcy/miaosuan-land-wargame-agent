"""Sprint 19: the committed public files of the T6-G shadow study (no private data needed).

The protocol and inputs are bound to the frozen sources and to Sprint 18's pins; the result files, once present, are
bound to each other: the disposition is recomputed from the public per-side-game figures by the frozen rule.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s19_t6g as st
from miaosuan_agent.experiments import t6_threat_entry_gate as tg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s19-t6g-shadow"
S18 = ROOT / "evaluation" / "s18-frontier-reset"
RESULTS = ("fidelity.json", "shadow.json", "certificates.json", "objectives.json", "disposition.json")


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProtocolTest(unittest.TestCase):
    def test_protocol_matches_the_frozen_modules(self) -> None:
        p = load("protocol.json")
        g = p["gate"]
        self.assertEqual((g["route_prefix"], g["hold_limit_steps"], g["cooldown_steps"]), (5, 150, 300))
        self.assertEqual((tg.ROUTE_PREFIX, tg.HOLD_LIMIT, tg.COOLDOWN), (5, 150, 300))
        self.assertEqual((p["opportunity"]["minimum_per_hh_side_game"], p["opportunity"]["hh_side_games"]), (10, 4))
        self.assertEqual(p["damage_windows_steps"], [75, 150, 300])
        self.assertEqual(p["dispositions_first_match"], list(st.DISPOSITIONS))
        self.assertEqual(p["engine_sessions"], 0)
        for path, digest in p["sources"].items():
            normalised = hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertEqual(normalised, digest, path)
        self.assertEqual(len(p["sources"]), 7)

    def test_inputs_are_sprint_18_pins(self) -> None:
        i = load("inputs.json")
        s18 = json.loads((S18 / "inputs.json").read_text(encoding="utf-8"))
        self.assertEqual((i["H0"], i["HH"]), (s18["H0"], s18["HH"]))
        self.assertEqual((len(i["H0"]["games"]), len(i["HH"]["games"])), (8, 4))
        self.assertEqual(i["sprint18_inputs"]["sha256"], sha256(S18 / "inputs.json"))
        self.assertEqual(i["sprint18_census"]["sha256"], sha256(S18 / "census.json"))

    def test_anchors_are_the_published_census_figures(self) -> None:
        census = json.loads((S18 / "census.json").read_text(encoding="utf-8"))["families"]["T6"]
        anchors = load("protocol.json")["anchors"]
        self.assertEqual(anchors["H0 threat-exposed move orders"], census["H0"]["threat_exposed_orders"])
        self.assertEqual(anchors["HH threat-exposed orders followed by mover damage within 300 steps"],
                         census["HH"]["threat_exposed_then_damaged"])
        self.assertEqual((anchors["H0 threat-exposed move orders"], anchors["HH threat-exposed move orders"]), (230, 200))


@unittest.skipUnless(all((OUT / n).exists() for n in RESULTS), "Sprint 19 results not yet written")
class ResultsTest(unittest.TestCase):
    def test_results_are_bound_to_the_frozen_protocol_and_inputs(self) -> None:
        for name in RESULTS:
            data = load(name)
            self.assertEqual(data["protocol_sha256"], sha256(OUT / "protocol.json"), name)
            self.assertEqual(data["inputs_sha256"], sha256(OUT / "inputs.json"), name)

    def test_fidelity_holds(self) -> None:
        f = load("fidelity.json")
        self.assertTrue(f["ok"])
        self.assertTrue(all(a["equal"] for a in f["anchors"].values()))
        self.assertTrue(all(f["blocks"].values()))
        self.assertEqual(f["side_games"], {"H0": 16, "HH": 4})
        self.assertEqual(f["anchors"]["HH threat-exposed move orders"]["replay"], 200)

    def test_disposition_recomputed_from_the_public_figures(self) -> None:
        s = load("shadow.json")
        d = load("disposition.json")
        hh = s["HH"]["sides"]
        self.assertEqual(len(hh), 4)
        episodes = [side["gate_episodes"] for side in hh]
        participants = sum(side["capturers"]["first_ownership_participants"] for side in hh)
        gated = sum(side["capturers"]["distinct_gated"] for side in hh)
        again = st.disposition(load("fidelity.json")["ok"], episodes, participants, gated)
        self.assertEqual(d["disposition"], again["disposition"])
        self.assertEqual((d["hh_gate_episodes"], d["capturer"]), (episodes, [participants, gated]))
        pooled = s["HH"]["pooled"]["capturers"]
        self.assertEqual((pooled["participants"], pooled["gated"]), (participants, gated))

    def test_side_figures_are_consistent(self) -> None:
        s = load("shadow.json")
        self.assertEqual(len(s["H0"]["sides"]), 16)
        for pop in ("H0", "HH"):
            for side in s[pop]["sides"]:
                self.assertEqual(side["gated_decisions"], side["gate_episodes"] + side["repeats_within_episodes"])
                self.assertEqual(sum(side["release_reasons"].values()), side["gate_episodes"])
                self.assertLessEqual(side["distinct_gated"], side["gate_episodes"])
                self.assertLessEqual(side["gate_episodes"] + side["cooldown_suppressions"] + side["repeats_within_episodes"],
                                     side["threat_entry_opportunities"])
                self.assertTrue(all(side["integrity"].values()), side["side_game"])
            self.assertEqual(sum(x["move_orders"] for x in s[pop]["sides"]), s[pop]["pooled"]["move_orders"])
        self.assertEqual(sum(x["move_orders"] for x in s["HH"]["sides"]), 416)
        self.assertEqual(sum(x["move_orders"] for x in s["H0"]["sides"]), 509)

    def test_certificates_cover_every_hh_side_game_with_a_gate(self) -> None:
        certs = load("certificates.json")["HH"]
        sides = load("shadow.json")["HH"]["sides"]
        self.assertEqual(len(certs), 4)
        for cert, side in zip(certs, sides):
            if side["gate_episodes"] == 0:
                self.assertIsNone(cert)
                continue
            self.assertEqual((cert["side_game"], cert["decision"]), (side["side_game"], side["first_gate"]["decision"]))
            self.assertEqual(len(cert["gate_action_types"]) + 1, len(cert["baseline_action_types"]))
            self.assertEqual(cert["baseline_action_types"][cert["dropped_position"]], 1)

    def test_public_files_carry_no_forbidden_key_or_candidate_identity(self) -> None:
        from miaosuan_agent.evaluation.s12_screen import privacy_problems
        for name in RESULTS:
            self.assertEqual(privacy_problems(load(name)), [], name)
        for path in sorted(OUT.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            for needle in ("t9-batch-capacity-v3", "t9-delayed-post-stage-any-v6", "t9-capacity", "t4-artillery",
                           "t7-idle-concealment", "tactic-deployment-split", "ps1-probe-hook"):
                self.assertNotIn(needle, text, path.name)
            self.assertLess(len(text.encode("utf-8")), 100_000, path.name)


if __name__ == "__main__":
    unittest.main()
