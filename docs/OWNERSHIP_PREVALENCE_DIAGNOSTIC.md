# Target-ownership prevalence diagnostic

`baseline-v2-target-ownership-prevalence-1` is a registered, read-only, prospective diagnostic. It measures how
often unchanged `baseline-v2`, on its own trajectories, meets an actionable isolated single-target shoot collision
in which its first-by-unit-order owner has a strictly lower attack level than another eligible claimant. It is an
incidence study: no candidate policy runs, nothing that plays changes, and no tactical effect is estimated.

This document was committed with the manifest, before any engine session of the study. The manifest is
`evaluation/baseline-v2-target-ownership-prevalence-1/manifest.json` (canonical SHA-256 `d88c2416…`), built by
`scripts/build_prevalence_manifest.py` from `src/miaosuan_agent/evaluation/ownership_prevalence.py`; where this text
and the manifest differ, the manifest governs. Results are appended under "Results".

## Why

The target-ownership design study (`docs/TARGET_OWNERSHIP_DESIGN.md`) specified one candidate for isolated
single-target collisions (S1) and found the missing fact to be on-policy incidence: its 9 historical S1 ownership
changes are 3 situations in 2 games, all from replayed `baseline-v0` C1 trajectories, and the captured
`baseline-v2` decisions covered 0.55% of their games. Those 9 changes are not an incidence estimate and are not
pooled with this study.

## Frozen identities

| Item | Value |
|---|---|
| Tactical baseline | `baseline-v2` (code identity `baseline-v2-candidate-shoot-target-reservation`), policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, golden trace chain `0d16c814c03909ed89303a776b276b4cc441cd047450a063329009458654910f` |
| Control | `inert-v0`: ends deployment, then never issues a unit action |
| Runtime | `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`) |
| Scheduler | `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90`; the manifest builder refuses a checkout whose pool computes another identity |
| Execution | `execution.workers` 32, through `scripts/run_evaluation.sh --plan prevalence` |
| Observer | sources `evaluation/ownership_prevalence.py`, `evaluation/ownership_design.py`, `evaluation/allocation_audit.py`, `evaluation/shoot_counterfactual.py`, digest `e53e5bac…` in the manifest; every capture must name it |
| Engine ledger | ends at session 1897 before the study |

## Events

For one active `baseline-v2` seat at one decision, the shoot graph is the design study's: shooters are the
controllable units, in `baseline-v2`'s processing order, with at least one shoot candidate (extracted by
`baseline-v2`'s own `engage_candidates`), targets are their candidates' targets, and an edge carries the shooter's
best candidate on the target by `baseline-v2`'s within-unit rank (attack level, then weapon id).

