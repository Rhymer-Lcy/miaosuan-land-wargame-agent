# Shoot-target reservation experiment

`baseline-v2-candidate-shoot-target-reservation-ab-1` is a preregistered single-variable tactical experiment.
It tests one change to `baseline-v1`: within one seat's decision step, at most one emitted shoot action may
target the same enemy object. The question is whether this deterministic deconfliction reduces the engine
refusal class `shoot / 516 / CantShootToDiedBop` without safety regressions and without materially degrading
the outcomes the evaluation can measure. Both experimental groups run on `baseline-v1-runtime-r1`
(`docs/BASELINE_V1_RUNTIME_R1.md`), so the routing implementation cannot differ between them.

This document was committed with the registration, before the first game. The registration is
`evaluation/baseline-v2-candidate-shoot-target-reservation/manifest.json`, built by
`scripts/build_shoot_experiment_manifest.py` from `src/miaosuan_agent/evaluation/shoot_experiment.py`;
where this text and the manifest differ, the manifest governs. Results are appended under "Results".

## Identities

| Field | Value |
|---|---|
| Parent | `baseline-v1`: policy source `1d01e48a…`, golden decision chain `11e12bf0…` |
| Runtime | `baseline-v1-runtime-r1` (code identity `baseline-v1-routing-bounded-candidate`): policy source `f9e50a53…`; routing-remediation registration `ffe4539d…` |
| Candidate | `baseline-v2-candidate-shoot-target-reservation`, a provisional name. Its sources are the runtime's, byte-identical, plus `src/miaosuan_agent/experiments/shoot_reservation.py`: policy source `7cbaf032…`, golden trace chain `0d16c814…` (`tests/test_shoot_reservation.py`) |
| Group B | `baseline-v1` on `baseline-v1-runtime-r1` |
| Group C | the candidate on `baseline-v1-runtime-r1` |

The candidate is called `baseline-v2` only if every promotion criterion below passes.

## The one change

For each play-stage decision of a seat:

1. The reserved-target set starts empty.
2. Units are processed in `baseline-v1`'s ascending id order, with its hierarchy (engage, occupy, move,
   nothing) and its shoot ranking (highest attack level, then lower target id, then lower weapon id).
3. Before a unit selects, its shoot options whose `target_obj_id` is reserved are excluded. The unit then
   selects exactly as `baseline-v1` would among what remains: the next shoot option in baseline order, or,
   with none left, occupation, movement or nothing.
4. A shoot action reserves its target only when the final safety gate accepts it. A gate-rejected shot
   reserves nothing.
5. Reservations end with the step. They never cross seats and are never inferred from enemy actions.

Everything else is inherited unchanged: the tactical context, candidate generation, the same-step occupation
reservation, the target-bounded router, deployment and the safety gate. No target health, damage, kill
probability, salvo size or survival is estimated, and no scenario or map value appears in the policy.

The trace records every unit that had a shoot option excluded, with the excluded options, the unit that
reserved each target, and the effect on the unit's selection. The reason code is
`same-step-shoot-target-reserved`. The effect is one of:

* `alternate-target`: another, unreserved target was shot;
* `fallback-occupy`, `fallback-move` or `fallback-none`: no unreserved shoot option remained;
* `unchanged`: the unit's best option was not reserved.

An excluded option was legal at the start of the step. The exclusion is a coordination decision, not a
legality verdict.

## Evidence before registration

* **Public tests.** `tests/test_shoot_reservation.py` covers each registered situation, the gate, seats and
  steps, determinism and identity, and invariants on 1,500 generated situations. `tests/test_shoot_experiment.py`
  covers the registration, schedule, metrics, analyses, promotion criteria, validation and runner pins.
* **Mutation.** 17 of 17 non-equivalent mutants of the candidate were killed, and 2 equivalent mutants survived
  as argued (`mutation.json`). Every mutant of the analysis and registration code was killed
  (`mutation-analysis.json`).
* **Counterfactual replay** (`counterfactual-replay.json`, no engine). Both policies decided on the 33,802
  decisions of the private canonical corpus pinned by the routing remediation. The candidate was checked
  against an oracle that does not use its code: `baseline-v1` on the same input with the reserved targets'
  options withdrawn.
  * 33,707 decisions were identical and 95 changed.
  * `baseline-v1` emitted 105 duplicate-target shoot commands, and the candidate displaced exactly 105 units.
    79 shot another target (class A) and 26 did nothing (class D). No unit fell back to occupation (B) or
    movement (C), and no inherited occupation reservation was induced (I).
  * Unexplained deltas (class E): 0.
  * The candidate emitted no duplicate-target shot, changed no first shot of a step and changed no action
    other than those shots.

