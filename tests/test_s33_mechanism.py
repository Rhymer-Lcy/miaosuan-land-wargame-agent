"""Sprint 33's registered mechanism classification (``evaluation/s33_mechanism.py``) on SYNTHETIC frames.

Pinned: Sprint 32's rules are called unchanged and preserved beside Sprint 33's; the one correction (a transient
``flag_force_stop`` while the unit completes its hex is not adverse; the flag with a path at or after the clearing
deadline is ``deferred_indefinite``) at its boundary; every supplementary endpoint; the endpoints a game demonstrates;
the evidence level attached to the two positive dispositions; and that a listed shot alone never reads as an accepted
shot.
"""

from __future__ import annotations

import unittest

from miaosuan_agent.evaluation import s32_mechanism as m32
from miaosuan_agent.evaluation import s33_mechanism as mm

UNIT, OTHER, FOE = 7, 8, 90
SEAT = 11
A, B, C, D = 1010, 1011, 1012, 1013  # the unit's hex, the next hex, the rest of the route
S0, H0 = 100, 5
CONTROL = {"occupy": 310, "margin_min": 559}
WEAPONS = (69,)


def snap(hex_=A, path=(B, C, D), speed=0.05, stop=0, timer=0, force=0, listed=(10,), see=(FOE,), keep=0):
    return m32.Snap(hex=hex_, path=tuple(path), speed=speed, stop=stop, timer=timer, force=force, listed=tuple(listed),
                    see=tuple(see), keep=keep)


def documented(flag=True, transition=75, listed_after=(1, 2), shoot=True, judge=True, resume=True, foe_hex=1020,
               extra=None, total=None):
    """Frames of the documented sequence: the stop at S0, the next hex entered and the path cleared at S0 + H0, the
    transition of ``transition`` steps, then the listing ``listed_after``; a shot at completion and a later MOVE."""
    frames = []
    clear = S0 + H0
    done = clear + transition
    last = total or done + 40
    for step in range(S0, last + 1):
        emitted, feedback, judged = [], [], []
        if step == S0:
            s = snap()
            emitted.append({"actor": SEAT, "obj_id": UNIT, "type": 10})
            feedback.append({"message": {"obj_id": UNIT, "type": 10}})
        elif step < clear:
            s = snap(force=1 if flag else 0, listed=(10,))
        elif step < done:
            s = snap(hex_=B, path=(), speed=0, timer=done - step, listed=())
        else:
            s = snap(hex_=B, path=(), speed=0, stop=1, timer=0, listed=listed_after)
            if step == done and shoot:
                emitted.append({"actor": SEAT, "obj_id": UNIT, "type": 2, "target_obj_id": FOE, "weapon_id": 69})
                feedback.append({"message": {"obj_id": UNIT, "type": 2}})
                if judge:
                    judged.append({"att_obj_id": UNIT, "damage": 1})
            if step == done + 10 and resume:
                emitted.append({"actor": SEAT, "obj_id": UNIT, "type": 1, "move_path": [C]})
            if step > done + 10 and resume:
                s = snap(hex_=B, path=(C,), speed=0.05, stop=0, listed=(10,))
        units = {UNIT: s}
        if extra:
            units.update(extra(step))
        frames.append({"step": step, "units": units, "enemies": {FOE: (foe_hex, 2)}, "feedback": feedback,
                       "judge": judged, "emitted": emitted})
    return frames


ORDER = m32.Order(k=0, step=S0, unit=UNIT, h0=H0, start_hex=A, next_hex=B, weapons=WEAPONS)


def verdict(frames, structural=(), occupy=310, margin=559):
    result = mm.classify(ORDER, frames)
    runs = m32.deadlock_runs([ORDER], [result], frames)
    return result, mm.game_verdict(structural, [result], runs, occupy, margin, CONTROL)


