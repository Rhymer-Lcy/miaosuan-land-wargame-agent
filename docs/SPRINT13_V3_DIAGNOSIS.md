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
