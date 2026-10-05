"""Sprint 11 offline replay of ``t9-batch-capacity-v3`` on the frozen Sprint 10 full-step captures (server only).

    python scripts/t9_batch_replay.py [--check] [--every N]

Reads the six private diagnostic captures under ``local/evaluation/`` (pinned by SHA-256 below), applies baseline-v2
(as captured), T9-v1 (as captured), frozen T9-v2 and every design variant of the batch allocator to each captured
decision of the diagnosed seat, and writes

* ``evaluation/s11-batch-allocator/replay.json``: aggregates and the 2120531121 C3 allocation certificate, with no
  unit id, hex or raw observation;
* ``local/diagnostics/s11/replay-private.json``: the same plus per-decision identifiers (ignored by git).

``--check`` regenerates both in memory and compares the public file byte for byte. One step only: no game outcome is
simulated. Faithfulness is checked, not assumed: baseline-v2 is re-decided from the captured memory on a sample of
decisions and must equal the captured actions, the candidate policy class must equal the pure allocation, and the
captured T9-v1 audit's move rows must count exactly the captured baseline ground moves.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pickle
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import t9_batch_replay as rp  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402
from miaosuan_agent.experiments.t9_staging import StagingAddon  # noqa: E402

SCHEMA = "miaosuan-s11-batch-replay/1"
OUT = REPO_ROOT / "evaluation" / "s11-batch-allocator" / "replay.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s11" / "replay-private.json"
EV = REPO_ROOT / "local" / "evaluation"
# (configuration, card, capture stem, scenario, map id, diagnosed seat, policy that played the seat). The windows
# files' SHA-256 are recorded in the public output, so --check also fails if any input changed.
GAMES = [
    ("2120531121 C3", "s10-t9-v1-diagnosis", "2120531121.C3.s10-t9-v1-diagnosis.g01", "2120531121", "21", 11, "t9-v1"),
    ("2120531121 C3", "s10-t9-v1-diagnosis", "2120531121.C3.s10-t9-v1-diagnosis.g02", "2120531121", "21", 11,
     "baseline-v2"),
    ("1930331196 C3", "s10-t9-v1-diagnosis", "1930331196.C3.s10-t9-v1-diagnosis.g03", "1930331196", "96", 11, "t9-v1"),
    ("1930331196 C3", "s10-t9-v1-diagnosis", "1930331196.C3.s10-t9-v1-diagnosis.g04", "1930331196", "96", 11,
     "baseline-v2"),
    ("1930331196 C2", "s10-t9-v1-c2-diagnosis", "1930331196.C2.s10-t9-v1-c2-diagnosis.g01", "1930331196", "96", 1,
     "t9-v1"),
    ("1930331196 C2", "s10-t9-v1-c2-diagnosis", "1930331196.C2.s10-t9-v1-c2-diagnosis.g02", "1930331196", "96", 1,
     "baseline-v2"),
]
FAITHFUL_EVERY = 97
PERMUTE_EVERY = 1  # every decision with at least two claimants


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def seat_snap(sample: Mapping[str, Any], seat: int) -> Optional[Mapping[str, Any]]:
    return sample["seats"].get(seat) or sample["seats"].get(str(seat))


def kinds(observation: Observation, faction: int) -> Dict[int, int]:
    return {u.obj_id: u.unit_type for u in rp.own_ground(observation, faction).values()}


def replay_game(entry: tuple, every: int) -> Dict[str, Any]:
    config, card, stem, scenario, map_id, seat, played = entry
    path = EV / card / "capture" / f"{stem}.windows.pkl"
    data = EV / card / "data" / scenario / "Data"
    costs = MoveCosts.from_raw(sdk_data.load_inputs(data, scenario, map_id).cost, Origin.ENGINE, "setup_info.cost_data")
    baseline_policy = ShootReservationPolicy(costs)
    router = baseline_policy.router
    staging = StagingAddon(costs, ShootReservationPolicy(costs))
    candidate = tb.BatchPolicy(costs)
    with path.open("rb") as handle:
        samples = pickle.load(handle)["samples"]
    names = ["t9-v1", "t9-v2"] + list(rp.VARIANTS)
    totals = {name: collections.Counter() for name in names}
    removed = {name: [] for name in names}
    episodes = {name: rp.Episodes() for name in names}
    design = {name: collections.Counter() for name in rp.VARIANTS}
    checks = collections.Counter()
    rng = random.Random(f"{stem}-permutations")
    decisions: List[Dict[str, Any]] = []
    flags: Dict[int, List[Any]] = collections.defaultdict(list)
    values: Dict[int, Any] = {}
    dominated_units = {name: set() for name in rp.VARIANTS}
    first_state = None
    faction = None
    controls: collections.Counter = collections.Counter()
    series: List[Dict[int, Dict[str, Any]]] = []
    emitted_moves: List[Any] = []
    last_k = 0
    for sample in samples:
        k = sample["k"]
        last_k = k
        snap = seat_snap(sample, seat)
        if snap is None:
            continue
        raw = pickle.loads(snap["observation"])
        observation = Observation.from_raw(raw, Origin.ENGINE)
        faction = snap["faction"]
        if len(series) != k:
            raise SystemExit(f"{stem}: samples are not one per decision at k{k}")
        series.append(rp.timing_units(raw, faction))
        if raw["time"]["stage"] == 2:
            submitted = [dict(a) for a in snap.get("submitted") or []]
            controls.update(rp.control_counts(raw, faction, submitted, snap["baseline_actions"]))
            emitted_moves.extend((k, a) for a in submitted
                                 if a.get("type") == tb.MOVE and a.get("obj_id") in series[k])
        for city in raw.get("cities") or []:
            if not flags[city["coord"]] or flags[city["coord"]][-1][1] != city["flag"]:
                standing = sorted(u.obj_id for u in rp.own_ground(observation, faction).values()
                                  if not u.move_path and u.cur_hex == city["coord"])
                flags[city["coord"]].append((k, city["flag"], standing))
            values[city["coord"]] = city["value"]
        if every > 1 and k % every:
            continue
        baseline = [dict(a) for a in snap["baseline_actions"]]
        audit = snap["t9_audit"]
        t9v1 = [dict(a) for a in audit["hypothetical_t9_actions"]]
        ground = rp.own_ground(observation, faction)
        if raw["time"]["stage"] == 2:
            checks["play decisions"] += 1
            if len(rp.ground_moves(baseline, ground)) != len(audit["moves"]):
                raise SystemExit(f"{stem} k{k}: captured baseline ground moves and T9-v1 audit rows disagree")
            checks["baseline ground-move count cross-checked"] += 1
        if k % FAITHFUL_EVERY == 0 and raw["time"]["stage"] == 2:
            memory = pickle.loads(snap["memory"])
            base_memory = memory.baseline if isinstance(memory, AddonMemory) else memory
            fresh = ShootReservationPolicy(costs).decide(observation, seat, faction, base_memory)
            if [dict(a) for a in fresh.actions] != baseline:
                raise SystemExit(f"{stem} k{k}: re-decided baseline-v2 differs from the captured actions")
            checks["baseline-v2 re-decided equal"] += 1
            policy = candidate.decide(observation, seat, faction, AddonMemory(base_memory))
            pure = tb.allocate(observation, seat, faction, baseline, router)
            if [dict(a) for a in policy.actions] != [dict(a) for a in pure.actions]:
                raise SystemExit(f"{stem} k{k}: the candidate policy and the pure allocation disagree")
            checks["candidate policy equals pure allocation"] += 1
        row = rp.decision(observation, seat, faction, baseline, t9v1, router, staging)
        if row is None:
            for name in names:
                episodes[name].update(k, ())
            continue
        checks["decisions with a baseline objective move"] += 1
        unit_kind = kinds(observation, faction)
        if first_state is None:
            first_state = hashlib.sha256(json.dumps(raw, sort_keys=True, default=repr).encode("utf-8")).hexdigest()
        reference = row["allocations"]["candidate"]
        record = {"k": k, "cur_step": raw["time"]["cur_step"], "end": raw["time"].get("max_step"), "policies": {},
                  "before": {str(c): v for c, v in row["before"].items()},
                  "baseline_owners": rp.structural(observation, faction, baseline, baseline, router)["owners"],
                  "claimants": {str(c.obj_id): [c.objective, c.free_flow, c.status, unit_kind.get(c.obj_id)]
                                for c in reference.claimants.values()},
                  "kinds": {str(u): kind for u, kind in unit_kind.items()}}
        for name in names:
            info = row["policies"][name]
            counter = totals[name]
            for key in ("kept", "shortened", "withheld", "cross_objective", "prefix_failures", "late_owners",
                        "invented", "unrelated_changed"):
                counter[key] += info.get(key, 0)
            for key, value in info["capacity"].items():
                counter[f"capacity {key}"] += value
            counter["decisions changed"] += int(info.get("shortened", 0) + info.get("withheld", 0)
                                                + info.get("cross_objective", 0) > 0)
            removed[name].extend(info["removed"])
            base_moves = rp.ground_moves(baseline, ground)
            out_moves = rp.ground_moves(row["emitted"][name], ground)
            held = [u for u, a in base_moves.items() if dict(out_moves.get(u) or {}) != dict(a)]
            episodes[name].update(k, held)
            for cause, count in rp.hold_back_causes(name, observation, faction, baseline, row["emitted"][name],
                                                    row["before"], router).items():
                counter[f"hold-back: {cause}"] += count
            owner_free_flow = {str(u): rp.free_flow(router, ground[u], out_moves[u]["move_path"])
                               for ids in info["owners"].values() for u in ids}
            record["policies"][name] = {"owners": info["owners"], "held": sorted(held),
                                        "owner_free_flow": owner_free_flow}
        for name in rp.VARIANTS:
            allocation = row["allocations"][name]
            d = design[name]
            d["stage-rejected"] += sum(1 for c in allocation.changes if c["kind"] == "stage-rejected")
            d["errors"] += allocation.error is not None
            d["phantom movers excluded (unit-decisions)"] += sum(i["phantom"] for i in allocation.objectives.values())
            d["movers retained (unit-decisions)"] += sum(i["movers"] for i in allocation.objectives.values())
            dominated = rp.dominated_movers(allocation)
            d["dominated movers retained (unit-decisions)"] += len(dominated)
            dominated_units[name].update(dominated)
            for coord, info in allocation.objectives.items():
                d["objective-decisions with claimants"] += 1
                d["contended objective-decisions"] += int(info["claimants"] > max(info["free"], 0))
                group = [allocation.claimants[u] for u in info["ranked"]]
                d["mixed infantry/vehicle batches"] += int(len({unit_kind.get(c.obj_id) for c in group}) > 1)
                d["late claimants (unit-decisions)"] += sum(1 for c in group if c.status ==
                                                            "cannot arrive before the end")
        for name in ("emission-order", "route-cost", "no-end-of-game-test"):
            other = row["allocations"][name]
            for coord in reference.objectives:
                mine = set(reference.objectives[coord]["selected"])
                theirs = set(other.objectives.get(coord, {}).get("selected", []))
                design[name]["selection differs from the candidate (objective-decisions)"] += int(mine != theirs)
                design[name]["units selected differently from the candidate (unit-decisions)"] += len(mine ^ theirs)
        claimants = len(reference.claimants)
        if claimants >= 2 and k % PERMUTE_EVERY == 0:
            orders = [list(reversed(range(len(baseline)))), list(range(1, len(baseline))) + [0]]
            shuffled = list(range(len(baseline)))
            rng.shuffle(shuffled)
            orders.append(shuffled)
            if not rp.permutation_invariant(observation, seat, faction, baseline, router, orders):
                raise SystemExit(f"{stem} k{k}: candidate outcome depends on the order of baseline-v2's actions")
            checks["permutation checks passed"] += 1
        decisions.append(record)
    controls.update(rp.move_timing(series, emitted_moves, router))
    controls.update({f"remaining bound: {key}": value for key, value in rp.remaining_bound_check(series, router).items()})
    out = {"configuration": config, "game": stem, "played_by": played, "seat": seat, "decisions_read": last_k + 1,
           "control_audit": dict(sorted(controls.items())),
           "checks": dict(sorted(checks.items())),
           "policies": {name: dict(sorted(totals[name].items())) for name in names},
           "hexes_removed_per_shortened_move": {name: rp.distribution(removed[name]) for name in names},
           "hold_back_episodes": {name: rp.distribution(episodes[name].finish(last_k)) for name in names},
           "design": {name: dict(sorted(dict(design[name], **{
               "dominated movers retained (units)": len(dominated_units[name])}).items())) for name in rp.VARIANTS}}
    return {"public": out, "private": {"decisions": decisions, "flags": {str(c): v for c, v in flags.items()},
                                       "values": {str(c): v for c, v in values.items()}, "faction": faction,
                                       "first_state_sha256": first_state}}


CERTIFIED = ("t9-v1", "t9-v2", "candidate", "no-end-of-game-test")
KIND = {1: "infantry", 2: "vehicle"}


def labels(values: Mapping[str, Any]) -> Dict[str, str]:
    """Public objective labels: value, then a rank among objectives of that value (ordered by an internal key that is
    not published)."""
    out, seen = {}, collections.Counter()
    for coord in sorted(values, key=lambda c: (-values[c], int(c))):
        seen[values[coord]] += 1
        out[coord] = f"{values[coord]}-point objective {chr(64 + seen[values[coord]])}"
    return out


def owners_view(record: Mapping[str, Any], name: str, names: Mapping[str, str]) -> Dict[str, Any]:
    """Per objective label: how many places the policy granted, to which unit kinds, at which free-flow times, and how
    many of them cannot arrive before the end."""
    policy = record["policies"][name]
    out = {}
    for coord, ids in sorted(policy["owners"].items()):
        times = [policy["owner_free_flow"][str(u)] for u in ids]
        out[names[str(coord)]] = {
            "places": len(ids),
            "kinds": dict(sorted(collections.Counter(KIND.get(record["kinds"][str(u)], "other") for u in ids).items())),
            "free_flow_steps": sorted(times),
            "cannot_arrive_before_the_end": sum(1 for t in times if t is not None and
                                                record["cur_step"] + t >= record["end"])}
    return out


def decision_one(private: Mapping[str, Any]) -> Dict[str, Any]:
    """The first decision with baseline objective moves, per objective: baseline-v2's claimants and every policy's
    granted places."""
    names = labels(private["values"])
    record = private["decisions"][0]
    claimants = collections.defaultdict(list)
    for obj_id, (objective, free_flow, status, kind) in record["claimants"].items():
        claimants[names[str(objective)]].append((free_flow, KIND.get(kind, "other")))
    return {"k": record["k"],
            "baseline_claimants": {label: {"count": len(rows),
                                           "kinds": dict(sorted(collections.Counter(k for _, k in rows).items())),
                                           "free_flow_steps": sorted(f for f, _ in rows)}
                                   for label, rows in sorted(claimants.items())},
            "places": {name: owners_view(record, name, names) for name in CERTIFIED}}


def certificate(cand: Mapping[str, Any], base: Mapping[str, Any]) -> Dict[str, Any]:
    """2120531121 C3: the objective T9-v1 never captured and baseline-v2 did, and who would hold its places."""
    faction = cand["faction"]
    reached = {c for c, rows in base["flags"].items() if any(flag == faction for _, flag, _ in rows)}
    never = {c for c, rows in cand["flags"].items() if not any(flag == faction for _, flag, _ in rows)}
    missed = sorted(reached & never)
    if len(missed) != 1:
        raise SystemExit(f"expected exactly one objective missed by T9-v1 and captured by baseline-v2, got {len(missed)}")
    missed = missed[0]
    names = labels(cand["values"])
    if cand["first_state_sha256"] != base["first_state_sha256"]:
        raise SystemExit("the two 2120531121 C3 games do not start their play stage from the same seat state")
    blocked = []
    for record in cand["decisions"]:
        waiting = [u for u in record["policies"]["t9-v1"]["held"]
                   if record["claimants"].get(str(u), [None])[0] == int(missed)]
        if waiting:
            blocked.append((record, waiting))
    if not blocked:
        raise SystemExit("no decision in which T9-v1 held back a claimant of the missed objective")
    part_b = collections.Counter()
    waiting_times, chosen_times, remaining, phantom_bounds = [], [], [], []
    for record, waiting in blocked:
        before = record["before"][missed]
        part_b["decisions"] += 1
        part_b["claimants held back by T9-v1 (unit-decisions)"] += len(waiting)
        waiting_times.extend(record["claimants"][str(u)][1] for u in waiting)
        remaining.append(record["end"] - record["cur_step"])
        part_b[f"incumbents before the decision: {before['physical']} standing, {before['movers']} movers that can "
               f"arrive, {before['phantom']} that cannot"] += 1
        for name in CERTIFIED:
            ids = record["policies"][name]["owners"].get(int(missed), [])
            part_b[f"{name}: places granted (unit-decisions)"] += len(ids)
            part_b[f"{name}: decisions granting at least one place"] += int(bool(ids))
            if name == "candidate":
                chosen = [record["policies"][name]["owner_free_flow"][str(u)] for u in ids]
                chosen_times.extend(chosen)
                held = [record["claimants"][str(u)][1] for u in record["policies"][name]["held"]
                        if record["claimants"].get(str(u), [None])[0] == int(missed)]
                part_b["candidate: a held-back claimant of the objective arrives sooner than a selected one"] += int(
                    bool(chosen and held and min(held) < max(chosen)))
                part_b["candidate: places granted to claimants T9-v1 held back (unit-decisions)"] += len(
                    set(ids) & set(waiting))
    capture = next(row for row in base["flags"][missed] if row[1] == faction)
    capturers = capture[2]
    part_c = collections.Counter()
    for unit in capturers:
        last = None
        for record in base["decisions"]:
            if record["k"] < capture[0] and unit in record["baseline_owners"].get(int(missed), []):
                last = record
        if last is None:
            part_c["capturers with no baseline-v2 order to the objective in the capture"] += 1
            continue
        status = ("selected" if unit in last["policies"]["candidate"]["owners"].get(int(missed), []) else
                  "held back")
        part_c[f"candidate at the baseline-v2 order that sent the capturer: {status}"] += 1
    return {
        "objective": names[missed],
        "first_capture_decision_baseline_v2": capture[0],
        "same_initial_play_state": True,
        "decision_1": {"t9-v1 game": decision_one(cand), "baseline-v2 game": decision_one(base)},
        "t9_v1_blocked_decisions": {
            "first": blocked[0][0]["k"], "last": blocked[-1][0]["k"], "counts": dict(sorted(part_b.items())),
            "held_back_free_flow_steps": {"min": min(waiting_times), "max": max(waiting_times)},
            "candidate_selected_free_flow_steps": ({"min": min(chosen_times), "max": max(chosen_times)}
                                                   if chosen_times else None),
            "remaining_steps": {"min": min(remaining), "max": max(remaining)}},
        "baseline_v2_capturers": {"units": len(capturers), "counts": dict(sorted(part_c.items()))},
    }


def build(every: int) -> Dict[str, Any]:
    inputs, games, private = [], [], {}
    for entry in GAMES:
        path = EV / entry[1] / "capture" / f"{entry[2]}.windows.pkl"
        inputs.append({"capture": f"{entry[2]}.windows.pkl", "sha256": sha256(path)})
        result = replay_game(entry, every)
        result["public"]["decision_1"] = decision_one(result["private"])
        games.append(result["public"])
        private[entry[2]] = result["private"]
    cert = certificate(private[GAMES[0][2]], private[GAMES[1][2]])
    return {"schema": SCHEMA, "candidate": {"identity": tb.CANDIDATE_ID, "policy_source_sha256": candidate_digest(),
                                            "engine_use": "none (offline design candidate)"},
            "inputs": inputs, "games": games, "certificate_2120531121_C3": cert}, private


def candidate_digest() -> str:
    """The candidate's policy-source digest: baseline-v2's frozen source set plus the add-on wrapper and the module
    (the same construction as every exploratory run card)."""
    sources = rr.candidate_sources() + ("experiments/shoot_reservation.py", "experiments/exploratory_addon.py",
                                        "experiments/t9_batch.py")
    return digest_of_files(policy_source_files(sources=sources))


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--every", type=int, default=1, help="replay every Nth decision (development only)")
    args = parser.parse_args()
    public, private = build(args.every)
    text = dump(public)
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    if args.every == 1:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(dump(private), encoding="utf-8", newline="\n")
    print(text if args.every > 1 else f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
