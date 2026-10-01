# Baseline identity: baseline-v0

> From 2026-09-30 the current baseline was `baseline-v1` (`docs/BASELINE_V1.md`), which adds one registered
> change to this policy; since 2026-10-01 it is `baseline-v2` (`docs/BASELINE_V2.md`), which adds a second.
> This record, the policy source and every `baseline-v0` artefact are kept unchanged and still verify.

`baseline-v0` is the project's first agent: deterministic, minimal, legal and active by
construction, and measured by the registered evaluation (`docs/EVALUATION.md`). It is a reference
point, not a competitor: no part of it was tuned on outcomes, and it must not be changed under
this name. Any behavioural change needs a new identity, a new registration and a complete rerun.

## Identity

| Field | Value |
|---|---|
| Identity | `baseline-v0`; control policy `inert-v0` |
| Policy source | SHA-256 `8e209640534e0af597fdcf4c7911bdcce417c6f2b883671e5bbfc0d243e43a13` over `agent.py`, `boundary/` and `decision/` (rule in `src/miaosuan_agent/evaluation/identity.py`) |
| Golden decisions | trace chain `0743df89c0855d7673352ce16727c1c613264839659b157183f6a97fbaa7cff2` (`tests/test_decision_determinism.py`) |
| Registration | commit `0a806f1` (author date 2026-09-29T23:58:00+08:00), pushed to GitHub at about 2026-09-30T00:00+08:00, before the first baseline engine session (Gate 1, opened at about 00:01+08:00); manifest canonical SHA-256 `01c1f88b064ace501e56018576426cea6291bbabdce0e35387f72bec2d0068e6` |
| Engine | `land_wargame_train_env` 4.1.0 from the persistent installation; SDK archive SHA-256 `ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725` |
| Runtime | CPython 3.10.20 (`miaosuan-runtime`, CPU only); the public tests also pass on CPython 3.12 |
| Configuration | none: the policy has no parameters, thresholds or weights |
| Evaluation | Gate 1 passed all six criteria. Suite of 64 games: G1, G2 and G6 passed in all 32 configurations, G3 and G5 in all 24 applicable ones; G4 (legality) failed in 14 of 24, because the engine refused 187 of 3,383 unit actions (5.5%) in same-step conflicts (`docs/EVALUATION.md`, Results) |

Verify the identity of a checkout:

```bash
python -m unittest tests.test_evaluation_registration tests.test_decision_determinism
```

## Decision pipeline

One step, from the raw observation to emitted actions, using only the canonical boundary:

1. `Observation.from_raw` (the boundary; malformed input is a contract error, never guessed);
2. tactical context: controllable units sorted by id, objectives not held by the faction sorted
   by hex, roadblocks, and every excluded unit with its reason;
3. candidates, each originating in the current legal-action information: shoot options and
   occupation as listed in `valid_actions`; movement when listed, with the path built from the
   setup cost graph; deployment completion as the one documented exception;
4. priority engage, occupy, move, then nothing; ties broken by explicit keys (attack level, target
   id, weapon id; path cost, hex);
5. the final safety gate, which re-derives every check and rejects rather than repairs;
6. emission of the accepted actions and a decision trace with a stable digest.

## Action semantics used

| Type | Meaning | Legality source | Parameters |
|---|---|---|---|
| 1 move | move along a path of adjacent hexes; cannot be changed once issued | listed in `valid_actions` (value `None`) | `move_path` built by shortest path on the setup cost graph, roadblocks excluded for vehicles |
| 2 shoot | direct fire | listed option | `target_obj_id`, `weapon_id` copied from one option with attack level at least 1 |
| 5 occupy | take the objective the unit stands on | listed in `valid_actions` | none |
| 333 end deployment | end the seat's deployment stage | documented as absent from `valid_actions`; available while deploying | none |

The evidence for each entry, and its remaining uncertainty, is in
`src/miaosuan_agent/decision/semantics.py`.

## Safety gate

An action leaves the agent only if its type is catalogued (an int, never a bool), its keys are
exactly the catalogued ones, `actor` is the agent's seat, the stage allows it, and: for deployment
completion, it is available and not duplicated in the step; for a unit action, the unit is
controllable, has no other action in the step, and the type is listed for it; shoot parameters
are ints equal to a listed option; a move is not issued to a unit already moving, and its path is
a non-empty list of distinct int hexes, each a traversable neighbour of the previous one, never
the start hex and never a roadblock for vehicles. Rejections are recorded in the trace.

## Known limitations

### Policy

* One action per unit per step, in the fixed order engage, occupy, move, with no coordination
  between units: several units standing on one objective all occupy it in the same step, and
  several units may fire at one target in the same step. In the diagnostic games these were the
  circumstances of every refusal with code 1804 or 516, the two most frequent codes in the suite.
* Target choice is the highest attack level with ties to the lowest target id, so fire
  concentrates on one target. There is no threat assessment and no use of line of sight, cover or
  terrain beyond movement cost.
* Movement goes to the nearest objective not held, by path cost. It ignores enemy positions and
  minefields, never changes movement state (march, cover), never stops a move, and a move cannot be
  redirected once issued, so a unit may continue towards an objective that changed hands.
* Once every objective is held the units idle, and a unit on an unheld objective whose occupation
  is blocked waits there indefinitely.
* Units of a type without a documented movement mode (any type other than 1 to 3, such as
  fortifications) never move, and passengers are never unloaded; loading, unloading, indirect and
  guided fire and every other action type are unused.
* Rare decisions are slow (the slowest in the suite took about 1.3 s); the cause was not measured.

### Engine

* Outcomes are not reproducible through the documented interface. In the suite every
  configuration in which a shot was fired diverged between its repetitions exactly one step after
  the first shot, and every configuration without a shot repeated exactly; the engine draws from
  neither of the process's global generators, and no seed is documented.
* `valid_actions` describes the start of a step, and actions resolved earlier in the same step can
  invalidate later ones (refusal codes 1804, 516 and 203). A shot by a unit destroyed earlier in the
  step (203) cannot be foreseen from start-of-step information by any policy. (Correction
  2026-09-30: code 203, engine message `CantControlDiedOperator`, has also been recorded on an
  occupation, so it is not a shooting code; see `docs/REFUSAL_TAXONOMY.md`.)
* The `actions` feedback echoes unit actions but not deployment completion (observed on 4.1.0).
* Only the SDK's engine 4.1.0 (Linux, CPython 3.10) was used. The online platform documents SDK
  5.0.0 or later, so its behaviour may differ.

### Evaluation

* Eight scenarios, four conditions and two repetitions support descriptive statements only. With
  a stochastic engine, two repetitions cannot estimate the variance of outcomes, so no comparison
  of outcomes between policies is possible from this suite.
* The selection favours the smallest force per map plus the largest force overall; mid-sized
  forces are under-represented, and 10 of the 50 scenarios were ineligible (no supplied map).
* Scenario-to-map pairing rests on the naming rule plus consistency checks, not on a declaration
  in the scenario files, which name no map.
* G4 as registered counts refusals caused by the engine's order of resolution within a step, which
  no start-of-step policy can fully avoid. A future protocol should separate same-step conflicts
  from actions illegal at decision time.
* The meaning of the refusal codes comes from diagnostic games outside the registered plan. The
  effect check reads only the next observation, and occupation and shot confirmations are not
  gating.
* Latency was measured on a shared host; wall time includes the harness's per-step state digests
  (reported separately as harness time). Host clock readings are labels only; durations use a
  monotonic clock.
