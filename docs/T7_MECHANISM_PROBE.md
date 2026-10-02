# T7 idle concealment: registered engine mechanism probe

**MECHANISM PROBE.** At most three diagnostic engine sessions; no tactical A/B, no promotion, no platform upload,
nothing here can change a baseline. This document is the protocol of `t7-mechanism-probe-1` (Tactical Frontier Sprint
6), approved by the owner on the design of `docs/T7_SCREEN_PROPOSAL.md`. Sections 1 to 14 were written and pushed,
with the manifest, the candidate and every analysis, before the first session; later sections are written afterwards
and say so. Times are UTC+8.

## 1. Questions

1. **P-A, deterministic mechanism and non-interference.** In the deterministic configuration of Sprint 2 game `b`,
   does engine 4.1.0 accept a concealment order (action 6, `target_state` 4) from an idle, stationary own ground unit
   that `baseline-v2` leaves without an action (E1), complete the documented 75-second transition into `move_state` 4
   (E2), keep the unit's listed actions (E3), and change nothing else in the game (E6), without an engine error (S1),
   a locked unit (S2) or any departure from the reference game's `baseline-v2` actions and outcome (S3)?
2. **P-B1 and P-B2, active opponent.** Against `baseline-v2` in scenario 2120531121, once in each seat: does a
   completed concealment halve the distance at which the opposing seat lists the unit (E4), and what happens when a
   concealed or transitioning unit is ordered to move or fire, or is suppressed (E3, E5)?
3. **Disposition.** With these answers and the registered rules, which research disposition does T7 idle concealment
   receive?

The primary metric is the share of issued concealment orders that reach the concealed state within 76 steps
(section 9). Three games cannot measure tactical efficacy and this probe does not try.

## 2. Starting evidence and disclosure

Sprint 5 (`docs/T7_DESIGN.md`) selected the mechanism, specified it (section 14) and checked a shadow of it offline;
its gates ended in `READY_FOR_MECHANISM_PROBE` and the proposal of this probe. Before this protocol, and with no new
engine session, the following were read or computed:

* **The reference game.** Sprint 2 game `b` (`1910631192.C3.b.x01`, session 2459; inert red, `baseline-v2` blue),
  whose record and capture (the all-seeing state and the blue observation at every decision from index 1) are
  private and pinned by digest in the manifest. A read-only exploration of it (private record
  `local/diagnostics/t7-probe/explore-game-b.txt`) found that its blue seat never lists an enemy unit and that from
  decision 717 on `baseline-v2` gives none of the four units the candidate would order any action, so P-A is not
  expected to produce E3b, E4 or E5 events.
* **Premise** (`scripts/t7_probe_analysis.py premise`, `evaluation/t7-mechanism-probe-1/premise.json`): the registered
  candidate replayed over the reference game's 1,800 blue observations makes `baseline-v2`'s recorded decision at
  every one (actions and trace digest) and orders concealment first at decision index 717 (cur_step 716) to two
  units, then at 736 (cur_step 735) to two more units of the same hex. The summary "first orders at 717, four units"
  of the proposal and the sprint brief joins these two decisions; this protocol registers both. On the recorded
  trajectory, where no unit ever concealed, the replay issues 60 orders to 4 units; after the first order the replay
  is not a prediction of the probe game.
* **Equivalence** (`equivalence.json`): on every recorded decision of the Sprint 5 populations (H0 33,696, H1 1,800,
  H2 4,684) the registered candidate emits exactly the Sprint 5 shadow's actions, added orders and skip reasons; its
  recorded baseline trace digest equals an independent `baseline-v2` instance's; its orders number 234, 60 and 429,
  the Sprint 5 counts.
