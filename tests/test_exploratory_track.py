"""The EXPLORATORY track (``docs/EXPLORATORY_TRACK.md``): run cards, the sprint session cap, the runner pins and the
read-only capture. SYNTHETIC states only; no SDK material and no engine.
"""

from __future__ import annotations

import contextlib
import copy
import gzip
import importlib.util
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from miaosuan_agent.boundary import Origin, normalize_state
from miaosuan_agent.evaluation import exploratory as xp
from miaosuan_agent.evaluation import manifest as mf

from tests.fixtures import synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ledger(path: Path, sessions) -> Path:
    lines = []
    for number in sessions:
        lines.append(json.dumps({"event": "session-open", "session": f"{number:04d}"}))
        lines.append(json.dumps({"event": "session-close", "session": f"{number:04d}"}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_script("build_run_card")

    def test_every_committed_card_rebuilds_byte_identically(self) -> None:
        committed = [card for card in self.builder.CARDS
                     if (ROOT / "evaluation" / card / "manifest.json").exists()]
        self.assertTrue(committed, "no committed run card")
        for card_id in committed:
            text = (ROOT / "evaluation" / card_id / "manifest.json").read_text(encoding="utf-8")
            fresh = json.dumps(self.builder.build(card_id), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
            self.assertEqual(text, fresh, card_id)

    def test_cards_are_exploratory_and_budgeted(self) -> None:
        self.assertTrue(self.builder.CARDS)
        for card_id in self.builder.CARDS:
            card = self.builder.build(card_id)
            self.assertTrue(xp.is_card(card))
            self.assertEqual(card["track"], "EXPLORATORY")
            self.assertIs(card["eligible_for_promotion"], False)
            self.assertIn("NOT ELIGIBLE FOR BASELINE PROMOTION", card["status"])
            self.assertEqual(card["budget"], {"batch_sessions": len(card["games"]), "ledger_base_session": 2464,
                                              "sprint_session_cap": 24})
            self.assertEqual(card["policies"][self.builder.V2_ID]["policy_source"]["sha256"], V2_DIGEST)
            for game in card["games"]:
                self.assertIn(card["candidate"], (game["red"], game["blue"]))
                self.assertTrue(game["game_id"].startswith(f"{game['scenario_id']}.{game['condition']}.{card_id}."))
            for field in ("mechanism", "controls", "configurations", "safety_checks", "intended_observations",
                          "version", "next_step_rule"):
                self.assertTrue(card[field], f"{card_id}: {field}")
            self.assertEqual(len(xp.scheduled_games(card)), len(card["games"]))

    def test_build_rejects_inconsistent_input(self) -> None:
        shoot = json.loads((ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" /
                            "manifest.json").read_text(encoding="utf-8"))
        policy = {"id": "p", "label": "p", "policy_source": {"sha256": "0", "files": [], "sources": []}}
        game = {"game_id": "g", "scenario_id": "2120531121", "condition": "H1", "red": "p", "blue": "inert-v0"}
        budget = {"batch_sessions": 1, "ledger_base_session": 2464, "sprint_session_cap": 24}
        xp.build("c", {}, shoot, "x", [policy], "p", [game], "baseline-v1-runtime-r2", 1, budget)
        with self.assertRaises(ValueError):
            xp.build("c", {}, shoot, "x", [policy], "p", [dict(game, scenario_id="1")], "baseline-v1-runtime-r2", 1,
                     budget)
        with self.assertRaises(ValueError):
            xp.build("c", {}, shoot, "x", [policy], "p", [dict(game, red="q")], "baseline-v1-runtime-r2", 1, budget)
        with self.assertRaises(ValueError):
            xp.build("c", {}, shoot, "x", [policy], "p", [game, game], "baseline-v1-runtime-r2", 1,
                     dict(budget, batch_sessions=2))
        with self.assertRaises(ValueError):
            xp.build("c", {}, shoot, "x", [policy], "p", [game], "baseline-v1-runtime-r2", 1,
                     dict(budget, batch_sessions=2))


class BudgetTest(unittest.TestCase):
    def test_sessions_after_the_base_count_toward_the_cap(self) -> None:
        card = {"budget": {"batch_sessions": 6, "ledger_base_session": 2464, "sprint_session_cap": 24}}
        with tempfile.TemporaryDirectory() as tmp:
            path = ledger(Path(tmp) / "usage-ledger.jsonl", range(2460, 2483))  # 2465..2482: 18 after the base
            self.assertEqual(xp.sessions_after(path, 2464), 18)
            self.assertIsNone(xp.budget_problem(card, path, 6))
            self.assertIn("exceed the sprint cap of 24", xp.budget_problem(card, path, 7))
            path = ledger(Path(tmp) / "usage-ledger.jsonl", range(2460, 2470))
            self.assertIn("batch budget of 6", xp.budget_problem(card, path, 7))
            self.assertIn("no session ledger", xp.budget_problem(card, Path(tmp) / "missing.jsonl", 1))


class RunnerPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        builder = load_script("build_run_card")
        cls.card_id = next(iter(builder.CARDS))
        cls.card = builder.build(cls.card_id)

    def run_game(self, card, dirty=False, capture=False, used=0):
        runner = load_script("run_explore_game")
        game_id = card["games"][0]["game_id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(card), encoding="utf-8")
            ledger(Path(tmp) / "usage-ledger.jsonl", range(2464, 2465 + used))
            if capture:
                (Path(tmp) / "work" / "capture").mkdir(parents=True)
                (Path(tmp) / "work" / "capture" / f"{game_id}.explore.json").write_bytes(b"")
            args = Namespace(manifest=path, game_id=game_id, work=Path(tmp) / "work", engine_install=Path(tmp),
                             harness_commit="x", harness_dirty=dirty)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = runner.cmd_game(args)
        return status, err.getvalue()

    def test_a_registered_manifest_is_refused(self) -> None:
        manifest = json.loads((ROOT / "evaluation" / "t7-mechanism-probe-1" / "manifest.json").read_text(encoding="utf-8"))
        manifest["games"] = self.card["games"]
        status, message = self.run_game(manifest)
        self.assertEqual(status, 2)
        self.assertIn("not an exploratory run card", message)

    def test_a_dirty_tree_is_refused(self) -> None:
        status, message = self.run_game(self.card, dirty=True)
        self.assertEqual(status, 2)
        self.assertIn("clean, committed tree", message)

    def test_a_tampered_candidate_digest_is_refused(self) -> None:
        tampered = copy.deepcopy(self.card)
        tampered["policies"][tampered["candidate"]]["policy_source"]["sha256"] = "0" * 64
        status, message = self.run_game(tampered)
        self.assertEqual(status, 2)
        self.assertIn("differs from the registered one", message)

    def test_captures_are_never_overwritten(self) -> None:
        status, message = self.run_game(self.card, capture=True)
        self.assertEqual(status, 2)
        self.assertIn("captures are never overwritten", message)

    def test_an_exhausted_session_cap_is_refused(self) -> None:
        status, message = self.run_game(self.card, used=24)
        self.assertEqual(status, 2)
        self.assertIn("exceed the sprint cap of 24", message)

    def test_runner_knows_the_candidates_and_the_shell_runner(self) -> None:
        runner = load_script("run_explore_game")
        for card_id in load_script("build_run_card").CARDS:
            card = json.loads((ROOT / "evaluation" / card_id / "manifest.json").read_text(encoding="utf-8"))
            for policy in card["policies"]:
                self.assertIn(policy, runner.FACTORIES)
        shell = (ROOT / "scripts" / "run_explore.sh").read_text(encoding="utf-8")
        self.assertIn("build_run_card.py\" --card \"$CARD\" --check", shell)
        self.assertIn("exploratory games run only from a clean, committed tree", shell)
        self.assertIn("card_check end", shell)
        self.assertIn("problem = xp.budget_problem(card, ledger, len(pending))", shell)
        self.assertIn('env -i', shell)
        self.assertIn('HOME="$INSTALL/home"', shell)
        self.assertIn("PYTHONHASHSEED=0", shell)

    def test_the_registered_evaluator_is_unchanged(self) -> None:
        pinned = json.loads((ROOT / "evaluation" / "t7-mechanism-probe-1" / "manifest.json").read_text(
            encoding="utf-8"))["implementation"]["files"]
        from miaosuan_agent.evaluation import t7_probe as tp
        for name in ("scripts/run_evaluation.py", "scripts/run_evaluation.sh"):
            self.assertEqual(tp.normalized_sha256(ROOT / name), pinned[name], name)


class CaptureTest(unittest.TestCase):
    def view(self, cur_step, jm_points=(), judge_info=(), feedback=(), units=None):
        state = syn.state(stage=2, cur_step=cur_step)
        everything = state[-1]
        everything["jm_points"] = [dict(p) for p in jm_points]
        everything["judge_info"] = [dict(j) for j in judge_info]
        everything["actions"] = [dict(f) for f in feedback]
        if units is not None:
            everything["operators"] = units
        return normalize_state(state, Origin.ENGINE)

    def test_orders_points_judgements_and_waiting_units(self) -> None:
        capture = xp.ExploreCapture(("t4-artillery-v1",))
        point = {"obj_id": syn.RED_UNIT, "color": 0, "weapon_id": 72, "pos": 505, "status": 0, "fly_time": 1,
                 "boom_time": 0}
        order = {"actor": syn.RED_SEAT, "obj_id": syn.RED_UNIT, "type": 8, "jm_pos": 505, "weapon_id": 72}
        trace = SimpleNamespace(addon_name="t4", changes=(json.dumps({"kind": "add"}),), skipped=(("weapon cooling", 2),),
                                addon_error=None)
        decisions = [{"seat": syn.RED_SEAT, "faction": 0, "submitted": [order], "trace": trace}]
        waiting = dict(syn.unit(syn.RED_UNIT, 0, syn.RED_HEX, move_path=[103]), speed=0)
        v0 = self.view(10)
        v1 = self.view(11, jm_points=[point], feedback=[{"message": order}], units=[waiting])
        v2 = self.view(12, jm_points=[dict(point, status=1)],
                       judge_info=[{"align_status": 2, "att_obj_id": syn.RED_UNIT, "damage": 1}], units=[waiting])
        v3 = self.view(40, jm_points=[point], units=[waiting])
        capture.step(0, v0, v1, decisions)
        capture.step(1, v1, v2, [])
        capture.step(2, v2, v3, [])
        compact = capture.compact()
        self.assertEqual(len(compact["indirect_orders"]), 1)
        self.assertEqual(compact["indirect_orders"][0]["cur_step"], 10)
        self.assertEqual(len(compact["indirect_feedback"]), 1)
        self.assertEqual([(p["first_step"], p["statuses"]) for p in compact["indirect_points"]],
                         [(11, {"0": 11, "1": 12}), (40, {"0": 40})])
        self.assertEqual(len(compact["indirect_judgements"]), 1)
        self.assertEqual(compact["addon_changes"], {"0:add": 1})
        self.assertEqual(compact["addon_skips"], {"0": {"weapon cooling": 2}})
        self.assertEqual(compact["waiting_ground_units"]["0"], {"max": 1, "sum": 3, "steps_positive": 3})
        compact_bytes, series = capture.files()
        self.assertEqual(json.loads(compact_bytes)["schema"], xp.CAPTURE_SCHEMA)
        self.assertEqual(json.loads(gzip.decompress(series))["waiting"]["0"], [1, 1, 1])
        summary = capture.summary(compact_bytes, series)
        self.assertEqual((summary["indirect_orders"], summary["indirect_points"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