## Design

* **Population.** The eight scenarios of the frozen evaluation and variance study, unchanged: 2120531121,
  2010211129, 2010431153, 1910631192, 2010131194, 1930331196, 201033019601 and 2130511121.
  * The three conditions contain the policy: C1 mirror, C2 policy red against the inert control, and C3 policy
    blue against it. That gives 24 active configurations.
  * C4, the inert mirror, contains no decision of either policy and is not played.
* **Repetitions.** 15 per configuration and group, the variance study's default, fixed before any result.
  That is 720 new games. n is neither raised nor lowered after any result.
* **Schedule** (`schedule` in the manifest, positions 1 to 720).
  * Round r plays repetition r of every configuration in both groups.
  * Within a round, the groups alternate game by game: B first in odd rounds, C first in even rounds.
  * Each group's configurations are ordered by the SHA-256 of `<design digest>:<r>:<group>:<configuration>`.
    The design digest is the manifest's digest without the schedule.
  * One configuration and group never plays twice in a row.
  * No uncontrolled randomness is used. The groups are independent samples: the engine has no seed control,
    so games are not paired by repetition number.
* **Failure rules.**
  * A record is never overwritten, and a game that started without leaving a record stops the runner.
  * FAIL and CAPPED games are kept and reported.
  * Three consecutive games that did not complete stop the run. This is the only safety stop, and no stop is
    ever decided from outcomes.
  * A replacement needs a registered amendment and a distinct attempt identity (`.a2`), and both attempts are
    kept.
  * If execution-affecting code must change, the run stops and a new version is registered.

## Primary metric and hypothesis

* **Metric.** Code-516 refusals per 1,000 emitted unit actions. It is exactly the metric
  `code_516_per_1000` of the variance study, computed by the same code.
  * Numerator: code-516 refusals of the seats of the group's policy in the game (both seats in C1).
  * Denominator: emitted unit actions of those seats, every action type except deployment completion (333).
    A game without a unit action has no rate.
  * Weighting: the mean over games within each configuration, then the equal-weighted mean over the 24
    configurations.
* **Hypothesis** (directional). Per-seat, per-step shoot-target reservation reduces this rate relative to
  `baseline-v1` on `baseline-v1-runtime-r1`. It is not claimed that unique-target fire is tactically
  superior: removing follow-up fire can lose damage when the first shot does not destroy its target.
* **Effect grid.** Reductions of 25%, 50% and 100%; the 50% point is the practically important one.
  * In the variance study's planning at n = 15, the analytic, conservative and Monte Carlo powers were:
    * 50% reduction: 0.90, 0.60 and 0.995;
    * 100% reduction: 1.00, 0.99 and 1.00.
  * The default n = 15 itself came from the registered rule on all engine refusals (conservative power 0.90
    for halving them).
* **Analysis.**
  * Estimand: delta, the equal-weighted mean over configurations of (candidate mean minus baseline mean).
    The relative change is delta over the baseline's equal-weighted mean.
  * Interval: 95% percentile interval of a stratified bootstrap. Games are resampled within each configuration
    and group independently, with 10,000 resamples and a registered seed rule.
  * Sensitivity: the analytic interval of the planning method is reported but is not decisive.
* **P6 criterion.** The upper limit of the bootstrap interval of delta must be below 0, and the estimated
  relative reduction must be at least 25%, the smallest effect of the grid.

## Tactical non-inferiority

* **Metric.** The score margin from the active side: red minus blue in C2, blue minus red in C3. The C1 mirror
  margin measures side asymmetry and is not used.
* **Contrast.** The equal-weighted mean over the 16 C2 and C3 configurations of (candidate mean minus
  baseline mean), with the same stratified bootstrap interval.
* **P7 rule.** The lower limit of the interval must lie above −10 engine score points. The margin of 10 points
  is the smallest absolute margin effect of the variance study's planning grid, which was fixed from game
  semantics before that study's first game.

## Other registered metrics

* **Mechanism** (deterministic within a state):
  * duplicate same-target shoot commands per seat and step, counted by the harness from the emitted actions;
  * reserved-target exclusions, alternate-target redirections, and fallbacks to occupation, movement or no
    action;
  * excluded options, shots, and unique targets engaged (overall and per step with a shot);
  * code-516 refusals per 1,000 shots (secondary).

  Candidate invariant: no seat emits two shoot actions at one target in one step.
