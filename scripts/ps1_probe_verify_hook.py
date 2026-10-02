"""Offline verification of the P1 probe hook on a real captured game (``docs/PS1_ENGINE_PROBE.md``, section 4).

    PYTHON scripts/ps1_probe_verify_hook.py [--work DIR] [--game ID] [--certificate FILE] [--out FILE]

Replays ``ps1-probe-hook-1`` decision by decision over a captured game of the frozen split candidate (default: the
Sprint 2 split game ``1910631192.C3.c.x01`` in ``local/evaluation/t1r-diagnosis-1``, a snapshot every step) and
checks, at every decision before the hook's trigger:

* the hooked policy's actions and trace digest equal a fresh ``tactic-deployment-split-1`` decision on the same
  captured observation and memory, and equal the captured actions and trace digest of the game itself;
* the hooked policy's own memory chain carries the candidate's memory unchanged.

It then reports the trigger step, the deadlocked set, the verification result, the selected group and its planned
back-off paths, and, with ``--certificate``, compares them with the first recovery of the Sprint 3 A2 certificate
(stopped units and their planned destinations). Private output only (unit ids, hexes): ``--out`` defaults to
``local/diagnostics/ps1-probe/hook-verification.json``. The process refuses on any disagreement before the trigger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import digest  # noqa: E402
from miaosuan_agent.experiments import ps1_probe_hook as hook  # noqa: E402
from miaosuan_agent.experiments.deployment_split import DeploymentSplitPolicy  # noqa: E402
from miaosuan_agent.evaluation.residual516 import plain  # noqa: E402

SCREEN = "tactical-screen-deployment-split-1"


def load_costs(work: Path, scenario: str) -> MoveCosts:
    manifest = json.loads((REPO_ROOT / "evaluation" / SCREEN / "manifest.json").read_text(encoding="utf-8"))
    entry = next(s for s in manifest["scenarios"] if s["scenario_id"] == scenario)
    path = sdk_data.map_paths(work / "data" / scenario / "Data", entry["map_id"])["cost"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["inputs_sha256"]["cost"]:
        raise SystemExit(f"REFUSED: {path} does not match the manifest's cost digest")
    return MoveCosts.from_raw(sdk_data.load_cost(path), Origin.ENGINE)


def captured_rewrites(mine: List[Dict[str, Any]], captured: List[Dict[str, Any]]) -> Any:
    """How many captured actions differ from ``mine`` only by the engine's documented in-place rewrite of a
    deployment split's type (314 to 14, serialised after the step); None if they differ in any other way."""
    if len(mine) != len(captured):
        return None
    rewrites = 0
    for a, b in zip(mine, captured):
        if a == b:
            continue
        if a.get("type") == 314 and b.get("type") == 14 and dict(a, type=14) == b:
            rewrites += 1
            continue
        return None
    return rewrites


