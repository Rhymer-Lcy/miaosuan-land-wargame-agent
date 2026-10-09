"""Mutation test of the Sprint 27 decision logic (``docs/SPRINT27_T6S_PROBE.md``).

    python scripts/mutate_s27.py [--check]

Copies ``src``, ``tests``, ``scripts`` and the evaluation folders the tests read to a temporary directory, first runs
the Sprint 27 test modules unmutated (they must pass, or every later kill would be vacuous), then plants each
registered defect into the candidate (``experiments/t6s_column_stagger_p1.py``), the frozen rules module or the
observer, rebuilds the card in the copy (the card pins those files' digests, so without the rebuild every defect would
be caught by the pin alone), re-pins the candidate's source digest inside the copy for candidate defects (so that only
the logic tests, never the digest pin, can catch them), runs the tests in a fresh process and records whether they
failed. Defects planted inside the candidate's verbatim copy of Sprint 26's frozen rule are labelled: the copy check
must catch them whatever the logic tests do. Every planted defect's original text must occur exactly once. Writes (or
with ``--check`` compares) ``evaluation/s27-t6s-probe/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t6s_column_stagger_p1.py")
RULES = Path("src/miaosuan_agent/evaluation/s27_probe.py")
CAPTURE = Path("src/miaosuan_agent/evaluation/s27_capture.py")
TESTS = ("tests.test_t6s_column_stagger_p1", "tests.test_s27_probe")
EVALUATION = ("s27-t6s-probe-1", "s27-t6s-probe", "s26-t6s-shadow", "baseline-v2-candidate-shoot-target-reservation")
CARD = Path("evaluation/s27-t6s-probe-1/manifest.json")
OUT = REPO_ROOT / "evaluation" / "s27-t6s-probe" / "mutation.json"
COPY = "copied rule"
MUTATIONS = [
    # -- the candidate's verbatim copy of Sprint 26's rule (the copy check must catch these)
    (CANDIDATE, f"{COPY}: wait bound slack", "STALL_SLACK = 10", "STALL_SLACK = 11"),
    (CANDIDATE, f"{COPY}: minimum group", "MIN_GROUP = 2", "MIN_GROUP = 3"),
    (CANDIDATE, f"{COPY}: release on the start hex",
     "            if ref_unit is None or (ref_hex is not None and ref_hex != ep.origin):",
     "            if ref_unit is None or (ref_hex is not None and ref_hex == ep.origin):"),
    (CANDIDATE, f"{COPY}: leader by unit id only", "    return (member.arrival, member.cost, len(member.route), member.unit)",
     "    return (member.unit,)"),
    # -- the candidate's reading of the seat observation
    (CANDIDATE, "seat inputs: own and enemy colours swapped",
     '        (own if u.get("color") == faction else enemies)[u["obj_id"]] = unit_view(u)',
     '        (own if u.get("color") != faction else enemies)[u["obj_id"]] = unit_view(u)'),
    (CANDIDATE, "seat inputs: unreadable unit ids kept",
     '        if not isinstance(u, Mapping) or as_int(u.get("obj_id")) is None:\n            continue\n        (own',
     '        if not isinstance(u, Mapping):\n            continue\n        (own'),
    (CANDIDATE, "unit view: route not a tuple", '    out["move_path"] = tuple(u.get("move_path") or ())',
     '    out["move_path"] = u.get("move_path") or ()'),
    (CANDIDATE, "listings: string keys not read", "        oid = as_int(obj)", "        oid = obj if isinstance(obj, int) else None"),
    # -- the candidate's memory
    (CANDIDATE, "encode: spent units dropped", "        values += [_int(unit_id), _int(origin)]\n", "        pass\n"),
    (CANDIDATE, "encode: pending followers dropped",
     "        values += [len(ep.pending)] + [_int(u) for u in ep.pending]", "        values += [0]"),
    (CANDIDATE, "encode: empty memory not empty", "    if memory == StaggerMemory():\n        return ()\n", ""),
    (CANDIDATE, "decode: positions not checked",
     "        if len(pair) != 2 or _int(pair[0]) != position:", "        if len(pair) != 2:"),
    (CANDIDATE, "decode: spent pairs read swapped", "        unit_id, origin = take(2)",
     "        origin, unit_id = take(2)"),
    (CANDIDATE, "decode: one-member chain accepted", "        if n_chain < 2 or not set(pending) <= set(chain):",
     "        if not set(pending) <= set(chain):"),
    (CANDIDATE, "decode: pending outside the chain accepted",
     "        if n_chain < 2 or not set(pending) <= set(chain):", "        if n_chain < 2:"),
    (CANDIDATE, "decode: round trip not required",
     "    if encode(memory) != tuple((i, v) for i, v in enumerate(values)):", "    if False:"),
    # -- the add-on
    (CANDIDATE, "add-on: memory not carried",
     "    result = decide(cur_step, stage, own, enemies.values(), valid, base_actions, decode(memory), travel)",
     "    result = decide(cur_step, stage, own, enemies.values(), valid, base_actions, StaggerMemory(), travel)"),
    (CANDIDATE, "add-on: next memory is the input memory",
     "    return result, encode(result.memory)", "    return result, encode(decode(memory))"),
    (CANDIDATE, "add-on: change records lose the index",
     "        if e.index is not None:\n            record[\"index\"] = e.index\n", ""),
    (CANDIDATE, "add-on: group outcomes not counted", '        counts[f"group {outcome}"] += 1', "        pass"),
    (CANDIDATE, "add-on: no failure without cost data",
     '            raise RuntimeError("no setup cost data: the free-flow relation is unreadable")',
     "            return AddonResult(tuple(base.actions))"),
    # -- the rules: ledger and stages
    (RULES, "ledger: schedule position not checked",
     "            elif position > len(order) or order[position - 1] != game:", "            elif False:"),
    (RULES, "ledger: card digest not checked",
     '            if harness.get("card") != CARD_ID or harness.get("manifest_sha256") != digest:',
     '            if harness.get("card") != CARD_ID:'),
    (RULES, "ledger: candidate digest not checked",
     '            if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:\n                problems["S2"]',
     '            if False:\n                problems["S2"]'),
    (RULES, "ledger: a game opened twice not found", "            if game in seen:\n                problems",
     "            if False:\n                problems"),
    (RULES, "ledger: unclosed sessions not found", "    if unclosed:\n        problems", "    if False:\n        problems"),
    (RULES, "ledger: recovery not flagged", '            if record.get("event") == "session-recovered":\n                problems',
     '            if False:\n                problems'),
    (RULES, "ledger: integrity not checked", '            elif not (record.get("integrity") or {}).get("ok"):',
     "            elif False:"),
    (RULES, "ledger: state chain not checked",
     '            if previous is not None and record.get("state") != previous.get("state"):', "            if False:"),
    (RULES, "ledger: session order not checked",
     "    if sorted(int(s) for s in opened) != list(EXPECTED_SESSIONS[:len(opened)]):", "    if False:"),
    (RULES, "stages: stage A tolerates a session", '    if stage == "A" and audit["sessions"] != 0:',
     '    if stage == "A" and audit["sessions"] > 1:'),
    (RULES, "stages: stage B prerequisites skipped",
     '    if stage == "B" and (audit["sessions"] != 1 or list(audit["games"]) != [order[0]]):',
     '    if stage == "C" and (audit["sessions"] != 1 or list(audit["games"]) != [order[0]]):'),
    # -- the rules: per-game stops and differences
    (RULES, "game stops: opponent digest not checked",
     '    if (harness.get("policy_sources") or {}).get(V2_ID) != V2_DIGEST:', "    if False:"),
    (RULES, "game stops: seats not checked", "    if by_faction != {faction: CANDIDATE_ID, 1 - faction: V2_ID}:",
     "    if False:"),
    (RULES, "game stops: one seat reconstructed suffices",
     '    if timeline.get("reconstructed_decisions") != 2 * len(steps):',
     '    if timeline.get("reconstructed_decisions") < len(steps):'),
    (RULES, "game stops: max_step not checked", '    if max_step != RULES["max_step"]:', "    if False:"),
    (RULES, "game stops: unregistered differences ignored", '    if timeline.get("unregistered_differences"):',
     "    if False:"),
    (RULES, "differences: a withheld non-MOVE accepted", "    if any(dict(baseline[i]).get(\"type\") != MOVE for i in drop):",
     "    if False:"),
    (RULES, "differences: order not checked",
     "    if out != [a for i, a in enumerate(base) if i not in drop]:",
     "    if sorted(out) != sorted(a for i, a in enumerate(base) if i not in drop):"),
    # -- the rules: P1, P2, fidelity
    (RULES, "P1: equality triggers", "    triggered = Fraction(candidate_e4) > half", "    triggered = Fraction(candidate_e4) >= half"),
    (RULES, "P1: against the mean, not half of it", "    triggered = Fraction(candidate_e4) > half",
     "    triggered = Fraction(candidate_e4) > mean"),
    (RULES, "P2: earliest reference instead of the latest", "            ref = max(finite)", "            ref = min(finite)"),
    (RULES, "P2: never owned passes", "            triggered = c is None or c > ref",
     "            triggered = c is not None and c > ref"),
    (RULES, "P2: equality triggers", "            triggered = c is None or c > ref", "            triggered = c is None or c >= ref"),
    (RULES, "P2: an objective without reference triggers when never owned",
     '            row.update(reference_step=None, status="no historical timing reference", triggered=False)',
     '            row.update(reference_step=None, status="no historical timing reference", triggered=c is None)'),
    (RULES, "fidelity: frozen-rule equality not required",
     '    if fidelity.get("frozen_rule_equal_decisions") != fidelity.get("decisions") or not fidelity.get("decisions"):',
     "    if False:"),
    (RULES, "fidelity: rule events not required", '    if fidelity.get("frozen_rule_events_equal") is not True:',
     "    if False:"),
    (RULES, "fidelity: prefix not required",
     '    if fidelity.get("candidate_equals_baseline_v2_before_the_first_withholding") is not True:', "    if False:"),
    # -- the rules: mechanism, gate, disposition
    (RULES, "mechanism: any release reason counts",
     '    out["executed"] = out["completed"] and any(f.get("release_reason") == "reference_left" and f["departed_after_release"]',
     '    out["executed"] = out["completed"] and any(f.get("release_reason") is not None and f["departed_after_release"]'),
    (RULES, "mechanism: completion not required",
     '    out["executed"] = out["completed"] and any(', '    out["executed"] = True and any('),
    (RULES, "mechanism: every follower required",
     '    out["executed"] = out["completed"] and any(', '    out["executed"] = out["completed"] and all('),
    (RULES, "mechanism: departures ignore absence",
     '        if unit not in frames[j].own:\n            return j, "absent"', "        if unit not in frames[j].own:\n            continue"),
    (RULES, "mechanism: separation from the follower itself",
     '        lp = _hex(frames[d_k], leader) if d_kind == "moved" else None',
     '        lp = _hex(frames[d_k], u) if d_kind == "moved" else None'),
    (RULES, "mechanism: co-location counts the start hex",
     "        shared = {h for h, c in here.items() if c >= 2 and h != origin and h is not None}",
     "        shared = {h for h, c in here.items() if c >= 2 and h is not None}"),
    (RULES, "mechanism: an error echo counts as accepted", '    return not echoes[0].get("error")', "    return True"),
    (RULES, "gate: mechanism not required", "    if not observed:\n        reasons", "    if False:\n        reasons"),
    (RULES, "gate: P2 not required", '    if p2_result.get("triggered"):', "    if False:"),
    (RULES, "disposition: not observed before invalid", "    if problems:\n        return {**base, \"disposition\": INVALID",
     "    if problems and False:\n        return {**base, \"disposition\": INVALID"),
    (RULES, "disposition: an authorized stage B may be skipped",
     "    if stage_b_authorized and not stage_b_opened:", "    if False:"),
    (RULES, "disposition: one session can be supported",
     "    if count != SESSION_CEILING:\n        return", "    if False:\n        return"),
    # -- the observer
    (CAPTURE, "observer: candidate memory chain not compared", '            "addon_memory": addon_memory == expected_memory[1]}',
     '            "addon_memory": True}'),
    (CAPTURE, "observer: opponent policy not compared", '            "policy": decision["policy"] == V2_ID,',
     '            "policy": True,'),
    (CAPTURE, "observer: opponent memory not compared", '            "memory": decision["memory"] == expected_memory}',
     '            "memory": True}'),
    (CAPTURE, "observer: rule withholding forgotten", '            "actions": rd.plain(result.actions), "withheld": list(result.withheld),',
     '            "actions": rd.plain(result.actions), "withheld": [],'),
]


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    return env


def digest_of_candidate(root: Path) -> str:
    done = subprocess.run([sys.executable, "-c", (
        "import importlib.util; spec = importlib.util.spec_from_file_location('b', 'scripts/build_s27_card.py'); "
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        "print(m.policy_source(m.CANDIDATE_SOURCES)['sha256'])")], cwd=root, env=env_for(root), capture_output=True,
        text=True, check=True)
    return done.stdout.strip()


def prepare(root: Path, replacements) -> bool:
    for name in ("src", "tests", "scripts"):
        shutil.copytree(REPO_ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "evaluation").mkdir()
    for name in EVALUATION:
        shutil.copytree(REPO_ROOT / "evaluation" / name, root / "evaluation" / name)
    for source, text in replacements.items():
        (root / source).write_text(text, encoding="utf-8", newline="\n")
    if CANDIDATE in replacements:
        old = digest_of_candidate(REPO_ROOT)
        new = digest_of_candidate(root)
        text = (root / RULES).read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"the candidate digest occurs {text.count(old)} times in {RULES}")
        (root / RULES).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    (root / CARD).unlink()
    built = subprocess.run([sys.executable, "scripts/build_s27_card.py"], cwd=root, env=env_for(root),
                           capture_output=True, text=True, timeout=300)
    if built.returncode != 0:
        shutil.copy2(REPO_ROOT / CARD, root / CARD)
    return built.returncode == 0


def tests_pass(replacements) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        built = prepare(root, replacements)
        done = subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=root, env=env_for(root),
                              capture_output=True, text=True, timeout=1800)
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
    sources = (CANDIDATE, RULES, CAPTURE, Path("tests/test_t6s_column_stagger_p1.py"), Path("tests/test_s27_probe.py"),
               Path("tests/fixtures/s27_engine.py"))
    payload = {"schema": "miaosuan-s27-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
               "tests": list(TESTS), "unmutated_tests_pass": True, "mutations": results,
               "killed": sum(r["killed"] for r in results), "total": len(results),
               "killed_with_the_card_rebuilt": sum(r["killed"] and r["card_rebuilt"] for r in results),
               "copied_rule_mutations": sum(1 for r in results if r["mutation"].startswith(COPY))}
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
