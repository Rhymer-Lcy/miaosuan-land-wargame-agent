"""The diagnostic P1 hook ``ps1-probe-hook-1`` and the probe capture, on the SYNTHETIC stand-in engine.

Before its trigger the hook makes the frozen split candidate's decisions (same trace digests, same states); it fires
once, on the registered trigger, verifies it from the observation, stops the group PS-1B selects, never repeats a
stop, emits the planned back-off only when the move is listed again and the safety checks hold, drops the candidate's
actions for units it still controls, and releases units it cannot move. The capture keeps a pre-execution copy of
every action (an in-place rewrite by the engine is detected) and a snapshot at every decision.
"""

from __future__ import annotations

import copy
import json
import pickle
import unittest

from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import digest
from miaosuan_agent.decision.context import build_context
from miaosuan_agent.decision.routing import Router
from miaosuan_agent.experiments import ps1_probe_hook as hook
from miaosuan_agent.experiments.deployment_split import CANDIDATE_ID as SPLIT_ID, DeploymentSplitPolicy

from tests.fixtures import ps1_probe_engine as pe

BLUE_SEAT = 11
TRIGGER_K = 23  # the stand-in's deadlock is complete at cur_step 5 and stalled (2 * 3 + 10 steps) from cur_step 22


def notes_by_k(compact):
    return {s["k"]: s["hook_notes"][str(BLUE_SEAT)] for s in compact["steps"] if s.get("hook_notes")}


def blue_seat(record):
    return next(s for s in record["seats"] if s["seat"] == BLUE_SEAT)


class HookGameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hooked = pe.play_probe()
        cls.plain = pe.play_probe(SPLIT_ID)

    def test_before_the_trigger_the_decisions_are_the_candidates(self) -> None:
        record, plain = self.hooked[0], self.plain[0]
        self.assertEqual(record["state_steps"][:TRIGGER_K + 1], plain["state_steps"][:TRIGGER_K + 1])
        self.assertEqual(blue_seat(record)["trace_steps"][:TRIGGER_K], blue_seat(plain)["trace_steps"][:TRIGGER_K])
        self.assertNotEqual(blue_seat(record)["trace_steps"][TRIGGER_K], blue_seat(plain)["trace_steps"][TRIGGER_K])
        self.assertNotEqual(record["state_steps"][TRIGGER_K + 1], plain["state_steps"][TRIGGER_K + 1])

    def test_one_trigger_four_stops_never_repeated(self) -> None:
        _, compact, _ = self.hooked
        notes = notes_by_k(compact)
        self.assertEqual(min(notes), TRIGGER_K)
        self.assertEqual(sum(1 for n in notes[TRIGGER_K] if "trigger at step 22" in n), 1)
        stops = [(s["k"], a["action"]["obj_id"]) for s in compact["steps"] for a in s["submitted"]
                 if a["action"].get("type") == hook.STOP]
        self.assertEqual(stops, [(TRIGGER_K, u) for u in pe.WAITERS])  # the group not on the objective

    def test_back_off_when_the_move_is_listed_again(self) -> None:
        _, compact, _ = self.hooked
        relist = TRIGGER_K + 75
        moves = [(s["k"], a["action"]["obj_id"], a["action"]["move_path"]) for s in compact["steps"]
                 for a in s["submitted"] if a["action"].get("type") == 1 and a["action"]["obj_id"] in pe.WAITERS]
        self.assertEqual(moves[:4], [(relist, u, [105]) for u in pe.WAITERS])
        notes = notes_by_k(compact)
        self.assertEqual(sum(1 for n in notes[relist] if n.startswith(hook.NOTE + "dropped the candidate's action")), 4)
        self.assertIn(hook.NOTE + "done: every stopped unit is resolved", notes[relist])
        self.assertFalse([k for k in notes if k > relist])

    def test_replay_checks_and_record(self) -> None:
        record = self.hooked[0]
        seat = blue_seat(record)
        self.assertEqual((seat["replay_mismatches"], seat["contract_errors"]), (0, 0))
        self.assertGreater(seat["replay_checks"], 1)
        self.assertEqual(seat["actions_by_type"]["10"], 4)

    def test_orders_count_as_progress_in_the_stall_history(self) -> None:
        _, compact, windows = self.hooked
        samples = {s["k"]: s for s in windows["samples"]}
        checked = 0
        for step in compact["steps"]:
            k = step["k"]
            moves = [a["action"]["obj_id"] for a in step["submitted"] if a["seat"] == BLUE_SEAT and a["action"]["type"] == 1]
            if not moves or k + 1 not in samples or k not in samples:
                continue
            cur = pickle.loads(samples[k]["seats"][BLUE_SEAT]["observation"])["time"]["cur_step"]
            last = dict(pickle.loads(samples[k + 1]["seats"][BLUE_SEAT]["memory"]).last)
            self.assertTrue(all(last[u] == cur for u in moves), k)
            checked += len(moves)
        self.assertGreaterEqual(checked, 8)  # the four back-offs and the candidate's later orders

    def test_the_registered_selection_is_back_off_only(self) -> None:
        # the registered PS-1B selection (manifest hook.selection) uses Recovery(option='back-off'); in the stand-in and
        # in P1's predicted state 'auto' would choose the same group, so this pin is what protects the registration
        self.assertEqual(hook.RECOVERY_OPTION, "back-off")

    def test_snapshot_at_every_decision_and_submitted_copies(self) -> None:
        record, compact, windows = self.hooked
        self.assertEqual(sorted(s["k"] for s in windows["samples"]), list(range(1, record["steps"])))
        self.assertTrue(all("submitted" in s for s in compact["steps"]))
        self.assertEqual(sum(s["rewritten_in_place"] for s in compact["steps"]), 0)


