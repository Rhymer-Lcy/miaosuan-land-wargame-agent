"""The registered concurrency qualification ``concurrency-qualification-1``.

Question: how many engine games can run at once on the persistent installation without violating engine-state
integrity, authentication integrity, independence of games, determinism, or ledger and result accounting, and
does running them at once raise registered-game throughput? The policy is ``baseline-v2`` on
``baseline-v1-runtime-r1`` and is not changed.

This module holds the plan (tiers, workload, queue rule, game identities, isolation, checks, stop conditions,
criteria, recommendation rule, the scheduler-equivalence corpus), the serial references derived from the
shoot experiment's records, and the pure functions that evaluate records, ledger events and samples against
the plan. ``scripts/build_concurrency_plan.py`` writes the plan; ``scripts/qualify_concurrency.py`` runs it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import shoot_experiment as sx
from .manifest import canonical_bytes
from .stats import exact_rank_value

QUESTION = ("How many engine games can run at once on the persistent installation without violating engine-state "
            "integrity, authentication integrity, independence of games, determinism, or ledger and result "
            "accounting, and does running them at once raise registered-game throughput?")
SCHEMA = "miaosuan-concurrency-qualification-plan/1"
PLAN_ID = "concurrency-qualification-1"
GAME_PREFIX = "cq1"
POLICY = sx.CANDIDATE_ID
PURPOSE = "diagnostic"

#: The workload block: one configuration of each scenario. The first five were identical in all 15 serial
#: repetitions of the shoot experiment (deterministic); the last three diverge after their first shot.
BLOCK_CONFIGS = ("201033019601.C2", "2010131194.C2", "2010211129.C3", "1910631192.C2", "2010431153.C2",
                 "1930331196.C3", "2120531121.C1", "2130511121.C3")
DETERMINISTIC_EXPECTED = BLOCK_CONFIGS[:5]

TIERS = (
    {"tier": "S", "workers": 1, "session_mode": "exclusive", "blocks": 1,
     "role": "serial control: the current architecture (exclusive session lock, one game at a time)"},
    {"tier": "w01", "workers": 1, "session_mode": "shared", "blocks": 2,
     "role": "one worker through the shared-session protocol: the throughput base and the protocol control"},
    {"tier": "w02", "workers": 2, "session_mode": "shared", "blocks": 2, "role": "concurrency tier"},
    {"tier": "w04", "workers": 4, "session_mode": "shared", "blocks": 2, "role": "concurrency tier"},
    {"tier": "w08", "workers": 8, "session_mode": "shared", "blocks": 4, "role": "concurrency tier"},
    {"tier": "w16", "workers": 16, "session_mode": "shared", "blocks": 8, "role": "concurrency tier"},
)
OPTIONAL_TIERS = (
    {"tier": "w24", "workers": 24, "session_mode": "shared", "blocks": 12,
     "role": "optional: only if w16 met every criterion with parallel efficiency of at least 0.85"},
    {"tier": "w32", "workers": 32, "session_mode": "shared", "blocks": 16,
     "role": "optional: only if w24 met every criterion with parallel efficiency of at least 0.85"},
)
OPTIONAL_EFFICIENCY = 0.85
GAME_TIMEOUT_SECONDS = 2100
KILL_AFTER_SECONDS = 30

CRITERIA = {
    "material_speedup": 1.5,
    "minimum_efficiency": 0.70,
    "p99_ratio": 1.5,
    "max_ratio": 2.0,
    "maximum_our_cpus": 32.0,
    "maximum_rss_fraction": 0.10,
    "maximum_others_cpus_during": 8.0,
    "knee_fraction": 0.85,
}
ETIQUETTE = {
    "pre_tier_window_seconds": 30,
    "maximum_others_cpus_before": 16.0,
    "minimum_idle_logical_cpus": 16,
    "recheck_seconds": 300,
    "rechecks": 6,
}
EXPECTED_WRITABLE = (".session.lock", ".ledger.lock", "usage-ledger.jsonl")

QUEUE_RULE = (
    "A tier plays its blocks' games in one queue ordered longest first: by descending expected serial wall time "
    "of the configuration (the median of its 15 serial shoot-experiment games), then by the configuration's "
    "position in the block, then by block number. Game k (1-based) of tier T is cq1.T.kkk.<scenario>.<condition>. "
    "Games are dispatched in queue order to the lowest-numbered free worker; batch = (k - 1) div workers."
)
ISOLATION = (
    "Each game is one process started like scripts/run_evaluation.sh starts one: an environment holding only "
    "HOME (the installation's persistent home/, shared, as ENGINE_INSTALL.md requires), PATH, LANG=C.UTF-8, "
    "PYTHONNOUSERSITE=1, PYTHONDONTWRITEBYTECODE=1, PYTHONHASHSEED=0, CUDA_VISIBLE_DEVICES empty, PYTHONPATH "
    "(installation site/ then the repository's src/) and TMPDIR; a working directory and a TMPDIR of its own, "
    "both empty and checked empty afterwards; a new session (process group); output to its own log; the "
    "harness seeds Python's and NumPy's global generators as the registered evaluations do. All games share "
    "the one persistent installation and its existing authentication state; nothing is copied, reset, "
    "restored or regenerated."
)
SAFETY_CHECKS = (
    "every planned game started once, exited 0, and left exactly one record, one log and one started marker",
    "no record, log or marker path collided (created with exclusive creation; an existing path refuses the game)",
    "the ledger parses; the tier's sessions are numbered consecutively after the last session before the tier, "
    "each has exactly one session-open and one session-close, none was recovered, and no session is unclosed",
    "each session-open names the game of the record that cites it, with the tier's session mode and worker",
    "the engine state file's SHA-256, size, mtime and ctime are unchanged across the tier, and every ledger "
    "record of the tier carries that hash",
    "package integrity holds with no added file, and home/ is unchanged",
    "each game's working directory and TMPDIR are empty after it",
    "no game shows a contract error, project-gate rejection or replay mismatch",
    "every factual refusal class is a known baseline-v2 class (the shoot experiment's four)",
    "no process remained in a game's process group after it exited, and every exit status was captured",
    "no game process held a writable file outside its record, its log and the installation's lock and ledger "
    "files, and none opened an internet socket",
)
INDEPENDENCE = (
    "Deterministic configurations: the state chain and every seat's trace chain equal the serial reference "
    "(identical in all 15 serial repetitions).",
    "Stochastic configurations: the state digests and every seat's trace digests up to the serial common "
    "prefix (the earliest step at which any two serial repetitions differ) equal the serial prefix.",
    "No two games of one stochastic configuration in a tier have the same state chain, and none equals a serial "
    "repetition's state chain: identical stochastic trajectories would mean the engine's randomness is shared "
    "or derived from the start time, so concurrent games would not be independent.",
)
STOP_CONDITIONS = (
    "Any failed safety or independence check stops the qualification after the tier: no higher tier runs, "
    "nothing is repaired, and the tier is reported as found.",
    "Any change of the engine state file, any refused session, or any ledger anomaly is an authentication or "
    "engine-state anomaly and stops at once (running games of the tier finish; none is started).",
    "Before each tier the host is sampled for 30 s with none of our games running. The tier starts only if "
    "other activity uses at most 16 logical CPUs and at least 16 logical CPUs stay idle after adding the "
    "tier's workers; otherwise it rechecks every 300 s up to 6 times and then pauses the qualification.",
    "A tier during which other activity averaged more than 8 logical CPUs is reported as contended; it is "
    "repeated once under a new attempt name, and both attempts are kept.",
)
RECOMMENDATION_RULE = (
    "A tier is acceptable when it and every lower tier passed every safety and independence check, the "
    "engine state and ledger checks passed, speedup >= 1.5, parallel efficiency >= 0.70, decision-latency "
    "p99 <= 1.5 x w01's and maximum <= 2 x w01's, our mean CPU use <= 32 logical CPUs and our peak resident "
    "memory <= 10% of host memory. Recommend the smallest acceptable worker count whose speedup is at least "
    "0.85 of the largest speedup among acceptable tiers (the throughput knee): RECOMMEND N WORKERS. If every "
    "check passed but no tier of two or more workers is acceptable: RETAIN SERIAL EXECUTION. If any safety, "
    "independence, engine-state or ledger check failed: CONCURRENCY BLOCKED PENDING MORE EVIDENCE."
)
MEASUREMENTS = (
    "throughput = games / tier makespan (first launch to last exit); speedup(N) = throughput(N) / throughput(w01); "
    "parallel efficiency(N) = speedup(N) / N",
    "per game (from wait4): CPU user and system seconds, peak resident set, voluntary and involuntary context "
    "switches, block input and output; process wall time; the record's in-game wall time",
    "per game (self-report at the end): CPU seconds per thread, peak resident set, I/O counters, GC collection "
    "counts per generation, mapped GPU, OpenMP and OpenBLAS libraries, open descriptors",
    "every second: host CPU time (busy/total), load average, running processes, context switches, available "
    "memory, and per running game CPU time, threads, resident set and context switches; descriptors every 5 s; "
    "GPU utilisation every 10 s, reduced to per-GPU utilisation and whether any of our processes uses a GPU",
    "decision latency of the policy seats: p50, p95, p99, maximum, decisions over 100 ms, 400 ms and 1 s",
)


def tier_spec(plan: Mapping[str, Any], tier: str) -> Dict[str, Any]:
    for spec in list(plan["tiers"]) + list(plan["optional_tiers"]):
        if spec["tier"] == tier:
            return dict(spec)
    raise KeyError(f"unknown tier {tier!r}")


def tier_queue(plan: Mapping[str, Any], tier: str) -> List[Dict[str, Any]]:
    """The tier's games in dispatch order (longest expected first)."""
    spec = tier_spec(plan, tier)
    block = {entry["config"]: entry for entry in plan["block"]}
    order = [entry["config"] for entry in plan["block"]]
    items = [(b, c) for b in range(spec["blocks"]) for c in order]
    items.sort(key=lambda item: (-block[item[1]]["expected_wall_seconds"], order.index(item[1]), item[0]))
    queue = []
    for k, (b, config) in enumerate(items, start=1):
        entry = block[config]
        queue.append({"seq": k, "game_id": f"{GAME_PREFIX}.{tier}.{k:03d}.{config}", "config": config, "block": b,
                      "scenario_id": entry["scenario_id"], "condition": entry["condition"],
                      "red": entry["red"], "blue": entry["blue"]})
    return queue


