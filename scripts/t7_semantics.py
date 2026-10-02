"""T7 design study: the versioned action-semantics matrix (``evaluation/t7-design-1/semantics.json``).

    python scripts/t7_semantics.py [--check]

Every claim carries one evidence level (``docs/T7_DESIGN.md``, section 5), its provenance and its scope. Claims that
rest on observations are computed here from ``audit.json`` (the study's public aggregates) and asserted: if the data
did not support the stated level, the script stops instead of writing the matrix. Documented claims cite the
published rules (section 3, D1 to D10) and Sprint 4's engine facts.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "t7-design-1"
VERSION = 1
POPULATIONS = ("H0", "H1", "H2")


def rows(audit: Mapping[str, Any], populations: Iterable[str] = POPULATIONS) -> List[Dict[str, Any]]:
    out = []
    for p in populations:
        for r in audit["semantics_rows"][p]:
            out.append(dict(r, population=p))
    return out


def total(items: Iterable[Mapping[str, Any]]) -> int:
    return sum(r["unit_decisions"] for r in items)


def claim(cid: str, family: str, text: str, level: str, provenance: str, scope: str,
          evidence: Mapping[str, Any]) -> Dict[str, Any]:
    return {"id": cid, "family": family, "claim": text, "level": level, "provenance": provenance, "scope": scope,
            "evidence": dict(evidence)}


def build() -> Dict[str, Any]:
    audit = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
    all_rows = rows(audit)
    play = [r for r in all_rows if r["stage"] == "play"]
    pops = audit["populations"]
    claims: List[Dict[str, Any]] = []

    # ---- T7-A change state
    a = [r for r in play if r["type"] == 6]
    sets = collections.Counter()
    for r in a:
        kind = "infantry" if r["archetype"].startswith("1.") else "vehicle" if r["archetype"].startswith("2.") else "other"
        sets[(kind, tuple(r["options"][0][1]))] += r["unit_decisions"]
    allowed = {("infantry", (2, 3, 4)), ("vehicle", (4, 5)), ("vehicle", (5,))}
    assert set(sets) == allowed, sets
    assert all(0 not in s and 1 not in s for _, s in sets)
    claims.append(claim(
        "A-1", "T7-A", "Listed change-state options: vehicles {4 concealment, 5 half speed} or {5}; infantry {2 and 3 "
        "charge, 4 concealment}; option 0 (normal) and option 1 (march) were never listed for any unit",
        "DIRECTLY OBSERVED", "seat observations", "H0, H1, H2, play stage",
        {f"{k} {list(s)}": n for (k, s), n in sorted(sets.items())}))
    moving_6 = total(r for r in a if r["situation"]["has_path"] or r["situation"]["speed>0"])
    stationary_6 = total(r for r in a if r["situation"]["stop"] == 1)
    stopping_6 = total(r for r in a if r["situation"]["stop"] == 0 and r["situation"]["move_to_stop_remain_time>0"])
    assert moving_6 == 0 and stationary_6 + stopping_6 == total(a)
    claims.append(claim(
        "A-2", "T7-A", "Action 6 is listed only for units without a move path: stationary units (stop 1) and units in "
        "the move-to-stop transition; never for a unit with a move path", "DIRECTLY OBSERVED", "seat observations",
        "H0, H1, H2, play stage", {"stationary": stationary_6, "in move-to-stop transition": stopping_6,
                                   "with a move path": moving_6}))
    keep_6 = [r for r in a if r["situation"]["keep>0"]]
    keep_sets = {tuple(r["options"][0][1]) for r in keep_6}
    assert keep_sets == {(5,)}
    claims.append(claim(
        "A-3", "T7-A", "A suppressed vehicle is listed half speed only, never concealment, consistent with the rule that "
        "suppression prevents concealment (D4)", "DIRECTLY OBSERVED", "seat observations", "H0, H1, H2, play stage",
        {"suppressed unit-decisions": total(keep_6)}))
    dep = {p: pops[p]["decisions_listing"].get("deployment:6", 0) for p in POPULATIONS}
    claims.append(claim(
        "A-4", "T7-A", "Action 6 is listed in every deployment decision; whether a change ordered during deployment, "
        "while cur_step stands still, completes before play is unknown", "DIRECTLY OBSERVED (listing); UNKNOWN (effect)",
        "seat observations", "H0, H2 deployment decisions",
        {"deployment decisions listing 6": dep, "deployment decisions": {p: pops[p]["decisions"].get("deployment", 0)
                                                                          for p in POPULATIONS}}))
    states = collections.Counter()
    for r in all_rows:
        states[r["situation"]["move_state"]] += r["unit_decisions"]
    changes = {p: {k: v for k, v in audit["transitions"][p]["field_changes"].items() if k.startswith("move_state")}
               for p in POPULATIONS}
    cs_episodes = {p: [k for k in audit["transitions"][p]["episodes"] if k.startswith("change_state")] for p in POPULATIONS}
    assert set(states) == {0} and not any(changes.values()) and not any(cs_episodes.values())
    claims.append(claim(
        "A-5", "T7-A", "move_state is 0 for every listed own unit, never changes, and change_state_remain_time is never "
        "positive: no state transition occurs in any record, so no transition duration, speed or observation effect is "
        "observed", "DIRECTLY OBSERVED", "seat observations", "H0, H1, H2", {"unit-decisions with move_state 0": states[0]}))
    missing = {p: pops[p]["missing_fields"] for p in POPULATIONS}
    assert all(set(m) <= {"play:target_state", "deployment:target_state"} for m in missing.values())
    claims.append(claim(
        "A-6", "T7-A", "The documented unit field target_state is absent from every unit record read; every other field "
        "the audit reads is present", "DIRECTLY OBSERVED (CONTRADICTED for the documentation's field list)",
        "seat observations", "H0, H1, H2", {"missing": missing}))
    claims.extend([
        claim("A-7", "T7-A", "Entering concealment takes 75 s, during which the unit executes no other command; a tank "
              "firing interrupts it; suppression prevents or interrupts it; once concealed, moving or firing ends it at no "
              "time cost", "DOCUMENTED", "published rules (D4)", "not observed", {}),
        claim("A-8", "T7-A", "A concealed unit is observed at half distance (not for a vehicle lower than its observer) "
              "and is a favourable target in the direct- and indirect-fire tables", "DOCUMENTED", "published rules (D4)",
              "not observed", {}),
        claim("A-9", "T7-A", "March: vehicles only, on a road hex, after locking weapons; 75 s to enter and to leave; no "
              "fire, embarking or leaving the road while marching; blocked by a stopped or non-marching unit in the next "
              "hex; the largest adverse target modifier", "DOCUMENTED", "published rules (D2)", "never listed", {}),
        claim("A-10", "T7-A", "March hex time 8 s per unit of march cost (90 km/h on a 200 m hex, cost defined relative to "
              "the mode's maximum speed)", "DERIVED", "D2, D9, D10", "unverified; never marched", {}),
        claim("A-11", "T7-A", "Charge doubles or quadruples infantry speed and adds one fatigue level per charged hex; "
              "second-level fatigue stops movement; no transition time is documented", "DOCUMENTED (speed, fatigue); "
              "UNKNOWN (transition)", "published rules (D3)", "never ordered", {}),
        claim("A-12", "T7-A", "Half speed (option 5) has no documented effect other than crossing minefields",
              "DOCUMENTED", "published rules (D5)", "never ordered", {}),
        claim("A-13", "T7-A", "Whether and when option 1 (march) is listed, e.g. after a lock on a road hex", "UNKNOWN",
              "no record", "never listed", {}),
    ])

    # ---- T7-B stop
    b = [r for r in play if r["type"] == 10]
    no_path_10 = total(r for r in b if not r["situation"]["has_path"])
    waiting = total(r for r in b if r["situation"]["has_path"] and not r["situation"]["speed>0"])
    traversing = total(r for r in b if r["situation"]["has_path"] and r["situation"]["speed>0"])
    aircraft = total(r for r in b if r["archetype"].startswith("3."))
    assert no_path_10 == 0 and aircraft > 0
    waiting_audit = {p: pops[p]["no_executable_opportunity"].get(
        "play:10:speed 0 with a move path (ground unit; the Sprint 4 case when its next hex is full)", 0)
        for p in POPULATIONS}
    assert sum(waiting_audit.values()) == total(r for r in b if r["situation"]["has_path"] and not r["situation"]["speed>0"]
                                                and r["archetype"][0] in "12")
    claims.append(claim(
        "B-1", "T7-B", "Action 10 is listed only for units with a non-empty move path, ground and air, traversing or "
        "waiting; never for a unit without a path", "DIRECTLY OBSERVED", "seat observations", "H0, H1, H2, play stage",
        {"traversing (speed above 0)": traversing, "speed 0 with a path": waiting, "without a path": no_path_10,
         "aircraft": aircraft, "ground units with speed 0 and a path": waiting_audit}))
    arrivals: Dict[str, Any] = {}
    for p in POPULATIONS:
        for arch, d in audit["transitions"][p]["arrivals"].items():
            s = d.get("stop_after")
            if s:
                assert s["min"] == s["max"] == 75, (p, arch, s)
                arrivals[f"{p} {arch}"] = s["n"]
            m = d.get("move_listed_after")
            if m:
                assert m["max"] in (0, 129) and m["median"] == 0
    claims.append(claim(
        "B-2", "T7-B", "At the natural end of a path (no stop order) stop becomes 1 exactly 75 steps after the move path "
        "empties, in every arrival observed to settle; movement is listed again at once (a normal stop)",
        "DIRECTLY OBSERVED", "seat observations", "H0, H1, H2 arrivals that settled", {"settled arrivals": arrivals}))
    shoot_after = {}
    for p in POPULATIONS:
        for arch, d in audit["transitions"][p]["arrivals"].items():
            if d.get("shoot_listed_after"):
                shoot_after[f"{p} {arch}"] = d["shoot_listed_after"]
    assert all(v["min"] >= 75 for k, v in shoot_after.items() if k.split()[1] != "2.0")
    assert any(v["min"] < 75 for k, v in shoot_after.items() if k.split()[1] == "2.0")
    claims.append(claim(
        "B-3", "T7-B", "After an arrival, infantry fighting vehicles and other non-tank units list a shoot option only "
        "from 75 steps on; tanks list it at once (they fire while moving, D8)", "DIRECTLY OBSERVED", "seat observations",
        "arrivals with a later shoot listing", {"shoot listed after (steps)": shoot_after}))
    claims.extend([
        claim("B-4", "T7-B", "A stop issued to a unit waiting in front of a full hex is echoed without error, sets "
              "flag_force_stop one step later, withdraws every listed action and is deferred while the next hex stays full",
              "DIRECTLY OBSERVED", "Sprint 4 probe P1 (docs/PS1_ENGINE_PROBE.md)", "4 units, one game", {}),
        claim("B-5", "T7-B", "The effect of a stop on a traversing unit: completes its hex, then a 75 s penalty "
              "transition during which it takes no action (D6)", "DOCUMENTED; UNKNOWN on engine 4.1.0",
              "published rules (D6)", "never issued in this project", {}),
        claim("B-6", "T7-B", "speed above 0 does not exclude a unit traversing towards a hex that fills before it "
              "arrives (448 such unit-steps in the Sprint 2 split game)", "DIRECTLY OBSERVED",
              "docs/PS1_DESIGN.md 11.2", "one game", {}),
    ])

    # ---- T7-C weapon lock and unfold
    c11 = [r for r in play if r["type"] == 11]
    bad = [r for r in c11 if not (r["situation"]["stop"] == 1 and not r["situation"]["has_path"]
                                  and r["situation"]["weapon_unfold_state"] == 1 and not r["situation"]["keep>0"]
                                  and not r["archetype"].startswith(("1.", "3.")))]
    assert not bad, bad[:2]
    by_arch = collections.Counter()
    for r in c11:
        by_arch[r["archetype"]] += r["unit_decisions"]
    claims.append(claim(
        "C-1", "T7-C", "Action 11 is listed only for stationary vehicles (stop 1, no path) with unfolded weapons that are "
        "not suppressed, never in the move-to-stop transition, never for infantry or aircraft", "DIRECTLY OBSERVED",
        "seat observations", "H0, H1, H2, play stage", {"unit-decisions by archetype": dict(sorted(by_arch.items()))}))
    unfold_values = collections.Counter()
    for r in all_rows:
        unfold_values[r["situation"]["weapon_unfold_state"]] += r["unit_decisions"]
    assert set(unfold_values) == {1}
    assert not any(k.startswith("weapon_unfold") for p in POPULATIONS for k in audit["transitions"][p]["field_changes"])
    assert not any(pops[p]["decisions_listing"].get(f"{s}:12") for p in POPULATIONS for s in ("play", "deployment"))
    claims.append(claim(
        "C-2", "T7-C", "Every listed own unit's weapon_unfold_state is 1 (unfolded) throughout; action 12 is never listed; "
        "no lock or unfold occurs in any record", "DIRECTLY OBSERVED", "seat observations", "H0, H1, H2",
        {"unit-decisions unfolded": unfold_values[1]}))
    claims.extend([
        claim("C-3", "T7-C", "The observation holds one lock state per unit (weapon_unfold_state, weapon_unfold_time), so "
              "per-weapon states cannot be represented; whether the engine keeps them per weapon is unknown",
              "DERIVED (schema); UNKNOWN (engine)", "observation note and records", "all records", {}),
        claim("C-4", "T7-C", "Locking and unfolding take 75 s each and exclude other commands; locking is required before "
              "march and unfolding after march before firing", "DOCUMENTED", "published rules (D2, D7)", "not observed", {}),
        claim("C-5", "T7-C", "Lock and unfold are listed in the deployment stage too (11: every deployment decision)",
              "DIRECTLY OBSERVED (listing); UNKNOWN (effect)", "seat observations", "H0, H2 deployment decisions",
              {"deployment decisions listing 11": {p: pops[p]["decisions_listing"].get("deployment:11", 0)
                                                   for p in POPULATIONS}}),
    ])
    issued = audit["issued_records"]["t7_actions_by_policy"]
    claims.append(claim(
        "X-1", "all", "No frozen policy (baseline-v0, v1, v2, the runtimes, the split candidate, the inert control) issued "
        "any T7 action in the registered records; the only T7 actions ever issued are the 4 stops of Sprint 4's probe P1",
        "DIRECTLY OBSERVED", "game records (R)", f"{audit['issued_records']['files']} game records",
        {"t7 actions by policy": issued}))
    return {"schema": "miaosuan-t7-semantics/1", "study_id": "t7-design-1", "version": VERSION,
            "levels": ["DOCUMENTED", "DIRECTLY OBSERVED", "DERIVED", "HYPOTHESIZED", "CONTRADICTED", "UNKNOWN"],
            "claims": claims}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    path = OUT / "semantics.json"
    if args.check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print("semantics identical" if same else "MISMATCH")
        return 0 if same else 1
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
