"""Mutation check of the Sprint 20 T11-O1 rule, comparison and decision logic (``docs/SPRINT20_T11_REPLAY.md``).

    python scripts/mutate_s20.py [--write]

Every mutant must make ``tests/test_s20_t11.py`` fail. Each run copies ``src``, ``tests`` and ``scripts`` into a
temporary root (``tests/__init__.py`` puts that copy's own ``src`` first on ``sys.path``, so the mutant is the module
really imported); the unmutated copy must pass first. ``--write`` records the outcome in
``evaluation/s20-t11-replay/mutation.json``.
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
RULE = "src/miaosuan_agent/experiments/t11_kill_first.py"
ANALYSIS = "src/miaosuan_agent/evaluation/s20_t11.py"
TEST = "tests.test_s20_t11"
OUT = ROOT / "evaluation" / "s20-t11-replay" / "mutation.json"
MUTANTS = [
    (RULE, "blood direction: highest first", "    lowest = min(values.values())\n", "    lowest = max(values.values())\n"),
    (RULE, "blood tie broken by the higher target id",
     "    return best([c for c in options if values[target_of(c)] == lowest]), None",
     "    tied = [c for c in options if values[target_of(c)] == lowest]\n"
     "    top = max(target_of(c) for c in tied)\n"
     "    return best([c for c in tied if target_of(c) == top]), None"),
    (RULE, "attack-level direction on the chosen target",
     "    return best([c for c in options if values[target_of(c)] == lowest]), None",
     "    return min([c for c in options if values[target_of(c)] == lowest], key=lambda c: (-c.rank[0], c.rank[1], c.rank[2])), None"),
    (RULE, "weapon tie-break reversed",
     "    return best([c for c in options if values[target_of(c)] == lowest]), None",
     "    return min([c for c in options if values[target_of(c)] == lowest], key=lambda c: (c.rank[0], c.rank[1], -c.rank[2])), None"),
    (RULE, "ranking before the reservation's exclusion",
     "                if category is Category.ENGAGE:\n                    ranked, fallback = self.rank_engage(options)",
     "                if category is Category.ENGAGE:\n                    ranked, fallback = self.rank_engage(engage)"),
    (RULE, "reservation not updated by the selected shot",
     "                    targets[target_of(selected)] = unit.obj_id\n",
     "                    targets[target_of(best(engage))] = unit.obj_id\n"),
    (RULE, "a bool blood accepted", "    if isinstance(value, bool) or not isinstance(value, int) or value < 0:",
     "    if not isinstance(value, int) or value < 0:"),
    (RULE, "a negative blood accepted", "    if isinstance(value, bool) or not isinstance(value, int) or value < 0:",
     "    if isinstance(value, bool) or not isinstance(value, int):"),
    (RULE, "a missing blood read as zero", "        if not view.present:\n            return best(options), BLOOD_MISSING\n",
     ""),
    (RULE, "an invisible target skipped instead of failing closed",
     "        if view is None:\n            return best(options), NOT_VISIBLE\n",
     "        if view is None:\n            continue\n"),
    (RULE, "own units counted as enemies", "    return {obj: v for obj, v in views.items() if v.color != faction}",
     "    return dict(views)"),
    (RULE, "baseline ranking is kill-first", "        if self.ranking == BASELINE:\n            return best(options), None\n",
     ""),
    (ANALYSIS, "root switches not separated", "        root = c.ranked_choice != c.baseline_choice\n",
     "        root = False\n"),
    (ANALYSIS, "unexplained differences accepted",
     "            cls = UNEXPLAINED\n            out.problems.append(\"an action difference with the same ranking and the same reservation state\")\n",
     "            cls = INDUCED_SHOOT if kind == CHANGED_SHOT else INDUCED_NONSHOOT\n"),
    (ANALYSIS, "occupation state ignored in the explanation",
     "        elif set(b.excluded) != set(c.excluded) or b.occupy_blocked != c.occupy_blocked:",
     "        elif set(b.excluded) != set(c.excluded):"),
    (ANALYSIS, "lost shots counted as changed shots",
     "        kind = (CHANGED_SHOT if b_shot and c_shot else LOST_SHOT if b_shot else GAINED_SHOT if c_shot else OTHER)",
     "        kind = (CHANGED_SHOT if b_shot or c_shot else OTHER)"),
    (ANALYSIS, "silent root switches counted as differences", "        if ba == ca:\n", "        if ba == ca and not root:\n"),
    (ANALYSIS, "chain not accumulated", "        diff.chain = 1 + max((d.chain for d in causes), default=0)",
     "        diff.chain = 1 + int(bool(causes))"),
    (ANALYSIS, "memory difference ignored", "    if base_memory != cand_memory:\n", "    if False:\n"),
    (ANALYSIS, "reserved-target shot not flagged",
     "            if ca.get(\"target_obj_id\") in c.reserved_before:\n", "            if False:\n"),
    (ANALYSIS, "unlisted shot not flagged", "            if shot_key(ca) not in listed:\n", "            if False:\n"),
    (ANALYSIS, "changed-shot denominator includes non-shoot differences",
     "    return [s.counts[\"changed_emitted_shots\"] for s in sides]",
     "    return [s.counts[\"changed_emitted_shots\"] + nonshoot(s) for s in sides]"),
    (ANALYSIS, "opportunity threshold exclusive", "all(n >= OPPORTUNITY_MIN for n in hh_changed_shots)",
     "all(n > OPPORTUNITY_MIN for n in hh_changed_shots)"),
    (ANALYSIS, "pooled opportunity", "all(n >= OPPORTUNITY_MIN for n in hh_changed_shots)",
     "sum(hh_changed_shots) >= OPPORTUNITY_MIN * HH_SIDE_GAMES"),
    (ANALYSIS, "side-game count not checked", "len(hh_changed_shots) == HH_SIDE_GAMES and ", ""),
    (ANALYSIS, "gained shots not coupling",
     "        kind = (CHANGED_SHOT if b_shot and c_shot else LOST_SHOT if b_shot else GAINED_SHOT if c_shot else OTHER)",
     "        kind = (CHANGED_SHOT if c_shot else LOST_SHOT if b_shot else OTHER)"),
    (ANALYSIS, "coupling reads one population", "    return any(nonshoot(s) > 0 for s in sides)",
     "    return any(nonshoot(s) > 0 for s in list(sides)[:1])"),
    (ANALYSIS, "zero kill edge passes", "    return delta_pkill is not None and delta_pkill > 0",
     "    return delta_pkill is not None and delta_pkill >= 0"),
    (ANALYSIS, "model availability checked after coupling",
     "    elif not items[\"kill_model_available\"]:\n        outcome = DISPOSITIONS[1]\n"
     "    elif not items[\"pure_target_priority\"]:\n        outcome = DISPOSITIONS[2]\n",
     "    elif not items[\"pure_target_priority\"]:\n        outcome = DISPOSITIONS[2]\n"
     "    elif not items[\"kill_model_available\"]:\n        outcome = DISPOSITIONS[1]\n"),
    (ANALYSIS, "opportunity checked before coupling",
     "    elif not items[\"pure_target_priority\"]:\n        outcome = DISPOSITIONS[2]\n"
     "    elif not items[\"opportunity\"]:\n        outcome = DISPOSITIONS[3]\n",
     "    elif not items[\"opportunity\"]:\n        outcome = DISPOSITIONS[3]\n"
     "    elif not items[\"pure_target_priority\"]:\n        outcome = DISPOSITIONS[2]\n"),
    (ANALYSIS, "fidelity ignored", "    if not items[\"fidelity\"]:\n", "    if False:\n"),
    (ANALYSIS, "inferred items accepted by the model rule",
     "    return bool(items) and all(item[\"status\"] == REQUIRED_FOR_MODEL for item in items)",
     "    return bool(items) and all(item[\"status\"] != UNDOCUMENTED for item in items)"),
    (ANALYSIS, "quotations compared without normalising whitespace",
     "            if normalise_space(text) not in cache[name]:", "            if text not in read(name):"),
    (ANALYSIS, "numbers not masked", "privacy_problems(mask_numbers(data), ", "privacy_problems(data, "),
    (ANALYSIS, "an unequal reference decision accepted",
     "                self.problems.append(f\"k{k}: the baseline ranking does not reproduce baseline-v2\")\n", "                pass\n"),
]


def run_copy(target: str, text: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        for part in ("src", "tests", "scripts"):
            shutil.copytree(ROOT / part, Path(tmp) / part, ignore=shutil.ignore_patterns("__pycache__"))
        (Path(tmp) / target).write_text(text, encoding="utf-8", newline="\n")
        done = subprocess.run([sys.executable, "-m", "unittest", TEST], cwd=tmp, capture_output=True, text=True)
        return done.returncode


def main() -> int:
    sources = {t: (ROOT / t).read_text(encoding="utf-8") for t in (RULE, ANALYSIS)}
    if run_copy(RULE, sources[RULE]) != 0:
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
        record = {"schema": "miaosuan-s20-mutation/1", "test": TEST, "declared": len(MUTANTS), "killed": killed,
                  "sources_sha256": {t: hashlib.sha256(s.replace("\r\n", "\n").encode("utf-8")).hexdigest()
                                     for t, s in sorted(sources.items())},
                  "mutants": rows}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
