"""Contract checks against private fixtures captured from the real engine.

The fixtures are derived from SDK scenario data that carries no redistribution license, so they
are git-ignored and exist only on machines that ran a capture
(``local/contract-fixtures/sdk-<version>/``). Without them every test here is skipped.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Iterator, Tuple

from miaosuan_agent import sdk_provenance as prov
from miaosuan_agent.boundary import ContractError, Observation, Origin, StateForm, normalize_state
from miaosuan_agent.boundary.profile import check_deployment_transition, check_state
from miaosuan_agent.contract_capture import load_capture
from miaosuan_agent.engine_smoke import CAPTURE_POINTS
from miaosuan_agent.fingerprint import Detail, digest, fingerprint

REPO = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO / "local" / "contract-fixtures" / f"sdk-{prov.ENGINE_VERSION}"
CAPTURES = sorted(p.parent for p in FIXTURE_ROOT.glob("*/manifest.json")) if FIXTURE_ROOT.is_dir() else []
SLOTS = {"red": 0, "blue": 1, "global": -1}


def setUpModule() -> None:
    if not CAPTURES:
        raise unittest.SkipTest(f"no private real fixtures under {FIXTURE_ROOT.relative_to(REPO).as_posix()} "
                                "(git-ignored; created only by an engine capture on a machine holding the SDK)")


def canonical(observation: Observation) -> Tuple[Any, ...]:
    time_info = observation.time()
    return (
        (time_info.cur_step, time_info.stage, time_info.tick, time_info.max_time, time_info.max_step),
        tuple(sorted(unit.obj_id for unit in observation.operators())),
        {obj_id: dict(actions) for obj_id, actions in observation.valid_actions().items()},
        {seat: (info.role, info.operators, info.faction, info.end_deployment)
         for seat, info in observation.role_and_grouping().items()},
        observation.communication(), observation.scenario_id(), observation.terrain_id(),
    )


def distinctive_values(value: Any) -> Iterator[Any]:
    """Scalar *values* (never field names) specific enough to reveal scenario content if copied."""
    if isinstance(value, dict):
        for item in value.values():
            yield from distinctive_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from distinctive_values(item)
    elif isinstance(value, str) and len(value) >= 2:
        yield value
    elif isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 1000:
        yield value


class RealFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = [(root, load_capture(root)) for root in CAPTURES]  # verifies every file digest

    def each_state(self) -> Iterator[Tuple[str, str, Any]]:
        for root, capture in self.loaded:
            for point, state in capture["states"].items():
                yield root.name, point, state

    def test_captures_are_complete_and_faithful(self) -> None:
        for root, capture in self.loaded:
            manifest = capture["manifest"]
            with self.subTest(capture=root.name):
                self.assertEqual(manifest["points"], list(CAPTURE_POINTS))
                self.assertEqual(len(manifest["entries"]), len(SLOTS) * len(CAPTURE_POINTS))
                self.assertEqual(manifest["inexact_values"], [])
                self.assertEqual(manifest["engine_version"], prov.ENGINE_VERSION)
                self.assertEqual(manifest["run_status"], "PASS")

    def test_accepted_contract_holds(self) -> None:
        for name, point, state in self.each_state():
            with self.subTest(capture=name, point=point):
                self.assertIs(normalize_state(state, Origin.ENGINE).form, StateForm.MAPPING)

    def test_observed_profile_holds(self) -> None:
        for name, point, state in self.each_state():
            with self.subTest(capture=name, point=point):
                report = check_state(state)
                self.assertTrue(report.matches, report.deviations[:5])

    def test_stages_and_deployment_transition(self) -> None:
        for root, capture in self.loaded:
            states = capture["states"]
            stages = {point: normalize_state(states[point]).red.time().stage for point in CAPTURE_POINTS}
            with self.subTest(capture=root.name):
                self.assertEqual(stages, {"setup": 1, "after-deployment": 2, "play-step": 2})
                self.assertTrue(check_deployment_transition(states["setup"], states["after-deployment"]).matches)
                for slot in ("red", "blue"):
                    before = normalize_state(states["setup"]).observation(SLOTS[slot]).role_and_grouping()
                    after = normalize_state(states["after-deployment"]).observation(SLOTS[slot]).role_and_grouping()
                    self.assertTrue(before and all(info.end_deployment is False for info in before.values()))
                    self.assertTrue(all(info.end_deployment is True for info in after.values()))

    def test_json_round_trip_through_the_boundary(self) -> None:
        for name, point, state in self.each_state():
            for slot, key in SLOTS.items():
                raw = state[key]
                transported = json.loads(json.dumps(raw))
                with self.subTest(capture=name, point=point, slot=slot):
                    engine = Observation.from_raw(raw, Origin.ENGINE).validate()
                    json_ = Observation.from_raw(transported, Origin.JSON, path="json").validate()
                    self.assertEqual(canonical(engine), canonical(json_))
                    if engine.valid_actions():
                        with self.assertRaises(ContractError):
                            Observation.from_raw(transported, Origin.ENGINE).valid_actions()

    def test_fingerprints_are_reproducible(self) -> None:
        for root, capture in self.loaded:
            for entry in capture["manifest"]["entries"]:
                raw = capture["states"][entry["point"]][SLOTS[entry["slot"]]]
                with self.subTest(capture=root.name, point=entry["point"], slot=entry["slot"]):
                    self.assertEqual(digest(fingerprint(raw, Detail.PRIVATE)), entry["fingerprint_private_digest"])
                    self.assertEqual(digest(fingerprint(raw, Detail.PUBLIC)), entry["fingerprint_public_digest"])

    def test_public_fingerprint_carries_no_scenario_values(self) -> None:
        for name, point, state in self.each_state():
            for slot, key in SLOTS.items():
                text = json.dumps(fingerprint(state[key], Detail.PUBLIC), ensure_ascii=False)
                values = set(distinctive_values(state[key]))
                with self.subTest(capture=name, point=point, slot=slot):
                    self.assertTrue(values)
                    for value in values:
                        if isinstance(value, str):
                            self.assertNotIn(json.dumps(value, ensure_ascii=False), text)
                        else:
                            self.assertIsNone(re.search(rf"(?<![0-9]){value}(?![0-9])", text))


if __name__ == "__main__":
    unittest.main()
