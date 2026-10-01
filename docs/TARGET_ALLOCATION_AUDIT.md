# Target-allocation audit

`target-allocation-audit-1` is a read-only audit of one consequence of `baseline-v2`'s same-step shoot-target
reservation (`docs/BASELINE_V2.md`): within a seat and a step, a target is owned by the first unit, in ascending id
order, whose shot at it passes the gate, whatever that unit's attack level. It asks:

1. what happened to the units the reservation displaced;
2. whether first-come ownership gives a target to a weaker shooter while a stronger eligible shooter is displaced;
3. whether displaced units get a useful alternate action or do nothing;
4. whether reserved targets disappear or survive in the actual `baseline-v2` trajectory;
5. whether the evidence justifies designing one future target-allocation experiment.

No engine session is opened, no policy changes, no candidate is implemented and nothing is preregistered. The
audit only reconstructs `baseline-v2`'s own decisions on existing private states and runs the frozen
`baseline-v2` on modified copies of them for one read-only oracle. A no-op is not assumed to be a mistake.

This document was committed with the reconstruction (`src/miaosuan_agent/evaluation/allocation_audit.py`), its
synthetic tests (`tests/test_allocation_audit.py`) and the driver (`scripts/audit_target_allocation.py`), before
the driver was run on any private state. Results are appended under "Results".

## Population

**The registered arm cannot be reconstructed.** The shoot experiment's group C (360 games, `baseline-v2` in both
seats or against the inert control) displaced 1,329 units: 840 shot another target, 17 occupied, 12 moved and 460
did nothing (`docs/EVALUATION_SHOOT_RESERVATION.md`). Its records hold per-seat counts only; no decision-time
observation was kept. Its public per-configuration means give only the context below: 389 of the 460 no-ops
(85%) are in C1, where both seats run `baseline-v2`, and 377 of them in four scenarios.

**The audited population is every decision of the existing private corpora whose decision-time observation is
kept and on which `baseline-v2`'s decision can be verified.**

| Corpus | Source | Policy that played | Verification required | Trajectory evidence |
|---|---|---|---|---|
| D1 | residual-516 diagnostic, 32 games of 1930331196 C3, every captured snapshot (both kinds: event windows and periodic samples) | `baseline-v2`, runtime-r2 | `baseline-v2` reproduces the recorded actions, trace digest and memory exactly | the compact log of every step: submitted batch, feedback, new judge records, units gone; the actual `baseline-v2` trajectory |
| D2 | the routing remediation's replay corpus, 8 games, one per scenario, C1, both seats | `baseline-v0` | `baseline-v0` reproduces the recorded decision exactly, and every unit on which `baseline-v2` differs from it carries `baseline-v2`'s own reservation record | the opposing seat's own view at the next step, only where the recorded actions equal `baseline-v2`'s; the trajectory is `baseline-v0`'s |
| D3 | the latency diagnostic's captured decisions, 5 games (2130511121 C2 and C3, 2010131194 C3) | `baseline-v1` | `baseline-v1` reproduces the recorded trace digest, and every difference of `baseline-v2` from it carries a shoot-reservation record | none |

D2's and D3's states come from other policies' trajectories, so they show what `baseline-v2` would decide in those
states, not how often such states arise under `baseline-v2`. Every count is reported per corpus as well as pooled,
and none is extrapolated to the registered arm.

**Units of analysis.** A *collision decision* is one seat-decision in which at least one unit had a shoot option
excluded by the reservation. A *collision group* is one target of one collision decision whose options were
excluded for at least one later unit. A *displaced unit* is one unit of one decision whose preferred shoot option
was on a reserved target (the trace effect is not `unchanged`). Units whose excluded options were not their
preferred ones (effect `unchanged`) are counted, not classified.

## Definitions

Everything is read from the seat's own observation and `baseline-v2`'s own decision on it.

* **Candidate**: a shoot option `baseline-v2` would consider (well-formed, attack level at least 1).
* **Attack level**: the option's documented result-table index. It is compared as an ordinal and never converted
  to damage, kill probability or expected value.
* **Processing order**: `baseline-v2`'s order (ascending unit id), read from its trace.
* **Reserver**: the unit named as `reserved_by` in the trace's exclusion records. Its level and weapon on the
  target are its best candidate on that target (its selection, since `baseline-v2` ranks by level, target, weapon).
* **Preferred target**: the target of a unit's best candidate before any exclusion, by `baseline-v2`'s rank
  (highest attack level, then lower target id, then lower weapon id). `baseline-v2` records it in the unit's detail
  only when the unit still selects an action, so it is derived for every displaced unit and checked against the
  record wherever the record exists.
