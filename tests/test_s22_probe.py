"""The Sprint 22 probe rules (``evaluation/s22_probe.py``) and observer (``evaluation/s22_capture.py``).

SYNTHETIC inputs throughout: witness rows, ledgers, records, action lists and a stand-in transport world
(``tests/test_t2_transport_p1.StandInWorld``) that plays the real ``baseline-v2`` with the candidate. What is pinned:
witness selection (every minimum, the ranking order, the tiers, the feasibility boundary); the card, its schedule,
pins, budget and the session mapping (exactly session 2796); every ledger defect including a second session; the
per-game structural checks; the registered-difference check and the prefix check clause by clause; every endpoint fact
and its failure, the stacking boundary at 3 and 4, and the disposition order; the public guard; the observer's
reconstruction, memory chain and difference check against a live agent; and the whitelist of the new identity.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent.boundary import Observation, Origin
from miaosuan_agent.decision import INERT_ID, Memory
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s22_capture as cap
from miaosuan_agent.evaluation import s22_probe as sp
from miaosuan_agent.experiments import t2_transport_p1 as t2
from miaosuan_agent.experiments.exploratory_addon import AddonMemory
from tests import test_t2_transport_p1 as tt
from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
INF, CAR, OTHER = tt.INF, tt.CAR, tt.OTHER
SEAT, RED = tt.SEAT, tt.RED


def builder():
    spec = importlib.util.spec_from_file_location("bs22_test", ROOT / "scripts" / "build_s22_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(game: str, **overrides: Any) -> Dict[str, Any]:
    out = {"game": game, "tier": 1, "full_step_capture": True, "inert_opponent": True, "reconstruction_exact": True,
           "trigger": True, "before_first_fire": True, "carrier_route_to_objective": True, "time_feasible": True,
           "destination_saturated_in_history": False, "destination_taken_by_another_unit_before_release": False,
           "free_flow_saving": 100, "infantry_cannot_arrive_on_foot": True, "trigger_step": 1}
    out.update(overrides)
    return out


class SelectionTest(unittest.TestCase):
    def test_every_minimum_excludes(self) -> None:
        for name in sp.MINIMUMS:
            with self.subTest(name):
                chosen = sp.select_witness([row("a", **{name: False})])
                self.assertIsNone(chosen["chosen"])
                self.assertEqual(chosen["failures"]["a"], [name])

    def test_ranking_order(self) -> None:
        pairs = [("destination_saturated_in_history", True, False),
                 ("destination_taken_by_another_unit_before_release", True, False),
                 ("free_flow_saving", 0, 1), ("infantry_cannot_arrive_on_foot", False, True),
                 ("trigger_step", 5, 4)]
        for name, worse, better in pairs:
            with self.subTest(name):
                rows = [row("a", **{name: worse}), row("b", **{name: better})]
                self.assertEqual(sp.select_witness(rows)["chosen"]["game"], "b")
        self.assertEqual(sp.select_witness([row("b"), row("a")])["chosen"]["game"], "a")
        self.assertEqual(sp.select_witness([row("a", destination_saturated_in_history=True, trigger_step=0,
                                                free_flow_saving=999),
                                            row("b", trigger_step=9, free_flow_saving=1)])["chosen"]["game"], "b")
        self.assertEqual(sp.select_witness([row("a", free_flow_saving=0, trigger_step=0),
                                            row("b", infantry_cannot_arrive_on_foot=False,
                                                trigger_step=9)])["chosen"]["game"], "b")

    def test_tier_two_only_without_an_eligible_tier_one_game(self) -> None:
        rows = [row("a", tier=2, trigger_step=0), row("b", tier=1, trigger_step=9, free_flow_saving=0)]
        self.assertEqual(sp.select_witness(rows)["chosen"]["game"], "b")
        rows[1]["trigger"] = False
        self.assertEqual(sp.select_witness(rows)["chosen"]["game"], "a")

    def test_feasibility_boundary(self) -> None:
        self.assertTrue(sp.feasible(1, 100, 1 + 3 * 75 + 100 + 1))
        self.assertFalse(sp.feasible(1, 100, 1 + 3 * 75 + 100))

    def test_published_witness_is_the_rule_applied_to_its_rows(self) -> None:
        witness = json.loads((ROOT / "evaluation" / sp.STUDY_ID / "witness.json").read_text(encoding="utf-8"))
        self.assertEqual(len(witness["rows"]), 12)
        chosen = sp.select_witness(witness["rows"])
        self.assertEqual(chosen["chosen"]["game"], witness["selected"])
        self.assertEqual(chosen["eligible"], witness["eligible_in_rank_order"])
        self.assertEqual(witness["selected"], sp.RULES["witness"]["game"])
        selected = next(r for r in witness["rows"] if r["game"] == witness["selected"])
        for key in ("tier", "trigger_decision", "trigger_step", "destination", "carrier_free_flow",
                    "infantry_free_flow_to_destination"):
            self.assertEqual(selected[key], sp.RULES["witness"][key], key)
        self.assertEqual((selected["scenario_id"], selected["condition"], selected["seat_side"]),
                         (sp.SCHEDULE[0][1], sp.SCHEDULE[0][2], "blue"))


class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = builder()
        cls.card = cls.builder.build()

    def test_committed_card_rebuilds_byte_for_byte(self) -> None:
        self.assertEqual(self.builder.CARD.read_text(encoding="utf-8"), sp.dump(self.card))
        self.assertEqual(sp.card_problems(self.card, ROOT), [])

    def test_schedule_seats_session_and_budget(self) -> None:
        self.assertEqual(len(self.card["games"]), 1)
        game = self.card["games"][0]
        self.assertEqual((game["game_id"], game["scenario_id"], game["condition"], game["red"], game["blue"]),
                         ("1930331196.C3.s22-t2-transport-probe-1.p01", "1930331196", "C3", INERT_ID, sp.CANDIDATE_ID))
        self.assertEqual(self.card["budget"]["ledger_base_session"], 2795)
        self.assertEqual(self.card["budget"]["sprint_session_cap"], 1)
        self.assertEqual(self.card["screen"]["expected_sessions"], [2796])
        self.assertEqual((sp.LEDGER_BASE_SESSION, sp.SESSION_CEILING, sp.EXPECTED_SESSIONS), (2795, 1, (2796,)))

    def test_card_problems_catch_every_pin(self) -> None:
        cases = {"rules": lambda c: c["screen"]["rules"].update(stacking_limit=5),
                 "frozen": lambda c: c["screen"]["frozen_files"].update({sp.FROZEN_FILES[0]: "0" * 64}),
                 "policy": lambda c: c["policies"][sp.CANDIDATE_ID]["policy_source"].update(sha256="0" * 64),
                 "budget": lambda c: c["budget"].update(sprint_session_cap=2),
                 "schedule": lambda c: c["games"][0].update(condition="C2"),
                 "stops": lambda c: c["screen"].update(structural_stops=["S1"]),
                 "candidate": lambda c: c.update(candidate="other")}
        for name, change in cases.items():
            card = copy.deepcopy(self.card)
            change(card)
            self.assertTrue(sp.card_problems(card, ROOT), name)
        self.assertEqual(sp.card_problems({"card_id": "x"}, ROOT), ["not the Sprint 22 probe card"])

    def test_frozen_pins_cover_the_candidate_the_rules_the_observer_and_both_test_files(self) -> None:
        for rel in ("src/miaosuan_agent/experiments/t2_transport_p1.py", "src/miaosuan_agent/evaluation/s22_probe.py",
                    "src/miaosuan_agent/evaluation/s22_capture.py", "tests/test_t2_transport_p1.py",
                    "tests/test_s22_probe.py", "scripts/run_s22_game.py", "scripts/s22_analysis.py"):
            self.assertIn(rel, sp.FROZEN_FILES)

    def test_rules_are_the_registered_values(self) -> None:
        self.assertEqual((sp.RULES["max_step"], sp.RULES["timing_basis"], sp.RULES["documented_transition_steps"],
                          sp.RULES["transition_bound_steps"], sp.RULES["stacking_limit"]),
                         (2880, "DOCUMENTED_75", 75, 150, 4))
        self.assertEqual(sp.DISPOSITIONS, ("T2_P1_PROTOCOL_AMBIGUOUS", "T2_P1_NO_DETERMINISTIC_WITNESS",
                                           "CAPTURE_INVALID", "T2_P1_DESTINATION_CAPACITY_BLOCKED",
                                           "T2_P1_MECHANISM_REFUTED", "T2_P1_MECHANISM_SUPPORTED"))


def open_(session: int, game: str, card: Dict[str, Any], state: str = "s", digest: str = sp.CANDIDATE_DIGEST):
    return {"session": session, "event": "session-open", "state": state,
            "harness": {"game_id": game, "card": sp.CARD_ID, "manifest_sha256": mf.digest(card),
                        "policy_source_sha256": digest}}


def close(session: int, ok: bool = True, event: str = "session-close"):
    return {"session": session, "event": event, "state": "s", "integrity": {"ok": ok}}


class LedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.card = builder().build()
        cls.game = cls.card["games"][0]["game_id"]

    def audit(self, records):
        return sp.ledger_audit([{"session": 2795, "event": "session-close", "state": "s", "integrity": {"ok": True}}]
                               + records, self.card)

    def test_the_registered_session_passes_and_none_also_passes(self) -> None:
        ok = self.audit([open_(2796, self.game, self.card), close(2796)])
        self.assertEqual((ok["ok"], ok["sessions"], ok["unclosed"], ok["games"]), (True, 1, [], {self.game: 2796}))
        self.assertEqual(self.audit([])["sessions"], 0)
        self.assertTrue(self.audit([])["ok"])

    def test_every_defect_is_found(self) -> None:
        g = self.game
        cases = {
            "outside": ([open_(2796, "other", self.card), close(2796)], "S2"),
            "unclosed": ([open_(2796, g, self.card)], "S2"),
            "recovered": ([open_(2796, g, self.card), close(2796, event="session-recovered")], "S2"),
            "integrity": ([open_(2796, g, self.card), close(2796, ok=False)], "S1"),
            "state": ([open_(2796, g, self.card, state="other"), close(2796)], "S1"),
            "digest": ([open_(2796, g, self.card, digest="0" * 64), close(2796)], "S2"),
            "second session": ([open_(2796, g, self.card), close(2796), open_(2797, g, self.card), close(2797)], "S2"),
        }
        for name, (records, code) in cases.items():
            found = self.audit(records)
            self.assertFalse(found["ok"], name)
            self.assertTrue(found["problems"][code], name)
        found = self.audit([open_(2796, g, self.card), close(2796), open_(2797, g, self.card), close(2797)])
        self.assertIn("2 sessions exceed the ceiling of 1", found["problems"]["S2"])
        self.assertTrue(any("not the expected [2796]" in p for p in found["problems"]["S2"]))

    def test_structural_stop_mapping(self) -> None:
        self.assertEqual(sp.structural_stops({"S5": ["x"], "SP": ["y"], "S7": ["z"], "S3": []}), ["S7", "SP"])


class GameStopsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = {"game_id": "g", "scenario_id": "1930331196", "condition": "C3", "red": INERT_ID,
                      "blue": sp.CANDIDATE_ID}
        self.record = {"status": "COMPLETED", "steps": 3, "scenario_id": "1930331196", "condition": "C3",
                       "session_close": {"integrity": {"ok": True}},
                       "harness": {"game_id": "g", "card": sp.CARD_ID, "policy_source_sha256": sp.CANDIDATE_DIGEST},
                       "final_scores": {"blue_win": 10, "blue_total": 30, "red_total": 20},
                       "seats": [{"seat": 11, "faction": 1, "policy": sp.CANDIDATE_ID, "contract_errors": 0,
                                  "replay_mismatches": 0, "actions_by_type": {"1": 5}},
                                 {"seat": 1, "faction": 0, "policy": INERT_ID, "contract_errors": 0,
                                  "replay_mismatches": 0}]}
        self.t9 = {"steps": 3, "seats": {"1": {"moves": {"emitted": 5}}}}
        self.explore = {"steps": 3, "addon_errors": []}
        self.timeline = {"steps": [{}, {}, {}], "reconstructed_decisions": 3, "consistency_errors": [],
                         "unregistered_differences": []}

    def stops(self, **changes):
        args = dict(entry=self.entry, record=self.record, t9cap=self.t9, explore=self.explore, timeline=self.timeline,
                    max_step=2880, capture_digests={"t9.json": ("a", "a")})
        args.update(changes)
        return sp.game_stops(**args)

    def test_a_clean_game_has_no_stop(self) -> None:
        self.assertEqual(self.stops(), {})

    def test_each_defect_maps_to_its_code(self) -> None:
        def rec(**kw):
            r = copy.deepcopy(self.record)
            r.update(kw)
            return r
        cases = {
            "S1": dict(record=rec(session_close={"integrity": {"ok": False}})),
            "S4": dict(record=rec(status="FAILED")),
            "S6": dict(record=rec(seats=[dict(self.record["seats"][0], replay_mismatches=1), self.record["seats"][1]])),
            "S7": dict(timeline=dict(self.timeline, unregistered_differences=[{"k": 1}])),
        }
        for code, change in cases.items():
            self.assertIn(code, self.stops(**change), code)
        more = [dict(timeline=dict(self.timeline, consistency_errors=[{"k": 1}])), dict(max_step=2881),
                dict(capture_digests={"t9.json": ("a", "b")}), dict(explore={"steps": 3, "addon_errors": ["e"]}),
                dict(t9cap={"steps": 3, "seats": {"1": {"moves": {"emitted": 4}}}}),
                dict(timeline=dict(self.timeline, reconstructed_decisions=2)),
                dict(record=rec(harness=dict(self.record["harness"], policy_source_sha256="0")))]
        for change in more:
            self.assertIn("S7", self.stops(**change), change)
        bad_margin = rec(final_scores={"blue_win": 11, "blue_total": 30, "red_total": 20})
        self.assertIn("S4", self.stops(record=bad_margin))


def move(obj_id: int, path: List[int]) -> Dict[str, Any]:
    return {"actor": SEAT, "obj_id": obj_id, "type": 1, "move_path": path}


class DifferenceTest(unittest.TestCase):
    base = [move(OTHER, [1, 2]), move(INF, [3]), move(CAR, [4, 5])]
    embark = {"actor": SEAT, "obj_id": INF, "type": 3, "target_obj_id": CAR}
    disembark = {"actor": SEAT, "obj_id": CAR, "type": 4, "target_obj_id": INF}

    def diff(self, live, before, after, pair=(INF, CAR), base=None):
        return sp.unregistered_differences(base if base is not None else self.base, live, before, after, pair)

    def test_registered_edits_pass(self) -> None:
        self.assertEqual(self.diff([self.base[0], self.embark], "READY", "EMBARK_REQUESTED"), [])
        for state in ("EMBARK_REQUESTED", "AT_DESTINATION", "DISEMBARK_REQUESTED"):
            self.assertEqual(self.diff(self.base[:2], "EMBARK_REQUESTED" if state != "AT_DESTINATION"
                                       else "CARRIER_RELEASED", state), [], state)
        self.assertEqual(self.diff([self.base[0], self.base[1], self.disembark], "AT_DESTINATION",
                                   "DISEMBARK_REQUESTED"), [])
        self.assertEqual(self.diff([self.base[0], self.base[1], self.disembark], "AT_DESTINATION",
                                   "DISEMBARK_REQUESTED", base=self.base[:2]), [])
        self.assertEqual(self.diff(list(self.base), "READY", "READY", pair=None), [])

    def test_unregistered_edits_fail(self) -> None:
        cases = {
            "other unit changed": ([move(OTHER, [9]), self.embark], "READY", "EMBARK_REQUESTED"),
            "order changed": ([self.base[2], self.base[1], self.base[0]], "CARRIER_RELEASED", "CARRIER_RELEASED"),
            "embark outside the trigger": ([self.base[0], self.embark], "CARRIER_RELEASED", "CARRIER_RELEASED"),
            "embark to another carrier": ([self.base[0], dict(self.embark, target_obj_id=OTHER)], "READY",
                                          "EMBARK_REQUESTED"),
            "hold outside a hold state": (self.base[:2], "EMBARK_REQUESTED", "CARRIER_RELEASED"),
            "disembark outside the destination": ([self.base[0], self.base[1], self.disembark], "CARRIER_RELEASED",
                                                  "CARRIER_RELEASED"),
            "infantry action dropped": ([self.base[0], self.base[2]], "CARRIER_RELEASED", "CARRIER_RELEASED"),
            "embark moved to the end": ([self.base[0], self.base[2], self.embark], "READY", "EMBARK_REQUESTED"),
        }
        for name, (live, before, after) in cases.items():
            self.assertTrue(self.diff(live, before, after), name)
        self.assertTrue(self.diff([self.base[0]], "READY", "READY", pair=None))


class PrefixTest(unittest.TestCase):
    reference = {"trigger_decision": 2, "trigger_actions": "T", "pair": [INF, CAR]}

    def test_the_registered_prefix_passes(self) -> None:
        self.assertEqual(sp.prefix_problems(self.reference, ["a", "b", "T"], ["a", "b", "x"], "T", (INF, CAR)), [])

    def test_every_clause_fails_alone(self) -> None:
        self.assertTrue(sp.prefix_problems(self.reference, ["a", "z", "T"], ["a", "b", "x"], "T", (INF, CAR)))
        self.assertTrue(sp.prefix_problems(self.reference, ["a", "b", "U"], ["a", "b", "x"], "U", (INF, CAR)))
        self.assertTrue(sp.prefix_problems(self.reference, ["a", "b", "T"], ["a", "b", "x"], "T", (INF, OTHER)))
        self.assertTrue(sp.prefix_problems(self.reference, ["a", "b", "T"], ["a", "b", "x"], "T", None))
        self.assertTrue(sp.prefix_problems(self.reference, ["a", "b"], ["a", "b"], None, None))


def play_world(world: "tt.StandInWorld", steps: int, refuse: Any = None):
    """Run the candidate agent in the stand-in world; return the raw views, emitted actions and synthetic feedback
    (one echo per emitted action, with an error for the action types in ``refuse``)."""
    agent = t2.TransportAgent()
    agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
    raws, submitted, feedback, decisions = [], [], [], []
    for _ in range(steps):
        raw = world.observation()
        memory = agent.memory
        actions = [dict(a) for a in agent.step(raw)]
        decisions.append({"observation": raw, "memory": memory, "trace": agent.last_trace,
                          "submitted": copy.deepcopy(actions), "seat": SEAT, "faction": RED, "policy": sp.CANDIDATE_ID})
        raws.append(raw)
        submitted.append(copy.deepcopy(actions))
        echoes = []
        applied = []
        for a in actions:
            refused = refuse is not None and a["type"] in refuse
            echoes.append({"message": dict(a), **({"error": {"code": 999}} if refused else {})})
            if not refused:
                applied.append(a)
        feedback.append(echoes)
        world.apply(applied)
    return raws, submitted, feedback, decisions


class FactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raws, cls.submitted, cls.feedback, _ = play_world(tt.StandInWorld(), 700)

    def facts(self, raws=None, submitted=None, feedback=None, pair=(INF, CAR), trigger=0):
        frames = [sp.Frame(r, RED, SEAT) for r in (raws or self.raws)]
        return sp.transport_facts(frames, submitted or self.submitted, feedback or self.feedback, pair, trigger)

    def verdict(self, facts):
        embark = sp.embark_endpoint(facts["embark"])
        carry = sp.carry_endpoint(facts["carry"]) if "carry" in facts else None
        stacking = sp.stacking_endpoint(facts["stacking"]) if "stacking" in facts else None
        disembark = sp.disembark_endpoint(facts["disembark"]) if "disembark" in facts else None
        return sp.disposition(None, [], embark, carry, stacking, disembark), (embark, carry, stacking, disembark)

    def test_the_complete_chain_is_supported(self) -> None:
        facts = self.facts()
        verdict, (embark, carry, stacking, disembark) = self.verdict(facts)
        self.assertEqual(verdict["disposition"], sp.SUPPORTED, (embark, carry, stacking, disembark))
        self.assertEqual(facts["embark"]["aboard_after"], 75)
        self.assertEqual(facts["disembark"]["ground_after"], 75)
        self.assertEqual(facts["stacking"]["ground_units_at_check"], 1)
        self.assertEqual(facts["post"]["aboard_cleared"], True)
        self.assertEqual(facts["private"]["destination"], tt.DEST)
        self.assertGreater(facts["carry"]["aboard_decisions"], 0)
        self.assertEqual((facts["carry"]["passenger_breaks"], facts["carry"]["position_mismatches"],
                          facts["carry"]["actions_for_passenger"]), (0, 0, 0))

    def test_refused_embark_and_refused_disembark(self) -> None:
        for refused, failing in (({3}, "embark"), ({4}, "disembark")):
            raws, submitted, feedback, _ = play_world(tt.StandInWorld(), 700, refuse=refused)
            verdict, _ = self.verdict(self.facts(raws, submitted, feedback))
            self.assertEqual(verdict["disposition"], sp.REFUTED, refused)
            self.assertIn(failing, verdict["failed"])

    def test_blocked_at_four_and_not_at_three(self) -> None:
        raws, submitted, feedback, _ = play_world(tt.StandInWorld(extra_ground_at_dest=3), 700)
        facts = self.facts(raws, submitted, feedback)
        verdict, _ = self.verdict(facts)
        self.assertEqual((verdict["disposition"], facts["stacking"]["ground_units_at_check"]), (sp.BLOCKED, 4))
        raws, submitted, feedback, _ = play_world(tt.StandInWorld(extra_ground_at_dest=2), 700)
        facts = self.facts(raws, submitted, feedback)
        verdict, _ = self.verdict(facts)
        self.assertEqual((verdict["disposition"], facts["stacking"]["ground_units_at_check"]), (sp.SUPPORTED, 3))

    def tampered(self, change) -> Dict[str, Any]:
        raws = copy.deepcopy(self.raws)
        change(raws, self.facts()["private"]["decisions"])
        return self.verdict(self.facts(raws))[0]

    def test_planted_defects_refute(self) -> None:
        def passenger_break(raws, d):
            raws[d["aboard"] + 5]["passengers"] = []
        def position(raws, d):
            raws[d["move"] + 7]["passengers"][0]["cur_hex"] = 101
        def inconsistent(raws, d):
            raws[d["aboard"] + 3]["passengers"][0]["car"] = OTHER
        def not_on_destination(raws, d):
            for u in raws[d["landing"]]["operators"]:
                if u["obj_id"] == INF:
                    u["cur_hex"] = 101
        def carrier_gone(raws, d):
            raws[d["order"] + 2]["operators"] = [u for u in raws[d["order"] + 2]["operators"] if u["obj_id"] != CAR]
        def uncontrolled(raws, d):
            raws[d["aboard"] + 2]["role_and_grouping_info"][SEAT]["operators"] = [INF]
        for change in (passenger_break, position, inconsistent, not_on_destination, carrier_gone, uncontrolled):
            verdict = self.tampered(change)
            self.assertEqual(verdict["disposition"], sp.REFUTED, change.__name__)

    def test_no_arrival_and_no_aboard(self) -> None:
        d = self.facts()["private"]["decisions"]
        verdict, _ = self.verdict(self.facts(self.raws[:d["arrival"]], self.submitted[:d["arrival"]],
                                             self.feedback[:d["arrival"]]))
        self.assertEqual((verdict["disposition"], verdict["failed"]), (sp.REFUTED, ["carry", "disembark"]))
        verdict, _ = self.verdict(self.facts(self.raws[:d["aboard"]], self.submitted[:d["aboard"]],
                                             self.feedback[:d["aboard"]]))
        self.assertEqual(verdict["failed"], ["embark", "carry", "disembark"])

    def test_aboard_waits_for_the_embark_fields_to_clear(self) -> None:
        raws = copy.deepcopy(self.raws)
        d = self.facts()["private"]["decisions"]
        for j in range(d["aboard"], d["aboard"] + 3):
            for u in raws[j]["operators"]:
                if u["obj_id"] == CAR:
                    u["get_on_remain_time"], u["get_on_partner_id"] = 1, [INF]
        facts = self.facts(raws)
        self.assertEqual((facts["embark"]["relation_after"], facts["embark"]["aboard_after"]), (75, 78))

    def test_actions_for_the_passenger_while_aboard_refute(self) -> None:
        submitted = copy.deepcopy(self.submitted)
        d = self.facts()["private"]["decisions"]
        submitted[d["aboard"] + 4].append({"actor": SEAT, "obj_id": INF, "type": 1, "move_path": [101]})
        verdict, _ = self.verdict(self.facts(submitted=submitted))
        self.assertEqual(verdict["disposition"], sp.REFUTED)

    def test_endpoint_bounds_are_exact(self) -> None:
        good = {"emitted": True, "response": True, "aboard_after": 150, "inconsistent_decisions": 0,
                "carrier_present_and_controlled": True}
        self.assertTrue(sp.embark_endpoint(good)["ok"])
        self.assertFalse(sp.embark_endpoint(dict(good, aboard_after=151))["ok"])
        self.assertFalse(sp.embark_endpoint(dict(good, response=None))["ok"])
        self.assertFalse(sp.embark_endpoint(dict(good, response=False))["ok"])
        self.assertEqual(sp.embark_endpoint(dict(good, response=False))["reasons"], ["embark refused"])
        dis = {"listed_after": 150, "emitted": 1, "response": True, "ground_after": 150, "on_destination": True,
               "inconsistent_decisions": 0, "carrier_present": True}
        self.assertTrue(sp.disembark_endpoint(dis)["ok"])
        for change in (dict(listed_after=151), dict(ground_after=151), dict(emitted=2), dict(emitted=0),
                       dict(listed_after=None)):
            self.assertFalse(sp.disembark_endpoint(dict(dis, **change))["ok"], change)
        self.assertEqual(sp.stacking_endpoint({"ground_units_at_check": 3})["blocked"], False)
        self.assertEqual(sp.stacking_endpoint({"ground_units_at_check": 4})["blocked"], True)

    def test_accepted_reads_one_echo(self) -> None:
        action = {"type": 3, "obj_id": INF, "target_obj_id": CAR}
        self.assertIs(sp.accepted([{"message": dict(action)}], action), True)
        self.assertIs(sp.accepted([{"message": dict(action), "error": {"code": 1}}], action), False)
        self.assertIsNone(sp.accepted([], action))
        self.assertIsNone(sp.accepted([{"message": dict(action)}, {"message": dict(action)}], action))


class DispositionTest(unittest.TestCase):
    ok = {"ok": True, "reasons": []}
    bad = {"ok": False, "reasons": ["x"]}

    def test_order(self) -> None:
        d = sp.disposition
        self.assertEqual(d(sp.AMBIGUOUS, [], None, None, None, None)["disposition"], sp.AMBIGUOUS)
        self.assertEqual(d(sp.NO_WITNESS, [], None, None, None, None)["disposition"], sp.NO_WITNESS)
        with self.assertRaises(ValueError):
            d(sp.SUPPORTED, [], None, None, None, None)
        blocked = {"blocked": True}
        free = {"blocked": False}
        self.assertEqual(d(None, ["p"], self.ok, self.ok, blocked, self.ok)["disposition"], sp.INVALID)
        self.assertEqual(d(None, [], None, None, None, None)["disposition"], sp.INVALID)
        self.assertEqual(d(None, [], self.ok, self.ok, blocked, self.bad)["disposition"], sp.BLOCKED)
        self.assertEqual(d(None, [], self.bad, self.ok, blocked, self.bad)["disposition"], sp.REFUTED)
        self.assertEqual(d(None, [], self.ok, self.bad, blocked, self.bad)["disposition"], sp.REFUTED)
        self.assertEqual(d(None, [], self.ok, self.ok, free, self.bad)["disposition"], sp.REFUTED)
        self.assertEqual(d(None, [], self.ok, None, None, None)["disposition"], sp.REFUTED)
        self.assertEqual(d(None, [], self.ok, self.ok, free, self.ok)["disposition"], sp.SUPPORTED)

    def test_public_guard(self) -> None:
        self.assertTrue(sp.public_check({"a": INF}, [INF]))
        self.assertTrue(sp.public_check({str(CAR): 1}, [CAR]))
        self.assertTrue(sp.public_check({"a": f"unit {INF} moved"}, [INF]))
        self.assertTrue(sp.public_check({"units": 1}))
        self.assertEqual(sp.public_check({"a": 1, "b": "text"}, [INF]), [])


class ObserverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.costs = tt.COSTS
        _, _, _, cls.decisions = play_world(tt.StandInWorld(), 400)

    def test_reconstruction_memory_chain_and_differences_agree_with_the_live_agent(self) -> None:
        expected = (Memory(), ())
        states = []
        for decision in self.decisions:
            rebuilt = cap.reconstruct(decision["observation"], SEAT, RED, decision["memory"], self.costs)
            checks = cap.consistency(decision, rebuilt, expected)
            self.assertTrue(all(checks.values()), checks)
            self.assertEqual(sp.unregistered_differences(rebuilt["baseline_actions"], decision["submitted"],
                                                         rebuilt["state_before"], rebuilt["state_after"],
                                                         rebuilt["pair"]), [])
            expected = (rebuilt["baseline_memory_out"], rebuilt["memory_out"])
            states.append(rebuilt["state_after"])
        self.assertIn("CARRIER_RELEASED", states)
        self.assertEqual(states[0], "EMBARK_REQUESTED")

    def test_tampering_is_detected(self) -> None:
        first, second = self.decisions[0], self.decisions[1]
        previous = cap.reconstruct(first["observation"], SEAT, RED, first["memory"], self.costs)
        rebuilt = cap.reconstruct(second["observation"], SEAT, RED, second["memory"], self.costs)
        expected = (previous["baseline_memory_out"], previous["memory_out"])
        self.assertTrue(all(cap.consistency(second, rebuilt, expected).values()))
        wrong = dict(second, memory=AddonMemory(second["memory"].baseline, ()))
        self.assertFalse(cap.consistency(wrong, rebuilt, expected)["addon_memory"])
        extra = [{"actor": SEAT, "obj_id": OTHER, "type": 5}]
        self.assertFalse(cap.consistency(dict(second, submitted=list(second["submitted"]) + extra), rebuilt,
                                         expected)["actions"])
        self.assertFalse(cap.consistency(second, rebuilt, (Memory(), ()))["addon_memory"])

    def test_prefix_inputs_read_the_live_and_baseline_digests(self) -> None:
        steps = []
        for decision in self.decisions[:3]:
            rebuilt = cap.reconstruct(decision["observation"], SEAT, RED, decision["memory"], self.costs)
            other = [{"seat": 1, "action": {"actor": 1, "obj_id": 1, "type": 1, "move_path": [5]}}]
            steps.append({"submitted": other + [{"seat": SEAT, "action": a} for a in decision["submitted"]],
                          "s22": {str(SEAT): {"baseline_actions": rebuilt["baseline_actions"],
                                              "pair": list(rebuilt["pair"]) if rebuilt["pair"] else None}}})
        live = cap.prefix_inputs({"steps": steps}, SEAT, 0)
        self.assertNotEqual(live["live"][0], live["baseline"][0])
        self.assertEqual(live["trigger_actions"], cap.actions_digest(self.decisions[0]["submitted"]))
        self.assertEqual(live["pair"], [INF, CAR])


class StandInGameTest(unittest.TestCase):
    """The real game loop (``evaluation.game.play``) with the Sprint 22 observers and the transport stand-in engine
    (``tests/fixtures/s22_engine.py``): the live reconstruction, the memory chain and the difference check hold at every
    decision, and the analysis's endpoint facts reach the registered dispositions."""

    def play(self, **options):
        import itertools
        import pickle
        from miaosuan_agent.agent import PolicyAgent
        from miaosuan_agent.boundary import MoveCosts
        from miaosuan_agent.evaluation import t9_confirmation as tc
        from miaosuan_agent.evaluation.game import play
        from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
        from tests.fixtures import s22_engine as se
        steps = options.pop("play_steps", 900)
        spec = GameSpec(game_id="synthetic.C3.s22", scenario_id="900000001", map_id="9000", condition="C3",
                        red=INERT_ID, blue=sp.CANDIDATE_ID, repetition=1, max_time=steps)
        costs = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")
        timeline = cap.TransportTimeline((INERT_ID, sp.CANDIDATE_ID), costs)
        ticks = itertools.count()
        factories = {INERT_ID: lambda: PolicyAgent(INERT_ID), sp.CANDIDATE_ID: lambda: t2.TransportAgent()}
        record = play(lambda: se.TransportEnv(play_steps=steps, **options), factories, spec, se.Inputs, PLAYERS,
                      clock=lambda: next(ticks) * 0.001, replay_policies={sp.CANDIDATE_ID},
                      observer=tc.Tee(tc.T9Capture(), timeline))
        compact, windows = timeline.files()
        compact, windows = json.loads(compact), pickle.loads(windows)
        samples = sorted(windows["samples"], key=lambda s: s["k"])
        frames = [sp.Frame(pickle.loads(s["seats"][11]["observation"]), 1, 11) for s in samples]
        submitted = [[a["action"] for a in step["submitted"] if a["seat"] == 11] for step in compact["steps"]]
        feedback = [[f for f in step["feedback"] if (f.get("message") or {}).get("actor") == 11]
                    for step in compact["steps"]]
        trigger = next(k for k, acts in enumerate(submitted) if any(a.get("type") == 3 for a in acts))
        facts = sp.transport_facts(frames, submitted, feedback, (se.INF, se.CAR), trigger)
        embark = sp.embark_endpoint(facts["embark"])
        carry = sp.carry_endpoint(facts["carry"]) if "carry" in facts else None
        stacking = sp.stacking_endpoint(facts["stacking"]) if "stacking" in facts else None
        disembark = sp.disembark_endpoint(facts["disembark"]) if "disembark" in facts else None
        verdict = sp.disposition(None, [], embark, carry, stacking, disembark)
        return record, compact, facts, verdict

    def test_the_chain_through_the_real_game_loop(self) -> None:
        record, compact, facts, verdict = self.play()
        self.assertEqual(record["status"], "COMPLETED")
        self.assertEqual(record.get("observer_errors"), [])
        self.assertEqual(compact["reconstructed_decisions"], len(compact["steps"]))
        self.assertEqual((compact["consistency_errors"], compact["unregistered_differences"]), ([], []))
        self.assertEqual(verdict["disposition"], sp.SUPPORTED, facts)
        self.assertEqual((facts["embark"]["aboard_after"], facts["disembark"]["ground_after"]), (75, 75))

    def test_refused_embark_and_the_stacking_limit_through_the_real_game_loop(self) -> None:
        _, compact, _, verdict = self.play(refuse=(3,))
        self.assertEqual((verdict["disposition"], compact["unregistered_differences"]), (sp.REFUTED, []))
        _, compact, facts, verdict = self.play(extra_at_destination=3)
        self.assertEqual((verdict["disposition"], facts["stacking"]["ground_units_at_check"]), (sp.BLOCKED, 4))
        self.assertEqual(compact["unregistered_differences"], [])


