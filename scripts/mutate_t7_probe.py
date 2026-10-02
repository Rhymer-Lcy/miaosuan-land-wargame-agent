"""Mutation test of the T7 mechanism probe: the candidate wrapper, the capture, the game loop's pre-execution copy,
the visibility model and the registered analyses.

    python scripts/mutate_t7_probe.py [--check] [--workers N]

Applies each mutation to a temporary copy of the repository's ``src``, ``scripts`` and ``tests``, runs the public T7
probe tests against it in a fresh process and records whether they failed (the mutation was killed). Every
mutation's original text must occur exactly once in its file, and the unmutated tests must pass first. Writes (or
with ``--check`` compares) ``evaluation/t7-mechanism-probe-1/mutation.json``; a surviving mutation is kept with its
documented reason in ``SURVIVORS``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "t7-mechanism-probe-1" / "mutation.json"
TESTS = ("tests.test_t7_concealment", "tests.test_t7_visibility", "tests.test_t7_probe_analysis")
CAND = "src/miaosuan_agent/experiments/t7_concealment.py"
PROBE = "src/miaosuan_agent/evaluation/t7_probe.py"
METRICS = "src/miaosuan_agent/evaluation/t7_probe_metrics.py"
ENDPOINTS = "src/miaosuan_agent/evaluation/t7_probe_endpoints.py"
VIS = "src/miaosuan_agent/evaluation/t7_visibility.py"
GAME = "src/miaosuan_agent/evaluation/game.py"
ANALYSIS = "scripts/t7_probe_analysis.py"
MUTATIONS = [
    # the candidate wrapper
    (CAND, "baseline digest of the composite trace", "baseline_trace_sha256=digest(base),",
     "baseline_trace_sha256=digest(base)[::-1],"),
    (CAND, "added orders not recorded", "added=tuple((int(a[\"obj_id\"]), int(a[\"target_state\"])) for a in added),",
     "added=(),"),
    (CAND, "emitted list from the baseline only", "values.update(policy=CANDIDATE_ID, emitted=tuple((int(a[\"type\"]), "
     "a.get(\"obj_id\")) for a in actions))", "values.update(policy=CANDIDATE_ID)"),
    (CAND, "fallback keeps no baseline action", "return Decision(tuple(base.actions), trace, replace(memory, "
     "baseline=base.memory))", "return Decision((), trace, replace(memory, baseline=base.memory))"),
    (CAND, "errors not recorded", "error = f\"{type(exc).__name__}: {exc}\"[:300]", "error = None"),
    # the capture and the game loop
    (PROBE, "copies taken after the step", "submitted.append({\"seat\": decision[\"seat\"], \"faction\": "
     "decision[\"faction\"], \"j\": j,\n                                  \"action\": rd.plain(action)})",
     "submitted.append({\"seat\": decision[\"seat\"], \"faction\": decision[\"faction\"], \"j\": j,\n"
     "                                  \"action\": rd.plain(decision[\"actions\"][j])})"),
    (PROBE, "no snapshot at decision 0", "if index == 0 or (self.events and self.events[-1][\"k\"] == index):",
     "if self.events and self.events[-1][\"k\"] == index:"),
    (PROBE, "no final state", "out[\"final\"] = self._final()", "out[\"final\"] = None"),
    (PROBE, "t7 blocks dropped", "entry[\"t7\"] = blocks", "entry[\"t7\"] = {}"),
    (GAME, "pre-execution copy not copied", "\"submitted\": copy.deepcopy(produced)", "\"submitted\": produced"),
    # data layer and integrity
    (METRICS, "concealed ignores the timer", "return self.move_state == CONCEAL and _num(self.timers[0]) == 0",
     "return self.move_state == CONCEAL"),
    (METRICS, "transition reads one timer only", "return any((_num(t) or 0) > 0 for t in self.timers)",
     "return (_num(self.timers[0]) or 0) > 0"),
    (METRICS, "fresh feedback keeps repeats", "if previous is not None and step[\"cur_step\"] == previous[\"cur_step\"]:",
     "if False:"),
    (METRICS, "echo match ignores target_state", "for key in (\"target_state\", \"target_obj_id\", \"weapon_id\"):",
     "for key in (\"target_obj_id\", \"weapon_id\"):"),
    (METRICS, "three-way: record count unchecked", "if not blocks == copies == recorded or other6:",
     "if not blocks == copies or other6:"),
    (METRICS, "three-way: missing blocks tolerated", "    if missing:\n        raise AnalysisRefused(f\"I3: no t7 trace block",
     "    if False:\n        raise AnalysisRefused(f\"I3: no t7 trace block"),
    (METRICS, "channels: listings not compared", "\"speed\", \"blood\", \"on_board\", \"path\", \"types\", \"states\")",
     "\"speed\", \"blood\", \"on_board\", \"path\")"),
    (METRICS, "capture: missing snapshots tolerated", "    if missing:\n        problems.append(f\"no snapshot at",
     "    if False:\n        problems.append(f\"no snapshot at"),
    (METRICS, "record: dirty harness tolerated", "if harness.get(\"dirty\"):", "if False:"),
    # E2 and its reconstruction
    (ENDPOINTS, "window one step longer", "for s in range(s0 + 1, s0 + WINDOW + 1):",
     "for s in range(s0 + 1, s0 + WINDOW + 2):"),
    (ENDPOINTS, "completion on move_state alone", "            if unit.concealed:\n                completion = s",
     "            if unit.move_state == CONCEAL:\n                completion = s"),
    (ENDPOINTS, "any timer start accepted", "timer_ok = any(s0 + d == timer_start for d in tp.TIMER_START)",
     "timer_ok = True"),
    (ENDPOINTS, "censoring never applies", "elif end < s0 + WINDOW:", "elif False:"),
    (ENDPOINTS, "suppression not an interrupter", "        if (_num(unit.keep) or 0) > 0:\n            return k, \"suppressed\"",
     "        if False:\n            return k, \"suppressed\""),
    (ENDPOINTS, "firing not an interrupter", "if _judged(game, step, o.unit):", "if False:"),
    (ENDPOINTS, "reconstruction unchecked", "if (timer_a, record[\"completion\"]) != (timer_b, completion_b):", "if False:"),
    (ENDPOINTS, "E2: anomalies not refuting", "elif any(counts[x] for x in (\"COMPLETED_TIMER_ANOMALY\", \"LATE\", \"NOT_COMPLETED\")):",
     "elif any(counts[x] for x in (\"LATE\", \"NOT_COMPLETED\")):"),
    (ENDPOINTS, "E1: missing echoes accepted", "verdict = REFUTED if errors else INCONCLUSIVE if odd else SUPPORTED",
     "verdict = REFUTED if errors else SUPPORTED"),
    # S2 and E3
    (ENDPOINTS, "S2: flag_force_stop ignored", "if unit.flag_force_stop == 1:", "if False:"),
    (ENDPOINTS, "S2: transient threshold zero", "(violations if length > TRANSIENT else transients).append(item)",
     "(violations if length > 0 else transients).append(item)"),
    (ENDPOINTS, "E3a: transient threshold two", "(losses if length > TRANSIENT else transients).append(item)",
     "(losses if length > 2 else transients).append(item)"),
    (ENDPOINTS, "E3a: weapon lock not required", "before = set(snaps[p[\"order_k\"]].units[p[\"unit\"]].types or ()) - {CHANGE_STATE}",
     "before = set(snaps[p[\"order_k\"]].units[p[\"unit\"]].types or ()) - {CHANGE_STATE, 11}"),
    (ENDPOINTS, "E3b: exit not required", "exited = nxt is not None and nxt.move_state != CONCEAL", "exited = True"),
    (ENDPOINTS, "E5: executed counted as deferred", "elif executed and remaining <= 1:", "elif executed:"),
    (ENDPOINTS, "E5: suppression always consistent", "            if (_num(unit.keep) or 0) > 0:\n                events.append({\"order_k\": o.k, \"k\": k, \"unit\": o.unit, \"event\": \"suppressed\",\n"
     "                               \"transition_completed\": completed, \"consistent\": not completed})",
     "            if (_num(unit.keep) or 0) > 0:\n                events.append({\"order_k\": o.k, \"k\": k, \"unit\": o.unit, \"event\": \"suppressed\",\n"
     "                               \"transition_completed\": completed, \"consistent\": True})"),
    # S3, E6, S4
    (ENDPOINTS, "S3: state digests unchecked", "if rec[\"state_steps\"][k] != rrec[\"state_steps\"][k]:", "if False:"),
    (ENDPOINTS, "S3: later actions unchecked", "            if mine != expected:\n                after.append({\"k\": k, \"what\": \"baseline-v2 actions differ\"",
     "            if False:\n                after.append({\"k\": k, \"what\": \"baseline-v2 actions differ\""),
    (ENDPOINTS, "E6: positions unchecked", "        if pos_a != pos_b:", "        if False:"),
    (ENDPOINTS, "S4: refusal classes unchecked", "            if new:\n                problems.append(", "            if False:\n                problems.append("),
    # E4
    (ENDPOINTS, "E4: channels not compared", "if [r[:5] + r[6:] for r in a] != [r[:5] + r[6:] for r in b]:", "if False:"),
    (ENDPOINTS, "E4: refutation needs all listed", "elif disc[\"listed\"] / n >= tp.REFUTE_SHARE:", "elif disc[\"listed\"] == n:"),
    (ENDPOINTS, "E4: matched band unchecked", "and matched_listed / matched >= tp.MATCHED_AGREEMENT)", "and True)"),
    (ENDPOINTS, "E4: matched minimum unchecked", "and matched >= tp.MATCHED_MINIMUM", "and True"),
    (ENDPOINTS, "E4: concealed units as control", "            if unit.concealed:\n                near = min(",
     "            if False:\n                near = min("),
    (VIS, "no concealment halving band", "elif d <= full / 2 - 0.5 or (full / 2).is_integer() and d <= full / 2:",
     "elif d <= full:"),
    (VIS, "terrain halving ignored", "reach = full / 2 if m.covered(x) else full", "reach = full"),
    (VIS, "aerial observers on the ground mode", "if not m.los(AIR_MODE if is_aerial(observer) else GROUND_MODE, o, x):",
     "if not m.los(GROUND_MODE, o, x):"),
    (VIS, "lower vehicle exception dropped", "    if any(p.band in (INSIDE, BETWEEN, BOUNDARY) and p.lower_vehicle for p in pairs):\n        return EXCEPTION_VISIBLE, pairs\n",
     ""),
    (VIS, "boundary folded into the band", "elif not (full / 2).is_integer() and d == int(full / 2) + 1:", "elif False:"),
    # gates and disposition
    (ENDPOINTS, "gate: S3 not required", "\"S3\": pa[\"S3\"][\"verdict\"] == PASS, \"E2\": pa[\"E2\"][\"verdict\"] == SUPPORTED,",
     "\"S3\": True, \"E2\": pa[\"E2\"][\"verdict\"] == SUPPORTED,"),
    (ENDPOINTS, "stop branch: S4 not required", "\"S4\": pb1[\"S4\"][\"verdict\"] == PASS,", "\"S4\": True,"),
    (ENDPOINTS, "disposition: E4a refutation not shelving", "if safety_fail or e[\"E1\"] == REFUTED or e[\"E3b\"] == REFUTED or e[\"E4a\"] == REFUTED or (",
     "if safety_fail or e[\"E1\"] == REFUTED or e[\"E3b\"] == REFUTED or ("),
    (ENDPOINTS, "pooling: inconclusive hidden", "    if INCONCLUSIVE in present:\n        return INCONCLUSIVE\n", ""),
    # the driver
    (ANALYSIS, "pool predicate not compared", "if found != expected and \"I5\" not in relax:", "if False:"),
    (ANALYSIS, "I1 problems tolerated", "    if i1 and \"I1\" not in relax:", "    if False:"),
    (ANALYSIS, "re-decided actions not compared",
     "            if [dict(a) for a in d.actions] != tm.submitted(self.game, seat, k):", "            if False:"),
]
#: Mutations that survive, with the reason (equivalent or a documented residual weakness).
SURVIVORS: dict = {
    "three-way: record count unchecked": "equivalent: the per-seat comparison of the pre-execution copies by type with "
                                         "the record's actions_by_type, which follows, enforces the same equality",
}


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env, capture_output=True,
                              text=True, timeout=1800)
    return {"file": path, "mutation": name, "killed": done.returncode != 0, "reason_if_surviving": SURVIVORS.get(name)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    for path, name, old, _ in MUTATIONS:
        if (REPO_ROOT / path).read_text(encoding="utf-8").count(old) != 1:
            raise SystemExit(f"mutation {name!r}: original text does not occur exactly once in {path}")
    baseline = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=REPO_ROOT, capture_output=True, text=True)
    if baseline.returncode != 0:
        print("the unmutated tests fail; no mutation run")
        return 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, MUTATIONS))
    files = sorted({m[0] for m in MUTATIONS})
    payload = {"schema": "miaosuan-t7-probe-mutation/1", "tests": list(TESTS),
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