class CorrectionTest(unittest.TestCase):
    def test_transient_flag_is_adverse_under_sprint32_and_not_under_sprint33(self) -> None:
        result, v = verdict(documented(flag=True))
        self.assertEqual(result["s32_adverse"], ["deferred"])
        self.assertEqual(result["adverse"], [])
        self.assertEqual((v["verdict"], v["s32_verdict"]), ("OBSERVED", "ADVERSE"))
        self.assertEqual(result["endpoints"]["flag_frames"], H0 - 1)
        self.assertEqual((result["endpoints"]["flag_first_offset"], result["endpoints"]["flag_last_offset"]),
                         (1, H0 - 1))
        self.assertFalse(result["endpoints"]["deferred_indefinite"])

    def test_without_the_flag_both_agree(self) -> None:
        result, v = verdict(documented(flag=False))
        self.assertEqual((result["adverse"], result["s32_adverse"]), ([], []))
        self.assertEqual((v["verdict"], v["s32_verdict"]), ("OBSERVED", "OBSERVED"))

    def test_deferred_indefinite_boundary(self) -> None:
        deadline = S0 + H0 + mm.TOLERANCE
        for last_flag, expected in ((deadline - 1, False), (deadline, True)):
            frames = []
            for step in range(S0, deadline + 3):
                force = 1 if S0 < step <= last_flag else 0
                path = (B, C, D) if step < deadline + 2 else ()
                s = snap(force=force, path=path) if path else snap(hex_=B, path=(), speed=0, timer=70)
                frames.append({"step": step, "units": {UNIT: s}, "enemies": {}, "feedback": [], "judge": [],
                               "emitted": []})
            self.assertEqual(mm.deferred_indefinite(ORDER, frames), expected, last_flag)
            self.assertEqual("deferred_indefinite" in mm.classify(ORDER, frames)["adverse"], expected)

    def test_flag_with_an_empty_path_is_not_indefinite(self) -> None:
        frames = documented(flag=False)
        clear = S0 + H0
        for f in frames:
            if f["step"] >= clear + 3 and f["step"] < clear + 20:
                s = f["units"][UNIT]
                f["units"][UNIT] = m32.Snap(s.hex, s.path, s.speed, s.stop, s.timer, 1, s.listed, s.see, s.keep)
        result = mm.classify(ORDER, frames)
        self.assertFalse(result["endpoints"]["deferred_indefinite"])
        self.assertTrue(result["endpoints"]["flag_after_clear"])
        self.assertNotIn("deferred_indefinite", result["adverse"])
        self.assertIn("deferred", result["s32_adverse"])

    def test_b4_signature_is_adverse_in_both(self) -> None:
        frames = [{"step": s, "units": {UNIT: snap(force=1 if s > S0 else 0, speed=0 if s > S0 else 0.05,
                                                   listed=() if s > S0 else (10,))},
                   "enemies": {}, "feedback": [], "judge": [], "emitted": []} for s in range(S0, S0 + 40)]
        result = mm.classify(ORDER, frames)
        self.assertEqual(result["adverse"], ["deferred_indefinite", "path_not_cleared"])
        self.assertEqual(result["s32_adverse"], ["deferred", "path_not_cleared"])

    def test_other_adverse_outcomes_are_sprint32s(self) -> None:
        late = documented(flag=False, transition=78)
        self.assertEqual(mm.classify(ORDER, late)["adverse"], ["transition_timing"])
        stuck = documented(flag=False, listed_after=(), shoot=False, resume=False)
        self.assertEqual(mm.classify(ORDER, stuck)["adverse"], ["unable_to_resume"])
        refused = documented(flag=False)
        refused[0]["feedback"] = [{"message": {"obj_id": UNIT, "type": 10}, "error": {"code": 5}}]
        result = mm.classify(ORDER, refused)
        self.assertEqual(result["adverse"], ["rejected"])
        self.assertTrue(result["endpoints"]["stop_refused"])
        self.assertEqual(mm.ADVERSE, ("rejected", "deferred_indefinite") + m32.ADVERSE[2:])


