"""T7 design study: the gates G1 to G5 and the research disposition (``docs/T7_DESIGN.md``, section 11).

    python scripts/t7_gates.py [--check]

Reads the study's public outputs (audit, candidates, semantics, selection, shadow, mutation) and the conditional
proposal ``docs/T7_SCREEN_PROPOSAL.md``; applies the gate criteria and the disposition order written in section 11
before any candidate result; writes ``evaluation/t7-design-1/gates.json``. Every verdict lists the evidence it used.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
EV = REPO_ROOT / "evaluation" / "t7-design-1"
PROPOSAL = REPO_ROOT / "docs" / "T7_SCREEN_PROPOSAL.md"
DESIGN = REPO_ROOT / "docs" / "T7_DESIGN.md"
#: Elements section 12 requires of the proposal, matched against its second-level headings.
PROPOSAL_ELEMENTS = ("Policy delta", "Identities", "Scenarios and seats", "Sample size", "Capture requirements",
                     "Safety endpoints", "Mechanism endpoints", "Primary metric", "Independent validation checks",
                     "Stopping rules")
PROBE_ENDPOINTS = ("E1", "E2", "E3", "E4", "E5", "E6")


def load(name: str) -> Dict[str, Any]:
    return json.loads((EV / name).read_text(encoding="utf-8"))


def g1(audit: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    fid = audit["baseline_v2_reconstruction"]
    sva = audit["seat_vs_all_seeing"]
    issued = audit["issued_capture_vs_record"]
    evidence = {
        "h0_pinned_digests_verified": all(i["verified"] for i in audit["inputs"] if i["population"] == "H0"),
        "capture_digests_recorded": sum(1 for i in audit["inputs"] if i["population"] != "H0"),
        "census_reconciled": audit["census_reconciliation"]["equal"],
        "crosscheck_agrees": all(v["agree"] for v in audit["crosscheck"].values()),
        "seat_vs_all_seeing_identical": all(sva[f"{p} identical in the all-seeing view"] ==
                                            sva[f"{p} seat-vs-all-seeing unit listings"] for p in ("H1", "H2")),
        "h2r_identical": audit["h2r_reproduction"]["identical_t7_listings"] == audit["h2r_reproduction"]["decisions_compared"],
        "issued_capture_equals_record": all(v["record"] == v["compact_log"] for v in issued.values()),
        "baseline_v0_replayed": fid["H0 baseline-v0 exact"] == fid["H0 decisions"],
        "baseline_v2_reconstructed": fid["H0 baseline-v2 reconstructed"] == fid["H0 decisions"],
        "real_record_test": "tests/test_real_t7_audit.py passed before the full run (docs/T7_DESIGN.md, 13.1); the "
                            "private suite rebuilds audit, candidates and post-hoc outputs byte for byte",
    }
    passed = all(v is True for k, v in evidence.items() if isinstance(v, bool)) and evidence["capture_digests_recorded"] > 0
    return ("PASS" if passed else "FAIL"), evidence


def g2(semantics: Dict[str, Any], shadow: Dict[str, Any], selection: Dict[str, Any],
       scores: Dict[str, Any], specification: str) -> Tuple[str, Dict[str, Any]]:
    selected = selection["selected"]
    claims = {c["id"]: c for c in semantics["claims"]}
    listed = all(shadow["populations"][p]["counts"].get("contract valid", 0) == shadow["populations"][p]["activations"]
                 for p in ("H0", "H1", "H2"))
    evidence = {
        "selected": selected,
        "observability_score": scores["scores"][selected]["O"]["score"],
        "option_listed_for_population": claims["A-1"]["level"] == "DIRECTLY OBSERVED" and listed,
        "listing_situation": claims["A-2"]["level"],
        "effect_documented": claims["A-7"]["level"] == "DOCUMENTED" and claims["A-8"]["level"] == "DOCUMENTED",
        "probe_endpoints_named": [e for e in PROBE_ENDPOINTS if re.search(rf"\b{e}\b", specification)],
    }
    if evidence["observability_score"] < 4:
        return "FAIL", evidence
    if not evidence["option_listed_for_population"]:
        return "UNRESOLVED", evidence
    ok = evidence["effect_documented"] and len(evidence["probe_endpoints_named"]) == len(PROBE_ENDPOINTS)
    return ("PASS" if ok else "FAIL"), evidence


def g3(shadow: Dict[str, Any], mutation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    checks: Dict[str, Any] = {}
    for p, block in shadow["populations"].items():
        c = block["counts"]
        checks[p] = {"baseline_v2_equal_everywhere": c["baseline-v2 equal"] == c["decisions"] and c["baseline-v2 differs"] == 0,
                     "prefix_equal_everywhere": c["prefix equal"] == c["decisions"],
                     "no_unit_with_two_actions": c["a unit with two actions"] == 0,
                     "nothing_added_to_a_baseline_unit": c["added to a unit baseline-v2 acted on"] == 0,
                     "nothing_added_outside_play": c["added outside the play stage"] == 0,
                     "contract_valid": c.get("contract valid", 0) == c.get("added", 0),
                     "agrees_with_the_independent_trigger": block["only_in_shadow"] == 0 and block["only_in_pool_predicate"] == 0,
                     "recorded_baseline_reproduced": c.get("recorded play actions equal", 0) == c.get("recorded play actions compared", 0)}
    determinism = shadow["determinism"]
    repeat = shadow["repeated_observation"]
    evidence = {"populations": checks, "second_run_identical": determinism["second_run_identical"],
                "permuted_run_identical": determinism["permuted_run_identical"],
                "repeated_observation_adds_nothing": repeat["actions added"] == 0,
                "mutation": f"{mutation['killed']} of {mutation['total']} killed",
                "mutation_survivors_documented": all(m["killed"] or m["reason_if_surviving"] for m in mutation["mutations"]),
                "known_unsafe_cases_excluded": "the shadow never stops a unit and refuses units in any transition or "
                                               "suppressed (tests/test_t7_shadow.py)"}
    passed = (all(all(v.values()) for v in checks.values()) and evidence["second_run_identical"]
              and evidence["permuted_run_identical"] and evidence["repeated_observation_adds_nothing"]
              and evidence["mutation_survivors_documented"])
    return ("PASS" if passed else "FAIL"), evidence


def g4(candidates: Dict[str, Any], selection: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    entry = candidates["summary"]["H0"][selection["selected"]]
    evidence = {"h0_scenarios_with_activations": len(entry["scenarios"]), "h0_witnessed_activations": entry["witness_true"],
                "h0_witnessed_units": entry["witness_units"]}
    if entry["activations"] == 0:
        return "FAIL", evidence
    if len(entry["scenarios"]) >= 2 and entry["witness_true"] >= 1:
        return "PASS", evidence
    return "UNRESOLVED", evidence


def section(text: str, heading: str) -> str:
    """The body of a second-level section whose heading starts with ``heading``."""
    match = re.search(rf"^## {re.escape(heading)}.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def specification() -> str:
    """Section 14 of the design document: the selected mechanism and its named probe endpoints."""
    text = DESIGN.read_text(encoding="utf-8")
    match = re.search(r"^## 14\..*?(?=^## 15\.|\Z)", text, re.M | re.S)
    return match.group(0) if match else ""


def g5(proposal: str) -> Tuple[str, Dict[str, Any]]:
    headings = re.findall(r"^## (.+?)\s*$", proposal, re.M)
    present = [e for e in PROPOSAL_ELEMENTS if any(h.startswith(e) for h in headings)]
    evidence = {"proposal": "docs/T7_SCREEN_PROPOSAL.md" if proposal else None, "required_elements_present": present,
                "missing": [e for e in PROPOSAL_ELEMENTS if e not in present],
                "mechanism_endpoints_need_no_simulation": bool(proposal)
                and "simulat" not in section(proposal, "Mechanism endpoints")}
    passed = bool(proposal) and not evidence["missing"] and evidence["mechanism_endpoints_need_no_simulation"]
    return ("PASS" if passed else "FAIL"), evidence


def disposition(gates: Dict[str, str], eligible_any: bool, fires: bool) -> str:
    if not eligible_any or not fires:
        return "SHELVE_T7_FOR_NOW"
    if gates["G1"] == "FAIL":
        return "REVISE"
    if gates["G2"] == "UNRESOLVED" or gates["G4"] == "UNRESOLVED":
        return "NEEDS_ENGINE_PROBE"
    if "FAIL" in (gates["G2"], gates["G3"], gates["G5"]):
        return "REVISE"
    return "READY_FOR_MECHANISM_PROBE"


def build() -> Dict[str, Any]:
    audit, candidates, semantics = load("audit.json"), load("candidates.json"), load("semantics.json")
    selection, scores, shadow, mutation = load("selection.json"), load("scores.json"), load("shadow.json"), load("mutation.json")
    proposal = PROPOSAL.read_text(encoding="utf-8") if PROPOSAL.exists() else ""
    results: Dict[str, Tuple[str, Dict[str, Any]]] = {
        "G1": g1(audit), "G2": g2(semantics, shadow, selection, scores, specification()), "G3": g3(shadow, mutation),
        "G4": g4(candidates, selection), "G5": g5(proposal)}
    verdicts = {k: v[0] for k, v in results.items()}
    eligible_any = any(b["eligible"] for b in selection["base"].values())
    fires = candidates["summary"]["H0"][selection["selected"]]["activations"] > 0 if selection["selected"] else False
    return {"schema": "miaosuan-t7-gates/1", "study_id": "t7-design-1", "selected": selection["selected"],
            "gates": {k: {"verdict": v[0], "evidence": v[1]} for k, v in results.items()},
            "disposition": disposition(verdicts, eligible_any, fires),
            "note": "a Sprint 5 research disposition; it changes no state of the hypothesis register by itself, and an "
                    "offline legality check validates no engine mechanism"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    out = EV / "gates.json"
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print("gates identical" if same else "MISMATCH")
        return 0 if same else 1
    out.write_text(text, encoding="utf-8", newline="\n")
    data = json.loads(text)
    print({k: v["verdict"] for k, v in data["gates"].items()}, data["disposition"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
