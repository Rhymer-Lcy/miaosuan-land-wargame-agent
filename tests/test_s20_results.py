"""Sprint 20: the committed public files of the T11-O1 offline replay (no private data needed).

The protocol, inputs and kill-model assessment are bound to the frozen sources, to Sprint 18's pins and to each other;
the result files, once present, are bound to them, and the disposition is recomputed from the public per-side-game
figures by the frozen rule. Where the local documentation snapshot exists (the workstation), every quotation of the
kill-model assessment is checked against it again.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s20_t11 as st
from miaosuan_agent.experiments import t11_kill_first as tk

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s20-t11-replay"
S18 = ROOT / "evaluation" / "s18-frontier-reset"
SNAPSHOT = ROOT / st.SNAPSHOT
RESULTS = ("fidelity.json", "replay.json", "disposition.json")


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RegistrationTest(unittest.TestCase):
    def test_protocol_matches_the_frozen_modules(self) -> None:
        p = load("protocol.json")
        self.assertEqual(p["engine_sessions"], 0)
        self.assertEqual(p["dispositions_first_match"], list(st.DISPOSITIONS))
        self.assertEqual(p["classes"], list(st.CLASSES))
        self.assertEqual(p["kinds"], list(st.KINDS))
        self.assertEqual((p["opportunity"]["minimum_per_hh_side_game"], p["opportunity"]["hh_side_games"]), (10, 4))
        self.assertEqual(p["rule"]["rankings"], list(tk.RANKINGS))
        self.assertEqual(p["rule"]["fail_closed"], list(tk.FALLBACKS))
        for path, digest in p["sources"].items():
            normalised = hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertEqual(normalised, digest, path)
        self.assertEqual(len(p["sources"]), 8)

    def test_anchors_are_the_published_census_figures(self) -> None:
        census = json.loads((S18 / "census.json").read_text(encoding="utf-8"))["scan"]["N3"]
        anchors = load("protocol.json")["anchors"]
        for pop in ("H0", "HH"):
            self.assertEqual(anchors[f"{pop} baseline-v2 direct-fire shots"], census[pop]["shots"])
            self.assertEqual(anchors[f"{pop} shots with two or more targets listed"],
                             census[pop]["shots_with_two_or_more_targets"])
            self.assertEqual(anchors[f"{pop} shots with a lower-blood target listed"],
                             census[pop]["lower_blood_target_listed"])
        self.assertEqual(anchors, {"H0 baseline-v2 direct-fire shots": 432, "H0 shots with two or more targets listed": 368,
                                   "H0 shots with a lower-blood target listed": 127, "HH baseline-v2 direct-fire shots": 319,
                                   "HH shots with two or more targets listed": 267,
                                   "HH shots with a lower-blood target listed": 97})

    def test_inputs_are_sprint_18_pins(self) -> None:
        i = load("inputs.json")
        s18 = json.loads((S18 / "inputs.json").read_text(encoding="utf-8"))
        self.assertEqual((i["H0"], i["HH"]), (s18["H0"], s18["HH"]))
        self.assertEqual((len(i["H0"]["games"]), len(i["HH"]["games"])), (8, 4))
        self.assertEqual(i["sprint18_inputs"]["sha256"], sha256(S18 / "inputs.json"))
        self.assertEqual(i["sprint18_census"]["sha256"], sha256(S18 / "census.json"))

    def test_kill_model_is_pinned_and_equal_to_the_module(self) -> None:
        p, k = load("protocol.json"), load("kill_model.json")
        self.assertEqual(p["kill_model"]["sha256"], sha256(OUT / "kill_model.json"))
        self.assertEqual((p["kill_model"]["available"], k["available"]), (False, False))
        self.assertEqual((p["kill_model"]["gaps"], k["gaps"]), (["K2", "K4", "K5", "K6"], ["K2", "K4", "K5", "K6"]))
        self.assertEqual([dict(i, quotes=[list(q) for q in i["quotes"]]) for i in st.KILL_MODEL_ITEMS], k["items"])
        self.assertEqual(k["available"], st.kill_model_available(k["items"]))

    @unittest.skipUnless((SNAPSHOT / "rules_tables.txt").exists(), "documentation snapshot not present")
    def test_quotations_are_verbatim_and_the_snapshot_is_the_pinned_one(self) -> None:
        k = load("kill_model.json")
        for name, digest in k["snapshot"]["files_sha256"].items():
            self.assertEqual(sha256(SNAPSHOT / name), digest, name)
        problems = st.quote_problems(k["items"], lambda n: (SNAPSHOT / n).read_text(encoding="utf-8"))
        self.assertEqual(problems, [])
        planted = [dict(k["items"][0], quotes=[["rules_tables.txt", "### 对车辆单位战斗结果表格不存在"]])]
        self.assertEqual(len(st.quote_problems(planted, lambda n: (SNAPSHOT / n).read_text(encoding="utf-8"))), 1)

    def test_mutation_record_covers_the_frozen_sources(self) -> None:
        m = load("mutation.json")
        self.assertEqual((m["declared"], m["killed"]), (36, 36))  # 35 at registration, 36 after amendment A1
        p = load("protocol.json")
        for path, digest in m["sources_sha256"].items():
            self.assertEqual(p["sources"][path], digest, path)


@unittest.skipUnless(all((OUT / n).exists() for n in RESULTS), "Sprint 20 results not yet written")
class ResultsTest(unittest.TestCase):
    def test_results_are_bound_to_the_frozen_registration(self) -> None:
        for name in RESULTS:
            data = load(name)
            self.assertEqual(data["protocol_sha256"], sha256(OUT / "protocol.json"), name)
            self.assertEqual(data["inputs_sha256"], sha256(OUT / "inputs.json"), name)
            self.assertEqual(data["kill_model_sha256"], sha256(OUT / "kill_model.json"), name)

    def test_fidelity_holds(self) -> None:
        f = load("fidelity.json")
        self.assertTrue(f["ok"])
        self.assertTrue(all(a["equal"] for a in f["anchors"].values()))
        self.assertEqual(f["side_games"], {"H0": 16, "HH": 4})
        self.assertEqual(f["baseline_ranking_reproduces_baseline_v2"],
                         {"H0": [33696, 33696, 33696], "HH": [11524, 11524, 11524]})
        self.assertEqual(sum(f["problems_by_side_game"].values()), 0)

    def test_disposition_recomputed_from_the_public_figures(self) -> None:
        r, d = load("replay.json"), load("disposition.json")
        hh, h0 = r["HH"]["sides"], r["H0"]["sides"]
        self.assertEqual((len(hh), len(h0)), (4, 16))
        changed = [s["counts"]["changed_emitted_shots"] for s in hh]
        coupled = any(s["non_shoot_differences"] > 0 for s in hh + h0)
        expected = st.disposition(load("fidelity.json")["ok"], load("kill_model.json")["available"], coupled,
                                  changed, None)
        self.assertEqual(d["disposition"], expected["disposition"])
        self.assertEqual(d["items"], expected["items"])
        self.assertEqual(d["hh_changed_emitted_shots"], changed)

    def test_side_game_figures_are_internally_consistent(self) -> None:
        r = load("replay.json")
        for pop in ("HH", "H0"):
            for s in r[pop]["sides"]:
                c, kinds = s["counts"], s["differences_by_class_and_kind"]
                self.assertEqual(c["changed_emitted_shots"], c["root_changed_shots"] + c["induced_changed_shots"])
                self.assertEqual(c["root_changed_shots"], kinds[st.ROOT][st.CHANGED_SHOT])
                self.assertEqual(c["induced_changed_shots"], kinds[st.INDUCED_SHOOT][st.CHANGED_SHOT])
                self.assertEqual(sum(kinds[st.UNEXPLAINED].values()), 0)
                self.assertEqual(s["non_shoot_differences"],
                                 sum(n for cls in kinds.values() for k, n in cls.items() if k != st.CHANGED_SHOT))
                self.assertEqual((c["duplicate_targets_baseline"], c["duplicate_targets_candidate"]), (0, 0))
                self.assertEqual(s["root_switches"]["n"], c["root_changed_shots"])
                self.assertEqual(s["root_switches"]["same_target_as_baseline_ranking"], 0)
                self.assertTrue(s["integrity_ok"])
            pooled = r[pop]["pooled"]
            self.assertEqual(pooled["counts"]["changed_emitted_shots"],
                             sum(s["counts"]["changed_emitted_shots"] for s in r[pop]["sides"]))
            self.assertEqual(pooled["counts"]["baseline_shots"], {"HH": 319, "H0": 432}[pop])


if __name__ == "__main__":
    unittest.main()
