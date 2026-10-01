"""The registered runtime thread-pool qualification ``runtime-thread-qualification-1``.

Question: can NumPy's OpenBLAS thread pool, which every game process starts with one thread per logical CPU,
be constrained without changing engine or agent behaviour, and does constraining it improve the concurrency
tail and permit a higher safe worker count? The only variable is the numerical-library thread environment of
the game process: A, the current runtime with no such variable, and B, ``OPENBLAS_NUM_THREADS=1``. Policies,
routing, garbage collection and the engine installation are unchanged.

The workload and the serial references are those of the registered concurrency qualification
(``evaluation/concurrency-qualification-1/plan.json``), cited by digest.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import concurrency as cq
from . import shoot_experiment as sx
from .manifest import canonical_bytes

SCHEMA = "miaosuan-runtime-thread-plan/1"
PLAN_ID = "runtime-thread-qualification-1"
GAME_PREFIX = "rt1"
PURPOSE = "diagnostic"
RUNTIME_CANDIDATE = "baseline-v1-runtime-r2"
QUESTION = ("Can NumPy's OpenBLAS thread pool be constrained without changing engine or agent behaviour, and does "
            "that improve the concurrency tail and permit a higher safe game-worker count?")

#: The numerical-thread environment of each group, added to the game's environment before the interpreter starts.
ENVIRONMENTS = {"A": {}, "B": {"OPENBLAS_NUM_THREADS": "1"}}
ENVIRONMENT_ROLES = {
    "A": "current runtime: no numerical-thread variable; OpenBLAS starts one thread per logical CPU",
    "B": "constrained: OPENBLAS_NUM_THREADS=1, OpenBLAS's own variable; no OpenMP, MKL or other variable, "
         "because the runtime holds no such library",
}
GROUP_POLICIES = {"B": sx.RUNTIME_R1_CODE_ID, "C": sx.CANDIDATE_ID}

TIERS = (
    {"tier": "P-A", "environment": "A", "workers": 1, "corpus": "equivalence", "probe": True,
     "role": "BLAS usage probe: the 16-game corpus under the current runtime with the call-counting shim preloaded"},
    {"tier": "E-B", "environment": "B", "workers": 1, "corpus": "equivalence", "probe": False,
     "role": "behavioural equivalence: the 16-game corpus (both policies) under the constrained runtime, serially"},
    {"tier": "B-w01", "environment": "B", "workers": 1, "corpus": "block", "blocks": 2, "probe": False,
     "role": "constrained throughput base and serial control"},
    {"tier": "A-w16", "environment": "A", "workers": 16, "corpus": "block", "blocks": 8, "probe": False,
     "role": "current runtime at 16 workers, measured with the new per-thread instrumentation"},
    {"tier": "B-w16", "environment": "B", "workers": 16, "corpus": "block", "blocks": 8, "probe": False,
     "role": "constrained runtime at 16 workers"},
    {"tier": "A-w24", "environment": "A", "workers": 24, "corpus": "block", "blocks": 12, "probe": False,
     "role": "current runtime at 24 workers"},
    {"tier": "B-w24", "environment": "B", "workers": 24, "corpus": "block", "blocks": 12, "probe": False,
     "role": "constrained runtime at 24 workers"},
)
OPTIONAL_TIERS = (
    {"tier": "B-w32", "environment": "B", "workers": 32, "corpus": "block", "blocks": 16, "probe": False,
     "role": "only if B-w24 met every worker criterion with parallel efficiency of at least 0.85"},
)
OPTIONAL_EFFICIENCY = 0.85
BENEFIT = {"throughput_gain": 1.05, "cpu_per_game_ratio": 0.85}
CRITERIA = dict(cq.CRITERIA)
NOT_PLANNED = ("w40 and above: 40 workers would exceed the courtesy ceiling of 32 logical CPUs (half the host) "
               "that the concurrency qualification registered", "A-w01: the committed concurrency qualification "
               "measured the current runtime serially (w01); A is re-measured only where B is compared with it")

PROBE = {
    "source": "scripts/blas_count_shim.c",
    "build": "gcc -shared -fPIC -O2 -o WORK/blas_count.so scripts/blas_count_shim.c -ldl",
    "environment": ["LD_PRELOAD", "BLAS_COUNT_LIBRARY", "BLAS_COUNT_DEPS", "BLAS_COUNT_OUTPUT"],
    "import_baseline": {"cblas_sdot64_": 1},
    "reading": ("Each of the 57 BLAS and LAPACK entry points NumPy imports from its OpenBLAS is counted. Importing "
                "NumPy calls cblas_sdot64_ once (its own check); any further call during a game is BLAS work by "
                "the engine, the policy or the harness. The shim forwards every call unchanged."),
}
PROCESS_CHECK = {
    "serial_repetitions": 10, "concurrent": [16, 24], "rounds": 2, "settle_seconds": 0.5, "sanity_repetitions": 3,
    "reading": ("Fresh interpreters without the engine, in each environment: threads before and after importing NumPy, "
                "the import's wall and CPU time, CPU after a 0.5 s settle (which includes the pool's spin), mapped BLAS, "
                "OpenMP, LAPACK or MKL libraries, and context switches from wait4; then 16 and 24 interpreters started "
                "at once, twice each; then five NumPy operations hashed bit for bit as a runtime sanity check. The "
                "sanity hashes are reported, not criteria: they show which operations OpenBLAS's threading can change, "
                "not whether the engine performs them."),
}
EQUIVALENCE = (
    "Deterministic configurations: the state chain, the step count and every seat's trace chain equal the serial "
    "reference of the configuration and policy group (identical in all 15 serial repetitions of the current runtime).",
    "Stochastic configurations: the state digests and every seat's trace digests up to the serial common prefix "
    "equal the serial prefix; the first divergence from every serial repetition is reported against the first shot.",
    "No two stochastic games of a tier share a state chain, and none equals a serial repetition's chain.",
    "Every factual refusal class is a known class; no contract error, project-gate rejection or replay mismatch.",
    "Any difference before the serial common prefix, or in a deterministic game, blocks the constrained runtime; "
    "no difference is dismissed as floating point.",
)
INTEGRITY = cq.SAFETY_CHECKS
DISPOSITION_RULE = (
    "BLOCKED if any tier fails an equivalence, safety, engine-state or ledger check. Otherwise PROMOTED AS "
    "baseline-v1-runtime-r2 if at least one benefit holds: (a) a constrained tier of more than 16 workers is "
    "acceptable under the concurrency qualification's worker criteria computed against B-w01; (b) at 16 or 24 "
    "workers the constrained throughput is at least 1.05 times the current runtime's in the same run; (c) at 16 "
    "workers the median CPU time per game under the constrained runtime is at most 0.85 times the current "
    "runtime's. Otherwise RETAIN runtime-r1, and no runtime identity is created."
)
WORKER_RULE = (
    "Only constrained tiers count, against B-w01: speedup >= 1.5, parallel efficiency >= 0.70, decision-latency "
    "p99 <= 1.5 x B-w01's and maximum <= 2 x B-w01's, our mean CPU use <= 32 logical CPUs, peak memory <= 10% of "
    "the host. If the runtime is promoted, recommend the smallest acceptable count among 16, 24 and 32 whose "
    "speedup is at least 0.85 of the largest acceptable speedup; if none is acceptable, retain 16. If the runtime "
    "is not promoted, the recommendation stays 16 workers on runtime-r1. No untested count is recommended."
)
MEASUREMENTS = cq.MEASUREMENTS + (
    "per game at the start of the game command: wall time since the process started, CPU time, threads and the "
    "process's context switches so far (startup and import cost)",
    "per game at its end: per-thread CPU time, voluntary and involuntary context switches and CPU migrations; and "
    "garbage-collection pauses per generation (count, total, longest, and every pause over 50 ms), observed "
    "through gc.callbacks without changing collection",
)


def tier_spec(plan: Mapping[str, Any], tier: str) -> Dict[str, Any]:
    for spec in list(plan["tiers"]) + list(plan["optional_tiers"]):
        if spec["tier"] == tier:
            return dict(spec)
    raise KeyError(f"unknown tier {tier!r}")


def sequence(plan: Mapping[str, Any]) -> List[str]:
    return [t["tier"] for t in plan["tiers"]] + [t["tier"] for t in plan["optional_tiers"]]


def tier_queue(plan: Mapping[str, Any], tier: str) -> List[Dict[str, Any]]:
    """The tier's games in dispatch order. Block tiers: longest expected first; corpus tiers: schedule order."""
    spec = tier_spec(plan, tier)
    if spec["corpus"] == "equivalence":
        items = []
        for game in plan["equivalence"]["corpus"]:
            scenario, condition, group, _ = game.split(".")
            items.append((f"{scenario}.{condition}", group, plan["equivalence"]["references"][game]))
    else:
        block = {entry["config"]: entry for entry in plan["block"]}
        order = [entry["config"] for entry in plan["block"]]
        pairs = [(b, c) for b in range(spec["blocks"]) for c in order]
        pairs.sort(key=lambda item: (-block[item[1]]["expected_wall_seconds"], order.index(item[1]), item[0]))
        items = [(config, "C", block[config]["reference"]) for _, config in pairs]
    queue = []
    for k, (config, group, reference) in enumerate(items, start=1):
        scenario, condition = config.split(".")
        policies = plan["groups"][group][condition]
        suffix = f".{group}" if spec["corpus"] == "equivalence" else ""
        queue.append({"seq": k, "game_id": f"{GAME_PREFIX}.{tier}.{k:03d}.{config}{suffix}", "config": config,
                      "group": group, "policy": GROUP_POLICIES[group], "scenario_id": scenario, "condition": condition,
                      "red": policies["red"], "blue": policies["blue"], "reference": reference})
    return queue


