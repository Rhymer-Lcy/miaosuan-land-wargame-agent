# Concurrency qualification

`concurrency-qualification-1` is a registered engineering diagnostic. It asks whether several engine games
can run at once on the one persistent engine installation without violating engine-state integrity,
authentication integrity, the independence of games, determinism, or ledger and result accounting, and
whether running them at once raises registered-game throughput. It changes no policy: every game plays
`baseline-v2` on `baseline-v1-runtime-r1`. It does not change routing or garbage collection, uses no GPU,
and does not touch the production evaluator (`scripts/run_evaluation.sh`), which stays strictly serial.

This document was committed with the plan, before any qualification session. The plan is
`evaluation/concurrency-qualification-1/plan.json` (canonical SHA-256 `f6d0f1b1…`), built by
`scripts/build_concurrency_plan.py` from `src/miaosuan_agent/evaluation/concurrency.py`; where this text and
the plan differ, the plan governs. Results are appended under "Results".

## Why the evaluator is serial, and what is known before any concurrent game

The engine writes its authentication state into its own installed package (`ENGINE_INSTALL.md`). The
evaluator therefore runs one game at a time under an exclusive installation lock, and its ledger protocol
is serial as well: a new session's number is the count of earlier openings plus one, and a last ledger
record that is an opening is taken to be a crashed session and recovered. Two overlapping sessions would
break both rules. This was a deliberate choice made before concurrent engine behaviour was characterised.

Read-only evidence gathered before registration, without opening an engine session:

* Across all 1,073 sessions so far the engine changed its state file only in the first-use session (0001).
  The file's modification and status-change times both still equal that first use, so the engine has not
  written to it, even with identical content, in any later session. Reuse sessions only read it.
* No session added, changed or removed a package file, and `home/` (the shared persistent `HOME`) stayed
  empty throughout. The package holds compiled extension modules only and no bytecode cache; the evaluator
  runs with bytecode writing disabled.
* The engine receives its scenario and map data in memory through `setup`, and wrote nothing into the
  working directory or `HOME` in the smoke test.
* It does not draw from Python's or NumPy's global random generators (the harness's fingerprints are
  unchanged at every probe point), so its randomness comes from a source of its own. Whether that source
  is shared, or derived from the start time, is unknown; two games started in the same second are the test.
* The runtime's NumPy uses OpenBLAS built for at most two threads.
* `play` stops a game at 1,800 s of wall time. The slowest block configuration takes about 191 s serially,
  so contention would have to slow it more than ninefold to change an outcome this way.

Unknown before measurement: whether the engine opens sockets, shared memory or temporary files during a
game, how many threads it runs, and whether concurrent games interfere.

## Shared sessions

`miaosuan_agent.engine_install` gains a second, opt-in session kind; the exclusive `session` is unchanged.

* `shared_session` holds the installation lock in shared mode for the whole game, so shared sessions may
  overlap each other but never an exclusive session, and an exclusive session never starts while a shared
  one runs.
* Every ledger read and append of a shared session happens under a separate ledger lock, so concurrent
  openings get distinct consecutive numbers. The opening compares the engine state with the latest ledger
  record and refuses on any difference, exactly as an exclusive opening compares it with the previous
  session's close.
* A shared session never performs the first use and never recovers another session. Recovery needs the
  exclusive lock, when no session can be running: `recover_unclosed`, or an exclusive `open_session`, which
  now closes every unclosed session rather than only the latest. With exclusive sessions only, at most the
  latest can be unclosed, so the exclusive behaviour on every ledger written so far is unchanged.
* Every worker uses the one legitimate installation and its existing state. Nothing is copied, reset,
  restored, regenerated or patched, and no second installation is created.

## Plan

* **Workload.** One block holds one configuration of each scenario, all with `baseline-v2` against itself
  (C1) or the inert control (C2, C3):
  * deterministic in all 15 serial repetitions of the shoot experiment: 201033019601 C2, 2010131194 C2,
    2010211129 C3, 1910631192 C2 and 2010431153 C2;
  * stochastic after their first shot: 1930331196 C3, 2120531121 C1 and 2130511121 C3.

  A block takes about 414 s serially, about 52 s per game, close to the shoot experiment's average.
