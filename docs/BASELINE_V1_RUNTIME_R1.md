# Runtime identity: baseline-v1-runtime-r1

`baseline-v1-runtime-r1` is a runtime of the tactical `baseline-v1`: the same decisions from the same inputs,
computed with a shortest-path search that stops once every objective the decision reads is settled. It is
the promoted name of `baseline-v1-routing-bounded-candidate`, promoted after every criterion of the
registered routing remediation held (`docs/ROUTING_REMEDIATION.md`). It is not a new tactical baseline:
`baseline-v1` remains the tactical reference and still verifies under its own identity (`docs/BASELINE_V1.md`).

## Identity

| Field | Value |
|---|---|
| Identity | `baseline-v1-runtime-r1`, the promoted name of the executed candidate `baseline-v1-routing-bounded-candidate`. The code and every trace keep the candidate name |
| Parent | `baseline-v1`: policy source `1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9`, golden decision chain `11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66`, results `ea0ec674e8e51e546684fb75696673e5c81d32d6c9dd7a0d11796a91aeaeda07` |
| Policy source | SHA-256 `f9e50a538f1f530e9e485f75ce3d457435cfb9bcc2eb039ecdfa9374d54398ad` over `baseline-v1`'s sources, byte-identical, plus `experiments/routing_bounded.py` (`candidate_sources()` in `src/miaosuan_agent/evaluation/runtime_remediation.py`) |
| Decision identity | the decisions of `baseline-v1`: equal actions and equal traces except the `policy` field; the candidate's semantic chain over the golden sequence equals `baseline-v1`'s (`tests/test_routing_bounded.py`) |
| Routing identity | the frozen Dijkstra (heap of `(cost, hex)`, strict improvement, roadblocks for vehicle modes), stopped once every objective not held by the side is settled or the frontier is exhausted; memo key `(start, mode, roadblocks, target set)`, 32 entries |
| Registration | `evaluation/routing-remediation-1/registration.json`, canonical SHA-256 `ffe4539d505dc53bc7b3875d9f9e451fc14ead6a4dd89bffe060bac028e87184`, commit `9568da2`, pushed before the candidate was implemented |
| Replay corpus | 22 private files pinned in `corpus.json`, corpus digest `2fb5470b87bf55c3809ee7476e3afe5faf17a4ab96523340214ea405ef7f6588`, 33,802 decisions |
| Results | `equivalence.json` `f44417d4cd0df076f021d209126428368f5dc42b2ce7a28262e2bfaf9eabb8ee`; `mutation.json` `ac289f45706d778d6ec385e4639998b5b7995639c37c7dd7992ae9c58161cae4`; `benchmark.json` `0898a29fa65ca96eac65a2ac0e6850aa145ca7594481455d2493665046d5f56f`; `engine.json` `e68883d6e401b07c61a37832b37ea978e33befde2d9ac3b0e8d348c0be283b3c` (file SHA-256) |
| Engine | `land_wargame_train_env` 4.1.0 from the persistent installation; diagnostic sessions 0351 to 0353 |
| Runtime | CPython 3.10.20 (`miaosuan-runtime`, CPU only); the public tests also pass on CPython 3.12 |
| Configuration | none: no parameters, thresholds or weights |

Verify the identity of a checkout:

```bash
python -m unittest tests.test_routing_bounded tests.test_routing_remediation_tools tests.test_remediation_registration
```

## What changed and what did not

On the first play decision of the largest scenario the decision takes 0.178 times `baseline-v1`'s median time offline
(median 516.0 ms to 91.6 ms) and between 0.174 and 0.413 of its shadow's time in the engine. Decisions
that request no path are unchanged in cost. Everything else is `baseline-v1`, including its known limitations,
and the late-game collection pauses of the shared engine process are not addressed.

## Use

A tactical experiment on top of `baseline-v1` runs every arm on this runtime, so that routing latency cannot
differ between arms. The shooting-conflict experiment ran both of its arms on it
(`docs/EVALUATION_SHOOT_RESERVATION.md`), and the baseline it promoted, `baseline-v2` (`docs/BASELINE_V2.md`),
runs on it.

`baseline-v1-runtime-r2` (`docs/BASELINE_V1_RUNTIME_R2.md`) is this runtime's code run with NumPy's OpenBLAS pool
limited to one thread. It makes the same decisions and uses less CPU per game; this runtime keeps its name and stays
the default of every manifest that registers no runtime.