* **Refusals** (stochastic engine outcome):
  * code 516 with its step evidence (own shots at the target in that step: one, or at least two);
  * codes 203 and 404, all engine refusals, and the factual classes of taxonomy fact/1 and attribution/2.

  A code-516 refusal is attributed to repeated fire only with that evidence. Code 203 is not a target of the
  candidate.
* **Safety and regression:**
  * project-gate rejections, contract errors, replay mismatches;
  * code 1804, duplicate occupation commands;
  * games that did not complete, deployment completion;
  * new factual refusal classes, and policy and runtime digests.
* **Descriptive:** scores and margins in every condition, activity and no-op rates, action counts, and decision
  latency (p50, p95, p99, max, and decisions slower than 100 ms, 400 ms and 1 s).

## Promotion criteria

The candidate is promoted to `baseline-v2` only if all ten pass; otherwise it is retained as a partial or
negative candidate. A higher score is not required, and zero code-516 refusals is not sufficient.

| Criterion | Requirement |
|---|---|
| P1 implementation integrity | the sources are the runtime's plus exactly the one file; the pinned counterfactual replay has no unexplained state and no class-E unit |
| P2 deterministic mechanism | group C emitted no duplicate-target shot in any seat and step, and every in-game replay check of group C matched |
| P3 execution reliability | every registered game has a record; group C has no more non-completed games than group B, and no contract error |
| P4 project legality | project-gate rejections of group C: 0 |
| P5 solved-feature regression | code-1804 refusals and duplicate occupation commands of group C: 0 |
| P6 primary effect | as above |
| P7 non-inferiority | as above |
| P8 no unexplained new refusal mechanism | every factual refusal class of group C is a known `baseline-v1` class or also occurs in group B |
| P9 runtime comparability | every record carries its group's registered digest (group B the runtime-r1 digest) under this manifest, from one clean harness commit |
| P10 privacy and reproducibility | the results regenerate byte-identically, the public artifacts hold aggregates only, and the registration was on the public remote before the first game |

A promoted `baseline-v2` keeps running on `baseline-v1-runtime-r1`; the runtime is not renamed.

## Running and analysing

```bash
python scripts/build_shoot_experiment_manifest.py --check
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --evaluation baseline-v2-candidate-shoot-target-reservation --plan ab
python scripts/analyze_shoot_experiment.py
```

## Results

All 720 registered games were played at the registration commit `e7ed892`, in engine sessions
0354 to 1073, one session per game, in the registered order. Unless a source is named, every figure
below comes from `evaluation/baseline-v2-candidate-shoot-target-reservation/results.json`. `scripts/analyze_shoot_experiment.py`
derives that file from the private records, and running it again with `--check` reproduced it byte for byte.
`tests/test_shoot_results.py` recomputes its estimates, intervals, totals and criteria from the per-game values
it holds. Scores are engine value points.

How to read the figures:

* **Deterministic mechanism.** Whether a seat emits two shots at one target in one step is fixed by the rule in
  every state; the candidate's rule excludes it.
* **State-dependent counts.** Exclusions, redirections and fallbacks are deterministic for a given state, but the
  states follow stochastic engine outcomes, so these totals would differ in another run.
* **Stochastic outcomes.** Refusals and scores are engine outcomes. Repeated games of one configuration diverge
  once shots are fired (`docs/VARIANCE_STUDY.md`), so they are compared as means over 15 games per configuration.

### Execution and validation

* 720 of 720 attempts were recorded and completed: 360 per group, 15 per configuration and group. None failed,
  was capped, missing, replaced or unregistered, and none started without a record.
* The engine sessions follow the registered schedule position by position.
* Every record passed the analysis's identity checks. Group-B records carry the policy digest `f9e50a53…`
  (`baseline-v1-runtime-r1`), and group-C records the candidate's `7cbaf032…`. All carry the manifest digest
  `01c9c967…`, a clean harness at `e7ed892`, CPython 3.10.20 and engine 4.1.0.
* The engine ledger holds 1,073 sessions, continuous and all closed. The authentication state file changed
  only at its first use (session 0001), so its digest was the same in every event of this experiment.
* The registration commit was verified on the public remote at 2026-09-30T21:58:11+08:00. The host
  clock runs 387.68 s ahead (measured). Corrected for that offset, the first game started at
  2026-09-30T22:05:09+08:00, 7.0 minutes later.
* Game wall time summed to 10.09 h.

### Primary result (P6)

Code-516 refusals per 1,000 emitted unit actions, mean of configuration means:

| Level | Group B (`baseline-v1`) | Group C (candidate) |
|---|---|---|
| C1 | 9.334 | 0.810 |
| C2 | 4.233 | 0.000 |
| C3 | 3.334 | 1.092 |
| All 24 configurations | 5.634 | 0.634 |

