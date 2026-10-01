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

Every registered tier ran in order and passed every safety, independence, engine-state and ledger check; the
optional tier w32 did not run. 248 games in 7 tiers, then the 32 games of the scheduler-equivalence
corpus, added sessions 1074 to 1353. Every figure below comes from
`evaluation/concurrency-qualification-1/results.json` unless a source is named; `scripts/qualify_concurrency.py
analyze --check` regenerates it from the private tier summaries, and `tests/test_concurrency_results.py` recomputes
its speedups, criteria and recommendation from its own figures.

### Execution

* The plan's commit `93329f9` was verified on the public remote at 2026-10-01T12:21:23+08:00, before
  the first qualification session.
* Tier S ran at `93329f9`. Its writable-descriptor check flagged `/dev/null`, which is each game's stdin:
  CPython's `subprocess` opens it read-write for `stdin=DEVNULL`, and a character device carries no state between
  games. That one path was added to the expected set (`dc3c615`, pushed before the next tier), tier S's
  summary was rederived from what it had collected, and no game was rerun. Every later tier ran at
  `dc3c615`. This is the only deviation from the plan.
* Before each tier the host was quiet: other activity used at most 0.13 logical CPUs in the 30 s check, and no tier was
  contended.

### Serial utilisation

| Measure | S (exclusive) | w01 (shared) |
|---|---|---|
| games per hour | 66.2 | 68.1 |
| host CPU busy | 1.9% | 1.9% |
| our logical CPUs (mean) | 1.11 | 1.11 |
| CPU seconds per game (median) | 22.8 | 22.7 |
| peak resident set per game (median / max) | 742 MiB / 1,825 MiB | 742 MiB / 1,836 MiB |
| decision latency p99 / max | 1.214 / 823.0 ms | 1.227 / 822.8 ms |

* One game uses about one logical CPU: the serial tiers kept 1.11 logical CPUs busy on average, and
  the host was 98% idle.
* Each game process runs 64 threads, but only one does the game's work. In 246 of the 248 qualification games it
  was the only thread to use 1% or more of the process's CPU; in the other two, the shortest scenario under 16 and
  24 workers, one pool thread's start-up spin also passed 1% of about 9.5 CPU-seconds. Serially the other
  63 threads each spend 80 to 90 ms of CPU, about
  5.3 s per game whatever its length, and then sleep. They are NumPy's OpenBLAS pool, sized to the
  host's logical CPUs: importing NumPy alone, outside any engine session, creates 64 threads. The engine's native
  code adds no parallel work, so the per-game ratio of CPU to wall time is about 1 for long games and up to about 2
  for the shortest, where the pool's start-up spin is a large share.
* No game opened a socket of any kind, held a writable file other than its log, its record (written at the end),
  `/dev/null` and the installation's lock file, wrote to its working directory or `TMPDIR`, mapped a GPU, OpenMP or
  CUDA library, or appeared as a GPU process. The engine reads its scenario data in memory and each map's
  visibility file read-only. The state file's hash, size, modification and status-change times are unchanged:
  they still equal the first use of 2026-09-29.

### Safety and independence

| Tier | Workers | Games | Sessions | Checks | Deterministic identical | Stochastic prefix equal | Shared chains |
|---|---|---|---|---|---|---|---|
| S | 1 | 8 of 8 | 8 | all pass | 5 of 5 | 3 of 3 | 0 |
| w01 | 1 | 16 of 16 | 16 | all pass | 10 of 10 | 6 of 6 | 0 |
| w02 | 2 | 16 of 16 | 16 | all pass | 10 of 10 | 6 of 6 | 0 |
| w04 | 4 | 16 of 16 | 16 | all pass | 10 of 10 | 6 of 6 | 0 |
| w08 | 8 | 32 of 32 | 32 | all pass | 20 of 20 | 12 of 12 | 0 |
| w16 | 16 | 64 of 64 | 64 | all pass | 40 of 40 | 24 of 24 | 0 |
| w24 | 24 | 96 of 96 | 96 | all pass | 60 of 60 | 36 of 36 | 0 |

* In every tier each session was opened and closed once, the numbers were consecutive, nothing was recovered or left
  unclosed, package integrity held with nothing added, and `home/` stayed empty.
* Independence held at every level. Every deterministic game reproduced the serial state chain and every seat's
  trace chain (155 games), and every stochastic game the serial prefix (93 games). The eight games of
  2130511121 C3 in w16 started within 9 ms of each other and the twelve in w24 within 14 ms, and no two produced the same
  trajectory: the engine's randomness is neither shared between processes nor derived from the start time at
  that resolution.

