"""Structural analysis for the target-ownership design study (``target-ownership-design-1``).

    python scripts/analyze_ownership_design.py [--check]

No engine and no policy change. The population and its verification are exactly the target-allocation audit's: the
same loaders (``scripts/audit_target_allocation.py``: D1 baseline-v2 snapshots reproduced exactly, D2 baseline-v0
replay decisions with every baseline-v2 difference explained, D3 baseline-v1 captured decisions) feed every verified
baseline-v2 decision to ``miaosuan_agent.evaluation.ownership_design``, which builds the shoot graph, classifies its
components (S1, S2, S3), applies the designed ownership rule to S1 components only, runs the S1 oracle where the
owner would change, and fingerprints collision components. The public output holds aggregate counts and
fingerprint hashes only; ``--check`` rebuilds it and compares.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.boundary import MoveCosts  # noqa: E402
from miaosuan_agent.decision import Memory  # noqa: E402
from miaosuan_agent.evaluation import allocation_audit as aa  # noqa: E402
from miaosuan_agent.evaluation import ownership_design as od  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

STUDY_ID = "target-ownership-design-1"
OUT = REPO_ROOT / "evaluation" / STUDY_ID / "analysis.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "ownership" / "analysis-private.json"
SCHEMA = "miaosuan-target-ownership-design-analysis/1"
#: Corpora holding every decision of their games (the replay corpus). D1 and D3 hold captured decisions only, so a
#: game-level interval over them would describe the captures, not the games.
COMPLETE_GAMES = ("D2",)


def load_audit() -> Any:
    spec = importlib.util.spec_from_file_location("audit_target_allocation",
                                                  REPO_ROOT / "scripts" / "audit_target_allocation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hist(values: Any) -> Dict[str, int]:
    return {str(k): v for k, v in sorted(collections.Counter(values).items(), key=lambda kv: (isinstance(kv[0], str), kv[0]))}


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> Tuple[float, float]:
    """Exact binomial interval by bisection on the binomial tail (no third-party dependency)."""
    def tail_ge(p: float) -> float:
        return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(x, n + 1))

    def tail_le(p: float) -> float:
        return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(0, x + 1))

    def solve(f: Any, target: float, increasing: bool) -> float:
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
    return round(low, 4), round(high, 4)


class Collector:
    """Receives every verified baseline-v2 decision from the audit's loaders."""

    def __init__(self) -> None:
        self.fidelity: collections.Counter = collections.Counter()
        self.decisions: collections.Counter = collections.Counter()
        self.components: List[Dict[str, Any]] = []
        self.groups: List[Dict[str, Any]] = []
        self.problems: List[Dict[str, Any]] = []
        self.games: Dict[str, set] = collections.defaultdict(set)

    def decision(self, where: Dict[str, Any], raw: Mapping[str, Any], seat: int, faction: int, v2: Any, costs: MoveCosts,
                 memory: Memory, outcome: Any = None) -> None:
        self.decisions[where["corpus"]] += 1
        self.games[where["corpus"]].add(where["game"])
        order, graph = od.shoot_graph(raw, seat, faction)
        comps = od.components(order, graph)
        traced = [u.obj_id for u in v2.trace.units]
        if traced and traced != order:
            self.problems.append({**where, "problem": "processing order differs from the trace"})
        if not traced:  # deployment decisions carry no unit decisions; they must have no shoot edge either
            self.fidelity["decisions without unit decisions"] += 1
            if graph:
                self.problems.append({**where, "problem": "a decision without unit decisions has shoot edges"})
        groups = aa.collision_groups(raw, v2)
        component_of = {t: i for i, c in enumerate(comps) for t in c.targets}
        records = {e["obj_id"]: e for e in v2.trace.to_dict().get("shoot_reserved", [])}
        collided = {component_of[g.target] for g in groups}
        stronger = {component_of[g.target] for g in groups if g.metrics()["stronger_displaced"]}
        for i, comp in enumerate(comps):
            row = {**where, "kind": comp.kind, "shooters": len(comp.shooters), "targets": len(comp.targets),
                   "edges": comp.edges, "collision": i in collided, "lower_attack_reserver": i in stronger}
            if comp.kind in ("S1", "S2"):
                row["fingerprint"] = od.fingerprint(where["config"], raw, seat, faction, comp, graph)
                row["identity"] = [where["corpus"], where["game"], seat, list(comp.shooters), list(comp.targets)]
            if comp.kind == "S1":
                target = comp.targets[0]
                for later in comp.shooters[1:]:
                    record = records.get(later)
                    if (record is None or record["effect"] == "unchanged"
                            or {e["target_obj_id"] for e in record["excluded"]} != {target}
                            or any(e["reserved_by"] != comp.shooters[0] for e in record["excluded"])):
                        self.problems.append({**where, "problem": "an S1 shooter after the first is not displaced by it"})
                result = od.s1_oracle(raw, seat, faction, v2, comp, graph, lambda: ShootReservationPolicy(costs), memory)
                if not result["baseline_owner_shot_emitted"]:
                    self.problems.append({**where, "problem": "the first S1 shooter's shot at the target was not emitted"})
                if result["owner_changed"]:
                    again = od.s1_oracle(raw, seat, faction, v2, comp, graph, lambda: ShootReservationPolicy(costs), memory)
                    self.fidelity["S1 oracle repeated runs differing"] += again != result
                row["s1"] = result
            elif comp.kind == "S2" and i in collided:
                row["s2"] = "fallback to baseline-v2"
            self.components.append(row)
        for g in groups:
            m = g.metrics()
            self.groups.append({**where, "kind": comps[component_of[g.target]].kind,
                                "stronger_displaced": m["stronger_displaced"] > 0,
                                "identity": [where["corpus"], where["game"], seat, g.target,
                                             sorted(e["unit"] for e in g.eligible)],
                                "fingerprint": od.fingerprint(where["config"], raw, seat, faction,
                                                              comps[component_of[g.target]], graph)})
        self.fidelity["consistency problems"] = len(self.problems)


