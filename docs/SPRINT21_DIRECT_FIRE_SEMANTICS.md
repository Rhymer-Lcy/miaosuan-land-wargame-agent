# Sprint 21: direct-fire adjudication semantics audit

**REGISTERED — OFFLINE — EXISTING RUNTIME EVIDENCE ONLY — NO ENGINE SESSION — T11-O1 UNCHANGED — NOTHING PROMOTED**

Sprint 20 (`docs/SPRINT20_T11_REPLAY.md`) closed with T11_OFFLINE_MODEL_UNAVAILABLE: the public documentation does not
define the immediate-kill probability `p_kill_now` its registered endpoint needs. The owner approved one narrow offline
audit before deciding whether to leave T11 for T2: do the engine records that already exist identify the immediate
direct-fire adjudication well enough to define that probability without fitting a model and without an unsupported rule
assumption? This sprint does not change T11-O1, does not design a T11-v2 and does not run a T11 candidate. No engine
session is authorized; session 2796 is not opened. Dates are business dates in UTC+8.

Sections 1 to 14 are the registration. They are committed and pushed, with the analysis module, the driver, their tests,
the mutation record and the frozen `protocol.json` and `inputs.json` (`evaluation/s21-direct-fire-semantics/`), before
the audit is run, and are not edited afterwards. Results follow in a separate section.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `c3503504ab0dd170f96db4cc0a7b7555ebecd923`, tree `9d04cf61342717208ef3c5f77607b300809da39e`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,795 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only verify at the start of the sprint); ledger file SHA-256 `65c803504b6f93f6e6d2a7e36892078a9cd116924fbb819a8dbb595a4039e8de` |
| Privacy baseline | the 104 accepted hit lines, reproduced as the same set at the start of the sprint (967 reachable blobs) |
| Frozen history | Sprint 18 NEXT_FAMILY_SELECTED (T6 first, T11 second); Sprint 19 T6_G_OFFLINE_INADEQUATE_OPPORTUNITY; Sprint 20 T11_OFFLINE_MODEL_UNAVAILABLE, with its descriptive facts (anchors reproduced, HH changed shots 15, 33, 19 and 27, 94 root switches, no lost, gained or non-shoot difference); nothing here changes them |

## 2. Question, scope and evidence order

The quantity is `P(immediate target destruction | current observed target state, listed direct-fire option)` for one
accepted direct-fire shot: no later salvo, no score, no target value. Sprint 20 left four uncertainties that decide it:

* **K2**: whether a listed `valid_actions` `attack_level` is the attack level the engine adjudicates with;
* **K4**: the random mechanism, split into the deterministic mapping of a drawn number to a published table cell
  (K4-MAPPING) and the probability of each drawn number (K4-PROBABILITY);
* **K5**: how `ori_damage`, `rect_damage` and the final `damage` combine, a no-effect or suppression result and
  clamping included;
* **K6**: how the final damage, the observed blood and the target's removal relate, per target class.

Evidence order, as the project uses it: runtime observation on engine 4.1.0 first, then the public documentation
snapshot, then SDK material already legitimately held, then inference, labelled as such. A runtime relation establishes
what the observed engine did; it does not establish an unobserved probability law. Disassembling or decompiling the
engine's compiled modules is not evidence this audit uses: no license or terms of use grant it (`docs/PROVENANCE.md`,
section 4), and it is not in the project's evidence order.

Offline only: no engine session, no run card, no change to `baseline-v2`, T11-O1, the stable core, the registered
evaluator or any historical output, no external research and no private data sent out.

## 3. Evidence seen before this registration (disclosure)

