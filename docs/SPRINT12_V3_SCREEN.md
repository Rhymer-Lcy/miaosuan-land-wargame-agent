# Sprint 12: registered exploratory screen of `t9-batch-capacity-v3`

**REGISTERED — EXPLORATORY TRACK — EXECUTED 2026-10-05 — STOPPED AFTER P1 — NOT_PRESERVED_IN_PRIMARY**

Execution note (2026-10-05): the owner reviewed this registration at `main` `25d1ab1b160ff6e8d9bd8df703f3b0a475377fc7`
and authorized execution of the full registered screen under its frozen rules. P1 ran in sessions 2787 to 2790; its
committed report stopped the screen by the frozen interim rule, so P2, A1 and A2 were neither built nor run. Sections 1
to 9 are the registration as approved and are not edited; the results are in section 10.

This document records the registration of the Sprint 12 screen. It authorizes no engine session: P1 is not executed,
session 2787 is not opened, and the engine ledger stays closed through session 2786. The owner reviews this
registration once more before any engine execution is authorized. Dates are business dates in UTC+8.

## 1. Approval and scope

On 2026-10-05 the owner approved the screen proposed in `docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md` at `main`
`4def396f3a5118189c0b2baf07af740c8b3e1e63`, for registration work only, with these requirements:

* the approved design unchanged: a hard ceiling of 12 sessions after 2786, 9 on the path without a stop or a
  replication, P1 and P2 in 2130511121 first with H1 and H2 balanced, A1 covering 2120531121 C3, 1930331196 C2 and
  1930331196 C3, A2 conditional exactly as drafted, every directional threshold, the immediate stops S1 to S13, the
  structural stop S14, the evidence boundaries and the disposition rules as drafted;
* `t9-batch-capacity-v3` source-frozen at `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8`;
* full-step private capture of every game, preserved through the close-out (lossless compression allowed, deletion
  of evidence not);
* every adaptive-stage rule frozen and tested before the first session: no decision code, threshold, observer
  semantics, replication rule or classification may be edited after it; if a later stage needs such a change, the
  screen stops and returns to the owner;
* the run-card safeguard of `tests/test_t9_batch.py` replaced by an exact whitelist, not removed;
* the draft companion kept as proposal evidence; a separate stage-card infrastructure;
* no public issue; ordinary fast-forward commits only.

The draft and its companion `evaluation/s12-batch-allocator-draft/draft.json` are unchanged and remain the approved
proposal. Where this document and the code differ, the code at the registration commit governs, and the code is
pinned by digest in every stage card.

## 2. Identities

