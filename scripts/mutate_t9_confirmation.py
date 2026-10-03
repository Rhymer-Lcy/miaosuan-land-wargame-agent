"""Mutation test of the T9 confirmatory study's analysis and capture (``evaluation/t9_confirmation.py``) and of its
analysis script (``scripts/t9_confirmation_analysis.py``).

    python scripts/mutate_t9_confirmation.py [--check]

Applies each mutation to a temporary copy of ``src``, ``tests``, ``scripts``, ``evaluation`` and ``docs``, runs
``tests.test_t9_confirmation`` in a new process and records whether it failed (the mutation was killed). The
unmutated tests must pass first, and every mutation's original text must occur exactly once. Writes (or with
``--check`` compares) ``evaluation/t9-confirmation-1/mutation.json``; a surviving mutation is kept with its
documented reason in ``SURVIVORS``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "t9-confirmation-1" / "mutation.json"
TESTS = ("tests.test_t9_confirmation",)
MOD = "src/miaosuan_agent/evaluation/t9_confirmation.py"
SCR = "scripts/t9_confirmation_analysis.py"
COPIED = ("src", "tests", "scripts", "evaluation", "docs")
MUTATIONS = [
    (MOD, "margin sign inverted", 'return int(scores[f"{own}_total"]) - int(scores[f"{other}_total"])',
     'return int(scores[f"{other}_total"]) - int(scores[f"{own}_total"])'),
    (MOD, "C1 stratum added", 'Stratum("C1 seat average", -1.0,', 'Stratum("C1 seat average", 1.0,'),
    (MOD, "seat weights 1 instead of 1/2", 'Stratum("H1 red", 0.5, h1), Stratum("H2 blue", 0.5, h2)',
     'Stratum("H1 red", 1.0, h1), Stratum("H2 blue", 1.0, h2)'),
    (MOD, "H2 measured with the red margin", 'h2 = tuple(float(m["blue"]) for m in margins("H2"))',
     'h2 = tuple(float(m["red"]) for m in margins("H2"))'),
    (MOD, "C1 game value is its red margin", 'tuple((m["red"] + m["blue"]) / 2.0 for m in c1)',
     'tuple(float(m["red"]) for m in c1)'),
    (MOD, "inert seat swapped", 'side = "red" if condition == "C2" else "blue"\n\n    def margins(arm',
     'side = "blue" if condition == "C2" else "red"\n\n    def margins(arm'),
    (MOD, "interval limits from the wrong quantile", "low = point - q_high * se if se > 0 else point",
     "low = point - q_low * se if se > 0 else point"),
    (MOD, "resampling repeats one game", "s.values[stats.draw(rng, n)] for _ in range(n)", "s.values[0] for _ in range(n)"),
    (MOD, "standard error ignores n",
     "return math.sqrt(sum(s.weight ** 2 * _variance(s.values) / len(s.values) for s in strata))",
     "return math.sqrt(sum(s.weight ** 2 * _variance(s.values) for s in strata))"),
    (MOD, "a capped game counts as completed", 'completed=record.get("status") == "COMPLETED"',
     'completed=record.get("status") != "FAIL"'),
    (MOD, "margin identity ignored", '"ok": not not_completed and not identity and bool(games)',
     '"ok": not not_completed and bool(games)'),
    (MOD, "primary tested despite an integrity failure", 'testable = completion["ok"] and integrity["ok"]',
     'testable = completion["ok"]'),
    (MOD, "primary judged by its point estimate", 'primary.get("estimable") and primary["ci_low"] > 0)',
     'primary.get("estimable") and primary["estimate"] > 0)'),
    (MOD, "phase D threshold inclusive", 'a["estimate"] < -MATERIAL_MARGIN', 'a["estimate"] <= -MATERIAL_MARGIN'),
    (MOD, "phase B judged by the lower limit", 'a["ci_high"] < -MATERIAL_MARGIN', 'a["ci_low"] < -MATERIAL_MARGIN'),
    (MOD, "recovered sessions tolerated",
     'problems.append(f"session {session} was recovered (never closed by its game)")', "pass"),
    (MOD, "state continuity unchecked", 'if record.get("state") != previous.get("state"):', "if False:"),
    (MOD, "a game opened twice tolerated", "elif game in games:", "elif False:"),
    (MOD, "cap off by one", "if used > cap:", "if used > cap + 1:"),
    (MOD, "python version unchecked", 'if not str(record.get("python", "")).startswith("3.10."):', "if False:"),
    (MOD, "new refusal classes tolerated", "if tuple(c[:3]) not in known:", "if False:"),
    (MOD, "baseline-v2's classes in the phase not known",
     '                known |= {tuple(c[:3]) for c in seat["refusal_classes"]}', "                pass"),
    (MOD, "withheld runs never continue", "runs[1] = runs[1] + 1 if runs[0] == index - 1 else 1",
     "runs[1] = runs[1] + 1 if runs[0] == index else 1"),
    (MOD, "embarked units counted as removed",
     'self.left[f][obj_id] = "embarked" if obj_id in passengers else "removed"', 'self.left[f][obj_id] = "removed"'),
    (MOD, "departure never detected", "elif unit.cur_hex != start:", "elif False:"),
    (MOD, "objectives of the wrong side held", "held = [c for c in cities.values() if c.flag == color]",
     "held = [c for c in cities.values() if c.flag != color]"),
    (MOD, "waiting series not cross-checked", 'if mine["waiting"] != theirs["waiting_ground_units"][color]:', "if False:"),
    (MOD, "move orders not cross-checked", 'if mine is None or mine["moves"]["emitted"] != recorded:', "if False:"),
    (MOD, "step count not cross-checked", 'if capture.get("steps") != record.get("steps"):', "if False:"),
    (MOD, "later safety failures ignored",
     'elif any(safety[p] in ("SYSTEMIC_FAILURE", "ADVERSE_SIGNAL") for p in reached):', "elif False:"),
    (MOD, "no rotation of the round order", "shift = (repetition - 1) % len(base)", "shift = 0"),
    (MOD, "the last phase continues", 'decision = "STOP" if reasons else ("CONTINUE" if following else "COMPLETE")',
     'decision = "STOP" if reasons else "CONTINUE"'),
    (MOD, "latency flag ignores the maximum",
     'if max(values["p99"]) > LATENCY_FLAG_P99_MS or max(values["max"]) > LATENCY_FLAG_MAX_MS:',
     'if max(values["p99"]) > LATENCY_FLAG_P99_MS:'),
    (MOD, "refused re-assigned moves not attributed",
     "if kind == MOVE and code is not None and (actor, obj_id) in replaced:", "if False:"),
    (MOD, "reverted re-assignments still attributed", "replaced.pop(key, None)", "pass"),
    (MOD, "idle flag on the reversed difference", "mean_or_none(idle_t9) - mean_or_none(idle_v2) >= IDLE_FLAG_UNITS",
     "mean_or_none(idle_v2) - mean_or_none(idle_t9) >= IDLE_FLAG_UNITS"),
    (MOD, "integrity ignores the captures", '"ok": bool(ledger["ok"] and not identity_bad and not captures_bad)}',
     '"ok": bool(ledger["ok"] and not identity_bad)}'),
    (MOD, "contract errors not counted", 'totals["contract_errors"] += seat["contract_errors"]', "pass"),
    (MOD, "gate rejections read as a count", 'sum((seat.get("gate_rejections") or {}).values())',
     'len(seat.get("gate_rejections") or {})'),
    (SCR, "ledger read in full", "return list(ledger) if last is None else list(ledger[:last + 1])",
     "return list(ledger)"),
    (SCR, "capture digests not checked", "if hashlib.sha256(data).hexdigest() != expected:", "if False:"),
    (SCR, "session not compared with the ledger's", 'if audit["games"].get(entry["game_id"]) != record.get("session"):',
     "if False:"),
]
#: Mutations that survive by design, with the reason (none so far).
SURVIVORS: dict = {}


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def run(mutation: tuple) -> dict:
    path, name, old, new = mutation
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times in {path}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for part in COPIED:
            shutil.copytree(REPO_ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
        (root / path).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONPATH"] = str(root / "src")
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env, capture_output=True,
                              text=True, timeout=900)
    return {"file": path, "mutation": name, "killed": done.returncode != 0, "reason_if_surviving": SURVIVORS.get(name)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    baseline = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=REPO_ROOT, env=env, capture_output=True,
                              text=True)
    if baseline.returncode != 0 or "skipped" in baseline.stderr.splitlines()[-1]:
        print("the unmutated tests fail or skip; no mutation run\n" + baseline.stderr[-2000:])
        return 1
    results = [run(m) for m in MUTATIONS]
    payload = {"schema": "miaosuan-t9-confirmation-mutation/1", "tests": list(TESTS),
               "sources_sha256": {p: normalized_sha256(REPO_ROOT / p) for p in (MOD, SCR)},
               "tests_sha256": {"tests/test_t9_confirmation.py": normalized_sha256(REPO_ROOT / "tests" / "test_t9_confirmation.py")},
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
