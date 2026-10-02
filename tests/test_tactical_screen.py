"""Exploratory tactical screens (``evaluation/tactical_screen.py``) and the deployment-split screen. SYNTHETIC data.

The registered manifest (byte-identical rebuild, both policies pinned, the arm and head-to-head configurations, the
schedule, the smoke games, EXPLORATORY status), the runner's pins, the smoke facts read from a step capture, and the
registered smoke verdict and exploratory disposition at their boundaries.
"""

from __future__ import annotations

import collections
import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from miaosuan_agent.decision import INERT_ID
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation import tactical_screen as ts
from miaosuan_agent.experiments.deployment_split import CANDIDATE_ID

ROOT = Path(__file__).resolve().parents[1]
SCREEN = "tactical-screen-deployment-split-1"
MANIFEST = ROOT / "evaluation" / SCREEN / "manifest.json"
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(MANIFEST.exists(), "the screen manifest is registered by its own commit")
class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_rebuilds_byte_identically(self) -> None:
        built = load_script("build_tactical_screen").build(SCREEN)
        self.assertEqual(json.dumps(built, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                         MANIFEST.read_text(encoding="utf-8"))

    def test_identities_and_status(self) -> None:
        m = self.m
        self.assertEqual((m["baseline"], m["candidate"]), (sx.CANDIDATE_ID, CANDIDATE_ID))
        self.assertEqual(m["policies"][sx.CANDIDATE_ID]["policy_source"]["sha256"], V2_DIGEST)
        self.assertIn("experiments/deployment_split.py", m["policies"][CANDIDATE_ID]["policy_source"]["files"])
        self.assertFalse(m["eligible_for_promotion"])
        self.assertEqual(m["status"], "EXPLORATORY - NOT ELIGIBLE FOR BASELINE PROMOTION")
        self.assertEqual(m["execution"]["workers"], 32)
        self.assertEqual(m["runtime_environment"], {"OPENBLAS_NUM_THREADS": "1"})

    def test_configurations_and_schedule(self) -> None:
        games = self.m["games"]
        self.assertEqual(len(games), 192)
        self.assertEqual(collections.Counter(g["condition"] for g in games), {"C1": 48, "C2": 48, "C3": 48, "H1": 24, "H2": 24})
        self.assertEqual(set(collections.Counter(g["config"] for g in games).values()), {3})
        self.assertTrue(all(a["config"] != b["config"] for a, b in zip(games, games[1:])))
        self.assertEqual([g["position"] for g in games], list(range(1, 193)))
        for g in games:
            if g["condition"] == "H1":
                self.assertEqual((g["red"], g["blue"]), (CANDIDATE_ID, sx.CANDIDATE_ID))
            elif g["condition"] == "H2":
                self.assertEqual((g["red"], g["blue"]), (sx.CANDIDATE_ID, CANDIDATE_ID))
            else:
                policy = CANDIDATE_ID if g["arm"] == "c" else sx.CANDIDATE_ID
                self.assertEqual((g["red"], g["blue"]), tuple(ts.arm_players(g["condition"], policy)[s] for s in ("red", "blue")))
        smoke = self.m["smoke_games"]
        self.assertEqual(len(smoke), 8)
        self.assertTrue(all((g["red"], g["blue"]) == (CANDIDATE_ID, INERT_ID) for g in smoke))
        self.assertEqual(len(ts.scheduled_games(self.m)), 192)
        self.assertEqual(len(ts.scheduled_games(self.m, smoke=True)), 8)

    def test_runner_refuses_a_changed_candidate_and_never_overwrites_a_capture(self) -> None:
        rev = load_script("run_evaluation")

        def run(manifest, game_id, purpose, capture=False):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "manifest.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                if capture:
                    (Path(tmp) / "work" / "capture").mkdir(parents=True)
                    (Path(tmp) / "work" / "capture" / f"{game_id}.capture.json").write_bytes(b"")
                args = Namespace(manifest=path, game_id=game_id, work=Path(tmp) / "work", engine_install=Path(tmp),
                                 harness_commit="x", harness_dirty=False, purpose=purpose)
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    status = rev.cmd_game(args)
            return status, err.getvalue()

        tampered = copy.deepcopy(self.m)
        tampered["policies"][CANDIDATE_ID]["policy_source"]["sha256"] = "0" * 64
        h1 = next(g["game_id"] for g in self.m["games"] if g["condition"] == "H1")
        status, message = run(tampered, h1, "evaluation")
        self.assertEqual(status, 2)
        self.assertIn(f"policy source of {CANDIDATE_ID}", message)
        status, message = run(self.m, self.m["smoke_games"][0]["game_id"], "diagnostic", capture=True)
        self.assertEqual(status, 2)
        self.assertIn("captures are never overwritten", message)

    def test_sample_every_is_for_diagnostic_runs_only(self) -> None:
        rev = load_script("run_evaluation")
        h1 = next(g["game_id"] for g in self.m["games"] if g["condition"] == "H1")
        for purpose, sample_every in (("evaluation", 1), ("diagnostic", 0)):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "manifest.json"
                path.write_text(json.dumps(self.m), encoding="utf-8")
                args = Namespace(manifest=path, game_id=h1, work=Path(tmp) / "work", engine_install=Path(tmp),
                                 harness_commit="x", harness_dirty=False, purpose=purpose, sample_every=sample_every)
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    status = rev.cmd_game(args)
            self.assertEqual(status, 2, (purpose, sample_every))
            self.assertIn("--sample-every is for diagnostic runs", err.getvalue())


class SmokeTest(unittest.TestCase):
    """The capture as the real engine leaves it: a deployment split's type rewritten from 314 to 14 in place before
    the batch is serialised, and deployment feedback re-reported at every step while the engine clock stands still."""

    def capture(self, split_type=14):
        def split(unit):
            return {"type": split_type, "obj_id": unit, "actor": 1}

        round1 = [{"cur_step": 0, "message": split(11)}, {"cur_step": 0, "message": split(12), "error": {"code": 999}}]
        round2 = round1 + [{"cur_step": 0, "message": split(11)},
                           {"cur_step": 0, "message": split(22), "error": {"code": 999}}]
        return {"setup": {"seats": [{"seat": 1, "faction": 0, "operators": 5}]},
                "steps": [{"k": 0, "stage": 1, "cur_step": 0,
                           "batch": [{"seat": 1, "action": split(11)}, {"seat": 1, "action": split(12)},
                                     {"seat": 11, "action": dict(split(31), actor=11)},
                                     {"seat": 11, "action": {"type": 333}}],
                           "feedback": round1, "appeared": [21, 22], "changed": {"11": {"blood": [4, 2]}}},
                          {"k": 1, "stage": 1, "cur_step": 0,
                           "batch": [{"seat": 1, "action": split(11)}, {"seat": 1, "action": split(22)}],
                           "feedback": round2, "appeared": [], "changed": {}},
                          {"k": 2, "stage": 1, "cur_step": 0, "batch": [{"seat": 1, "action": {"type": 333}}],
                           "feedback": list(round2), "appeared": [], "changed": {}},
                          {"k": 3, "stage": 2, "cur_step": 0,
                           "batch": [{"seat": 1, "action": {"type": 1, "obj_id": 21}},
                                     {"seat": 11, "action": {"type": 1, "obj_id": 31}}],
                           "feedback": list(round2), "appeared": [31], "changed": {}},
                          {"k": 4, "stage": 2, "cur_step": 1, "batch": [{"seat": 1, "action": {"type": 2, "obj_id": 21}}],
                           "feedback": [{"cur_step": 1, "message": {"type": 2, "obj_id": 21}, "error": {"code": 7}}],
                           "appeared": [], "changed": {}}]}

    def record(self, emitted=4):
        return {"game_id": "s.C2.c.s01", "status": "COMPLETED", "policies": {"red": CANDIDATE_ID, "blue": INERT_ID},
                "seats": [{"seat": 1, "faction": 0, "units_seen": 6, "units_acted": 4, "contract_errors": 0,
                           "gate_rejections": {}, "actions_by_type": {"1": 1, "2": 1, "314": emitted, "333": 1}}]}

    def test_smoke_facts(self) -> None:
        script = load_script("tactical_screen")
        for split_type in (14, 314):
            facts = script.smoke_game({"candidate": CANDIDATE_ID}, self.record(), self.capture(split_type))
            self.assertEqual((facts["deployment_steps"], facts["splits_emitted"]), (3, 4))
            self.assertEqual(facts["split_outcomes"], {"no effect, no error": 1, "refused": 2, "took effect": 1})
            self.assertEqual(facts["split_errors_by_code"], {"999": 2})
            self.assertEqual((facts["operators_appearing_in_deployment"], facts["appearing_operators_commanded"]), (2, 1))
            self.assertEqual(facts["refused_orders_to_appearing_operators"], 1)
            self.assertEqual((facts["split_blood_changes"], facts["deployment_ended"], facts["operators_at_setup"]),
                             ({"4->2": 1}, True, 5))

    def test_a_capture_that_disagrees_with_the_record_is_refused(self) -> None:
        script = load_script("tactical_screen")
        with self.assertRaises(SystemExit) as raised:
            script.smoke_game({"candidate": CANDIDATE_ID}, self.record(emitted=5), self.capture())
        self.assertIn("not being read correctly", str(raised.exception))

    def test_fresh_feedback(self) -> None:
        script = load_script("tactical_screen")
        news = script.fresh_feedback(self.capture()["steps"])
        self.assertEqual([len(n) for n in news], [2, 2, 0, 0, 1])
        steps = [{"cur_step": 0, "feedback": [{"m": 1}]}, {"cur_step": 0, "feedback": [{"m": 2}]},
                 {"cur_step": 1, "feedback": [{"m": 2}]}]
        self.assertEqual(script.fresh_feedback(steps), [[{"m": 1}], [{"m": 2}], [{"m": 2}]])

    def test_verdict(self) -> None:
        good = {"splits_emitted": 2, "operators_appearing_in_deployment": 1, "appearing_operators_commanded": 1,
                "status": "COMPLETED", "contract_errors": 0, "deployment_ended": True}
        self.assertEqual(ts.smoke_verdict([good]), "PASS")
        self.assertEqual(ts.smoke_verdict([dict(good, operators_appearing_in_deployment=0)]), "BLOCKED BY ENGINE SEMANTICS")
        self.assertEqual(ts.smoke_verdict([dict(good, appearing_operators_commanded=0)]), "BLOCKED BY ENGINE SEMANTICS")
        split_over_two_games = [dict(good, appearing_operators_commanded=0), dict(good, operators_appearing_in_deployment=0)]
        self.assertEqual(ts.smoke_verdict(split_over_two_games), "BLOCKED BY ENGINE SEMANTICS")
        self.assertEqual(ts.smoke_verdict([good, dict(good, contract_errors=1)]), "FAIL: a game was not healthy")
        self.assertEqual(ts.smoke_verdict([good, dict(good, deployment_ended=False)]), "FAIL: a game was not healthy")


@unittest.skipUnless(MANIFEST.exists(), "the screen manifest is registered by its own commit")
class AnalysisTest(unittest.TestCase):
    """The A/B analysis over synthetic records of every registered game with planted values: integrity first, then
    the metrics and the registered disposition; every planted integrity defect must stop the analysis."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = load_script("tactical_screen")
        cls.m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.index = {s["scenario_id"]: i for i, s in enumerate(cls.m["scenarios"])}

    def records(self):
        """Head-to-head candidate margin +12 in five scenarios and -4 in three; vs-inert candidate-minus-baseline
        active margin +6 in nine of the sixteen C2/C3 configurations, 0 in one and -2 in six; candidate seats see 14
        operators (baseline seats 10) in six scenarios and record a deployment refusal class in the other two."""
        pins = {p: v["policy_source"]["sha256"] for p, v in self.m["policies"].items()}
        out = {}
        for k, g in enumerate(self.m["games"]):
            i, cond = self.index[g["scenario_id"]], g["condition"]
            total = {"red": 100, "blue": 100}
            if cond in ts.HEAD_TO_HEAD:
                total["red" if cond == "H1" else "blue"] += 12 if i < 5 else -4
            elif cond in ("C2", "C3"):
                position = 2 * i + (cond == "C3")
                gain = (6 if position < 9 else 0 if position == 9 else -2) if g["arm"] == "c" else 0
                total["red" if cond == "C2" else "blue"] += 50 + gain
            seats = []
            for faction, policy in ((0, g["red"]), (1, g["blue"])):
                mine = policy == CANDIDATE_ID
                seats.append({"seat": 1 + 10 * faction, "faction": faction, "policy": policy, "contract_errors": 0,
                              "gate_rejections": {}, "duplicate_shoot_target_commands": 0, "replay_mismatches": 0,
                              "feedback_errors_by_code_and_type": {"103/14": 3} if mine and i >= 6 else {},
                              "latency_us": [1000, 3000], "actions_by_type": {"314": 4} if mine else {},
                              "units_seen": 14 if mine and i < 6 else 10})
            scores = {f"{side}_{part}": 0 for side in ("red", "blue") for part in ("attack", "remain")}
            scores.update({f"{side}_total": v for side, v in total.items()})
            scores.update({f"{side}_occupy": v for side, v in total.items()})
            out[g["game_id"]] = {
                "game_id": g["game_id"], "status": "COMPLETED", "session": f"{3000 + k:04d}", "final_scores": scores,
                "seats": seats,
                "harness": {"manifest_sha256": ts.digest(self.m), "dirty": False,
                            "policy_sources": {p: pins[p] for p in {g["red"], g["blue"]} - {INERT_ID}},
                            "runtime": self.m["execution"]["runtime"], "thread_env": dict(self.m["runtime_environment"]),
                            "execution": {"mode": "shared", "workers": 32, "scheduler": self.m["execution"]["scheduler"]}}}
        return out

    @staticmethod
    def ledger(records):
        events = []
        for record in records.values():
            events.append({"session": record["session"], "event": "session-open"})
            events.append({"session": record["session"], "event": "session-close", "state_changed": False,
                           "integrity": {"ok": True}})
        return events

    def analyse(self, records, events=None, queue=None):
        order = queue if queue is not None else [g["game_id"] for g in self.m["games"]]
        events = self.ledger(records) if events is None else events
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evaluation" / SCREEN).mkdir(parents=True)
            (root / "evaluation" / SCREEN / "manifest.json").write_text(MANIFEST.read_text(encoding="utf-8"),
                                                                       encoding="utf-8")
            work = root / "local" / "evaluation" / SCREEN
            (work / "games").mkdir(parents=True)
            (work / "logs").mkdir()
            for game, record in records.items():
                (work / "games" / f"{game}.json").write_text(json.dumps(record), encoding="utf-8")
            (work / "logs" / "queue-1.txt").write_text(chr(10).join(order) + chr(10), encoding="utf-8")
            with mock.patch.object(self.script, "REPO_ROOT", root), \
                    mock.patch.object(self.script.ei, "EngineInstall", lambda path: None), \
                    mock.patch.object(self.script.ei, "read_ledger", lambda install: events):
                return self.script.analyse(SCREEN)

    def candidate_game(self, condition="H1"):
        return next(g["game_id"] for g in self.m["games"] if g["condition"] == condition)

    def test_planted_values_and_disposition(self) -> None:
        out = self.analyse(self.records())
        self.assertTrue(out["integrity"]["pass"], out["integrity"]["problems"])
        self.assertEqual((out["integrity"]["records"], out["integrity"]["sessions"]), (192, [3000, 3191]))
        h = out["head_to_head"]
        self.assertEqual((h["games"], h["pooled_mean_margin"], h["scenarios_positive"], h["scenarios_negative"]),
                         (48, 6.0, 5, 3))
        self.assertEqual(h["wins_draws_losses"], {"win": 30, "draw": 0, "loss": 18})
        self.assertEqual((sorted(set(h["per_scenario_mean_margin"].values())), h["range_per_scenario"]), ([-4, 12], [-4, 12]))
        v = out["vs_inert"]
        self.assertEqual((v["configurations"], v["configurations_not_worse"], v["configurations_better"],
                          v["configurations_worse"]), (16, 10, 9, 6))
        self.assertEqual(sorted(set(v["candidate_minus_baseline_active_margin"].values())), [-2, 0, 6])
        self.assertEqual(set(out["mirror_margin_means"].values()), {0})
        self.assertEqual(out["components"]["head_to_head_candidate_minus_opponent"]["occupy"], 6.0)
        mech = out["mechanism"]
        self.assertEqual((mech["cells"], mech["cells_with_more_operators"], mech["candidate_seat_games"]), (32, 24, 144))
        self.assertEqual(mech["deployment_splits_per_candidate_seat"], {"4": 144})
        self.assertEqual((out["safety"]["b"]["policy seat-games"], out["safety"]["c"]["policy seat-games"]), (144, 144))
        self.assertEqual(out["refusal_classes"]["c"], {"103/14": 108})
        self.assertEqual(out["refusal_class_seat_games"], {"b": {}, "c": {"103/14": 36}})
        self.assertEqual(out["refusal_classes_new_in_candidate"], ["103/14"])
        self.assertEqual(out["failed_games"], {"total": 0, "involving_the_candidate": 0})
        self.assertEqual(out["disposition"], "ADVANCE TO CONFIRMATION")

    def test_dispositions_follow_the_planted_changes(self) -> None:
        records = self.records()
        records[self.candidate_game("H1")]["status"] = "FAILED"
        out = self.analyse(records)
        self.assertEqual((out["failed_games"], out["disposition"], out["head_to_head"]["games"]),
                         ({"total": 1, "involving_the_candidate": 1}, "REJECT TACTIC", 47))
        records = self.records()
        next(s for s in records[self.candidate_game("H2")]["seats"] if s["policy"] == CANDIDATE_ID)["contract_errors"] = 1
        self.assertEqual(self.analyse(records)["disposition"], "REJECT TACTIC")
        records = self.records()
        for game, g in ((g["game_id"], g) for g in self.m["games"]):
            if self.index[g["scenario_id"]] == 5:
                for seat in records[game]["seats"]:
                    if seat["policy"] == CANDIDATE_ID:
                        seat["units_seen"] = 10
        out = self.analyse(records)
        self.assertEqual((out["mechanism"]["cells_with_more_operators"], out["disposition"]),
                         (20, "REVISE BEFORE CONFIRMATION"))

    def test_integrity_defects_stop_the_analysis(self) -> None:
        def broken(change):
            records = self.records()
            change(records)
            return records

        game = self.candidate_game("H1")
        plants = {
            "a missing record": (broken(lambda r: r.pop(game)), None, None, "records for 191 of 192"),
            "a dirty harness": (broken(lambda r: r[game]["harness"].update(dirty=True)), None, None, "dirty harness"),
            "another manifest": (broken(lambda r: r[game]["harness"].update(manifest_sha256="0" * 64)), None, None,
                                 "manifest digest"),
            "another candidate": (broken(lambda r: r[game]["harness"]["policy_sources"].update({CANDIDATE_ID: "0" * 64})),
                                  None, None, "policy sources"),
            "another runtime": (broken(lambda r: r[game]["harness"].update(thread_env={})), None, None, "runtime"),
            "other workers": (broken(lambda r: r[game]["harness"]["execution"].update(workers=8)), None, None,
                              "execution"),
            "a session gap": (broken(lambda r: r[game].update(session="9999")), None, None, "not consecutive"),
        }
        records = self.records()
        twice = self.ledger(records) + [{"session": records[game]["session"], "event": "session-open"}]
        plants["a session opened twice"] = (records, twice, None, "exactly once")
        changed = [dict(e, state_changed=True) if e["session"] == records[game]["session"] and e["event"] == "session-close"
                   else e for e in self.ledger(records)]
        plants["engine state changed"] = (records, changed, None, "state or integrity changed")
        order = [g["game_id"] for g in self.m["games"]]
        order[0], order[1] = order[1], order[0]
        plants["another queue order"] = (records, None, order, "registered order")
        self.assertEqual(len(plants), 10)
        for label, (planted, events, queue, needle) in plants.items():
            out = self.analyse(planted, events, queue)
            self.assertFalse(out["integrity"]["pass"], label)
            self.assertIsNone(out["disposition"], label)
            self.assertTrue(any(needle in p for p in out["integrity"]["problems"]), (label, out["integrity"]["problems"]))


class DispositionTest(unittest.TestCase):
    def test_boundaries(self) -> None:
        advance, revise, reject, _ = ts.DISPOSITIONS
        base = dict(catastrophic=False, pooled_mean=10.0, positive=5, negative=3, activated=24, cells=32, inert_not_worse=8)
        self.assertEqual(ts.exploratory_disposition(**base), advance)
        self.assertEqual(ts.exploratory_disposition(**dict(base, catastrophic=True)), reject)
        self.assertEqual(ts.exploratory_disposition(**dict(base, positive=4)), revise)
        self.assertEqual(ts.exploratory_disposition(**dict(base, activated=23)), revise)
        self.assertEqual(ts.exploratory_disposition(**dict(base, inert_not_worse=7)), revise)
        self.assertEqual(ts.exploratory_disposition(**dict(base, pooled_mean=0.0)), revise)
        self.assertEqual(ts.exploratory_disposition(**dict(base, pooled_mean=-1.0, negative=5, positive=3)), reject)
        self.assertEqual(ts.exploratory_disposition(**dict(base, pooled_mean=-1.0, negative=4, positive=4)), revise)


if __name__ == "__main__":
    unittest.main()
