# Candidate experiment: occupation reservation

This document registers a single-variable experiment on top of the frozen `baseline-v0`
(`docs/BASELINE.md`, `docs/EVALUATION.md`). It was committed, together with its manifest
`evaluation/baseline-v1-candidate-occupy-reservation/manifest.json`, and pushed before the first
engine session of the candidate. The manifest carries no timestamp; the commit is the registration
record. Results are appended below the protocol, never mixed into it.

## 1. The single variable

`baseline-v1-candidate-occupy-reservation` is `baseline-v0` plus one rule: **within one decision
step, at most one occupation command is issued per objective.**

* Units are processed in `baseline-v0` order (ascending unit id), with `baseline-v0`'s per-unit
  priority (engage, occupy, move).
* The first unit that selects occupation of an objective keeps it; the objective is reserved for
  the rest of the step. The key is the hex the occupying unit stands on, which is the objective's
  `coord`, the identity `baseline-v0` already uses.
* A later unit that would select occupation of a reserved objective is suppressed and continues
  down the unchanged hierarchy. `baseline-v0` forbids moving away from an unheld objective the unit
  stands on, so in practice the unit does nothing that step.
* Each suppression is recorded in the decision trace (field `suppressed`, reason code
  `same-step-objective-reserved`). It is a project-side coordination decision, not a legality
  verdict: the suppressed occupation was legal at the start of the step.
* The reservation lives for one decision step. No state is carried between steps.

Everything else is `baseline-v0`, reused by import: tactical context, candidate generation,
rankings and tie-breaks, shooting (several units may still fire at one target), movement and
routing, deployment and the final safety gate. The candidate lives in
`src/miaosuan_agent/experiments/`, outside the files covered by `baseline-v0`'s source digest, so
`baseline-v0` stays executable and verifiable under its original identity.

## 2. Hypothesis and acceptance

Hypothesis, as registered: per-objective, per-step occupation reservation eliminates engine
refusal code 1804 attributable to duplicate friendly occupation commands, without introducing a
project-gate rejection or changing unrelated baseline decision behaviour. No score or win-rate
hypothesis is registered.

The candidate is promoted to `baseline-v1` only if all of A1 to A11 in the manifest hold (the
`baseline-v0` identity still verifies; the counterfactual replay shows no unexplained delta; tests
pass; Gate 1 passes its runtime criteria (amendment 1); the suite completes; no project-gate rejection; no duplicate same-objective
occupation emitted; no code-1804 refusal whose start-of-step context is several own occupations;
no scenario-specific identifier; determinism holds; repository checks pass). The original G4 is
reported exactly as registered and is not a promotion criterion: it is expected to keep failing,
because codes 516 and 203 are deliberately untouched. Scores are descriptive; latency is reported,
not judged.

## Amendment 1 (before any suite game)

The first registration (commit `0b4c2cd`, manifest `aff71d57…`) copied `baseline-v0`'s Gate 1
rule, "G1 to G6 all pass", into criterion A4. That contradicted its own statement that G4 is no
criterion and is expected to fail, since codes 516 and 203 are untouched, and the experiment's
specification, which defines Gate 1 as a runtime sanity check. Gate 1 under that registration
(engine sessions 0086 and 0087) recorded one engine refusal, code 203 on a shot, failing G4. G1,
G2, G3, G5 and G6 passed and no project-gate rejection occurred. The wrapper therefore refused to
start the suite, as registered. The amendment changes only the Gate 1 rule and A4: Gate 1 now
requires G1, G2, G3, G5 and G6 for both games and zero project-gate rejections, and G4 is reported.
The candidate's policy source is unchanged. The first Gate 1 attempt is kept and reported but not
reused: Gate 1 is played again under the amended registration, before the suite.

## 3. Counterfactual replay before registration

Before registration, both policies decided on identical recorded start-of-step inputs. The inputs
are every decision of eight `baseline-v0` baseline-mirror games (the C1 configuration of each
registered scenario), recorded from the real engine, plus the private contract fixtures.
`baseline-v0` first had to reproduce every recorded decision exactly. Each state was then
compared through an oracle that does not use the candidate's code. With no duplicate occupier,
the candidate must equal `baseline-v0`. With duplicate occupiers, it must suppress exactly those
units and must equal `baseline-v0` run with occupation withdrawn from exactly those units' legal
actions. Result: `baseline-v0` reproduced all 33,696 recorded decisions exactly. Of 33,702 decision states, 33,667 were identical and 35 differed; every difference was explained by the registered rule: 55 duplicate occupation commands of `baseline-v0` were suppressed in 35 states, and the only `baseline-v0` action type that changed was occupation. Unexplained deltas: 0. The aggregate is `evaluation/baseline-v1-candidate-occupy-reservation/counterfactual-replay.json`; the corpus stays private.

