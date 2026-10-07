# Sprint 19: T6-G threat-entry gate, offline shadow study

**REGISTERED — OFFLINE — NO ENGINE SESSION — A SHADOW ON HISTORICAL STATES, NOT EVIDENCE THAT HOLDING REDUCES DAMAGE — NOTHING PROMOTED**

Sprint 18 (`docs/SPRINT18_FRONTIER_RESET.md`) selected T6, threat-aware movement, and named its first experiment: T6-G,
the threat-entry gate. Its registered first step is this offline shadow study. No engine session is authorized; session
2796 is not opened. If the offline gate passes, a two-session engine mechanism probe is drafted for the owner's review
and not executed; if it fails, the timing branch of T6 is closed. Dates are business dates in UTC+8.

Sections 1 to 15 are the registration. They are committed and pushed, with the gate, the analysis, the driver, their
tests and the frozen `protocol.json` and `inputs.json` (`evaluation/s19-t6g-shadow/`), before the final replay, and
are not edited afterwards. Results follow in a separate section.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `92041a1dfc27b1fb0eb187554986c4147ee291ca`, tree `b3e96d93426ddcf7356406ff3996a6369b342410`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,795 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only verify at the start of the sprint); ledger file SHA-256 `65c803504b6f93f6e6d2a7e36892078a9cd116924fbb819a8dbb595a4039e8de` |
| Privacy baseline | the 104 accepted hit lines, reproduced as the same set at the start of the sprint (919 reachable blobs) |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Frozen history | T9 `SHELVED`; Sprint 18 outcome NEXT_FAMILY_SELECTED, T6, first experiment T6-G; no historical output is changed by this sprint |

## 2. Question and scope

Sprint 18's census found that moving ground units take most of the damage (124 of 205 damage events in H0, 117 of 158
in HH), almost always from an attacker the side had already seen (120 of 124, 117 of 117), and that 230 H0 and 200 HH
`baseline-v2` move orders were threat-exposed, 88 and 101 of them followed by damage to the mover within 300 steps.

The question here is narrow: **is there enough repeated opportunity to delay entry into a currently visible enemy's
direct-fire envelope, without the gated population being dominated by the units that `baseline-v2` needs to capture
objectives?** Whether holding reduces damage is not answered here; that needs the candidate's own trajectory, which only
an engine session produces.

Offline only. No new policy in any run card, no change to `baseline-v2`, the stable core, the registered evaluator or any
historical output. No route optimisation, replanning, formation control or last-seen belief: those are other T6
branches and need a later frontier decision. No external research and no private data sent out.

## 3. Evidence seen before this registration (disclosure)

Before writing these sections the author read Sprint 18's document, rubric, selection, experiments, census and inputs,
the frontier, and the movement and timing documents of Sprints 3, 4, 10, 11 and 17. Sprint 18's T6 entry already fixed
the denominator of its offline stop item: "hold lengths to release (first gate of each episode only, since later states
are counterfactual)". No T6-G figure was computed on private data before this registration. The code was developed on
synthetic frames. Two known-answer smoke runs (`scripts/s19_t6g_shadow.py smoke`) were made on the real inputs before
the freeze, with a code revision that differs from the frozen one only by a counting helper the smoke does not use; they
print no T6-G figure:

* `never` (the gate with an empty route prefix): every Sprint 18 fidelity figure of section 8 reproduced; 0 moves
  dropped in H0 and HH; 0 ordered routes starting at the mover's current hex; shadow invariants intact.
* `exposure` (the gate's state machine driven by Sprint 18's threat-exposure predicate, no hold limit, no cooldown):
  230 moves dropped in H0 and 200 in HH, exactly Sprint 18's threat-exposed orders, so the frames, actions, threat lists
  and dropped indices are joined as intended on real data.

The structure of the HH records was read (seat order and colours: in p01 and p03 `baseline-v2` is blue, in p02 and p04
red), not their outcomes.

## 4. The frozen gate

