"""Sprint 18 census functions on synthetic frames, and the committed public census file (no private data needed)."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import s18_census as sc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "s18-frontier-reset"
RED, BLUE = 0, 1


def unit(obj, color, hex_, *, type_=2, sub=0, path=(), speed=0, keep=0, stack=0, blood=4, weapons=(36,),
         close=0, remain=0):
    return {"obj_id": obj, "color": color, "type": type_, "sub_type": sub, "cur_hex": hex_, "move_path": list(path),
            "speed": speed, "keep": keep, "keep_remain_time": remain, "stack": stack, "blood": blood,
            "carry_weapon_ids": list(weapons), "close_combat": close, "basic_speed": 36, "move_state": 0}


def raw(step, units, *, valid=None, cities=None, judge=None, passengers=(), stage=2):
    return {"time": {"cur_step": step, "max_step": 2880, "stage": stage}, "operators": list(units),
            "passengers": list(passengers), "valid_actions": valid or {}, "cities": cities or [],
            "judge_info": judge or []}


def game(frames_red, frames_blue, events):
    return sc.Game("H0", "g", "s", {RED: frames_red, BLUE: frames_blue}, events, (RED, BLUE))


def judge(step, attacker, target, *, damage=1, distance=5, att_color=BLUE, tgt_color=RED, ele=0):
    return {"cur_step": step, "att_obj_id": attacker, "target_obj_id": target, "damage": damage, "distance": distance,
            "attack_color": att_color, "target_color": tgt_color, "type": "direct", "ele_diff": ele}


class FrameTest(unittest.TestCase):
    def test_frame_separates_own_enemy_and_aboard(self) -> None:
        r = raw(10, [unit(1, RED, 1010), unit(9, BLUE, 1020)], passengers=[unit(2, RED, 1010, type_=1)],
                valid={"1": {"6": [{"target_state": 4}]}}, cities=[{"coord": 1010, "flag": RED}])
        f = sc.frame_from_raw(3, r, RED, [{"obj_id": 1, "type": 1}], [1])
        self.assertEqual((sorted(f.own), sorted(f.enemies), sorted(f.aboard)), ([1], [9], [2]))
        self.assertEqual(f.valid, {1: {6: [{"target_state": 4}]}})
        self.assertEqual((f.k, f.cur_step, f.flags, f.concealment), (3, 10, {1010: RED}, [1]))

    def test_event_collector_keeps_the_first_decision_and_drops_zero_damage(self) -> None:
        c = sc.EventCollector()
        a, b = judge(5, 9, 1), judge(5, 9, 1, damage=0)
        c.add(2, [a, b])
        c.add(3, [dict(a)])
        self.assertEqual(c.events, [(2, a)])


class EventRowTest(unittest.TestCase):
    def setUp(self) -> None:
        # the attacker 9 is seen at steps 100 and 200 by red; the event is at step 500 (k 3)
        steps = [100, 200, 400, 500]
        self.red = [sc.frame_from_raw(k, raw(s, [unit(1, RED, 1010, keep=int(k == 2))] +
                                              ([unit(9, BLUE, 1020)] if s in (100, 200) else []),
                                              cities=[{"coord": 1010, "flag": RED}]), RED)
                    for k, s in enumerate(steps)]
        self.blue = [sc.frame_from_raw(k, raw(s, [unit(9, BLUE, 1020)]), BLUE) for k, s in enumerate(steps)]

    def row(self, step):
        g = game(self.red, self.blue, [(3, judge(step, 9, 1))])
        (r,) = sc.event_rows(g, RED)
        return r

    def test_seen_before_window_is_three_hundred_steps(self) -> None:
        self.assertTrue(self.row(500)["seen_before"])        # 200 is within [200, 500)
        self.assertFalse(self.row(501)["seen_before"])       # 200 is outside [201, 501)
        self.assertTrue(self.row(501)["ever_seen_before"])
        self.assertFalse(self.row(500)["seen_at_event"])

    def test_victim_state(self) -> None:
        r = self.row(500)
        self.assertEqual((r["victim_class"], r["moving"], r["on_objective"], r["aboard"]), ("vehicle", False, True, False))
        self.assertTrue(r["suppressed_before"])              # keep 1 at the decision before the event
        self.assertEqual(r["attacker_class"], "vehicle")
        self.assertEqual(r["attacker_observe"], 25)


class FamilyTest(unittest.TestCase):
    def test_t7c_concealable_needs_75_steps_and_no_path(self) -> None:
        def frames(path_at_event):
            out = []
            for k, s in enumerate((0, 74, 75, 76)):
                path = (1011,) if (k == 3 and path_at_event) else ()
                out.append(sc.frame_from_raw(k, raw(s, [unit(1, RED, 1010, path=path)]), RED, [],
                                             [1] if k == 0 else []))
            return out
        blue = [sc.frame_from_raw(k, raw(s, [unit(9, BLUE, 1030)]), BLUE) for k, s in enumerate((0, 74, 75, 76))]
        for step, path, expected in ((74, False, 0), (75, False, 1), (76, True, 0)):
            g = game(frames(path), blue, [(3, judge(step, 9, 1, distance=20))])
            out = sc.t7c(g, RED, sc.event_rows(g, RED))
            self.assertEqual(out["concealable_events"], expected, (step, path))
        g = game(frames(False), blue, [(3, judge(76, 9, 1, distance=20))])
        out = sc.t7c(g, RED, sc.event_rows(g, RED))
        self.assertEqual((out["concealable_ground_beyond_half_distance"], out["concealable_ground_beyond_half_equal_elevation"]),
                         (1, 1))
        g = game(frames(False), blue, [(3, judge(76, 9, 1, distance=12))])
        self.assertEqual(sc.t7c(g, RED, sc.event_rows(g, RED))["concealable_ground_beyond_half_distance"], 0)

    def test_t7c_e3b_exposure(self) -> None:
        red = [sc.frame_from_raw(0, raw(0, [unit(1, RED, 1010)]), RED, [], [1]),
               sc.frame_from_raw(1, raw(74, [unit(1, RED, 1010)]), RED, [{"obj_id": 1, "type": 1}]),
               sc.frame_from_raw(2, raw(75, [unit(1, RED, 1010)]), RED, [{"obj_id": 1, "type": 2}])]
        out = sc.t7c(game(red, red, []), RED, [])
        self.assertEqual((out["e3b_exposure_units"], out["e3b_exposure_actions"], out["units_ordered"]), (1, 1, 1))

    def test_threat_exposed(self) -> None:
        enemy = unit(9, BLUE, 1020, weapons=(36,))               # range 18 against vehicles
        self.assertEqual((sc.hex_distance(1020, 1030), sc.hex_distance(1020, 1040), sc.hex_distance(1020, 5045)), (10, 20, 45))
        far = sc.frame_from_raw(0, raw(0, [unit(1, RED, 5050), enemy]), RED)
        near = sc.frame_from_raw(0, raw(0, [unit(1, RED, 1030), enemy]), RED)
        outside = sc.frame_from_raw(0, raw(0, [unit(1, RED, 1040), enemy]), RED)
        unarmed = sc.frame_from_raw(0, raw(0, [unit(1, RED, 1030), unit(9, BLUE, 1020, weapons=())]), RED)
        empty = sc.frame_from_raw(0, raw(0, [unit(1, RED, 1030)]), RED)
        move = {"obj_id": 1, "type": 1, "move_path": [1041]}
        self.assertFalse(sc.threat_exposed(far, move))
        self.assertTrue(sc.threat_exposed(near, move))
        self.assertFalse(sc.threat_exposed(outside, {"obj_id": 1, "type": 1, "move_path": [1041]}))
        self.assertIsNone(sc.threat_exposed(unarmed, move))
        self.assertFalse(sc.threat_exposed(empty, move))
        self.assertTrue(sc.threat_exposed(far, {"obj_id": 1, "type": 1, "move_path": [5049, 1030]}))
        route = [5049, 5048, 5047, 5046, 5045, 1030]              # the threatened hex is sixth, beyond the first five
        self.assertFalse(sc.threat_exposed(far, {"obj_id": 1, "type": 1, "move_path": route}))
        self.assertTrue(sc.threat_exposed(far, {"obj_id": 1, "type": 1, "move_path": route[1:]}))

    def test_t6_counts(self) -> None:
        red = [sc.frame_from_raw(0, raw(0, [unit(1, RED, 1030, path=(1031,), speed=1), unit(9, BLUE, 1020)]), RED,
                                 [{"obj_id": 1, "type": 1, "move_path": [1031]}]),
               sc.frame_from_raw(1, raw(10, [unit(9, BLUE, 1020)]), RED)]
        blue = [sc.frame_from_raw(k, raw(s, [unit(9, BLUE, 1020)]), BLUE) for k, s in enumerate((0, 10))]
        g = game(red, blue, [(1, judge(5, 9, 1))])
        out = sc.t6(g, RED, sc.event_rows(g, RED))
        self.assertEqual(out["events_by_victim_state"], {"moving ground": 1})
        self.assertEqual((out["moving_ground_seen_before"], out["units_lost"], out["ground_units_lost_with_a_move_path"]),
                         (1, 1, 1))
        self.assertEqual((out["move_orders"], out["threat_exposed_orders"], out["threat_exposed_then_damaged"]), (1, 1, 1))

    def test_visibility_gaps(self) -> None:
        frames = [sc.frame_from_raw(k, raw(s, [unit(1, RED, 1010)] + ([unit(9, BLUE, 1020)] if seen else [])), RED)
                  for k, (s, seen) in enumerate(((0, 1), (10, 0), (30, 1), (40, 1), (50, 0)))]
        self.assertEqual(sc.visibility_gaps(frames), (1, [30]))

    def test_suppression_and_listing(self) -> None:
        frames = [sc.frame_from_raw(k, raw(s, [unit(1, RED, 1010, type_=1, sub=2, keep=keep, remain=150 * keep)],
                                           valid={1: {7: None}} if keep else {}), RED)
                  for k, (s, keep) in enumerate(((0, 0), (1, 1), (2, 1), (3, 0), (4, 1)))]
        out = sc.suppression(game(frames, frames, []), RED, [])
        self.assertEqual(out["onsets_by_class"], {"infantry": 2})
        self.assertEqual(out["keep_remain_time_at_onset"], [150, 150])
        self.assertEqual(out["remove_suppression_unit_decisions"], {"keep_1": 3})

    def test_fire_choice_and_lower_blood(self) -> None:
        valid = {1: {2: [{"target_obj_id": 8, "attack_level": 5}, {"target_obj_id": 9, "attack_level": 3}]}}
        f = sc.frame_from_raw(0, raw(0, [unit(1, RED, 1010), unit(8, BLUE, 1020, blood=4), unit(9, BLUE, 1021, blood=1)],
                                     valid=valid), RED, [{"obj_id": 1, "type": 2, "target_obj_id": 8}])
        self.assertEqual(sc.fire_choice(game([f], [f], []), RED),
                         {"shots": 1, "shots_with_two_or_more_targets": 1, "lower_blood_target_listed": 1})
        g = sc.frame_from_raw(0, raw(0, [unit(1, RED, 1010), unit(8, BLUE, 1020, blood=1), unit(9, BLUE, 1021, blood=1)],
                                     valid=valid), RED, [{"obj_id": 1, "type": 2, "target_obj_id": 8}])
        self.assertEqual(sc.fire_choice(game([g], [g], []), RED)["lower_blood_target_listed"], 0)

    def test_objective_defence_and_idle(self) -> None:
        frames = [sc.frame_from_raw(k, raw(s, [unit(1, RED, 1010), unit(2, RED, 1011, path=(1012,))],
                                           cities=[{"coord": 1010, "flag": flag}]), RED)
                  for k, (s, flag) in enumerate(((0, RED), (1, BLUE), (2, RED)))]
        out = sc.objective_defence(game(frames, frames, []), RED)
        self.assertEqual(out, {"objective_losses": 1, "losses_with_own_unit_on_it_before": 1, "held_at_end": 1})
        self.assertEqual(sc.idle(game(frames, frames, []), RED), {"vehicle_no_enemy": 3})

    def test_lost_units(self) -> None:
        frames = [sc.frame_from_raw(k, raw(k, [unit(1, RED, 1010)] if k < 2 else []), RED) for k in range(4)]
        self.assertEqual(sc.lost_units(frames), {1: 2})


class CensusSanitizerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("s18_census_script", ROOT / "scripts" / "s18_census.py")
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_keys_and_strings_are_checked_numbers_are_masked(self) -> None:
        p = self.script.public_problems
        self.assertEqual(p({"count": 1234}, {1234}), [])
        self.assertTrue(p({"note": "unit 1234 lost"}, {1234}))
        self.assertTrue(p({"1234": 1}, {1234}))
        self.assertTrue(p({"units": 3}, set()))
        self.assertTrue(p({"cur_hex": 3}, set()))


class PublicCensusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.census = json.loads((OUT / "census.json").read_text(encoding="utf-8"))
        cls.inputs = json.loads((OUT / "inputs.json").read_text(encoding="utf-8"))

    def test_consistency_checks_all_equal(self) -> None:
        checks = self.census["consistency"]
        self.assertEqual(len(checks), 10)
        self.assertTrue(all(c["equal"] for c in checks.values()))
        self.assertEqual(checks["H0 v2 differs from recorded v0"]["census"], 123)
        self.assertEqual(checks["HH baseline-v2 reconstruction equal"]["census"], 11524)

    def test_populations_and_pins(self) -> None:
        pops = self.census["populations"]
        self.assertEqual((pops["H0"]["games"], pops["H0"]["scenario_sides"], pops["HH"]["games"], pops["HI"]["games"]),
                         (8, 16, 4, 5))
        self.assertEqual((len(self.inputs["H0"]["games"]), len(self.inputs["HH"]["games"]), len(self.inputs["HI"]["games"])),
                         (8, 4, 5))
        self.assertEqual(self.inputs["R"]["records"], sum(self.inputs["R"]["records_by_folder"].values()))
        self.assertNotIn("baseline-v2-target-ownership-prevalence-1", self.inputs["R"]["records_by_folder"])
        import hashlib
        self.assertEqual(self.census["inputs_sha256"], hashlib.sha256((OUT / "inputs.json").read_bytes()).hexdigest())
        self.assertEqual(self.census["records"]["records"], self.inputs["R"]["records"])

    def test_public_files_carry_no_forbidden_key(self) -> None:
        from miaosuan_agent.evaluation.s12_screen import privacy_problems
        for name in ("census.json", "admission.json", "experiments.json", "scores.json", "selection.json", "inputs.json"):
            data = json.loads((OUT / name).read_text(encoding="utf-8"))
            if name == "inputs.json":       # file paths and digests only; "path" is its own field name
                continue
            self.assertEqual(privacy_problems(data), [], name)

    def test_no_candidate_identity_in_the_public_files(self) -> None:
        # the owner-approved whitelists of Sprints 12 and 17 keep candidate identities in their own folders
        for path in sorted(OUT.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            for needle in ("t9-batch-capacity-v3", "t9-delayed-post-stage-any-v6", "t9-capacity", "t4-artillery",
                           "t7-idle-concealment", "tactic-deployment-split", "ps1-probe-hook"):
                self.assertNotIn(needle, text, path.name)

    def test_opportunity_flags_cover_sixteen_sides(self) -> None:
        sides = self.census["opportunity_sides"]
        self.assertEqual(sides["of"], 16)
        self.assertTrue(all(0 <= v <= 16 for v in sides["sides_with_opportunity"].values()))
        for family in ("T2", "T3", "T5", "T6", "T7-C", "T8"):
            self.assertIn(family, sides["sides_with_opportunity"])


if __name__ == "__main__":
    unittest.main()
