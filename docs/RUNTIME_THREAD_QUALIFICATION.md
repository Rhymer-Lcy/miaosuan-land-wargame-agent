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

Every tier ran in order and passed every equivalence, safety, engine-state and ledger check. B-w24 met every worker
criterion with an efficiency of 0.868, at least the 0.85 the optional tier required, so B-w32 ran.
496 games in 8 tiers used engine sessions 1354 to 1849; the 16 games of the production-path check
used sessions 1850 to 1865. Every figure below comes from `evaluation/runtime-thread-qualification-1/results.json`
unless a source is named; `scripts/qualify_runtime_threads.py analyze --check` regenerates it from the private tier
summaries, and `tests/test_runtime_thread_results.py` recomputes its throughput, criteria, comparison and disposition
from its own figures.

### Execution

* The plan's commit `2a8cf6f` was verified on the public remote at 2026-10-01T14:30:31+08:00, before the
  process-level check and the first qualification session. Every tier ran at that commit from a clean tree.
* Before each tier the host was quiet: other activity used at most 0.20 logical CPUs in the 30 s check,
  at most 0.51 on average during a tier, and no tier was contended.
* After the runs the analysis gained the production-path check (`77c0763`) and the slow-decision attribution
  (`4e70a02`), and the tier summaries were rederived from what the tiers had collected. One rederivation, run from a
  work tree reached through a symbolic link, flagged each game's own log as an unexpected writable file, because the
  descriptor check compared real paths with the link's path; the check now resolves the folder (`4e70a02`) and every
  summary was rederived again, with every check passing. No game was rerun and no collected data changed.

### BLAS runtime and its use

| Measure (fresh interpreter, no engine) | A: no variable | B: `OPENBLAS_NUM_THREADS=1` |
|---|---|---|
| threads before / after importing NumPy | 1 / 64 | 1 / 1 |
| import wall time (median of 10) | 100.1 ms | 66.4 ms |
| process CPU during the import (median) | 5.90 s | 0.07 s |
| process CPU after a 0.5 s settle (median) | 5.92 s | 0.07 s |
| involuntary context switches (median) | 37 | 0 |
| 16 started at once: CPU / involuntary switches / import wall per interpreter | 0.880 s / 479,306 / 240.1 ms | 0.133 s / 1.6 / 71.7 ms |
| 24 started at once: CPU / involuntary switches / import wall per interpreter | 0.908 s / 517,660 / 319.7 ms | 0.139 s / 1.4 / 71.8 ms |

* Both environments map the same library, `libopenblas64_p-r0-0cf96a72.3.23.dev.so`, NumPy's bundled OpenBLAS, and no OpenMP,
  MKL or other BLAS library. Under A the import creates the pool, whose 63 extra threads spin and then sleep; under B the
  library starts no thread at all.
* The call-counting shim, preloaded into all 16 games of P-A under A, counted no call to any of the 57 BLAS and LAPACK
  entry points beyond NumPy's own import check: 0 games with a call. The engine, both policies and the harness do
  no BLAS work during a game, so the pool's threads have nothing to do.
* The sanity operations show why that matters. A 1,000-element dot product and a 40 by 40 product are bit-identical
  between A and B; a 200,000-element dot product differs by one unit in the last place, and a 500 by 500 product and a
  50 by 50 solve differ as well. Each was identical across its three repetitions within an environment. OpenBLAS's
  thread count can change the rounding of large operations; the equivalence below rests on the engine performing none.

### Process-level effect in games

