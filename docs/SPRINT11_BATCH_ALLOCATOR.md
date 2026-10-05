# Sprint 11: offline design of a batch capacity allocator for T9

Sprint 11 is an offline design study. It opened no engine session: the engine ledger still ends at the closed session
2786. It does not re-estimate or reinterpret Sprint 9's registered result (`PRIMARY_SUPPORTED_NEEDS_REVISION`; in
2130511121, +305.47 seat-averaged, 95% interval 172.87 to 611.24) or Sprint 10's disposition
(`PARTIAL_REPAIR_NOT_READY_FOR_CONFIRMATION`), it pools no observations across sprints, it claims no score effect from
action replay, and it promotes nothing. Every figure below is an action-level difference on a recorded state.

Frozen identities were verified before the work and are unchanged: `baseline-v2`
`7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, T9-v1
`0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa`, T9-v2
`66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece` (policy-source digests), and the `baseline-v2` canary
`a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`.

## 1. Historical-gate maintenance

Sprint 8's private documentation gate had failed since Sprint 9's commit `6d3c5d48`, which correctly rewrote the T9 row
of the living hypothesis register from `EXPLORATORY` to `NEEDS_REVISION`; the gate still required the old row. This is
retrospective maintenance caused by a later legitimate status update, not a research failure, and no Sprint 8 result
changed. The old gate is kept byte-identical as version 1. Version 2 drops only the living-row clause and binds the same
Sprint 8 claim (10 of 12 games) to the text that still records it: roadmap item 7 of `docs/TACTICAL_FRONTIER.md` and the
T9 v1 row of `docs/SPRINT8_EXPLORATION.md`. At the Sprint 8 close-out tree both versions pass (7 of 7 and 8 of 8 planted
errors caught); at Sprint 10's close-out tree version 1 fails on that clause alone and version 2 passes, 8 of 8.

Commit `7fed764075defa674adfe9975ba94c95cdc74e50` (`eval: register sprint 10 c2 diagnosis`) does not follow the
`type(scope): message` rule. The project's commit audit runs over each sprint's range; Sprint 11's range does not
contain it, so no exception was added and the published history is not rewritten.

## 2. What the policy can control

Measured on all six Sprint 10 full-step captures (the diagnosed seat, every play decision) and on earlier engine
records. Classes: OBSERVED_SUPPORTED, OFFLINE_LEGAL_BUT_ENGINE_UNTESTED, NOT_AVAILABLE_TO_THE_CURRENT_POLICY, UNKNOWN.

| Operation | Class | Evidence |
|---|---|---|
| `baseline-v2` issues another move to a unit whose path is active | NOT_AVAILABLE_TO_THE_CURRENT_POLICY | the candidate generator refuses ("already moving"); no captured `baseline-v2` action is such a move |
| An add-on replaces or shortens an active path with a new move | NOT_AVAILABLE_TO_THE_CURRENT_POLICY | move is listed for 0 of 159,442 own ground unit-decisions with an active path (127,568 traversing, 31,874 waiting); the project gate rejects it; the published rules forbid changing an issued move |
| Stop (action 10) to free a unit waiting in front of a full hex | NOT_AVAILABLE_TO_THE_CURRENT_POLICY | observed in Sprint 4: echoed without error but never took effect; the unit kept its path and lost every listed action for the rest of the game |
| Stop (action 10) to a traversing unit, then a new move | OFFLINE_LEGAL_BUT_ENGINE_UNTESTED | stop is listed for all 159,442 unit-decisions with a path; no stop has ever been issued to a traversing unit (`docs/T7_DESIGN.md`, claim B-5) |
| An unsolicited move to a stationary unit that `baseline-v2` leaves idle | OBSERVED_SUPPORTED as an engine operation | the same action `baseline-v2` issues to every stationary unit listing a move; not used here, because it would add actions `baseline-v2` did not choose |
| Keep, shorten to a same-route prefix that ends off any objective, or withhold `baseline-v2`'s move to a stationary unit | OBSERVED_SUPPORTED | T9-v2 issued 239 prefix moves in 8 sessions, none refused; withholding since Sprint 8 |
| A new move to a unit that has just stopped at the end of a shortened path | OBSERVED_SUPPORTED | all 182 moves the diagnosed seats emitted entered their first hex exactly one hex time after the order, including the 86 issued during the 75-step move-to-stop transition |
| Free-flow time (per-hex `720 / basic_speed * cost`, rounded) is a lower bound on arrival | OBSERVED_SUPPORTED | Sprint 3 hex-time fact; of the 182 emitted moves 139 arrived exactly at it, 9 later, 34 never, none earlier; at every twentieth decision, 3,530 active paths whose end was reached arrived no sooner than the remaining bound that excludes the hex being entered |

So a reservation held by a mover can be neither re-ranked nor taken back by any established operation. The only
lever on movers would be a stop on a traversing unit, which is untested; the design below does not use it.

## 3. Formal model

For one decision of one seat and each objective `o`:

* `P(o)`: own ground units standing on `o` with no path (always counted);
* `M(o)`: own ground units whose active path ends on `o`; not controllable this decision. A mover is counted unless
  `cur_step + R >= max_step`, where `R` is its remaining free-flow time excluding the hex it is entering; by the lower
  bound such a mover cannot stand on `o` before the game ends, so it holds no place (it keeps moving: nothing is
  issued to it);
* `N(o)`: own ground units for which `baseline-v2` emits a move ending on `o` in this decision (controllable, all
  stationary);
* free places `F(o) = 4 - |P(o)| - |counted M(o)|`;
* each claimant's free-flow time `T` along `baseline-v2`'s own path; it is selectable only if `cur_step + T < max_step`
  and `T` is readable;
* selected owners: the first `max(F(o), 0)` selectable claimants of `N(o)` in rank order; every other claimant is
  staged or withheld (section 5).

Invariants: at most four counted places per objective after the decision (counted incumbents plus selected owners); the
selected set, the staged paths and the withheld set do not depend on the order of `baseline-v2`'s actions; every kept
or shortened move keeps `baseline-v2`'s objective and is a prefix of its path; no cross-objective move; actions other
than own ground moves are unchanged and keep their order; only the seat's observation and the setup cost data are read;
ties break deterministically; a failure withholds every own ground move to an objective rather than emitting one
unchecked; a place is held only by a unit that can arrive before the game ends, so a claimant can no longer be kept
out for the rest of the game by a reservation that cannot be honoured, and no place is granted because of a claimant's
position in the action list. An incumbent mover that a waiting claimant would
outrank is retained and counted explicitly as "kept only because uncontrollable"; it is never pretended to be re-ranked.

## 4. Designs considered

* Ranking. R1, route cost in the unit's own movement mode; R2, free-flow time. R1 ranks an infantry unit (5 km/h, 144
  steps per hex) level with a vehicle (36 km/h, 20 steps per hex) at equal cost; a synthetic test shows it, and R1
  cannot express whether a unit can arrive before the end. R2 selected. On the six captures the two rankings chose
  differently in 2 objective-decisions, because claimant batches mixing infantry and vehicles were rare there (0 to 1
  per game).
* Admission. A, batch ranking only (counts every mover, selects regardless of the end of the game); B, batch ranking
  plus the end-of-game test of section 3 (selected); C, B plus a commitment horizon (claimants with free-flow time above
  1,440, 720 or 360 steps are staged, not selected). A does not repair the diagnosed failure (section 6). C only kept
  fewer moves than B (1 to 4 per game at 1,440 or 720 steps, 4 to 12 at 360) and adds an unvalidated constant, so it is
  not adopted.
* Overflow disposition. Same-route staging at the farthest non-objective hex of the path holding fewer than three own
  ground units (selected); the same with four (T9-v2's limit); withholding only. Staging keeps the geometry closest
  to `baseline-v2` (its overflow units also end next to the objective) and is established at the engine. The limit of
  three leaves one place in every staging hex for passing units: four stationary units in a corridor hex would block
  every own unit routed through it (Sprint 2's stacking fact), including selected owners.
* Rejected without replay: chaining arrival estimates through other objectives (predicting where `baseline-v2` will
  send a unit after its current objective) is speculative and can starve an objective whose predicted claimants are
  never sent; displacing dominated movers by a stop depends on the untested operation of section 2; cross-objective
  redirection is excluded by the Sprint 10 finding.

## 5. The selected rule: `t9-batch-capacity-v3`

Module `src/miaosuan_agent/experiments/t9_batch.py`, an add-on to the frozen `baseline-v2` through the unchanged
exploratory wrapper. It is OFFLINE ONLY: it is in no run card, is never packaged and has never played. Its
policy-source digest (`baseline-v2`'s source set plus the wrapper and the module) is
`9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8`.

Rank key, smallest first: selectable before not selectable; readable free-flow time before unreadable; free-flow time;
route cost; path length; unit id. No emission index enters any comparison. Non-selected claimants are processed in the
same order, so their staging hexes are order-free too. A staged move the project gate rejects is withheld. A missing
`max_step` makes every mover counted and every readable claimant selectable (the conservative direction); a missing
`basic_speed` makes a claimant unselectable.

## 6. Replay on the frozen captures

`scripts/t9_batch_replay.py` (server; inputs pinned by SHA-256 in its output) replays every one of the 17,280 play
decisions of the six Sprint 10 captures: `baseline-v2` as captured, T9-v1 as captured, frozen T9-v2, the candidate and
eight variants, one decision at a time. Faithfulness is checked rather than assumed: on 174 sampled decisions
`baseline-v2` re-decided from the captured memory equals the captured actions and the candidate's policy class equals
its pure allocation; every decision's captured `baseline-v2` ground moves equal the T9-v1 audit's move rows; and the
candidate's outcome was identical under three reorderings of `baseline-v2`'s actions in all 3,079 decisions with two or
more claimants. Output: `evaluation/s11-batch-allocator/replay.json`.

Each cell is the number of `baseline-v2` objective moves not kept as issued, summed over the decisions, and in
parentheses those held back only because a place was held by, or granted to, a unit that cannot arrive before the end
("batch only" is design A):

| Configuration | Recorded trajectory | Decisions with objective moves | T9-v1 | T9-v2 | batch only | candidate |
|---|---|---:|---:|---:|---:|---:|
| 2120531121 C3 | T9-v1 game | 2,522 | 29,276 (27,722) | 29,272 (27,724) | 29,272 (27,722) | 19,839 (0) |
| 2120531121 C3 | baseline-v2 game | 15 | 25 (8) | 21 (10) | 21 (8) | 23 (0) |
| 1930331196 C3 | T9-v1 game | 263 | 1,736 (1,688) | 1,730 (1,684) | 1,730 (1,684) | 1,206 (0) |
| 1930331196 C3 | baseline-v2 game | 11 | 26 (4) | 20 (0) | 20 (0) | 20 (0) |
| 1930331196 C2 | T9-v1 game | 289 | 1,057 (0) | 1,057 (0) | 1,057 (0) | 1,057 (0) |
| 1930331196 C2 | baseline-v2 game | 16 | 21 (0) | 21 (0) | 21 (0) | 21 (0) |

| Configuration | Recorded trajectory | Places granted that cannot be reached: T9-v1, T9-v2, batch only, candidate | Cross-objective moves: T9-v1 |
|---|---|---|---:|
| 2120531121 C3 | T9-v1 game | 6 / 4 / 2 / 0 | 12 |
| 2120531121 C3 | baseline-v2 game | 6 / 4 / 2 / 0 | 18 |
| 1930331196 C3 | T9-v1 game | 4 / 0 / 0 / 0 | 14 |
| 1930331196 C3 | baseline-v2 game | 4 / 0 / 0 / 0 | 12 |
| 1930331196 C2 | T9-v1 game | 0 / 0 / 0 / 0 | 8 |
| 1930331196 C2 | baseline-v2 game | 0 / 0 / 0 / 0 | 15 |

| Configuration | Recorded trajectory | Objective-decisions with claimants | Contended | Selection changed by removing emission order | Changed by route-cost ranking | Unreachable reservations not counted | Movers kept only because uncontrollable (units / unit-decisions) |
|---|---|---:|---:|---:|---:|---:|---|
| 2120531121 C3 | T9-v1 game | 2,645 | 2,544 | 2,238 | 0 | 9,998 | 2 / 61 |
| 2120531121 C3 | baseline-v2 game | 18 | 10 | 0 | 0 | 10 | 4 / 20 |
| 1930331196 C3 | T9-v1 game | 285 | 260 | 239 | 0 | 524 | 4 / 316 |
| 1930331196 C3 | baseline-v2 game | 13 | 7 | 0 | 0 | 0 | 6 / 10 |
| 1930331196 C2 | T9-v1 game | 290 | 285 | 1 | 1 | 0 | 4 / 483 |
| 1930331196 C2 | baseline-v2 game | 17 | 7 | 2 | 1 | 0 | 1 / 3 |

"Selection changed by removing emission order" compares the candidate with the same rule ranking by emission order
(feasibility kept): it is the number of objective-decisions whose owners differ solely because of the order. "Movers
kept only because uncontrollable" are counted movers whose remaining bound exceeds the free-flow time of a waiting
selectable claimant of the same objective.

For the candidate and every variant, across all six games: 0 cross-objective moves, 0 shortened moves that are not a
strict prefix ending off an objective, 0 moves invented for units `baseline-v2` did not move, 0 changes to any other
action or to their order, 0 objectives pushed above four counted places, 0 staged moves rejected by the gate and 0
errors. The candidate's 22,166 shortened moves removed 1 hex (19,563) or 2 hexes (2,603) from `baseline-v2`'s path.

## 7. The 2120531121 C3 certificate

Computed by the same driver; units appear only as kinds, objectives only by value and a letter.

* Both diagnostic games start their play stage from the same seat state, and the first decision is identical.
  `baseline-v2` sends six infantry to 80-point objective B (free-flow times 2,736, 2,736, 2,880, 2,880, 3,024 and 3,024
  steps in a 2,880-step game) and eight and four vehicles to two 50-point objectives.
* At that decision T9-v1 grants all four places of 80-point objective A, the objective it never captured, to infantry it
  redirected there, with free-flow times 3,168 to 3,456: none of them can arrive. T9-v2 grants all four places of
  80-point objective B to infantry with free-flow times 2,880 to 3,024: none can arrive either. The candidate grants
  objective B's places only to the two infantry that can arrive (2,736) and leaves two free; it grants no place that
  cannot be reached and sends nobody to objective A.
* In the T9-v1 game, from decision 442 to the end (2,439 decisions), T9-v1 held back claimants of objective A in every
  decision (28,435 unit-decisions, free-flow times 100 to 160 steps) while the objective's incumbents were, at every one
  of those decisions, no standing unit, no mover that could arrive and four movers that could not. On the same states the
  candidate grants places in 2,339 of those decisions, 9,194 unit-decisions, every one to a claimant T9-v1 held back,
  at free-flow times 100 to 160; it never held back a claimant that would arrive sooner than one it selected. In the
  remaining decisions the clock left too little time for any claimant to arrive. T9-v2 and design A grant none.
* In the `baseline-v2` game the objective was first captured at decision 564 by two units; at the `baseline-v2` order
  that sent each of them, the candidate selects it.

This shows that the rule would select the nearer, faster units that were blocked by the four distant reservations. It
does not show that the objective would be captured in an engine game: the replayed states are the recorded ones, not
states the candidate would produce.

## 8. 1930331196 C3 and C2

The candidate makes no cross-objective move, so it cannot recreate the redirections that removed later firing
corridors in either configuration. At the first decision of 1930331196 C3 the candidate grants exactly the places T9-v2
grants, the configuration T9-v2 restored. In C2 it seats the four fastest vehicles at the contested 50-point objective
(free-flow times 360 to 400) where T9-v2, in emission order, seated three vehicles and one infantry unit (2,736); the
same objective and the same routes, but different arrival times. Whether that changes C2's later geometry (Sprint 10
traced C2's lost shot to capture order) cannot be known offline.

## 9. Beyond the diagnosed configurations

Trigger prevalence on the pinned replay corpus H0 (`scripts/t9_batch_prevalence.py`,
`evaluation/s11-batch-allocator/prevalence.json`): one `baseline-v0` mirror game per frozen scenario, both seats, 33,696
decisions; `baseline-v0` reproduced every recorded decision and `baseline-v2` was reconstructed sequentially. These are
not states any T9 policy reaches. `baseline-v2` moved a ground unit to an objective in 142 decisions; 65 of 159
objective-decisions with claimants were contended. Removing emission order changed the selection in 4 objective-decisions
(3 of 16 seats): rare. Claimants that cannot arrive before the end occurred in 9 seats (23 unit-decisions) and
unreachable movers in 5 seats (35 unit-decisions): common enough to matter. T9-v1 made 135 cross-objective moves and
granted 28 unreachable places, T9-v2 16, the candidate 0; every invariant held for the candidate in every seat.

In the primary scenario (2130511121, seven objectives) the H0 game has 58 decisions with objective moves. There T9-v1
made 74 cross-objective moves; the candidate keeps 74 and holds back 87 objective moves, close to T9-v2's 75 and 86,
and differs from T9-v2 mainly in granting no unreachable place (T9-v2 4). In Sprint 9's registered primary phase, 842 of
the 1,294 ground moves the 30 T9-v1 seats emitted were cross-objective replacements
(`evaluation/t9-confirmation-1/phase-A.json`). T9-v1's registered gain therefore coincided with redistribution, which
this design excludes by construction, and T9-v2, which also excludes it, kept only about +43 of it in its two-game smoke.
Nothing offline says whether the candidate recovers any of the primary benefit; that is the first question for any
engine use.

## 10. Staging and withholding compared with T9-v2

In its own 2120531121 C3 engine games, T9-v2 withheld units for up to 2,459 consecutive decisions; its first decision
there is the replayed one, at which it granted all four places of 80-point objective B to infantry that could not
arrive. In the replay, holds caused by such reservations are 27,724 of T9-v2's 29,272 held moves on the 2120531121 C3
T9-v1 states and 1,684 of 1,730 on the 1930331196 C3 T9-v1 states; the candidate has none, by construction. Its remaining
holds are of two kinds only: four places with more claimants that can arrive, and claimants that cannot arrive
themselves. Hypothetical episode lengths on recorded states are not comparable across policies (a selected unit never
departs in a trajectory another policy produced, so the same overflow recurs), and no episode bound is claimed. A
claimant stays held while four units that can arrive hold the places and are not yet there; with a reservation that
cannot be honoured no longer counted, such a hold ends when the owners arrive and the objective is taken, or when the
clock rules the claimant out.

## 11. Tests

`tests/test_t9_batch.py` (synthetic, 25 tests): six claimants under every permutation of their order; four slow moves
before two near claimants and the reverse; an infantry unit against a vehicle at equal route cost; ties that straddle
the selection cut under ten orders; one to four standing incumbents; active movers counted and never ordered; a
dominated mover retained; a mover that cannot arrive holding no place, at the exact boundary; a late claimant never
selected, at the exact boundary; a staged unit competing again from its staging hex; an objective taken between
decisions; every objective already held; every target objective full; staging as a same-route prefix with at most three
units per staging hex and never on another objective; a gate rejection of a staged move; unrelated actions and their
order; the deployment stage; unavailable, suppressed and transitioning units; missing speed and missing clock; an
internal failure; the seven-objective shape under five reorderings; agent replay; and the candidate's absence from
every run card. `tests/test_t9_batch_replay.py` (15 tests) plants a defect into each replay check (cross-objective move,
stop on another objective, off-route and non-prefix shortening, invented move, changed unrelated action, unreachable
owner, an order-dependent allocator, a move for a moving unit, an early arrival) and requires the check to see it.
`scripts/mutate_t9_batch.py` first runs both modules unmutated, then plants 28 defects, including four that restore
emission order (in the rank, the per-objective grouping, the staging order and the tie-break) and one that ranks by
route cost only: 28 of 28 killed
(`evaluation/s11-batch-allocator/mutation.json`). `tests/test_s11_batch_results.py` binds the committed results to these
claims and to the current candidate source; `tests/test_real_t9_batch.py` regenerates both result files from the
private captures and compares them byte for byte (server only).

## 12. Offline gate and disposition

| Requirement | Result |
|---|---|
| Permutation invariance | synthetic tests under every order; 3,079 replayed decisions under three reorderings each; four order-restoring mutants killed |
| Seat-locality | the module reads the seat's observation and the setup cost data only |
| No cross-objective redirection | 0 in every replayed decision, H0 included |
| No capacity violation | 0 objectives pushed above four counted places |
| No unrelated-action change | 0 |
| Improved allocation certificate in 2120531121 C3 | section 7 |
| No replay evidence of recreating the 1930331196 corridor changes | section 8 (no redirection; C3 first decision as T9-v2) |
| Staging and withholding materially better than T9-v2, or remaining holds explained | section 10: every hold caused by an unreachable reservation is gone; the remainder is explained |
| No silently assumed engine operation | every operation used is OBSERVED_SUPPORTED (section 2) |

Disposition: **READY_FOR_SMALL_EXPLORATORY_PROPOSAL**. No proposal is registered or run. Two limits travel with it: the
offline evidence cannot say whether the primary scenario's benefit survives without redistribution (section 9), and C2's
first-decision allocation differs from T9-v2's (section 8). The residual reservations kept only because a mover cannot be
re-ordered (1 to 6 units per game here) could be released only by a stop on a traversing unit, the smallest open
engine-mechanism question; the design does not need it.
