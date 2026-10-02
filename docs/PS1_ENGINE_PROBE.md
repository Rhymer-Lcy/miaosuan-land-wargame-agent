# PS-1 engine probe: two registered sessions

**ENGINE PROBE.** Two diagnostic engine sessions, no screen, no promotion, nothing here can change a baseline. This
document is the protocol of `ps1-engine-probe-1`: sections 1 to 11 were written and pushed, with the manifest and both
analysis implementations, before either session; later sections are written afterwards and say so. Times are UTC+8.

## 1. Questions

1. **P1, engine semantics.** What does engine 4.1.0 do with a stop order (action 10) issued to own ground units that
   wait in front of a hex holding four own ground units: is it accepted (E1), does it take effect where the unit
   stands (E2), how long is the transition and is a new move listed and accepted afterwards (E3), and does a
   transitioning unit still count toward its hex's stacking limit (E4)?
2. **P2, the movement model.** Does the frozen post-hoc model M1c predict an unseen game, entry for entry (F1), and
   do its distinctive assumptions hold where the game discriminates them (E5 and the targeted claims T-a to T-e)? Does
   the baseline surrogate reproduce the candidate's orders (F2)?
3. **Gates.** With those answers, what are the gates G2 and G3 of `docs/PS1_DESIGN.md`, and the research
   disposition?

## 2. Starting evidence and disclosure

Sprint 3 (`docs/PS1_DESIGN.md`, section 11) ended with G1 PASS, G2 FAIL (PS-1B depends on the unobserved E1 to E4), G3
FAIL (M1 and M1b failed their registered fidelity requirements), G4 PASS for PS-1B, and disposition NEEDS_ENGINE_PROBE.
M1c, the model P2 tests, is **post hoc**: it was derived from the two Sprint 2 games it reproduces, and the replay
corpus was inspected while it was developed. Neither is independent evidence for it.

Read before this protocol, none of it from the probe games (which did not exist):

* the two Sprint 2 captures of 1910631192 C3 (private, a snapshot every step), the Sprint 3 outputs and certificates;
* from the Sprint 1 smoke capture of the P2 configuration, setup-level facts only: no roadblocks, minefields or
  fortifications in either scenario, and the candidate's force type mix at its first snapshot (ground vehicles and
  infantry, two aircraft, passengers). Its 200-step snapshots were used in Sprint 3 for the trigger census only;
