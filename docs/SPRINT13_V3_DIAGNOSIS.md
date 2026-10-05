# Sprint 13: offline diagnosis of the T9-v3 primary-scenario failure

**OFFLINE DIAGNOSIS — NO ENGINE SESSION — PROTOCOL FIXED BEFORE ANY DIAGNOSTIC RESULT**

Sprint 13 explains, from evidence that already exists, why `t9-batch-capacity-v3` did not show in 2130511121 the
head-to-head behaviour that T9-v1 had shown. It opens no engine session: the engine ledger stays closed through session
2790 and session 2791 is not opened. It registers no candidate, implements no new policy and changes no frozen identity,
result or disposition. Dates are business dates in UTC+8; the protocol was written on 2026-10-05.

Sections 1 to 12 are the protocol. They were committed and pushed before any figure of sections 3 to 9 was computed,
and they are not edited afterwards; the results follow in a separate section.

## 1. Starting state and fixed results

| Item | Identity |
|---|---|
| Repository | `main` `c2eb54c4f0292bee6fbefee814bda977382e93ea`, tree `b70fbfa0d9a371879bb2270279847884bb884c88`, identical on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,790 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only `verify`); the ledger file's SHA-256 at the start is `e2116700df7645f7c116386bfb4b955cb2725f1541ba24f906fafe9172891cef` |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| T9-v1 (`t9-capacity-allocation-v1`) | policy source `0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa` |
| T9-v2 (`t9-capacity-staging-v2`) | policy source `66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece` |
| T9-v3 (`t9-batch-capacity-v3`) | policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8` |

Fixed and not re-litigated: Sprint 12 played P1 only (sessions 2787 to 2790; 2130511121 H1, H2, H1, H2 with v3 as red,
blue, red, blue; margins -609, 481, -1,037 and 585; red coverage 0.5691 and 0.2885); all four games were classified
T9-v2-like, none a collapse, no stop S1 to S14 fired, and the frozen interim rule stopped the screen. The frozen
disposition is NOT_PRESERVED_IN_PRIMARY (`evaluation/s12-v3-screen/disposition.json`). Sprint 9's registered result
(+305.47 seat-averaged in 2130511121, interval 172.87 to 611.24) belongs to T9-v1 alone and is neither re-estimated nor
attributed to v3.

## 2. Evidence and what it can show

* **Sprint 12 states.** The four games' private records and five capture files each (`.t9.json`, `.v3.json`,
  `.v3series.json.gz`, `.timeline.json`, `.timeline.pkl`) under the ignored `local/evaluation/s12-v3-primary-1/` on the
  server. The timeline holds, for every decision, the all-seeing state and each seat's observation and memory, the
  final post-step state, and v3's complete allocation. Every input file is pinned by SHA-256 in
  `evaluation/s13-v3-diagnosis/inputs.json` before the analysis runs, and the analysis refuses a file whose digest
  differs.
* **Sprint 9 T9-v1 evidence.** The 30 primary candidate seats of `t9-confirmation-1` phase A (2130511121 H1, T9-v1 red,
  15 games; H2, T9-v1 blue, 15 games): the private records, Sprint 9's `T9Capture` file and its exploratory capture
  (50-step snapshots of flags, scores and total strength per side), also pinned by SHA-256. These games hold no
  per-decision trace and no full-step state; any requested Sprint 9 metric that needs them is reported as unavailable,
  never reconstructed from aggregates.
* **Off-policy counterfactuals.** T9-v1, T9-v2 and the oracles of section 7 are decided offline on states that v3
  produced. Their actions are action-level facts about those states; their downstream consequences were never played
  and are never described as engine outcomes. A Sprint 9 T9-v1 game is a different stochastic game from a Sprint 12 v3
  game, so no same-game causal chain between them can be established; comparisons with Sprint 9 are descriptive.
* **Four games.** Every statement about prevalence or prediction is exploratory. No model is fitted; features are
  read through conditional counts and one rank statistic per feature.

## 3. Reconstruction of four policies on the Sprint 12 states

On every decision of the v3 seat in each game (2,881 per game), from the captured seat observation and the captured
`baseline-v2` memory (`AddonMemory.baseline`), the analysis decides, each with a fresh policy instance:

* `baseline-v2`: the frozen `ShootReservationPolicy`;
* T9-v1: the frozen `t9_allocation.AllocationAddon` applied to that `baseline-v2` decision, and independently Sprint 10's
  `t9_diagnostic.audit_allocation`, which also records every capacity and alternative test; the two must agree on the
  actions and changes at every decision;
* T9-v2: the frozen `t9_staging.StagingAddon`;
* v3: the frozen `t9_batch.allocate`.

All four policies are stateless add-ons of the same `baseline-v2` memory chain, so each one's decision on a captured
state is well defined. Verification before any other figure: the reconstructed `baseline-v2` actions and trace digest
equal those the timeline captured, and the reconstructed v3 actions equal the actions the v3 seat submitted, with
v3's selected, staged and withheld sets equal to the captured allocation, at every decision. Any disagreement stops the
analysis.

## 4. Differences between T9-v1 and v3

The unit of comparison is one `baseline-v2` move order for an own ground unit in one decision. Each such order has a
T9-v1 form (KEEP, REDIRECT to another objective, WITHHOLD; a redirect the project gate rejects reverts to KEEP) and a
v3 form (KEEP, STAGE, WITHHOLD; a staged move the gate rejects is WITHHELD). An order whose two forms emit the same
action is not a difference. Every other order receives exactly one class, taken in this order:

1. `CROSS_OBJECTIVE_REDIRECTION_V1_ONLY`: T9-v1 redirects, v3 keeps `baseline-v2`'s move;
2. `STAGING_VERSUS_REDIRECTION`: T9-v1 redirects, v3 stages;
3. `WITHHOLDING_VERSUS_REDIRECTION`: T9-v1 redirects, v3 withholds;
4. `END_OF_GAME_FEASIBILITY_EXCLUSION`: T9-v1 keeps, v3 stages or withholds because the claimant cannot arrive before
   `max_step`;
5. `INCUMBENT_MOVER_DIFFERENCE`: T9-v1 withholds, v3 keeps, and T9-v1 would have kept the order had it counted only
   the incumbents v3 counts (movers that cannot arrive before the end excluded);
6. `SAME_OBJECTIVE_CAPACITY_SELECTION`: any other KEEP against STAGE or WITHHOLD, either way round (emission order
   against free-flow rank on the same objective);
7. `STAGING_VERSUS_WITHHOLDING`: T9-v1 withholds, v3 stages, same objective;
8. `OTHER`: anything else (expected empty; reported if not).

Classes 1 to 3 also carry v3's reason and a cause: `PHANTOM_INCUMBENTS` when T9-v1's destination count reached four
only because of movers that cannot arrive before the end, otherwise `CAPACITY`. Actions other than own ground move
orders must be identical in both policies; their count is reported and any difference stops the analysis. Counts are
given by game, seat, decision interval (decisions 0 to 99, 100 to 499, 500 to 1,499, 1,500 to the end) and objective
(Sprint 11's public labels: value and letter).

## 5. Loss of cross-objective reallocation

For every T9-v1 REDIRECT on a v3 state the private rows keep: the source objective (`baseline-v2`'s), the replacement
objective, T9-v1's reason (the destination's count at the order, the phantom share of that count, the replacement's
cost against the detour bound), the unit kind, its position, route lengths to both objectives, both objectives' flags
and T9-v1 commitment counts, and v3's form and reason for the same order. Public output aggregates these by objective
label pair, kind and v3 form.

Per game: the first decision at which T9-v1 and v3 emit different actions, and the first decision with a T9-v1
REDIRECT (the first redistribution divergence). The redistribution signature on v3's states is the share of T9-v1's
emitted ground moves that are redirects; it is set beside Sprint 9's per-game share of re-assigned among emitted ground
moves in the 30 real T9-v1 seats (the definition that gave 842 of 1,294), as a descriptive comparison of different
state populations.

The v3 game's own later facts are listed beside these divergences, with no counterfactual claim: capture order,
objectives never own, objectives own and later lost, the v3 seat's direct-fire listings and orders by interval, own
unit losses by interval, the final objective count, and red coverage.

## 6. Reservations that were never honoured

A reservation episode is one (holder, objective) pair from v3's selection of the holder for that objective (or its
first appearance as a counted mover) to the last decision in which v3 counted it. For every episode, privately: the
selection decision, the free-flow estimate, the path hexes reached and remaining, the decisions it stayed counted,
whether and when the holder left the seat's units (destroyed) before standing on the objective, whether v3 stopped
counting it at the first decision whose observation no longer lists it, the claimant-decisions in which a selectable
claimant of that objective was staged or withheld while it was counted, those claimants' free-flow times, and whether a
blocked claimant's free-flow time was below the holder's remaining lower bound at that decision ("faster"). After the
release: the decisions until v3 next selects a claimant for that objective, the steps from that selection to its
arrival, and whether that replacement's place ended OCCUPIED or HELD (Sprint 12's place outcomes, unchanged).

Destruction is never treated as known at selection time: the all-seeing timeline only labels outcomes. Public output:
episode counts by outcome (honoured, destroyed before arrival, alive and never arrived), lifetimes, blocked
claimant-decisions and distinct claimants, faster blocked claimants, release-to-replacement and replacement-to-arrival
distributions, and replacement outcomes, by game and pooled; the 27 holders Sprint 12 reported are reproduced first.

## 7. Prospective features and oracles

**Features.** For every place v3 selected, at the selection decision and from the seat's own observation only:
free-flow time; route length in hexes; unit kind; strength fraction (`blood / max_blood`); suppressed (`keep` not 0);
the number of enemy units the seat sees; hex distance from the unit to the nearest seen enemy; the smallest hex
distance from any hex of the route to a seen enemy; seen enemies within 3 hexes of the route; the objective contested
(not own, and a seen enemy within 2 hexes of it or the enemy's flag on it); the objective's value; the counted
incumbents of the objective before the decision. Label (all-seeing timeline, analysis only): Sprint 12's outcome LOST
against every other outcome. Each feature is reported as conditional counts by quartile (or category) and by one rank
statistic, the probability that a LOST place has the larger value (AUC; ties count one half), pooled and per game. The
same features are described, per holder, at each counted decision of its episode (with path progress and the incumbent
flag), weighting each holder equally. A feature is *prospectively separating* when its pooled AUC is at least 0.70 or
at most 0.30 and its per-game AUC lies on the same side of 0.5 in every game with at least 3 LOST and 3 other places.

**Oracles** (offline diagnostics only; they are not candidates, are named nowhere as policies, and never enter a run
card):

* O1: v3's allocation, but a counted mover that will leave the seat's units before standing on its objective (label
  from the timeline: future information on purpose) holds no place. It bounds the action opportunity of an oracle that
  knew which holders would die.
* O2: v3's counting, ranking and end-of-game test, with T9-v1's cross-objective rule for claimants that v3 leaves
  without a place because the objective is full: in v3's rank order, each such claimant goes to the T9-v1 alternative
  (another objective not own, fewer than four places counted the v3 way including this decision's selections and
  redirects, path cost at most twice the cost to its own objective, smallest cost divided by value) whose free-flow
  arrival is before `max_step`; with none it is staged or withheld as by v3. A redirect the gate rejects is withheld.
  O2 uses only information T9-v1 used at that decision.
* O3: O1 and O2 together.

The oracles are implemented by one analysis-side allocator that must reproduce `t9_batch.allocate` exactly (actions,
selected, staged, withheld) at every decision when both modifications are off. For each oracle and each policy: slot
assignments per objective, cross-objective moves, staged and withheld orders, claimants newly admitted relative to v3,
and action differences from T9-v1 and from v3, in order-decisions and distinct units. No game score is computed or
estimated for any oracle. The question is whether the two modifications change different decisions or mostly the same
ones.

## 8. Sequence analysis and Sprint 9 comparison

Both populations carry the same `T9Capture` facts and the same 50-step snapshots (decision index `k` divisible by 50:
flags, scores and total strength per side). From the 15 Sprint 9 T9-v1 games of the same seat, per snapshot:

* the T9-v1 range (minimum and maximum) of the seat metric, which is red cumulative coverage (mean objectives own over
  the play snapshots so far) for H1 and the seat's margin (`<side>_win`) for H2; a v3 game's score divergence point
  `D` is the first snapshot from which its metric stays below the T9-v1 minimum at every later snapshot (none if no
  such snapshot exists);
* the characteristic ownership pattern: an objective is characteristically own at a snapshot when T9-v1 owned it in at
  least 12 of 15 games and characteristically not own when in at most 3; the first ownership divergence is the first
  snapshot at which a v3 game contradicts a characteristic entry (undefined if no entry exists);
* the same "stays below the minimum to the end" first snapshot for own attack points and own total strength.

Per v3 game a compact private chronology and a public certificate list: the first T9-v1/v3 action divergence, the
first redistribution divergence, the first unproductive reservation that blocks a claimant, `D`, the first ownership
divergence, and the attack and strength divergences, each as decision and step. Every certificate states that the
compared T9-v1 trajectories are other stochastic games, so no causal chain is claimed.

Per-game comparison with the 30 Sprint 9 seats, using fields both populations hold: ground moves emitted;
re-assignments among them (v3 makes none by construction); largest objective commitment; waiting unit-steps; red or
blue coverage; objectives ever own, own at the end and own then lost; first-own snapshot order (capture order at 50-step
resolution); attack; units lost; margin. Each v3 value is placed against the 15 same-seat T9-v1 values (minimum, median,
maximum and rank). v3's staging and withholding counts are reported beside T9-v1's withholding but are not the same
quantity.

## 9. Disposition rule (mechanical)

Per game `g`, with onsets measured in steps:

* A, loss of redistribution, is material in `g` when T9-v1 on v3's states redirects at least 4 distinct units, its
  redirects are at least 25% of its emitted ground moves, and the first redirect comes before `D(g)` (or `D(g)` does
  not exist);
* B, blocking by never-honoured reservations, is material in `g` when O1 newly admits at least 4 distinct claimant
  units, its newly admitted claimant-decisions are at least 10% of v3's staged or withheld selectable
  claimant-decisions in `g`, and the first such admission comes before `D(g)` (or `D(g)` does not exist).

A mechanism is material when it is material in at least 3 of the 4 games including at least one H1 and one H2 game.
`J` is the pooled overlap |A ∩ B| / |A ∪ B| of the (game, decision, unit) sets of T9-v1 redirects and O1 admissions.
`SA` and `SB` sum the per-game distinct units of the two sets. `P` holds when at least one feature of section 7 is
prospectively separating.

1. Neither material: `INSUFFICIENT_FOR_REVISION`.
2. A material, B not: `REDISTRIBUTION_DOMINANT`.
3. B material, A not: `RESERVATION_LIFETIME_DOMINANT` if `P`, otherwise `INSUFFICIENT_FOR_REVISION`.
4. Both material and `J` > 0.5: `REDISTRIBUTION_DOMINANT` if `SA` >= `SB`, otherwise as in 3.
5. Both material and `J` <= 0.5: `REDISTRIBUTION_DOMINANT` if `SB` < 0.25 `SA`; as in 3 if `SA` < 0.25 `SB`; otherwise
   `BOTH_MECHANISMS_MATERIAL`.

The label is computed by code from the published facts and is not chosen from terminal scores. A third mechanism, if
the captures establish one, is reported descriptively; it can change the label only through rule 1.

## 10. What the result may and may not lead to

Design requirements implied by the result may be described. No new policy is implemented while the diagnosis is open,
and none of the following is assumed to be the remedy: restoring all of T9-v1's redirection, ignoring movers likely to
die, a fixed reservation timeout, overbooking objective capacity, or stopping active movers. Any future policy must be
seat-local. Exactly one next task is recommended.

## 11. Outputs, privacy and tests

* Public: `evaluation/s13-v3-diagnosis/inputs.json` (input digests, before the analysis) and the result files written
  by `scripts/s13_v3_diagnosis.py`, each regenerated byte for byte from the private inputs (`--check`) and each below
  100,000 bytes. Every public serializer refuses unit ids, hexes, paths, coordinates and raw observations
  (`s12_screen.privacy_problems` with the private values of the games planted as forbidden).
* Private (server, ignored `local/diagnostics/s13/`): per-order rows, reservation episodes, feature rows and the four
  chronologies.
* Tests: synthetic cases for redistribution only, unproductive reservation only, both, neither, a holder destroyed after
  several blocked decisions, a released slot and a replacement, a faster claimant blocked by an incumbent, and a
  feature that cannot identify later destruction; planted analysis defects that the tests must catch; the oracle
  allocator's identity with `t9_batch.allocate`; and a server test that regenerates every public file from the private
  inputs.
* Close-out: the full non-engine suites on the workstation tree, a clean clone and the server private tree; the
  historical documentation gates; the privacy scan compared with the accepted 103 hits as a set of hit lines, not as a
  count; and a ledger check that still reads 2,790 sessions, none unclosed.

## 12. Not claimed

Nothing here is an engine result for T9-v1, T9-v2 or any oracle on these states, a score estimate, or evidence that a
revised policy would improve anything. Sprint 12's disposition stands.

## Results (2026-10-06)

Sections 1 to 12 were pushed as commit `a34f2691598b43b64ff01acdebb69a5dc3391d6d` at 2026-10-06T00:11:21+08:00, together
with the input digests, and fetched back unauthenticated byte for byte before the analysis ran; they are unchanged.
Every figure below comes from the public files of `evaluation/s13-v3-diagnosis/` (`reconstruction`, `redistribution`,
`reservations`, `features`, `oracles`, `sequence`, `disposition`), which `scripts/s13_v3_diagnosis.py run --check`
regenerates byte for byte from the pinned private inputs on the evaluation server. T9-v1, T9-v2 and the oracles are
action-level counterfactuals on states that v3 produced; none of their consequences was played.

### R1. Inputs and reconstruction

* Inputs: the four Sprint 12 P1 games (sessions 2787 to 2790) with their records and 20 capture files, the scenario's
  cost data, and the 30 Sprint 9 phase-A primary T9-v1 seats (15 H1 red, 15 H2 blue) with their records, `T9Capture`
  and exploratory capture files, each pinned by SHA-256 in `evaluation/s13-v3-diagnosis/inputs.json`; the four policy
  identities were recomputed from the checkout and equal the frozen values.
* All 11,524 decisions of the v3 seat (2,881 per game) were reconstructed. At every one the reconstructed
  `baseline-v2` actions and trace digest equalled the captured ones and the reconstructed v3 actions equalled the
  submitted actions; at every decision with an own ground move (660: 300, 158, 16 and 186 in games p01 to p04) v3's
  selected, staged and withheld sets equalled the captured allocation, the oracle allocator without modifications
  equalled `t9_batch.allocate`, the frozen T9-v1 add-on equalled Sprint 10's independent audit, and the counted movers
  equalled the captured ones. No disagreement occurred.
* The seat's decision-1 state was identical in the two games of each seat (H1 and H2).

### R2. Where T9-v1 and v3 differ (section 4)

1,523 `baseline-v2` ground move orders were classified (505, 470, 50 and 498); 913 of them differ between T9-v1 and v3.

| Class | p01 (H1) | p02 (H2) | p03 (H1) | p04 (H2) | Pooled |
|---|---:|---:|---:|---:|---:|
| `CROSS_OBJECTIVE_REDIRECTION_V1_ONLY` | 0 | 5 | 0 | 4 | 9 |
| `STAGING_VERSUS_REDIRECTION` | 34 | 46 | 15 | 50 | 145 |
| `WITHHOLDING_VERSUS_REDIRECTION` | 128 | 161 | 0 | 202 | 491 |
| `END_OF_GAME_FEASIBILITY_EXCLUSION` | 145 | 2 | 4 | 73 | 224 |
| `INCUMBENT_MOVER_DIFFERENCE` | 0 | 0 | 0 | 0 | 0 |
| `SAME_OBJECTIVE_CAPACITY_SELECTION` | 4 | 7 | 0 | 6 | 17 |
| `STAGING_VERSUS_WITHHOLDING` | 2 | 15 | 0 | 10 | 27 |
| `OTHER` | 0 | 0 | 0 | 0 | 0 |

* Redistribution classes (the first three) hold 645 of the 913 differences. Every T9-v1 redirect had the cause
  `CAPACITY`: none was triggered only by movers that cannot arrive, so the incumbent-mover difference never arose.
* The end-of-game exclusions are late: 220 of the 224 come from decision 1,500 on (143 in p01, 73 in p04), when the
  units T9-v1 would have kept could not reach their objective before the end.
* Every action other than an own ground move order was identical to `baseline-v2`'s under every policy and oracle,
  in order (1,127 comparisons at the 660 decisions with an own ground move).

### R3. Loss of cross-objective reallocation (section 5)

| Game | Distinct units T9-v1 redirects | Redirects | T9-v1 emitted ground moves | Redirect share |
|---|---:|---:|---:|---:|
| p01 (H1) | 18 | 162 | 346 | 0.4682 |
| p02 (H2) | 22 | 212 | 268 | 0.7910 |
| p03 (H1) | 14 | 15 | 49 | 0.3061 |
| p04 (H2) | 22 | 256 | 394 | 0.6497 |

* Timing: the first T9-v1/v3 action difference and the first redirect are at decision 1 in every game. At decision 1
  T9-v1 redirects 14 units as red and 19 as blue (the states are identical within a seat). Later redirects concentrate
  where v3 withholds full-objective overflow repeatedly: in p01 from decision 581 on, from 50-point objective C to
  80-point objective C (83 orders), 80-point objective B (34) and 50-point objective D (25); in p02 and p04 from
  decision 365 on, from 80-point objective A to 50-point objective D (132 and 173 orders), of which v3 withheld 128 and
  169 and staged the rest.
* Signature against Sprint 9 (descriptive, different state populations): the share of re-assigned among emitted
  ground moves was 0.4107 to 0.6500 in the 15 real T9-v1 H1 seats and 0.7500 to 0.8444 in the 15 H2 seats; on v3's
  states T9-v1 would redirect 0.4682 and 0.3061 as red and 0.7910 and 0.6497 as blue. v3 makes none by construction.
* What the redirects point at, beside what v3 then did. As red, the objectives T9-v1 redirects to at decision 1
  include 80-point objectives B and C; at the 50-step snapshots T9-v1 owned 80-point objective C in all 15 of its H1
  games and objective B in 11, while v3 never owned objective C in either H1 game and never owned objective B in p03.
  Both H1 games ended with no objective own (p01 never own: 80-point objective C; p03: 50-point objective C and 80-point objectives B and C). As
  blue, v3 owned all seven objectives at some point and six at the end in both games (50-point objective C own and
  then lost); T9-v1 owned all seven at the end in all 15 H2 games. These are other stochastic games, so no causal chain
  is claimed.

### R4. Reservations that were never honoured (section 6)

* Sprint 12's figures are reproduced exactly: holds behind a never-honoured place 298 of 319, 187 of 405, 13 of 14 and
  57 of 350, and 12, 6, 4 and 5 such holders, all 27 destroyed before arriving.
* Episodes: 188 reservation episodes, 139 honoured and 49 destroyed before arriving; none alive without arriving. The
  53 places Sprint 12 classed LOST are the 49 destroyed episodes plus 4 units in p01 lost one decision after their
  selection, before they were ever counted. One of the 27 holders, in p01, likewise formed no episode, so
  episode-level blocking covers the other 26.
* The 26 destroyed holders that blocked a claimant held their place a median of 59.5 decisions from selection to
  release (20 to 276) and blocked 1,093 claimant-decisions. In only 1 of those 1,093 was the blocked claimant's
  free-flow time below the holder's remaining bound: the destroyed holders were almost always closer to the objective
  than the units they kept out. Honoured holders blocked 3,162 claimant-decisions, 413 of them by a faster claimant.
* Release and replacement: every one of the 26 places was released at the first decision whose observation no longer
  listed the holder. v3 selected a replacement for that objective a median of 0 steps later (0 to 166; 2 of 26 never
  replaced); the replacements that arrived took 20 to 161 steps, and for 5 of the 26 a replacement place ended
  OCCUPIED or HELD.

### R5. Prospective features (section 7)

192 places were selected in the four games, 53 of them LOST. No registered feature is prospectively separating.

| Feature | Pooled AUC (LOST larger) | Per game p01, p02, p03, p04 |
|---|---:|---|
| seen enemies within 3 hexes of the route | 0.6993 | 0.5013, 0.4848, 0.76, 0.7921 |
| objective contested | 0.6277 | 0.6627, 0.613, 0.6667, 0.6404 |
| counted incumbents | 0.6336 | 0.8214, 0.475, 0.6244, 0.5939 |
| route's nearest seen enemy (hexes) | 0.3436 | 0.2557, 0.406, 0.3942, 0.2857 |
| strength fraction | 0.385 | 0.3254, 0.3674, 0.44, 0.3772 |
| free-flow time | 0.4122 | 0.1839, 0.4511, 0.4156, 0.4579 |

* The closest, seen enemies near the route, falls below 0.70 pooled and points the other way in p02. Conditional
  counts show associations, not identification: 49 of the 142 places at a contested objective were lost, against 4 of
  the 50 elsewhere, so a rule that dropped contested reservations would also have dropped 93 places that were not lost.
* Per holder, destroyed holders spent a larger share of their counted decisions with a seen enemy within 3 hexes and
  below full strength than honoured ones in every game (`features.json`, holder descriptives); this is a description,
  not a predictor.

### R6. Oracle decomposition (section 7)

Pooled over the four games (order-decisions; objective-decisions for slot assignments):

| Policy | Cross-objective | Staged | Withheld | Admitted where v3 held back | Slot assignments differing from T9-v1 | Orders differing from T9-v1 | Orders differing from v3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline-v2` | 0 | 0 | 0 | 1,331 | 806 | 1,111 | 1,331 |
| T9-v1 | 645 | 0 | 466 | 871 | 0 | 0 | 913 |
| T9-v2 | 0 | 589 | 514 | 241 | 369 | 709 | 712 |
| v3 | 0 | 191 | 1,140 | 0 | 550 | 913 | 0 |
| O1 (no doomed holders) | 0 | 172 | 867 | 292 | 752 | 1,040 | 297 |
| O2 (v3 plus T9-v1 redirection) | 637 | 51 | 643 | 637 | 222 | 337 | 645 |
| O3 (both) | 583 | 44 | 412 | 875 | 605 | 724 | 881 |

