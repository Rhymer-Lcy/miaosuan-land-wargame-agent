"""The registration of the PS-1 engine probe ``ps1-engine-probe-1`` and its runner pins.

The committed manifest is a byte-identical fresh build from committed inputs; the two configurations keep the original
seats of the Sprint 2 game and the Sprint 1 smoke game; the frozen identities recompute; the rules are registered;
the document cites the manifest; the runner refuses a registered-purpose run, another capture setting, a tampered
digest and an existing capture before it touches the engine.
"""

from __future__ import annotations

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
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import ps1_probe as pp
from miaosuan_agent.evaluation.identity import digest_of_files

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / pp.PROBE_ID / "manifest.json"
DOC = ROOT / "docs" / "PS1_ENGINE_PROBE.md"
SPLIT_SOURCE = "000f639b35becbbd712d6134def855284b80ad4644409dc2f0ae9ee47113a2e9"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_rebuilds_byte_identically(self) -> None:
        builder = load_script("build_ps1_probe_manifest")
        self.assertEqual(MANIFEST.read_text(encoding="utf-8"), json.dumps(builder.build(), indent=1, sort_keys=True) + "\n")

    def test_configurations_keep_the_original_seats(self) -> None:
        p1, p2 = self.manifest["games"]
        self.assertEqual((p1["probe"], p1["scenario_id"], p1["condition"], p1["red"], p1["blue"]),
                         ("P1", "1910631192", "C3", INERT_ID, pp.HOOK_ID))
        self.assertEqual((p2["probe"], p2["scenario_id"], p2["condition"], p2["red"], p2["blue"]),
                         ("P2", "1930331196", "C2", pp.SPLIT_ID, INERT_ID))
        screen = json.loads((ROOT / "evaluation" / pp.SCREEN_ID / "manifest.json").read_text(encoding="utf-8"))
        original = next(g for g in screen["games"] if g["game_id"] == pp.SPRINT2_SPLIT_GAME)
        smoke = next(g for g in screen["smoke_games"] if g["scenario_id"] == "1930331196")
        self.assertEqual((original["red"], original["blue"]), (INERT_ID, pp.SPLIT_ID))
        self.assertEqual((smoke["condition"], smoke["red"], smoke["blue"]), ("C2", pp.SPLIT_ID, INERT_ID))
        self.assertEqual(self.manifest["randomness"]["global_seed"], 20260929)

    def test_frozen_identities(self) -> None:
        policies = self.manifest["policies"]
        self.assertEqual(policies[pp.SPLIT_ID]["policy_source"]["sha256"], SPLIT_SOURCE)
        hooked = policies[pp.HOOK_ID]["policy_source"]
        self.assertEqual(digest_of_files(hooked["files"]), hooked["sha256"])
        self.assertIn("experiments/ps1_probe_hook.py", hooked["files"])
        self.assertIn("evaluation/ps1_model.py", hooked["files"])
        self.assertEqual(self.manifest["model"]["sha256"],
                         pp.normalized_sha256(ROOT / "src" / "miaosuan_agent" / "evaluation" / "ps1_model.py"))
        for path, digest in {**self.manifest["implementation"]["files"], **self.manifest["implementation"]["tests"]}.items():
            self.assertEqual(pp.normalized_sha256(ROOT / path), digest, path)

    def test_two_serial_sessions_on_the_qualified_runtime(self) -> None:
        self.assertEqual(self.manifest["max_sessions"], 2)
        self.assertEqual(len(self.manifest["games"]), 2)
        self.assertEqual(self.manifest["execution"]["workers"], 1)
        self.assertEqual(self.manifest["execution"]["runtime"], "baseline-v1-runtime-r2")
        self.assertTrue(self.manifest["execution"]["scheduler"].startswith("miaosuan-game-pool/1@e717be37"))
        self.assertEqual(self.manifest["capture"]["sample_every"], 1)

    def test_rules_are_registered(self) -> None:
        self.assertEqual(sorted(self.manifest["p1"]["hypotheses"]), ["E1", "E2", "E3", "E4"])
        self.assertEqual(sorted(self.manifest["p2"]["targeted"]), ["T-a", "T-b", "T-c", "T-d", "T-e"])
        self.assertEqual(sorted(self.manifest["gates"]), ["G1", "G2", "G3", "G4", "G5"])
        for key in ("F1", "F2", "integrity", "population", "verdict_rule", "keep", "coverage", "two_methods"):
            self.assertIn(key, self.manifest["p2"])
        self.assertEqual(self.manifest["parameters"]["e3_window"], [74, 77])

    def test_document_cites_the_manifest(self) -> None:
        text = " ".join(DOC.read_text(encoding="utf-8").split())
        self.assertIn(mf.digest(self.manifest), text)
        self.assertIn(self.manifest["policies"][pp.HOOK_ID]["policy_source"]["sha256"], text)
        self.assertIn(self.manifest["model"]["sha256"], text)


class RunnerPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def run_game(self, manifest, purpose="diagnostic", sample_every=None, capture=False):
        rev = load_script("run_evaluation")
        game_id = manifest["games"][0]["game_id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            if capture:
                (Path(tmp) / "work" / "capture").mkdir(parents=True)
                (Path(tmp) / "work" / "capture" / f"{game_id}.windows.pkl").write_bytes(b"")
            args = Namespace(manifest=path, game_id=game_id, work=Path(tmp) / "work", engine_install=Path(tmp),
                             harness_commit="x", harness_dirty=False, purpose=purpose, sample_every=sample_every)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = rev.cmd_game(args)
        return status, err.getvalue()

    def test_a_registered_purpose_run_is_refused(self) -> None:
        status, message = self.run_game(self.manifest, purpose="evaluation")
        self.assertEqual(status, 2)
        self.assertIn("runs as a diagnostic", message)

    def test_another_capture_setting_is_refused(self) -> None:
        status, message = self.run_game(self.manifest, sample_every=200)
        self.assertEqual(status, 2)
        self.assertIn("snapshot every 1 step", message)

    def test_a_tampered_hook_digest_is_refused(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["policies"][pp.HOOK_ID]["policy_source"]["sha256"] = "0" * 64
        status, message = self.run_game(tampered)
        self.assertEqual(status, 2)
        self.assertIn("differs from the registered one", message)

    def test_captures_are_never_overwritten(self) -> None:
        status, message = self.run_game(self.manifest, capture=True)
        self.assertEqual(status, 2)
        self.assertIn("captures are never overwritten", message)


if __name__ == "__main__":
    unittest.main()
