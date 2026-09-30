"""Factual refusal records and the versioned attribution layer (evaluation/refusals.py)."""

from __future__ import annotations

import unittest

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import BASELINE_ID, INERT_ID
from miaosuan_agent.evaluation import metrics, refusals

from tests.fixtures import fake_engine
from tests.fixtures import synthetic as syn
from tests.test_evaluation_game import run, spec

MESSAGE = fake_engine.ENGINE_MESSAGES


def game(red=BASELINE_ID, blue=BASELINE_ID, **options):
    options.setdefault("engine_messages", True)
    return run(engine=lambda: fake_engine.FakeEnv(**options), game=spec(red=red, blue=blue))


def seat(record, number):
    return next(s for s in record["seats"] if s["seat"] == number)


class Code203UnderSeveralActionTypesTest(unittest.TestCase):
    """The same code and message on different action types are different factual classes."""

    def test_move_refused_with_203(self) -> None:
        red = seat(game(blue=INERT_ID, doomed=(2, fake_engine.RED_UNIT)), 1)
        self.assertEqual(red["refusal_facts"], [{"action_type": 1, "code": 203,
                                                 "message_class": MESSAGE[203], "count": 1}])
        self.assertEqual(red["refusal_attributions"], {refusals.ACTOR_GONE: 1})
        (entry,) = red["refusals"]
        self.assertEqual((entry["decision_index"], entry["passed_project_gate"], entry["legal_at_start"]), (1, True, True))
        self.assertEqual(entry["evidence"], {"actor_on_map_at_start": True, "actor_present_after": False})

    def test_occupation_refused_with_203_next_to_a_duplicate(self) -> None:
        record = game(blue=INERT_ID, red_wingmen=2, doomed=(7, fake_engine.RED_UNIT + 1))
        red = seat(record, 1)
        self.assertEqual(red["refusal_facts"], [
            {"action_type": 5, "code": 1804, "message_class": MESSAGE[1804], "count": 1},
            {"action_type": 5, "code": 203, "message_class": MESSAGE[203], "count": 1}])
        self.assertEqual(red["refusal_attributions"], {refusals.ACTOR_GONE: 1, refusals.DUPLICATE_OCCUPATION: 1})
        duplicate = next(r for r in red["refusals"] if r["code"] == 1804)
        self.assertEqual(duplicate["evidence"]["own_occupations_of_objective"], 3)
        self.assertEqual((duplicate["evidence"]["objective_own_at_start"], duplicate["evidence"]["objective_own_after"]),
                         (False, True))
        self.assertEqual(red["feedback_errors_by_code_and_type"], {"1804/5": 1, "203/5": 1})

    def test_shot_refused_with_203_and_shot_at_the_lost_unit_with_516(self) -> None:
        record = game(doomed=(7, fake_engine.BLUE_UNIT))
        red, blue = seat(record, 1), seat(record, 11)
        self.assertEqual(blue["refusal_facts"], [{"action_type": 2, "code": 203,
                                                  "message_class": MESSAGE[203], "count": 1}])
        self.assertEqual(blue["refusal_attributions"], {refusals.ACTOR_GONE: 1})
        self.assertEqual(red["refusal_facts"], [{"action_type": 2, "code": 516,
                                                 "message_class": MESSAGE[516], "count": 1}])
        self.assertEqual(red["refusal_attributions"], {refusals.TARGET_GONE: 1})
        (shot,) = red["refusals"]
        self.assertEqual((shot["evidence"]["target_on_map_at_start"], shot["evidence"]["target_present_after"],
                          shot["evidence"]["own_shots_at_target"]), (True, False, 1))
        self.assertTrue(shot["legal_at_start"] and shot["passed_project_gate"])
        self.assertEqual(record["refusal_schema"], {"fact": refusals.FACT_SCHEMA,
                                                    "attribution": refusals.ATTRIBUTION_VERSION})

    def test_a_message_without_a_rule_stays_unclassified(self) -> None:
        red = seat(game(blue=INERT_ID, red_wingmen=2, engine_messages=False), 1)
        self.assertEqual(red["refusal_facts"], [{"action_type": 5, "code": 1804,
                                                 "message_class": "synthetic refusal", "count": 2}])
        self.assertEqual(red["refusal_attributions"], {refusals.NO_RULE: 2})

    def test_public_summary_has_counts_not_instances(self) -> None:
        record = game(blue=INERT_ID, red_wingmen=2, doomed=(7, fake_engine.RED_UNIT + 1))
        public = metrics.public_game(record)["seats"][0]
        self.assertEqual(public["refusal_attributions"], seat(record, 1)["refusal_attributions"])
        self.assertIn("refusal_facts", public)
        self.assertNotIn("refusals", public)
        del record["seats"][0]["refusal_facts"]
        self.assertNotIn("refusal_facts", metrics.public_game(record)["seats"][0])