* O2 removes most of v3's divergence from T9-v1 (slot assignments 550 to 222, orders 913 to 337); O1 moves v3 further
  from T9-v1 (752 and 1,040), because T9-v1 also counts the holders that later die.
* The two modifications change different decisions: of the 645 T9-v1 redirect order-decisions and the 292 O1
  admissions, 154 coincide (overlap 0.1967). The end-of-game test removed 8 T9-v1 alternatives in O2 (4 in each H2
  game) and none as red.

### R7. Sequence and Sprint 9 comparison (section 8)

| Game | First redirect | First blocking unproductive reservation | First O1 admission | First ownership divergence | Score divergence `D` | Attack | Strength |
|---|---|---|---|---|---|---|---|
| p01 (H1) | decision 1 | decision 581 | decision 581 | step 550 | step 950 | none | none |
| p02 (H2) | decision 1 | decision 1 | decision 365 | step 250 | step 1450 | step 1300 | step 750 |
| p03 (H1) | decision 1 | decision 1 | decision 581 | step 550 | step 550 | step 450 | none |
| p04 (H2) | decision 1 | decision 365 | decision 365 | step 250 | step 1900 | step 2350 | step 750 |

* The characteristic T9-v1 pattern is defined in both seats (269 entries as red, 392 as blue). As red, all 15 T9-v1
  games first owned 50-point objective B at step 550 and neither v3 game owned it then; as blue, all 15 first owned it
  at step 1450, so none owned it at step 250, and both v3 games did.
