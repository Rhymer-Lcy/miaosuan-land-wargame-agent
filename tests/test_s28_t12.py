"""Sprint 28 T12-O1 analysis (``evaluation/s28_t12.py``) on synthetic frames: the independent check, episodes, onward
and damage facts, the census, the stops, the interaction criteria, the disposition order, certificates and the
sanitizer."""

from __future__ import annotations

import copy
import unittest

from miaosuan_agent.evaluation import s18_census as sc
from miaosuan_agent.evaluation import s28_t12 as st
from miaosuan_agent.experiments import t12_dispersion_shadow as ts

from tests.test_t12_dispersion_shadow import ACTOR, BLUE, NB, OBJ, RED, FakeCosts, move, unit

OTHER = 909
FULL = {"stop": 1, "move_to_stop_remain_time": 0, "change_state_remain_time": 0, "get_on_remain_time": 0,
        "get_off_remain_time": 0}


def frame(k, own, flags, actions=(), enemies=(), valid=None, stage=2):
    own_map = {u["obj_id"]: u for u in own}
    return sc.Frame(k=k, cur_step=100 + k, max_step=2880, stage=stage, faction=RED, own=own_map, aboard={},
                    enemies={e["obj_id"]: e for e in enemies},
                    valid={o: {1: None} for o in own_map} if valid is None else valid, flags=dict(flags),
                    actions=[dict(a) for a in actions])


def side(frames, population="HH", recorded=None, damage=(), label="HH p01 baseline-v2 red", extras=None):
    return st.Side(population, label, "G", "2130511121", RED, frames,
                   recorded if recorded is not None else [[dict(a) for a in f.actions] for f in frames],
                   FakeCosts(), frozenset(), extras or [{o: dict(FULL) for o in f.own} for f in frames],
                   list(damage), {OBJ: 80, OTHER: 50}, ACTOR)


def scenario(damage=()):
    """Deployment, a dispersal at decision 1 (holder 1, unit 2 dispersed), unit 2 sent on to the other objective at
    decision 2, moving at 3, first owner of the other objective at 4, the origin objective lost at 5."""
    held = {OBJ: RED, OTHER: -1}
    frames = [frame(0, [unit(1), unit(2)], held, stage=1),
              frame(1, [unit(1), unit(2), unit(3, 101)], held),
              frame(2, [unit(1), unit(2)], held, actions=[move(2, (NB[0], OTHER))]),
              frame(3, [unit(1), unit(2, NB[0], speed=1, move_path=(OTHER,))], held),
              frame(4, [unit(1), unit(2, OTHER)], {OBJ: RED, OTHER: RED}),
              frame(5, [unit(1), unit(2, OTHER)], {OBJ: BLUE, OTHER: RED}, actions=[move(2, (808,))])]
    return side(frames, damage=damage)


def damage_row(k, victim, stacked=True, moving=False, aboard=False, on_objective=True, cls="vehicle"):
    return {"k": k, "step": 100 + k, "victim": victim, "victim_class": cls, "aboard": aboard, "moving": moving,
            "on_objective": on_objective, "stacked": stacked, "seen_at_event": True, "seen_before": True, "lost": False}


class ShadowRunTest(unittest.TestCase):
    def test_scenario_is_explained_and_certified(self) -> None:
        a = st.analyse_side(scenario())
        self.assertEqual(a.shadow.unexplained, [])
        self.assertEqual(a.shadow.first_divergence, 1)
        self.assertEqual(list(a.shadow.added), [1])
        self.assertEqual(a.shadow.withheld, {2: (0,)})
        self.assertTrue(all(a.integrity.values()), a.integrity)
        cert = st.certificate(a)
        self.assertEqual((cert["decision"], cert["dispersed_units"], cert["destinations_empty_before"]), (1, 1, 1))
        for key in ("holder_retained", "only_registered_moves_added", "baseline_actions_preserved",
                    "no_baseline_action_for_dispersed_units", "objective_held", "on_policy_baseline_v2_witness"):
            self.assertTrue(cert[key], key)

    def test_no_divergence_without_a_trigger(self) -> None:
        held = {OBJ: RED}
        s = side([frame(0, [unit(1), unit(2, speed=1)], held), frame(1, [unit(1)], held)])
        a = st.analyse_side(s)
        self.assertIsNone(a.shadow.first_divergence)
        self.assertIsNone(st.certificate(a))
        self.assertTrue(all(a.integrity.values()))


class IndependentCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.held = {OBJ: RED, OTHER: -1}

    def problems(self, f, candidate, s=None, dispersed=None):
        checker = st.IndependentCheck(s or side([f]))
        if dispersed:
            checker.dispersed.update(dispersed)
        return [p["problem"] for p in checker.step(f, candidate)]

    def disp(self, obj, dest):
        return {"actor": ACTOR, "obj_id": obj, "type": 1, "move_path": [dest]}

    def test_accepts_a_registered_dispersal(self) -> None:
        f = frame(0, [unit(1), unit(2)], self.held)
        self.assertEqual(self.problems(f, [self.disp(2, NB[3])]), [])

    def test_refusals(self) -> None:
        f = frame(0, [unit(1), unit(2), unit(3)], self.held)
        cases = {
            "no idle holder stays on the objective": [self.disp(1, NB[0]), self.disp(2, NB[1]), self.disp(3, NB[2])],
            "the route is not one hex": [{**self.disp(2, NB[0]), "move_path": [NB[0], 303]}],
            "the destination is not a neighbour inside the map": [self.disp(2, 707)],
            "an appended action is not a registered MOVE": [{**self.disp(2, NB[0]), "actor": 99}],
            "a unit is dispersed twice": [self.disp(2, NB[0]), self.disp(2, NB[1])],
        }
        for problem, candidate in cases.items():
            self.assertIn(problem, self.problems(f, candidate), problem)
        extra = [{**self.disp(2, NB[0]), "x": 1}]
        self.assertIn("an appended action is not a registered MOVE", self.problems(f, extra))

    def test_unit_conditions(self) -> None:
        f = frame(0, [unit(1), unit(2, keep=1), unit(3)], self.held)
        self.assertIn("an appended MOVE is not of an idle own ground unit", self.problems(f, [self.disp(2, NB[0])]))
        f = frame(0, [unit(1), unit(2)], {OBJ: BLUE})
        self.assertIn("the unit is not on an objective the side holds", self.problems(f, [self.disp(2, NB[0])]))
        f = frame(0, [unit(1), unit(2), unit(3, speed=1)], self.held)
        self.assertEqual(self.problems(f, [self.disp(2, NB[0])]), [])
        f = frame(0, [unit(1, speed=1), unit(2)], self.held)
        self.assertIn("fewer than two idle units on the objective", self.problems(f, [self.disp(2, NB[0])]))
        f = frame(0, [unit(1), unit(2)], self.held, valid={1: {1: None}, 2: {}})
        self.assertIn("movement is not listed for the unit", self.problems(f, [self.disp(2, NB[0])]))
        f = frame(0, [unit(1), unit(2)], self.held, actions=[{"actor": ACTOR, "obj_id": 2, "type": 6}])
        self.assertIn("an appended MOVE is not of an idle own ground unit",
                      self.problems(f, list(f.actions) + [self.disp(2, NB[0])]))

    def test_destination_conditions(self) -> None:
        held = {OBJ: RED, NB[0]: -1}
        enemy = {"obj_id": 900, "type": 2, "color": BLUE, "cur_hex": NB[1]}
        own = [unit(1), unit(2), unit(50, 808, move_path=(707, NB[2]))] + [unit(60 + j, NB[4]) for j in range(4)]
        f = frame(0, own, held, enemies=[enemy])
        s = side([f])
        self.assertIn("the destination is an objective", self.problems(f, [self.disp(2, NB[0])], s))
        self.assertIn("the destination holds a visible enemy", self.problems(f, [self.disp(2, NB[1])], s))
        self.assertIn("the destination is on an own route", self.problems(f, [self.disp(2, NB[2])], s))
        self.assertIn("the destination would exceed the stacking limit", self.problems(f, [self.disp(2, NB[4])], s))
        self.assertEqual(self.problems(f, [self.disp(2, NB[3])], s), [])
        cut = side([f])
        cut.costs = FakeCosts(vehicle_cut={(OBJ, NB[3])})
        self.assertIn("the destination is not traversable in the unit's mode", self.problems(f, [self.disp(2, NB[3])], cut))
        rb = side([f])
        rb.roadblocks = frozenset({NB[3]})
        self.assertIn("the destination is a roadblock for a vehicle", self.problems(f, [self.disp(2, NB[3])], rb))

    def test_appended_moves_share_the_room(self) -> None:
        own = [unit(1), unit(2), unit(3)] + [unit(60 + j, NB[4]) for j in range(3)]
        f = frame(0, own, self.held)
        self.assertEqual(self.problems(f, [self.disp(2, NB[4])]), [])
        self.assertIn("the destination would exceed the stacking limit",
                      self.problems(f, [self.disp(2, NB[4]), self.disp(3, NB[4])]))

    def test_removals(self) -> None:
        f = frame(0, [unit(1), unit(2, NB[0])], self.held, actions=[move(2, (NB[0], 303)),
                                                                   {"actor": ACTOR, "obj_id": 1, "type": 6}])
        self.assertEqual(self.problems(f, [f.actions[1]], dispersed={2: OBJ}), [])
        self.assertIn("a removed action is not a MOVE of a dispersed unit", self.problems(f, [f.actions[1]]))
        self.assertIn("a removed action is not a MOVE of a dispersed unit", self.problems(f, [f.actions[0]], dispersed={2: OBJ}))
        lost = frame(0, f.own.values(), {OBJ: BLUE}, actions=f.actions)
        self.assertIn("a removed action is not a MOVE of a dispersed unit",
                      self.problems(lost, [lost.actions[1]], dispersed={2: OBJ}))


