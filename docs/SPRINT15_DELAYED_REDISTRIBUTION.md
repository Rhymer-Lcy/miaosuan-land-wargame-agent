# Sprint 15: stateful, event-triggered redistribution

**OFFLINE STUDY — PROTOCOL FIXED BEFORE ANY CANDIDATE WAS REPLAYED ON THE TARGET CORPUS — NO ENGINE SESSION**

Sprint 15 asks whether the primary benefit that T9-v1's redistribution was associated with requires redirecting at the
opening, and whether a deterministic, seat-local rule with memory can restore the later redistribution without
recreating the adverse mechanisms of Sprint 10. It opens no engine session: the ledger stays closed through session 2790
and session 2791 is not opened. If a candidate passes the gate of section 7 with every adverse configuration tested
(section 8), the sprint stops and reports to the owner before any engine use; if none does, it closes offline. Dates are
business dates in UTC+8; this protocol was written on 2026-10-06.

Sections 1 to 12 are the protocol. They are committed and pushed, with the candidate module, its tests, the analysis
module, the replay driver, the reference diagnostics and the input digests, before any candidate decision is computed
on the target corpus, and they are not edited afterwards; results follow in a separate section.

## 1. Starting state and fixed results

| Item | Identity |
|---|---|
| Repository | `main` `c83fe0fc6ea5bfa59972883501d4a2cea24cad91`, tree `0eb6ec80e9c196396b3af7fbdcc45a84a155aad2`, identical on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,790 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `e2116700df7645f7c116386bfb4b955cb2725f1541ba24f906fafe9172891cef`; session 2791 never opened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| T9-v1 | policy source `0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa` |
| T9-v2 | policy source `66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece` |
| T9-v3 | policy source `9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8` |
| Privacy baseline | the 104 hit lines accepted at Sprint 14's close (the 104th is the benign corridor share 123/317 in `evaluation/s14-redistribution-design/replay.json`), compared as a set of lines; the starting scan reproduced that set exactly |

Fixed and not re-litigated: Sprint 12 `NOT_PRESERVED_IN_PRIMARY`, Sprint 13 `REDISTRIBUTION_DOMINANT`, Sprint 14
`NO_ENGINE_CANDIDATE`. Sprint 9's +305.47 is T9-v1's registered result alone. None of the frozen policies changes.

## 2. Evidence status and scope

* All evidence is historical and has been used for development before: the four Sprint 12 primary games (sessions 2787
  to 2790), the six Sprint 10 diagnostic captures (sessions 2773 to 2778), the eight Sprint 10 T9-v2 exploratory games
  (sessions 2779 to 2786, compact captures only), and the H0 replay corpus (eight `baseline-v0` mirror games). **None of
  it is an untouched holdout**; leave-one-out checks are robustness diagnostics, not validation. BOKE-2026 is not used.
* Every candidate figure is a decision on a state another policy produced. A candidate's memory is simulated over the
  recorded observation stream (its own counterfactual memory); the world's response to its actions is never invented.
* A candidate that resembles T9-v1 on these states is not evidence that it recovers T9-v1's +305.47.
* Doctrine: deterministic, hierarchical, seat-local; no learning, no online model; no future information; no scenario,
  unit, objective or coordinate special case; no rule keyed on the decision index.

### 2.1 External research (conceptual only)

Generic searches, with no private data sent: event-triggered multi-robot task reallocation with a dead-zone hysteresis
and an assignment-change penalty to limit churn (arXiv 2603.14622; an event-triggered consensus allocator on
ResearchGate 403642079); plan repair against replanning, which keeps a valid plan stable and repairs only the part an
event made stale (Fox, Gerevini, Long and Serina, ICAPS 2006); online matching with bounded recourse (arXiv 2001.03107,
2609.19001); the value of delaying an assignment in dynamic routing (ScienceDirect S0191261525002309). Ideas borrowed,
none copied: triggers on events rather than on cost differences (families A, C, D), hysteresis (family C), repair of the
stale part only (stage 1 is never re-solved), and at most one reassignment per episode (bounded recourse). No external
code enters the repository.

## 3. What the diagnostics show (reference policies only)

