# Sprint 20: T11-O1 kill-first target rule, offline replay

**REGISTERED — OFFLINE — NO ENGINE SESSION — AN ACTION-LEVEL REPLAY ON HISTORICAL STATES, NOT EVIDENCE OF KILLS — NOTHING PROMOTED**

Sprint 19 (`docs/SPRINT19_T6G_SHADOW.md`) closed T6's timing branch with T6_G_OFFLINE_INADEQUATE_OPPORTUNITY. The owner
approved moving to the next eligible family of Sprint 18's frozen ranking: T11, direct-fire target priority, with its
registered first increment T11-O1, the kill-first target rule. This sprint replays that rule offline on Sprint 18's
H0 and HH populations. No engine session is authorized; session 2796 is not opened. If the rule passed the frozen
offline gate, a two-session mechanism-probe registration would be drafted for the owner and not executed; if it fails,
T11-O1 is closed without repair in this sprint. Dates are business dates in UTC+8.

Sections 1 to 17 are the registration. They are committed and pushed, with the rule, the analysis, the driver, their
tests, the mutation record and the frozen `protocol.json`, `inputs.json` and `kill_model.json`
(`evaluation/s20-t11-replay/`), before the final replay, and are not edited afterwards. Results follow in a separate
section.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `d2b63144a6634f0d010e6ad1fdc600e814ab7c54`, tree `b7c53b4db839bc02a9a15be8ffba03f436ae0c60`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,795 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only verify at the start of the sprint); ledger file SHA-256 `65c803504b6f93f6e6d2a7e36892078a9cd116924fbb819a8dbb595a4039e8de` |
| Privacy baseline | the 104 accepted hit lines, reproduced as the same set at the start of the sprint (939 reachable blobs) |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Frozen history | T9 `SHELVED`; Sprint 18 NEXT_FAMILY_SELECTED (T6 first, T11 second, W 4.10, E 4); Sprint 19 T6_G_OFFLINE_INADEQUATE_OPPORTUNITY; no historical output is changed by this sprint |

## 2. Question and scope

Sprint 18 registered the hypothesis: among a shooter's currently legal listed direct-fire targets, preferring the one
with the lowest observed blood may complete kills earlier and remove enemy combat power sooner. Its census counted the
opportunity: of `baseline-v2`'s shots, 127 of 432 (H0) and 97 of 319 (HH) had a listed target with lower blood than the
chosen one. Those are opportunity counts, not a replay of the rule.

This sprint answers four narrower questions, all at the level of actions on recorded states: how often the rule, run
through `baseline-v2`'s full decision with its same-step shoot-target reservation, changes emitted shots; whether every
change stays inside direct fire; whether the public rules support a defensible immediate-kill probability for a shot;
and, only if they do, whether the changed shots' documented kill probability exceeds that of the shots they replace.
Actual kills, survival, later targets and score need the candidate's own trajectory, which only an engine session
produces.

T11 is not the target-ownership line. TO-1 asks which of several colliding shooters owns a target; T11 asks which
legal target one shooter prefers. TO-1's history, its stopped 360-game prevalence study and its data are not touched.
Offline only: no run card, no change to `baseline-v2`, the stable core, the registered evaluator or any historical
output; no external research; no private data sent out.

## 3. Evidence seen before this registration (disclosure)

Before writing these sections the author read Sprint 18's document, experiments, selection and census, Sprint 19's
document, the frontier, the shoot-reservation, target-allocation and target-ownership documents and the code of
`baseline-v2`'s decision (candidates, policy, semantics, shoot reservation), and the public platform documentation
snapshot of 2026-09-29 (section 11). No T11 figure was computed on private data before this registration. The rule and
the analysis were developed on synthetic situations. One known-answer smoke run (`scripts/s20_t11_replay.py smoke`) was
made on the real inputs before the freeze with a code revision equal to the frozen one; it decides every analysed
seat-decision twice with `baseline-v2`'s ranking, so no difference may appear, and it prints no T11 figure. Its result
is stated in section 9.

The two kill-model gaps of section 11 were found by reading the documentation, before any replay, and they fix the
disposition at its second step unless fidelity fails (section 14). The replay is still run, for the descriptive record
the brief asks for; nothing in it can change the disposition except a fidelity failure.

