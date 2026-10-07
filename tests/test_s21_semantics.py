"""Sprint 21: synthetic tests of the direct-fire adjudication-semantics audit (``docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md``).

Every boundary of the registered rules is exercised on hand-made rows: pairing, K2, the K4 table mapping and the
probability-law rule, the K5 relations and their identification, the K6 tests, per-class sufficiency, the first-match
disposition and the conditional T11 completion. Where the local documentation snapshot exists (the workstation), the
transcribed tables and the quotations are checked against it again.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from miaosuan_agent.evaluation import s21_semantics as sm

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / sm.SNAPSHOT


def shot(seat=11, faction=1, obj=101, target=202, weapon=36, j=0, type_=2):
    return {"seat": seat, "faction": faction, "j": j,
            "action": {"actor": seat, "obj_id": obj, "target_obj_id": target, "weapon_id": weapon, "type": type_}}


def echo(seat=11, obj=101, target=202, weapon=36, error=None, type_=2):
    entry = {"cur_step": 5, "message": {"actor": seat, "obj_id": obj, "target_obj_id": target, "weapon_id": weapon,
                                        "type": type_}}
    if error:
        entry["error"] = {"code": 516, "message": "x"}
    return entry


def record(att=101, target=202, wp=36, **extra):
    return {"att_obj_id": att, "target_obj_id": target, "wp_id": wp, "type": sm.DIRECT_FIRE_TYPE, **extra}


class PairingTest(unittest.TestCase):
    def test_one_accepted_shot_one_record(self) -> None:
        out = sm.pair_step([shot()], [echo()], [record()])
        self.assertEqual(out["shots"][0]["status"], sm.PAIRED)
        self.assertEqual(out["record_status"], [sm.RECORD_PAIRED])
        self.assertEqual(out["problems"], [])

    def test_refused_shot_without_record(self) -> None:
        out = sm.pair_step([shot()], [echo(error=True)], [])
        self.assertEqual(out["shots"][0]["status"], sm.REFUSED)
        self.assertEqual(out["problems"], [])

    def test_refused_shot_with_record_is_an_integrity_failure(self) -> None:
        out = sm.pair_step([shot()], [echo(error=True)], [record()])
        self.assertEqual(out["shots"][0]["status"], sm.REFUSED_WITH_RECORD)
        self.assertEqual([k for k, _ in out["problems"]], [sm.REFUSED_WITH_RECORD])
        self.assertEqual(out["record_status"], [sm.RECORD_UNMATCHED])

    def test_duplicate_judge_rows_are_not_paired(self) -> None:
        out = sm.pair_step([shot()], [echo()], [record(damage=1), record(damage=1)])
        self.assertEqual(out["shots"][0]["status"], sm.AMBIGUOUS)
        self.assertEqual(out["record_status"], [sm.RECORD_AMBIGUOUS, sm.RECORD_AMBIGUOUS])
        self.assertEqual(out["problems"], [])

    def test_a_record_claimed_twice_is_never_paired(self) -> None:
        out = sm.pair_step([shot(j=0), shot(j=1)], [echo()], [record()])
        # two identical submitted shots of one seat: neither the echo nor the record can be attributed
        self.assertTrue(all(s["status"] == sm.ACCEPTANCE_UNKNOWN for s in out["shots"]))
        self.assertNotIn(sm.RECORD_PAIRED, out["record_status"])
        out = sm.pair_step([shot(j=0), shot(j=1)], [echo(), echo()], [record()])
        self.assertTrue(all(s["status"] == sm.ACCEPTANCE_UNKNOWN for s in out["shots"]))

    def test_record_claimed_by_two_accepted_shots(self) -> None:
        # two seats, same unit/target/weapon key (synthetic): both accepted, one record
        out = sm.pair_step([shot(seat=1), shot(seat=11)], [echo(seat=1), echo(seat=11)], [record()])
        self.assertEqual([s["status"] for s in out["shots"]], [sm.AMBIGUOUS, sm.AMBIGUOUS])
        self.assertIn(sm.CLAIMED_TWICE, [k for k, _ in out["problems"]])
        self.assertEqual(out["record_status"], [sm.RECORD_AMBIGUOUS])

    def test_mismatched_shooter_target_or_weapon_is_rejected(self) -> None:
        for rec in (record(att=999), record(target=999), record(wp=999)):
            out = sm.pair_step([shot()], [echo()], [rec])
            self.assertEqual(out["shots"][0]["status"], sm.ACCEPTED_NO_RECORD)
            self.assertEqual([k for k, _ in out["problems"]], [sm.ACCEPTED_NO_RECORD])
            self.assertEqual(out["record_status"], [sm.RECORD_UNMATCHED])

    def test_acceptance_unknown_without_or_with_two_echoes_or_another_actor(self) -> None:
        for fb in ([], [echo(), echo()], [echo(seat=1)]):
            out = sm.pair_step([shot()], fb, [record()])
            self.assertEqual(out["shots"][0]["status"], sm.ACCEPTANCE_UNKNOWN)
            self.assertEqual([k for k, _ in out["problems"]], [sm.ACCEPTANCE_UNKNOWN])

    def test_non_shoot_actions_and_echoes_are_ignored(self) -> None:
        out = sm.pair_step([shot(type_=1), shot()], [echo(type_=1), echo()], [record()])
        self.assertEqual(len(out["shots"]), 1)
        self.assertEqual(out["shots"][0]["status"], sm.PAIRED)

    def test_listed_level(self) -> None:
        va = {101: {2: [{"target_obj_id": 202, "weapon_id": 36, "attack_level": 7},
                        {"target_obj_id": 203, "weapon_id": 36, "attack_level": 5}]}}
        self.assertEqual(sm.listed_level(va, 101, 202, 36), ("listed", 7))
        self.assertEqual(sm.listed_level(va, 101, 202, 37), ("missing", None))
        self.assertEqual(sm.listed_level({"101": {"2": va[101][2]}}, 101, 203, 36), ("listed", 5))
        va[101][2].append({"target_obj_id": 202, "weapon_id": 36, "attack_level": 6})
        self.assertEqual(sm.listed_level(va, 101, 202, 36), ("ambiguous", None))
        self.assertEqual(sm.listed_level({}, 101, 202, 36), ("missing", None))


def k2row(listed, judged, ele=0, cls=sm.VEHICLE):
    return {"listed": listed, "judged": judged, "ele_diff": ele, "att_obj_blood": 2, "weapon": 36,
            "shooter_class": sm.VEHICLE, "target_class": cls}


class K2Test(unittest.TestCase):
    def test_equality_with_two_elevations_is_supported(self) -> None:
        out = sm.k2_summary([k2row(5, 5, 0), k2row(7, 7, -1)], {0, -1})
        self.assertEqual(out["status"], sm.K2_SUPPORTED)
        self.assertEqual((out["n_both_levels"], out["equal"], out["different"]), (2, 2, 0))
        self.assertEqual(out["by_target_class"][sm.VEHICLE], sm.K2_SUPPORTED)
        self.assertEqual(out["by_target_class"][sm.AIRCRAFT], "UNTESTED")

    def test_mismatch_refutes(self) -> None:
        out = sm.k2_summary([k2row(5, 5, 0), k2row(7, 6, -1, sm.INFANTRY)], {0, -1})
        self.assertEqual(out["status"], sm.K2_REFUTED)
        self.assertEqual(out["difference_distribution"], {"difference_0": 1, "difference_minus_1": 1})
        self.assertEqual(out["by_target_class"][sm.INFANTRY], sm.K2_REFUTED)
        self.assertEqual(out["subgroups"]["ele_diff"]["ele_diff_minus_1"], {"n": 1, "equal": 0})

    def test_single_elevation_subgroup_is_unresolved_when_the_corpus_has_more(self) -> None:
        out = sm.k2_summary([k2row(5, 5, 0), k2row(6, 6, 0)], {0, 2})
        self.assertEqual(out["status"], sm.K2_UNRESOLVED)
        self.assertFalse(out["elevation_coverage"])
        self.assertEqual(sm.k2_summary([k2row(5, 5, 0)], {0})["status"], sm.K2_SUPPORTED)

    def test_missing_levels(self) -> None:
        out = sm.k2_summary([k2row(None, 5), k2row(5, None), k2row(4, 4, 1), k2row(3, 3, 0)], {0, 1})
        self.assertEqual((out["missing_listed"], out["missing_judged"], out["n_both_levels"]), (1, 1, 2))
        self.assertEqual(out["status"], sm.K2_SUPPORTED)
        self.assertEqual(sm.k2_summary([k2row(None, 5)], {0})["status"], sm.K2_UNRESOLVED)


class K4TableTest(unittest.TestCase):
    def test_personnel_cells(self) -> None:
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 1, 2, 1), (sm.PERSONNEL_TABLE, sm.SUPPRESSION, None))
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 5, 2, 1), (sm.PERSONNEL_TABLE, sm.NUMERIC, 1))
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 10, 11, 1), (sm.PERSONNEL_TABLE, sm.NUMERIC, 2))
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 1, 3, 1), (sm.PERSONNEL_TABLE, sm.NO_EFFECT, None))
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 4, 10, 1), (sm.PERSONNEL_TABLE, sm.SUPPRESSION, None))

    def test_vehicle_cells_follow_the_shooter_count_columns(self) -> None:
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 1, 2, 1), (sm.VEHICLE_TABLE, sm.NUMERIC, 1))
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 1, 2, 2), (sm.VEHICLE_TABLE, sm.NO_EFFECT, None))
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 1, 4, 2), (sm.VEHICLE_TABLE, sm.NUMERIC, 1))
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 10, 2, 5), (sm.VEHICLE_TABLE, sm.NUMERIC, 5))
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 10, 2, 1), (sm.VEHICLE_TABLE, sm.NUMERIC, 1))
        self.assertEqual(sm.raw_cell(sm.FORTIFICATION, 36, 10, 2, 5), (sm.VEHICLE_TABLE, sm.NUMERIC, 5))

    def test_infantry_light_weapon_against_a_vehicle_reads_the_personnel_table(self) -> None:
        self.assertEqual(sm.raw_cell(sm.VEHICLE, sm.INFANTRY_LIGHT_WEAPON, 5, 2, 3)[0], sm.PERSONNEL_TABLE)
        self.assertEqual(sm.raw_cell(sm.FORTIFICATION, sm.INFANTRY_LIGHT_WEAPON, 5, 2, 3)[0], sm.PERSONNEL_TABLE)

    def test_air_and_other(self) -> None:
        self.assertEqual(sm.raw_cell(sm.AIRCRAFT, 1, 11, 7, 1), (sm.AIR_TABLE, sm.ANNIHILATION, None))
        self.assertEqual(sm.raw_cell(sm.AIRCRAFT, 1, 10, 7, 1), (sm.AIR_TABLE, sm.NO_EFFECT, None))
        self.assertEqual(sm.raw_cell(sm.OTHER, 1, 10, 7, 1), (sm.NO_TABLE, sm.NO_TABLE, None))

    def test_out_of_table(self) -> None:
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 11, 2, 1)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 0, 2, 1)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, 5, 13, 1)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 5, 2, 6)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 11, 2, 1)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.VEHICLE, 36, 5, 2, None)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.AIRCRAFT, 1, 12, 2, 1)[1], sm.OUT_OF_TABLE)
        self.assertEqual(sm.raw_cell(sm.INFANTRY, 36, True, 2, 1)[1], sm.OUT_OF_TABLE)

    def test_vehicle_columns_are_one_to_one(self) -> None:
        for count, cols in sm.VEHICLE_COLUMNS.items():
            self.assertEqual(sorted(c for c in cols if c is not None), list(range(1, 11)), count)
            self.assertEqual(len(cols), 20)
        self.assertTrue(all(len(r) == 20 for r in sm.VEHICLE_RESULT.values()))
        self.assertEqual(sorted(sm.VEHICLE_RESULT), list(range(2, 13)))

    def test_corrections(self) -> None:
        self.assertEqual([sm.personnel_correction(v) for v in (-3, 0, 1, 7, 8, 11)], [-1, -1, 0, 0, 1, 1])
        self.assertEqual(sm.vehicle_correction(-5, 4), -3)
        self.assertEqual(sm.vehicle_correction(-5, 0), 0)
        self.assertEqual(sm.vehicle_correction(-1, 3), -2)
        self.assertEqual(sm.vehicle_correction(4, 0), 1)
        self.assertEqual(sm.vehicle_correction(12, 0), 3)
        self.assertEqual(sm.vehicle_correction(20, 4), 2)
        self.assertIsNone(sm.vehicle_correction(5, 5))
        self.assertIsNone(sm.vehicle_correction(5, None))

    def test_correction_mapping(self) -> None:
        rows = [{"correction_table": "personnel_correction", "record": {"random2_rect": 8, "rect_damage": 1}},
                {"correction_table": "personnel_correction", "record": {"random2_rect": 3, "rect_damage": 1}},
                {"correction_table": "vehicle_correction", "target_armor": 7, "record": {"random2_rect": 3, "rect_damage": 0}}]
        out = sm.correction_mapping(rows)
        self.assertEqual(out["personnel_correction"], {"compared": 2, "matches": 1, "mismatches": 1, "undefined_armor": 0})
        self.assertEqual(out["vehicle_correction"]["undefined_armor"], 1)


def mrow(table, kind, value, observed, field="ori_damage"):
    return {"table": table, "kind": kind, "value": value, "observed": observed, "compared_field": field}


class K4MappingTest(unittest.TestCase):
    def test_numeric_matches_and_single_valued_kinds_support(self) -> None:
        rows = [mrow(sm.PERSONNEL_TABLE, sm.NUMERIC, 1, 1), mrow(sm.PERSONNEL_TABLE, sm.SUPPRESSION, None, 0),
                mrow(sm.PERSONNEL_TABLE, sm.SUPPRESSION, None, 0), mrow(sm.PERSONNEL_TABLE, sm.NO_EFFECT, None, 0)]
        out = sm.k4_mapping(rows)[sm.PERSONNEL_TABLE]
        self.assertEqual(out["status"], sm.MAPPING_SUPPORTED)
        self.assertEqual(out["non_numeric_values"], {sm.SUPPRESSION: {"value_0": 2}, sm.NO_EFFECT: {"value_0": 1}})

    def test_numeric_mismatch_contradicts(self) -> None:
        out = sm.k4_mapping([mrow(sm.VEHICLE_TABLE, sm.NUMERIC, 2, 1)])[sm.VEHICLE_TABLE]
        self.assertEqual((out["status"], out["numeric_mismatches"]), (sm.MAPPING_CONTRADICTED, 1))

    def test_two_values_for_one_kind_contradict(self) -> None:
        rows = [mrow(sm.AIR_TABLE, sm.NUMERIC, 1, 1), mrow(sm.AIR_TABLE, sm.ANNIHILATION, None, 1),
                mrow(sm.AIR_TABLE, sm.ANNIHILATION, None, 2)]
        self.assertEqual(sm.k4_mapping(rows)[sm.AIR_TABLE]["status"], sm.MAPPING_CONTRADICTED)

    def test_only_non_numeric_rows_are_untested_and_out_of_table_contradicts(self) -> None:
        self.assertEqual(sm.k4_mapping([mrow(sm.AIR_TABLE, sm.ANNIHILATION, None, 1)])[sm.AIR_TABLE]["status"],
                         sm.MAPPING_UNTESTED)
        rows = [mrow(sm.PERSONNEL_TABLE, sm.NUMERIC, 1, 1), mrow(sm.PERSONNEL_TABLE, sm.OUT_OF_TABLE, None, 0)]
        self.assertEqual(sm.k4_mapping(rows)[sm.PERSONNEL_TABLE]["status"], sm.MAPPING_CONTRADICTED)
        self.assertEqual(sm.k4_mapping([mrow(sm.NO_TABLE, sm.NO_TABLE, None, 0)])[sm.NO_TABLE]["status"],
                         sm.MAPPING_UNTESTED)

    def test_random_support_extraction(self) -> None:
        rows = [{"table": sm.PERSONNEL_TABLE, "record": {"random1": 7, "random2": 3, "random2_rect": 5}},
                {"table": sm.PERSONNEL_TABLE, "record": {"random1": 2, "random2": 6, "random2_rect": 4}},
                {"table": sm.AIR_TABLE, "record": {"random1": 12}}]
        out = sm.k4_support(rows)
        p = out[sm.PERSONNEL_TABLE]
        self.assertEqual(p["random1"], {"populated": 2, "support": {"random_value_2": 1, "random_value_7": 1}, "min": 2, "max": 7})
        self.assertEqual(p["joint_random1_random2"], {"random1_2_random2_6": 1, "random1_7_random2_3": 1})
        self.assertEqual(p["random2_rect_minus_random2"], {"modifier_2": 1, "modifier_minus_2": 1})
        self.assertEqual(out[sm.AIR_TABLE]["random2"]["populated"], 0)


class K4ProbabilityTest(unittest.TestCase):
    def test_unavailable_path_at_registration(self) -> None:
        self.assertEqual(sm.k4_probability_status(), sm.K4P_UNRESOLVED)
        self.assertTrue(all(e["status"] == sm.DOES_NOT_STATE_LAW for e in sm.K4_PROBABILITY_EVIDENCE))
        self.assertEqual({e["route"] for e in sm.K4_PROBABILITY_EVIDENCE}, {"A", "B"})

    def test_only_a_stated_law_supports(self) -> None:
        stated = ({"id": "x", "route": "A", "status": sm.STATES_LAW},)
        self.assertEqual(sm.k4_probability_status(stated), sm.K4P_SUPPORTED)
        self.assertEqual(sm.k4_probability_status(({"id": "x", "route": "B", "status": sm.STATES_LAW},)), sm.K4P_SUPPORTED)
        self.assertEqual(sm.k4_probability_status(({"id": "x", "route": "C", "status": sm.STATES_LAW},)), sm.K4P_UNRESOLVED)

    def test_no_statistical_fit_can_become_a_proof(self) -> None:
        """A perfectly two-dice-shaped sample changes nothing: the law's status takes no runtime input."""
        self.assertEqual(list(inspect.signature(sm.k4_probability_status).parameters), ["evidence"])
        rows = []
        for a in range(1, 7):
            for b in range(1, 7):
                rows.append({"table": sm.PERSONNEL_TABLE, "record": {"random1": a + b, "random2": a, "random2_rect": a}})
        support = sm.k4_support(rows)
        self.assertEqual(support[sm.PERSONNEL_TABLE]["random1"]["support"]["random_value_7"], 6)
        self.assertNotIn("law", json.dumps(support))
        self.assertEqual(sm.k4_probability_status(), sm.K4P_UNRESOLVED)


