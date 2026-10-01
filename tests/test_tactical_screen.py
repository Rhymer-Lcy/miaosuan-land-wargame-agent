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
