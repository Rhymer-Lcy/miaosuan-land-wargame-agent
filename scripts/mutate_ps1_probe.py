"""Mutation test of the PS-1 probe: the P1 hook, the probe capture and the P1/P2 analyses.

    python scripts/mutate_ps1_probe.py [--check]

Applies each registered mutation to a temporary copy of the repository's ``src``, ``scripts`` and ``tests``, runs
``tests.test_ps1_probe_hook`` and ``tests.test_ps1_probe_analysis`` against it in a fresh process and records whether
the tests failed (the mutation was killed). Every mutation's original text must occur exactly once in its file.
Writes (or with ``--check`` compares) ``evaluation/ps1-engine-probe-1/mutation.json``; a surviving mutation is kept in
the output with its documented reason in ``SURVIVORS``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from miaosuan_agent.evaluation.ps1_probe import normalized_sha256  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "ps1-engine-probe-1" / "mutation.json"
TESTS = ("tests.test_ps1_probe_hook", "tests.test_ps1_probe_analysis")
HOOK = "src/miaosuan_agent/experiments/ps1_probe_hook.py"
ANALYSIS = "scripts/ps1_probe_analysis.py"
CAPTURE = "src/miaosuan_agent/evaluation/ps1_probe.py"
GAME = "src/miaosuan_agent/evaluation/game.py"
MUTATIONS = [
    (HOOK, "trigger without the stall condition",
     "return bool(dead) and all(pm.stalled(u, now, edges) for u in units if u.uid in dead), dead",
     "return bool(dead), dead"),
    (HOOK, "no speed verification", 'if op.fields.get("speed") != 0:', "if False:"),
    (HOOK, "stops repeated (the probe keeps watching)",
     'return ProbeState(phase="stopped", trigger_step=now, group=group, status=status), kept + stops, notes',
     'return ProbeState(phase="watching", trigger_step=now, group=group, status=status), kept + stops, notes'),
    (HOOK, "back-off without the move listed",
     "eligible = op is not None and MOVE in (listed.get(uid) or {}) and not (op.move_path or ())",
     "eligible = op is not None and not (op.move_path or ())"),
    (HOOK, "no destination capacity check", "if counts.get(path[-1], 0) + pending.get(path[-1], 0) >= pm.K:", "if False:"),
    (HOOK, "no path capacity check", "if any(counts.get(h, 0) >= pm.K for h in path):", "if False:"),
    (HOOK, "watch window widened", "WATCH_STEPS = 300", "WATCH_STEPS = 400"),
    (HOOK, "candidate actions not dropped",
     'kept, dropped = self._drop(actions, still | {m["obj_id"] for m in moves})', "kept, dropped = list(actions), []"),
    (HOOK, "orders not counted as progress", '        if action.get("type") == MOVE:\n                last[action["obj_id"]] = now',
     '        if action.get("type") == MOVE:\n                pass'),
    (HOOK, "hex changes not counted as progress", "if uid in hexes and hexes[uid] != op.cur_hex:",
     "if uid in hexes and hexes[uid] == op.cur_hex:"),
    (HOOK, "bypass allowed in the selection", 'RECOVERY_OPTION = "back-off"', 'RECOVERY_OPTION = "auto"'),
    (HOOK, "trace replaced before the trigger", "        if notes:\n            trace = replace(",
     "        if True:\n            trace = replace("),
    (CAPTURE, "event steps lose their snapshot", 'if self.events and self.events[-1]["k"] == index:', "if False:"),
    (GAME, "no pre-execution copy", '"submitted": copy.deepcopy(produced)', '"submitted": produced'),
    (ANALYSIS, "E3 window not applied", "not (lo <= c[\"L\"] <= hi) for c in placed)", "False for c in placed)"),
    (ANALYSIS, "transition timer not attributable",
     "attributable = ((effect is not None and t.b[effect][uid].hex != final_hex) or mtsrt_positive is not None)",
     "attributable = (effect is not None and t.b[effect][uid].hex != final_hex)"),
    (ANALYSIS, "an entry before the effect still counts as in place",
     "in_place = effect is not None and entered_before is None and t.b[effect][uid].hex == before_b.hex",
     "in_place = effect is not None"),
    (ANALYSIS, "E4 violations ignored", "if occ_all[h] > K:", "if occ_all[h] > K + 10:"),
    (ANALYSIS, "E4 restarts ignored", "elif (v, h) in waited:", "elif False:"),
    (ANALYSIS, "repeated feedback kept", "if pool[key] > 0:", "if False:"),
    (ANALYSIS, "refusals ignored", "return not any(code is not None for code in action.codes)", "return True"),
    (ANALYSIS, "premise ignores the states",
     'same_states = rec["state_steps"][:trigger_k + 1] == sprint2["state_steps"][:trigger_k + 1]', "same_states = True"),
    (ANALYSIS, "premise ignores the prediction", "and trigger_k == predicted_k\n", "\n"),
    (ANALYSIS, "minimum events lowered", "if n < pp.MIN_EVENTS:", "if n < 1:"),
    (ANALYSIS, "T-a ignores leaving units", "if start[nh] >= K and end[nh] >= K and not left:",
     "if start[nh] >= K and end[nh] >= K:"),
    (ANALYSIS, "T-b accepts an entry straight from waiting", 'elif final is None or not final["moving"]:',
     "elif final is None:"),
    (ANALYSIS, "arbitration judged by the highest indices", '"ascending": pool[:n] == entered,',
     '"ascending": sorted(pool[-n:]) == entered,'),
    (ANALYSIS, "restart delay judged in descending order", "ascending = restarts(v for v in cur if v < w)",
     "ascending = restarts(v for v in cur if v > w)"),
    (ANALYSIS, "F1 tolerance widened",
     'passed = (cmp["hex_sequences_differ"] == 0 and cmp["worst_step_offset"] <= pp.F1_TOLERANCE and not violations',
     'passed = (cmp["hex_sequences_differ"] == 0 and cmp["worst_step_offset"] <= 2 and not violations'),
    (ANALYSIS, "F1 ignores observed capacity", "and max(occupancy.values()) <= K and complete)", "and complete)"),
    (ANALYSIS, "F2 ignores unmatched occupations", "and len(occ_matched) == len(recorded_occupations) and not occ_extra)",
     "and len(occ_matched) == len(recorded_occupations))"),
    (ANALYSIS, "F2 ignores wrong destinations",
     "matched = [r for r in recorded_moves if any(r[1] == s[1] and r[2] == s[2] and abs(r[0] - s[0]) <= 1 for s in run.orders)]",
     "matched = [r for r in recorded_moves if any(r[1] == s[1] and abs(r[0] - s[0]) <= 1 for s in run.orders)]"),
    (ANALYSIS, "G3 passes without the certificate",
     'g3 = "PASS" if certificate is not None and certificate.get("verdict") == "feasible" else "UNRESOLVED"', 'g3 = "PASS"'),
    (ANALYSIS, "SHELVE on any E1 refutation",
     'if v.get("E1") == "REFUTED" and not any(o in p1.get("outcomes", {}) for o in ("accepted in place", "accepted after entry")):',
     'if v.get("E1") == "REFUTED":'),
    (ANALYSIS, "channel disagreement ignored",
     'same = {key: results["a"][i] == results["b"][i] for i, key in',
     'same = {key: True for i, key in'),
    (ANALYSIS, "removals not applied", "for uid in gone.get(s.step, ()):", "for uid in ():"),
    (ANALYSIS, "validator ignores removals", "occ[pos.pop(uid)] -= 1", "pos.pop(uid)"),
    (ANALYSIS, "validators not cross-checked", "        if frozen != problems:", "        if False:"),
    (ANALYSIS, "appearances not applied", "for uid in new.get(s.step, ()):", "for uid in ():"),
    (ANALYSIS, "E2 blocked by a refused unit",
     'elif effective and all(c["outcome"] == "accepted in place" for c in effective):',
     'elif effective and all(c["outcome"] == "accepted in place" for c in courses):'),
    (ANALYSIS, "stops not checked against the notes", "if submitted != noted:", "if False:"),
    (ANALYSIS, "missing snapshots tolerated", "if sorted(self.samples) != expected:", "if False:"),
    (ANALYSIS, "capture against record not checked", "if dict(mine) != recorded:", "if False:"),
]
#: Surviving mutations, each with the reason it is not killed (documented, not hidden).
SURVIVORS = {
    "trace replaced before the trigger": "equivalent: with no notes the replacement rebuilds the same diagnostics and "
                                         "emitted fields, so the trace and its digest are unchanged",
}


def run(mutation: tuple) -> dict:
    path, name, old, new = mutation
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times in {path}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for part in ("src", "scripts", "tests"):
            shutil.copytree(REPO_ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
        (root / path).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONPATH"] = str(root / "src")
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env, capture_output=True,
                              text=True, timeout=1200)
    return {"file": path, "mutation": name, "killed": done.returncode != 0,
            "reason_if_surviving": SURVIVORS.get(name)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = [run(m) for m in MUTATIONS]
    files = sorted({m[0] for m in MUTATIONS})
    payload = {"schema": "miaosuan-ps1-probe-mutation/1", "tests": list(TESTS),
               "sources_sha256": {f: normalized_sha256(REPO_ROOT / f) for f in files},
               "tests_sha256": {f"tests/{t.split('.')[-1]}.py": normalized_sha256(REPO_ROOT / "tests" / f"{t.split('.')[-1]}.py")
                                for t in TESTS},
               "mutations": results, "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("mutation results identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    surviving = [r["mutation"] for r in results if not r["killed"]]
    print(f"killed {payload['killed']} of {payload['total']}" + (f"; surviving: {surviving}" if surviving else ""))
    return 0 if all(r["killed"] or r["reason_if_surviving"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
