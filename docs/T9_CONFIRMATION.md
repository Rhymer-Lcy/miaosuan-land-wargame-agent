# T9 confirmatory study: staged, registered (`t9-confirmation-1`)

Status: REGISTERED before the first engine session of the study (public issue #4); phases A, D and B ran (285
sessions), phase B's gate stopped the study before phase C. Disposition PRIMARY_SUPPORTED_NEEDS_REVISION (see
"Disposition and next step" under Results). CONFIRMATORY track (`docs/EXPLORATORY_TRACK.md`);
not eligible for baseline promotion. Dates are business dates in UTC+8. The registration is
`evaluation/t9-confirmation-1/manifest.json` (canonical SHA-256 `28324b3a6742f8fe8b4a7938b03f0077e894be701ce06527543cf81df043981c`, design digest
`028ebf57a55e8ad00624f66de449b164fa4b44ca45c9f520ba65e4217ad15576`), built by `scripts/build_t9_confirmation_manifest.py` from committed inputs; where this text and
the manifest differ, the manifest governs. Results are appended under "Results", phase by phase.

## 1. Purpose and starting state

The study decides whether the unchanged Sprint 8 candidate `t9-capacity-allocation-v1` improves competitive
performance. It was approved by the owner as a staged design built on `docs/T9_CONFIRMATION_PROPOSAL.md`, with five
revisions: a fixed phase A test with conditional continuation; one C1 control game supplying both seat outcomes,
kept together in the analysis; power from the observed candidate variance as well as the historical baseline
variance; the small-scenario panel as a safety screen, not a powered non-inferiority proof; and one primary endpoint
that no other comparison can replace.

