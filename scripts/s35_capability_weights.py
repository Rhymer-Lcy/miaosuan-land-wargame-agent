"""Sprint 35: empirical class capability from recorded engine games (aggregates only, read-only).

    python scripts/s35_capability_weights.py [--work DIR] [--out FILE]

Reads the compact all-seeing timelines of the 24 Sprint 34 live games (both seats: the Sprint 34 candidate and
``baseline-v2`` or the inert control) and tabulates, per ground unit class (sub_type),

* exposure: unit-steps alive on the map (passengers excluded);
* direct fire dealt: judge records of type direct fire by an attacker of the class, records with damage, damage sum;
* damage received by the class from direct and indirect fire;

and the derived rate ``damage dealt per 1,000 alive unit-steps``. The rate describes how much damage units of a class
did as these two policies used them on these scenarios; it is not a kill probability and is not a property of the
engine alone. Sprint 35 uses it only to weight classes relative to each other in a bounded local force estimate
(``integrated/coalition.py``), with the weights frozen in source and their derivation recorded here.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

DIRECT, INDIRECT = "直瞄射击", "间瞄伤害"
CLASS = {0: "tank", 1: "ifv", 2: "squad", 3: "artillery", 4: "ugv", 5: "uav", 6: "helicopter", 7: "loitering"}


def main() -> int:
    from miaosuan_agent.evaluation import s34_live as sl
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "evaluation" / "s35-coalition-agent" / "capability.json")
    args = parser.parse_args()
    exposure = collections.Counter()
    dealt_records = collections.Counter()
    dealt_hits = collections.Counter()
    dealt_damage = collections.Counter()
    received = collections.Counter()
    games = 0
    for path in sorted((args.work / "capture").glob("*.timeline.json")):
        compact = json.loads(path.read_text(encoding="utf-8"))
        games += 1
        seen = set()
        for step in compact["steps"]:
            for r in step["units"]:
                if r[2] in (1, 2) and not r[9]:
                    exposure[CLASS.get(r[3], "other")] += 1
            for j in step.get("judge") or ():
                key = json.dumps(j, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    continue
                seen.add(key)
                damage = max(0, j.get("damage") or 0)
                target = CLASS.get(j.get("target_sub_type"), "other")
                received[(target, "direct" if j.get("type") == DIRECT else "indirect" if j.get("type") == INDIRECT
                          else "other")] += damage
                if j.get("type") == DIRECT:
                    attacker = CLASS.get(j.get("attack_sub_type"), "other")
                    dealt_records[attacker] += 1
                    dealt_hits[attacker] += int(damage > 0)
                    dealt_damage[attacker] += damage
    rate = {c: round(1000.0 * dealt_damage[c] / exposure[c], 4) for c in sorted(exposure) if exposure[c]}
    payload = {"schema": "miaosuan-s35-capability/1", "games": games,
               "exposure_unit_steps": dict(sorted(exposure.items())),
               "direct_fire_records": dict(sorted(dealt_records.items())),
               "direct_fire_records_with_damage": dict(sorted(dealt_hits.items())),
               "direct_fire_damage": dict(sorted(dealt_damage.items())),
               "damage_received": {f"{a} {b}": v for (a, b), v in sorted(received.items())},
               "direct_damage_per_1000_alive_unit_steps": rate,
               "note": "descriptive rates of these policies on these scenarios, not kill probabilities"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
                        newline="\n")
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
