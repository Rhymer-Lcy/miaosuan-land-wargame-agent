# Sprint 30: T13-K1 keep-one garrison, exploratory pilot

**EXPLORATORY TRACK — AT MOST FOUR ENGINE SESSIONS (2798 TO 2801) — NOT A CONFIRMATION — NOTHING PROMOTED — NOTHING
UPLOADED**

Dates are business dates in UTC+8 (2026-10-10). Sections 1 to 5 were committed and pushed before the historical
preflight ran; section 6 (the pilot card and its stop rules) before session 2798 was opened. No registered section is
edited afterwards; results follow in their own sections.

## 1. Starting state and the owner's authorization

| Item | Identity |
|---|---|
| Repository | `main` `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85`, tree `a7803726953142ff8cd090a55284d0232afdc511`, on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,797 sessions opened and closed, none unclosed; ledger file SHA-256 `70ae38f21e0ac2c0d9c2772a8fe73b5b3a6dbdcc8f4e62af8dbc4443d4df8036` (as at the close of Sprints 27 to 29); session 2798 unopened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, unchanged |
| Privacy baseline | 106 accepted hit lines |

The owner authorized, for this sprint only: one exploratory implementation of Sprint 29's portfolio item H1 (T13-K1,
keep one eligible ground unit on an objective the side already holds); a short historical action-level preflight; its
registration and tests; and **at most four** new local engine sessions, 2798 to 2801, played one at a time with a stop
check after each. Session 2802 and Sprint 29's 20-session proposal are not authorized. The ceiling is not a requirement
to play four games. No retry or replacement game, no promotion, no platform upload, no change to the frozen
`baseline-v2`, the platform package or any historical conclusion. T13-K1 is a new increment; the closed T13-D1
(`docs/SPRINT25_T13_D1.md`) is neither modified nor reinterpreted.

## 2. Isolation from the platform compatibility work

Another session was working on platform compatibility at the start of this sprint. On the workstation the shared
checkout held its uncommitted changes to the package builder and its test; on the evaluation server it ran a replay
check from its own folder that imports the server checkout's source tree. Nothing of that work is touched, staged,
stashed, reset or merged here:

* the workstation work happens in a separate `git worktree` on the branch `sprint30-t13-k1`, created from the committed
  base `08aff3f` (its tree equal to the one above); the shared checkout and its changes are never written;
* on the evaluation server the branch reaches the repository by bundle into a separate worktree; the server checkout's
  branch, HEAD and files are never changed. That worktree reaches the persistent engine installation, the ledger and
  the private historical captures through links to the existing ignored folders, so there is still exactly one
  installation and one ledger;
* only the branch `sprint30-t13-k1` is pushed; `main` is not changed by this sprint;
* the canary package, its builder and the platform adapter are not modified.

Server CPU policy (`docs/SERVER_RESOURCE_POLICY.md`): the topology check matched the policy (2 sockets, 16 physical
cores each, SMT siblings `i` and `i + 32`, node 0 = CPUs 0-15 and 32-47); the colleague's job was pinned to node 1, so
the mode is shared and every job of this sprint runs pinned to node 0. Engine games run serially, one exclusive session
each; the preflight uses a pool of at most 8 worker processes on node 0.

## 3. The candidate: `t13-keep-one-k1`

Module `src/miaosuan_agent/experiments/t13_keep_one_k1.py` on the exploratory add-on
(`experiments/exploratory_addon.py`): frozen `baseline-v2` decides first on the seat's own current observation and
memory, unchanged; one rule then edits that decision.

* **Held objective and centre**: a `cities` entry of the seat's observation whose flag is the side's colour; its centre
  is its hex.
* **Occupants**: own ground units (type 1 or 2, artillery included) whose current hex is the centre.
* **Departing**: an occupant with a non-empty `move_path` (an accepted movement under way) or one for which
  `baseline-v2` emits a MOVE now. Every other occupant **remains**.