## 4. The frozen T11-O1 rule

`src/miaosuan_agent/experiments/t11_kill_first.py`, class `RankedReservationPolicy`, ranking `kill-first`. For each
controllable unit, in `baseline-v2`'s ascending unit order, `baseline-v2`'s hierarchy is unchanged: engage, then
occupy, then move, then nothing. Only the ranking of the engage candidates differs, and only among the candidates that
remain after the same-step reservation has excluded the targets already reserved in this seat-decision:

1. the engage candidates are exactly `baseline-v2`'s: the unit's listed shoot options in the current `valid_actions`,
   well-formed, attack level at least 1; no option is invented;
2. they are grouped by target; each target's blood is the `blood` field of the enemy unit with that `obj_id` in the
   seat's current `operators`;
3. if every remaining target has a comparable blood (an integer of at least 0, not a boolean), the candidates whose
   target has the lowest blood are kept, and among them `baseline-v2`'s own rank selects: highest attack level, then
   lower target id, then lower weapon id. Among targets tied on blood this is `baseline-v2`'s target order; on the
   chosen target it is the highest attack level, then the lower weapon id;
4. if any remaining target is not a visible enemy, has no `blood` field, or has a blood that is not comparable, the
   unit uses `baseline-v2`'s ranking (fail closed), and the reason is counted (`target_not_visible`, `blood_missing`,
   `blood_malformed`).

Nothing else enters: no target class or value, objective, shooter value, threat, distance, retaliation, future
visibility, ammunition, scenario, map or unit special case. A higher attack level is not assumed to mean more damage;
attack level appears only as `baseline-v2`'s own tie order.

## 5. The frozen same-step reservation

`baseline-v2` emits at most one shot per target per seat-decision: when a unit's selected shot passes the project gate
on its own, its target is reserved for the rest of the decision, and later units' options on reserved targets are
excluded before their selection. T11 keeps this mechanism exactly; the exclusion is applied before the kill-first
ranking. Because an earlier unit's changed target changes which target is reserved, the whole seat-decision is
recomputed sequentially in the same unit order: every later unit sees the reservations of the shots T11 actually
selected before it, never `baseline-v2`'s. Units are never evaluated independently.

Implementation: the play step of `ShootReservationPolicy` is restated line for line in `RankedReservationPolicy` so
that each unit's selection state can be recorded; deployment, memory, the tactical context, candidate generation, the
occupation reservation, the bounded router and the final gate are inherited unchanged. With ranking `baseline` the
class must emit exactly what `baseline-v2` emits; the replay checks that on every analysed decision (section 9).

## 6. Classification of differences

Every analysed seat-decision is decided twice on the same recorded observation, each run with its own memory from an
empty start of the side-game: with ranking `baseline` (`B`, which must equal `baseline-v2`) and with ranking
`kill-first` (`T`). Per unit, with `B`'s and `T`'s emitted actions and recorded selection states:

* **UNCHANGED**: the emitted actions are equal. A unit whose kill-first ranking differs from `baseline-v2`'s ranking at
  that point but whose emitted action happens to be equal (its reservation state differs too) is counted as a *silent
  root switch*, not as a change.
* **ROOT_TARGET_SWITCH**: the actions differ and, on `T`'s remaining candidates, the kill-first selection differs from
  `baseline-v2`'s ranking of the same candidates.
* **RESERVATION_INDUCED_SHOOT_CHANGE**: not a root switch, both runs emit a shot, the shots differ, and the unit's
  reservation state differs (its excluded options, or whether its occupation was blocked).
* **RESERVATION_INDUCED_NONSHOOT_CHANGE**: not a root switch, the actions differ, the state differs, and at least one
  run emits no shot.
* **UNEXPLAINED**: the actions differ with the same ranking and the same state. Any such unit is a fidelity failure.

Each difference also has a kind: `changed_shot` (both shoot, at a different target or with a different weapon),
`lost_shot` (`B` shoots, `T` does not), `gained_shot` (`T` shoots, `B` does not), `other_nonshoot` (neither shoots).
A root switch whose shot the gate refused counts as a `lost_shot` root switch.

