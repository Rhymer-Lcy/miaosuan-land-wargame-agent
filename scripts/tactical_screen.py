"""Analysis of a registered exploratory tactical screen.

    PYTHON scripts/tactical_screen.py --screen ID smoke [--check]     the mechanism smoke (diagnostic run, step captures)
    PYTHON scripts/tactical_screen.py --screen ID analyze [--check]   the exploratory A/B

``smoke`` reads the smoke games' records and step captures (``local/evaluation/<screen>-smoke``) and applies the
registered pass rule; ``analyze`` reads the A/B records (``local/evaluation/<screen>``), checks integrity first, and
reports head-to-head and vs-inert margins, score components, mechanism and safety metrics, and the registered
exploratory disposition. Public outputs hold counts, scores and game labels only; ``--check`` rebuilds and compares.
EXPLORATORY: nothing here can promote a baseline.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install as ei  # noqa: E402
from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import tactical_screen as ts  # noqa: E402
from miaosuan_agent.evaluation.execution import RUNTIMES  # noqa: E402

INSTALL = REPO_ROOT / "local" / "engines" / "sdk-4.1.0"
DEPLOY_SPLIT = "314"
SPLIT_TYPES = (314, 14)  # as emitted, and as the engine rewrites it in place during the step
END_DEPLOYMENT = 333
BOOTSTRAP = 2000
SEED = 20261002


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def hist(values: Any) -> Dict[str, int]:
    return {str(k): v for k, v in sorted(collections.Counter(values).items(), key=lambda kv: str(kv[0]))}


def seat_of(record: Mapping[str, Any], faction: int) -> Mapping[str, Any]:
    return next(s for s in record["seats"] if s["faction"] == faction)


# ----------------------------------------------------------------------------------------------
# mechanism smoke


def fresh_feedback(steps: List[Mapping[str, Any]]) -> List[List[Mapping[str, Any]]]:
    """Each step's feedback entries not reported before: while the engine clock stands still (deployment), its
    feedback list accumulates, so a step first repeats the entries already reported at the same ``cur_step``."""
    out: List[List[Mapping[str, Any]]] = []
    previous: List[Mapping[str, Any]] = []
    clock = None
    for step in steps:
        entries = list(step["feedback"])
        repeated = step.get("cur_step") == clock and entries[:len(previous)] == previous
        out.append(entries[len(previous):] if repeated else entries)
        previous, clock = entries, step.get("cur_step")
    return out


def smoke_game(manifest: Mapping[str, Any], record: Mapping[str, Any], capture: Mapping[str, Any]) -> Dict[str, Any]:
    """One smoke game's facts. The engine rewrites a deployment split's type from 314 to 14 in place and the capture
    serialises the batch after the engine step, so a captured deployment split carries either type; the record counts
    the policy's own actions before the step, and the two counts must agree."""
    candidate = manifest["candidate"]
    seat = seat_of(record, 0)
    steps = capture["steps"]
    news = fresh_feedback(steps)
    deployment = [k for k, s in enumerate(steps) if s.get("stage") == 1]
    splits = [(k, i) for k in deployment for i in steps[k]["batch"]
              if i["seat"] == seat["seat"] and i["action"].get("type") in SPLIT_TYPES]
    emitted = seat["actions_by_type"].get(DEPLOY_SPLIT, 0)
    if len(splits) != emitted:
        raise SystemExit(f"REFUSED: {record['game_id']}: {len(splits)} captured deployment splits but the record "
                         f"counts {emitted} emitted; the capture is not being read correctly")
    errors, outcomes, blood_changes = collections.Counter(), collections.Counter(), collections.Counter()
    for k, item in splits:
        unit = item["action"]["obj_id"]
        refused = [e for e in news[k] if isinstance(e.get("error"), Mapping)
                   and (e.get("message") or {}).get("obj_id") == unit
                   and (e.get("message") or {}).get("type") in SPLIT_TYPES]
        diff = steps[k]["changed"].get(str(unit), {})
        if "blood" in diff:
            outcomes["took effect"] += 1
            blood_changes[f"{diff['blood'][0]}->{diff['blood'][1]}"] += 1
        elif refused:
            outcomes["refused"] += 1
            errors[str(refused[0]["error"].get("code"))] += 1
        else:
            outcomes["no effect, no error"] += 1
    appeared = {u for k in deployment for u in steps[k]["appeared"]}
    play = [k for k, s in enumerate(steps) if s.get("stage") != 1]
    commanded = {i["action"].get("obj_id") for k in play for i in steps[k]["batch"] if i["seat"] == seat["seat"]} & appeared
    refused_orders = sum(1 for k in play for e in news[k]
                         if isinstance(e.get("error"), Mapping) and (e.get("message") or {}).get("obj_id") in appeared)
    ended = any(i["action"].get("type") == END_DEPLOYMENT and i["seat"] == seat["seat"] for s in steps for i in s["batch"])
    setup = next(s for s in capture["setup"]["seats"] if s["seat"] == seat["seat"])
    return {"game": record["game_id"], "status": record["status"], "policy": record["policies"]["red"] == candidate,
            "deployment_steps": len(deployment), "splits_emitted": len(splits),
            "split_outcomes": dict(sorted(outcomes.items())), "split_errors_by_code": dict(sorted(errors.items())),
            "operators_appearing_in_deployment": len(appeared), "appearing_operators_commanded": len(commanded),
            "refused_orders_to_appearing_operators": refused_orders,
            "split_blood_changes": dict(sorted(blood_changes.items())),
            "operators_at_setup": setup["operators"], "controllable_operators_seen": seat["units_seen"],
            "operators_that_acted": seat["units_acted"], "deployment_ended": ended,
            "contract_errors": seat["contract_errors"], "gate_rejections": sum(seat["gate_rejections"].values())}