| Tier | Workers | Threads per process | CPU per game | main / other threads | Start-up CPU | Involuntary switches per game | main / other threads | before the game starts |
|---|---:|---:|---:|---|---:|---:|---|---:|
| P-A | 1 | 64 | 22.8 s | 16.95 / 5.26 s | 5.99 s | 91 | 40 / 37 | 37 |
| E-B | 1 | 1 | 16.9 s | 16.82 / 0.00 s | 0.12 s | 71 | 71 / 0 | 1 |
| B-w01 | 1 | 1 | 16.9 s | 16.80 / 0.00 s | 0.12 s | 60 | 60 / 0 | 1 |
| A-w16 | 16 | 64 | 23.9 s | 19.24 / 3.95 s | 4.70 s | 867,032 | 94 / 866,710 | 841,190 |
| B-w16 | 16 | 1 | 18.4 s | 18.31 / 0.00 s | 0.14 s | 32 | 32 / 0 | 0 |
| A-w24 | 24 | 64 | 24.1 s | 20.24 / 3.02 s | 3.21 s | 1,302,848 | 183 / 1,302,816 | 1,189,747 |
| B-w24 | 24 | 1 | 19.4 s | 19.27 / 0.00 s | 0.15 s | 325 | 325 / 0 | 1 |
| B-w32 | 32 | 1 | 20.6 s | 20.42 / 0.00 s | 0.14 s | 151 | 151 / 0 | 1 |

Medians over a tier's games; the parts need not add up to the total's median. Start-up CPU runs from the process's
start until NumPy is imported. In P-A the preloaded shim loads OpenBLAS when the process starts, before the interpreter
runs, so the pool's spin counts as start-up there and not as import.

* Under B every game process ran one thread, and nothing but the main thread used CPU or was switched out.
* The median CPU time per game fell from 23.9 s to 18.4 s at 16 workers (ratio 0.772) and from 24.1 s to
  19.4 s at 24 (0.806). Serially B-w01 needed 16.9 s per game, against 22.7 s in the committed w01.
* Throughput barely moved: B over A was 1.032 at 16 workers and 1.003 at 24. The pool's spin ran
  beside the main thread on otherwise idle CPUs, so removing it saves CPU time, not wall time.

### Behavioural equivalence

| Tier | Runtime | Games | Deterministic identical | Stochastic prefix equal | Shared chains | Divergence past the first shot (minimum) |
|---|---|---|---|---|---|---|
| P-A | runtime-r1 | 16 of 16 | 10 of 10 | 6 of 6 | 0 | 1 step |
| E-B | runtime-r2 | 16 of 16 | 10 of 10 | 6 of 6 | 0 | 1 step |
| B-w01 | runtime-r2 | 16 of 16 | 10 of 10 | 6 of 6 | 0 | 1 step |
| A-w16 | runtime-r1 | 64 of 64 | 40 of 40 | 24 of 24 | 0 | 1 step |
| B-w16 | runtime-r2 | 64 of 64 | 40 of 40 | 24 of 24 | 0 | 1 step |
| A-w24 | runtime-r1 | 96 of 96 | 60 of 60 | 36 of 36 | 0 | 1 step |
| B-w24 | runtime-r2 | 96 of 96 | 60 of 60 | 36 of 36 | 0 | 1 step |
| B-w32 | runtime-r2 | 128 of 128 | 80 of 80 | 48 of 48 | 0 | 1 step |

* Under the constrained runtime 320 games in five tiers, both policies in E-B, reproduced the serial references:
  every deterministic game (200) the state chain, the step count and every seat's trace chain that all 15
  serial repetitions share, and every stochastic game (120) the state and trace digests up to the serial common prefix. No
  difference occurred before that prefix or in a deterministic game, so nothing had to be judged as floating point.
* In every tier each stochastic game first differed from its closest serial repetition no earlier than one step after
  its first shot, no two stochastic games shared a trajectory, none equalled a serial one, and every refusal was of a known
  class, with no contract error, gate rejection or replay mismatch.
* The current runtime's tiers (176 games) passed the same comparison.

### Context switches

* The committed figure of 837,450 involuntary switches per game at 16 workers was measured correctly. It is the
  child's total from `wait4`, and in this run each game's own `getrusage` at its end agreed with it (median ratio
  0.987 to 1.000 across tiers).
* It is genuine, and it is the pool's start-up. A-w16 repeated it (867,032 per game): the main thread accounted for
  94, the other 63 threads for 866,710, and 841,190 (97%) had happened by the time NumPy's
  import returned, before the game's first step. The process-level check reproduces them without the engine: 37 per
  interpreter started alone, 479,306 per interpreter when 16 start at once.