# ----------------------------------------------------------------------------------------------
# Serial references


def first_divergence(a: Sequence[str], b: Sequence[str]) -> Optional[int]:
    """The first index at which two digest sequences differ (or the shorter length), None if equal."""
    for k, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return k
    return None if len(a) == len(b) else min(len(a), len(b))


def _sequence_digest(values: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("ascii")).hexdigest()


def _seat_traces(record: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(seat["seat"]): seat for seat in record.get("seats", [])}


def common_prefix(sequences: Sequence[Sequence[str]]) -> int:
    """Length of the prefix shared by every sequence."""
    length = min(len(s) for s in sequences)
    for s in sequences[1:]:
        k = first_divergence(sequences[0], s)
        if k is not None:
            length = min(length, k)
    return length


def reference(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Digests of what every serial repetition of a configuration shares, and its chains."""
    chains = sorted({r["state_chain"] for r in records})
    states = [r["state_steps"] for r in records]
    prefix = common_prefix(states)
    deterministic = len(chains) == 1 and len({len(s) for s in states}) == 1
    seats: Dict[str, Dict[str, Any]] = {}
    for seat in _seat_traces(records[0]):
        traces = [_seat_traces(r)[seat]["trace_steps"] for r in records]
        length = common_prefix(traces)
        seats[seat] = {"trace_prefix_steps": length, "trace_prefix_digest": _sequence_digest(traces[0][:length]),
                       "trace_chains": sorted({_seat_traces(r)[seat]["trace_chain"] for r in records})}
    walls = sorted(r["timings_seconds"]["wall"] for r in records)
    return {"repetitions": len(records), "class": "deterministic" if deterministic else "stochastic",
            "state_steps": len(states[0]), "state_prefix_steps": prefix,
            "state_prefix_digest": _sequence_digest(states[0][:prefix]), "state_chains": chains, "seats": seats,
            "expected_wall_seconds": round(walls[(len(walls) - 1) // 2], 3)}


def compare(record: Mapping[str, Any], ref: Mapping[str, Any]) -> Dict[str, Any]:
    """Independence evidence of one game against its configuration's serial reference."""
    prefix = ref["state_prefix_steps"]
    states_ok = _sequence_digest(record["state_steps"][:prefix]) == ref["state_prefix_digest"]
    seats = _seat_traces(record)
    traces_ok = set(seats) == set(ref["seats"]) and all(
        _sequence_digest(seats[s]["trace_steps"][:r["trace_prefix_steps"]]) == r["trace_prefix_digest"]
        for s, r in ref["seats"].items())
    result = {"class": ref["class"], "prefix_steps": prefix, "state_prefix_equal": states_ok,
              "trace_prefix_equal": traces_ok, "matches_a_serial_chain": record["state_chain"] in ref["state_chains"]}
    if ref["class"] == "deterministic":
        result["identical"] = (result["matches_a_serial_chain"] and len(record["state_steps"]) == ref["state_steps"]
                               and all(seats[s]["trace_chain"] in r["trace_chains"] for s, r in ref["seats"].items()))
        result["pass"] = states_ok and traces_ok and result["identical"]
    else:
        result["pass"] = states_ok and traces_ok and not result["matches_a_serial_chain"]
    return result


def duplicate_chains(records: Iterable[Mapping[str, Any]], classes: Mapping[str, str]) -> List[List[str]]:
    """Groups of games of one stochastic configuration that share a state chain."""
    seen: Dict[Tuple[str, str], List[str]] = {}
    for record in records:
        config = f"{record['scenario_id']}.{record['condition']}"
        if classes.get(config) == "stochastic":
            seen.setdefault((config, record["state_chain"]), []).append(record["game_id"])
    return sorted(sorted(games) for games in seen.values() if len(games) > 1)


# ----------------------------------------------------------------------------------------------
# The plan


def equivalence_corpus(manifest: Mapping[str, Any]) -> List[str]:
    """Groups B and C, repetition 1, of the block's configurations, in the shoot experiment's schedule order."""
    wanted = {f"{c}.{g}.r1" for c in BLOCK_CONFIGS for g in sx.GROUPS}
    return [entry["game_id"] for entry in manifest["schedule"] if entry["game_id"] in wanted]


def build(manifest: Mapping[str, Any], manifest_sha256: str, references: Mapping[str, Mapping[str, Mapping[str, Any]]],
          policy_source: Mapping[str, Any], golden_trace_chain: str) -> Dict[str, Any]:
    """The plan. ``references[group][config]`` come from the shoot experiment's serial records."""
    conditions = manifest["groups"]["C"]["conditions"]
    block = []
    for config in BLOCK_CONFIGS:
        scenario, condition = config.split(".")
        ref = references["C"][config]
        block.append({"config": config, "scenario_id": scenario, "condition": condition,
                      "red": conditions[condition]["red"], "blue": conditions[condition]["blue"],
                      "expected_wall_seconds": ref["expected_wall_seconds"], "reference": dict(ref)})
    classes = [entry["reference"]["class"] for entry in block]
    if classes != ["deterministic"] * 5 + ["stochastic"] * 3:
        raise ValueError(f"the block's determinism classes changed: {classes}")
    corpus = equivalence_corpus(manifest)
    return {
        "schema": SCHEMA, "plan_id": PLAN_ID, "purpose": PURPOSE,
        "question": QUESTION,
        "policy": {"identity": "baseline-v2", "code_identity": POLICY, "runtime": "baseline-v1-runtime-r1",
                   "policy_source": dict(policy_source), "golden_trace_chain": golden_trace_chain},
        "inputs": {"experiment": sx.EXPERIMENT_NAME, "manifest_sha256": manifest_sha256,
                   "scenarios": [dict(s) for s in manifest["scenarios"]], "players": [dict(p) for p in manifest["players"]],
                   "randomness": dict(manifest["randomness"]), "engine": dict(manifest["engine"])},
        "block": block,
        "tiers": [dict(t) for t in TIERS],
        "optional_tiers": [dict(t) for t in OPTIONAL_TIERS],
        "optional_efficiency": OPTIONAL_EFFICIENCY,
        "queue_rule": QUEUE_RULE,
        "isolation": ISOLATION,
        "game_timeout_seconds": GAME_TIMEOUT_SECONDS,
        "kill_after_seconds": KILL_AFTER_SECONDS,
        "safety_checks": list(SAFETY_CHECKS),
        "independence": list(INDEPENDENCE),
        "stop_conditions": list(STOP_CONDITIONS),
        "etiquette": dict(ETIQUETTE),
        "measurements": list(MEASUREMENTS),
        "criteria": dict(CRITERIA),
        "recommendation_rule": RECOMMENDATION_RULE,
        "known_refusal_classes": [list(c) for c in sx.KNOWN_CLASSES],
        "expected_writable": list(EXPECTED_WRITABLE),
        "equivalence": {
            "corpus": corpus,
            "references": {gid: dict(references[gid.split(".")[2]][".".join(gid.split(".")[:2])]) for gid in corpus},
            "runs": [{"run": "serial", "workers": 1, "path": "the existing serial loop of scripts/run_evaluation.sh"},
                     {"run": "parallel", "workers": "the recommended worker count",
                      "path": "scripts/run_evaluation.sh --workers N (the production scheduler)"}],
            "criteria": ["both runs record exactly the 16 planned game identities, each once, all completed",
                         "each record carries its group's registered policy digest and the experiment manifest digest",
                         "every game passes the independence comparison with its configuration and group's serial "
                         "reference, and deterministic games are identical between the two runs",
                         "the ledger shows one open and one close per game, no recovery, no unclosed session, and an "
                         "unchanged engine state", "no game was rerun and no record overwritten"],
            "condition": "run only if a worker count is recommended and the production scheduler is added",
        },
        "gpu": ("The games run with CUDA_VISIBLE_DEVICES empty; the qualification records whether any game maps a "
                "GPU library or appears as a GPU compute process. No GPU work is added."),
    }


def digest(plan: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(plan)).hexdigest()


# ----------------------------------------------------------------------------------------------
# Checks on one tier


def game_facts(record: Mapping[str, Any], policy: str = POLICY) -> Dict[str, Any]:
    metrics = sx.game_metrics(record, policy)
    values = metrics["values"]
    return {"status": record.get("status"), "contract_errors": values["contract_errors"],
            "gate_rejections": values["gate_rejections"], "replay_mismatches": values["replay_mismatches"],
            "classes": sorted((f["action_type"], f["code"], f["message_class"]) for f in metrics["facts"])}


def ledger_check(events: Sequence[Mapping[str, Any]], last_before: int, records: Mapping[str, Mapping[str, Any]],
                 session_mode: str, state_hash: Mapping[str, Optional[str]]) -> Dict[str, Any]:
    """The tier's ledger events (those appended during the tier) against its records."""
    opens = [e for e in events if e.get("event") == "session-open"]
    closes = [e for e in events if e.get("event") == "session-close"]
    recovered = [e for e in events if e.get("event") == "session-recovered"]
    numbers = [int(e["session"]) for e in opens]
    by_session = {e["session"]: e for e in opens}
    problems = []
    if sorted(numbers) != list(range(last_before + 1, last_before + 1 + len(records))):
        problems.append(f"session numbers {sorted(numbers)} are not {last_before + 1}..{last_before + len(records)}")
    if len(numbers) != len(set(numbers)):
        problems.append("a session number was allocated twice")
    if sorted(e["session"] for e in closes) != sorted(by_session):
        problems.append("opens and closes do not pair one to one")
    if recovered:
        problems.append(f"recovered sessions {[e['session'] for e in recovered]}")
    other = [e for e in events if e.get("event") not in ("session-open", "session-close")]
    if [e for e in other if e not in recovered]:
        problems.append("unknown ledger events")
    for game, record in records.items():
        opened = by_session.get(record.get("session"))
        if opened is None or opened["harness"].get("game_id") != game:
            problems.append(f"{game}: no session-open names it")
            continue
        mode = opened.get("concurrency", {}).get("mode", "exclusive")
        if mode != session_mode:
            problems.append(f"{game}: session mode {mode}, expected {session_mode}")
    for e in events:
        if e.get("state") != state_hash:
            problems.append(f"session {e.get('session')}: state hash differs from the tier's")
        if e.get("event") == "session-close" and (e.get("state_changed") or e.get("home_changed")
                                                   or not e.get("integrity", {}).get("ok")):
            problems.append(f"session {e['session']}: state, home or integrity changed")
    return {"pass": not problems, "problems": problems, "sessions": len(numbers),
            "first": min(numbers) if numbers else None, "last": max(numbers) if numbers else None}


def percentiles(values: Sequence[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "max": None}
    return {"p50": exact_rank_value(values, 50), "p95": exact_rank_value(values, 95),
            "p99": exact_rank_value(values, 99), "max": max(values)}


def latency_summary(records: Iterable[Mapping[str, Any]], policy: str = POLICY) -> Dict[str, Any]:
    values = [v for r in records for s in r.get("seats", []) if s["policy"] == policy for v in s["latency_us"]]
    ms = [v / 1000.0 for v in values]
    return {"decisions": len(ms), **{f"{k}_ms": (round(v, 3) if v is not None else None)
                                     for k, v in percentiles(ms).items()},
            "over_100ms": sum(1 for v in ms if v > 100), "over_400ms": sum(1 for v in ms if v > 400),
            "over_1000ms": sum(1 for v in ms if v > 1000)}


def criteria_for(tier: Mapping[str, Any], base: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The preregistered engineering criteria of one tier against the w01 base."""
    c = CRITERIA
    speedup = tier["throughput_games_per_hour"] / base["throughput_games_per_hour"]
    efficiency = speedup / tier["workers"]
    p99_ratio = tier["latency"]["p99_ms"] / base["latency"]["p99_ms"]
    max_ratio = tier["latency"]["max_ms"] / base["latency"]["max_ms"]
    return {
        "safety": {"pass": tier["safety_pass"]},
        "independence": {"pass": tier["independence_pass"]},
        "engine_state": {"pass": tier["engine_state_pass"]},
        "ledger": {"pass": tier["ledger_pass"]},
        "throughput": {"pass": speedup >= c["material_speedup"], "speedup": speedup},
        "efficiency": {"pass": efficiency >= c["minimum_efficiency"], "efficiency": efficiency},
        "latency": {"pass": p99_ratio <= c["p99_ratio"] and max_ratio <= c["max_ratio"],
                    "p99_ratio": p99_ratio, "max_ratio": max_ratio},
        "headroom": {"pass": tier["our_cpus_mean"] <= c["maximum_our_cpus"]
                     and tier["peak_rss_fraction"] <= c["maximum_rss_fraction"],
                     "our_cpus_mean": tier["our_cpus_mean"], "peak_rss_fraction": tier["peak_rss_fraction"]},
    }


def recommend(tiers: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply the recommendation rule to tier summaries in tier order (w01 first among the shared tiers)."""
    integrity = ("safety", "independence", "engine_state", "ledger")
    if any(not t["criteria"][k]["pass"] for t in tiers for k in integrity if k in t["criteria"]) or any(
            not (t["safety_pass"] and t["independence_pass"] and t["engine_state_pass"] and t["ledger_pass"])
            for t in tiers):
        return {"disposition": "CONCURRENCY BLOCKED PENDING MORE EVIDENCE", "workers": None,
                "reason": "a safety, independence, engine-state or ledger check failed"}
    acceptable = [t for t in tiers if t["workers"] >= 2 and all(v["pass"] for v in t["criteria"].values())]
    if not acceptable:
        return {"disposition": "RETAIN SERIAL EXECUTION", "workers": 1,
                "reason": "every check passed, but no tier of two or more workers met the engineering criteria"}
    best = max(t["criteria"]["throughput"]["speedup"] for t in acceptable)
    chosen = min((t for t in acceptable if t["criteria"]["throughput"]["speedup"] >= CRITERIA["knee_fraction"] * best),
                 key=lambda t: t["workers"])
    return {"disposition": f"RECOMMEND {chosen['workers']} WORKERS", "workers": chosen["workers"],
            "reason": f"smallest acceptable tier within {CRITERIA['knee_fraction']} of the largest acceptable "
                      f"speedup ({best:.3f})"}


def text(plan: Mapping[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
