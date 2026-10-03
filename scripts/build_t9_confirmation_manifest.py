"""Build, or check, the registered manifest of the T9 confirmatory study ``t9-confirmation-1``.

    python scripts/build_t9_confirmation_manifest.py [--check]

Every input is committed: the shoot-reservation experiment's manifest (the frozen scenarios with their input digests,
players, caps and randomness procedure), the runtime thread qualification's results (the qualified scheduler, whose
identity must equal the one this checkout computes), the policy sources of ``baseline-v2`` and the candidate (which
must equal the frozen digests), the line-ending-normalised SHA-256 of every implementation and test file the study
relies on, and the normalised SHA-256 of its pre-registration outputs (planning, validation and mutation). Generation is
deterministic; ``--check`` fails unless the committed manifest is byte-identical to a fresh build.
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
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t9_allocation as t9  # noqa: E402

OUT = REPO_ROOT / "evaluation" / tc.STUDY_ID / "manifest.json"
V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
T9_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_allocation.py")
FILES = (
    "src/miaosuan_agent/evaluation/t9_confirmation.py",
    "scripts/build_t9_confirmation_manifest.py",
    "scripts/run_t9_confirmation.py",
    "scripts/run_t9_confirmation_game.py",
    "scripts/t9_confirmation_analysis.py",
    "scripts/t9_confirmation_planning.py",
    "scripts/t9_confirmation_validation.py",
    "scripts/run_evaluation.py",
    "scripts/run_game_pool.py",
    "src/miaosuan_agent/evaluation/scheduler.py",
    "src/miaosuan_agent/evaluation/game.py",
    "src/miaosuan_agent/evaluation/effects.py",
    "src/miaosuan_agent/evaluation/refusals.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/stats.py",
    "src/miaosuan_agent/evaluation/manifest.py",
    "src/miaosuan_agent/evaluation/execution.py",
    "src/miaosuan_agent/evaluation/randomness.py",
    "src/miaosuan_agent/engine_install.py",
)
TESTS = (
    "tests/test_t9_confirmation.py",
    "tests/test_t9_confirmation_registration.py",
    "tests/test_real_t9_confirmation.py",
    "scripts/mutate_t9_confirmation.py",
)
PUBLIC_INPUTS = (
    f"evaluation/{tc.STUDY_ID}/planning.json",
    f"evaluation/{tc.STUDY_ID}/validation.json",
    f"evaluation/{tc.STUDY_ID}/mutation.json",
    "docs/T9_CONFIRMATION_PROPOSAL.md",
    "evaluation/s8-t9-v1-rep/manifest.json",
)

TEXTS: Dict[str, Any] = {
    "status": "CONFIRMATORY - REGISTERED BEFORE THE FIRST ENGINE SESSION; NOT ELIGIBLE FOR BASELINE PROMOTION",
    "question": "Does t9-capacity-allocation-v1, unchanged from Sprint 8, improve baseline-v2's terminal score margin "
                "head to head in scenario 2130511121, and is it free of systemic failures and of material "
                "deterioration where its rule rarely binds?",
    "hypothesis": "In scenario 2130511121 head to head, the equally seat-weighted improvement of the candidate's "
                  "terminal margin over fresh baseline-v2 C1 mirror margins of the same seat is greater than 0.",
    "margin_convention": "a seat's terminal margin is its side's <side>_total minus the other side's total in the "
                         "engine's final scores (the engine's own <side>_win, checked per game); it is zero-sum, so "
                         "in a C1 game the blue margin is minus the red margin",
    "primary_estimand": "Delta = 1/2 (mean H1 red margin - mean C1 red margin) + 1/2 (mean H2 blue margin - mean C1 "
                        "blue margin) over the 45 phase-A games; computed as 1/2 mean(H1) + 1/2 mean(H2) - mean(c) "
                        "with c = (red + blue) / 2 per C1 game, so each C1 game is one unit carrying its correlated "
                        "pair of seat outcomes; under the margin convention c = 0 for every game, so the C1 games "
                        "cancel from Delta and from every resample (a property of the data, checked per game)",
    "interval": "95% studentized bootstrap (bootstrap-t) interval: the H1, H2 and C1 strata are resampled "
                "independently with replacement at the game level (C1 games as pairs), 20,000 resamples, seed "
                "derived from 20261003 and the estimand's name, nearest-rank quantiles of t* = (Delta* - Delta) / "
                "SE*, SE the plug-in standard error sqrt(sum w^2 s^2 / n); the percentile interval of the same "
                "resamples and the Welch interval are reported as non-decisive sensitivity",
    "primary_test": "tested once, after all 45 phase-A games, only if every game completed and integrity holds; "
                    "SUPPORTED if the interval's lower limit is strictly above 0",
    "seat_contrasts": "secondary, descriptive: H1 red minus C1 red and H2 blue minus C1 blue, each with the same "
                      "interval procedure (C1 resampled by game)",
    "secondary": [
        "phase B: per large scenario and condition (C2, C3), mean candidate margin minus mean baseline-v2 margin "
        "against the inert control, studentized bootstrap interval with the two arms as strata (6 contrasts)",
        "phase C: per scenario (2120531121, 1930331196), the primary-form seat-average contrast and the two seat "
        "contrasts, as in phase A",
        "phase D: per small scenario and condition, the mean difference, each arm's values, the range of pairwise "
        "differences and the Welch interval where defined (3 games per arm: an estimate, not a test)",
        "all secondary analyses are descriptive: no multiplicity adjustment is applied because no secondary claim "
        "is confirmatory; no secondary result can replace the primary endpoint; configurations are never pooled",
    ],
    "phase_gates": {
        "A": "CONTINUE to D only if all 45 games completed and are accounted for, integrity holds (ledger, record "
             "identities, capture digests and cross-checks), there is no systemic failure (contract errors, "
             "project-gate rejections, replay mismatches, add-on errors, observer errors, a candidate refusal class "
             "unknown to baseline-v2) and the primary interval's lower limit is strictly above 0; otherwise STOP",
        "D": "CONTINUE to B only if all 60 games completed, integrity holds, there is no systemic failure and no "
             "configuration's mean margin difference (candidate minus baseline-v2) is below -10 (adverse signal); "
             "otherwise STOP with the safety result recorded (NEEDS_REVISION for an adverse signal)",
        "B": "CONTINUE to C only if all 180 games completed, integrity holds, there is no systemic failure and no "
             "configuration's interval upper limit is below -10 (adverse signal); otherwise STOP",
        "C": "the last phase: completion, integrity and systemic failures are reported; no further games",
    },
    "flags": "descriptive, never a stop on their own: latency (a candidate configuration's largest per-game p99 "
             "above 10 ms or any decision above 5,000 ms), idle (against the inert control, the candidate's mean "
             "count of ground units that never leave their start hex exceeds baseline-v2's by 1 or more) and "
             "objectives (the candidate's mean objectives held at the end are 0.5 or more below baseline-v2's)",
    "failure_handling": [
        "no game is retried, replaced or added; records and captures are never overwritten",
        "a game that does not complete (FAIL, CAPPED, interrupted, missing record) keeps its record and fails its "
        "phase's gate; the primary is then NOT TESTED and its figures over completed games are labelled descriptive; "
        "a non-completed C1 game would change no seat-average figure (its contribution is 0)",
        "a started game without a record, a recovered session, an installation refusal or 3 consecutive games that "
        "did not complete stop dispatch (the qualified scheduler's rules); the phase's gate fails",
        "a missing or digest-mismatched capture of a completed game leaves its margin in the analysis and fails the "
        "phase's integrity, so the gate fails",
        "an execution-affecting code change needs a new registration; no phase runs with a pinned file changed",
        "the cumulative cap of 375 sessions after ledger session 2487 is checked before each phase and by each game",
    ],
    "integrity": [
        "every session after ledger session 2487 belongs to a scheduled game of this study under the registered "
        "manifest, is opened once, closed with integrity ok, and continues the previous record's state; none unclosed",
        "every record carries the manifest digest, a clean harness, the study id, the registered policy sources, "
        "runtime baseline-v1-runtime-r2 with OPENBLAS_NUM_THREADS=1, a shared session of 32 workers under the "
        "qualified scheduler, engine 4.1.0, CPython 3.10 and session-close integrity ok; its session equals the "
        "ledger's for its game",
        "both capture files of a completed game match the digests its record carries, and the study's capture "
        "agrees with the Sprint 8 exploratory capture (waiting units, largest commitment, add-on changes and skips) "
        "and with the record (move orders, steps)",
        "the margin of every completed game equals the engine's <side>_win for both sides",
    ],
    "mechanism": "per policy seat (descriptive): move orders emitted, kept, re-assigned, reverted and withheld, "
                 "refused re-assigned moves; withheld units and their longest run of consecutive withheld decisions; "
                 "ground units idle at their start hex (count never departed, unit-steps, maximum, units idle half "
                 "the play stage or more); units waiting in front of full hexes; largest objective commitment; "
                 "objectives held over time, at the end and value-weighted; units lost; refusal classes; contract "
                 "errors, gate rejections, add-on errors; decision latency",
    "disposition": [
        "PRIMARY_SUPPORTED: primary SUPPORTED and every phase that ran CLEAN (no systemic failure, no adverse signal)",
        "PRIMARY_SUPPORTED_NEEDS_REVISION: primary SUPPORTED but a later phase had a systemic failure or adverse signal",
        "PRIMARY_NOT_SUPPORTED: primary tested, lower limit not above 0 (a valid outcome; the study stops)",
        "INCONCLUSIVE_PROTOCOL_INCOMPLETE: primary not tested (incomplete phase A or integrity failure)",
        "generality is reported descriptively from phases B and C (counts of configurations with estimates and "
        "intervals above or below 0); mechanism and flags are descriptive; no outcome promotes a baseline",
    ],
    "not_claimed": [
        "an improvement against stronger or external opponents, or on the platform",
        "an across-scenario improvement from a positive phase A",
        "that 3 games per arm in phase D rule out a loss of 10 points or more in any configuration",
        "a baseline promotion: a separate decision must keep baseline-v2 frozen as the reference and weigh the "
        "platform compatibility evidence",
    ],
    "limitations": [
        "the engine's own randomness is not documented as controllable: games are independent samples, not "
        "seed-matched, although the harness seeds Python's and NumPy's global generators",
        "the planning standard deviations of the candidate rest on 3 exploratory games per seat",
        "a percentile or studentized bootstrap with 15 games per stratum is an approximation; its null error and "
        "power were measured by simulation before registration (validation.json)",
        "32 concurrent shared sessions (the qualified configuration) lengthen decision-latency tails relative to "
        "serial play; latency is compared within the study only",
    ],
    "separate_workstreams": "the frozen baseline-v2 platform canary (a3d3b022...) is prepared for the owner's "
                            "manual upload to an AI test slot; platform observations never enter this study's "
                            "estimates; T4 stays shelved and T7's dispositions stand; no session of this study "
                            "is spent on them",
}


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def policy_source(sources) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def current_scheduler() -> str:
    spec = importlib.util.spec_from_file_location("run_game_pool", REPO_ROOT / "scripts" / "run_game_pool.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scheduler_identity()


def build() -> Dict[str, Any]:
    if (t9.CAPACITY, t9.DETOUR) != (tc.CANDIDATE_CAPACITY, tc.CANDIDATE_DETOUR):
        raise SystemExit("the candidate's parameters are not the explored ones")
    shoot = load(REPO_ROOT / "evaluation" / tc.V2_ID / "manifest.json")
    rt = load(REPO_ROOT / "evaluation" / "runtime-thread-qualification-1" / "results.json")
    (scheduler,) = rt["production_path"]["scheduler"]
    if rt["production_path"]["workers"] != tc.WORKERS or scheduler != current_scheduler():
        raise SystemExit("the scheduler or worker count of this checkout is not the qualified one")
    policies = {tc.V2_ID: {"label": "baseline-v2 (frozen)", "policy_source": policy_source(V2_SOURCES)},
                tc.CANDIDATE_ID: {"label": "T9 capacity-limited objective allocation, version 1 (Sprint 8, unchanged)",
                                  "policy_source": policy_source(T9_SOURCES)}}
    files = {rel: tc.normalized_sha256(REPO_ROOT / rel) for rel in FILES}
    tests = {rel: tc.normalized_sha256(REPO_ROOT / rel) for rel in TESTS}
    inputs = {f"{rel} (normalised sha256)": tc.normalized_sha256(REPO_ROOT / rel) for rel in PUBLIC_INPUTS}
    return tc.build(TEXTS, shoot, mf.digest(shoot), policies, scheduler, files, tests, inputs)


def text() -> str:
    return json.dumps(build(), indent=1, sort_keys=True) + "\n"


def matches() -> bool:
    return OUT.exists() and OUT.read_text(encoding="utf-8") == text()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed manifest instead of writing")
    args = parser.parse_args()
    fresh = text()
    digest = mf.digest(json.loads(fresh))
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != fresh:
            print(f"{OUT.relative_to(REPO_ROOT).as_posix()} differs from a fresh build", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(REPO_ROOT).as_posix()} matches a fresh build (canonical SHA-256 {digest})")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(fresh, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()} (canonical SHA-256 {digest}, file sha256 "
          f"{hashlib.sha256(fresh.encode('utf-8')).hexdigest()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
