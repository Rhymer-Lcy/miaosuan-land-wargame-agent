# Miaosuan Land Wargame Agent

庙算兵棋智能体: an AI agent for the 庙算·陆战指挥官 (Miaosuan Land Wargame Commander) platform at
https://wargame.ia.ac.cn/.

## Status

Bootstrap. The repository holds provenance records, a static audit of the platform's community SDK,
and tooling to verify a local copy of that SDK. No agent logic has been written.

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
| `docs/PROVENANCE.md` | identity of the SDK and documentation inputs, licensing status, local archive layout |
| `docs/COMPATIBILITY.md` | static audit of the SDK: engine requirements, inconsistencies, upload constraints |
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

## Constraints to know before development

1. The engine (`land_wargame_train_env` 4.1.0) exists only as a
   `cp310-cp310-manylinux2014_x86_64` wheel: x86-64 Linux with CPython 3.10.
2. The engine embeds a MAC-bound, time-since-first-use authenticator and may refuse to run; its
   first execution belongs in a disposable environment (`docs/COMPATIBILITY.md`, section 2).
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
