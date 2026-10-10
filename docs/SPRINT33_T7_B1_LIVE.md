# Sprint 33: T7-B1 live stop mechanism qualification

**EXPLORATORY TRACK - REGISTERED TWO-GAME MECHANISM QUALIFICATION - AT MOST SESSIONS 2801 AND 2802 - NOTHING PROMOTED -
NOTHING UPLOADED - SCORE IMPROVEMENT IS NOT AN ENDPOINT**

Dates are business dates in UTC+8 (2026-10-10). Sections 1 to 8 (the authorization, the candidate, the verified
opportunities, the pre-engine validation, the registered rules, the gate, the dispositions and the pre-engine checks)
are committed and pushed before session 2801 opens; later sections are written afterwards and say so. No registered
section is edited afterwards.

## 1. Starting state and the owner's instruction

| Item | Identity |
|---|---|
| Frozen Sprint 32 branch | `sprint32-t7-b1`, head `5369a1cae56f9559803fbd668f858ba5309ede3d`, tree `b3061fd52f188eb7ad9c886eade5128549a6f86a`, identical on the workstation, GitHub and the evaluation server |
| `main` | `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85`, unchanged |
| Engine ledger | 2,800 sessions opened and closed, none unclosed; ledger file SHA-256 `fde702863518b42eb983a206eab2fd3c870966cce338e61b8cfce129e3ebb799`; session 2801 unopened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, unchanged |
| Privacy baseline | 106 accepted hit lines in the published scope |

**Sprint 32 stands.** The owner accepted the registered disposition `S32_PREFLIGHT_INADEQUATE`; it is not modified or
reinterpreted, and nothing here is a retrospective pass for it.

**Authorization (owner, Option 1 of the Sprint 32 report).** A new, separately registered mechanism study of T7-B1 in
the two genuinely observed configurations with `baseline-v2` blue against the inert control red, instead of the
originally proposed pair in 2130511121. At most two engine sessions, run in order: 2801 (2120531121 C3) and 2802
(1930331196 C3), the second only when the registered gate after the first allows it. No retry, no replacement game, no
substitution, no session 2803, no other engine study. Spending both sessions is not required.

## 2. Isolation and server use

All work is on the branch `sprint33-t7-b1-live`, created from the frozen Sprint 32 head in a separate workstation
worktree and in a separate server worktree whose ignored `local/` folder is a folder of links to the existing private
folders (one engine installation, one ledger). The shared workstation checkout (whose two uncommitted
platform-compatibility files belong to another session), the server checkout (`main`), the `platform-compat2` branch,
every earlier sprint branch, the canary, its builder and the adapter are not touched; `main` is not changed; only the
new branch is pushed and nothing is merged. Server CPU policy (`docs/SERVER_RESOURCE_POLICY.md`, shared mode): at the
pre-work check a colleague's job held NUMA node 1 (logical CPUs 16-31 and 48-63) and node 0 carried other work of this
account; this project's jobs run pinned to node 0 (logical CPUs 0-15 and 32-47), and each engine game is one serial
process.

## 3. Research question and endpoints

Can an own ground unit that is actively moving (A) receive a listed stop, (B) have it accepted, (C) finish its current
hex, (D) have its remaining route cleared, (E) enter the documented 75-step stop transition, (F) complete it within the
registered tolerance, (G) recover movement and firing options, (H) fire at a visible, eligible target if one remains,
and (I) avoid an indefinite deferred stop and a persistent movement deadlock?

* **Primary endpoint: stop execution semantics** (A to G and I).
* **Secondary endpoint: engagement** (H): a shot listed, emitted and accepted after the transition.
* **Not an endpoint:** any score. The inert-control scores are a harm screen only (section 6.4); a successful or
  high-scoring game against the inert control says nothing about tactical value.

