"""Publish the aggregates of the Sprint 36 reconstruction (``docs/SPRINT36_TACTICAL_RECOVERY.md`` sections 5, 8 and 9).

    python scripts/s36_episodes.py --s34 FILE --s35 FILE [--check]

Reads the private outputs of ``scripts/s36_reconstruct.py`` for the 24 Sprint 34 and the 19 Sprint 35 live games (policy
under test re-decided with its own memory chain; shadows ``S34-MO`` and ``CM``) and writes
``evaluation/s36-tactical-recovery/reconstruction.json``: fidelity per game, held-objective losses by the fate of the
last standing defenders, the Sprint 35 candidate's stance 150 steps before each loss, enemy ground units in the zone at
the loss, destroyed own ground units by place and plan, every halted run by cause, guided-fire listings and use, and the
first decision difference of the two policies in the three blue configurations Sprint 35 regressed in. Counts and steps
only: no unit id, hex or coordinate. ``--check`` regenerates and compares byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "s36-tactical-recovery" / "reconstruction.json"
REGRESSIONS = (("s35", 12, 11), ("s35", 15, 16), ("s35", 4, 3))


def loss_category(loss: Dict[str, Any]) -> str:
    fates = loss["last_defenders"]
    if not fates:
        return "no standing defender within 1800 steps"
    if all(f["fate"] == "destroyed" for f in fates):
        return "last defenders destroyed"
    return "last defender left alive"


def build(s34: List[Dict[str, Any]], s35: List[Dict[str, Any]]) -> Dict[str, Any]:
    games = [("s34", r) for r in s34] + [("s35", r) for r in s35]
    if len(s34) != 24 or len(s35) != 19:
        raise SystemExit(f"expected 24 and 19 reconstructed games, found {len(s34)} and {len(s35)}")
    fidelity = {f"{card} p{r['position']:02d}": [r["fidelity"]["decisions"], r["fidelity"]["differing"]]
                for card, r in games}
    losses: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    destroyed: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    stage_a_games = collections.Counter()
    for card, r in games:
        if r["condition"] not in ("H1", "H2"):
            continue
        policy = r["policy"]
        stage_a_games[policy] += 1
        for loss in r["losses"]:
            c = losses[policy]
            c["losses"] += 1
            c[loss_category(loss)] += 1
            window = loss["windows"]["150"]["stance"]
            if policy == "CM":
                c[f"stance 150 steps before: {window['stance'] if window else 'none'}"] += 1
            c[f"enemy ground units in the zone at the loss: {min(3, len(loss['windows']['0']['enemy_in_zone']))}"] += 1
        for d in r["destroyed"]:
            c = destroyed[policy]
            c["all"] += 1
            c[d["where"]] += 1
            plan = d["plan"] or [None, None]
            if d["where"] == "in zone" and plan[0] == "coalition" and plan[1] == "hold":
                c[f"in zone kept by the stance: {d['stance']}"] += 1
    halts = []
    for card, r in games:
        for w in r["waits"]:
            halts.append({"game": f"{card} p{r['position']:02d}", "policy": r["policy"], "length": w["length"],
                          "causes": dict(sorted(w["causes"].items()))})
    guided = {f"{card} p{r['position']:02d}": dict(r["guided"], policy=r["policy"], condition=r["condition"])
              for card, r in games}
    first = {}
    by = {(card, r["position"]): r for card, r in games}
    for card, cand, ctrl in REGRESSIONS:
        r = by[(card, cand)]
        diff = r["first_difference"].get("S34-MO")
        first[f"{r['scenario_id']} {r['condition']} p{cand:02d}"] = {
            "first_difference_step": diff["step"] if diff else None,
            "candidate_modules": sorted({p[0] for p in diff["tested"] if p}) if diff else [],
            "shadow_modules": sorted({p[0] for p in diff["shadow"] if p}) if diff else []}
    return {"schema": "miaosuan-s36-reconstruction/1",
            "evidence": "historical descriptive: recorded games re-decided with each policy's own memory chain",
            "fidelity": fidelity,
            "fidelity_total": {"games": len(fidelity), "decisions": sum(v[0] for v in fidelity.values()),
                               "differing": sum(v[1] for v in fidelity.values())},
            "stage_a_games": dict(stage_a_games),
            "losses": {k: dict(sorted(v.items())) for k, v in sorted(losses.items())},
            "destroyed": {k: dict(sorted(v.items())) for k, v in sorted(destroyed.items())},
            "halted_runs": halts, "guided": guided, "first_difference": first}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--s34", type=Path, required=True)
    parser.add_argument("--s35", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build(json.loads(args.s34.read_text(encoding="utf-8")), json.loads(args.s35.read_text(encoding="utf-8")))
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("reconstruction identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({k: data[k] for k in ("fidelity_total", "stage_a_games", "losses", "destroyed")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