def verify(samples: List[Dict[str, Any]], seat: int, faction: int, costs: MoveCosts) -> Dict[str, Any]:
    """Replay the hook over the captured snapshots of ``seat`` (ascending k, one per decision from k = 1)."""
    ks = [s["k"] for s in samples]
    if ks != list(range(ks[0], ks[0] + len(ks))):
        raise SystemExit("REFUSED: the capture does not hold a snapshot at every decision")
    policy, fresh = hook.ProbePolicy(costs), DeploymentSplitPolicy(costs)
    memory = None
    out: Dict[str, Any] = {"decisions_checked": 0, "trigger": None}
    for sample in samples:
        entry = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        raw = pickle.loads(entry["observation"])
        inner_memory = pickle.loads(entry["memory"])
        if memory is None:
            memory = hook.ProbeMemory(inner=inner_memory)
        elif memory.inner != inner_memory:
            raise SystemExit(f"REFUSED: k {sample['k']}: the hook's chain carries a different candidate memory")
        observation = Observation.from_raw(raw, Origin.ENGINE)
        hooked = policy.decide(observation, seat, faction, memory)
        if hooked.memory.probe.phase != "watching":
            out["trigger"] = {"k": sample["k"], "cur_step": observation.time().cur_step,
                              "phase": hooked.memory.probe.phase,
                              "group": [[u, h, list(p)] for u, h, p in hooked.memory.probe.group],
                              "notes": [d for d in hooked.trace.diagnostics if d.startswith(hook.NOTE)],
                              "actions": [plain(a) for a in hooked.actions],
                              "candidate_actions": plain(entry["actions"])}
            break
        plainly = fresh.decide(observation, seat, faction, inner_memory)
        if [dict(a) for a in hooked.actions] != [dict(a) for a in plainly.actions]:
            raise SystemExit(f"REFUSED: k {sample['k']}: the hooked actions differ from the candidate's")
        if digest(hooked.trace) != digest(plainly.trace) or digest(hooked.trace) != entry["trace"]:
            raise SystemExit(f"REFUSED: k {sample['k']}: the trace digest differs from the candidate's or the capture's")
        rewritten = captured_rewrites(plain([dict(a) for a in hooked.actions]), entry["actions"])
        if rewritten is None:
            raise SystemExit(f"REFUSED: k {sample['k']}: the hooked actions differ from the captured ones")
        out["captured_split_rewrites"] = out.get("captured_split_rewrites", 0) + rewritten
        if hooked.memory.inner != plainly.memory:
            raise SystemExit(f"REFUSED: k {sample['k']}: the candidate memory differs")
        memory = hooked.memory
        out["decisions_checked"] += 1
    out["first_k"], out["last_k_checked"] = ks[0], ks[0] + out["decisions_checked"] - 1
    return out


def compare_certificate(trigger: Dict[str, Any], certificate: Dict[str, Any]) -> Dict[str, Any]:
    """The hook's selection against the first recovery of a Sprint 3 certificate (private events list)."""
    events = certificate["events"]
    first = min(e[0] for e in events if e[1] == "stop")
    stops = sorted(e[2] for e in events if e[1] == "stop" and e[0] == first)
    planned = {}
    for step, kind, uid, detail in events:
        if kind == "order" and uid in stops and uid not in planned and step > first:
            planned[uid] = detail[0]  # (destination, path length)
    mine = {u: p[-1] for u, _, p in trigger["group"]}
    return {"certificate_first_stop_k": first, "hook_trigger_k": trigger["k"], "same_k": first == trigger["k"],
            "same_units": sorted(mine) == stops, "same_destinations": all(planned.get(u) == d for u, d in mine.items()),
            "certificate_stops": stops, "certificate_destinations": planned, "hook_destinations": mine}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / "t1r-diagnosis-1")
    parser.add_argument("--game", default="1910631192.C3.c.x01")
    parser.add_argument("--certificate", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "ps1" / "certificates" / "A2.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "ps1-probe" / "hook-verification.json")
    args = parser.parse_args()
    record = json.loads((args.work / "games" / f"{args.game}.json").read_text(encoding="utf-8"))
    seat_rec = next(s for s in record["seats"] if s["policy"] != "inert-v0")
    windows = pickle.loads((args.work / "capture" / f"{args.game}.windows.pkl").read_bytes())
    costs = load_costs(args.work, record["scenario_id"])
    result = verify(sorted(windows["samples"], key=lambda s: s["k"]), seat_rec["seat"], seat_rec["faction"], costs)
    if result["trigger"] is not None and args.certificate.exists():
        result["certificate"] = compare_certificate(result["trigger"],
                                                    json.loads(args.certificate.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "trigger"}
    if result["trigger"]:
        summary["trigger"] = {k: result["trigger"][k] for k in ("k", "cur_step", "phase")}
        summary["group_size"] = len(result["trigger"]["group"])
        summary["certificate"] = {k: v for k, v in result.get("certificate", {}).items()
                                  if k in ("same_k", "same_units", "same_destinations", "certificate_first_stop_k")}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
