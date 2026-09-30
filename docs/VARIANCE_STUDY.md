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

All 192 scheduled games were played at the registration commit `cf97654`, in engine sessions 0154 to 0345, one session per game, in the registered order. Every figure below comes from `evaluation/baseline-v1-variance-study-1/results.json`. `scripts/analyze_variance_study.py` derives that file from the private records; repetitions 1 and 2 are the frozen `baseline-v1` games, checked against their pinned digests. Scores are engine value points.

### Execution and validation

* 192 of 192 games recorded and completed; none failed, was capped, missing, unregistered, started without a record, or opened a second engine session.
* Every new record carries:
  * the pinned policy digest and the registered manifest digest;
  * a clean harness at `cf97654`;
  * CPython 3.10.20 and engine 4.1.0;
  * a session that closed with the engine package intact.

  The runner recomputed the policy digest before every game and again after the last one; both times it was `baseline-v1`.
* 64 of 64 reused records match their pinned digests.
* The engine ledger holds 345 sessions, continuous and all closed. The authentication state file changed only at its first use (session 0001); its digest was the same in every event of this study.
* The new games took 2.69 h of game wall time. On the host clock, which runs about 388 s ahead, they ran from 2026-09-30T02:07:01Z to 2026-09-30T04:53:43+00:00.
* A separate standard-library script checked the same facts from the raw files, and recomputed the configuration means and SDs of the margin, the suite mean and pooled SD, and the refusal totals; it agreed on every item. Running the analysis twice gave byte-identical results.

### Determinism

* In 8 configurations no shot was fired, and all ten repetitions produced the identical engine trajectory. In the other 16, the first shot came at the same decision in every repetition and all ten trajectories differ.
* Of the 144 comparisons with repetition 1 in those configurations, 141 diverged exactly one step after the first shot. 3 diverged later: the first shots happened to resolve identically. None diverged earlier.
* Wherever two repetitions' engine states agreed, the policy's decision traces were identical.
* The C4 control (not replayed) is identical in its two historical repetitions in all 8 scenarios.

### Outcome variance

Score margin from the policy's side, by condition. The suite row weights the 24 configurations equally. The interval is the stratified bootstrap. "Between" is the between-scenario SD of configuration means; "between share" is the between-scenario share of the total variance.

| Level | Mean | 95% interval | Pooled within SD | Between SD | Between share | Constant configurations |
|---|---|---|---|---|---|---|
| C1 | -220.1 | -275.8 to -158.9 | 281.8 | 308.1 | 0.52 | 0 of 8 |
| C2 | 251.2 | 248.5 to 254.5 | 14.6 | 242.6 | 1.00 | 6 of 8 |
| C3 | 313.7 | 309.1 to 318.0 | 21.4 | 233.5 | 0.99 | 6 of 8 |
| suite | 115.0 | 96.3 to 135.3 | 163.4 | 350.2 | 0.82 | 12 of 24 |

Per configuration: mean (SD) [min, max] over ten repetitions; "constant" means all ten equal.

| Scenario | C1 (mirror, red seat) | C2 (policy red) | C3 (policy blue) |
|---|---|---|---|
| 2120531121 | -770.2 (60.0) [-851, -643] | 351.0 (40.1) [297, 437] | 589.0 (16.3) [559, 599] |
| 2010211129 | -194.4 (176.3) [-304, 296] | 264.0 constant | 128.0 constant |
| 2010431153 | -194.4 (179.6) [-310, 302] | 102.0 constant | 158.0 constant |
| 1910631192 | -155.0 (227.1) [-334, 250] | 102.0 constant | 158.0 constant |
| 2010131194 | 24.0 (123.3) [-150, 170] | 50.0 constant | 210.0 constant |
| 1930331196 | 41.4 (470.1) [-552, 702] | 274.0 constant | 570.0 constant |
| 201033019601 | 80.0 (116.6) [-140, 140] | 80.0 constant | 80.0 constant |
| 2130511121 | -592.2 (516.6) [-1,075, 427] | 787.0 (9.7) [773, 793] | 616.8 (58.2) [523, 659] |