## 4. Design

Identical to the `baseline-v0` suite, with the candidate in place of `baseline-v0` wherever the
policy under test plays: the same eight scenarios and selection rule (copied unchanged into the
manifest), conditions C1 (candidate mirror), C2 and C3 (candidate against the inert control, each
side), C4 (inert mirror), two repetitions, the same order, players, caps, isolation, randomness
procedure and Gate 1 scenario. G1 to G6 keep their definitions, with "baseline seats" read as the
seats of the policy under test.

## 5. Metrics and refusal decomposition

All `baseline-v0` metrics are kept. Added:

* primary: code-1804 refusals by start-of-step context; occupations suppressed by the
  reservation and steps with a suppression; duplicate same-objective occupation commands emitted,
  counted by the harness from the emitted actions (not from the policy's own trace); project-gate
  rejections; engine refusals; G4 as registered;
* secondary: active-step rate, no-op rate, total decision time, in addition to the `baseline-v0`
  reliability, activity and latency metrics.

The refusal decomposition is supplementary to G4 and does not replace it. It reports project-gate
rejections, engine refusals (all of them refusals of actions the gate accepted at decision time),
refusals by code, by evidence-backed code category (1804, 516 and 203 from the `baseline-v0`
diagnostics; any other code stays unclassified), and by start-of-step context class recorded for
every refusal: for an occupation, the objective's flag and the number of own occupations of it in
that step; for a shot, whether target and shooter were present at step start and how many own shots
went at that target. A refusal that matches no class is reported as unexplained.

## 6. Artifacts

| Artifact | Where | Public |
|---|---|---|
| Manifest (the registration) | `evaluation/baseline-v1-candidate-occupy-reservation/manifest.json` | yes |
| Counterfactual replay aggregate | `evaluation/baseline-v1-candidate-occupy-reservation/counterfactual-replay.json` | yes |
| Sanitized results | `evaluation/baseline-v1-candidate-occupy-reservation/results.json` | yes, after the run |
| Replay corpus, game records, traces | `local/` | no (git-ignored) |

## 7. Reproducing

```bash
python scripts/build_candidate_manifest.py --check
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --evaluation baseline-v1-candidate-occupy-reservation --plan gate1
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --evaluation baseline-v1-candidate-occupy-reservation --plan suite
```

## Results

Gate 1 and the suite were played on 2026-09-30 (UTC+8) on the Linux host of the persistent engine installation, harness commit `1376ca6`, one recorded engine session per game. Every figure below is computed from `evaluation/baseline-v1-candidate-occupy-reservation/results.json` (and, for the first Gate 1 attempt, `results-gate1-attempt-1.json`); the `baseline-v0` figures come from `evaluation/baseline-v0/results.json`.

### Gate 1

* First attempt, under the first registration (manifest `aff71d57…`, sessions 0086 and 0087): G1 pass, G2 pass, G3 pass, G4 FAIL, G5 pass, G6 pass; engine refusals: 1 of code 203, project-gate rejections 0. Kept and reported, not reused (amendment 1).
* Under amendment 1 (manifest `38526b92…`): G1 pass, G2 pass, G3 pass, G4 FAIL, G5 pass, G6 pass; engine refusals: 1 of code 203, project-gate rejections 0; the required criteria (G1, G2, G3, G5, G6) passed, so the suite started.

### Suite

64 of 64 games reached the engine's done flag; none failed or hit a cap. Criteria per configuration (pass / fail / not applicable):

| Criterion | baseline-v0 | candidate |
|---|---|---|
| G1 | 32 / 0 / 0 | 32 / 0 / 0 |
| G2 | 32 / 0 / 0 | 32 / 0 / 0 |
| G3 | 24 / 0 / 8 | 24 / 0 / 8 |
| G4 | 10 / 14 / 8 | 12 / 12 / 8 |
| G5 | 24 / 0 / 8 | 24 / 0 / 8 |
| G6 | 32 / 0 / 0 | 32 / 0 / 0 |

The candidate emitted no duplicate same-objective occupation command (harness count over Gate 1 and the suite: 0). The reservation suppressed 188 occupations in 131 steps; every suppressed unit then did nothing that step (188 no-op unit-steps carry the suppression reason). No code-1804 refusal occurred. The engine refused 28 of the candidate's 3,278 unit actions, all shots or occupations whose unit or target was lost earlier in the same step:

| Refusal (code / action / start-of-step context) | Count |
|---|---|
| 203/2/same-step: shooter present at step start | 9 |
| 203/5/unclassified | 1 |
| 516/2/same-step: target fired at more than once by own side | 18 |

One code-203 refusal was on an occupation, not a shot (engine message `CantControlDiedOperator`: the occupying unit, which the policy only orders when it is on the map at the start of the step, was destroyed during the step). The registered instance classifier defines 203 for shots only and left it unclassified, as reported above; the code-level category of the taxonomy, whose evidence came from shots, calls every 203 "shooter destroyed" and so mislabels this one occurrence.

### Direct comparison with baseline-v0

Suite games only, seats of the policy under test. **D** marks a deterministic property of the policy; **S** marks a count that also depends on the stochastic engine trajectory (the two suites diverged after their first shots), so its difference is descriptive.

| Metric | baseline-v0 | candidate | Kind |
|---|---|---|---|
| Games completed | 64 / 64 | 64 / 64 | D |
| Project-gate rejections | 0 | 0 | D |
| Duplicate same-objective occupations emitted | not counted by its harness (counterfactual corpus: 55 in the 8 recorded C1 games) | 0 | D |
| Occupations suppressed by the reservation | none (no reservation) | 188 in 131 steps | S |
| Code 1804 refusals | 157 | 0 | S (0 with a duplicate context is D) |
| Code 516 refusals | 23 | 18 | S |
| Code 203 refusals | 7 | 10 | S |
| Total engine refusals | 187 | 28 | S |
| Occupation actions emitted | 378 | 246 | S |
| Active-step rate | 0.0122 | 0.0127 | S |
| No-op rate (no-op unit-steps / all unit-steps) | 0.9983 | 0.9983 | S |
| G4 failures | 14 of 24 | 12 of 24 | S |

Decision latency in milliseconds, by condition (nearest rank; **S**, and measured on a shared host):

| Condition | baseline-v0 p50 / p95 / p99 / max | candidate p50 / p95 / p99 / max |
|---|---|---|
| C1 | 0.303 / 0.912 / 1.182 / 507.089 | 0.318 / 0.906 / 1.2 / 524.579 |
| C2 | 0.599 / 1.019 / 1.162 / 424.725 | 0.612 / 1.022 / 1.168 / 421.882 |
| C3 | 0.701 / 1.175 / 1.205 / 1304.309 | 0.714 / 1.172 / 1.215 / 1103.604 |

The p50, p95 and p99 of the two policies differ by at most 0.018 ms in any condition. Both show rare slow decisions between 0.4 and 1.3 s; their cause was not measured and is listed as a limitation in `docs/BASELINE_V1.md`. No material latency difference was observed.

### Determinism

Decision traces were identical at every step at which the engine states of two repetitions agreed (G5 passed in 24 of 24 applicable configurations), and all 1,436 in-game replay checks matched. As for baseline-v0, the engine repeated exactly in all 16 configurations without a shot and diverged in all 16 with one, each time exactly one step after the first shot.

### Outcomes (descriptive)

Against the inert control the candidate side's engine total was higher in 32 of 32 games. Per-game scores are in the results file. As registered, no claim of tactical strength is made.

### Acceptance

* A1: **pass**. baseline-v0 still verifies: its policy source digest, golden decision chain, manifest re-derivation, and byte-identical regeneration of its committed results from its game records
* A2: **pass**. counterfactual replay of recorded real start-of-step inputs shows zero unexplained deltas (pinned below; run before registration)
* A3: **pass**. the public and private tests pass on both machines
* A4: **pass**. Gate 1 passes its runtime criteria: G1, G2, G3, G5 and G6 for its two games, with zero project-gate rejections; G4 is reported (amendment 1)
* A5: **pass**. the suite completes: every registered game reaches the engine's done flag
* A6: **pass**. project-gate rejections of the policy under test: 0 over Gate 1 and the suite
* A7: **pass**. duplicate same-objective occupation commands emitted by the policy under test, counted by the harness from the emitted actions: 0
* A8: **pass**. engine refusals 1804 whose start-of-step context is several own occupations of the objective: 0
* A9: **pass**. no scenario, map or terrain identifier in the candidate's policy sources
* A10: **pass**. determinism: G5 passes in every applicable configuration and every in-game replay check matches
* A11: **pass**. repository and privacy checks pass

### Disposition

**PROMOTED AS baseline-v1.** All eleven registered acceptance criteria hold (A1, A3 and A11 were verified on the
final repository state on both machines). The promotion changes no code: `baseline-v1` is the name given to the
executed candidate, whose identity string in the code and in every trace remains
`baseline-v1-candidate-occupy-reservation`, so every result stays attributed to the policy source digest that was
actually run. The identity record is `docs/BASELINE_V1.md`; `baseline-v0` is preserved unchanged
(`docs/BASELINE.md`).