`scripts/s15_delayed_replay.py diagnose` decides `baseline-v2`, frozen T9-v1, frozen v3, Sprint 13's O2 and Sprint 14's
batch rule on the ten captures (Sprint 14's pinned inputs, which still hold) and writes
`evaluation/s15-delayed-redistribution/diagnostics.json`, committed before this protocol. No candidate is decided there.
"Opening" is the first decision with an own ground move (decision 1 in every capture), an experimental label only.

1. **Opportunity after the opening.** On the primary states the post-opening redistribution of T9-v1 involves 15
   distinct units as red (p01 14, p03 1) and 26 as blue (13 and 13); O2 has the same counts. Most of it re-redirects
   units that already overflowed at the opening (T9-v1: 155 of 162 redirects in p01, 155 of 212 in p02, 13 of 15 in
   p03, 189 of 256 in p04), repeated at every decision while v3 holds them. The first post-opening O2 opportunity comes
   at decision 460 (p01), 162 (p02, p04) and 581 (p03).
2. **On-policy prefix.** On the primary states a delayed rule behaves exactly like v3 until its first redirect, so the
   recorded v3 games are its own trajectory up to that decision. In p03 that is decision 581 (step 580), after
   Sprint 13's first ownership divergence from T9-v1's characteristic pattern (step 550): there, no delayed rule can
   differ from v3 before the divergence. This is a description of action opportunity, not a score inference.
3. **Adverse trajectories cannot exercise a staging-based trigger.** Neither adverse trajectory ever staged the
   opening overflow (one is T9-v1's, which redirected it, the other `baseline-v2`'s, which sent it on). In 1930331196 C3
   no unit has a post-opening O2 opportunity on either trajectory; no shooter has one before its firing decision on
   either trajectory; the two shooters that overflowed at the opening (firing decision 841) have 141 overflow claims
   before firing on the T9-v1 trajectory, none after the opening with an admissible alternative. In C2 the shooter
   (decision 611) never claims before firing; O2 redirects 8 times after the opening on the `baseline-v2` trajectory
   and once on the T9-v1 trajectory.
4. **Geometry from v3's first staging hexes.** From the staging endpoint of every decision-1 overflow unit, with
   ownership and capacity ignored (a necessary condition only), no other objective lies within twice the cost to the
   unit's own objective in 1930331196 C3 (4 units), C2 (7) and 2120531121 C3 (4), and none as red (12); as blue, 7 of 18
   have one. A same-source redirect after a completed staging move is therefore impossible in every adverse
   configuration; a later redirect needs a change of target.
5. **A staging-hex proxy is not calibrated.** Pinning the decision-1 staged units at their staging hexes on the recorded
   objective states predicts the step of their first re-claim well (11 of 12, 9 of 18, 9 of 10 and 14 of 18 on the
   primary games) but classifies that claim as a redirect opportunity or not correctly for only 4 of 12, 13 of 18, 9 of
   10 and 13 of 18 known answers. Its adverse outputs are therefore hypotheses and gate nothing.
6. **T9-v2's own staging games.** In both 1930331196 C3 games T9-v2's withhold episodes include two units that fire at
   decision 876 in the `baseline-v2` game, withheld from decision 721 (155 decisions before), when one objective
   remained unheld on the `baseline-v2` trajectory: no alternative can exist then. In C2 no shooter was withheld before
   firing. These are on-policy staging trajectories, but only their episode summaries were captured.
7. **State features.** Among post-opening O2 opportunities (first per unit), the nearest seen enemy is 0 to 3 hexes as
   red and 2 to 10 as blue in the primary games, 25 in C2 and 17 to 20 in 2120531121 C3; a one-predicate search
   separates them (nearest seen enemy at most 10), but leaving C2 out yields a rule that admits all 7 C2 rows, and the
   distance is confounded with the opponent (the adverse games are against the inert control). At the opening no
   enemy is seen in any configuration; the best opening rule (detour ratio at least 1.125 and value ratio at most 1.0)
   admits none of the held-out primary seat's rows when that seat is left out. No rule from the search is shipped. The
   search was run after exploratory looks at the same rows; it is disclosed as diagnostic only.

## 4. Candidates

All candidates are in `src/miaosuan_agent/experiments/t9_delayed.py`, an add-on to the frozen `baseline-v2` through the
unchanged exploratory wrapper; identity `t9-<rule>-v5`; policy-source identity (`baseline-v2`'s sources, the wrapper,
the frozen `t9_batch.py` and `t9_redistribution.py`, and the module) recorded in `inputs.json`. No candidate is in any
run card.

**Allocation.** Exactly Sprint 14's `feasible-value-redirect` (= O2) with one change: an overflow claimant may be
redirected only if its trigger holds. Stage 1 (v3), admissibility (objective not held, fewer than four counted places
including this decision's redirects, route cost at most twice the cost to the own objective, free-flow arrival before
`max_step`), ranking (cost / value, cost, hex) and claimant order (v3's rank) are unchanged. With no claimant eligible
the module equals v3, with every claimant eligible it equals O2; both identities are checked at every replayed
decision.

**Memory** (one record per own ground unit, integer pairs in the wrapper's add-on state):

| Event (observed at a decision) | Effect |
|---|---|
| unit absent, moving to an objective, or standing on one | record deleted |
| stage 1 gives the unit a place, or it claims while it cannot arrive before the end | record deleted |
| source objective held by the side | episode ends (source, count, alternative, saturation, redirect flag, start cleared); staging facts kept |
| unit stands with no path on the endpoint of a staging move the add-on emitted | `done` = 1 |
| overflow at a source other than the episode's | new episode (count 1, start step, redirect flag 0); staging facts kept |
| overflow at the episode's source | count + 1 (capped at 1,000) |
| after any overflow observation | best admissible alternative and source saturation (four standing units, no counted mover) recorded |
| staged | staging endpoint and its source recorded, `done` = 0 |
| redirected | redirect flag 1: no further redirect in this episode |

**Rules** (declared order of simplicity):

| Rule | Family | Trigger for an overflow claimant |
|---|---|---|
| `delayed-repeat-2` | A, first-overflow deferral | at least the 2nd overflow observation of the episode |
| `delayed-repeat-3` | A | at least the 3rd |
| `delayed-stable-alternative` | C, hysteresis | the same best admissible alternative as at the previous overflow observation of the episode |
| `delayed-post-stage-same` | B, post-staging | the unit completed a staging move the add-on emitted toward this same source |
| `delayed-post-stage-any` | B | the unit completed a staging move the add-on emitted (any source: a deferred unit available again after re-targeting) |
| `delayed-saturated-source` | D, event-triggered repair | the source is saturated by standing units now and was at the previous overflow observation of the episode |

At the first decision every memory is empty, so no rule can redirect there; this is a consequence of the memory, not a
decision-index rule. No trigger reads a unit id, coordinate, scenario or decision index.

## 5. Target corpus and replay

* **Primary**: the four Sprint 12 games, every decision of the v3 seat. **Adverse**: the six Sprint 10 captures, every
  decision of the diagnosed seat. **Generalisation (H0)**: both seats of the eight replay-corpus games, `baseline-v0`
  reproduced and `baseline-v2` reconstructed sequentially. Every file is pinned by SHA-256 in `inputs.json`.
* On every decision `baseline-v2` is re-decided from the captured memory; T9-v1, v3, O2, the batch rule and the six
  candidates are decided on its actions, each candidate with the memory it produced at the previous decision, starting
  empty at the first decision of each capture and seat.
* **Fidelity** (any failure: `REPLAY_INVALID`): Sprint 14's requirements (re-decided `baseline-v2` and trace equal the
  capture; the played policy equals the submitted actions; v3 equals the captured allocation; T9-v1 equals Sprint 10's
  audit; Sprint 13's figures 162, 212, 15 and 256 redirects, 346, 268, 49 and 394 emitted moves, 18, 22, 14 and 22
  units, 14, 19, 14 and 19 first-decision redirects, pooled slot divergence 550 (v3) and 222 (O2), order divergence 913
  and 337, O2's 645 orders and 637 redirects; the adverse anchors 564, 9,194, firing decisions 742, 804, 841, 876 and
  611, T9-v1's 12 and 7 first-decision redirects); the module's v3 and O2 identities at every decision; every capture's
  first decision with an own ground move is decision 1.
* **Invariant checks** per decision (Sprint 14's `candidate_checks`, independent of the candidate's bookkeeping, plus
  memory): determinism (a fresh router, the same memory in: identical actions, allocation and memory out), order
  invariance (three reorderings of `baseline-v2`'s actions at every decision with two or more claimants: identical
  allocation, per-unit moves, unrelated actions in order, and memory out), memory bounds (decodes cleanly, records only
  for present own ground units, no empty record, fields in range, at most the declared fields).

## 6. Metrics

Per policy and capture: redirects by bucket (first decision, next 5, next 20 and later decisions with an own ground
move), distinct redirected units, post-opening distinct redirected units (decisions after the first), forms (keep,
redirect, stage, withhold), slot divergence from T9-v1 over all decisions and after the first, order divergence from
`baseline-v2`, T9-v1, v3 and O2. Per candidate also: oscillations (a unit redirected from B back to A after having been
redirected from A to B), the largest number of redirects of one unit in one game, trigger observations, records ended
by reason, the episode count and steps in episode at each redirect, the largest number of records, and on the adverse
captures the trigger exposure (overflow observations at which the trigger held) and the memory state of each shooter
at every decision before its firing decision. 2120531121 C3: unreachable places, v3 selections not kept, the Sprint 11
certificate (unit-decisions from decision 442 of the T9-v1 game in which a claimant T9-v1 held back is admitted), and,
descriptively, Sprint 14's registered far-reservation count. Latency per decision with an own ground move, measured
once (`timing.json`).

## 7. Gate (every item must hold)

| Item | Requirement |
|---|---|
| G1 deterministic | no difference in actions, allocation or memory out under a fresh router (target corpus and H0) |
| G2 seat-local | the module imports no analysis or engine code; `allocate`'s inputs are the observation, seat, faction, `baseline-v2`'s actions, the router, the rule, the memory and the identity switch (static) |
| G3 order invariant | no difference under the three reorderings, memory out included (target corpus and H0) |
| G4 capacity | no objective above four counted places where a place is added |
| G5 unrelated actions | none changed, none reordered |
| G6 no invented move | none |
| G7 engine-supported moves | every redirect is `baseline-v2`'s candidate route to an unheld objective within the detour bound; every other changed move a strict same-route prefix off objectives; no candidate error, no gate rejection |
| G8 reachable | no place for a unit whose free-flow arrival is not before `max_step` |
| G9 memory | no memory-bound problem at any decision |
| G10, G11 | no future information (as G2); no numeric literal beyond the declared constants (static) |
| G12 latency | 99th percentile at most 20 ms, maximum at most 200 ms |
| R1 no opening redistribution | zero redirects at the first decision of every capture (primary and adverse) |
| R2 post-opening restoration | per seat, post-opening distinct redirected units at least max(4, ceil(0.5 x T9-v1's)) = 8 as red, 13 as blue |
| R3 divergence | pooled post-opening slot divergence from T9-v1 at most 0.70 x v3's; each seat's below v3's |
| R4 bounded recourse | no oscillation and at most 3 redirects of any one unit in one game (primary and H0) |
| A1 1930331196 | C3 and C2: no shooter redirected before its firing decision (either trajectory); first-decision redirects at most floor(T9-v1's at the first decision of its own game / 3) (4 and 2); redirects before the first firing decision on the `baseline-v2` trajectory at most floor(T9-v1's there / 3) (4 and 5) |
| A2 2120531121 C3 | no unreachable place, every v3 selection kept, certificate unit-decisions at least v3's 9,194 |

Thresholds are `GATE` in `src/miaosuan_agent/evaluation/s15_delayed.py`, recorded in `inputs.json`.

Changes from Sprint 14, stated before the replay:

* Sprint 14's G9 (first-decision redirects at least half T9-v1's) is replaced by R1 and R2, because whether those
  redirects are necessary is the question; "material" is R2's per-seat count, reported against T9-v1's post-opening
  redistribution on the same states.
* R4 replaces a churn measure by recourse: the orders a rule changes from `baseline-v2` are the same for every rule
  built on v3's stage 1 (it keeps v3's selections and changes exactly the overflow orders: 1,331 on the primary
  states for v3, O2 and a never-firing rule alike), so that measure could not fail. Found by the smoke run of section
  12 before the freeze.
* Sprint 14's G11 far-reservation clause (a redirect into the missed objective issued before step 563 and arriving
  after it) is reported but does not gate. The diagnosed failure was places held by units that could not arrive before
  the end of the game (3,168 to 3,456 steps in a 2,880-step game), blocking faster claimants for the rest of it; G8 and
  A2's "no unreachable place" forbid exactly that, and v3's ranking removes emission order. Sprint 14's clause counted
  100-to-160-step vehicles sent into an objective whose places were held only by unreachable movers on the T9-v1
  trajectory, which is the repair, not the failure.

## 8. Adequacy of the adverse evidence

An adverse configuration's result is **TESTED** for a candidate only if the candidate's trigger held for at least one
overflow observation in that configuration's risk window on either trajectory: before decision 876 (1930331196 C3, the
last firing decision), 611 (C2) and 564 (2120531121 C3, the `baseline-v2` capture). Otherwise it is **UNTESTED**,
whatever A1 and A2 say: a trigger that never held on these trajectories shows nothing about the trajectory the
candidate itself would produce (section 3, items 3 to 6).

## 9. Selection (only among candidates that pass every item with every configuration TESTED)

Lexicographic, each step keeping the best band: (1) adverse margin, 1 minus the largest fraction of an A1 limit used,
in bands of 0.05; (2) restoration margin, the smaller per-seat ratio of post-opening units to R2's requirement minus 1,
in bands of 0.05; (3) pooled post-opening slot divergence from T9-v1, within 10% of the smallest; (4) recourse, primary
redirect order-decisions, within 10% of the smallest; (5) the declared order of simplicity. Exactly one candidate
results.

## 10. Disposition (mechanical, first match)

1. `REPLAY_INVALID`: a fidelity requirement failed.
2. `NO_DELAYED_REDISTRIBUTION_OPPORTUNITY`: in a seat, even O2's post-opening distinct redirected units (the most any
   delayed rule can restore on these states) are below R2's requirement.
