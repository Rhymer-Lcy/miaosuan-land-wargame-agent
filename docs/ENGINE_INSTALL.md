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
  .ledger.lock            advisory lock held while a shared session reads and appends the ledger
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
found; an exclusive opening recovers every session the ledger shows as open. The chain of state hashes
across records is the evidence that the state was never reset.

A shared session (`miaosuan_agent.engine_install.shared_session`) holds the lock in shared mode, so
shared sessions may overlap each other but never an exclusive one. It allocates its number, compares the
state with the latest ledger record and appends under `.ledger.lock`, and its records name the session
mode and the worker. It never performs the first use and never recovers another session: recovery needs
the exclusive lock (`recover_unclosed`, or an exclusive opening). Shared sessions share the one
installation and its state; nothing is copied. They are used only by the registered concurrency
qualification (`CONCURRENCY_QUALIFICATION.md`); the evaluator's sessions are exclusive.

`python scripts/engine_install.py verify` prints the same checks without writing anything.

## Commands

```
PYTHON scripts/engine_install.py install --sdk-archive local/source-archives/land_wargame_sdk.zip
PYTHON scripts/engine_install.py verify
bash scripts/run_engine_smoke_test.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip [--capture]
```

`PYTHON` is the interpreter of the `miaosuan-runtime` environment (CPython 3.10); its pip performs
the offline `--target` installation.

## Installation in use

One installation exists for engine 4.1.0, created on 2026-09-29 on the Linux host used for
development. Its manifest fingerprints 153 package files before the first import. Session 0001
(first use, with contract capture) and session 0002 (reuse) both passed. The state file was empty
at installation, was written by the engine during session 0001, and was not changed by session
0002; each session opened with exactly the state its predecessor closed with. `home/` stayed empty.

## Host clock

The authenticator's method names indicate a check of time since first use; which clock it reads
was not verified. On the host used so far, the wall clock ran about 388 s ahead of external
references (the HTTP `Date` headers of Cloudflare and Google, which agreed with the development
workstation to within about one second; GitHub's header was about 8 s off and was not used). The
host is not NTP-synchronised: its time service is active, reports the clock as unsynchronised, and
times out contacting its NTP servers. The offset was stable while observed (388.36 s and then
388.26 s against the workstation, about 48 minutes apart).

Consequences:

* ledger and report timestamps are host-clock labels and carry that offset; durations are measured
  with monotonic clocks;
* the clock is never changed to influence the engine, and nothing here changes it;
* if the host's clock is later corrected, it will step back by the offset; how the authenticator
  treats a first-use time that then lies in the future is unknown.

## History

The first engine execution (2026-09-29, `ENGINE_SMOKE_TEST.md`) predates this policy: it installed
a fresh copy into a disposable run directory. That copy and its evidence are kept untouched; they
are not the persistent installation and are not used again.
