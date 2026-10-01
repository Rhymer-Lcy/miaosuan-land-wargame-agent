"""The committed launcher-dependency counterfactual, checked against its own figures and the declared gate.

The byte-identical regeneration from the private corpora runs only where they exist (it takes several minutes).
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import launcher_counterfactual as lc
from miaosuan_agent.evaluation.identity import policy_source_digest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation" / "launcher-dependency-counterfactual-1"
PRIVATE = ROOT / "local" / "replay-corpus"
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CounterfactualResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = json.loads((DIRECTORY / "counterfactual.json").read_text(encoding="utf-8"))

    def test_identities(self) -> None:
        replay = load_script("replay_launcher_counterfactual")
        self.assertEqual(self.r["baseline"]["policy_source_sha256"], V2_DIGEST)
        self.assertEqual(self.r["candidate"]["policy_source_sha256"],
                         policy_source_digest(sources=replay.CANDIDATE_SOURCES)[0])
        self.assertFalse(self.r["candidate"]["pinned"])

    def test_fidelity(self) -> None:
        f = self.r["fidelity"]
        self.assertGreater(f["D1 decisions"], 0)
        for key in ("D1 baseline-v2 exact", "D1 baseline-v2 unchanged by the augmentation"):
            self.assertEqual(f[key], f["D1 decisions"], key)
        for key in ("D2 baseline-v0 exact", "D2 baseline-v2 explained against baseline-v0",
                    "D2 baseline-v2 unchanged by the augmentation"):
            self.assertEqual(f[key], f["D2 decisions"], key)
        self.assertFalse([k for k in f if "excluded" in k])

    def test_tallies_are_consistent(self) -> None:
        blocks = [self.r["faithful"]["D1"], self.r["faithful"]["D2"], self.r["information_augmented_reference"]["D1"],
                  self.r["information_augmented_reference"]["D2"]]
        for block in blocks:
            self.assertEqual(sorted(block["categories"]), list(lc.CATEGORIES))
            self.assertEqual(sum(block["categories"].values()), block["changed"])
            direct = sum(block["units"][k] for k in ("alternate-target", "fallback-occupy", "fallback-move", "fallback-none"))
            self.assertEqual(direct, block["suppressed_emitted_shots"])
            self.assertLessEqual(block["suppressed_emitted_shots"], block["excluded_options"])
            self.assertEqual(block["baseline_shots"] - block["candidate_shots"],
                             block["units"]["fallback-occupy"] + block["units"]["fallback-move"] + block["units"]["fallback-none"])
            mix = block["action_mix_in_changed_decisions"]
            self.assertEqual(mix["baseline"].get("shoot", 0) - mix["candidate"].get("shoot", 0),
                             block["baseline_shots"] - block["candidate_shots"])
        reference = self.r["information_augmented_reference"]
        for corpus in ("D1", "D2"):
            o_classes = {k: v for k, v in reference[corpus]["reference_o_classes"].items() if k in ("O1", "O2", "O3")}
            self.assertEqual(sum(o_classes.values()), reference[corpus]["suppressed_emitted_shots"], corpus)
        steps = reference["D1_every_step"]
        self.assertEqual(steps["O1"] + steps["O2"], steps["exposed shots"])
        self.assertEqual(steps["exposed shots, first in step"] + steps.get("exposed shots, later in step", 0), steps["exposed shots"])
        self.assertEqual(sum(sum(v.values()) for v in steps["launcher_blood_at_step_start"].values()), steps["exposed shots"])
        for o_class in ("O1", "O2"):
            self.assertEqual(sum(v for k, v in steps.items() if k.startswith(f"{o_class}: dependent shot")), steps[o_class])
            self.assertEqual(sum(v for k, v in steps.items() if k.startswith(f"{o_class}: dependent") and "in the step" in k),
                             steps[o_class])

    def test_gate_and_disposition_follow_the_declared_rule(self) -> None:
        r = self.r
        faithful = [r["faithful"]["D1"], r["faithful"]["D2"]]
        h4 = r["h4"]
        gate = {
            "G1 no secondary interaction (C6)": sum(t["categories"]["C6"] for t in faithful) == 0,
            "G2 nothing unexplained (C7)": sum(t["categories"]["C7"] + t["unexplained"] for t in faithful) == 0,
            "G3 every replayable diagnostic H4 refusal suppressed": h4["replayable"] > 0 and h4["faithful_suppressed"] == h4["replayable"],
            "G4 no contract or gate regression": sum(t["contract_errors"] + t["gate_rejections"] for t in faithful) == 0,
            "G5 seat-local observation only": True, "G6 opportunity cost measured": True,
            "G7 a meaningful A/B question remains": sum(t["changed"] for t in faithful) > 0,
        }
        self.assertEqual(r["gate"], gate)
        self.assertEqual(r["disposition"], "PREREGISTER" if all(gate.values()) else "DO NOT PREREGISTER")
        self.assertLessEqual(h4["reference_suppressed"], h4["replayable"])
        self.assertLessEqual(h4["replayable"], h4["diagnostic_events"])

    @unittest.skipUnless(PRIVATE.is_dir(), "the replay corpora are private (git-ignored)")
    def test_regenerates_from_the_private_corpora(self) -> None:
        replay = load_script("replay_launcher_counterfactual")
        public, _ = replay.build()
        text = json.dumps(public, indent=1, sort_keys=True) + "\n"
        self.assertEqual((DIRECTORY / "counterfactual.json").read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
