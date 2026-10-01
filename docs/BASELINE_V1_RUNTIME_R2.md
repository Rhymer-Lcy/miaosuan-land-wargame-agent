# Runtime identity: baseline-v1-runtime-r2

`baseline-v1-runtime-r2` is `baseline-v1-runtime-r1` with one environment variable, `OPENBLAS_NUM_THREADS=1`, in every
game process. The code is runtime-r1's, byte for byte; no policy, routing, collection setting or engine file differs.
It was promoted by the registered runtime thread-pool qualification (`docs/RUNTIME_THREAD_QUALIFICATION.md`). It is a
runtime, not a tactical baseline: `baseline-v2` (`docs/BASELINE_V2.md`) and `baseline-v1` make the same decisions on
it as on runtime-r1, which keeps its name and stays the default.

## Identity

| Field | Value |
|---|---|
| Identity | `baseline-v1-runtime-r2`, an execution identity: runtime-r1's code run with the environment delta below |
| Parent | `baseline-v1-runtime-r1` (`docs/BASELINE_V1_RUNTIME_R1.md`): policy source `f9e50a538f1f530e9e485f75ce3d457435cfb9bcc2eb039ecdfa9374d54398ad`, routing-remediation registration `ffe4539d505dc53bc7b3875d9f9e451fc14ead6a4dd89bffe060bac028e87184` |
| Code | identical to the parent's. Games on runtime-r2 carry the same policy source digests as on runtime-r1: `f9e50a538f1f530e9e485f75ce3d457435cfb9bcc2eb039ecdfa9374d54398ad` for `baseline-v1` on the runtime, `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` for `baseline-v2` |
| Environment delta | `OPENBLAS_NUM_THREADS=1`, added to each game's otherwise empty environment before the interpreter starts, and no other variable (`RUNTIMES` in `src/miaosuan_agent/evaluation/execution.py`). A game refuses to play when its effective numerical-thread variables differ |
| Effect | NumPy's bundled OpenBLAS 0.3.23.dev starts no pool: 1 thread per game process instead of 64; median CPU per game 0.772 times runtime-r1's at 16 workers |
| Behavioural equivalence | 320 games on runtime-r2 in five tiers: 200 of 200 deterministic games identical (state chain, step count, every seat's trace chain) and 120 of 120 stochastic games equal to the serial prefix, both policies; the call-counting probe found no BLAS call in 16 games |
| Scheduler compatibility | the serial loop and `scripts/run_game_pool.py` both take the variable from `execution.py`; production-path check of 16 games at 32 workers, sessions 1850 to 1865, scheduler `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90`: pass |
| Benchmark identity | plan `evaluation/runtime-thread-qualification-1/plan.json`, canonical SHA-256 `06a05d2b71ce499b6fb41c9597206fe4d700ddbb2be01a8484e7341c37c1cfcf`, commit `2a8cf6f`; results `results.json`, file SHA-256 `39a6cefc0b634bb86325af2298272671046841ef3b5ca066799b898431c3a798`; workload of the concurrency qualification (plan `f6d0f1b1adf2f7b5e41e67513304528d50d415f17a3aae7a281f7f1c831c304c`); engine sessions 1354 to 1849 |
| Recommended workers | 32, measured (speedup 26.77, efficiency 0.837); 16 stays the recommendation on runtime-r1 |
| Engine | `land_wargame_train_env` 4.1.0 from the persistent installation |
| Runtime environment | CPython 3.10.20 (`miaosuan-runtime`, CPU only), NumPy 1.26.2 |
| Configuration | one environment variable; no parameters, thresholds or weights |

Verify the identity of a checkout:

```bash
python -m unittest tests.test_execution tests.test_runtime_threads tests.test_runtime_thread_results
```

## What changed and what did not

Changed: one thread per game process instead of 64; the median CPU time per game at 16 workers fell from
23.9 s to 18.4 s, and the involuntary context switches per game from 867,032 to 32.
Unchanged: the decisions (320 games compared with the serial references), the throughput (runtime-r2 over runtime-r1 1.032 at 16 workers and 1.003 at 24), the decision-latency
p99, and the late-game collection pauses of the shared engine process, which runtime-r2 does not address.

The equivalence holds for code that makes no large BLAS call, as the current policies make none. Large BLAS and
LAPACK results can differ between OpenBLAS's pool and one thread (a 200,000-element dot product by one unit in the
last place), so a change that adds linear algebra must be checked under the runtime it registers.

## Use

A registered evaluation selects the runtime and the worker count in its manifest's `execution` block, for example
`{"workers": 32, "runtime": "baseline-v1-runtime-r2", "scheduler": "miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90"}`;
`scripts/run_evaluation.sh` then refuses any other runtime, worker count or scheduler. A manifest without the block
runs serially on runtime-r1, as every registration before this runtime did. Diagnostic runs take `--runtime` and
`--workers` directly. Both arms of an A/B experiment always run on the same runtime.