* **Visibility calibration** (`calibration.json`): the documented observation model (section 8, E4) against every
  unconcealed ground target-step of the replay corpus H0 (8 games, both seats). The model was fixed from the published
  rules; two choices were read from this data before registration: aerial observers use line-of-sight mode 2 (low
  air to ground; mode 0 and mode 6 disagree on some aerial pairs), and units with a `launcher` relation are excluded,
  because in all 100 target-steps where the model disagrees for them the unit's launcher was listed by the opponent,
  an association the rules do not document. With these, the model agrees on 258,964 of 258,964 target-steps; a
  vehicle in a forest or town hex 13 hexes from its only possible observer was unlisted in all 238 such target-steps,
  so a half distance of 12.5 hexes behaves as a real-valued limit (concealed vehicles at 13 hexes are nevertheless
  kept out of E4's verdict, section 8).
* **Dry run** (`dryrun.json`): the registered P-A analysis on the reference game itself, adapted to the probe's
  capture form (its batch as the pre-execution copies, its recorded trace digest in place of the candidate's block),
  finds no concealment order and reports every mechanism endpoint NOT TESTED; its premise comparison runs over all
  1,801 decisions (state and trace digests and actions equal at every one, observation digests at the 1,800 the
  reference captured) and stops on "no concealment order was issued". The reference's state and trace digests and final scores equal those of the three Sprint 1 games of the
  same configuration. E4's machinery on the H0 game of 2120531121 (no concealed unit) agrees with the listings on
  59,528 of 59,528 control target-steps, 2,357 of them in the matched band.

## 3. The candidate

`t7-idle-concealment` (`src/miaosuan_agent/experiments/t7_concealment.py`) imports the Sprint 5 shadow
(`experiments/t7_idle_concealment.py`, unchanged) and adapts it to the agent interface:

* **Rule** (frozen, `docs/T7_DESIGN.md` section 14): `baseline-v2` decides first, unchanged; its actions are emitted
  unchanged and in its order. Then each own unit in ascending `obj_id` that received no `baseline-v2` action is
  ordered `{"actor", "obj_id", "type": 6, "target_state": 4}` when it is a ground unit listed in `operators`, action 6
  is listed for it with `target_state` 4, `move_state` is not 4, the five transition timers are numbers equal to 0,
  `stop` is 1, `move_path` is empty, `keep` is 0, no unit of the other faction is in the seat view, and the candidate
  has not ordered it in the last 75 steps; the order passes the candidate's own check (option listed, exact key set,
  one action per unit). Nothing in deployment; no stop, march, charge, lock, unfold or path change; no other seat's
  view, all-seeing state or hidden information; every missing or malformed field fails closed.
* **Trace**: `baseline-v2`'s trace with the candidate's identity and every emitted action, plus a `t7` block holding
  the SHA-256 of `baseline-v2`'s own trace for the decision, the added orders and the skip reasons by count. The P-A
  comparison with the reference game uses that baseline digest.
* **Fail closed** beyond the rule: an exception other than a contract violation after `baseline-v2` decided makes the
  decision `baseline-v2`'s alone and is recorded as a `t7` error (counted by S4); a contract violation gives no action.

The shadow's docstring says that no runner imports it; it predates this registration, and the candidate module is
the one place that does.

## 4. The three games

| Probe | Game id | Scenario | Map | Condition | Red | Blue | max_time |
|---|---|---|---|---|---|---|---|
| P-A | `1910631192.C3.pa` | 1910631192 | 92 | C3 | `inert-v0` | `t7-idle-concealment` | 1800 |
| P-B1 | `2120531121.H1.pb1` | 2120531121 | 21 | H1 | `t7-idle-concealment` | `baseline-v2` | 2880 |
| P-B2 | `2120531121.H2.pb2` | 2120531121 | 21 | H2 | `baseline-v2` | `t7-idle-concealment` | 2880 |

P-A is the reference game's configuration with `baseline-v2` replaced by the candidate; P-B keeps the seat
conventions of the deployment-split screen's head-to-head conditions H1 and H2. The scenario inputs, players,
randomness and caps are the screen manifest's, checked by the manifest builder. `baseline-v2` runs under its code
identity `baseline-v2-candidate-shoot-target-reservation`.

* Seeds: the harness seeds Python's and NumPy's generators with `global_seed` 20260929 in a fresh process,
  `PYTHONHASHSEED` 0. **The engine's own random source is not controlled by these seeds.** The reference configuration
  was deterministic in Sprint 1 (three games) and Sprint 2 (no shot is fired); P-B, where units fire, is stochastic.
* Runtime `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), SDK 4.1.0, CPython 3.10.20, NumPy 1.26.2, the persistent
  installation on the evaluation server; one game per exclusive session, serially, through
  `scripts/run_evaluation.sh --plan t7-probe --purpose diagnostic --workers 1 --work local/evaluation/t7-mechanism-probe-1
  --games FILE` with one game per invocation (the plan refuses more). The scheduler identity is recorded.
* At most 3 sessions. The ledger stood at 2461 at G0, so they are expected to be 2462, 2463 and 2464; the ledger
  decides.
* Capture (`evaluation/t7_probe.py`, `T7Capture`): the residual-516 step capture extended to snapshot both seats (the
  inert control included) and the all-seeing state at every decision from index 0, the final state after the last
  step, a deep copy of every submitted action taken before the engine step, and the candidate's `t7` block. Private,
  under the server's `local/evaluation/t7-mechanism-probe-1/`.

## 5. Frozen identities

| Item | Identity |
|---|---|
| Manifest | `evaluation/t7-mechanism-probe-1/manifest.json`, canonical SHA-256 `270f7f6cc88040d1e746ac153c4d720ee1cf4f8606c445cefd9f5c414ecb84c8` |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` (unchanged) |
| `t7-idle-concealment` | policy source `6b73c39ad785938cc1c54b72065858fbf6460a66ceebae627bad4e99fa1a50f0`: `baseline-v2`'s source set plus `experiments/t7_idle_concealment.py` and `experiments/t7_concealment.py` |
| Runtime, scheduler | `baseline-v1-runtime-r2`; `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90` |
| Analyses and tests | `implementation.files` and `implementation.tests` of the manifest (normalised SHA-256 of each file); the game loop and the step capture are those of the registration commit, which every game record carries |
| Inputs | the reference game's record, capture and windows, the private premise and the Sprint 1 records (SHA-256 in `inputs`); the public pre-registration outputs (normalised SHA-256) |

## 6. Definitions

* **Order**: an action `{actor, obj_id, type 6, target_state 4}` in the candidate seat's pre-execution copy of
  decision `k`; `s0` is the cur_step of the observation it was decided on; the engine step that executes it leads to
  the snapshot of decision `k + 1` (cur_step `s0 + 1`).
* **Fresh feedback**: the engine's action feedback entries after a step that were not already reported at the previous
  step while the clock stood still. An entry echoes an action when its message has the same actor, type and `obj_id`
  and, for action 6, `target_state` (matched against the pre-execution copy or the action as serialised after the
  step, since the engine may rewrite action objects in place).
* **Unit series**: an affected unit's fields at every snapshot from its order on (`move_state`, the five transition
  timers, `stop`, `keep`, `move_path`, `cur_hex`, `flag_force_stop`, `speed`, `blood`, `on_board`, the listed action
  types and change-state options), read from the all-seeing state and, independently, from the candidate seat's
  observation; the analysis refuses when the two disagree for an affected unit.