The gate filters the action list `baseline-v2` has produced for one seat at one decision
(`src/miaosuan_agent/experiments/t6_threat_entry_gate.py`). A move (action type 1) is **dropped** when all hold:

1. the actor is an own ground unit (type 1 or 2) in the seat's own operators;
2. **current position outside**: there is at least one qualifying visible threat, and for every one of them
   `hex_distance(current_hex, enemy_hex) > range`;
3. **route entry**: among `route[0:min(5, len(route))]`, the first five hexes of the ordered `move_path` (which lists
   the hexes after the current one, as the project's router builds it, up to the destination), at least one
   satisfies `hex_distance(route_hex, enemy_hex) <= range` for at least one qualifying threat; a shorter route uses
   every hex it has; an empty route cannot trigger;
4. the unit is not in its post-release cooldown and its hold episode has not reached 150 steps (section 5).

A **qualifying visible threat** is a currently visible enemy unit (the seat observation's operators of the other colour,
any class, aircraft included) with a readable hex and at least one weapon with a published direct-fire range against the
mover's class. The range is `evaluation/t7_candidates.weapon_range` over the enemy's `carry_weapon_ids`: the longest
published direct-fire range of its weapons against personnel (mover type 1) or vehicles (mover type 2). That table was
transcribed by Sprint 5 from the published rules and used by Sprint 18 for its threat-exposure figures, so the gate and
the exposure anchors share one mapping. A weapon outside the table (indirect artillery among them) or with no published
range for the class adds nothing. "Any weapon covers" equals "the longest range covers", so taking the maximum is exact;
ranges are not averaged, the nearest enemy is not singled out, hidden weapons and unseen enemies are not inferred.
Distances are the project's `evaluation/t7_visibility.hex_distance`. No other filter is applied: no enemy cooldown,
suppression, line of fire, future visibility, predicted motion, last-seen memory, attack probability or target value.

Dropping is the only change. No replacement move, alternate route, stop, new action type, target-allocation change or
change to any other action; the remaining actions keep their order. Every unreadable field fails closed: a missing
mover, an unreadable hex in the current position or in the inspected route prefix means no gate and the move passes.

## 5. The frozen hold state machine

Per unit, on `cur_step`, from an empty memory at the start of every game (and of every side-game in the shadow):

* **Start.** No state and the condition holds: the move is dropped and an episode starts, `hold_start = cur_step`.
* **Continuation.** In an episode, a move for the unit arrives: if `cur_step - hold_start >= 150` the episode is released
  (reason `hold_limit`) and the move passes; else if the condition holds the move is dropped again (a repeat within the
  episode); else the episode is released (reason `condition_cleared`) and the move passes.
* **No baseline move.** In an episode, this decision's list holds no move for the unit: the episode is released (reason
  `no_baseline_move`). This is the simplest reading, chosen now: an episode stays active only while `baseline-v2` keeps
  emitting the move it withholds, and no future move is inferred.
* **Cooldown.** Every release sets `release_step = cur_step`. While `cur_step - release_step < 300` the unit cannot start
  an episode; a move that meets the condition then passes and is counted as a cooldown suppression. At exactly 300 it is
  eligible again.
* **Absence.** A unit absent from the seat's own operators loses its state; an open episode ends with reason
  `unit_absent`.
* **End of game.** An episode still open at the side's last decision is closed there by the analysis with reason
  `open_at_end`.

A consequence fixed now, before any replay: on HH the historical unit moved where T6-G would have held it, so its next
recorded decision usually carries no move for it (`baseline-v2` does not re-order a unit that is executing a move), the
shadow's episode ends there with `no_baseline_move`, and the 300-step cooldown follows. The shadow's synthetic hold
lengths therefore describe the replay, not holds the candidate would make, and the cooldown bounds how often one unit can
be gated on recorded states. On H0 the recorded actions are `baseline-v0`'s, so a reconstructed `baseline-v2` move can
recur while the historical unit does something else.

## 6. The evidence boundary

The recorded H0 and HH states were produced by historical policies, not by T6-G.

* **Before the first gate** of a side-game the candidate's action lists equal `baseline-v2`'s; on HH this is the genuine
  `baseline-v2` decision stream on its own trajectory.
