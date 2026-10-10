"""The Sprint 33 mechanism-check rules (``evaluation/s33_pilot.py``), observer (``evaluation/s33_capture.py``) and runner
checks.

SYNTHETIC inputs throughout, except the committed card, controls and preflight they are bound to: ledgers, records,
timelines and a stand-in world (``tests/fixtures/s33_engine.py``) in which the inert control plays red and the candidate
blue through the real game loop with the real ``baseline-v2``. Pinned: the card, its schedule, positions, sessions,
budget and pins; the harm thresholds against Sprint 30's committed controls and the recorded opportunities against
Sprint 32's committed preflight; every ledger defect and the position prerequisite; the structural checks; the harm
boundaries; the gate; the disposition order and evidence level; the earlier-gate check of the runner; the live
reconstruction, memory chains, action fidelity and independent check in the stand-in world, and the verdict of every
stand-in stop behaviour.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import pickle
import tempfile
import unittest
from pathlib import Path

from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s33_capture as cap
from miaosuan_agent.evaluation import s33_pilot as sp
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.experiments import t7_b1_stop_engage as b1
from tests.fixtures import s33_engine as se

ROOT = Path(__file__).resolve().parents[1]


def script(name: str):
    spec = importlib.util.spec_from_file_location(f"s33_test_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CARDS = script("build_s33_card")
ANALYSIS = script("s33_analysis")
REV = script("run_evaluation")


def committed_card():
    return json.loads(CARDS.CARD.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------
# card and its bindings


class CardTest(unittest.TestCase):
    def test_committed_card_rebuilds_byte_for_byte_and_passes(self) -> None:
        self.assertEqual(sp.dump(CARDS.build()), CARDS.CARD.read_text(encoding="utf-8"))
        self.assertEqual(sp.card_problems(committed_card(), ROOT), [])

    def test_schedule_sessions_and_budget(self) -> None:
        card = committed_card()
        self.assertEqual([(g["screen_position"], g["scenario_id"], g["condition"], g["red"], g["blue"])
                          for g in card["games"]],
                         [(1, "2120531121", "C3", INERT_ID, sp.CANDIDATE_ID),
                          (2, "1930331196", "C3", INERT_ID, sp.CANDIDATE_ID)])
        self.assertEqual(card["budget"], {"batch_sessions": 2, "ledger_base_session": 2800, "sprint_session_cap": 2})
        self.assertEqual(sp.EXPECTED_SESSIONS, (2801, 2802))
        self.assertEqual((card["track"], card["eligible_for_promotion"]), ("EXPLORATORY", False))
        self.assertEqual(card["screen"]["mechanism_rules"], "s33-t7-b1-mechanism-1")

    def test_card_problems_catch_every_pin(self) -> None:
        card = committed_card()
        for mutate in (lambda c: c["screen"]["rules"]["inert_harm"]["positions"]["1"].update(occupy=300),
                       lambda c: c["screen"]["frozen_files"].update({sp.FROZEN_FILES[0]: "0" * 64}),
                       lambda c: c["screen"].update(controls_sha256="0" * 64),
                       lambda c: c["screen"].update(preflight_sha256="0" * 64),
                       lambda c: c["screen"].update(mechanism_rules="other"),
                       lambda c: c["games"].reverse(),
                       lambda c: c["policies"][sp.CANDIDATE_ID]["policy_source"].update(sha256="0" * 64),
                       lambda c: c["budget"].update(sprint_session_cap=3),
                       lambda c: c["screen"].update(dispositions=["X"])):
            bad = copy.deepcopy(card)
            mutate(bad)
            self.assertTrue(sp.card_problems(bad, ROOT))
        self.assertEqual(sp.card_problems(dict(card, card_id="other"), ROOT), ["not the Sprint 33 card"])

    def test_candidate_digest_and_pinned_files(self) -> None:
        source = CARDS.policy_source(CARDS.CANDIDATE_SOURCES)
        self.assertEqual((source["sha256"], len(source["files"])), (sp.CANDIDATE_DIGEST, 24))
        self.assertIn("experiments/t7_b1_stop_engage.py", source["files"])
        self.assertEqual(CARDS.policy_source(CARDS.V2_SOURCES)["sha256"],
                         "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae")
        for rel, digest in ((sp.CONTROLS, sp.CONTROLS_SHA256), (sp.PREFLIGHT, sp.PREFLIGHT_SHA256)):
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest)

    def test_thresholds_are_sprint30s_controls(self) -> None:
        controls = json.loads((ROOT / sp.CONTROLS).read_text(encoding="utf-8"))["configurations"]
        self.assertEqual(sorted(sp.RULES["inert_harm"]["positions"]), ["1", "2"])
        for pos, rule in sp.RULES["inert_harm"]["positions"].items():
            row = controls[rule["configuration"]]
            self.assertTrue(row["occupy_constant"])
            self.assertEqual(row["games"], 15)
            self.assertEqual((rule["occupy"], rule["margin_minimum"], rule["margin_floor"]),
                             (row["occupy"]["min"], row["margin"]["min"], row["margin"]["min"] - 50))
        self.assertEqual([(r["occupy"], r["margin_floor"]) for _, r in sorted(sp.RULES["inert_harm"]["positions"].items())],
                         [(310, 509), (310, 520)])

    def test_opportunities_are_sprint32s_verified_first_divergences(self) -> None:
        preflight = json.loads((ROOT / sp.PREFLIGHT).read_text(encoding="utf-8"))
        self.assertEqual(preflight["disposition"], "S32_PREFLIGHT_INADEQUATE")
        self.assertEqual(preflight["verified_inert_configurations"], {"blue": ["1930331196 C3", "2120531121 C3"],
                                                                      "red": []})
        sides = {(s["population"], s["scenario"], s["condition"], s["colour"]): s for s in preflight["sides"]}
        for pos, scenario in (("1", "2120531121"), ("2", "1930331196")):
            first = sides[("HI", scenario, "C3", "blue")]["first_divergence"]
            rule = sp.RULES["opportunity"]["positions"][pos]
            self.assertTrue(first["valid"])
            self.assertEqual((first["step"], first["weapon"], first["distance"], first["range"]),
                             (rule["first_divergence_step"], rule["reaching_weapon"], rule["distance"], rule["range"]))
        self.assertIsNone(sides[("HI", "1930331196", "C2", "red")]["first_divergence"])

    def test_the_frozen_set_exists(self) -> None:
        for rel in sp.FROZEN_FILES:
            self.assertTrue((ROOT / rel).exists(), rel)
        self.assertEqual(len(set(sp.FROZEN_FILES)), len(sp.FROZEN_FILES))


# ------------------------------------------------------------------------------------------------
# ledger


def ledger_rows(card, sessions, state="s0", override=None):
    rows = [{"session": "2800", "event": "session-close", "state": state, "integrity": {"ok": True}}]
    order = [g["game_id"] for g in card["games"]]
    for i, s in enumerate(sessions):
        harness = {"game_id": order[min(i, len(order) - 1)], "card": sp.CARD_ID, "manifest_sha256": mf.digest(card),
                   "policy_source_sha256": sp.CANDIDATE_DIGEST, **(override or {}).get(i, {})}
        rows.append({"session": str(s), "event": "session-open", "harness": harness, "state": state})
        rows.append({"session": str(s), "event": "session-close", "state": state, "integrity": {"ok": True}})
    return rows


class LedgerTest(unittest.TestCase):
    def test_registered_sessions_pass(self) -> None:
        card = committed_card()
        for n in range(3):
            audit = sp.ledger_audit(ledger_rows(card, sp.EXPECTED_SESSIONS[:n]), card)
            self.assertTrue(audit["ok"], audit)
            if n < 2:
                self.assertIsNone(sp.position_ledger_problem(audit, n + 1, card))
        audit = sp.ledger_audit(ledger_rows(card, (2801,)), card)
        self.assertTrue(sp.position_ledger_problem(audit, 1, card))
        self.assertIsNone(sp.position_ledger_problem(audit, 2, card))
        self.assertTrue(sp.position_ledger_problem(audit, 3, card))
        audit = sp.ledger_audit(ledger_rows(card, (2801, 2802)), card)
        self.assertEqual(list(audit["games"]), [g["game_id"] for g in card["games"]])

    def test_every_defect_is_found(self) -> None:
        card = committed_card()
        cases = [ledger_rows(card, (2801,), override={0: {"card": "other"}}),
                 ledger_rows(card, (2801,), override={0: {"policy_source_sha256": "x"}}),
                 ledger_rows(card, (2801,), override={0: {"manifest_sha256": "x"}}),
                 ledger_rows(card, (2801,), override={0: {"game_id": "other"}}),
                 ledger_rows(card, (2802,)),
                 ledger_rows(card, (2801, 2802, 2803)),
                 ledger_rows(card, (2801,))[:-1],
                 ledger_rows(card, (2801,))[:-1] + [{"session": "2801", "event": "session-recovered"}],
                 ledger_rows(card, (2801,))[:-1] + [{"session": "2801", "event": "session-close",
                                                     "integrity": {"ok": False}}],
                 ledger_rows(card, (2801, 2802), override={1: {"game_id": card["games"][0]["game_id"]}})]
        swapped = ledger_rows(card, (2801, 2802))
        swapped[1]["harness"], swapped[3]["harness"] = swapped[3]["harness"], swapped[1]["harness"]
        cases.append(swapped)
        broken = ledger_rows(card, (2801,))
        broken[1]["state"] = "changed"
        cases.append(broken)
        self.assertEqual(len(cases), 12)
        for i, rows in enumerate(cases):
            self.assertFalse(sp.ledger_audit(rows, card)["ok"], i)


# ------------------------------------------------------------------------------------------------
# structural checks


def record(entry, **extra):
    rec = {"status": "COMPLETED", "steps": 3, "scenario_id": entry["scenario_id"], "condition": entry["condition"],
           "seats": [{"seat": 11, "faction": 1, "policy": sp.CANDIDATE_ID, "actions_by_type": {"1": 1, "10": 1}},
                     {"seat": 1, "faction": 0, "policy": INERT_ID}],
           "harness": {"game_id": entry["game_id"], "card": sp.CARD_ID, "policy_source_sha256": sp.CANDIDATE_DIGEST,
                       "policy_sources": {sp.CANDIDATE_ID: sp.CANDIDATE_DIGEST}},
           "final_scores": {"red_total": 4, "blue_total": 10, "red_win": -6, "blue_win": 6},
           "session_close": {"integrity": {"ok": True}}}
    rec.update(extra)
    return rec


def timeline(steps=3, seat=11, moves=1, stops=1):
    st = [{"submitted": []} for _ in range(steps)]
    for i in range(moves):
        st[i]["submitted"].append({"seat": seat, "action": {"type": 1}})
    for i in range(stops):
        st[i]["submitted"].append({"seat": seat, "action": {"type": 10}})
    return {"steps": st, "reconstructed_decisions": steps, "policy_decisions": steps, "stops_emitted": stops,
            "consistency_errors": [], "unregistered_differences": [], "independent_problems": [],
            "repeated_stops": []}


class GameStopsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = next(g for g in committed_card()["games"] if g["screen_position"] == 1)

    def stops(self, rec=None, tl=None, explore=None, max_step=2880, digests=None):
        return sp.game_stops(self.entry, rec or record(self.entry), explore or {"steps": 3}, tl or timeline(),
                             max_step, digests or {"x": ("a", "a")})

    def test_clean_and_each_defect(self) -> None:
        self.assertEqual(self.stops(), {})
        base = record(self.entry)
        cases = {"S1": dict(rec=record(self.entry, session_close={"integrity": {"ok": False}})),
                 "S4": dict(rec=record(self.entry, status="FAILED")),
                 "S6": dict(rec=record(self.entry, seats=[dict(base["seats"][0], replay_mismatches=1),
                                                          base["seats"][1]]))}
        for code, kw in cases.items():
            self.assertIn(code, self.stops(**kw), code)
        s7 = (dict(tl=dict(timeline(), consistency_errors=[{}])), dict(tl=dict(timeline(), independent_problems=[{}])),
              dict(tl=dict(timeline(), unregistered_differences=[{}])), dict(tl=dict(timeline(), repeated_stops=[{}])),
              dict(tl=timeline(moves=2)), dict(tl=timeline(stops=2)), dict(tl=dict(timeline(), stops_emitted=0)),
              dict(tl=dict(timeline(stops=2), stops_emitted=1)),
              dict(tl=dict(timeline(), reconstructed_decisions=2)), dict(max_step=2881),
              dict(digests={"x": ("a", "b")}), dict(digests={"x": (None, "b")}),
              dict(explore={"steps": 3, "addon_errors": [1]}), dict(explore={"steps": 4}),
              dict(rec=record(self.entry, condition="C2")),
              dict(rec=record(self.entry, harness=dict(base["harness"], policy_source_sha256="x"))),
              dict(rec=record(self.entry, observer_errors=["x"])),
              dict(rec=record(self.entry, seats=[base["seats"][0], dict(base["seats"][1], policy=sp.V2_ID)])))
        for kw in s7:
            self.assertIn("S7", self.stops(**kw), kw)
        bad_margin = dict(rec=record(self.entry, final_scores={"red_total": 4, "blue_total": 10, "blue_win": 5}))
        self.assertIn("S4", self.stops(**bad_margin))
        self.assertEqual(sp.structural_stops({"S7": ["x"], "S1": ["y"]}), ["S1", "S7"])


# ------------------------------------------------------------------------------------------------
# gate and disposition


def v(verdict, demonstrated=(), s32=None):
    return {"verdict": verdict, "gate_open": verdict in ("UNTESTED", "STOP_ONLY", "OBSERVED"),
            "s32_verdict": s32 or verdict, "demonstrated": list(demonstrated)}


class GateDispositionTest(unittest.TestCase):
    def test_gate(self) -> None:
        for verdict, open_ in (("UNTESTED", True), ("STOP_ONLY", True), ("OBSERVED", True), ("STRUCTURAL", False),
                               ("ADVERSE", False), ("HARM", False), ("NOT_ENGAGING", False)):
            self.assertEqual(sp.gate(True, [], v(verdict))["next_session_authorized"], open_, verdict)
        self.assertFalse(sp.gate(False, [], v("OBSERVED"))["next_session_authorized"])
        self.assertFalse(sp.gate(True, ["S7"], v("OBSERVED"))["next_session_authorized"])
        self.assertFalse(sp.gate(True, [], None)["next_session_authorized"])

    def test_disposition_order_and_levels(self) -> None:
        def game(p, verdict, demonstrated=(), completed=True, structural=()):
            return {"position": p, "completed": completed, "structural": list(structural),
                    "verdict": v(verdict, demonstrated)}
        full = ["STOP_EXECUTION", "MOVEMENT_RESUMED", "SHOOTING_LISTED", "SHOT_ACCEPTED"]
        cases = [([], True, "T7B1_MECH_INVALID", None),
                 ([game(1, "OBSERVED", full)], False, "T7B1_MECH_INVALID", None),
                 ([game(1, "OBSERVED", full, completed=False)], True, "T7B1_MECH_INVALID", None),
                 ([game(2, "OBSERVED", full)], True, "T7B1_MECH_INVALID", None),
                 ([game(1, "OBSERVED", full, structural=["S7"])], True, "T7B1_MECH_INVALID", None),
                 ([game(1, "OBSERVED", full)], True, "T7B1_MECH_INVALID", None),
                 ([game(1, "ADVERSE"), game(2, "OBSERVED", full)], True, "T7B1_MECH_INVALID", None),
                 ([game(1, "UNTESTED"), game(2, "OBSERVED", full, completed=False)], True, "T7B1_MECH_INVALID", None),
                 ([game(1, "UNTESTED"), game(2, "OBSERVED", full, structural=["S7"])], True, "T7B1_MECH_INVALID",
                  None),
                 ([game(1, "ADVERSE")], True, "T7B1_MECH_REJECT", None),
                 ([game(1, "HARM")], True, "T7B1_MECH_REJECT", None),
                 ([game(1, "UNTESTED"), game(2, "HARM")], True, "T7B1_MECH_REJECT", None),
                 ([game(1, "NOT_ENGAGING")], True, "T7B1_MECH_NOT_ENGAGING", None),
                 ([game(1, "OBSERVED", full), game(2, "UNTESTED")], True, "T7B1_MECH_SUPPORTED",
                  "STOP_AND_SHOT_ACCEPTED"),
                 ([game(1, "UNTESTED"), game(2, "OBSERVED", full[:3])], True, "T7B1_MECH_SUPPORTED",
                  "STOP_AND_SHOOTING_LISTED"),
                 ([game(1, "STOP_ONLY", full[:2]), game(2, "UNTESTED")], True, "T7B1_MECH_STOP_ONLY",
                  "STOP_AND_MOVEMENT_RESUMPTION"),
                 ([game(1, "STOP_ONLY", full[:1]), game(2, "STOP_ONLY", full[:1])], True, "T7B1_MECH_STOP_ONLY",
                  "STOP_EXECUTION"),
                 ([game(1, "UNTESTED"), game(2, "UNTESTED")], True, "T7B1_MECH_UNTESTED", None)]
        for games, ledger_ok, expected, level in cases:
            out = sp.disposition(games, ledger_ok)
            self.assertEqual((out["disposition"], out["evidence_level"]), (expected, level), (games, expected))


# ------------------------------------------------------------------------------------------------
# the real game loop in the stand-in world


COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")
ENTRY = {"game_id": "synthetic", "scenario_id": "900000001", "condition": "C3", "red": INERT_ID,
         "blue": sp.CANDIDATE_ID}
SCORES = {"blue_occupy": 310, "blue_attack": 100, "blue_remain": 400, "blue_total": 810, "red_total": 0,
          "red_occupy": 0, "blue_win": 810, "red_win": -810}


class Played:
    def __init__(self, mode="documented", steps=300, flag=True) -> None:
        from miaosuan_agent.evaluation.game import play
        from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
        spec = GameSpec(game_id="synthetic.C3.s33", scenario_id="900000001", map_id="9000", condition="C3",
                        red=INERT_ID, blue=sp.CANDIDATE_ID, repetition=1, max_time=steps)
        self.timeline = cap.StopTimeline((sp.CANDIDATE_ID,), COSTS)
        ticks = itertools.count()
        factories = {INERT_ID: REV.FACTORIES[INERT_ID], sp.CANDIDATE_ID: lambda: b1.StopEngageAgent()}
        self.record = play(lambda: se.StopEnv(play_steps=steps, mode=mode, flag=flag), factories, spec, se.Inputs,
                           PLAYERS, clock=lambda: next(ticks) * 0.001, replay_policies={sp.CANDIDATE_ID},
                           observer=tc.Tee(xp.ExploreCapture((sp.CANDIDATE_ID,)), self.timeline))
        compact, windows = self.timeline.files()
        self.compact, self.windows = json.loads(compact), pickle.loads(windows)
        view = ANALYSIS.seat_view(self.windows, self.compact, 11)
        self.facts = sp.game_facts(1, ENTRY, view["raws"], view["final"], view["rows"], view["steps"], 11, SCORES, [])


class StandInGameTest(unittest.TestCase):
    """The inert control red against the candidate blue: baseline-v2 sends the IFV toward the objective, the candidate
    stops it while it traverses with the red vehicle in range, and the stand-in applies each stop behaviour."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.games = {mode: Played(mode) for mode in se.MODES}
        cls.games["documented-no-flag"] = Played("documented", flag=False)

    def test_live_reconstruction_and_checks_hold(self) -> None:
        for mode, p in self.games.items():
            self.assertEqual((p.record["status"], p.record.get("observer_errors")), ("COMPLETED", []), mode)
            self.assertEqual(p.compact["reconstructed_decisions"], len(p.compact["steps"]), mode)
            self.assertEqual((p.compact["consistency_errors"], p.compact["unregistered_differences"],
                              p.compact["independent_problems"], p.compact["repeated_stops"]), ([], [], [], []), mode)
            self.assertEqual(p.compact["stops_emitted"], 1, mode)
            self.assertEqual(p.facts["stops"], 1, mode)

    def test_verdict_of_every_stop_behaviour(self) -> None:
        expected = {"documented": ("OBSERVED", "ADVERSE", []), "documented-no-flag": ("OBSERVED", "OBSERVED", []),
                    "refuse": ("ADVERSE", "ADVERSE", ["rejected"]),
                    "defer": ("ADVERSE", "ADVERSE", ["deferred_indefinite", "path_not_cleared"]),
                    "in_place": ("OBSERVED", "OBSERVED", []), "late": ("ADVERSE", "ADVERSE", ["transition_timing"]),
                    "no_resume": ("ADVERSE", "ADVERSE", ["unable_to_resume"]),
                    "no_fire": ("NOT_ENGAGING", "ADVERSE", [])}
        self.assertEqual(sorted(expected), sorted(self.games))
        for mode, (verdict, s32, adverse) in expected.items():
            got = self.games[mode].facts["verdict"]
            self.assertEqual((got["verdict"], got["s32_verdict"], got["adverse"]), (verdict, s32, adverse), mode)

    def test_documented_stop_demonstrates_every_endpoint(self) -> None:
        f = self.games["documented"].facts
        row = f["stop_rows"][0]
        self.assertEqual((row["where"], row["cleared_offset"], row["completed_offset"] - row["cleared_offset"]),
                         ("next_hex", row["h0"], 75))
        self.assertEqual(row["endpoints"]["entry_offset"], row["endpoints"]["expected_entry_offset"])
        self.assertEqual(f["verdict"]["demonstrated"], ["STOP_EXECUTION", "MOVEMENT_RESUMED", "SHOOTING_LISTED",
                                                        "SHOT_ACCEPTED"])
        self.assertTrue(row["endpoints"]["stop_emitted_exact"] and row["endpoints"]["stop_echoed_clean"])
        self.assertEqual(sp.public_problems({k: v for k, v in f.items() if k != "private"},
                                            [se.IFV, se.RED_VEHICLE, se.START, se.FAR, se.RED_HEX], ["900000001"]), [])

    def test_harm_screen_boundaries(self) -> None:
        p = self.games["documented"]
        view = ANALYSIS.seat_view(p.windows, p.compact, 11)
        for occupy, margin, harm in ((310, 509, False), (309, 600, True), (310, 508, True)):
            scores = dict(SCORES, blue_occupy=occupy, blue_total=margin, red_total=0)
            facts = sp.game_facts(1, ENTRY, view["raws"], view["final"], view["rows"], view["steps"], 11, scores, [])
            self.assertEqual(facts["verdict"]["verdict"] == "HARM", harm, (occupy, margin))
        scores = dict(SCORES, blue_total=519, red_total=0)
        facts = sp.game_facts(2, ENTRY, view["raws"], view["final"], view["rows"], view["steps"], 11, scores, [])
        self.assertEqual(facts["verdict"]["verdict"], "HARM")
        scores = dict(SCORES, blue_total=520, red_total=0)
        facts = sp.game_facts(2, ENTRY, view["raws"], view["final"], view["rows"], view["steps"], 11, scores, [])
        self.assertEqual(facts["verdict"]["verdict"], "OBSERVED")


