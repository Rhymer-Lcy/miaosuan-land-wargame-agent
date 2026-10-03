# T7 idle concealment: offline search for an E3b configuration

**EXPLORATORY OFFLINE STUDY.** No engine session, no registration, no public experiment issue, no change to any policy,
protocol, verdict or output of an earlier study. This document is the protocol and the record of `t7-e3b-search-1`
(Tactical Frontier Sprint 7). Sections 1 to 11 were written, and the input selection frozen
(`evaluation/t7-e3b-search-1/inputs.json`), before any eligible seat was searched; section 12 onwards is written
afterwards and says so. An offline protocol pushed before analysis is not an engine preregistration. Times are UTC+8.

## 1. Question and scope

Sprint 6 (`docs/T7_MECHANISM_PROBE.md`) ended in `NEEDS_TARGETED_PROBE`: endpoint E3b, exit from concealment by a real
`baseline-v2` move or shot, had no event in its three games. This study asks, without the engine, whether an existing
historical record contains a configuration in which `baseline-v2`, with no intervention:

1. leaves an own ground unit idle and stationary while no enemy is seen;
2. meets the exact frozen trigger of `t7-idle-concealment` (`docs/T7_DESIGN.md`, section 14) for that unit, including
   the transition timers, the listing and the candidate's memory;
3. leaves the unit undisturbed for at least the 75-step transition;
4. then issues a move (action 1) or a direct-fire shot (action 2) to that same unit.

Such a history is a candidate configuration for a small, separately registered E3b probe. It never shows that the
command would be accepted after concealment or that concealment would end without delay: the recorded trajectories
contain no concealed unit at the target, and E3b stays untested until a new registered session observes it. E4b and E5
are not addressed. If a configuration qualifies (section 9), a proposal is drafted; nothing here registers or runs it.

## 2. Evidence already seen (disclosure)

Before this protocol: the public documents and outputs of Sprints 5 and 6; the private Sprint 6 exploration of game
`b` summarised in `docs/T7_MECHANISM_PROBE.md` section 2 (from decision 717 on, `baseline-v2` gives none of the four
units the candidate orders any action); Sprint 6's post-hoc finding that `baseline-v2` gave none of the 16 ordered units
any action after its order; Sprint 5's post-hoc count that 2 of 49 first-activated H0 units later "acted or moved" in
the recorded `baseline-v0` trajectory (`evaluation/t7-design-1/posthoc.json`), a label computed from the recorded
`baseline-v0` actions and from `stop` or move-path changes, not from reconstructed `baseline-v2` decisions. For the
inventory of section 3, capture metadata only were read (players, step and snapshot counts, snapshot indices, field
names of one snapshot); no observation content of any dataset was read for this study. Sprint 6's registered
analysis re-decided every decision of the two P-B games' `baseline-v2` seats and used their units as observers (E4),
but no study has evaluated the trigger on those seats or followed their units.

## 3. Datasets

All private, on the evaluation server (`local/`). "Full" means a snapshot at every decision.