def level_summary(collector: Collector) -> Dict[str, Any]:
    """Raw group, distinct situation, game and configuration levels of the ownership-mismatch phenomenon."""
    groups = collector.groups
    games_all = collector.games
    out: Dict[str, Any] = {}
    for corpus in sorted({g["corpus"] for g in groups} | set(games_all)):
        gs = [g for g in groups if g["corpus"] == corpus]
        mismatch = [g for g in gs if g["stronger_displaced"]]
        ident = {json.dumps(g["identity"]) for g in gs}
        ident_mis = {json.dumps(g["identity"]) for g in mismatch}
        fps = {g["fingerprint"] for g in gs}
        fps_mis = {g["fingerprint"] for g in mismatch}
        games_coll = {g["game"] for g in gs}
        games_mis = {g["game"] for g in mismatch}
        configs = {g["config"] for g in gs}
        configs_mis = {g["config"] for g in mismatch}
        per_game = collections.Counter(g["game"] for g in mismatch)
        out[corpus] = {
            "groups": len(gs), "mismatch_groups": len(mismatch),
            "identity_situations": len(ident), "identity_situations_with_mismatch": len(ident_mis),
            "fingerprints": len(fps), "fingerprints_with_mismatch": len(fps_mis),
            "games_in_corpus": len(games_all[corpus]), "games_with_a_collision": len(games_coll),
            "games_with_a_mismatch": len(games_mis),
            "configurations_with_a_collision": len(configs), "configurations_with_a_mismatch": len(configs_mis),
            "mismatch_groups_per_affected_game": sorted(per_game.values(), reverse=True),
            "complete_games": corpus in COMPLETE_GAMES,
            "game_prevalence_exact_95": clopper_pearson(len(games_mis), len(games_all[corpus]))
            if corpus in COMPLETE_GAMES and games_all[corpus] else None,
        }
    return out


