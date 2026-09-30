"""Mutation test of the shoot-reservation experiment's registration and analysis code.

    python scripts/mutate_shoot_analysis.py [--check]

The repository's files (tracked, or new and not ignored) are copied to a temporary directory; each mutant
replaces exactly one fragment of the copy's ``src/miaosuan_agent/evaluation/shoot_experiment.py`` or
``scripts/analyze_shoot_experiment.py``, and ``tests.test_shoot_experiment`` runs against that copy. The
checkout itself is never modified. Every mutant here changes a registered definition or verdict and must be
killed. The outcome is written to
``evaluation/baseline-v2-candidate-shoot-target-reservation/mutation-analysis.json``; ``--check`` reruns and
compares.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = "src/miaosuan_agent/evaluation/shoot_experiment.py"
SCRIPT = "scripts/analyze_shoot_experiment.py"
TESTS = ("tests.test_shoot_experiment",)
OUT = REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "mutation-analysis.json"
SCHEMA = "miaosuan-shoot-analysis-mutation/1"

MUTANTS = [
    (MODULE, "primary: an interval touching zero passes", 'result["ci_high"] < 0 and reduction is not None',
     'result["ci_high"] <= 0 and reduction is not None'),
    (MODULE, "primary: the minimum reduction ignored", "              and reduction >= MINIMUM_RELATIVE_REDUCTION)",
     "              )"),
    (MODULE, "non-inferiority: a lower limit at the margin passes", 'result["ci_low"] > -NON_INFERIORITY_MARGIN',
     'result["ci_low"] >= -NON_INFERIORITY_MARGIN'),
    (MODULE, "contrast: sign reversed", "delta = sum(c - b for b, c in zip(base_means, cand_means)) / k",
     "delta = sum(b - c for b, c in zip(base_means, cand_means)) / k"),
    (MODULE, "contrast: games pooled instead of configurations weighted equally",
     "delta = sum(c - b for b, c in zip(base_means, cand_means)) / k",
     "delta = sum(sum(x) for _, _, x in usable) / sum(len(x) for _, _, x in usable) - sum(sum(b) for _, b, _ in usable) "
     "/ sum(len(b) for _, b, _ in usable)"),
    (MODULE, "bootstrap: candidate drawn before baseline",
     "            mb = sum(b[stats.draw(rng, len(b))] for _ in b) / len(b)\n            mx = sum(x[stats.draw(rng, len(x))] for _ in x) / len(x)",
     "            mx = sum(x[stats.draw(rng, len(x))] for _ in x) / len(x)\n            mb = sum(b[stats.draw(rng, len(b))] for _ in b) / len(b)"),
    (MODULE, "exclusions count unchanged selections", "sum(effects.get(e, 0) for e in DISPLACED_EFFECTS)",
     "sum(effects.get(e, 0) for e in DISPLACED_EFFECTS + ('unchanged',))"),
    (MODULE, "per-shot rate over unit actions", '_per_1000(values["code_516"], shots)',
     '_per_1000(values["code_516"], values["unit_actions"])'),
    (MODULE, "repeat fire counted from one shot", '"repeat_fire" if shots >= 2 else "single_fire"',
     '"repeat_fire" if shots >= 1 else "single_fire"'),
    (MODULE, "schedule: groups not alternated between rounds", 'first, second = ("B", "C") if round_number % 2 else ("C", "B")',
     'first, second = ("B", "C")'),
    (MODULE, "schedule: boundary swap removed", "            orders[first][0], orders[first][1] = orders[first][1], orders[first][0]",
     "            pass"),
    (MODULE, "promotion on any criterion", 'all_pass = all(v["pass"] for v in verdict.values())',
     'all_pass = any(v["pass"] for v in verdict.values())'),
    (MODULE, "fourteen repetitions", "REPETITIONS = 15", "REPETITIONS = 14"),
    (MODULE, "missing seat fields tolerated", "    if missing:\n        raise ValueError", "    if False:\n        raise ValueError"),
    (SCRIPT, "P2 reads group B", 'totals["C"]["duplicate_shoot_target_commands"] == 0 and totals["C"]["replay_mismatches"] == 0',
     'totals["B"]["duplicate_shoot_target_commands"] == 0 and totals["C"]["replay_mismatches"] == 0'),
    (SCRIPT, "P3 ignores missing games", 'not validation["missing"] and not validation["started_without_record"]',
     'not validation["started_without_record"]'),
    (SCRIPT, "P4 reads group B", '"P4": {"pass": totals["C"]["gate_rejections"] == 0',
     '"P4": {"pass": totals["B"]["gate_rejections"] == 0'),
    (SCRIPT, "P5 reads group B", 'totals["C"]["code_1804"] == 0 and totals["C"]["duplicate_occupation_commands"] == 0',
     'totals["B"]["code_1804"] == 0 and totals["C"]["duplicate_occupation_commands"] == 0'),
    (SCRIPT, "P8 never finds a new class",
     'new_classes = sorted([list(k) for k in facts["C"] if k not in known and k not in facts["B"]], key=str)',
     "new_classes = []"),
    (SCRIPT, "host clock offset applied with the wrong sign",
     'first_true = first_host - dt.timedelta(seconds=push["host_clock_ahead_seconds"])',
     'first_true = first_host + dt.timedelta(seconds=push["host_clock_ahead_seconds"])'),
    (SCRIPT, "group of a record not checked", '"group": harness.get("group") == group', '"group": True'),
    (SCRIPT, "engine state changes tolerated", '    if changed != ["0001"]:', "    if False:"),
    (SCRIPT, "primary contrast on all refusals",
     'primary = sx.contrast(values["B"][sx.PRIMARY_METRIC], values["C"][sx.PRIMARY_METRIC], sx.PRIMARY_METRIC)',
     'primary = sx.contrast(values["B"]["refusals_per_1000"], values["C"]["refusals_per_1000"], sx.PRIMARY_METRIC)'),
    (SCRIPT, "non-inferiority over C1 too", 'c2c3 = [c for c in configs if c.split(".")[1] in ("C2", "C3")]',
     "c2c3 = list(configs)"),
]


def repository_copy(destination: Path) -> None:
    listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-co", "--exclude-standard"], capture_output=True,
                            text=True, check=True)
    for name in listed.stdout.splitlines():
        source = REPO_ROOT / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def killed(root: Path) -> bool:
    result = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, capture_output=True, text=True,
                            timeout=3600)
    return result.returncode != 0


def build() -> Dict[str, Any]:
    originals = {name: (REPO_ROOT / name).read_bytes() for name in (MODULE, SCRIPT)}
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="shoot-analysis-mutation-") as temporary:
        root = Path(temporary)
        repository_copy(root)
        if killed(root):
            raise SystemExit("the unmutated copy fails its tests")
        for target, name, old, new in MUTANTS:
            text = originals[target].decode("utf-8")
            if text.count(old) != 1:
                raise SystemExit(f"mutant {name!r}: the fragment occurs {text.count(old)} times, not once")
            (root / target).write_bytes(text.replace(old, new).encode("utf-8"))
            try:
                outcome = "killed" if killed(root) else "survived"
            finally:
                (root / target).write_bytes(originals[target])
            rows.append({"target": target, "mutant": name, "outcome": outcome})
            print(f"{outcome:9s} {name}", flush=True)
    survivors = [r["mutant"] for r in rows if r["outcome"] != "killed"]
    test_file = REPO_ROOT / "tests" / "test_shoot_experiment.py"
    return {"schema": SCHEMA, "targets": {name: hashlib.sha256(data).hexdigest() for name, data in originals.items()},
            "tests": list(TESTS), "tests_sha256": hashlib.sha256(test_file.read_bytes()).hexdigest(),
            "mutants": rows, "total": len(rows),
            "killed": sum(1 for r in rows if r["outcome"] == "killed"), "survivors": survivors, "pass": not survivors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}; pass={result['pass']}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