* The ownership pattern departs from T9-v1's before the seat metric does in three games and at the same snapshot in
  p03, and every game's redistribution difference is present from decision 1. As blue, own strength falls below every
  T9-v1 game from step 750 on, well before the margin (steps 1450 and 1900).
* Against the 15 same-seat T9-v1 games (`sequence.json`, placements): as red, coverage 0.5691 and 0.2885 below the
  minimum 0.6184 and units lost 35 and 29 against a median of 32; as blue, coverage 6.0056 and 5.7139 above the maximum
  5.426, yet attack 442 and 466 below the minimum 490, units lost 18 and 16 against a median of 11, waiting unit-steps
  184 and 200 against at most 6, and six objectives at the end against seven in every T9-v1 game. v3 emitted 124 and 135
  ground moves as blue against at most 64.
* Not available in Sprint 9: per-decision redirect timing, full-step states, shot listings and per-objective flags in
  the final state (its snapshots end at step 2850); none of them was reconstructed from aggregates.

### R8. Disposition

| Game | A share | A material | B share | B material |
|---|---:|---|---:|---|
| p01 (H1) | 0.4682 | yes | 0.721 | yes |
| p02 (H2) | 0.791 | yes | 0.1037 | yes |
| p03 (H1) | 0.3061 | yes | 0.0714 | no |
| p04 (H2) | 0.6497 | yes | 0.0543 | no |

