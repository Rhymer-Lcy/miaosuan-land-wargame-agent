"""Sprint 34 full-step observer for the live games (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 10).

A read-only observer of ``evaluation.game.play``: nothing it computes reaches the agents or the engine. After every
engine step it keeps, privately:

* every seat's observation (pickled), its memory digest and its submitted actions (the deep copy taken before the
  step, so the engine's in-place rewriting of action objects cannot leak into the record);
* compact all-seeing facts: every unit's id, side, class, hex, path length, speed and strength, the passengers, the
  objectives' flags, the scores, new judge records and the action feedback (refusals);

and for every decision of a candidate seat it runs two independent checks:

* **reconstruction**: a fresh :class:`~miaosuan_agent.integrated.policy.CommanderPolicy` re-decides the recorded
  observation from the recorded memory; its actions must equal the submitted ones (structural stop S5 otherwise);
* **attribution**: a shadow ``baseline-v2`` (its own memory chain) decides the same observation; every unit whose action
  differs is attributed to the candidate's module for that unit (from its trace plans).

``files()`` returns the compact JSON and the pickled windows; both stay under the git-ignored ``local/`` tree.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pickle
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from ..boundary import MoveCosts, Observation, Origin
from ..decision import Memory
from ..decision.trace import canonical_json, digest
from ..experiments.shoot_reservation import ShootReservationPolicy
from ..integrated.config import Config
from ..integrated.policy import CommanderPolicy
from . import effects

TIMELINE_SCHEMA = "miaosuan-s34-timeline/1"


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def materialize(value: Any) -> Any:
    """A picklable copy of an observation: read-only mapping proxies become dicts (key types kept), recursively."""
    if isinstance(value, Mapping):
        return {k: materialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [materialize(v) for v in value]
    if isinstance(value, tuple):
        return tuple(materialize(v) for v in value)
    return value


def action_key(action: Mapping[str, Any]) -> str:
    return json.dumps(plain(dict(action)), sort_keys=True)


def unit_rows(fields: Mapping[str, Any]) -> List[List[Any]]:
    rows = []
    for u in fields.get("operators") or ():
        rows.append([u.get("obj_id"), u.get("color"), u.get("type"), u.get("sub_type"), u.get("cur_hex"),
                     len(u.get("move_path") or ()), u.get("speed"), u.get("blood"), u.get("value"), 0])
    for u in fields.get("passengers") or ():
        rows.append([u.get("obj_id"), u.get("color"), u.get("type"), u.get("sub_type"), u.get("car"), 0, 0,
                     u.get("blood"), u.get("value"), 1])
    return sorted(rows, key=lambda r: (r[0] if isinstance(r[0], int) else -1))


class S34Timeline:
    def __init__(self, candidate_policy: str, config: Config, costs: MoveCosts,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self.candidate_policy = candidate_policy
        self.config = config
        self.costs = costs
        self.clock = clock
        self.seconds = 0.0
        self.seats: Dict[int, Dict[str, Any]] = {}
        self.samples: List[Dict[str, Any]] = []
        self.steps: List[Dict[str, Any]] = []
        self.shadow = CommanderPolicy(costs, config)
        self.v2: Dict[int, Any] = {}
        self.checks = collections.Counter()
        self.mismatches: List[Dict[str, Any]] = []
        self.differing_by_module: collections.Counter = collections.Counter()
        self.module_actions: collections.Counter = collections.Counter()

    def setup(self, view: Any, players: Sequence[Mapping[str, Any]], policies: Mapping[int, str]) -> None:
        tick = self.clock()
        for p in players:
            self.seats[p["seat"]] = {"faction": p["faction"], "policy": policies[p["faction"]]}
        g = view.global_observation.fields
        self.steps.append({"k": -1, "cur_step": 0, "units": unit_rows(g),
                           "cities": [[c.get("coord"), c.get("flag"), c.get("value")] for c in g.get("cities") or ()],
                           "scores": plain(g.get("scores") or {})})
        self.seconds += self.clock() - tick

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        tick = self.clock()
        g0, g1 = before.global_observation, after.global_observation
        sample: Dict[str, Any] = {"k": index, "cur_step": g0.time().cur_step, "seats": {}}
        for d in decisions:
            seat = d["seat"]
            submitted = [plain(dict(a)) for a in d["submitted"]]
            memory = d["memory"]
            entry = {"observation": pickle.dumps(materialize(d["observation"]), protocol=4), "submitted": submitted,
                     "trace": digest(d["trace"]),
                     "memory": hashlib.sha256(canonical_json(plain(memory.to_dict())).encode("utf-8")).hexdigest()
                     if hasattr(memory, "to_dict") else None}
            if d["policy"] == self.candidate_policy:
                trace = d["trace"]
                entry["plans"] = [list(p) for p in getattr(trace, "plans", ())]
                entry["stats"] = dict(getattr(trace, "stats", ()))
                entry["fallback"] = getattr(trace, "fallback", None)
                entry["rejected"] = [list(r) for r in trace.rejected]
                self.checks["decisions"] += 1
                self.checks["fallbacks"] += bool(entry["fallback"])
                self.checks["validation_rejections"] += len(trace.rejected)
                for plan in getattr(trace, "plans", ()):
                    if plan[4]:
                        self.module_actions[f"{plan[1]}:{plan[4]}"] += 1
                self._check(index, seat, d, submitted, trace)
            sample["seats"][str(seat)] = entry
        self.samples.append(sample)
        fields = g1.fields
        judge = list(fields.get("judge_info") or ())
        feedback = [plain(e) for e in (g1.action_feedback() or ())]
        refusals = [e for e in feedback if effects.feedback_error_code(e) is not None]
        self.steps.append({"k": index, "cur_step": g1.time().cur_step, "units": unit_rows(fields),
                           "cities": [[c.get("coord"), c.get("flag"), c.get("value")] for c in fields.get("cities") or ()],
                           "scores": plain(fields.get("scores") or {}), "judge": plain(judge),
                           "refusals": refusals,
                           "jm": [[p.get("pos"), p.get("status"), p.get("obj_id")] for p in fields.get("jm_points") or ()]})
        self.seconds += self.clock() - tick

    def _check(self, index: int, seat: int, d: Mapping[str, Any], submitted: List[Any], trace: Any) -> None:
        observation = Observation.from_raw(d["observation"], Origin.ENGINE)
        faction = d["faction"]
        actions, rebuilt, _ = self.shadow.decide(observation, seat, faction, d["memory"])
        self.checks["reconstructed"] += 1
        same = sorted(action_key(a) for a in actions) == sorted(json.dumps(a, sort_keys=True) for a in submitted)
        same_trace = digest(rebuilt) == digest(trace)
        if not (same and same_trace):
            self.checks["reconstruction_mismatch"] += 1
            if len(self.mismatches) < 10:
                self.mismatches.append({"k": index, "actions_equal": same, "trace_equal": same_trace})
        if seat not in self.v2:
            self.v2[seat] = [ShootReservationPolicy(self.costs), Memory()]
        base = self.v2[seat][0].decide(observation, seat, faction, self.v2[seat][1])
        self.v2[seat][1] = base.memory
        base_units = {a.get("obj_id"): action_key(a) for a in base.actions}
        mine = {a.get("obj_id"): json.dumps(a, sort_keys=True) for a in submitted}
        plans = {p[0]: p for p in getattr(trace, "plans", ())}
        differs = False
        for unit in set(base_units) | set(mine):
            if base_units.get(unit) != mine.get(unit):
                differs = True
                self.differing_by_module[plans[unit][1] if unit in plans else "outside the plans"] += 1
        self.checks["decisions_differing_from_v2"] += differs

    def compact(self) -> Dict[str, Any]:
        return {"schema": TIMELINE_SCHEMA, "seats": {str(k): v for k, v in sorted(self.seats.items())},
                "checks": dict(self.checks), "mismatches": self.mismatches,
                "differing_by_module": dict(sorted(self.differing_by_module.items())),
                "module_actions": dict(sorted(self.module_actions.items())), "steps": self.steps,
                "observer_seconds": round(self.seconds, 3)}

    def files(self) -> tuple:
        compact = json.dumps(self.compact(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        windows = pickle.dumps({"schema": TIMELINE_SCHEMA, "samples": self.samples}, protocol=4)
        return compact, windows