| Id | Dataset | Seat searched: policy (identity actually executed) | Scenario, condition | Opponent | Snapshots; memory; feedback | Eligibility |
|---|---|---|---|---|---|---|
| A-b | Sprint 2 game `b` (`t1r-diagnosis-1`, `1910631192.C3.b.x01`, session 2459) | blue: `baseline-v2` | 1910631192 C3 | inert | full (decisions 1 to 1,800; seat view and all-seeing); seat memory; per-step feedback, judge records and batch | A-eligible |
| A-pb1 | Sprint 6 P-B1 (`t7-mechanism-probe-1`, `2120531121.H1.pb1`, session 2463) | blue: `baseline-v2` | 2120531121 H1 | `t7-idle-concealment` | full (0 to 2,880 plus the final state; both seats and all-seeing); memory; feedback, pre-execution copies | A-eligible |
| A-pb2 | Sprint 6 P-B2 (`2120531121.H2.pb2`, session 2464) | red: `baseline-v2` | 2120531121 H2 | `t7-idle-concealment` | as A-pb1 | A-eligible |
| B-c | Sprint 2 game `c` (`1910631192.C3.c.x01`, session 2458) | blue: `tactic-deployment-split-1` (its play stage is `baseline-v2`'s) | 1910631192 C3 | inert | full (1 to 1,802); memory; feedback | B: policy identity |
| B-p2 | Sprint 4 game P2 (`ps1-engine-probe-1`, `1930331196.C2.p2`, session 2461) | red: `tactic-deployment-split-1` | 1930331196 C2 | inert | full (1 to 2,882); memory; feedback | B: policy identity |
| B-r516 | residual-516 diagnostic, 32 games (`baseline-v2-residual-516-diagnostic-1`, sessions 1866-1897) | blue: `baseline-v2` | 1930331196 C3 | inert | every 200th decision plus 5-step windows at refusals; memory at snapshots; per-step batch, feedback, judge records and all-seeing changes of `blood`, `keep`, `on_board`, presence | B: sparse snapshots |
| B-smoke | deployment-split smoke, 8 games (`tactical-screen-deployment-split-1-smoke`, sessions 2258-2265) | red: `tactic-deployment-split-1` | 8 scenarios, C2 | inert | every 200th decision; as B-r516 | B: sparse and policy identity |
| C-h0 | H0 replay corpus (`evaluation/routing-remediation-1/corpus.json`), 8 games | both seats: `baseline-v0` executed; `baseline-v2` reconstructed offline | 8 scenarios, C1 | `baseline-v0` | every decision of each seat (seat view only); no memory (re-derived by replay); no feedback (judge records in the observation) | C: off-policy |

Excluded, fixed now:

| Dataset | Reason |
|---|---|
| P-A (`1910631192.C3.pa`) candidate seat; P-B1 and P-B2 candidate seats | intervention (concealment orders); used only for the known-answer validation of section 7 |
| inert seats of every game | not `baseline-v2` |
| Sprint 4 game P1 (`1910631192.C3.p1`) | before its first stop it reproduces game `c` (never counted twice); from the stop on, a diagnostic intervention |
| `baseline-v2-target-ownership-prevalence-1` captures | withheld by that study's own rule; not opened |
| BOKE-2026 holdout | not available locally; never inspected |
| game records of every other experiment (`baseline-v0`, `baseline-v0-diagnostics`, the occupy, variance, shoot-reservation and deployment-split experiments) | aggregates only (actions by type, refusals): no unit can be followed, so they cannot hold an episode of any category |
| latency-diagnostic states | single decisions of `baseline-v1` |

The Sprint 5 record inventory (`evaluation/t7-design-1/record-inventory.json`) froze that study's input; it is not a
limit here. This study's own input is frozen by `evaluation/t7-e3b-search-1/inputs.json` (the SHA-256 of every record,
compact capture, snapshot file and corpus file named above, the pinned identities of the candidate, `baseline-v2` and
the pool predicate); the search refuses when a named file is missing or changed and reads no other file, so later
records cannot change its results.

## 4. Definitions

* **Trigger**: the frozen candidate `t7-idle-concealment` (`experiments/t7_concealment.py` around the unchanged shadow
  `experiments/t7_idle_concealment.py`, policy source `6b73c39ad785938cc1c54b72065858fbf6460a66ceebae627bad4e99fa1a50f0`),
  replayed decision by decision over the seat's recorded observations with its own memory from game start. Nothing in
  the trigger is relaxed.