class EpisodeTest(unittest.TestCase):
    def test_maximal_runs_per_objective(self) -> None:
        held = {OBJ: RED}
        own = [unit(1), unit(2)]
        frames = [frame(0, own, held), frame(1, own, held), frame(2, [unit(1), unit(2, speed=1)], held),
                  frame(3, own, held)]
        s = side(frames)
        checks = st.stateless_checks(s)
        rows = st.episodes(s, checks, "trigger")
        self.assertEqual([(r["start_k"], r["end_k"], r["decisions"]) for r in rows], [(0, 1, 2), (3, 3, 1)])
        self.assertEqual(st.episodes(s, checks, "legal")[0]["idle"], (1, 2))
        key = st.episode_key(s, rows[0])
        self.assertEqual(key, ("2130511121 red", OBJ, 100, (1, 2)))

    def test_distinct_merges_replicas(self) -> None:
        held = {OBJ: RED}
        frames = [frame(0, [unit(1), unit(2)], held)]
        a1 = st.analyse_side(side(frames, label="HH p01 baseline-v2 red"))
        a2 = st.analyse_side(side(copy.deepcopy(frames), label="HH p03 baseline-v2 red"))
        self.assertEqual(len(st.distinct([a1, a2], "legal")), 1)
        other = [frame(0, [unit(1), unit(4)], held)]
        a3 = st.analyse_side(side(other, label="HH p03 baseline-v2 red"))
        self.assertEqual(len(st.distinct([a1, a3], "legal")), 2)