* Under B the count fell to 32 per game at 16 workers and 325 at 24, all on the main thread.

### Scaling

| Runtime | Workers | Games/hour | Speedup | Efficiency | Host CPU | Threads/process | p95 game time |
|---|---:|---:|---:|---:|---:|---:|---:|
| runtime-r1, committed | 1 | 68.1 | 1.00 | 1.000 | 1.9% | 64 | 192.8 s |
| runtime-r1, committed | 16 | 959.8 | 14.09 | 0.881 | 26.5% | 64 | 212.1 s |
| runtime-r1, committed | 24 | 1,386.2 | 20.35 | 0.848 | 38.9% | 64 | 217.5 s |
| runtime-r1, A-w16 | 16 | 940.8 | 13.81 | 0.863 | 26.2% | 64 | 213.5 s |
| runtime-r1, A-w24 | 24 | 1,390.5 | 20.41 | 0.850 | 39.1% | 64 | 220.9 s |
| runtime-r2, B-w01 | 1 | 67.0 | 1.00 | 1.000 | 1.8% | 1 | 202.6 s |
| runtime-r2, B-w16 | 16 | 971.3 | 14.50 | 0.906 | 24.9% | 1 | 211.7 s |
| runtime-r2, B-w24 | 24 | 1,394.6 | 20.82 | 0.868 | 37.3% | 1 | 217.3 s |
| runtime-r2, B-w32 | 32 | 1,793.2 | 26.77 | 0.837 | 49.8% | 1 | 229.3 s |

Speedups of runtime-r2 are against B-w01 (67.0 games per hour), as the plan registers; those of runtime-r1 against
the committed w01 (68.1), because A was not rerun serially.

| Tier | Decision p50 / p95 / p99 | Decision max | Over 1 s | Our logical CPUs | Peak memory (all games) | Others' CPUs |
|---|---|---:|---:|---:|---:|---:|
| B-w01 | 0.457 / 1.202 / 1.229 ms | 1,318.3 ms | 1 | 1.0 | 1.8 GiB (0.4%) | 0.14 |
| A-w16 | 0.620 / 1.420 / 1.465 ms | 1,394.5 ms | 5 | 16.6 | 21.6 GiB (4.4%) | 0.28 |
| B-w16 | 0.592 / 1.409 / 1.448 ms | 1,304.5 ms | 9 | 15.8 | 21.4 GiB (4.4%) | 0.30 |
| A-w24 | 0.640 / 1.440 / 1.492 ms | 1,448.2 ms | 11 | 24.8 | 32.2 GiB (6.6%) | 0.43 |
| B-w24 | 0.643 / 1.444 / 1.494 ms | 1,243.8 ms | 11 | 23.6 | 32.6 GiB (6.7%) | 0.40 |
| B-w32 | 0.673 / 1.509 / 1.569 ms | 1,578.5 ms | 20 | 31.6 | 42.3 GiB (8.7%) | 0.51 |

* The same work cost more CPU time as workers were added: 16.9 s per game in B-w01, 18.4 s in B-w16, 19.4 s in B-w24
  and 20.6 s in B-w32 (22% more than serially). The host has 32 physical cores with 2 hardware threads each, so
  at 32 workers games increasingly share a core. The slowdown was not attributed further; with no pool thread running
  under B, it is contention between the games themselves.

### Tail latency

| Tier | First play decision p50 / max | Decisions over 100 ms (first play / later) | Collections over 1 s | Longest generation-2 collection | Decision max |
|---|---|---|---:|---:|---:|
| B-w01 | 12.0 / 105.6 ms | 2 / 5 | 22 | 1,354.5 ms | 1,318.3 ms |
| A-w16 | 12.8 / 121.0 ms | 9 / 34 | 97 | 1,423.4 ms | 1,394.5 ms |
| B-w16 | 12.5 / 119.5 ms | 12 / 46 | 93 | 1,391.4 ms | 1,304.5 ms |
| A-w24 | 13.0 / 123.7 ms | 24 / 48 | 165 | 1,761.1 ms | 1,448.2 ms |
| B-w24 | 12.9 / 125.1 ms | 22 / 93 | 163 | 2,029.2 ms | 1,243.8 ms |
| B-w32 | 13.5 / 225.8 ms | 33 / 76 | 246 | 1,576.8 ms | 1,578.5 ms |

