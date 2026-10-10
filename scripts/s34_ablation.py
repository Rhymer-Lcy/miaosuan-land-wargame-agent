"""Sprint 34 engine-free ablation on the live games' authentic observations (``docs/SPRINT34_INTEGRATED_AGENT.md``).

    python scripts/s34_ablation.py [--work DIR] [--out FILE] [--workers N]

For every played game of the live card, the candidate seat's recorded observations (``*.timeline.pkl``) are re-decided,
decision by decision, by each ablation of the live variant and by the other architecture (``CT``), each with its own
memory chain. Reported per configuration: the first decision whose actions differ from the live candidate's, the
number of decisions whose actions differ, and, among the units whose action differs, the live candidate's module for
that unit. Before a configuration's first divergence it saw exactly the states it would have seen; after it, the
states come from the live candidate's trajectory, so later differences are action-level facts only, never outcomes.
Aggregates to ``evaluation/s34-integrated-live-1/ablation.json``.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import multiprocessing as mp
import pickle
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

CONFIGS = ("CT", "mo-no-transport", "mo-no-artillery", "mo-no-threat-routing", "mo-no-economy", "mo-no-recovery")


def _key(action) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True)


def one(job) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.evaluation import s34_live as sl
    from miaosuan_agent.integrated.agent import CommanderAgent
    from miaosuan_agent.integrated.config import VARIANTS
    work, game, data_root, map_id = job
    windows = pickle.load(open(Path(work) / "capture" / f"{game['game_id']}.timeline.pkl", "rb"))
    colour = 0 if sl.CANDIDATE_SIDE[game["condition"]] == "red" else 1
    seat = 1 if colour == 0 else 11
    inputs = sdk_data.load_inputs(Path(data_root), game["scenario_id"], map_id)
    agents = {}
    for name in CONFIGS:
        agent = CommanderAgent(VARIANTS[name])
        agent.setup({"seat": seat, "faction": colour, "cost_data": inputs.cost})
        agents[name] = agent
    out = {name: {"first_divergence_step": None, "decisions_differing": 0, "units_differing_by_live_module":
                  collections.Counter()} for name in CONFIGS}
    decisions = 0
    for sample in sorted(windows["samples"], key=lambda s: s["k"]):
        snap = sample["seats"].get(str(seat))
        if snap is None:
            continue
        decisions += 1
        raw = pickle.loads(snap["observation"])
        live = {a.get("obj_id"): _key(a) for a in snap["submitted"]}
        plans = {p[0]: p[1] for p in snap.get("plans") or ()}
        for name, agent in agents.items():
            mine = {a.get("obj_id"): _key(a) for a in agent.step(raw)}
            if mine != live:
                r = out[name]
                r["decisions_differing"] += 1
                if r["first_divergence_step"] is None:
                    r["first_divergence_step"] = sample["cur_step"]
                for unit in set(mine) | set(live):
                    if mine.get(unit) != live.get(unit):
                        r["units_differing_by_live_module"][plans.get(unit, "outside the plans")] += 1
    for r in out.values():
        r["units_differing_by_live_module"] = dict(sorted(r["units_differing_by_live_module"].items()))
    return {"position": game["position"], "condition": game["condition"], "scenario_id": game["scenario_id"],
            "decisions": decisions, "configs": out}


def main() -> int:
    from miaosuan_agent.evaluation import s34_live as sl
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "local" / "s34-data" / "Data")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "evaluation" / sl.CARD_ID / "ablation.json")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("abl_cards", REPO_ROOT / "scripts" / "build_s34_card.py")
    cards = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cards)
    card = json.loads(cards.CARD.read_text(encoding="utf-8"))
    maps = {s["scenario_id"]: s["map_id"] for s in card["scenarios"]}
    games = [g for g in sl.schedule(cards.CANDIDATE_ID) if (args.work / "capture" / f"{g['game_id']}.timeline.pkl").exists()]
    jobs = [(str(args.work), g, str(args.data), maps[g["scenario_id"]]) for g in games]
    with mp.Pool(args.workers) as pool:
        results = sorted(pool.map(one, jobs), key=lambda r: r["position"])
    payload = {"schema": "miaosuan-s34-ablation/1", "configs": list(CONFIGS), "games": results,
               "note": "action-level re-decisions of the live candidate's recorded observations; no outcome is implied"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(results)} games")
    return 0


if __name__ == "__main__":
    sys.exit(main())