Before writing these sections the author read Sprint 20's document, `kill_model.json` and replay summary, the
residual-516 diagnostic's findings on `judge_info`, Sprint 18's census loaders and the capture modules, and the public
documentation snapshot of 2026-09-29 (rules, tables, observation reference). The private captures (not the prevalence
study's, which was not opened) were then read for their **structure** only, by scripts kept in the evaluation server's
scratch area and the workstation's ignored `local/`:

* an inventory of every capture: steps, pre-step snapshots, kept seats, final state, and counts of shoot actions,
  feedback entries and judge records (section 4 publishes it);
* the key sets and value types of the judge records of the 18 usable games and the distinct values of their `type`
  text: two key sets (1,044 records with `ori_damage`, `rect_damage`, `random2` and `random2_rect`, 166 without them),
  every value an integer except the two name strings and the type text, which is `直瞄射击` (direct fire) in all 1,210;
  no `align_status`, `offset` or `guide_obj_id` field;
* the key names of the submitted copies, the feedback echoes, the seat observations, the all-seeing state and the
  final state of three games;
* the Sprint 20 HH target-class pairs, which fix the required classes (section 6).

Two smoke runs of the loader and the pairing on the real corpus followed, before the freeze
(`scripts/s21_semantics.py smoke`; section 5). Each printed integrity and pairing counts only and computed no K2, K4, K5
or K6 figure. Between them only the public output layer changed: a pre-freeze review found that `k6.json` would have
used a key the sanitizer forbids and that `k4.json` would have repeated evidence texts containing small numbers, either
of which would have made the frozen privacy check refuse the run; both were fixed and a synthetic test now runs the
driver's aggregation through the sanitizer with small identifiers. The second smoke ran on the code frozen here. A
private check also planted eight integrity defects into one real game's step log in memory (a record removed, a paired
shot marked refused, an echo removed, a shifted `cur_step`, a flipped colour, an unexplained record, a record of
another type, a disagreeing removal); each produced its problem kind and the unaltered game produced none. No relation
between judge fields, listed options, blood or removal was computed or looked at before this registration. The
relations of sections 7 to 10 were written from the field names, the documentation and synthetic cases.

## 4. The frozen corpus

A capture is usable when its window file holds a pre-step snapshot (the all-seeing state and the observation of every
shooting seat) for every step, its step log holds the pre-execution copies of the submitted actions, the engine's
feedback and the step's new judge records, and it keeps the final post-step state (the Sprint 10, 12, 16, 17 and T7
probe observers). Every existing capture was tested against this rule; `inputs.json` lists each with its reason and pins
every file of the usable ones by SHA-256.

| Folder | Games | Sessions | Configuration | Policies (public classes) | Steps | Shoot actions | Judge records |
|---|---|---|---|---|---|---|---|
| `t7-mechanism-probe-1` | 3 | 2462-2464 | 1910631192 C3; 2120531121 H1, H2 | `baseline-v2`, exploratory candidates, inert control | 7,563 | 295 | 353 |
| `s10-t9-v1-diagnosis` | 4 | 2773-2776 | 1930331196 C3; 2120531121 C3 | `baseline-v2`, exploratory candidates, inert control | 11,524 | 53 | 52 |
| `s10-t9-v1-c2-diagnosis` | 2 | 2777-2778 | 1930331196 C2 | `baseline-v2`, exploratory candidates, inert control | 5,762 | 1 | 1 |
| `s12-v3-primary-1` | 4 | 2787-2790 | 2130511121 H1, H2 | `baseline-v2`, exploratory candidates | 11,524 | 578 | 749 |
| `s16-v3-mechanism-capture-1` | 3 | 2791-2793 | 1930331196 C2, C3; 2120531121 C3 | exploratory candidates, inert control | 8,643 | 31 | 31 |
| `s17-post-stage-v6-probe-1` | 2 | 2794-2795 | 1930331196 C2; 2120531121 C3 | exploratory candidates, inert control | 5,762 | 24 | 24 |
| **Total** | **18** | | | | **50,778** | **982** | **1,210** |

All 18 games ran on engine 4.1.0. The four `s12-v3-primary-1` games are the games of Sprint 20's HH population.

Not used, by the same rule or by registration:

* the 32 residual-516 diagnostic captures (309 shoot actions, 297 records) and the 8 deployment-split smoke captures
  (82, 82): pre-step snapshots only every 200th step and around refusals, so neither the listed option nor the pre-shot
  target state can be reconstructed for most shots; no pre-execution copies and no final state;
* the 2 PS-1 probe captures (3, 3) and the 2 T1-r diagnosis captures (no shot): one step without a pre-step snapshot
  and no final state, and (T1-r) no pre-execution copies;
* the exploratory and confirmation captures (`s8-*`, `s10-t9-v2-exploration`, `t9-confirmation-1`): the exploratory
  capture keeps only indirect-fire judgements and the confirmation capture none;
* every game record (aggregates only) and the replay corpus (seat observations and actions without the engine's
  feedback, so acceptance cannot be established apart from the record it would be paired with);
* the stopped 360-game prevalence study (registered stop: its folder is not opened), BOKE-2026 data, and anything first
  generated after the sprint began.

