"""Rapid tactical capability census for Tactical Frontier Sprint 1 (``tactical-frontier-1``). Aggregates only.

    python scripts/tactical_census.py [--check]

Private inputs (git-ignored): the SDK archive's nested ``Data.zip`` (the 50 historical scenarios, read in memory)
and the routing remediation's replay corpus (8 recorded games of the frozen scenarios under C1, both seats, every
decision's observation including ``valid_actions``). The public output holds counts per operator archetype and per
action type, never a scenario roster, unit identifier or observation. Archetypes are (type, sub_type) codes, named
only where the SDK 4.1.0 observation note names them. ``--check`` rebuilds and compares.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterator, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import typed_json  # noqa: E402

ARCHIVE = REPO_ROOT / "local" / "source-archives" / "land_wargame_sdk.zip"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
FROZEN = REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "manifest.json"
OUT = REPO_ROOT / "evaluation" / "tactical-frontier-1" / "census.json"
SCHEMA = "miaosuan-tactical-census/1"
NAMES = {(1, 2): "infantry", (2, 0): "tank", (2, 1): "infantry fighting vehicle", (2, 3): "artillery",
         (2, 4): "unmanned ground vehicle", (3, 5): "unmanned aerial vehicle", (3, 6): "helicopter",
         (3, 7): "loitering munition"}
ACTIONS = {1: "move", 2: "shoot", 3: "embark", 4: "disembark", 5: "occupy", 6: "change state", 7: "remove suppression",
           8: "indirect fire", 9: "guided fire", 10: "stop", 11: "weapon lock", 12: "weapon unfold",
           13: "cancel indirect fire", 14: "split", 15: "merge", 16: "change altitude", 17: "correction radar",
           18: "enter fortification", 19: "exit fortification", 20: "lay mine"}


def label(code: Any) -> str:
    key = tuple(code)
    return f"{key[0]}.{key[1]}" + (f" {NAMES[key]}" if key in NAMES else "")


def splittable(unit: Dict[str, Any]) -> bool:
    """A ground operator of two or more vehicles or squads, not artillery: what the rules allow to split."""
    return unit.get("type") in (1, 2) and unit.get("sub_type") != 3 and (unit.get("blood") or 0) >= 2


def scenarios() -> Iterator[Dict[str, Any]]:
    with zipfile.ZipFile(ARCHIVE) as outer:
        (name,) = [n for n in outer.namelist() if n.lower().endswith("data.zip")]
        with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
            for member in sorted(n for n in inner.namelist() if "/scenarios/" in n and n.endswith(".json")):
                yield json.loads(inner.read(member))


def scenario_census(frozen: List[str]) -> Dict[str, Any]:
    presence: Dict[str, collections.Counter] = {"all": collections.Counter(), "frozen": collections.Counter()}
    units: collections.Counter = collections.Counter()
    split = {"all": 0, "frozen": 0}
    split_units: collections.Counter = collections.Counter()
    split_blood: collections.Counter = collections.Counter()
    stacked = collections.Counter()
    frozen_split_sides = 0
    count = {"all": 0, "frozen": 0}
    for scenario in scenarios():
        sid = str(scenario["scenario_id"])
        groups = ["all"] + (["frozen"] if sid in frozen else [])
        operators = scenario["operators"]
        for group in groups:
            count[group] += 1
            for code in {(u.get("type"), u.get("sub_type")) for u in operators}:
                presence[group][label(code)] += 1
            if any(splittable(u) for u in operators):
                split[group] += 1
        for unit in operators:
            units[label((unit.get("type"), unit.get("sub_type")))] += 1
            stacked["stacked" if unit.get("stack") else "not stacked"] += 1
            if splittable(unit):
                split_units[label((unit.get("type"), unit.get("sub_type")))] += 1
                split_blood[str(unit.get("blood"))] += 1
        if sid in frozen:
            frozen_split_sides += len({u.get("color") for u in operators if splittable(u)})
    return {"scenarios": count, "archetype_presence": {g: dict(sorted(c.items())) for g, c in presence.items()},
            "operators_by_archetype": dict(sorted(units.items())),
            "scenarios_with_a_splittable_operator": split, "splittable_operators_by_archetype": dict(sorted(split_units.items())),
            "splittable_operators_by_blood": dict(sorted(split_blood.items())),
            "frozen_scenario_sides_with_a_splittable_operator": frozen_split_sides,
            "operators_stacked_at_start": dict(sorted(stacked.items()))}


def corpus_census() -> Dict[str, Any]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    decisions: collections.Counter = collections.Counter()
    listing_decisions: collections.Counter = collections.Counter()
    listing_units: collections.Counter = collections.Counter()
    by_archetype: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    enemy_visible = 0
    own_stacked = collections.Counter()
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            next(handle)
            for line in handle:
                row = json.loads(line)
                raw = typed_json.decode(row["observation"])
                stage = str(raw["time"]["stage"])
                decisions[stage] += 1
                operators = {u["obj_id"]: u for u in raw.get("operators") or []}
                if stage == "2" and any(u.get("color") != row["faction"] for u in operators.values()):
                    enemy_visible += 1
                for unit in operators.values():
                    if unit.get("color") == row["faction"]:
                        own_stacked["stacked" if unit.get("stack") else "not stacked"] += 1
                listed = set()
                for obj_id, actions in (raw.get("valid_actions") or {}).items():
                    unit = operators.get(int(obj_id), {})
                    for action_type in actions:
                        t = int(action_type)
                        listed.add(t)
                        listing_units[f"{stage}:{t}"] += 1
                        by_archetype[f"{t} {ACTIONS.get(t, '?')}"][label((unit.get("type"), unit.get("sub_type")))] += 1
                for t in listed:
                    listing_decisions[f"{stage}:{t}"] += 1
    def keyed(counter: collections.Counter) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = collections.defaultdict(dict)
        for key, n in counter.items():
            stage, t = key.split(":")
            out[{"1": "deployment", "2": "play"}[stage]][f"{int(t):02d} {ACTIONS.get(int(t), '?')}"] = n
        return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}
    return {"decisions": {{"1": "deployment", "2": "play"}[k]: v for k, v in sorted(decisions.items())},
            "decisions_listing_type": keyed(listing_decisions), "unit_listings_by_type": keyed(listing_units),
            "listing_archetypes_by_type": {k: dict(sorted(v.items())) for k, v in sorted(by_archetype.items())},
            "play_decisions_with_a_visible_enemy": enemy_visible,
            "own_unit_observations_stacked": dict(sorted(own_stacked.items()))}


def build() -> Dict[str, Any]:
    frozen = [s["scenario_id"] for s in json.loads(FROZEN.read_text(encoding="utf-8"))["scenarios"]]
    return {"schema": SCHEMA, "study_id": "tactical-frontier-1",
            "sources": {"scenarios": "the SDK 4.1.0 archive's 50 historical scenarios (private, read in memory)",
                        "corpus": "the routing remediation's pinned replay corpus: 8 baseline-v0 games, C1, both seats"},
            "frozen_scenarios": len(frozen), "scenario": scenario_census(frozen), "corpus": corpus_census()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("census identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
