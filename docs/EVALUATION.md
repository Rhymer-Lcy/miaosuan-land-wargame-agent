# Evaluation protocol: baseline-v0

This document registers how the baseline policy `baseline-v0` is evaluated. It was committed,
together with the manifest `evaluation/baseline-v0/manifest.json`, before any game with the
baseline policy was played on the real engine. The commit that adds them is the registration
record; the manifest deliberately contains no timestamp. Results are appended below the protocol,
never mixed into it.

The goal is a baseline that is **legal, deterministic, active and measurable**, in that order.
Winning is not a goal: nothing in the policy was, or may be, tuned on outcomes.

## 1. Policies

| Identity | Behaviour |
|---|---|
| `baseline-v0` | Deployment stage: end deployment once. Play stage: for each controllable unit, in ascending unit id, at most one action from the first category that has a candidate: engage (the listed shoot option with the highest attack level of at least 1; ties by lower target id, then lower weapon id), occupy (when listed), move (to the unheld objective with the lowest path cost; ties by lower hex; roadblocks avoided for vehicles; never while a move is executing, never away from an unheld objective the unit stands on). Otherwise nothing, with the reason traced. |
| `inert-v0` | Ends deployment the same way (the game cannot start otherwise) and never issues a unit action. It is the control. |

Every action passes the final safety gate (`src/miaosuan_agent/decision/gate.py`) before it
leaves the agent. The policy identity is pinned three ways: the identity string, a golden
decision test (`tests/test_decision_determinism.py`), and the SHA-256 of the policy source
recorded in the manifest (`policy_source`: the agent wrapper, the boundary and the decision
package, line endings normalized). `tests/test_evaluation_registration.py` fails if that source
changes, and `scripts/run_evaluation.py` refuses to play a game with a different source.

## 2. Scenario selection

The rule was fixed before any baseline game and is implemented by
`src/miaosuan_agent/evaluation/selection.py`. The pool is the 50 scenarios shipped with the SDK.

Eligibility; a failure makes the scenario/map pairing or its inputs objectively invalid:

* **E1** the scenario id names a supplied map (the last four digits when they are 9601, otherwise
  the last two);
* **E2** every operator and objective hex lies inside that map;
* **E3** every operator starting on the map (not on board) with a documented movement mode
  (unit types 1 to 3) has at least one traversable neighbour for that mode at its start hex;
* **E4** on a map whose cells carry roadblock flags, the scenario's roadblocks are exactly those cells.

Selection:

* **S1** strata are the maps of the eligible scenarios;
* **S2** from each stratum, the scenario with the fewest operators; ties by smaller `max_time`,
  then smaller numeric id;
* **S3** in addition, the eligible scenario with the most operators overall (ties by smaller
  numeric id), or the next in that order if S2 already picked it;
* **R** replacement only after a documented objective failure (the engine raises during setup,
  before any decision): the next listed alternate of the same pick.

Outcome of the rule: 40 of 50 scenarios are eligible (the other 10 fail E1, as recorded in
`docs/COMPATIBILITY.md` 3.5), spread over 7 maps. The registered scenarios:

| Scenario | Map | Operators (red / blue) | Objectives | `max_time` | Rule |
|---|---|---|---|---|---|
| 2120531121 | 21 | 54 (28 / 26) | 5 | 2880 | S2 |
| 2010211129 | 29 | 11 (6 / 5) | 2 | 1800 | S2 |
| 2010431153 | 53 | 12 (6 / 6) | 2 | 1800 | S2 |
| 1910631192 | 92 | 12 (6 / 6) | 2 | 1800 | S2 |
| 2010131194 | 94 | 4 (2 / 2) | 1 | 1800 | S2 |
| 1930331196 | 96 | 52 (26 / 26) | 5 | 2880 | S2 |
| 201033019601 | 9601 | 2 (1 / 1) | 1 | 1000 | S2 |
| 2130511121 | 21 | 89 (45 / 44) | 7 | 2880 | S3 |

The manifest also records the SHA-256 of each scenario's four input files, so a run can prove it
used exactly these inputs. Scenario and map identifiers are published; scenario contents are not.

## 3. Conditions, repetitions and order

| Condition | Red | Blue | Purpose |
|---|---|---|---|
| C1 | `baseline-v0` | `baseline-v0` | baseline mirror |
| C2 | `baseline-v0` | `inert-v0` | baseline against the control, red side |
| C3 | `inert-v0` | `baseline-v0` | baseline against the control, blue side |
| C4 | `inert-v0` | `inert-v0` | the engine's outcome when nobody acts |

