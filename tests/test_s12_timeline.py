"""Per-game facts and stops of the Sprint 12 screen (``evaluation/s12_timeline.py``) on a stand-in game, with each
immediate stop S4 to S14 planted and required to fire, and every place outcome on synthetic states."""

from __future__ import annotations

import copy
import pickle
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from tests.fixtures import s12_engine as se  # noqa: E402

PLAY = 90
RULES = dict(sc.RULES, max_step=PLAY)
ENTRY = {"game_id": "synthetic.p07", "scenario_id": "2120531121", "condition": "C3", "red": INERT_ID,
         "blue": sc.V3_ID, "screen_position": 7}


def stand_in():
    record, t9, v3, timeline, windows = se.play_screen_game(play_steps=PLAY)
    record["session_close"] = {"integrity": {"ok": True}}
    return record, t9, v3, timeline, windows


class Game:
    """One stand-in game's inputs, copied for each planted defect."""

    original = None

    def __init__(self) -> None:
        if Game.original is None:
            Game.original = stand_in()
        self.record, self.t9, self.v3, self.timeline, self.windows = copy.deepcopy(Game.original)

    def facts(self, entry=ENTRY, **options):
        return tl.analyze(entry, "s12-v3-adverse-1", self.record, self.t9, self.v3, self.timeline, self.windows,
                          se.costs(), rules=RULES, **options)

    def first_selection(self):
        return next(k for k, e in enumerate(self.timeline["steps"]) if e["s12"]["11"]["allocation"]["selected"])

    def seat_observation(self, k):
        return pickle.loads(self.windows["samples"][k]["seats"][11]["observation"])

    def set_seat_observation(self, k, raw):
        self.windows["samples"][k]["seats"][11]["observation"] = pickle.dumps(raw, protocol=4)


class CleanGameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = Game().facts()

    def test_no_stop_in_a_clean_game(self) -> None:
        self.assertEqual(self.facts["stops"], {})

    def test_places_and_their_outcomes(self) -> None:
        places = self.facts["places"]
        self.assertEqual(places["selected"], 8)
        self.assertEqual(sum(places["outcomes"].values()), 8)
        self.assertEqual(places["outcomes"]["OCCUPIED"], 2)
        self.assertEqual(places["arrival_delay"], {"n": 8, "min": 0, "median": 0, "max": 0})
        for place in self.facts["places_private"]:
            self.assertEqual(place["arrival_slack"], PLAY - place["arrival_step"])
            self.assertEqual(place["arrival_delay"], place["arrival_step"] - place["predicted_arrival"])
            self.assertLessEqual(place["arrival_step"], place["path_end_step"])
        self.assertEqual(self.facts["premise"]["arrivals_earlier_than_free_flow"], 0)

    def test_objectives_staging_and_commitments(self) -> None:
        self.assertEqual(self.facts["capture_order"], ["50-point objective A", "80-point objective A"])
        self.assertEqual(self.facts["fifth_objective_last_to_own_step"],
                         self.facts["objectives"]["80-point objective A"]["last_to_own_step"])
        self.assertGreater(self.facts["objectives"]["80-point objective A"]["last_to_own_step"],
                           self.facts["objectives"]["50-point objective A"]["last_to_own_step"])
        self.assertTrue(self.facts["fifth_objective_attributed_to_v3_selection"])
        self.assertEqual(self.facts["objectives_at_end"], 2)
        self.assertEqual(self.facts["staging"]["staged_moves"], 4)
        self.assertLessEqual(self.facts["commitments"]["max_counted"], 4)
        self.assertEqual(self.facts["consistency"]["differences"], 0)
        self.assertEqual(self.facts["occupation"]["responses"], {"accepted": 2})
        self.assertEqual(self.facts["adverse_class"], "NOT_REPAIRED")  # the stand-in scores nothing

    def test_the_public_form_carries_no_unit_or_hex(self) -> None:
        public = tl.public(self.facts)
        units = {p["unit"] for p in self.facts["places_private"]}
        self.assertTrue(units)
        self.assertEqual(sc.privacy_problems(public, private_values=units), [])
        self.assertNotIn("places_private", public)
        self.assertNotIn("holds_private", public)
        self.assertEqual(public["stops"], {})