* Against the inert control, most variation is between scenarios: between-scenario shares of 0.996 (C2) and 0.992 (C3). Twelve of those sixteen configurations are constant; the four that vary are C2 and C3 of scenarios 2120531121 and 2130511121.
* The mirror C1 varies most. Its pooled within-configuration SD (281.8) exceeds those of C2 and C3 more than tenfold, and within-configuration variance is about half of its total (between share 0.52).
* In 7 of the 8 mirror configurations the margin changed sign between repetitions. Mirror margins reflect the scenarios' asymmetric forces and objectives, since both seats run the same policy; they are not a policy effect.
* Mean engine totals in C1 are 209.45 for red and 429.55 for blue. The engine's `red_win` and `blue_win` equal the signed differences of the totals in every game, so they are margins, not win flags.

### Refusals and activity

Per 1,000 emitted unit actions, by condition (mean of configuration means, bootstrap interval, constant configurations):

| Level | All refusals | Code 516 | Code 203 |
|---|---|---|---|
| C1 | 24.41 (19.42 to 28.85; 1 constant) | 5.12 (3.64 to 6.80; 3 constant) | 19.26 (14.70 to 23.15; 3 constant) |
| C2 | 4.01 (1.93 to 6.35; 5 constant) | 4.01 (2.03 to 6.35; 5 constant) | 0.00 (0.00 to 0.00; 8 constant) |
| C3 | 2.74 (1.67 to 3.87; 5 constant) | 2.74 (1.67 to 3.87; 5 constant) | 0.00 (0.00 to 0.00; 8 constant) |
| suite | 10.39 (8.54 to 12.06; 11 constant) | 3.96 (3.02 to 4.99; 13 constant) | 6.42 (4.90 to 7.72; 19 constant) |

Factual classes over the 240 active games (repetitions 1-10):

| Action | Code | Engine message | Refusals | Configurations |
|---|---|---|---|---|
| shoot | 516 | `CantShootToDiedBop` | 119 | 11 |
| shoot | 203 | `CantControlDiedOperator` | 46 | 5 |
| move | 404 | `CantMoveKeptPeople` | 1 | 1 |
| occupy | 203 | `CantControlDiedOperator` | 1 | 1 |

* Code 1804, the regression metric, occurred in none of the 240 games.
* Code 203 occurred only in the mirror C1. The inert control never fires, and the rate is 0 in every C2 and C3 configuration.
* Code 516 occurred in all three conditions. Every code-516 refusal of the new games is labelled "target no longer alive at resolution". In each of them the private step evidence also records two to four own shots at that target within the step.
* One refusal belonged to a class not seen before: a move refused with code 404 and the message `CantMoveKeptPeople`. The unit was present before and after the step. No attribution rule covers the class, so it stays unclassified; its cause was not examined further.
* Attribution 2 applies to the 139 refusals of the new games: actor no longer alive at resolution: 37, target no longer alive at resolution: 101, unclassified: no attribution rule for this factual class: 1. The refused action matched an emitted action and was listed in the start-of-step `valid_actions` in every case; no evidence was missing or contradicted a rule.

Activity, by condition (mean of configuration means; pooled within-configuration SD; between-scenario SD):

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| unit actions | 128.3; 24.0; 152.8 | 34.6; 1.0; 40.1 | 37.3; 2.7; 42.4 |
| shots | 54.2; 14.9; 64.2 | 6.2; 1.0; 11.0 | 5.5; 2.7; 6.9 |
| moves | 65.9; 20.8; 86.5 | 25.2; 0.0; 29.1 | 28.6; 0.0; 36.2 |
| occupations | 8.2; 4.0; 9.0 | 3.1; 0.0; 2.2 | 3.1; 0.0; 2.2 |
| suppressions | 6.46; 4.70; 8.62 | 2.38; 0.00; 4.41 | 1.99; 0.11; 2.13 |
| active-step rate | 0.0138; 0.0030; 0.0121 | 0.0067; 0.0003; 0.0054 | 0.0063; 0.0008; 0.0039 |
| no-op rate | 0.99662; 0.00058; 0.00145 | 0.99865; 0.00005; 0.00053 | 0.99863; 0.00027; 0.00082 |

Moves and occupations were constant in every C2 and C3 configuration. Against the static control, the policy's movement and occupation repeat exactly, and only shooting-dependent counts vary.

### Run order and exchangeability

Standardized within configuration, new games only (historical versus new uses repetitions 1-2 against 3-10). Each cell gives the estimate [95% bootstrap interval]; constant configurations are excluded.

