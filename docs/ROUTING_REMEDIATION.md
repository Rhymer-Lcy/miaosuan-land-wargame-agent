# Routing remediation of baseline-v1

`routing-remediation-1` is a behaviour-preserving engineering change. It replaces the full-map
shortest-path search of the frozen `baseline-v1` with one that stops once every objective the
decision reads is settled. The aim is the same actions and the same decision content for the
same input, with less intrinsic latency at the first play decision (`docs/LATENCY_DIAGNOSTIC.md`).
It is not a tactical change and not a new tactical baseline. `baseline-v1` itself stays frozen:
its source, digest, golden chain, manifests and results are untouched.

This document was committed with the registration, before the candidate was implemented or timed.
The registration is `evaluation/routing-remediation-1/registration.json`, built by
`scripts/build_remediation_registration.py` from `src/miaosuan_agent/evaluation/runtime_remediation.py`;
where they differ, the registration governs. Results are appended under "Results".

## Identities

* Parent: `baseline-v1`, policy source `1d01e48a…`, golden decision chain `11e12bf0…`.
* Candidate: `baseline-v1-routing-bounded-candidate`. Its sources are `baseline-v1`'s, byte-identical,
  plus the one added file `src/miaosuan_agent/experiments/routing_bounded.py`.
* Name if promoted: `baseline-v1-runtime-r1`. It would be a runtime of the tactical `baseline-v1`, not a
  new tactical baseline.

## The routing contract being preserved

Characterized by `tests/test_routing_contract.py` before any change:

* **Who routes.** Move candidates are computed for every controllable unit that lists movement, is not
  executing a move, has a documented movement mode, and does not stand on an objective not held by its
  side.
* **What is read.** Only the cost and path of each objective not held by the side.
* **The search.** Dijkstra from the unit's hex over the setup-supplied costs of the unit's movement mode.
  Roadblock hexes are excluded as neighbours for the two vehicle modes only, and the start hex is never
  checked against them.
* **Costs.** Entry costs are positive and finite; the boundary rejects anything else.
* **Tie-breaking and relaxation.** The frontier is a heap of `(cost, hex)`, so equal costs pop in
  ascending hex order. Settled and blocked neighbours are skipped. A neighbour's cost and predecessor
  change only on a strictly lower cost, and neighbour order is irrelevant.
* **Paths.** A path is the predecessor chain from the objective back to the start, without the start.
* **Unreachable objectives.** An objective absent from the result is unreachable and yields no candidate.
* **Choice.** The chosen objective has the smallest `(cost, objective hex)`.
* **Memo.** A first-in-first-out memo of 32 entries keyed by `(start, mode, roadblocks)`; no result
  depends on it.

## Why the bounded search is equivalent

1. The bounded search performs the full search's pops and relaxations in the same order and stops
   partway, so it is a prefix of the full run.
2. A settled hex's cost and predecessor never change later, and every hex on its path was settled
   before it. Settled hexes therefore have equal costs and paths.
3. The search stops only when every target is settled. An unreachable target keeps it running to the
   end of the frontier, which is the full run.
4. The policy reads only targets, so candidates, choices, actions and trace content are equal.
5. The bounded result exposes settled hexes only.

The memo key adds the target set to `(start, mode, roadblocks)`. Objectives change as they are taken
or lost, so a truncated result must never serve another target set. The router belongs to one agent
and one map.

## Criteria

**Equivalence**, E1-E11 in the registration:

* the parent still verifies, and the source delta is exactly the added file;
* the characterization and differential routing tests pass, and mutation testing kills every
  non-equivalent mutant;
* over every registered replay input, both agents given the same observation and memory produce equal
  action lists, equal semantic traces and equal contract errors, and neither modifies the observation.
  The semantic trace is the trace dictionary without its `policy` field. Unexplained differences: 0;
* the candidate's semantic golden chain equals `baseline-v1`'s;
* in the engine diagnostic, a shadow `baseline-v1` agent compares every decision live;
* no tactical rule and no legality check changes.

**Performance**, fixed before measurement:

* On the first play decision of 2130511121 (as in the replay corpus and as captured in the latency
  diagnostic), the candidate's median `agent.step` time with a fresh agent must be at most half of
  `baseline-v1`'s, measured interleaved in the same benchmark invocation.