def k5row(o, r, d, b, kind=sm.NUMERIC, cls=sm.VEHICLE, keep=0, value=None):
    rec = {"damage": d}
    if o is not None:
        rec.update(ori_damage=o, rect_damage=r)
    return {"record": rec, "target_blood_before": b, "target_class": cls, "kind": kind, "value": value,
            "target_suppressed_before": keep}


class K5Test(unittest.TestCase):
    def fits(self, o, r, d, b, **kw):
        return set(sm.k5_row(k5row(o, r, d, b, **kw))["fits"])

    def test_each_relation_formula(self) -> None:
        f = sm.RELATIONS
        args = (2, -3, 4, 0)  # o, r, b, t
        self.assertEqual(f["additive_unclamped__without_resuppression_loss"](*args), -1)
        self.assertEqual(f["additive_lower_clamp__without_resuppression_loss"](*args), 0)
        self.assertEqual(f["additive_lower_and_strength_clamp__without_resuppression_loss"](3, 2, 4, 0), 4)
        self.assertEqual(f["correction_on_positive_raw_only__without_resuppression_loss"](0, 1, 4, 0), 0)
        self.assertEqual(f["correction_on_positive_raw_only__without_resuppression_loss"](1, 1, 4, 0), 2)
        self.assertEqual(f["correction_on_positive_raw_only_strength_clamp__without_resuppression_loss"](3, 2, 4, 0), 4)
        self.assertEqual(f["rect_damage_is_final__without_resuppression_loss"](3, 1, 4, 0), 1)
        self.assertEqual(f["additive_lower_clamp__with_resuppression_loss"](0, 0, 4, 1), 1)
        self.assertEqual(f["additive_lower_clamp__without_resuppression_loss"](0, 0, 4, 1), 0)
        self.assertEqual(len(f), 12)

    def test_zero_no_effect_and_suppression_with_a_positive_correction(self) -> None:
        # raw 0 with +1: additive readings give 1, positive-only readings give 0
        add = self.fits(0, 1, 1, 3, kind=sm.SUPPRESSION)
        pos = self.fits(0, 1, 0, 3, kind=sm.SUPPRESSION)
        self.assertIn("additive_lower_clamp__without_resuppression_loss", add)
        self.assertNotIn("correction_on_positive_raw_only__without_resuppression_loss", add)
        self.assertIn("correction_on_positive_raw_only__without_resuppression_loss", pos)
        self.assertNotIn("additive_lower_clamp__without_resuppression_loss", pos)

    def test_positive_negative_and_clamps(self) -> None:
        self.assertIn("additive_unclamped__without_resuppression_loss", self.fits(2, 1, 3, 4))      # positive correction
        self.assertIn("additive_unclamped__without_resuppression_loss", self.fits(2, -1, 1, 4))    # negative correction
        lower = self.fits(1, -3, 0, 4)                                                              # lower clamp
        self.assertNotIn("additive_unclamped__without_resuppression_loss", lower)
        self.assertIn("additive_lower_clamp__without_resuppression_loss", lower)
        upper = self.fits(3, 2, 4, 4)                                                               # upper clamp
        self.assertIn("additive_lower_and_strength_clamp__without_resuppression_loss", upper)
        self.assertNotIn("additive_lower_clamp__without_resuppression_loss", upper)
        self.assertIn("rect_damage_is_final__without_resuppression_loss", self.fits(3, 1, 1, 4))

    def test_resuppression_term(self) -> None:
        self.assertEqual(sm.resuppression_term(sm.INFANTRY, sm.SUPPRESSION, 1), 1)
        self.assertEqual(sm.resuppression_term(sm.INFANTRY, sm.SUPPRESSION, 0), 0)
        self.assertEqual(sm.resuppression_term(sm.VEHICLE, sm.SUPPRESSION, 1), 0)
        self.assertEqual(sm.resuppression_term(sm.INFANTRY, sm.NUMERIC, 1), 0)
        with_loss = self.fits(0, 0, 1, 2, kind=sm.SUPPRESSION, cls=sm.INFANTRY, keep=1)
        self.assertIn("additive_lower_clamp__with_resuppression_loss", with_loss)
        self.assertNotIn("additive_lower_clamp__without_resuppression_loss", with_loss)

    def test_identification_and_observational_equivalence(self) -> None:
        # only positive numeric rows without clamps: many relations agree -> underidentified
        same = [k5row(2, 0, 2, 4), k5row(1, 0, 1, 3)]
        self.assertEqual(sm.k5_class(same)["status"], sm.K5_UNDERIDENTIFIED)
        # rows separating all but one relation family member
        rows = [k5row(0, 1, 0, 3, kind=sm.NO_EFFECT), k5row(1, -3, 0, 4), k5row(3, 2, 4, 4), k5row(2, 1, 3, 4),
                k5row(0, 0, 0, 2, kind=sm.SUPPRESSION, cls=sm.INFANTRY, keep=1)]
        out = sm.k5_class(rows)
        self.assertEqual(out["families"]["full"]["survivors"],
                         ["correction_on_positive_raw_only_strength_clamp__without_resuppression_loss"])
        self.assertEqual(out["status"], sm.K5_IDENTIFIED)
        cov = out["families"]["full"]["boundary_coverage"]
        self.assertEqual((cov["lower_clamp_exercised"], cov["upper_clamp_exercised"], cov["positive_correction"],
                          cov["negative_correction"], cov["no_effect_raw"], cov["suppression_raw"]), (1, 1, 3, 1, 1, 1))
        bad = rows + [k5row(1, 0, 3, 4)]
        self.assertEqual(sm.k5_class(bad)["status"], sm.K5_NO_FIT)
        self.assertEqual(sm.k5_class([])["status"], sm.K5_UNTESTED)
        self.assertEqual(sm.k5_class([k5row(1, 0, 1, None)])["status"], sm.K5_UNTESTED)

    def test_short_records(self) -> None:
        whole = sm.k5_row(k5row(None, None, 2, 2, kind=sm.ANNIHILATION, cls=sm.AIRCRAFT))
        self.assertEqual(whole["family"], "short")
        self.assertIn("table_value_annihilation_whole_unit__without_resuppression_loss", whole["fits"])
        self.assertNotIn("table_value_annihilation_one__without_resuppression_loss", whole["fits"])
        one = sm.k5_class([k5row(None, None, 1, 1, kind=sm.ANNIHILATION, cls=sm.AIRCRAFT)])
        self.assertEqual(one["status"], sm.K5_UNDERIDENTIFIED)  # blood 1: whole unit and one coincide
        self.assertIsNone(sm.k5_row(k5row(None, None, 1, 1, kind=sm.OUT_OF_TABLE)))
        mixed = sm.k5_class([k5row(None, None, 2, 2, kind=sm.ANNIHILATION, cls=sm.AIRCRAFT),
                             k5row(None, None, 0, 2, kind=sm.NO_EFFECT, cls=sm.AIRCRAFT)])
        self.assertCountEqual(mixed["families"]["short"]["survivors"],
                              ["table_value_annihilation_whole_unit__with_resuppression_loss",
                               "table_value_annihilation_whole_unit__without_resuppression_loss"])

    def test_numeric_short_record(self) -> None:
        k = sm.k5_row(k5row(None, None, 2, 3, kind=sm.NUMERIC, value=2))
        self.assertEqual(len(k["fits"]), 4)


