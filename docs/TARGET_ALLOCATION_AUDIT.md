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
