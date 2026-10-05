# Sprint 12 proposal: a small exploratory screen of `t9-batch-capacity-v3`

**DRAFT — UNAPPROVED — NO ENGINE AUTHORIZATION**

This document proposes an engine screen; it does not register or start one. Nothing in it authorizes an engine
session: no run card exists for the screen, the candidate is still in no run card, and the engine ledger stays closed
through session 2786. The screen may start only after the owner approves it explicitly and a separate registration
commit (section 17) has been reviewed, pushed and checked. Dates are business dates in UTC+8; the draft was written on
2026-10-05.

The machine-readable companion `evaluation/s12-batch-allocator-draft/draft.json`, built by
`scripts/t9_batch_screen_draft.py` from committed files (`--check` regenerates it byte for byte), holds the proposed
schedule, every reference value the rules below use and the behaviour of those rules on existing games. It is not a
run card: its schema is `miaosuan-proposal-draft/1`, it carries `executable: false`, and the exploratory runner refuses
any file whose schema is not the run-card schema.

## 1. Purpose

The screen asks two questions, in this order:

1. Does `t9-batch-capacity-v3` keep enough of T9-v1's head-to-head behaviour in 2130511121 to remain worth pursuing?
2. Does it repair, or at least avoid, the three adverse configurations against the inert control (2120531121 C3,
   1930331196 C3, 1930331196 C2) in real engine trajectories, and through the mechanism it was designed for?

It is an `EXPLORATORY` screen (`docs/EXPLORATORY_TRACK.md`): directional, game-level evidence with mechanism
certificates. It is not a powered comparison, it applies no significance test, it uses historical controls only as
descriptive references, and no result of it can promote a baseline. A favourable screen can only support a separately
registered confirmatory study with fresh games.

## 2. Identities and starting state

| Item | Identity |
|---|---|
| Candidate | `t9-batch-capacity-v3`: `experiments/exploratory_addon.py` and `experiments/t9_batch.py` on the frozen `baseline-v2`; policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8` (recomputed from the checkout; equal to Sprint 11's) |
| Frozen baseline (opponent and reference) | `baseline-v2` (`baseline-v2-candidate-shoot-target-reservation`), policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| Inert control | `inert-v0` |
| Historical candidates (not played) | T9-v1 `0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa`; T9-v2 `66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece` |
| Repository | `main` `0eab5f780f41c26cbfa57344c1960568584807f6`, tree `818f432eea82226eb25471d254b7edc5004e571d`, the same on the workstation, GitHub and the evaluation server when this draft was started |
| Engine ledger | 2,786 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only `verify` on the server) |
| Runtime | `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), engine 4.1.0, CPython 3.10 |

The candidate's rule, unchanged: it keeps `baseline-v2`'s selected objective and route; it considers all current
claimants of an objective together; incumbent movers are never displaced; a mover or claimant that cannot physically
arrive before the end of the game holds no place; selectable new claimants are ranked by free-flow arrival time, then
route cost, path length and unit id; at most four counted commitments per objective; overflow stays on its own route
through a staging hex that holds at most three own ground units, never another objective; every other `baseline-v2`
action is unchanged. Its source is not edited for this proposal or for the screen.

## 3. What is known, and what is not

* Sprint 9 (registered): T9-v1 in 2130511121 head to head against `baseline-v2`, seat-averaged improvement +305.47,
  95% interval 172.87 to 611.24. In that primary population 842 of the 1,294 ground moves emitted by the 30 candidate
  seats were cross-objective replacements. That result belongs to T9-v1 and is not inherited by v3, which forbids
  cross-objective reallocation.
* Sprint 10 (exploratory): T9-v2, which also forbids redirection, kept about +43 seat-averaged in one game per seat
  (H1 red -729, H2 blue 815). It restored 1930331196 C3 (570 twice) and C2 (274 twice) but not 2120531121 C3 (423 and
  403; the fifth objective stayed neutral).
* Sprint 11 (offline only): on the frozen states v3 removes the unreachable reservations behind the 2120531121 C3
  block and selects the nearer, faster claimants; its 1930331196 C3 opening allocation equals T9-v2's; in 1930331196
  C2 it seats the four fastest vehicles where T9-v2 seated three vehicles and one infantry unit. In the primary
  scenario's replay-corpus game it held back 87 objective moves where T9-v2 held back 86, and it differs from T9-v2
  there mainly by granting no unreachable place. None of this is a game-score effect.
* So the most likely failure is in the primary scenario, and that is tested first.

## 4. Proposed games and order

At most 12 sessions after session 2786, in four stages. Each stage is a separate run card. P1's card is part of the
registration; each later card is built and committed only after the previous stage's report has been committed and
permits it (section 6).