* **Claimants** of a group: the reserver and the units displaced from that target. **Eligible** units: every unit
  with any candidate on the target. A unit's level on a target is its best candidate on it.
* **Stronger displaced**: a displaced claimant whose level on the target is strictly greater than the reserver's.
* **Reserver rank**: 1 plus the number of distinct claimant levels above the reserver's level.
* **Coupled component**: groups of one decision connected by a shared eligible unit.

**Consistency checks** (expected: none fail). Every excluded option is a candidate in the observation; the derived
preferred target is on an excluded target exactly when the effect is not `unchanged`; it equals the recorded one
where recorded; a `fallback-none` unit selects nothing; the reserving shot was emitted and is the reserver's best
option on the target; a fresh `baseline-v2` instance decides identically on the same observation. Any failure is
reported as an implementation defect.

## Displaced-unit outcomes

**Fallback class**, from the trace effect: F1 alternate shoot (`alternate-target`), F2 occupy, F3 move, F4 no-op
(`fallback-none`).

**F4 subreasons**, recomputed from the decision-time observation under the baseline contract:

* shoot: "its only shootable target was reserved" or "every shootable target was reserved";
* occupy: "not listed" or "suppressed by the same-step objective reservation";
* move: the reason of `baseline-v2`'s own movement step (`move_candidates` with the router's objective targets
  set as `baseline-v2` sets them), compared with the reason in the unit's trace;
* any listed action type outside the baseline's supported types (move, shoot, occupy), reported, never treated
  as an available action.

**Legal-action opportunity (defect check).** A no-op unit with an unreserved shoot candidate, an unsuppressed
listed occupation or a move candidate would contradict the baseline contract. Such a unit is reported as a defect
for separate investigation; it is not turned into a heuristic.

**Redirects** (F1): the attack level of the preferred option against the alternate one, and in D1 the alternate
target's outcome.

## Reserved-target outcome

For each group, in the step of the decision: T1 the target disappeared in that step, T2 it was still present,
T3 unavailable. D1: from the compact log's units gone, with the reserving shot's feedback (accepted, refused with
its code, no feedback), whether a judge record of that shot appeared, and whether other units acted on the target.
D2: T1 or T2 from the opposing seat's own view at the next step, only where the recorded actions equal
`baseline-v2`'s, otherwise T3. D3: T3. These are co-occurrences, never causes: a target that disappeared was not
necessarily destroyed by the reserving shot.

## Short-horizon follow-up

Fixed before the audit: **1, 2 and 5 steps**. For each displaced unit in D1 (the only corpus with a `baseline-v2`
trajectory), over the decisions at steps k+1 to k+h: whether the unit acted at all, shot, shot its original
target, moved or occupied; and after step k+h whether the unit and the original target were still present.
Descriptive only; a horizon that runs past the end of the game is not observed.

## Allocation oracle

* **O-A**: `baseline-v2` exactly (the reconstruction above).
* **O-B**: strongest-existing-attack-first ownership. For each group, the strongest claimant is the one with the
  highest level on the target, ties broken by lower weapon id, then processing order (the existing deterministic
  fields; nothing else is used). If it is not the reserver, the oracle removes the target's candidates from every
  unit processed before it and lets the frozen `baseline-v2` decide on that copy. The group is **unambiguous**
  when only the reserver and the strongest claimant change action and the strongest claimant then shoots the
  target; otherwise it is **coupled or ambiguous**, because the change reaches other units. No matching, search,
  optimiser or learned value is used. O-B is a measurement, never a policy, and is not proposed as one here.

For unambiguous owner changes the audit reports the level gained, whether the change came from a higher level or a
weapon tie-break, what the former owner and the promoted claimant did instead, and the change in the number of
shots. Each owner-changing O-B run is repeated and must give the same result.

## Gate and disposition (declared before the audit)

| Gate | Condition |
|---|---|
| G0 | at least 30 reconstructable collision groups |
| G1 | strictly lower-attack ownership with a stronger claimant displaced in at least 10% of collision groups and in at least 10 groups |
| G2 | such groups occur in at least two scenarios |
| G3 | the ranking fields are in the seat's own observation (attack level, target id, weapon id, unit order: true by construction, not measured) |
| G4 | O-B is deterministic: total tie-breaks and identical repeated runs |
| G5 | O-B changes the emitted actions in at least 10 decisions |
| G6 | O-B is isolable as one tactical variable (only the reserver and the promoted claimant change) in at least half of the owner-changing groups |
| G7 | no implementation defect: no consistency check fails and no no-op unit has a supported action left |

* G0 fails: `BLOCKED BY INSUFFICIENT REPLAY EVIDENCE`.
* G0 to G7 all hold: `DESIGN TARGET-ALLOCATION CANDIDATE`. That disposition authorises designing one candidate in
  a later turn; it does not implement or register anything.