* **Transition**: any of the five timers positive. **Concealed**: `move_state` 4 with `change_state_remain_time` 0.
* **Completion**: the first snapshot after the order with cur_step `s` at most `s0 + 76` at which the unit is
  concealed; `d = s - s0` is the duration (documented 75 s; the transition may start in the order's step or the next).
* **Outcome** of each order: COMPLETED (timer positive at `s0 + 1` or `s0 + 2`, completion with `d <= 76`);
  COMPLETED_TIMER_ANOMALY (completion with `d <= 76` but no positive timer at `s0 + 1` or `s0 + 2`); LATE (no completion
  within 76 steps, concealed later, no documented interrupter before); NOT_COMPLETED (the window fully observed, no
  completion, no interrupter, never concealed later); INTERRUPTED (before completion and within the window: the unit
  suppressed, an enemy unit in its hex, the unit firing, a `baseline-v2` action for it accepted by the engine, or the
  unit gone or boarded); CENSORED (the game ended before `s0 + 76` without completion or interruption).

## 7. Safety endpoints

| Id | Rule |
|---|---|
| S1 | PASS when no fresh feedback entry echoing a concealment order carries an error code; FAIL otherwise |
| S2 | over the affected units, from their first order to the end: FAIL when `flag_force_stop` is 1 at any snapshot, when an alive unit on the map has an empty or absent listing for more than 1 consecutive snapshot outside a transition, or when a unit that listed action 1 at its order does not list it for more than 1 consecutive snapshot at which it is alive, on the map, outside a transition, with `keep` 0 and no move path; PASS when none occurs and an order was issued; NOT TESTED without an order. Every transient (single-snapshot) loss and every listing change is reported. A documented transition's temporary restrictions are thereby separated from an indefinite lock such as Sprint 4's |
| S3 | P-A. S3a, the premise: at every decision before the first order and at that decision, the all-seeing state digest equals the reference's, the candidate seat's observation digest equals the reference's blue observation's, the candidate's baseline trace digest equals the reference's blue trace digest, the inert seat's trace digest equals the reference's red one, and the actions equal the reference's (the full dictionaries in order; at the first order the reference's actions followed by the orders); and the first order is at decision 717 with the 2 predicted units. S3b: at every later decision the candidate seat's actions without its orders equal the reference's blue actions, the inert seat's equal the reference's red actions, the game has the reference's number of steps and the final scores equal the reference's. PASS when both hold; FAIL when S3a holds and S3b does not (the first differing decision characterised); INCONCLUSIVE when S3a does not hold or the game did not complete. Concealment changing a state or a later listing is not exempted: if it changes a `baseline-v2` action, S3 FAILS |
| S4 | P-B. PASS when every refusal class (action type, code, message class) of the candidate seat is one of `baseline-v2`'s registered classes (shoot-reservation experiment, group C: 1/404, 2/203, 2/516, 5/203), every candidate decision carries its `t7` block, no `t7` error was recorded, and the record shows no contract error, replay mismatch or observer error; FAIL otherwise. The opponent's classes outside that set are reported, not judged |