| Metric | Spearman with play position | Second minus first half (SD) | Historical minus new (SD) | Material |
|---|---|---|---|---|
| margin | 0.07 [-0.13, 0.26] | 0.04 [-0.31, 0.39] | 0.71 [-0.07, 2.23] | no |
| refusals per 1,000 | 0.04 [-0.15, 0.22] | 0.02 [-0.33, 0.37] | 0.01 [-0.54, 0.41] | no |
| unit actions | 0.15 [-0.03, 0.31] | 0.13 [-0.20, 0.44] | 0.86 [-0.03, 2.41] | no |
| shots | 0.19 [0.04, 0.34] | 0.27 [-0.04, 0.57] | 0.46 [-0.35, 1.64] | no |
| moves | 0.19 [-0.10, 0.47] | 0.20 [-0.35, 0.71] | 0.04 [-0.58, 1.02] | no |
| occupations | -0.08 [-0.38, 0.22] | -0.31 [-0.88, 0.22] | 0.02 [-0.51, 1.17] | no |
| latency p99 (ms) | -0.04 [-0.17, 0.10] | -0.07 [-0.30, 0.17] | -0.10 [-0.51, 1.21] | no |
| slowest decision (ms) | 0.01 [-0.11, 0.13] | -0.11 [-0.34, 0.14] | 0.30 [-0.11, 1.27] | no |
| decision time (s) | 0.03 [-0.10, 0.16] | 0.02 [-0.23, 0.26] | 0.40 [0.09, 1.35] | no |
| engine time (s) | -0.05 [-0.17, 0.06] | -0.21 [-0.45, 0.03] | 0.02 [-0.33, 0.59] | no |
| wall time (s) | 0.06 [-0.06, 0.19] | -0.02 [-0.28, 0.23] | -0.01 [-0.34, 0.97] | no |

By the registered rule, no trend is material. That does not show the absence of drift:

* The shot count rises slightly with play position (Spearman 0.19, interval 0.04 to 0.34). The interval excludes 0, but the size is below the registered 0.3. The half comparison for shots has an interval that includes 0.
* The historical repetitions differ from the new ones by at least 0.5 SD in margin and unit actions, but every such interval includes 0. With two historical repetitions per configuration, this comparison cannot establish either agreement or disagreement.
* Decision time was 0.40 SD higher in the historical repetitions (interval 0.09 to 1.35). They ran at another time, under another harness commit, on a shared host; the cause was not measured.
* The engine's state file and package were unchanged throughout, and the sessions were continuous.

Within the study (repetitions 3-10), no material run-order trend was found at the registered threshold, apart from the small shot-count association noted above. Pooling them with repetitions 1-2 rests on that plus the unchanged policy, engine and scenarios, not on a demonstrated equivalence.

### Two repetitions against ten

Equal-weighted estimates over the 24 configurations and the width of their 95% intervals. Per configuration, the table gives the median ratio of the interval widths (configurations with ten equal values are excluded) and the number of configurations whose repetitions 1 and 2 were equal although repetitions 1-10 vary.

| Metric | Repetitions 1-2 | Repetitions 1-10 | Change | Interval width (1-2 / 1-10) | Median per-configuration width ratio | Equal in 1-2, varying in 1-10 | 1-2 estimate outside the 1-10 interval |
|---|---|---|---|---|---|---|---|
| margin | 136.17 | 114.96 | 21.21 | 132.28 / 41.57 | 13.1 | 2 | 1 of 24 |
| refusals per 1,000 | 11.64 | 10.39 | 1.26 | 6.50 / 3.72 | 13.9 | 3 | 1 of 24 |
| code 516 per 1,000 | 4.37 | 3.96 | 0.42 | 6.46 / 2.08 | 15.2 | 3 | 1 of 24 |
| code 203 per 1,000 | 7.27 | 6.42 | 0.85 | 3.07 / 3.03 | 6.4 | 2 | 0 of 24 |
| active-step rate | 0.0092 | 0.0089 | 0.0002 | 0.0014 / 0.0005 | 9.8 | 2 | 4 of 24 |
| no-op rate | 0.997961 | 0.997969 | -0.000008 | 0.000264 / 0.000094 | 9.7 | 3 | 4 of 24 |
| shots | 21.00 | 21.98 | -0.98 | 4.56 / 2.23 | 9.8 | 3 | 5 of 24 |
| moves | 42.17 | 39.91 | 2.25 | 9.99 / 3.05 | 10.8 | 1 | 2 of 24 |
| occupations | 5.12 | 4.82 | 0.31 | 1.67 / 0.59 | 4.3 | 2 | 2 of 24 |
| latency p99 (ms) | 0.5328 | 0.5335 | -0.0007 | 0.0031 / 0.0023 | 7.8 | 2 | 8 of 24 |
| decision time (s) | 1.77 | 1.76 | 0.01 | 0.32 / 0.07 | 5.7 | 0 | 7 of 24 |
| wall time (s) | 50.61 | 50.41 | 0.20 | 1.32 / 0.53 | 10.2 | 0 | 7 of 24 |