**Reservation chain.** A changed unit is caused by an earlier changed unit of the same decision when the target the
earlier unit reserved under `B` or under `T` is in the symmetric difference of the two runs' reserved targets before the
later unit, restricted to the later unit's targets. The chain length is 1 for an uncaused change and one more than the
longest chain of its causes otherwise. Changes carried only by the occupation reservation are classified but do not
extend a chain.

## 7. The evidence boundary

All actions of one seat-decision are chosen from the same observation, so the whole recomputed T11 action list,
reservation effects included, is a valid action-level counterfactual for that decision. Once a T11 decision differs and
the engine advances, every later recorded state is off-policy for T11. The replay therefore establishes opportunity,
the exact action differences and their reservation consequences. It does not establish actual kills caused by T11,
shooter survival, later target availability, focus-fire effects, later firing opportunities or any score effect. H0
states are `baseline-v0` trajectories with `baseline-v2` reconstructed seat-locally, as in Sprint 18; H0 is
descriptive. The results report, per HH side-game, the first changed decision and how many decisions follow it.

## 8. Corpora and inputs

Exactly Sprint 18's registered populations, with its pinned digests (`evaluation/s20-t11-replay/inputs.json` copies the
H0 and HH pins from `evaluation/s18-frontier-reset/inputs.json` and pins that file and `census.json`):

| Id | Population | Analysed |
|---|---|---|
| H0 | the 8 replay-corpus games (`baseline-v0` mirrors, C1), every decision's seat observation | both seats: 16 side-games; `baseline-v2` reconstructed with its own memory, as in Sprint 18 |
| HH | the 4 full-step timelines of Sprint 12 (2130511121, `baseline-v2` against v3, both seat orders) | the `baseline-v2` seat: 4 side-games, p01 and p03 blue, p02 and p04 red; its recorded submitted actions |

No sensitivity corpus is declared. No other record enters: no HI, R or S population, no BOKE-2026 data, nothing of the
stopped 360-game prevalence corpus. The loaders are Sprint 18's census loaders (`scripts/s18_census.py`), unchanged.

## 9. Fidelity (REPLAY_INVALID)

Before T11 is evaluated, the same run reproduces exactly, from the same loaders on the same pinned inputs: H0 432
`baseline-v2` direct-fire shots, 368 with at least two targets listed, 127 with a listed target of lower blood than the
chosen one; HH 319, 267 and 97 (Sprint 18's `fire_choice` definitions and `census.json` block N3, both populations);
H0 33,696 decisions, 33,680 play decisions, 123 decisions where reconstructed `baseline-v2` differs from the recorded
`baseline-v0`; HH reconstruction equal to the recorded seat in 11,524 of 11,524 decisions. In addition:

* run `B` reproduces `baseline-v2`'s actions in every analysed decision: 33,696 of 33,696 (H0, against the census
  reconstruction) and 11,524 of 11,524 (HH, against the recorded submitted actions);
* 16 H0 and 4 HH side-games, every side-game's decided steps matching its frames one to one;
* no UNEXPLAINED difference; equal memories after every decision; equal actions in every non-play decision; both
  runs' actions in unit order; no duplicate shoot target in either run; every T11 shot equal to a listed option of
  its unit; no T11 shot at a target reserved earlier in the step; equal engage candidates per unit in both runs.

Any difference, or any input, frozen source or `kill_model.json` not matching its pin, is **REPLAY_INVALID**, and the
run stops without altered definitions.

**Smoke run before the freeze.** Both runs with `baseline-v2`'s ranking, on the evaluation server from
2026-10-07T15:28:19+08:00, 310 s: every anchor and integrity figure above reproduced; run `B` equal to `baseline-v2` in
33,696 of 33,696 H0 and 11,524 of 11,524 HH decisions; 45,220 seat-decisions decided; 0 decisions with a difference
and 0 problems in all 16 H0 and 4 HH side-games. The frames, seats, memories, routers and reference actions are joined
as intended on real data.

## 10. Opportunity adequacy

