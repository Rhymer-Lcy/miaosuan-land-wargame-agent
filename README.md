# Miaosuan Land Wargame Agent

庙算兵棋智能体: an AI agent for the 庙算·陆战指挥官 (Miaosuan Land Wargame Commander) platform at
https://wargame.ia.ac.cn/.

## Status

Current baseline: `baseline-v1` (`docs/BASELINE_V1.md`). On top of the provenance records, the static
SDK audit, the runtime environment, the guarded persistent engine installation and the contract
boundary (`docs/CONTRACT.md`), the repository holds `baseline-v0`, a deterministic, minimal agent that
acts only through legal-action information and a final safety gate (`docs/BASELINE.md`,
`docs/EVALUATION.md`), and `baseline-v1`, which adds one change tested in a registered single-variable
experiment: at most one occupation command per objective in a decision step
(`docs/EVALUATION_OCCUPY_RESERVATION.md`). Both are reference points; nothing in them is tuned for
winning, and `baseline-v0` stays reproducible under its original identity. The repeated-run variance of
`baseline-v1` was measured in a registered study with ten repetitions per configuration
(`docs/VARIANCE_STUDY.md`), which also sizes future single-variable experiments.

## Third-party material is not in this repository

The platform's community SDK (engine wheel, map and scenario data, demo code, documentation) carries
no license that authorizes redistribution, so none of it is stored here, verbatim or modified. The
repository records only file names, sizes, SHA-256 digests and observed interfaces
(`docs/PROVENANCE.md`). Machines that hold a legitimately obtained copy keep it under the
git-ignored `local/` tree; nothing in the package or the test suite requires it.

## Layout

| Path | Content |
|---|---|
| `src/miaosuan_agent/` | the project's Python package |
| `scripts/` | command-line tools |
| `tests/` | unit tests (standard library `unittest`; no SDK needed) |
| `environments/` | reproducible definition of the platform-compatible runtime environment |
| `docs/PROVENANCE.md` | identity of the SDK and documentation inputs, licensing status, local archive layout |
| `docs/COMPATIBILITY.md` | static audit of the SDK: engine requirements, inconsistencies, upload constraints |
| `docs/ENGINE_SMOKE_TEST.md` | observed engine behaviour and interface contract from the first controlled run |
| `docs/CONTRACT.md` | observed contract of SDK 4.1.0, accepted boundary, canonical representation, fixture policy |
| `docs/ENGINE_INSTALL.md` | persistent engine installation: rules, session ledger, host clock |
| `docs/BASELINE.md` | identity, decision pipeline, action semantics, safety gate and limitations of `baseline-v0` |
| `docs/EVALUATION.md` | the registered evaluation protocol of `baseline-v0` and its results |
| `docs/BASELINE_V1.md` | identity of `baseline-v1`: the one change, its digests and its limitations |
| `docs/EVALUATION_OCCUPY_RESERVATION.md` | the registered single-variable experiment that produced `baseline-v1`, and its results |
| `docs/VARIANCE_STUDY.md` | the registered repeated-run variance study of `baseline-v1`: design, statistics, planning method, results |
| `docs/REFUSAL_TAXONOMY.md` | how engine refusals are recorded (facts) and attributed (versioned rules); the code-203 correction |
| `evaluation/<name>/` | each registered evaluation's manifest and sanitized results |
| `evaluation/refusal-taxonomy-correction/` | historical refusal facts derived from the unchanged records |
| `local/` (git-ignored) | machine-specific material: SDK archives, runtime files, logs, replays |

## Verifying a local SDK copy

```
python scripts/verify_source_archives.py
```

The script checks `local/source-archives/` against the recorded digests. Absent files are reported
as skipped with exit status 0; `--require` makes absence an error (status 2). Any mismatch gives
status 1.

## Running the tests

```
python -m unittest discover -s tests -t .
```

Tests that need private material (real contract fixtures, the persistent engine installation, POSIX
file locking) skip with a stated reason when it is absent, so a public checkout passes without any
SDK asset.

## Engine smoke test

On an x86-64 Linux host with the `miaosuan-runtime` environment (`environments/README.md`), a local
SDK copy and the persistent engine installation (created once; `docs/ENGINE_INSTALL.md`):

```
bash scripts/run_engine_smoke_test.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip [--capture]
```

The script stages one game's data into a new directory under `local/runtime/` and runs the engine
from the persistent installation with an empty environment, the installation's persistent `HOME`,
no user site-packages, no GPU and a hard timeout. The session ledger refuses to start if the
installation or its state changed outside a recorded session. Two inert agents end the deployment
stage and otherwise do nothing; every state passes through the contract boundary
(`docs/CONTRACT.md`). `--capture` also writes private contract fixtures under `local/`.
`PYTHON` is the interpreter of `miaosuan-runtime`. Exit status:
0 PASS, 1 FAIL, 2 invalid input, 3 BLOCKED (the engine reported an authentication failure),
4 REFUSED (an installation guardrail stopped the run).

The default game is scenario `201033019601` on map `9601`: two units, at most 1000 steps. Scenario
files do not name their map; this pairing is established by the scenario's 50 roadblock positions,
which are exactly the 50 cells flagged as roadblocks in map 9601, the only map with such flags.

## Baseline agent and evaluation

`miaosuan_agent.agent.BaselineAgent` implements the platform's agent interface (`setup`, `step`,
`reset`) around the policy in `miaosuan_agent.decision`. The evaluation plays the registered games
on the real engine, one isolated process and recorded engine session per game:

```
python scripts/build_evaluation_manifest.py --check
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip --plan gate1
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip --plan suite
```

Game records stay under the git-ignored `local/evaluation/`; only sanitized aggregates are
published (`evaluation/baseline-v0/results.json`).

## Constraints to know before development

1. The engine (`land_wargame_train_env` 4.1.0) exists only as a
   `cp310-cp310-manylinux2014_x86_64` wheel: x86-64 Linux with CPython 3.10.
2. The engine embeds a MAC-bound, time-since-first-use authenticator that keeps its state inside
   the installed package. It is used only through one persistent installation that is never
   reinstalled or reset (`docs/ENGINE_INSTALL.md`).
3. The SDK's demo runner does not run as shipped: the data paths it opens do not exist in the
   supplied `Data.zip` (section 3).
4. The platform accepts an upload only as a zip holding a single top-level package `ai` that
   exposes class `Agent`. Development happens in `src/miaosuan_agent/`; the `ai/` tree will be
   generated for upload (section 6).

## Names

| Use | Name |
|---|---|
| Repository and directory | `miaosuan-land-wargame-agent` |
| Display name | Miaosuan Land Wargame Agent |
| Chinese name | 庙算兵棋智能体 |
| Python package | `miaosuan_agent` |

## License

No license has been chosen for this project yet, so no rights beyond those implied by publication
are granted. The third-party SDK material it is developed against is unlicensed and is not
redistributed (`docs/PROVENANCE.md`, section 4).
