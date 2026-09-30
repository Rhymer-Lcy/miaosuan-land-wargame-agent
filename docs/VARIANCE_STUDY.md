# Variance study of baseline-v1

`baseline-v1-variance-study-1` measures how much the unchanged `baseline-v1` varies from one run of
a fixed scenario and condition to the next, how that variation differs between scenarios, whether
repetitions drift with run order, and how many repetitions future single-variable experiments need.
It changes no policy and promotes nothing: `baseline-v1` (`docs/BASELINE_V1.md`) stays the frozen
baseline. It makes no claim of tactical strength.

This document was committed with the registration, before the first new game. The results are
appended under "Results" after the study completes. The registration is
`evaluation/baseline-v1-variance-study-1/manifest.json` (canonical SHA-256
`78109fca78dc8b044b63dcf475c163ca91a6f7f60fe1454a4b126d7ada10f48e`, built by
`scripts/build_variance_study_manifest.py`); where this text and the manifest differ, the
manifest governs.

## Why

The `baseline-v1` evaluation played two repetitions of each configuration. That settles engineering
facts that do not vary: completion, gate rejections, deterministic decisions, code-1804 refusals.
The engine, however, is stochastic from the first shot on and offers no documented seed. Two
repetitions cannot estimate the spread of scores, refusal counts or activity after combat starts.

## Identity

| Field | Value |
|---|---|
| Policy | `baseline-v1` (code identity `baseline-v1-candidate-occupy-reservation`), policy source SHA-256 `1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9`, golden decision chain `11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66` |
| Scenario set | the eight scenarios of the `baseline-v1` evaluation manifest (canonical SHA-256 `38526b9250d8bce7facdb0f5c6303b5f2040e3939bd2bcedfe1fc2fdb14f103f`), copied unchanged, with the same players, caps and randomness procedure |
| Engine | SDK 4.1.0 from the persistent installation (`docs/ENGINE_INSTALL.md`) |
| Runtime | CPython 3.10.20, `miaosuan-runtime`, CPU only |

Every game recomputes the policy source digest before it touches the engine. It refuses unless the
digest equals both the registered value and the pinned `baseline-v1` digest in
`src/miaosuan_agent/evaluation/variance_study.py`, and the runner then stops the study.

## Design

* Configurations: 8 scenarios × the three conditions that contain the policy. C1 is the mirror,
  C2 the policy (red) against the inert control, C3 the inert control against the policy (blue).
  That makes 24 configurations.
* C4 (inert mirror) contains no decision of the policy and repeated exactly in the frozen
  evaluation. It is not replayed; its two historical repetitions are kept as the deterministic
  control.
* Target: 10 repetitions per configuration, fixed before the first new game.
  * Repetitions 1 and 2 are the frozen evaluation's own games (engine sessions 0090 to 0153). They
    are reused, not replaced, and pinned by the SHA-256 of each private record
    (`historical-records.json`, from `scripts/pin_study_history.py`).
  * Repetitions 3 to 10 are 192 new games, 8 per configuration.
* Run order (`schedule` in the manifest): eight rounds. Round r plays repetition r + 2 of every
  configuration once. Within a round, configurations are ordered by the SHA-256 of
  `<design digest>:<r>:<configuration>`, where the design digest is the manifest's digest without
  the schedule. A configuration never plays twice in a row across a round boundary. No
  uncontrolled randomness is used, and each configuration is spread over the whole study.
* Failure rules (`failure_rules` in the manifest):
  * a record is never overwritten, and a game that started and left no record stops the runner;
  * a game that ends FAIL or CAPPED is kept and reported;
  * three consecutive games that did not complete stop the study, and so does any other abnormal
    exit;
  * no replacement is scheduled: a replacement needs a registered amendment and a distinct attempt
    identity, and is reported beside the attempt it replaces;
  * missing games reduce their configuration's n and are reported;
  * no valid observation is excluded, however extreme.
* After registration nothing that can affect game execution changes. If it must, the study stops
  and a new version is registered; results are never merged across versions.

## Metrics

Per game, over the seats of the policy (both seats in C1):

* Outcome: `red_total`, `blue_total`, and the margin from the policy's side:
  * red minus blue in C1 (red seat) and C2;
  * blue minus red in C3.

  The engine's `red_win` and `blue_win` are checked to equal the signed margins and are not read
  as win flags.
