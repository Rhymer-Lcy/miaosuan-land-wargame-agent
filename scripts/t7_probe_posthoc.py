"""POST HOC descriptions of the T7 mechanism probe, written after every registered verdict (they change none).

    python scripts/t7_probe_posthoc.py [--check]

Reads the three probe games (private records and captures under ``local/evaluation/t7-mechanism-probe-1/``) and the
registered analyses' private rows (``local/diagnostics/t7-probe/<game>-private.json``). Public aggregates only, in
``evaluation/t7-mechanism-probe-1/posthoc.json``:

1. the population of every order: unit class (type, sub_type) and the action types it listed at its order;
2. every baseline-v2 action of the candidate seat on an ordered unit after its order, by type (the population E3b
   and E5 would have needed);
3. E4's discriminating target-steps: the target's class, the nearest observer's class and distance, and the
   elevation difference;
4. the ambiguous aerial class: the nearest aerial observer's sub_type and distance band, and the listing.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import t7_probe as tp  # noqa: E402
from miaosuan_agent.evaluation import t7_probe_metrics as tm  # noqa: E402
from miaosuan_agent.evaluation import t7_visibility as tv  # noqa: E402
from miaosuan_agent import sdk_data  # noqa: E402

WORK = REPO_ROOT / "local" / "evaluation" / tp.PROBE_ID
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "t7-probe"
OUT = REPO_ROOT / "evaluation" / tp.PROBE_ID / "posthoc.json"
GAMES = (("P-A", tp.PA_GAME, "pa"), ("P-B1", tp.PB1_GAME, "pb1"), ("P-B2", tp.PB2_GAME, "pb2"))


def cls(u: Any) -> str:
    return f"type {u.type} sub_type {u.sub_type}"


def describe(probe: str, game_id: str, label: str) -> Dict[str, Any]:
    game = tm.load(WORK, game_id)
    private = json.loads((PRIVATE / f"{label}-private.json").read_text(encoding="utf-8"))
    snaps = tm.series(game)
    (seat,) = game.seats_of(tp.CANDIDATE_ID)
    scenario = game_id.split(".")[0]
    map_id = {"1910631192": "92", "2120531121": "21"}[scenario]
    inputs = sdk_data.load_inputs(WORK / "data" / scenario / "Data", scenario, map_id)
    m = tv.MapData(inputs.basic, inputs.see)
    out: Dict[str, Any] = {}
    orders = private["orders"]
    pop = collections.Counter()
    listed = collections.Counter()
    for o in orders:
        u = snaps[o["k"]].units[o["unit"]]
        pop[cls(u)] += 1
        listed[str(list(u.types or ()))] += 1
    out["orders_by_class"] = dict(sorted(pop.items()))
    out["listed_at_order"] = dict(sorted(listed.items()))
    ordered = {o["unit"]: o["k"] for o in orders}
    later = collections.Counter()
    for k in sorted(game.steps):
        for a in tm.submitted(game, seat, k):
            if a.get("obj_id") in ordered and k > ordered[a["obj_id"]] and not tm.is_order(a):
                later[str(a.get("type"))] += 1
    out["baseline_v2_actions_on_ordered_units_after_their_order"] = dict(sorted(later.items()))
    rows = private["E4_rows"]
    disc = collections.Counter()
    aerial = collections.Counter()
    for r in rows:
        snap = snaps[r["k"]]
        target = snap.units[r["target"]]
        if r["class"] == tv.DISCRIMINATING:
            obs = snap.units[r["nearest"][0]]
            elev = m.elev.get(obs.hex, 0) - m.elev.get(target.hex, 0)
            disc[f"target {cls(target)}; observer {cls(obs)}; distance {r['nearest'][1]}; observer higher by {elev}; "
                 f"listed {r['listed']}"] += 1
        elif r["class"] == tv.AMBIGUOUS_AIR:
            others = [u for u in snap.units.values() if u.color != target.color and u.on_map]
            pairs = [(tv.band(m, {"obj_id": u.obj_id, "type": u.type, "sub_type": u.sub_type, "cur_hex": u.hex},
                              {"obj_id": target.obj_id, "type": target.type, "sub_type": target.sub_type,
                               "cur_hex": target.hex}), u.sub_type) for u in others]
            relevant = (tv.INSIDE, tv.BETWEEN, tv.BOUNDARY)
            air = sorted({f"sub_type {s} {p.band}" for p, s in pairs if p.aerial and p.band in relevant})
            ground_close = any(not p.aerial and p.band == tv.INSIDE for p, _ in pairs)
            aerial[f"aerial observers within their normal distance: {'; '.join(air)}; ground observer within the "
                   f"concealed distance: {ground_close}; listed {r['listed']}"] += 1
    out["discriminating_target_steps"] = dict(sorted(disc.items()))
    out["ambiguous_aerial_target_steps"] = dict(sorted(aerial.items()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = {"schema": "miaosuan-t7-probe-posthoc/1", "probe_id": tp.PROBE_ID,
               "status": "POST HOC: written after every registered verdict; it changes none",
               "games": {probe: describe(probe, game_id, label) for probe, game_id, label in GAMES}}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("posthoc identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