Starting state, verified before any implementation: GitHub `main` `48483f68edf6a6575b3bce0d2a95cf7983aa98d0` on the
workstation, GitHub and the evaluation server; the engine ledger closed through session 2487 with none unclosed,
integrity ok and the state chain continuous; candidate policy source
`0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa`, `baseline-v2` policy source
`7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, both recomputed from the checkout; the qualified
scheduler `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90` recomputed from
the checkout and equal to the runtime thread qualification's.

## 2. Identities

| Item | Identity |
|---|---|
| Candidate | `t9-capacity-allocation-v1`: `experiments/exploratory_addon.py` and `experiments/t9_allocation.py` on the frozen `baseline-v2`; capacity 4, detour factor 2, exactly as explored; policy source `0a0b7174...`, equal to the Sprint 8 run cards' |
| Control | `baseline-v2` (`baseline-v2-candidate-shoot-target-reservation`), policy source `7cbaf032...`; fresh games only |
| Inert control | `inert-v0` |
| Runtime | `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`) |
| Execution | the qualified scheduler, unchanged, with 32 workers: the configuration the runtime thread qualification promoted for runtime-r2 (`docs/BASELINE_V1_RUNTIME_R2.md`); shared engine sessions through the persistent installation and its append-only ledger |
| Game entry point | `scripts/run_t9_confirmation_game.py`, the pool's own game command line; the registered evaluator (`scripts/run_evaluation.py`, `.sh`) is unchanged and reused by import |

Nothing in the candidate was tuned against Sprint 8's games or will be tuned against this study's.

## 3. Design

| Phase | Configurations | Games | Sessions | Role |
|---|---|---|---|---|
| A | 2130511121: H1 (candidate red against `baseline-v2` blue), H2 (`baseline-v2` red against candidate blue), C1 (`baseline-v2` mirror) | 15 each | 45 | primary |
| D | 2010211129, 2010431153, 1910631192, 2010131194, 201033019601: C2 and C3 against the inert control, candidate and `baseline-v2` arms | 3 per configuration and arm | 60 | safety screen |
| B | 2120531121, 1930331196, 2130511121: C2 and C3 against the inert control, both arms | 15 per configuration and arm | 180 | secondary |
| C | 2120531121 and 1930331196: H1, H2 and C1 as in A | 15 each | 90 | secondary |

* Order and gates. A runs first. Each later phase runs only after the previous phase's registered gate says
  CONTINUE (section 7). A phase passing its gate permits only the next phase, never a promotion.
* Budget. At most 375 sessions after ledger session 2487 (45 + 60 + 180 + 90); a ceiling, not a target. The
  runner checks the cap before each phase and each game checks it again.
* Schedule. Within a phase, round r plays repetition r of every cell once; the order within a round is a fixed
  base order (SHA-256 of the design digest, phase and cell) rotated by one position per round. In phase A every
  cell therefore takes every position of a round exactly five times. The pool dispatches games in this order, at
  most 32 at a time.
* Randomness. Each game runs in a new process; the harness seeds Python's and NumPy's global generators with the
  frozen seed before the engine is constructed. The engine's own randomness is not documented as controllable, so
  games are independent samples. They are not seed-matched, and repetition numbers do not pair games.
* Sprint 8's exploratory games enter no estimate of this study. They inform only the planning variance and the
  effect sizes of the power table.

## 4. Margin convention and the primary estimand

* Margin. A seat's terminal margin is its side's `<side>_total` minus the other side's total in the engine's final
  scores, the engine's own `<side>_win` (checked on every completed game). It is zero-sum: in a C1 game the blue
  margin is minus the red margin.
* Seat contrasts. Red: mean H1 red margin minus mean C1 red margin. Blue: mean H2 blue margin minus mean C1 blue
  margin.
* Primary estimand. Delta, their equally weighted mean, over the 45 phase-A games. Each C1 game is one experimental
  unit carrying its pair of seat outcomes; H1 and H2 games form separate strata. In computing form,
  Delta = 1/2 mean(H1 red) + 1/2 mean(H2 blue) - mean(c), with c = (red + blue) / 2 per C1 game.
* A consequence to state before any result: under the zero-sum convention c = 0 for every C1 game, so the C1
  games cancel exactly from Delta and from every resample that keeps their pairs together; Delta equals half the
  mean of the H1 red and H2 blue margins, and its uncertainty comes from the H1 and H2 games alone. Resampling the
  C1 red and blue outcomes as if they were independent would add variance that is not there; the registered
  procedure keeps the pairs. The C1 games still define the two seat-specific contrasts (secondary) and give fresh
  control figures. The general paired form is kept in the code, so the identity is checked on the data (every C1
  value of c is reported) rather than assumed.
* Hypothesis. Delta > 0. It is tested once, after all 45 phase-A games, and only if every one of them completed and
  integrity holds (sections 10 and 11). SUPPORTED if the lower limit of the registered 95% interval is strictly
  above 0.

## 5. Interval procedure

* Registered: a 95% studentized bootstrap (bootstrap-t) interval. Each stratum (H1, H2, C1 by game) is resampled
  independently with replacement, 20,000 resamples, from a generator seeded by `20261003` and the estimand's name
  (`t9_confirmation.seed_for`).
* For each resample t* = (Delta* - Delta) / SE*, with SE the plug-in standard error sqrt(sum w^2 s^2 / n). The
  interval is [Delta - q(0.975) SE, Delta - q(0.025) SE], with nearest-rank quantiles of t* computed exactly.
* The percentile interval of the same resamples and the Welch interval are reported as non-decisive sensitivity.
* Why studentized. Before registration the procedure was applied to 2,000 simulated phase-A analyses per cell
  (`validation.json`): three variance assumptions, normal and empirical shapes, Delta = 0. The studentized interval's
  lower limit lay above 0 in 1.5% to 2.6% of analyses (nominal 2.5%). The percentile interval did so in 3.45% to
  4.35%, the Welch interval in 2.4% to 3.55%: with 15 games per stratum the percentile interval is too narrow.
* An independent NumPy implementation of the studentized interval agreed with the registered one to within 0.03
  standard errors on two fixed data sets.

## 6. Power

Planning figures (`planning.json`, computed from 372 private records pinned by digest). The historical C1 margin of
2130511121 has a sample standard deviation of 114.66. The proposal quoted 110.8, the population figure; the sample
figures are the basis here, and the other two scenarios' C1 sample standard deviations are 586.6 and 453.24. The
candidate's six exploratory games there had red margins -815, -621 and -505 and blue margins 1,077, 1,133 and
1,297. Their seat standard deviations are 156.63 and 114.33, the exploratory estimate of Delta is 261.0, and the
three pair sums are 318, 456 and 792. With the C1 games cancelling,
SE(Delta) = 1/2 sqrt(sd_H1^2 / 15 + sd_H2^2 / 15).

| Variance assumption | SD H1 / H2 | SE | 80% MDE | Power at 130.5 (half the exploratory estimate) | Power at 261.0 |
|---|---|---|---|---|---|
| optimistic: both at the historical C1 SD | 114.7 / 114.7 | 20.93 | 58.7 | 1.000 | 1.000 |
| observed exploratory SDs (3 games each) | 156.6 / 114.3 | 25.03 | 70.1 | 0.999 | 1.000 |
| 80% upper bound of the pooled exploratory SD (4 df) | 213.6 / 213.6 | 38.99 | 109.2 | 0.917 | 1.000 |
| 80% upper bound of each seat's SD (2 df) | 331.6 / 242.0 | 53.00 | 148.5 | 0.692 | 0.998 |
| 95% upper bound of each seat's SD (2 df) | 691.6 / 504.8 | 110.54 | 309.7 | 0.219 | 0.656 |

Normal-approximation power of a two-sided 5% test. The simulation in section 5 gave matching power for the
registered interval itself: 0.66 to 0.67 at half the exploratory estimate under the 80% per-seat bounds, and at
least 0.999 under the observed SDs. Three observations per seat estimate a standard deviation imprecisely: the
95% bound is 4.4 times the estimate. The exploratory estimate comes from games selected for promise and is likely
overstated, which is why half of it is the planning effect.

Secondary planning, assuming the candidate's SD equals the control's: phase C seat averages detect about 300.0
(2120531121) and 231.8 (1930331196) with 80% power. Phase B detects 51.3 (2120531121 C2), 15.2 (2120531121 C3), 12.6
(2130511121 C2), 33.9 (2130511121 C3) and 4.2 (1930331196 C2). In 1930331196 C3 and all ten phase-D
configurations, `baseline-v2`'s margin against the inert control was the same in all 15 historical games.

## 7. Phase gates and stopping

Each gate is computed by `scripts/t9_confirmation_analysis.py phase --phase X`, committed as
`evaluation/t9-confirmation-1/phase-X.json`, and applied mechanically: no game is added, no candidate changes, no
scenario is substituted.

| Gate | CONTINUE only if | Otherwise |
|---|---|---|
| A | all 45 games completed and accounted for; integrity holds (section 11); no systemic failure; the primary interval's lower limit is strictly above 0 | STOP: a failed or inconclusive primary result is a valid outcome |
| D | all 60 games completed; integrity holds; no systemic failure; no configuration's mean margin difference (candidate minus `baseline-v2`, candidate seat) is below -10 | STOP; an adverse margin signal gives NEEDS_REVISION |
| B | all 180 games completed; integrity holds; no systemic failure; no configuration's interval upper limit is below -10 | STOP; an adverse signal gives NEEDS_REVISION |
| C | (last phase) completion, integrity and systemic failures are reported | the study ends |

* Systemic failure: any contract error, project-gate rejection, replay mismatch, add-on error (the add-on fell
  back to `baseline-v2`) or observer error in any seat. Also a factual refusal class (action, code, message) in a
  candidate seat that is neither one of `baseline-v2`'s four known classes nor seen in a `baseline-v2` seat of this
  study.
* The -10 threshold is the project's established tactical margin (shoot-reservation experiment P7). Measured on
  `baseline-v2`'s own historical games, drawing both arms from them 2,000 times per configuration, the phase D
  rule never fired and the phase B rule fired in at most 0.35% of draws.
* Phase D gives 3 games per arm. Its gate is a screen for a material adverse signal; it does not show that a loss
  of 10 points or more is ruled out in any configuration. Each configuration reports the mean difference, both
  arms' values, the range of pairwise differences and, where the arms vary, the Welch interval.
* An ordinary tactical loss is an outcome. A systemic failure is an engine, contract or candidate malfunction
  (above); the gate treats them separately.

## 8. Secondary estimands and multiplicity

* Phase A: the two seat contrasts (H1 red minus C1 red, H2 blue minus C1 blue), each with the registered interval.
* Phase B: per large scenario and condition, mean candidate margin minus mean `baseline-v2` margin against the
  inert control, two strata (6 contrasts).
* Phase C: per scenario, the primary-form seat average and the two seat contrasts.
* Phase D: as in section 7.
* All secondary analyses are descriptive. No multiplicity adjustment is applied because no secondary claim is
  confirmatory, and no secondary result can stand in for the primary endpoint. Configurations are never pooled:
  scenarios and seats differ by hundreds of points in level and spread. The disposition summarises generality only
  by counts of the 8 secondary configurations of B and C whose estimate, or whose interval, lies above or below 0.

## 9. Mechanism and safety observations

The study's read-only capture (`t9_confirmation.T9Capture`) records, for every policy seat of every game (the
candidate's and `baseline-v2`'s), descriptively:

* move orders emitted, kept, re-assigned, reverted and withheld, and re-assigned moves the engine refused;
* withheld units, withheld unit-decisions and each unit's longest run of consecutive withheld decisions;
* ground units idle at their start hex: count never leaving it, idle unit-steps, the longest idle time, units idle
  for half the play stage or more;
* ground units waiting in front of full hexes;
* the largest objective commitment;
* objectives held over the play stage, at the end and value-weighted;
* units lost.

From the records: score components, refusal classes, contract errors, gate rejections and decision latency. The
known T9 risk, units withheld at their start while every objective is at capacity, is read from the withholding
and start-position counts beside each arm's margins and objectives held; whether a score gain reflects fewer
deadlocks, a different spread over objectives or something else is a descriptive reading of these counts.

Descriptive flags, never a stop on their own:

* latency: a candidate configuration's largest per-game p99 above 10 ms, or any decision above 5,000 ms. In
  Sprint 8 (`evaluation/s8-t9-v1-*/results.json`) the candidate's per-game p99 reached 2.798 ms, against 1.217 ms
  for `baseline-v2` over all its decisions in the shoot-reservation experiment, and its maximum reached 1,156.9 ms
  in a GC tail, so a ratio rule would fire on correct behaviour;
* idle: against the inert control, the candidate's mean count of ground units that never leave their start hex
  exceeds `baseline-v2`'s by 1 or more;
* objectives: the candidate's mean objectives held at the end are 0.5 or more below `baseline-v2`'s.

## 10. Failure handling and intent to treat

* No game is retried, replaced or added, and no record or capture is overwritten.
* A game that does not complete (FAIL, CAPPED, interrupted, missing record) keeps whatever it recorded and fails its
  phase's gate. The primary is then NOT TESTED; figures over the completed games are labelled descriptive. A
  non-completed C1 game would change no seat-average figure.
* A started game without a record, a recovered session, an installation refusal or 3 consecutive games that did not
  complete stop dispatch (the qualified scheduler's rules), and the phase's gate fails.
* A missing or digest-mismatched capture of a completed game leaves its margin in the analysis but fails integrity,
  so the gate fails.
* Any change of a pinned file refuses every later game. An execution-affecting change needs a new registration.

## 11. Integrity checks

Each check refuses the gate:

* Ledger. Every session after 2487 is a scheduled game of this study under the registered manifest, opened once,
  closed with integrity ok, opened with the previous record's state; none unclosed; the cap holds.
* Records. Each carries the manifest digest, a clean harness, the study id, the registered policy sources, the
  runtime and its thread variable, a shared session of 32 workers under the qualified scheduler, engine 4.1.0,
  CPython 3.10 and session-close integrity ok; its session equals the ledger's for its game.
* Captures. Both capture files match the digests the record carries. The study's capture agrees with Sprint 8's
  exploratory capture, which runs beside it unchanged (waiting units, largest commitment, add-on changes and
  skips), and with the record (move orders, steps): two independently produced counts.
* Margins. Every completed game's margin equals the engine's `<side>_win` for both sides.

## 12. Validation before registration

* Synthetic tests (`tests/test_t9_confirmation.py`): schedule and balance, margins, the interval procedure,
  strata, the ledger audit, record identities, systemic checks, every gate and the disposition.
* The capture on hand-built states and on the PS-1 stand-in engine through the real game loop with the real
  candidate. There the candidate withheld six idle units for 55 consecutive decisions each, and both captures
  agreed.
* A dry run of the full 375-game schedule through every phase's registered analysis on synthetic records.
* Mutation testing (`scripts/mutate_t9_confirmation.py`, `mutation.json`).
* Real records (`validation.json`):
  * Rehearsal. The registered extraction and phase-A contrasts were run on the six Sprint 8 games of the candidate
    in 2130511121 and the 15 historical C1 games. Every margin equals the exploratory reports' and the engine's
    `<side>_win`, and every C1 value of c is 0. The estimate equals the planning's 261.0; the studentized interval
    over those 3 + 3 games is 55.1 to 407.9. This is a rehearsal, not a result: these games are never pooled into
    the study. The record-identity check rejected all 21 records, which belong to other registrations.
  * Capture replay. Both captures were fed with the real all-seeing states of the T7 probe's two head-to-head
    games (2120531121, every decision), the candidate deciding offline for the `baseline-v2` seat. Their common
    counts agree and the other seat's move orders equal its record's. In both games the value of the objectives
    each side holds at the end equals that side's occupy score in the engine's final scores (310 for blue, 0 for
    red), and the capture's figure for the replayed seat equals it.
* The pre-registration check itself found one defect before any session: real records hold project-gate
  rejections as a reason-to-count mapping, not a number. The rehearsal stopped on it, and the extraction and the
  synthetic records were corrected.

## 13. Disposition

* PRIMARY_SUPPORTED: primary SUPPORTED and every phase that ran without a systemic failure or adverse signal.
* PRIMARY_SUPPORTED_NEEDS_REVISION: primary SUPPORTED, but a later phase had a systemic failure or adverse signal.
* PRIMARY_NOT_SUPPORTED: primary tested and its lower limit not above 0; the study stops after phase A.
* INCONCLUSIVE_PROTOCOL_INCOMPLETE: primary not tested.

The disposition (`disposition.json`) also reports safety per phase (CLEAN, ADVERSE_SIGNAL, SYSTEMIC_FAILURE,
NOT_REACHED), the flags, generality counts from B and C, and the mechanism summaries.

* A supported primary result holds for 2130511121 head to head against `baseline-v2` only; it is not evidence of
  an improvement across scenarios.
* A successful local confirmation does not change the production baseline. A separate promotion decision must keep
  `baseline-v2` frozen as the reference and weigh the remaining platform compatibility evidence.

## 14. Not claimed; limitations

* Not claimed:
  * an improvement against stronger or external opponents, or on the platform;
  * an across-scenario improvement from a positive phase A;
  * that phase D rules out a 10-point loss;
  * a promotion.
* The planning SDs of the candidate rest on 3 exploratory games per seat.
* The studentized bootstrap with 15 games per stratum is an approximation, measured in section 5.
* 32 concurrent shared sessions lengthen decision-latency tails relative to serial play; latency is compared
  within the study only.

## 15. Separate workstreams

* Platform canary. The frozen `baseline-v2` canary `dist/miaosuan-baseline-v2-canary.zip` (SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`) is prepared for the owner's manual upload to an
  AI test slot, never the official slot, following `docs/PLATFORM_CANARY.md`. Platform logs or replays, if
  returned, are classified as compatibility or tactics apart from this study's local estimates. The candidate is
  not uploaded.