* **The first gate** itself is a valid action-level fact: the state, the move `baseline-v2` emitted and the move T6-G
  would withhold.
* **After the first gate** every recorded state is off-policy for T6-G. Later gates, holds and releases are opportunity
  diagnostics on recorded states, never states T6-G would reach.
* H0 states are `baseline-v0` trajectories throughout, with `baseline-v2` reconstructed seat-locally; H0 is reported
  descriptively only.

The results keep the three apart: pre-divergence decisions, first-gate certificates, post-divergence opportunities.

## 7. Corpora and inputs

Exactly Sprint 18's registered populations for T6, with its pinned digests (`evaluation/s19-t6g-shadow/inputs.json`
copies the H0 and HH pins from `evaluation/s18-frontier-reset/inputs.json` and pins that file and `census.json`):

| Id | Population | Analysed |
|---|---|---|
| H0 | the 8 replay-corpus games (`baseline-v0` mirrors, C1), every decision's seat observation | both seats: 16 side-games; `baseline-v2` reconstructed on every recorded observation with its own memory, as in Sprint 18 |
| HH | the 4 full-step timelines of Sprint 12 (2130511121, `baseline-v2` against v3, both seat orders) | the `baseline-v2` seat: 4 side-games, p01 and p03 blue, p02 and p04 red; its recorded submitted actions (equal to the census reconstruction in 11,524 of 11,524 decisions) |

No other corpus enters the registered decision, and no sensitivity corpus is declared: no HI, R or S figure, no other
capture, no BOKE-2026 data, nothing of the stopped 360-game prevalence diagnostic. The loaders are Sprint 18's census
loaders (`scripts/s18_census.py`), unchanged.

## 8. Fidelity (REPLAY_INVALID)

Before T6-G is evaluated the replay reproduces Sprint 18's published figures exactly, from the same loaders on the same
pinned inputs: H0 230 threat-exposed move orders, 88 of them followed by mover damage within 300 steps; HH 200 and 101;
moving-ground damage events 124 and 117, attacker seen before 120 and 117; damage events 205 and 158; `baseline-v2` move
orders 509 and 416; the whole T6 block and the first-ownership figures of `census.json` for H0 and HH; H0 33,696
decisions, 33,680 play decisions, 123 decisions where reconstructed `baseline-v2` differs from the recorded
`baseline-v0`; HH reconstruction equal in 11,524 of 11,524 decisions. The shadow's own invariants are part of fidelity:
action order preserved and only dropped moves removed; every dropped move is one of Sprint 18's threat-exposed orders
(the gate's condition implies the census's); the side's first ownerships equal the census's steps; no ordered route
starts at the mover's current hex; 16 H0 and 4 HH side-games. Any difference, or any input or frozen source not matching
its pin, is **REPLAY_INVALID** and the run stops without altered definitions.

## 9. Shadow outputs

Per side-game, as aggregates only (no unit identifier, coordinate, hex or path): `baseline-v2` move orders;
threat-entry opportunities (moves meeting the condition, whatever the state machine says) and the distinct units with
one; gate episodes (first gate of an episode) and distinct gated units; gated decisions (starts and repeats); repeats
within episodes; cooldown suppressions; release reasons, and for `condition_cleared` which part of the condition failed;
synthetic hold lengths; the first gate (decision, step, decisions before it, unit class); post-divergence episodes;
condition reasons over all moves; damage after gates and after exposed orders not gated. Pooled per population: the
capturer fraction, damage-following tables (section 12), attacker facts and safety diagnostics.

**First-gate certificates** (each HH side-game). Private, on the evaluation server: decision and step, unit identity,
class, current hex, route, every qualifying visible threat with its hex, weapons and range, the first route hex inside an
envelope, `baseline-v2`'s action list and T6-G's, the route's end objective, whether the unit later takes part in a
first ownership on the historical trajectory, and whether it takes damage within 300 historical steps. Public: the same
without identities, hexes or paths (class, route and inspected lengths, entry index, threat count, classes and ranges,
distance and margin, action types in order, dropped position, objective label, the two historical outcomes).

