"""Read-only audit of baseline-v2's same-step shoot-target reservation (``target-allocation-audit-1``).

    python scripts/audit_target_allocation.py [--check]

No engine and no policy change. The registered shoot experiment's records hold per-seat aggregates only, so its
decisions cannot be reconstructed; the audit uses every private corpus whose decision-time observations can be:

* D1, the residual-516 diagnostic (baseline-v2 on runtime-r2, 1930331196 C3): every captured snapshot, kept only
  where baseline-v2 reproduces actions, trace digest and memory; the compact log of every step gives the outcome in
  the actual baseline-v2 trajectory and the fixed short horizon (1, 2 and 5 steps);
* D2, the routing remediation's replay corpus (8 baseline-v0 games, C1): kept only where baseline-v0 reproduces the
  recorded decision and every difference of baseline-v2 from it carries baseline-v2's own reservation record; the
  next state is used only where the recorded actions equal baseline-v2's;
* D3, the latency diagnostic's captured decisions (baseline-v1, C2 and C3): kept only where baseline-v1 reproduces
  the recorded trace digest and every difference of baseline-v2 from it carries a shoot-reservation record; no next
  state exists.

``miaosuan_agent.evaluation.allocation_audit`` reconstructs every collision group from baseline-v2's own trace,
classifies the displaced units, measures attack-level ownership and coupling, and runs the read-only O-B oracle.
The public output holds aggregate counts only; ``--check`` rebuilds it and compares.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.evaluation import allocation_audit as aa  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import OccupyReservationPolicy  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

AUDIT_ID = "target-allocation-audit-1"
OUT = REPO_ROOT / "evaluation" / AUDIT_ID / "audit.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "allocation" / "audit-private.json"
D1 = REPO_ROOT / "local" / "evaluation" / rd.DIAGNOSTIC_ID
CORPUS = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID / "corpus.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
SCHEMA = "miaosuan-target-allocation-audit/1"
V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
HORIZONS = aa.HORIZONS
Outcome = Optional[Callable[[str, int, int], Any]]


def costs_for(root: Path, scenario_id: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(root / scenario_id / "Data", scenario_id, map_id).cost)


def lines(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def pinned(entry: Mapping[str, Any]) -> Path:
    path = REPO_ROOT / entry["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{entry['path']} does not match its pinned digest")
    return path


def explained(reference: Any, v2: Any, allow_suppressed: bool) -> bool:
    """Every unit on which baseline-v2 differs from the reference carries baseline-v2's own reservation record."""
    old = {a.get("obj_id", "seat"): dict(a) for a in reference.actions}
    new = {a.get("obj_id", "seat"): dict(a) for a in v2.actions}
    payload = v2.trace.to_dict()
    marked = {e["obj_id"] for e in payload.get("shoot_reserved", []) if e["effect"] != "unchanged"}
    if allow_suppressed:
        marked |= {s["obj_id"] for s in payload.get("suppressed", [])}
    return all(old.get(k) == new.get(k) or k in marked for k in set(old) | set(new))