* T4 stays shelved and T7's dispositions stand. No session of this study is spent on them.

## 16. Running and analysing

```
python scripts/build_t9_confirmation_manifest.py --check
PYTHON scripts/run_t9_confirmation.py --python PYTHON --sdk-archive ZIP --phase A
python scripts/t9_confirmation_analysis.py phase --phase A
python scripts/t9_confirmation_analysis.py disposition
```

`PYTHON` is the interpreter of the `miaosuan-runtime` environment on the evaluation server. Each later phase is
run only after the previous phase's file is committed and permits it.

## Results

Every figure below comes from the committed phase files (`evaluation/t9-confirmation-1/phase-X.json`), which
`scripts/t9_confirmation_analysis.py phase --phase X --check` regenerates byte for byte from the private records,
captures and ledger. Margins are engine score points.

### Registration and execution

* The registration (`48861fa`) was pushed, and public issue #4 was created at 2026-10-03T22:09:19+08:00. It was
  fetched without authentication at 22:09:32+08:00 with a byte-identical body (12,880 bytes, SHA-256
  `bd98685185a65618fd0f4811ca916719fdd07e3cddc386753b1b8590453cd98b`; `registration-verification.json`).
* The first session of the study opened about one minute later, from harness commit `e4ac08c`, which adds only
  the issue record to the registration. The time is corrected for the host clock's recorded offset
  (`docs/ENGINE_INSTALL.md`).