Two repetitions fixed the deterministic facts: completion, gate rejections, code 1804, the configurations without a shot, and divergence only after the first shot. For stochastic quantities they are not enough:

* A per-configuration interval from two games uses t with one degree of freedom. Across these metrics its median width is 4.3 to 15.2 times the width from ten games.
* Worse, two equal repetitions can make a stochastic configuration look constant. This happened for 2 configurations of the margin and 3 of the refusal rate. "Constant in two repetitions" is therefore not evidence of determinism; only the engine-state comparison, which ties divergence to the first shot, is.
* The largest single-configuration change of the margin mean was 307.2 points (2130511121.C1). The equal-weighted margin moved by 21.2, well inside its two-repetition interval.

### Planning future experiments

Independent arms, n repetitions per configuration and arm, equal-weighted difference of configuration means, two-sided alpha 0.05. Power is given as analytic / conservative (SD at its 90% upper bound) / Monte Carlo. Games and serial engine hours are per arm over all 24 active configurations, from the observed mean wall time; a full A/B doubles them.

All engine refusals per 1,000 unit actions (24 configurations):

| n | Games per arm | Hours per arm | MDE (per 1,000), analytic / conservative | -25% | -50% | -100% |
|---|---|---|---|---|---|---|
| 2 | 48 | 0.7 | 8.37 / 12.30 | 0.14 / 0.09 / 0.25 | 0.41 / 0.22 / 0.65 | 0.94 / 0.66 / 1.00 |
| 5 | 120 | 1.7 | 5.29 / 7.78 | 0.28 / 0.15 / 0.39 | 0.78 / 0.46 / 0.92 | 1.00 / 0.96 / 1.00 |
| 10 | 240 | 3.4 | 3.74 / 5.50 | 0.49 / 0.26 / 0.60 | 0.97 / 0.75 / 1.00 | 1.00 / 1.00 / 1.00 |
| 15 | 360 | 5.0 | 3.06 / 4.49 | 0.66 / 0.37 / 0.79 | 1.00 / 0.90 / 1.00 | 1.00 / 1.00 / 1.00 |
| 20 | 480 | 6.7 | 2.65 / 3.89 | 0.78 / 0.46 / 0.90 | 1.00 / 0.96 / 1.00 | 1.00 / 1.00 / 1.00 |

Code-516 refusals per 1,000 unit actions (24 configurations):

| n | Games per arm | Hours per arm | MDE (per 1,000), analytic / conservative | -25% | -50% | -100% |
|---|---|---|---|---|---|---|
| 2 | 48 | 0.7 | 4.66 / 6.85 | 0.09 / 0.07 / 0.13 | 0.22 / 0.13 / 0.32 | 0.66 / 0.37 / 1.00 |
| 5 | 120 | 1.7 | 2.95 / 4.33 | 0.16 / 0.10 / 0.19 | 0.47 / 0.25 / 0.74 | 0.96 / 0.72 / 1.00 |
| 10 | 240 | 3.4 | 2.09 / 3.06 | 0.26 / 0.15 / 0.34 | 0.76 / 0.44 / 0.96 | 1.00 / 0.95 / 1.00 |
| 15 | 360 | 5.0 | 1.70 / 2.50 | 0.37 / 0.20 / 0.48 | 0.90 / 0.60 / 0.99 | 1.00 / 0.99 / 1.00 |
| 20 | 480 | 6.7 | 1.47 / 2.17 | 0.47 / 0.25 / 0.59 | 0.96 / 0.72 / 1.00 | 1.00 / 1.00 / 1.00 |

