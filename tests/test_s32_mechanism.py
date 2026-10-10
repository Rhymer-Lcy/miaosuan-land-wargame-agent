"""Sprint 32 proposed mechanism-check rules (``evaluation/s32_mechanism.py``) on synthetic frames: every event of a
stop order, its windows and boundaries, censoring, deadlock runs, the game verdicts and the disposition order.

Synthetic frames only: they test the rules that would read a future capture, not any engine behaviour."""

from __future__ import annotations

import unittest

from miaosuan_agent.evaluation import s32_mechanism as m

UNIT, S0, H0, START, NEXT = 1, 100, 10, 1010, 1011
ORDER = m.Order(k=0, step=S0, unit=UNIT, h0=H0, start_hex=START, next_hex=NEXT, weapons=(54, 43))
CONTROL = {"occupy": 310, "margin_min": 559}


def snap(hex_=START, path=(NEXT, 1012), speed=0.05, stop=0, timer=0, force=0, listed=(10,), see=(900,), keep=0):
    return m.Snap(hex_, tuple(path), speed, stop, timer, force, tuple(listed), tuple(see), keep)


def story(clear_at=S0 + H0, where=NEXT, complete_after=75, end=S0 + 400, relisted=(1, 2), feedback_error=False,
          force_from=None, timer_at_clear=75, lose_at=None, keep_at_completion=0, enemy_hex=1016, shot=False):
    """Frames of the stopped unit, one per step from the order's decision on."""
    frames = []
    for step in range(S0, end + 1):
        if lose_at is not None and step >= lose_at:
            units = {}
        elif clear_at is None or step < clear_at:
            units = {UNIT: snap(force=1 if force_from is not None and step >= force_from else 0,
                                listed=() if force_from is not None and step >= force_from else (10,))}
        elif complete_after is None or step < clear_at + complete_after:
            left = clear_at + 75 - step
            units = {UNIT: snap(where, (), 0, 0, timer_at_clear and max(left, 1), listed=())}
        else:
            units = {UNIT: snap(where, (), 0, 1, 0, listed=relisted,
                                keep=keep_at_completion if step == clear_at + complete_after else 0)}
        frame = {"step": step, "units": units, "enemies": {900: (enemy_hex, 2)}, "feedback": [], "judge": [],
                 "emitted": []}
        if step == S0 + 1:
            frame["feedback"] = [{"message": {"obj_id": UNIT, "type": 10},
                                  "error": {"code": 7} if feedback_error else None}]
        if shot and clear_at is not None and complete_after is not None and step == clear_at + complete_after:
            frame["emitted"] = [{"obj_id": UNIT, "type": 2}]
            frame["judge"] = [{"att_obj_id": UNIT}]
        frames.append(frame)
    return frames


