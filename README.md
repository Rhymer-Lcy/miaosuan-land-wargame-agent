# Miaosuan Land Wargame Agent

庙算兵棋智能体: an AI agent for the 庙算·陆战指挥官 (Miaosuan Land Wargame Commander) platform at
https://wargame.ia.ac.cn/.

## Status

Current baseline: `baseline-v2` (`docs/BASELINE_V2.md`), on the runtime `baseline-v1-runtime-r1`. On top of
the provenance records, the static SDK audit, the runtime environment, the guarded persistent engine
installation and the contract boundary (`docs/CONTRACT.md`), the repository holds `baseline-v0`, a
deterministic, minimal agent that acts only through legal-action information and a final safety gate
(`docs/BASELINE.md`, `docs/EVALUATION.md`), and `baseline-v1`, which adds one change tested in a registered
single-variable experiment: at most one occupation command per objective in a decision step
(`docs/EVALUATION_OCCUPY_RESERVATION.md`). Both are reference points; nothing in them is tuned for winning,
and `baseline-v0` stays reproducible under its original identity. The repeated-run variance of `baseline-v1`
was measured in a registered study with ten repetitions per configuration (`docs/VARIANCE_STUDY.md`), which
also sizes future single-variable experiments. `baseline-v1-runtime-r1` (`docs/BASELINE_V1_RUNTIME_R1.md`)
makes the same decisions as `baseline-v1` with a shortest-path search bounded by the objectives, which
shortens the first play decision on the largest scenario from 0.4-0.5 s to under 0.2 s; it was promoted after
a registered behaviour-preserving remediation (`docs/ROUTING_REMEDIATION.md`), and tactical experiments on top
of `baseline-v1` run on it. `baseline-v2` adds one more change, tested in a registered two-group experiment on
that runtime (`docs/EVALUATION_SHOOT_RESERVATION.md`): at most one shoot action per enemy target in a seat's
decision step. It lowered code-516 refusals from 5.63 to 0.63 per 1,000 unit actions without a safety
regression, and its interval excludes a loss of 10 score points or more against the inert control. Like its
predecessors it is a reference point, and `baseline-v1` stays reproducible under its own identity. A
registered concurrency qualification (`docs/CONCURRENCY_QUALIFICATION.md`) found that games can share the one
persistent engine installation without integrity, independence or accounting effects; `scripts/run_evaluation.sh
--workers N` runs a registered plan with the worker count its manifest registers, and the default stays serial. A
registered runtime thread-pool qualification (`docs/RUNTIME_THREAD_QUALIFICATION.md`) then promoted
`baseline-v1-runtime-r2` (`docs/BASELINE_V1_RUNTIME_R2.md`): runtime-r1's code with NumPy's OpenBLAS pool limited to
one thread, which makes the same decisions with about 23% less CPU per game. On it 32 workers are acceptable (about
27 times the serial throughput); on runtime-r1 the recommendation stays 16. A manifest registers its runtime and worker
count; without them a plan runs serially on runtime-r1. A registered read-only diagnostic
(`docs/RESIDUAL_516_DIAGNOSTIC.md`) traced the residual code-516 refusals of `baseline-v2` in scenario 1930331196 to the
engine removing an unmanned ground vehicle together with the vehicle that launched it, destroyed by the same seat's
earlier shot in the step. A counterfactual design of a rule against it (`docs/LAUNCHER_DEPENDENCY_COUNTERFACTUAL.md`)
found that engine 4.1.0 hides enemy units' launcher relations from a seat's own observation, so a seat-local rule
changes no decision; it was not preregistered. A read-only audit of `baseline-v2`'s first-come target ownership
(`docs/TARGET_ALLOCATION_AUDIT.md`) found, on replayable states, the target given to a strictly weaker shooter in 14
of 110 collision groups (6 recurring situations) and no no-op that left a supported action unused; its declared gate
authorises designing one target-allocation candidate, and nothing was implemented or registered. The design study
(`docs/TARGET_OWNERSHIP_DESIGN.md`) specified that one candidate, `highest-attack-claimant reservation`, for isolated
single-target collisions only; within that scope 9 of the 14 mismatch groups remain (3 situations in 2 games, all on
replayed `baseline-v0` states), so on-policy incidence is the missing fact and the next step is a prospective
prevalence diagnostic of unchanged `baseline-v2`; nothing was implemented or registered. That diagnostic
(`docs/OWNERSHIP_PREVALENCE_DIAGNOSTIC.md`) was registered and played 360 games, but its registered independence-prefix
check failed for 9 stochastic games (a supplementary check found no decision differing on identical observed states),
so it stopped before interpretation: no prevalence is reported and no next-step decision was taken.