### Scaling

| Workers | Games/hour | Speedup | Efficiency | Host CPU | p95 game time |
|---:|---:|---:|---:|---:|---:|
| 1 | 68.1 | 1.00 | 1.000 | 1.9% | 192.8 s |
| 2 | 131.3 | 1.93 | 0.964 | 3.6% | 198.6 s |
| 4 | 254.2 | 3.73 | 0.933 | 6.9% | 204.5 s |
| 8 | 500.1 | 7.34 | 0.918 | 13.5% | 205.7 s |
| 16 | 959.8 | 14.09 | 0.881 | 26.5% | 212.1 s |
| 24 | 1,386.2 | 20.35 | 0.848 | 38.9% | 217.5 s |

| Workers | Decision p50 / p95 / p99 | Decision max | Over 1 s | Peak resident set (all games) | Involuntary switches per game |
|---:|---|---:|---:|---:|---:|
| 1 | 0.475 / 1.193 / 1.227 ms | 822.8 ms | 0 | 1.8 GiB | 91 |
| 2 | 0.480 / 1.237 / 1.325 ms | 842.2 ms | 0 | 3.6 GiB | 211 |
| 4 | 0.492 / 1.302 / 1.376 ms | 1,317.6 ms | 5 | 5.4 GiB | 159,466 |
| 8 | 0.551 / 1.342 / 1.397 ms | 1,195.3 ms | 2 | 10.8 GiB | 446,346 |
| 16 | 0.633 / 1.392 / 1.439 ms | 1,168.8 ms | 2 | 21.8 GiB | 837,450 |
| 24 | 0.633 / 1.414 / 1.465 ms | 1,759.7 ms | 10 | 32.1 GiB | 1,420,090 |

Throughput is games divided by the tier's makespan, with the w01 tier (68.1 games per hour) as the base. A
game's own CPU time (median) rose only from 22.7 s (w01) to 23.7 s (w16) and 24.4 s (w24), so the
longer wall times come mostly from contention, not from more work.

### GC and resource interaction

| Tier | 2130511121 C3 wall (median) | its decision max | its decisions over 1 s | its GC collections (gen 0 / 1 / 2) |
|---|---:|---:|---:|---|
| S | 190.9 s | 823.0 ms | 0 | 61,838 / 5,621 / 111 |
| w01 | 191.5 s | 822.8 ms | 0 | 61,705 / 5,609 / 112 |
| w02 | 195.3 s | 842.2 ms | 0 | 61,705 / 5,609 / 112 |
| w04 | 203.8 s | 1,317.6 ms | 5 | 63,294 / 5,753 / 113 |
| w08 | 205.4 s | 1,195.3 ms | 2 | 61,976 / 5,634 / 113 |
| w16 | 211.9 s | 1,168.8 ms | 2 | 61,977 / 5,634 / 112 |
| w24 | 217.2 s | 1,759.7 ms | 10 | 62,122 / 5,647 / 112 |

* Each game is its own process with its own heap, so collections stay per process: the long game made about the
  same number of collections in every tier (generation 2: 111 to 113).
* Contention lengthens them. The largest scenario's wall time grew by 11% at 16 workers and 13% at 24, and the late collection pauses grew with it:
  the maximum decision latency rose from 822.8 ms (w01) to 1,168.8 ms (w16) and 1,759.7 ms (w24).
  Involuntary context switches per game rose from 91 (w01) to 159,466 at 4 workers and 837,450 at 16;
  their cause was not established.
* Memory is not a constraint: at 24 workers all games together peaked at 32.1 GiB, 6.6% of host memory.

### Recommendation

| Tier | Throughput | Efficiency | Latency (p99 / max ratio) | Headroom | Acceptable |
|---|---|---|---|---|---|
| w02 | pass (1.93) | pass (0.964) | pass (1.08 / 1.02) | pass (2.2 CPUs, 0.7% memory) | yes |
| w04 | pass (3.73) | pass (0.933) | pass (1.12 / 1.60) | pass (4.3 CPUs, 1.1% memory) | yes |
| w08 | pass (7.34) | pass (0.918) | pass (1.14 / 1.45) | pass (8.5 CPUs, 2.2% memory) | yes |
| w16 | pass (14.09) | pass (0.881) | pass (1.17 / 1.42) | pass (16.7 CPUs, 4.5% memory) | yes |
| w24 | pass (20.35) | pass (0.848) | FAIL (1.19 / 2.14) | pass (24.7 CPUs, 6.6% memory) | no |