* No other registered state may be slower than `baseline-v1`'s median × 1.10 + 0.2 ms.
* In the engine, the candidate's first play decision on 2130511121 must take at most half the time
  its shadow `baseline-v1` takes on the same observation.
* The basis: the diagnostic measured about 500 ms, 99% of it in Dijkstra, and estimated that 15.8% of
  the settled nodes are needed. The factor of two leaves room for the bounded search's own overhead.
  No platform deadline is assumed.

**Corpus.** 22 private files pinned by SHA-256 in `evaluation/routing-remediation-1/corpus.json`:
* the 8 recorded games of the replay corpus;
* the 9 states of the latency diagnostic;
* the captures of its 5 engine games.

The variance-study records hold no observations and cannot be replayed.

**Engine diagnostic.** Three diagnostic sessions:
* 2130511121 C1, with both seats on the candidate;
* 2130511121 C3;
* 2010131194 C3, as a small control.

No score is compared.

**Promotion.** Only if E1-E11 all hold. Otherwise the candidate is kept as failed or partial.

**Out of scope.** Garbage collection (no setting, call or threshold changes), every tactical rule, and
the shooting-conflict experiment.

## Results

Executed on 2026-09-30 (UTC+8). The replay, the benchmark and the engine diagnostic ran on the Linux host of
the persistent engine installation (CPython 3.10.20); the mutation test gives the same outcome there and on
CPython 3.12. The registration (`registration.json`, canonical SHA-256 `ffe4539d…`) was
pushed in commit `9568da2` before the candidate existed; the candidate, policy source
`f9e50a53…`, was committed in `69a8d1f`. The figures below come from four
aggregates in `evaluation/routing-remediation-1/`:

* `equivalence.json`, from `scripts/compare_routing_candidate.py`;
* `mutation.json`, from `scripts/mutate_routing_candidate.py`;
* `benchmark.json`, from `scripts/benchmark_routing_candidate.py`;
* `engine.json`, from `scripts/analyze_routing_diagnostic.py`.

Observations, traces and per-call timings stay under the git-ignored `local/` tree.

### Criteria

| Criterion | Verdict | Evidence |
|---|---|---|
| E1 | pass | `baseline-v1`'s policy source `1d01e48a…`, golden chain `11e12bf0…` and manifests verify; its results and the variance study's results regenerate byte-identically |
| E2 | pass | no file of `baseline-v1`'s source set changed; the candidate adds exactly `experiments/routing_bounded.py` |
| E3 | pass | `tests/test_routing_contract.py` (11 tests) and `tests/test_routing_bounded.py` (14 tests): hand-made cases, a 60 x 80 grid, 400 generated graphs (seed 20260930), and the memo over changing targets, roadblocks and modes |
| E4 | pass | 15 of 15 non-equivalent mutants killed; 5 equivalent mutants identified, each surviving as argued |
| E5 | pass | 33,802 of 33,802 registered decisions identical: actions and their order, semantic trace, memory, contract errors; no observation modified |
| E6 | pass | 1,751 of 1,751 move paths and chosen objectives equal |
| E7 | pass | the candidate's semantic chain over the golden sequence equals `baseline-v1`'s; `baseline-v1`'s own golden chain is unchanged |
| E8 | pass | first play decision of 2130511121: median 516.0 ms to 91.6 ms (ratio 0.178); on the same decision as captured by the latency diagnostic, ratio 0.179; every other state within its limit |
| E9 | pass | 3 of 3 diagnostic games completed; 10,444 decisions compared live with the shadow, none different; engine state unchanged |
| E10 | pass | from E2 and E5 |
| E11 | pass | from E5 and E9 |

### Full-agent equivalence

Both agents decided on every registered input: the replay-corpus games seat by seat with persistent agents,
the rest with new agents and the recorded memory. The count compared equals the pinned count, file by file.

| Inputs | Decisions | Identical | Moves (paths and objectives equal) | Units without action (reasons equal) |
|---|---|---|---|---|
| latency diagnostic captured slow state | 5 | 5 | 32 (32) | 188 (188) |
| latency diagnostic captures | 97 | 97 | 1,176 (1,176) | 1,827 (1,827) |
| latency diagnostic state | 4 | 4 | 34 (34) | 46 (46) |
| replay corpus game | 33,696 | 33,696 | 509 (509) | 378,148 (378,148) |
| total | 33,802 | 33,802 | 1,751 (1,751) | 380,209 (380,209) |