## 10. Opportunity adequacy

Sprint 18's stop item "the gate fires fewer than 10 times per side-game" is read with Sprint 18's own denominator, the
first gate of each episode. For each of the four registered HH side-games the gate episodes are counted over every
recorded decision of the side-game (pre- and post-divergence, under the frozen state machine). The item passes only if
**every one of the four HH side-games has at least 10**. Pooled counts never replace a failing side-game. H0 is reported
descriptively.

## 11. Eventual-capturer risk

For analysis only, never as a policy input: a **historical first-ownership participant** is an own ground unit
standing on the objective's hex (own operators, `cur_hex`) at the side's first recorded decision whose flag for that
objective reads its own colour. An objective already owned at the side's first recorded decision has no transition and
no participants (reported separately). Per HH side-game: the distinct gated units, those of them that participate in at
least one first ownership (at any time in the side-game), and the fraction. The primary metric pools the four HH
side-games, de-duplicating units only within a side-game:

`capturer_fraction = gated distinct-unit side-game instances that are participants / all gated distinct-unit side-game instances`

"Most" means strictly more than one half: the item **fails when `capturer_fraction > 0.50`** (computed exactly as
`2 * participants > gated`); exactly 0.50 passes. Sprint 18 gave no more precise definition. Each side-game's fraction is
reported as well.

## 12. Descriptives (they decide nothing)

* **Damage following a gate**: for every gate episode, whether the same unit takes a damage event (Sprint 18's
  definition) with `gate step <= event step <= gate step + W`, W in 75, 150 and 300; for the first such event within 300
  steps, whether its attacker was visible at the gate, whether it was one of the threats that caused the gate, its class,
  and whether the victim was moving at the event; the same windows for Sprint 18's threat-exposed orders the shadow did
  not gate; by unit class; first gates apart from post-divergence gates; distinct gated units damaged within 300 steps of
  their first gate. No significance test: these are not causal comparisons, and nothing here says a hold would have
  prevented a hit.
* **Historical episode-level reference** (for a future probe's damage endpoint): an episode counts as damaged when its
  unit takes damage from the hold start through 300 steps after the shadow's release step. Computed on HH by the same
  run, before any probe registration.
* **Objective timing exposure** (HH): for every first ownership, the objective (public label: its value and a letter),
  the step, the participants, how many were gated at any time and how many before the first ownership, and the steps
  from the earliest such gate to the first ownership. No new capture time is simulated from recorded states.
* **Safety diagnostics** of gate episodes: unit class; on an objective; stacked; in close combat; close-combat entry (an
  inspected route hex holding a visible enemy); objective-bound (the route ends on an objective, from `baseline-v2`'s own
  move); route length; inspected length; first entry index 1 to 5; current margin outside range (minimum over
  qualifying threats of distance minus range); route entry depth (maximum over causing threats and inspected hexes of
  range minus distance); visible qualifying threats; causing threats; their ranges and classes. They are for
  understanding only; no rule is added after seeing them.

## 13. Dispositions (first match)

1. **REPLAY_INVALID**: a pin or a fidelity item of section 8 fails.
2. **T6_G_OFFLINE_INADEQUATE_OPPORTUNITY**: at least one registered HH side-game has fewer than 10 gate episodes.
3. **T6_G_OFFLINE_CAPTURE_RISK**: opportunity passes, and `capturer_fraction > 0.50`.
4. **T6_G_OFFLINE_PASS**: opportunity and capturer risk both pass.

Damage-following figures do not enter the disposition. Nothing is promoted under any outcome. On a failing disposition
T6-G is not repaired in this sprint and its timing branch is closed; on PASS a two-session head-to-head mechanism-probe
registration is drafted for the owner (2130511121, both seat orders, candidate against `baseline-v2`), defining the
candidate identity, its memory, first-gate fidelity, gate counts, an episode-level damage endpoint compared with the
historical reference of section 12, a seat-correct objective first-ownership endpoint, structural stops and retirement
rules, and no score-based endpoint. It is not executed and session 2796 stays unopened.

## 14. Outputs, privacy and checks

* Public (`evaluation/s19-t6g-shadow/`): `protocol.json` and `inputs.json` (this registration); after the run
  `fidelity.json`, `shadow.json`, `certificates.json`, `objectives.json`, `disposition.json`. Every public file passes the
  project's sanitizer as Sprint 18 applies it (forbidden keys; the private hexes and unit identifiers as keys and words,
  numeric leaves masked) and regenerates byte for byte (`scripts/s19_t6g_shadow.py run --check`).
