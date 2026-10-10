"""Sprint 35 offline comparison: populations, gates and the registered selection rule.

Registered in ``docs/SPRINT35_COALITION_AGENT.md`` section 8 before the comparison was run. Candidates: the two Sprint 35
architectures, ``CA`` (coalition allocator) and ``CM`` (coalition mission planner); the frozen Sprint 34 live candidate
``S34-MO`` is the control. Populations:

* ``M-inert`` and ``M-v2``: every eligible SDK scenario (registered naming rule), both seats, each agent against the
  inert control and against ``baseline-v2`` in the Sprint 34 model world (no combat damage);
* ``G``: genuine engine observations (the pinned replay corpus, Sprint 34's sixteen offline timelines and the 24 Sprint 34
  live games' full-step timelines, every seat that is not the inert control), every decision re-decided by each agent
  with its own memory chain; legality by the agent's validator and by an independent check;
* ``P``: the 57 held-objective loss episodes of Sprint 34's sixteen Stage A games, read on the Sprint 34 candidate's
  own recorded observations (each agent re-deciding the whole game with its own memory chain).

Only legality, determinism, latency, traffic, the movement race and decision-level facts are measured; the model has no
combat, and a re-decision on a recorded trajectory is not a counterfactual outcome. The rule (:func:`select`) is a pure
function of the per-candidate summaries, so it is tested on synthetic summaries.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

CANDIDATES = ("CA", "CM")
CONTROL = "S34-MO"
DEADLOCK_WAIT = 300
LATENCY_P99_MS = 100.0
LATENCY_MAX_MS = 1000.0
NONTRIVIAL_SHARE = 0.01
NON_INFERIORITY = 0.98
MODEL_FLOOR = 0.90
ALERT_SHARE = 0.5
RETENTION_SHARE = 0.5


def gates(model: Mapping[str, Mapping[str, Any]], genuine: Mapping[str, Any], precursors: Mapping[str, Any],
          control_model: Mapping[str, Mapping[str, Any]]) -> Dict[str, bool]:
    """``model``: population -> the candidate's model summary (``s34_offline.summarise_model`` fields);
    ``genuine``: its genuine-observation summary; ``precursors``: its loss-episode summary; ``control_model``: the same
    model summaries of ``S34-MO``."""
    pops = list(model.values())
    return {
        "G1 no rejected, refused or independently illegal action": all(
            p["rejections"] == 0 and p["model_refusals"] == 0 for p in pops)
        and genuine["rejections"] == 0 and genuine["independent_illegal"] == 0,
        "G2 no fallback or contract error": all(p["fallbacks"] == 0 for p in pops)
        and genuine["fallbacks"] == 0 and genuine["contract_errors"] == 0,
        "G3 model replay identical": all(p["replay_mismatches"] == 0 and p["replay_checks"] > 0 for p in pops),
        "G4 no deadlock wait": all(p["max_wait"] < DEADLOCK_WAIT for p in pops),
        "G5 latency": genuine["latency_ms_p99"] <= LATENCY_P99_MS and genuine["latency_ms_max"] <= LATENCY_MAX_MS
        and all(p["latency_ms_max"] <= LATENCY_MAX_MS for p in pops),
        "G6 differs from the Sprint 34 control": genuine["decisions_differing_from_control"]
        >= NONTRIVIAL_SHARE * max(1, genuine["play_decisions"]),
        "G7 no friendly exposure": all(p["friendly_exposure"] == 0 for p in pops),
        "G8 every population played": all(p["games"] > 0 for p in pops) and genuine["play_decisions"] > 0
        and precursors["episodes"] > 0,
        "G9 threat recognised before the loss": precursors["alerted"] >= ALERT_SHARE * precursors["episodes"],
        "G10 last defenders kept": precursors["departures"] > 0
        and precursors["departures_kept"] >= RETENTION_SHARE * precursors["departures"],
        "G11 no collapse of the movement race": all(
            model[p]["objective_value"] >= MODEL_FLOOR * control_model[p]["objective_value"] for p in model),
    }


def select(summaries: Mapping[str, Mapping[str, Any]], control: Mapping[str, Any]) -> Dict[str, Any]:
    """``summaries``: candidate -> {"model": {population: summary}, "genuine": summary, "precursors": summary};
    ``control``: S34-MO's {"model": ..., "fidelity": {"decisions": n, "differing": m}}.

    The precursor population is valid only when S34-MO's re-decisions reproduce its recorded actions at every decision
    (fidelity); otherwise nothing is selected. If both candidates pass every gate, CM is selected when its model
    objective value is at least 98% of CA's in both model populations (CM's extra modules - stance-driven fire
    support, arrival fire, guided fire, threat-limited transport - have engine-listed or engine-verified mechanisms but
    no value the model can show, while any movement they cost is measurable); otherwise CA. If one passes, it is
    selected; if neither, nothing is (``S35_ENGINEERING_BLOCKED`` unless a documented corrected revision passes)."""
    fidelity = control.get("fidelity") or {}
    passed = {c: gates(s["model"], s["genuine"], s["precursors"], control["model"]) for c, s in summaries.items()}
    progress = {c: {p: summaries[c]["model"][p]["objective_value"] for p in summaries[c]["model"]} for c in summaries}
    base = {"gates": passed, "progress": progress, "control_fidelity": fidelity}
    if not fidelity.get("decisions") or fidelity.get("differing", 1) != 0:
        return {"selected": None, "rule": "the control's re-decisions do not reproduce its recorded actions", **base}
    eligible = [c for c in CANDIDATES if c in passed and all(passed[c].values())]
    if not eligible:
        return {"selected": None, "rule": "no candidate passed every gate", **base}
    if len(eligible) == 1:
        return {"selected": eligible[0], "rule": "the only candidate that passed every gate", **base}
    cm, ca = progress["CM"], progress["CA"]
    if all(cm[p] >= NON_INFERIORITY * ca[p] for p in ca):
        return {"selected": "CM", "rule": "both passed; CM within 2% of CA's model objective value in both populations",
                **base}
    return {"selected": "CA", "rule": "both passed; CM not within 2% of CA's model objective value", **base}


def summarise_precursors(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """``rows``: one per loss episode for one agent: {"alerted": bool, "departure": bool, "kept": bool,
    "responded": bool, "stance_b150": str}."""
    out = {"episodes": len(rows), "alerted": sum(1 for r in rows if r["alerted"]),
           "departures": sum(1 for r in rows if r["departure"]),
           "departures_kept": sum(1 for r in rows if r["departure"] and r["kept"]),
           "responded": sum(1 for r in rows if r["responded"]), "stance_b150": {}}
    for r in rows:
        out["stance_b150"][r["stance_b150"]] = out["stance_b150"].get(r["stance_b150"], 0) + 1
    out["stance_b150"] = dict(sorted(out["stance_b150"].items()))
    return out
