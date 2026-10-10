"""Mutation test of the Sprint 35 coalition agent and its rules (``docs/SPRINT35_COALITION_AGENT.md``).

    python scripts/mutate_s35.py [--check]

Sprint 34's procedure (``scripts/mutate_s34.py``): copy ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary
directory, rebuild the live card there when one exists (so its pins never kill a mutation by themselves), first run the
test modules unmutated (they must pass, or every kill would be vacuous), then plant each defect, run the tests in a fresh
process and record whether they failed. Every planted defect's original text must occur exactly once. Record:
``evaluation/s35-coalition-agent/mutation.json``.
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
K = Path("src/miaosuan_agent/coalition")
E = Path("src/miaosuan_agent/evaluation")
OUT = REPO_ROOT / "evaluation" / "s35-coalition-agent" / "mutation.json"
CARD = Path("evaluation/s35-coalition-live-1/manifest.json")
TESTS = ("tests.test_s35_coalition", "tests.test_s35_offline", "tests.test_s35_live", "tests.test_s35_card")
MUTATIONS = [
    # force estimate and attribution
    (K / "capability.py", "remembered threat never fades",
     "        confidence = max(0.0, 1.0 - age / float(config.sighting_ttl))", "        confidence = 1.0"),
    (K / "capability.py", "enemy-held objectives not excluded",
     "if hex_ not in enemy_held] if config.attribution", "if True] if config.attribution"),
    (K / "capability.py", "threat horizon ignored", "            if arrival <= config.threat_horizon:", "            if True:"),
    (K / "capability.py", "no power floor", "    return max(FLOOR_WEIGHT, CLASS_WEIGHT.get(sub_type, OTHER_WEIGHT))",
     "    return CLASS_WEIGHT.get(sub_type, OTHER_WEIGHT)"),
    (K / "capability.py", "holder rank not infantry first",
     "    return (0 if unit.type == F.INFANTRY else 1, unit.value, unit.obj_id)", "    return (unit.value, unit.obj_id)"),
    # stances
    (K / "coalition.py", "secure without enough defence", "            if defence[p.hex] >= want[p.hex]:",
     "            if defence[p.hex] > 0:"),
    (K / "coalition.py", "commit ratio ignored", "            commit = reached >= cfg.commit_ratio * zt.power",
     "            commit = True"),
    (K / "coalition.py", "dwell ignored", "and world.step - prior[2] < cfg.stance_dwell:", "and False:"),
    (K / "coalition.py", "withdrawal on remembered threat", "        if cfg.withdrawal and share >= cfg.withdraw_visible_share:",
     "        if cfg.withdrawal:"),
    (K / "coalition.py", "cheaper units withdrawn", "                if u.value <= holder.value or u.obj_id not in free_ids:",
     "                if u.obj_id not in free_ids:"),
    (K / "coalition.py", "coalition below the capture ratio",
     "        count, reached = _needed(reach, defence[p.hex], want[p.hex])\n        if reached >= want[p.hex]:",
     "        count, reached = _needed(reach, defence[p.hex], want[p.hex])\n        if True:"),
    (K / "coalition.py", "secure keeps every defender", "                        if reached >= want[p.hex]:\n                            break",
     "                        if False:\n                            break"),
    (K / "coalition.py", "defenders not kept when defending",
     "                if cfg.retention:\n                    keep[p.hex] = tuple(sorted(u.obj_id for u in mine))",
     "                if cfg.retention:\n                    keep[p.hex] = ()"),
    (K / "coalition.py", "inbound arrivals not counted",
     "            if arriving:\n                defence[p.hex] = round(defence[p.hex] + C.total_power(arriving), 6)",
     "            if False:\n                defence[p.hex] = round(defence[p.hex] + C.total_power(arriving), 6)"),
    (K / "coalition.py", "reinforcement grace dropped",
     "zt.eta + cfg.deadline_grace, frozenset(committed))", "zt.eta, frozenset(committed))"),
    # allocation
    (K / "allocator.py", "reinforcement deadline ignored",
     "        return place.deadline is None or world.step + eta <= place.deadline", "        return True"),
    (K / "allocator.py", "safe transport ignored", "        safe = self.coalition.safe_transport", "        safe = False"),
    (K / "allocator.py", "power not valued",
     "        value = place.weight * picture.value * (0.5 + C.unit_power(unit)) - cfg.time_cost * eta",
     "        value = place.weight * picture.value - cfg.time_cost * eta"),
    (K / "allocator.py", "skip offers places", "            elif a.stance == COALITION:",
     "            elif a.stance in (COALITION, \"skip\"):"),
    # policy
    (K / "policy.py", "kept units stay in the pool",
     "        pool = [u for u in free if u.obj_id not in kept and u.obj_id not in withdrawing]", "        pool = list(free)"),
    (K / "policy.py", "guided carrier acts", "            elif unit.obj_id in guided_carriers:", "            elif False:"),
    (K / "policy.py", "withdrawals not ordered",
     "                intents[unit_id] = Intent(\"coalition\", WITHDRAW, stand, f\"withdraw toward {dest}\")",
     "                pass"),
    # fire support
    (K / "support.py", "impact near own units", "            if any(F.hex_distance(aim, p) <= clearance for p in protected):",
     "            if False:"),
    (K / "support.py", "arrival window ignored",
     "            if steps is not None and F.ARTILLERY_FLIGHT <= steps < F.ARTILLERY_FLIGHT + config.arrival_window:",
     "            if steps is not None:"),
    (K / "support.py", "guided target not reserved", "        reserved_targets.add(best[0])", "        pass"),
    (K / "support.py", "guided attack level 0 accepted", "and values[3] >= 1:", "and values[3] >= 0:"),
    (K / "support.py", "threat priority ignored",
     "        g = group.get(e.obj_id, 2 if aim in zones else 3)", "        g = 2 if aim in zones else 3"),
    # validation and memory
    (K / "validate.py", "guided option not checked", "    if chosen not in offered:\n        return \"parameters match no",
     "    if False:\n        return \"parameters match no"),
    (K / "validate.py", "guided carrier acting allowed", "    if action[\"guided_obj_id\"] in carriers_acting:",
     "    if False:"),
    (K / "validate.py", "guided gate ignored", "        if not guided_enabled:", "        if False:"),
    (K / "memory.py", "sightings never capped",
     "    kept = sorted(latest.values(), key=lambda s: (-s[2], s[0]))[:MAX_SIGHTINGS]",
     "    kept = sorted(latest.values(), key=lambda s: (-s[2], s[0]))"),
    # live rules
    (E / "s35_live.py", "latency stop widened", "LATENCY_P99_MS = 200.0", "LATENCY_P99_MS = 201.0"),
    (E / "s35_live.py", "memory stop widened", "MEMORY_BYTES = 200_000", "MEMORY_BYTES = 200_001"),
    (E / "s35_live.py", "deadlock threshold widened", "DEADLOCK_WAIT = 600", "DEADLOCK_WAIT = 601"),
    (E / "s35_live.py", "friendly damage tolerated", "    if (facts.get(\"fire\") or {}).get(\"friendly_damage\", 0) > 0:",
     "    if (facts.get(\"fire\") or {}).get(\"friendly_damage\", 0) > 1:"),
    (E / "s35_live.py", "control not subtracted",
     "                d[f\"{sid} {side}\"] = round(sum(a) / len(a) - sum(b) / len(b), 6)",
     "                d[f\"{sid} {side}\"] = round(sum(a) / len(a), 6)"),
    (E / "s35_live.py", "reject threshold loosened", "REJECT_DBAR, PROMISING_DBAR, PROMISING_ZBAR = -0.5, 0.5, 0.5",
     "REJECT_DBAR, PROMISING_DBAR, PROMISING_ZBAR = -0.6, 0.5, 0.5"),
    (E / "s35_live.py", "promising threshold loosened", "REJECT_DBAR, PROMISING_DBAR, PROMISING_ZBAR = -0.5, 0.5, 0.5",
     "REJECT_DBAR, PROMISING_DBAR, PROMISING_ZBAR = -0.5, 0.4, 0.5"),
    (E / "s35_live.py", "breadth loosened", "            and positive >= 4 and not collapse", "            and positive >= 3 and not collapse"),
    (E / "s35_live.py", "collapse threshold loosened", "COLLAPSE_DS = -1.0", "COLLAPSE_DS = -1.1"),
    (E / "s35_live.py", "stage B remaining force ignored", "    if b_occupy >= 3 or b_remain >= 3:", "    if b_occupy >= 3:"),
    (E / "s35_live.py", "order not interleaved", "            order = ORDER[(index + repetition - 1) % 2]",
     "            order = ORDER[0]"),
    (E / "s35_live.py", "severe harm at the minimum",
     "all(g[\"candidate\"][\"win\"] < g[\"reference\"][\"win\"][\"min\"] for g in games)",
     "all(g[\"candidate\"][\"win\"] <= g[\"reference\"][\"win\"][\"min\"] for g in games)"),
    (E / "s35_live.py", "A2 gate ignores Dbar", "        if dbar is not None and dbar <= REJECT_DBAR:", "        if False:"),
    (E / "s35_live.py", "control games gated", "    candidate = [f for f in facts if f[\"tag\"] == \"s35\"]",
     "    candidate = list(facts)"),
    # offline rule
    (E / "s35_offline.py", "alert share loosened", "ALERT_SHARE = 0.5", "ALERT_SHARE = 0.4"),
    (E / "s35_offline.py", "retention share loosened", "RETENTION_SHARE = 0.5", "RETENTION_SHARE = 0.4"),
    (E / "s35_offline.py", "model floor loosened", "MODEL_FLOOR = 0.90", "MODEL_FLOOR = 0.89"),
    (E / "s35_offline.py", "fidelity not required", "    if not fidelity.get(\"decisions\") or fidelity.get(\"differing\", 1) != 0:",
     "    if False:"),
    # observer
    (E / "s35_capture.py", "memory size never recorded", "                if size > self.checks[\"memory_bytes_max\"]:",
     "                if False:"),
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
        subprocess.run([sys.executable, str(root / "scripts" / "build_s35_card.py")], cwd=root, env=env_for(root),
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
    payload = {"schema": "miaosuan-s35-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