class ClassifyTest(unittest.TestCase):
    def test_documented_sequence(self) -> None:
        r = m.classify(ORDER, story(shot=True))
        self.assertEqual(r["adverse"], [])
        self.assertEqual((r["where"], r["cleared_step"], r["completed_step"]), ("next_hex", 110, 185))
        self.assertEqual((r["fire_evaluable"], r["fire_listed"], r["shot_accepted"], r["move_relisted"]),
                         (True, True, True, True))
        self.assertIsNone(r["censored"])

    def test_clearing_window_boundaries(self) -> None:
        self.assertEqual(m.classify(ORDER, story(clear_at=S0 + H0 + 2))["adverse"], [])
        self.assertEqual(m.classify(ORDER, story(clear_at=S0 + H0 + 3))["adverse"], ["path_not_cleared"])
        self.assertEqual(m.classify(ORDER, story(clear_at=None))["adverse"], ["path_not_cleared"])

    def test_in_place_is_reported_not_adverse(self) -> None:
        r = m.classify(ORDER, story(clear_at=S0 + 1, where=START))
        self.assertEqual((r["where"], r["adverse"]), ("in_place", []))

    def test_overrun(self) -> None:
        self.assertIn("overrun", m.classify(ORDER, story(where=1012))["adverse"])

    def test_rejected(self) -> None:
        self.assertEqual(m.classify(ORDER, story(feedback_error=True))["adverse"], ["rejected"])

    def test_deferred(self) -> None:
        r = m.classify(ORDER, story(clear_at=None, force_from=S0 + 1))
        self.assertEqual(r["adverse"], ["deferred", "path_not_cleared"])

    def test_no_transition(self) -> None:
        self.assertIn("no_transition", m.classify(ORDER, story(timer_at_clear=0))["adverse"])

    def test_transition_timing_boundaries(self) -> None:
        self.assertEqual(m.classify(ORDER, story(complete_after=73))["adverse"], [])
        self.assertEqual(m.classify(ORDER, story(complete_after=77))["adverse"], [])
        self.assertEqual(m.classify(ORDER, story(complete_after=72))["adverse"], ["transition_timing"])
        self.assertEqual(m.classify(ORDER, story(complete_after=78))["adverse"], ["transition_timing"])
        self.assertEqual(m.classify(ORDER, story(complete_after=None))["adverse"], ["transition_timing"])

    def test_unable_to_resume(self) -> None:
        self.assertEqual(m.classify(ORDER, story(relisted=()))["adverse"], ["unable_to_resume"])
        self.assertEqual(m.classify(ORDER, story(relisted=(2,)))["adverse"], ["unable_to_resume"])
        r = m.classify(ORDER, story(relisted=(1,)))
        self.assertEqual((r["adverse"], r["fire_evaluable"], r["fire_listed"]), ([], True, False))

    def test_fire_opportunity_needs_a_target_in_range(self) -> None:
        r = m.classify(ORDER, story(enemy_hex=1030))
        self.assertEqual((r["fire_evaluable"], r["adverse"]), (False, []))

    def test_censoring(self) -> None:
        self.assertEqual(m.classify(ORDER, story(lose_at=S0 + 5))["censored"], "lost before the path cleared")
        self.assertEqual(m.classify(ORDER, story(lose_at=S0 + 50))["censored"], "lost during the transition")
        r = m.classify(ORDER, story(end=S0 + 60))
        self.assertEqual((r["censored"], r["adverse"]), ("game over during the transition", []))
        r = m.classify(ORDER, story(end=S0 + 5))
        self.assertEqual((r["censored"], r["adverse"]), ("game over before the path cleared", []))
        r = m.classify(ORDER, story(keep_at_completion=1))
        self.assertEqual((r["censored"], r["adverse"]), ("suppressed at completion", []))

    def test_shot_not_accepted(self) -> None:
        frames = story(shot=True)
        for f in frames:
            if f["judge"]:
                f["judge"] = []
        self.assertFalse(m.classify(ORDER, frames)["shot_accepted"])
        frames = story(shot=True)
        for f in frames:
            if f["emitted"]:
                f["feedback"] = [{"message": {"obj_id": UNIT, "type": 2}, "error": {"code": 203}}]
        self.assertFalse(m.classify(ORDER, frames)["shot_accepted"])


class DeadlockTest(unittest.TestCase):
    def frames(self, run, crowd=4):
        out = []
        for i in range(400):
            units = {UNIT: snap(NEXT, (), 0, 1, 0, listed=(1,))}
            for j in range(2, crowd + 1):
                units[j] = snap(NEXT, (), 0, 1, 0, listed=(1,))
            waiting = i < run
            units[9] = snap(1012, (NEXT, 1013), 0 if waiting else 0.05)
            out.append({"step": S0 + 10 + i, "units": units})
        return out

    def test_runs(self) -> None:
        result = {"cleared_step": S0 + 10}
        self.assertEqual(m.deadlock_runs([ORDER], [result], self.frames(300)), [300])
        self.assertEqual(m.deadlock_runs([ORDER], [result], self.frames(299)), [299])
        self.assertEqual(m.deadlock_runs([ORDER], [result], self.frames(300, crowd=3)), [0])
        self.assertEqual(m.deadlock_runs([ORDER], [{"cleared_step": None}], self.frames(300)), [])


def result(**kw):
    base = {"adverse": [], "censored": None, "completed_step": 185, "fire_evaluable": True, "fire_listed": True,
            "shot_accepted": True, "where": "next_hex"}
    base.update(kw)
    return base