class EndpointTest(unittest.TestCase):
    def test_documented_sequence_endpoints(self) -> None:
        result, v = verdict(documented())
        e = result["endpoints"]
        self.assertTrue(e["stop_listed"] and e["stop_emitted_exact"] and e["stop_echoed_clean"])
        self.assertEqual((e["expected_entry_step"], e["entry_step"]), (S0 + H0, S0 + H0))
        self.assertEqual((result["cleared_step"], result["where"], e["transition_started"]), (S0 + H0, "next_hex", True))
        self.assertEqual((result["completed_step"], e["completion_offset"]), (S0 + H0 + 75, 75))
        self.assertTrue(e["shot_emitted"] and result["shot_accepted"] and result["fire_listed"])
        self.assertEqual((e["judge_records_in_window"], e["damage_in_window"]), (1, 1))
        self.assertEqual((e["resume_order_step"], e["resume_order_refused"], e["resumed"]),
                         (S0 + H0 + 85, False, True))
        self.assertEqual((e["baseline_actions_before_effect"], e["blocked_frames"]), (0, 0))
        self.assertEqual(v["demonstrated"], list(mm.ENDPOINTS))

    def test_inexact_stop_form_and_no_listing(self) -> None:
        frames = documented()
        frames[0]["emitted"] = [{"actor": SEAT, "obj_id": UNIT, "type": 10, "extra": 1}]
        frames[0]["units"][UNIT] = snap(listed=(1,))
        e = mm.classify(ORDER, frames)["endpoints"]
        self.assertFalse(e["stop_emitted_exact"])
        self.assertFalse(e["stop_listed"])

    def test_listed_shot_is_not_an_accepted_shot(self) -> None:
        for kw in (dict(shoot=False), dict(judge=False)):
            result, v = verdict(documented(**kw))
            self.assertTrue(result["fire_listed"])
            self.assertFalse(bool(result["shot_accepted"]), kw)
            self.assertEqual(v["verdict"], "OBSERVED")
            self.assertNotIn("SHOT_ACCEPTED", v["demonstrated"])
            self.assertIn("SHOOTING_LISTED", v["demonstrated"])
        result, _ = verdict(documented(shoot=False))
        self.assertFalse(result["endpoints"]["shot_emitted"])

    def test_refused_shot(self) -> None:
        frames = documented()
        done = S0 + H0 + 75
        f = next(x for x in frames if x["step"] == done)
        f["feedback"] = [{"message": {"obj_id": UNIT, "type": 2}, "error": {"code": 3}}]
        f["judge"] = []
        result = mm.classify(ORDER, frames)
        self.assertTrue(result["endpoints"]["shot_refused"])
        self.assertFalse(result["shot_accepted"])

    def test_no_target_at_completion_is_stop_semantics_only(self) -> None:
        result, v = verdict(documented(foe_hex=1090, listed_after=(1,), shoot=False))
        self.assertFalse(result["fire_evaluable"])
        self.assertEqual(v["verdict"], "STOP_ONLY")
        self.assertEqual(v["demonstrated"], ["STOP_EXECUTION", "MOVEMENT_RESUMED"])

    def test_target_in_range_without_listing_is_not_engaging(self) -> None:
        result, v = verdict(documented(listed_after=(1,), shoot=False))
        self.assertTrue(result["fire_evaluable"])
        self.assertEqual(v["verdict"], "NOT_ENGAGING")

    def test_resumption_variants(self) -> None:
        result, _ = verdict(documented(resume=False))
        self.assertIsNone(result["endpoints"]["resumed"])
        frames = documented(resume=False)
        done = S0 + H0 + 75
        f = next(x for x in frames if x["step"] == done + 5)
        f["emitted"].append({"actor": SEAT, "obj_id": UNIT, "type": 1, "move_path": [C]})
        e = mm.classify(ORDER, frames)["endpoints"]
        self.assertEqual((e["resume_order_step"], e["resumed"]), (done + 5, False))

    def test_baseline_action_before_effect_and_blocked_frames(self) -> None:
        frames = documented(extra=lambda step: {OTHER: snap(hex_=A, path=(B, C), speed=0, listed=())}
                            if step >= S0 + H0 else {})
        frames[2]["emitted"].append({"actor": SEAT, "obj_id": UNIT, "type": 1, "move_path": [D]})
        e = mm.classify(ORDER, frames)["endpoints"]
        self.assertEqual(e["baseline_actions_before_effect"], 1)
        self.assertGreater(e["blocked_frames"], 0)

    def test_suppressed_at_completion_is_censored_and_never_positive(self) -> None:
        frames = documented()
        done = S0 + H0 + 75
        f = next(x for x in frames if x["step"] == done)
        s = f["units"][UNIT]
        f["units"][UNIT] = m32.Snap(s.hex, s.path, s.speed, s.stop, s.timer, s.force, s.listed, s.see, 1)
        result, v = verdict(frames)
        self.assertEqual((result["censored"], result["completed_step"]), ("suppressed at completion", done))
        self.assertEqual(v["verdict"], "UNTESTED")
        self.assertEqual(v["demonstrated"], [])

    def test_moving_unit_through_the_stop_hex_is_not_blocked(self) -> None:
        frames = documented(extra=lambda step: {OTHER: snap(hex_=A, path=(B, C), speed=0.05, listed=(10,))}
                            if step >= S0 + H0 else {})
        self.assertEqual(mm.classify(ORDER, frames)["endpoints"]["blocked_frames"], 0)

    def test_censored_stop_is_never_positive(self) -> None:
        frames = documented()
        done = S0 + H0 + 75
        for f in frames:
            if f["step"] >= done - 10:
                f["units"].pop(UNIT)
        result, v = verdict(frames)
        self.assertEqual(result["censored"], "lost during the transition")
        self.assertEqual(v["verdict"], "UNTESTED")
        self.assertEqual(v["demonstrated"], [])