class IndependentFindingTest(unittest.TestCase):
    def test_a_disagreeing_restatement_is_recorded(self) -> None:
        from unittest import mock
        with mock.patch.object(cap, "independent_triggers", lambda *args: {123456}):
            p = Played(steps=60)
        self.assertEqual(len(p.compact["independent_problems"]), len(p.compact["steps"]))
        self.assertEqual((p.compact["consistency_errors"], p.compact["unregistered_differences"]), ([], []))


class ObserverChecksTest(unittest.TestCase):
    def test_appended_only(self) -> None:
        base = [{"actor": 11, "obj_id": 5, "type": 1, "move_path": [1, 2]}]
        stop = {"actor": 11, "obj_id": 7, "type": 10}
        self.assertEqual(cap.appended_only(base, base + [stop], [7], 11), [])
        for live, stops in ((base + [dict(stop, extra=1)], [7]), ([stop] + base, [7]), (base, [7]),
                            (base + [stop, stop], [7]), ([dict(base[0], move_path=[1])] + [stop], [7]),
                            (base + [stop], []), (base + [dict(stop, actor=1)], [7])):
            self.assertTrue(cap.appended_only(base, live, stops, 11), live)

    def test_repeated_stops(self) -> None:
        self.assertEqual(cap.repeated([7], set()), [])
        self.assertEqual(cap.repeated([7], {7}), [7])
        self.assertEqual(cap.repeated([7, 7], set()), [7])
        self.assertEqual(cap.repeated([7, 8], {9}), [])

    def test_each_consistency_check_can_fail(self) -> None:
        from types import SimpleNamespace
        from miaosuan_agent.decision import Memory
        from miaosuan_agent.experiments.exploratory_addon import AddonMemory
        trace = SimpleNamespace(changes=(), skipped=(), baseline_trace_sha256="d", addon_error=None,
                                addon_name=b1.ADDON_NAME, policy=sp.CANDIDATE_ID)
        rebuilt = {"actions": [], "changes": (), "skipped": (), "baseline_trace_sha256": "d"}
        good = {"trace": trace, "memory": AddonMemory(Memory(), ((3, 4),)), "submitted": []}
        self.assertTrue(all(cap.consistency(good, rebuilt, Memory(), ((3, 4),)).values()))
        self.assertFalse(cap.consistency(good, rebuilt, Memory(), ())["addon_memory"])
        self.assertFalse(cap.consistency(good, rebuilt, Memory(deployment_sent=True), ((3, 4),))["baseline_memory"])
        self.assertFalse(cap.consistency(dict(good, submitted=[{"type": 1}]), rebuilt, Memory(), ((3, 4),))["actions"])
        for field, value in (("addon_error", "x"), ("addon_name", "other"), ("policy", "other"),
                             ("baseline_trace_sha256", "e"), ("changes", ("c",)), ("skipped", (("s", 1),))):
            bad = dict(good, trace=SimpleNamespace(**{**vars(trace), field: value}))
            self.assertFalse(all(cap.consistency(bad, rebuilt, Memory(), ((3, 4),)).values()), field)


class EarlierGatesTest(unittest.TestCase):
    def test_missing_unregenerated_and_closed(self) -> None:
        card = committed_card()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self.assertEqual(ANALYSIS.earlier_gates(card, 1, work), "")
            self.assertIn("no stored analysis", ANALYSIS.earlier_gates(card, 2, work))
            path = ANALYSIS.analysis_path(work, 1)
            path.parent.mkdir(parents=True)
            path.write_text("{}\n", encoding="utf-8")
            self.assertIn("does not regenerate", ANALYSIS.earlier_gates(card, 2, work))
            path.write_text(ANALYSIS.text_of(ANALYSIS.analyse(card, 1, work)), encoding="utf-8")
            self.assertIn("closed the gate", ANALYSIS.earlier_gates(card, 2, work))


if __name__ == "__main__":
    unittest.main()
