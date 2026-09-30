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

None at registration.
