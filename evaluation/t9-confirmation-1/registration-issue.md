**CONFIRMATORY STUDY, STAGED: at most 375 engine sessions; registered before the first session; not eligible for promotion**

Preregistration record of Sprint 9: the confirmatory study of the T9 capacity-allocation candidate (`docs/T9_CONFIRMATION.md`). Created before any engine session of this study.

## Question
Does t9-capacity-allocation-v1, unchanged from Sprint 8, improve baseline-v2's terminal score margin head to head in scenario 2130511121, and is it free of systemic failures and of material deterioration where its rule rarely binds?

## Hypothesis
In scenario 2130511121 head to head, the equally seat-weighted improvement of the candidate's terminal margin over fresh baseline-v2 C1 mirror margins of the same seat is greater than 0.

## Frozen identities
- Manifest `evaluation/t9-confirmation-1/manifest.json`, canonical SHA-256 `28324b3a6742f8fe8b4a7938b03f0077e894be701ce06527543cf81df043981c`; design digest `028ebf57a55e8ad00624f66de449b164fa4b44ca45c9f520ba65e4217ad15576`
- Candidate `t9-capacity-allocation-v1`, capacity 4, detour factor 2, policy source `0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa` (Sprint 8, unchanged)
- Control `baseline-v2-candidate-shoot-target-reservation` (baseline-v2), policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`; inert control `inert-v0`
- Runtime `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), 32 workers, qualified scheduler `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90`; SDK 4.1.0, CPython 3.10
- Every implementation and test file pinned by normalised SHA-256 in the manifest (19 files, 4 test files); pre-registration outputs pinned likewise
- Registration commit `48861fa6cfa33c8efee5639baaeda53ba8b1c575`

## Design (each phase only after the previous phase's gate says CONTINUE)
- **A**, primary: scenarios 2130511121; cells H1, H2, C1; 15 games per cell; 45 sessions
- **D**, safety screen: scenarios 2010211129, 2010431153, 1910631192, 2010131194, 201033019601; cells C2-T9, C2-V2, C3-T9, C3-V2; 3 games per cell; 60 sessions
- **B**, secondary (robustness against the inert control): scenarios 2120531121, 1930331196, 2130511121; cells C2-T9, C2-V2, C3-T9, C3-V2; 15 games per cell; 180 sessions
- **C**, secondary (robustness head to head): scenarios 2120531121, 1930331196; cells H1, H2, C1; 15 games per cell; 90 sessions
- Budget: at most 375 sessions after ledger session 2487; a ceiling, checked before each phase and by each game
- Schedule: each round plays every cell once, in a hash-derived base order rotated by one per round (in phase A every cell takes every position of a round exactly five times)
- Seeds: `global_seed` 20260929, `PYTHONHASHSEED` 0; the engine's own randomness is not controlled by them; games are independent, not seed-matched