class OnwardTest(unittest.TestCase):
    def test_claimant_first_owner_and_hold(self) -> None:
        a = st.analyse_side(scenario())
        (row,) = a.legal_episodes
        on = row["onward"]
        (u,) = on["units"]
        self.assertEqual((u["unit"], u["onward_move"], u["claimant"], u["first_owner"]), (2, True, True, True))
        self.assertEqual((u["steps_to_onward_move"], u["suppressed_move_decisions"]), (1, 1))
        self.assertFalse(u["other_own_first_owners"])
        self.assertEqual((on["hold_to_end"], on["hold_release_steps"]), (False, 4))
        self.assertFalse(on["holder_ordered_off_while_held"])

    def test_holder_ordered_off_and_held_destination(self) -> None:
        held = {OBJ: RED, OTHER: RED}
        frames = [frame(0, [unit(1), unit(2)], held),
                  frame(1, [unit(1), unit(2)], held, actions=[move(1, (NB[1], 303)), move(2, (NB[0], OTHER))])]
        a = st.analyse_side(side(frames))
        on = a.legal_episodes[0]["onward"]
        self.assertTrue(on["holder_ordered_off_while_held"])
        self.assertEqual(on["holder_ordered_off_steps"], 1)
        self.assertEqual(on["units"][0]["onward_destination_kind"], st.DEST_HELD)
        self.assertFalse(on["units"][0]["claimant"])
        self.assertTrue(on["hold_to_end"])

    def test_destination_owned_before_the_order(self) -> None:
        held = {OBJ: RED, OTHER: RED}
        frames = [frame(0, [unit(1), unit(2), unit(3, OTHER)], held),
                  frame(1, [unit(1), unit(2)], {OBJ: RED, OTHER: BLUE}, actions=[move(2, (NB[0], OTHER))]),
                  frame(2, [unit(1), unit(2, OTHER)], held)]
        (u,) = st.analyse_side(side(frames)).legal_episodes[0]["onward"]["units"]
        self.assertTrue(u["claimant"])
        self.assertFalse(u["first_owner"])
        self.assertTrue(u["destination_first_owned_before_order"])

    def test_moves_after_release_do_not_count(self) -> None:
        frames = [frame(0, [unit(1), unit(2)], {OBJ: RED, OTHER: -1}),
                  frame(1, [unit(1), unit(2)], {OBJ: BLUE, OTHER: -1}, actions=[move(2, (NB[0], OTHER))])]
        on = st.analyse_side(side(frames)).legal_episodes[0]["onward"]
        self.assertFalse(on["units"][0]["onward_move"])
        self.assertEqual(on["units"][0]["suppressed_move_decisions"], 0)


class DamageTest(unittest.TestCase):
    def test_rows(self) -> None:
        rows = [damage_row(3, 1), damage_row(3, 2, moving=True), damage_row(3, 1, aboard=True),
                damage_row(5, 1, stacked=False), damage_row(1, 1, cls="aircraft")]
        a = st.analyse_side(scenario(rows))
        self.assertEqual(len(a.damage), 2)
        first, lost = a.damage
        self.assertTrue(first["held"] and first["earlier_trigger"] and first["earlier_legal"])
        self.assertTrue(first["earlier_legal_at_first_divergence"])
        self.assertEqual(first["steps_since_latest_legal"], 2)
        self.assertFalse(lost["held"])
        self.assertFalse(lost["earlier_legal"])
        summary = st.damage_summary([a])
        self.assertEqual((summary["HH"]["stationary_on_objective_ground_events"], summary["HH"]["stacked_and_held"]), (2, 1))

    def test_the_event_decision_itself_is_not_earlier(self) -> None:
        held = {OBJ: RED}
        frames = [frame(0, [unit(1), unit(2, speed=1)], held), frame(1, [unit(1), unit(2)], held)]
        a = st.analyse_side(side(frames, damage=[damage_row(1, 1)]))
        self.assertTrue(a.damage[0]["held"])
        self.assertFalse(a.damage[0]["earlier_legal"] or a.damage[0]["earlier_trigger"])

    def test_episode_damage_windows(self) -> None:
        rows = [damage_row(0, 1), damage_row(3, 2), damage_row(3, 2)]
        a = st.analyse_side(scenario(rows))
        d = a.legal_episodes[0]["damage"]
        self.assertEqual((d["centre_units_damaged_before"], d["centre_units_damaged_after"], d["damage_events_after"]),
                         (1, 1, 2))


