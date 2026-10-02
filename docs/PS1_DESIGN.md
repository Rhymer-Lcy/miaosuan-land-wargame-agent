# PS-1 capacity-aware movement: design study

**DESIGN STUDY.** No engine session, no production policy, no registration, no promotion. This document is the
protocol and the record of an offline study of a capacity-aware movement rule for `baseline-v2`'s play stage,
motivated by the stacking-limit deadlock diagnosed in `docs/T1R_DIAGNOSIS.md`. Sections 1 to 10 were written and
pushed before any counterfactual quantity was computed; section 11 onwards is written afterwards and says so. Times are
UTC+8.

## 1. Questions

1. Which movement, occupancy, path and command-execution facts can a seat actually observe?
2. Which observable conditions suffice to detect, or to anticipate, the blocking configuration of `docs/T1R_DIAGNOSIS.md`?
3. Can a legal alternative sequence release the blocked units without breaking the stacking limit or using information
   a seat does not have?
4. What is the smallest defensible PS-1 rule, and which uncertainties need a live engine test?
5. What registered experiment would separate PS-1's effect from the deployment-split policy that exposed the problem?

## 2. Evidence already seen (disclosure)

Before this protocol was written, the following had been read; none of it is a counterfactual quantity.

* `docs/T1R_DIAGNOSIS.md` and `evaluation/t1r-diagnosis-1/analysis.json` (public aggregates of the two Sprint 2 games).
* The private per-unit trajectory listing of those two games (Sprint 2, `local/diagnostics/t1r/`): every own unit's
  orders, hex-change steps and stall periods, with the `can_to_move`, `flag_force_stop`, `stop` and `move_state` fields
  at the start of each stall.
* One Sprint 1 smoke snapshot in which units with a move in progress had only action 10 listed in `valid_actions`.
* The platform's published rules on movement, stopping and stacking, and the project's action catalogue
  (`src/miaosuan_agent/decision/semantics.py`).
* The schemas, not the contents, of the pinned replay corpus (`evaluation/routing-remediation-1/corpus.json`).

The captures of `baseline-v2-target-ownership-prevalence-1` stay unexamined, as that study's report requires; they are
not used here.

## 3. The documented contract

From the platform's published rules (paraphrased) and the project's catalogue:

| Id | Rule | Source |
|---|---|---|
| C1 | An issued move order cannot be changed. A stop order (action 10) may be issued; the unexecuted remainder of the move is then dropped. | platform movement rules |
| C2 | On a stop order a moving unit first completes the hex it is moving into, then serves a 75-second move-to-stop transition during which it can take no action. | platform movement rules |
| C3 | At most four own ground units may stand in one hex; a hex already holding four own ground units cannot be entered or passed through by another own ground unit. | platform stacking rule |
| C4 | The cost graph supplied at setup gives, per movement mode, the cost of entering each neighbouring hex, defined as the mode's maximum speed divided by the current speed. | platform map reference |
| C5 | One engine step is one second of game time (`time.tick` 1.0); a game has 1,800 steps. | observation `time` |
| C6 | The project gate catalogues actions 1, 2, 5 and 333 only; action 10 is not catalogued, so any rule that emits it carries its own check, as the deployment-split candidate did for action 314. | `semantics.py`, `gate.py` |
| C7 | `baseline-v2` never orders a unit whose move path is non-empty ("already moving"). | `decision/candidates.py` |

The rules do not say how a unit that cannot enter a full hex is represented while it waits (at its hex centre, or
"moving into" the full hex), so C2's "first completes the hex it is moving into" is undetermined for a blocked unit.

## 4. Formal model

Notation for one seat, one engine step `t`, own ground units `u` (not on board):

