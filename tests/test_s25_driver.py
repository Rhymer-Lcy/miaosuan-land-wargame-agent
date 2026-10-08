"""Sprint 25 driver (``scripts/s25_t13_d1.py``) logic that needs no private data: the H0 recorded-action pass, side
labels, the public-file split, the input check, the registered anchors against the published Sprint 18 census, and
the protocol's frozen values."""

from __future__ import annotations

import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("s25_driver", ROOT / "scripts" / "s25_t13_d1.py")
drv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drv)
CENSUS = json.loads((ROOT / "evaluation" / "s18-frontier-reset" / "census.json").read_text(encoding="utf-8"))


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
        out = drv.split_rows("losses-HH", {"population": "HH"}, [{"i": i} for i in range(3)])
        self.assertEqual(list(out), ["losses-HH.json"])
        self.assertEqual(out["losses-HH.json"]["part"], "1/1")

    def test_parts_in_order_under_the_limit(self) -> None:
        rows = [{"i": i, "text": "x" * 400} for i in range(40)]
        saved = drv.PUBLIC_LIMIT
        drv.PUBLIC_LIMIT = 3000
        try:
            out = drv.split_rows("losses-H0", {"population": "H0"}, rows)
            sizes = [len(drv.dump(v).encode("utf-8")) for v in out.values()]
        finally:
            drv.PUBLIC_LIMIT = saved
        self.assertGreater(len(out), 1)
        self.assertTrue(all(s <= 3000 for s in sizes), sizes)
        self.assertEqual([r for v in out.values() for r in v["rows"]], rows)
        self.assertEqual(list(out)[0], "losses-H0-1.json")
        self.assertEqual({v["part"].split("/")[1] for v in out.values()}, {str(len(out))})


class InputsTest(unittest.TestCase):
    def test_a_changed_pin_is_reported(self) -> None:
        good = drv.sha256(drv.S18 / "census.json")
        committed = {"sprint18_inputs": {"path": "evaluation/s18-frontier-reset/inputs.json", "sha256": "0" * 64},
                     "sprint18_census": {"path": "evaluation/s18-frontier-reset/census.json", "sha256": good},
                     "H0": {"games": []}, "HH": {"games": []}}
        problems = drv.input_problems(committed, {"sources": {}})
        self.assertEqual(problems, ["evaluation/s18-frontier-reset/inputs.json"])
        problems = drv.input_problems(committed, {"sources": {"scripts/s25_t13_d1.py": "0" * 64}})
        self.assertIn("scripts/s25_t13_d1.py", problems)


class AnchorTest(unittest.TestCase):
    def test_anchors_are_the_published_census_figures(self) -> None:
        for name, value in drv.INTEGRITY.items():
            self.assertEqual(CENSUS["consistency"][name]["census"], value, name)
        self.assertEqual(CENSUS["consistency"]["HH baseline-v2 reconstruction equal"]["census"], drv.HH_EQUAL)
        for pop in ("H0", "HH"):
            self.assertEqual(CENSUS["scan"]["N4"][pop]["objective_losses"], drv.LOSSES[pop])
            self.assertEqual(CENSUS["scan"]["N4"][pop]["losses_with_own_unit_on_it_before"], drv.ON_HEX[pop])
        self.assertEqual(CENSUS["opportunity_sides"]["sides_with_opportunity"]["scan objective lost after being held"],
                         drv.H0_SIDES_WITH_LOSS)
        self.assertEqual((CENSUS["populations"]["H0"]["scenario_sides"], CENSUS["populations"]["HH"]["analysed_sides"]),
                         (drv.SIDE_GAMES["H0"], drv.SIDE_GAMES["HH"]))

    def test_protocol_frozen_values(self) -> None:
        p = drv.protocol()
        self.assertEqual((p["shadow"]["threat_margin_hexes"], p["shadow"]["hold_limit_steps"],
                          p["shadow"]["cooldown_steps"], p["denial_zone"]["radius_hexes"], p["engine_sessions"]),
                         (1, 300, 300, 1, 0))
        self.assertFalse(p["shadow"]["executable"])
        self.assertEqual(p["dispositions_first_match"], ["T13_D1_INVALID", "T13_D1_NOT_READY",
                                                          "T13_D1_READY_FOR_SMALL_EXPLORATORY_PROPOSAL"])
        self.assertEqual(sorted(p["sources"]), sorted(drv.SOURCES))
        self.assertTrue(all((ROOT / s).exists() for s in drv.SOURCES))


if __name__ == "__main__":
    unittest.main()
