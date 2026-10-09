"""Sprint 28 driver (``scripts/s28_t12.py``) logic that needs no private data: the H0 recorded-action pass, side labels,
the seat id, the public-file split, the refusal file, the input check, the registered anchors against the published
Sprint 18 files and the protocol's frozen values."""

from __future__ import annotations

import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("s28_driver", ROOT / "scripts" / "s28_t12.py")
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


class LabelSeatAndSplitTest(unittest.TestCase):
    def test_side_labels(self) -> None:
        class G:
            game, scenario = "2130511121.H1.s12-v3-primary-1.p03", "2130511121"
        self.assertEqual(drv.side_label("HH", G, 1), "HH p03 baseline-v2 blue")
        self.assertEqual(drv.side_label("H0", G, 0), "H0 2130511121 red")

    def test_seat_of(self) -> None:
        class F:
            def __init__(self, actions):
                self.actions = actions
        self.assertEqual(drv.seat_of([[{"actor": 3}], []], [F([{"actor": 3}])]), (3, True))
        self.assertEqual(drv.seat_of([[{"actor": 3}]], [F([{"actor": 4}])]), (None, False))
        self.assertEqual(drv.seat_of([[]], [F([])]), (None, False))

    def test_one_file_when_small(self) -> None:
        out = drv.split_rows("episodes-HH", {"population": "HH"}, [{"i": i} for i in range(3)])
        self.assertEqual(list(out), ["episodes-HH.json"])
        self.assertEqual(out["episodes-HH.json"]["part"], "1/1")

    def test_parts_in_order_under_the_limit(self) -> None:
        rows = [{"i": i, "text": "x" * 400} for i in range(40)]
        saved = drv.PUBLIC_LIMIT
        drv.PUBLIC_LIMIT = 3000
        try:
            out = drv.split_rows("damage", {"population": "H0"}, rows)
            sizes = [len(drv.dump(v).encode("utf-8")) for v in out.values()]
        finally:
            drv.PUBLIC_LIMIT = saved
        self.assertGreater(len(out), 1)
        self.assertTrue(all(s <= 3000 for s in sizes), sizes)
        self.assertEqual([r for v in out.values() for r in v["rows"]], rows)
        self.assertEqual(list(out)[0], "damage-1.json")

    def test_refusal_writes_only_an_invalid_disposition(self) -> None:
        out = drv.refused({"schema": drv.SCHEMA_RESULTS}, True)
        self.assertEqual(list(out), ["disposition.json"])
        data = json.loads(out["disposition.json"])
        self.assertEqual(data["disposition"], "T12_O1_OFFLINE_INVALID")
        self.assertNotIn("findings", data["reason"])


class InputsTest(unittest.TestCase):
    def committed(self, **wrong):
        keys = {"sprint18_inputs": S18 / "inputs.json", "sprint18_census": S18 / "census.json",
                "sprint18_admission": S18 / "admission.json",
                "sprint24_experiments": ROOT / "evaluation/s24-tactical-frontier-reselection/experiments.json"}
        out = {k: {"path": p.relative_to(ROOT).as_posix(), "sha256": wrong.get(k, drv.sha256(p))} for k, p in keys.items()}
        out.update({"H0": {"games": []}, "HH": {"games": []}})
        return out

    def test_a_changed_pin_is_reported(self) -> None:
        self.assertEqual(drv.input_problems(self.committed(), {"sources": {}}), [])
        for key in ("sprint18_inputs", "sprint18_census", "sprint18_admission", "sprint24_experiments"):
            problems = drv.input_problems(self.committed(**{key: "0" * 64}), {"sources": {}})
            self.assertEqual(len(problems), 1, key)
        problems = drv.input_problems(self.committed(), {"sources": {"scripts/s28_t12.py": "0" * 64}})
        self.assertEqual(problems, ["scripts/s28_t12.py"])


class AnchorTest(unittest.TestCase):
    def test_anchors_are_the_published_figures(self) -> None:
        for name, value in drv.INTEGRITY.items():
            self.assertEqual(CENSUS["consistency"][name]["census"], value, name)
        self.assertEqual(CENSUS["consistency"]["HH baseline-v2 reconstruction equal"]["census"], drv.HH_EQUAL)
        for pop, value in drv.MOVE_ORDERS.items():
            self.assertEqual(CENSUS["families"]["T6"][pop]["move_orders"], value)
        for pop, (stacked, alone) in drv.STATIONARY_ON_OBJECTIVE.items():
            rows = ADMISSION["tables"][pop]["ground_events_by_state"]
            self.assertEqual((rows["stationary, on an objective, stacked"], rows["stationary, on an objective, alone"]),
                             (stacked, alone))
        self.assertEqual(ADMISSION["tables"]["H0"]["sides_with_a_stationary_stacked_hit_on_an_objective"],
                         drv.H0_SIDES_STATIONARY_STACKED_HIT)
        self.assertEqual((CENSUS["populations"]["H0"]["scenario_sides"], CENSUS["populations"]["HH"]["analysed_sides"]),
                         (drv.SIDE_GAMES["H0"], drv.SIDE_GAMES["HH"]))

    def test_frozen_hypothesis_is_sprint_24s(self) -> None:
        exp = json.loads((ROOT / "evaluation/s24-tactical-frontier-reselection/experiments.json").read_text(encoding="utf-8"))
        t12 = exp["experiments"]["T12"] if "experiments" in exp else exp["T12"]
        self.assertIn("two or more idle own ground units", t12["trigger"])
        self.assertIn("fewer than four own ground units", t12["trigger"])
        self.assertEqual(t12["stop"].split(";")[0], "offline: fewer than one trigger per side-game")

    def test_protocol_frozen_values(self) -> None:
        proto = drv.protocol()
        self.assertEqual(proto["engine_sessions"], 0)
        self.assertEqual(proto["shadow"]["minimum_idle_units"], 2)
        self.assertEqual(proto["shadow"]["stacking_limit"], 4)
        self.assertEqual(proto["opportunity_stop"]["minimum_per_hh_side_game"], 1)
        self.assertEqual(proto["dispositions_first_match"][0], "T12_O1_OFFLINE_INVALID")
        self.assertEqual(set(proto["sources"]), set(drv.SOURCES))
        self.assertEqual(len(proto["anchors"]), 13)


if __name__ == "__main__":
    unittest.main()
