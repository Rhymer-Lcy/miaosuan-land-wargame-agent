"""The registered read-only prevalence diagnostic ``baseline-v2-target-ownership-prevalence-1``.

Question: how often does unchanged ``baseline-v2``, on its own prospective trajectories, meet an actionable isolated
single-target shoot collision in which its first-by-unit-order owner has a strictly lower attack level than another
eligible claimant? The diagnostic plays 360 new games (the 8 frozen scenarios under C1, C2 and C3, 15 games per
configuration) on ``baseline-v1-runtime-r2`` with 32 workers through the qualified production scheduler. Nothing that
plays changes: a read-only observer classifies, privately, every shoot-collision component of every ``baseline-v2``
decision with the target-ownership design study's model (``ownership_design``), and the analysis estimates the share
of games containing at least one actionable mismatch (event E3). It is an incidence study, not a tactical evaluation;
no candidate policy runs.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import pickle
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import Origin
from ..decision import INERT_ID
from ..decision import digest as trace_digest
from . import manifest as mf
from . import ownership_design as od
from . import shoot_experiment as sx
from .canonical import value_digest
from .execution import RUNTIMES
from .identity import policy_source_digest

STUDY_ID = "baseline-v2-target-ownership-prevalence-1"
SCHEMA = "miaosuan-ownership-prevalence-manifest/1"
CAPTURE_SCHEMA = "miaosuan-ownership-prevalence-capture/1"
RESULTS_SCHEMA = "miaosuan-ownership-prevalence-results/1"
REFERENCES_SCHEMA = "miaosuan-ownership-prevalence-references/1"
PURPOSE = "diagnostic"
CONDITIONS = ("C1", "C2", "C3")
GAMES_PER_CONFIGURATION = 15
WORKERS = 32
RUNTIME = "baseline-v1-runtime-r2"
BASELINE_V2_SOURCE_SHA256 = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
SAMPLE_EVERY = 200
STOP_AFTER_CONSECUTIVE_FAILURES = 3
FINGERPRINT_SCHEMA = "ownership-structural-fingerprint/1 (target-ownership-design-1)"
OBSERVER_SOURCES = ("evaluation/ownership_prevalence.py", "evaluation/ownership_design.py",
                    "evaluation/allocation_audit.py", "evaluation/shoot_counterfactual.py")
SHOOT = 2

EVENTS = {
    "E0": "shoot collision: a connected component of the seat's shoot graph has at least two shooters (S1 or S2)",
    "E1": "S1 collision: a component with exactly one target and at least two shooters",
    "E2": "structural ownership mismatch: in an S1 component, the first shooter in baseline-v2's processing order (its "
          "owner) has a strictly lower attack level on the target than at least one other shooter; equal attack levels "
          "never make E2, and weapon ids play no part",
    "E3": "candidate-applicable mismatch (primary): E2, and the exact shoot action of the claimant the design would "
          "designate (highest attack level, then lower weapon id, then processing order) passes the project gate's "
          "single-proposal check in the same decision-time context",
}
GRAPH = ("The shoot graph of one baseline-v2 seat at one decision: shooters are the controllable units in baseline-v2's "
         "processing order with at least one shoot candidate (a well-formed valid_actions option with attack level at "
         "least 1, extracted by baseline-v2's own engage_candidates), targets are the targets of those candidates, and an "
         "edge carries the shooter's best candidate on the target by baseline-v2's within-unit rank (attack level, then "
         "weapon id). Components: S1 one target and at least two shooters; S2 two or more targets and at least two "
         "shooters; S3 one shooter.")
OBSERVER = {
    "schema": CAPTURE_SCHEMA,
    "called": "after every engine step, once every seat has decided (game.play's observer hook); it reads the seat "
              "observation each baseline-v2 seat received, its memory before the decision, its actions and its trace, "
              "and returns nothing; without an observer the game loop and its record are unchanged",
    "classified": "every decision of every baseline-v2 seat; a decision whose valid_actions list shoot options for "
                  "fewer than two units cannot hold a collision and is only counted",
    "per_component": "for every component with at least two shooters: decision index, seat, faction, kind, shooter, "
                     "target and edge counts, the structural fingerprint, E0 to E3; for S1 also each claimant's attack "
                     "level in processing order, the deciding key of the designed rule, the gate precheck of the "
                     "designated claimant, the number of claimants at the top level and whether their weapons differ, "
                     "unit classes (type, sub_type) of the owner and the designated claimant, whether their weapons are "
                     "equal, baseline-v2's emitted action category of every claimant, whether the owner's shot at the "
                     "target was emitted, the decision's trace digest, and private identifiers",
    "snapshots": f"the seat observation, memory, actions and trace digest of every decision holding an S1 component, and "
                 f"of every {SAMPLE_EVERY}th decision of each baseline-v2 seat, for the offline replay check",
    "self_checks": "the observation's canonical digest before and after classification (any difference is an observer "
                   "defect), and the consistency of each S1 component with baseline-v2's emitted actions",
    "storage": "local/evaluation/<study>/capture/<game>.ownership.json and <game>.snapshots.pkl, created exclusively, "
               "git-ignored",
}
FINGERPRINT = ("The structural fingerprint of the target-ownership design study, unchanged (ownership_design.fingerprint): "
               "configuration, seat faction, component kind, and per shooter in processing order its edges as (target "
               "index, attack level, weapon rank), whether occupation and movement are listed and whether it stands on an "
               "objective outside own control, plus whether any objective is outside own control; a 16-hex SHA-256 "
               "prefix with no unit, target or weapon id. Its source is pinned by the observer source digest.")
CLUSTERING = (
    "The game is the independent unit: games are separate engine executions. Decisions, components and fingerprints "
    "are never treated as independent samples.",
    "Within a game, components sharing a fingerprint are one situation; their repeats are reported as multiplicity.",
    "An active-seat-game is one baseline-v2 seat in one game: two per C1 game, one per C2 or C3 game. The two seats of "
    "a C1 game are not independent; active-seat-game counts are descriptive and get no binomial interval in C1.",
)
ESTIMANDS = {
    "primary": "the share of registered games containing at least one E3 event, for C1, C2, C3 and the fixed suite; the "
               "suite share weights the 24 configurations equally, which with 15 games each equals the pooled share",
    "secondary": [
        "active-seat-game share of E3 (descriptive in C1)",
        "games with E2 and games with E1",
        "decisions with E3",
        "E3 components per affected game",
        "distinct E3 fingerprints per affected game, multiplicity per fingerprint, the games containing each repeated "
        "fingerprint, maximum within-game and cross-game repetition",
        "distribution over scenarios and configurations",
        "attack-level gap (designated claimant minus owner) distribution",
        "claimant-count distribution",
        "designated-claimant gate-precheck passes and failures",
        "unit-class composition: owner and designated claimant classes, same-class and cross-class E3, equal and "
        "different weapons",
        "weapon-tie facts for open decision D-1: S1 components whose designated owner differs from the first shooter "
        "only through the weapon key, and E3 components with several claimants at the top level",
    ],
}
INTERVALS = (
    "Game-level shares: exact Clopper-Pearson 95% intervals over games (120 per condition, 360 for the suite, 15 per "
    "configuration, the last reported but not interpreted).",
    "No interval is computed over decisions, components, fingerprints or C1 active-seat-games.",
)
INSTRUMENTATION = (
    "Every game must pass the independence comparison with its configuration's serial reference (state and trace "
    "digests over the common prefix of the 15 serial baseline-v2 games of the shoot experiment's group C, and for a "
    "deterministic configuration an identical chain): the observer cannot have changed what was played.",
    "Every in-game replay check (a fresh policy instance recomputes the decision every 100 steps) must agree.",
    "Offline, in a separate process, a fresh baseline-v2 policy recomputes the decision of every captured snapshot from "
    "its observation and memory; actions and trace digest must equal the captured ones.",
    "The observer's observation digests never differ, no observer error occurs, every S1 component is consistent with "
    "baseline-v2's emitted actions, and every capture names the registered observer source digest.",
)
INTEGRITY = (
    "Exactly the 360 registered games, one record, start marker, log and capture pair each, none overwritten, in "
    "registered order; each capture matches the digests in its record and its decision counts match the record's.",
    "Every record names the registered manifest, the baseline-v2 policy source, baseline-v1-runtime-r2 with its "
    "variable, 32 workers and the registered scheduler, from a clean harness.",
    "Consecutive engine sessions, each opened and closed once, engine state, home/ and package unchanged; no leftover "
    "process; the authentication file unchanged (size and modification time, read-only).",
    "If any integrity or instrumentation check fails, the study stops before interpretation: no prevalence is reported "
    "as valid and no next-step decision is taken.",
)
STOP_RULES = (
    "Before the first game: the shared-server courtesy check of the concurrency qualification (other activity at most "
    "16 logical CPUs over 30 s and at least 16 logical CPUs idle beside the 32 workers), rechecked every 300 s up to 6 "
    "times; while the host is busy the run waits, and the registered worker count is never changed.",
    f"During the run: dispatch stops after {STOP_AFTER_CONSECUTIVE_FAILURES} consecutive games that do not complete and "
    "on any other exit status; no game is retried or replaced; a failed or capped game is preserved and reported, and "
    "counts as a game without an observed event only if it completed.",
    "The study stops for: an observer that changes emitted actions (a failed prefix or replay check), a policy digest, "
    "runtime or scheduler mismatch, ledger corruption, an authentication-state or package anomaly, or repeated "
    "unexpected process failure. It never stops because prevalence looks high or low.",
)
DECISION_RULE = {
    "outcomes": ("IMPLEMENT CANDIDATE FOR OFFLINE VALIDATION", "STOP TARGET-ALLOCATION LINE",
                 "MORE SEMANTIC EVIDENCE REQUIRED"),
    "thresholds": {"min_e3_games": 5, "min_scenarios": 2, "min_distinct_fingerprints": 3,
                   "max_top_fingerprint_game_share": 0.8, "max_cross_class_game_share": 0.5},
    "rule": (
        "Applied only when every integrity and instrumentation check passes.",
        "STOP TARGET-ALLOCATION LINE unless all of: at least 5 E3-positive games; E3-positive games in at least 2 "
        "scenarios; at least 3 distinct E3 fingerprints; no single E3 fingerprint present in 80% or more of the "
        "E3-positive games.",
        "Otherwise MORE SEMANTIC EVIDENCE REQUIRED if more than half of the E3-positive games contain only cross-class "
        "E3 components (owner and designated claimant of different unit classes).",
        "Otherwise IMPLEMENT CANDIDATE FOR OFFLINE VALIDATION.",
    ),
    "rationale": (
        "5 games: below it q is under about 1.4%, where the design study's sensitivity puts a targeted A/B above 2,000 "
        "games per arm for 30 affected games.",
        "3 distinct fingerprints: the historical replay corpus held 3 S1 mismatch situations; fewer prospectively "
        "cannot show more than one periodic state.",
        "80% of games under one fingerprint: one repeated state, confined to one configuration.",
        "cross-class half: attack levels are compared across unit classes only with that caveat; a majority of such "
        "comparisons calls for a semantic study first.",
    ),
}
ARTIFACTS = {
    "public": "this module, the manifest, the references file, the scripts, the document, the observer check and "
              "results.json with counts, shares, intervals and fingerprint hashes only",
    "private": "game records, logs, capture files and snapshots under the git-ignored local/evaluation/" + STUDY_ID + "/",
}
NOT_CLAIMED = (
    "No tactical effect: nothing here says that ownership by the higher attack level would change scores, kills, "
    "refusals or no-ops, or that a candidate would be beneficial.",
    "No candidate policy runs; the designated claimant is computed only to evaluate the gate precheck of E3.",
)


# ----------------------------------------------------------------------------------------------
# Registration


def configurations(scenarios: Sequence[str]) -> List[str]:
    return [f"{s}.{c}" for s in scenarios for c in CONDITIONS]


def game_id(config: str, k: int) -> str:
    return f"{config}.p{k:02d}"


def schedule(scenarios: Sequence[str], design_sha256: str) -> List[Dict[str, Any]]:
    """Round r plays game r of every configuration once, ordered by SHA-256 of '<design>:<r>:<config>'; if a round would
    start with the previous round's last configuration, its first two games exchange places."""
    entries: List[Dict[str, Any]] = []
    for r in range(1, GAMES_PER_CONFIGURATION + 1):
        order = sorted(configurations(scenarios),
                       key=lambda c: hashlib.sha256(f"{design_sha256}:{r}:{c}".encode("utf-8")).hexdigest())
        if entries and order[0] == entries[-1]["config"]:
            order[0], order[1] = order[1], order[0]
        for config in order:
            scenario, condition = config.split(".")
            entries.append({"game_id": game_id(config, r), "config": config, "scenario_id": scenario,
                            "condition": condition, "repetition": r, "round": r, "position": len(entries) + 1})
    return entries