def k6(blood, damage, present, after=None, linked=False, cls=sm.VEHICLE):
    return {"class": cls, "blood_before": blood, "damage": damage, "present_after": present, "blood_after": after,
            "linked_removal": linked}


class K6Test(unittest.TestCase):
    def test_supported(self) -> None:
        out = sm.k6_class([k6(3, 1, True, 2), k6(1, 1, False), k6(2, 0, True, 2)])
        self.assertEqual(out["status"], sm.K6_SUPPORTED)
        self.assertEqual((out["c_lethal"], out["b_nonlethal_positive_damage"], out["zero_damage"]), (1, 1, 1))

    def test_nonlethal_decrement_mismatch_refutes(self) -> None:
        self.assertEqual(sm.k6_class([k6(3, 1, True, 1), k6(1, 1, False)])["status"], sm.K6_REFUTED)

    def test_lethal_retained_and_nonlethal_removed_refute(self) -> None:
        self.assertEqual(sm.k6_class([k6(3, 1, True, 2), k6(1, 2, True, 0)])["status"], sm.K6_REFUTED)
        self.assertEqual(sm.k6_class([k6(3, 1, False), k6(1, 1, False)])["status"], sm.K6_REFUTED)

    def test_unrelated_and_launcher_linked_removals_are_excluded(self) -> None:
        out = sm.k6_class([k6(3, 1, True, 2), k6(1, 1, False), k6(2, 0, False, linked=True)])
        self.assertEqual((out["status"], out["linked_removals_excluded"]), (sm.K6_SUPPORTED, 1))

    def test_untested_without_lethal_or_nonlethal_rows(self) -> None:
        self.assertEqual(sm.k6_class([k6(3, 1, True, 2)])["status"], sm.K6_UNTESTED)
        self.assertEqual(sm.k6_class([k6(1, 1, False)])["status"], sm.K6_UNTESTED)
        self.assertEqual(sm.k6_class([k6(2, 0, True, 2), k6(1, 1, False)])["status"], sm.K6_UNTESTED)
        self.assertEqual(sm.k6_class([])["status"], sm.K6_UNTESTED)

    def test_target_classes(self) -> None:
        self.assertEqual([sm.unit_class({"type": t}) for t in (1, 2, 3, 4, 5)],
                         [sm.INFANTRY, sm.VEHICLE, sm.AIRCRAFT, sm.FORTIFICATION, sm.OTHER])
        self.assertEqual(sm.unit_class({"type": True}), sm.OTHER)
        self.assertEqual(sm.unit_class(None), sm.OTHER)


