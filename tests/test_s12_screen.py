"""The frozen rules, stage cards, decisions, disposition, ledger audit and public sanitization of the Sprint 12
screen (``evaluation/s12_screen.py``). Synthetic facts only; no engine, no private data."""

from __future__ import annotations

import copy
import importlib.util
import itertools
import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402

DRAFT = json.loads((ROOT / "evaluation" / "s12-batch-allocator-draft" / "draft.json").read_text(encoding="utf-8"))


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def primary_game(cell: str, margin: float, coverage: float = 1.0, **extra):
    return {"game_id": f"g-{cell}-{margin}-{coverage}", "scenario_id": sc.PRIMARY_SCENARIO, "condition": cell,
            "margin": margin, "coverage": coverage, **extra}


def adverse_game(config: str, margin=600, attack=100, occupy=310, last=100, **extra):
    scenario, condition = config.split()
    return {"game_id": f"g-{config}-{margin}-{attack}", "scenario_id": scenario, "condition": condition,
            "margin": margin, "attack": attack, "occupy": occupy, "fifth_objective_last_to_own_step": last, **extra}


GOOD_H1 = dict(margin=-700, coverage=1.2)
GOOD_H2 = dict(margin=1100)


class RulesAreTheDraftsTest(unittest.TestCase):
    def test_primary_values_equal_the_approved_draft(self) -> None:
        values = DRAFT["primary"]["rule_values"]
        for key in ("h1_coverage_floor", "h2_margin_floor", "h1_collapse_below", "h2_collapse_below",
                    "preserved_seat_average_at_least"):
            self.assertEqual(sc.RULES[key], values[key], key)

    def test_adverse_values_equal_the_approved_draft(self) -> None:
        for config, row in DRAFT["adverse"].items():
            for key, value in row["thresholds"].items():
                self.assertEqual(sc.RULES["adverse"][config][key], value, (config, key))
            self.assertEqual(sc.RULES["adverse"][config]["side"], row["candidate_side"])
        self.assertEqual(sorted(sc.RULES["adverse"]), sorted(DRAFT["adverse"]))

    def test_declared_constants_equal_the_draft(self) -> None:
        constants = DRAFT["declared_constants"]
        self.assertEqual(sc.RULES["max_step"], constants["max_step"])
        self.assertEqual(sc.RULES["late_capture_window_steps"], constants["infantry_hex_steps"])
        self.assertEqual(sc.RULES["staging_wait_flag_steps"], constants["infantry_hex_steps"])
        self.assertEqual(sc.RULES["long_hold_flag_decisions"], constants["half_play_stage"])

    def test_identities_and_budget_are_the_approved_ones(self) -> None:
        self.assertEqual(sc.V3_DIGEST, DRAFT["candidate"]["policy_source_sha256"])
        self.assertEqual(sc.V2_DIGEST, DRAFT["baseline"]["policy_source_sha256"])
        self.assertEqual((sc.LEDGER_BASE_SESSION, sc.SESSION_CEILING), (2786, 12))
        draft = DRAFT["schedule"]["stages"]
        for stage in draft:
            mine = sc.SCHEDULE[stage["stage"]]
            self.assertEqual([(g["position"], g["scenario_id"], g["condition"], g["red"], g["blue"])
                              for g in stage["games"]], [tuple(row) for row in mine])
        self.assertEqual(sum(len(v) for v in sc.SCHEDULE.values()), 12)
        self.assertEqual(sum(len(sc.SCHEDULE[s]) for s in ("P1", "P2", "A1")), 9)

    def test_classifications_equal_the_draft_scripts(self) -> None:
        draft = load_script("t9_batch_screen_draft")
        floors = {k: sc.RULES[k] for k in ("h1_coverage_floor", "h2_margin_floor", "h1_collapse_below",
                                            "h2_collapse_below")}
        rng = random.Random(12)
        for _ in range(3000):
            h1 = [{"margin": rng.choice([-1300, -1195, -1194, -900, -700, 900]),
                   "coverage": rng.choice([0.3, 0.6184027777777777, 0.62, 2.0]), "condition": "H1"}
                  for _ in range(3)]
            h2 = [{"margin": rng.choice([100, 217, 216, 864, 865, 1200]), "coverage": 5.0, "condition": "H2"}
                  for _ in range(3)]
            games = h1 + h2
            self.assertEqual(sc.interim_stop(h1[:2] + h2[:2]), draft.interim_stop(h1[:2], h2[:2], floors))
            self.assertEqual(sc.primary_class(games), draft.final_class(h1, h2, floors, 130.5))
        limits = {key: draft.adverse_thresholds(key, [{"margin": row["thresholds"].get("margin_at_least", 0),
                                                        "attack": row["thresholds"].get("attack_at_least", 0)}],
                                                [{"attack": row["thresholds"].get("attack_at_most_regressed", 0)}])
                  for key, row in DRAFT["adverse"].items()}
        for key in limits:
            for margin, attack, occupy in itertools.product((400, 558, 559, 700), (0, 1, 15, 16, 61, 62, 77, 78),
                                                            (230, 310)):
                game = {"margin": margin, "attack": attack, "occupy": occupy}
                self.assertEqual(sc.adverse_class(key, game), draft.classify_adverse(key, game, limits[key]),
                                 (key, game))

    def test_the_interim_stop_never_changes_the_final_classification(self) -> None:
        cells = [(-1300, 0.3), (-700, 0.3), (-700, 1.0)]
        blues = [100, 800, 1100]
        for h1 in itertools.product(cells, repeat=3):
            for h2 in itertools.product(blues, repeat=3):
                games = ([primary_game("H1", m, c) for m, c in h1] + [primary_game("H2", m) for m in h2])
                early = [games[0], games[1], games[3], games[4]]
                if sc.interim_stop(early):
                    self.assertEqual(sc.primary_class(games), "NOT_PRESERVED")


