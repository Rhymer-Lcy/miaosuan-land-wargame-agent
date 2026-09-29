from __future__ import annotations

import unittest

from miaosuan_agent.boundary import normalize_state
from miaosuan_agent.boundary.profile import (DETAIL_VERIFIED_SLOTS, DIRECTOR_ACTION_TYPES, DIRECTOR_KEY, PROFILE_ID,
                                             check_deployment_transition, check_state)
from tests.fixtures import synthetic as syn


def paths(report) -> list:
    return [deviation.path for deviation in report.deviations]


class CheckStateTest(unittest.TestCase):
    def test_synthetic_observed_shape_matches(self) -> None:
        report = check_state(syn.state())
        self.assertEqual(report.profile_id, PROFILE_ID)
        self.assertTrue(report.matches, report.deviations)

    def test_profile_is_stricter_than_the_boundary(self) -> None:
        sequence = syn.sequence_state()
        normalize_state(sequence)  # accepted
        self.assertEqual(paths(check_state(sequence)), ["state"])
        raw = syn.state()
        raw[2] = {}
        normalize_state(raw)  # accepted, extra slot preserved
        self.assertIn("state", paths(check_state(raw)))

    def test_json_round_trip_deviates(self) -> None:
        self.assertIn("state", paths(check_state(syn.json_round_trip(syn.state()))))

    def test_field_set_deviations(self) -> None:
        raw = syn.state()
        del raw[0]["communication"]
        del raw[-1]["actions"]
        found = paths(check_state(raw))
        self.assertIn("state[0]", found)
        self.assertIn("state[-1]", found)
        red_deviation = [d for d in check_state(raw).deviations if d.path == "state[0]"][0]
        self.assertIn("communication", red_deviation.actual)


@unittest.skipUnless(0 in DETAIL_VERIFIED_SLOTS, "red detail is part of the profile")
class RedDetailTest(unittest.TestCase):
    def deviations_after(self, mutate) -> list:
        raw = syn.state()
        mutate(raw[0])
        return paths(check_state(raw))

    def test_exact_types(self) -> None:
        self.assertIn("state[0].scenario_id", self.deviations_after(lambda o: o.__setitem__("scenario_id", True)))
        self.assertIn("state[0].time.tick", self.deviations_after(lambda o: o["time"].__setitem__("tick", 1)))
        self.assertIn("state[0].time.stage", self.deviations_after(lambda o: o["time"].__setitem__("stage", 3)))

    def test_grouping_and_actions(self) -> None:
        seat = f"state[0].role_and_grouping_info[{syn.RED_SEAT!r}]"
        self.assertIn(seat, self.deviations_after(lambda o: o["role_and_grouping_info"][syn.RED_SEAT].pop("end_deployment")))
        option = f"state[0].valid_actions[{syn.RED_UNIT!r}][6]"
        self.assertIn(option, self.deviations_after(lambda o: o["valid_actions"][syn.RED_UNIT].__setitem__(6, [4])))

    def test_scores_and_landmarks_key_sets(self) -> None:
        self.assertIn("state[0].scores", self.deviations_after(lambda o: o["scores"].pop("red_win")))
        self.assertIn("state[0].landmarks", self.deviations_after(lambda o: o["landmarks"].pop("fortifications")))

    def test_player_valid_actions_are_keyed_by_the_views_units(self) -> None:
        self.assertIn("state[0].valid_actions", self.deviations_after(
            lambda o: o["valid_actions"].__setitem__(DIRECTOR_KEY, {401: None})))


@unittest.skipUnless(-1 in DETAIL_VERIFIED_SLOTS, "all-seeing detail is part of the profile")
class GlobalDetailTest(unittest.TestCase):
    def deviations_after(self, mutate) -> list:
        raw = syn.state()
        mutate(raw[-1])
        return paths(check_state(raw))

    def test_director_options_are_expected(self) -> None:
        director = f"state[-1].valid_actions[{DIRECTOR_KEY}]"
        self.assertIn(director, self.deviations_after(lambda o: o["valid_actions"].pop(DIRECTOR_KEY)))
        self.assertIn(director, self.deviations_after(lambda o: o["valid_actions"][DIRECTOR_KEY].pop(404)))
        self.assertEqual(set(syn.state()[-1]["valid_actions"][DIRECTOR_KEY]), DIRECTOR_ACTION_TYPES)

    def test_unknown_unit_key_deviates(self) -> None:
        self.assertIn("state[-1].valid_actions",
                      self.deviations_after(lambda o: o["valid_actions"].__setitem__(900999, {1: None})))


class DeploymentTransitionTest(unittest.TestCase):
    def test_observed_transition(self) -> None:
        self.assertTrue(check_deployment_transition(syn.state(stage=1), syn.state(stage=2)).matches)

    def test_missing_transition_deviates(self) -> None:
        report = check_deployment_transition(syn.state(stage=1), syn.state(stage=1))
        self.assertFalse(report.matches)
        self.assertIn("state[0].time.stage", paths(report))


if __name__ == "__main__":
    unittest.main()