* **Trigger** (play stage, per held objective, in increasing centre order): at least one occupant, every occupant
  departs, and at least one departs by a `baseline-v2` MOVE. If an occupant remains, nothing changes. If every occupant
  departs under earlier movement only, the case is uncovered (a withheld order cannot cancel an accepted path) and
  nothing changes.
* **Eligible holder**, in order, the first failing level recorded: `A_stationary` (speed not positive), `B_no_route`
  (empty `move_path`), `C_no_transition` (the `stop` flag not 0; `move_to_stop_remain_time` and
  `change_state_remain_time` not positive), `D_no_transport_transition` (`get_on_remain_time`, `get_off_remain_time`
  not positive), `E_single_departing_move` (`baseline-v2` emits exactly one action for it, a MOVE with a non-empty
  route of integer hexes not ending on the centre). A to D are Sprint 28's idle levels of the same names, restated (a
  test compares the two). A missing field counts as the absence of a transition. Reading of the brief: "no pending
  movement or stop transition" is levels B to D, so a unit that has just arrived and is still in its stop transition
  is not an eligible holder.
* **Selection**: the eligible holder with the longest free-flow travel time of its `baseline-v2` MOVE (the sum over the
  route of `experiments.t9_batch.path_times`: per hex `720 / basic_speed * entry cost`, rounded per hex, in the unit's
  movement mode from its current hex); ties go to the lower unit id. A holder whose time is unreadable (unknown mode or
  speed, a route edge outside the cost graph) is not ranked; if none can be ranked the objective is skipped
  (`no_travel_time`) and nothing changes.
* **Edit**: that one MOVE is withheld. Nothing is added, replaced, reordered or constructed: no stop, no route change,
  no reassignment, no change to fire, occupation, embarkation or any other unit. One holder per objective at most;
  distinct centres hold distinct units, so edits never conflict.
* **Stateless**: no add-on memory; every decision is recomputed from the current observation, so a holder is released
  when the objective is no longer held, another occupant remains, the holder is gone, or it no longer qualifies.
  `baseline-v2`'s own memory is only its deployment flag, so a withheld MOVE cannot desynchronise it.
* **Failure**: an error inside the rule yields `baseline-v2`'s decision with the error recorded in the trace (the
  wrapper's fail-closed path); in the pilot any such error is an integrity stop, never a successful decision.

## 4. Historical feasibility preflight (frozen before it runs)

`scripts/s30_preflight.py` with the rules of `src/miaosuan_agent/evaluation/s30_preflight.py`; inputs pinned in
`evaluation/s30-t13-k1/preflight-inputs.json`. Offline, on the evaluation server.

* **Populations**, never pooled into one figure: **HH**, the `baseline-v2` seat of the four Sprint 12 head-to-head
  games in 2130511121 (two per colour; the opponent was the T9-v3 candidate); **HI**, the three Sprint 10 games of
  `baseline-v2` against the inert control (2120531121 C3, 1930331196 C3, 1930331196 C2); **H0**, the eight
  replay-corpus games, both seats, recorded `baseline-v0` actions with `baseline-v2` reconstructed. HH and HI are
  genuine `baseline-v2` trajectories; H0 is off-policy. Sprint 23's pinned job list, loader and `baseline-v2`
  reconstruction are reused unchanged.
* **Fidelity anchors**: H0 33,696 decisions, 33,680 play decisions, 123 decisions where reconstructed `baseline-v2`
  differs from the record; HH 11,524 and HI 8,643 decisions, every one equal to the recorded seat; 16, 4 and 3
  side-games.
* **Independent check**: at every decision a restatement of the rule written apart from the candidate's code (its own
  reading of the observation and its own free-flow sum over the cost graph) must explain every withheld action and find
  no missed trigger.
