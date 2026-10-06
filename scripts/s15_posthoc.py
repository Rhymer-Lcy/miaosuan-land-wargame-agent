"""Sprint 15 POST-HOC sensitivity analysis (``docs/SPRINT15_DELAYED_REDISTRIBUTION.md``, results R7), server only.

    python scripts/s15_posthoc.py [--check]

NOT a registered result. It changes no disposition and selects no candidate. After the frozen replay, two defects of
the registered design were found: (1) the candidates' memory ends a record when the unit stands on ANY objective,
including one the side already holds, where ``baseline-v2`` keeps re-targeting it (a deferred unit, not a committed
one); (2) the registered R3 compares slot assignments with stateless T9-v1 at every later decision, while on recorded
states a redirected unit reappears as an overflow claimant (the recorded policy held it), so a rule that redirects once
per episode is counted as diverging again at every later decision. This script re-runs the frozen driver's own
per-capture analysis with:

* the six frozen rules under a corrected memory update that ends a record only on an objective NOT held by the side
  (``posthoc-<rule>``);
* a reference ``posthoc-bounded-o2``: O2's redirection with at most one redirect per episode and no delay, under the
  corrected memory, to measure what bounded recourse alone does to R3 on these recorded states;

and reports, per variant, the gate items and the adequacy rule exactly as frozen (latency not measured: shown as 0).
Writes (or with ``--check`` compares) ``evaluation/s15-delayed-redistribution/posthoc.json``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s15_delayed as s15  # noqa: E402
from miaosuan_agent.experiments import t9_delayed as td  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "s15-delayed-redistribution" / "posthoc.json"
FROZEN_OBSERVE, FROZEN_ELIGIBLE = td.observe, td.eligible
VARIANTS = {f"posthoc-{name}": rule for name, rule in td.RULES.items()}
VARIANTS["posthoc-bounded-o2"] = td.DelayedRule("posthoc-bounded-o2", "always")


def observe_corrected(observation, faction, records):
    """``t9_delayed.observe`` with one change: standing on an objective ends the record only when the side does not
    hold that objective."""
    own = {u.obj_id: u for u in observation.operators() if u.color == faction and u.unit_type in td.GROUND}
    cities = {c.coord: c for c in (observation.cities() or ())}
    held = {coord for coord, city in cities.items() if city.flag == faction}
    shadow = {}
    for unit_id in list(records):
        unit = own.get(unit_id)
        if unit is not None and not tuple(unit.move_path or ()) and unit.cur_hex in held:
            shadow[unit_id] = records.pop(unit_id)  # handled below, never by the frozen "standing" rule
    ended = FROZEN_OBSERVE(observation, faction, records)
    for unit_id, record in shadow.items():
        if record[td.SOURCE] in cities and cities[record[td.SOURCE]].flag == faction:
            ended[unit_id] = "source held by the side"
            for index in (td.SOURCE, td.COUNT, td.ALTERNATIVE, td.SATURATED, td.REDIRECTED, td.FIRST):
                record[index] = 0
        if any(record):
            records[unit_id] = record
    return ended


def eligible_with_reference(rule, record, source, best, saturated):
    if rule.trigger == "always":
        return record is None or not record[td.REDIRECTED]
    return FROZEN_ELIGIBLE(rule, record, source, best, saturated)


def install() -> Any:
    spec = importlib.util.spec_from_file_location("s15_delayed_replay_posthoc", REPO_ROOT / "scripts" /
                                                  "s15_delayed_replay.py")
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver  # worker processes pickle the driver's functions by module name
    spec.loader.exec_module(driver)
    driver.require_inputs()  # the frozen inputs, identities and thresholds must still hold, before any patch
    td.observe = observe_corrected
    td.eligible = eligible_with_reference
    td.RULES.clear()
    td.RULES.update(VARIANTS)
    s15.CANDIDATES = tuple(VARIANTS)
    s15.POLICIES = s15.REFERENCES + s15.CANDIDATES
    s15.SIMPLICITY = s15.CANDIDATES
    driver.static_checks = lambda: {"seat_local": True, "no_special_case_literal": True}  # checked on the frozen module
    return driver


def build(driver, workers: int) -> Tuple[Dict[str, Any], set]:
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        shooters = driver.shooter_table(pool)
        results = pool.map(driver.process, driver.jobs("run", shooters), chunksize=1)
        h0 = pool.map(driver.process_h0, [str(p) for p, _ in driver.h0_files()], chunksize=1)
    timing = {"candidates": {name: {"p99": 0.0, "max": 0.0} for name in VARIANTS}}
    public = driver.run_combine(results, h0, shooters, timing)
    gate, replay = public["gate"], public["replay"]["primary"]
    rows: Dict[str, Any] = {}
    for name in VARIANTS:
        items = gate["gates"][name]["items"]
        rows[name] = {
            "failed_excluding_latency": [k for k in gate["gates"][name]["failed"] if k != "G12_latency"],
            "R1": items["R1_no_opening_redistribution"], "R2": items["R2_post_opening_restored"],
            "R3": items["R3_divergence_reduced"], "R4": items["R4_bounded_recourse"],
            "A1": items["A1_1930331196"], "A2": items["A2_2120531121_C3"],
            "invariants_pass": all(items[k]["pass"] for k in items if k.startswith("G") and k != "G12_latency"),
            "adequacy": gate["adequacy"][name],
            "primary_pooled": replay[name]["pooled"],
            "adverse_redirects": {cfg: public[stem]["policies"][name]["t9-v1"]["redirects"]
                                  + public[stem]["policies"][name]["baseline-v2"]["redirects"]
                                  for cfg, stem in driver.ADVERSE_FILES.items()}}
    return ({"schema": "miaosuan-s15-posthoc/1",
            "label": "POST HOC: not a registered result; no disposition and no candidate follow from it",
            "inputs_sha256": driver.sha256(driver.INPUTS), "fidelity_problems": gate["fidelity_problems"],
            "corrections": ["memory: standing on an objective ends a record only when the side does not hold it",
                            "reference posthoc-bounded-o2: O2 with at most one redirect per episode and no delay"],
            "variants": rows}, driver.private_values(results))


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args(argv)
    driver = install()
    data, hidden = build(driver, args.workers)
    text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    found = s15.public_check(data, hidden)
    if found:
        raise SystemExit(f"refused: posthoc.json would publish private values: {found[:5]}")
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({n: (r["failed_excluding_latency"], r["adequacy"]["all_tested"]) for n, r in
                      data["variants"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