class VerdictTest(unittest.TestCase):
    def verdict(self, results, runs=(0,), occupy=310, margin=600, structural=()):
        return m.game_verdict(list(structural), results, list(runs), occupy, margin, CONTROL)["verdict"]

    def test_first_match(self) -> None:
        self.assertEqual(self.verdict([result()], structural=["capture missing"]), "STRUCTURAL")
        self.assertEqual(self.verdict([result(adverse=["deferred"])]), "ADVERSE")
        self.assertEqual(self.verdict([result()], runs=(300,)), "ADVERSE")
        self.assertEqual(self.verdict([result()], runs=(299,)), "OBSERVED")
        self.assertEqual(self.verdict([result()], occupy=300), "HARM")
        self.assertEqual(self.verdict([result()], margin=508), "HARM")
        self.assertEqual(self.verdict([result()], margin=509), "OBSERVED")
        self.assertEqual(self.verdict([result(fire_listed=False)]), "NOT_ENGAGING")
        self.assertEqual(self.verdict([result(fire_listed=False), result()]), "OBSERVED")
        self.assertEqual(self.verdict([]), "UNTESTED")
        self.assertEqual(self.verdict([result(completed_step=None, censored="lost")]), "UNTESTED")
        self.assertEqual(self.verdict([result(censored="suppressed at completion")]), "UNTESTED")
        self.assertEqual(self.verdict([result(fire_evaluable=False)]), "STOP_ONLY")

    def test_gate(self) -> None:
        cases = ((dict(structural=["x"]), "STRUCTURAL", False), (dict(results=[result(adverse=["deferred"])]),
                 "ADVERSE", False), (dict(occupy=300), "HARM", False),
                 (dict(results=[result(fire_listed=False)]), "NOT_ENGAGING", False), (dict(results=[]), "UNTESTED", True),
                 (dict(results=[result(fire_evaluable=False)]), "STOP_ONLY", True), (dict(), "OBSERVED", True))
        for kw, verdict, open_ in cases:
            args = dict(structural=[], results=[result()], occupy=310, margin=600)
            args.update(kw)
            out = m.game_verdict(args["structural"], args["results"], [0], args["occupy"], args["margin"], CONTROL)
            self.assertEqual((out["verdict"], out["gate_open"]), (verdict, open_))


def game(verdict):
    return {"verdict": verdict, "gate_open": verdict in m.GAME_VERDICTS[4:]}


class DispositionTest(unittest.TestCase):
    def test_order(self) -> None:
        d = lambda *v: m.disposition([game(x) for x in v])["disposition"]  # noqa: E731
        self.assertEqual(d(), "T7B1_MECH_INVALID")
        self.assertEqual(d("STRUCTURAL"), "T7B1_MECH_INVALID")
        self.assertEqual(d("OBSERVED", "STRUCTURAL"), "T7B1_MECH_INVALID")
        self.assertEqual(d("ADVERSE", "OBSERVED"), "T7B1_MECH_INVALID")      # second game behind a closed gate
        self.assertEqual(d("OBSERVED", "OBSERVED", "OBSERVED"), "T7B1_MECH_INVALID")
        self.assertEqual(d("OBSERVED"), "T7B1_MECH_INVALID")                  # stopped with the gate open
        self.assertEqual(d("ADVERSE"), "T7B1_MECH_REJECT")
        self.assertEqual(d("HARM"), "T7B1_MECH_REJECT")
        self.assertEqual(d("OBSERVED", "ADVERSE"), "T7B1_MECH_REJECT")
        self.assertEqual(d("NOT_ENGAGING"), "T7B1_MECH_NOT_ENGAGING")
        self.assertEqual(d("OBSERVED", "NOT_ENGAGING"), "T7B1_MECH_NOT_ENGAGING")
        self.assertEqual(d("UNTESTED", "UNTESTED"), "T7B1_MECH_UNTESTED")
        self.assertEqual(d("STOP_ONLY", "UNTESTED"), "T7B1_MECH_STOP_ONLY")
        self.assertEqual(d("UNTESTED", "OBSERVED"), "T7B1_MECH_SUPPORTED")
        self.assertEqual(d("OBSERVED", "STOP_ONLY"), "T7B1_MECH_SUPPORTED")


if __name__ == "__main__":
    unittest.main()
