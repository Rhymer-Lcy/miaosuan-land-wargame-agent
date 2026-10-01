# Runtime thread-pool qualification

`runtime-thread-qualification-1` is a registered engineering diagnostic. Every game process starts NumPy's
OpenBLAS thread pool with one thread per logical CPU, and the concurrency qualification found that those threads
do no sustained game work (`CONCURRENCY_QUALIFICATION.md`). The question here is whether that pool can be
constrained without changing engine or agent behaviour, and whether constraining it improves the concurrency tail
and permits a higher safe worker count. The only variable is the numerical-library thread environment of the game
process. Policies (`baseline-v2`, and `baseline-v1` on `baseline-v1-runtime-r1`), routing, garbage collection and
the engine installation are unchanged, and no GPU is used.

This document was committed with the plan, before any constrained engine run. The plan is
`evaluation/runtime-thread-qualification-1/plan.json` (canonical SHA-256 `06a05d2b…`), built by
`scripts/build_runtime_thread_plan.py` from `src/miaosuan_agent/evaluation/runtime_threads.py`; where this text and
the plan differ, the plan governs. Results are appended under "Results".

## What is known before registration

Read without opening an engine session:

* The numerical runtime is the OpenBLAS 0.3.23.dev that NumPy 1.26.2 bundles (64-bit integer interface,
  dynamic architecture, POSIX threads). The environment holds no MKL, numexpr, threadpoolctl or SciPy, and no
  OpenMP runtime is mapped.
* Importing NumPy in a fresh interpreter takes the process from 1 thread to 64, one per logical CPU. The library
  reads three variables, in order: `OPENBLAS_NUM_THREADS`, `GOTO_NUM_THREADS` and `OMP_NUM_THREADS`. Each of them
  set to 1 alone leaves the process with 1 thread; `MKL_NUM_THREADS` and `NUMEXPR_NUM_THREADS` change nothing,
  because neither library is present. The smallest effective change is therefore `OPENBLAS_NUM_THREADS=1`, the
  library's own variable, and no other variable is set.
* The project's own code uses NumPy only to seed the global generator and to load map data. The engine modules
  that reference NumPy name only `ndarray`, `zeros`, `load`, `copy` and `random`; none names `dot`, `matmul`,
  `linalg` or another BLAS-backed function. That is not proof: the `@` operator leaves no name behind.
* In the concurrency qualification each pool thread used 80 to 90 ms of CPU whatever the game's length, so no
  BLAS call large enough for OpenBLAS to hand to its pool happened during a game. Smaller calls would run on the
  calling thread whatever the setting.
* Lazy symbol binding cannot show BLAS use here: NumPy's BLAS symbols are bound when NumPy loads. Instead the
  plan registers a call-counting shim (`scripts/blas_count_shim.c`), preloaded into the game process. Each of
  the 57 BLAS and LAPACK entry points NumPy imports from OpenBLAS is an assembly trampoline that counts the call
  and jumps to the real function, independent of its signature and without changing a result. Validated without
  the engine, importing NumPy counted one `cblas_sdot64_` call (NumPy's own check); element-wise work added none;
  `dot`, a 40 by 40 `@` and `linalg.solve` each added exactly their entry points.

## Plan

* **Environments.** A: the current runtime, no numerical-thread variable. B: `OPENBLAS_NUM_THREADS=1`, added to
  the game's environment before the interpreter starts. Every game refuses to play if its effective
  numerical-thread variables differ from its group's, and records its whole environment.
* **Workload.** The concurrency qualification's block (five deterministic and three stochastic configurations of
  `baseline-v2`) and its 16-game scheduler-equivalence corpus (both policies), with that plan's serial references,
  cited by its digest.