| Term | Definition | Observable? |
|---|---|---|
| occupancy `occ_t(h)` | number of own ground units whose `cur_hex` is `h` | derived from observed `cur_hex`, `on_board` |
| full hex | `occ_t(h) >= K`, `K = 4` (C3) | derived |
| outstanding order | the unit's `move_path` is non-empty; `move_path` is the engine's remaining path, first element the next hex | observed (the shrinking of the path is to be audited, O2) |
| next-hex demand | `nh_t(u) = move_path_t(u)[0]`; `demand_t(h)` = number of units with `nh_t(u) = h` | derived |
| final destination | `fd_t(u) = move_path_t(u)[-1]` | derived |
| objective assignment | the objective the policy chose for the unit (for `baseline-v2`, its move's final hex) | policy-internal |
| transit hex | a hex on a unit's remaining path other than its final destination | derived |
| expected hex time | `tau(u, h) = (720 / basic_speed(u)) * cost(mode(u), cur_hex(u), h)` seconds, `basic_speed` in km/h; the 200 m hex size is inferred from the observed 20 s and 144 s per hex at 36 and 5 km/h | model, from C4; to be validated (O5) |
| progress | `last_t(u)`: the latest step at or before `t` at which `cur_hex(u)` changed (or the order was issued) | derived from a history the policy keeps |
| stall age | `s_t(u) = t - last_t(u)` while the order is outstanding | derived |
| stalled | `s_t(u) > 2 * tau(u, nh_t(u)) + 10` | derived; the threshold is declared here, not tuned |
| blocked by capacity | outstanding order and `nh_t(u)` is a full hex | derived |
| holder | a unit with no outstanding order in a full hex (it will not leave unless ordered) | derived |
| waiting location | a hex where a unit stands while blocked; its spare capacity is `K - occ_t(h)` | derived |
| occupied vs reserved | a hex is occupied by units standing in it; it is reserved (by the policy) for units ordered to end their move in it | occupied: derived; reserved: policy state |

Wait-for graph `W_t`: one node per own ground unit; an edge `u -> v` when `u` is blocked by capacity and `v` stands in
`nh_t(u)`. A **deadlock** is a non-empty set `D` of blocked units such that every unit standing in the next hex of a
unit of `D` is either in `D` or a holder: without an intervention no unit of `D` can ever move (under C3, and assuming
no other own unit leaves those hexes, which holds when none of them has an order). A deadlock is **cyclic** when `W_t`
restricted to `D` contains a cycle (two groups waiting for each other's hexes, as in Sprint 2), and a **chain** when it
ends at holders. Final-destination reservation is not route capacity: four units with one destination can still fill a
transit hex that a fifth unit's path needs.

## 5. Observation audit (method fixed now, results in section 11)

Each policy input is classified as: (1) directly observed, (2) reliably derived from observed state, (3) available only
in private diagnostic records, (4) unknown, (5) not seat-observable. Only classes 1 and 2 may enter a decision rule.

| Id | Input | Method |
|---|---|---|
| O1 | own units' `cur_hex`, `on_board`, `type`, `basic_speed` in the seat observation | compare the seat observation with the all-seeing state at every step of both Sprint 2 games |
| O2 | `move_path` is the remaining path and shrinks by one hex per hex change | check every hex change of every own unit in both games |
| O3 | `valid_actions` for a blocked unit: is action 10 listed, is action 1 absent | read the seat observation at every blocked unit-step |
| O4 | `can_to_move`, `flag_force_stop`, `stop`, `move_state`, `speed`, `stationary_count` as blockage indicators | tabulate their values on moving, blocked and stationary unit-steps; usable only if they separate the classes without exception |
| O5 | the hex-time model `tau` | predict every observed hex change of both games from the cost graph and compare |
| O6 | stacking count from observed positions predicts every observed refusal to enter (a unit waits exactly when its next hex is full) | check every waiting unit-step and every entry |
| O7 | command acceptance of action 10 on a blocked unit, its effect on position, the penalty, and the re-listing of action 1 | not answerable from the captures (no stop was ever issued); class 4 |
| O8 | the engine's processing order when several units enter one hex in the same step | not answerable from the captures; class 4 |

## 6. Engine behaviour hypotheses (not facts)

| Id | Hypothesis | Status until a probe |
|---|---|---|
| E1 | action 10 is listed for, and accepted from, a unit blocked by capacity | unverified |
| E2 | a stop on a blocked unit takes effect at its current hex (it does not need to enter the full hex first) | unverified; C2 leaves it open |
| E3 | after the 75-second transition, action 1 is listed again and a new move is accepted | unverified for this case |
| E4 | a unit in the move-to-stop transition still counts toward the stacking limit of its hex | unverified (plausible from C3) |
| E5 | when several units may enter a hex with fewer free places than entrants in one step, the engine admits them in a fixed order | unverified |

## 7. Candidate alternatives and evaluation criteria

* **PS-1A capacity-aware dispatch.** Before issuing a move to a unit without an order, limit the demand on capacity:
  at most `K` units with a common final destination or a common transit hex within the next `w` hexes, counting units
  standing in, ordered through, and already waiting for that hex; units beyond the limit are held (no order this step)
  or routed by an alternative path whose hexes are not saturated. It uses only actions the baseline already emits
  (action 1 to units without an order).
* **PS-1B stalled-movement recovery.** Detect a unit that is stalled and blocked by capacity, find the wait-for
  dependency, and if it is a deadlock, stop (action 10) the fewest units that break it and, after the transition,
  re-order them by a path or to a waiting hex that does not recreate the dependency; at most one recovery per unit per
  window, and never towards a hex that would be full on arrival under the model.
* **PS-1C dispatch plus recovery.** Both, if and only if neither alone is sufficient and the two cannot be tested
  separately.

Each is evaluated for: observability; correctness conditions; prevention capability; recovery capability; risk of
suppressing necessary movement; risk of oscillation or repeated commands; dependence on unverified engine behaviour
(E1 to E5); computational cost per decision; compatibility with `baseline-v2` (it must make the same decisions when its
trigger is absent); applicability to unsplit forces and other scenarios.

## 8. Offline counterfactual method

Evidence levels: **observed** (present in a capture), **model-derived** (follows from the listed assumptions), and
**unverified** (an engine response or trajectory a capture cannot supply). After the intervention point no recorded
transition of the original game is reused as if the counterfactual had produced it.

Model assumptions for the simulator (`scripts/ps1_study.py` with `src/miaosuan_agent/evaluation/ps1_model.py`):

| Id | Assumption |
|---|---|
| M1 | a unit enters its next hex `tau(u, h)` steps after entering its current hex (or after its order), rounded to whole steps, if that hex is not full at that step; otherwise it waits at its current hex and retries every step |
| M2 | entries within one step are processed in ascending unit index; occupancy is updated after each entry (E5 is unverified) |
| M3 | a stop order on a blocked unit leaves it in its hex; it may be re-ordered 75 steps later (E1 to E4 assumed; unverified) |
| M4 | the opponent never moves (true in the Sprint 2 games: the inert control issues no unit action) and enemy units do not count toward own stacking (C3 says own units) |
| M5 | occupation is instantaneous once a unit stands on an unheld objective (rules) |
| M6 | movement modes, costs and roadblocks are those of the setup cost graph and the observation |
| M7 | after an intervention, own units are ordered by a stated surrogate of `baseline-v2`'s movement and occupation rules: a unit without an outstanding order that stands on an unheld objective occupies it (one occupation per objective per step); otherwise it is ordered along the cheapest path (setup cost graph, roadblocks excluded for vehicles) to the cheapest unheld objective, ties by lower hex; a unit with an outstanding order is never re-ordered except by the PS-1 intervention under study |

Simulator fidelity is a precondition, at two levels, on both Sprint 2 games from their first play step with no
intervention:

* F1: replaying the recorded orders, the simulator reproduces every observed hex change of every own unit within one
  step, and the deadlock (same hexes, same units, formation step within one step);
* F2: replacing the recorded orders by the M7 surrogate, the simulator reproduces the recorded orders (step within one
  step, same final hex) and again every hex change and the flag changes.

If F1 fails, no counterfactual is reported as model-derived feasible and G3 fails; if only F2 fails, continuations that
need re-ordering after the intervention are reported as unresolved.

Alternatives analysed from the observed state at their start point (never a later, more favourable one):

| Id | Intervention | Start point |
|---|---|---|
| A1 | prevent conflicting dispatch (PS-1A) | the first play decision of the split game |
| A2 | reroute the waiting column to a legal waiting hex, then on | first detection of the deadlock |
| A3 | redirect the units occupying the nearer objective by a path avoiding the full neighbour | first detection of the deadlock |
| A4 | sequence the groups (one group moves while the other holds) instead of simultaneous orders | the occupation of the nearer objective |
| A5 | recovery after the block has persisted (PS-1B at a later detection) | detection plus 300 and plus 900 steps |
| A6 | failure witnesses: synthetic maps with no legal waiting hex or bypass | synthetic |

Each alternative produces a machine-readable certificate or failure witness (private on the server, sanitised summary
public): start observation and assumptions; command sequence; the observed inputs used; capacity constraints checked at
every modelled step; predicted occupancy and wait-for graph; whether the original cycle is broken; whether every
affected unit reaches its destination or a stable hex before the game ends under the model; the assumptions (M and E
ids) a prospective test must still validate. Infeasible and unresolved cases are reported.

## 9. Decision gates (fixed before any counterfactual output)

| Gate | Passes only when |
|---|---|
| G1 evidence integrity | two independent channels (the all-seeing state and the seat observation, plus the observation's own score counters against the city flags) reconstruct the Sprint 2 failure as diagnosed (ten vehicle units, a full objective hex, a full neighbour, the reciprocal next hexes, no progress to the end, the 80-point objective never occupied); the input files' SHA-256 digests are unchanged before and after the study; the analysis passes its real-record cross-checks (capture against record counts) |
| G2 observable intervention | the selected intervention uses only class 1 and 2 inputs and actions documented in the contract; an intervention that depends on E1 to E4 cannot pass on documentation alone |
| G3 offline feasibility | the simulator passes its fidelity check, and a reproducible certificate shows a capacity-consistent sequence that breaks the cycle and leaves every affected unit with a feasible continuation and no new unresolved conflict within the modelled continuation; feasibility is not engine execution or efficacy |
| G4 generalisation and non-interference | over the historical observations available (the Sprint 2 baseline game, the 8-game pinned replay corpus with both seats at every decision, the Sprint 1 smoke snapshots), the trigger never fires where its condition is absent, and every firing on ordinary movement is investigated and explained; no claim of broad generalisation from one scenario |
| G5 disposition | exactly one of READY_FOR_PROSPECTIVE_VALIDATION (G1 to G4 pass), NEEDS_ENGINE_PROBE (a named engine behaviour blocks G2 or G3; the smallest probe is specified), REVISE (a correctable requirement fails), SHELVE (no intervention survives) |

Each gate is reported separately; a plausible design does not override a failed gate.

## 10. Literature (context, not engine evidence)

* Coffman, Elphick and Shoshani (1971), System Deadlocks, ACM Computing Surveys 3(2): deadlock requires mutual exclusion,
  hold-and-wait, no preemption and circular wait. The Sprint 2 block has all four: capacity (C3), units hold their hex
  while waiting, an issued move cannot be changed (C1), and two groups wait for each other's hexes. Breaking any one
  condition prevents it; PS-1A attacks hold-and-wait through admission, PS-1B attacks no-preemption through the stop order.
* Reveliotis (2000), Conflict Resolution in AGV Systems, IIE Transactions 32(7): zone capacity control to avoid deadlock
  among guided vehicles; the transferable idea is admission control on finite-capacity zones, the guarantee depends on a
  known, fixed guide-path network and full control of every vehicle.
* Ma, Li, Kumar and Koenig (2017), Lifelong Multi-Agent Path Finding for Online Pickup and Delivery Tasks, AAMAS:
  agents repeatedly plan around the paths others have already committed to; its completeness argument relies on well-formed
  instances with parking endpoints, which a wargame map with objectives under fire does not guarantee.
* Li, Tinka, Kiesel, Durham, Kumar and Koenig (2021), Lifelong Multi-Agent Path Finding in Large-Scale Warehouses, AAAI:
  rolling-horizon collision resolution that resolves conflicts only within a bounded window and replans periodically;
  results are empirical, and windowed planning can still deadlock beyond the window.
* Chen, Harabor, Li and Stuckey (2024), Traffic Flow Optimisation for Lifelong Multi-Agent Path Finding, AAAI: guide
  agents along congestion-avoiding paths; the transferable idea is to price congestion into route choice; results are
  empirical.

None of these assumes this game's mechanics (stop penalty, one-way commitment of a move, simultaneous execution by an
opaque engine); they inform the design, they do not certify it.

## Amendment 1 (2026-10-02, written after the fidelity check failed and before any counterfactual was computed)

**What failed.** Fidelity F1 for the registered model (assumption M1) failed on the split game: every own unit's hex
sequence matched the capture and the deadlock was reproduced, but four units entered some hexes 19 steps earlier in the
model than in the game (worst offset 19 against the allowed 1). On the baseline game F1 and F2 both passed with no
offset at all. By section 8, no counterfactual is reported as model-derived feasible under M1, and G3 cannot pass on M1.
The failure stays on record.

**Why (private captures).** Those four units had reached the end of a hex time in front of a full hex; they then stood
at their hex centre with the observation's `speed` field at 0, and entered a full hex time after the hex had room again
(room at one step, entry 19 steps later at a 20-step hex time). Units following a column that leaves the hex in the same
step never wait, and no hex ever held more than four own ground units, so units in transit reserve no place.

**Assumption M1b**, replacing M1: a unit whose hex time ends in front of a full hex stops at its hex centre (waiting);
in the first step its next hex has room it starts the traversal again and enters a hex time later, counting that step
(`tau - 1` steps after it). Everything else is unchanged. M1b was derived from the same two games it must reproduce, so
fidelity under M1b on those games is not independent evidence.

**Independent check of M1b (fixed now, computed afterwards).** Over the pinned replay corpus (8 games under condition
C1, both seats, every decision; `baseline-v0` policy), every episode in which an own ground unit with a move path stands
with `speed` 0 in front of a hex holding four own ground units, keeps the same path, sees that hex have room at some later
step, and then enters it. With `d` = entry step minus the first step with room: M1 predicts `d` in {0, 1}; M1b predicts
`|d - (tau - 1)| <= 1`. M1b is supported if there are at least 10 episodes, at least 90% of them fall in the M1b window,
and at most 10% in the M1 window. With fewer than 10 episodes the check is insufficient.

**G3 as amended** passes only when F1 and F2 pass under M1b on both Sprint 2 games, the independent check supports M1b,
and a certificate is feasible. G1, G2, G4 and G5 are unchanged.

## 11. Results (written 2026-10-02, after every registered quantity was computed)

Registered quantities come from `evaluation/ps1-design-1/summary.json` (`scripts/ps1_study.py`). Descriptions computed
after the gates, which change no verdict, come from `evaluation/ps1-design-1/posthoc.json`
(`scripts/ps1_posthoc.py`) and are marked POST HOC. `k` is the capture's decision index; in the split game the engine
step is `k - 3`. No engine session was used.

### 11.1 Reconstruction and score reconciliation

Both channels agree at every snapshot of both games (0 disagreements in 1,800 and 1,802 snapshots), and the city flags
equal the observation's own occupy counter at every snapshot. Capture and record agree on 10 and 18 moves and on 2 and 1
occupations, and every recorded order reappears as the unit's remaining path in the next state (10 of 10, 18 of 18).
The input files' digests were unchanged after both drivers ran (6 files).

In the split game the first unit is blocked at `k` 263. From `k` 482 (engine step 479) to the end, 1,321 steps, 10
vehicle units in groups of 4, 4 and 2 are deadlocked, with one two-hex cycle that includes an objective; the 80-point
objective is never occupied. The declared trigger first holds at `k` 533, 51 steps after the deadlock formed (the
vehicles' stall threshold is `2 * 20 + 10` steps), and holds on 1,270 steps. No unit is ever blocked in the baseline
game.

| Final score component (blue) | `baseline-v2` | split candidate |
|---|---|---|
| remain + occupy + attack | 132 + 130 + 0 | 132 + 50 + 0 |
| total | 262 | 182 |
| red (inert control) total | 104 | 104 |
| win = total minus red total | 158 | 78 |

The 158 and 78 of Sprint 1 and Sprint 2 are the win margins against the inert control; 262 and 182 are the totals.
Either way the difference is 80, the 80-point objective.

### 11.2 Observation audit (question 1)

| Id | Input | Class | Evidence (both Sprint 2 games unless stated) |
|---|---|---|---|
| O1 | own units' `cur_hex`, `on_board`, `type`, `basic_speed` | 1 observed | seat observation equals the all-seeing state at every snapshot |
| O2 | `move_path` is the remaining path | 1 observed | it advanced by exactly one hex at all 138 and 274 hex changes |
| O3 | `valid_actions` of a blocked unit | 1 observed (listing only) | action 10 alone at all 13,764 blocked unit-steps of the split game; acceptance is O7 |
| O4 | `speed` | 1 observed | `1 / tau` on every moving unit-step (6,190 and 11,414); 0 on 13,316 of the 13,764 blocked unit-steps, the other 448 being units still traversing towards a hex that is full at that moment |
| O4 | `stationary_count` | 1 observed; not used | steps in the hex plus one on every blocked unit-step, but 762 moving and 28 stationary unit-steps of the split game differ |
| O4 | `can_to_move`, `stop`, `flag_force_stop`, `move_state` | 1 observed; not blockage indicators | `can_to_move` takes both values in every class; `stop` is 0 on every blocked and moving unit-step; the other two are 0 everywhere |
| O5 | hex time `tau` | 2 derived | predicts every unimpeded entry exactly (138 of 138 and 235 of 235, offset 0) |
| O6 | stacking from observed positions | 2 derived | every waiting unit-step (speed 0) faces a full next hex (13,316 of 13,316); every entry after waiting follows a step with room (39 of 39) |
| O7 | acceptance and effect of action 10 on a blocked unit | 4 unknown | no stop was ever issued |
| O8 | processing order of simultaneous entries | 4 unknown (registered) | not examined before the gates; POST HOC evidence in 11.6, items 1 and 4 |

The section 4 terms (occupancy, full hex, next-hex demand, wait-for graph, deadlock, stall age) are class 2, derived
from O1, O2, O5 and the policy's own step history. Objective assignment and reservation are policy state. Nothing a rule
needs is class 3 or 5.

### 11.3 Fidelity and the restart check (G3)

| Model | Game | F1 (recorded orders) | F2 (surrogate) |
|---|---|---|---|
| M1 | baseline | pass, offset 0 | pass, 10 of 10 orders, occupations at `k` 461 and 642 |
| M1 | split | **fail**: sequences equal, worst offset 19 | **fail**: 18 of 18 orders, occupation at `k` 463, worst offset 19 |
| M1b | baseline | pass, offset 0 | pass |
| M1b | split | **fail**: 2 units' hex sequences differ | **fail**: the same 2 units |

Every split-game run reproduces the deadlock itself (10 units, one cycle). The independent check of amendment 1 found
71 corpus episodes: 58 in the M1b window, 0 in the M1 window, 13 in neither. That is 81.7% against the required 90%,
so the registered verdict is **does not support M1b**. The 13 others lie 38 to 299 steps beyond a hex time. On the
two Sprint 2 games, which are not independent, 38 of 39 episodes fall in the M1b window.

### 11.4 Certificates (question 3; descriptive, because G3 fails)

All under M1b from the observed state at the stated start, with 0 capacity violations. Every order after the start and
every trajectory are model-derived; engine acceptance of every order is unverified.

| Alt | Intervention | Start `k` | Commands | Cycle broken at `k` | Deadlocked at end | 80-point objective from `k` | Verdict | Unverified |
|---|---|---|---|---|---|---|---|---|
| A1 | PS-1A from the first play decision | 3 | 8 orders, 3,928 holds | no cycle forms | 0 | 584 | feasible | E5 |
| A4 | stop units bound for an objective just taken, re-order | 464 | 22 stops, 14 orders | no cycle forms | 0 | 718 | feasible | E3, E4, E5 |
| A2 | PS-1B back-off at first detection | 533 | 10 stops, 16 orders, 3 recoveries | 534 | 0 | 808 | feasible | E1 to E5 |
| A3 | PS-1B bypass of the occupying group | 533 | 4 stops, 10 orders, 1 recovery, 2 no-escape events | 534 | 6 | 849 | cycle broken, unresolved residual | E1 to E5 |
| A5a | PS-1B 300 steps after detection | 833 | 10 stops, 16 orders, 3 recoveries | 834 | 0 | 1108 | feasible | E1 to E5 |
| A5b | PS-1B 900 steps after detection | 1433 | 4 stops, 10 orders, 1 recovery | 1434 | 6 | 1708 | cycle broken, unresolved residual | E1 to E5 |
| A6 | PS-1B on a synthetic dead-end corridor | | 0 recoveries, 1 no-escape event, 4 witnesses | | 8 | | failure witness | |

In the model the first recovery breaks the cycle one step after the stop. After a back-off a residual chain forms,
which a second pair of recoveries clears once the 600-step window allows. In A5b the window outlasts the game; in A3
the occupying group's bypass leaves 6 units with no escape. Every certificate ends with both objectives held, 130
occupy points against the 50 observed. That is a model statement about an unobserved engine outcome, not a
prediction of one.

### 11.5 Generalisation and non-interference (G4)

| Rule | Sprint 2 baseline game | split game | replay corpus (8 games, 16 seat-sequences) | Sprint 1 smoke (8 games) |
|---|---|---|---|---|
| PS-1A would change an order | 2 of 10 | 14 of 18 | 162 of 391 | |
| A4's retarget trigger, unit-steps | 2,752 of 10,800 | 13,390 of 25,200 | 65,377 of 323,288 | 853 of 1,665 |
| PS-1B trigger, steps | 0 | 1,270 | 1,429 | 31 snapshots |

Every corpus firing was investigated (POST HOC detail, `posthoc.json`). The corpus holds 10 deadlock episodes (2,447
steps, `baseline-v0` play). The trigger never fires in the 4 shortest (1 to 20 steps). It fires in the other 6:

* a cycle of up to 14 units lasting 323 steps (trigger on 163 of them, first after 91), released when a unit left the
  observation; in a private check, every deadlocked unit had speed 0 at the first, middle and last step of each trigger
  run within it;
* a chain of up to 6 units lasting 1,637 steps to the end of the game (trigger on 969);
* chains of 1 or 2 units lasting 241, 91 and 56 steps, each released when a unit left the observation;
* a chain of 1 unit lasting 64 steps, released when the policy itself ordered a holder, 13 steps after the trigger first
  fired.

In every chain at least one holder stands on an objective. In the smoke games of the split candidate (one snapshot per
200 steps) the trigger fires in 4 of 8 scenarios: two cycles (up to 13 and 38 units) and two chains (3 and 4 units).

* **PS-1A fails G4**: it changes 2 of the frozen baseline's 10 orders in a game with no blocking, and 41% of corpus
  orders.
* **A4's retarget fails G4**: it fires on 2,752 unit-steps of a game with no blocking.
* **PS-1B passes G4**: it never fires without a deadlock in observed state; it does not fire in the baseline game; every
  corpus and smoke firing is on a deadlock and is explained above.
* Two caveats for PS-1B. Once (1 of 6 corpus episodes) the policy's own order released the units 13 steps into a firing,
  where a stop would have cost the 75-second transition. And the trigger lapses whenever a newly blocked unit joins the
  set (163 trigger steps in the 323-step cycle).

No claim of generality beyond these scenarios is made.

### 11.6 POST HOC descriptions (no gate changes)

1. **The M1b departure.** At `k` 283 the contested hex had 2 free places and 3 contenders. Two had waited since `k` 263.
   The third had entered the hex in front of it at `k` 263, the step the contested hex filled, and showed speed 0 from
   its entry step: it never started its traversal (the first two contenders' histories are in the private trace). The
   engine gave both places to the two earlier waiters (entries at `k` 302); the third entered at `k` 322. M1b let the
   third traverse from its entry and gave it a place at `k` 283.
2. **M1c** is M1b plus: a unit entering a hex whose next hex is full at that moment waits at once, with units processed
   in ascending index and occupancy updated after each move. It reproduces both Sprint 2 games under F1 and F2 with 0
   sequence differences and offset 0. Every certificate verdict and step of 11.4 is unchanged under it. M1c was derived
   from item 1, so this is not evidence for it.
3. **The 13 restart outliers** each split into traversals of exactly `tau - 1` steps (38 of 38), separated by re-waits
   that began with the target full again (25 of 25). The Sprint 2 outlier splits the same way (2 traversals, 1
   re-wait). The registered check measured `d` from the first step with room and did not anticipate a refill during a
   restarted traversal.
4. **The entry rule on the corpus.** Of 3,240 entries with a path left, 60 waited at once. Ascending-index processing
   predicts the speed-0 state of 3,230; descending index predicts 3,193, and end-of-step occupancy 3,221. All 10
   ascending disagreements are units at speed 0 whose next hex was not full and whose observation `keep` flag was set.
   This corpus was already used by the amendment-1 check, and the property was chosen after item 1.

### 11.7 Engine facts and hypotheses

| Statement | Status | Provenance |
|---|---|---|
| `speed` is 0 while a unit with a path waits in front of a full hex and `1 / tau` while it traverses | fact | O4, O6 |
| `valid_actions` lists only action 10 for a unit blocked by capacity | fact (listing) | O3 |
| `tau = (720 / basic_speed) * cost` predicts every unimpeded entry | fact on this route | O5 |
| `can_to_move`, `stop`, `flag_force_stop`, `move_state` do not tell a blocked unit from a moving one | fact | O4 |
| a unit in transit reserves no place; a column follows a column leaving the hex in the same step | supported | amendment 1 (Sprint 2 captures) |
| restarting after a wait takes a full hex time, counting the restart step (M1b) | hypothesis: registered check not supported (58 of 71); POST HOC consistent with every episode | 11.3, 11.6 item 3 |
| a unit entering a hex in front of a full hex waits at once; entries processed in ascending index (M1c, E5) | POST HOC hypothesis | 11.6 items 1, 2, 4 |
| action 10 is accepted from a blocked unit, takes effect in place, and is followed by a 75-second transition after which action 1 is listed again (E1 to E4) | unverified | O7 |
| a game's length is scenario-specific: 1,800 steps in 1910631192, while a corpus game of 2130511121 runs to step 2,879 (C5 stated 1,800 without that qualification) | fact | `posthoc.json` episode rows |

### 11.8 Selection (questions 2 and 4)

*Detection.* Speed 0 with a full next hex identifies a waiting unit (O6); the maximal deadlocked set and its cycles
follow from observed positions and paths. The stall condition delays detection by a hex-time margin (51 steps after
formation in the split game) and keeps the trigger off for transient queues (the 4 short corpus episodes).

*Anticipation.* PS-1A's commitment counting anticipates the block, but counts commitment rather than timing, and so
fires where nothing would block.

*Choice.* PS-1A is rejected (G4). PS-1C is not needed: under the model, recovery alone suffices (A2, A5a), and the
combination would only add PS-1A's interference. **Selected minimal candidate: PS-1B with back-off.** When the
deadlock-and-stall trigger holds, it stops the smallest deadlocked group on the cycle (or, for a chain, any deadlocked
group) whose units can all back off to hexes with spare capacity that lie on no blocked unit's remaining path. After
the transition it re-orders that group; otherwise it emits nothing. Its live uncertainties are E1 to E4, M1c with E5,
and whether a residual chain forms in the engine as it does in the model.

*State, reset and ties* (as in `src/miaosuan_agent/evaluation/ps1_model.py`):

* State: for each unit, the step of its last hex change or order (its stall age), the step of its last recovery, and
  a planned path while it is in its transition.
* Reset: a recovery needs every deadlocked unit to be at least 600 steps past its last recovery or failed attempt. A
  planned path is issued, and dropped from the state, at the first step its unit accepts a move again.
* Ties: the group is the smallest, then one not standing on an objective, then the one in the lower hex index.
  Backed-off units go to the nearest hexes by path cost, with spare capacity counted as they are placed, ties by lower
  hex index, units taken in ascending index.

### 11.9 Gate verdicts

| Gate | Verdict | Reason |
|---|---|---|
| G1 evidence integrity | **PASS** | 11.1: both channels, flags against counters, record counts, order echo, unchanged digests, the failure as diagnosed |
| G2 observable intervention | **FAIL** for the selected PS-1B | it uses only class 1 and 2 inputs but depends on E1 to E4, which documentation cannot settle (PS-1A would pass G2; it fails G4) |
| G3 offline feasibility | **FAIL** | F1 and F2 fail under M1b on the split game, and the independent check does not support M1b; the certificates of 11.4 stay descriptive |
| G4 generalisation and non-interference | **PASS** for PS-1B | 11.5; PS-1A and A4's retarget fail |
| G5 disposition | **NEEDS_ENGINE_PROBE** | below |

### 11.10 Disposition: NEEDS_ENGINE_PROBE

What blocks the selected candidate is a set of named engine behaviours that no capture contains: E1 to E4 block G2, and
the admission of entrants that outnumber the free places (E5; POST HOC, M1c's wait at entry) blocks G3.

* **Not REVISE.** The one correctable defect found, an independent check that did not anticipate refills, is not what
  blocks: with a corrected check, G2 would still fail on E1 to E4.
* **Not SHELVE.** The model admits a capacity-consistent recovery (A2, A5a), and PS-1B passes G4.
* **Not READY.** G2 and G3 fail.

The deadlock also arises in ordinary `baseline-v0` corpus play (11.5), so the question does not depend on the split
candidate alone. Whether `baseline-v2` meets it outside this one game is not known.

**The smallest probe** (next sprint, after the owner's approval and a registration written before any session; not run
here):

* **P1, stop on a waiting unit (E1 to E4).** One session of the configuration that produced the deadlock (scenario
  1910631192, condition C3, the split candidate against the inert control) with a diagnostic hook. At the first step
  the registered trigger holds, the hook stops every unit of the group PS-1B selects; after the transition it issues the
  planned back-off moves. Per step, for every unit involved, record: the engine's response to each action, `cur_hex`,
  `move_path`, `speed`, `stop`, `valid_actions`, `stationary_count`, and own occupancy of the involved hexes. Read off:
  acceptance (E1); the unit's hex after the stop (E2); the transition length and the re-listing of action 1 (E3);
  whether the other group enters the stopped group's hex during the transition (E4).
* **P2, the movement model on fresh data.** Register M1c and its pass criterion first (F1 within one step, 0 sequence
  differences, every own unit). Then evaluate it on one session of the split candidate against the inert control, in a
  second scenario whose smoke game showed a cycle (1930331196 or 2130511121), with no intervention.

Two engine sessions in total. P1's trajectory before the stop is not fresh evidence for M1c if the engine reproduces the
Sprint 2 game.

### 11.11 Question 5: separating PS-1 from the split policy (outline, not a proposal)

A 2 x 2 design, `{baseline-v2, split candidate} x {PS-1B off, on}`, on the same scenarios, seats and opponents, plus an
observe-only arm that logs the trigger without acting.

* PS-1B's effect within `baseline-v2` measures interference and the prevalence of the block in the frozen policy.
* Its effect within the split candidate measures rescue.
* The interaction is the part of the split's loss that capacity-aware movement removes.

It is contingent on the probe and is not registered. `docs/PS1_SCREEN_PROPOSAL.md` is not written, because G5 is not
READY_FOR_PROSPECTIVE_VALIDATION.

### 11.12 Limits

* The failure is observed in one scenario.
* The certificates rest on a model that failed its registered fidelity check.
* The corpus is `baseline-v0` play, not `baseline-v2`.
* The smoke snapshots are 200 steps apart.
* M1c was derived from the games it reproduces.
* No offline counterfactual here establishes an engine outcome.