class SufficiencyTest(unittest.TestCase):
    def ok(self):
        return sm.class_sufficiency(sm.K2_SUPPORTED, sm.K4P_SUPPORTED, sm.K5_IDENTIFIED, sm.K6_SUPPORTED)

    def test_all_classes_covered_resolve(self) -> None:
        suff = {c: self.ok() for c in (sm.INFANTRY, sm.VEHICLE)}
        self.assertEqual(sm.disposition(True, suff, [sm.INFANTRY, sm.VEHICLE])["disposition"], sm.DISPOSITIONS[2])

    def test_one_required_class_untested_underidentifies(self) -> None:
        suff = {sm.INFANTRY: self.ok(),
                sm.VEHICLE: sm.class_sufficiency(sm.K2_SUPPORTED, sm.K4P_SUPPORTED, sm.K5_IDENTIFIED, sm.K6_UNTESTED)}
        out = sm.disposition(True, suff, [sm.INFANTRY, sm.VEHICLE])
        self.assertEqual((out["disposition"], out["insufficient_required_classes"]), (sm.DISPOSITIONS[1], [sm.VEHICLE]))
        self.assertEqual(sm.disposition(True, {sm.INFANTRY: self.ok()}, [sm.INFANTRY, sm.AIRCRAFT])["disposition"],
                         sm.DISPOSITIONS[1])
        self.assertEqual(sm.disposition(True, {}, [])["disposition"], sm.DISPOSITIONS[1])

    def test_each_item_is_required(self) -> None:
        for args in ((sm.K2_UNRESOLVED, sm.K4P_SUPPORTED, sm.K5_IDENTIFIED, sm.K6_SUPPORTED),
                     (sm.K2_SUPPORTED, sm.K4P_UNRESOLVED, sm.K5_IDENTIFIED, sm.K6_SUPPORTED),
                     (sm.K2_SUPPORTED, sm.K4P_SUPPORTED, sm.K5_UNDERIDENTIFIED, sm.K6_SUPPORTED),
                     (sm.K2_SUPPORTED, sm.K4P_SUPPORTED, sm.K5_IDENTIFIED, sm.K6_REFUTED)):
            self.assertFalse(sm.class_sufficiency(*args)["sufficient"], args)

    def test_invalid_comes_first(self) -> None:
        suff = {sm.INFANTRY: self.ok()}
        self.assertEqual(sm.disposition(False, suff, [sm.INFANTRY])["disposition"], sm.DISPOSITIONS[0])
        # invalid integrity wins over insufficient classes too
        self.assertEqual(sm.disposition(False, {}, [sm.INFANTRY])["disposition"], sm.DISPOSITIONS[0])
        self.assertEqual(sm.DISPOSITIONS, ("SEMANTICS_AUDIT_INVALID", "DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED",
                                           "DIRECT_FIRE_SEMANTICS_RESOLVED"))

    def test_required_classes_from_sprint20(self) -> None:
        replay = json.loads((ROOT / "evaluation" / "s20-t11-replay" / "replay.json").read_text(encoding="utf-8"))
        self.assertEqual(sm.required_classes(replay["HH"]["pooled"]),
                         [sm.INFANTRY, sm.VEHICLE, sm.AIRCRAFT, sm.FORTIFICATION])
        pooled = {"root_switches": {"target_class_pairs": {"type 1 sub 2 -> type 4 sub 11": 3, "type 3 sub 6 -> type 2 sub 0": 0}}}
        self.assertEqual(sm.required_classes(pooled), [sm.INFANTRY, sm.FORTIFICATION])
        with self.assertRaises(ValueError):
            sm.class_of_label("type x")