| Position | Stage | Proposed card | Configuration | Red | Blue | Runs only if |
|---:|---|---|---|---|---|---|
| 1 | P1 | `s12-v3-primary-1` | 2130511121 H1 | v3 | `baseline-v2` | the screen is approved and registered |
| 2 | P1 | `s12-v3-primary-1` | 2130511121 H2 | `baseline-v2` | v3 | as above |
| 3 | P1 | `s12-v3-primary-1` | 2130511121 H1 | v3 | `baseline-v2` | as above |
| 4 | P1 | `s12-v3-primary-1` | 2130511121 H2 | `baseline-v2` | v3 | as above |
| 5 | P2 | `s12-v3-primary-2` | 2130511121 H1 | v3 | `baseline-v2` | the P1 report finds no stop of section 6.1 and no interim stop of section 6.3 |
| 6 | P2 | `s12-v3-primary-2` | 2130511121 H2 | `baseline-v2` | v3 | as above |
| 7 | A1 | `s12-v3-adverse-1` | 2120531121 C3 | `inert-v0` | v3 | the primary report classifies the primary PRESERVED_DIRECTIONALLY or AMBIGUOUS |
| 8 | A1 | `s12-v3-adverse-1` | 1930331196 C2 | v3 | `inert-v0` | as above |
| 9 | A1 | `s12-v3-adverse-1` | 1930331196 C3 | `inert-v0` | v3 | as above |
| 10 | A2 | `s12-v3-adverse-2` | 2120531121 C3 | `inert-v0` | v3 | the A1 report names a replication trigger for this configuration (section 6.4) |
| 11 | A2 | `s12-v3-adverse-2` | 1930331196 C2 | v3 | `inert-v0` | as above, for this configuration |
| 12 | A2 | `s12-v3-adverse-2` | 1930331196 C3 | `inert-v0` | v3 | as above, for this configuration |

* The primary scenario comes first, alternating the two candidate seats, so that a stop after any game leaves the seats
  as balanced as possible. Nothing else is played until the primary report exists.
* Within A1, 2120531121 C3 comes first: it is the configuration the end-of-game test was designed for and the only one
  with a structural stop of its own (section 6.4). 1930331196 C2 follows because there v3's opening differs from
  T9-v2's; 1930331196 C3, where it equals T9-v2's, is last.
* The A2 card holds only the configurations whose A1 game triggered a replication; its contents follow mechanically
  from the committed A1 report. Without a trigger, no A2 card is built.

## 5. Session budget and ledger accounting

* Ceiling: 12 sessions opened after session 2786. If no stop fires and no replication is triggered, the screen uses
  9. Unused sessions are not reallocated to other games, carried over or spent to finish a sequence.
* Every game is one exclusive diagnostic session of the persistent installation, played serially (1 worker), under
  `baseline-v1-runtime-r2`, with the frozen scenarios' inputs, caps (`max_time + 1 + 100` steps, 2,981 in these
  scenarios, and 1,800 s wall time per game) and randomness procedure (global seed 20260929, a new process per game,
  `PYTHONHASHSEED=0`), exactly as in the earlier exploratory cards. Session numbers are whatever the ledger assigns.
* Every stage card carries `ledger_base_session` 2786 and `sprint_session_cap` 12; the existing budget check refuses
  a stage, and each game, when the sessions already opened after 2786 plus the planned ones would exceed 12.
* No game is retried, replaced or added. A game that does not complete still counts toward the ceiling and stops the
  screen (section 12).
* After each stage: `engine_install.py verify` (integrity ok, state continuous, none unclosed) and a ledger audit
  showing that every session after 2786 is one of this screen's games, opened once and closed with integrity ok.

## 6. Stop and continuation rules

All rules are fixed by this draft before any game. None may be changed after the first Sprint 12 game; a change would
need a new approval and a new registration, and games already played would keep the rules they were played under.

### 6.1 Immediate stops

The stage runner plays one game at a time. After each game, before the next one starts, the game's own invariants
(S4 to S13) are checked from its record and captures by the game entry point, which exits with a distinct status, and
the runner then checks the session (S1, S2) and, after the 2120531121 C3 game, the structural rule (S14); any non-zero
status or fired rule ends the stage. S3 is checked on every public output before it is committed and on the
repository before every push. A stop ends the screen; resuming needs a new owner decision.

| Code | Stop when |
|---|---|
| S1 | engine-installation integrity fails: a session closes with integrity not ok, `verify` fails, or the state chain breaks |
| S2 | the ledger is inconsistent: a session after 2786 that is not a game of this screen, an unclosed or recovered session, a session opened twice, or more than 12 sessions after 2786 |
| S3 | privacy exposure: a unit id, hex coordinate or raw observation in a tracked file or public output, or a new privacy-scan hit not adjudicated benign |
| S4 | an unexplained contract failure: any contract error in any seat, or a game that does not complete |
| S5 | a candidate add-on error: the wrapper's fallback to `baseline-v2`, or the allocator's own fail-closed path (an `error` change) |
| S6 | a replay mismatch in any seat's agent replay check |
| S7 | the observer's seat-local reconstruction of `baseline-v2` and of v3 differs from the live decision (actions, add-on changes or `baseline-v2`'s trace digest) |
| S8 | an objective commitment above four: at any decision, v3's counted places of an objective (standing units, counted movers and the claimants selected in that decision) exceed four, or more than four own ground units stand on one hex |
| S9 | a staging endpoint above the staging cap: at a decision that stages a move, v3's endpoint count of the staging hex (own ground units standing there or with a path ending there, that decision's staged moves included) exceeds three |
| S10 | a staged move that is not a strict prefix of `baseline-v2`'s path for that unit in that decision, or that ends on an objective |
| S11 | cross-objective redirection: an emitted move whose last hex is an objective other than `baseline-v2`'s destination for that unit in that decision |
| S12 | an unrelated `baseline-v2` action changed: any action other than a ground move to an objective is missing, altered or reordered, or a move is emitted for a unit `baseline-v2` did not move |
| S13 | a project-gate rejection of an emitted action, or a refusal class in a v3 seat that neither `baseline-v2`'s known classes nor a `baseline-v2` seat of this screen explains |
| S14 | a structural design failure in 2120531121 C3 (section 6.4) |