* **Routing.** The first play decision, which plans routes, took a median of 11.9 to 13.5 ms in every tier. Its maximum
  rose from 105.6 ms serially to 225.8 ms at 32 workers, still well under the 516.0 ms of the route search before
  the routing remediation.
* **Collections.** Collections of more than 1 s happen serially under both runtimes: 22 in B-w01, against
  1 decision over 1 s, so most fall outside the timed decisions. Constraining the pool did not shorten them:
  97 against 93 collections over 1 s at 16 workers and 165 against 163 at 24, and the longest collection of the
  whole run, 2,029.2 ms, was in B-w24. The decision-latency p99 was unchanged (B over A 0.988 at 16 workers,
  1.001 at 24).
* **The maximum is one event.** It records whichever collection lands inside a timed decision. In the 16-game corpus
  the longest decision of group B's games was 1,158.5 ms under A and 318.7 ms under B, but of group C's 669.8 ms under A
  and 1,283.3 ms under B. The B over A ratios of the maximum (0.935 at 16 workers, 0.859 at 24) are therefore not
  evidence of a shorter tail.
* **The registered base.** B-w01's maximum, 1,318.3 ms, is 1.60 times the committed w01's 822.8 ms, so the
  registered latency criterion, computed against B-w01, was more lenient than in the concurrency qualification. As a
  sensitivity reading, not a change of rule: against the committed base B-w32's ratios would be 1.28 (p99) and 1.92
  (maximum), within the limits of 1.5 and 2, and the knee rule would still select 32. Likewise A-w24's maximum here,
  1,448.2 ms, is 1.76 times the committed base, whereas the committed w24 reached 2.14: that failure did not recur.

### Integrity

* Every tier opened and closed each of its sessions once, with consecutive numbers (1354 to 1849), no recovery and
  nothing left unclosed; package integrity held with nothing added, `home/` stayed empty, and the engine state file
  kept its hash, size, modification and status-change times, which still equal its first use of 2026-09-29.
* No game opened a socket, held an unexpected writable file, wrote to its working directory or `TMPDIR`, mapped a GPU,
  OpenMP or CUDA library, or appeared as a GPU process. Our processes per tier never exceeded the tier's workers.

### Disposition

| Tier | Throughput | Efficiency | Latency (p99 / max ratio) | Headroom | Acceptable |
|---|---|---|---|---|---|
| B-w16 | pass (14.50) | pass (0.906) | pass (1.18 / 0.99) | pass (15.8 CPUs, 4.4% memory) | yes |
| B-w24 | pass (20.82) | pass (0.868) | pass (1.22 / 0.94) | pass (23.6 CPUs, 6.7% memory) | yes |
| B-w32 | pass (26.77) | pass (0.837) | pass (1.28 / 1.20) | pass (31.6 CPUs, 8.7% memory) | yes |

| Registered benefit | Measured | Required | Holds |
|---|---|---|---|
| (a) a constrained tier above 16 workers is acceptable | B-w24 and B-w32 acceptable | at least one | yes |
| (b) constrained throughput over current, 16 or 24 workers | 1.032 / 1.003 | at least 1.05 | no |
| (c) CPU per game, constrained over current, 16 workers | 0.772 | at most 0.85 | yes |

**PROMOTED AS baseline-v1-runtime-r2.** No check failed in any tier, and benefits (a) and (c) hold. Benefit (c) is the direct
effect: one thread instead of 64 and 23% less CPU per game. Benefit (a) holds under the rule, but this
run does not attribute it to the constrained runtime: against the committed base A-w24 met every
worker criterion as well (speedup 20.41, efficiency 0.850, latency ratios 1.22 / 1.76, 24.8 CPUs), and A-w32 was not
run. What the constrained runtime does add at 32 workers is room under the courtesy ceiling: at 24 workers A used 1.1 logical
CPUs more than B, and B-w32 stayed 0.4 below the ceiling of 32.