* Raw counts: 227 code-516 refusals in group B and 16 in group C, over 23,443 and
  24,148 unit actions.
* Difference: −5.000 per 1,000; 95% stratified-bootstrap interval −6.125 to −3.937.
* Relative change: −88.7% (interval −94.1% to −81.3%).
* Analytic interval (sensitivity, not decisive): −6.147 to −3.853.
* P6 passes: the interval lies below 0, and the estimated reduction of 88.7% reaches the registered 25%.
* Secondary, per 1,000 shoot actions, over the 16 configurations where the rate is defined in both
  groups: 33.25 against 4.86.

Per configuration, code-516 refusals per 1,000 unit actions, group B / group C:

| Scenario | C1 | C2 | C3 |
|---|---|---|---|
| 2120531121 | 16.264 / 0.000 | 11.268 / 0.000 | 9.102 / 0.000 |
| 2010211129 | 12.698 / 3.030 | 20.833 / 0.000 | 0.000 / 0.000 |
| 2010431153 | 18.432 / 1.667 | 0.000 / 0.000 | 0.000 / 0.000 |
| 1910631192 | 5.048 / 0.844 | 0.000 / 0.000 | 0.000 / 0.000 |
| 2010131194 | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 |
| 1930331196 | 11.595 / 0.606 | 0.000 / 0.000 | 13.062 / 8.178 |
| 201033019601 | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 |
| 2130511121 | 10.636 / 0.333 | 1.766 / 0.000 | 4.511 / 0.560 |

10 of group C's 16 code-516 refusals occurred in scenario 1930331196, 8 of them in its C3
configuration, which keeps the highest remaining rate (8.178 against 13.062).

### Tactical non-inferiority (P7)

Score margin from the active side over the 16 C2 and C3 configurations, all played against the inert control:
282.86 for group B and 283.11 for group C.

* Difference: +0.25; 95% stratified-bootstrap interval −2.50 to +3.03; analytic interval
  −2.67 to +3.17.
* P7 passes: the registered limit is a loss of 10 points, and the interval's lower end, −2.50, lies
  above −10.
* By condition: C2 251.58 against 251.78; C3 314.13 against 314.43.
* 11 of the 16 configurations gave the same margin in all 15 games of group B, and 11 in group C.
* The result rules out, at the registered confidence, a loss of 10 points or more against the inert control. It
  does not show that the candidate plays better.

### Mechanism

| Count, summed over the group's 360 games | Group B | Group C |
|---|---|---|
| shoot actions | 8,164 | 7,735 |
| duplicate same-target shoot commands | 1,818 | 0 |
| seat-steps with a duplicate | 1,380 | 0 |
| unique targets engaged (summed over steps) | 6,346 | 7,735 |
| units whose best shoot option was on a reserved target | 0 | 1,329 |
| of these: shot another target | 0 | 840 |
| of these: occupied | 0 | 17 |
| of these: moved | 0 | 12 |
| of these: did nothing | 0 | 460 |
| units with an option excluded and the selection unchanged | 0 | 105 |
| excluded shoot options | 0 | 2,414 |

* Deterministic mechanism: group B emitted 1,818 duplicate same-target shoot commands in 1,380 seat-steps; group C
  emitted none. Group B has no reservation, so its exclusion counts are 0 by construction.
* Unique targets per step with a shot (mean of configuration means): 1.023 against 1.158.
* Code-516 evidence. Each of group B's 227 code-516 refusals came in a step in which the seat had emitted at least
  two shoot actions at the refused target. Each of group C's 16 came in a step with exactly one, so same-step
  repeated fire is excluded for all of them.
* 9 of those 16 occurred in C3, where the opponent is the inert control and never issues a unit action, so its
  fire is excluded for them too. An inspection of the private records found the target present at the start of each
  of the 16 steps and absent after it. Own fire ordered in an earlier step and resolving in this one would fit,
  but the records hold no per-step action log to establish what destroyed the target.

  > Later finding (2026-10-01; analysis only, the registered files and counts are unchanged): the registered
  > residual-516 diagnostic (`docs/RESIDUAL_516_DIAGNOSTIC.md`) captured 32 new games of 1930331196 under C3. All 12
  > residual refusals in them came in a step in which the seat's own accepted shot, earlier in the same batch,
  > destroyed the vehicle that had launched the target (an unmanned ground vehicle); the engine removed the target
  > with it, without a damage record of its own. No shot had been aimed at the target in the 30 preceding steps. The
  > refusals of this experiment in other configurations were not captured.