The comparator reports planted faults: reversed or dropped actions, a modified observation, a different
memory, a shifted objective, a changed no-op reason, a reversed path, and searches stopped early or run in
another movement mode (`tests/test_routing_remediation_tools.py` and a private check over the registered states).

### Mutation

15 non-equivalent mutants of the candidate's search, memo key and policy hook were all
killed by the routing tests. Two of them survived earlier versions of the tests: the movement mode dropped
from the memo key, before `test_the_memo_distinguishes_movement_modes` existed, and tentative predecessors
exposed, against the tests of commit `7f52e39`, which compared costs and paths but not the predecessor map.
The tests that kill them were added before the recorded run. The equivalent mutants survive, as argued:

* duplicate-pop guard removed: a stale heap entry has a larger distance than the hex's settled cost; re-expanding it can offer no neighbour a strictly lower cost (entry costs are positive and float addition is monotone), and the stop test is unaffected.
* settle and discard swapped: two independent operations on different sets, with nothing between them.
* memo capacity 1: every memo entry is a pure function of its full key, so recomputation returns an equal result; only work changes.
* mode kept as an enum in the key: MoveMode is an IntEnum: each member hashes and compares equal to its integer value.
* settled neighbours not skipped: a settled neighbour's cost is at most the current distance, so distance plus a positive entry cost is never strictly lower; the relaxation never fires.

### Offline latency

Fresh agent, 200 calls per arm, interleaved; milliseconds. Criterion: ratio at most
0.50 on the two first-play states of 2130511121; elsewhere the candidate's median at most `baseline-v1`'s
x 1.10 + 0.20 ms.

| State | Kind | `baseline-v1` median / p99 / max | candidate median / p99 / max | Ratio | Criterion |
|---|---|---|---|---|---|
| 2010131194-seat11-decision1 | registered | 33.8 / 35.0 / 36.9 | 1.972 / 2.242 / 3.181 | 0.058 | pass |
| 2010131194-seat11-decision900 | registered | 0.243 / 0.383 / 0.449 | 0.246 / 0.377 / 0.388 | 1.011 | pass |
| 2130511121-seat11-decision1 | registered | 516.0 / 533.7 / 539.2 | 91.6 / 94.1 / 110.0 | 0.178 | pass |
| 2130511121-seat11-decision1-latdiag-1 | registered | 520.5 / 585.3 / 595.9 | 93.0 / 99.9 / 113.5 | 0.179 | pass |
| 2130511121-seat11-decision1000 | registered | 1.031 / 1.359 / 1.368 | 1.033 / 1.194 / 1.380 | 1.002 | pass |
| 2130511121-seat11-decision1177-latdiag-1 | registered | 1.384 / 1.848 / 19.1 | 1.384 / 1.822 / 22.5 | 1.000 | pass |
| 2130511121-seat11-decision211-latdiag-1 | registered | 1.274 / 1.475 / 1.563 | 1.276 / 1.520 / 2.339 | 1.001 | pass |
| 2130511121-seat11-decision2163-latdiag-1 | registered | 1.387 / 2.077 / 20.7 | 1.392 / 1.799 / 19.1 | 1.004 | pass |
| 2130511121-seat11-decision2714-latdiag-1 | registered | 1.392 / 1.857 / 20.0 | 1.393 / 1.984 / 20.7 | 1.001 | pass |
| 1910631192-seat11-decision1 | supplementary | 103.2 / 107.1 / 108.4 | 28.2 / 28.9 / 31.7 | 0.273 | pass |
| 1930331196-seat11-decision1 | supplementary | 289.9 / 296.3 / 297.2 | 112.6 / 114.2 / 114.6 | 0.389 | pass |
| 2010211129-seat11-decision1 | supplementary | 90.1 / 92.6 / 95.5 | 6.419 / 7.054 / 7.194 | 0.071 | pass |
| 201033019601-seat11-decision1 | supplementary | 1.203 / 1.535 / 1.627 | 0.823 / 1.101 / 1.131 | 0.684 | pass |
| 2010431153-seat11-decision1 | supplementary | 106.0 / 110.4 / 112.1 | 12.9 / 13.9 / 15.7 | 0.122 | pass |
| 2120531121-seat11-decision1 | supplementary | 331.2 / 338.9 / 340.3 | 97.2 / 99.5 / 119.4 | 0.294 | pass |