Every configuration (scenario and condition) is played twice: 8 x 4 x 2 = 64 games. Order: for
each repetition, for each scenario in the table's order, for each condition in order. Seats are
1 (red) and 11 (blue), the player list the SDK's own demo runner uses.

Each game is one process and one recorded engine session, with the isolation of the smoke test
(`docs/ENGINE_SMOKE_TEST.md`): empty environment, the persistent installation's home, no user
site-packages, `PYTHONHASHSEED=0`, no GPU, a hard timeout. Caps: `max_time + 1 + 100` engine steps
(a game takes `max_time + 1` steps including the deployment step) and 1800 s of wall time.

## 4. Randomness

The documented engine interface (`setup`, `step`, `reset`) takes no seed, and the platform
documentation shows random draws in combat adjudication (`judge_info` records carry random
numbers). No seed control is claimed and no undocumented engine interface is used. What the
harness controls is its own process: the hash seed, and Python's and NumPy's global generators,
seeded with 20260929 before the engine is constructed and fingerprinted at five points to record
whether the engine draws from them. Whether games are reproducible is **measured** by repeating
every configuration and locating the first step at which the engine state diverges.

The policy itself uses no randomness and no clock; tests enforce this by patching every clock
and random source to raise, and by scanning the decision sources for such imports.

## 5. Metrics

| Group | Definition |
|---|---|
| Reliability | games completed / started; exceptions by origin (engine, setup, agent, contract, reset); step-cap and wall-cap hits |
| Legality | gate rejections by reason (numbers replaced by `N`); engine-reported errors for the seat's actions by code (the all-seeing `actions` field); effect check of every emitted action against the next all-seeing observation: confirmed / not observed / indeterminate, by action type |
| Activity | actions by type; steps with at least one action; units that acted and units seen; first step of each action type; unit-steps per no-op reason |
| Determinism | per-step order-independent digest of the all-seeing state; per-seat chained digest of the decision traces; first divergence between repetitions; in-game replay checks (every 100 steps the decision is recomputed by a fresh policy instance and compared) |
| Outcome | the engine's final `scores` fields exactly as reported; no composite score |
| Performance | per-decision latency with `time.perf_counter`, reported as p50 / p95 / p99 / max by the nearest-rank method (the value at rank ceil(p/100 x n)); total decision time; total engine step time; game wall time; harness time = wall - decisions - engine |

The effect check exists because an engine that stays silent would otherwise make every action
look accepted. Documented effects used: deployment completion sets the seat's `end_deployment`
(or the play stage begins); a move gives the unit a non-empty `move_path` or a new hex;
occupation sets the objective's flag; direct fire adds a `judge_info` record naming shooter and
target.

## 6. Gates

Criteria, evaluated over the repetitions of one configuration:

* **G1** every game reaches the engine's done flag within the step cap, without an exception in
  the engine, the harness or an agent, and without a contract error;
* **G2** both seats end deployment and the play stage begins;
* **G3** every baseline seat emits at least one play-stage unit action;
* **G4** no gate rejection, no engine-reported error for a baseline action, and every emitted move
  and deployment completion confirmed by the next observation; occupy and shoot confirmation is
  reported but not gating, because another action in the same step (such as a second shot at a
  target already destroyed) can legitimately remove its precondition;
* **G5** for every step before the first divergence of the engine state between the repetitions,
  the decision traces are identical, and every in-game replay check matches;
* **G6** every game record contains every registered metric.

**Gate 1** is the baseline mirror on scenario 201033019601 (map 9601), played twice, recorded
separately from the suite. It passes when G1 to G6 all pass; `scripts/run_evaluation.sh` refuses
to start the suite before that. **Gate 2** is the registered suite: all 64 games in the registered
order, with G1 to G6 reported per configuration (criteria about baseline seats do not apply to C4).
No policy change is allowed between suite games; a change invalidates every result and requires a
new identity, a new registration and a complete rerun. Scenarios are never dropped, added or
reordered after results are seen, except by rule R.

## 7. Analysis commitments

* No composite quality score.
* Outcomes are reported per game and summarized descriptively per condition. Eight scenarios and
  two repetitions support no claim that one policy is stronger than another, and none is made.