The documented contract (platform rules snapshot of 2026-09-29, quoted in `docs/SPRINT32_T7_B1_PREFLIGHT.md`, section
3.1): the moving unit must complete the hex it is moving into, the rest of the move is dropped, and a 75-second penalty
transition follows in which it can do nothing; non-tank ground units fire only when stopped.

## 4. The candidate: `t7-b1-stop-engage-1`, unchanged

`src/miaosuan_agent/experiments/t7_b1_stop_engage.py`, byte-identical to Sprint 32 (normalised SHA-256
`d7fff57a49850d877917360327a34983e05d8ffac3e4a2710f08571d71ade0dd`); its rule is Sprint 32's section 4. Policy source
over `baseline-v2`'s 22 files, the add-on wrapper and the candidate (24 files):
`97658f4d89e47eb247704f1995754a1e81d32e8b60dcce9ae4ed61c6e068fd84`. `baseline-v2` decides first on the live
observation, unchanged; the add-on appends only a listed, parameterless stop in the documented key set `actor`,
`obj_id`, `type` for a traversing non-tank ground unit that `baseline-v2` leaves without an action, never twice to one
unit in a game, never to a waiting unit (`speed` 0 with a path), and never with constructed parameters. No pre-engine
correctness defect of the candidate was found, so no new candidate identity exists. Its status text ("no engine use
authorized") predates this authorization and is left unchanged with the file.

## 5. The two configurations and their verified opportunities

Re-read from the committed Sprint 32 preflight (`evaluation/s32-t7-b1/preflight.json`, SHA-256
`ec94e9847fe5ceedfcde210b61040b5572696af3b28b3a5829ee065684b946f0`), whose verified inert configurations are blue only
(1930331196 C3 and 2120531121 C3; none for red):

| Position | Session | Configuration | Recorded first divergence | Unit and weapon | Distance (range) |
|---:|---:|---|---:|---|---|
| 1 | 2801 | 2120531121 C3: inert red, candidate blue | step 380 | vehicle, vehicle-mounted missile | 18 (20) |
| 2 | 2802 | 1930331196 C3: inert red, candidate blue | step 620 | vehicle, vehicle-mounted missile | 20 (20) |

Both come from genuine full-step `baseline-v2` records, each with a valid first divergence and no independent-check
finding. They are the steps at which the candidate's rule first fires on those records. Nothing here predicts any
event after the live game diverges, and no historical observation after a divergence counts as live evidence. Whether
the live first stop falls at the recorded step is reported descriptively (section 6.6).

## 6. Pre-engine validation (private probes on genuine records; no engine)

Before the rules were fixed, three private probes (`local/diagnostics/s33/validate_timing.py`,
`probe_fire_listing.py`, `probe_prefix.py`, logs beside them) read the three Sprint 10 inert games (HI: 2120531121 C3,
1930331196 C3, 1930331196 C2) and the full-step timelines of sessions 2797 to 2800 (TL), own ground units of every
policy seat. No record contains a stop on a traversing unit, so these probes test the rules' reading of the movement,
transition, listing and judgement machinery that a stop shares with a natural arrival; they cannot show what a stop
does.

### 6.1 Timing (Sprint 32's tolerance and deadlines are kept)

| Check | HI | TL |
|---|---:|---:|
| traversing observations whose next-hex entry happened exactly at `cur_step + ceil((1 - cur_pos) / speed)` (unit kept moving), of all such observations | 64,274 of 64,274 | 139,171 of 139,171 |
| entries into the last hex of a path with the path empty in the entry frame | 3,560 of 3,560 | 11,044 of 11,044 |
| natural arrivals with `stop` 0, `move_to_stop_remain_time` 75 and `flag_force_stop` 0 at the first empty-path frame | 98 of 98 | 317 of 317 |
| completed transitions with `stop` 1 exactly 75 steps after the path emptied | 24 of 24 | 55 of 55 |
| completed transitions with movement listed in the completion frame | 24 of 24 | 55 of 55 |
| own ground unit-decisions with `flag_force_stop` 0 | 190,146 of 190,146 | 350,706 of 350,706 |
| shots emitted by a policy seat, echoed in their own step without an error and named as attacker by a judge record in the same step | | 322 of 322 |

So the hex-completion count `h0`, the clearing deadline, the transition window and the shot-acceptance window of
Sprint 32's rules (`evaluation/s32_mechanism.py`: tolerance 2 steps) agree with every recorded natural movement and
shot. `flag_force_stop` never left 0 in any record: what it does during a stop on a moving unit is unknown.

### 6.2 The one correction: transient versus indefinite deferral

Sprint 32's code marks a stop `deferred` (adverse) when `flag_force_stop` is 1 at any later frame, while its own
taxonomy names indefinite deferral as the adverse outcome. The only recorded behaviour of the flag
(`docs/PS1_ENGINE_PROBE.md`, B-4) is a stop that is pending because it cannot take effect yet (the unit waits in
front of a full hex, keeps its path and lists nothing for the rest of the game), and the documented contract makes a
moving unit's stop pending until its current hex is complete. A flag raised while the unit completes its hex and gone
when the path clears is therefore the documented sequence itself, and Sprint 32's code would read it as adverse: on
the Sprint 33 stand-in world, whose stop follows the documented contract with that transient flag, Sprint 32's
classification gives `ADVERSE` and Sprint 33's gives `OBSERVED` (`tests/test_s33_pilot.py`). Sprint 33 therefore
registers, under the new rules identity `s33-t7-b1-mechanism-1` (`evaluation/s33_mechanism.py`), `deferred_indefinite`
in place of `deferred`: `flag_force_stop` 1 together with a non-empty path at a frame at or after the clearing deadline
`s0 + h0 + 2`. The transient flag is reported (frames, first and last offset, whether it outlasts the path). Every
other adverse outcome, window, deadline, censoring rule, verdict and the disposition order are Sprint 32's, called
unchanged, and Sprint 32's own adverse list, game verdict and disposition are computed and reported beside Sprint 33's.

### 6.3 The firing-opportunity reading

Sprint 32 calls a completed stop's firing opportunity evaluable when an enemy ground unit in the unit's own
`see_enemy_bop_ids` lies within the published range of one of its weapons from its hex, and `NOT_ENGAGING` when no
shot is then listed. On settled, unsuppressed non-tank own units in the two selected configurations' records (HI
2120531121 C3 and 1930331196 C3, TL session 2798) that had not fired before, the reading coincided with a listed shot
in 4 of 4 unit-decisions; the 2 evaluable unit-decisions without a listed shot followed the unit's own shot by at most
30 steps. Against the moving opponents of the head-to-head records the reading does not predict the listing (32
listed, 263 not, among evaluable unit-decisions of units that had not fired), so the rule is applied only to these
inert configurations, whose targets never move; it is kept unchanged.