def record(action_type, code, message):
    return {"action_type": action_type, "code": code, "message_class": refusals.normalize_message(message)}


class AttributionRuleTest(unittest.TestCase):
    def test_actor_rule_needs_agreeing_evidence(self) -> None:
        for kind in (1, 2, 5, 9):
            fact = record(kind, 203, "CantControlDiedOperator")
            with self.subTest(kind=kind):
                self.assertEqual(refusals.attribute(fact, {"actor_on_map_at_start": True, "actor_present_after": False}),
                                 refusals.ACTOR_GONE)
                self.assertEqual(refusals.attribute(fact, {"actor_on_map_at_start": True, "actor_present_after": True}),
                                 refusals.CONTRADICTED)
                self.assertEqual(refusals.attribute(fact, {"actor_on_map_at_start": False, "actor_present_after": False}),
                                 refusals.CONTRADICTED)
                self.assertEqual(refusals.attribute(fact, {"actor_on_map_at_start": True}), refusals.MISSING)
                self.assertEqual(refusals.attribute(fact, None), refusals.EVIDENCE_FAILED)

    def test_code_alone_assigns_nothing(self) -> None:
        agreeing = {"actor_on_map_at_start": True, "actor_present_after": False,
                    "target_on_map_at_start": True, "target_present_after": False}
        self.assertEqual(refusals.attribute(record(2, 203, "SomeOtherMessage"), agreeing), refusals.NO_RULE)
        self.assertEqual(refusals.attribute(record(2, 777, "CantControlDiedOperator"), agreeing), refusals.NO_RULE)
        self.assertEqual(refusals.attribute(record(5, 516, "CantShootToDiedBop"), agreeing), refusals.NO_RULE)
        self.assertEqual(refusals.attribute(record(2, 516, "CantShootToDiedBop"), agreeing), refusals.TARGET_GONE)
        self.assertEqual(refusals.attribute(record(2, "203", "CantControlDiedOperator"), agreeing), refusals.ACTOR_GONE)

    def test_occupation_rule(self) -> None:
        fact = record(5, 1804, "CantOccupyCauseAlreadyMy")
        attribute = refusals.attribute
        self.assertEqual(attribute(fact, {"objective_own_at_start": True}), refusals.OBJECTIVE_HELD)
        evidence = {"objective_own_at_start": False, "objective_own_after": True, "own_occupations_of_objective": 2}
        self.assertEqual(attribute(fact, evidence), refusals.DUPLICATE_OCCUPATION)
        self.assertEqual(attribute(fact, dict(evidence, own_occupations_of_objective=1)), refusals.CONTRADICTED)
        self.assertEqual(attribute(fact, dict(evidence, objective_own_after=False)), refusals.CONTRADICTED)
        self.assertEqual(attribute(fact, dict(evidence, objective_own_after=None)), refusals.MISSING)
        self.assertEqual(attribute(fact, {"objective_own_at_start": None}), refusals.MISSING)
        self.assertEqual(attribute(record(2, 1804, "CantOccupyCauseAlreadyMy"), evidence), refusals.NO_RULE)

    def test_every_rule_label_is_reachable_and_distinct(self) -> None:
        labels = [label for rule in refusals.RULES for label in rule.labels]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(set(labels), {refusals.OBJECTIVE_HELD, refusals.DUPLICATE_OCCUPATION, refusals.TARGET_GONE,
                                       refusals.ACTOR_GONE})


