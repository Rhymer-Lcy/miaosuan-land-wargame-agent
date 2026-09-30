# Routing remediation of baseline-v1

`routing-remediation-1` is a behaviour-preserving engineering change. It replaces the full-map
shortest-path search of the frozen `baseline-v1` with one that stops once every objective the
decision reads is settled. The aim is the same actions and the same decision content for the
same input, with less intrinsic latency at the first play decision (`docs/LATENCY_DIAGNOSTIC.md`).
It is not a tactical change and not a new tactical baseline. `baseline-v1` itself stays frozen:
its source, digest, golden chain, manifests and results are untouched.

This document was committed with the registration, before the candidate was implemented or timed.
The registration is `evaluation/routing-remediation-1/registration.json`, built by
`scripts/build_remediation_registration.py` from `src/miaosuan_agent/evaluation/runtime_remediation.py`;
where they differ, the registration governs. Results are appended under "Results".

## Identities

* Parent: `baseline-v1`, policy source `1d01e48a…`, golden decision chain `11e12bf0…`.
* Candidate: `baseline-v1-routing-bounded-candidate`. Its sources are `baseline-v1`'s, byte-identical,
  plus the one added file `src/miaosuan_agent/experiments/routing_bounded.py`.
* Name if promoted: `baseline-v1-runtime-r1`. It would be a runtime of the tactical `baseline-v1`, not a
  new tactical baseline.

## The routing contract being preserved

Characterized by `tests/test_routing_contract.py` before any change:

* **Who routes.** Move candidates are computed for every controllable unit that lists movement, is not
  executing a move, has a documented movement mode, and does not stand on an objective not held by its
  side.
* **What is read.** Only the cost and path of each objective not held by the side.
* **The search.** Dijkstra from the unit's hex over the setup-supplied costs of the unit's movement mode.
  Roadblock hexes are excluded as neighbours for the two vehicle modes only, and the start hex is never
  checked against them.
* **Costs.** Entry costs are positive and finite; the boundary rejects anything else.
* **Tie-breaking and relaxation.** The frontier is a heap of `(cost, hex)`, so equal costs pop in
  ascending hex order. Settled and blocked neighbours are skipped. A neighbour's cost and predecessor
  change only on a strictly lower cost, and neighbour order is irrelevant.
* **Paths.** A path is the predecessor chain from the objective back to the start, without the start.
* **Unreachable objectives.** An objective absent from the result is unreachable and yields no candidate.
* **Choice.** The chosen objective has the smallest `(cost, objective hex)`.
* **Memo.** A first-in-first-out memo of 32 entries keyed by `(start, mode, roadblocks)`; no result
  depends on it.

## Why the bounded search is equivalent

1. The bounded search performs the full search's pops and relaxations in the same order and stops
   partway, so it is a prefix of the full run.
2. A settled hex's cost and predecessor never change later, and every hex on its path was settled
   before it. Settled hexes therefore have equal costs and paths.
3. The search stops only when every target is settled. An unreachable target keeps it running to the
   end of the frontier, which is the full run.
4. The policy reads only targets, so candidates, choices, actions and trace content are equal.
5. The bounded result exposes settled hexes only.

The memo key adds the target set to `(start, mode, roadblocks)`. Objectives change as they are taken
or lost, so a truncated result must never serve another target set. The router belongs to one agent
and one map.

## Criteria

**Equivalence**, E1-E11 in the registration:

* the parent still verifies, and the source delta is exactly the added file;
* the characterization and differential routing tests pass, and mutation testing kills every
  non-equivalent mutant;
* over every registered replay input, both agents given the same observation and memory produce equal
  action lists, equal semantic traces and equal contract errors, and neither modifies the observation.
  The semantic trace is the trace dictionary without its `policy` field. Unexplained differences: 0;
* the candidate's semantic golden chain equals `baseline-v1`'s;
* in the engine diagnostic, a shadow `baseline-v1` agent compares every decision live;
* no tactical rule and no legality check changes.

**Performance**, fixed before measurement:

* On the first play decision of 2130511121 (as in the replay corpus and as captured in the latency
  diagnostic), the candidate's median `agent.step` time with a fresh agent must be at most half of
  `baseline-v1`'s, measured interleaved in the same benchmark invocation.
* No other registered state may be slower than `baseline-v1`'s median × 1.10 + 0.2 ms.
* In the engine, the candidate's first play decision on 2130511121 must take at most half the time
  its shadow `baseline-v1` takes on the same observation.
* The basis: the diagnostic measured about 500 ms, 99% of it in Dijkstra, and estimated that 15.8% of
  the settled nodes are needed. The factor of two leaves room for the bounded search's own overhead.
  No platform deadline is assumed.

**Corpus.** 22 private files pinned by SHA-256 in `evaluation/routing-remediation-1/corpus.json`:
* the 8 recorded games of the replay corpus;
* the 9 states of the latency diagnostic;
* the captures of its 5 engine games.

The variance-study records hold no observations and cannot be replayed.

**Engine diagnostic.** Three diagnostic sessions:
* 2130511121 C1, with both seats on the candidate;
* 2130511121 C3;
* 2010131194 C3, as a small control.

No score is compared.

**Promotion.** Only if E1-E11 all hold. Otherwise the candidate is kept as failed or partial.

**Out of scope.** Garbage collection (no setting, call or threshold changes), every tactical rule, and
the shooting-conflict experiment.

## Results

None at registration.