class CensusTest(unittest.TestCase):
    def test_nested_counts(self) -> None:
        held = {OBJ: RED}
        frames = [frame(0, [unit(1), unit(2)], held),
                  frame(1, [unit(1), unit(2, keep=1)], held),
                  frame(2, [unit(1), unit(2)], held, actions=[move(2, (NB[0], 303))]),
                  frame(3, [unit(1), unit(2, speed=1, move_path=(303,))], held),
                  frame(4, [unit(1)], held)]
        a = st.analyse_side(side(frames))
        c = a.census["objective_decisions"]
        self.assertEqual(c["held_objective_decisions"], 5)
        self.assertEqual(c["centre_two_or_more_ground"], 4)
        self.assertEqual(c["centre_two_or_more_through_A_stationary"], 3)
        self.assertEqual(c["centre_two_or_more_through_D_no_transport_transition"], 3)
        self.assertEqual(c["centre_two_or_more_through_E_not_suppressed"], 2)
        self.assertEqual(c["centre_two_or_more_through_F_no_baseline_move"], 1)
        self.assertEqual((c["trigger"], c["legal_tier"], c["held_objectives"]), (1, 1, 1))
        self.assertEqual(a.census["batch_outcomes_unit_decisions"], {"dispersed": 1, "holder": 1})

    def test_conflict_counters(self) -> None:
        other = 507
        enemy = {"obj_id": 900, "type": 2, "color": BLUE, "cur_hex": NB[0]}
        held = {OBJ: RED, other: RED}
        frames = [frame(0, [unit(1), unit(2), unit(3, other), unit(4, other)], held, enemies=[enemy]),
                  frame(1, [unit(1), unit(2), unit(3, other), unit(4, other, speed=1)], held)]
        c = st.analyse_side(side(frames)).census["objective_decisions"]
        self.assertEqual(c["decisions_with_two_triggered_objectives_sharing_a_neighbour"], 1)
        self.assertEqual(c["trigger_with_a_visible_enemy_on_a_neighbour"], 1)
        self.assertEqual(c["trigger"], 3)

    def test_passes_through(self) -> None:
        self.assertTrue(st.passes_through("idle", "G_no_baseline_action"))
        self.assertTrue(st.passes_through("C_no_transition", "B_no_route"))
        self.assertFalse(st.passes_through("C_no_transition", "C_no_transition"))
        self.assertFalse(st.passes_through("A_stationary", "A_stationary"))
        self.assertTrue(all(st.passes_through("idle", lv) for lv in ts.IDLE_LEVELS))


class PrefixTest(unittest.TestCase):
    def test_h0_prefix(self) -> None:
        held = {OBJ: RED}
        frames = [frame(0, [unit(1)], held, actions=[move(1, (NB[0],))]), frame(1, [unit(1), unit(2)], held)]
        s = side(frames, population="H0", recorded=[[], []], label="H0 2130511121 red")
        self.assertFalse(st.prefix_supported(s, 1))
        self.assertTrue(st.prefix_supported(s, 0))
        cert = st.certificate(st.analyse_side(s))
        self.assertFalse(cert["prefix_supported"] or cert["on_policy_baseline_v2_witness"])


class Stub:
    def __init__(self, population, label, trig, legal, scenario_side="2130511121 red"):
        self.side = type("S", (), {"population": population, "label": label, "scenario_side": scenario_side})()
        self.trigger_episodes = [{"objective": i, "start_step": i, "idle": (i,)} for i in range(trig)]
        self.legal_episodes = [{"objective": i, "start_step": i, "idle": (i,)} for i in range(legal)]


