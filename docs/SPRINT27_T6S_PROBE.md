# Sprint 27: T6-S registered two-seat mechanism probe

**REGISTERED — EXPLORATORY TRACK — MECHANISM PROBE, NOT A CONFIRMATION AND NOT A SCORE SCREEN — AT MOST TWO ENGINE SESSIONS (2797, THEN 2798 ONLY IF 2797 PASSES ITS GATE) — NOTHING PROMOTED**

On 2026-10-09 the owner approved the DRAFT probe of Sprint 26 (`docs/SPRINT26_T6S_PROBE_DRAFT.md`), which followed
Sprint 26's registered disposition `T6_S_OFFLINE_PASS`, with one prospective clarification of the first-ownership stop
(section 4), and authorized at most two engine sessions in scenario 2130511121: session 2797, the candidate blue against
frozen `baseline-v2` red, and session 2798, the candidate red against frozen `baseline-v2` blue, the second only if the
first passes every registered integrity and early-stop check. No retry, no replacement game, no third session and no
policy promotion. The candidate identity is `t6s-column-stagger-p1`. This is an exploratory mechanism probe: it asks
whether the frozen stagger executes on the candidate's own trajectory and what it costs there, not whether the candidate
plays better. Dates are business dates in UTC+8.

Sections 1 to 20 are the registration. They are committed and pushed, with every frozen file, the card, the frozen
references, the rehearsal, the tests and the mutation record, before session 2797 is opened, and are not edited
afterwards; results follow in a separate section.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `cb120a7d143ea74de32733aae2907ca638921b4e`, tree `558dc0021d4ac5cebafdb6200d33bcdea94828de`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | read-only verify at the start of the sprint: 2,796 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `eaae02bb0b1805a6ee0cf757f96fa39ec8e443f821835b6feb994dee55230bea` |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Candidate (the only new engine policy) | `t6s-column-stagger-p1`, policy source `9d74eb78208ff7ad10b33b3974f2831754122dba2bff1684177d6fbd4b44e29e` (section 6) |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` |
| Privacy baseline | the 106 accepted hit lines of `local/diagnostics/s25/privacy-baseline-106.txt`, compared exactly |

## 2. Frozen history and scope

* Not reinterpreted and not reopened: Sprint 26 `T6_S_OFFLINE_PASS` and its frozen rule, registration and results;
  Sprint 24's selection; T6-G `T6_G_OFFLINE_INADEQUATE_OPPORTUNITY`; T9 SHELVED; T13-D1 `T13_D1_NOT_READY`; T2-X1
  SHELVED; T2-P1 `T2_P1_MECHANISM_SUPPORTED`. No document, test or result of Sprint 24 or Sprint 26 is edited.
* Two engine sessions at most, in order, each an exclusive diagnostic session in the registered runtime
  (`baseline-v1-runtime-r2`), one game per session. A session that was opened counts even if it fails.
* No change to `baseline-v2`, the stable core, the registered evaluator, the engine installation or configuration, or
  any historical output.
* Never used: BOKE-2026, the stopped 360-game prevalence study, any game other than the two of this card.

## 3. Question

On the candidate's own on-policy trajectory, against frozen `baseline-v2`, in both seat orders of 2130511121: does the
frozen T6-S stagger fire, withhold only the registered follower MOVEs and release them as registered; do leader and
followers move apart and stay apart; do stacked moving own ground unit-decisions inside applicable envelopes fall to at
most half of the same-colour HH references (P1); and is any objective first owned later than its same-colour HH
reference, or never (P2)? It does not ask whether the candidate scores better: score enters no rule and cannot rescue a
stop.

## 4. The owner-approved clarification of P2 (prospective)

Sprint 24 registered the probe's stops as "stacked moving unit-steps inside envelopes not halved against HH, or any
objective first owned later than in all four HH games" (`evaluation/s24-tactical-frontier-reselection/experiments.json`,
T6 entry, `stop`). Sprint 26's draft (section 5) left the comparison set to the owner because the four HH games mix
seat colours whose distances to each objective differ.

**Owner decision (2026-10-09, before any Sprint 27 engine session, this registration being its first record):** the
primary P2 reference is the two same-colour historical HH `baseline-v2` seats: for the candidate blue, HH p01 and HH p03
(`baseline-v2` blue); for the candidate red, HH p02 and HH p04 (`baseline-v2` red). The candidate's first ownership is
never compared with the other colour's for the primary endpoint. Sprint 24's four-game mixed-colour reading is reported
as a sensitivity analysis only. This is a prospective clarification of Sprint 24's wording; Sprint 24 and Sprint 26
are not edited. The HH games played `baseline-v2` against a different candidate (Sprint 12's batch-capacity
allocator), not against `baseline-v2`, so these references are exploratory historical benchmarks, not a randomized or
paired causal control.

## 5. Design

| Item | Registered |
|---|---|
| Scenario | 2130511121 (Sprint 24's registered probe scenario; the HH scenario) |
| Stage A | session 2797: `2130511121.H2.s27-t6s-probe-1.p01`, the candidate blue, `baseline-v2` red |
| Stage B | session 2798: `2130511121.H1.s27-t6s-probe-1.p02`, the candidate red, `baseline-v2` blue, only if stage A's gate authorizes it (section 15) |
| Candidate | `t6s-column-stagger-p1` (section 6) |
| Opponent | frozen `baseline-v2` (policy source `7cbaf032...`) |
| Runtime | `baseline-v1-runtime-r2`, one worker, one game per exclusive session |
| Card | `evaluation/s27-t6s-probe-1/manifest.json`, built and checked by `scripts/build_s27_card.py`: the two games, ledger base 2796, ceiling 2, the frozen rules and the normalised SHA-256 of every frozen file (`s27_probe.FROZEN_FILES`) |
| Capture | Sprint 9's `T9Capture` and the exploratory capture, both unchanged, and the Sprint 27 full-step timeline (section 9) |
| References | the four Sprint 12 head-to-head `baseline-v2` seat-games (HH), by colour (section 10) |

## 6. The candidate `t6s-column-stagger-p1`

`src/miaosuan_agent/experiments/t6s_column_stagger_p1.py` (identity `t6s-column-stagger-p1`, add-on
`t6s_column_stagger_p1`) is a new exploratory mechanism identity, not a baseline. It runs `baseline-v2` first, on the
seat's own current observation and memory at every decision, through the existing add-on wrapper
(`experiments/exploratory_addon.py`, unchanged), and then applies Sprint 26's frozen T6-S rule to that decision.

* **The rule is Sprint 26's, verbatim.** Sprint 26's shadow is non-executable, and Sprint 26's own frozen test (whose
  digest Sprint 26's mutation record pins) fixes the exact list of source, script and test files that may name it. The candidate therefore
  carries a mechanical copy of the shadow's text from its first documented code to the end of its decision function
  (the shadow's three identity constants excepted), between two marker lines, and imports the same three helpers the
  shadow imports, unchanged: the published weapon ranges (`evaluation/t7_candidates.py`), the hex distance
  (`evaluation/t7_visibility.py`) and the free-flow relation (`experiments/t9_batch.py`). A test locates the frozen
  file through Sprint 26's protocol pins, checks its pinned digest and requires the marked block to equal it line for
  line. No Sprint 27 file names or imports the shadow; where Sprint 27 needs the frozen rule itself (the offline
  fidelity of section 8 and the rehearsal of section 19) it calls Sprint 26's own analysis (`evaluation/s26_t6s.py`,
  `run_shadow`), which does.
* **Only edit:** at an episode's start the leader's `baseline-v2` MOVE passes and every follower's MOVE is withheld;
  while a follower is pending, every `baseline-v2` MOVE of it is withheld. Nothing is added, replaced, reordered or
  constructed: a released follower moves only if `baseline-v2` emits a MOVE for it on that decision's own observation.
  No stop command, route change, objective reassignment, target-selection change, global movement allocation, threat
  memory, combat-priority change or scenario-specific exception.
* **Inputs:** the seat's own observation read exactly as Sprint 18's census frames read it (the operators of the seat's
  colour are own; every other operator in the seat's view is a visible enemy; the listed actions), the setup cost data
  and the rule's memory. Nothing reads another seat's view, the all-seeing state, the clock or randomness.
* **Memory:** the rule's episode state, encoded as integer pairs (position, value) in the wrapper's add-on memory and
  empty at the start of every game; the empty state is `()`. Memory that cannot be decoded raises, so the wrapper plays
  `baseline-v2`'s decision and records the error, which is a structural stop (S7); it is never re-interpreted.
* **Source identity:** 29 files (`baseline-v2`'s set, the add-on wrapper, the three helper modules with the analysis
  package marker and the support module the published ranges need, and the candidate), digest
  `9d74eb78208ff7ad10b33b3974f2831754122dba2bff1684177d6fbd4b44e29e` (line endings normalised).

## 7. The frozen T6-S semantics (Sprint 26, sections 5 to 9, unchanged)

* **Mover:** a `baseline-v2` MOVE at a play decision is eligible when, in this order, the unit is an own ground unit
  (type 1 or 2) with a readable hex; it has exactly one MOVE in the list; it is not already moving (empty route and no
  positive speed); it has no embark or disembark; action type 1 is listed for it; its route and free-flow times are
  readable; it is in no active episode; it is re-armed.
* **Trigger:** eligible movers grouped by (current hex, first route hex); a group of at least two with at least one
  threat-exposed member (Sprint 18's predicate: a visible enemy's published direct-fire range against the mover's type
  covers its hex or one of the first five route hexes) starts an episode.
* **Leader and chain:** ordered by (free-flow arrival, route cost, route length, unit id); the first is the leader.
* **Release:** the next pending member is released at the first play decision at which the reference (initially the
  leader) is absent or observed on a readable hex other than the shared start hex; a member released with a MOVE
  becomes the reference. **Wait bound:** when `cur_step - reference release step > 2 * reference hex time + 10`, every
  pending member is released at once (`timeout`).
* **Limits:** a unit belongs to at most one active episode; after completion each member is spent at the start hex
  until observed elsewhere. A pending member absent or observed elsewhere leaves the queue. An episode open at the
  side's last decision is closed there (`open_at_end`). Non-play decisions pass unchanged.

## 8. On-policy fidelity

**Live**, at every decision of both seats (the timeline of section 9): for the candidate's seat, `baseline-v2` is
re-decided from the seat's own observation and carried memory, the rule is re-applied to that list from the carried
rule memory, and the result must equal the emitted actions, the wrapper's change records and skip counts, `baseline-v2`'s
trace digest, with no add-on error and the memory chain intact (the memory carried into a decision equals the
reconstruction's memory after the previous decision, empty before the first); every difference between the emitted
list and `baseline-v2`'s must be exactly the rule's withheld MOVEs, the rest in order. For the `baseline-v2` seat, its
own reconstruction, trace digest, policy and memory chain.

**Offline**, from the captures and empty memories (`scripts/s27_analysis.py game`, section 15): both seats re-derived at every decision and compared
with the carried memories and emitted lists; Sprint 26's frozen rule replayed on the candidate's live trajectory through
Sprint 26's own analysis (`run_shadow`, with `baseline-v2`'s reconstructed lists) must give exactly the emitted list at
every decision and exactly the rule events the candidate recorded; Sprint 26's independent action-level check
(`IndependentCheck`, Sprint 18's threat predicate and its own bookkeeping) must find no unexplained difference; and the
candidate must equal `baseline-v2` at every decision before its first withholding. After the first divergence only the
live trajectory is used; no historical future state is substituted. Sprint 26's first divergences (blue at step 161,
red at step 401) are reported against the new games but not required: the new opponent can change the candidate's
observations earlier.

## 9. Capture

`evaluation/s27_capture.py` (`StaggerTimeline`, Sprint 22's full-step timeline adapted to a head-to-head game) keeps,
privately and for every step, the all-seeing state and both seats' observations, memories, emitted actions and their
pre-execution copies, the engine's feedback (acceptance and refusals), the judge records, `baseline-v2`'s
reconstruction of both seats, the rule's withheld indices, events and memory, every consistency and difference finding,
and the final post-step state. Positions, stacking, visible enemies, damage and destruction, objective flags and first
ownership are read from these. Record and five capture files are written exclusively under the ignored
`local/evaluation/s27-t6s-probe-1/`, digested in the record; nothing is overwritten.

## 10. Frozen references

`evaluation/s27-t6s-probe/references.json` (`scripts/s27_analysis.py references`, regenerated byte for byte) reads the
four HH timelines through Sprint 26's own driver and loader, unchanged, refusing unless every Sprint 26 input pin
matches, and checks that each HH exposure equals Sprint 26's published per-side exposure, that each side carries the
same seven objective labels, that `baseline-v2`'s reconstruction equals the recorded seat at all 11,524 HH decisions,
and that the references equal the frozen rules (`s27_probe.RULES`).

| HH seat-game | E4 | first ownership (step): 50-point A, B, C, D; 80-point A, B, C |
|---|---:|---|
| HH p01 `baseline-v2` blue | 9,122 | 161, 222, 364, 442; 421, 283, 161 |
| HH p03 `baseline-v2` blue | 29,248 | 161, 222, 364, 442; 421, 283, 161 |
| HH p02 `baseline-v2` red | 6,518 | 421, 543, 2,737, 401; never, 482, never |
| HH p04 `baseline-v2` red | 6,489 | 421, 543, 561, 401; never, 482, 604 |

The two blue references first own every objective at the same steps. Neither red reference ever first-owns the 80-point
objective A, so it has no red P2 timing reference.

## 11. P1, the exposure stop (exact)

* **E4**, per candidate seat-game: over the play decisions of the candidate's seat, the own ground unit-decisions in
  which the unit is moving (a non-empty route or a positive speed), stacked (the engine's `stack` field) and inside an
  applicable envelope (a visible enemy's published direct-fire range against the unit's type covers its hex): Sprint
  26's `exposure`, key `moving_stacked_inside_envelope`, the same function that produced the references.
* **Rule:** P1 triggers when candidate E4 exceeds half the arithmetic mean of E4 in the two same-colour HH seat-games;
  equality passes; in exact integers, `4 * E4 > sum of the two references`. Blue: `4 * E4 > 38,370`, so E4 9,592 passes
  and 9,593 triggers. Red: `4 * E4 > 13,007`, so E4 3,251 passes and 3,252 triggers. The 50% target is not tuned.
* **Reported, descriptive:** all moving ground unit-decisions inside envelopes (stacked and alone), the stacked share
  among them, E4 per moving unit-decision against the references', the moving unit-decisions of withheld followers,
  the number and duration of completed episodes, and the absolute and relative change of E4 against the reference
  mean. A lower E4 that comes mainly from less movement is not evidence that staggering reduced damage or improved play.

## 12. P2, the onward-capture stop (exact)

* **First ownership** of an objective by a seat: the `cur_step` of the first play decision of that seat at which the
  objective's flag, in the seat's own observation, reads the seat's colour (Sprint 26's `first_ownership`). **Never**:
  no such decision up to and including the seat's last decision of the game. Objectives are named by Sprint 11's public value
  labels; a game whose labels are not the registered seven is a structural stop (S7).
* **Rule:** for every objective first owned by the candidate's colour in at least one of its two same-colour HH
  references, the reference step is the latest finite first-ownership step among those two; P2 triggers when the
  candidate never first-owns that objective or first-owns it at a later step; equality passes. An objective neither
  same-colour reference first-owned has no timing reference: it is reported separately and cannot trigger P2; no
  timestamp is invented and absence is never zero.
* **Reported:** for every objective the candidate's step, the reference step and the difference from each reference
  game; Sprint 24's four-game reading (the latest finite step among all four HH seats) as a sensitivity analysis only.
* P2 is a conservative exploratory safety rule, not proof of a causal delay of first ownership.

## 13. The mechanism-observation rule

An **executed episode** is an episode on the live trajectory that completed before the game's end and in which at least
one withheld follower was released because its reference was observed off the shared start hex (release reason
`reference_left`) and was afterwards observed on a readable hex other than the start hex. A session **observes the
mechanism** when it has at least one executed episode. A session without one is `MECHANISM_NOT_OBSERVED` whatever its
exposure; a low E4 alone never makes a session mechanism-supported. Releases by the wait bound (`timeout`) or because
the reference disappeared (`reference_absent`) are reported but do not make an episode executed.

## 14. Mechanism and tactical-risk endpoints (reported per seat)

Per episode, from the seat's own observations, the emitted actions and the engine's feedback: the start step, group
size and classes; whether the leader's MOVE was emitted and accepted; the follower MOVEs withheld at the start and the
repeats; per follower the release reason and actual wait, whether `baseline-v2` gave it a MOVE at release and whether
that MOVE was accepted, its actual departure from the start hex and the leader's, its separation from the leader at
its departure, whether it was lost before departing, damage events while it waited on the start hex, its destination
objective, whether the side's first ownership of that objective came after the start and whether the follower, the
leader or another own unit stood on it then, its arrival and its arrival lag behind the leader; per episode within
300 steps of the start, whether members were co-located while moving on a hex other than the start hex (reunion),
on how many hexes and decisions and from when, the stacked moving member unit-decisions inside applicable envelopes, and
the members' damage events by their state (waiting on the start hex, moving stacked, moving alone, stationary).
Per seat: the first registered trigger against Sprint 26's opening divergence, moving ground damage events (stacked and
alone victims) against the references', and followers destroyed while waiting. All of these are descriptive.

## 15. Stages and the gate

* **Stage A:** only session 2797. `scripts/run_s27_probe.py --stage A` refuses unless the ledger shows no session after
  2796. After the game, `scripts/s27_analysis.py game --position 1` evaluates every structural stop, P1, P2 and the
  mechanism rule and writes `evaluation/s27-t6s-probe/game-p01.json`.
* **Gate:** stage B is authorized only when session 2797 completed with no structural stop, P1 not triggered, P2 not
  triggered and the mechanism observed (`s27_probe.stage_gate`). Otherwise the probe stops, session 2798 is not opened
  and the result returns to the owner.
* **Stage B:** only session 2798. The runner refuses unless the ledger shows exactly session 2797 (this card's first
  game, closed with integrity ok) after 2796, the committed `game-p01.json` authorizes stage B and regenerates byte
  for byte from the stage-A capture, and the card and every pin are unchanged; the game entry point repeats the gate
  and the session-number check. Before it, the ledger, the candidate digest, the privacy scan and the platform canary
  are revalidated and recorded.
* No session 2799. A refusal before the engine is touched opens no session; it may be resolved only without changing
  any frozen file, otherwise the probe ends `T6S_P1_INVALID`.

## 16. Structural stops

| Stop | Meaning |
|---|---|
| S1 | engine-installation integrity failure (session close or the ledger's state chain) |
| S2 | ledger inconsistency, a wrong card, game, stage or digest, an unclosed session, or a session beyond 2797 and 2798 or out of order |
| S3 | a file outside the ignored tree appeared, or a tracked file changed, during the game |
| S4 | a contract error, a wrong margin identity or a game that did not complete |
| S6 | a replay mismatch |
| S7 | an observer error; a missing or digest-mismatched capture; a live decision or memory of either seat that differs from its seat-local reconstruction; a difference from `baseline-v2` that is not the rule's withholding; a candidate add-on error; captures and record disagreeing; a wrong scenario, condition, seat or opponent policy or digest; a `max_step` other than 2,880; objective labels other than the registered seven |
| SF | an offline re-derivation or memory-chain difference of either seat, a decision whose emitted list differs from Sprint 26's frozen rule replayed on the live trajectory, rule events that differ from the frozen rule's, an unexplained difference under Sprint 26's independent check, or a candidate list other than `baseline-v2`'s before the first withholding |

Any structural stop ends the probe. A wrong engine installation, ledger inconsistency, wrong session number,
scenario, seat or opponent, a digest or identity mismatch, a dirty or inconsistent repository, a capture or
reconstruction failure, an unclosed session, a privacy exposure or an unexplained or unregistered action are all covered
by these stops. Nothing is retried.

## 17. Dispositions (first match)

| Disposition | Rule |
|---|---|
| `T6S_P1_INVALID` | any structural, integrity, source, capture or fidelity failure in an opened session; a game that did not complete; or stage B authorized and not run |
| `T6S_P1_MECHANISM_NOT_OBSERVED` | a completed session without an executed episode (section 13) |
| `T6S_P1_MECHANISM_NOT_SUPPORTED` | P1 or P2 triggered in a completed session |
| `T6S_P1_MECHANISM_SUPPORTED` | both sessions ran, each observed the mechanism, and each passed P1 and P2 |

If only session 2797 runs because of an early stop, the result states the one-session outcome and that the paired
two-seat probe was terminated early; one passing seat is never described as a completed two-seat study.
`T6S_P1_MECHANISM_SUPPORTED` would mean only that the registered stagger executed and passed P1 and P2 in both seat
orders of this one scenario. It is not a score improvement, a damage reduction caused by the rule, a survival
improvement, a confirmation or readiness for promotion. The disposition is computed by `s27_probe.disposition` from the
games' public files (`scripts/s27_analysis.py disposition`).

## 18. Outputs and privacy

* Public (`evaluation/s27-t6s-probe/`): before session 2797 `references.json`, `rehearsal.json`, `inputs.json` (the
  card's canonical digest, the candidate and `baseline-v2` digests, the rules digest, the digests of the references,
  the rehearsal and Sprint 26's inputs, protocol and census, the HH pins, the sessions and stages) and
  `mutation.json`; after the sessions `game-p01.json`, `game-p02.json` if opened, and `disposition.json`, all
  regenerating byte for byte (`--check`). Their ledger reads stop at the game's own session so that they regenerate
  after later sessions; the runner and the game entry point audit the whole live ledger. Every public file passes the
  project sanitizer (forbidden keys anywhere; the unit ids and hexes of both seats' observations, objective hexes and
  routes as keys or words, numeric leaves masked) and carries no word made only of digits other than the scenario
  identifiers it reports (2130511121; in the rehearsal file also the scenarios of Sprint 26's H0 side labels, as
  Sprint 26 allowed), or nothing is written.
* Private (ignored `local/`): the records and captures, `local/diagnostics/s27/game-p0N-private.json.gz` (ids, hexes,
  routes and the rule's rows).
* The repository privacy scan over every reachable blob is compared exactly with the 106 accepted hit lines before
  every push. A published result number that happens to match one of the scanner's numeric patterns would be a new
  hit line: it would be adjudicated, disclosed and left for the owner to confirm; no result is reshaped to avoid it.
* **Whitelist** (`tests/test_s27_probe.py`): the identity `t6s-column-stagger-p1` may appear in exactly one run card,
  this one, bound to the registered digest; any other JSON naming it lies in `evaluation/s27-t6s-probe/` and is never
  executable; only the Sprint 27 scripts and modules import the module, and no Sprint 27 file names Sprint 26's shadow.

## 19. Validation before session 2797

* **References** (`references.json`): all six anchors hold. Every HH exposure equals Sprint 26's published per-side
  exposure; the four HH side-games are present; each carries the registered seven objective labels; `baseline-v2`'s
  reconstruction equals the recorded seat at 11,524 of 11,524 HH decisions; the P1 and P2 references equal the frozen
  rules. As a cross-check, the four seats' damage events on moving ground units sum to 117 and split 60 stacked and 57
  alone, Sprint 18's and Sprint 26's HH figures.
* **Rehearsal** (`rehearsal.json`, `scripts/s27_analysis.py rehearse`, 382 s on the evaluation server): the marked
  block equals the frozen rule's text; over every decision of Sprint 26's 20 side-games (45,220: H0 33,696 and HH
  11,524) the copy, run from an empty memory on Sprint 26's frames, gives exactly the lists, withheld indices, events,
  mover checks and group outcomes of Sprint 26's frozen rule run by Sprint 26's analysis (0 decisions differ); and the
  executable candidate (`baseline-v2` then the add-on, on the raw seat observations and recorded memories of the four
  HH seats) gives exactly Sprint 26's candidate list at all 11,524 HH decisions (0 differ), with `baseline-v2` equal to
  the recorded seat at every one, no add-on error, and its first divergences at decision 162 (step 161) for the blue
  seats and 402 (step 401) for the red ones, Sprint 26's.
* **Tests:** `tests/test_t6s_column_stagger_p1.py` (45): Sprint 26's 31 synthetic rule tests (all but its four
  identity tests) ported mechanically onto the copy (exposure, trigger, leader and ties, the one-hex release boundary,
  three followers, a follower without a MOVE at release, a disappearing leader, the exact wait bound and its
  measurement, followers absent or gone, repeats, an unreadable reference, active membership, one episode per stay on
  a hex, a bounded hold) and 14 new ones (the copy against the frozen text and a planted change to it, the frozen
  parameters and helpers, the memory round trip and every malformed form, the observation reading against Sprint 18's
  frames, the add-on's actions, change records, skip counts and memory, failure without cost data or with malformed
  memory, unmodified inputs, the executable policy with the real `baseline-v2` in the stand-in world withholding two of
  three co-located tanks, the identity, the source digest and the imports). `tests/test_s27_probe.py` (39): the card,
  its schedule, stages, pins, budget and colour-matched references; every ledger defect and the stage prerequisites;
  every per-game stop; the registered-difference check including a duplicated action; P1 at its exact half-mean
  boundary (blue 9,592 and 9,593, red 3,251 and 3,252); P2 with both references finite, one or both never owned, a
  candidate that never owns, equality and the same-colour sets; the fidelity stop clause by clause; the mechanism
  rule, the gate and every disposition case with early termination; the sanitizer; the observer and its tampering
  checks; the real game loop in a head-to-head stand-in world (`tests/fixtures/s27_engine.py`, documented movement
  only) with Sprint 26's frozen rule replayed through Sprint 26's analysis and its independent check, and episodes that
  are executed, lose a follower while it waits, are released by the wait bound, are released because the leader
  disappeared, are still open at the end, or start with a refused leader MOVE; the committed-gate check on a temporary
  repository; the whitelist and the absence of Sprint 26's shadow name. `tests/test_real_s27.py` (4, server): the
  references, rehearsal, inputs, game files, disposition and mutation record regenerate byte for byte.
* **Mutation** (`scripts/mutate_s27.py`, `evaluation/s27-t6s-probe/mutation.json`): the first run killed 54 of 64
  planted defects. Seven survivors were test gaps, closed before this registration: a moving unit in the observation
  reading, a game opened again in its own session, an episode still open at the end, a leader lost before departing,
  every member stuck on the start hex, the opponent's memory chain, and the problem named when an authorized stage B
  is not run. Three were equivalent (the trailing-values check of the memory is implied by its round-trip check, stage
  B's first-game check by the ledger's position check, and a departure after release by a departure of a follower
  released because its reference left) and were replaced by a swapped spent pair, a skipped stage-B prerequisite and
  an every-follower rule. The final run on the registered sources killed 64 of 64 with the card rebuilt every
  time; the four defects planted inside the copied rule are caught by the copy check, as they must be.
* **Stand-in rehearsal of the runner** (private, `local/diagnostics/s27/standin_rehearsal.py`; the head-to-head
  stand-in, a session context that records nothing, the ledger file byte-identical before and after): a 40-step
  stage-A game completed, wrote its record and five captures with matching digests and stopped on S7 (not a
  2,880-step game) and the runner's S2 (the fake session is not in the ledger); a full-length stage-A game completed
  with both seats reconstructed at all 2,881 decisions and no consistency or difference finding; its analysis, against
  a ledger showing it as session 2797, found no fidelity problem (all 2,881 decisions equal to Sprint 26's frozen rule
  replayed through Sprint 26's analysis, every difference count zero), the mechanism observed, S7 for the stand-in's
  two objectives, and a public file clean under the sanitizer; stage B was refused without a committed stage-A file
  and, with the gate patched to pass and a ledger showing session 2797, seated the candidate red against `baseline-v2`
  blue; stage A after a session, an unknown game, an existing record and a dirty-tree flag were refused.
* **Defects found and fixed before this registration:** the first runs of the references and the rehearsal were
  refused by the sanitizer (a digit-only word in a sentence; the other scenarios' identifiers in Sprint 26's H0 side
  labels, now allowed for that file only, as Sprint 26 did); Sprint 12's frozen whitelist test refused a public sentence
  naming Sprint 12's candidate identity, now named by class (the first full-suite run on the not yet pushed
  registration found that the references file committed then was a copy made before that rewording; it was
  regenerated on the evaluation server and the unpushed commits were rebuilt); `path` is a forbidden public key and
  became `file` in the inputs; and the stand-in rehearsal found that the public game file would carry the session number and an exact
  integer value as digit-only words, which the sanitizer refuses (both are now numbers). An add-on test first used the
  ported tests' timing stub, which reads a test-only field the observation reading drops; the stub was corrected, not
  the candidate. No rule, threshold or reference changed.
* **Registration checks** (reported in the results, R1): the registration pushed and fetched back byte for byte; the
  workstation, GitHub and the evaluation server at the same commit and tree; the full non-engine suites on the
  workstation, a clean clone and the server's private tree; the server regeneration of the card, references, rehearsal
  and inputs; the stand-in rehearsal from the committed tree; the privacy scan compared exactly with the 106 accepted
  lines; the platform canary rebuilt on both hosts; a read-only engine verify (2,796 sessions, none unclosed).

## 20. Not claimed

No score, damage, survival, population or generality claim. Two games of one scenario against one opponent policy show
whether one frozen rule executes and what it costs there; the HH references are historical seat-games against a
different opponent.
