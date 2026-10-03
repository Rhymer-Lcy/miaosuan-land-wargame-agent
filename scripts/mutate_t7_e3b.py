"""Mutation test of the E3b configuration search's rules (``t7-e3b-search-1``): the episode classifier, the
continuity checks, episode opening, the D2 idle runs, the command evidence, the feasibility conditions, the ranking
and the decision rule (``evaluation/t7_e3b.py``).

    python scripts/mutate_t7_e3b.py [--check]

Applies each mutation to a temporary copy of ``src`` and ``tests``, runs ``tests.test_t7_e3b`` in a new process and
records whether it failed (the mutation was killed). Every mutation's original text must occur exactly once. Writes (or
with ``--check`` compares) ``evaluation/t7-e3b-search-1/mutation.json``; a surviving mutation is kept with its
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
OUT = REPO_ROOT / "evaluation" / "t7-e3b-search-1" / "mutation.json"
TESTS = ("tests.test_t7_e3b",)
LIB = "src/miaosuan_agent/evaluation/t7_e3b.py"
MUTATIONS = [
    (LIB, "75-step boundary off by one", "episode.cls = W if episode.d >= TRANSITION else TI",
     "episode.cls = W if episode.d > TRANSITION else TI"),
    (LIB, "indirect fire counted as a shot", 'if action.get("type") in (MOVE, SHOOT):\n                episode.cls',
     'if action.get("type") in (MOVE, SHOOT, 8):\n                episode.cls'),
    (LIB, "only moves counted", 'if action.get("type") in (MOVE, SHOOT):\n                episode.cls',
     'if action.get("type") == MOVE:\n                episode.cls'),
    (LIB, "completion boundary off by one", "return self.d is not None and self.d >= TRANSITION",
     "return self.d is not None and self.d > TRANSITION"),
    (LIB, "damage ignored", 'if now.blood != start.blood:\n        return "damaged"', 'if False:\n        return "damaged"'),
    (LIB, "movement ignored", 'if now.hex != start.hex:\n        return "moved"', 'if False:\n        return "moved"'),
    (LIB, "a move path ignored", 'if now.path:\n        return "move path"', 'if False:\n        return "move path"'),
    (LIB, "stop ignored", 'if now.stop != 1:\n        return "not stopped"', 'if False:\n        return "not stopped"'),
    (LIB, "suppression ignored", 'if now.keep != 0:\n        return "suppressed"', 'if False:\n        return "suppressed"'),
    (LIB, "boarding ignored", 'if now.on_board not in (0, None, False):\n        return "boarded"',
     'if False:\n        return "boarded"'),
    (LIB, "forced stop ignored", 'if now.flag_force_stop == 1:\n        return "forced stop"',
     'if False:\n        return "forced stop"'),
    (LIB, "timers ignored", 'if any(_num(t) != 0 for t in now.timers):\n        return "transition"',
     'if False:\n        return "transition"'),
    (LIB, "only the first timer read", 'if any(_num(t) != 0 for t in now.timers):\n        return "transition"',
     'if _num(now.timers[0]) != 0:\n        return "transition"'),
    (LIB, "enemy in the hex ignored", 'if now.hex in decision.enemy_hexes:\n        return "enemy in hex"',
     'if False:\n        return "enemy in hex"'),
    (LIB, "firing ignored", 'if now.obj_id in decision.attackers:\n        return "fired"',
     'if False:\n        return "fired"'),
    (LIB, "being attacked ignored", 'if now.obj_id in decision.targets:\n        return "attacked"',
     'if False:\n        return "attacked"'),
    (LIB, "a missing unit read as missing evidence", 'if now is None:\n        return "unit gone"',
     'if now is None:\n        return MISSING'),
    (LIB, "missing fields read as disturbance", "        if reason == MISSING:\n            episode.gaps.append((decision.k, MISSING))\n        elif reason is not None:",
     "        if reason is not None:"),
    (LIB, "snapshot gaps not recorded", "            episode.gaps.append((decision.k, GAP))", "            pass"),
    (LIB, "the command checked before the state", "        reason = state_violation(start, decision.units.get(unit), decision)\n        if reason == MISSING:",
     "        reason = None if unit in decision.actions else state_violation(start, decision.units.get(unit), decision)\n        if reason == MISSING:"),
    (LIB, "order decision may carry a baseline action", "    if unit in d0.actions:\n        raise",
     "    if False:\n        raise"),
    (LIB, "conditional episodes not opened", "            if previous is not None and (previous.cls == CE or k <= boundary):",
     "            if previous is not None:"),
    (LIB, "a CE episode admits a successor", "            if previous is not None and (previous.cls == CE or k <= boundary):",
     "            if previous is not None and k <= boundary:"),
    (LIB, "orders inside an episode open new ones", "            if previous is not None and (previous.cls == CE or k <= boundary):",
     "            if previous is not None and previous.cls == CE:"),
    (LIB, "conditional flag lost", "episode = classify(decisions, index[k], unit, None if previous is None else previous.label())",
     "episode = classify(decisions, index[k], unit, None)"),
    (LIB, "idle runs ignore orders", "            if any(start_k <= k < decision.k for k in orders.get(unit, ())):\n                continue",
     "            if False:\n                continue"),
    (LIB, "idle runs of 74 steps admitted", "            if length < TRANSITION:\n                continue",
     "            if length < TRANSITION - 1:\n                continue"),
    (LIB, "idle runs cross gaps", "                if decisions[j].cur_step != before.cur_step + 1 or unit in before.actions:",
     "                if unit in before.actions:"),
    (LIB, "idle runs include non-ground units", "if here is None or here.type not in GROUND or state_violation(here, here, decision) is not None:",
     "if here is None or state_violation(here, here, decision) is not None:"),
    (LIB, "acceptance with several echoes", '"accepted": len(matching) == 1 and codes == [None]',
     '"accepted": bool(matching) and all(c is None for c in codes)'),
    (LIB, "an error code accepted", '"accepted": len(matching) == 1 and codes == [None]',
     '"accepted": len(matching) == 1'),
    (LIB, "echo ignores the path", '    if "move_path" in action and list(message.get("move_path") or []) != list(action.get("move_path") or []):\n        return False',
     "    pass"),
    (LIB, "echo ignores the serialisation", "matching = [e for e in feedback if echoes(e, action) or any(echoes(e, s) for s in serialised)]",
     "matching = [e for e in feedback if echoes(e, action)]"),
    (LIB, "shot executed without a judge record",
     'executed = any(isinstance(r, Mapping) and r.get("att_obj_id") == unit for r in judge_of_step)', "executed = True"),
    (LIB, "move executed without entering", "executed = bool(path) and (next_state.hex == path[0]",
     "executed = bool(path) and (True"),
    (LIB, "shot listing ignores the weapon", 'and o.get("weapon_id") == action.get("weapon_id") for o in listed.get(SHOOT) or ())',
     "for o in listed.get(SHOOT) or ())"),
    (LIB, "rows include units only listed", "        if unit.get(\"color\") != faction:\n            continue",
     "        if False:\n            continue"),
    (LIB, "F2 accepts conditional episodes", "        if self.episode.conditional:\n            return False",
     "        if False:\n            return False"),
    (LIB, "F2 ignores the first shot", "if self.first_judge_step is not None and self.first_judge_step < self.episode.s0:",
     "if False:"),
    (LIB, "F2 shot boundary inclusive", "if self.first_judge_step is not None and self.first_judge_step < self.episode.s0:",
     "if self.first_judge_step is not None and self.first_judge_step <= self.episode.s0:"),
    (LIB, "F2 ignores the opponent's view", "return self.opponent_inert or self.earlier_seen_by_opponent == 0",
     "return True"),
    (LIB, "F3 ignores execution", "return bool(self.accepted) and bool(self.executed) and (self.episode.d or 0) >= TRANSITION",
     "return bool(self.accepted) and (self.episode.d or 0) >= TRANSITION"),
    (LIB, "F1 accepts category B", 'return self.category == "A"', 'return self.category in ("A", "B")'),
    (LIB, "rank ignores determinism", "return (0 if c.deterministic_configuration else 1,", "return (0,"),
    (LIB, "rank ignores earlier activations", "0 if c.earlier_first_orders == 0 else 1,\n", "0,\n"),
    (LIB, "rank prefers the longer slack", "(e.d or 0) - TRANSITION, e.s1 or 0)", "TRANSITION - (e.d or 0), e.s1 or 0)"),
    (LIB, "decision ignores the cross-check", "    if stopped or not crosscheck_agrees:\n        return BLOCKED",
     "    if stopped:\n        return BLOCKED"),
    (LIB, "uncertain needs category A", 'if any(c.episode.cls == W and c.category in ("A", "B", "C") for c in configurations):',
     'if any(c.episode.cls == W and c.category == "A" for c in configurations):'),
    (LIB, "TI episodes count as witnesses", 'if any(c.episode.cls == W and c.category in ("A", "B", "C") for c in configurations):',
     'if any(c.category in ("A", "B", "C") for c in configurations):'),
    (LIB, "long wait limit inclusive", "            if runs[unit] > limit:", "            if runs[unit] >= limit:"),
]
#: Surviving mutations, each with the reason it is not killed (documented, not hidden).
SURVIVORS: dict = {
    "a CE episode admits a successor": "equivalent: a CE episode ends at the last decision of the game, so every later "
                                       "order already fails the k <= boundary test; the explicit clause documents it",
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
        for part in ("src", "tests"):
            shutil.copytree(REPO_ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
        (root / path).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONPATH"] = str(root / "src")
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env, capture_output=True,
                              text=True, timeout=600)
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
    payload = {"schema": "miaosuan-t7-e3b-mutation/1", "tests": list(TESTS),
               "sources_sha256": {LIB: normalized_sha256(REPO_ROOT / LIB)},
               "tests_sha256": {"tests/test_t7_e3b.py": normalized_sha256(REPO_ROOT / "tests" / "test_t7_e3b.py")},
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