def observer_source_sha256() -> str:
    return policy_source_digest(sources=OBSERVER_SOURCES)[0]


def build(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, references: Mapping[str, Any],
          references_sha256: str, rt_results: Mapping[str, Any], rt_results_sha256: str) -> Dict[str, Any]:
    """The registered manifest, from committed inputs only."""
    candidate = shoot_manifest["groups"]["C"]
    if candidate["policy_source"]["sha256"] != BASELINE_V2_SOURCE_SHA256:
        raise ValueError("the shoot experiment's group C is not the frozen baseline-v2 source")
    (scheduler,) = rt_results["production_path"]["scheduler"]
    if rt_results["disposition"]["runtime"] != RUNTIME:
        raise ValueError("the runtime qualification did not promote baseline-v1-runtime-r2")
    scenarios = [s["scenario_id"] for s in shoot_manifest["scenarios"]]
    conditions = {c: dict(candidate["conditions"][c]) for c in CONDITIONS}
    if sorted(references["configurations"]) != sorted(configurations(scenarios)):
        raise ValueError("the references do not cover exactly the registered configurations")
    exposure = {c: sorted(p["seat"] for p in shoot_manifest["players"]
                          if conditions[c][{0: "red", 1: "blue"}[p["faction"]]] == sx.CANDIDATE_ID) for c in CONDITIONS}
    design = {
        "schema": SCHEMA, "study_id": STUDY_ID, "evaluation_id": STUDY_ID, "purpose": PURPOSE,
        "question": __doc__.split("\n\n")[1].replace("\n", " "),
        "policy_under_test": sx.CANDIDATE_ID, "control_policy": INERT_ID,
        "policy_source": dict(candidate["policy_source"]), "golden_trace_chain": candidate["golden_trace_chain"],
        "identities": {"tactical": "baseline-v2", "code_identity": sx.CANDIDATE_ID,
                       "policy_source_sha256": BASELINE_V2_SOURCE_SHA256, "runtime": RUNTIME,
                       "runtime_environment": dict(RUNTIMES[RUNTIME]), "scheduler": scheduler,
                       "observer_sources": list(OBSERVER_SOURCES), "observer_source_sha256": observer_source_sha256()},
        "execution": {"workers": WORKERS, "runtime": RUNTIME, "scheduler": scheduler},
        "conditions": conditions, "active_seats": exposure,
        "scenarios": [dict(s) for s in shoot_manifest["scenarios"]],
        "players": [dict(p) for p in shoot_manifest["players"]],
        "randomness": dict(shoot_manifest["randomness"]), "caps": dict(shoot_manifest["caps"]),
        "games_per_configuration": GAMES_PER_CONFIGURATION, "games_total": len(scenarios) * len(CONDITIONS) * GAMES_PER_CONFIGURATION,
        "references": {c: dict(references["configurations"][c]) for c in sorted(references["configurations"])},
        "inputs": {"shoot_manifest_sha256": shoot_manifest_sha256, "references_sha256": references_sha256,
                   "runtime_results_sha256": rt_results_sha256},
        "known_refusal_classes": [list(c) for c in sx.KNOWN_CLASSES],
        "graph": GRAPH, "events": dict(EVENTS), "observer": dict(OBSERVER), "fingerprint": FINGERPRINT,
        "fingerprint_schema": FINGERPRINT_SCHEMA, "clustering": list(CLUSTERING), "estimands": dict(ESTIMANDS),
        "intervals": list(INTERVALS), "instrumentation": list(INSTRUMENTATION), "integrity": list(INTEGRITY),
        "stop_rules": list(STOP_RULES), "decision_rule": dict(DECISION_RULE), "artifacts": dict(ARTIFACTS),
        "not_claimed": list(NOT_CLAIMED), "parameters": {"sample_every": SAMPLE_EVERY,
                                                          "stop_after_consecutive_failures": STOP_AFTER_CONSECUTIVE_FAILURES},
        "schedule_rule": [
            "design_sha256 is the canonical SHA-256 of the manifest without schedule and design_sha256",
            "round r (r = 1..15) plays game r of each of the 24 configurations exactly once",
            "within a round, configurations are ordered by the ascending hex SHA-256 of '<design_sha256>:<r>:<config>'",
            "if a round's first configuration repeats the previous round's last one, the round's first two games "
            "exchange places",
            "positions 1..360 number the games in play order; no game is added, removed or reordered after registration",
        ],
    }
    design_sha = mf.digest(design)
    return {**design, "design_sha256": design_sha, "games": schedule(scenarios, design_sha)}