class WhitelistTest(unittest.TestCase):
    def test_candidate_occurs_only_in_the_approved_sprint22_card(self) -> None:
        """Owner-approved narrow authorization (Sprint 22, 2026-10-07): the identity ``t2-transport-p1`` may appear in
        exactly one run card, ``s22-t2-transport-probe-1``, bound to the registered digest; any other JSON naming it
        lies in ``evaluation/s22-t2-transport-probe/`` and is never executable; only the Sprint 22 scripts import the
        module. A changed source is a new identity that needs new approval."""
        from miaosuan_agent.evaluation import exploratory as xp
        cards = 0
        for path in sorted((ROOT / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if t2.CANDIDATE_ID not in text and sp.CANDIDATE_DIGEST not in text:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = json.loads(text)
            if isinstance(data, dict) and (xp.is_card(data) or path.name == "manifest.json"):
                cards += 1
                self.assertEqual(rel, f"evaluation/{sp.CARD_ID}/manifest.json")
                self.assertEqual(data["policies"][sp.CANDIDATE_ID]["policy_source"]["sha256"], sp.CANDIDATE_DIGEST)
                self.assertIn("experiments/t2_transport_p1.py", data["policies"][sp.CANDIDATE_ID]["policy_source"]["files"])
                continue
            self.assertTrue(rel.startswith(f"evaluation/{sp.STUDY_ID}/"), rel)
            self.assertFalse(isinstance(data, dict) and data.get("executable"), rel)
        self.assertEqual(cards, 1)
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "run_evaluation.py",
                     "run_s17_game.py", "build_s17_card.py"):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn("t2_transport_p1", text, name)
            self.assertNotIn(t2.CANDIDATE_ID, text, name)
        users = sorted(p.name for p in (ROOT / "scripts").glob("*.py")
                       if "t2_transport_p1" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["build_s22_card.py", "mutate_s22.py", "run_s22_game.py", "s22_analysis.py"])


if __name__ == "__main__":
    unittest.main()
