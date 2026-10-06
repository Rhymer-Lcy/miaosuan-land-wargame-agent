# Sprint 16: registered on-policy v3 mechanism capture

**REGISTERED — EXPLORATORY TRACK — MECHANISM CAPTURE, NOT A SCORE SCREEN — THREE ENGINE SESSIONS — NOTHING PROMOTED**

On 2026-10-06 the owner authorized a very small registered engine mechanism capture: three exclusive sessions of the
frozen `t9-batch-capacity-v3`, unchanged, against the inert control, one game in each of the three adverse
configurations, serially. The purpose is to collect the on-policy v3 trajectories that no existing capture contains,
so that delayed, post-staging redistribution can be evaluated as an offline shadow on its own trajectory. It is not a
score screen, not a candidate evaluation and not a confirmation; no rule here can promote anything, and no delayed
rule influences an engine action. Dates are business dates in UTC+8.

Sections 1 to 13 are the registration. They are committed and pushed, with every frozen file, the card, the frozen
inputs, the tests and the mutation record, before session 2791 is opened, and are not edited afterwards; results follow
in a separate section.

## 1. Starting state and fixed results

| Item | Identity |
|---|---|
| Repository | `main` `40dca6da9f3988ee1de4c078506fca903beeaff4`, tree `f117d5a556ef8a2b5f487d6403fac8546e2b4974`, identical on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,790 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `e2116700df7645f7c116386bfb4b955cb2725f1541ba24f906fafe9172891cef`; session 2791 never opened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| T9-v3 (the only engine policy of this sprint) | `t9-batch-capacity-v3`, policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8` |
| Privacy baseline | the 104 hit lines accepted at Sprint 14's close and reproduced at Sprint 15's, compared as a set of lines |

Fixed and not reinterpreted: Sprint 12 `NOT_PRESERVED_IN_PRIMARY`, Sprint 13 `REDISTRIBUTION_DOMINANT`, Sprint 14
`NO_ENGINE_CANDIDATE`, Sprint 15 `NO_RESTORING_TRIGGER`. Sprint 15's disposition stands although its post-hoc analysis
exposed a memory-reset defect and two restoration measures (R3, R4) unsuited to rules with bounded recourse on
recorded states; those findings motivate this sprint and rewrite nothing.

## 2. Scope and the nature of the evidence

* Exactly three sessions are authorized, subject only to the structural stops of section 3: no retry, no replacement,
  no extra replication, no fourth session. A session that is opened and fails counts.
* One game per configuration is a mechanism capture, not a population estimate. It shows the exact v3 trajectory
  observed in that configuration and gives an on-policy state stream on which a delayed rule is valid until its first
  action divergence. Findings are stated as "on the observed v3 trajectory"; no finding says that a configuration can
  never trigger a rule, and no statistical or score claim is made.
* No delayed rule is executable. The delayed rules exist only as analysis-side shadows (section 5), computed after the
  three games on the recorded observations.

## 3. The card, the runner and the stops

The card is `evaluation/s16-v3-mechanism-capture-1/manifest.json` (exploratory run-card schema, built and checked by
`scripts/build_s16_card.py`; frozen rules in `src/miaosuan_agent/evaluation/s16_mechanism.py`). It binds exactly the
frozen v3 identity (policy source above, source files including `experiments/t9_batch.py`) and `baseline-v2`'s, and
pins the normalised SHA-256 of 29 frozen implementation files (`s16_mechanism.FROZEN_FILES`: the Sprint 16 modules,
scripts and tests, the reused Sprint 12 observers and per-game checks, the frozen policy and analysis modules they rely
on, the registered evaluator, and both copies of the v3 whitelist test). The shadow identity is recorded in the card
for reference only, marked not executable.

| Position | Game id | Scenario | Condition | Red | Blue | Expected session |
|---:|---|---|---|---|---|---:|
| 1 | `1930331196.C3.s16-v3-mechanism-capture-1.p01` | 1930331196 | C3 | inert control | v3 | 2791 |
| 2 | `1930331196.C2.s16-v3-mechanism-capture-1.p02` | 1930331196 | C2 | v3 | inert control | 2792 |
| 3 | `2120531121.C3.s16-v3-mechanism-capture-1.p03` | 2120531121 | C3 | inert control | v3 | 2793 |

The seats are Sprint 10's (and the unrun Sprint 12 A1 stage's): C2 is the candidate as red against the inert blue
control, C3 the inert red control against the candidate as blue. Budget: ledger base session 2790, ceiling 3,
exclusive diagnostic sessions, one game at a time, runtime `baseline-v1-runtime-r2`.

`scripts/run_s16_capture.py` refuses to start unless the tree is clean and committed, the card rebuilds byte for byte,
every pin equals the checkout and the ledger audit passes; it then plays the games in card order through
`scripts/run_s16_game.py` in the registered evaluator's isolation (the same isolated environment as Sprint 12, a hard
timeout). The game entry point refuses, before the engine is touched, a card that does not rebuild, a changed pin, a
dirty tree, an existing record or capture, a session beyond the ceiling, a wrong thread environment or a mismatched
input. After every game, before the next one starts, the structural stops are evaluated:

| Stop | Meaning (the frozen Sprint 12 checks, `s12_timeline.analyze`, and the Sprint 16 ledger audit) |
|---|---|
| S1 | engine-installation integrity failure (session close or the ledger's state chain) |
| S2 | ledger inconsistency: a session after 2790 that is not the card's game in schedule position, under the card's digest, opened once and closed; an unclosed session; more than three sessions |
| S3 | privacy exposure |
| S4 | a contract error or a game that did not complete |
| S6 | a replay mismatch (an engine action differing from the policy that played) |
| S7 | an observer error, a missing or digest-mismatched capture, a seat-local reconstruction that differs from the live decision (a v3 add-on error included, because the frozen consistency check requires none), a disagreement between capture and record, or a `max_step` other than 2,880 |

Any structural stop, or a non-zero game status, ends the study at once; nothing is retried. S5 and S8 to S14 describe
v3's own behaviour and are reported, never a stop: there is no tactical early stop, and no shadow is evaluated between
games, so the next game never depends on a shadow finding.

**Whitelist amendment.** Sprint 12's owner-approved safeguard (`tests/test_t9_batch.py`, and its copy in
`tests/test_s12_proposal_draft.py`) permitted the v3 identity only in the four Sprint 12 stage cards. It now permits
exactly one further card id, `s16-v3-mechanism-capture-1`, bound to the same frozen digest and source files, as the
owner's 2026-10-06 read-only mechanism capture of the same identity. No wildcard, folder family or generic builder is
whitelisted, no historical card becomes executable, a changed v3 digest still fails, and non-card files may still name
v3 only under the three historical folder prefixes (the Sprint 16 analysis refuses to write the identity into its own
public files).

## 4. Capture

Every game runs the proven Sprint 12 observer stack unchanged (`evaluation/s12_capture.py`): Sprint 9's `T9Capture`,
the compact v3 capture (the v3 trace: changes, staging, hold episodes, errors) and the full-step private timeline. The
timeline keeps, for every decision, the all-seeing state and every seat's observation (action listings, own and seen
units, move paths, movement state, objective ownership) and memory, the submitted actions and the engine's responses,
the final post-step state, and, for the v3 seat, the reconstructed `baseline-v2` decision and the complete
reconstructed v3 allocation (incumbents, counted movers, ranked claimants, selections, staging paths, withheld units).
Every decision of the v3 seat is re-decided from that seat's own observation and memory and compared with the live
decision during the game (a difference is S7); the analysis repeats the reconstruction offline from the files and
requires the same (any difference makes the disposition `CAPTURE_INVALID`). The record and five capture files per game
are written exclusively under the ignored `local/evaluation/s16-v3-mechanism-capture-1/` and digested in the record;
nothing is overwritten or deleted. No unit id, coordinate, route or observation enters public Git.

## 5. The shadow identity `s16-delayed-shadow-v6`

`src/miaosuan_agent/evaluation/s16_shadow.py` restates Sprint 15's six delayed rules as analysis-side shadows under one
correction of their memory, the one disclosed in Sprint 15 (results, R7) and implemented post hoc in
`scripts/s15_posthoc.py`, which is its source of truth:

* frozen v5 (`t9-<rule>-v5`, unchanged): a unit observed standing on any objective loses its record;
* v6: a unit observed standing on an objective loses its record only when its side does not hold that objective. A unit
  standing on an objective its side holds is a deferred claimant (`baseline-v2` never orders a unit standing on an
  objective its side does not hold), and its deferred overflow history is kept.

Every other memory transition, every trigger, the allocation (Sprint 14's `feasible-value-redirect` restricted to
eligible overflow claimants, on v3's stage 1) and the fail-closed path are the frozen v5 code, called unchanged. With
nobody eligible the shadow equals v3 exactly; with an empty memory nobody is eligible, so no shadow can differ from v3
at the first decision of a game. A test shows that the correction produces the same records as the post-hoc function on
every synthetic scene. The module defines no policy, agent or add-on class, is imported by no engine path, and its
source digest (`source_sha256` in the card and in `inputs.json`) is fixed before session 2791.

| Shadow | Identity | Trigger for an overflow claimant |
|---|---|---|
| `delayed-repeat-2` | `s16-delayed-repeat-2-shadow-v6` | at least the 2nd overflow observation of the episode |
| `delayed-repeat-3` | `s16-delayed-repeat-3-shadow-v6` | at least the 3rd |
| `delayed-stable-alternative` | `s16-delayed-stable-alternative-shadow-v6` | the same best admissible alternative as at the previous overflow observation of the episode |
| `delayed-post-stage-same` | `s16-delayed-post-stage-same-shadow-v6` | completed a staging move v3 emitted toward this same source |
| `delayed-post-stage-any` | `s16-delayed-post-stage-any-shadow-v6` | completed a staging move v3 emitted (any source) |
| `delayed-saturated-source` | `s16-delayed-saturated-source-shadow-v6` | the source is saturated now and was at the previous overflow observation |

The scientific target is `delayed-post-stage-any`, the only Sprint 15 trigger that materially restored post-opening
redistribution on the primary states; the other five are comparison shadows. Sprint 15's `posthoc-bounded-o2` is not
retained: it is not a delayed rule, and its role as a reference for R3 is taken by the reference units of section 10.

## 6. Evidence boundary: the first shadow divergence

A shadow and frozen v3 produce the same world only until the first decision at which the shadow's emitted actions
differ from v3's (content or order), its **first shadow divergence**. For each shadow and game:

* every state strictly before the first divergence is on-policy for the shadow: its memory there is exactly the memory
  it would have had in the engine;
* the state at the first divergence is valid for judging the proposed first action;
* every later recorded state is a v3 state and is **OFF-POLICY** for the shadow. Later shadow actions are computed only
  as off-policy replay, labelled so in every output, and never used as evidence of what the shadow would have done.

The registered classification rests on the first divergence only.

## 7. The first-divergence certificate

For every shadow in every new game, privately: whether it diverges at all; the decision, step and ordinal (among
decisions with an own ground move) of the first divergence; every unit whose emitted action differs, with its kind and
its v3 and shadow forms; and for every redirect at that decision: unit kind, source objective, alternative objective,
trigger, episode count and age in steps, whether a staging move had completed, the previous staging source, the current
`baseline-v2` destination, the v3 action (stage or withhold, staged length) and the shadow's action, route cost, own
cost and detour ratio, independent free-flow time, arrival slack, counted places at the source and at the destination
before the redirect, whether the unit has a direct-fire action listed at that decision, how many enemy units the seat
sees and the nearest one's distance, its firing-role membership (section 8.1), whether the decision is inside the risk
window, and the reservation facts of section 8.2. Public outputs carry objectives by Sprint 11's labels and units by
kind only.

## 8. Risk windows and per-configuration classification

### 8.1 1930331196 C3 and C2: firing

* **Historical anchors**: the units of the direct-fire orders of Sprint 10's frozen `baseline-v2` captures at their
  firing decisions (C3: 742, 804, 841 and 876, 8 units; C2: 611, 1 unit). Unit ids, kinds and start hexes are identical
  across separate games of one configuration (checked on all three configurations' Sprint 10 capture pairs); the
  analysis requires each historical shooter to be the same unit at decision 0 of the new game (otherwise a fidelity
  problem).
* **Observed fire in the new game**: every decision at which an own ground unit of the v3 seat has a direct-fire action
  listed, or at which the seat orders direct fire, with the engine's responses.
* **Risk window**: from the first decision to the latest of the historical anchors and the observed fire decisions.
* **Firing role** of a unit changed at the first divergence (decision k): a historical shooter whose firing decision is
  not before k, or a unit with a direct-fire listing or order at some decision from k to the end of the window (a
  listing at k itself is a fire opportunity the unit carries now).

| Class | Rule (first match) |
|---|---|
| `C3_PREFIX_SAFE` / `C2_PREFIX_SAFE` | no divergence in the whole game (sublabel `NO_TRIGGER_OBSERVED`), or the first divergence after the risk window |
| `C3_FIRST_DIVERGENCE_UNSAFE` / `C2_FIRST_DIVERGENCE_UNSAFE` | the first divergence is inside the window and either changes a unit with a firing role or comes at the opening (the first decision with an own ground move: Sprint 14's harmful opening-redirect topology) |
| `C3_PREFIX_AMBIGUOUS` / `C2_PREFIX_AMBIGUOUS` | the first divergence is inside the window on units with no firing role: the world diverges before the window ends, so later shooter behaviour is not observable on-policy |

Sprint 10 tied C3's loss to the shooters themselves being on other corridors, which the firing-role clause captures. It
tied C2's loss to earlier redirects of other units changing the capture order, so that `baseline-v2` later routed the
shooter differently: that indirect path can only show after the divergence, so an early divergence on another unit is
ambiguous, never safe. Whether the opening-redirect topology is absent is reported for every shadow.

### 8.2 2120531121 C3: objective capacity

* **Problem objective**: the 80-point objective T9-v1 never owned in Sprint 10's capture (Sprint 11's objective A),
  first owned by `baseline-v2` at decision 564 in the other capture (a reported anchor).
* **Risk window**: from the first decision to v3's first ownership of the problem objective in the new game, or to the
  last decision if v3 never owns it.
* **Certificate clauses** for each redirect at the first divergence: (a) a v3 selection of that decision not kept;
  (b) dominated: a claimant of the same destination at that decision that can arrive before the end, with a strictly
  shorter free-flow time, given no place there; (c) the unit cannot arrive before the end; (d) the redirect goes to the
  problem objective, fills its last free place (three counted places before it, stage-1 selections and earlier
  redirects of that decision included), comes before v3's first ownership, and at least one unit standing on the
  objective at v3's first ownership held no place there at the divergence (the v3 trajectory identifies which places
  its capture used; this is never read as the shadow's own future).

| Class | Rule (first match) |
|---|---|
| `C3_212_PREFIX_SAFE` | no divergence (sublabel `NO_TRIGGER_OBSERVED`), or the first divergence after the risk window |
| `C3_212_FIRST_DIVERGENCE_BAD_RESERVATION` | the first divergence is inside the window and meets a clause, or comes at the opening |
| `C3_212_PREFIX_AMBIGUOUS` | the first divergence is inside the window and meets no clause |

Because v3's selections are allocated first, a valid shadow should never meet clauses (a) or (b); they are certificate
checks of the shadow, not expected outcomes. Sprint 14's far-reservation count is not copied: it counted fast vehicles
sent into an objective whose places were held only by movers that could not arrive, which is the repair, not the
failure. No capture success is inferred from a first-divergence action.

## 9. Disposition (first match)

| Disposition | Rule |
|---|---|
| `CAPTURE_INVALID` | a capture, reconstruction, integrity, ledger or fidelity requirement failed, or a configuration has no valid game |
| `MECHANISM_REFUTED` | the target's first divergence is `UNSAFE` or `BAD_RESERVATION` in at least one configuration |
| `MECHANISM_AMBIGUOUS` | in at least one configuration the target's first divergence is `PREFIX_AMBIGUOUS` |
| `MECHANISM_PREFIX_SUPPORTED` | in all three configurations the target's class is `PREFIX_SAFE` |

`MECHANISM_PREFIX_SUPPORTED` means only that the known adverse mechanism is absent on the three observed on-policy
prefixes; it does not mean that a complete candidate is safe. `NO_TRIGGER_OBSERVED` is a per-configuration sublabel:
a shadow that never diverges during a whole v3 game would have played exactly v3 on that trajectory, which is real
mechanism evidence. The other five shadows are classified the same way and reported descriptively. No disposition
authorizes a score screen; after the analysis the study returns to the owner.

## 10. R3 and R4 replacements (on the historical primary corpus and, off-policy, the new captures)

**R3, distinct-unit restoration** (the four Sprint 12 primary games). Reference units: the distinct units T9-v1
redirects after the opening (decisions after the first with an own ground move), per seat: 15 as red (H1) and 26 as
blue (H2), as Sprint 15 published (reproduction required). A reference unit is restored when the shadow issues at least
one qualifying redirect of it in the same game: a redirect emitted after the opening at a decision whose independent
checks (Sprint 14's `candidate_checks`) find no violation. Repeated redirects of one unit count once. Requirement: at
least 8 restored units as red and 13 as blue (the ceiling of half the reference, Sprint 15's intended "at least half").

**R4, bounded recourse per episode.** An independent tracker, which never reads a shadow's memory, builds episodes from
the observation and v3's stage-1 allocation alone: an episode of a unit is a run of overflow observations at one
source, ended by the unit's absence, a path ending on an objective, standing on an objective its side does not hold,
its source held by its side, a place given, a claim it cannot complete before the end, or overflow at another source
(which starts a new episode). Every shadow redirect is charged to the unit's open episode. R4 holds when no episode has
more than one redirect or more than one destination and no redirect falls outside an episode. Within one episode the
source is fixed, so an oscillation there (A to B, later B to A) needs two redirects in that episode and is excluded by
the same item. Reported, not gated: redirects per unit over a whole game (a unit may enter several episodes) and
oscillations across episodes. Sprint 15's R3 and R4 are not reused.

R3 and R4 are reported with their frozen values; they do not enter the Sprint 16 disposition, which concerns the
adverse mechanism only.

## 11. Validation before session 2791

* **Tests** (`tests/test_s16_shadow.py`, `tests/test_s16_mechanism.py`): the corrected memory and its equality with the
  post-hoc correction, a held objective that keeps the deferred history, an unheld one that still ends it, every other
  transition, stage completion, the target trigger and its absence before a completed staging move, one redirect per
  episode and the reset on a new source, the tracker on every ending event and against a shadow whose per-episode flag
  is removed, the first-divergence comparison, every classification at its window boundary, firing roles at and around
  the firing decision, each reservation clause alone and the fourth clause member by member, the disposition order,
  restoration at both thresholds without double counting, the card, schedule, budget and pins, every ledger defect,
  the structural-stop mapping, the certificate on synthetic first divergences, and the public sanitization.
* **Mutation** (`scripts/mutate_s16.py`, `evaluation/s16-mechanism-capture/mutation.json`): 54 planted defects in the
  shadow, the frozen rules and the analysis driver (the corrected reset, every other memory transition, the
  first-divergence comparison, both window boundaries, firing-role membership, the no-trigger reading, the opening
  topology, each reservation clause, the disposition order, restoration and recourse, the v3 digest, the session and
  card mapping, the ledger audit, the structural stops, the public guard); the card is rebuilt inside the copy after
  each defect, so that the pin alone cannot catch it. All 54 were caught; for one (a changed v3 digest) the card cannot
  be built at all, and a test catches it as well. The first run caught 53 of 54: the ledger's ceiling finding was
  never isolated by a test (a fourth session also breaks the schedule position), and an exact assertion was added.
* **Rehearsal on real captures** (`scripts/s16_analysis.py rehearse`, private): run at the registration code on the
  four Sprint 12 primary captures, the only v3 captures that exist and in exactly the format of the new ones, both as
  stand-ins for the new games and as the primary corpus. `baseline-v2`, v3 and v3's captured allocation were
  reconstructed at 11,524 of 11,524 decisions with no difference (Sprint 13 reported the same count), the shadow with
  nobody eligible equalled v3 at every decision, and the target's first divergence fell at decisions 460, 181, 581 and
  181 (581 in the third game is Sprint 15's documented on-policy prefix). The restoration measure was therefore computed
  before registration: T9-v1's reference units were reproduced (15 and 26), and the restored units per shadow equal
  Sprint 15's post-hoc post-opening counts exactly (`delayed-post-stage-any` 9 and 21, `delayed-repeat-2` 3 and 16,
  `delayed-repeat-3` and `delayed-stable-alternative` 2 and 16, `delayed-post-stage-same` 2 and 8,
  `delayed-saturated-source` 0 and 0). Those counts were public in Sprint 15's post-hoc record before the owner set the
  thresholds of section 10, and no definition changed after the rehearsal. R4 held for every shadow: at most one
  redirect in each of the 170 episodes, a count the same for every shadow because the tracker never reads a shadow's
  memory.
* **Stand-in rehearsal of the runner** (private, `local/diagnostics/s16/standin_rehearsal.py`): run on the committed
  registration code on the server, with stand-in engines and a session context that records nothing (the ledger file
  byte-identical before and after). With the real staged inputs the first game completed on a 40-step stand-in, wrote
  its record and five captures with matching digests and raised S7 (`max_step` 40 is not the registered 2,880), and the
  runner stopped with exactly one game recorded. On the Sprint 12 stand-in scenario all three games completed with no
  structural stop; the analysis replayed each with 2,881 of 2,881 reconstructions equal, found that the stand-in's
  units are not the historical shooters (8 and 1) and therefore decided `CAPTURE_INVALID`, and wrote four public files
  that pass the privacy checks. An unknown game, an existing record and a dirty tree were refused. It found one defect
  before registration: a public block named with a forbidden key (`memory`), renamed.
* **Registration checks**: the registration pushed and fetched back byte for byte; the server fast-forwarded; the
  workstation, GitHub and server at the same commit and tree; the v3 digest verified; the full non-engine suites run;
  the privacy scan compared as a set; the canary rebuilt; a read-only engine verify; the ledger still at 2,790 with
  none unclosed. Their results are reported in the results section.

## 12. Outputs and privacy

* Public (`evaluation/s16-mechanism-capture/`): `inputs.json` (before session 2791: the historical inputs by digest,
  the card's canonical digest, the shadow identity, the rules and the derived anchors as counts and decisions),
  `mutation.json`, and after the games `games.json` (sessions, capture validity, reconstruction counts, v3 mechanism
  facts, observed fire, staging followed by overflow on the v3 trajectory, risk windows), `shadows.json` (per
  configuration and shadow: classification, sanitized first-divergence certificate, trigger exposure, labelled
  off-policy replay, memory checks and recourse), `restoration.json` (R3 and R4) and `disposition.json`; all four
  regenerate byte for byte (`scripts/s16_analysis.py run --check`). Every public file passes the forbidden-key and
  private-value checks and may not contain the v3 identity or digest.
* Private (ignored `local/`): records, captures, `local/diagnostics/s16/analysis-private.json.gz` (unit ids,
  certificates, episodes), the rehearsals.

## 13. Not claimed

No score, effect or population property. One game per configuration shows one trajectory. A shadow's off-policy
replay after its first divergence is not what it would have done. `MECHANISM_PREFIX_SUPPORTED` would not make a
delayed candidate safe or ready for any screen.

## Results (2026-10-06)

Every figure below comes from the committed public files of `evaluation/s16-mechanism-capture/`, which
`scripts/s16_analysis.py run --check` regenerates byte for byte from the private records and captures, or from the run
logs kept privately. Shadow figures after a first divergence are off-policy and labelled so; scores are record facts
that enter no rule.

### R1. Registration and pre-engine checks

Sections 1 to 13, every frozen file, the card, the inputs, the tests and the mutation record were pushed as commit
`6d9a88b6e51e3a5fb09a130d722fa241895f4a5d` (tree `b9cae184ecacc25befcc3b02712e0c7586c40465`) at
2026-10-06T15:02:31+08:00, after an audit of its 12 commits; a fresh unauthenticated clone from GitHub had the same
commit and tree and all 16 changed files byte for byte. The evaluation server was fast-forwarded to the same commit by
bundle. Before session 2791: the card and `inputs.json` regenerated byte for byte on the server, the v3 source hashed
to the frozen digest, the workstation tree ran 1,556 tests (78 skipped) with exit 0, a clean clone from GitHub 1,553
(79 skipped) with exit 0, and the server's private tree 1,569 (1 skipped: the regeneration of the result files, which
did not exist yet; 5,054 s) with exit 0 and the ledger file byte-identical before and after; the privacy scan over
every reachable blob (860 blobs) found 104 hit lines, identical as a set to the accepted 104; the platform canary
rebuilt byte for byte on both hosts; a read-only verify reported 2,790 sessions, integrity ok, state continuous, none
unclosed.

### R2. Sessions and capture integrity

| Session | Game | v3 seat | Wall time | Structural stops | Reported v3 findings | Decisions reconstructed (live, offline) |
|---:|---|---|---:|---|---|---|
| 2791 | 1930331196 C3, position 1 | blue | 113.2 s | none | none | 2,881, 2,881 |
| 2792 | 1930331196 C2, position 2 | red | 116.0 s | none | none | 2,881, 2,881 |
| 2793 | 2120531121 C3, position 3 | blue | 112.4 s | none | none | 2,881, 2,881 |

All three games completed 2,881 steps, in schedule order, one at a time; nothing was retried or replaced and no fourth
session was opened. Every session closed with integrity ok and the engine state unchanged; the ledger audit found each
session after 2790 to be the card's game in its schedule position under the card's digest, none unclosed, and the
read-only verify afterwards reported 2,793 sessions, integrity ok, state continuous. The live reconstruction found no
difference at any decision, and the offline replay re-derived `baseline-v2`, v3 and the captured v3 allocation at all
8,643 decisions without a difference; the shadow with nobody eligible equalled v3 throughout, every historical shooter
was the same unit at decision 0, and the structural checks (cross-objective moves, invented moves, staging prefixes,
unrelated actions) found nothing. `CAPTURE_INVALID` does not apply.

### R3. What v3 did on the three trajectories (descriptive)

| | 1930331196 C3 | 1930331196 C2 | 2120531121 C3 |
|---|---|---|---|
| staged moves / withheld order-decisions | 26 / 16,691 | 24 / 121 | 22 / 303 |
| longest hold (decisions) | 1,585 | 25 | 43 |
| direct-fire listings of own ground units | 3 decisions, 742 to 802 | none | 18 decisions, 321 to 841 |
| direct-fire orders (all accepted) | 8 | 2 (decisions 611 and 686) | 21 |
| overflow after a completed staging move: all / at another source / with an admissible alternative | 15,119 / 2,697 / 0 | 132 / 13 / 6 | 313 / 10 / 4 |
| first such overflow with an alternative | none | decision 421 | decision 361 |
| objectives own at the end | 5 | 5 | 5 |

The last row of the overflow facts is the target trigger's opportunity on v3's own trajectory, before any shadow
acts. In 2120531121 C3 v3 first owned the problem objective (80-point objective A) at decision 564, which fixes that
configuration's risk window. The record facts, which enter no rule, are margins 570, 274 and 579 and attack 88, 24 and
98; on each observed trajectory they equal those of Sprint 10's `baseline-v2` diagnostic game in the same
configuration. This is one game per configuration and is not evidence of an effect.

### R4. The target's first divergence

| Configuration | First divergence | Risk window ends | Units changed | Class |
|---|---|---:|---|---|
| 1930331196 C3 | none | 876 | none | `C3_PREFIX_SAFE`, `NO_TRIGGER_OBSERVED` |
| 1930331196 C2 | decision 421 (step 420), the 5th with an own ground move | 686 | 2 vehicles, staged by v3, redirected by the shadow | `C2_PREFIX_AMBIGUOUS` |
| 2120531121 C3 | decision 361 (step 360), the 3rd with an own ground move | 564 | 2 vehicles, staged by v3, redirected by the shadow | `C3_212_PREFIX_AMBIGUOUS` |

* **1930331196 C3.** The target's trigger held 15,119 times on the v3 trajectory, 392 of them inside the risk window,
  all on-policy, but at no decision did an admissible alternative exist, so the target never acted: on this trajectory
  it is exactly v3 for the whole game, and no shooter or other unit is changed. The new game's direct-fire listings and
  orders all fall inside the window, which therefore ends at the historical anchor 876.
* **1930331196 C2.** Both vehicles had completed a staging move toward 50-point objective A and were then sent by
  `baseline-v2` to 50-point objective C, which already had four counted places. The target sends both to 80-point
  objective A at the same route cost (detour ratio 1.0, 100 free-flow steps, arrival slack 2,360), with no direct-fire
  action listed, no enemy seen and no firing role. Neither is the shooter of the new game's orders at 611 and 686 or
  the historical shooter. The divergence is 190 decisions before the shot at 611 and inside the window: the redirect
  could change the capture order (in the v3 game 50-point objective C was first own at step 442 and 80-point objective
  A at step 503), which is the indirect path Sprint 10 diagnosed, and nothing after the divergence is observable on
  this trajectory. Ambiguous, not unsafe.
* **2120531121 C3.** Both vehicles had completed a staging move toward 50-point objective C and were then sent to
  80-point objective B, which had four counted places. The target sends both into the problem objective (detour ratio
  1.1429, 160 free-flow steps, arrival slack 2,360), with no place counted there before the first and one before the
  second. No clause holds: v3's selections are kept, no claimant of that objective exists at the decision (not
  dominated), both can arrive, and neither fills the last place. The divergence is 203 decisions before v3's own
  capture, for which v3 used at least one unit that held no place there at decision 361; whether two early places would help or
  block that capture is a question about the world after the divergence. Ambiguous.

No shadow diverged at the opening decision in any configuration, so Sprint 14's harmful opening-redirect topology is
absent for all six.

### R5. Comparison shadows (first divergence, class)

| Shadow | 1930331196 C3 | 1930331196 C2 | 2120531121 C3 |
|---|---|---|---|
| `delayed-repeat-2` | none, safe | 783, safe (after the window) | 441, ambiguous |
| `delayed-repeat-3` | none, safe | 784, safe (after the window) | 442, ambiguous |
| `delayed-stable-alternative` | none, safe | 783, safe (after the window) | 441, ambiguous |
| `delayed-post-stage-same` | none, safe | 783, safe (after the window) | 441, ambiguous |
| `delayed-saturated-source` | none, safe | none, safe | none, safe |

In 2120531121 C3 the first divergence of each of the four comparison shadows that diverge there (all but
`delayed-saturated-source`) also redirects three withheld vehicles into the problem objective, with no bad-reservation
clause. In both 1930331196 configurations no first divergence of any shadow
changed a unit with a firing role.

### R6. Restoration (R3) and recourse (R4)

| Shadow | Restored reference units, red (8 required) / blue (13 required) | R3 | R4 |
|---|---|---|---|
| `delayed-repeat-2` | 3 / 16 | fail | pass |
| `delayed-repeat-3` | 2 / 16 | fail | pass |
| `delayed-stable-alternative` | 2 / 16 | fail | pass |
| `delayed-post-stage-same` | 2 / 8 | fail | pass |
| `delayed-post-stage-any` | 9 / 21 | pass | pass |
| `delayed-saturated-source` | 0 / 0 | fail | pass |

The reference units were reproduced (15 and 26), and the values equal the registration rehearsal's (section 11). R4:
no episode had more than one redirect, more than one destination or a redirect outside an episode, over the 170
episodes of the primary corpus and the 70 of the new captures (off-policy); across episodes, the target redirected one
unit at most 6 times in a primary game and at most twice in a new one, with no oscillation. After its first divergence
the target's off-policy replay redirects 5 units at 3 decisions in C2 and 4 units at 3 decisions in 2120531121 C3. R3
and R4 do not enter the disposition.

### R7. Disposition

The target is `C3_PREFIX_SAFE` in 1930331196 C3 and `PREFIX_AMBIGUOUS` in 1930331196 C2 and 2120531121 C3; no
fidelity problem and no unsafe or bad-reservation first divergence. By the rule of section 9:

**MECHANISM_AMBIGUOUS.**

It authorizes no engine use and no screen; the study returns to the owner.

### R8. What Sprint 16 shows

1. **The trigger is exercised on-policy.** Sprint 15 left every adverse configuration untested, because no capture
   contained a completed staging move. On v3's own trajectories the target's trigger holds on the on-policy prefix
   inside the risk window in all three configurations (392, 2 and 2 overflow observations), so the evidence is no longer
   vacuous.
2. **1930331196 C3: the known firing mechanism does not arise on the observed trajectory.** The target never acts
   there, because no admissible alternative ever exists; the delayed rule and v3 are the same policy on that game.
3. **1930331196 C2 and 2120531121 C3: the first redirect has one shape.** Vehicles that completed a staging move and
   were then re-targeted to a full objective are sent, early in the game, to an 80-point objective the side does not
   yet hold and where few places are counted. That is neither the shooter mechanism nor a bad reservation, but in both
   configurations it comes before the event the window protects (the shot at 611, the capture at 564), so its
   consequences cannot be read from the v3 trajectory.
4. **Restoration and recourse.** With the corrected memory the target restores 9 of the 15 red and 21 of the 26 blue
   reference units and never redirects twice in an episode; the other five restore at most 3 red units.

### R9. Recommended next task (one)

Design, offline and before any engine use, the smallest registered probe that crosses the two observed first
divergences, for the owner's decision. It would play an executable identity of the target: a new owner-approved engine
identity whose actions equal frozen v3's until the corrected `delayed-post-stage-any` trigger meets an admissible
alternative. It would play once each in 1930331196 C2 and 2120531121 C3 against the inert control, under the Sprint 12
full-step capture. Its registered endpoints would be mechanism facts only, read against this sprint's v3 games:

* the prefix reproduces exactly up to decisions 421 and 361 (its own determinism check);
* which units the first redirect moves and where they go;
* in C2, the capture order, and whether the direct-fire orders of decisions 611 and 686 are still listed and accepted;
* in 2120531121 C3, when the problem objective is first owned, and whether any claimant of it is staged or withheld
  behind the two early places.

1930331196 C3 needs no session, because the target equals v3 on the observed trajectory, unless the design finds
that game not deterministic before decision 876. There would be no score comparison, no replication and no third
configuration, and the design must state beforehand which result would retire the rule.

### R10. Close-out

* Tests at the results commit `bb50c6403f75ef133ce7334b1432e2af0b56327f`: the workstation tree ran 1,556 tests (78
  skipped) with exit 0; a clean clone from GitHub at the same commit and tree ran 1,553 (79 skipped) with exit 0; the
  evaluation server's private tree ran 1,569 tests (0 skipped, 5,154 s) with exit 0, regenerating every Sprint 16 public
  file, `inputs.json` and the mutation record from the private captures, with the ledger file byte-identical before and
  after.
* Documentation gates: Sprint 16's private gate (`local/diagnostics/s16/doc_gate.py`) passes, checks that sections 1 to
  13 equal the pushed registration and catches 16 of 16 planted errors; the historical gates pass with their plants.
* Privacy: the scan over every reachable blob (867 blobs) found 104 hit lines, identical as a set to the accepted 104.
* Platform canary: rebuilt byte for byte on the workstation and the server.
* Engine ledger: read-only verify after the suite, 2,793 sessions opened and closed, none unclosed, integrity ok, state
  chain continuous; the Sprint 16 ledger audit passes (sessions 2791 to 2793, the card's three games in order).