## 5. Pairing and integrity (SEMANTICS_AUDIT_INVALID)

For each step, from the step log (pre-execution copies, the engine's echoes, the step's new judge records) and the
snapshots (the all-seeing state before the step and after it, which is the next step's pre-step snapshot or the final
state):

* a submitted shoot action is **accepted** when exactly one shoot echo carries its seat, unit, target and weapon and no
  error, **refused** when that echo carries an error, and of **unknown acceptance** otherwise (no echo, several echoes, or
  two identical submissions);
* an accepted shot is **paired** with the step's direct-fire records naming its unit, target and weapon if there is
  exactly one and no other accepted shot claims it; **ambiguous** if there are several (excluded and counted; the
  rules let an anti-air unit adjudicate once per vehicle); a record is never used twice;
* a record no accepted shot claims is a **same-hex engagement** when its distance is 0, the attacker is in close combat
  before the step, or attacker and target share a hex before or after the step (the rules adjudicate same-hex combat
  automatically); otherwise it is **unexplained**.

The audit is **SEMANTICS_AUDIT_INVALID**, and stops without altered definitions, on any pinned file or frozen source
not matching its pin, a usable game failing to load, or any one of: an accepted shot without a record; a refused shot
with a record; a shot of unknown acceptance; a record claimed by two accepted shots; a paired record whose `cur_step` is
not the step's or whose colours disagree with the shooter's faction and the target's colour; a shooter or target absent
from the pre-step state; a shooting seat's observation missing; a missing snapshot or final state; a step's removed
units disagreeing with its snapshots; an unexplained record; a judge record of another type.

**Smoke runs before the freeze.** On the evaluation server from 2026-10-07T18:49:45+08:00 and, on the frozen code,
from 18:59:13+08:00 (its host clock, which runs ahead by the offset recorded in `docs/ENGINE_INSTALL.md`), 47 s each,
with identical counts: 18 games loaded, 0 integrity problems, 0 records of another type; of 982 shoot actions 975
paired, 5 ambiguous and 2 refused; of 1,210 records 975 paired, 12 in ambiguous groups and 223 same-hex engagements;
every paired shot's listed option found; every record's target in the pre-step state.

## 6. Target classes and the classes required

A unit's class is its observed `type` before the step: 1 infantry, 2 vehicle (every sub-type, unmanned ground vehicles
and artillery included), 3 aircraft, 4 fortification, anything else other (public observation reference).

The model is needed for **every target class on either side of a Sprint 20 HH changed shot** (the baseline shot and the
T11 shot): computed from the committed `evaluation/s20-t11-replay/replay.json`, these are infantry, vehicle, aircraft
and fortification. No shot is deleted or special-cased away; a required class whose semantics are not sufficient leaves
the model unavailable (section 11).

## 7. K2: the listed attack level against the adjudicated one

For every paired shot, the listed `attack_level` is the level of the option with the shot's target and weapon in the
shooting seat's pre-step `valid_actions` (missing or ambiguous listings are counted), and the adjudicated level is the
record's `att_level`. Reported: the number with both, equal and different, the difference distribution, and the same by
shooter class, target class, `ele_diff`, attacker strength (`att_obj_blood`) and weapon.

**K2_RUNTIME_SUPPORTED** only if every paired shot with both values has them equal, the paired shots cover two or more
`ele_diff` values (unless the whole corpus has only one), and no source contradicts it; any difference is
**K2_REFUTED_FOR_THE_SIMPLE_MODEL**; otherwise **K2_UNRESOLVED**. A class carries the corpus-wide status only if it has
paired shots of its own and they all agree; without any it is UNTESTED, and a difference in it refutes it.
Even exact equality shows only that the two values were equal on these records, not how the engine derived them.

## 8. K4: the random fields, the table mapping and the probability law

**Support (descriptive).** Per table: which of `random1`, `random2` and `random2_rect` are populated, their values, minima
and maxima, the joint `random1`-`random2` combinations, and `random2_rect - random2`. Nothing in it is evidence of a law.