class DispositionTest(unittest.TestCase):
    def game(self, frames, **kw):
        return verdict(frames, **kw)[1]

    def test_evidence_levels(self) -> None:
        full = self.game(documented())
        listed = self.game(documented(judge=False))
        stop_resume = self.game(documented(foe_hex=1090, listed_after=(1,), shoot=False))
        stop_only = self.game(documented(foe_hex=1090, listed_after=(1,), shoot=False, resume=False))
        cases = (([full, stop_only], "T7B1_MECH_SUPPORTED", "STOP_AND_SHOT_ACCEPTED"),
                 ([listed, stop_only], "T7B1_MECH_SUPPORTED", "STOP_AND_SHOOTING_LISTED"),
                 ([stop_resume, stop_only], "T7B1_MECH_STOP_ONLY", "STOP_AND_MOVEMENT_RESUMPTION"),
                 ([stop_only, stop_only], "T7B1_MECH_STOP_ONLY", "STOP_EXECUTION"))
        for games, disposition, level in cases:
            out = mm.disposition(games)
            self.assertEqual((out["disposition"], out["evidence_level"]), (disposition, level))

    def test_preserved_sprint32_disposition(self) -> None:
        flagged = self.game(documented(flag=True))
        out = mm.disposition([flagged, flagged])
        # Sprint 32's rules would have closed the gate after the first game, so its second game is behind a closed gate
        self.assertEqual((out["disposition"], out["s32_disposition"]), ("T7B1_MECH_SUPPORTED", "T7B1_MECH_INVALID"))
        out = mm.disposition([flagged], planned=1)
        self.assertEqual((out["disposition"], out["s32_disposition"]), ("T7B1_MECH_SUPPORTED", "T7B1_MECH_REJECT"))

    def test_negative_dispositions_carry_no_level(self) -> None:
        harm = self.game(documented(), margin=508)
        self.assertEqual(harm["verdict"], "HARM")
        self.assertEqual(self.game(documented(), margin=509)["verdict"], "OBSERVED")
        self.assertEqual(self.game(documented(), occupy=309)["verdict"], "HARM")
        not_engaging = self.game(documented(listed_after=(1,), shoot=False))
        untested = self.game(documented()[:3])
        for games, expected in (([harm], "T7B1_MECH_REJECT"), ([not_engaging], "T7B1_MECH_NOT_ENGAGING"),
                                ([untested, untested], "T7B1_MECH_UNTESTED"), ([untested], "T7B1_MECH_INVALID"),
                                ([harm, untested], "T7B1_MECH_INVALID"), ([], "T7B1_MECH_INVALID")):
            out = mm.disposition(games)
            self.assertEqual(out["disposition"], expected, expected)
            self.assertIsNone(out["evidence_level"])

    def test_structural_game_is_invalid(self) -> None:
        bad = self.game(documented(), structural=("S7",))
        self.assertEqual(bad["verdict"], "STRUCTURAL")
        self.assertEqual(mm.disposition([bad])["disposition"], "T7B1_MECH_INVALID")

    def test_rules_identity(self) -> None:
        self.assertEqual(mm.RULES_ID, "s33-t7-b1-mechanism-1")
        self.assertEqual((mm.TOLERANCE, mm.FEEDBACK_STEPS), (m32.TOLERANCE, m32.FEEDBACK_STEPS))
        self.assertEqual((m32.TOLERANCE, m32.FEEDBACK_STEPS, m32.DEADLOCK_RUN, m32.HARM_MARGIN), (2, 2, 300, 50))
        self.assertEqual(mm.GAME_VERDICTS, ("STRUCTURAL", "ADVERSE", "HARM", "NOT_ENGAGING", "UNTESTED", "STOP_ONLY",
                                            "OBSERVED"))


if __name__ == "__main__":
    unittest.main()
