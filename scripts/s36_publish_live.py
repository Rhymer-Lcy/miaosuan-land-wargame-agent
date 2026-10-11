"""Publish the Sprint 36 live results (REPORTING ONLY; ``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 23).

    python scripts/s36_publish_live.py [--work DIR] [--check]

Writes two public files from the private game records, both with the value-preserving publication policy
(``evaluation.s36_publish``):

* ``evaluation/s36-tactical-live-1/results.json``: exactly the object of the registered report
  (``scripts/s36_analysis.py``'s ``report``, called unchanged: every played game's public facts and the study state
  derived by ``evaluation.s36_study.report``), serialised compactly. The registered ``report --public`` writes the same
  object with one-space indentation, which for 43 games exceeds the 100,000-byte size rule of the project's pre-push
  scan; the compact form is checked to read back equal to the registered serialisation, value for value, so no metric
  is dropped and the accepted privacy baseline is not changed.
* ``evaluation/s36-tactical-live-1/summary.json``: the registered functions of ``evaluation.s36_live`` applied to the
  played games (the comparison after A1 and after A1 and A2, both batch gates, the replication rows, the references of
  the played configurations) and per-policy aggregates. The A1 and A2 comparison values are descriptive wherever the
  registered gates did not read them.

``--check`` regenerates both and fails unless the committed files are byte-identical. Nothing here changes a rule.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s36_live as sl  # noqa: E402
from miaosuan_agent.evaluation import s36_publish as pub  # noqa: E402

OUT = REPO_ROOT / "evaluation" / sl.CARD_ID
SIZE_RULE = 100_000


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s36p_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact(data: Any) -> str:
    return pub.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def summary(facts: Dict[int, Dict[str, Any]], state: Dict[str, Any]) -> Dict[str, Any]:
    history = [facts[p] for p in sorted(facts)]
    a1 = [f for f in history if f["batch"] == "A1"]
    by = collections.defaultdict(list)
    for f in history:
        by[f["tag"]].append(f)
    tags = {}
    for tag, fs in sorted(by.items()):
        tags[tag] = {
            "games": len(fs), "mean_share": round(sum(f["share"] for f in fs) / len(fs), 6),
            "decisions": sum(f["decisions"] for f in fs), "fallbacks": sum(f["fallbacks"] for f in fs),
            "contract_errors": sum(f["contract_errors"] or 0 for f in fs),
            "reconstruction_mismatches": sum(f["reconstruction_mismatches"] for f in fs),
            "latency_ms_p99_largest": max(f["latency_ms_p99"] for f in fs),
            "latency_ms_max_largest": max(f["latency_ms_max"] for f in fs),
            "memory_bytes_max_largest": max(f["memory_bytes_max"] for f in fs),
            "friendly_damage": sum(f["fire"]["friendly_damage"] for f in fs),
            "units_lost": sum(f["force"]["units_lost"] for f in fs),
            "value_lost": sum(f["force"]["value_lost"] for f in fs),
            "opponent_units_lost": sum(f["opponent_force"]["units_lost"] for f in fs),
            "objective_losses": sum(f["objectives"]["losses"] for f in fs),
            "recaptures": sum(f["objectives"]["recaptures"] for f in fs),
            "final_objectives_owned": sum(f["objectives"]["final_owned"] for f in fs),
            "full_hex_wait_longest": max(f["halts"]["longest_full_hex_wait"] for f in fs),
            "halted_unit_steps_by_cause": dict(sum((collections.Counter(f["halts"]["by_cause"]) for f in fs),
                                                   collections.Counter())),
            "refusal_classes": dict(sum((collections.Counter({k: v for k, v in
                                                              (f["refusal_summary"] or {}).get("classes", {}).items()
                                                              if v}) for f in fs), collections.Counter())),
            "module_actions": dict(sum((collections.Counter(f["module_actions"]) for f in fs),
                                       collections.Counter()))}
    references = {}
    for f in history:
        references[f"{f['scenario_id']} {f['candidate_side']}"] = {"win": f["reference"]["win"],
                                                                    "occupy": f["reference"]["occupy"]}
    gate_a1 = sl.batch_gate("A1", a1) if len(a1) == len(sl.BATCHES["A1"]) else None
    played_a2 = [f for f in history if f["batch"] in ("A1", "A2")]
    gate_a2 = sl.batch_gate("A2", played_a2) if len(played_a2) == len(sl.BATCHES["A1"]) + len(sl.BATCHES["A2"]) \
        else None
    return {"card": sl.CARD_ID, "rules": sl.RULES_ID, "disposition": state["disposition"], "stop": state["stop"],
            "games_played": len(history), "positions_not_played": [int(p) for p, s in state["positions"].items()
                                                                   if p not in {str(k) for k in facts}],
            "comparison_after_A1": sl.comparison(history, ("A1",)),
            "comparison_after_A1_A2_descriptive": sl.comparison(history),
            "batch_gate_A1": list(gate_a1) if gate_a1 else None, "batch_gate_A2": list(gate_a2) if gate_a2 else None,
            "thresholds": {"early_futility": sl.EARLY_FUTILITY, "unfavourable": sl.UNFAVOURABLE_DBAR,
                           "promising": -sl.UNFAVOURABLE_DBAR, "severe_sd": sl.SEVERE_SD},
            "replication": sl.replication(history), "references": references, "by_policy": tags}


def build(work: Path) -> Dict[str, str]:
    analysis = load("s36_analysis")
    result = analysis.report(work)
    registered = pub.dumps(result, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    results = compact(result)
    if json.loads(results) != json.loads(registered):
        raise RuntimeError("the compact results do not read back equal to the registered serialisation")
    facts = analysis.played(work)
    text = {"results.json": results, "summary.json": compact(summary(facts, result["state"]))}
    for name, body in text.items():
        if pub.collisions(body):
            raise RuntimeError(f"{name}: a numeric literal still matches the scan pattern")
        if len(body.encode("utf-8")) > SIZE_RULE:
            raise RuntimeError(f"{name}: {len(body.encode('utf-8'))} bytes exceed the size rule")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = build(args.work)
    if args.check:
        bad = [n for n, body in text.items() if not (OUT / n).exists() or (OUT / n).read_text(encoding="utf-8") != body]
        print("OK" if not bad else f"MISMATCH {bad}")
        return 1 if bad else 0
    for name, body in text.items():
        (OUT / name).write_text(body, encoding="utf-8", newline="\n")
        print(f"wrote evaluation/{sl.CARD_ID}/{name} ({len(body.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
