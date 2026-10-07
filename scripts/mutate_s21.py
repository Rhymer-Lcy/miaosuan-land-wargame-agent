"""Mutation check of the Sprint 21 direct-fire semantics audit (``docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md``).

    python scripts/mutate_s21.py [--write]

Every mutant must make ``tests/test_s21_semantics.py`` fail. Each run copies ``src``, ``tests``, ``scripts``, ``docs`` and
``evaluation`` into a temporary root (``tests/__init__.py`` puts that copy's own ``src`` first on ``sys.path``, so the
mutant is the module really imported); the unmutated copy must pass first. ``--write`` records the outcome in
``evaluation/s21-direct-fire-semantics/mutation.json``.
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
ANALYSIS = "src/miaosuan_agent/evaluation/s21_semantics.py"
TEST = "tests.test_s21_semantics"
OUT = ROOT / "evaluation" / "s21-direct-fire-semantics" / "mutation.json"
MUTANTS = [
    # pairing
    ("refused shot read as accepted", '            status = REFUSED if found[0].get("error") else "accepted"',
     '            status = "accepted"'),
    ("duplicate submissions not detected", "        if len(found) != 1 or submitted_keys[key] != 1:",
     "        if len(found) != 1:"),
    ("ambiguous records paired with the first", "        elif len(matched) == 1 and claims[matched[0]] == 1:",
     "        elif matched and claims[matched[0]] == 1:"),
    ("a record claimed twice still paired", "        elif len(matched) == 1 and claims[matched[0]] == 1:",
     "        elif len(matched) == 1:"),
    ("refused shot with a record tolerated", "            if matched:\n                s[\"status\"] = REFUSED_WITH_RECORD\n",
     ""),
    ("accepted shot without a record tolerated",
     "INTEGRITY_FAILURES = (ACCEPTED_NO_RECORD, REFUSED_WITH_RECORD, ACCEPTANCE_UNKNOWN)",
     "INTEGRITY_FAILURES = (REFUSED_WITH_RECORD, ACCEPTANCE_UNKNOWN)"),
    ("weapon ignored in the pairing key", '    return record.get("att_obj_id"), record.get("target_obj_id"), record.get("wp_id")',
     '    return record.get("att_obj_id"), record.get("target_obj_id"), None'),
    ("actor ignored in acceptance", "            echoes[(message.get(\"actor\"),) + shot_key(message)].append(entry)",
     "            echoes[(None,) + shot_key(message)].append(entry)"),
    # K2
    ("K2 mismatch not refuting", "    if different:\n        status = K2_REFUTED", "    if False:\n        status = K2_REFUTED"),
    ("K2 elevation coverage ignored", "    coverage = len(values) >= 2 or len(corpus) <= 1", "    coverage = True"),
    ("K2 class without rows not untested", '        if not part:\n            by_class[cls] = "UNTESTED"',
     '        if not part:\n            by_class[cls] = status'),
    # K4
    ("infantry light weapon reads the vehicle table",
     "        table = PERSONNEL_TABLE if weapon == INFANTRY_LIGHT_WEAPON else VEHICLE_TABLE",
     "        table = VEHICLE_TABLE"),
    ("vehicle columns ignore the shooter count",
     "    columns = VEHICLE_COLUMNS.get(shooter_count) if is_int(shooter_count) else None",
     "    columns = VEHICLE_COLUMNS.get(1)"),
    ("attack level off by one in the personnel table", "        return (table, *_cell(row[att_level - 1]))\n    if table == AIR_TABLE:",
     "        return (table, *_cell(row[min(att_level, len(row) - 1)]))\n    if table == AIR_TABLE:"),
    ("out-of-table rows accepted by the mapping",
     "        elif mismatches or any(len(v) > 1 for v in kinds.values()) or out_of_table:",
     "        elif mismatches or any(len(v) > 1 for v in kinds.values()):"),
    ("two values for one kind accepted", "        elif mismatches or any(len(v) > 1 for v in kinds.values()) or out_of_table:",
     "        elif mismatches or out_of_table:"),
    ("probability law accepted from route C",
     '    return K4P_SUPPORTED if any(e["status"] == STATES_LAW and e["route"] in ("A", "B") for e in evidence) else K4P_UNRESOLVED',
     '    return K4P_SUPPORTED if any(e["status"] == STATES_LAW for e in evidence) else K4P_UNRESOLVED'),
    ("probability law always supported",
     '    return K4P_SUPPORTED if any(e["status"] == STATES_LAW and e["route"] in ("A", "B") for e in evidence) else K4P_UNRESOLVED',
     "    return K4P_SUPPORTED"),
    ("personnel correction boundary moved", "    return -1 if modified <= 0 else (0 if modified <= 7 else 1)",
     "    return -1 if modified < 0 else (0 if modified <= 7 else 1)"),
    # K5
    ("lower clamp dropped from the additive relation", '    "additive_lower_clamp": lambda o, r, b, t: max(0, o + r) + t,',
     '    "additive_lower_clamp": lambda o, r, b, t: o + r + t,'),
    ("positive-only relation corrects a zero raw loss", "    return max(0, o + r) if o > 0 else max(0, o)",
     "    return max(0, o + r) if o >= 0 else max(0, o)"),
    ("resuppression term ignores prior suppression",
     "    return int(target_class == INFANTRY and kind == SUPPRESSION and bool(suppressed_before))",
     "    return int(target_class == INFANTRY and kind == SUPPRESSION)"),
    ("several survivors read as identified",
     "        status = K5_IDENTIFIED if len(survivors) == 1 else (K5_NO_FIT if not survivors else K5_UNDERIDENTIFIED)",
     "        status = K5_IDENTIFIED if survivors else K5_NO_FIT"),
    ("annihilation read as one in the whole-unit relation", "            return (b if annihilation_all else 1) + extra",
     "            return 1 + extra"),
    # K6
    ("decrement test skipped",
     '    a_bad = [r for r in a_rows if not (is_int(r.get("blood_after")) and r["blood_before"] - r["blood_after"] == r["damage"])]',
     "    a_bad = []"),
    ("lethal boundary exclusive", '    lethal = [r for r in used if r["damage"] >= r["blood_before"]]',
     '    lethal = [r for r in used if r["damage"] > r["blood_before"]]'),
    ("linked removals counted as contradictions", '    used = [r for r in rows if not r.get("linked_removal")]',
     "    used = list(rows)"),
    ("no lethal row still supported", "    elif not lethal or not nonlethal_positive:", "    elif not nonlethal_positive:"),
    # sufficiency and disposition
    ("K4 probability not required", '    items = {"K2": k2_status == K2_SUPPORTED, "K4_probability": k4_probability == K4P_SUPPORTED,',
     '    items = {"K2": k2_status == K2_SUPPORTED, "K4_probability": True,'),
    ("missing required class ignored",
     '    missing = [c for c in required if not (sufficiency.get(c) or {}).get("sufficient")]',
     '    missing = [c for c in required if not (sufficiency.get(c) or {"sufficient": True}).get("sufficient")]'),
    ("integrity checked after sufficiency",
     "    if not integrity_ok:\n        outcome = DISPOSITIONS[0]\n    elif not required or missing:\n        outcome = DISPOSITIONS[1]\n",
     "    if not required or missing:\n        outcome = DISPOSITIONS[1]\n    elif not integrity_ok:\n        outcome = DISPOSITIONS[0]\n"),
    ("zero kill edge passes", "            \"delta_pkill\": delta, \"status\": T11_COMPLETIONS[1] if c_mean > b_mean else T11_COMPLETIONS[0]}",
     "            \"delta_pkill\": delta, \"status\": T11_COMPLETIONS[1] if c_mean >= b_mean else T11_COMPLETIONS[0]}"),
    ("denominator not enforced", "    if len(baseline) != HH_CHANGED_SHOTS or len(candidate) != HH_CHANGED_SHOTS:",
     "    if len(baseline) != len(candidate):"),
    ("required classes miss the T11 side", "                classes.update((class_of_label(before), class_of_label(after)))",
     "                classes.add(class_of_label(before))"),
    ("bare numeric public keys", '    if isinstance(value, int) and value < 0:\n        return f"{label}_minus_{-value}"\n    return f"{label}_{value}"',
     '    return str(value)'),
    ("numbers not masked by the sanitizer", "privacy_problems(mask_numbers(data), ", "privacy_problems(data, "),
]


def run_copy(text: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        for part in ("src", "tests", "scripts", "docs", "evaluation"):
            shutil.copytree(ROOT / part, Path(tmp) / part, ignore=shutil.ignore_patterns("__pycache__"))
        local = ROOT / "local" / "source-archives"
        if local.exists():  # the snapshot checks run where the snapshot exists
            shutil.copytree(local / "docs-live-snapshot-20260929", Path(tmp) / "local" / "source-archives" /
                            "docs-live-snapshot-20260929")
        (Path(tmp) / ANALYSIS).write_text(text, encoding="utf-8", newline="\n")
        done = subprocess.run([sys.executable, "-m", "unittest", TEST], cwd=tmp, capture_output=True, text=True)
        return done.returncode


def main() -> int:
    source = (ROOT / ANALYSIS).read_text(encoding="utf-8")
    if run_copy(source) != 0:
        print("baseline FAIL: the unmutated copy does not pass")
        return 1
    print("baseline PASS")
    rows = []
    for name, old, new in MUTANTS:
        if source.count(old) != 1:
            print(f"NOT APPLIED {name}")
            rows.append({"mutant": name, "outcome": "not applied"})
            continue
        dead = run_copy(source.replace(old, new)) != 0
        print(("KILLED   " if dead else "SURVIVED ") + name)
        rows.append({"mutant": name, "outcome": "killed" if dead else "survived"})
    killed = sum(r["outcome"] == "killed" for r in rows)
    print(f"killed {killed} of {len(MUTANTS)}")
    if "--write" in sys.argv:
        record = {"schema": "miaosuan-s21-mutation/1", "test": TEST, "file": ANALYSIS, "declared": len(MUTANTS),
                  "killed": killed,
                  "source_sha256": hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest(),
                  "mutants": rows}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
