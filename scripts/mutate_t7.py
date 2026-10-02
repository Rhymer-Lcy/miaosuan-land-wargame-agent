"""Mutation test of the T7 design study: the shadow's trigger and own check, the audit, the pool predicates, the
exposure and witness scoring, the rubric's computed anchors and the shadow-check contract test.

    python scripts/mutate_t7.py [--check]

Applies each mutation to a temporary copy of the repository's ``src``, ``scripts``, ``tests`` and the study's public
outputs, runs the public T7 tests against it in a fresh process and records whether they failed (the mutation was
killed). Every mutation's original text must occur exactly once in its file. Writes (or with ``--check`` compares)
``evaluation/t7-design-1/mutation.json``; a surviving mutation is kept with its documented reason in ``SURVIVORS``.
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
OUT = REPO_ROOT / "evaluation" / "t7-design-1" / "mutation.json"
TESTS = ("tests.test_t7_shadow", "tests.test_t7_audit", "tests.test_t7_analysis", "tests.test_t7_results")
SHADOW = "src/miaosuan_agent/experiments/t7_idle_concealment.py"
AUDIT = "src/miaosuan_agent/evaluation/t7_audit.py"
POOL = "src/miaosuan_agent/evaluation/t7_candidates.py"
STUDY = "scripts/t7_study.py"
RUBRIC = "scripts/t7_rubric.py"
CHECKS = "scripts/t7_shadow.py"
MUTATIONS = [
    (SHADOW, "ground units not required", 'if fields.get("type") not in GROUND:', "if False:"),
    (SHADOW, "any change-state option accepted", 'if option["target_state"] == CONCEAL and found is None:',
     "if found is None:"),
    (SHADOW, "concealed units not refused", "if state == CONCEAL:", "if False:"),
    (SHADOW, "transitions ignored", 'if value != 0:\n            return "in a transition"',
     'if False:\n            return "in a transition"'),
    (SHADOW, "missing transition fields accepted", 'if not _is_number(value):\n            return f"missing or malformed {name}"',
     'if False:\n            return f"missing or malformed {name}"'),
    (SHADOW, "stop not required", 'if fields.get("stop") != 1:', "if False:"),
    (SHADOW, "a move path allowed", 'if path:\n        return "has a move path"', 'if False:\n        return "has a move path"'),
    (SHADOW, "suppressed units allowed", "if keep != 0:", "if False:"),
    (SHADOW, "booleans read as numbers", "return isinstance(value, (int, float)) and not isinstance(value, bool)",
     "return isinstance(value, (int, float))"),
    (SHADOW, "enemy seen ignored", 'if enemy_seen:\n        return "an enemy is seen"', 'if False:\n        return "an enemy is seen"'),
    (SHADOW, "repeat window one step longer", "if last is not None and cur_step - last < REPEAT_WINDOW:",
     "if last is not None and cur_step - last <= REPEAT_WINDOW:"),
    (SHADOW, "repeat window removed", "if last is not None and cur_step - last < REPEAT_WINDOW:", "if False:"),
    (SHADOW, "units with a baseline action considered", "if unit.color != faction or unit.obj_id in acted:",
     "if unit.color != faction:"),
    (SHADOW, "enemy units considered", "if unit.color != faction or unit.obj_id in acted:", "if unit.obj_id in acted:"),
    (SHADOW, "deployment allowed", "if time.stage != Stage.PLAY:", "if False:"),
    (SHADOW, "memory not updated", "last[unit.obj_id] = time.cur_step", "pass"),
    (SHADOW, "own check ignored", "if failed is not None:", "if False:"),
    (SHADOW, "own check: key set", "if set(action) != ACTION_KEYS:", "if False:"),
    (SHADOW, "own check: listing", 'if option is None:\n        return "option not listed for the unit"',
     'if False:\n        return "option not listed for the unit"'),
    (SHADOW, "own check: second action", 'if any(a.get("obj_id") == action["obj_id"] for a in taken):', "if False:"),
    (SHADOW, "baseline actions dropped", "return ShadowDecision(tuple(base.actions) + tuple(added), base,",
     "return ShadowDecision(tuple(added), base,"),
    (AUDIT, "current-state option counted as an opportunity", 'if all(s == unit.get("move_state") for s in states):',
     "if False:"),
    (AUDIT, "empty move path counted as an opportunity", 'if not path:\n            return "empty move path"',
     'if False:\n            return "empty move path"'),
    (AUDIT, "speed 0 counted as an opportunity", 'if positive(unit, "speed") is False:', "if False:"),
    (AUDIT, "aircraft labelled as ground", 'if unit.get("type") == 3:', "if False:"),
    (AUDIT, "locked weapons counted as a lock opportunity",
     'return "already locked" if unit.get("weapon_unfold_state") == 0 else None', "return None"),
    (AUDIT, "fingerprint without the enemy flag", 'u.get("tire"), seen,', 'u.get("tire"), False,'),
    (AUDIT, "enemy listings counted", 'if unit is not None and unit.get("color") != faction:\n                continue',
     'if False:\n                continue'),
    (AUDIT, "issued actions not counted", 'if t in T7_TYPES:\n                self.issued', 'if False:\n                self.issued'),
    (AUDIT, "malformed options not counted", 'if malformed:\n                        self.malformed',
     'if False:\n                        self.malformed'),
    (AUDIT, "gaps not detected", "if self.previous is not None and cur_step != self.previous[0] + 1:", "if False:"),
    (AUDIT, "arrivals not detected", "if has_path(old) and has_path(unit) is False:", "if False:"),
    (AUDIT, "arrivals never settle", 'elif arr["stop_after"] is not None and "move" in arr["listed_after"]:', "elif False:"),
    (POOL, "A2 ignores the enemy", "if CONCEAL not in states or v2 is not None or seen:",
     "if CONCEAL not in states or v2 is not None:"),
    (POOL, "A2 repeat window one step longer", "if last is not None and cur_step - last < TRANSITION:",
     "if last is not None and cur_step - last <= TRANSITION:"),
    (POOL, "stops on units with speed 0", 'has_path(unit) is True and (number(unit.get("speed")) or 0) > 0',
     "has_path(unit) is True"),
    (POOL, "B1 range one hex longer", "if d <= reach and (best is None or d < best[0]):",
     "if d <= reach + 1 and (best is None or d < best[0]):"),
    (POOL, "B1 includes move-and-fire units", 'if unit.get("A1") != 0 or not moving(unit, unit_actions):',
     "if not moving(unit, unit_actions):"),
    (POOL, "B2 fires inside the observation range", "if hex_distance(there, nxt) <= reach < hex_distance(there, here):",
     "if hex_distance(there, nxt) <= reach <= hex_distance(there, here):"),
    (POOL, "A1 counts three transitions", "A1_OVERHEAD = 4 * TRANSITION", "A1_OVERHEAD = 3 * TRANSITION"),
    (POOL, "A1 includes artillery", 'if unit.get("type") != VEHICLE or unit.get("sub_type") == ARTILLERY:',
     'if unit.get("type") != VEHICLE:'),
    (POOL, "A3 without the two-hex limit", "if not path or len(path) > A3_MAX_HEXES or path[-1] not in cities(raw):",
     "if not path or path[-1] not in cities(raw):"),
    (POOL, "hex distance with even rows shifted", "q1, q2 = c1 - (r1 - (r1 & 1)) // 2, c2 - (r2 - (r2 & 1)) // 2",
     "q1, q2 = c1 - (r1 + (r1 & 1)) // 2, c2 - (r2 + (r2 & 1)) // 2"),
    (POOL, "weapon range columns swapped", "column = 0 if target_type == INFANTRY else 1 if target_type == VEHICLE else None",
     "column = 1 if target_type == INFANTRY else 0 if target_type == VEHICLE else None"),
    (POOL, "short-sighted observers see 3 hexes", "SHORT_SIGHTED:\n        return 2", "SHORT_SIGHTED:\n        return 3"),
    (STUDY, "A2 exposure window one step longer",
     'exposure = any(unit in row["acted"] for _, row in forward(mine, step, WINDOW))',
     'exposure = any(unit in row["acted"] for _, row in forward(mine, step, WINDOW + 1))'),
    (STUDY, "A2 witness continues after the unit moves",
     'if stop != 1 or path is not False or unit in row["acted"]:\n                break',
     'if False:\n                break'),
    (STUDY, "A2 witness ignores the opposing view", '(unit in other["listed_ids"] or unit in other["judged"])',
     '(unit in other["judged"])'),
    (STUDY, "B2 witness always true", 'return exposure, bool(other is not None and unit in other["listed_ids"])',
     "return exposure, True"),
    (STUDY, "B1 witness ignores the range", "if tc.hex_distance(here, there) > reach:", "if False:"),
    (RUBRIC, "generality without the archetype condition", "if n == 8 and archetypes >= 3:", "if n == 8:"),
    (RUBRIC, "opportunity anchors widened", "for limit, score in ((0.01, 5), (0.05, 4), (0.15, 3), (0.30, 2)):",
     "for limit, score in ((0.01, 5), (0.10, 4), (0.15, 3), (0.30, 2)):"),
    (RUBRIC, "mandatory minimum made strict", 'return all(row[c]["score"] >= rubric["criteria"][c]["mandatory_minimum"]',
     'return all(row[c]["score"] > rubric["criteria"][c]["mandatory_minimum"]'),
    (RUBRIC, "unknown cells not capped in sensitivity",
     'value = unknown_value if (unknown_value is not None and cell["unknown"]) else cell["score"]',
     'value = cell["score"]'),
    (CHECKS, "contract check accepts anything",
     'return any(isinstance(o, dict) and o.get("target_state") == action["target_state"] for o in options)',
     "return True"),
]
#: Surviving mutations, each with the reason it is not killed (documented, not hidden).
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
        for part in ("src", "scripts", "tests", "evaluation/t7-design-1"):
            shutil.copytree(REPO_ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
        (root / path).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONPATH"] = str(root / "src")
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env, capture_output=True,
                              text=True, timeout=1200)
    return {"file": path, "mutation": name, "killed": done.returncode != 0, "reason_if_surviving": SURVIVORS.get(name)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    baseline = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=REPO_ROOT, capture_output=True, text=True)
    if baseline.returncode != 0:
        print("the unmutated tests fail; no mutation run")
        return 1
    results = [run(m) for m in MUTATIONS]
    files = sorted({m[0] for m in MUTATIONS})
    payload = {"schema": "miaosuan-t7-mutation/1", "tests": list(TESTS),
               "sources_sha256": {f: normalized_sha256(REPO_ROOT / f) for f in files},
               "tests_sha256": {f"tests/{t.split('.')[-1]}.py": normalized_sha256(REPO_ROOT / "tests" / f"{t.split('.')[-1]}.py")
                                for t in TESTS},
               "mutations": results, "killed": sum(r["killed"] for r in results), "total": len(results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("mutation results identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    surviving = [r["mutation"] for r in results if not r["killed"]]
    print(f"killed {payload['killed']} of {payload['total']}" + (f"; surviving: {surviving}" if surviving else ""))
    return 0 if all(r["killed"] or r["reason_if_surviving"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