**RECOMMEND 16 WORKERS.** w02, w04, w08 and w16 are acceptable; w24 is not, because its maximum decision latency
reached 2.14 times w01's (the registered limit is 2), and its efficiency of 0.848 is below the 0.85 that w32
required, so w32 did not run. The largest acceptable speedup is 14.09 (w16), and 16 is the smallest acceptable count
within 0.85 of it (w08 reaches 7.34). Throughput had not levelled off by 24 workers; the limit came from
the decision-latency tail, which crossed the registered bound at 24. At 16 workers our games used about a quarter
of the host's logical CPUs.

### Production scheduler

Added only after the qualification passed, and opt-in:

* `scripts/run_evaluation.sh --workers N` (default 1). With 1 the serial loop runs exactly as before. With N > 1 the
  script makes the same registered checks before and after the run and hands the plan's games, in registered
  order, to `scripts/run_game_pool.py`.
* The pool dispatches in queue order to the lowest-numbered free worker, at most N games at a time, through
  `src/miaosuan_agent/evaluation/scheduler.py`. Each game is the serial loop's command and isolation with a working
  directory of its own and a shared engine session. Its record names the worker count, worker, batch and the
  scheduler identity (`miaosuan-game-pool/1@<SHA-256 of the scheduler's sources>`).
* Accounting is the serial loop's: a recorded game is skipped; a game started earlier without a record stops the
  run before any game starts; nothing is retried; markers, logs and records are created exclusively. Dispatch stops
  after three consecutive non-completions (study and A/B plans) or on any other exit status. SIGINT and SIGTERM
  terminate the running games, whose sessions record the interruption. No session may be unclosed before or after.
* A registered evaluation runs with the worker count its manifest registers (`execution.workers`); a manifest
  without one registers 1, so every existing registration stays serial. `--purpose diagnostic --work DIR
  [--games FILE]` runs a diagnostic subset with any worker count.
* Fair A/B scheduling follows from dispatching the registered schedule in order. The schedule alternates the groups
  game by game and alternates which group leads each round, so every batch of N consecutive games mixes both groups
  and neither group sits on early or late slots. Worker and batch are recorded per game. Games that run at the same
  time are not paired: the analysis still treats every game as an independent engine run.

### Serial-versus-parallel equivalence

The 16-game corpus ran once through the serial loop (sessions 1322 to 1337, exclusive) and once
through `run_evaluation.sh --workers 16` (sessions 1338 to 1353, shared, one batch of 8 group-B and
8 group-C games). Both recorded exactly the 16 planned games with the registered digests, each
opened and closed once in the ledger, with one engine state throughout. All 16 games of each run passed the
independence comparison with the serial references of their configuration and group, and the 10 deterministic
games were identical between the two runs. Equivalence: pass.

```bash
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan ab \
    --evaluation baseline-v2-candidate-shoot-target-reservation --purpose diagnostic \
    --work DIR/serial --games corpus.txt --workers 1          # then --work DIR/parallel --workers 16
PYTHON scripts/qualify_concurrency.py equivalence --workers 16
```

### GPUs

No game mapped a CUDA or other GPU library or appeared as a GPU compute process, and games run with
`CUDA_VISIBLE_DEVICES` empty. Neither the engine nor the policy does GPU work, so the host's GPUs are irrelevant to
game-evaluation throughput; using them here would add complexity without speed. They stay available for workloads
that can use them, such as training or inference of learned policies.

### Operational impact

At the measured w01 throughput, 720 games take about 10.6 h; the shoot experiment's 720 games took about
10.4 h serially. At the measured w16 throughput they would take about 45 minutes. That figure is an extrapolation:
w16 was measured on 64 games, and 720 games of a different configuration mix would scale it only as far as the mix's
longest games and the makespan's start and end allow.

### Limitations

* One host, one engine build, eight configurations, and short tiers: tiers of 16 to 96 games measure the safety
  properties and the throughput knee, not rare events. A tier's makespan includes its start and end.
* Decision-latency tails rise with concurrency through longer collection pauses. Latency is not a criterion of the
  tactical experiments, but an experiment that measures latency should run serially or report the worker count.
* The OpenBLAS pool's start-up spin costs about 5 CPU-seconds per game; it was observed, not changed.
* The equivalence corpus covers 16 games; it shows that the parallel path accounts and reproduces like the serial
  one, not that rare failures are handled identically under load.