* **Tiers**, in this order; each runs only if every earlier tier passed every check:

  | Tier | Environment | Workers | Games | Purpose |
  |---|---|---|---|---|
  | P-A | A + counting shim | 1 | 16 (corpus) | does the engine or a policy call BLAS during a game? |
  | E-B | B | 1 | 16 (corpus) | behavioural equivalence of both policies under B |
  | B-w01 | B | 1 | 16 (2 blocks) | constrained base and serial control |
  | A-w16 | A | 16 | 64 | current runtime, new per-thread instrumentation |
  | B-w16 | B | 16 | 64 | constrained runtime |
  | A-w24 | A | 24 | 96 | current runtime |
  | B-w24 | B | 24 | 96 | constrained runtime |
  | B-w32 (optional) | B | 32 | 128 | only if B-w24 met every worker criterion with efficiency of at least 0.85 |

  Not planned: 40 workers or more, which would exceed the courtesy ceiling of 32 logical CPUs; and a new A-w01,
  because the concurrency qualification measured the current runtime serially.
* **Process-level check** (no engine): in each environment, 10 fresh interpreters one at a time (threads before
  and after importing NumPy, the import's wall and CPU time, CPU after a 0.5 s settle, mapped libraries, context
  switches), then 16 and 24 interpreters started at once, twice each, and five NumPy operations hashed bit for bit
  as a runtime sanity check (reported, not a criterion).
* **Equivalence**, in E-B and every B tier: deterministic configurations reproduce the serial state chain, step
  count and every seat's trace chain; stochastic ones reproduce the state and trace digests up to the serial
  common prefix, and their first divergence from every serial repetition is reported against their first shot; no
  two stochastic games of a tier share a chain, and none equals a serial chain; only known refusal classes, and no
  contract error, gate rejection or replay mismatch. Any difference before the serial prefix or in a deterministic
  game blocks the constrained runtime. No difference is dismissed as floating point.
* **Integrity**, in every tier: the concurrency qualification's safety, engine-state and ledger checks (records,
  logs and markers once each, consecutive sessions opened and closed once, an unchanged state file and package,
  empty working directories, no unexpected writable file, no socket, no orphan, no GPU).
* **Measurements.** Those of the concurrency qualification, plus, per game: wall time since the process started,
  CPU time and threads at the start of the game command, NumPy's import wall and CPU time, the process's context
  switches so far; and at its end the CPU time, voluntary and involuntary switches and CPU migrations of every
  thread, and garbage-collection pauses per generation (count, total, longest, every pause over 50 ms), observed
  through `gc.callbacks` without changing collection.
* **Disposition.** BLOCKED if any tier fails an equivalence, safety, engine-state or ledger check. Otherwise
  PROMOTED AS `baseline-v1-runtime-r2` if at least one benefit holds: (a) a constrained tier of more than 16
  workers meets the concurrency qualification's worker criteria against B-w01; (b) at 16 or 24 workers the
  constrained throughput is at least 1.05 times the current runtime's in the same run; (c) at 16 workers the
  median CPU time per game under B is at most 0.85 times A's. Otherwise RETAIN runtime-r1, and no runtime
  identity is created.
* **Worker count.** Only constrained tiers count, against B-w01: speedup at least 1.5, efficiency at least 0.70,
  decision-latency p99 at most 1.5 times and maximum at most twice B-w01's, our mean CPU use at most 32 logical
  CPUs, peak memory at most 10% of the host. If the runtime is promoted, the recommendation is the smallest
  acceptable count among 16, 24 and 32 whose speedup is at least 0.85 of the largest acceptable speedup, or 16 if
  none is acceptable. Otherwise it stays 16 workers on runtime-r1. No untested count is recommended.

## Running

```bash
PYTHON scripts/build_runtime_thread_plan.py --check
PYTHON scripts/qualify_runtime_threads.py stage --sdk-archive ZIP
PYTHON scripts/qualify_runtime_threads.py build-probe
PYTHON scripts/qualify_runtime_threads.py process
PYTHON scripts/qualify_runtime_threads.py tier --tier P-A     # then E-B, B-w01, A-w16, B-w16, A-w24, B-w24
PYTHON scripts/qualify_runtime_threads.py analyze
```

## Results

None at registration.