Sprint 18's stop item "fewer than 10 changed shots per side-game" is read exactly as follows. For each of the four HH
side-games, count the T11 emitted shoot actions whose `(target_obj_id, weapon_id)` differs from `baseline-v2`'s emitted
shoot action for the same shooter at the same decision, over every recorded decision of the side-game: root and
reservation-induced changed shots both count. Options considered but not emitted do not count, and neither do changes
from a shot to occupation, movement or nothing (`lost_shot`) or the reverse (`gained_shot`); those are reported apart.
The item passes only if **every one of the four HH side-games has at least 10**. A pooled total never replaces a failing
side-game. H0 is descriptive. Also reported: root switches, induced changed shots, distinct changed shooters,
decisions with at least one change.

## 11. The documented immediate-kill model

Sprint 18 proposed to evaluate "the expected kill probability per changed shot from the published damage tables". The
quantity is `p_kill_now`: the documented probability that this shot destroys this currently observed target
immediately, with no later salvo, shooter, retaliation, score or value. Before any replay the public platform
documentation snapshot fetched 2026-09-29T18:41:10+08:00 (`local/source-archives/docs-live-snapshot-20260929`; local,
not redistributed) was read against every requirement of that quantity.
`evaluation/s20-t11-replay/kill_model.json` records each requirement, its status and verbatim quotations, with the
SHA-256 of each quoted file from the snapshot's own `SHA256SUMS`; a test re-checks every quotation against the snapshot
where it exists.

| Item | Requirement | Status | Finding |
|---|---|---|---|
| K1 | a table maps a shot's attack level to its possible results | documented | result tables for vehicle targets (by the shooter's vehicle or squad count and the attack level), for personnel targets and infantry light weapons against vehicles (by the attack level), and for air targets, each read with a random number from 2 to 12 |
| K2 | the listed option's `attack_level` is the index those tables are read with | **undocumented** | `valid_actions` documents `attack_level` only as an attack level; the rules derive a shot's attack level from weapon and distance tables, the shooter's count (against personnel) and a separate elevation-difference correction; whether the listed value already includes that correction and the count row is not stated |
| K3 | the possible results of one shot | documented | a number eliminates that many squads or vehicles (and suppresses a vehicle); no effect; suppression only |
| K4 | the distribution of the random number | inferred, not stated | the dice are stated for the corrections (two dice for vehicles, one die for personnel), not for the result tables; two fair dice is an inference from the range 2 to 12 |
| K5 | how the result and its correction combine into the final loss | **undocumented** | the correction comes from the armour column (vehicles) or is -1, 0 or +1 (personnel); whether it applies to a no-effect or a suppression result, how it is added, and how a total below zero or above the target's strength is treated are not stated; the judge record names an original loss, a loss correction and a final loss without a rule |
| K6 | how observed blood maps to destruction | inferred, not stated | blood is the squad (or vehicle) count, a number eliminates that many, and a suppressed infantry unit suppressed again loses one squad; that a unit reaching zero is removed is not stated as a rule (`docs/RESIDUAL_516_DIAGNOSTIC.md` recorded the same inference) |
| K7 | whether the target class changes the table | documented | separate tables for personnel, vehicles (with the observed armour class) and aircraft |
| K8 | whether the weapon or shooter class changes the table | documented | the weapon through the attack-level tables, the shooter's count through the vehicle result table and the personnel attack-level table, the shooter's state through the corrections |
| K9 | the inputs of the corrections are observable | documented | target terrain, target state (concealed, moving, stacked, marching) and shooter state are named, with observation fields for the state |
| K10 | when the model is undefined | documented | the vehicle result table covers counts 1 to 5 and attack levels 1 to 10 |

**Determination: the model is unavailable.** The rule frozen here is that every item must be documented; an inference
or a gap is an unsupported assumption. K2 and K5 are gaps, K4 and K6 are inferences. K5 alone decides the sign of
comparisons that matter to this rule. Two readings the text allows give different answers for the same synthetic
shot: an attack level of 4 against a one-squad, unsuppressed, stacked infantry target, with no other modifier. On two
fair dice the personnel table gives suppression with probability 12/36 (random numbers 2, 3, 4, 10, 11 and 12) and
otherwise no effect; the personnel correction is +1 only when one die plus the stacked modifier of +2 reaches 8, with
probability 1/6. If the correction applies only to a numeric result, `p_kill_now` is 0; if a +1 turns a suppression
into one squad, it is 1/18. A kill-first rule moves fire onto low-blood targets, exactly where such a choice decides
whether a shot can kill at all. K2 adds the elevation correction table's entries, from -5 to +1 attack levels, as an
unknown shift of the column a listed attack level is read in.