def digest(manifest: Mapping[str, Any]) -> str:
    return mf.digest(manifest)


def is_study(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(manifest: Mapping[str, Any]) -> List[mf.GameSpec]:
    scenarios = {s["scenario_id"]: s for s in manifest["scenarios"]}
    specs = []
    for entry in manifest["games"]:
        policies = manifest["conditions"][entry["condition"]]
        scenario = scenarios[entry["scenario_id"]]
        specs.append(mf.GameSpec(game_id=entry["game_id"], scenario_id=entry["scenario_id"], map_id=scenario["map_id"],
                                 condition=entry["condition"], red=policies["red"], blue=policies["blue"],
                                 repetition=entry["repetition"], max_time=int(scenario["max_time"])))
    return specs


# ----------------------------------------------------------------------------------------------
# Classification (one baseline-v2 decision)


def _kind(action: Optional[Mapping[str, Any]]) -> str:
    if action is None:
        return "none"
    return {2: "shoot", 5: "occupy", 1: "move"}.get(int(action.get("type")), "other")


def shoot_listed_units(raw: Mapping[str, Any]) -> int:
    """Units with shoot options listed in valid_actions: an upper bound on the shoot graph's shooters."""
    count = 0
    for per_unit in (raw.get("valid_actions") or {}).values():
        if isinstance(per_unit, Mapping) and any(str(k) == str(SHOOT) and v for k, v in per_unit.items()):
            count += 1
    return count


def unit_classes(raw: Mapping[str, Any]) -> Dict[int, str]:
    result = {}
    for where in ("operators", "passengers"):
        for unit in raw.get(where) or ():
            if isinstance(unit, Mapping) and "obj_id" in unit:
                result[int(unit["obj_id"])] = f"{unit.get('type')}.{unit.get('sub_type')}"
    return result


def classify(raw: Mapping[str, Any], seat: int, faction: int, config: str, actions: Sequence[Mapping[str, Any]],
             origin: Origin = Origin.ENGINE) -> List[Dict[str, Any]]:
    """Every component with at least two shooters of one baseline-v2 decision, with E0 to E3 (see EVENTS)."""
    order, graph = od.shoot_graph(raw, seat, faction, origin)
    emitted = {a.get("obj_id"): dict(a) for a in actions if isinstance(a, Mapping) and "obj_id" in a}
    classes = None
    rows = []
    for comp in od.components(order, graph):
        if len(comp.shooters) < 2:
            continue
        row: Dict[str, Any] = {"kind": comp.kind, "shooters": len(comp.shooters), "targets": len(comp.targets),
                               "edges": comp.edges, "fingerprint": od.fingerprint(config, raw, seat, faction, comp, graph,
                                                                                  origin),
                               "E0": True, "E1": comp.kind == "S1", "E2": False, "E3": False}
        if comp.kind == "S1":
            own = od.owners(comp, graph)
            target, first, designated, levels = own["target"], own["baseline_owner"], own["designated_owner"], own["levels"]
            top = [u for u, level in zip(comp.shooters, levels) if level == max(levels)]
            e2 = max(levels) > levels[0]
            precheck = od.gate_precheck(raw, seat, faction, designated, target, origin) if e2 else None
            if classes is None:
                classes = unit_classes(raw)
            first_action = emitted.get(first)
            row.update({
                "levels": levels, "key": own["key"], "E2": e2, "gate_precheck": precheck, "E3": bool(e2 and precheck),
                "gap": max(levels) - levels[0], "top_claimants": len(top),
                "top_weapons_differ": len({graph[u][target][1] for u in top}) > 1,
                "owner_class": classes.get(first), "designated_class": classes.get(designated),
                "same_class": classes.get(first) == classes.get(designated),
                "same_weapon": graph[first][target][1] == graph[designated][target][1],
                "claimant_actions": [_kind(emitted.get(u)) for u in comp.shooters],
                "owner_shot_emitted": _kind(first_action) == "shoot" and first_action.get("target_obj_id") == target,
                "private": {"shooters": list(comp.shooters), "target": target, "owner": first, "designated": designated,
                            "weapons": [graph[u][target][1] for u in comp.shooters]},
            })
        rows.append(row)
    return rows


def check_consistency(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    """S1 facts the model implies about baseline-v2's emitted actions (expected: no problem)."""
    problems = []
    for row in rows:
        if row["kind"] != "S1":
            continue
        if not row["owner_shot_emitted"]:
            problems.append("the S1 owner's shot at the target was not emitted")
        if any(action == "shoot" for action in row["claimant_actions"][1:]):
            problems.append("a later S1 claimant shot")
    return problems


# ----------------------------------------------------------------------------------------------
# The observer


def plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class Observer:
    """The read-only observer of one game. ``play(..., observer=Observer(...))`` calls :meth:`setup` once and
    :meth:`step` after every engine step; nothing it does reaches the policies or the engine."""

    def __init__(self, config: str, policy_ids: Iterable[str] = (sx.CANDIDATE_ID,), sample_every: int = SAMPLE_EVERY,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self.config, self.policies, self.sample_every, self.clock = config, frozenset(policy_ids), sample_every, clock
        self.active: List[Dict[str, Any]] = []
        self.decisions: collections.Counter = collections.Counter()
        self.classified: collections.Counter = collections.Counter()
        self.components: List[Dict[str, Any]] = []
        self.snapshots: List[Dict[str, Any]] = []
        self.mutations = 0
        self.problems: List[Dict[str, Any]] = []
        self.seconds = 0.0

    def setup(self, view: Any, players: Sequence[Mapping[str, Any]], policies: Mapping[int, str]) -> None:
        self.active = [{"seat": p["seat"], "faction": p["faction"]} for p in players if policies[p["faction"]] in self.policies]

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        tick = self.clock()
        for d in decisions:
            if d["policy"] not in self.policies:
                continue
            seat, faction, raw = d["seat"], d["faction"], d["observation"]
            self.decisions[str(seat)] += 1
            s1 = False
            if shoot_listed_units(raw) >= 2:
                self.classified[str(seat)] += 1
                before_digest = value_digest(dict(raw))
                rows = classify(raw, seat, faction, self.config, d["actions"])
                if value_digest(dict(raw)) != before_digest:
                    self.mutations += 1
                trace = trace_digest(d["trace"])
                for problem in check_consistency(rows):
                    self.problems.append({"k": index, "seat": seat, "problem": problem})
                for row in rows:
                    self.components.append({"k": index, "seat": seat, "faction": faction, "trace": trace, **row})
                s1 = any(r["E1"] for r in rows)
            if s1 or self.decisions[str(seat)] % self.sample_every == 0:
                self.snapshots.append({"k": index, "seat": seat, "faction": faction, "reason": "S1" if s1 else "sample",
                                       "observation": pickle.dumps(dict(raw), protocol=4),
                                       "memory": pickle.dumps(d["memory"], protocol=4),
                                       "actions": plain(list(d["actions"])), "trace": trace_digest(d["trace"])})
        self.seconds += self.clock() - tick

    def compact(self) -> Dict[str, Any]:
        return {"schema": CAPTURE_SCHEMA, "config": self.config, "active": self.active,
                "decisions": dict(sorted(self.decisions.items())), "classified": dict(sorted(self.classified.items())),
                "components": plain(self.components), "snapshots": len(self.snapshots),
                "observation_mutations": self.mutations, "problems": self.problems, "observer_seconds": self.seconds,
                "observer_source_sha256": observer_source_sha256()}

    def files(self) -> Tuple[bytes, bytes]:
        compact = json.dumps(self.compact(), ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        return compact, pickle.dumps({"schema": CAPTURE_SCHEMA, "snapshots": self.snapshots}, protocol=4)

    def summary(self, compact: bytes, snapshots: bytes) -> Dict[str, Any]:
        flags = {e: sum(1 for c in self.components if c[e]) for e in ("E0", "E1", "E2", "E3")}
        return {"schema": CAPTURE_SCHEMA, "decisions": dict(sorted(self.decisions.items())), "components": flags,
                "snapshots": len(self.snapshots), "observation_mutations": self.mutations,
                "problems": len(self.problems), "observer_seconds": self.seconds,
                "observer_source_sha256": observer_source_sha256(),
                "compact_sha256": hashlib.sha256(compact).hexdigest(),
                "snapshots_sha256": hashlib.sha256(snapshots).hexdigest()}


# ----------------------------------------------------------------------------------------------
# Analysis helpers


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> List[float]:
    """Exact binomial interval by bisection on the binomial tails."""
    def tail_ge(p: float) -> float:
        return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(x, n + 1))

    def tail_le(p: float) -> float:
        return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(0, x + 1))

    def solve(f: Callable[[float], float], target: float, increasing: bool) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    low = 0.0 if x == 0 else solve(tail_ge, alpha / 2, True)
    high = 1.0 if x == n else solve(tail_le, alpha / 2, False)
    return [round(low, 4), round(high, 4)]


def next_step(games: Sequence[Mapping[str, Any]], integrity_pass: bool) -> Optional[str]:
    """The registered decision rule. ``games``: one entry per completed game with its scenario, configuration and E3
    components (each with its fingerprint and same_class)."""
    if not integrity_pass:
        return None
    t = DECISION_RULE["thresholds"]
    positive = [g for g in games if g["e3"]]
    scenarios = {g["scenario_id"] for g in positive}
    fingerprints = collections.Counter(fp for g in positive for fp in {c["fingerprint"] for c in g["e3"]})
    top_share = max(fingerprints.values()) / len(positive) if positive else 1.0
    if not (len(positive) >= t["min_e3_games"] and len(scenarios) >= t["min_scenarios"]
            and len(fingerprints) >= t["min_distinct_fingerprints"] and top_share < t["max_top_fingerprint_game_share"]):
        return DECISION_RULE["outcomes"][1]
    cross_only = sum(1 for g in positive if all(not c["same_class"] for c in g["e3"]))
    if cross_only > t["max_cross_class_game_share"] * len(positive):
        return DECISION_RULE["outcomes"][2]
    return DECISION_RULE["outcomes"][0]