## Margin convention and primary estimand
- a seat's terminal margin is its side's <side>_total minus the other side's total in the engine's final scores (the engine's own <side>_win, checked per game); it is zero-sum, so in a C1 game the blue margin is minus the red margin
- Delta = 1/2 (mean H1 red margin - mean C1 red margin) + 1/2 (mean H2 blue margin - mean C1 blue margin) over the 45 phase-A games; computed as 1/2 mean(H1) + 1/2 mean(H2) - mean(c) with c = (red + blue) / 2 per C1 game, so each C1 game is one unit carrying its correlated pair of seat outcomes; under the margin convention c = 0 for every game, so the C1 games cancel from Delta and from every resample (a property of the data, checked per game)
- Interval: 95% studentized bootstrap (bootstrap-t) interval: the H1, H2 and C1 strata are resampled independently with replacement at the game level (C1 games as pairs), 20,000 resamples, seed derived from 20261003 and the estimand's name, nearest-rank quantiles of t* = (Delta* - Delta) / SE*, SE the plug-in standard error sqrt(sum w^2 s^2 / n); the percentile interval of the same resamples and the Welch interval are reported as non-decisive sensitivity
- Test: tested once, after all 45 phase-A games, only if every game completed and integrity holds; SUPPORTED if the interval's lower limit is strictly above 0
- Seat contrasts: secondary, descriptive: H1 red minus C1 red and H2 blue minus C1 blue, each with the same interval procedure (C1 resampled by game)

## Power (planning.json)
- Historical C1 SD (2130511121, sample) 114.66; exploratory candidate SDs 156.63 (red) and 114.33 (blue); exploratory estimate 261.0
- conservative: 80% upper confidence bound of each seat's exploratory SD (2 df): SE 53.00, 80% MDE 148.5; power 0.692 at 0.5 x exploratory estimate (130.5), 0.998 at 1 x exploratory estimate (261.0)
- conservative: 80% upper confidence bound of the pooled SD (4 df): SE 38.99, 80% MDE 109.2; power 0.917 at 0.5 x exploratory estimate (130.5), 1.000 at 1 x exploratory estimate (261.0)
- observed exploratory standard deviations per seat (3 games each): SE 25.03, 80% MDE 70.1; power 0.999 at 0.5 x exploratory estimate (130.5), 1.000 at 1 x exploratory estimate (261.0)
- optimistic: both seats at the historical C1 standard deviation: SE 20.93, 80% MDE 58.7; power 1.000 at 0.5 x exploratory estimate (130.5), 1.000 at 1 x exploratory estimate (261.0)
- pooled exploratory standard deviation (6 games, 4 df): SE 25.03, 80% MDE 70.1; power 0.999 at 0.5 x exploratory estimate (130.5), 1.000 at 1 x exploratory estimate (261.0)
- very conservative: 95% upper confidence bound of each seat's exploratory SD (2 df): SE 110.54, 80% MDE 309.7; power 0.219 at 0.5 x exploratory estimate (130.5), 0.656 at 1 x exploratory estimate (261.0)

## Calibration of the interval procedure (validation.json)
- Null one-sided error of 'lower limit above 0' over 6 cells of 2000 simulated analyses: studentized (registered) 0.0150 to 0.0260; percentile 0.0345 to 0.0435; Welch 0.0240 to 0.0355 (nominal 0.025)

## Phase gates
- **A**: CONTINUE to D only if all 45 games completed and are accounted for, integrity holds (ledger, record identities, capture digests and cross-checks), there is no systemic failure (contract errors, project-gate rejections, replay mismatches, add-on errors, observer errors, a candidate refusal class unknown to baseline-v2) and the primary interval's lower limit is strictly above 0; otherwise STOP
- **D**: CONTINUE to B only if all 60 games completed, integrity holds, there is no systemic failure and no configuration's mean margin difference (candidate minus baseline-v2) is below -10 (adverse signal); otherwise STOP with the safety result recorded (NEEDS_REVISION for an adverse signal)
- **B**: CONTINUE to C only if all 180 games completed, integrity holds, there is no systemic failure and no configuration's interval upper limit is below -10 (adverse signal); otherwise STOP
- **C**: the last phase: completion, integrity and systemic failures are reported; no further games
- Flags: descriptive, never a stop on their own: latency (a candidate configuration's largest per-game p99 above 10 ms or any decision above 5,000 ms), idle (against the inert control, the candidate's mean count of ground units that never leave their start hex exceeds baseline-v2's by 1 or more) and objectives (the candidate's mean objectives held at the end are 0.5 or more below baseline-v2's)

## Secondary analyses
- phase B: per large scenario and condition (C2, C3), mean candidate margin minus mean baseline-v2 margin against the inert control, studentized bootstrap interval with the two arms as strata (6 contrasts)
- phase C: per scenario (2120531121, 1930331196), the primary-form seat-average contrast and the two seat contrasts, as in phase A
- phase D: per small scenario and condition, the mean difference, each arm's values, the range of pairwise differences and the Welch interval where defined (3 games per arm: an estimate, not a test)
- all secondary analyses are descriptive: no multiplicity adjustment is applied because no secondary claim is confirmatory; no secondary result can replace the primary endpoint; configurations are never pooled

## Failure handling
- no game is retried, replaced or added; records and captures are never overwritten
- a game that does not complete (FAIL, CAPPED, interrupted, missing record) keeps its record and fails its phase's gate; the primary is then NOT TESTED and its figures over completed games are labelled descriptive; a non-completed C1 game would change no seat-average figure (its contribution is 0)
- a started game without a record, a recovered session, an installation refusal or 3 consecutive games that did not complete stop dispatch (the qualified scheduler's rules); the phase's gate fails
- a missing or digest-mismatched capture of a completed game leaves its margin in the analysis and fails the phase's integrity, so the gate fails
- an execution-affecting code change needs a new registration; no phase runs with a pinned file changed
- the cumulative cap of 375 sessions after ledger session 2487 is checked before each phase and by each game

## Integrity (each check refuses the gate)
- every session after ledger session 2487 belongs to a scheduled game of this study under the registered manifest, is opened once, closed with integrity ok, and continues the previous record's state; none unclosed
- every record carries the manifest digest, a clean harness, the study id, the registered policy sources, runtime baseline-v1-runtime-r2 with OPENBLAS_NUM_THREADS=1, a shared session of 32 workers under the qualified scheduler, engine 4.1.0, CPython 3.10 and session-close integrity ok; its session equals the ledger's for its game
- both capture files of a completed game match the digests its record carries, and the study's capture agrees with the Sprint 8 exploratory capture (waiting units, largest commitment, add-on changes and skips) and with the record (move orders, steps)
- the margin of every completed game equals the engine's <side>_win for both sides

## Mechanism (descriptive)
per policy seat (descriptive): move orders emitted, kept, re-assigned, reverted and withheld, refused re-assigned moves; withheld units and their longest run of consecutive withheld decisions; ground units idle at their start hex (count never departed, unit-steps, maximum, units idle half the play stage or more); units waiting in front of full hexes; largest objective commitment; objectives held over time, at the end and value-weighted; units lost; refusal classes; contract errors, gate rejections, add-on errors; decision latency

## Disposition
- PRIMARY_SUPPORTED: primary SUPPORTED and every phase that ran CLEAN (no systemic failure, no adverse signal)
- PRIMARY_SUPPORTED_NEEDS_REVISION: primary SUPPORTED but a later phase had a systemic failure or adverse signal
- PRIMARY_NOT_SUPPORTED: primary tested, lower limit not above 0 (a valid outcome; the study stops)
- INCONCLUSIVE_PROTOCOL_INCOMPLETE: primary not tested (incomplete phase A or integrity failure)
- generality is reported descriptively from phases B and C (counts of configurations with estimates and intervals above or below 0); mechanism and flags are descriptive; no outcome promotes a baseline

## Validation before registration
- Mutation testing: 42 of 42 mutants of the analysis killed
- Rehearsal on 21 real records (Sprint 8 games and historical C1 games; never pooled): problems 0; the record-identity check rejected 21 of them (other registrations)
- Capture replay on the real states of two captured head-to-head games: 2120531121.H1.pb1 agrees; 2120531121.H2.pb2 agrees
- Gate false alarms on baseline-v2's own historical games: at most 0.0035

## Not claimed
- an improvement against stronger or external opponents, or on the platform
- an across-scenario improvement from a positive phase A
- that 3 games per arm in phase D rule out a loss of 10 points or more in any configuration
- a baseline promotion: a separate decision must keep baseline-v2 frozen as the reference and weigh the platform compatibility evidence

## Limitations
- the engine's own randomness is not documented as controllable: games are independent samples, not seed-matched, although the harness seeds Python's and NumPy's global generators
- the planning standard deviations of the candidate rest on 3 exploratory games per seat
- a percentile or studentized bootstrap with 15 games per stratum is an approximation; its null error and power were measured by simulation before registration (validation.json)
- 32 concurrent shared sessions (the qualified configuration) lengthen decision-latency tails relative to serial play; latency is compared within the study only

## Separate workstreams
the frozen baseline-v2 platform canary (a3d3b022...) is prepared for the owner's manual upload to an AI test slot; platform observations never enter this study's estimates; T4 stays shelved and T7's dispositions stand; no session of this study is spent on them