* **First divergence**: a side's first decision at which the candidate's list differs from `baseline-v2`'s. Valid in
  HH and HI; in H0 only when the recorded actions equal `baseline-v2`'s at every earlier decision of that seat.
  Withholdings after it lie on recorded states the candidate would not reach: post-divergence diagnostics only.
  **Verified opportunity**: a side-game with a valid first divergence and no independent-check finding.
* **Measured**: per held objective and play decision the rule's outcome; departure episodes (maximal runs of
  decisions at which every occupant of a held objective departs) by their first outcome; units already moving and
  stationary eligible units ordered at an episode's start; failing eligibility levels of ordered occupants; per side the
  first divergence (step, objective label, holder class, occupants, travel time, transit routes through the centre),
  whether an enemy had been seen before it, the first own shot, and historical onward labels (whether the holder was,
  on the record, the first owner of its MOVE's destination; whether the objective was later lost on the record).
* **Stop, first match**: `K1_PREFLIGHT_INVALID` (an anchor, an integrity check or the independent check fails);
  `K1_PREFLIGHT_INADEQUATE` (no verified opportunity among the two HH red side-games, or none among the two HH blue
  side-games, or fewer than two HI configurations with one): **no engine session is opened**; otherwise
  `K1_PREFLIGHT_PASS`.
* **Inert games of the pilot**: the first two of 2120531121 C3 (the configuration in which withholding moves already
  cost an objective: T9-v1 as blue against the inert control), 1930331196 C2 (another scenario, the other colour),
  1930331196 C3, in that order, that have a verified opportunity. All three are among Sprint 29's proposed harm
  configurations and they are the only ones with a genuine `baseline-v2` full-step record.

## 5. Historical controls

The same run reads the registered shoot-reservation experiment's group C records (frozen `baseline-v2`, 15 games per
configuration; each record pinned by SHA-256 in the inputs) for 2120531121 C3 (blue), 1930331196 C2 (red), 1930331196
C3 (blue) and 2130511121 C1 (both seats), and writes `evaluation/s30-t13-k1/controls.json`: for each the occupy,
attack, remain and total values and the margin (the seat's total minus the opponent's, checked against the engine's
own margin field), with minimum, maximum and mean. The pilot's thresholds (section 6) are read from that file, never
typed from memory.

## 6. Pilot card: not registered

