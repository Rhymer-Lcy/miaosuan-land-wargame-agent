"""Sprint 34 offline architecture comparison: populations, gates and the registered selection rule.

Registered in ``docs/SPRINT34_INTEGRATED_AGENT.md`` section 8 before the comparison was run. Populations:

* ``M-inert``: every eligible SDK scenario, both seats, the candidate against the inert control, in the model world;
* ``M-v2``: the same, against ``baseline-v2``;
* ``G``: genuine engine observations of ``baseline-v2`` seats (the replay corpus and the full-step timelines), every
  decision re-decided by the candidate with its own memory chain; actions compared with ``baseline-v2``'s.

Candidates: the two architectural variants (``CT``, ``MO``). Ablations are reported and never selected.

The rule (:func:`select`) is a pure function of the per-candidate summaries (:func:`summarise`), so it is tested on
synthetic summaries.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

CANDIDATES = ("CT", "MO")
DEADLOCK_WAIT = 300
LATENCY_P99_MS = 100.0
LATENCY_MAX_MS = 1000.0
NONTRIVIAL_SHARE = 0.01
NON_INFERIORITY = 0.98


def summarise_model(games: Iterable[Mapping[str, Any]], candidate: str) -> Dict[str, Any]:
    """Aggregate model games in which ``candidate`` played one seat (its seat's figures only)."""
    out = {"games": 0, "objective_value": 0, "objective_value_max": 0, "rejections": 0, "fallbacks": 0,
           "replay_mismatches": 0, "replay_checks": 0, "model_refusals": 0, "max_wait": 0, "wait_unit_steps": 0,
           "latency_ms_max": 0.0, "friendly_exposure": 0, "embarked": 0, "indirect_orders": 0, "first_owned": 0,
           "first_owned_steps": []}
    for g in games:
        for seat, s in g["seats"].items():
            if s["agent"] != candidate:
                continue
            colour = int(seat)
            out["games"] += 1
            out["objective_value"] += int(g["occupy"]["red_occupy" if colour == 0 else "blue_occupy"])
            out["objective_value_max"] += int(g.get("objective_value_total", 0))
            out["rejections"] += sum(s["rejected"].values())
            out["fallbacks"] += s["fallbacks"]
            out["replay_mismatches"] += s["replay_mismatches"]
            out["replay_checks"] += s["replay_checks"]
            out["model_refusals"] += g["model_refusals"]
            out["max_wait"] = max(out["max_wait"], int(g["max_wait"][str(colour)] if str(colour) in g["max_wait"]
                                                       else g["max_wait"][colour]))
            out["wait_unit_steps"] += int(g["wait_unit_steps"][str(colour)] if str(colour) in g["wait_unit_steps"]
                                          else g["wait_unit_steps"][colour])
            out["latency_ms_max"] = max(out["latency_ms_max"], float(s["latency_ms_max"] or 0.0))
            out["friendly_exposure"] += s.get("friendly_exposure_unit_steps", 0)
            out["embarked"] += s["embarked"]
            out["indirect_orders"] += s["indirect_orders"]
            for hex_, (owner, step) in g["first_owner"].items():
                if owner == colour:
                    out["first_owned"] += 1
                    out["first_owned_steps"].append(step)
    steps = sorted(out.pop("first_owned_steps"))
    out["first_owned_median_step"] = steps[len(steps) // 2] if steps else None
    return out


def gates(model: Mapping[str, Mapping[str, Any]], genuine: Mapping[str, Any]) -> Dict[str, bool]:
    """``model``: population -> summary; ``genuine``: the candidate's genuine-observation summary."""
    pops = list(model.values())
    return {
        "G1 no rejected or refused action": all(p["rejections"] == 0 and p["model_refusals"] == 0 for p in pops)
        and genuine["rejections"] == 0 and genuine["independent_illegal"] == 0,
        "G2 no fallback or contract error": all(p["fallbacks"] == 0 for p in pops)
        and genuine["fallbacks"] == 0 and genuine["contract_errors"] == 0,
        "G3 replay identical": all(p["replay_mismatches"] == 0 and p["replay_checks"] > 0 for p in pops),
        "G4 no deadlock wait": all(p["max_wait"] < DEADLOCK_WAIT for p in pops),
        "G5 latency": genuine["latency_ms_p99"] <= LATENCY_P99_MS and genuine["latency_ms_max"] <= LATENCY_MAX_MS
        and all(p["latency_ms_max"] <= LATENCY_MAX_MS for p in pops),
        "G6 nontrivial action differences": genuine["decisions_differing"] >= NONTRIVIAL_SHARE * max(1, genuine["play_decisions"]),
        "G7 no friendly exposure": all(p["friendly_exposure"] == 0 for p in pops),
        "G8 every population played": all(p["games"] > 0 for p in pops) and genuine["play_decisions"] > 0,
    }


def select(summaries: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """``summaries``: candidate -> {"model": {population: summary}, "genuine": summary}."""
    passed = {c: gates(s["model"], s["genuine"]) for c, s in summaries.items()}
    eligible = [c for c in CANDIDATES if c in passed and all(passed[c].values())]
    progress = {c: {p: summaries[c]["model"][p]["objective_value"] for p in ("M-inert", "M-v2")} for c in summaries}
    if not eligible:
        return {"selected": None, "rule": "no candidate passed every gate", "gates": passed, "progress": progress}
    if eligible == ["CT"] or eligible == ["MO"]:
        return {"selected": eligible[0], "rule": "the only candidate that passed every gate", "gates": passed,
                "progress": progress}
    mo, ct = progress["MO"], progress["CT"]
    if mo["M-inert"] >= NON_INFERIORITY * ct["M-inert"] and mo["M-v2"] >= NON_INFERIORITY * ct["M-v2"]:
        return {"selected": "MO", "rule": "both passed; MO within 2% of CT's model objective value in both populations",
                "gates": passed, "progress": progress}
    total = {c: progress[c]["M-inert"] + progress[c]["M-v2"] for c in ("CT", "MO")}
    choice = "MO" if total["MO"] > total["CT"] else "CT"
    return {"selected": choice, "rule": "both passed; MO not within 2% of CT; higher total model objective value",
            "gates": passed, "progress": progress}