* Otherwise: `NO TARGET-ALLOCATION EXPERIMENT JUSTIFIED`.

The thresholds are fixed here and are not revised after the audit.

## Results

Run on the server on 2026-10-01 (UTC+8), offline, without the engine: driver commit `5b4fe4b`, Python 3.10,
`OPENBLAS_NUM_THREADS=1`, 211 s. The first run, at the plan commit `6be3b16`, gave the same figures; the review then
added the descriptive `situations` block (commit `5b4fe4b`), and the rerun reproduced every earlier figure unchanged.
The gate and the disposition rule were not changed. Figures: `evaluation/target-allocation-audit-1/audit.json`.

### Fidelity

* D1: 506 of 506 snapshots reproduced exactly by `baseline-v2`.
* D2: 33,696 of 33,696 decisions reproduced exactly by `baseline-v0`, and every difference of `baseline-v2` from it on
  all 33,696 is carried by `baseline-v2`'s own reservation records.
* D3: 51 of 97 captured decisions reproduced by `baseline-v1`, all explained. The other 46 are excluded under the
  declared rule; a private check found every one of them reproduced exactly by the inert control policy, i.e. they are
  the opponent seat's decisions. None of the 51 `baseline-v1` decisions has an exclusion, so D3 contributes no
  collision group; the captured states in which `baseline-v2` would exclude an option are all inert-seat states.
* Reconstruction inconsistencies: 0. Repeated O-B runs that differ: 0.

### Audit corpus

| Unit of analysis | D1 | D2 | D3 | Total |
|---|---|---|---|---|
| verified decisions | 506 | 33,696 | 51 | 34,253 |
| collision decisions | 12 | 90 | 0 | 102 |
| collision groups | 12 | 98 | 0 | 110 |
| displaced units | 12 | 98 | 0 | 110 |

14 further unit-group pairs had options excluded on a target they did not prefer. The 110 groups are 64 distinct
situations (same game, seat, target and eligible units): 41 occur once, the rest recur, and 37 of the 46 recurrences
come exactly 75 steps after the previous one.

Representativeness: the registered arm displaced 1,329 units; of its 460 no-ops, 389 were in C1 and 377 in four
configurations. The audit has 98 groups from C1 states of `baseline-v0` games (one game per scenario) and 12 from
`baseline-v2`'s own trajectory in 1930331196 C3. Nothing below is extrapolated to the registered arm.

### Collision structure