3. `OFFLINE_CANDIDATE_SELECTED`: a candidate passes every item and every adverse configuration is TESTED; the rubric's
   choice is reported to the owner in a pre-engine review, and nothing runs before the owner's authorization.
4. `MECHANISM_AMBIGUOUS`: a candidate passes every item but some adverse configuration is UNTESTED.
5. `NO_STATE_DISCRIMINATOR`: a candidate passes the invariants and the restoration items, and every such candidate fails
   an adverse item.
6. `NO_RESTORING_TRIGGER`: no candidate passes the invariants and the restoration items.

## 11. Outputs, privacy and tests

* Public (`evaluation/s15-delayed-redistribution/`): `diagnostics.json` (before this protocol), `inputs.json` (before
  the replay), `replay.json`, `adverse-<configuration>.json` (three), `generalisation.json`, `gate.json` (regenerated
  byte for byte by `run --check`) and `timing.json` (measured once). Every public file passes the forbidden-key check
  and a value check against every objective hex; unit ids are excluded structurally; memory appears only as aggregate
  metrics.
* Private (server, ignored `local/diagnostics/s15/`): redirect rows, exposure rows, shooter identities.
* Tests: `tests/test_t9_delayed.py` (synthetic sequences: v3 and O2 identities, every trigger on and off, completed and
  incomplete staging, capture of the source, absence, place given, bounded recourse, no oscillation, memory bounds,
  codec and malformed state, emission and operator order, fresh router, capacity with same-decision redirects, fail
  closed, wrapper and agent replay with memory, reset between games, static source checks); `tests/test_s15_delayed.py`
  (gate items with planted crossings and boundaries, adequacy, rubric, disposition order, rule search with leave-one-out,
  oscillations, memory bounds); a server test regenerating the public files.

## 12. Validation before the freeze, and what is not claimed

* A private smoke harness (`local/diagnostics/s15/smoke_run.py`, server) ran the complete `run` path on the target
  corpus and H0 with the candidate table replaced by one rule that can never fire, to find crashes; it equals v3 by
  construction, and its outputs matched v3's on every aggregate (a known-answer check of the plumbing). No real
  candidate was decided on a captured state before this protocol was pushed. The smoke run found three plumbing
  defects (a default argument bound at definition time, a public key the privacy check forbids, a digest of a missing
  file) and the constant churn measure (section 7).
* Not claimed: any engine outcome, score, or effect; that a candidate passing offline would restore T9-v1's primary
  advantage; that any adverse configuration is safe beyond what its recorded trajectories can show.