class PlantedStopTest(unittest.TestCase):
    def assertStop(self, facts, code):
        self.assertIn(code, facts["stops"], facts["stops"])

    def test_s4_contract_error_and_incomplete_game(self) -> None:
        game = Game()
        game.record["seats"][1]["contract_errors"] = 1
        self.assertStop(game.facts(), "S4")
        game = Game()
        game.record["status"] = "CAPPED"
        self.assertStop(game.facts(), "S4")

    def test_s5_addon_error(self) -> None:
        game = Game()
        game.v3["v3"]["errors"] = [{"k": 3, "faction": 1, "error": "planted"}]
        self.assertStop(game.facts(), "S5")
        game = Game()
        game.timeline["steps"][game.first_selection()]["s12"]["11"]["allocation"]["error"] = "planted"
        self.assertStop(game.facts(), "S5")

    def test_s6_replay_mismatch(self) -> None:
        game = Game()
        game.record["seats"][1]["replay_mismatches"] = 1
        self.assertStop(game.facts(), "S6")

    def test_s7_observer_reconstruction_and_capture(self) -> None:
        game = Game()
        game.timeline["consistency_errors"] = [{"k": 1, "seat": 11, "actions": False}]
        self.assertStop(game.facts(), "S7")
        game = Game()
        game.record["observer_errors"] = ["planted"]
        self.assertStop(game.facts(), "S7")
        game = Game()
        self.assertStop(game.facts(capture_digests={"timeline.pkl": ("a" * 64, "b" * 64)}), "S7")
        game = Game()
        game.timeline["reconstructed_decisions"] -= 1
        self.assertStop(game.facts(), "S7")
        game = Game()
        del game.timeline["steps"][5]["s12"]["11"]
        self.assertStop(game.facts(), "S7")

    def test_s8_counted_places_above_four(self) -> None:
        game = Game()
        allocation = game.timeline["steps"][game.first_selection()]["s12"]["11"]["allocation"]
        coord = next(iter(allocation["objectives"]))
        allocation["objectives"][coord]["physical"] = 2
        self.assertStop(game.facts(), "S8")

    def test_s8_more_than_four_units_on_one_hex(self) -> None:
        game = Game()
        raw = game.seat_observation(10)
        own = [u for u in raw["operators"] if u.get("color") == 1]
        for unit in own[:5]:
            unit["cur_hex"] = 202
        game.set_seat_observation(10, raw)
        self.assertStop(game.facts(), "S8")

    def test_s8_a_kept_move_that_pushes_the_objective_above_four(self) -> None:
        game = Game()
        k = game.first_selection()
        entry = game.timeline["steps"][k]
        staged = next(a for a in entry["submitted"] if a["seat"] == 11 and a["action"].get("type") == 1
                      and tuple(a["action"]["move_path"]) in {tuple(p) for p in
                                                              entry["s12"]["11"]["allocation"]["staged"].values()})
        baseline = next(b for b in entry["s12"]["11"]["baseline_actions"]
                        if b.get("obj_id") == staged["action"]["obj_id"])
        staged["action"]["move_path"] = list(baseline["move_path"])
        facts = game.facts()
        self.assertStop(facts, "S8")

    def test_s9_staging_endpoint_above_three(self) -> None:
        game = Game()
        k = game.first_selection()
        staged_path = next(iter(game.timeline["steps"][k]["s12"]["11"]["allocation"]["staged"].values()))
        hex_ = staged_path[-1]
        raw = game.seat_observation(k)
        extra = copy.deepcopy(raw["operators"][0])
        added = sum(1 for path in game.timeline["steps"][k]["s12"]["11"]["allocation"]["staged"].values()
                    if path[-1] == hex_)
        for n in range(sc.RULES["stage_cap"] + 1 - added):
            raw["operators"].append(dict(extra, obj_id=940001 + n, cur_hex=hex_, move_path=[], color=1, type=2))
        game.set_seat_observation(k, raw)
        self.assertStop(game.facts(), "S9")

    def staged_action(self, game):
        k = game.first_selection()
        entry = game.timeline["steps"][k]
        staged = {tuple(p) for p in entry["s12"]["11"]["allocation"]["staged"].values()}
        action = next(a["action"] for a in entry["submitted"] if a["seat"] == 11 and a["action"].get("type") == 1
                      and tuple(a["action"]["move_path"]) in staged)
        baseline = next(b for b in entry["s12"]["11"]["baseline_actions"] if b.get("obj_id") == action["obj_id"])
        return action, baseline

    def test_s10_a_staged_move_that_is_not_a_prefix(self) -> None:
        game = Game()
        action, baseline = self.staged_action(game)
        action["move_path"] = list(baseline["move_path"][1:len(action["move_path"]) + 1])
        self.assertStop(game.facts(), "S10")

    def test_s11_cross_objective_redirection(self) -> None:
        game = Game()
        action, baseline = self.staged_action(game)
        action["move_path"] = list(baseline["move_path"][:-1]) + [se.FAR]
        self.assertStop(game.facts(), "S11")

    def test_s12_invented_move_and_dropped_unrelated_action(self) -> None:
        game = Game()
        found = None
        for k, entry in enumerate(game.timeline["steps"]):
            row = entry["s12"]["11"]
            if not any(a.get("type") == 1 for a in row["baseline_actions"]):
                continue
            acting = {a.get("obj_id") for a in row["baseline_actions"]}
            others = [u for u in game.seat_observation(k)["operators"] if u.get("color") == 1
                      and u["obj_id"] not in acting]
            if others:
                found = (k, others[0]["obj_id"])
                break
        self.assertIsNotNone(found, "the stand-in game has a move decision with an own unit baseline-v2 leaves alone")
        k, unit = found
        game.timeline["steps"][k]["submitted"].append(
            {"seat": 11, "faction": 1, "j": 99, "action": {"actor": 11, "obj_id": unit, "type": 1, "move_path": [201]}})
        self.assertStop(game.facts(), "S12")
        game = Game()
        game.timeline["steps"][k]["submitted"].append(
            {"seat": 11, "faction": 1, "j": 99, "action": {"actor": 11, "obj_id": unit, "type": 5}})
        self.assertStop(game.facts(), "S12")

    def test_s13_gate_rejection_and_unknown_refusal(self) -> None:
        game = Game()
        game.record["seats"][1]["gate_rejections"] = {"planted": 1}
        self.assertStop(game.facts(), "S13")
        game = Game()
        game.record["seats"][1]["refusal_facts"] = [{"action_type": 1, "code": 999, "message_class": "Planted",
                                                     "count": 1}]
        self.assertStop(game.facts(), "S13")
        game = Game()
        game.record["seats"][1]["refusal_facts"] = [{"action_type": 2, "code": 516, "message_class":
                                                     "CantShootToDiedBop", "count": 1}]
        self.assertNotIn("S13", game.facts()["stops"])
        game = Game()
        game.record["seats"][1]["refusal_facts"] = [{"action_type": 1, "code": 999, "message_class": "Planted",
                                                     "count": 1}]
        self.assertNotIn("S13", game.facts(extra_known=[(1, 999, "Planted")])["stops"])

    def test_s1_session_integrity(self) -> None:
        game = Game()
        game.record["session_close"] = {"integrity": {"ok": False}}
        self.assertStop(game.facts(), "S1")

    def test_a_planted_stop_is_not_reported_without_its_defect(self) -> None:
        self.assertEqual(Game().facts()["stops"], {})


