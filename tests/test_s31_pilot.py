"""The Sprint 31 pilot rules (``evaluation/s31_pilot.py``), observer (``evaluation/s31_capture.py``) and runner checks.

SYNTHETIC inputs throughout, except the committed card, controls, references and preflight they are bound to: ledgers,
records, observation frames and a stand-in world (``tests/fixtures/s31_engine.py``) in which the real ``baseline-v2``
plays one seat and the candidate the other through the real game loop. Pinned: the card, its schedule, positions,
sessions, budget and pins; every threshold against Sprint 30's committed controls and Sprint 27's registered references;
every ledger defect and the position prerequisite; the structural checks; the facts (retained, released with its
reason, departed without release, destroyed, the transition completed on the centre, interference runs, objective
first ownership, losses and recaptures, lost units); every harm boundary; the mechanism failures; the gate; the
disposition order; the earlier-gate check of the runner; the live reconstruction, memory chains and independent check
in the stand-in world; and the whitelist of the new identity.
"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import json
import pickle
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from miaosuan_agent.boundary import MoveCosts, Origin
from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import s27_probe as s27
from miaosuan_agent.evaluation import s31_capture as cap
from miaosuan_agent.evaluation import s31_pilot as sp
from miaosuan_agent.evaluation import t9_confirmation as tc
from miaosuan_agent.experiments import t13_keep_one_k2 as k2
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent
from tests.fixtures import s31_engine as se

ROOT = Path(__file__).resolve().parents[1]


def script(name: str):
    spec = importlib.util.spec_from_file_location(f"s31_test_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CARDS = script("build_s31_card")
ANALYSIS = script("s31_analysis")


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
                         [(1, "2120531121", "C3", INERT_ID, sp.CANDIDATE_ID), (2, "1930331196", "C2", sp.CANDIDATE_ID,
                                                                            INERT_ID),
                          (3, "2130511121", "H1", sp.CANDIDATE_ID, sp.V2_ID),
                          (4, "2130511121", "H2", sp.V2_ID, sp.CANDIDATE_ID)])
        self.assertEqual(card["budget"], {"batch_sessions": 4, "ledger_base_session": 2797, "sprint_session_cap": 4})
        self.assertEqual(sp.EXPECTED_SESSIONS, (2798, 2799, 2800, 2801))
        self.assertEqual((card["track"], card["eligible_for_promotion"]), ("EXPLORATORY", False))

    def test_card_problems_catch_every_pin(self) -> None:
        card = committed_card()
        for mutate in (lambda c: c["screen"]["rules"]["inert_harm"]["positions"]["1"].update(occupy=300),
                       lambda c: c["screen"]["frozen_files"].update({sp.FROZEN_FILES[0]: "0" * 64}),
                       lambda c: c["screen"].update(controls_sha256="0" * 64),
                       lambda c: c["screen"].update(preflight_sha256="0" * 64),
                       lambda c: c["games"].reverse(),
                       lambda c: c["policies"][sp.CANDIDATE_ID]["policy_source"].update(sha256="0" * 64),
                       lambda c: c["budget"].update(sprint_session_cap=5),
                       lambda c: c["screen"].update(mechanism_failures=["M1"])):
            bad = copy.deepcopy(card)
            mutate(bad)
            self.assertTrue(sp.card_problems(bad, ROOT))
        self.assertEqual(sp.card_problems(dict(card, card_id="other"), ROOT), ["not the Sprint 31 pilot card"])

    def test_candidate_digest_and_pinned_files(self) -> None:
        source = CARDS.policy_source(CARDS.CANDIDATE_SOURCES)
        self.assertEqual((source["sha256"], len(source["files"])), (sp.CANDIDATE_DIGEST, 25))
        self.assertIn("experiments/t13_keep_one_k2.py", source["files"])
        for rel, digest in ((sp.CONTROLS, sp.CONTROLS_SHA256), (sp.PREFLIGHT, sp.PREFLIGHT_SHA256)):
            self.assertEqual(__import__("hashlib").sha256((ROOT / rel).read_bytes()).hexdigest(), digest)
        self.assertEqual(json.loads((ROOT / sp.PREFLIGHT).read_text(encoding="utf-8"))["disposition"],
                         "K2_PREFLIGHT_PASS")

    def test_thresholds_are_sprint30s_controls(self) -> None:
        controls = json.loads((ROOT / sp.CONTROLS).read_text(encoding="utf-8"))["configurations"]
        for pos, rule in sp.RULES["inert_harm"]["positions"].items():
            row = controls[rule["configuration"]]
            self.assertTrue(row["occupy_constant"])
            self.assertEqual((rule["occupy"], rule["margin_minimum"], rule["margin_floor"]),
                             (row["occupy"]["min"], row["margin"]["min"], row["margin"]["min"] - 50))
        for pos, rule in sp.RULES["head_to_head_harm"]["positions"].items():
            row = controls[f"2130511121 C1 baseline-v2 {rule['seat']}"]
            self.assertEqual((rule["margin_minimum"], rule["occupy_minimum"], rule["occupy_maximum"],
                              rule["margin_mean"]),
                             (row["margin"]["min"], row["occupy"]["min"], row["occupy"]["max"], row["margin"]["mean"]))

    def test_opening_objectives_are_sprint27s_equal_references(self) -> None:
        refs = s27.RULES["p2"]["references"]
        for pos, rule in sp.RULES["head_to_head_harm"]["positions"].items():
            expected = sorted(label for label, steps in refs[rule["seat"]].items()
                              if None not in steps.values() and len(set(steps.values())) == 1)
            self.assertEqual(sorted(rule["opening_objectives"]), expected)

    def test_the_frozen_set_exists(self) -> None:
        for rel in sp.FROZEN_FILES:
            self.assertTrue((ROOT / rel).exists(), rel)


# ------------------------------------------------------------------------------------------------
# ledger


def ledger_rows(card, sessions, state="s0", override=None):
    rows = [{"session": "2797", "event": "session-close", "state": state, "integrity": {"ok": True}}]
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
        for n in range(5):
            audit = sp.ledger_audit(ledger_rows(card, sp.EXPECTED_SESSIONS[:n]), card)
            self.assertTrue(audit["ok"], audit)
            self.assertIsNone(sp.position_ledger_problem(audit, n + 1, card) if n < 4 else None)
        audit = sp.ledger_audit(ledger_rows(card, (2798,)), card)
        self.assertTrue(sp.position_ledger_problem(audit, 1, card))
        self.assertTrue(sp.position_ledger_problem(audit, 3, card))
        self.assertIsNone(sp.position_ledger_problem(audit, 2, card))
        audit = sp.ledger_audit(ledger_rows(card, (2798, 2799, 2800)), card)
        self.assertEqual(list(audit["games"]), [g["game_id"] for g in card["games"]][:3])

    def test_every_defect_is_found(self) -> None:
        card = committed_card()
        cases = [ledger_rows(card, (2798,), override={0: {"card": "other"}}),
                 ledger_rows(card, (2798,), override={0: {"policy_source_sha256": "x"}}),
                 ledger_rows(card, (2799,)),
                 ledger_rows(card, (2798, 2799, 2800, 2801, 2802)),
                 ledger_rows(card, (2798,))[:-1],
                 ledger_rows(card, (2798,))[:-1] + [{"session": "2798", "event": "session-recovered"}],
                 ledger_rows(card, (2798,))[:-1] + [{"session": "2798", "event": "session-close",
                                                     "integrity": {"ok": False}}]]
        swapped = ledger_rows(card, (2798, 2799))
        swapped[1]["harness"], swapped[3]["harness"] = swapped[3]["harness"], swapped[1]["harness"]
        cases.append(swapped)
        broken = ledger_rows(card, (2798,))
        broken[1]["state"] = "changed"
        cases.append(broken)
        for rows in cases:
            self.assertFalse(sp.ledger_audit(rows, card)["ok"])


# ------------------------------------------------------------------------------------------------
# structural checks


def record(entry, side="red", **extra):
    faction = 0 if side == "red" else 1
    other = sp.opponent(entry)
    rec = {"status": "COMPLETED", "steps": 3, "scenario_id": entry["scenario_id"], "condition": entry["condition"],
           "seats": [{"seat": 1 if faction == 0 else 11, "faction": faction, "policy": sp.CANDIDATE_ID,
                      "actions_by_type": {"1": 1}},
                     {"seat": 11 if faction == 0 else 1, "faction": 1 - faction, "policy": other}],
           "harness": {"game_id": entry["game_id"], "card": sp.CARD_ID, "policy_source_sha256": sp.CANDIDATE_DIGEST,
                       "policy_sources": {sp.V2_ID: sp.V2_DIGEST}},
           "final_scores": {"red_total": 10, "blue_total": 4, "red_win": 6, "blue_win": -6},
           "session_close": {"integrity": {"ok": True}}}
    rec.update(extra)
    return rec


def timeline(steps=3, seats=1, seat=1, moves=1):
    st = [{"submitted": []} for _ in range(steps)]
    for i in range(moves):
        st[i]["submitted"].append({"seat": seat, "action": {"type": 1}})
    return {"steps": st, "reconstructed_decisions": seats * steps, "policy_decisions": seats * steps,
            "consistency_errors": [], "unregistered_differences": [], "independent_problems": []}


class GameStopsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = next(g for g in committed_card()["games"] if g["screen_position"] == 2)  # candidate red v inert

    def stops(self, rec=None, tl=None, explore=None, max_step=2880, digests=None):
        return sp.game_stops(self.entry, rec or record(self.entry), explore or {"steps": 3}, tl or timeline(),
                             max_step, digests or {"x": ("a", "a")})

    def test_clean_and_each_defect(self) -> None:
        self.assertEqual(self.stops(), {})
        cases = {"S1": dict(rec=record(self.entry, session_close={"integrity": {"ok": False}})),
                 "S4": dict(rec=record(self.entry, status="FAILED")),
                 "S6": dict(rec=record(self.entry, seats=[dict(record(self.entry)["seats"][0], replay_mismatches=1),
                                                          record(self.entry)["seats"][1]])),
                 }
        for code, kw in cases.items():
            self.assertIn(code, self.stops(**kw), code)
        for kw in (dict(tl=dict(timeline(), consistency_errors=[{}])), dict(tl=dict(timeline(), independent_problems=[{}])),
                   dict(tl=dict(timeline(), unregistered_differences=[{}])), dict(tl=timeline(moves=2)),
                   dict(tl=dict(timeline(), reconstructed_decisions=2)), dict(max_step=2881),
                   dict(digests={"x": ("a", "b")}), dict(explore={"steps": 3, "addon_errors": [1]}),
                   dict(rec=record(self.entry, condition="C3")),
                   dict(rec=record(self.entry, final_scores={"red_total": 10, "blue_total": 4, "red_win": 5}))):
            stops = self.stops(**kw)
            self.assertTrue(set(stops) & {"S4", "S7"}, kw)
        self.assertEqual(sp.structural_stops({"S7": ["x"], "S1": ["y"]}), ["S1", "S7"])


# ------------------------------------------------------------------------------------------------
# facts on synthetic frames (blue is the candidate; the held objective's centre is C)

C, D, OFF = 1010, 1020, 1050
BLUE, RED = 1, 0


def u(obj, hex_=C, path=(), speed=0, stop=1, timer=0, type_=2, sub=0):
    return {"obj_id": obj, "color": BLUE, "type": type_, "sub_type": sub, "cur_hex": hex_, "move_path": list(path),
            "speed": speed, "stop": stop, "move_to_stop_remain_time": timer, "flag_force_stop": 0,
            "change_state_remain_time": 0, "get_on_remain_time": 0, "get_off_remain_time": 0}


def frame(step, units, flag_c=BLUE, flag_d=-1):
    return {"time": {"cur_step": step, "stage": 2, "max_step": 2880}, "operators": units,
            "cities": [{"coord": C, "flag": flag_c, "value": 50}, {"coord": D, "flag": flag_d, "value": 80}]}


def withheld_row(unit, index=0):
    return {"checks": [[C, "withheld", unit, index, 100, [[unit, "eligible"]]]],
            "baseline_actions": [{"obj_id": unit, "type": 1, "move_path": [1011, D]}]}


def plain_row(status="holder_remains"):
    return {"checks": [[C, status, None, None, None, []]], "baseline_actions": []}


def facts(raws, rows, emitted, final=None, position=4, scores=None):
    entry = next(g for g in committed_card()["games"] if g["screen_position"] == position)
    scores = scores or {"blue_occupy": 440, "blue_attack": 300, "blue_remain": 300, "blue_total": 1040,
                        "red_occupy": 0, "red_total": 200, "red_win": -840, "blue_win": 840}
    return sp.game_facts(entry, raws, final, rows, emitted, 0, scores)


class FactsTest(unittest.TestCase):
    def test_retained_then_released_when_another_remains(self) -> None:
        raws = [frame(0, [u(7, timer=74, stop=0)]), frame(1, [u(7, timer=73, stop=0)]),
                frame(2, [u(7, timer=0, stop=1), u(8)]), frame(3, [u(7, path=[1011], speed=1), u(8)])]
        rows = [withheld_row(7), withheld_row(7), plain_row("holder_remains"), plain_row()]
        emitted = [[], [], [{"obj_id": 7, "type": 1}], []]
        f = facts(raws, rows, emitted)
        m = f["mechanism"]
        self.assertEqual((m["withheld_moves"], m["withheld_from_settling_holders"], m["executed_episodes"]), (2, 2, 1))
        self.assertEqual(m["next_decision_outcomes"], {"retained": 2})
        self.assertEqual((m["episodes_by_end"], m["transition_completed_on_centre"]), ({"released": 1}, 1))
        row = m["episode_rows"][0]
        self.assertEqual((row["release"], row["start_step"], row["end_step"], row["duration_steps"]),
                         ("another_occupant_remains", 0, 2, 2))
        self.assertEqual(sp.mechanism_failures(f), {})

    def test_departure_without_release_and_absence(self) -> None:
        raws = [frame(0, [u(7)]), frame(1, [u(7, hex_=OFF)])]
        f = facts(raws, [withheld_row(7), plain_row()], [[], []])
        self.assertEqual(f["mechanism"]["departures_without_release"], 1)
        self.assertEqual(set(sp.mechanism_failures(f)), {"M1", "M2"})
        raws = [frame(0, [u(7)]), frame(1, [u(7)]), frame(2, [])]
        f = facts(raws, [withheld_row(7), withheld_row(7), plain_row()], [[], [], []])
        self.assertEqual((f["mechanism"]["episodes_by_end"], f["mechanism"]["holders_destroyed_while_holding"]),
                         ({"holder_absent": 1}, 1))
        self.assertEqual(f["mechanism"]["next_decision_outcomes"], {"absent": 1, "retained": 1})

    def test_release_when_the_objective_is_lost_and_objective_counts(self) -> None:
        raws = [frame(0, [u(7)], flag_c=-1), frame(1, [u(7)]), frame(2, [u(7)], flag_c=RED),
                frame(3, [u(7, path=[1011], speed=1)], flag_c=RED), frame(4, [], flag_c=BLUE)]
        rows = [plain_row("no_centre_occupant"), withheld_row(7), {"checks": [], "baseline_actions": []},
                {"checks": [], "baseline_actions": []}, plain_row("no_centre_occupant")]
        emitted = [[], [], [{"obj_id": 7, "type": 1}], [], []]
        f = facts(raws, rows, emitted, final=frame(5, [], flag_c=BLUE))
        self.assertEqual(f["mechanism"]["episode_rows"][0]["release"], "objective_not_held")
        self.assertEqual(f["mechanism"]["episode_rows"][0]["objective_lost_with_holder"], 1)
        obj = f["objectives"]["50-point objective A"]
        self.assertEqual((obj["first_ownership_step"], obj["losses"], obj["recaptures"], obj["held_at_end"]),
                         (1, 1, 1, True))
        self.assertEqual(obj["losses_with_a_holder_episode"], 1)
        self.assertEqual(f["objectives"]["80-point objective A"]["first_ownership_step"], None)
        self.assertEqual((f["units_lost"], f["units_lost_total"]), ({"vehicle": 1}, 1))

    def test_interference_runs(self) -> None:
        blockers = [u(20 + i, hex_=C, timer=0) for i in range(3)]
        waiting = u(30, hex_=OFF, path=[C, D], speed=0)
        n = 5
        raws = [frame(i, [u(7)] + blockers + [waiting]) for i in range(n)]
        rows = [withheld_row(7) for _ in range(n)]
        f = facts(raws, rows, [[] for _ in range(n)])
        self.assertEqual(f["mechanism"]["longest_interference_run_steps"], n)
        limit = sp.RULES["mechanism"]["interference_limit_steps"]
        self.assertEqual(limit, 300)
        f["mechanism"]["longest_interference_run_steps"] = limit - 1
        self.assertNotIn("M3", sp.mechanism_failures(f))
        f["mechanism"]["longest_interference_run_steps"] = limit
        self.assertIn("M3", sp.mechanism_failures(f))
        raws = [frame(i, [u(7)] + blockers[:2] + [waiting]) for i in range(n)]
        self.assertEqual(facts(raws, rows, [[] for _ in range(n)])["mechanism"]["longest_interference_run_steps"], 0)

    def test_a_route_on_the_centre_is_not_retention(self) -> None:
        raws = [frame(0, [u(7)]), frame(1, [u(7, path=[1011], speed=0)])]
        f = facts(raws, [withheld_row(7), plain_row()], [[], []])
        self.assertEqual(f["mechanism"]["next_decision_outcomes"], {"departed_without_release": 1})
        self.assertIn("M1", sp.mechanism_failures(f))

    def test_misaligned_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            facts([frame(0, [u(7)])], [], [[]])


# ------------------------------------------------------------------------------------------------
# harm, gate and disposition


def harm_facts(side, occupy, margin, opening=None):
    objectives = {o: {"first_ownership_step": 1} for o in (opening or [])}
    return {"candidate_side": side, "scores": {"occupy": occupy, "margin": margin}, "objectives": objectives}


class HarmTest(unittest.TestCase):
    def test_inert_boundaries(self) -> None:
        self.assertEqual(sp.harm_stops(1, harm_facts("blue", 310, 509)), [])
        self.assertEqual(len(sp.harm_stops(1, harm_facts("blue", 309, 509))), 1)
        self.assertEqual(len(sp.harm_stops(1, harm_facts("blue", 310, 508))), 1)
        self.assertEqual(sp.harm_stops(2, harm_facts("red", 310, 208)), [])
        self.assertEqual(len(sp.harm_stops(2, harm_facts("red", 300, 207))), 2)

    def test_head_to_head_boundaries(self) -> None:
        red = sp.RULES["head_to_head_harm"]["positions"]["3"]["opening_objectives"]
        blue = sp.RULES["head_to_head_harm"]["positions"]["4"]["opening_objectives"]
        self.assertEqual(sp.harm_stops(3, harm_facts("red", 0, -1055, red)), [])
        self.assertEqual(len(sp.harm_stops(3, harm_facts("red", 0, -1056, red))), 1)
        self.assertEqual(sp.harm_stops(4, harm_facts("blue", 390, 719, blue)), [])
        self.assertEqual(len(sp.harm_stops(4, harm_facts("blue", 389, 719, blue))), 1)
        self.assertEqual(len(sp.harm_stops(4, harm_facts("blue", 440, 718, blue))), 1)
        missing = sp.harm_stops(3, harm_facts("red", 50, -800, red[1:]))
        self.assertEqual(len(missing), 1)
        self.assertIn(red[0], missing[0])
        with self.assertRaises(ValueError):
            sp.harm_stops(3, harm_facts("blue", 0, 0, red))


def game(position, completed=True, structural=(), mechanism=None, harm=(), occupy=0, margin=-870, executed=1):
    return {"position": position, "completed": completed, "structural": list(structural), "mechanism": mechanism or {},
            "harm": list(harm), "facts": {"scores": {"occupy": occupy, "margin": margin},
                                          "mechanism": {"executed_episodes": executed}}}


class GateAndDispositionTest(unittest.TestCase):
    def test_gate(self) -> None:
        self.assertEqual(sp.gate(True, [], {}, []), {"next_session_authorized": True, "reasons": []})
        for args in ((False, [], {}, []), (True, ["S7"], {}, []), (True, [], {"M2": ["x"]}, []), (True, [], {}, ["h"])):
            self.assertFalse(sp.gate(*args)["next_session_authorized"])

    def test_disposition_order(self) -> None:
        four = [game(1), game(2), game(3, occupy=80, margin=-869), game(4)]
        self.assertEqual(sp.disposition(four, True)["disposition"], "K2_PILOT_PROMISING")
        exact = [game(1), game(2), game(3, occupy=80, margin=-869), game(4)]
        exact[2]["facts"]["scores"]["margin"] = Fraction(-13049, 15)
        self.assertEqual(sp.disposition(exact, True)["disposition"], "K2_PILOT_PROMISING")
        for third in (game(3, occupy=50, margin=-800), game(3, occupy=80, margin=-870), game(3, occupy=80, executed=0,
                                                                                            margin=-800)):
            self.assertEqual(sp.disposition([game(1), game(2), third, game(4)], True)["disposition"],
                             "K2_PILOT_INCONCLUSIVE")
        self.assertEqual(sp.disposition([game(1), game(2, harm=["h"])], True)["disposition"], "K2_PILOT_REJECT")
        self.assertEqual(sp.disposition([game(1, mechanism={"M2": ["x"]})], True)["disposition"], "K2_PILOT_REJECT")
        for games_, ok in (([game(1, structural=["S7"])], True), ([game(1)], True), ([], True), (four, False),
                           ([game(1, harm=["h"]), game(2)], True), ([game(2)], True),
                           ([game(1, completed=False)], True)):
            self.assertEqual(sp.disposition(games_, ok)["disposition"], "K2_PILOT_INVALID", games_)


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


# ------------------------------------------------------------------------------------------------
# the real game loop in the stand-in world


COSTS = MoveCosts.from_raw(se.Inputs.cost, Origin.ENGINE, "setup_info.cost_data")


class Played:
    def __init__(self, steps=260) -> None:
        from miaosuan_agent.evaluation.game import play
        from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
        from tests.fixtures import synthetic as syn  # noqa: F401
        spec = GameSpec(game_id="synthetic.H2.s31", scenario_id="900000001", map_id="9000", condition="H2",
                        red=sp.V2_ID, blue=sp.CANDIDATE_ID, repetition=1, max_time=steps)
        self.timeline = cap.K2Timeline((sp.V2_ID, sp.CANDIDATE_ID), COSTS)
        ticks = itertools.count()
        factories = {sp.V2_ID: lambda: ShootReservationAgent(), sp.CANDIDATE_ID: lambda: k2.K2Agent()}
        self.record = play(lambda: se.SettleEnv(play_steps=steps), factories, spec, se.Inputs, PLAYERS,
                           clock=lambda: next(ticks) * 0.001, replay_policies={sp.V2_ID, sp.CANDIDATE_ID},
                           observer=tc.Tee(xp.ExploreCapture((sp.CANDIDATE_ID, sp.V2_ID)), self.timeline))
        compact, windows = self.timeline.files()
        self.compact, self.windows = json.loads(compact), pickle.loads(windows)


class StandInGameTest(unittest.TestCase):
    """baseline-v2 red (a tank that lists nothing) against the candidate blue: three blue tanks capture the near
    objective together and are ordered on while settling; the candidate keeps one through and after its transition."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.p = Played()

    def test_live_reconstruction_and_checks_hold(self) -> None:
        p = self.p
        self.assertEqual((p.record["status"], p.record.get("observer_errors")), ("COMPLETED", []))
        self.assertEqual(p.compact["reconstructed_decisions"], 2 * len(p.compact["steps"]))
        self.assertEqual((p.compact["consistency_errors"], p.compact["unregistered_differences"],
                          p.compact["independent_problems"]), ([], [], []))

    def test_facts_show_an_executed_garrison(self) -> None:
        p = self.p
        view = ANALYSIS.seat_view(p.windows, p.compact, 11)
        entry = {"game_id": "synthetic", "scenario_id": "900000001", "condition": "H2", "red": sp.V2_ID,
                 "blue": sp.CANDIDATE_ID}
        f = sp.game_facts(entry, view["raws"], view["final"], view["rows"], view["emitted"], view["errors"], {})
        m = f["mechanism"]
        self.assertGreater(m["executed_episodes"], 0)
        self.assertGreater(m["withheld_from_settling_holders"], 0)
        self.assertEqual((m["departures_without_release"], m["transition_completed_on_centre"]), (0, 1))
        self.assertEqual(sp.mechanism_failures(f), {})
        self.assertEqual(f["objectives"]["80-point objective A"]["first_ownership_step"] is not None, True)

    def test_tampering_is_detected(self) -> None:
        rows = []
        for step in self.p.compact["steps"]:
            row = step["s31"]["11"]
            rows.append(row)
        first = next(r for r in rows if r["withheld"])
        self.assertEqual(len(first["withheld"]), 1)
        self.assertTrue(s27.unregistered_differences(first["baseline_actions"], first["baseline_actions"],
                                                     first["withheld"]))