* Before the first session, the real game entry point was also run on the server with the registered manifest and
  staged inputs against the PS-1 stand-in, with the session API replaced in-process: no engine, no ledger record.
  It played three phase-A games, wrote records and captures that passed the cross-checks, and refused a phase-D
  game for want of a committed gate.

### Phase A (primary)

* All 45 games completed, in sessions 2488 to 2532, with 32 workers. Each game took 114.6 to 163.6 s.
* Integrity held: the ledger audit, every record's identities, both capture digests and the cross-checks. Every
  margin equalled the engine's `<side>_win`.
* No systemic failure: contract errors, project-gate rejections, replay mismatches, add-on errors and observer
  errors were all 0, and no new refusal class appeared.

Margins by game, in schedule order:

| Cell | Margins (H1 and C1: red; H2: blue) |
|---|---|
| H1 | -1,003, -963, -597, -361, -827, 1,035, -967, -871, -737, -393, -755, -743, -721, -133, 709 |
| H2 | 1,283, 973, 1,045, 1,081, 1,101, 1,061, 865, 1,391, 1,105, 1,033, 1,055, 1,435, 899, 953, 1,211 |
| C1 | -919, -817, -1,021, -971, -1,163, -569, -661, -1,195, -1,079, -365, -217, -917, -709, -1,003, -1,191 |

