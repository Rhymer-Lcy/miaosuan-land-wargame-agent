# Decision-latency diagnostic of baseline-v1

This records an engineering diagnostic of the rare decision-latency tail of the frozen `baseline-v1`
(policy source `1d01e48a…`). It changed no policy, routing, ordering or runtime setting, and nothing
was optimized; every measurement came from external instrumentation
(`src/miaosuan_agent/diagnostics/`) or from replaying recorded inputs. The evidence, in order:

1. The 256 game records of the variance study (`scripts/latency_from_records.py`,
   aggregate `evaluation/latency-diagnostic-1/record-tail.json`).
2. An offline replay without the engine of the 8 recorded games of the replay corpus, and a
   benchmark of selected recorded inputs (`scripts/replay_latency_benchmark.py`).
3. 5 instrumented diagnostic games on the real engine (`evaluation/latency-diagnostic-1/plan.json`, pushed
   before they ran; engine sessions 0346 to 0350, ledger purpose `diagnostic`), played by the
   unchanged harness with each agent wrapped by the probe (`scripts/run_latency_diagnostic.sh`).

The public figures are in `evaluation/latency-diagnostic-1/findings.json` (`scripts/analyze_latency_diagnostic.py`).
Observations, unit identifiers and traces stay under the git-ignored `local/` tree.

## 1. The tail in the recorded games

673,920 decisions of the policy (and 404,352 of the inert control) in 256 games. Median 0.368 ms, p99 1.195 ms, slowest 1,316.4 ms.

| Threshold | Decisions | Games | First play decision | Other decisions |
|---|---|---|---|---|
| > 10ms | 1,119 | 210 | 280 | 839 |
| > 50ms | 336 | 180 | 240 | 96 |
| > 100ms | 224 | 130 | 160 | 64 |
| > 250ms | 118 | 70 | 80 | 38 |
| > 400ms | 69 | 30 | 40 | 29 |
| > 1000ms | 10 | 8 | 0 | 10 |

* Every decision above 400 ms is in scenario 2130511121 (the largest force): 20 in C1, 10 in C2 and 39 in C3. All 10 decisions above 1 s are in its C3 configuration, in 8 games, and none is a first play decision.
* 160 of the 224 decisions above 100 ms are the first decision of the play stage (decision 1), in every repetition of the configurations concerned. The variance-study report counted 130: that was the number of games with a slow decision 1, because its per-game index set merged the two seats of the C1 mirror. Measured in decisions, the figure is 160.
* Deployment decisions never exceeded 1.025 ms.
* In 2130511121.C3 the median stays between 1.132 and 1.175 ms over the whole game. The largest decision per 250-step window, however, grows from 243.6 ms to 1,316.4 ms towards the end.
* The inert control, whose decisions do almost nothing, had 13 decisions above 100 ms, all in 2130511121.C2 (slowest 233.3 ms).

## 2. Two mechanisms

### First play decision: route planning (policy computation)

At decision 1 every unit that can move plans a route at once, while the routing memo is still empty. For the blue side of 2130511121 that is 32 shortest-path requests from 32 distinct start hexes (44 units). Each Dijkstra run settles the whole map, 7,084 nodes (about 41,830 directed edges in the infantry, vehicle and air modes), although only the objective hexes are read.
Offline, with no engine, that input takes 502.7 ms (median of 200 calls). Dijkstra accounts for 99.1% of it, the thread CPU time equals the wall time, and in-decision collection is below 1 ms. It is the same input as decision 1 of every historical game of that scenario: the engine state after step 1 has the same digest in all conditions and repetitions.
From decision 2 on the units are already moving, and the decision takes about a millisecond again.

### Late slow decisions: full garbage collections (runtime)

In the diagnostic games of 2130511121.C3, every slow decision after the first came from one collection of the oldest generation:

