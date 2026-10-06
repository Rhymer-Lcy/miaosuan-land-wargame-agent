"""Mutation test of the Sprint 17 decision logic (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``).

    python scripts/mutate_s17.py [--check]

Copies ``src``, ``tests``, ``scripts`` and the evaluation folders the tests read to a temporary directory, first runs
the Sprint 17 test modules unmutated (they must pass, or every later kill would be vacuous), then plants each
registered defect into the executable candidate (``experiments/t9_post_stage_v6.py``; the frozen modules it imports
are never mutated), the frozen rules module, the observer or the analysis driver, rebuilds the card in the copy (the
card pins those files' digests, so without the rebuild every defect would be caught by the pin alone and the run would
say nothing about the logic tests), runs the tests in a fresh process and records whether they failed.
A defect after which the card cannot be built at all counts as caught by the card builder and is labelled so. Every
planted defect's original text must occur exactly once. Writes (or with ``--check`` compares)
``evaluation/s17-first-divergence-probe/mutation.json``.
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
CANDIDATE = Path("src/miaosuan_agent/experiments/t9_post_stage_v6.py")
RULES = Path("src/miaosuan_agent/evaluation/s17_probe.py")
CAPTURE = Path("src/miaosuan_agent/evaluation/s17_capture.py")
ANALYSIS = Path("scripts/s17_analysis.py")
TESTS = ("tests.test_t9_post_stage_v6", "tests.test_s17_probe")
EVALUATION = ("s17-post-stage-v6-probe-1", "s16-v3-mechanism-capture-1",
              "baseline-v2-candidate-shoot-target-reservation")
CARD = Path("evaluation/s17-post-stage-v6-probe-1/manifest.json")
OUT = REPO_ROOT / "evaluation" / "s17-first-divergence-probe" / "mutation.json"
MUTATIONS = [
    # -- the executable candidate: the corrected memory, every unchanged transition, the rule, recourse, fail closed
    (CANDIDATE, "corrected reset reverted to v5 (any objective ends the record)",
     "        elif not path and unit.cur_hex in cities and cities[unit.cur_hex].flag != faction:",
     "        elif not path and unit.cur_hex in cities:"),
    (CANDIDATE, "standing on an unheld objective no longer ends the record",
     "        elif not path and unit.cur_hex in cities and cities[unit.cur_hex].flag != faction:", "        elif False:"),
    (CANDIDATE, "a move to an objective no longer ends the record", "        elif path and path[-1] in cities:",
     "        elif False:"),
    (CANDIDATE, "an absent unit keeps its record", "        if unit is None:\n            reason = ABSENT",
     "        if False:\n            reason = ABSENT"),
    (CANDIDATE, "the source's capture no longer ends the episode",
     "        if record[td.SOURCE] in cities and cities[record[td.SOURCE]].flag == faction:", "        if False:"),
    (CANDIDATE, "the source's capture wipes the staging fact",
     "            for index in (td.SOURCE, td.COUNT, td.ALTERNATIVE, td.SATURATED, td.REDIRECTED, td.FIRST):",
     "            for index in range(len(td.FIELD_NAMES)):"),
    (CANDIDATE, "staging completion detected away from the staging endpoint",
     "        if record[td.STAGED] and not path and unit.cur_hex == record[td.STAGED]:",
     "        if record[td.STAGED] and not path:"),
    (CANDIDATE, "every overflow claimant eligible", "records, ended, errors, False)", "records, ended, errors, True)"),
    (CANDIDATE, "the post-stage-same trigger instead of post-stage-any", 'td.RULES["delayed-post-stage-any"]',
     'td.RULES["delayed-post-stage-same"]'),
    (CANDIDATE, "the repeat-2 trigger instead of post-stage-any", 'td.RULES["delayed-post-stage-any"]',
     'td.RULES["delayed-repeat-2"]'),
    (CANDIDATE, "memory dropped outside the play stage", "        return td.Allocation(actions, td.encode(records))",
     "        return td.Allocation(actions, ())"),
    (CANDIDATE, "a failed memory update keeps the records",
     '        ended = {unit_id: "memory update failed" for unit_id in records}\n        records = {}',
     '        ended = {unit_id: "memory update failed" for unit_id in records}'),
    (CANDIDATE, "the add-on carries the incoming memory forward",
     "tuple(sorted(result.skipped.items())), result.memory)", "tuple(sorted(result.skipped.items())), memory)"),
    (CANDIDATE, "the trace omits ended records", "    for unit_id, reason in sorted(result.ended.items()):",
     "    for unit_id, reason in ():"),
    # -- ledger, card and structural checks
    (RULES, "ledger ceiling off by one", "    if len(opened) > SESSION_CEILING:",
     "    if len(opened) > SESSION_CEILING + 1:"),
    (RULES, "ledger ignores the candidate digest",
     '            if harness.get("policy_source_sha256") != CANDIDATE_DIGEST:', "            if False:"),
    (RULES, "ledger ignores the schedule position",
     "            elif position > len(order) or order[position - 1] != game:", "            elif False:"),
    (RULES, "ledger ignores an integrity failure", '            elif not (record.get("integrity") or {}).get("ok"):',
     "            elif False:"),
    (RULES, "the prefix check is not a structural stop",
     'STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7", "SP")',
     'STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7")'),
    (RULES, "wrong seats accepted", "    if by_faction != {faction: CANDIDATE_ID, 1 - faction: INERT_ID}:",
     "    if False:"),
    (RULES, "a candidate add-on error is not structural", '    if explore.get("addon_errors"):', "    if False:"),
    (RULES, "a wrong max_step accepted", '    if max_step != RULES["max_step"]:', "    if False:"),
    (RULES, "a capture digest mismatch accepted", "        if recorded is None or recorded != actual:",
     "        if recorded is None:"),
    (RULES, "an incomplete reconstruction accepted", '    if timeline.get("reconstructed_decisions") != len(steps):',
     "    if False:"),
    # -- prefix check
    (RULES, "prefix actions checked from decision 1",
     '    early = [j for j in range(k) if live_actions[j] != reference["v3_actions"][j]]',
     '    early = [j for j in range(1, k) if live_actions[j] != reference["v3_actions"][j]]'),
    (RULES, "no divergence accepted", '    if live_actions[k] == reference["v3_actions"][k]:', "    if False:"),
    (RULES, "any divergence accepted", '    elif live_actions[k] != reference["expected_actions"]:', "    elif False:"),
    (RULES, "the memory after the divergence is not checked",
     '    memory = [j for j in range(k + 2) if live_memory[j] != reference["memory_in"][j]]',
     '    memory = [j for j in range(k + 1) if live_memory[j] != reference["memory_in"][j]]'),
    (RULES, "changed units not checked",
     '    if sorted(map(str, live_changed)) != sorted(map(str, reference["changed"])):', "    if False:"),
    (RULES, "redirect routes not checked",
     '    if {str(u): r for u, r in dict(live_redirects).items()} != {str(u): r for u, r in reference["redirects"].items()}:',
     "    if False:"),
    # -- C2 fire endpoints
    (RULES, "a listing is not required", '    out["preserved"] = out["listed"] and out["emitted"] and out["accepted"]',
     '    out["preserved"] = out["emitted"] and out["accepted"]'),
    (RULES, "another unit's shot counts",
     '    mine = [(a, r) for a, r in orders if a.get("type") == SHOOT and a.get("obj_id") == unit]',
     '    mine = [(a, r) for a, r in orders if a.get("type") == SHOOT]'),
    (RULES, "a refused shot counts as accepted", '"accepted": any(r == "accepted" for _, r in mine),',
     '"accepted": bool(mine),'),
    (RULES, "only the first protected decision is checked", "    for k in decisions:\n        e = endpoints[k]",
     "    for k in decisions[:1]:\n        e = endpoints[k]"),
    (RULES, "another decision may substitute for a protected one",
     "    if sorted(int(k) for k in endpoints) != sorted(decisions):", "    if False:"),
    # -- 212 first ownership and the EARLY-PLACE BLOCK audit
    (RULES, "first ownership reads the other side",
     "    return next((k for k, flags in enumerate(flags_by_decision) if flags.get(coord) == faction), None)",
     "    return next((k for k, flags in enumerate(flags_by_decision) if flags.get(coord) is not None), None)"),
    (RULES, "the counterfactual does not remove the early places",
     "    free_without = max(capacity - (counted - early_counted), 0)", "    free_without = max(capacity - counted, 0)"),
    (RULES, "the counterfactual removes every counted place", "    free_without = max(capacity - (counted - early_counted), 0)",
     "    free_without = capacity"),
    (RULES, "a placed claimant may be blocked",
     '        blocked = c["feasible"] and c["unit"] not in actual and c["unit"] in without',
     '        blocked = c["feasible"] and c["unit"] in without'),
    (RULES, "a claimant that cannot arrive may be blocked",
     '        blocked = c["feasible"] and c["unit"] not in actual and c["unit"] in without',
     '        blocked = c["unit"] not in actual and c["unit"] in (without | {x["unit"] for x in claimants})'),
    (RULES, "the audit accepts a ranking that does not reproduce stage 1", "    if actual != set(selected):",
     "    if False:"),
    (RULES, "212 deadline exclusive", '    if first_own is None or first_own > rules["first_ownership_deadline"]:',
     '    if first_own is None or first_own >= rules["first_ownership_deadline"]:'),
    (RULES, "212 never owned passes", '    if first_own is None or first_own > rules["first_ownership_deadline"]:',
     '    if first_own is not None and first_own > rules["first_ownership_deadline"]:'),
    (RULES, "212 blocks ignored", '    if blocks > rules["early_place_blocks_allowed"]:', "    if False:"),
    # -- disposition and public guards
    (RULES, "both refutations read as C2 only", "    if c2_bad and b_bad:", "    if False:"),
    (RULES, "212 refutation ignored", "    if b_bad:\n        return {\"disposition\": DISPOSITIONS[3]}",
     "    if False:\n        return {\"disposition\": DISPOSITIONS[3]}"),
    (RULES, "structural problems do not invalidate", "    if problems or c2 is None or c212 is None:",
     "    if c2 is None or c212 is None:"),
    (RULES, "the stage-1 identity may be published", "    return tb.CANDIDATE_ID in text or sc.V3_DIGEST in text",
     "    return False"),
    # -- the observer
    (CAPTURE, "the add-on memory chain is not checked", '            "addon_memory": addon_memory == expected_memory[1]}',
     '            "addon_memory": True}'),
    (CAPTURE, "the emitted actions are not compared",
     '    return {"actions": rd.plain(decision["submitted"]) == rebuilt["actions"],',
     '    return {"actions": True,'),
    (CAPTURE, "prefix digests read every seat's actions",
     '    actions = [sp.actions_digest([a["action"] for a in step.get("submitted") or () if a["seat"] == seat])',
     '    actions = [sp.actions_digest([a["action"] for a in step.get("submitted") or ()])'),
    (CAPTURE, "a withheld action is not a changed unit", "set(a) | set(b) if a.get(u) != b.get(u)",
     "set(a) & set(b) if a.get(u) != b.get(u)"),
    # -- the analysis driver
    (ANALYSIS, "the audit summary counts placements as blocks",
     '            "early_place_blocks": sum(1 for r in rows if r["early_place_block"]),',
     '            "early_place_blocks": sum(1 for r in rows if r["placed"]),'),
    (ANALYSIS, "the audit window starts after the divergence",
     'if problem is not None and k >= ref["divergence"] and (first_own is None or k < first_own):',
     'if problem is not None and k > ref["divergence"] and (first_own is None or k < first_own):'),
    (ANALYSIS, "the public files may name the stage-1 identity", "        if sp.forbidden_identity(text):",
     "        if False:"),
    (ANALYSIS, "candidate memory carried into the next stream",
     "    differences: List[int] = []\n    memory: Tuple[Tuple[int, int], ...] = ()",
     "    differences: List[int] = []\n    memory: Tuple[Tuple[int, int], ...] = CARRIED"),
]


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    return env


def digest_of_candidate(root: Path) -> str:
    """The candidate's policy-source digest computed over ``root``'s package (the card builder's source list)."""
    script = ("import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'scripts'); import build_s17_card as b; "
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
        # a mutated candidate is a new source digest: re-pin it inside the copy (rules module and the whitelist test),
        # so that only the logic tests, never the digest pin, can catch the defect
        old = digest_of_candidate(REPO_ROOT)
        new = digest_of_candidate(root)
        for rel in (RULES, Path("tests/test_t9_post_stage_v6.py")):
            text = (root / rel).read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise SystemExit(f"the candidate digest occurs {text.count(old)} times in {rel}")
            (root / rel).write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    (root / CARD).unlink()
    built = subprocess.run([sys.executable, "scripts/build_s17_card.py"], cwd=root, env=env_for(root),
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
    return done.returncode == 0, built


def run(mutation) -> dict:
    source, name, old, new = mutation
    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutation {name!r}: original text occurs {text.count(old)} times")
    passed, built = tests_pass({source: text.replace(old, new)})
    return {"mutation": name, "module": source.as_posix(), "killed": not passed, "card_rebuilt": built}


def digest(path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    passed, built = tests_pass({})
    if not (passed and built):
        raise SystemExit("the unmutated tests fail (or the card cannot be built) in the temporary copy; kills would "
                         "be vacuous")
    results = [run(m) for m in MUTATIONS]
    sources = (CANDIDATE, RULES, CAPTURE, ANALYSIS, Path("tests/test_t9_post_stage_v6.py"),
               Path("tests/test_s17_probe.py"))
    payload = {"schema": "miaosuan-s17-mutation/1", "sources": {p.as_posix(): digest(p) for p in sources},
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