| Estimand | Estimate | 95% interval (registered) | Percentile | Welch |
|---|---|---|---|---|
| Delta, seat average (primary) | 305.47 | 172.87 to 611.24 | 168.60 to 467.73 | 133.43 to 477.50 |
| Red: H1 minus C1 | 364.67 | 65.60 to 881.46 | 56.80 to 709.60 | 1.37 to 727.96 |
| Blue: H2 minus C1 | 246.27 | 84.67 to 456.59 | 88.13 to 417.07 | 64.05 to 428.48 |

* Strata. H1 red mean -488.47 (SD 606.51), H2 blue mean 1,099.40 (SD 166.37), C1 red mean -853.13 (SD 296.85).
  The value c = (red + blue) / 2 was 0 in all 15 C1 games, as the convention implies.
* **Primary: SUPPORTED.** The registered interval's lower limit, 172.87, is above 0, so gate A says CONTINUE. Both
  sensitivity intervals also lie above 0.
* Two of the 15 H1 games were won by the candidate as red (1,035 and 709), a side that lost every C1 game. They
  make the H1 spread large and the registered interval asymmetric.
* The fresh C1 games varied more than the historical ones (SD 296.85 against 114.66); their mean, -853.13, is close
  to the historical -869.93.

Mechanism (descriptive; means per game):