Accordingly, as the brief requires, no probability model is invented, none is fitted from historical outcomes, no
private engine data are used to settle the gaps, and future target disappearance is not used as a proxy. No
`p_kill_now` calculator is implemented, no paired delta is computed, and the optional implementation cross-check of the
brief's section 24 does not arise. The kill-edge item of section 13 cannot be evaluated.

## 12. The pure-variable invariant

T11-O1 is a target-priority rule. Every action difference must stay inside direct fire: the same units act, every
changed `baseline-v2` shot remains a T11 shot, and no move, occupation, no-op, deployment or memory changes. Frozen:
the item **fails on any `lost_shot`, `gained_shot` or `other_nonshoot` difference, in any class, in any HH or H0
side-game** (a root switch whose shot the gate refused included). Memory or deployment differences cannot arise from
the rule and are fidelity failures (section 9). A failure here is **T11_OFFLINE_COUPLED_BEHAVIOR**; no reason to allow
such coupling is recognised in this sprint.

## 13. The kill-edge item (registered, not reachable)

Had the model been available: over the HH changed emitted shots, `baseline_mean_pkill` the mean of `baseline-v2`'s
`p_kill_now` for the corresponding baseline shots, `candidate_mean_pkill` the mean of T11's, and the paired
`delta_pkill = mean(candidate - baseline)`; the item passes only if `delta_pkill > 0` on the pooled HH changed shots
(exactly zero fails), each side-game reported apart, no significance test, `lost_shot` and `gained_shot` counted apart
and never in the denominator. With the model unavailable the item is reported as not evaluated (`delta_pkill` null).

## 14. Dispositions (first match)

1. **REPLAY_INVALID**: a pin or an item of section 9 fails.
2. **T11_OFFLINE_MODEL_UNAVAILABLE**: the published rules do not support a defensible immediate-kill probability
   (section 11; determined at registration).
3. **T11_OFFLINE_COUPLED_BEHAVIOR**: the invariant of section 12 fails.
4. **T11_OFFLINE_INADEQUATE_OPPORTUNITY**: at least one HH side-game has fewer than 10 changed emitted shots.
5. **T11_OFFLINE_NO_KILL_EDGE**: opportunity passes, and `candidate_mean_pkill <= baseline_mean_pkill`.
6. **T11_OFFLINE_PASS**: everything above passes and `candidate_mean_pkill > baseline_mean_pkill`.

Items below the first match are computed where possible and reported as descriptive; they decide nothing. Nothing is
promoted under any outcome, and no engine use is authorized by any of them. On any disposition other than PASS, T11-O1
is not repaired in this sprint (no target value, attack-level threshold, target class, focus-fire memory or threat
filter is added), no probe registration is drafted, and the next decision returns to the owner with Sprint 18's
ranking.

## 15. Descriptives (they decide nothing)

Per side-game and pooled per population, as aggregates only: decisions, play decisions, decisions with at least one
change, the first changed decision and the decisions after it; counts by class and kind; changed emitted shots (root
and induced); silent root switches; distinct changed shooters; shots of each run; fail-closed counts by reason (all,
and with two or more remaining targets). Reservation diagnostics over changed decisions: the two runs' shoot targets,
duplicate targets (expected 0 in both), targets newly reserved and no longer reserved, units with an option excluded
only under T11 or only under `baseline-v2`, decisions whose changes form a chain, and the longest chain. For root
switches, comparing `baseline-v2`'s ranking with T11's at the same point: the two targets' blood, the blood reduction,
the attack-level pair and change, how often T11's attack level is lower, equal or higher, shooter class, target class
pair, the number of remaining targets, and how often both rankings name the same target (expected 0). For induced
changed shots: blood pairs, shooter class and target class pairs. No kill-probability diagnostic exists, since the
model is unavailable; no recorded outcome (later blood, disappearance, judge records) is read.