class StopTest(unittest.TestCase):
    def hh(self, counts, legal=None):
        legal = legal or counts
        return [Stub("HH", f"HH p0{i} red", n, m) for i, (n, m) in enumerate(zip(counts, legal), start=1)]

    def test_opportunity_stop(self) -> None:
        self.assertFalse(st.stops(self.hh([1, 1, 1, 1]))["opportunity_stop"]["met"])
        self.assertTrue(st.stops(self.hh([1, 1, 0, 3]))["opportunity_stop"]["met"])
        self.assertTrue(st.stops(self.hh([1, 1, 1]))["opportunity_stop"]["met"])

    def test_legality_gate(self) -> None:
        self.assertFalse(st.stops(self.hh([2, 1, 1, 1]))["legality_gate"]["met"])
        self.assertTrue(st.stops(self.hh([2, 1, 1]))["legality_gate"]["met"])
        self.assertTrue(st.stops(self.hh([2, 1, 1, 1], [1, 0, 1, 1]))["legality_gate"]["met"])

    def test_h0_readings(self) -> None:
        h0 = [Stub("H0", f"H0 s{i} red", n, 0) for i, n in enumerate([2] * 8 + [0] * 8)]
        r = st.stops(self.hh([1, 1, 1, 1]) + h0)["h0_readings"]
        self.assertTrue(r["each_side_game_reading_met"])
        self.assertFalse(r["average_reading_met"])
        h0 = [Stub("H0", f"H0 s{i} red", n, 0) for i, n in enumerate([2] * 7 + [1] + [0] * 8)]
        self.assertTrue(st.stops(h0)["h0_readings"]["average_reading_met"])


class InteractionTest(unittest.TestCase):
    def analysis(self, population, label, eps):
        a = Stub(population, label, 0, 0)
        a.side.scenario_side = label
        a.legal_episodes = eps
        return a

    def ep(self, i, claimants, units, holder_off=False, partial=False):
        check = type("C", (), {"units": (type("U", (), {"outcome": "no_destination_left" if partial else "dispersed"})(),)})()
        return {"objective": i, "start_step": i, "idle": (i,), "check": check,
                "onward": {"units": [{"claimant": j < claimants} for j in range(units)],
                           "holder_ordered_off_while_held": holder_off}}

    def test_majority_boundary(self) -> None:
        half = [self.ep(1, 1, 2), self.ep(2, 1, 2)]
        out = st.interaction([self.analysis("HH", "HH p01 red", half)])
        self.assertFalse(out["met"]["I1_tactical_isolation"])
        more = [self.ep(1, 2, 2), self.ep(2, 1, 2)]
        out = st.interaction([self.analysis("HH", "HH p01 red", more)])
        self.assertTrue(out["met"]["I1_tactical_isolation"])
        self.assertEqual((out["HH"]["claimant_units"], out["HH"]["dispersed_units"]), (3, 4))

    def test_replicas_count_once(self) -> None:
        same = [self.ep(1, 1, 1)]
        a1 = self.analysis("HH", "HH p01 red", same)
        a2 = self.analysis("HH", "HH p01 red", [dict(same[0])])
        a3 = self.analysis("HH", "HH p01 red", [self.ep(2, 0, 1), self.ep(3, 0, 1)])
        out = st.interaction([a1, a2, a3])
        self.assertEqual((out["HH"]["distinct_legal_episodes"], out["HH"]["claimant_units"]), (3, 1))
        self.assertFalse(out["met"]["I1_tactical_isolation"])

    def test_any_population_and_other_criteria(self) -> None:
        hh = self.analysis("HH", "HH p01 red", [self.ep(1, 0, 1)])
        h0 = self.analysis("H0", "H0 s red", [self.ep(1, 0, 1, holder_off=True, partial=True)])
        out = st.interaction([hh, h0])
        self.assertFalse(out["HH"]["I2_holder_ordered_off"])
        self.assertTrue(out["H0"]["I2_holder_ordered_off"] and out["H0"]["I3_partial_dispersion"])
        self.assertTrue(out["met"]["I2_holder_ordered_off"] and out["met"]["I3_partial_dispersion"])
        self.assertFalse(out["met"]["I1_tactical_isolation"])
        self.assertEqual(st.interaction([])["met"], {c: False for c in st.INTERACTION_CRITERIA})