The preflight's stop fired (section 7), so no pilot card was built, no candidate digest was pinned in a run card, the
pilot's harm stops and dispositions were never registered, and no engine session was opened. The draft full-step
observer for the pilot (a seat-local reconstruction of every decision of both seats, after Sprint 27's) was not
committed; it is kept privately for a later pilot.

## Amendment A1 (after the preflight run)

After the preflight had run, the full workstation suite failed one test: Sprint 28's frozen identity test allows only
Sprint 28's own files to name its shadow module, and the candidate's docstring named that module (where section 3 cites
Sprint 28's idle levels), as did the candidate test that compared the two. Sprint 28's test is not edited, and neither
are sections 1 to 5. The correction:

* the candidate's docstring cites Sprint 28's report instead of the module path; nothing else in the file changed (the
  module's syntax trees with every docstring removed are identical before and after);
* the candidate test compares the four level names, their order and the transition fields with Sprint 28's registered
  `evaluation/s28-t12-o1/protocol.json`, and checks each level's boundary on the same cases with the expected level
  written out, instead of importing Sprint 28's module; "a test compares the two" in section 3 refers to this test;
* the candidate's file digest is pinned in the preflight inputs, so the inputs were frozen again (one line changed:
  that digest) and the preflight was run again. Both public files are identical to the first run's apart from the
  inputs digest they carry, the private rows are byte-identical, and the disposition is unchanged. The mutation record
  was regenerated on the amended sources.

The first run's outputs are kept privately. The candidate's policy source (`baseline-v2`'s 22 files, the add-on wrapper,
`experiments/t9_batch.py` and the candidate module) is
`56f3f147cb8ef23ef37e6ed815357b57d5882591079eec489d6affd3d9072b21` after the amendment
(`2b04907f8f667b5eb80c36112a71ef8ee1a114850b03b65244062e395d08e6e6` before); it was never pinned in a run card. Process
lesson: the targeted policy tests run before the registration push did not include Sprint 28's identity test; the full
suite runs before any registration push.

## 7. Preflight results (2026-10-10)

Every figure in R1 to R5 is read from the committed `evaluation/s30-t13-k1/preflight.json` and `controls.json`, which
`scripts/s30_preflight.py run --check` regenerates byte for byte on the evaluation server; R6 is post hoc and labelled.

### R1. Order of work

Sections 1 to 5, the candidate, the preflight rules and driver, their tests and the frozen inputs were pushed on the
branch at 2026-10-10T02:20:36+08:00 (`87a93ac8c1ea1f9eed6a632f45b4a2158488a042`). The evaluation server's worktree was
fast-forwarded to that commit and the preflight was run once (8 worker processes on node 0); a second run with
`--check` reproduced both public files and the private rows byte for byte. No definition, threshold or stop was changed
after the run. Amendment A1 then re-froze the inputs and repeated the run with identical results apart from the
inputs digest; the committed files are the repeated run's.

### R2. Fidelity

All anchors are reproduced exactly: H0 33,696 decisions, 33,680 play decisions and 123 decisions where reconstructed
`baseline-v2` differs from the record; HH 11,524 and HI 8,643 decisions, every one equal to the recorded seat; 16, 4
and 3 side-games. The independent restatement of the rule found nothing at any decision of any side-game (0 findings):
every withholding the candidate made was explained, and no trigger with an eligible holder was missed.

### R3. What the rule found, by population

Counts are objective-decisions (one held objective at one play decision of one side) unless stated otherwise.

| | HH | HI | H0 |
|---|---:|---:|---:|
| side-games | 4 | 3 | 16 |
| no own ground unit on the centre | 20,074 | 20,677 | 31,186 |
| an occupant remains (no change) | 10,544 | 13,149 | 16,959 |
| every occupant already moving (uncovered) | 5,637 | 838 | 4,541 |
| every occupant departing, none eligible | 123 | 43 | 137 |
| withheld | 0 | 0 | 2 |
| departure episodes | 66 | 21 | 78 |
| of which first outcome: none eligible | 66 | 21 | 75 |
| of which first outcome: every occupant already moving | 0 | 0 | 1 |
| of which first outcome: withheld | 0 | 0 | 2 |
| ordered occupants, failing level `C_no_transition` (objective-decisions summed) | 199 | 73 | 239 |
| ordered occupants, eligible (objective-decisions summed) | 0 | 0 | 6 |
| side-games with a first divergence | 0 | 0 | 1 |
| valid first divergences, verified opportunities | 0 | 0 | 0 |

The genuine side-games one by one (departure episodes; objective-decisions with every occupant departing and none
eligible): HH p01 `baseline-v2` blue 19 and 38, p02 red 11 and 19, p03 blue 16 and 35, p04 red 20 and 31; HI
1930331196 C2 red 7 and 18, 1930331196 C3 blue 9 and 10, 2120531121 C3 blue 5 and 15. None has a first divergence.

H0's only first divergence (2130511121 red, step 803, two withholdings on the record) lies after that seat's recorded
`baseline-v0` actions first differ from `baseline-v2`'s, so it is not a valid action-level fact.

### R4. Disposition: `K1_PREFLIGHT_INADEQUATE`

No verified first-divergence opportunity among the HH red side-games, none among the HH blue side-games, and none in any
HI configuration, so no inert configuration could be selected. Under the frozen stop **no engine session was opened**:
the ledger still ends at session 2797 and session 2798 is unopened. The pilot's dispositions (`H1_PILOT_INVALID`,
`H1_PILOT_REJECT`, `H1_PILOT_INCONCLUSIVE`, `H1_PILOT_PROMISING`) were never reached: the pilot did not start, and this
is not a four-game result of any kind.

### R5. Historical controls (descriptive; no pilot read them)

| Configuration (`baseline-v2` seat) | Occupy over 15 games | Margin minimum | Margin mean | Margin maximum |
|---|---|---:|---:|---:|
| 2120531121 C3 blue (inert opponent) | 310 in all 15 | 559 | 1765/3 | 599 |
| 1930331196 C2 red (inert opponent) | 310 in all 15 | 258 | 4094/15 | 274 |
| 1930331196 C3 blue (inert opponent) | 310 in all 15 | 570 | 570 | 570 |
| 2130511121 C1 red (mirror) | 0 in 9, 50 in 6 | -1,055 | -13049/15 | -719 |
| 2130511121 C1 blue (mirror) | 390 in 6, 440 in 9 | 719 | 13049/15 | 1,055 |

The mirror margin's standard deviation is 114.66 (sample) and 110.78 (population); Sprint 29 printed it as 115. Margins
equal the engine's own margin field in every record.

### R6. Why no holder was eligible (post hoc, read after the disposition; changes nothing)

`local/diagnostics/s30/posthoc.py` re-read the same pinned populations and, at the start of every departure episode
with no eligible holder, looked at each occupant `baseline-v2` ordered off the centre:

| | HH | HI | H0 |
|---|---:|---:|---:|
| ordered occupants at those episode starts | 110 | 38 | 135 |
| failing level `C_no_transition` | 110 | 38 | 135 |
| of which `stop` flag 0 and `move_to_stop_remain_time` positive | 110 | 38 | 135 |
| of which `change_state_remain_time` positive | 0 | 0 | 0 |
| remaining stop transition, median (minimum to maximum), steps | 74 (17 to 75) | 75 (73 to 75) | 74 (4 to 75) |
| steps since arriving on the centre, median (maximum) | 1 (58) | 0 (2) | 1 (71) |
| the side's flag on that centre turned to its colour during the unit's stay | 71 | 17 | 105 |

So `baseline-v2` sends its units onward the moment they stand on an objective it holds, usually within a step of arrival
and often after their own arrival had captured it (last row), while every one of them is still in the 75-step stop
transition that follows a move. A unit that has completed that transition on a held objective is one `baseline-v2` is
not ordering away: those objectives fall under "an occupant remains". Under the brief's requirement of "no pending
movement or stop transition", the eligibility clause and the departures that lose objectives are mutually exclusive in
every population examined.

**Counterfactual reading, post hoc only**: if a unit with no route whose only transition is the stop transition were
an eligible holder (a state change would still disqualify), the same rule would have its first divergence at a valid
prefix in all four HH side-games (blue at step 161 on the 50-point objective A in p01 and p03; red at step 401 on the
50-point objective D in p02 and p04; withholding decisions on the record: p01 31, p02 17, p03 28, p04 28) and in all
three HI configurations (1930331196 C2 at step 361, 2120531121 C3 at step 341, 1930331196 C3 at step 521), and at a
first divergence in 10 H0 side-games, 4 of them valid. These are opportunity counts on recorded states, not effects.
Engine evidence on the mechanism such a reading would rely on is limited to one vehicle in one game: in Sprint 22's
session 2796 the carrier's `baseline-v2` MOVE was withheld for 75 decisions after its arrival, while it settled, and
it stayed on its destination (`docs/SPRINT22_T2_TRANSPORT_PROBE.md`).

### R7. Tests and mutation

* Candidate tests (`tests/test_t13_keep_one_k1.py`, 32 tests): the trigger and each objective outcome, every
  eligibility level at its boundary, missing fields, unheld objectives, the non-play stage, selection by travel time,
  its tie rule and unreadable times, two objectives at one decision, artillery, infantry, aircraft, enemies and
  passengers, unchanged inputs and action order, malformed observations and the fail-closed wrapper, the registered
  travel relation, the executable policy with the real `baseline-v2` in a held-objective stand-in world
  (`tests/fixtures/s30_engine.py`), identity, imports, and the restatement of Sprint 28's idle levels.
* Preflight tests (`tests/test_s30_preflight.py`, 13 tests), results binding (`tests/test_s30_results.py`, 6 tests)
  and the server regeneration test (`tests/test_real_s30.py`).
* Mutation (`scripts/mutate_s30.py`, record `evaluation/s30-t13-k1/mutation.json`): the first run caught 30 of 31
  planted defects; the survivor (infantry not counted as an occupant) was a test gap, closed by a test; the final run
  on the committed tests caught 31 of 31 after the unmutated tests passed in the copy.
* While building the preflight, review before the run caught three public texts with words made only of digits (the
  sanitizer would have refused them) and per-side episode lists that could exceed the public size limit; three test
  plants were found ineffective by their own failing tests and corrected. After the run, a commit order in which one
  test expected a file added two commits later was re-cut before any push, and every re-cut commit was tested.

### R8. Evidence limits

The genuine populations are seven side-games in three scenarios; HH's opponent was the T9-v3 candidate, not
`baseline-v2`. The preflight measures whether the frozen rule can act, not whether a garrison helps. Nothing here
estimates a score effect; nothing is promoted or uploaded.

### R9. Close-out

* **Engine**: no session was opened. Read-only verify on the evaluation server after the work: 2,797 sessions opened
  and closed, none unclosed, integrity ok, state chain continuous, the last event the close of session 2797; ledger file
  SHA-256 `70ae38f21e0ac2c0d9c2772a8fe73b5b3a6dbdcc8f4e62af8dbc4443d4df8036`, unchanged. No installation, state file or
  engine configuration was touched.
* **Platform canary**: rebuilt from this branch into a scratch folder,
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, isolated smoke 62 steps with 0 mismatches; the
  shared checkout's copy has the same digest. This sprint changed neither the package, its builder nor the adapter.
* **Tests**: the workstation suite in this branch's worktree (which has no ignored private folders, so more tests
  skip) ran 2,427 tests, 114 skipped, exit 0. On the server the Sprint 30 tests, Sprint 28's shadow tests and the
  documentation-policy tests ran 99 tests, OK, including the byte-for-byte regeneration of the preflight. The
  multi-hour private server suite was not rerun: apart from documentation, the sprint added files and amended only its
  own candidate's docstring.