A is material in all four games; B in two (one per seat), short of the three the rule requires. `SA` = 76, `SB` = 24,
overlap 0.1967, no prospectively separating feature. Rule 2 applies:

**REDISTRIBUTION_DOMINANT.**

Sensitivity, stated because the margin is narrow: B in p02 is 0.1037 against the 0.10 threshold, and in p04 it is
0.0543. Had B been material in one more game, rule 5 would have given BOTH_MECHANISMS_MATERIAL (`SB` 24 is not below
0.25 `SA` = 19). Never-honoured reservations are therefore a real, large effect in p01 (230 of 319 held claimant-decisions
admitted by O1) and a small one elsewhere; they are not the main actionable difference across the four games, and
nothing seat-local identified them in advance.

No third mechanism was established. The end-of-game exclusions (224 orders) are late and concern units that could not
reach their objective before the end. As blue, the earliest divergence in a score-type quantity is own strength at
step 750, after the decision-1 redistribution difference and during v3's withholding of 80-point objective A's
overflow; with other stochastic games as the only reference, that is an observation, not an established mechanism.

### R9. Design constraints implied (no design is implemented)

1. Cross-objective reallocation is the part of T9-v1 that v3 lost, and it is the part Sprint 10 tied to the adverse
   configurations (1930331196 C2 and C3 corridors, 2120531121 C3 far reservations). A future allocator that restores
   any of it must be evaluated offline on the Sprint 10 adverse captures as well as on these four primary games before
   any engine request.