## 8. Mechanism endpoints

Verdict levels: SUPPORTED, REFUTED, INCONCLUSIVE, NOT TESTED. An endpoint without a discriminating event is NOT
TESTED; no event is manufactured, and no endpoint is inferred from another or from documentation.

| Id | Rule |
|---|---|
| E1 | per order, exactly one echoing fresh feedback entry. SUPPORTED when an order was issued and every order has one echo without an error code; REFUTED when an echo carries an error code; INCONCLUSIVE when an order has no echo or several; NOT TESTED without an order. An echo without error is acceptance of the message only, never evidence of the transition |
| E2 | the outcome of every order (section 6). SUPPORTED when an order was issued and every order is COMPLETED; REFUTED when any is COMPLETED_TIMER_ANOMALY, LATE or NOT_COMPLETED; INCONCLUSIVE when none is refuted and some is INTERRUPTED or CENSORED; NOT TESTED without an order. Every duration, the first step `move_state` read 4 and the timer's trajectory are reported |
| E3a | retained listings: for every completed order, every action type the unit listed at its order (except 6) must stay listed at every later snapshot while it is concealed, alive, on the map, outside a transition and with `keep` 0; a type absent for more than 1 consecutive snapshot is a loss. SUPPORTED with such snapshots and no loss; REFUTED with a loss (type named); NOT TESTED without a completed order. The change-state options listed while concealed are reported |
| E3b | exit by a real action: every `baseline-v2` move (1) or shot (2) submitted for a unit concealed at the decision; per event the listing, submission, echo, execution (a move: the next snapshot shows the ordered path or the first hex entered; a shot: a judge record of the unit in that step), `move_state` and, for a move, `speed` at the next snapshot. Consistent: echoed without error, executed, `move_state` not 4 at the next snapshot, and a move showing `speed` above 0 or its first hex entered there; a move whose first hex holds 4 own ground units at the next snapshot is excluded (stacking wait). SUPPORTED with a consistent event and none inconsistent; REFUTED with an inconsistent event; INCONCLUSIVE when every event is excluded; NOT TESTED without an event. Moves of unconcealed stationary units of the same game are reported as the comparison |
| E4 | P-B, defined below; E4a decides, E4b is a consistency check |
| E5 | during an unfinished transition: a `baseline-v2` action for the unit, its suppression, an enemy unit in its hex, or its firing. Documented: no other command executes during the transition (an order is refused, or executed only once the transition ends: decided with at most 1 step left); a tank's shot executes and interrupts it; suppression and same-hex engagement interrupt it. SUPPORTED with an event and all as documented; REFUTED with an event against it; NOT TESTED without an event |
| E6 | P-A: at every snapshot from the first order, every unit's position, presence and `blood`, the objectives' flags and the scores equal the reference's at the same decision index, and the final scores equal it. SUPPORTED when an order completed and all are equal; REFUTED with a difference (the first characterised); INCONCLUSIVE when S3a does not hold; NOT TESTED without an order |