class Audit:
    def __init__(self) -> None:
        self.fidelity: collections.Counter = collections.Counter()
        self.decisions: collections.Counter = collections.Counter()
        self.groups: List[Dict[str, Any]] = []
        self.units: List[Dict[str, Any]] = []
        self.components: List[Dict[str, Any]] = []
        self.problems: List[Dict[str, Any]] = []

    def decision(self, where: Dict[str, Any], raw: Mapping[str, Any], seat: int, faction: int, v2: Any, costs: MoveCosts,
                 memory: Memory, outcome: Outcome = None) -> None:
        """One verified baseline-v2 decision. ``outcome(kind, unit, target)`` gives the trajectory's evidence."""
        self.decisions[where["corpus"]] += 1
        groups = aa.collision_groups(raw, v2)
        if not groups:
            return
        self.decisions[f"{where['corpus']} with exclusions"] += 1
        problems = aa.inconsistencies(raw, v2)
        fresh = ShootReservationPolicy(costs).decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
        if [dict(a) for a in fresh.actions] != [dict(a) for a in v2.actions]:
            problems.append("a fresh baseline-v2 instance decides differently on the same observation")
        self.fidelity["reconstruction inconsistencies"] += len(problems)
        self.problems.extend({**where, "problem": p} for p in problems)
        self.components.extend({**where, **c} for c in aa.components(groups))
        record = {e["obj_id"]: e for e in v2.trace.to_dict()["shoot_reserved"]}
        options = aa.candidates(raw)
        emitted = {a["obj_id"]: dict(a) for a in v2.actions if "obj_id" in a}
        for group in groups:
            oracle = aa.oracle_b(raw, seat, faction, v2, group, lambda: ShootReservationPolicy(costs), memory)
            if oracle["owner_changed"]:
                again = aa.oracle_b(raw, seat, faction, v2, group, lambda: ShootReservationPolicy(costs), memory)
                self.fidelity["O-B repeated runs differing"] += again != oracle
            self.groups.append({**where, "target": group.target, **group.metrics(), "oracle": oracle,
                                "outcome": outcome("target", group.reserver, group.target) if outcome else {"class": "T3"},
                                "situation": [where["corpus"], where["game"], seat, group.target,
                                              sorted(e["unit"] for e in group.eligible)],
                                "recorded_next": outcome("recorded", group.reserver, group.target) if outcome
                                else "unavailable"})
            for unit in group.displaced:
                effect = record[unit]["effect"]
                level = next(c["level"] for c in group.claimants if c["unit"] == unit)
                entry = {**where, "unit": unit, "target": group.target, "fallback": aa.FALLBACK[effect],
                         "stronger_than_reserver": level > group.reserver_level, "level_gap": level - group.reserver_level,
                         "group_claimants": len(group.claimants)}
                if effect == "fallback-none":
                    entry["no_op"] = aa.no_op_reasons(raw, seat, faction, v2, unit, ShootReservationPolicy(costs).router)
                if effect == "alternate-target":
                    action = emitted[unit]
                    alternate = next(o[2] for o in options[unit]
                                     if o[0] == action["target_obj_id"] and o[1] == action["weapon_id"])
                    entry["redirect"] = {"preferred_level": level, "alternate_level": alternate,
                                         "outcome": outcome("redirect", unit, action["target_obj_id"]) if outcome
                                         else {"class": "unavailable"}}
                entry["follow_up"] = outcome("follow", unit, group.target) if outcome else None
                self.units.append(entry)


# ----------------------------------------------------------------------------------------------
# D1


def shot_evidence(step: Mapping[str, Any], unit: int, target: int) -> Dict[str, Any]:
    """The compact log's evidence on one unit's shot at one target in one step (no causal reading)."""
    mine = [i["action"] for i in step["batch"] if i["action"].get("obj_id") == unit
            and i["action"].get("target_obj_id") == target and i["action"].get("type") in rd.SHOT_TYPES]
    codes = [rd.feedback_code(f) for f in step["feedback"] for a in mine
             if rd.refusals.same_action(f.get("message") or {}, a)]
    shot = ("not submitted" if not mine else "no feedback" if not codes
            else "accepted" if codes[0] is None else f"refused {codes[0]}")
    return {"class": "T1" if target in step["gone"] else "T2", "shot": shot,
            "judged": any(r.get("att_obj_id") == unit and r.get("target_obj_id") == target for r in step["judge_new"]),
            "other_actions_on_target": sum(1 for i in step["batch"] if i["action"].get("target_obj_id") == target
                                           and i["action"].get("obj_id") != unit)}


def follow(steps: List[Mapping[str, Any]], k: int, unit: int, target: int) -> Dict[str, Any]:
    """The unit's actions at steps k+1..k+h and the presence of unit and target after step k+h (actual trajectory)."""
    result: Dict[str, Any] = {}
    for horizon in HORIZONS:
        if k + horizon >= len(steps):
            result[str(horizon)] = None
            continue
        gone = set().union(*(set(s["gone"]) for s in steps[k:k + horizon + 1]))
        actions = [i["action"] for s in steps[k + 1:k + horizon + 1] for i in s["batch"] if i["action"].get("obj_id") == unit]
        result[str(horizon)] = {
            "unit_present": unit not in gone, "target_present": target not in gone,
            "any_action": bool(actions),
            "shoots": any(a.get("type") in rd.SHOT_TYPES for a in actions),
            "shoots_original_target": any(a.get("type") in rd.SHOT_TYPES and a.get("target_obj_id") == target for a in actions),
            "moves_or_occupies": any(a.get("type") in (aa.MOVE, aa.OCCUPY) for a in actions)}
    return result