2. Any redirect keeps v3's admission discipline: rank order free of emission order, and no place for a unit that
   cannot arrive before the end (the test that removed T9-v1's unreachable reservations). O2 shows the two compose: it
   redirects 637 order-decisions and the end-of-game test dropped only 8 alternatives.
3. Redirection should be bounded to overflow of a full objective (T9-v1's trigger); O2 kept every claimant that had a
   place and redirected only the rest, and still removed most of v3's slot-assignment divergence from T9-v1 (550 to 222
   objective-decisions).
4. No reservation timeout, threat-based release or overbooking is supported: destroyed holders were released at the
   next decision every time, the claimants they blocked were almost never faster, and no seat-local feature separated
   them in advance.
5. Seat-local inputs only; stop orders to active movers stay outside every design (untested at the engine).

### R10. Tests, privacy, provenance

* Tests: `tests/test_s13_diagnosis.py` (28 synthetic tests: redistribution only, unproductive reservation only, both,
  neither, a holder destroyed after several blocked decisions and released and replaced, a faster claimant blocked by an
  incumbent, a feature that cannot identify destruction, the exact boundaries, the oracle allocator's identity with v3,
  planted ids), `tests/test_s13_results.py` (6 tests binding the files to each other, to Sprint 12's committed report and
  to the registered rule; five planted result errors were each caught), `tests/test_real_s13_diagnosis.py` (server:
  freeze and run `--check`, mutation record). Mutation: 36 of 36 planted analysis defects caught
  (`evaluation/s13-v3-diagnosis/mutation.json`); the first run caught 31, and the 5 gaps were missing tests, added
  before the record.
* Corrections made before the results were committed, none to a registered measure or threshold: a reservation episode
  first omitted the holder's own selection decision from its blocked claimant-decisions, which section 6 includes
  (Sprint 12 counts a unit selected at a decision among that decision's holders); a public key named `units` was
  renamed; the disposition file's thresholds were overwritten by the rule number until renamed `thresholds`; and four
  descriptive tables (redirect timing, classes by v3's reason, the LOST-place reconciliation and the decision-1 state
  identity) were added after the first results were read.
* One amendment after the analysis, to a file pinned before it: the pushed `inputs.json` listed the four policy
  digests, and Sprint 12's owner-approved safeguard (`tests/test_t9_batch.py`) allows v3's identity in no evaluation
  file outside its listed folders, so the full suite failed on it. The safeguard was left unchanged; `inputs.json` now
  names the identities the driver checks against its frozen table (the digests remain in section 1 and in the driver,
  which refuses on any mismatch). Its Sprint 12 and Sprint 9 input digests are byte-identical to the pushed version, and
  the public files changed only in the digest of `inputs.json` they record.
* Privacy: every public file passed the forbidden-key check and a value check against every hex the games' seats saw.
  Unit ids are not part of the value check: these games' ids include round numbers such as 100 and 1,300 that coincide
  with steps and counts, so ids are excluded structurally (forbidden keys, aggregates only, planted-id tests).
* No engine session was opened; the server's read-only ledger check still reports 2,790 sessions, none unclosed.

### R11. Recommended next task

One task, offline and without the engine: a design study of a feasibility-gated cross-objective allocator that starts
from O2 (v3's counting, ranking and end-of-game test, with T9-v1's redirection applied only to the overflow of a full
objective), evaluated by action replay on these four primary games and on the six Sprint 10 diagnostic captures of the
adverse configurations, with offline criteria fixed before the replay: how much of T9-v1's primary slot assignment it
recovers, and that it recreates neither the 1930331196 corridor redirects nor a far reservation of 2120531121 C3's
missed objective. The study may conclude that no gated redirection meets both; no proposal or engine request comes
before it closes.
