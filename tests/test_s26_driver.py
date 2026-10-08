"""Sprint 26 driver (``scripts/s26_t6s.py``) logic that needs no private data: the H0 recorded-action pass, side labels,
the public-file split, the input check, the registered anchors against the published Sprint 18, 19 and 25 files, the
fidelity rule on a stand-in loader, the moving-damage table and the protocol's frozen values."""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("s26_driver", ROOT / "scripts" / "s26_t6s.py")
drv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drv)
S18 = ROOT / "evaluation" / "s18-frontier-reset"
CENSUS = json.loads((S18 / "census.json").read_text(encoding="utf-8"))
ADMISSION = json.loads((S18 / "admission.json").read_text(encoding="utf-8"))


class RecordedTest(unittest.TestCase):
    def write(self, folder: Path, rows) -> str:
        path = folder / "g.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps({"game_id": "G", "scenario_id": 1}) + "\n")
            for r in rows:
                handle.write(json.dumps(r) + "\n")
        return str(path)

    def test_actions_in_step_order_per_faction(self) -> None:
        rows = [{"seat": 1, "faction": 0, "step": 2, "actions": [{"type": 2}]},
                {"seat": 1, "faction": 0, "step": 1, "actions": [{"type": 1}]},
                {"seat": 2, "faction": 1, "step": 1, "actions": []}]
        with tempfile.TemporaryDirectory() as tmp:
            out = drv.recorded_h0({"H0": {"games": [{"path": self.write(Path(tmp), rows)}]}})
        self.assertEqual(out[("G", 0)], [[{"type": 1}], [{"type": 2}]])
        self.assertEqual(out[("G", 1)], [[]])

    def test_two_rows_for_one_seat_and_step_refused(self) -> None:
        rows = [{"seat": 1, "faction": 0, "step": 1, "actions": []}, {"seat": 1, "faction": 0, "step": 1, "actions": []}]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                drv.recorded_h0({"H0": {"games": [{"path": self.write(Path(tmp), rows)}]}})


class LabelAndSplitTest(unittest.TestCase):
    def test_side_labels(self) -> None:
        class G:
            game, scenario = "2130511121.H1.s12-v3-primary-1.p03", "2130511121"
        self.assertEqual(drv.side_label("HH", G, 1), "HH p03 baseline-v2 blue")
        self.assertEqual(drv.side_label("H0", G, 0), "H0 2130511121 red")

    def test_one_file_when_small(self) -> None:
        out = drv.split_rows("episodes-HH", {"population": "HH"}, [{"i": i} for i in range(3)])
        self.assertEqual(list(out), ["episodes-HH.json"])
        self.assertEqual(out["episodes-HH.json"]["part"], "1/1")

    def test_parts_in_order_under_the_limit(self) -> None:
        rows = [{"i": i, "text": "x" * 400} for i in range(40)]
        saved = drv.PUBLIC_LIMIT
        drv.PUBLIC_LIMIT = 3000
        try:
            out = drv.split_rows("episodes-H0", {"population": "H0"}, rows)
            sizes = [len(drv.dump(v).encode("utf-8")) for v in out.values()]
        finally:
            drv.PUBLIC_LIMIT = saved
        self.assertGreater(len(out), 1)
        self.assertTrue(all(s <= 3000 for s in sizes), sizes)
        self.assertEqual([r for v in out.values() for r in v["rows"]], rows)
        self.assertEqual(list(out)[0], "episodes-H0-1.json")
        self.assertEqual({v["part"].split("/")[1] for v in out.values()}, {str(len(out))})


class InputsTest(unittest.TestCase):
    def committed(self, **wrong):
        keys = {"sprint18_inputs": S18 / "inputs.json", "sprint18_census": S18 / "census.json",
                "sprint18_admission": S18 / "admission.json",
                "sprint19_disposition": ROOT / "evaluation/s19-t6g-shadow/disposition.json",
                "sprint25_private_rows": S18 / "census.json"}
        out = {k: {"path": p.relative_to(ROOT).as_posix(), "sha256": wrong.get(k, drv.sha256(p))} for k, p in keys.items()}
        out.update({"H0": {"games": []}, "HH": {"games": []}})
        return out

    def test_a_changed_pin_is_reported(self) -> None:
        self.assertEqual(drv.input_problems(self.committed(), {"sources": {}}), [])
        for key in ("sprint18_admission", "sprint19_disposition", "sprint25_private_rows"):
            problems = drv.input_problems(self.committed(**{key: "0" * 64}), {"sources": {}})
            self.assertEqual(len(problems), 1, key)
        problems = drv.input_problems(self.committed(), {"sources": {"scripts/s26_t6s.py": "0" * 64}})
        self.assertEqual(problems, ["scripts/s26_t6s.py"])