## 16. Outputs, privacy and checks

* Public (`evaluation/s20-t11-replay/`): `protocol.json`, `inputs.json`, `kill_model.json` and `mutation.json` (this
  registration); after the run `fidelity.json`, `replay.json` and `disposition.json`. Every public file passes the
  project's sanitizer as Sprint 18 applies it (forbidden keys; the private hexes and unit identifiers as keys and words,
  numeric leaves masked) and regenerates byte for byte (`scripts/s20_t11_replay.py run --check`).
* Private (evaluation server, git-ignored): `local/diagnostics/s20/replay-private.json.gz`, every changed unit with
  its decision, identities and both actions.
* Checks: synthetic tests of every boundary of sections 4 to 6 and 10 to 14 (`tests/test_s20_t11.py`), including a
  generated corpus on which run `B` must equal `baseline-v2` and every difference must be explained; mutation tests of
  the rule, the comparison and the decision logic in a copied tree whose unmutated copy must pass first
  (`scripts/mutate_s20.py`, record `mutation.json`: 35 of 35 mutants killed before the freeze; the first run killed 33,
  and the two survivors, a chain length not accumulated past two and a non-reproducing reference decision not recorded
  as a problem, were test gaps closed before the freeze); the public files bound to the registration
  (`tests/test_s20_results.py`) and regenerated on the server (`tests/test_real_s20.py`); deterministic regeneration; a
  private documentation gate binding the results' numbers to the public files with planted errors; every earlier
  sprint's documentation gates; the full non-engine suites on the workstation tree, a clean clone and the server's
  private tree; the privacy scan compared as a set with the 104 accepted hit lines; the platform canary rebuilt; a
  read-only ledger verify showing 2,795 sessions and none unclosed.

## 17. Not claimed

No tactic is shown to work or fail. The replay counts how the kill-first rule would change emitted actions on recorded
states and how the reservation propagates those changes inside one decision; whether a changed shot kills, and what
follows, are properties of a trajectory no record contains. The kill-model determination is a statement about the
public documentation, not about the engine: the engine may implement a definite rule that the documentation does not
state. HH is four games in one scenario against one opponent policy; H0 describes `baseline-v2`'s decisions on
`baseline-v0` trajectories.

## Amendment A1 (2026-10-07, after a refused first run, before any result was written)

Sections 1 to 17 were pushed at 2026-10-07T15:39:44+08:00 (`ac774a7`, tree `538dfecb`) and fetched back from GitHub
identical. The replay was then launched once on the evaluation server at 2026-10-07T15:46:48+08:00. It computed every
figure but wrote nothing: the frozen privacy check refused `replay.json` before any file was written, because the
frozen serializer wrote the root-switch distributions (target blood, blood reduction, attack-level change, remaining
targets) with bare numbers as keys, and small integers are also private unit identifiers in these records. The
synthetic privacy test had used only large identifiers and could not see it. The server's tree stayed clean, with no
result file and no private output.

What the author saw before this amendment, disclosed in full: the refusal message, which lists the first 10 offending
keys, all in the first HH side-game's root-switch block (`baseline_target_blood` keys 2, 3 and 4; `t11_target_blood`
1 and 2; `blood_reduction` 1, 2 and 3; `attack_level_change` 0; `targets_available` 6). It shows that this side-game has
root switches and these key values; it shows no count, no other side-game and no disposition item. Because the run
reached the privacy check of `replay.json`, the fidelity items of section 9 had held (that file is built only then).

The amendment changes the public serializer only: every count keyed by a number is keyed by a labelled value instead
(`blood_2`, `reduction_1`, `change_0`, `targets_6`). No definition, threshold, classification, input or disposition
rule changes, and the disposition was fixed at its second step by section 11 unless fidelity failed, so the amendment
cannot be outcome-motivated. A test now checks the public side and pooled summaries against small identifiers
(0 to 49 and -5 to -1), and a mutant restoring bare keys is killed: the mutation record is 36 of 36. `protocol.json`
is re-frozen; only the analysis module's normalised digest changes. The replay is run once more after this amendment is
pushed; the refused launch is counted as a run that produced no output.