* **Tiers.** Each tier plays its blocks' games in one queue, longest expected first, with at most N games at
  a time:

  | Tier | Workers | Sessions | Blocks | Games |
  |---|---|---|---|---|
  | S | 1 | exclusive | 1 | 8 |
  | w01 | 1 | shared | 2 | 16 |
  | w02 | 2 | shared | 2 | 16 |
  | w04 | 4 | shared | 2 | 16 |
  | w08 | 8 | shared | 4 | 32 |
  | w16 | 16 | shared | 8 | 64 |
  | w24 (optional) | 24 | shared | 12 | 96 |
  | w32 (optional) | 32 | shared | 16 | 128 |

  S is the serial control: the current architecture. w01 is the base for speedup and the control for the
  protocol itself. A tier runs only if every earlier tier passed its safety, independence, engine-state and
  ledger checks; w24 runs only if w16 met every criterion with parallel efficiency of at least 0.85, and
  w32 likewise after w24. No tier fills every logical CPU.
* **Isolation.** Each game is one process, started as the evaluator starts one: a minimal environment, the
  shared persistent `HOME`, an empty working directory and `TMPDIR` of its own (checked empty afterwards),
  a new process group, its own log, and the registered seeding of Python's and NumPy's global generators.
* **Scheduling.** `src/miaosuan_agent/evaluation/scheduler.py` dispatches in queue order to the
  lowest-numbered free worker, records the worker and the batch (dispatch wave) of every game, never
  retries, stops dispatching on the first failure, cancels cleanly, and reaps each game with `wait4` so
  that its CPU time, peak memory and context switches are exact. Records, logs and start markers are
  created exclusively and are never overwritten.
* **Safety checks**, at every tier: every game exits 0 with one record, one log and one marker; the ledger
  parses and the tier's sessions are consecutive, each opened and closed once, none recovered or unclosed,
  each naming its game, mode and worker; the state file's hash, size, modification and status-change times
  are unchanged, and every ledger record carries that hash; package integrity holds with nothing added, and
  `home/` is unchanged; no contract error, gate rejection or replay mismatch; only known refusal classes; no
  process left in a game's group; no writable file outside the game's record and log and the installation's
  lock and ledger files; no internet socket.
* **Independence.** Deterministic configurations must reproduce the serial state chain and every seat's
  trace chain exactly. Stochastic ones must reproduce the state and trace digests up to the earliest step
  at which any two serial repetitions differ. No two games of one stochastic configuration may share a
  state chain, and none may equal a serial one: that would mean shared or time-derived randomness.
* **Stop conditions.** A failed check stops the qualification after the tier, and nothing is repaired; an
  engine-state, refusal or ledger anomaly stops it at once. Before each tier the host is sampled for 30 s:
  the tier starts only if other activity uses at most 16 logical CPUs and at least 16 stay idle with the
  tier's workers added; otherwise it waits, and after six 5-minute rechecks it pauses. A tier during which
  other activity averaged more than 8 logical CPUs is repeated once under a new attempt name; both are kept.
* **Measurements.** Host CPU time, load, running processes, context switches and memory every second;
  every game's CPU time, threads, resident set and context switches every second and its descriptors every
  5 s; its exact usage from `wait4`; its own report of CPU per thread, peak memory, I/O, GC collection
  counts and mapped GPU, OpenMP and OpenBLAS libraries; GPU utilisation every 10 s; and the decision
  latency of the policy seats. Only our own processes are read; other activity appears only as host CPU
  time minus ours.
* **Criteria and recommendation.** A tier is acceptable when it and every lower tier passed every check,
  its speedup over w01 is at least 1.5, its parallel efficiency at least 0.70, its decision-latency p99 at
  most 1.5 times w01's and its maximum at most twice w01's, and our processes used at most 32 logical CPUs
  on average and at most 10% of host memory at peak. The recommendation is the smallest acceptable worker
  count whose speedup is at least 0.85 of the largest acceptable speedup: `RECOMMEND N WORKERS`. If every
  check passed but no tier of two or more workers is acceptable: `RETAIN SERIAL EXECUTION`. If any check
  failed: `CONCURRENCY BLOCKED PENDING MORE EVIDENCE`.
* **Scheduler equivalence.** If a worker count is recommended and a production scheduler is added, the
  plan's 16-game corpus (groups B and C, repetition 1, of the block's configurations, in the shoot
  experiment's schedule order) runs once through the existing serial loop and once through the new
  parallel path. Both runs must record exactly those games, carry the registered digests, pass the
  independence comparison with the serial references of their configuration and group (deterministic games
  identical between the runs), and leave a clean ledger and an unchanged engine state.

## Running

```bash
PYTHON scripts/build_concurrency_plan.py --check
PYTHON scripts/qualify_concurrency.py stage --sdk-archive ZIP
PYTHON scripts/qualify_concurrency.py tier --tier S        # then w01, w02, w04, w08, w16
PYTHON scripts/qualify_concurrency.py analyze
```

## Results

None at registration.
