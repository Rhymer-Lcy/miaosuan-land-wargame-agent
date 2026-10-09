"""Sprint 30 historical feasibility preflight of ``t13-keep-one-k1`` and the historical controls of the pilot
(``docs/SPRINT30_T13_K1_PILOT.md``, sections 4 and 5). Offline only; runs on the evaluation server.

    python scripts/s30_preflight.py freeze [--check]
    python scripts/s30_preflight.py run [--check] [--workers N]

``freeze`` writes ``evaluation/s30-t13-k1/preflight-inputs.json``: Sprint 23's committed job list (H0, HH, HI) with its
own pins, the SHA-256 of Sprint 23's ``inputs.json``, the normalised SHA-256 of every source the preflight depends on,
the fidelity anchors, the stop rule and the inert priority, and the SHA-256 of each historical control record (the
registered shoot-reservation experiment's group C games of the configurations the pilot can play).

``run`` refuses unless every pin matches. It reads every side through Sprint 23's own loader and ``baseline-v2``
reconstruction (``scripts/s23_t2_design.py``: ``decisions``, ``baseline``, ``scenario_costs``; unchanged), applies the
candidate's frozen rule and the independent check (``evaluation/s30_preflight.py``) and writes the public
``preflight.json`` and ``controls.json`` (aggregates, steps, labels; sanitised, or nothing is written) and the private
rows ``local/diagnostics/s30/preflight-private.json.gz``. ``--check`` rebuilds and compares instead of writing.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import multiprocessing
import statistics
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT = REPO_ROOT / "evaluation" / "s30-t13-k1"
INPUTS = OUT / "preflight-inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s30"
S23_INPUTS = REPO_ROOT / "evaluation" / "s23-t2-policy-design" / "inputs.json"
CONTROL_GAMES = REPO_ROOT / "local" / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "games"
SCHEMA_INPUTS = "miaosuan-s30-preflight-inputs/1"
SCHEMA_CONTROLS = "miaosuan-s30-controls/1"
#: Historical control configurations: (scenario, condition, the baseline-v2 seat colours read).
CONTROL_CONFIGS = (("2120531121", "C3", ("blue",)), ("1930331196", "C2", ("red",)), ("1930331196", "C3", ("blue",)),
                   ("2130511121", "C1", ("red", "blue")))
CONTROL_REPS = 15
SOURCES = ("src/miaosuan_agent/experiments/t13_keep_one_k1.py",
           "src/miaosuan_agent/experiments/exploratory_addon.py",
           "src/miaosuan_agent/experiments/t9_batch.py",
           "src/miaosuan_agent/evaluation/s30_preflight.py",
           "scripts/s30_preflight.py",
           "scripts/s23_t2_design.py",
           "src/miaosuan_agent/evaluation/s12_timeline.py",
           "src/miaosuan_agent/evaluation/s12_screen.py",
           "src/miaosuan_agent/evaluation/s27_probe.py")
PUBLIC_LIMIT = 90_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalised(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def s23() -> Any:
    spec = importlib.util.spec_from_file_location("s30_s23_driver", REPO_ROOT / "scripts" / "s23_t2_design.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def control_files() -> List[Tuple[str, str, Path]]:
    return [(sid, cond, CONTROL_GAMES / f"{sid}.{cond}.C.r{r}.json")
            for sid, cond, _ in CONTROL_CONFIGS for r in range(1, CONTROL_REPS + 1)]


# ------------------------------------------------------------------------------------------------
# freeze


def freeze() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s30_preflight as pf
    committed = json.loads(S23_INPUTS.read_text(encoding="utf-8"))
    problems = s23().file_problems(committed["jobs"])
    if problems:
        raise SystemExit(f"refused: Sprint 23's pinned inputs differ: {problems[:5]}")
    return {"schema": SCHEMA_INPUTS, "study_id": pf.STUDY_ID, "engine_sessions": 0,
            "s23_inputs": {"path": S23_INPUTS.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(S23_INPUTS)},
            "jobs": committed["jobs"],
            "sources": {rel: normalised(REPO_ROOT / rel) for rel in SOURCES},
            "anchors": pf.ANCHORS, "dispositions_first_match": list(pf.DISPOSITIONS),
            "inert_priority": [list(c) for c in pf.INERT_PRIORITY], "inert_games_needed": pf.INERT_GAMES_NEEDED,
            "genuine_populations": list(pf.GENUINE),
            "controls": {"configurations": [[s, c, list(sides)] for s, c, sides in CONTROL_CONFIGS],
                         "records": {path.name: sha256(path) for _, _, path in control_files()}}}


def input_problems(committed: Mapping[str, Any]) -> List[str]:
    problems = []
    if sha256(REPO_ROOT / committed["s23_inputs"]["path"]) != committed["s23_inputs"]["sha256"]:
        problems.append(committed["s23_inputs"]["path"])
    problems += s23().file_problems(committed["jobs"])
    for rel, digest in committed["sources"].items():
        if normalised(REPO_ROOT / rel) != digest:
            problems.append(rel)
    for name, digest in committed["controls"]["records"].items():
        path = CONTROL_GAMES / name
        if not path.exists() or sha256(path) != digest:
            problems.append(name)
    return problems


# ------------------------------------------------------------------------------------------------
# sides


def label(job: Mapping[str, Any], faction: int, scenario: str) -> Tuple[str, str]:
    colour = "red" if faction == 0 else "blue"
    if job["population"] == "H0":
        return f"H0 {scenario} {colour}", "C1"
    condition = job["game"].split(".")[1]
    if job["population"] == "HH":
        return f"HH {job['game'].rsplit('.', 1)[-1]} baseline-v2 {colour}", condition
    return f"HI {scenario} {condition} baseline-v2 {colour}", condition


def worker(job: Mapping[str, Any]) -> List[Tuple[Dict[str, Any], List[Any]]]:
    from miaosuan_agent.decision.routing import Router
    from miaosuan_agent.evaluation import residual516 as rd
    from miaosuan_agent.evaluation import s30_preflight as pf
    from miaosuan_agent.boundary import Observation, Origin
    from miaosuan_agent.experiments import t13_keep_one_k1 as k1
    driver = s23()
    scenario, _, costs = driver.scenario_costs(job)
    travel = k1.router_travel(Router(costs))
    out = []
    for _, seat, faction, stream in driver.decisions(job):
        decide = driver.baseline(costs)
        text, condition = label(job, faction, scenario)

        def rows():
            for raw, recorded, memory in stream:
                actions = decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
                yield raw, rd.plain(list(recorded)), rd.plain(list(actions))

        meta = {"population": job["population"], "label": text, "scenario": scenario, "condition": condition,
                "faction": faction}
        summary, private = pf.analyse_side(meta, rows(), costs, travel)
        out.append((summary, sorted(str(v) for v in private)))
    return out


def compute(committed: Mapping[str, Any], workers: int) -> Tuple[List[Dict[str, Any]], set]:
    jobs = committed["jobs"]
    with multiprocessing.Pool(max(1, min(workers, len(jobs)))) as pool:
        parts = pool.map(worker, jobs)
    sides, private = [], set()
    for part in parts:
        for summary, values in part:
            sides.append(summary)
            private.update(values)
    order = {p: i for i, p in enumerate(("HH", "HI", "H0"))}
    sides.sort(key=lambda s: (order[s["population"]], s["label"]))
    return sides, private


def anchors(sides: List[Mapping[str, Any]]) -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s30_preflight as pf
    pop = {p: [s for s in sides if s["population"] == p] for p in pf.POPULATIONS}
    got = {"H0 decisions": sum(s["decisions"] for s in pop["H0"]),
           "H0 play decisions": sum(s["play_decisions"] for s in pop["H0"]),
           "H0 v2 differs from recorded v0": sum(s["baseline_v2_differs_from_recorded"] for s in pop["H0"]),
           "HH decisions": sum(s["decisions"] for s in pop["HH"]), "HI decisions": sum(s["decisions"] for s in pop["HI"])}
    out = {k: {"published": v, "preflight": got[k], "equal": got[k] == v} for k, v in pf.ANCHORS.items()}
    for p in pf.GENUINE:
        out[f"{p} baseline-v2 reconstruction equal to the recorded seat at every decision"] = {
            "published": True, "preflight": all(s["baseline_v2_differs_from_recorded"] == 0 for s in pop[p]),
            "equal": all(s["baseline_v2_differs_from_recorded"] == 0 for s in pop[p])}
    out["side-games H0, HH, HI"] = {"published": [16, 4, 3], "preflight": [len(pop[p]) for p in pf.POPULATIONS],
                                    "equal": [len(pop[p]) for p in pf.POPULATIONS] == [16, 4, 3]}
    return out


# ------------------------------------------------------------------------------------------------
# controls


def frac(value: Fraction) -> Any:
    return value.numerator if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def controls(committed: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"schema": SCHEMA_CONTROLS,
                           "source": "the registered shoot-reservation experiment's group C games (baseline-v2), "
                                     "fifteen per configuration; margin = the seat's total minus the opponent's total "
                                     "(the engine's <side>_win)",
                           "inputs_sha256": sha256(INPUTS), "configurations": {}}
    for sid, cond, sides in CONTROL_CONFIGS:
        records = [json.loads((CONTROL_GAMES / f"{sid}.{cond}.C.r{r}.json").read_text(encoding="utf-8"))
                   for r in range(1, CONTROL_REPS + 1)]
        if any(r["status"] != "COMPLETED" or str(r["scenario_id"]) != sid or r["condition"] != cond for r in records):
            raise SystemExit(f"{sid} {cond}: a control record is incomplete or mislabelled")
        for side in sides:
            other = "blue" if side == "red" else "red"
            scores = [r["final_scores"] for r in records]
            margins = [s[f"{side}_total"] - s[f"{other}_total"] for s in scores]
            if margins != [s[f"{side}_win"] for s in scores]:
                raise SystemExit(f"{sid} {cond}: the margin is not the engine's {side}_win")
            row: Dict[str, Any] = {"games": len(records)}
            for name in ("occupy", "attack", "remain", "total"):
                values = sorted(s[f"{side}_{name}"] for s in scores)
                row[name] = {"values": values, "min": values[0], "max": values[-1],
                             "mean": frac(Fraction(sum(values), len(values)))}
            values = sorted(margins)
            row["margin"] = {"values": values, "min": values[0], "max": values[-1],
                             "mean": frac(Fraction(sum(values), len(values))),
                             "population_sd": round(statistics.pstdev(values), 2),
                             "sample_sd": round(statistics.stdev(values), 2)}
            row["occupy_constant"] = row["occupy"]["min"] == row["occupy"]["max"]
            out["configurations"][f"{sid} {cond} baseline-v2 {side}"] = row
    return out


# ------------------------------------------------------------------------------------------------
# run


def build(committed: Mapping[str, Any], workers: int) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s27_probe as sp
    from miaosuan_agent.evaluation import s30_preflight as pf
    sides, private = compute(committed, workers)
    fid = anchors(sides)
    verdict = pf.disposition(all(a["equal"] for a in fid.values()), sides)
    head = {"schema": pf.SCHEMA, "study_id": pf.STUDY_ID, "inputs_sha256": sha256(INPUTS), "engine_sessions": 0}
    boundary = ("HH and HI are genuine baseline-v2 trajectories (HH's opponent was the T9-v3 candidate, not "
                "baseline-v2; HI's the inert control); H0 is baseline-v0's trajectory with baseline-v2 reconstructed. "
                "A first divergence is a valid action-level fact in HH and HI, and in H0 only on a supported prefix. "
                "Withholdings after a side's first divergence lie on recorded states the candidate would not reach "
                "and are post-divergence diagnostics only. Onward labels are historical.")
    public = {"preflight.json": {**head, "evidence_boundary": boundary, "fidelity": fid, **verdict,
                                 "populations": {p: pf.pooled([s for s in sides if s["population"] == p])
                                                 for p in pf.POPULATIONS},
                                 "sides": [pf.public_side(s) for s in sides]},
              "controls.json": controls(committed)}
    scenarios = {s["scenario"] for s in sides}
    for name, data in public.items():
        problems = sp.public_problems(data, private, scenarios)
        if problems:
            raise SystemExit(f"the public sanitizer refused {name}: {len(problems)} findings; nothing written")
    texts = {name: dump(data) for name, data in public.items()}
    for name, text in texts.items():
        if len(text.encode("utf-8")) > PUBLIC_LIMIT:
            raise SystemExit(f"{name} exceeds the public size limit; nothing written")
    blob = gzip.compress(json.dumps([{**s["private"], "label": s["label"], "departure_episodes": s["departure_episodes"]}
                                     for s in sides], sort_keys=True, default=str).encode("utf-8"), mtime=0)
    return texts, blob


def run(check: bool, workers: int) -> int:
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = input_problems(committed)
    if problems:
        print("inputs or frozen sources differ from their pins; refusing to run:", problems[:5])
        return 1
    texts, blob = build(committed, workers)
    if check:
        same = all((OUT / n).exists() and (OUT / n).read_text(encoding="utf-8") == t for n, t in texts.items())
        same &= (PRIVATE / "preflight-private.json.gz").exists() \
            and (PRIVATE / "preflight-private.json.gz").read_bytes() == blob
        print("preflight identical" if same else "MISMATCH")
        return 0 if same else 1
    if any((OUT / n).exists() for n in texts):
        print("preflight results exist; refusing to overwrite")
        return 1
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "preflight-private.json.gz").write_bytes(blob)
    verdict = json.loads(texts["preflight.json"])
    print("wrote", ", ".join(sorted(texts)), "| disposition", verdict["disposition"], verdict["inert_configurations"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--check", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("--check", action="store_true")
    p.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.command == "freeze":
        text = dump(freeze())
        if args.check:
            same = INPUTS.exists() and INPUTS.read_text(encoding="utf-8") == text
            print("preflight inputs identical" if same else "MISMATCH")
            return 0 if same else 1
        OUT.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", INPUTS.relative_to(REPO_ROOT).as_posix())
        return 0
    return run(args.check, args.workers)


if __name__ == "__main__":
    sys.exit(main())