S8 is defined on v3's counted places, not on every path that ends on the objective. A mover that can no longer arrive
before the end holds no place by design, so the raw count of paths ending on an objective may exceed four while the
counted places do not; every such event is reported with its cause, and it is not a stop. A staged move that the
project gate rejected inside the allocator (it is then withheld, by design) is reported and explained in the stage
report; an unexplained one stops the screen under S13.

Not stops: an ordinary tactical loss; the known refusal classes of `docs/REFUSAL_TAXONOMY.md` (code 516, a shot at a
target destroyed earlier in the step; code 203, an action of a unit destroyed earlier in the step; code 1804, a
duplicate occupation) when `baseline-v2` shows the same class; the descriptive flags of sections 7 and 8.

### 6.2 Definitions for the primary rules

From Sprint 9 phase A (`evaluation/t9-confirmation-1/phase-A.json`), with the seat facts measured by Sprint 9's own
capture definitions, which the screen reuses unchanged (section 9):

* coverage: a seat's mean number of objectives whose flag is its own, over the post-step states of the play stage;
* a **T9-v2-like** game: an H1 game whose red coverage is below 0.618 (exactly 0.6184..., the lowest of T9-v1's 15
  registered H1 games), or an H2 game whose blue margin is below 865 (the lowest of T9-v1's 15 registered H2 games);
* a **collapse** game: an H1 red margin below -1,195 or an H2 blue margin below 217 (the lowest of the 15 fresh
  Sprint 9 `baseline-v2` C1 margins of that seat);
* the seat average: half the sum of the mean H1 red margin and the mean H2 blue margin (Sprint 9's estimand form; the
  mirror term is 0 under the zero-sum margin convention).

Why these two indicators: the seat margins of T9-v1 and `baseline-v2` overlap heavily as red (T9-v1 H1 -1,003 to
1,035, median -737; `baseline-v2` red -1,195 to -217, median -919), so an H1 margin says little, while red coverage
separates them (T9-v1 0.618 to 5.386, median 1.210; `baseline-v2` 0.160 to 2.763, median 0.378, with 11 of 15 below
0.618). As blue the margin itself separates them better (T9-v1 865 to 1,435, median 1,061; `baseline-v2` 217 to 1,195,
median 919). Both Sprint 10 T9-v2 games are T9-v2-like by these definitions: as red its coverage was 0.4211 in 50-step
snapshots, at most 0.4531 in the every-step definition given the calibration below, and as blue its margin was 815. No
Sprint 8 T9-v1 game is: the three exploratory H2 margins are 1,077 to 1,297, and the three H1 snapshot coverages are
0.7544, 1.1930 and 1.1579, all above the floor even after the largest calibration difference.

Blue coverage is not used in a rule. T9-v1's 15 registered values lie in a narrow band (5.057 to 5.426) and two of the
three Sprint 8 T9-v1 snapshot values (5.4561 and 5.4737) lie just above it within the snapshot error, so a rule on it
could call a T9-v1-like game T9-v2-like. It is reported descriptively.

The snapshot calibration: the same 50-step approximation computed on the 45 Sprint 9 phase A games differs from the
every-step value by -0.0320 to +0.0636 (red seat) and -0.0281 to +0.0714 (blue seat). The approximations were read
once, read-only, from the private Sprint 8 and Sprint 10 captures and are declared constants of the draft.

### 6.3 Primary continuation: interim stop and final classification

* Interim, after P1 (two games per seat): stop if at least 2 of the 4 games are collapse games, or if all 4 are
  T9-v2-like. Otherwise play P2.
* Final, after P2 (three games per seat):
  * NOT_PRESERVED if at least 2 of the 6 games are collapse games, or if at least 2 of the 3 games are T9-v2-like in
    each seat;
  * PRESERVED_DIRECTIONALLY if no game collapses, at most 1 of the 6 games is T9-v2-like, and the seat average is at
    least +130.5 (half of T9-v1's exploratory estimate of 261.0, Sprint 9's planning effect);
  * AMBIGUOUS otherwise.
* The interim stop fires only when the final classification is already NOT_PRESERVED whatever P5 and P6 show, so
  stopping early never changes the classification; it only saves the sessions.
* A tactical early stop (interim stop or NOT_PRESERVED) ends the screen before the adverse stage. PRESERVED_DIRECTIONALLY
  and AMBIGUOUS both continue to A1: an ambiguous primary is a likely outcome of six games and is not a reason to skip
  question 2.

Behaviour of these rules on existing games (`draft.json`, 20,000 seeded draws each; descriptive, not a test):

| If the candidate behaved like | Stopped before the adverse stage | AMBIGUOUS | PRESERVED_DIRECTIONALLY |
|---|---:|---:|---:|
| T9-v1 (3 + 3 draws from its 15 + 15 registered games; floors recomputed from the other 12 per seat) | 0.11% | 19.43% | 80.46% |
| `baseline-v2` (3 + 3 draws of distinct C1 games; floors from all T9-v1 games) | 29.80% | 66.66% | 3.54% |

So the rules almost never discard a candidate that behaves like T9-v1, rarely call a no-effect candidate preserved,
and leave most no-effect outcomes AMBIGUOUS. A single loss never stops the screen. These are rank properties of 15
games per population; v3 is a different policy, and the figures are not error rates of any inference.

### 6.4 Adverse continuation, replication and the structural stop

Each A1 game is classified against Sprint 9 phase B's 15 games per arm of the same configuration
(`evaluation/t9-confirmation-1/phase-B.json`):

| Configuration (v3 seat) | Favourable | Unfavourable | In between |
|---|---|---|---|
| 2120531121 C3 (blue) | REPAIRED: all five objectives held at the end (occupy 310) and margin at least 559 | NOT_REPAIRED: occupy below 310 (a fifth objective missed) | PARTIAL: all five held, margin below 559 |
| 1930331196 C3 (blue) | AVOIDED: occupy 310 and attack at least 78 | REGRESSED: occupy below 310, or attack at most 61 | AMBIGUOUS: attack 62 to 77 |
| 1930331196 C2 (red) | AVOIDED: occupy 310 and attack at least 16 | REGRESSED: occupy below 310, or attack 0 | AMBIGUOUS: attack 1 to 15 |

The limits are the lowest `baseline-v2` value and the highest T9-v1 value of each configuration. Applied with
leave-one-out limits to the Sprint 9 games themselves, the `baseline-v2` arm is classified favourable in 15, 14 and 14
games and in between in 0, 1 and 1 (2120531121 C3, 1930331196 C3, 1930331196 C2); the T9-v1 arm unfavourable in 15,
14 and 15 and in between in 0, 1 and 0; no game lands on the wrong side. The two T9-v2 games of each configuration are
classified NOT_REPAIRED, AVOIDED and AVOIDED.

Replication (A2) of a configuration is triggered when its A1 game is anything other than REPAIRED or AVOIDED, or, in
2120531121 C3, when the fifth objective last changed to own control within the final 144 steps (after step 2,736), so
that the repair hinged on the last infantry hex time. A favourable A1 game without that late trigger is not
replicated: against the inert control, objective holding has repeated in every recorded game (in each of these
configurations all 15 Sprint 9 games of each arm had exactly the same coverage, and T9-v2's two games per
configuration had the same objectives and margins), and within each arm the margin minus twice the attack score was
the same in all 15 games (in 2120531121 C3 the two arms' constants, 383 and 303, differ by exactly the missed 80-point
objective). A second favourable game would therefore mostly re-measure shot dice. An unfavourable game is replicated so that no configuration
is judged unfavourable on one game alone, except for the structural stop.

Structural design failure (S14), 2120531121 C3 only: the fifth objective is not held at the end, and the capture shows
that v3 staged or withheld a selectable claimant of that objective at a decision where every counted place of it was
held by units that never stood on it before the end, while that claimant's free-flow arrival at that decision was
earlier than the actual arrival of every place holder (or none of them arrived). That is the reservation failure
Sprint 10 diagnosed in T9-v1, reproduced by places that pass the end-of-game test but are never honoured; it stops the
screen on one game, without replication.

Every stage report states which rule fired, with the values it fired on, before the next card is built.

## 7. Primary-scenario screen (2130511121)

Reference populations (all descriptive; candidate seat; Sprint 9 phase A, 15 games each):

| Seat fact | T9-v1 H1 red | `baseline-v2` C1 red | T9-v1 H2 blue | `baseline-v2` C1 blue |
|---|---|---|---|---|
| Margin, min / median / max | -1,003 / -737 / 1,035 | -1,195 / -919 / -217 | 865 / 1,061 / 1,435 | 217 / 919 / 1,195 |
| Coverage | 0.618 / 1.210 / 5.386 | 0.160 / 0.378 / 2.763 | 5.057 / 5.280 / 5.426 | 3.541 / 5.925 / 6.143 |
| Objectives held at the end | 0 / 0 / 7 | 0 / 0 / 1 | 7 / 7 / 7 | 6 / 7 / 7 |
| Own units lost | 18 / 32 / 35 | 28 / 33 / 36 | 3 / 11 / 16 | 7 / 13 / 28 |
| Waiting unit-steps in front of full hexes | 0 / 89 / 791 | 392 / 697 / 1,282 | 0 / 0 / 6 | 1,469 / 9,038 / 31,065 |
| Own attack score | 228 / 362 / 601 | 130 / 282 / 513 | 490 / 542 / 548 | 430 / 489 / 546 |
| Opponent's total | 284 / 1,170 / 1,303 | 910 / 1,261 / 1,399 | 84 / 271 / 369 | 204 / 342 / 693 |

Other references: the historical `baseline-v2` C1 red margins of the shoot-reservation experiment (15 games, -1,055 to
-719, median -843); Sprint 8's exploratory T9-v1 margins (H1 -815, -621, -505; H2 1,077, 1,133, 1,297; exploratory
seat average 261.0); Sprint 10's T9-v2 smoke (H1 -729 with 1 objective at the end, attack 322, waiting 515 unit-steps,
1,126 withheld unit-decisions; H2 815 with 7 objectives, attack 486, opponent total 394, waiting 549 unit-steps, 288
withheld unit-decisions; seat average +43).

