"""Mutation test of the Sprint 26 T6-S rules (``docs/SPRINT26_T6S_SHADOW.md``).

    python scripts/mutate_s26.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the Sprint 26 test
modules unmutated (they must pass, or every later kill would be vacuous), then plants each defect into the stagger
shadow (``experiments/t6s_stagger_shadow.py``), the analysis (``evaluation/s26_t6s.py``) or the driver
(``scripts/s26_t6s.py``), runs the tests in a fresh process and records whether they failed. Every planted defect's
original text must occur exactly once. The protocol pin test (``tests/test_s26_results.py``) is not among the tests
run, so a mutant is killed by behaviour, never by its changed digest. Writes (or with ``--check`` compares)
``evaluation/s26-t6s-shadow/mutation.json``.
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
SHADOW = Path("src/miaosuan_agent/experiments/t6s_stagger_shadow.py")
RULES = Path("src/miaosuan_agent/evaluation/s26_t6s.py")
DRIVER = Path("scripts/s26_t6s.py")
TESTS = ("tests.test_t6s_stagger_shadow", "tests.test_s26_t6s", "tests.test_s26_driver")
OUT = REPO_ROOT / "evaluation" / "s26-t6s-shadow" / "mutation.json"
MUTATIONS = [
    # -- the shadow: threat, grouping, leader, eligibility, release, wait bound, episode limit, action change
    (SHADOW, "route prefix four hexes", "ROUTE_PREFIX = 5\n", "ROUTE_PREFIX = 4\n"),
    (SHADOW, "range boundary excluded", '        if any(hex_distance(enemy["cur_hex"], h) <= reach for h in hexes):',
     '        if any(hex_distance(enemy["cur_hex"], h) < reach for h in hexes):'),
    (SHADOW, "start hex not inspected", '    hexes = [unit["cur_hex"]] + [h for h in list(route or ())[:ROUTE_PREFIX]',
     '    hexes = [] + [h for h in list(route or ())[:ROUTE_PREFIX]'),
    (SHADOW, "minimum group of three", "MIN_GROUP = 2\n", "MIN_GROUP = 3\n"),
    (SHADOW, "grouped by start hex only", '            eligible.setdefault((own[m.unit]["cur_hex"], m.route[0]), []).append(m)',
     '            eligible.setdefault((own[m.unit]["cur_hex"], 0), []).append(m)'),
    (SHADOW, "grouped by first hex only", '            eligible.setdefault((own[m.unit]["cur_hex"], m.route[0]), []).append(m)',
     '            eligible.setdefault((0, m.route[0]), []).append(m)'),
    (SHADOW, "every member must be exposed", "        if not any(m.exposed for m in members):",
     "        if not all(m.exposed for m in members):"),
    (SHADOW, "no threat required", "        if not any(m.exposed for m in members):", "        if False:"),
    (SHADOW, "leader by first-hex time", "    return (member.arrival, member.cost, len(member.route), member.unit)",
     "    return (member.hex_time, member.cost, len(member.route), member.unit)"),
    (SHADOW, "ties by unit id first", "    return (member.arrival, member.cost, len(member.route), member.unit)",
     "    return (member.unit, member.arrival, member.cost, len(member.route))"),
    (SHADOW, "ties ignore the route cost", "    return (member.arrival, member.cost, len(member.route), member.unit)",
     "    return (member.arrival, len(member.route), member.unit)"),
    (SHADOW, "moving units eligible",
     "    if unit.get(\"move_path\") or (isinstance(speed, (int, float)) and not isinstance(speed, bool) and speed > 0):",
     "    if False:"),
    (SHADOW, "positive speed ignored",
     "    if unit.get(\"move_path\") or (isinstance(speed, (int, float)) and not isinstance(speed, bool) and speed > 0):",
     "    if unit.get(\"move_path\"):"),
    (SHADOW, "listing not checked", "    if MOVE not in (valid.get(unit_id) or {}):", "    if False:"),
    (SHADOW, "transport commitment ignored", "        return MoverCheck(False, \"transport_committed\")",
     "        pass"),
    (SHADOW, "several MOVEs tolerated",
     '    if sum(1 for a in actions if a.get("type") == MOVE and a.get("obj_id") == unit_id) != 1:',
     '    if sum(1 for a in actions if a.get("type") == MOVE and a.get("obj_id") == unit_id) < 1:'),
    (SHADOW, "release without the reference leaving",
     "            if ref_unit is None or (ref_hex is not None and ref_hex != ep.origin):", "            if True:"),
    (SHADOW, "release only after the reference leaves the first hex too",
     "            if ref_unit is None or (ref_hex is not None and ref_hex != ep.origin):",
     "            if ref_unit is None or (ref_hex is not None and ref_hex not in (ep.origin, ep.first_hex)):"),
    (SHADOW, "released member never becomes the reference",
     "                if moved:\n                    ep = replace(ep, ref=head",
     "                if False:\n                    ep = replace(ep, ref=head"),
    (SHADOW, "member without a MOVE becomes the reference",
     "                if moved:\n                    ep = replace(ep, ref=head",
     "                if True:\n                    ep = replace(ep, ref=head"),
    (SHADOW, "timeout one step early",
     "    return cur_step - episode.ref_step > STALL_FACTOR * episode.ref_hex_time + STALL_SLACK",
     "    return cur_step - episode.ref_step >= STALL_FACTOR * episode.ref_hex_time + STALL_SLACK"),
    (SHADOW, "stall factor three", "STALL_FACTOR = 2\n", "STALL_FACTOR = 3\n"),
    (SHADOW, "no stall slack", "STALL_SLACK = 10\n", "STALL_SLACK = 0\n"),
    (SHADOW, "no wait bound", "            if stalled(ep, cur_step):", "            if False:"),
    (SHADOW, "timeout releases the head only", "                pending = []\n            break",
     "                pending = pending[1:]\n            break"),
    (SHADOW, "absent follower kept in the queue",
     "            if head_unit is None or (head_hex is not None and head_hex != ep.origin):", "            if False:"),
    (SHADOW, "members not spent on completion", "                spent[unit_id] = ep.origin", "                pass"),
    (SHADOW, "never re-armed", "        if h is not None and h != spent[unit_id]:", "        if False:"),
    (SHADOW, "re-armed at once", "        if h is not None and h != spent[unit_id]:", "        if True:"),
    (SHADOW, "members of active episodes eligible", "    busy = {u for ep in active for u in ep.chain}", "    busy = set()"),
    (SHADOW, "pending MOVEs pass", "        if unit_id in pending_of:\n            for i in idx:",
     "        if False:\n            for i in idx:"),
    (SHADOW, "non-play decisions examined", "    if stage != PLAY_STAGE:", "    if False:"),
    (SHADOW, "the leader withheld instead of the last follower", "        for m in chain[1:]:\n            withheld.append(m.index)",
     "        for m in chain[:-1]:\n            withheld.append(m.index)"),
    # -- the analysis: independent check, onward risk, follow-up, stops, disposition
    (RULES, "independent check skipped", "            problem = self.explain(frame, a, kept, base)", "            problem = None"),
    (RULES, "independent bound loosened", '                              "bound": (len(group) - 1) * (2 * max(times) + 11)}',
     '                              "bound": (len(group) - 1) * (2 * max(times) + 11) * 100}'),
    (RULES, "independent second run allowed", "        if self.closed.get(unit_id) == here:", "        if False:"),
    (RULES, "independent check: own free-flow time not required", "        if self.travel(unit, route) is None:",
     "        if False:"),
    (RULES, "first ownership at the start counted", "    after = first_k is not None and first_k > k",
     "    after = first_k is not None and first_k >= k"),
    (RULES, "the leader counted as delayed", '    row["onward"] = {u: follower_onward(side, row, u, i, lost) for i, u in enumerate(chain) if i > 0}',
     '    row["onward"] = {u: follower_onward(side, row, u, i, lost) for i, u in enumerate(chain) if i >= 0}'),
    (RULES, "projected wait includes the own hex time",
     '    row["projected_waits"] = [sum(row["hex_times"][:i]) for i in range(1, len(chain))]',
     '    row["projected_waits"] = [sum(row["hex_times"][:i + 1]) for i in range(1, len(chain))]'),
    (RULES, "follow-up co-location on the start hex counted",
     '        shared = {h for h, n in here.items() if n >= 2 and h != row["origin"] and h is not None}',
     '        shared = {h for h, n in here.items() if n >= 2 and h is not None}'),
    (RULES, "certificate ignores the prefix", '            "on_policy_baseline_v2_witness": a.side.population == "HH" or prefix_supported(a.side, first),',
     '            "on_policy_baseline_v2_witness": True,'),
    (RULES, "stop A: nine episodes suffice", "STOP_A_MIN_EPISODES = 10\n", "STOP_A_MIN_EPISODES = 9\n"),
    (RULES, "stop A: pooled over side-games",
     '                               "met": len(hh) != HH_SIDE_GAMES or any(n < STOP_A_MIN_EPISODES for n in per.values())}',
     '                               "met": sum(per.values()) < STOP_A_MIN_EPISODES * HH_SIDE_GAMES}'),
    (RULES, "stop A: a missing side-game ignored",
     '                               "met": len(hh) != HH_SIDE_GAMES or any(n < STOP_A_MIN_EPISODES for n in per.values())}',
     '                               "met": any(n < STOP_A_MIN_EPISODES for n in per.values())}'),
    (RULES, "stop B: three scenario-sides suffice", "STOP_B_MIN_SCENARIO_SIDES = 4\n", "STOP_B_MIN_SCENARIO_SIDES = 3\n"),
    (RULES, "stop B: side-games counted", "    sides = sorted({a.side.scenario_side for a in h0 if a.shadow.episodes})",
     "    sides = sorted({a.side.label for a in h0 if a.shadow.episodes})"),
    (RULES, "stop C: exactly half fails", '"evaluable": n > 0, "met": n == 0 or 2 * risk > n}',
     '"evaluable": n > 0, "met": n == 0 or 2 * risk >= n}'),
    (RULES, "stop C: no episode passes", '"evaluable": n > 0, "met": n == 0 or 2 * risk > n}',
     '"evaluable": n > 0, "met": n > 0 and 2 * risk > n}'),
    (RULES, "stop C: replicas counted", "    n = len(distinct)\n", "    n = sum(len(v) for v in distinct.values())\n"),
    (RULES, "stop C: risk read from the first replica only",
     '    risk = sum(1 for occurrences in distinct.values() if any(r["first_owner_risk"] for _, r in occurrences))',
     '    risk = sum(1 for occurrences in distinct.values() if occurrences[0][1]["first_owner_risk"])'),
    (RULES, "disposition: capture risk before opportunity",
     '    elif stop["A_hh_opportunity"]["met"] or stop["B_h0_generality"]["met"]:\n        outcome = DISPOSITIONS[1]\n'
     '    elif stop["C_onward_capture_conflict"]["met"]:\n        outcome = DISPOSITIONS[2]',
     '    elif stop["C_onward_capture_conflict"]["met"]:\n        outcome = DISPOSITIONS[2]\n'
     '    elif stop["A_hh_opportunity"]["met"] or stop["B_h0_generality"]["met"]:\n        outcome = DISPOSITIONS[1]'),
    (RULES, "disposition: unexplained differences ignored",
     "    invalid = not fidelity_ok or not integrity_ok or unexplained != 0",
     "    invalid = not fidelity_ok or not integrity_ok"),
    # -- the driver
    (DRIVER, "recorded actions in file order", "            out[(header[\"game_id\"], faction)] = [steps[s] for s in sorted(steps)]",
     "            out[(header[\"game_id\"], faction)] = list(steps.values())"),
    (DRIVER, "side colours swapped", '    colour = "red" if faction == 0 else "blue"\n    if population == "HH":',
     '    colour = "blue" if faction == 0 else "red"\n    if population == "HH":'),
    (DRIVER, "split parts may exceed the limit", "        if parts[-1] and len(dump(trial).encode(\"utf-8\")) > PUBLIC_LIMIT:",
     "        if parts[-1] and len(dump(trial).encode(\"utf-8\")) > 2 * PUBLIC_LIMIT:"),
    (DRIVER, "fidelity: gate episodes not compared",
     '    put("HH gate episodes of the frozen T6-G gate", S19_GATE_EPISODES, loader.gate_episodes,',
     '    put("HH gate episodes of the frozen T6-G gate", S19_GATE_EPISODES, S19_GATE_EPISODES,'),
    (DRIVER, "fidelity: side-games not compared", '        put(f"{pop} side-games", value, len(loader.analyses[pop]))',
     '        put(f"{pop} side-games", value, value)'),
    (DRIVER, "fidelity: separate pass not compared",
     '        INTEGRITY["H0 v2 differs from recorded v0"], loader.recorded_differs)',
     '        INTEGRITY["H0 v2 differs from recorded v0"], INTEGRITY["H0 v2 differs from recorded v0"])'),
    (DRIVER, "moving damage counts stationary units",
     '        out[pop] = {"stacked": sum(v for k, v in rows.items() if k.startswith("moving") and k.endswith("stacked")),',
     '        out[pop] = {"stacked": sum(v for k, v in rows.items() if k.endswith("stacked")),'),
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
    for source, name, old, _ in MUTATIONS:
        count = (REPO_ROOT / source).read_text(encoding="utf-8").count(old)
        if count != 1:
            raise SystemExit(f"mutation {name!r}: original text occurs {count} times")
    passed, log = tests_pass({})
    if not passed:
        raise SystemExit("the unmutated tests fail in the temporary copy; kills would be vacuous\n" + log)
    results = [run(m) for m in MUTATIONS]
    sources = (SHADOW, RULES, DRIVER) + tuple(Path(f"{t.replace('.', '/')}.py") for t in TESTS)
    payload = {"schema": "miaosuan-s26-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