Cold first call in a new interpreter (10 per arm) and memo-warm calls on one agent (200 per arm); medians in milliseconds:

| State | Cold `baseline-v1` | Cold candidate | Memo-warm `baseline-v1` | Memo-warm candidate |
|---|---|---|---|---|
| 2010131194-seat11-decision1 | 35.9 | 2.074 | 0.198 | 0.199 |
| 2010131194-seat11-decision900 | 0.341 | 0.314 | 0.129 | 0.131 |
| 2130511121-seat11-decision1 | 496.1 | 88.1 | 2.787 | 2.763 |
| 2130511121-seat11-decision1-latdiag-1 | 500.4 | 87.7 | 2.782 | 2.759 |
| 2130511121-seat11-decision1000 | 1.214 | 1.207 | 0.869 | 0.871 |
| 2130511121-seat11-decision1177-latdiag-1 | 1.607 | 1.691 | 1.190 | 1.193 |
| 2130511121-seat11-decision211-latdiag-1 | 1.571 | 1.556 | 1.092 | 1.092 |
| 2130511121-seat11-decision2163-latdiag-1 | 1.606 | 1.616 | 1.203 | 1.206 |
| 2130511121-seat11-decision2714-latdiag-1 | 1.707 | 1.707 | 1.204 | 1.204 |
| 1910631192-seat11-decision1 | 100.0 | 26.5 | 0.517 | 0.519 |
| 1930331196-seat11-decision1 | 273.5 | 105.0 | 1.950 | 1.943 |
| 2010211129-seat11-decision1 | 86.1 | 5.994 | 0.346 | 0.348 |
| 201033019601-seat11-decision1 | 1.229 | 0.851 | 0.220 | 0.221 |
| 2010431153-seat11-decision1 | 100.1 | 11.8 | 0.453 | 0.453 |
| 2120531121-seat11-decision1 | 313.0 | 90.8 | 1.818 | 1.810 |

Every call is CPU-bound: the median thread-CPU share of wall time per state and arm lies between 1.000 and
1.008. The longest collection inside any measured call took 21.6 ms. Every one of the
12,300 calls produced `baseline-v1`'s actions and semantic trace for its input.

### Work reduction

Counted in a separate untimed pass per arm: searches, settled hexes and examined edges (neighbour entries read
while expanding a settled hex).

| State | Searches | Settled: `baseline-v1` / candidate (share) | Edges: `baseline-v1` / candidate (share) | Time ratio |
|---|---|---|---|---|
| 2010131194-seat11-decision1 | 2 | 14,168 / 650 (4.6%) | 83,660 / 3,815 (4.6%) | 0.058 |
| 2130511121-seat11-decision1 | 32 | 226,688 / 35,920 (15.8%) | 1,338,526 / 215,129 (16.1%) | 0.178 |
| 2130511121-seat11-decision1-latdiag-1 | 32 | 226,688 / 35,920 (15.8%) | 1,338,526 / 215,129 (16.1%) | 0.179 |
| 1910631192-seat11-decision1 | 6 | 42,504 / 10,324 (24.3%) | 250,956 / 61,394 (24.5%) | 0.273 |
| 1930331196-seat11-decision1 | 17 | 120,428 / 40,971 (34.0%) | 710,966 / 244,800 (34.4%) | 0.389 |
| 2010211129-seat11-decision1 | 5 | 35,420 / 2,116 (6.0%) | 203,048 / 12,591 (6.2%) | 0.071 |
| 201033019601-seat11-decision1 | 1 | 293 / 146 (49.8%) | 1,712 / 850 (49.6%) | 0.684 |
| 2010431153-seat11-decision1 | 6 | 42,504 / 4,470 (10.5%) | 249,540 / 26,784 (10.7%) | 0.122 |
| 2120531121-seat11-decision1 | 20 | 141,680 / 36,999 (26.1%) | 836,576 / 221,638 (26.5%) | 0.294 |

6 states request no path at all; for them both arms do the same work and the ratio is noise around 1.