**E4.** The documented visibility model (`src/miaosuan_agent/evaluation/t7_visibility.py`): infantry, vehicle and
helicopter observers see infantry at 10 hexes and vehicles at 25, unmanned aerial vehicles and loitering munitions see
ground units at 2; line of sight from the setup table, mode 0 for ground observers and mode 2 for aerial ones; a unit
in a forest or town hex is observed at half the distance; a concealed unit is observed at half the distance, except a
vehicle lower than its observer. Targets: every ground unit on the map of either seat at every snapshot, except units
with a `launcher` relation (section 2). A **concealed** target (`move_state` 4, timer 0) is set against every opposing
unit on the map, each pair banded as within the concealed distance, between it and the normal distance, on the
12.5-hex boundary, beyond the normal distance, or without line of sight, and the target-step falls into exactly one
class, in this order:

1. terrain: the target in a forest or town hex with an observer within its normal distance (whether the two halvings
   stack is undocumented: reported with both predictions, outside the verdict);
2. exception: a vehicle lower than a ground observer within its normal distance (expected listed; reported);
3. ambiguous aerial: a concealed vehicle with an aerial observer within its normal distance (whether an aircraft
   counts as higher is undocumented; reported);
4. expected listed: an observer within the concealed distance (E4b);
5. ambiguous boundary: the nearest relevant observer 13 hexes from a concealed vehicle (reported);
6. **discriminating**: an observer between the concealed and the normal distance and none closer (E4a: expected
   unlisted);
7. expected unlisted: none within the normal distance (reported).

