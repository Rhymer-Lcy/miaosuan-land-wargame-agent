"""Checks of the boundary's terrain normalization against the real SDK map data.

The map data is part of the SDK archive, which carries no redistribution license, so it exists
only under the git-ignored ``local/source-archives/``. Without it every test here is skipped.
"""

from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path

from miaosuan_agent import sdk_provenance as prov
from miaosuan_agent.boundary import MoveCosts, MoveMode, normalize_state
from miaosuan_agent.sdk_data import load_cost_bytes

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = prov.default_archive_dir(REPO) / prov.SDK_ARCHIVE_NAME
FIXTURES = REPO / "local" / "contract-fixtures" / f"sdk-{prov.ENGINE_VERSION}"


def setUpModule() -> None:
    if not ARCHIVE.is_file():
        raise unittest.SkipTest(f"no local SDK archive at {ARCHIVE.relative_to(REPO).as_posix()} (git-ignored)")


class RealMoveCostsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with zipfile.ZipFile(ARCHIVE) as outer:
            cls.data = zipfile.ZipFile(io.BytesIO(outer.read(prov.DATA_ARCHIVE_MEMBER)))
        cls.maps = sorted({name.split("/")[2][len("map_"):] for name in cls.data.namelist()
                           if name.startswith("Data/maps/map_") and name.endswith("/cost.pickle")})

    def costs(self, map_id: str) -> MoveCosts:
        # the restricted unpickler refuses any global, so loading executes no code
        return MoveCosts.from_raw(load_cost_bytes(self.data.read(f"Data/maps/map_{map_id}/cost.pickle")))

    def test_every_supplied_map_normalizes(self) -> None:
        self.assertEqual(len(self.maps), 16)
        for map_id in self.maps:
            with self.subTest(map=map_id):
                costs = self.costs(map_id)
                self.assertGreater(sum(len(edges) for edges in costs.edges[MoveMode.VEHICLE].values()), 0)

    def test_map_9601_dimensions(self) -> None:
        costs = self.costs("9601")
        self.assertEqual((costs.rows, costs.cols), (92, 77))

    @unittest.skipUnless(FIXTURES.is_dir(), "private contract fixtures absent")
    def test_vehicle_graph_does_not_exclude_runtime_roadblocks(self) -> None:
        from miaosuan_agent.contract_capture import load_capture

        capture = load_capture(sorted(p.parent for p in FIXTURES.glob("*/manifest.json"))[0])
        roadblocks = set(normalize_state(capture["states"]["setup"]).red.roadblocks())
        entering = {n for edges in self.costs("9601").edges[MoveMode.VEHICLE].values() for n in edges}
        self.assertTrue(roadblocks)
        self.assertTrue(roadblocks <= entering)


if __name__ == "__main__":
    unittest.main()