class EventStepTest(unittest.TestCase):
    def test_a_516_step_keeps_its_snapshot_among_the_samples(self) -> None:
        import itertools
        from miaosuan_agent.decision import BASELINE_ID
        from miaosuan_agent.evaluation import ps1_probe as pp
        from miaosuan_agent.evaluation.game import play
        from miaosuan_agent.evaluation.manifest import PLAYERS
        from tests.fixtures import fake_engine
        from tests.test_evaluation_game import FACTORIES, Inputs, spec
        capture = pp.ProbeCapture((BASELINE_ID,))
        ticks = itertools.count()
        record = play(lambda: fake_engine.FakeEnv(engine_messages=True, doomed=(7, fake_engine.BLUE_UNIT)), FACTORIES,
                      spec(), Inputs, PLAYERS, clock=lambda: next(ticks) * 0.001, replay_policies={BASELINE_ID},
                      observer=capture)
        self.assertEqual(len(capture.events), 1)
        self.assertEqual(sorted(s["k"] for s in capture.samples), list(range(1, record["steps"])))


class InPlaceRewriteTest(unittest.TestCase):
    def test_the_capture_keeps_the_pre_execution_action(self) -> None:
        record, compact, _ = pe.play_probe(rewrite_stop=99)
        step = compact["steps"][TRIGGER_K]
        self.assertEqual(sorted(a["action"]["type"] for a in step["submitted"] if a["seat"] == BLUE_SEAT), [10] * 4)
        self.assertEqual(sorted(b["action"]["type"] for b in step["batch"] if b["seat"] == BLUE_SEAT), [99] * 4)
        self.assertEqual(step["rewritten_in_place"], 4)
        self.assertEqual(blue_seat(record)["actions_by_type"]["10"], 4)  # the record counts before the step


def trigger_state():
    """The stand-in's observation at the trigger, with the seat's memory chain of the hooked game up to it."""
    record, compact, windows = pe.play_probe(play_steps=TRIGGER_K + 2)
    sample = next(s for s in windows["samples"] if s["k"] == TRIGGER_K)
    entry = sample["seats"][BLUE_SEAT]
    return pickle.loads(entry["observation"]), pickle.loads(entry["memory"])


class VerificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw, cls.memory = trigger_state()
        cls.costs = MoveCosts.from_raw(pe.cost_data(), Origin.ENGINE)

    def decide(self, raw):
        return hook.ProbePolicy(self.costs).decide(Observation.from_raw(raw, Origin.ENGINE), BLUE_SEAT, 1, self.memory)

    def test_the_trigger_fires_here(self) -> None:
        decision = self.decide(self.raw)
        self.assertEqual(decision.memory.probe.phase, "stopped")
        self.assertEqual([a["type"] for a in decision.actions], [10] * 4)

    def test_a_deadlocked_unit_still_moving_ends_the_probe(self) -> None:
        raw = copy.deepcopy(self.raw)
        next(u for u in raw["operators"] if u["obj_id"] == pe.OCCUPANTS[0])["speed"] = 0.333333
        decision = self.decide(raw)
        self.assertEqual(decision.memory.probe.phase, "ended: trigger not verified")
        self.assertFalse(decision.actions)
        self.assertTrue(any("shows speed" in d for d in decision.trace.diagnostics))

    def test_an_unlisted_stop_ends_the_probe(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["valid_actions"][pe.WAITERS[2]] = {}
        decision = self.decide(raw)
        self.assertEqual(decision.memory.probe.phase, "ended: trigger not verified")
        self.assertTrue(any("does not list action 10" in d for d in decision.trace.diagnostics))

    def test_not_full_next_hex_ends_the_probe(self) -> None:
        self.assertIsNotNone(hook.verification_problem({}, frozenset({1}), {}))

    def test_an_ended_probe_never_acts_again(self) -> None:
        state = hook.ProbeState(phase="ended: trigger not verified", trigger_step=22)
        decision = hook.ProbePolicy(self.costs).decide(Observation.from_raw(self.raw, Origin.ENGINE), BLUE_SEAT, 1,
                                                       hook.ProbeMemory(inner=self.memory.inner, probe=state))
        self.assertFalse(decision.actions)
        self.assertEqual(decision.memory.probe, state)


class NoEscapeTest(unittest.TestCase):
    def test_a_dead_end_corridor_ends_the_probe_without_action(self) -> None:
        record, compact, _ = pe.play_probe(corridor=True, play_steps=60)
        notes = notes_by_k(compact)
        self.assertEqual(list(notes), [TRIGGER_K])
        self.assertTrue(any(n.startswith(hook.NOTE + "ended: no escape plan") for n in notes[TRIGGER_K]))
        self.assertNotIn("10", blue_seat(record)["actions_by_type"])


class WatchTest(unittest.TestCase):
    def test_a_unit_not_eligible_within_the_window_is_released(self) -> None:
        record, compact, _ = pe.play_probe(transition=400, play_steps=TRIGGER_K + 420)
        notes = notes_by_k(compact)
        released = [n for k in notes for n in notes[k] if "released: not eligible within 300 steps" in n]
        self.assertEqual(len(released), 4)
        # cur_step - 22 > 300 first holds at cur_step 323, the observation of decision 324
        self.assertEqual(min(k for k in notes if any("released" in n for n in notes[k])), TRIGGER_K + 301)
        moves = [a for s in compact["steps"] for a in s["submitted"]
                 if a["action"].get("type") == 1 and a["action"]["obj_id"] in pe.WAITERS and s["k"] > TRIGGER_K]
        self.assertTrue(all(a["action"]["move_path"] != [105] for a in moves))  # only the candidate's own moves

    def test_a_newly_full_destination_releases_the_unit(self) -> None:
        _, compact, _ = pe.play_probe(fill=(95, 105, 4))
        notes = notes_by_k(compact)
        released = [n for k in notes for n in notes[k] if "released: s2" in n or "released: s3" in n]
        self.assertEqual(len(released), 4)


class CheckFunctionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw, _ = trigger_state()
        cls.obs = Observation.from_raw(cls.raw, Origin.ENGINE)
        cls.context = build_context(cls.obs, BLUE_SEAT, 1)
        cls.router = Router(MoveCosts.from_raw(pe.cost_data(), Origin.ENGINE))

    def test_stop_problem(self) -> None:
        good = {"actor": BLUE_SEAT, "obj_id": pe.WAITERS[0], "type": 10}
        self.assertIsNone(hook.stop_problem(good, self.context, []))
        cases = {"not a stop action": dict(good, type=1), "fields must be ints": dict(good, obj_id=True),
                 "actor is not this seat": dict(good, actor=1), "obj_id is not a controllable unit": dict(good, obj_id=1),
                 "second action for the same unit in one step": good}
        for reason, action in cases.items():
            seen = [pe.WAITERS[0]] if action is good else []
            self.assertEqual(hook.stop_problem(action, self.context, seen), reason)
        self.assertEqual(hook.stop_problem(dict(good, extra=1), self.context, []), "not a stop action")

    def test_backoff_problem(self) -> None:
        units = hook.own_ground(self.obs, BLUE_SEAT)
        uid = pe.WAITERS[0]
        self.assertEqual(hook.backoff_problem(uid, 999, (105,), units, self.context, self.router, {})[:3], "s1:")
        self.assertEqual(hook.backoff_problem(uid, pe.NEIGHBOUR, (pe.OBJECTIVE,), units, self.context, self.router,
                                              {})[:3], "s2:")
        self.assertEqual(hook.backoff_problem(uid, pe.NEIGHBOUR, (105,), units, self.context, self.router, {105: 4})[:3],
                         "s3:")
        # s4: the unit still has its move path, so the project gate refuses a new move
        self.assertEqual(hook.backoff_problem(uid, pe.NEIGHBOUR, (105,), units, self.context, self.router, {})[:3], "s4:")
        self.assertEqual(hook.backoff_problem(uid, pe.NEIGHBOUR, (999,), units, self.context, self.router, {})[:3], "s4:")


class TraceTest(unittest.TestCase):
    def test_emit_notes_hold_the_canonical_action(self) -> None:
        _, compact, _ = pe.play_probe(play_steps=TRIGGER_K + 2)
        notes = notes_by_k(compact)[TRIGGER_K]
        emitted = [json.loads(n.split("emit ", 1)[1]) for n in notes if n.startswith(hook.NOTE + "emit ")]
        self.assertEqual(emitted, [{"actor": BLUE_SEAT, "obj_id": u, "type": 10} for u in pe.WAITERS])

    def test_untriggered_trace_object_is_the_candidates(self) -> None:
        raw, memory = trigger_state()
        costs = MoveCosts.from_raw(pe.cost_data(), Origin.ENGINE)
        quiet = hook.ProbeMemory(inner=memory.inner, probe=hook.ProbeState(phase="done"))
        obs = Observation.from_raw(raw, Origin.ENGINE)
        mine = hook.ProbePolicy(costs).decide(obs, BLUE_SEAT, 1, quiet)
        theirs = DeploymentSplitPolicy(costs).decide(obs, BLUE_SEAT, 1, memory.inner)
        self.assertEqual(digest(mine.trace), digest(theirs.trace))
        self.assertEqual(mine.actions, theirs.actions)


if __name__ == "__main__":
    unittest.main()
