"""Mutation test of the Sprint 22 decision logic (``docs/SPRINT22_T2_TRANSPORT_PROBE.md``).

    python scripts/mutate_s22.py [--check]

Copies ``src``, ``tests``, ``scripts`` and the evaluation folders the tests read to a temporary directory, first runs
the Sprint 22 test modules unmutated (they must pass, or every later kill would be vacuous), then plants each
registered defect into the candidate (``experiments/t2_transport_p1.py``), the frozen rules module or the observer,
rebuilds the card in the copy (the card pins those files' digests, so without the rebuild every defect would be caught
by the pin alone), re-pins the candidate's source digest inside the copy for candidate defects (so that only the logic
tests, never the digest pin, can catch them), runs the tests in a fresh process and records whether they failed. A
defect after which the card cannot be built counts as caught by the card builder and is labelled so. Every planted
defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s22-t2-transport-probe/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t2_transport_p1.py")
RULES = Path("src/miaosuan_agent/evaluation/s22_probe.py")
CAPTURE = Path("src/miaosuan_agent/evaluation/s22_capture.py")
TESTS = ("tests.test_t2_transport_p1", "tests.test_s22_probe")
EVALUATION = ("s22-t2-transport-probe-1", "s22-t2-transport-probe", "baseline-v2-candidate-shoot-target-reservation")
CARD = Path("evaluation/s22-t2-transport-probe-1/manifest.json")
OUT = REPO_ROOT / "evaluation" / "s22-t2-transport-probe" / "mutation.json"
MUTATIONS = [
    # -- the candidate: action schemas, the trigger, every transition, the bounds, the hold, the stacking boundary
    (CANDIDATE, "embark schema: unit and target swapped",
     '        embark = {"actor": seat, "obj_id": inf_id, "type": EMBARK, "target_obj_id": option["target_obj_id"]}',
     '        embark = {"actor": seat, "obj_id": option["target_obj_id"], "type": EMBARK, "target_obj_id": inf_id}'),
    (CANDIDATE, "disembark schema: unit and target swapped",
     '                disembark = {"actor": seat, "obj_id": car_id, "type": DISEMBARK, "target_obj_id": option["target_obj_id"]}',
     '                disembark = {"actor": seat, "obj_id": inf_id, "type": DISEMBARK, "target_obj_id": car_id}'),
    (CANDIDATE, "embark appended instead of replacing the move in place", "        actions[index] = embark",
     "        del actions[index]\n        actions.append(embark)"),
    (CANDIDATE, "no carrier hold at the trigger",
     "        withhold_carrier_move(actions, car_id, EMBARK_REQUESTED, changes)\n        return tuple(actions)",
     "        return tuple(actions)"),
    (CANDIDATE, "no carrier hold during the embark transition",
     "        else:\n            withhold_carrier_move(actions, car_id, EMBARK_REQUESTED, changes)",
     "        else:\n            pass"),
    (CANDIDATE, "no carrier hold at the destination",
     "        else:\n            withhold_carrier_move(actions, car_id, AT_DESTINATION, changes)",
     "        else:\n            pass"),
    (CANDIDATE, "no carrier hold during the disembark transition",
     "        else:\n            withhold_carrier_move(actions, car_id, DISEMBARK_REQUESTED, changes)",
     "        else:\n            pass"),
    (CANDIDATE, "the hold withholds every carrier action", '        if actions[i].get("type") == MOVE:',
     "        if True:"),
    (CANDIDATE, "embark bound off by one", "        elif now - record[F_EMBARK] > BOUND:",
     "        elif now - record[F_EMBARK] >= BOUND:"),
    (CANDIDATE, "settle bound off by one", "        elif now - record[F_ARRIVE] > BOUND:",
     "        elif now - record[F_ARRIVE] >= BOUND:"),
    (CANDIDATE, "disembark bound off by one", "        elif now - record[F_DISEMBARK] > BOUND:",
     "        elif now - record[F_DISEMBARK] >= BOUND:"),
    (CANDIDATE, "aboard without the embark transition over",
     '        elif aboard and view.settled(inf_id, car_id, "get_on"):', "        elif aboard:"),
    (CANDIDATE, "done without the disembark transition over",
     '        elif view.on_ground(inf_id, car_id) and view.settled(inf_id, car_id, "get_off"):',
     "        elif view.on_ground(inf_id, car_id):"),
    (CANDIDATE, "stacking boundary off by one",
     "            if view.ground_on(dest) >= STACK_LIMIT:\n                go(FAILED, CAPACITY)",
     "            if view.ground_on(dest) > STACK_LIMIT:\n                go(FAILED, CAPACITY)"),
    (CANDIDATE, "stacking never checked",
     "            if view.ground_on(dest) >= STACK_LIMIT:\n                go(FAILED, CAPACITY)",
     "            if False:\n                go(FAILED, CAPACITY)"),
    (CANDIDATE, "same hex not required", "            if car.cur_hex != inf.cur_hex or not quiet(car)",
     "            if not quiet(car)"),
    (CANDIDATE, "speed ignored by stationarity", ' and zero(unit, "speed")', ""),
    (CANDIDATE, "suppression ignored", ' and zero(unit, "keep")', ""),
    (CANDIDATE, "capacity ignored", " or not infantry_room(car, view.passengers):", ":"),
    (CANDIDATE, "a carrier already carrying infantry accepted",
     '    if any(p in passengers and field(passengers[p], "type") == INFANTRY_TYPE for p in aboard):\n        return False\n',
     ""),
    (CANDIDATE, "the carrier's class not checked",
     "            if car is None or not is_class(car, VEHICLE_TYPE, IFV_SUB) or car_id not in view.controlled:",
     "            if car is None or car_id not in view.controlled:"),
    (CANDIDATE, "the carrier's control not checked",
     "            if car is None or not is_class(car, VEHICLE_TYPE, IFV_SUB) or car_id not in view.controlled:",
     "            if car is None or not is_class(car, VEHICLE_TYPE, IFV_SUB):"),
    (CANDIDATE, "baseline-v2's infantry move not required",
     '        if len(mine) != 1 or actions[mine[0]].get("type") != MOVE:\n            continue',
     "        if not mine:\n            continue"),
    (CANDIDATE, "baseline-v2's carrier move not required",
     '            if len(theirs) != 1 or actions[theirs[0]].get("type") != MOVE:', "            if not theirs:"),
    (CANDIDATE, "the option key set not checked",
     '                   if set(o) == {"target_obj_id"} and is_int(o.get("target_obj_id"))]',
     '                   if is_int(o.get("target_obj_id"))]'),
    (CANDIDATE, "the disembark option key set not checked",
     '        if set(option) == {"target_obj_id"} and option.get("target_obj_id") == target:',
     '        if option.get("target_obj_id") == target:'),
    (CANDIDATE, "a passenger leaving early does not fail",
     "        elif not aboard:\n            go(FAILED, PASSENGER_LEFT)", "        elif False:\n            go(FAILED, PASSENGER_LEFT)"),
    (CANDIDATE, "the destination read from the first hex of the move",
     "                record[F_DEST] = path[-1]", "                record[F_DEST] = path[0]"),
    (CANDIDATE, "the carrier leaving the destination does not fail",
     "        if car.cur_hex != dest:\n            go(FAILED, CARRIER_LEFT)", "        if False:\n            go(FAILED, CARRIER_LEFT)"),
    (CANDIDATE, "malformed memory accepted",
     "    if record.get(F_STATE) not in range(1, len(STATES)) or not record.get(F_INF) or not record.get(F_CAR):\n"
     "        return None\n", ""),
    (CANDIDATE, "a terminal state triggers a second pair", "    if not record:\n        found = trigger(view, actions)",
     "    if not record or record.get(F_STATE) in TERMINAL:\n        found = trigger(view, actions)"),
    (CANDIDATE, "the carrier's absence does not fail the embark transition",
     "    if state == EMBARK_REQUESTED:\n        if car is None:\n            go(FAILED, UNIT_ABSENT)",
     "    if state == EMBARK_REQUESTED:\n        if False:\n            go(FAILED, UNIT_ABSENT)"),
    # -- the rules: selection, ledger, structural checks, differences, prefix, endpoints, disposition
    (RULES, "tier 2 preferred to tier 1", "    pool = tier1 or [r for r in eligible if r[\"tier\"] == 2]",
     "    pool = [r for r in eligible if r[\"tier\"] == 2] or tier1"),
    (RULES, "the saturation preference ignored",
     '    return (row["tier"], bool(row["destination_saturated_in_history"]),', '    return (row["tier"], False,'),
    (RULES, "feasibility off by one", "carrier_free_flow < max_step", "carrier_free_flow <= max_step"),
    (RULES, "ledger ceiling off by one", "    if len(opened) > SESSION_CEILING:", "    if len(opened) > SESSION_CEILING + 1:"),
    (RULES, "ledger ignores the expected session",
     "    if any(int(s) not in EXPECTED_SESSIONS for s in opened):", "    if False:"),
    (RULES, "ledger ignores the candidate digest",
     '            if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:\n                problems["S2"]',
     '            if False:\n                problems["S2"]'),
    (RULES, "ledger ignores an integrity failure", '            elif not (record.get("integrity") or {}).get("ok"):',
     "            elif False:"),
    (RULES, "game stops ignore unregistered differences", '    if timeline.get("unregistered_differences"):',
     "    if False:"),
    (RULES, "differences: other units not compared", "    if others_base != others_live:", "    if False:"),
    (RULES, "differences: order not checked", "    if order != sorted(order) or len(set(order)) != len(order):",
     "    if False:"),
    (RULES, "differences: a hold allowed in any state",
     '        hold = state_after in ("EMBARK_REQUESTED", "AT_DESTINATION", "DISEMBARK_REQUESTED")', "        hold = True"),
    (RULES, "differences: disembark allowed in any state",
     '        disembark_ok = (state_before in ("CARRIER_RELEASED", "AT_DESTINATION") and state_after == "DISEMBARK_REQUESTED"',
     '        disembark_ok = (True'),
    (RULES, "prefix: early differences ignored", "    if early:", "    if False:"),
    (RULES, "prefix: trigger actions not compared", '    if trigger_actions != reference["trigger_actions"]:',
     "    if False:"),
    (RULES, "prefix: pair not compared", '    if pair is None or list(pair) != list(reference["pair"]):',
     "    if False:"),
    (RULES, "embark endpoint bound off by one", 'or facts["aboard_after"] > t2.BOUND:', 'or facts["aboard_after"] >= t2.BOUND:'),
    (RULES, "embark refusal ignored", '    if facts.get("response") is False:\n        reasons.append("embark refused")',
     '    if False:\n        reasons.append("embark refused")'),
    (RULES, "carry: passenger breaks ignored", '    if facts.get("passenger_breaks"):', "    if False:"),
    (RULES, "carry: position mismatches ignored", '    if facts.get("position_mismatches"):', "    if False:"),
    (RULES, "carry: actions for the passenger ignored", '    if facts.get("actions_for_passenger"):', "    if False:"),
    (RULES, "carry: arrival not required", '    if facts.get("arrival_decision") is None:', "    if False:"),
    (RULES, "stacking endpoint boundary off by one", "    blocked = count is not None and count >= t2.STACK_LIMIT",
     "    blocked = count is not None and count > t2.STACK_LIMIT"),
    (RULES, "disembark emitted more than once accepted", '    if facts.get("emitted") != 1:',
     '    if facts.get("emitted", 0) < 1:'),
    (RULES, "disembark destination not required",
     '    if facts.get("ground_after") is not None and not facts.get("on_destination"):', "    if False:"),
    (RULES, "disposition: problems ignored", "    if problems or embark is None:", "    if embark is None:"),
    (RULES, "disposition: blocked after refuted",
     '    if embark["ok"] and carry is not None and carry["ok"] and stacking is not None and stacking["blocked"]:',
     '    if False:'),
    (RULES, "facts: aboard without the transition over",
     '    aboard = next((j for j in range(trigger + 1, n) if frames[j].is_aboard(inf, car)\n'
     '                   and frames[j].cleared(inf, car, "get_on")), None)',
     '    aboard = next((j for j in range(trigger + 1, n) if frames[j].is_aboard(inf, car)), None)'),
    (RULES, "facts: aboard ignores the car field", ' and p.get("car") == car and p.get("on_board") == 1', ""),
    (RULES, "facts: the carrier's control not checked",
     "    embark[\"carrier_present_and_controlled\"] = all(car in frames[j].own and car in frames[j].controlled",
     "    embark[\"carrier_present_and_controlled\"] = all(car in frames[j].own"),
    # -- the observer
    (CAPTURE, "the live actions are never compared",
     '    return {"actions": rd.plain(decision["submitted"]) == rebuilt["actions"],', '    return {"actions": True,'),
    (CAPTURE, "the memory chain is never compared", '            "addon_memory": addon_memory == expected_memory[1]}',
     '            "addon_memory": True}'),
    (CAPTURE, "prefix digests read every seat's actions",
     '        live.append(actions_digest([a["action"] for a in step.get("submitted") or () if a["seat"] == seat]))',
     '        live.append(actions_digest([a["action"] for a in step.get("submitted") or ()]))'),
]


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    return env


def digest_of_candidate(root: Path) -> str:
    script = ("import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'scripts'); import build_s22_card as b; "
              "from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files; "
              "print(digest_of_files(policy_source_files(sources=b.CANDIDATE_SOURCES)))")
    done = subprocess.run([sys.executable, "-c", script], cwd=root, env=env_for(root), capture_output=True, text=True,
                          timeout=120, check=True)
    return done.stdout.strip()


def prepare(root: Path, replacements) -> bool:
    for folder in ("src", "tests", "scripts"):
        shutil.copytree(REPO_ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    for name in EVALUATION:
        shutil.copytree(REPO_ROOT / "evaluation" / name, root / "evaluation" / name)
    for source, text in replacements.items():
        (root / source).write_text(text, encoding="utf-8", newline="\n")
    if CANDIDATE in replacements:
        old = digest_of_candidate(REPO_ROOT)
        new = digest_of_candidate(root)
        for rel, expected in ((RULES, 1), (Path("tests/test_t2_transport_p1.py"), 1)):
            text = (root / rel).read_text(encoding="utf-8")
            if text.count(old) != expected:
                raise SystemExit(f"the candidate digest occurs {text.count(old)} times in {rel}")
            (root / rel).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    (root / CARD).unlink()
    built = subprocess.run([sys.executable, "scripts/build_s22_card.py"], cwd=root, env=env_for(root),
                           capture_output=True, text=True, timeout=300)
    if built.returncode != 0:
        shutil.copy2(REPO_ROOT / CARD, root / CARD)
    return built.returncode == 0


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        built = prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=900)
    return done.returncode == 0, built, done.stdout[-1500:] + done.stderr[-1500:]


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    passed, built, _ = tests_pass({source: text.replace(old, new)})
    return {"mutation": name, "module": source.as_posix(), "killed": not passed, "card_rebuilt": built}


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
    passed, built, log = tests_pass({})
    if not (passed and built):
        raise SystemExit("the unmutated tests fail (or the card cannot be built) in the temporary copy; kills would "
                         "be vacuous\n" + log)
    results = [run(m) for m in MUTATIONS]
    sources = (CANDIDATE, RULES, CAPTURE, Path("tests/test_t2_transport_p1.py"), Path("tests/test_s22_probe.py"))
    payload = {"schema": "miaosuan-s22-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results),
               "killed_with_the_card_rebuilt": sum(r["killed"] and r["card_rebuilt"] for r in results)}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"killed {payload['killed']} of {payload['total']} ({payload['killed_with_the_card_rebuilt']} with the card "
          "rebuilt)")
    for r in results:
        if not r["killed"]:
            print("SURVIVED", r["mutation"])
        elif not r["card_rebuilt"]:
            print("caught by the card builder only:", r["mutation"])
    return 0 if payload["killed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