def d1(audit: Audit) -> None:
    manifest = json.loads((REPO_ROOT / "evaluation" / rd.DIAGNOSTIC_ID / "manifest.json").read_text(encoding="utf-8"))
    scenario = manifest["scenarios"][0]
    costs = costs_for(D1 / "data", scenario["scenario_id"], scenario["map_id"])
    for game in [g["game_id"] for g in manifest["games"]]:
        windows = pickle.loads((D1 / "capture" / f"{game}.windows.pkl").read_bytes())
        steps = json.loads((D1 / "capture" / f"{game}.capture.json").read_text(encoding="utf-8"))["steps"]
        snaps = {s["k"]: s for e in windows["events"] for s in e["window"]}
        snaps.update({s["k"]: s for s in windows["samples"]})
        for k, snap in sorted(snaps.items()):
            for seat, entry in sorted(snap["seats"].items()):
                raw, memory = pickle.loads(entry["observation"]), pickle.loads(entry["memory"])
                v2 = ShootReservationPolicy(costs).decide(Observation.from_raw(raw, Origin.ENGINE), seat, entry["faction"],
                                                          memory)
                exact = (rd.plain([dict(a) for a in v2.actions]) == entry["actions"] and digest(v2.trace) == entry["trace"]
                         and v2.memory == memory)
                audit.fidelity["D1 decisions"] += 1
                audit.fidelity["D1 baseline-v2 exact"] += exact
                if not exact:
                    audit.fidelity["D1 excluded: baseline-v2 not reproduced"] += 1
                    continue

                def outcome(kind: str, unit: int, target: int, k: int = k) -> Any:
                    if kind == "recorded":
                        return "absent" if target in steps[k]["gone"] else "present"
                    return follow(steps, k, unit, target) if kind == "follow" else shot_evidence(steps[k], unit, target)
                audit.decision({"corpus": "D1", "config": f"{scenario['scenario_id']} {rd.CONDITION}", "game": game,
                                "k": k, "seat": seat}, raw, seat, entry["faction"], v2, costs, memory, outcome)


# ----------------------------------------------------------------------------------------------
# D2 and D3


