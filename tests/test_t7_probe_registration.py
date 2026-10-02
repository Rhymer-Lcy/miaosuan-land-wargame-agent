"""The registration of the T7 mechanism probe ``t7-mechanism-probe-1`` and its runner pins.

The committed manifest is a byte-identical fresh build from committed inputs; P-A keeps the reference game's
configuration and P-B the head-to-head seat conventions; the frozen identities recompute; every rule is registered;
the protocol document cites the manifest; the runner refuses a registered-purpose run, another capture setting, a
tampered digest and an existing capture before it touches the engine, and the shell plan plays one game per call.
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
from miaosuan_agent.evaluation import t7_probe as tp
from miaosuan_agent.evaluation.identity import digest_of_files

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / tp.PROBE_ID / "manifest.json"
DOC = ROOT / "docs" / "T7_MECHANISM_PROBE.md"


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
        builder = load_script("build_t7_probe_manifest")
        self.assertEqual(MANIFEST.read_text(encoding="utf-8"), json.dumps(builder.build(), indent=1, sort_keys=True) + "\n")

    def test_three_games_with_the_registered_seats(self) -> None:
        pa, pb1, pb2 = self.manifest["games"]
        self.assertEqual((pa["probe"], pa["scenario_id"], pa["condition"], pa["red"], pa["blue"], pa["map_id"]),
                         ("P-A", "1910631192", "C3", INERT_ID, tp.CANDIDATE_ID, "92"))
        self.assertEqual((pb1["probe"], pb1["scenario_id"], pb1["red"], pb1["blue"], pb1["map_id"]),
                         ("P-B1", "2120531121", tp.CANDIDATE_ID, tp.BASELINE_ID, "21"))
        self.assertEqual((pb2["probe"], pb2["scenario_id"], pb2["red"], pb2["blue"]),
                         ("P-B2", "2120531121", tp.BASELINE_ID, tp.CANDIDATE_ID))
        screen = json.loads((ROOT / "evaluation" / tp.SCREEN_ID / "manifest.json").read_text(encoding="utf-8"))
        reference = next(g for g in screen["games"] if g["game_id"] == tp.REFERENCE_GAME)
        self.assertEqual((reference["condition"], reference["red"], reference["blue"]), ("C3", INERT_ID, tp.BASELINE_ID))
        self.assertEqual(self.manifest["randomness"]["global_seed"], 20260929)
        scenarios = {s["scenario_id"]: s for s in screen["scenarios"]}
        for s in self.manifest["scenarios"]:
            self.assertEqual(s, scenarios[s["scenario_id"]])
        self.assertEqual(self.manifest["reference"]["predicted_orders"],
                         [{"k": 717, "cur_step": 716, "units": 2}, {"k": 736, "cur_step": 735, "units": 2}])

    def test_frozen_identities(self) -> None:
        policies = self.manifest["policies"]
        self.assertEqual(policies[tp.BASELINE_ID]["policy_source"]["sha256"], tp.BASELINE_V2_SOURCE_SHA256)
        candidate = policies[tp.CANDIDATE_ID]["policy_source"]
        self.assertEqual(digest_of_files(candidate["files"]), candidate["sha256"])
        self.assertEqual(sorted(set(candidate["files"]) - set(policies[tp.BASELINE_ID]["policy_source"]["files"])),
                         ["experiments/t7_concealment.py", "experiments/t7_idle_concealment.py"])
        for path, digest in {**self.manifest["implementation"]["files"], **self.manifest["implementation"]["tests"]}.items():
            self.assertEqual(tp.normalized_sha256(ROOT / path), digest, path)

    def test_three_serial_sessions_on_the_qualified_runtime(self) -> None:
        self.assertEqual(self.manifest["max_sessions"], 3)
        self.assertEqual(len(self.manifest["games"]), 3)
        self.assertEqual(self.manifest["execution"]["workers"], 1)
        self.assertEqual(self.manifest["execution"]["runtime"], "baseline-v1-runtime-r2")
        self.assertTrue(self.manifest["execution"]["scheduler"].startswith("miaosuan-game-pool/1@e717be37"))
        self.assertEqual(self.manifest["capture"]["sample_every"], 1)
        self.assertEqual(self.manifest["runtime_environment"], {"OPENBLAS_NUM_THREADS": "1"})

    def test_rules_are_registered(self) -> None:
        self.assertEqual(sorted(self.manifest["safety"]), ["S1", "S2", "S3", "S4"])
        self.assertEqual(sorted(self.manifest["mechanism"]), ["E1", "E2", "E3a", "E3b", "E4", "E5", "E6"])
        self.assertEqual(sorted(self.manifest["definitions"]["outcomes"]),
                         ["CENSORED", "COMPLETED", "COMPLETED_TIMER_ANOMALY", "INTERRUPTED", "LATE", "NOT_COMPLETED"])
        for key in ("primary", "integrity", "gate_pa", "stop_pb", "disposition", "stop_rules", "not_claimed",
                    "limitations", "refusal_classes", "candidate"):
            self.assertIn(key, self.manifest)
        self.assertEqual(self.manifest["parameters"]["completion_window"], 76)
        self.assertEqual(len(self.manifest["refusal_classes"]), 4)
        for name in ("premise_private_sha256", "reference_record_sha256", "reference_capture_sha256",
                     "reference_windows_sha256"):
            self.assertIn(name, self.manifest["inputs"])

    def test_public_inputs_match(self) -> None:
        for key, digest in self.manifest["inputs"].items():
            if key.endswith(" (normalised sha256)"):
                self.assertEqual(tp.normalized_sha256(ROOT / key.split(" ")[0]), digest, key)

    def test_document_cites_the_manifest(self) -> None:
        text = " ".join(DOC.read_text(encoding="utf-8").split())
        self.assertIn(mf.digest(self.manifest), text)
        self.assertIn(self.manifest["policies"][tp.CANDIDATE_ID]["policy_source"]["sha256"], text)


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
        self.assertIn("T7 mechanism probe runs as a diagnostic", message)

    def test_another_capture_setting_is_refused(self) -> None:
        status, message = self.run_game(self.manifest, sample_every=200)
        self.assertEqual(status, 2)
        self.assertIn("snapshot every 1 step", message)

    def test_a_tampered_candidate_digest_is_refused(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["policies"][tp.CANDIDATE_ID]["policy_source"]["sha256"] = "0" * 64
        status, message = self.run_game(tampered)
        self.assertEqual(status, 2)
        self.assertIn("differs from the registered one", message)

    def test_captures_are_never_overwritten(self) -> None:
        status, message = self.run_game(self.manifest, capture=True)
        self.assertEqual(status, 2)
        self.assertIn("captures are never overwritten", message)

    def test_runner_knows_the_candidate_and_the_shell_plan(self) -> None:
        rev = load_script("run_evaluation")
        self.assertIn(tp.CANDIDATE_ID, rev.FACTORIES)
        self.assertEqual(sorted(rev.all_games(self.manifest)), sorted(g["game_id"] for g in self.manifest["games"]))
        shell = (ROOT / "scripts" / "run_evaluation.sh").read_text(encoding="utf-8")
        self.assertIn("build_t7_probe_manifest.py\" --check", shell)
        self.assertIn("--plan t7-probe plays exactly one game per invocation", shell)
        self.assertIn("t7_digest_check end", shell)


if __name__ == "__main__":
    unittest.main()