| Seat | Ground moves emitted | Kept / re-assigned / withheld | Withheld units (longest run) | Largest commitment | Waiting unit-steps | Objectives held at the end (value) | Units lost |
|---|---|---|---|---|---|---|---|
| candidate red (H1) | 47.33 | 22.33 / 25.00 / 758.33 | 6.60 (91.07) | 4.00 | 190.00 | 1.27 (75.33) | 29.80 |
| `baseline-v2` red (C1) | 62.87 | - | - | 16.00 | 754.87 | 0.33 (16.67) | 32.73 |
| candidate blue (H2) | 38.93 | 7.80 / 31.13 / 14,803.93 | 20.27 (1,236.00) | 4.00 | 0.40 | 7.00 (440.00) | 10.20 |
| `baseline-v2` blue (C1) | 85.53 | - | - | 17.00 | 13,994.60 | 6.67 (423.33) | 15.00 |

* Re-assigned moves: none reverted, none refused by the engine.
* Start positions: in every game of every arm the same ground units left their start hexes at the same steps
  (25 of 31 red, 26 of 32 blue); 6 per side never moved under either policy. The candidate never withheld a unit
  at its start position in this scenario. Its withholding, about 20 units per game as blue for runs of up to
  1,236 consecutive decisions, fell on units that had already left.
* A reading of these counts, descriptive only: the candidate removed the queues in front of full objective hexes
  almost entirely (waiting unit-steps 0.40 against 13,994.60 as blue; 190.00 against 754.87 as red). It held more
  objectives at the end (1.27 against 0.33 as red; 7.00 against 6.67 as blue) and lost fewer units. This study
  cannot separate fewer deadlocks from a different spread over objectives.
* Refusals: the candidate 7 code-516 shots (as blue); `baseline-v2` 6 code-516 and 4 code-203 shots, all known
  classes.
