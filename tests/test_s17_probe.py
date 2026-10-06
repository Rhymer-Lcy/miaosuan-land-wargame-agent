"""The frozen rules of the Sprint 17 probe (``evaluation/s17_probe.py``) and its observer (``evaluation/s17_capture.py``).

Synthetic inputs throughout: ledgers, records, capture summaries, prefix digests, claimant tables and decisions of the
executable candidate on the scenes of ``tests/test_t9_delayed.py``. What is pinned: the card, its schedule, pins,
budget and the session mapping; every ledger defect including the ceiling; the per-game structural checks; the prefix
check clause by clause; the direct-fire endpoints at exactly 611 and 686; first ownership; the EARLY-PLACE BLOCK
definition (positive, negative and the removal-of-early-places counterfactual); both retirement rules at their
boundaries; the disposition order; the public sanitization; and the observer's reconstruction with its memory chain.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

from miaosuan_agent.decision import INERT_ID, Memory
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s17_capture as cap
from miaosuan_agent.evaluation import s17_probe as sp
from miaosuan_agent.experiments import exploratory_addon as ea
from miaosuan_agent.experiments import t9_post_stage_v6 as c6
from tests import test_t9_delayed as t15
from tests.fixtures import synthetic as syn
from tests.test_t9_redistribution import RED, SEAT

ROOT = Path(__file__).resolve().parents[1]


def builder():
    spec = importlib.util.spec_from_file_location("bs17_test", ROOT / "scripts" / "build_s17_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_(session: int, game: str, card: Dict[str, Any], state: str = "s", digest: str = sp.CANDIDATE_DIGEST):
    return {"session": session, "event": "session-open", "state": state,
            "harness": {"game_id": game, "card": sp.CARD_ID, "manifest_sha256": mf.digest(card),
                        "policy_source_sha256": digest}}


def close(session: int, ok: bool = True, event: str = "session-close"):
    return {"session": session, "event": event, "state": "s", "integrity": {"ok": ok}}


class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = builder()
        cls.card = cls.module.build()

    def test_committed_card_rebuilds_byte_for_byte(self) -> None:
        self.assertEqual(sp.dump(self.card), self.module.CARD.read_text(encoding="utf-8"))
        self.assertEqual(sp.card_problems(self.card, ROOT), [])

    def test_schedule_seats_sessions_and_budget(self) -> None:
        games = [(g["game_id"], g["scenario_id"], g["condition"], g["red"], g["blue"]) for g in self.card["games"]]
        self.assertEqual(games, [
            ("1930331196.C2.s17-post-stage-v6-probe-1.p01", "1930331196", "C2", sp.CANDIDATE_ID, INERT_ID),
            ("2120531121.C3.s17-post-stage-v6-probe-1.p02", "2120531121", "C3", INERT_ID, sp.CANDIDATE_ID)])
        self.assertEqual(self.card["budget"], {"batch_sessions": 2, "ledger_base_session": 2793,
                                               "sprint_session_cap": 2})
        self.assertEqual(sp.EXPECTED_SESSIONS, (2794, 2795))
        self.assertEqual([sp.LEDGER_BASE_SESSION + g["position"] for g in self.card["games"]], [2794, 2795])
        self.assertEqual(self.card["execution"], {"runtime": "baseline-v1-runtime-r2", "workers": 1})
        self.assertFalse(self.card["eligible_for_promotion"])
        self.assertEqual([sp.candidate_side(g) for g in self.card["games"]], ["red", "blue"])
        self.assertEqual(self.card["screen"]["prefix_reference"]["games"], sp.SOURCE_GAMES)

    def test_card_problems_catch_every_pin(self) -> None:
        def broken(change):
            card = json.loads(json.dumps(self.card))
            change(card)
            return sp.card_problems(card, ROOT)
        self.assertTrue(broken(lambda c: c["screen"]["rules"].update(first_ownership_deadline=565)))
        self.assertTrue(broken(lambda c: c["screen"]["frozen_files"].update(
            {sp.FROZEN_FILES[0]: "0" * 64})))
        self.assertTrue(broken(lambda c: c["policies"][sp.CANDIDATE_ID]["policy_source"].update(sha256="0" * 64)))
        self.assertTrue(broken(lambda c: c["games"].reverse()))
        self.assertTrue(broken(lambda c: c["budget"].update(sprint_session_cap=3)))
        self.assertTrue(broken(lambda c: c["screen"].update(structural_stops=["S1"])))
        self.assertTrue(broken(lambda c: c.update(candidate="t9-delayed-post-stage-any-v5")))
        self.assertEqual(broken(lambda c: c.update(card_id="other")), ["not the Sprint 17 probe card"])
        with self.assertRaises(ValueError):
            sp.build_card({}, "", [{"id": sp.V2_ID, "policy_source": {"sha256": sp.V2_DIGEST}},
                                   {"id": sp.CANDIDATE_ID, "policy_source": {"sha256": "0" * 64}}], {}, {})

    def test_frozen_pins_cover_the_candidate_the_stage_one_allocator_and_both_test_files(self) -> None:
        for rel in ("src/miaosuan_agent/experiments/t9_post_stage_v6.py", "src/miaosuan_agent/experiments/t9_batch.py",
                    "src/miaosuan_agent/experiments/t9_delayed.py", "tests/test_t9_post_stage_v6.py",
                    "tests/test_s17_probe.py", "scripts/run_s17_game.py", "scripts/s17_analysis.py"):
            self.assertIn(rel, sp.FROZEN_FILES)
        self.assertEqual(set(self.card["screen"]["frozen_files"]), set(sp.FROZEN_FILES))

    def test_rules_are_the_registered_values(self) -> None:
        self.assertEqual(sp.RULES["first_divergence"], {sp.C2: 421, sp.C212: 361})
        self.assertEqual(sp.RULES["first_divergence_redirected_vehicles"], {sp.C2: 2, sp.C212: 2})
        self.assertEqual(sp.RULES["protected_fire_decisions"], [611, 686])
        self.assertEqual((sp.RULES["problem_objective"], sp.RULES["first_ownership_deadline"],
                          sp.RULES["early_place_blocks_allowed"], sp.RULES["max_step"], sp.RULES["capacity"]),
                         ("80-point objective A", 564, 0, 2880, 4))
        self.assertEqual(sp.STRUCTURAL_STOPS, ("S1", "S2", "S3", "S4", "S6", "S7", "SP"))


class LedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.card = builder().build()
        cls.games = [g["game_id"] for g in cls.card["games"]]

    def audit(self, records):
        return sp.ledger_audit([{"session": 2793, "event": "session-close", "state": "s", "integrity": {"ok": True}}]
                               + records, self.card)

    def test_the_registered_sequence_passes(self) -> None:
        ok = self.audit([open_(2794, self.games[0], self.card), close(2794), open_(2795, self.games[1], self.card),
                         close(2795)])
        self.assertEqual((ok["ok"], ok["sessions"], ok["unclosed"]), (True, 2, []))
        self.assertEqual(ok["games"], {self.games[0]: 2794, self.games[1]: 2795})

    def test_every_defect_is_found(self) -> None:
        g0, g1 = self.games
        cases = {
            "order": ([open_(2794, g1, self.card), close(2794)], "S2"),
            "outside": ([open_(2794, "other", self.card), close(2794)], "S2"),
            "unclosed": ([open_(2794, g0, self.card)], "S2"),
            "recovered": ([open_(2794, g0, self.card), close(2794, event="session-recovered")], "S2"),
            "integrity": ([open_(2794, g0, self.card), close(2794, ok=False)], "S1"),
            "state": ([open_(2794, g0, self.card, state="other"), close(2794)], "S1"),
            "digest": ([open_(2794, g0, self.card, digest="0" * 64), close(2794)], "S2"),
            "twice": ([open_(2794, g0, self.card), close(2794), open_(2795, g0, self.card), close(2795)], "S2"),
        }
        for name, (records, code) in cases.items():
            found = self.audit(records)
            self.assertFalse(found["ok"], name)
            self.assertTrue(found["problems"][code], name)

    def test_a_third_session_exceeds_the_ceiling(self) -> None:
        g0, g1 = self.games
        found = self.audit([open_(2794, g0, self.card), close(2794), open_(2795, g1, self.card), close(2795),
                            open_(2796, g1, self.card), close(2796)])
        self.assertIn("3 sessions exceed the ceiling of 2", found["problems"]["S2"])

    def test_structural_stop_mapping(self) -> None:
        self.assertEqual(sp.structural_stops({"S5": ["x"], "SP": ["y"], "S7": ["z"], "S3": []}), ["S7", "SP"])
        self.assertEqual(sp.structural_stops({"S8": ["v3 behaviour"]}), [])


class GameStopsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = {"game_id": "g", "scenario_id": "1930331196", "condition": "C2", "red": sp.CANDIDATE_ID,
                      "blue": INERT_ID}
        self.record = {"status": "COMPLETED", "steps": 3, "scenario_id": "1930331196", "condition": "C2",
                       "session_close": {"integrity": {"ok": True}},
                       "harness": {"game_id": "g", "card": sp.CARD_ID, "policy_source_sha256": sp.CANDIDATE_DIGEST},
                       "final_scores": {"red_win": 10, "red_total": 30, "blue_total": 20},
                       "seats": [{"seat": 1, "faction": 0, "policy": sp.CANDIDATE_ID, "contract_errors": 0,
                                  "replay_mismatches": 0, "actions_by_type": {"1": 5}},
                                 {"seat": 11, "faction": 1, "policy": INERT_ID, "contract_errors": 0,
                                  "replay_mismatches": 0}]}
        self.t9 = {"steps": 3, "seats": {"0": {"moves": {"emitted": 5}}}}
        self.explore = {"steps": 3, "addon_errors": []}
        self.timeline = {"steps": [{}, {}, {}], "reconstructed_decisions": 3, "consistency_errors": []}

    def stops(self, **changes):
        args = dict(entry=self.entry, record=self.record, t9cap=self.t9, explore=self.explore, timeline=self.timeline,
                    max_step=2880, capture_digests={"t9.json": ("a", "a")})
        args.update(changes)
        return sp.game_stops(**args)

    def test_a_clean_game_has_no_stop(self) -> None:
        self.assertEqual(self.stops(), {})

    def test_each_defect_maps_to_its_code(self) -> None:
        def record(**kw):
            return {**self.record, **kw}
        seats = json.loads(json.dumps(self.record["seats"]))
        seats[0]["replay_mismatches"] = 1
        swapped = json.loads(json.dumps(self.record["seats"]))
        swapped[0]["faction"], swapped[1]["faction"] = 1, 0
        cases = [
            ({"record": record(session_close={"integrity": {"ok": False}})}, "S1"),
            ({"record": record(status="FAILED")}, "S4"),
            ({"record": record(final_scores={"red_win": 11, "red_total": 30, "blue_total": 20})}, "S4"),
            ({"record": record(seats=seats)}, "S6"),
            ({"record": record(seats=swapped)}, "S7"),
            ({"record": record(condition="C3")}, "S7"),
            ({"record": record(harness={**self.record["harness"], "policy_source_sha256": "0" * 64})}, "S7"),
            ({"record": record(observer_errors=["x"])}, "S7"),
            ({"capture_digests": {"t9.json": ("a", "b")}}, "S7"),
            ({"timeline": {**self.timeline, "consistency_errors": [{"k": 1}]}}, "S7"),
            ({"timeline": {**self.timeline, "reconstructed_decisions": 2}}, "S7"),
            ({"t9cap": {"steps": 3, "seats": {"0": {"moves": {"emitted": 4}}}}}, "S7"),
            ({"explore": {"steps": 3, "addon_errors": [{"k": 2}]}}, "S7"),
            ({"explore": {"steps": 2, "addon_errors": []}}, "S7"),
            ({"max_step": 40}, "S7"),
        ]
        for change, code in cases:
            found = self.stops(**change)
            self.assertIn(code, found, change)


class PrefixTest(unittest.TestCase):
    def reference(self) -> Dict[str, Any]:
        return {"divergence": 3, "v3_actions": ["a0", "a1", "a2", "v3"], "expected_actions": "x3",
                "memory_in": ["m0", "m1", "m2", "m3", "m4"], "changed": [100, 400],
                "redirects": {"100": [39, [1, 2]], "400": [39, [1, 3]]}}

    def check(self, actions=None, memory=None, changed=None, redirects=None):
        ref = self.reference()
        return sp.prefix_problems(ref, actions or ["a0", "a1", "a2", "x3", "z"], memory or ref["memory_in"],
                                  [100, 400] if changed is None else changed,
                                  {100: [39, [1, 2]], 400: [39, [1, 3]]} if redirects is None else redirects)

    def test_the_registered_prefix_passes(self) -> None:
        self.assertEqual(self.check(), [])

    def test_every_clause_fails_alone(self) -> None:
        self.assertTrue(self.check(actions=["a0", "b1", "a2", "x3"])[0].startswith("the candidate's actions differ"))
        self.assertTrue(self.check(actions=["b0", "a1", "a2", "x3"])[0].endswith("(first at 0)"))
        self.assertEqual(self.check(actions=["a0", "a1", "a2", "v3"]), ["no divergence at decision 3"])
        self.assertEqual(self.check(actions=["a0", "a1", "a2", "y3"]),
                         ["the divergence at decision 3 is not the registered first-divergence decision"])
        self.assertEqual(len(self.check(memory=["m0", "m1", "m2", "m3", "other"])), 1)
        self.assertEqual(len(self.check(memory=["other", "m1", "m2", "m3", "m4"])), 1)
        self.assertEqual(len(self.check(changed=[100])), 1)
        self.assertEqual(len(self.check(redirects={100: [39, [1, 2]], 400: [39, [1, 4]]})), 1)
        self.assertEqual(len(self.check(redirects={100: [38, [1, 2]], 400: [39, [1, 3]]})), 1)
        self.assertEqual(self.check(actions=["a0", "a1"]), ["the game ended before decision 4"])

    def test_digests_are_canonical(self) -> None:
        a = [{"type": 1, "obj_id": 7, "move_path": (1, 2)}]
        b = [{"move_path": [1, 2], "obj_id": 7, "type": 1}]
        self.assertEqual(sp.actions_digest(a), sp.actions_digest(b))
        self.assertNotEqual(sp.actions_digest(a), sp.actions_digest(list(reversed(a + b[:0] + [{"type": 2}]))))
        self.assertEqual(sp.memory_digest(((1, 2),)), sp.memory_digest([[1, 2]]))
        self.assertNotEqual(sp.memory_digest(()), sp.memory_digest(((1, 2),)))


class FireTest(unittest.TestCase):
    UNIT = 4600

    def endpoint(self, k=611, listed=(1, 2), orders=None):
        if orders is None:
            orders = [({"type": 2, "obj_id": self.UNIT, "target_obj_id": 5}, "accepted")]
        return sp.fire_endpoint(k, self.UNIT, listed, orders)

    def test_listed_emitted_accepted(self) -> None:
        self.assertTrue(self.endpoint()["preserved"])
        self.assertEqual(self.endpoint(listed=(1,))["listed"], False)
        self.assertFalse(self.endpoint(listed=(1,))["preserved"])
        self.assertFalse(self.endpoint(listed=())["preserved"])
        self.assertFalse(self.endpoint(orders=[])["emitted"])
        self.assertFalse(self.endpoint(orders=[({"type": 2, "obj_id": self.UNIT}, "516")])["accepted"])
        other = self.endpoint(orders=[({"type": 2, "obj_id": 1, "target_obj_id": 5}, "accepted")])
        self.assertFalse(other["emitted"] or other["preserved"])  # another unit's shot never counts
        move = self.endpoint(orders=[({"type": 1, "obj_id": self.UNIT}, "accepted")])
        self.assertFalse(move["preserved"])

    def test_c2_classification_needs_both_exact_decisions(self) -> None:
        good = {611: self.endpoint(611), 686: self.endpoint(686)}
        self.assertEqual(sp.classify_c2(good)["class"], "C2_MECHANISM_PRESERVED")
        for k in (611, 686):
            for change in ({"listed": (1,)}, {"orders": []}, {"orders": [({"type": 2, "obj_id": self.UNIT}, "516")]}):
                lost = dict(good)
                lost[k] = self.endpoint(k, **change)
                found = sp.classify_c2(lost)
                self.assertEqual((found["class"], found["retired"]), ("C2_FIRE_MECHANISM_LOST", True))
                self.assertTrue(found["reasons"][0].startswith(f"decision {k}"))
        with self.assertRaises(ValueError):
            sp.classify_c2({611: self.endpoint(611), 687: self.endpoint(687)})  # a later shot never substitutes


class OwnershipAndBlockTest(unittest.TestCase):
    def test_first_ownership(self) -> None:
        flags = [{5: None}, {5: 1}, {5: 0}, {5: 1}]
        self.assertEqual(sp.first_ownership(flags, 5, 1), 1)
        self.assertEqual(sp.first_ownership(flags, 5, 0), 2)
        self.assertIsNone(sp.first_ownership(flags, 6, 0))

    def test_forms(self) -> None:
        self.assertEqual(sp.form((1, 2, 3), (1, 2, 3), False), "KEEP")
        self.assertEqual(sp.form((1, 2, 3), (1, 2), False), "STAGE")
        self.assertEqual(sp.form((1, 2, 3), None, False), "WITHHOLD")
        self.assertEqual(sp.form((1, 2, 3), (1, 4), True), "REDIRECT")

    def claimant(self, unit, ff, feasible=True, form="STAGE"):
        return {"unit": unit, "feasible": feasible, "key": [not feasible, False, ff, 1.0, 3, unit], "form": form}

    def test_positive_case(self) -> None:
        rows = sp.early_place_rows([self.claimant(7, 100)], counted=4, early_counted=2, selected=[])
        self.assertEqual([(r["unit"], r["early_place_block"], r["placed_without_early_places"]) for r in rows],
                         [(7, True, True)])

    def test_negative_cases(self) -> None:
        # full, but none of the places is an early one
        self.assertFalse(sp.early_place_rows([self.claimant(7, 100)], 4, 0, [])[0]["early_place_block"])
        # early places counted, but room is left: the claimant is placed
        rows = sp.early_place_rows([self.claimant(7, 100, form="KEEP")], 2, 2, [7])
        self.assertEqual((rows[0]["placed"], rows[0]["early_place_block"]), (True, False))
        # a claimant that cannot arrive is never selectable, so never blocked
        self.assertFalse(sp.early_place_rows([self.claimant(7, 100, feasible=False)], 4, 2, [])[0]["early_place_block"])

    def test_only_the_early_places_are_removed(self) -> None:
        claimants = [self.claimant(7, 100), self.claimant(8, 120), self.claimant(9, 140)]
        rows = {r["unit"]: r for r in sp.early_place_rows(claimants, counted=4, early_counted=1, selected=[])}
        self.assertEqual([rows[u]["early_place_block"] for u in (7, 8, 9)], [True, False, False])
        rows = {r["unit"]: r for r in sp.early_place_rows(claimants, counted=4, early_counted=2, selected=[])}
        self.assertEqual([rows[u]["early_place_block"] for u in (7, 8, 9)], [True, True, False])
        rows = {r["unit"]: r for r in sp.early_place_rows(claimants, counted=3, early_counted=2, selected=[7])}
        self.assertEqual([rows[u]["early_place_block"] for u in (7, 8, 9)], [False, True, True])
        self.assertEqual([rows[u]["rank"] for u in (7, 8, 9)], [1, 2, 3])

    def test_the_audit_refuses_when_it_does_not_describe_the_candidate(self) -> None:
        with self.assertRaises(ValueError):
            sp.early_place_rows([self.claimant(7, 100), self.claimant(8, 90)], 3, 0, [7])  # 8 ranks first
        with self.assertRaises(ValueError):
            sp.early_place_rows([self.claimant(7, 100)], 1, 2, [])

    def test_212_retirement_boundaries(self) -> None:
        self.assertEqual(sp.classify_212(564, 0)["class"], "C3_212_MECHANISM_PRESERVED")
        self.assertEqual(sp.classify_212(300, 0)["class"], "C3_212_MECHANISM_PRESERVED")
        for first, blocks in ((565, 0), (None, 0), (564, 1), (565, 2)):
            found = sp.classify_212(first, blocks)
            self.assertEqual((found["class"], found["retired"]), ("C3_212_MECHANISM_LOST", True), (first, blocks))
        self.assertEqual(len(sp.classify_212(600, 3)["reasons"]), 2)


class DispositionTest(unittest.TestCase):
    def test_order(self) -> None:
        good2, bad2 = {"class": sp.C2_CLASSES[0]}, {"class": sp.C2_CLASSES[1]}
        good3, bad3 = {"class": sp.C212_CLASSES[0]}, {"class": sp.C212_CLASSES[1]}
        self.assertEqual(sp.disposition(["x"], bad2, bad3)["disposition"], "CAPTURE_INVALID")
        self.assertEqual(sp.disposition([], good2, None)["disposition"], "CAPTURE_INVALID")
        self.assertEqual(sp.disposition([], bad2, bad3)["disposition"], "MECHANISM_REFUTED_BOTH")
        self.assertEqual(sp.disposition([], bad2, good3)["disposition"], "MECHANISM_REFUTED_C2")
        self.assertEqual(sp.disposition([], good2, bad3)["disposition"], "MECHANISM_REFUTED_212")
        self.assertEqual(sp.disposition([], good2, good3)["disposition"], "MECHANISM_CROSSED_WITHOUT_KNOWN_REGRESSION")
        with self.assertRaises(ValueError):
            sp.disposition([], {"class": "OTHER"}, good3)

    def test_public_guards(self) -> None:
        self.assertTrue(sp.public_check({"unit": 3}))
        self.assertTrue(sp.public_check({"label": "x", "n": 3837}, {3837}))
        self.assertEqual(sp.public_check({"label": "80-point objective A", "n": 2}, {3837}), [])
        self.assertTrue(sp.forbidden_identity("... t9-batch-capacity-v3 ..."))
        self.assertTrue(sp.forbidden_identity("9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8"))
        self.assertFalse(sp.forbidden_identity(sp.CANDIDATE_ID))


class ObserverTest(unittest.TestCase):
    setUp = t15.DelayedTest.setUp
    staged_scene_start = t15.DelayedTest.staged_scene_start
    staged_scene_arrived = t15.DelayedTest.staged_scene_arrived

    def decisions(self) -> List[Dict[str, Any]]:
        agent = c6.PostStageAnyV6Agent()
        agent.setup({"seat": SEAT, "faction": RED, "cost_data": syn.cost_data()})
        out = []
        for obs in (self.staged_scene_start(), self.staged_scene_arrived(), self.staged_scene_arrived()):
            raw = dict(obs.fields)
            memory = agent.memory
            actions = agent.step(raw)
            out.append({"observation": raw, "memory": memory, "trace": agent.last_trace,
                        "submitted": [dict(a) for a in actions], "seat": SEAT, "faction": RED,
                        "policy": sp.CANDIDATE_ID})
        return out

    def test_reconstruction_and_memory_chain_agree_with_the_live_agent(self) -> None:
        expected = (Memory(), ())
        kinds = []
        for decision in self.decisions():
            rebuilt = cap.reconstruct(decision["observation"], SEAT, RED, decision["memory"], self.costs)
            checks = cap.consistency(decision, rebuilt, expected)
            self.assertTrue(all(checks.values()), checks)
            expected = (rebuilt["baseline_memory_out"], rebuilt["memory_out"])
            kinds.append(sorted(rebuilt["candidate"]["redirected"]))
        self.assertEqual(kinds, [[], [str(t15.X)], []])

    def test_tampering_is_detected(self) -> None:
        decisions = self.decisions()
        first, second = decisions[0], decisions[1]
        rebuilt = cap.reconstruct(second["observation"], SEAT, RED, second["memory"], self.costs)
        previous = cap.reconstruct(first["observation"], SEAT, RED, first["memory"], self.costs)
        expected = (previous["baseline_memory_out"], previous["memory_out"])
        self.assertTrue(all(cap.consistency(second, rebuilt, expected).values()))
        wrong_memory = dict(second, memory=ea.AddonMemory(second["memory"].baseline, ()))
        self.assertFalse(cap.consistency(wrong_memory, rebuilt, expected)["addon_memory"])
        self.assertFalse(cap.consistency(second, rebuilt, (expected[0], ()))["addon_memory"])
        self.assertFalse(cap.consistency(dict(second, submitted=[]), rebuilt, expected)["actions"])
        # the first decision of a game must start from empty memory
        self.assertFalse(cap.consistency(second, rebuilt, (Memory(), ()))["addon_memory"])

    def test_prefix_inputs_and_changed_units(self) -> None:
        a = [{"type": 1, "obj_id": 5, "move_path": [1, 2]}, {"type": 2, "obj_id": 6}]
        b = [{"type": 1, "obj_id": 5, "move_path": [1, 3]}, {"type": 2, "obj_id": 6}, {"type": 1, "obj_id": 7}]
        self.assertEqual(cap.changed_units(a, b), [5, 7])
        import pickle
        timeline = {"steps": [{"submitted": [{"seat": 1, "action": a[1]}, {"seat": 11, "action": {"type": 9}}]},
                              {"submitted": [{"seat": 1, "action": b[0]}],
                               "s17": {"1": {"v3_actions": [a[0]],
                                             "candidate": {"redirected": {"5": {"objective": 9, "path": [1, 3]}}}}}}]}
        windows = {"samples": [{"k": k, "seats": {1: {"memory": pickle.dumps(ea.AddonMemory(Memory(), m))}}}
                               for k, m in ((1, ((80, 1),)), (0, ()))]}
        live = cap.prefix_inputs(timeline, windows, 1, 1)
        self.assertEqual(live["actions"], [sp.actions_digest([a[1]]), sp.actions_digest([b[0]])])
        self.assertEqual(live["memory"], [sp.memory_digest(()), sp.memory_digest(((80, 1),))])
        self.assertEqual((live["changed"], live["redirects"]), ([5], {"5": [9, [1, 3]]}))


class AnalysisHelpersTest(unittest.TestCase):
    """The analysis driver's pure helpers and the registered audit window (server-only paths are exercised by the
    rehearsals and tests/test_real_s17.py)."""

    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("s17_analysis_test", ROOT / "scripts" / "s17_analysis.py")
        cls.analysis = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.analysis)
        cls.source = (ROOT / "scripts" / "s17_analysis.py").read_text(encoding="utf-8")

    def row(self, k, unit, block, placed=False, feasible=True, form="WITHHOLD"):
        return {"k": k, "unit": unit, "early_place_block": block, "placed": placed, "feasible": feasible, "form": form,
                "early_places": 2 if block else 0, "redirect_place_block": block}

    def test_audit_summary_counts_blocks_not_placements(self) -> None:
        rows = [self.row(400, 1, False, placed=True, form="KEEP"), self.row(401, 2, True),
                self.row(401, 3, False, feasible=False), self.row(402, 2, True, form="STAGE")]
        summary = self.analysis.audit_summary(rows)
        self.assertEqual((summary["early_place_blocks"], summary["early_place_block_decisions"],
                          summary["claim_decisions"], summary["claimant_decisions"], summary["claimants"],
                          summary["placed"], summary["selectable_not_placed"], summary["first_claim_decision"]),
                         (2, [401, 402], 3, 4, 3, 1, 2, 400))
        self.assertEqual(summary["early_place_block_forms"], {"STAGE": 1, "WITHHOLD": 1})

    def test_classification_dispatch(self) -> None:
        facts = {"first_own_problem_decision": 564}
        self.assertEqual(self.analysis.classify(sp.C212, facts, {"audit": []})["class"], sp.C212_CLASSES[0])
        self.assertEqual(self.analysis.classify(sp.C212, facts, {"audit": [self.row(500, 1, True)]})["class"],
                         sp.C212_CLASSES[1])
        endpoint = sp.fire_endpoint(611, 9, (2,), [({"type": 2, "obj_id": 9}, "accepted")])
        lost = sp.fire_endpoint(686, 9, (2,), [])
        self.assertEqual(self.analysis.classify(sp.C2, {}, {"fire_endpoints": {611: endpoint, 686: lost}})["class"],
                         sp.C2_CLASSES[1])

    def test_public_texts_refuse_the_stage_one_identity_and_private_values(self) -> None:
        results = [({}, {"names": {"3837": "50-point objective A"}, "redirects": []})]
        self.assertIn("games", self.analysis.public_texts({"games": {"label": "x"}}, results))
        with self.assertRaises(SystemExit):
            self.analysis.public_texts({"games": {"label": "t9-batch-capacity-v3"}}, results)
        with self.assertRaises(SystemExit):
            self.analysis.public_texts({"games": {"n": 3837}}, results)

    def test_registered_audit_window_and_fresh_memory_per_stream(self) -> None:
        self.assertEqual(self.source.count(
            'if problem is not None and k >= ref["divergence"] and (first_own is None or k < first_own):'), 1)
        tree = __import__("ast").parse(self.source)
        analyze = next(n for n in __import__("ast").walk(tree) if getattr(n, "name", None) == "analyze_game")
        text = __import__("ast").unparse(analyze)
        self.assertIn("memory: Tuple[Tuple[int, int], ...] = ()", text)
        self.assertIn("alloc = c6.allocate(observation, seat, faction, base.actions, policy_v2.router, before)", text)


if __name__ == "__main__":
    unittest.main()