| Game | Decision | Wall | Thread CPU | Full collection inside it | Involuntary switches |
|---|---|---|---|---|---|
| latdiag-1 | 211 | 120.5 ms | 120.5 ms | 119.0 ms | 0 |
| latdiag-1 | 1177 | 588.6 ms | 588.6 ms | 587.0 ms | 1 |
| latdiag-1 | 2163 | 1,064.3 ms | 1,064.3 ms | 1,062.6 ms | 3 |
| latdiag-1 | 2714 | 1,333.1 ms | 1,332.9 ms | 1,331.4 ms | 8 |
| latdiag-2 | 211 | 115.6 ms | 115.6 ms | 114.1 ms | 1 |
| latdiag-2 | 790 | 384.9 ms | 384.8 ms | 383.4 ms | 4 |
| latdiag-2 | 1205 | 614.8 ms | 614.8 ms | 613.1 ms | 1 |
| latdiag-2 | 2084 | 971.8 ms | 971.8 ms | 970.1 ms | 1 |

* The process ran 115 full collections in latdiag-1; they lengthened from 21.2 ms to 1,454.5 ms. Only 5 fell inside a decision of either seat; the rest fell in the engine step or the harness.
* The collections lengthen because the heap grows. Python-tracked objects rose from 154,463 at decision 0 to 3,408,490 at decision 2500, about 1,302 per step; in the small scenario 2010131194, about 55 per step.
* Replayed offline, the policy and the boundary keep the process heap flat: 86,140 to 91,911 tracked objects over the whole game. The 7 full collections that landed inside decisions took 8.3 to 9.6 ms. Per step the harness appends only integers and strings, which the collector does not track, plus an occasional refusal record. The growth therefore comes from the engine running in the same process. This is an inference from these three facts; no census of object types was taken.
* The exact inputs of those slow decisions, captured in latdiag-1 and replayed offline, take 1.22 to 1.33 ms (median), and 1.46 to 1.63 ms as the first call of a fresh interpreter. In the engine they took 120.5 to 1,333.1 ms.
* A collection slows whichever agent it lands in. In 2130511121.C2, the 3 inert-seat decisions above 100 ms were full collections as well.
* The labelled comparison latdiag-5 paused collection for the duration of each agent step only. It left one decision above 100 ms, decision 1. The process still ran 112 full collections (up to 1,337.3 ms), all between decisions. Its decision traces equal latdiag-1's at every step until the engine states diverged, at step 526, one step after the first shot.

## 3. Offline benchmark of recorded inputs

Each input was called as the first call of a fresh interpreter (10 times), then 200 times with a new agent each (empty routing memo, unprobed), and 200 times on one agent (memo warm). The decision trace equalled the recorded one in every call.

| Input | In-engine wall | Cold first call | Fresh agent p50 / p95 / p99 / max | Memo warm p50 |
|---|---|---|---|---|
| 2010131194-decision1 | n/a (corpus) | 33.337 ms | 32.276 / 32.738 / 33.341 / 35.025 ms | 0.196 ms |
| 2010131194-decision900 | n/a (corpus) | 0.274 ms | 0.231 / 0.241 / 0.266 / 0.395 ms | 0.129 ms |
| 2130511121-decision1 | n/a (corpus) | 493.778 ms | 502.719 / 519.004 / 528.348 / 532.297 ms | 2.732 ms |
| 2130511121-decision1000 | n/a (corpus) | 1.137 ms | 0.990 / 1.012 / 1.026 / 1.270 ms | 0.842 ms |
| 2130511121-decision1-latdiag-1 | 511.8 ms | 509.524 ms | 492.805 / 510.642 / 516.850 / 522.578 ms | 2.734 ms |
| 2130511121-decision211-latdiag-1 | 120.5 ms | 1.629 ms | 1.215 / 1.242 / 1.307 / 1.847 ms | 1.063 ms |
| 2130511121-decision1177-latdiag-1 | 588.6 ms | 1.457 ms | 1.300 / 1.496 / 3.389 / 12.489 ms | 1.160 ms |
| 2130511121-decision2163-latdiag-1 | 1,064.3 ms | 1.560 ms | 1.329 / 1.521 / 1.629 / 13.111 ms | 1.170 ms |
| 2130511121-decision2714-latdiag-1 | 1,333.1 ms | 1.465 ms | 1.333 / 1.527 / 1.733 / 13.272 ms | 1.165 ms |