The outcome is whether the opposing seat's observation lists the target. **Control**: unconcealed targets
(`move_state` 0, no timer) are predicted listed exactly when some opposing unit sees them under the model; the
**matched band** is the control target-steps that would be discriminating if the target were concealed. The control
is valid in a game when the model agrees on at least 0.999 of its control target-steps and on at least 0.99 of at
least 20 matched-band target-steps. **E4a**: SUPPORTED when the control is valid in every game used, at least one
discriminating concealed target-step exists and none is listed; REFUTED when the control is valid and at least half
of the discriminating target-steps are listed; INCONCLUSIVE when the control is invalid or fewer than half but some
are listed (each listed target-step characterised); NOT TESTED without a discriminating target-step. **E4b**:
SUPPORTED when every expected-listed concealed target-step is listed; REFUTED when one is not; NOT TESTED without one.
Pairs and classes are computed twice, from the all-seeing state and from the two seats' own views (targets from their
own seat, observers from the opposing seat), and the analysis refuses when the hex, the pairs, the class or the outcome
differ. Reported per game and pooled over P-B1 and P-B2: target-steps, distinct targets, distinct (target, observer)
pairs and episodes per class. Target-steps of one unit are serially dependent; they are counts of observations, not
independent trials, and unconcealed pairs are a contextual comparison, not a within-unit experiment.

## 9. Primary metric

The share of issued concealment orders that reach the concealed state within 76 steps of the order's cur_step, per
game and pooled over the games played. Every order issued is in the denominator; censored and interrupted orders are
counted there and reported separately. The mechanism criterion requires 100% with every applicable safety check
passed. A successful E2 establishes neither E3, E4, E5 nor E6.

## 10. Integrity and independent evidence

| Check | Rule (the analysis refuses on failure) |
|---|---|
| I1 | the record completed, `done`, the registered policy digests, runtime and capture settings, harness commit the registration commit and not dirty, no observer error, no replay mismatch |
| I2 | a snapshot of both seats and the all-seeing state at every decision from 0 to the last, the compact log complete, the final state present |
| I3 | the candidate's orders counted three ways (its `t7` blocks, its pre-execution copies, the record's `actions_by_type`), and every seat's copies by type equal the record's counts; in-place rewrites counted |
| I4 | the two channels agree on every affected unit's series |
| I5 | a new candidate instance re-decides every captured candidate decision from the seat's recorded observation and memory, and a new `baseline-v2` instance every `baseline-v2` decision, reproducing the submitted actions and trace digests; the independently written pool predicate (`evaluation/t7_candidates.py`, Sprint 5) finds exactly the captured orders |
| I6 | transition start and completion reconstructed a second time, by one pass over the seat's own view for every unit, equal the forward scan over the all-seeing state |

| Claim | Primary source | Independent source |
|---|---|---|
| Orders issued | candidate `t7` blocks | pre-execution copies; record counts; pool predicate |
| Acceptance | fresh feedback | the transition itself (E2), never inferred from the echo |
| Transition times | all-seeing state, forward scan | seat view, one pass per unit |
| P-A premise | record state digests | seat observation digests; baseline trace digests |
| Non-interference | reference record and capture | positions, flags, scores per snapshot (E6) |
| Visibility pairs | all-seeing positions and setup line of sight | each seat's own positions |
| Decisions | the game's agents | new instances on the recorded observations |

## 11. Continuation gate and stop rules

* **Before P-A**: the registration verified (commit on the public remote; the public issue fetched without
  authentication and byte-identical to the canonical body), G0 passed, the server tree at the registration commit.
* **P-A continuation gate** (`scripts/t7_probe_analysis.py gate`): P-B runs only when P-A's integrity checks pass, S1
  PASS, S2 PASS, S3 PASS and E2 SUPPORTED, and after P-A the ledger is continuous with no unclosed session, the
  installation passes its integrity check and the frozen identities recompute. Anything else stops the probe; an
  analysis that refuses is a blocker to report, never something to repair and relabel as registered.
* **P-B stop branch** (`stop`): after P-B1, P-B2 runs unless P-B1's integrity checks fail, S1, S2 or S4 FAIL, or the
  ledger, installation or identities fail their check. An E verdict of P-B1 does not stop P-B2.
* No repetition, replacement or fourth game; no change of scenario, seed, configuration, candidate, trigger or
  analysis after any game. A failed or capped game is preserved and reported, never replaced. A defect found after
  the first game is handled only in a separate, labelled post-hoc analysis; registered outputs and verdicts stand.

