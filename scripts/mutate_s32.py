"""Mutation test of the Sprint 32 rules (``docs/SPRINT32_T7_B1_PREFLIGHT.md``).

    python scripts/mutate_s32.py --phase preflight|mechanism [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the phase's test modules
unmutated (they must pass, or every later kill would be vacuous), then plants each defect of the phase, runs the tests
in a fresh process and records whether they failed. Every planted defect's original text must occur exactly once.
Phase ``preflight``: the candidate (``experiments/t7_b1_stop_engage.py``) and the preflight rules
(``evaluation/s32_preflight.py``), record ``evaluation/s32-t7-b1/mutation-preflight.json``, written before the
preflight runs. Phase ``mechanism``: the proposed mechanism-check rules (``evaluation/s32_mechanism.py``), record
``evaluation/s32-t7-b1/mutation-mechanism.json``.
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
CAND = Path("src/miaosuan_agent/experiments/t7_b1_stop_engage.py")
PRE = Path("src/miaosuan_agent/evaluation/s32_preflight.py")
MECH = Path("src/miaosuan_agent/evaluation/s32_mechanism.py")
OUT = REPO_ROOT / "evaluation" / "s32-t7-b1"
PHASES = {
    "preflight": {
        "tests": ("tests.test_t7_b1_stop_engage", "tests.test_s32_preflight"),
        "out": OUT / "mutation-preflight.json",
        "mutations": [
            (CAND, "tank main guns admitted", "            or TANK_GUNS & set(weapons):", "            or False:"),
            (CAND, "move-and-fire field not required 0", '    if as_int(u.get("A1")) != 0 or', "    if False or"),
            (CAND, "waiting units admitted", '    if u["speed"] <= 0:', '    if u["speed"] < 0:'),
            (CAND, "progress upper bound dropped", 'not 0 <= u["cur_pos"] < 1', 'not 0 <= u["cur_pos"]'),
            (CAND, "parameterised stop listing admitted",
             "    if len(keys) != 1 or per[keys[0]] is not None:\n        return None",
             "    if False:\n        return None"),
            (CAND, "stop flag not required 0", 'ZERO_FIELDS = ("stop", "move_to_stop_remain_time",',
             'ZERO_FIELDS = ("move_to_stop_remain_time",'),
            (CAND, "deferred stop admitted", '"move_to_stop_remain_time", "flag_force_stop", "change_state_remain_time",',
             '"move_to_stop_remain_time", "change_state_remain_time",'),
            (CAND, "suppressed units admitted", '"weapon_unfold_time", "keep", "move_state", "on_board")',
             '"weapon_unfold_time", "move_state", "on_board")'),
            (CAND, "locked weapons admitted",
             '            or not (is_number(u.get("weapon_unfold_state")) and u.get("weapon_unfold_state") == 1):',
             "            or False:"),
            (CAND, "last hex admitted", "    if len(path) < 2:", "    if len(path) < 1:"),
            (CAND, "baseline-v2 action overridden", "    if uid in base_units:\n        return UnitCheck(uid, LEVELS[6])",
             "    if False:\n        return UnitCheck(uid, LEVELS[6])"),
            (CAND, "repeated stops allowed", "    if uid in stopped:\n        return UnitCheck(uid, LEVELS[7])",
             "    if False:\n        return UnitCheck(uid, LEVELS[7])"),
            (CAND, "unit visibility ignored", '        if e["obj_id"] not in seen_ids:\n            continue',
             "        if False:\n            continue"),
            (CAND, "range measured from the current hex", "        d = hex_distance(nxt, there)",
             '        d = hex_distance(u["cur_hex"], there)'),
            (CAND, "range bound off by one", "        if d <= reach and", "        if d <= reach + 1 and"),
            (CAND, "room limit widened", "ROOM_OTHERS = 2\n", "ROOM_OTHERS = 3\n"),
            (CAND, "routed units not counted",
             '        if o.get("cur_hex") == nxt or (isinstance(route, (list, tuple)) and nxt in route):',
             '        if o.get("cur_hex") == nxt:'),
            (CAND, "baseline-v2 moves not counted", "        if unit != uid and nxt in route:\n            others.add(unit)",
             "        if False:\n            others.add(unit)"),
            (CAND, "transition left out of the time check",
             "    if cur_step + steps + TRANSITION + END_MARGIN > max_step:",
             "    if cur_step + steps + END_MARGIN > max_step:"),
            (CAND, "hex steps not rounded up",
             '    return int(math.ceil(round((1.0 - unit["cur_pos"]) / unit["speed"], 6)))',
             '    return int(round((1.0 - unit["cur_pos"]) / unit["speed"], 6))'),
            (CAND, "memory not updated", "    new_memory.update({unit: cur_step for unit in stops})", "    pass"),
            (CAND, "own check tolerates a changed baseline action",
             '    if [dict(a) for a in actions[:len(base)]] != [dict(a) for a in base]:\n        raise ValueError',
             "    if False:\n        raise ValueError"),
            (CAND, "own check tolerates an unlisted stop",
             '        if stop_listed(unit_listing(raw, action["obj_id"])) is not True:', "        if False:"),
            (CAND, "uncontrolled units admitted",
             "    if u.get(\"type\") not in GROUND or controlled is None or uid not in controlled:",
             "    if u.get(\"type\") not in GROUND:"),
            (CAND, "own units read as targets",
             '    enemies = [u for u in operators if u.get("color") != faction and u.get("type") in GROUND]',
             '    enemies = [u for u in operators if u.get("type") in GROUND]'),
            (CAND, "stops placed before baseline-v2's actions", "    return StopResult(base + added,",
             "    return StopResult(added + base,"),
            (PRE, "independent findings ignored", '    if any(s["independent_check_findings"] for s in sides):',
             "    if False:"),
            (PRE, "H0 first divergence without a supported prefix",
             '    valid = first is not None and (population in GENUINE or first_difference is None or first_difference >= first["k"])',
             "    valid = first is not None"),
            (PRE, "episodes closed at every decision",
             "            if unit not in eligible:\n                episodes.append(open_runs.pop(unit))",
             "            if True:\n                episodes.append(open_runs.pop(unit))"),
            (PRE, "configuration status from any population",
             '    group = [s for s in sides if s["population"] == "HI" and s["scenario"] == scenario',
             '    group = [s for s in sides if s["scenario"] == scenario'),
            (PRE, "PASS with one proposed configuration", "    if all(v == CONFIG_STATUS[0] for v in proposed.values()):",
             "    if any(v == CONFIG_STATUS[0] for v in proposed.values()):"),
            (PRE, "alternative with one seat colour", '    if alternatives["red"] and alternatives["blue"]:',
             '    if alternatives["red"] or alternatives["blue"]:'),
            (PRE, "restated room limit widened", "        if len(crowd) > 2:", "        if len(crowd) > 3:"),
            (PRE, "restated time margin narrowed", "        if step + steps + 75 + 3 > end:",
             "        if step + steps + 75 + 2 > end:"),
            (PRE, "restated visibility ignored", 'e.get("obj_id") not in seen', 'e.get("obj_id") is None'),
            (PRE, "witness ignores the range",
             "                  and t7v.hex_distance(nxt, f[\"enemy\"][target]) <= reach for f in window)",
             "                  for f in window)"),
            (PRE, "window without the transition",
             '    end_step = stop["step"] + stop["hex_steps"] + cand.TRANSITION + cand.END_MARGIN',
             '    end_step = stop["step"] + stop["hex_steps"] + cand.END_MARGIN'),
            (PRE, "stops counted without the candidate's memory",
             "        live = cand.decide(raw, seat, faction, base, memory)",
             "        live = cand.decide(raw, seat, faction, base, ())"),
        ],
    },
    "mechanism": {
        "tests": ("tests.test_s32_mechanism",),
        "out": OUT / "mutation-mechanism.json",
        "mutations": [
            (MECH, "rejection ignored",
             '        if any(echoes(e, order.unit, STOP) and error_code(e) is not None for e in f.get("feedback") or ()):',
             "        if False:"),
            (MECH, "deferral ignored",
             '    if any(order.unit in f["units"] and f["units"][order.unit].force == 1 for f in later):', "    if False:"),
            (MECH, "clearing deadline widened", "    deadline = order.step + order.h0 + TOLERANCE\n",
             "    deadline = order.step + order.h0 + TOLERANCE + 1\n"),
            (MECH, "overrun tolerated", '    if out["where"] == "elsewhere":\n        out["adverse"].append("overrun")',
             '    if False:\n        out["adverse"].append("overrun")'),
            (MECH, "transition start not required", "    if not (positive(snap.timer) and snap.stop == 0):",
             "    if False:"),
            (MECH, "transition window opened early",
             '    low, high = fc["step"] + cand.TRANSITION - TOLERANCE, fc["step"] + cand.TRANSITION + TOLERANCE',
             '    low, high = fc["step"] + cand.TRANSITION - TOLERANCE - 1, fc["step"] + cand.TRANSITION + TOLERANCE'),
            (MECH, "transition window closed late",
             '    low, high = fc["step"] + cand.TRANSITION - TOLERANCE, fc["step"] + cand.TRANSITION + TOLERANCE',
             '    low, high = fc["step"] + cand.TRANSITION - TOLERANCE, fc["step"] + cand.TRANSITION + TOLERANCE + 1'),
            (MECH, "movement re-listing not required", "    if not listed or MOVE not in listed:", "    if not listed:"),
            (MECH, "firing opportunity without range", "and cand.hex_distance(snap.hex, there) <= reach:",
             "and cand.hex_distance(snap.hex, there) <= reach + 10:"),
            (MECH, "shot listing read from movement", '    out["fire_listed"] = SHOOT in listed',
             '    out["fire_listed"] = MOVE in listed'),
            (MECH, "shot accepted without a judgement", "            accepted = accepted or (clean and judged)",
             "            accepted = accepted or clean"),
            (MECH, "suppression not censored", '    if positive(fd["units"][order.unit].keep):', "    if False:"),
            (MECH, "deadlock without a full hex", "run = run + 1 if (blocked and crowd >= cand.STACK_LIMIT) else 0",
             "run = run + 1 if blocked else 0"),
            (MECH, "deadlock run lengthened", "DEADLOCK_RUN = 300\n", "DEADLOCK_RUN = 301\n"),
            (MECH, "harm margin widened", "HARM_MARGIN = 50\n", "HARM_MARGIN = 51\n"),
            (MECH, "occupy harm ignored", '    if occupy < control["occupy"]:', "    if False:"),
            (MECH, "not engaging ignored", '    elif evaluable and not any(r["fire_listed"] for r in evaluable):',
             "    elif False:"),
            (MECH, "censored stops counted as completed",
             'and not r["adverse"] and not r["censored"]]', 'and not r["adverse"]]'),
            (MECH, "gate open after harm", '"gate_open": verdict in GAME_VERDICTS[4:]',
             '"gate_open": verdict in GAME_VERDICTS[2:]'),
            (MECH, "game behind a closed gate accepted", '            or any(not g["gate_open"] for g in games[:-1])',
             "            or False"),
            (MECH, "incomplete check accepted",
             "    if len(games) < planned:\n        return {\"disposition\": DISPOSITIONS[0]",
             "    if False:\n        return {\"disposition\": DISPOSITIONS[0]"),
            (MECH, "stop only read as supported", "    if GAME_VERDICTS[6] in verdicts:",
             "    if GAME_VERDICTS[6] in verdicts or GAME_VERDICTS[5] in verdicts:"),
            (MECH, "lost unit not censored",
             '            out["censored"] = "lost before the path cleared"\n            return out',
             "            pass"),
        ],
    },
}


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


def tests_pass(tests, replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *tests], cwd=root, env=env_for(root),
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
    parser.add_argument("--phase", required=True, choices=sorted(PHASES))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    phase = PHASES[args.phase]
    mutations, tests = phase["mutations"], phase["tests"]
    names = [m[1] for m in mutations]
    if len(set(names)) != len(names):
        raise SystemExit("two mutations share a name")
    plans = [mutated(m) for m in mutations]
    passed, log = tests_pass(tests, {})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = []
    for (source, name, _, _), plan in zip(mutations, plans):
        ok, _ = tests_pass(tests, plan)
        results.append({"mutation": name, "module": source.as_posix(), "killed": not ok})
    sources = sorted({m[0] for m in mutations} | {Path(f"{t.replace('.', '/')}.py") for t in tests},
                     key=lambda p: p.as_posix())
    payload = {"schema": "miaosuan-s32-mutation/1", "phase": args.phase,
               "sources": {p.as_posix(): digest(p) for p in sources}, "tests": list(tests),
               "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    out = phase["out"]
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + out.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']}")
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