* Latency: the candidate's largest per-game p99 was 3.421 ms and its maximum 961.5 ms; `baseline-v2`'s were
  2.069 ms and 311.2 ms. No decision exceeded 1 s, and no flag was raised.

### Phase D (safety screen)

* All 60 games completed, in sessions 2533 to 2592. Integrity held, there was no systemic failure, and no flag was
  raised. The gate says CONTINUE.
* In all ten configurations both arms gave the same margin in all three games, the margin of the historical
  control:

| Scenario | C2: red's margin, both arms | C3: blue's margin, both arms |
|---|---|---|
| 2010211129 | 264 | 128 |
| 2010431153 | 102 | 158 |
| 1910631192 | 102 | 158 |
| 2010131194 | 50 | 210 |
| 201033019601 | 80 | 80 |

* The difference is 0 in every configuration, with no spread in either arm. That is no adverse signal, but three
  identical games per arm are not a proof of non-inferiority in general.
* The rule acted in two configurations without changing the outcome. In 1910631192 C3 it re-assigned 2 moves and
  withheld 324 unit-decisions per game (2 units); in 2010211129 C3 it withheld 121 (1 unit). Everywhere else it
  kept every move.
* Latency: the candidate's largest p99 was 0.715 ms, `baseline-v2`'s 0.37 ms.

### Phase B (secondary, against the inert control)

* All 180 games completed, in sessions 2593 to 2772. Each game took 106.5 to 250.0 s.
* Integrity held and there was no systemic failure. The refusals were 14 code-516 shots, all in `baseline-v2`
  seats.
* **Gate B: STOP.** Two configurations crossed the registered adverse threshold: their interval's upper limit lies
  below -10.
* Phase C was therefore not run, and its 90 sessions stay unused.

Candidate margin minus `baseline-v2` margin, candidate seat (C2: red, C3: blue), 15 games per arm:

| Configuration | Candidate mean (SD) | `baseline-v2` mean (SD) | Difference | 95% interval (registered) | Percentile | Welch | Signal |
|---|---|---|---|---|---|---|---|
| 2120531121 C2 | 516.73 (11.05) | 363.67 (40.47) | +153.07 | 130.78 to 177.14 | 132.53 to 173.60 | 130.11 to 176.02 | - |
| 2120531121 C3 | 519.00 (0.00) | 587.67 (14.07) | -68.67 | -75.25 to -57.30 | -74.67 to -61.33 | -76.46 to -60.87 | adverse |
| 1930331196 C2 | 226.00 (0.00) | 272.93 (4.13) | -46.93 | -48.26 to unbounded | -48.00 to -44.80 | -49.22 to -44.65 | (see below) |
| 1930331196 C3 | 457.47 (34.88) | 568.67 (5.16) | -111.20 | -130.10 to -90.92 | -128.40 to -94.00 | -130.65 to -91.75 | adverse |
| 2130511121 C2 | 900.73 (52.90) | 782.33 (14.86) | +118.40 | 87.80 to 147.66 | 91.20 to 144.80 | 88.35 to 148.45 | - |
| 2130511121 C3 | 603.93 (51.84) | 636.87 (27.94) | -32.93 | -63.61 to 0.68 | -61.73 to -4.00 | -64.51 to -1.36 | - |

* The unbounded limit in 1930331196 C2 is a defect of the registered procedure in a nearly degenerate case. The
  candidate scored 226 in all 15 games, and `baseline-v2` 274 in 14 and 258 in one. Every bootstrap resample
  without that one game has zero spread and a different estimate, which the registered rule turns into an infinite
  t*; the upper limit therefore went to infinity.
* Under the registered rule this configuration is not an adverse signal. Read directly, it is a deterioration of
  about 47 points, which both sensitivity intervals place below -10. The gate decision is the same either way.
  The pre-registration checks measured the B rule's false alarms with both arms drawn from `baseline-v2`'s games and
  never met an arm without spread; that gap is recorded here, after the results, and nothing was re-decided.
