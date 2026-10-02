"""Dry run of the registered probe analyses on real Sprint 2 captures, before any probe session (lesson L4).

    PYTHON scripts/ps1_probe_dryrun.py [--t1r DIR] [--smoke DIR] [--out DIR]

The two Sprint 2 games of 1910631192 C3 (``local/evaluation/t1r-diagnosis-1``, a snapshot every step) are real
captures of the kind P2 plays: the frozen split candidate (game c) and baseline-v2 (game b) against the inert control.
They predate the probe capture, so the pre-execution copies are rebuilt from the serialised batch by undoing the one
documented in-place rewrite (a deployment split's type 314 serialised as 14); nothing else is changed. Known answers,
established in Sprint 3 (``evaluation/ps1-design-1/posthoc.json``), must come out again:

* P2 analysis on game c: F1 PASS with 0 sequence differences and worst offset 0; F2 PASS; the frozen Sprint 3
  extractors agree; the trigger census equals the deadlock episodes' trigger steps;
* P1 analysis on game c: no hook note, so no stop: not evaluable, every E verdict INCONCLUSIVE;
* the Sprint 1 smoke capture of 1930331196 (a snapshot every 200 steps) is refused for missing snapshots (I2).

Outputs (private, unit ids and hexes) go to ``--out`` (default ``local/diagnostics/ps1-probe/dryrun``); the summary
printed holds counts and verdicts only. Exit status 1 when a known answer does not come out.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import ps1_probe as pp  # noqa: E402

_spec = importlib.util.spec_from_file_location("ps1_probe_analysis", Path(__file__).with_name("ps1_probe_analysis.py"))
an = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(an)


def adapt(record: Mapping[str, Any], compact: Mapping[str, Any]) -> Dict[str, Any]:
    """The compact log with a ``submitted`` list per step rebuilt from the serialised batch (split type 14 -> 314)."""
    out = copy.deepcopy(dict(compact))
    for step in out["steps"]:
        step["submitted"] = [dict(b, action=dict(b["action"], type=314) if b["action"].get("type") == 14 and step["stage"] == 1
                                  else dict(b["action"])) for b in step["batch"]]
    return out


def game(work: Path, game_id: str) -> Any:
    record = json.loads((work / "games" / f"{game_id}.json").read_text(encoding="utf-8"))
    compact = json.loads((work / "capture" / f"{game_id}.capture.json").read_text(encoding="utf-8"))
    windows = pickle.loads((work / "capture" / f"{game_id}.windows.pkl").read_bytes())
    return an.Game(record, adapt(record, compact), windows), record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--t1r", type=Path, default=REPO_ROOT / "local" / "evaluation" / "t1r-diagnosis-1")
    parser.add_argument("--smoke", type=Path,
                        default=REPO_ROOT / "local" / "evaluation" / "tactical-screen-deployment-split-1-smoke")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "ps1-probe" / "dryrun")
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "evaluation" / pp.PROBE_ID / "manifest.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    costs = an.load_costs(args.t1r, manifest, "1910631192")
    failures = []
    summary: Dict[str, Any] = {}

    g, record = game(args.t1r, "1910631192.C3.c.x01")
    p2 = an.analyze_p2(g, manifest, costs)
    pub = p2["public"]
    summary["P2 on the Sprint 2 split game"] = {
        "F1": {k: pub["F1"][k] for k in ("verdict", "hex_sequences_differ", "worst_step_offset", "observed_entries",
                                         "simulated_entries", "accounting_complete")},
        "F2": {k: pub["F2"][k] for k in ("verdict", "hex_sequences_differ", "worst_step_offset", "orders", "occupations")},
        "claims": pub["targeted"]["claims"], "frozen_extractors": pub["frozen_extractors"],
        "population": pub["population"], "actions": pub["actions"], "integrity_ok": pub["integrity"]["ok"],
        "trigger_census": pub["trigger_census"], "deadlock_episodes": pub["deadlock_episodes"],
        "targeted_counts": {c: pub["targeted"][c] for c in ("T-a", "T-b", "T-c", "T-d", "T-e")}}
    if not (pub["F1"]["verdict"] == "PASS" and pub["F1"]["hex_sequences_differ"] == 0 and pub["F1"]["worst_step_offset"] == 0):
        failures.append("F1 on the Sprint 2 split game is not PASS with offset 0")
    if pub["F2"]["verdict"] != "PASS":
        failures.append("F2 on the Sprint 2 split game is not PASS")
    if pub["actions"]["rewritten_in_place"] != 12:
        failures.append("the adapted capture does not show the 12 documented rewrites")
    an.write(pub, p2["private"], args.out / "p2-on-sprint2-split.json", args.out / "p2-on-sprint2-split-private.json")

    p1 = an.analyze_p1(g, manifest, record, costs)
    summary["P1 on the Sprint 2 split game"] = {"evaluable": p1["public"]["evaluable"], "verdicts": p1["public"]["verdicts"],
                                                "integrity_problems": p1["public"]["integrity"]["problems"]}
    if p1["public"]["evaluable"] or set(p1["public"]["verdicts"].values()) != {"INCONCLUSIVE"}:
        failures.append("P1 without hook notes is not INCONCLUSIVE")

    try:
        smoke, _ = game(args.smoke, "1930331196.C2.c.s01")
        smoke.tables()
        failures.append("the 200-step smoke capture was not refused")
    except an.Refused as exc:
        summary["smoke capture"] = str(exc)
        if "I2" not in str(exc):
            failures.append("the smoke capture was refused for another reason than missing snapshots")

    summary["failures"] = failures
    print(json.dumps(summary, indent=1, sort_keys=True, default=list))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