class AnchorTest(unittest.TestCase):
    def test_anchors_are_the_published_figures(self) -> None:
        for name, value in drv.INTEGRITY.items():
            self.assertEqual(CENSUS["consistency"][name]["census"], value, name)
        self.assertEqual(CENSUS["consistency"]["HH baseline-v2 reconstruction equal"]["census"], drv.HH_EQUAL)
        for name, (pop, key, value) in drv.T6_ANCHORS.items():
            self.assertEqual(CENSUS["families"]["T6"][pop][key], value, name)
        for pop, (ground, stacked) in drv.N9_ANCHORS.items():
            self.assertEqual((CENSUS["scan"]["N9"][pop]["ground_events"], CENSUS["scan"]["N9"][pop]["ground_events_victim_stacked"]),
                             (ground, stacked))
            self.assertEqual(sum(CENSUS["families"]["T6"][pop]["events_by_victim_state"].values()), drv.EVENT_TOTALS[pop])
            self.assertEqual(ADMISSION["tables"][pop]["ground_events_by_state"]["moving, off objectives, stacked"],
                             drv.MOVING_STACKED_OFF_OBJECTIVES[pop])
        self.assertEqual(CENSUS["opportunity_sides"]["sides_with_opportunity"]["scan stacked ground unit damaged"],
                         drv.H0_SIDES_STACKED_DAMAGED)
        s19 = json.loads((ROOT / "evaluation/s19-t6g-shadow/disposition.json").read_text(encoding="utf-8"))
        self.assertEqual(s19["hh_gate_episodes"], drv.S19_GATE_EPISODES)
        s25 = json.loads((ROOT / "evaluation/s25-t13-d1/anatomy.json").read_text(encoding="utf-8"))
        several = [r for r in s25["pooled"]["v_reasons"] if r[0] == "several last defenders, all left alive under recorded MOVEs"]
        self.assertEqual(several[0][1], drv.S25_MULTI_DEFENDER_V_ORDER)
        self.assertEqual((CENSUS["populations"]["H0"]["scenario_sides"], CENSUS["populations"]["HH"]["analysed_sides"]),
                         (drv.SIDE_GAMES["H0"], drv.SIDE_GAMES["HH"]))

    def test_protocol_frozen_values(self) -> None:
        from miaosuan_agent.evaluation import s26_t6s as st
        p = drv.protocol()
        s = p["shadow"]
        self.assertEqual((s["minimum_group"], s["route_prefix_hexes"], s["stall_factor"], s["stall_slack_steps"],
                          p["engine_sessions"], p["follow_up_window_steps"]), (2, 5, 2, 10, 0, 300))
        self.assertFalse(s["executable"])
        self.assertEqual((p["stops"]["A"]["minimum_episodes_per_hh_side_game"], p["stops"]["A"]["hh_side_games"],
                          p["stops"]["B"]["minimum_h0_scenario_sides"]), (10, 4, 4))
        self.assertEqual(p["dispositions_first_match"], ["T6_S_INVALID", "T6_S_INADEQUATE_OPPORTUNITY",
                                                          "T6_S_ONWARD_CAPTURE_RISK", "T6_S_OFFLINE_PASS"])
        self.assertEqual(sorted(p["sources"]), sorted(drv.SOURCES))
        self.assertTrue(all((ROOT / s).exists() for s in drv.SOURCES))
        self.assertEqual(st.digit_words({k: v for k, v in p.items() if k != "sources"}), [])


def stand_in_loader():
    """A loader whose census blocks, integrity counts and side-games equal the published figures."""
    analyses = {pop: [types.SimpleNamespace(side=types.SimpleNamespace(label=f"{pop} {i}"), integrity={"x": True})
                      for i in range(n)] for pop, n in drv.SIDE_GAMES.items()}
    return types.SimpleNamespace(
        families={"T6": copy.deepcopy(CENSUS["families"]["T6"])},
        scan={"N9": copy.deepcopy(CENSUS["scan"]["N9"]), "N6": copy.deepcopy(CENSUS["scan"]["N6"])},
        integrity={**drv.INTEGRITY, "HH baseline-v2 reconstruction equal": [drv.HH_EQUAL, drv.HH_EQUAL]},
        recorded_differs=drv.INTEGRITY["H0 v2 differs from recorded v0"], gate_episodes=list(drv.S19_GATE_EPISODES),
        sides=[{"scan stacked ground unit damaged": i < drv.H0_SIDES_STACKED_DAMAGED} for i in range(16)],
        private={"events": [], "sides": []}, analyses=analyses)


class FidelityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = drv.admission_script
        drv.admission_script = lambda: types.SimpleNamespace(tables=lambda events, sides: copy.deepcopy(ADMISSION["tables"]))

    def tearDown(self) -> None:
        drv.admission_script = self.saved

    def test_published_figures_pass(self) -> None:
        out = drv.fidelity(stand_in_loader())
        self.assertTrue(out["ok"], {k: v for k, v in out["anchors"].items() if not v["equal"]})
        self.assertEqual(len(out["anchors"]), 27)
        self.assertEqual(len(out["blocks"]), 8)

    def test_each_planted_difference_fails(self) -> None:
        plants = {
            "H0 decisions": lambda l: l.integrity.__setitem__("H0 decisions", 33695),
            "separate pass": lambda l: setattr(l, "recorded_differs", 122),
            "HH reconstruction": lambda l: l.integrity.__setitem__("HH baseline-v2 reconstruction equal", [11523, 11524]),
            "stacked victims": lambda l: l.scan["N9"]["HH"].__setitem__("ground_events_victim_stacked", 69),
            "T6 block": lambda l: l.families["T6"]["H0"].__setitem__("threat_exposed_orders", 231),
            "gate episodes": lambda l: setattr(l, "gate_episodes", [0, 0, 1, 0]),
            "stacked sides": lambda l: l.sides.__setitem__(15, {"scan stacked ground unit damaged": True}),
            "side-games": lambda l: l.analyses["HH"].pop(),
            "side integrity": lambda l: setattr(l.analyses["H0"][0], "integrity", {"x": False}),
        }
        for name, plant in plants.items():
            loader = stand_in_loader()
            plant(loader)
            self.assertFalse(drv.fidelity(loader)["ok"], name)

    def test_moving_damage_from_the_admission_rows(self) -> None:
        self.assertEqual(drv.moving_damage(stand_in_loader()), {"H0": {"stacked": 72, "alone": 52},
                                                                "HH": {"stacked": 60, "alone": 57}})


if __name__ == "__main__":
    unittest.main()