* A game that was started but left no record stops the run; it is investigated and documented
  before anything is rerun, so outcomes cannot be selected by retrying.

## 8. Artifacts

| Artifact | Where | Public |
|---|---|---|
| Manifest (the registration) | `evaluation/baseline-v0/manifest.json` | yes |
| Sanitized results: counts, rates, percentiles, engine scores, gate verdicts | `evaluation/baseline-v0/results.json` | yes |
| Game records: per-step digests, raw latencies, feedback details | `local/evaluation/baseline-v0/games/` | no (git-ignored) |
| Staged inputs, logs, engine session ledger | `local/` | no |

## 9. Reproducing

```bash
python scripts/build_evaluation_manifest.py --check          # the manifest re-derives from the SDK archive
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan gate1
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan suite
python scripts/run_evaluation.py summarize --public evaluation/baseline-v0/results.json
```

`PYTHON` is the interpreter of the `miaosuan-runtime` environment and `ZIP` the local copy of the
SDK archive; the engine runs only on Linux, from the persistent installation
(`docs/ENGINE_INSTALL.md`).

## Results

Gate 1 and the suite were played on 2026-09-30 (UTC+8) on the Linux host of the persistent engine installation, harness commit `0a806f1`, one recorded engine session per game (ledger sessions 0003 to 0068; Gate 1 is 0003 and 0004). The engine's persistent state did not change in any of them.

Manifest `01c1f88b064ace501e56018576426cea6291bbabdce0e35387f72bec2d0068e6`; every record carries the registered policy source (`policy_source_consistent`: true). All figures below are computed from `evaluation/baseline-v0/results.json`.

### Summary

* **Reliable.** 64 of 64 suite games and 2 of 2 Gate 1 games reached the engine's done flag within the caps, without an exception or a contract error.
* **Active.** Every baseline seat emitted play-stage unit actions (G3 passed in 24 of 24 applicable configurations).
* **Deterministic where the engine is.** Decision traces were identical at every step at which the engine states of two repetitions agreed, and every in-game replay check matched (G5 passed in 24 of 24). The engine repeated exactly in all 16 configurations in which no shot was fired and diverged in all 16 in which one was, each time exactly one step after the first shot and never earlier: its randomness shows in combat adjudication.
* **Not fully legal by the registered criterion.** G4 failed in 14 of 24 applicable configurations. The gate rejected nothing and every move and deployment completion took effect, but the engine refused 187 of the baseline's 3,383 unit actions (5.5%). All three refusal codes are same-step conflicts: the refused action was listed as legal at the start of the step, and an action resolved earlier in the same step removed its precondition. Code 1804 is pure redundancy (several own units occupying one objective in the same step) and a policy can avoid it; 516 (a shot at a target destroyed earlier in the step) can be avoided only by giving up follow-up shots whose predecessor may leave the target alive; 203 (a shot by a unit destroyed earlier in the step) cannot be foreseen from start-of-step information. The criterion counts all three and is reported as registered. (Correction 2026-09-30: code 203 is not specific to shots; see the note under the engine-reported errors table.)
  In 3 further diagnostic games every refusal fitted this reading: all 45 refusals with code 1804 concerned an objective not held at the start of the step for which several occupations were issued in that step; all 7 with code 516 concerned a target present at the start of the step and fired at more than once in it; and the single refusal with code 203 concerned a shooter present at the start of the step.
* **Outcomes, descriptively.** Against the inert control the baseline side's engine total was higher in 32 of 32 games. As registered, no claim of relative strength is drawn from this.
* **Fast, with rare slow steps.** The 99th percentile of decision latency was at most 1.205 ms in every condition; the slowest single decision took 1304.309 ms. What made the rare slow steps slow was not measured.

### Gate 1

| Game | Status | Steps | red_total | blue_total | Baseline actions (red / blue) |
|---|---|---|---|---|---|
| gate1.201033019601.C1.r1 | COMPLETED | 1001 | 140 | 0 | 6 / 5 |
| gate1.201033019601.C1.r2 | COMPLETED | 1001 | 120 | 20 | 6 / 5 |

Criteria: G1 pass, G2 pass, G3 pass, G4 pass, G5 pass, G6 pass.
The engine states of the two games first differ at step 102, and their final scores differ; the decision traces are identical at every step before the divergence.

### Suite

64 of 64 registered games recorded.