A fresh interpreter costs nothing measurable beyond the decision itself: the first call of decision 1 took 493.8 ms against a warm median of 502.7 ms. So no lazy import, bytecode or allocator warm-up is involved. The occasional maximum near 13 ms among the fast inputs coincides with an offline full collection (up to 13.6 ms).

## 4. Components and workload

Share of offline decision time by component, over all 33,696 replayed decisions and over those above 100 ms. Routing is Dijkstra plus the memo lookup. Trace construction is included; its hashing is not, since the harness hashes after the timed call:

| Component | All decisions | Above 100 ms |
|---|---|---|
| context | 44.3% | 0.2% |
| other | 28.7% | 0.2% |
| dijkstra | 17.1% | 99.0% |
| trace | 2.4% | 0.0% |
| engage | 2.1% | 0.0% |
| move_candidates | 2.0% | 0.3% |
| boundary | 1.5% | 0.0% |
| occupy | 1.4% | 0.0% |
| gate | 0.5% | 0.2% |
| routing_lookup | 0.0% | 0.0% |
| ranking | 0.0% | 0.0% |

The probe's own cost, measured as probed minus unprobed median on the same input, ranged from -2.691 to 0.306 ms: below 0.5 ms, or below 1% of the decision where that is larger (the largest, 2.7 ms, on a 493 ms decision). In the engine games, recording each decision (trace digest, compressed write) added 0.150 to 0.555 ms per decision outside the probe window. Labelled time plus unattributed time equals the probe's wall time for every decision.

Rank correlation of offline decision time with workload (Spearman): with the number of units 0.98; with total candidates 0.15; with routing requests 0.10; with Dijkstra runs 0.07. The ordinary decision scales with the units in the tactical context. Routing is rare: 509 shortest-path requests in 33,696 replayed decisions. When it occurs it dominates: it is 99.0% of the time of decisions above 100 ms. Correlation is not causation; the component timings, not the correlations, attribute the time.

Routing over the offline replay: 509 shortest-path requests, 213 Dijkstra runs and 296 memo hits. No routing was done for a unit that then did not move (units routed but not moving: 0). The implementation is a binary-heap Dijkstra over the whole map, O((V + E) log V) for each run, with one run for each distinct start hex and mode that the 32-entry memo does not already hold.
On the first play input of 2130511121, the last of the 7 objective hexes is settled after 35,920 of the 226,688 settled nodes (15.8%). In 2010131194 it is 4.6% (`diagnostics/routing_estimate.py`). This estimates the work a search needs to reach the objectives; no such search was implemented.

## 5. Runtime and scheduling

* All 15 decisions above 100 ms in the diagnostic games used thread CPU time equal to their wall time (ratio 0.9998 to 1.0001), with 0 to 8 involuntary context switches and no major page fault. A preempted thread would show CPU time far below wall time; none did.
* The host's one-minute load average stayed between 0.73 and 1.18 during the games.
* The historical records hold wall time only, so their outliers cannot be classified individually. What they show matches what the diagnostic games measured: decision 1 in every repetition of the affected configurations, late spikes growing with game time in one configuration, and spikes in the inert seat.

## 6. Classification

**Mixed**, of two measured and independent causes. Scheduling was not observed to contribute:

* **Route planning at the first play decision (policy computation).** It accounts for 160 of the 224 decisions above 100 ms (71.4%) and for 40 of the 69 above 400 ms; the slowest was 524.6 ms. It recurs in every repetition of those configurations, reproduces offline within a few percent, is CPU-bound, and grows with the number of distinct unit start hexes times the size of the map.
* **Full garbage collections (runtime).** They produced all decisions above 1 s and the remaining slow decisions late in a game: 11 of 11 in the diagnostic games. The pause grows with the process heap, which the engine enlarges in this harness; the policy's own work on those inputs is about a millisecond.