| Event | Definition |
|---|---|
| E0 shoot collision | a connected component with at least two shooters (S1 or S2); in a connected bipartite component with two shooters some target has both as neighbours, so this is exactly "a target with more than one eligible shooter" |
| E1 S1 collision | a component with exactly one target and at least two shooters |
| E2 structural mismatch | in an S1 component, the first shooter in processing order (`baseline-v2`'s owner) has a strictly lower attack level on the target than another shooter; equal levels never make E2, and weapon ids play no part |
| E3 candidate-applicable mismatch (**primary event**) | E2, and the exact shoot action of the claimant the design would designate (highest attack level, then lower weapon id, then processing order) passes the project gate's single-proposal check in the same decision-time context |

An E2 whose designated claimant fails the gate check is counted separately and is not an opportunity: the candidate
would keep `baseline-v2`'s behaviour there. S2 components are counted under E0 only.

## Population and schedule

* Unchanged `baseline-v2` on the 8 frozen scenarios of the shoot experiment, under C1 (`baseline-v2` mirror), C2
  (`baseline-v2` red against the inert control) and C3 (`baseline-v2` blue against the inert control), 15 games per
  configuration: **360 games**, `<scenario>.<condition>.p01` to `.p15`. No candidate arm, no C4.
* Order: round r plays game r of every configuration once; within a round configurations are ordered by the SHA-256
  of `<design_sha256>:<r>:<config>`, and a round never starts with the previous round's last configuration. The
  queue is fixed by the manifest; no game is added, removed or reordered.
* **Exposure differs by condition.** A C1 game has two active `baseline-v2` seats (1 and 11); a C2 or C3 game has
  one (seat 1, respectively seat 11). The game remains the independent cluster; the two seats of a C1 game are not
  independent games, and raw C1 and C2/C3 game shares are compared only together with this exposure difference.

## Observer

A read-only observer (`ownership_prevalence.Observer`), called by the game loop after every engine step once every
seat has decided. For each decision of each `baseline-v2` seat it reads the seat observation, the memory before the
decision, the actions and the trace; it returns nothing to the policy or the engine. A decision whose
`valid_actions` list shoot options for fewer than two units cannot hold a collision and is only counted.

* **Recorded privately per component** with at least two shooters: decision index, seat, faction, kind, shooter,
  target and edge counts, the structural fingerprint, E0 to E3; for S1 also each claimant's attack level in
  processing order, the deciding key of the designed rule, the designated claimant's gate check, the number of
  claimants at the top level and whether their weapons differ, the unit classes (type, sub_type) of owner and
  designated claimant, whether their weapons are equal, `baseline-v2`'s emitted action category for every claimant,
  whether the owner's shot was emitted, the trace digest, and private identifiers (shooters, target, weapons).
* **Snapshots**: the seat observation, memory, actions and trace digest of every decision holding an S1 component and
  of every 200th decision of each `baseline-v2` seat, for the offline replay check and later offline work.
* **Self-checks**: the observation's canonical digest before and after classification (any difference is an observer
  defect); each S1 component's consistency with `baseline-v2`'s emitted actions (the owner shot the target, no later
  claimant shot).
* Storage: `local/evaluation/<study>/capture/<game>.ownership.json` and `<game>.snapshots.pkl`, created exclusively.

**Evidence before registration.**

* Synthetic tests (`tests/test_ownership_prevalence.py`): with and without the observer, the fake-engine game record
  is identical; only the registered policy's seats are observed; ties and weapon keys are not E2; a failed gate check
  is E2 but not E3; S2 is never E2 or E3; the observation is unchanged and the classification deterministic; the gate
  check is the designated claimant's; an observation mutation is counted; the decision rule's boundaries. 20 of 20
  mutants of the module are killed by these tests.
* Preserved real states (`scripts/ownership_prevalence.py check-observer`, `observer-check.json`): the classifier on
  every verified decision of the target-allocation audit's corpora leaves every observation unchanged, a fresh
  `baseline-v2` decision after it is identical, it is deterministic, the pre-filter never skips a decision with two
  shooters, and its E0 to E3 counts equal the design study's oracle on the same population. Result: 34,253
  decisions, 105 classified and 34,148 skipped by the pre-filter (none of them with two shooters), E0 102, E1 18,
  E2 9, E3 9 as in the design study, 0 problems.

## Fingerprint

Pinned, unchanged from the design study (`ownership_design.fingerprint`, schema
`ownership-structural-fingerprint/1`): configuration, seat faction, component kind, and per shooter in processing
order its edges as (target index, attack level, weapon rank), whether occupation and movement are listed and whether
it stands on an objective outside own control, plus whether any objective is outside own control; a 16-hex SHA-256
prefix with no unit, target or weapon id. Its source is covered by the observer digest.

## Estimands and intervals

* **Primary**: the share of registered games with at least one E3 event, for C1, C2, C3 and the fixed suite. The
  suite share weights the 24 configurations equally, which with 15 games each equals the pooled share.
* **Secondary**: active-seat-game share of E3 (descriptive in C1); games with E2 and with E1; decisions with E3; E3
  components and distinct E3 fingerprints per affected game; multiplicity per fingerprint, games per repeated
  fingerprint, maximum within-game and cross-game repetition; scenario and configuration distribution; attack-level
  gaps; claimant counts; designated-claimant gate passes and failures; unit-class pairs, same-class and cross-class
  E3, equal and different weapons; weapon-tie facts for the design's open decision D-1.
