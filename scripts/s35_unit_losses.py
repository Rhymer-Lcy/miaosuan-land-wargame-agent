"""Sprint 35: where and under which task the Sprint 34 candidate's ground units were destroyed (post hoc, read-only).

    python scripts/s35_unit_losses.py [--work DIR] [--out FILE] [--workers N]

For each own ground unit (passengers included) of the candidate seat that disappears from the all-seeing compact
timeline in the 16 Stage A games, records at its last observed step: class and value; whether it was aboard a carrier,
moving, or standing; whether it stood in an objective's zone (held by its side or not); the candidate's plan for it
(module and task kind) in the last recorded decision; own and enemy ground units within 3 hexes (truth); visible enemy
ground units within 8 hexes in the seat's own observation 75 steps before; and how many own ground units shared its hex
(stacking). It also counts the opponent's destroyed units, so that the exchange can be read per scenario and side.
Aggregates only in the output; descriptive, post hoc.
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

CLASS = {0: "tank", 1: "ifv", 2: "squad", 3: "artillery", 4: "ugv"}


def _cards():
    spec = importlib.util.spec_from_file_location("s35u_cards", REPO_ROOT / "scripts" / "build_s34_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def one(job) -> Dict[str, Any]:
    from miaosuan_agent.boundary import Observation, Origin
    from miaosuan_agent.evaluation import s34_live as sl
    from miaosuan_agent.integrated import facts as F
    from miaosuan_agent.integrated.world import build_world
    work, game = job
    colour = 0 if sl.CANDIDATE_SIDE[game["condition"]] == "red" else 1
    seat = 1 if colour == 0 else 11
    compact = json.loads((Path(work) / "capture" / f"{game['game_id']}.timeline.json").read_text(encoding="utf-8"))
    steps = [s for s in compact["steps"] if s["k"] >= 0]
    windows = pickle.load(open(Path(work) / "capture" / f"{game['game_id']}.timeline.pkl", "rb"))
    samples = {s["cur_step"]: s for s in windows["samples"]}
    out = collections.Counter()
    enemy_lost = collections.Counter()
    own_lost_value = 0.0
    enemy_lost_value = 0.0
    last_row: Dict[int, Any] = {}
    last_index: Dict[int, int] = {}
    for i, s in enumerate(steps):
        ids = set()
        for r in s["units"]:
            if r[2] in (1, 2):
                ids.add(r[0])
                last_row[r[0]] = r
                last_index[r[0]] = i
        for uid, r in list(last_row.items()):
            if uid in ids or last_index[uid] != i - 1:
                continue
            # destroyed between steps i-1 and i
            if r[1] != colour:
                enemy_lost[CLASS.get(r[3], "other")] += 1
                enemy_lost_value += r[8] or 0
                continue
            own_lost_value += r[8] or 0
            prev = steps[i - 1]
            cls = CLASS.get(r[3], "other")
            if r[9]:
                where = "aboard"
            else:
                held = [c for c, f, _ in prev["cities"] if r[4] in F.zone(c)]
                flags = {c: f for c, f, _ in prev["cities"]}
                if held:
                    where = "objective zone held" if any(flags[c] == colour for c in held) else "objective zone not held"
                else:
                    where = "elsewhere"
                where += ", moving" if r[5] else ", standing"
            plan = "no plan recorded"
            for back in range(0, 4):
                sample = samples.get(prev["cur_step"] - back)
                snap = sample["seats"].get(str(seat)) if sample else None
                for p in (snap.get("plans") or ()) if snap else ():
                    if p[0] == r[0]:
                        plan = f"{p[1]}/{p[2]}"
                if plan != "no plan recorded":
                    break
            hex_ = r[4] if not r[9] else next((x[4] for x in prev["units"] if x[0] == r[4]), None)
            own3 = enemy3 = stacked = 0
            if hex_ is not None and not r[9]:
                own3 = sum(1 for x in prev["units"] if x[1] == colour and x[2] in (1, 2) and not x[9]
                           and F.hex_distance(x[4], hex_) <= 3)
                enemy3 = sum(1 for x in prev["units"] if x[1] == 1 - colour and x[2] in (1, 2) and not x[9]
                             and F.hex_distance(x[4], hex_) <= 3)
                stacked = sum(1 for x in prev["units"] if x[1] == colour and x[2] in (1, 2) and not x[9] and x[4] == hex_)
            seen8 = None
            sample = samples.get(max(0, prev["cur_step"] - 75))
            snap = sample["seats"].get(str(seat)) if sample else None
            if snap and hex_ is not None:
                world = build_world(Observation.from_raw(pickle.loads(snap["observation"]), Origin.ENGINE), seat, colour,
                                    100, 100)
                seen8 = sum(1 for e in world.enemies if e.ground and F.hex_distance(e.hex, hex_) <= 8)
            out[("class", cls)] += 1
            out[("where", where)] += 1
            out[("plan", plan)] += 1
            out[("local_ratio", "enemy>own" if enemy3 > own3 else "enemy<=own")] += 1
            out[("stacked", "alone" if stacked <= 1 else "stacked")] += 1
            out[("seen8_75_before", "none" if not seen8 else "1-2" if seen8 <= 2 else "3+")] += 1
    return {"position": game["position"], "scenario_id": game["scenario_id"], "side": sl.CANDIDATE_SIDE[game["condition"]],
            "own": {f"{a}: {b}": n for (a, b), n in sorted(out.items())},
            "own_lost": sum(n for (a, _), n in out.items() if a == "class"), "own_lost_value": own_lost_value,
            "enemy_lost": sum(enemy_lost.values()), "enemy_lost_value": enemy_lost_value,
            "enemy_lost_by_class": dict(sorted(enemy_lost.items()))}


def main() -> int:
    from miaosuan_agent.evaluation import s34_live as sl
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "evaluation" / "s35-coalition-agent" / "unit-losses.json")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    cards = _cards()
    games = [g for g in sl.schedule(cards.CANDIDATE_ID) if g["stage"] == "A"]
    with mp.Pool(args.workers) as pool:
        results = sorted(pool.map(one, [(str(args.work), g) for g in games]), key=lambda r: r["position"])
    total = collections.Counter()
    for r in results:
        total.update(r["own"])
    by = collections.defaultdict(lambda: collections.Counter())
    for r in results:
        key = f"{r['scenario_id']} {r['side']}"
        by[key]["own_lost"] += r["own_lost"]
        by[key]["enemy_lost"] += r["enemy_lost"]
        by[key]["own_lost_value"] += r["own_lost_value"]
        by[key]["enemy_lost_value"] += r["enemy_lost_value"]
    payload = {"schema": "miaosuan-s35-unit-losses/1", "own_losses_total": dict(sorted(total.items())),
               "by_scenario_side": {k: dict(v) for k, v in sorted(by.items())},
               "note": "post hoc, descriptive; truth from the all-seeing compact timeline, plans from the candidate's "
                       "recorded trace, seen from the candidate seat's own observation"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
