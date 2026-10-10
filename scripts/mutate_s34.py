"""Mutation test of the Sprint 34 integrated agent and its rules (``docs/SPRINT34_INTEGRATED_AGENT.md``).

    python scripts/mutate_s34.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, rebuilds the live card there when one
exists (so that its pins never kill a mutation by themselves), first runs the test modules unmutated (they must pass,
or every later kill would be vacuous), then plants each defect, runs the tests in a fresh process and records whether
they failed. Every planted defect's original text must occur exactly once. Record:
``evaluation/s34-integrated-agent/mutation.json``.
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
I = Path("src/miaosuan_agent/integrated")
E = Path("src/miaosuan_agent/evaluation")
OUT = REPO_ROOT / "evaluation" / "s34-integrated-agent" / "mutation.json"
CARD = Path("evaluation/s34-integrated-live-1/manifest.json")
TESTS = ("tests.test_s34_integrated", "tests.test_s34_world", "tests.test_s34_offline", "tests.test_s34_live",
         "tests.test_s34_gaps")
MUTATIONS = [
    # traffic
    (I / "traffic.py", "full planned stands stay open",
     "if self.stand(h) >= F.STACK_LIMIT}", "if self.stand(h) > F.STACK_LIMIT}"),
    (I / "traffic.py", "a full first hex counts as open",
     "return self.present.get(hex_, 0) < F.STACK_LIMIT", "return self.present.get(hex_, 0) <= F.STACK_LIMIT"),
    (I / "traffic.py", "destination cap off by one",
     "return self.stand(destination) < min(cap, F.STACK_LIMIT)", "return self.stand(destination) <= min(cap, F.STACK_LIMIT)"),
    (I / "traffic.py", "issued moves not registered",
     "        self.inbound[path[-1]] = self.inbound.get(path[-1], 0) + 1\n        for hex_ in path[:-1]:\n            self.transit",
     "        pass\n        for hex_ in path[:-1]:\n            self.transit"),
    (I / "traffic.py", "blockers never reported", "            if self.present.get(nxt, 0) >= F.STACK_LIMIT:",
     "            if False:"),
    # allocation
    (I / "allocation.py", "late arrivals feasible",
     "return eta is not None and world.step + eta + self.config.arrival_margin <= world.max_step",
     "return eta is not None"),
    (I / "allocation.py", "committed movers ignored", "            for k in range(p.committed, len(weights)):",
     "            for k in range(0, len(weights)):"),
    (I / "allocation.py", "objective room ignored", "                if room <= 0:\n                    break",
     "                if False:\n                    break"),
    (I / "allocation.py", "infeasible movers counted", "                        if self.feasible(world, eta):\n"
     "                            inbound.append", "                        if True:\n                            inbound.append"),
    (I / "config.py", "a single capture slot when clear", "    capture_clear: Tuple[float, ...] = (1.0, 0.15)",
     "    capture_clear: Tuple[float, ...] = (1.0, 0.15, 0.15, 0.15)"),
    (I / "allocation.py", "lift gain ignored",
     "                if walk is not None and self.feasible(world, walk) and walk < eta + cfg.lift_gain:\n                    continue",
     "                if False:\n                    continue"),
    # policy
    (I / "policy.py", "fire before occupation",
     "            if (F.OCCUPY in unit.actions and unit.hex not in occupy_taken",
     "            if (unit.obj_id not in fire and F.OCCUPY in unit.actions and unit.hex not in occupy_taken"),
    (I / "policy.py", "recovery never steps aside",
     "                intents[mover.obj_id] = Intent(\"recovery\", M.RESERVE, target,", "                _unused = (\"recovery\", M.RESERVE, target,"),
    (I / "policy.py", "destination cap not checked", "        if not traffic.accepts(intent.target, cap):\n            return None, \"destination stand at capacity\"",
     "        if False:\n            return None, \"destination stand at capacity\""),
    (I / "policy.py", "impact zones not avoided", "        blocked = traffic.blocked_for(unit.hex) | (hazards - {unit.hex})",
     "        blocked = traffic.blocked_for(unit.hex)"),
    (I / "policy.py", "first hex not checked", "        if not traffic.first_hex_open(path[0]):\n            return None, \"first hex full\"",
     "        if False:\n            return None, \"first hex full\""),
    (I / "policy.py", "fallback not counted", "                             fallbacks=memory.fallbacks + 1)",
     "                             fallbacks=memory.fallbacks)"),
    (I / "policy.py", "re-lift cooldown ignored", "            if action_type == F.GET_ON and world.step - step < cfg.lift_cooldown:",
     "            if False:"),
    (I / "policy.py", "boarding carrier sent on", "                intents[carrier_id] = Intent(\"transport\", HOLD_FOR_BOARDING, a.target,",
     "                intents[carrier_id] = Intent(\"transport\", M.CARRY, a.target,"),
    # fire
    (I / "fire.py", "targets not reserved", "        reserved.add(best[0])", "        pass"),
    (I / "fire.py", "indirect fire near own units", "            if any(F.hex_distance(e.hex, p) <= clearance for p in protected):\n                continue",
     "            if False:\n                continue"),
    (I / "fire.py", "attack level 0 accepted", "and values[2] >= 1:", "and values[2] >= 0:"),
    # validation
    (I / "validate.py", "actor not checked", "    if not F.is_int(action[\"actor\"]) or action[\"actor\"] != world.seat:\n        return",
     "    if False:\n        return"),
    (I / "validate.py", "listing not checked", "    if kind not in unit.actions:\n        return \"action type not listed for the unit\"",
     "    if False:\n        return \"action type not listed for the unit\""),
    (I / "validate.py", "options not checked", "        if chosen not in offered:\n            return \"parameters match no listed option\"",
     "        if False:\n            return \"parameters match no listed option\""),
    (I / "validate.py", "path adjacency not checked", "            if hex_ not in terrain.costs.neighbours(mode, here):\n                return",
     "            if False:\n                return"),
    (I / "validate.py", "two actions per unit", "    if obj_id in seen:\n        return \"second action for the same unit in one step\"",
     "    if False:\n        return \"second action for the same unit in one step\""),
    # transport
    (I / "transport.py", "unexecuted embark kept forever",
     "            elif world.step - since > ORDER_GRACE or carrier is None or on_ground is None:",
     "            elif carrier is None or on_ground is None:"),
    (I / "transport.py", "unloading away from the objective", "            if (at_target or overdue) and passenger_id in options(carrier, F.GET_OFF):",
     "            if passenger_id in options(carrier, F.GET_OFF):"),
    # memory
    (I / "memory.py", "sightings never capped", "    kept = sorted(latest.values(), key=lambda s: (-s[2], s[0]))[:MAX_SIGHTINGS]",
     "    kept = sorted(latest.values(), key=lambda s: (-s[2], s[0]))"),
    # live rules
    (E / "s34_live.py", "reconstruction mismatches ignored", "    if facts.get(\"reconstruction_mismatches\"):",
     "    if False:"),
    (E / "s34_live.py", "refusal share widened", "REFUSAL_SHARE = 0.02", "REFUSAL_SHARE = 0.05"),
    (E / "s34_live.py", "severe harm at the minimum", "all(g[\"candidate\"][\"win\"] < g[\"reference\"][\"win\"][\"min\"] for g in games)",
     "all(g[\"candidate\"][\"win\"] <= g[\"reference\"][\"win\"][\"min\"] for g in games)"),
    (E / "s34_live.py", "gate ignores structural stops", "    if any(stops.values()):\n        return {\"batch\": batch, \"open\": False, \"reason\": \"structural stop\",",
     "    if False:\n        return {\"batch\": batch, \"open\": False, \"reason\": \"structural stop\","),
    (E / "s34_live.py", "reject threshold loosened", "REJECT_ZBAR, PROMISING_ZBAR = -0.5, 0.5", "REJECT_ZBAR, PROMISING_ZBAR = -0.6, 0.5"),
    (E / "s34_live.py", "promising threshold loosened", "REJECT_ZBAR, PROMISING_ZBAR = -0.5, 0.5", "REJECT_ZBAR, PROMISING_ZBAR = -0.5, 0.4"),
    (E / "s34_live.py", "ledger state change ignored",
     "if not (close.get(\"integrity\") or {}).get(\"ok\") or close.get(\"state_changed\") or close.get(\"home_changed\"):",
     "if not (close.get(\"integrity\") or {}).get(\"ok\") or close.get(\"home_changed\"):"),
    (E / "s34_live.py", "losses never counted", "                losses += 1", "                losses += 0"),
    # offline rule
    (E / "s34_offline.py", "deadlock gate widened", "DEADLOCK_WAIT = 300", "DEADLOCK_WAIT = 301"),
    (E / "s34_offline.py", "non-inferiority loosened", "NON_INFERIORITY = 0.98", "NON_INFERIORITY = 0.97"),
    # observer
    (E / "s34_capture.py", "reconstruction never compared", "        if not (same and same_trace):", "        if False:"),
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
        subprocess.run([sys.executable, str(root / "scripts" / "build_s34_card.py")], cwd=root, env=env_for(root),
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
    payload = {"schema": "miaosuan-s34-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
