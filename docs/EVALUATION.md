# Evaluation protocol: baseline-v0

This document registers how the baseline policy `baseline-v0` is evaluated. It was committed,
together with the manifest `evaluation/baseline-v0/manifest.json`, before any game with the
baseline policy was played on the real engine. The commit that adds them is the registration
record; the manifest deliberately contains no timestamp. Results are appended below the protocol,
never mixed into it.

The goal is a baseline that is **legal, deterministic, active and measurable**, in that order.
Winning is not a goal: nothing in the policy was, or may be, tuned on outcomes.

## 1. Policies

| Identity | Behaviour |
|---|---|
| `baseline-v0` | Deployment stage: end deployment once. Play stage: for each controllable unit, in ascending unit id, at most one action from the first category that has a candidate: engage (the listed shoot option with the highest attack level of at least 1; ties by lower target id, then lower weapon id), occupy (when listed), move (to the unheld objective with the lowest path cost; ties by lower hex; roadblocks avoided for vehicles; never while a move is executing, never away from an unheld objective the unit stands on). Otherwise nothing, with the reason traced. |
| `inert-v0` | Ends deployment the same way (the game cannot start otherwise) and never issues a unit action. It is the control. |

Every action passes the final safety gate (`src/miaosuan_agent/decision/gate.py`) before it
leaves the agent. The policy identity is pinned three ways: the identity string, a golden
decision test (`tests/test_decision_determinism.py`), and the SHA-256 of the policy source
recorded in the manifest (`policy_source`: the agent wrapper, the boundary and the decision
package, line endings normalized). `tests/test_evaluation_registration.py` fails if that source
changes, and `scripts/run_evaluation.py` refuses to play a game with a different source.

## 2. Scenario selection

The rule was fixed before any baseline game and is implemented by
`src/miaosuan_agent/evaluation/selection.py`. The pool is the 50 scenarios shipped with the SDK.

Eligibility; a failure makes the scenario/map pairing or its inputs objectively invalid:

* **E1** the scenario id names a supplied map (the last four digits when they are 9601, otherwise
  the last two);
* **E2** every operator and objective hex lies inside that map;
* **E3** every operator starting on the map (not on board) with a documented movement mode
  (unit types 1 to 3) has at least one traversable neighbour for that mode at its start hex;
* **E4** on a map whose cells carry roadblock flags, the scenario's roadblocks are exactly those cells.

Selection:

* **S1** strata are the maps of the eligible scenarios;
* **S2** from each stratum, the scenario with the fewest operators; ties by smaller `max_time`,
  then smaller numeric id;
* **S3** in addition, the eligible scenario with the most operators overall (ties by smaller
  numeric id), or the next in that order if S2 already picked it;
* **R** replacement only after a documented objective failure (the engine raises during setup,
  before any decision): the next listed alternate of the same pick.

Outcome of the rule: 40 of 50 scenarios are eligible (the other 10 fail E1, as recorded in
`docs/COMPATIBILITY.md` 3.5), spread over 7 maps. The registered scenarios:

| Scenario | Map | Operators (red / blue) | Objectives | `max_time` | Rule |
|---|---|---|---|---|---|
| 2120531121 | 21 | 54 (28 / 26) | 5 | 2880 | S2 |
| 2010211129 | 29 | 11 (6 / 5) | 2 | 1800 | S2 |
| 2010431153 | 53 | 12 (6 / 6) | 2 | 1800 | S2 |
| 1910631192 | 92 | 12 (6 / 6) | 2 | 1800 | S2 |
| 2010131194 | 94 | 4 (2 / 2) | 1 | 1800 | S2 |
| 1930331196 | 96 | 52 (26 / 26) | 5 | 2880 | S2 |
| 201033019601 | 9601 | 2 (1 / 1) | 1 | 1000 | S2 |
| 2130511121 | 21 | 89 (45 / 44) | 7 | 2880 | S3 |

The manifest also records the SHA-256 of each scenario's four input files, so a run can prove it
used exactly these inputs. Scenario and map identifiers are published; scenario contents are not.

## 3. Conditions, repetitions and order

| Condition | Red | Blue | Purpose |
|---|---|---|---|
| C1 | `baseline-v0` | `baseline-v0` | baseline mirror |
| C2 | `baseline-v0` | `inert-v0` | baseline against the control, red side |
| C3 | `inert-v0` | `baseline-v0` | baseline against the control, blue side |
| C4 | `inert-v0` | `inert-v0` | the engine's outcome when nobody acts |

Every configuration (scenario and condition) is played twice: 8 x 4 x 2 = 64 games. Order: for
each repetition, for each scenario in the table's order, for each condition in order. Seats are
1 (red) and 11 (blue), the player list the SDK's own demo runner uses.

