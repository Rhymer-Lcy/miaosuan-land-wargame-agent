"""Sprint 32 historical feasibility preflight of ``t7-b1-stop-engage-1`` (``docs/SPRINT32_T7_B1_PREFLIGHT.md``,
sections 4 and 5). Offline only; runs on the evaluation server, where the private records are.

    python scripts/s32_preflight.py freeze [--check]
    python scripts/s32_preflight.py run [--check] [--workers N]

``freeze`` writes ``evaluation/s32-t7-b1/preflight-inputs.json``: Sprint 23's committed job list (H0, HH, HI) with
its own pins and the SHA-256 of Sprint 23's ``inputs.json``; the two HX jobs (the ``baseline-v2`` seats of sessions
2797 and 2800: record and full-step timeline, each by SHA-256); the normalised SHA-256 of every source the preflight
depends on; the fidelity anchors; the proposed configurations; and the SHA-256 of every historical control record read
for the record-level description (the registered shoot-reservation experiment's group C games of five inert
configurations).

``run`` refuses unless every pin matches. It reads every side through Sprint 23's own loader and ``baseline-v2``
reconstruction (``scripts/s23_t2_design.py``: ``decisions``, ``baseline``; unchanged; an HX job is read through the
same timeline branch as HH), applies the candidate's frozen rule and the independent check
(``evaluation/s32_preflight.py``) and writes the public ``preflight.json`` (aggregates, steps, labels; sanitised, or
nothing is written) and the private rows ``local/diagnostics/s32/preflight-private.json.gz``. ``--check`` rebuilds and
compares instead of writing.
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

OUT = REPO_ROOT / "evaluation" / "s32-t7-b1"
INPUTS = OUT / "preflight-inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s32"
S23_INPUTS = REPO_ROOT / "evaluation" / "s23-t2-policy-design" / "inputs.json"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
CONTROL_GAMES = LOCAL_EVAL / "baseline-v2-candidate-shoot-target-reservation" / "games"
SCHEMA_INPUTS = "miaosuan-s32-preflight-inputs/1"
V2_ID = "baseline-v2-candidate-shoot-target-reservation"
#: The two later genuine baseline-v2 seats in 2130511121 with a full-step timeline (Sprints 27 and 31).
HX_GAMES = (("s27-t6s-probe-1", "2130511121.H2.s27-t6s-probe-1.p01", "HX s27-p01"),
            ("s31-t13-k2-pilot-1", "2130511121.H1.s31-t13-k2-pilot-1.p03", "HX s31-p03"))
#: Record-level description: (scenario, condition, baseline-v2 seat colour) of the inert configurations read.
CONTROL_CONFIGS = (("2130511121", "C2", "red"), ("2130511121", "C3", "blue"), ("2120531121", "C3", "blue"),
                   ("1930331196", "C2", "red"), ("1930331196", "C3", "blue"))
CONTROL_REPS = 15
SOURCES = ("src/miaosuan_agent/experiments/t7_b1_stop_engage.py",
           "src/miaosuan_agent/experiments/exploratory_addon.py",
           "src/miaosuan_agent/evaluation/s32_preflight.py",
           "src/miaosuan_agent/evaluation/t7_candidates.py",
           "src/miaosuan_agent/evaluation/t7_visibility.py",
           "src/miaosuan_agent/evaluation/s12_timeline.py",
           "src/miaosuan_agent/evaluation/s27_probe.py",
           "scripts/s32_preflight.py",
           "scripts/s23_t2_design.py")
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
    spec = importlib.util.spec_from_file_location("s32_s23_driver", REPO_ROOT / "scripts" / "s23_t2_design.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hx_jobs() -> List[Dict[str, Any]]:
    out = []
    for folder, game, label in HX_GAMES:
        record = LOCAL_EVAL / folder / "games" / f"{game}.json"
        timeline = LOCAL_EVAL / folder / "capture" / f"{game}.timeline.pkl"
        out.append({"population": "HX", "game": game, "label": label,
                    "record": {"path": record.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(record)},
                    "timeline": {"path": timeline.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(timeline)}})
    return out


def control_files() -> List[Tuple[str, str, str, Path]]:
    return [(sid, cond, colour, CONTROL_GAMES / f"{sid}.{cond}.C.r{r}.json")
            for sid, cond, colour in CONTROL_CONFIGS for r in range(1, CONTROL_REPS + 1)]


# ------------------------------------------------------------------------------------------------
# freeze


def freeze() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s32_preflight as pf
    committed = json.loads(S23_INPUTS.read_text(encoding="utf-8"))
    problems = s23().file_problems(committed["jobs"])
    if problems:
        raise SystemExit(f"refused: Sprint 23's pinned inputs differ: {problems[:5]}")
    return {"schema": SCHEMA_INPUTS, "study_id": pf.STUDY_ID, "engine_sessions": 0,
            "s23_inputs": {"path": S23_INPUTS.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(S23_INPUTS)},
            "jobs": committed["jobs"] + hx_jobs(),
            "sources": {rel: normalised(REPO_ROOT / rel) for rel in SOURCES},
            "anchors": pf.ANCHORS, "side_games": pf.SIDE_GAMES,
            "dispositions_first_match": list(pf.DISPOSITIONS),
            "proposed_configurations": [list(c) for c in pf.PROPOSED],
            "controls": {"configurations": [list(c) for c in CONTROL_CONFIGS],
                         "records": {path.name: sha256(path) for _, _, _, path in control_files()}}}


def input_problems(committed: Mapping[str, Any]) -> List[str]:
    problems = []
    if sha256(REPO_ROOT / committed["s23_inputs"]["path"]) != committed["s23_inputs"]["sha256"]:
        problems.append(committed["s23_inputs"]["path"])
    driver = s23()
    problems += driver.file_problems([j for j in committed["jobs"] if j["population"] != "HX"])
    for job in committed["jobs"]:
        if job["population"] == "HX":
            for part in ("record", "timeline"):
                path = REPO_ROOT / job[part]["path"]
                if not path.exists() or sha256(path) != job[part]["sha256"]:
                    problems.append(job[part]["path"])
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
    if job["population"] == "HX":
        return f"{job['label']} baseline-v2 {colour}", condition
    return f"HI {scenario} {condition} baseline-v2 {colour}", condition


def worker(job: Mapping[str, Any]) -> List[Tuple[Dict[str, Any], List[str]]]:
    from miaosuan_agent.boundary import Observation, Origin
    from miaosuan_agent.evaluation import residual516 as rd
    from miaosuan_agent.evaluation import s32_preflight as pf
    driver = s23()
    # An HX job is read through Sprint 23's timeline branch, unchanged (the same capture layout as HH).
    read_as = dict(job, population="HH") if job["population"] == "HX" else job
    scenario, _, costs = driver.scenario_costs(read_as)
    out = []
    for _, seat, faction, stream in driver.decisions(read_as):
        decide = driver.baseline(costs)
        text, condition = label(job, faction, scenario)

        def rows():
            for raw, recorded, memory in stream:
                actions = decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
                yield raw, rd.plain(list(recorded)), rd.plain(list(actions))

        meta = {"population": job["population"], "label": text, "scenario": scenario, "condition": condition,
                "faction": faction, "seat": seat}
        summary, private = pf.analyse_side(meta, rows())
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
    from miaosuan_agent.evaluation import s32_preflight as pf
    order = {p: i for i, p in enumerate(pf.POPULATIONS)}
    sides.sort(key=lambda s: (order[s["population"]], s["label"]))
    return sides, private


def anchors(sides: List[Mapping[str, Any]]) -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s32_preflight as pf
    pop = {p: [s for s in sides if s["population"] == p] for p in pf.POPULATIONS}
    got = {"H0 decisions": sum(s["decisions"] for s in pop["H0"]),
           "H0 play decisions": sum(s["play_decisions"] for s in pop["H0"]),
           "H0 v2 differs from recorded v0": sum(s["baseline_v2_differs_from_recorded"] for s in pop["H0"]),
           "HH decisions": sum(s["decisions"] for s in pop["HH"]), "HI decisions": sum(s["decisions"] for s in pop["HI"]),
           "HX decisions": sum(s["decisions"] for s in pop["HX"])}
    out = {k: {"published": v, "preflight": got[k], "equal": got[k] == v} for k, v in pf.ANCHORS.items()}
    for p in pf.GENUINE:
        same = all(s["baseline_v2_differs_from_recorded"] == 0 for s in pop[p])
        out[f"{p} baseline-v2 reconstruction equal to the recorded seat at every decision"] = {
            "published": True, "preflight": same, "equal": same}
    counts = [len(pop[p]) for p in pf.POPULATIONS]
    expected = [pf.SIDE_GAMES[p] for p in pf.POPULATIONS]
    out["side-games HH, HX, HI, H0"] = {"published": expected, "preflight": counts, "equal": counts == expected}
    return out


# ------------------------------------------------------------------------------------------------
# record-level description of the inert configurations


def frac(value: Fraction) -> Any:
    return value.numerator if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def control_rows() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "source": "the registered shoot-reservation experiment's group C games (baseline-v2 against the inert "
                  "control), fifteen per configuration; game records only (no full-step observation): issued shots "
                  "and moves of the baseline-v2 seat, the step of its first shot, its occupy score and margin",
        "configurations": {}}
    for sid, cond, colour in CONTROL_CONFIGS:
        records = [json.loads((CONTROL_GAMES / f"{sid}.{cond}.C.r{r}.json").read_text(encoding="utf-8"))
                   for r in range(1, CONTROL_REPS + 1)]
        if any(r["status"] != "COMPLETED" or str(r["scenario_id"]) != sid or r["condition"] != cond for r in records):
            raise SystemExit(f"{sid} {cond}: a control record is incomplete or mislabelled")
        faction = 0 if colour == "red" else 1
        seats = [next(s for s in r["seats"] if s["faction"] == faction) for r in records]
        if any(s["policy"] != V2_ID for s in seats):
            raise SystemExit(f"{sid} {cond}: the {colour} seat is not baseline-v2")
        other = "blue" if colour == "red" else "red"
        shots = sorted(int(s["actions_by_type"].get("2", 0)) for s in seats)
        moves = sorted(int(s["actions_by_type"].get("1", 0)) for s in seats)
        first = sorted(s["first_step_by_type"]["2"] for s in seats if "2" in s["first_step_by_type"])
        occupy = sorted(r["final_scores"][f"{colour}_occupy"] for r in records)
        margin = sorted(r["final_scores"][f"{colour}_total"] - r["final_scores"][f"{other}_total"] for r in records)
        out["configurations"][f"{sid} {cond} baseline-v2 {colour}"] = {
            "games": len(records), "shots_per_game": {"min": shots[0], "median": statistics.median(shots),
                                                      "max": shots[-1]},
            "moves_per_game": {"min": moves[0], "median": statistics.median(moves), "max": moves[-1]},
            "games_with_a_shot": len(first),
            "first_shot_step": None if not first else {"min": first[0], "median": statistics.median(first),
                                                       "max": first[-1]},
            "occupy": {"min": occupy[0], "max": occupy[-1]},
            "margin": {"min": margin[0], "mean": frac(Fraction(sum(margin), len(margin))), "max": margin[-1]}}
    return out


# ------------------------------------------------------------------------------------------------
# run


BOUNDARY = ("HH, HX and HI are genuine baseline-v2 trajectories (HH's opponent was the T9-v3 candidate, HX's the T6-S "
            "and K2 candidates, HI's the inert control); H0 is baseline-v0's trajectory with baseline-v2 "
            "reconstructed. A first divergence (a side's first stop) is a valid action-level fact in HH, HX and HI, "
            "and in H0 only on a supported prefix. Every later stop lies on recorded states that a game with the "
            "candidate would not reach and is a descriptive diagnostic only. Recorded-trajectory descriptions say "
            "what happened without a stop; they are not effects of a stop. No engine behaviour of a stop on a "
            "traversing unit is observed anywhere in these records.")


def build(committed: Mapping[str, Any], workers: int) -> Tuple[str, bytes]:
    from miaosuan_agent.evaluation import s27_probe as sp
    from miaosuan_agent.evaluation import s32_preflight as pf
    sides, private = compute(committed, workers)
    fid = anchors(sides)
    verdict = pf.disposition(all(a["equal"] for a in fid.values()), sides)
    public = {"schema": pf.SCHEMA, "study_id": pf.STUDY_ID, "inputs_sha256": sha256(INPUTS), "engine_sessions": 0,
              "evidence_boundary": BOUNDARY, "fidelity": fid, **verdict,
              "populations": {p: pf.pooled([s for s in sides if s["population"] == p]) for p in pf.POPULATIONS},
              "sides": [pf.public_side(s) for s in sides],
              "record_level_inert_configurations": control_rows()}
    scenarios = {s["scenario"] for s in sides} | {c[0] for c in CONTROL_CONFIGS}
    problems = sp.public_problems(public, private, scenarios)
    if problems:
        raise SystemExit(f"the public sanitizer refused preflight.json: {len(problems)} findings; nothing written")
    text = dump(public)
    if len(text.encode("utf-8")) > PUBLIC_LIMIT:
        raise SystemExit("preflight.json exceeds the public size limit; nothing written")
    blob = gzip.compress(json.dumps([{**s["private"], "label": s["label"]} for s in sides], sort_keys=True,
                                    default=str).encode("utf-8"), mtime=0)
    return text, blob


def run(check: bool, workers: int) -> int:
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = input_problems(committed)
    if problems:
        print("inputs or frozen sources differ from their pins; refusing to run:", problems[:5])
        return 1
    text, blob = build(committed, workers)
    target, private = OUT / "preflight.json", PRIVATE / "preflight-private.json.gz"
    if check:
        same = target.exists() and target.read_text(encoding="utf-8") == text \
            and private.exists() and private.read_bytes() == blob
        print("preflight identical" if same else "MISMATCH")
        return 0 if same else 1
    if target.exists():
        print("preflight results exist; refusing to overwrite")
        return 1
    target.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    private.write_bytes(blob)
    verdict = json.loads(text)
    print("wrote preflight.json | disposition", verdict["disposition"], verdict["proposed_configurations"],
          verdict["verified_inert_configurations"])
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