class FactTest(unittest.TestCase):
    shot = {"type": 2, "obj_id": 1, "target_obj_id": 9, "weapon_id": 43, "actor": 7}

    def test_message_normalization(self) -> None:
        self.assertEqual(refusals.normalize_message("Unit 1234 cannot  move to 5.5"), "Unit N cannot move to N")
        self.assertEqual(refusals.normalize_message(None), refusals.NO_MESSAGE)
        self.assertEqual(refusals.normalize_message(""), refusals.NO_MESSAGE)
        self.assertEqual(len(refusals.normalize_message("x" * 500)), refusals.MESSAGE_LIMIT)

    def test_gate_fact_compares_the_identifying_fields(self) -> None:
        entry = {"message": dict(self.shot), "error": {"code": 516, "message": "CantShootToDiedBop"}}
        emitted = [dict(self.shot)]
        self.assertTrue(refusals.fact(entry, 516, 3, 40, emitted)["passed_project_gate"])
        self.assertFalse(refusals.fact(entry, 516, 3, 40, [dict(self.shot, target_obj_id=8)])["passed_project_gate"])
        self.assertFalse(refusals.fact(entry, 516, 3, 40, [])["passed_project_gate"])
        move = {"type": 1, "obj_id": 1, "move_path": [2, 3]}
        self.assertFalse(refusals.same_action(move, dict(move, move_path=[2, 4])))
        self.assertTrue(refusals.same_action(dict(move, move_path=(2, 3)), move))

    def test_listed_at_start(self) -> None:
        valid = {1: {1: None, 2: ({"target_obj_id": 9, "weapon_id": 43},)}}
        self.assertTrue(refusals.listed_at_start(self.shot, valid))
        self.assertFalse(refusals.listed_at_start(dict(self.shot, weapon_id=44), valid))
        self.assertFalse(refusals.listed_at_start(dict(self.shot, target_obj_id=8), valid))
        self.assertTrue(refusals.listed_at_start({"type": 1, "obj_id": 1}, valid))
        self.assertFalse(refusals.listed_at_start({"type": 5, "obj_id": 1}, valid))
        self.assertFalse(refusals.listed_at_start({"type": 1, "obj_id": 2}, valid))

    def test_describe_never_raises(self) -> None:
        class Broken:
            def __getattr__(self, name):
                raise KeyError(name)

        entry = {"message": dict(self.shot), "error": {"code": 516, "message": "CantShootToDiedBop"}}
        described = refusals.describe(entry, 516, 0, 3, Broken(), Broken(), [dict(self.shot)])
        self.assertEqual(described["attribution"], refusals.EVIDENCE_FAILED)
        self.assertEqual((described["evidence"], described["evidence_error"], described["legal_at_start"]),
                         (None, "KeyError", None))
        self.assertEqual((described["engine_step"], described["legal_at_start_error"]), (None, "KeyError"))

    def test_a_unit_that_boarded_is_present(self) -> None:
        def observation(operators, passengers):
            raw = syn.build_observation(units=operators, valid_actions={}, seats={}, all_seeing=True)
            raw["passengers"] = passengers
            return Observation.from_raw(raw, Origin.ENGINE)

        actor, other = syn.unit(900101, 0, 505), syn.unit(900102, 0, 506)
        before, after = observation([actor, other], []), observation([other], [actor])
        facts = refusals.evidence({"type": 1, "obj_id": 900101}, 0, before, after, [])
        self.assertEqual(facts, {"actor_on_map_at_start": True, "actor_present_after": True})
        self.assertEqual(refusals.attribute(record(1, 203, "CantControlDiedOperator"), facts), refusals.CONTRADICTED)
        gone = refusals.evidence({"type": 1, "obj_id": 900101}, 0, before, observation([other], []), [])
        self.assertEqual(gone["actor_present_after"], False)

    def test_counts_merge(self) -> None:
        a = [record(2, 203, "CantControlDiedOperator"), record(5, 203, "CantControlDiedOperator"),
             record(2, 203, "CantControlDiedOperator")]
        counts = refusals.fact_counts(a)
        self.assertEqual([(c["action_type"], c["count"]) for c in counts], [(2, 2), (5, 1)])
        self.assertEqual(refusals.merge_fact_counts([counts, counts])[0]["count"], 4)
        self.assertEqual(refusals.fact_counts([]), [])


if __name__ == "__main__":
    unittest.main()