* **Clustering**: the game is the independent unit. Decisions, components and fingerprints are never treated as
  independent samples; within a game, components sharing a fingerprint are one situation.
* **Intervals**: exact Clopper-Pearson 95% over games (120 per condition, 360 for the suite, 15 per configuration,
  the last reported but not interpreted). None over decisions, components, fingerprints or C1 active-seat-games.
* **Class comparability** is recorded and reported (same-class and cross-class E3) but does not redefine E3, which
  stays the registered attack-level comparison.

## Integrity and instrumentation

* Exactly the 360 registered games, one record, start marker, log and capture pair each, none overwritten; the
  dispatch queue equal to the registered order; capture digests equal to those in each record; capture decision
  counts equal to the record's; every capture naming the registered observer digest.
* Every record names the manifest, the `baseline-v2` policy source, `baseline-v1-runtime-r2` with its variable, 32
  workers and the registered scheduler, from a clean harness.
* Sessions 1898 to 2257, consecutive, each opened and closed once; engine state, `home/` and package unchanged;
  ledger snapshots before and after; the engine state files, the authentication file among them, unchanged in hash,
  size and modification time; no leftover process.
* Every game passes the independence comparison with its configuration's serial reference, derived from the 15
  serial `baseline-v2` games of the shoot experiment's group C (`references.json`: 8 deterministic configurations,
  which must reproduce a serial chain exactly, and 16 stochastic ones, which must share the common prefix and not
  reproduce a serial chain). This is the in-run proof that the observer did not change what was played.
* Every in-game replay check agrees; offline, a fresh `baseline-v2` policy recomputes every captured snapshot's
  decision with identical actions and trace digest; no observation mutation, consistency problem or observer error.
* **If any of these fails, the study stops before interpretation**: no prevalence is reported as valid and no
  next-step decision is taken.

## Stop and failure rules

* Before the first game: the shared-server courtesy check of the concurrency qualification (other activity at most
  16 logical CPUs over 30 s, at least 16 idle beside the 32 workers), rechecked every 300 s up to 6 times; while the
  host is busy the run waits; the worker count is never changed.
* During the run: dispatch stops after 3 consecutive games that do not complete and on any other exit status. No
  game is retried, replaced or overwritten; a failed or capped game is kept and reported.
* The study stops for an observer that changes emitted actions, a policy, runtime or scheduler mismatch, ledger
  corruption, an authentication-state or package anomaly, or repeated unexpected process failure. It never stops
  because prevalence looks high or low.

## Next-step decision rule (declared before the first game)

Applied only when every integrity and instrumentation check passes.

1. `STOP TARGET-ALLOCATION LINE` unless all of: at least **5** E3-positive games; E3-positive games in at least
   **2** scenarios; at least **3** distinct E3 fingerprints; no single E3 fingerprint present in **80%** or more of
   the E3-positive games.
2. Otherwise `MORE SEMANTIC EVIDENCE REQUIRED` if more than **half** of the E3-positive games contain only
   cross-class E3 components (owner and designated claimant of different unit classes).
3. Otherwise `IMPLEMENT CANDIDATE FOR OFFLINE VALIDATION`.

Rationale, fixed now: below 5 affected games of 360 (q under about 1.4%) the design study's sensitivity puts a
targeted A/B above 2,000 games per arm for 30 affected games; 3 fingerprints is the number of historical S1 mismatch
situations, and fewer cannot show more than one periodic state; one fingerprint in 80% of the affected games is one
repeated state, confined to one configuration; a majority of cross-class comparisons calls for a semantic study of
attack levels first. Whatever the outcome, no candidate is encoded in this study.

## Not claimed

* No tactical effect: nothing here says that ownership by the higher attack level would change scores, kills,
  refusals or no-ops, or that a candidate would be beneficial.
* No candidate policy runs; the designated claimant is computed only for E3's gate check.

## Running