* an **offline replay of the hook over the Sprint 2 split game** (`scripts/ps1_probe_verify_hook.py`): at all 532
  decisions before its trigger the hooked policy decides exactly as the frozen candidate (actions and trace digests,
  and the captured decisions; the only differences in the serialised capture are the six documented in-place rewrites
  of a deployment split's type). It triggers at decision index 533 (cur_step 530), the registered first detection of
  Sprint 3, and selects 4 units, the same units and back-off destinations as the first recovery of the Sprint 3
  certificate A2. This is the prediction the P1 premise registers;
* a **dry run of the analyses on real records** (`scripts/ps1_probe_dryrun.py`): on the Sprint 2 split game, adapted to
  the probe capture format only by undoing the documented rewrite, the P2 analysis gives F1 PASS (274 of 274 entries,
  worst offset 0) and F2 PASS (18 of 18 orders, 1 of 1 occupation), agrees with the frozen Sprint 3 extractors, and
  counts 1,270 trigger steps, Sprint 3's figure; the P1 analysis finds no stop there and reports every E hypothesis
  INCONCLUSIVE; the 200-step smoke capture is refused for missing snapshots. These runs test the analysis code; they
  are not evidence for M1c, which was derived from the game they ran on.

## 3. The two games

| Probe | Game id | Scenario | Map | Condition | Red | Blue | max_time | Step cap |
|---|---|---|---|---|---|---|---|---|
| P1 | `1910631192.C3.p1` | 1910631192 | 92 | C3 | `inert-v0` | `ps1-probe-hook-1` | 1800 | 1901 |
| P2 | `1930331196.C2.p2` | 1930331196 | 96 | C2 | `tactic-deployment-split-1` | `inert-v0` | 2880 | 2981 |

P1 is the Sprint 2 split-game configuration (`1910631192.C3.c.x01`: the inert control red, the split candidate blue)
with the candidate replaced by the diagnostic hook. P2 is the Sprint 1 smoke configuration of the second scenario
(`1930331196.C2.c.s01`: the candidate red, the inert control blue), whose 200-step snapshots showed a deadlock cycle;
both seat assignments are checked against the screen manifest by the manifest builder and a registration test.

* Seeds: the harness seeds Python's and NumPy's generators with `global_seed` 20260929 in a fresh process,
  `PYTHONHASHSEED` 0; the engine's own random source is not controlled (procedure of the screen manifest).
* Runtime `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), one game per exclusive session, serially, P1 first,
  through `scripts/run_evaluation.sh --plan probe --purpose diagnostic --workers 1 --work local/evaluation/ps1-engine-probe-1
  --games FILE` with one game in each invocation; the scheduler identity is recorded but the serial loop does not use it. SDK
  4.1.0, CPython 3.10.20, NumPy 1.26.2, the persistent installation on the evaluation server.
* At most 2 sessions; the ledger stood at 2459 at G0, so they are expected to be 2460 and 2461 (the ledger decides).
* Capture: the read-only step capture of the residual-516 diagnostic with a full snapshot at every decision (the
  all-seeing state, the policy seat's observation, memory, actions and trace digest), plus a deep copy of every
  submitted action taken before the engine step, and the hook's notes. Private, under the server's
  `local/evaluation/ps1-engine-probe-1/`.

## 4. Frozen identities

| Item | Identity |
|---|---|
| Manifest | `evaluation/ps1-engine-probe-1/manifest.json`, canonical SHA-256 `17de5076b15f977730c03606727da6d95fd369d9b61717dc270d0179f7fbca96` |
| Split candidate `tactic-deployment-split-1` | policy source `000f639b35becbbd712d6134def855284b80ad4644409dc2f0ae9ee47113a2e9`, unchanged since Sprint 1 |
| Hook `ps1-probe-hook-1` | policy source `84a98a48346cca928e0f1d990637dda1c33d93fd790bb2176f73df47412b651a`: the candidate's sources plus `experiments/ps1_probe_hook.py` and `evaluation/ps1_model.py` |
| Model M1c | `src/miaosuan_agent/evaluation/ps1_model.py`, SHA-256 (line endings normalised) `d5b2016afafc59f80493c2f00a9b40dd677b5db695bc75c99d619dc2a57a5f55`, `Simulation(restart_after_wait=True, wait_at_entry=True)` |
| Analyses and tests | `implementation.files` and `implementation.tests` of the manifest (normalised SHA-256 of each file); the shared runner and capture harness are those of the registration commit, which every game record carries |
| Mutation results | `evaluation/ps1-engine-probe-1/mutation.json`: 42 of 43 mutants killed |

## 5. The diagnostic hook (P1)

`ps1-probe-hook-1` is not a candidate. It composes the frozen split candidate, reused by import and unchanged, with a
hook that runs after the candidate's own decision:

* **Bookkeeping.** For each own ground unit, the step of its last hex change or order, from the seat's observations
  and its own emitted moves; time is the observation's `cur_step`. This is the stall history of the design study.
* **Trigger.** The frozen PS-1B trigger: a non-empty deadlocked set, every unit of it stalled (no progress for more
  than 2 hex times + 10 steps), computed with the Sprint 3 functions.
* **At the first trigger only.** A verification from the seat observation coded apart from the model (every
  deadlocked unit at speed 0, listing action 10, facing a hex with at least 4 own ground units); the frozen PS-1B
  selection with the back-off option (`ps1_model.ps1b` on a scratch model copy of the observed state); one stop
  `{"actor", "obj_id", "type": 10}` per selected unit, each passing the hook's own check (the project gate does not
  catalogue action 10). A failed verification, an empty selection or a model error ends the probe without action.
* **After the stops.** No stop is ever repeated. A stopped unit gets its planned back-off move at the first step its
  observation lists action 1 and shows no move path, within 300 steps of the stops, and only if s1 to s4 hold (still
  in its hex of the trigger; no hex of the path full; the destination's units plus the stopped units already sent
  there below 4; the project gate accepts the move); otherwise it is released to the candidate. Until then the
  candidate's own actions for it are dropped and recorded.
* **Scope.** One recovery per game: the 600-step recovery window of PS-1B is never exercised, and the rule itself is
  unchanged. Before the trigger the hook returns the candidate's actions and trace object unchanged.

## 6. P1 protocol

**Premise.** P1 is evaluable when the hook emits its stops. The expected deadlock reproduced when the P1 record's
all-seeing state digests and the inert seat's trace digests equal those of the Sprint 2 split-game record (SHA-256
pinned in the manifest) at every decision index up to the trigger, the hooked seat's trace digests equal the
candidate's before it, and the trigger is at index 533 with a group of 4. If not, every E verdict is INCONCLUSIVE and
the observations are reported descriptively only. No other trigger is substituted and no session is added.

**Events**, per stopped unit, from the seat observation and independently from the all-seeing state (the analysis
refuses to run when the two disagree for a stopped unit): listing of action 10 at the decision; submission (the
pre-execution copy and the hook's notes must agree); fresh feedback (entries not already reported while the clock stood
still) matching the stop, with or without an error code; the effect (first step its remaining path is empty); in place
or after an entry; the transition (listed action types, `stop`, `move_to_stop_remain_time`, speed, `move_state`,
`can_to_move` per step); the re-listing of action 1 and `L` = its cur_step minus the decision's cur_step `s0`; the
new move (emitted or not and why; its feedback, its echo in the next observation, its arrival). Listing, submission,
acceptance, state change and completion are separate events; acceptance is never inferred from the absence of an
error alone.

| Id | SUPPORTED | REFUTED | INCONCLUSIVE |
|---|---|---|---|
| E1 | every stopped unit shows, within 300 steps, a change attributable to the stop (its path empties while it stands outside the final hex of its path at `s0`, or `move_to_stop_remain_time` becomes positive) and no fresh feedback for the stop carries an error code | an error code with no attributable change, or no attributable change within 300 steps (accepted-and-deferred and ignored cannot be told apart while the next hex stays full); mixed outcomes across the group | contradictory evidence (an error code and an attributable change), or no stop issued |
| E2 | at least one stop took effect, every one in place, and no unit lacked an attributable change | a unit entered its next hex before its path emptied, or showed no attributable change while its next hex stayed full | no stop took effect (all refused or contradictory); a refused unit is E1's failure |
| E3 | every unit stopped in place has action 1 listed again within 300 steps with 74 <= `L` <= 77, and every back-off emitted is accepted (no error code and the echo) | `L` outside the window, no re-listing within 300 steps, or an emitted back-off refused or not echoed | no unit stopped in place |
| E4 | no violation, at least one discriminating unit-step, no restart | a violation or a restart | no discriminating unit-step (untested) |

The E3 window: 75 s are documented; the transition may start in the submission step or the next (`L` 75 or 76), and
one step either side is allowed because whether the engine lists actions before or after updating its timer within a
step is unknown. If no back-off could be emitted (a safety check failed), acceptance of a new move is reported as
untested and E3 rests on the timing and the re-listing.

E4 definitions: transitioning units at step `s` are units whose stop took effect, from their effect step to their
re-listing (or 300 steps). A violation is an observation in that span with more than 4 own ground units in a hex that
holds a transitioning unit. A discriminating unit-step is a non-transitioning own ground unit at speed 0 (keep flag not
set) whose next hex holds a transitioning unit, at least 4 own ground units with it and fewer than 4 without, at least
2 steps after the first effect in that hex. A restart is such a unit later showing speed above 0 towards that hex while
it is full only by counting transitioning units. In the predicted P1 state the units on the objective wait for the
stopped group's hex, so a discriminating event is expected but not guaranteed.

**Secondary outcomes** (descriptive; mechanism, not efficacy): whether and when the trigger's cycle leaves the
wait-for graph, the deadlocked set first empties and a formerly deadlocked unit first enters a hex; deadlock episodes
after the stops (count, largest set, cycle or chain, duration, whether they last to the end); back-off arrivals; new
cycles; final flags and occupy points; the largest own ground occupancy; refusals, contract errors, gate rejections,
replay mismatches. **P1-S**: every accepted order of the hooked seat replayed through M1c with M3 from the first play
step, entry agreement before and after the stops reported separately (before the stops P1 repeats a game M1c was
derived from; P1-S never revises M1c and never enters G3).

**Offline checks**: every pre-trigger snapshot re-decided by a fresh split candidate (actions and trace digest as
captured); the trigger recomputed from the all-seeing state with the Sprint 3 reconstruction (same step).

## 7. P2 protocol

**Population.** The candidate seat's own ground units (type 1 or 2, listed for the seat, not on board) at the first
play decision, plus any that appear later (added to the model at their first observation; one already traversing
cannot be timed and makes the accounting incomplete). Removals are applied as observed inputs. Aircraft, passengers and
the opponent's units are outside the model and are counted, not compared.

**Integrity.** I1 the record (completed, registered digests, runtime, capture setting, no observer error, no replay
mismatch, harness not dirty); I2 a snapshot at every decision, or the analysis refuses; I3 submitted actions by type
equal to the record's own count, or the analysis refuses (in-place rewrites counted); I4 both channels agree on every
unit's hex and path at every snapshot, or F1, F2 and every targeted claim are INCONCLUSIVE; I5 every applied move
reappears as the remaining path in the next snapshot, or F1 is INCONCLUSIVE.

**F1 (primary).** From the first play decision the model receives every pre-execution move and occupation order of
an eligible unit whose fresh feedback carries no error code, at its decision index, plus the observed removals and
appearances, and predicts every entry. **PASS** when every eligible unit's predicted hex sequence equals the observed
one, every matched entry is within 1 step, the predicted trajectory passes the independent capacity and adjacency
validator (observed removals and appearances applied as inputs, never violations themselves), no observation shows more than 4 own ground units in a hex, and the accounting is complete (every unit and
step compared, no model error, no inapplicable order). Otherwise **FAIL**. Reported in full: the offset distribution
and worst offset, each mismatched unit's first differing entry with its conditions (occupancy and contenders at the
contested hex, keep flag, `move_state` and speed changes, refused orders), order counts by outcome. Failures are
never averaged away and no unit is discarded.

**F2 (secondary, its own rule).** The same start with the frozen surrogate M7 issuing every order. **PASS** when every
eligible unit's predicted sequence equals the observed one within 1 step, every recorded accepted move order is
matched (same unit, same final hex, within 1 step) with no unmatched prediction, and every recorded accepted
occupation is matched (same objective, within 1 step) with none extra. Otherwise **FAIL**. Behaviour outside the
surrogate's scope (shots, refused orders, occupations not listed, aircraft orders) is reported. A passing F1 does not
establish F2.

**Targeted claims** (computed from the observations, not from the simulator, by two extractions over the two channels;
a disagreement makes a claim INCONCLUSIVE):

| Id | Discriminating event | M1c predicts |
|---|---|---|
| T-a wait at entry | an entry with a path left whose next hex holds at least 4 own ground units before and after the step, nobody leaving it, keep flag not set | speed 0 at the entry (M1b: above 0) |
| T-b restart | the final run before the entry of every entered blocked-wait episode, tau >= 4, no keep flag or speed-state change in it | a traversal of tau - 1 steps (tolerance 1); an entry straight from waiting (M1) or another length contradicts it |
| T-c re-wait | a traversal run followed by a re-wait within such an episode (each run separately; never measured from the first step with room) | tau - 1 steps (tolerance 1), and the hex full again at the first step of the re-wait |
| T-d arbitration | a step in which, for one hex, some traversing units enter and others re-wait | the entrants are the lowest-index units; descending index and first come (earliest start of the current wait) are evaluated beside it |
| T-e processing order | entries whose next hex is full or not depending on the processing order (ascending, descending, end of step); T-d events; waiting units whose next hex gets room through leaving units, where the predictions of the orders differ | ascending index in each |

A claim is **SUPPORTED** with at least 3 discriminating events, all as predicted (T-d also needs at least one event in
which first come predicts other entrants than ascending index); **REFUTED** when any discriminating event contradicts
the prediction; **INSUFFICIENT** with 1 or 2, all as predicted; **NOT TESTED** with none. Excluded observations are
counted with their reason. Keep-flag observations are reported separately, never discarded from F1, never counted as
discriminating. A perfect F1 on a game without discriminating events does not support E5. The entry rule and the
blocked-wait episodes are also recomputed by the frozen Sprint 3 extractors (`ps1_posthoc.entry_rule`,
`ps1_study.restart_episodes`), and the analysis refuses to run when they disagree with its own; the PS-1B trigger census
of P2 must equal the trigger steps counted inside its deadlock episodes.

## 8. Gate reassessment and disposition

Sprint 3's verdicts stay as the historical record; these rules give Sprint 4's.

| Gate | Rule |
|---|---|
| G1 | Sprint 3's PASS stands; audited for contradiction (P1's reproduction of the Sprint 2 states; both channels agreeing and no hex above 4 own ground units in both captures) |
| G2 | PASS when E1, E2, E3 and E4 are SUPPORTED and the P1 sequence used only the seat observation and listed actions (every hook action passed its check, no replay mismatch, the offline re-decisions agree); FAIL when any of them is REFUTED, naming the part of PS-1B it invalidates; UNRESOLVED otherwise |
| G3 | PASS when F1 and F2 PASS, T-a, T-b, T-d and T-e are SUPPORTED, T-c is SUPPORTED, INSUFFICIENT or NOT TESTED, G2 passes, and the A2 certificate recomputed under M1c is feasible (recomputed only when everything else passes); FAIL when F1 or F2 fails or a targeted claim is REFUTED; UNRESOLVED otherwise. M1 and M1b keep their failed registered results |
| G4 | Sprint 3's PASS for PS-1B stands; audited for contradiction (the trigger census of P2 and P1's pre-trigger part) |
| G5 | exactly one of: SHELVE when E1 is REFUTED with no stop accepted from any blocked unit; REVISE when otherwise any of E2 to E4 is REFUTED, F1 or F2 fails, or a targeted claim is REFUTED; NEEDS_ENGINE_PROBE when nothing is refuted or failed but G2 or G3 is UNRESOLVED (the smallest next probe named, not run); READY_FOR_PROSPECTIVE_VALIDATION when G2 and G3 pass and G1 and G4 are not contradicted |

A READY disposition would only allow `docs/PS1_SCREEN_PROPOSAL.md`, a proposal, not a registration.

## 9. Stop rules and branches

* Before P1: the registration verified (commit on the public remote; the public issue fetched without authentication
  and byte-identical to the canonical body), G0 passed, the server tree at the registration commit.
* P1 first, then P2, one session each; no repetition, replacement, or change of scenario, seed, configuration or code
  after either game. A failed or capped game is preserved and reported, never replaced.
* After P1: ledger continuity, capture integrity and the frozen identities are verified before P2. An installation
  integrity failure, an unauthorised installation change or a serious safety violation stops the probe before P2. An
  inconclusive P1 or a refuted E hypothesis does not stop P2, which tests M1c independently. P1 never revises M1c.
* An analysis defect found after registration is fixed in a separate, labelled post-hoc analysis; the registered
  output and its verdicts stand. An inconclusive probe never authorises a third session.
* Branches: P1 INCONCLUSIVE leaves G2 UNRESOLVED and names the next probe; a refuted E hypothesis fails G2 and states
  what part of PS-1B it invalidates; a failed F1 means any corrected model is a new post-hoc candidate needing its own
  prospective test in a later sprint; a P2 without discriminating events leaves the claims NOT TESTED or INSUFFICIENT.

Not claimed: tactical efficacy (P1 is one game with one intervention), engine-wide correctness (one prospective game
supports a mechanism within its observed conditions only), or the promotion of either candidate; T1 stays shelved.

## 10. Independent evidence for each check

| Check | Primary source | Independent source |
|---|---|---|
| P1 reproduction | P1 record's state and trace digests | Sprint 2 record (pinned digest) and the offline hook replay's prediction |
| P1 trigger | the hook's notes at decision time | Sprint 3 reconstruction from the all-seeing state |
| Pre-trigger decisions | in-game replay checks | offline re-decision of every snapshot by a fresh candidate |
| Stops and moves submitted | pre-execution copies | the hook's notes; the record's own count by type |
| Effect, re-listing, positions | seat observation | all-seeing state (refusal on disagreement); `move_to_stop_remain_time` |
| Acceptance | a state change attributable to the action | fresh feedback (no error code), never alone |
| E4 occupancy | seat observation counts | the all-seeing state's capacity check (largest occupancy) |
| F1 entries | the replay against the seat observation | the all-seeing state (I4); the independent trajectory validator |
| Targeted events | extraction from the seat observation | separate extraction from the all-seeing state; the frozen Sprint 3 extractors |
| Trigger census | `ps1_study.census_sequence` | `ps1_posthoc.deadlock_episodes` |

## 11. Analysis readiness

* Tests: `tests/test_ps1_probe_hook.py`, `tests/test_ps1_probe_analysis.py`, `tests/test_ps1_probe_registration.py`.
  The hook and the P1 analysis run end to end on a synthetic stand-in engine whose movement core is the frozen model
  (`tests/fixtures/ps1_probe_engine.py`), one game per stop behaviour: in place, refused, ignored, entering first,
  transitions of 73, 74, 77 and 78 steps, no re-listing, a refused re-order, transitioning units that do not count, a
  partly accepted group, a newly full destination, a dead-end corridor with no escape, a watch window running out, an
  engine rewriting the stop action in place. Each gives its registered verdicts. The P2 claims run on trajectories
  generated by M1c and by its rivals (`tests/fixtures/ps1_trajectories.py`): each claim holds on M1c data and is
  refuted on its rival's (M1b: T-a; M1: T-a, T-b and F1; descending processing: T-d, T-e and F1), with planted entry
  delays, capacity violations, keep flags, removals, appearances, mixed speeds and game lengths of 40 and 400 steps.
* Mutation testing (`scripts/mutate_ps1_probe.py`): 42 of 43 mutants of the hook, the capture, the game loop's
  pre-execution copy and the analyses are killed; the one survivor is equivalent (trace replaced before the trigger:
  with no notes the replacement rebuilds the same diagnostics and emitted fields, so the trace and its digest are
  unchanged). The first run killed 30 of 41: of its 11 survivors one was that equivalent mutant and 10 were gaps in the
  tests; closing one of them exposed a defect in the analysis (the independent trajectory validator ignored observed
  removals and appearances, which would have failed F1 falsely). Tests and a cross-checked inputs-aware validator were
  added before registration.
* The dry run on real records of section 2.

## 12. Registration (written after the registration commit, before either session)

* Registration commit `23341a4d72cd55a62c3f76aef4adfc763fc257ca`, pushed and fetched back from the public remote without
  authentication; manifest canonical SHA-256 `17de5076b15f977730c03606727da6d95fd369d9b61717dc270d0179f7fbca96`.
* Public issue [#2](https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/2), created 2026-10-02T18:27:13+08:00
  (GitHub's clock), fetched without authentication at 2026-10-02T18:27:29+08:00: its body, 16,312 bytes, SHA-256
  `7c8626c30ff5f60ccb222177a3c24a6d769add914d6d68ddadc9b40402e77894`, is byte-identical to the canonical file
  `evaluation/ps1-engine-probe-1/registration-issue.md` (record: `registration-verification.json`).
* The server stayed at the registration commit with a clean tree for both games; this record and every result file were
  committed afterwards, so that both game records carry the registration commit, as registered.

## 13. Execution (written after the sessions)

* Two sessions, as registered: **2460** (P1) opened at 2026-10-02T10:35:12Z by the server clock, which runs fast by the
  offset recorded in `docs/ENGINE_INSTALL.md`, a little over a minute after the issue's verification once corrected
  for it; **2461** (P2) after P1's checks. Both reused the persistent installation as exclusive diagnostic sessions on
  harness `23341a4`, not dirty. The ledger runs from 0001 to 2461 without a gap or an unclosed session; the state
  hash chain is intact, the package integrity held and the state file did not change.
* P1: 1,803 steps, completed; capture of 1,802 snapshots (every decision from index 1), 19 replay checks and 0
  mismatches. P2: 2,883 steps, completed; 2,882 snapshots, 29 replay checks and 0 mismatches. Neither game had an
  observer error, a contract error, a gate rejection or an engine refusal; capture digests equal those in the records.
* After P1, the ledger, the installation and the frozen identities were verified before P2 started.
* Documentation deviation: the registration commit's copy of this document used, in sections 3 and 5, two phrases
  that the repository's documentation policy (the retired-wording rule of `tests/test_docs_policy.py`) reserves for the
  history of the retired engine installation, so the full test suite at that commit fails two policy subtests. The probe's own suites passed before
  registration, but the document was still untracked when the full suite last ran, and that policy test reads tracked
  files only. The two phrases were reworded after the games; no rule changed (the rules are the manifest's and the
  issue's, both unchanged).
* No deviation from the registered execution. The analyses wrote their public outputs first under the server's
  git-ignored `local/` tree (so the working tree stayed clean between the games), and the files were copied unchanged
  into `evaluation/ps1-engine-probe-1/` (`p1.json`, `p2.json`, `gates.json`).

## 14. P1 results (registered)

**Premise: reproduced.** State and trace digests equal the Sprint 2 split-game record up to the trigger; the trigger
is at decision index 533 (cur_step 530) with a group of 4, as predicted. The trigger recomputed from the all-seeing
state with the Sprint 3 reconstruction is at 533 too, and all 532 earlier decisions re-decided offline by a fresh
candidate agree with the hooked seat's. Both channels agree at every snapshot; no hex ever held more than 4 own ground
units.

Each of the 4 stopped units listed action 10 at the decision, the 4 stops were submitted as the hook's notes say, and
each drew one fresh feedback entry **without an error code**. None showed an attributable change in the following 300
steps: the remaining path never emptied, `move_to_stop_remain_time` stayed 0, and action 1 was never listed again. The
hook released all four when its window closed, without a back-off; the deadlock (a cycle of 10 units) lasted from
decision 534 to the end, 1,269 steps, and only the 50-point objective was held at the end.

| Id | Verdict | Evidence |
|---|---|---|
| E1 | **REFUTED** | 4 of 4 stops with no attributable change within 300 steps (no error code) |
| E2 | **REFUTED** | the stops did not take effect at the units' hex while the next hex stayed full |
| E3 | **INCONCLUSIVE** | no unit stopped in place, so no transition could be timed |
| E4 | **INCONCLUSIVE** | no stop took effect, so no transitioning unit existed |

P1-S (descriptive): the replay of every accepted order through M1c reproduces the 238 entries before the stops and the
36 after them (4 infantry units still moving) at offset 0; the stops do not change these entries in either the model or
the game, so this does not discriminate.

## 15. P2 results (registered)

Population: 30 own ground units at the first play decision (2 aircraft and 12 passengers outside the model), none
removed or added later; 69 orders applied; 6 aircraft moves and 3 aircraft shots outside the population; every
applied move echoed.

**F1: FAIL.** All 683 observed entries were predicted, with 0 hex-sequence differences among the 24 units that moved,
no capacity or adjacency violation and complete accounting. But 81 entries were predicted early: 79 by 19 steps, 1 by
20 and 1 by 40 (602 exact); the worst offset, 40, exceeds the registered 1.

**F2: FAIL.** 12 hex sequences differ (worst offset 118); 56 of 64 recorded accepted orders are matched, with 25 of
81 predicted orders unmatched; 2 of 5 occupations are matched.

| Claim | Discriminating events | As predicted | Verdict |
|---|---|---|---|
| T-a wait at entry | 103 | 103 | **SUPPORTED** |
| T-b restart (final run tau - 1) | 113 | 113 (every one exactly tau - 1) | **SUPPORTED** |
| T-c re-wait | 6 | 4 | **REFUTED** |
| T-d arbitration by ascending index | 9 | 8 (2 events discriminated it from first come) | **REFUTED** |
| T-e processing order | 62 entry-rule, 9 arbitration, 107 restart-delay events | 62, 8, 107 | **REFUTED** |

Coverage: 633 entries with a path left, 133 of them waiting at once; ascending-index processing agrees with every one
of the 633 (descending 577, end of step 599); 127 blocked-wait episodes, 113 entered and 14 open at the end; the frozen
Sprint 3 extractors give the same entries and episodes. No keep flag was set on any eligible unit with a path. The
PS-1B trigger held on 1,950 steps, all inside the game's 3 deadlock episodes (1 cycle, 2 chains), of which 1 fired.

## 16. Post-hoc descriptions (written after every registered verdict; they change none)

`scripts/ps1_probe_posthoc.py`, output `evaluation/ps1-engine-probe-1/posthoc.json`:

1. **The stop's footprint in P1.** One step after the stop, `flag_force_stop` turned from 0 to 1 on all 4 units and
   their listed actions became empty; until the end of the game (5,076 unit-steps) they kept that state, their move
   path, `stop` 0 and `move_to_stop_remain_time` 0. `flag_force_stop` was never set on any other unit of P1 or P2. So
   the engine registered each stop and deferred it, consistent with the documented rule that a moving unit first
   completes the hex it is moving into: a unit waiting in front of a full hex is treated as moving into it, never
   completes it while it stays full, and is locked meanwhile, with no action listed, not even another stop. The
   registered E1 defined acceptance by the path emptying or the transition timer, which is why the verdict is REFUTED;
   under either reading the stop did not take effect.
2. **Where F1's early entries come from.** All 81 belong to 6 units. For 4 of them the first early entry follows a move
   ordered while the order's first hex already held 4 own ground units: the engine kept the unit at speed 0 until
   room appeared and then ran a full hex time, the order-time twin of M1c's wait at entry, which M1c does not model;
   each later entry of these units inherits the delay. The other 2 units' delays (20 and 40 steps) stay unexplained.
3. **A post-hoc candidate M1d** (M1c plus "a unit ordered while its first hex is full waits at once") reproduces 681
   of P2's 683 entries exactly (the remaining two late by 20 and 40) and keeps both Sprint 2 games exact (274 and 138
   entries, offset 0). It was derived from P2 and is evidence for nothing until tested prospectively.
4. **T-c and T-d re-read in processing order.** The registered rules judged an arbitration by the lowest indices among
   the contenders and a re-wait by end-of-step occupancy. Processing every unit that entered or left the contested
   hex in the step in ascending index, with the occupancy updated after each move, as M1c does, gives the observed
   entrants in all 15 steps of P2 that had a re-wait. In the contradicting T-d event, a unit leaving the hex was
   processed between the contenders, so the higher-index entrant found room that the lower-index re-waiters had not.
   The registered verdicts stand; the rules, not this observation, were too coarse.
5. **Outside F2's surrogate.** The candidate also fired 3 shots and moved its aircraft 6 times, and its occupations
   depend on what the engine lists; the surrogate models none of this.

## 17. Gate reassessment and disposition

| Gate | Sprint 3 | Sprint 4 | Reason |
|---|---|---|---|
| G1 | PASS | **PASS**, not contradicted | P1 reproduced the Sprint 2 states exactly; both captures agree across channels and never exceed 4 own ground units per hex |
| G2 | FAIL | **FAIL** | E1 and E2 REFUTED: a stop issued to a unit waiting in front of a full hex does not take effect there |
| G3 | FAIL | **FAIL** | F1 and F2 FAIL; T-c, T-d and T-e REFUTED by their registered rules |
| G4 | PASS | **PASS**, not contradicted | every PS-1B trigger step of P2 lies inside a deadlock episode; before its trigger P1 made the candidate's decisions |
| G5 | NEEDS_ENGINE_PROBE | **SHELVE** | E1 refuted with no stop taking effect on any blocked unit: PS-1B's only intervention is unavailable, and no other approved alternative exists |

**What G2's failure invalidates.** PS-1B's recovery begins by stopping the waiting group; on engine 4.1.0 that stop is
registered but deferred until the unit enters the full hex, which in a deadlock never happens, and it removes every
listed action from the unit. The back-off, the cooldown and the selection never get to act. Any future capacity-aware
movement would need a different mechanism: prevention before a column forms (admission at dispatch, which PS-1A
attempted but which failed non-interference), or intervention on units that are still traversing, whose stop
behaviour remains unobserved.

**Separated as required:**

1. *Observed engine facts* (P1, one game; P2, one game): a stop on a waiting unit is echoed without error, sets
   `flag_force_stop`, withdraws every listed action and keeps the move path for at least 1,269 steps while the next hex
   stays full. A unit entering a hex in front of a full hex waits at once (103 of 103), and a restart takes a hex time
   counting the restart step (113 of 113).
2. *Prospectively supported model claims*: T-a and T-b of M1c within P2's conditions. No other claim.
3. *Conditional simulation results*: none recomputed. The Sprint 3 certificates assume a stop that takes effect in
   place, which P1 contradicts; they stay descriptive and no longer describe a reachable recovery.
4. *Remaining unverified*: the stop on a traversing unit; whether a stopped unit counts toward capacity; M1d, the
   order-aware arbitration and the two unexplained delays, all post hoc; the transition length.

Research disposition: **SHELVE** for PS-1B. T1 stays shelved, now without a pending play-stage remedy; the deadlock
itself remains a known property of `baseline-v2`'s play stage, recorded in the frontier as an open problem.

## 18. Limits

* One game per probe. P1 shows what the engine does to a group of waiting vehicles in one deadlock; P2 tests M1c on one
  scenario. Neither establishes engine-wide behaviour.
* The registered T-c and T-d rules ignored leaving units processed between the contenders; their REFUTED verdicts stand
  as registered, and the post-hoc re-reading is not a substitute for a registered test.
* M1d and the order-aware reading were derived from P2 and need a fresh game before they can support anything.