class T11CompletionTest(unittest.TestCase):
    def test_denominator_is_preserved(self) -> None:
        with self.assertRaises(ValueError):
            sm.t11_completion([0.1] * 93, [0.2] * 93)
        with self.assertRaises(ValueError):
            sm.t11_completion([0.1] * 94, [0.2] * 95)

    def test_paired_comparison(self) -> None:
        out = sm.t11_completion([0.1] * 94, [0.1] * 93 + [0.2])
        self.assertEqual(out["status"], sm.T11_COMPLETIONS[1])
        self.assertAlmostEqual(out["delta_pkill"], 0.1 / 94)

    def test_exactly_zero_fails_and_negative_fails(self) -> None:
        self.assertEqual(sm.t11_completion([0.25] * 94, [0.25] * 94)["status"], sm.T11_COMPLETIONS[0])
        self.assertEqual(sm.t11_completion([0.3] * 94, [0.2] * 94)["status"], sm.T11_COMPLETIONS[0])


class PrivacyTest(unittest.TestCase):
    def test_labels_never_bare_numbers(self) -> None:
        self.assertEqual(sm.labelled("blood", 2), "blood_2")
        self.assertEqual(sm.labelled("difference", -3), "difference_minus_3")
        self.assertEqual(sm.label_counts([1, 1, -1], "damage"), {"damage_1": 2, "damage_minus_1": 1})

    def test_sanitizer_catches_bare_small_keys(self) -> None:
        ids = list(range(0, 50))
        self.assertTrue(sm.public_problems({"blood": {"2": 5}}, ids))
        self.assertEqual(sm.public_problems({"blood": {"blood_2": 5}}, ids), [])
        self.assertTrue(sm.public_problems({"obj_id": 1}, ids))
        self.assertTrue(sm.public_problems({"note": "unit 7 left"}, ids))


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables, self.row, self.cell, self.heading, self.in_heading, self.current = [], None, None, "", False, None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3"):
            self.in_heading, self.heading = True, ""
        if tag == "table":
            self.current = {"title": self.heading, "rows": []}
            self.tables.append(self.current)
        if tag == "tr" and self.current is not None:
            self.row = []
            self.current["rows"].append(self.row)
        if tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.row.append(self.cell)

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3"):
            self.in_heading = False
        if tag in ("td", "th"):
            self.cell = None
        if tag == "table":
            self.current = None

    def handle_data(self, data):
        if self.in_heading:
            self.heading += data.strip()
        if self.cell is not None:
            self.cell.append(data.strip())