Reliability and legality (baseline seats; effect checks as confirmed / not observed / indeterminate):

| Condition | Games | Completed | Failed | Capped | Gate rejections | Engine errors | Contract errors | Moves | Shots | Occupations | Deployment |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 16 | 16 | 0 | 0 | 0 | 112 | 0 | 1024 / 0 / 3 | 874 / 17 / 12 | 209 / 0 / 0 | 32 / 0 / 0 |
| C2 | 16 | 16 | 0 | 0 | 0 | 41 | 0 | 404 / 0 / 0 | 109 / 4 / 0 | 87 / 0 / 0 | 16 / 0 / 0 |
| C3 | 16 | 16 | 0 | 0 | 0 | 34 | 0 | 458 / 0 / 0 | 98 / 2 / 0 | 82 / 0 / 0 | 16 / 0 / 0 |
| C4 | 16 | 16 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | n/a |

Engine-reported errors: 187 of 3,383 baseline unit actions (5.5%) were refused by the engine. Their meaning was identified afterwards from the engine's own error messages in 4 separate diagnostic games (`evaluation/baseline-v0/diagnostics.json`; not part of the registered results):

| Code | Action | Engine message | C1 | C2 | C3 | Total |
|---|---|---|---|---|---|---|
| 1804 | occupy | `CantOccupyCauseAlreadyMy` | 88 | 37 | 32 | 157 |
| 516 | shoot | `CantShootToDiedBop` | 17 | 4 | 2 | 23 |
| 203 | shoot | `CantControlDiedOperator` | 7 | 0 | 0 | 7 |

> Correction (2026-09-30; analysis only, counts unchanged): the suite records of this evaluation hold
> the refusal code only. The Action and Engine message columns come from the diagnostic games, in
> which every code-203 refusal was a shot; the action type of the suite refusals with code 203 is
> unknown, and a later evaluation recorded code 203, with the same message, on an occupation. Code
> 203 does not identify a shot. See `docs/REFUSAL_TAXONOMY.md`.