class S14Test(unittest.TestCase):
    names = {1: "80-point objective A", 2: "50-point objective A"}

    def hold(self, **changes):
        row = {"objective": 1, "k": 10, "cur_step": 10, "free_flow": 100, "physical": 0, "holders": [7, 8]}
        row.update(changes)
        return row

    def history(self, own=False):
        return {1: {"own_at_end": own}, 2: {"own_at_end": True}}

    def test_fires_behind_places_never_honoured(self) -> None:
        never = lambda u, c, j: None  # noqa: E731
        self.assertEqual(len(tl.s14_findings("2120531121 C3", self.history(), [self.hold()], never, self.names)), 1)

    def test_does_not_fire_otherwise(self) -> None:
        never = lambda u, c, j: None  # noqa: E731
        arrived = lambda u, c, j: 500 if u == 8 else None  # noqa: E731
        cases = [("1930331196 C3", self.history(), [self.hold()], never),
                 ("2120531121 C3", self.history(own=True), [self.hold()], never),
                 ("2120531121 C3", self.history(), [self.hold(physical=1)], never),
                 ("2120531121 C3", self.history(), [self.hold(holders=[])], never),
                 ("2120531121 C3", self.history(), [self.hold()], arrived),
                 ("2120531121 C3", self.history(), [self.hold(objective=2)], never),
                 ("2120531121 C3", self.history(), [self.hold(free_flow=None)], never)]
        for config, history, holds, arrival in cases:
            self.assertEqual(tl.s14_findings(config, history, holds, arrival, self.names), [], (config, holds))

    def test_reaches_the_stop_codes(self) -> None:
        game = Game()
        allocation = game.timeline["steps"][game.first_selection()]["s12"]["11"]["allocation"]
        info = allocation["objectives"][str(se.NEAR)]
        info["selected"], info["mover_bounds"] = [], {"999001": 5}
        final = pickle.loads(game.windows["final"]["global"])
        for city in final["cities"]:
            city["flag"] = -1
        game.windows["final"]["global"] = pickle.dumps(final, protocol=4)
        facts = game.facts()
        self.assertIn("S14", facts["stops"])
        self.assertEqual(sc.decide("A1", [facts], expected=1)["stops"][-1]["code"], "S14")