Directional criteria, fixed now:

* Obvious tactical collapse: the collapse game of section 6.2.
* Preservation of objective coverage: red coverage at or above 0.618 (the T9-v1 floor); blue objectives at the end and
  blue coverage reported against both populations.
* Extreme long-term withholding or staging: a unit staged or withheld by v3 in 1,440 or more consecutive decisions
  (half the play stage, Sprint 9's convention for idle units) while its claimed objective is not own-held. Flag only;
  T9-v1 won as blue with runs up to 1,532 decisions, so length alone is not a failure.
* Capacity queues: own waiting unit-steps above the largest T9-v1 value of the seat (791 as red, 6 as blue) are
  flagged, and so is every staging-induced wait longer than 144 steps (section 9.3). The queue count alone does not
  measure withholding (Sprint 10: a withheld unit has no path and never queues), so both are reported.
* Terminal margin: each game's rank within T9-v1's and within `baseline-v2`'s 15 games of the seat, and the seat
  average against +305.47 (T9-v1 registered), +261.0 (T9-v1 exploratory) and +43 (T9-v2 smoke). With three games per
  seat the seat average has a standard error of roughly 121 points under `baseline-v2`'s fresh spread and 182 under
  T9-v1's, so it cannot by itself distinguish +305.47 from 0; it enters only the PRESERVED condition.
* Resemblance: a game is T9-v2-like or not by section 6.2; the counts per seat decide the classification of section
  6.3. Mechanism counts that follow from the design itself (withheld unit-decisions, staged moves) are reported but do
  not count as resemblance: v3 stages by construction, as T9-v2 did.

The H1 variance (T9-v1's red margins have a sample standard deviation of 606.51, with two wins among its 15 games) is
handled by not judging the red seat on its margin, by requiring two T9-v2-like games in both seats before a stop, and
by the rule check of section 6.3.

## 8. Adverse-configuration screen

References (Sprint 9 phase B, 15 games per arm; Sprint 10's T9-v2 games):

| Configuration | `baseline-v2` margin / attack / occupy | T9-v1 margin / attack / occupy | T9-v2 (Sprint 10) |
|---|---|---|---|
| 2120531121 C3 (blue) | 559 to 599 / 88 to 108 / 310 | 519 / 108 / 230 | 423, 403; occupy 230 |
| 1930331196 C3 (blue) | 550 to 570 / 78 to 88 / 310 | 414 to 516 / 10 to 61 / 310 | 570, 570; attack 88 |
| 1930331196 C2 (red) | 258 to 274 / 16 to 24 / 310 | 226 / 0 / 310 | 274, 274; attack 24 |

### 8.1 2120531121 C3

The question is the mechanism, not only the score. For each objective, and in particular the 80-point objective that
T9-v1 and T9-v2 never took (objective A in Sprint 11's certificate) and the 80-point objective B whose places v3 gives
at its first decision only to the two infantry units that can arrive (free-flow 2,736 steps in a 2,880-step game), the
capture establishes:

* whether movers that cannot arrive are excluded from the counted places, decision by decision;
* whether nearer, faster claimants receive the places, and which ones (by kind, free-flow time and rank);
* for every selected claimant: the selection step, its free-flow estimate, the predicted arrival, the actual arrival,
  the arrival delay (actual minus predicted; never negative if the lower-bound fact holds), the arrival slack
  (2,880 minus the arrival step), the step it became stationary, the first step an occupation was listed for it, its
  occupation order and the engine's response, and the objective's ownership from then to the end;
* the outcome of every place, classified as in section 9.3, so that a place that passed the end-of-game test but came
  too late to give useful control is counted as such;
* staging and withholding episodes per unit, the largest occupancy of every staging hex, and every staging-induced
  wait;
* when the fifth objective is reached, when it first changes to own control and whether it is own-held at the end.

Capturing the fifth objective does not by itself advance v3: a REPAIRED game counts towards readiness only if the
certificate attributes the capture to claimants that v3 selected under its rule, and only together with a primary that
is not NOT_PRESERVED and the other two configurations favourable (section 15).

### 8.2 1930331196 C3 and C2

Both configurations ask whether v3 keeps the same-route geometry and the later firing opportunities that T9-v2
restored. Tracked per game: direct-fire availability (decisions in which an own unit lists a shoot option, and the
targets listed), direct-fire orders emitted and their engine responses, attack score, objective capture order, staging
and withholding, route prefixes (path hexes removed by staging), waiting and capacity maxima. They are compared,
decision by decision where the states allow, with the frozen full-step `baseline-v2` diagnostic trajectories of Sprint
10 (sessions 2776 and 2778), whose firing periods (decisions 742, 804, 841 and 876 in C3; decision 611 in C2) are the
opportunities T9-v1 lost; and with T9-v2's two games of each. In C2, where v3 seats four vehicles at its first decision
instead of T9-v2's three vehicles and one infantry unit, the capture also follows the later shooter's route and the
capture order that Sprint 10 traced its shot to.

## 9. Mechanism instrumentation (specified here, built only at registration)

### 9.1 Observers

Three read-only observers run together through Sprint 9's `Tee`:

1. Sprint 9's `T9Capture`, imported unchanged (its module is pinned by the Sprint 9 registration). It gives the seat
   facts of section 7 by exactly the definitions that produced the reference populations: coverage, objectives held,
   losses, waiting, commitment maxima, start positions and move counts.
2. A new compact capture for v3's trace block (`t9_batch`), built like Sprint 10's T9-v2 capture on the exploratory
   capture: staging and withholding changes, episodes and their longest runs, path hexes removed by staging, gate
   rejections inside the allocator, the counts of movers that hold no place, and add-on errors; so that staging and
   withholding are comparable with T9-v2's screen.
3. A new full-step private timeline, built like Sprint 10's diagnostic capture (every step, all-seeing state and each
   seat's observation, kept only under `local/`), which re-decides the candidate seat from its own observation and
   memory: `baseline-v2`'s actions and trace digest, then v3's complete allocation (per objective: standing units,
   counted movers with their remaining bounds, movers that hold no place, free places, the ranked claimants with their
   free-flow time, cost, path length and status, the selected claimants, staged paths and withheld units with reasons).
   It checks every decision against the live one (S7). Recording the whole allocation matters because the trace holds
   only the changes.

From the records: score components, action counts by type, engine feedback and refusal classes, contract errors,
gate rejections, replay checks and decision latency. Every capture's digest is written into its record; capture and
record must agree on two independently produced counts (move orders and steps), and the analysis refuses a game where
they do not.

### 9.2 What is recorded

`baseline-v2`'s pre-add-on moves; v3's claimant batches and ranking features; standing incumbents; counted movers;
excluded unreachable movers; selected claimants; staging and withholding reasons; free-flow estimates at selection;
actual arrival times; objective ownership transitions; occupation listings, orders and responses; direct-fire
availability and orders; waiting and queue counts; staging-hex and objective occupancy maxima; action feedback;
contract, gate, add-on, observer and replay errors; decision latency (flagged above 10 ms at the 99th percentile or
5,000 ms for any decision, as in Sprint 9; never a stop).

### 9.3 Definitions

* Arrival: the first post-step state in which the unit stands on its destination objective. Path end: the first state
  from then on with an empty path. Stationary: the first state after the path end with `stop` equal to 1 (75 steps after
  the path ends in every settled arrival observed so far).
* First occupation opportunity: the first state in which the seat's `valid_actions` lists an occupation for the unit.
  The delay between arrival and this listing is not an established engine fact; the screen measures it and assumes
  nothing about it.
* Arrival slack: 2,880 minus the arrival step. Predicted slack: 2,880 minus (selection step plus free-flow time). Arrival
  delay: actual minus predicted arrival.
* Outcome of a selected place: OCCUPIED (the unit's own occupation was accepted and the flag became own), HELD (the
  unit stood on the objective at the end while it was own), REDUNDANT (it arrived after the objective was already own
  and it was not needed to keep it), TOO_LATE (it arrived, but the objective was not own at the end and its occupation
  was not accepted), NEVER_ARRIVED (still moving or waiting at the end), LOST (destroyed first).
* An unproductive place: a counted place whose holder never stood on the objective before the end. Held back by an
  unproductive place: claimant-decisions in which v3 staged or withheld a selectable claimant while at least one of
  the objective's counted places was unproductive.
* Counted commitment: v3's own count (S8). Raw commitment: every own ground unit standing on or with a path ending on
  the objective; reported.
* Staging hex: the last hex of a move v3 shortened. Staging-induced wait: an own ground unit with a path and speed 0
  whose next hex holds four own ground units, at least one of which stands there after a staged move. Flagged above
  144 steps; a staging-induced wait that lasts to the end of the game is a block and is reported as a finding with its
  certificate.
* Direct-fire availability: decisions in which an own unit lists a shoot option; orders: emitted shoot actions.

### 9.4 Seat-locality

The candidate reads only its seat's observation and the setup cost data (Sprint 11, section 12). The observers receive
the all-seeing state after each step through the game loop's read-only observer interface and never return anything to
a policy or the engine; the all-seeing state is used only after the game. S7's reconstruction uses the seat's
observation and memory only, so it also checks that the live decision depends on nothing else.

## 10. Privacy

* Raw observations, unit ids, exact coordinates and paths stay in ignored `local/` captures and private diagnostics on
  the evaluation server.
* Public outputs (stage reports, results files, this document's later results) hold aggregates and sanitized event
  certificates only: objectives by value and the letters of Sprint 11's certificate, units by kind and an anonymous
  index within a certificate, steps and decision indices, counts.
* The repository privacy scan must stay at its adjudicated baseline of 81 hits, or each new hit is adjudicated before
  a push. Any exposure stops the screen (S3).

## 11. Evidence populations and historical comparisons

| Population | Policy | Track | Games in 2130511121 head to head | Use here |
|---|---|---|---|---|
| Sprint 8 | T9-v1 | exploratory | 3 per seat | descriptive reference |
| Sprint 9 | T9-v1 and `baseline-v2` | confirmatory (registered) | 15 per cell | reference populations and rule values |
| Sprint 10 | T9-v2 (and six full-step diagnostic games of T9-v1 and `baseline-v2`) | exploratory | 1 per seat | descriptive reference |
| Sprint 12 | v3 | exploratory (proposed) | up to 3 per seat | this screen |

These populations are never pooled into one estimator, no historical game is reweighted into a Sprint 12 figure, and
Sprint 12 games will never be pooled into a later confirmatory estimate. No new `baseline-v2` control game is played:
in the primary scenario the mirror term cancels exactly under the zero-sum convention and 30 control games exist (15
fresh in Sprint 9, 15 historical); against the inert control `baseline-v2` has 15 historical and 15 Sprint 9 games per
configuration plus one full-step diagnostic game each, and its objective holding repeated in all 15 Sprint 9 games of
each configuration. No causal interpretation proposed here needs a fresh control.

## 12. Failure handling

* A game that does not complete (failure, cap, interruption, missing record) keeps what it recorded, counts toward the
  ceiling and stops the screen (S4) until its cause is documented. It is never rerun.
* A missing or digest-mismatched capture of a completed game leaves its margin in the report but removes it from every
  mechanism figure, and stops the screen until explained.
* Records and captures are never overwritten. A stage card is never edited after its first game; a correction is a new
  card with a new name, approved by the owner.
* Any change of the candidate's source, the observers or the analysis after the first game ends the screen: a changed
  candidate is a new identity with a new proposal.
* A stop is reported with its evidence in the next stage report and in the close-out; nothing is retried to make a
  stop disappear.

## 13. Tests and checks required before the first session

* The draft's own checks: `scripts/t9_batch_screen_draft.py --check` and `tests/test_s12_proposal_draft.py`.
* Synthetic tests of the two new observers: arrival, path end, stationarity, occupation listing and order, flag
  transitions, slack and delay, every outcome class of section 9.3, unproductive places, staging-induced waits, counted
  against raw commitments, and the S7 reconstruction with a planted mismatch.
* A real-capture rehearsal before any engine use: the new extraction run over the frozen Sprint 10 full-step
  captures must reproduce known facts (in the `baseline-v2` 2120531121 C3 game, objective A first captured at decision
  564 by two units; the 1930331196 C2 `baseline-v2` shot at decision 611; final flags equal to the occupy scores), and
  the v3 reconstruction must equal Sprint 11's replay on the same states.
* A stand-in rehearsal: the real game entry point and stage runner, with v3 and the observers, against the PS-1
  stand-in engine with the session interface replaced in-process (no engine, no ledger record), writing records and
  captures that pass every cross-check; it must also refuse a stage card whose prerequisite report is missing.
* Mutation tests of the per-game invariant checks and the stage rules: plant each of S5 to S13 (a fifth counted place,
  a fourth unit at a staging hex, a non-prefix and an on-objective stage, a cross-objective move, an invented move, a
  reordered unrelated action, an add-on error, a replay and an observer mismatch, a gate rejection and an unknown
  refusal class) and a wrong rule value, and require
  each to be caught, after the unmutated input has passed.
* A timing check: the observers' overhead measured on the largest Sprint 10 full-step capture and scaled to
  2130511121's force, so that a head-to-head game is expected to stay well inside the 1,800 s wall cap.
* The full suite on the committed tree (workstation, a clean clone, and the server's private suite) and a read-only
  `verify` before the first session.

## 14. Close-out requirements

* Ledger: exactly the sessions this screen played after 2786, all closed with integrity ok, none unclosed; the
  installation's `verify` ok.
* Every stage report regenerated byte for byte from the private records and captures (`--check`), with planted
  errors caught by its gate.
* The proposal's results appended under a dated heading of the registered document, with every printed number
  checked against the reports by a private documentation gate, including planted errors, and the earlier sprints' doc
  gates rerun after any edit of their documents.
* Privacy scan at its baseline or adjudicated; the commit range audited as a set; the canary
  (`a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`) rebuilt and unchanged.
* The workstation, GitHub and the server at the same commit and tree, clean; frozen identities unchanged.

## 15. Interpretation rules and dispositions

* Every result is exploratory and directional. No interval, p-value or power statement is computed for Sprint 12
  games; their placement against historical games is descriptive.
* The Sprint 9 result belongs to T9-v1. A Sprint 12 seat average is never compared with +305.47 as if it estimated the
  same quantity with similar precision.
* Results against the inert control do not generalise to head-to-head play, and a primary result does not generalise
  to other scenarios.
* No disposition promotes anything; `baseline-v2` stays the frozen reference.

The first row that matches applies:

| Disposition | When |
|---|---|
| SCREEN_INCOMPLETE | a stop not attributable to v3 (installation, ledger, infrastructure, privacy) |
| STRUCTURAL_FAILURE | S14, or another stop shown to be a defect of v3 |
| NOT_PRESERVED_IN_PRIMARY | a tactical early stop; v3 is not pursued in this form |
| READY_FOR_CONFIRMATORY_PROPOSAL | primary PRESERVED_DIRECTIONALLY; all three configurations favourable in every game played; the 2120531121 C3 certificate attributes the fifth objective to claimants v3 selected; no unexplained staging-induced block. The owner may then commission a separately registered confirmatory study with fresh games |
| PROMISING_PRIMARY_UNRESOLVED | primary AMBIGUOUS, and otherwise as for the row above. No confirmation is proposed on this screen alone; the next step is an offline reading of the primary mechanism |
| NEEDS_REVISION | every other completed screen: a configuration unfavourable or mixed, or an unexplained staging-induced block, with its mechanism identified from the captures where they allow; the next step is offline, under a new identity |

## 16. Critical review of this draft

The draft was challenged against the questions below before it was finalised; the answers are the design above, and
the revisions they caused are listed at the end.

* Is the primary scenario tested early enough? It is tested first and alone: no other game is played until its report
  exists, and the most likely failure (the offline replay places v3 close to T9-v2 there) can end the screen after four
  or six sessions.
* Could the design discard v3 because of the known H1 variance? The red seat is judged on coverage, not margin; a stop
  needs two T9-v2-like games in both seats or two collapses; drawn from T9-v1's own games with leave-out floors the
  rules stop 0.11% of the time. One loss never stops the screen.
* Could it advance v3 merely because 2120531121 C3 captures its fifth objective? No: readiness needs a preserved
  primary and all three configurations favourable, and the capture must be attributed to v3's selections.
* Does it distinguish arrival from useful occupation? Yes: arrival, path end, stationarity, first occupation listing,
  occupation order and ownership are separate observables, and every selected place is classified by outcome, with
  TOO_LATE and NEVER_ARRIVED counted apart from useful ones.
* Does it test both known firing-regression configurations? Yes, 1930331196 C3 and C2, each against the frozen
  `baseline-v2` full-step trajectory that holds the lost firing periods.
* Does it detect a staging corridor whose three-unit cap still causes harmful traffic? Staging-hex occupancy maxima,
  staging-induced waits (flagged above 144 steps; a block to the end reported with a certificate) and own waiting
  unit-steps against the T9-v1 maxima. S9 catches a violated cap; the waits catch a respected cap that still blocks.
* Are historical controls only descriptive? Yes: they set the rule values in advance and place results; nothing is
  pooled or tested against them.
* Does the proposal quietly assume an engine semantic? Every operation v3 uses is observed-supported (Sprint 11,
  section 2): kept moves, same-route prefixes, withholding, moves to units in the move-to-stop transition, the stacking
  limit and free-flow time as a lower bound on arrival. One fact is not established and is measured rather than
  assumed: how soon after arrival an occupation is listed. The end of the game (step 2,880, equal to `max_time` in
  every frozen record) is read from the observation, and the capture checks it.
* Can the same information be obtained with fewer sessions? Partly, and the draft takes it: adverse replications are
  conditional (objective holding against the inert control repeated in every Sprint 9 and Sprint 10 game of these
  configurations), so the unconditional total is 9, not 12; no control game is played. Going lower costs information that matters: dropping P2 would leave v3 with less primary
  evidence than the three games per seat on which T9-v1 itself was proposed for confirmation; one game per seat is
  what Sprint 10 had, and it settled nothing; dropping 1930331196 C3 would rest on an opening allocation alone, while
  Sprint 11's replay shows v3's later decisions there differ from T9-v2's (on the T9-v1 states, 1,206 against 1,730
  `baseline-v2` objective moves not kept as issued).

Revisions made during this review:

1. Three sessions moved from unconditional adverse replications to the primary (three games per seat instead of two),
   because objective holding against the inert control repeated in every Sprint 9 and Sprint 10 game of these
   configurations while the primary has the largest spread.
2. The interim stop was made exactly the case in which the final classification is already determined.
3. S8 was defined on v3's counted places, because the raw count of paths ending on an objective can legitimately
   exceed four when an unreachable mover releases its place; a raw-count rule would stop a correct candidate.
4. The red seat's indicator was changed from margin to coverage, and blue coverage was kept out of the rules after the
   Sprint 8 snapshot values showed T9-v1-like games at its edge.
5. The rule checks recompute T9-v1's floors without the drawn games; with in-sample floors a T9-v1 draw could never
   fall below them and the check could not fail.
6. The structural stop was extended to places that pass the end-of-game test but are never honoured, the form of the
   old failure that the new test cannot see.

Remaining limits: the H1 floor rests on one game (coverage 0.618, margin -597); the T9-v2 reference is one game per
seat; the rule checks assume v3 resembles one of the populations, which it need not; AMBIGUOUS is the likely result for
a candidate without effect; the observers' overhead in a head-to-head game is estimated, not yet measured.

## 17. Work needed at registration (not done in this draft)

* The runner side, as new files that leave the pinned evaluator, the existing exploratory runner and the card builder
  of earlier sprints unchanged: a stage card builder (the A2 card derived from the committed A1 report), a stage
  runner that stops on any non-zero game status and refuses a stage without its prerequisite report, and a game entry
  point that knows v3's agent, runs the three observers and checks the per-game invariants of section 6.1.
* The two observers of section 9 and the stage analysis that writes the public stage reports.
* `tests/test_t9_batch.py` currently asserts that v3 is in no run card. The registration must change that assertion,
  with the owner's approval, to allow exactly the approved Sprint 12 stage cards; until then it stays as it is.
* The tests of section 13, all passing on the committed tree before the first session.
* No public issue is proposed (exploratory track); the owner may ask for one.

## 18. Owner decisions requested

1. Approve, amend or reject the screen as drafted: 12 sessions at most, 9 if nothing stops and nothing is replicated,
   primary first.
2. Confirm that full-step private captures are wanted in every game (several hundred MB each; the server has room),
   so that no later diagnostic replay is needed.
3. Authorise the registration work of section 17, including the change to the run-card assertion of
   `tests/test_t9_batch.py`. No engine session follows until that work is committed, checked and approved.