* **Episode-opening order** of unit `u` at decision `k0` (`cur_step` `s0`): the replay's first order to `u`, and every
  later replay order to `u` issued after `u`'s previous episode ended (at its later command or disturbance). Orders
  inside an episode, the replay's 75-step repeats on a trajectory where no unit ever concealed, are ignored, and an
  episode running to the end of the game admits no successor. An episode opened after a previous one is
  **conditional**: it presupposes the unobserved outcome of the earlier order (an interrupted transition, a command
  executed during the transition or from concealment, or a disturbance of a concealing or concealed unit) and is
  reported with the previous episode's class. The replay's baseline part must equal the recorded `baseline-v2`
  decision at every play-stage decision of the seat (section 6; in B-c and B-p2 the split candidate's play stage is
  `baseline-v2`'s, and its deployment decisions differ by design).
* **Later command**: the first decision `k1 > k0` at which `baseline-v2` (the recorded decision, equal to the replay's
  baseline part) gives `u` any action; `s1` its `cur_step`; **interval** `d = s1 - s0`. Its type decides: action 1 (move)
  or action 2 (direct fire) only. Indirect fire (8), guided fire (9), occupation (5), boarding (3, 4) and every other type
  are "another action", never a move or shot.
* **Undisturbed** at a decision `k` in `(k0, k1]`: `u` is in the seat's `operators`, on the map, with the `blood` it had at
  `k0`, the same `cur_hex`, an empty move path, `stop` 1, `keep` 0, `flag_force_stop` not 1 and every transition timer 0;
  no enemy unit is in its hex (all-seeing state where captured, else the seat view); no judge record of the engine step
  leading to `k` names `u` as attacker or target. The first decision violating one of these ends the episode as
  **disturbed**, with the reason and `d` at that decision. Missing evidence does not end an episode: a decision whose
  `cur_step` is not the previous decision's plus one (a snapshot gap) or a missing or malformed field is recorded and the
  scan continues, and an episode carrying such a gap can be at most category B. Where the all-seeing state is captured,
  the unit's fields there must equal the seat view's over `[k0, k1 + 1]` (section 5).
* **Episode classes** (one per episode-opening order):
  * `W`: undisturbed through `k1`, later command type 1 or 2, `d >= 75`: the completed-concealment case.
  * `TI`: undisturbed through `k1`, type 1 or 2, `d <= 74`: a possible transition-interference case (E5), reported
    separately, never an E3b witness.
  * `OA`: undisturbed through `k1`, another action type (reported by type and `d`).
  * `DT`: disturbed, split by whether the first violation is at `d <= 74` (transition interrupted) or `d >= 75`
    (disturbed while it would have been concealed; whether concealment survives that is undocumented, so never a
    witness).
  * `CE`: no later command and no disturbance until the last decision of the game, split by whether the last decision
    is at `d >= 75`.
* **Acceptance of the later command** in the original game: exactly one fresh feedback entry echoes it without an error
  code, and it executed (a move: the next snapshot shows the ordered path or its first hex entered; a shot: a judge
  record of the step with `u` as attacker). Its listing at `k1` (type listed for `u`; for a shot, the target and weapon
  among the listed options) is recorded.

The 75-step boundary follows Sprint 6's observation: every order completed exactly 75 steps after `s0`, so a decision
at `s0 + 75` sees the concealed state and one at `s0 + 74` the last transition step.

## 5. Evidence categories

Never pooled into one witness count.

| Category | Rule |
|---|---|
| A, direct historical behaviour | a `W` episode in an A-eligible seat whose whole-game re-decision reproduces every recorded action and trace (section 6), with both trigger implementations agreeing on every order, both channels agreeing on the unit over `[k0, k1 + 1]`, and the later command accepted and executed |
| B, incomplete evidence | a `W` episode, or a sparse-capture episode meeting section 6.2, that fails one requirement of A only through missing or deficient evidence: policy identity (B-c, B-p2, B-smoke), a missing snapshot (B-r516, B-smoke), a re-decision difference, a channel disagreement, or missing or ambiguous feedback; the failed requirement is named |
| C, off-policy replay hypothesis | a `W` episode in C-h0: the trigger and the later command are decisions of `baseline-v2` reconstructed on `baseline-v0`'s trajectory, which `baseline-v2` did not generate |
| D, structural opportunity only | (D1) an episode whose unit stays undisturbed for at least 75 steps but has no later move or shot (`CE` with `d >= 75`, or `OA` with `d >= 75`); (D2) a `baseline-v2` move or shot to a ground unit that, in the decisions immediately before it, had been stationary, unsuppressed, without an action and undisturbed for at least 75 consecutive steps, while the frozen trigger never held for it in that run (the first trigger refusal reason in the run is reported). D is never a witness |

A category-A episode establishes only that the event occurs on a trajectory without concealment. Concealment could
change later observations, the opponent's decisions and the candidate seat's own listings; the recorded later command
is never projected into the altered game as an observed fact.

## 6. Search procedure

### 6.1 Full captures (A-b, A-pb1, A-pb2, B-c, B-p2)

1. Verify every input against `inputs.json`.
2. Re-decide every decision of the searched seat with a new instance of the frozen policy the seat executed
   (`baseline-v2`, or the split candidate in B-c and B-p2) from the recorded observation and the recorded memory; count
   decisions whose actions or trace digest differ (pre-execution copies where captured, otherwise the recorded
   actions).
3. Replay the frozen candidate sequentially over the seat's observations; independently evaluate the pool predicate
   (`evaluation/t7_candidates.py`, `a2`, written separately in Sprint 5) on the same observations with the recorded
   `baseline-v2` actions; the two must find the same orders. A disagreement stops the population.
4. Classify each episode (section 4), with the unit's series read from the seat view and, independently, from the
   all-seeing state; for every `W` and `TI` episode, the acceptance evidence.
5. For every `W` episode: the divergence analysis of section 8.

### 6.2 Sparse captures (B-r516, B-smoke)

The first eligible decision cannot be located between snapshots, so only B is possible. At each snapshot, the frozen
trigger is evaluated with the candidate's repeat memory empty (the earliest true order is at or before the snapshot)
after the seat's policy is re-decided from the captured observation and memory; a snapshot whose re-decision differs
from the recorded decision is excluded from trigger evaluation and counted.
For each unit at its first triggering snapshot `s`, the per-step log gives the first later `baseline-v2` action to it,
its type and `cur_step` `s1`, and every step's judge records and all-seeing changes of `blood`, `keep`, `on_board` and
presence; `d = s1 - s` is a lower bound of the true interval. A sparse episode is reported as B when no action reached
the unit before `s1`, no judge record names it, none of those fields changed, its type is 1 or 2 and `d >= 75`;
position, move path and enemy presence between snapshots are unobservable, which is the named deficiency.

### 6.3 Replay corpus (C-h0)

`baseline-v0` must reproduce each recorded decision and `baseline-v2` is reconstructed as in Sprint 5
(`scripts/t7_study.py`, every difference explained by `baseline-v2`'s own reservation record); a decision failing
either is excluded and counted. The candidate is replayed on each seat; continuity uses the seat view (no all-seeing
state, no feedback: acceptance is reported as unavailable). The later command is the reconstructed `baseline-v2`'s;
whether the recorded `baseline-v0` gave the same action, and whether the recorded trajectory shows it executed, is
reported beside it.

### 6.4 The two H0 leads

Sprint 5's two first-activated H0 units labelled "acted or moved" are identified from its private post-hoc rows. For
each: the decision and `d` at which the label fired, which condition fired it (a recorded `baseline-v0` action, a
`stop` change or a move path), the reconstructed `baseline-v2` decision there and its action type for the unit, and the
episode's class under section 4.

## 7. Validation before use

* Synthetic tests (`tests/test_t7_e3b.py`), positive and negative: intervals of 74, 75 and 76 steps; game-end
  censoring on either side of 75; a missing snapshot; a missing or malformed field; the unit disappearing, boarding,
  suppressed, damaged, moved or given a path; a transition timer becoming positive; an enemy entering its hex; a judge
  record naming it; a later command of another type (8, 5); a misleading listing (action 6 listed with only malformed
  options; a unit listed in `valid_actions` but absent from `operators`; a later command to a different unit); a
  rejected or unechoed later command; two first orders in one decision.
* Known-answer real-record test, before any eligible seat is searched: the machinery on the three excluded candidate
  seats (P-A, P-B1, P-B2), where the published answer is known. There the concealment really happened, so the
  expected answer is exact: the candidate replay over each seat's recorded observations, from game start with its own
  memory, reproduces every recorded order (16 orders to 16 units, decision and unit) and its actions and trace at every
  decision; each of the 16 episodes is `DT` with reason "transition" at `d` = 1 (the timer positive one step after the
  order, as Sprint 6 observed); there is no `W`, `TI` or `OA` episode and no conditional episode. A failure stops the
  study.
* Mutation testing of the classifier and the decision rule; every survivor killed or documented.
* Independent cross-check of the final counts (`scripts/t7_e3b_crosscheck.py`): separately written code using the pool
  predicate as the trigger and the all-seeing state (seat view in C-h0) for continuity recounts the episodes and the
  `W`, `TI`, `OA`, `DT` and `CE` classes per dataset, and the `W` episodes by category; any disagreement blocks the
  disposition until explained in a dated note.

## 8. Divergence analysis and feasibility rubric (fixed before any result)

For every `W` episode (any category): `k_first`, the seat's first order to any unit; the number of other units first
ordered before `k0` and before `k1`; for each, whether its 75-step transition would complete before `s1` and whether
the opposing seat lists it after that point and before `s1` (then concealment of that unit could change the opponent's
information and decisions); the cur_step of the game's first judge record (the variance study found no divergence
between repetitions before a game's first shot); the opposing policy.

Mandatory feasibility conditions of a configuration (all must hold):

* **F1** category A.
* **F2** deterministic reachability of the target's order: the episode is not conditional (it opens at the unit's first
  order); no judge record in the original game before `s0`; and every other unit first ordered before `k0` is never
  listed by the opposing seat between its order and `s0`, or the opponent is inert.
* **F3** the later command accepted and executed in the original game, with `d >= 75`.

Ranking of the configurations that meet F1 to F3, lexicographic, fixed now: (1) a configuration whose earlier records
show identical repetitions (deterministic) before one whose determinism ends at the first shot; (2) the target among
the units of `k_first` (no earlier activation in the seat); (3) fewer units first ordered before `k1`; (4) no unit of
the seat waiting more than 20 steps in front of a full hex (speed 0 with a path) before `s1`; (5) the smaller slack
`d - 75`; (6) the earlier `s1`. Reported beside the rank (not deciding): the later command's type, whether survival and
listings are captured in both channels, and whether a single prospective game can be decisive.

## 9. Decision rule

Evaluated in this order:

1. **`E3B_CONFIGURATION_IDENTIFIED`**: at least one category-A episode meets F1 to F3 and the independent cross-check
   agrees. The best-ranked configuration is the basis of a probe proposal.
2. **`E3B_CONFIGURATION_UNCERTAIN`**: otherwise, at least one `W` episode of category A, B or C exists; the missing
   evidence of the strongest one is stated.
3. **`NO_NATURAL_E3B_WITNESS_FOUND`**: no `W` episode of category A, B or C exists in the eligible datasets, all of
   which were searched; D episodes are reported as structural opportunity only.

A cross-check disagreement or a stopped population gives no disposition until explained in a dated note.

## 10. Stopping rules and governance

* The search is exhaustive over the frozen inputs; there is no early stop on a favourable or unfavourable result.
* It stops, and reports a blocker rather than a result, when an input fails its digest, the known-answer test fails,
  or the two trigger implementations disagree; nothing is repaired and relabelled as the registered search.
* No trigger, class boundary, rubric or rule changes after the first eligible seat is searched; a defect found later is
  handled in a labelled post-hoc note, and the outputs computed under this protocol stand.
* Sprint 5 and Sprint 6 protocols, manifests, verdicts and outputs are not touched; their code is imported, not
  modified. No engine session is opened.

## 11. Outputs and privacy

Public (`evaluation/t7-e3b-search-1/`): `inputs.json`; `validation.json` (known-answer test); `search.json` (per
dataset: decisions, re-decision agreement, first orders, classes, categories, the leads); `certificates.json` (per `W`
episode: dataset, scenario, seat colour, unit type and sub_type, `k0`, `s0`, `k1`, `s1`, `d`, the later command's type
and listing, acceptance, the divergence analysis, and three separated sections: observed historical facts, offline
replay decisions, hypothetical consequences); `crosscheck.json`; `decision.json` (the decision rule's inputs and
result); `mutation.json`. Private (`local/diagnostics/e3b/`):
the same with unit identifiers and hexes. No observation, unit identifier, hex or SDK content is published.