class DecisionTest(unittest.TestCase):
    def p1(self, h1, h2):
        return [primary_game("H1", **h1[0]), primary_game("H2", **h2[0]), primary_game("H1", **h1[1]),
                primary_game("H2", **h2[1])]

    def test_p1_outcomes(self) -> None:
        good = self.p1([GOOD_H1, GOOD_H1], [GOOD_H2, GOOD_H2])
        decision = sc.decide("P1", good, expected=4)
        self.assertEqual((decision["decision"], decision["permits"]), ("CONTINUE", sc.CARD_IDS["P2"]))
        like = self.p1([dict(margin=-700, coverage=0.5)] * 2, [dict(margin=800)] * 2)
        self.assertEqual(sc.decide("P1", like, expected=4)["decision"], "STOP")
        three = self.p1([dict(margin=-700, coverage=0.5), GOOD_H1], [dict(margin=800)] * 2)
        self.assertEqual(sc.decide("P1", three, expected=4)["decision"], "CONTINUE")
        collapses = self.p1([dict(margin=-1300, coverage=1.0)] * 2, [GOOD_H2, GOOD_H2])
        self.assertEqual(sc.decide("P1", collapses, expected=4)["kind"], "tactical")
        one = self.p1([dict(margin=-1300, coverage=1.0), GOOD_H1], [GOOD_H2, GOOD_H2])
        self.assertEqual(sc.decide("P1", one, expected=4)["decision"], "CONTINUE")
        self.assertEqual(sc.decide("P1", good[:3], expected=4)["kind"], "incomplete")

    def test_p2_outcomes_and_a_changed_threshold(self) -> None:
        earlier = self.p1([GOOD_H1, GOOD_H1], [GOOD_H2, GOOD_H2])
        decision = sc.decide("P2", [primary_game("H1", **GOOD_H1), primary_game("H2", **GOOD_H2)], expected=2,
                             earlier=earlier)
        self.assertEqual((decision["primary_class"], decision["permits"]), ("PRESERVED_DIRECTIONALLY", sc.CARD_IDS["A1"]))
        low = [primary_game("H1", margin=-1000, coverage=1.0), primary_game("H2", margin=900)]
        mixed = sc.decide("P2", low, expected=2, earlier=self.p1([dict(margin=-1000, coverage=1.0)] * 2,
                                                                  [dict(margin=900)] * 2))
        self.assertEqual(mixed["primary_class"], "AMBIGUOUS")
        self.assertEqual(mixed["decision"], "CONTINUE")
        bad = sc.decide("P2", [primary_game("H1", margin=-700, coverage=0.5), primary_game("H2", margin=800)],
                        expected=2, earlier=self.p1([dict(margin=-700, coverage=0.5), GOOD_H1],
                                                    [dict(margin=800), GOOD_H2]))
        self.assertEqual((bad["primary_class"], bad["decision"], bad["kind"]), ("NOT_PRESERVED", "STOP", "tactical"))
        rules = copy.deepcopy(sc.RULES)
        rules["h2_margin_floor"] = 1200
        games = earlier + [primary_game("H1", **GOOD_H1), primary_game("H2", **GOOD_H2)]
        self.assertEqual(sc.primary_class(games), "PRESERVED_DIRECTIONALLY")
        self.assertEqual(sc.primary_class(games, rules), "AMBIGUOUS")

    def test_the_preserved_seat_average_boundary(self) -> None:
        h1 = [primary_game("H1", margin=-739, coverage=1.0) for _ in range(3)]
        h2 = [primary_game("H2", margin=1000) for _ in range(3)]
        self.assertEqual(sc.primary_counts(h1 + h2)["seat_average"], 130.5)
        self.assertEqual(sc.primary_class(h1 + h2), "PRESERVED_DIRECTIONALLY")
        h2[0]["margin"] = 999
        self.assertEqual(sc.primary_class(h1 + h2), "AMBIGUOUS")

    def test_a1_triggers_and_the_late_capture_boundary(self) -> None:
        games = [adverse_game("2120531121 C3", margin=590, attack=103, last=2736),
                 adverse_game("1930331196 C2", margin=274, attack=24), adverse_game("1930331196 C3", margin=570,
                                                                                    attack=88)]
        decision = sc.decide("A1", games, expected=3)
        self.assertEqual((decision["decision"], decision["replicate"]), ("COMPLETE", []))
        games[0]["fifth_objective_last_to_own_step"] = 2737
        decision = sc.decide("A1", games, expected=3)
        self.assertEqual((decision["decision"], decision["permits"], decision["replicate"]),
                         ("CONTINUE", sc.CARD_IDS["A2"], ["2120531121 C3"]))
        games[0]["fifth_objective_last_to_own_step"] = 100
        games[2]["attack"] = 70
        games[1]["attack"] = 0
        decision = sc.decide("A1", games, expected=3)
        self.assertEqual(decision["replicate"], ["1930331196 C2", "1930331196 C3"])
        self.assertEqual(decision["adverse"]["1930331196 C3"]["class"], "AMBIGUOUS")
        self.assertEqual(decision["adverse"]["1930331196 C2"]["class"], "REGRESSED")

    def test_any_stop_code_stops_the_stage(self) -> None:
        for code in sc.STOP_CODES:
            game = primary_game("H1", **GOOD_H1, stops={code: ["planted"]})
            decision = sc.decide("P1", [game] + self.p1([GOOD_H1, GOOD_H1], [GOOD_H2, GOOD_H2])[1:], expected=4)
            self.assertEqual((decision["decision"], decision["kind"]), ("STOP", "immediate"), code)
            self.assertEqual(decision["stops"][0]["code"], code)
        ledger = sc.decide("P1", self.p1([GOOD_H1, GOOD_H1], [GOOD_H2, GOOD_H2]), expected=4,
                           stage_level={"S2": ["planted"]})
        self.assertEqual(ledger["stops"][0]["code"], "S2")