Activity (baseline actions emitted, summed over the condition's games):

| Condition | Moves | Shots | Occupations | Deployment | Seats with a play-stage action |
|---|---|---|---|---|---|
| C1 | 1027 | 903 | 209 | 32 | 32 of 32 |
| C2 | 404 | 113 | 87 | 16 | 16 of 16 |
| C3 | 458 | 100 | 82 | 16 | 16 of 16 |
| C4 | 0 | 0 | 0 | 0 | 0 of 0 |

Criteria over the 32 configurations (pass / fail / not applicable):

| Criterion | Pass | Fail | Not applicable | Failing configurations |
|---|---|---|---|---|
| G1 | 32 | 0 | 0 | none |
| G2 | 32 | 0 | 0 | none |
| G3 | 24 | 0 | 8 | none |
| G4 | 10 | 14 | 8 | 1910631192.C1, 1910631192.C3, 1930331196.C1, 1930331196.C3, 2010131194.C1, 2010211129.C2, 2010431153.C1, 2010431153.C3, 2120531121.C1, 2120531121.C2, 2120531121.C3, 2130511121.C1, 2130511121.C2, 2130511121.C3 |
| G5 | 24 | 0 | 8 | none |
| G6 | 32 | 0 | 0 | none |

Determinism: engine state and decision traces across the two repetitions of each configuration.

| Configuration | Engine states identical | First divergence (step) | Final scores equal | Traces identical while states agreed |
|---|---|---|---|---|
| 2120531121.C1 | false | 137 | false | true |
| 2120531121.C2 | false | 370 | false | true |
| 2120531121.C3 | false | 169 | false | true |
| 2120531121.C4 | true | n/a | true | true |
| 2010211129.C1 | false | 322 | false | true |
| 2010211129.C2 | false | 583 | true | true |
| 2010211129.C3 | true | n/a | true | true |
| 2010211129.C4 | true | n/a | true | true |
| 2010431153.C1 | false | 142 | false | true |
| 2010431153.C2 | true | n/a | true | true |
| 2010431153.C3 | true | n/a | true | true |
| 2010431153.C4 | true | n/a | true | true |
| 1910631192.C1 | false | 523 | false | true |
| 1910631192.C2 | true | n/a | true | true |
| 1910631192.C3 | true | n/a | true | true |
| 1910631192.C4 | true | n/a | true | true |
| 2010131194.C1 | false | 102 | false | true |
| 2010131194.C2 | true | n/a | true | true |
| 2010131194.C3 | false | 222 | true | true |
| 2010131194.C4 | true | n/a | true | true |
| 1930331196.C1 | false | 189 | false | true |
| 1930331196.C2 | false | 612 | true | true |
| 1930331196.C3 | false | 213 | true | true |
| 1930331196.C4 | true | n/a | true | true |
| 201033019601.C1 | false | 102 | false | true |
| 201033019601.C2 | true | n/a | true | true |
| 201033019601.C3 | true | n/a | true | true |
| 201033019601.C4 | true | n/a | true | true |
| 2130511121.C1 | false | 102 | false | true |
| 2130511121.C2 | false | 102 | false | true |
| 2130511121.C3 | false | 526 | false | true |
| 2130511121.C4 | true | n/a | true | true |

Identical engine states in both repetitions: 16 of 32 configurations. In-game replay checks: 1392, mismatches: 0.
The global generators were changed by the engine in 0 of 66 games (Gate 1 and suite).

Outcomes: the engine's final `red_total` / `blue_total`, per game.

| Scenario | Condition | Repetition 1 | Repetition 2 |
|---|---|---|---|
| 2120531121 | C1 | 170 / 881 | 100 / 951 |
| 2120531121 | C2 | 744 / 307 | 674 / 377 |
| 2120531121 | C3 | 231 / 820 | 226 / 825 |
| 2120531121 | C4 | 334 / 407 | 334 / 407 |
| 2010211129 | C1 | 26 / 310 | 36 / 300 |
| 2010211129 | C2 | 300 / 36 | 300 / 36 |
| 2010211129 | C3 | 104 / 232 | 104 / 232 |
| 2010211129 | C4 | 104 / 102 | 104 / 102 |
| 2010431153 | C1 | 28 / 338 | 26 / 340 |
| 2010431153 | C2 | 234 / 132 | 234 / 132 |
| 2010431153 | C3 | 104 / 262 | 104 / 262 |
| 2010431153 | C4 | 104 / 132 | 104 / 132 |
| 1910631192 | C1 | 46 / 320 | 26 / 340 |
| 1910631192 | C2 | 234 / 132 | 234 / 132 |
| 1910631192 | C3 | 104 / 262 | 104 / 262 |
| 1910631192 | C4 | 104 / 132 | 104 / 132 |
| 2010131194 | C1 | 200 / 10 | 60 / 150 |
| 2010131194 | C2 | 130 / 80 | 130 / 80 |
| 2010131194 | C3 | 0 / 210 | 0 / 210 |
| 2010131194 | C4 | 80 / 80 | 80 / 80 |
| 1930331196 | C1 | 897 / 143 | 530 / 510 |
| 1930331196 | C2 | 657 / 383 | 657 / 383 |
| 1930331196 | C3 | 235 / 805 | 235 / 805 |
| 1930331196 | C4 | 323 / 407 | 323 / 407 |
| 201033019601 | C1 | 10 / 130 | 130 / 10 |
| 201033019601 | C2 | 110 / 30 | 110 / 30 |
| 201033019601 | C3 | 30 / 110 | 30 / 110 |
| 201033019601 | C4 | 30 / 30 | 30 / 30 |
| 2130511121 | C1 | 276 / 1327 | 334 / 1269 |
| 2130511121 | C2 | 1198 / 405 | 1180 / 423 |
| 2130511121 | C3 | 472 / 1131 | 520 / 1083 |
| 2130511121 | C4 | 560 / 603 | 560 / 603 |

Descriptively, in C2 and C3 the baseline side's total was ahead of the inert side's in 32, level in 0 and behind in 0 of 32 games. As registered, no claim of relative strength is drawn from this.

Performance (baseline decisions; latency by nearest rank):

| Condition | Decisions | p50 ms | p95 ms | p99 ms | max ms | Engine s | Wall s |
|---|---|---|---|---|---|---|---|
| C1 | 67392 | 0.303 | 0.912 | 1.182 | 507.089 | 249.967 | 643.27 |
| C2 | 33696 | 0.599 | 1.019 | 1.162 | 424.725 | 346.32 | 900.644 |
| C3 | 33696 | 0.701 | 1.175 | 1.205 | 1304.309 | 339.742 | 895.437 |
| C4 | 0 | n/a | n/a | n/a | n/a | 324.861 | 913.93 |