def summarize(collector: Collector, d1_steps: int) -> Dict[str, Any]:
    comps, groups = collector.components, collector.groups
    s1 = [c for c in comps if c["kind"] == "S1"]
    changed = [c for c in s1 if c["s1"]["owner_changed"]]
    by_key = collections.Counter(c["s1"]["key"] for c in s1)
    collision_comps = [c for c in comps if c["collision"]]
    fp_occ: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for c in collision_comps:
        fp_occ[c["fingerprint"]].append(c)
    id_occ = collections.Counter(json.dumps(c["identity"]) for c in collision_comps)
    mismatch_comps = [c for c in collision_comps if c["lower_attack_reserver"]]
    stronger_groups = [g for g in groups if g["stronger_displaced"]]
    retained = [g for g in stronger_groups if g["kind"] == "S1"]
    return {
        "schema": SCHEMA, "study_id": STUDY_ID,
        "baseline": {"identity": "baseline-v2",
                     "policy_source_sha256": policy_source_digest(sources=load_audit().V2_SOURCES)[0]},
        "fidelity": dict(sorted(collector.fidelity.items())),
        "decisions": dict(sorted(collector.decisions.items())),
        "d1_coverage": {"captured_decisions": collector.decisions.get("D1", 0), "policy_seat_steps": d1_steps},
        "graph": {
            "components_by_kind": hist(c["kind"] for c in comps),
            "components_by_kind_and_corpus": hist(f"{c['corpus']} {c['kind']}" for c in comps),
            "decisions_with_kind": {k: len({(c["corpus"], c["game"], c["k"], c["seat"]) for c in comps if c["kind"] == k})
                                    for k in od.KINDS},
            "s1_shooters": hist(c["shooters"] for c in s1),
            "s2_shape": hist(f"{c['shooters']} shooters, {c['targets']} targets" for c in comps if c["kind"] == "S2"),
            "collision_components_by_kind": hist(c["kind"] for c in collision_comps),
            "s2_with_a_collision": sum(1 for c in comps if c.get("s2")),
        },
        "s1": {
            "components": len(s1), "key": dict(sorted(by_key.items())),
            "lower_attack_level_owner": sum(1 for c in s1 if c["s1"]["key"] == "higher attack level"),
            "gate_precheck_failures": sum(1 for c in s1 if c["s1"].get("fallback")),
            "owner_changed": len(changed),
            "simple": sum(1 for c in changed if c["s1"]["simple"]),
            "designated_owner_shoots_target": sum(1 for c in changed if c["s1"]["designated_owner_shoots_target"]),
            "level_gain": hist(c["s1"]["level_gain"] for c in changed),
            "former_owner_then": hist(c["s1"]["former_owner_then"] for c in changed),
            "designated_owner_before": hist(c["s1"]["designated_owner_before"] for c in changed),
            "shot_delta": hist(c["s1"]["shot_delta"] for c in changed),
            "non_shoot_changes": sum(c["s1"]["non_shoot_changes"] for c in changed),
            "changed_units": hist(c["s1"]["changed_units"] for c in changed),
            "earlier_non_owners": hist(c["s1"]["earlier_non_owners"] for c in changed),
            "later_non_owners": hist(c["s1"]["later_non_owners"] for c in changed),
            "decisions_changed": len({(c["corpus"], c["game"], c["k"], c["seat"]) for c in changed}),
            "games_changed": len({(c["corpus"], c["game"]) for c in changed}),
            "identity_situations_changed": len({json.dumps(c["identity"]) for c in changed}),
            "fingerprints_changed": len({c["fingerprint"] for c in changed}),
            "by_corpus": hist(c["corpus"] for c in changed),
        },
        "historical_mismatch_groups": {
            "groups": len(stronger_groups), "by_kind": hist(g["kind"] for g in stronger_groups),
            "retained_identity_situations": len({json.dumps(g["identity"]) for g in retained}),
            "retained_games": len({(g["corpus"], g["game"]) for g in retained}),
            "excluded_identity_situations": len({json.dumps(g["identity"]) for g in stronger_groups if g["kind"] != "S1"}),
            "excluded_games": len({(g["corpus"], g["game"]) for g in stronger_groups if g["kind"] != "S1"}),
        },
        "situations": {
            "collision_groups": len(groups), "collision_components": len(collision_comps),
            "identity_situations": len(id_occ), "fingerprints": len(fp_occ),
            "fingerprint_game_pairs": len({(fp, c["corpus"], c["game"]) for fp, cs in fp_occ.items() for c in cs}),
            "fingerprint_multiplicity": hist(len(cs) for cs in fp_occ.values()),
            "repeated_fingerprints": sum(1 for cs in fp_occ.values() if len(cs) > 1),
            "fingerprints_with_a_lower_attack_reserver": len({c["fingerprint"] for c in mismatch_comps}),
            "games_with_a_lower_attack_reserver": len({(c["corpus"], c["game"]) for c in mismatch_comps}),
            "fingerprints_by_kind": hist(cs[0]["kind"] for cs in fp_occ.values()),
            "mismatch_fingerprints_by_kind": hist(c["kind"] for c in
                                                  {c["fingerprint"]: c for c in mismatch_comps}.values()),
            "fingerprints_spanning_games": sum(1 for cs in fp_occ.values() if len({(c["corpus"], c["game"]) for c in cs}) > 1),
        },
        "levels": level_summary(collector),
    }


def d1_policy_steps(audit: Any) -> int:
    manifest = json.loads((REPO_ROOT / "evaluation" / audit.rd.DIAGNOSTIC_ID / "manifest.json").read_text(encoding="utf-8"))
    return sum(len(json.loads((audit.D1 / "capture" / f"{g['game_id']}.capture.json").read_text(encoding="utf-8"))["steps"])
               for g in manifest["games"])


def build() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    audit = load_audit()
    collector = Collector()
    audit.d1(collector)
    audit.d2(collector)
    audit.d3(collector)
    public = summarize(collector, d1_policy_steps(audit))
    return public, {"components": [c for c in collector.components if c["kind"] != "S3"], "groups": collector.groups,
                    "problems": collector.problems}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    public, private = build()
    text = json.dumps(public, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("analysis identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps(private, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
