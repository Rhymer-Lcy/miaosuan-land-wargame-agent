"""Sprint 34 scenario coverage and capability matrix (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 5). Engine-free.

    python scripts/s34_coverage.py --data DIR [--check]

``DIR`` is the extracted ``Data`` folder of the SDK archive (pinned by SHA-256 below; the script checks the archive
it names in ``--archive``). For every one of the archive's scenario files it records: the map named by the project's
registered naming rule and the registered eligibility verdict (``evaluation/selection.py``, rules E1 to E4, with
their reasons); operators by faction and by (type, sub_type) class; objectives (count and values); the movement modes
present; which capability modules of the integrated agent have something to act on (transport: an infantry squad and
a carrier of squads; indirect fire: artillery; aircraft support; direct fire: any weapon); for each side, how many
objectives some mobile ground unit can reach before ``max_time`` at free-flow speed; and, for each eligible scenario
and side, the live candidate's first play decision on the model world's initial state (actions by type, objectives
targeted, validation rejections, fallbacks, latency). Output: ``evaluation/s34-integrated-agent/coverage.json``
(public: scenario and map ids are the SDK's file names; no hex, unit id or coordinate is written).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts  # noqa: E402
from miaosuan_agent.decision.routing import move_mode  # noqa: E402
from miaosuan_agent.evaluation import selection  # noqa: E402
from miaosuan_agent.evaluation.s34_world import SEATS, ModelWorld  # noqa: E402
from miaosuan_agent.integrated import facts as F  # noqa: E402
from miaosuan_agent.integrated.agent import CommanderAgent  # noqa: E402
from miaosuan_agent.integrated.config import CT, MO  # noqa: E402
from miaosuan_agent.integrated.movement import Terrain  # noqa: E402

ARCHIVE_SHA256 = "ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725"
OUT = REPO_ROOT / "evaluation" / "s34-integrated-agent" / "coverage.json"
SCHEMA = "miaosuan-s34-coverage/1"
CLASS_NAMES = {(1, 2): "infantry squad", (2, 0): "tank", (2, 1): "infantry fighting vehicle", (2, 3): "artillery",
               (2, 4): "unmanned ground vehicle", (3, 5): "unmanned aerial vehicle", (3, 6): "helicopter",
               (3, 7): "loitering munition", (3, 8): "transport helicopter"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def label(code) -> str:
    return CLASS_NAMES.get(code, f"type {code[0]} sub_type {code[1]}")


def reachable(scenario: Dict[str, Any], terrain: Terrain, color: int) -> int:
    max_time = int(scenario["time"]["max_time"])
    count = 0
    for city in scenario["cities"]:
        best = None
        for u in scenario["operators"]:
            if u["color"] != color or u["type"] not in F.GROUND or u.get("on_board"):
                continue
            if u["type"] == F.VEHICLE and u.get("sub_type") == F.ARTILLERY:
                continue
            mode = move_mode(u["type"], u.get("move_state"))
            cost = terrain.cost_to(mode, u["cur_hex"], city["coord"], frozenset())
            seconds = terrain.seconds(float(u.get("basic_speed") or 0), cost)
            if seconds is not None and (best is None or seconds < best):
                best = seconds
        count += best is not None and best <= max_time
    return count


def first_decision(data: Path, scenario_id: str, map_id: str, config, color: int) -> Dict[str, Any]:
    inputs = sdk_data.load_inputs(data, scenario_id, map_id)
    costs = MoveCosts.from_raw(inputs.cost)
    world = ModelWorld(inputs.scenario, costs, terrain_id=int(map_id))
    world.step({0: [{"actor": SEATS[0], "type": F.END_DEPLOYMENT}], 1: [{"actor": SEATS[1], "type": F.END_DEPLOYMENT}]})
    agent = CommanderAgent(config)
    agent.setup({"seat": SEATS[color], "faction": color, "cost_data": inputs.cost})
    tick = time.perf_counter()
    actions = agent.step(world.observation(color))
    latency = (time.perf_counter() - tick) * 1000.0
    trace = agent.last_trace
    targets = {a["move_path"][-1] for a in actions if a["type"] == F.MOVE}
    targets |= {p[3] for p in getattr(trace, "plans", ()) if p[2] in ("ride", "capture", "hold") and p[3] >= 0}
    objective_hexes = {c["coord"] for c in inputs.scenario["cities"]}
    by_type = collections.Counter(int(a["type"]) for a in actions)
    return {"actions_by_type": {f"type_{k}": v for k, v in sorted(by_type.items())},
            "objectives_targeted": len(targets & objective_hexes), "objectives": len(objective_hexes),
            "rejections": len(trace.rejected), "fallback": bool(getattr(trace, "fallback", None)),
            "contract_error": trace.error is not None, "first_decision_ms": round(latency, 1)}


def build(data: Path, archive: Path) -> Dict[str, Any]:
    if sha256(archive) != ARCHIVE_SHA256:
        raise SystemExit("the SDK archive does not match its pinned digest")
    with zipfile.ZipFile(archive) as outer:
        (name,) = [n for n in outer.namelist() if n.lower().endswith("data.zip")]
        with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
            facts = selection.survey(inner)
    rows: List[Dict[str, Any]] = []
    terrains: Dict[str, Terrain] = {}
    for fact in facts:
        scenario = json.loads((data / "scenarios" / f"{fact.scenario_id}.json").read_text(encoding="utf-8"))
        ops = scenario["operators"]
        classes = {c: collections.Counter(label((u["type"], u.get("sub_type"))) for u in ops if u["color"] == c)
                   for c in (0, 1)}
        codes = {(u["type"], u.get("sub_type")) for u in ops}
        squads = any(c == (1, 2) for c in codes)
        carriers = any(2 in (u.get("valid_passenger_types") or []) for u in ops)
        row: Dict[str, Any] = {
            "scenario_id": fact.scenario_id, "map_id": fact.map_id, "eligible": fact.eligible,
            "eligibility_reasons": list(fact.reasons), "max_time": fact.max_time,
            "operators": {"red": fact.red, "blue": fact.blue},
            "classes": {("red" if c == 0 else "blue"): dict(sorted(v.items())) for c, v in classes.items()},
            "objectives": {"count": len(scenario["cities"]),
                           "values": sorted((int(c.get("value") or 0) for c in scenario["cities"]), reverse=True)},
            "movement_modes": sorted({str(move_mode(u["type"], u.get("move_state")).name)
                                      for u in ops if move_mode(u["type"], u.get("move_state")) is not None}),
            "capabilities": {"transport": squads and carriers, "indirect_fire": (2, 3) in codes,
                             "aircraft_support": any(c[0] == 3 for c in codes),
                             "direct_fire": any(u.get("carry_weapon_ids") for u in ops),
                             "starts_aboard": any(u.get("on_board") for u in ops)},
            "contract_limitations": ([] if fact.eligible else ["not playable on the old SDK pairing: " + "; ".join(fact.reasons)]),
        }
        if fact.eligible:
            if fact.map_id not in terrains:
                terrains[fact.map_id] = Terrain(MoveCosts.from_raw(sdk_data.load_cost(
                    data / "maps" / f"map_{fact.map_id}" / "cost.pickle")))
            terrain = terrains[fact.map_id]
            row["reachable_objectives"] = {"red": reachable(scenario, terrain, 0), "blue": reachable(scenario, terrain, 1)}
            row["first_decision"] = {cfg.name: {("red" if c == 0 else "blue"): first_decision(data, fact.scenario_id,
                                                                                               fact.map_id, cfg, c)
                                                for c in (0, 1)} for cfg in (CT, MO)}
        rows.append(row)
    eligible = [r for r in rows if r["eligible"]]
    summary = {
        "scenarios": len(rows), "eligible": len(eligible), "maps": len({r["map_id"] for r in rows if r["map_id"]}),
        "eligible_maps": len({r["map_id"] for r in eligible}),
        "capability_scenarios": {k: sum(1 for r in eligible if r["capabilities"][k])
                                 for k in ("transport", "indirect_fire", "aircraft_support", "direct_fire",
                                           "starts_aboard")},
        "first_decision_problems": sum(1 for r in eligible for cfg in r["first_decision"].values()
                                       for side in cfg.values()
                                       if side["rejections"] or side["fallback"] or side["contract_error"]),
        "sides_targeting_no_objective": {cfg: sum(1 for r in eligible for side in r["first_decision"][cfg].values()
                                                  if side["objectives_targeted"] == 0) for cfg in (CT.name, MO.name)},
    }
    return {"schema": SCHEMA, "archive_sha256": ARCHIVE_SHA256, "summary": summary, "scenarios": rows,
            "note": "engine-free: listings come from the Sprint 34 model world, not the engine; no scenario was "
                    "played on the engine to build this matrix"}


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=REPO_ROOT / "local" / "source-archives" / "land_wargame_sdk.zip")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build(args.data, args.archive)
    # Latency varies between hosts and runs; --check compares everything else.
    if args.check:
        committed = json.loads(OUT.read_text(encoding="utf-8"))
        for doc in (committed, result):
            for row in doc["scenarios"]:
                for cfg in (row.get("first_decision") or {}).values():
                    for side in cfg.values():
                        side.pop("first_decision_ms", None)
        if committed != result:
            print("MISMATCH")
            return 1
        print("coverage identical (latency excluded)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dump(result), encoding="utf-8", newline="\n")
    print(json.dumps(result["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