* Where the margins moved, by score component (means per game; against the inert control the margin is own occupy
  + own attack + own remaining value - the inert side's remaining value):
  * 2120531121 C3: the candidate held 4 objectives at the end of every game, `baseline-v2` 5 (occupy 230 against
    310). The objective flag was raised.
  * 1930331196 C3 and C2: objectives and own losses equal; the candidate destroyed less of the inert side (attack
    31.7 against 87.3, and 0 against 23.5).
  * 2130511121 C3: attack 60.5 against 76.9.
  * The gains, 2120531121 C2 and 2130511121 C2: attack 139.9 against 63.3, and 251.9 against 192.7, with objectives
    equal.
* Mechanism (descriptive, candidate arm, means per game). The largest commitment was 4 in every configuration,
  against 11 to 23 for `baseline-v2`, and waiting in front of full hexes nearly vanished (at most 62 unit-steps,
  against 5,852 to 35,422).
  * Withholding was heaviest as blue: 29,265.27 withheld unit-decisions with 12 units in 2120531121 C3, 28,332 with
    21 units in 2130511121 C3, 1,722 with 10 units in 1930331196 C3; the longest runs averaged 2,499.20 and 1,712
    decisions in the first two.
  * As in phase A, start positions were identical in both arms of every configuration: withholding fell on units
    that had already left their start.
* Latency: the candidate's largest p99 was 3.578 ms and its maximum 1,638.5 ms (26 decisions over 1 s);
  `baseline-v2`'s were 2.338 ms and 1,574.8 ms (14 over 1 s). These are GC-tail spikes under 32 concurrent games;
  no latency flag was raised.

### Disposition and next step

The registered disposition (`disposition.json`) is **PRIMARY_SUPPORTED_NEEDS_REVISION**.

* **Primary, supported in the tested scenario.** In 2130511121 head to head against `baseline-v2` the candidate
  improved the seat-averaged terminal margin by 305.47 points (95% interval 172.87 to 611.24). It did so in both
  seats.
* **Generality: not supported.**
  * The candidate gained against the inert control as red in 2120531121 and 2130511121, with intervals above 0.
  * It lost as blue in 2120531121 and 1930331196, with intervals below -10, and by about 47 points as red in
    1930331196.
  * 2130511121 C3 is inconclusive (-32.93; interval -63.61 to 0.68).
  * The head-to-head phase C in the other two scenarios was not reached.
  * Counts over the six B configurations: estimate above 0 in 2, interval above 0 in 2, interval below 0 in 2.
* **Mechanism (descriptive).**
  * The rule does what it was built to do: commitments capped at 4, queues in front of full hexes nearly gone,
    re-assigned moves accepted. Head to head, the gain came with more objectives held at the end and fewer units
    lost.
  * Its cost is long withholding of units that have left their start: up to about 2,500 consecutive decisions on
    average as blue in 2120531121. With it come one missed objective (2120531121 C3) and less fire on the inert
    side (1930331196).
  * The known risk took a different form from the one feared: no unit was ever held at its start position.
* **Safety.**
  * No systemic failure in 285 games: no contract error, gate rejection, replay mismatch, add-on error or new
    refusal class, every game completed and the ledger stayed intact.
  * The small-scenario screen found no deterioration (identical margins).
  * The adverse signals are tactical outcomes, not engine or contract failures.
* **External platform: none.** No platform evidence exists; the canary has not been uploaded.

No baseline is promoted; `baseline-v2` stays the frozen reference. The candidate is not changed by this study.

Recommended next step (one): an exploratory diagnosis of the two adverse configurations against the inert control,
2120531121 C3 and 1930331196 C3. Both are nearly deterministic, so a captured diagnostic game of each arm per
configuration, under a run card, can show why the 80-point objective is never taken under long withholding and why
fire on the inert side drops. Only then should a revised candidate, such as one that releases withheld units while
an objective outside own control remains untaken, be written, under a new identity and its own exploratory batch.

### Deviations and disclosures

* None in execution: every phase ran from a clean committed tree under the registered manifest, in the registered
  order, with no retry, replacement or added game. Sessions used: 285 of the 375 cap (2488 to 2772).
* The degenerate interval in phase B (above) is a limitation of the registered procedure, disclosed after the
  results; the gate decision does not depend on it.
* The phase files store that unbounded limit as `Infinity`, which Python's JSON reader accepts but strict JSON does
  not.
* Before the push, the server's full private suite ran on the first registration commit, `816c16b`: 1,256 of 1,258
  tests passed. The 2 errors were a defect of the new regeneration test itself (multiprocessing could not import the
  scripts it loaded under another name). The test was fixed in `48861fa`, which also re-pinned the manifest, and the
  affected test modules (79 tests) passed on the server before the registration was pushed. The full private suite
  was run again at close-out.