* Private (evaluation server, git-ignored): `local/diagnostics/s19/shadow-private.json.gz`, the per-episode rows and the
  full certificates.
* Checks: synthetic tests of every boundary (section 4 and 5 edges, opportunity and capturer thresholds, disposition
  order, sanitizer); mutation tests of the gate, the state machine and the decision logic in a copied tree whose
  unmutated copy must pass first (`scripts/mutate_s19.py`, record `mutation.json`: 33 of 33 mutants killed before the
  freeze; the first run killed 32, and the survivor, a pooled opportunity count, was a test gap closed before the
  freeze); deterministic regeneration; a private documentation gate binding the results' numbers
  to the public files with planted errors; every earlier sprint's documentation gates; the full non-engine suites on the
  workstation tree, a clean clone and the server's private tree; the privacy scan compared as a set with the 104 accepted
  hit lines; the platform canary rebuilt; a read-only ledger verify showing 2,795 sessions and none unclosed.

## 15. Not claimed

No tactic is shown to work or fail. The shadow counts opportunities and describes who would have been gated on recorded
states; whether a held unit avoids damage, and how much capture is delayed, are properties of a trajectory no record
contains. HH is four games in one scenario against one opponent policy; H0 describes `baseline-v2`'s decisions on
`baseline-v0` trajectories.

## Results (2026-10-07)

### R1. Order of work

Sections 1 to 15, the gate, the analysis, the driver, their tests, `protocol.json`, `inputs.json` and `mutation.json`
(`8d017a2` to `6b4db88`, tree `e2918170`) were pushed at 2026-10-07T11:05:19+08:00 and fetched back from GitHub byte for
byte. The evaluation server then checked out `6b4db88` and `freeze --check` confirmed the frozen protocol and inputs. A
first launch of the replay did not start: the command line called a timing program the server does not have, the shell
exited with code 127 before Python ran, and nothing was read or written. The replay itself ran once, from
2026-10-07T11:12:38+08:00 to 11:16:32+08:00, and `run --check` afterwards reproduced every public file and the private
rows byte for byte.

### R2. Fidelity: every item holds

Every Sprint 18 figure of section 8 is reproduced exactly (`fidelity.json`): H0 230 threat-exposed move orders, 88 of
them followed by mover damage within 300 steps; HH 200 and 101; damage events on moving ground units 124 and 117,
attacker seen before 120 and 117; damage events 205 and 158; `baseline-v2` move orders 509 and 416; H0 33,696 decisions
and 33,680 play decisions, 123 decisions where reconstructed `baseline-v2` differs from the recorded `baseline-v0`; HH
reconstruction equal to the recorded seat in 11,524 of 11,524 decisions. The whole T6 blocks and the first-ownership
figures of `census.json` are equal for H0 and HH, and the shadow's invariants hold in all 16 H0 and 4 HH side-games.

### R3. The gate never fires

Not one move meets the threat-entry condition, in any side-game of either population. Every move falls in one of three
classes (`shadow.json`, condition reasons over all moves):

| Population | Move orders | Mover not a ground unit | No qualifying visible threat | Current hex already inside an envelope | Route enters from outside |
|---|---|---|---|---|---|
| HH | 416 | 114 | 102 | 200 | 0 |
| H0 | 509 | 118 | 161 | 230 | 0 |