## 7. Operational significance and the remediation decision

The platform runs on an asynchronous, accelerated clock and publishes no per-step deadline, so none is assumed here.

* The first play decision is the agent's own computation and would occur on the platform too, scaled by its CPU. On the
  largest registered scenario it costs about 0.5 s. A platform scenario with
  more units or a larger map would cost proportionally more, and second-scale intrinsic computation cannot be excluded
  for such scenarios.
* The second-scale collections depend on what else lives in the agent's process. Here the engine does, and grows the
  heap by about 1,300 objects per step in the largest scenario. Whether the online agent shares a process with the engine is not known, so
  the online relevance of these pauses is uncertain. In this local harness the engine waits for the agent, so latency
  cannot change any evaluation outcome.

Decision rule, stated in this document after the measurements (no deadline existed to fix one in advance): remediation
precedes the next tactical experiment if some part of the tail
(1) is the policy's own computation (CPU-bound and reproduced offline without the engine), (2) reaches at least 100 ms in a
registered scenario, and (3) grows with scenario size. 100 ms is the threshold the variance study already treated as an
outlier; it is not a deadline. The first-play route planning meets all three conditions. The collections do not meet (1).

**REMEDIATE BEFORE NEXT TACTICAL EXPERIMENT**, limited to the route planning. A behaviour-preserving change there alters
the policy source digest (the router lives in `decision/`). Doing it first gives the next tactical candidate a single
lineage and keeps its latency measurements free of this known spike.

## 8. Candidate remediation, not implemented

1. **Target-bounded search.** Stop each Dijkstra run once every current objective hex is settled, and keep the objective
   set in the memo key; objectives can be recaptured, so a truncated result must not serve a larger set. The estimated work
   is 15.8% of today's on the worst input. It affects routing only. Paths and costs to the objectives
   cannot change: a settled node's cost and predecessor are final, and predecessors change only on a strictly lower cost.
   The source identity changes.
2. **Route precomputation at setup.** Run the first-play searches from the units' initial hexes in `setup`, which receives
   the initial state, and give the memo room for every distinct start. The results are the same objects, computed earlier,
   so the work moves out of the play stage without being removed. It depends on a setup budget that is not published either.
   The source identity changes.
3. **Dijkstra loop tuning** (local bindings, plain adjacency lookups instead of per-call read-only views). The semantics are
   identical, the gain is unmeasured, and the source identity changes.
4. **Runtime collection control** (for example freezing setup-time objects, or collecting at controlled points). This is a
   harness or deployment setting, not a policy change, and matters only where the agent shares a process with a growing
   heap. The platform's process layout would have to be established first.

Equivalence proof for 1 to 3, before any tactical work resumes:
* the golden decision chain is unchanged;
* every recorded input replays with identical traces and actions: the replay corpus, the captured states, and the
  counterfactual replay;
* latency is re-measured on the captured first-play inputs.

The change is registered as its own behaviour-preserving identity, and `baseline-v1` stays frozen.

## Reproducing

```bash
python scripts/latency_from_records.py
python scripts/replay_latency_benchmark.py sequence --out local/diagnostics/latency/offline-sequence.jsonl.gz
python scripts/replay_latency_benchmark.py extract --out-dir local/diagnostics/latency/states
python scripts/replay_latency_benchmark.py states --states local/diagnostics/latency/states --out local/diagnostics/latency/offline-states.json
python scripts/replay_latency_benchmark.py bound --states local/diagnostics/latency/states --out local/diagnostics/latency/offline-bound.json
bash scripts/run_latency_diagnostic.sh --python PYTHON
python scripts/replay_latency_benchmark.py import-captures --game latdiag-1 --out-dir local/diagnostics/latency/states-engine
python scripts/replay_latency_benchmark.py states --states local/diagnostics/latency/states-engine --out local/diagnostics/latency/offline-states-engine.json
python scripts/analyze_latency_diagnostic.py
```
