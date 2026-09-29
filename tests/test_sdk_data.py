from __future__ import annotations

import collections
import hashlib
import io
import json
import pickle
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from miaosuan_agent import sdk_data
from miaosuan_agent import sdk_provenance as prov

try:
    import numpy
except ImportError:  # pragma: no cover - numpy is present in every environment used so far
    numpy = None


def _write_map(root: Path, map_id: str, rows: int = 3, cols: int = 4) -> None:
    directory = root / "maps" / f"map_{map_id}"
    directory.mkdir(parents=True)
    grid = [[{"cond": 0} for _ in range(cols)] for _ in range(rows)]
    (directory / "basic.json").write_text(json.dumps({"map_data": grid}), encoding="utf-8")
    cost = [[[{r * 100 + c: 1} for c in range(cols)] for r in range(rows)]]
    (directory / "cost.pickle").write_bytes(pickle.dumps(cost))
    if numpy is not None:
        numpy.savez(directory / f"{map_id}see.npz", data=numpy.zeros((3, rows, cols, rows, cols), dtype=bool))


def _write_scenario(root: Path, scenario_id: str, hexes: list[int]) -> None:
    (root / "scenarios").mkdir(parents=True, exist_ok=True)
    scenario = {"scenario_id": int(scenario_id), "operators": [{"cur_hex": h} for h in hexes],
                "time": {"cur_step": 0}, "cities": [{"coord": hexes[0]}]}
    (root / "scenarios" / f"{scenario_id}.json").write_text(json.dumps(scenario), encoding="utf-8")


class CostLoadingTest(unittest.TestCase):
    def test_primitive_pickle_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cost.pickle"
            path.write_bytes(pickle.dumps([[{101: 2}]], protocol=3))
            self.assertEqual(sdk_data.load_cost(path), [[{101: 2}]])

    def test_pickle_with_globals_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cost.pickle"
            path.write_bytes(pickle.dumps(collections.OrderedDict(a=1)))
            with self.assertRaises(sdk_data.SdkDataError):
                sdk_data.load_cost(path)


@unittest.skipIf(numpy is None, "numpy is required to build see.npz fixtures")
class LoadInputsTest(unittest.TestCase):
    def test_loads_matching_scenario_and_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_map(root, "7")
            _write_scenario(root, "42", [0, 203])
            inputs = sdk_data.load_inputs(root, "42", "7")
        self.assertEqual(inputs.see.shape, (3, 3, 4, 3, 4))
        self.assertEqual(inputs.cost[0][2][3], {203: 1})

    def test_positions_outside_the_map_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_map(root, "7")
            _write_scenario(root, "42", [0, 305])
            with self.assertRaises(sdk_data.SdkDataError):
                sdk_data.load_inputs(root, "42", "7")

    def test_missing_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sdk_data.SdkDataError):
                sdk_data.load_inputs(Path(tmp), "42", "7")


class StagingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as data:
            data.writestr("Data/scenarios/42.json", "{}")
            for name in ("basic.json", "cost.pickle", "7see.npz"):
                data.writestr(f"Data/maps/map_7/{name}", name)
            data.writestr("Data/maps/map_8/basic.json", "not staged")
        self.data_bytes = inner.getvalue()
        self.wheel_bytes = b"wheel"
        self.outer = self.root / "sdk.zip"
        with zipfile.ZipFile(self.outer, "w") as archive:
            archive.writestr("Data.zip", self.data_bytes)
            archive.writestr("engine.whl", self.wheel_bytes)
        sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
        self.patches = [
            mock.patch.object(prov, "SDK_ARCHIVE_SHA256", sha(self.outer.read_bytes())),
            mock.patch.object(prov, "DATA_ARCHIVE_MEMBER", "Data.zip"),
            mock.patch.object(prov, "ENGINE_WHEEL_MEMBER", "engine.whl"),
            mock.patch.object(prov, "NESTED_ARCHIVES", {"Data.zip": sha(self.data_bytes),
                                                        "engine.whl": sha(self.wheel_bytes)}),
        ]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _patched(self):
        class Patched:
            def __enter__(inner):
                for patch in self.patches:
                    patch.start()

            def __exit__(inner, *exc):
                for patch in reversed(self.patches):
                    patch.stop()
        return Patched()

    def files(self, directory: Path) -> list:
        return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())

    def test_stages_only_the_requested_game_data(self) -> None:
        with self._patched():
            data_root = sdk_data.stage_game_data(self.outer, self.root / "run", "42", "7")
            with self.assertRaises(sdk_data.SdkDataError):  # never overwrites
                sdk_data.stage_game_data(self.outer, self.root / "run", "42", "7")
        self.assertEqual(self.files(self.root / "run"), ["Data/maps/map_7/7see.npz", "Data/maps/map_7/basic.json",
                                                         "Data/maps/map_7/cost.pickle", "Data/scenarios/42.json"])
        self.assertEqual(data_root, self.root / "run" / "Data")

    def test_extracts_the_verified_wheel_once(self) -> None:
        with self._patched():
            wheel = sdk_data.extract_engine_wheel(self.outer, self.root / "wheels")
            with self.assertRaises(sdk_data.SdkDataError):
                sdk_data.extract_engine_wheel(self.outer, self.root / "wheels")
        self.assertEqual(wheel.read_bytes(), self.wheel_bytes)

    def test_unverified_archive_is_refused(self) -> None:
        with self.assertRaises(sdk_data.SdkDataError):
            sdk_data.stage_game_data(self.outer, self.root / "run", "42", "7")
        with self.assertRaises(sdk_data.SdkDataError):
            sdk_data.extract_engine_wheel(self.outer, self.root / "wheels")
        self.assertFalse((self.root / "run").exists() or (self.root / "wheels").exists())


if __name__ == "__main__":
    unittest.main()
