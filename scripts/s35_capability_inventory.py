"""Sprint 35: which actions the engine listed, for which unit classes, in the recorded Sprint 34 live games.

    python scripts/s35_capability_inventory.py [--work DIR] [--out FILE] [--workers N]

Reads every seat's pickled observation of the 24 Sprint 34 live games and counts, per scenario, stage and own unit
class (type and sub_type), the unit-decisions in which each action type was listed, and per scenario and seat the
action types the seat submitted (from the recorded submissions). Aggregates only. This is the listing-frequency column
of the Sprint 35 capability inventory (``docs/SPRINT35_COALITION_AGENT.md``); a listed action is not an executed one.
"""

from __future__ import annotations

import argparse
import collections
import json
import multiprocessing as mp
import pickle
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

SUB = {0: "tank", 1: "ifv", 2: "squad", 3: "artillery", 4: "ugv", 5: "uav", 6: "helicopter", 7: "loitering",
       8: "transport_helicopter"}


def one(path: str) -> Dict[str, Any]:
    windows = pickle.load(open(path, "rb"))
    scenario = Path(path).name.split(".")[0]
    listed = collections.Counter()
    submitted = collections.Counter()
    for sample in windows["samples"]:
        for seat, snap in sample["seats"].items():
            raw = pickle.loads(snap["observation"])
            stage = raw["time"]["stage"]
            subs = {}
            for o in list(raw.get("operators") or ()) + list(raw.get("passengers") or ()):
                if o.get("color") == (0 if seat == "1" else 1):
                    subs[o["obj_id"]] = SUB.get(o.get("sub_type"), f"sub{o.get('sub_type')}")
            for obj_id, actions in (raw.get("valid_actions") or {}).items():
                cls = subs.get(int(obj_id), "seat-level")
                for t in actions:
                    listed[(scenario, stage, cls, int(t))] += 1
            for a in snap.get("submitted") or ():
                submitted[(scenario, seat, stage, int(a.get("type", -1)))] += 1
    return {"listed": [[*k, v] for k, v in listed.items()], "submitted": [[*k, v] for k, v in submitted.items()]}


def main() -> int:
    from miaosuan_agent.evaluation import s34_live as sl
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "evaluation" / "s35-coalition-agent" / "capability-inventory.json")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    paths = sorted(str(p) for p in (args.work / "capture").glob("*.timeline.pkl"))
    with mp.Pool(args.workers) as pool:
        parts = pool.map(one, paths)
    listed = collections.Counter()
    submitted = collections.Counter()
    for part in parts:
        for *k, v in part["listed"]:
            listed[tuple(k)] += v
        for *k, v in part["submitted"]:
            submitted[tuple(k)] += v
    by_scenario: Dict[str, Any] = {}
    for (scenario, stage, cls, t), v in sorted(listed.items(), key=lambda kv: str(kv[0])):
        by_scenario.setdefault(scenario, {}).setdefault(f"stage {stage}", {}).setdefault(cls, {})[str(t)] = v
    subs: Dict[str, Any] = {}
    for (scenario, seat, stage, t), v in sorted(submitted.items(), key=lambda kv: str(kv[0])):
        subs.setdefault(scenario, {}).setdefault(f"seat {seat}", {}).setdefault(f"stage {stage}", {})[str(t)] = v
    payload = {"schema": "miaosuan-s35-capability-inventory/1", "games": len(paths),
               "unit_decisions_listing_type": by_scenario, "submitted_actions": subs,
               "note": "listing counts from both seats' recorded observations of the Sprint 34 live games; "
                       "seat-level = options not attached to an own unit"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload, indent=1)[:9000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
