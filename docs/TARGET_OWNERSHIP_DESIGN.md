# Target-ownership design study

`target-ownership-design-1` turns the target-allocation audit (`docs/TARGET_ALLOCATION_AUDIT.md`) into one precisely
specified, single-variable candidate design and determines what evidence is required before such a candidate is
implemented or evaluated. No engine session is opened, `baseline-v2` is not modified, no candidate policy is
implemented and nothing is registered. The tools are analysis-only:
`src/miaosuan_agent/evaluation/ownership_design.py` (the formal model, the S1 oracle, the fingerprint),
`scripts/analyze_ownership_design.py` (the structural analysis of the audit's verified population) and
`scripts/ownership_sensitivity.py` (planning sensitivity from public inputs).

This document, the tools and their synthetic tests were committed before the structural analysis was run on any
private state; the sensitivity table, which uses public inputs only, was generated first. Results are appended under
"Results".

## Evidence boundaries

The audit's 14 ownership mismatches are not 14 independent observations: they are 6 recurring situations in 4 games,
all in replayed `baseline-v0` C1 trajectories (D2), and the available `baseline-v2` trajectory (D1) contains none.

| Conclusion | Status | Why |
|---|---|---|
| **State level**: when `baseline-v2` decides on the reconstructed states, first-come reservation can give a target to a claimant with a lower attack level than a later, displaced claimant | **supported** | 14 collision groups, 6 situations, 4 games of the replay corpus, reproduced exactly |
| **Trajectory frequency**: how often `baseline-v2` itself reaches such states in normal play | **not established** | the D2 states come from `baseline-v0` trajectories; D1 is a `baseline-v2` trajectory, but only its captured snapshots (event windows before code-516 refusals and every 200th step) hold decision-time observations, so its zero is not evidence of rarity; the registered experiment kept per-seat counts only |
| **Tactical effect**: whether changing the owner improves or harms outcomes | **not established** | no outcome of an ownership change has been observed; the attack level is the engine's result-table index, and no engine contract states that a higher index means more damage |

No n=14 is used anywhere as a sample size, no effect is estimated from those groups, and no claim is made that
`baseline-v2` commonly encounters these states.

## Formal allocation model

**Shoot graph.** For one seat at one decision: left nodes are the controllable units in `baseline-v2`'s processing
order (ascending id), right nodes are targets, and an edge joins a shooter to a target where the shooter has at
least one shoot candidate on it (a well-formed `valid_actions` option with attack level at least 1, extracted by
`baseline-v2`'s own `engage_candidates`). The edge carries the shooter's best candidate on that target by
`baseline-v2`'s existing within-unit rank: highest attack level, then lower weapon id (the target is fixed on an
edge). No new score is introduced.

**Components.** Connected components of the graph:

* **S1, isolated single-target collision component**: exactly one target and at least two shooters;
* **S2, coupled multi-target component**: two or more targets and at least two shooters;
* **S3, non-collision**: one shooter (with any number of targets); no competing claimant.

These are components of the full shoot graph. The audit's 102 components were built only from targets that had an
exclusion, so its counts are not comparable with these.

**Current ownership.** `baseline-v2` processes units in order; each selects by category (shoot, then occupy, then
move) and by rank within a category; a target is reserved by the first unit whose emitted shot at it passes the
single-proposal gate check, and later units' options on it are excluded. In an S1 component every shooter's only
shoot candidates are on the one target T, so the first shooter shoots T and every later shooter is displaced to
occupation, movement or nothing.

**Proposed ownership (S1 only).** The designated owner of T is the shooter whose best candidate on T has the highest
attack level; ties are broken by the lower weapon id of that best candidate, then by earlier processing order. The
target id is the same for every claimant and plays no role.

## Candidate: `highest-attack-claimant reservation`

A conceptual design only; nothing here is implemented in the agent.

**The single behavioural variable.** For an isolated single-target shoot-collision component, target ownership is
chosen by the highest existing attack-level claimant rather than by first unit-id processing order. Nothing else.

**Not variables**: the number of shots per target (still one), the ranking of alternate targets, movement,
occupation and its same-step reservation, damage or kill prediction, target hit points, weapon-effect modelling, and
any optimisation of coupled components.

**Cases, stated explicitly.**

* *Several claimants tie on attack level*: the lower weapon id of their best candidates decides, then earlier
  processing order. Weapon ids are compared across units here, which `baseline-v2` does only within a unit. The
  analysis reports how often this key alone changes the owner; an implementation turn must confirm or drop it before
  any registration (open decision D-1), and the prospective diagnostic records the deciding key so that the decision
  can rest on on-policy data.
* *One claimant has several weapons on T*: only its best candidate takes part. If it is the owner it emits exactly
  that candidate, as `baseline-v2` would. If it is a non-owner processed before the owner, all its options on T are
  excluded.
* *A claimant disappears from the legal candidates before final selection*: impossible within one decision. The
  candidates come from the decision-time `valid_actions`; both passes use the same context and the same extraction;
  the only removals inside a decision are `baseline-v2`'s own same-step reservation and the designed exclusion. The
  contract requires a test of this equality.
* *The designated owner's shot would be rejected by the project gate*: see the gate interaction below.

**Gate interaction.** The single-proposal gate check `baseline-v2` applies before reserving a target is, for a
shoot proposal, a pure function of the action and the decision's context: the router is not used for shoot
parameters, and the only batch-level rule (one action per unit) cannot reject a unit's single proposal. The design
therefore runs that same check on the designated owner's best candidate in the first pass:

* passes: the designation stands; the owner's shot then passes the identical check in the second pass and is emitted;
* fails: there is no designation and the component keeps `baseline-v2`'s behaviour exactly. No other claimant is
  promoted and the component is not declared unsupported.

The gate itself is unchanged; no target is ever reserved for an action that cannot be emitted, and a failed
designation never leaves T without the shot `baseline-v2` would have emitted.

**S2 and S3.** Exactly `baseline-v2`. A collision inside an S2 component is reported as "fallback to
`baseline-v2`"; no matching, search or optimisation is attempted.

## Two-pass structure and behavioural isolation

The candidate needs a read-only first pass, because the owner may be processed after the units it must exclude.

* **Pass 1** (no side effects): extract every controllable unit's shoot candidates with the same function and
  context as pass 2; build the graph and its components; for each S1 component compute the designated owner and,
  when it is not the first shooter, the gate precheck; record a designation only when both hold.
* **Pass 2**: `baseline-v2`'s loop, unchanged, in the same order. The one addition: a unit processed before the
  designated owner of an S1 target has its options on that target removed from its shoot candidates before category
  selection, with a trace record. Later shooters of the component are excluded by `baseline-v2`'s own same-step
  reservation once the owner's shot passes the gate, with its usual record naming the owner as reserver.

| Concern | Could a two-pass design change it? | Requirement |
|---|---|---|
| candidate generation | yes, if pass 1 used other extraction or recorded diagnostics | pass 1 calls the same `engage_candidates` on the same context and records nothing; diagnostics come from pass 2 only |
| ordering | yes, if pass 2 iterated differently | pass 2 iterates `context.units` exactly as `baseline-v2` |
| occupation reservation | only through inputs | code unchanged; a displaced former owner may now occupy or move earlier in the order, which can suppress a later unit's occupation: an allowed, traced consequence of the variable, not a second variable |
| same-target reservation | no | code unchanged; it excludes later shooters of the component after the owner's shot |
| movement | only through inputs | code unchanged; route results must not depend on the order of router calls (test) |
| trace semantics | yes | new record list only when a designation exists; otherwise the semantic trace (policy key removed) equals `baseline-v2`'s |
| project-gate timing | no | the gate runs as before; the precheck is an extra pure call |
| state mutation | yes, if pass 1 touched memory, the router or the trace | pass 1 is pure |

**Invariants.**

* I1. Pass 1 and pass 2 see identical candidates for every unit.
* I2. Processing order is `baseline-v2`'s.
* I3. No exclusion and no record unless the component is S1, the designated owner is not the first shooter and its
  precheck passes.
* I4. In every decision without a designation, actions and semantic trace equal `baseline-v2`'s.
* I5. A designated owner emits its best candidate on T.
* I6. Exactly one shot at T is emitted whenever `baseline-v2` emits one.
* I7. Only shooters of a designated S1 component processed before its owner lose options, and only their options
  on T.
* I8. Pass 1 changes no memory, router state, diagnostic or trace.
* I9. Determinism under input order and hash seeds.

## Situation fingerprint

Two keys, both deterministic:

* **identity situation** (private key; only counts are published): corpus, game, seat, the shooters and the targets
  of the component (for audit groups: the target and its eligible units), as in the audit;
* **structural fingerprint** (published as a 16-hex hash): configuration, seat faction, component kind, and per
  shooter in processing order its edges as (target index, attack level, weapon rank), whether occupation and movement
  are listed for it and whether it stands on an objective outside own control, plus whether any objective is outside
  own control. Targets are indexed by first appearance; weapons by dense rank within the component; no unit, target
  or weapon id enters it. Steps are not part of it, so periodic repeats collapse.

## Cluster-aware summaries

The phenomenon is reported at four levels: raw collision group, distinct situation (both keys), game, and
configuration. No binomial interval is computed over collision groups. The only interval reported is an exact one
over games within a corpus, where games are independent; it is labelled with its corpus, its policy and its number
of games.

## Oracle under strict scope

For every S1 component of every verified decision: baseline owner (first shooter), designated owner, deciding key,
and, where the owner would change and the precheck passes, the frozen `baseline-v2` decided on a copy of the
observation without T's candidates for the shooters processed before the designated owner. Reported: owner unchanged
or changed, attack-level difference, what the former owner then does, what the designated owner did before, emitted
shot-count delta, non-shoot action changes, the units changed and the trace records the candidate would add (one per
earlier non-owner). For S2: "fallback to `baseline-v2`" only. The audit's 14 mismatch groups are reclassified under
the strict S1 definition, without adjusting the definition to recover them.

## Prospective prevalence diagnostic (design only; not registered, not run)

* **What runs**: unchanged `baseline-v2` on `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), workers 32,
  scheduler `miaosuan-game-pool/1@e717be37...`, the 8 frozen scenarios under C1, C2 and C3, 15 games per
  configuration (the registered layout, 360 games), ledger purpose `diagnostic`. No candidate, no intervention; a
  read-only observer computes the shoot graph from each `baseline-v2` seat observation after the decision (the
  residual-516 diagnostic's observer pattern; records are unchanged without it).
* **Recorded per collision component** (private, git-ignored): game, step, seat, faction, kind, shooter and target
  counts, edges, claimant attack levels and weapon ranks in processing order, first and designated owner, deciding
  key, precheck result, each shooter's `baseline-v2` action class, structural fingerprint, trace digest; and, for
  each decision containing an S1 mismatch, the seat observation and memory, so that the S1 oracle can be replayed
  offline and verified against the recorded digest.
* **Per decision** (aggregated publicly): decisions, decisions with at least one S1 or S2 component, components by
  kind.
* **Primary quantity**: the share of games containing at least one `baseline-v2` decision with an S1 component
  whose first owner has a strictly lower attack level than another claimant, per configuration and per condition.
* **Secondary**: distinct decisions with such a component; distinct fingerprints and fingerprint-game pairs; S2
  mismatches (outside the candidate's scope); weapon-tie-break-only changes; gate-precheck failures.
* **Clustering**: the game is the independent unit; within a game, decisions sharing a fingerprint are one
  situation and their repeats are reported as multiplicity; configurations are summarised as a range; intervals are
  exact over games within a condition.
* **Fidelity**: the captured decisions replay to their recorded trace digests; observer time is measured.

## Planning sensitivity

`scripts/ownership_sensitivity.py` takes the game as the unit (q = share of games with at least one S1
lower-attack-level owner) over the grid 1%, 2.5%, 5%, 10% and 20%. It reports the diagnostic games needed for 5, 10
and 20 affected games with 90% assurance; what the 360-game registered layout would show; what a 720-game A/B of the
registered layout could resolve, using the registered experiment's C2/C3 margin standard error as a stated planning
assumption (not a power calculation: the outcome variance in affected games is unknown); the per-affected-game loss a
suite-level non-inferiority margin of 10 points would hide; and the games per arm a mechanism-targeted design would
need for 30 affected games.

## Future A/B measurement design (not registered)

* **Mechanism metric**: among S1 components with a lower-attack-level first owner and a passing precheck, the share
  owned by the first shooter. `baseline-v2`: all of them by definition; candidate: none, deterministically. Plus:
  designation records only in such components, none elsewhere.
* **Safety and outcome**, from the project's existing methodology: C2/C3 score-margin non-inferiority, analysed both
  over the suite and over affected games identified symmetrically in both arms by the observer; code-516 refusals;
  total refusals and any new refusal class; code 1804; project-gate rejections (must stay 0); emitted shots and
  duplicate same-target commands (must stay 0); no-op and fallback counts; whether the designated owner's target
  disappears in the step, where measurable.
* Attack-level improvement is the mechanism and never a success metric. No claim is made that ownership by the
  higher attack level should raise the score.

## Candidate risks

| Risk | Evidence or test that would address it |
|---|---|
| a higher attack level may not mean more realised damage | target fate after designated versus first-come shots in the diagnostic and in the A/B (judge records, units gone); no prior assumption |
| the earlier, lower-attack-level unit may have fewer useful alternatives | in S1 it has no other target by definition; the oracle reports its fallback (occupy, move, nothing) |
| promoting the later claimant displaces useful fire from the former owner | in S1 the former owner has no other shoot candidate, so no alternate fire is lost; its occupation or movement fallback is reported |
| changed ordering alters stochastic combat trajectories | expected after the first changed decision; the A/B must compare outcome distributions, never single games |
| S1/S2 misclassification alters coupled components | invariant I3, synthetic S2 cases, and a replay check that no decision without an S1 designation changes |
| a designated owner failing the gate leaves the target idle | the pass-1 precheck uses the identical pure check; I5 and I6 tested, including a forced precheck failure |
| attack levels may not be comparable across unit or weapon classes | the diagnostic records attack-level pairs by unit class pair; the A/B reports outcomes by pair; no cross-class claim before that |

## Implementation contract (for a later turn, only if justified)

* Name: `highest-attack-claimant reservation`; parent `baseline-v2`; a new candidate identity, nothing promoted.
* Allowed source delta: one new experiment module subclassing the `baseline-v2` policy, adding pass 1 and the one
  exclusion in pass 2 with its trace record; no change to any existing file of `baseline-v2`'s source set.
* S1 definition, S2 and S3 fallback, claimant extraction, ownership keys and gate precheck exactly as above.
* Trace: a new list `ownership_designated` with, per excluded unit, the target, the designated owner, the deciding
  key, the excluded options and the unit's effect; reason `same-step-highest-attack-claimant`; present only when a
  designation exists.
* Invariants I1 to I9.
* Forbidden: any other change of candidate generation, ranking, order, occupation, movement, gate or memory; any use
  of S2 components; any score, damage or hit-point model; any scenario-specific rule.
* Public tests: S1/S2/S3 classification; every tie case; multi-weapon claimants; forced precheck failure; I4 on a
  generated corpus; determinism; golden chain for the new identity; mutation tests.
* Private replay: the audit's verified population, with zero unexplained differences from `baseline-v2` and every
  difference inside a designated S1 component.

## Decision rule (declared before the analysis)

* `ABANDON TARGET-ALLOCATION LINE` if the strict S1 scope retains none of the audit's 6 mismatch situations, or if
  the S1 oracle finds a changed component in which the designated owner does not shoot its target.
* `IMPLEMENT CANDIDATE FOR OFFLINE VALIDATION` only if on-policy `baseline-v2` evidence (D1) contains S1 mismatch
  situations in at least two games. The audit already found no mismatch of any kind in D1's captured decisions, so
  this condition is known not to hold; it is stated so that the rule is complete.
* Otherwise `RUN PROSPECTIVE V2 PREVALENCE DIAGNOSTIC`.

## Reproduce

```
python scripts/ownership_sensitivity.py [--check]      # public inputs; evaluation/target-ownership-design-1/sensitivity.json
python scripts/analyze_ownership_design.py [--check]   # private corpora; evaluation/target-ownership-design-1/analysis.json
```
