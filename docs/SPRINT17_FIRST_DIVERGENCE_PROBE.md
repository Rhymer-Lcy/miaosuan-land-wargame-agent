# Sprint 17: registered executable first-divergence mechanism probe

**REGISTERED — EXPLORATORY TRACK — MECHANISM PROBE, NOT A SCORE SCREEN — TWO ENGINE SESSIONS — NOTHING PROMOTED**

On 2026-10-06 the owner authorized a registered two-session engine mechanism probe. Sprint 16 left the delayed
post-staging redistribution rule `MECHANISM_AMBIGUOUS`: on frozen v3's own trajectories its first divergence came at
decision 421 in 1930331196 C2 and at decision 361 in 2120531121 C3, before the events those configurations protect, so
the consequences could not be read from v3's games. This sprint plays an executable form of that rule once in each of
the two configurations against the inert control and observes what happens after it crosses those two divergences. It
is not a score screen, not a confirmation and not a performance comparison; no score enters any rule, and nothing can
be promoted. Dates are business dates in UTC+8.

Sections 1 to 14 are the registration. They are committed and pushed, with every frozen file, the card, the frozen
inputs, the tests and the mutation record, before session 2794 is opened, and are not edited afterwards; results follow
in a separate section.

## 1. Starting state and fixed results

