"""Mutation test of the Sprint 28 T12-O1 rules (``docs/SPRINT28_T12_O1.md``).

    python scripts/mutate_s28.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the Sprint 28 test
modules unmutated (they must pass, or every later kill would be vacuous), then plants each defect into the dispersion
shadow (``experiments/t12_dispersion_shadow.py``), the analysis (``evaluation/s28_t12.py``) or the driver
(``scripts/s28_t12.py``), runs the tests in a fresh process and records whether they failed. Every planted defect's
original text must occur exactly once. The protocol pin test (``tests/test_s28_results.py``) is not among the tests
run, so a mutant is killed by behaviour, never by its changed digest. Writes (or with ``--check`` compares)
``evaluation/s28-t12-o1/mutation.json``.
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
SHADOW = Path("src/miaosuan_agent/experiments/t12_dispersion_shadow.py")
RULES = Path("src/miaosuan_agent/evaluation/s28_t12.py")
DRIVER = Path("scripts/s28_t12.py")
TESTS = ("tests.test_t12_dispersion_shadow", "tests.test_s28_t12", "tests.test_s28_driver")
OUT = REPO_ROOT / "evaluation" / "s28-t12-o1" / "mutation.json"
MUTATIONS = [
    # -- the shadow: idle levels, geometry, trigger, legality, admissibility, batch, action change, hold
    (SHADOW, "minimum idle three", "MIN_IDLE = 2\n", "MIN_IDLE = 3\n"),
    (SHADOW, "stacking limit five", "STACK_LIMIT = 4\n", "STACK_LIMIT = 5\n"),
    (SHADOW, "speed ignored", '    if positive(u.get("speed")):\n        return IDLE_LEVELS[0]',
     '    if False:\n        return IDLE_LEVELS[0]'),
    (SHADOW, "observed route ignored", '    if u.get("move_path"):\n        return IDLE_LEVELS[1]',
     '    if False:\n        return IDLE_LEVELS[1]'),
    (SHADOW, "stop flag ignored", '    stopping = extra.get("stop") == 0 or positive(extra.get("move_to_stop_remain_time"))\n',
     '    stopping = False or positive(extra.get("move_to_stop_remain_time"))\n'),
    (SHADOW, "stop transition time ignored",
     '    stopping = extra.get("stop") == 0 or positive(extra.get("move_to_stop_remain_time"))\n',
     '    stopping = extra.get("stop") == 0\n'),
    (SHADOW, "state transition ignored", '    if stopping or positive(extra.get("change_state_remain_time")):',
     '    if stopping:'),
    (SHADOW, "get-on transition ignored",
     '    if positive(extra.get("get_on_remain_time")) or positive(extra.get("get_off_remain_time")):',
     '    if positive(extra.get("get_off_remain_time")):'),
    (SHADOW, "get-off transition ignored",
     '    if positive(extra.get("get_on_remain_time")) or positive(extra.get("get_off_remain_time")):',
     '    if positive(extra.get("get_on_remain_time")):'),
    (SHADOW, "suppression ignored", '    if u.get("keep"):\n        return IDLE_LEVELS[4]', '    if False:\n        return IDLE_LEVELS[4]'),
    (SHADOW, "baseline MOVE tolerated", "    if MOVE in types:\n        return IDLE_LEVELS[5]",
     "    if False:\n        return IDLE_LEVELS[5]"),
    (SHADOW, "other baseline action tolerated", "    if types:\n        return IDLE_LEVELS[6]",
     "    if False:\n        return IDLE_LEVELS[6]"),
    (SHADOW, "aircraft counted as ground",
     '    return bool(u) and u.get("type") in GROUND and hex_int(u.get("cur_hex")) is not None',
     '    return bool(u) and hex_int(u.get("cur_hex")) is not None'),
    (SHADOW, "neighbours ignore the map edge",
     "            if 0 <= rr < rows and 0 <= cc < cols and hex_distance(h, rr * 100 + cc) == 1:",
     "            if hex_distance(h, rr * 100 + cc) == 1:"),
    (SHADOW, "neighbours up to distance two",
     "            if 0 <= rr < rows and 0 <= cc < cols and hex_distance(h, rr * 100 + cc) == 1:",
     "            if 0 <= rr < rows and 0 <= cc < cols and hex_distance(h, rr * 100 + cc) <= 2:"),
    (SHADOW, "passability ignored", "any(n in ctx.costs.neighbours(m, centre) for m in GROUND_MODES)", "True"),
    (SHADOW, "trigger ignores the room",
     "        trigger = len(idle) >= MIN_IDLE and any(p and k < STACK_LIMIT for _, k, p in cells)",
     "        trigger = len(idle) >= MIN_IDLE"),
    (SHADOW, "held units idle", '        idle = tuple(o for o, lv in levels if lv == "idle" and o not in held)',
     '        idle = tuple(o for o, lv in levels if lv == "idle")'),
    (SHADOW, "listing not checked", "    if MOVE not in (ctx.valid.get(unit_id) or {}):\n        return LEGAL_REASONS[1]",
     "    if False:\n        return LEGAL_REASONS[1]"),
    (SHADOW, "roadblocks ignored", "    blocked = ctx.roadblocks if mode in ROADBLOCKED_MODES else frozenset()",
     "    blocked = frozenset()"),
    (SHADOW, "roadblocks stop infantry", "    blocked = ctx.roadblocks if mode in ROADBLOCKED_MODES else frozenset()",
     "    blocked = ctx.roadblocks"),
    (SHADOW, "gate path check skipped",
     "    if _path_problem([dest], centre, mode, blocked, _RouterView(ctx.costs)) is not None:", "    if False:"),
    (SHADOW, "stack full only above four", "    if counts.get(dest, 0) >= STACK_LIMIT:\n        return LEGAL_REASONS[4]",
     "    if counts.get(dest, 0) > STACK_LIMIT:\n        return LEGAL_REASONS[4]"),
    (SHADOW, "objective hexes admissible", "    if dest in ctx.flags:\n        return ADMISSIBLE_REASONS[1]",
     "    if False:\n        return ADMISSIBLE_REASONS[1]"),
    (SHADOW, "enemy hexes admissible", "    if dest in enemy_hexes:\n        return ADMISSIBLE_REASONS[2]",
     "    if False:\n        return ADMISSIBLE_REASONS[2]"),
    (SHADOW, "route hexes admissible", "    if dest in routes:\n        return ADMISSIBLE_REASONS[3]",
     "    if False:\n        return ADMISSIBLE_REASONS[3]"),
    (SHADOW, "observed routes not collected",
     '        out.update(h for h in (u.get("move_path") or ()) if hex_int(h) is not None)', "        pass"),
    (SHADOW, "baseline routes not collected",
     '            out.update(h for h in (a.get("move_path") or ()) if hex_int(h) is not None)', "            pass"),
    (SHADOW, "holder by unit id only", "        order = sorted(idle, key=lambda o: (len(per[o][1]), o))",
     "        order = sorted(idle)"),
    (SHADOW, "holder with the most destinations", "        order = sorted(idle, key=lambda o: (len(per[o][1]), o))",
     "        order = sorted(idle, key=lambda o: (-len(per[o][1]), o))"),
    (SHADOW, "holder dispersed too",
     '        checks: List[UnitCheck] = [UnitCheck(order[0], per[order[0]][0], per[order[0]][1], "holder")]\n'
     '        for o in order[1:]:',
     '        checks: List[UnitCheck] = []\n        for o in order:'),
    (SHADOW, "room ignores this decision's moves",
     "            room = [n for n in admissible if counts.get(n, 0) + assigned.get(n, 0) < STACK_LIMIT]",
     "            room = [n for n in admissible if counts.get(n, 0) < STACK_LIMIT]"),
    (SHADOW, "destination by cost first",
     "            dest = min(room, key=lambda n: (counts.get(n, 0) + assigned.get(n, 0), entry_cost(ctx, u, centre, n), n))",
     "            dest = min(room, key=lambda n: (entry_cost(ctx, u, centre, n), counts.get(n, 0) + assigned.get(n, 0), n))"),
    (SHADOW, "destination ignores the cost",
     "            dest = min(room, key=lambda n: (counts.get(n, 0) + assigned.get(n, 0), entry_cost(ctx, u, centre, n), n))",
     "            dest = min(room, key=lambda n: (counts.get(n, 0) + assigned.get(n, 0), n))"),
    (SHADOW, "assignments not counted", "            assigned[dest] = assigned.get(dest, 0) + 1", "            pass"),
    (SHADOW, "count reset per objective",
     "        per: Dict[Any, Tuple[Tuple[Tuple[int, str], ...], Tuple[int, ...]]] = {}\n",
     "        per: Dict[Any, Tuple[Tuple[Tuple[int, str], ...], Tuple[int, ...]]] = {}\n        assigned = {}\n"),
    (SHADOW, "legal tier without a dispersal", '        tier = any(c.outcome == "dispersed" for c in checks)',
     "        tier = True"),
    (SHADOW, "objectives in decreasing order",
     "    for centre in sorted(c for c, flag in ctx.flags.items() if hex_int(c) is not None and flag == ctx.faction):",
     "    for centre in sorted((c for c, flag in ctx.flags.items() if hex_int(c) is not None and flag == ctx.faction), "
     "reverse=True):"),
    (SHADOW, "unheld objectives examined",
     "    for centre in sorted(c for c, flag in ctx.flags.items() if hex_int(c) is not None and flag == ctx.faction):",
     "    for centre in sorted(c for c, flag in ctx.flags.items() if hex_int(c) is not None):"),
    (SHADOW, "held MOVEs pass", '        if a.get("type") == MOVE and a.get("obj_id") in holds:', "        if False:"),
    (SHADOW, "no release on objective loss",
     "    if ctx.flags.get(objective) != ctx.faction:\n        return RELEASE_REASONS[0]",
     "    if False:\n        return RELEASE_REASONS[0]"),
    (SHADOW, "no release on absence", "    if unit_id not in ctx.own:\n        return RELEASE_REASONS[1]",
     "    if False:\n        return RELEASE_REASONS[1]"),
    (SHADOW, "appended before the baseline actions",
     "    out = tuple(a for i, a in enumerate(actions) if i not in kept) + tuple(added)",
     "    out = tuple(added) + tuple(a for i, a in enumerate(actions) if i not in kept)"),
    (SHADOW, "two-hex dispersal route",
     '            added.append({"actor": ctx.actor, "obj_id": unit_id, "type": MOVE, "move_path": [dest]})',
     '            added.append({"actor": ctx.actor, "obj_id": unit_id, "type": MOVE, "move_path": [dest, dest]})'),
    (SHADOW, "held units examined as holders", "    checks = evaluate(ctx, holds)", "    checks = evaluate(ctx)"),
    (SHADOW, "hold not recorded", "            holds[unit_id] = (check.objective, dest, ctx.cur_step)", "            pass"),
    (SHADOW, "non-play decisions examined",
     "    if ctx.stage != PLAY_STAGE:\n        return DispersionResult(", "    if False:\n        return DispersionResult("),
    # -- the analysis: independent check, episodes, onward, damage, census, stops, interaction, disposition
    (RULES, "check accepts any removal", '            if a.get("type") != 1 or a.get("obj_id") not in self.dispersed:',
     "            if False:"),
    (RULES, "check never releases", "            if f.flags.get(self.dispersed[u]) != faction or u not in f.own:",
     "            if False:"),
    (RULES, "check without a holder", "            if not stay:", "            if False:"),
    (RULES, "check ignores this decision's appended moves",
     "        if counts.get(n, 0) + added_to.get(n, 0) >= ts.STACK_LIMIT:", "        if counts.get(n, 0) >= ts.STACK_LIMIT:"),
    (RULES, "check accepts route hexes", '        if n in routes:\n            return "the destination is on an own route"',
     '        if False:\n            return "the destination is on an own route"'),
    (RULES, "check idle ignores suppression", '                and not u.get("keep") and unit_id not in acted)',
     "                and unit_id not in acted)"),
    (RULES, "check accepts a roadblock", "        if mode in ROADBLOCKED_MODES and n in self.side.roadblocks:",
     "        if False:"),
    (RULES, "episodes merge across gaps", "            if k is not None and k == prev + 1:", "            if k is not None:"),
    (RULES, "episode key without the idle units",
     '    return (side.scenario_side, row["objective"], row["start_step"], tuple(sorted(row["idle"])))',
     '    return (side.scenario_side, row["objective"], row["start_step"])'),
    (RULES, "claimant includes held objectives", '                        "claimant": kind == DEST_UNHELD,',
     '                        "claimant": kind != DEST_NOT_OBJECTIVE,'),
    (RULES, "onward reads past the release", "    end = release if release is not None else len(frames)",
     "    end = len(frames)"),
    (RULES, "first ownership before the order counted", "            after = fo is not None and fo > g.k",
     "            after = fo is not None"),
    (RULES, "holder departure ignored",
     '        if any(a.get("type") == 1 and a.get("obj_id") == holder for a in g.actions):', "        if False:"),
    (RULES, "damage includes moving victims",
     '        if r["victim_class"] not in ("infantry", "vehicle", "artillery") or r["aboard"] or r["moving"] or not r["on_objective"]:',
     '        if r["victim_class"] not in ("infantry", "vehicle", "artillery") or r["aboard"] or not r["on_objective"]:'),
    (RULES, "the event decision counted as earlier",
     '        earlier = [j for j in range(run, k) if j in by_obj.get(coord, {})] if run is not None else []',
     '        earlier = [j for j in range(run, k + 1) if j in by_obj.get(coord, {})] if run is not None else []'),
    (RULES, "prefix always supported",
     "    return all([dict(a) for a in side.recorded[j]] == [dict(a) for a in side.frames[j].actions] for j in range(upto))",
     "    return True"),
    (RULES, "idle level boundary off by one", '    return level == "idle" or order.index(level) > order.index(upto)',
     '    return level == "idle" or order.index(level) >= order.index(upto)'),
    (RULES, "majority at one half", "    return 2 * part > whole", "    return 2 * part >= whole"),
    (RULES, "stop needs two episodes", "STOP_MIN_EPISODES_PER_HH_SIDE_GAME = 1\n", "STOP_MIN_EPISODES_PER_HH_SIDE_GAME = 2\n"),
    (RULES, "stop ignores a missing side-game",
     '            "met": len(hh) != HH_SIDE_GAMES or any(n < STOP_MIN_EPISODES_PER_HH_SIDE_GAME for n in per_hh.values())},',
     '            "met": any(n < STOP_MIN_EPISODES_PER_HH_SIDE_GAME for n in per_hh.values())},'),
    (RULES, "stop pooled over side-games",
     '            "met": len(hh) != HH_SIDE_GAMES or any(n < STOP_MIN_EPISODES_PER_HH_SIDE_GAME for n in per_hh.values())},',
     '            "met": sum(per_hh.values()) < len(per_hh)},'),
    (RULES, "legality gate ignores a missing side-game",
     '            "met": len(hh) != HH_SIDE_GAMES or any(n < 1 for n in legal_hh.values())},',
     '            "met": any(n < 1 for n in legal_hh.values())},'),
    (RULES, "legality gate reads trigger episodes", "    legal_hh = {a.side.label: len(a.legal_episodes) for a in hh}",
     "    legal_hh = {a.side.label: len(a.trigger_episodes) for a in hh}"),
    (RULES, "legality before opportunity",
     '    elif stop["opportunity_stop"]["met"]:\n        outcome = DISPOSITIONS[1]\n    elif stop["legality_gate"]["met"]:\n'
     '        outcome = DISPOSITIONS[2]',
     '    elif stop["legality_gate"]["met"]:\n        outcome = DISPOSITIONS[2]\n    elif stop["opportunity_stop"]["met"]:\n'
     '        outcome = DISPOSITIONS[1]'),
    (RULES, "interaction ignored", '    elif any(inter["met"].values()):', "    elif False:"),
    (RULES, "unexplained differences ignored", "    if not fidelity_ok or not integrity_ok or unexplained != 0:",
     "    if not fidelity_ok or not integrity_ok:"),
    (RULES, "interaction read in HH only", "    out[\"met\"] = {c: any(out[g][c] for g in groups) for c in INTERACTION_CRITERIA}",
     "    out[\"met\"] = {c: out[\"HH\"][c] for c in INTERACTION_CRITERIA}"),
    (RULES, "interaction counts replicas", "        eps = [occ[0][1] for occ in distinct(part, \"legal\").values()]",
     "        eps = [r for occ in distinct(part, \"legal\").values() for _, r in occ]"),
    (RULES, "certificate ignores the prefix",
     '            "on_policy_baseline_v2_witness": a.side.population == "HH" or prefix_supported(a.side, first),',
     '            "on_policy_baseline_v2_witness": True,'),
    # -- the driver
    (DRIVER, "recorded actions in file order",
     '            out[(header["game_id"], faction)] = [steps[s] for s in sorted(steps)]',
     '            out[(header["game_id"], faction)] = list(steps.values())'),
    (DRIVER, "side colours swapped", '    colour = "red" if faction == 0 else "blue"\n    if population == "HH":',
     '    colour = "blue" if faction == 0 else "red"\n    if population == "HH":'),
    (DRIVER, "split parts may exceed the limit", '        if parts[-1] and len(dump(trial).encode("utf-8")) > PUBLIC_LIMIT:',
     '        if parts[-1] and len(dump(trial).encode("utf-8")) > 2 * PUBLIC_LIMIT:'),
    (DRIVER, "refusal not invalid", '    data = {**head, "disposition": st.DISPOSITIONS[0], "fidelity_ok": bool(fid_ok),',
     '    data = {**head, "disposition": st.DISPOSITIONS[4], "fidelity_ok": bool(fid_ok),'),
    (DRIVER, "two seat ids tolerated", "    return (next(iter(actors)) if len(actors) == 1 else None), len(actors) == 1",
     "    return (next(iter(actors)) if actors else None), len(actors) >= 1"),
    (DRIVER, "input pins ignored", '        if sha256(REPO_ROOT / committed[key]["path"]) != committed[key]["sha256"]:',
     "        if False:"),
    (DRIVER, "source pins ignored", "        if normalised(REPO_ROOT / path) != digest:", "        if False:"),
    (DRIVER, "stacked anchor shifted", 'STATIONARY_ON_OBJECTIVE = {"H0": (40, 13), "HH": (10, 3)}',
     'STATIONARY_ON_OBJECTIVE = {"H0": (41, 13), "HH": (10, 3)}'),
    (DRIVER, "move-order anchor shifted", 'MOVE_ORDERS = {"H0": 509, "HH": 416}', 'MOVE_ORDERS = {"H0": 510, "HH": 416}'),
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


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=900)
    return done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    passed, _ = tests_pass({source: text.replace(old, new)})
    return {"mutation": name, "module": source.as_posix(), "killed": not passed}


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    names = [m[1] for m in MUTATIONS]
    if len(set(names)) != len(names):
        raise SystemExit("two mutations share a name")
    for source, name, old, _ in MUTATIONS:
        count = (REPO_ROOT / source).read_text(encoding="utf-8").count(old)
        if count != 1:
            raise SystemExit(f"mutation {name!r}: original text occurs {count} times")
    passed, log = tests_pass({})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = [run(m) for m in MUTATIONS]
    sources = (SHADOW, RULES, DRIVER) + tuple(Path(f"{t.replace('.', '/')}.py") for t in TESTS)
    payload = {"schema": "miaosuan-s28-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