### Safety and regression

| Metric | Group B | Group C |
|---|---|---|
| project-gate rejections | 0 | 0 |
| contract errors | 0 | 0 |
| replay checks | 10,440 | 10,440 |
| replay mismatches | 0 | 0 |
| code 1804 | 0 | 0 |
| duplicate occupation commands | 0 | 0 |
| games not completed | 0 | 0 |
| deployment completed | 360 of 360 | 360 of 360 |
| code 203 | 40 | 63 |
| code 404 | 0 | 3 |
| all engine refusals | 267 | 82 |

Factual refusal classes:

| Action | Code | Engine message | Group B | Group C |
|---|---|---|---|---|
| shoot | 516 | `CantShootToDiedBop` | 227 | 16 |
| shoot | 203 | `CantControlDiedOperator` | 38 | 62 |
| move | 404 | `CantMoveKeptPeople` | 0 | 3 |
| occupy | 203 | `CantControlDiedOperator` | 2 | 1 |

* Attribution (`refusal-attribution/2`), group B and group C: target no longer alive at resolution 227 and 16;
  actor no longer alive at resolution 40 and 63; no attribution rule 0 and 3 (the code-404 class).
* Every factual class of group C is one of the four known `baseline-v1` classes recorded by the variance study
  (`docs/VARIANCE_STUDY.md`), so P8 passes.
* `move / 404 / CantMoveKeptPeople` occurred 3 times in group C, all in C1, and never in group B; the variance
  study had seen it once in its 240 active games. An inspection of the private records found that in each case the
  move was among the unit's legal actions at the start of the step and had passed the gate, and that the unit was
  present before and after the step. No attribution rule covers the class, and its cause was not established.
* Code 203 rose from 40 to 63, all in C1 in both groups. It is not a target of the candidate, and its rate
  contrast includes 0 (−0.42 to +3.61 per 1,000). As registered, its count is reported, not credited:
  a change arises from different engine trajectories.

### Other outcomes (descriptive)

| Metric (mean of configuration means) | Group B | Group C |
|---|---|---|
| unit actions per game | 65.1 | 67.1 |
| shoot actions per game | 22.68 | 21.49 |
| moves per game | 37.98 | 40.48 |
| occupations per game | 4.46 | 5.11 |
| active-step rate | 0.00874 | 0.00940 |
| no-op rate | 0.998025 | 0.997962 |
| all engine refusals per 1,000 unit actions | 8.982 | 5.666 |
| margin in the C1 mirror, red minus blue | −298.6 | −164.7 |

* In C1 both sides play the group's policy, so the C1 margin shows how each policy plays out the scenarios'
  asymmetry between the sides; it does not measure which policy is stronger. Its contrast is +133.97 (interval
  +65.48 to +202.88).
* Movement and occupation rose only in C1, where the summed moves went from 7,209 to 8,109 and the
  occupations from 855 to 1,089. In C2 and C3 both counts were identical in every game of a
  configuration, in both groups.

### Latency

| Group | Decisions | p50 | p95 | p99 | Max | Over 100 ms | Over 400 ms | Over 1 s |
|---|---|---|---|---|---|---|---|---|
| B | 1,010,880 | 0.395 ms | 1.143 ms | 1.200 ms | 1,304.2 ms | 152 | 38 | 8 |
| C | 1,010,880 | 0.429 ms | 1.160 ms | 1.217 ms | 1,300.3 ms | 149 | 29 | 2 |

All 10 decisions slower than 1 s occurred late in games of scenario 2130511121 C3 (decision indices 2,279 to
2,787), 8 in group B and 2 in group C; none is a first play decision. The latency diagnostic
traced such late tails to collection pauses of the shared engine process (`docs/LATENCY_DIAGNOSTIC.md`); this
experiment did not instrument them. Both groups ran on `baseline-v1-runtime-r1`, so routing was not the variable,
and nothing was optimized.

### Promotion

| Criterion | Result |
|---|---|
| P1 implementation integrity | pass |
| P2 deterministic mechanism | pass |
| P3 execution reliability | pass |
| P4 project legality | pass |
| P5 solved-feature regression | pass |
| P6 primary effect | pass |
| P7 tactical non-inferiority | pass |
| P8 no unexplained new refusal mechanism | pass |
| P9 runtime comparability | pass |
| P10 privacy and reproducibility | pass |

All ten criteria pass. The candidate is promoted as `baseline-v2` (`docs/BASELINE_V2.md`). It keeps running on
`baseline-v1-runtime-r1`, which is not renamed.