## Results (2026-10-07)

### R1. Order of work

Sections 1 to 17, the rule, the analysis, the driver, their tests, `protocol.json`, `inputs.json`, `kill_model.json`
and `mutation.json` (`3a5870c` to `ac774a7`, tree `538dfecb`) were pushed at 2026-10-07T15:39:44+08:00 and fetched back
from GitHub identical. The first launch of the replay was refused by its own privacy check and wrote nothing; Amendment
A1 (`6fb4ce4` to `cf67013`, tree `8c0ff02a`) was pushed at 2026-10-07T15:55:19+08:00 and fetched back identical; the
evaluation server fast-forwarded to it and `freeze --check` confirmed the frozen protocol and inputs. The replay then ran
once, from 2026-10-07T16:02:19+08:00 to 16:07:47+08:00, and wrote `fidelity.json`, `replay.json` and
`disposition.json`. `run --check` afterwards regenerated every public file and the private rows byte for byte. Times
of server runs in this document (the smoke run of section 9, both launches and the replay) are read from the evaluation
server's host clock, which runs ahead of the workstation's by the offset recorded in `docs/ENGINE_INSTALL.md`; push
times are the workstation's. The order of events is unaffected.

### R2. Fidelity: every item holds

Every Sprint 18 anchor of section 9 is reproduced exactly (`fidelity.json`): H0 432 `baseline-v2` direct-fire shots,
368 with at least two targets listed, 127 with a listed target of lower blood than the chosen one; HH 319, 267 and 97;
the fire-choice blocks of `census.json` are equal for both populations; H0 33,696 decisions and 33,680 play decisions,
123 decisions where reconstructed `baseline-v2` differs from the recorded `baseline-v0`; HH reconstruction equal to the
recorded seat in 11,524 of 11,524 decisions. Run `B` reproduces `baseline-v2` in 33,696 of 33,696 H0 and 11,524 of
11,524 HH decisions. In all 16 H0 and 4 HH side-games there is no problem of any kind: no UNEXPLAINED difference, no
memory or non-play difference, no duplicate shoot target in either run, no T11 shot outside its unit's listed options
or at a target reserved earlier in the step.

### R3. Disposition: T11_OFFLINE_MODEL_UNAVAILABLE

By the first-match rule of section 14 (`disposition.json`): fidelity passes; the kill model is unavailable (section 11:
K2 and K5 undocumented, K4 and K6 inferred). **T11_OFFLINE_MODEL_UNAVAILABLE.** No `p_kill_now` was computed, no
probe registration is drafted, nothing is promoted, and session 2796 was not opened. The items below the first match,
computed and reported as descriptive only (they decide nothing):

* pure target priority: holds. There are 0 lost, gained or other non-shoot differences in every HH and H0 side-game;
  every T11 change is a changed shot, the same units shoot in both runs, and the two runs emit the same number of
  shots (319 in HH, 432 in H0);
* opportunity: would pass. The four HH side-games have 15, 33, 19 and 27 changed emitted shots, each at least 10;
* kill edge: not evaluated (`delta_pkill` null).

### R4. What the replay shows (descriptive)

| HH side-game | Decisions with a change | Changed emitted shots | Root switches | Reservation-induced | Distinct changed shooters | First changed decision (step) |
|---|---|---|---|---|---|---|
| p01, `baseline-v2` blue | 13 | 15 | 15 | 0 | 5 | 276 (275) |
| p02, `baseline-v2` red | 33 | 33 | 33 | 0 | 6 | 180 (179) |
| p03, `baseline-v2` blue | 18 | 19 | 19 | 0 | 6 | 276 (275) |
| p04, `baseline-v2` red | 27 | 27 | 27 | 0 | 6 | 180 (179) |

