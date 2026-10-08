"""Mutation test of the Sprint 23 design logic (``docs/SPRINT23_T2_POLICY_DESIGN.md``).

    python scripts/mutate_s23.py [--check]

Copies ``src``, ``tests``, ``scripts`` and ``evaluation`` to a temporary directory, first runs the Sprint 23 test
modules unmutated (they must pass, or every later kill would be vacuous), then plants each defect into the proposed
candidate (``experiments/t2_transport_x1.py``), the rules module (``evaluation/s23_design.py``) or the study driver
(``scripts/s23_t2_design.py``), runs the tests in a fresh process and records whether they failed. Every planted
defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s23-t2-policy-design/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t2_transport_x1.py")
RULES = Path("src/miaosuan_agent/evaluation/s23_design.py")
DRIVER = Path("scripts/s23_t2_design.py")
TESTS = ("tests.test_t2_transport_x1", "tests.test_s23_design", "tests.test_s23_driver")
OUT = REPO_ROOT / "evaluation" / "s23-t2-policy-design" / "mutation.json"
MUTATIONS = [
    # -- the candidate: actions, the nine conditions, the time model, matching, admission
    (CANDIDATE, "embark schema: unit and target swapped",
     '        actions[index] = {"actor": seat, "obj_id": pair.infantry, "type": EMBARK,\n'
     '                          "target_obj_id": option["target_obj_id"]}',
     '        actions[index] = {"actor": seat, "obj_id": pair.carrier, "type": EMBARK,\n'
     '                          "target_obj_id": pair.infantry}'),
    (CANDIDATE, "embark appended instead of replacing the move in place",
     '        actions[index] = {"actor": seat, "obj_id": pair.infantry, "type": EMBARK,\n'
     '                          "target_obj_id": option["target_obj_id"]}',
     '        del actions[index]\n'
     '        actions.append({"actor": seat, "obj_id": pair.infantry, "type": EMBARK,\n'
     '                        "target_obj_id": option["target_obj_id"]})'),
    (CANDIDATE, "no carrier hold at the trigger",
     '        withhold_move(actions, pair.carrier, changes, "EMBARK_REQUESTED")', '        pass'),
    (CANDIDATE, "the hold withholds every carrier action",
     '        if actions[i].get("type") == MOVE:\n            changes.append({"kind": "carrier-move-withheld"',
     '        if True:\n            changes.append({"kind": "carrier-move-withheld"'),
    (CANDIDATE, "condition 2: units of a past episode eligible again",
     "            if (inf_id in used or car_id in used or uncontrolled(view, inf_id)",
     "            if (uncontrolled(view, inf_id)"),
    (CANDIDATE, "condition 2: a moving carrier eligible",
     "                    or not p1.quiet(inf) or not p1.quiet(car)):", "                    or not p1.quiet(inf)):"),
    (CANDIDATE, "condition 3: the listing not required",
     "            option = p1.listed_option(view.valid, inf_id, EMBARK, car_id)",
     '            option = {"target_obj_id": car_id}'),
    (CANDIDATE, "condition 4: the carrier's MOVE not required",
     '                    or actions[theirs[0]].get("type") != MOVE or not actions[mine[0]].get("move_path")',
     '                    or not actions[mine[0]].get("move_path")'),
    (CANDIDATE, "condition 5: different destinations accepted",
     "            if inf_path[-1] != dest or not is_objective(observation, dest):",
     "            if not is_objective(observation, dest):"),
    (CANDIDATE, "condition 5: a non-objective destination accepted",
     "            if inf_path[-1] != dest or not is_objective(observation, dest):",
     "            if inf_path[-1] != dest:"),
    (CANDIDATE, "condition 6: a tie with the foot arrival accepted",
     "    if not (foot >= max_step or foot > transported):", "    if not (foot >= max_step or foot >= transported):"),
    (CANDIDATE, "condition 7: arrival at the last step accepted",
     "    if not (transported < max_step and foot - transported > 0):",
     "    if not (transported <= max_step and foot - transported > 0):"),
    (CANDIDATE, "unable on foot: arrival at the last step counted as able",
     "    return transported, foot, foot - transported, foot >= max_step",
     "    return transported, foot, foot - transported, foot > max_step"),
    (CANDIDATE, "time model: one transition left out",
     "    transported = trigger_step + CHAIN_TRANSITIONS * TRANSITION + carrier_ff",
     "    transported = trigger_step + (CHAIN_TRANSITIONS - 1) * TRANSITION + carrier_ff"),
    (CANDIDATE, "condition 8: capacity not checked",
     "            elif not p1.infantry_room(car, view.passengers):", "            elif False:"),
    (CANDIDATE, "matching: smaller saving first", "    return (-(pair.saving or 0), not pair.unable_on_foot,",
     "    return ((pair.saving or 0), not pair.unable_on_foot,"),
    (CANDIDATE, "matching: infantry able to walk preferred", "    return (-(pair.saving or 0), not pair.unable_on_foot,",
     "    return (-(pair.saving or 0), pair.unable_on_foot,"),
    (CANDIDATE, "matching: no infantry conflict", "        if pair.infantry in taken_inf:", "        if False:"),
    (CANDIDATE, "matching: no carrier conflict", "        elif pair.carrier in taken_car:", "        elif False:"),
    (CANDIDATE, "admission: the pair's own two places not counted",
     "              + PLACES * (added[pair.destination] + 1)) > STACK_LIMIT:",
     "              + PLACES * added[pair.destination]) > STACK_LIMIT:"),
    (CANDIDATE, "admission: active reservations ignored",
     "        elif (view.ground_on(pair.destination) + reserved.get(pair.destination, 0)",
     "        elif (view.ground_on(pair.destination) + 0"),
    (CANDIDATE, "reservations: a carrier on the destination still counted",
     "        need[dest] += (0 if car is not None and car.cur_hex == dest else 1)", "        need[dest] += 1"),
    # -- the candidate: the episode machine, the bounds, recovery
    (CANDIDATE, "disembark issued at the stacking limit",
     "        return option if option is not None and view.ground_on(carrier.cur_hex) < STACK_LIMIT else None",
     "        return option if option is not None and view.ground_on(carrier.cur_hex) <= STACK_LIMIT else None"),
    (CANDIDATE, "embark failure read in the order's own step",
     "        elif not aboard and inf in view.own and view.settled(inf, car, \"get_on\") and now > ep[F_EMBARK]:",
     "        elif not aboard and inf in view.own and view.settled(inf, car, \"get_on\") and now >= ep[F_EMBARK]:"),
    (CANDIDATE, "embark bound off by one", "        elif now - ep[F_EMBARK] > BOUND:", "        elif now - ep[F_EMBARK] >= BOUND:"),
    (CANDIDATE, "carriage bound without the free-flow time", "        elif now > ep[F_RELEASE] + ep[F_FF] + BOUND:",
     "        elif now > ep[F_RELEASE] + BOUND:"),
    (CANDIDATE, "destination bound off by one", "            if now - ep[F_ARRIVE] > BOUND:",
     "            if now - ep[F_ARRIVE] >= BOUND:"),
    (CANDIDATE, "no hold while waiting at the destination",
     "                to_recovery(CAPACITY if view.ground_on(ep[F_DEST]) >= STACK_LIMIT else NOT_LISTED)\n"
     "            else:\n                return \"hold\"",
     "                to_recovery(CAPACITY if view.ground_on(ep[F_DEST]) >= STACK_LIMIT else NOT_LISTED)\n"
     "            else:\n                return None"),
    (CANDIDATE, "no re-issue of an interrupted disembark",
     "                    return (\"disembark\", option)  # bounded re-issue", "                    pass  # bounded re-issue"),
    (CANDIDATE, "disembark appended instead of replacing the carrier's action",
     "    if mine:\n        actions[mine[0]] = disembark", "    if False:\n        actions[mine[0]] = disembark"),
    (CANDIDATE, "recovery may start at the failure decision",
     "        if now <= ep.get(F_HOLD_STEP, now) or moving(carrier)", "        if moving(carrier)"),
    (CANDIDATE, "recovery on a full hex",
     "        if now <= ep.get(F_HOLD_STEP, now) or moving(carrier) or view.ground_on(carrier.cur_hex) >= STACK_LIMIT:",
     "        if now <= ep.get(F_HOLD_STEP, now) or moving(carrier):"),
    (CANDIDATE, "recovery attempts unbounded", "        if ep.get(F_ATTEMPTS, 0) < RECOVERY_ATTEMPTS:",
     "        if True:"),
    (CANDIDATE, "an absent infantry tolerated outside a transition",
     "        since = {EMBARK_REQUESTED: F_EMBARK, DISEMBARK_REQUESTED: F_DISEMBARK, RECOVERY_DISEMBARK: F_DISEMBARK}",
     "        since = {EMBARK_REQUESTED: F_EMBARK, DISEMBARK_REQUESTED: F_DISEMBARK, RECOVERY_DISEMBARK: F_DISEMBARK,\n"
     "                 CARRIER_RELEASED: F_RELEASE}"),
    (CANDIDATE, "memory with a unit in two episodes accepted", "    if len(set(units)) != len(units):\n        return None",
     "    if False:\n        return None"),
    # -- the rules module: the independent batch check, the projections, the roles, the readiness and screen rules
    (RULES, "batch check: an over-committed destination accepted",
     "        if _ground(own, dest) + reserved.get(dest, 0) + PLACES * n > STACK_LIMIT:",
     "        if _ground(own, dest) + reserved.get(dest, 0) + PLACES * (n - 1) > STACK_LIMIT:"),
    (RULES, "batch check: a kept carrier MOVE accepted",
     "        elif unit in carriers and a.get(\"type\") == MOVE:\n            continue",
     "        elif unit in carriers and a.get(\"type\") == MOVE and False:\n            continue"),
    (RULES, "batch check: an unselected admissible pair accepted",
     "                problems.append(\"an admissible pair with both units free was left unselected\")",
     "                pass"),
    (RULES, "batch check: different objectives accepted", "    if list(mine[0][\"move_path\"])[-1] != dest or dest not in cities:",
     "    if dest not in cities:"),
    (RULES, "projection: arrival without the embark", "    arrival = s + TRANSITION + carrier_ff",
     "    arrival = s + carrier_ff"),
    (RULES, "saturation at four others instead of three",
     "    out[\"saturated_at_arrival\"] = j is not None and others_on(history[j], dest, pair) >= STACK_LIMIT - 1",
     "    out[\"saturated_at_arrival\"] = j is not None and others_on(history[j], dest, pair) >= STACK_LIMIT"),
    (RULES, "saturation counts the pair's own units",
     "    return moment.ground.get(dest, 0) - sum(1 for u in pair if (moment.where.get(u) or (None,))[0] == dest)",
     "    return moment.ground.get(dest, 0)"),
    (RULES, "role C boundary off by one", "    if delivery >= max_step:\n        return \"C\"",
     "    if delivery > max_step:\n        return \"C\""),
    (RULES, "role B: any owner counts", "    if history[j].flags.get(dest) == faction:\n        return \"B\"",
     "    if history[j].flags.get(dest) != -1:\n        return \"B\""),
    (RULES, "role A: earlier ownership ignored",
     "    if all(m.flags.get(dest) != faction for m in history[: j + 1]):", "    if True:"),
    (RULES, "carrier hold window one step short",
     "    orders = [(m, m.orders[car]) for m in history[arrived:] if car in m.orders and m.cur_step <= t0 + 2 * TRANSITION]",
     "    orders = [(m, m.orders[car]) for m in history[arrived:] if car in m.orders and m.cur_step < t0 + 2 * TRANSITION]"),
    (RULES, "claimant: a held objective counts",
     "        out[\"claimant_elsewhere\"] = end != dest and end in moment.flags and moment.flags.get(end) != faction",
     "        out[\"claimant_elsewhere\"] = end != dest and end in moment.flags"),
    (RULES, "runs: non-consecutive selections merged", "            if not (previous[0] == k - 1 and tuple(pair) in previous[1]):",
     "            if not (tuple(pair) in previous[1]):"),
    (RULES, "readiness: a minimum met one below", " if value < floor]", " if value < floor - 1]"),
    (RULES, "readiness: inert episodes counted as acting",
     "    acting = sum(1 for e in episodes if e[\"population\"] in ACTING)", "    acting = len(episodes)"),
    (RULES, "readiness: a share at its maximum blocks", "            if value > Fraction(ceiling)]",
     "            if value >= Fraction(ceiling)]"),
    (RULES, "readiness: risk before opportunity",
     "    if short:\n        return {\"disposition\": NO_OPPORTUNITY", "    if short and False:\n        return {\"disposition\": NO_OPPORTUNITY"),
    (RULES, "screen: phase M with a single pair", "    m = [b for b in batches if b[\"population\"] == \"HI\" and b[\"batch_size\"] >= 2]",
     "    m = [b for b in batches if b[\"population\"] == \"HI\" and b[\"batch_size\"] >= 1]"),
    (RULES, "screen: H0 preferred to HH on ties",
     "    scenario = sorted(by_scenario, key=lambda s: (-by_scenario[s][0], -by_scenario[s][1], s))[0]",
     "    scenario = sorted(by_scenario, key=lambda s: (-by_scenario[s][0], by_scenario[s][1], s))[0]"),
    # -- the driver
    (DRIVER, "H0 validity: a difference at the trigger decision invalidates",
     "                   and (population != \"H0\" or first_difference is None or first_difference >= first_trigger))",
     "                   and (population != \"H0\" or first_difference is None or first_difference > first_trigger))"),
    (DRIVER, "H0 validity not required",
     "                   and (population != \"H0\" or first_difference is None or first_difference >= first_trigger))",
     "                   and True)"),
    (DRIVER, "known answer: decision not compared",
     "        agrees = (in_first and side.get(\"first_trigger_decision\") == row[\"trigger_decision\"]) if same else not in_first",
     "        agrees = in_first if same else True"),
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
    sources = (CANDIDATE, RULES, DRIVER) + tuple(Path(f"{t.replace('.', '/')}.py") for t in TESTS)
    payload = {"schema": "miaosuan-s23-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