class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_script("build_s12_card")
        cls.shoot = json.loads((ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" /
                                "manifest.json").read_text(encoding="utf-8"))
        cls.policies = [{"id": sc.V2_ID, "label": "v2", "policy_source": cls.builder.policy_source(cls.builder.V2_SOURCES)},
                        {"id": sc.V3_ID, "label": "v3", "policy_source": cls.builder.policy_source(cls.builder.V3_SOURCES)}]
        cls.frozen = sc.frozen_digests(ROOT)

    def build(self, stage, reports):
        digests = {s: f"digest-{s}" for s in reports}
        return sc.build_card(stage, self.shoot, mf.digest(self.shoot), self.policies, self.frozen, reports, digests)

    def report(self, stage, **decision):
        return {"decision": {"decision": "CONTINUE", **decision}}

    def test_p1_card(self) -> None:
        card = self.build("P1", {})
        self.assertEqual([g["condition"] for g in card["games"]], ["H1", "H2", "H1", "H2"])
        self.assertEqual([g["screen_position"] for g in card["games"]], [1, 2, 3, 4])
        self.assertEqual(card["budget"], {"batch_sessions": 4, "ledger_base_session": 2786, "sprint_session_cap": 12})
        self.assertEqual(card["screen"]["rules"], sc.RULES)
        self.assertIsNone(card["screen"]["prerequisite"])
        self.assertEqual(card["policies"][sc.V3_ID]["policy_source"]["sha256"], sc.V3_DIGEST)
        self.assertFalse(card["eligible_for_promotion"])
        self.assertEqual(sc.card_problems(card, ROOT), [])

    def test_later_cards_follow_only_from_permitting_reports(self) -> None:
        with self.assertRaises(sc.NotPermitted):
            self.build("P2", {})
        with self.assertRaises(sc.NotPermitted):
            self.build("P2", {"P1": {"decision": {"decision": "STOP", "permits": None}}})
        with self.assertRaises(sc.NotPermitted):
            self.build("P2", {"P1": self.report("P1", permits=sc.CARD_IDS["A1"])})
        p2 = self.build("P2", {"P1": self.report("P1", permits=sc.CARD_IDS["P2"])})
        self.assertEqual([g["screen_position"] for g in p2["games"]], [5, 6])
        self.assertEqual(p2["screen"]["prerequisite"], {"stage": "P1", "report": sc.report_path("P1"),
                                                         "report_sha256": "digest-P1"})
        a1 = self.build("A1", {"P2": self.report("P2", permits=sc.CARD_IDS["A1"])})
        self.assertEqual([(g["scenario_id"], g["condition"]) for g in a1["games"]], list(sc.ADVERSE))
        with self.assertRaises(sc.NotPermitted):
            self.build("A2", {"A1": {"decision": {"decision": "COMPLETE", "permits": None, "replicate": []}}})
        a2 = self.build("A2", {"A1": self.report("A1", permits=sc.CARD_IDS["A2"],
                                                 replicate=["1930331196 C3", "2120531121 C3"])})
        self.assertEqual([g["screen_position"] for g in a2["games"]], [10, 12])
        self.assertEqual(a2["budget"]["batch_sessions"], 2)
        self.assertEqual(a2["screen"]["replicated_configurations"], ["1930331196 C3", "2120531121 C3"])

    def test_the_decision_mechanically_determines_the_next_card(self) -> None:
        a1_games = [adverse_game("2120531121 C3", margin=590), adverse_game("1930331196 C2", margin=274, attack=24),
                    adverse_game("1930331196 C3", margin=570, attack=88)]
        a1_games[2]["attack"] = 70
        decision = sc.decide("A1", a1_games, expected=3)
        card = self.build("A2", {"A1": {"decision": decision}})
        self.assertEqual([g["game_id"] for g in card["games"]],
                         [sc.game_id("A2", 12, "1930331196", "C3")])

    def test_card_problems_catch_tampering(self) -> None:
        card = self.build("P1", {})
        tampered = copy.deepcopy(card)
        tampered["screen"]["frozen_files"]["src/miaosuan_agent/evaluation/s12_screen.py"] = "0" * 64
        self.assertTrue(any("frozen" in p for p in sc.card_problems(tampered, ROOT)))
        tampered = copy.deepcopy(card)
        tampered["screen"]["rules"]["h2_margin_floor"] = 800
        self.assertTrue(any("rules" in p for p in sc.card_problems(tampered, ROOT)))
        tampered = copy.deepcopy(card)
        tampered["budget"]["sprint_session_cap"] = 13
        self.assertTrue(any("budget" in p for p in sc.card_problems(tampered, ROOT)))
        tampered = copy.deepcopy(card)
        tampered["policies"][sc.V3_ID]["policy_source"]["sha256"] = "0" * 64
        self.assertTrue(any("identities" in p for p in sc.card_problems(tampered, ROOT)))

    def test_frozen_files_exist(self) -> None:
        for rel in sc.FROZEN_FILES:
            self.assertTrue((ROOT / rel).is_file(), rel)