class ObserverChecksTest(unittest.TestCase):
    """The observer's consistency checks flag a carried add-on memory, a broken baseline memory chain and every other
    field (each check can fail)."""

    def test_each_check_can_fail(self) -> None:
        from types import SimpleNamespace
        from miaosuan_agent.decision import Memory
        from miaosuan_agent.experiments.exploratory_addon import AddonMemory
        trace = SimpleNamespace(changes=(), skipped=(), baseline_trace_sha256="d", addon_error=None,
                                addon_name=k2.ADDON_NAME, policy=sp.CANDIDATE_ID)
        rebuilt = {"actions": [], "changes": (), "skipped": (), "baseline_trace_sha256": "d"}
        good = {"trace": trace, "memory": AddonMemory(Memory(), ()), "submitted": []}
        self.assertTrue(all(cap.consistency(good, rebuilt, Memory()).values()))
        self.assertFalse(cap.consistency(dict(good, memory=AddonMemory(Memory(), ((1, 2),))), rebuilt,
                                         Memory())["addon_memory"])
        self.assertFalse(cap.consistency(good, rebuilt, Memory(deployment_sent=True))["baseline_memory"])
        self.assertFalse(cap.consistency(dict(good, submitted=[{"type": 1}]), rebuilt, Memory())["actions"])
        for field, value in (("addon_error", "x"), ("addon_name", "other"), ("policy", "other"),
                             ("baseline_trace_sha256", "e"), ("changes", ("c",)), ("skipped", (("s", 1),))):
            bad = dict(good, trace=SimpleNamespace(**{**vars(trace), field: value}))
            self.assertFalse(all(cap.consistency(bad, rebuilt, Memory()).values()), field)


