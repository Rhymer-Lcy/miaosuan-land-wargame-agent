"""The baseline policy on real captured observations and real map costs (private assets only).

Uses the private contract fixtures (``local/contract-fixtures/``) and the SDK archive
(``local/source-archives/``), both git-ignored. Without them every test here is skipped. The
policy runs without the engine: these tests check legality, stage separation and determinism of
decisions on real data, not engine acceptance (that is the real-engine evaluation's job).
"""

from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path

from miaosuan_agent import sdk_provenance as prov
from miaosuan_agent.boundary import MoveCosts, Observation, Origin, Stage
from miaosuan_agent.contract_capture import load_capture
from miaosuan_agent.decision import BaselinePolicy, Memory, digest
from miaosuan_agent.sdk_data import load_cost_bytes

from tests.fixtures import decision_scenarios as ds

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = prov.default_archive_dir(REPO) / prov.SDK_ARCHIVE_NAME
FIXTURE_ROOT = REPO / "local" / "contract-fixtures" / f"sdk-{prov.ENGINE_VERSION}"
CAPTURES = sorted(p.parent for p in FIXTURE_ROOT.glob("*/manifest.json")) if FIXTURE_ROOT.is_dir() else []


def setUpModule() -> None:
    if not (CAPTURES and ARCHIVE.is_file()):
        raise unittest.SkipTest("private real fixtures or SDK archive absent (both git-ignored)")


def seat_of(observation: Observation, faction: int) -> int:
    seats = [seat for seat, info in observation.role_and_grouping().items() if info.faction == faction]
    if len(seats) != 1:
        raise AssertionError(f"expected one seat of faction {faction}, found {len(seats)}")
    return seats[0]


class RealDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.captures = [load_capture(root) for root in CAPTURES]
        with zipfile.ZipFile(ARCHIVE) as outer:
            data = zipfile.ZipFile(io.BytesIO(outer.read(prov.DATA_ARCHIVE_MEMBER)))
            cls.costs = {}
            for capture in cls.captures:
                map_id = str(capture["manifest"]["map_id"])
                if map_id not in cls.costs:
                    cls.costs[map_id] = MoveCosts.from_raw(load_cost_bytes(data.read(f"Data/maps/map_{map_id}/cost.pickle")))

    def cases(self):
        for capture in self.captures:
            costs = self.costs[str(capture["manifest"]["map_id"])]
            for point, slots in capture["states"].items():
                for faction in (0, 1):
                    observation = Observation.from_raw(slots[faction], Origin.ENGINE)
                    yield point, faction, observation, slots[faction], costs

    def test_decisions_are_legal_and_stage_separated(self) -> None:
        count = 0
        for point, faction, observation, _, costs in self.cases():
            with self.subTest(point=point, faction=faction):
                decision = BaselinePolicy(costs).decide(observation, seat_of(observation, faction), faction, Memory())
                self.assertEqual(decision.trace.rejected, ())
                self.assertIsNone(decision.trace.error)
                types = [action["type"] for action in decision.actions]
                if observation.time().stage == Stage.DEPLOYMENT:
                    self.assertEqual(types, [333])
                else:
                    self.assertNotIn(333, types)
                count += 1
        self.assertEqual(count, 6 * len(self.captures))

    def test_first_play_state_is_active(self) -> None:
        for point, faction, observation, _, costs in self.cases():
            if point != "after-deployment":
                continue
            with self.subTest(faction=faction):
                decision = BaselinePolicy(costs).decide(observation, seat_of(observation, faction), faction, Memory())
                self.assertGreater(len(decision.actions), 0, [u.no_op_reason for u in decision.trace.units])

    def test_decisions_are_order_and_instance_independent(self) -> None:
        for point, faction, observation, raw, costs in self.cases():
            seat = seat_of(observation, faction)
            reference = digest(BaselinePolicy(costs).decide(observation, seat, faction, Memory()).trace)
            with self.subTest(point=point, faction=faction):
                for key in (1, 2, 5):
                    shuffled = Observation.from_raw(ds.reordered(raw, key), Origin.ENGINE)
                    self.assertEqual(digest(BaselinePolicy(costs).decide(shuffled, seat, faction, Memory()).trace),
                                     reference)


if __name__ == "__main__":
    unittest.main()