Each game is one process and one recorded engine session, with the isolation of the smoke test
(`docs/ENGINE_SMOKE_TEST.md`): empty environment, the persistent installation's home, no user
site-packages, `PYTHONHASHSEED=0`, no GPU, a hard timeout. Caps: `max_time + 1 + 100` engine steps
(a game takes `max_time + 1` steps including the deployment step) and 1800 s of wall time.

## 4. Randomness

The documented engine interface (`setup`, `step`, `reset`) takes no seed, and the platform
documentation shows random draws in combat adjudication (`judge_info` records carry random
numbers). No seed control is claimed and no undocumented engine interface is used. What the
harness controls is its own process: the hash seed, and Python's and NumPy's global generators,
seeded with 20260929 before the engine is constructed and fingerprinted at five points to record
whether the engine draws from them. Whether games are reproducible is **measured** by repeating
every configuration and locating the first step at which the engine state diverges.

The policy itself uses no randomness and no clock; tests enforce this by patching every clock
and random source to raise, and by scanning the decision sources for such imports.

## 5. Metrics

| Group | Definition |
|---|---|
| Reliability | games completed / started; exceptions by origin (engine, setup, agent, contract, reset); step-cap and wall-cap hits |
| Legality | gate rejections by reason (numbers replaced by `N`); engine-reported errors for the seat's actions by code (the all-seeing `actions` field); effect check of every emitted action against the next all-seeing observation: confirmed / not observed / indeterminate, by action type |
| Activity | actions by type; steps with at least one action; units that acted and units seen; first step of each action type; unit-steps per no-op reason |
| Determinism | per-step order-independent digest of the all-seeing state; per-seat chained digest of the decision traces; first divergence between repetitions; in-game replay checks (every 100 steps the decision is recomputed by a fresh policy instance and compared) |
| Outcome | the engine's final `scores` fields exactly as reported; no composite score |
| Performance | per-decision latency with `time.perf_counter`, reported as p50 / p95 / p99 / max by the nearest-rank method (the value at rank ceil(p/100 x n)); total decision time; total engine step time; game wall time; harness time = wall - decisions - engine |

The effect check exists because an engine that stays silent would otherwise make every action
look accepted. Documented effects used: deployment completion sets the seat's `end_deployment`
(or the play stage begins); a move gives the unit a non-empty `move_path` or a new hex;
occupation sets the objective's flag; direct fire adds a `judge_info` record naming shooter and
target.

## 6. Gates

Criteria, evaluated over the repetitions of one configuration:

* **G1** every game reaches the engine's done flag within the step cap, without an exception in
  the engine, the harness or an agent, and without a contract error;
* **G2** both seats end deployment and the play stage begins;
* **G3** every baseline seat emits at least one play-stage unit action;
* **G4** no gate rejection, no engine-reported error for a baseline action, and every emitted move
  and deployment completion confirmed by the next observation; occupy and shoot confirmation is
  reported but not gating, because another action in the same step (such as a second shot at a
  target already destroyed) can legitimately remove its precondition;
* **G5** for every step before the first divergence of the engine state between the repetitions,
  the decision traces are identical, and every in-game replay check matches;
* **G6** every game record contains every registered metric.

**Gate 1** is the baseline mirror on scenario 201033019601 (map 9601), played twice, recorded
separately from the suite. It passes when G1 to G6 all pass; `scripts/run_evaluation.sh` refuses
to start the suite before that. **Gate 2** is the registered suite: all 64 games in the registered
order, with G1 to G6 reported per configuration (criteria about baseline seats do not apply to C4).
No policy change is allowed between suite games; a change invalidates every result and requires a
new identity, a new registration and a complete rerun. Scenarios are never dropped, added or
reordered after results are seen, except by rule R.

## 7. Analysis commitments

* No composite quality score.
* Outcomes are reported per game and summarized descriptively per condition. Eight scenarios and
  two repetitions support no claim that one policy is stronger than another, and none is made.
* A game that was started but left no record stops the run; it is investigated and documented
  before anything is rerun, so outcomes cannot be selected by retrying.

## 8. Artifacts

| Artifact | Where | Public |
|---|---|---|
| Manifest (the registration) | `evaluation/baseline-v0/manifest.json` | yes |
| Sanitized results: counts, rates, percentiles, engine scores, gate verdicts | `evaluation/baseline-v0/results.json` | yes |
| Game records: per-step digests, raw latencies, feedback details | `local/evaluation/baseline-v0/games/` | no (git-ignored) |
| Staged inputs, logs, engine session ledger | `local/` | no |

## 9. Reproducing

```bash
python scripts/build_evaluation_manifest.py --check          # the manifest re-derives from the SDK archive
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan gate1
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan suite
python scripts/run_evaluation.py summarize --public evaluation/baseline-v0/results.json
```

`PYTHON` is the interpreter of the `miaosuan-runtime` environment and `ZIP` the local copy of the
SDK archive; the engine runs only on Linux, from the persistent installation
(`docs/ENGINE_INSTALL.md`).

## Results

None at registration.
