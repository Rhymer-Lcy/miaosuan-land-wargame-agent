"""Mutation test of the Sprint 36 agent, gates and study derivation (``docs/SPRINT36_TACTICAL_RECOVERY.md``).

    python scripts/mutate_s36.py [--check]

Sprint 35's procedure (``scripts/mutate_s35.py``): copy ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary
directory, rebuild the live card there when one exists (so its pins never kill a mutation by themselves), first run the
test modules unmutated (they must pass, or every kill would be vacuous), then plant each defect, run the tests in a fresh
process and record whether they failed. Every planted defect's original text must occur exactly once. Record:
``evaluation/s36-tactical-recovery/mutation.json``.
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
T = Path("src/miaosuan_agent/tactical")
E = Path("src/miaosuan_agent/evaluation")
OUT = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "mutation.json"
CARD = Path("evaluation/s36-tactical-live-1/manifest.json")
TESTS = ("tests.test_s36_refusals", "tests.test_s36_study", "tests.test_s36_tactical", "tests.test_s36_offline",
         "tests.test_s36_live", "tests.test_s36_gaps", "tests.test_s36_revision2")
MUTATIONS = [
    # refusal taxonomy and gate
    (E / "s36_refusals.py", "ErrorActionType not a contract refusal", '    if message == "ErrorActionType":',
     '    if message == "never":'),
    (E / "s36_refusals.py", "unlisted move classed as contract", '        return "B" if kind in MOVEMENT_TYPES else "A"',
     '        return "A"'),
    (E / "s36_refusals.py", "duplicate own shot classed as race", "        if isinstance(shots, int) and shots >= 2:",
     "        if isinstance(shots, int) and shots >= 3:"),
    (E / "s36_refusals.py", "echo mismatch ignored", '    if not summary["echo_matches"]:', "    if False:"),
    (E / "s36_refusals.py", "unexplained per game not counted", "    if e >= E_PER_GAME:", "    if e >= 99:"),
    (E / "s36_refusals.py", "unexplained over the study not counted", "    elif e and e + e_before >= E_PER_STUDY:",
     "    elif e and e >= E_PER_STUDY:"),
    (E / "s36_refusals.py", "systemic minimum ignored", "            if k < least:", "            if k < 1:"),
    (E / "s36_refusals.py", "small denominators use the tail", "            if n < MIN_DENOMINATOR:",
     "            if False:"),
    (E / "s36_refusals.py", "tail threshold inverted", "            if tail < alpha:", "            if tail > alpha:"),
    (E / "s36_refusals.py", "repeated actor ignored", '    if summary["repeat_actor_max"] >= repeat:', "    if False:"),
    (E / "s36_refusals.py", "race rate changed", '"race_fire": 0.00776733', '"race_fire": 0.0776733'),
    (E / "s36_refusals.py", "systemic alpha loosened", "SYSTEMIC_ALPHA = 1e-6", "SYSTEMIC_ALPHA = 1e-5"),
    # study derivation
    (E / "s36_study.py", "game stops ignored", "        found = rules.game_stop(facts, tuple(history))",
     "        found = None"),
    (E / "s36_study.py", "batch gates ignored", "        if rules.last_of_batch(position):", "        if False:"),
    (E / "s36_study.py", "games after a stop accepted",
     "            if stop is not None:\n                problems.append(", "            if False:\n                problems.append("),
    (E / "s36_study.py", "incomplete study reported complete", "    complete = stop is None and walked == len(schedule)",
     "    complete = stop is None"),
    (E / "s36_study.py", "restatement skips batch gates",
     '        if p == dict(rules.batches)[batch][-1]:', "        if False:"),
    (E / "s36_publish.py", "colliding literal left unchanged", "            out.append(_exponent(text[a:b]))",
     "            out.append(text[a:b])"),
    # tactical assessment
    (T / "assess.py", "static filter keeps every enemy",
     "    return post is not None and post[1] == threat.hex and step - post[2] >= minimum",
     "    return False"),
    (T / "assess.py", "static enemies in a zone filtered too", "                 if t.hex in zones or not is_static(",
     "                 if not is_static("),
    (T / "assess.py", "opportunity ignores remembered enemies",
     "for t in threats if t.confidence > 0), default=float(\"inf\"))",
     "for t in threats if t.visible), default=float(\"inf\"))"),
    (T / "assess.py", "race margin ignored", "    if ours is None or ours + margin > contest:",
     "    if ours is None or ours > contest + 1000:"),
    (T / "assess.py", "valuable holder kept", "    return unit.value <= limit", "    return True"),
    (T / "assess.py", "withdrawal on memory alone",
     "share >= tcfg.withdraw_visible_share and a.enemy_eta >= tcfg.withdraw_lead:",
     "a.enemy_eta >= tcfg.withdraw_lead:"),
    (T / "assess.py", "withdrawal under fire",
     "share >= tcfg.withdraw_visible_share and a.enemy_eta >= tcfg.withdraw_lead:",
     "share >= tcfg.withdraw_visible_share:"),
    (T / "assess.py", "end window ignored", "    if world.remaining <= tcfg.end_window:", "    if False:"),
    (T / "assess.py", "fallback hex not farther", "< now + tcfg.safe_margin:", "< now:"),
    (T / "assess.py", "fallback hex inside a zone", "        if h == unit.hex or h in zones or h in world.roadblocks:",
     "        if h == unit.hex or h in world.roadblocks:"),
    (T / "assess.py", "empty zone gets no delaying place",
     "        return replace(a, places=1, deadline=deadline, keep=(), withdraw=(), note=DELAY_ROLE_NOTE)",
     "        return replace(a, keep=(), withdraw=())"),
    # allocation and policy
    (T / "allocator.py", "delaying place open to valuable units",
     "                if pl.role == DELAY_PLACE and not is_cheap(unit, limit):", "                if False:"),
    (T / "allocator.py", "counterattack window ignored",
     "            recent = {h for h, step in self.lost.items() if world.step - step <= t.counterattack_window}",
     "            recent = set(self.lost)"),
    (T / "policy.py", "guard drops nothing", "            if target is not None:\n                dropped[unit.obj_id]",
     "            if False:\n                dropped[unit.obj_id]"),
    (T / "policy.py", "guard retention off", "            if home is not None and end not in zone_of[home]:",
     "            if False:"),
    (T / "policy.py", "guard cheap exemption off", "            if A.is_cheap(unit, limit):\n                kept.append(action)",
     "            if False:\n                kept.append(action)"),
    (T / "policy.py", "guard withdrawals not added", "                    added.append({", "                    continue\n                    added.append({"),
    (T / "memory.py", "posts never reset on a move", "        since = prior[2] if prior is not None and prior[1] == hex_ else step",
     "        since = prior[2] if prior is not None else step"),
    (T / "memory.py", "posts unbounded", "    kept = sorted(latest.values(), key=lambda p: (-p[3], p[0]))[:MAX_POSTS]",
     "    kept = sorted(latest.values(), key=lambda p: (-p[3], p[0]))"),
    # live rules and offline rules
    (E / "s36_live.py", "control failures count as agent failures",
     '        return ("agent" if facts.get("tag") == "s36" else "structural"), policy', '        return "agent", policy'),
    (E / "s36_live.py", "harm read on control games", '    if facts.get("tag") != "s36" or facts.get("batch") not in',
     '    if facts.get("batch") not in'),
    (E / "s36_live.py", "A1 comparison reads every batch",
     '        if f["batch"] in batches and f["tag"] in ("s36", "s34") and f.get("share") is not None:',
     '        if f["tag"] in ("s36", "s34") and f.get("share") is not None:'),
    (E / "s36_live.py", "early futility ignored", "        if cmp_[\"dbar\"] is not None and cmp_[\"dbar\"] <= EARLY_FUTILITY:",
     "        if False:"),
    (E / "s36_live.py", "only suppressed waits read as deadlock", "        if cause != FULL:", "        if cause == FULL:"),
    (E / "s36_live.py", "share sd changed", "SHARE_SD = 0.4187", "SHARE_SD = 0.5187"),
    (E / "s36_offline.py", "least change not first", 'CANDIDATES = ("TC", "TA", "TB")', 'CANDIDATES = ("TA", "TC", "TB")'),
    (E / "s36_offline.py", "movement floor loosened", "MOVEMENT_FLOOR = 0.95", "MOVEMENT_FLOOR = 0.9"),
    (E / "s36_offline.py", "equivalence not required", '    gate("G10", all(v == 0 for v in eq.values()) and len(eq) == 2, dict(eq))',
     '    gate("G10", True, dict(eq))'),
    (E / "s36_capture.py", "full hex threshold changed", "    if next_own >= 4:", "    if next_own >= 3:"),
    (T / "config.py", "counterattack bonus by default (revision 1)", "    counterattack_bonus: float = 0.0",
     "    counterattack_bonus: float = 0.25"),
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
    if (root / CARD).exists():
        (root / CARD).unlink()
        subprocess.run([sys.executable, str(root / "scripts" / "build_s36_card.py")], cwd=root, env=env_for(root),
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
    parser.add_argument("--only", nargs="*", help="run only the named mutations (development)")
    args = parser.parse_args()
    names = [m[1] for m in MUTATIONS]
    if len(set(names)) != len(names):
        raise SystemExit("two mutations share a name")
    chosen = [m for m in MUTATIONS if not args.only or m[1] in args.only]
    plans = [mutated(m) for m in chosen]
    passed, log = tests_pass({})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = []
    for (source, name, _, _), plan in zip(chosen, plans):
        ok, _ = tests_pass(plan)
        results.append({"mutation": name, "module": source.as_posix(), "killed": not ok})
        print(("killed   " if not ok else "SURVIVED ") + name, flush=True)
    if args.only:
        return 0
    sources = sorted({m[0] for m in MUTATIONS} | {Path(f"{t.replace('.', '/')}.py") for t in TESTS},
                     key=lambda p: p.as_posix())
    payload = {"schema": "miaosuan-s36-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
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