| Item | Identity |
|---|---|
| Candidate | `t9-batch-capacity-v3`, policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8` |
| Frozen baseline | `baseline-v2` (`baseline-v2-candidate-shoot-target-reservation`), policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| Rules | `evaluation/s12_screen.RULES`, SHA-256 `1f7156f193ada6d686fa4cb3f13f2e92d6c360ca174530085c6cf4821b22b00b` (the draft's values, checked against the draft companion by `tests/test_s12_screen.py`) |
| Budget | ledger base session 2786, ceiling 12, exclusive diagnostic sessions, one game at a time, `baseline-v1-runtime-r2` |

## 3. Stage cards

| Stage | Card id | Games (screen positions) | Exists before execution |
|---|---|---|---|
| P1 | `s12-v3-primary-1` | 2130511121 H1, H2, H1, H2 (1 to 4) | yes: `evaluation/s12-v3-primary-1/manifest.json`, canonical SHA-256 `3ea02487849e5558f7888e3a13a0844b6dc17ba11cc552862c84cf21acb970bb` |
| P2 | `s12-v3-primary-2` | 2130511121 H1, H2 (5, 6) | no |
| A1 | `s12-v3-adverse-1` | 2120531121 C3, 1930331196 C2, 1930331196 C3 (7 to 9) | no |
| A2 | `s12-v3-adverse-2` | the A1 configurations with a replication trigger, in that order (10 to 12) | no |

Game ids are `<scenario>.<condition>.<card>.p<position>`. A later card can only be built by
`scripts/build_s12_card.py` from the committed report of the stage before it, and only when that report's decision
permits it (`s12_screen.prerequisite`); A2 holds exactly the configurations the A1 report names. Every card pins the
rules, the two policy identities, the budget, the committed report that permits it (by digest) and the normalised
SHA-256 of 18 frozen implementation files (`s12_screen.FROZEN_FILES`: the screen's modules, card builder, game entry
point, stage runner, analysis and tests, and the shared modules they rely on, the registered evaluator included). The
game entry point and the stage runner refuse a card whose pins differ from the checkout, or that does not rebuild
byte for byte from the committed reports, so no frozen file can change after the first session without stopping the
screen.

## 4. What was implemented and where

| Part | File | Content |
|---|---|---|
| Rules and stage logic | `src/miaosuan_agent/evaluation/s12_screen.py` | identities, budget, schedule, rule values, primary and adverse classifications, replication triggers, stage decisions, card building and prerequisites, card pin checks, ledger audit (S1, S2), disposition, public report and sanitizer (S3) |
| Observers | `src/miaosuan_agent/evaluation/s12_capture.py` | `V3CompactCapture` (the v3 trace block: changes, staging, hold episodes, errors) and `V3Timeline` (full-step private snapshots of the all-seeing state and every seat's observation and memory, the final state, and at every decision of a `baseline-v2` or v3 seat the seat-local reconstruction compared with the live decision) |
| Per-game facts | `src/miaosuan_agent/evaluation/s12_timeline.py` | stops S1 and S4 to S14 recomputed from the record and captures, classification facts, and every mechanism endpoint of the draft's section 9 |
| Card builder | `scripts/build_s12_card.py` | stage cards from the committed reports (`--check` byte for byte); separate from `scripts/build_run_card.py`, whose cards are unchanged |
| Game entry point | `scripts/run_s12_game.py` | one game under Sprint 9's `T9Capture` (unchanged) and the two new observers; five capture files written exclusively; the game's own stops checked afterwards (exit 3) |
| Stage runner | `scripts/run_s12_stage.py` | clean committed tree, card and prerequisite checks (the previous report regenerated from the private records), staged inputs, then one game at a time in the registered evaluator's isolation, each followed by the full stop check (S1 to S14 with the ledger audit) before the next; any non-zero status or stop ends the stage |
| Analysis | `scripts/s12_screen_analysis.py` | `game` (one game's facts and stops), `report` (the public stage report, `--check`), `disposition` |
| Rehearsal | `scripts/s12_rehearsal.py` | the real-capture rehearsal and the timing benchmark (server only) |
| Tests | `tests/test_s12_screen.py`, `tests/test_s12_timeline.py`, `tests/test_s12_capture.py`, `tests/fixtures/s12_engine.py` | 53 tests (section 8) |
| Mutation | `scripts/mutate_s12_screen.py`, `evaluation/s12-v3-screen/mutation.json` | 48 mutations |

The registered evaluator, the exploratory runner (`scripts/run_explore.sh`, `scripts/run_explore_game.py`),
`scripts/build_run_card.py`, Sprint 9's `T9Capture` and every historical card are unchanged.

## 5. Capture

Every game writes, under the ignored `local/evaluation/<card>/`: its record (`games/<id>.json`) and five capture files
(`capture/<id>.t9.json`, `.v3.json`, `.v3series.json.gz`, `.timeline.json`, `.timeline.pkl`), each created exclusively
and digested in the record. The timeline holds a full snapshot for every decision and the final post-step state. No
file is overwritten, deleted or replaced; the evidence is kept through the close-out. The public files hold aggregates
and sanitized certificates only: objectives by value and Sprint 11's letters, units by kind, steps and counts.

The timeline re-decides each `baseline-v2` and v3 seat from that seat's own observation and memory and compares the
reconstruction with the live decision (actions; for v3 also the add-on changes, skip counts and `baseline-v2`'s trace
digest). It records the complete v3 allocation of every decision: standing incumbents, counted movers with their
remaining bounds, movers that hold no place, free places, ranked claimants with free-flow time, cost, path length,
feasibility and status, selected claimants, staged paths and withheld units with reasons. From these the analysis
derives arrival, path end, stationarity, first occupation listing, occupation order and response, ownership
transitions, predicted and actual arrival, arrival slack and delay, the selected place's outcome, unproductive
places, counted against raw commitments, staging-hex occupancy, staging-induced waits, hold episodes, direct-fire
availability, orders and responses, and capture order. "Can arrive before `max_step`" remains the policy's admission
test only; usefulness is the measured outcome. No commitment-horizon constant was added.

## 6. Clarifications made at registration

None changes a threshold, a stage, a stop or a disposition row of the draft; each closes a case the draft did not
spell out, and each is fixed in the frozen code.

1. Place outcomes are exhaustive and taken in order: LOST, NEVER_ARRIVED, OCCUPIED, HELD, REDUNDANT, TOO_LATE, and
   ARRIVED_NOT_DECISIVE for any other arrival (it arrived before own control, did not occupy, did not stand there at
   the end, and the objective is own at the end).
2. "The fifth objective" of 2120531121 C3 is the objective whose last change to own control is the latest when all
   five are own at the end; the late-capture trigger (after step 2,736) and the attribution to v3's selections (a place
   on it with outcome OCCUPIED or HELD) use it. Every objective, Sprint 11's objective A included, is reported by label.
3. S13's known refusal classes are `baseline-v2`'s four, the duplicate occupation (code 1804), and every class seen in
   a `baseline-v2` seat of the same or an earlier screen game.
4. S7 also covers observer errors, a missing or digest-mismatched capture, a decision without a reconstruction, a
   disagreement between capture and record on steps or move orders, and a `max_step` other than 2,880.
5. S1 is also read from each record's session close; S8 also fires when more than four own ground units stand on one
   hex, and when the counted places before a decision already exceed four.
6. S9 is recounted from the observation and the emitted moves that differ from `baseline-v2`'s, not from the
   policy's own bookkeeping; S10 to S12 use the Sprint 11 structural check on the emitted actions against the
   reconstructed `baseline-v2` actions.
7. Mechanical disposition of a stop: S5, S8 to S12 and S14 are defects of v3 (STRUCTURAL_FAILURE); S1 to S4, S6, S7
   and S13 give SCREEN_INCOMPLETE unless a committed attribution file (`evaluation/s12-v3-screen/stop-attribution.json`)
   records an investigation showing a v3 defect. Any staging-induced wait that lasts to the end of a game prevents
   READY_FOR_CONFIRMATORY_PROPOSAL.
8. A stage whose card lists more games than have facts is decided STOP (incomplete). The stage runner stops on any
   non-zero game status, stricter than the exploratory runner's three consecutive failures.

## 7. Validation before handoff (no engine, no session)

* **Real-capture rehearsal** (`evaluation/s12-v3-screen/rehearsal.json`, the six frozen Sprint 10 full-step captures
  pinned by SHA-256): the reconstructed `baseline-v2` actions equal the captured ones at 17,286 of 17,286 decisions;
  the v3 places and held moves equal Sprint 11's replay at 3,116 of 3,116 decisions, and the kept, shortened and
  withheld totals and the hexes removed by staging equal Sprint 11's in every game; the arrival audit reproduces
  Sprint 11's exactly (139 exact, 9 late, 34 never, 0 early); in the `baseline-v2` 2120531121 C3 game objective A is
  first own at decision 564 with two units standing on it; in the `baseline-v2` 1930331196 C2 game the direct-fire
  order at decision 611 is accepted; in every game the value of the objectives held at the end equals the occupy
  score. Measured on existing data before registration, the recomputed stops S8, S9, S10, S11 and S12 report nothing
  on 3,119 correct v3 decisions, and no state of the six games has more than four own ground units on one hex (each
  reaches four). Two planted defects (no staging, staging cap four) were each caught; an earlier version of the
  rehearsal compared only places and held moves and missed the first, so the totals comparison was added.
* **Stand-in rehearsal** (private script `local/diagnostics/s12/standin_rehearsal.py`, server, committed tree; the
  engine factory replaced by the PS-1 stand-in and the ledger session by a context that records nothing): with real
  staged inputs the first P1 game completed through the real game entry point, wrote its record and five captures with
  matching digests, raised S7 (the stand-in's 40-step game is not the 2,880-step scenario), and the runner stopped after
  that game with status 3; on the stand-in's own scenario all four P1 games (2,881 steps each) completed with no stop
  and no reconstruction difference, the P1 report was computed by the frozen rules (STOP, tactical: the stand-in
  scores nothing) and the P2 card was then refused as not permitted; an unknown game, an existing record and the P2,
  A1 and A2 stages without their prerequisite reports were refused. The ledger file was byte-identical before and
  after, and nothing was written under `local/evaluation`.
* **Planted and mutation tests.** Each of S1 and S4 to S14 is planted into a copy of a stand-in game and must fire
  (`tests/test_s12_timeline.py`), with S14 also tested directly on its positive case and seven negative ones; every
  place outcome is produced on synthetic states; every stage decision, every card prerequisite, the mechanical A2
  composition, a changed threshold and a changed report outcome lead to the declared next card or stop
  (`tests/test_s12_screen.py`); the observers are shown not to change the game and to catch a live decision that
  differs from the allocation (`tests/test_s12_capture.py`). The mutation run killed 48 of 48 mutations of rule
  values, comparisons, stage logic, prerequisites, disposition, ledger audit, sanitizer, recomputed stops, outcomes and
  observers; its first run killed 45 and exposed two test gaps (a disposition test that compared with the module's own
  set, and no refused occupation with the flag turning own) and one equivalent mutation, all fixed before
  registration.
* **Privacy.** Every public serializer refuses forbidden keys; tests plant unit ids and require their absence from
  the public facts and reports. The repository privacy scan (all reachable history) rose from 81 to 101 hits: the 20
  new ones are the word "secrets", the sanitizer's former parameter name for those planted ids, in two of this
  registration's commits; the parameter was renamed in a later commit, history is not rewritten, and the hits were
  adjudicated benign, so 101 is the new baseline.
* **Timing** (`evaluation/s12-v3-screen/timing.json`): the complete observer stack replayed over the largest Sprint 10
  capture (2,881 decisions) took 17.7 s (6.14 ms per step), the per-game analysis 15.8 s. Projected to a 2130511121
  head-to-head game (two reconstructed seats, 89 operators: factor 3.296) on Sprint 10's longest head-to-head wall
  time of 131.8 s, a game takes about 192 s; with Sprint 10's largest in-game full-step observer time (154.7 s) instead
  of this measurement, 641.7 s, and 694.0 s with the analysis, against the 1,800 s wall cap and the 2,100 s process
  timeout.
* **Whitelist.** `tests/test_t9_batch.py` now requires that v3 occur in a card only as one of the four approved stage
  card ids, each binding the frozen v3 digest and listing `experiments/t9_batch.py`; that no historical card or
  builder names it; that any other manifest naming it fails; and that the v3 source still hashes to the frozen digest.
  `tests/test_s12_proposal_draft.py` was changed in the same way; the draft companion is still not a card.

## 8. Running (after the owner's authorization only)

```
python scripts/run_s12_stage.py --python PYTHON --sdk-archive ZIP --stage P1
python scripts/s12_screen_analysis.py report --stage P1          # then commit the report
python scripts/build_s12_card.py --stage P2                      # only if the report permits it; commit the card
```

and so on for P2, A1 and A2, followed by `python scripts/s12_screen_analysis.py disposition`. Each report is committed
before the next card is built; the runner regenerates it from the private records before the next stage plays.

## 9. Not claimed

No engine result exists for v3. Nothing in this registration is evidence of a score effect, and no outcome of the
screen can promote a baseline.

## 10. Results (2026-10-05)

Every figure below comes from the committed report `evaluation/s12-v3-primary-1/report.json` (regenerated byte for
byte from the private records and captures by `scripts/s12_screen_analysis.py report --stage P1 --check`) and the
disposition `evaluation/s12-v3-screen/disposition.json`. Everything is exploratory and directional; historical
populations are descriptive references only, and nothing is pooled.

### 10.1 Sessions and games

| Session | Game | v3 seat | Margin | v3 coverage | Objectives at the end | T9-v2-like | Collapse | Stops |
|---:|---|---|---:|---:|---:|---|---|---|
| 2787 | 2130511121 H1, position 1 | red | -609 | 0.5691 | 0 | yes (coverage below 0.618) | no | none |
| 2788 | 2130511121 H2, position 2 | blue | 481 | 6.0056 | 6 | yes (margin below 865) | no | none |
| 2789 | 2130511121 H1, position 3 | red | -1,037 | 0.2885 | 0 | yes (coverage below 0.618) | no | none |
| 2790 | 2130511121 H2, position 4 | blue | 585 | 5.7139 | 6 | yes (margin below 865) | no | none |

All four games completed (2,881 steps, 124.1 to 154.9 s each), every session closed with integrity ok, and no stop
S1 to S14 fired after any game or at stage level. The seat-local reconstruction equalled the live decision at all
5,762 reconstructed decisions of every game; the recomputed structural checks found no cross-objective move, no
non-prefix staging, no invented move and no changed unrelated action; counted commitments never exceeded four (raw
commitments never either); no refusal was recorded in a v3 seat; the v3 seat's decision latency had a 99th
percentile of at most 2.362 ms and a maximum of 177.9 ms.

### 10.2 Decision

The interim rule (two games per seat) applied to P1: 0 collapse games, 2 of 2 H1 games T9-v2-like and 2 of 2 H2 games
T9-v2-like, so all four games were T9-v2-like and the rule stopped the screen (decision STOP, tactical). As registered,
this case is the one in which the final classification is NOT_PRESERVED whatever P2 would show. The seat average,
-145.0, enters no rule here and is reported descriptively; it is not comparable with T9-v1's registered +305.47, which
belongs to Sprint 9. The P2 card was then refused by the builder (the report does not permit it). The frozen
disposition is **NOT_PRESERVED_IN_PRIMARY**: v3 is not pursued in this form. Sessions used: 4 of the ceiling of 12;
nothing else was played, retried or replaced.

### 10.3 Placement against the historical populations (descriptive)

* H1, v3 red: margins -609 and -1,037, inside both reference ranges (T9-v1 -1,003 to 1,035, median -737; `baseline-v2`
  red -1,195 to -217, median -919). Red coverage 0.5691 and 0.2885, below T9-v1's lowest (0.618) and around
  `baseline-v2`'s median (0.378); no objective held at the end in either game.
* H2, v3 blue: margins 481 and 585, below T9-v1's lowest (865) and below `baseline-v2`'s fresh median (919). Against
  T9-v1's H2 games: opponent totals 561 and 509 (T9-v1 84 to 369), own attack 442 and 466 (T9-v1 490 to 548), own
  units lost 18 and 16 (T9-v1 3 to 16), 6 objectives at the end in both games (T9-v1 7 in all 15).
* Both seats therefore sit with T9-v2's smoke games (H1 coverage about 0.42, H2 margin 815) rather than with
  T9-v1's registered games, as the offline replay of Sprint 11 had suggested.

### 10.4 Mechanism (descriptive)

* Staging and withholding: 38, 68, 17 and 68 staged moves; the longest hold episodes 112, 62, 2 and 61 decisions; no
  hold reached the 1,440-decision flag. Staging-induced waits occurred in the two H2 games only (9 and 7 episodes, at
  most 20 steps; none above the 144-step flag, none to the end of the game); every game's busiest staging hex held 4
  own ground units at some step.
* Queues: own waiting unit-steps 188, 184, 294 and 200. As blue this is above T9-v1's largest value (6) and was flagged;
  `baseline-v2`'s blue seats queued 1,469 to 31,065.
* Places and outcomes (selected places 39, 56, 30 and 67): OCCUPIED 9, 19, 6 and 22; LOST (the unit was destroyed
  before arriving) 18, 10, 15 and 10; TOO_LATE 8, 4, 7 and 3. TOO_LATE means that the objective was not own at the end
  and the unit's own occupation was not accepted; in head-to-head play that includes objectives taken first and lost
  later. Of the 22 TOO_LATE arrivals, 18 came with more than 2,000 steps left and 4 with 63 to 138 steps left (from the
  private facts), so the class does not mean that the arrival came late.
* Arrival against prediction: no arrival was earlier than its free-flow time (the lower bound held); arrival delays
  had a median of 0 and a maximum of 12, 0, 6 and 61 steps; the path ended in the arrival state every time; where a
  unit later became stationary it did so 75 steps after its path end at the earliest; the first occupation listing
  came a median of 0 steps after arrival (at most 380). Occupation orders: 6, 12, 5 and 17, all accepted; direct-fire
  orders 58, 74, 49 and 78, all accepted.
* Places that were never honoured: in 298 of 319, 187 of 405, 13 of 14 and 57 of 350 decisions in which v3 staged or
  withheld a selectable claimant, at least one counted place of that objective was held by a unit that never stood on
  it before the end (12, 6, 4 and 5 such holders; every one of the 27 was no longer among the seat's units at the end,
  that is, destroyed, per the private facts). The end-of-game test excludes only units that cannot arrive in time; a
  counted mover that is destroyed en route keeps its place until it is gone. This is an observation from four games,
  not a tested effect.

### 10.5 Not run

P2 (positions 5 and 6), A1 (2120531121 C3, 1930331196 C2, 1930331196 C3) and A2 were not built and not run. There is
therefore no Sprint 12 evidence on the 2120531121 C3 arrival and occupation question or on the 1930331196 firing
windows; Sprint 10's and Sprint 11's evidence on them stands as it was.
