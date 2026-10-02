# T1-r diagnosis: the deployment-split loss in scenario 1910631192

**DIAGNOSTIC.** No decision rule depends on this document's outcome. It feeds the revision of candidate
`tactic-deployment-split-1` (`docs/SCREEN_DEPLOYMENT_SPLIT.md`), not any registered study.

Sections 1 to 4 were written and pushed before the two diagnostic games were played; section 5 onwards is filled
afterwards and says so. Times are UTC+8.

## 1. The question

In the Sprint 1 screen, with the inert control as red in scenario 1910631192, the split arm as blue scored 78 (blue
total minus red total) in all three of its games where the `baseline-v2` arm scored 158 in all three of its games.
The two arms share the play stage: the candidate adds deployment splits (two rounds) and otherwise is `baseline-v2`.
Why does splitting cost 80 points here?

### Prior evidence read before this document (disclosed)

The six Sprint 1 records of `1910631192.C3.b.x01-03` and `1910631192.C3.c.x01-03` exist and were read while
planning. They hold aggregates only. What they show, and what this document therefore already assumes:

| | `baseline-v2` arm (x3, identical) | split arm (x3, identical) |
|---|---|---|
| blue occupy / attack / remain | 130 / 0 / 132 (remain max 132) | 50 / 0 / 132 (remain max 132) |
| red occupy / attack / remain | 0 / 0 / 104 | 0 / 0 / 104 |
| blue actions by type | move 10, occupy 2, end deployment 1 | move 18, occupy 1, deployment split 12, end deployment 1 |
| blue controllable operators seen / acted | 6 / 6 | 14 / 14 |
| feedback errors | none | none |
| deployment ended at step | 1 | 3 |

So the whole 80-point gap is the occupy component (130 against 50); neither side lost a unit or fired. The scenario
file (private, read offline) has two objectives, worth 80 and 50, and the sum of the blue operators' `value` times
`blood` is 132: the remain score is exactly that sum, which splitting conserves. The missing 80 is the value of one
objective the split arm never held at the end. These facts shape the hypotheses below but decide none of them.

## 2. The two diagnostic games and the capture configuration

| Item | Value |
|---|---|
| games | `1910631192.C3.b.x01` (red inert-v0, blue `baseline-v2`) and `1910631192.C3.c.x01` (red inert-v0, blue `tactic-deployment-split-1`), the first repetition of each Sprint 1 configuration, played again from the screen manifest (`7ef883b7...`) with `--purpose diagnostic` |
| runtime | `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), serial (`--workers 1`), SDK 4.1.0 engine installation on the server |
| work directory | `local/evaluation/t1r-diagnosis-1` (private), records and captures beside each other |
| capture | the read-only step capture of `evaluation/residual516.py` for both seats' policies: every step's submitted batch, feedback, unit appearances and watched-field changes, trace digests; full state snapshot (all-seeing state, each policy seat's observation and memory) **every step** (`--sample-every 1`, added to the runner for this diagnosis; the default stays 200) |
| premise check | each game must reproduce its Sprint 1 record exactly: blue total 262 and 182, red total 104, the same action counts by type. If either does not, the diagnosis stops and reports; determinism is part of the premise |
| ledger | two diagnostic sessions, expected 2458 and 2459 |

## 3. Pre-declared hypotheses and their observables

Each hypothesis names the observable that would support it and the one that would refute it. The observables are
computed by `scripts/t1r_diagnosis.py` from the two captures; the public output (`evaluation/t1r-diagnosis-1/
analysis.json`) carries counts, scores, hexes of objectives and step indices only, never unit identifiers.

| Id | Hypothesis | Supported if | Refuted if |
|---|---|---|---|
| H1 | force fragmentation: split products are weaker per unit and lose more to attrition, or score less | any blue blood loss, any shot fired at or by blue, or a remain score below value x blood in the split game | blue blood sum constant through both games, no shot in either, remain equal to value x blood in both |
| H2 | play-stage interaction: `baseline-v2`'s per-unit hierarchy (engage, occupy, move; one occupation per objective per step; no move while a move is executing; no move away from an unheld objective the unit stands on; move to the cheapest unheld objective) behaves differently with more, smaller units | in the split game, at least one blue unit stands on the unheld 80-point objective at some step while no occupation is listed or issued for it, or units able to move are left idle or sent elsewhere by a stated rule while that objective is unheld, and the baseline game shows no such state | every blue unit that reaches an unheld objective gets an occupation listed and issued, and the policy's decisions on the split game's states would, unit for unit, equal those of the baseline game |
| H3 | positional congestion: more units in the same hexes hit the stacking limit (four own ground units per hex) and moves do not complete | some hex holds four blue ground units at some step in the split game and a confirmed move into or through it does not complete (unit position unchanged over the following 20 steps, or a feedback error), while the baseline game never reaches four | no blue hex holds four units at any step of the split game, or every confirmed move reaches its destination |
| H4 | carrier/passenger effects: passengers split with carriers and change transport or dismount behaviour | any blue unit with `on_board` 1 or a non-null `car` at any step of either game, or a boarding or landing event | no blue unit is ever a passenger in either game (the scenario's blue force is read as six ground operators) |
| H5 | timing: the two extra deployment decisions shift the play stage so the second occupation cannot complete before step 1800 | in the baseline game the occupation of the 80-point objective completes (city flag flips) within 2 steps of the end, or the split game's last occupation is in progress at the end | the baseline's second flag flips more than 2 steps before the end and the split game's units reach the objective, if at all, with more than that margin left |
| H6 | scoring artefact: the scoring rule values units, losses or objectives in a way splitting changes | remain differs from value x blood, or occupy differs from the sum of the values of the objectives held at the end, in either game | both identities hold exactly in both games |
| H0 | something else | stated if found, with its observable | |

Quantification required: the 80 points attributed by scoring component and by 200-step window of the play stage
(cumulative occupy points held per window, from the city flags in the per-step snapshots), and the components'
difference summed and compared with the score difference exactly.

## 4. First-divergence method

The two games are aligned by engine time (`cur_step`), not by decision index, because the split game spends two more
decisions in deployment. For each aligned step the analysis compares, for blue: the blood-weighted occupancy of hexes
(sum of blood per hex, which splitting alone leaves unchanged), the set of hexes with a blue unit, the city flags,
the set of destinations of moves issued in the step, and the occupation commands issued. The first play step at which
the blood-weighted occupancy or the city flags differ is the first behavioural divergence; the actions of the
preceding steps are then read forward to find which rule produced it, and the consequence is traced to the final
flags. Deployment steps are compared separately (splits only).

Cross-checks required by lesson L4 before any conclusion: the batch's occupation and move counts must equal the
record's `actions_by_type`; the final flags in the last snapshot must reproduce the record's occupy scores; the
candidate's split count must equal the record's. The analysis refuses to run on disagreement.

## 5. Results

(filled after the run)
