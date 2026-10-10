"""Sprint 31 historical feasibility preflight of ``t13-keep-one-k2`` (``docs/SPRINT31_T13_K2_PILOT.md``, section 4).
Offline only; runs on the evaluation server.

    python scripts/s31_preflight.py freeze [--check]
    python scripts/s31_preflight.py run [--check] [--workers N]

``freeze`` writes ``evaluation/s31-t13-k2/preflight-inputs.json``: Sprint 23's committed job list with its own pins (the
same populations as Sprint 30), the SHA-256 of Sprint 23's ``inputs.json``, of Sprint 30's frozen preflight inputs,
result and historical controls (``evaluation/s30-t13-k1/``), the normalised SHA-256 of every source the preflight
depends on, the anchors, the stop rule and the pilot's fixed inert configurations.

``run`` refuses unless every pin matches. It reads every side through Sprint 23's loader and ``baseline-v2``
reconstruction (unchanged, by way of Sprint 30's driver helpers), applies Sprint 30's frozen analysis with the K2 rule
and the K2 restatement (``evaluation/s31_preflight.py``) and writes the public ``preflight.json`` (aggregates, steps and
labels; sanitised, or nothing is written) and the private rows ``local/diagnostics/s31/preflight-private.json.gz``.
``--check`` rebuilds and compares instead of writing.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import multiprocessing
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT = REPO_ROOT / "evaluation" / "s31-t13-k2"
INPUTS = OUT / "preflight-inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s31"
S23_INPUTS = REPO_ROOT / "evaluation" / "s23-t2-policy-design" / "inputs.json"
S30 = REPO_ROOT / "evaluation" / "s30-t13-k1"
SCHEMA_INPUTS = "miaosuan-s31-preflight-inputs/1"
SOURCES = ("src/miaosuan_agent/experiments/t13_keep_one_k2.py",
           "src/miaosuan_agent/experiments/exploratory_addon.py",
           "src/miaosuan_agent/experiments/t9_batch.py",
           "src/miaosuan_agent/evaluation/s31_preflight.py",
           "src/miaosuan_agent/evaluation/s30_preflight.py",
           "scripts/s31_preflight.py",
           "scripts/s30_preflight.py",
           "scripts/s23_t2_design.py",
           "src/miaosuan_agent/evaluation/s12_timeline.py",
           "src/miaosuan_agent/evaluation/s12_screen.py",
           "src/miaosuan_agent/evaluation/s27_probe.py")
S30_FILES = ("preflight-inputs.json", "preflight.json", "controls.json")
PUBLIC_LIMIT = 90_000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalised(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def s30_driver() -> Any:
    spec = importlib.util.spec_from_file_location("s31_s30_driver", REPO_ROOT / "scripts" / "s30_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def freeze() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s31_preflight as kp
    committed = json.loads(S23_INPUTS.read_text(encoding="utf-8"))
    problems = s30_driver().s23().file_problems(committed["jobs"])
    if problems:
        raise SystemExit(f"refused: Sprint 23's pinned inputs differ: {problems[:5]}")
    return {"schema": SCHEMA_INPUTS, "study_id": kp.STUDY_ID, "engine_sessions": 0,
            "s23_inputs": {"path": S23_INPUTS.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(S23_INPUTS)},
            "sprint30": {name: sha256(S30 / name) for name in S30_FILES},
            "jobs": committed["jobs"],
            "sources": {rel: normalised(REPO_ROOT / rel) for rel in SOURCES},
            "anchors": kp.ANCHORS, "dispositions_first_match": list(kp.DISPOSITIONS),
            "pilot_inert_configurations": [list(c) for c in kp.PILOT_INERT],
            "genuine_populations": list(kp.GENUINE), "settle_limit_steps": kp.SETTLE_LIMIT}


def input_problems(committed: Mapping[str, Any]) -> List[str]:
    problems = []
    if sha256(REPO_ROOT / committed["s23_inputs"]["path"]) != committed["s23_inputs"]["sha256"]:
        problems.append(committed["s23_inputs"]["path"])
    for name, digest in committed["sprint30"].items():
        if sha256(S30 / name) != digest:
            problems.append(f"evaluation/s30-t13-k1/{name}")
    problems += s30_driver().s23().file_problems(committed["jobs"])
    for rel, digest in committed["sources"].items():
        if normalised(REPO_ROOT / rel) != digest:
            problems.append(rel)
    return problems


def worker(job: Mapping[str, Any]) -> List[Tuple[Dict[str, Any], List[str]]]:
    from miaosuan_agent.boundary import Observation, Origin
    from miaosuan_agent.decision.routing import Router
    from miaosuan_agent.evaluation import residual516 as rd
    from miaosuan_agent.evaluation import s31_preflight as kp
    from miaosuan_agent.experiments import t13_keep_one_k2 as k2
    s30 = s30_driver()
    driver = s30.s23()
    scenario, _, costs = driver.scenario_costs(job)
    travel = k2.router_travel(Router(costs))
    out = []
    for _, seat, faction, stream in driver.decisions(job):
        decide = driver.baseline(costs)
        text, condition = s30.label(job, faction, scenario)

        def rows():
            for raw, recorded, memory in stream:
                actions = decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
                yield raw, rd.plain(list(recorded)), rd.plain(list(actions))

        meta = {"population": job["population"], "label": text, "scenario": scenario, "condition": condition,
                "faction": faction}
        summary, private = kp.analyse_side(meta, rows(), costs, travel)
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


def build(committed: Mapping[str, Any], workers: int) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s27_probe as sp
    from miaosuan_agent.evaluation import s31_preflight as kp
    sides, private = compute(committed, workers)
    fid = s30_driver().anchors(sides)
    verdict = kp.disposition(all(a["equal"] for a in fid.values()), sides)
    head = {"schema": kp.SCHEMA, "study_id": kp.STUDY_ID, "inputs_sha256": sha256(INPUTS), "engine_sessions": 0}
    boundary = ("Sprint 30's evidence boundary, unchanged: HH and HI are genuine baseline-v2 trajectories (HH's opponent "
                "was the T9-v3 candidate, not baseline-v2; HI's the inert control); H0 is baseline-v0's trajectory with "
                "baseline-v2 reconstructed. A first divergence is a valid action-level fact in HH and HI, and in H0 "
                "only on a supported prefix. Withholdings after a side's first divergence lie on recorded states the "
                "candidate would not reach and are post-divergence diagnostics only. Onward labels are historical.")
    public = {"preflight.json": {**head, "evidence_boundary": boundary, "fidelity": fid, **verdict,
                                 "pilot_inert_configurations": [list(c) for c in kp.PILOT_INERT],
                                 "genuine_opportunities": kp.opportunities(sides),
                                 "populations": {p: kp.pooled([s for s in sides if s["population"] == p])
                                                 for p in kp.POPULATIONS},
                                 "sides": [kp.public_side(s) for s in sides]}}
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
    print("wrote", ", ".join(sorted(texts)), "| disposition", verdict["disposition"])
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
