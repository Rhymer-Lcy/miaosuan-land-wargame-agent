"""Mutation test of the Sprint 33 registered rules (``docs/SPRINT33_T7_B1_LIVE.md``).

    python scripts/mutate_s33.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, rebuilds the card there (so that the
card's pins of the frozen files never kill a mutation by themselves), first runs the test modules unmutated (they must
pass, or every later kill would be vacuous), then plants each defect, rebuilds the card in the copy, runs the tests in a
fresh process and records whether they failed. Every planted defect's original text must occur exactly once. The
defects cover the mechanism classification and its one correction (``evaluation/s33_mechanism.py``), the gate, harm
screen, ledger audit, structural checks, frames and disposition (``evaluation/s33_pilot.py``) and the observer's
action-fidelity, memory-chain, repeat and independent checks (``evaluation/s33_capture.py``). Record:
``evaluation/s33-t7-b1-live/mutation.json``, written before any engine session.
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
MECH = Path("src/miaosuan_agent/evaluation/s33_mechanism.py")
PILOT = Path("src/miaosuan_agent/evaluation/s33_pilot.py")
CAP = Path("src/miaosuan_agent/evaluation/s33_capture.py")
OUT = REPO_ROOT / "evaluation" / "s33-t7-b1-live" / "mutation.json"
CARD = Path("evaluation/s33-t7-b1-live-1/manifest.json")
TESTS = ("tests.test_s33_mechanism", "tests.test_s33_pilot")
MUTATIONS = [
    (MECH, "correction disabled (Sprint 32's deferred kept)",
     '    out = [a for a in result["adverse"] if a != "deferred"]', '    out = list(result["adverse"])'),
    (MECH, "indefinite deferral never adverse", "    if deferred_indefinite(order, frames):\n        out.insert",
     "    if False:\n        out.insert"),
    (MECH, "indefinite deadline widened",
     '    deadline = order.step + order.h0 + TOLERANCE\n    return any(row["step"] >= deadline',
     '    deadline = order.step + order.h0 + TOLERANCE + 1\n    return any(row["step"] >= deadline'),
    (MECH, "indefinite deferral without a path", 'row["step"] >= deadline and row["path"] > 0', 'row["step"] >= deadline'),
    (MECH, "inexact stop form accepted", '    return set(action) == {"actor", "obj_id", "type"} and',
     '    return set(action) >= {"actor", "obj_id", "type"} and'),
    (MECH, "refused stop read as clean", "                if m32.error_code(e) is None:\n                    out[\"stop_echoed_clean\"] = True",
     "                if True:\n                    out[\"stop_echoed_clean\"] = True"),
    (MECH, "accepted shot read from the listing", '             "SHOT_ACCEPTED": any(r["shot_accepted"] for r in q)}',
     '             "SHOT_ACCEPTED": any(r["fire_listed"] for r in q)}'),
    (MECH, "supported always at the accepted-shot level",
     '        return SUPPORTED_LEVELS[1] if "SHOT_ACCEPTED" in found else SUPPORTED_LEVELS[0]',
     "        return SUPPORTED_LEVELS[1]"),
    (MECH, "stop only always at the resumption level",
     '        return STOP_ONLY_LEVELS[1] if "MOVEMENT_RESUMED" in found else STOP_ONLY_LEVELS[0]',
     "        return STOP_ONLY_LEVELS[1]"),
    (MECH, "censored stops qualify",
     '    return [r for r in results if r["completed_step"] is not None and not r["adverse"] and not r["censored"]]',
     '    return [r for r in results if r["completed_step"] is not None and not r["adverse"]]'),
    (MECH, "resumption without a move order",
     '        if not any(a.get("obj_id") == order.unit and a.get("type") == MOVE for a in f.get("emitted") or ()):\n            continue',
     "        if False:\n            continue"),
    (MECH, "preserved verdict read from the correction",
     '    preserved = [dict(r, adverse=r["s32_adverse"]) for r in results]', "    preserved = list(results)"),
    (MECH, "blocked frames count moving units", "            out[\"blocked_frames\"] += any(s.path and s.path[0] == snap.hex and not m32.positive(s.speed)",
     "            out[\"blocked_frames\"] += any(s.path and s.path[0] == snap.hex"),
    (MECH, "baseline actions counted after the effect",
     "        if effect is not None and f[\"step\"] >= effect:\n            break",
     "        if False:\n            break"),
    (PILOT, "harm margin floor lowered", '    return {"occupy": p["occupy"], "margin_min": p["margin_minimum"]}',
     '    return {"occupy": p["occupy"], "margin_min": p["margin_minimum"] - 1}'),
    (PILOT, "harm occupy lowered", '    return {"occupy": p["occupy"], "margin_min": p["margin_minimum"]}',
     '    return {"occupy": p["occupy"] - 1, "margin_min": p["margin_minimum"]}'),
    (PILOT, "gate open after a closing verdict", '    elif not verdict["gate_open"]:', "    elif False:"),
    (PILOT, "gate ignores structural stops",
     '    if structural:\n        reasons.append(f"structural stops', '    if False:\n        reasons.append(f"structural stops'),
    (PILOT, "a third session expected", "EXPECTED_SESSIONS = (2801, 2802)", "EXPECTED_SESSIONS = (2801, 2802, 2803)"),
    (PILOT, "ledger ignores the candidate digest",
     '            if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:\n                problems["S2"]',
     '            if False:\n                problems["S2"]'),
    (PILOT, "ledger ignores the state chain",
     '            if previous is not None and record.get("state") != previous.get("state"):', "            if False:"),
    (PILOT, "ledger accepts a recovered session",
     '                problems["S2"].append(f"session {session} was recovered")', "                pass"),
    (PILOT, "repeated stops not structural",
     '                       ("independent_problems", "decisions with an independent-check finding"),\n'
     '                       ("repeated_stops", "decisions stop a unit a second time")):',
     '                       ("independent_problems", "decisions with an independent-check finding")):'),
    (PILOT, "observer stop count not compared",
     '    if timeline.get("stops_emitted") != int(by_type.get(str(cand.STOP), 0)):', "    if False:"),
    (PILOT, "timeline stop actions not compared", "    for kind in (cand.MOVE, cand.STOP):", "    for kind in (cand.MOVE,):"),
    (PILOT, "incomplete game accepted", '        if not g["completed"] or g.get("verdict") is None:',
     '        if g.get("verdict") is None:'),
    (PILOT, "structural game not mapped to invalid", "        if g[\"structural\"]:\n            v.update(",
     "        if False:\n            v.update("),
    (PILOT, "judge records dropped from the frames", '"judge": list(step.get("judge_new") or ()),', '"judge": [],'),
    (PILOT, "hex steps read off by one", 'h0=change["hex_steps"],', 'h0=change["hex_steps"] + 1,'),
    (PILOT, "harm screen not applied", "    verdict = mm.game_verdict(structural, results, runs, occupy if occupy is not None else -1, margin,\n"
                                       "                              harm_control(position))",
     "    verdict = mm.game_verdict(structural, results, runs, 10 ** 6, 10 ** 6,\n"
     "                              harm_control(position))"),
    (CAP, "changed baseline action accepted", "    if live[:len(base)] != base:", "    if False:"),
    (CAP, "unregistered additions accepted", "    if live[len(base):] != expected:", "    if False:"),
    (CAP, "add-on memory chain not checked", '            "addon_memory": addon_memory == tuple(expected_addon)}',
     '            "addon_memory": True}'),
    (CAP, "repeated stops not detected",
     "    return sorted(set(emitted) & set(stopped_before)) + sorted({u for u in emitted if list(emitted).count(u) > 1})",
     "    return []"),
    (CAP, "independent check ignored", '                independent = [] if restated == set(rebuilt["stops"]) else',
     "                independent = [] if True else"),
]


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def prepare(root: Path, replacements) -> None:
    for name in ("src", "tests", "scripts", "evaluation"):
        shutil.copytree(REPO_ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for source, text in replacements.items():
        (root / source).write_text(text, encoding="utf-8", newline="\n")
    (root / CARD).unlink()
    subprocess.run([sys.executable, str(root / "scripts" / "build_s33_card.py")], cwd=root, env=env_for(root),
                   capture_output=True, text=True, check=True, timeout=600)


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=1800)
    return done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]


def mutated(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    return {source: text.replace(old, new)}


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    names = [m[1] for m in MUTATIONS]
    if len(set(names)) != len(names):
        raise SystemExit("two mutations share a name")
    plans = [mutated(m) for m in MUTATIONS]
    passed, log = tests_pass({})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = []
    for (source, name, _, _), plan in zip(MUTATIONS, plans):
        ok, _ = tests_pass(plan)
        results.append({"mutation": name, "module": source.as_posix(), "killed": not ok})
        print(("killed   " if not ok else "SURVIVED ") + name, flush=True)
    sources = sorted({m[0] for m in MUTATIONS} | {Path(f"{t.replace('.', '/')}.py") for t in TESTS},
                     key=lambda p: p.as_posix())
    payload = {"schema": "miaosuan-s33-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "card_rebuilt_in_each_copy": True,
               "mutations": results, "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']}")
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