def _value(text):
    if text == "":
        return None
    if text in ("压",):
        return sm.S
    if text in ("歼灭",):
        return sm.A
    return int(text)


def _bin(text):
    text = text.replace("，", ",")
    if text.startswith("<="):
        return None, int(text[2:])
    if text.startswith(">="):
        return int(text[2:]), None
    if "," in text:
        low, high = text.split(",")
        return int(low), int(high)
    if "-" in text[1:]:
        low, high = text.split("-")
        return int(low), int(high)
    return int(text), int(text)


@unittest.skipUnless(SNAPSHOT.exists(), "the documentation snapshot is local to the workstation")
class SnapshotTest(unittest.TestCase):
    """The transcribed tables and the quotations against the documentation snapshot itself."""

    @classmethod
    def setUpClass(cls) -> None:
        parser = _Tables()
        parser.feed((SNAPSHOT / "rules_tables.html").read_text(encoding="utf-8"))
        cls.tables = {t["title"]: [["".join(c) for c in r] for r in t["rows"]] for t in parser.tables}

    def test_snapshot_digests(self) -> None:
        for name, digest in sm.SNAPSHOT_FILES_SHA256.items():
            self.assertEqual(hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest(), digest, name)

    def test_personnel_table(self) -> None:
        rows = self.tables["直瞄武器对人员/步兵轻武器对车辆战斗结果表"][2:]
        self.assertEqual(len(rows), 11)
        self.assertEqual({int(r[0]): tuple(_value(c) for c in r[1:]) for r in rows}, sm.PERSONNEL_RESULT)

    def test_vehicle_table(self) -> None:
        rows = self.tables["对车辆单位战斗结果"]
        self.assertEqual({int(r[0]): tuple(_value(c) for c in r[1:]) for r in rows[1:6]}, sm.VEHICLE_COLUMNS)
        self.assertEqual({int(r[0]): tuple(_value(c) for c in r[1:]) for r in rows[7:18]}, sm.VEHICLE_RESULT)

    def test_air_table(self) -> None:
        rows = self.tables["空战斗结果表"][2:]
        self.assertEqual({int(r[0]): tuple(_value(c) for c in r[1:]) for r in rows}, sm.AIR_RESULT)

    def test_vehicle_correction_table(self) -> None:
        rows = self.tables["车辆战损结果修正"][2:]
        got = []
        for r in rows:
            label, *values = r[-6:]
            by_armor = tuple(0 if v == "" else int(v) for v in reversed(values))  # composite..none -> armor 0..4
            got.append((*_bin(label), by_armor))
        self.assertEqual(tuple(got), sm.VEHICLE_CORRECTION_BINS)

    def test_quotations(self) -> None:
        for item in sm.K4_PROBABILITY_EVIDENCE:
            for name, text in item["quotes"]:
                source = (ROOT / name) if name.startswith("docs/") else (SNAPSHOT / name)
                body = " ".join(source.read_text(encoding="utf-8").split())
                self.assertIn(" ".join(text.split()), body, (item["id"], name))


class RepositoryQuotationTest(unittest.TestCase):
    def test_repository_quotations(self) -> None:
        quotes = [(i["id"], n, t) for i in sm.K4_PROBABILITY_EVIDENCE for n, t in i["quotes"] if n.startswith("docs/")]
        self.assertTrue(quotes)
        for item, name, text in quotes:
            body = " ".join((ROOT / name).read_text(encoding="utf-8").split())
            self.assertIn(" ".join(text.split()), body, item)


if __name__ == "__main__":
    unittest.main()
