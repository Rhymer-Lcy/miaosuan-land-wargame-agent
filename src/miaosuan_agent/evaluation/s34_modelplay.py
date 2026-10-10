"""Play two agents in the Sprint 34 MODEL WORLD (:mod:`.s34_world`) and collect integration and movement metrics.

Offline only and model-based: the metrics describe legality, determinism, latency, traffic and the movement race in
the model, never a predicted engine score (the model has no combat damage).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .. import sdk_data
from ..boundary import MoveCosts
from ..decision import INERT_ID
from ..decision.trace import digest
from ..agent import PolicyAgent
from ..experiments.shoot_reservation import ShootReservationAgent
from ..integrated.agent import CommanderAgent
from ..integrated.config import VARIANTS
from .s34_world import SEATS, ModelWorld

V2 = "baseline-v2"
INERT = "inert"


def factory(name: str) -> Callable[[], Any]:
    if name == V2:
        return lambda: ShootReservationAgent()
    if name == INERT:
        return lambda: PolicyAgent(INERT_ID)
    if name in VARIANTS:
        return lambda: CommanderAgent(VARIANTS[name])
    raise ValueError(f"unknown agent {name!r}")


def play_model(data_root: Path, scenario_id: str, map_id: str, red: str, blue: str,
               max_step: Optional[int] = None, replay_every: int = 0,
               clock: Callable[[], float] = time.perf_counter) -> Dict[str, Any]:
    inputs = sdk_data.load_inputs(Path(data_root), scenario_id, map_id)
    costs = MoveCosts.from_raw(inputs.cost)
    world = ModelWorld(inputs.scenario, costs, max_step, terrain_id=int(map_id))
    names = {0: red, 1: blue}
    agents = {c: factory(names[c])() for c in (0, 1)}
    for c, agent in agents.items():
        agent.setup({"scenario": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                     "see_data": None, "seat": SEATS[c], "faction": c, "role": 1, "user_name": "model",
                     "user_id": 0})
    stats = {c: {"latency_ms": [], "actions": Counter(), "rejected": Counter(), "fallbacks": 0, "replay_checks": 0,
                 "replay_mismatches": 0, "modules": Counter(), "held": Counter(), "trace_chain": hashlib.sha256()}
             for c in (0, 1)}
    done = False
    calls = 0
    while not done and calls < world.max_step + 10:
        calls += 1
        actions = {}
        for c in (0, 1):
            obs = world.observation(c)
            memory = agents[c].memory
            tick = clock()
            produced = agents[c].step(obs)
            stats[c]["latency_ms"].append((clock() - tick) * 1000.0)
            trace = agents[c].last_trace
            stats[c]["trace_chain"].update(digest(trace).encode("ascii"))
            for a in produced:
                stats[c]["actions"][int(a["type"])] += 1
            for r in trace.rejected:
                stats[c]["rejected"][str(r[2])[:60]] += 1
            if getattr(trace, "fallback", None):
                stats[c]["fallbacks"] += 1
            for plan in getattr(trace, "plans", ()):
                stats[c]["modules"][plan[1]] += 1
                if "held:" in plan[5]:
                    stats[c]["held"][plan[5].split("held:")[1].strip()[:40]] += 1
            if replay_every and calls % replay_every == 0 and hasattr(agents[c], "replay"):
                stats[c]["replay_checks"] += 1
                if digest(agents[c].replay(obs, memory)) != digest(trace):
                    stats[c]["replay_mismatches"] += 1
            actions[c] = produced
        done = world.step(actions)
    out: Dict[str, Any] = {"scenario_id": scenario_id, "map_id": map_id, "red": red, "blue": blue,
                           "steps": world.cur_step, "max_step": world.max_step, "occupy": world.scores(),
                           "first_owner": {str(h): list(v) for h, v in sorted(world.first_owner.items())},
                           "final_flags": {str(c["coord"]): c["flag"] for c in world.cities},
                           "objective_value_total": sum(int(c.get("value") or 0) for c in world.cities),
                           "model_refusals": len(world.refused),
                           "model_refusal_examples": [r["reason"] for r in world.refused[:5]],
                           "max_wait": {}, "wait_unit_steps": {}, "seats": {}}
    for c in (0, 1):
        color_units = [u for u in list(world.units.values()) + list(world.aboard.values()) if u["color"] == c]
        ids = {u["obj_id"] for u in color_units} | {uid for uid in world.max_wait
                                                    if uid in {u["obj_id"] for u in inputs.scenario["operators"]
                                                               if u["color"] == c}}
        out["max_wait"][c] = max((world.max_wait.get(i, 0) for i in ids), default=0)
        out["wait_unit_steps"][c] = sum(world.wait_steps.get(i, 0) for i in ids)
        lat = sorted(stats[c]["latency_ms"])
        out["seats"][c] = {
            "agent": names[c], "decisions": len(lat),
            "latency_ms_p50": round(lat[len(lat) // 2], 3) if lat else None,
            "latency_ms_p99": round(lat[int(len(lat) * 0.99)], 3) if lat else None,
            "latency_ms_max": round(lat[-1], 3) if lat else None,
            "actions": {str(k): v for k, v in sorted(stats[c]["actions"].items())},
            "rejected": dict(stats[c]["rejected"]), "fallbacks": stats[c]["fallbacks"],
            "replay_checks": stats[c]["replay_checks"], "replay_mismatches": stats[c]["replay_mismatches"],
            "modules": dict(stats[c]["modules"]), "held_reasons": dict(stats[c]["held"]),
            "trace_chain": stats[c]["trace_chain"].hexdigest(),
            "embarked": sum(1 for e in world.events if e[1] == "embarked" and e[2] == c),
            "disembarked": sum(1 for e in world.events if e[1] == "disembarked" and e[2] == c),
            "indirect_orders": sum(1 for e in world.events if e[1] == "indirect" and e[2] == c),
            "friendly_exposure_unit_steps": world.friendly_exposure.get(c, 0),
        }
    return out


def dump(result: Mapping[str, Any]) -> str:
    return json.dumps(result, sort_keys=True, ensure_ascii=False)