def smoke(screen: str) -> Dict[str, Any]:
    manifest = load(REPO_ROOT / "evaluation" / screen / "manifest.json")
    work = REPO_ROOT / "local" / "evaluation" / f"{screen}-smoke"
    games = []
    for entry in manifest["smoke_games"]:
        record = load(work / "games" / f"{entry['game_id']}.json")
        capture = load(work / "capture" / f"{entry['game_id']}.capture.json")
        games.append(smoke_game(manifest, record, capture))
    took_effect = [g for g in games if g["splits_emitted"] and g["operators_appearing_in_deployment"]]
    commanded = [g for g in took_effect if g["appearing_operators_commanded"]]
    healthy = all(g["status"] == "COMPLETED" and not g["contract_errors"] and g["deployment_ended"] for g in games)
    verdict = ts.smoke_verdict(games)
    return {"schema": "miaosuan-tactical-smoke/1", "screen_id": screen, "manifest_sha256": mf.digest(manifest),
            "games": games, "games_where_splits_took_effect": len(took_effect),
            "games_where_new_operators_were_commanded": len(commanded), "all_games_healthy": healthy, "verdict": verdict}


# ----------------------------------------------------------------------------------------------
# exploratory A/B


def integrity(manifest: Mapping[str, Any], records: Mapping[str, Dict[str, Any]], work: Path) -> Dict[str, Any]:
    problems: List[str] = []
    games = [g["game_id"] for g in manifest["games"]]
    if sorted(records) != sorted(games):
        problems.append(f"records for {len(records)} of {len(games)} registered games")
    queues = sorted((work / "logs").glob("queue-*.txt")) if (work / "logs").exists() else []
    if len(queues) != 1 or queues[0].read_text(encoding="utf-8").split() != games:
        problems.append("the dispatch queue is not exactly the registered order")
    execution = manifest["execution"]
    env = dict(RUNTIMES[execution["runtime"]])
    digest = mf.digest(manifest)
    pins = {p: v["policy_source"]["sha256"] for p, v in manifest["policies"].items()}
    ledger = ei.read_ledger(ei.EngineInstall(INSTALL.resolve()))
    events: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for event in ledger:
        events.setdefault(event["session"], {}).setdefault(event["event"], []).append(event)
    for game, record in sorted(records.items()):
        h = record["harness"]
        if h["manifest_sha256"] != digest or h.get("dirty"):
            problems.append(f"{game}: manifest digest or dirty harness")
        if any(pins[p] != d for p, d in (h.get("policy_sources") or {}).items()) or not h.get("policy_sources"):
            problems.append(f"{game}: policy sources {h.get('policy_sources')}")
        if (h.get("runtime"), h.get("thread_env")) != (execution["runtime"], env):
            problems.append(f"{game}: runtime")
        run = h.get("execution") or {}
        if (run.get("mode"), run.get("workers"), run.get("scheduler")) != ("shared", execution["workers"], execution["scheduler"]):
            problems.append(f"{game}: execution {run}")
        session = events.get(record["session"], {})
        if len(session.get("session-open", [])) != 1 or len(session.get("session-close", [])) != 1:
            problems.append(f"{game}: session not opened and closed exactly once")
        elif session["session-close"][0].get("state_changed") or not session["session-close"][0]["integrity"]["ok"]:
            problems.append(f"{game}: state or integrity changed")
    sessions = sorted(int(r["session"]) for r in records.values())
    if sessions and sessions != list(range(sessions[0], sessions[0] + len(sessions))):
        problems.append("sessions are not consecutive")
    return {"pass": not problems, "problems": problems, "records": len(records),
            "sessions": [sessions[0], sessions[-1]] if sessions else None}