Tactical Frontier Sprint 1 (`docs/TACTICAL_FRONTIER.md`) moved the project to tactics-first research: a deterministic
platform upload package of `baseline-v2` (`scripts/build_platform_package.py`, ready for a platform canary), a
capability census, and a rubric committed before scoring that selected deployment disaggregation. Its exploratory
screen (`docs/SCREEN_DEPLOYMENT_SPLIT.md`, preregistered in issue #1) found that engine 4.1.0 accepts deployment splits
in 3 of the 8 frozen scenarios and refuses them in the other 5; its 192 games showed no reliable gain or loss (pooled
head-to-head margin +5.88, 95% interval -78.58 to 97.71), and the registered disposition is REVISE BEFORE
CONFIRMATION. Nothing was promoted. Sprint 2 diagnosed the screen's one deterministic loss with two captured games
(`docs/T1R_DIAGNOSIS.md`): under the engine's four-units-per-hex stacking limit, a split force bound for one
objective blocks itself at that objective and `baseline-v2` never re-orders a unit that is executing a move. No
deployment-side rule corrects that without forbidding the splits themselves, so the revised candidate's specification
(`docs/T1R_SPEC.md`) fails its gate and the T1 line is SHELVED; a play-stage candidate, capacity-aware movement, is
proposed. Sprint 3 designed it offline (`docs/PS1_DESIGN.md`) without an engine session: the block is observable
from seat fields, and under the movement model a stalled-movement recovery releases it, but that model failed its
registered fidelity check and the recovery relies on a stop no capture has tested, so the disposition is
NEEDS_ENGINE_PROBE. Nothing was implemented in the policy, registered or promoted. Sprint 4 ran that probe
(`docs/PS1_ENGINE_PROBE.md`, preregistered in issue #2) in two engine sessions: a stop issued to a unit waiting in
front of a full hex is echoed and flagged by the engine but deferred indefinitely, so the recovery cannot start, and
the post-hoc movement model failed its prospective fidelity test on a fresh game. PS-1 is SHELVED; nothing was
promoted. Sprint 5 studied the T7 family (movement state, stop, weapon lock) offline (`docs/T7_DESIGN.md`) without an
engine session: no T7 action had ever been issued by a frozen policy and march was never listed; of six candidate
mechanisms four failed the safety condition, and concealment of idle stationary units was selected over locking
weapons on their own, which has no documented benefit. Its offline shadow
leaves `baseline-v2` unchanged on every recorded decision; its engine effects are documented but unobserved, so the
disposition is READY_FOR_MECHANISM_PROBE, and a three-game mechanism probe is proposed for the owner's approval
(`docs/T7_SCREEN_PROPOSAL.md`). Nothing was registered, implemented in the policy or promoted. Sprint 6 ran that probe
(`docs/T7_MECHANISM_PROBE.md`, preregistered in issue #3) in three engine sessions: all 16 concealment orders were
accepted and completed in exactly 75 steps, concealed units kept their listed actions, nothing else changed in the
deterministic game, and ground observers beyond half the documented distance did not see a concealed unit; no game
produced a concealed unit that `baseline-v2` later moved or fired, so exit from concealment is untested and the
disposition is NEEDS_TARGETED_PROBE. Nothing was promoted or uploaded. Sprint 7 searched the existing records offline
for a configuration in which `baseline-v2` itself would later move or fire a unit the candidate had concealed
(`docs/T7_E3B_SEARCH.md`), without an engine session: in the three genuine full-step `baseline-v2` seats none of the 16
units the candidate would order was ever commanded again, and none of `baseline-v2`'s 198 moves and shots followed 75
idle steps; the only witnesses are off-policy (`baseline-v2` reconstructed on a `baseline-v0` game, one tank firing
411 steps after the order) in a game that is stochastic before the trigger. The disposition is
E3B_CONFIGURATION_UNCERTAIN, and no probe was proposed. Sprint 8 added an `EXPLORATORY` track beside the registered
`CONFIRMATORY` one (`docs/EXPLORATORY_TRACK.md`): versioned run cards committed before each small batch, a separate
serial runner with the same engine safeguards (the registered evaluator is unchanged), and a ledger-counted session
cap. In 23 exploratory sessions (`docs/SPRINT8_EXPLORATION.md`), indirect artillery fire (T4) executed every order
but its versions either damaged own units or gained nothing, and is shelved; capacity-limited objective allocation
(T9) was above `baseline-v2`'s historical control in 10 of 12 games and is proposed for a registered confirmatory
study (`docs/T9_CONFIRMATION_PROPOSAL.md`, awaiting the owner's approval). Exploratory results are directional and
promote nothing. Sprint 9 registered the confirmatory study of T9 as a staged design (`docs/T9_CONFIRMATION.md`): a
primary head-to-head test in scenario 2130511121 (45 games), then, each only after the previous phase's registered
gate, a small-scenario safety screen and two secondary phases, at most 375 engine sessions in all (public issue #4).
In 285 sessions the primary result was supported: head to head in 2130511121 the candidate improved the seat-averaged
margin by 305.47 points (95% interval 172.87 to 611.24). The safety screen showed identical margins. Against the
inert control in the large scenarios, however, the candidate gained as red in two scenarios and lost as blue in two,
beyond the registered threshold, so the study stopped before its last phase. The disposition is
PRIMARY_SUPPORTED_NEEDS_REVISION; nothing was promoted. Sprint 10 diagnosed the adverse configurations and screened a
same-route revision (`docs/SPRINT10_T9_DIAGNOSIS.md`, PARTIAL_REPAIR_NOT_READY_FOR_CONFIRMATION), and Sprint 11
designed, offline and without engine sessions, a batch capacity allocator (`docs/SPRINT11_BATCH_ALLOCATOR.md`,
READY_FOR_SMALL_EXPLORATORY_PROPOSAL; nothing registered). A small exploratory screen of it is drafted for the owner's
approval (`docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md`), approved for registration and registered
(`docs/SPRINT12_V3_SCREEN.md`). Executed in four sessions, it stopped after its first stage: v3 did not keep T9-v1's
head-to-head pattern (disposition NOT_PRESERVED_IN_PRIMARY; nothing promoted). Sprint 13 diagnosed that result
offline from the four games' full-step captures, with no engine session (`docs/SPRINT13_V3_DIAGNOSIS.md`): the main
actionable difference is the cross-objective reallocation T9-v1 had and v3 removed (REDISTRIBUTION_DOMINANT);
reservations held by units destroyed en route are large in one game and were not predictable from the seat's view.
Sprint 14's offline design competition (`docs/SPRINT14_REDISTRIBUTION.md`, no engine session) found no
feasibility-gated redistribution rule that restores the primary redistribution without also redirecting at the openings
of the 1930331196 adverse configurations (disposition NO_ENGINE_CANDIDATE; session 2791 not opened).
Sprint 15's offline study of delayed, memory-triggered redistribution (`docs/SPRINT15_DELAYED_REDISTRIBUTION.md`, no
engine session) found no trigger that passes its restoration items (disposition NO_RESTORING_TRIGGER); two design
defects found after the replay are disclosed with a post-hoc sensitivity analysis, and no existing adverse capture can
exercise the one trigger family that restores red-seat redistribution.
Sprint 16's registered mechanism capture (`docs/SPRINT16_MECHANISM_CAPTURE.md`, sessions 2791 to 2793) played the frozen
v3 once in each adverse configuration against the inert control and evaluated the delayed rules afterwards as
analysis-side shadows with a corrected memory: on the observed trajectories the post-staging trigger never acts in
1930331196 C3 and first diverges from v3 inside the risk window in C2 and 2120531121 C3, without recreating a diagnosed
mechanism (disposition MECHANISM_AMBIGUOUS); nothing was promoted.
Sprint 17's registered probe (`docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md`, sessions 2794 and 2795) played an executable
form of the post-staging rule once in each of those two configurations: the 1930331196 C2 firing sequence survived, but
in 2120531121 C3 the early redirected vehicles held the problem objective's places while later claimants were blocked
behind them (disposition MECHANISM_REFUTED_212); the rule is retired and nothing was promoted.
On 2026-10-06 the owner shelved T9; Sprint 9's primary result stands, but no deterministic, seat-local revision found
through Sprint 17 kept its redistribution without the adverse mechanisms. Sprint 18's offline frontier reset
(`docs/SPRINT18_FRONTIER_RESET.md`, no engine session) re-read every usable historical capture, admitted three new
families and scored one concrete next increment per family under a rubric registered before scoring: the selected
family is T6, threat-aware movement, with a threat-entry gate as its first experiment. Sprint 19's offline shadow of that
gate (`docs/SPRINT19_T6G_SHADOW.md`, no engine session) found that it never fires on the historical play: every
threat-exposed move already started inside a visible enemy's envelope (disposition T6_G_OFFLINE_INADEQUATE_OPPORTUNITY),
so the timing branch of T6 is closed and nothing was promoted.
Sprint 20's offline replay of the next family's first rule, kill-first target priority (`docs/SPRINT20_T11_REPLAY.md`,
no engine session), found that the public rules do not define the immediate-kill probability its gate needs
(disposition T11_OFFLINE_MODEL_UNAVAILABLE); descriptively the rule changes only which target a shooter fires at, and
nothing was promoted.
Sprint 21's offline audit of the existing direct-fire judge records (`docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md`, no
engine session) found the engine's bookkeeping largely readable from its records but the probability law of its draws
stated nowhere the project may use (disposition DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED), so T11-O1 is closed and
nothing was promoted.
Sprint 22's registered one-session probe of infantry transport (`docs/SPRINT22_T2_TRANSPORT_PROBE.md`, session 2796)
ran the complete chain on engine 4.1.0 for one infantry-carrier pair: embark, carry to an objective the infantry could
not reach on foot within the game, and disembark there, with the documented 75-step transitions (disposition
T2_P1_MECHANISM_SUPPORTED). It is a mechanism result only; nothing was promoted.
The canary's manual upload steps are in `docs/PLATFORM_CANARY.md`; no platform test has taken place.

## Third-party material is not in this repository

The platform's community SDK (engine wheel, map and scenario data, demo code, documentation) carries
no license that authorizes redistribution, so none of it is stored here, verbatim or modified. The
repository records only file names, sizes, SHA-256 digests and observed interfaces
(`docs/PROVENANCE.md`). Machines that hold a legitimately obtained copy keep it under the
git-ignored `local/` tree; nothing in the package or the test suite requires it.

## Layout

| Path | Content |
|---|---|
| `src/miaosuan_agent/` | the project's Python package |
| `scripts/` | command-line tools |
| `tests/` | unit tests (standard library `unittest`; no SDK needed) |
| `environments/` | reproducible definition of the platform-compatible runtime environment |
| `docs/PROVENANCE.md` | identity of the SDK and documentation inputs, licensing status, local archive layout |
| `docs/COMPATIBILITY.md` | static audit of the SDK: engine requirements, inconsistencies, upload constraints |
| `docs/ENGINE_SMOKE_TEST.md` | observed engine behaviour and interface contract from the first controlled run |
| `docs/CONTRACT.md` | observed contract of SDK 4.1.0, accepted boundary, canonical representation, fixture policy |
| `docs/ENGINE_INSTALL.md` | persistent engine installation: rules, session ledger, host clock |
| `docs/BASELINE.md` | identity, decision pipeline, action semantics, safety gate and limitations of `baseline-v0` |
| `docs/EVALUATION.md` | the registered evaluation protocol of `baseline-v0` and its results |
| `docs/BASELINE_V1.md` | identity of `baseline-v1`: the one change, its digests and its limitations |
| `docs/EVALUATION_OCCUPY_RESERVATION.md` | the registered single-variable experiment that produced `baseline-v1`, and its results |
| `docs/VARIANCE_STUDY.md` | the registered repeated-run variance study of `baseline-v1`: design, statistics, planning method, results |
| `docs/LATENCY_DIAGNOSTIC.md` | the measured causes of the rare decision-latency tail of `baseline-v1`, and the remediation decision |
| `docs/ROUTING_REMEDIATION.md` | the registered behaviour-preserving routing remediation of `baseline-v1`: contract, equivalence argument, criteria, results |
| `docs/BASELINE_V1_RUNTIME_R1.md` | identity of `baseline-v1-runtime-r1`, the runtime of `baseline-v1` with target-bounded routing |
| `docs/BASELINE_V1_RUNTIME_R2.md` | identity of `baseline-v1-runtime-r2`: runtime-r1's code with NumPy's OpenBLAS pool limited to one thread |
| `docs/EVALUATION_SHOOT_RESERVATION.md` | the registered two-group experiment of same-step shoot-target reservation that produced `baseline-v2`: design, criteria, results |
| `docs/BASELINE_V2.md` | identity of `baseline-v2`: the one change, its digests and its limitations |
| `docs/REFUSAL_TAXONOMY.md` | how engine refusals are recorded (facts) and attributed (versioned rules); the code-203 correction |
| `docs/CONCURRENCY_QUALIFICATION.md` | the registered diagnostic of running several engine games at once: shared sessions, plan, criteria, results |
| `docs/RUNTIME_THREAD_QUALIFICATION.md` | the registered diagnostic of constraining NumPy's OpenBLAS thread pool: evidence, plan, criteria, results |
| `docs/RESIDUAL_516_DIAGNOSTIC.md` | the registered read-only diagnostic of what removes the targets of `baseline-v2`'s residual code-516 refusals |
| `docs/LAUNCHER_DEPENDENCY_COUNTERFACTUAL.md` | the counterfactual design of a launcher-dependent shooting rule: relation semantics, candidate, replay, gate, results |
| `docs/TARGET_ALLOCATION_AUDIT.md` | the read-only audit of `baseline-v2`'s first-come shoot-target ownership: population, definitions, oracle, gate, results |
| `docs/TARGET_OWNERSHIP_DESIGN.md` | the design study of one target-ownership candidate: formal model, semantics, isolation, evidence boundaries, diagnostic and A/B design, contract, results |
| `docs/OWNERSHIP_PREVALENCE_DIAGNOSTIC.md` | the registered prospective diagnostic of how often `baseline-v2` meets an actionable target-ownership mismatch: events, observer, plan, rules, results |
| `docs/TACTICAL_FRONTIER.md` | the tactics-first roadmap: architecture, research states, capability census, selection rubric, hypothesis register, roadmap, platform canary and failure ledger, BOKE-2026 holdout |
| `docs/SCREEN_DEPLOYMENT_SPLIT.md` | the exploratory screen of deployment disaggregation: registration, mechanism smoke and engine semantics, A/B, reading, disposition |
| `docs/T1R_DIAGNOSIS.md` | the diagnosis of the screen's deterministic loss: pre-declared hypotheses and observables, two captured games, verdicts, engine facts |
| `docs/T1R_SPEC.md` | the revised deployment-split candidate's specification (probe and stop, stack-void avoidance), the correction the diagnosis calls for, gate G6 and its verdict |
| `docs/PS1_DESIGN.md` | the offline design study of capacity-aware movement: formal model, observation audit, amendment, fidelity, certificates, generalisation, gates, disposition, the smallest engine probe |
| `docs/PS1_ENGINE_PROBE.md` | the registered two-session engine probe of PS-1: the diagnostic hook, the stop semantics (P1), the prospective test of the movement model (P2), post-hoc descriptions, gates and disposition |
| `docs/T7_DESIGN.md` | the offline design study of T7 movement-state micro: protocol, action-semantics matrix, opportunity audit, candidate pool, rubric and selection, specification, offline shadow checks, gates and disposition |
| `docs/T7_SCREEN_PROPOSAL.md` | the proposed mechanism probe of idle concealment (for the owner's approval; not a registration) |
| `docs/T7_MECHANISM_PROBE.md` | the registered three-game mechanism probe of idle concealment: candidate, capture, endpoints, gates, results, post-hoc descriptions and disposition |
| `docs/T7_E3B_SEARCH.md` | the offline search for a natural E3b configuration: datasets, episode rules, evidence categories, rubric, decision rule, results, leads and disposition |
| `docs/EXPLORATORY_TRACK.md` | the exploratory track: run cards, the exploratory runner and its safeguards, evidence and reporting, stopping |
| `docs/SPRINT8_EXPLORATION.md` | Sprint 8's exploratory batches: T4 indirect fire (three versions) and T9 capacity-limited allocation, engine facts, game-level results, comparison and selection |
| `docs/T9_CONFIRMATION_PROPOSAL.md` | the proposed confirmatory study of T9 (for the owner's approval; not a registration) |
| `docs/T9_CONFIRMATION.md` | the registered, staged confirmatory study of T9: identities, design, estimand, interval, power, phase gates, failure handling, integrity, validation, disposition, results |
| `docs/SPRINT10_T9_DIAGNOSIS.md` | Sprint 10's full-step T9 failure diagnosis, same-route T9-v2 revision, eight-game exploratory screen and disposition |
| `docs/SPRINT11_BATCH_ALLOCATOR.md` | Sprint 11's offline design of a batch capacity allocator: control audit, formal model, designs considered, frozen-capture replay, certificate, prevalence, tests and disposition |
| `docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md` | the proposed Sprint 12 exploratory screen of the batch capacity allocator (a draft for the owner's approval; not a registration, no engine authorization) |
| `docs/SPRINT12_V3_SCREEN.md` | the registered Sprint 12 screen: approval, identities, stage cards, frozen implementation, capture, registration clarifications, pre-session validation, results and disposition |
| `docs/SPRINT13_V3_DIAGNOSIS.md` | Sprint 13's offline diagnosis of v3's primary-scenario failure: protocol, four-policy reconstruction, difference classes, reservation episodes, prospective features, oracle decomposition, Sprint 9 comparison and disposition |
| `docs/SPRINT14_REDISTRIBUTION.md` | Sprint 14's offline design competition of bounded cross-objective redistribution rules: protocol, eight frozen candidates, fidelity, primary and adverse replay, gate, rubric and disposition |
| `docs/SPRINT15_DELAYED_REDISTRIBUTION.md` | Sprint 15's offline study of delayed, memory-triggered redistribution: reference diagnostics, protocol, six frozen stateful candidates, replay, gate, adequacy rule, disposition and a post-hoc sensitivity analysis |
| `docs/SPRINT16_MECHANISM_CAPTURE.md` | Sprint 16's registered three-session mechanism capture of the frozen v3: card, corrected analysis-side shadows, first-divergence rules, restoration and recourse measures, results and disposition |
| `docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md` | Sprint 17's registered two-session probe of the executable delayed post-staging candidate: card, prefix check, direct-fire endpoints, EARLY-PLACE BLOCK audit, retirement rules, results and disposition |
| `docs/SPRINT18_FRONTIER_RESET.md` | Sprint 18's offline frontier reset after T9 was shelved: populations, census definitions, new-family scan, increment rubric with information per session, results, scores, sensitivity and the selected next family |
| `docs/SPRINT19_T6G_SHADOW.md` | Sprint 19's offline shadow study of the T6-G threat-entry gate: frozen gate and hold state machine, evidence boundary, fidelity, opportunity and capturer rules, results and disposition |
| `docs/SPRINT20_T11_REPLAY.md` | Sprint 20's offline replay of the T11-O1 kill-first target rule: frozen rule and reservation semantics, classification of differences, the documentary kill-model assessment, fidelity, opportunity and coupling rules, results and disposition |
| `docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md` | Sprint 21's offline audit of direct-fire adjudication semantics in the existing judge records: frozen corpus and pairing, the K2 to K6 rules, sufficiency, results, post-hoc findings and disposition |
| `docs/SPRINT22_T2_TRANSPORT_PROBE.md` | Sprint 22's registered T2-P1 transport mechanism probe: the transport-semantics audit, the frozen witness selection, the candidate and its state machine, the endpoints, the one engine session, results and disposition |
| `docs/PLATFORM_CANARY.md` | the owner's manual upload and compatibility-check steps for the platform canary |
| `evaluation/<name>/` | each registered evaluation's manifest and sanitized results |
| `evaluation/latency-diagnostic-1/` | the registered latency diagnostic plan and its privacy-safe aggregates |
| `evaluation/routing-remediation-1/` | the routing remediation's registration, pinned corpus and privacy-safe results |
| `evaluation/baseline-v2-candidate-shoot-target-reservation/` | the shoot-reservation experiment's manifest, registration push record, counterfactual and mutation aggregates, and results |
| `evaluation/refusal-taxonomy-correction/` | historical refusal facts derived from the unchanged records |
| `evaluation/concurrency-qualification-1/` | the concurrency qualification's plan and its privacy-safe results |
| `evaluation/runtime-thread-qualification-1/` | the runtime thread-pool qualification's plan and its privacy-safe results |
| `evaluation/baseline-v2-residual-516-diagnostic-1/` | the residual-516 diagnostic's manifest and its privacy-safe results |
| `evaluation/launcher-dependency-counterfactual-1/` | the launcher-dependency candidate's mutation results and counterfactual aggregates |
| `evaluation/target-allocation-audit-1/` | the target-allocation audit's privacy-safe aggregates |
| `evaluation/target-ownership-design-1/` | the ownership design study's structural analysis and planning sensitivity |
| `evaluation/baseline-v2-target-ownership-prevalence-1/` | the prevalence diagnostic's manifest, references, observer check, results and prefix diagnosis |
| `evaluation/tactical-frontier-1/` | the capability census, the selection rubric (committed before scoring), the scores and the selection |
| `evaluation/tactical-screen-deployment-split-1/` | the deployment-split screen's manifest, mechanism-smoke facts and exploratory results |
| `evaluation/t1r-diagnosis-1/` | the T1-r diagnosis's public analysis of the two captured games (counts, scores, step indices) |
| `evaluation/ps1-design-1/` | the PS-1 design study's public summary (reconstruction, audit, fidelity, certificates, census) and its post-hoc descriptions |
| `evaluation/ps1-engine-probe-1/` | the PS-1 engine probe's manifest, mutation results, registration issue and its verification, the P1 and P2 results, the gates and the post-hoc descriptions |
| `evaluation/t7-design-1/` | the T7 design study's frozen rubric, audit and candidate aggregates, semantics matrix, scores and selection, post-hoc descriptions, shadow checks, mutation results and gates |
| `evaluation/t7-mechanism-probe-1/` | the T7 mechanism probe's manifest, pre-registration outputs (calibration, premise, equivalence, dry run, mutation), registration issue and its verification, per-game results, gate, stop branch, pooled result and post-hoc descriptions |
| `evaluation/t7-e3b-search-1/` | the E3b search's frozen inputs, known-answer validation, per-dataset results, certificates, independent cross-check, decision, post-hoc descriptions and mutation results |
| `evaluation/s8-*/` | Sprint 8's exploratory run cards (`manifest.json`) and their aggregate game results (`results.json`) |
| `evaluation/t9-confirmation-1/` | the T9 confirmatory study's manifest, planning figures, pre-registration validation and mutation results, registration issue and its verification, phase results and disposition |
| `local/` (git-ignored) | machine-specific material: SDK archives, runtime files, logs, replays |

## Verifying a local SDK copy

```
python scripts/verify_source_archives.py
```

The script checks `local/source-archives/` against the recorded digests. Absent files are reported
as skipped with exit status 0; `--require` makes absence an error (status 2). Any mismatch gives
status 1.

## Running the tests

```
python -m unittest discover -s tests -t .
```

Tests that need private material (real contract fixtures, the persistent engine installation, POSIX
file locking) skip with a stated reason when it is absent, so a public checkout passes without any
SDK asset.

## Engine smoke test

On an x86-64 Linux host with the `miaosuan-runtime` environment (`environments/README.md`), a local
SDK copy and the persistent engine installation (created once; `docs/ENGINE_INSTALL.md`):

```
bash scripts/run_engine_smoke_test.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip [--capture]
```

The script stages one game's data into a new directory under `local/runtime/` and runs the engine
from the persistent installation with an empty environment, the installation's persistent `HOME`,
no user site-packages, no GPU and a hard timeout. The session ledger refuses to start if the
installation or its state changed outside a recorded session. Two inert agents end the deployment
stage and otherwise do nothing; every state passes through the contract boundary
(`docs/CONTRACT.md`). `--capture` also writes private contract fixtures under `local/`.
`PYTHON` is the interpreter of `miaosuan-runtime`. Exit status:
0 PASS, 1 FAIL, 2 invalid input, 3 BLOCKED (the engine reported an authentication failure),
4 REFUSED (an installation guardrail stopped the run).

The default game is scenario `201033019601` on map `9601`: two units, at most 1000 steps. Scenario
files do not name their map; this pairing is established by the scenario's 50 roadblock positions,
which are exactly the 50 cells flagged as roadblocks in map 9601, the only map with such flags.

## Baseline agent and evaluation

`miaosuan_agent.agent.BaselineAgent` implements the platform's agent interface (`setup`, `step`,
`reset`) around the policy in `miaosuan_agent.decision`. The evaluation plays the registered games
on the real engine, one isolated process and recorded engine session per game:

```
python scripts/build_evaluation_manifest.py --check
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip --plan gate1
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive local/source-archives/land_wargame_sdk.zip --plan suite
```

Game records stay under the git-ignored `local/evaluation/`; only sanitized aggregates are
published (`evaluation/baseline-v0/results.json`).

## Constraints to know before development

1. The engine (`land_wargame_train_env` 4.1.0) exists only as a
   `cp310-cp310-manylinux2014_x86_64` wheel: x86-64 Linux with CPython 3.10.
2. The engine embeds a MAC-bound, time-since-first-use authenticator that keeps its state inside
   the installed package. It is used only through one persistent installation that is never
   reinstalled or reset (`docs/ENGINE_INSTALL.md`).
3. The SDK's demo runner does not run as shipped: the data paths it opens do not exist in the
   supplied `Data.zip` (section 3).
4. The platform accepts an upload only as a zip holding a single top-level package `ai` that
   exposes class `Agent`. Development happens in `src/miaosuan_agent/`; the `ai/` tree will be
   generated for upload (section 6).

## Names

| Use | Name |
|---|---|
| Repository and directory | `miaosuan-land-wargame-agent` |
| Display name | Miaosuan Land Wargame Agent |
| Chinese name | 庙算兵棋智能体 |
| Python package | `miaosuan_agent` |

## License

No license has been chosen for this project yet, so no rights beyond those implied by publication
are granted. The third-party SDK material it is developed against is unlicensed and is not
redistributed (`docs/PROVENANCE.md`, section 4).