### 6.4 Determinism of the inert games

Sprint 31's session 2798 played the K2 candidate, which equals `baseline-v2` until its first withholding at step 341,
in configuration 2120531121 C3. Against Sprint 10's record of `baseline-v2` in the same configuration, the policy
seat's actions were identical through step 340 (first difference at step 341), and every own and enemy ground unit's
hex, path, speed, progress and transition fields through step 341; combat outcomes differed earlier (the judge records
from step 168, a unit's damage from step 243). So movement reproduces up to a policy's first divergence while combat
outcomes are random; the live first stop is therefore likely, not certain, to fall at the recorded step.

## 7. Registered rules (frozen before session 2801)

Code: `evaluation/s33_pilot.py` (identities, card, ledger audit, structural stops, frames and orders, facts, harm
screen, gate, disposition, sanitization), `evaluation/s33_mechanism.py` (section 6.2 and the endpoints of 7.2),
`evaluation/s33_capture.py` (observer), `scripts/build_s33_card.py`, `scripts/run_s33_game.py`,
`scripts/run_s33_pilot.py`, `scripts/s33_analysis.py`: Sprint 31's proven runner, ledger audit and full-step
observer, adapted; no new framework. Card `evaluation/s33-t7-b1-live-1/manifest.json` (exploratory run-card schema):
the two games of section 5, ledger base 2800, cap 2, one worker, runtime `baseline-v1-runtime-r2`, `track:
EXPLORATORY`, `eligible_for_promotion: false`, the rules and their SHA-256, and the normalised SHA-256 of 26 frozen
files.

### 7.1 Structural stops and action fidelity (any of them stops the check)

`S1` installation integrity; `S2` ledger (a session out of order, under another card or digest, recovered, unclosed,
or beyond 2802); `S3` repository exposure; `S4` contract error, an incomplete game or a wrong margin identity; `S6` a
replay mismatch; `S7` capture or reconstruction: an observer error, a capture digest mismatch, a live decision or
memory differing from its seat-local reconstruction (`baseline-v2`'s actions, trace digest and memory chain, the rule
on its actions and the add-on memory chain), a live action list that is not `baseline-v2`'s list unchanged and in
order followed by exactly the rule's documented stops, a unit stopped twice, a finding of Sprint 32's independent
restatement of the trigger at any decision, an add-on error, disagreeing move or stop counts between the timeline and
the record, a wrong scenario, condition, seat or opponent, or a `max_step` other than 2,880.

### 7.2 Per stop (`evaluation/s33_mechanism.classify`)

Sprint 32's events with their windows (tolerance 2 steps): rejected (an error echo within 2 steps); path cleared by
`s0 + h0 + 2` (else `path_not_cleared`); where (`next_hex` as documented, `in_place` reported, `elsewhere` =
`overrun`); transition started at the clearing frame (else `no_transition`); completed at the clearing step plus 75,
plus or minus 2 (else `transition_timing`); movement listed within 2 steps of completion (else `unable_to_resume`);
firing opportunity evaluable and shot listed within 2 steps; shot accepted (emitted within 2 steps, echoed without
error and named as attacker by a judge record in its step or the next); censoring (lost before the path cleared or
during the transition, game over before a deadline, suppressed at completion: never positive and never adverse); plus
`deferred_indefinite` (section 6.2). Reported endpoints, which never change a verdict: stop listed, emitted in the
exact form, echoed clean or refused; flag frames; expected and observed next-hex entry; transition start and
completion offsets; shot emitted, refused; judge records and damage in the window and after completion; the first
later MOVE for the unit, its refusal and whether the unit then traversed again (movement resumption); other own units
waiting at the stop hex (blocked frames) and the longest deadlock run (Sprint 32: 300 frames with a full hex);
`baseline-v2` actions for the unit before the stop took effect.

### 7.3 Per game, first match (Sprint 32's `game_verdict` on Sprint 33's adverse lists)

`STRUCTURAL`; `ADVERSE` (any adverse outcome of any stop, or a deadlock run of 300 frames); `HARM`; `NOT_ENGAGING` (a
completed stop with an evaluable firing opportunity and no listed shot); `UNTESTED` (no completed, uncensored stop
without an adverse outcome, including a game with no stop at all); `STOP_ONLY` (completed stops, none with an
evaluable firing opportunity); `OBSERVED` (a completed stop whose firing opportunity was met by a listed shot).

**Harm screen** (Sprint 30's committed controls, `evaluation/s30-t13-k1/controls.json`, SHA-256
`27dffdfdfa2f920a921cb68da389bed80bb7a6e01950de7ffaac54b34c186e93`: `baseline-v2`'s fifteen group C games per
configuration against the inert control): `HARM` when occupy is below the configuration's constant control occupy, or
the margin is below the control minimum minus 50; the boundaries pass.

| Configuration | Control occupy (constant) | Control margin minimum | Harm floor |
|---|---:|---:|---:|
| 2120531121 C3, `baseline-v2` blue | 310 | 559 | 509 |
| 1930331196 C3, `baseline-v2` blue | 310 | 570 | 520 |

Head-to-head scores are not used.

### 7.4 Gate after session 2801

Session 2802 opens only when game one completed with no structural stop and its verdict is `UNTESTED`, `STOP_ONLY` or
`OBSERVED`, its stored analysis regenerates byte for byte from the preserved record and captures, and the ledger audit
shows exactly session 2801 under this card. `STRUCTURAL`, `ADVERSE`, `HARM` and `NOT_ENGAGING` close it. An `UNTESTED`
first game does not close it, because configuration 2's opportunity is verified from its own genuine full-step record
(step 620), independently of configuration 1. After session 2802 the check stops whatever the result.

### 7.5 Disposition, first match, and what each label establishes

| Disposition | When | Establishes |
|---|---|---|
| `T7B1_MECH_INVALID` | no game, a structural stop, an incomplete game, a ledger problem, a game behind a closed gate, more than two games, or one game with the gate still open | nothing |
| `T7B1_MECH_REJECT` | an `ADVERSE` or `HARM` game | a registered adverse mechanism or harm result |
| `T7B1_MECH_NOT_ENGAGING` | a `NOT_ENGAGING` game | a completed stop with an in-range visible target and no legal shot |
| `T7B1_MECH_SUPPORTED` | an `OBSERVED` game | evidence level `STOP_AND_SHOT_ACCEPTED` (a shot accepted after a completed stop) or `STOP_AND_SHOOTING_LISTED` (a shot listed, none accepted) |
| `T7B1_MECH_STOP_ONLY` | a `STOP_ONLY` game | evidence level `STOP_AND_MOVEMENT_RESUMPTION` (the unit later moved again on a `baseline-v2` order) or `STOP_EXECUTION` (stop semantics only) |
| `T7B1_MECH_UNTESTED` | otherwise | no completed, evaluable stop |

A listed shot is never reported as an accepted shot, and a completed stop with no target in range at completion is
evidence for stop semantics, not for engagement. None of these labels promotes T7-B1, establishes battlefield value or
authorizes a wider test.

## 8. Checks before session 2801

Recorded at registration (section 9 lists the results).

* Tests: `tests/test_s33_mechanism.py` (the correction at its boundary, every endpoint, the evidence levels, Sprint 32
  preserved) and `tests/test_s33_pilot.py` (the card and its pins against the committed controls and preflight, every
  ledger defect, every structural check, the harm boundaries, the gate, the disposition order, and the real game loop
  in a stand-in world, `tests/fixtures/s33_engine.py`, under every stop behaviour: documented with and without the
  transient flag, refused, deferred, in place, late, without resumption, without a listed shot), with the Sprint 32
  candidate and mechanism tests and the full non-engine suite.
* Mutation: `scripts/mutate_s33.py`, record `evaluation/s33-t7-b1-live/mutation.json` (the card is rebuilt inside each
  mutated copy, so that its pins never kill a mutation by themselves).
* An engine-free rehearsal of the runner, game entry point, observers and analysis (`local/diagnostics/s33/
  standin_rehearsal.py`): the real runner with the engine replaced by the stand-in and the ledger session by a context
  that records nothing.
* The card rebuilt byte for byte, every frozen digest, the controls and preflight hashes, the ledger state (2,800
  sessions, none unclosed, next 2801), the platform canary, the privacy scan of the published scope, the server
  resource allocation, and the byte identity of the registration on the workstation, GitHub and the server.

## 9. Results of the checks before session 2801 (written before session 2801)

* **Tests.** The workstation suite ran 2,601 tests (Sprint 32's 2,558 plus this sprint's 43), 114 skipped, exit 0. On
  the evaluation server (CPython 3.10.20) the Sprint 33, Sprint 32 and Sprint 31 rule modules and the documentation
  policy ran 130 tests, OK.
* **Mutation** (`evaluation/s33-t7-b1-live/mutation.json`): 35 of 35 planted defects caught. Two earlier runs found
  test gaps, each closed with a new test before the recorded run: a first run, stopped part-way because its tests
  were being edited, had let 2 of its first 21 defects survive (a censored stop counted as qualifying, which only a stop suppressed at
  completion can show; moving units counted as blocked at the stop hex); a full second run caught 32 of 35 (an
  incomplete second game and a structural second game accepted, which a one-game case cannot show because a single
  game with an open gate is invalid anyway; an independent-check finding ignored, which the stand-in never produces).
* **Engine-free rehearsal** (`local/diagnostics/s33/standin_rehearsal.py`, on the server, committed tree with the
  clean-tree guards active): the real runner played position 1 in the stand-in world, wrote the record and four
  captures with matching digests, stopped only on the fake session's ledger absence, and wrote an analysis that
  regenerates byte for byte; the one stop had no Sprint 33 adverse outcome and demonstrated every endpoint (Sprint
  32's preserved list: `deferred`), and the stand-in's scores (not the scenario's) gave `HARM`, which closed the gate;
  position 2 was refused behind that gate and, with the check patched, played 1930331196 C3 with the candidate blue; a
  deferred stop gave `ADVERSE` (`deferred_indefinite`, `path_not_cleared`); position 1 after a session, an unknown
  game, an existing record and a dirty-tree flag were refused; the ledger file was unchanged.
* **Card** `evaluation/s33-t7-b1-live-1/manifest.json`: canonical SHA-256
  `ab1026bfb3307150cef04064adf039d11b2f942db9c7332a11903c5b974da99f`, rebuilt byte for byte on the workstation and the
  server; candidate digest, controls and preflight hashes as in sections 4, 5 and 7.3.
* **Engine** (read-only verify): 2,800 sessions opened and closed, none unclosed, integrity ok, state chain
  continuous, last event the close of session 2800; ledger SHA-256 as in section 1. Next session 2801.
* **Platform canary** rebuilt from this branch into a scratch folder:
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` (107,646 bytes, 26 files), isolated smoke 62 steps
  with 0 mismatches.

## 10. Order of work (written after session 2802)

The registration (sections 1 to 9, the code, the card and the mutation record) was committed as
`d97e4227a8921f17299e18534b663508faf33b11` (tree `1198fe0e548fe6018f126335472209cba9c3cb01`) and pushed at about
2026-10-10T13:47+08:00; GitHub and the server worktree then held the same commit and tree, the server worktree was
clean and rebuilt the card byte for byte, and the scan of every blob reachable from the published refs (1,264 blobs)
gave 106 hit lines, identical as a multiset to the accepted baseline. Both games were then played with
`scripts/run_s33_pilot.py --position n`, pinned to NUMA node 0, while a colleague's job held node 1. Ledger events
(the evaluation server's host clock, UTC): session 2801 opened 05:55:07 and closed 05:57:06; session 2802 opened
05:59:02 and closed 06:00:47. Between them the runner re-read the ledger and regenerated game one's stored analysis
byte for byte before opening session 2802, as section 7.4 requires. No game was retried or replaced; no session 2803
was opened.

## 11. Game results (written after session 2802)

Read from the committed `evaluation/s33-t7-b1-live/game-p01.json`, `game-p02.json` and `disposition.json`, which
`scripts/s33_analysis.py report --check` regenerates byte for byte from the private records and captures.

| | Session 2801, 2120531121 C3 | Session 2802, 1930331196 C3 |
|---|---|---|
| Completion | 2,881 steps, no structural stop | 2,881 steps, no structural stop |
| Stops emitted (each listed, in the exact documented form, echoed without error) | 3 | 2 |
| First stop | step 380, the recorded first divergence | step 620 (two units), the recorded first divergence |
| Rejected, deferred indefinitely, overrun, in place | none | none |
| Next hex entered at the predicted step `s0 + h0`; path cleared in that frame | 3 of 3 (`h0` 20, 19, 19) | 2 of 2 (`h0` 20, 20) |
| Transition started at the clearing frame (`move_to_stop_remain_time` 75, `stop` 0) and completed exactly 75 steps later | 3 of 3 | 2 of 2 |
| `flag_force_stop` | 1 from the step after the order until the step before completion (94, 93 and 93 frames), 0 at completion | the same (94 frames each) |
| Movement relisted at completion | 3 of 3 | 2 of 2 |
| Movement resumed (a `baseline-v2` MOVE accepted, the unit traversing again) | 3 of 3, the MOVE emitted 0 to 1 steps after completion | 2 of 2, at completion |
| In-range visible enemy at completion (firing opportunity evaluable) | 1 of 3 | 0 of 2 |
| Shot listed, emitted and accepted (echo without error, judge record naming the unit, damage) | 1 of 1 evaluable | none (no opportunity) |
| Deadlock runs; other own units blocked at a stop hex; `baseline-v2` actions for a unit before its stop took effect | 0; 0; 0 | 0; 0; 0 |
| Occupy (control 310); margin (harm floor) | 310; 599 (509) | 310; 570 (520) |
| Own ground units lost | 0 of 24 | 0 of 24 |
| Refused actions of the candidate seat | 0 | 1 (a `baseline-v2` shot at a unit already destroyed, error 516; not a stopped unit) |
| Sprint 33 verdict (Sprint 32's preserved verdict) | `OBSERVED` (`ADVERSE`: `deferred`) | `STOP_ONLY` (`ADVERSE`: `deferred`) |
| Gate | open | open (the check stops after session 2802 regardless) |

## 12. Disposition: `T7B1_MECH_SUPPORTED`, evidence level `STOP_AND_SHOT_ACCEPTED`

First match over the two games (`OBSERVED`, `STOP_ONLY`): no structural stop, no adverse or harm verdict, no
`NOT_ENGAGING` game, and an `OBSERVED` game. Endpoints demonstrated by at least one completed, uncensored stop without
an adverse outcome: `STOP_EXECUTION`, `MOVEMENT_RESUMED`, `SHOOTING_LISTED`, `SHOT_ACCEPTED`.

What this establishes, on engine 4.1.0 in these two inert configurations: all five stops of non-tank vehicles moving
with a target in range were accepted, took effect exactly where and when the documented rule puts them (the hex being
entered, at the step the progress fields predict), cleared the rest of the route, served exactly the 75-step
transition, and left the unit able to move (all five moved again on `baseline-v2`'s next order) with no deadlock and no
blocked friendly unit; in the one stop with a visible target in range at completion, a shot was listed, emitted and
accepted with damage. Engagement rests on that single stop. The other four completed stops are evidence for stop
semantics only.

What it does not establish: any tactical or score benefit (the scores are a harm screen: both games equal or exceed
their control minimum, and the inert opponent never fights back); behaviour against an active opponent, under fire, in
other scenarios, for infantry, or with more than one stop per unit; promotion; or a basis for a wider A/B test.

**Sprint 32's preserved classification.** Every stop carried `flag_force_stop` 1 after its path cleared, so Sprint 32's
rule reads each one as `deferred`: its verdicts are `ADVERSE` in both games, its gate would have closed after session
2801 (disposition `T7B1_MECH_REJECT` on that game alone), and over the two games actually played its disposition is
`T7B1_MECH_INVALID` (a game behind its closed gate). Sprint 33's registered `deferred_indefinite` (the flag together
with a non-empty path at or after the clearing deadline) did not occur. The published `order` field of
`disposition.json` lists the six labels in the constant order of `evaluation/s32_mechanism.DISPOSITIONS`, not in the
first-match order, which is section 7.5's.

## 13. Post hoc reading (after the disposition; changes nothing)

`local/diagnostics/s33/posthoc.py` on the private captures:

* **The flag outlasts the path.** Section 6.2 expected the flag to fall when the path clears; it fell at transition
  completion instead (1 at the clearing frame, 0 at completion, in all five stops). The registered definition did not
  depend on that expectation and needed no change; the rationale's description of the flag was wrong in that detail.
* **Listing during the transition.** Throughout every transition the unit listed action 6 only; the rules text says no
  operation is possible in that period. Nothing here tested whether that action is accepted.
* **Why four stops had no firing opportunity.** In the second and third stops of session 2801 and both of session
  2802 the target named at the order stayed in place within published range of the stop hex (17 and 20 hexes), but
  left the unit's own `see_enemy_bop_ids` once the unit stood on the stop hex, and no other enemy was visible to it.
  The candidate checks range from the stop hex but visibility from where the unit is at the order; visibility from
  the stop hex is not seat-observable in advance. This is a design limit of the candidate, not a stop failure.
* **The accepted shot.** In the first stop of session 2801 the target was visible at 18 hexes at completion; the shot
  was emitted at completion, and the target was no longer present one step later.

## 14. Limits

* Two games, five stops, one engaged target, all against an inert opponent in blue seats; one candidate rule and one
  unit class (vehicle with a vehicle-mounted missile).
* The engagement endpoint is demonstrated once; the firing opportunity disappeared in four of five stops for a
  visibility reason the candidate does not model.
* Combat outcomes in these games are random while movement reproduced (section 6.4); a different damage roll can
  change later trajectories.
* The movement and transition timing agrees exactly with the natural-arrival records, but the stop's own engine
  semantics were observed only in these five instances.

## 15. Close-out

* **Engine**: read-only verify on the evaluation server after session 2802: 2,802 sessions opened and closed, none
  unclosed, integrity ok, state chain continuous, the last event the close of session 2802; ledger file SHA-256
  `b91d0538c96a855513de98226b28d21c4484785cc6dab1dadc5b50d6d3c69dbe`. No installation, state file or configuration was
  touched. No session 2803 exists.
* **Reproducibility**: both stored analyses (`scripts/s33_analysis.py game --position n --check`) and the public
  report (`report --check`) regenerate byte for byte from the private records and captures on the server.
* **Platform canary** rebuilt from the results commit into a scratch folder:
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, isolated smoke 62 steps with 0 mismatches; the
  builder, the adapter and every `baseline-v2` lineage module are unchanged since Sprint 32.
* **Tests**: the workstation suite at the results commit ran 2,601 tests, 114 skipped, exit 0.
* **Document checks** (private, `local/diagnostics/s33/doc_check.py`): 39 clauses of sections 1, 5, 6, 7.3 and 9 to 12
  rebuilt from the logs, records and committed results, every one present, and 19 of 19 planted single-number errors
  caught.
* **Privacy**: the scan of every blob reachable from the published refs (1,270 blobs before this section) gives 106
  hit lines, identical as a multiset to the accepted baseline; the concurrent `platform-compat2` branch is outside that
  scope, as in Sprint 32. Raw observations, unit identifiers, hexes and captures stay under the ignored `local/`.
* **Isolation**: `main` stays at `08aff3f`; `platform-compat2`, the shared workstation checkout's two uncommitted
  files, the server checkout and every earlier sprint branch are untouched; only `sprint33-t7-b1-live` was pushed and
  nothing was merged or uploaded. The server worktree is removed after the final check; its branch ref stays in the
  server clone.

**Recommended next action (one): the owner's review of `T7B1_MECH_SUPPORTED` together with its limits (section 14),
before any further T7-B1 work.** No engine session is requested. The visibility limit of section 13 would need a new,
separately identified candidate and its own offline qualification; nothing here proposes one.