* Refusals:
  * emitted unit actions and engine refusals, and refusals per 1,000 emitted unit actions;
  * codes 1804 (the regression metric), 516 and 203, as counts and rates;
  * counts by factual class (action type, code, engine message; `docs/REFUSAL_TAXONOMY.md`) and,
    for new games, by attribution-2 label;
  * project-gate rejections.
* Activity: moves, shots (the engagement count), occupations, active-step rate, no-op rate,
  occupation suppressions, and units that acted.
* Runtime (monotonic clock):
  * decision latency p50, p95, p99 and maximum;
  * decisions slower than 100 ms and than 400 ms;
  * total decision, engine, harness and wall time.

## Statistics

* Per configuration (n = 10):
  * mean, SD, nearest-rank median and quartiles, minimum and maximum;
  * a 95% Student-t interval for the mean. It is descriptive: n is small and outcomes need not be
    normal. A configuration whose ten values are all equal is reported as constant.
* Per condition and for the suite: equal-weighted means of configuration means. These come with:
  * the pooled within-configuration SD;
  * the between-scenario SD of configuration means;
  * a method-of-moments between-scenario variance component;
  * a 95% interval from a stratified bootstrap (10,000 resamples of games within each
    configuration; seeds registered).

  Nothing is pooled into one SD across configurations, and steps are never resampled as if they
  were games.
* Run order and exchangeability (new games only):
  * Spearman correlation of play position with the within-configuration standardized value;
  * second half (repetitions 7 to 10) minus first half (3 to 6), in within-configuration SD units;
  * the historical repetitions minus the new ones, in the same units.

  Each estimate gets a 95% stratified-bootstrap interval. A trend is material when its interval
  excludes 0 and its size reaches 0.5 SD (or |Spearman| 0.3). Short of that, the size and interval
  are reported and absence of drift is not claimed. Session continuity and the engine state file
  are checked from the session ledger.
* Two against ten repetitions: for the major metrics, the estimate from repetitions 1 and 2 against
  the estimate from all ten, the change, and the interval widths.

## Planning future experiments

Future candidate and baseline runs are independent samples: the engine has no seed control, so no
pairing by repetition number is assumed. The planned analysis is the equal-weighted difference of
configuration means, with configurations as fixed blocks.

For 2, 5, 10, 15 and 20 repetitions per configuration and arm, the study reports:
* the standard error and the minimum detectable effect at 80% power (two-sided α = 0.05);
* normal-approximation power over the effect grid;
* the same power with each configuration's SD at its 90% upper confidence bound;
* a deterministic Monte Carlo check that resamples the observed values;
* game counts and serial engine hours from the observed wall times.

It assumes a candidate has the same within-configuration SD as `baseline-v1`. A configuration
that is deterministic under `baseline-v1` then makes any shift there detectable, which holds
only if the candidate stays deterministic there too.

The effect grid was fixed from game semantics before any new game:

| Metric | Configurations | Effects |
|---|---|---|
| margin | C2, C3 (the C1 margin measures side asymmetry) | 10, 25, 50, 100 points; 2.5%, 5%, 10% of each scenario's combined start force value |
| refusals per 1,000 unit actions | C1, C2, C3 | reductions of 25%, 50%, 100% of each configuration's mean |
| code-516 refusals per 1,000 unit actions | C1, C2, C3 | reductions of 25%, 50%, 100% |
| active-step rate | C1, C2, C3 | changes of +5%, +10%, +20% |

The default repetition count recommended for the next experiment is set by a rule registered in
advance: the smallest n of the grid at which the conservative power for a 50% reduction of the
refusal rate reaches 0.8. The report states it together with the n every other cell of the grid
needs; no single n is presented as universally correct.

## Evidence

Public: the manifest, `historical-records.json`, and after completion `results.json`, which holds
aggregates and sanitized per-game metrics. Everything else stays under the git-ignored `local/`
tree: game records, per-step digests, refusal instances, logs, scenario and map data, the engine
installation and its ledger.

## Running and analysing

```bash
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --evaluation baseline-v1-variance-study-1 --plan study
python scripts/analyze_variance_study.py
```

The analysis verifies the historical record digests, every new record's identity (policy and
manifest digests, clean harness, runtime, engine state), the session ledger and completeness. It
then writes `results.json`; `--check` regenerates it and compares.

## Results

None at registration.
