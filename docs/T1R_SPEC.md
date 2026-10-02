# T1-r specification and gate G6

Specification of the revised deployment-split candidate (T1-r), written after the diagnosis in `docs/T1R_DIAGNOSIS.md`
and before any implementation. It states the three required rules, the correction the diagnosis calls for, the analysis
population, and gate G6 with its verdict. Nothing here is registered; no engine run follows from it.

## Rules required of any T1-r

1. **Probe and stop.** In the first deployment decision issue one deployment split (type 314) for the most eligible
   operator (lowest `obj_id` among the eligible). In the next decision read the fresh feedback (lesson L2: only entries
   not present in the previous decision's feedback at the same `cur_step`): on code 103 for that action, mark the split
   action unavailable for the rest of the game, issue no further split, and end deployment through `baseline-v2`'s
   rule; otherwise continue with the remaining eligible operators. The probe's outcome is stored in the memory, so the
   decision stays a function of observation and memory, and it is the seat-observable runtime criterion that defines the
   analysis population (below).
2. **Stack-void avoidance.** Never issue a split whose product would raise the count of own ground units (operators not
   `on_board`) in the parent's hex above the stacking limit of four (lesson L3), counting the products of splits issued
   earlier in the same decision. Record each predicted void in the trace's diagnostics so the capture can verify the
   prediction against the engine (every split issued must take effect; every skipped split must be one that would have
   been voided).
3. **Play stage unchanged.** `baseline-v2`'s play stage, objectives and reservations are not touched.

## The correction the diagnosis calls for

The diagnosis attributes the 80-point loss to a standing block under the stacking limit: more than four ground units
bound for one objective along one route cannot pass the objective's hex and its neighbour once the objective is
occupied, and the play stage never re-orders a unit that is executing a move. Splitting caused the loss only by raising
the number of units above the route's capacity; the units themselves were sound.

A deployment-side rule can prevent that block only by keeping the number of ground units that will travel together at
or below the stacking limit. Written as a seat-observable predicate it reads: split an operator only while the number
of own ground vehicle units after the split stays at or below four. In the diagnosed scenario the seat already has four
vehicle operators, so the predicate allows no vehicle split at all, and in every frozen scenario with more than four
ground operators it allows none either. The predicate avoids the loss by removing the mechanism the hypothesis relies
on (more independent units with full ammunition): a T1-r under it is `baseline-v2` in all but the smallest forces.

A weaker predicate (at most four ground units per unheld objective, i.e. eight here) does not remove the block: the
play stage sends every unit to the same nearest objective first, so eight units still form a column of eight against a
capacity of four at the first objective. A predicate keyed on route geometry (how many units will share one path) is
not seat-observable before play begins and would be a lookup table in disguise.

The correction that addresses the mechanism itself is in the play stage: capacity-aware movement (at most four units
bound for one destination hex at a time, or a unit whose move has not advanced for a fixed number of steps gets a new
order). That is a different candidate, on the stable play stage of `baseline-v2`, and needs its own justification,
design and registration; it is proposed in `docs/TACTICAL_FRONTIER.md` as PS-1 and not begun in this sprint.

## Analysis population

Games in which the probe's split was accepted (no code 103 on the probe), identified from the candidate seat's own
memory and trace in the record, never from a scenario identifier. In Sprint 1 that population would have been the
three accepting scenarios.

## Gate G6

Proceed to WP7 (a preregistered screen of T1-r) only if all of:

| Condition | Verdict |
|---|---|
| WP5 attributed the loss with at least one SUPPORTED hypothesis | met: H3 supported (primary), H2 supported (amplifier) |
| T1-r addresses the attributed loss by a seat-observable rule | **not met**: the only deployment-side rule that prevents the block forbids the splits that carry the hypothesis; the correction belongs to the play stage, outside T1-r's allowed delta |
| tests, mutation and offline replay checks pass | not reached |

**G6 fails.** The sprint ends after WP6 with the T1 line set to SHELVED in `docs/TACTICAL_FRONTIER.md`: not rejected
(the mechanism was never tested without the block; the one scenario where the force nearly doubled scored +281.33 in
Sprint 1) and not blocked by the engine, but shelved until a play-stage candidate removes the block. Rules 1 and 2
above are kept as the specification any later deployment-split candidate must satisfy.

Choice recorded: the probe-and-stop and stack-void rules were not implemented in this sprint, because the gate fails
on the correction and an implementation of a shelved candidate would be code without an experiment. The owner decides
whether PS-1 opens.