class DispositionTest(unittest.TestCase):
    def test_first_match(self) -> None:
        stop = {"opportunity_stop": {"met": False}, "legality_gate": {"met": False}}
        clear = {"met": {c: False for c in st.INTERACTION_CRITERIA}}
        inter = {"met": {**clear["met"], "I2_holder_ordered_off": True}}
        D = st.DISPOSITIONS
        self.assertEqual(st.disposition(True, True, 0, stop, clear)["disposition"], D[4])
        self.assertEqual(st.disposition(True, True, 0, stop, inter)["disposition"], D[3])
        self.assertEqual(st.disposition(True, True, 0, {**stop, "legality_gate": {"met": True}}, inter)["disposition"], D[2])
        both = {"opportunity_stop": {"met": True}, "legality_gate": {"met": True}}
        self.assertEqual(st.disposition(True, True, 0, both, inter)["disposition"], D[1])
        self.assertEqual(st.disposition(False, True, 0, both, inter)["disposition"], D[0])
        self.assertEqual(st.disposition(True, False, 0, stop, clear)["disposition"], D[0])
        self.assertEqual(st.disposition(True, True, 1, stop, clear)["disposition"], D[0])
        self.assertEqual(st.disposition(True, True, 0, stop, inter)["interaction_criteria_met"], ["I2_holder_ordered_off"])

    def test_names(self) -> None:
        self.assertEqual(st.DISPOSITIONS, ("T12_O1_OFFLINE_INVALID", "T12_O1_INADEQUATE_OPPORTUNITY",
                                           "T12_O1_LEGALITY_UNRESOLVED", "T12_O1_INTERACTION_NOT_READY",
                                           "T12_O1_READY_FOR_MECHANISM_PROPOSAL"))


class PublicTest(unittest.TestCase):
    def test_public_rows_are_sanitised(self) -> None:
        rows = [damage_row(3, 1)]
        a = st.analyse_side(scenario(rows))
        private = {1, 2, 3, OBJ, OTHER, 101, 808} | set(NB)
        files = {"episode": st.public_episode(a, a.legal_episodes[0], 1, True), "side": st.side_summary(a),
                 "pooled": st.pooled([a]), "damage": st.public_damage_row(a, a.damage[0]),
                 "certificate": st.certificate(a), "risks": st.readiness_risks([a]),
                 "interaction": st.interaction([a]), "summary": st.damage_summary([a])}
        for name, data in files.items():
            self.assertEqual(st.public_problems(data, private), [], name)
            self.assertEqual(st.digit_words(data, {"2130511121"}), [], name)
        ep = files["episode"]
        self.assertEqual((ep["objective_label"], ep["centre_own_ground_after"], ep["holder_class"]),
                         ("80-point objective A", 1, "vehicle"))
        self.assertEqual(ep["dispersed"][0]["onward_destination_label"], "50-point objective A")

    def test_sanitiser_catches_an_identifier_word(self) -> None:
        self.assertTrue(st.public_problems({"label": "unit 101 moved"}, {101}))
        self.assertTrue(st.public_problems({"path": 1}, ()))
        self.assertEqual(st.digit_words({"a": "seen 300 steps", "b": "2130511121 red"}, {"2130511121"}), ["300"])

    def test_pooled_counts(self) -> None:
        a = st.analyse_side(scenario())
        p = st.pooled([a])
        self.assertEqual((p["legal_episodes"], p["legal_episodes_distinct"], p["dispersed_units_distinct"]), (1, 1, 1))
        self.assertEqual((p["onward"]["claimants"], p["onward"]["first_owners"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
