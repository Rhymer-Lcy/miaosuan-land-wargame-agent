# Miaosuan Land Wargame Agent

庙算兵棋智能体: an AI agent for the 庙算·陆战指挥官 (Miaosuan Land Wargame Commander) platform at
https://wargame.ia.ac.cn/.

## Status

Bootstrap complete. The repository holds provenance records, a static audit of the platform's
community SDK, tooling to verify a local copy of it, a reproducible runtime environment, and an
isolated engine smoke test that passed on Linux (`docs/ENGINE_SMOKE_TEST.md`). No agent logic has
been written.

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
(`miaosuan_agent.boundary`). `--capture` also writes private contract fixtures under `local/`.
`PYTHON` is the interpreter of `miaosuan-runtime`. Exit status:
0 PASS, 1 FAIL, 2 invalid input, 3 BLOCKED (the engine reported an authentication failure),
4 REFUSED (an installation guardrail stopped the run).

The default game is scenario `201033019601` on map `9601`: two units, at most 1000 steps. Scenario
files do not name their map; this pairing is established by the scenario's 50 roadblock positions,
which are exactly the 50 cells flagged as roadblocks in map 9601, the only map with such flags.

## Constraints to know before development

1. The engine (`land_wargame_train_env` 4.1.0) exists only as a
   `cp310-cp310-manylinux2014_x86_64` wheel: x86-64 Linux with CPython 3.10.
2. The engine embeds a MAC-bound, time-since-first-use authenticator. It passed on first use and
   keeps its state inside the installed package (`docs/ENGINE_SMOKE_TEST.md`, section 4).
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
