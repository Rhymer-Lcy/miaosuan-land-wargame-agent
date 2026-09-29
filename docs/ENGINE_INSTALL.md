# Persistent engine installation

The SDK engine writes authentication state into its own installed package
(`train_env/env/authenticate/.engine_config`; see `ENGINE_SMOKE_TEST.md`, section 4), and its
authenticator checks the time elapsed since first use. Reinstalling the engine would therefore
restart that state. The project uses one persistent installation per engine version, created once
and afterwards only reused.

## Rules

1. The installation is created once, from the engine wheel inside a local SDK archive whose digest
   and whose wheel digest match `docs/PROVENANCE.md`, with `scripts/engine_install.py install`.
2. It is never reinstalled, repaired, reset or restored. The engine's state file is never
   interpreted, edited, copied, replaced or deleted. The project tooling offers no command for any
   of these, and none may be added; removing an installation is a deliberate manual act and must
   never be done to regain validity.
3. Engine processes run with the installation's persistent `home/` as `HOME`, so any state the
   engine keeps under `HOME` persists as well. (Engine 4.1.0 wrote nothing there.)
4. Every engine session goes through the session ledger described below. Engine processes started
   by other means are not recorded and will make the next session refuse to start.
5. The engine is never installed into a Python environment and never run as root.

## Layout

All paths are relative to the repository root and git-ignored:

```
local/engines/sdk-4.1.0/
  install-manifest.json   provenance and package fingerprint, written once, then read-only
  site/                   pip --target installation; the only place the engine may change files
  home/                   persistent HOME for engine processes
  usage-ledger.jsonl      append-only record of every engine session
  .session.lock           advisory lock held while a session runs
```

The manifest records the engine version, the SDK archive and wheel digests, the Python version and
installer command, the installation time as read from the host clock, the SHA-256 of every
package file before the first import (with an aggregate digest), and the hash of the state file at
installation.

## Session ledger and guardrails

Opening a session (`miaosuan_agent.engine_install.session`) takes the lock, then:

* verifies that every package file except the state file still matches the manifest; a changed or
  missing file refuses the session (files the engine adds are recorded, not refused);
* verifies that the state file's hash equals the hash recorded at the end of the previous session,
  or at installation for the first session; any difference means something outside a recorded
  session touched it, and the session is refused;
* appends a `session-open` record marked `first-use` or `reuse`.

Closing appends a `session-close` record with the state hash after the run, whether it changed,
the `home/` contents, the integrity result and the run outcome. A session that was never closed
(killed or crashed) is closed as `session-recovered` by the next opening, recording the state as
found. The chain of state hashes across records is the evidence that the state was never reset.

`python scripts/engine_install.py verify` prints the same checks without writing anything.

## Commands

```
PYTHON scripts/engine_install.py install --sdk-archive local/source-archives/land_wargame_sdk.zip
PYTHON scripts/engine_install.py verify
bash scripts/run_engine_smoke_test.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip [--capture]
```

`PYTHON` is the interpreter of the `miaosuan-runtime` environment (CPython 3.10); its pip performs
the offline `--target` installation.

## History

The first engine execution (2026-09-29, `ENGINE_SMOKE_TEST.md`) predates this policy: it installed
a fresh copy into a disposable run directory. That copy and its evidence are kept untouched; they
are not the persistent installation and are not used again.
