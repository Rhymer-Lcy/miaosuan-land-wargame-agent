"""Sprint 36 study derivation: every way a registered schedule can end, and planted reporting errors (SYNTHETIC)."""

from __future__ import annotations

import json
import unittest

from miaosuan_agent.evaluation import s36_publish as pub
from miaosuan_agent.evaluation import s36_study as st


def game_stop(facts, history):
    kind = facts.get("stop")
    return (kind, [f"planted {kind}"]) if kind else None


def batch_gate(batch, history):
    gate = history[-1].get("gate")
    return (gate, [f"planted {gate} after {batch}"]) if gate else None


def final(history):
    total = sum(f.get("score", 0) for f in history)
    return {"disposition": "PROMISING" if total > 0 else "INCONCLUSIVE", "why": f"total {total}"}


RULES = st.Rules(
    rules_id="synthetic-rules-1", batches=(("A", (1, 2, 3)), ("B", (4, 5)), ("C", (6,))),
    game_stop=game_stop, batch_gate=batch_gate, final=final,
    stop_dispositions={"protocol": "INVALID", "structural": "INVALID", "agent": "AGENT_FAILURE", "harm": "REJECT",
                       "futility": "UNFAVOURABLE", "complete": "COMPLETE"},
    not_started="NOT_AUTHORIZED", in_progress="IN_PROGRESS")


def games(n, **special):
    out = {p: {"score": 1} for p in range(1, n + 1)}
    for p, facts in special.items():
        out[int(p[1:])] = dict(out.get(int(p[1:]), {}), **facts)
    return out


def name(d):
    return d["disposition"]["disposition"]


class TerminationTests(unittest.TestCase):
    def check(self, played, authorized=True):
        derived = st.report(RULES, played, authorized)        # refused if the independent restatement disagrees
        return derived

    def test_before_the_first_game(self):
        d = self.check({}, authorized=False)
        self.assertEqual(name(d), "NOT_AUTHORIZED")
        self.assertEqual(d["next_position"], 1)
        self.assertEqual(set(d["positions"].values()), {st.PENDING})
        d = self.check({})
        self.assertEqual(name(d), "NOT_AUTHORIZED")
        self.assertFalse(d["complete"])

    def test_after_any_ordinary_game_the_study_is_in_progress(self):
        for n in range(1, 6):
            d = self.check(games(n))
            self.assertEqual(name(d), "IN_PROGRESS")
            self.assertFalse(d["complete"])
            self.assertEqual(d["next_position"], n + 1)
            self.assertEqual(sum(v == st.PENDING for v in d["positions"].values()), 6 - n)

    def test_structural_stop_inside_a_batch(self):
        d = self.check(games(2, p2={"stop": "structural"}))
        self.assertEqual(name(d), "INVALID")
        self.assertEqual(d["stop"]["position"], 2)
        self.assertEqual(d["stop"]["at"], "game")
        self.assertEqual(d["positions"]["2"], st.STOPPED_HERE)
        self.assertEqual([d["positions"][str(p)] for p in range(3, 7)], [st.AFTER_STOP] * 4)
        self.assertIsNone(d["next_position"])
        self.assertFalse(d["complete"])

    def test_stop_exactly_at_a_batch_boundary(self):
        d = self.check(games(3, p3={"gate": "harm"}))
        self.assertEqual((name(d), d["stop"]["at"], d["stop"]["batch"]), ("REJECT", "batch", "A"))
        d = self.check(games(3, p3={"stop": "structural", "gate": "harm"}))
        self.assertEqual((name(d), d["stop"]["at"]), ("INVALID", "game"))   # the game check comes first

    def test_severe_harm_and_agent_failure_and_futility(self):
        self.assertEqual(name(self.check(games(4, p4={"stop": "harm"}))), "REJECT")
        self.assertEqual(name(self.check(games(1, p1={"stop": "agent"}))), "AGENT_FAILURE")
        self.assertEqual(name(self.check(games(5, p5={"gate": "futility"}))), "UNFAVOURABLE")

    def test_normal_completion(self):
        d = self.check(games(6))
        self.assertEqual(name(d), "PROMISING")
        self.assertTrue(d["complete"])
        d = self.check(games(6, p6={"gate": "complete", "score": -10}))
        self.assertEqual(name(d), "INCONCLUSIVE")                 # a "complete" gate still goes to the final rule
        self.assertTrue(d["complete"])

    def test_a_game_recorded_after_the_stop_is_a_protocol_violation(self):
        d = self.check(games(4, p2={"stop": "harm"}))
        self.assertEqual(name(d), "INVALID")
        self.assertEqual(d["stop"]["position"], 2)                # the stop itself stays recorded
        self.assertEqual(d["positions"]["3"], st.VIOLATION)
        self.assertTrue(d["protocol_problems"])

    def test_a_gap_and_a_foreign_position(self):
        played = games(3)
        del played[2]
        d = self.check(played)
        self.assertEqual(name(d), "INVALID")
        self.assertEqual(d["positions"]["3"], st.VIOLATION)
        played = games(2)
        played[9] = {"score": 1}
        self.assertEqual(name(self.check(played)), "INVALID")

    def test_missing_future_games_are_not_invalid_games(self):
        d = self.check(games(4))
        self.assertEqual(name(d), "IN_PROGRESS")
        self.assertEqual([d["positions"][str(p)] for p in (5, 6)], [st.PENDING, st.PENDING])