## 12. Disposition

Evaluated in this order on the registered results of the games played (E verdicts pooled: REFUTED in any game wins,
then INCONCLUSIVE, then SUPPORTED):

1. **SHELVE** when S1 or S2 FAIL in any game, or E1, E3b or E4a is REFUTED, or E2 is REFUTED with an order
   NOT_COMPLETED;
2. **REVISE** when otherwise an integrity check fails or S4 FAILS, S3 FAILS or E6 is REFUTED, E3a or E5 is REFUTED, or
   E2 is REFUTED by LATE or COMPLETED_TIMER_ANOMALY outcomes only;
3. **READY_FOR_TACTICAL_SCREEN** when all three games were played, E1, E2, E3a, E3b, E4a and E6 are SUPPORTED and S1
   to S4 PASS wherever they apply (E4b and E5 reported, not deciding);
4. **NEEDS_TARGETED_PROBE** otherwise, naming the smallest missing verification.

The indispensable behaviours are E1, E2, E3a, E3b, E4a and E6. Only READY would allow drafting a tactical A/B
proposal, which needs its own registration and approval; no A/B runs in this sprint.

## 13. Analysis readiness

* Tests: `tests/test_t7_concealment.py` (the wrapper), `tests/test_t7_visibility.py` (the model),
  `tests/test_t7_probe_analysis.py` (end to end on a stand-in engine, `tests/fixtures/t7_probe_engine.py`, that plays
  the candidate through the project's game loop and capture, one engine behaviour per game: documented, refused,
  ignored, instant, no timer, timer one or two steps late, a longer transition, a lock, listings lost while concealed,
  a single-snapshot and a two-snapshot listing loss, game-end censoring, suppression that does and does not interrupt,
  free and delayed exit by a move, orders during the transition refused, deferred and executed, a tank's shot during
  the transition, a shot from concealment, visibility as documented, without effect, total, with the lower-vehicle
  exception and without any opponent nearby, an engine rewriting the order in place; planted errors for every
  integrity check; the reference differing before and after the first order; the gate, stop branch and disposition
  tables), `tests/test_t7_probe_registration.py`, and the private `tests/test_real_t7_probe.py` (byte-identical
  rebuilds of the pre-registration outputs and the dry run's registered content).
* Mutation testing (`scripts/mutate_t7_probe.py`, `mutation.json`): 55 of 56 mutants of the candidate wrapper, the capture, the game loop's pre-execution copy, the visibility model, the analyses, the gate and the disposition are killed; the survivor is equivalent (removing the record from the three-way order count leaves the per-seat comparison of the copies by type with the record, which enforces the same equality). The first run killed 43 of 55; of its 12 survivors one was the same equivalent mutant and 11 were gaps in the tests (an engine that sets `move_state` 4 before the timer ends, a transition of 76 or 77 steps, a missing echo, a move that keeps concealment, a move-to-stop transition, a new refusal class, a listing changed in one channel, re-decided actions, the matched-band validity, a fallback decision in which `baseline-v2` acts) and were closed before registration, adding one mutant (the matched-band minimum).
* The calibration, premise, equivalence and dry run of section 2.

## 14. Not claimed and limitations

* No tactical efficacy: P-A's opponent is inert; P-B's two seat-swapped games are a mechanism study, not an A/B, and
  no score, win or rate difference is estimated or claimed.
* No engine-wide generality: each verdict holds within the scenarios and unit populations observed, and an endpoint
  supported in one game or unit population is reported as such.
* No promotion and no platform upload of the candidate; `baseline-v2` is unchanged.
* The engine's random source is not controlled; E3b and E5 need events the registered policies produce on their own;
  E4 rests on the documented model calibrated on unconcealed units, and terrain stacking, aerial observers of concealed
  vehicles and the 12.5-hex boundary stay outside its verdict.