def d2(audit: Audit) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        stream = lines(pinned(entry))
        header = next(stream)
        costs = costs_for(DATA, header["scenario_id"], header["map_id"])
        rows = list(stream)
        by_step: Dict[int, Dict[int, Dict[str, Any]]] = collections.defaultdict(dict)
        for row in rows:
            by_step[row["step"]][row["faction"]] = row
        state: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            seat, faction = row["seat"], row["faction"]
            s = state.setdefault(seat, {"v0": BaselinePolicy(costs), "v2": ShootReservationPolicy(costs),
                                        "m0": Memory(), "m2": Memory()})
            raw = typed_json.decode(row["observation"])
            audit.fidelity["D2 decisions"] += 1
            try:
                v0 = s["v0"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, s["m0"])
            except ContractError:
                audit.fidelity["D2 excluded: contract error"] += 1
                continue
            s["m0"] = v0.memory
            memory = s["m2"]
            v2 = s["v2"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
            s["m2"] = v2.memory
            if not ([dict(a) for a in v0.actions] == [dict(a) for a in row["actions"]]
                    and digest(v0.trace) == row["trace_digest"]):
                audit.fidelity["D2 excluded: baseline-v0 not reproduced"] += 1
                continue
            audit.fidelity["D2 baseline-v0 exact"] += 1
            if not explained(v0, v2, allow_suppressed=True):
                audit.fidelity["D2 excluded: baseline-v2 difference unexplained"] += 1
                continue
            audit.fidelity["D2 baseline-v2 explained"] += 1
            recorded = None
            after = by_step.get(row["step"] + 1, {}).get(1 - faction)
            if after is not None:
                view = typed_json.decode(after["observation"])
                recorded = {u["obj_id"] for u in view["operators"]} | {u["obj_id"] for u in view.get("passengers") or []}
            present = recorded if [dict(a) for a in row["actions"]] == [dict(a) for a in v2.actions] else None

            def outcome(kind: str, unit: int, target: int, present: Optional[set] = present,
                        recorded: Optional[set] = recorded) -> Any:
                if kind == "recorded":
                    return "unavailable" if recorded is None else "present" if target in recorded else "absent"
                if kind == "follow":
                    return None
                if present is None:
                    return {"class": "T3"}
                return {"class": "T1" if target not in present else "T2", "shot": "unrecorded"}
            audit.decision({"corpus": "D2", "config": f"{header['scenario_id']} C1", "game": header["game_id"],
                            "k": row["step"], "seat": seat}, raw, seat, faction, v2, costs, memory, outcome)


def d3(audit: Audit) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    study = json.loads((REPO_ROOT / "evaluation" / "baseline-v1-variance-study-1" / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json").read_text(encoding="utf-8"))
    maps = {s["scenario_id"]: s["map_id"] for s in study["scenarios"]}
    for entry in corpus["files"]:
        if entry["role"] != "latency diagnostic captures":
            continue
        path = pinned(entry)
        game = path.name.split(".")[0]
        planned = next(g for g in plan["games"] if g["id"] == game)
        costs = costs_for(DATA, planned["scenario_id"], maps[planned["scenario_id"]])
        for capture in lines(path):
            raw = typed_json.decode(capture["observation"])
            seat, faction = capture["seat"], capture["faction"]
            memory = Memory(deployment_sent=bool(capture["memory"]["deployment_sent"]))
            audit.fidelity["D3 decisions"] += 1
            v1 = OccupyReservationPolicy(costs).decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
            if digest(v1.trace) != capture["expected_trace_digest"]:
                audit.fidelity["D3 excluded: baseline-v1 not reproduced"] += 1
                continue
            audit.fidelity["D3 baseline-v1 exact"] += 1
            v2 = ShootReservationPolicy(costs).decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
            if not explained(v1, v2, allow_suppressed=False):
                audit.fidelity["D3 excluded: baseline-v2 difference unexplained"] += 1
                continue
            audit.fidelity["D3 baseline-v2 explained"] += 1
            audit.decision({"corpus": "D3", "config": f"{planned['scenario_id']} {planned['condition']}", "game": game,
                            "k": capture["decision"], "seat": seat}, raw, seat, faction, v2, costs, memory)


# ----------------------------------------------------------------------------------------------
# the registered arm, for context (public per-configuration aggregates only)

SHOOT_RESULTS = REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "results.json"
EFFECT_KEYS = {"alternate_target_redirections": "F1 alternate shoot", "fallback_occupy": "F2 occupy",
               "fallback_move": "F3 move", "fallback_none": "F4 no-op"}


def registered_arm() -> Dict[str, Any]:
    """Group C of the shoot experiment: per-configuration totals of each displacement effect (mean x games)."""
    results = json.loads(SHOOT_RESULTS.read_text(encoding="utf-8"))
    per_config: Dict[str, Dict[str, int]] = collections.defaultdict(dict)
    for key, label in EFFECT_KEYS.items():
        for config, stats in results["descriptive"]["C"][key]["configurations"].items():
            total = stats["mean"] * stats["n"]
            if abs(total - round(total)) > 1e-3 or stats["missing"]:
                raise SystemExit(f"{config} {key}: the mean does not give a whole total")
            per_config[config][label] = int(round(total))
        if sum(per_config[c][label] for c in per_config) != results["totals"]["C"][key]:
            raise SystemExit(f"{key}: the per-configuration totals do not sum to the published total")
    return {"totals": {label: sum(per_config[c][label] for c in per_config) for label in EFFECT_KEYS.values()},
            "by_condition": {cond: {label: sum(v[label] for c, v in per_config.items() if c.endswith(cond))
                                    for label in EFFECT_KEYS.values()} for cond in ("C1", "C2", "C3")},
            "by_configuration": {c: dict(sorted(v.items())) for c, v in sorted(per_config.items())}}


# ----------------------------------------------------------------------------------------------
# aggregates


def hist(values: Any) -> Dict[str, int]:
    return {str(k): v for k, v in sorted(collections.Counter(values).items(), key=lambda kv: (isinstance(kv[0], str), kv[0]))}


def situations(groups: List[Dict[str, Any]], units: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Added at review, after the first run (the gate is unchanged): collision groups of one game and seat with the
    same target and the same eligible units are one recurring situation, so the groups are not independent."""
    def key(g: Mapping[str, Any]) -> str:
        return json.dumps(g["situation"])
    occurrences: Dict[str, List[int]] = collections.defaultdict(list)
    for g in groups:
        occurrences[key(g)].append(g["k"])
    no_op = {(u["corpus"], u["game"], u["k"], u["seat"], u["target"]) for u in units if u["fallback"] == "F4 no-op"}
    with_no_op = [g for g in groups if (g["corpus"], g["game"], g["k"], g["seat"], g["target"]) in no_op]
    stronger = [g for g in groups if g["stronger_displaced"]]
    return {
        "distinct": len(occurrences),
        "distinct_with_a_stronger_displaced_claimant": len({key(g) for g in stronger}),
        "distinct_with_a_no_op_unit": len({key(g) for g in with_no_op}),
        "games_with_a_stronger_displaced_claimant": len({(g["corpus"], g["game"]) for g in stronger}),
        "occurrences_per_situation": hist(len(v) for v in occurrences.values()),
        "occurrences_per_stronger_situation": hist(len(occurrences[k]) for k in {key(g) for g in stronger}),
        "steps_between_recurrences": hist(b - a for v in occurrences.values() for a, b in zip(sorted(v), sorted(v)[1:])),
        "recorded_trajectory_next_step": hist(
            f"{g['corpus']} | target {g['recorded_next']} | {'stronger displaced' if g['stronger_displaced'] else 'none stronger'}"
            for g in groups),
    }


def summarize(audit: Audit) -> Dict[str, Any]:
    groups, units = audit.groups, audit.units
    stronger = [g for g in groups if g["stronger_displaced"]]
    changed = [g for g in groups if g["oracle"]["owner_changed"]]
    unambiguous = [g for g in changed if g["oracle"]["unambiguous"]]
    no_op = [u for u in units if u["fallback"] == "F4 no-op"]
    redirects = [u for u in units if u["fallback"] == "F1 alternate shoot"]
    by_config: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for g in groups:
        by_config[g["config"]]["collision groups"] += 1
        by_config[g["config"]]["groups with a stronger displaced claimant"] += bool(g["stronger_displaced"])
        by_config[g["config"]]["groups whose owner O-B changes"] += g["oracle"]["owner_changed"]
    for u in units:
        by_config[u["config"]]["displaced units"] += 1
        by_config[u["config"]]["no-op displaced units"] += u["fallback"] == "F4 no-op"
    follow_up: Dict[str, Any] = {}
    for fallback in sorted({u["fallback"] for u in units if u["follow_up"]}):
        rows = [u for u in units if u["follow_up"] and u["fallback"] == fallback]
        follow_up[fallback] = {"units": len(rows)}
        for horizon in HORIZONS:
            seen = [u["follow_up"][str(horizon)] for u in rows if u["follow_up"][str(horizon)] is not None]
            follow_up[fallback][str(horizon)] = {"observed": len(seen), **{key: sum(1 for r in seen if r[key]) for key in (
                "unit_present", "target_present", "any_action", "shoots", "shoots_original_target", "moves_or_occupies")}}
    decisions_changed = {(g["corpus"], g["game"], g["k"], g["seat"]) for g in changed}
    gate = {
        "G0 at least 30 reconstructable collision groups": len(groups) >= aa.MIN_GROUPS,
        "G1 strictly lower-attack ownership with a stronger claimant displaced in at least 10% and at least 10 groups":
            len(stronger) >= 10 and 10 * len(stronger) >= len(groups),
        "G2 such groups in at least two scenarios": len({g["config"].split()[0] for g in stronger}) >= 2,
        "G3 the ranking fields are in the seat's own observation": True,
        "G4 O-B deterministic (repeated runs identical, total tie-breaks)": audit.fidelity["O-B repeated runs differing"] == 0,
        "G5 O-B changes the emitted actions in at least 10 decisions": len(decisions_changed) >= 10,
        "G6 O-B isolable (only reserver and promoted claimant change) in at least half of owner changes":
            bool(changed) and 2 * len(unambiguous) >= len(changed),
        "G7 no implementation defect (no reconstruction inconsistency, no no-op with a supported action left)":
            audit.fidelity["reconstruction inconsistencies"] == 0 and not any(u["no_op"]["defect"] for u in no_op),
    }
    disposition = ("BLOCKED BY INSUFFICIENT REPLAY EVIDENCE" if not gate["G0 at least 30 reconstructable collision groups"]
                   else "DESIGN TARGET-ALLOCATION CANDIDATE" if all(gate.values())
                   else "NO TARGET-ALLOCATION EXPERIMENT JUSTIFIED")
    return {
        "schema": SCHEMA, "audit_id": AUDIT_ID,
        "baseline": {"identity": "baseline-v2", "policy_source_sha256": policy_source_digest(sources=V2_SOURCES)[0]},
        "registered_arm": registered_arm(),
        "fidelity": dict(sorted(audit.fidelity.items())), "decisions": dict(sorted(audit.decisions.items())),
        "population": {"collision_decisions": sum(v for k, v in audit.decisions.items() if k.endswith("with exclusions")),
                       "collision_groups": len(groups), "displaced_units": len(units),
                       "excluded_other_units": sum(g["excluded_other"] for g in groups),
                       "groups_by_corpus": hist(g["corpus"] for g in groups),
                       "displaced_by_corpus": hist(u["corpus"] for u in units)},
        "structure": {"claimants_per_group": hist(g["claimants"] for g in groups),
                      "eligible_per_group": hist(g["eligible"] for g in groups),
                      "components": len(audit.components),
                      "single_target_components": sum(1 for c in audit.components if c["targets"] == 1),
                      "targets_per_component": hist(c["targets"] for c in audit.components),
                      "shooters_per_component": hist(c["shooters"] for c in audit.components),
                      "by_configuration": {k: dict(sorted(v.items())) for k, v in sorted(by_config.items())}},
        "ownership": {"reserver_is_strongest_claimant": sum(1 for g in groups if g["reserver_is_max_claimant"]),
                      "reserver_weaker_than_a_claimant": sum(1 for g in groups if not g["reserver_is_max_claimant"]),
                      "groups_with_stronger_displaced": len(stronger),
                      "stronger_displaced_units": sum(g["stronger_displaced"] for g in groups),
                      "reserver_rank": hist(g["reserver_rank"] for g in groups),
                      "level_gap": hist(g["level_gap"] for g in groups),
                      "reserver_level": hist(g["reserver_level"] for g in groups),
                      "groups_tied_at_the_top": sum(1 for g in groups if g["tie_at_max"]),
                      "groups_with_stronger_eligible_non_claimant": sum(1 for g in groups
                                                                        if g["stronger_eligible_non_claimant"]),
                      "stronger_displaced_fallback": hist(u["fallback"] for u in units if u["stronger_than_reserver"])},
        "displaced": {"fallback": hist(u["fallback"] for u in units),
                      "fallback_by_corpus": {c: hist(u["fallback"] for u in units if u["corpus"] == c)
                                             for c in sorted({u["corpus"] for u in units})}},
        "no_op": {"units": len(no_op),
                  "shoot": hist(u["no_op"]["reasons"]["shoot"] for u in no_op),
                  "occupy": hist(u["no_op"]["reasons"]["occupy"] for u in no_op),
                  "move": hist(u["no_op"]["reasons"]["move"] for u in no_op),
                  "move_reason_equals_trace": sum(1 for u in no_op if u["no_op"]["reasons"]["move"]
                                                  == u["no_op"]["reasons"]["trace_move_reason"]),
                  "with_unsupported_listed_types": sum(1 for u in no_op if u["no_op"]["reasons"]["unsupported_types"]),
                  "unsupported_listed_types": hist(t for u in no_op for t in u["no_op"]["reasons"]["unsupported_types"]),
                  "free_shoot_candidates": sum(u["no_op"]["free_shoot_candidates"] for u in no_op),
                  "defects": sum(1 for u in no_op if u["no_op"]["defect"]),
                  "joint": hist(" | ".join((u["no_op"]["reasons"]["shoot"], u["no_op"]["reasons"]["occupy"],
                                            u["no_op"]["reasons"]["move"],
                                            "stronger than the reserver" if u["stronger_than_reserver"] else "not stronger"))
                                for u in no_op),
                  "by_configuration": hist(u["config"] for u in no_op)},
        "target_outcome": {"classes": hist(g["outcome"]["class"] for g in groups),
                           "by_stronger_displacement": hist(
                               f"{g['outcome']['class']} | {'stronger displaced' if g['stronger_displaced'] else 'none stronger'}"
                               for g in groups),
                           "by_fallback": hist(f"{g['outcome']['class']} | {u['fallback']}" for g in groups for u in units
                                               if (u["corpus"], u["game"], u["k"], u["seat"], u["target"])
                                               == (g["corpus"], g["game"], g["k"], g["seat"], g["target"])),
                           "reserving_shot": hist(g["outcome"].get("shot", "unavailable") for g in groups),
                           "reserving_shot_judged": sum(1 for g in groups if g["outcome"].get("judged")),
                           "groups_with_other_actions_on_target": sum(1 for g in groups
                                                                      if g["outcome"].get("other_actions_on_target"))},
        "follow_up": {"horizons": list(HORIZONS), "by_fallback": follow_up},
        "redirects": {"units": len(redirects),
                      "same_level": sum(1 for u in redirects if u["redirect"]["alternate_level"] == u["redirect"]["preferred_level"]),
                      "lower_level": sum(1 for u in redirects if u["redirect"]["alternate_level"] < u["redirect"]["preferred_level"]),
                      "level_drop": hist(u["redirect"]["preferred_level"] - u["redirect"]["alternate_level"] for u in redirects),
                      "outcome": hist(f"{u['redirect']['outcome']['class']} | {u['redirect']['outcome'].get('shot', 'unavailable')}"
                                      for u in redirects)},
        "oracle_b": {"groups": len(groups), "owner_unchanged": len(groups) - len(changed), "owner_changed": len(changed),
                     "unambiguous": len(unambiguous), "coupled_or_ambiguous": len(changed) - len(unambiguous),
                     "decisions_changed": len(decisions_changed),
                     "promoted_by": hist(g["oracle"]["promoted_by"] for g in changed),
                     "promoted_level_gain": hist(g["oracle"]["promoted_level_gain"] for g in unambiguous),
                     "former_owner_then": hist(g["oracle"]["former_owner"] for g in unambiguous),
                     "promoted_claimant_before": hist(g["oracle"]["promoted_previous"] for g in unambiguous),
                     "shot_delta": hist(g["oracle"]["shot_delta"] for g in unambiguous),
                     "non_shoot_changes": sum(g["oracle"]["non_shoot_changes"] for g in unambiguous),
                     "changed_units_when_coupled": hist(g["oracle"]["changed_units"] for g in changed
                                                        if not g["oracle"]["unambiguous"])},
        "situations": situations(groups, units),
        "gate": gate, "disposition": disposition,
    }


def build() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    audit = Audit()
    d1(audit)
    d2(audit)
    d3(audit)
    private = {"groups": audit.groups, "units": audit.units, "components": audit.components, "problems": audit.problems}
    return summarize(audit), private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    public, private = build()
    text = json.dumps(public, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("audit identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps(private, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}: {public['disposition']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