def build(cq_plan: Mapping[str, Any], cq_plan_sha256: str, manifest: Mapping[str, Any], manifest_sha256: str,
          probe_sha256: str, scheduler_identity: str) -> Dict[str, Any]:
    groups = {group: {condition: dict(manifest["groups"][group]["conditions"][condition]) for condition in ("C1", "C2", "C3")}
              for group in sx.GROUPS}
    return {
        "schema": SCHEMA, "plan_id": PLAN_ID, "purpose": PURPOSE, "question": QUESTION,
        "variable": "the numerical-library thread environment of each game process, and nothing else",
        "environments": {name: dict(env) for name, env in ENVIRONMENTS.items()},
        "environment_roles": dict(ENVIRONMENT_ROLES),
        "runtime_candidate": RUNTIME_CANDIDATE,
        "identities": {
            "tactical": "baseline-v2", "policy_source": dict(manifest["groups"]["C"]["policy_source"]),
            "golden_trace_chain": manifest["groups"]["C"]["golden_trace_chain"],
            "runtime": "baseline-v1-runtime-r1", "runtime_policy_source_sha256": manifest["groups"]["B"]["policy_source"]["sha256"],
            "scheduler": scheduler_identity,
        },
        "inputs": {"experiment": sx.EXPERIMENT_NAME, "manifest_sha256": manifest_sha256,
                   "concurrency_plan": cq.PLAN_ID, "concurrency_plan_sha256": cq_plan_sha256,
                   "players": [dict(p) for p in manifest["players"]], "randomness": dict(manifest["randomness"])},
        "groups": groups, "group_policies": dict(GROUP_POLICIES),
        "block": [dict(entry) for entry in cq_plan["block"]],
        "equivalence": {"corpus": list(cq_plan["equivalence"]["corpus"]),
                        "references": dict(cq_plan["equivalence"]["references"])},
        "tiers": [dict(t) for t in TIERS], "optional_tiers": [dict(t) for t in OPTIONAL_TIERS],
        "optional_efficiency": OPTIONAL_EFFICIENCY, "not_planned": list(NOT_PLANNED),
        "queue_rule": cq.QUEUE_RULE.replace("cq1.T.kkk", "rt1.T.kkk"),
        "isolation": cq.ISOLATION + " Group B adds exactly its numerical-thread variables; the probe tier adds the "
                                    "shim's variables. Every record names its environment.",
        "game_timeout_seconds": cq.GAME_TIMEOUT_SECONDS, "kill_after_seconds": cq.KILL_AFTER_SECONDS,
        "probe": {**PROBE, "source_sha256": probe_sha256},
        "process_check": dict(PROCESS_CHECK),
        "equivalence_rules": list(EQUIVALENCE), "integrity_checks": list(INTEGRITY),
        "stop_conditions": list(cq.STOP_CONDITIONS), "etiquette": dict(cq.ETIQUETTE),
        "measurements": list(MEASUREMENTS), "criteria": dict(CRITERIA), "benefit": dict(BENEFIT),
        "disposition_rule": DISPOSITION_RULE, "worker_rule": WORKER_RULE,
        "known_refusal_classes": [list(c) for c in sx.KNOWN_CLASSES],
        "expected_writable": list(cq.EXPECTED_WRITABLE),
    }