def latency(values: List[int]) -> Dict[str, float]:
    ordered = sorted(values)
    return {"p50_ms": round(ordered[len(ordered) // 2] / 1000, 3), "p95_ms": round(ordered[int(len(ordered) * 0.95)] / 1000, 3),
            "max_ms": round(ordered[-1] / 1000, 3)} if ordered else {}


def bootstrap_mean(groups: List[List[float]]) -> List[float]:
    """Percentile 95% interval of the pooled mean, resampling scenarios (with their games) as clusters."""
    rng = random.Random(SEED)
    means = []
    for _ in range(BOOTSTRAP):
        sample = [g for g in (rng.choice(groups) for _ in groups)]
        values = [v for g in sample for v in g]
        means.append(sum(values) / len(values))
    means.sort()
    return [round(means[int(0.025 * BOOTSTRAP)], 2), round(means[int(0.975 * BOOTSTRAP) - 1], 2)]


def analyse(screen: str) -> Dict[str, Any]:
    manifest = load(REPO_ROOT / "evaluation" / screen / "manifest.json")
    work = REPO_ROOT / "local" / "evaluation" / screen
    records = {g["game_id"]: load(work / "games" / f"{g['game_id']}.json") for g in manifest["games"]
               if (work / "games" / f"{g['game_id']}.json").exists()}
    integ = integrity(manifest, records, work)
    candidate = manifest["candidate"]
    out: Dict[str, Any] = {"schema": "miaosuan-tactical-screen-results/1", "screen_id": screen,
                           "status": "EXPLORATORY - NOT ELIGIBLE FOR BASELINE PROMOTION",
                           "manifest_sha256": mf.digest(manifest), "integrity": integ}
    if not integ["pass"]:
        out["disposition"] = None
        return out
    by = {g["game_id"]: g for g in manifest["games"]}
    scenarios = [s["scenario_id"] for s in manifest["scenarios"]]
    failed = sorted(g for g, r in records.items() if r["status"] != "COMPLETED")
    failed_candidate = [g for g in failed if candidate in (by[g]["red"], by[g]["blue"])]
    records = {g: r for g, r in records.items() if g not in failed}
    h2h: Dict[str, List[float]] = collections.defaultdict(list)
    wdl = collections.Counter()
    components: Dict[str, Dict[str, List[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    active: Dict[str, Dict[str, List[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    mirror: Dict[str, List[float]] = collections.defaultdict(list)
    seen: Dict[str, Dict[str, List[int]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    splits: List[int] = []
    safety: Dict[str, collections.Counter] = {"b": collections.Counter(), "c": collections.Counter()}
    refusal_classes: Dict[str, collections.Counter] = {"b": collections.Counter(), "c": collections.Counter()}
    refusal_seat_games: Dict[str, collections.Counter] = {"b": collections.Counter(), "c": collections.Counter()}
    lat: Dict[str, List[int]] = {"b": [], "c": []}
    for game, record in sorted(records.items()):
        g, scores = by[game], record["final_scores"]
        total = {"red": scores["red_total"], "blue": scores["blue_total"]}
        for seat in record["seats"]:
            policy = seat["policy"]
            if policy == INERT_ID:
                continue
            arm = "c" if policy == candidate else "b"
            safety[arm]["policy seat-games"] += 1
            safety[arm]["contract errors"] += seat["contract_errors"]
            safety[arm]["gate rejections"] += sum(seat["gate_rejections"].values())
            safety[arm]["duplicate same-target shots"] += seat["duplicate_shoot_target_commands"]
            safety[arm]["replay mismatches"] += seat["replay_mismatches"]
            for key, n in seat["feedback_errors_by_code_and_type"].items():
                refusal_classes[arm][key] += n
                refusal_seat_games[arm][key] += 1
                if key.startswith("1804/"):
                    safety[arm]["code 1804"] += n
            lat[arm].extend(seat["latency_us"])
            if policy == candidate:
                splits.append(seat["actions_by_type"].get(DEPLOY_SPLIT, 0))
            if g["arm"] is not None:
                colour = "red" if seat["faction"] == 0 else "blue"
                seen[f"{g['scenario_id']}.{g['condition']}.{colour}"][g["arm"]].append(seat["units_seen"])
        if g["condition"] in ts.HEAD_TO_HEAD:
            mine = "red" if g["condition"] == "H1" else "blue"
            other = "blue" if mine == "red" else "red"
            margin = total[mine] - total[other]
            h2h[g["scenario_id"]].append(margin)
            wdl["win" if margin > 0 else "loss" if margin < 0 else "draw"] += 1
            for part in ("occupy", "attack", "remain"):
                components["head_to_head_candidate_minus_opponent"][part].append(scores[f"{mine}_{part}"] - scores[f"{other}_{part}"])
        elif g["condition"] in ("C2", "C3"):
            mine = "red" if g["condition"] == "C2" else "blue"
            other = "blue" if mine == "red" else "red"
            active[f"{g['scenario_id']}.{g['condition']}"][g["arm"]].append(total[mine] - total[other])
            for part in ("occupy", "attack", "remain"):
                components[f"vs_inert_{g['arm']}"][part].append(scores[f"{mine}_{part}"])
        else:
            mirror[f"{g['scenario_id']}.{g['arm']}"].append(total["red"] - total["blue"])
    per_scenario = {s: round(statistics.mean(h2h[s]), 2) for s in scenarios if h2h[s]}
    pooled = [v for s in scenarios for v in h2h[s]]
    differences = {c: round(statistics.mean(v["c"]) - statistics.mean(v["b"]), 2) for c, v in sorted(active.items())
                   if v["c"] and v["b"]}
    cells = {c: {"baseline": round(statistics.mean(v["b"]), 2), "candidate": round(statistics.mean(v["c"]), 2)}
             for c, v in sorted(seen.items()) if v["b"] and v["c"]}
    activated = sum(1 for v in cells.values() if v["candidate"] > v["baseline"])
    new_classes = sorted(set(refusal_classes["c"]) - set(refusal_classes["b"]))
    catastrophic = bool(failed_candidate) or safety["c"]["contract errors"] > 0 or safety["c"]["gate rejections"] > 0
    pooled_mean = round(statistics.mean(pooled), 2)
    positive = sum(1 for v in per_scenario.values() if v > 0)
    negative = sum(1 for v in per_scenario.values() if v < 0)
    inert_ok = sum(1 for v in differences.values() if v >= 0)
    disposition = ts.exploratory_disposition(catastrophic, pooled_mean, positive, negative, activated, len(cells),
                                             inert_ok, len(scenarios), len(differences))
    out.update({
        "failed_games": {"total": len(failed), "involving_the_candidate": len(failed_candidate)},
        "head_to_head": {"games": len(pooled), "per_scenario_mean_margin": per_scenario, "pooled_mean_margin": pooled_mean,
                         "pooled_mean_95_scenario_bootstrap": bootstrap_mean([h2h[s] for s in scenarios if h2h[s]]),
                         "scenarios_positive": positive, "scenarios_negative": negative,
                         "wins_draws_losses": {k: wdl[k] for k in ("win", "draw", "loss")},
                         "range_per_scenario": [min(per_scenario.values()), max(per_scenario.values())]},
        "vs_inert": {"configurations": len(differences), "candidate_minus_baseline_active_margin": differences,
                     "configurations_not_worse": inert_ok, "configurations_better": sum(1 for v in differences.values() if v > 0),
                     "configurations_worse": sum(1 for v in differences.values() if v < 0)},
        "mirror_margin_means": {k: round(statistics.mean(v), 2) for k, v in sorted(mirror.items())},
        "components": {k: {p: round(statistics.mean(v), 2) for p, v in parts.items()} for k, parts in sorted(components.items())},
        "mechanism": {"candidate_seat_games": len(splits), "deployment_splits_per_candidate_seat": hist(splits),
                      "controllable_operators_seen": cells, "cells_with_more_operators": activated, "cells": len(cells)},
        "safety": {arm: dict(sorted(c.items())) for arm, c in safety.items()},
        "refusal_classes": {arm: dict(sorted(c.items())) for arm, c in refusal_classes.items()},
        "refusal_class_seat_games": {arm: dict(sorted(c.items())) for arm, c in refusal_seat_games.items()},
        "refusal_counting_note": ("refusal counts are as the harness records them: while the engine clock stands "
                                  "still (deployment) the engine re-reports earlier feedback at every step, so a "
                                  "deployment refusal is counted once per step until play starts; seat-games per "
                                  "class are not affected"),
        "refusal_classes_new_in_candidate": new_classes,
        "latency": {arm: latency(v) for arm, v in lat.items()},
        "disposition": disposition,
    })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--screen", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("smoke", "analyze"):
        command = sub.add_parser(name)
        command.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = smoke(args.screen) if args.command == "smoke" else analyse(args.screen)
    out = REPO_ROOT / "evaluation" / args.screen / ("smoke.json" if args.command == "smoke" else "results.json")
    content = text(result)
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == content
        print(f"{args.command} identical" if same else "MISMATCH")
        return 0 if same else 1
    out.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()}: {result.get('verdict') or result.get('disposition')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