Active-step rate (24 configurations):

| n | Games per arm | Hours per arm | MDE (rate), analytic / conservative | +5% | +10% | +20% |
|---|---|---|---|---|---|---|
| 2 | 48 | 0.7 | 0.00103 / 0.00151 | 0.23 / 0.13 / 0.25 | 0.68 / 0.38 / 0.66 | 1.00 / 0.91 / 0.99 |
| 5 | 120 | 1.7 | 0.00065 / 0.00096 | 0.48 / 0.26 / 0.48 | 0.97 / 0.74 / 0.98 | 1.00 / 1.00 / 1.00 |
| 10 | 240 | 3.4 | 0.00046 / 0.00068 | 0.78 / 0.46 / 0.79 | 1.00 / 0.96 / 1.00 | 1.00 / 1.00 / 1.00 |
| 15 | 360 | 5.0 | 0.00038 / 0.00055 | 0.91 / 0.62 / 0.94 | 1.00 / 0.99 / 1.00 | 1.00 / 1.00 / 1.00 |
| 20 | 480 | 6.7 | 0.00033 / 0.00048 | 0.97 / 0.74 / 0.98 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

Score margin, C2 and C3 (16 configurations):

| n | Games per arm | Hours per arm | MDE (points), analytic / conservative | 10 points | 25 points | 2.5% of force value | 5.0% of force value |
|---|---|---|---|---|---|---|---|
| 2 | 48 | 0.7 | 12.81 / 18.83 | 0.59 / 0.32 / 0.62 | 1.00 / 0.96 / 1.00 | 0.67 / 0.38 / 0.68 | 1.00 / 0.91 / 1.00 |
| 5 | 120 | 1.7 | 8.10 / 11.91 | 0.93 / 0.65 / 0.95 | 1.00 / 1.00 / 1.00 | 0.97 / 0.74 / 0.98 | 1.00 / 1.00 / 1.00 |
| 10 | 240 | 3.4 | 5.73 / 8.42 | 1.00 / 0.91 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 0.96 / 1.00 | 1.00 / 1.00 / 1.00 |
| 15 | 360 | 5.0 | 4.68 / 6.88 | 1.00 / 0.98 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 0.99 / 1.00 | 1.00 / 1.00 / 1.00 |
| 20 | 480 | 6.7 | 4.05 / 5.95 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

* The registered default rule gives n = 15: the conservative power for halving the refusal rate is 0.75 at n = 10 and 0.90 at n = 15. That costs 360 games and about 5.0 serial engine hours per arm.
* The margin looks cheap to test only because 12 of its 16 configurations are constant under `baseline-v1`, leaving 4 with any variance. The table assumes a candidate keeps them constant. A candidate that changes when or whether shots are fired would make them vary, and the margin would then need more repetitions than shown.
* The Monte Carlo powers for relative rate effects exceed the analytic ones: scaling each resampled value also shrinks the candidate arm's variance, which the analytic column does not assume. The analytic and conservative columns are the planning figures. Where the Monte Carlo agrees with the analytic power, as for absolute effects and moderate n, the normal approximation is adequate.

### Latency

* Typical decisions take about a millisecond or less. Per-game p50 ranges from 0.113 to 1.171 ms and p99 from 0.162 to 1.410 ms, with within-configuration SDs of the p99 near 0.009 ms.
* The rare slow decisions recur, with the same scenario structure:
  * All 30 games with a decision slower than 400 ms are in scenario 2130511121, the largest force.
  * All 8 games whose slowest decision exceeded 1 s are its C3 configuration: 7 new and 1 historical. The slowest was 1,316.4 ms.
* Of the 224 decisions slower than 100 ms, 130 were decision 1, the first decision of the play stage; the rest are scattered over later steps. The cause was not measured, and nothing was optimized.

### Limitations

* The engine has no documented seed. Its stochasticity is observed only after the first shot, so conclusions about variance hold for this engine build and these eight scenarios.
* Repetitions 1-2 come from another harness commit and another time. Their equivalence with repetitions 3-10 is plausible but, with two per configuration, not demonstrated.
* The planning tables assume a candidate with `baseline-v1`'s within-configuration SDs and use a normal approximation. Ten repetitions estimate each SD only roughly; the conservative column bounds that uncertainty at 90%.
* The latency figures come from a shared host.
