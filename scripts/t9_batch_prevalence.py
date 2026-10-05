"""Sprint 11 trigger prevalence of ``t9-batch-capacity-v3`` on the pinned replay corpus H0 (server only).

    python scripts/t9_batch_prevalence.py [--check]

H0 is the replay corpus pinned by ``evaluation/routing-remediation-1/corpus.json``: one baseline-v0 mirror game (C1,
both seats active) for each of the 8 frozen scenarios, every decision of both seats. As in Sprint 5, baseline-v0 must
reproduce every recorded decision exactly (else the decision is excluded) and baseline-v2 is reconstructed
sequentially per seat with its own memory; T9-v1 (frozen add-on), T9-v2 (frozen add-on) and the candidate with three
of its variants are then applied to baseline-v2's actions one decision at a time. These are baseline-v0 trajectory
states, not states any T9 policy would reach: the output says how often the allocator's triggers occur in
baseline-v2's choices on recorded states and that its invariants hold there, nothing about outcomes. Writes
``evaluation/s11-batch-allocator/prevalence.json`` (aggregates only); ``--check`` compares it byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.evaluation import t9_batch_replay as rp  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402
from miaosuan_agent.experiments.t9_allocation import AllocationAddon  # noqa: E402
from miaosuan_agent.experiments.t9_staging import StagingAddon  # noqa: E402

SCHEMA = "miaosuan-s11-batch-prevalence/1"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
OUT = REPO_ROOT / "evaluation" / "s11-batch-allocator" / "prevalence.json"
VARIANTS = {name: rp.VARIANTS[name] for name in ("candidate", "emission-order", "route-cost", "no-end-of-game-test")}
POLICIES = ("t9-v1", "t9-v2") + tuple(VARIANTS)


def sha256(path: Path) -> str:
    digest_ = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest_.update(block)
    return digest_.hexdigest()


def lines(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def game(path: Path) -> Dict[str, Any]:
    stream = lines(path)
    header = next(stream)
    scenario = header["scenario_id"]
    costs = MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario / "Data", scenario, header["map_id"]).cost)
    seats: Dict[int, Dict[str, Any]] = {}
    rows: Dict[int, Dict[str, Any]] = {}
    for row in stream:
        seat, faction = row["seat"], row["faction"]
        if seat not in seats:
            seats[seat] = {"v0": BaselinePolicy(costs), "v2": ShootReservationPolicy(costs), "m0": Memory(),
                           "m2": Memory(), "t9": AllocationAddon(costs, ShootReservationPolicy(costs)),
                           "staging": StagingAddon(costs, ShootReservationPolicy(costs)),
                           "router": ShootReservationPolicy(costs).router}
            rows[seat] = {"faction": faction, "checks": collections.Counter(), "design": collections.Counter(),
                          "policies": {name: collections.Counter() for name in POLICIES}}
        s, out = seats[seat], rows[seat]
        raw = typed_json.decode(row["observation"])
        out["checks"]["decisions"] += 1
        try:
            v0 = s["v0"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, s["m0"])
        except ContractError:
            out["checks"]["excluded: contract error"] += 1
            continue
        s["m0"] = v0.memory
        if not ([dict(a) for a in v0.actions] == [dict(a) for a in row["actions"]] and
                digest(v0.trace) == row["trace_digest"]):
            out["checks"]["excluded: baseline-v0 not reproduced"] += 1
            continue
        observation = Observation.from_raw(raw, Origin.ENGINE)
        v2 = s["v2"].decide(observation, seat, faction, s["m2"])
        s["m2"] = v2.memory
        out["checks"]["baseline-v0 reproduced, baseline-v2 reconstructed"] += 1
        baseline = [dict(a) for a in v2.actions]
        t9v1 = s["t9"].apply(observation, seat, faction, SimpleNamespace(actions=tuple(baseline)), ()).actions
        result = rp.decision(observation, seat, faction, baseline, [dict(a) for a in t9v1], s["router"],
                             s["staging"], VARIANTS)
        if result is None:
            continue
        out["checks"]["decisions with a baseline-v2 objective move"] += 1
        unit_kind = {u.obj_id: u.unit_type for u in rp.own_ground(observation, faction).values()}
        for name in POLICIES:
            info, counter = result["policies"][name], out["policies"][name]
            for key in ("kept", "shortened", "withheld", "cross_objective", "prefix_failures", "late_owners",
                        "invented", "unrelated_changed"):
                counter[key] += info.get(key, 0)
            for key, value in info["capacity"].items():
                counter[f"capacity {key}"] += value
            for cause, count in rp.hold_back_causes(name, observation, faction, baseline, result["emitted"][name],
                                                    result["before"], s["router"]).items():
                counter[f"hold-back: {cause}"] += count
        reference = result["allocations"]["candidate"]
        d = out["design"]
        d["phantom movers excluded (unit-decisions)"] += sum(i["phantom"] for i in reference.objectives.values())
        d["dominated movers retained (unit-decisions)"] += len(rp.dominated_movers(reference))
        d["errors"] += reference.error is not None
        for coord, info in reference.objectives.items():
            group = [reference.claimants[u] for u in info["ranked"]]
            d["objective-decisions with claimants"] += 1
            d["contended objective-decisions"] += int(info["claimants"] > max(info["free"], 0))
            d["mixed infantry/vehicle batches"] += int(len({unit_kind.get(c.obj_id) for c in group}) > 1)
            d["late claimants (unit-decisions)"] += sum(1 for c in group if c.status == "cannot arrive before the end")
            for name in ("emission-order", "route-cost", "no-end-of-game-test"):
                other = result["allocations"][name].objectives.get(coord, {}).get("selected", [])
                d[f"selection differs: {name} (objective-decisions)"] += int(set(other) != set(info["selected"]))
    return {"game": header["game_id"], "scenario": scenario,
            "seats": [{"faction": rows[s]["faction"], "checks": dict(sorted(rows[s]["checks"].items())),
                       "design": dict(sorted(rows[s]["design"].items())),
                       "policies": {n: dict(sorted(c.items())) for n, c in rows[s]["policies"].items()}}
                      for s in sorted(rows, key=lambda seat: rows[seat]["faction"])]}


def build() -> Dict[str, Any]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    games, inputs = [], []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        inputs.append({"file": path.name, "sha256": entry["sha256"]})
        games.append(game(path))
    if len(games) != 8:
        raise SystemExit(f"expected 8 replay corpus games, read {len(games)}")
    return {"schema": SCHEMA, "inputs": inputs, "games": games}


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = dump(build())
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