* **Document check** (`local/diagnostics/s30/doc_check.py`): every anchored clause and table row rebuilt from the
  committed files, the private post-hoc output and the logs; every number printed here derived or declared; 10 of 10
  planted single-number errors caught.
* **Privacy**: the scan of every reachable blob before each push is compared as a multiset with the 106 accepted hit
  lines; the results are in the hand-over and in the private logs.
* **Concurrent work**: the platform-compatibility changes in the shared checkout (two modified files) and its server
  folder were not touched; the server checkout stayed on `main` at `08aff3f`, clean; `main` was not changed on
  GitHub. Only the branch `sprint30-t13-k1` was pushed. Its final head, identical on the workstation, GitHub and the
  server, is given in the hand-over; the server worktree is removed after that check, and the private evidence stays
  under the ignored `local/` folders.

### R10. Recommended next task (one)

**The owner's decision on the stop transition, then this preflight on a new identity before any engine use.** The
question Sprint 30 leaves open belongs to the owner: may a unit with no route whose only transition is the stop
transition that follows a move (stop flag 0, `move_to_stop_remain_time` positive) be kept as the holder? If yes, a new
candidate T13-K2 differs from K1 only in level C (a state change still disqualifies), gets its own identity, and is run
through this sprint's frozen preflight unchanged before any session; R6's post-hoc count suggests valid first
divergences in all seven genuine side-games, but only the rerun counts. If it passes, the four-game pilot of this brief
follows under a new authorization, with its card, harm stops and dispositions written before session 2798. If no,
T13-K1 stays not run.