class DispositionTest(unittest.TestCase):
    def reports(self, primary="PRESERVED_DIRECTIONALLY", a1=("REPAIRED", "AVOIDED", "AVOIDED"), a2=None,
                attributed=True, blocks=0):
        games = [{"scenario_id": "2120531121", "condition": "C3", "fifth_objective_attributed_to_v3_selection":
                  attributed, "staging_blocks_to_end": blocks}]
        rows = {sc.config_key(*cfg): {"class": cls} for cfg, cls in zip(sc.ADVERSE, a1)}
        out = {"P1": {"decision": {"decision": "CONTINUE", "stops": []}, "games": []},
               "P2": {"decision": {"decision": "CONTINUE", "stops": [], "primary_class": primary}, "games": []},
               "A1": {"decision": {"decision": "CONTINUE" if a2 else "COMPLETE", "stops": [], "adverse": rows},
                      "games": games}}
        if a2:
            out["A2"] = {"decision": {"decision": "COMPLETE", "stops": [], "adverse": a2}, "games": []}
        return out

    def test_every_row(self) -> None:
        self.assertEqual(sc.disposition(self.reports())["disposition"], "READY_FOR_CONFIRMATORY_PROPOSAL")
        self.assertEqual(sc.disposition(self.reports("AMBIGUOUS"))["disposition"], "PROMISING_PRIMARY_UNRESOLVED")
        self.assertEqual(sc.disposition(self.reports(attributed=False))["disposition"], "NEEDS_REVISION")
        self.assertEqual(sc.disposition(self.reports(blocks=1))["disposition"], "NEEDS_REVISION")
        mixed = self.reports(a1=("REPAIRED", "AVOIDED", "AMBIGUOUS"), a2={"1930331196 C3": {"class": "AVOIDED"}})
        self.assertEqual(sc.disposition(mixed)["disposition"], "NEEDS_REVISION")
        self.assertEqual(sc.disposition(mixed)["adverse"]["1930331196 C3"], "MIXED")
        stopped = {"P1": {"decision": {"decision": "STOP", "kind": "tactical", "stops": []}}}
        self.assertEqual(sc.disposition(stopped)["disposition"], "NOT_PRESERVED_IN_PRIMARY")
        for code in sc.STOP_CODES:
            reports = {"P1": {"decision": {"decision": "STOP", "kind": "immediate",
                                           "stops": [{"code": code, "game": "g", "text": ""}]}}}
            # registered in docs/SPRINT12_V3_SCREEN.md; typed here so the test does not read the module's own set
            expected = ("STRUCTURAL_FAILURE" if code in {"S5", "S8", "S9", "S10", "S11", "S12", "S14"}
                        else "SCREEN_INCOMPLETE")
            self.assertEqual(sc.disposition(reports)["disposition"], expected, code)
            self.assertEqual(sc.disposition(reports, {code: "v3"})["disposition"], "STRUCTURAL_FAILURE", code)
        self.assertEqual(sc.disposition({"P1": {"decision": {"decision": "CONTINUE", "stops": []}}})["disposition"],
                         "IN_PROGRESS")


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.card = {"card_id": sc.CARD_IDS["P1"], "games": [{"game_id": g["game_id"]} for g in sc.stage_games("P1")]}
        self.digest = mf.digest(self.card)

    def rows(self, n=2, **changes):
        out = [{"session": "2786", "event": "session-close", "integrity": {"ok": True}, "state": "s"}]
        for k in range(n):
            session = str(2787 + k)
            out.append({"session": session, "event": "session-open", "state": "s",
                        "harness": {"game_id": self.card["games"][k % 4]["game_id"], "card": self.card["card_id"],
                                    "manifest_sha256": self.digest}})
            out.append({"session": session, "event": "session-close", "integrity": {"ok": True}, "state": "s"})
        return out

    def test_clean_ledger(self) -> None:
        audit = sc.ledger_audit(self.rows(), {self.card["card_id"]: self.card})
        self.assertTrue(audit["ok"], audit)
        self.assertEqual(audit["sessions"], 2)

    def test_exactly_the_ceiling_is_allowed(self) -> None:
        cards = {}
        for stage in sc.STAGE_ORDER:
            card = {"card_id": sc.CARD_IDS[stage], "games": [{"game_id": g["game_id"]} for g in sc.stage_games(stage)]}
            cards[card["card_id"]] = card
        rows = [{"session": "2786", "event": "session-close", "integrity": {"ok": True}, "state": "s"}]
        session = 2787
        for card in cards.values():
            for game in card["games"]:
                rows.append({"session": str(session), "event": "session-open", "state": "s",
                             "harness": {"game_id": game["game_id"], "card": card["card_id"],
                                         "manifest_sha256": mf.digest(card)}})
                rows.append({"session": str(session), "event": "session-close", "integrity": {"ok": True},
                             "state": "s"})
                session += 1
        audit = sc.ledger_audit(rows, cards)
        self.assertEqual((audit["sessions"], audit["ok"]), (12, True), audit["problems"])
        rows.append(dict(rows[-2], session=str(session)))
        rows.append(dict(rows[-2], session=str(session)))
        self.assertTrue(any("ceiling" in p for p in sc.ledger_audit(rows, cards)["problems"]["S2"]))

    def test_planted_problems(self) -> None:
        cards = {self.card["card_id"]: self.card}
        rows = self.rows()
        rows[1]["harness"]["game_id"] = "elsewhere"
        self.assertTrue(sc.ledger_audit(rows, cards)["problems"]["S2"])
        rows = self.rows()
        rows[2]["integrity"] = {"ok": False}
        self.assertTrue(sc.ledger_audit(rows, cards)["problems"]["S1"])
        rows = self.rows()
        rows[3]["state"] = "other"
        self.assertTrue(sc.ledger_audit(rows, cards)["problems"]["S1"])
        rows = self.rows()[:-1]
        self.assertTrue(sc.ledger_audit(rows, cards)["problems"]["S2"])
        rows = self.rows()
        rows[2]["event"] = "session-recovered"
        self.assertTrue(sc.ledger_audit(rows, cards)["problems"]["S2"])
        rows = self.rows()
        rows[1]["harness"]["manifest_sha256"] = "0" * 64
        self.assertTrue(sc.ledger_audit(rows, cards)["problems"]["S2"])
        rows = self.rows(n=13)
        self.assertTrue(any("ceiling" in p for p in sc.ledger_audit(rows, cards)["problems"]["S2"]))
        rows = self.rows(n=4)
        rows[5]["harness"]["game_id"] = rows[1]["harness"]["game_id"]
        self.assertTrue(any("twice" in p for p in sc.ledger_audit(rows, cards)["problems"]["S2"]))