class PlantedReportErrorTests(unittest.TestCase):
    def test_a_stopped_batch_reported_as_inconclusive_is_detected(self):
        played = games(2, p2={"stop": "structural"})
        derived = st.derive(RULES, played)
        stored = json.loads(json.dumps(derived))
        stored["disposition"] = {"disposition": "INCONCLUSIVE", "why": "gates stored: none"}   # Sprint 35's defect
        self.assertIn("stored disposition does not match the derivation", st.check_stored(derived, stored))
        stored = json.loads(json.dumps(derived))
        stored["stop"] = None
        self.assertIn("stored stop does not match the derivation", st.check_stored(derived, stored))
        stored = json.loads(json.dumps(derived))
        stored["complete"] = True
        self.assertIn("stored complete does not match the derivation", st.check_stored(derived, stored))
        self.assertEqual(st.check_stored(derived, json.loads(json.dumps(derived))), [])

    def test_restatement_catches_a_derivation_that_ignores_game_stops(self):
        played = games(2, p2={"stop": "structural"})
        derived = st.derive(RULES, played)
        broken = json.loads(json.dumps(derived))
        broken["disposition"]["disposition"] = "IN_PROGRESS"
        broken["stop"] = None
        self.assertTrue(st.agree(broken, st.restate(RULES, played)))
        self.assertEqual(st.agree(derived, st.restate(RULES, played)), [])

    def test_rules_digest_depends_on_the_rule_source(self):
        other = st.Rules(rules_id="synthetic-rules-1", batches=RULES.batches, game_stop=lambda f, h: None,
                         batch_gate=batch_gate, final=final, stop_dispositions=RULES.stop_dispositions,
                         not_started="NOT_AUTHORIZED", in_progress="IN_PROGRESS")
        self.assertNotEqual(other.digest(), RULES.digest())

    def test_rules_must_cover_every_stop_kind_and_contiguous_positions(self):
        bad = st.Rules(rules_id="x", batches=(("A", (1, 3)),), game_stop=game_stop, batch_gate=batch_gate,
                       final=final, stop_dispositions=RULES.stop_dispositions, not_started="N", in_progress="P")
        with self.assertRaises(ValueError):
            st.derive(bad, {})


class PublicationPolicyTests(unittest.TestCase):
    """Colliding values are built arithmetically so that this file itself carries none."""

    HELD = 380 + 7.383          # a mean held value in the colliding range
    STEPS = 380 + 8             # an integer that collides
    HALF = 380 + 9.5

    def test_colliding_numbers_are_rewritten_value_preserving(self):
        data = {"mean_held_value": self.HELD, "steps": self.STEPS, "ok": 1000 + self.STEPS,
                "list": [self.HALF, 12.0], "text": "v" + str(self.STEPS)}
        self.assertTrue(pub.collisions(json.dumps(data)))
        text = pub.dumps(data, indent=1, sort_keys=True)
        self.assertEqual(pub.collisions(text), [])
        back = json.loads(text)
        self.assertEqual(set(back), set(data))
        self.assertEqual(back["mean_held_value"], self.HELD)
        self.assertEqual(back["steps"], self.STEPS)
        self.assertEqual(back["list"], [self.HALF, 12.0])
        self.assertIn("e+02", text)

    def test_unaffected_document_is_byte_identical(self):
        data = {"a": 1.5, "b": [1, 2]}
        self.assertEqual(pub.dumps(data, indent=1, sort_keys=True), json.dumps(data, indent=1, sort_keys=True))

    def test_a_colliding_string_is_refused(self):
        with self.assertRaises(ValueError):
            pub.dumps({f"{self.STEPS + 0.5} seconds": 1})
        with self.assertRaises(ValueError):
            pub.dumps({"note": f"offset {self.STEPS + 0.1} s"})


if __name__ == "__main__":
    unittest.main()