The moves whose current hex is already inside are exactly Sprint 18's threat-exposed orders (200 and 230): every
exposed order was exposed at its starting hex, none only along its route. So there are 0 threat-entry opportunities,
0 gate episodes, 0 gated decisions and 0 cooldown suppressions in each of the four HH side-games and each of the 16 H0
side-games, and no first-gate certificate exists (`certificates.json` holds one empty entry per HH side-game).

What depends on gates is empty as a consequence, not as a finding of its own: the capturer fraction is undefined (0
gated units, 0 participants); none of the 25 HH first ownerships (7, 5, 7 and 6 per side-game) or 40 H0 first
ownerships has a gated participant (`objectives.json`); no objective was owned at a side's first decision; the
historical episode-level reference has no episode. The only damage-following table with entries is the one for the
exposed orders the shadow did not gate, which are all exposed orders: within 75, 150 and 300 steps, 42, 67 and 101 of
the 200 HH orders and 28, 56 and 88 of the 230 H0 orders were followed by damage to the mover, all of them vehicles'
(4 HH and 10 H0 infantry orders were never followed by damage). The 300-step counts are Sprint 18's.

### R4. Post hoc: how deep inside the envelopes the moves start (labelled, not registered)

Because a zero can come from a defect, the starting margins were measured after the registered run by a separate script
(`local/diagnostics/s19/posthoc_margins.py`, private; it recomputes ranges from the weapon table directly and does not
use the gate's reason codes). Of the 430 ground moves with a qualifying visible threat (416 by vehicles, 14 by
infantry), every one had at least one envelope over its current hex, and its distance minus range to the nearest one
was between -20 and -2, median -16: the movers started deep inside, not at the edge. The farthest qualifying visible
threat was a median 9 hexes away (at most 21), with a median 10.5 qualifying threats in view (at most 15). In this
historical play `baseline-v2` orders ground moves either before any armed enemy is in view or once its units are already
in contact; it never orders a move from outside a visible enemy's fire into it.

### R5. Disposition: T6_G_OFFLINE_INADEQUATE_OPPORTUNITY

By the first-match rule of section 13 (`disposition.json`): fidelity passes; the opportunity item fails, with 0, 0, 0
and 0 gate episodes in the four HH side-games against the registered minimum of 10 each; the capturer item is not
reached. **T6_G_OFFLINE_INADEQUATE_OPPORTUNITY.** The timing branch of T6 is closed. T6-G is not repaired in this
sprint, no probe registration is drafted, nothing is promoted, and session 2796 was not opened.

What it teaches: the damage Sprint 18 attributed to threat-exposed moves happens to units that are already inside the
fire of enemies in view when they are ordered to move; a gate on entering an envelope from outside has nothing to act
on in this play. Any later T6 branch would have to act on moves made inside an envelope (whether, where and when to
move while in contact), which is a different mechanism with a different safety risk (it touches the moves that take
objectives under fire) and needs its own frontier decision; route choice and formation stay open questions, not
automatic next steps.

### R6. Process notes

* The first mutation run killed 32 of 33 mutants; the survivor (a pooled opportunity count in place of the per-side-game
  rule) was a test gap, closed before the freeze; 33 of 33 afterwards.
* A pre-push re-read found a router description in quotation marks that was not the source's wording; the marks were
  removed in the unpushed registration commit.
* The first replay launch failed before Python started (R1); it is not counted as a run, and the replay was not
  repeated after the one run that produced the files.
* The known-answer smoke runs (section 3) were what made the zero credible before the post-hoc check: the same
  plumbing drops exactly Sprint 18's 230 and 200 exposed orders when driven by Sprint 18's predicate.

### R7. Recommendation (one)

Start the next eligible family of Sprint 18's frozen ranking, T11 (direct-fire target priority, W 4.10), with its
registered offline step: replay the kill-first target rule on H0 and HH with its stop condition (fewer than 10 changed
shots per side-game, or no gain in kills per shot) frozen before the replay, and no engine session; its two-session
probe would again need the owner's approval. A T6 branch on movement inside envelopes is not recommended as the next
task: it would need a new frontier decision with this sprint's finding as an input.