```bash
PYTHON scripts/build_prevalence_manifest.py --check
PYTHON scripts/ownership_prevalence.py preflight
PYTHON scripts/ownership_prevalence.py snapshot --label before
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan prevalence \
    --evaluation baseline-v2-target-ownership-prevalence-1 --workers 32
PYTHON scripts/ownership_prevalence.py snapshot --label after
PYTHON scripts/ownership_prevalence.py analyze
```

Public: the module, manifest, references, scripts, this document, `observer-check.json` and `results.json` (counts,
shares, intervals and fingerprint hashes only). Private (git-ignored): records, logs, captures and snapshots.

## Results

**The registered prefix check failed for 9 of 360 games, so the study stopped before interpretation, as registered: no
prevalence is reported, and no next-step decision is taken.** Every other integrity and instrumentation check passed.
Figures: `evaluation/baseline-v2-target-ownership-prevalence-1/results.json` (`scripts/ownership_prevalence.py analyze
--check` regenerates it from the private records and captures).

### Execution

* The registration commit `c8635dd` was on the public remote, verified at 2026-10-02T00:34:06+08:00, before the
  courtesy check and the first session. All games ran at `c8635dd` from a clean tree.
* The courtesy check passed at its first attempt (2026-10-02T00:44:38+08:00): other activity 0.21 logical CPUs over a
  30-second window, 31.8 idle beside the 32 workers.
* 360 of 360 games completed in sessions 1898 to 2257, first opened at 2026-10-02T00:45:10+08:00, the pool finishing
  after 832.2 s. No game failed, was capped, retried or replaced; the queue was the registered order.
* Game wall time: median 18.7 s, at most 231.3 s.

### Integrity

| Check | Result |
|---|---|
| records, start markers, logs, capture pairs, queue order | 360 of 360; none overwritten; captures match their records' digests and decision counts; every capture names the registered observer source |
| engine sessions | 1898 to 2257, consecutive, each opened and closed once; 1 engine state throughout; engine state files (the authentication file among them), `home/` and package unchanged between the snapshots before and after |
| execution | every record names the manifest, `baseline-v2`, `baseline-v1-runtime-r2` with `OPENBLAS_NUM_THREADS=1`, 32 workers and the registered scheduler; 1 pool run, 0 leftover processes |

### Instrumentation

| Check | Result |
|---|---|
| independence prefix (registered) | **351 of 360: fails**. Deterministic configurations: 120 of 120 games reproduced a serial chain exactly. Stochastic: 231 of 240 |
| in-game replay checks | 10,440, 0 mismatches |
| offline re-decisions of captured snapshots | 5,335, 0 mismatches in actions or trace digest |
| observation unchanged by the observer | 0 mutations |
| S1 consistency with emitted actions | 0 problems |
| observer errors | 0 |

* The observer took a median of 0.064 s per game (at most 2.72 s), 0.31% of the game's wall time (at most 1.96%).

### Why the prefix check failed (supplementary; not registered, not used to rescue the study)

`prefix-diagnosis.json` (`scripts/ownership_prevalence.py prefix-diagnosis`, added after the run) asks whether any
`baseline-v2` decision differed from a serial game of the same configuration while the states it had observed were
still identical. Over 360 games and 5,400 serial comparisons: **0**. The 9 failing games, all stochastic, in 6
configurations:

* 8 games matched the reference's state prefix, but a seat's decisions diverged before the end of the reference's
  trace prefix. Each reference is the common prefix of 15 serial games, and its trace prefix runs longer than its
  state prefix; in these games the states diverged from every serial game first, and the decisions followed.
* 1 game reproduced a serial game's entire chain (2,882 states, every decision), which the stochastic criterion counts
  as a failure because it was written to detect a shared session, not an altered game.

The registered criterion therefore measured something stricter than observer non-interference for stochastic
configurations played 15 times each. That finding does not change the registered outcome.

### Prevalence

Not reported. The captures hold the observations, but no prevalence, event or fingerprint figure was computed for this
report. Disclosure: while the run was being monitored, the capture summaries of 5 early games (component counts by
event) were displayed; none had an E3 component.

### Next step

No decision is taken: the registered rule withholds it after a failed instrumentation check. The captures of this
study stay unexamined and are not to be pooled with a later study.
