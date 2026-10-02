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
