"""Sprint 18 admission evidence for new families (``docs/SPRINT18_FRONTIER_RESET.md``, section 7), from the census rows.

    python scripts/s18_admission.py [--check]

Reads the private per-event and per-side rows the census wrote (``local/diagnostics/s18/census-private.json.gz``,
checked against the digest recorded beside it) and writes ``evaluation/s18-frontier-reset/admission.json``: cross
tabulations of the damage events (victim stacked, moving, on an objective, in close combat; attacker seen before) and
the per-side presence figures the admission entries cite. These tables were defined after the census had run and
before any family was scored; they are descriptive admission evidence, labelled post hoc relative to the census.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "s18-frontier-reset" / "admission.json"
CENSUS = REPO_ROOT / "evaluation" / "s18-frontier-reset" / "census.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s18" / "census-private.json.gz"
SCHEMA = "miaosuan-s18-admission/1"
GROUND = ("infantry", "vehicle", "artillery")


def state(r: Mapping[str, Any]) -> str:
    where = "on an objective" if r["on_objective"] else "off objectives"
    motion = "moving" if r["moving"] else "stationary"
    return f"{motion}, {where}, {'stacked' if r['stacked'] else 'alone'}"


def tables(events: List[Mapping[str, Any]], sides: List[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for population in ("H0", "HH"):
        rows = [r for r in events if r["population"] == population]
        ground = [r for r in rows if r["victim_class"] in GROUND and not r["aboard"]]
        close = [r for r in rows if r["distance"] == 0]
        out[population] = {
            "damage_events": len(rows),
            "ground_events_by_state": dict(sorted(collections.Counter(state(r) for r in ground).items())),
            "ground_damage_by_state": {s: sum(r["damage"] for r in ground if state(r) == s)
                                       for s in sorted({state(r) for r in ground})},
            "close_combat_events": len(close),
            "close_combat_events_victim_moving": sum(r["moving"] for r in close),
            "close_combat_events_victim_on_objective": sum(r["on_objective"] for r in close),
            "close_combat_events_victim_stacked": sum(r["stacked"] for r in close),
            "close_combat_events_attacker_seen_before": sum(r["seen_before"] for r in close),
            "stationary_stacked_on_objective_events_attacker_seen_before": sum(
                r["seen_before"] for r in ground if not r["moving"] and r["stacked"] and r["on_objective"]),
            "aircraft_events_by_attacker_class": dict(sorted(collections.Counter(
                r["attacker_class"] for r in rows if r["victim_class"] == "aircraft").items())),
            "events_by_attacker_class": dict(sorted(collections.Counter(r["attacker_class"] for r in rows).items())),
        }
        h0_sides = [s for s in sides if s["population"] == population]
        out[population]["sides"] = len(h0_sides)

    def side_has(population: str, predicate) -> int:
        keys = {(s["game"], s["faction"]) for s in sides if s["population"] == population}
        return sum(1 for key in keys if any(predicate(r) for r in events
                                            if r["population"] == population and (r["game"], r["faction"]) == key))

    out["H0"]["sides_with_a_stationary_stacked_hit_on_an_objective"] = side_has(
        "H0", lambda r: r["victim_class"] in GROUND and not r["aboard"] and not r["moving"] and r["stacked"] and r["on_objective"])
    out["H0"]["sides_with_a_close_combat_hit_on_a_moving_unit"] = side_has("H0", lambda r: r["distance"] == 0 and r["moving"])
    return out


def build() -> Dict[str, Any]:
    raw = PRIVATE.read_bytes()
    data = json.loads(gzip.decompress(raw))
    return {"schema": SCHEMA, "study_id": "s18-frontier-reset",
            "census_sha256": hashlib.sha256(CENSUS.read_bytes()).hexdigest(),
            "private_rows_sha256": hashlib.sha256(raw).hexdigest(),
            "label": "post hoc relative to the census, written before any family was scored; descriptive",
            "tables": tables(data["events"], data["sides"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from miaosuan_agent.evaluation.s12_screen import privacy_problems
    data = build()
    problems = privacy_problems(data)
    if problems:
        print("privacy problems:", problems[:5])
        return 1
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("admission identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