| Item | Identity |
|---|---|
| Repository | `main` `a4362d75a12cfea70a0e2c054199ee2ec9bf122b`, tree `8ab1c3227a136cb241db951de35f7866e9a1b3dc`, identical on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,793 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `ce852ed35c26e98d5d5de831f224642bfb85dde6542039a926f55a676bb83934`; session 2794 never opened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| Frozen v3 (`t9-batch-capacity-v3`, stage 1 of the candidate, not itself played) | policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8`, unchanged |
| Candidate (the only engine policy of this sprint) | `t9-delayed-post-stage-any-v6`, policy source `b60e3812a8d43ffaf3a015c87783f7693d8e98894c4fb2363b90ea59dd306ec0` |
| Privacy baseline | the 104 hit lines accepted at Sprint 14's close and reproduced at Sprints 15 and 16, compared as a set of lines |

Fixed and not reinterpreted: Sprint 12 `NOT_PRESERVED_IN_PRIMARY`, Sprint 13 `REDISTRIBUTION_DOMINANT`, Sprint 14
`NO_ENGINE_CANDIDATE`, Sprint 15 `NO_RESTORING_TRIGGER`, Sprint 16 `MECHANISM_AMBIGUOUS`. Sprint 16 established on
v3's own trajectories: in 1930331196 C3 the rule never diverges (no admissible alternative ever exists), so it equals v3
on that whole game; in 1930331196 C2 its first divergence is at decision 421 (two staged vehicles redirected, no firing
role, before v3's direct-fire orders at decisions 611 and 686); in 2120531121 C3 it is at decision 361 (two staged
vehicles redirected into the problem objective, no bad-reservation clause, before v3's first ownership of that
objective at decision 564).

## 2. Scope and the nature of the evidence

* Exactly two sessions are authorized: 1930331196 C2 (expected session 2794), then 2120531121 C3 (expected session
  2795). No third session, no replication, no replacement of a failed or opened session without new owner approval. A
  session that is opened and fails counts.
* There is no 1930331196 C3 session: Sprint 16 showed the rule equal to v3 for the whole observed C3 trajectory, and
  this sprint's rehearsal (section 11) replays the executable agent over all 2,881 decisions of that game and finds it
  equal to v3 at every one.
* One game per configuration is a mechanism probe: it shows one observed trajectory. Findings are stated as facts of
  that trajectory; no statistical, population or score claim is made.

## 3. The executable candidate `t9-delayed-post-stage-any-v6`

`src/miaosuan_agent/experiments/t9_post_stage_v6.py` (identity `t9-delayed-post-stage-any-v6`, add-on trace block
`t9_delayed_v6`) is the executable form of Sprint 16's target shadow `s16-delayed-post-stage-any-shadow-v6`. It is new:
it is not `t9-batch-capacity-v3`, not `s16-delayed-shadow-v6` and not any Sprint 15 identity, and it adds no tactical
condition (no threat, scenario, objective or timing filter, no shooter protection, no threshold, no special case: the
module holds no numeric literal other than the 0 and 1 flag values of the copied memory update). `baseline-v2` decides
first, unchanged; one decision is then:

1. **stage 1**: frozen v3's allocation (counted incumbents, claimants ranked by free-flow time, places by rank), as
   restated unchanged inside the frozen Sprint 15 allocation;
2. **memory**: Sprint 16's corrected deferred-history update. A unit standing on an objective its side holds keeps its
   record; a unit standing on an objective its side does not hold, a unit moving to an objective, an absent unit, a
   unit given a place and a unit that cannot arrive before the end lose it; the episode (but not the staging fact)
   ends when its source is held by the side. The function is the Sprint 16 shadow's `observe`, copied verbatim (a test
   compares the two function bodies node for node), so that the candidate's source set holds no analysis module;
3. **eligibility**: the frozen `delayed-post-stage-any` trigger: an overflow claimant that completed a staging move this
   add-on emitted, toward any source;
4. **redirect**: Sprint 14's `feasible-value-redirect` admissibility (objective not held by the side, fewer than four
   counted places, route cost at most twice the cost to the own objective, free-flow arrival before the end) and ranking
   (cost per value, cost, hex), in v3's claimant order;
5. **bounded recourse**: at most one redirect per memory episode;
6. **deterministic, seat-local memory**: integer pairs keyed by own unit id, holding only own hexes and objective
   coordinates read from the seat's own observation; deleted with the unit; empty at the start of every game (the
   agent's setup and reset); no state crosses sessions;
7. **fail closed**: memory that cannot be decoded or updated is dropped (nobody eligible, v3's decision); if the
   allocation cannot be computed, every own ground move to an objective is withheld for that decision; if the add-on
   raises, the wrapper plays `baseline-v2`'s decision and records the error.

With nobody eligible the decision equals frozen v3's exactly, actions and order included; with an empty memory nobody is
eligible. `t9_batch`, `t9_redistribution`, `t9_delayed` and the add-on wrapper are imported and called unchanged, and
their normalised digests equal the ones Sprint 16's card pinned.

**Integration.** No difference in decisions from the Sprint 16 shadow. The only engine-integration elements are the
existing add-on wrapper (`experiments/exploratory_addon.py`, unchanged) and the trace's change records, which take the
form of Sprint 15's add-on (`changes`, then an `error` record if any, then one `memory-ended` record per record deleted
at the decision). `t9_delayed.py` enters the candidate's source set as a library; its own v5 identities stay
non-executable.

**Source identity.** 27 files: `baseline-v2`'s set, `experiments/exploratory_addon.py`, `experiments/t9_batch.py`,
`experiments/t9_redistribution.py`, `experiments/t9_delayed.py` and `experiments/t9_post_stage_v6.py`, digest
`b60e3812a8d43ffaf3a015c87783f7693d8e98894c4fb2363b90ea59dd306ec0` (line endings normalised, as for every identity).

## 4. The card, the runner, the stops and the whitelist

The card is `evaluation/s17-post-stage-v6-probe-1/manifest.json` (exploratory run-card schema, built and checked by
`scripts/build_s17_card.py`; frozen rules in `src/miaosuan_agent/evaluation/s17_probe.py`). It binds exactly
`baseline-v2` and the candidate, names Sprint 16's card and its canonical digest as the source of the prefix
trajectories, and pins the normalised SHA-256 of 28 frozen implementation files (`s17_probe.FROZEN_FILES`: the
candidate and the frozen modules it imports, the Sprint 17 modules, scripts and the two Sprint 17 test modules, and the
reused observers, analysis modules, game loop and evaluator).

| Position | Game id | Scenario | Condition | Red | Blue | Expected session |
|---:|---|---|---|---|---|---:|
| 1 | `1930331196.C2.s17-post-stage-v6-probe-1.p01` | 1930331196 | C2 | candidate | inert control | 2794 |
| 2 | `2120531121.C3.s17-post-stage-v6-probe-1.p02` | 2120531121 | C3 | inert control | candidate | 2795 |

The seats are Sprint 10's and Sprint 16's. Budget: ledger base session 2793, ceiling 2, exclusive diagnostic sessions,
one game at a time, runtime `baseline-v1-runtime-r2`.

`scripts/run_s17_probe.py` refuses to start unless the tree is clean and committed with no untracked file outside the
ignored tree, the card rebuilds byte for byte, every pin equals the checkout, the private prefix reference (section 6)
exists with the digest `inputs.json` pins, and the ledger audit passes. It plays the games in card order through
`scripts/run_s17_game.py` in the registered evaluator's isolation, with a hard timeout. The game entry point refuses,
before the engine is touched, a card that does not rebuild, a changed pin, a candidate source other than the registered
digest, a dirty tree, an existing record or capture, a session beyond the ceiling, a wrong thread environment, a missing
or altered prefix reference, or mismatched inputs. After each game, before the next one starts:

| Stop | Meaning |
|---|---|
| S1 | engine-installation integrity failure (session close or the ledger's state chain) |
| S2 | ledger inconsistency: a session after 2793 that is not the card's game in schedule position, under the card's digest and the candidate's registered digest, opened once and closed; an unclosed session; more than two sessions |
| S3 | privacy exposure: a file outside the ignored tree appeared, or a tracked file changed, during the game |
| S4 | a contract error, a margin that is not the engine's `<side>_win`, or a game that did not complete |
| S6 | a replay mismatch |
| S7 | capture or reconstruction failure: an observer error; a missing or digest-mismatched capture; a live decision, add-on change record, skip count or memory (the add-on's or `baseline-v2`'s) that differs from the seat-local reconstruction; a candidate add-on error; captures and record disagreeing on the number of steps or on the seat's move orders; a decision not reconstructed; a scenario, condition or seat other than the card's; a `max_step` other than 2,880 |
| SP | prefix failure (section 6) |

Any structural stop, or a non-zero game status, ends the study at once; nothing is retried. **There is no tactical
early stop**: no mechanism endpoint is evaluated between the games, and the second game is played whatever the first
game's tactical result.

**Whitelist.** Sprint 16's v3 whitelist (`tests/test_t9_batch.py` and its copy in `tests/test_s12_proposal_draft.py`)
is not changed: the Sprint 17 card and every Sprint 17 public file name neither v3's identity nor its digest, and both
safeguards pass unchanged. The narrow authorization for this sprint is a new safeguard
(`tests/test_t9_post_stage_v6.py`): the identity `t9-delayed-post-stage-any-v6` may appear in exactly one run card,
`evaluation/s17-post-stage-v6-probe-1/manifest.json`, bound to the registered digest and source files; any other JSON
naming it must lie in `evaluation/s17-first-divergence-probe/` and is never executable; the generic builders and
runners and the earlier entry points name neither the module nor the identity; and only the four Sprint 17 scripts
import the module. No wildcard, folder family or generic v6 permission exists, and no historical card becomes
executable. There is no duplicate copy of this new safeguard.

## 5. Capture

Every game runs three read-only observers through Sprint 9's `Tee`: Sprint 9's `T9Capture` and the exploratory capture
(`evaluation/exploratory.py`), both unchanged, and the Sprint 17 timeline (`evaluation/s17_capture.py`), which is
Sprint 12's full-step timeline adapted to the candidate. It keeps, for every decision, the all-seeing state, every
seat's observation (action listings, own and seen units, move paths, movement state, objective ownership) and memory,
the submitted actions and the engine's responses, and the final post-step state. At every decision of the candidate's
seat it re-decides from that seat's own observation and memory only: `baseline-v2`'s actions, trace digest and next
memory; the frozen stage-1 allocator's complete allocation on that state; and the candidate's allocation (claimants,
overflow, eligibility, best alternatives, redirects with route, cost and free-flow time, staging, withholding, ended
records, next memory). It compares the reconstruction with the live decision (emitted actions, the add-on's change
records and skip counts, `baseline-v2`'s trace digest, no add-on error, the policy and block names) and checks the
memory chain: the memory the seat carries into a decision must equal the reconstruction's memory after the previous
decision, and must be empty before the first. Any difference is S7. The record and five capture files per game are
written exclusively under the ignored `local/evaluation/s17-post-stage-v6-probe-1/` and digested in the record; nothing
is overwritten or deleted. The analysis repeats the whole reconstruction offline from the files, with the candidate's
memory re-derived from an empty memory, and requires zero differences.

## 6. The prefix check (SP) and its reference

`scripts/s17_analysis.py freeze` derives, from Sprint 16's v3 games of the two configurations (records and captures
pinned by SHA-256 in `inputs.json`) and the Sprint 16 target shadow, a private prefix reference
(`local/diagnostics/s17/prefix-reference.json`; `inputs.json` publishes its SHA-256). For each configuration it holds:
the digest of v3's emitted actions at every decision up to the registered first divergence; the digest of the
corrected-memory chain before every decision up to the one after the divergence; the digest of the registered
first-divergence actions; the units changed there and each redirect's objective and route; the digests of the seat's
observations up to the divergence; and the endpoint anchors of sections 7 and 8. The derivation refuses unless v3
re-decides every captured decision exactly, the first divergence is at decision 421 (C2) and 361 (2120531121 C3) with
two redirected vehicles each, the 2120531121 C3 redirects go to the problem objective, and the anchors below hold.

**SP passes only if**, in the new game: every candidate action list before the registered divergence equals frozen
v3's (content and order); the action list at the divergence differs from v3's and equals the registered one exactly;
the candidate's memory before every decision up to the one after the divergence equals the corrected-memory chain;
the changed units are exactly the registered two; and the redirects go to the registered objective along the
registered routes. The analysis re-checks SP independently. Whether the seat's observations are identical up to the
divergence is reported, not gated.

## 7. 1930331196 C2: endpoints and retirement

Anchors (Sprint 16's v3 game, derived and checked at freeze): first divergence at decision 421, two vehicles redirected
to 80-point objective A; v3's direct-fire orders at decisions 611 and 686 were made by one unit, an aircraft (the
same unit at both decisions), which had a direct-fire action listed at both decisions, and both orders were accepted.
Sprint 16's results text gave first ownership by step (50-point objective C at step 442, 80-point objective A at step
503); by decision, the definition used here (the first decision whose observed state shows the objective own), v3's
first ownerships in that game were 50-point objective A at decision 362, C at 443, 80-point objective A at 504,
50-point objective B at 805 and 80-point objective B at 886.

* **C2-PREFIX**: SP (section 6). A failure is structural.
* **C2-FIRE-611** and **C2-FIRE-686**: at exactly that decision of the new game, for the protected unit (the unit of v3's
  orders above): a direct-fire action (type 2) listed for it in the seat's own observation; a direct-fire order by it
  emitted at that decision; the engine's response to that order `accepted`.
* **Capture order**: every objective's first ownership decision and step, reported beside v3's (descriptive only).

**Retirement rule.** The candidate is **RETIRED BY C2** if the protected mechanism at 611 or at 686 is lost (not listed,
not emitted or not accepted at that exact decision). A later shot, another unit's shot, a higher total attack or a
better score never rescues it. If both hold, the class is `C2_MECHANISM_PRESERVED` and the change in capture order is
reported separately. The exact-decision test is deliberately strict: a shot shifted by one decision counts as lost.

## 8. 2120531121 C3: first ownership, the EARLY-PLACE BLOCK audit and retirement

Anchors (Sprint 16's v3 game, derived and checked at freeze): the **problem objective** is Sprint 11's 80-point
objective A (the 80-point objective T9-v1 never owned in Sprint 10's capture); v3 first owned it at decision 564; the
registered first divergence at decision 361 redirects two vehicles into it; and two units, both vehicles, stood on it
at v3's first ownership (v3's capturers).

* **212-PREFIX**: SP (section 6). A failure is structural.
* **First ownership**: the first decision whose observed state shows the problem objective own.
* **Pre-capture audit**: at every decision from 361 up to (not including) the first ownership, or to the last decision if
  it is never owned, and for every unit to which `baseline-v2` emits a move to the problem objective (a claimant), the
  analysis records: whether it can arrive before the end; its rank under v3's frozen ranking (selectable first, then
  free-flow time, route cost, path length, unit id); its free-flow time; the objective's counted places (own ground
  units standing on it plus counted movers, counted exactly as stage 1 counts them, and cross-checked against the
  stage-1 allocator's own count at every audited decision); how many of those places belong to the two decision-361
  units (a counted mover to it or standing on it); whether it is placed; whether it would be placed with only those
  early places removed; and its actual form (KEEP, REDIRECT, STAGE or WITHHOLD).
* **EARLY-PLACE BLOCK** (`s17_probe.early_place_rows`, mutation-tested): before first ownership, a claimant that (1) is
  selectable under the frozen v3-style allocation (it can arrive before the end), (2) does not receive a place, and
  (3) would receive one if only the places counted for the two decision-361 units were removed from the count. The
  audit refuses (a fidelity problem) whenever v3's ranking over the recorded claimants does not reproduce stage 1's
  actual selection.

**Retirement rule.** The candidate is **RETIRED BY 212** if (A) the problem objective is not first owned by decision 564,
or (B) at least one EARLY-PLACE BLOCK occurs before its first ownership. Otherwise the class is
`C3_212_MECHANISM_PRESERVED`. Score never overrides it. Reported, not gated: blocking after first ownership; blocks
attributable to places of any earlier candidate redirect into the objective (the same counterfactual with those places
removed as well); whether the two decision-361 units stay counted, survive and stand on the objective at first
ownership; and, for v3's two capturers, their claim decisions, forms, blocks and whether they stand on the objective at
the new first ownership (whether the original v3 capture mechanism is obstructed).

## 9. Disposition (first match)

| Disposition | Rule |
|---|---|
| `CAPTURE_INVALID` | any structural, fidelity, prefix or reconstruction requirement fails, or a configuration has no valid game |
| `MECHANISM_REFUTED_BOTH` | retired by C2 and retired by 212 |
| `MECHANISM_REFUTED_C2` | retired by C2, `C3_212_MECHANISM_PRESERVED` |
| `MECHANISM_REFUTED_212` | `C2_MECHANISM_PRESERVED`, retired by 212 |
| `MECHANISM_CROSSED_WITHOUT_KNOWN_REGRESSION` | `C2_MECHANISM_PRESERVED` and `C3_212_MECHANISM_PRESERVED` |

The last label means only that the executable candidate crossed the two previously ambiguous first divergences without
reproducing either registered adverse mechanism in these two observed games. It does not mean safe in general, better
scoring, a restored T9-v1 benefit, or ready for confirmation; nothing is promoted. If it holds, no score screen follows
automatically: the study returns to the owner. If either mechanism is refuted, the candidate is not patched in this
sprint and no new threshold is added; the sprint closes with the registered refutation.

## 10. Other reported facts (descriptive)

For each game: live prefix equality and observation identity up to the divergence; the first divergence (units changed
by kind, sources and destinations by label, route and own cost, free-flow time, v3's and the candidate's forms, Sprint
14's independent checks); every later candidate redirect by decision (count, kinds, labels, independent checks);
bounded recourse per memory episode from Sprint 16's episode tracker, now on the candidate's own trajectory; memory
bounds (largest number of records, ended records by reason, eligible-claimant decisions); every objective's ownership
sequence against v3's; the seat's direct-fire listings, orders and responses; and the record's scores, which enter no
rule.

## 11. Validation before session 2794

* **Tests** (`tests/test_t9_post_stage_v6.py`, 21; `tests/test_s17_probe.py`, 32): the candidate equals the Sprint 16
  target shadow, actions and memory, on 171 decisions of 32 synthetic sequences (with redirects among them) and its
  memory update and allocation equal the shadow's function bodies; equality with v3 before eligibility; the held- and
  unheld-objective transitions; one redirect per episode with no return within it; claimant order and emission,
  operator and router independence; seat-local, bounded memory; empty memory in every game; every fail-closed path;
  the source digest, the unchanged frozen modules and the whitelist; the card, schedule, budget and session mapping;
  every ledger defect including a third session; every structural check; each prefix clause; the fire endpoints at
  exactly 611 and 686; first ownership; the EARLY-PLACE BLOCK positive case, negative cases and the removal-of-early-
  places counterfactual; both retirement boundaries; the disposition order; the public guards; the observer's
  reconstruction and memory chain against a live agent, with tampering detected; and the analysis helpers.
  `tests/test_real_s17.py` (server) regenerates `inputs.json`, the prefix reference, the public results and the
  mutation record.
* **Mutation** (`scripts/mutate_s17.py`, `evaluation/s17-first-divergence-probe/mutation.json`): 56 planted defects in
  the candidate, the rules module, the observer and the analysis driver (each memory transition, the trigger, recourse,
  fail closed, the trace; the ledger, card and structural checks; every prefix clause; each fire clause; first
  ownership; the EARLY-PLACE BLOCK counterfactual; both retirement boundaries; the disposition order; the public
  guards; the memory chain). All 56 were caught, each with the card rebuilt inside the copy. The first run also caught
  56 of 56, but 14 candidate defects only because the mutated source no longer matched the pinned digest; the script
  now re-pins the digest inside the copy for candidate defects, so that only the logic tests can catch them.
* **Freeze** (server): the prefix reference reproduced the registered first divergences (decision 421 and 361, two
  vehicles each, both to 80-point objective A), the C2 fire anchors (one aircraft, listed, emitted and accepted at 611
  and 686) and v3's first ownership of the problem objective at 564.
* **Pre-engine rehearsal** (`scripts/s17_analysis.py rehearse`, server, private output): the candidate's agent
  (`PostStageAnyV6Agent`) replayed every recorded decision of the three Sprint 16 v3 games. It equalled frozen v3 at all
  421 decisions before 421 in C2, all 361 before 361 in 2120531121 C3 and all 2,881 of 1930331196 C3, produced exactly
  the registered actions at 421 and 361, carried exactly the corrected-memory chain, and equalled the Sprint 16 target
  shadow (actions and memory) at all 8,643 recorded decisions; the observer's reconstruction and consistency checks
  passed at all 3,665 on-policy decisions. The analysis's replay, run on the two Sprint 16 games as stand-ins, found the
  first live-versus-candidate difference exactly at 421 and 361, the C2 fire mechanism preserved in v3's own game, the
  problem objective first owned at 564 with both v3 capturers on it, no audit problem, and a prefix check that passes
  before the divergence and fails at it (the stand-in seat is v3).
* **Stand-in rehearsal of the runner** (private, `local/diagnostics/s17/standin_rehearsal.py`; stand-in engines, a
  session context that records nothing, the ledger file byte-identical before and after): a 40-step stand-in game
  completed, wrote its record and five captures with matching digests, raised S7 and SP, and the runner stopped with one
  game recorded; on the Sprint 12 stand-in scenario the first game completed with SP as its only structural stop
  (the stand-in world is not Sprint 16's) and the second game was not started; with the prefix check disabled inside
  the game module only, both games completed, the analysis re-derived all 2,881 decisions of each with no difference
  and the memory compared at every decision, found the prefix failure on its own and decided `CAPTURE_INVALID`, and its
  public files passed the privacy checks; an unknown game, an existing record, a dirty tree and an altered prefix
  reference were refused.
* **Disclosed before registration (an observation, not a prediction).** On v3's own 2120531121 C3 trajectory, from
  decision 361 to v3's first ownership, 12 units claimed the problem objective at 27 decisions (the first at 463), 126
  claimant-decisions in all, every one able to arrive; 4 were placed and 122 were selectable but not placed (114
  withheld, 8 staged), because the objective's places were already counted. That trajectory is off-policy for the
  candidate after 361, but it shows that the audit of section 8 will be exercised if claims arrive while the two early
  vehicles still hold counted places. The rule is the owner's and is deliberately conservative; it is not changed.
* **Registration checks**: the registration pushed and fetched back byte for byte; the server fast-forwarded; the
  workstation, GitHub and server at the same commit and tree; the candidate and v3 digests verified; the full non-engine
  suites run; the privacy scan compared as a set; the canary rebuilt; a read-only engine verify; the ledger still at
  2,793 with none unclosed. Their results are reported in the results section.

## 12. Maintenance disclosed with the registration

* Sprint 16's published `games.json` and `disposition.json` embed the audit of every session after 2790, so the two new
  sessions would make the server test that re-derives them (`tests/test_real_s16.py`) fail. That test now runs Sprint
  16's frozen analysis unchanged, in process, with its ledger read bounded at Sprint 16's last session (2793). Sprint 16's
  card, analysis code and public files are untouched (the test file is not among Sprint 16's pins).
* For the same reason, Sprint 17's own published ledger audit reads the ledger up to session 2795; the runner and the
  game entry point audit the whole live ledger, and the close-out verifies separately that no session after 2795 was
  opened.

## 13. Outputs and privacy

* Public (`evaluation/s17-first-divergence-probe/`): `inputs.json` (before session 2794: the Sprint 16 inputs by digest,
  the card's canonical digest, the candidate identity, the rules, the prefix reference's digest, and the anchors as
  decisions, labels and counts), `mutation.json`, and after the games `games.json` (sessions, reconstruction counts,
  prefix results, record facts), `mechanism.json` (per configuration: first divergence, later redirects, recourse,
  memory bounds, ownership against v3, direct fire, the C2 endpoints, the 2120531121 C3 audit summary, the
  decision-361 units and v3's capturers) and `disposition.json`; all three regenerate byte for byte
  (`scripts/s17_analysis.py run --check`). Every public file passes the forbidden-key and private-value checks and may
  not name v3's identity or digest.
* Private (ignored `local/`): records, captures, the prefix reference, `local/diagnostics/s17/analysis-private.json.gz`
  (unit ids, certificates, the full audit rows, episodes), the rehearsals.

## 14. Not claimed

No score, effect or population property. One game per configuration shows one trajectory. A preserved mechanism here
says nothing about other configurations or other trajectories, and a refutation retires this rule for the reason
registered, not the T9 line in general.

## Results (2026-10-06)

Every figure below comes from the committed public files of `evaluation/s17-first-divergence-probe/`, which
`scripts/s17_analysis.py run --check` regenerates byte for byte from the private records and captures, or from the run
logs kept privately. Scores are record facts that enter no rule.

### R1. Registration and pre-engine checks

Sections 1 to 14, every frozen file, the card, the inputs, the tests and the mutation record were pushed as commit
`93ac24e843958722533dbb469875389ea9476b25` (tree `629df1aeb80a60958f8eb91351df411e92658ddc`) at
2026-10-06T19:31:06+08:00, after an audit of its 13 commits; a fresh unauthenticated clone from GitHub had the same
commit and tree and all 16 changed files byte for byte. The evaluation server was fast-forwarded to the same commit by
bundle, and on that committed tree the card and `inputs.json` regenerated, the rehearsal passed every requirement and
the stand-in rehearsal passed with the clean-tree guards in force. Before session 2794: the workstation tree ran 1,612
tests (81 skipped) with exit 0, a clean clone from GitHub 1,609 (82 skipped) with exit 0, and the server's private tree
1,625 (1 skipped: the regeneration of the result files, which did not exist yet; 5,200 s) with exit 0 and the ledger
file byte-identical before and after; the privacy scan over every reachable blob (884 blobs) found 104 hit lines,
identical as a set to the accepted 104; the platform canary rebuilt byte for byte on both hosts; a read-only verify
reported 2,793 sessions, integrity ok, state continuous, none unclosed.

### R2. Sessions and capture integrity

| Session | Game | Candidate seat | Wall time | Structural stops | Decisions reconstructed offline, memory compared, differences |
|---:|---|---|---:|---|---|
| 2794 | 1930331196 C2, position 1 | red | 117.2 s | none | 2,881, 2,881, 0 |
| 2795 | 2120531121 C3, position 2 | blue | 112.9 s | none | 2,881, 2,881, 0 |

Both games were launched at 2026-10-06T20:59:42+08:00 and completed 2,881 steps in schedule order, one at a time;
nothing was retried or replaced and no third session was opened. Both sessions closed with integrity ok; the ledger
audit found each session after 2793 to be the card's game in its schedule position under the card's digest and the
candidate's registered digest, none unclosed, and the read-only verify afterwards reported 2,795 sessions, integrity ok,
state continuous. The live reconstruction found no difference at any decision, the memory chain included; the offline
replay re-derived every candidate decision and its memory from an empty memory with no difference and no problem.
`CAPTURE_INVALID` does not apply.

### R3. Prefix reproduction

| Configuration | Actions before the divergence equal to frozen v3 | Registered first divergence reproduced | Memory chain equal | Seat observations identical through the divergence |
|---|---|---|---|---|
| 1930331196 C2 | yes (decisions 0 to 420) | yes, decision 421 | yes | 422 of 422 |
| 2120531121 C3 | yes (decisions 0 to 360) | yes, decision 361 | yes | 169 of 362 |

SP passed in both games, live and offline. In 2120531121 C3 the seat's observations equal Sprint 16's only through
decision 168: the seat's helicopter fired at decision 168 in both games and the engine's damage draw differed (2 points
in Sprint 16's game, 1 here), which changes the inert enemy's state and the scores from decision 169 on. Every own action
through decision 361 was nevertheless identical and the registered redirect was reproduced exactly; this is reported, as
registered, and gates nothing.

### R4. 1930331196 C2

* **Decision 421.** As registered: two vehicles that `baseline-v2` sent to 50-point objective C, which v3 would have
  staged, were redirected to 80-point objective A at the same route cost (5.0, 100 free-flow steps); Sprint 14's
  independent checks found no violation.
* **Later redirects.** Four more vehicles were redirected from 50-point objective B to 80-point objective B: one at
  decision 521, one at 522 and two at 541, all with clean independent checks. Six redirects of six units in all; 24
  memory episodes, 6 with a redirect, none with more than one; no oscillation.
* **Protected direct fire.**

| Decision | Listed for the protected unit | Order emitted by it | Response |
|---:|---|---|---|
| 611 | yes | yes | accepted |
| 686 | yes | yes | accepted |

* **Capture order.** The same as v3's in Sprint 16 (50-point A, 50-point C, 80-point A, 50-point B, 80-point B), and
  every first ownership at the same decision except 80-point objective B, first owned at decision 864 instead of 886.
* Record facts: margin 274 and attack 24, as in Sprint 16's v3 game.

**Class `C2_MECHANISM_PRESERVED`**: both protected fire events survive, and the Sprint 10 capture-order and firing
regression did not reappear on this trajectory.

### R5. 2120531121 C3

* **Decision 361.** As registered: two vehicles that `baseline-v2` sent to 80-point objective B, which v3 would have
  staged, were redirected into the problem objective (route cost 8.0 against 7.0, 160 free-flow steps), with clean
  independent checks. Two more vehicles followed the same redirect at decision 381. Four redirects of four units; 18
  memory episodes, 4 with a redirect, none with more than one; no oscillation.
* **First ownership.** The problem objective was first owned at decision 522, 42 decisions before v3's 564; clause A of
  the retirement rule does not hold.
* **Pre-capture audit (decisions 361 to 521).** Units claimed the problem objective at 23 decisions, the first at 463:
  49 claimant-decisions by 8 vehicles, every one able to arrive and none placed, because at each of those decisions the
  objective's four counted places were held by the two decision-361 vehicles and the two decision-381 vehicles. Removing
  only the two early places would have placed a claimant 45 times: **45 EARLY-PLACE BLOCK events**, at all 23 claim
  decisions (38 withheld, 7 staged). v3's two capturers were blocked at each of their 20 claim decisions (each withheld
  19 times and staged once) and were not on the objective at its first ownership; five other vehicles were blocked once
  each. With every candidate redirect place removed (descriptive), 48 claimant-decisions would have been placed.
* **The decision-361 vehicles** stayed counted on the objective for 160 decisions each, both survived, and one of them
  stood on it at its first ownership.
* Record facts: margin 579 and attack 98, as in Sprint 16's v3 game.

**Class `C3_212_MECHANISM_LOST`** (clause B: 45 EARLY-PLACE BLOCK events before first ownership). The candidate is
RETIRED BY 212.

### R6. Disposition

C2 preserved, 212 retired, no structural, fidelity, prefix or reconstruction problem. By the rule of section 9:

**MECHANISM_REFUTED_212.**

It promotes nothing and authorizes no further engine use; the study returns to the owner.

### R7. What Sprint 17 shows

1. **The executable candidate is the shadow.** It reproduced frozen v3 and Sprint 16's corrected-memory chain exactly up
   to both registered divergences and made exactly the registered redirects; every one of the 5,762 decisions was
   re-derived from the seat's own observation and memory without a difference.
2. **1930331196 C2: crossing decision 421 did not touch the firing sequence.** The protected unit fired at 611 and 686
   as in v3's game and the capture order was unchanged; 80-point objective B, the destination of the later redirects,
   was first owned 22 decisions earlier than in v3's game (whether because of them is not measured).
3. **2120531121 C3: the early places recreate capacity reservation.** The two decision-361 vehicles, joined by two more
   at 381, held every counted place of the problem objective from the first claim at 463 to the capture, and every
   later claimant, v3's own two capturers included, was withheld or staged behind them: the mechanism the 212 rule was
   registered to detect. On this trajectory the reserving vehicles did arrive, and the objective was taken 42 decisions
   earlier than by v3; the registered clause counts the displacement itself and does not measure whether it was
   harmful, and nothing here does.

### R8. Recommendation (one)

Retire `delayed-post-stage-any` completely, as the registered refutation requires, add no exception to it, and shelve
the T9 redistribution line. The engine exposed no new generic mechanism: what the 212 clause found is the property it
was written for, an early redirect holding capacity that later claimants would have used, which is what a redirect
made before those claimants arrive does by construction. Since Sprint 12 the line has produced no rule that both restores T9-v1's primary
redistribution and stays clear of the adverse mechanisms. The one next task: an offline re-selection of the next
tactical family from the frontier register (`docs/TACTICAL_FRONTIER.md`), scored with the committed rubric against the
evidence gathered since Sprint 1, with no engine session, for the owner's decision.

### R9. Close-out

* Tests at the results commit `45f8e2928ff3f8eb91afa46289a4cbe9ebd94e23`: the workstation tree ran 1,612 tests (81
  skipped) with exit 0; a clean clone from GitHub at the same commit and tree ran 1,609 (82 skipped) with exit 0; the
  evaluation server's private tree ran 1,625 tests (0 skipped, 5,226 s) with exit 0, regenerating every Sprint 17 public
  file, `inputs.json`, the prefix reference and the mutation record from the private captures, and Sprint 16's public
  files with its ledger read bounded at session 2793, with the ledger file byte-identical before and after.
* Process note: the first close-out run on the server started on the registration commit, because the fast-forward had
  been refused: the analysis had written the three public result files into the server's clone as untracked files
  (byte-identical to the committed ones). That run was stopped, the files removed, the clone fast-forwarded and the suite
  started again; a stop pattern that matched its own shell also ended a second, unfinished run. Only the complete run is
  reported.
* Documentation gates: Sprint 17's private gate (`local/diagnostics/s17/doc_gate.py`) passes, checks that sections 1 to
  14 equal the pushed registration and catches every planted error; the historical gates pass with their plants,
  Sprint 10's on the server with 40 checks and no failure.
* Privacy: the scan over every reachable blob at the results commit (890 blobs) found 104 hit lines, identical as a set
  to the accepted 104.
* Platform canary: rebuilt byte for byte on the workstation and the server.
* Engine ledger: read-only verify after the suite, 2,795 sessions opened and closed, none unclosed, integrity ok, state
  chain continuous; the Sprint 17 ledger audit of the whole live ledger passes (sessions 2794 and 2795, the card's two
  games in order, no later session). The server's development worktree was removed; the evidence stays under the
  ignored `local/` tree.
