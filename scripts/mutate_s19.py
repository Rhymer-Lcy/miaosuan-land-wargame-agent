"""Mutation check of the Sprint 19 T6-G gate, hold state machine and decision logic (``docs/SPRINT19_T6G_SHADOW.md``).

    python scripts/mutate_s19.py [--write]

Every mutant must make ``tests/test_s19_t6g.py`` fail. Each run copies ``src``, ``tests`` and ``scripts`` into a
temporary root (``tests/__init__.py`` puts that copy's own ``src`` first on ``sys.path``, so the mutant is the module
really imported); the unmutated copy must pass first. ``--write`` records the outcome in
``evaluation/s19-t6g-shadow/mutation.json``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = "src/miaosuan_agent/experiments/t6_threat_entry_gate.py"
ANALYSIS = "src/miaosuan_agent/evaluation/s19_t6g.py"
TEST = "tests.test_s19_t6g"
OUT = ROOT / "evaluation" / "s19-t6g-shadow" / "mutation.json"
MUTANTS = [
    (GATE, "current position at range counted outside",
     "if any(hex_distance(current, t.hex) <= t.reach for t in threats):",
     "if any(hex_distance(current, t.hex) < t.reach for t in threats):"),
    (GATE, "route hex at range counted outside",
     "causing = tuple(t for t in threats if any(hex_distance(h, t.hex) <= t.reach for h in inspected))",
     "causing = tuple(t for t in threats if any(hex_distance(h, t.hex) < t.reach for h in inspected))"),
    (GATE, "prefix of six hexes", "ROUTE_PREFIX = 5", "ROUTE_PREFIX = 6"),
    (GATE, "prefix slice one too long", "[:max(0, route_prefix)]", "[:max(0, route_prefix) + 1]"),
    (GATE, "prefix of four hexes", "ROUTE_PREFIX = 5", "ROUTE_PREFIX = 4"),
    (GATE, "hold limit exclusive", "if cur_step - start >= rules.hold_limit:", "if cur_step - start > rules.hold_limit:"),
    (GATE, "hold limit 149", "HOLD_LIMIT = 150", "HOLD_LIMIT = 149"),
    (GATE, "cooldown expiry exclusive", "elif phase == COOL and cur_step - step >= rules.cooldown:",
     "elif phase == COOL and cur_step - step > rules.cooldown:"),
    (GATE, "cooldown 301", "COOLDOWN = 300", "COOLDOWN = 301"),
    (GATE, "cooldown ignored", "if entry is not None and entry[0] == COOL:", "if False:"),
    (GATE, "no-baseline-move release dropped", "if phase == HOLD and obj not in touched:", "if False:"),
    (GATE, "absent unit keeps its state", "        if obj not in own:\n", "        if False:\n"),
    (GATE, "repeat not dropped",
     "                dropped.append(i)\n                events.append(GateEvent(\"gate_repeat\"",
     "                events.append(GateEvent(\"gate_repeat\""),
    (GATE, "condition cleared keeps the hold",
     "reason=\"condition_cleared\",\n                                        hold_start=start, check=check))\n"
     "                state[obj] = (COOL, cur_step)\n",
     "reason=\"condition_cleared\",\n                                        hold_start=start, check=check))\n"),
    (GATE, "first weapon only", "reach = weapon_range(enemy.get(\"carry_weapon_ids\") or (), mover_type)",
     "reach = weapon_range((enemy.get(\"carry_weapon_ids\") or (0,))[:1], mover_type)"),
    (GATE, "nearest listed threat only for the current position",
     "if any(hex_distance(current, t.hex) <= t.reach for t in threats):",
     "if any(hex_distance(current, t.hex) <= t.reach for t in threats[:1]):"),
    (GATE, "unreadable route not refused", "    if any(_hex(h) is None for h in prefix):\n", "    if False:\n"),
    (GATE, "order reversed",
     "out = tuple(dict(a) for i, a in enumerate(actions) if i not in kept)",
     "out = tuple(dict(a) for i, a in reversed(list(enumerate(actions))) if i not in kept)"),
    (GATE, "every unit class gated", "if mover is None or mover.get(\"type\") not in GROUND:", "if mover is None:"),
    (GATE, "first entry index zero-based", "for i, h in enumerate(inspected, start=1)", "for i, h in enumerate(inspected)"),
    (ANALYSIS, "opportunity threshold exclusive", "all(n >= OPPORTUNITY_MIN for n in hh_episodes)",
     "all(n > OPPORTUNITY_MIN for n in hh_episodes)"),
    (ANALYSIS, "side-game count not checked", "len(hh_episodes) == HH_SIDE_GAMES and ", ""),
    (ANALYSIS, "pooled opportunity", "all(n >= OPPORTUNITY_MIN for n in hh_episodes)",
     "sum(hh_episodes) >= OPPORTUNITY_MIN * HH_SIDE_GAMES"),
    (ANALYSIS, "exactly one half fails", "2 * capturer_participants <= capturer_gated",
     "2 * capturer_participants < capturer_gated"),
    (ANALYSIS, "fidelity ignored", "    if not items[\"fidelity\"]:\n", "    if False:\n"),
    (ANALYSIS, "opportunity ignored", "    elif not items[\"opportunity\"]:\n", "    elif False:\n"),
    (ANALYSIS, "gated decisions counted as opportunities", "return [len(a.episodes) for a in sides]",
     "return [a.shadow.gated_decisions for a in sides]"),
    (ANALYSIS, "capturers de-duplicated across side-games",
     "    num = sum(len(a.gated & a.participants) for a in sides)\n",
     "    num = len(set().union(*[a.gated & a.participants for a in sides]))\n"),
    (ANALYSIS, "damage window exclusive", "if lo <= r[\"step\"] <= hi]", "if lo <= r[\"step\"] < hi]"),
    (ANALYSIS, "damage before the gate counted", "if lo <= r[\"step\"] <= hi]", "if r[\"step\"] <= hi]"),
    (ANALYSIS, "initial ownership has participants", "parts = frozenset() if initial else frozenset(",
     "parts = frozenset("),
    (ANALYSIS, "numbers not masked", "privacy_problems(mask_numbers(data), ", "privacy_problems(data, "),
    (ANALYSIS, "open episode not closed", "ep.release_k, ep.release_step, ep.reason = last.k, last.cur_step, OPEN_AT_END",
     "pass"),
]


def run_copy(target: str, text: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        for part in ("src", "tests", "scripts"):
            shutil.copytree(ROOT / part, Path(tmp) / part, ignore=shutil.ignore_patterns("__pycache__"))
        (Path(tmp) / target).write_text(text, encoding="utf-8", newline="\n")
        done = subprocess.run([sys.executable, "-m", "unittest", TEST], cwd=tmp, capture_output=True, text=True)
        return done.returncode


def main() -> int:
    sources = {t: (ROOT / t).read_text(encoding="utf-8") for t in (GATE, ANALYSIS)}
    if run_copy(GATE, sources[GATE]) != 0:
        print("baseline FAIL: the unmutated copy does not pass")
        return 1
    print("baseline PASS")
    rows = []
    for target, name, old, new in MUTANTS:
        if sources[target].count(old) != 1:
            print(f"NOT APPLIED {name}")
            rows.append({"mutant": name, "file": target, "outcome": "not applied"})
            continue
        dead = run_copy(target, sources[target].replace(old, new)) != 0
        print(("KILLED   " if dead else "SURVIVED ") + name)
        rows.append({"mutant": name, "file": target, "outcome": "killed" if dead else "survived"})
    killed = sum(r["outcome"] == "killed" for r in rows)
    print(f"killed {killed} of {len(MUTANTS)}")
    if "--write" in sys.argv:
        record = {"schema": "miaosuan-s19-mutation/1", "test": TEST, "declared": len(MUTANTS), "killed": killed,
                  "sources_sha256": {t: hashlib.sha256(s.replace("\r\n", "\n").encode("utf-8")).hexdigest()
                                     for t, s in sorted(sources.items())},
                  "mutants": rows}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