The latency diagnostic estimated that the bounded search needs 35,920 of the
226,688 hexes the full search settles on this state (15.85%); the candidate settles
exactly that many, in the same 32 searches. Examined edges fall a little less, to 16.07%, and the median
time to 17.8%. About 4.308 ms of the decision is not search (context, candidates, gate and trace, from the
latency diagnostic's component breakdown) and is unchanged; without it the bounded search takes about
17.1% of the full search's time. The rest of the gap is consistent with work that neither count
shows: the bounded result's maps are built from the settled set, and its heap keeps entries that were pushed
but never settled. The share retained depends on how far the objectives lie from the units: on the small
control 2010131194 the candidate settles 4.6% of the hexes, on the supplementary first-play
states between 6.0% and 49.8%.

### Engine diagnostic

Three diagnostic sessions (0351 to 0353, ledger purpose `diagnostic`) from the clean checkout at
`5e9f8fe`, after the analysis script that judges them was pushed. Two reporting fields, the decisions above
100 ms and the refusal codes, were added to that script after the games (`3c33789`); its verdict rule is
unchanged. Every candidate seat carried a shadow
`baseline-v1` agent that decided on the same observation after the candidate, outside its timed window.

| Game | Configuration | Steps | Decisions compared | Different | First play: candidate / shadow (ratio) | Over 100 ms: candidate / shadow | Replay checks (mismatches) |
|---|---|---|---|---|---|---|---|
| rr-1 seat 1 | 2130511121 C1 | 2,881 | 2,881 | 0 | 174.9 / 423.1 ms (0.413) | 1 / 1 | 29 (0) |
| rr-1 seat 11 | 2130511121 C1 | 2,881 | 2,881 | 0 | 88.1 / 507.2 ms (0.174) | 0 / 2 | 29 (0) |
| rr-2 seat 11 | 2130511121 C3 | 2,881 | 2,881 | 0 | 91.0 / 523.2 ms (0.174) | 3 / 2 | 29 (0) |
| rr-3 seat 11 | 2010131194 C3 | 1,801 | 1,801 | 0 | 1.940 / 33.5 ms (0.058) | 0 / 0 | 19 (0) |

Neither arm had a project-gate rejection or a contract error in any decision. Every session closed with the engine state and its home directory unchanged and the
package integrity intact; the ledger holds 353 sessions, continuous (before: 350).

Trajectories: the first step at which a game's observed state differs from another game of the same
configuration.

| Game | First shot | From each `baseline-v1` game | Among the `baseline-v1` games |
|---|---|---|---|
| rr-1 | 101 | 102 (8 games) | 102 |
| rr-2 | 525 | 526 (11 games) | 526 |
| rr-3 | 221 | 222 (9 games) | 222, 242 |

Each diagnostic game's observed states equal those of every `baseline-v1` game of its configuration up to the
step after its first shot (steps 102, 526 and 222), which is also the first step at which the
`baseline-v1` games differ from each other: the candidate is indistinguishable from `baseline-v1` until the
engine's randomness enters.

Every other decision above 100 ms in either arm was a garbage collection inside the call:

* rr-1 seat 11, decision 250: 141.3 ms in the shadow's window;
* rr-2 seat 11, decision 1183: 644.9 ms in the candidate's window;
* rr-2 seat 11, decision 1594: 808.3 ms in the shadow's window;
* rr-2 seat 11, decision 1678: 850.1 ms in the candidate's window;
* rr-2 seat 11, decision 2172: 1,133.7 ms in the candidate's window.

A collection falls on whichever agent is running when it starts; here 3 of the 5 fell inside the candidate's
window. These are the late-game pauses that the latency diagnostic traced to the heap of the shared engine
process. This process also carried the shadow's allocations, so how often they occur here says nothing about
the candidate. The first play decisions of seat 11 fell below 100 ms; seat 1's in rr-1 still took
174.9 ms (ratio 0.413).

The engine refused 3 actions, all in rr-1 seat 11 and all of code 516 (several units firing at one target),
a known limitation of `baseline-v1`; the shadow emitted the same actions in every decision.

### Disposition

E1 to E11 all hold. The candidate is promoted as `baseline-v1-runtime-r1`, a runtime of the tactical
`baseline-v1` (`docs/BASELINE_V1_RUNTIME_R1.md`). The late-game collection pauses of the shared engine process
remain; they were out of scope.