**K4-MAPPING.** Each record's published cell is computed from the record's own `att_level` and `random1`, the target's
class before the step and, for the vehicle table, the attacker's count `att_obj_blood`: a personnel target reads the
personnel result table; a vehicle or fortification target reads the vehicle result table (the column of the attack level
in the row of the shooter's count), except the infantry light weapon, which reads the personnel table; an aircraft reads
the air result table; any other class has none. Cells are a number, suppression, annihilation or no effect (an empty
cell). The compared field is `ori_damage` where the record has it and `damage` otherwise. Per table:
**K4_MAPPING_SUPPORTED** only with at least one numeric cell, no numeric mismatch, every non-numeric kind mapped to one
single value, and no row outside the table; a mismatch, a non-numeric kind with two values or a row outside the table is
**K4_MAPPING_CONTRADICTED**; otherwise **K4_MAPPING_UNTESTED**. Reported for all records and for paired shots alone.
Also reported, descriptively: `rect_damage` against the published correction for `random2_rect` (personnel: at most 0
gives -1, 1 to 7 give 0, at least 8 gives +1; vehicles and fortifications: the correction bin and the target's
`armor`). The tables are transcribed in `src/miaosuan_agent/evaluation/s21_semantics.py`; a test parses the snapshot's
HTML and compares every cell.

**K4-PROBABILITY.** Supported only if (A) the public or SDK documentation states the probability law of the drawn
numbers, or (B) existing legitimate evidence exposes the generator or the exact law. The evidence, read before this
registration and recorded with verbatim quotations in `protocol.json`:

| Id | Route | Source | Finding |
|---|---|---|---|
| A1 | A | public rules, result tables | the tables are read with a random number from 2 to 12; how it is drawn is not stated |
| A2 | A | public rules, correction notes | dice are stated only for the corrections: two dice for vehicle targets, one for personnel targets |
| A3 | A | public observation reference, SDK observation notes | `random1` and `random2` are documented by name and type only |
| B1 | B | the project's harness evidence (`docs/BASELINE.md`) | the engine draws from neither of the process's global generators; no seed is documented; its own generator is not exposed |
| B2 | B | the frozen corpus | records carry drawn values only; a sample cannot establish a law, and no record names a generator or dice |

**Determination: K4_PROBABILITY_UNRESOLVED.** No goodness-of-fit result is used; no observed frequency replaces the law.
Because section 11 requires K4-PROBABILITY for every required class, this fixes the disposition at
DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED unless the audit is invalid. The audit is still run once, for the record of K2,
K4-MAPPING, K5 and K6 that any later direct-fire work needs; none of those findings can change the disposition except
through section 5.

## 9. K5: how the raw result, the correction and the final damage combine

For a record with correction fields, with `o = ori_damage`, `r = rect_damage`, `d = damage`, `B` the target's blood
before the step and `t` = 1 when the documented re-suppression loss applies (an infantry target already suppressed
before the step whose published cell is suppression), else 0, the registered relations are the six base forms, each
without the re-suppression term (t taken as 0) and with it (twelve relations):

| Base relation | `d =` |
|---|---|
| additive, unclamped | `o + r + t` |
| additive, lower clamp | `max(0, o + r) + t` |
| additive, lower and strength clamp | `min(B, max(0, o + r) + t)` |
| correction only on a positive raw loss | `max(0, o + r) + t` if `o > 0`, else `max(0, o) + t` |
| the same, with strength clamp | `min(B, that value)` |
| `rect_damage` is the final value | `r + t` |

Every relation is applied to the integers as recorded; a no-effect or suppression result enters through its recorded
`ori_damage`, whatever its value, and through the published cell for `t`. For a record without correction fields the
four relations read the published cell as the final loss: a number as itself, no effect and suppression as 0,
annihilation as the whole unit (`B`) or as 1, each without and with `t`. A record without a pre-shot blood, or without
correction fields and without a published cell, is not evaluable and is counted.

Evaluated per target class over every direct-fire record whose target is in the pre-step state (paired, ambiguous or
same-hex; the paired subset is reported apart). **K5_RUNTIME_IDENTIFIED** for a class only if, in each family present
(with and without correction fields), exactly one registered relation fits every row; several survivors are
**K5_UNDERIDENTIFIED** (observationally equivalent on these records), none is **K5_NO_REGISTERED_RELATION_FITS**, no
evaluable row is **K5_UNTESTED**. Reported with the coverage of the boundaries that separate them: no-effect and
suppression cells, positive raw loss, negative, zero and positive corrections, a lower clamp exercised (`o + r < 0`) and
a strength clamp exercised (`max(0, o + r) > B`).

## 10. K6: damage, blood and removal

Per target class, over target-steps with exactly one direct-fire record and the target in the pre-step state: A, a
target present after the step lost exactly the damage in blood; B, damage below the blood leaves it present; C, damage
at or above the blood removes it (present means listed in the all-seeing operators or passengers after the step). A
target whose launcher or carrier is removed in the same step with a lethal record of its own is excluded from tests A
to C and counted. **K6_SUPPORTED** for a class only with no contradiction of A, B or C, at least one lethal row and at
least one non-lethal row with positive damage; any contradiction is **K6_REFUTED**; a class without a lethal or a
non-lethal positive row is **K6_UNTESTED**.

Also reported: units removed in a step without a record of their own, by class, on board or not, and whether a unit they
depend on (launcher or carrier) was removed with a record in that step; never attributed to direct-fire damage of their
own. For fortifications (the rules adjudicate fire at a fortification as against vehicles and reduce its remaining
capacity; whether its `blood` tracks that capacity is what these tests ask): the same tests on the fortification itself,
"removal" meaning the fortification leaves the unit lists, and, descriptively, the units inside it before the step
(`fort` or `fort_passengers`), whether they had a record, lost blood or were removed. A fortification's removal is not
read as an enemy combat unit's destruction.

## 11. Sufficiency and dispositions (first match)

A class is sufficient only if K2 is supported for it, K4-PROBABILITY is supported, K5 is identified for it and K6 is
supported for it.

1. **SEMANTICS_AUDIT_INVALID**: section 5.
2. **DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED**: at least one required class is not sufficient. This closes T11-O1 under its
   registered endpoint; no engine probe; T2 is recommended next.
3. **DIRECT_FIRE_SEMANTICS_RESOLVED**: every required class is sufficient. This does not mean T11 passes.

## 12. Conditional continuation (only if resolved)

Only under DIRECT_FIRE_SEMANTICS_RESOLVED: an independent calculator of `p_kill_now` from the seat-observable state and
the listed option, frozen with tests from the published boundary cells, the runtime-supported mappings and synthetic
lethal and non-lethal cases before it sees a T11 row; validated on recorded draws for mechanics only; then the 94 HH
changed emitted shots of Sprint 20, unchanged, with Sprint 20's condition: T11_OFFLINE_PASS only if the candidate mean
exceeds the baseline mean (exactly zero fails), else T11_OFFLINE_NO_KILL_EDGE (`t11_completion`, frozen and tested now).
Under any other disposition no calculator is built and no T11 row is read.

## 13. Outputs, privacy and checks

* Public (`evaluation/s21-direct-fire-semantics/`): `protocol.json`, `inputs.json` and `mutation.json` (this
  registration); after the run `coverage.json`, `k2.json`, `k4.json`, `k5.json`, `k6.json`, `semantics.json` and
  `disposition.json`, aggregates only, every numeric key labelled (`blood_2`, `random_value_7`, `difference_minus_1`),
  each checked by the sanitizer against every unit identifier and hex of the corpus, and regenerated byte for byte by
  `scripts/s21_semantics.py run --check`.
* Private (evaluation server, ignored): `local/diagnostics/s21/rows-private.json.gz`, every shot, record, removal and
  fortification occupant row.
* Checks: synthetic tests of every rule (`tests/test_s21_semantics.py`, with the table transcription and quotations
  checked against the snapshot on the workstation); mutation tests in a copied tree whose unmutated copy passes first
  (`scripts/mutate_s21.py`, record `mutation.json`: 36 of 36 mutants killed before the freeze; the first run killed 35,
  and the survivor, integrity checked after sufficiency in the disposition order, was a test gap closed before the
  freeze); the committed files bound to the registration (`tests/test_s21_results.py`) and regenerated
  on the server (`tests/test_real_s21.py`); a private documentation gate with planted errors; every current
  historical gate; the full non-engine suites on the workstation tree, a clean clone and the server's private tree; the
  privacy scan compared as a set with the 104 accepted hit lines; the platform canary rebuilt; a read-only ledger verify
  showing 2,795 sessions and none unclosed.

## 14. Not claimed

The audit describes what engine 4.1.0 recorded in 18 games; a relation that holds on them is a runtime observation, not
a published rule, and a relation that is not exercised is not established. K4-PROBABILITY is a statement about the
documentation and the existing evidence, not about the engine, which may draw from a definite law nobody has published.
No probability is fitted, no tactic is evaluated, and nothing is promoted.
