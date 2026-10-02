"""T7 design study: the audit on real records (private; skipped when the replay corpus and captures are absent).

A slice of one pinned replay-corpus game and of one Sprint 2 capture: the raw-dictionary audit and the boundary
cross-count agree; the audit's listing counts equal a census-style count written inline; ``baseline-v0`` replays
every decision of the slice; per seat the slice's decisions are consecutive engine steps.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import pickle
import subprocess
import sys
import unittest
from pathlib import Path

from miaosuan_agent import sdk_data, typed_json
from miaosuan_agent.boundary import MoveCosts, Observation, Origin
from miaosuan_agent.decision import Memory, digest
from miaosuan_agent.decision.policy import BaselinePolicy
from miaosuan_agent.evaluation import t7_audit as ta
from miaosuan_agent.evaluation.t7_crosscheck import CrossCount, agree

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
GAME = "local/replay-corpus/1910631192.C1.r1.jsonl.gz"
DATA = ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
CAPTURE = ROOT / "local" / "evaluation" / "t1r-diagnosis-1" / "capture" / "1910631192.C3.b.x01.windows.pkl"
SLICE = 900


@unittest.skipUnless((ROOT / GAME).is_file() and DATA.is_dir(), "the replay corpus is private (git-ignored)")
class RealCorpusSlice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pinned = {e["path"]: e["sha256"] for e in json.loads(CORPUS.read_text(encoding="utf-8"))["files"]}
        cls.digest_ok = hashlib.sha256((ROOT / GAME).read_bytes()).hexdigest() == pinned[GAME]
        with gzip.open(ROOT / GAME, "rt", encoding="utf-8") as handle:
            cls.header = json.loads(next(handle))
            cls.rows = [json.loads(next(handle)) for _ in range(SLICE)]

    def test_pinned_digest(self):
        self.assertTrue(self.digest_ok)

    def test_audit_and_cross_count_agree_and_match_an_inline_census_count(self):
        audit, cross = ta.Audit(), CrossCount()
        inline = {}
        for row in self.rows:
            raw = typed_json.decode(row["observation"])
            audit.add("g", row["faction"], raw, row["actions"])
            cross.add(Observation.from_raw(raw, Origin.ENGINE), row["faction"])
            stage = {1: "deployment", 2: "play"}[raw["time"]["stage"]]
            listed = {int(t) for actions in raw["valid_actions"].values() for t in actions}
            for t in listed & set(ta.T7_TYPES):
                inline[f"{stage}:{t}"] = inline.get(f"{stage}:{t}", 0) + 1
        summary = audit.summary()
        self.assertTrue(agree(summary, cross.summary())["agree"])
        self.assertEqual(summary["decisions_listing"], inline)
        self.assertGreater(sum(inline.values()), 0)
        self.assertEqual(summary["decisions"]["play"] + summary["decisions"].get("deployment", 0), SLICE)

    def test_baseline_v0_replays_the_slice_and_steps_are_consecutive(self):
        scenario, map_id = self.header["scenario_id"], self.header["map_id"]
        costs = MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario / "Data", scenario, map_id).cost)
        policies, memories, last = {}, {}, {}
        exact = gaps = 0
        for row in self.rows:
            seat = row["seat"]
            policies.setdefault(seat, BaselinePolicy(costs))
            raw = typed_json.decode(row["observation"])
            decision = policies[seat].decide(Observation.from_raw(raw, Origin.ENGINE), seat, row["faction"],
                                             memories.get(seat, Memory()))
            memories[seat] = decision.memory
            exact += [dict(a) for a in decision.actions] == row["actions"] and digest(decision.trace) == row["trace_digest"]
            step = raw["time"]["cur_step"]
            if seat in last and last[seat] != 0 and step != last[seat] + 1:
                gaps += 1
            last[seat] = step
        self.assertEqual(exact, SLICE)
        self.assertEqual(gaps, 0)


@unittest.skipUnless(CAPTURE.is_file(), "the Sprint 2 captures are private (git-ignored)")
class RealCaptureSlice(unittest.TestCase):
    def test_seat_and_all_seeing_listings_agree_where_both_list(self):
        with CAPTURE.open("rb") as handle:
            samples = sorted(pickle.load(handle)["samples"], key=lambda s: s["k"])[:400]
        compared = 0
        for snap in samples:
            (_, entry), = snap["seats"].items()
            raw, everything = pickle.loads(entry["observation"]), pickle.loads(snap["global"])
            mine = ta.listings(raw)
            whole = ta.listings(everything)
            for unit_id, actions in mine.items():
                if unit_id in whole:
                    compared += 1
                    self.assertEqual({t: actions[t] for t in ta.T7_TYPES if t in actions},
                                     {t: whole[unit_id][t] for t in ta.T7_TYPES if t in whole[unit_id]})
        self.assertGreater(compared, 0)


@unittest.skipUnless((ROOT / GAME).is_file() and CAPTURE.is_file() and DATA.is_dir(),
                     "the study's private inputs are git-ignored")
class RealRegeneration(unittest.TestCase):
    """The public outputs rebuild byte for byte from the private inputs (several minutes)."""

    def run_check(self, name: str) -> str:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / name), "--check"], capture_output=True, text=True)
        return done.stdout.strip()

    def test_audit_and_candidates(self):
        self.assertEqual(self.run_check("t7_study.py"), "outputs identical")

    def test_posthoc(self):
        self.assertEqual(self.run_check("t7_posthoc.py"), "posthoc identical")


if __name__ == "__main__":
    unittest.main()