* Claimants per group: 1 in 9 groups (the reserver only; the excluded options were not the units' preferred ones), 2
  in 92, 3 in 9. Eligible units: 2 in 88, 3 in 22.
* Coupling: 102 components, 94 with one target and 8 with two; 88 involve two shooters and 14 three.

### Current reservation ownership

* The reserver had the highest attack level among the claimants in 96 of 110 groups (87.3%), and in at least 78 of
  those another claimant was tied with it at the top level (92 groups had two or more claimants at the top level, at
  most 14 of them with a weaker reserver). In most collisions first-come ownership selects among equals.
* In 14 groups (12.7%) the reserver was strictly weaker than a displaced claimant (reserver rank 2 in all of them), by
  1 level in 1 group, 2 in 6, 3 in 3 and 4 in 4. They displaced 21 stronger units: 5 shot another target and 16 did
  nothing.
* All 14 are in D2: 6 distinct situations in 4 games of 4 scenarios. `baseline-v2`'s own trajectory (D1) has none.
* In 6 groups a unit with a stronger option on the target preferred another target and was not a claimant.

### Displaced-unit outcomes

| Outcome | Count | Fraction |
|---|---|---|
| F1 alternate shoot | 84 | 76.4% |
| F2 occupy | 0 | 0.0% |
| F3 move | 0 | 0.0% |
| F4 no-op | 26 | 23.6% |
| total | 110 | 100.0% |

D1: 12 alternate shots. D2: 72 alternate shots and 26 no-ops.

### No-op root causes

All 26 no-op units are in D2 (11 distinct situations, all C1).

* Shoot: the only shootable target was reserved for 23; every shootable target was reserved for 3.
* Occupy: not listed for all 26.
* Move: no objective outside own control for 20, movement not listed for 5, standing on an objective outside own
  control (occupation not listed) for 1. The recomputed reason equals the trace's in 26 of 26.
* Every one of them listed at least one action type outside the baseline's supported types (move, shoot, occupy): type
  6 for 20, 11 for 20, 10 for 5, 16 for 1. They are outside the contract, not missed options.
* Legal-action opportunity: 0 unreserved shoot candidates, no unsuppressed occupation, no move candidate: 0 defects.
* 16 of the 26 were stronger on the reserved target than its reserver; for all of them the objectives were already
  under own control and occupation was not listed.

### Reserved-target outcomes

| Class | Groups | none stronger | stronger displaced |
|---|---|---|---|
| T1 disappeared in the step | 12 | 12 | 0 |
| T2 still present | 1 | 1 | 0 |
| T3 unavailable | 97 | 83 | 14 |

* D1: all 12 reserved targets disappeared in the step; the reserving shot was accepted and has a judge record in each,
  and no other unit acted on the target.
* D2: 1 group is comparable (recorded actions equal to `baseline-v2`'s); in the others `baseline-v0` fired the
  duplicate shot that `baseline-v2` removes, so its next state says nothing about `baseline-v2`'s. Labelled
  separately, in the recorded `baseline-v0` trajectory, where both claimants fired, the target was still present at
  the next step in 75 of 98 groups (11 of the 14 with a stronger displaced claimant) and absent in 23.
* By fallback: T1 for the 12 D1 alternate shots, T3 for the other 72 alternate shots and all 26 no-ops.

### Short-horizon follow-up

Only D1 has a `baseline-v2` trajectory, and its 12 displaced units are alternate shooters. At 1, 2 and 5 steps all
were present, none acted, and the original target was gone; none acted again before the end of its game (private
check). No no-op unit is in D1, so the follow-up of no-op units is not observed.

### Alternate-target redirects

84 redirects: 63 at the same attack level as the preferred option, 21 lower (by 1 level: 13, 2: 2, 3: 6). The 12 D1
redirects are the H4 events of the residual-516 diagnostic (12 of 12 matched by game, step and shooter): the alternate
target disappeared in the step and the redirected shot was refused with code 516. The 72 D2 redirects have no outcome
evidence.

### Allocation oracle

* O-A reproduces `baseline-v2`; O-B leaves the owner unchanged in 96 groups and changes it in 14 (14 decisions),
  always for a higher attack level, never by the weapon tie-break.
* Unambiguous: 13; coupled: 1 (the change reached a third unit).
* In the 13 unambiguous groups the target's attack level rose by 2 in 6, 3 in 3 and 4 in 4. The former owner then did
  nothing in 9 and shot another target in 4; in the same groups the promoted claimant had done the same before
  (private check). The number of shots and every non-shoot action stayed the same.

### Gate

| Gate | Holds |
|---|---|
| G0 at least 30 reconstructable collision groups | yes |
| G1 strictly lower-attack ownership with a stronger claimant displaced in at least 10% and at least 10 groups | yes |
| G2 such groups in at least two scenarios | yes |
| G3 the ranking fields are in the seat's own observation | yes |
| G4 O-B deterministic (repeated runs identical, total tie-breaks) | yes |
| G5 O-B changes the emitted actions in at least 10 decisions | yes |
| G6 O-B isolable (only reserver and promoted claimant change) in at least half of owner changes | yes |
| G7 no implementation defect (no reconstruction inconsistency, no no-op with a supported action left) | yes |

G3 holds by construction (the oracle reads only the seat's own options), not by measurement.

**Disposition: `DESIGN TARGET-ALLOCATION CANDIDATE`.**

### Review finding

The gate counts collision groups, as declared. The review found that the 14 groups behind G1 and G5 are 6 recurring
situations in 4 games, each the single recorded `baseline-v0` C1 game of its scenario, and that `baseline-v2`'s own
trajectory contains none. The gate holds as declared; the evidence is narrower than 14 independent observations. A
design built on it must treat the situation, not the group, as its unit, and must not assume that the registered arm's
460 no-ops arise in such states.

### Answers

1. Displaced units: 76.4% shot another target, 23.6% did nothing; none occupied or moved.
2. First-come ownership gave the target to a strictly weaker shooter in 14 of 110 groups (6 situations); in the other
   96 the reserver was the strongest claimant, in at least 78 of them tied with another.
3. Every no-op was contract-correct: no supported action was left. 16 of the 26 no-op units were stronger than the
   reserver.
4. In `baseline-v2`'s trajectory the 12 reserved targets all disappeared in the step; elsewhere there is no
   `baseline-v2` outcome evidence.
5. The declared gate holds: `DESIGN TARGET-ALLOCATION CANDIDATE`, with the review finding above.

## Not claimed

* Nothing about the registered arm's 1,329 displaced units beyond its published counts.
* No causal effect of any allocation on scores, kills or refusals; no estimate of damage.
* Nothing about a policy that would use O-B.

## Reproduce

```
python scripts/audit_target_allocation.py           # writes evaluation/target-allocation-audit-1/audit.json
python scripts/audit_target_allocation.py --check   # rebuilds and compares
```

The private corpora and the private per-group details (`local/diagnostics/allocation/`) stay outside Git.