class OutcomeTest(unittest.TestCase):
    def state(self, cur_step, units=None, flags=None, valid=None, present=None):
        s = tl.State.__new__(tl.State)
        s.cur_step, s.stage, s.max_step = cur_step, 2, 100
        s.units = units or {}
        s.kinds = {u: 2 for u in s.units}
        s.present = set(s.units) if present is None else present
        s.flags = flags or {5: -1}
        s.valid = valid or {}
        return s

    def outcome(self, states, submitted=(), feedback=()):
        steps = [{"submitted": [], "feedback": []} for _ in range(len(states) - 1)]
        for j, action in submitted:
            steps[j]["submitted"].append({"seat": 11, "action": action})
        for j, entry in feedback:
            steps[j]["feedback"].append(entry)
        place = {"unit": 7, "objective": 5, "k": 0, "predicted_arrival": 2}
        return tl.place_outcome(states, steps, 11, 1, place)

    def at(self, hex_, path=(), stop=0):
        return {7: (hex_, tuple(path), stop, 0)}

    def test_every_outcome(self) -> None:
        moving = self.at(3, (4, 5))
        lost = [self.state(0, moving), self.state(1, {}, present=set()), self.state(2, {}, present=set())]
        self.assertEqual(self.outcome(lost)["outcome"], "LOST")
        never = [self.state(0, moving), self.state(1, moving), self.state(2, moving)]
        self.assertEqual(self.outcome(never)["outcome"], "NEVER_ARRIVED")
        occupy = {"actor": 11, "obj_id": 7, "type": 5}
        occupied = [self.state(0, moving), self.state(2, self.at(5)), self.state(3, self.at(5), {5: 1}),
                    self.state(4, self.at(4), {5: 1})]
        result = self.outcome(occupied, [(1, occupy)], [(1, {"message": occupy})])
        self.assertEqual((result["outcome"], result["occupation_response"], result["arrival_delay"]),
                         ("OCCUPIED", "accepted", 0))
        refused = self.outcome(occupied[:2] + [self.state(3, self.at(5)), self.state(4, self.at(5), {5: 1})],
                               [(1, occupy)], [(1, {"message": occupy, "error": {"code": 1804}})])
        self.assertEqual((refused["outcome"], refused["occupation_response"]), ("HELD", "1804"))
        other_unit = self.outcome(occupied[:2] + [self.state(3, self.at(5), {5: 1}), self.state(4, self.at(5), {5: 1})],
                                  [(1, occupy)], [(1, {"message": occupy, "error": {"code": 1804}})])
        self.assertEqual(other_unit["outcome"], "HELD")
        redundant = [self.state(0, moving), self.state(2, self.at(5), {5: 1}), self.state(3, self.at(4), {5: 1})]
        self.assertEqual(self.outcome(redundant)["outcome"], "REDUNDANT")
        late = [self.state(0, moving), self.state(98, self.at(5)), self.state(100, self.at(5))]
        result = self.outcome(late)
        self.assertEqual((result["outcome"], result["arrival_slack"], result["arrival_delay"]), ("TOO_LATE", 2, 96))
        other = [self.state(0, moving), self.state(2, self.at(5)), self.state(3, self.at(4), {5: 1})]
        self.assertEqual(self.outcome(other)["outcome"], "ARRIVED_NOT_DECISIVE")

    def test_path_end_stationarity_and_listing_are_separate(self) -> None:
        states = [self.state(0, self.at(3, (4, 5))), self.state(2, self.at(5, (5,))), self.state(3, self.at(5)),
                  self.state(78, self.at(5, (), 1), valid={7: {5}}), self.state(80, self.at(5, (), 1))]
        result = self.outcome(states)
        self.assertEqual((result["arrival_step"], result["path_end_step"], result["stationary_step"],
                          result["first_occupation_listing_step"]), (2, 3, 78, 78))


if __name__ == "__main__":
    unittest.main()