class PrivacyTest(unittest.TestCase):
    def test_forbidden_keys_and_secrets(self) -> None:
        self.assertTrue(sc.privacy_problems({"a": {"obj_id": 1}}))
        self.assertTrue(sc.privacy_problems({"a": [{"cur_hex": 1}]}))
        self.assertTrue(sc.privacy_problems({"n": 930001}, secrets=[930001]))
        self.assertTrue(sc.privacy_problems({"s": "unit 930001 waited"}, secrets=[930001]))
        self.assertTrue(sc.privacy_problems({"930001": 1}, secrets=[930001]))
        self.assertEqual(sc.privacy_problems({"n": 4, "s": "four places"}, secrets=[930001]), [])

    def test_public_game_keeps_only_whitelisted_fields(self) -> None:
        facts = {"game_id": "g", "margin": 1, "places_private": [{"unit": 930001}], "holds_private": [], "x": 2}
        self.assertEqual(sc.public_game(facts), {"game_id": "g", "margin": 1})
        with self.assertRaises(ValueError):
            sc.public_game({"game_id": "g", "objectives": {"A": {"move_path": [1]}}})

    def test_report_refuses_private_content(self) -> None:
        with self.assertRaises(ValueError):
            sc.report("P1", [{"game_id": "g", "places": {"obj_id": 3}}], {"decision": "STOP"}, {})
        report = sc.report("P1", [{"game_id": "g", "margin": 3}], {"decision": "STOP"}, {"g": "d"})
        self.assertEqual(report["card"], sc.CARD_IDS["P1"])
        self.assertFalse(report["eligible_for_promotion"])


if __name__ == "__main__":
    unittest.main()
