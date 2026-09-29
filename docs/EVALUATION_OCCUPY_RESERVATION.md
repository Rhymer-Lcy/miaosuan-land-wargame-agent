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
pass; Gate 1 passes; the suite completes; no project-gate rejection; no duplicate same-objective
occupation emitted; no code-1804 refusal whose start-of-step context is several own occupations;
no scenario-specific identifier; determinism holds; repository checks pass). The original G4 is
reported exactly as registered and is not a promotion criterion: it is expected to keep failing,
because codes 516 and 203 are deliberately untouched. Scores are descriptive; latency is reported,
not judged.

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

None at registration.