def digest(plan: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(plan)).hexdigest()


def text(plan: Mapping[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# ----------------------------------------------------------------------------------------------
# Analysis


def blas_calls(counts: Mapping[str, int], baseline: Mapping[str, int]) -> Dict[str, int]:
    """Calls beyond the import-time baseline, by entry point."""
    extra = {name: count - baseline.get(name, 0) for name, count in counts.items()}
    return {name: n for name, n in sorted(extra.items()) if n}


def worker_criteria(tier: Mapping[str, Any], base: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The concurrency qualification's worker criteria of a constrained tier against B-w01."""
    return cq.criteria_for(tier, base)


def disposition(tiers: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply the registered disposition and worker rules to tier summaries keyed by tier name."""
    checks = ("safety_pass", "independence_pass", "engine_state_pass", "ledger_pass")
    failed = sorted(name for name, t in tiers.items() if not all(t[k] for k in checks))
    if failed or "E-B" not in tiers or "B-w01" not in tiers:
        return {"disposition": "BLOCKED", "runtime": None, "workers": 16,
                "reason": f"checks failed in {failed}" if failed else "the equivalence or base tier did not run"}
    base = tiers["B-w01"]
    constrained = {name: t for name, t in tiers.items() if name.startswith("B-w") and t["workers"] >= 16}
    criteria = {name: worker_criteria(t, base) for name, t in constrained.items()}
    acceptable = {name: t for name, t in constrained.items() if all(c["pass"] for c in criteria[name].values())}
    benefits = {
        "higher_worker_count": any(t["workers"] > 16 for t in acceptable.values()),
        "throughput_gain": any(f"A-w{n}" in tiers and f"B-w{n}" in tiers and tiers[f"B-w{n}"]["throughput_games_per_hour"]
                               >= BENEFIT["throughput_gain"] * tiers[f"A-w{n}"]["throughput_games_per_hour"] for n in (16, 24)),
        "cpu_reduction": ("A-w16" in tiers and "B-w16" in tiers and tiers["B-w16"]["cpu_seconds_per_game_median"]
                          <= BENEFIT["cpu_per_game_ratio"] * tiers["A-w16"]["cpu_seconds_per_game_median"]),
    }
    if not any(benefits.values()):
        return {"disposition": "RETAIN runtime-r1", "runtime": "baseline-v1-runtime-r1", "workers": 16,
                "benefits": benefits, "criteria": criteria, "reason": "no registered benefit held"}
    if not acceptable:
        return {"disposition": f"PROMOTED AS {RUNTIME_CANDIDATE}", "runtime": RUNTIME_CANDIDATE, "workers": 16,
                "benefits": benefits, "criteria": criteria, "reason": "no constrained tier acceptable; 16 is retained"}
    best = max(criteria[name]["throughput"]["speedup"] for name in acceptable)
    chosen = min((t for name, t in acceptable.items() if criteria[name]["throughput"]["speedup"] >= CRITERIA["knee_fraction"] * best),
                 key=lambda t: t["workers"])
    return {"disposition": f"PROMOTED AS {RUNTIME_CANDIDATE}", "runtime": RUNTIME_CANDIDATE, "workers": chosen["workers"],
            "benefits": benefits, "criteria": criteria,
            "reason": f"smallest acceptable constrained tier within {CRITERIA['knee_fraction']} of the largest acceptable "
                      f"speedup ({best:.3f})"}


def thread_split(scheduling: Sequence[Mapping[str, Any]]) -> Dict[str, Optional[float]]:
    """Main thread (the first) versus every other thread: switches, migrations and CPU."""
    if not scheduling:
        return {}
    main, others = scheduling[0], list(scheduling[1:])

    def total(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
        values = [r.get(key) for r in rows]
        return None if any(v is None for v in values) else float(sum(values))

    return {"threads": len(scheduling), "main_involuntary": main.get("involuntary"), "main_voluntary": main.get("voluntary"),
            "main_migrations": main.get("migrations"), "main_cpu_seconds": main.get("cpu_seconds"),
            "other_involuntary": total(others, "involuntary"), "other_voluntary": total(others, "voluntary"),
            "other_migrations": total(others, "migrations"), "other_cpu_seconds": total(others, "cpu_seconds")}