### Recommended worker count

**32 workers on `baseline-v1-runtime-r2`.** B-w16, B-w24 and B-w32 are acceptable; the largest acceptable speedup is
26.77 (B-w32), and B-w24's 20.82 is below 0.85 of it (22.76), so 32 is the smallest acceptable count within the knee.
At 32 workers our games used 31.6 logical CPUs on average, 49.8% of the host's CPU, and at most 8.7% of its
memory. 32 is the largest count tested and sits at the courtesy ceiling; no higher count is recommended. On
`baseline-v1-runtime-r1` the recommendation stays 16 workers.

### Production path

Added after the qualification passed:

* `src/miaosuan_agent/evaluation/execution.py` defines the two runtimes and their variables: `baseline-v1-runtime-r1`
  none, `baseline-v1-runtime-r2` exactly `OPENBLAS_NUM_THREADS=1`. It is the only place a runtime's environment is
  defined; the serial loop and the pool take the variables from it, never from the caller's environment.
* A manifest's `execution` block registers `workers`, `runtime` and `scheduler`. Missing fields mean 1 worker, runtime-r1
  and no scheduler pin, which is what every earlier registration ran with, so none of them changes, and runtime-r1
  game records carry no new field. A registered run cannot change its runtime or worker count, and with a registered
  scheduler the pool refuses to start under another identity (`--expected-scheduler`).
* `scripts/run_evaluation.sh --runtime ID` selects a runtime for diagnostic runs only. Each game refuses to play when
  its effective numerical-thread variables differ from its runtime's, and records the runtime and its variables; the
  pool's run file records them too.
* The pool's sources changed to carry the runtime, so its identity changed from the one the plan pins
  (`miaosuan-game-pool/1@628180cb…`) to `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90`.
* The 16-game corpus ran through `run_evaluation.sh --runtime baseline-v1-runtime-r2 --workers 32` (sessions 1850
  to 1865, one batch of 8 group-B and 8 group-C games). All 16 records name runtime-r2 and its variable, all
  16 passed the independence comparison with their serial references, and the engine state stayed one. Production path:
  pass.

```bash
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan ab \
    --evaluation baseline-v2-candidate-shoot-target-reservation --purpose diagnostic \
    --work DIR/production --games corpus.txt --runtime baseline-v1-runtime-r2 --workers 32
PYTHON scripts/qualify_runtime_threads.py production-check --workers 32
```

### Operational impact

| Runtime | Workers | Games/hour (measured) | 192 games | 720 games |
|---|---:|---:|---:|---:|
| runtime-r1 (committed w01) | 1 | 68.1 | 2.8 h | 10.6 h |
| runtime-r1 (committed w16) | 16 | 959.8 | 12 min | 45 min |
| runtime-r2 (B-w01) | 1 | 67.0 | 2.9 h | 10.8 h |
| runtime-r2 (B-w16) | 16 | 971.3 | 12 min | 44 min |
| runtime-r2 (B-w32) | 32 | 1,793.2 | 6 min | 24 min |

Both game counts are extrapolations from tiers of 16 to 128 games of this configuration mix, run longest first. A
registered plan dispatches in its schedule order and has its own mix, so its makespan scales only as far as its
longest games and its start and end allow; no run is shorter than its longest game (233.3 s at 32 workers here).

### Limitations

* One host, one engine build, eight configurations, tiers of 16 to 128 games. Decision-latency maxima are single
  events set by where collections fall, and tiers of this size cannot rank runtimes by them.
* `baseline-v1-runtime-r2` is equivalent to runtime-r1 for code that makes no large BLAS call, which the probe and the
  equivalence show for the current policies. A change that adds linear algebra must be checked under the runtime it
  registers: the sanity operations show that large BLAS and LAPACK results can differ between the two settings.
* 32 workers assumes a host as quiet as this one was (others used under one logical CPU). On a busier host fewer
  workers keep within the courtesy ceiling; the evaluator does not check the host's load itself.
* The collection tail is unchanged; an experiment that measures decision latency should run serially or report its
  worker count and runtime.