class WhitelistTest(unittest.TestCase):
    def test_candidate_occurs_only_in_the_sprint31_card_and_folder(self) -> None:
        cards = 0
        for path in sorted((ROOT / "evaluation").rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if sp.CANDIDATE_ID not in text and sp.CANDIDATE_DIGEST not in text:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = json.loads(text)
            if isinstance(data, dict) and (xp.is_card(data) or path.name == "manifest.json"):
                cards += 1
                self.assertEqual(rel, f"evaluation/{sp.CARD_ID}/manifest.json")
                continue
            self.assertTrue(rel.startswith(f"evaluation/{sp.STUDY_ID}/"), rel)
        self.assertEqual(cards, 1)
        users = sorted(p.relative_to(ROOT).as_posix() for folder in ("src", "scripts")
                       for p in (ROOT / folder).rglob("*.py")
                       if "t13_keep_one_k2" in p.read_text(encoding="utf-8") and p.name != "t13_keep_one_k2.py")
        self.assertEqual(users, ["scripts/build_s31_card.py", "scripts/mutate_s31.py", "scripts/run_s31_game.py",
                                 "scripts/s31_preflight.py", "src/miaosuan_agent/evaluation/s31_capture.py",
                                 "src/miaosuan_agent/evaluation/s31_pilot.py",
                                 "src/miaosuan_agent/evaluation/s31_preflight.py"])
        for name in ("build_run_card.py", "run_explore.sh", "run_explore_game.py", "run_evaluation.py"):
            self.assertNotIn("t13_keep_one_k2", (ROOT / "scripts" / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
