"""Build, or check, the manifest of a registered exploratory tactical screen.

    python scripts/build_tactical_screen.py --screen tactical-screen-deployment-split-1 [--check]

Inputs are committed: the shoot-reservation experiment's manifest (baseline-v2's policy source, the scenarios,
players, caps and randomness procedure) and the runtime thread qualification's results (runtime and qualified
scheduler, which must equal the one this checkout computes). The candidate's policy source is computed from this
checkout. ``--check`` fails unless the committed manifest is byte-identical to a fresh build.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import runtime_threads as rt  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation import tactical_screen as ts  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import deployment_split as dsp  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"

SCREENS: Dict[str, Dict[str, Any]] = {
    "tactical-screen-deployment-split-1": {
        "candidate_module": "experiments/deployment_split.py", "candidate_id": dsp.CANDIDATE_ID,
        "candidate_label": "deployment disaggregation (T1)", "n": 3,
        "texts": {
            "status": "EXPLORATORY - NOT ELIGIBLE FOR BASELINE PROMOTION",
            "family": "T1 deployment disaggregation (docs/TACTICAL_FRONTIER.md)",
            "hypothesis": "Splitting every eligible ground operator into operators of one vehicle or squad during deployment "
                          "(two split rounds before ending deployment) improves baseline-v2's terminal score margin, against "
                          "baseline-v2 and against the inert control.",
            "parent": "baseline-v2 (policy source 7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae), on "
                      "baseline-v1-runtime-r2",
            "allowed_delta": "one new module, experiments/deployment_split.py: in the deployment stage, before ending "
                             "deployment, emit the deployment split action (type 314) for every eligible operator; repeat for "
                             "the resulting eligible operators in the next deployment decision; then end deployment through "
                             "baseline-v2's own rule (after two rounds whatever remains). Memory carries the round count.",
            "applicability": "an operator the seat controls, on the map, of type 1 or 2, sub_type not 3 (artillery), blood at "
                             "least 2; every frozen scenario side has such operators (evaluation/tactical-frontier-1/census.json)",
            "observables": "the seat's own operators (type, sub_type, blood), its role_and_grouping_info entry and the stage",
            "action_semantics": "{actor: seat, obj_id: operator, type: 314}; documented as an instantaneous pre-game action and "
                                "absent from valid_actions by design; per the platform rules a split of 4 gives 2 + 2, of 3 "
                                "gives 2 + 1, of 2 gives 1 + 1, each half keeping the original ammunition",
            "expected_mechanism": "more independent operators, each with full ammunition: more simultaneous shots and more "
                                  "objectives reachable at once; offset by weaker shots and stacked-target modifiers",
            "risks": ["the engine refuses type 314 on 4.1.0", "the new operators are not controllable by the seat",
                      "the stacking limit of 4 own ground units per hex refuses splits", "stacked new operators take extra damage",
                      "more operators raise decision latency", "unexpected fields break the observation contract"],
            "forbidden": ["any play-stage change", "scenario, map or unit identifiers", "any change to baseline-v2's files",
                          "tuning after results", "changing n or the configurations after registration"],
            "smoke": {"games": "one game per frozen scenario, the candidate as red against the inert control (8 games)",
                      "purpose": "diagnostic, 8 workers, the read-only step capture (batch, feedback, units appearing, "
                                 "blood changes)",
                      "pass_rule": "PASS if in at least one game a deployment split is followed by new operators of the seat "
                                   "that the candidate later commands, deployment ends, and no game fails or records a "
                                   "contract error; BLOCKED BY ENGINE SEMANTICS if no split takes effect in any game or no "
                                   "new operator is ever commanded",
                      "records": "per game: splits emitted, engine errors for them, operators appearing during deployment, "
                                 "deployment decisions, play-start operator count, new operators that acted"},
            "ab_design": "8 frozen scenarios; arms baseline-v2 and candidate under C1, C2 and C3; head-to-head H1 (candidate red) "
                         "and H2 (candidate blue); n = 3 per configuration: 144 arm games and 48 head-to-head games; fresh "
                         "games for both arms in one interleaved queue; runtime-r2, 32 workers, the qualified scheduler",
            "metrics": {"primary_exploratory": ["head-to-head candidate margin (candidate total minus opponent total), per "
                                                "scenario over H1 and H2", "vs-inert active margin, candidate arm minus "
                                                "baseline arm, per C2 and C3 configuration"],
                        "components": ["occupy, attack and remain scores", "head-to-head wins, draws and losses"],
                        "mechanism": ["deployment splits emitted per candidate seat", "distinct controllable operators "
                                      "(units_seen) and operators that acted, candidate against baseline seats"],
                        "safety": ["project-gate rejections", "contract errors", "failed or capped games", "engine refusal "
                                   "classes and new classes", "code 1804", "duplicate same-target shots", "decision latency"]},
            "disposition_rule": [
                "BLOCKED BY ENGINE SEMANTICS if the smoke fails its pass rule; the A/B does not run",
                "REJECT TACTIC if a candidate game fails or is capped, a candidate seat records a contract error or a gate "
                "rejection, or the pooled head-to-head mean candidate margin is below 0 with the scenario mean below 0 in "
                "at least 5 of 8 scenarios",
                "ADVANCE TO CONFIRMATION if none of that, the mechanism is active (candidate seats see more controllable "
                "operators than the baseline seats of the same scenario, condition and side in at least 75% of those cells), "
                "the pooled head-to-head mean candidate margin is above 0 with the scenario mean above 0 in at least 5 of 8 "
                "scenarios, and the vs-inert difference is at least 0 in at least 8 of the 16 C2 and C3 configurations",
                "REVISE BEFORE CONFIRMATION otherwise"],
            "stopping": ["dispatch stops after 3 consecutive games that do not complete; no game is retried, replaced or "
                         "overwritten", "the candidate is frozen at its registered digest; the same runtime for both arms",
                         "no stop because results look good or bad"],
        },
    },
}


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def current_scheduler() -> str:
    spec = importlib.util.spec_from_file_location("run_game_pool", REPO_ROOT / "scripts" / "run_game_pool.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scheduler_identity()


def policy_source(sources: tuple) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def build(screen_id: str) -> Dict[str, Any]:
    screen = SCREENS[screen_id]
    shoot = REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json"
    results = REPO_ROOT / "evaluation" / rt.PLAN_ID / "results.json"
    shoot_manifest = load(shoot)
    baseline_source = policy_source(V2_SOURCES)
    if baseline_source["sha256"] != V2_DIGEST:
        raise SystemExit(f"baseline-v2's source is {baseline_source['sha256']}, not the frozen digest")
    baseline = {"id": sx.CANDIDATE_ID, "label": "baseline-v2", "policy_source": baseline_source}
    candidate = {"id": screen["candidate_id"], "label": screen["candidate_label"],
                 "policy_source": policy_source(V2_SOURCES + (screen["candidate_module"],))}
    manifest = ts.build(screen_id, screen["texts"], shoot_manifest, mf.digest(shoot_manifest), load(results),
                        hashlib.sha256(results.read_bytes()).hexdigest(), baseline, candidate, screen["n"])
    if manifest["execution"]["scheduler"] != current_scheduler():
        raise SystemExit("the production scheduler of this checkout is not the qualified one")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--screen", required=True, choices=sorted(SCREENS))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    out = REPO_ROOT / "evaluation" / args.screen / "manifest.json"
    manifest = build(args.screen)
    text = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    digest = ts.digest(manifest)
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()} sha256(canonical)={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
