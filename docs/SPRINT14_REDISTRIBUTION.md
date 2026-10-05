# Sprint 14: bounded cross-objective allocation

**PART A: OFFLINE DESIGN COMPETITION — PROTOCOL FIXED BEFORE ANY CANDIDATE WAS REPLAYED ON THE TARGET CORPUS**

Sprint 14 looks for a deterministic, seat-local allocator that restores useful cross-objective redistribution of
overflow (the part of T9-v1 that `t9-batch-capacity-v3` lost, Sprint 13) without recreating the adverse mechanisms that
Sprint 10 diagnosed. Part A is offline: it opens no engine session. Part B, a small exploratory engine screen, may follow
only if exactly one candidate passes the gate of section 7, and only after its own registration (section 10). Dates are
business dates in UTC+8; this protocol was written on 2026-10-06.

Sections 1 to 12 are the protocol. They are committed and pushed, together with the candidate module, its synthetic
tests and the input digests, before any candidate decision is computed on the target corpus, and they are not edited
afterwards; results follow in a separate section.

## 1. Starting state and fixed results

| Item | Identity |
|---|---|
| Repository | `main` `5d733da043a14bd3943d7bb11627b494abf7eaa3`, tree `543094f8eb7654dc891bdd64e2a820386aeeabd4`, identical on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,790 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `e2116700df7645f7c116386bfb4b955cb2725f1541ba24f906fafe9172891cef`; session 2791 never opened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| T9-v1 | policy source `0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa` |
| T9-v2 | policy source `66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece` |
| T9-v3 | policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8` |
| Privacy baseline | the 103 adjudicated hits accepted at Sprint 13's close, compared as a set of hit lines |

Fixed and not re-litigated: Sprint 12's disposition `NOT_PRESERVED_IN_PRIMARY` and Sprint 13's `REDISTRIBUTION_DOMINANT`,
with Sprint 13's figures as published (`evaluation/s13-v3-diagnosis/`). None of the four frozen policies is modified.

## 2. Authorization and scope

* Part A (offline) is authorized without an engine. Part B is authorized in advance by the owner on one condition:
  exactly one candidate is selected by section 8 after passing every item of section 7. With no passing candidate the
  disposition is `NO_ENGINE_CANDIDATE` and session 2791 is not opened.
* Part B's ceiling is 16 sessions after session 2790, one exclusive session at a time, no retry or replacement of a game,
  no confirmation study and no baseline promotion.
* Seat-local inputs only (the seat's own observation and the setup cost data); no future information; no stop orders
  to active movers; no scenario, objective, coordinate or unit special case.
* External research: none was used for the candidates below. The batch rule is a textbook minimum-cost maximum flow.

## 3. Candidates

All candidates live in one module, `src/miaosuan_agent/experiments/t9_redistribution.py`, an add-on to the frozen
`baseline-v2` through the unchanged exploratory wrapper; its policy-source identity (`baseline-v2`'s source set plus
`exploratory_addon.py`, the frozen `t9_batch.py` and the module) is recorded in
`evaluation/s14-redistribution-design/inputs.json` before the replay. No candidate is in any run card.

**Stage 1 (every candidate)** is v3 restated without change (counting of incumbents and of movers that can arrive
before the end, claimants ranked by free-flow time, route cost, path length and unit id, the best selectable claimants
take the free places). With no redistribution rule the module must reproduce `t9_batch.allocate` exactly; the synthetic
tests check it, and the replay checks that every candidate keeps every v3 selection.

**Stage 2 (redistribution of overflow only).** A claimant that could arrive at its own objective before the end but found
it full (v3's status "no place under capacity") may be redirected to another objective by the very move `baseline-v2`'s
candidate builder makes for that unit and objective (the router's path from the unit's hex), when all of the following
hold: the objective is not held by the side and differs from the claimant's own; its places, counted the stage-1 way
including this decision's selections and redirects, are fewer than four; its route cost is at most twice the cost to the
claimant's own objective (T9-v1's bound); its free-flow time ends before `max_step`; and the rule's own bounds hold. A
claimant that cannot arrive at its own objective is never redirected. Every claimant left without a place is staged on
its own route or withheld exactly as by v3. Replaced moves pass the project gate together with the step's other actions;
a rejected redirect or staged move is withheld. Every other action is unchanged and keeps its order. An internal failure
withholds every own ground move to an objective for that decision.

| Rule | Family | Ranking of admissible objectives | Own bound | Order of claimants |
|---|---|---|---|---|
| `feasible-cost-redirect` | D, capacity-aware `baseline-v2` | route cost, then hex (`baseline-v2`'s own order) | none | stage-1 rank |
| `feasible-value-redirect` | A, minimal O2 | cost / value, cost, hex (T9-v1's) | none | stage-1 rank |
| `feasible-value-redirect-h1440` | A, horizon | as A | free-flow time at most 1,440 steps | stage-1 rank |
| `feasible-value-redirect-h720` | A, horizon | as A | free-flow time at most 720 steps | stage-1 rank |
| `corridor-value-redirect-p25` | B, corridor | as A | shares at least 25% of `baseline-v2`'s path as its prefix | stage-1 rank |
| `corridor-value-redirect-p50` | B, corridor | as A | at least 50% | stage-1 rank |
| `corridor-value-redirect-p75` | B, corridor | as A | at least 75% | stage-1 rank |
| `batch-value-redirect` | C, batch assignment | arc cost = cost / value | none | all at once: the most redirects the places allow, then the smallest total cost / value (minimum-cost maximum flow, canonical order) |

Each rule's engine identity would be `t9-<rule>-v4`. `feasible-value-redirect` is Sprint 13's oracle O2 stated as a
policy; the replay requires it to equal O2 at every decision. The horizon and prefix grids are the sensitivity analysis
of their families' constants; neither constant was chosen from the target corpus. Shared prefix: all routes of one
unit come from one shortest-path tree from its hex, so the redirect's route and `baseline-v2`'s route share a leading
run of hexes until they branch; the share is that run's length over the length of `baseline-v2`'s route.

## 4. Target corpus

* **Primary**: the four Sprint 12 games (sessions 2787 to 2790; 2130511121; p01 and p03 H1 with the v3 seat red, p02
  and p04 H2 with it blue), every decision of the v3 seat, from the private records and timelines.
* **Adverse**: the six Sprint 10 full-step diagnostic captures (sessions 2773 to 2778): 2120531121 C3, 1930331196 C3
  (seat 11) and 1930331196 C2 (seat 1), each once with T9-v1 and once with `baseline-v2` in the diagnosed seat, every
  decision.

Every file is pinned by SHA-256 in `inputs.json` (the replay refuses a file whose digest differs), together with the cost
data, the gate thresholds and the Sprint 13 and Sprint 10 reference figures of section 5. Development used synthetic
observations only (`tests/test_t9_redistribution.py`); no candidate decision was computed on any captured state before
this protocol was pushed.

## 5. Replay method and fidelity

On every decision of each capture, `baseline-v2` is re-decided by a fresh instance from the captured memory, and on its
actions are computed: frozen T9-v1, frozen T9-v2, frozen v3, Sprint 13's oracle O2 and the eight candidates. Faithfulness
is required, not assumed; any failure makes the disposition `REPLAY_INVALID`:

* the re-decided `baseline-v2` actions (and, for the primary games, the trace digest) equal the captured ones;
* what the diagnosed seat submitted equals the re-decided policy that played it (v3, T9-v1 or `baseline-v2`), and v3's
  selected, staged and withheld sets equal the captured allocation;
* T9-v1 equals Sprint 10's captured audit of it on the adverse captures;
* `feasible-value-redirect` equals O2 (actions and sets) at every decision;
* the four primary games reproduce Sprint 13's published figures: T9-v1 redirects 162, 212, 15 and 256 among 346, 268, 49
  and 394 emitted ground moves, 18, 22, 14 and 22 distinct redirected units, 14, 19, 14 and 19 redirects at the first
  decision; pooled slot divergence from T9-v1 550 for v3 and 222 for O2, order divergence from T9-v1 913 for v3 and 337
  for O2, O2's 645 orders differing from v3 and its 637 redirects;
* the anchors of the adverse checks are found in the captures as Sprint 10 and 11 published them: in 2120531121 C3 one
  80-point objective that T9-v1 never owned, first owned by `baseline-v2` at decision 564, and v3 admitting 9,194
  unit-decisions of claimants T9-v1 held back from decision 442 on; in 1930331196 C3 eight direct-fire actions at
  decisions 742, 804, 841 and 876 of the `baseline-v2` game, in C2 one at decision 611; T9-v1 redirecting 12 (C3) and 7
  (C2) orders at the first decision of its own game; the first decision with an own ground move is decision 1 in every
  capture.

Determinism and order invariance are tested on the captured states: every candidate decision is recomputed with a fresh
router, and every decision with at least two claimants under three reorderings of `baseline-v2`'s actions (reversed,
rotated by one, a seeded shuffle); the selections, redirects (objective and route), staged routes, withheld sets, the
per-unit moves and the order of the other actions must not change.

## 6. Metrics

A *redirect* is an emitted ground move whose objective differs from `baseline-v2`'s; *forms* are Sprint 13's (KEEP,
REDIRECT, STAGE, WITHHOLD per `baseline-v2` ground move order). Per policy and capture: emitted ground moves, redirects,
distinct redirected units, redirect share (redirects / emitted ground moves), keeps, stages, withholds, end-of-game
exclusions (claimants that cannot arrive), redirects at the first decision, the first decision whose ground moves differ
from `baseline-v2`'s, redirect destinations by public objective label, the largest objective commitment, slot divergence
and order divergence from `baseline-v2`, T9-v1, v3 and O2 (Sprint 13's definitions), and for redirects the
distributions of arrival slack (`max_step` minus free-flow arrival), free-flow time, detour ratio (route cost over the
cost to the own objective), shared prefix (hexes and share) and unit kind. Per seat: pooled redirect share and slot
divergence from T9-v1. Independent re-derivations per decision (a fresh router, `ps1_model.hex_time` for free-flow times):
unrelated actions and their order, invented moves, capacity (counted incumbents plus new places at most four wherever a
place is added), every redirect's route equal to `baseline-v2`'s candidate route for that objective, the objective not
held, the detour bound, arrival before the end, every other changed move a strict same-route prefix ending off
objectives, every v3 selection kept, gate rejections and errors. Latency: milliseconds per decision with an own ground
move, measured once (`timing.json`).

Adverse specifics. 2120531121 C3: places granted that cannot be reached; v3 selections not kept; redirects into the
missed objective; *far reservations of the missed objective*, redirects into it issued before the step at which
`baseline-v2` first owned it and arriving (free flow) after that step; the Sprint 11 certificate, unit-decisions from
decision 442 of the T9-v1 game in which a claimant of the missed objective that T9-v1 held back is admitted.
1930331196 C3 and C2: shooters (the units of the direct-fire actions of section 5) redirected at a decision before their
firing decision, in either trajectory; their forms before firing; redirects at the first decision (the decision state
is reported as identical or not across the two trajectories); redirects at decisions before the first firing decision
of the `baseline-v2` game; first-decision redirects equal to T9-v1's (same unit, same objective); T9-v1's
first-decision redirected units whose objective the candidate also changes; the first-decision redirects' prefix
shares. No shot, capture or score is inferred from any of these.

## 7. Gate (every item must hold)

| Item | Requirement |
|---|---|
| G1 deterministic | no difference between a decision and its recomputation with a fresh router, over every decision with an own ground move |
| G2 seat-local | the allocator's inputs are the observation, seat, faction, `baseline-v2`'s actions, the router and the rule; no analysis or engine module is imported (static) |
| G3 order invariant | no difference under the three reorderings, over every decision with at least two claimants |
| G4 capacity | no objective above four counted places where the candidate adds a place |
| G5 unrelated actions | none changed, none reordered |
| G6 no invented move | none |
| G7 engine-supported moves | every redirect is `baseline-v2`'s candidate route to an objective not held, within the detour bound; every other changed move a strict same-route prefix off objectives; no candidate error |
| G8 reachable | no place (kept or redirected move to an objective) for a unit whose free-flow arrival is not before `max_step` |
| G9 redistribution restored | per seat, pooled redirect share at least 0.5 of T9-v1's on the same states; in each of the four games, first-decision redirects at least 0.5 of T9-v1's and at least 4 distinct redirected units |
| G10 divergence reduced | pooled slot divergence and pooled order divergence from T9-v1 each at most 0.70 of v3's; each seat's slot divergence below v3's |
| G11 2120531121 C3 | no unreachable place, every v3 selection kept, no far reservation of the missed objective, certificate unit-decisions at least v3's (both trajectories) |
| G12 1930331196 corridors | in C3 and in C2: no shooter redirected before its firing decision (either trajectory); first-decision redirects (the larger of the two trajectories) at most floor(T9-v1's at the first decision of its own game / 3); redirects before the first firing decision on the `baseline-v2` trajectory at most floor(T9-v1's on the same states / 3) |
| G13 no future information | as G2: nothing but the current observation and cost data enters (static) |
| G14 no special case | the module's numeric literals are only its rule constants and structural indices (static) |
| G15 latency | 99th percentile at most 20 ms and maximum at most 200 ms per decision with an own ground move |

Thresholds are those of `GATE` in `src/miaosuan_agent/evaluation/s14_design.py`, recorded in `inputs.json`. "Materially"
in the sprint brief is G9 and G10. The tension is deliberate: G9 asks for at least half of T9-v1's first-decision
redistribution in the primary states, G12 for at most a third of it in the 1930331196 states. A rule passes both only if
something generic in the states separates them; if none does, no candidate passes.

## 8. Selection rubric (only among candidates that passed every item)

Lexicographic, each step keeping the best band:

1. margin band: `restore` = the smallest of the seat share ratios and the first-decision ratios of G9 (capped at 1);
   `adverse` = the largest fraction of a G12 limit used; margin = min((restore - 0.5) / 0.5, 1 - adverse), in bands of
   0.05;
2. corridor band: median shared-prefix share of the primary redirects, in bands of 0.1;
3. behaviour changed from `baseline-v2`: pooled primary order divergence from `baseline-v2`, keeping candidates within 10%
   of the smallest;
4. simplicity, in the declared order of the table of section 3 (top first);

Exactly one candidate results. Rule identity, digest and parameters are then frozen for Part B.

## 9. Part A disposition (mechanical)

* `REPLAY_INVALID`: a fidelity requirement of section 5 failed; no candidate result is used, no engine.
* `NO_ENGINE_CANDIDATE`: no candidate passed every gate item; Sprint 14 stops without opening session 2791.
* `ENGINE_CANDIDATE_SELECTED`: at least one passed; the rubric's choice goes to Part B.

## 10. Part B, fixed now (operational details follow in the registration)

* **Card** (positions in order; H1 = candidate red against `baseline-v2` blue, H2 = candidate blue against `baseline-v2`
  red; C3 and C2 against the inert control in Sprint 10's seats): 1 to 8, 2130511121 H1, H2, H1, H2, H1, H2, H1, H2;
  9 2120531121 C3, 10 1930331196 C2, 11 1930331196 C3, 12 2120531121 C3, 13 1930331196 C2, 14 1930331196 C3; reserve
  15 and 16 (below). Runtime `baseline-v1-runtime-r2`, one worker, exclusive diagnostic sessions, serial.
* **Primary classes** (Sprint 12's frozen thresholds): a game is T9-v2-like when H1 red coverage < 0.6184027777777777 or
  H2 blue margin < 865, a collapse when H1 margin < -1,195 or H2 margin < 217. Interim after positions 1 to 4: STOP
  (tactical) if two or more collapses or all four T9-v2-like. After position 8: `RESTORED` if no collapse, at most one
  T9-v2-like game per seat and seat-averaged margin at least +130.5; `NOT_RESTORED` if two or more collapses or at
  least three T9-v2-like games in each seat; otherwise `PARTIAL`. `NOT_RESTORED` stops the screen before the adverse
  block.
* **Adverse classes** (Sprint 12's frozen thresholds): 2120531121 C3 `REPAIRED` (occupation 310 and margin >= 559),
  `PARTIAL`, `NOT_REPAIRED` (occupation < 310); 1930331196 C3 `AVOIDED` (all objectives and attack >= 78), `REGRESSED`
  (occupation < 310 or attack <= 61), else `AMBIGUOUS`; C2 likewise with 16 and 0. A configuration is FAVOURABLE when all
  its games are REPAIRED or AVOIDED, UNFAVOURABLE when all are NOT_REPAIRED or REGRESSED, else MIXED.
* **Reserve**: positions 15 and 16 run only if, after position 14 and with no stop, some configuration is MIXED; they
  replicate the first MIXED configuration in the order 2120531121 C3, 1930331196 C2, 1930331196 C3. Otherwise the screen
  ends at 14 sessions.
* **Immediate stops** (after every game): engine-installation integrity, ledger inconsistency, privacy exposure, contract
  error or incomplete game, candidate error, replay or reconstruction mismatch, capacity violation, a redirect the rule
  does not allow or that fails its arrival test, an invented move, a changed unrelated action, a project-gate rejection of
  a candidate-constructed move, an implementation that differs from the frozen files.
* **Designed-against tactical stops** (immediate): a 2120531121 C3 game that ends with an objective not own into which
  the candidate redirected a unit while, at a later decision, a claimant of that objective was held back because it was
  full; the first 1930331196 game of a configuration classified REGRESSED in which the candidate redirected at the first
  decision. A single ordinary loss is never a stop.
* **Dispositions** (first match): `ENGINE_SCREEN_STOPPED_STRUCTURAL` (an immediate stop attributable to the candidate);
  `ENGINE_SCREEN_INCOMPLETE` (an infrastructure stop); `PRIMARY_NOT_RESTORED` (interim stop or `NOT_RESTORED`);
  `PRIMARY_RESTORED_ADVERSE_FAILED` (`RESTORED` and an UNFAVOURABLE configuration or a designed-against stop);
  `PRIMARY_PARTIAL_ADVERSE_FAILED` (`PARTIAL` and the same); `READY_FOR_CONFIRMATORY_PROPOSAL` (`RESTORED` and every
  configuration FAVOURABLE); `PROMISING_NEEDS_REVISION` (anything else). Nothing in Sprint 14 promotes a baseline.
* **Unattended execution**: the registered controller runs only on the evaluation server, detached from any terminal;
  it may run the registered games serially, stop under these rules and write private records and logs, and never edits,
  commits or pushes anything. Public results are committed after the owner returns.

## 11. Outputs, privacy and tests

* Public (`evaluation/s14-redistribution-design/`): `inputs.json` (before the replay), `replay.json`, `adverse.json`,
  `gate.json` (regenerated byte for byte by `scripts/s14_design_replay.py run --check`) and `timing.json` (measured once).
  Every public file passes the forbidden-key check and a value check against every objective hex of the three
  scenarios; unit ids are excluded structurally (aggregates only, forbidden keys).
* Private (server, ignored `local/diagnostics/s14/`): redirect rows with units, hexes and decisions.
* Tests: `tests/test_t9_redistribution.py` (synthetic: v3 identity of stage 1, overflow only, held objectives, capacity,
  late claimants, inclusive detour, end-of-game and horizon boundaries, prefix boundaries, value and cost ranking,
  emission-order freedom of every rule, the batch assignment against brute force on 300 random instances, route and
  prefix invariants on a seven-objective shape, fresh-router identity, gate rejection, fail-closed, frozen rule table,
  trace and agent replay, static source checks); `tests/test_s14_design.py` (the gate, rubric and disposition on
  synthetic facts with planted threshold crossings); a server test regenerating the public files.
* Close-out: full non-engine suites on the workstation tree, a clean clone and the server private tree; historical
  documentation gates; the privacy scan compared with the accepted 103 hits as a set; a read-only ledger check.

## 12. Not claimed

Nothing in Part A is an engine result, a score estimate or evidence that any candidate improves anything: every figure is
a decision on a state another policy produced. Sprint 12's and Sprint 13's dispositions stand.
