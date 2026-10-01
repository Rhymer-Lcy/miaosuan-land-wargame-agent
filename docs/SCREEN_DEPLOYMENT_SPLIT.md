# Screen: deployment disaggregation (tactical-screen-deployment-split-1)

**EXPLORATORY - NOT ELIGIBLE FOR BASELINE PROMOTION.** Registered disposition: **REVISE BEFORE CONFIRMATION**.

The first exploratory screen of the tactical frontier (`docs/TACTICAL_FRONTIER.md`), family T1. It tested one
deployment-stage change on top of the frozen `baseline-v2`. Exploratory evidence only: nothing here supports a claim
that the tactic helps or harms, and nothing here can promote a baseline.

## Registration

* Public preregistration record: https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/1, created
  2026-10-01T18:40:46Z (GitHub's clock) before any engine session of this experiment. The first one, session 2258,
  opened at 2026-10-01T18:55:37Z by the server clock, which runs fast by the offset recorded in
  `docs/ENGINE_INSTALL.md`.
* Registration commit `ec2be5f`; manifest `evaluation/tactical-screen-deployment-split-1/manifest.json`, canonical
  SHA-256 `7ef883b7daa6f4272655cd2f8716cd84dcf0d369aff68f6122adec2357c77dcd`, design digest `3e773d90...`.
* Parent `baseline-v2`, policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`; candidate
  `tactic-deployment-split-1`, policy source `000f639b35becbbd712d6134def855284b80ad4644409dc2f0ae9ee47113a2e9`
  (`baseline-v2`'s sources plus `src/miaosuan_agent/experiments/deployment_split.py`). Runtime
  `baseline-v1-runtime-r2`, 32 workers, scheduler `miaosuan-game-pool/1@e717be37...`. Both digests were checked
  before the first and after the last game of each run.

The candidate splits every eligible operator (controllable, on the map, type 1 or 2, not artillery, at least 2 vehicles
or squads) with the deployment split action 314 in its first deployment decision, splits the resulting eligible
operators once more in the next, and then ends deployment through `baseline-v2`'s own rule. The play stage is
`baseline-v2`'s.

## Mechanism smoke

Eight diagnostic games, one per frozen scenario, the candidate as red against the inert control, with the read-only
step capture (sessions 2258 to 2265). `evaluation/tactical-screen-deployment-split-1/smoke.json`; verdict **PASS**:
in three games splits took effect and the candidate later commanded the new operators, every game completed, every
deployment ended, and no game recorded a contract error.

| Scenario | Splits emitted | Took effect | Refused (code) | No effect, no error | New units | Commanded later | Controllable seen / at setup |
|---|---|---|---|---|---|---|---|
| 1910631192 | 10 | 4 | 0 | 6 | 6 | 4 | 8 / 6 |
| 1930331196 | 30 | 12 | 0 | 18 | 18 | 12 | 32 / 26 |
| 2130511121 | 52 | 28 | 0 | 24 | 36 | 28 | 65 / 45 |
| 2010131194 | 4 | 0 | 4 (103) | 0 | 0 | 0 | 2 / 2 |
| 2010211129 | 8 | 0 | 8 (103) | 0 | 0 | 0 | 4 / 6 |
| 201033019601 | 2 | 0 | 2 (103) | 0 | 0 | 0 | 1 / 1 |
| 2010431153 | 8 | 0 | 8 (103) | 0 | 0 | 0 | 4 / 6 |
| 2120531121 | 24 | 0 | 24 (103) | 0 | 0 | 0 | 22 / 28 |

New units include passengers; no order to a new unit was refused.

### Engine semantics observed on 4.1.0

* **Acceptance is decided per scenario.** Three scenarios accepted deployment splits; in the other five the engine
  refused every one with code 103 (`ErrorActionType`), including two whose own force matches an accepting scenario's
  unit for unit. A seat's observation holds no field that tells the two groups apart. In the scenario files the
  accepting scenarios carry `annual_version` 2021 or none and the refusing ones 2020 or `msb`; that is an association
  across eight scenarios, not an established cause, and a seat cannot read it.
* **The engine rewrites the action in place**: during the step it changes a deployment split's `type` from 314 to 14
  in the caller's own action object.
* **Split mode as documented**: 4 vehicles or squads become 2 + 2, 3 become 2 + 1, 2 become 1 + 1. The new operator
  appears in its parent's hex under the lowest unused ids; a carrier's passengers split with it, and the new carrier
  holds their twins.
* **The new operators are the seat's own**: they are listed in the seat's `role_and_grouping_info` and obey orders.
* **Stacking limit**: a split takes no effect, and returns no error, when the parent's hex already holds four of the
  seat's ground units (passengers not counted). Replaying the candidate's batches from the scenarios' initial positions
  under that rule predicts exactly which splits took effect in all six split rounds of the three accepting games;
  without the limit the prediction fails in every round. Whether an operator bound to a launcher is blocked
  independently of the limit cannot be separated here: those operators always stood in full hexes.
* **Deployment lasts until both sides end it** (three decisions here; the engine clock stays at step 0).
* **Feedback accumulates while the clock stands still**: during deployment the engine re-reports its earlier feedback
  entries at every step, so the harness counts each deployment refusal once per step until play starts.

### Analysis deviation

The first run of the smoke analysis reported BLOCKED BY ENGINE SEMANTICS with zero splits in every game. It had
matched type 314 in the batch, which the capture serialises after the engine step has rewritten it to 14; the games'
own records (2 to 52 deployment splits emitted per game) contradicted it. Two fixes were committed, tested
(mutation-tested: 8 of 8 planted defects caught) and pushed before the first A/B session:

* `0d0ae92`: a captured split is read under either type; the count must equal the record's, or the analysis refuses
  to run; only fresh feedback entries are read; each split's outcome is classified.
* `e0a4f8a`: the verdict requires the split, the new operators and the later command in one and the same game, as
  the registered rule says; before, two different games could satisfy it together.

The registered pass rule did not change, and neither fix changes the verdict on these data. The first output is kept
outside the repository.

## Exploratory A/B

192 games (sessions 2266 to 2457), every one completed; integrity passed (records, queue order, manifest digest, policy
digests, runtime, execution identity, each session opened and closed once, consecutive sessions).
`evaluation/tactical-screen-deployment-split-1/results.json`. The analysis's tests (`557160b`, 12 of 12 planted defects
caught) were pushed while the games were running, before any result was read.

Head-to-head (candidate total minus `baseline-v2` total; three games as red and three as blue per scenario):

| Scenario | Splits | Mean margin |
|---|---|---|
| 1910631192 | accepted | 4.67 |
| 1930331196 | accepted | -190.33 |
| 2130511121 | accepted | 281.33 |
| 2010131194 | refused | 60 |
| 2010211129 | refused | 3.33 |
| 201033019601 | refused | 40 |
| 2010431153 | refused | -8.67 |
| 2120531121 | refused | -143.33 |

Pooled mean +5.88 (95% scenario bootstrap -78.58 to 97.71); 5 scenarios above 0 and 3 below; 24 wins, 24 losses, no
draw. Components, candidate minus opponent: occupy -12.08, attack +8.98, remain +8.98.

Against the inert control (candidate arm minus baseline arm, the arm's active margin): 0 in eight of the ten
configurations of the refusing scenarios and +46.67 and +10 in the other two (2120531121, whose games against the inert
control vary from game to game); in the accepting scenarios 0 and -80 (1910631192, as red and as blue), 0 and -14
(1930331196), -9.33 and +6.67 (2130511121). 13 of 16 configurations are not worse, 3 better, 3 worse.

Mechanism: the candidate's seats saw more controllable operators than the baseline's in 12 of 32 cells, exactly the
cells of the three accepting scenarios (8 to 80 against 4 to 44).

Safety: no contract error, gate rejection, replay mismatch or duplicate same-target shot in either arm (144 policy
seat-games each); no failed or capped game. Refusal classes new in the candidate: 103/14 in 90 seat-games (its
refused deployment splits, every candidate seat-game of the refusing scenarios) and 203/5 in 4 seat-games (refused
occupation orders, all in 1930331196). Code 516 on shots: 7 candidate seat-games against 5. Decision latency, candidate
against baseline: median 0.661 ms against 0.517 ms, 95th percentile 2.781 ms against 1.398 ms, maximum 1,697 ms
against 1,509 ms.

## Reading

* **The refusing scenarios are an A/A control.** There the candidate's splits are refused and it plays `baseline-v2`'s
  play stage. Its head-to-head scenario means there still range from -143.33 to +60 (standard deviation 79.62), each
  within 1.11 standard errors of zero by its own six games (1.58 with the pooled residual standard deviation below).
* **One lead, one opposite sign, one null.** In the largest scenario, 2130511121, where splitting nearly doubles the
  force (65 controllable operators against 37 as red, 80 against 44 as blue), the candidate's mean is +281.33, 3.45
  standard errors above zero by its own six games (3.09 pooled), the largest deviation of the screen. In 1930331196
  it is -190.33 (-1.09; -2.09 pooled), in 1910631192 +4.67 (0.36). One deviation of this size among eight scenarios,
  its standard error estimated from two degrees of freedom per side, is a lead for the revision, not evidence of a
  gain.
* **Noise.** The head-to-head margin's residual standard deviation within a scenario and side is 222.9 points
  (pooled, 32 degrees of freedom), so a six-game scenario mean has a standard error of about 91 points; with three games
  per side the screen could only have detected a pooled effect of about 90 points (80% power, 5% two-sided).
* **One deterministic signal.** Against the inert control most games repeat exactly. As blue in 1910631192, the
  candidate scored 78 in all three games where `baseline-v2` scored 158: splitting changed what `baseline-v2`'s play
  stage does with the force, and the occupation component is lower on average. The new refusal class 203/5 points the
  same way: occupation orders of a split force refused. This is a doctrine interaction, not a fire-power effect.

## Disposition

**REVISE BEFORE CONFIRMATION**, by the registered rule: no catastrophic event and a pooled mean above 0 with only 3
scenarios below 0 (no REJECT); the mechanism active in 12 of 32 cells, below the 75% the rule requires (no ADVANCE).

## What a revision would change (not registered)

* Probe once: stop splitting after the engine refuses a deployment split with code 103 (a capability predicate read
  from the engine's own feedback, not from a scenario list).
* Skip splits that the stacking limit voids.
* Diagnose the deterministic loss before changing anything in play: two captured diagnostic games of 1910631192 with
  the inert control as red, one per arm.
* Judge only games in which the engine accepted splits, identified per game from the records.
* Carry the lead forward as a hypothesis stated in advance, with its own observable predicate: disaggregation pays
  when the force is large (its operator count at deployment), not as a list of scenarios.

## Confirmation (not designed now)

Only a revised candidate that earns ADVANCE in a fresh screen would get a confirmatory design. With the observed
residual standard deviation, a confirmation over the three split-capable scenarios would need about 20 games per side
per scenario to detect a pooled effect of about 57 points, or 40 games for about 40 points (80% power, 5% two-sided,
one common effect assumed; heterogeneous effects widen it).