Pooled over HH: 94 changed emitted shots in 91 of 11,524 decisions, all of them root switches, and 1 silent root
switch (in p01: a root switch whose emitted shot equals `baseline-v2`'s because the two runs' reservations also
differed). In H0, 133 changed shots (122 root switches, 11 reservation-induced) in 100 decisions, in 6 of the 16
side-games (the 1930331196, 2120531121 and 2130511121 games); the other 10 side-games, with 2 to 15 shots each, have
none. No unit fell back for want of a readable blood: every remaining target was a visible enemy with an integer blood.
Everything after a side-game's first change is on recorded states that are off-policy for T11 (section 7): in HH the
first change is at decision 180 or 276, so 2,700 or 2,604 of the 2,881 decisions follow it.

**The root switches trade attack level for low blood.** Of the 94 HH root switches, T11's attack level is lower in 58,
equal in 36 and never higher (H0: 90, 32 and 0 of 122); the drop is 5 levels or more in 17 (H0 10). T11's target has
blood 1 in 77 of the 94 (H0 104 of 122), while `baseline-v2`'s target at the same point had blood 3 in 52 (H0 48);
the two rankings never name the same target. The shooters are vehicles of sub-type 0 and aircraft of sub-type 6 (49
and 45 of the HH root switches; in H0 also vehicles of sub-type 1 and 4).

**Reservation effects are small.** In HH no shot changes only because of an earlier change: the 3 decisions with a
reservation chain hold root switches only, a later one also seeing a different reserved set; the longest chain is 2.
Changed decisions reserve 94 targets that `baseline-v2` did not and leave 94 unreserved that it did; 4 units had an
option excluded only under T11 and 4 only under `baseline-v2`. In H0 the 11 induced changed shots come from chains of
up to 3 (31 decisions with a chain, 33 units each way).

**Post hoc, labelled: where the low-blood targets are.** The target classes of `replay.json` show that the rule's
lowest blood is often not a combat unit's strength. In HH, 24 of the 94 T11 targets are fortifications (type 4), 16 of
them switched onto from another class; the published rules adjudicate fire at a fortification against its remaining
capacity, and vehicles inside do not inherit the result. In H0, 53 of the 122 switches move fire onto aircraft
(type 3), from other classes, for which the rules publish separate anti-air tables. These observations were not
anticipated by the registration, change no item and are not a repair; they bear on any later form of the rule (R6).

### R5. Process notes

* The first mutation run killed 33 of 35 mutants; the two survivors were test gaps (a reservation chain longer than
  two, and a non-reproducing reference decision not recorded as a problem), closed before the freeze. Amendment A1
  added a mutant for bare public keys: 36 of 36.
* The first replay launch was refused by the frozen privacy check before writing any file (Amendment A1). The synthetic
  privacy test had used only large identifiers; it now checks small ones. The refused launch is counted as a run that
  produced no output; the registered decision rule was not touched.
* A binding test first compared the six anchors in a hand-typed key order that was wrong; it was replaced by a named
  comparison before the registration commit.
* A pre-push re-read removed an unverified claim about the snapshot's provenance and corrected the range of the
  elevation correction table (from -5 to +1) in section 11.
* A shell heredoc carrying this section failed to parse on its apostrophes and wrote nothing; the section was written
  with the editor instead.

### R6. What it teaches, and the one recommended next task

Mechanically, T11-O1 is the narrow change it was meant to be: on these states it changes only targets, never the
shooting units or any other behaviour, and it has more than the registered opportunity in every HH side-game. What
blocks it is the endpoint. The public documentation does not say how a result and its correction combine (K5) or
whether a listed attack level already includes the elevation correction (K2), and the rule gives up attack level on
exactly the low-blood targets, often fortifications or aircraft, where those gaps decide whether a shot can kill.
Under the registered gate no engine probe is justified until the endpoint is valid.

**Recommended next task (one, owner's approval):** an offline, registered adjudication-semantics audit of the existing
direct-fire judge records, with no engine session: establish from the engine's own records (the project's semantics
evidence order puts runtime observation first) whether a listed `attack_level` equals the record's `att_level`, how
`ori_damage` and `rect_damage` combine into `damage` (a no-effect or suppression result and clamping included), and what
removal means for infantry, vehicles, aircraft and fortifications. It would settle or confirm K2, K4, K5 and K6 without
fitting any probability; only then could a documented `p_kill_now` be frozen and T11-O1, as registered, be evaluated.
If the owner prefers to leave direct fire, the frozen ranking's next eligible family is T2.
